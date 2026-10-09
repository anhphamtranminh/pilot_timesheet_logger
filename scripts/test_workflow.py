#!/usr/bin/env python3
"""[Script] Interactive test runner for the Personal Pilot Timesheet Logger AI workflow.

Runs all 5 steps of the daily timesheet workflow in preview / dry-run mode
so users can inspect data harvesting, prompt payload sizing, topic synthesis,
standard markdown formatting, and token consumption without modifying files.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

# Add parent directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_prompt import generate_ai_payload
from run_pipeline import fallback_topic_grouping
from format_entry import format_single_entry
from track_tokens import estimate_tokens
from config import resolve_target_date


# ANSI colors for terminal output
BOLD = "\033[1m"
GREEN = "\033[32m"
BLUE = "\033[34m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RESET = "\033[0m"


def print_banner(target_date: str, mode: str):
    print(f"\n{BOLD}{CYAN}{'=' * 78}{RESET}")
    print(f"{BOLD}{CYAN} PILOT TIMESHEET LOGGER -- AI WORKFLOW TEST RUNNER{RESET}")
    print(f"{CYAN}{'=' * 78}{RESET}")
    print(f" Target Date : {BOLD}{target_date}{RESET}")
    print(f" Mode        : {BOLD}{YELLOW if 'DRY-RUN' in mode else GREEN}{mode}{RESET}")
    print(f"{CYAN}{'-' * 78}{RESET}\n")


def run_workflow_test(target_date: str, custom_topics: dict = None, live: bool = False, sync_workspace: bool = False):
    mode_str = "LIVE EXECUTION (Disk & Workspace)" if live else "DRY-RUN SIMULATION (No file or API writes)"
    print_banner(target_date, mode_str)

    # -------------------------------------------------------------
    # Step 1: Data Harvesting
    # -------------------------------------------------------------
    print(f"{BOLD}{BLUE}[Step 1/5] Extracting Data (Git, GitHub PRs, Calendar/Workspace)...{RESET}")
    payload = generate_ai_payload(target_date)
    blocks = payload.get("blocks", [])

    print(f"  • Found {BOLD}{len(blocks)}{RESET} time block(s).")
    for b in blocks:
        commits = b.get("commit_subjects", [])
        prs = b.get("prs", [])
        print(f"    - [{b.get('start_time')} - {b.get('end_time')}] {b.get('title')}")
        if commits:
            print(f"      Commits ({len(commits)}): {commits[0]}" + (f" (+{len(commits)-1} more)" if len(commits) > 1 else ""))
        if prs:
            print(f"      PRs: {', '.join(prs)}")
        issues = b.get("issues", [])
        if issues:
            print(f"      Issues: {', '.join(issues)}")
        reviews = b.get("reviews", [])
        comments = b.get("comments", [])
        discussions = b.get("discussions", [])
        if reviews:
            print(f"      Reviews ({len(reviews)}): {reviews[0]}" + (f" (+{len(reviews)-1} more)" if len(reviews) > 1 else ""))
        if discussions:
            print(f"      Discussions ({len(discussions)}): {discussions[0]}" + (f" (+{len(discussions)-1} more)" if len(discussions) > 1 else ""))
        elif comments:
            print(f"      Comments ({len(comments)}): {comments[0]}" + (f" (+{len(comments)-1} more)" if len(comments) > 1 else ""))
    print()

    # -------------------------------------------------------------
    # Step 2: AI Input Payload Inspection
    # -------------------------------------------------------------
    ai_input = payload.get("ai_input", [])
    estimated_input_tokens = payload.get("estimated_input_tokens", 0)
    print(f"{BOLD}{BLUE}[Step 2/5] Minimal AI Input Payload (Token Compressed)...{RESET}")
    print(f"  • Estimated Prompt Tokens: {BOLD}{estimated_input_tokens}{RESET} tokens (Budget Target: < 200 input)")
    print(f"  • Exact JSON passed to AI model:")
    print(f"{CYAN}{json.dumps(ai_input, indent=4)}{RESET}\n")

    # -------------------------------------------------------------
    # Step 3: AI Topic Synthesis
    # -------------------------------------------------------------
    print(f"{BOLD}{BLUE}[Step 3/5] AI Topic Synthesis (Judgment Step)...{RESET}")
    all_day_repos = set()
    for b in blocks:
        for r in b.get("repos", []):
            if r:
                all_day_repos.add(r)
    is_multi_project = (len(all_day_repos) > 1) or any(r not in ("pilot_timesheet", "pilot_timesheet_logger") for r in all_day_repos)

    synthesized_topics = {}
    for idx, b in enumerate(blocks):
        b_id = str(b.get("block_id", idx + 1))
        commits = b.get("commit_subjects", [])
        cal_title = b.get("title", "Daily Development")

        if custom_topics and (b_id in custom_topics or b.get("block_id") in custom_topics):
            topic = custom_topics.get(b_id) or custom_topics.get(b.get("block_id"))
        else:
            topic = fallback_topic_grouping(commits, cal_title, prs=b.get("prs", []), issues=b.get("issues", []), issue_objs=b.get("issue_objs", []))

        synthesized_topics[b_id] = topic
        print(f"  • Block {b_id} ({b.get('start_time')} - {b.get('end_time')}):")
        print(f"    {BOLD}{GREEN}\"{topic}\"{RESET}")
    print()

    # -------------------------------------------------------------
    # Step 4: Markdown Formatting Compliance
    # -------------------------------------------------------------
    print(f"{BOLD}{BLUE}[Step 4/5] Formatting Standard Markdown Entries...{RESET}")
    formatted_entries = []
    for idx, b in enumerate(blocks):
        b_id = str(b.get("block_id", idx + 1))
        topic = synthesized_topics[b_id]
        block_project = ""
        b_proj = b.get("project", "")
        if b_proj and not any(k in b_proj for k in ["Gradion Intern Academy", "Internal Project"]):
            block_project = b_proj
        elif is_multi_project:
            block_repos = b.get("repos", [])
            if block_repos:
                block_project = ", ".join(sorted(block_repos))

        md = format_single_entry(
            date=target_date,
            start_time=b.get("start_time", "09:00"),
            end_time=b.get("end_time", "12:00"),
            topic_summary=topic,
            prs=b.get("prs", []),
            issues=b.get("issues", []),
            project=block_project,
            source_title=b.get("title", ""),
            repos=b.get("repos", []),
            commit_subjects=b.get("commit_subjects", []),
            reviews=b.get("reviews", []),
            comments=b.get("comments", []),
            discussions=b.get("discussions", [])
        )
        formatted_entries.append(md)

    print(f"{YELLOW}--- MARKDOWN PREVIEW (What gets saved to logs/timesheet_YYYY-MM.md) ---{RESET}")
    for md in formatted_entries:
        print(md)
    print(f"{YELLOW}------------------------------------------------------------------------{RESET}\n")

    # -------------------------------------------------------------
    # Step 5: Token Tracking & Budget Compliance
    # -------------------------------------------------------------
    topics_json_str = json.dumps(synthesized_topics)
    estimated_output_tokens = estimate_tokens(topics_json_str) + 30
    total_tokens = estimated_input_tokens + estimated_output_tokens
    budget_limit = 350
    pct = (total_tokens / budget_limit) * 100.0
    status_tag = f"{GREEN}[PASS]{RESET}" if total_tokens <= budget_limit else f"{YELLOW}[OPTIMIZE]{RESET}"

    print(f"{BOLD}{BLUE}[Step 5/5] Token Budget & Performance Metrics...{RESET}")
    print(f"  • Input Tokens  : {estimated_input_tokens}")
    print(f"  • Output Tokens : {estimated_output_tokens}")
    print(f"  • Total Tokens  : {BOLD}{total_tokens}{RESET} / {budget_limit} ({pct:.1f}%) {status_tag}")
    print()

    # -------------------------------------------------------------
    # Execution Summary
    # -------------------------------------------------------------
    print(f"{BOLD}{CYAN}{'=' * 78}{RESET}")
    if not live:
        print(f" {GREEN}[OK] Dry run completed successfully. No changes were written to disk or API.{RESET}")
        print(f" To execute this live, run:")
        print(f"   {BOLD}python3 scripts/run_pipeline.py --date {target_date} --sync-workspace{RESET}")
        print(f" Or simply type {BOLD}'log'{RESET} in Antigravity.")
    else:
        from run_pipeline import run_daily_timesheet
        print(f" {GREEN}Executing live timesheet persistence...{RESET}")
        run_daily_timesheet(target_date, dry_run=False, custom_topics=synthesized_topics, sync_workspace=sync_workspace)
        print(f" {GREEN}[OK] Timesheet saved and synced successfully.{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 78}{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Test and visualize the AI timesheet logging workflow.")
    parser.add_argument("date_pos", nargs="?", default=None, help="Target date YYYY-MM-DD or 'yesterday' (optional positional argument)")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD or 'yesterday'")
    parser.add_argument("--live", action="store_true", help="Perform live save to markdown and sync to Workspace")
    parser.add_argument("--sync-workspace", action="store_true", help="Sync to Gradion Workspace (if --live is enabled)")
    parser.add_argument("--topics-json", help="Optional JSON string of custom topic summaries")
    args = parser.parse_args()

    raw_date = args.date or args.date_pos
    target_date = resolve_target_date(raw_date)

    custom_topics = None
    if args.topics_json:
        try:
            custom_topics = json.loads(args.topics_json)
        except json.JSONDecodeError as e:
            print(f"[WARN] Failed to parse custom topics: {e}", file=sys.stderr)

    run_workflow_test(target_date, custom_topics=custom_topics, live=args.live, sync_workspace=args.sync_workspace)


if __name__ == "__main__":
    main()
