# Loan Origination & Underwriting Copilot — Compliance Mapping

This document maps regulatory obligations under the **EU Artificial Intelligence Act (EU AI Act)**, the **NIST Artificial Intelligence Risk Management Framework (NIST AI RMF 1.0)**, and the **Digital Personal Data Protection (DPDP) Act** directly to committed implementation controls, tests, and evidence artifacts in this repository.

---

## 1. EU AI Act (Regulation (EU) 2024/1689)
*Classification: High-Risk AI System under Annex III, Point 5(b) (AI systems intended to be used to evaluate the creditworthiness of natural persons or establish their credit score).*

| Article & Requirement | Implementation Strategy | Committed Evidence Artifact / Control File |
| :--- | :--- | :--- |
| **Article 9: Risk Management System**<br>Continuous iterative risk management process throughout lifecycle. | Formal risk identification, categorizing failure modes, likelihood, impact, and mitigations. | [`docs/risk-register.md`](risk-register.md)<br>[`docs/threat-model.md`](threat-model.md)<br>[`docs/failure-analysis.md`](failure-analysis.md) |
| **Article 10: Data & Data Governance**<br>Training and testing data must be relevant, representative, free of errors, and complete. | 100% synthetic, deterministic test fixtures covering approvals, breaches, declines, and boundary conditions. | [`data/sample_applications/`](../data/sample_applications)<br>[`scripts/validate_policy_corpus.py`](../scripts/validate_policy_corpus.py)<br>[`tests/test_application_schema.py`](../tests/test_application_schema.py) |
| **Article 12: Record-Keeping & Logging**<br>Automatic recording of events to ensure traceability and auditability. | Dual-write unified audit trail logging every tool call, agent action, MCP request, and human review with timestamps. | [`src/observability/unified_logger.py`](../src/observability/unified_logger.py)<br>[`logs/unified_trace.jsonl`](../logs/unified_trace.jsonl)<br>[`logs/tool_calls.jsonl`](../logs/tool_calls.jsonl) |
| **Article 13: Transparency & Provision of Information**<br>Operation must be sufficiently transparent for users to interpret system output. | Every recommendation includes a detailed rationale citing verifiable policy clause IDs and exact rule thresholds. | [`src/tools/rag_tool.py`](../src/tools/rag_tool.py)<br>[`tests/test_policy_citations.py`](../tests/test_policy_citations.py)<br>[`docs/model-card.md`](model-card.md) |
| **Article 14: Human Oversight**<br>System must enable human-in-the-loop oversight to prevent or minimize risks. | Copilot produces `ai_recommendation` only; loans with breaches or values > £25,000 mandate human sign-off via `--review` CLI. | [`src/domain/decisions.py`](../src/domain/decisions.py)<br>[`logs/human_reviews.jsonl`](../logs/human_reviews.jsonl)<br>[`docs/output-risk.md`](output-risk.md) |
| **Article 15: Accuracy, Robustness & Cybersecurity**<br>Resilience against errors, loops, timeouts, and adversarial prompt attacks. | Deterministic Decimal math, circuit breakers, prompt injection quarantine, and recursion limit guards. | [`src/domain/calculations.py`](../src/domain/calculations.py)<br>[`src/context/quarantine.py`](../src/context/quarantine.py)<br>[`tests/test_llm_cannot_override_rules.py`](../tests/test_llm_cannot_override_rules.py)<br>[`tests/test_loops.py`](../tests/test_loops.py) |

---

## 2. NIST AI Risk Management Framework (NIST AI RMF 1.0)

| Core Function | Sub-category & Action | Committed Evidence Artifact |
| :--- | :--- | :--- |
| **GOVERN 1.1** | Policies and procedures established for AI decision oversight and accountability. | [`src/state.py`](../src/state.py) (strict terminal state invariants)<br>[`docs/output-risk.md`](output-risk.md) |
| **GOVERN 1.2** | Legal and regulatory requirements mapped to engineering specifications. | [`docs/compliance.md`](compliance.md)<br>[`GRADER_GUIDE.md`](../GRADER_GUIDE.md) |
| **MAP 1.1** | Context of deployment, intended users, and limitations documented. | [`docs/model-card.md`](model-card.md)<br>[`docs/architecture.md`](architecture.md) |
| **MEASURE 2.2** | Quantitative evaluation of system accuracy, routing, and hallucination rates. | [`reports/eval_report.json`](../reports/eval_report.json)<br>[`scripts/run_eval.py`](../scripts/run_eval.py)<br>[`reports/golden_signals.json`](../reports/golden_signals.json) |
| **MEASURE 2.5** | Failure modes and unexpected behaviors benchmarked and analyzed. | [`docs/failure-analysis.md`](failure-analysis.md)<br>[`scripts/reproduce_failure.py`](../scripts/reproduce_failure.py) |
| **MANAGE 1.1** | Risk mitigation mechanisms activated for degraded operational modes. | [`src/resilience/fallback.py`](../src/resilience/fallback.py)<br>[`src/resilience/timeout.py`](../src/resilience/timeout.py)<br>[`tests/test_resilience.py`](../tests/test_resilience.py) |

---

## 3. Data Protection & Privacy (DPDP / GDPR)

| Privacy Principle | Operational Control | Committed Evidence Artifact |
| :--- | :--- | :--- |
| **Data Minimization** | Context engineering selects only required fields per worker agent; raw application context is isolated. | [`src/context/select.py`](../src/context/select.py)<br>[`src/context/isolate.py`](../src/context/isolate.py)<br>[`tests/test_context_isolation.py`](../tests/test_context_isolation.py) |
| **PII Anonymization & Redaction** | Masking of national IDs, account numbers, and credit references across all outputs, OpenTelemetry spans, and log lines. | [`src/guardrails/output_guard.py`](../src/guardrails/output_guard.py)<br>[`src/observability/span_sanitizer.py`](../src/observability/span_sanitizer.py)<br>[`tests/test_output_pii_redaction.py`](../tests/test_output_pii_redaction.py)<br>[`tests/test_log_pii_redaction.py`](../tests/test_log_pii_redaction.py) |
| **Access Authorization & Partitioning** | Multi-tenant isolation ensuring applicants can never inspect peer applications; cross-session memory scoped strictly to applicant ID. | [`src/security/authorization.py`](../src/security/authorization.py)<br>[`src/memory/memory_write_policy.py`](../src/memory/memory_write_policy.py)<br>[`tests/test_authorization.py`](../tests/test_authorization.py)<br>[`tests/test_memory_isolation.py`](../tests/test_memory_isolation.py) |
| **Storage & Purpose Limitation** | Untrusted free text is quarantined and barred from long-term memory persistence; only verified facts are retained. | [`src/context/quarantine.py`](../src/context/quarantine.py)<br>[`tests/test_memory_persistence.py`](../tests/test_memory_persistence.py) |

---

## 4. Multi-Provider LLM Layer Regulatory Disclosure (v8 Addendum)

### Deviation from Stated Gemini-Only Rule
- **Description**: A secondary open-source-compatible model fallback (Groq: `qwen/qwen3-32b`) is configured to ensure operational continuity under primary API quota exhaustion or network isolation.
- **Provider Precedence**: Google Gemini (`gemini-2.0-flash`) remains primary and default. Groq is accessed strictly as an automated failover when `GEMINI_API_KEY` is absent or when Gemini API retries are exhausted.
- **Determinism Preservation**: The multi-provider switch strictly affects explanatory rationale generation; all mathematical affordability calculations, policy rules, and `ai_recommendation` decisions remain 100% deterministic and invariant across both providers.
- **Instructor Approval Status**: Formal written instructor approval artifact (`docs/instructor-approval-groq-fallback.md`) is pending submission; the architecture is implemented with explicit configuration gating in [`config/model_config.json`](../config/model_config.json) and verifiable logging of all `provider_resolution` and `provider_fallback` events in [`logs/agent_actions.jsonl`](../logs/agent_actions.jsonl).
- **Committed Controls & Evidence**:
  - Configuration: [`config/model_config.json`](../config/model_config.json)
  - Resolver: [`src/llm/provider_resolver.py`](../src/llm/provider_resolver.py)
  - Client & Fallback Engine: [`src/llm/client.py`](../src/llm/client.py)
  - Environment Record: [`reports/environment.json`](../reports/environment.json) (field `provider`)
  - Integration Tests: [`tests/test_model_provider_fallback.py`](../tests/test_model_provider_fallback.py) and [`tests/test_resilience.py`](../tests/test_resilience.py)

