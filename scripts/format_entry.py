#!/usr/bin/env python3
"""[Script] Deterministic formatter for timesheet entries matching Section 3.2 requirements."""

import argparse
import json
import re
import sys


def extract_topic_items(topic_summary: str) -> list:
    """Extract distinct topic items from a topic summary string."""
    raw_topic = (topic_summary or "").strip()
    raw_topic = re.sub(r"^\[[^\]]+\]\s*", "", raw_topic).strip()
    raw_topic = re.sub(r"^PRs:\s*[^|]+\|\s*", "", raw_topic).strip()
    raw_topic = re.sub(r"^Issues:\s*[^|]+\|\s*", "", raw_topic).strip()
    raw_topic = re.sub(r"\s*\|\s*PRs:.*$", "", raw_topic).strip()
    raw_topic = re.sub(r"\s*\|\s*Issues:.*$", "", raw_topic).strip()
    raw_topic = re.sub(r"\s*\|\s*Commits:.*$", "", raw_topic, flags=re.DOTALL).strip()

    if not raw_topic:
        return []

    items = []
    lines = [l.strip() for l in raw_topic.splitlines() if l.strip()]
    if len(lines) > 1:
        for l in lines:
            clean_l = re.sub(r"^[-*•]\s*", "", l).strip()
            clean_l = re.sub(r"^(?:and|&)\s+", "", clean_l, flags=re.IGNORECASE).strip()
            clean_l = re.sub(r"^(?:feat|fix|docs|chore|refactor|test|style|perf|build|ci)(?:\([^)]+\))?:\s*", "", clean_l, flags=re.IGNORECASE).strip()
            clean_l = re.sub(r"\s*\((?:fixes|closes|refs)?\s*#\d+\)", "", clean_l, flags=re.IGNORECASE).strip()
            clean_l = re.sub(r"\s*\(#\d+\)", "", clean_l).strip()
            if clean_l and not clean_l.startswith("PRs:") and not clean_l.startswith("Issues:") and not clean_l.startswith("Commits:"):
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
            clean_p = re.sub(r"^(?:feat|fix|docs|chore|refactor|test|style|perf|build|ci)(?:\([^)]+\))?:\s*", "", clean_p, flags=re.IGNORECASE).strip()
            clean_p = re.sub(r"\s*\((?:fixes|closes|refs)?\s*#\d+\)", "", clean_p, flags=re.IGNORECASE).strip()
            clean_p = re.sub(r"\s*\(#\d+\)", "", clean_p).strip()
            if clean_p and not clean_p.startswith("PRs:") and not clean_p.startswith("Issues:") and not clean_p.startswith("Commits:"):
                clean_p = clean_p[0].upper() + clean_p[1:]
                if clean_p not in items:
                    items.append(clean_p)
    return items


def format_description(
    topic_summary: str,
    prs: list = None,
    issues: list = None,
    project: str = ""
) -> list:
    """Format description lines with PRs, Issues, and topic on the first line, conditionally bulleting additional items.

    Rules:
    - If concise / single topic (len(items) <= 1):
      - With PRs/Issues: - **Description:** [project] PRs: #... | Issues: #... | <Topic>
      - Without PRs/Issues: - **Description:** [project] <Topic>
    - If multiple items / too long (len(items) > 1):
      - First line: - **Description:** [project] PRs: #... | Issues: #... | <Topic 1>
      - Subsequent items formatted as indented bullets (max 2 bullets to keep concise):
        - <Topic 2>
        - <Topic 3>
    """
    clean_prs = [p.strip() for p in (prs or []) if p.strip()]
    clean_issues = [i.strip() for i in (issues or []) if i.strip()]
    proj = (project or "").strip()

    if not proj and topic_summary:
        m_proj = re.match(r"^\[([^\]]+)\]\s*", topic_summary.strip())
        if m_proj:
            proj = m_proj.group(1).strip()

    if not clean_prs and topic_summary:
        m = re.search(r"\bPRs:\s*([^|]+)", topic_summary)
        if m:
            clean_prs = [p.strip() for p in m.group(1).split(",") if p.strip()]

    if not clean_issues and topic_summary:
        m = re.search(r"\bIssues:\s*([^|]+)", topic_summary)
        if m:
            clean_issues = [i.strip() for i in m.group(1).split(",") if i.strip()]

    prefixes = []
    if clean_prs:
        prefixes.append(f"PRs: {', '.join(clean_prs)}")
    if clean_issues:
        prefixes.append(f"Issues: {', '.join(clean_issues)}")
    joined_prefix = " | ".join(prefixes)

    project_prefix = f"[{proj}] " if proj else ""

    items = extract_topic_items(topic_summary)
    if not items:
        first_topic = "Engineering Work"
        sub_items = []
    else:
        first_topic = items[0]
        # Keep descriptions concise by capping sub-items at at most 2 indented bullets
        sub_items = items[1:3]

    if joined_prefix and first_topic:
        first_line = f"- **Description:** {project_prefix}{joined_prefix} | {first_topic}"
    elif joined_prefix:
        first_line = f"- **Description:** {project_prefix}{joined_prefix}"
    elif first_topic:
        first_line = f"- **Description:** {project_prefix}{first_topic}"
    else:
        first_line = f"- **Description:** {project_prefix}Engineering Work"

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
    comments: list = None,
    issues: list = None,
    project: str = "",
    discussions: list = None
) -> str:
    """Format a single timesheet block entry into standard markdown."""
    prs = prs or []
    repos = repos or []
    commit_subjects = commit_subjects or []
    reviews = reviews or []
    comments = comments or []
    issues = issues or []
    discussions = discussions or []

    proj = (project or "").strip()
    if not proj and topic_summary:
        m_proj = re.match(r"^\[([^\]]+)\]\s*", topic_summary.strip())
        if m_proj:
            proj = m_proj.group(1).strip()

    desc_lines = format_description(topic_summary, prs=prs, issues=issues, project=proj)

    first_sentence = (topic_summary or "Engineering Work").split('\n')[0].split('.')[0].strip()
    first_sentence = re.sub(r"^\[[^\]]+\]\s*", "", first_sentence).strip()
    first_sentence = re.sub(r"^PRs:\s*[^|]+\|\s*", "", first_sentence).strip()
    first_sentence = re.sub(r"^Issues:\s*[^|]+\|\s*", "", first_sentence).strip()
    first_sentence = re.sub(r"^(?:feat|fix|docs|chore|refactor|test|style|perf|build|ci)(?:\([^)]+\))?:\s*", "", first_sentence, flags=re.IGNORECASE).strip()
    first_sentence = re.sub(r"\s*\((?:fixes|closes|refs)?\s*#\d+\)", "", first_sentence, flags=re.IGNORECASE).strip()
    first_sentence = re.sub(r"\s*\(#\d+\)", "", first_sentence).strip()
    if len(first_sentence) > 65:
        header_title = first_sentence[:62].rsplit(" ", 1)[0] + "..."
    else:
        header_title = first_sentence or "Engineering Work"
    if header_title:
        header_title = header_title[0].upper() + header_title[1:]

    if proj and not header_title.startswith(f"[{proj}]"):
        header_title = f"[{proj}] {header_title}"

    source_trace_lines = [
        "- **Source Trace:**",
        f"  - *Calendar / Activity:* {source_title or 'General Work Block'}",
        f"  - *Repos:* {', '.join(repos) if repos else 'N/A'}",
        f"  - *Commits:* {'; '.join(commit_subjects) if commit_subjects else 'None'}",
    ]
    if issues:
        clean_issues = [i.strip() for i in issues if i.strip()]
        if clean_issues:
            source_trace_lines.append(f"  - *Issues:* {', '.join(clean_issues)}")
    if reviews:
        clean_reviews = [r.strip() for r in reviews if r.strip()]
        if clean_reviews:
            source_trace_lines.append(f"  - *Reviews:* {'; '.join(clean_reviews)}")
    if discussions:
        clean_discussions = [d.strip() for d in discussions if d.strip()]
        if clean_discussions:
            source_trace_lines.append(f"  - *Discussions:* {'; '.join(clean_discussions)}")
    elif comments:
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
            comments=data.get("comments", []),
            issues=data.get("issues", []),
            project=data.get("project", ""),
            discussions=data.get("discussions", [])
        )
        print(entry_md)


if __name__ == "__main__":
    main()
