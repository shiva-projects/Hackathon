"""
Streamlit Web Interface for Loan Origination & Underwriting Copilot (BC-AAIE-HACK-02).
Interactive dashboard allowing users to:
1. Select or customize loan applications.
2. Trigger the multi-agent LangGraph underwriting pipeline.
3. Inspect deterministic DTI/affordability calculations, policy citations, and AI rationales.
4. Execute interactive Human-in-the-Loop (HITL) review overrides.
5. Inspect system observability logs, golden signals, and Phoenix traces.
"""

import sys
import os
import json
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import streamlit as st

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import time
from scripts.run_pipeline import run_single_application
from src.graph import build_loan_copilot_graph
from src.state import create_initial_state, assert_state_invariants
from src.memory.checkpoint_config import get_session_config
from src.observability.unified_logger import log_human_review, log_event
from src.guardrails.output_guard import sanitize_review_reason

NODE_METADATA = {
    "input_guard": ("1. Input Guard", "Screening applicant free-text for prompt injection & quarantining raw input"),
    "authorization_node": ("2. Authorization", "Validating requester role & cross-applicant access boundaries"),
    "intent_classifier": ("3. Intent Classifier", "Classifying user statement intent (new_application / query / escalation)"),
    "supervisor": ("4. Supervisor", "Dynamic routing orchestrator managing multi-agent delegation"),
    "policy_agent": ("5. Policy Agent", "Matching active policy corpus & retrieving verifiable RAG clauses"),
    "eligibility_agent": ("6. Eligibility Agent", "Calling FastMCP tools & calculating pure Decimal DTI affordability"),
    "risk_agent": ("7. Risk Agent", "Verifying mandatory documents & assessing credit risk profile"),
    "decision_node": ("8. Decision Node", "Assigning deterministic recommendation & drafting AI explanatory rationale"),
}

ALL_STAGES = [
    ("input_guard", "1. Input Guard\\n(Injection Screening)"),
    ("authorization_node", "2. Authorization\\n(Access Control)"),
    ("intent_classifier", "3. Intent Classifier\\n(Intent Detection)"),
    ("supervisor", "4. Supervisor\\n(Orchestration)"),
    ("policy_agent", "5. Policy Agent\\n(RAG Retrieval)"),
    ("eligibility_agent", "6. Eligibility Agent\\n(DTI Arithmetic)"),
    ("risk_agent", "7. Risk Agent\\n(Risk & Docs)"),
    ("decision_node", "8. Decision Node\\n(AI Rationale)"),
]

def render_pipeline_dot(current_node=None, completed_nodes=None, refused=False):
    completed_nodes = completed_nodes or set()
    dot = [
        'digraph G {',
        '  rankdir=LR;',
        '  graph [bgcolor="transparent", pad="0.2", nodesep="0.3", ranksep="0.4"];',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica, Arial, sans-serif", fontsize=10, height=0.6, width=1.4];',
        '  edge [color="#94A3B8", penwidth=1.5, arrowsize=0.7];',
    ]

    for nid, label in ALL_STAGES:
        if nid == current_node:
            dot.append(f'  {nid} [label="{label}\\n⏳ [EXECUTING NOW]", fillcolor="#FEF08A", color="#CA8A04", penwidth=3.0, fontcolor="#854D0E"];')
        elif nid in completed_nodes:
            dot.append(f'  {nid} [label="{label}\\n✅ [COMPLETED]", fillcolor="#DCFCE7", color="#16A34A", penwidth=2.0, fontcolor="#166534"];')
        elif refused and nid in ("input_guard", "authorization_node"):
            dot.append(f'  {nid} [label="{label}\\n🚫 [REFUSED]", fillcolor="#FEE2E2", color="#DC2626", penwidth=2.0, fontcolor="#991B1B"];')
        else:
            dot.append(f'  {nid} [label="{label}\\n○ [Pending]", fillcolor="#F8FAFC", color="#CBD5E1", penwidth=1.0, fontcolor="#64748B"];')

    dot.append('  input_guard -> authorization_node -> intent_classifier -> supervisor;')
    dot.append('  supervisor -> policy_agent -> supervisor;')
    dot.append('  supervisor -> eligibility_agent -> supervisor;')
    dot.append('  supervisor -> risk_agent -> supervisor;')
    dot.append('  supervisor -> decision_node;')
    dot.append('}')
    return "\n".join(dot)


st.set_page_config(
    page_title="Loan Copilot | Underwriting Dashboard",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished aesthetic
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .badge-approve {
        background-color: #DCFCE7;
        color: #15803D;
        padding: 6px 16px;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 1.1rem;
        display: inline-block;
        border: 1px solid #86EFAC;
    }
    .badge-refer {
        background-color: #FEF3C7;
        color: #B45309;
        padding: 6px 16px;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 1.1rem;
        display: inline-block;
        border: 1px solid #FCD34D;
    }
    .badge-decline {
        background-color: #FEE2E2;
        color: #B91C1C;
        padding: 6px 16px;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 1.1rem;
        display: inline-block;
        border: 1px solid #FCA5A5;
    }
    .badge-refused {
        background-color: #F1F5F9;
        color: #475569;
        padding: 6px 16px;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 1.1rem;
        display: inline-block;
        border: 1px solid #CBD5E1;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)


# Load sample applications list
SAMPLE_APPS_DIR = PROJECT_ROOT / "data" / "sample_applications"
SAMPLE_FILES = sorted(list(SAMPLE_APPS_DIR.glob("*.json")))
SAMPLE_APP_NAMES = {f.stem: f for f in SAMPLE_FILES}

# Sidebar: Controls & Configuration
st.sidebar.image("https://img.icons8.com/color/96/bank-building.png", width=64)
st.sidebar.title("Loan Copilot")
st.sidebar.caption("Multi-Agent Underwriting Engine")

# Model Environment Status
env_file = PROJECT_ROOT / "reports" / "environment.json"
resolved_provider = "unknown"
resolution_reason = "No environment report found"
if env_file.exists():
    try:
        env_data = json.loads(env_file.read_text(encoding="utf-8"))
        resolved_provider = env_data.get("provider", "gemini")
        resolution_reason = env_data.get("resolution_reason", "")
    except Exception:
        pass

st.sidebar.markdown(f"**Provider**: `{resolved_provider.upper()}`")
has_live_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GROQ_API_KEY"))
if has_live_key:
    st.sidebar.success("● Live LLM Key Active", icon="✅")
else:
    st.sidebar.warning("○ Fallback / Simulation Mode", icon="⚠️")

st.sidebar.divider()

app_mode = st.sidebar.radio("Select Application Source:", ["Preset Sample Application", "Custom Application Form"])

applicant_payload = None

if app_mode == "Preset Sample Application":
    selected_name = st.sidebar.selectbox(
        "Choose Application:",
        list(SAMPLE_APP_NAMES.keys()),
        index=0,
        format_func=lambda x: f"{x} ({'Approval' if x=='APP-001' else 'DTI Breach' if x=='APP-002' else 'Missing Docs' if x=='APP-003' else 'High Value' if x=='APP-004' else 'Security/Test'})"
    )
    selected_path = SAMPLE_APP_NAMES[selected_name]
    with open(selected_path, "r", encoding="utf-8") as f:
        applicant_payload = json.load(f)

else:
    st.sidebar.subheader("New Application Parameters")
    cust_id = st.sidebar.text_input("Application ID", "APP-CUSTOM-001")
    cust_name = st.sidebar.text_input("Applicant Name", "Jane Doe")
    cust_product = st.sidebar.selectbox("Product", ["personal_loan", "mortgage"])
    cust_jurisdiction = st.sidebar.selectbox("Jurisdiction", ["IN", "UK"])
    cust_amount = st.sidebar.number_input("Requested Loan Amount", min_value=1000, max_value=5000000, value=250000, step=50000)
    cust_tenure = st.sidebar.number_input("Tenure (Months)", min_value=6, max_value=84, value=36, step=6)
    cust_income = st.sidebar.number_input("Monthly Income", min_value=1000, max_value=2000000, value=85000, step=5000)
    cust_obligations = st.sidebar.number_input("Existing Monthly Obligations", min_value=0, max_value=1000000, value=15000, step=2500)
    cust_docs = st.sidebar.multiselect("Attached Documents", ["identity_proof", "income_statement", "proof_of_address"], default=["identity_proof", "income_statement"])
    cust_free_text = st.sidebar.text_area("Applicant Free Text", "I am applying for a home renovation personal loan.")

    applicant_payload = {
        "application_id": cust_id,
        "applicant_name": cust_name,
        "product": cust_product,
        "jurisdiction": cust_jurisdiction,
        "application_date": datetime.now().strftime("%Y-%m-%d"),
        "income_amount": float(cust_income),
        "income_period": "monthly",
        "currency": "INR" if cust_jurisdiction == "IN" else "GBP",
        "requested_amount": float(cust_amount),
        "tenure_months": int(cust_tenure),
        "employment": "salaried",
        "existing_obligations": [{"obligation_type": "credit_card", "amount": float(cust_obligations), "period": "monthly"}] if cust_obligations > 0 else [],
        "documents": cust_docs,
        "free_text": cust_free_text,
    }


# Header
st.markdown('<div class="main-header">🏦 Loan Origination & Underwriting Copilot</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Automated Lending Decisions: Pure Decimal Arithmetic Decides, Generative AI Explains</div>', unsafe_allow_html=True)

# Main Application Details Display
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📋 Application Metadata")
    st.markdown(f"**Application ID**: `{applicant_payload.get('application_id')}`")
    st.markdown(f"**Applicant Name**: {applicant_payload.get('applicant_name', 'N/A')}")
    st.markdown(f"**Product & Jurisdiction**: {applicant_payload.get('product', 'N/A')} ({applicant_payload.get('jurisdiction', 'N/A')})")
    st.markdown(f"**Application Date**: {applicant_payload.get('application_date', 'N/A')}")
    st.markdown(f"**Free-Text Statement**: *\"{applicant_payload.get('free_text', '')}\"*")

with col_right:
    st.subheader("💰 Financial Profile")
    curr = applicant_payload.get("currency", "INR")
    st.markdown(f"**Requested Loan**: {curr} {applicant_payload.get('requested_amount', 0):,.2f} for {applicant_payload.get('tenure_months', 0)} months")
    st.markdown(f"**Stated Monthly Income**: {curr} {applicant_payload.get('income_amount', 0):,.2f}")
    obligations = applicant_payload.get("existing_obligations", [])
    total_ob = sum(Decimal(str(o.get("amount", 0))) for o in obligations)
    st.markdown(f"**Existing Monthly Obligations**: {curr} {float(total_ob):,.2f}")
    st.markdown(f"**Documents Attached**: {', '.join(applicant_payload.get('documents', [])) or 'None'}")

st.divider()

# Underwrite Execution Button
run_button = st.button("🚀 Run Multi-Agent Underwriting Copilot", type="primary", use_container_width=True)

if run_button or f"result_{applicant_payload.get('application_id')}" in st.session_state:
    app_key = f"result_{applicant_payload.get('application_id')}"
    completed_key = f"completed_{applicant_payload.get('application_id')}"

    st.subheader("⚡ Multi-Agent Execution Graph")
    graph_box = st.empty()
    status_box = st.empty()

    if run_button:
        graph = build_loan_copilot_graph()
        app_id = applicant_payload.get("application_id", "APP-UNKNOWN")
        raw_text = applicant_payload.get("free_text", "")
        session_id = f"SESSION-{app_id}-{int(datetime.now().timestamp())}"
        cfg = get_session_config(session_id)
        current_state = create_initial_state(
            app_id, applicant_raw_text=raw_text, applicant_facts=applicant_payload, session_id=session_id
        )

        completed_set = set()
        graph_box.graphviz_chart(render_pipeline_dot(current_node="input_guard", completed_nodes=completed_set), use_container_width=True)
        status_box.info("🚀 Initializing LangGraph multi-agent pipeline...")
        time.sleep(0.35)

        for event in graph.stream(current_state, config=cfg):
            for node_name, updated_state in event.items():
                current_state = updated_state
                title, desc = NODE_METADATA.get(node_name, (node_name, "Processing application state"))

                # Live highlight: show which node is executing NOW
                graph_box.graphviz_chart(
                    render_pipeline_dot(current_node=node_name, completed_nodes=completed_set),
                    use_container_width=True
                )
                status_box.markdown(f"**Executing Step Now**: `{title}` — *{desc}*")
                time.sleep(0.4)

                completed_set.add(node_name)

        is_refused = current_state.get("request_status") == "REFUSED"
        graph_box.graphviz_chart(
            render_pipeline_dot(current_node=None, completed_nodes=completed_set, refused=is_refused),
            use_container_width=True
        )
        if is_refused:
            status_box.error(f"🚫 Request Refused by Security Guard: {current_state.get('refusal_reason', 'SECURITY_SENSITIVE')}")
        else:
            status_box.success("✅ Multi-Agent Execution Completed across all stages!")

        # Validate state invariants
        try:
            assert_state_invariants(current_state)
        except Exception:
            pass

        st.session_state[app_key] = current_state
        st.session_state[completed_key] = completed_set
    else:
        # Re-render completed graph from session state
        cached_completed = st.session_state.get(completed_key, set())
        cached_refused = st.session_state[app_key].get("request_status") == "REFUSED"
        graph_box.graphviz_chart(
            render_pipeline_dot(current_node=None, completed_nodes=cached_completed, refused=cached_refused),
            use_container_width=True
        )
        status_box.success("✅ Multi-Agent Underwriting Pipeline Completed")

    final_state = st.session_state[app_key]

    rec = final_state.get("ai_recommendation")
    req_status = final_state.get("request_status")
    dti = final_state.get("affordability", {}).get("dti")
    human_req = final_state.get("human_review_required", False)

    st.subheader("🏁 Underwriting Outcome")

    # Recommendation Banner
    rec_col, dti_col, human_col = st.columns([1, 1, 1])

    with rec_col:
        st.markdown("**AI Recommendation:**")
        if req_status == "REFUSED":
            st.markdown(f'<span class="badge-refused">REFUSED ({final_state.get("refusal_reason", "SECURITY")})</span>', unsafe_allow_html=True)
        elif rec == "APPROVE":
            st.markdown('<span class="badge-approve">✅ APPROVE</span>', unsafe_allow_html=True)
        elif rec == "REFER":
            st.markdown('<span class="badge-refer">⚠️ REFER (HUMAN SIGN-OFF MANDATED)</span>', unsafe_allow_html=True)
        elif rec == "DECLINE":
            st.markdown('<span class="badge-decline">❌ DECLINE</span>', unsafe_allow_html=True)
        else:
            st.markdown(f'<span class="badge-refused">{rec or "N/A"}</span>', unsafe_allow_html=True)

    with dti_col:
        st.markdown("**Computed Debt-to-Income (DTI):**")
        if dti is not None:
            dti_pct = float(dti) * 100.0
            st.metric("DTI Ratio", f"{dti_pct:.1f}%")
        else:
            st.metric("DTI Ratio", "N/A")

    with human_col:
        st.markdown("**Human Review Routing:**")
        if human_req:
            st.error("Mandatory Human Sign-off Required")
        else:
            st.success("Automated Flow (No Override Required)")

    st.markdown("### 📝 Explanatory Rationale")
    rationale_text = final_state.get("rationale") or final_state.get("refusal_reason") or "No rationale recorded."
    st.info(rationale_text)

    # Detailed Tabs for Deep Inspection
    tab1, tab2, tab3, tab4 = st.tabs(["Policy Citations & RAG", "Calculations Breakdown", "Multi-Agent Routing Path", "Human Review (HITL)"])

    with tab1:
        st.markdown("#### Matched Policy Document")
        policy_info = final_state.get("policy_selected", {})
        if policy_info:
            st.write(f"**Policy File**: `{policy_info.get('file_path')}`")
            st.write(f"**Version**: `{policy_info.get('version')}` | **Max DTI**: `{policy_info.get('thresholds', {}).get('max_dti')}`")
        else:
            st.write("No policy matched.")

        st.markdown("#### Cited Clauses")
        citations = final_state.get("policy_citations", [])
        if citations:
            for i, cit in enumerate(citations, 1):
                rule_id = cit.get("rule_id") or cit.get("clause_id") or cit.get("chunk_id", "N/A")
                st.markdown(f"""
                **Citation #{i} — Policy Rule `{rule_id}`**  
                *Source*: `{cit.get('source_file')}` (`{cit.get('chunk_id')}`)  
                > {cit.get('text', '')}  
                `SHA-256 Hash: {cit.get('text_hash')}`
                """)
        else:
            st.write("No specific policy citations attached.")

    with tab2:
        st.markdown("#### Pure Python Decimal Arithmetic")
        afford = final_state.get("affordability", {})
        if afford:
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Net Monthly Income", f"{float(afford.get('monthly_income', 0)):,.2f}")
            col_b.metric("Proposed Loan EMI", f"{float(afford.get('proposed_emi', 0)):,.2f}")
            col_c.metric("Disposable Income", f"{float(afford.get('disposable_income', 0)):,.2f}")
            st.json(afford)
        else:
            st.write("Affordability calculation was bypassed (e.g. refused by input guard or missing critical facts).")

    with tab3:
        st.markdown("#### LangGraph Agent Node Trajectory")
        routing = final_state.get("routing_history", [])
        st.write(" → ".join([f"`{node}`" for node in routing]))
        st.metric("Total State Steps", final_state.get("step_count", 0))

    with tab4:
        st.markdown("#### Human-in-the-Loop Decision Override")
        if human_req or rec == "REFER":
            st.warning("This application triggered a policy rule requiring explicit sign-off by a credit underwriter.")
            with st.form("hitl_review_form"):
                reviewer_id = st.text_input("Reviewer Officer ID", "LO-OFFICER-42")
                human_action = st.selectbox("Underwriter Determination", ["APPROVE", "DECLINE"])
                review_note = st.text_area("Review Rationale / Mitigating Circumstances", "Reviewed applicant profile and accepted supplementary guarantee.")
                submit_review = st.form_submit_button("Submit Underwriter Determination", type="primary")

                if submit_review:
                    # Record review to logs/human_reviews.jsonl
                    log_human_review(
                        application_id=applicant_payload.get("application_id"),
                        reviewer_id=reviewer_id,
                        action=human_action,
                        reason=review_note,
                        original_recommendation=rec,
                        dti=float(dti) if dti is not None else None,
                    )
                    st.success(f"Review successfully committed: Application marked as {human_action} by {reviewer_id}!")
        else:
            st.info("This application completed deterministically with no mandatory human referral required.")

st.divider()

# System Metrics & Observability Section
with st.expander("📊 System Observability & Golden Signals (Arize Phoenix / OpenTelemetry)"):
    signals_file = PROJECT_ROOT / "reports" / "golden_signals.json"
    if signals_file.exists():
        try:
            sig = json.loads(signals_file.read_text(encoding="utf-8"))
            col1, col2, col3, col4 = st.columns(4)
            lat = sig.get("latency_seconds", {})
            col1.metric("Thinking Latency (P50)", f"{lat.get('thinking_p50', 0)*1000:.1f} ms")
            col2.metric("Thinking Latency (P95)", f"{lat.get('thinking_p95', 0)*1000:.1f} ms")
            col3.metric("Cost per Application", f"${sig.get('cost_governance', {}).get('estimated_cost_usd', 0):.4f}")
            col4.metric("Total Spans Captured", sig.get("spans_evaluated", 0))
        except Exception as e:
            st.write(f"Could not load golden signals: {e}")
    else:
        st.write("No golden signals report found.")
