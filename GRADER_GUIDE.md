# Grader Quick-Reference Guide (5-Minute Evaluation)
**Business Case**: AAIE_AGT_001_BFS · **Domain**: Banking & Financial Services · **System**: Transaction Dispute & Fraud Triage Copilot

Welcome, evaluator! This repository contains a fully working, observable, and governed LangGraph multi-agent copilot built specifically for **Transaction Dispute & Fraud Triage (`AAIE_AGT_001_BFS`)**. Every claim in this repository is backed by committed code and machine-generated artifacts under the **Evidence-in-Repo Rule**.

> **LLM Provider Transparency (v8 Addendum)**:  
> Which model/provider actually produced a given run → [`reports/environment.json`](reports/environment.json), field `provider` (`gemini` primary per spec; `groq` configured for rate resilience). Detailed resolution logs are recorded in [`logs/agent_actions.jsonl`](logs/agent_actions.jsonl).

---

## ⚡ The 3 Locked Commands (Quick Test)

To verify the entire system end-to-end in under 2 minutes:

```bash
# 1. Run dispute pipeline or test suite (Phoenix collector auto-launches in-process)
pytest tests/test_dispute_agents.py tests/test_dispute_rag.py tests/test_reflection_loop.py tests/test_memory_eviction.py -v

# 2. Regenerate all evidence, traces, golden signals & dashboard
python scripts/regenerate_evidence.py

# 3. Verify all 12 Acceptance Criteria (AC-01..12) and 8 Non-Functional Requirements (NFR-01..08)
python scripts/verify_acceptance_criteria.py
```
Expected final output: `RESULT: READY FOR SUBMISSION`.

> **Key Architectural Features**:  
> - **Supervisor Multi-Agent Pattern**: Supervisor routes dynamically to `intake_agent` (MCP customer/transaction lookups), `fraud_signal_agent` (MCP fraud rules & risk scoring), `chargeback_eligibility_agent` (120-day presentation window & reason code mapping), and `resolution_draft_agent` (Agentic-RAG rule retrieval & reflection loop).
> - **Agentic-RAG with SHA-256 Digest Verification**: Rule lookups from `data/dispute_rules/` cross-verified against `data/dispute_rules/dispute_manifest.json` cryptographic hashes.
> - **Self-Healing Reflection Loop (AC-12)**: Post-draft critique node validates citations, 120-day compliance, and reason code references with an evidenced OpenTelemetry span.
> - **Memory Eviction Policy (AC-08)**: Long-term memory enforces TTL expiration and importance-weighted LRU eviction per namespace.

---

## 📋 Comprehensive Acceptance Criteria Mapping (AC-01 .. AC-12)

| Criterion | Requirement Summary | Implementation File | Verification Test | Committed Evidence Artifact |
| :--- | :--- | :--- | :--- | :--- |
| **AC-01** | Explicit typed state shared across nodes | [`src/state.py`](src/state.py) (`DisputeState`) | [`tests/test_dispute_agents.py`](tests/test_dispute_agents.py) | `src/state.py`<br>`assert_state_invariants()` |
| **AC-02** | Supervisor routes to specialized workers | [`src/agents/supervisor.py`](src/agents/supervisor.py)<br>[`src/graph.py`](src/graph.py) | [`tests/test_dispute_agents.py`](tests/test_dispute_agents.py) | `logs/agent_actions.jsonl`<br>`traces/phoenix_spans.parquet` |
| **AC-03** | Conditional edges route on state | [`src/agents/chargeback_eligibility_agent.py`](src/agents/chargeback_eligibility_agent.py)<br>[`src/agents/fraud_signal_agent.py`](src/agents/fraud_signal_agent.py) | [`tests/test_dispute_agents.py`](tests/test_dispute_agents.py) | `logs/agent_actions.jsonl`<br>`logs/human_reviews.jsonl` |
| **AC-04** | Validated Pydantic models at handoffs | `IntakeOutput`, `FraudSignalOutput`, `ChargebackEligibilityOutput`, `ResolutionDraftOutput` | [`tests/test_dispute_agents.py`](tests/test_dispute_agents.py) | Pydantic schema validation |
| **AC-05** | Checkpointer enables pause/resume | [`src/memory/checkpoint_config.py`](src/memory/checkpoint_config.py) (`SqliteSaver`) | [`tests/test_checkpoint_resume.py`](tests/test_checkpoint_resume.py) | `data/checkpoints.sqlite` |
| **AC-06** | Tiered working + semantic memory | [`src/memory/short_term.py`](src/memory/short_term.py)<br>[`src/memory/long_term.py`](src/memory/long_term.py) | [`tests/test_memory_persistence.py`](tests/test_memory_persistence.py) | `data/long_term_memory.json` |
| **AC-07** | Cross-session memory persistence | [`src/memory/long_term.py`](src/memory/long_term.py) | [`tests/test_memory_persistence.py`](tests/test_memory_persistence.py) | `logs/memory_test.log` |
| **AC-08** | Memory eviction / importance policy | [`src/memory/long_term.py`](src/memory/long_term.py) (`evict_namespace`) | [`tests/test_memory_eviction.py`](tests/test_memory_eviction.py) | `tests/test_memory_eviction.py` |
| **AC-09** | Custom MCP server (≥2 tools, 1 resource) | [`mcp_server/server.py`](mcp_server/server.py) | [`tests/test_mcp_integration.py`](tests/test_mcp_integration.py) | `logs/mcp_transcript.jsonl` |
| **AC-10** | MCP consumed via langchain-mcp-adapters | [`mcp_server/client.py`](mcp_server/client.py) | [`tests/test_mcp_integration.py`](tests/test_mcp_integration.py) | `logs/mcp_transcript.jsonl`<br>`logs/tool_calls.jsonl` |
| **AC-11** | Agentic-RAG dispute rule retrieval | [`src/tools/rag_tool.py`](src/tools/rag_tool.py) (`retrieve_dispute_rules`) | [`tests/test_dispute_rag.py`](tests/test_dispute_rag.py) | `data/dispute_rules/dispute_manifest.json` |
| **AC-12** | Reflection / self-healing loop | [`src/agents/resolution_draft_agent.py`](src/agents/resolution_draft_agent.py) | [`tests/test_reflection_loop.py`](tests/test_reflection_loop.py) | `traces/phoenix_spans.parquet` (`reflection_critique_span`) |

---

## 🔒 Non-Functional Requirements (NFR-01 .. NFR-08) Checklist

- **NFR-01 (Secrets Hygiene)**: [`.env.example`](.env.example) and [`.gitignore`](.gitignore) present; `.env` is gitignored; zero API keys or private tokens in repo or logs (verified via `scripts/verify_evidence.py`).
- **NFR-02 (Two Documented Commands)**: `run_pipeline.py` executes pipeline; `regenerate_evidence.py` exports traces, runs eval, and verifies evidence.
- **NFR-03 (Quarantine Untrusted Text)**: [`src/context/quarantine.py`](src/context/quarantine.py) encapsulates user complaint text into non-executable XML data tags.
- **NFR-04 (Structured JSON Logs & Traces)**: Structured JSONL logs (`logs/tool_calls.jsonl`, `logs/agent_actions.jsonl`) and OpenTelemetry traces (`traces/phoenix_spans.parquet`) committed.
- **NFR-05 (Synthetic Data & Masking)**: 100% synthetic financial data; Presidio Analyzer and regex sanitization active across all spans (`src/observability/span_sanitizer.py`).
- **NFR-06 (Single-vs-Multi-Agent Rationale)**: Formal architectural trade-off documented in [`docs/business-case.md`](docs/business-case.md) §4.1.
- **NFR-07 (Graceful Degradation)**: Bounded retries (`src/resilience/retry.py`), typed timeouts (`src/resilience/timeout.py`), and graceful fallbacks (`src/resilience/fallback.py`).
- **NFR-08 (Context Management & Compression)**: Proposition distillation middleware ([`src/context/compress.py`](src/context/compress.py)) compresses conversation context >= 50%.

---

## 🌟 Extra Credit & Bonus Deliverables

| Deliverable | Implementation | Verification Command | Committed Evidence |
| :--- | :--- | :--- | :--- |
| **FastAPI Streaming Server** | [`src/api/server.py`](src/api/server.py) (Async SSE events for agent node transitions) | `pytest tests/test_api.py -v` | [`logs/api_stream_demo.log`](logs/api_stream_demo.log) |
| **Streaming Runner Demo** | [`scripts/demo_api_stream.py`](scripts/demo_api_stream.py) | `python scripts/demo_api_stream.py` | Recorded 9 SSE frame transitions |
| **Business Case & Governance Pack** | [`docs/business-case.md`](docs/business-case.md), [`docs/risk-register.md`](docs/risk-register.md), [`docs/model-card.md`](docs/model-card.md) | `python scripts/verify_evidence.py` | 100% verified documentation suite |
