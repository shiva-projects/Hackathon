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
    yield build_loan_copilot_graph(checkpointer=checkpointer)
    checkpointer.close()


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
    # Must NOT run decision_node or compute new affordability
    state = create_initial_state("APP-001", session_id="S-STATUS-01")
    state["applicant_raw_text"] = "What is the status of my loan application?"
    state["applicant_facts"] = {"requester_id": "LO-001"}
    cfg = get_session_config("S-STATUS-01")
    final_state = test_graph.invoke(state, config=cfg)

    assert final_state["intent"] == "status_check"
    assert "status_node" in final_state["routing_history"]
    assert "decision_node" not in final_state["routing_history"]
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


def test_policy_question_with_structured_fields_remains_policy_question(test_graph):
    """Phase 7 Acceptance: 'What is the DTI policy?' remains policy_question even when structured fields exist."""
    state = create_initial_state("APP-001", session_id="S-POL-STRUCT-01")
    state["applicant_raw_text"] = "What is the DTI policy and maximum loan allowed?"
    # Incidental structured fields present in request payload:
    state["applicant_facts"] = {
        "requester_id": "LO-001",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "2026-03-01",
        "income_amount": 100000,
        "income_period": "monthly",
        "requested_amount": 500000,
        "tenure_months": 24,
        "employment": "salaried",
        "existing_obligations": [{"amount": 20000, "period": "monthly"}],
    }
    cfg = get_session_config("S-POL-STRUCT-01")
    final_state = test_graph.invoke(state, config=cfg)

    # Must route to policy_agent, not full underwriting
    assert final_state["intent"] == "policy_question"
    assert "policy_agent" in final_state["routing_history"]
    assert "decision_node" not in final_state["routing_history"]
    assert final_state["ai_recommendation"] is None
    assert final_state["affordability"] == {}


def test_malformed_llm_intent_output_handled_safely():
    """Phase 7: Malformed or unknown LLM intent output rejected by Pydantic model without crashing."""
    from src.agents.intent_classifier import parse_llm_intent_output

    # Malformed output
    res1 = parse_llm_intent_output("I think the user wants maybe_loan_or_something")
    assert res1 is None

    # Valid JSON output
    res2 = parse_llm_intent_output('{"intent": "policy_question", "reasoning": "User asked about DTI rules"}')
    assert res2 is not None
    assert res2.intent == "policy_question"

    # Valid direct token
    res3 = parse_llm_intent_output("status_check")
    assert res3 is not None
    assert res3.intent == "status_check"


def test_status_check_reads_stored_persisted_status(test_graph, tmp_path):
    """Phase 7 Acceptance: Status check reads existing persisted/checkpoint state."""
    import json
    from pathlib import Path
    from src.security.authorization import register_custom_application

    app_id = "TEST-APP-STORED-STATUS"
    register_custom_application(app_id, officer_id="LO-001")
    res_dir = Path("outputs/sample_results")
    res_dir.mkdir(parents=True, exist_ok=True)
    res_file = res_dir / f"{app_id}.json"

    # Seed stored result
    stored_result = {
        "application_id": app_id,
        "session_id": "SESSION-STORED-01",
        "run_id": "RUN-STORED-01",
        "request_status": "COMPLETED",
        "decision_status": "DETERMINED",
        "ai_recommendation": "REFER",
        "human_review_required": True,
        "final_decision": "APPROVE",
        "review_id": "REV-STORED-01",
    }
    with open(res_file, "w", encoding="utf-8") as f:
        json.dump(stored_result, f, indent=2)

    try:
        state = create_initial_state(app_id, session_id="S-STATUS-RETRIEVE")
        state["applicant_raw_text"] = "What is the status of my application?"
        state["applicant_facts"] = {"requester_id": "LO-001"}
        cfg = get_session_config("S-STATUS-RETRIEVE")
        final_state = test_graph.invoke(state, config=cfg)

        assert final_state["intent"] == "status_check"
        assert "status_node" in final_state["routing_history"]
        # Reads stored state:
        assert final_state["request_status"] == "COMPLETED"
        assert final_state["decision_status"] == "DETERMINED"
        assert final_state["ai_recommendation"] == "REFER"
        assert final_state["final_decision"] == "APPROVE"
        assert final_state["human_review_required"] is True
    finally:
        if res_file.exists():
            res_file.unlink()


def test_status_check_nonexistent_application_does_not_manufacture_completed(test_graph):
    """Phase 7: Status check for missing application does not manufacture COMPLETED state."""
    from src.security.authorization import register_custom_application
    app_id = "APP-NONEXISTENT-999"
    register_custom_application(app_id, officer_id="LO-001")

    state = create_initial_state(app_id, session_id="S-STATUS-MISSING")
    state["applicant_raw_text"] = "What is the status of my loan application?"
    state["applicant_facts"] = {"requester_id": "LO-001"}
    cfg = get_session_config("S-STATUS-MISSING")
    final_state = test_graph.invoke(state, config=cfg)

    assert final_state["intent"] == "status_check"
    assert "status_node" in final_state["routing_history"]
    # Does NOT manufacture COMPLETED:
    assert final_state["request_status"] != "COMPLETED"
    assert final_state["request_status"] == "IN_PROGRESS"
    assert final_state["ai_recommendation"] is None
