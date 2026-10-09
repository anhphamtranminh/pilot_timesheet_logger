#!/usr/bin/env python3
"""[Script] Deterministic Pull Request collector for GitHub/GitLab."""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Add parent directory to sys.path to import config
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import find_project_root, load_config


def extract_prs_from_git_log(target_date: str) -> list:
    """Fallback: Extract PRs merged or referenced in local git logs."""
    from fetch_git import fetch_all_commits
    commits = fetch_all_commits(target_date)
    prs = []
    seen = set()

    for c in commits:
        subj = c["subject"]
        repo = c["repo"]
        # Merge pull request #123 from user/branch
        m_merge = re.search(r"Merge pull request #(\d+)", subj)
        if m_merge:
            num = f"#{m_merge.group(1)}"
            if num not in seen:
                seen.add(num)
                prs.append({
                    "number": num,
                    "title": subj,
                    "repo": repo,
                    "status": "merged",
                    "url": ""
                })
        # (#123) inline
        for p in c.get("prs", []):
            if p not in seen:
                seen.add(p)
                prs.append({
                    "number": p,
                    "title": subj,
                    "repo": repo,
                    "status": "merged",
                    "url": ""
                })

    return prs


def iso_to_local_date(iso_str: str) -> str:
    """Convert ISO8601 UTC timestamp to local YYYY-MM-DD."""
    if not iso_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:10]


def iso_to_local_time(iso_str: str) -> str:
    """Convert ISO8601 UTC timestamp to local HH:MM."""
    if not iso_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M")
    except Exception:
        return ""


def fetch_prs_from_repos_gh_cli(target_date: str, username: str, repos: list) -> list:
    """Fetch PRs across configured repos using gh pr list (avoids Search API secondary rate limits)."""
    gh_bin = None
    for bin_path in ["/opt/homebrew/bin/gh", "/usr/local/bin/gh", "gh"]:
        try:
            check = subprocess.run([bin_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if check.returncode == 0:
                gh_bin = bin_path
                break
        except FileNotFoundError:
            continue

    if not gh_bin:
        return []

    project_root = find_project_root()
    prs = []
    seen = set()

    for r in repos:
        repo_path = Path(r)
        if not repo_path.is_absolute():
            repo_path = (project_root / repo_path).resolve()

        if not repo_path.is_dir():
            continue

        repo_name = repo_path.name

        cmd = [
            gh_bin, "pr", "list",
            "--state", "all",
            "--json", "number,title,state,url,author,updatedAt,mergedAt,createdAt",
            "--limit", "30"
        ]
        try:
            res = subprocess.run(cmd, cwd=str(repo_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and res.stdout.strip():
                items = json.loads(res.stdout)
                for item in items:
                    num = f"#{item.get('number')}"
                    if num in seen:
                        continue

                    created_date = iso_to_local_date(item.get("createdAt") or "")
                    updated_date = iso_to_local_date(item.get("updatedAt") or "")
                    merged_date = iso_to_local_date(item.get("mergedAt") or "")

                    if target_date not in (created_date, updated_date, merged_date):
                        continue

                    author_login = item.get("author", {}).get("login", "")
                    raw_state = item.get("state", "OPEN").lower()

                    if raw_state == "merged" and merged_date == target_date:
                        status = "merged"
                    elif username and author_login and author_login.lower() != username.lower():
                        status = "reviewed"
                    elif created_date == target_date or raw_state == "open":
                        status = "opened"
                    else:
                        status = raw_state

                    action_time = ""
                    if merged_date == target_date and item.get("mergedAt"):
                        action_time = iso_to_local_time(item.get("mergedAt"))
                    elif created_date == target_date and item.get("createdAt"):
                        action_time = iso_to_local_time(item.get("createdAt"))
                    elif updated_date == target_date and item.get("updatedAt"):
                        action_time = iso_to_local_time(item.get("updatedAt"))

                    seen.add(num)
                    prs.append({
                        "number": num,
                        "title": item.get("title", ""),
                        "repo": repo_name,
                        "status": status,
                        "url": item.get("url", ""),
                        "time": action_time
                    })
        except Exception:
            continue

    return prs


def fetch_prs_via_gh_cli(target_date: str, username: str) -> list:
    """Attempt to fetch PRs using gh CLI if installed and authenticated."""
    for bin_path in ["/opt/homebrew/bin/gh", "/usr/local/bin/gh", "gh"]:
        try:
            check = subprocess.run([bin_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if check.returncode == 0:
                prs = []
                seen = set()
                # Section 3.1: "Pull PRs you opened, reviewed, or that merged today"
                query = f"involves:{username} updated:{target_date}" if username else f"updated:{target_date}"
                cmd = [bin_path, "search", "prs", query, "--json", "number,title,repository,state,url,author"]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    items = json.loads(res.stdout)
                    for item in items:
                        num = f"#{item.get('number')}"
                        if num not in seen:
                            seen.add(num)
                            raw_state = item.get("state", "open").lower()
                            author_login = item.get("author", {}).get("login", "")
                            
                            # Determine status: opened, reviewed, or merged
                            if raw_state == "merged":
                                status = "merged"
                            elif username and author_login and author_login.lower() != username.lower():
                                status = "reviewed"
                            elif raw_state == "open":
                                status = "opened"
                            else:
                                status = raw_state

                            prs.append({
                                "number": num,
                                "title": item.get("title", ""),
                                "repo": item.get("repository", {}).get("name", ""),
                                "status": status,
                                "url": item.get("url", "")
                            })
                return prs
        except FileNotFoundError:
            continue
    return []


def fetch_all_prs(target_date: str) -> list:
    """Fetch pull requests for the target date across repos and GitHub."""
    config = load_config()
    username = config.get("user", {}).get("github_username", "")
    root = find_project_root()
    repos = list(config.get("repos", ["."]))

    # Auto-discover sibling git repositories in root.parent (e.g. ~/Documents)
    if config.get("auto_discover_siblings", True) and root.parent.exists():
        for sibling in root.parent.iterdir():
            if sibling.is_dir() and (sibling / ".git").exists() and sibling.resolve() != root.resolve():
                sibling_resolved = str(sibling.resolve())
                existing_resolved = [
                    str(Path(r).resolve() if Path(r).is_absolute() else (root / r).resolve())
                    for r in repos
                ]
                if sibling_resolved not in existing_resolved:
                    repos.append(sibling_resolved)

    # First attempt: gh pr list across configured repos (fast, avoids secondary search rate limits)
    prs = fetch_prs_from_repos_gh_cli(target_date, username, repos)
    if prs:
        return prs

    # Second attempt: gh search prs across GitHub
    prs = fetch_prs_via_gh_cli(target_date, username)
    if prs:
        return prs

    # Third attempt: extract from local git log
    return extract_prs_from_git_log(target_date)


def clean_snippet(text: str, max_len: int = 70) -> str:
    """Format and truncate multiline text into a clean snippet."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) > max_len:
        return cleaned[:max_len - 3] + "..."
    return cleaned


def fetch_comments_and_reviews_from_repos_gh_cli(target_date: str, username: str, repos: list) -> tuple:
    """Fetch comments and reviews across configured repos using gh CLI."""
    gh_bin = None
    for bin_path in ["/opt/homebrew/bin/gh", "/usr/local/bin/gh", "gh"]:
        try:
            check = subprocess.run([bin_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if check.returncode == 0:
                gh_bin = bin_path
                break
        except FileNotFoundError:
            continue

    if not gh_bin:
        return [], []

    project_root = find_project_root()
    comments = []
    reviews = []
    seen_comments = set()
    seen_reviews = set()

    for r in repos:
        repo_path = Path(r)
        if not repo_path.is_absolute():
            repo_path = (project_root / repo_path).resolve()

        if not repo_path.is_dir():
            continue

        repo_name = repo_path.name

        # 1. Fetch PR comments and reviews
        pr_cmd = [
            gh_bin, "pr", "list",
            "--state", "all",
            "--json", "number,title,comments,reviews,updatedAt,url",
            "--limit", "30"
        ]
        try:
            res_pr = subprocess.run(pr_cmd, cwd=str(repo_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res_pr.returncode == 0 and res_pr.stdout.strip():
                items = json.loads(res_pr.stdout)
                for item in items:
                    num = f"#{item.get('number')}"
                    # Check PR comments
                    for c in item.get("comments", []):
                        created_date = iso_to_local_date(c.get("createdAt") or "")
                        if created_date == target_date:
                            author = c.get("author", {}).get("login", "")
                            body = c.get("body", "")
                            action_time = iso_to_local_time(c.get("createdAt") or "")
                            if username and author and author.lower() == username.lower():
                                summary = f"{num}: {clean_snippet(body)}"
                            else:
                                summary = f"{num} comment by @{author}: {clean_snippet(body)}"
                            dedup_key = (repo_name, num, action_time, summary[:30])
                            if dedup_key not in seen_comments:
                                seen_comments.add(dedup_key)
                                comments.append({
                                    "number": num,
                                    "title": item.get("title", ""),
                                    "time": action_time,
                                    "author": author,
                                    "repo": repo_name,
                                    "summary": summary,
                                    "url": c.get("url", "")
                                })

                    # Check PR reviews
                    for rev in item.get("reviews", []):
                        rev_ts = rev.get("submittedAt") or rev.get("createdAt") or ""
                        rev_date = iso_to_local_date(rev_ts)
                        if rev_date == target_date:
                            author = rev.get("author", {}).get("login", "")
                            state = rev.get("state", "").upper()
                            body = rev.get("body", "")
                            action_time = iso_to_local_time(rev_ts)

                            state_clean = state.lower()
                            if state_clean == "approved":
                                summary = f"{num}: approved by @{author}"
                            elif state_clean == "changes_requested":
                                summary = f"{num}: changes requested by @{author}"
                            elif state_clean == "commented":
                                summary = f"{num}: review comment by @{author}"
                            else:
                                summary = f"{num}: review ({state_clean}) by @{author}"

                            if body:
                                summary += f": {clean_snippet(body, 50)}"

                            dedup_key = (repo_name, num, action_time, summary[:30])
                            if dedup_key not in seen_reviews:
                                seen_reviews.add(dedup_key)
                                reviews.append({
                                    "number": num,
                                    "title": item.get("title", ""),
                                    "time": action_time,
                                    "author": author,
                                    "repo": repo_name,
                                    "state": state,
                                    "summary": summary,
                                    "url": rev.get("url", "")
                                })
        except Exception:
            pass

        # 2. Fetch Issue comments
        iss_cmd = [
            gh_bin, "issue", "list",
            "--state", "all",
            "--json", "number,title,comments,updatedAt,url",
            "--limit", "30"
        ]
        try:
            res_iss = subprocess.run(iss_cmd, cwd=str(repo_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res_iss.returncode == 0 and res_iss.stdout.strip():
                items = json.loads(res_iss.stdout)
                for item in items:
                    num = f"#{item.get('number')}"
                    for c in item.get("comments", []):
                        created_date = iso_to_local_date(c.get("createdAt") or "")
                        if created_date == target_date:
                            author = c.get("author", {}).get("login", "")
                            body = c.get("body", "")
                            action_time = iso_to_local_time(c.get("createdAt") or "")
                            if username and author and author.lower() == username.lower():
                                summary = f"{num}: {clean_snippet(body)}"
                            else:
                                summary = f"{num} comment by @{author}: {clean_snippet(body)}"
                            dedup_key = (repo_name, num, action_time, summary[:30])
                            if dedup_key not in seen_comments:
                                seen_comments.add(dedup_key)
                                comments.append({
                                    "number": num,
                                    "title": item.get("title", ""),
                                    "time": action_time,
                                    "author": author,
                                    "repo": repo_name,
                                    "summary": summary,
                                    "url": c.get("url", "")
                                })
        except Exception:
            pass

    return comments, reviews


def fetch_comments_and_reviews_from_user_events_gh_cli(target_date: str, username: str) -> tuple:
    """Fetch user comments and reviews from GitHub user events."""
    if not username:
        return [], []

    gh_bin = None
    for bin_path in ["/opt/homebrew/bin/gh", "/usr/local/bin/gh", "gh"]:
        try:
            check = subprocess.run([bin_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if check.returncode == 0:
                gh_bin = bin_path
                break
        except FileNotFoundError:
            continue

    if not gh_bin:
        return [], []

    comments = []
    reviews = []
    try:
        cmd = [gh_bin, "api", f"users/{username}/events"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and res.stdout.strip():
            events = json.loads(res.stdout)
            for ev in events:
                created_at = ev.get("created_at", "")
                if iso_to_local_date(created_at) != target_date:
                    continue

                action_time = iso_to_local_time(created_at)
                repo_full = ev.get("repo", {}).get("name", "")
                repo_name = repo_full.split("/")[-1] if "/" in repo_full else repo_full
                ev_type = ev.get("type", "")
                payload = ev.get("payload", {})

                if ev_type == "IssueCommentEvent":
                    issue = payload.get("issue", {})
                    comment = payload.get("comment", {})
                    num = f"#{issue.get('number')}"
                    body = comment.get("body", "")
                    summary = f"{num}: {clean_snippet(body)}"
                    comments.append({
                        "number": num,
                        "time": action_time,
                        "author": username,
                        "repo": repo_name,
                        "summary": summary,
                        "url": comment.get("html_url", "")
                    })
                elif ev_type == "PullRequestReviewEvent":
                    pr = payload.get("pull_request", {})
                    review = payload.get("review", {})
                    num = f"#{pr.get('number')}"
                    state = review.get("state", "").upper()
                    body = review.get("body", "")
                    summary = f"{num}: review ({state.lower()})"
                    if body:
                        summary += f": {clean_snippet(body, 50)}"
                    reviews.append({
                        "number": num,
                        "time": action_time,
                        "author": username,
                        "repo": repo_name,
                        "state": state,
                        "summary": summary,
                        "url": review.get("html_url", "")
                    })
                elif ev_type == "PullRequestReviewCommentEvent":
                    pr = payload.get("pull_request", {})
                    comment = payload.get("comment", {})
                    num = f"#{pr.get('number')}"
                    body = comment.get("body", "")
                    summary = f"{num}: review comment: {clean_snippet(body)}"
                    comments.append({
                        "number": num,
                        "time": action_time,
                        "author": username,
                        "repo": repo_name,
                        "summary": summary,
                        "url": comment.get("html_url", "")
                    })
    except Exception:
        pass

    return comments, reviews


def fetch_all_comments_and_reviews(target_date: str) -> tuple:
    """Fetch all comments and PR reviews for target date across repos and user events."""
    config = load_config()
    username = config.get("user", {}).get("github_username", "")
    root = find_project_root()
    repos = list(config.get("repos", ["."]))

    if config.get("auto_discover_siblings", True) and root.parent.exists():
        for sibling in root.parent.iterdir():
            if sibling.is_dir() and (sibling / ".git").exists() and sibling.resolve() != root.resolve():
                sibling_resolved = str(sibling.resolve())
                existing_resolved = [
                    str(Path(r).resolve() if Path(r).is_absolute() else (root / r).resolve())
                    for r in repos
                ]
                if sibling_resolved not in existing_resolved:
                    repos.append(sibling_resolved)

    repo_comments, repo_reviews = fetch_comments_and_reviews_from_repos_gh_cli(target_date, username, repos)
    user_comments, user_reviews = fetch_comments_and_reviews_from_user_events_gh_cli(target_date, username)

    # Merge and deduplicate comments
    all_comments = []
    seen_c = set()
    for c in repo_comments + user_comments:
        key = (c.get("number", ""), c.get("time", ""), c.get("summary", "")[:25])
        if key not in seen_c:
            seen_c.add(key)
            all_comments.append(c)

    # Merge and deduplicate reviews
    all_reviews = []
    seen_r = set()
    for r in repo_reviews + user_reviews:
        key = (r.get("number", ""), r.get("time", ""), r.get("summary", "")[:25])
        if key not in seen_r:
            seen_r.add(key)
            all_reviews.append(r)

    all_comments.sort(key=lambda x: x.get("time", ""))
    all_reviews.sort(key=lambda x: x.get("time", ""))
    return all_comments, all_reviews


def fetch_all_comments(target_date: str) -> list:
    """Fetch comments for target date."""
    comments, _ = fetch_all_comments_and_reviews(target_date)
    return comments


def fetch_all_reviews(target_date: str) -> list:
    """Fetch PR reviews for target date."""
    _, reviews = fetch_all_comments_and_reviews(target_date)
    return reviews


def fetch_issues_from_repos_gh_cli(target_date: str, username: str, repos: list) -> list:
    """Fetch GitHub issues active on target_date (created, closed, or commented)."""
    gh_bin = None
    for bin_path in ["/opt/homebrew/bin/gh", "/usr/local/bin/gh", "gh"]:
        try:
            check = subprocess.run([bin_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if check.returncode == 0:
                gh_bin = bin_path
                break
        except FileNotFoundError:
            continue

    if not gh_bin:
        return []

    project_root = find_project_root()
    issues = []
    seen = set()

    for r in repos:
        repo_path = Path(r)
        if not repo_path.is_absolute():
            repo_path = (project_root / repo_path).resolve()

        if not repo_path.is_dir():
            continue

        repo_name = repo_path.name

        cmd = [
            gh_bin, "issue", "list",
            "--state", "all",
            "--json", "number,title,comments,updatedAt,url,author,createdAt,closedAt",
            "--limit", "30"
        ]
        try:
            res = subprocess.run(cmd, cwd=str(repo_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and res.stdout.strip():
                items = json.loads(res.stdout)
                for item in items:
                    num = f"#{item.get('number')}"
                    dedup_key = (repo_name, num)
                    if dedup_key in seen:
                        continue

                    created_date = iso_to_local_date(item.get("createdAt") or "")
                    updated_date = iso_to_local_date(item.get("updatedAt") or "")
                    closed_date = iso_to_local_date(item.get("closedAt") or "")

                    # Check for comments created on target_date
                    today_comments = [
                        c for c in item.get("comments", [])
                        if iso_to_local_date(c.get("createdAt") or "") == target_date
                    ]

                    # Is this issue active today?
                    if target_date not in (created_date, updated_date, closed_date) and not today_comments:
                        continue

                    action_time = ""
                    if today_comments:
                        comment_times = [iso_to_local_time(c.get("createdAt") or "") for c in today_comments if c.get("createdAt")]
                        if comment_times:
                            action_time = max(comment_times)
                    elif closed_date == target_date and item.get("closedAt"):
                        action_time = iso_to_local_time(item.get("closedAt"))
                    elif created_date == target_date and item.get("createdAt"):
                        action_time = iso_to_local_time(item.get("createdAt"))
                    elif updated_date == target_date and item.get("updatedAt"):
                        action_time = iso_to_local_time(item.get("updatedAt"))

                    status = "open"
                    if closed_date == target_date:
                        status = "closed"
                    elif created_date == target_date:
                        status = "opened"
                    elif today_comments:
                        status = "commented"

                    seen.add(dedup_key)
                    issues.append({
                        "number": num,
                        "title": item.get("title", ""),
                        "repo": repo_name,
                        "status": status,
                        "url": item.get("url", ""),
                        "time": action_time,
                        "comments_count": len(today_comments)
                    })
        except Exception:
            continue

    issues.sort(key=lambda x: x.get("time", ""))
    return issues


def fetch_all_issues(target_date: str) -> list:
    """Fetch all GitHub issues active on target_date across repos."""
    config = load_config()
    username = config.get("user", {}).get("github_username", "")
    root = find_project_root()
    repos = list(config.get("repos", ["."]))

    if config.get("auto_discover_siblings", True) and root.parent.exists():
        for sibling in root.parent.iterdir():
            if sibling.is_dir() and (sibling / ".git").exists() and sibling.resolve() != root.resolve():
                sibling_resolved = str(sibling.resolve())
                existing_resolved = [
                    str(Path(r).resolve() if Path(r).is_absolute() else (root / r).resolve())
                    for r in repos
                ]
                if sibling_resolved not in existing_resolved:
                    repos.append(sibling_resolved)

    return fetch_issues_from_repos_gh_cli(target_date, username, repos)


def summarize_discussions(comments: list) -> list:
    """Summarize comments into concise, topic-level discussion points per issue/PR."""
    if not comments:
        return []

    # Group comments by (repo, number)
    grouped = {}
    for c in comments:
        if isinstance(c, dict):
            num = c.get("number", "")
            repo = c.get("repo", "")
            title = c.get("title", "")
            author = c.get("author", "")
            summary = c.get("summary", "")
        else:
            m = re.match(r"^(#\d+)", str(c))
            num = m.group(1) if m else ""
            repo = ""
            title = ""
            author = ""
            summary = str(c)

        key = (repo, num)
        if key not in grouped:
            grouped[key] = {
                "num": num,
                "repo": repo,
                "title": title,
                "authors": set(),
                "count": 0,
                "summaries": []
            }
        if author:
            grouped[key]["authors"].add(author)
        if title and not grouped[key]["title"]:
            grouped[key]["title"] = title
        grouped[key]["count"] += 1
        if summary:
            grouped[key]["summaries"].append(summary)

    discussions = []
    for key, data in grouped.items():
        num = data["num"]
        title = data["title"]
        count = data["count"]

        clean_t = ""
        if title:
            clean_t = re.sub(r"^(?:feat|fix|docs|chore|refactor|test|style|perf|build|ci)(?:\([^)]+\))?:\s*", "", title, flags=re.IGNORECASE).strip()
            clean_t = re.sub(r"\s*\((?:fixes|closes|refs)?\s*#\d+\)", "", clean_t, flags=re.IGNORECASE).strip()
            clean_t = re.sub(r"\s*\(#\d+\)", "", clean_t).strip()
            if len(clean_t) > 50:
                clean_t = clean_t[:47].rsplit(" ", 1)[0] + "..."

        count_suffix = f"({count} comments)" if count > 1 else "(1 comment)"
        if num and clean_t:
            discussions.append(f"{num}: {clean_t} {count_suffix}")
        elif num:
            discussions.append(f"{num} {count_suffix}")
        elif clean_t:
            discussions.append(f"{clean_t} {count_suffix}")
        elif data["summaries"]:
            discussions.append(data["summaries"][0])

    return discussions


def main():
    parser = argparse.ArgumentParser(description="Fetch pull requests, comments, and reviews for timesheet.")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Target date YYYY-MM-DD")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    parser.add_argument("--comments", action="store_true", help="Fetch comments instead of PRs")
    parser.add_argument("--reviews", action="store_true", help="Fetch reviews instead of PRs")
    parser.add_argument("--issues", action="store_true", help="Fetch issues instead of PRs")
    args = parser.parse_args()

    indent = 2 if args.pretty else None
    if args.comments:
        res = fetch_all_comments(args.date)
        print(json.dumps(res, indent=indent))
    elif args.reviews:
        res = fetch_all_reviews(args.date)
        print(json.dumps(res, indent=indent))
    elif args.issues:
        res = fetch_all_issues(args.date)
        print(json.dumps(res, indent=indent))
    else:
        prs = fetch_all_prs(args.date)
        print(json.dumps(prs, indent=indent))


if __name__ == "__main__":
    main()
