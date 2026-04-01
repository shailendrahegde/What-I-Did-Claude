#!/usr/bin/env python3
"""
whatidid.py — Daily Claude activity analytics.

Usage:
  python whatidid.py                                      # Last 7 days (default)
  python whatidid.py --date today                        # Today
  python whatidid.py --date 2026-03-30                   # Specific date
  python whatidid.py --7D                                # Last 7 days (shortcut)
  python whatidid.py --30D                               # Last 30 days (shortcut)
  python whatidid.py --from 2026-03-09 --to 2026-03-30   # Date range
  python whatidid.py --from 2026-03-09                   # From date to today
  python whatidid.py --email you@company.com             # Send email
  python whatidid.py --html                              # Save HTML only
  python whatidid.py --refresh                           # Force re-analysis
  python whatidid.py --lock                              # Freeze estimates

Triggered as a Claude skill via /whatidid
"""
import argparse
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DEFAULT_EMAIL = "shahegde@microsoft.com"

_LOOKBACK_RE = re.compile(r'^(\d+)[dD]$')


# ── Date parsing helpers ───────────────────────────────────────────────────────

def _parse_date(s: str) -> str:
    """Resolve a flexible date string to a YYYY-MM-DD string.

    Accepted forms:
      - "today" or "" or None      → today's date
      - "7D", "30D", "14D" etc.   → N days back from today
      - "YYYY-MM-DD"               → returned as-is
      - "MM-DD-YYYY"               → normalised
      - "MM/DD/YYYY"               → slashes converted to dashes then normalised
      - "DD-Mon-YYYY"              → e.g. "15-Mar-2026"
    """
    from datetime import datetime
    today = date.today()

    if not s or s.lower() == "today":
        return today.isoformat()

    cleaned = s.strip()

    # Lookback shortcut: 7D, 30D, 14D …
    m = _LOOKBACK_RE.match(cleaned)
    if m:
        n = int(m.group(1))
        return (today - timedelta(days=n)).isoformat()

    # Normalise slashes → dashes
    cleaned = cleaned.replace("/", "-")

    # MM-DD-YYYY → YYYY-MM-DD
    parts = cleaned.split("-")
    if len(parts) == 3 and len(parts[0]) == 2 and len(parts[2]) == 4:
        try:
            int(parts[0]); int(parts[1]); int(parts[2])
            cleaned = f"{parts[2]}-{parts[0]}-{parts[1]}"
        except ValueError:
            pass

    # DD-Mon-YYYY (e.g. "15-Mar-2026")
    try:
        from datetime import datetime as _dt
        parsed = _dt.strptime(cleaned, "%d-%b-%Y")
        return parsed.date().isoformat()
    except ValueError:
        pass

    # ISO fallback
    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError:
        print(f"ERROR: Cannot parse date '{s}'. Use YYYY-MM-DD, MM/DD/YYYY, 'today', or e.g. '7D'.")
        sys.exit(1)


def _preprocess_argv(argv: list) -> list:
    """Rewrite --7D / --30D etc. shortcut flags to ['--date', 'ND'] before argparse."""
    _shortcut_re = re.compile(r'^--(\d+[dD])$')
    result = []
    for arg in argv:
        m = _shortcut_re.match(arg)
        if m:
            result += ["--date", m.group(1)]
        else:
            result.append(arg)
    return result


# ── Date range helper ──────────────────────────────────────────────────────────

def _date_range(from_str: str, to_str: str) -> list:
    """Return list of YYYY-MM-DD strings for every day in [from, to]."""
    d0 = date.fromisoformat(from_str)
    d1 = date.fromisoformat(to_str)
    days = []
    cur = d0
    while cur <= d1:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


# ── Goal merging ───────────────────────────────────────────────────────────────

def _normalize_project(name: str) -> str:
    return name.replace("\\", "/").split("/")[-1].lower().strip().replace(" ", "-")


def _merge_related_goals(goals: list) -> list:
    """Group goals from the same project across days."""
    groups = OrderedDict()
    for g in goals:
        proj = g.get("project", "")
        key = _normalize_project(proj) if proj else f"_unnamed_{id(g)}"
        if key in groups:
            merged = groups[key]
            merged["tasks"].extend(g.get("tasks", []))
            merged["human_hours"] += g.get("human_hours", 0)
            merged["_dates"].add(g.get("date", ""))
            if len(g.get("title", "")) > len(merged.get("title", "")):
                merged["title"] = g["title"]
            for d in g.get("docs_referenced", []):
                if d not in merged.get("docs_referenced", []):
                    merged.setdefault("docs_referenced", []).append(d)
        else:
            groups[key] = {**g, "tasks": list(g.get("tasks", [])),
                           "human_hours": g.get("human_hours", 0), "_dates": {g.get("date", "")}}
    result = []
    for merged in groups.values():
        dates = sorted(merged.pop("_dates", set()))
        merged["_all_dates"] = dates
        if len(dates) > 1:
            merged["date"] = dates[0]
            d0, d1 = dates[0][5:], dates[-1][5:]
            merged["summary"] = (merged.get("summary", "") or "") + f" ({len(dates)} days: {d0} to {d1})"
        elif dates:
            merged["date"] = dates[0]
        merged["human_hours"] = round(merged["human_hours"] * 4) / 4
        result.append(merged)
    return result


# ── Analysis merging ───────────────────────────────────────────────────────────

def _merge_analyses(day_analyses: list) -> dict:
    """Combine per-day analysis dicts into one, tagging each goal with its date."""
    all_goals        = []
    all_sessions     = []
    total_tokens     = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "total": 0}
    all_projects     = set()
    all_files        = set()
    total_premium    = 0
    total_lines_added    = 0
    total_lines_removed  = 0
    heuristic_dates  = []
    merged_session_metrics = OrderedDict()  # key: "date|project"

    for target_date, analysis, sessions in day_analyses:
        for g in analysis.get("goals", []):
            g["date"] = target_date
            all_goals.append(g)
        for k in total_tokens:
            total_tokens[k] += analysis.get("tokens", {}).get(k, 0)
        all_sessions.extend(sessions)
        all_projects.update(analysis.get("projects", []))
        all_files.update(analysis.get("files_modified", []))
        total_premium    += analysis.get("premium_requests", 0)
        total_lines_added    += analysis.get("lines_added", 0)
        total_lines_removed  += analysis.get("lines_removed", 0)

        if analysis.get("analysis_method") == "heuristic":
            heuristic_dates.append(target_date)

        # Aggregate session_metrics across days using "date|project" key
        sm_raw = analysis.get("session_metrics", {})
        if isinstance(sm_raw, dict):
            for proj_key, sm in sm_raw.items():
                if not isinstance(sm, dict):
                    continue
                key = f"{target_date}|{proj_key}"
                if key not in merged_session_metrics:
                    merged_session_metrics[key] = dict(sm)
                    merged_session_metrics[key]["date"] = target_date
                else:
                    existing = merged_session_metrics[key]
                    existing["tokens"]           = existing.get("tokens", 0)           + sm.get("tokens", 0)
                    existing["tool_invocations"] = existing.get("tool_invocations", 0) + sm.get("tool_invocations", 0)
                    existing["lines_added"]      = existing.get("lines_added", 0)      + sm.get("lines_added", 0)
                    existing["active_minutes"]   = existing.get("active_minutes", 0)   + sm.get("active_minutes", 0)

    active_dates = sorted({d for d, _, _ in day_analyses})

    # Merge goals across days for multi-day reports
    if len(active_dates) > 1:
        all_goals = _merge_related_goals(all_goals)

    # Headline / narrative
    if len(active_dates) == 1:
        headline  = day_analyses[0][1].get("headline", f"Activity on {active_dates[0]}")
        narrative = day_analyses[0][1].get("day_narrative", "")
    else:
        d0 = active_dates[0][5:]
        d1 = active_dates[-1][5:]
        n  = len(all_goals)
        headline  = (f"{len(active_dates)} active days ({d0} – {d1}): "
                     f"{n} goal{'s' if n != 1 else ''} accomplished")
        narrative = (f"Across {len(active_dates)} active days from "
                     f"{active_dates[0]} to {active_dates[-1]}, Claude assisted with "
                     f"{n} distinct goal{'s' if n != 1 else ''} across "
                     f"{len(all_projects)} project{'s' if len(all_projects) != 1 else ''}. "
                     f"Each goal below shows the date it was completed.")

    analysis_method = "heuristic" if heuristic_dates else "ai"

    return {
        "headline":             headline,
        "primary_focus":        day_analyses[0][1].get("primary_focus", ""),
        "day_narrative":        narrative,
        "goals":                all_goals,
        "tokens":               total_tokens,
        "sessions_count":       len(all_sessions),
        "projects":             list(all_projects),
        "active_dates":         active_dates,
        "total_premium":        total_premium,
        "total_lines_added":    total_lines_added,
        "total_lines_removed":  total_lines_removed,
        "all_files":            sorted(all_files),
        "merged_session_metrics": dict(merged_session_metrics),
        "heuristic_dates":      heuristic_dates,
        "analysis_method":      analysis_method,
        "session_metrics":      dict(merged_session_metrics),
        "lines_added":          total_lines_added,
        "lines_removed":        total_lines_removed,
        "files_modified":       sorted(all_files),
    }


# ── Console summary ────────────────────────────────────────────────────────────

def _print_summary(analysis: dict):
    goals   = analysis.get("goals", [])
    total_t = sum(len(g.get("tasks", [])) for g in goals)
    total_h = sum(g.get("human_hours", 0) for g in goals)

    print(f"Identified {len(goals)} goal(s), {total_t} task(s):")
    for g in goals:
        date_tag = f"  [{g['date']}]" if "date" in g else ""
        print(f"  [GOAL]{date_tag} {g.get('title','')[:65]}  ({g.get('human_hours',0):.1f}h)")
        for t in g.get("tasks", []):
            domain = ", ".join(t.get("domain_skills", []))
            tech   = ", ".join(t.get("tech_skills", []))
            skills = " | ".join(filter(None, [domain, tech]))
            print(f"    - {t.get('title','')[:55]}  ({t.get('human_hours',0):.1f}h | {skills})")

    print(f"\n  Total human effort estimate: {total_h:.1f} hours")
    print(f"  Total tokens consumed:       {analysis['tokens'].get('total', 0):,}")

    lines_added   = analysis.get("lines_added", 0) or analysis.get("total_lines_added", 0)
    lines_removed = analysis.get("lines_removed", 0) or analysis.get("total_lines_removed", 0)
    if lines_added or lines_removed:
        print(f"  Lines added / removed:       +{lines_added} / -{lines_removed}")

    premium = analysis.get("total_premium", 0)
    if premium:
        print(f"  Premium requests:            {premium}")


# ── File helpers ───────────────────────────────────────────────────────────────

def _save_and_open(html: str, label: str) -> Path:
    output_path = Path(__file__).parent / f"report_{label}.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"\nHTML report saved: {output_path}")
    try:
        subprocess.run(["cmd", "/c", "start", "", str(output_path)], check=False)
    except Exception:
        pass
    return output_path


def _lock_cache(dates: list):
    """Mark cache files as read-only to freeze estimates."""
    import stat
    cache_dir = Path.home() / ".claude" / "cache"
    if not cache_dir.exists():
        return
    for d in dates:
        for cache_file in cache_dir.glob(f"*{d}*.json"):
            try:
                cache_file.chmod(cache_file.stat().st_mode & ~stat.S_IWRITE)
                print(f"  Locked: {cache_file.name}")
            except Exception as e:
                print(f"  Could not lock {cache_file.name}: {e}")


# ── Email auto-detect ──────────────────────────────────────────────────────────

def _detect_email() -> str:
    """Auto-detect email from git config, falling back to DEFAULT_EMAIL."""
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, timeout=5
        )
        email = result.stdout.strip()
        if email:
            return email
    except Exception:
        pass
    return DEFAULT_EMAIL


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    argv = _preprocess_argv(sys.argv[1:])

    parser = argparse.ArgumentParser(
        description="Generate a digest of what Claude helped you accomplish."
    )
    parser.add_argument("--date",    default="7D",
                        help="Single date or lookback: YYYY-MM-DD, 'today', '7D', '30D' (default: 7D)")
    parser.add_argument("--from",    dest="date_from", default=None,
                        help="Start of date range: YYYY-MM-DD")
    parser.add_argument("--to",      dest="date_to",   default=None,
                        help="End of date range: YYYY-MM-DD (default: today)")
    parser.add_argument("--email",   nargs="?", const=True, default=None,
                        help=f"Send to this address (default: auto-detect from git config)")
    parser.add_argument("--html",    action="store_true",
                        help="Save HTML file (default when --email not used)")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-run semantic analysis even if cached")
    parser.add_argument("--lock",    action="store_true",
                        help="Freeze estimates by locking cache files after analysis")
    args = parser.parse_args(argv)

    # ── Determine date(s) to process ──────────────────────────────────────────
    today = date.today().isoformat()

    if args.date_from:
        from_date = _parse_date(args.date_from)
        to_date   = _parse_date(args.date_to) if args.date_to else today
        dates = _date_range(from_date, to_date)
        report_label = f"{from_date}_to_{to_date}"
    else:
        # --date may be a lookback (e.g. "7D") which expands to a range
        resolved = _parse_date(args.date)
        # If it was a lookback the resolved date is the *start*; range to today
        raw = args.date.strip() if args.date else ""
        if _LOOKBACK_RE.match(raw):
            dates = _date_range(resolved, today)
            report_label = f"{resolved}_to_{today}"
        else:
            dates = [resolved]
            report_label = resolved

    # ── Harvest + Analyse each date ───────────────────────────────────────────
    from harvest import get_sessions_for_date
    from analyze import analyze_day, check_api_health

    print(f"\nwhatidid -- {report_label.replace('_', ' ')}")
    print("-" * 40)

    # API pre-flight check
    print("  Checking AI analysis API... ", end="", flush=True)
    status, msg = check_api_health()
    if status == "ok":
        print("[OK]")
        api_ok = True
    elif status == "auth":
        print(f"[FAIL] {msg}")
        api_ok = False
    else:
        print(f"[FAIL] {msg} — using heuristic fallback.")
        api_ok = False

    day_analyses = []
    all_sessions = []

    for d in dates:
        sessions = get_sessions_for_date(d)
        if not sessions:
            continue
        tok = sum(sum(s["tokens"].values()) for s in sessions)
        print(f"  {d}: {len(sessions)} session(s), {tok:,} tokens")
        analysis = analyze_day(d, sessions, refresh=args.refresh, use_api=api_ok)
        day_analyses.append((d, analysis, sessions))
        all_sessions.extend(sessions)

    if not day_analyses:
        print(f"\nNo Claude sessions found for {report_label.replace('_', ' ')}.")
        print("  (Sessions are stored in ~/.claude/projects/*/)")
        sys.exit(0)

    print()
    analysis = _merge_analyses(day_analyses)
    _print_summary(analysis)

    # Active-session reminder
    active_dates = analysis.get("active_dates", [])
    if today in active_dates:
        print("\n  Note: today's sessions may still be active — re-run later for a complete digest.")

    # ── Lock cache if requested ────────────────────────────────────────────────
    if args.lock:
        print("\nLocking cache files...")
        _lock_cache(active_dates)

    # ── Generate HTML ──────────────────────────────────────────────────────────
    from report import generate_html
    html = generate_html(report_label, analysis, all_sessions)

    # ── Email handling ─────────────────────────────────────────────────────────
    # args.email is True  → --email given with no address (const=True)
    # args.email is str   → --email you@example.com
    # args.email is None  → --email not given at all
    email_addr = None
    if args.email is True:
        email_addr = _detect_email()
        print(f"\nAuto-detected email: {email_addr}")
    elif isinstance(args.email, str):
        email_addr = args.email

    send_email_flag = bool(email_addr)
    save_html = args.html or not send_email_flag

    output_path = None
    if save_html:
        output_path = _save_and_open(html, report_label)

    if send_email_flag:
        from email_send import send_email
        subject = f"What I Did | {report_label.replace('_', ' ')}"
        print(f"\nSending to {email_addr}...")
        if send_email(email_addr, subject, html):
            print("   Sent.")
        else:
            print("   Email failed. Saving HTML as fallback...")
            if not output_path:
                output_path = _save_and_open(html, report_label)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
