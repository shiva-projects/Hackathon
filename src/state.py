"""
LoanState TypedDict and state invariants for BC-AAIE-HACK-02.
Frozen architecture per plan.md v7.
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal


GEMINI_FALLBACK_RATIONALE = (
    "Rationale generation was unavailable. The recommendation below was produced "
    "entirely from the selected policy and deterministic underwriting rules."
)

VALID_INTENTS = {
    "new_application",
    "status_check",
    "document_question",
    "policy_question",
    "ambiguous",
    "out_of_scope",
    "security_sensitive",
}

VALID_REQUEST_STATUSES = {"IN_PROGRESS", "COMPLETED", "REFUSED"}
VALID_DECISION_STATUSES = {"DETERMINED", "UNABLE_TO_COMPLETE", "N/A"}
VALID_RECOMMENDATIONS = {"APPROVE", "REFER", "DECLINE", None}
VALID_FINAL_DECISIONS = {"APPROVE", "REFER", "DECLINE", None}


class LoanState(TypedDict):
    application_id: str
    applicant_raw_text: str            # untrusted, quarantined, never used as instructions
    applicant_facts: Dict[str, Any]    # extracted + schema-validated
    session_id: str
    intent: str                        # new_application | status_check | document_question |
                                       # policy_question | ambiguous | out_of_scope | security_sensitive
    clarification_needed: bool
    clarification_question: Optional[str]  # the concrete follow-up question shown to applicant
    clarification_response: Optional[str]  # the applicant's reply on --resume-session
    request_status: str                # "IN_PROGRESS" | "COMPLETED" | "REFUSED"
    refusal_reason: Optional[str]      # "CROSS_APPLICANT_ACCESS", "SECURITY_SENSITIVE_REQUEST", "OUT_OF_SCOPE", "AUTHORIZATION_DENIED"
    policy_selected: Dict[str, Any]    # {policy_id, version, effective_from, effective_to, product, jurisdiction}
    policy_citations: List[Dict[str, Any]]  # [{policy_id, version, rule_id, source_file, chunk_id, text_hash}]
    affordability: Dict[str, Any]      # deterministic: {dti, disposable_income, breach, threshold}
    risk_flags: List[Dict[str, Any]]   # deterministic rule outputs
    rule_evaluations: List[Dict[str, Any]]  # deterministic rule evaluations
    ai_recommendation: Optional[str]   # "APPROVE" | "REFER" | "DECLINE" | None — AI ONLY, never final
    decision_status: str               # "DETERMINED" | "UNABLE_TO_COMPLETE" | "N/A"
    unable_reason: Optional[str]       # "POLICY_UNAVAILABLE", "MCP_UNAVAILABLE", etc.
    human_review_required: bool
    final_decision: Optional[str]      # null until a human sets it — NEVER set by the agent
    review_id: Optional[str]           # links to the record in logs/human_reviews.jsonl
    rationale: str                     # LLM explains the deterministic result; does not invent it
    routing_history: List[str]
    step_count: int


def create_initial_state(
    application_id: str,
    applicant_raw_text: str = "",
    applicant_facts: Optional[Dict[str, Any]] = None,
    session_id: str = "default-session",
    intent: str = "new_application",
) -> LoanState:
    """Helper to initialize a clean LoanState."""
    return LoanState(
        application_id=application_id,
        applicant_raw_text=applicant_raw_text,
        applicant_facts=applicant_facts or {},
        session_id=session_id,
        intent=intent,
        clarification_needed=False,
        clarification_question=None,
        clarification_response=None,
        request_status="IN_PROGRESS",
        refusal_reason=None,
        policy_selected={},
        policy_citations=[],
        affordability={},
        risk_flags=[],
        rule_evaluations=[],
        ai_recommendation=None,
        decision_status="N/A",
        unable_reason=None,
        human_review_required=False,
        final_decision=None,
        review_id=None,
        rationale="",
        routing_history=[],
        step_count=0,
    )


def assert_state_invariants(state: LoanState) -> None:
    """
    Validates state contract invariants (Section 3.1 & 3.4 of plan.md).
    Raises AssertionError on contract violations.
    """
    request_status = state.get("request_status")
    assert request_status in VALID_REQUEST_STATUSES, f"Invalid request_status: {request_status}"

    decision_status = state.get("decision_status")
    assert decision_status in VALID_DECISION_STATUSES, f"Invalid decision_status: {decision_status}"

    ai_rec = state.get("ai_recommendation")
    final_dec = state.get("final_decision")

    # Contract 1: Request refused / escalated
    if request_status == "REFUSED":
        assert state.get("refusal_reason") is not None, "REFUSED state requires a non-null refusal_reason"
        assert decision_status == "N/A", f"REFUSED state requires decision_status='N/A', got '{decision_status}'"
        assert ai_rec is None, f"REFUSED state must have ai_recommendation=None, got '{ai_rec}'"
        assert final_dec is None, f"REFUSED state must have final_decision=None, got '{final_dec}'"

    # Contract 2: Normal underwriting completed
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
        else:
            raise AssertionError(f"COMPLETED request cannot have decision_status='{decision_status}'")

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
