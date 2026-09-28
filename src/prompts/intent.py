"""Intent prompts module export."""
from src.prompts.intent_prompts import (
    INTENT_PROMPT_VERSION,
    INTENT_SYSTEM_PROMPT_V2,
    INTENT_USER_PROMPT_TEMPLATE_V2,
    build_intent_prompt,
)

PROMPT_VERSION = INTENT_PROMPT_VERSION

__all__ = [
    "INTENT_PROMPT_VERSION",
    "PROMPT_VERSION",
    "INTENT_SYSTEM_PROMPT_V2",
    "INTENT_USER_PROMPT_TEMPLATE_V2",
    "build_intent_prompt",
]
