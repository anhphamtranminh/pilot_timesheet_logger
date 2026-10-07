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


def main():
    parser = argparse.ArgumentParser(description="Fetch pull requests for timesheet.")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Target date YYYY-MM-DD")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    args = parser.parse_args()

    prs = fetch_all_prs(args.date)
    indent = 2 if args.pretty else None
    print(json.dumps(prs, indent=indent))


if __name__ == "__main__":
    main()
