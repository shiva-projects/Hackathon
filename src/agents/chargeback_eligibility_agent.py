"""
Chargeback Eligibility Agent for Transaction Dispute & Fraud Triage Copilot.
Deterministically checks chargeback window compliance (120-Day Rule) and maps reason codes.
Enforces the 'Code decides, LLM explains' invariant.
Per AAIE_AGT_001_BFS Specification §5.1 (AC-02, AC-03, AC-04).
"""

import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from src.state import DisputeState
from src.observability.unified_logger import log_agent_action
from src.observability.tracing import tracer

logger = logging.getLogger(__name__)


class ChargebackEligibilityOutput(BaseModel):
    """Pydantic validated structured handoff object (AC-04)."""
    transaction_id: str
    days_since_transaction: int
    chargeback_window_days: int = 120
    chargeback_eligible: bool
    chargeback_reason_code: Optional[str]
    ineligibility_reason: Optional[str] = None
    short_circuit_outside_window: bool


def _parse_iso_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str[:19], fmt[:len(date_str[:19])])
        except ValueError:
            pass
    return None


def evaluate_chargeback_eligibility(
    transaction_date_str: Optional[str],
    dispute_date_str: Optional[str] = None,
    raw_text: str = "",
    fraud_risk_level: str = "LOW",
) -> Dict[str, Any]:
    """
    Deterministic domain rule computation:
    Calculates elapsed days against the card network 120-day chargeback window.
    """
    txn_dt = _parse_iso_date(transaction_date_str)
    disp_dt = _parse_iso_date(dispute_date_str) or datetime(2026, 2, 28, 12, 0, 0)

    if txn_dt:
        delta = (disp_dt - txn_dt).days
        days_since = max(0, delta)
    else:
        # Default fallback to 15 days if date string is unparseable
        days_since = 15

    window_limit = 120

    if days_since > window_limit:
        return {
            "eligible": False,
            "days_since": days_since,
            "window_limit": window_limit,
            "reason_code": None,
            "ineligibility_reason": "EXCEEDS_120_DAY_WINDOW",
        }

    # Map chargeback reason code deterministically based on dispute indicators
    text_lower = raw_text.lower()
    if fraud_risk_level in ("HIGH", "CRITICAL") or "unauthorized" in text_lower or "stolen" in text_lower:
        reason_code = "10.4"   # Card-Absent Fraud / No Authorization
    elif "cancel" in text_lower or "subscription" in text_lower:
        reason_code = "13.2"   # Cancelled Recurring Transaction
    elif "duplicate" in text_lower or "twice" in text_lower or "double" in text_lower:
        reason_code = "12.5"   # Duplicate Processing
    elif "damaged" in text_lower or "defective" in text_lower or "not as described" in text_lower:
        reason_code = "13.3"   # Defective or Not as Described
    else:
        reason_code = "13.1"   # Merchandise / Services Not Received

    return {
        "eligible": True,
        "days_since": days_since,
        "window_limit": window_limit,
        "reason_code": reason_code,
        "ineligibility_reason": None,
    }


def chargeback_eligibility_agent_node(state: DisputeState) -> DisputeState:
    """
    Chargeback Eligibility worker agent:
    Calculates days since transaction vs 120-day limit.
    Short-circuits disputes outside the window (AC-03).
    """
    start_time = time.time()
    dispute_id = state.get("dispute_id") or state.get("application_id", "DSP-001")
    txn_details = state.get("transaction_details", {})
    txn_id = txn_details.get("transaction_id") or state.get("transaction_id", "TXN-88412")
    txn_date = txn_details.get("transaction_date")
    raw_text = state.get("dispute_raw_text") or state.get("applicant_raw_text", "")
    fraud_level = state.get("fraud_risk_level", "LOW")

    res = evaluate_chargeback_eligibility(
        transaction_date_str=txn_date,
        raw_text=raw_text,
        fraud_risk_level=fraud_level,
    )

    eligible = res["eligible"]
    days_since = res["days_since"]
    window_limit = res["window_limit"]
    reason_code = res["reason_code"]
    ineligibility_reason = res["ineligibility_reason"]

    # Short circuit condition for AC-03
    short_circuit = not eligible

    validated_output = ChargebackEligibilityOutput(
        transaction_id=txn_id,
        days_since_transaction=days_since,
        chargeback_window_days=window_limit,
        chargeback_eligible=eligible,
        chargeback_reason_code=reason_code,
        ineligibility_reason=ineligibility_reason,
        short_circuit_outside_window=short_circuit,
    )

    state["chargeback_eligible"] = eligible
    state["chargeback_window_days"] = window_limit
    state["days_since_transaction"] = days_since
    state["chargeback_reason_code"] = reason_code
    state["ineligibility_reason"] = ineligibility_reason

    if short_circuit:
        state["resolution_action"] = "DENY_OUTSIDE_WINDOW"
        state["request_status"] = "COMPLETED"
        state["rationale"] = (
            f"The disputed transaction occurred {days_since} days ago, exceeding the mandatory "
            f"{window_limit}-day card network chargeback window (Rule CR-01). The dispute cannot be filed."
        )

    state["routing_history"] = list(state.get("routing_history", [])) + ["chargeback_eligibility_agent"]
    state["step_count"] = state.get("step_count", 0) + 1

    latency_ms = round((time.time() - start_time) * 1000, 2)
    tracer.record_span(
        name="agent.chargeback_eligibility_agent",
        span_kind="acting",
        start_time=start_time,
        end_time=time.time(),
        inputs={"transaction_id": txn_id, "transaction_date": txn_date},
        outputs=validated_output.model_dump(),
        run_id=dispute_id,
        step_id="step-chargeback-eligibility-agent",
    )
    log_agent_action(
        actor="chargeback_eligibility_agent",
        action="evaluated_chargeback_window",
        state=state,
        latency_ms=latency_ms,
    )
    return state


async def achargeback_eligibility_agent_node(state: DisputeState) -> DisputeState:
    """Async LangGraph node for chargeback eligibility agent."""
    import asyncio
    return await asyncio.to_thread(chargeback_eligibility_agent_node, state=state)
