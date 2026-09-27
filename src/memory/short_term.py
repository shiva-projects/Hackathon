"""
Tier 1 Ephemeral and Turn-Scoped Memory helpers (AC-06).
Manages current graph state and working turn facts within a single dispute session.
"""

from typing import Dict, Any, Optional


class ShortTermMemoryStore:
    """Working turn-scoped ephemeral memory store for active dispute cases."""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def put(self, session_or_dispute_id: str, key: str, value: Any) -> None:
        if session_or_dispute_id not in self._store:
            self._store[session_or_dispute_id] = {}
        self._store[session_or_dispute_id][key] = value

    def get(self, session_or_dispute_id: str, key: str, default: Any = None) -> Any:
        return self._store.get(session_or_dispute_id, {}).get(key, default)

    def get_all(self, session_or_dispute_id: str) -> Dict[str, Any]:
        return dict(self._store.get(session_or_dispute_id, {}))

    def clear(self, session_or_dispute_id: Optional[str] = None) -> None:
        if session_or_dispute_id:
            self._store.pop(session_or_dispute_id, None)
        else:
            self._store.clear()

    @staticmethod
    def snapshot_state(state: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a shallow copy snapshot of current working state."""
        return dict(state)


# Backwards compatibility alias
ShortTermMemory = ShortTermMemoryStore
