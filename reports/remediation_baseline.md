# Remediation Baseline Snapshot

- **Date**: 2026-09-30
- **Scope**: Loan Origination & Underwriting Copilot (BC-AAIE-HACK-02)

## 1. Python Compilation
Command: `python -m compileall src mcp_server scripts tests`
Result: Clean compilation across all modules (34 files in tests, scripts, mcp_server, src), 0 errors.

## 2. Test Suite Baseline
Command: `pytest -q`
Result:
- **135 passed**, 0 failed, 3 warnings in 324.52s.
- Dependencies intact.

## 3. Provider Configuration Baseline
- `config/model_config.json`: Resolution order `["gemini", "groq"]`.
- `reports/environment.json`: Active provider reported as `groq` with `openai/gpt-oss-120b`.
- `.env.example`: Currently exposes `LLM_PROVIDER=groq` override.

## 4. Current Evidence Files Snapshot
- `reports/evidence_manifest.json` (4,814 bytes)
- `reports/eval_report.json` (49,549 bytes)
- `reports/golden_signals.json` (1,434 bytes)
- `reports/cost_config.json` (1,128 bytes)
- `reports/dashboard.png` (60,628 bytes)
- `reports/dashboard_data.csv` (198 bytes)
- `logs/agent_actions.jsonl` (~2.01 MB)
- `logs/tool_calls.jsonl` (~1.21 MB)
- `logs/mcp_transcript.jsonl` (~449 KB)
- `logs/llm_calls.jsonl` (~324 KB)
- `logs/unified_trace.jsonl` (~4.41 MB)
- `traces/phoenix_spans.parquet` (418,380 bytes)

## 5. Behavioral Safety
No source code behavior modified during Phase 0 baseline capture.
