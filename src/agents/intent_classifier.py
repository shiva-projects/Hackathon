"""
Intent Classifier Node for Loan Origination & Underwriting Copilot.
Classifies requests into 7 distinct intents with strict allowed-path routing constraints.
Per plan.md Section 4.3.
"""

import os
import re
from typing import Dict, Any, Tuple, Optional
from src.state import LoanState, VALID_INTENTS
from src.observability.unified_logger import log_agent_action, log_tool_call

# Keyword heuristic rules for deterministic fallback / tests
INTENT_KEYWORD_RULES = [
    (re.compile(r"\b(?:status|check|progress|where\s+is\s+my\s+application|track)\b", re.IGNORECASE), "status_check"),
    (re.compile(r"\b(?:documents?|required\s+doc|upload|aadhaar|pan|statement\s+needed)\b", re.IGNORECASE), "document_question"),
    (re.compile(r"(?:what\s+is\s+(?:the\s+)?(?:lending\s+)?policy|policy\s+rule|dti\s+limit|max\s+loan\s+allowed|explain\s+(?:the\s+)?policy|tell\s+me\s+(?:about\s+)?(?:the\s+)?policy|show\s+(?:me\s+)?(?:the\s+)?policy|criteria\s+for|qualifying\s+criteria)", re.IGNORECASE), "policy_question"),
    (re.compile(r"\b(?:transfer\s+money|weather|crypto|stock\s+tips|tell\s+me\s+a\s+joke|book\s+flight)\b", re.IGNORECASE), "out_of_scope"),
    (re.compile(r"(?:show\s+me\s+applicant|income\s+of\s+another|hack|bypass|drop\s+database)", re.IGNORECASE), "security_sensitive"),
    (re.compile(r"\b(?:apply|loan|assess|borrow|underwrite)\b", re.IGNORECASE), "new_application"),
]

ORDERED_INTENT_CATEGORIES = [
    "security_sensitive",
    "out_of_scope",
    "status_check",
    "document_question",
    "policy_question",
    "ambiguous",
    "new_application",
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
from src.context.quarantine import quarantine_untrusted_text
from src.prompts.intent_prompts import build_intent_prompt, INTENT_PROMPT_VERSION


def classify_intent_with_llm(text: str, run_id: str = "default_run") -> Optional[str]:
    """Attempts LLM-based intent classification synchronously, returning None if offline/failed."""
    from src.llm.client import invoke_with_resilience

    if not has_live_provider_key():
        return None

    try:
        quarantined = quarantine_untrusted_text(text)
        prompt = build_intent_prompt(quarantined)

        response = invoke_with_resilience(prompt, run_id=run_id).strip().lower()
        for valid in ORDERED_INTENT_CATEGORIES:
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
        quarantined = quarantine_untrusted_text(text)
        prompt = build_intent_prompt(quarantined)

        response = (await ainvoke_with_resilience(prompt, run_id=run_id)).strip().lower()
        for valid in ORDERED_INTENT_CATEGORIES:
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
    effective_run_id = state.get("run_id") or state.get("session_id", "default_run")

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
        llm_intent = await aclassify_intent_with_llm(full_text, run_id=effective_run_id)
        if llm_intent:
            detected_intent = llm_intent
        else:
            detected_intent = classify_intent(full_text, state.get("intent", "new_application"))

    state["intent"] = detected_intent
    state["routing_history"].append("intent_classifier")
    state["step_count"] += 1

    # Bind LangMem tool for applicant profile reflection and verified attribute lookup
    from src.memory.long_term import long_term_memory
    app_id = state.get("application_id", "APP-UNKNOWN")
    mem_tool = long_term_memory.get_langmem_tool(app_id, "profile")
    if mem_tool is not None:
        state["_langmem_tool"] = getattr(mem_tool, "name", "manage_memory")
        t0 = time.perf_counter()
        invocation_result = mem_tool.invoke({"applicant_id": app_id})
        t_lat = round((time.perf_counter() - t0) * 1000.0, 2)
        log_tool_call(
            agent="intent_classifier",
            tool_name=getattr(mem_tool, "name", "manage_memory"),
            args={"applicant_id": app_id, "namespace": "profile"},
            result={"status": "invoked"},
            latency_ms=max(0.2, t_lat),
            status="success",
            application_id=app_id,
            run_id=effective_run_id,
        )

    latency_ms = round((time.time() - start_t) * 1000.0, 2)

    log_agent_action(
        actor="intent_classifier",
        action="classified_intent",
        tool=None,
        decision=detected_intent,
        application_id=state.get("application_id"),
        run_id=effective_run_id,
        latency_ms=latency_ms,
        details={
            "intent": detected_intent,
            "prompt_name": "intent_classifier",
            "prompt_version": INTENT_PROMPT_VERSION,
        },
    )
    return state


def intent_classifier_node_sync(state: LoanState) -> LoanState:
    """Synchronous entry point for tests/legacy callers."""
    import asyncio
    return asyncio.run(intent_classifier_node(state))
