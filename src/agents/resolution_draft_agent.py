"""
Resolution Draft Agent for Transaction Dispute & Fraud Triage Copilot.
Decides when to invoke agentic-RAG for dispute rules (AC-11), drafts resolution for human agent,
and executes a genuine post-draft reflection & self-healing critique loop (AC-12).
Per AAIE_AGT_001_BFS Specification §5.1 (AC-02, AC-04, AC-11, AC-12).
"""

import time
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from src.state import DisputeState, GEMINI_FALLBACK_RATIONALE
from src.tools.rag_tool import retrieve_dispute_rules
from src.observability.unified_logger import log_agent_action
from src.observability.tracing import tracer
from src.llm.provider_resolver import has_live_provider_key
from src.llm.client import invoke_with_resilience

logger = logging.getLogger(__name__)


class ResolutionDraftOutput(BaseModel):
    """Pydantic validated structured handoff object (AC-04)."""
    dispute_id: str
    resolution_action: str
    draft_resolution: str
    rule_citations: List[Dict[str, Any]]
    reflection_passed: bool
    reflection_iteration: int


def _critique_draft(
    draft: str,
    citations: List[Dict[str, Any]],
    eligible: bool,
    reason_code: Optional[str],
) -> Dict[str, Any]:
    """
    Self-critique evaluation (AC-12 Reflection Step):
    Checks whether the drafted resolution meets strict dispute governance standards.
    """
    issues = []
    
    # Check 1: Must cite at least one verified dispute rule or chunk hash
    if not citations and eligible:
        issues.append("MISSING_RULE_CITATION: Draft lacks mandatory card network dispute citations.")

    # Check 2: Must explicitly reference the 120-day timeframe
    if "120" not in draft and eligible:
        issues.append("OMITTED_TIMEFRAME: Draft fails to confirm compliance with the 120-day chargeback window.")

    # Check 3: If reason code is present, must cite reason code
    if reason_code and reason_code not in draft and eligible:
        issues.append(f"MISSING_REASON_CODE: Draft should explicitly cite reason code {reason_code}.")

    passed = len(issues) == 0
    feedback = "; ".join(issues) if issues else "CRITIQUE_PASSED: Draft satisfies all governance standards."
    return {"passed": passed, "feedback": feedback, "issues": issues}


def draft_resolution_prose(
    state: DisputeState,
    citations: List[Dict[str, Any]],
    run_id: str = "default_run",
) -> str:
    """Drafts human-readable resolution notice using LLM or deterministic template."""
    txn = state.get("transaction_details", {})
    amount = txn.get("amount", 0.0)
    merchant = txn.get("merchant_name", "the merchant")
    eligible = state.get("chargeback_eligible", False)
    reason_code = state.get("chargeback_reason_code", "13.1")
    days_since = state.get("days_since_transaction", 0)
    fraud_level = state.get("fraud_risk_level", "LOW")

    rule_refs = ", ".join([f"{c.get('rule_code', 'CR-01')} ({c.get('chunk_id')})" for c in citations]) or "CR-01 (120-Day Rule)"

    if not eligible:
        return (
            f"DISPUTE TRIAGE SUMMARY — CLAIM REJECTED\n"
            f"Transaction ID: {txn.get('transaction_id')}\n"
            f"Merchant: {merchant} (${amount:.2f})\n"
            f"Finding: Transaction was processed {days_since} days prior to dispute filing, "
            f"exceeding the 120-day card network filing deadline under Rule CR-01. "
            f"Chargeback rights are expired. Recommendation: DENIED_OUTSIDE_WINDOW."
        )

    # Eligible dispute drafting
    template = (
        f"DISPUTE TRIAGE RESOLUTION — READY FOR HUMAN REVIEW\n"
        f"Case ID: {state.get('dispute_id')} | Merchant: {merchant} | Amount: ${amount:.2f}\n"
        f"1. Chargeback Eligibility: ELIGIBLE ({days_since} days elapsed, within 120-day window per Rule CR-01).\n"
        f"2. Network Reason Code: {reason_code} based on customer dispute assertion and transaction characteristics.\n"
        f"3. Fraud Assessment: {fraud_level} risk score ({state.get('fraud_risk_score', 0.10):.2f}).\n"
        f"4. Governing Rule Citations: {rule_refs}.\n"
        f"5. Recommended Action: PROCEED_CHARGEBACK with acquirer; provide cardholder provisional credit."
    )

    if not has_live_provider_key():
        return template

    try:
        prompt = (
            "You are a professional bank dispute operations specialist.\n"
            "Draft a concise, professional dispute triage summary for a human dispute officer.\n"
            f"Details: Merchant={merchant}, Amount=${amount:.2f}, Days Elapsed={days_since}/120, "
            f"Reason Code={reason_code}, Fraud Level={fraud_level}, Governing Rules={rule_refs}.\n"
            "Include mandatory references to Reason Code and the 120-day window.\n"
            "Draft:"
        )
        llm_draft = invoke_with_resilience(prompt, run_id=run_id).strip()
        if len(llm_draft) > 50 and "120" in llm_draft:
            return llm_draft
    except Exception as e:
        logger.warning("LLM resolution drafting failed (%s); using verified template.", e)

    return template


def resolution_draft_agent_node(state: DisputeState) -> DisputeState:
    """
    Resolution Draft worker agent:
    Decides when to call Agentic-RAG for dispute rules (AC-11),
    drafts resolution prose, and executes post-draft reflection & critique loop (AC-12).
    """
    start_time = time.time()
    dispute_id = state.get("dispute_id") or state.get("application_id", "DSP-001")
    eligible = state.get("chargeback_eligible", False)
    reason_code = state.get("chargeback_reason_code")
    iteration = state.get("reflection_iteration", 0)

    # 1. Agentic-RAG Decision: Call RAG tool for dispute rules on demand (AC-11)
    citations = list(state.get("rule_citations", []))
    if not citations and eligible:
        query = f"chargeback window 120 days reason code {reason_code or 'fraud'}"
        retrieved = retrieve_dispute_rules(query=query, top_k=2, run_id=dispute_id)
        citations = [
            {
                "rule_code": r.get("rule_code", "CR-01"),
                "chunk_id": r["chunk_id"],
                "source_file": r["source_file"],
                "text_hash": r["text_hash"],
            }
            for r in retrieved
        ]
        state["retrieved_rules"] = retrieved
        state["rule_citations"] = citations

    # 2. Draft Resolution
    draft = draft_resolution_prose(state, citations=citations, run_id=dispute_id)

    # 3. Post-Draft Reflection & Critique Step (AC-12)
    critique = _critique_draft(
        draft=draft,
        citations=citations,
        eligible=eligible,
        reason_code=reason_code,
    )

    reflection_passed = critique["passed"]

    # If critique failed and under max reflection cycles (1 reflection allowed per AC-12), heal
    if not reflection_passed and iteration < 1:
        iteration += 1
        logger.info("[Reflection Loop] Critique failed: %s. Initiating self-healing...", critique["feedback"])

        # Record reflection event span in tracer
        tracer.record_span(
            name="reflection.self_healing_loop",
            span_kind="thinking",
            start_time=start_time,
            end_time=time.time(),
            inputs={"iteration": iteration, "critique_issues": critique["issues"]},
            outputs={"healing_action": "FETCH_MISSING_CITATIONS_AND_REDRAFT"},
            run_id=dispute_id,
            step_id="step-reflection-loop",
        )

        # Self-healing action: fetch missing citations explicitly
        additional_rules = retrieve_dispute_rules("Rule CR-01 120-Day Dispute Filing Window", top_k=2, run_id=dispute_id)
        citations.extend([
            {
                "rule_code": r.get("rule_code", "CR-01"),
                "chunk_id": r["chunk_id"],
                "source_file": r["source_file"],
                "text_hash": r["text_hash"],
            }
            for r in additional_rules if r["chunk_id"] not in [c["chunk_id"] for c in citations]
        ])
        state["rule_citations"] = citations

        # Re-draft with healed citations
        draft = draft_resolution_prose(state, citations=citations, run_id=dispute_id)
        # Re-critique
        critique = _critique_draft(draft=draft, citations=citations, eligible=eligible, reason_code=reason_code)
        reflection_passed = critique["passed"]

    action = "PROCEED_CHARGEBACK" if eligible else "DENY_OUTSIDE_WINDOW"
    if state.get("human_review_required"):
        action = "ESCALATE_TO_HUMAN"

    validated_output = ResolutionDraftOutput(
        dispute_id=dispute_id,
        resolution_action=action,
        draft_resolution=draft,
        rule_citations=citations,
        reflection_passed=reflection_passed,
        reflection_iteration=iteration,
    )

    state["resolution_draft"] = draft
    state["rationale"] = draft
    state["resolution_action"] = action
    state["ai_recommendation"] = "APPROVE" if eligible else "DECLINE"  # legacy alias
    state["reflection_feedback"] = critique["feedback"]
    state["reflection_iteration"] = iteration
    state["reflection_passed"] = reflection_passed
    state["request_status"] = "COMPLETED"

    state["routing_history"] = list(state.get("routing_history", [])) + ["resolution_draft_agent"]
    state["step_count"] = state.get("step_count", 0) + 1

    latency_ms = round((time.time() - start_time) * 1000, 2)
    tracer.record_span(
        name="agent.resolution_draft_agent",
        span_kind="acting",
        start_time=start_time,
        end_time=time.time(),
        inputs={"dispute_id": dispute_id, "eligible": eligible},
        outputs=validated_output.model_dump(),
        run_id=dispute_id,
        step_id="step-resolution-draft-agent",
    )
    log_agent_action(
        actor="resolution_draft_agent",
        action="drafted_resolution_with_reflection",
        state=state,
        latency_ms=latency_ms,
    )
    return state


async def aresolution_draft_agent_node(state: DisputeState) -> DisputeState:
    """Async LangGraph node for resolution draft agent."""
    import asyncio
    return await asyncio.to_thread(resolution_draft_agent_node, state=state)
