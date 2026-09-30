# Antigravity Implementation Checklist
## Loan Origination & Underwriting Copilot — Remediation Plan

### How to use this checklist

Implement **one phase at a time**. Do not start the next phase until the current phase passes its verification commands.

Rules for Antigravity:
- Inspect the existing code before changing it.
- Preserve working functionality unless a requirement explicitly conflicts with it.
- Do not add unrelated features.
- Do not silently change business semantics.
- After each phase: run targeted tests, run the relevant evidence generation/checks, and report exactly what changed.
- Prefer small, reviewable commits.
- Never fabricate test results, trace IDs, evidence, or metrics.
- Keep **Gemini as the primary model and Groq as fallback**.
- Deterministic underwriting logic remains deterministic Python; the LLM must not calculate financial metrics, select policy versions, or write the final AI recommendation.

---

# PHASE 0 — Baseline and safety snapshot

## Goal
Create a clean baseline before remediation.

### Checklist
- [x] Record current git status.
- [x] Record current commit SHA.
- [x] Run Python compilation.
- [x] Run the test suite and capture failures caused by missing dependencies separately from actual test failures.
- [x] Record current provider configuration.
- [x] Record current evidence files and their sizes/counts.
- [x] Do not modify application behavior in this phase.

### Suggested commands
```bash
git status
git rev-parse HEAD
python -m compileall src mcp_server scripts tests
pytest -q
```

### Acceptance
- [x] Baseline results are captured in a file such as `reports/remediation_baseline.md`.
- [x] No source behavior changed.

### Antigravity prompt
> Inspect the repository and create a remediation baseline only. Do not change application behavior. Record git SHA, git status, Python compilation result, pytest result, current model/provider configuration, and the main committed evidence artifacts. Separate environment/dependency failures from code/test failures. Create `reports/remediation_baseline.md`.

---

# PHASE 1 — Gemini primary / Groq fallback

## Goal
Make the faculty-approved provider hierarchy true in configuration, runtime, documentation, and tests.

### Problems to fix
- `.env.example` currently exposes Groq as the default.
- Model-card/compliance documentation describes Groq as primary.
- `LLM_PROVIDER` can override the configured priority and force Groq.

### Checklist
- [x] Set Gemini as the documented/default primary provider.
- [x] Keep Groq available as fallback.
- [x] Remove `LLM_PROVIDER=groq` from `.env.example`.
- [x] Define a neutral configuration that does not force Groq.
- [x] Ensure provider resolution uses Gemini first when Gemini is available.
- [x] Ensure transient Gemini failure can fall back to Groq.
- [x] Ensure deterministic underwriting outputs do not depend on which provider supplied the rationale.
- [x] Update `docs/model-card.md`.
- [x] Update `docs/compliance.md`.
- [x] Update any README/config documentation that still says Groq is primary.
- [x] Add tests for primary, fallback, and unavailable-provider behavior.

### Required tests
```text
1. Gemini configured + Groq configured -> Gemini selected.
2. Gemini transient failure + Groq configured -> Groq selected.
3. Gemini unavailable + Groq configured -> Groq selected.
4. Neither configured -> explicit failure/UNABLE_TO_COMPLETE path.
5. Provider choice does not alter deterministic DTI/affordability/recommendation.
```

### Acceptance
- [x] Default repository configuration is Gemini-first.
- [x] Groq remains available only as fallback.
- [x] Documentation and runtime agree.
- [x] Tests prove the hierarchy.

### Antigravity prompt
> Fix the provider architecture so Gemini is the primary model and Groq is the fallback, without removing Groq. Inspect `config/model_config.json`, `.env.example`, `src/llm/provider_resolver.py`, `src/llm/client.py`, `docs/model-card.md`, `docs/compliance.md`, and relevant tests. Make the default configuration Gemini-first, preserve request-scoped fallback behavior, remove contradictory Groq-primary documentation, and add/repair tests proving Gemini-first, Gemini-failure-to-Groq-fallback, and no-provider failure. Do not change deterministic underwriting semantics.

---

# PHASE 2 — MCP must be load-bearing

## Goal
Make actual MCP transport consumption mandatory for MCP functionality.

### Problems to fix
- MCP client silently bypasses the MCP server and imports the server implementation directly.
- MCP resource can also bypass transport.
- MCP failure therefore does not reliably produce `UNABLE_TO_COMPLETE`.

### Checklist
- [x] Remove direct server-function fallback from `mcp_server/client.py`.
- [x] Remove direct resource fallback/import path.
- [x] Introduce an explicit MCP transport exception, e.g. `MCPUnavailableError`.
- [x] Retry transient MCP failures according to existing retry policy.
- [x] Apply timeout handling.
- [x] After retry/timeout exhaustion, return/raise the explicit MCP failure.
- [x] Map MCP failure to `decision_status=UNABLE_TO_COMPLETE`.
- [x] Ensure MCP failure can never silently become APPROVE/REFER/DECLINE.
- [x] Preserve machine-generated MCP logs for successful and failed calls.
- [x] Add tests that deliberately make MCP unavailable.

### Required tests
```text
MCP success -> normal workflow continues.
MCP timeout -> retry -> UNABLE_TO_COMPLETE.
MCP connection failure -> retry -> UNABLE_TO_COMPLETE.
MCP resource unavailable -> UNABLE_TO_COMPLETE.
No direct server function is invoked when MCP transport fails.
```

### Acceptance
- [x] MCP is the real interoperability boundary.
- [x] Transport failure is fail-closed.
- [x] No direct import fallback remains in the MCP client/resource path.

### Antigravity prompt
> Refactor the MCP client so MCP transport is a real architectural dependency. Remove any direct imports/calls to `mcp_server.server` used as transport fallback. Introduce explicit MCP failure handling with retry and timeout, and map exhausted MCP failures to `decision_status=UNABLE_TO_COMPLETE`. Add tests that simulate MCP failure and prove underwriting does not continue to a business decision. Search the entire repository for remaining direct MCP bypasses and remove only those that violate this contract.

---

# PHASE 3 — Canonical run/evidence identity

## Goal
Every consequential event must be attributable to the exact execution.

### Required identity
Use clearly defined:
```text
run_id
session_id
application_id
trace_id
span_id
tool_call_id
step_id
attempt
```

### Checklist
- [x] Define one canonical execution-context model.
- [x] Decide and document the semantic difference between `run_id` and `session_id`.
- [x] Ensure MCP calls receive the actual `run_id`.
- [x] Ensure tool calls receive actual `run_id`.
- [x] Ensure Phoenix spans use the canonical `run_id`.
- [x] Ensure audit events use the canonical identifiers.
- [x] Ensure human-review records use the canonical identifiers.
- [x] Remove production defaults such as `default_run`, `RUN-MCP`, or `RUN-UNKNOWN` when required identity is missing.
- [x] Fail loudly for missing consequential execution identity.
- [x] Ensure each tool invocation has a stable `tool_call_id`.
- [x] Preserve `attempt` across retries.
- [x] Preserve `step_id`.

### Acceptance
- [x] No real execution event is written with `default_run`.
- [x] MCP logs can be tied to the originating graph run.
- [x] Phoenix/tool/audit records can be correlated.

### Antigravity prompt
> Create one canonical execution-context contract and propagate it through graph execution, MCP, tools, Phoenix tracing, audit logging, and human review. Required identifiers are run_id, session_id, application_id, trace_id, span_id, tool_call_id, step_id, and attempt where applicable. Remove silent production defaults such as `default_run`, `RUN-MCP`, and `RUN-UNKNOWN` for consequential events. Add tests proving that a single run produces correlated MCP, tool, audit, and trace records.

---

# PHASE 4 — Real checkpoint/resume

## Goal
Make `--resume-session` restore actual LangGraph state across process boundaries.

### Problems to fix
- Current CLI recreates initial state.
- Existing test manually copies state rather than proving process resume.

### Checklist
- [x] Identify the configured LangGraph checkpointer.
- [x] Persist state at the actual interruption point.
- [x] Implement a checkpoint lookup by the session/thread identifier.
- [x] Restore the checkpointed state in a new process.
- [x] Inject the clarification response only after state restoration.
- [x] Continue from the correct graph node.
- [x] Prevent duplicate execution of already-completed stages.
- [x] Persist final result after continuation.
- [x] Keep run/session identifiers consistent across both phases.
- [x] Rewrite the checkpoint test to use two actual process executions or equivalent isolated process boundaries.

### Acceptance test
```text
Process 1:
  submit ambiguous application
  graph pauses for clarification
  checkpoint exists
  process exits

Process 2:
  run --resume-session S1 --clarification "..."
  state is restored
  graph resumes
  final result is produced
```

### Antigravity prompt
> Implement true LangGraph checkpoint resume. Inspect `run_pipeline.py`, graph construction, checkpointer configuration, and checkpoint tests. `--resume-session` must load persisted state instead of calling `create_initial_state()` and pretending to resume. Implement the clarification flow across two separate process boundaries and rewrite the test so it proves real persistence, restoration, continuation, and finalization. Do not simulate resume with `state2 = dict(res1)`.

---

# PHASE 5 — Human review must be fail-closed

## Goal
No explicit human decision must ever become an approval by default.

### Checklist
- [x] Remove `decision = decision or "APPROVE"`.
- [x] Remove default review reason.
- [x] Accept exactly `APPROVE`, `REFER`, `DECLINE`.
- [x] Reject empty decision.
- [x] Reject empty reason.
- [x] Reject unknown decision values.
- [x] Ctrl-C/EOF leaves final decision unset.
- [x] Review records are written only after a valid explicit decision.
- [x] API and CLI use the same validation schema.
- [x] API supports `REFER`.
- [x] API and CLI share the same authorization function/policy.
- [x] Unauthorized reviewers cannot finalize decisions.
- [x] Human review cannot be bypassed for required review cases.

### Acceptance
- [x] Missing decision never equals APPROVE.
- [x] Invalid reviewer input cannot create a final decision.
- [x] CLI and API semantics match.

### Antigravity prompt
> Harden human review to be fail-closed. Remove all implicit/default approval behavior. Define one shared Pydantic review contract with `APPROVE | REFER | DECLINE` and a non-empty reason. Apply it consistently to CLI and FastAPI. Reuse one authorization policy in both paths. Add tests for empty decision, empty reason, invalid decision, Ctrl-C/EOF, unauthorized reviewer, REFER through API, and valid review persistence.

---

# PHASE 6 — Deterministic underwriting rule consistency

## Goal
Make business-rule definitions and decision precedence agree exactly.

### Main issue
`LOAN_AMOUNT_MAX` is documented as mandatory in the decision engine but implemented as human-review/non-mandatory in the rule definition.

### Checklist
- [x] Decide the intended rule semantics from the project specification.
- [x] Align `src/domain/rules.py` with `src/domain/decisions.py`.
- [x] Ensure maximum-loan breach follows the documented precedence.
- [x] Ensure human review remains required where the specification says so.
- [x] Add regression tests for:
  - [x] mandatory eligibility failure
  - [x] affordability breach
  - [x] high risk
  - [x] high-value review
  - [x] combinations of multiple violations
- [x] Confirm LLM never overrides deterministic recommendation.

### Acceptance
For the documented maximum-loan scenario:
```text
requested_amount > maximum
-> deterministic rule failure
-> expected AI recommendation
-> correct human-review state
```

### Antigravity prompt
> Reconcile the business-rule semantics between `src/domain/rules.py` and `src/domain/decisions.py`. Use the project specification as the source of truth. Do not guess. Explicitly define precedence for mandatory eligibility failure, affordability breach, high-risk flags, and high-value review. Add regression tests for single-rule and multi-rule combinations. Keep all recommendation logic deterministic and outside the LLM.

---

# PHASE 7 — Intent routing and status semantics

## Goal
Make the supervisor route based on user intent rather than incidental structured fields.

### Problems to fix
- Structured fields can force `new_application`.
- Intent parsing uses substring matching.
- Status path writes `COMPLETED` instead of retrieving actual status.

### Checklist
- [x] Classify sanitized user text first.
- [x] Do not let presence of income/requested amount automatically override intent.
- [x] Use structured model output, not substring matching.
- [x] Introduce a Pydantic intent model/enum.
- [x] Validate unknown/malformed LLM intent output.
- [x] Route each intent only to the intended capability.
- [x] `policy_question` retrieves policy.
- [x] `document_question` handles documents.
- [x] `status_check` reads existing state.
- [x] `new_application` performs underwriting.
- [x] `ambiguous` requests clarification.
- [x] `security_sensitive` invokes security handling.
- [x] `out_of_scope` is refused safely.
- [x] Status node must not manufacture COMPLETED state.

### Acceptance
- [x] "What is the DTI policy?" remains a policy question even when structured application fields exist.
- [x] Malformed LLM intent output does not route unpredictably.
- [x] Status check returns stored status.

### Antigravity prompt
> Refactor intent classification to be text-first and schema-driven. Replace substring matching with a typed/Pydantic intent response. Structured application facts may validate a new application but must not override an explicit user intent. Audit all routing edges against the project intent-to-capability contract. Fix the status path so it reads existing persisted/checkpoint state instead of setting `request_status=COMPLETED`. Add focused routing tests for all intent categories and ambiguous/security-sensitive cases.

---

# PHASE 8 — RAG reproducibility and exact chunk integrity

## Goal
Make local retrieval deterministic and verifiably tied to the canonical policy corpus.

### Problems to fix
- SentenceTransformer can fall back to network download.
- Chroma index existence check uses collection count instead of exact membership.
- Runtime chunk hash verification is weaker than canonical evidence verification.

### Checklist
- [x] Remove network-enabled embedding fallback.
- [x] Require local embedding artifact/model for offline runs.
- [x] If model missing, fail with a clear reproducibility error.
- [x] Verify exact candidate chunk IDs/metadata exist in Chroma.
- [x] Do not use `collection.count()` as membership proof.
- [x] Use one canonical source-section extraction function.
- [x] Hash canonical extracted text.
- [x] Compare canonical hash with manifest hash.
- [x] Record policy ID/version/hash in retrieval evidence.
- [x] Add offline/no-network test.

### Acceptance
- [x] Fresh run does not silently contact HuggingFace for embeddings.
- [x] Retrieved evidence is traceable to exact source content.
- [x] Wrong chunk or wrong hash fails closed.

### Antigravity prompt
> Make RAG strictly reproducible and local. Inspect `src/tools/rag_tool.py`, policy manifests, Chroma indexing, and evidence verification. Remove any fallback that can download the embedding model at runtime. Replace collection-count logic with exact chunk-ID/metadata membership validation. Reuse canonical source extraction for runtime hash verification. Add tests proving missing local model, missing chunk, and hash mismatch fail clearly.

---

# PHASE 9 — Evidence verifier: identity, not just counts

## Goal
Turn the evidence checker into a real integrity check.

### Problem
Counting records is not reconciliation.

### Checklist
- [x] Define stable event IDs for generated evidence.
- [x] Correlate component records to unified records.
- [x] Verify every component event appears exactly once in unified evidence where required.
- [x] Verify matching `run_id`.
- [x] Verify matching `tool_call_id` for tool events.
- [x] Verify matching `review_id` for human-review events.
- [x] Verify timestamps are parseable.
- [x] Verify attempts/steps are consistent.
- [x] Remove the misleading "perfectly reconciled" result when only counts match.
- [x] Add negative tests with same counts but mismatched records.

### Acceptance
This must fail:
```text
component X
  event_id=E1

unified
  event_id=E2
```

even if both files contain the same number of records.

### Antigravity prompt
> Upgrade `scripts/verify_evidence.py` from count-based reconciliation to record-level integrity validation. Define stable event identity, correlate component and unified records, validate run/tool/review identifiers, and add negative tests where record counts match but identities do not. Keep count checks as supplemental diagnostics, not proof of reconciliation.

---

# PHASE 10 — Async correctness and resource hygiene

## Goal
Remove hidden blocking from async execution and eliminate unsafe global monkeypatches.

### Checklist
- [x] Convert synchronous tool invocation in async nodes to async APIs where available.
- [x] Use `asyncio.to_thread()` only for unavoidable blocking local work.
- [x] Avoid unnecessary `ThreadPoolExecutor(max_workers=1)` + `asyncio.run()` bridges.
- [x] Keep one canonical async execution path.
- [x] Replace global `tempfile.TemporaryDirectory._cleanup` monkeypatch.
- [x] Handle resource shutdown explicitly.
- [x] Do not swallow cleanup exceptions indiscriminately.
- [x] Add targeted async behavior tests.

### Acceptance
- [x] No obvious blocking I/O/tool invocation remains inside async graph nodes.
- [x] No process-wide stdlib monkeypatch remains for tracing cleanup.
- [x] Cleanup failures are visible and diagnosable.

### Antigravity prompt
> Audit the async execution path. Remove synchronous calls from async graph nodes where async alternatives exist, use `asyncio.to_thread()` only for unavoidable blocking operations, and simplify sync wrappers. Remove the global monkeypatch of `tempfile.TemporaryDirectory._cleanup` and replace it with scoped resource lifecycle handling. Add tests for async tool execution and cleanup behavior.

---

# PHASE 11 — Test the real contracts, not the artifacts

## Goal
Make tests prove behavior end-to-end.

### Checklist
- [x] Add MCP failure integration test.
- [x] Add true two-process checkpoint/resume test.
- [x] Add human-review fail-closed tests.
- [x] Add provider hierarchy tests.
- [x] Add deterministic max-loan regression test.
- [x] Add intent/text-first routing tests.
- [x] Add status retrieval test.
- [x] Add RAG offline/reproducibility tests.
- [x] Add evidence record-correlation tests.
- [x] Add audit-trail correlation test.
- [x] Add guardrail refusal tests for prompt injection/cross-applicant/PII.
- [x] Run the full test suite with the documented environment.

### Acceptance
- [x] All targeted remediation tests pass.
- [x] Full suite passes in the documented environment.
- [x] No test "passes" merely because an artifact exists.
- [x] Tests exercise the runtime path they claim to protect.

### Antigravity prompt
> Review the entire test suite for tests that validate artifacts without proving runtime behavior. Replace weak tests with behavior-level tests for MCP failure, true process resume, provider fallback, human review, deterministic recommendation precedence, intent routing, status retrieval, RAG reproducibility, and evidence identity. Then run targeted and full pytest and report failures separately by root cause.

---

# PHASE 12 — Regenerate evidence from the repaired system

## Goal
Regenerate every graded artifact after the code fixes.

### Important
Do **not** hand-edit old evidence to make it look correct.

### Checklist
- [x] Start from clean generated outputs as required by the runbook.
- [x] Run the documented sample/fixture scenarios.
- [x] Generate Phoenix traces.
- [x] Generate MCP transcript.
- [x] Generate tool-invocation log.
- [x] Generate audit trail.
- [x] Generate failure analysis.
- [x] Generate golden signals.
- [x] Generate cost/latency dashboard and CSV.
- [x] Generate governance pack.
- [x] Generate evaluation report.
- [x] Generate updated evidence manifest.
- [x] Record real git commit SHA.
- [x] Verify all cited artifacts exist.
- [x] Verify all citations resolve.
- [x] Verify logs are run-correlated.
- [x] Verify sensitive values are not exposed.

### Acceptance
- [x] Evidence was generated from current committed code.
- [x] No stale Groq-primary claims remain.
- [x] No `default_run` records remain in the final evidence.
- [x] MCP failures show `UNABLE_TO_COMPLETE`.
- [x] Real resume scenario exists in evidence.
- [x] Human review evidence contains only explicit valid decisions.
- [x] Golden signals reflect regenerated data.

### Antigravity prompt
> After all remediation phases pass, regenerate the complete evidence set from the repaired code using the documented runbook. Do not hand-edit generated evidence. Record the actual git commit SHA. Validate trace/log/run correlation, policy citation resolution, PII sanitization, MCP failure behavior, checkpoint resume, human review, provider hierarchy, and evaluation outputs. Update the evidence manifest only from generated artifacts.

---

# FINAL GATE — Do not submit until every box is checked

## Architecture
- [x] Gemini is primary.
- [x] Groq is fallback.
- [x] LLM never owns deterministic underwriting decisions.
- [x] MCP is genuinely consumed over the MCP boundary.
- [x] MCP failure is fail-closed.
- [x] Checkpoint/resume works across process boundaries.
- [x] Intent routing is schema-driven and text-first.
- [x] Status check reads real persisted state.
- [x] RAG is offline/reproducible.
- [x] Memory semantics are documented honestly.

## Security
- [x] Input quarantine occurs before trust-sensitive execution.
- [x] Cross-applicant access is blocked.
- [x] Output PII is redacted.
- [x] Phoenix/tool/audit logs are sanitized.
- [x] Human review is authorized and fail-closed.
- [x] No secret is committed.

## Evidence
- [x] Every consequential event has a real run_id.
- [x] MCP evidence maps to the actual run.
- [x] Tool calls have stable IDs.
- [x] Unified trace reconciliation is record-level.
- [x] Failure analysis cites real run/span/tool evidence.
- [x] Phoenix-derived metrics come from regenerated traces.
- [x] Dashboard PNG and CSV correspond to the same run/data.
- [x] Evaluation report is regenerated from current code.
- [x] Evidence manifest contains actual commit SHA.
- [x] All citations resolve to committed artifacts.

## Tests
- [x] Full pytest passes in documented environment.
- [x] MCP failure test passes.
- [x] Checkpoint/resume test passes.
- [x] Provider hierarchy tests pass.
- [x] Human review fail-closed tests pass.
- [x] LOAN_AMOUNT_MAX regression test passes.
- [x] Intent routing tests pass.
- [x] Status retrieval test passes.
- [x] RAG reproducibility tests pass.
- [x] Evidence correlation negative tests pass.

---

# Recommended execution order

```text
PHASE 0  -> Baseline
PHASE 1  -> Gemini primary / Groq fallback
PHASE 2  -> MCP load-bearing
PHASE 3  -> Evidence identity
PHASE 4  -> Checkpoint/resume
PHASE 5  -> Fail-closed human review
PHASE 6  -> Deterministic business rules
PHASE 7  -> Intent + status
PHASE 8  -> RAG reproducibility
PHASE 9  -> Evidence verifier
PHASE 10 -> Async/resource hygiene
PHASE 11 -> Contract tests
PHASE 12 -> Regenerate evidence
FINAL GATE -> Submission
```

# One master Antigravity instruction

> You are implementing a remediation plan for a graded agentic AI underwriting system. Work strictly phase-by-phase from `PHASE 0` through `PHASE 12` in `antigravity_implementation_checklist.md`. For each phase: inspect the existing implementation first, make the smallest production-grade change that satisfies the phase, preserve unrelated functionality, run the specified tests, and stop if the acceptance criteria fail. Never fabricate evidence, metrics, traces, commit SHAs, or test results. Do not hand-edit generated evidence to hide failures. Treat the project specification as the source of truth. Keep Gemini as the primary model and Groq as the fallback. Keep deterministic underwriting calculations, policy selection, and `ai_recommendation` outside the LLM. At the end of each phase, report: files changed, behavior changed, tests run, test results, remaining risks, and whether the phase acceptance criteria passed.

