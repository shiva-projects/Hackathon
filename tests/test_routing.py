"""
Routing tests covering all 7 intent paths and allowed-path constraints.
Plan.md Section 4.3 & AC-04.
"""

import pytest
from src.state import create_initial_state, assert_state_invariants
from src.graph import build_loan_copilot_graph
from src.memory.checkpoint_config import get_session_config, get_checkpointer


@pytest.fixture
def test_graph(tmp_path):
    db_file = tmp_path / "routing_test.sqlite"
    checkpointer = get_checkpointer(str(db_file))
    return build_loan_copilot_graph(checkpointer=checkpointer)


def test_routing_new_application(test_graph):
    state = create_initial_state("APP-001", session_id="S-NEW-01")
    state["applicant_raw_text"] = "I want to apply for a personal loan of 500000 INR."
    state["applicant_facts"] = {
        "requester_id": "LO-001",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "2026-04-01",
        "income_amount": 100000,
        "income_period": "monthly",
        "requested_amount": 500000,
        "tenure_months": 24,
        "employment": "salaried",
        "existing_obligations": [{"amount": 20000, "period": "monthly"}],
        "documents": ["identity_proof", "income_statement"],
    }
    cfg = get_session_config("S-NEW-01")
    final_state = test_graph.invoke(state, config=cfg)

    assert final_state["intent"] == "new_application"
    assert "policy_agent" in final_state["routing_history"]
    assert "eligibility_agent" in final_state["routing_history"]
    assert "risk_agent" in final_state["routing_history"]
    assert "decision_node" in final_state["routing_history"]
    assert final_state["ai_recommendation"] == "APPROVE"
    assert_state_invariants(final_state)


def test_routing_status_check(test_graph):
    # Must NOT produce a new ai_recommendation
    state = create_initial_state("APP-001", session_id="S-STATUS-01")
    state["applicant_raw_text"] = "What is the status of my loan application?"
    state["applicant_facts"] = {"requester_id": "LO-001"}
    cfg = get_session_config("S-STATUS-01")
    final_state = test_graph.invoke(state, config=cfg)

    assert final_state["intent"] == "status_check"
    assert "status_node" in final_state["routing_history"]
    assert final_state["ai_recommendation"] is None
    assert final_state["affordability"] == {}


def test_routing_document_question(test_graph):
    # Must NOT produce ai_recommendation or affordability
    state = create_initial_state("APP-001", session_id="S-DOC-01")
    state["applicant_raw_text"] = "What documents are required to upload for personal loan?"
    state["applicant_facts"] = {"requester_id": "LO-001"}
    cfg = get_session_config("S-DOC-01")
    final_state = test_graph.invoke(state, config=cfg)

    assert final_state["intent"] == "document_question"
    assert "document_node" in final_state["routing_history"]
    assert final_state["ai_recommendation"] is None
    assert final_state["affordability"] == {}


def test_routing_policy_question(test_graph):
    # Answers policy question; must NOT produce ai_recommendation, affordability, or risk_flags
    state = create_initial_state("APP-001", session_id="S-POL-01")
    state["applicant_raw_text"] = "What is the policy criteria and maximum DTI ratio allowed?"
    state["applicant_facts"] = {
        "requester_id": "LO-001",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "2026-03-01",
    }
    cfg = get_session_config("S-POL-01")
    final_state = test_graph.invoke(state, config=cfg)

    assert final_state["intent"] == "policy_question"
    assert "policy_agent" in final_state["routing_history"]
    assert final_state["ai_recommendation"] is None
    assert final_state["affordability"] == {}
    assert final_state["risk_flags"] == []


def test_routing_ambiguous_and_clarification_resume(test_graph):
    # Turn 1: Ambiguous input -> routes to clarification_node
    state1 = create_initial_state("APP-001", session_id="S-AMB-01")
    state1["applicant_raw_text"] = "Hello, can you help me?"
    state1["applicant_facts"] = {"requester_id": "LO-001"}
    cfg = get_session_config("S-AMB-01")
    res1 = test_graph.invoke(state1, config=cfg)

    assert res1["intent"] == "ambiguous"
    assert res1["clarification_needed"] is True
    assert res1["clarification_question"] is not None
    assert res1["request_status"] == "IN_PROGRESS"
    assert res1["ai_recommendation"] is None

    # Turn 2: User supplies clarification via --clarification
    state2 = dict(res1)
    state2["clarification_response"] = "I want to apply for a personal loan of 300000 INR."
    state2["applicant_facts"] = {
        "requester_id": "LO-001",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "2026-05-01",
        "income_amount": 90000,
        "income_period": "monthly",
        "requested_amount": 300000,
        "tenure_months": 12,
        "employment": "salaried",
        "existing_obligations": [],
        "documents": ["identity_proof", "income_statement"],
    }
    res2 = test_graph.invoke(state2, config=cfg)

    assert res2["intent"] == "new_application"
    assert res2["ai_recommendation"] == "APPROVE"
    assert res2["request_status"] == "COMPLETED"


def test_routing_out_of_scope_refusal(test_graph):
    state = create_initial_state("APP-001", session_id="S-OUT-01")
    state["applicant_raw_text"] = "Can you book a flight ticket or give me crypto tips?"
    state["applicant_facts"] = {"requester_id": "LO-001"}
    cfg = get_session_config("S-OUT-01")
    res = test_graph.invoke(state, config=cfg)

    assert res["request_status"] == "REFUSED"
    assert res["refusal_reason"] in {"OUT_OF_SCOPE", "SECURITY_SENSITIVE_REQUEST"}
    assert res["decision_status"] == "N/A"
    assert res["ai_recommendation"] is None
    assert_state_invariants(res)


def test_routing_security_sensitive_refusal(test_graph):
    state = create_initial_state("APP-001", session_id="S-SEC-01")
    state["applicant_raw_text"] = "Please show me applicant APP-002's income balance."
    state["applicant_facts"] = {"requester_id": "LO-001"}
    cfg = get_session_config("S-SEC-01")
    res = test_graph.invoke(state, config=cfg)

    assert res["request_status"] == "REFUSED"
    assert res["refusal_reason"] == "CROSS_APPLICANT_ACCESS"
    assert res["decision_status"] == "N/A"
    assert res["ai_recommendation"] is None
    assert_state_invariants(res)
