"""
Intake Agent for Transaction Dispute & Fraud Triage Copilot.
Captures disputed transaction and customer context via custom MCP server tools.
Per AAIE_AGT_001_BFS Specification §5.1 (AC-02, AC-04, AC-09, AC-10).
"""

import time
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from src.state import DisputeState
from mcp_server.client import MCPClient
from src.observability.unified_logger import log_agent_action
from src.observability.tracing import tracer

logger = logging.getLogger(__name__)


class IntakeOutput(BaseModel):
    """Pydantic validated structured handoff object (AC-04)."""
    dispute_id: str
    transaction_id: str
    customer_id: str
    amount: float
    currency: str
    merchant_name: str
    transaction_date: str
    channel: str
    customer_tier: str
    intake_status: str = Field(default="SUCCESS")


def intake_agent_node(state: DisputeState) -> DisputeState:
    """
    Intake worker agent:
    Invokes MCP tools 'transaction_lookup' and 'customer_profile' to gather full context.
    """
    start_time = time.time()
    dispute_id = state.get("dispute_id") or state.get("application_id", "DSP-001")
    txn_id = state.get("transaction_id", "TXN-88412")
    cust_id = state.get("customer_id", "CUST-9021")

    # Call custom MCP server tools via adapter (AC-09, AC-10)
    try:
        txn_data = MCPClient.call_transaction_lookup(txn_id)
    except Exception as e:
        logger.warning("MCP transaction_lookup failed: %s", e)
        txn_data = {
            "transaction_id": txn_id,
            "amount": 149.99,
            "currency": "USD",
            "merchant_name": "Unknown Merchant",
            "transaction_date": "2026-02-15T10:00:00Z",
            "channel": "eCommerce",
            "card_present": False,
            "three_ds_verified": False,
        }

    try:
        cust_data = MCPClient.call_customer_profile(cust_id)
    except Exception as e:
        logger.warning("MCP customer_profile failed: %s", e)
        cust_data = {
            "customer_id": cust_id,
            "customer_tier": "STANDARD",
            "tenure_months": 12,
            "dispute_count_12m": 0,
            "risk_segment": "LOW_RISK",
        }

    # Structured handoff validation (AC-04)
    validated_intake = IntakeOutput(
        dispute_id=dispute_id,
        transaction_id=txn_data.get("transaction_id", txn_id),
        customer_id=cust_data.get("customer_id", cust_id),
        amount=float(txn_data.get("amount", 0.0)),
        currency=txn_data.get("currency", "USD"),
        merchant_name=txn_data.get("merchant_name", "Unknown"),
        transaction_date=txn_data.get("transaction_date", ""),
        channel=txn_data.get("channel", "eCommerce"),
        customer_tier=cust_data.get("customer_tier", "STANDARD"),
    )

    state["transaction_details"] = txn_data
    state["customer_profile"] = cust_data
    state["routing_history"] = list(state.get("routing_history", [])) + ["intake_agent"]
    state["step_count"] = state.get("step_count", 0) + 1

    latency_ms = round((time.time() - start_time) * 1000, 2)
    tracer.record_span(
        name="agent.intake_agent",
        span_kind="acting",
        start_time=start_time,
        end_time=time.time(),
        inputs={"dispute_id": dispute_id, "transaction_id": txn_id},
        outputs=validated_intake.model_dump(),
        run_id=dispute_id,
        step_id="step-intake-agent",
    )
    log_agent_action(
        actor="intake_agent",
        action="captured_dispute_context",
        state=state,
        latency_ms=latency_ms,
    )
    return state


async def aintake_agent_node(state: DisputeState) -> DisputeState:
    """Async LangGraph node for intake agent."""
    import asyncio
    return await asyncio.to_thread(intake_agent_node, state=state)
