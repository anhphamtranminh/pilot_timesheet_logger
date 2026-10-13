# Timesheet Skill Improvement Log

This log tracks daily learnings, what broke or required manual intervention, and corresponding optimizations made to `workflow.md` and scripts as required by Section 3.5 & 3.6 of Assignment 1.

The continuous improvement pattern: **log → review what broke → improve the skill → log again**.

---

## Week 1

### Tue 6 Oct 2026 (Kickoff)
- **What happened:**
  - Initial scaffolding of git, PR, and calendar fetchers.
  - Initial direct `git log` output contained long commit messages and verbose timestamps that consumed unnecessary tokens.
- **What broke / needed adjustment:**
  - Passing raw commit logs directly to the AI step easily exceeded a 1,000 token budget for busy days.
  - If no calendar events were found (or user hadn't set up OAuth), calendar fetching could fail or return empty blocks.
- **Improvements made:**
  - Built `scripts/prepare_prompt.py` to extract only clean commit subjects and group them chronologically into time blocks before passing to the AI.
  - Implemented configurable default work blocks in `config.json` so the tool generates standard morning and afternoon entries even on days without calendar events (satisfying Section 3.2).
  - Target token budget established: **< 350 tokens per day**. Measured Day 1 baseline: **275 tokens**.

### Wed 7 Oct 2026
- **What happened:**
  - Integrated Gradion Workspace API using credentials stored in macOS Keychain (`GRADION_API_TOKEN`) and MCP proxy endpoints (`list_my_entries`, `log_time`).
  - Successfully retrieved live morning and afternoon time blocks from `https://workspace.gradion.com` and automatically matched them with multi-branch git commits.
  - Added trailing development block detection (`16:00 - 18:58`) to isolate evening commits from earlier meeting blocks.
  - Implemented sibling repo auto-discovery across `~/Documents/*` for multi-repo commit and PR harvesting.
  - Synchronized new blocks directly to Gradion Workspace via `run_pipeline.py --sync-workspace`.
- **What broke / needed adjustment:**
  - Passing full block dictionaries for 5 distinct time blocks into `generate_ai_payload()` resulted in 483 estimated prompt tokens, failing the < 350 token daily budget contract in `tests/test_skill_packaging.py`.
  - Workspace entry descriptions contained internal metadata tags (`| #SE`) which cluttered synthesized topic sentences.
- **Improvements made:**
  - Designed compact `ai_input` serialization in `scripts/prepare_prompt.py` passing only essential fields (`id`, sanitized `title`, and active `commits`), compressing multi-block payloads to ~250–280 tokens.
  - Added regex sanitization in `scripts/fetch_workspace_timesheet.py` to strip `#SE` classification suffixes.
  - Enabled two-way synchronization: read existing blocks from Gradion Workspace and post unlogged blocks back to the platform without duplicate range collisions.
  - Added support for updating existing and overlapping blocks via MCP `edit_time`, ensuring blocks (even if initially empty or created manually) get updated with their corresponding commits and PRs.
  - Included both commit subjects (`| Commits: ...`) and pull requests (`| PRs: ...`) directly within the Gradion Workspace entry description so they are clearly visible on the platform timesheet UI.

### Thu 8 Oct 2026
- **What happened:**
  - Expanded timesheet entry structure to capture GitHub PRs, issues, code reviews, and comment threads.
  - Built interactive workflow test runner (`scripts/test_workflow.py`) with 5-step visual breakdown.
  - Standardized Antigravity quick triggers (`log`, `log test`) in `AGENTS.md`.
  - Encountered long development stretches (e.g. 13:00 - 18:04) with numerous disparate PRs.
- **What broke / needed adjustment:**
  - Long commit subject paragraphs were hard for supervisors to scan quickly; descriptions lacked prominent PR/issue tags.
  - Antigravity ran slow exploratory commands (`git status`, `git branch`, `ls`) before running `run_pipeline.py`, creating friction.
  - Unsupervised pipeline writes risked persisting unverified entries if an intern made mistakes or had inaccurate calendar blocks.
  - Oversized multi-hour development blocks grouped 4+ PRs into a single massive block with truncated descriptions.
  - Pipeline artificially generated trailing filler blocks past 18:00 (e.g., 18:00 - 18:15) even when no work occurred after hours.
- **Improvements made:**
  - Updated `scripts/format_entry.py` to place PR and issue numbers prominently at the beginning of descriptions (`PRs: #... | Issues: #...`) and format items as clean bullet points.
  - Added logging of PR comments and code reviews with conditional bullet point formatting.
  - Strict instruction added to `AGENTS.md` and global rules prohibiting preliminary exploratory commands (`ls`, `git status`) prior to running the pipeline orchestrator.
  - Added `PreToolUse` hook configuration to automatically allow timesheet commands without repetitive user approval popups.
  - Implemented two-phase confirmation: `run_pipeline.py --dry-run` displays a formatted Markdown preview, followed by `ask_question` prompt for explicit user confirmation before persisting.
  - Implemented dynamic sub-block splitting in `scripts/prepare_prompt.py`: multi-hour blocks are subdivided into focused 30–45 minute slices aligned with specific PR commit timestamps (fixes #34, #36).
  - Eliminated artificial filler blocks after 18:00, capping daily blocks at the last actual activity timestamp (fixes #41).
  - Added positional and relative date parsing (`scripts/run_pipeline.py 2026-10-08` and `yesterday`) for flexible retroactive logging (fixes #43).

### Fri 9 Oct 2026
- **What happened:**
  - Running timesheet logging mid-day on a workday with 0 pushed git commits resulted in the pipeline skipping timesheet generation entirely.
  - The calendar meeting `[Intern Academy 2026] Security Awareness Training` was not recognized as a meeting block because `MEETING_KEYWORDS` lacked `"training"`.
  - Began multi-project work spanning `pilot_timesheet` and `mcp-standard-research`.
  - Created issues and PRs across multiple repositories with active comment threads.
- **What broke / needed adjustment:**
  - Pipeline skipped active morning work (`09:00 - 11:00`, `11:45 - 12:00`) and afternoon gaps when an intern attended meetings/training without early commit pushes.
  - Internal git stash commits (`WIP on...`) were occasionally detected as git activity.
  - Timesheet entries did not specify which project or repository an activity belonged to, making it impossible for a supervisor to distinguish `pilot_timesheet` from `mcp-standard-research`.
  - Raw GitHub issue discussion comments dumped full multi-paragraph comment text into the AI prompt and timesheet descriptions, inflating token counts.
  - Workspace classification categories (e.g., `#SE`) were accidentally treated as repo names.
- **Improvements made:**
  - Expanded `MEETING_KEYWORDS` in `scripts/prepare_prompt.py` and `scripts/run_pipeline.py` to recognize training, orientation, onboarding, workshops, and ceremonies (fixes #45).
  - Filtered internal git stash references in `scripts/fetch_git.py`.
  - Updated activity heuristic to recognize active workdays during standard working hours (`>= 09:00` for morning, `>= 13:00` for afternoon), generating clean filler work blocks around meetings.
  - Implemented multi-project context tagging: automatically tags `[repo_name]` or `[project_name]` in block headers and descriptions whenever multiple repositories/projects are active in a day (fixes #48).
  - Added active GitHub issue harvesting across sibling repositories (`scripts/fetch_prs.py`).
  - Added concise discussion summarization: aggregates comment threads per issue/PR with comment counts (e.g. `(2 comments)`) rather than dumping raw comment text, keeping token consumption low.
  - Filtered internal workspace categories from project tags.

---

## Week 2

### Mon 12 Oct 2026
- **What happened:**
  - Executed mid-day timesheet logging while researching Model Context Protocol (MCP) servers and the 2048 game engine implementation.
  - Noticed morning blocks had duplicated contents and sub-blocks.
  - Running the pipeline repeatedly during the day re-evaluated the full day from 09:00, creating risk of modifying or overwriting blocks that had already been logged earlier in the day.
- **What broke / needed adjustment:**
  - Morning development blocks (`09:00 - 11:00`, `11:45 - 12:00`) had zero morning commits. The PR assignment fallback previously pulled from the entire day's PR set, erroneously assigning afternoon PRs (such as `#46` created at 14:47) to morning blocks and producing identical duplicated summaries.
  - Blocks $> 45$ minutes were arbitrarily split even when there was only 1 or 0 distinct activity timestamps inside the interval, resulting in multiple consecutive sub-blocks with the same content.
  - Re-running the pipeline at midday or end of day processed the entire day from the beginning rather than preserving previously logged blocks intact and logging only remaining unblocked time.
- **Improvements made:**
  - Isolated morning PR assignment in `scripts/prepare_prompt.py`: PRs with timestamps $\ge 12:00$ are strictly excluded from morning blocks, preventing afternoon PR leakage (fixes #50).
  - Preserved uninterrupted blocks whole: blocks with fewer than 2 distinct timestamped events inside their interval are kept intact and not split blindly without activity evidence.
  - Implemented incremental "remaining-only" blocking:
    - Added `get_persisted_timesheet_blocks` and `get_existing_blocked_intervals` in `scripts/save_entry.py` to parse already-logged intervals from both local markdown (`logs/timesheet_YYYY-MM.md`) and Gradion Workspace.
    - When running for today, the pipeline locks and preserves already-recorded intervals intact and only generates entries for remaining unblocked time blocks.
    - Added CLI flags `--remaining-only` (default for today) and `--all` / `--reblock-all` to allow intentional full-day reblocking when requested.
  - Expanded unit test suite with coverage for morning PR isolation, persisted block parsing, overlap detection, and CLI flag handling (71 unit tests passing).
- **What broke / needed adjustment (End-of-day daily block merge issue):**
  - On days without Google Calendar events (full development days), fallback logic created a single monolithic 9-hour block spanning `09:00 - 18:00` bridging the mandatory lunch break (`12:00 - 13:00`).
  - Fallback development blocks had an explicit check `and (b.get("source") != "commits_prs")` in `scripts/prepare_prompt.py` which prevented overloaded blocks with multiple PRs and commits from being subdivided into discrete 30–60 minute focus blocks.
  - Furthermore, in `scripts/save_entry.py`, `is_block_already_blocked` treated oversized placeholder blocks (e.g., `09:00 - 18:00` or `09:00 - 12:00`) as already blocking any discrete sub-blocks (<= 90 min), locking out refined sub-blocks upon resync.
- **Improvements made (End-of-day daily block merge fix):**
  - Separated zero-calendar fallback into distinct `Morning Development` (`09:00 - 12:00`) and `Afternoon Development` (`13:00 - 18:00`), strictly omitting the mandatory lunch break (`12:00 - 13:00`).
  - Removed the `source != "commits_prs"` restriction so overloaded full-day development blocks are appropriately split into discrete 30–60 min focus sessions mapped to distinct PRs/commits (fixes #57).
  - Updated `is_block_already_blocked` and `save_timesheet_entry` so oversized placeholder blocks (>= 180 min) do not lock out discrete candidate sub-blocks (<= 120 min) and are cleanly replaced upon re-blocking.
  - Successfully logged and synchronized 13 discrete blocks for 2026-10-12 to `logs/timesheet_2026-10.md` and Gradion Workspace via MCP `edit_time` and `log_time`.
