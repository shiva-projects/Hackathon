"""
Guardrails-AI Validator Integration for Loan Origination & Underwriting Copilot.
Implements custom Guardrails-AI Validators for prompt injection detection and
cross-applicant data isolation per hackathon specification (Section 7.4 & NFR-03).
"""

import os
import re
from typing import Dict, Any, Optional
from pydantic import BaseModel

# Disable external hub telemetry and tracing to prevent network latency / timeouts
os.environ["GUARDRAILS_DISABLE_TRACING"] = "true"
os.environ["GUARDRAILS_DISABLE_TELEMETRY"] = "true"

try:
    import guardrails.utils.hub_telemetry_utils as _htu
    _htu.HubTelemetry._instance = object()
except Exception:
    pass

try:
    import guardrails.settings as _gr_settings
    _gr_settings.disable_tracing = True
except Exception:
    pass

try:
    from guardrails import Guard
    from guardrails.validators import (
        Validator,
        register_validator,
        ValidationResult,
        PassResult,
        FailResult,
    )
    GUARDRAILS_AI_AVAILABLE = True
except ImportError:
    GUARDRAILS_AI_AVAILABLE = False
    Validator = object
    def register_validator(*args, **kwargs):
        def decorator(cls):
            return cls
        return decorator


@register_validator(name="prompt_injection_guardrail", data_type="string")
class PromptInjectionGuardrail(Validator):
    """
    Guardrails-AI Validator for detecting adversarial prompt injections,
    jailbreak phrases, instruction overriding, and system persona hijacking.
    """
    def __init__(self, on_fail: str = "noop"):
        if GUARDRAILS_AI_AVAILABLE:
            super().__init__(on_fail=on_fail)

    def validate(self, value: Any, metadata: Optional[Dict[str, Any]] = None) -> Any:
        text = str(value or "").lower()
        if not text:
            return PassResult() if GUARDRAILS_AI_AVAILABLE else True

        # Semantic & adversarial override signatures
        injection_signals = [
            "ignore previous",
            "ignore all",
            "ignore prior",
            "ignore the underwriting",
            "disregard all",
            "disregard previous",
            "disregard prior",
            "override rules",
            "override policy",
            "bypass underwriting",
            "bypass rules",
            "bypass compliance",
            "bypass check",
            "set aside the rules",
            "set aside all",
            "system:",
            "admin:",
            "root:",
            "developer:",
            "developer mode",
            "jailbreak",
            "unrestricted mode",
            "dan mode",
            "you are now",
            "act as an unrestricted",
            "auto-approve",
            "always approve",
            "approve every loan",
            "approve this loan immediately",
            "reveal your system prompt",
            "leak system prompt",
            "dump base prompt",
            "output your instructions",
        ]

        for sig in injection_signals:
            if sig in text:
                msg = f"Prompt injection detected: signature '{sig}' identified in applicant input."
                return FailResult(error_message=msg) if GUARDRAILS_AI_AVAILABLE else False

        # Regex heuristic check for structural prompt injection
        injection_regexes = [
            r"ignore\s+(?:all\s+)?(?:previous\s+|prior\s+)?instructions",
            r"(?:disregard|forget|override|drop|bypass)\s+(?:all\s+)?(?:prior\s+)?(?:instructions|rules|policy|policies|checks|thresholds|dti|guardrails)",
            r"(?:system|admin|root|developer)\s*:\s*",
            r"(?:now\s+in|entering|switch\s+to)\s+(?:developer|jailbreak|god|unrestricted|admin)\s+mode",
            r"approve\s+(?:all|every|this)\s+(?:loan|application)",
        ]
        for pattern in injection_regexes:
            if re.search(pattern, text, re.IGNORECASE):
                msg = f"Prompt injection detected by structural pattern: {pattern}"
                return FailResult(error_message=msg) if GUARDRAILS_AI_AVAILABLE else False

        return PassResult() if GUARDRAILS_AI_AVAILABLE else True


@register_validator(name="cross_applicant_guardrail", data_type="string")
class CrossApplicantGuardrail(Validator):
    """
    Guardrails-AI Validator for detecting cross-applicant data exfiltration and context switching.
    """
    def __init__(self, on_fail: str = "noop"):
        if GUARDRAILS_AI_AVAILABLE:
            super().__init__(on_fail=on_fail)

    def validate(self, value: Any, metadata: Optional[Dict[str, Any]] = None) -> Any:
        text = str(value or "")
        if not text:
            return PassResult() if GUARDRAILS_AI_AVAILABLE else True

        current_app_id = (metadata or {}).get("current_application_id", "")

        # 1. Explicit application ID mentions (e.g., APP-002, LO-002)
        matches = re.findall(r"\b([A-Z]{2,5}-\d{2,5})\b", text, re.IGNORECASE)
        for target_id in matches:
            if current_app_id and target_id.upper() != current_app_id.upper():
                msg = f"Cross-applicant access attempt: unauthorized target applicant '{target_id}' queried."
                return FailResult(error_message=msg) if GUARDRAILS_AI_AVAILABLE else False

        # 2. Indirect cross-applicant queries
        indirect_patterns = [
            r"(?:show|get|view|reveal|read|fetch|pull|inspect|compare\s+(?:with|to)?)\s+(?:me\s+)?(?:applicant|application|app|file|record|profile)",
            r"(?:what\s+(?:was|is)|show\s+me|tell\s+me)\s+(?:the\s+)?(?:other|prior|another|second|different)\s+(?:applicant|borrower|customer|user|client|person)",
            r"(?:compare\s+(?:my\s+)?(?:rate|loan|income|profile)\s+with|how\s+does\s+my\s+application\s+compare\s+to)\s+(?:the\s+)?(?:other|another|previous)",
            r"(?:access|dump|export|leak)\s+(?:records|data|files)\s+of\s+(?:other|all|another)\s+(?:applicants?|borrowers?)",
        ]
        for pat in indirect_patterns:
            if re.search(pat, text, re.IGNORECASE):
                msg = "Cross-applicant access attempt: indirect query targeting other applicant records."
                return FailResult(error_message=msg) if GUARDRAILS_AI_AVAILABLE else False

        return PassResult() if GUARDRAILS_AI_AVAILABLE else True


class GuardrailsValidationResult(BaseModel):
    is_safe: bool
    injection_detected: bool = False
    cross_applicant_detected: bool = False
    target_applicant: Optional[str] = None
    rejection_reason: Optional[str] = None
    validator_engine: str = "guardrails-ai"


_COMPILED_GUARD: Optional[Any] = None


def get_compiled_guard() -> Optional[Any]:
    global _COMPILED_GUARD
    if _COMPILED_GUARD is None and GUARDRAILS_AI_AVAILABLE:
        try:
            _COMPILED_GUARD = Guard().use(
                PromptInjectionGuardrail(on_fail="noop")
            ).use(
                CrossApplicantGuardrail(on_fail="noop")
            )
        except Exception:
            _COMPILED_GUARD = None
    return _COMPILED_GUARD


def validate_input_with_guardrails(
    raw_text: str,
    current_application_id: str,
) -> GuardrailsValidationResult:
    """
    Validates applicant input using Guardrails-AI custom validators.
    Returns structured GuardrailsValidationResult.
    """
    if not raw_text:
        return GuardrailsValidationResult(is_safe=True)

    guard = get_compiled_guard()
    if guard is not None:
        try:
            res = guard.validate(raw_text, metadata={"current_application_id": current_application_id})
            if not res.validation_passed:
                errors = [s.failure_reason for s in (res.validation_summaries or []) if s.failure_reason]
                err_text = " ".join(errors)
                is_injection = "injection" in err_text.lower()
                is_cross = "cross-applicant" in err_text.lower()
                
                target = None
                m = re.search(r"target applicant '([^']+)'", err_text)
                if m:
                    target = m.group(1)

                reason = "PROMPT_INJECTION_DETECTED" if is_injection else "CROSS_APPLICANT_ACCESS"
                return GuardrailsValidationResult(
                    is_safe=False,
                    injection_detected=is_injection,
                    cross_applicant_detected=is_cross,
                    target_applicant=target,
                    rejection_reason=reason,
                    validator_engine="guardrails-ai",
                )
            return GuardrailsValidationResult(is_safe=True, validator_engine="guardrails-ai")
        except Exception:
            pass

    # Fallback to direct validator class execution
    p_val = PromptInjectionGuardrail()
    c_val = CrossApplicantGuardrail()

    c_res = c_val.validate(raw_text, metadata={"current_application_id": current_application_id})
    if hasattr(c_res, "error_message") or c_res is False:
        err_msg = getattr(c_res, "error_message", "Cross applicant access attempt")
        target = None
        m = re.search(r"\b([A-Z]{2,5}-\d{2,5})\b", raw_text, re.IGNORECASE)
        if m and m.group(1).upper() != current_application_id.upper():
            target = m.group(1)
        return GuardrailsValidationResult(
            is_safe=False,
            cross_applicant_detected=True,
            target_applicant=target,
            rejection_reason="CROSS_APPLICANT_ACCESS",
            validator_engine="guardrails-ai-direct",
        )

    p_res = p_val.validate(raw_text)
    if hasattr(p_res, "error_message") or p_res is False:
        return GuardrailsValidationResult(
            is_safe=False,
            injection_detected=True,
            rejection_reason="PROMPT_INJECTION_DETECTED",
            validator_engine="guardrails-ai-direct",
        )

    return GuardrailsValidationResult(is_safe=True, validator_engine="guardrails-ai-direct")
