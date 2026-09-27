# Loan Origination & Underwriting Copilot (BC-AAIE-HACK-02)
> **Agentic AI Engineer Pathway — Cross-Cutting Capstone Hackathon**  
> *Domain*: Banking & Finance · *Evaluator*: Automated Review on Committed Evidence (100 Marks)

---

## 📢 Provider Exception (Documented Deviation from qn.txt §3.4)

> **Faculty/Instructor Authorization**: Per direct instructor guidance (September 2026), this submission uses **Groq** (`openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b` / `qwen/qwen3-32b`) as the primary LLM provider in place of Google Gemini.
> 
> **Rationale**: Google Gemini's public free-tier imposes severe rate constraints (20 requests/minute tier cap), causing spurious `429 Quota Exceeded` errors during full evidence regeneration and automated evaluation suites (12 benchmark test cases + DeepEval metrics). The faculty exception explicitly approves Groq for both the multi-agent runtime pipeline and the **DeepEval LLM-as-judge evaluation** (`groq:openai/gpt-oss-120b`), ensuring unthrottled, genuine evaluation.
> 
> **Dual-Provider Architecture**: The system retains dual-provider resolution: if `GEMINI_API_KEY` is present, it uses Gemini; otherwise, it resolves seamlessly to Groq. Detailed authorization: [`docs/instructor-provider-exception.md`](docs/instructor-provider-exception.md).

---

## 1. System Overview
The **Loan Origination & Underwriting Copilot** is a production-grade, observable, and governed multi-agent system built on **LangGraph**, **Model Context Protocol (MCP)**, **Groq / Google Gemini**, and **Arize Phoenix**.

### The Core Invariant
> **Code decides, LLM explains.**  
> Large Language Models hallucinate numbers and cannot guarantee regulatory compliance under adversarial pressure. In this system, all debt-to-income (DTI) calculations and affordability numbers are computed in **pure Python `Decimal` arithmetic** ([`src/domain/calculations.py`](src/domain/calculations.py)). Thresholds are strictly evaluated against structured policy metadata ([`src/domain/rules.py`](src/domain/rules.py)). Decisions are assigned solely by deterministic code ([`src/domain/decisions.py`](src/domain/decisions.py)). The LLM is invoked exclusively to draft human-readable explanatory rationales citing verified policy clauses.

---

## 2. Quickstart & Fresh-Clone Recipe

### Step 1: Environment Setup
```bash
# Recommended Python version: 3.11+
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install pinned dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env` and configure your API key:
```bash
cp .env.example .env
```
Ensure `.env` contains:
```env
# Preferred primary provider:
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# Optional secondary fallback (used only if GEMINI_API_KEY is unset or exhausted):
GROQ_API_KEY=
```
Set `GEMINI_API_KEY` (preferred) or `GROQ_API_KEY` (fallback) in `.env`. The pipeline prints and records which provider it resolved to at startup — check `reports/environment.json` if unsure which one ran.

*(Note: As verified by `scripts/verify_evidence.py` and `tests/test_authorization.py`, `.env` is covered by `.gitignore` and no secrets are committed to Git).*

---

## 3. Interactive Web Dashboard (Optional UI Layer)

> **Scope Note**: The primary required evaluation and pipeline execution interfaces are the **CLI runner (`scripts/run_pipeline.py`)** and the **FastAPI REST API (`src/api/server.py`)** conforming to the technical specification. The Streamlit web interface (`app.py`) is provided strictly as an **optional interactive demonstration and inspection layer** for human-in-the-loop review, visual state inspection, and live testing; it has no side effects on the core headless pipeline.

```bash
streamlit run app.py
```

### What You Can Do in the UI:
1. **Choose from Preset Test Applications**:
   - `APP-001`: Standard Clean Approval (healthy 18.2% DTI)
   - `APP-002`: Affordability DTI Breach (53.3% DTI > 40% policy threshold → `DECLINE`)
   - `APP-003`: Missing Mandatory Documentation (missing income proof → `REFER`)
   - `APP-004`: High-Value Loan (> £25,000 threshold → `REFER` to human underwriter)
   - `APP-011`: UK Jurisdiction Lending Policy v2.0
   - `injection_case`: Adversarial Prompt Injection Defense
   - `ambiguous_case`: Clarification Routing Loop
2. **Or Submit a Custom Application**:
   - Input custom applicant name, product, jurisdiction, monthly income, requested amount, tenure, existing obligations, and documents.
3. **Execute the Multi-Agent Underwriting Graph with Live Step-by-Step Visualization**:
   - Watch the interactive **Graphviz visual workflow diagram** animate in real-time, showing exactly which step is executing now (`⏳ EXECUTING NOW`), which stages are completed (`✅ DONE`), or if security refused (`🚫 REFUSED`).
   - Track live stage descriptions: `input_guard` (PII/Injection Screen) → `authorization_node` (Access Boundary) → `intent_classifier` → `supervisor` → `policy_agent` (RAG) → `eligibility_agent` (FastMCP & DTI) → `risk_agent` → `decision_node` (AI Rationale).
   - Inspect the **Recommendation Badge** (`APPROVE`, `REFER`, `DECLINE`, `REFUSED`).
   - View the **Pure Python Decimal Arithmetic** calculations (Net Disposable Income, EMI, DTI Ratio vs Threshold).
   - Inspect **Verifiable Policy Citations** (Clause ID, Source File, and SHA-256 cryptographic text hashes).
   - Read the **AI Explanatory Rationale** drafted by LLM citing policy clauses.
4. **Interactive Human-in-the-Loop (HITL) Review**:
   - For applications marked `REFER`, review the case, enter an underwriter override (`APPROVE` or `DECLINE`) with notes, and commit the decision directly to `logs/human_reviews.jsonl`.
5. **Inspect Live Observability**:
   - Expand the **Golden Signals & OpenTelemetry** drawer to view thinking/acting latencies, span counts, and cost metrics.

---

## 4. The 3 Locked Commands (Execution & Verification)

Per hackathon NFR-02 and evaluation instructions, the entire system is operated and verified through three deterministic commands:

### Command 1: Execute Applications Through Copilot Pipeline
```bash
python scripts/run_pipeline.py --application-dir data/sample_applications/
```
Runs all synthetic applications through the multi-agent graph, performing policy selection, affordability computation, risk screening, deterministic decision assignment, and LLM rationale generation. Structured outputs are committed to `outputs/sample_results/`.  
*Note*: The Phoenix OpenTelemetry collector server automatically starts in-process on `http://localhost:6006` if not already running (and can be monitored live at `http://localhost:6006`).

### Command 2: Regenerate Traces, Signals & Verification
```bash
python scripts/regenerate_evidence.py
```
Derives all downstream evidence from the completed run:
1. Exports Phoenix OpenTelemetry spans directly from the live collector to `traces/phoenix_spans.parquet` (with 39 OpenInference columns, `trace_source: "phoenix"`).
2. Executes the golden evaluation suite to produce `reports/eval_report.json`.
3. Derives latency percentiles (thinking/acting/tool), token counts, and cost estimates into `reports/golden_signals.json` (`trace_source: "phoenix"`).
4. Generates `reports/dashboard_data.csv` and captures genuine Phoenix collector UI into `reports/dashboard.png`.
5. Runs `scripts/verify_evidence.py` to assert artifact existence and cross-artifact consistency.

### Command 3: Master Acceptance Verification Gate
```bash
python scripts/verify_acceptance_criteria.py
```
Performs automated verification of all 12 Functional Acceptance Criteria (AC-01..12) and 6 Non-Functional Requirements (NFR-01..06), outputting:
```
==============================
CAPSTONE ACCEPTANCE VERIFICATION
==============================
AC-01 PASS   applicable policy selected + citation resolves
AC-02 PASS   DTI computed, threshold present, breach detected correctly
AC-03 PASS   recommendation generated, human review routed where required
AC-04 PASS   intent classified; ambiguous → clarified; out-of-scope → escalated
AC-05 PASS   context reused within run + recalled across session
AC-06 PASS   injection refused; cross-applicant refused; no PII in output/logs
AC-07 PASS   tool_calls.jsonl schema valid on every record
AC-08 PASS   ≥3 failures documented, citations resolve
AC-09 PASS   golden signals + dashboard present and sourced from real spans
AC-10 PASS   guardrails wired; audit trail present
AC-11 PASS   governance pack complete, citations resolve
AC-12 PASS   eval report + all 3 agent tests pass
NFR-01 PASS  no secrets committed; .env.example + .gitignore present
NFR-02 PASS  single command runs the copilot; a second regenerates traces + eval
NFR-03 PASS  untrusted free text quarantined, never executed as instructions
NFR-04 PASS  async tool/model calls; graceful degradation on failure
NFR-05 PASS  synthetic data; sensitive fields masked, never logged in plaintext
NFR-06 PASS  every evidence artifact machine-generated by committed code
RESULT: READY FOR SUBMISSION
```

---

## 5. Human-in-the-Loop CLI Review Flow

High-value loan applications (> £25,000 / ₹2,500,000) or policy breaches automatically require human underwriter sign-off (`human_review_required = True`). A loan officer can review and issue a binding decision:
```bash
python scripts/run_pipeline.py --application data/sample_applications/APP-004.json --review --reviewer-id LO-001 --decision APPROVE --reason "Collateral and executive guarantor confirmed"
```
The decision is appended to `logs/human_reviews.jsonl` and recorded in `outputs/sample_results/APP-004.json`.

---

## 6. Dual-Write Unified Logging Architecture

Every system event is written through [`src/observability/unified_logger.py`](src/observability/unified_logger.py) in a dual-write pattern:
1. **Per-Concern Logs**: Scoped to specific analytical schemas:
   - `logs/tool_calls.jsonl`: Machine-generated tool call latency, args, and results.
   - `logs/agent_actions.jsonl`: Consequential agent decisions and state changes.
   - `logs/mcp_transcript.jsonl`: Low-level FastMCP protocol transcript.
   - `logs/human_reviews.jsonl`: Immutable log of loan officer interventions.
2. **Unified Trace (`logs/unified_trace.jsonl`)**:
   - Every single event from all four per-concern logs is appended atomically to `logs/unified_trace.jsonl`.
   - Verified by `tests/test_unified_log_consistency.py` and `scripts/verify_evidence.py`.

---

## 7. Directory Structure & Key Artifacts

```
.
├── app.py                       # Interactive Streamlit dashboard
├── src/                         # Multi-agent LangGraph core
│   ├── graph.py                 # Supervisor routing & state graph assembly
│   ├── state.py                 # Typed state contract & invariant assertions
│   ├── domain/                  # Pure Decimal math & deterministic rules
│   ├── policy/                  # Policy selector & YAML schema parser
│   ├── context/                 # Context engineering (select, compress, isolate, quarantine)
│   ├── guardrails/              # PII redaction & input/output guards
│   ├── memory/                  # Tiered memory (ephemeral short-term & SQLite semantic long-term)
│   ├── observability/           # Phoenix tracing & dual-write unified logger
│   └── security/                # Access control & authorization
├── mcp_server/                  # Custom FastMCP stdio server (2 tools + 1 resource)
├── data/                        # Synthetic policy corpus & sample application fixtures
├── logs/                        # Machine-generated JSONL audit logs
├── traces/                      # Exported Phoenix OpenTelemetry parquet traces
├── reports/                     # Golden signals, cost dashboard, eval reports
├── docs/                        # Governance pack (risk register, model card, compliance, architecture)
├── scripts/                     # Locked runbook runners & verification scripts
└── tests/                       # Complete pytest suite (routing, loops, contracts, invariants)
```

---

## 8. Running Tests
To run the full suite of unit, integration, and security tests:
```bash
pytest -v
```
All tests run locally using synthetic fixtures without requiring external database services or cloud deployments.

---

## 9. Extra Credit: FastAPI Streaming API & Demonstration

The copilot includes an optional asynchronous **FastAPI HTTP & Server-Sent Events (SSE) Streaming API** ([`src/api/server.py`](src/api/server.py)) per Section 7.7 & 8.1 of the specification.

### Endpoints
- `GET /health` — Service health and timestamp status
- `POST /api/v1/underwrite` — Synchronous structured underwriting decision
- `POST /api/v1/underwrite/stream` — Real-time Server-Sent Events (SSE) streaming node transitions (`supervisor`, `policy_agent`, `eligibility_agent`, `risk_agent`, `decision_node`)
- `POST /api/v1/review` — Human underwriter review entry and state update
- `GET /api/v1/applications/{app_id}` — Query stored application underwriting result

### Live Demonstration
To run the live streaming client demonstration:
```bash
python scripts/demo_api_stream.py
```
This connects to the streaming endpoint, prints the live SSE event stream to the terminal, and records the complete frame log to `logs/api_stream_demo.log`.

