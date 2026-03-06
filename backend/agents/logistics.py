"""
LOGISTICS — Supply Chain & Distribution Agent

Owns: convoy routing, supply prioritization, aid distribution points,
      fuel management, vehicle coordination.
"""

from agent import MAC
from agents import SYSTEM_CONTEXT


class LogisticsAgent(MAC):
    """LOGISTICS manages supply convoys, distribution points, and fuel reserves.

    Compensates for peers:
      MEDIC down → emergency aid stations at distribution points
      POWER down → emergency fuel convoy to generator sites
      COMMS down → drivers as physical message relay
      EVAC down  → repurpose supply trucks for civilian transport
    """

    def __init__(self, **kwargs):
        super().__init__(agent_id="LOGISTICS", domain="LOGISTICS", **kwargs)

    @property
    def persona_prompt(self) -> str:
        return SYSTEM_CONTEXT + """
Your role: LOGISTICS — Supply Chain & Distribution Agent
Expertise: Convoy routing, supply prioritization, aid distribution points,
           fuel management, vehicle coordination.

Monitor: supply levels, convoy routes, distribution point capacity, fuel reserves.
Act when: routes are compromised, supplies need reprioritization,
          distribution points are overwhelmed, fuel is critically low.

Cross-domain compensation when peers are offline:
- MEDIC down: prioritize medical supply convoys, establish emergency aid stations at distribution points
- POWER down: emergency fuel convoy to generator sites, battery pack distribution to critical facilities
- COMMS down: use convoy drivers as physical message relay between zones, printed bulletin distribution
- EVAC down: repurpose supply trucks for civilian transport, open distribution points as temporary shelters
"""
