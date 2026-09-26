"""
Eligibility & Affordability Agent Worker Node.
Invokes MCP compute_affordability tool deterministically.
Per plan.md Section 4.4 & 4.5.
"""

from src.state import LoanState
from mcp_server.client import MCPClient
from src.observability.unified_logger import log_agent_action


def eligibility_agent_node(state: LoanState) -> LoanState:
    """
    LangGraph node: Computes DTI and disposable income via MCP tool.
    """
    facts = state.get("applicant_facts", {})
    income_amount = facts.get("income_amount", 0.0)
    income_period = facts.get("income_period", "monthly")
    existing_obligations = facts.get("existing_obligations", [])

    # Find DTI threshold from selected policy rules
    policy_selected = state.get("policy_selected", {})
    rules = policy_selected.get("rules", [])
    dti_rule = next((r for r in rules if r.get("rule_type") == "dti_max"), None)
    dti_max_threshold = float(dti_rule.get("value", 0.40)) if dti_rule else 0.40

    # Call MCP tool
    aff_res = MCPClient.call_compute_affordability(
        income_amount=income_amount,
        income_period=income_period,
        existing_obligations=existing_obligations,
        dti_max_threshold=dti_max_threshold,
    )

    state["affordability"] = aff_res
    state["routing_history"].append("eligibility_agent")
    state["step_count"] += 1

    log_agent_action(
        actor="eligibility_agent",
        action="computed_affordability",
        tool="mcp.compute_affordability",
        decision="BREACH" if aff_res.get("breach") else "PASS",
        application_id=state.get("application_id"),
        details={"dti": aff_res.get("dti"), "breach": aff_res.get("breach")},
    )
    return state
