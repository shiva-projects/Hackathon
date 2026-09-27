"""
Input Guardrail & Untrusted Text Quarantine.
Detects prompt injection and cross-applicant requests, isolating applicant free text as quarantined data.
Per plan.md Section 6.1, 6.4 & NFR-03.
"""

import re
from typing import Optional, Dict, Any
from pydantic import BaseModel
from src.observability.unified_logger import log_agent_action

# Patterns for prompt injection attacks (including paraphrased adversarial overrides)
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous\s+|prior\s+)?instructions", re.IGNORECASE),
    re.compile(r"ignore\s+(?:the\s+)?(?:underwriting\s+)?(?:policy|guidelines?|rules?|criteria)", re.IGNORECASE),
    re.compile(r"(?:disregard|forget|override|drop|bypass)\s+(?:all\s+)?(?:prior\s+)?(?:instructions|rules|policy|policies|checks|thresholds|dti|guardrails|compliance)", re.IGNORECASE),
    re.compile(r"(?:set\s+aside|waive)\s+(?:all\s+)?(?:the\s+)?(?:rules|policies|guidelines|requirements)", re.IGNORECASE),
    re.compile(r"(?:system|admin|root|developer)\s*:\s*", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:the\s+)?(?:admin|administrator|root|super-?user|developer|god|unrestricted|jailbreak|dan)", re.IGNORECASE),
    re.compile(r"(?:now\s+in|entering|switch\s+to)\s+(?:developer|jailbreak|god|unrestricted|admin)\s+mode", re.IGNORECASE),
    re.compile(r"(?:bypass|skip|circumvent|override)\s+(?:the\s+)?(?:underwriting|approval|decision|review|eligibility|assessment|check|guardrail|policy|compliance)\s*(?:process|engine|step|logic|rules?|checks?)?", re.IGNORECASE),
    re.compile(r"approve\s+(?:all|every|this)\s+(?:loan|application)", re.IGNORECASE),
    re.compile(r"(?:auto-?approve|always\s+approve|greenlight)", re.IGNORECASE),
    re.compile(r"(?:act|pretend|simulate)\s+as\s+(?:an?\s+)?(?:unrestricted|lenient|different|rogue)\s+(?:loan\s+officer|ai|system|underwriter)", re.IGNORECASE),
    re.compile(r"new\s+rule\s*:\s*(?:auto-?approve|always\s+approve|grant\s+loan)", re.IGNORECASE),
    re.compile(r"(?:reveal|print|output|leak|dump)\s+(?:your\s+)?(?:system\s+prompt|developer\s+instructions|base\s+prompt)", re.IGNORECASE),
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

    # 1. Primary evaluation via Guardrails-AI validator suite
    from src.guardrails.guardrails_ai_validator import validate_input_with_guardrails
    gr_res = validate_input_with_guardrails(raw_text, current_application_id)

    if not gr_res.is_safe:
        from src.context.quarantine import quarantine_untrusted_text
        quarantined = quarantine_untrusted_text(raw_text)

        if gr_res.cross_applicant_detected:
            target_id = gr_res.target_applicant or "ANOTHER_APPLICANT"
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
                    "engine": gr_res.validator_engine,
                },
            )
            return InputGuardResult(
                is_safe=False,
                quarantined_text=quarantined,
                rejection_reason="CROSS_APPLICANT_ACCESS",
                cross_applicant_detected=True,
                target_applicant=target_id,
            )

        if gr_res.injection_detected:
            log_agent_action(
                actor="input_guard",
                action="prompt_injection_detected",
                tool=None,
                decision="QUARANTINED",
                run_id=run_id,
                application_id=current_application_id,
                details={
                    "refusal_reason": "SECURITY_SENSITIVE_REQUEST",
                    "engine": gr_res.validator_engine,
                },
            )
            return InputGuardResult(
                is_safe=False,
                quarantined_text=quarantined,
                rejection_reason="SECURITY_SENSITIVE_REQUEST",
                injection_detected=True,
            )

    # 2. Secondary pattern verification layer for domain pattern coverage
    for pattern in CROSS_APPLICANT_PATTERNS:
        match = pattern.search(raw_text)
        if match:
            target_id = match.group(1) if match.groups() else "ANOTHER_APPLICANT"
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
