---
name: pilot-timesheet-logger
description: Generates and records daily internship timesheet entries from git commits, pull requests, and Google Calendar events into standard timesheet format with minimal token consumption.
---

# Pilot Timesheet Logger Skill

A Claude Code / Antigravity skill for generating and maintaining daily personal timesheet entries from real data sources: Git commits, Pull Requests, and Google Calendar events.

## When Claude / Antigravity Should Use This Skill
Activate this skill whenever the user says or types:
- `log` or `/log` or `/timesheet`
- `log test`, `test log`, `/log:test`, or `log --dry-run` (triggers dry-run test runner)
- *"log today's work"* or *"log my work for today"*
- *"record my timesheet"* or *"fill my timesheet"*
- *"generate daily log"* or *"run timesheet logger"*
- *"test timesheet workflow"* or *"see and test the AI workflow"*
- *"log yesterday's work"* (with an explicit date)

---

## Daily Execution Protocol for Claude / Antigravity

When activated by `log`, immediately execute the master pipeline with workspace synchronization:
```bash
python3 scripts/run_pipeline.py --sync-workspace
```
*(If logging for a specific past date, append `--date YYYY-MM-DD`)*

Alternatively, if custom topic synthesis is performed:

### Step 1: Extract & Aggregate Data [Script]
Run the aggregation script via the Bash tool to extract today's git commits, PRs, and calendar blocks into a minimal structured JSON payload:
```bash
python3 scripts/prepare_prompt.py
```
*(If logging for a specific past date, append `--date YYYY-MM-DD`)*

### Step 2: Topic Synthesis [AI - Judgment Step]
Inspect the JSON output returned by `prepare_prompt.py`. For each block:
- Review the `commit_subjects` and `title` (calendar event).
- Synthesize them into **one concise, professional engineering topic sentence** (e.g., *"Personal pilot timesheet logger implementation, GitHub PR tracking, and token usage analytics"*).
- Combine multiple minor commits into high-level themes; do not list raw individual commit messages.

### Step 3: Format & Persist Entry [Script]
Pass your synthesized topic strings to the pipeline orchestrator to deterministically format markdown and idempotently save to `logs/timesheet_YYYY-MM.md` and sync with Gradion Workspace:
```bash
python3 scripts/run_pipeline.py --sync-workspace --topics-json '{"1": "<Synthesized Topic Sentence>"}'
```

### Step 4: Record Token Usage [Script]
Log session tokens to maintain evidence for token optimization tracking:
```bash
python3 scripts/track_tokens.py --record --date <YYYY-MM-DD> --input-tokens <PROMPT_TOKENS> --output-tokens <COMPLETION_TOKENS>
```

### Step 5: Report Summary to User
Show the user:
1. The formatted timesheet entry that was appended or updated.
2. The Gradion Workspace synchronization status.
3. The token usage confirmation (and chart status via `python3 scripts/track_tokens.py --chart`).
4. Note any anomalies in `logs/improvement_log.md` if an event was missing or unclear.
