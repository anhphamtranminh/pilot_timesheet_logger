#!/usr/bin/env python3
"""Unit tests verifying Gradion Workspace Timesheet block data collection."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from fetch_workspace_timesheet import (
    resolve_gradion_token,
    make_gradion_request,
    fetch_workspace_timesheet_blocks,
)
from fetch_calendar import fetch_all_events


class TestWorkspaceTimesheet(unittest.TestCase):
    """Test suite for Gradion Workspace timesheet API connector."""

    def test_token_resolution_from_env(self):
        """Verify token is correctly picked up from GRADION_API_TOKEN environment variable."""
        with patch.dict("os.environ", {"GRADION_API_TOKEN": "pat_test_token_123"}):
            token = resolve_gradion_token()
            self.assertEqual(token, "pat_test_token_123")

    def test_token_resolution_missing(self):
        """Verify empty string returned when no token is configured."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="")
                with patch("config.load_config", return_value={}):
                    token = resolve_gradion_token()
                    self.assertEqual(token, "")

    @patch("fetch_workspace_timesheet.resolve_gradion_token", return_value="pat_test_mock")
    @patch("fetch_workspace_timesheet.make_gradion_request")
    def test_fetch_workspace_timesheet_blocks_from_export(self, mock_request, mock_token):
        """Verify parsing of timesheet export entries for a target date."""
        def mock_api(endpoint, token, method="GET", data=None):
            if endpoint == "/api/auth/me":
                return {"id": "usr_123", "workspace_id": "ws_abc", "display_name": "Anh Pham"}
            elif endpoint == "/api/me/apps/export":
                return {
                    "apps": [
                        {
                            "slug": "timesheet",
                            "name": "Timesheet App",
                            "datasets": [{"dataset": "entries"}]
                        }
                    ]
                }
            elif "/api/me/apps/timesheet/export/entries" in endpoint:
                return {
                    "rows": [
                        {
                            "date": "2026-10-07",
                            "start_time": "09:00",
                            "end_time": "12:00",
                            "task": "Core Pipeline Integration",
                            "project": "Personal Pilot"
                        },
                        {
                            "date": "2026-10-07",
                            "start_time": "13:30",
                            "end_time": "18:00",
                            "task": "Antigravity & Claude Skill Testing",
                            "project": "Personal Pilot"
                        },
                        {
                            "date": "2026-10-06",
                            "start_time": "09:00",
                            "end_time": "18:00",
                            "task": "Previous Day Work",
                            "project": "Personal Pilot"
                        }
                    ]
                }
            return {}

        mock_request.side_effect = mock_api

        blocks = fetch_workspace_timesheet_blocks("2026-10-07")
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["start_time"], "09:00")
        self.assertEqual(blocks[0]["end_time"], "12:00")
        self.assertEqual(blocks[0]["title"], "Core Pipeline Integration")
        self.assertEqual(blocks[0]["source"], "workspace_timesheet")

        self.assertEqual(blocks[1]["start_time"], "13:30")
        self.assertEqual(blocks[1]["end_time"], "18:00")
        self.assertEqual(blocks[1]["title"], "Antigravity & Claude Skill Testing")

    @patch("fetch_workspace_timesheet.resolve_gradion_token", return_value="pat_test_mock")
    @patch("fetch_workspace_timesheet.make_gradion_request")
    def test_fetch_workspace_timesheet_handles_401_gracefully(self, mock_request, mock_token):
        """Verify HTTP 401 returns empty list without raising unhandled exception."""
        mock_request.side_effect = urllib.error.HTTPError(
            url="https://workspace.gradion.com/api/auth/me",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None
        )

        blocks = fetch_workspace_timesheet_blocks("2026-10-07")
        self.assertEqual(blocks, [])

    @patch("fetch_workspace_timesheet.fetch_workspace_timesheet_blocks")
    def test_fetch_all_events_prioritizes_workspace(self, mock_ws):
        """Verify fetch_all_events prioritizes Gradion Workspace blocks over calendar."""
        mock_ws.return_value = [
            {"title": "Morning Dev", "start_time": "09:00", "end_time": "12:00", "source": "workspace_timesheet"}
        ]
        events = fetch_all_events("2026-10-07")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Morning Dev")
        self.assertEqual(events[0]["source"], "workspace_timesheet")


if __name__ == "__main__":
    unittest.main()
