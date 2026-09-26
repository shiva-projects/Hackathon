"""
Underwriting Decision & Rationale Generation Node.
Combines deterministic rule results into ai_recommendation (SOLE WRITER: decisions.py),
then generates written rationale explaining the decision.
Per plan.md Section 3.2, 4.4, 14.6 & 14.17.
"""

import os
from decimal import Decimal
from typing import Dict, Any, List
from src.state import LoanState, GEMINI_FALLBACK_RATIONALE
from src.domain.models import AffordabilityResult, RuleEvaluationResult
from src.domain.decisions import evaluate_underwriting_decision
from src.guardrails.output_guard import screen_output
from src.observability.unified_logger import log_agent_action, log_tool_call


from src.llm.client import get_llm_client, invoke_with_resilience
from src.llm.provider_resolver import load_model_config, resolve_provider


def generate_llm_rationale(
    recommendation: str,
    affordability: AffordabilityResult,
    reasons: List[str],
    policy_version: str,
    citations: List[Dict[str, Any]],
    run_id: str = "default_run",
) -> str:
    """
    Invokes the resolved LLM provider (Gemini primary -> Groq fallback) to explain
    the deterministic decision in prose.
    Gracefully falls back to deterministic explanation or GEMINI_FALLBACK_RATIONALE.
    """
    # Check if a live provider key exists in the environment
    has_live_key = False
    try:
        cfg = load_model_config()
        provider_name, provider_cfg = resolve_provider(cfg)
        key_val = os.environ.get(provider_cfg.get("env_key", ""), "")
        if key_val and key_val not in ("your_gemini_api_key_here", "gsk_test_dummy", "test-key"):
            has_live_key = True
    except Exception:
        has_live_key = False

    # If no live API key is provided or offline mode, generate factual explanation directly
    if not has_live_key:
        rule_citations = ", ".join([c.get("rule_id", "PL-07") for c in citations]) or "PL-07"
        return (
            f"AI recommendation: {recommendation}. "
            f"Based on policy {policy_version} ({rule_citations}), the applicant's DTI is {float(affordability.dti):.1%}. "
            + " ".join(reasons)
        )

    try:
        prompt = (
            f"You are a loan underwriting assistant. Explain the following deterministic underwriting result:\n"
            f"Recommendation: {recommendation}\n"
            f"Policy Version: {policy_version}\n"
            f"DTI: {float(affordability.dti):.1%}\n"
            f"Breach Status: {affordability.breach}\n"
            f"Reasons: {'; '.join(reasons)}\n"
            f"Instructions: Write a clear 2-3 sentence explanation for the credit officer. "
            f"Do not alter the recommendation. Do not invent new figures."
        )

        return invoke_with_resilience(prompt, run_id=run_id)
    except Exception as e:
        # Per Section 14.17: Rationale generation failure falls back gracefully
        return GEMINI_FALLBACK_RATIONALE


def decision_agent_node(state: LoanState) -> LoanState:
    """
    LangGraph node: Evaluates deterministic decision and attaches rationale.
    """
    aff_dict = state.get("affordability", {})
    affordability = AffordabilityResult(
        dti=Decimal(str(aff_dict.get("dti", "0.0"))),
        disposable_income=Decimal(str(aff_dict.get("disposable_income", "0.0"))),
        breach=bool(aff_dict.get("breach", False)),
        threshold=Decimal(str(aff_dict.get("threshold", "0.40"))) if aff_dict.get("threshold") is not None else None,
        monthly_gross_income=Decimal(str(aff_dict.get("monthly_gross_income", "0.0"))),
        monthly_obligations=Decimal(str(aff_dict.get("monthly_obligations", "0.0"))),
    )

    raw_rules = state.get("rule_evaluations", [])
    rule_results = [RuleEvaluationResult(**r) for r in raw_rules]
    risk_flags = state.get("risk_flags", [])

    # 1. Deterministic Decision Engine (SOLE WRITER of ai_recommendation)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)

    state["ai_recommendation"] = decision.ai_recommendation
    state["decision_status"] = decision.decision_status
    state["unable_reason"] = decision.unable_reason
    state["human_review_required"] = decision.human_review_required
    state["request_status"] = "COMPLETED"

    # 2. Rationale generation explaining the decision
    policy_ver = state.get("policy_selected", {}).get("version", "v2.0")
    citations = state.get("policy_citations", [])
    raw_rationale = generate_llm_rationale(
        recommendation=decision.ai_recommendation or "REFER",
        affordability=affordability,
        reasons=decision.reasons,
        policy_version=policy_ver,
        citations=citations,
        run_id=state.get("session_id", "default_run"),
    )

    # 3. Output Guardrail (PII scrub + recommendation language enforcement)
    clean_rationale = screen_output(
        rationale=raw_rationale,
        ai_recommendation=decision.ai_recommendation,
    )
    state["rationale"] = clean_rationale
    state["routing_history"].append("decision_node")
    state["step_count"] += 1

    log_agent_action(
        actor="decision_agent",
        action="underwriting_decision_rendered",
        tool="domain.decisions.evaluate_underwriting_decision",
        decision=str(decision.ai_recommendation),
        application_id=state.get("application_id"),
        details={
            "ai_recommendation": decision.ai_recommendation,
            "decision_status": decision.decision_status,
            "human_review_required": decision.human_review_required,
        },
    )
    return state
