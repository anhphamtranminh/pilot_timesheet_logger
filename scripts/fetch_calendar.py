#!/usr/bin/env python3
"""[Script] Deterministic Calendar event collector supporting iCal feeds, local .ics, and fallback blocks."""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Add parent directory to sys.path to import config
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import find_project_root, load_config


def parse_ics_datetime(dt_str: str) -> tuple:
    """Parse iCal date/datetime string into (date_str, time_str), converting UTC to local time."""
    clean = dt_str.split(":")[-1].strip()
    is_utc = clean.endswith("Z")
    val = clean.replace("Z", "")

    if "T" in val:
        if is_utc:
            try:
                dt_utc = datetime.datetime.strptime(clean, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
                dt_local = dt_utc.astimezone()
                return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M")
            except Exception:
                pass

        date_part, time_part = val.split("T")
        y = date_part[0:4]
        m = date_part[4:6]
        d = date_part[6:8]
        hh = time_part[0:2]
        mm = time_part[2:4]
        return f"{y}-{m}-{d}", f"{hh}:{mm}"
    elif len(val) >= 8:
        y = val[0:4]
        m = val[4:6]
        d = val[6:8]
        return f"{y}-{m}-{d}", "00:00"
    return "", ""


def parse_ics_content(ics_text: str, target_date: str) -> list:
    """Parse VEVENT items from iCal content for a specific date."""
    events = []
    in_vevent = False
    current_event = {}

    unfolded_lines = []
    for line in ics_text.splitlines():
        if line.startswith(" ") or line.startswith("\t"):
            if unfolded_lines:
                unfolded_lines[-1] += line[1:]
        else:
            unfolded_lines.append(line)

    for line in unfolded_lines:
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_vevent = True
            current_event = {}
        elif line == "END:VEVENT":
            in_vevent = False
            start_date, start_time = parse_ics_datetime(current_event.get("DTSTART", ""))
            end_date, end_time = parse_ics_datetime(current_event.get("DTEND", ""))
            summary = current_event.get("SUMMARY", "Work Block").strip()

            if start_date == target_date:
                events.append({
                    "title": summary,
                    "start_time": start_time or "09:00",
                    "end_time": end_time or "10:00",
                    "source": "calendar"
                })
        elif in_vevent:
            if ":" in line:
                key, val = line.split(":", 1)
                base_key = key.split(";")[0]
                current_event[base_key] = val

    events.sort(key=lambda x: x["start_time"])
    return events


def fetch_events_from_source(source: str, target_date: str) -> list:
    """Fetch from local .ics file or remote iCal URL."""
    ics_text = ""
    if source.startswith("http://") or source.startswith("https://") or source.startswith("webcal://"):
        url = source.replace("webcal://", "https://")
        req = urllib.request.Request(url, headers={"User-Agent": "PilotTimesheetLogger/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                ics_text = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"[WARN] Failed to fetch calendar URL: {e}", file=sys.stderr)
            return []
    else:
        file_path = Path(source)
        if not file_path.is_absolute():
            file_path = find_project_root() / file_path
        if file_path.exists():
            try:
                ics_text = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                print(f"[WARN] Failed to read calendar file: {e}", file=sys.stderr)
                return []

    if ics_text:
        return parse_ics_content(ics_text, target_date)
    return []


def fetch_all_events(target_date: str, include_defaults: bool = False) -> list:
    """Fetch calendar events from configured source or local .ics."""
    config = load_config()
    cal_cfg = config.get("calendar", {})
    ics_source = cal_cfg.get("ics_path_or_url", "")

    events = []
    if ics_source:
        events = fetch_events_from_source(ics_source, target_date)

    if not events:
        local_ics = find_project_root() / "calendar.ics"
        if local_ics.exists():
            events = fetch_events_from_source(str(local_ics), target_date)

    # Only fall back to default template blocks if explicitly requested
    if not events and include_defaults:
        default_blocks = cal_cfg.get("default_blocks", [
            {"title": "Morning Work Block", "start": "09:00", "end": "12:00"},
            {"title": "Afternoon Work Block", "start": "13:30", "end": "18:00"}
        ])
        for b in default_blocks:
            events.append({
                "title": b.get("title", "Work Block"),
                "start_time": b.get("start", "09:00"),
                "end_time": b.get("end", "12:00"),
                "source": "default_block"
            })

    events.sort(key=lambda x: x["start_time"])
    return events


def main():
    parser = argparse.ArgumentParser(description="Fetch calendar events for timesheet.")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Target date YYYY-MM-DD")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    args = parser.parse_args()

    events = fetch_all_events(args.date)
    indent = 2 if args.pretty else None
    print(json.dumps(events, indent=indent))


if __name__ == "__main__":
    main()
