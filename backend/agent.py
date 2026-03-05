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
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Optional

from shared_state import bulletin, Event

logger = logging.getLogger(__name__)

# ── Try importing Anthropic SDK; fall back gracefully ────────────────────────
try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


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

        if not mock_mode and _ANTHROPIC_AVAILABLE and anthropic_api_key:
            self._client = anthropic.Anthropic(api_key=anthropic_api_key)
        else:
            self._client = None

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
        """
        Ask the LLM whether to take action. Returns a decision dict or None.
        Falls back to mock if no client available.
        """
        if self._client is None or self.mock_mode:
            return self._mock_reason()

        relevant_summary = json.dumps(
            [{"type": e.event_type, "domain": e.domain, "severity": e.severity,
              "payload": e.payload} for e in relevant_events],
            indent=2,
        )

        user_prompt = f"""
Current situation (shared bulletin board state):
{context}

New events since last tick:
{relevant_summary}

Based on the situation above, should you take action in your domain ({self.domain})?
If yes, respond with a JSON object:
{{
  "action": true,
  "event_type": "ACTION_TAKEN",
  "severity": "HIGH|MEDIUM|LOW",
  "message": "what you are doing",
  "details": {{}}
}}
If no action needed:
{{
  "action": false
}}
Respond ONLY with valid JSON.
"""

        try:
            response = self._client.messages.create(
                model="claude-opus-4-6",
                max_tokens=400,
                system=self.persona_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text.strip()
            # Strip markdown code blocks if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            logger.warning(f"[{self.agent_id}] LLM error: {e} — using mock")
            return self._mock_reason()

    def _mock_reason(self) -> Optional[dict]:
        """Return a pre-scripted response for demo/testing."""
        responses = MOCK_RESPONSES.get(self.domain, [])
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
