# MACS — Architecture Document
*Multi-Agent Crisis Response System*
*Epiminds Hackathon 2026 — Swarm Intelligence Track*

---

## Mission

A **non-hierarchical swarm of autonomous AI agents (MACs)** that exhibits collective intelligence in humanitarian crisis response during active conflict. No coordinators. No single points of failure. Just emergence.

---

## Core Architecture: Stigmergy

Inspired by ant colonies. MACs never communicate directly. They interact only through a **shared environment** — an append-only bulletin board (event log). This is stigmergy: coordination through environmental traces.

```
                    ┌─────────────────────────────┐
                    │      BULLETIN BOARD          │
                    │   (append-only event log)    │
                    │                              │
     MEDIC ──read──▶│  EVT-001 CRISIS_ALERT        │
     MEDIC ──write─▶│  EVT-002 ACTION_TAKEN (MEDIC)│
  LOGISTICS ─read──▶│  EVT-003 ACTION_TAKEN (LOG)  │
     POWER ──read──▶│  EVT-004 INFRASTRUCTURE_FAIL │
      EVAC ──read──▶│  EVT-005 ACTION_TAKEN (EVAC) │
                    │            ...               │
                    └─────────────────────────────┘
                               ▲
                         WebSocket feed
                               │
                    ┌─────────────────────┐
                    │  React Dashboard    │
                    │  (live feed + viz)  │
                    └─────────────────────┘
```

**No MAC ever calls another MAC's function. No MAC sends messages to another MAC.**

---

## MAC Design

Every MAC runs the same loop:

```
PERCEIVE → REASON → ACT
```

1. **PERCEIVE**: Read new events from the bulletin board since last tick
2. **REASON**: LLM (Gemini 3.1 Flash) analyzes the situation — should I act?
3. **ACT**: Post decision back to the bulletin board

Same codebase. Different system prompt = different domain expert.

### The Five MACs

| MAC | Domain | Monitors | Typical Action |
|-----|--------|----------|----------------|
| MEDIC | MEDICAL | Hospital capacity, casualties, blood supply | Activate field triage, reroute patients |
| LOGISTICS | LOGISTICS | Convoy routes, supply levels, fuel | Reroute convoys, reprioritize supplies |
| POWER | POWER | Grid sectors, generator fuel | Deploy generators, trigger rolling blackouts |
| COMMS | COMMS | Relay nodes, coverage, distress signals | Activate mesh backups, relay to external orgs |
| EVAC | EVACUATION | Routes, shelter capacity, civilian zones | Open overflow shelters, reroute evacuees |

---

## Shared State: The Bulletin Board

```python
# Post an event (any MAC or SYSTEM)
bulletin.post(source="MEDIC", event_type="ACTION_TAKEN",
              domain="MEDICAL", severity="HIGH",
              payload={"message": "Field triage activated at B-7"})

# Any MAC reads the board
events = bulletin.read_since(last_event_id)
```

- **Append-only**: events are never deleted or modified
- **Thread-safe**: concurrent reads and writes
- **WebSocket broadcast**: every new event is pushed to the React dashboard
- **Redis Streams ready**: swap `BulletinBoard` for `RedisBulletinBoard` (same API)

---

## Emergence: The Cascade Scenario

The "Hospital Cascade" scenario injects 7 SYSTEM events over 75 seconds. No MAC is told what to do. The cascade is the emergence.

```
T+00s  SYSTEM: Hospital hit → 92% capacity, 47 casualties
       ↳ MEDIC:    Activate field triage at B-7

T+08s  SYSTEM: Grid sectors 3+4 offline, generator fuel: 5hrs
       ↳ POWER:    Monitor fuel, request LOGISTICS priority
       ↳ MEDIC:    Reads POWER event → flags fuel urgency for hospital

T+18s  SYSTEM: Route Alpha blocked, medical convoy delayed 2hrs
       ↳ LOGISTICS: Reroute convoy via northern corridor

T+28s  SYSTEM: Comms relay B-5 destroyed, 40% coverage lost
       ↳ COMMS:    Activate mesh backup nodes, restore to 60%
       ↳ EVAC:     Reads COMMS event → adjusts civilian broadcast plan

T+40s  SYSTEM: Zones 3+4 unsafe, 2400 civilians need evacuation
       ↳ EVAC:     Open university shelter, deploy bus convoy

T+55s  SYSTEM: Blood supply critical (2 units O-neg)
       ↳ LOGISTICS: Blood supply reprioritized to medical convoy
       ↳ MEDIC:    Reads LOGISTICS event → confirms field triage can absorb

T+75s  SYSTEM: WHO field team available 18km north
       ↳ COMMS:    Establish secure channel, broadcast coordination
       ↳ LOGISTICS: Coordinate convoy escort for WHO team
```

**Six coherent, cross-domain responses. Zero instructions between MACs.**

---

## Resilience Demonstration

Kill any MAC mid-demo:

```bash
# Terminal (CLI mode)
> kill MEDIC

# Or Docker mode
docker compose stop macs-core
```

The remaining four MACs continue reading the same bulletin board. LOGISTICS and EVAC independently pick up medical-relevant events and respond. No data is lost. No coordination breaks. MACS degrades gracefully.

Revive:
```bash
> revive MEDIC
# MEDIC reconnects, reads full history, catches up autonomously
```

---

## Flatness Proof

**There is no coordinator.** Evidence:

1. `agent.py`: No MAC imports any other MAC module
2. `shared_state.py`: The bulletin board has no routing logic — it's a dumb log
3. `personas.py`: MAC prompts explicitly state "You have no commander"
4. Kill any single MAC: MACS continues functioning
5. No MAC holds a lock that blocks others

The only shared resource is the event log — and it's append-only.

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| MAC runtime | Python 3.12 + threads | Simple, portable, easy to kill/revive |
| LLM backbone | Gemini 3.1 Flash (Google) | Fast multimodal reasoning for crisis decisions |
| Shared state | In-memory BulletinBoard → Redis Streams | Append-only, observable, distributed-ready |
| Real-time feed | WebSockets (websockets library) | Push to dashboard without polling |
| Dashboard | React + Vite + Recharts | Fast iteration, live visualization |
| Demo isolation | Docker Compose | Container-level MAC isolation |

---

## Running Locally

```bash
# Backend (mock mode — no API key needed)
cd backend
pip install -r requirements.txt
python main.py

# Backend (live Gemini MACs)
GOOGLE_API_KEY=... GEMINI_MODEL=gemini-3.1-flash python main.py --live

# Dashboard
cd frontend
npm install && npm run dev
# Open http://localhost:3000

# Docker (full stack)
GOOGLE_API_KEY=... GEMINI_MODEL=gemini-3.1-flash docker compose up
```

---

## Submission Checklist

- [x] Working demo (mock mode + live mode)
- [x] GitHub repository with source code
- [x] 1-page architecture document (this file)
- [ ] Submit link
