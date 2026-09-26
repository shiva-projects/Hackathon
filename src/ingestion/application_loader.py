"""
Loan Application schema and loader with unit/currency normalization.
Per plan.md Section 8.3 & 14.9.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import json
from pathlib import Path


class Obligation(BaseModel):
    obligation_type: str = "loan"
    amount: Decimal = Field(..., ge=0, description="Obligation payment amount")
    period: Literal["monthly", "annual"] = "monthly"

    @property
    def monthly_amount(self) -> Decimal:
        if self.period == "annual":
            return (self.amount / Decimal("12")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return self.amount


class LoanApplication(BaseModel):
    application_id: str = Field(..., min_length=1)
    applicant_name: str = Field(..., min_length=1)
    requester_id: Optional[str] = None
    product: str = Field(..., description="e.g. personal_loan, home_loan, auto_loan")
    jurisdiction: str = Field(..., description="e.g. IN, UK, US")
    application_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")

    income_amount: Decimal = Field(..., gt=0, description="Gross income amount")
    income_period: Literal["monthly", "annual"] = "monthly"
    currency: str = Field("INR", min_length=3, max_length=3)

    requested_amount: Decimal = Field(..., gt=0)
    tenure_months: int = Field(..., gt=0, le=360)
    employment: str = Field(..., description="e.g. salaried, self_employed, unemployed")

    existing_obligations: List[Obligation] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)
    free_text: str = Field("", description="Untrusted applicant-supplied notes or explanations")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def validate_application_rules(self) -> "LoanApplication":
        # Disallow unreasonable loan amounts
        if self.requested_amount > Decimal("1000000000"):  # 1 Billion limit to prevent overflow
            raise ValueError("Requested amount exceeds platform system limits")
        return self

    @property
    def monthly_gross_income(self) -> Decimal:
        """Normalized monthly gross income in single currency basis."""
        if self.income_period == "annual":
            return (self.income_amount / Decimal("12")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return self.income_amount

    @property
    def total_monthly_obligations(self) -> Decimal:
        """Sum of all obligations normalized to monthly."""
        total = sum((ob.monthly_amount for ob in self.existing_obligations), Decimal("0"))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def to_facts_dict(self) -> Dict[str, Any]:
        """Convert validated application to normalized applicant_facts dictionary."""
        return {
            "application_id": self.application_id,
            "applicant_name": self.applicant_name,
            "requester_id": self.requester_id or self.applicant_name,
            "product": self.product,
            "jurisdiction": self.jurisdiction,
            "application_date": self.application_date,
            "income_amount": float(self.income_amount),
            "income_period": self.income_period,
            "monthly_gross_income": float(self.monthly_gross_income),
            "currency": self.currency,
            "requested_amount": float(self.requested_amount),
            "tenure_months": self.tenure_months,
            "employment": self.employment,
            "existing_obligations": [ob.model_dump(mode="json") for ob in self.existing_obligations],
            "total_monthly_obligations": float(self.total_monthly_obligations),
            "documents": self.documents,
        }


def load_application_from_dict(data: Dict[str, Any]) -> LoanApplication:
    """Validate and return a LoanApplication instance from dictionary."""
    return LoanApplication(**data)


def load_application_from_file(file_path: str | Path) -> LoanApplication:
    """Load and validate LoanApplication from JSON file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Application file not found: {file_path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return load_application_from_dict(data)
