"""
World State — shared operational picture derived from bulletin events.

Purpose:
- Keep a mutable crisis state that all agents implicitly share through the bulletin.
- Convert raw events (SYSTEM, FIELD_REPORT, ACTION_TAKEN) into state deltas.
- Broadcast state snapshots as WORLD_STATE_UPDATE events for observability/demo.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from shared_state import bulletin, Event


@dataclass
class WorldState:
    hospital_capacity_pct: int = 45
    hospital_casualties: int = 0
    surgical_backlog: int = 0
    blood_units_oneg: int = 24

    grid_sectors_offline: int = 0
    generator_fuel_hours: float = 18.0
    comms_coverage_pct: int = 100

    route_alpha_blocked: bool = False
    medical_convoy_delay_hours: float = 0.0
    shelter_capacity_pct: int = 40
    civilians_displaced: int = 0
    water_reserve_hours: int = 72

    scenario: str = "unknown"
    updated_at: float = 0.0


class WorldStateManager:
    def __init__(self, scenario_key: str = "cascade"):
        self._lock = threading.RLock()
        self.state = WorldState(scenario=scenario_key, updated_at=time.time())

    def bootstrap(self):
        """Emit initial state so dashboard/demo has a baseline."""
        self._emit("bootstrap")

    def observe(self, event: Event):
        """Observe bulletin events and apply state transitions."""
        if event.event_type in {
            "WORLD_STATE_INIT", "WORLD_STATE_UPDATE", "WORLD_STATE_SNAPSHOT"
        }:
            return

        changed = False
        with self._lock:
            changed |= self._apply_payload_fields(event)

            if event.source == "FIELD_REPORT" or event.event_type == "CITIZEN_INTEL":
                changed |= self._apply_field_report(event)

            if event.event_type == "ACTION_TAKEN":
                changed |= self._apply_action_effects(event)

            self.state.updated_at = time.time()

        if changed:
            self._emit(f"from {event.id} {event.event_type}")

    def snapshot(self) -> dict:
        with self._lock:
            s = self.state
            return {
                "scenario": s.scenario,
                "updated_at": s.updated_at,
                "medical": {
                    "hospital_capacity_pct": s.hospital_capacity_pct,
                    "hospital_casualties": s.hospital_casualties,
                    "surgical_backlog": s.surgical_backlog,
                    "blood_units_oneg": s.blood_units_oneg,
                },
                "power": {
                    "grid_sectors_offline": s.grid_sectors_offline,
                    "generator_fuel_hours": round(s.generator_fuel_hours, 1),
                },
                "comms": {
                    "coverage_pct": s.comms_coverage_pct,
                },
                "logistics": {
                    "route_alpha_blocked": s.route_alpha_blocked,
                    "medical_convoy_delay_hours": round(s.medical_convoy_delay_hours, 1),
                    "water_reserve_hours": s.water_reserve_hours,
                },
                "evacuation": {
                    "shelter_capacity_pct": s.shelter_capacity_pct,
                    "civilians_displaced": s.civilians_displaced,
                },
            }

    # ── Internals ───────────────────────────────────────────────────────────

    def _clamp(self):
        s = self.state
        s.hospital_capacity_pct = max(0, min(100, s.hospital_capacity_pct))
        s.comms_coverage_pct = max(0, min(100, s.comms_coverage_pct))
        s.shelter_capacity_pct = max(0, min(100, s.shelter_capacity_pct))
        s.grid_sectors_offline = max(0, min(6, s.grid_sectors_offline))
        s.generator_fuel_hours = max(0.0, min(72.0, s.generator_fuel_hours))
        s.medical_convoy_delay_hours = max(0.0, min(12.0, s.medical_convoy_delay_hours))
        s.blood_units_oneg = max(0, min(200, s.blood_units_oneg))
        s.hospital_casualties = max(0, min(10000, s.hospital_casualties))
        s.surgical_backlog = max(0, min(500, s.surgical_backlog))
        s.civilians_displaced = max(0, min(200000, s.civilians_displaced))
        s.water_reserve_hours = max(0, min(240, s.water_reserve_hours))

    def _apply_payload_fields(self, event: Event) -> bool:
        s = self.state
        p = event.payload or {}
        before = self.snapshot()

        if "hospital_capacity_pct" in p:
            s.hospital_capacity_pct = int(p["hospital_capacity_pct"])
        if "casualties" in p:
            s.hospital_casualties += int(p["casualties"])
        if "surgical_backlog" in p:
            s.surgical_backlog = int(p["surgical_backlog"])
        if "units_remaining" in p:
            s.blood_units_oneg = int(p["units_remaining"])

        if "sectors_offline" in p:
            sectors = p["sectors_offline"]
            if isinstance(sectors, list):
                s.grid_sectors_offline = len(sectors)
            elif isinstance(sectors, int):
                s.grid_sectors_offline = sectors
        if "generator_fuel_hours" in p:
            s.generator_fuel_hours = float(p["generator_fuel_hours"])
        if "fuel_hours" in p:
            s.generator_fuel_hours = float(p["fuel_hours"])
        if "coverage_pct" in p:
            s.comms_coverage_pct = int(p["coverage_pct"])

        if "shelter_capacity_pct" in p:
            s.shelter_capacity_pct = int(p["shelter_capacity_pct"])
        if "civilians" in p:
            s.civilians_displaced = max(s.civilians_displaced, int(p["civilians"]))
        if "water_reserve_hours" in p:
            s.water_reserve_hours = int(p["water_reserve_hours"])

        if p.get("route") == "Alpha" and event.event_type == "ROUTE_COMPROMISED":
            s.route_alpha_blocked = True
            s.medical_convoy_delay_hours = max(s.medical_convoy_delay_hours, 2.0)

        # External feed impacts
        if event.event_type == "SEISMIC_ACTIVITY":
            mag = float(p.get("magnitude") or 0.0)
            if mag >= 4.0:
                s.grid_sectors_offline += 1
                s.route_alpha_blocked = True
                s.medical_convoy_delay_hours += 0.5
                s.hospital_casualties += int(max(1, (mag - 3.5) * 3))

        if event.event_type == "WEATHER_ALERT":
            precip = float(p.get("precipitation_mm") or 0.0)
            gust = float(p.get("wind_gust_kmh") or 0.0)
            if precip >= 2.0 or gust >= 35.0:
                s.medical_convoy_delay_hours += 0.4
                s.comms_coverage_pct -= 2
            if precip >= 6.0 or gust >= 50.0:
                s.medical_convoy_delay_hours += 0.6
                s.comms_coverage_pct -= 4
                s.shelter_capacity_pct += 1

        self._clamp()
        return before != self.snapshot()

    def _apply_field_report(self, event: Event) -> bool:
        s = self.state
        before = self.snapshot()
        text = " ".join([
            str(event.payload.get("message", "")),
            str(event.payload.get("original", "")),
            str(event.payload.get("location", "")),
        ]).lower()

        if any(k in text for k in ("blocked", "bridge", "route", "convoy")):
            s.route_alpha_blocked = True
            s.medical_convoy_delay_hours += 0.5
        if any(k in text for k in ("blackout", "no power", "generator")):
            s.grid_sectors_offline += 1
            s.generator_fuel_hours -= 0.5
        if any(k in text for k in ("wounded", "casualty", "injury", "bleeding")):
            s.hospital_casualties += 6
            s.surgical_backlog += 2
        if any(k in text for k in ("evacuate", "trapped", "stranded", "shelter")):
            s.civilians_displaced += 120
            s.shelter_capacity_pct += 2

        self._clamp()
        return before != self.snapshot()

    def _apply_action_effects(self, event: Event) -> bool:
        s = self.state
        before = self.snapshot()
        domain = (event.domain or "").upper()
        msg = str((event.payload or {}).get("message", "")).lower()

        if domain == "POWER":
            s.grid_sectors_offline -= 1
            if "fuel" in msg or "generator" in msg:
                s.generator_fuel_hours += 1.5
        elif domain == "COMMS":
            s.comms_coverage_pct += 8
        elif domain == "LOGISTICS":
            if "reroute" in msg or "convoy" in msg:
                s.medical_convoy_delay_hours -= 0.7
            if "blood" in msg:
                s.blood_units_oneg += 4
            if "water" in msg:
                s.water_reserve_hours += 6
        elif domain == "MEDICAL":
            s.hospital_capacity_pct -= 3
            s.surgical_backlog -= 2
            s.hospital_casualties = max(0, s.hospital_casualties - 1)
        elif domain == "EVACUATION":
            s.shelter_capacity_pct -= 4
            s.civilians_displaced = max(0, s.civilians_displaced - 150)

        self._clamp()
        return before != self.snapshot()

    def _emit(self, reason: str):
        bulletin.post(
            source="SYSTEM",
            event_type="WORLD_STATE_UPDATE",
            domain="SYSTEM",
            severity="INFO",
            payload={
                "message": f"World state updated ({reason})",
                "state": self.snapshot(),
            },
            tags=["world-state"],
        )


def start_world_state(scenario_key: str = "cascade") -> WorldStateManager:
    mgr = WorldStateManager(scenario_key=scenario_key)
    bulletin.subscribe(mgr.observe)
    mgr.bootstrap()
    return mgr
