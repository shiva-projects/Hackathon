"""
Versioned prompt templates for the Loan Origination & Underwriting Copilot.
"""

from .rationale_prompts import (
    RATIONALE_SYSTEM_PROMPT_V1,
    RATIONALE_USER_PROMPT_TEMPLATE_V1,
    build_rationale_prompt,
)
from .intent_prompts import (
    INTENT_PROMPT_VERSION,
    INTENT_SYSTEM_PROMPT_V2,
    INTENT_USER_PROMPT_TEMPLATE_V2,
    build_intent_prompt,
)
from .injection_prompts import (
    INJECTION_PROMPT_VERSION,
    INJECTION_SYSTEM_PROMPT_V2,
    INJECTION_CLASSIFIER_PROMPT_TEMPLATE_V2,
    build_injection_prompt,
)

__all__ = [
    "RATIONALE_SYSTEM_PROMPT_V1",
    "RATIONALE_USER_PROMPT_TEMPLATE_V1",
    "build_rationale_prompt",
    "INTENT_PROMPT_VERSION",
    "INTENT_SYSTEM_PROMPT_V2",
    "INTENT_USER_PROMPT_TEMPLATE_V2",
    "build_intent_prompt",
    "INJECTION_PROMPT_VERSION",
    "INJECTION_SYSTEM_PROMPT_V2",
    "INJECTION_CLASSIFIER_PROMPT_TEMPLATE_V2",
    "build_injection_prompt",
]
