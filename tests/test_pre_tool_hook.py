#!/usr/bin/env python3
"""Unit tests for Antigravity PreToolUse hook script."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
HOOK_SCRIPT = ROOT_DIR / "scripts" / "pre_tool_hook.py"


class TestPreToolHook(unittest.TestCase):
    def run_hook(self, payload: dict) -> dict:
        proc = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True
        )
        return json.loads(proc.stdout.strip())

    def test_allow_run_pipeline(self):
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {
                    "CommandLine": "python3 /Users/anh.phamminh/Documents/pilot_timesheet/scripts/run_pipeline.py --sync-workspace"
                }
            }
        }
        res = self.run_hook(payload)
        self.assertEqual(res.get("decision"), "allow")

    def test_allow_test_workflow(self):
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {
                    "CommandLine": "python3 scripts/test_workflow.py"
                }
            }
        }
        res = self.run_hook(payload)
        self.assertEqual(res.get("decision"), "allow")

    def test_allow_track_tokens(self):
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {
                    "CommandLine": "python3 scripts/track_tokens.py --chart"
                }
            }
        }
        res = self.run_hook(payload)
        self.assertEqual(res.get("decision"), "allow")

    def test_ask_other_command(self):
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {
                    "CommandLine": "rm -rf /"
                }
            }
        }
        res = self.run_hook(payload)
        self.assertEqual(res.get("decision"), "ask")

    def test_ask_other_tool(self):
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "/tmp/test.txt"
                }
            }
        }
        res = self.run_hook(payload)
        self.assertEqual(res.get("decision"), "ask")


if __name__ == "__main__":
    unittest.main()
