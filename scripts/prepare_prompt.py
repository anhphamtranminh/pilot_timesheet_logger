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
from config import resolve_target_date


MEETING_KEYWORDS = [
    "meeting", "standup", "1:1", "catch-up", "q&a",
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


LEAVE_KEYWORDS = [
    "leave", "vacation", "sick", "annual leave", "day off", "time off",
    "personal leave", "ooo", "out of office", "holiday"
]


def is_leave_event(title: str) -> bool:
    """Return True if event represents time off, leave, holiday, or absence."""
    t_clean = title.strip().lower()
    if not t_clean:
        return False
    if any(re.search(rf"\b{re.escape(k)}\b", t_clean) for k in LEAVE_KEYWORDS):
        return True
    if re.search(r"\b(?:morning|afternoon|full[\s-]day|day)?\s*off\b", t_clean):
        return True
    return False


def get_leave_period(title: str, st_m: int, et_m: int) -> tuple:
    """Return (is_morning_leave, is_afternoon_leave) given event title and time bounds."""
    t_lower = title.lower()
    has_morning_kw = bool(re.search(r"\b(?:morning|am)\b", t_lower))
    has_afternoon_kw = bool(re.search(r"\b(?:afternoon|pm)\b", t_lower))
    has_fullday_kw = bool(re.search(r"\b(?:full[\s-]day|all[\s-]day)\b", t_lower))

    if has_fullday_kw:
        return True, True
    if has_morning_kw and not has_afternoon_kw:
        return True, False
    if has_afternoon_kw and not has_morning_kw:
        return False, True

    is_m = (st_m < 720)
    is_a = (et_m > 780 or (st_m >= 720 and et_m > 720))
    if is_m and is_a:
        return True, True
    if is_m:
        return True, False
    if is_a:
        return False, True
    return True, True


def is_meeting_block(b: dict) -> bool:
    """Check if block represents a meeting/event rather than general development."""
    title = b.get("title", "").strip()
    if re.match(r"^(?:feat|fix|docs|chore|refactor|test|style|perf|build|ci)(?:\([^)]*\))?:", title, re.IGNORECASE):
        return False
    if "commits:" in title.lower() or "prs:" in title.lower():
        return False
    if any(k in title.lower() for k in ("morning development", "afternoon development", "evening development", "daily development")):
        return False

    first_segment = title.split(" | ")[0].strip() if " | " in title else title
    t_lower = first_segment.lower()

    if any(re.search(rf"\b{re.escape(k)}\b", t_lower) for k in MEETING_KEYWORDS):
        return True

    if re.search(r"\b(?:team|daily|weekly|bi-weekly|monthly|quick|1:1|all-hands|engineering|design|product|project)?\s*sync\b", t_lower):
        if not re.search(r"\bsync\s+(?:all\b|workspace\b|branches?\b|to\b|from\b|data\b|code\b|files?\b|commits?\b|prs?\b|timesheet\b|app\b)", t_lower):
            return True

    return False


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

    # Filter out calendar events that are lunch blocks or leave/time off
    morning_leave = False
    afternoon_leave = False
    filtered_blocks = []
    for b in blocks:
        st_m = time_to_minutes(b.get("start_time", "09:00"))
        et_m = time_to_minutes(b.get("end_time", "12:00"))
        t = b.get("title", "")
        if is_leave_event(t):
            m_leave, a_leave = get_leave_period(t, st_m, et_m)
            if m_leave:
                morning_leave = True
            if a_leave:
                afternoon_leave = True
            continue
        if is_lunch_block(t, st_m, et_m):
            continue
        filtered_blocks.append(b)

    # Ensure no blocks overlap lunch break (12:00 - 13:00 / 720 - 780 minutes) or leave periods
    normalized_blocks = []
    for b in filtered_blocks:
        st_m = time_to_minutes(b.get("start_time", "09:00"))
        et_m = time_to_minutes(b.get("end_time", "12:00"))
        if morning_leave and st_m < 720 and et_m <= 720:
            continue
        if afternoon_leave and st_m >= 720:
            continue
        if st_m < 720 and et_m > 720:
            # Block spans across lunch. Split into morning part and afternoon part.
            if not morning_leave:
                morning_block = dict(b)
                morning_block["end_time"] = "12:00"
                normalized_blocks.append(morning_block)
            if not afternoon_leave and et_m > 780:
                afternoon_block = dict(b)
                afternoon_block["start_time"] = "13:00"
                afternoon_block["entry_id"] = ""
                normalized_blocks.append(afternoon_block)
        elif 720 <= st_m < 780:
            if not afternoon_leave and et_m > 780:
                b_copy = dict(b)
                b_copy["start_time"] = "13:00"
                normalized_blocks.append(b_copy)
        elif st_m < 780 and et_m > 720 and et_m <= 780:
            if not morning_leave and st_m < 720:
                b_copy = dict(b)
                b_copy["end_time"] = "12:00"
                normalized_blocks.append(b_copy)
        else:
            if morning_leave and et_m <= 720:
                continue
            if afternoon_leave and st_m >= 780:
                continue
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

    # Collect activities in morning vs afternoon vs evening to detect absence and prevent artificial evening filler
    morning_commits = [c for c in commits if 0 < time_to_minutes(c.get("time", "")) < 720]
    work_afternoon_commits = [c for c in commits if 720 <= time_to_minutes(c.get("time", "")) <= 1080]
    evening_commits = [c for c in commits if time_to_minutes(c.get("time", "")) > 1080]
    afternoon_commits = [c for c in commits if time_to_minutes(c.get("time", "")) >= 720]

    morning_prs = [p for p in prs if 0 < time_to_minutes(p.get("time", "")) < 720]
    work_afternoon_prs = [p for p in prs if 720 <= time_to_minutes(p.get("time", "")) <= 1080]
    evening_prs = [p for p in prs if time_to_minutes(p.get("time", "")) > 1080]
    afternoon_prs = [p for p in prs if time_to_minutes(p.get("time", "")) >= 720]

    morning_comments = [c for c in comments if 0 < time_to_minutes(c.get("time", "")) < 720]
    work_afternoon_comments = [c for c in comments if 720 <= time_to_minutes(c.get("time", "")) <= 1080]
    evening_comments = [c for c in comments if time_to_minutes(c.get("time", "")) > 1080]
    afternoon_comments = [c for c in comments if time_to_minutes(c.get("time", "")) >= 720]

    morning_reviews = [r for r in reviews if 0 < time_to_minutes(r.get("time", "")) < 720]
    work_afternoon_reviews = [r for r in reviews if 720 <= time_to_minutes(r.get("time", "")) <= 1080]
    evening_reviews = [r for r in reviews if time_to_minutes(r.get("time", "")) > 1080]
    afternoon_reviews = [r for r in reviews if time_to_minutes(r.get("time", "")) >= 720]

    morning_cal = [b for b in normalized_blocks if time_to_minutes(b.get("start_time", "09:00")) < 720]
    work_afternoon_cal = [b for b in normalized_blocks if time_to_minutes(b.get("start_time", "13:00")) < 1080 and time_to_minutes(b.get("end_time", "18:00")) > 720]
    evening_cal = [b for b in normalized_blocks if time_to_minutes(b.get("start_time", "18:00")) >= 1080]
    afternoon_cal = [b for b in normalized_blocks if time_to_minutes(b.get("end_time", "18:00")) > 720]

    unspecified_commits = [c for c in commits if not time_to_minutes(c.get("time", ""))]
    unspecified_prs = [p for p in prs if not time_to_minutes(p.get("time", ""))]

    has_morning_activity = (not morning_leave) and bool(
        morning_commits or morning_prs or morning_comments or morning_reviews or morning_cal
        or (unspecified_commits and not afternoon_commits)
        or (unspecified_prs and not afternoon_prs and not afternoon_cal)
    )
    has_work_afternoon_activity = (not afternoon_leave) and bool(
        work_afternoon_commits or work_afternoon_prs or work_afternoon_comments or work_afternoon_reviews or work_afternoon_cal
        or (unspecified_commits and not morning_commits)
        or (unspecified_prs and not morning_prs and not morning_cal)
    )
    has_evening_activity = bool(
        evening_commits or evening_prs or evening_comments or evening_reviews or evening_cal
    )
    has_afternoon_activity = has_work_afternoon_activity or has_evening_activity

    # If neither morning nor afternoon has activity or both are on leave, return empty
    if not has_morning_activity and not has_afternoon_activity:
        return []

    # If user was absent in morning or afternoon, filter out corresponding blocks
    if not has_morning_activity:
        normalized_blocks = [b for b in normalized_blocks if time_to_minutes(b.get("start_time", "09:00")) >= 720]
    if not has_afternoon_activity:
        normalized_blocks = [b for b in normalized_blocks if time_to_minutes(b.get("end_time", "12:00")) <= 720]

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

    # If a day has no calendar events, create entries based on active periods
    if not structured_blocks:
        if has_morning_activity and not has_afternoon_activity:
            start_time = "09:00"
            if morning_commits:
                times = [c.get("time") for c in morning_commits if c.get("time")]
                if times:
                    min_time = min(times)
                    if time_to_minutes(min_time) < time_to_minutes("09:00"):
                        start_time = min_time
            end_minutes = time_to_minutes("12:00")
            if is_today:
                end_minutes = min(end_minutes, now_min)
            end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
            structured_blocks.append({
                "block_id": 1,
                "title": "Morning Development",
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
        elif not has_morning_activity and has_afternoon_activity:
            if has_work_afternoon_activity:
                start_time = "13:00"
                end_minutes = time_to_minutes("18:00")
                if work_afternoon_commits:
                    times = [c.get("time") for c in work_afternoon_commits if c.get("time")]
                    if times:
                        max_time = max(times)
                        if time_to_minutes(max_time) > end_minutes:
                            end_minutes = time_to_minutes(max_time)
                if is_today:
                    end_minutes = min(end_minutes, now_min)
                end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
                structured_blocks.append({
                    "block_id": len(structured_blocks) + 1,
                    "title": "Afternoon Development",
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
            if has_evening_activity:
                eve_times = [time_to_minutes(x["time"]) for x in (evening_commits + evening_prs + evening_reviews + evening_comments) if x.get("time")]
                if eve_times:
                    eve_min = min(eve_times)
                    eve_max = max(eve_times)
                    start_eve = max(1080, ((eve_min - 15) // 15) * 15)
                    end_eve = max(eve_max + 15, start_eve + 15)
                    if is_today:
                        end_eve = min(now_min, end_eve)
                    if start_eve < end_eve:
                        structured_blocks.append({
                            "block_id": len(structured_blocks) + 1,
                            "title": "Evening Development" if start_eve >= 1080 else "Afternoon Development",
                            "start_time": f"{start_eve // 60:02d}:{start_eve % 60:02d}",
                            "end_time": f"{end_eve // 60:02d}:{end_eve % 60:02d}",
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
        else:
            # Both morning and afternoon active with zero calendar events
            if has_work_afternoon_activity:
                start_time = "09:00"
                if morning_commits:
                    times = [c.get("time") for c in morning_commits if c.get("time")]
                    if times:
                        min_time = min(times)
                        if time_to_minutes(min_time) < time_to_minutes("09:00"):
                            start_time = min_time
                end_minutes = time_to_minutes("18:00")
                if work_afternoon_commits:
                    times = [c.get("time") for c in work_afternoon_commits if c.get("time")]
                    if times:
                        max_time = max(times)
                        if time_to_minutes(max_time) > end_minutes:
                            end_minutes = time_to_minutes(max_time)
                if is_today:
                    end_minutes = min(end_minutes, now_min)
                end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
                structured_blocks.append({
                    "block_id": len(structured_blocks) + 1,
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
            else:
                start_time = "09:00"
                if morning_commits:
                    times = [c.get("time") for c in morning_commits if c.get("time")]
                    if times:
                        min_time = min(times)
                        if time_to_minutes(min_time) < time_to_minutes("09:00"):
                            start_time = min_time
                end_minutes = time_to_minutes("12:00")
                if is_today:
                    end_minutes = min(end_minutes, now_min)
                end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
                structured_blocks.append({
                    "block_id": len(structured_blocks) + 1,
                    "title": "Morning Development",
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
            if has_evening_activity:
                eve_times = [time_to_minutes(x["time"]) for x in (evening_commits + evening_prs + evening_reviews + evening_comments) if x.get("time")]
                if eve_times:
                    eve_min = min(eve_times)
                    eve_max = max(eve_times)
                    start_eve = max(1080, ((eve_min - 15) // 15) * 15)
                    end_eve = max(eve_max + 15, start_eve + 15)
                    if is_today:
                        end_eve = min(now_min, end_eve)
                    if start_eve < end_eve:
                        structured_blocks.append({
                            "block_id": len(structured_blocks) + 1,
                            "title": "Evening Development" if start_eve >= 1080 else "Afternoon Development",
                            "start_time": f"{start_eve // 60:02d}:{start_eve % 60:02d}",
                            "end_time": f"{end_eve // 60:02d}:{end_eve % 60:02d}",
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
    else:
        # We have existing calendar / workspace blocks in structured_blocks
        # 1. Morning extension and backfill:
        if has_morning_activity:
            morning_blocks = [b for b in structured_blocks if time_to_minutes(b["start_time"]) < 720]
            if not morning_blocks:
                structured_blocks.insert(0, {
                    "block_id": 0,
                    "title": "Morning Development",
                    "start_time": "09:00",
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
            else:
                earliest_block = min(morning_blocks, key=lambda b: time_to_minutes(b["start_time"]))
                earliest_m = time_to_minutes(earliest_block["start_time"])
                target_morning_start = 540  # 09:00
                if morning_commits:
                    earliest_c = min(time_to_minutes(c.get("time", "12:00")) for c in morning_commits if c.get("time"))
                    if earliest_c < target_morning_start:
                        target_morning_start = earliest_c

                target_start_str = f"{target_morning_start // 60:02d}:{target_morning_start % 60:02d}"

                if earliest_m > target_morning_start:
                    if not is_meeting_block(earliest_block):
                        earliest_block["start_time"] = target_start_str
                    else:
                        idx = structured_blocks.index(earliest_block)
                        structured_blocks.insert(idx, {
                            "block_id": 0,
                            "title": "Morning Development",
                            "start_time": target_start_str,
                            "end_time": earliest_block["start_time"],
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
                elif earliest_m <= target_morning_start:
                    early_commits = [c for c in commits if time_to_minutes(c.get("time", "12:00")) < earliest_m - 15]
                    if early_commits:
                        min_c_time = min(time_to_minutes(c.get("time", "12:00")) for c in early_commits)
                        start_time_str = f"{min_c_time // 60:02d}:{min_c_time % 60:02d}"
                        if not is_meeting_block(earliest_block):
                            earliest_block["start_time"] = start_time_str
                        else:
                            idx = structured_blocks.index(earliest_block)
                            structured_blocks.insert(idx, {
                                "block_id": 0,
                                "title": "Morning Development",
                                "start_time": start_time_str,
                                "end_time": earliest_block["start_time"],
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

        # 2. Afternoon extension:
        if has_afternoon_activity:
            afternoon_blocks = [b for b in structured_blocks if time_to_minutes(b["end_time"]) > 720]
            if not afternoon_blocks:
                if has_work_afternoon_activity:
                    start_m = 780
                    end_m = time_to_minutes("18:00")
                    if work_afternoon_commits:
                        max_c_time = max(time_to_minutes(c.get("time", "12:00")) for c in work_afternoon_commits if c.get("time"))
                        if max_c_time > end_m:
                            end_m = max_c_time
                    if is_today:
                        end_m = min(now_min, end_m)
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
            else:
                last_block_end = time_to_minutes(structured_blocks[-1]["end_time"])
                if has_work_afternoon_activity:
                    work_act_items = [x for x in (work_afternoon_commits + work_afternoon_prs + work_afternoon_reviews + work_afternoon_comments) if x.get("time")]
                    if work_act_items:
                        max_c_time = max(time_to_minutes(x.get("time", "12:00")) for x in work_act_items if x.get("time"))
                        if max_c_time > last_block_end and not is_meeting_block(structured_blocks[-1]):
                            extended_end = min(now_min, max_c_time + 15) if is_today else max_c_time + 15
                            structured_blocks[-1]["end_time"] = f"{extended_end // 60:02d}:{extended_end % 60:02d}"
                            last_block_end = extended_end

                        late_items = [x for x in work_act_items if time_to_minutes(x.get("time", "12:00")) > last_block_end + 15]
                        if late_items:
                            start_m = max(780, last_block_end) if last_block_end >= 780 else 780
                            max_late_time = max(time_to_minutes(x.get("time", "12:00")) for x in late_items)
                            if is_today:
                                end_m = min(now_min, max(max_late_time + 15, start_m + 15))
                            else:
                                end_m = max(time_to_minutes("18:00"), max_late_time + 15)
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
                            last_block_end = end_m

            # Handle evening activity (> 18:00) cleanly without bridging gaps
            if has_evening_activity:
                eve_items = [c for c in evening_commits if c.get("time")] + \
                            [p for p in evening_prs if p.get("time")] + \
                            [r for r in evening_reviews if r.get("time")] + \
                            [c for c in evening_comments if c.get("time")]
                uncovered_eve = []
                for it in eve_items:
                    t = time_to_minutes(it.get("time", ""))
                    if not any(time_to_minutes(b["start_time"]) <= t <= time_to_minutes(b["end_time"]) for b in structured_blocks):
                        uncovered_eve.append(it)

                if uncovered_eve:
                    uncovered_eve.sort(key=lambda x: time_to_minutes(x.get("time", "")))
                    clusters = []
                    curr_cluster = [uncovered_eve[0]]
                    for item in uncovered_eve[1:]:
                        prev_time = time_to_minutes(curr_cluster[-1].get("time", ""))
                        curr_time = time_to_minutes(item.get("time", ""))
                        if curr_time - prev_time <= 45:
                            curr_cluster.append(item)
                        else:
                            clusters.append(curr_cluster)
                            curr_cluster = [item]
                    clusters.append(curr_cluster)

                    for cluster in clusters:
                        min_eve = min(time_to_minutes(x.get("time", "")) for x in cluster)
                        max_eve = max(time_to_minutes(x.get("time", "")) for x in cluster)
                        current_last_end = max(time_to_minutes(b["end_time"]) for b in structured_blocks) if structured_blocks else 1080
                        if min_eve <= current_last_end + 30:
                            if not is_meeting_block(structured_blocks[-1]):
                                target_end = max(max_eve + 15, current_last_end)
                                if is_today:
                                    target_end = min(now_min, target_end)
                                if target_end > current_last_end:
                                    structured_blocks[-1]["end_time"] = f"{target_end // 60:02d}:{target_end % 60:02d}"
                                continue
                            else:
                                start_m = current_last_end
                        else:
                            start_m = max(1080, ((min_eve - 15) // 15) * 15)

                        end_m = max(max_eve + 15, start_m + 15)
                        if is_today:
                            end_m = min(now_min, end_m)

                        if start_m < end_m:
                            structured_blocks.append({
                                "block_id": len(structured_blocks) + 1,
                                "title": "Evening Development" if start_m >= 1080 else "Afternoon Development",
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

        # Sanity check: keep only blocks with valid duration
        structured_blocks = [b for b in structured_blocks if time_to_minutes(b["start_time"]) < time_to_minutes(b["end_time"])]

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

    # Propagate morning PRs and repos to empty morning development blocks
    morning_prs_set = set()
    morning_repos_set = set()
    morning_pr_objs = []
    for b in structured_blocks:
        if time_to_minutes(b["start_time"]) < 720:
            morning_prs_set.update(b["prs"])
            morning_repos_set.update(b["repos"])
            for p_obj in b.get("pr_objs", []):
                if p_obj not in morning_pr_objs:
                    morning_pr_objs.append(p_obj)

    if not morning_prs_set:
        for p in prs:
            p_time_str = p.get("time", "")
            p_time = time_to_minutes(p_time_str) if p_time_str else None
            if p_time is not None and p_time < 720:
                morning_prs_set.add(p["number"])
                if p.get("repo"):
                    morning_repos_set.add(p["repo"])
                if p not in morning_pr_objs:
                    morning_pr_objs.append(p)
        for c in commits:
            c_time_str = c.get("time", "")
            c_time = time_to_minutes(c_time_str) if c_time_str else None
            if c_time is not None and c_time < 720:
                for p_num in c.get("prs", []):
                    morning_prs_set.add(p_num)
                    p_obj = pr_lookup.get(p_num)
                    if p_obj and p_obj not in morning_pr_objs:
                        morning_pr_objs.append(p_obj)
                if c.get("repo"):
                    morning_repos_set.add(c["repo"])

    if not morning_prs_set and prs:
        for p in prs:
            morning_prs_set.add(p["number"])
            if p.get("repo"):
                morning_repos_set.add(p["repo"])
            if p not in morning_pr_objs:
                morning_pr_objs.append(p)

    for b in structured_blocks:
        if time_to_minutes(b["start_time"]) < 720 and not is_meeting_block(b):
            if not b["commits"] and not b["prs"] and morning_prs_set:
                b["prs"].update(morning_prs_set)
                b["repos"].update(morning_repos_set)
                b.setdefault("pr_objs", []).extend(morning_pr_objs)

    final_blocks = []
    for b in structured_blocks:
        start_m = time_to_minutes(b["start_time"])
        end_m = time_to_minutes(b["end_time"])
        dur = end_m - start_m

        # Clean overgrown title if not a meeting
        if not is_meeting_block(b):
            curr_title = b.get("title", "")
            if len(curr_title) > 60 or " | " in curr_title or "Commits:" in curr_title or re.match(r"^(?:feat|fix|docs|chore|refactor|test|style|perf)\b", curr_title, re.IGNORECASE):
                b["title"] = "Morning Development" if start_m < 720 else "Afternoon Development"

        num_prs = len(b["prs"])
        num_commits = len(b["commits"])
        num_items = num_prs + num_commits

        # A development block should split only if it contains enough items to distribute across multiple sub-blocks
        # and is not a zero-calendar fallback block:
        is_overloaded = (
            (num_prs >= 3 and dur >= 60)
            or (num_prs >= 2 and num_commits >= 2 and dur >= 60)
            or (num_prs >= 2 and dur >= 90)
            or (num_items >= 5 and dur >= 60)
        )
        should_split = (
            (not is_meeting_block(b))
            and (b.get("source") != "commits_prs")
            and (dur > 50)
            and is_overloaded
        )

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

        if dur >= 90 and (num_prs >= 4 or num_items >= 6):
            target_dur, max_dur, min_dur = 35, 45, 30
        else:
            target_dur, max_dur, min_dur = 45, 60, 30

        sub_ranges = split_time_range(
            start_m, end_m, activity_times,
            target_duration=target_dur, max_duration=max_dur, min_duration=min_dur
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

        # Merge adjacent sub-blocks if one is completely empty and merged duration <= 60 min
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

            if not curr_has_items and (prev_dur + curr_dur <= 60):
                prev_sb["end_time"] = sb["end_time"]
            elif not prev_has_items and (prev_dur + curr_dur <= 60):
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

    # Filter out empty artificial filler blocks after 18:00 (1080 min).
    # Normal filler blocks during work hours (09:00 - 18:00) are preserved.
    # Calendar events or external meetings after 18:00 are also preserved.
    filtered_blocks = []
    for b in final_blocks:
        b_st = time_to_minutes(b["start_time"])
        has_activity = bool(b.get("commits") or b.get("prs") or b.get("reviews") or b.get("comments"))
        is_external_or_meeting = is_meeting_block(b) or b.get("source") in ("calendar", "workspace_timesheet") or bool(b.get("entry_id"))
        if b_st >= 1080 and not has_activity and not is_external_or_meeting:
            continue
        filtered_blocks.append(b)
    final_blocks = filtered_blocks

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
    parser.add_argument("date_pos", nargs="?", default=None, help="Target date YYYY-MM-DD or 'yesterday' (optional positional argument)")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD or 'yesterday'")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    args = parser.parse_args()

    raw_date = args.date or args.date_pos
    target_date = resolve_target_date(raw_date)

    payload = generate_ai_payload(target_date)
    indent = 2 if args.pretty else None
    print(json.dumps(payload, indent=indent))


if __name__ == "__main__":
    main()
