"""
Shared State — Stigmergic Bulletin Board

Agents never talk to each other directly. They read and write to this
append-only event log. Like ants leaving pheromone trails.

Redis Streams drop-in: swap BulletinBoard for RedisBulletinBoard (same API).
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional
import json

import asyncio
import websockets


@dataclass
class Event:
    id: str
    timestamp: float
    source: str          # agent id or "SYSTEM"
    event_type: str      # e.g. CRISIS_ALERT, ACTION_TAKEN, STATE_UPDATE
    domain: str          # e.g. MEDICAL, LOGISTICS, POWER, COMMS, EVACUATION
    severity: str        # CRITICAL, HIGH, MEDIUM, LOW, INFO
    payload: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)


class BulletinBoard:
    """
    In-memory append-only event log with pub/sub.
    Thread-safe. WebSocket broadcast for dashboard.
    Designed to be swapped for Redis Streams with zero API changes.
    """

    def __init__(self):
        self._events: list[Event] = []
        self._lock = threading.RLock()
        self._subscribers: list = []   # callbacks(event)
        self._ws_clients: set = set()
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._counter = 0

    # ── Core API ────────────────────────────────────────────────────────────

    def post(self, source: str, event_type: str, domain: str,
             severity: str, payload: dict, tags: list = None) -> Event:
        with self._lock:
            self._counter += 1
            event = Event(
                id=f"EVT-{self._counter:05d}",
                timestamp=time.time(),
                source=source,
                event_type=event_type,
                domain=domain,
                severity=severity,
                payload=payload,
                tags=tags or [],
            )
            self._events.append(event)

        self._notify(event)
        return event

    def read_all(self) -> list[Event]:
        with self._lock:
            return list(self._events)

    def read_since(self, after_id: Optional[str] = None) -> list[Event]:
        """Return events after a given event id (exclusive)."""
        with self._lock:
            if after_id is None:
                return list(self._events)
            for i, e in enumerate(self._events):
                if e.id == after_id:
                    return list(self._events[i + 1:])
            return list(self._events)

    def read_domain(self, domain: str) -> list[Event]:
        with self._lock:
            return [e for e in self._events if e.domain == domain]

    def read_by_type(self, event_type: str) -> list[Event]:
        with self._lock:
            return [e for e in self._events if e.event_type == event_type]

    def snapshot(self, max_events: int = 50) -> list[dict]:
        """Return recent events as dicts (for LLM context injection)."""
        with self._lock:
            recent = self._events[-max_events:]
            return [asdict(e) for e in recent]

    def stats(self) -> dict:
        with self._lock:
            domains = {}
            severities = {}
            for e in self._events:
                domains[e.domain] = domains.get(e.domain, 0) + 1
                severities[e.severity] = severities.get(e.severity, 0) + 1
            return {
                "total_events": len(self._events),
                "by_domain": domains,
                "by_severity": severities,
            }

    # ── Subscription / broadcast ─────────────────────────────────────────────

    def subscribe(self, callback):
        """Register a callback(event) fired on every new post."""
        self._subscribers.append(callback)

    def _notify(self, event: Event):
        for cb in self._subscribers:
            try:
                cb(event)
            except Exception:
                pass
        self._broadcast_ws(event)

    # ── WebSocket broadcast (for React dashboard) ────────────────────────────

    def set_ws_loop(self, loop: asyncio.AbstractEventLoop):
        self._ws_loop = loop

    def register_ws_client(self, ws):
        self._ws_clients.add(ws)

    def unregister_ws_client(self, ws):
        self._ws_clients.discard(ws)

    def _broadcast_ws(self, event: Event):
        if not self._ws_clients or self._ws_loop is None:
            return
        msg = json.dumps(asdict(event))
        for ws in list(self._ws_clients):
            try:
                asyncio.run_coroutine_threadsafe(ws.send(msg), self._ws_loop)
            except Exception:
                self._ws_clients.discard(ws)


# ── Singleton ────────────────────────────────────────────────────────────────

bulletin = BulletinBoard()
