#!/usr/bin/env python3
"""[Script] Deterministic token usage tracker as required by Section 3.6."""

import argparse
import csv
import datetime
import json
import os
import sys
from pathlib import Path

# Add parent directory to sys.path to import modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import find_project_root, load_config


def get_token_csv_path() -> Path:
    """Get path to the token usage CSV."""
    root = find_project_root()
    config = load_config()
    token_file = config.get("logging", {}).get("token_file", "logs/token_usage.csv")
    csv_path = root / token_file
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    return csv_path


def init_token_csv_if_missing(csv_path: Path):
    """Initialize token usage CSV with header if missing."""
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "date",
                "session_id",
                "input_tokens",
                "output_tokens",
                "cache_tokens",
                "total_tokens",
                "workflow_version",
                "notes"
            ])


def record_token_run(
    date_str: str,
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_tokens: int = 0,
    workflow_version: str = "v1.0",
    notes: str = ""
):
    """Append a token record to the CSV."""
    csv_path = get_token_csv_path()
    init_token_csv_if_missing(csv_path)

    total_tokens = input_tokens + output_tokens + cache_tokens
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            date_str,
            session_id,
            input_tokens,
            output_tokens,
            cache_tokens,
            total_tokens,
            workflow_version,
            notes
        ])
    print(f"[OK] Recorded {total_tokens} tokens for session {session_id} on {date_str}")


def scan_claude_sessions_for_date(target_date: str) -> list:
    """Scan ~/.claude local logs if available for usage entries."""
    claude_dir = Path.home() / ".claude"
    if not claude_dir.exists():
        return []

    records = []
    for jsonl_file in claude_dir.glob("**/*.jsonl"):
        try:
            mtime = datetime.date.fromtimestamp(jsonl_file.stat().st_mtime).isoformat()
            if mtime != target_date:
                continue

            session_id = jsonl_file.stem
            in_tok = 0
            out_tok = 0
            cache_tok = 0

            with open(jsonl_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if '"usage"' in line:
                        try:
                            obj = json.loads(line)
                            usage = obj.get("usage") or obj.get("message", {}).get("usage", {})
                            in_tok += usage.get("input_tokens", 0)
                            out_tok += usage.get("output_tokens", 0)
                            cache_tok += usage.get("cache_read_input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                        except Exception:
                            pass

            if in_tok + out_tok > 0:
                records.append({
                    "session_id": session_id,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "cache_tokens": cache_tok
                })
        except Exception:
            pass

    return records


def get_all_token_records(custom_csv: Path = None) -> list:
    """Read all token usage records from CSV."""
    csv_path = custom_csv or get_token_csv_path()
    if not csv_path.exists():
        return []
    records = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                records.append({
                    "date": row.get("date", ""),
                    "session_id": row.get("session_id", ""),
                    "input_tokens": int(row.get("input_tokens", 0)),
                    "output_tokens": int(row.get("output_tokens", 0)),
                    "cache_tokens": int(row.get("cache_tokens", 0)),
                    "total_tokens": int(row.get("total_tokens", 0)),
                    "workflow_version": row.get("workflow_version", ""),
                    "notes": row.get("notes", "")
                })
            except ValueError:
                continue
    return records


def generate_ascii_chart(custom_csv: Path = None, budget_limit: int = 350) -> str:
    """Generate an ASCII / Unicode horizontal statistical chart comparing usage to daily budget."""
    records = get_all_token_records(custom_csv)
    if not records:
        return "No token usage data recorded yet."

    # Group by date
    daily_stats = {}
    for r in records:
        d = r["date"]
        if d not in daily_stats:
            daily_stats[d] = {"input": 0, "output": 0, "total": 0, "runs": 0}
        daily_stats[d]["input"] += r["input_tokens"]
        daily_stats[d]["output"] += r["output_tokens"]
        daily_stats[d]["total"] += r["total_tokens"]
        daily_stats[d]["runs"] += 1

    sorted_dates = sorted(daily_stats.keys())
    bar_width = 35  # 35 chars = 350 tokens (1 char = 10 tokens)

    lines = []
    lines.append("=" * 86)
    lines.append(f" DAILY TOKEN CONSUMPTION vs BUDGET (Target: < {budget_limit} tokens/day)")
    lines.append("=" * 86)
    lines.append(" Date       | Input | Output | Total | % Budget | Bar Chart (Scale: 350 tokens max)")
    lines.append("-" * 12 + "+" + "-" * 7 + "+" + "-" * 8 + "+" + "-" * 7 + "+" + "-" * 10 + "+" + "-" * 36)

    total_all_tokens = 0
    compliant_days = 0

    for d in sorted_dates:
        stat = daily_stats[d]
        tot = stat["total"]
        pct = (tot / budget_limit) * 100.0
        total_all_tokens += tot

        if tot <= budget_limit:
            compliant_days += 1
            status_tag = "[PASS]"
        else:
            status_tag = "[OVER]"

        filled = min(int((tot / budget_limit) * bar_width), bar_width)
        empty = bar_width - filled
        bar = "█" * filled + "░" * empty

        lines.append(f" {d:<10} | {stat['input']:>5} | {stat['output']:>6} | {tot:>5} | {pct:>7.1f}% | [{bar}] {status_tag}")

    lines.append("-" * 86)
    avg_tokens = total_all_tokens / len(sorted_dates) if sorted_dates else 0
    compliance_rate = (compliant_days / len(sorted_dates)) * 100.0 if sorted_dates else 0
    totals_list = [daily_stats[d]["total"] for d in sorted_dates]

    lines.append(f" Summary Statistics:")
    lines.append(f"  • Monitored Days:      {len(sorted_dates)}")
    lines.append(f"  • Daily Average:       {avg_tokens:.1f} tokens/day")
    lines.append(f"  • Min / Max Tokens:    {min(totals_list)} / {max(totals_list)} tokens")
    lines.append(f"  • Budget Compliance:   {compliance_rate:.1f}% ({compliant_days}/{len(sorted_dates)} days within < {budget_limit} budget)")
    lines.append("=" * 86)

    return "\n".join(lines)


def generate_html_dashboard(custom_csv: Path = None, output_html: Path = None, budget_limit: int = 350) -> Path:
    """Generate a standalone SVG / HTML statistical dashboard for Week 4 presentation."""
    records = get_all_token_records(custom_csv)
    root = find_project_root()
    out_path = output_html or (root / "logs" / "token_stats.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    daily_stats = {}
    for r in records:
        d = r["date"]
        if d not in daily_stats:
            daily_stats[d] = {"input": 0, "output": 0, "total": 0, "runs": 0, "notes": []}
        daily_stats[d]["input"] += r["input_tokens"]
        daily_stats[d]["output"] += r["output_tokens"]
        daily_stats[d]["total"] += r["total_tokens"]
        daily_stats[d]["runs"] += 1
        if r.get("notes"):
            daily_stats[d]["notes"].append(r["notes"])

    sorted_dates = sorted(daily_stats.keys())
    totals = [daily_stats[d]["total"] for d in sorted_dates] or [0]
    avg_tokens = sum(totals) / len(totals) if totals else 0
    max_tokens = max(totals) if totals else 0
    compliant_days = sum(1 for t in totals if t <= budget_limit)
    compliance_rate = (compliant_days / len(totals)) * 100.0 if totals else 0

    # Build SVG Chart
    svg_width = 700
    svg_height = 280
    chart_top = 30
    chart_bottom = 220
    chart_height = chart_bottom - chart_top
    max_y = max(max_tokens, budget_limit, 400)

    bar_spacing = svg_width / (len(sorted_dates) + 1)
    bar_w = min(40, bar_spacing * 0.6)

    budget_y = chart_bottom - (budget_limit / max_y) * chart_height

    svg_elements = []
    # Budget threshold line
    svg_elements.append(f'<line x1="50" y1="{budget_y:.1f}" x2="{svg_width-20}" y2="{budget_y:.1f}" stroke="#e53e3e" stroke-dasharray="5,5" stroke-width="2"/>')
    svg_elements.append(f'<text x="{svg_width-25}" y="{budget_y-5:.1f}" fill="#e53e3e" font-size="12" font-weight="bold" text-anchor="end">Daily Budget Limit: {budget_limit} tokens</text>')

    # Bars
    for i, d in enumerate(sorted_dates):
        tot = daily_stats[d]["total"]
        bh = (tot / max_y) * chart_height
        bx = 60 + i * bar_spacing
        by = chart_bottom - bh
        fill_color = "#38a169" if tot <= budget_limit else "#e53e3e"

        svg_elements.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="4" fill="{fill_color}"/>')
        svg_elements.append(f'<text x="{bx + bar_w/2:.1f}" y="{by - 6:.1f}" font-size="11" font-weight="600" text-anchor="middle" fill="#2d3748">{tot}</text>')
        svg_elements.append(f'<text x="{bx + bar_w/2:.1f}" y="{chart_bottom + 18:.1f}" font-size="11" text-anchor="middle" fill="#718096">{d[5:]}</text>')

    # Axis line
    svg_elements.append(f'<line x1="45" y1="{chart_bottom}" x2="{svg_width-20}" y2="{chart_bottom}" stroke="#cbd5e0" stroke-width="2"/>')

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Personal Pilot Timesheet — Token Usage Statistics</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f7fafc; color: #2d3748; margin: 0; padding: 24px; }}
    .container {{ max-width: 850px; margin: 0 auto; }}
    h1 {{ font-size: 24px; margin-bottom: 4px; color: #1a202c; }}
    p.subtitle {{ color: #718096; margin-top: 0; margin-bottom: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
    .card {{ background: white; padding: 18px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; }}
    .card-title {{ font-size: 12px; font-weight: 700; color: #718096; text-transform: uppercase; letter-spacing: 0.5px; }}
    .card-val {{ font-size: 26px; font-weight: bold; margin-top: 6px; color: #2b6cb0; }}
    .chart-box {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; margin-bottom: 24px; text-align: center; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; }}
    th, td {{ padding: 12px 16px; text-align: left; font-size: 14px; }}
    th {{ background: #edf2f7; color: #4a5568; font-weight: 600; border-bottom: 1px solid #e2e8f0; }}
    tr:not(:last-child) td {{ border-bottom: 1px solid #edf2f7; }}
    .badge-pass {{ background: #c6f6d5; color: #22543d; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
    .badge-over {{ background: #fed7d7; color: #742a2a; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Personal Pilot Timesheet — Token Usage Statistics</h1>
    <p class="subtitle">Auditing daily token consumption against the &lt; 350 tokens/day target (Section 3.6)</p>
    
    <div class="grid">
      <div class="card">
        <div class="card-title">Daily Average</div>
        <div class="card-val">{avg_tokens:.0f} <span style="font-size:14px;color:#718096;">tokens</span></div>
      </div>
      <div class="card">
        <div class="card-title">Daily Budget</div>
        <div class="card-val">{budget_limit} <span style="font-size:14px;color:#718096;">tokens</span></div>
      </div>
      <div class="card">
        <div class="card-title">Compliance Rate</div>
        <div class="card-val" style="color:#2f855a;">{compliance_rate:.0f}%</div>
      </div>
      <div class="card">
        <div class="card-title">Recorded Days</div>
        <div class="card-val">{len(sorted_dates)}</div>
      </div>
    </div>

    <div class="chart-box">
      <h3 style="margin-top:0;font-size:16px;text-align:left;color:#4a5568;">Daily Token Trend vs Budget Ceiling</h3>
      <svg width="100%" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}">
        {''.join(svg_elements)}
      </svg>
    </div>

    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Input</th>
          <th>Output</th>
          <th>Total</th>
          <th>% Budget</th>
          <th>Status</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
"""
    for d in sorted_dates:
        s = daily_stats[d]
        tot = s["total"]
        pct = (tot / budget_limit) * 100.0
        badge = '<span class="badge-pass">PASS</span>' if tot <= budget_limit else '<span class="badge-over">OVER</span>'
        notes_str = "; ".join(s["notes"]) or "—"
        html_content += f"""        <tr>
          <td><strong>{d}</strong></td>
          <td>{s['input']}</td>
          <td>{s['output']}</td>
          <td><strong>{tot}</strong></td>
          <td>{pct:.1f}%</td>
          <td>{badge}</td>
          <td>{notes_str}</td>
        </tr>
"""

    html_content += """      </tbody>
    </table>
  </div>
</body>
</html>
"""
    out_path.write_text(html_content, encoding="utf-8")
    return out_path


def print_daily_summary(target_date: str):
    """Print the daily total token consumption."""
    csv_path = get_token_csv_path()
    if not csv_path.exists():
        print(f"No token records found for {target_date}.")
        return

    total = 0
    runs = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("date") == target_date:
                total += int(row.get("total_tokens", 0))
                runs += 1

    print(f"Token Summary for {target_date}: {total} tokens across {runs} run(s).")


def main():
    parser = argparse.ArgumentParser(description="Track daily token usage.")
    parser.add_argument("--record", action="store_true", help="Record a new run")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Date YYYY-MM-DD")
    parser.add_argument("--session-id", default="", help="Session ID")
    parser.add_argument("--input-tokens", type=int, default=0, help="Input tokens")
    parser.add_argument("--output-tokens", type=int, default=0, help="Output tokens")
    parser.add_argument("--cache-tokens", type=int, default=0, help="Cache tokens")
    parser.add_argument("--version", default="v1.0", help="Workflow version")
    parser.add_argument("--notes", default="", help="Notes or optimization info")
    parser.add_argument("--summary", action="store_true", help="Print daily summary")
    parser.add_argument("--chart", action="store_true", help="Display ASCII / Unicode statistical chart")
    parser.add_argument("--html", action="store_true", help="Generate HTML / SVG statistical dashboard")
    args = parser.parse_args()

    if args.chart:
        print(generate_ascii_chart())
    elif args.html:
        path = generate_html_dashboard()
        print(f"[OK] Generated HTML Token Statistics Dashboard: {path}")
    elif args.record:
        record_token_run(
            date_str=args.date,
            session_id=args.session_id or f"manual-{int(datetime.datetime.now().timestamp())}",
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            cache_tokens=args.cache_tokens,
            workflow_version=args.version,
            notes=args.notes
        )
    elif args.summary:
        print_daily_summary(args.date)
    else:
        records = scan_claude_sessions_for_date(args.date)
        if records:
            for r in records:
                record_token_run(
                    date_str=args.date,
                    session_id=r["session_id"],
                    input_tokens=r["input_tokens"],
                    output_tokens=r["output_tokens"],
                    cache_tokens=r["cache_tokens"],
                    notes="Auto-scanned session"
                )
        print_daily_summary(args.date)


if __name__ == "__main__":
    main()
