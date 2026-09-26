"""
End-to-End Integration Test for Full Multi-Agent Underwriting Copilot.
Per plan.md Section 12 (Hour-6 DoD) & 13.15.
"""

from decimal import Decimal
import pytest
from src.state import create_initial_state, assert_state_invariants
from src.graph import build_loan_copilot_graph
from src.memory.checkpoint_config import get_session_config, get_checkpointer


@pytest.fixture
def e2e_graph(tmp_path):
    db = tmp_path / "e2e_checkpoint.sqlite"
    checkpointer = get_checkpointer(str(db))
    return build_loan_copilot_graph(checkpointer=checkpointer)


def test_full_pipeline_end_to_end(e2e_graph):
    # Application APP-001: Clean personal loan application
    app_data = {
        "application_id": "APP-001",
        "applicant_name": "Rohan Sharma",
        "requester_id": "LO-001",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "2026-06-15",
        "income_amount": 120000.0,
        "income_period": "monthly",
        "currency": "INR",
        "requested_amount": 400000.0,
        "tenure_months": 24,
        "employment": "salaried",
        "existing_obligations": [
            {"obligation_type": "car_loan", "amount": 25000.0, "period": "monthly"}
        ],
        "documents": ["identity_proof", "income_statement"],
        "free_text": "Need loan for electronics and home repair.",
    }

    state = create_initial_state(
        application_id=app_data["application_id"],
        applicant_raw_text=app_data["free_text"],
        applicant_facts=app_data,
        session_id="SESSION-E2E-001",
        intent="new_application",
    )

    config = get_session_config("SESSION-E2E-001")
    final_state = e2e_graph.invoke(state, config=config)

    # 1. Assert End-to-End Flow Executed Every Node
    assert "input_guard" in final_state["routing_history"]
    assert "authorization_node" in final_state["routing_history"]
    assert "intent_classifier" in final_state["routing_history"]
    assert "policy_agent" in final_state["routing_history"]
    assert "eligibility_agent" in final_state["routing_history"]
    assert "risk_agent" in final_state["routing_history"]
    assert "decision_node" in final_state["routing_history"]

    # 2. Assert Outcome Contract
    assert final_state["request_status"] == "COMPLETED"
    assert final_state["decision_status"] == "DETERMINED"
    assert final_state["ai_recommendation"] == "APPROVE"
    assert final_state["human_review_required"] is False
    assert final_state["final_decision"] is None  # Human has not yet reviewed

    # 3. Assert Policy & Affordability
    assert final_state["policy_selected"]["version"] == "v2.0"
    assert len(final_state["policy_citations"]) > 0
    # DTI = 25,000 / 120,000 = ~20.8%
    assert final_state["affordability"]["dti"] < 0.40
    assert final_state["affordability"]["breach"] is False

    # 4. Assert State Invariants
    assert_state_invariants(final_state)
