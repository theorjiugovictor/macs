# ⬡ MACS — Multi-Agent Crisis Response System

> A non-hierarchical swarm of autonomous AI agents for humanitarian crisis response.
> No coordinators. No bottlenecks. No single point of failure. Just emergence.

**Epiminds Hackathon 2026** — Swarm Intelligence Track

📐 Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
🎤 Demo Script: [PITCH.md](PITCH.md)

---

## Live System

| Resource | URL |
|----------|-----|
| 🌐 Intake Form | https://macs-demo.duckdns.org |
| 📡 API Base | https://macs-demo.duckdns.org/status |
| 🔌 WebSocket | wss://macs-demo.duckdns.org/ws |
| ☁️ Hosting | GCP Compute Engine (us-central1-a) |
| 🔒 TLS | Let's Encrypt via Caddy (auto-renewing) |

---

## Quick Start

### Live mode (Gemini 3.1 Flash + real-world data)

```bash
cd backend
pip install -r requirements.txt
GOOGLE_API_KEY=... python main.py --live --ext-feeds --area stockholm --feed-interval 120
```

### Mock mode (no API key needed — keyword-based reasoning)

```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Dashboard (legacy React — now handled by Lovable teammate)

```bash
cd frontend && npm install && npm run dev
```

### Docker

```bash
GOOGLE_API_KEY=... GEMINI_MODEL=gemini-3.1-flash-lite-preview docker compose up
```

---

## What Is MACS?

**MACS** = Multi-Agent Crisis Response System

Five autonomous AI agents (**MACs**), each owning a crisis domain, coordinate through a shared append-only bulletin board. No agent talks to any other agent. They read the environment, reason independently, and post decisions back. Coordination is emergent — like an ant colony.

### The Five Agents

| Agent | Domain | What It Does |
|-------|--------|-------------|
| MEDIC | Medical | Triage, hospital capacity, blood supply, casualty routing |
| LOGISTICS | Supply Chain | Convoy routes, supply priorities, fuel, aid distribution |
| POWER | Infrastructure | Grid management, generators, rolling blackouts |
| COMMS | Communications | Mesh networks, relay nodes, external coordination |
| EVAC | Evacuation | Route safety, shelters, civilian transport |

### Three-Layer Validation Pipeline

Every piece of intelligence is tagged by source and cross-referenced:

| Layer | Source | Trust Level | Weight |
|-------|--------|------------|--------|
| **SENSOR** | USGS seismic, Open-Meteo weather | Ground truth | 0.45 |
| **API** | NASA EONET, govt alerts | Institutional truth | 0.35 |
| **CROWD** | Citizen field reports + photos | Human truth (needs corroboration) | 0.15 |

The **corroboration engine** cross-references CROWD reports against SENSOR + API events in a 10-minute sliding window. Multi-layer confirmation = confidence boost. No corroboration = agents treat it cautiously.

---

## API Reference

**Base**: `https://macs-demo.duckdns.org`

### GET

| Endpoint | Description |
|----------|-------------|
| `/status` | Event counts by domain and severity |
| `/events` | All events (newest first), all layers |
| `/agents` | Agent status: online/offline, last action, domain |
| `/world-state` | Scenario metrics: hospital %, grid sectors, convoy delays |
| `/layers` | Event counts per source layer (SENSOR/API/CROWD/AGENT/SYSTEM) |
| `/reports` | CROWD-layer citizen reports only |
| `/photo/<id>` | Photo evidence for a report (base64 JPEG) |

### POST

| Endpoint | Body | Description |
|----------|------|-------------|
| `/report` | multipart/form-data | Submit citizen field report (with photo + location) |
| `/validate` | `{"event_id", "reporter_id"}` | Cross-validate an existing event |
| `/control` | `{"action": "kill\|revive\|list\|inject_event"}` | System control |

### WebSocket

```javascript
const ws = new WebSocket("wss://macs-demo.duckdns.org/ws");
ws.onmessage = (msg) => {
  const data = JSON.parse(msg.data);
  // data.type === "bulletin"
  // data.events === [{id, timestamp, source, event_type, domain, severity, source_layer, payload, tags}]
};
```

---

## Control API

For live demos — kill/revive agents, inject events:

```bash
# Kill an agent (demonstrates resilience)
curl -X POST https://macs-demo.duckdns.org/control \
  -H 'Content-Type: application/json' \
  -d '{"action":"kill","agent":"MEDIC"}'

# Revive it (demonstrates recovery)
curl -X POST https://macs-demo.duckdns.org/control \
  -d '{"action":"revive","agent":"MEDIC"}'

# List agents
curl -X POST https://macs-demo.duckdns.org/control \
  -d '{"action":"list"}'

# Inject a crisis event
curl -X POST https://macs-demo.duckdns.org/control \
  -d '{"action":"inject_event","event_type":"CRISIS_ALERT","severity":"CRITICAL","message":"Chemical spill at zone 5"}'
```

Optional auth: set `MACS_CONTROL_TOKEN` env var and pass `"token":"..."` in JSON body.

---

## Scenarios

```bash
python main.py --scenario cascade      # Hospital cascade (default)
python main.py --scenario blackout     # City-wide power failure
python main.py --scenario displacement # Mass civilian displacement
python main.py --list-scenarios        # Show all available
```

---

## External Data Feeds

Live real-world data pulled every 120 seconds:

| Source | Type | Layer |
|--------|------|-------|
| USGS Earthquake API | Seismic activity (mag, depth, location) | SENSOR |
| Open-Meteo | Weather (temp, wind, precipitation, alerts) | SENSOR |
| NASA EONET | Hazards (volcanoes, wildfires, floods, storms) | API |

Scoped by `--area` flag: `stockholm`, `sweden`, `iran`, or custom coordinates.

---

## Project Structure

```
macs/
├── backend/
│   ├── main.py              # Entry — wires everything together
│   ├── shared_state.py      # Bulletin board: append-only log + WS broadcast
│   ├── agent.py             # MAC loop: perceive → reason → act
│   ├── personas.py          # 5 agent personas + stigmergic protocol
│   ├── verifier.py          # Three-layer validator + corroboration engine
│   ├── intake_server.py     # Citizen form + all API endpoints
│   ├── scenarios.py         # Crisis scenario timelines
│   ├── world_state.py       # Scenario metric tracking + emission
│   ├── external_feeds.py    # USGS / Open-Meteo / EONET integration
│   ├── ws_server.py         # WebSocket server
│   └── requirements.txt
├── frontend/                # Legacy React dashboard
├── docker/                  # Container configs
├── ARCHITECTURE.md          # Full technical architecture
├── PITCH.md                 # Demo presentation script
└── README.md                # ← This file
```

---

## What Makes This Different

| Feature | Why It Matters |
|---------|---------------|
| **Stigmergy** | Not just "agents that talk" — agents that coordinate without talking. The environment IS the protocol. |
| **Three-layer validation** | Not just "chatbots responding" — cross-referencing sensors, institutions, and citizens before acting. |
| **Kill/revive** | Not just "multiple agents" — genuinely flat. Prove it by killing any agent live. |
| **Real sensor data** | Not just simulated — USGS, weather, and NASA data flowing in real-time. |
| **Citizen intake** | Not just an API — a full mobile form with photo evidence, maps, and cross-validation. |
| **Event ID citations** | Not just parallel responses — agents reference each other's work by ID. True collaboration. |

---

## Team

| Role | Person | Handles |
|------|--------|---------|
| Backend + Architecture | Prince | Agent system, validation pipeline, APIs, infrastructure |
| Frontend Dashboard | [Lovable teammate] | Ops center UI consuming the API |
