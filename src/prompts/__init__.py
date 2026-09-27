"""
Versioned prompt templates for the Loan Origination & Underwriting Copilot.
"""

from .rationale_prompts import (
    RATIONALE_SYSTEM_PROMPT_V1,
    RATIONALE_USER_PROMPT_TEMPLATE_V1,
    build_rationale_prompt,
)

__all__ = [
    "RATIONALE_SYSTEM_PROMPT_V1",
    "RATIONALE_USER_PROMPT_TEMPLATE_V1",
    "build_rationale_prompt",
]
