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
from format_entry import format_single_entry, normalize_repo_name
from save_entry import (
    save_or_update_block_entry,
    get_existing_blocked_intervals,
    is_block_already_blocked
)
from track_tokens import record_token_run
from config import resolve_target_date, extract_time_args


def fallback_topic_grouping(commit_subjects: list, calendar_title: str, prs: list = None, issues: list = None, issue_objs: list = None) -> str:
    """Deterministic fallback topic summary if running entirely script-only."""
    MEETING_KEYWORDS = [
        "meeting", "standup", "1:1", "catch-up", "q&a",
        "demo", "retro", "interview", "lunch", "kickoff", "discussion",
        "training", "workshop", "webinar", "seminar", "session",
        "course", "lecture", "orientation", "onboarding", "all-hands",
        "presentation", "ceremony", "townhall", "office hours", "sync",
        "sync-up", "grooming", "planning"
    ]
    title_lower = calendar_title.lower()
    is_meeting = any(re.search(rf"\b{re.escape(k)}\b", title_lower) for k in MEETING_KEYWORDS)
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
        if issue_objs:
            titles = []
            for io in issue_objs:
                t = io.get("title", "").strip()
                if t:
                    t_clean = re.sub(r"^(?:feat|fix|docs|chore|refactor|test|style|perf|build|ci)(?:\([^)]+\))?:\s*", "", t, flags=re.IGNORECASE).strip()
                    if t_clean:
                        t_clean = t_clean[0].upper() + t_clean[1:]
                    titles.append(t_clean or t)
            distinct_titles = list(dict.fromkeys(titles))
            if len(distinct_titles) == 1:
                return distinct_titles[0]
            elif len(distinct_titles) == 2:
                return f"{distinct_titles[0]}, and {distinct_titles[1]}"
            elif len(distinct_titles) > 2:
                return f"{distinct_titles[0]}, {distinct_titles[1]}, and {len(distinct_titles) - 2} other issues"
        if issues:
            formatted_issues = [i if str(i).startswith("#") else f"#{i}" for i in issues]
            return f"Problem investigation and task development for {', '.join(formatted_issues)}"
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


def run_daily_timesheet(
    target_date: str,
    dry_run: bool = False,
    custom_topics: dict = None,
    sync_workspace: bool = False,
    remaining_only: bool = None,
    start_time: str = None,
    end_time: str = None
) -> list:
    """Run timesheet generation pipeline for target_date."""
    payload = generate_ai_payload(target_date, start_time=start_time, end_time=end_time)
    blocks = payload.get("blocks", [])
    formatted_entries = []

    if not blocks:
        print(f"\n[INFO] No work activity or time blocks detected for {target_date} (e.g. leave/absence). Timesheet entry skipped.\n")
        return []

    today_str = datetime.date.today().isoformat()
    if remaining_only is None:
        remaining_only = (target_date == today_str)

    if remaining_only:
        existing_blocked = get_existing_blocked_intervals(target_date)
        if existing_blocked:
            unblocked_blocks = [b for b in blocks if not is_block_already_blocked(b, existing_blocked)]
            blocked_count = len(blocks) - len(unblocked_blocks)
            if blocked_count > 0:
                print(f"[INFO] Detected {blocked_count} already-blocked time block(s) for {target_date} (preserved intact).")
            if not unblocked_blocks:
                print(f"[INFO] All time blocks for {target_date} are already blocked in timesheet and Gradion Workspace.")
                print(f"[INFO] No remaining unblocked time blocks detected. Skipping without making changes.\n")
                return []
            blocks = unblocked_blocks

    print(f"\n[INFO] Processing Timesheet for {target_date}...")
    print(f"[INFO] Found {len(blocks)} time block(s). Estimated AI prompt tokens: {payload['estimated_input_tokens']}\n")

    all_day_repos = set()
    for b in blocks:
        for r in b.get("repos", []):
            if r:
                all_day_repos.add(r)

    is_multi_project = (len(all_day_repos) > 1) or any(r not in ("pilot_timesheet", "pilot_timesheet_logger") for r in all_day_repos)

    saved_count = 0
    unchanged_count = 0

    for idx, b in enumerate(blocks):
        commits = b.get("commit_subjects", [])
        prs = b.get("prs", [])
        issues = b.get("issues", [])
        issue_objs = b.get("issue_objs", [])
        discussions = b.get("discussions", [])
        cal_title = b.get("title", "Work Block")

        block_id_str = str(b.get("block_id", idx + 1))
        if custom_topics and (block_id_str in custom_topics or b.get("block_id") in custom_topics):
            topic_summary = custom_topics.get(block_id_str) or custom_topics.get(b.get("block_id"))
        elif isinstance(custom_topics, list) and idx < len(custom_topics):
            topic_summary = custom_topics[idx]
        else:
            topic_summary = fallback_topic_grouping(commits, cal_title, prs=prs, issues=issues, issue_objs=issue_objs)

        block_project = ""
        b_proj = b.get("project", "")
        block_repos = [normalize_repo_name(r) for r in b.get("repos", []) if r and r != "N/A"]
        if b_proj and not any(k in b_proj for k in ["Gradion Intern Academy", "Internal Project"]):
            block_project = normalize_repo_name(b_proj)
        elif block_repos:
            block_project = ", ".join(sorted(dict.fromkeys(block_repos)))

        entry_dict = {
            "date": target_date,
            "start_time": b.get("start_time", "09:00"),
            "end_time": b.get("end_time", "12:00"),
            "topic_summary": topic_summary,
            "prs": prs,
            "issues": issues,
            "source_title": cal_title,
            "repos": block_repos or b.get("repos", []),
            "commit_subjects": commits,
            "reviews": b.get("reviews", []),
            "comments": b.get("comments", []),
            "discussions": discussions
        }
        if b.get("entry_id"):
            entry_dict["entry_id"] = b["entry_id"]
        if block_project:
            entry_dict["project"] = block_project

        formatted_entries.append(entry_dict)

        if not dry_run:
            changed = save_or_update_block_entry(entry_dict)
            if changed:
                saved_count += 1
            else:
                unchanged_count += 1
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
                issues=entry_dict.get("issues", []),
                project=entry_dict.get("project", ""),
                source_title=entry_dict["source_title"],
                repos=entry_dict["repos"],
                commit_subjects=entry_dict["commit_subjects"],
                reviews=entry_dict["reviews"],
                comments=entry_dict["comments"],
                discussions=entry_dict.get("discussions", [])
            ))

    if not dry_run and blocks:
        print(f"\n[INFO] Timesheet save summary: {saved_count} saved/updated, {unchanged_count} unchanged.")

    return formatted_entries


def main():
    parser = argparse.ArgumentParser(description="Run timesheet logger pipeline.")
    parser.add_argument("date_pos", nargs="*", default=[], help="Target date YYYY-MM-DD, 'yesterday', or time argument(s) like 14:30 (optional positional arguments)")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD or 'yesterday'")
    parser.add_argument("--dry-run", action="store_true", help="Print entries without saving to file")
    parser.add_argument("--topics-json", help="JSON object {block_id: topic_string} or list of topic strings synthesized by AI")
    parser.add_argument("--sync-workspace", action="store_true", help="Sync entry to Gradion Workspace Timesheet app")
    parser.add_argument("--remaining-only", action="store_true", default=None, help="Only process and log remaining unblocked time blocks")
    parser.add_argument("--all", "--reblock-all", dest="reblock_all", action="store_true", help="Reblock and update all time blocks for the day from the beginning")
    parser.add_argument("--start-time", help="Custom workday start time (e.g. 14:30 or 14h30)")
    parser.add_argument("--end-time", help="Custom workday end time (e.g. 18:00 or 18h00)")
    args = parser.parse_args()

    raw_date = args.date or args.date_pos
    target_date = resolve_target_date(raw_date)

    remaining_only = None
    if args.reblock_all:
        remaining_only = False
    elif args.remaining_only:
        remaining_only = True

    start_time = args.start_time
    end_time = args.end_time

    full_cmd_str = " ".join(sys.argv)
    parsed_start, parsed_end = extract_time_args(args.date_pos, full_cmd_str)
    if not start_time:
        start_time = parsed_start
    if not end_time:
        end_time = parsed_end

    custom_topics = None
    if args.topics_json:
        try:
            custom_topics = json.loads(args.topics_json)
        except json.JSONDecodeError as e:
            print(f"[WARN] Failed to parse --topics-json: {e}. Using fallback grouping.", file=sys.stderr)

    extra_kwargs = {}
    if remaining_only is not None:
        extra_kwargs["remaining_only"] = remaining_only
    if start_time is not None:
        extra_kwargs["start_time"] = start_time
    if end_time is not None:
        extra_kwargs["end_time"] = end_time

    run_daily_timesheet(target_date, args.dry_run, custom_topics, args.sync_workspace, **extra_kwargs)


if __name__ == "__main__":
    main()
