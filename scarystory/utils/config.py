"""Configuration loader and manager."""

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.yaml"
LOCAL_CONFIG_PATH = "config.local.yaml"


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load configuration from YAML file.

    Loads the default config.yaml first, then overlays config.local.yaml
    if it exists (for credentials and local overrides).
    """
    base_dir = Path.cwd()

    # Load default config
    default_path = Path(config_path) if config_path else base_dir / DEFAULT_CONFIG_PATH
    if not default_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {default_path}")

    with open(default_path) as f:
        config = yaml.safe_load(f)

    # Overlay local config if it exists
    local_path = base_dir / LOCAL_CONFIG_PATH
    if local_path.exists():
        with open(local_path) as f:
            local_config = yaml.safe_load(f) or {}
        config = _deep_merge(config, local_config)
        logger.info("Loaded local config overrides from %s", local_path)

    # Apply environment variable overrides
    config = _apply_env_overrides(config)

    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(config: dict) -> dict:
    """Apply environment variable overrides for sensitive values."""
    env_mappings = {
        "REDDIT_CLIENT_ID": ("reddit", "client_id"),
        "REDDIT_CLIENT_SECRET": ("reddit", "client_secret"),
        "REDDIT_USERNAME": ("reddit", "username"),
        "REDDIT_PASSWORD": ("reddit", "password"),
        "ELEVENLABS_API_KEY": ("tts", "elevenlabs", "api_key"),
    }

    for env_var, config_path in env_mappings.items():
        value = os.environ.get(env_var)
        if value:
            _set_nested(config, config_path, value)
            logger.debug("Applied env override: %s", env_var)

    return config


def _set_nested(d: dict, keys: tuple, value: Any) -> None:
    """Set a value in a nested dict using a tuple of keys."""
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value
