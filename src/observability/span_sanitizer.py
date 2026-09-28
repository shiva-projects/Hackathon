"""
Span and data sanitizer for PII scrubbing.
Redacts income figures, account numbers, credit identifiers, emails, and phone numbers.
Per plan.md Section 6.1 & 6.2.
"""

import re
from typing import Any, Dict, List, Union


# Common PII regex patterns
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}|\d{10})\b")
ACCOUNT_PATTERN = re.compile(r"\b(?:ACC-?|AC-?|acc-?|\d{4}-)\d{4,12}\b")
CREDIT_ID_PATTERN = re.compile(r"\b(?:CR-?|cr-?|PAN-?|pan-?)[A-Z0-9]{8,12}\b")
AADHAAR_PATTERN = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

# Sensitive key names to redact or mask (Canonical Policy for NFR-05 & AC-06)
SENSITIVE_KEYS = {
    "income",
    "income_amount",
    "raw_income",
    "monthly_gross_income",
    "monthly_income",
    "monthly_obligations",
    "existing_obligations",
    "disposable_income",
    "account_number",
    "account_no",
    "credit_id",
    "credit_identifier",
    "pan_number",
    "aadhaar_number",
    "ssn",
    "phone",
    "email",
    "bank_account",
    "bank_account_number",
    "salary",
    "net_income",
}

# Presidio PII Analyzer integration (Microsoft Presidio)
import logging
logger = logging.getLogger(__name__)

_presidio_analyzer = None
_presidio_active = False
_presidio_model_name = "unavailable"
_presidio_initialized = False

def _ensure_presidio():
    global _presidio_analyzer, _presidio_active, _presidio_model_name, _presidio_initialized
    if _presidio_initialized:
        return
    _presidio_initialized = True
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        import spacy.util
        # Only load models that are actually installed locally to avoid blocking network downloads
        installed = [m for m in ("en_core_web_sm", "en_core_web_lg") if spacy.util.is_package(m)]
        models_to_try = installed if installed else ["en_core_web_sm"]
        for model_name in models_to_try:
            try:
                _provider = NlpEngineProvider(nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": model_name}],
                })
                _presidio_analyzer = AnalyzerEngine(nlp_engine=_provider.create_engine())
                _presidio_active = True
                _presidio_model_name = model_name
                logger.info("[Presidio] PII Analyzer initialized with spaCy %s.", model_name)
                return
            except Exception as inner_e:
                logger.debug("[Presidio] Could not load %s: %s — trying next model.", model_name, inner_e)
        _presidio_analyzer = None
        _presidio_active = False
        logger.warning("[Presidio] No spaCy model available; falling back to regex-only sanitizer.")
    except Exception as e:
        _presidio_analyzer = None
        _presidio_active = False
        logger.warning("[Presidio] Presidio analyzer unavailable (%s); fallback to robust domain regex sanitizer.", e)


def is_presidio_active() -> bool:
    """Returns True if Microsoft Presidio is active at runtime."""
    _ensure_presidio()
    return _presidio_active


def sanitize_text(text: str) -> str:
    """Redacts PII patterns from raw string text using domain rules + Microsoft Presidio."""
    if not isinstance(text, str):
        return str(text)

    sanitized = text

    # Layer 1: Financial domain specific account, credit, email, and phone patterns
    sanitized = ACCOUNT_PATTERN.sub("[REDACTED_ACCOUNT]", sanitized)
    sanitized = CREDIT_ID_PATTERN.sub("[REDACTED_CREDIT_ID]", sanitized)
    sanitized = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", sanitized)
    sanitized = PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
    sanitized = AADHAAR_PATTERN.sub("[REDACTED_AADHAAR]", sanitized)
    sanitized = SSN_PATTERN.sub("[REDACTED_SSN]", sanitized)
    sanitized = PAN_PATTERN.sub("[REDACTED_PAN]", sanitized)

    # Layer 2: Microsoft Presidio Named Entity & PII Analyzer (catches generic SSN, NHS, IBAN, etc.)
    if len(sanitized) >= 7 and ("@" in sanitized or any(c.isdigit() for c in sanitized)):
        _ensure_presidio()
        if _presidio_analyzer is not None:
            try:
                results = _presidio_analyzer.analyze(
                    text=sanitized,
                    entities=["EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", "UK_NHS", "CREDIT_CARD", "IBAN_CODE"],
                    language="en",
                )
                for r in sorted(results, key=lambda x: x.start, reverse=True):
                    if r.entity_type == "EMAIL_ADDRESS":
                        rep = "[REDACTED_EMAIL]"
                    elif r.entity_type == "PHONE_NUMBER":
                        rep = "[REDACTED_PHONE]"
                    elif r.entity_type in ("CREDIT_CARD", "IBAN_CODE"):
                        rep = "[REDACTED_ACCOUNT]"
                    else:
                        rep = f"[REDACTED_{r.entity_type}]"
                    sanitized = sanitized[:r.start] + rep + sanitized[r.end:]
            except Exception:
                pass

    return sanitized


SYSTEM_ID_KEYS = {
    "review_id",
    "run_id",
    "session_id",
    "application_id",
    "chunk_id",
    "rule_id",
    "source_file",
    "type",
    "status",
    "actor",
    "action",
    "tool_name",
    "timestamp",
    "step_id",
    "tool_call_id",
    "final_decision",
    "ai_recommendation",
    "decision",
}


def sanitize_data(data: Any) -> Any:
    """Recursively traverses dictionaries, lists, and primitives to mask sensitive fields."""
    if isinstance(data, dict):
        sanitized_dict = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if k_lower in SENSITIVE_KEYS:
                # Mask value
                sanitized_dict[k] = "[REDACTED_SENSITIVE]"
            elif k_lower in SYSTEM_ID_KEYS:
                sanitized_dict[k] = v
            else:
                sanitized_dict[k] = sanitize_data(v)
        return sanitized_dict
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, str):
        return sanitize_text(data)
    else:
        return data
