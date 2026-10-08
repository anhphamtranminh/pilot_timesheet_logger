#!/usr/bin/env python3
"""Unit tests verifying Claude Code Skill packaging and workflow compliance (Section 3.5 & Section 6)."""

import json
import re
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from prepare_prompt import generate_ai_payload
from format_entry import format_single_entry
from run_pipeline import run_daily_timesheet


class TestSkillPackaging(unittest.TestCase):
    """Test suite for validating skill structure, YAML frontmatter, and workflow tags."""

    def test_skill_folder_and_files_exist(self):
        """Verify skill folder and required SKILL.md and workflow.md files exist."""
        skill_dir = PROJECT_ROOT / "skills" / "pilot-timesheet-logger"
        self.assertTrue(skill_dir.is_dir(), "skills/pilot-timesheet-logger directory must exist")

        skill_md = skill_dir / "SKILL.md"
        workflow_md = skill_dir / "workflow.md"
        self.assertTrue(skill_md.is_file(), "SKILL.md must exist in skill folder")
        self.assertTrue(workflow_md.is_file(), "workflow.md must exist in skill folder")

        # Also check .claude/skills and .agents/skills mirroring
        claude_skill_dir = PROJECT_ROOT / ".claude" / "skills" / "pilot-timesheet-logger"
        self.assertTrue(claude_skill_dir.is_dir(), ".claude/skills/pilot-timesheet-logger must exist")

        agents_skill_dir = PROJECT_ROOT / ".agents" / "skills" / "pilot-timesheet-logger"
        self.assertTrue(agents_skill_dir.is_dir(), ".agents/skills/pilot-timesheet-logger must exist")

        agents_md = PROJECT_ROOT / "AGENTS.md"
        self.assertTrue(agents_md.is_file(), "AGENTS.md must exist in root")
        self.assertIn("log", agents_md.read_text(encoding="utf-8"))

    def test_skill_md_yaml_frontmatter(self):
        """Verify SKILL.md has valid YAML frontmatter with name and description."""
        skill_md = PROJECT_ROOT / "skills" / "pilot-timesheet-logger" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")

        self.assertTrue(content.startswith("---"), "SKILL.md must start with YAML frontmatter delimiter '---'")
        match = re.search(r"^name:\s*([\w\-]+)", content, re.MULTILINE)
        self.assertIsNotNone(match, "SKILL.md frontmatter must contain a 'name:' field")
        self.assertEqual(match.group(1), "pilot-timesheet-logger")

        desc_match = re.search(r"^description:\s*(.+)", content, re.MULTILINE)
        self.assertIsNotNone(desc_match, "SKILL.md frontmatter must contain a 'description:' field")

    def test_workflow_md_script_and_ai_tags(self):
        """Verify workflow.md tags every step with [Script] or [AI] and declares token budget."""
        workflow_md = PROJECT_ROOT / "skills" / "pilot-timesheet-logger" / "workflow.md"
        content = workflow_md.read_text(encoding="utf-8")

        self.assertIn("[Script]", content, "workflow.md must contain [Script] steps")
        self.assertIn("[AI]", content, "workflow.md must contain [AI] steps")
        self.assertIn("350", content, "workflow.md must declare target token budget (< 350 tokens)")

    def test_skill_pipeline_execution_contract(self):
        """Simulate Claude running the skill: prepare_prompt -> synthesize topic -> run_pipeline."""
        payload = generate_ai_payload("2026-10-06")
        self.assertIn("blocks", payload)
        self.assertIn("estimated_input_tokens", payload)
        self.assertLess(payload["estimated_input_tokens"], 350, "Prompt tokens must be within budget")

        # Simulate Claude providing AI synthesized topic for block 1
        ai_topics = {"1": "Refactored timesheet logger and packaged skill for Claude Code"}
        entries = run_daily_timesheet(target_date="2026-10-06", dry_run=True, custom_topics=ai_topics)

        self.assertTrue(len(entries) >= 1)
        entry = entries[0]
        self.assertEqual(entry["date"], "2026-10-06")
        self.assertEqual(entry["topic_summary"], "Refactored timesheet logger and packaged skill for Claude Code")

        # Format markdown and check Section 3.2 fields
        formatted = format_single_entry(
            date=entry["date"],
            start_time=entry["start_time"],
            end_time=entry["end_time"],
            topic_summary=entry["topic_summary"],
            prs=entry["prs"],
            source_title=entry["source_title"],
            repos=entry["repos"],
            commit_subjects=entry["commit_subjects"]
        )

        self.assertIn("### 2026-10-06 |", formatted)
        self.assertIn("- **Date:** 2026-10-06", formatted)
        self.assertIn("- **Start time:**", formatted)
        self.assertIn("- **End time:**", formatted)
        self.assertIn("- **Description:**", formatted)
        self.assertIn("- **Source Trace:**", formatted)


if __name__ == "__main__":
    unittest.main()
