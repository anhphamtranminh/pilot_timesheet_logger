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
  - Passing raw commit logs directly to the AI step would easily exceed a 1,000 token budget for busy days.
  - If no calendar events are found (or user hasn't set up OAuth), calendar fetching could fail or return empty blocks.
- **Improvements made:**
  - Built `scripts/prepare_prompt.py` to extract only clean commit subjects and group them chronologically into time blocks before passing to the AI.
  - Implemented configurable default work blocks in `config.json` so the tool generates standard morning and afternoon entries even on days without calendar events (satisfying Section 3.2).
  - Target token budget established: **< 350 tokens per day**. Measured Day 1 baseline: **275 tokens**.

### Wed 7 Oct 2026
- **What happened:**
  - Integrated Gradion Workspace API using credentials stored in macOS Keychain (`GRADION_API_TOKEN`) and MCP proxy endpoints (`list_my_entries`, `log_time`).
  - Successfully retrieved 4 live morning and afternoon time blocks from `https://workspace.gradion.com` and automatically matched them with multi-branch git commits.
  - Added trailing development block detection (`16:00 - 18:58`) to isolate evening commits from earlier meeting blocks.
  - Implemented sibling repo auto-discovery across `~/Documents/*` for multi-repo commit and PR harvesting.
  - Synchronized new block directly to Gradion Workspace via `run_pipeline.py --sync-workspace`.
- **What broke / needed adjustment:**
  - Passing full block dictionaries for 5 distinct time blocks into `generate_ai_payload()` resulted in 483 estimated prompt tokens, failing the < 350 token daily budget contract in `tests/test_skill_packaging.py`.
  - Workspace entry descriptions contained internal metadata tags (`| #SE`) which cluttered synthesized topic sentences.
- **Improvements made:**
  - Designed compact `ai_input` serialization in `scripts/prepare_prompt.py` that passes only essential fields (`id`, sanitized `title`, and active `commits`), compressing multi-block payloads to ~250–280 tokens.
  - Added regex sanitization in `scripts/fetch_workspace_timesheet.py` to strip `#SE` classification suffixes.
  - Enabled two-way synchronization: read existing blocks from Gradion Workspace and post unlogged blocks back to the platform without duplicate range collisions.
  - Added support for updating existing and overlapping blocks via MCP `edit_time`, ensuring blocks (even if initially empty or created manually) get updated with their corresponding commits and PRs.
  - Included both commit subjects (`| Commits: ...`) and pull requests (`| PRs: ...`) directly within the Gradion Workspace entry description so they are clearly visible on the platform timesheet UI.

### Fri 9 Oct 2026
- **What happened:**
  - Running timesheet logging mid-day on a workday with 0 pushed git commits resulted in the pipeline skipping timesheet generation entirely.
  - The calendar meeting `[Intern Academy 2026] Security Awareness Training` was not recognized as a meeting block because `MEETING_KEYWORDS` lacked `"training"`.
  - Leading, intermediate, and trailing dev work blocks around meetings were omitted when no commits were yet recorded.
- **What broke / needed adjustment:**
  - Pipeline skipped active morning work (`09:00 - 11:00`, `11:45 - 12:00`) and afternoon gaps when an intern attended meetings/training without early commit pushes.
  - Internal git stash commits (`WIP on...`) were occasionally detected as git activity.
- **Improvements made:**
  - Expanded `MEETING_KEYWORDS` in `scripts/prepare_prompt.py` and `scripts/run_pipeline.py` to recognize training, orientation, onboarding, workshops, and ceremonies.
  - Filtered internal git stash references in `scripts/fetch_git.py`.
  - Updated activity heuristic to recognize active workdays during standard working hours (`>= 09:00` for morning, `>= 13:00` for afternoon), generating clean filler work blocks around meetings.
  - Added test coverage in `tests/test_overlapping_blocks.py` verifying zero-commit workdays with training meetings produce all standard time blocks.

