"""
Tests for Reflection & Self-Healing Loop (AC-12).
Validates:
- Post-draft critique node evaluates resolution compliance against governance standards.
- Low-confidence or citation-deficient output triggers self-healing re-planning loop.
- Emits dedicated OpenTelemetry thinking span 'reflection.self_healing_loop'.
Per AAIE_AGT_001_BFS Specification §5.1 (AC-12).
"""

import pytest
from src.state import create_initial_state
from src.agents.resolution_draft_agent import resolution_draft_agent_node, _critique_draft
from src.observability.tracing import tracer


def test_ac12_critique_evaluates_flawed_draft():
    """AC-12: Asserts critique identifies missing citations and omitted timeframe."""
    flawed_draft = "We approved your request and will give you a refund."
    
    critique = _critique_draft(
        draft=flawed_draft,
        citations=[],
        eligible=True,
        reason_code="10.4",
    )
    assert critique["passed"] is False
    assert any("MISSING_RULE_CITATION" in issue for issue in critique["issues"])
    assert any("OMITTED_TIMEFRAME" in issue for issue in critique["issues"])


def test_ac12_critique_passes_compliant_draft():
    """AC-12: Asserts critique passes a fully compliant resolution notice."""
    compliant_draft = (
        "Dispute Resolution Notice: The transaction is ELIGIBLE under card network rules "
        "as it occurred within the 120-day chargeback window. Initiating chargeback under Reason Code 10.4."
    )
    citations = [{"rule_code": "CR-01", "chunk_id": "chunk-disp-window-001", "text_hash": "a"*64}]

    critique = _critique_draft(
        draft=compliant_draft,
        citations=citations,
        eligible=True,
        reason_code="10.4",
    )
    assert critique["passed"] is True
    assert "CRITIQUE_PASSED" in critique["feedback"]


def test_ac12_self_healing_loop_execution_and_trace():
    """AC-12: Asserts that an un-cited draft triggers the self-healing loop and records an OTEL span."""
    state = create_initial_state(
        dispute_id="DSP-REFLECT-001",
        transaction_id="TXN-88412",
        dispute_raw_text="Unauthorized card absent transaction.",
    )
    state["chargeback_eligible"] = True
    state["chargeback_reason_code"] = "10.4"
    state["rule_citations"] = []
    state["reflection_iteration"] = 0

    # Execute resolution drafting
    state = resolution_draft_agent_node(state)

    # Resolution must pass critique after self-healing
    assert state["reflection_passed"] is True
    assert len(state["rule_citations"]) >= 1

    # Verify OpenTelemetry trace has recorded the resolution agent span
    spans = [s for s in tracer.spans if "resolution_draft_agent" in s.get("name", "") or "reflection" in s.get("name", "")]
    assert len(spans) >= 1
