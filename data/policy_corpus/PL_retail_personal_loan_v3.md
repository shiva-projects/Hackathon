---
policy_id: PL-001
version: v3.0
product: personal_loan
jurisdiction: IN
effective_from: "2027-01-01"
effective_to: "2027-12-31"
rules:
  - rule_id: PL-07-v3
    rule_type: dti_max
    value: 0.45
    operator: "<="
    unit: ratio
  - rule_id: PL-12-v3
    rule_type: loan_amount_max
    value: 2000000.0
    operator: "<="
    unit: amount
  - rule_id: PL-15-v3
    rule_type: minimum_income
    value: 30000.0
    operator: ">="
    unit: monthly_amount
  - rule_id: PL-DOC-01-v3
    rule_type: required_document
    value: identity_proof
    operator: contains
    unit: document
  - rule_id: PL-DOC-02-v3
    rule_type: required_document
    value: income_statement
    operator: contains
    unit: document
---

# Personal Lending Underwriting Policy (v3.0 - Future Draft) - India Retail Banking

## Section 1: Overview
Upcoming personal lending framework scheduled to become effective on January 1, 2027.

## Section 2: Expanded Affordability Limits (Chunk: chunk-dti-v3-001)
Under forward policy Rule PL-07-v3, the maximum permitted Debt-to-Income (DTI) ratio is expanded to 45.0% (0.45) for eligible applicants with higher disposable income buffers.
