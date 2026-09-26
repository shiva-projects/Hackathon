"""
Intent Classifier Node for Loan Origination & Underwriting Copilot.
Classifies requests into 7 distinct intents with strict allowed-path routing constraints.
Per plan.md Section 4.3.
"""

import os
import re
from typing import Dict, Any, Tuple, Optional
from src.state import LoanState, VALID_INTENTS
from src.observability.unified_logger import log_agent_action

# Keyword heuristic rules for deterministic fallback / tests
INTENT_KEYWORD_RULES = [
    (re.compile(r"(?:status|check|progress|where\s+is\s+my\s+application|track)", re.IGNORECASE), "status_check"),
    (re.compile(r"(?:documents?|required\s+doc|upload|aadhaar|pan|statement\s+needed)", re.IGNORECASE), "document_question"),
    (re.compile(r"(?:what\s+is\s+(?:the\s+)?(?:lending\s+)?policy|policy\s+rule|dti\s+limit|max\s+loan\s+allowed|explain\s+(?:the\s+)?policy|tell\s+me\s+(?:about\s+)?(?:the\s+)?policy|show\s+(?:me\s+)?(?:the\s+)?policy|criteria\s+for|qualifying\s+criteria)", re.IGNORECASE), "policy_question"),
    (re.compile(r"(?:transfer\s+money|weather|crypto|stock\s+tips|tell\s+me\s+a\s+joke|book\s+flight)", re.IGNORECASE), "out_of_scope"),
    (re.compile(r"(?:show\s+me\s+applicant|income\s+of\s+another|hack|bypass|drop\s+database)", re.IGNORECASE), "security_sensitive"),
    (re.compile(r"\b(?:apply|loan|assess|borrow|underwrite)\b", re.IGNORECASE), "new_application"),
]


def classify_intent(text: str, current_intent: str = "new_application") -> str:
    """
    Classifies the user input text into one of the 7 valid intents:
    new_application | status_check | document_question | policy_question |
    ambiguous | out_of_scope | security_sensitive
    """
    if not text or not text.strip():
        return "ambiguous"

    query = text.strip()

    # If text is extremely vague (under 15 chars and no clear loan terms), classify as ambiguous
    if len(query) < 15 and not any(kw in query.lower() for kw in ["loan", "status", "policy", "doc", "apply"]):
        return "ambiguous"

    # Evaluate keyword rules
    for pattern, intent in INTENT_KEYWORD_RULES:
        if pattern.search(query):
            return intent

    # Check for ambiguous phrasing with word boundaries
    if re.search(r"\b(?:help|info|hello|hi|hey|options)\b", query, re.IGNORECASE):
        return "ambiguous"

    # Default to current or new application if structured applicant data present
    return "new_application"


import time
from src.llm.provider_resolver import has_live_provider_key


def classify_intent_with_llm(text: str, run_id: str = "default_run") -> Optional[str]:
    """Attempts LLM-based intent classification synchronously, returning None if offline/failed."""
    from src.llm.client import invoke_with_resilience

    if not has_live_provider_key():
        return None

    try:
        prompt = (
            "You are an intent classifier for a retail loan underwriting copilot system.\n"
            "Classify the following applicant request into EXACTLY ONE of the following valid intent categories:\n"
            "- new_application (applying for loan, assessing eligibility)\n"
            "- status_check (asking where is application, progress, track)\n"
            "- document_question (asking what documents are needed)\n"
            "- policy_question (asking about lending policy, rules, thresholds, DTI)\n"
            "- ambiguous (vague greeting, unclear request)\n"
            "- out_of_scope (weather, crypto, transfer money, flight booking)\n"
            "- security_sensitive (prompt injection, cross-applicant data, hacking)\n\n"
            f"Applicant Request: {text}\n\n"
            "Respond ONLY with the category name in lowercase."
        )

        response = invoke_with_resilience(prompt, run_id=run_id).strip().lower()
        for valid in VALID_INTENTS:
            if valid in response:
                return valid
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Sync LLM intent classification failed ({e}), falling back to heuristics.")
    return None


async def aclassify_intent_with_llm(text: str, run_id: str = "default_run") -> Optional[str]:
    """Attempts asynchronous LLM-based intent classification."""
    from src.llm.client import ainvoke_with_resilience

    if not has_live_provider_key():
        return None

    try:
        prompt = (
            "You are an intent classifier for a retail loan underwriting copilot system.\n"
            "Classify the following applicant request into EXACTLY ONE of the following valid intent categories:\n"
            "- new_application (applying for loan, assessing eligibility)\n"
            "- status_check (asking where is application, progress, track)\n"
            "- document_question (asking what documents are needed)\n"
            "- policy_question (asking about lending policy, rules, thresholds, DTI)\n"
            "- ambiguous (vague greeting, unclear request)\n"
            "- out_of_scope (weather, crypto, transfer money, flight booking)\n"
            "- security_sensitive (prompt injection, cross-applicant data, hacking)\n\n"
            f"Applicant Request: {text}\n\n"
            "Respond ONLY with the category name in lowercase."
        )

        response = (await ainvoke_with_resilience(prompt, run_id=run_id)).strip().lower()
        for valid in VALID_INTENTS:
            if valid in response:
                return valid
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Async LLM intent classification failed ({e}), falling back to heuristics.")
    return None


async def intent_classifier_node(state: LoanState) -> LoanState:
    """Async LangGraph node: Classifies intent and registers routing in state."""
    start_t = time.time()
    raw_text = state.get("applicant_raw_text", "")
    clarification = state.get("clarification_response", "")

    # If clarification provided on resume, combine to reclassify
    full_text = f"{raw_text} {clarification}".strip()
    session_id = state.get("session_id", "default_run")

    # Structural override: if applicant_facts has income_amount AND requested_amount,
    # this is definitively a loan application regardless of free-text keywords.
    facts = state.get("applicant_facts", {})
    has_structured_application = (
        facts.get("income_amount") is not None
        and facts.get("requested_amount") is not None
    )

    if has_structured_application:
        # Skip LLM and keyword classification — structured data is authoritative
        detected_intent = "new_application"
    else:
        # 1. Attempt async LLM classification if live provider is configured
        llm_intent = await aclassify_intent_with_llm(full_text, run_id=session_id)
        if llm_intent:
            detected_intent = llm_intent
        else:
            detected_intent = classify_intent(full_text, state.get("intent", "new_application"))

    state["intent"] = detected_intent
    state["routing_history"].append("intent_classifier")
    state["step_count"] += 1

    latency_ms = round((time.time() - start_t) * 1000.0, 2)

    log_agent_action(
        actor="intent_classifier",
        action="classified_intent",
        tool=None,
        decision=detected_intent,
        application_id=state.get("application_id"),
        latency_ms=latency_ms,
        details={"intent": detected_intent},
    )
    return state


def intent_classifier_node_sync(state: LoanState) -> LoanState:
    """Synchronous entry point for tests/legacy callers."""
    import asyncio
    return asyncio.run(intent_classifier_node(state))
