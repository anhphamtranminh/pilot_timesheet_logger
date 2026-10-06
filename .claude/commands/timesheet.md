---
description: Run the daily personal pilot timesheet logger
---

Log today's work by executing the `pilot-timesheet-logger` skill:
1. Run `python3 scripts/prepare_prompt.py` to get today's aggregated time blocks, commits, and PRs.
2. Review the commit subjects and calendar event titles, and synthesize a concise 1-sentence engineering topic summary for each block.
3. Run `python3 scripts/run_pipeline.py --topics-json '{"1": "<Synthesized Topic>"}'` to persist the entry.
4. Record the token usage using `python3 scripts/track_tokens.py --record`.
5. Display the logged timesheet entry and current token status chart (`python3 scripts/track_tokens.py --chart`) to the user.
