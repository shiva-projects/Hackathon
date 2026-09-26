# Grader Quick-Reference Guide (5-Minute Evaluation)
**Business Case**: BC-AAIE-HACK-02 · **Domain**: Banking & Finance · **System**: Loan Origination & Underwriting Copilot

Welcome, evaluator! This repository contains a fully working, observable, and governed LangGraph multi-agent copilot. Every claim in this repository is backed by committed code and machine-generated artifacts under the **Evidence-in-Repo Rule**.

> **LLM Provider Transparency (v8 Addendum)**:  
> Which model/provider actually produced a given run → [`reports/environment.json`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/reports/environment.json), field `provider` (`gemini` primary, `groq` fallback). Detailed resolution logs are recorded in [`logs/agent_actions.jsonl`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/logs/agent_actions.jsonl).

---

## ⚡ The 3 Locked Commands (Quick Test)

To verify the entire system end-to-end in under 2 minutes:

```bash
# 1. Run applications through the multi-agent copilot
python scripts/run_pipeline.py --application-dir data/sample_applications/

# 2. Regenerate all evidence, traces, golden signals & dashboard
python scripts/regenerate_evidence.py

# 3. Verify all AC-01..12 and NFR-01..06 criteria
python scripts/verify_acceptance_criteria.py
```
Expected final output: `RESULT: READY FOR SUBMISSION`.

---

## 📋 Comprehensive Acceptance Criteria Mapping

| Criterion | Summary & Requirement | Implementation File | Verification Test | Committed Evidence Artifact |
| :--- | :--- | :--- | :--- | :--- |
| **AC-01** | Policy retrieval & cited policy rule | [`src/policy/policy_selector.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/policy/policy_selector.py)<br>[`src/tools/rag_tool.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/tools/rag_tool.py) | [`tests/test_policy_citations.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_policy_citations.py) | `outputs/sample_results/APP-001.json`<br>`data/policy_corpus/PL_retail_personal_loan_v2.md` |
| **AC-02** | Affordability (DTI / disposable income) | [`src/domain/calculations.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/domain/calculations.py)<br>[`mcp_server/server.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/mcp_server/server.py) | [`tests/test_domain_logic.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_domain_logic.py) | `outputs/sample_results/APP-002.json` |
| **AC-03** | Recommendation & human review routing | [`src/domain/decisions.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/domain/decisions.py)<br>[`src/state.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/state.py) | [`tests/test_llm_cannot_override_rules.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_llm_cannot_override_rules.py) | `outputs/sample_results/APP-004.json`<br>`logs/human_reviews.jsonl` |
| **AC-04** | Intent classification & escalation | [`src/agents/intent_classifier.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/agents/intent_classifier.py)<br>[`src/agents/clarification.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/agents/clarification.py) | [`tests/test_routing.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_routing.py) | `outputs/sample_results/ambiguous_case.json`<br>`logs/agent_actions.jsonl` |
| **AC-05** | Tiered memory & cross-session recall | [`src/memory/short_term.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/memory/short_term.py)<br>[`src/memory/long_term.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/memory/long_term.py) | [`tests/test_memory_persistence.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_memory_persistence.py) | `logs/memory_test.log` |
| **AC-06** | Prompt injection defense & PII masking | [`src/guardrails/input_guard.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/guardrails/input_guard.py)<br>[`src/guardrails/output_guard.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/guardrails/output_guard.py) | [`tests/test_prompt_injection.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_prompt_injection.py)<br>[`tests/test_output_pii_redaction.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_output_pii_redaction.py) | `outputs/sample_results/injection_case.json` |
| **AC-07** | Machine-generated tool invocation log | [`src/observability/unified_logger.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/observability/unified_logger.py) | [`tests/test_tool_log_schema.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_tool_log_schema.py) | `logs/tool_calls.jsonl` |
| **AC-08** | Real failure mode analysis (≥3 cases) | [`scripts/reproduce_failure.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/scripts/reproduce_failure.py) | Reproduction script verified | [`docs/failure-analysis.md`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/docs/failure-analysis.md) |
| **AC-09** | Phoenix golden signals & dashboard | [`scripts/generate_golden_signals.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/scripts/generate_golden_signals.py) | Script derived from traces | `reports/golden_signals.json`<br>`reports/dashboard.png`<br>`reports/dashboard_data.csv` |
| **AC-10** | Input/output guardrails & audit trail | [`src/observability/unified_logger.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/observability/unified_logger.py) | [`tests/test_unified_log_consistency.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_unified_log_consistency.py) | `logs/agent_actions.jsonl`<br>`logs/unified_trace.jsonl` |
| **AC-11** | Governance pack complete & cited | Documented in `docs/` | [`scripts/verify_evidence.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/scripts/verify_evidence.py) | [`docs/risk-register.md`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/docs/risk-register.md)<br>[`docs/model-card.md`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/docs/model-card.md)<br>[`docs/compliance.md`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/docs/compliance.md)<br>[`docs/output-risk.md`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/docs/output-risk.md) |
| **AC-12** | DeepEval report & agent unit tests | [`scripts/run_eval.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/scripts/run_eval.py) | [`tests/test_routing.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_routing.py)<br>[`tests/test_loops.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_loops.py)<br>[`tests/test_tool_contracts.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/tests/test_tool_contracts.py) | `reports/eval_report.json` |

---

## 🔒 Non-Functional Requirements (NFR) Checklist

- **NFR-01 (Secrets Hygiene)**: [`.env.example`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/.env.example) and [`.gitignore`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/.gitignore) present; `.env` is gitignored; zero API keys or private tokens in repo or logs (verified via `scripts/verify_evidence.py`).
- **NFR-02 (Two Documented Commands)**: `run_pipeline.py` executes pipeline; `regenerate_evidence.py` exports traces, runs eval, and verifies evidence.
- **NFR-03 (Quarantine Untrusted Text)**: [`src/context/quarantine.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/context/quarantine.py) encapsulates user input into non-executable XML data tags.
- **NFR-04 (Async & Graceful Degradation)**: [`src/resilience/timeout.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/resilience/timeout.py) and [`src/resilience/fallback.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/resilience/fallback.py) ensure tool and model failures degrade gracefully to `UNABLE_TO_COMPLETE`.
- **NFR-05 (Synthetic Data & Masking)**: 100% synthetic data; zero plaintext national IDs or account numbers in logs or traces.
- **NFR-06 (Machine-Generated Evidence)**: Traces, golden signals, eval reports, and logs produced by committed Python scripts.

---

## 🌟 Extra Credit & Bonus Deliverables (Section 7.7 & 8.1 of qn.txt)

| Deliverable | Implementation | Verification Command | Committed Evidence |
| :--- | :--- | :--- | :--- |
| **FastAPI Streaming Server** | [`src/api/server.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/src/api/server.py) (Async SSE events for agent node transitions) | `pytest tests/test_api.py -v` | [`logs/api_stream_demo.log`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/logs/api_stream_demo.log) |
| **Streaming Runner Demo** | [`scripts/demo_api_stream.py`](file:///c:/Users/ashiv/OneDrive/Desktop/hackathon/scripts/demo_api_stream.py) | `python scripts/demo_api_stream.py` | Recorded 9 SSE frame transitions |

