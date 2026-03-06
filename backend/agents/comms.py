"""
COMMS — Communications & Intelligence Agent

Owns: mesh networking, radio relay, civilian broadcast systems,
      signal intelligence, external coordination (UN, NGOs, media).
"""

from agent import MAC
from agents import SYSTEM_CONTEXT


class CommsAgent(MAC):
    """COMMS maintains the communication mesh, relays, and external coordination.

    Compensates for peers:
      MEDIC down     → broadcast medical self-aid guidance, relay casualty locations
      LOGISTICS down → distribute last known supply status to field teams
      POWER down     → switch to battery-powered radio, reduce broadcast power
      EVAC down      → broadcast shelter locations and safe routes on loop
    """

    def __init__(self, **kwargs):
        super().__init__(agent_id="COMMS", domain="COMMS", **kwargs)

    @property
    def persona_prompt(self) -> str:
        return SYSTEM_CONTEXT + """
Your role: COMMS — Communications & Intelligence Agent
Expertise: Mesh networking, radio relay, civilian broadcast systems,
           signal intelligence, external coordination (UN, NGOs, media).

Monitor: relay node status, comms coverage gaps, distress signals, external aid comms.
Act when: relays fail (activate backups), coverage drops below 50%,
          distress signals detected, external aid needs coordination channel.

Cross-domain compensation when peers are offline:
- MEDIC down: broadcast medical self-aid guidance on all channels, relay casualty locations to remaining MACs
- LOGISTICS down: distribute last known supply status to field teams, coordinate ad-hoc civilian supply sharing
- POWER down: switch to battery-powered radio, reduce broadcast power to extend coverage duration
- EVAC down: broadcast shelter locations and safe routes on loop, coordinate civilian self-evacuation via radio
"""
