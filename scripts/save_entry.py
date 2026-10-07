#!/usr/bin/env python3
"""[Script] Deterministic saver that persists timesheet entries into monthly log files with deduplication."""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# Add parent directory to sys.path to import modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import find_project_root, load_config
from format_entry import format_single_entry


def get_monthly_log_path(date_str: str) -> Path:
    """Get path to the monthly timesheet log file (e.g., logs/timesheet_2026-10.md)."""
    root = find_project_root()
    config = load_config()
    log_dir_name = config.get("logging", {}).get("log_dir", "logs")
    log_dir = root / log_dir_name
    log_dir.mkdir(parents=True, exist_ok=True)

    month_str = date_str[:7] if len(date_str) >= 7 else datetime.date.today().strftime("%Y-%m")
    return log_dir / f"timesheet_{month_str}.md"


def init_log_file_if_missing(file_path: Path, month_str: str):
    """Initialize a monthly log file with table of contents and instructions."""
    if not file_path.exists():
        header = f"""# Pilot Timesheet Log — {month_str}

**Intern:** Anh Pham  
**Repository:** pilot_timesheet  
**Format:** Section 3.2 compliant (One entry per time block, grouped by topic, inline PRs, source trace)

---

## Daily Entries

"""
        file_path.write_text(header, encoding="utf-8")


def save_or_update_block_entry(entry_dict: dict, custom_log_path: Path = None) -> bool:
    """Save or update a timesheet block entry, preventing duplicate time blocks."""
    date_str = entry_dict.get("date", datetime.date.today().isoformat())
    start_time = entry_dict.get("start_time", "09:00")
    end_time = entry_dict.get("end_time", "12:00")
    month_str = date_str[:7]

    log_path = custom_log_path if custom_log_path else get_monthly_log_path(date_str)
    init_log_file_if_missing(log_path, month_str)

    content = log_path.read_text(encoding="utf-8")

    entry_md = format_single_entry(
        date=date_str,
        start_time=start_time,
        end_time=end_time,
        topic_summary=entry_dict.get("topic_summary", ""),
        prs=entry_dict.get("prs", []),
        source_title=entry_dict.get("source_title", ""),
        repos=entry_dict.get("repos", []),
        commit_subjects=entry_dict.get("commit_subjects", [])
    )

    pattern = re.compile(
        rf"(### {re.escape(date_str)} \| {re.escape(start_time)} - {re.escape(end_time)} \|[^\n]*\n(?:(?!\n### ).)*)",
        re.DOTALL
    )

    if pattern.search(content):
        updated_content = pattern.sub(entry_md.strip(), content)
        log_path.write_text(updated_content, encoding="utf-8")
        print(f"[OK] Updated existing entry for {date_str} ({start_time} - {end_time}) in {log_path.name}")
    else:
        if not content.endswith("\n\n"):
            content += "\n"
        content += entry_md.strip() + "\n\n"
        log_path.write_text(content, encoding="utf-8")
        print(f"[OK] Appended new entry for {date_str} ({start_time} - {end_time}) in {log_path.name}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Save timesheet entry.")
    parser.add_argument("--json-file", help="Path to JSON file containing entry or list of entries")
    parser.add_argument("--json-input", help="JSON string or '-' for stdin containing entry or list of entries")
    args = parser.parse_args()

    data = None
    if args.json_input:
        raw = sys.stdin.read() if args.json_input == "-" else args.json_input
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON input: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.json_file:
        p = Path(args.json_file)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"[ERROR] Failed to parse JSON file: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"[ERROR] File not found: {args.json_file}", file=sys.stderr)
            sys.exit(1)

    if data:
        if isinstance(data, list):
            for item in data:
                save_or_update_block_entry(item)
        elif isinstance(data, dict):
            save_or_update_block_entry(data)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
