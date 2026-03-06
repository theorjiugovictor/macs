# MACS — Presentation & Demo Script

*Epiminds Hackathon 2026 — Swarm Intelligence Track*
*Target: 100/100*

---

## 🎯 Before You Present: Know Your Rubric

| Criterion | Weight | What Judges Want to See | Your Killer Moment |
|-----------|--------|------------------------|-------------------|
| **Emergence Quality** | 30% | Complex group behavior from simple individual rules | Cascade scenario: 7 events → cross-domain response chain |
| **Flatness** | 25% | No hidden coordinator, truly decentralized | Kill an agent live → system doesn't flinch |
| **Resilience** | 20% | Survives failure, degrades gracefully | Kill MEDIC → others absorb medical functions |
| **Collaboration Depth** | 15% | Agents genuinely building on each other's work | Event ID cross-references in agent posts |
| **Demo Impact** | 10% | Engaging, visual, memorable | Judges scan QR, submit report, watch agents react live |

---

## 🎬 The Script (5-7 minutes)

### Act 1: The Hook (30 seconds)

> "What happens when a hospital is bombed in a war zone? Power goes out. Convoys are blocked. Communications collapse. 2,400 civilians need evacuation. In a traditional system, you need a human coordinator making all these decisions. If they're killed, the system collapses.
>
> We asked: what if there IS no coordinator? What if the system can't collapse because there's nothing to collapse?
>
> This is MACS — a swarm of five AI agents that coordinate humanitarian crisis response the way an ant colony builds a nest. No hierarchy. No coordinator. No single point of failure."

### Act 2: The Architecture (60 seconds)

> "MACS uses **stigmergy** — the same principle behind ant colonies. Ants don't have project managers. They leave chemical traces in the environment, and other ants respond to those traces. The environment itself IS the coordination mechanism.
>
> Our five agents — MEDIC, LOGISTICS, POWER, COMMS, and EVAC — never talk to each other. They can't. They don't even know each other exists. They all read and write to one shared bulletin board — an append-only event log. Each agent runs a simple loop: perceive the board, reason about it with Gemini, post a decision back.
>
> Complex coordination emerges from these simple local interactions. That's emergence."

**[Show the architecture diagram on dashboard]**

### Act 3: The Three-Layer Pipeline (60 seconds)

> "But here's the real innovation. Having five chatbots isn't enough. In a crisis, information is noisy. People panic. Trolls post false reports. How do you separate signal from noise?
>
> MACS has a three-layer validation pipeline. Every piece of intelligence is tagged by source:
>
> **Layer 1: SENSOR** — USGS earthquakes, weather stations. This is ground truth. Highest trust.
> **Layer 2: API** — NASA disaster events, government alerts. Institutional truth.
> **Layer 3: CROWD** — citizen reports submitted through a mobile form. Human truth — but it needs corroboration.
>
> When a citizen report comes in, our corroboration engine cross-references it against recent SENSOR and API data. If a citizen says 'hospital is overwhelmed' and we have a magnitude 4.2 earthquake from USGS 15 minutes ago — that report gets a 0.95 confidence score. Agents treat it as near-certain.
>
> If someone submits 'aliens attacking downtown' — zero sensor corroboration, zero institutional data. Confidence: 0.0. Agents ignore it.
>
> This is the moat. Anyone can build a chatbot swarm. Cross-referencing three independent data layers in real-time — that's what makes MACS trustworthy enough for actual crisis response."

### Act 4: Live Demo — The Cascade (90 seconds)

> "Let me show you. This is a live system running on Google Cloud. The agents are reasoning with Gemini right now."

**[Point to dashboard — show agents active, events flowing]**

> "We're running the Hospital Cascade scenario. Watch what happens when a hospital is hit."

**Show the event feed. Narrate as events appear:**

> "The system just detected a hospital at 92% capacity with 47 casualties. Watch MEDIC — it activates field triage at B-7. Nobody told it to do that. It read the board and decided.
>
> Now power goes down in sectors 3 and 4. POWER deploys generators. But look — MEDIC also reacts. It flags the fuel urgency for hospital backup power. MEDIC doesn't know POWER exists. It just saw the grid failure on the board and reasoned about what that means for hospitals.
>
> Route Alpha is blocked. LOGISTICS reroutes the convoy. Blood supply is critical — LOGISTICS reprioritizes. Every response builds on the previous ones. They cite each other's event IDs. They reference each other by name. Zero instructions between them."

### Act 5: The Kill Demo — Resilience (60 seconds)

> "Now the real test. What happens when a critical agent goes down?"

**[Send kill command — either from dashboard control or terminal]**

> "I just killed MEDIC. In a traditional system, this would mean no medical coordination. In MACS..."

**[Wait 10-15 seconds for other agents to react]**

> "Watch the other agents. LOGISTICS is now prioritizing medical supply convoys. COMMS is broadcasting medical self-aid guidance. EVAC is equipping buses with first-aid kits. Nobody told them to do this. They detected that MEDIC's posts stopped appearing on the board, and they each decided how to compensate from their own domain.
>
> The swarm degraded, but it's alive. Medical functions aren't gone — they're distributed across four agents."

**[Send revive command]**

> "And when we bring MEDIC back — it reads the full bulletin history, catches up on everything that happened while it was down, and seamlessly rejoins the swarm. No manual re-sync. No restart needed."

### Act 6: Citizen Demo — The QR Moment (60 seconds)

> "One more thing. MACS isn't just for operators. Citizens on the ground can contribute intelligence."

**[Show QR code or open the intake form]**

> "Anyone can scan this QR code and submit a field report. You can take a photo, pin your location on Google Maps, and describe what you see. The report flows through the three-layer validator — gets cross-referenced against sensor data — and if it's credible and corroborated, agents react to it in real-time.
>
> Other citizens can cross-validate reports — hit 'I CAN CONFIRM THIS' to boost confidence. It's crowdsourced intelligence with institutional-grade validation."

**[Invite a judge to try it if time permits]**

### Act 7: The Close (30 seconds)

> "MACS is not five chatbots pretending to coordinate. It's a genuinely flat, stigmergic swarm with a three-layer validation pipeline that cross-references sensor, institutional, and citizen data in real-time.
>
> Kill any agent — the swarm adapts. Submit false reports — the validator catches them. Add more agents — the system scales linearly.
>
> The validation pipeline IS the product. Thank you."

---

## 🔧 Demo Checklist (Before Going on Stage)

### 10 Minutes Before

- [ ] Verify system is live: `curl https://macs-demo.duckdns.org/status`
- [ ] Verify all 5 agents online: `curl https://macs-demo.duckdns.org/agents`
- [ ] Verify WebSocket working: Dashboard shows live events
- [ ] Open intake form on phone: `https://macs-demo.duckdns.org`
- [ ] Have kill/revive commands ready (bookmark or terminal)
- [ ] Dashboard is open and visible on projector

### If Something Breaks

| Problem | Fix |
|---------|-----|
| Agents not responding | SSH into VM: `sudo systemctl restart macs` |
| Dashboard not connecting | Check Caddy: `sudo systemctl restart caddy` |
| WebSocket disconnecting | Refresh dashboard — it auto-reconnects |
| Intake form not loading | Check port 8766: `curl localhost:8766/` from VM |
| TLS cert expired | `sudo systemctl restart caddy` (auto-renews) |

### Emergency SSH

```bash
gcloud compute ssh macs-backend --zone us-central1-a --project macs-489321
sudo systemctl restart macs
sudo journalctl -u macs -n 30 --no-pager
```

---

## 🧠 Anticipate These Questions

### "How is this different from just having five GPT prompts?"

> "Three things. First, the agents never communicate directly — they coordinate through the shared environment, which is stigmergy. That's fundamentally different from message-passing architectures like AutoGen or CrewAI. Second, we have a three-layer validation pipeline that cross-references sensor, institutional, and citizen data before agents act. It's not just chatbots reacting — it's validated intelligence driving decisions. Third, kill any agent and the system continues. Try that with CrewAI."

### "What happens if the bulletin board goes down?"

> "Great question. Right now it's in-memory — single point of failure. In production, you'd swap it for Redis Streams. Our BulletinBoard API is designed for exactly this — same interface, just change the backend. The agents don't know the difference."

### "How do you prevent agents from conflicting with each other?"

> "We don't — and that's the point. In a flat system, agents may occasionally have overlapping responses. But look at the bulletin board: they read each other's posts and explicitly avoid duplication. The stigmergic protocol in their prompts says 'never repeat what another MAC already handled.' In practice, conflicts are rare because each agent owns a distinct domain."

### "Is this really emergent or just well-designed prompts?"

> "The prompts give each agent domain expertise and the instruction to read the board. But the specific cross-domain responses — POWER reacting to a medical crisis, LOGISTICS reacting to an evacuation order — those emerge at runtime. We don't hard-code which agent responds to which event. The agents decide based on what they see. That's emergence: complex group behavior from simple individual rules."

### "What's the latency? Can this work in a real crisis?"

> "Each agent cycle is about 2-3 seconds with Gemini Flash. Cross-domain responses cascade within 10-15 seconds. For humanitarian crisis coordination, that's faster than any human command chain. We're not trying to replace real-time control systems — we're replacing the human coordinator who becomes a bottleneck."

### "Why not use a more powerful model like GPT-4 or Claude Opus?"

> "Speed. In a crisis, a fast good decision beats a slow perfect decision. Gemini Flash Lite gives us sub-2-second reasoning per agent tick. With five agents running in parallel, that's five domain-expert decisions every 3 seconds. A larger model would be 5-10x slower, which defeats the purpose of real-time crisis response."

---

## 📊 Key Numbers to Memorize

| Metric | Value |
|--------|-------|
| Agents | 5 autonomous MACs |
| Agent cycle time | ~3 seconds per perceive→reason→act |
| Cascade response | 7 crisis events → 6+ cross-domain responses in 75 seconds |
| External data sources | 3 (USGS, Open-Meteo, NASA EONET) |
| Corroboration window | 10 minutes sliding |
| Layer weights | SENSOR 0.45, API 0.35, CROWD 0.15 |
| Kill → compensation | ~10-15 seconds for remaining agents to detect and adapt |
| Revive → catch-up | Instant (reads full bulletin history) |
| TLS | Let's Encrypt auto-renewing |
| Uptime | systemd managed, auto-restart on failure |

---

## 💡 Power Phrases (Use These)

- *"The environment IS the coordination mechanism"*
- *"Agents that coordinate without communicating"*
- *"The validation pipeline is the product"*
- *"Multi-source corroborated intelligence vs. single-source rumors"*
- *"Kill it — the swarm doesn't flinch"*
- *"Ground truth from sensors, institutional truth from APIs, human truth from citizens"*
- *"Complex behavior from simple rules — that's emergence"*
- *"No coordinator to kill means no coordinator to fail"*
