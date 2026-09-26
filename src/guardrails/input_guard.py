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
    re.compile(r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"override\s+(?:all\s+)?(?:policy|rules|checks)", re.IGNORECASE),
    re.compile(r"approve\s+(?:all|every)\s+loans?", re.IGNORECASE),
    re.compile(r"disregard\s+(?:dti|rules|thresholds)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"bypass\s+(?:underwriting|risk|guardrails)", re.IGNORECASE),
]

# Patterns for cross-applicant data exfiltration attempts
CROSS_APPLICANT_PATTERNS = [
    re.compile(r"(?:show|get|view|reveal|read)\s+(?:me\s+)?(?:applicant|application)\s+([A-Z0-9\-_]+)", re.IGNORECASE),
    re.compile(r"(?:what\s+is|give\s+me)\s+([A-Z0-9\-_]+)'?s?\s+(?:income|data|account|loan|details)", re.IGNORECASE),
    re.compile(r"transfer\s+(?:funds|money)\s+from\s+(?:account|applicant)", re.IGNORECASE),
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
            quarantined_text=f"<QUARANTINED_DATA>{raw_text}</QUARANTINED_DATA>",
            rejection_reason="SECURITY_SENSITIVE_REQUEST",
            injection_detected=True,
        )

    # Clean text safely wrapped in quarantine container
    return InputGuardResult(
        is_safe=True,
        quarantined_text=f"<QUARANTINED_DATA>{raw_text}</QUARANTINED_DATA>",
    )
