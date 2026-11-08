"""
config_loader.py
Single place that loads Sentry's configuration.

Load order (later wins):
1. <repo root>/config.json        - tracked in git, must NOT contain secrets
2. <repo root>/config.local.json  - git-ignored, put your real secrets here
3. Environment variables:
     SENTRY_LINE_TOKEN      -> notifications.line_channel_access_token
     SENTRY_LINE_USER_ID    -> notifications.line_user_id
     SENTRY_CONTROL_TOKEN   -> security.control_token
     SENTRY_PUBLIC_URL      -> notifications.public_url
"""

import copy
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "config.json")
LOCAL_CONFIG_PATH = os.path.join(REPO_ROOT, "config.local.json")

DEFAULTS = {
    "networking": {
        "udp_receiver_port": 5000,
        "http_port": 8000,
    },
    "ai_settings": {
        "variance_threshold": 2.0,
    },
    "notifications": {
        "line_channel_access_token": "",
        "line_user_id": "",
        "public_url": "https://csi.ohmpatumwan.com",
    },
    "alarm": {
        "enabled": True,
        "udp_port": 5005,
    },
    "security": {
        "control_token": "",
    },
}

ENV_OVERRIDES = {
    "SENTRY_LINE_TOKEN": ("notifications", "line_channel_access_token"),
    "SENTRY_LINE_USER_ID": ("notifications", "line_user_id"),
    "SENTRY_CONTROL_TOKEN": ("security", "control_token"),
    "SENTRY_PUBLIC_URL": ("notifications", "public_url"),
}

PLACEHOLDER_VALUES = {"", "YOUR_CHANNEL_ACCESS_TOKEN", "YOUR_USER_ID"}


def _deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _read_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[CONFIG] Failed to read {path}: {e}", flush=True)
        return {}


def load_config(config_path=CONFIG_PATH, local_path=LOCAL_CONFIG_PATH, environ=None):
    environ = os.environ if environ is None else environ
    cfg = copy.deepcopy(DEFAULTS)
    _deep_merge(cfg, _read_json(config_path))
    _deep_merge(cfg, _read_json(local_path))
    for env_name, (section, key) in ENV_OVERRIDES.items():
        value = environ.get(env_name)
        if value:
            cfg.setdefault(section, {})[key] = value
    return cfg


def is_configured(value):
    return bool(value) and value not in PLACEHOLDER_VALUES


CONFIG = load_config()
