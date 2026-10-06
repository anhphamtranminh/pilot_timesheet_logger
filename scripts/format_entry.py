#!/usr/bin/env python3
"""[Script] Deterministic formatter for timesheet entries matching Section 3.2 requirements."""

import argparse
import json
import sys


def format_single_entry(
    date: str,
    start_time: str,
    end_time: str,
    topic_summary: str,
    prs: list = None,
    source_title: str = "",
    repos: list = None,
    commit_subjects: list = None
) -> str:
    """Format a single timesheet block entry into standard markdown."""
    prs = prs or []
    repos = repos or []
    commit_subjects = commit_subjects or []

    # Format according to Section 3.2:
    # "Put the grouped topics in Description, and the PRs: list at the end of it."
    description = topic_summary.strip()
    if prs:
        pr_str = ", ".join(prs)
        if "PRs:" not in description:
            description = f"{description} | PRs: {pr_str}"

    lines = [
        f"### {date} | {start_time} - {end_time} | {topic_summary.split('.')[0][:50]}",
        "",
        f"- **Date:** {date}",
        f"- **Start time:** {start_time}",
        f"- **End time:** {end_time}",
        f"- **Description:** {description}",
        "- **Source Trace:**",
        f"  - *Calendar / Activity:* {source_title or 'General Work Block'}",
        f"  - *Repos:* {', '.join(repos) if repos else 'N/A'}",
        f"  - *Commits:* {'; '.join(commit_subjects) if commit_subjects else 'None'}",
        ""
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Format a timesheet entry.")
    parser.add_argument("--json-input", help="JSON string containing entry fields")
    args = parser.parse_args()

    if args.json_input:
        data = json.loads(args.json_input)
        entry_md = format_single_entry(
            date=data.get("date", ""),
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time", ""),
            topic_summary=data.get("topic_summary", ""),
            prs=data.get("prs", []),
            source_title=data.get("source_title", ""),
            repos=data.get("repos", []),
            commit_subjects=data.get("commit_subjects", [])
        )
        print(entry_md)


if __name__ == "__main__":
    main()
