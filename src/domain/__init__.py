"""Domain logic package for Loan Origination Copilot."""
from src.domain.models import (
    RecommendationType,
    RuleType,
    AffordabilityResult,
    RuleEvaluationResult,
    UnderwritingDecisionResult,
)
from src.domain.calculations import (
    calculate_dti,
    calculate_monthly_gross_income,
    calculate_monthly_obligations,
    calculate_disposable_income,
    compute_affordability,
)
from src.domain.rules import evaluate_policy_rules
from src.domain.decisions import evaluate_underwriting_decision, create_unable_to_complete_decision

__all__ = [
    "RecommendationType",
    "RuleType",
    "AffordabilityResult",
    "RuleEvaluationResult",
    "UnderwritingDecisionResult",
    "calculate_dti",
    "calculate_monthly_gross_income",
    "calculate_monthly_obligations",
    "calculate_disposable_income",
    "compute_affordability",
    "evaluate_policy_rules",
    "evaluate_underwriting_decision",
    "create_unable_to_complete_decision",
]
