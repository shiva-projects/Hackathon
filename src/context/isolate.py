"""
Context Isolation module.
Verifies and enforces strict data isolation boundaries between agents.
Per plan.md Section 13.10.
"""

from typing import Dict, Any, List


def verify_context_isolation(agent_context: Dict[str, Any], forbidden_keys: List[str] = None) -> bool:
    """
    Asserts that forbidden keys (such as applicant_raw_text or private scratch reasoning)
    are absent from the agent's active execution context.
    """
    if forbidden_keys is None:
        forbidden_keys = ["applicant_raw_text", "internal_scratchpad", "system_prompt_tokens"]

    context_data = agent_context.get("selected_context", agent_context)

    for forbidden in forbidden_keys:
        if forbidden in context_data:
            return False

    return True
