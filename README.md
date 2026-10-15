# Personal Pilot Timesheet Logger

An automated, token-optimized daily timesheet logger built for engineering pilot tracking at Gradion Workspace. It extracts work from Git commits across multiple repositories, GitHub pull requests, and Google Calendar or Workspace events, synthesizing structured daily markdown timesheet entries with minimal LLM token consumption.

Packaged as a dual **Claude Code** and **Google Antigravity (AGY)** native skill.

---

## Quick Triggers

### 1. In Antigravity (AGY) or Claude Code
Open your AI assistant chat within this repository workspace and type:

| Command / Trigger | Action |
|:---|:---|
| `log` or `/log` or `/timesheet` | Runs the full 5-step daily logging workflow and saves to `logs/timesheet_YYYY-MM.md` & Gradion Workspace. |
| `log test` or `log --dry-run` | Executes a **visual dry-run simulation** of the 5-step workflow with zero writes to disk or remote APIs. |
| `"log 2026-10-07"` | Logs work for a specific past date. |

### 2. In Terminal
Run the CLI scripts or root executable shortcut:
```bash
# Preview today's workflow in dry-run mode
./log-test

# Preview a past date in dry-run mode
./log-test --date 2026-10-07

# Execute live persistence and sync to Gradion Workspace
python3 scripts/run_pipeline.py --sync-workspace

# View token efficiency charts and statistics
python3 scripts/track_tokens.py --chart
```

---

## Architecture: Script vs AI Boundary

All deterministic data manipulation is handled by standalone Python scripts, reserving AI calls solely for high-level judgment and semantic topic synthesis.

```
+-------------------------------------------------------------------------------+
|                               1. HARVEST DATA                                 |
|  [Script] scripts/fetch_git.py                Commits across all local repos  |
|  [Script] scripts/fetch_prs.py                PRs opened/reviewed/merged (gh) |
|  [Script] scripts/fetch_calendar.py           Google Calendar / iCal blocks   |
|  [Script] scripts/fetch_workspace_timesheet.py Gradion Workspace API blocks   |
+-------------------------------------------------------------------------------+
                                       │
                                       ▼
+-------------------------------------------------------------------------------+
|                       2. AGGREGATE & TOKEN COMPRESS                           |
|  [Script] scripts/prepare_prompt.py                                           |
|  • Matches commits & PRs to calendar/workspace time blocks                    |
|  • Resolves overlaps, prioritizes dev over meetings, fills empty blocks       |
|  • Generates minimal JSON payload (e.g. 50-150 tokens vs 2000+ raw tokens)   |
+-------------------------------------------------------------------------------+
                                       │
                                       ▼
+-------------------------------------------------------------------------------+
|                              3. TOPIC SYNTHESIS                               |
|  [AI - Judgment] Model synthesizes raw commit subjects & block title into     |
|  one concise, professional engineering topic sentence per block.              |
+-------------------------------------------------------------------------------+
                                       │
                                       ▼
+-------------------------------------------------------------------------------+
|                             4. FORMAT & PERSIST                               |
|  [Script] scripts/format_entry.py                                             |
|  • Formats markdown block with inline PR references & source traces           |
|  [Script] scripts/save_entry.py                                               |
|  • Idempotently updates logs/timesheet_YYYY-MM.md (replaces/appends)          |
|  [Script] scripts/fetch_workspace_timesheet.py                                |
|  • Syncs entry to Gradion Workspace timesheet (edit_time / log_time)          |
+-------------------------------------------------------------------------------+
                                       │
                                       ▼
+-------------------------------------------------------------------------------+
|                           5. MEASURE & REPORT                                 |
|  [Script] scripts/track_tokens.py                                             |
|  • Logs session token consumption against budget (<350 tokens)                |
|  • Updates logs/token_usage.csv and terminal ASCII visual charts              |
+-------------------------------------------------------------------------------+
```

---

## Timesheet Markdown Format

Each entry adheres to the structured format matching the timesheet interface and daily logs:

```markdown
### 2026-10-08 | 08:50 - 18:00 | Workflow test runner implementation and Antigravity triggers...

- **Date:** 2026-10-08
- **Start time:** 08:50
- **End time:** 18:00
- **Description:** Interactive AI workflow test runner, non-destructive simulation harness, and Antigravity quick triggers | PRs: #11, #12, #13
- **Source Trace:**
  - *Calendar / Activity:* Daily Development
  - *Repos:* pilot_timesheet
  - *Commits:* feat(testing): add interactive AI workflow test runner and agy triggers (fixes #12); feat(workspace): include commits and PRs in timesheet entry description
```

---

## Token Efficiency and Tracking

The tool tracks prompt and completion token usage across all daily runs to keep execution lightweight and adhere strictly to the target budget of **< 350 tokens/day**:

### 1. Token Metrics Hierarchy

| Metric | Target / Ceiling | Description | Scope / Formula |
| :--- | :---: | :--- | :--- |
| **Input / Prompt Tokens ($T_{\text{in}}$)** | ~150–200 tokens (ceiling < 300) | Tokens sent to LLM during Step 3 Topic Synthesis | Raw commit subjects + calendar title (stripped of diffs, hashes, attendees) |
| **Output / Completion Tokens ($T_{\text{out}}$)** | ~80–120 tokens | Tokens returned by LLM | 1 concise synthesized topic sentence per block |
| **Cache Tokens ($T_{\text{cache}}$)** | Context cache reads/writes | Cache reads/writes when available in assistant runtime | Stored in tracking CSV |
| **Total Session Tokens ($T_{\text{total}}$)** | **< 350 tokens/day** | Cumulative tokens used per daily execution | $T_{\text{total}} = T_{\text{in}} + T_{\text{out}} + T_{\text{cache}}$ |
| **Budget Compliance Rate** | $\ge 85\%$ | Percentage of logged days within the < 350 token budget | $(\text{Compliant Days} / \text{Monitored Days}) \times 100\%$ |
| **Daily Average** | Historical mean | Rolling average of total tokens per logged day | $\sum T_{\text{total}} / N$ |

> [!NOTE]
> **Architectural Boundary:** Deterministic steps (`[Script]`: git commit extraction, PR querying, iCal feed parsing, overlap reconciliation, markdown formatting, file writing, and Gradion Workspace synchronization) run via local Python scripts and consume **0 LLM tokens**. The token budget applies strictly to Step 3 (`[AI]` Topic Synthesis).

### 2. Where Tokens Are Tracked & Monitored

- **Persistent Historical CSV:** [`logs/token_usage.csv`](file:///Users/anh.phamminh/Documents/pilot_timesheet/logs/token_usage.csv) stores structured records (`date`, `session_id`, `input_tokens`, `output_tokens`, `cache_tokens`, `total_tokens`, `workflow_version`, `notes`).
- **Terminal Status & ASCII Trend Chart:** Run `python3 scripts/track_tokens.py --chart` to display the daily consumption breakdown, visual bar chart, and summary compliance metrics.
- **Visual HTML / SVG Dashboard:** Run `python3 scripts/track_tokens.py --html` to generate an interactive report at [`logs/token_stats.html`](file:///Users/anh.phamminh/Documents/pilot_timesheet/logs/token_stats.html).
- **Dry-Run Test Runner:** Run `python3 scripts/test_workflow.py` (or `./log-test`) to preview prompt token estimation and budget compliance without writing files.

### 3. CLI Tracking Commands

```bash
# Display terminal ASCII / Unicode trend chart
python3 scripts/track_tokens.py --chart

# Generate visual HTML / SVG statistical dashboard
python3 scripts/track_tokens.py --html

# Scan session transcripts for 'log' prompts and auto-record tokens
python3 scripts/track_tokens.py --scan --keyword "log" --auto-record

# Manually record a run's token consumption
python3 scripts/track_tokens.py --record --date 2026-10-15 --input-tokens 145 --output-tokens 55

# Print daily token summary for a specific date
python3 scripts/track_tokens.py --summary --date 2026-10-15
```

### 4. Terminal Chart Output Example

```
======================================================================================
 DAILY TOKEN CONSUMPTION vs BUDGET (Target: < 350 tokens/day)
======================================================================================
 Date       | Input | Output | Total | % Budget | Bar Chart (Scale: 350 tokens max)
------------+-------+--------+-------+----------+------------------------------------
 2026-10-06 |   180 |     95 |   275 |    78.6% | [███████████████████████████░░░░░░░░] [PASS]
 2026-10-07 |   379 |    110 |   489 |   139.7% | [███████████████████████████████████] [OVER]
 2026-10-08 |   104 |     40 |   144 |    41.1% | [██████████████░░░░░░░░░░░░░░░░░░░░░] [PASS]
 2026-10-09 |   139 |     55 |   194 |    55.4% | [███████████████████░░░░░░░░░░░░░░░░] [PASS]
 2026-10-12 |   156 |     65 |   221 |    63.1% | [██████████████████████░░░░░░░░░░░░░] [PASS]
 2026-10-13 |   124 |     50 |   174 |    49.7% | [█████████████████░░░░░░░░░░░░░░░░░░] [PASS]
--------------------------------------------------------------------------------------
 Summary Statistics:
  • Monitored Days:      6
  • Daily Average:       249.5 tokens/day
  • Min / Max Tokens:    144 / 489 tokens
  • Budget Compliance:   83.3% (5/6 days within < 350 budget)
======================================================================================
```

---

## Repository Layout

```
.
├── AGENTS.md                          # Antigravity agent instructions & 'log' trigger runbook
├── config.example.json                # Configuration template
├── config.json                        # Local configuration (repos, authors, calendar URL)
├── log-test                           # Executable convenience script for dry-run testing
├── logs/
│   ├── timesheet_2026-10.md           # Monthly timesheet markdown log (one file per month)
│   ├── improvement_log.md             # Continuous improvement & anomaly review log
│   ├── token_usage.csv                # Historical token usage records
│   └── token_stats.html               # Visual charts of token consumption trends
├── scripts/
│   ├── fetch_git.py                   # Multi-repo Git commit extraction
│   ├── fetch_prs.py                   # GitHub PR extraction via `gh` CLI
│   ├── fetch_calendar.py              # Google Calendar / iCal event extraction
│   ├── fetch_workspace_timesheet.py   # Gradion Workspace API integration & two-way sync
│   ├── prepare_prompt.py              # Token compressor & commit/PR-to-block allocator
│   ├── format_entry.py                # Deterministic markdown formatter
│   ├── save_entry.py                  # Idempotent file updater with overlap replacement
│   ├── run_pipeline.py                # Pipeline orchestrator
│   ├── test_workflow.py               # Visual dry-run workflow test runner
│   └── track_tokens.py                # Session transcript token tracker & chart generator
├── skills/
│   ├── pilot-timesheet-logger/
│   │   ├── SKILL.md                   # Canonical skill definition & triggers
│   │   └── workflow.md                # 5-step runbook & token budget rules
│   └── gradion-workspace/             # Gradion Workspace MCP API skill & OpenAPI spec
└── tests/                             # Full automated unit test suite (33 unit tests)
```

---

## Setup and Configuration

1. **Prerequisites:**
   - Python 3.9+ installed.
   - GitHub CLI (`gh`) authenticated (`gh auth login`).
   - Git configured.

2. **Copy Configuration:**
   ```bash
   cp config.example.json config.json
   ```

3. **Configure `config.json`:**
   ```json
   {
     "git": {
       "authors": ["your.name", "your.github.username"],
       "extra_repo_paths": [
         "~/Documents/another_repo"
       ]
     },
     "calendar": {
       "url": "https://calendar.google.com/calendar/ical/your_calendar_id/basic.ics"
     },
     "workspace": {
       "base_url": "https://workspace-api.gradion.ai",
       "api_token": "YOUR_GRADION_API_TOKEN"
     }
   }
   ```
   *(Alternatively, export `GRADION_API_TOKEN="your-token"` in your shell environment).*

---

## Testing

Run the automated test suite covering all 33 unit tests:
```bash
python3 -m unittest discover -s tests
```

### Git Discipline
This project strictly enforces:
- **One task = one small branch = one focused PR**.
- No direct commits to `main`.
- Clean semantic commit messages (`feat`, `fix`, `docs`, `test`, `refactor`).
