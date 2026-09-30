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


class HumanDecision(str, Enum):
    APPROVE = "APPROVE"
    REFER = "REFER"
    DECLINE = "DECLINE"


class IntentType(str, Enum):
    NEW_APPLICATION = "new_application"
    STATUS_CHECK = "status_check"
    DOCUMENT_QUESTION = "document_question"
    POLICY_QUESTION = "policy_question"
    AMBIGUOUS = "ambiguous"
    OUT_OF_SCOPE = "out_of_scope"
    SECURITY_SENSITIVE = "security_sensitive"


class IntentClassificationResult(BaseModel):
    intent: IntentType = Field(..., description="Classified user intent")
    reasoning: Optional[str] = Field(None, description="Optional classification justification")


class HumanReviewSubmission(BaseModel):
    application_id: str = Field(..., min_length=3, max_length=50, description="Target application ID")
    reviewer_id: str = Field(..., min_length=1, description="Reviewer employee/officer ID")
    decision: HumanDecision = Field(..., description="Binding human decision: APPROVE, REFER, or DECLINE")
    review_reason: str = Field(..., min_length=5, description="Non-empty justification for the human decision")
    conditions: Optional[List[str]] = Field(None, description="Optional conditions precedent")


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
