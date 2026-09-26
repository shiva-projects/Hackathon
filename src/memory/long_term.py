"""
Tier 3 Verified Long-Term Semantic Memory.
Namespaced by applicant_id + memory_type.
Enforces that only facts verified by memory_write_policy are stored.
Per plan.md Section 6.3 & 14.5.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from src.memory.memory_write_policy import validate_long_term_fact


class LongTermMemoryStore:
    """
    Persistent key-value memory store for verified applicant attributes.
    Namespaced strictly by applicant_id + memory_type.
    """

    def __init__(self, storage_path: str = "data/long_term_memory.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=2)

    def _make_key(self, applicant_id: str, memory_type: str) -> str:
        return f"{applicant_id}:{memory_type}"

    def write_fact(
        self,
        applicant_id: str,
        memory_type: str,
        fact_key: str,
        fact_value: Any,
    ) -> bool:
        """
        Attempts to write a fact into long-term memory.
        Gated by memory_write_policy. Returns True if stored, False if rejected.
        """
        is_valid, reason = validate_long_term_fact(fact_key, fact_value)
        if not is_valid:
            # Memory failure/rejection never blocks underwriting (Rule 8)
            return False

        namespace_key = self._make_key(applicant_id, memory_type)
        if namespace_key not in self._cache:
            self._cache[namespace_key] = {}

        self._cache[namespace_key][fact_key] = fact_value
        self._save()
        return True

    def get_facts(self, applicant_id: str, memory_type: str = "profile") -> Dict[str, Any]:
        """Retrieves stored verified facts for a specific applicant namespace."""
        namespace_key = self._make_key(applicant_id, memory_type)
        return self._cache.get(namespace_key, {}).copy()

    def clear(self) -> None:
        """Clears memory storage (for testing)."""
        self._cache = {}
        self._save()


# Default singleton memory store
long_term_memory = LongTermMemoryStore()
