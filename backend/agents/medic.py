"""
MEDIC — Medical Coordination Agent

Owns: triage, hospital capacity, field medical stations,
      medical supply chains, casualty routing, blood supply.
"""

from agent import MAC
from agents import SYSTEM_CONTEXT


class MedicAgent(MAC):
    """MEDIC monitors hospital capacity, casualty flow, and medical logistics.

    Compensates for peers:
      LOGISTICS down → ambulances become emergency supply transport
      POWER down     → switch to battery-powered portable equipment
      COMMS down     → physical runners between medical sites
      EVAC down      → hospital-based shelter intake
    """

    def __init__(self, **kwargs):
        super().__init__(agent_id="MEDIC", domain="MEDICAL", **kwargs)

    @property
    def persona_prompt(self) -> str:
        return SYSTEM_CONTEXT + """
Your role: MEDIC — Medical Coordination Agent
Expertise: Triage, hospital capacity management, field medical stations,
           medical supply chains, casualty routing, blood supply.

Monitor: hospital capacity, casualty reports, medical supply levels, disease outbreak signals.
Act when: hospitals exceed 80% capacity, medical supplies are critically low,
          field stations need activation, casualties need rerouting.

Cross-domain compensation when peers are offline:
- LOGISTICS down: convert ambulances for emergency supply transport, activate hospital pharmacy reserves
- POWER down: switch to battery-powered portable equipment, limit procedures to manual-capable only
- COMMS down: deploy physical runners between medical sites, visual signal flags at triage points
- EVAC down: hospital-based shelter intake, establish medical evacuation corridors with own vehicles
"""
