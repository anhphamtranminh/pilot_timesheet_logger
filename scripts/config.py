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

    local_config_path = root / "config.local.json"
    if local_config_path.exists():
        try:
            with open(local_config_path, "r", encoding="utf-8") as f:
                local_cfg = json.load(f)
                for key, val in local_cfg.items():
                    if isinstance(val, dict) and key in config:
                        config[key].update(val)
                    else:
                        config[key] = val
        except Exception as e:
            print(f"[WARN] Error reading config.local.json: {e}", file=sys.stderr)

    env_cal_url = os.environ.get("CALENDAR_ICS_URL", "").strip()
    if env_cal_url:
        config.setdefault("calendar", {})["ics_path_or_url"] = env_cal_url

    return config

def resolve_target_date(date_str: str = None) -> str:
    """Normalize date argument, supporting YYYY-MM-DD, 'yesterday', 'today', time inputs, or default today."""
    import datetime
    import re
    if isinstance(date_str, (list, tuple)):
        date_str = " ".join(str(x) for x in date_str)
    if not date_str or not str(date_str).strip() or str(date_str).strip().lower() in ("today", "now"):
        return datetime.date.today().isoformat()
    clean = str(date_str).strip().lower()
    if clean == "yesterday":
        return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    m_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", clean)
    if m_iso:
        return m_iso.group(1)
    if "yesterday" in clean:
        return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if "today" in clean:
        return datetime.date.today().isoformat()
    # If the string contains time patterns (e.g. 14:30, 14h30, 14h) but no date, default to today
    if re.search(r"\b[0-2]?\d(?::[0-5]\d|[hH][0-5]\d?|[hH])\b", clean):
        return datetime.date.today().isoformat()
    return str(date_str).strip()


def extract_time_args(args_list: list = None, full_cmd_str: str = None) -> tuple:
    """Extract (start_time, end_time) from CLI positional args, flags, or command string."""
    import re

    start_time = None
    end_time = None

    if full_cmd_str is None and args_list:
        if isinstance(args_list, (list, tuple)):
            full_cmd_str = " ".join(str(a) for a in args_list)
        else:
            full_cmd_str = str(args_list)
    elif full_cmd_str is None:
        full_cmd_str = ""

    # 1. Range pattern: e.g. "14:30-18:00", "14:30 - 18:00", "14h30 to 18h00"
    m_range = re.search(
        r"\b([0-2]?\d(?::[0-5]\d|[hH][0-5]\d|[hH]))\s*(?:-|to)\s*([0-2]?\d(?::[0-5]\d|[hH][0-5]\d|[hH]))\b",
        full_cmd_str,
        re.IGNORECASE
    )
    if m_range:
        start_time = m_range.group(1)
        end_time = m_range.group(2)
        return start_time, end_time

    # 2. Natural language prefixes: "at 14:30", "from 14:30", "went to work at 14h30"
    m_start = re.search(
        r"(?:start(?:ed|ing)?|from|at|went to work at|arrived at)\s+([0-2]?\d(?:[:hH][0-5]\d|h|\b))",
        full_cmd_str,
        re.IGNORECASE
    )
    if m_start:
        start_time = m_start.group(1)

    m_end = re.search(
        r"(?:end(?:ed|ing)?|until|to|leave at|left at)\s+([0-2]?\d(?:[:hH][0-5]\d|h|\b))",
        full_cmd_str,
        re.IGNORECASE
    )
    if m_end:
        end_time = m_end.group(1)

    # 3. Check isolated positional tokens if start_time not set by prefix
    if args_list:
        raw_items = args_list if isinstance(args_list, (list, tuple)) else str(args_list).split()
        time_tokens = []
        for item in raw_items:
            s = str(item).strip()
            if s.startswith("-"):
                continue
            # Check for range inside a token: 14:30-18:00
            m_tok_range = re.match(
                r"^([0-2]?\d(?::[0-5]\d|[hH][0-5]\d|[hH]))\s*(?:-|to)\s*([0-2]?\d(?::[0-5]\d|[hH][0-5]\d|[hH]))$",
                s,
                re.IGNORECASE
            )
            if m_tok_range:
                return m_tok_range.group(1), m_tok_range.group(2)
            # Check single time token: e.g. 14:30, 14h30, 14h
            if re.match(r"^[0-2]?\d(?::[0-5]\d|[hH][0-5]\d|[hH])$", s):
                time_tokens.append(s)

        if time_tokens:
            if not start_time:
                start_time = time_tokens[0]
            if not end_time and len(time_tokens) > 1:
                end_time = time_tokens[1]

    return start_time, end_time


if __name__ == "__main__":
    print(json.dumps(load_config(), indent=2))
