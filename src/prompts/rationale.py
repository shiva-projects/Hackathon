"""Rationale prompts module export."""
from src.prompts.rationale_prompts import (
    RATIONALE_SYSTEM_PROMPT_V1,
    RATIONALE_USER_PROMPT_TEMPLATE_V1,
    build_rationale_prompt,
)

PROMPT_VERSION = "rationale-v1"
RATIONALE_PROMPT_VERSION = "rationale-v1"

__all__ = [
    "RATIONALE_SYSTEM_PROMPT_V1",
    "RATIONALE_USER_PROMPT_TEMPLATE_V1",
    "build_rationale_prompt",
    "PROMPT_VERSION",
    "RATIONALE_PROMPT_VERSION",
]
