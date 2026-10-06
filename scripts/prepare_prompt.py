#!/usr/bin/env python3
"""[Script] Deterministic aggregator that maps commits and PRs into time blocks and prepares a minimal-token payload for [AI]."""

import argparse
import datetime
import json
import sys
from pathlib import Path

# Add parent directory to sys.path to import modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_git import fetch_all_commits
from fetch_prs import fetch_all_prs
from fetch_calendar import fetch_all_events


def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM string to minutes since midnight."""
    parts = time_str.split(":")
    if len(parts) >= 2:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass
    return 0


def assign_items_to_blocks(blocks: list, commits: list, prs: list) -> list:
    """Assign commits and PRs to the time blocks based on timestamps."""
    structured_blocks = []

    for i, b in enumerate(blocks):
        structured_blocks.append({
            "block_id": i + 1,
            "title": b.get("title", "Work Block"),
            "start_time": b.get("start_time", "09:00"),
            "end_time": b.get("end_time", "12:00"),
            "source": b.get("source", "calendar"),
            "commits": [],
            "prs": set(),
            "repos": set()
        })

    if not structured_blocks:
        structured_blocks.append({
            "block_id": 1,
            "title": "Daily Development",
            "start_time": "09:00",
            "end_time": "18:00",
            "source": "fallback",
            "commits": [],
            "prs": set(),
            "repos": set()
        })

    for c in commits:
        c_time = time_to_minutes(c.get("time", "12:00"))
        matched_block = None

        for b in structured_blocks:
            b_start = time_to_minutes(b["start_time"])
            b_end = time_to_minutes(b["end_time"])
            if b_start <= c_time <= b_end:
                matched_block = b
                break

        if not matched_block:
            matched_block = structured_blocks[-1]

        matched_block["commits"].append(c["subject"])
        matched_block["repos"].add(c["repo"])
        for p in c.get("prs", []):
            matched_block["prs"].add(p)

    for p in prs:
        num = p["number"]
        already_attached = any(num in b["prs"] for b in structured_blocks)
        if not already_attached:
            structured_blocks[0]["prs"].add(num)
            if p.get("repo"):
                structured_blocks[0]["repos"].add(p["repo"])

    result = []
    for b in structured_blocks:
        result.append({
            "block_id": b["block_id"],
            "title": b["title"],
            "start_time": b["start_time"],
            "end_time": b["end_time"],
            "repos": sorted(list(b["repos"])),
            "prs": sorted(list(b["prs"])),
            "commit_subjects": b["commits"]
        })

    return result


def generate_ai_payload(target_date: str) -> dict:
    """Prepare the minimal token payload for the [AI] step."""
    commits = fetch_all_commits(target_date)
    prs = fetch_all_prs(target_date)
    events = fetch_all_events(target_date)

    blocks = assign_items_to_blocks(events, commits, prs)

    raw_str = json.dumps(blocks)
    estimated_tokens = max(1, len(raw_str) // 4)

    return {
        "date": target_date,
        "estimated_input_tokens": estimated_tokens,
        "blocks": blocks
    }


def main():
    parser = argparse.ArgumentParser(description="Prepare minimal token payload for AI step.")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Target date YYYY-MM-DD")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    args = parser.parse_args()

    payload = generate_ai_payload(args.date)
    indent = 2 if args.pretty else None
    print(json.dumps(payload, indent=indent))


if __name__ == "__main__":
    main()
