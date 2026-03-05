"""
Crisis Scenarios — timed event injection into the bulletin board.

Each scenario has a sequence of SYSTEM events injected at defined offsets.
Agents perceive these events and respond autonomously — no agent is told what to do.

The cascade is the emergence.
"""

import time
import threading
from dataclasses import dataclass
from shared_state import bulletin


@dataclass
class ScenarioEvent:
    delay: float          # seconds after scenario start
    event_type: str
    domain: str
    severity: str
    payload: dict
    tags: list = None


SCENARIOS = {
    "cascade": {
        "name": "Hospital Cascade",
        "description": (
            "A strike hits the city hospital's power grid. The cascade unfolds: "
            "medical emergency → logistics reroute → power crisis → comms relay lost → "
            "mass evacuation. Watch MACS self-coordinate."
        ),
        "events": [
            ScenarioEvent(
                delay=0,
                event_type="CRISIS_ALERT",
                domain="MEDICAL",
                severity="CRITICAL",
                payload={
                    "message": "City Hospital (Grid A-3) hit. Emergency generators active. "
                               "Capacity at 92%. 47 critical casualties incoming.",
                    "location": "grid-A3",
                    "casualties": 47,
                    "hospital_capacity_pct": 92,
                },
                tags=["strike", "hospital", "cascade-trigger"],
            ),
            ScenarioEvent(
                delay=8,
                event_type="INFRASTRUCTURE_FAILURE",
                domain="POWER",
                severity="CRITICAL",
                payload={
                    "message": "Main grid sectors 3 and 4 offline. Hospital generator fuel: 5 hours.",
                    "sectors_offline": [3, 4],
                    "generator_fuel_hours": 5,
                    "location": "grid-A3",
                },
                tags=["power-failure", "cascade"],
            ),
            ScenarioEvent(
                delay=18,
                event_type="ROUTE_COMPROMISED",
                domain="LOGISTICS",
                severity="HIGH",
                payload={
                    "message": "Route Alpha (main supply corridor) blocked — bridge damaged. "
                               "Medical convoy ETA extended by 2 hours.",
                    "route": "Alpha",
                    "blockage": "bridge-damaged",
                    "impact": "medical-convoy-delayed",
                },
                tags=["route-blocked", "cascade"],
            ),
            ScenarioEvent(
                delay=28,
                event_type="COMMS_FAILURE",
                domain="COMMS",
                severity="HIGH",
                payload={
                    "message": "Primary comms relay (Grid B-5) destroyed. 40% coverage lost. "
                               "Distress signals from civilian zone C-9 going unanswered.",
                    "relay_destroyed": "B-5",
                    "coverage_pct": 60,
                    "distress_location": "grid-C9",
                },
                tags=["comms-failure", "cascade"],
            ),
            ScenarioEvent(
                delay=40,
                event_type="EVACUATION_REQUIRED",
                domain="EVACUATION",
                severity="CRITICAL",
                payload={
                    "message": "Zones 3 and 4 declared unsafe. Estimated 2,400 civilians require "
                               "immediate evacuation. Shelter capacity at 88%.",
                    "zones": [3, 4],
                    "civilians": 2400,
                    "shelter_capacity_pct": 88,
                },
                tags=["mass-evacuation", "cascade"],
            ),
            ScenarioEvent(
                delay=55,
                event_type="SUPPLY_CRITICAL",
                domain="LOGISTICS",
                severity="CRITICAL",
                payload={
                    "message": "Blood supply at City Hospital: O-negative critical (2 units remaining). "
                               "Surgical backlog: 12 patients.",
                    "blood_type": "O-negative",
                    "units_remaining": 2,
                    "surgical_backlog": 12,
                },
                tags=["blood-supply", "cascade"],
            ),
            ScenarioEvent(
                delay=75,
                event_type="EXTERNAL_AID_AVAILABLE",
                domain="COMMS",
                severity="HIGH",
                payload={
                    "message": "WHO field team with 3 surgical units on standby 18km north. "
                               "Requesting coordination channel and convoy escort.",
                    "aid_source": "WHO",
                    "units": 3,
                    "distance_km": 18,
                    "direction": "north",
                },
                tags=["external-aid", "opportunity"],
            ),
        ],
    },

    "blackout": {
        "name": "City-wide Blackout",
        "description": "Rolling blackout hits the city. Agents must triage power to critical systems.",
        "events": [
            ScenarioEvent(
                delay=0,
                event_type="CRISIS_ALERT",
                domain="POWER",
                severity="CRITICAL",
                payload={
                    "message": "City-wide grid failure. All sectors offline. Critical infrastructure "
                               "on backup power only. Generator fuel reserve: 8 hours total.",
                    "sectors_offline": [1, 2, 3, 4, 5, 6],
                    "fuel_hours": 8,
                },
                tags=["blackout", "cascade-trigger"],
            ),
            ScenarioEvent(
                delay=10,
                event_type="INFRASTRUCTURE_STATUS",
                domain="MEDICAL",
                severity="HIGH",
                payload={
                    "message": "3 hospitals on generator power. Combined fuel: 7 hours. "
                               "ICU wards: 89 patients on life support.",
                    "hospitals": 3,
                    "icu_patients": 89,
                    "fuel_hours": 7,
                },
                tags=["hospital-power"],
            ),
            ScenarioEvent(
                delay=20,
                event_type="WATER_PUMP_FAILURE",
                domain="LOGISTICS",
                severity="HIGH",
                payload={
                    "message": "Water treatment plant pumps offline. Potable water reserves: 36 hours.",
                    "water_reserve_hours": 36,
                },
                tags=["water", "blackout"],
            ),
            ScenarioEvent(
                delay=35,
                event_type="FUEL_REQUEST",
                domain="POWER",
                severity="CRITICAL",
                payload={
                    "message": "Hospital generator fuel critically low. Requesting emergency fuel "
                               "delivery within 4 hours or ICU patients at risk.",
                    "urgency_hours": 4,
                },
                tags=["fuel-emergency"],
            ),
        ],
    },

    "displacement": {
        "name": "Mass Displacement",
        "description": "50,000 displaced civilians arriving. Shelter, food, medical — MACS coordinates intake.",
        "events": [
            ScenarioEvent(
                delay=0,
                event_type="CRISIS_ALERT",
                domain="EVACUATION",
                severity="CRITICAL",
                payload={
                    "message": "Convoy of ~50,000 displaced civilians approaching from eastern corridor. "
                               "ETA: 3 hours. Current shelter capacity: 18,000.",
                    "civilians": 50000,
                    "eta_hours": 3,
                    "shelter_capacity": 18000,
                },
                tags=["displacement", "cascade-trigger"],
            ),
            ScenarioEvent(
                delay=12,
                event_type="MEDICAL_SCREENING_REQUIRED",
                domain="MEDICAL",
                severity="HIGH",
                payload={
                    "message": "Reports of cholera outbreak at source camp. "
                               "Medical screening and quarantine protocols required at intake.",
                    "disease": "cholera",
                    "quarantine_required": True,
                },
                tags=["disease", "displacement"],
            ),
            ScenarioEvent(
                delay=25,
                event_type="SUPPLY_SHORTAGE",
                domain="LOGISTICS",
                severity="HIGH",
                payload={
                    "message": "Food supplies sufficient for 20,000 people for 5 days. "
                               "Water: 15,000 people for 3 days. Emergency resupply needed.",
                    "food_capacity": 20000,
                    "water_capacity": 15000,
                },
                tags=["food-water", "displacement"],
            ),
        ],
    },
}


class ScenarioRunner:
    def __init__(self, scenario_key: str):
        self.scenario = SCENARIOS[scenario_key]
        self._thread: threading.Thread = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="scenario-runner")
        self._thread.start()
        bulletin.post(
            source="SYSTEM",
            event_type="SCENARIO_START",
            domain="SYSTEM",
            severity="INFO",
            payload={
                "scenario": self.scenario["name"],
                "description": self.scenario["description"],
            },
            tags=["scenario"],
        )

    def _run(self):
        start_time = time.time()
        events = sorted(self.scenario["events"], key=lambda e: e.delay)

        for scenario_event in events:
            if not self._running:
                break
            elapsed = time.time() - start_time
            wait = scenario_event.delay - elapsed
            if wait > 0:
                time.sleep(wait)
            if not self._running:
                break
            bulletin.post(
                source="SYSTEM",
                event_type=scenario_event.event_type,
                domain=scenario_event.domain,
                severity=scenario_event.severity,
                payload=scenario_event.payload,
                tags=(scenario_event.tags or []),
            )

    def stop(self):
        self._running = False

    @staticmethod
    def list_scenarios() -> list[dict]:
        return [
            {"key": k, "name": v["name"], "description": v["description"]}
            for k, v in SCENARIOS.items()
        ]
