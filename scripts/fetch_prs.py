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


def fetch_prs_via_gh_cli(target_date: str, username: str) -> list:
    """Attempt to fetch PRs using gh CLI if installed and authenticated."""
    for bin_path in ["/opt/homebrew/bin/gh", "/usr/local/bin/gh", "gh"]:
        try:
            check = subprocess.run([bin_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if check.returncode == 0:
                prs = []
                seen = set()
                query = f"author:{username} updated:{target_date}" if username else f"updated:{target_date}"
                cmd = [bin_path, "search", "prs", query, "--json", "number,title,repository,state,url"]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    items = json.loads(res.stdout)
                    for item in items:
                        num = f"#{item.get('number')}"
                        if num not in seen:
                            seen.add(num)
                            prs.append({
                                "number": num,
                                "title": item.get("title", ""),
                                "repo": item.get("repository", {}).get("name", ""),
                                "status": item.get("state", "open").lower(),
                                "url": item.get("url", "")
                            })
                return prs
        except FileNotFoundError:
            continue
    return []


def fetch_all_prs(target_date: str) -> list:
    """Fetch pull requests for the target date."""
    config = load_config()
    username = config.get("user", {}).get("github_username", "")

    prs = fetch_prs_via_gh_cli(target_date, username)
    if prs:
        return prs

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
