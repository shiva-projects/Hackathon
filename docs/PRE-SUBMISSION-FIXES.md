# Pre-Submission Audit & Fix Checklist

This document details the code fixes, evidence remediation, and final verification steps completed following the comprehensive architectural review of the **Loan Origination & Underwriting Copilot (BC-AAIE-HACK-02)**.

---

## 1. Summary of Issues Identified & Actions Taken

| Category | Issue Identified | Resolution Status | Affected Files |
|---|---|---|---|
| **Citation Links** | 168 broken `file:///c:/Users/ashiv/...` absolute links | **RESOLVED**: Converted all 168 occurrences to clean repo-relative markdown paths (`../path/to/file` / `./path/to/file`) | `README.md`, `GRADER_GUIDE.md`, `docs/*.md` (8 files) |
| **DeepEval Integration** | DeepEval was not imported or called; metrics were hardcoded | **RESOLVED**: Wired real `deepeval.metrics.HallucinationMetric` & `FaithfulnessMetric` via `LLMTestCase` into `scripts/run_eval.py` | `scripts/run_eval.py` |
| **Token Usage & Cost** | Token counts were hardcoded constants (24500/4800) | **RESOLVED**: `scripts/generate_golden_signals.py` now aggregates real measured token usage from `logs/llm_calls.jsonl` | `scripts/generate_golden_signals.py` |
| **Repo Bloat** | `data/checkpoints.sqlite` was ~34MB containing 187 debug test sessions | **RESOLVED**: Vacuumed database down to 1.5MB preserving latest test threads; ensured `*.sqlite` and `*.zip` are in `.gitignore` | `data/checkpoints.sqlite`, `.gitignore` |
| **Model Provider Clarification** | Groq fallback risked reading as non-compliant with Gemini-Only rule | **RESOLVED**: Documented explicitly in `docs/model-card.md` that Gemini is the primary approved grading provider; Groq is secondary resilience only per v8 addendum | `docs/model-card.md` |
| **Verification Guard** | Verification scripts passed even when run without live LLM keys | **RESOLVED**: Added preflight guard in `scripts/verify_acceptance_criteria.py` that fails submission exit code if evidence was produced without a live key | `scripts/verify_acceptance_criteria.py` |
| **Secret Rotation Alert** | Uncommitted `.env` file contained an active Groq API key | **ACTION REQUIRED BY USER**: Revoke and rotate that Groq key immediately in the Groq console | `.env` |

---

## 2. Key Code Changes

### A. DeepEval Evaluation (`scripts/run_eval.py`)
- Integrated `deepeval` test cases (`LLMTestCase`) evaluating rationale prose against retrieved policy context.
- Measures `HallucinationMetric` (threshold 0.5) and `FaithfulnessMetric` (threshold 0.5) on cases with actual explanatory rationale.
- Replaced hardcoded numbers with measured scores and method metadata (`deepeval_method`, `deepeval_cases_evaluated`).

### B. Golden Signals Token Sourcing (`scripts/generate_golden_signals.py`)
- Reads measured input and output token counts directly from `logs/llm_calls.jsonl`.
- `src/llm/client.py` logs actual token counts returned by Google Gemini SDK (`usage_metadata.prompt_token_count` & `candidates_token_count`).
- Tracks token count source as `"measured"` in `reports/golden_signals.json`.

### C. Live Key Guard (`scripts/verify_acceptance_criteria.py`)
- Checks for presence of `GEMINI_API_KEY` or `GOOGLE_API_KEY`.
- If no live key is present, prints explicit diagnostic warnings and returns `Exit 1` to prevent accidental submission of fallback template data.

---

## 3. Final Step Required from User

The codebase and evidence verification tools are now fully wired to capture real LLM data. **To produce 100% compliant grading evidence:**

1. Open `.env` and set your real Gemini API key:
   ```env
   GEMINI_API_KEY=AIzaSy...your_real_gemini_key...
   GEMINI_MODEL=gemini-2.0-flash
   ```
2. (Recommended) Rotate your Groq API key in the Groq developer console since it was present in a shared environment.
3. Run the end-to-end evidence generation pipeline:
   ```powershell
   python scripts/run_pipeline.py --application-dir data/sample_applications/
   python scripts/regenerate_evidence.py
   ```
4. Verify acceptance criteria:
   ```powershell
   python scripts/verify_acceptance_criteria.py
   python scripts/verify_evidence.py
   ```
   Both commands should output `Exit 0` and `READY FOR SUBMISSION`.
