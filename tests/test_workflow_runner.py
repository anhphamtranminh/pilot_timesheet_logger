#!/usr/bin/env python3
"""[Tests] Unit tests for the AI workflow test runner and CLI triggers."""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from test_workflow import run_workflow_test, main as workflow_main


class TestWorkflowRunner(unittest.TestCase):
    """Test suite for test_workflow.py and dry-run execution."""

    def test_log_test_script_exists_and_is_executable(self):
        """Ensure the root log-test helper script exists and is executable."""
        root = Path(__file__).resolve().parent.parent
        log_test = root / "log-test"
        self.assertTrue(log_test.exists(), "log-test script does not exist in project root")
        self.assertTrue(os.access(log_test, os.X_OK), "log-test script is not executable")

    def test_dry_run_workflow_execution(self):
        """Test that running the workflow in dry-run mode produces formatted 5-step output without modifying files."""
        out = io.StringIO()
        with redirect_stdout(out):
            run_workflow_test("2026-10-06", live=False)

        output = out.getvalue()
        self.assertIn("[Step 1/5] Extracting Data", output)
        self.assertIn("[Step 2/5] Minimal AI Input Payload", output)
        self.assertIn("[Step 3/5] AI Topic Synthesis", output)
        self.assertIn("[Step 4/5] Formatting Standard Markdown Entries", output)
        self.assertIn("[Step 5/5] Token Budget & Performance Metrics", output)
        self.assertIn("DRY-RUN SIMULATION", output)
        self.assertIn("Dry run completed successfully", output)

    def test_workflow_with_custom_topics(self):
        """Test workflow execution with custom synthesized topics provided by AI/user."""
        custom_topics = {
            "1": "Custom synthesized engineering task summary for block 1"
        }
        out = io.StringIO()
        with redirect_stdout(out):
            run_workflow_test("2026-10-06", custom_topics=custom_topics, live=False)

        output = out.getvalue()
        self.assertIn("Custom synthesized engineering task summary for block 1", output)

    @patch("sys.argv", ["test_workflow.py", "--date", "2026-10-06", "--topics-json", '{"1": "CLI parsed topic"}'])
    def test_main_cli_execution(self):
        """Test main() entrypoint parsing arguments and running the test workflow."""
        out = io.StringIO()
        with redirect_stdout(out):
            workflow_main()

        output = out.getvalue()
        self.assertIn("Target Date", output)
        self.assertIn("2026-10-06", output)
        self.assertIn("CLI parsed topic", output)

    def test_resolve_target_date(self):
        """Test resolve_target_date for explicit dates, relative keywords, and defaults."""
        import datetime
        from config import resolve_target_date

        today = datetime.date.today().isoformat()
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

        self.assertEqual(resolve_target_date("2026-10-07"), "2026-10-07")
        self.assertEqual(resolve_target_date("yesterday"), yesterday)
        self.assertEqual(resolve_target_date("YESTERDAY"), yesterday)
        self.assertEqual(resolve_target_date("today"), today)
        self.assertEqual(resolve_target_date(""), today)
        self.assertEqual(resolve_target_date(None), today)

    @patch("sys.argv", ["test_workflow.py", "2026-10-06"])
    def test_main_cli_positional_date(self):
        """Test that positional date argument without --date works seamlessly."""
        out = io.StringIO()
        with redirect_stdout(out):
            workflow_main()
        output = out.getvalue()
        self.assertIn("Target Date", output)
        self.assertIn("2026-10-06", output)

    @patch("sys.argv", ["test_workflow.py", "yesterday"])
    def test_main_cli_yesterday_date(self):
        """Test that 'yesterday' positional argument resolves and runs."""
        import datetime
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        out = io.StringIO()
        with redirect_stdout(out):
            workflow_main()
        output = out.getvalue()
        self.assertIn("Target Date", output)
        self.assertIn(yesterday, output)

    @patch("run_pipeline.run_daily_timesheet")
    def test_pipeline_main_positional_date(self, mock_run):
        """Test that run_pipeline.py accepts positional date argument."""
        from run_pipeline import main as pipeline_main
        with patch("sys.argv", ["run_pipeline.py", "--dry-run", "2026-10-06"]):
            pipeline_main()
        mock_run.assert_called_once_with("2026-10-06", True, None, False)

    @patch("run_pipeline.run_daily_timesheet")
    def test_pipeline_main_yesterday_date(self, mock_run):
        """Test that run_pipeline.py resolves 'yesterday' positional argument."""
        import datetime
        from run_pipeline import main as pipeline_main
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        with patch("sys.argv", ["run_pipeline.py", "--sync-workspace", "yesterday"]):
            pipeline_main()
        mock_run.assert_called_once_with(yesterday, False, None, True)


if __name__ == "__main__":
    unittest.main()
