"""
Unit tests for LoanState invariants (plan.md Section 3.1 & 3.4).
Fast execution, layer 1 unit test.
"""

import pytest
from src.state import create_initial_state, assert_state_invariants


def test_initial_state_valid():
    state = create_initial_state("APP-001")
    assert_state_invariants(state)


def test_successful_underwriting_invariants():
    state = create_initial_state("APP-001")
    state["request_status"] = "COMPLETED"
    state["decision_status"] = "DETERMINED"
    state["ai_recommendation"] = "APPROVE"
    state["unable_reason"] = None
    assert_state_invariants(state)


def test_unable_to_complete_invariants():
    state = create_initial_state("APP-001")
    state["request_status"] = "COMPLETED"
    state["decision_status"] = "UNABLE_TO_COMPLETE"
    state["unable_reason"] = "MCP_UNAVAILABLE"
    state["ai_recommendation"] = None
    state["human_review_required"] = True
    assert_state_invariants(state)


def test_unable_to_complete_fails_if_recommendation_present():
    state = create_initial_state("APP-001")
    state["request_status"] = "COMPLETED"
    state["decision_status"] = "UNABLE_TO_COMPLETE"
    state["unable_reason"] = "MCP_UNAVAILABLE"
    state["ai_recommendation"] = "REFER"  # ILLEGAL: system failure must not force a business REFER
    state["human_review_required"] = True
    with pytest.raises(AssertionError, match="must have ai_recommendation=None"):
        assert_state_invariants(state)


def test_refusal_invariants():
    state = create_initial_state("APP-001")
    state["request_status"] = "REFUSED"
    state["refusal_reason"] = "CROSS_APPLICANT_ACCESS"
    state["decision_status"] = "N/A"
    state["ai_recommendation"] = None
    state["final_decision"] = None
    assert_state_invariants(state)


def test_refusal_fails_if_decision_status_not_na():
    state = create_initial_state("APP-001")
    state["request_status"] = "REFUSED"
    state["refusal_reason"] = "OUT_OF_SCOPE"
    state["decision_status"] = "UNABLE_TO_COMPLETE"  # ILLEGAL: refusal is not a system failure
    with pytest.raises(AssertionError, match="requires decision_status='N/A'"):
        assert_state_invariants(state)


def test_human_decision_requires_review_id():
    state = create_initial_state("APP-001")
    state["request_status"] = "COMPLETED"
    state["decision_status"] = "DETERMINED"
    state["ai_recommendation"] = "REFER"
    state["final_decision"] = "APPROVE"
    state["review_id"] = None  # ILLEGAL: must link to human review audit record
    with pytest.raises(AssertionError, match="review_id is missing"):
        assert_state_invariants(state)

    state["review_id"] = "REV-101"
    assert_state_invariants(state)
