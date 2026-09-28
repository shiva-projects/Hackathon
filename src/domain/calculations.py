"""
Deterministic Affordability and Financial Calculations.
Pure functions using Decimal arithmetic, per plan.md Section 4.4 & 14.14.
NO LLM CALLS HERE.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import List, Dict, Any, Union
from src.domain.models import AffordabilityResult

DTI_COMPARISON_TOLERANCE = Decimal("1e-6")


def to_decimal(val: Union[int, float, str, Decimal]) -> Decimal:
    """Safe conversion to Decimal."""
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def calculate_monthly_gross_income(income_amount: Union[Decimal, float, int], income_period: str) -> Decimal:
    """
    Computes monthly gross income:
    monthly_gross_income = income_amount / 12 if income_period == "annual" else income_amount
    """
    amt = to_decimal(income_amount)
    if amt <= Decimal("0"):
        raise ValueError(f"Income amount must be greater than zero; got {amt}")
    if income_period.lower() == "annual":
        return (amt / Decimal("12")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return amt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_monthly_obligations(existing_obligations: List[Dict[str, Any]]) -> Decimal:
    """
    Computes monthly obligations from list of obligations:
    monthly_obligations = sum(normalize_to_monthly(o) for o in existing_obligations)
    """
    total = Decimal("0.00")
    for ob in existing_obligations:
        amt = to_decimal(ob.get("amount", 0))
        if amt < Decimal("0"):
            raise ValueError(f"Obligation amount cannot be negative; got {amt}")
        period = ob.get("period", "monthly").lower()
        if period == "annual":
            monthly = (amt / Decimal("12")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            monthly = amt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total += monthly
    return total


def calculate_dti(monthly_obligations: Decimal, monthly_gross_income: Decimal) -> Decimal:
    """
    DTI = monthly_obligations / monthly_gross_income
    Stored and compared as Decimal ratio (e.g. 0.40).
    """
    if monthly_gross_income <= Decimal("0"):
        raise ValueError("Monthly gross income must be greater than zero to compute DTI")
    # Store with high precision (6 decimal places)
    return (monthly_obligations / monthly_gross_income).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def calculate_disposable_income(monthly_gross_income: Decimal, monthly_obligations: Decimal) -> Decimal:
    """disposable_income = monthly_gross_income - monthly_obligations"""
    return (monthly_gross_income - monthly_obligations).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compare_threshold(val: Decimal, threshold: Decimal, operator: str = "<=") -> bool:
    """
    Compares value against threshold with 1e-6 tolerance.
    """
    diff = val - threshold
    if operator == "<=":
        return diff <= DTI_COMPARISON_TOLERANCE
    elif operator == "<":
        return diff < -DTI_COMPARISON_TOLERANCE
    elif operator == ">=":
        return diff >= -DTI_COMPARISON_TOLERANCE
    elif operator == ">":
        return diff > DTI_COMPARISON_TOLERANCE
    elif operator == "==":
        return abs(diff) <= DTI_COMPARISON_TOLERANCE
    else:
        raise ValueError(f"Unsupported comparison operator: {operator}")


def compute_affordability(
    income_amount: Union[Decimal, float, int],
    income_period: str,
    existing_obligations: List[Dict[str, Any]],
    dti_max_threshold: Union[Decimal, float, str] = Decimal("0.40"),
) -> AffordabilityResult:
    """
    Computes complete AffordabilityResult deterministically.
    """
    monthly_income = calculate_monthly_gross_income(income_amount, income_period)
    monthly_debts = calculate_monthly_obligations(existing_obligations)
    dti_ratio = calculate_dti(monthly_debts, monthly_income)
    disp_income = calculate_disposable_income(monthly_income, monthly_debts)

    threshold = to_decimal(dti_max_threshold)
    # Breach if DTI > threshold (i.e. not compare_threshold(dti_ratio, threshold, "<="))
    breach = not compare_threshold(dti_ratio, threshold, "<=")

    return AffordabilityResult(
        dti=dti_ratio,
        disposable_income=disp_income,
        breach=breach,
        threshold=threshold,
        monthly_gross_income=monthly_income,
        monthly_obligations=monthly_debts,
    )
