# ⬡ MACS — Multi-Agent Crisis Response System

> A non-hierarchical swarm of autonomous AI agents (MACs) for humanitarian crisis response in conflict zones.
> No coordinators. No bottlenecks. Just emergence.

Built for the **Epiminds Hackathon 2026**.

---

## Quick Start

### Mock mode (no API key needed)
```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Live mode (Gemini 3.1 Flash)
```bash
GOOGLE_API_KEY=... GEMINI_MODEL=gemini-3.1-flash python main.py --live
```

### Dashboard
```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### Docker
```bash
GOOGLE_API_KEY=... GEMINI_MODEL=gemini-3.1-flash docker compose up
# Dashboard → http://localhost:3000
# WS server → ws://localhost:8765
```

> Optional fallback: set `ANTHROPIC_API_KEY` if you want to run Claude instead.

---

## CLI Controls

```
kill MEDIC       — simulate MAC failure (live demo moment)
revive MEDIC     — bring MAC back online
state            — print bulletin board stats
quit             — stop MACS
```

## Scenarios

```bash
python main.py --scenario cascade      # Hospital cascade (default)
python main.py --scenario blackout     # City-wide power failure
python main.py --scenario displacement # Mass civilian displacement
python main.py --list-scenarios
```

---

## What is a MAC?

A **MAC** (Multi-Agent Crisis response unit) is a single autonomous agent that:
- Owns one domain (MEDICAL, LOGISTICS, POWER, COMMS, or EVACUATION)
- Reads the shared bulletin board continuously
- Reasons independently about whether to act
- Posts its decisions back to the board

MACs never talk to each other directly. **MACS** is the collective system.

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design doc.

**tldr**: 5 MACs. 1 append-only bulletin board. No coordinator.
Each MAC perceives → reasons → acts. Coordination emerges from the shared environment (stigmergy).

```
MEDIC ──┐
LOGIST──┤  read/write   ┌──────────────┐   WebSocket   ┌──────────┐
POWER ──┼──────────────▶│ Bulletin     │──────────────▶│ React    │
COMMS ──┤               │ Board        │               │ Dashboard│
EVAC ───┘               └──────────────┘               └──────────┘
```

---

## File Structure

```
macs/
├── backend/
│   ├── main.py           # Entry point + CLI
│   ├── shared_state.py   # Bulletin board (append-only event log + WS broadcast)
│   ├── agent.py          # MAC base class (perceive→reason→act loop)
│   ├── personas.py       # 5 MACs: MEDIC, LOGISTICS, POWER, COMMS, EVAC
│   ├── scenarios.py      # Crisis scenarios with timed event injection
│   ├── ws_server.py      # WebSocket server for dashboard
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx       # Dashboard UI (MAC status, live feed, emergence graph)
│   │   ├── useSwarm.js   # WebSocket hook
│   │   └── index.css
│   ├── index.html
│   └── package.json
├── docker/
│   ├── Dockerfile.agent
│   └── Dockerfile.dashboard
├── docker-compose.yml
├── ARCHITECTURE.md       # Submission doc
└── README.md
```
