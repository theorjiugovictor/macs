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


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash")


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
            time.sleep(self.tick_interval)

    def _tick(self):
        self._tick_count += 1

        # 1. PERCEIVE — read new events
        new_events = bulletin.read_since(self._last_event_id)
        if new_events:
            self._last_event_id = new_events[-1].id

        # 2. REASON — should I act?
        relevant = self._filter_relevant(new_events)
        if not relevant and self._tick_count % 6 != 0:   # periodic check every ~30s
            return

        context = self._build_context()
        decision = self._reason(context, relevant)

        if decision:
            self._act(decision)

    def _filter_relevant(self, events: list[Event]) -> list[Event]:
        """Keep events that are actionable for this domain (override to customize)."""
        if not events:
            return []
        skip_types = {"AGENT_ONLINE", "AGENT_OFFLINE"}
        # Include own domain + high severity from any domain + system events
        return [
            e for e in events
            if e.event_type not in skip_types and (
                e.domain == self.domain
                or e.severity in ("CRITICAL", "HIGH")
                or e.source == "SYSTEM"
            )
        ]

    def _build_context(self) -> str:
        """Construct the situational awareness snapshot passed to the LLM."""
        snapshot = bulletin.snapshot(max_events=30)
        stats = bulletin.stats()
        return json.dumps({
            "agent_id": self.agent_id,
            "domain": self.domain,
            "bulletin_summary": stats,
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
        relevant_summary = json.dumps(
            [{"type": e.event_type, "domain": e.domain, "severity": e.severity,
              "payload": e.payload} for e in relevant_events],
            indent=2,
        )
        return f"""Current situation (shared bulletin board state):
{context}

New events since last tick:
{relevant_summary}

Based on the situation above, should you take action in your domain ({self.domain})?
If yes, respond with a JSON object:
{{
  "action": true,
  "event_type": "ACTION_TAKEN",
  "severity": "HIGH|MEDIUM|LOW",
  "message": "what you are doing (be specific: locations, quantities, timeframes)",
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

        Prefers a reactive response when another MAC has recently posted
        something relevant, making agents appear to coordinate with each other.
        Falls back to the default cycling responses otherwise.
        """
        # Try to react to the most recent HIGH/CRITICAL post from another MAC
        if relevant_events:
            # Collect unique source domains from other agents (most recent first)
            seen = set()
            candidates = []
            for e in reversed(relevant_events):
                if (e.source != self.agent_id
                        and e.event_type == "ACTION_TAKEN"
                        and e.domain not in seen):
                    seen.add(e.domain)
                    candidates.append(e.domain)

            reactions = REACTIVE_RESPONSES.get(self.agent_id, {})
            for domain in candidates:
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
                    }

        # Fall back to default cyclic responses
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

        bulletin.post(
            source=self.agent_id,
            event_type=decision.get("event_type", "ACTION_TAKEN"),
            domain=self.domain,
            severity=decision.get("severity", "MEDIUM"),
            payload={
                "message": decision.get("message", ""),
                "details": decision.get("details", {}),
            },
            tags=[self.domain.lower(), "action"],
        )
        logger.info(f"[{self.agent_id}] acted: {decision.get('message', '')[:80]}")
