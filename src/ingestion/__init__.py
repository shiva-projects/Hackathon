"""Ingestion module for Loan Origination Copilot."""
from src.ingestion.application_loader import (
    LoanApplication,
    Obligation,
    load_application_from_dict,
    load_application_from_file,
)

__all__ = [
    "LoanApplication",
    "Obligation",
    "load_application_from_dict",
    "load_application_from_file",
]
