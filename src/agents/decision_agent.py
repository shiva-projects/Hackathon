"""
Underwriting Decision & Rationale Generation Node.
Combines deterministic rule results into ai_recommendation (SOLE WRITER: decisions.py),
then generates written rationale explaining the decision.
Per plan.md Section 3.2, 4.4, 14.6 & 14.17.
"""

import os
import time
from decimal import Decimal
from typing import Dict, Any, List
from src.state import LoanState, GEMINI_FALLBACK_RATIONALE
from src.domain.models import AffordabilityResult, RuleEvaluationResult
from src.domain.decisions import evaluate_underwriting_decision
from src.guardrails.output_guard import screen_output
from src.observability.unified_logger import log_agent_action, log_tool_call
from src.prompts import build_rationale_prompt

from src.llm.client import get_llm_client, invoke_with_resilience, ainvoke_with_resilience
from src.llm.provider_resolver import has_live_provider_key
from src.context.select import select_agent_context
from src.context.isolate import verify_context_isolation
from src.context.compress import compress_interaction_history


def generate_llm_rationale(
    recommendation: str,
    affordability: AffordabilityResult,
    reasons: List[str],
    policy_version: str,
    citations: List[Dict[str, Any]],
    run_id: str = "default_run",
) -> str:
    """
    Invokes the resolved LLM provider synchronously to explain the deterministic decision in prose.
    Delegates to agenerate_llm_rationale to maintain a single source of truth without code duplication.
    """
    from mcp_server.client import _run_coroutine_sync
    return _run_coroutine_sync(
        agenerate_llm_rationale(
            recommendation=recommendation,
            affordability=affordability,
            reasons=reasons,
            policy_version=policy_version,
            citations=citations,
            run_id=run_id,
        )
    )


async def agenerate_llm_rationale(
    recommendation: str,
    affordability: AffordabilityResult,
    reasons: List[str],
    policy_version: str,
    citations: List[Dict[str, Any]],
    run_id: str = "default_run",
) -> str:
    """
    Asynchronously invokes the resolved LLM provider to explain the deterministic decision in prose.
    Tests that need to intercept this call should mock `ainvoke_with_resilience` directly.
    """
    has_live_key = has_live_provider_key()
    if not has_live_key:
        rule_citations = ", ".join([c.get("rule_id", "PL-07") for c in citations]) or "PL-07"
        return (
            f"AI recommendation: {recommendation}. "
            f"Based on policy {policy_version} ({rule_citations}), the applicant's DTI is {float(affordability.dti):.1%}. "
            + " ".join(reasons)
        )

    try:
        prompt = build_rationale_prompt(
            recommendation=recommendation,
            policy_version=policy_version,
            dti=affordability.dti,
            breach=affordability.breach,
            reasons=reasons,
        )
        return await ainvoke_with_resilience(prompt, run_id=run_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Async LLM rationale generation failed ({e}), using deterministic fallback.")
        return GEMINI_FALLBACK_RATIONALE



async def adecision_agent_node(state: LoanState) -> LoanState:
    """
    Async LangGraph node: Evaluates deterministic decision and attaches rationale via async LLM call.
    """
    start_t = time.time()

    # 0. Context engineering: Select and isolate agent context
    agent_ctx = select_agent_context("rationale_agent", state)
    if not verify_context_isolation(agent_ctx):
        raise RuntimeError("Context isolation breach in rationale_agent")

    aff_dict = state.get("affordability", {})
    affordability = AffordabilityResult(
        dti=Decimal(str(aff_dict.get("dti", "0.0"))),
        disposable_income=Decimal(str(aff_dict.get("disposable_income", "0.0"))),
        breach=bool(aff_dict.get("breach", False)),
        threshold=Decimal(str(aff_dict.get("threshold", "0.40"))) if aff_dict.get("threshold") is not None else None,
        monthly_gross_income=Decimal(str(aff_dict.get("monthly_gross_income", "0.0"))),
        monthly_obligations=Decimal(str(aff_dict.get("monthly_obligations", "0.0"))),
    )

    raw_rules = state.get("rule_evaluations", []) or state.get("_rule_results", [])
    rule_results = [RuleEvaluationResult(**r) if isinstance(r, dict) else r for r in raw_rules]
    risk_flags = state.get("risk_flags", [])

    # 1. Deterministic Decision Engine (SOLE WRITER of ai_recommendation)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)

    state["ai_recommendation"] = decision.ai_recommendation
    state["decision_status"] = decision.decision_status
    state["unable_reason"] = decision.unable_reason
    state["human_review_required"] = decision.human_review_required
    state["request_status"] = "COMPLETED"

    # 2. Async Rationale generation explaining the decision
    policy_ver = state.get("policy_selected", {}).get("version", "v2.0")
    citations = state.get("policy_citations", [])
    raw_rationale = await agenerate_llm_rationale(
        recommendation=decision.ai_recommendation or "REFER",
        affordability=affordability,
        reasons=decision.reasons,
        policy_version=policy_ver,
        citations=citations,
        run_id=state.get("session_id", "default_run"),
    )

    # 3. Output Guardrail (PII scrub + recommendation language + numeric consistency enforcement)
    clean_rationale = screen_output(
        rationale=raw_rationale,
        ai_recommendation=decision.ai_recommendation,
        dti=affordability.dti,
    )
    state["rationale"] = clean_rationale
    state["routing_history"].append("decision_node")
    state["step_count"] += 1

    # 4. Long-term memory integration: LangMem manage_memory tool binding and verified attribute storage
    from src.memory.long_term import long_term_memory
    app_id = state.get("application_id", "APP-UNKNOWN")
    langmem_tool = long_term_memory.get_langmem_tool(app_id, "profile")
    if langmem_tool is not None:
        state["_langmem_tool"] = getattr(langmem_tool, "name", "manage_memory")
        log_tool_call(
            agent="decision_agent",
            tool_name=getattr(langmem_tool, "name", "manage_memory"),
            args={"namespace": f"{app_id}:profile"},
            result={"status": "bound"},
            latency_ms=0.1,
            status="success",
            application_id=app_id,
            run_id=state.get("session_id", "default_run"),
        )
        # Exercise the LangMem manage_memory tool to decide what to remember
        invocation_result = langmem_tool.invoke(state.get("applicant_facts", {}))
        log_tool_call(
            agent="decision_agent",
            tool_name=getattr(langmem_tool, "name", "manage_memory"),
            args={"facts": state.get("applicant_facts", {})},
            result={"invocation": invocation_result},
            latency_ms=0.1,
            status="success",
            application_id=app_id,
            run_id=state.get("session_id", "default_run"),
        )
    # Persist verified applicant attributes per memory write policy
    applicant_facts = state.get("applicant_facts", {})
    if applicant_facts.get("employment_type"):
        long_term_memory.write_fact(app_id, "profile", "employment_type", applicant_facts["employment_type"])
    if applicant_facts.get("employer_name"):
        long_term_memory.write_fact(app_id, "profile", "employer_name", applicant_facts["employer_name"])
    elif applicant_facts.get("employer"):
        long_term_memory.write_fact(app_id, "profile", "employer_name", applicant_facts["employer"])
    if applicant_facts.get("preferred_currency"):
        long_term_memory.write_fact(app_id, "profile", "preferred_currency", applicant_facts["preferred_currency"])

    latency_ms = round((time.time() - start_t) * 1000.0, 2)

    log_agent_action(
        actor="decision_agent",
        action="underwriting_decision_rendered",
        tool="domain.decisions.evaluate_underwriting_decision",
        decision=str(decision.ai_recommendation),
        application_id=state.get("application_id"),
        latency_ms=latency_ms,
        details={
            "ai_recommendation": decision.ai_recommendation,
            "decision_status": decision.decision_status,
            "human_review_required": decision.human_review_required,
        },
    )
    return state


def decision_agent_node(state: LoanState) -> LoanState:
    """
    Synchronous entry point for tests/callers that directly execute the node.
    Thin wrapper delegating canonically to adecision_agent_node.
    """
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(adecision_agent_node(state))).result()
    else:
        return asyncio.run(adecision_agent_node(state))


def decision_agent_node_sync(state: LoanState) -> LoanState:
    """Explicit sync alias for decision_agent_node."""
    return decision_agent_node(state)
