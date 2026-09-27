"""
DisputeState TypedDict and state invariants for Transaction Dispute & Fraud Triage Copilot.
Conforms strictly to AAIE_AGT_001_BFS Specification §5.1 (AC-01, AC-02, AC-03, AC-04).
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal

GEMINI_FALLBACK_RATIONALE = (
    "Resolution drafting model was temporarily unavailable. The recommendation below "
    "was produced deterministically from card network dispute rules and chargeback eligibility calculations."
)

VALID_INTENTS = {
    "new_dispute",
    "status_check",
    "dispute_inquiry",
    "document_question",
    "ambiguous",
    "out_of_scope",
    "security_sensitive",
    # Legacy alias
    "new_application",
    "policy_question",
}

VALID_REQUEST_STATUSES = {"IN_PROGRESS", "COMPLETED", "REFUSED", "ESCALATED"}
VALID_DECISION_STATUSES = {"DETERMINED", "UNABLE_TO_COMPLETE", "N/A"}
VALID_RESOLUTION_ACTIONS = {
    "PROCEED_CHARGEBACK",
    "MERCHANT_DIRECT_REFUND",
    "DENY_OUTSIDE_WINDOW",
    "ESCALATE_TO_HUMAN",
    "REQUEST_DOCUMENTATION",
    "APPROVE",
    "REFER",
    "DECLINE",
    None,
}


class DisputeState(TypedDict):
    """
    Typed graph state shared across all nodes in the dispute triage system.
    Satisfies AC-01 (explicit typed state contract).
    """
    dispute_id: str
    customer_id: str
    transaction_id: str
    dispute_raw_text: str             # Untrusted customer complaint: quarantined, never treated as instructions (NFR-03)
    session_id: str
    intent: str                       # new_dispute | status_check | dispute_inquiry | ambiguous | out_of_scope | security_sensitive
    clarification_needed: bool
    clarification_question: Optional[str]
    clarification_response: Optional[str]
    request_status: str               # IN_PROGRESS | COMPLETED | REFUSED | ESCALATED
    refusal_reason: Optional[str]

    # Intake & Profile metadata (from MCP)
    transaction_details: Dict[str, Any]
    customer_profile: Dict[str, Any]

    # Fraud evaluation (from fraud_signal_agent)
    fraud_signals: List[Dict[str, Any]]
    fraud_risk_score: float           # 0.0 - 1.0
    fraud_risk_level: str             # LOW | MEDIUM | HIGH | CRITICAL

    # Chargeback eligibility (from chargeback_eligibility_agent)
    chargeback_eligible: bool
    chargeback_window_days: int       # default 120 days
    days_since_transaction: int
    chargeback_reason_code: Optional[str]
    ineligibility_reason: Optional[str]

    # Agentic RAG citations & Resolution draft
    retrieved_rules: List[Dict[str, Any]]
    rule_citations: List[Dict[str, Any]]
    resolution_draft: str
    resolution_action: Optional[str]

    # Reflection & Self-Healing Loop (AC-12)
    reflection_feedback: Optional[str]
    reflection_iteration: int
    reflection_passed: bool

    # Human oversight & Audit trail
    human_review_required: bool
    human_review_reason: Optional[str]
    final_decision: Optional[str]     # null until a human sets it — NEVER set by the AI agent
    review_id: Optional[str]
    rationale: str
    routing_history: List[str]
    step_count: int

    # Backward compatibility aliases
    application_id: str
    applicant_raw_text: str
    applicant_facts: Dict[str, Any]
    policy_selected: Dict[str, Any]
    policy_citations: List[Dict[str, Any]]
    affordability: Dict[str, Any]
    risk_flags: List[Dict[str, Any]]
    ai_recommendation: Optional[str]
    decision_status: str
    unable_reason: Optional[str]


# Backward compatible alias for legacy imports
LoanState = DisputeState


def create_initial_state(
    dispute_id: str = "DSP-2026-001",
    dispute_raw_text: str = "",
    customer_id: str = "CUST-9021",
    transaction_id: str = "TXN-88412",
    session_id: str = "default-dispute-session",
    intent: str = "new_dispute",
    # Legacy parameter support
    application_id: Optional[str] = None,
    applicant_raw_text: Optional[str] = None,
    applicant_facts: Optional[Dict[str, Any]] = None,
) -> DisputeState:
    """Helper to initialize a clean DisputeState with complete defaults."""
    actual_dispute_id = application_id or dispute_id
    actual_raw_text = applicant_raw_text if applicant_raw_text is not None else dispute_raw_text

    return DisputeState(
        dispute_id=actual_dispute_id,
        customer_id=customer_id,
        transaction_id=transaction_id,
        dispute_raw_text=actual_raw_text,
        session_id=session_id,
        intent=intent,
        clarification_needed=False,
        clarification_question=None,
        clarification_response=None,
        request_status="IN_PROGRESS",
        refusal_reason=None,
        transaction_details={},
        customer_profile={},
        fraud_signals=[],
        fraud_risk_score=0.0,
        fraud_risk_level="LOW",
        chargeback_eligible=False,
        chargeback_window_days=120,
        days_since_transaction=0,
        chargeback_reason_code=None,
        ineligibility_reason=None,
        retrieved_rules=[],
        rule_citations=[],
        resolution_draft="",
        resolution_action=None,
        reflection_feedback=None,
        reflection_iteration=0,
        reflection_passed=False,
        human_review_required=False,
        human_review_reason=None,
        final_decision=None,
        review_id=None,
        rationale="",
        routing_history=[],
        step_count=0,
        # Legacy aliases
        application_id=actual_dispute_id,
        applicant_raw_text=actual_raw_text,
        applicant_facts=applicant_facts or {},
        policy_selected={},
        policy_citations=[],
        affordability={},
        risk_flags=[],
        ai_recommendation=None,
        decision_status="N/A",
        unable_reason=None,
    )


def assert_state_invariants(state: DisputeState) -> None:
    """
    Validates state contract invariants (AC-01 & AC-04).
    Raises AssertionError on contract violations.
    """
    request_status = state.get("request_status")
    assert request_status in VALID_REQUEST_STATUSES, f"Invalid request_status: {request_status}"

    decision_status = state.get("decision_status")
    if decision_status is not None:
        assert decision_status in VALID_DECISION_STATUSES, f"Invalid decision_status: {decision_status}"

    ai_rec = state.get("ai_recommendation")
    final_dec = state.get("final_decision")

    # Contract 1: Request refused / escalated
    if request_status == "REFUSED":
        assert state.get("refusal_reason") is not None, "REFUSED state requires a non-null refusal_reason"
        assert decision_status == "N/A", f"REFUSED state requires decision_status='N/A', got '{decision_status}'"
        assert ai_rec is None, f"REFUSED state must have ai_recommendation=None, got '{ai_rec}'"
        assert final_dec is None, f"REFUSED state must have final_decision=None, got '{final_dec}'"

    # Contract 2: Normal execution completed
    elif request_status == "COMPLETED":
        if decision_status == "DETERMINED":
            assert ai_rec in {"APPROVE", "REFER", "DECLINE"}, (
                f"DETERMINED decision requires ai_recommendation in APPROVE/REFER/DECLINE, got '{ai_rec}'"
            )
            assert state.get("unable_reason") is None, (
                f"DETERMINED decision must have unable_reason=None, got '{state.get('unable_reason')}'"
            )
        elif decision_status == "UNABLE_TO_COMPLETE":
            assert ai_rec is None, (
                f"UNABLE_TO_COMPLETE decision must have ai_recommendation=None, got '{ai_rec}'"
            )
            assert state.get("unable_reason") is not None, (
                "UNABLE_TO_COMPLETE requires a non-null unable_reason"
            )
            assert state.get("human_review_required") is True, (
                "UNABLE_TO_COMPLETE requires human_review_required=True"
            )
        elif decision_status == "N/A":
            assert ai_rec is None, f"COMPLETED with decision_status='N/A' requires ai_recommendation=None, got '{ai_rec}'"
            assert final_dec is None, f"COMPLETED with decision_status='N/A' requires final_decision=None, got '{final_dec}'"

    # Contract 3: In progress / awaiting clarification
    elif request_status == "IN_PROGRESS":
        if state.get("clarification_needed"):
            assert state.get("clarification_question") is not None, (
                "clarification_needed=True requires clarification_question to be non-null"
            )

    # Contract 4: Human review link integrity
    if final_dec is not None:
        assert state.get("review_id") is not None, (
            "final_decision is set but review_id is missing (violates human audit link)"
        )

    # Invariant: step count cannot exceed safe recursion ceiling
    assert state.get("step_count", 0) <= 25, f"Step count exceeded recursion limit: {state.get('step_count')}"
