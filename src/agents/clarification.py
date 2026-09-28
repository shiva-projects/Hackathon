"""
Clarification Node for Ambiguous Requests.
Generates concrete follow-up questions without invoking underwriting or deciding cases.
Per plan.md Section 4.3.
"""

import time
from src.state import LoanState
from src.observability.unified_logger import log_agent_action


async def clarification_node(state: LoanState) -> LoanState:
    """
    Async LangGraph node: Asks applicant for clarification when intent is ambiguous.
    Sets clarification_needed=True and pauses underwriting with request_status=IN_PROGRESS.
    """
    start_t = time.time()
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

    latency_ms = round((time.time() - start_t) * 1000.0, 2)
    effective_run_id = state.get("run_id") or state.get("session_id", "default_run")

    log_agent_action(
        actor="clarification_node",
        action="request_clarification",
        tool=None,
        decision="AWAITING_CLARIFICATION",
        run_id=effective_run_id,
        application_id=state.get("application_id"),
        latency_ms=latency_ms,
        details={"question": question},
    )
    return state


def clarification_node_sync(state: LoanState) -> LoanState:
    """Synchronous entry point for tests/legacy callers."""
    import asyncio
    return asyncio.run(clarification_node(state))
