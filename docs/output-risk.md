# Loan Origination & Underwriting Copilot — Output Risk Classification & Governance

This document establishes the classification taxonomy for all copilot outputs, defining gating mechanisms, human-in-the-loop controls, and sample representations.

---

## 1. Output Risk Taxonomy

| Risk Tier | Definition & Trigger Criteria | System Gating & Control Mechanism | Permitted Terminal State |
| :--- | :--- | :--- | :--- |
| **Tier 1: Low Risk** | Informational queries, policy document summaries, general eligibility inquiries, and standard-value clean approvals meeting all policy thresholds without exception. | - Input/Output PII redaction.<br>- Advisory language verification (must not claim binding bank commitment).<br>- Automated processing permitted without mandatory underwriter hold. | `request_status = "COMPLETED"`<br>`decision_status = "DETERMINED"`<br>`ai_recommendation = "APPROVE"`<br>`human_review_required = false` |
| **Tier 2: Medium Risk** | Ambiguous applicant requests requiring clarification, minor documentation mismatches, border-line income verification, or low-confidence intent parsing. | - Execution paused via conditional edge to `clarification_node`.<br>- Follow-up clarification prompt returned to user.<br>- Resume flow supported via `--clarification` CLI flag. | `request_status = "IN_PROGRESS"`<br>`decision_status = "PENDING"`<br>`ai_recommendation = null` |
| **Tier 3: High Risk** | Adverse credit decisions (`DECLINE`), affordability breaches (DTI > threshold), high-value loan requests (> £25,000 / ₹2,500,000), prompt injection attacks, unauthorized cross-applicant access attempts, or downstream tool/model failures. | **Mandatory Human-in-the-Loop Gating or Hard Refusal**:<br>1. *Policy Breaches & High Value*: Gated behind `human_review_required = true`. Binding decision cannot be finalized without human officer approval via `python scripts/run_pipeline.py --review`.<br>2. *Security Violations*: Immediate hard refusal (`request_status = "REFUSED"`).<br>3. *System/Tool Outages*: Graceful degradation (`decision_status = "UNABLE_TO_COMPLETE"`). | `request_status = "COMPLETED"`<br>`decision_status = "DETERMINED"`<br>`ai_recommendation = "REFER"` or `"DECLINE"`<br>`human_review_required = true`<br>*(or `request_status = "REFUSED"`)* |

---

## 2. Gating Architecture & Human-in-the-Loop Contract

```
                     ┌───────────────────────────────┐
                     │   Applicant Request Ingestion  │
                     └───────────────┬───────────────┘
                                     │
                        [Input Guardrail & Auth]
                                     │
                ┌────────────────────┴────────────────────┐
                │                                         │
        [Security Breach]                        [Valid Request]
                │                                         │
                ▼                                         ▼
   ┌─────────────────────────┐               ┌─────────────────────────┐
   │ request_status: REFUSED │               │  Multi-Agent Evaluation │
   └─────────────────────────┘               └────────────┬────────────┘
                                                          │
                                                [Threshold Checks]
                                                          │
                             ┌────────────────────────────┴───────────────────────────┐
                             │                                                        │
                      [Standard Clean]                                    [Breach / High Value]
                             │                                                        │
                             ▼                                                        ▼
                ┌─────────────────────────┐                              ┌─────────────────────────┐
                │ Tier 1: Low Risk        │                              │ Tier 3: High Risk Gated │
                │ ai_rec: APPROVE         │                              │ ai_rec: REFER / DECLINE │
                │ human_review: false     │                              │ human_review: TRUE      │
                └─────────────────────────┘                              └────────────┬────────────┘
                                                                                      │
                                                                           [Human Reviewer CLI]
                                                                                      │
                                                                                      ▼
                                                                         ┌─────────────────────────┐
                                                                         │ final_decision Recorded │
                                                                         │ in human_reviews.jsonl  │
                                                                         └─────────────────────────┘
```

---

## 3. Sample Payloads by Tier

### Tier 1 (Low Risk): Clean Approval
```json
{
  "application_id": "APP-001",
  "request_status": "COMPLETED",
  "decision_status": "DETERMINED",
  "ai_recommendation": "APPROVE",
  "final_decision": null,
  "human_review_required": false,
  "affordability": {
    "monthly_gross_income": "5000.00",
    "monthly_obligations": "1000.00",
    "dti": "0.200000",
    "disposable_income": "4000.00",
    "breaches": []
  },
  "rationale": "Applicant satisfies all criteria under Retail Personal Loan Policy v2.0 (PL-001). Monthly debt-to-income ratio is 20.00%, well below the maximum allowable threshold of 45.00% (Rule PL-01). Minimum monthly income requirement of £1,500.00 is satisfied (Rule PL-02). Recommendation: APPROVE."
}
```

### Tier 2 (Medium Risk): Ambiguous Request (Clarification Needed)
```json
{
  "application_id": "APP-AMB-01",
  "request_status": "IN_PROGRESS",
  "decision_status": "PENDING",
  "ai_recommendation": null,
  "final_decision": null,
  "human_review_required": false,
  "clarification_prompt": "Could you please clarify whether you are requesting a personal loan eligibility evaluation, or seeking information regarding an existing application status?",
  "rationale": "Ambiguous intent detected. Routed to clarification node to gather necessary application context."
}
```

### Tier 3 (High Risk): Policy Breach Gated to Human Underwriter
```json
{
  "application_id": "APP-002",
  "request_status": "COMPLETED",
  "decision_status": "DETERMINED",
  "ai_recommendation": "REFER",
  "final_decision": null,
  "human_review_required": true,
  "affordability": {
    "monthly_gross_income": "3000.00",
    "monthly_obligations": "1600.00",
    "dti": "0.533333",
    "disposable_income": "1400.00",
    "breaches": [
      {
        "rule_id": "PL-01",
        "rule_type": "dti_max",
        "threshold": "0.450000",
        "actual": "0.533333",
        "description": "Debt-to-Income ratio exceeds policy limit"
      }
    ]
  },
  "rationale": "Applicant's DTI ratio of 53.33% breaches maximum allowable threshold of 45.00% under Rule PL-01. Mandatory referral for senior underwriting review."
}
```

### Tier 3 (High Risk): Security Violation Refusal
```json
{
  "application_id": "APP-INJ-01",
  "request_status": "REFUSED",
  "decision_status": "PENDING",
  "refusal_reason": "PROMPT_INJECTION_DETECTED",
  "ai_recommendation": null,
  "final_decision": null,
  "human_review_required": false,
  "rationale": "Adversarial prompt injection pattern detected in applicant free-text field. Processing halted."
}
```
