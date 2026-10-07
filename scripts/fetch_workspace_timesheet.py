#!/usr/bin/env python3
"""[Script] Deterministic Gradion Workspace timesheet block data collector.

Connects to Gradion Workspace (https://workspace.gradion.com) via PAT authentication
to retrieve daily timesheet entries or planned work blocks for timesheet compilation.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Add parent directory to sys.path to import config
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import find_project_root, load_config

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

    # Check macOS Keychain
    try:
        cmd = ["security", "find-generic-password", "-ga", "GRADION_API_TOKEN", "-w"]
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
        user_id = me.get("id")

        if not workspace_id:
            print("[WARN] Gradion Workspace API: No workspace_id returned in /api/auth/me", file=sys.stderr)
            return []

        # Step 2: Query export catalog to see available timesheet datasets
        export_cat = make_gradion_request("/api/me/apps/export", token)
        apps = export_cat.get("apps", [])

        timesheet_blocks = []

        # Check if timesheet app is present in export catalog
        has_timesheet_export = any(app.get("slug") == "timesheet" for app in apps)
        if has_timesheet_export:
            # Query export entries
            entries_data = make_gradion_request("/api/me/apps/timesheet/export/entries?limit=500", token)
            rows = entries_data.get("rows", [])
            for row in rows:
                # Expected fields: date, start_time, end_time, project, task, description
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

        # Step 3: If no export entries found, check MCP catalog for tools
        if not timesheet_blocks:
            mcp_cat = make_gradion_request("/api/me/apps/mcp", token)
            mcp_apps = mcp_cat.get("apps", [])
            for app in mcp_apps:
                if app.get("slug") == "timesheet":
                    tools = [t.get("name") for t in app.get("tools", [])]
                    # Check for read tools like get_entries, list_entries, get_blocks
                    for read_tool in ["get_entries", "list_entries", "get_blocks"]:
                        if read_tool in tools:
                            result = make_gradion_request(
                                f"/api/me/apps/timesheet/tools/{read_tool}/call",
                                token,
                                method="POST",
                                data={"arguments": {"date": target_date}}
                            )
                            # Parse structuredContent or content
                            if result.get("structuredContent"):
                                sc = result["structuredContent"]
                                entries = sc if isinstance(sc, list) else sc.get("entries", [])
                                for e in entries:
                                    timesheet_blocks.append({
                                        "title": e.get("title") or e.get("project") or "Workspace Task",
                                        "start_time": e.get("start_time", "09:00"),
                                        "end_time": e.get("end_time", "18:00"),
                                        "source": "workspace_timesheet"
                                    })
                            break

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


def post_workspace_timesheet_entry(entry: dict) -> bool:
    """Post or sync a timesheet entry to Gradion Workspace Timesheet app.

    Requires PAT with write scope for the timesheet app.
    Uses MCP tools/call on /api/me/apps/timesheet/tools/{create_entry|log_entry|add_entry}/call.
    """
    token = resolve_gradion_token()
    if not token:
        return False

    try:
        mcp_cat = make_gradion_request("/api/me/apps/mcp", token)
        apps = mcp_cat.get("apps", [])
        write_tool = None
        for app in apps:
            if app.get("slug") == "timesheet":
                tools = [t.get("name") for t in app.get("tools", [])]
                for candidate in ["create_entry", "log_entry", "add_entry", "record_time"]:
                    if candidate in tools:
                        write_tool = candidate
                        break
                break

        if not write_tool:
            print("[INFO] No timesheet write tool found in Gradion Workspace MCP catalog.", file=sys.stderr)
            return False

        payload = {
            "arguments": {
                "date": entry.get("date"),
                "start_time": entry.get("start_time"),
                "end_time": entry.get("end_time"),
                "description": entry.get("topic_summary"),
                "prs": entry.get("prs", []),
                "repos": entry.get("repos", [])
            }
        }
        res = make_gradion_request(
            f"/api/me/apps/timesheet/tools/{write_tool}/call",
            token,
            method="POST",
            data=payload
        )
        print(f"[OK] Synced timesheet entry to Gradion Workspace ({write_tool})")
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
