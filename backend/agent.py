"""
MAC — Multi-Agent Crisis (response unit). Base class for all agents.

Every MAC runs an identical loop:
  1. PERCEIVE  — read bulletin board since last tick
  2. REASON    — LLM decides whether to act (or mock response)
  3. ACT       — post decision back to bulletin board

No MAC knows about other MACs. They only see the shared state.
Resilience: if this process dies, no other MAC's loop breaks.
"""

from __future__ import annotations

import time
import random
import threading
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Optional

from shared_state import bulletin, Event

logger = logging.getLogger(__name__)

# ── Try importing LLM SDKs; fall back gracefully ─────────────────────────────
try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

try:
    from google import genai as google_genai
    from google.genai import types as google_types
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")


MOCK_RESPONSES = {
    "MEDIC": [
        "Analyzing medical situation. Hospital at 87% capacity. Recommend activating field triage station at grid B-7.",
        "Detected 3 critical patients requiring surgery. Blood supply critically low — requesting LOGISTICS to prioritize medical convoy.",
        "Field station operational. Redirecting incoming patients. Coordinating with EVAC on ambulance routing.",
    ],
    "LOGISTICS": [
        "Supply convoy route compromised. Calculating alternate path via northern corridor — ETA 45 minutes.",
        "Medical supplies prioritized. Deploying convoy to field triage at B-7. Water trucks rerouted to shelter zone.",
        "Aid distribution point established. Cross-referencing COMMS signal map to avoid dead zones.",
    ],
    "POWER": [
        "Grid sector 4 offline. Hospital running on generator — fuel for 6 hours. Requesting emergency fuel from LOGISTICS.",
        "Generator deployed to field hospital. Monitoring critical infrastructure: 2 water pumps, 3 comms relays still online.",
        "Rolling blackout initiated for residential zones to preserve power for medical and comms infrastructure.",
    ],
    "COMMS": [
        "Primary comms relay destroyed. Activating mesh network on 4 backup nodes. Coverage restored to 60%.",
        "Civilian distress signals detected at grid C-9. Relaying coordinates to MEDIC and EVAC.",
        "Secure channel established with external aid organizations. Broadcasting situation report.",
    ],
    "EVAC": [
        "Route Alpha compromised. Switching to Route Bravo — capacity 200 civilians per hour. Bus convoy deploying.",
        "Shelter at Central School at 95% capacity. Opening secondary shelter at university gymnasium.",
        "Coordinating with COMMS on civilian broadcast. Evacuation order issued for zones 3 and 4.",
    ],
}

# Cross-agent reactive responses: keyed by (agent_id, triggering_domain).
# These are chosen when an agent sees a HIGH/CRITICAL post from another MAC,
# making it appear that agents are reading and responding to each other.
REACTIVE_RESPONSES = {
    "MEDIC": {
        "LOGISTICS": [
            "Blood convoy from LOGISTICS confirmed at triage B-7. Surgical team activated — ICU capacity extended 30%.",
            "Medical cargo received. Rerouting critical patients from overflow ward to field station.",
        ],
        "POWER": [
            "ICU and OR switched to generator backup. Blood banks stable. Requesting LOGISTICS fuel resupply in 6 hours.",
            "Operating theatre running on emergency power per POWER alert. Proceeding with critical surgeries.",
        ],
        "COMMS": [
            "Medical team dispatched to grid C-9 per COMMS distress signal. Requesting EVAC casualty transport.",
            "Coordinating with external medical NGOs via COMMS channel. Specialist surgical team ETA T+2h.",
        ],
        "EVACUATION": [
            "Field medics deployed to shelter intake points per EVAC report. Triage protocol active.",
            "Casualty transport integrated with EVAC Route Bravo. Mobile surgical unit repositioned to junction 4.",
        ],
    },
    "LOGISTICS": {
        "MEDICAL": [
            "Blood supply convoy fast-tracked — clearing civilian aid lane. Medical cargo ETA triage B-7: 35 min.",
            "MEDIC blood shortage confirmed. Rerouting food convoy to secondary distribution; medics resupplied.",
        ],
        "POWER": [
            "Emergency fuel convoy deployed to generator sites via Route Bravo. ETA 40 min — 6,000 L capacity.",
            "Fuel reserves reallocated: 60% critical infrastructure, 40% medical per POWER request. Resupply cycle updated.",
        ],
        "COMMS": [
            "Convoy routes uploaded to COMMS mesh network. Avoiding signal dead zones — real-time traffic monitoring active.",
            "Aid manifests broadcast to field teams via COMMS relay. Distribution synchronized across 3 checkpoints.",
        ],
        "EVACUATION": [
            "Supply chain adjusted for EVAC overflow shelter. Aid distribution point relocated to university gymnasium.",
            "Water and food pre-positioned at secondary shelter per EVAC capacity report. Civilian intake flow coordinated.",
        ],
    },
    "POWER": {
        "MEDICAL": [
            "Hospital grid priority elevated. Shedding residential sector load — surgical suite and ICU at full power.",
            "Medical facility generators topped up. Rolling blackout revised to exclude all health infrastructure.",
        ],
        "LOGISTICS": [
            "Fuel convoy from LOGISTICS confirmed. Pre-positioning portable generator at triage site B-7.",
            "Refueling schedule synchronized with LOGISTICS convoy routes. Generator runtime extended to 18 hours.",
        ],
        "COMMS": [
            "COMMS relay nodes added to priority grid list. Generator rerouted — mesh network coverage maintained.",
            "Backup power for all COMMS mesh nodes activated. Infrastructure protected from rolling blackout.",
        ],
        "EVACUATION": [
            "Evacuation corridors excluded from rolling blackout per EVAC route update. Emergency lighting on Route Bravo.",
            "Shelter power circuits isolated from grid failures. Dedicated generator confirmed for civilian intake zones.",
        ],
    },
    "COMMS": {
        "MEDICAL": [
            "Field station coordinates broadcast on all channels. NGO medical teams redirected to triage B-7.",
            "MEDIC casualty report relayed to external aid networks. Requesting specialist surgical team inbound.",
        ],
        "LOGISTICS": [
            "Convoy manifests distributed to all field checkpoints via mesh. Supply vehicles tracked in real time.",
            "Aid distribution broadcast live on civilian radio. Queue management information active.",
        ],
        "POWER": [
            "Backup radio active for POWER blackout sectors. Emergency channel maintained on battery relay.",
            "Grid failure map distributed to all MACs. COMMS links rerouted around failed sectors — coverage 85%.",
        ],
        "EVACUATION": [
            "Evacuation order live on all channels — 4 languages. Estimated 2,000 civilians now en route.",
            "Real-time shelter capacity broadcast to civilians per EVAC update. Route guidance active.",
        ],
    },
    "EVAC": {
        "MEDICAL": [
            "Bus convoy diverted via triage B-7 per MEDIC request. Casualty pickup integrated into evacuation route.",
            "Ambulance corridor cleared on Route Alpha. Civilian buses rerouted to avoid medical traffic at B-7.",
        ],
        "LOGISTICS": [
            "Civilian flow redirected through LOGISTICS aid distribution point. Convoy deconfliction active.",
            "Evacuation buses refueled at LOGISTICS depot. Fleet operational — 12 buses confirmed en route.",
        ],
        "POWER": [
            "Night convoy equipped with emergency lighting. Avoiding POWER blackout sectors on revised route.",
            "Overflow shelter backup power confirmed via POWER — maintaining civilian intake through grid failure.",
        ],
        "COMMS": [
            "Bus dispatched to grid C-9 per COMMS distress signal. ETA 20 minutes — 50-person capacity.",
            "Civilian COMMS broadcast integrated with EVAC routing app. Shelter capacity updated every 5 minutes.",
        ],
    },
}

# Gap-detection responses: when an agent detects a peer is offline, it compensates.
GAP_RESPONSES = {
    "MEDIC": {
        "LOGISTICS": "LOGISTICS offline — medical supply chain at risk. Converting ambulance fleet to emergency supply transport. Blood reserves prioritized from hospital pharmacy stores. Requesting remaining MACs assist with supply routing.",
        "POWER": "POWER offline — hospital backup generators unmonitored. Switching to battery-powered portable equipment. Surgical procedures limited to manual-capable and life-threatening cases only.",
        "COMMS": "COMMS offline — medical coordination degraded. Deploying physical runners between triage sites B-7 and hospital. Visual signal flags active at all field stations for casualty routing.",
        "EVAC": "EVAC offline — casualty transport disrupted. Converting medical vehicles to dual evacuation/triage role. Hospital shelter intake activated — receiving displaced civilians at ER entrance.",
    },
    "LOGISTICS": {
        "MEDIC": "MEDIC offline — medical supply prioritization lost. Establishing emergency aid station at distribution point Alpha. Medical supply convoy fast-tracked to hospital on standing orders.",
        "POWER": "POWER offline — fuel distribution now critical. Emergency fuel convoy deployed to all known generator sites. Battery packs distributed to critical facilities.",
        "COMMS": "COMMS offline — convoy coordination degraded. Using drivers as physical message relay between zones. Printed supply manifests distributed to all checkpoints.",
        "EVAC": "EVAC offline — civilian transport halted. Repurposing 4 supply trucks for civilian evacuation. Distribution points opened as temporary shelters with aid supplies.",
    },
    "POWER": {
        "MEDIC": "MEDIC offline — ensuring uninterrupted power to hospital automation and life-support systems. Generator priority elevated for all medical facilities.",
        "LOGISTICS": "LOGISTICS offline — fuel resupply uncertain. Switching to conservation mode: extending generator runtime via load shedding on non-critical sectors.",
        "COMMS": "COMMS offline — powering all backup radio and mesh relay nodes at maximum priority. Emergency broadcast tower on dedicated generator circuit.",
        "EVAC": "EVAC offline — ensuring evacuation corridor lighting and shelter power remain on priority grid. Emergency lighting deployed on all known safe routes.",
    },
    "COMMS": {
        "MEDIC": "MEDIC offline — broadcasting medical self-aid guidance on all channels (4 languages). Relaying casualty locations to remaining MACs for cross-domain pickup.",
        "LOGISTICS": "LOGISTICS offline — distributing last known supply status to all field teams. Coordinating ad-hoc civilian supply sharing via community radio.",
        "POWER": "POWER offline — switching to battery-powered radio. Reducing broadcast intervals to extend coverage duration. Emergency frequencies maintained.",
        "EVAC": "EVAC offline — broadcasting shelter locations and safe routes on continuous loop. Coordinating civilian self-evacuation via radio guidance every 5 minutes.",
    },
    "EVAC": {
        "MEDIC": "MEDIC offline — equipping all evacuation buses with first-aid kits. Deploying trained volunteers for basic triage at shelter intake. Priority evacuation for visibly injured.",
        "LOGISTICS": "LOGISTICS offline — using evacuation vehicles for emergency supply runs during non-evacuation windows. Fuel conserved for critical transport only.",
        "POWER": "POWER offline — routing evacuations through lit corridors only. All buses equipped with portable lighting. Night evacuations suspended until dawn.",
        "COMMS": "COMMS offline — using bus PA systems for local broadcasts at each stop. Deploying runners between shelters for inter-shelter coordination.",
    },
}


class MAC(ABC):
    """
    Base class for a MAC (Multi-Agent Crisis response unit).
    Subclasses override `persona_prompt` and optionally `mock_reason`.
    """

    def __init__(
        self,
        agent_id: str,
        domain: str,
        tick_interval: float = 5.0,
        mock_mode: bool = False,
        anthropic_api_key: str = None,
        google_api_key: str = None,
    ):
        self.agent_id = agent_id
        self.domain = domain
        self.tick_interval = tick_interval
        self.mock_mode = mock_mode
        self._alive = False
        self._thread: threading.Thread = None
        self._last_event_id: str = None
        self._tick_count = 0
        self._mock_response_index = 0
        self._last_act_time = 0.0
        self._consecutive_idle = 0
        self._client  = None  # Anthropic
        self._gclient = None  # Gemini

        if not mock_mode:
            if google_api_key and _GOOGLE_AVAILABLE:
                self._gclient = google_genai.Client(api_key=google_api_key)
                logger.info(f"[{agent_id}] using Gemini model: {GEMINI_MODEL}")
            elif anthropic_api_key and _ANTHROPIC_AVAILABLE:
                self._client = anthropic.Anthropic(api_key=anthropic_api_key)
                logger.info(f"[{agent_id}] using Claude")

    # ── Abstract interface ───────────────────────────────────────────────────

    @property
    @abstractmethod
    def persona_prompt(self) -> str:
        """System prompt defining this agent's role and expertise."""

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        self._alive = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name=self.agent_id)
        self._thread.start()
        bulletin.post(
            source=self.agent_id,
            event_type="AGENT_ONLINE",
            domain=self.domain,
            severity="INFO",
            source_layer="AGENT",
            payload={"message": f"{self.agent_id} online and monitoring."},
            tags=["lifecycle"],
        )
        logger.info(f"[{self.agent_id}] started")

    def stop(self):
        self._alive = False
        bulletin.post(
            source=self.agent_id,
            event_type="AGENT_OFFLINE",
            domain=self.domain,
            severity="INFO",
            source_layer="AGENT",
            payload={"message": f"{self.agent_id} going offline."},
            tags=["lifecycle"],
        )
        logger.info(f"[{self.agent_id}] stopped")

    def is_alive(self) -> bool:
        return self._alive and self._thread is not None and self._thread.is_alive()

    # ── Main loop ────────────────────────────────────────────────────────────

    def _loop(self):
        while self._alive:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"[{self.agent_id}] tick error: {e}")
            # Jitter ±40% so agents don't fire in synchronized bursts
            jitter = self.tick_interval * random.uniform(0.6, 1.4)
            time.sleep(jitter)

    def _tick(self):
        self._tick_count += 1
        now = time.time()

        # 1. PERCEIVE — read new events
        new_events = bulletin.read_since(self._last_event_id)
        if new_events:
            self._last_event_id = new_events[-1].id

        # 2. REASON — should I act?
        relevant = self._filter_relevant(new_events)

        # Skip if nothing relevant and not time for a periodic check.
        # Periodic check backs off: every ~30s initially, stretching to ~90s
        # when idle for many consecutive ticks.
        idle_period = 6 + min(self._consecutive_idle, 12)  # 6-18 ticks
        if not relevant and self._tick_count % idle_period != 0:
            self._consecutive_idle += 1
            return

        # Per-agent cooldown: don't act again within 10s of last action.
        # Only bypass for SYSTEM crisis events (scenario injections, agent failures)
        # — never bypass for peer ACTION_TAKEN, no matter the severity.
        since_last = now - self._last_act_time
        if since_last < 10.0:
            has_system_crisis = any(
                e.source == "SYSTEM" and e.severity in ("CRITICAL", "HIGH")
                or e.event_type == "AGENT_OFFLINE"
                for e in relevant
            )
            if not has_system_crisis:
                return

        context = self._build_context()
        decision = self._reason(context, relevant)

        if decision and decision.get("action"):
            self._act(decision)
            self._last_act_time = time.time()
            self._consecutive_idle = 0
        else:
            self._consecutive_idle += 1

    def _filter_relevant(self, events: list[Event]) -> list[Event]:
        """Keep events that are actionable for this domain (override to customize)."""
        if not events:
            return []
        skip_types = {"AGENT_ONLINE"}  # Keep AGENT_OFFLINE for gap detection
        # Include own domain + high severity + system + lifecycle + all peer actions
        return [
            e for e in events
            if e.event_type not in skip_types and (
                e.domain == self.domain
                or e.severity in ("CRITICAL", "HIGH")
                or e.source == "SYSTEM"
                or e.event_type == "AGENT_OFFLINE"
                or e.event_type == "ACTION_TAKEN"
            )
        ]

    def _build_context(self) -> str:
        """Construct the situational awareness snapshot passed to the LLM."""
        snapshot = bulletin.snapshot(max_events=30)
        stats = bulletin.stats()
        agent_status = bulletin.agent_status()
        domain_activity = bulletin.domain_last_active()
        now = time.time()
        return json.dumps({
            "agent_id": self.agent_id,
            "domain": self.domain,
            "bulletin_summary": stats,
            "macs_status": agent_status,
            "seconds_since_last_action": {
                k: round(now - v) for k, v in domain_activity.items()
            },
            "recent_events": snapshot,
        }, indent=2)

    def _reason(self, context: str, relevant_events: list) -> Optional[dict]:
        """Route to Gemini, Claude, or mock depending on what's configured."""
        if self._gclient:
            return self._gemini_reason(context, relevant_events)
        if self._client:
            return self._claude_reason(context, relevant_events)
        return self._mock_reason(relevant_events)

    def _build_user_prompt(self, context: str, relevant_events: list) -> str:
        # Build team awareness section
        agent_status = bulletin.agent_status()
        domain_activity = bulletin.domain_last_active()
        now = time.time()

        online = [k for k, v in agent_status.items() if v == "online" and k != self.agent_id]
        offline = [k for k, v in agent_status.items() if v == "offline" and k != self.agent_id]

        silent = []
        for aid, ts in domain_activity.items():
            if aid != self.agent_id and (now - ts) > 45:
                silent.append("{} (silent {}s)".format(aid, int(now - ts)))

        # Format other agents' recent actions for cross-referencing
        other_actions = []
        for e in reversed(relevant_events):
            if e.source != self.agent_id and e.event_type == "ACTION_TAKEN":
                other_actions.append(
                    "  [{}] {}: {}".format(e.id, e.source, e.payload.get("message", "")[:150])
                )
        other_actions = other_actions[:6]

        relevant_summary = json.dumps(
            [{"id": e.id, "type": e.event_type, "source": e.source, "domain": e.domain,
              "severity": e.severity, "payload": e.payload} for e in relevant_events],
            indent=2,
        )

        actions_block = "\n".join(other_actions) if other_actions else "  (none yet)"
        team_section = (
            "TEAM STATUS:\n"
            "  Peers online: " + (", ".join(online) if online else "none visible") + "\n"
            "  Peers offline: " + (", ".join(offline) if offline else "none") + "\n"
            "  Silent domains: " + (", ".join(silent) if silent else "none") + "\n\n"
            "RECENT PEER ACTIONS (reference these by event ID when building on them):\n"
            + actions_block
        )

        return f"""Current situation (shared bulletin board state):
{context}

{team_section}

New events since last tick:
{relevant_summary}

Based on the situation above, decide your next action for domain {self.domain}.

IMPORTANT:
- NEVER start your message with your own agent name — just describe what you're doing
- If a MAC has gone OFFLINE or is silent, acknowledge the gap and describe compensation
- Reference specific event IDs (e.g. EVT-00042) when building on another MAC's work
- Be specific: grid references, quantities, timeframes, ETAs
- Don't duplicate what another MAC already handled

Respond with JSON:
If acting:
{{
  "action": true,
  "event_type": "ACTION_TAKEN",
  "severity": "HIGH|MEDIUM|LOW",
  "message": "what you are doing (reference other MACs and event IDs)",
  "references": ["EVT-XXXXX"],
  "details": {{}}
}}
If no action needed:
{{
  "action": false
}}
Respond ONLY with valid JSON. No markdown."""

    def _gemini_reason(self, context: str, relevant_events: list) -> Optional[dict]:
        """Reason using Gemini."""
        user_prompt = self._build_user_prompt(context, relevant_events)
        try:
            response = self._gclient.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=google_types.GenerateContentConfig(
                    system_instruction=self.persona_prompt,
                    response_mime_type="application/json",
                    max_output_tokens=500,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Gemini error: {e} — using mock")
            return self._mock_reason(relevant_events)

    def _claude_reason(self, context: str, relevant_events: list) -> Optional[dict]:
        """Reason using Claude (Anthropic)."""
        user_prompt = self._build_user_prompt(context, relevant_events)
        try:
            response = self._client.messages.create(
                model="claude-opus-4-6",
                max_tokens=400,
                system=self.persona_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Claude error: {e} — using mock")
            return self._mock_reason(relevant_events)

    def _mock_reason(self, relevant_events: list = None) -> Optional[dict]:
        """Return a context-aware scripted response for demo/testing.

        Priority order:
        1. Gap detection — compensate for offline peers
        2. Reactive — respond to other MACs' actions
        3. Default — cyclic domain responses
        """
        if relevant_events:
            # 1. GAP DETECTION — compensate for offline peers
            for e in relevant_events:
                if e.event_type == "AGENT_OFFLINE" and e.source != self.agent_id:
                    gaps = GAP_RESPONSES.get(self.agent_id, {})
                    gap_msg = gaps.get(e.source)
                    if gap_msg:
                        self._mock_response_index += 1
                        return {
                            "action": True,
                            "event_type": "ACTION_TAKEN",
                            "severity": "HIGH",
                            "message": gap_msg,
                            "details": {"mock": True, "compensating_for": e.source},
                            "references": [e.id],
                        }

            # 2. REACTIVE — respond to other MACs' recent actions
            seen = set()
            candidates = []
            for e in reversed(relevant_events):
                if (e.source != self.agent_id
                        and e.event_type == "ACTION_TAKEN"
                        and e.domain not in seen):
                    seen.add(e.domain)
                    candidates.append((e.domain, e.id))

            reactions = REACTIVE_RESPONSES.get(self.agent_id, {})
            for domain, ref_id in candidates:
                options = reactions.get(domain)
                if options:
                    msg = options[self._mock_response_index % len(options)]
                    self._mock_response_index += 1
                    return {
                        "action": True,
                        "event_type": "ACTION_TAKEN",
                        "severity": "HIGH",
                        "message": msg,
                        "details": {"mock": True, "reacting_to": domain},
                        "references": [ref_id],
                    }

        # 3. Fall back to default cyclic responses
        responses = MOCK_RESPONSES.get(self.agent_id, [])
        if not responses:
            return None
        msg = responses[self._mock_response_index % len(responses)]
        self._mock_response_index += 1
        return {
            "action": True,
            "event_type": "ACTION_TAKEN",
            "severity": "HIGH",
            "message": msg,
            "details": {"mock": True},
        }

    def _act(self, decision: dict):
        """Post the decision to the bulletin board."""
        if not decision.get("action"):
            return

        payload = {
            "message": decision.get("message", ""),
            "details": decision.get("details", {}),
        }
        refs = decision.get("references", [])
        if refs:
            payload["references"] = refs

        bulletin.post(
            source=self.agent_id,
            event_type=decision.get("event_type", "ACTION_TAKEN"),
            domain=self.domain,
            severity=decision.get("severity", "MEDIUM"),
            source_layer="AGENT",
            payload=payload,
            tags=[self.domain.lower(), "action"],
        )
        logger.info(f"[{self.agent_id}] acted: {decision.get('message', '')[:80]}")
