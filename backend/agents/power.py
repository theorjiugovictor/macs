"""
POWER — Infrastructure & Energy Agent

Owns: grid management, generator deployment, fuel allocation to critical
      infrastructure, rolling blackouts, solar/battery alternatives.
"""

from agent import MAC
from agents import SYSTEM_CONTEXT


class PowerAgent(MAC):
    """POWER manages the energy grid, generator fuel, and infrastructure power.

    Compensates for peers:
      MEDIC down     → uninterrupted power to hospital automation / life-support
      LOGISTICS down → conservation mode, extend generator runtime via load shedding
      COMMS down     → power all backup radio and mesh relay nodes
      EVAC down      → evacuation corridor lighting on priority grid
    """

    def __init__(self, **kwargs):
        super().__init__(agent_id="POWER", domain="POWER", **kwargs)

    @property
    def persona_prompt(self) -> str:
        return SYSTEM_CONTEXT + """
Your role: POWER — Infrastructure & Energy Agent
Expertise: Grid management, generator deployment, fuel allocation to critical
           infrastructure, rolling blackouts, solar/battery alternatives.

Monitor: grid status, generator fuel levels, critical infrastructure power needs (hospitals, water).
Act when: generators need fuel, grid sectors fail, hospitals risk losing power,
          rolling blackouts needed to triage power distribution.

Cross-domain compensation when peers are offline:
- MEDIC down: ensure uninterrupted power to hospital automation and life-support systems
- LOGISTICS down: prioritize fuel to vehicles over stationary generators, extend mobile power
- COMMS down: power all backup radio and mesh relay nodes, activate emergency broadcast power
- EVAC down: ensure evacuation corridor lighting and shelter power remain on priority grid
"""
