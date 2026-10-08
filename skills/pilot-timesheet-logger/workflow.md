# Daily Timesheet Logger Workflow

This document defines the daily execution procedure for the Personal Pilot Timesheet Logger in compliance with Assignment 1 Section 3.5.

---

## 1. Design Principles & Token Budget

### Core Principle: Deterministic = [Script] | Judgment = [AI]
- **[Script] steps:** Fixed, repeatable rules. Scripts extract git logs, parse calendar iCal feeds, query GitHub pull requests via CLI, deduplicate entries, format markdown fields, and write files. The AI never re-derives what code can compute deterministically.
- **[AI] steps:** Reserved strictly for judgment—synthesizing raw commit subjects into concise, cohesive engineering topics (e.g., combining 5 commit messages into *"Personal pilot timesheet logger implementation, GitHub PR tracking, and token usage analytics"*), and evaluating ambiguous calendar meetings.

### Token Budget Target: < 350 tokens / day
- **Target prompt tokens:** ~150 – 200 tokens
- **Target completion tokens:** ~80 – 120 tokens
- **Target total:** < 350 tokens per run

#### How the [AI] input is kept minimal:
1. **No raw git logs:** Full diffs, file trees, parent hashes, and author metadata are stripped out by `scripts/fetch_git.py`. Only concise commit subjects and timestamps are retained.
2. **No raw calendar dumps:** Recurrence rules, attendee emails, and meeting URLs are stripped by `scripts/fetch_calendar.py`. Only event title and time interval are passed.
3. **No historical context:** The AI receives only today's structured payload—never logs from previous days.
4. **Structured Pre-aggregation:** `scripts/prepare_prompt.py` groups commits and PRs into their corresponding time blocks deterministically *before* calling the AI.

---

## 2. Daily Step-by-Step Procedure

| Step | Tag | Description | Responsible Tool / File |
| :--- | :---: | :--- | :--- |
| **1. Data Ingestion** | **[Script]** | Extract today's git commits, PRs (opened/reviewed/merged), and Google Calendar events/blocks. | `scripts/fetch_git.py`<br>`scripts/fetch_prs.py`<br>`scripts/fetch_calendar.py` |
| **2. Source Aggregation** | **[Script]** | Map commits and PRs into calendar time blocks based on timestamps. Build compact payload. Collapses into 1 consolidated daily entry if no calendar events exist (Section 3.2). | `scripts/prepare_prompt.py` |
| **3. Topic Synthesis** | **[AI]** | Evaluate time blocks: synthesize commit subjects into grouped high-level topics; verify work relevance. | AI Assistant (Judgment) |
| **4. Entry Formatting** | **[Script]** | Validate required fields (`Date`, `Start time`, `End time`, `Description`, `PRs:` inline, source trace) and render standard Section 3.2 markdown. | `scripts/format_entry.py` |
| **5. Persistent Storage** | **[Script]** | Idempotently write entries to monthly log (`logs/timesheet_YYYY-MM.md`). Overwrite matching time blocks without duplicate entries. | `scripts/save_entry.py` |
| **6. Token Measurement** | **[Script]** | Record session token usage (input, output, total) into tracking CSV. | `scripts/track_tokens.py` |
| **7. Improvement Log** | **[AI]** | Document any edge cases or anomalies in `logs/improvement_log.md` for Friday review. | AI Assistant & Intern |

---

## 3. Justification for [AI] Steps

1. **Step 3 (Topic Synthesis):**
   - *Why judgment is needed:* Commits are written incrementally (e.g. `fix typo`, `add parse_ics function`, `update regex`). A human supervisor needs a clean topic summary (e.g. `iCal parser implementation and edge-case handling`). Grouping disparate tasks into a natural human sentence requires linguistic understanding, not rigid regex.
   - *Constraint:* The AI only returns a 1-sentence topic string per block. It does not compute dates, start/end times, or file formatting.

2. **Step 7 (Improvement Review):**
   - *Why judgment is needed:* Identifying whether a missing calendar block or unassigned commit was due to a config error, an off-calendar meeting, or a process gap requires contextual reflection.

---

## 4. Execution Commands

### A. End-to-End Execution with AI Topic Synthesis (Standard Workflow)
```bash
# 1. Pre-aggregate sources into minimal payload:
python3 scripts/prepare_prompt.py

# 2. (AI synthesizes concise topic per block)

# 3. Format and save with synthesized topics:
python3 scripts/run_pipeline.py --topics-json '{"1": "<AI Synthesized Topic>"}'
```

### B. Dry-Run Preview (No Disk Writes)
```bash
python3 scripts/run_pipeline.py --dry-run
```

### C. Offline / Fallback Run (Deterministic Regex Topic Grouping)
```bash
python3 scripts/run_pipeline.py
```
