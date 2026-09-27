"""
Tier 3 Verified Long-Term Semantic Memory with Eviction & Importance Policy (AC-08).
Namespaced strictly by (applicant_id / customer_id, memory_type).
Enforces:
1. Gated fact validation (memory_write_policy).
2. TTL-based expiration for temporal validity.
3. Importance-weighted LRU eviction cap (AC-08).
Per AAIE_AGT_001_BFS Specification §5.1 (AC-06, AC-07, AC-08).
"""

import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from src.memory.memory_write_policy import validate_long_term_fact

try:
    import langmem
    from langgraph.store.memory import InMemoryStore
    _HAS_LANGMEM = True
except ImportError:
    _HAS_LANGMEM = False
    InMemoryStore = None

DEFAULT_TTL_SECONDS = 7776000   # 90 calendar days
DEFAULT_CAP_PER_NAMESPACE = 15   # Max distinct facts per namespace before eviction fires


class LongTermMemoryStore:
    """
    Tier 3 Persistent semantic memory store for verified customer/dispute attributes.
    Backed by LangGraph BaseStore and LangMem namespaced memory tools (AC-06, AC-07).
    Enforces TTL expiration and importance-weighted LRU eviction (AC-08).
    """

    def __init__(
        self,
        storage_path: str = "data/long_term_memory.json",
        max_entries_per_namespace: int = DEFAULT_CAP_PER_NAMESPACE,
        default_ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries_per_namespace
        self.default_ttl = default_ttl_seconds
        self._cache = self._load()
        self.has_langmem = _HAS_LANGMEM

        # LangMem / LangGraph store integration
        if _HAS_LANGMEM:
            self.langgraph_store = InMemoryStore()
            for ns_key, facts in self._cache.items():
                parts = ns_key.split(":", 1)
                ns = tuple(parts) if len(parts) == 2 else (parts[0],)
                for k, v in facts.items():
                    val = v["value"] if isinstance(v, dict) and "value" in v else v
                    self.langgraph_store.put(ns, key=k, value={"fact": val})
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
        ttl_seconds: Optional[int] = None,
        importance: float = 0.5,
    ) -> bool:
        """
        Attempts to write a verified fact into long-term memory with TTL & importance metadata.
        Gated by memory_write_policy. Triggers eviction if capacity is reached (AC-08).
        """
        is_valid, reason = validate_long_term_fact(fact_key, fact_value)
        if not is_valid:
            return False

        namespace_key = self._make_key(applicant_id, memory_type)
        if namespace_key not in self._cache:
            self._cache[namespace_key] = {}

        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl

        # Record envelope with eviction telemetry (AC-08)
        self._cache[namespace_key][fact_key] = {
            "value": fact_value,
            "created_at": now,
            "last_accessed": now,
            "ttl_seconds": ttl,
            "importance": max(0.0, min(1.0, float(importance))),
        }

        # Enforce eviction policy (AC-08)
        self.evict_namespace(applicant_id, memory_type)
        self._save()

        # Update LangGraph store
        if self.langgraph_store is not None:
            self.langgraph_store.put((applicant_id, memory_type), key=fact_key, value={"fact": fact_value})

        return True

    def evict_namespace(self, applicant_id: str, memory_type: str) -> List[str]:
        """
        Executes memory eviction policy (AC-08):
        1. TTL Expiration: Prunes any fact whose elapsed time exceeds its ttl_seconds.
        2. Importance-weighted LRU: If count > max_entries, prunes lowest (importance * recency) facts.
        Returns list of evicted keys.
        """
        namespace_key = self._make_key(applicant_id, memory_type)
        entries = self._cache.get(namespace_key, {})
        if not entries:
            return []

        now = time.time()
        evicted_keys = []

        # 1. TTL Pass
        keys_to_remove = []
        for k, meta in entries.items():
            if isinstance(meta, dict) and "created_at" in meta and "ttl_seconds" in meta:
                if (now - meta["created_at"]) > meta["ttl_seconds"]:
                    keys_to_remove.append(k)

        for k in keys_to_remove:
            del entries[k]
            evicted_keys.append(k)

        # 2. Capacity & Importance-Weighted LRU Pass
        if len(entries) > self.max_entries:
            # Rank entries by score = importance * (1 / (1 + age_hours))
            scored = []
            for k, meta in entries.items():
                if isinstance(meta, dict):
                    importance = meta.get("importance", 0.5)
                    last_access = meta.get("last_accessed", now)
                    # Higher score = more important / more recently accessed
                    score = importance * (1.0 / (1.0 + max(0.0, (now - last_access) / 3600.0)))
                    scored.append((k, score))
                else:
                    scored.append((k, 0.1))

            # Sort ascending by score (lowest score evicted first)
            scored.sort(key=lambda x: x[1])
            excess = len(entries) - self.max_entries
            for k, _ in scored[:excess]:
                del entries[k]
                evicted_keys.append(k)

        if evicted_keys:
            self._save()

        return evicted_keys

    def get_facts(self, applicant_id: str, memory_type: str = "profile") -> Dict[str, Any]:
        """
        Retrieves stored verified facts for a namespace, updating last_accessed timestamps.
        Unwraps raw values so callers receive standard {fact_key: fact_value} dicts.
        """
        namespace_key = self._make_key(applicant_id, memory_type)
        entries = self._cache.get(namespace_key, {})
        if not entries:
            return {}

        # Prune expired before returning
        self.evict_namespace(applicant_id, memory_type)
        entries = self._cache.get(namespace_key, {})

        now = time.time()
        result = {}
        for k, meta in entries.items():
            if isinstance(meta, dict) and "value" in meta:
                meta["last_accessed"] = now
                result[k] = meta["value"]
            else:
                result[k] = meta

        return result

    def get_langmem_tool(self, applicant_id: str, memory_type: str = "profile"):
        if not _HAS_LANGMEM or self.langgraph_store is None:
            return None
        return langmem.create_manage_memory_tool(
            namespace=(applicant_id, memory_type),
            store=self.langgraph_store,
        )

    def clear(self) -> None:
        self._cache = {}
        if self.langgraph_store is not None:
            self.langgraph_store = InMemoryStore()
        self._save()


# Default singleton memory store
long_term_memory = LongTermMemoryStore()
