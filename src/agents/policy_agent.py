"""
Policy Agent Worker Node.
Invokes deterministic policy selector and targeted RAG retrieval.
Per plan.md Section 4.2 & 7.1.
"""

import time
from src.state import LoanState
from src.policy.policy_selector import select_applicable_policy
from src.tools.rag_tool import retrieve_policy_chunks, aretrieve_policy_chunks
from mcp_server.client import MCPClient, MCPUnavailableError
from src.observability.unified_logger import log_agent_action
from src.context.select import select_agent_context
from src.context.isolate import verify_context_isolation
from src.resilience.fallback import handle_mcp_failure


async def apolicy_agent_node(state: LoanState) -> LoanState:
    """
    Async LangGraph node: Selects current applicable policy, fetches document via MCP,
    and retrieves relevant chunks asynchronously via targeted RAG.
    """
    start_t = time.time()
    effective_run_id = state.get("run_id")
    if not effective_run_id or effective_run_id in {"default_run", "RUN-MCP", "RUN-UNKNOWN"}:
        raise ValueError("policy_agent requires canonical run_id in state")

    # 0. Context engineering: Select and isolate agent context
    agent_ctx = select_agent_context("policy_agent", state)
    if not verify_context_isolation(agent_ctx):
        raise RuntimeError("Context isolation breach in policy_agent")

    facts = state.get("applicant_facts", {})
    product = facts.get("product", "personal_loan")
    jurisdiction = facts.get("jurisdiction", "IN")
    app_date = facts.get("application_date", "2026-01-01")

    # 1. Deterministic policy selection
    selection = select_applicable_policy(product, jurisdiction, app_date)

    if not selection.is_success:
        state["decision_status"] = "UNABLE_TO_COMPLETE"
        state["unable_reason"] = selection.reason or "POLICY_UNAVAILABLE"
        state["human_review_required"] = True
        state["request_status"] = "COMPLETED"
        state["routing_history"].append("policy_agent_error")
        return state

    selected_policy = selection.policy
    state["policy_selected"] = selected_policy

    # 2. Async MCP Tool call: fetch authoritative policy document
    try:
        await MCPClient.acall_get_policy_document(
            policy_id=selected_policy["policy_id"],
            version=selected_policy["version"],
            run_id=effective_run_id,
            step_id="step-mcp-get-policy-document",
            application_id=state.get("application_id"),
        )
    except (MCPUnavailableError, Exception) as exc:
        state["routing_history"].append("policy_agent_error")
        return handle_mcp_failure(
            state,
            error_message=f"MCP policy document fetch failed: {exc}",
            run_id=effective_run_id,
        )

    # 3. Async Targeted RAG retrieval within selected policy only
    query = f"{product} affordability DTI loan limits documents"
    citations = await aretrieve_policy_chunks(
        query=query,
        selected_policy=selected_policy,
        top_k=3,
        run_id=effective_run_id,
    )
    state["policy_citations"] = citations
    state["routing_history"].append("policy_agent")
    state["step_count"] += 1

    latency_ms = round((time.time() - start_t) * 1000.0, 2)

    log_agent_action(
        actor="policy_agent",
        action="selected_policy_and_citations",
        tool="policy_selector",
        decision=selected_policy["version"],
        run_id=effective_run_id,
        application_id=state.get("application_id"),
        latency_ms=latency_ms,
        details={"policy_id": selected_policy["policy_id"], "version": selected_policy["version"]},
    )
    if state.get("intent") == "policy_question":
        state["request_status"] = "COMPLETED"
        state["rationale"] = (
            f"Policy {selected_policy.get('version')} retrieved. "
            f"Found {len(citations)} relevant policy rules."
        )

    return state


def policy_agent_node(state: LoanState) -> LoanState:
    """Synchronous entry point for tests/legacy callers."""
    import asyncio
    return asyncio.run(apolicy_agent_node(state))


def policy_agent_node_sync(state: LoanState) -> LoanState:
    """Explicit synchronous alias for policy_agent_node."""
    return policy_agent_node(state)
