# ⏱️ Personal Pilot Timesheet Logger

An automated, token-optimized daily timesheet logger built for personal engineering pilot tracking at Gradion Workspace. It extracts work from Git commits across multiple repositories, GitHub pull requests, and Google Calendar / Workspace events, synthesizing compliant daily markdown timesheet entries with minimal LLM token consumption.

Packaged as a dual **Claude Code** and **Google Antigravity (AGY)** native skill.

---

## ⚡ Quick Triggers

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

## 🏗️ Architecture: Strict [Script] vs [AI] Boundary

In adherence to assignment Section 3.5, all deterministic data manipulation is handled by standalone Python scripts, reserving AI calls solely for high-level judgment and semantic topic synthesis.

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
|  • Formats Section 3.2 markdown block with inline PR references & traces     |
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

## 📋 Section 3.2 Timesheet Markdown Specification

Each entry adheres to the exact schema expected by human supervisors and the Gradion Workspace timesheet interface:

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

## 📊 Token Efficiency & Measurement (Section 3.6)

The tool measures real prompt and completion token usage across all daily sessions to verify continuous optimization:

- **Target Budget:** Prompt input < 200 tokens, total session < 350 tokens.
- **CSV Log:** Stored in `logs/token_usage.csv`.
- **HTML Visual Dashboard:** `logs/token_stats.html`.
- **Terminal Status:** Run `python3 scripts/track_tokens.py --chart` to inspect daily trends.

```
======================================================================
  DAILY TOKEN USAGE (Target Budget: < 350 tokens)
======================================================================
Date         Runs  Tokens   Target   Status  Visual
----------------------------------------------------------------------
2026-10-06      1     185      350   PASS    [██████████                  ] 52.9%
2026-10-07      2     320      350   PASS    [██████████████████          ] 91.4%
2026-10-08      1     134      350   PASS    [███████                     ] 38.3%
----------------------------------------------------------------------
Average Daily Usage: 213 tokens/day (60.9% of budget)
```

---

## 🛠️ Repository Layout

```
.
├── AGENTS.md                          # Antigravity agent instructions & 'log' trigger runbook
├── assignment-1-personal-pilot-...md   # Original assignment specification and grading rubric
├── config.example.json                # Configuration template
├── config.json                        # Local configuration (repos, authors, calendar URL)
├── log-test                           # Executable convenience script for dry-run testing
├── logs/
│   ├── timesheet_2026-10.md           # Section 3.2 timesheet markdown store (one file per month)
│   ├── improvement_log.md             # Continuous improvement & anomaly review log
│   ├── token_usage.csv                # Historical token usage records
│   └── token_stats.html               # Visual charts of token consumption trends
├── scripts/
│   ├── fetch_git.py                   # Multi-repo Git commit extraction
│   ├── fetch_prs.py                   # GitHub PR extraction via `gh` CLI
│   ├── fetch_calendar.py              # Google Calendar / iCal event extraction
│   ├── fetch_workspace_timesheet.py   # Gradion Workspace API integration & two-way sync
│   ├── prepare_prompt.py              # Token compressor & commit/PR-to-block allocator
│   ├── format_entry.py                # Deterministic Section 3.2 markdown formatter
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

## ⚙️ Setup & Configuration

1. **Clone & Prerequisites:**
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

## 🧪 Testing

Run the automated test suite covering all 33 unit tests:
```bash
python3 -m unittest discover -s tests
```

### Git Discipline
This project strictly enforces:
- **One task = one small branch = one focused PR**.
- No direct commits to `main`.
- Clean semantic commit messages (`feat`, `fix`, `docs`, `test`, `refactor`).
