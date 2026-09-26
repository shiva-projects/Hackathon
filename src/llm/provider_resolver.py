"""
Deterministic LLM Provider Resolver.
Per v8 Addendum Section 3 & 5.
Resolves provider from config/model_config.json based on environment keys.
Does NOT make any network or LLM calls.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Tuple


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


def resolve_provider(config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Walk config['resolution_order'] in order; return the first provider whose
    env_key is set in the environment. Raises if none are set — this must never
    silently continue with no model, per Rule 10 of the developer contract.
    """
    resolution_order = config.get("resolution_order", [])
    providers = config.get("providers", {})

    for name in resolution_order:
        provider = providers.get(name)
        if not provider:
            continue
        env_key = provider.get("env_key")
        val = os.environ.get(env_key) if env_key else None
        if val and str(val).strip():
            return name, provider

    tried = ", ".join(providers[n]["env_key"] for n in resolution_order if n in providers)
    raise RuntimeError(f"No configured LLM provider has a live API key. Tried: {tried}")
