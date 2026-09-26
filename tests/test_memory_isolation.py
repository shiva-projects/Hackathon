"""
Tests for Memory Isolation across applicants (plan.md Section 14.5).
Asserts that APP-001's stored facts are completely invisible to queries scoped to APP-002.
"""

import pytest
from src.memory.long_term import LongTermMemoryStore


def test_applicant_memory_isolation(tmp_path):
    store = LongTermMemoryStore(str(tmp_path / "isolation_memory.json"))

    # 1. APP-001 writes facts
    store.write_fact("APP-001", "profile", "employment", "salaried")
    store.write_fact("APP-001", "profile", "account_tenure_years", 5)

    # 2. APP-002 writes facts
    store.write_fact("APP-002", "profile", "employment", "self_employed")

    # 3. Query APP-001
    facts_001 = store.get_facts("APP-001", "profile")
    assert facts_001["employment"] == "salaried"
    assert facts_001["account_tenure_years"] == 5

    # 4. Query APP-002: must NOT contain APP-001's facts
    facts_002 = store.get_facts("APP-002", "profile")
    assert facts_002["employment"] == "self_employed"
    assert "account_tenure_years" not in facts_002

    # 5. Query unknown applicant: must return empty dict
    facts_003 = store.get_facts("APP-003", "profile")
    assert len(facts_003) == 0
