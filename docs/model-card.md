# Loan Origination & Underwriting Copilot — Model Card

## 1. Model Details
- **System Name**: Loan Origination & Underwriting Copilot (BC-AAIE-HACK-02)

### Runtime Model
- **Provider**: Groq (OpenAI-compatible endpoint `https://api.groq.com/openai/v1`)
- **Primary Model**: `openai/gpt-oss-120b` (Input: $0.15 / 1M, Output: $0.60 / 1M tokens)
- **Fallback Model**: `openai/gpt-oss-20b` (Input: $0.075 / 1M, Output: $0.30 / 1M tokens)
- **Supported Alternative Provider**: Google Gemini API (`gemini`, model: `gemini-3.7-flash`, Input: $0.75 / 1M, Output: $3.75 / 1M tokens) supported when `LLM_PROVIDER=gemini` and `GEMINI_API_KEY` is provided. If `LLM_PROVIDER=groq` (default in submission) or if `GEMINI_API_KEY` is unconfigured, the Groq provider is resolved.

### Evaluation Model
- The same resolved provider/model configuration (`openai/gpt-oss-120b`) is used by `CopilotJudgeLLM` for DeepEval automated evaluation metrics.

### Evidence & Traceability
The exact provider and model for each evidence run are recorded deterministically in:
- [`reports/environment.json`](../reports/environment.json)
- [`logs/llm_calls.jsonl`](../logs/llm_calls.jsonl) (capturing exact model, provider, latency, and measured token usage from provider metadata)
- [`reports/eval_report.json`](../reports/eval_report.json)
- [`reports/golden_signals.json`](../reports/golden_signals.json)

- **Provider Resolution & Fallback**: Deterministic, configuration-driven via [`config/model_config.json`](../config/model_config.json) and [`src/llm/provider_resolver.py`](../src/llm/provider_resolver.py). Every resolution and fallback event is self-disclosed and logged to [`logs/agent_actions.jsonl`](../logs/agent_actions.jsonl) and [`reports/environment.json`](../reports/environment.json).
- **Orchestration**: LangGraph (StateGraph multi-agent architecture with supervisor pattern)
- **Tool Protocol**: Model Context Protocol (FastMCP server consumed through `langchain-mcp-adapters` via connected in-memory client/server protocol session; exposes 2 MCP tools: `compute_affordability`, `get_policy_document` and 1 MCP resource: `policy-corpus://index`)
- **Temperature**: `0.0` (deterministic explanatory generation)
- **Strict Role Separation**: The LLM serves **strictly as an explanatory agent**. It never computes affordability numbers, evaluates mathematical thresholds, or assigns final loan decisions. All arithmetic is executed in pure `Decimal` Python, and decisions are written solely by deterministic domain logic in [`src/domain/decisions.py`](../src/domain/decisions.py).

## 2. Intended Use
- **Primary Domain**: Retail banking personal loan origination and underwriting assistance.
- **Intended Users**: Retail credit analysts, loan officers, and risk managers.
- **Capabilities**:
  - Validates and normalizes structured synthetic loan applications.
  - Matches active lending policies deterministically based on product, jurisdiction, and application date.
  - Retrieves relevant policy clauses with SHA256-verified citations.
  - Computes DTI ratios and disposable income using pure Decimal arithmetic.
  - Generates transparent, human-readable explanatory rationales citing specific policy rules.
  - Automatically flags policy breaches and routes high-value loans to human underwriters.

## 3. Data & Synthetic Training Corpus
- **Application Data**: 100% synthetic loan applications generated for testing and benchmark evaluation in [`data/sample_applications/`](../data/sample_applications). All applicant identities, incomes, and account numbers are synthetic.
- **Policy Corpus**: Markdown-structured retail lending policies with YAML frontmatter specifying product scope, effective dates, and quantitative thresholds in [`data/policy_corpus/`](../data/policy_corpus).
- **PII Governance**: No real personal data is ingested, processed, or logged. Strict regex and named-entity redaction scrubs synthetic PII prior to Phoenix tracing or JSONL log persistence.

## 4. Limitations & Boundary Conditions
- **Advisory Only**: The copilot produces an `ai_recommendation` (`APPROVE`, `REFER`, or `DECLINE`) and never sets a binding `final_decision`. The binding decision must be executed by a human loan officer.
- **Single Jurisdiction Scope**: Current policy corpus is restricted to UK and India retail personal loan products. Cross-jurisdiction or multi-currency applications are rejected or routed to human clarification.
- **Corporate / Commercial Out of Scope**: Complex commercial lending, syndicate credit facilities, and collateral liquidation structures are explicitly out of scope.

## 5. Known Failure Modes & Evidence Citations
The system's known failure modes have been rigorously identified, cataloged, and mitigated. For detailed traces, root-cause analyses, and committed fixes, refer to [`docs/failure-analysis.md`](failure-analysis.md):
- **FAIL-001 (Policy Selection Boundary / Off-by-One)**: Application on policy boundary date matching an expired policy version. *Mitigation: Strict semi-open interval date matching in `policy_selector.py`.*
- **FAIL-002 (MCP Tool Timeout / Fragility)**: Tool unavailability during affordability calculation. *Mitigation: Bounded retry, 10s hard timeout, and graceful degradation to `UNABLE_TO_COMPLETE` with `human_review_required = True`.*
- **FAIL-003 (RAG Retrieval Poisoning / Noise Insertion)**: Out-of-policy retrieved chunks polluting decision context. *Mitigation: Targeted RAG chunk filtering with SHA256 cryptographic text hash validation.*

## 6. Out-of-Scope & Prohibited Uses
- Autonomous loan disbursement without human-in-the-loop review.
- Automated adverse credit determinations without verifiable policy citation.
- Processing unvetted raw applicant instructions embedded in free-text fields.
- Storage of unredacted applicant bank account or national ID identifiers.
