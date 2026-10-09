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
        issues=entry_dict.get("issues", []),
        project=entry_dict.get("project", ""),
        source_title=entry_dict.get("source_title", ""),
        repos=entry_dict.get("repos", []),
        commit_subjects=entry_dict.get("commit_subjects", []),
        reviews=entry_dict.get("reviews", []),
        comments=entry_dict.get("comments", []),
        discussions=entry_dict.get("discussions", [])
    )

    # 1. Exact match on date, start_time, end_time
    exact_pattern = re.compile(
        rf"(### {re.escape(date_str)} \| {re.escape(start_time)} - {re.escape(end_time)} \|[^\n]*\n(?:(?!\n### ).)*)",
        re.DOTALL
    )

    if exact_pattern.search(content):
        updated_content = exact_pattern.sub(entry_md.strip(), content)
        log_path.write_text(updated_content, encoding="utf-8")
        print(f"[OK] Updated existing entry for {date_str} ({start_time} - {end_time}) in {log_path.name}")
        return True

    # 2. Check for overlapping entries for the same date
    def to_min(t_str):
        parts = t_str.split(":")
        return int(parts[0]) * 60 + int(parts[1]) if len(parts) >= 2 else 0

    s_min = to_min(start_time)
    e_min = to_min(end_time)
    current_dur = e_min - s_min

    entry_header_pattern = re.compile(
        rf"(### {re.escape(date_str)} \| (\d{{2}}:\d{{2}}) - (\d{{2}}:\d{{2}}) \|[^\n]*\n(?:(?!\n### ).)*)",
        re.DOTALL
    )

    for match in entry_header_pattern.finditer(content):
        matched_text = match.group(1)
        ex_st = match.group(2)
        ex_et = match.group(3)
        ex_s = to_min(ex_st)
        ex_e = to_min(ex_et)
        ex_dur = ex_e - ex_s

        # If existing is a full-day placeholder (>= 8 hours, e.g. 09:00 - 18:00 Daily Development) and current is discrete sub-block
        if ex_dur >= 480 and current_dur < 480 and ("Daily Development" in matched_text):
            content = content.replace(matched_text.strip(), "").strip()
            if not content.endswith("\n\n"):
                content += "\n\n"
            break

        overlap = min(e_min, ex_e) - max(s_min, ex_s)
        if overlap > 0:
            # If same start time or overlap covers majority of the block
            if ex_st == start_time or (current_dur > 0 and overlap / current_dur >= 0.75):
                content = content.replace(matched_text.strip(), entry_md.strip())
                log_path.write_text(content, encoding="utf-8")
                print(f"[OK] Replaced overlapping entry for {date_str} ({ex_st} - {ex_et} -> {start_time} - {end_time}) in {log_path.name}")
                return True

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
