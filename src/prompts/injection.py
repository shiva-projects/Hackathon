"""Injection screening prompts module export."""
from src.prompts.injection_prompts import (
    INJECTION_PROMPT_VERSION,
    INJECTION_SYSTEM_PROMPT_V2,
    INJECTION_CLASSIFIER_PROMPT_TEMPLATE_V2,
    build_injection_prompt,
)

PROMPT_VERSION = INJECTION_PROMPT_VERSION

__all__ = [
    "INJECTION_PROMPT_VERSION",
    "PROMPT_VERSION",
    "INJECTION_SYSTEM_PROMPT_V2",
    "INJECTION_CLASSIFIER_PROMPT_TEMPLATE_V2",
    "build_injection_prompt",
]
