"""
Deterministic LLM Provider Resolver.
Per v8 Addendum Section 3 & 5.
Resolves provider from config/model_config.json based on environment keys.
Does NOT make any network or LLM calls.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_model_config(path: str = "config/model_config.json") -> Dict[str, Any]:
    """Loads the model configuration JSON file."""
    config_path = Path(path)
    if not config_path.is_absolute():
        # Search from project root if relative
        project_root = Path(__file__).resolve().parent.parent.parent
        resolved_path = project_root / path
        if resolved_path.exists():
            config_path = resolved_path

    if not config_path.exists():
        raise FileNotFoundError(f"Model config file not found: {path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_provider_environment(
    config: Optional[Dict[str, Any]] = None,
    config_path: str = "config/model_config.json",
) -> Dict[str, Any]:
    """
    Canonical, unified provider and key validation function.
    Per v8 specification: single source of truth across run_eval.py,
    verify_acceptance_criteria.py, decision_agent.py, and app.py.
    """
    if config is None:
        try:
            config = load_model_config(config_path)
        except Exception as exc:
            return {
                "has_live_key": False,
                "active_provider": None,
                "provider_config": None,
                "available_providers": [],
                "reason": f"Config load failure: {exc}",
            }

    forced_env_provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    resolution_order = list(config.get("resolution_order", ["gemini", "groq"]))
    providers = config.get("providers", {})
    dummy_values = {"", "your_gemini_api_key_here", "your_groq_api_key_here", "placeholder"}

    def _is_live(val: Optional[str]) -> bool:
        if not val:
            return False
        v_clean = val.strip().lower()
        return not (v_clean in dummy_values or v_clean.startswith("your_") or "placeholder" in v_clean)

    # Explicit provider override takes absolute precedence and fails closed if unconfigured
    if forced_env_provider:
        if forced_env_provider not in providers:
            return {
                "has_live_key": False,
                "active_provider": None,
                "provider_config": None,
                "available_providers": [],
                "reason": f"Unknown LLM_PROVIDER='{forced_env_provider}'. Configured providers: {list(providers.keys())}",
            }
        p_cfg = providers[forced_env_provider]
        env_key = p_cfg.get("env_key")
        val = os.environ.get(env_key)
        if not _is_live(val):
            return {
                "has_live_key": False,
                "active_provider": None,
                "provider_config": None,
                "available_providers": [],
                "reason": f"LLM_PROVIDER='{forced_env_provider}' was requested but {env_key} is not configured.",
            }
        return {
            "has_live_key": True,
            "active_provider": forced_env_provider,
            "provider_config": p_cfg,
            "available_providers": [forced_env_provider],
            "reason": f"Explicitly resolved {forced_env_provider} via LLM_PROVIDER override using {env_key}",
        }

    available = []
    for name in resolution_order:
        p_cfg = providers.get(name)
        env_key = p_cfg.get("env_key")
        val = os.environ.get(env_key)
        if _is_live(val):
            available.append(name)

    if available:
        active = available[0]
        return {
            "has_live_key": True,
            "active_provider": active,
            "provider_config": providers[active],
            "available_providers": available,
            "reason": f"Resolved {active} using {providers[active].get('env_key')}",
        }
    else:
        tried = ", ".join(providers[n].get("env_key", n) for n in resolution_order if n in providers)
        return {
            "has_live_key": False,
            "active_provider": None,
            "provider_config": None,
            "available_providers": [],
            "reason": f"No configured LLM provider has a live API key. Tried: {tried}",
        }


def has_live_provider_key(
    config: Optional[Dict[str, Any]] = None,
    config_path: str = "config/model_config.json",
) -> bool:
    """Returns True if at least one LLM provider has a live, non-placeholder API key."""
    return validate_provider_environment(config=config, config_path=config_path)["has_live_key"]


def resolve_provider(config: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Walk config['resolution_order'] in order; return the first provider whose
    env_key is set in the environment. Raises RuntimeError if none are set.
    """
    validation = validate_provider_environment(config=config)
    if validation["has_live_key"]:
        return validation["active_provider"], validation["provider_config"]
    raise RuntimeError(validation["reason"])
