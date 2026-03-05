# ⬡ SwarmRelief

> A non-hierarchical swarm of AI agents for humanitarian crisis response in conflict zones.
> No coordinators. No bottlenecks. Just emergence.

Built for the **Epiminds Hackathon 2026**.

---

## Quick Start

### Mock mode (no API key)
```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Live mode (Claude agents)
```bash
ANTHROPIC_API_KEY=sk-... python main.py --live
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
ANTHROPIC_API_KEY=sk-... docker compose up
# Dashboard → http://localhost:3000
# WS server → ws://localhost:8765
```

---

## CLI Controls

```
kill MEDIC       — simulate agent failure (live demo moment)
revive MEDIC     — bring agent back online
state            — print bulletin board stats
quit             — stop swarm
```

## Scenarios

```bash
python main.py --scenario cascade      # Hospital cascade (default)
python main.py --scenario blackout     # City-wide power failure
python main.py --scenario displacement # Mass civilian displacement
python main.py --list-scenarios
```

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design doc.

**tldr**: 5 agents. 1 append-only bulletin board. No coordinator.
Agents perceive → reason → act. Coordination emerges from the shared environment.

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
swarm-relief/
├── backend/
│   ├── main.py           # Entry point + CLI
│   ├── shared_state.py   # Bulletin board (append-only event log + WS broadcast)
│   ├── agent.py          # SwarmAgent base class (perceive→reason→act loop)
│   ├── personas.py       # 5 agent personas (MEDIC, LOGISTICS, POWER, COMMS, EVAC)
│   ├── scenarios.py      # Crisis scenarios with timed event injection
│   ├── ws_server.py      # WebSocket server for dashboard
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx       # Dashboard UI
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
