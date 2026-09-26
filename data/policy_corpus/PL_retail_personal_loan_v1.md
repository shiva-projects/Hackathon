---
policy_id: PL-001
version: v1.0
product: personal_loan
jurisdiction: IN
effective_from: "2025-01-01"
effective_to: "2025-12-31"
rules:
  - rule_id: PL-07-v1
    rule_type: dti_max
    value: 0.40
    operator: "<="
    unit: ratio
  - rule_id: PL-12-v1
    rule_type: loan_amount_max
    value: 1000000.0
    operator: "<="
    unit: amount
  - rule_id: PL-15-v1
    rule_type: minimum_income
    value: 20000.0
    operator: ">="
    unit: monthly_amount
  - rule_id: PL-DOC-01-v1
    rule_type: required_document
    value: identity_proof
    operator: contains
    unit: document
---

# Personal Lending Underwriting Policy (v1.0 - Expired) - India Retail Banking

## Section 1: Overview
Historical personal lending guidelines for calendar year 2025. This policy expired on December 31, 2025 and is no longer valid for 2026 applications.

## Section 2: Affordability Criteria (Chunk: chunk-dti-v1-001)
Under expired Rule PL-07-v1, the maximum permitted Debt-to-Income (DTI) ratio was 40% with a maximum loan ceiling of INR 1,000,000.
