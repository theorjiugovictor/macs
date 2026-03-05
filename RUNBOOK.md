# MACS Hackathon Run Book

This run book is optimized for the swarm-intelligence judging rubric:

- Emergence Quality (30%)
- Flatness (25%)
- Resilience (20%)
- Collaboration Depth (15%)
- Demo Impact (10%)

---

## 1) Fast score upgrade plan (highest impact first)

1. Script one **repeatable wow sequence** (do not improvise).
2. Narrate every action against a rubric category.
3. Capture hard proof (event IDs, timestamps, screenshots).
4. Show one failure + recovery live (`kill` then `revive`).
5. Show one field report changing swarm behavior.

---

## 2) Demo architecture talking points (30 seconds)

Use this exact framing:

1. “There is no coordinator. Every MAC reads/writes the same bulletin board.”
2. “Coordination is stigmergic: agents react to traces in shared state.”
3. “If one MAC dies, others continue because control is decentralized.”

Reference files:

- [backend/agent.py](backend/agent.py)
- [backend/shared_state.py](backend/shared_state.py)
- [backend/main.py](backend/main.py)
- [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 3) Pre-demo checklist (T-10 min)

## Services

- Confirm backend is running on VM.
- Confirm dashboard WebSocket endpoint responds.
- Confirm intake UI endpoint responds.

## URLs to open before presenting

- Dashboard (local): http://localhost:3001/
- Intake UI (VM): http://35.222.182.254:8766/
- Intake QR (VM): http://35.222.182.254:8766/qr

## VM health checks

Run from local terminal:

```bash
curl -sS -m 5 -o /dev/null -w "intake:%{http_code}\n" http://35.222.182.254:8766/
curl -sS -m 5 -o /dev/null -w "ws-port:%{http_code}\n" http://35.222.182.254:8765/
```

Expected:

- `intake:200`
- `ws-port:426` (normal for raw WS endpoint over HTTP)

---

## 4) Live demo script (7–9 min)

## Segment A — Baseline swarm behavior (Emergence)

1. Start with dashboard visible.
2. Explain scenario injection and independent MAC action.
3. Point to cross-domain actions appearing without direct calls.

What to say:

“No orchestrator assigns tasks. Each MAC independently reacts to shared context and produces coordinated system behavior.”

## Segment B — Wow moment (Resilience + Flatness)

In backend CLI, run:

```text
kill MEDIC
```

Then narrate:

1. MEDIC goes offline.
2. Other MACs continue posting actions.
3. Cross-domain coverage continues.

After ~20–40 seconds:

```text
revive MEDIC
```

Then narrate:

1. MEDIC rejoins.
2. Reads shared history.
3. Resynchronizes without a coordinator.

## Segment C — Human-in-the-loop adaptation (Collaboration Depth)

Submit a field report from intake UI (mobile or browser), for example:

“Route Bravo blocked near junction 4, two buses stranded, civilians with injuries.”

Show in dashboard:

1. `FIELD_REPORT` event appears.
2. Multiple MACs react in sequence (LOGISTICS + EVAC + MEDIC).

---

## 5) How to prove the wow segment (hard evidence)

Capture 4 proof artifacts during demo:

1. Screenshot: `AGENT_OFFLINE` event for MEDIC.
2. Screenshot: at least 2 other MAC `ACTION_TAKEN` events while MEDIC is down.
3. Screenshot: `AGENT_ONLINE` for MEDIC after revive.
4. Screenshot: post-revive MEDIC action.

Optional log proof on VM:

```bash
$HOME/google-cloud-sdk/bin/gcloud compute ssh macs-backend \
  --zone us-central1-a --project macs-489321 \
  --command 'sudo journalctl -u macs.service --since "10 minutes ago" --no-pager | tail -n 200'
```

---

## 6) Rubric mapping cheat sheet (say this explicitly)

- **Emergence Quality:** “Cross-domain responses appear from local rules + shared board.”
- **Flatness:** “No coordinator process or routing brain; all MACs use same interface.”
- **Resilience:** “One MAC failure does not halt collective response.”
- **Collaboration Depth:** “Agents build on prior events posted by others and field intel.”
- **Demo Impact:** “Live event stream + mobile intake + failure recovery in one flow.”

---

## 7) Contingency plan (if live API fails)

If model/API instability occurs:

1. Continue in mock mode immediately.
2. Keep same script: baseline -> kill/revive -> field report.
3. State clearly: “Swarm logic and emergence are architecture-level, model-agnostic.”

This protects judging on flatness/resilience/collaboration even if LLM quality dips.

---

## 8) Final submission checklist

- [ ] Working demo rehearsed with timer
- [ ] Repo up to date on GitHub
- [ ] Architecture doc finalized
- [ ] 4 wow-proof screenshots captured
- [ ] Submission form completed
