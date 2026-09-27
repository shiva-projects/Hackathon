"""
Tests for Agentic-RAG Dispute Rule Retrieval (AC-11).
Validates:
- Agentic-RAG tool called on demand for card dispute rules & chargeback reasons.
- Verifiable citations containing rule_code, source_file, chunk_id, and SHA-256 text_hash.
- Text hashes match cryptographic SHA-256 digest of retrieved chunk contents.
Per AAIE_AGT_001_BFS Specification §5.1 (AC-11).
"""

import hashlib
import pytest
from src.tools.rag_tool import retrieve_dispute_rules
from src.state import create_initial_state
from src.agents.resolution_draft_agent import resolution_draft_agent_node


def test_ac11_dispute_rag_rule_retrieval_and_citation_hashing():
    """AC-11: Asserts dense semantic retrieval returns valid citations with exact SHA-256 hashes."""
    query = "What is the cardholder filing deadline and 120-day rule for chargebacks?"
    results = retrieve_dispute_rules(query=query, top_k=3, run_id="TEST-AC11")

    assert len(results) >= 1
    top_chunk = results[0]

    # Verify citation schema
    assert "chunk_id" in top_chunk
    assert "rule_code" in top_chunk
    assert "source_file" in top_chunk
    assert "text_hash" in top_chunk
    assert "text" in top_chunk

    # Verify cryptographic integrity of citation text_hash
    computed_hash = hashlib.sha256(top_chunk["text"].encode("utf-8")).hexdigest()
    assert top_chunk["text_hash"] == computed_hash

    # Must retrieve Rule CR-01 (120-Day Rule)
    assert any("CR-01" in r.get("rule_code", "") or "120" in r.get("text", "") for r in results)


def test_ac11_agentic_rag_called_inside_decision_loop():
    """AC-11: Asserts that resolution_draft_agent invokes RAG on demand during state execution."""
    state = create_initial_state(
        dispute_id="DSP-RAG-TEST",
        transaction_id="TXN-88412",
        dispute_raw_text="Unauthorized transaction on card not present eCommerce purchase.",
    )
    state["chargeback_eligible"] = True
    state["chargeback_reason_code"] = "10.4"
    state["rule_citations"] = []  # Empty initial citations

    # Agent must autonomously call RAG inside the node to retrieve matching reason code rule
    state = resolution_draft_agent_node(state)

    assert len(state["rule_citations"]) >= 1
    citation = state["rule_citations"][0]
    assert "chunk_id" in citation
    assert "text_hash" in citation
    assert len(citation["text_hash"]) == 64
