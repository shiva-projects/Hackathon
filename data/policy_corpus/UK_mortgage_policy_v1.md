---
policy_id: PL-MORT-UK-01
version: v1.0
product: mortgage
jurisdiction: UK
effective_from: "2026-01-01"
effective_to: "2026-12-31"
rules:
  - rule_id: UK-MORT-01
    rule_type: dti_max
    value: 0.35
    operator: "<="
    unit: ratio
  - rule_id: UK-MORT-02
    rule_type: loan_amount_max
    value: 500000.0
    operator: "<="
    unit: amount
  - rule_id: UK-MORT-DOC
    rule_type: required_document
    value: property_valuation
    operator: contains
    unit: document
---

# UK Residential Mortgage Underwriting Standards (v1.0)

## Section 1: Scope
Standards governing residential mortgage originations across the United Kingdom for 2026.

## Section 2: Affordability Criteria (Chunk: chunk-uk-mort-001)
Under Rule UK-MORT-01, the maximum total debt service ratio must not exceed 35.0% of verified sterling gross income. A certified property valuation report is strictly required.
