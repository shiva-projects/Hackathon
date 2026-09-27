"""
Tests for Memory Eviction & Importance Policy (AC-08).
Validates:
1. TTL-based expiration of stale facts.
2. Importance-weighted LRU eviction when namespace reaches capacity limit.
Per AAIE_AGT_001_BFS Specification §5.1 (AC-08).
"""

import time
import pytest
from src.memory.long_term import LongTermMemoryStore


@pytest.fixture
def eviction_memory_store(tmp_path):
    store_file = tmp_path / "eviction_test_store.json"
    # Small capacity of 3 items for deterministic testing
    return LongTermMemoryStore(
        storage_path=str(store_file),
        max_entries_per_namespace=3,
        default_ttl_seconds=3600,
    )


def test_ttl_fact_expiration(eviction_memory_store):
    """AC-08: Asserts that facts with expired TTL are automatically evicted."""
    cust_id = "CUST-TTL-TEST"
    
    # Write a fact with a 1-second TTL using an approved key
    success = eviction_memory_store.write_fact(
        applicant_id=cust_id,
        memory_type="profile",
        fact_key="preferred_currency",
        fact_value="USD",
        ttl_seconds=1,
        importance=0.8,
    )
    assert success is True

    # Immediate read should return the fact
    facts_immediate = eviction_memory_store.get_facts(cust_id, "profile")
    assert "preferred_currency" in facts_immediate

    # Wait for TTL to expire
    time.sleep(1.2)

    # Subsequent read must evict the expired fact
    facts_after = eviction_memory_store.get_facts(cust_id, "profile")
    assert "preferred_currency" not in facts_after


def test_importance_weighted_lru_eviction(eviction_memory_store):
    """AC-08: Asserts that when namespace exceeds capacity, lowest importance facts are evicted first."""
    cust_id = "CUST-CAP-TEST"

    # Capacity is 3 items. Write 3 facts with varying importance:
    # 1. verified identity (high importance: 0.95)
    eviction_memory_store.write_fact(
        applicant_id=cust_id,
        memory_type="profile",
        fact_key="verified_identity",
        fact_value="SSN_VERIFIED",
        importance=0.95,
    )
    # 2. primary bank (medium-high importance: 0.80)
    eviction_memory_store.write_fact(
        applicant_id=cust_id,
        memory_type="profile",
        fact_key="primary_bank",
        fact_value="Chase Bank",
        importance=0.80,
    )
    # 3. preferred channel (low importance: 0.20)
    eviction_memory_store.write_fact(
        applicant_id=cust_id,
        memory_type="profile",
        fact_key="preferred_channel",
        fact_value="mobile_app",
        importance=0.20,
    )

    facts = eviction_memory_store.get_facts(cust_id, "profile")
    assert len(facts) == 3

    # Now write a 4th fact (high importance: 0.90) to trigger capacity eviction
    eviction_memory_store.write_fact(
        applicant_id=cust_id,
        memory_type="profile",
        fact_key="customer_tier",
        fact_value="PLATINUM",
        importance=0.90,
    )

    facts_after = eviction_memory_store.get_facts(cust_id, "profile")
    assert len(facts_after) == 3

    # Lowest importance item ('preferred_channel' with 0.20) must have been evicted!
    assert "preferred_channel" not in facts_after
    assert "verified_identity" in facts_after
    assert "customer_tier" in facts_after
