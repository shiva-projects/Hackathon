# Loan Origination & Underwriting Copilot — Master Implementation Checklist

This checklist tracks the implementation of BC-AAIE-HACK-02 per `qn.txt` and `plan.md` (v7).

---

## Phase 0: Environment, Scaffolding & Dependencies
- [x] Initialize repository structure (`src/`, `mcp_server/`, `data/`, `logs/`, `traces/`, `reports/`, `docs/`, `tests/`, `scripts/`, `outputs/`)
- [x] Create `.env.example` and ensure `.gitignore` covers `.env`, SQLite DBs, Chroma DBs, caches
- [x] Create `requirements.txt` with pinned versions
- [x] Create `reports/environment.json` and `reports/cost_config.json`
- [x] Verify environment dependencies (Python 3.11+, LangGraph, Phoenix, Google GenAI, etc.)

---

## Phase 1: Schemas, State Contract & Invariants
- [x] `src/state.py`: Implement `LoanState` TypedDict with explicit field split:
  - `ai_recommendation` vs `final_decision` vs `decision_status` vs `request_status`
  - Invariant validator function `assert_state_invariants(state)`
- [x] `src/ingestion/application_loader.py`: `LoanApplication` Pydantic schema with normalized income/obligation amount + period + currency
- [x] `tests/test_state_invariants.py`: Unit tests for terminal-state contracts (DETERMINED, UNABLE_TO_COMPLETE, REFUSED, IN_PROGRESS)
- [x] `tests/test_application_schema.py`: Unit tests for input validation and normalization

---

## Phase 2: Deterministic Domain Logic (No LLM)
- [x] `src/domain/models.py`: Data models for calculations, rule evaluations, decision outputs
- [x] `src/domain/calculations.py`: Pure functions using `Decimal` arithmetic:
  - `monthly_gross_income()`, `monthly_obligations()`, `dti()`, `disposable_income()`
- [x] `src/domain/rules.py`: Threshold evaluation against policy rules (dti_max, loan_amount_max, minimum_income, high_value_review, required_document)
- [x] `src/domain/decisions.py`: Sole writer of `ai_recommendation`, implementing exact decision precedence

---

## Phase 3: Policy Corpus & Deterministic Policy Selector
- [x] `data/policy_corpus/`: Synthetic lending policy documents with structured YAML frontmatter / metadata (`PL-001`, `PL-002`, etc., with v1 expired, v2 current, v3 future)
- [x] `src/policy/policy_metadata.py`: Parser conforming to formal `rule_type` schema
- [x] `src/policy/policy_selector.py`: Deterministic selector matching product, jurisdiction, and effective date window (`effective_from <= date < effective_to`), consuming MCP resource manifest
- [x] `scripts/validate_policy_corpus.py`: Pre-flight sanity validator for policy corpus integrity

---

## Phase 4: Custom MCP Server (≥2 Tools + 1 Resource)
- [x] `mcp_server/server.py`: Standard MCP stdio server with:
  - Tool 1: `get_policy_document`
  - Tool 2: `compute_affordability`
  - Resource: `policy-corpus://index` (returns full corpus manifest)
- [x] Wire MCP client using `langchain-mcp-adapters`
- [x] `tests/test_mcp_integration.py`: Verify both tools called, resource read, and resource manifest is causally load-bearing

---

## Phase 5: Observability & Unified Logging
- [x] `src/observability/unified_logger.py`: Single atomic write routing through `log_event()` to per-concern log AND `logs/unified_trace.jsonl`
- [x] `src/observability/span_sanitizer.py`: PII scrubber for Phoenix OpenTelemetry spans
- [x] `src/observability/tracing.py`: OpenInference / Phoenix tracer integration with `run_id`, `step_id`, `latency_ms`
- [x] Initialize log files: `logs/tool_calls.jsonl`, `logs/agent_actions.jsonl`, `logs/mcp_transcript.jsonl`, `logs/human_reviews.jsonl`, `logs/unified_trace.jsonl`
- [x] `tests/test_tool_log_schema.py`: Schema validation on every log line
- [x] `tests/test_unified_log_consistency.py`: Strict reconciliation between per-concern logs and unified trace

---

## Phase 6: Security, Guardrails & Authorization
- [x] `src/security/authorization.py`: `authorize(requester_id, application_id)` access control gate
- [x] `src/guardrails/input_guard.py`: Detect prompt injection, cross-applicant attempts, quarantine untrusted text
- [x] `src/guardrails/output_guard.py`: PII redaction (multiple representations) and recommendation language check (advisory vs final)
- [x] `tests/test_authorization.py`: Authorization tests against fixture table
- [x] `tests/test_prompt_injection.py`: Injection defense tests
- [x] `tests/test_cross_applicant_access.py`: Cross-applicant refusal tests
- [x] `tests/test_output_pii_redaction.py`: PII scrub in outputs
- [x] `tests/test_log_pii_redaction.py`: Literal values absent from all logs (including `review_reason`)
- [x] `tests/test_output_recommendation_language.py`: Ensures AI output never claims a final decision

---

## Phase 7: Resilience & Context Engineering
- [x] `src/resilience/retry.py`: Bounded async retry (`max_attempts=2`, backoff)
- [x] `src/resilience/timeout.py`: Hard timeouts (`MCP_TIMEOUT_SECONDS=10`, `GEMINI_TIMEOUT_SECONDS=20`)
- [x] `src/resilience/fallback.py`: Graceful failure to `UNABLE_TO_COMPLETE` with `GEMINI_FALLBACK_RATIONALE`
- [x] `src/context/`:
  - `write.py`, `select.py`, `compress.py`, `isolate.py`, `quarantine.py`
- [x] `tests/test_resilience.py`: Resilience under injected failures and timeouts
- [x] `tests/test_context_compression.py`: Real reduction (>50%) on stress application
- [x] `tests/test_context_isolation.py`: Isolation of raw context between agents

---

## Phase 8: Tiered Memory System
- [x] `src/memory/short_term.py`: Ephemeral message state
- [x] `src/memory/long_term.py`: Semantic memory with `applicant_id + memory_type` namespacing
- [x] `src/memory/memory_write_policy.py`: Gate ensuring only verified facts persist to long-term memory
- [x] `src/memory/checkpoint_config.py`: SQLite checkpointer persistence
- [x] `tests/test_memory_persistence.py`: Cross-session recall of verified facts; refusal to persist untrusted text
- [x] `tests/test_memory_isolation.py`: Strict isolation between applicants
- [x] `tests/test_checkpoint_resume.py`: Graph state restoration across process restarts

---

## Phase 9: Agents, RAG & LangGraph Assembly
- [x] `src/agents/intent_classifier.py`: 7-intent classification with allowed-path table
- [x] `src/agents/clarification.py`: Follow-up question generator for ambiguous intents
- [x] `src/agents/supervisor.py`: LangGraph supervisor routing based on classified intent and state
- [x] `src/agents/policy_agent.py`: Policy selector + targeted RAG
- [x] `src/agents/eligibility_agent.py`: MCP tool invocation + affordability computation
- [x] `src/agents/risk_agent.py`: Risk rule evaluation
- [x] `src/tools/rag_tool.py`: Targeted RAG restricted to selected policy chunks with `text_hash` verification
- [x] `src/graph.py`: LangGraph state graph with conditional edges, checkpointer, and recursion limits
- [x] `tests/test_routing.py`: Complete coverage of all 7 intent paths and allowed-path constraints
- [x] `tests/test_loops.py`: Recursion / runaway loop guards
- [x] `tests/test_tool_contracts.py`: Input/output schema validation for every tool
- [x] `tests/test_llm_cannot_override_rules.py`: Adversarial test proving Gemini cannot alter deterministic recommendation

---

## Phase 10: Synthetic Data & Golden Evaluation Fixtures
- [x] `data/sample_applications/`:
  - `APP-001.json` (clean approval)
  - `APP-002.json` (DTI breach / refer)
  - `APP-003.json` (missing docs / decline)
  - `APP-004.json` (high-value loan / human review)
  - `APP-011.json` (policy version selection test case)
  - `context_stress.json` (large history for compression test)
  - `ambiguous_case.json`, `out_of_scope_case.json`, `injection_case.json`, `cross_applicant_case.json`
- [x] `data/failure_cases/`:
  - `wrong_policy_selection.json`
  - `mcp_timeout.json`
  - `rag_poisoning.json`
  - `authorization_fixture.json`

---

## Phase 11: CLI Runners, Evaluation Harness & Utilities
- [x] `scripts/run_pipeline.py`: Main CLI supporting `--application`, `--application-dir`, `--resume-session`, `--clarification`, `--review`, `--reviewer-id`
- [x] `scripts/export_traces.py`: Exports Phoenix spans to `traces/phoenix_spans.parquet`
- [x] `scripts/generate_golden_signals.py`: Computes latency (thinking/acting/tool), tokens, cost into `reports/golden_signals.json`
- [x] `scripts/run_eval.py`: Golden set evaluation (routing accuracy, hallucination, faithfulness) into `reports/eval_report.json`
- [x] `scripts/reproduce_failure.py`: Deterministic replay of the 3 failure fixtures
- [x] `scripts/verify_evidence.py`: Automated artifact existence and cross-artifact consistency verifier
- [x] `scripts/verify_acceptance_criteria.py`: Automated AC-01..12 and NFR-01..06 checker
- [x] `scripts/regenerate_evidence.py`: The locked 2nd command deriving all evidence from the latest run
- [x] `scripts/show_evidence.py`: Read-only offline demo viewer

---

## Phase 12: Governance Pack & Documentation
- [x] `docs/risk-register.md`: OWASP/NIST categorized risks with committed control citations
- [x] `docs/model-card.md`: Gemini model details, synthetic data, failure modes
- [x] `docs/compliance.md`: EU AI Act, NIST AI RMF, DPDP mapping with engineering citations
- [x] `docs/output-risk.md`: Low/med/high output tiers, human-in-the-loop gating
- [x] `docs/architecture.md`: Data flow, per-node failure semantics table, component boundaries
- [x] `docs/threat-model.md`: T1–T10 threats mapped to concrete controls and tests
- [x] `docs/failure-analysis.md`: ≥3 real failures (wrong policy, MCP timeout, RAG poisoning) with Phoenix run_id/span_id, root cause, and fix
- [x] `docs/demo-runbook.md`: Timed demo scripts marked [INSPECT] and [RERUN]
- [x] `GRADER_GUIDE.md`: 5-minute pointer guide for AC-01..12 and NFR-01..06
- [x] `README.md`: Fresh-clone recipe, locked 3-command sequence, logging architecture, CLI contract

---

## Phase 13: Pipeline Execution, Trace Generation & Validation
- [x] Execute pipeline on all sample applications
- [x] Run `--review` CLI flow on human-review cases (`APP-004`)
- [x] Run `scripts/regenerate_evidence.py` to produce traces, golden signals, dashboard, eval report
- [x] Run full pytest suite across all layers (80 passed in 3.78s)
- [x] Run `scripts/verify_acceptance_criteria.py` and confirm `RESULT: READY FOR SUBMISSION`
