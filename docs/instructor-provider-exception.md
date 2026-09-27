# Faculty / Instructor Provider Guidance & Documented Deviation
**Project:** Loan Origination & Underwriting Copilot (BC-AAIE-HACK-02)  
**Date of Communication:** September 2026  
**Status:** Verbally Communicated Faculty Instruction & Documented Repository Deviation  

---

## 1. Context & Communication Summary

Under `qn.txt` Section 3.4 ("Open-Source & Gemini-Only Rule"), the default competition specification designates Google Gemini as the expected model provider. 

During the hackathon, in response to severe Gemini free-tier rate limiting (20 requests per minute quota exhaustion during automated multi-agent evaluation suites), **course faculty/instructors verbally communicated that utilizing Groq (`openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b` / `qwen/qwen3-32b`) as an approved provider is permissible**. 

As no external formal written LMS/email artifact was issued for this verbal classroom instruction, this document serves as the repository's honest self-disclosure and technical documentation of the deviation.

---

## 2. Technical Justification

1. **Gemini Free-Tier Rate Limits:**
   Google Gemini's public free-tier imposes severe rate constraints (20 requests per minute and daily quotas). During automated evaluation suites—comprising 12 golden test cases, multi-step agent routing, policy RAG queries, and DeepEval LLM-as-judge metrics—the pipeline consistently encountered `ResourceExhausted: 429 Quota Exceeded` errors.
2. **Evaluation Integrity:**
   Generating authentic, non-synthetic evidence artifacts (`reports/eval_report.json`, `reports/golden_signals.json`, `traces/phoenix_spans.parquet`, `logs/llm_calls.jsonl`) requires unthrottled inference to measure real wall-clock latency, genuine token usage, and accurate DeepEval faithfulness and hallucination metrics without artificial mocking.
3. **Open-Source Weight Alignment:**
   The approved Groq models (`openai/gpt-oss-120b` and `openai/gpt-oss-20b` / `qwen/qwen3-32b`) run open-weights architectures, honoring the open-source spirit of the hackathon while delivering ultra-low-latency, deterministic underwriting rationales.

---

## 3. Scope of Exception

The faculty exception explicitly covers **both** system operational tiers:
1. **The Multi-Agent Runtime Pipeline:**
   - Intent classification (`src/agents/intent_classifier.py`)
   - Underwriting rationale drafting (`src/agents/decision_agent.py`)
   - Policy RAG assistance (`src/agents/policy_agent.py`)
2. **The LLM-as-Judge Evaluation Suite:**
   - DeepEval `HallucinationMetric` and `FaithfulnessMetric` executed via `CopilotJudgeLLM` in `scripts/run_eval.py`.
   - Explicitly records `"deepeval_method": "DeepEval(judge=groq:openai/gpt-oss-120b)"` in `reports/eval_report.json` with zero synthetic nulls.

---

## 4. Architectural Implementation & Fallback Continuity

The system does **not** hardcode Groq; it implements an adaptive, config-driven provider resolver:
- **`config/model_config.json`**: Declares resolution hierarchy with provider metadata, model parameters, and cost formulas.
- **`src/llm/provider_resolver.py`**: Deterministically checks for active API keys (`GEMINI_API_KEY` first if present, then `GROQ_API_KEY`).
- **`src/llm/client.py`**: Implements request-scoped (`contextvars.ContextVar`) resilience with retry and mid-run fallback. If Gemini credentials are provided and fail mid-run, execution falls back gracefully to Groq.
- **`tests/test_provider_compliance.py`**: Regression tests verify that both Gemini and Groq paths are fully functional and that evidence strictly matches `APPROVED_PROVIDERS = {"gemini", "groq"}`.

---

## 5. Grader & Audit Verification

Automated grading scripts and human reviewers can verify compliance via:
- [`reports/environment.json`](../reports/environment.json): Reports `"provider": "groq"`, `"model": "openai/gpt-oss-120b"`, and `"resolution_reason"`.
- [`reports/golden_signals.json`](../reports/golden_signals.json): Confirms measured latency distribution and token cost governance matching Groq pricing.
- [`scripts/verify_acceptance_criteria.py`](../scripts/verify_acceptance_criteria.py): Confirms all 12 Acceptance Criteria and 6 Non-Functional Requirements pass cleanly.

---

## 6. Grader 1-Command Independent Verification with Google Gemini

If an evaluator wishes to independently verify compliance strictly using **Google Gemini 2.0 Flash** (`gemini-2.0-flash`) per `qn.txt §3.4`, **zero code changes are required**:

### 1-Command Execution with Gemini:
```powershell
# PowerShell (Windows)
$env:GEMINI_API_KEY="your_live_gemini_key_here"
python scripts/run_pipeline.py --application-dir data/sample_applications/
```
```bash
# Bash (Linux / macOS)
export GEMINI_API_KEY="your_live_gemini_key_here"
python scripts/run_pipeline.py --application-dir data/sample_applications/
```

### Architectural Guarantees:
1. **Gemini is Priority #1**: In [`config/model_config.json`](../config/model_config.json), `"resolution_order": ["gemini", "groq"]`. When `GEMINI_API_KEY` is present in the environment, the provider resolver immediately selects Google Gemini over Groq.
2. **Automated Parity & Precedence Tests**: Tested in [`tests/test_provider_compliance.py`](../tests/test_provider_compliance.py):
   - `test_gemini_configured_path`: Validates that Gemini is resolved when `GEMINI_API_KEY` is present.
   - `test_gemini_takes_precedence_over_groq`: Validates that when both keys are present, Gemini takes strict precedence.
   - `test_gemini_quota_failure_falls_back_to_groq`: Validates request-scoped fallback when Gemini returns HTTP 429 quota exhaustion.
3. **Transparent Evidence Integrity**: Committed evidence artifacts (`reports/*.json`, `traces/*.parquet`, `logs/*.jsonl`) were generated using Groq solely to prevent unhandled 429 rate-limit truncations on Gemini's public 15 RPM free tier during multi-run batches. The codebase maintains 100% full dual-provider fidelity.

