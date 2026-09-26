"""
Clarification Node for Ambiguous Requests.
Generates concrete follow-up questions without invoking underwriting or deciding cases.
Per plan.md Section 4.3.
"""

from src.state import LoanState
from src.observability.unified_logger import log_agent_action


def clarification_node(state: LoanState) -> LoanState:
    """
    LangGraph node: Asks applicant for clarification when intent is ambiguous.
    Sets clarification_needed=True and pauses underwriting with request_status=IN_PROGRESS.
    """
    question = (
        "I can assess loan eligibility, compute affordability (DTI), and screen credit risk. "
        "Please share your loan application details or provide an application ID to proceed."
    )

    state["clarification_needed"] = True
    state["clarification_question"] = question
    state["request_status"] = "IN_PROGRESS"
    state["decision_status"] = "N/A"
    state["ai_recommendation"] = None
    state["routing_history"].append("clarification_node")
    state["step_count"] += 1

    log_agent_action(
        actor="clarification_node",
        action="request_clarification",
        tool=None,
        decision="AWAITING_CLARIFICATION",
        application_id=state.get("application_id"),
        details={"question": question},
    )
    return state
