#!/usr/bin/env python3
"""[Script] Deterministic formatter for timesheet entries matching Section 3.2 requirements."""

import argparse
import json
import re
import sys


def extract_topic_items(topic_summary: str) -> list:
    """Extract distinct topic items from a topic summary string."""
    raw_topic = (topic_summary or "").strip()
    raw_topic = re.sub(r"^PRs:\s*[^|]+\|\s*", "", raw_topic).strip()
    raw_topic = re.sub(r"\s*\|\s*PRs:.*$", "", raw_topic).strip()
    raw_topic = re.sub(r"\s*\|\s*Commits:.*$", "", raw_topic, flags=re.DOTALL).strip()

    if not raw_topic:
        return []

    items = []
    lines = [l.strip() for l in raw_topic.splitlines() if l.strip()]
    if len(lines) > 1:
        for l in lines:
            clean_l = re.sub(r"^[-*•]\s*", "", l).strip()
            clean_l = re.sub(r"^(?:and|&)\s+", "", clean_l, flags=re.IGNORECASE).strip()
            if clean_l and not clean_l.startswith("PRs:") and not clean_l.startswith("Commits:"):
                clean_l = clean_l[0].upper() + clean_l[1:]
                if clean_l not in items:
                    items.append(clean_l)
    else:
        if "; " in raw_topic:
            raw_parts = [p.strip() for p in raw_topic.split("; ") if p.strip()]
        elif " | " in raw_topic:
            raw_parts = [p.strip() for p in raw_topic.split(" | ") if p.strip()]
        elif ", and " in raw_topic:
            prefix, last = raw_topic.rsplit(", and ", 1)
            raw_parts = [p.strip() for p in prefix.split(", ") if p.strip()] + [last.strip()]
        else:
            raw_parts = [raw_topic]

        for p in raw_parts:
            clean_p = re.sub(r"^[-*•]\s*", "", p).strip()
            clean_p = re.sub(r"^(?:and|&)\s+", "", clean_p, flags=re.IGNORECASE).strip()
            if clean_p and not clean_p.startswith("PRs:") and not clean_p.startswith("Commits:"):
                clean_p = clean_p[0].upper() + clean_p[1:]
                if clean_p not in items:
                    items.append(clean_p)
    return items


def format_description(topic_summary: str, prs: list = None) -> list:
    """Format description lines with PRs and topic on the first line, conditionally bulleting additional items.

    Rules:
    - If concise / single topic (len(items) <= 1):
      - With PRs: - **Description:** PRs: #... | <Topic>
      - Without PRs: - **Description:** <Topic>
    - If multiple items / too long (len(items) > 1):
      - First line: - **Description:** PRs: #... | <Topic 1> (or - **Description:** <Topic 1> if no PRs)
      - Subsequent items formatted as indented bullets:
        - <Topic 2>
        - <Topic 3>
    """
    clean_prs = [p.strip() for p in (prs or []) if p.strip()]
    if not clean_prs and topic_summary:
        m = re.match(r"^PRs:\s*([^|]+)\|?", topic_summary.strip())
        if m:
            clean_prs = [p.strip() for p in m.group(1).split(",") if p.strip()]

    pr_prefix = f"PRs: {', '.join(clean_prs)}" if clean_prs else ""

    items = extract_topic_items(topic_summary)
    if not items:
        first_topic = "Engineering Work"
        sub_items = []
    else:
        first_topic = items[0]
        sub_items = items[1:]

    if pr_prefix and first_topic:
        first_line = f"- **Description:** {pr_prefix} | {first_topic}"
    elif pr_prefix:
        first_line = f"- **Description:** {pr_prefix}"
    else:
        first_line = f"- **Description:** {first_topic}"

    lines = [first_line]
    for sub in sub_items:
        lines.append(f"  - {sub}")

    return lines


def build_bullet_description(
    topic_summary: str,
    prs: list = None,
    commits: list = None,
    reviews: list = None,
    comments: list = None
) -> list:
    """Build bullet points for description when bulleted list is required."""
    bullets = []
    clean_prs = [p.strip() for p in (prs or []) if p.strip()]
    if clean_prs:
        bullets.append(f"PRs: {', '.join(clean_prs)}")

    items = extract_topic_items(topic_summary)
    for it in items:
        if it not in bullets:
            bullets.append(it)

    if commits:
        clean_commits = [c.strip() for c in commits if c.strip()]
        if clean_commits:
            bullets.append(f"Commits: {'; '.join(clean_commits)}")
    if reviews:
        clean_reviews = [r.strip() for r in reviews if r.strip()]
        if clean_reviews:
            bullets.append(f"Reviews: {'; '.join(clean_reviews)}")
    if comments:
        clean_comments = [c.strip() for c in comments if c.strip()]
        if clean_comments:
            bullets.append(f"Comments: {'; '.join(clean_comments)}")

    return bullets


def format_single_entry(
    date: str,
    start_time: str,
    end_time: str,
    topic_summary: str,
    prs: list = None,
    source_title: str = "",
    repos: list = None,
    commit_subjects: list = None,
    reviews: list = None,
    comments: list = None
) -> str:
    """Format a single timesheet block entry into standard markdown."""
    prs = prs or []
    repos = repos or []
    commit_subjects = commit_subjects or []
    reviews = reviews or []
    comments = comments or []

    desc_lines = format_description(topic_summary, prs)

    first_sentence = (topic_summary or "Engineering Work").split('\n')[0].split('.')[0].strip()
    first_sentence = re.sub(r"^PRs:\s*[^|]+\|\s*", "", first_sentence).strip()
    if len(first_sentence) > 65:
        header_title = first_sentence[:62].rsplit(" ", 1)[0] + "..."
    else:
        header_title = first_sentence or "Engineering Work"

    source_trace_lines = [
        "- **Source Trace:**",
        f"  - *Calendar / Activity:* {source_title or 'General Work Block'}",
        f"  - *Repos:* {', '.join(repos) if repos else 'N/A'}",
        f"  - *Commits:* {'; '.join(commit_subjects) if commit_subjects else 'None'}",
    ]
    if reviews:
        clean_reviews = [r.strip() for r in reviews if r.strip()]
        if clean_reviews:
            source_trace_lines.append(f"  - *Reviews:* {'; '.join(clean_reviews)}")
    if comments:
        clean_comments = [c.strip() for c in comments if c.strip()]
        if clean_comments:
            source_trace_lines.append(f"  - *Comments:* {'; '.join(clean_comments)}")

    lines = [
        f"### {date} | {start_time} - {end_time} | {header_title}",
        "",
        f"- **Date:** {date}",
        f"- **Start time:** {start_time}",
        f"- **End time:** {end_time}",
    ] + desc_lines + source_trace_lines + [""]
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
            commit_subjects=data.get("commit_subjects", []),
            reviews=data.get("reviews", []),
            comments=data.get("comments", [])
        )
        print(entry_md)


if __name__ == "__main__":
    main()
