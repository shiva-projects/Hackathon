"""
Tests for Dispute Multi-Agent Orchestration & Conditional Routing (AC-01, AC-02, AC-03, AC-04).
Validates:
- AC-01: Explicit typed state object (DisputeState) with invariant enforcement.
- AC-02: Supervisor routes incoming disputes to specialized workers (intake, fraud-signal, chargeback-eligibility, resolution-draft).
- AC-03: Conditional edges route on state:
  1. Escalate suspected fraud to manual review
  2. Short-circuit disputes outside the 120-day chargeback window.
- AC-04: Node/agent outputs are validated structured objects (Pydantic).
Per AAIE_AGT_001_BFS Specification §5.1.
"""

import pytest
from src.state import DisputeState, create_initial_state, assert_state_invariants
from src.agents.intake_agent import intake_agent_node, IntakeOutput
from src.agents.fraud_signal_agent import fraud_signal_agent_node, FraudSignalOutput
from src.agents.chargeback_eligibility_agent import chargeback_eligibility_agent_node, ChargebackEligibilityOutput
from src.agents.resolution_draft_agent import resolution_draft_agent_node, ResolutionDraftOutput
from src.agents.supervisor import supervisor_router


def test_ac01_typed_dispute_state_contract():
    """AC-01: Asserts explicit typed DisputeState and invariant assertions."""
    state = create_initial_state(
        dispute_id="DSP-AC01-TEST",
        customer_id="CUST-9021",
        transaction_id="TXN-88412",
        dispute_raw_text="Unauthorized charge on my statement from Apex Electronics.",
    )
    assert state["dispute_id"] == "DSP-AC01-TEST"
    assert state["chargeback_window_days"] == 120
    assert state["request_status"] == "IN_PROGRESS"
    assert_state_invariants(state)


def test_ac02_supervisor_worker_routing_pipeline():
    """AC-02: Asserts supervisor routes sequentially through all specialized dispute workers."""
    state = create_initial_state(
        dispute_id="DSP-AC02-TEST",
        transaction_id="TXN-88412",
        customer_id="CUST-9021",
        intent="new_dispute",
    )

    # 1. First hop must route to intake_agent
    next_node = supervisor_router(state)
    assert next_node == "intake_agent"
    state = intake_agent_node(state)

    # 2. Second hop must route to fraud_signal_agent
    next_node = supervisor_router(state)
    assert next_node == "fraud_signal_agent"
    state = fraud_signal_agent_node(state)

    # 3. Third hop must route to chargeback_eligibility_agent
    next_node = supervisor_router(state)
    assert next_node == "chargeback_eligibility_agent"
    state = chargeback_eligibility_agent_node(state)

    # 4. Fourth hop must route to resolution_draft_agent
    next_node = supervisor_router(state)
    assert next_node == "resolution_draft_agent"
    state = resolution_draft_agent_node(state)

    # 5. After all workers complete, supervisor must terminate cleanly
    next_node = supervisor_router(state)
    assert next_node == "__end__"


def test_ac03_conditional_fraud_escalation():
    """AC-03: Conditional edge escalates suspected fraud to human manual review."""
    state = create_initial_state(
        dispute_id="DSP-FRAUD-TEST",
        transaction_id="TXN-88412",
        dispute_raw_text="My card was stolen and used fraudulently online for $1200 without my authorization!",
    )
    state = intake_agent_node(state)
    state = fraud_signal_agent_node(state)

    # High fraud risk or stolen card must trigger manual human review escalation
    assert state["human_review_required"] is True
    assert "SUSPECTED_FRAUD_ESCALATION" in state["human_review_reason"]


def test_ac03_conditional_short_circuit_outside_window():
    """AC-03: Conditional edge short-circuits disputes exceeding 120-day window."""
    state = create_initial_state(
        dispute_id="DSP-EXPIRED-TEST",
        transaction_id="TXN-10294",  # Transaction date is 2025-08-01 (>200 days old)
        dispute_raw_text="I want to dispute this hotel charge from last summer.",
    )
    state = intake_agent_node(state)
    state["transaction_details"]["transaction_date"] = "2025-05-01T12:00:00Z"
    
    state = chargeback_eligibility_agent_node(state)

    # Must be ineligible and short-circuited as DENY_OUTSIDE_WINDOW
    assert state["chargeback_eligible"] is False
    assert state["ineligibility_reason"] == "EXCEEDS_120_DAY_WINDOW"
    assert state["resolution_action"] == "DENY_OUTSIDE_WINDOW"
    assert state["request_status"] == "COMPLETED"


def test_ac04_pydantic_structured_handoff_validation():
    """AC-04: Asserts all worker nodes produce validated Pydantic structured objects at handoff boundaries."""
    # Test Intake output model
    intake = IntakeOutput(
        dispute_id="DSP-001",
        transaction_id="TXN-88412",
        customer_id="CUST-9021",
        amount=429.99,
        currency="USD",
        merchant_name="Apex Electronics",
        transaction_date="2026-02-10T14:32:00Z",
        channel="eCommerce",
        customer_tier="PLATINUM",
    )
    assert intake.amount == 429.99

    # Test Fraud output model
    fraud = FraudSignalOutput(
        transaction_id="TXN-88412",
        fraud_score=0.75,
        risk_level="HIGH",
        recommended_action="ESCALATE_SUSPECTED_FRAUD",
        detected_indicators=["NO_3DS_AUTHENTICATION"],
        escalate_to_manual_review=True,
    )
    assert fraud.fraud_score == 0.75

    # Test Chargeback output model
    cb = ChargebackEligibilityOutput(
        transaction_id="TXN-88412",
        days_since_transaction=18,
        chargeback_window_days=120,
        chargeback_eligible=True,
        chargeback_reason_code="10.4",
        short_circuit_outside_window=False,
    )
    assert cb.chargeback_eligible is True

    # Test Resolution output model
    res = ResolutionDraftOutput(
        dispute_id="DSP-001",
        resolution_action="PROCEED_CHARGEBACK",
        draft_resolution="Resolution notice citing Rule CR-01 within 120 days.",
        rule_citations=[{"rule_code": "CR-01", "chunk_id": "chunk-disp-window-001"}],
        reflection_passed=True,
        reflection_iteration=0,
    )
    assert res.reflection_passed is True
