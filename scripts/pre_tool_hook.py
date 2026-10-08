#!/usr/bin/env python3
"""PreToolUse hook script for Antigravity to auto-allow timesheet logging commands."""

import json
import sys

ALLOWED_SCRIPTS = [
    "run_pipeline.py",
    "test_workflow.py",
    "track_tokens.py",
    "prepare_prompt.py",
    "fetch_workspace_timesheet.py"
]


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps({"decision": "ask"}))
            return

        data = json.loads(raw_input)
        tool_call = data.get("toolCall", {})
        tool_name = tool_call.get("name", "")
        args = tool_call.get("args", {})
        command_line = args.get("CommandLine", "")

        if tool_name == "run_command":
            if any(script in command_line for script in ALLOWED_SCRIPTS):
                print(json.dumps({
                    "decision": "allow",
                    "reason": "Auto-approved pilot timesheet pipeline command."
                }))
                return

        print(json.dumps({"decision": "ask"}))
    except Exception as e:
        # Fall back to asking user if hook encounters any unexpected error
        print(json.dumps({"decision": "ask", "reason": f"Hook error: {e}"}))


if __name__ == "__main__":
    main()
