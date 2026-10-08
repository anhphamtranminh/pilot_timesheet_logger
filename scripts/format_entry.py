#!/usr/bin/env python3
"""[Script] Deterministic formatter for timesheet entries matching Section 3.2 requirements."""

import argparse
import json
import sys


import re


def build_bullet_description(topic_summary: str, prs: list = None, commits: list = None) -> list:
    """Build bullet points for description: PRs first, followed by topic bullets, and commits."""
    bullets = []
    if prs:
        clean_prs = [p.strip() for p in prs if p.strip()]
        if clean_prs:
            bullets.append(f"PRs: {', '.join(clean_prs)}")

    raw_topic = (topic_summary or "").strip()
    raw_topic = re.sub(r"^PRs:\s*[^|]+\|\s*", "", raw_topic).strip()
    raw_topic = re.sub(r"\s*\|\s*PRs:.*$", "", raw_topic).strip()
    raw_topic = re.sub(r"\s*\|\s*Commits:.*$", "", raw_topic, flags=re.DOTALL).strip()

    if raw_topic:
        lines = [l.strip() for l in raw_topic.splitlines() if l.strip()]
        if len(lines) > 1:
            for l in lines:
                clean_l = re.sub(r"^[-*•]\s*", "", l).strip()
                clean_l = re.sub(r"^(?:and|&)\s+", "", clean_l, flags=re.IGNORECASE).strip()
                if clean_l and not clean_l.startswith("PRs:") and not clean_l.startswith("Commits:"):
                    clean_l = clean_l[0].upper() + clean_l[1:]
                    if clean_l not in bullets:
                        bullets.append(clean_l)
        else:
            if "; " in raw_topic:
                items = [p.strip() for p in raw_topic.split("; ") if p.strip()]
            elif ", and " in raw_topic:
                prefix, last = raw_topic.rsplit(", and ", 1)
                items = [p.strip() for p in prefix.split(", ") if p.strip()] + [last.strip()]
            else:
                items = [raw_topic]

            for item in items:
                clean_item = re.sub(r"^[-*•]\s*", "", item).strip()
                clean_item = re.sub(r"^(?:and|&)\s+", "", clean_item, flags=re.IGNORECASE).strip()
                if clean_item and not clean_item.startswith("PRs:") and not clean_item.startswith("Commits:"):
                    clean_item = clean_item[0].upper() + clean_item[1:]
                    if clean_item not in bullets:
                        bullets.append(clean_item)

    if commits:
        clean_commits = [c.strip() for c in commits if c.strip()]
        if clean_commits:
            bullets.append(f"Commits: {'; '.join(clean_commits)}")

    return bullets


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

    bullets = build_bullet_description(topic_summary, prs)

    first_sentence = (topic_summary or "Engineering Work").split('\n')[0].split('.')[0].strip()
    first_sentence = re.sub(r"^PRs:\s*[^|]+\|\s*", "", first_sentence).strip()
    if len(first_sentence) > 65:
        header_title = first_sentence[:62].rsplit(" ", 1)[0] + "..."
    else:
        header_title = first_sentence or "Engineering Work"

    desc_lines = []
    if len(bullets) == 1 and not prs:
        desc_lines.append(f"- **Description:** {bullets[0]}")
    else:
        desc_lines.append("- **Description:**")
        for b in bullets:
            desc_lines.append(f"  - {b}")

    lines = [
        f"### {date} | {start_time} - {end_time} | {header_title}",
        "",
        f"- **Date:** {date}",
        f"- **Start time:** {start_time}",
        f"- **End time:** {end_time}",
    ] + desc_lines + [
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
