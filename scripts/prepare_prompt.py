#!/usr/bin/env python3
"""[Script] Deterministic aggregator that maps commits and PRs into time blocks and prepares a minimal-token payload for [AI]."""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# Add parent directory to sys.path to import modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_git import fetch_all_commits
from fetch_prs import fetch_all_prs, fetch_all_comments_and_reviews
from fetch_calendar import fetch_all_events


MEETING_KEYWORDS = [
    "meeting", "standup", "sync", "1:1", "catch-up", "q&a",
    "demo", "retro", "interview", "lunch", "kickoff", "discussion"
]


def is_lunch_block(title: str, st_m: int, et_m: int) -> bool:
    """Return True if block represents lunch break (12:00 - 13:00)."""
    if st_m >= 720 and et_m <= 780:
        return True
    t_clean = title.strip().lower()
    if t_clean in ["lunch", "lunch break", "team lunch", "lunch time", "lunch break (12:00-13:00)"]:
        return True
    if re.search(r"^(lunch|lunch break|team lunch)\b", t_clean) and (700 <= st_m <= 780):
        return True
    return False


def is_meeting_block(b: dict) -> bool:
    """Check if block represents a meeting/event rather than general development."""
    title = b.get("title", "")
    if "Commits:" in title or "PRs:" in title or " | " in title:
        first_segment = title.split(" | ")[0].lower()
        return any(re.search(rf"\b{re.escape(k)}\b", first_segment) for k in MEETING_KEYWORDS)
    title_lower = title.lower()
    return any(re.search(rf"\b{re.escape(k)}\b", title_lower) for k in MEETING_KEYWORDS)


def split_time_range(
    start_m: int,
    end_m: int,
    activity_times: list = None,
    target_duration: int = 60,
    max_duration: int = 105,
    min_duration: int = 40
) -> list:
    """Split [start_m, end_m] into intervals <= max_duration, snapping cut points to 15-min intervals between activities."""
    duration = end_m - start_m
    if duration <= max_duration:
        return [(start_m, end_m)]

    activity_times = activity_times or []
    min_k = (duration + max_duration - 1) // max_duration
    k = max(min_k, round(duration / target_duration))

    cand_15 = [m for m in range(start_m + min_duration, end_m - min_duration + 1) if m % 15 == 0]
    cand_5 = [m for m in range(start_m + min_duration, end_m - min_duration + 1) if m % 5 == 0]
    cands = cand_15 if len(cand_15) >= k - 1 else cand_5

    relevant_acts = [a for a in activity_times if start_m <= a <= end_m]

    def min_dist_to_act(t):
        if not relevant_acts:
            return 999
        return min(abs(t - a) for a in relevant_acts)

    cuts = []
    curr = start_m
    for i in range(1, k):
        rem_blocks = k - i
        ideal = curr + (end_m - curr) / (rem_blocks + 1)

        min_pos = max(curr + min_duration, end_m - rem_blocks * max_duration)
        max_pos = min(curr + max_duration, end_m - rem_blocks * min_duration)

        valid_cands = [c for c in cands if min_pos <= c <= max_pos]
        if not valid_cands:
            valid_cands = [c for c in cand_5 if min_pos <= c <= max_pos]
            if not valid_cands:
                valid_cands = [int(ideal)]

        def score(c):
            dist = min_dist_to_act(c)
            dist_bonus = min(dist, 25) * 2.0
            ideal_penalty = abs(c - ideal) * 0.5
            return dist_bonus - ideal_penalty

        best_cut = max(valid_cands, key=score)
        cuts.append(best_cut)
        curr = best_cut

    result = []
    prev = start_m
    for c in cuts:
        result.append((prev, c))
        prev = c
    result.append((prev, end_m))
    return result


def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM string to minutes since midnight."""
    parts = time_str.split(":")
    if len(parts) >= 2:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass
    return 0


def assign_items_to_blocks(
    blocks: list,
    commits: list,
    prs: list,
    target_date: str = None,
    comments: list = None,
    reviews: list = None
) -> list:
    """Assign commits, PRs, comments, and reviews to the time blocks based on timestamps and block metadata."""
    comments = comments or []
    reviews = reviews or []
    is_today = (target_date == datetime.date.today().isoformat())
    now_dt = datetime.datetime.now()
    now_min = now_dt.hour * 60 + now_dt.minute

    # Filter out calendar events that are lunch blocks
    filtered_blocks = []
    for b in blocks:
        st_m = time_to_minutes(b.get("start_time", "09:00"))
        et_m = time_to_minutes(b.get("end_time", "12:00"))
        if is_lunch_block(b.get("title", ""), st_m, et_m):
            continue
        filtered_blocks.append(b)

    # Ensure no blocks overlap lunch break (12:00 - 13:00 / 720 - 780 minutes)
    normalized_blocks = []
    for b in filtered_blocks:
        st_m = time_to_minutes(b.get("start_time", "09:00"))
        et_m = time_to_minutes(b.get("end_time", "12:00"))
        if st_m < 720 and et_m > 720:
            # Block spans across lunch. Split into morning part and afternoon part.
            morning_block = dict(b)
            morning_block["end_time"] = "12:00"
            normalized_blocks.append(morning_block)
            if et_m > 780:
                afternoon_block = dict(b)
                afternoon_block["start_time"] = "13:00"
                afternoon_block["entry_id"] = ""
                normalized_blocks.append(afternoon_block)
        elif 720 <= st_m < 780:
            if et_m > 780:
                b_copy = dict(b)
                b_copy["start_time"] = "13:00"
                normalized_blocks.append(b_copy)
        elif st_m < 780 and et_m > 720 and et_m <= 780:
            if st_m < 720:
                b_copy = dict(b)
                b_copy["end_time"] = "12:00"
                normalized_blocks.append(b_copy)
        else:
            normalized_blocks.append(b)

    # If logging for today, exclude blocks that are entirely in the future and cap ongoing blocks at current time
    if is_today:
        time_bounded = []
        for b in normalized_blocks:
            st_m = time_to_minutes(b.get("start_time", "09:00"))
            et_m = time_to_minutes(b.get("end_time", "12:00"))
            if st_m >= now_min:
                continue
            if et_m > now_min:
                b_copy = dict(b)
                b_copy["end_time"] = f"{now_dt.hour:02d}:{now_dt.minute:02d}"
                time_bounded.append(b_copy)
            else:
                time_bounded.append(b)
        normalized_blocks = time_bounded

    structured_blocks = []
    for i, b in enumerate(normalized_blocks):
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
            "repos": set(),
            "reviews": [],
            "comments": []
        })

    # If a day has no calendar events, write one entry (or morning/afternoon split if spanning lunch)
    if not structured_blocks:
        start_time = "09:00"
        if commits:
            times = [c.get("time") for c in commits if c.get("time")]
            if times:
                min_time = min(times)
                if time_to_minutes(min_time) < time_to_minutes("09:00"):
                    start_time = min_time

        if is_today:
            end_minutes = min(time_to_minutes("18:00"), now_min)
        else:
            end_minutes = time_to_minutes("18:00")
            if commits:
                times = [c.get("time") for c in commits if c.get("time")]
                if times:
                    max_time = max(times)
                    if time_to_minutes(max_time) > end_minutes:
                        end_minutes = time_to_minutes(max_time)

        end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
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
            "repos": set(),
            "reviews": [],
            "comments": []
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
                "repos": set(),
                "reviews": [],
                "comments": []
            })

        # If there are commits occurring after the last scheduled block, extend or add trailing development blocks
        last_block_end = time_to_minutes(structured_blocks[-1]["end_time"])
        max_c_time = max(time_to_minutes(c.get("time", "12:00")) for c in commits)
        if max_c_time > last_block_end and not is_meeting_block(structured_blocks[-1]):
            extended_end = min(now_min, max_c_time + 15) if is_today else max_c_time + 15
            structured_blocks[-1]["end_time"] = f"{extended_end // 60:02d}:{extended_end % 60:02d}"
            last_block_end = extended_end

        late_commits = [c for c in commits if time_to_minutes(c.get("time", "12:00")) > last_block_end + 15]
        if late_commits:
            midday_commits = [c for c in late_commits if time_to_minutes(c.get("time", "12:00")) < 720]
            afternoon_commits = [c for c in late_commits if time_to_minutes(c.get("time", "12:00")) >= 720]

            if midday_commits and last_block_end < 720:
                structured_blocks.append({
                    "block_id": len(structured_blocks) + 1,
                    "title": "Morning Development",
                    "start_time": structured_blocks[-1]["end_time"],
                    "end_time": "12:00",
                    "source": "commits_prs",
                    "entry_id": "",
                    "project": "",
                    "status": "",
                    "commits": [],
                    "prs": set(),
                    "repos": set(),
                    "reviews": [],
                    "comments": []
                })
                last_block_end = 720

            if afternoon_commits:
                start_m = max(780, last_block_end) if last_block_end >= 780 else 780
                max_c_time = max(time_to_minutes(c.get("time", "12:00")) for c in afternoon_commits)
                if is_today:
                    end_m = min(now_min, max(max_c_time + 15, start_m + 15))
                else:
                    end_m = max(time_to_minutes("18:00"), max_c_time + 15)

                structured_blocks.append({
                    "block_id": len(structured_blocks) + 1,
                    "title": "Afternoon Development",
                    "start_time": f"{start_m // 60:02d}:{start_m % 60:02d}",
                    "end_time": f"{end_m // 60:02d}:{end_m % 60:02d}",
                    "source": "commits_prs",
                    "entry_id": "",
                    "project": "",
                    "status": "",
                    "commits": [],
                    "prs": set(),
                    "repos": set(),
                    "reviews": [],
                    "comments": []
                })

        # Re-index block_id sequentially
        for idx, b in enumerate(structured_blocks):
            b["block_id"] = idx + 1

    pr_lookup = {p["number"]: p for p in prs}

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
        matched_block.setdefault("commit_objs", []).append(c)
        for p in c.get("prs", []):
            matched_block["prs"].add(p)
            p_obj = pr_lookup.get(p)
            if p_obj:
                matched_block.setdefault("pr_objs", []).append(p_obj)
            else:
                matched_block.setdefault("pr_objs", []).append({
                    "number": p,
                    "repo": c.get("repo", ""),
                    "time": c.get("time", "")
                })

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
            target_b.setdefault("pr_objs", []).append(p)
        else:
            for b in structured_blocks:
                if num in b["prs"]:
                    existing_nums = [x.get("number") for x in b.get("pr_objs", [])]
                    if num not in existing_nums:
                        b.setdefault("pr_objs", []).append(p)
                    break

    for r in reviews:
        r_time_str = r.get("time", "")
        r_time = time_to_minutes(r_time_str) if r_time_str else None
        r_num = r.get("number", "")
        r_repo = r.get("repo", "")
        target_b = None

        if r_time is not None and r_time > 0:
            candidates = [b for b in structured_blocks if time_to_minutes(b["start_time"]) <= r_time <= time_to_minutes(b["end_time"])]
            if candidates:
                target_b = candidates[0]

        if not target_b and r_num:
            for b in structured_blocks:
                if r_num in b.get("prs", set()):
                    target_b = b
                    break

        if not target_b:
            non_meetings = [b for b in structured_blocks if not is_meeting_block(b)]
            target_b = non_meetings[0] if non_meetings else structured_blocks[0]

        target_b["reviews"].append(r["summary"])
        if r_repo:
            target_b["repos"].add(r_repo)
        target_b.setdefault("review_objs", []).append(r)

    for c in comments:
        c_time_str = c.get("time", "")
        c_time = time_to_minutes(c_time_str) if c_time_str else None
        c_num = c.get("number", "")
        c_repo = c.get("repo", "")
        target_b = None

        if c_time is not None and c_time > 0:
            candidates = [b for b in structured_blocks if time_to_minutes(b["start_time"]) <= c_time <= time_to_minutes(b["end_time"])]
            if candidates:
                target_b = candidates[0]

        if not target_b and c_num:
            for b in structured_blocks:
                if c_num in b.get("prs", set()) or c_num.lower() in b.get("title", "").lower():
                    target_b = b
                    break

        if not target_b:
            non_meetings = [b for b in structured_blocks if not is_meeting_block(b)]
            target_b = non_meetings[0] if non_meetings else structured_blocks[0]

        target_b["comments"].append(c["summary"])
        if c_repo:
            target_b["repos"].add(c_repo)
        target_b.setdefault("comment_objs", []).append(c)

    final_blocks = []
    for b in structured_blocks:
        start_m = time_to_minutes(b["start_time"])
        end_m = time_to_minutes(b["end_time"])
        dur = end_m - start_m

        # Clean overgrown title if not a meeting
        if not is_meeting_block(b):
            curr_title = b.get("title", "")
            if len(curr_title) > 60 or " | " in curr_title or "Commits:" in curr_title:
                b["title"] = "Morning Development" if start_m < 720 else "Afternoon Development"

        num_prs = len(b["prs"])
        num_commits = len(b["commits"])
        is_overloaded = (
            num_prs >= 3
            or (num_prs + num_commits >= 5)
            or (num_prs >= 2 and dur >= 150)
        )
        should_split = (not is_meeting_block(b)) and (dur > 105) and is_overloaded

        if not should_split:
            final_blocks.append(b)
            continue

        activity_times = []
        for c_obj in b.get("commit_objs", []):
            t = time_to_minutes(c_obj.get("time", ""))
            if t > 0:
                activity_times.append(t)
        for p_obj in b.get("pr_objs", []):
            t = time_to_minutes(p_obj.get("time", ""))
            if t > 0:
                activity_times.append(t)
        for r_obj in b.get("review_objs", []):
            t = time_to_minutes(r_obj.get("time", ""))
            if t > 0:
                activity_times.append(t)
        for c_obj in b.get("comment_objs", []):
            t = time_to_minutes(c_obj.get("time", ""))
            if t > 0:
                activity_times.append(t)

        sub_ranges = split_time_range(
            start_m, end_m, activity_times,
            target_duration=60, max_duration=105, min_duration=40
        )

        if len(sub_ranges) <= 1:
            final_blocks.append(b)
            continue

        clean_title = b.get("title", "Work Block")
        if len(clean_title) > 60 or " | " in clean_title or "Commits:" in clean_title:
            clean_title = "Morning Development" if start_m < 720 else "Afternoon Development"

        sub_blocks = []
        for idx, (sub_s, sub_e) in enumerate(sub_ranges):
            sub_b = {
                "block_id": 0,
                "title": clean_title,
                "start_time": f"{sub_s // 60:02d}:{sub_s % 60:02d}",
                "end_time": f"{sub_e // 60:02d}:{sub_e % 60:02d}",
                "source": b.get("source", "calendar"),
                "entry_id": b.get("entry_id", "") if idx == 0 else "",
                "project": b.get("project", ""),
                "status": b.get("status", ""),
                "commits": [],
                "prs": set(),
                "repos": set(),
                "reviews": [],
                "comments": []
            }
            sub_blocks.append(sub_b)

        # Distribute commits into sub-blocks
        for c_obj in b.get("commit_objs", []):
            c_t = time_to_minutes(c_obj.get("time", ""))
            target_sb = None
            if c_t > 0:
                for idx_sb, sb in enumerate(sub_blocks):
                    sb_s = time_to_minutes(sb["start_time"])
                    sb_e = time_to_minutes(sb["end_time"])
                    if idx_sb == len(sub_blocks) - 1:
                        if sb_s <= c_t <= sb_e:
                            target_sb = sb
                            break
                    else:
                        if sb_s <= c_t < sb_e:
                            target_sb = sb
                            break
            if not target_sb:
                def dist_fn(sb):
                    sb_s = time_to_minutes(sb["start_time"])
                    sb_e = time_to_minutes(sb["end_time"])
                    if c_t < sb_s:
                        return sb_s - c_t
                    if c_t > sb_e:
                        return c_t - sb_e
                    return 0
                target_sb = min(sub_blocks, key=dist_fn)

            target_sb["commits"].append(c_obj["subject"])
            if c_obj.get("repo"):
                target_sb["repos"].add(c_obj["repo"])
            for p_num in c_obj.get("prs", []):
                target_sb["prs"].add(p_num)

        # Distribute PRs into sub-blocks
        for p_obj in b.get("pr_objs", []):
            p_num = p_obj.get("number")
            assigned_sb = next((sb for sb in sub_blocks if p_num in sb["prs"]), None)
            if assigned_sb:
                if p_obj.get("repo"):
                    assigned_sb["repos"].add(p_obj["repo"])
                continue

            p_t = time_to_minutes(p_obj.get("time", ""))
            target_sb = None
            if p_t > 0:
                for idx_sb, sb in enumerate(sub_blocks):
                    sb_s = time_to_minutes(sb["start_time"])
                    sb_e = time_to_minutes(sb["end_time"])
                    if idx_sb == len(sub_blocks) - 1:
                        if sb_s <= p_t <= sb_e:
                            target_sb = sb
                            break
                    else:
                        if sb_s <= p_t < sb_e:
                            target_sb = sb
                            break
            if not target_sb:
                def dist_fn(sb):
                    sb_s = time_to_minutes(sb["start_time"])
                    sb_e = time_to_minutes(sb["end_time"])
                    if p_t < sb_s:
                        return sb_s - p_t
                    if p_t > sb_e:
                        return p_t - sb_e
                    return 0
                target_sb = min(sub_blocks, key=dist_fn)

            target_sb["prs"].add(p_num)
            if p_obj.get("repo"):
                target_sb["repos"].add(p_obj["repo"])

        # Distribute reviews into sub-blocks
        for r_obj in b.get("review_objs", []):
            r_t = time_to_minutes(r_obj.get("time", ""))
            r_num = r_obj.get("number", "")
            target_sb = None
            if r_num:
                target_sb = next((sb for sb in sub_blocks if r_num in sb["prs"]), None)
            if not target_sb and r_t > 0:
                for idx_sb, sb in enumerate(sub_blocks):
                    sb_s = time_to_minutes(sb["start_time"])
                    sb_e = time_to_minutes(sb["end_time"])
                    if idx_sb == len(sub_blocks) - 1:
                        if sb_s <= r_t <= sb_e:
                            target_sb = sb
                            break
                    else:
                        if sb_s <= r_t < sb_e:
                            target_sb = sb
                            break
            if not target_sb:
                target_sb = sub_blocks[0]
            target_sb["reviews"].append(r_obj["summary"])
            if r_obj.get("repo"):
                target_sb["repos"].add(r_obj["repo"])

        # Distribute comments into sub-blocks
        for c_obj in b.get("comment_objs", []):
            c_t = time_to_minutes(c_obj.get("time", ""))
            c_num = c_obj.get("number", "")
            target_sb = None
            if c_num:
                target_sb = next((sb for sb in sub_blocks if c_num in sb["prs"]), None)
            if not target_sb and c_t > 0:
                for idx_sb, sb in enumerate(sub_blocks):
                    sb_s = time_to_minutes(sb["start_time"])
                    sb_e = time_to_minutes(sb["end_time"])
                    if idx_sb == len(sub_blocks) - 1:
                        if sb_s <= c_t <= sb_e:
                            target_sb = sb
                            break
                    else:
                        if sb_s <= c_t < sb_e:
                            target_sb = sb
                            break
            if not target_sb:
                target_sb = sub_blocks[0]
            target_sb["comments"].append(c_obj["summary"])
            if c_obj.get("repo"):
                target_sb["repos"].add(c_obj["repo"])

        # Retain any unmatched items from original b
        for c_subj in b.get("commits", []):
            if not any(c_subj in sb["commits"] for sb in sub_blocks):
                sub_blocks[0]["commits"].append(c_subj)
        for p_num in b.get("prs", []):
            if not any(p_num in sb["prs"] for sb in sub_blocks):
                sub_blocks[0]["prs"].add(p_num)
        for repo in b.get("repos", []):
            if not any(repo in sb["repos"] for sb in sub_blocks):
                sub_blocks[0]["repos"].add(repo)

        # Merge adjacent sub-blocks if one is completely empty and merged duration <= 105 min
        merged_sub_blocks = []
        for sb in sub_blocks:
            if not merged_sub_blocks:
                merged_sub_blocks.append(sb)
                continue
            prev_sb = merged_sub_blocks[-1]
            prev_dur = time_to_minutes(prev_sb["end_time"]) - time_to_minutes(prev_sb["start_time"])
            curr_dur = time_to_minutes(sb["end_time"]) - time_to_minutes(sb["start_time"])
            curr_has_items = bool(sb["commits"] or sb["prs"] or sb["reviews"] or sb["comments"])
            prev_has_items = bool(prev_sb["commits"] or prev_sb["prs"] or prev_sb["reviews"] or prev_sb["comments"])

            if not curr_has_items and (prev_dur + curr_dur <= 105):
                prev_sb["end_time"] = sb["end_time"]
            elif not prev_has_items and (prev_dur + curr_dur <= 105):
                sb["start_time"] = prev_sb["start_time"]
                merged_sub_blocks[-1] = sb
            else:
                merged_sub_blocks.append(sb)

        # Ensure entry_id on first sub-block is preserved and subsequent sub-blocks are empty
        if b.get("entry_id") and merged_sub_blocks:
            merged_sub_blocks[0]["entry_id"] = b["entry_id"]
            for sb in merged_sub_blocks[1:]:
                sb["entry_id"] = ""

        final_blocks.extend(merged_sub_blocks)

    # Re-index block_id sequentially
    for idx, b in enumerate(final_blocks):
        b["block_id"] = idx + 1

    result = []
    for b in final_blocks:
        item = {
            "block_id": b["block_id"],
            "title": b["title"],
            "start_time": b["start_time"],
            "end_time": b["end_time"],
            "source": b.get("source", "calendar"),
            "repos": sorted(list(b["repos"])),
            "prs": sorted(list(b["prs"])),
            "commit_subjects": b["commits"],
            "reviews": b.get("reviews", []),
            "comments": b.get("comments", [])
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
    comments, reviews = fetch_all_comments_and_reviews(target_date)

    blocks = assign_items_to_blocks(
        events, commits, prs, target_date=target_date, comments=comments, reviews=reviews
    )

    # Minimal payload passed to LLM for topic synthesis
    ai_view = []
    for b in blocks:
        item = {"id": b["block_id"], "title": b["title"]}
        if b.get("commit_subjects"):
            item["commits"] = b["commit_subjects"]
        if b.get("reviews"):
            item["reviews"] = b["reviews"]
        if b.get("comments"):
            item["comments"] = b["comments"]
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
