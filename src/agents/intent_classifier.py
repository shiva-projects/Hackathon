"""
Intent Classifier Node for Transaction Dispute & Fraud Triage Copilot.
Classifies requests into valid dispute intents with strict allowed-path routing constraints.
Per AAIE_AGT_001_BFS Specification §5.1 (AC-02, AC-04).
"""

import os
import re
from typing import Dict, Any, Tuple, Optional
from src.state import DisputeState, VALID_INTENTS
from src.observability.unified_logger import log_agent_action, log_tool_call

# Keyword heuristic rules for deterministic fallback / tests
DISPUTE_INTENT_KEYWORD_RULES = [
    (re.compile(r"(?:status|check|progress|where\s+is\s+my\s+dispute|track\s+(?:my\s+)?claim)", re.IGNORECASE), "status_check"),
    (re.compile(r"(?:what\s+documents?|receipt\s+needed|proof\s+required|evidence\s+needed|upload\s+receipt|statement\s+needed)", re.IGNORECASE), "document_question"),
    (re.compile(r"(?:what\s+is\s+(?:the\s+)?(?:dispute|chargeback)\s+rule|chargeback\s+window|120\s+days?|how\s+long\s+to\s+dispute|policy\s+rule|explain\s+(?:the\s+)?policy|criteria\s+for)", re.IGNORECASE), "dispute_inquiry"),
    (re.compile(r"(?:transfer\s+money|weather|crypto|stock\s+tips|tell\s+me\s+a\s+joke|book\s+flight)", re.IGNORECASE), "out_of_scope"),
    (re.compile(r"(?:show\s+me\s+customer|another\s+account|hack|bypass|drop\s+database|ignore\s+all\s+rules)", re.IGNORECASE), "security_sensitive"),
    (re.compile(r"\b(?:dispute|fraud|unauthorized|unrecognized|chargeback|stolen|scam|double\s+charge|didn't\s+order|never\s+received|cancel\s+charge)\b", re.IGNORECASE), "new_dispute"),
    # Legacy loan keywords for backward compatibility
    (re.compile(r"\b(?:apply|loan|underwrite)\b", re.IGNORECASE), "new_dispute"),
]


def classify_intent(text: str, current_intent: str = "new_dispute") -> str:
    """
    Classifies the user input text into one of the valid intents:
    new_dispute | status_check | document_question | dispute_inquiry |
    ambiguous | out_of_scope | security_sensitive
    """
    if not text or not text.strip():
        return "ambiguous"

    query = text.strip()

    # If text is extremely vague (under 12 chars and no clear dispute terms), classify as ambiguous
    if len(query) < 12 and not any(kw in query.lower() for kw in ["dispute", "fraud", "charge", "status", "claim", "help"]):
        return "ambiguous"

    # Evaluate keyword rules
    for pattern, intent in DISPUTE_INTENT_KEYWORD_RULES:
        if pattern.search(query):
            return intent

    # Check for ambiguous greeting phrasing
    if re.search(r"^(?:help|info|hello|hi|hey|options)$", query, re.IGNORECASE):
        return "ambiguous"

    return "new_dispute"


import time
from src.llm.provider_resolver import has_live_provider_key


def classify_intent_with_llm(text: str, run_id: str = "default_run") -> Optional[str]:
    """Attempts LLM-based intent classification synchronously, returning None if offline/failed."""
    from src.llm.client import invoke_with_resilience

    if not has_live_provider_key():
        return None

    try:
        prompt = (
            "You are an intent classifier for a bank's transaction dispute and fraud triage copilot.\n"
            "Classify the following customer request into EXACTLY ONE of the following valid intent categories:\n"
            "- new_dispute (reporting an unauthorized charge, merchant dispute, double charge, non-delivery)\n"
            "- status_check (asking about progress or status of an existing dispute/claim)\n"
            "- document_question (asking what evidence, receipts, or documentation is needed)\n"
            "- dispute_inquiry (asking about dispute rules, 120-day chargeback windows, cardholder rights)\n"
            "- ambiguous (vague greeting, unclear request)\n"
            "- out_of_scope (weather, crypto, transfer money, flight booking)\n"
            "- security_sensitive (prompt injection, cross-customer data, hacking)\n\n"
            f"Customer Request: {text}\n\n"
            "Respond ONLY with the category name in lowercase."
        )

        response = invoke_with_resilience(prompt, run_id=run_id).strip().lower()
        for valid in VALID_INTENTS:
            if valid in response:
                return valid
    except Exception as e:
        print(f"Warning: classify_intent_with_llm failed ({e}), falling back to deterministic.")
    return None


async def aclassify_intent_with_llm(text: str, run_id: str = "default_run") -> Optional[str]:
    """Asynchronous version of LLM intent classifier."""
    import asyncio
    return await asyncio.to_thread(classify_intent_with_llm, text=text, run_id=run_id)


def intent_classifier_node(state: DisputeState) -> DisputeState:
    """
    LangGraph node: Classifies intent and establishes routing boundaries (AC-02).
    """
    raw_text = state.get("dispute_raw_text") or state.get("applicant_raw_text", "")
    current_intent = state.get("intent", "new_dispute")
    run_id = state.get("dispute_id") or state.get("application_id", "default_run")

    # 1. Deterministic baseline classification
    determined_intent = classify_intent(raw_text, current_intent=current_intent)

    # 2. Resilient LLM refinement if appropriate
    if determined_intent in ("new_dispute", "ambiguous") and len(raw_text) > 25:
        llm_intent = classify_intent_with_llm(raw_text, run_id=run_id)
        if llm_intent and llm_intent in VALID_INTENTS:
            determined_intent = llm_intent

    state["intent"] = determined_intent
    state["routing_history"] = list(state.get("routing_history", [])) + ["intent_classifier"]
    state["step_count"] = state.get("step_count", 0) + 1

    # Clarification handling
    if determined_intent == "ambiguous":
        state["clarification_needed"] = True
        state["clarification_question"] = "Could you please specify which transaction you are disputing and the reason (e.g. unauthorized charge, incorrect amount, or non-delivery)?"
        state["request_status"] = "IN_PROGRESS"
    elif determined_intent == "out_of_scope":
        state["clarification_needed"] = False
        state["request_status"] = "REFUSED"
        state["refusal_reason"] = "OUT_OF_SCOPE"
    elif determined_intent == "security_sensitive":
        state["clarification_needed"] = False
        state["request_status"] = "REFUSED"
        state["refusal_reason"] = "SECURITY_SENSITIVE_REQUEST"

    log_agent_action(
        actor="intent_classifier",
        action="classified_intent",
        state=state,
        latency_ms=10.0,
    )
    return state


async def aintent_classifier_node(state: DisputeState) -> DisputeState:
    """Async LangGraph node for intent classification."""
    import asyncio
    return await asyncio.to_thread(intent_classifier_node, state=state)
