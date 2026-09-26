"""
LangGraph Multi-Agent Architecture for Loan Origination & Underwriting Copilot.
Per plan.md Section 4.1, 7.1, 7.2 & AC-01..AC-06.
Full Phoenix tracing instrumentation & load-bearing Supervisor orchestration.
"""

import time
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from src.state import LoanState, assert_state_invariants
from src.guardrails.input_guard import screen_input
from src.security.authorization import authorize
from src.agents.intent_classifier import intent_classifier_node
from src.agents.supervisor import supervisor_router
from src.agents.clarification import clarification_node
from src.agents.policy_agent import policy_agent_node, apolicy_agent_node
from src.agents.eligibility_agent import eligibility_agent_node, aeligibility_agent_node
from src.agents.risk_agent import risk_agent_node, arisk_agent_node
from src.agents.decision_agent import decision_agent_node, adecision_agent_node
from src.memory.checkpoint_config import get_checkpointer
from src.observability.tracing import tracer, traced_node
from src.observability.unified_logger import log_agent_action


async def input_guard_node(state: LoanState) -> LoanState:
    """Entry node: Screens input for prompt injection and isolates raw text."""
    start_t = time.time()
    raw_text = state.get("applicant_raw_text", "")
    app_id = state.get("application_id", "APP-UNKNOWN")
    guard_result = screen_input(raw_text, current_application_id=app_id)

    state["routing_history"].append("input_guard")
    state["step_count"] += 1

    if not guard_result.is_safe:
        state["request_status"] = "REFUSED"
        state["refusal_reason"] = guard_result.rejection_reason or "SECURITY_SENSITIVE_REQUEST"
        state["decision_status"] = "N/A"
        state["ai_recommendation"] = None
        state["final_decision"] = None
        state["rationale"] = f"Request refused: {state['refusal_reason']}."
    return state


async def authorization_node(state: LoanState) -> LoanState:
    """Security node: Enforces access control boundaries."""
    start_t = time.time()
    state["routing_history"].append("authorization_node")
    state["step_count"] += 1

    if state.get("request_status") == "REFUSED":
        return state

    requester_id = state.get("actor_id") or state.get("applicant_facts", {}).get("requester_id") or state.get("application_id", "")
    app_id = state.get("application_id", "")

    auth_status = authorize(requester_id, app_id, run_id=state.get("session_id", "default_run"))
    if auth_status != "AUTHORIZED":
        state["request_status"] = "REFUSED"
        state["refusal_reason"] = "AUTHORIZATION_DENIED"
        state["decision_status"] = "N/A"
        state["ai_recommendation"] = None
        state["final_decision"] = None
        state["rationale"] = f"Access denied: Requester '{requester_id}' is unauthorized for application '{app_id}'."
    return state


async def supervisor_node(state: LoanState) -> LoanState:
    """Supervisor coordinator node: central dispatch point for multi-agent execution."""
    start_t = time.time()

    # On clarification resume: clear the flag so routing continues to underwriting pipeline.
    # Also reset step_count — turn-1 steps must not consume the turn-2 loop guard budget.
    if state.get("clarification_needed") and state.get("clarification_response"):
        state["clarification_needed"] = False
        state["step_count"] = 0

    state["routing_history"].append("supervisor")
    state["step_count"] += 1

    latency_ms = round((time.time() - start_t) * 1000.0, 2)

    log_agent_action(
        actor="supervisor",
        action="supervisor_dispatch",
        tool="supervisor_router",
        decision=state.get("intent", "new_application"),
        application_id=state.get("application_id"),
        latency_ms=latency_ms,
        details={"step_count": state.get("step_count"), "intent": state.get("intent")},
    )
    return state


async def status_node(state: LoanState) -> LoanState:
    """Handles status_check intent without modifying decision fields."""
    state["routing_history"].append("status_node")
    state["step_count"] += 1
    state["request_status"] = "COMPLETED"
    app_id = state.get("application_id")
    state["rationale"] = f"Application {app_id} is currently in state {state.get('request_status')} with review status {state.get('human_review_required')}."
    return state


async def document_node(state: LoanState) -> LoanState:
    """Handles document_question intent without evaluating decisions."""
    state["routing_history"].append("document_node")
    state["step_count"] += 1
    state["request_status"] = "COMPLETED"
    state["rationale"] = (
        "Standard documentation required under retail lending policies includes "
        "verified identity proof (Aadhaar/PAN) and 6 months of bank income statements."
    )
    return state


async def refusal_node(state: LoanState) -> LoanState:
    """Terminal node for out_of_scope or security refusals."""
    state["routing_history"].append("refusal_node")
    state["step_count"] += 1
    state["request_status"] = "REFUSED"
    if not state.get("refusal_reason"):
        state["refusal_reason"] = "OUT_OF_SCOPE"
    state["decision_status"] = "N/A"
    state["ai_recommendation"] = None
    state["final_decision"] = None
    state["rationale"] = f"Request refused: {state.get('refusal_reason', 'OUT_OF_SCOPE')}."
    return state


# Routing conditionals
def route_after_input_guard(state: LoanState) -> str:
    if state.get("request_status") == "REFUSED":
        return "refusal_node"
    return "authorization_node"


def route_after_authorization(state: LoanState) -> str:
    if state.get("request_status") == "REFUSED":
        return "refusal_node"
    return "intent_classifier"


def route_from_supervisor(state: LoanState) -> str:
    """Routes execution from supervisor to worker or termination."""
    # Loop/cascade guard (plan.md Section 8)
    if state.get("step_count", 0) >= 15:
        state["decision_status"] = "UNABLE_TO_COMPLETE"
        state["unable_reason"] = "RECURSION_LIMIT_EXCEEDED"
        return END

    target = supervisor_router(state)
    if target == "__end__":
        return END
    return target


def route_after_intent(state: LoanState) -> str:
    """Delegates directly to supervisor routing per Section 3.3 & plan.md Section 8."""
    return route_from_supervisor(state)


def route_after_policy(state: LoanState) -> str:
    if state.get("decision_status") == "UNABLE_TO_COMPLETE":
        return END
    # If this was only a policy question, end after policy retrieval
    if state.get("intent") == "policy_question":
        state["request_status"] = "COMPLETED"
        state["rationale"] = (
            f"Policy {state.get('policy_selected', {}).get('version')} retrieved. "
            f"Found {len(state.get('policy_citations', []))} relevant policy rules."
        )
        return END
    return "supervisor"


def build_loan_copilot_graph(checkpointer: Any = None) -> StateGraph:
    """Assembles and compiles the full LangGraph loan copilot state graph with Phoenix tracing."""
    # Initialize Phoenix instrumentation
    tracer.initialize()

    workflow = StateGraph(LoanState)

    # ── Fully Async Multi-Agent Pipeline Nodes (NFR-04) ──────────────────────
    # Every node in the execution graph is natively async (async def), dispatching
    # async MCP tools, async RAG retrievers, and async LLM calls with full
    # tracing. Each node also provides a synchronous wrapper (*_node / *_node_sync)
    # for legacy callers and unit testing.
    workflow.add_node("input_guard", traced_node("input_guard", "acting", input_guard_node))
    workflow.add_node("authorization_node", traced_node("authorization_node", "acting", authorization_node))
    workflow.add_node("intent_classifier", traced_node("intent_classifier", "thinking", intent_classifier_node))
    workflow.add_node("supervisor", traced_node("supervisor", "acting", supervisor_node))
    workflow.add_node("clarification_node", traced_node("clarification_node", "acting", clarification_node))
    workflow.add_node("status_node", traced_node("status_node", "acting", status_node))
    workflow.add_node("document_node", traced_node("document_node", "acting", document_node))
    workflow.add_node("refusal_node", traced_node("refusal_node", "acting", refusal_node))
    workflow.add_node("policy_agent", traced_node("policy_agent", "acting", apolicy_agent_node))
    workflow.add_node("eligibility_agent", traced_node("eligibility_agent", "acting", aeligibility_agent_node))
    workflow.add_node("risk_agent", traced_node("risk_agent", "acting", arisk_agent_node))
    workflow.add_node("decision_node", traced_node("decision_node", "acting", adecision_agent_node))

    # Set entry point
    workflow.set_entry_point("input_guard")

    # Connect edges
    workflow.add_conditional_edges("input_guard", route_after_input_guard, ["authorization_node", "refusal_node"])
    workflow.add_conditional_edges("authorization_node", route_after_authorization, ["intent_classifier", "refusal_node"])
    workflow.add_edge("intent_classifier", "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        [
            "clarification_node",
            "refusal_node",
            "status_node",
            "document_node",
            "policy_agent",
            "eligibility_agent",
            "risk_agent",
            "decision_node",
            END,
        ],
    )

    workflow.add_edge("clarification_node", END)
    workflow.add_edge("status_node", END)
    workflow.add_edge("document_node", END)
    workflow.add_edge("refusal_node", END)

    workflow.add_conditional_edges("policy_agent", route_after_policy, ["supervisor", END])
    workflow.add_edge("eligibility_agent", "supervisor")
    workflow.add_edge("risk_agent", "supervisor")
    workflow.add_edge("decision_node", "supervisor")

    if checkpointer is None:
        checkpointer = get_checkpointer()

    return workflow.compile(checkpointer=checkpointer)
