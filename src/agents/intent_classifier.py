"""
Intent Classifier Node for Loan Origination & Underwriting Copilot.
Classifies requests into 7 distinct intents with strict allowed-path routing constraints.
Per plan.md Section 4.3.
"""

import os
import re
from typing import Dict, Any, Tuple
from src.state import LoanState, VALID_INTENTS
from src.observability.unified_logger import log_agent_action

# Keyword heuristic rules for deterministic fallback / tests
INTENT_KEYWORD_RULES = [
    (re.compile(r"(?:status|check|progress|where\s+is\s+my\s+application|track)", re.IGNORECASE), "status_check"),
    (re.compile(r"(?:documents?|required\s+doc|upload|aadhaar|pan|statement\s+needed)", re.IGNORECASE), "document_question"),
    (re.compile(r"(?:what\s+is\s+(?:the\s+)?(?:lending\s+)?policy|policy\s+rule|dti\s+limit|max\s+loan\s+allowed|criteria|\bpolicy\b)", re.IGNORECASE), "policy_question"),
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


def intent_classifier_node(state: LoanState) -> LoanState:
    """LangGraph node: Classifies intent and registers routing in state."""
    raw_text = state.get("applicant_raw_text", "")
    clarification = state.get("clarification_response", "")

    # If clarification provided on resume, combine to reclassify
    full_text = f"{raw_text} {clarification}".strip()
    detected_intent = classify_intent(full_text, state.get("intent", "new_application"))

    state["intent"] = detected_intent
    state["routing_history"].append("intent_classifier")
    state["step_count"] += 1

    log_agent_action(
        actor="intent_classifier",
        action="classified_intent",
        tool=None,
        decision=detected_intent,
        application_id=state.get("application_id"),
        details={"intent": detected_intent},
    )
    return state
