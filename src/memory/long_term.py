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


try:
    import langmem
    from langgraph.store.memory import InMemoryStore
    _HAS_LANGMEM = True
except ImportError:
    _HAS_LANGMEM = False
    InMemoryStore = None


class LongTermMemoryStore:
    """
    Tier 3 Persistent semantic memory store for verified applicant attributes.
    Backed by LangGraph BaseStore and LangMem namespaced memory tools (plan.md Section 6.3 & 14.5).
    Namespaced strictly by (applicant_id, memory_type).
    """

    def __init__(self, storage_path: str = "data/long_term_memory.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = self._load()
        self.has_langmem = _HAS_LANGMEM
        
        # LangMem / LangGraph store integration
        if _HAS_LANGMEM:
            self.langgraph_store = InMemoryStore()
            # Hydrate LangGraph store from persistent storage
            for ns_key, facts in self._cache.items():
                parts = ns_key.split(":", 1)
                ns = tuple(parts) if len(parts) == 2 else (parts[0],)
                for k, v in facts.items():
                    self.langgraph_store.put(ns, key=k, value={"fact": v})
        else:
            self.langgraph_store = None

    def _load(self) -> Dict[str, Any]:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Could not load long-term memory store from {self.storage_path}: {e}")
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
        Updates both the persistent JSON cache and the LangMem LangGraph store.
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

        # Update LangMem store
        if self.langgraph_store is not None:
            self.langgraph_store.put((applicant_id, memory_type), key=fact_key, value={"fact": fact_value})

        return True

    def get_facts(self, applicant_id: str, memory_type: str = "profile") -> Dict[str, Any]:
        """Retrieves stored verified facts for a specific applicant namespace."""
        namespace_key = self._make_key(applicant_id, memory_type)
        return self._cache.get(namespace_key, {}).copy()

    def get_langmem_tool(self, applicant_id: str, memory_type: str = "profile"):
        """
        Returns a LangMem memory management tool bound to this applicant namespace.
        Enables agent reflection and memory updates through the LangMem framework.
        """
        if not _HAS_LANGMEM or self.langgraph_store is None:
            return None
        return langmem.create_manage_memory_tool(
            namespace=(applicant_id, memory_type),
            store=self.langgraph_store,
        )

    def clear(self) -> None:
        """Clears memory storage (for testing)."""
        self._cache = {}
        if self.langgraph_store is not None:
            self.langgraph_store = InMemoryStore()
        self._save()


# Default singleton memory store
long_term_memory = LongTermMemoryStore()
