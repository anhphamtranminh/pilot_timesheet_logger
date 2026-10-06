#!/usr/bin/env python3
"""Tests for personal pilot timesheet logger scripts."""

import datetime
import json
import os
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
import sys
sys.path.insert(0, str(SCRIPTS_DIR))

from config import DEFAULT_CONFIG, load_config
from fetch_git import extract_prs_from_subject
from fetch_calendar import parse_ics_content, parse_ics_datetime
from prepare_prompt import assign_items_to_blocks, time_to_minutes
from format_entry import format_single_entry
from save_entry import save_or_update_block_entry, get_monthly_log_path
from track_tokens import record_token_run, get_token_csv_path


class TestPilotTimesheet(unittest.TestCase):

    def test_extract_prs_from_subject(self):
        self.assertEqual(extract_prs_from_subject("feat: timesheet setup (#102)"), ["#102"])
        self.assertEqual(extract_prs_from_subject("fix: resolve bug in parser and close #14 and #15"), ["#14", "#15"])
        self.assertEqual(extract_prs_from_subject("chore: simple update"), [])

    def test_parse_ics_datetime(self):
        d, t = parse_ics_datetime("20261006T093000Z")
        self.assertEqual(d, "2026-10-06")
        self.assertEqual(t, "09:30")

        d, t = parse_ics_datetime("TZID=Asia/Bangkok:20261006T140000")
        self.assertEqual(d, "2026-10-06")
        self.assertEqual(t, "14:00")

    def test_parse_ics_content(self):
        sample_ics = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Standup Meeting
DTSTART:20261006T090000Z
DTEND:20261006T093000Z
END:VEVENT
BEGIN:VEVENT
SUMMARY:Sprint Review
DTSTART:20261006T140000Z
DTEND:20261006T150000Z
END:VEVENT
END:VCALENDAR"""
        events = parse_ics_content(sample_ics, "2026-10-06")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["title"], "Standup Meeting")
        self.assertEqual(events[0]["start_time"], "09:00")
        self.assertEqual(events[1]["title"], "Sprint Review")
        self.assertEqual(events[1]["start_time"], "14:00")

    def test_assign_items_to_blocks(self):
        blocks = [
            {"title": "Morning Dev", "start_time": "09:00", "end_time": "12:00", "source": "cal"},
            {"title": "Afternoon Review", "start_time": "13:30", "end_time": "17:30", "source": "cal"}
        ]
        commits = [
            {"repo": "timesheet", "time": "10:15", "subject": "feat: calendar fetcher", "prs": ["#1"]},
            {"repo": "timesheet", "time": "15:00", "subject": "fix: bug in parser", "prs": ["#2"]}
        ]
        prs = [{"number": "#1", "repo": "timesheet"}, {"number": "#2", "repo": "timesheet"}]

        assigned = assign_items_to_blocks(blocks, commits, prs)
        self.assertEqual(len(assigned), 2)
        self.assertIn("feat: calendar fetcher", assigned[0]["commit_subjects"])
        self.assertIn("#1", assigned[0]["prs"])
        self.assertIn("fix: bug in parser", assigned[1]["commit_subjects"])
        self.assertIn("#2", assigned[1]["prs"])

    def test_format_single_entry_spec_compliance(self):
        entry_md = format_single_entry(
            date="2026-10-06",
            start_time="09:00",
            end_time="12:00",
            topic_summary="Timesheet pipeline scaffolding and calendar integration",
            prs=["#101", "#102"],
            source_title="Morning Sprint Block",
            repos=["pilot_timesheet"],
            commit_subjects=["feat: init", "feat: calendar"]
        )

        self.assertIn("- **Date:** 2026-10-06", entry_md)
        self.assertIn("- **Start time:** 09:00", entry_md)
        self.assertIn("- **End time:** 12:00", entry_md)
        self.assertIn("- **Description:** Timesheet pipeline scaffolding and calendar integration | PRs: #101, #102", entry_md)
        self.assertIn("- **Source Trace:**", entry_md)
        self.assertIn("Morning Sprint Block", entry_md)

    def test_save_deduplication(self):
        test_entry = {
            "date": "2026-10-06",
            "start_time": "09:00",
            "end_time": "12:00",
            "topic_summary": "Initial run",
            "prs": ["#1"],
            "source_title": "Dev Block",
            "repos": ["repo1"],
            "commit_subjects": ["feat: initial"]
        }

        save_or_update_block_entry(test_entry)

        updated_entry = dict(test_entry)
        updated_entry["topic_summary"] = "Updated run without duplicates"
        save_or_update_block_entry(updated_entry)

        log_path = get_monthly_log_path("2026-10-06")
        content = log_path.read_text(encoding="utf-8")

        occurrences = content.count("### 2026-10-06 | 09:00 - 12:00")
        self.assertEqual(occurrences, 1)
        self.assertIn("Updated run without duplicates", content)


if __name__ == "__main__":
    unittest.main()
