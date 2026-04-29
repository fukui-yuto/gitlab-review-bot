"""
Start review-bot locally for testing.
Loads .env.test if it exists, uses config/settings.test.yaml.

Usage:
    python scripts/start_bot.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env.test
env_file = Path(".env.test")
if env_file.exists():
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    print(f"Loaded {env_file}")

# Ensure src is on path
sys.path.insert(0, "src")

# Override config path
os.environ.setdefault("REVIEW_BOT_CONFIG", "config/settings.test.yaml")

import uvicorn

# Patch load_settings to use test config
from review_bot.core import config as config_module

_orig_load = config_module.load_settings


def _patched_load(config_path=None):
    return _orig_load(os.environ.get("REVIEW_BOT_CONFIG", config_path))


config_module.load_settings = _patched_load

from review_bot.main import app  # noqa: E402

if __name__ == "__main__":
    print("Starting review-bot on http://localhost:8080 ...")
    print(f"  LLM_PROVIDER={os.environ.get('LLM_PROVIDER', '(default from yaml)')}")
    print(f"  GITLAB_URL={os.environ.get('GITLAB_URL', '(default)')}")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
