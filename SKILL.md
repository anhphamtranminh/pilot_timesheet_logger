---
name: pilot-timesheet-logger
description: Automatically logs daily internship work from git commits, pull requests, and Google Calendar events into Section 3.2-compliant timesheet entries with minimal token consumption.
---

# Pilot Timesheet Logger Skill

A skill for generating and maintaining daily personal timesheet entries from real data sources: Git commits, Pull Requests, and Google Calendar events.

## When to Use This Skill
- When the user asks to "log today's work", "record my timesheet", "generate daily log", or "run timesheet logger".
- Run daily at the end of each working day (scheduled or manual trigger).

## Core Capabilities
1. **Automated Git Harvesting:** Scans authored commits and PRs across repos for today.
2. **Calendar Ingestion:** Reads Google Calendar events (.ics feed, local file, or default blocks).
3. **Topic Grouping:** Compresses small commits into cohesive topic summaries per time block.
4. **Idempotent Logging:** Appends or updates entries in `logs/timesheet_YYYY-MM.md` without duplicating time blocks.
5. **Token Measurement:** Logs token usage in `logs/token_usage.csv` to ensure adherence to the < 350 token daily budget.

## Execution Procedure

When invoked, follow the procedure defined in `workflow.md`:

1. **Run the deterministic aggregation script:**
   ```bash
   python3 scripts/prepare_prompt.py --date <YYYY-MM-DD>
   ```
2. **Topic Grouping (Judgment):**
   - For each block in the output, review the commit subjects and calendar event title.
   - Formulate a concise, high-level topic description (e.g. *"Frontend contract refactoring and unit test coverage"*).
   - Keep each description to 1 concise sentence.
3. **Save the formatted entry:**
   ```bash
   python3 scripts/run_pipeline.py --date <YYYY-MM-DD>
   ```
4. **Record token usage:**
   ```bash
   python3 scripts/track_tokens.py --record --date <YYYY-MM-DD> --input-tokens <IN> --output-tokens <OUT>
   ```
5. **Report to User:**
   - Display the logged entries and the total tokens consumed.
   - Note any anomalies or items needing review.

## File Structure
- `config.json`: Configuration for tracked repos, author name, and calendar feeds.
- `workflow.md`: Detailed daily procedure with `[Script]` vs `[AI]` breakdown.
- `scripts/`: Deterministic collection and formatting pipeline.
- `logs/`: Persistent timesheet records, token statistics, and improvement notes.
