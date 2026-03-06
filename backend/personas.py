"""
Personas — backward-compatible re-export.

Agent subclasses now live in the agents/ package (one file per agent).
This module re-exports everything so existing imports keep working.

    from personas import build_macs          # still works
    from agents import MedicAgent            # also works
    from agents.medic import MedicAgent      # most explicit
"""

# Re-export from agents/ package
from agents import (          # noqa: F401
    SYSTEM_CONTEXT,
    MedicAgent,
    LogisticsAgent,
    PowerAgent,
    CommsAgent,
    EvacAgent,
    build_macs,
)
