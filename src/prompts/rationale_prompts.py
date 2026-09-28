"""
Versioned Underwriting Rationale Prompts.
Enforces separation of prompt templates from orchestration logic (Rule 1 & Prompt Engineering Standards).
Incorporates retrieved policy chunk rules, currency discipline, and deterministic evaluation reasons.
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal

RATIONALE_SYSTEM_PROMPT_V1 = (
    "You are a professional loan underwriting assistant in a regulated lending environment. "
    "Your role is strictly explanatory: you explain deterministic underwriting outcomes to credit officers. "
    "Under no circumstances may you alter the recommendation, invent figures, or claim to render a final legal decision. "
    "The Code decides; the LLM explains."
)

RATIONALE_USER_PROMPT_TEMPLATE_V1 = """Explain the following deterministic underwriting evaluation in 2 to 3 clear, professional sentences for the loan officer:

[Underwriting Assessment]
- AI Recommendation: {recommendation} (Advisory)
- Applicable Policy: {policy_version}
- Calculated Debt-to-Income (DTI): {dti_pct}
- DTI Breach Status: {breach_status}
- Evaluation Reasons:
{reasons_bulleted}

[Retrieved Authoritative Policy Rules]
{policy_context}

[Regulatory & Accuracy Instructions]
1. Explicitly state the advisory recommendation '{recommendation}' and calculated DTI {dti_pct}.
2. Use the application currency ({currency}). Never use foreign currency symbols (e.g. $, £, €) unless the applicant's official currency is USD, GBP, or EUR.
3. Keep the prose neutral, factual, and strictly advisory. Reference the applicable policy rules ({policy_version}).
4. Do not invent unverified applicant numbers or external credit claims.
"""


def build_rationale_prompt(
    recommendation: str,
    policy_version: str,
    dti: Decimal,
    breach: bool,
    reasons: List[str],
    citations: Optional[List[Dict[str, Any]]] = None,
    currency: str = "INR",
) -> str:
    """
    Constructs the canonical rationale prompt using versioned template V1.
    Integrates retrieved RAG policy context and application currency.
    """
    reasons_bulleted = "\n".join(f"  * {r}" for r in reasons) if reasons else "  * Standard policy thresholds satisfied."
    dti_pct = f"{float(dti):.1%}"
    breach_status = "BREACH DETECTED" if breach else "Within Acceptable Limits"

    policy_snippets = []
    if citations:
        for c in citations:
            rule_id = c.get("rule_id", "POLICY_RULE")
            text = c.get("text", "")
            policy_snippets.append(f"[{rule_id}]: {text}")
    policy_context = "\n\n".join(policy_snippets) if policy_snippets else "Standard policy guidelines applicable."

    user_prompt = RATIONALE_USER_PROMPT_TEMPLATE_V1.format(
        recommendation=recommendation,
        policy_version=policy_version,
        dti_pct=dti_pct,
        breach_status=breach_status,
        reasons_bulleted=reasons_bulleted,
        policy_context=policy_context,
        currency=currency,
    )

    return f"{RATIONALE_SYSTEM_PROMPT_V1}\n\n{user_prompt}"
