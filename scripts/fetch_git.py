#!/usr/bin/env python3
"""[Script] Deterministic Git commit collector across configured repositories."""

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


def extract_prs_from_subject(subject: str) -> list:
    """Extract PR / issue numbers like #123 from commit subject."""
    matches = re.findall(r"#(\d+)", subject)
    return [f"#{m}" for m in matches]


def get_git_executable() -> str:
    """Find git executable on the system."""
    for path in ["/opt/homebrew/bin/git", "/usr/local/bin/git", "/usr/bin/git", "git"]:
        try:
            res = subprocess.run([path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                return path
        except FileNotFoundError:
            continue
    return "git"


def fetch_commits_for_repo(repo_path: Path, target_date: str, author_filter: str = "") -> list:
    """Fetch commits for a single git repository for target_date (YYYY-MM-DD)."""
    if not (repo_path / ".git").exists() and not repo_path.is_dir():
        return []

    git_bin = get_git_executable()
    since_str = f"{target_date} 00:00:00"
    until_str = f"{target_date} 23:59:59"

    cmd = [
        git_bin,
        "-C", str(repo_path),
        "log",
        "--all",
        f"--since={since_str}",
        f"--until={until_str}",
        "--date=iso",
        "--pretty=format:%h|%an|%ae|%ad|%s"
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    except subprocess.CalledProcessError:
        return []

    commits = []
    lines = res.stdout.strip().split("\n") if res.stdout.strip() else []

    repo_name = repo_path.name
    if repo_name == "." or repo_name == "":
        repo_name = repo_path.resolve().name

    seen_hashes = set()
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("|", 4)
        if len(parts) < 5:
            continue
        commit_hash, author_name, author_email, date_str, subject = parts
        if commit_hash in seen_hashes:
            continue
        seen_hashes.add(commit_hash)

        if author_filter:
            author_lower = author_filter.lower()
            if author_lower not in author_name.lower() and author_lower not in author_email.lower():
                continue

        time_part = "12:00"
        time_match = re.search(r"(\d{2}:\d{2}):\d{2}", date_str)
        if time_match:
            time_part = time_match.group(1)

        prs = extract_prs_from_subject(subject)

        commits.append({
            "repo": repo_name,
            "hash": commit_hash,
            "author": author_name,
            "email": author_email,
            "time": time_part,
            "raw_date": date_str,
            "subject": subject,
            "prs": prs
        })

    commits.sort(key=lambda x: x["time"])
    return commits


def fetch_all_commits(target_date: str, author_filter: str = "") -> list:
    """Fetch commits across all configured repositories and auto-discovered sibling repositories."""
    config = load_config()
    root = find_project_root()
    repo_paths = list(config.get("repos", ["."]))
    author = author_filter or config.get("user", {}).get("git_author", "")

    # Auto-discover sibling git repositories in root.parent (e.g. ~/Documents)
    if config.get("auto_discover_siblings", True) and root.parent.exists():
        for sibling in root.parent.iterdir():
            if sibling.is_dir() and (sibling / ".git").exists() and sibling.resolve() != root.resolve():
                sibling_resolved = str(sibling.resolve())
                existing_resolved = [
                    str(Path(r).resolve() if Path(r).is_absolute() else (root / r).resolve())
                    for r in repo_paths
                ]
                if sibling_resolved not in existing_resolved:
                    repo_paths.append(sibling_resolved)

    all_commits = []
    seen_hashes = set()
    for rel_or_abs in repo_paths:
        p = Path(rel_or_abs)
        if not p.is_absolute():
            p = (root / p).resolve()
        commits = fetch_commits_for_repo(p, target_date, author)
        for c in commits:
            if c["hash"] not in seen_hashes:
                seen_hashes.add(c["hash"])
                all_commits.append(c)

    all_commits.sort(key=lambda x: x["time"])
    return all_commits


def main():
    parser = argparse.ArgumentParser(description="Fetch git commits for timesheet.")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Target date YYYY-MM-DD")
    parser.add_argument("--author", default="", help="Filter by author name or email")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    args = parser.parse_args()

    commits = fetch_all_commits(args.date, args.author)
    indent = 2 if args.pretty else None
    print(json.dumps(commits, indent=indent))


if __name__ == "__main__":
    main()
