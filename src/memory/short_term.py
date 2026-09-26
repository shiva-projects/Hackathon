"""
Tier 1 Ephemeral and Turn-Scoped Memory helpers.
Manages current graph state and working turn facts.
"""

from typing import Dict, Any
from src.state import LoanState


class ShortTermMemory:
    """Encapsulates turn-scoped ephemeral state manipulations."""

    @staticmethod
    def snapshot_state(state: LoanState) -> Dict[str, Any]:
        """Creates a shallow copy snapshot of current working state."""
        return dict(state)
