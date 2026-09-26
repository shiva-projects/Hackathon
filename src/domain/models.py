"""
Domain models for calculations, rule evaluations, and underwriting decisions.
Pure deterministic types, per plan.md Section 4.4 & 14.11.
"""

from decimal import Decimal
from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class RecommendationType(str, Enum):
    APPROVE = "APPROVE"
    REFER = "REFER"
    DECLINE = "DECLINE"


class RuleType(str, Enum):
    DTI_MAX = "dti_max"
    LOAN_AMOUNT_MAX = "loan_amount_max"
    MINIMUM_INCOME = "minimum_income"
    MINIMUM_TENURE = "minimum_tenure"
    HIGH_VALUE_REVIEW = "high_value_review"
    REQUIRED_DOCUMENT = "required_document"


class AffordabilityResult(BaseModel):
    dti: Decimal
    disposable_income: Decimal
    breach: bool
    threshold: Optional[Decimal] = None
    monthly_gross_income: Decimal
    monthly_obligations: Decimal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dti": float(self.dti),
            "disposable_income": float(self.disposable_income),
            "breach": self.breach,
            "threshold": float(self.threshold) if self.threshold is not None else None,
            "monthly_gross_income": float(self.monthly_gross_income),
            "monthly_obligations": float(self.monthly_obligations),
        }


class RuleEvaluationResult(BaseModel):
    rule_id: str
    rule_type: str
    passed: bool
    threshold_value: Any
    actual_value: Any
    operator: str
    message: str
    is_mandatory_eligibility: bool = False
    requires_human_review: bool = False


class UnderwritingDecisionResult(BaseModel):
    ai_recommendation: Optional[str] = None
    decision_status: str = "DETERMINED"
    unable_reason: Optional[str] = None
    human_review_required: bool = False
    affordability: AffordabilityResult
    rule_results: List[RuleEvaluationResult] = Field(default_factory=list)
    risk_flags: List[Dict[str, Any]] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
