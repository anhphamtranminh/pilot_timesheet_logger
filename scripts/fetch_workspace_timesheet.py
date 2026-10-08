#!/usr/bin/env python3
"""[Script] Deterministic Gradion Workspace timesheet block data collector.

Connects to Gradion Workspace (https://workspace.gradion.com) via PAT authentication
to retrieve daily timesheet entries or planned work blocks for timesheet compilation.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Add parent directory to sys.path to import config
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import find_project_root, load_config
from format_entry import build_bullet_description

GRADION_BASE_URL = "https://workspace.gradion.com"
SKILL_BUNDLE_VERSION = "1.9.0"


def resolve_gradion_token() -> str:
    """Resolve Gradion Workspace Personal API Token (PAT).

    Checks in priority order:
    1. Environment variable GRADION_API_TOKEN
    2. macOS Keychain entry for GRADION_API_TOKEN
    3. Project config.json under workspace.api_token
    """
    token = os.environ.get("GRADION_API_TOKEN", "").strip()
    if token:
        return token

    # Check macOS Keychain (-s service name or -ga account name)
    for flag in ["-s", "-ga"]:
        try:
            cmd = ["security", "find-generic-password", flag, "GRADION_API_TOKEN", "-w"]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except Exception:
            pass

    # Check config.json
    try:
        cfg = load_config()
        token = cfg.get("workspace", {}).get("api_token", "").strip()
        if token:
            return token
    except Exception:
        pass

    return ""


def make_gradion_request(endpoint: str, token: str, method: str = "GET", data: dict = None) -> dict:
    """Execute authenticated HTTP request to Gradion Workspace API."""
    url = f"{GRADION_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Gradion-Skill-Bundle-Version": SKILL_BUNDLE_VERSION,
        "Accept": "application/json",
        "User-Agent": "PilotTimesheetLogger/1.0"
    }

    req_data = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        req_data = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return json.loads(body) if body else {}


def parse_mcp_entries_text(text: str, target_date: str) -> list:
    """Parse text output from list_my_entries MCP tool into structured timesheet blocks."""
    blocks = []
    # Format: YYYY-MM-DD HH:MM-HH:MM (XhYm) | Project [Internal Project] | submitted | Description · UUID
    # Uses re.DOTALL to match multiline descriptions until the next entry header or EOF
    pattern = re.compile(
        r"(?:^|\n)(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})-(\d{2}:\d{2})\s+\([^)]+\)\s+\|\s+([^|]+)\|\s+([^|]+)\|\s*(.+?)(?:\s*·\s*([a-f0-9-]+))?(?=\n\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}-\d{2}:\d{2}|$)",
        re.DOTALL
    )
    for m in pattern.finditer(text):
        row_date, st, et, proj, status, desc, entry_id = m.groups()
        if row_date == target_date:
            clean_title = re.sub(r"\s*\|\s*#[A-Za-z0-9_-]+", "", desc).strip()
            clean_title = re.sub(r"\s*\|\s*Commits:.*", "", clean_title, flags=re.DOTALL).strip()
            clean_title = re.sub(r"\s*\|\s*PRs:.*", "", clean_title).strip()
            clean_title = re.sub(r"^PRs:\s*[^|]+\|\s*", "", clean_title).strip()
            lines = [re.sub(r"^[-*•]\s*", "", l).strip() for l in clean_title.splitlines() if l.strip()]
            lines = [l for l in lines if not l.startswith("PRs:") and not l.startswith("#")]
            if lines:
                clean_title = " | ".join(lines)
            else:
                clean_title = "Work Block"
            blocks.append({
                "title": clean_title,
                "start_time": st,
                "end_time": et,
                "project": proj.strip(),
                "status": status.strip(),
                "source": "workspace_timesheet",
                "entry_id": entry_id or ""
            })
    blocks.sort(key=lambda x: x["start_time"])
    return blocks


def fetch_workspace_timesheet_blocks(target_date: str) -> list:
    """Fetch timesheet blocks from Gradion Workspace API for a given target_date."""
    token = resolve_gradion_token()
    if not token:
        # Return empty list gracefully if token is not yet configured
        return []

    try:
        # Step 1: Bootstrap caller & workspace info
        me = make_gradion_request("/api/auth/me", token)
        workspace_id = me.get("workspace_id")

        if not workspace_id:
            print("[WARN] Gradion Workspace API: No workspace_id returned in /api/auth/me", file=sys.stderr)
            return []

        timesheet_blocks = []

        # Step 2: Query MCP catalog for timesheet app tools
        mcp_cat = make_gradion_request("/api/me/apps/mcp", token)
        mcp_apps = mcp_cat.get("apps", [])
        for app in mcp_apps:
            if app.get("slug") == "timesheet":
                tools = [t.get("name") for t in app.get("tools", [])]
                if "list_my_entries" in tools:
                    result = make_gradion_request(
                        "/api/me/apps/timesheet/tools/list_my_entries/call",
                        token,
                        method="POST",
                        data={"arguments": {"dateFrom": target_date, "dateTo": target_date, "limit": 50}}
                    )
                    content_list = result.get("content", [])
                    for item in content_list:
                        if item.get("type") == "text":
                            parsed = parse_mcp_entries_text(item.get("text", ""), target_date)
                            timesheet_blocks.extend(parsed)
                break

        # Step 3: Fallback to bulk export catalog if no entries from MCP
        if not timesheet_blocks:
            export_cat = make_gradion_request("/api/me/apps/export", token)
            apps = export_cat.get("apps", [])
            has_timesheet_export = any(app.get("slug") == "timesheet" for app in apps)
            if has_timesheet_export:
                entries_data = make_gradion_request("/api/me/apps/timesheet/export/entries?limit=500", token)
                rows = entries_data.get("rows", [])
                for row in rows:
                    row_date = row.get("date") or row.get("day")
                    if row_date == target_date:
                        title = row.get("task") or row.get("project") or row.get("description") or "Workspace Task"
                        timesheet_blocks.append({
                            "title": title,
                            "start_time": row.get("start_time", "09:00"),
                            "end_time": row.get("end_time", "18:00"),
                            "source": "workspace_timesheet",
                            "raw_entry": row
                        })

        timesheet_blocks.sort(key=lambda x: x.get("start_time", "00:00"))
        return timesheet_blocks

    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("[WARN] Gradion Workspace API: 401 Unauthorized (invalid or revoked GRADION_API_TOKEN)", file=sys.stderr)
        elif e.code == 403:
            print("[WARN] Gradion Workspace API: 403 Forbidden (insufficient token scope for timesheet app)", file=sys.stderr)
        elif e.code == 400:
            print("[WARN] Gradion Workspace API: 400 Bad Request or outdated skill bundle version", file=sys.stderr)
        else:
            print(f"[WARN] Gradion Workspace API HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[WARN] Failed to connect to Gradion Workspace timesheet API: {e}", file=sys.stderr)
        return []


def edit_workspace_timesheet_entry(
    entry_id: str,
    desc: str,
    reason: str = "Automated sync of topic, commits, and PRs",
    task: str = None,
    start_time: str = None,
    end_time: str = None
) -> bool:
    """Update an existing timesheet entry in Gradion Workspace via edit_time MCP tool."""
    token = resolve_gradion_token()
    if not token or not entry_id:
        return False

    try:
        args = {
            "entryId": entry_id,
            "reason": reason[:200],
            "description": desc[:3000]
        }
        if task:
            args["task"] = task[:150]
        if start_time:
            args["startTime"] = start_time
        if end_time:
            args["endTime"] = end_time

        res = make_gradion_request(
            "/api/me/apps/timesheet/tools/edit_time/call",
            token,
            method="POST",
            data={"arguments": args}
        )
        if res.get("isError"):
            err_msg = res.get("content", [{}])[0].get("text", "Unknown error")
            print(f"[WARN] Failed to edit entry in Gradion Workspace ({entry_id[:8]}...): {err_msg}", file=sys.stderr)
            return False

        print(f"[OK] Successfully updated existing entry in Gradion Workspace ({entry_id[:8]}...)")
        return True
    except Exception as e:
        print(f"[WARN] Failed to edit timesheet entry in Gradion Workspace: {e}", file=sys.stderr)
        return False


def post_workspace_timesheet_entry(entry: dict) -> bool:
    """Post or sync a timesheet entry to Gradion Workspace Timesheet app via log_time or edit_time MCP tools."""
    token = resolve_gradion_token()
    if not token:
        return False

    cfg = load_config()
    classification = (
        entry.get("classification")
        or cfg.get("workspace", {}).get("default_classification")
        or "Gradion Intern Academy 2026"
    )
    task = entry.get("task") or cfg.get("workspace", {}).get("default_task") or "#SE"

    desc = entry.get("topic_summary") or entry.get("description", "Daily Development")
    commits = entry.get("commit_subjects", [])
    prs = entry.get("prs", [])
    bullets = build_bullet_description(desc, prs, commits=commits)
    if bullets:
        desc = "\n".join(f"- {b}" for b in bullets)

    start_time = entry.get("start_time", "09:00")
    end_time = entry.get("end_time", "12:00")
    date_str = entry.get("date", datetime.date.today().isoformat())

    # Ensure entry duration does not exceed Gradion Workspace limit (max 4 hours = 240 mins)
    def parse_time_min(t_str):
        parts = t_str.split(":")
        return int(parts[0]) * 60 + int(parts[1]) if len(parts) >= 2 else 0

    s_min = parse_time_min(start_time)
    e_min = parse_time_min(end_time)

    # Ensure entry never spans across lunch break (12:00 - 13:00 / 720 - 780 mins)
    if s_min < 720 and e_min > 720 and not entry.get("entry_id"):
        chunk_morn = dict(entry)
        chunk_morn["end_time"] = "12:00"
        ok_morn = post_workspace_timesheet_entry(chunk_morn)
        ok_aft = True
        if e_min > 780:
            chunk_aft = dict(entry)
            chunk_aft["start_time"] = "13:00"
            ok_aft = post_workspace_timesheet_entry(chunk_aft)
        return ok_morn and ok_aft

    if e_min - s_min > 240 and not entry.get("entry_id"):
        # Auto-split long entry into <= 4-hour chunks
        current_s = s_min
        all_ok = True
        while current_s < e_min:
            chunk_e = min(current_s + 240, e_min)
            chunk_s_str = f"{current_s // 60:02d}:{current_s % 60:02d}"
            chunk_e_str = f"{chunk_e // 60:02d}:{chunk_e % 60:02d}"
            chunk_entry = dict(entry)
            chunk_entry["start_time"] = chunk_s_str
            chunk_entry["end_time"] = chunk_e_str
            chunk_res = post_workspace_timesheet_entry(chunk_entry)
            all_ok = all_ok and chunk_res
            current_s = chunk_e
        return all_ok

    # If entry_id is explicitly provided, update existing entry via edit_time
    entry_id = entry.get("entry_id")
    if entry_id:
        return edit_workspace_timesheet_entry(
            entry_id=entry_id,
            desc=desc,
            reason="Update timesheet block with commits and PRs",
            task=task,
            start_time=start_time,
            end_time=end_time
        )

    try:
        payload = {
            "arguments": {
                "date": date_str,
                "startTime": start_time,
                "endTime": end_time,
                "description": desc,
                "classification": classification,
                "task": task,
                "billable": False
            }
        }
        res = make_gradion_request(
            "/api/me/apps/timesheet/tools/log_time/call",
            token,
            method="POST",
            data=payload
        )
        if res.get("isError"):
            err_msg = res.get("content", [{}])[0].get("text", "Unknown error")

            # If error is due to overlapping entry, find existing overlapping entry and edit it
            if "overlap" in err_msg.lower():
                print(f"[INFO] Overlapping entry detected in Gradion Workspace for {start_time} - {end_time}. Resolving entry ID for edit_time...", file=sys.stderr)
                existing_blocks = fetch_workspace_timesheet_blocks(date_str)

                def to_min(t_str):
                    parts = t_str.split(":")
                    return int(parts[0]) * 60 + int(parts[1]) if len(parts) >= 2 else 0

                s_min = to_min(start_time)
                e_min = to_min(end_time)
                candidates = []
                for eb in existing_blocks:
                    if not eb.get("entry_id"):
                        continue
                    eb_s = to_min(eb.get("start_time", "09:00"))
                    eb_e = to_min(eb.get("end_time", "18:00"))
                    overlap = min(e_min, eb_e) - max(s_min, eb_s)
                    if overlap > 0:
                        candidates.append((overlap, eb))

                if candidates:
                    # Choose entry with greatest overlap
                    best_overlap, best_eb = max(candidates, key=lambda c: c[0])
                    return edit_workspace_timesheet_entry(
                        entry_id=best_eb["entry_id"],
                        desc=desc,
                        reason="Update overlapping block with commits and PRs",
                        task=task,
                        start_time=start_time,
                        end_time=end_time
                    )

            print(f"[WARN] Failed to log time to Gradion Workspace: {err_msg}", file=sys.stderr)
            return False

        print(f"[OK] Successfully logged time to Gradion Workspace ({start_time} - {end_time})")
        return True
    except Exception as e:
        print(f"[WARN] Failed to sync timesheet entry to Gradion Workspace: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Fetch timesheet blocks from Gradion Workspace.")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Target date YYYY-MM-DD")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    parser.add_argument("--post-entry", help="JSON string of entry to post to Gradion Workspace")
    args = parser.parse_args()

    if args.post_entry:
        entry = json.loads(args.post_entry)
        success = post_workspace_timesheet_entry(entry)
        sys.exit(0 if success else 1)

    blocks = fetch_workspace_timesheet_blocks(args.date)
    indent = 2 if args.pretty else None
    print(json.dumps(blocks, indent=indent))


if __name__ == "__main__":
    main()
