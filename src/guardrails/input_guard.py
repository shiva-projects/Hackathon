"""
Input Guardrail & Untrusted Text Quarantine.
Detects prompt injection and cross-applicant requests, isolating applicant free text as quarantined data.
Per plan.md Section 6.1, 6.4 & NFR-03.
"""

import re
from typing import Optional, Dict, Any
from pydantic import BaseModel
from src.observability.unified_logger import log_agent_action

# Patterns for prompt injection attacks
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous\s+|prior\s+)?instructions", re.IGNORECASE),
    re.compile(r"(?:disregard|forget|override)\s+(?:all\s+)?(?:prior\s+)?(?:instructions|rules|policy|checks|thresholds|dti)", re.IGNORECASE),
    re.compile(r"(?:system|admin|root)\s*:\s*", re.IGNORECASE),
    re.compile(r"approve\s+(?:all|every)\s+loans?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:in\s+)?(?:developer|god|unrestricted|jailbreak|dan)\s+mode", re.IGNORECASE),
    re.compile(r"bypass\s+(?:underwriting|risk|guardrails|policy|compliance)", re.IGNORECASE),
    re.compile(r"(?:act|pretend)\s+as\s+(?:an?\s+)?(?:unrestricted|lenient|different)\s+(?:loan\s+officer|ai|system)", re.IGNORECASE),
    re.compile(r"new\s+rule\s*:\s*(?:auto-?approve|always\s+approve)", re.IGNORECASE),
]

# Patterns for cross-applicant data exfiltration attempts (explicit IDs, indirect & paraphrased)
CROSS_APPLICANT_PATTERNS = [
    re.compile(r"(?:show|get|view|reveal|read|fetch|pull|inspect|compare\s+(?:with|to)?)\s+(?:me\s+)?(?:applicant|application|app|file|record|profile)?\s*([A-Z]{2,5}-\d{2,5})", re.IGNORECASE),
    re.compile(r"(?:what\s+is|give\s+me|find|extract)\s+(?:(?:application|applicant)\s+)?([A-Z]{2,5}-\d{2,5})'?s?\s+(?:income|data|account|loan|details|balance|status|history|report)", re.IGNORECASE),
    re.compile(r"(?:what\s+is|give\s+me|find|extract)\s+([A-Z0-9\-_]+)'s\s+(?:income|data|account|loan|details|balance|status|history|report)", re.IGNORECASE),
    re.compile(r"\b(?:switch|change)\s+(?:context\s+to\s+|to\s+)?(?:application\s+|applicant\s+)?([A-Z]{2,5}-\d{2,5})", re.IGNORECASE),
    re.compile(r"transfer\s+(?:funds|money|balance)\s+(?:from|to)\s+(?:account|applicant|customer)", re.IGNORECASE),
    re.compile(r"(?:what\s+(?:was|is)|show\s+me|tell\s+me)\s+(?:the\s+)?(?:other|prior|another|second|different)\s+(?:applicant|borrower|customer|user|client|person)'?s?\s+(?:income|loan|rate|decision|details|score|balance|status)", re.IGNORECASE),
    re.compile(r"(?:compare\s+(?:my\s+)?(?:rate|loan|income|profile)\s+with|how\s+does\s+my\s+application\s+compare\s+to)\s+(?:the\s+)?(?:other|another|previous)\s+(?:applicant|borrower|customer|loan|case)", re.IGNORECASE),
    re.compile(r"(?:access|dump|export|leak)\s+(?:records|data|files)\s+of\s+(?:other|all|another)\s+(?:applicants?|borrowers?|customers?)", re.IGNORECASE),
]


class InputGuardResult(BaseModel):
    is_safe: bool
    quarantined_text: str
    rejection_reason: Optional[str] = None
    injection_detected: bool = False
    cross_applicant_detected: bool = False
    target_applicant: Optional[str] = None


def screen_input(
    raw_text: str,
    current_application_id: str,
    run_id: str = "default_run",
) -> InputGuardResult:
    """
    Evaluates applicant-supplied text before graph processing:
    1. Quarantines raw text so it is labeled QUARANTINED_DATA.
    2. Flags prompt injection attempts.
    3. Refuses cross-applicant data queries.
    Logs consequential refusals to logs/agent_actions.jsonl.
    """
    if not raw_text:
        return InputGuardResult(
            is_safe=True,
            quarantined_text="<QUARANTINED_DATA></QUARANTINED_DATA>",
        )

    # 1. Screen for cross-applicant attempts
    for pattern in CROSS_APPLICANT_PATTERNS:
        match = pattern.search(raw_text)
        if match:
            target_id = match.group(1) if match.groups() else "ANOTHER_APPLICANT"
            # If the user is asking about a different application ID
            if target_id.upper() != current_application_id.upper():
                log_agent_action(
                    actor="input_guard",
                    action="cross_applicant_attempt_refused",
                    tool=None,
                    decision="REFUSED",
                    run_id=run_id,
                    application_id=current_application_id,
                    details={
                        "refusal_reason": "CROSS_APPLICANT_ACCESS",
                        "queried_target": target_id,
                    },
                )
                return InputGuardResult(
                    is_safe=False,
                    quarantined_text=f"<QUARANTINED_DATA>{raw_text}</QUARANTINED_DATA>",
                    rejection_reason="CROSS_APPLICANT_ACCESS",
                    cross_applicant_detected=True,
                    target_applicant=target_id,
                )

    # 2. Screen for prompt injection
    injection_found = False
    for pattern in INJECTION_PATTERNS:
        if pattern.search(raw_text):
            injection_found = True
            break

    from src.context.quarantine import quarantine_untrusted_text
    quarantined = quarantine_untrusted_text(raw_text)

    if injection_found:
        log_agent_action(
            actor="input_guard",
            action="prompt_injection_detected",
            tool=None,
            decision="QUARANTINED",
            run_id=run_id,
            application_id=current_application_id,
            details={"refusal_reason": "SECURITY_SENSITIVE_REQUEST"},
        )
        return InputGuardResult(
            is_safe=False,
            quarantined_text=quarantined,
            rejection_reason="SECURITY_SENSITIVE_REQUEST",
            injection_detected=True,
        )

    # Clean text safely wrapped in quarantine container
    return InputGuardResult(
        is_safe=True,
        quarantined_text=quarantined,
    )
