#!/usr/bin/env python3
"""[Script] Deterministic token usage tracker as required by Section 3.6."""

import argparse
import csv
import datetime
import json
import os
import sys
from pathlib import Path

# Add parent directory to sys.path to import modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import find_project_root, load_config


def get_token_csv_path() -> Path:
    """Get path to the token usage CSV."""
    root = find_project_root()
    config = load_config()
    token_file = config.get("logging", {}).get("token_file", "logs/token_usage.csv")
    csv_path = root / token_file
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    return csv_path


def init_token_csv_if_missing(csv_path: Path):
    """Initialize token usage CSV with header if missing."""
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "date",
                "session_id",
                "input_tokens",
                "output_tokens",
                "cache_tokens",
                "total_tokens",
                "workflow_version",
                "notes"
            ])


def record_token_run(
    date_str: str,
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_tokens: int = 0,
    workflow_version: str = "v1.0",
    notes: str = ""
):
    """Append a token record to the CSV."""
    csv_path = get_token_csv_path()
    init_token_csv_if_missing(csv_path)

    total_tokens = input_tokens + output_tokens + cache_tokens
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            date_str,
            session_id,
            input_tokens,
            output_tokens,
            cache_tokens,
            total_tokens,
            workflow_version,
            notes
        ])
    print(f"[OK] Recorded {total_tokens} tokens for session {session_id} on {date_str}")


def scan_claude_sessions_for_date(target_date: str) -> list:
    """Scan ~/.claude local logs if available for usage entries."""
    claude_dir = Path.home() / ".claude"
    if not claude_dir.exists():
        return []

    records = []
    for jsonl_file in claude_dir.glob("**/*.jsonl"):
        try:
            mtime = datetime.date.fromtimestamp(jsonl_file.stat().st_mtime).isoformat()
            if mtime != target_date:
                continue

            session_id = jsonl_file.stem
            in_tok = 0
            out_tok = 0
            cache_tok = 0

            with open(jsonl_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if '"usage"' in line:
                        try:
                            obj = json.loads(line)
                            usage = obj.get("usage") or obj.get("message", {}).get("usage", {})
                            in_tok += usage.get("input_tokens", 0)
                            out_tok += usage.get("output_tokens", 0)
                            cache_tok += usage.get("cache_read_input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                        except Exception:
                            pass

            if in_tok + out_tok > 0:
                records.append({
                    "session_id": session_id,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "cache_tokens": cache_tok
                })
        except Exception:
            pass

    return records


def print_daily_summary(target_date: str):
    """Print the daily total token consumption."""
    csv_path = get_token_csv_path()
    if not csv_path.exists():
        print(f"No token records found for {target_date}.")
        return

    total = 0
    runs = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("date") == target_date:
                total += int(row.get("total_tokens", 0))
                runs += 1

    print(f"Token Summary for {target_date}: {total} tokens across {runs} run(s).")


def main():
    parser = argparse.ArgumentParser(description="Track daily token usage.")
    parser.add_argument("--record", action="store_true", help="Record a new run")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Date YYYY-MM-DD")
    parser.add_argument("--session-id", default="", help="Session ID")
    parser.add_argument("--input-tokens", type=int, default=0, help="Input tokens")
    parser.add_argument("--output-tokens", type=int, default=0, help="Output tokens")
    parser.add_argument("--cache-tokens", type=int, default=0, help="Cache tokens")
    parser.add_argument("--version", default="v1.0", help="Workflow version")
    parser.add_argument("--notes", default="", help="Notes or optimization info")
    parser.add_argument("--summary", action="store_true", help="Print daily summary")
    args = parser.parse_args()

    if args.record:
        record_token_run(
            date_str=args.date,
            session_id=args.session_id or f"manual-{int(datetime.datetime.now().timestamp())}",
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            cache_tokens=args.cache_tokens,
            workflow_version=args.version,
            notes=args.notes
        )
    elif args.summary:
        print_daily_summary(args.date)
    else:
        records = scan_claude_sessions_for_date(args.date)
        if records:
            for r in records:
                record_token_run(
                    date_str=args.date,
                    session_id=r["session_id"],
                    input_tokens=r["input_tokens"],
                    output_tokens=r["output_tokens"],
                    cache_tokens=r["cache_tokens"],
                    notes="Auto-scanned session"
                )
        print_daily_summary(args.date)


if __name__ == "__main__":
    main()
