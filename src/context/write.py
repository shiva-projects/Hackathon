"""Context write helper for updating state with validated facts."""
from typing import Dict, Any
from src.state import LoanState


def write_verified_fact(state: LoanState, key: str, value: Any) -> LoanState:
    """Updates applicant_facts with a verified factual entry."""
    if "applicant_facts" not in state:
        state["applicant_facts"] = {}
    state["applicant_facts"][key] = value
    return state
