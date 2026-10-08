#!/usr/bin/env python3
"""Unit tests for overlapping blocks, empty block updates, and edit_time sync."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from prepare_prompt import assign_items_to_blocks
from save_entry import save_or_update_block_entry
from fetch_workspace_timesheet import (
    edit_workspace_timesheet_entry,
    post_workspace_timesheet_entry
)


class TestOverlappingBlocks(unittest.TestCase):
    """Test suite for overlapping blocks and empty block commit/PR synchronization."""

    def test_overlapping_meeting_and_dev_block(self):
        """Commits should be assigned to dev blocks rather than overlapping meeting blocks."""
        blocks = [
            {"title": "Daily Standup & Sync", "start_time": "09:30", "end_time": "10:30", "source": "calendar"},
            {"title": "Core Feature Development", "start_time": "09:00", "end_time": "12:00", "source": "calendar"}
        ]
        commits = [
            {"time": "10:00", "subject": "feat(core): implement core logic", "repo": "pilot_timesheet", "prs": ["#10"]}
        ]
        prs = []

        assigned = assign_items_to_blocks(blocks, commits, prs)
        self.assertEqual(len(assigned), 2)

        standup_block = next(b for b in assigned if "Standup" in b["title"])
        dev_block = next(b for b in assigned if "Core Feature" in b["title"])

        # Dev block should get the commit, standup block should remain free of code commit
        self.assertEqual(len(dev_block["commit_subjects"]), 1)
        self.assertIn("feat(core): implement core logic", dev_block["commit_subjects"])
        self.assertEqual(len(standup_block["commit_subjects"]), 0)
        self.assertIn("#10", dev_block["prs"])

    def test_overlapping_empty_block_prioritization(self):
        """When two dev blocks overlap, an empty block should be preferred so it gets populated."""
        blocks = [
            {"title": "Morning Work Block", "start_time": "09:00", "end_time": "12:00", "source": "calendar"},
            {"title": "Task Implementation Block", "start_time": "10:00", "end_time": "11:30", "source": "calendar"}
        ]
        # First commit at 09:15 goes to Morning Work Block
        # Second commit at 10:30 falls into both; Task Implementation Block is empty so it should get it
        commits = [
            {"time": "09:15", "subject": "chore: scaffold project structure", "repo": "pilot_timesheet", "prs": []},
            {"time": "10:30", "subject": "feat: implement task parser", "repo": "pilot_timesheet", "prs": []}
        ]
        prs = []

        assigned = assign_items_to_blocks(blocks, commits, prs)
        morning_block = assigned[0]
        task_block = assigned[1]

        self.assertEqual(len(morning_block["commit_subjects"]), 1)
        self.assertIn("chore: scaffold project structure", morning_block["commit_subjects"])

        self.assertEqual(len(task_block["commit_subjects"]), 1)
        self.assertIn("feat: implement task parser", task_block["commit_subjects"])

    def test_pr_assigned_to_empty_block_via_timestamp(self):
        """A PR with action time falling in an empty block should be assigned to that block."""
        blocks = [
            {"title": "Morning Development", "start_time": "09:00", "end_time": "12:00", "source": "calendar"},
            {"title": "Afternoon PR Review & QA", "start_time": "14:00", "end_time": "16:00", "source": "calendar"}
        ]
        commits = [
            {"time": "10:00", "subject": "feat: morning commit", "repo": "pilot_timesheet", "prs": []}
        ]
        prs = [
            {"number": "#10", "title": "feat: handle overlapping blocks", "repo": "pilot_timesheet", "status": "opened", "time": "14:30"}
        ]

        assigned = assign_items_to_blocks(blocks, commits, prs)
        morning_block = assigned[0]
        review_block = assigned[1]

        self.assertEqual(morning_block["commit_subjects"], ["feat: morning commit"])
        self.assertEqual(len(review_block["commit_subjects"]), 0)  # Empty of commits
        self.assertIn("#10", review_block["prs"])  # But received the PR based on time

    def test_preserve_entry_id_and_workspace_metadata(self):
        """assign_items_to_blocks must preserve entry_id, project, and status from workspace blocks."""
        blocks = [
            {
                "title": "Existing Workspace Task",
                "start_time": "09:00",
                "end_time": "11:00",
                "source": "workspace_timesheet",
                "entry_id": "uuid-1234-abcd",
                "project": "Gradion Academy",
                "status": "submitted"
            }
        ]
        commits = [{"time": "09:30", "subject": "fix: bugfix", "repo": "pilot_timesheet", "prs": []}]
        prs = []

        assigned = assign_items_to_blocks(blocks, commits, prs)
        self.assertEqual(len(assigned), 1)
        b = assigned[0]
        self.assertEqual(b.get("entry_id"), "uuid-1234-abcd")
        self.assertEqual(b.get("project"), "Gradion Academy")
        self.assertEqual(b.get("status"), "submitted")

    def test_save_or_update_replaces_overlapping_block(self):
        """save_or_update_block_entry should replace an overlapping block when time is adjusted."""
        test_log = Path("/tmp/test_timesheet_overlap.md")
        if test_log.exists():
            test_log.unlink()

        # Initial entry from 16:00 to 18:00
        initial_entry = {
            "date": "2026-10-07",
            "start_time": "16:00",
            "end_time": "18:00",
            "topic_summary": "Initial partial development",
            "prs": ["#8"],
            "source_title": "Afternoon Development",
            "repos": ["pilot_timesheet"],
            "commit_subjects": ["feat: initial work"]
        }
        save_or_update_block_entry(initial_entry, custom_log_path=test_log)
        content_1 = test_log.read_text(encoding="utf-8")
        self.assertIn("16:00 - 18:00", content_1)
        self.assertIn("Initial partial development", content_1)

        # Extended/adjusted block from 16:00 to 18:58 (same start time, overlapping interval)
        updated_entry = {
            "date": "2026-10-07",
            "start_time": "16:00",
            "end_time": "18:58",
            "topic_summary": "Extended development and workspace integration",
            "prs": ["#8", "#10"],
            "source_title": "Afternoon Development",
            "repos": ["pilot_timesheet"],
            "commit_subjects": ["feat: initial work", "feat: workspace integration"]
        }
        save_or_update_block_entry(updated_entry, custom_log_path=test_log)
        content_2 = test_log.read_text(encoding="utf-8")

        # Must have updated the block without duplicating it
        self.assertIn("16:00 - 18:58", content_2)
        self.assertIn("Extended development and workspace integration", content_2)
        self.assertNotIn("16:00 - 18:00", content_2)
        self.assertEqual(content_2.count("### 2026-10-07"), 1)

        if test_log.exists():
            test_log.unlink()

    def test_save_or_update_cleans_placeholder_entry(self):
        """save_or_update_block_entry removes full-day placeholder when discrete sub-blocks are saved."""
        test_log = Path("/tmp/test_timesheet_placeholder.md")
        if test_log.exists():
            test_log.unlink()

        # Initial placeholder entry 09:00 - 18:00 Daily Development
        placeholder = {
            "date": "2026-10-07",
            "start_time": "09:00",
            "end_time": "18:00",
            "topic_summary": "Daily Development fallback",
            "prs": [],
            "source_title": "Daily Development",
            "repos": ["pilot_timesheet"],
            "commit_subjects": ["feat: some commit"]
        }
        save_or_update_block_entry(placeholder, custom_log_path=test_log)
        content_1 = test_log.read_text(encoding="utf-8")
        self.assertIn("09:00 - 18:00", content_1)

        # Saving first discrete sub-block: 09:00 - 11:00
        discrete_block = {
            "date": "2026-10-07",
            "start_time": "09:00",
            "end_time": "11:00",
            "topic_summary": "Morning architectural research",
            "prs": ["#2"],
            "source_title": "Morning Focus",
            "repos": ["pilot_timesheet"],
            "commit_subjects": ["feat: architecture"]
        }
        save_or_update_block_entry(discrete_block, custom_log_path=test_log)
        content_2 = test_log.read_text(encoding="utf-8")

        self.assertIn("09:00 - 11:00", content_2)
        self.assertIn("Morning architectural research", content_2)
        self.assertNotIn("09:00 - 18:00", content_2)

        if test_log.exists():
            test_log.unlink()

    @patch("fetch_workspace_timesheet.resolve_gradion_token", return_value="dummy-token")
    @patch("fetch_workspace_timesheet.make_gradion_request")
    def test_post_workspace_timesheet_calls_edit_time_when_entry_id_present(self, mock_req, mock_token):
        """When entry_id is present, post_workspace_timesheet_entry must directly invoke edit_time."""
        mock_req.return_value = {"isError": False}

        entry = {
            "date": "2026-10-07",
            "start_time": "09:00",
            "end_time": "11:00",
            "topic_summary": "Synthesized topic sentence",
            "prs": ["#1", "#10"],
            "entry_id": "uuid-entry-1234"
        }

        success = post_workspace_timesheet_entry(entry)
        self.assertTrue(success)

        # Check call endpoint and payload
        mock_req.assert_called_once()
        endpoint, token = mock_req.call_args[0][:2]
        kwargs = mock_req.call_args[1]
        self.assertIn("edit_time", endpoint)
        self.assertEqual(kwargs.get("method"), "POST")
        self.assertEqual(kwargs["data"]["arguments"]["entryId"], "uuid-entry-1234")
        self.assertIn("PRs: #1, #10", kwargs["data"]["arguments"]["description"])

    @patch("fetch_workspace_timesheet.resolve_gradion_token", return_value="dummy-token")
    @patch("fetch_workspace_timesheet.fetch_workspace_timesheet_blocks")
    @patch("fetch_workspace_timesheet.make_gradion_request")
    def test_post_workspace_timesheet_fallback_on_overlap_collision(self, mock_req, mock_fetch_blocks, mock_token):
        """When log_time errors with overlap, it must resolve the overlapping entry_id and edit it."""
        # First call: log_time fails with overlap
        # Second call: edit_time succeeds
        mock_req.side_effect = [
            {"isError": True, "content": [{"text": "Time range overlaps an existing entry"}]},
            {"isError": False, "content": []}
        ]
        mock_fetch_blocks.return_value = [
            {
                "title": "Existing block",
                "start_time": "09:00",
                "end_time": "12:00",
                "entry_id": "overlapping-uuid-999"
            }
        ]

        entry = {
            "date": "2026-10-07",
            "start_time": "09:00",
            "end_time": "12:00",
            "topic_summary": "Resolved overlapping block topic",
            "prs": ["#10"]
        }

        success = post_workspace_timesheet_entry(entry)
        self.assertTrue(success)

        # Verified two API calls: log_time then edit_time
        self.assertEqual(mock_req.call_count, 2)
        call_1_endpoint = mock_req.call_args_list[0][0][0]
        call_2_endpoint = mock_req.call_args_list[1][0][0]
        self.assertIn("log_time", call_1_endpoint)
        self.assertIn("edit_time", call_2_endpoint)

        call_2_args = mock_req.call_args_list[1][1]["data"]["arguments"]
        self.assertEqual(call_2_args["entryId"], "overlapping-uuid-999")
        self.assertIn("Resolved overlapping block topic", call_2_args["description"])

    @patch("fetch_workspace_timesheet.resolve_gradion_token", return_value="dummy-token")
    @patch("fetch_workspace_timesheet.make_gradion_request")
    def test_post_workspace_timesheet_includes_commits_in_description(self, mock_req, mock_token):
        """post_workspace_timesheet_entry must include both Commits and PRs in the description."""
        mock_req.return_value = {"isError": False}

        entry = {
            "date": "2026-10-07",
            "start_time": "13:00",
            "end_time": "14:30",
            "topic_summary": "Architecture refactor",
            "commit_subjects": ["refactor(skills): remove duplicates (fixes #3)"],
            "prs": ["#3"],
            "entry_id": "uuid-entry-5678"
        }

        success = post_workspace_timesheet_entry(entry)
        self.assertTrue(success)

        desc = mock_req.call_args[1]["data"]["arguments"]["description"]
        self.assertIn("Architecture refactor", desc)
        self.assertIn("Commits: refactor(skills): remove duplicates (fixes #3)", desc)
        self.assertIn("PRs: #3", desc)


if __name__ == "__main__":
    unittest.main()
