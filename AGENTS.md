# Pilot Timesheet Logger Instructions

This workspace contains the automated daily timesheet logger for personal pilot tracking, extracting commits, pull requests, and calendar blocks into compliant Section 3.2 daily entries.

---

## ⚡ Quick Trigger: `log`
Whenever the user types `log`, `/log`, `/timesheet`, or asks to "log today's work" / "record timesheet":
**Immediately execute the 5-step daily logging workflow below without asking preliminary or clarifying questions.**

### Step 1: Extract Daily Data [Script]
Run the extraction script to aggregate today's git commits, PRs, and calendar blocks into a minimal JSON payload:
```bash
python3 scripts/prepare_prompt.py
```
*(If logging for a specific past date, append `--date YYYY-MM-DD`)*

### Step 2: Topic Synthesis [AI - Judgment Step]
Inspect the JSON output returned by `prepare_prompt.py`. For each block:
- Review the `commit_subjects` and calendar `title`.
- Synthesize them into **one concise, professional engineering topic sentence** (e.g., *"Multi-repo commit harvesting, timezone-aware PR matching, and token usage optimization"*).
- Combine minor commits into high-level themes; do not regurgitate raw commit lists.

### Step 3: Format & Persist Timesheet [Script]
Pass your synthesized topic string to the pipeline orchestrator to deterministically format Section 3.2 markdown and idempotently update `logs/timesheet_YYYY-MM.md`:
```bash
python3 scripts/run_pipeline.py --topics-json '{"1": "<Synthesized Topic Sentence>"}'
```

### Step 4: Record Token Usage [Script]
Log session token consumption to track efficiency against the Section 3.6 budget (< 350 tokens daily):
```bash
python3 scripts/track_tokens.py --record --date <YYYY-MM-DD> --input-tokens <PROMPT_TOKENS> --output-tokens <COMPLETION_TOKENS>
```

### Step 5: Report Summary to User
Show the user:
1. The formatted markdown entry appended/updated in `logs/timesheet_YYYY-MM.md`.
2. The token usage confirmation and ASCII status chart (`python3 scripts/track_tokens.py --chart`).
3. Note any anomalies in `logs/improvement_log.md` if an event was missing or unclear.

---

## 📁 Skill Reference & Architectural Boundaries
- Canonical Skill Definition: `skills/pilot-timesheet-logger/SKILL.md`
- Deterministic Workflow Runbook: `skills/pilot-timesheet-logger/workflow.md`
- Token Budget: Target daily prompt tokens < 200, total session < 350 tokens.
- Git Workflow: Adhere strictly to *"One task = one small branch = one focused PR"*. Do not commit directly to `main`.
