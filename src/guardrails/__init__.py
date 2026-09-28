"""Guardrails package for input screening and output sanitization."""
from src.guardrails.input_guard import screen_input, InputGuardResult
from src.guardrails.output_guard import (
    screen_output,
    enforce_recommendation_language,
    sanitize_review_reason,
    build_deterministic_rationale,
    validate_rationale_numeric_consistency,
)

from src.guardrails.guardrails_ai_validator import (
    PromptInjectionGuardrail,
    CrossApplicantGuardrail,
    validate_input_with_guardrails,
    GuardrailsValidationResult,
)

__all__ = [
    "screen_input",
    "InputGuardResult",
    "screen_output",
    "enforce_recommendation_language",
    "sanitize_review_reason",
    "build_deterministic_rationale",
    "validate_rationale_numeric_consistency",
    "PromptInjectionGuardrail",
    "CrossApplicantGuardrail",
    "validate_input_with_guardrails",
    "GuardrailsValidationResult",
]
