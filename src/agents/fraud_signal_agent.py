"""
Fraud Signal Agent for Transaction Dispute & Fraud Triage Copilot.
Surfaces fraud indicators and evaluates risk heuristics via custom MCP server tools.
Per AAIE_AGT_001_BFS Specification §5.1 (AC-02, AC-03, AC-04, AC-09, AC-10).
"""

import time
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from src.state import DisputeState
from mcp_server.client import MCPClient
from src.observability.unified_logger import log_agent_action
from src.observability.tracing import tracer

logger = logging.getLogger(__name__)


class FraudSignalOutput(BaseModel):
    """Pydantic validated structured handoff object (AC-04)."""
    transaction_id: str
    fraud_score: float = Field(ge=0.0, le=1.0)
    risk_level: str
    recommended_action: str
    detected_indicators: List[str]
    escalate_to_manual_review: bool


def fraud_signal_agent_node(state: DisputeState) -> DisputeState:
    """
    Fraud signal worker agent:
    Extracts transaction signals, queries MCP 'fraud_rules' tool, and evaluates risk.
    Routes to manual review if suspected fraud (AC-03 conditional routing).
    """
    start_time = time.time()
    dispute_id = state.get("dispute_id") or state.get("application_id", "DSP-001")
    txn_details = state.get("transaction_details", {})
    txn_id = txn_details.get("transaction_id") or state.get("transaction_id", "TXN-88412")
    raw_text = (state.get("dispute_raw_text") or state.get("applicant_raw_text", "")).lower()

    # Detect baseline signals from raw text and transaction payload
    signals = []
    if "stolen" in raw_text or "compromised" in raw_text:
        signals.append("REPORTED_STOLEN_CARD")
    if "unrecognized" in raw_text or "never made" in raw_text:
        signals.append("UNRECOGNIZED_TRANSACTION")
    if "scam" in raw_text or "phishing" in raw_text:
        signals.append("SUSPECTED_SOCIAL_ENGINEERING")

    # Call custom MCP server tool via adapter (AC-09, AC-10)
    try:
        fraud_eval = MCPClient.call_fraud_rules(txn_id, signals=signals)
    except Exception as e:
        logger.warning("MCP fraud_rules failed: %s", e)
        fraud_eval = {
            "transaction_id": txn_id,
            "fraud_score": 0.45,
            "risk_level": "MEDIUM",
            "recommended_action": "STANDARD_DISPUTE_TRIAGE",
            "detected_indicators": signals,
            "liability_shift_present": False,
        }

    fraud_score = float(fraud_eval.get("fraud_score", 0.10))
    risk_level = fraud_eval.get("risk_level", "LOW")
    recommended_action = fraud_eval.get("recommended_action", "STANDARD_DISPUTE_TRIAGE")
    indicators = fraud_eval.get("detected_indicators", signals)

    # AC-03 Conditional Routing Rule: Escalate suspected fraud to manual review
    escalate_manual = (fraud_score >= 0.70 or risk_level == "HIGH" or "REPORTED_STOLEN_CARD" in indicators)

    validated_output = FraudSignalOutput(
        transaction_id=txn_id,
        fraud_score=fraud_score,
        risk_level=risk_level,
        recommended_action=recommended_action,
        detected_indicators=indicators,
        escalate_to_manual_review=escalate_manual,
    )

    state["fraud_signals"] = [{"indicator": ind} for ind in indicators]
    state["fraud_risk_score"] = fraud_score
    state["fraud_risk_level"] = risk_level

    if escalate_manual:
        state["human_review_required"] = True
        state["human_review_reason"] = f"SUSPECTED_FRAUD_ESCALATION (score={fraud_score:.2f}, level={risk_level})"

    state["routing_history"] = list(state.get("routing_history", [])) + ["fraud_signal_agent"]
    state["step_count"] = state.get("step_count", 0) + 1

    latency_ms = round((time.time() - start_time) * 1000, 2)
    tracer.record_span(
        name="agent.fraud_signal_agent",
        span_kind="acting",
        start_time=start_time,
        end_time=time.time(),
        inputs={"transaction_id": txn_id, "signals_in": signals},
        outputs=validated_output.model_dump(),
        run_id=dispute_id,
        step_id="step-fraud-signal-agent",
    )
    log_agent_action(
        actor="fraud_signal_agent",
        action="evaluated_fraud_signals",
        state=state,
        latency_ms=latency_ms,
    )
    return state


async def afraud_signal_agent_node(state: DisputeState) -> DisputeState:
    """Async LangGraph node for fraud signal agent."""
    import asyncio
    return await asyncio.to_thread(fraud_signal_agent_node, state=state)
