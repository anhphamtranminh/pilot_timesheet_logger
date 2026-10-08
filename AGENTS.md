# Pilot Timesheet Logger Instructions

This workspace contains the automated daily timesheet logger for personal pilot tracking, extracting commits, pull requests, and calendar blocks into compliant daily entries.

---

## Quick Trigger: `log`
Whenever the user types `log`, `/log`, `/timesheet`, or asks to "log today's work" / "record timesheet":
1. **Immediately execute the pipeline in dry-run preview mode in a single command without asking preliminary questions and without running git status, git branch, ls, or exploratory commands:**
   ```bash
   python3 scripts/run_pipeline.py --dry-run
   ```
   *(If logging for a specific past date, append `--date YYYY-MM-DD`)*

2. **Present the formatted Markdown preview of the day's time blocks to the user.**

3. **Ask for confirmation using `ask_question`:**
   - Question: "Would you like to write these entries to the timesheet and sync to Gradion Workspace?"
   - Options:
     - "(Recommended) Yes, log to timesheet and sync to Gradion Workspace"
     - "No, cancel without making changes"

4. **Upon user confirmation, execute live persistence with workspace synchronization:**
   ```bash
   python3 scripts/run_pipeline.py --sync-workspace
   ```
   *(If logging for a specific past date, append `--date YYYY-MM-DD`)*

   *(Optional topic synthesis: if custom synthesized topics are requested, pass `--topics-json '{"1": "<Synthesized Topic Sentence>"}'` to `run_pipeline.py --sync-workspace`)*

5. **If the user cancels, stop execution immediately and report that no changes were made.**

*(Note: If the user provides `--force`, `-y`, or explicitly instructs to log without confirmation, steps 1-3 are bypassed and live persistence runs directly).*

### Report Summary to User
Show the user:
1. The formatted markdown entry appended/updated in `logs/timesheet_YYYY-MM.md`.
2. Gradion Workspace synchronization status.
3. The token usage confirmation and ASCII status chart (`python3 scripts/track_tokens.py --chart`).
4. Note any anomalies in `logs/improvement_log.md` if an event was missing or unclear.

---

## Quick Test Trigger: `log test` / `test log` / `log --dry-run`
Whenever the user types `log test`, `test log`, `/log:test`, `log --dry-run`, or asks to "test the logging workflow" / "dry run timesheet" / "test workflow on agy":
**Immediately execute the visual test runner in dry-run mode without running git status, git branch, ls, or any exploratory inspection commands:**
```bash
python3 scripts/test_workflow.py
```
*(If testing for a specific date, append `--date YYYY-MM-DD`)*

Present the 5-step visual breakdown to the user, highlighting data extraction, prompt tokens, topic synthesis, markdown preview, and token budget compliance without modifying any log files or calling mutation APIs.

---

## Skill Reference & Architectural Boundaries
- Canonical Skill Definition: `skills/pilot-timesheet-logger/SKILL.md`
- Deterministic Workflow Runbook: `skills/pilot-timesheet-logger/workflow.md`
- Token Budget: Target daily prompt tokens < 200, total session < 350 tokens.
- Git Workflow: Adhere strictly to *"One task = one small branch = one focused PR"*. Do not commit directly to `main`.
