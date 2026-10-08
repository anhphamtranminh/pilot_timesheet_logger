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

    # Format with PR and issue numbers at the start of Description
    description = topic_summary.strip()
    if prs:
        pr_str = ", ".join(prs)
        if not description.startswith("PRs:"):
            if " | PRs:" in description:
                description = description.split(" | PRs:")[0].strip()
            description = f"PRs: {pr_str} | {description}" if description else f"PRs: {pr_str}"

    first_sentence = topic_summary.split('.')[0].strip()
    if len(first_sentence) > 65:
        header_title = first_sentence[:62].rsplit(" ", 1)[0] + "..."
    else:
        header_title = first_sentence or "Engineering Work"

    lines = [
        f"### {date} | {start_time} - {end_time} | {header_title}",
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
