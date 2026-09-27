"""
Custom MCP Server for Transaction Dispute & Fraud Triage Copilot (AAIE_AGT_001_BFS).
Exposes:
- Resource: dispute_handling_manual://rules
- Tool 1: transaction_lookup
- Tool 2: customer_profile
- Tool 3: fraud_rules
Per AAIE_AGT_001_BFS Specification §5.1 (AC-09, AC-10).
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("mcp_server")

# Explicit, documented FastMCP import (Item 10)
try:
    from fastmcp import FastMCP
    logger.info("[MCP] Loaded FastMCP from fastmcp package.")
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
        logger.info("[MCP] Loaded FastMCP from mcp.server.fastmcp.")
    except ImportError as e:
        logger.error("[MCP] FastMCP could not be loaded: %s", e)
        raise ImportError("FastMCP is required to run the custom MCP server. Run: pip install fastmcp") from e

from src.domain.calculations import compute_affordability as domain_compute_affordability
from src.observability.unified_logger import log_tool_call

mcp = FastMCP("TransactionDisputeMCP")

DATA_DIR = Path("data")
SYNTHETIC_DB_PATH = DATA_DIR / "synthetic_transactions.json"
DISPUTE_MANUAL_PATH = DATA_DIR / "dispute_rules" / "CARD_dispute_handling_manual_v1.md"
MANIFEST_PATH = DATA_DIR / "policy_corpus" / "policy_corpus_manifest.json"


def _load_synthetic_db() -> Dict[str, Any]:
    if SYNTHETIC_DB_PATH.exists():
        with open(SYNTHETIC_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"transactions": {}, "customers": {}}


# =========================================================================
# RESOURCES (AC-09)
# =========================================================================

@mcp.resource("dispute-handling-manual://rules")
def get_dispute_handling_manual() -> str:
    """
    Resource 1: Exposes the full Card Network Dispute Handling Manual.
    Contains network chargeback windows, evidence timelines, and reason codes.
    Consumed via langchain-mcp-adapters per AC-09.
    """
    if DISPUTE_MANUAL_PATH.exists():
        return DISPUTE_MANUAL_PATH.read_text(encoding="utf-8")
    return "Dispute handling manual available under data/dispute_rules/."


@mcp.resource("policy-corpus://index")
def get_policy_corpus_index() -> str:
    """Legacy backward-compatible resource alias."""
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "{}"


# =========================================================================
# TOOLS (AC-09, AC-10)
# =========================================================================

@mcp.tool()
def transaction_lookup(transaction_id: str) -> str:
    """
    Tool 1: Looks up detailed card transaction metadata by transaction_id.
    Returns amount, currency, merchant, category, date, channel, card_last4, and 3DS auth status.
    """
    db = _load_synthetic_db()
    txn = db.get("transactions", {}).get(transaction_id)
    if txn:
        return json.dumps(txn, indent=2)

    # Deterministic fallback synthetic record for unknown IDs
    return json.dumps({
        "transaction_id": transaction_id,
        "customer_id": "CUST-DEFAULT",
        "amount": 149.99,
        "currency": "USD",
        "merchant_name": "Standard Online Retailer",
        "merchant_category": "general_merchandise",
        "transaction_date": "2026-02-15T10:00:00Z",
        "channel": "eCommerce",
        "card_last4": "1234",
        "card_present": False,
        "auth_status": "APPROVED",
        "three_ds_verified": False,
        "ip_address": "198.51.100.1",
        "device_id": "DEV-UNKNOWN"
    }, indent=2)


@mcp.tool()
def customer_profile(customer_id: str) -> str:
    """
    Tool 2: Looks up customer dispute history, loyalty tier, and fraud risk profile.
    """
    db = _load_synthetic_db()
    cust = db.get("customers", {}).get(customer_id)
    if cust:
        return json.dumps(cust, indent=2)

    return json.dumps({
        "customer_id": customer_id,
        "customer_tier": "STANDARD",
        "tenure_months": 12,
        "home_city": "Default City, USA",
        "dispute_count_12m": 0,
        "fraud_rate_historic": 0.0,
        "risk_segment": "LOW_RISK"
    }, indent=2)


@mcp.tool()
def fraud_rules(
    transaction_id: str,
    signals: Optional[List[str]] = None,
) -> str:
    """
    Tool 3: Evaluates fraud rules against transaction indicators and velocity.
    Computes deterministic fraud risk score (0.0 - 1.0) and action recommendation.
    """
    db = _load_synthetic_db()
    txn = db.get("transactions", {}).get(transaction_id, {})
    
    score = 0.10
    detected_indicators = list(signals or [])

    if not txn.get("three_ds_verified", False):
        score += 0.25
        detected_indicators.append("NO_3DS_AUTHENTICATION")

    amount = float(txn.get("amount", 0.0))
    if amount > 500.0:
        score += 0.20
        detected_indicators.append("HIGH_VALUE_TRANSACTION")
    if amount > 1000.0:
        score += 0.20
        detected_indicators.append("EXCESSIVE_AMOUNT_THRESHOLD")

    if not txn.get("card_present", True):
        score += 0.15
        detected_indicators.append("CARD_NOT_PRESENT_ECOMMERCE")

    score = min(1.0, round(score, 2))
    
    if score >= 0.70:
        risk_level = "HIGH"
        recommended_action = "ESCALATE_SUSPECTED_FRAUD"
    elif score >= 0.40:
        risk_level = "MEDIUM"
        recommended_action = "REQUEST_CARDHOLDER_VERIFICATION"
    else:
        risk_level = "LOW"
        recommended_action = "STANDARD_DISPUTE_TRIAGE"

    return json.dumps({
        "transaction_id": transaction_id,
        "fraud_score": score,
        "risk_level": risk_level,
        "recommended_action": recommended_action,
        "detected_indicators": detected_indicators,
        "liability_shift_present": txn.get("three_ds_verified", False),
    }, indent=2)


# =========================================================================
# LEGACY TOOLS (Maintained for Backward-Compatible Tooling Tests)
# =========================================================================

@mcp.tool()
def get_policy_document(policy_id: str, version: str) -> str:
    """Legacy tool maintained for backward compatibility."""
    res = {
        "policy_id": policy_id,
        "version": version,
        "status": "ACTIVE",
        "content": "Legacy policy document stub content.",
        "description": "Legacy policy document stub."
    }
    return json.dumps(res, indent=2)


@mcp.tool()
def compute_affordability(
    income_amount: float,
    income_period: str,
    existing_obligations: List[Dict[str, Any]],
    dti_max_threshold: float = 0.40,
) -> str:
    """Legacy tool maintained for backward compatibility."""
    affordability = domain_compute_affordability(
        income_amount=income_amount,
        income_period=income_period,
        existing_obligations=existing_obligations,
        dti_max_threshold=dti_max_threshold,
    )
    return json.dumps(affordability.to_dict(), indent=2)


if __name__ == "__main__":
    mcp.run()
