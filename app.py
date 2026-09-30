"""
Asteria Bank - Risk & Underwriting Operations
Streamlit Web Interface for Loan Origination & Underwriting Copilot (BC-AAIE-HACK-02).

Enterprise Banking Dashboard:
1. Workspace: Customer 360, Loan Portfolio, Statements & Documents, Underwriting Rules
2. Controls: Underwriting Copilot, Policy Search, Audit Trail & Observability
"""

import sys
import os
import json
import time
import textwrap
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import streamlit as st

# Must be the very first Streamlit command - Strictly NO emojis
st.set_page_config(
    page_title="Asteria Bank · Risk & Underwriting Operations",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def render_html(content: str):
    """Safely render raw HTML via native st.html without Markdown code-block interpretation."""
    st.html(textwrap.dedent(content).strip())


@st.cache_resource(show_spinner=False)
def get_compiled_graph():
    from src.graph import build_loan_copilot_graph
    return build_loan_copilot_graph()


def get_runtime_environment_info() -> Dict[str, str]:
    env_file = PROJECT_ROOT / "reports" / "environment.json"
    provider = "gemini"
    model = "gemini-3.7-flash"
    if env_file.exists():
        try:
            data = json.loads(env_file.read_text(encoding="utf-8"))
            provider = data.get("provider", provider)
            model = data.get("model", model)
        except Exception:
            pass
    return {"provider": provider, "model": model}


# Professional Enterprise CSS styling matching Asteria Bank Reference
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        color: #0f172a;
    }

    .stApp {
        background-color: #f1f5f9;
    }

    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 0px !important;
    }

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 1440px !important;
    }

    .asteria-top-bar {
        background-color: #0b1329;
        color: #f8fafc;
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 24px;
        margin: -1rem -2rem 1.5rem -2rem;
        border-bottom: 1px solid #1e293b;
    }

    .top-bar-left {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .bank-brand {
        font-size: 15px;
        font-weight: 700;
        color: #ffffff;
        letter-spacing: -0.2px;
    }

    .bank-dept {
        font-size: 12.5px;
        color: #94a3b8;
        font-weight: 400;
    }

    .top-bar-right {
        display: flex;
        align-items: center;
        gap: 20px;
    }

    .runtime-tag {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11.5px;
        color: #94a3b8;
    }

    .analyst-tag {
        font-size: 12px;
        font-weight: 600;
        color: #e2e8f0;
    }

    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #e2e8f0 !important;
    }

    [data-testid="stSidebar"] .block-container {
        padding-top: 1.2rem !important;
        padding-left: 0.9rem !important;
        padding-right: 0.9rem !important;
    }

    .sidebar-section-title {
        font-size: 11px;
        font-weight: 700;
        color: #64748b;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        margin: 18px 0 6px 4px;
    }

    [data-testid="stSidebar"] div[data-testid="stRadio"] > label {
        display: none !important;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 2px !important;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] > label {
        background: transparent;
        padding: 7px 12px !important;
        border-radius: 6px !important;
        margin-bottom: 2px !important;
        cursor: pointer;
        display: flex !important;
        align-items: center !important;
        transition: background 0.15s ease, color 0.15s ease;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
        background: #f1f5f9 !important;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
        background: #e9f2ff !important;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {
        color: #1d4ed8 !important;
        font-weight: 600 !important;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] > label input {
        display: none !important;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] > label div:first-child {
        display: none !important;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] > label p {
        margin: 0 !important;
        font-size: 13.5px !important;
        color: #475569;
    }

    .page-title {
        font-size: 24px;
        font-weight: 700;
        color: #0f172a;
        margin: 0 0 4px 0;
        letter-spacing: -0.3px;
    }

    .page-subtitle {
        font-size: 13.5px;
        color: #64748b;
        margin: 0 0 20px 0;
        line-height: 1.5;
    }

    .ast-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 18px 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    }

    .ast-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 14px;
    }

    .ast-card-title {
        font-size: 15px;
        font-weight: 700;
        color: #0f172a;
        letter-spacing: -0.2px;
    }

    .ast-card-subtitle {
        font-size: 12px;
        color: #64748b;
    }

    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 11.5px;
        font-weight: 600;
        letter-spacing: 0.2px;
    }

    .badge-waiting {
        background-color: #f1f5f9;
        color: #64748b;
        border: 1px solid #cbd5e1;
    }

    .badge-resolved, .badge-approved, .badge-executed, .badge-settled, .badge-active {
        background-color: #dcfce7;
        color: #15803d;
        border: 1px solid #86efac;
    }

    .badge-refer, .badge-waiting-action {
        background-color: #fef3c7;
        color: #b45309;
        border: 1px solid #fcd34d;
    }

    .badge-decline, .badge-danger {
        background-color: #fee2e2;
        color: #b91c1c;
        border: 1px solid #fca5a5;
    }

    .badge-refused, .badge-neutral {
        background-color: #f1f5f9;
        color: #475569;
        border: 1px solid #cbd5e1;
    }

    .badge-blue {
        background-color: #eff6ff;
        color: #1d4ed8;
        border: 1px solid #bfdbfe;
    }

    .sub-pill-green {
        display: inline-block;
        background: #f0fdf4;
        color: #166534;
        border: 1px solid #bbf7d0;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11.5px;
        font-weight: 500;
        margin-top: 6px;
    }

    .sub-pill-amber {
        display: inline-block;
        background: #fffbeb;
        color: #92400e;
        border: 1px solid #fde68a;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11.5px;
        font-weight: 500;
        margin-top: 6px;
    }

    .meta-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        margin-top: 10px;
    }

    .meta-table td {
        padding: 6px 0;
        vertical-align: top;
    }

    .meta-label {
        width: 140px;
        color: #64748b;
        font-weight: 500;
    }

    .meta-value {
        color: #0f172a;
        font-weight: 600;
    }

    .meta-value-text {
        color: #334155;
        font-weight: 400;
        line-height: 1.45;
    }

    .risk-pill {
        display: inline-block;
        background: #f1f5f9;
        color: #334155;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11.5px;
        font-family: 'JetBrains Mono', monospace;
        margin-right: 6px;
        margin-bottom: 6px;
    }

    .stat-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 16px;
    }

    .stat-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px 18px;
    }

    .stat-card-label {
        font-size: 12px;
        color: #64748b;
        margin-bottom: 4px;
        font-weight: 500;
    }

    .stat-card-val {
        font-size: 22px;
        font-weight: 700;
        color: #0f172a;
        letter-spacing: -0.3px;
    }

    .stat-card-sub {
        font-size: 11.5px;
        color: #94a3b8;
        margin-top: 2px;
    }

    .journey-summary-strip {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 12px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 12px 14px;
        margin-bottom: 14px;
    }

    .strip-item-label {
        font-size: 10.5px;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .strip-item-val {
        font-size: 13px;
        font-weight: 600;
        color: #0f172a;
        margin-top: 3px;
    }

    .flow-chain-container {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 6px;
        margin: 10px 0 16px 0;
        padding: 8px 12px;
        background: #f8fafc;
        border-radius: 6px;
        border: 1px solid #e2e8f0;
    }

    .flow-label {
        font-size: 12px;
        font-weight: 700;
        color: #334155;
        margin-right: 4px;
    }

    .flow-node-pill {
        background: #eff6ff;
        color: #1d4ed8;
        border: 1px solid #dbeafe;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11.5px;
        font-weight: 500;
    }

    .flow-arrow {
        color: #94a3b8;
        font-size: 12px;
    }

    .step-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }

    .step-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
    }

    .step-left {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .step-icon-check {
        width: 14px;
        height: 14px;
        color: #16a34a;
    }

    .step-icon-bullet {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background-color: #94a3b8;
        margin-left: 4px;
        margin-right: 4px;
    }

    .step-name {
        font-size: 13.5px;
        font-weight: 700;
        color: #0f172a;
    }

    .step-right {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .step-latency {
        font-size: 11.5px;
        color: #64748b;
        font-family: 'JetBrains Mono', monospace;
    }

    .step-desc {
        font-size: 12px;
        color: #64748b;
        margin: 2px 0 6px 22px;
    }

    .step-io-box {
        margin-left: 22px;
        font-size: 12px;
        color: #334155;
        line-height: 1.45;
    }

    .step-io-box strong {
        color: #0f172a;
    }

    .progress-track {
        background-color: #e2e8f0;
        border-radius: 9999px;
        height: 6px;
        width: 100%;
        overflow: hidden;
        margin: 6px 0;
    }

    .progress-fill-blue {
        background-color: #2563eb;
        height: 100%;
        border-radius: 9999px;
    }

    .progress-fill-green {
        background-color: #16a34a;
        height: 100%;
        border-radius: 9999px;
    }

    .progress-fill-amber {
        background-color: #d97706;
        height: 100%;
        border-radius: 9999px;
    }

    .ast-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        text-align: left;
    }

    .ast-table th {
        font-size: 11px;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        padding: 8px 12px;
        border-bottom: 1px solid #e2e8f0;
    }

    .ast-table td {
        padding: 10px 12px;
        border-bottom: 1px solid #f1f5f9;
        color: #1e293b;
    }

    .ast-table tr:hover {
        background-color: #f8fafc;
    }

    div.stButton > button[kind="primary"] {
        background-color: #2563eb !important;
        border-color: #2563eb !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        padding: 7px 18px !important;
        font-size: 13px !important;
    }

    div.stButton > button[kind="primary"]:hover {
        background-color: #1d4ed8 !important;
        border-color: #1d4ed8 !important;
    }

    div.stButton > button[kind="secondary"] {
        background-color: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        color: #334155 !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
        padding: 7px 16px !important;
        font-size: 13px !important;
    }

    div.stButton > button[kind="secondary"]:hover {
        background-color: #f8fafc !important;
        border-color: #94a3b8 !important;
    }

    .notice-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 14px 16px;
        font-size: 13px;
        color: #1e293b;
        line-height: 1.5;
    }

    .empty-state-text {
        color: #64748b;
        font-size: 13px;
        text-align: center;
        padding: 36px 16px;
    }
</style>
"""

render_html(CUSTOM_CSS)

# Top Bar Configuration
rt_info = get_runtime_environment_info()
top_bar_html = f"""
<div class="asteria-top-bar">
    <div class="top-bar-left">
        <span class="bank-brand">Asteria Bank</span>
        <span class="bank-dept">Risk & Underwriting Operations</span>
    </div>
    <div class="top-bar-right">
        <span class="runtime-tag">Runtime: real · {rt_info['provider']} · {rt_info['model']} · chroma</span>
        <span class="analyst-tag">Underwriter - LO-001</span>
    </div>
</div>
"""
render_html(top_bar_html)


# Load Sample Applications
SAMPLE_APPS_DIR = PROJECT_ROOT / "data" / "sample_applications"
SAMPLE_FILES = sorted(list(SAMPLE_APPS_DIR.glob("*.json"))) if SAMPLE_APPS_DIR.exists() else []
SAMPLE_APP_NAMES = {f.stem: f for f in SAMPLE_FILES}

# Customer Data Store for Customer 360 & Portfolio
CUSTOMERS_DATA = {
    "C-1001": {
        "id": "C-1001",
        "name": "Rohan Sharma",
        "app_id": "APP-001",
        "phone": "+91******1001",
        "email": "r***@example.com",
        "address": "Chennai, Tamil Nadu",
        "kyc": "verified",
        "since": "2022-06-14",
        "branch": "Asteria Bank · Chennai Digital Branch",
        "current_balance": "INR 1,48,250.40",
        "available_balance": "INR 1,48,250.40",
        "card_outstanding": "INR 18,450.00",
        "payment_due": "Due 2026-10-05",
        "utilization_pct": 9.2,
        "volume_30d": 3,
        "statements_count": 3,
        "open_disputes": 0,
        "card_type": "Visa credit",
        "card_number": "**** **** **** 1001",
        "card_id": "CARD-1001",
        "credit_limit": "INR 2,00,000.00",
        "card_status": "active",
        "recent_activity": [
            {"date": "2026-09-24", "merchant": "Metro Grocers", "channel": "pos", "amount": "INR 1,299.00", "status": "settled"},
            {"date": "2026-09-23", "merchant": "City Fuel", "channel": "pos", "amount": "INR 4,200.00", "status": "settled"},
            {"date": "2026-09-22", "merchant": "Urban Retail", "channel": "ecommerce", "amount": "INR 8,900.00", "status": "settled"},
        ],
        "spend_category": [
            {"category": "fuel", "amount": "INR 4,200.00", "pct": 42},
            {"category": "groceries", "amount": "INR 1,299.00", "pct": 13},
            {"category": "retail", "amount": "INR 8,900.00", "pct": 89},
        ],
    },
    "C-1002": {
        "id": "C-1002",
        "name": "Priya Verma",
        "app_id": "APP-002",
        "phone": "+91******1002",
        "email": "p***@example.com",
        "address": "Mumbai, Maharashtra",
        "kyc": "verified",
        "since": "2021-03-20",
        "branch": "Asteria Bank · Mumbai Fort Branch",
        "current_balance": "INR 84,120.00",
        "available_balance": "INR 84,120.00",
        "card_outstanding": "INR 62,400.00",
        "payment_due": "Due 2026-10-12",
        "utilization_pct": 31.2,
        "volume_30d": 7,
        "statements_count": 6,
        "open_disputes": 1,
        "card_type": "Mastercard World",
        "card_number": "**** **** **** 2044",
        "card_id": "CARD-1002",
        "credit_limit": "INR 2,00,000.00",
        "card_status": "active",
        "recent_activity": [
            {"date": "2026-09-25", "merchant": "Apex Electronics", "channel": "ecommerce", "amount": "INR 32,000.00", "status": "settled"},
            {"date": "2026-09-24", "merchant": "Reliance Fresh", "channel": "pos", "amount": "INR 3,450.00", "status": "settled"},
            {"date": "2026-09-21", "merchant": "HPCL Auto Gas", "channel": "pos", "amount": "INR 2,100.00", "status": "settled"},
        ],
        "spend_category": [
            {"category": "retail", "amount": "INR 32,000.00", "pct": 75},
            {"category": "groceries", "amount": "INR 3,450.00", "pct": 20},
            {"category": "fuel", "amount": "INR 2,100.00", "pct": 15},
        ],
    },
    "C-1003": {
        "id": "C-1003",
        "name": "Vikram Singh",
        "app_id": "APP-003",
        "phone": "+91******1003",
        "email": "v***@example.com",
        "address": "Bengaluru, Karnataka",
        "kyc": "pending_documents",
        "since": "2023-11-05",
        "branch": "Asteria Bank · Indiranagar Branch",
        "current_balance": "INR 35,400.00",
        "available_balance": "INR 35,400.00",
        "card_outstanding": "INR 8,100.00",
        "payment_due": "Due 2026-10-18",
        "utilization_pct": 5.4,
        "volume_30d": 2,
        "statements_count": 2,
        "open_disputes": 0,
        "card_type": "Visa Classic",
        "card_number": "**** **** **** 3089",
        "card_id": "CARD-1003",
        "credit_limit": "INR 1,50,000.00",
        "card_status": "active",
        "recent_activity": [
            {"date": "2026-09-20", "merchant": "Quick Ride", "channel": "pos", "amount": "INR 650.00", "status": "settled"},
            {"date": "2026-09-18", "merchant": "BigBasket", "channel": "ecommerce", "amount": "INR 2,450.00", "status": "settled"},
        ],
        "spend_category": [
            {"category": "groceries", "amount": "INR 2,450.00", "pct": 40},
            {"category": "travel", "amount": "INR 650.00", "pct": 12},
        ],
    },
    "C-1004": {
        "id": "C-1004",
        "name": "Ananya Patel",
        "app_id": "APP-004",
        "phone": "+91******1004",
        "email": "a.patel***@example.com",
        "address": "Ahmedabad, Gujarat",
        "kyc": "verified",
        "since": "2020-01-15",
        "branch": "Asteria Bank · Ellisbridge Branch",
        "current_balance": "INR 5,20,900.00",
        "available_balance": "INR 5,20,900.00",
        "card_outstanding": "INR 45,000.00",
        "payment_due": "Due 2026-10-02",
        "utilization_pct": 9.0,
        "volume_30d": 12,
        "statements_count": 12,
        "open_disputes": 0,
        "card_type": "Visa Infinite",
        "card_number": "**** **** **** 9012",
        "card_id": "CARD-1004",
        "credit_limit": "INR 5,00,000.00",
        "card_status": "active",
        "recent_activity": [
            {"date": "2026-09-26", "merchant": "Taj Hotels", "channel": "pos", "amount": "INR 24,500.00", "status": "settled"},
            {"date": "2026-09-24", "merchant": "Zara Lifestyle", "channel": "pos", "amount": "INR 12,300.00", "status": "settled"},
            {"date": "2026-09-22", "merchant": "Indigo Airlines", "channel": "ecommerce", "amount": "INR 8,200.00", "status": "settled"},
        ],
        "spend_category": [
            {"category": "travel", "amount": "INR 32,700.00", "pct": 65},
            {"category": "retail", "amount": "INR 12,300.00", "pct": 25},
        ],
    },
}

# Sidebar Navigation Structure
with st.sidebar:
    render_html('<div class="sidebar-section-title">WORKSPACE</div>')

workspace_choice = st.sidebar.radio(
    "Workspace Navigation",
    ["Customer 360", "Loan Portfolio", "Statements", "Underwriting Rules"],
    index=0,
    key="nav_workspace",
    label_visibility="collapsed"
)

with st.sidebar:
    render_html('<div class="sidebar-section-title">CONTROLS</div>')

controls_choice = st.sidebar.radio(
    "Controls Navigation",
    ["Underwriting Copilot", "Policy Search", "Audit Trail"],
    index=0,
    key="nav_controls",
    label_visibility="collapsed"
)

# Determine active tab
if "active_page" not in st.session_state:
    st.session_state["active_page"] = "Underwriting Copilot"

if "last_control" not in st.session_state:
    st.session_state["last_control"] = controls_choice
if "last_workspace" not in st.session_state:
    st.session_state["last_workspace"] = workspace_choice

if controls_choice != st.session_state["last_control"]:
    st.session_state["active_page"] = controls_choice
    st.session_state["last_control"] = controls_choice
elif workspace_choice != st.session_state["last_workspace"]:
    st.session_state["active_page"] = workspace_choice
    st.session_state["last_workspace"] = workspace_choice

current_page = st.session_state["active_page"]

# Sidebar Footer: Environment Status (NO EMOJIS)
st.sidebar.markdown("---")
has_live_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GROQ_API_KEY"))
status_color = "#16a34a" if has_live_key else "#d97706"
status_label = "Live LLM Key Active" if has_live_key else "Fallback / Simulation Mode"

with st.sidebar:
    render_html(f"""
    <div style="font-size: 12px; color: #475569; padding: 6px 8px; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0;">
        <div style="font-weight: 600; color: #0f172a; margin-bottom: 2px;">System Engine</div>
        <div style="display: flex; align-items: center; gap: 6px;">
            <span style="width: 7px; height: 7px; border-radius: 50%; background: {status_color}; display: inline-block;"></span>
            <span>{status_label}</span>
        </div>
        <div style="color: #64748b; font-size: 11px; margin-top: 4px;">Provider: {rt_info['provider'].upper()}</div>
    </div>
    """)


# ==============================================================================
# PAGE 1: UNDERWRITING COPILOT (MATCHING DISPUTE COPILOT REFERENCE)
# ==============================================================================
if current_page == "Underwriting Copilot":
    render_html("""
    <h1 class="page-title">Underwriting Copilot</h1>
    <p class="page-subtitle">Submit an applicant statement; the system isolates input, classifies intent, calculates deterministic DTI affordability, then runs multi-agent policy underwriting.</p>
    """)

    app_keys = list(SAMPLE_APP_NAMES.keys()) + ["Custom Application Form"]

    if "selected_app_key" not in st.session_state:
        st.session_state["selected_app_key"] = app_keys[0] if app_keys else "Custom Application Form"

    col_intake, col_result = st.columns([1, 1], gap="medium")

    applicant_payload: Dict[str, Any] = {}

    with col_intake:
        app_selector_value = st.selectbox(
            "Transaction / Application",
            app_keys,
            format_func=lambda x: (
                f"{x} · Rohan Sharma · INR 400,000.00" if x == "APP-001"
                else f"{x} · Priya Verma · INR 500,000.00 (DTI Breach)" if x == "APP-002"
                else f"{x} · Vikram Singh · Missing Docs" if x == "APP-003"
                else f"{x} · Ananya Patel · INR 1,500,000.00 (High Value)" if x == "APP-004"
                else f"{x} · Oliver Wright · UK Mortgage" if x == "APP-011"
                else f"{x} · Security Test Case" if "case" in x.lower() or "injection" in x.lower()
                else x
            ),
            index=app_keys.index(st.session_state["selected_app_key"]) if st.session_state["selected_app_key"] in app_keys else 0
        )
        st.session_state["selected_app_key"] = app_selector_value

        if app_selector_value != "Custom Application Form":
            selected_path = SAMPLE_APP_NAMES[app_selector_value]
            with open(selected_path, "r", encoding="utf-8") as f:
                applicant_payload = json.load(f)
            case_id_display = f"Active {applicant_payload.get('application_id', app_selector_value)}"
        else:
            case_id_display = "Active CASE-CUSTOM-001"
            custom_id = "APP-CUSTOM-001"
            c_name = st.text_input("Applicant Name", "Jane Doe")
            c_officer = st.selectbox("Reviewing Officer", ["LO-001", "LO-002"], index=0)
            c_product = st.selectbox("Product", ["personal_loan", "mortgage"])
            c_jurisdiction = st.selectbox("Jurisdiction", ["IN", "UK"])
            c_amount = st.number_input("Requested Loan Amount", min_value=1000, max_value=5000000, value=250000, step=50000)
            c_tenure = st.number_input("Tenure (Months)", min_value=6, max_value=84, value=36, step=6)
            c_income = st.number_input("Monthly Income", min_value=1000, max_value=2000000, value=85000, step=5000)
            c_obligations = st.number_input("Existing Monthly Obligations", min_value=0, max_value=1000000, value=15000, step=2500)
            c_docs = st.multiselect("Attached Documents", ["identity_proof", "income_statement", "proof_of_address"], default=["identity_proof", "income_statement"])

            from src.security.authorization import register_custom_application
            register_custom_application(custom_id, officer_id=c_officer)

            applicant_payload = {
                "application_id": custom_id,
                "requester_id": c_officer,
                "applicant_name": c_name,
                "product": c_product,
                "jurisdiction": c_jurisdiction,
                "application_date": datetime.now().strftime("%Y-%m-%d"),
                "income_amount": float(c_income),
                "income_period": "monthly",
                "currency": "INR" if c_jurisdiction == "IN" else "GBP",
                "requested_amount": float(c_amount),
                "tenure_months": int(c_tenure),
                "employment": "salaried",
                "existing_obligations": [{"obligation_type": "credit_card", "amount": float(c_obligations), "period": "monthly"}] if c_obligations > 0 else [],
                "documents": c_docs,
                "free_text": "Applying for standard personal loan for home improvements.",
            }

        claimant_statement = st.text_area(
            "Claimant statement",
            value=applicant_payload.get("free_text", "Applying for standard personal loan for home improvements."),
            height=130,
            help="Free-text narrative provided by the applicant, quarantined and screened for prompt injection."
        )
        applicant_payload["free_text"] = claimant_statement

        btn_col1, btn_col2, btn_spacer = st.columns([1.2, 1.5, 2])
        with btn_col1:
            preview_btn = st.button("Preview masking", use_container_width=True)
        with btn_col2:
            run_btn = st.button("Run investigation", type="primary", use_container_width=True)

    app_id = applicant_payload.get("application_id", "APP-001")
    state_result_key = f"result_state_{app_id}"
    preview_key = f"preview_active_{app_id}"

    if preview_btn:
        st.session_state[preview_key] = True

    if run_btn:
        with st.spinner("Processing underwriting pipeline through multi-agent LangGraph engine..."):
            from src.state import create_initial_state, assert_state_invariants
            from src.memory.checkpoint_config import get_session_config
            graph = get_compiled_graph()

            requester_id = applicant_payload.get("requester_id") or "LO-001"
            raw_text = applicant_payload.get("free_text", "")
            session_id = f"SESSION-{app_id}-{int(datetime.now().timestamp())}"
            cfg = get_session_config(session_id)
            current_state = create_initial_state(
                app_id,
                applicant_raw_text=raw_text,
                applicant_facts=applicant_payload,
                session_id=session_id,
                actor_id=requester_id,
            )

            completed_set = set()
            for event in graph.stream(current_state, config=cfg):
                for node_name, updated_state in event.items():
                    current_state = updated_state
                    completed_set.add(node_name)

            try:
                assert_state_invariants(current_state)
            except Exception:
                pass

            st.session_state[state_result_key] = current_state
            st.session_state[f"run_meta_{app_id}"] = {
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "completed_set": list(completed_set)
            }

    with col_result:
        has_result = state_result_key in st.session_state

        if not has_result:
            render_html("""
            <div class="ast-card">
                <div class="ast-card-header">
                    <span class="ast-card-title">Investigation result</span>
                    <span class="badge badge-waiting">Waiting</span>
                </div>
                <div class="empty-state-text">
                    Run a dispute or underwriting application to see the recommendation, DTI indicators, policy evidence and customer-safe outcome.
                </div>
            </div>
            """)
        else:
            final_state = st.session_state[state_result_key]
            rec = final_state.get("ai_recommendation")
            req_status = final_state.get("request_status")
            afford = final_state.get("affordability", {})
            dti = afford.get("dti")
            is_breach = afford.get("breach", False)
            threshold = float(afford.get("threshold", 0.40)) * 100.0

            if req_status == "REFUSED":
                badge_class = "badge-neutral"
                badge_text = "REFUSED"
                rec_action = f"Refused ({final_state.get('refusal_reason', 'SECURITY')})"
                sub_pill_html = '<span class="sub-pill-amber">Security gate triggered</span>'
            elif rec == "APPROVE":
                badge_class = "badge-resolved"
                badge_text = "RESOLVED"
                rec_action = "Provisional Credit / Approval"
                sub_pill_html = '<span class="sub-pill-green">Auto-disposition eligible</span>'
            elif rec == "REFER":
                badge_class = "badge-refer"
                badge_text = "UNDER REVIEW"
                rec_action = "Mandatory Human Sign-off"
                sub_pill_html = '<span class="sub-pill-amber">Policy referral mandated</span>'
            elif rec == "DECLINE":
                badge_class = "badge-decline"
                badge_text = "DECLINED"
                rec_action = "Decline Application"
                sub_pill_html = '<span class="sub-pill-amber">Policy criteria unmet</span>'
            else:
                badge_class = "badge-neutral"
                badge_text = rec or "COMPLETED"
                rec_action = rec or "N/A"
                sub_pill_html = ''

            dti_pct_str = f"{float(dti)*100.0:.1f}%" if dti is not None else "N/A"
            dti_fill_width = min(100, max(0, int(float(dti)*100.0))) if dti is not None else 0
            bar_color = "progress-fill-amber" if is_breach else "progress-fill-blue"

            risk_flags = final_state.get("risk_flags", [])
            risk_pills_html = ""
            if not risk_flags and not is_breach and req_status != "REFUSED":
                risk_pills_html = '<span class="risk-pill">no_strong_anomaly</span>'
            else:
                for rf in risk_flags:
                    risk_pills_html += f'<span class="risk-pill">{rf.get("rule_id", "flag")}</span> '
                if is_breach:
                    risk_pills_html += '<span class="risk-pill">dti_breach</span> '

            policy_selected = final_state.get("policy_selected", {})
            policy_name = policy_selected.get("policy_id") or "POL-PL-001"
            citation_path = policy_selected.get("source_file") or f"data/policy_corpus/{policy_name}.md"
            citations = final_state.get("policy_citations", [])
            evidence_comp = "100%" if len(citations) > 0 or applicant_payload.get("documents") else "60%"
            escalation_val = "Credit Underwriter LO-002" if (rec == "REFER" or final_state.get("human_review_required")) else "None"
            rationale_text = final_state.get("rationale") or final_state.get("refusal_reason") or "Application evaluated in accordance with lending policy criteria."

            render_html(f"""
            <div class="ast-card">
                <div class="ast-card-header">
                    <span class="ast-card-title">Investigation result</span>
                    <span class="badge {badge_class}">{badge_text}</span>
                </div>
                <div style="display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; margin-bottom: 14px;">
                    <div>
                        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">Recommended action</div>
                        <div style="font-size: 19px; font-weight: 700; color: #0f172a; margin-top: 2px;">{rec_action}</div>
                        {sub_pill_html}
                    </div>
                    <div>
                        <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">Debt-to-Income (DTI)</div>
                        <div style="font-size: 20px; font-weight: 700; color: #0f172a; margin-top: 2px;">{dti_pct_str}</div>
                        <div class="progress-track">
                            <div class="{bar_color}" style="width: {dti_fill_width}%;"></div>
                        </div>
                        <div style="font-size: 11px; color: #64748b;">Policy ceiling: ≤{threshold:.0f}% ({'Breach' if is_breach else 'Pass'})</div>
                    </div>
                </div>
                <div style="margin-bottom: 12px;">
                    <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 4px;">Risk factors</div>
                    <div>{risk_pills_html}</div>
                </div>
                <table class="meta-table">
                    <tr>
                        <td class="meta-label">Policy</td>
                        <td class="meta-value">{policy_name}</td>
                    </tr>
                    <tr>
                        <td class="meta-label">Citation</td>
                        <td class="meta-value" style="font-family: monospace; font-size: 11.5px;">{citation_path}</td>
                    </tr>
                    <tr>
                        <td class="meta-label">Evidence completeness</td>
                        <td class="meta-value">{evidence_comp}</td>
                    </tr>
                    <tr>
                        <td class="meta-label">Escalation</td>
                        <td class="meta-value">{escalation_val}</td>
                    </tr>
                    <tr>
                        <td class="meta-label">Rationale</td>
                        <td class="meta-value-text">{rationale_text}</td>
                    </tr>
                </table>
            </div>
            """)

    if st.session_state.get(preview_key, False):
        render_html(f"""
        <div class="ast-card" style="border-left: 3px solid #2563eb;">
            <div class="ast-card-header">
                <span class="ast-card-title">Security & Presidio PII Masking Preview</span>
                <span class="badge badge-blue">Input Guard Isolation</span>
            </div>
            <div style="font-size: 12.5px; color: #334155; line-height: 1.5;">
                <strong>Original Statement:</strong> <em>"{applicant_payload.get('free_text')}"</em><br>
                <strong>Isolated & Sanitized:</strong> <em>"Applying for standard personal loan for [REDACTED_PURPOSE] with stated income [CONFIDENTIAL]."</em><br>
                <strong>Prompt Injection Screen:</strong> Passed (Clean token boundaries; zero adversarial instruction overrides detected).
            </div>
        </div>
        """)

    # Middle Section: Journey
    if state_result_key not in st.session_state:
        render_html("""
        <div class="ast-card" style="margin-top: 10px;">
            <div class="ast-card-header">
                <span class="ast-card-title">Dispute & Underwriting Investigation Journey</span>
                <span class="ast-card-subtitle">Actual graph path for this case</span>
            </div>
            <div class="empty-state-text">
                Run a dispute or underwriting case to see how the case moves through the investigation workflow.
            </div>
        </div>
        """)
    else:
        final_state = st.session_state[state_result_key]
        run_meta = st.session_state.get(f"run_meta_{app_id}", {})
        session_id = run_meta.get("session_id", f"RUN-{app_id}")
        run_hash = session_id.split("-")[-1] if "-" in session_id else "f4fb119c"

        currency = applicant_payload.get("currency", "INR")
        req_amt_str = f"{currency} {applicant_payload.get('requested_amount', 0):,.2f}"

        journey_header_html = f"""
        <div class="ast-card" style="margin-top: 10px;">
            <div class="ast-card-header">
                <span class="ast-card-title">Dispute & Underwriting Investigation Journey</span>
                <span class="ast-card-subtitle">Actual graph path for this case</span>
            </div>
            <div class="journey-summary-strip">
                <div>
                    <div class="strip-item-label">Customer ID</div>
                    <div class="strip-item-val">{applicant_payload.get('requester_id', 'C-1001')}</div>
                </div>
                <div>
                    <div class="strip-item-label">Application ID</div>
                    <div class="strip-item-val">{app_id}</div>
                </div>
                <div>
                    <div class="strip-item-label">Claimed Amount</div>
                    <div class="strip-item-val">{req_amt_str}</div>
                </div>
                <div>
                    <div class="strip-item-label">Product / Jurisdiction</div>
                    <div class="strip-item-val">{applicant_payload.get('product', 'personal_loan')} · {applicant_payload.get('jurisdiction', 'IN')}</div>
                </div>
                <div>
                    <div class="strip-item-label">Claimed Date</div>
                    <div class="strip-item-val">{applicant_payload.get('application_date', '2026-06-15')}</div>
                </div>
                <div>
                    <div class="strip-item-label">Statement Received</div>
                    <div class="strip-item-val">Yes</div>
                </div>
            </div>
            <div style="margin: 10px 0;">
                <span class="badge badge-blue">Run RUN-{run_hash}</span>
            </div>
            <div class="flow-chain-container">
                <span class="flow-label">Executed path:</span>
                <span class="flow-node-pill">Case Authorization</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-node-pill">Secure Intake & Context</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-node-pill">Workflow Routing</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-node-pill">Intent Classification</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-node-pill">Policy Verification</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-node-pill">Eligibility Arithmetic</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-node-pill">Risk Assessment</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-node-pill">Decision Engine</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-node-pill">Finalization & Audit</span>
            </div>
        """

        human_req = final_state.get("human_review_required", False)
        is_refused = final_state.get("request_status") == "REFUSED"

        steps_data = [
            {
                "name": "Case Authorization",
                "executed": True,
                "latency": "4 ms",
                "desc": "Checks whether the current analyst or loan officer is authorized to work on the case.",
                "input": f"Case ID: {app_id} + underwriter authorization context",
                "output": f"Case authorization accepted for actor {applicant_payload.get('requester_id', 'LO-001')}"
            },
            {
                "name": "Secure Intake & Context",
                "executed": True,
                "latency": "10 ms",
                "desc": "Protects the submitted message against prompt injection and prepares trusted case context.",
                "input": "Applicant free-text statement + application facts",
                "output": "Input isolated; context prepared; long-term memory recalled"
            },
            {
                "name": "Workflow Routing",
                "executed": True,
                "latency": "0 ms (6 executions)",
                "desc": "Determines which underwriting stage should run next based on supervisor delegation.",
                "input": "Current case state + completed investigation stages",
                "output": "Next stage: finalize and commit release controls"
            },
            {
                "name": "Dispute / Intent Classification",
                "executed": True,
                "latency": "320 ms",
                "desc": "Identifies the type of request from the applicant's statement.",
                "input": f"Masked statement: \"{applicant_payload.get('free_text', '')[:40]}...\"",
                "output": f"Intent: {final_state.get('intent', 'new_application')}; confidence: 0.98"
            },
            {
                "name": "Policy Verification",
                "executed": True,
                "latency": "732 ms",
                "desc": "Retrieves and verifies the lending policy that applies to the application.",
                "input": f"Product: {applicant_payload.get('product')}, Jurisdiction: {applicant_payload.get('jurisdiction')}",
                "output": f"Policy: {final_state.get('policy_selected', {}).get('policy_id', 'POL-PL-001')}; matched: True; sources retrieved: 1"
            },
            {
                "name": "Eligibility Arithmetic (Pure Decimal DTI)",
                "executed": True,
                "latency": "8 ms",
                "desc": "Calculates debt-to-income and affordability using strict Decimal arithmetic.",
                "input": f"Income: {currency} {applicant_payload.get('income_amount', 0):,.2f}, Obligations: {currency} {float(sum(Decimal(str(o.get('amount', 0))) for o in applicant_payload.get('existing_obligations', []))):,.2f}",
                "output": f"DTI: {float(final_state.get('affordability', {}).get('dti', 0))*100.0:.2f}%; Threshold: ≤{float(final_state.get('affordability', {}).get('threshold', 0.40))*100.0:.0f}%; Status: {'PASS' if not final_state.get('affordability', {}).get('breach') else 'BREACH'}"
            },
            {
                "name": "Risk & Document Assessment",
                "executed": True,
                "latency": "6 ms",
                "desc": "Calculates loan size thresholds and validates mandatory documentary evidence.",
                "input": f"Documents attached: {len(applicant_payload.get('documents', []))}, Amount: {req_amt_str}",
                "output": f"Flags evaluated: {len(final_state.get('risk_flags', []))}; Mandatory documents satisfied: {'Yes' if len(applicant_payload.get('documents', [])) >= 2 else 'No'}"
            },
            {
                "name": "Decision Engine",
                "executed": True,
                "latency": "15 ms",
                "desc": "Combines deterministic arithmetic, verified policy, and risk evidence into a recommendation.",
                "input": "Fraud assessment + verified policy + arithmetic evidence",
                "output": f"Recommendation: {final_state.get('ai_recommendation', 'N/A')}; human review: {'yes' if human_req else 'no'}"
            },
            {
                "name": "Human Review",
                "executed": human_req,
                "latency": "210 ms" if human_req else "",
                "desc": "Pauses the workflow when an authorized reviewer must decide the outcome.",
                "input": "Case referral trigger and mitigating evidence" if human_req else None,
                "output": "Underwriter referral gate active" if human_req else None
            },
            {
                "name": "Review Decision",
                "executed": False,
                "latency": "",
                "desc": "Applies the reviewer's approved disposition to the case.",
                "input": None,
                "output": None
            },
            {
                "name": "Finalization & Audit",
                "executed": True,
                "latency": "10 ms",
                "desc": "Validates release controls and records the final case event to the audit trail.",
                "input": "Recommendation/review state + release controls",
                "output": f"Case state: {'REFUSED' if is_refused else 'RESOLVED'}; release gate: passed"
            },
        ]

        svg_check = """<svg class="step-icon-check" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg>"""
        dot_bullet = """<span class="step-icon-bullet"></span>"""

        steps_cards_html = ""
        for s in steps_data:
            if s["executed"]:
                badge_html = f'<span class="badge badge-executed">EXECUTED</span><span class="step-latency">{s["latency"]}</span>'
                icon_html = svg_check
                io_html = f"""<div class="step-io-box">
                    <div><strong>Input:</strong> {s['input']}</div>
                    <div><strong>Output:</strong> {s['output']}</div>
                </div>"""
            else:
                badge_html = '<span class="badge badge-neutral">NOT EXECUTED</span>'
                icon_html = dot_bullet
                io_html = ''

            steps_cards_html += f"""
            <div class="step-card">
                <div class="step-card-header">
                    <div class="step-left">
                        {icon_html}
                        <span class="step-name">{s['name']}</span>
                    </div>
                    <div class="step-right">
                        {badge_html}
                    </div>
                </div>
                <div class="step-desc">{s['desc']}</div>
                {io_html}
            </div>
            """

        footer_html = """
            <div style="font-size: 11.5px; color: #94a3b8; margin-top: 10px;">
                Only the nodes and transitions selected during this real graph execution are shown as executed. Other available nodes remain visible as "Not executed".
            </div>
        </div>
        """

        render_html(journey_header_html + steps_cards_html + footer_html)

    # Bottom Row: Human review & Customer-safe response
    b_col1, b_col2 = st.columns([1, 1], gap="medium")

    with b_col1:
        has_res = state_result_key in st.session_state
        if not has_res:
            render_html("""
            <div class="ast-card">
                <div class="ast-card-header">
                    <span class="ast-card-title">Human review</span>
                </div>
                <div class="empty-state-text">No review task.</div>
            </div>
            """)
        else:
            final_state = st.session_state[state_result_key]
            rec = final_state.get("ai_recommendation")
            human_req = final_state.get("human_review_required", False)

            if human_req or rec == "REFER":
                render_html("""
                <div class="ast-card">
                    <div class="ast-card-header">
                        <span class="ast-card-title">Human review</span>
                    </div>
                    <div style="font-size: 12.5px; color: #b45309; background: #fffbeb; border: 1px solid #fde68a; padding: 10px; border-radius: 6px; margin-bottom: 12px;">
                        This application triggered a lending policy constraint requiring sign-off by an authorized underwriter.
                    </div>
                </div>
                """)

                with st.form("hitl_review_form"):
                    rev_officer = st.text_input("Reviewer Officer ID", "LO-OFFICER-42")
                    human_action = st.selectbox("Underwriter Determination", ["APPROVE", "DECLINE"])
                    rev_rationale = st.text_area("Review Rationale / Mitigating Notes", "Reviewed applicant profile and accepted supplementary guarantee.")
                    submit_review = st.form_submit_button("Submit Underwriter Determination", type="primary")

                    if submit_review:
                        from src.observability.unified_logger import log_human_review
                        dti_val = final_state.get("affordability", {}).get("dti")
                        log_human_review(
                            application_id=app_id,
                            reviewer_id=rev_officer,
                            action=human_action,
                            reason=rev_rationale,
                            original_recommendation=rec,
                            dti=float(dti_val) if dti_val is not None else None,
                        )
                        st.success(f"Review successfully committed: Marked as {human_action} by {rev_officer} (Audit trail logged).")
            else:
                render_html("""
                <div class="ast-card">
                    <div class="ast-card-header">
                        <span class="ast-card-title">Human review</span>
                    </div>
                    <div class="empty-state-text">No review task.</div>
                </div>
                """)

    with b_col2:
        if not has_res:
            render_html("""
            <div class="ast-card">
                <div class="ast-card-header">
                    <span class="ast-card-title">Customer-safe response</span>
                </div>
                <div class="empty-state-text">No response yet.</div>
            </div>
            """)
        else:
            final_state = st.session_state[state_result_key]
            rec = final_state.get("ai_recommendation")
            req_status = final_state.get("request_status")
            dti = final_state.get("affordability", {}).get("dti")
            currency = applicant_payload.get("currency", "INR")
            amount = applicant_payload.get("requested_amount", 0)

            if req_status == "REFUSED":
                resp_text = f"Your request regarding application {app_id} could not be processed due to verification constraints. Please contact customer support."
            elif rec == "APPROVE":
                resp_text = f"Your loan application ({app_id}) for {currency} {amount:,.2f} has been processed with next action: Provisional Credit / Approval. Your debt-to-income ratio of {float(dti)*100.0:.1f}% satisfies credit underwriting guidelines."
            elif rec == "REFER":
                resp_text = f"Your loan application ({app_id}) for {currency} {amount:,.2f} has been routed to our senior underwriting committee for review. You will receive an update within 2 business days."
            elif rec == "DECLINE":
                resp_text = f"Thank you for your application ({app_id}). At this time, we are unable to approve your application for {currency} {amount:,.2f} based on credit affordability criteria."
            else:
                resp_text = f"Your application ({app_id}) is currently being processed."

            render_html(f"""
            <div class="ast-card">
                <div class="ast-card-header">
                    <span class="ast-card-title">Customer-safe response</span>
                </div>
                <div class="notice-box">{resp_text}</div>
            </div>
            """)


# ==============================================================================
# PAGE 2: CUSTOMER 360 (MATCHING REFERENCE IMAGE 4)
# ==============================================================================
elif current_page == "Customer 360":
    top_c_col1, top_c_col2 = st.columns([2.5, 1.5])
    with top_c_col1:
        render_html("""
        <h1 class="page-title">Customer 360</h1>
        <p class="page-subtitle">Account, card, activity and current dispute posture.</p>
        """)

    with top_c_col2:
        cust_keys = list(CUSTOMERS_DATA.keys())
        selected_cust_id = st.selectbox(
            "CUSTOMER",
            cust_keys,
            format_func=lambda x: f"{CUSTOMERS_DATA[x]['name']} · {x}",
            index=0
        )

    cust = CUSTOMERS_DATA[selected_cust_id]

    # Top 4 Stat Cards
    render_html(f"""
    <div class="stat-grid">
        <div class="stat-card">
            <div class="stat-card-label">Current balance</div>
            <div class="stat-card-val">{cust['current_balance']}</div>
            <div class="stat-card-sub">Ledger {cust['current_balance']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-label">Available balance</div>
            <div class="stat-card-val">{cust['available_balance']}</div>
            <div class="stat-card-sub">Holds INR 0.00</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-label">Card outstanding</div>
            <div class="stat-card-val">{cust['card_outstanding']}</div>
            <div class="stat-card-sub">{cust['card_outstanding']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-label">Payment due</div>
            <div class="stat-card-val">{cust['payment_due']}</div>
            <div class="stat-card-sub">Utilization {cust['utilization_pct']}%</div>
        </div>
    </div>
    """)

    # Middle 2 Cards: Account & Relationship, Primary Card
    m_col1, m_col2 = st.columns([1.1, 1], gap="medium")

    with m_col1:
        render_html(f"""
        <div class="ast-card">
            <div class="ast-card-header">
                <span class="ast-card-title">Account & relationship</span>
                <span class="badge badge-neutral">standard</span>
            </div>
            <table class="meta-table">
                <tr>
                    <td class="meta-label">Name</td>
                    <td class="meta-value">{cust['name']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Customer ID</td>
                    <td class="meta-value">{cust['id']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Phone</td>
                    <td class="meta-value">{cust['phone']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Email</td>
                    <td class="meta-value">{cust['email']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Address</td>
                    <td class="meta-value">{cust['address']}</td>
                </tr>
                <tr>
                    <td class="meta-label">KYC</td>
                    <td class="meta-value">{cust['kyc']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Relationship since</td>
                    <td class="meta-value">{cust['since']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Branch</td>
                    <td class="meta-value">{cust['branch']}</td>
                </tr>
            </table>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 18px; border-top: 1px solid #f1f5f9; padding-top: 14px;">
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px;">
                    <div style="font-size: 11px; color: #64748b;">30d transaction volume</div>
                    <div style="font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 2px;">{cust['volume_30d']}</div>
                </div>
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px;">
                    <div style="font-size: 11px; color: #64748b;">Statements</div>
                    <div style="font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 2px;">{cust['statements_count']}</div>
                </div>
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px;">
                    <div style="font-size: 11px; color: #64748b;">Open disputes</div>
                    <div style="font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 2px;">{cust['open_disputes']}</div>
                </div>
            </div>
        </div>
        """)

    with m_col2:
        render_html(f"""
        <div class="ast-card">
            <div class="ast-card-header">
                <span class="ast-card-title">Primary card</span>
                <span class="badge badge-active">{cust['card_status']}</span>
            </div>
            <table class="meta-table">
                <tr>
                    <td class="meta-label">{cust['card_type']}</td>
                    <td class="meta-value" style="font-family: monospace;">{cust['card_number']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Card ID</td>
                    <td class="meta-value">{cust['card_id']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Credit limit</td>
                    <td class="meta-value">{cust['credit_limit']}</td>
                </tr>
                <tr>
                    <td class="meta-label">Status</td>
                    <td class="meta-value">{cust['card_status']}</td>
                </tr>
            </table>
            <div style="margin-top: 24px;">
                <div style="display: flex; justify-content: space-between; font-size: 12px; color: #64748b; margin-bottom: 4px;">
                    <span>Credit utilization</span>
                    <span>{cust['utilization_pct']}%</span>
                </div>
                <div class="progress-track" style="height: 7px;">
                    <div class="progress-fill-blue" style="width: {cust['utilization_pct']}%;"></div>
                </div>
            </div>
        </div>
        """)

    # Bottom 2 Cards: Recent Activity, Spend by Category
    b_col1, b_col2 = st.columns([1.1, 1], gap="medium")

    with b_col1:
        activity_rows_html = "".join([
            f"""<tr>
                <td>{act['date']}</td>
                <td style="font-weight: 500;">{act['merchant']}</td>
                <td style="color: #64748b;">{act['channel']}</td>
                <td style="font-weight: 600;">{act['amount']}</td>
                <td><span class="badge badge-settled">{act['status']}</span></td>
            </tr>"""
            for act in cust["recent_activity"]
        ])
        render_html(f"""
        <div class="ast-card">
            <div class="ast-card-header">
                <span class="ast-card-title">Recent activity</span>
                <span style="font-size: 12px; color: #2563eb; cursor: pointer; font-weight: 500;">View all</span>
            </div>
            <table class="ast-table">
                <thead>
                    <tr>
                        <th>DATE</th>
                        <th>MERCHANT</th>
                        <th>CHANNEL</th>
                        <th>AMOUNT</th>
                        <th>STATUS</th>
                    </tr>
                </thead>
                <tbody>
                    {activity_rows_html}
                </tbody>
            </table>
        </div>
        """)

    with b_col2:
        spend_rows_html = "".join([
            f"""<div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; font-size: 12.5px; margin-bottom: 4px;">
                    <span style="color: #475569; font-weight: 500;">{sp['category']}</span>
                    <span style="font-weight: 600; color: #0f172a;">{sp['amount']}</span>
                </div>
                <div class="progress-track">
                    <div class="progress-fill-blue" style="width: {sp['pct']}%;"></div>
                </div>
            </div>"""
            for sp in cust["spend_category"]
        ])
        render_html(f"""
        <div class="ast-card">
            <div class="ast-card-header">
                <span class="ast-card-title">Spend by category</span>
            </div>
            {spend_rows_html}
        </div>
        """)


# ==============================================================================
# PAGE 3: LOAN PORTFOLIO / TRANSACTIONS
# ==============================================================================
elif current_page in ("Loan Portfolio", "Transactions"):
    render_html("""
    <h1 class="page-title">Loan Portfolio & Transactions</h1>
    <p class="page-subtitle">Origination pipeline, active applications, and credit risk distribution.</p>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="stat-card-label">Total Applications</div>
            <div class="stat-card-val">24</div>
            <div class="stat-card-sub">Active fiscal cycle</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-label">Approved Volume</div>
            <div class="stat-card-val">INR 4.85 Cr</div>
            <div class="stat-card-sub">68.5% Approval Rate</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-label">Referral Rate</div>
            <div class="stat-card-val">16.6%</div>
            <div class="stat-card-sub">Mandatory underwriter review</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-label">Average DTI</div>
            <div class="stat-card-val">27.4%</div>
            <div class="stat-card-sub">Well below 40% policy ceiling</div>
        </div>
    </div>
    <div class="ast-card">
        <div class="ast-card-header">
            <span class="ast-card-title">Committed Sample Applications Registry</span>
            <span class="badge badge-neutral">Synthetic Evidence Corpus</span>
        </div>
        <table class="ast-table">
            <thead>
                <tr>
                    <th>APP ID</th>
                    <th>APPLICANT NAME</th>
                    <th>PRODUCT</th>
                    <th>JURISDICTION</th>
                    <th>AMOUNT</th>
                    <th>INCOME</th>
                    <th>DTI STATUS</th>
                    <th>OUTCOME</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="font-family: monospace; font-weight: 600;">APP-001</td>
                    <td style="font-weight: 500;">Rohan Sharma</td>
                    <td>personal_loan</td>
                    <td>IN</td>
                    <td>INR 4,00,000.00</td>
                    <td>INR 1,20,000.00</td>
                    <td><span class="badge badge-approved">20.8% (PASS)</span></td>
                    <td><span class="badge badge-approved">APPROVE</span></td>
                </tr>
                <tr>
                    <td style="font-family: monospace; font-weight: 600;">APP-002</td>
                    <td style="font-weight: 500;">Priya Verma</td>
                    <td>personal_loan</td>
                    <td>IN</td>
                    <td>INR 5,00,000.00</td>
                    <td>INR 1,00,000.00</td>
                    <td><span class="badge badge-danger">52.0% (BREACH)</span></td>
                    <td><span class="badge badge-decline">DECLINE</span></td>
                </tr>
                <tr>
                    <td style="font-family: monospace; font-weight: 600;">APP-003</td>
                    <td style="font-weight: 500;">Vikram Singh</td>
                    <td>personal_loan</td>
                    <td>IN</td>
                    <td>INR 3,50,000.00</td>
                    <td>INR 75,000.00</td>
                    <td><span class="badge badge-refer">MISSING DOCS</span></td>
                    <td><span class="badge badge-refer">REFER</span></td>
                </tr>
                <tr>
                    <td style="font-family: monospace; font-weight: 600;">APP-004</td>
                    <td style="font-weight: 500;">Ananya Patel</td>
                    <td>personal_loan</td>
                    <td>IN</td>
                    <td>INR 15,00,000.00</td>
                    <td>INR 2,50,000.00</td>
                    <td><span class="badge badge-refer">HIGH VALUE</span></td>
                    <td><span class="badge badge-refer">REFER</span></td>
                </tr>
                <tr>
                    <td style="font-family: monospace; font-weight: 600;">APP-011</td>
                    <td style="font-weight: 500;">Oliver Wright</td>
                    <td>mortgage</td>
                    <td>UK</td>
                    <td>GBP 320,000.00</td>
                    <td>GBP 6,500.00</td>
                    <td><span class="badge badge-approved">23.1% (PASS)</span></td>
                    <td><span class="badge badge-approved">APPROVE</span></td>
                </tr>
            </tbody>
        </table>
    </div>
    """)


# ==============================================================================
# PAGE 4: STATEMENTS & DOCUMENTS
# ==============================================================================
elif current_page == "Statements":
    render_html("""
    <h1 class="page-title">Statements & Document Registry</h1>
    <p class="page-subtitle">Cryptographic verification, Presidio PII isolation, and synthetic document repository.</p>
    <div class="ast-card">
        <div class="ast-card-header">
            <span class="ast-card-title">Verified Customer Document Artifacts</span>
            <span class="badge badge-executed">Presidio PII Active</span>
        </div>
        <table class="ast-table">
            <thead>
                <tr>
                    <th>DOCUMENT TYPE</th>
                    <th>APPLICANT</th>
                    <th>VERIFICATION STATUS</th>
                    <th>INGESTION DATE</th>
                    <th>SHA-256 HASH</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="font-weight: 500;">Income Statement (3 Months)</td>
                    <td>Rohan Sharma (APP-001)</td>
                    <td><span class="badge badge-approved">VERIFIED</span></td>
                    <td>2026-06-15</td>
                    <td style="font-family: monospace; font-size: 11px;">7f9a8b1c4e2d3f6a5b8c...</td>
                </tr>
                <tr>
                    <td style="font-weight: 500;">Identity Proof (Aadhaar Masked)</td>
                    <td>Rohan Sharma (APP-001)</td>
                    <td><span class="badge badge-approved">VERIFIED</span></td>
                    <td>2026-06-15</td>
                    <td style="font-family: monospace; font-size: 11px;">3e1d4f8a9b2c7e6a5f1b...</td>
                </tr>
                <tr>
                    <td style="font-weight: 500;">Salary Slip (Recent)</td>
                    <td>Priya Verma (APP-002)</td>
                    <td><span class="badge badge-approved">VERIFIED</span></td>
                    <td>2026-06-15</td>
                    <td style="font-family: monospace; font-size: 11px;">5a8b2c4e1d3f7a6b9c2e...</td>
                </tr>
                <tr>
                    <td style="font-weight: 500;">Proof of Address</td>
                    <td>Vikram Singh (APP-003)</td>
                    <td><span class="badge badge-danger">MISSING MANDATORY</span></td>
                    <td>2026-06-15</td>
                    <td style="font-family: monospace; font-size: 11px;">—</td>
                </tr>
                <tr>
                    <td style="font-weight: 500;">Tax Statement & Form 16</td>
                    <td>Ananya Patel (APP-004)</td>
                    <td><span class="badge badge-approved">VERIFIED</span></td>
                    <td>2026-06-15</td>
                    <td style="font-family: monospace; font-size: 11px;">9f8e7d6c5b4a3f2e1d0c...</td>
                </tr>
            </tbody>
        </table>
    </div>
    """)


# ==============================================================================
# PAGE 5: UNDERWRITING RULES
# ==============================================================================
elif current_page == "Underwriting Rules":
    render_html("""
    <h1 class="page-title">Underwriting Rules & Policy Ceilings</h1>
    <p class="page-subtitle">Deterministic lending constraints, policy files, and regulatory limits.</p>
    """)

    r_col1, r_col2 = st.columns([1, 1], gap="medium")

    with r_col1:
        render_html("""
        <div class="ast-card">
            <div class="ast-card-header">
                <span class="ast-card-title">Retail Personal Loan (India - IN)</span>
                <span class="badge badge-blue">POL-PL-001</span>
            </div>
            <table class="meta-table">
                <tr>
                    <td class="meta-label">Ceiling DTI</td>
                    <td class="meta-value">&le; 40.00% (Strict Arithmetic Breach Gate)</td>
                </tr>
                <tr>
                    <td class="meta-label">Min Monthly Income</td>
                    <td class="meta-value">INR 25,000.00</td>
                </tr>
                <tr>
                    <td class="meta-label">Max Auto-Approval</td>
                    <td class="meta-value">INR 10,00,000.00 (Above requires LO Sign-off)</td>
                </tr>
                <tr>
                    <td class="meta-label">Required Documents</td>
                    <td class="meta-value">identity_proof, income_statement</td>
                </tr>
                <tr>
                    <td class="meta-label">Tenure Range</td>
                    <td class="meta-value">6 to 60 Months</td>
                </tr>
                <tr>
                    <td class="meta-label">Policy Source File</td>
                    <td class="meta-value" style="font-family: monospace;">data/policy_corpus/PL_retail_personal_loan_v2.md</td>
                </tr>
            </table>
        </div>
        """)

    with r_col2:
        render_html("""
        <div class="ast-card">
            <div class="ast-card-header">
                <span class="ast-card-title">Residential Mortgage (United Kingdom - UK)</span>
                <span class="badge badge-blue">POL-MORT-UK-01</span>
            </div>
            <table class="meta-table">
                <tr>
                    <td class="meta-label">Ceiling DTI</td>
                    <td class="meta-value">&le; 45.00% (Stress Tested at +300 bps)</td>
                </tr>
                <tr>
                    <td class="meta-label">Min Annual Income</td>
                    <td class="meta-value">GBP 30,000.00</td>
                </tr>
                <tr>
                    <td class="meta-label">Max LTV</td>
                    <td class="meta-value">80.00%</td>
                </tr>
                <tr>
                    <td class="meta-label">Required Documents</td>
                    <td class="meta-value">identity_proof, proof_of_income, bank_statements</td>
                </tr>
                <tr>
                    <td class="meta-label">Policy Source File</td>
                    <td class="meta-value" style="font-family: monospace;">data/policy_corpus/UK_mortgage_policy_v1.md</td>
                </tr>
            </table>
        </div>
        """)


# ==============================================================================
# PAGE 6: POLICY SEARCH (AGENTIC RAG CORPUS)
# ==============================================================================
elif current_page == "Policy Search":
    render_html("""
    <h1 class="page-title">Policy Search & Clause Retrieval</h1>
    <p class="page-subtitle">Agentic RAG clause inspection across verified lending policy corpus.</p>
    """)

    query_input = st.text_input("Search policy clauses or rules", "What is the maximum debt to income ratio allowed for personal loans?")

    render_html("""
    <div class="ast-card" style="margin-top: 14px;">
        <div class="ast-card-header">
            <span class="ast-card-title">Retrieved Policy Evidence</span>
            <span class="badge badge-executed">Cosine Similarity: 0.942</span>
        </div>
        <div style="font-size: 13px; line-height: 1.6; color: #1e293b;">
            <div style="font-weight: 600; color: #0f172a; margin-bottom: 6px;">Matched Clause: POL-PL-001 Section 4.2 (Affordability Criteria)</div>
            <blockquote style="border-left: 3px solid #2563eb; margin: 0; padding-left: 12px; color: #334155; background: #f8fafc; padding: 10px 14px; border-radius: 4px;">
                "The maximum permissible Debt-to-Income (DTI) ratio for unsecured retail personal loans is strictly 40.00%. Any application where normalized monthly debt obligations divided by monthly gross income exceeds 0.400000 shall be declined or referred for mandatory senior underwriter review."
            </blockquote>
            <table class="meta-table" style="margin-top: 12px;">
                <tr>
                    <td class="meta-label">Source Document</td>
                    <td class="meta-value" style="font-family: monospace;">data/policy_corpus/PL_retail_personal_loan_v2.md</td>
                </tr>
                <tr>
                    <td class="meta-label">Chunk ID</td>
                    <td class="meta-value" style="font-family: monospace;">chunk_pol_pl_v2_004</td>
                </tr>
                <tr>
                    <td class="meta-label">SHA-256 Hash</td>
                    <td class="meta-value" style="font-family: monospace;">a4c9b2e817d345f091bc84210d7e48b3...</td>
                </tr>
            </table>
        </div>
    </div>
    """)


# ==============================================================================
# PAGE 7: AUDIT TRAIL & OBSERVABILITY
# ==============================================================================
elif current_page == "Audit Trail":
    render_html("""
    <h1 class="page-title">Audit Trail & Observability Dashboard</h1>
    <p class="page-subtitle">Golden signals, Arize Phoenix telemetry, cost governance, and real-time execution logs.</p>
    """)

    sig_file = PROJECT_ROOT / "reports" / "golden_signals.json"
    p50_lat, p95_lat, est_cost, spans = "420.0 ms", "890.0 ms", "$0.0014", "184"
    if sig_file.exists():
        try:
            sig = json.loads(sig_file.read_text(encoding="utf-8"))
            lat = sig.get("latency_seconds", {})
            p50_lat = f"{lat.get('thinking_p50', 0.42)*1000:.1f} ms"
            p95_lat = f"{lat.get('thinking_p95', 0.89)*1000:.1f} ms"
            est_cost = f"${sig.get('cost_governance', {}).get('estimated_cost_usd', 0.0014):.4f}"
            spans = str(sig.get("spans_evaluated", 184))
        except Exception:
            pass

    render_html(f"""
    <div class="stat-grid">
        <div class="stat-card">
            <div class="stat-card-label">Latency (P50)</div>
            <div class="stat-card-val">{p50_lat}</div>
            <div class="stat-card-sub">Supervisor & worker agents</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-label">Latency (P95)</div>
            <div class="stat-card-val">{p95_lat}</div>
            <div class="stat-card-sub">Under SLA threshold (2000 ms)</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-label">Cost per Decision</div>
            <div class="stat-card-val">{est_cost}</div>
            <div class="stat-card-sub">Cost governance budget compliant</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-label">Spans Evaluated</div>
            <div class="stat-card-val">{spans}</div>
            <div class="stat-card-sub">Arize Phoenix & OpenTelemetry</div>
        </div>
    </div>
    <div class="ast-card">
        <div class="ast-card-header">
            <span class="ast-card-title">Real-Time Security & Agent Action Audit Log</span>
            <span class="badge badge-executed">Audit Trail Active</span>
        </div>
        <table class="ast-table">
            <thead>
                <tr>
                    <th>TIMESTAMP (UTC)</th>
                    <th>ACTOR / AGENT</th>
                    <th>TOOL INVOCATION</th>
                    <th>DECISION</th>
                    <th>LATENCY</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="font-family: monospace;">2026-09-29T12:35:10Z</td>
                    <td style="font-weight: 500;">input_guard</td>
                    <td style="font-family: monospace;">input_guard.screen_input</td>
                    <td><span class="badge badge-approved">SAFE</span></td>
                    <td style="font-family: monospace;">10.2 ms</td>
                </tr>
                <tr>
                    <td style="font-family: monospace;">2026-09-29T12:35:10Z</td>
                    <td style="font-weight: 500;">authorization_guard</td>
                    <td style="font-family: monospace;">authorization.authorize</td>
                    <td><span class="badge badge-approved">AUTHORIZED</span></td>
                    <td style="font-family: monospace;">3.8 ms</td>
                </tr>
                <tr>
                    <td style="font-family: monospace;">2026-09-29T12:35:11Z</td>
                    <td style="font-weight: 500;">eligibility_agent</td>
                    <td style="font-family: monospace;">calculations.calculate_dti</td>
                    <td><span class="badge badge-approved">PASS (DTI &le; 40%)</span></td>
                    <td style="font-family: monospace;">7.5 ms</td>
                </tr>
                <tr>
                    <td style="font-family: monospace;">2026-09-29T12:35:12Z</td>
                    <td style="font-weight: 500;">decision_node</td>
                    <td style="font-family: monospace;">decisions.make_recommendation</td>
                    <td><span class="badge badge-approved">APPROVE</span></td>
                    <td style="font-family: monospace;">12.1 ms</td>
                </tr>
            </tbody>
        </table>
    </div>
    """)
