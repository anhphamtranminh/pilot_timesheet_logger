#!/usr/bin/env python3
"""Configuration loader for personal pilot timesheet logger."""

import json
import os
import sys
from pathlib import Path

DEFAULT_CONFIG = {
    "user": {
        "name": "Anh Pham",
        "git_author": "Anh Pham",
        "github_username": "anhphamtranminh"
    },
    "repos": [
        "."
    ],
    "calendar": {
        "provider": "ics",
        "ics_path_or_url": "",
        "default_blocks": [
            {"title": "Morning Work Block", "start": "09:00", "end": "12:00"},
            {"title": "Afternoon Work Block", "start": "13:30", "end": "18:00"}
        ]
    },
    "logging": {
        "log_dir": "logs",
        "token_file": "logs/token_usage.csv",
        "improvement_file": "logs/improvement_log.md"
    }
}


def find_project_root() -> Path:
    """Find the root directory of the pilot_timesheet project."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "assignment-1-personal-pilot-timesheet.md").exists() or (current / "config.json").exists():
            return current
        current = current.parent
    return Path.cwd()


def load_config() -> dict:
    """Load configuration from config.json or fall back to defaults."""
    root = find_project_root()
    config_path = root / "config.json"
    config = dict(DEFAULT_CONFIG)

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                for key, val in user_config.items():
                    if isinstance(val, dict) and key in config:
                        config[key].update(val)
                    else:
                        config[key] = val
        except Exception as e:
            print(f"[WARN] Error reading config.json: {e}", file=sys.stderr)

    return config


if __name__ == "__main__":
    print(json.dumps(load_config(), indent=2))
