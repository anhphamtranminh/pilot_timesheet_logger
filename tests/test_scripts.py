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
from format_entry import format_single_entry, format_description, extract_topic_items
from save_entry import save_or_update_block_entry, get_monthly_log_path
from track_tokens import record_token_run, get_token_csv_path, generate_ascii_chart, generate_html_dashboard
from fetch_prs import clean_snippet


import tempfile

class TestPilotTimesheet(unittest.TestCase):

    def test_extract_prs_from_subject(self):
        self.assertEqual(extract_prs_from_subject("feat: timesheet setup (#102)"), ["#102"])
        self.assertEqual(extract_prs_from_subject("fix: resolve bug in parser and close #14 and #15"), ["#14", "#15"])
        self.assertEqual(extract_prs_from_subject("chore: simple update"), [])

    def test_parse_ics_datetime(self):
        d, t = parse_ics_datetime("20261006T093000")
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
DTSTART:20261006T090000
DTEND:20261006T093000
END:VEVENT
BEGIN:VEVENT
SUMMARY:Sprint Review
DTSTART:20261006T140000
DTEND:20261006T150000
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

    def test_assign_items_zero_calendar_events_rule(self):
        """Section 3.2: If a day has no calendar events, still write ONE entry for that day."""
        commits = [
            {"repo": "timesheet", "time": "14:15", "subject": "feat: single block fallback", "prs": []},
            {"repo": "timesheet", "time": "16:30", "subject": "fix: test isolation", "prs": []}
        ]
        assigned = assign_items_to_blocks([], commits, [])
        self.assertEqual(len(assigned), 1, "Must produce exactly ONE entry when no calendar events exist")
        self.assertEqual(len(assigned[0]["commit_subjects"]), 2)
        self.assertEqual(assigned[0]["source"], "commits_prs")

    def test_assign_items_early_morning_commit(self):
        """Early morning commit before 09:00 should assign to the first block, not the afternoon block."""
        blocks = [
            {"title": "Morning Dev", "start_time": "09:00", "end_time": "12:00", "source": "cal"},
            {"title": "Afternoon Dev", "start_time": "13:30", "end_time": "18:00", "source": "cal"}
        ]
        commits = [
            {"repo": "timesheet", "time": "08:30", "subject": "feat: early start", "prs": []}
        ]
        assigned = assign_items_to_blocks(blocks, commits, [])
        self.assertIn("feat: early start", assigned[0]["commit_subjects"])
        self.assertEqual(len(assigned[1]["commit_subjects"]), 0)

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
        # Single concise topic must stay on one line without bullets
        self.assertIn("- **Description:** PRs: #101, #102 | Timesheet pipeline scaffolding and calendar integration", entry_md)
        self.assertNotIn("  - PRs:", entry_md)
        self.assertIn("- **Source Trace:**", entry_md)
        self.assertIn("Morning Sprint Block", entry_md)

    def test_format_single_entry_conditional_bullets(self):
        # Multiple topics -> PRs & primary topic on first line, subtopics as indented bullets
        entry_md = format_single_entry(
            date="2026-10-08",
            start_time="08:50",
            end_time="10:30",
            topic_summary="Workspace timesheet integration | Interactive workflow test runner | Comprehensive README documentation",
            prs=["#11", "#12"]
        )
        self.assertIn("- **Description:** PRs: #11, #12 | Workspace timesheet integration", entry_md)
        self.assertIn("  - Interactive workflow test runner", entry_md)
        self.assertIn("  - Comprehensive README documentation", entry_md)

        # Without PRs
        entry_no_prs = format_single_entry(
            date="2026-10-08",
            start_time="08:50",
            end_time="10:30",
            topic_summary="Workspace timesheet integration; Interactive test runner"
        )
        self.assertIn("- **Description:** Workspace timesheet integration", entry_no_prs)
        self.assertIn("  - Interactive test runner", entry_no_prs)

    def test_format_single_entry_reviews_and_comments(self):
        entry_md = format_single_entry(
            date="2026-10-08",
            start_time="13:00",
            end_time="15:00",
            topic_summary="Afternoon development",
            prs=["#18"],
            reviews=["PR #18 (APPROVED): Looks good to merge"],
            comments=["#19 comment by @anhdo-gradion: Ok"]
        )
        self.assertIn("  - *Reviews:* PR #18 (APPROVED): Looks good to merge", entry_md)
        self.assertIn("  - *Comments:* #19 comment by @anhdo-gradion: Ok", entry_md)

        # Omitted when empty
        entry_empty = format_single_entry(
            date="2026-10-08",
            start_time="13:00",
            end_time="15:00",
            topic_summary="Afternoon development"
        )
        self.assertNotIn("*Reviews:*", entry_empty)
        self.assertNotIn("*Comments:*", entry_empty)

    def test_clean_snippet(self):
        self.assertEqual(clean_snippet("Simple text"), "Simple text")
        long_text = "This is a very long comment text that definitely exceeds the seventy character maximum snippet length"
        snippet = clean_snippet(long_text, max_len=50)
        self.assertTrue(len(snippet) <= 50)
        self.assertTrue(snippet.endswith("..."))

    def test_format_header_clean_truncation(self):
        long_topic = "This is an extremely long topic summary that describes multiple architectural improvements without running on forever in the markdown heading"
        entry_md = format_single_entry(
            date="2026-10-06",
            start_time="09:00",
            end_time="12:00",
            topic_summary=long_topic
        )
        first_line = entry_md.splitlines()[0]
        self.assertTrue(first_line.endswith("..."))
        # Ensure it didn't cut words awkwardly
        self.assertNotIn("without...", first_line)

    def test_save_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_log_path = Path(tmpdir) / "timesheet_test.md"

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

            save_or_update_block_entry(test_entry, custom_log_path=test_log_path)

            updated_entry = dict(test_entry)
            updated_entry["topic_summary"] = "Updated run without duplicates"
            save_or_update_block_entry(updated_entry, custom_log_path=test_log_path)

            content = test_log_path.read_text(encoding="utf-8")
            occurrences = content.count("### 2026-10-06 | 09:00 - 12:00")
            self.assertEqual(occurrences, 1)
            self.assertIn("Updated run without duplicates", content)

    def test_token_charts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_csv = Path(tmpdir) / "test_tokens.csv"
            # Write a dummy test record
            test_csv.write_text(
                "date,session_id,input_tokens,output_tokens,cache_tokens,total_tokens,workflow_version,notes\n"
                "2026-10-06,test-01,150,80,0,230,v1.0,Test run\n",
                encoding="utf-8"
            )

            chart_str = generate_ascii_chart(custom_csv=test_csv)
            self.assertIn("2026-10-06", chart_str)
            self.assertIn("230", chart_str)
            self.assertIn("[PASS]", chart_str)

            test_html = Path(tmpdir) / "test_chart.html"
            out_path = generate_html_dashboard(custom_csv=test_csv, output_html=test_html)
            self.assertTrue(out_path.exists())
            html_text = out_path.read_text(encoding="utf-8")
            self.assertIn("2026-10-06", html_text)
            self.assertIn("230", html_text)


if __name__ == "__main__":
    unittest.main()

