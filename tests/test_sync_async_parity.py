"""
Parity Tests: Synchronous Wrappers vs Canonical Asynchronous Agent Nodes.
Ensures 100% behavioral and state contract parity between sync and async execution paths.
"""

import pytest
import asyncio
from decimal import Decimal
from src.state import create_initial_state
from src.domain.models import RuleEvaluationResult
from src.agents.policy_agent import policy_agent_node, apolicy_agent_node
from src.agents.eligibility_agent import eligibility_agent_node, aeligibility_agent_node
from src.agents.risk_agent import risk_agent_node, arisk_agent_node
from src.agents.decision_agent import decision_agent_node, adecision_agent_node


def test_policy_agent_sync_async_parity():
    state_sync = create_initial_state("APP-PARITY-POL")
    state_sync["loan_product"] = "personal_loan"
    state_sync["jurisdiction"] = "IN"
    state_sync["application_date"] = "2026-06-15"

    state_async = create_initial_state("APP-PARITY-POL")
    state_async["loan_product"] = "personal_loan"
    state_async["jurisdiction"] = "IN"
    state_async["application_date"] = "2026-06-15"

    res_sync = policy_agent_node(state_sync)
    res_async = asyncio.run(apolicy_agent_node(state_async))

    assert res_sync["policy_selected"] == res_async["policy_selected"]
    assert res_sync["policy_citations"] == res_async["policy_citations"]
    assert res_sync["step_count"] == res_async["step_count"]


def test_eligibility_agent_sync_async_parity():
    state_sync = create_initial_state("APP-PARITY-ELIG")
    state_sync["applicant_facts"] = {
        "income_amount": 100000,
        "income_period": "monthly",
        "existing_obligations": [{"amount": 30000}],
        "requested_amount": 200000,
        "tenor_months": 24,
    }
    state_sync["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    state_async = create_initial_state("APP-PARITY-ELIG")
    state_async["applicant_facts"] = dict(state_sync["applicant_facts"])
    state_async["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    res_sync = eligibility_agent_node(state_sync)
    res_async = asyncio.run(aeligibility_agent_node(state_async))

    assert res_sync["affordability"] == res_async["affordability"]
    assert res_sync["step_count"] == res_async["step_count"]


def test_risk_agent_sync_async_parity():
    state_sync = create_initial_state("APP-PARITY-RISK")
    state_sync["affordability"] = {
        "dti": 0.55,
        "disposable_income": 45000.0,
        "breach": True,
        "threshold": 0.40,
    }
    state_sync["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    state_async = create_initial_state("APP-PARITY-RISK")
    state_async["affordability"] = dict(state_sync["affordability"])
    state_async["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    res_sync = risk_agent_node(state_sync)
    res_async = asyncio.run(arisk_agent_node(state_async))

    assert res_sync["risk_flags"] == res_async["risk_flags"]
    assert res_sync["step_count"] == res_async["step_count"]


def test_decision_agent_sync_async_parity():
    state_sync = create_initial_state("APP-PARITY-DEC")
    state_sync["affordability"] = {
        "dti": 0.35,
        "disposable_income": 65000.0,
        "breach": False,
        "threshold": 0.40,
    }
    state_sync["_rule_results"] = [
        RuleEvaluationResult(
            rule_id="PL-07",
            rule_type="dti_max",
            passed=True,
            threshold_value=0.40,
            actual_value=0.35,
            operator="<=",
            message="DTI within limits",
            requires_human_review=False,
        ).model_dump()
    ]
    state_sync["risk_flags"] = []
    state_sync["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    state_async = create_initial_state("APP-PARITY-DEC")
    state_async["affordability"] = dict(state_sync["affordability"])
    state_async["_rule_results"] = list(state_sync["_rule_results"])
    state_async["risk_flags"] = []
    state_async["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    res_sync = decision_agent_node(state_sync)
    res_async = asyncio.run(adecision_agent_node(state_async))

    assert res_sync["decision_status"] == res_async["decision_status"]
    assert res_sync["ai_recommendation"] == res_async["ai_recommendation"]
    assert res_sync["human_review_required"] == res_async["human_review_required"]
