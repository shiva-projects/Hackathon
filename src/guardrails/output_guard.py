"""
Output Guardrail, PII Redaction & Recommendation Language Enforcement.
Per plan.md Section 6.1 & 13.12.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
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


from decimal import Decimal


def validate_rationale_numeric_consistency(
    prose: str,
    ai_recommendation: Optional[str],
    dti: Optional[Decimal] = None,
) -> Tuple[bool, str]:
    """
    Validates that the LLM rationale does not hallucinate numbers or claims that contradict
    the deterministic calculations (Code decides, LLM explains invariant).
    Returns (is_consistent, message).
    """
    if not prose:
        return True, "Empty prose"

    # 1. Recommendation agreement check
    if ai_recommendation:
        rec_upper = ai_recommendation.upper()
        # If deterministic recommendation is REFER or DECLINE, ensure prose doesn't assert approval
        if rec_upper in {"REFER", "DECLINE"}:
            if re.search(r"\b(?:approve|approved)\b", prose, re.IGNORECASE) and not re.search(r"\b(?:not approve|cannot approve|refuse to approve)\b", prose, re.IGNORECASE):
                # Flag contradiction
                return False, f"Prose contains approval terminology contradicting deterministic recommendation {rec_upper}"

    # 2. DTI numeric consistency check
    if dti is not None:
        expected_dti_pct = float(dti) * 100.0
        # Search for any explicitly stated DTI percentage like 'DTI of 25%' or 'DTI is 55%'
        dti_matches = re.findall(r"(?:dti|debt-to-income)[^\d]{1,15}(\d+(?:\.\d+)?)\s*%", prose, re.IGNORECASE)
        for val_str in dti_matches:
            stated_pct = float(val_str)
            # If stated DTI deviates by more than 2.0% from computed DTI, it is a numeric hallucination
            if abs(stated_pct - expected_dti_pct) > 2.0:
                return False, f"Hallucinated DTI {stated_pct:.1f}% contradicts deterministic DTI {expected_dti_pct:.1f}%"

    return True, "Consistent with deterministic findings"


def enforce_currency_consistency(text: str, expected_currency: str = "INR") -> str:
    """Replaces mismatched currency symbols (e.g. $ or £ when currency is INR)."""
    curr = (expected_currency or "INR").upper()
    if curr == "INR":
        text = re.sub(r"\$(\s*\d)", r"₹\1", text)
        text = re.sub(r"£(\s*\d)", r"₹\1", text)
    elif curr == "GBP":
        text = re.sub(r"\$(\s*\d)", r"£\1", text)
        text = re.sub(r"₹(\s*\d)", r"£\1", text)
    elif curr == "USD":
        text = re.sub(r"₹(\s*\d)", r"$\1", text)
        text = re.sub(r"£(\s*\d)", r"$\1", text)
    return text


def build_deterministic_rationale(
    recommendation: Optional[str],
    dti: Optional[Decimal] = None,
    currency: str = "INR",
) -> str:
    """
    Constructs an authoritative deterministic rationale when LLM prose contradicts calculations.
    Ensures contradictory output is never preserved (Fail-Closed, Code decides, LLM explains).
    """
    rec_str = (recommendation or "REFER").upper()
    dti_str = f"{float(dti):.1%}" if dti is not None else "evaluated"

    if rec_str == "APPROVE":
        return (
            f"AI recommendation: APPROVE (Advisory). "
            f"The application satisfies all policy thresholds with a verified DTI of {dti_str}. "
            f"Deterministic evaluation indicates the loan meets affordability criteria."
        )
    elif rec_str == "DECLINE":
        return (
            f"AI recommendation: DECLINE (Advisory). "
            f"The application does not satisfy underwriting thresholds, with a calculated DTI of {dti_str}. "
            f"Deterministic policy rules prevent automated approval."
        )
    else:
        return (
            f"AI recommendation: REFER (Advisory). "
            f"Application flagged for underwriter review based on calculated DTI of {dti_str}. "
            f"Deterministic evaluation requires human assessment."
        )


def screen_output(
    rationale: str,
    ai_recommendation: Optional[str],
    seeded_pii_literals: Optional[List[str]] = None,
    dti: Optional[Decimal] = None,
    expected_currency: str = "INR",
    run_id: str = "default_run",
    span_id: Optional[str] = None,
) -> str:
    """
    Full output guardrail pipeline:
    1. Redacts PII and sensitive numeric representations.
    2. Rewrites any authoritative 'final decision' wording into advisory recommendation language.
    3. Enforces numeric and recommendation consistency against deterministic outputs.
       If contradictory, fails closed: replaces contradictory prose with build_deterministic_rationale.
    4. Enforces jurisdiction currency consistency.
    """
    # Step 1: PII Scrubbing
    sanitized = sanitize_text(rationale)
    if seeded_pii_literals:
        sanitized = redact_specific_literals(sanitized, seeded_pii_literals)

    # Step 2: Language Enforcement
    sanitized = enforce_recommendation_language(sanitized, ai_recommendation)

    # Step 3: Currency Enforcement
    sanitized = enforce_currency_consistency(sanitized, expected_currency)

    # Step 4: Numeric & Recommendation Consistency Validation (Fail-Closed)
    is_valid, reason = validate_rationale_numeric_consistency(sanitized, ai_recommendation, dti)
    if not is_valid:
        from src.observability.unified_logger import log_agent_action
        log_agent_action(
            actor="output_guard",
            action="blocked_and_replaced",
            tool=None,
            decision="CONTRADICTION_REPLACED",
            run_id=run_id,
            details={
                "guardrail": "numeric_consistency",
                "action": "blocked_and_replaced",
                "reason": reason,
                "run_id": run_id,
                "span_id": span_id,
                "ai_recommendation": ai_recommendation,
                "dti": str(dti) if dti is not None else None,
            },
        )
        return build_deterministic_rationale(
            recommendation=ai_recommendation,
            dti=dti,
            currency=expected_currency,
        )

    return sanitized


def sanitize_review_reason(reason: str) -> str:
    """Sanitizes human reviewer notes before saving to logs/human_reviews.jsonl."""
    return sanitize_text(reason)

