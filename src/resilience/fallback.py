"""
Graceful Degradation and Fallback Handlers.
Per plan.md Section 5, 14.7 & 14.17.
Enforces that:
1. MCP failures route to UNABLE_TO_COMPLETE with human_review_required=True.
2. Gemini outages preserve the deterministic recommendation with GEMINI_FALLBACK_RATIONALE.
"""

from typing import Dict, Any, Optional
from src.state import LoanState, GEMINI_FALLBACK_RATIONALE
from src.observability.unified_logger import log_agent_action


def handle_mcp_failure(state: LoanState, error_message: str, run_id: str = "default_run") -> LoanState:
    """
    Handles MCP tool outage gracefully (Section 14.7).
    Never defaults to REFER; sets UNABLE_TO_COMPLETE.
    """
    state["decision_status"] = "UNABLE_TO_COMPLETE"
    state["unable_reason"] = "MCP_UNAVAILABLE"
    state["ai_recommendation"] = None
    state["human_review_required"] = True
    state["request_status"] = "COMPLETED"

    log_agent_action(
        actor="resilience_fallback",
        action="mcp_failure_fallback",
        tool="mcp_tool",
        decision="UNABLE_TO_COMPLETE",
        run_id=run_id,
        application_id=state.get("application_id"),
        details={"error": error_message, "unable_reason": "MCP_UNAVAILABLE"},
    )
    return state


def handle_gemini_failure(state: LoanState, error_message: str, run_id: str = "default_run") -> LoanState:
    """
    Handles Gemini outage during rationale generation (Section 14.17).
    Deterministic recommendation survives; rationale set to exact named constant.
    """
    state["rationale"] = GEMINI_FALLBACK_RATIONALE
    # decision_status and ai_recommendation remain untouched from domain/decisions.py

    log_agent_action(
        actor="resilience_fallback",
        action="gemini_rationale_fallback",
        tool="gemini_model",
        decision="DEGRADED_RATIONALE",
        run_id=run_id,
        application_id=state.get("application_id"),
        details={"error": error_message, "fallback_applied": True},
    )
    return state
