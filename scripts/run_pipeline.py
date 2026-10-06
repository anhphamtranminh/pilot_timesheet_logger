#!/usr/bin/env python3
"""[Script] Master pipeline orchestrator for the Personal Pilot Timesheet Logger."""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

# Add parent directory to sys.path to import modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_prompt import generate_ai_payload
from format_entry import format_single_entry
from save_entry import save_or_update_block_entry
from track_tokens import record_token_run


def fallback_topic_grouping(commit_subjects: list, calendar_title: str) -> str:
    """Deterministic fallback topic summary if running entirely script-only."""
    if not commit_subjects:
        return f"{calendar_title} and general engineering activities"

    clean_items = []
    for s in commit_subjects:
        cleaned = s
        for prefix in ["feat:", "fix:", "chore:", "docs:", "refactor:", "test:", "style:"]:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        clean_items.append(cleaned)

    distinct = list(dict.fromkeys(clean_items))
    if len(distinct) == 1:
        return distinct[0].capitalize()
    elif len(distinct) <= 3:
        return ", ".join(distinct[:-1]) + f", and {distinct[-1]}"
    else:
        return ", ".join(distinct[:3]) + f", and {len(distinct) - 3} other tasks"


def run_daily_timesheet(target_date: str, dry_run: bool = False) -> list:
    """Run timesheet generation pipeline for target_date."""
    payload = generate_ai_payload(target_date)
    blocks = payload.get("blocks", [])
    formatted_entries = []

    print(f"\n[INFO] Processing Timesheet for {target_date}...")
    print(f"[INFO] Found {len(blocks)} time block(s). Estimated AI prompt tokens: {payload['estimated_input_tokens']}\n")

    for b in blocks:
        commits = b.get("commit_subjects", [])
        prs = b.get("prs", [])
        cal_title = b.get("title", "Work Block")

        topic_summary = fallback_topic_grouping(commits, cal_title)

        entry_dict = {
            "date": target_date,
            "start_time": b.get("start_time", "09:00"),
            "end_time": b.get("end_time", "12:00"),
            "topic_summary": topic_summary,
            "prs": prs,
            "source_title": cal_title,
            "repos": b.get("repos", []),
            "commit_subjects": commits
        }

        formatted_entries.append(entry_dict)

        if not dry_run:
            save_or_update_block_entry(entry_dict)
        else:
            print("--- DRY RUN ENTRY ---")
            print(format_single_entry(
                date=entry_dict["date"],
                start_time=entry_dict["start_time"],
                end_time=entry_dict["end_time"],
                topic_summary=entry_dict["topic_summary"],
                prs=entry_dict["prs"],
                source_title=entry_dict["source_title"],
                repos=entry_dict["repos"],
                commit_subjects=entry_dict["commit_subjects"]
            ))

    return formatted_entries


def main():
    parser = argparse.ArgumentParser(description="Run timesheet logger pipeline.")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Target date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Print entries without saving to file")
    args = parser.parse_args()

    run_daily_timesheet(args.date, args.dry_run)


if __name__ == "__main__":
    main()
