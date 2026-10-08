#!/usr/bin/env python3
"""[Script] Deterministic aggregator that maps commits and PRs into time blocks and prepares a minimal-token payload for [AI]."""

import argparse
import datetime
import json
import sys
from pathlib import Path

# Add parent directory to sys.path to import modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_git import fetch_all_commits
from fetch_prs import fetch_all_prs
from fetch_calendar import fetch_all_events


def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM string to minutes since midnight."""
    parts = time_str.split(":")
    if len(parts) >= 2:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass
    return 0


def assign_items_to_blocks(blocks: list, commits: list, prs: list) -> list:
    """Assign commits and PRs to the time blocks based on timestamps and block metadata."""
    structured_blocks = []

    for i, b in enumerate(blocks):
        structured_blocks.append({
            "block_id": i + 1,
            "title": b.get("title", "Work Block"),
            "start_time": b.get("start_time", "09:00"),
            "end_time": b.get("end_time", "12:00"),
            "source": b.get("source", "calendar"),
            "entry_id": b.get("entry_id", ""),
            "project": b.get("project", ""),
            "status": b.get("status", ""),
            "commits": [],
            "prs": set(),
            "repos": set()
        })

    # Section 3.2: "If a day has no calendar events, still write one entry for that day, built from your commits and PRs."
    if not structured_blocks:
        start_time = "09:00"
        end_time = "18:00"
        if commits:
            times = [c.get("time") for c in commits if c.get("time")]
            if times:
                min_time = min(times)
                max_time = max(times)
                if time_to_minutes(min_time) < time_to_minutes("09:00"):
                    start_time = min_time
                if time_to_minutes(max_time) > time_to_minutes("18:00"):
                    end_time = max_time

        structured_blocks.append({
            "block_id": 1,
            "title": "Daily Development",
            "start_time": start_time,
            "end_time": end_time,
            "source": "commits_prs",
            "entry_id": "",
            "project": "",
            "status": "",
            "commits": [],
            "prs": set(),
            "repos": set()
        })
    elif commits:
        # Check if there are commits occurring significantly before the first scheduled block
        first_block_start = time_to_minutes(structured_blocks[0]["start_time"])
        early_commits = [c for c in commits if time_to_minutes(c.get("time", "12:00")) < first_block_start - 15]
        if early_commits:
            min_c_time = min(time_to_minutes(c.get("time", "12:00")) for c in early_commits)
            start_hh = min_c_time // 60
            start_mm = min_c_time % 60
            start_time_str = f"{start_hh:02d}:{start_mm:02d}"

            structured_blocks.insert(0, {
                "block_id": 0,
                "title": "Morning Development",
                "start_time": start_time_str,
                "end_time": structured_blocks[0]["start_time"],
                "source": "commits_prs",
                "entry_id": "",
                "project": "",
                "status": "",
                "commits": [],
                "prs": set(),
                "repos": set()
            })

        # If there are commits occurring significantly after the last scheduled block, add a trailing development block
        last_block_end = time_to_minutes(structured_blocks[-1]["end_time"])
        late_commits = [c for c in commits if time_to_minutes(c.get("time", "12:00")) > last_block_end + 30]
        if late_commits:
            max_c_time = max(time_to_minutes(c.get("time", "12:00")) for c in late_commits)
            end_minutes = max(time_to_minutes("18:00"), max_c_time + 15)
            end_hh = end_minutes // 60
            end_mm = end_minutes % 60
            end_time_str = f"{end_hh:02d}:{end_mm:02d}"

            structured_blocks.append({
                "block_id": len(structured_blocks) + 1,
                "title": "Afternoon Development",
                "start_time": structured_blocks[-1]["end_time"],
                "end_time": end_time_str,
                "source": "commits_prs",
                "entry_id": "",
                "project": "",
                "status": "",
                "commits": [],
                "prs": set(),
                "repos": set()
            })

        # Re-index block_id sequentially
        for idx, b in enumerate(structured_blocks):
            b["block_id"] = idx + 1

    MEETING_KEYWORDS = ["meeting", "standup", "sync", "1:1", "catch-up", "q&a", "demo", "retro", "interview", "lunch", "kickoff", "discussion"]

    def is_meeting_block(b: dict) -> bool:
        title_lower = b.get("title", "").lower()
        return any(k in title_lower for k in MEETING_KEYWORDS)

    for c in commits:
        c_time = time_to_minutes(c.get("time", "12:00"))
        c_repo = c.get("repo", "")
        c_subj = c.get("subject", "").lower()
        matched_block = None

        # Check candidate blocks that overlap this commit time
        candidates = []
        for b in structured_blocks:
            b_start = time_to_minutes(b["start_time"])
            b_end = time_to_minutes(b["end_time"])
            if b_start <= c_time <= b_end:
                candidates.append(b)

        if len(candidates) == 1:
            matched_block = candidates[0]
        elif len(candidates) > 1:
            # Overlapping candidate blocks!
            # 1. Prefer non-meeting blocks over meetings
            non_meetings = [b for b in candidates if not is_meeting_block(b)]
            pool = non_meetings if non_meetings else candidates

            # 2. Prefer blocks matching commit repo or keywords
            keyword_matches = [
                b for b in pool
                if (c_repo and c_repo.lower() in b.get("title", "").lower())
                or any(w in b.get("title", "").lower() for w in c_subj.split() if len(w) > 4)
            ]
            if keyword_matches:
                pool = keyword_matches

            # 3. Prefer empty blocks (0 commits) so they get populated with work
            empty_blocks = [b for b in pool if not b["commits"]]
            if empty_blocks:
                matched_block = empty_blocks[0]
            else:
                # 4. Prefer shorter/tighter duration block
                def block_len(b):
                    return time_to_minutes(b["end_time"]) - time_to_minutes(b["start_time"])
                matched_block = min(pool, key=block_len)

        # If not within any block, assign to nearest block
        if not matched_block:
            non_meetings = [b for b in structured_blocks if not is_meeting_block(b)]
            search_pool = non_meetings if non_meetings else structured_blocks

            def block_dist(b):
                b_s = time_to_minutes(b["start_time"])
                b_e = time_to_minutes(b["end_time"])
                dist = 0
                if c_time < b_s:
                    dist = b_s - c_time
                elif c_time > b_e:
                    dist = c_time - b_e
                # Slight preference if block is currently empty
                if not b.get("commits"):
                    dist = max(0, dist - 15)
                return dist

            matched_block = min(search_pool, key=block_dist)

        matched_block["commits"].append(c["subject"])
        matched_block["repos"].add(c["repo"])
        for p in c.get("prs", []):
            matched_block["prs"].add(p)

    for p in prs:
        num = p["number"]
        already_attached = any(num in b["prs"] for b in structured_blocks)
        if not already_attached:
            p_time_str = p.get("time", "")
            p_time = time_to_minutes(p_time_str) if p_time_str else None
            p_repo = p.get("repo", "")
            p_title = p.get("title", "").lower()
            target_b = None

            # 1. Match by PR timestamp if within a block
            if p_time is not None and p_time > 0:
                candidates = []
                for b in structured_blocks:
                    b_start = time_to_minutes(b["start_time"])
                    b_end = time_to_minutes(b["end_time"])
                    if b_start <= p_time <= b_end:
                        candidates.append(b)
                if candidates:
                    def cand_score(b):
                        score = 0
                        if p_repo and p_repo in b.get("repos", set()):
                            score += 10
                        if not b.get("prs"):
                            score += 5
                        if not is_meeting_block(b):
                            score += 3
                        return score
                    target_b = max(candidates, key=cand_score)

            # 2. Match by title / PR number appearing in block title
            if not target_b:
                for b in structured_blocks:
                    b_title = b.get("title", "").lower()
                    if num.lower() in b_title or (p_title and any(w in b_title for w in p_title.split() if len(w) > 4)):
                        target_b = b
                        break

            # 3. Match by repo, preferring blocks that have 0 PRs or are empty
            if not target_b and p_repo:
                matching_blocks = [b for b in structured_blocks if p_repo in b["repos"]]
                if matching_blocks:
                    target_b = next((b for b in matching_blocks if not b["prs"]), matching_blocks[0])

            # 4. Fallback: prefer an empty block or first non-meeting block
            if not target_b:
                empty_cand = next((b for b in structured_blocks if not b["commits"] and not b["prs"] and not is_meeting_block(b)), None)
                if empty_cand:
                    target_b = empty_cand
                else:
                    non_meeting_first = next((b for b in structured_blocks if not is_meeting_block(b)), structured_blocks[0])
                    target_b = non_meeting_first

            target_b["prs"].add(num)
            if p_repo:
                target_b["repos"].add(p_repo)

    result = []
    for b in structured_blocks:
        item = {
            "block_id": b["block_id"],
            "title": b["title"],
            "start_time": b["start_time"],
            "end_time": b["end_time"],
            "source": b.get("source", "calendar"),
            "repos": sorted(list(b["repos"])),
            "prs": sorted(list(b["prs"])),
            "commit_subjects": b["commits"]
        }
        if b.get("entry_id"):
            item["entry_id"] = b["entry_id"]
        if b.get("project"):
            item["project"] = b["project"]
        if b.get("status"):
            item["status"] = b["status"]
        result.append(item)

    return result


def generate_ai_payload(target_date: str) -> dict:
    """Prepare the minimal token payload for the [AI] step."""
    commits = fetch_all_commits(target_date)
    prs = fetch_all_prs(target_date)
    events = fetch_all_events(target_date)

    blocks = assign_items_to_blocks(events, commits, prs)

    # Minimal payload passed to LLM for topic synthesis
    ai_view = []
    for b in blocks:
        item = {"id": b["block_id"], "title": b["title"]}
        if b.get("commit_subjects"):
            item["commits"] = b["commit_subjects"]
        ai_view.append(item)

    raw_str = json.dumps(ai_view, separators=(",", ":"))
    estimated_tokens = max(1, len(raw_str) // 4)

    return {
        "date": target_date,
        "estimated_input_tokens": estimated_tokens,
        "blocks": blocks,
        "ai_input": ai_view
    }


def main():
    parser = argparse.ArgumentParser(description="Prepare minimal token payload for AI step.")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Target date YYYY-MM-DD")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    args = parser.parse_args()

    payload = generate_ai_payload(args.date)
    indent = 2 if args.pretty else None
    print(json.dumps(payload, indent=indent))


if __name__ == "__main__":
    main()
