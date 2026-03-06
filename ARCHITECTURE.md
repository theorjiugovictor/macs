# MACS — Architecture Document

*Multi-Agent Crisis Response System*
*Epiminds Hackathon 2026 — Swarm Intelligence Track*

---

## One-Line Summary

**Five autonomous AI agents coordinate humanitarian crisis response through stigmergy — no hierarchy, no coordinator, no single point of failure — validated by a three-layer intelligence pipeline that cross-references sensors, institutions, and citizens.**

---

## The Problem

In a crisis zone (earthquake, conflict, infrastructure collapse), traditional command-and-control fails:

- **Single points of failure** — knock out the coordinator, the system dies
- **Communication bottlenecks** — every decision routes through a hierarchy
- **Information overload** — thousands of reports, no way to separate signal from noise
- **Slow adaptation** — rigid chains of command can't respond to a rapidly changing situation

## The MACS Solution

A **flat, decentralized swarm** of AI agents that:

1. **Never talk to each other** — they coordinate through a shared environment (stigmergy)
2. **Self-organize** — complex behavior emerges from simple local rules
3. **Survive failure** — kill any agent, the swarm continues
4. **Validate everything** — a three-layer pipeline cross-references sensor, institutional, and citizen data before acting

---

## Core Architecture: Stigmergy

**Stigmergy** (from Greek: *stigma* "mark" + *ergon* "work") is how ant colonies build complex structures without a foreman. Each ant reads environmental cues and acts locally. The environment itself becomes the coordination mechanism.

MACS applies this principle: agents never call each other's functions, never send messages to each other. They read and write to a **shared append-only bulletin board** — an event log. Coordination emerges from the traces they leave.

```
                          ┌──────────────────────────────────────────┐
                          │          BULLETIN BOARD                  │
                          │      (append-only event log)             │
                          │                                          │
     SENSOR LAYER ──────▶ │  EVT-001 [SENSOR] Seismic: 4.2 mag      │
         API LAYER ─────▶ │  EVT-002 [API]    EONET: flood warning   │
       CROWD LAYER ─────▶ │  EVT-003 [CROWD]  "Hospital overwhelmed" │
                          │  EVT-004 [AGENT]  MEDIC: field triage    │
                          │  EVT-005 [AGENT]  POWER: generator deploy│
                          │  EVT-006 [AGENT]  LOGISTICS: convoy rrt  │
                          │            ...                           │
                          └───────────────┬──────────────────────────┘
                                          │
                        ┌─────────────────┼─────────────────┐
                        │                 │                 │
                   WebSocket          GET APIs          Dashboard
                   (real-time)     (/events, etc.)      (Lovable UI)
```

### Why This Is Powerful (What to Say to Judges)

| Property | Traditional C2 | MACS (Stigmergic) |
|----------|----------------|-------------------|
| Coordination | Explicit message passing | Implicit via shared environment |
| Failure mode | Cascading (coordinator dies → all die) | Graceful degradation (any agent can die) |
| Scaling | Bottleneck at coordinator | Linear (add agents, same board) |
| Adaptation speed | Minutes (human approval chain) | Seconds (autonomous perception-action) |

> **Presenter note**: "Ants don't have project managers. They build colonies through stigmergy — leaving traces in the environment that other ants respond to. MACS works the same way. No agent knows any other agent exists. They just read the shared board and make domain-expert decisions."

---

## The Five MACs

Every MAC runs an identical loop: **PERCEIVE → REASON → ACT**

1. **PERCEIVE**: Read new events from the bulletin board since last tick
2. **REASON**: Gemini 3.1 Flash analyzes the situation — should I act? What's changed?
3. **ACT**: Post decision back to the bulletin board

Same codebase. Different system prompt = different domain expert.

| MAC | Domain | Watches For | Acts On |
|-----|--------|------------|---------|
| **MEDIC** | MEDICAL | Hospital capacity, casualties, blood supply, disease signals | Activate field triage, reroute patients, manage blood supply |
| **LOGISTICS** | LOGISTICS | Convoy routes, supply levels, fuel reserves | Reroute convoys, reprioritize supplies, establish distribution |
| **POWER** | POWER | Grid sectors, generator fuel, critical infrastructure | Deploy generators, rolling blackouts, fuel management |
| **COMMS** | COMMS | Relay nodes, coverage gaps, distress signals | Mesh backup, external coordination, civilian broadcast |
| **EVAC** | EVACUATION | Routes, shelter capacity, civilian zones | Open shelters, reroute evacuees, civilian transport |

### Cross-Domain Compensation (Resilience)

Each MAC's prompt includes explicit instructions for **what to do when another MAC goes offline**. For example, if MEDIC goes down:

- LOGISTICS prioritizes medical supply convoys
- COMMS broadcasts medical self-aid guidance
- EVAC equips buses with first-aid kits
- POWER ensures uninterrupted hospital power

> **Presenter note**: "This is not scripted. The agents decide in real-time using LLM reasoning, based on what they observe on the bulletin board — specifically, the *absence* of MEDIC posts. They detect the gap and fill it from their own domain."

---

## The Three-Layer Validation Pipeline (The Moat)

This is what makes MACS more than a chatbot swarm. **No agent acts on unvalidated single-source intelligence.**

```
LAYER 1: SENSOR (Ground Truth)         weight: 0.45
├── USGS earthquake feed (seismic)
├── Open-Meteo weather (temperature, wind, precipitation)
└── Raw environmental telemetry

LAYER 2: API (Institutional Truth)      weight: 0.35
├── NASA EONET (volcanic, wildfire, flood, storm events)
├── Government alerts
└── Institutional situation reports

LAYER 3: CROWD (Human Truth)            weight: 0.15
├── Citizen field reports (with photo evidence)
├── Cross-validation by other citizens ("I can confirm this")
└── Geolocation + Google Places verified locations
```

### How Corroboration Works (Technical Detail)

When a citizen submits a field report (CROWD layer), the **Validator** runs a cross-referencing engine:

1. **Domain classification** — What domain does this report belong to? (MEDICAL, POWER, etc.)
2. **Corroboration scan** — Search last 100 bulletin events within a 10-minute window for matching SENSOR/API events
3. **Layer weighting** — SENSOR evidence (0.45) counts 3× more than another citizen's report (0.15)
4. **Multi-layer bonus** — If BOTH sensor AND API data corroborate, +15% confidence boost
5. **Confidence scoring** — Final score 0.0–1.0 determines how agents weight this intel
6. **Gemini validation** — In live mode, the LLM itself cross-references against the full bulletin context

**Example — validated report**:
A citizen reports *"hospital overwhelmed, people dying"* (CROWD layer).
The validator finds:
- USGS: magnitude 4.2 earthquake 15 minutes ago → SENSOR match → +0.45
- EONET: building collapse event in the area → API match → +0.35
- Multi-layer bonus: +0.15
- **Final corroboration score: 0.95** — agents treat this as near-certain

**Example — rejected report**:
A troll submits *"aliens attacking city center"* (CROWD layer).
- No corroborating SENSOR events
- No corroborating API events
- **Final corroboration score: 0.0** — agents deprioritize entirely

> **Presenter note**: "This is the product moat. Anyone can build a chatbot swarm. Cross-referencing three independent data layers to validate intelligence in real-time — that's what makes MACS trustworthy enough for actual crisis response. It's the same principle intelligence agencies use: single-source intel is a rumor. Multi-source corroborated intel is actionable."

### Agent Intelligence Layer Awareness

Agents are prompt-engineered to weight intelligence by source layer:

> *"SENSOR events = GROUND TRUTH. Act with highest confidence. API events = INSTITUTIONAL TRUTH. High confidence, may lag reality. CROWD events = HUMAN TRUTH. Valuable but requires corroboration. If uncorroborated, acknowledge but note 'awaiting sensor/API confirmation.'"*

This means agents don't just blindly react to everything. They reason about information quality.

---

## Shared State: The Bulletin Board

```python
@dataclass
class Event:
    id: str              # EVT-00001, EVT-00002, ...
    timestamp: float     # Unix epoch
    source: str          # "MEDIC", "SYSTEM", "EXT_FEED", "FIELD_REPORT"
    event_type: str      # CRISIS_ALERT, ACTION_TAKEN, WEATHER_STATUS, etc.
    domain: str          # MEDICAL, LOGISTICS, POWER, COMMS, EVACUATION
    severity: str        # CRITICAL, HIGH, MEDIUM, LOW, INFO
    source_layer: str    # SENSOR | API | CROWD | AGENT | SYSTEM
    payload: dict        # {message: "...", ...}
    tags: list           # ["corroborated", "photo_evidence", ...]
```

Key properties:

- **Append-only** — events are never deleted or modified (immutable audit trail)
- **Thread-safe** — concurrent reads and writes with RLock
- **WebSocket broadcast** — every new event pushes to all connected dashboards in real-time
- **Layer-tagged** — every event carries its `source_layer`, so agents know how much to trust it
- **Redis Streams ready** — the BulletinBoard API is designed to swap for Redis Streams with zero code changes

> **Presenter note**: "The bulletin board is intentionally dumb. It has no routing logic, no priority queue, no awareness of which agents exist. It's a log. That's the point — all the intelligence is in the agents, not the infrastructure. This is what makes the system flat."

---

## Real-World Data Integration

MACS doesn't just run on simulated crises. It pulls **live external data**:

| Source | Layer | Data | Update Interval |
|--------|-------|------|----------------|
| USGS Earthquake API | SENSOR | Seismic events (magnitude, depth, location) | 120s |
| Open-Meteo API | SENSOR | Temperature, wind speed, precipitation, weather alerts | 120s |
| NASA EONET | API | Volcanic eruptions, wildfires, floods, severe storms | 120s |

These are tagged with their source layer and injected into the bulletin board. When a citizen reports something that aligns with sensor data, the corroboration engine automatically links them.

Currently scoped to **Stockholm, Sweden** for the hackathon demo (configurable via `--area` flag).

---

## Citizen Intake System

A mobile-first web form accessible via QR code or direct URL.

### Features

- **Photo evidence** — camera capture or gallery upload, stored as base64, linked to event
- **Google Places Autocomplete** — type an address, get verified lat/lng coordinates
- **Reverse geocoding** — tap the map, get a human-readable address
- **Interactive mini map** — visual location confirmation before submission
- **Cross-validation** — "I CAN CONFIRM THIS" button on live feed events (double-vote prevention)
- **Push notifications** — AirTag-style alerts when nearby crisis events post
- **Source layer badges** — each event in the feed shows its layer (SENSOR/API/CROWD/AGENT) and corroboration score

### Report Flow

```
Citizen opens form → types report + uploads photo + pins location
        │
        ▼
POST /report → Verifier (Gemini + corroboration engine)
        │
        ├── SPAM? → Reject (confidence < threshold)
        │
        ├── CREDIBLE + CORROBORATED → Post to bulletin as CROWD (high confidence)
        │   ↳ Agents see corroborated citizen report, act with high priority
        │
        └── CREDIBLE + UNCORROBORATED → Post to bulletin as CROWD (lower confidence)
            ↳ Agents acknowledge but note "awaiting sensor/API confirmation"
```

---

## Emergence: The Cascade Scenario

The "Hospital Cascade" injects 7 SYSTEM events over 75 seconds. **No agent is told what to do.** The swarm self-organizes:

```
T+00s  💥 SYSTEM: Hospital hit → 92% capacity, 47 casualties
       ↳ MEDIC: Activates field triage at B-7
       ↳ Other MACs observe but hold — not their domain yet

T+08s  ⚡ SYSTEM: Grid sectors 3+4 offline, generator fuel: 5hrs
       ↳ POWER: Monitors fuel, requests LOGISTICS priority
       ↳ MEDIC: Reads POWER event → flags fuel urgency for hospital backup

T+18s  🚧 SYSTEM: Route Alpha blocked, medical convoy delayed 2hrs
       ↳ LOGISTICS: Reroutes convoy via northern corridor
       ↳ MEDIC: Reads LOGISTICS event → adjusts patient intake expectations

T+28s  📡 SYSTEM: Comms relay B-5 destroyed, 40% coverage lost
       ↳ COMMS: Activates mesh backup, restores to 60%
       ↳ EVAC: Reads COMMS event → adjusts civilian broadcast plan

T+40s  🏃 SYSTEM: Zones 3+4 unsafe, 2400 civilians need evacuation
       ↳ EVAC: Opens university shelter, deploys bus convoy
       ↳ LOGISTICS: Reads EVAC event → pre-positions aid at shelter

T+55s  🩸 SYSTEM: Blood supply critical (2 units O-neg)
       ↳ LOGISTICS: Blood supply reprioritized to medical convoy
       ↳ MEDIC: Reads LOGISTICS event → confirms field triage can absorb

T+75s  🏥 SYSTEM: WHO field team available 18km north
       ↳ COMMS: Establishes secure channel, broadcasts coordination
       ↳ LOGISTICS: Coordinates convoy escort for WHO team
```

**Result: Six coherent, cross-domain responses. Zero instructions between agents.**

The agents cite each other's event IDs, reference each other by name, and build on each other's work — all through reading the shared environment. This is textbook emergence.

---

## Resilience Demonstration

### Kill an Agent

```bash
curl -X POST https://macs-demo.duckdns.org/control \
  -H 'Content-Type: application/json' \
  -d '{"action":"kill","agent":"MEDIC"}'
```

What happens:
1. MEDIC stops posting to the bulletin board
2. Other agents **detect the gap** — they see no MEDICAL-domain posts
3. Each agent **compensates from their own domain** using LLM reasoning
4. LOGISTICS starts prioritizing medical supply convoys
5. COMMS broadcasts medical self-aid guidance
6. The swarm continues functioning — degraded but alive

### Revive an Agent

```bash
curl -X POST https://macs-demo.duckdns.org/control \
  -d '{"action":"revive","agent":"MEDIC"}'
```

MEDIC reconnects, reads the full bulletin history, catches up autonomously. No manual re-sync needed.

> **Presenter note**: "This proves there's no single point of failure. In a real crisis, network partitions, hardware failures, and targeted attacks happen constantly. MACS survives them all because no agent depends on any other agent's existence."

---

## Flatness Proof (No Hidden Hierarchy)

Five hard proofs:

1. **Code proof**: `agent.py` — no MAC imports any other MAC module. Each is a standalone loop.
2. **State proof**: `shared_state.py` — the bulletin board has no routing logic, no priority queue. It's a dumb log.
3. **Prompt proof**: `personas.py` — every MAC's prompt states *"There is NO coordinator, NO hierarchy, NO leader."*
4. **Failure proof**: Kill any single MAC — MACS continues. Kill any *three* — the remaining two still function.
5. **Symmetry proof**: No agent holds a lock that blocks others. All agents have equal read/write access.

> **Presenter note**: "If we had a hidden coordinator, killing it would collapse the system. Try killing any agent — the swarm doesn't flinch. That's the proof."

---

## Technical Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Agent runtime | Python 3.12 + threads | Simple, portable, easy to kill/revive per agent |
| LLM backbone | Gemini 3.1 Flash Lite (Google) | Fast reasoning for time-critical crisis decisions |
| Shared state | In-memory BulletinBoard | Append-only, thread-safe, WebSocket-enabled |
| Validation | Three-layer corroboration engine | Cross-references SENSOR/API/CROWD automatically |
| Real-time feed | WebSockets | Push to dashboard without polling |
| Citizen intake | Mobile-first HTML + Google Maps APIs | Photo upload, Places Autocomplete, reverse geocoding |
| External data | USGS, Open-Meteo, NASA EONET | Live sensor + institutional feeds |
| HTTPS/TLS | Caddy v2 + Let's Encrypt | Auto-TLS for citizen and dashboard connections |
| Hosting | GCP Compute Engine (us-central1) | Single VM, systemd service |
| Dashboard | Lovable (teammate) | Real-time ops center visualization |

---

## API Surface

**Base URL**: `https://macs-demo.duckdns.org`
**WebSocket**: `wss://macs-demo.duckdns.org/ws`

### GET Endpoints

| Endpoint | Returns |
|----------|---------|
| `/status` | Event counts by domain and severity |
| `/events` | Full event list (newest first) — all layers |
| `/agents` | All 5 agents: status, domain, last action time, alive/dead |
| `/world-state` | Live scenario state: medical, power, comms, logistics, evacuation metrics |
| `/layers` | Three-layer breakdown: event counts per source layer |
| `/reports` | Citizen field reports only (CROWD layer) |
| `/photo/<id>` | Photo evidence by event ID (base64 JPEG) |

### POST Endpoints

| Endpoint | Body | Description |
|----------|------|-------------|
| `/report` | multipart/form-data | Submit citizen field report (with optional photo) |
| `/validate` | `{"event_id", "reporter_id"}` | Cross-validate (upvote) an existing event |
| `/control` | `{"action": "kill/revive/inject_event/list"}` | System control API |

### WebSocket Stream

Streams JSON messages in real-time:

```json
{
  "type": "bulletin",
  "events": [{
    "id": "EVT-00142",
    "timestamp": 1772792005.48,
    "source": "MEDIC",
    "event_type": "ACTION_TAKEN",
    "domain": "MEDICAL",
    "severity": "HIGH",
    "source_layer": "AGENT",
    "payload": {"message": "Field triage activated at B-7..."},
    "tags": []
  }]
}
```

---

## Scoring Rubric Alignment

| Criterion (Weight) | How MACS Scores | Evidence |
|---------------------|----------------|----------|
| **Emergence Quality (30%)** | Agents self-organize complex cross-domain responses from simple PERCEIVE→REASON→ACT loops. No pre-programmed coordination. | Cascade scenario: 7 injected events → 6+ coherent cross-domain responses with event ID citations |
| **Flatness (25%)** | Zero hierarchy. Append-only log. No routing. No coordinator. Five hard proofs in code. | Kill any agent → system continues. No inter-agent imports. Board has no routing logic. |
| **Resilience (20%)** | Kill/revive any agent live. Cross-domain compensation via real-time LLM reasoning. | Kill MEDIC → remaining 4 absorb medical functions. Revive → MEDIC catches up autonomously. |
| **Collaboration Depth (15%)** | Agents cite event IDs, reference by name, build on each other's actions, detect gaps. Three-layer validation adds SENSOR/API/CROWD cross-referencing. | Agent posts show "[EVT-00042]" references. Corroboration engine produces cross-layer confidence scores. |
| **Demo Impact (10%)** | Live HTTPS dashboard, citizen QR code intake with photo evidence, real sensor data, Google Maps. | Judges scan QR → submit report → watch it flow through validation → agents react in real-time on dashboard |

---

## File Structure

```
macs/
├── backend/
│   ├── main.py              # Entry point — wires bulletin, verifier, agents, scenarios
│   ├── shared_state.py      # BulletinBoard: append-only event log + WebSocket broadcast
│   ├── agent.py             # MAC base class: PERCEIVE → REASON → ACT loop
│   ├── personas.py          # 5 MAC personas with stigmergic protocol + layer awareness
│   ├── verifier.py          # Three-layer Validator + corroboration engine (THE MOAT)
│   ├── intake_server.py     # Citizen intake: form + API endpoints + photo + maps
│   ├── scenarios.py         # Crisis timelines (cascade, blackout, displacement)
│   ├── world_state.py       # WorldStateManager: scenario metrics + state broadcast
│   ├── external_feeds.py    # USGS, Open-Meteo, NASA EONET data pull
│   ├── ws_server.py         # WebSocket server for real-time dashboard feed
│   └── requirements.txt
├── frontend/                # (Legacy React dashboard — replaced by Lovable UI)
├── docker/
│   ├── Dockerfile.agent
│   └── Dockerfile.dashboard
├── docker-compose.yml
├── ARCHITECTURE.md          # ← This file
├── README.md                # Quickstart + context
└── PITCH.md                 # Demo scenario script for presentation
```
