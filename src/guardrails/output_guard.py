"""
Output Guardrail, PII Redaction & Recommendation Language Enforcement.
Per plan.md Section 6.1 & 13.12.
"""

import re
from typing import Any, Dict, List, Optional
from src.observability.span_sanitizer import sanitize_data, sanitize_text

# Regex patterns detecting claims of a "final decision" by the AI
FINAL_DECISION_PATTERNS = [
    re.compile(r"final\s+decision\s*:\s*(?:APPROVE|DECLINE|REFER)", re.IGNORECASE),
    re.compile(r"we\s+have\s+decided\s+to\s+(?:approve|decline|refer)", re.IGNORECASE),
    re.compile(r"this\s+loan\s+is\s+officially\s+(?:approved|declined)", re.IGNORECASE),
    re.compile(r"the\s+system\s+has\s+finalized\s+(?:approval|decline)", re.IGNORECASE),
]

FORBIDDEN_FINAL_PHRASES = [
    "final decision: approve",
    "final decision: decline",
    "final decision: refer",
]


def redact_specific_literals(text: str, literals: List[str]) -> str:
    """Explicitly scrubs exact literal values and their formatted representations."""
    sanitized = text
    for lit in literals:
        if not lit:
            continue
        # Clean literal
        clean_lit = re.escape(lit.strip())
        sanitized = re.sub(clean_lit, "[REDACTED_PII]", sanitized)
    return sanitized


def enforce_recommendation_language(prose: str, ai_recommendation: Optional[str]) -> str:
    """
    Enforces that LLM rationale text never asserts an authoritative final decision (AC-03, Section 13.12).
    Rewrites any accidental final decision declarations to advisory recommendation framing.
    """
    cleaned = prose
    for pattern in FINAL_DECISION_PATTERNS:
        if pattern.search(cleaned):
            rec_str = ai_recommendation or "REFER"
            cleaned = pattern.sub(f"AI recommendation: {rec_str} (Advisory)", cleaned)

    return cleaned


def screen_output(
    rationale: str,
    ai_recommendation: Optional[str],
    seeded_pii_literals: Optional[List[str]] = None,
) -> str:
    """
    Full output guardrail pipeline:
    1. Redacts PII and sensitive numeric representations.
    2. Rewrites any authoritative 'final decision' wording into advisory recommendation language.
    """
    # Step 1: PII Scrubbing
    sanitized = sanitize_text(rationale)
    if seeded_pii_literals:
        sanitized = redact_specific_literals(sanitized, seeded_pii_literals)

    # Step 2: Language Enforcement
    sanitized = enforce_recommendation_language(sanitized, ai_recommendation)

    return sanitized


def sanitize_review_reason(reason: str) -> str:
    """Sanitizes human reviewer notes before saving to logs/human_reviews.jsonl."""
    return sanitize_text(reason)
