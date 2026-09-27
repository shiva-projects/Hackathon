# Transaction Dispute & Fraud Triage Copilot (AAIE_AGT_001_BFS)
> **Agentic AI Engineer Pathway — Cross-Cutting Capstone Hackathon**  
> *Domain*: Banking & Financial Services · *Specification*: `AAIE_AGT_001_BFS` (100 Marks / 22 Rubric Parameters)

---

## 📢 Provider Architecture & Resilience

> **Google Gemini as Primary Model**: In accordance with the competition specification, Google Gemini (`gemini-2.0-flash`) is configured as the primary LLM provider.
> 
> **Rate Limit Resilience**: The system features automated dual-provider resolution in [`src/llm/provider_resolver.py`](src/llm/provider_resolver.py) and [`config/model_config.json`](config/model_config.json). If `GEMINI_API_KEY` is present, Gemini is invoked; if unset or throttled by tier limits, the runtime gracefully falls back to Groq (`openai/gpt-oss-20b` / `qwen/qwen3-32b`), ensuring uninterrupted multi-agent execution and non-blocking evaluation runs.

---

## 1. System Overview

The **Transaction Dispute & Fraud Triage Copilot** is a production-grade, observable, and governed multi-agent system built on **LangGraph**, **Model Context Protocol (MCP)**, **Agentic-RAG**, **Arize Phoenix**, and **Presidio Analyzer**.

### The Core Invariant
> **Code decides, LLM explains.**  
> LLMs hallucinate numbers and cannot guarantee strict card rail compliance. In this copilot:
> 1. **Chargeback Eligibility**: Enforced deterministically in pure Python (`120-Day Rule CR-01`).
> 2. **Reason Code Assignment**: Mapped deterministically from transaction data and claim types (Codes `10.4`, `13.1`, `13.3`, `10.5`).
> 3. **Fraud Risk Scoring**: Computed via deterministic rule evaluation against device, IP, and 3DS indicators.
> 4. **LLM Role**: Restricted exclusively to drafting human-readable dispute resolution notices citing verified rule chunks, followed by an automated **Self-Healing Reflection Loop (AC-12)**.

---

## 2. Quickstart & Fresh-Clone Recipe

### Step 1: Environment Setup
```bash
# Python 3.11+
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env` and set your preferred provider credentials:
```bash
cp .env.example .env
```
```env
# Primary Provider:
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# Fallback Provider:
GROQ_API_KEY=your_groq_api_key_here
```

---

## 3. The 3 Locked Commands (Execution & Verification)

Per hackathon NFR-02, the entire system is operated and verified through three deterministic commands:

### Command 1: Run Multi-Agent Dispute Test Suite
```bash
pytest tests/test_dispute_agents.py tests/test_dispute_rag.py tests/test_reflection_loop.py tests/test_memory_eviction.py -v
```
Executes all specialized worker nodes (`intake_agent`, `fraud_signal_agent`, `chargeback_eligibility_agent`, `resolution_draft_agent`), verifying typed `DisputeState`, conditional fraud escalation, 120-day short-circuiting, Agentic-RAG, reflection loop, and memory eviction.

### Command 2: Regenerate All Evidence & Golden Signals
```bash
python scripts/regenerate_evidence.py
```
1. Replays failure cases emitting exact Phoenix run and span citations matching [`docs/failure-analysis.md`](docs/failure-analysis.md).
2. Exports OpenInference spans directly to `traces/phoenix_spans.parquet`.
3. Derives latency distributions, token counts, and cost signals into `reports/golden_signals.json`.
4. Captures active Phoenix UI into `reports/dashboard.png` and tabular data into `reports/dashboard_data.csv`.
5. Runs `scripts/verify_evidence.py` to ensure artifact integrity.

### Command 3: Master Acceptance Verification Gate
```bash
python scripts/verify_acceptance_criteria.py
```
Performs automated verification of all 12 Acceptance Criteria (AC-01..12) and 8 Non-Functional Requirements (NFR-01..08):
```
============================================================
CAPSTONE ACCEPTANCE CRITERIA VERIFICATION (AAIE_AGT_001_BFS)
============================================================
Environment: Active provider resolved as 'groq'

AC-01   PASS   explicit typed DisputeState with invariant validation
AC-02   PASS   supervisor routes to intake, fraud-signal, chargeback-eligibility, resolution-draft
AC-03   PASS   conditional edges route on state: fraud escalation & 120-day short-circuit
AC-04   PASS   validated Pydantic models at all 4 agent handoff boundaries
AC-05   PASS   SqliteSaver checkpointer enables pause/resume of dispute workflows
AC-06   PASS   tiered memory (short-term working + long-term semantic) functional
AC-07   PASS   cross-session memory persistence verified with output log
AC-08   PASS   TTL-based expiry and importance-weighted LRU eviction implemented and tested
AC-09   PASS   MCP server exposes transaction_lookup, customer_profile, fraud_rules + dispute manual
AC-10   PASS   MCP client consumes server via langchain-mcp-adapters with transcript evidence
AC-11   PASS   Agentic-RAG indexes dispute corpus with SHA-256 chunk hashes (19 chunks)
AC-12   PASS   post-draft critique & self-healing reflection loop with OpenTelemetry trace span
NFR-01  PASS   no secrets committed; .env.example + .gitignore present
NFR-02  PASS   single command runs copilot; 2nd command regenerates evidence
NFR-03  PASS   untrusted free text quarantined in state['dispute_raw_text'] and XML tags
NFR-04  PASS   structured JSONL logs and OpenTelemetry parquet traces committed
NFR-05  PASS   Presidio Analyzer + financial regex sanitization active across all spans
NFR-06  PASS   architectural trade-off documented in docs/business-case.md §4.1
NFR-07  PASS   bounded retries, typed timeouts, and graceful fallbacks implemented
NFR-08  PASS   proposition distillation middleware compresses context >= 50%
------------------------------------------------------------
RESULT: READY FOR SUBMISSION (All 12 ACs & 8 NFRs Passed with Live Key)
```

---

## 4. Multi-Agent Graph Architecture

```
                  ┌──────────────────────┐
                  │     Input Guard      │ (PII Masking & Injection Check)
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │  Supervisor Router   │ ◄─────────────────────────┐
                  └──────────┬───────────┘                           │
                             │                                       │
     ┌───────────────────────┼───────────────────────┐               │
     │                       │                       │               │
┌────▼─────────────┐ ┌───────▼─────────────┐ ┌───────▼─────────────┐ │
│   Intake Agent   │ │ Fraud Signal Agent  │ │Chargeback Eligibility│ │
│ (MCP Lookup)     │ │ (Risk Scoring)      │ │(120-Day Rule CR-01) │ │
└────┬─────────────┘ └───────┬─────────────┘ └───────┬─────────────┘ │
     │                       │                       │               │
     └───────────────────────┼───────────────────────┘               │
                             │ (Next Worker)                         │
                  ┌──────────▼──────────────┐                        │
                  │  Resolution Draft Agent │                        │
                  │  (Agentic-RAG + Critique│                        │
                  │   & Reflection Loop)    │────────────────────────┘
                  └──────────┬──────────────┘
                             │ (All Nodes Completed)
                  ┌──────────▼──────────────┐
                  │         __end__         │
                  └─────────────────────────┘
```

---

## 5. Model Context Protocol (MCP) Integration (AC-09, AC-10)

The copilot integrates with a custom FastMCP server running in [`mcp_server/server.py`](mcp_server/server.py), consumed via [`langchain-mcp-adapters`](mcp_server/client.py):
- **Tools**:
  - `transaction_lookup(transaction_id: str)`: Fetches merchant, amount, category, 3DS status, and card details.
  - `customer_profile(customer_id: str)`: Returns customer tier, tenure, and historical fraud rate.
  - `fraud_rules(transaction_id: str)`: Evaluates transaction indicators and computes deterministic fraud score.
- **Resource**:
  - `dispute-handling-manual://rules`: Exposes full text of Card Dispute Handling Manual.
- **Transcript Logging**: Every MCP tool and resource invocation is captured in [`logs/mcp_transcript.jsonl`](logs/mcp_transcript.jsonl).

---

## 6. Agentic-RAG Corpus & Cryptographic Hashing (AC-11)

- **Corpus Files**: [`data/dispute_rules/CARD_dispute_handling_manual_v1.md`](data/dispute_rules/CARD_dispute_handling_manual_v1.md) and [`data/dispute_rules/CHARGEBACK_reason_codes_v1.md`](data/dispute_rules/CHARGEBACK_reason_codes_v1.md).
- **Manifest**: [`data/dispute_rules/dispute_manifest.json`](data/dispute_rules/dispute_manifest.json) parses the corpus into 19 discrete chunks with SHA-256 digests.
- **Verification**: `retrieve_dispute_rules()` verifies chunk text hashes dynamically at runtime to guarantee zero hallucinated citations.

---

## 7. Self-Healing Reflection Loop (AC-12)

The `resolution_draft_agent` executes a post-draft critique:
1. Validates that card network rule citations and cryptographic hashes are present.
2. Checks that the 120-day presentation timeframe is explicitly stated.
3. Asserts reason code matching (e.g. `10.4`, `13.1`).
4. On critique failure, the agent re-invokes the drafting loop with structured critique feedback, terminating cleanly within the `step_count <= 25` recursion guard.
5. Emits an OpenTelemetry span (`resolution_reflection_critique`) exported to `traces/phoenix_spans.parquet`.

---

## 8. Governance & Risk Pack

Complete enterprise compliance documentation is committed in `docs/`:
- [`docs/business-case.md`](docs/business-case.md): Problem statement, actors, success metrics, and AC-NN traceability.
- [`docs/risk-register.md`](docs/risk-register.md): 7 enterprise risks with mitigations and residual scores.
- [`docs/model-card.md`](docs/model-card.md): Model performance, data boundaries, and operational constraints.
- [`docs/compliance.md`](docs/compliance.md): Regulatory compliance mapping (Regulation E, Visa Core Rules, Fair Credit Billing Act).
- [`docs/threat-model.md`](docs/threat-model.md): Threat vectors and STRIDE analysis.
- [`docs/failure-analysis.md`](docs/failure-analysis.md): 4 documented failure modes with reproducible trace citations.
