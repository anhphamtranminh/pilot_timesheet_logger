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
