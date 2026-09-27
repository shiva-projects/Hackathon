"""
Eligibility & Affordability Agent Worker Node.
Invokes MCP compute_affordability tool deterministically.
Per plan.md Section 4.4 & 4.5.
"""

import time
from src.state import LoanState
from mcp_server.client import MCPClient
from src.observability.unified_logger import log_agent_action
from src.context.select import select_agent_context
from src.context.isolate import verify_context_isolation
from src.context.write import write_verified_fact


async def aeligibility_agent_node(state: LoanState) -> LoanState:
    """
    Async LangGraph node: Computes DTI and disposable income via async MCP tool call.
    """
    start_t = time.time()

    # 0. Context engineering: Select and isolate agent context
    agent_ctx = select_agent_context("eligibility_agent", state)
    if not verify_context_isolation(agent_ctx):
        raise RuntimeError("Context isolation breach in eligibility_agent")

    facts = state.get("applicant_facts", {})
    income_amount = facts.get("income_amount", 0.0)
    income_period = facts.get("income_period", "monthly")
    existing_obligations = facts.get("existing_obligations", [])

    # Find DTI threshold from selected policy rules
    policy_selected = state.get("policy_selected", {})
    rules = policy_selected.get("rules", [])
    dti_rule = next((r for r in rules if r.get("rule_type") == "dti_max"), None)
    dti_max_threshold = float(dti_rule.get("value", 0.40)) if dti_rule else 0.40

    # Call async MCP tool
    aff_res = await MCPClient.acall_compute_affordability(
        income_amount=income_amount,
        income_period=income_period,
        existing_obligations=existing_obligations,
        dti_max_threshold=dti_max_threshold,
    )

    state["affordability"] = aff_res
    state["routing_history"].append("eligibility_agent")
    state["step_count"] += 1

    latency_ms = round((time.time() - start_t) * 1000.0, 2)

    log_agent_action(
        actor="eligibility_agent",
        action="computed_affordability",
        tool="mcp.compute_affordability",
        decision="BREACH" if aff_res.get("breach") else "PASS",
        application_id=state.get("application_id"),
        latency_ms=latency_ms,
        details={"dti": aff_res.get("dti"), "breach": aff_res.get("breach")},
    )
    return state


def eligibility_agent_node(state: LoanState) -> LoanState:
    """Synchronous entry point for tests/legacy callers."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(aeligibility_agent_node(state))).result()
    else:
        return asyncio.run(aeligibility_agent_node(state))


def eligibility_agent_node_sync(state: LoanState) -> LoanState:
    """Explicit synchronous alias for eligibility_agent_node."""
    return eligibility_agent_node(state)
