"""CPE Model Registry — Configuration-driven model management.

Loads model definitions from models.yaml and provides unified interface
for model defaults, API versions, and capabilities per adapter.

Date: 2026-03-21
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


# Default registry (fallback if YAML not available)
# models is a dict of {model_name: {context_window: int, ...}}
_DEFAULT_REGISTRY: dict[str, Any] = {
    "anthropic": {
        "default": "claude-opus-4-6",
        "api_version": "2024-06-15",
        "max_tokens": 8192,
        "models": {
            "claude-opus-4-6":           {"context_window": 200000},
            "claude-sonnet-4-6":         {"context_window": 200000},
            "claude-haiku-4-5-20251001": {"context_window": 200000},
        },
    },
    "openai": {
        "default": "gpt-4o",
        "api_url": "https://api.openai.com/v1",
        "max_tokens": 8192,
        "models": {
            "gpt-4o":      {"context_window": 128000},
            "gpt-4o-mini": {"context_window": 128000},
            "gpt-4-turbo": {"context_window": 128000},
        },
        "supports": {"prompt_caching": True, "streaming": False, "vision": True},
    },
    "google": {
        "default": "gemini-2.0-flash",
        "api_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "max_tokens": 8192,
        "models": {
            "gemini-2.5-flash":                    {"context_window": 1048576},
            "gemini-3-flash-preview":              {"context_window": 1048576},
            "gemini-3.1-flash-lite-preview":       {"context_window": 1048576},
            "gemini-3.1-pro-preview":              {"context_window": 1048576},
            "gemini-2.0-flash":                    {"context_window": 1048576},
            "gemini-2.0-flash-thinking-exp-01-21": {"context_window": 1048576},
            "gemini-1.5-pro":                      {"context_window": 2097152},
        },
        "supports": {"thinking": True, "streaming": False},
    },
    "ollama": {
        "default": "llama3.2",
        "api_url": "http://localhost:11434",
        "max_tokens": 8192,
        "models": {
            "llama3.2":    {},
            "llama2":      {},
            "neural-chat": {},
            "mistral":     {},
        },
        "supports": {"streaming": True, "local_only": True},
    },
}


def _load_registry() -> dict[str, Any]:
    """Load model registry from models.yaml, fallback to defaults."""
    if yaml is None:
        return _DEFAULT_REGISTRY

    yaml_path = Path(__file__).parent / "models.yaml"
    if not yaml_path.exists():
        return _DEFAULT_REGISTRY

    try:
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
            if config and "adapters" in config:
                return config["adapters"]
    except Exception:
        pass

    return _DEFAULT_REGISTRY


_REGISTRY = _load_registry()


def get_default_model(adapter: str) -> str:
    """Return default model for given adapter.

    Args:
        adapter: Adapter name ("anthropic", "openai", "google", "ollama", etc.)

    Returns:
        Model name (e.g., "claude-opus-4-6", "gpt-4o")
    """
    env_var = f"{adapter.upper()}_MODEL"
    env_model = os.environ.get(env_var)
    if env_model:
        return env_model

    entry = _REGISTRY.get(adapter, {})
    return entry.get("default", "")


def get_api_version(adapter: str) -> str:
    """Return API version for given adapter.

    Args:
        adapter: Adapter name

    Returns:
        API version string (e.g., "2024-06-15")
    """
    entry = _REGISTRY.get(adapter, {})
    return entry.get("api_version", "")


def get_max_tokens(adapter: str) -> int:
    """Return max tokens for given adapter.

    Args:
        adapter: Adapter name

    Returns:
        Max output tokens (default: 8192)
    """
    entry = _REGISTRY.get(adapter, {})
    return entry.get("max_tokens", 8192)


def list_models(adapter: str) -> list[str]:
    """Return list of supported models for given adapter.

    Args:
        adapter: Adapter name

    Returns:
        List of model names
    """
    entry = _REGISTRY.get(adapter, {})
    models = entry.get("models", {})
    if isinstance(models, dict):
        return list(models.keys())
    return list(models)


def get_context_window(adapter: str, model: str) -> int:
    """Return the real context window size for a given adapter+model.

    Returns 0 if the model is not in the registry (e.g. custom Ollama models).
    Callers should treat 0 as "unknown" and suppress ctx% display.

    Args:
        adapter: Adapter name ("anthropic", "openai", "google", "ollama", …)
        model:   Model identifier as used in the API call

    Returns:
        Context window in tokens, or 0 if unknown.
    """
    entry = _REGISTRY.get(adapter, {})
    models = entry.get("models", {})
    if isinstance(models, dict):
        return int(models.get(model, {}).get("context_window", 0))
    return 0


def supports_feature(adapter: str, feature: str) -> bool:
    """Check if adapter supports given feature.

    Args:
        adapter: Adapter name
        feature: Feature name (e.g., "prompt_caching", "streaming", "thinking")

    Returns:
        True if adapter supports feature
    """
    entry = _REGISTRY.get(adapter, {})
    supports = entry.get("supports", {})
    return supports.get(feature, False)
