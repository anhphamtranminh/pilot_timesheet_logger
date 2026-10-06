# Daily Timesheet Logger Workflow

This document defines the daily execution procedure for the Personal Pilot Timesheet Logger.

---

## 1. Design Principles & Token Budget

### Principle: Deterministic = [Script] | Judgment = [AI]
- **[Script] steps:** Fixed, repeatable rules. The script extracts data, parses timestamps, deduplicates entries, formats markdown tables, and writes files. The AI never re-derives what code can compute.
- **[AI] steps:** Reserved strictly for judgment—synthesizing raw commit subjects into concise, high-level engineering topics (e.g., combining 4 commit messages into *"Timesheet repo scaffolding and calendar integration"*), and evaluating ambiguous events.

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
| **2. Source Aggregation** | **[Script]** | Map commits and PRs into calendar time blocks based on timestamps. Build compact payload. | `scripts/prepare_prompt.py` |
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

## 4. Execution Command

To execute the daily pipeline end-to-end:
```bash
python3 scripts/run_pipeline.py
```

For dry-run preview:
```bash
python3 scripts/run_pipeline.py --dry-run
```
