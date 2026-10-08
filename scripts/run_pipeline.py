#!/usr/bin/env python3
"""[Script] Master pipeline orchestrator for the Personal Pilot Timesheet Logger."""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

# Add parent directory to sys.path to import modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_prompt import generate_ai_payload
from format_entry import format_single_entry
from save_entry import save_or_update_block_entry
from track_tokens import record_token_run
from config import resolve_target_date


def fallback_topic_grouping(commit_subjects: list, calendar_title: str, prs: list = None) -> str:
    """Deterministic fallback topic summary if running entirely script-only."""
    MEETING_KEYWORDS = [
        "meeting", "standup", "1:1", "catch-up", "q&a",
        "demo", "retro", "interview", "lunch", "kickoff", "discussion"
    ]
    title_lower = calendar_title.lower()
    is_meeting = any(k in title_lower for k in MEETING_KEYWORDS)
    if "sync" in title_lower and not re.search(r"\bsync\s+(?:all\b|workspace\b|branches?\b|to\b|from\b|data\b|code\b|files?\b|commits?\b|prs?\b|timesheet\b|app\b)", title_lower):
        is_meeting = True

    if not commit_subjects:
        clean_title = calendar_title
        while clean_title.lower().endswith("and general engineering activities"):
            clean_title = clean_title[:-len("and general engineering activities")].strip()
        if is_meeting:
            return clean_title
        if prs:
            formatted_prs = [p if str(p).startswith("#") else f"#{p}" for p in prs]
            return f"Problem investigation and task development for {', '.join(formatted_prs)}"
        return f"{clean_title} and general engineering activities"

    clean_items = []
    for s in commit_subjects:
        cleaned = s
        cleaned = re.sub(r"^(?:feat|fix|docs|chore|refactor|test|style|perf|build|ci)(?:\([^)]+\))?:\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s*\((?:fixes|closes|refs)?\s*#\d+\)", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s*\(#\d+\)", "", cleaned).strip()
        if len(cleaned) > 80:
            cleaned = cleaned[:77].rsplit(" ", 1)[0] + "..."
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
            clean_items.append(cleaned)

    distinct = list(dict.fromkeys(clean_items))
    if len(distinct) == 1:
        commit_summary = distinct[0]
    elif len(distinct) == 2:
        commit_summary = f"{distinct[0]}, and {distinct[1]}"
    elif len(distinct) == 3:
        commit_summary = f"{distinct[0]}, {distinct[1]}, and {distinct[2]}"
    else:
        commit_summary = f"{distinct[0]}, {distinct[1]}, and {len(distinct) - 2} other tasks"

    if is_meeting:
        return f"{calendar_title}, and {commit_summary}"

    return commit_summary


def run_daily_timesheet(target_date: str, dry_run: bool = False, custom_topics: dict = None, sync_workspace: bool = False) -> list:
    """Run timesheet generation pipeline for target_date."""
    payload = generate_ai_payload(target_date)
    blocks = payload.get("blocks", [])
    formatted_entries = []

    if not blocks:
        print(f"\n[INFO] No work activity or time blocks detected for {target_date} (e.g. leave/absence). Timesheet entry skipped.\n")
        return []

    print(f"\n[INFO] Processing Timesheet for {target_date}...")
    print(f"[INFO] Found {len(blocks)} time block(s). Estimated AI prompt tokens: {payload['estimated_input_tokens']}\n")

    for idx, b in enumerate(blocks):
        commits = b.get("commit_subjects", [])
        prs = b.get("prs", [])
        cal_title = b.get("title", "Work Block")

        block_id_str = str(b.get("block_id", idx + 1))
        if custom_topics and (block_id_str in custom_topics or b.get("block_id") in custom_topics):
            topic_summary = custom_topics.get(block_id_str) or custom_topics.get(b.get("block_id"))
        elif isinstance(custom_topics, list) and idx < len(custom_topics):
            topic_summary = custom_topics[idx]
        else:
            topic_summary = fallback_topic_grouping(commits, cal_title, prs=prs)

        entry_dict = {
            "date": target_date,
            "start_time": b.get("start_time", "09:00"),
            "end_time": b.get("end_time", "12:00"),
            "topic_summary": topic_summary,
            "prs": prs,
            "source_title": cal_title,
            "repos": b.get("repos", []),
            "commit_subjects": commits,
            "reviews": b.get("reviews", []),
            "comments": b.get("comments", [])
        }
        if b.get("entry_id"):
            entry_dict["entry_id"] = b["entry_id"]
        if b.get("project"):
            entry_dict["project"] = b["project"]

        formatted_entries.append(entry_dict)

        if not dry_run:
            save_or_update_block_entry(entry_dict)
            if sync_workspace:
                try:
                    from fetch_workspace_timesheet import post_workspace_timesheet_entry
                    post_workspace_timesheet_entry(entry_dict)
                except Exception as e:
                    print(f"[WARN] Gradion Workspace sync error: {e}", file=sys.stderr)
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
                commit_subjects=entry_dict["commit_subjects"],
                reviews=entry_dict["reviews"],
                comments=entry_dict["comments"]
            ))

    return formatted_entries


def main():
    parser = argparse.ArgumentParser(description="Run timesheet logger pipeline.")
    parser.add_argument("date_pos", nargs="?", default=None, help="Target date YYYY-MM-DD or 'yesterday' (optional positional argument)")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD or 'yesterday'")
    parser.add_argument("--dry-run", action="store_true", help="Print entries without saving to file")
    parser.add_argument("--topics-json", help="JSON object {block_id: topic_string} or list of topic strings synthesized by AI")
    parser.add_argument("--sync-workspace", action="store_true", help="Sync entry to Gradion Workspace Timesheet app")
    args = parser.parse_args()

    raw_date = args.date or args.date_pos
    target_date = resolve_target_date(raw_date)

    custom_topics = None
    if args.topics_json:
        try:
            custom_topics = json.loads(args.topics_json)
        except json.JSONDecodeError as e:
            print(f"[WARN] Failed to parse --topics-json: {e}. Using fallback grouping.", file=sys.stderr)

    run_daily_timesheet(target_date, args.dry_run, custom_topics, args.sync_workspace)


if __name__ == "__main__":
    main()
