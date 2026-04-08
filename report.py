"""
report.py — Daily digest HTML with expandable goal sections.
Layout: Header → Narrative → KPIs →
        What Got Accomplished → What Got Produced →
        How I Collaborated → When I Worked →
        Skills Mobilized → By the Numbers →
        Estimation Evidence → Footer.
Uses inline JS for expand/collapse (works in browser; Outlook renders flat).
"""
from datetime import timezone
from harvest import compute_elapsed_minutes

C = {
    "bg":        "#f0f2f5",
    "card":      "#ffffff",
    "border":    "#dde1e7",
    "accent":    "#0078d4",
    "accent_dk": "#005a9e",
    "accent_lt": "#e8f2fb",
    "text":      "#1b1f23",
    "muted":     "#6a737d",
    "subtle":    "#f7f9fc",
    "green":     "#1a7f37",
    "green_lt":  "#dff6dd",
}

DOMAIN_PILL = ("background:#fff3e0;color:#e65100;padding:2px 8px;border-radius:9px;"
               "font-size:11px;font-weight:600;display:inline-block;margin:2px 3px 2px 0;"
               "white-space:nowrap")
TECH_PILL   = ("background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:9px;"
               "font-size:11px;font-weight:600;display:inline-block;margin:2px 3px 2px 0;"
               "white-space:nowrap")

HOURLY_RATE = 72          # $ per developer-hour (blended professional services rate)
SEAT_COST_PER_MONTH = 19  # Claude Pro subscription $/month


def _pills(domain: list, tech: list) -> str:
    out = [f'<span style="{DOMAIN_PILL}">{s}</span>' for s in domain]
    out += [f'<span style="{TECH_PILL}">{s}</span>' for s in tech]
    return "".join(out)


def _fmt_h(h: float) -> str:
    if h <= 0:      return "—"
    if h < 1:       return f"{int(round(h * 60))}m"
    if h == int(h): return f"{int(h)}h"
    return f"{h:.1f}h"


def _cost(tokens: dict) -> str:
    c = (tokens.get("input", 0)           * 3.00
       + tokens.get("output", 0)          * 15.00
       + tokens.get("cache_read", 0)      * 0.30
       + tokens.get("cache_creation", 0)  * 3.75) / 1_000_000
    return f"~${c:.2f}"


def _utc_to_local(ts: str) -> "datetime":
    """Parse an ISO-8601 UTC timestamp and convert to the system's local timezone."""
    from datetime import datetime
    dt = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return dt.astimezone()


def _fmt_ms(ms: int) -> str:
    """Format milliseconds as Xm Ys."""
    if not ms:
        return "—"
    s = ms // 1000
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"


def _kpi_card(value: str, label: str, sub: str = "") -> str:
    return f"""
    <td style="padding:6px;width:20%;vertical-align:top">
      <div style="background:{C['card']};border:1px solid {C['border']};border-radius:10px;
                  padding:16px 10px;text-align:center;height:80px;
                  box-shadow:0 1px 4px rgba(0,0,0,0.06)">
        <div style="font-size:26px;font-weight:700;color:{C['accent']};line-height:1;
                    letter-spacing:-0.5px">{value}</div>
        <div style="font-size:9px;font-weight:700;color:{C['muted']};text-transform:uppercase;
                    letter-spacing:0.8px;margin-top:6px;line-height:1.3">{label}</div>
        {f'<div style="font-size:10px;color:{C["muted"]};margin-top:3px;line-height:1.3">{sub}</div>' if sub else ""}
      </div>
    </td>"""


def _kpi_section(goals: list, analysis: dict, n_sessions: int,
                 total_prs: int = 0, total_commits: int = 0) -> str:
    total_human_h = sum(g.get("human_hours", 0) for g in goals)
    lines_added   = analysis.get("lines_added", 0)
    lines_removed = analysis.get("lines_removed", 0)
    active_dates  = analysis.get("active_dates", [])
    active_days   = max(1, len(active_dates))

    # Deduplicated total active minutes from session_metrics
    _seen: set = set()
    total_active_min = 0.0
    for _key, _m in analysis.get("session_metrics", {}).items():
        if not isinstance(_m, dict):
            continue
        if "|" in _key:
            _date, _proj = _key.split("|", 1)
            _canon = (_date, _proj.replace("\\", "/").split("/")[-1].lower().strip().replace(" ", "-"))
        else:
            _canon = (_key,)
        if _canon in _seen:
            continue
        _seen.add(_canon)
        total_active_min += _m.get("active_minutes", 0)

    active_val = f"{total_active_min / 60:.1f}h" if total_active_min >= 60 else f"{total_active_min:.0f}m"
    active_sub = f"{active_days} active day{'s' if active_days != 1 else ''}"

    speed_val = (f"{total_human_h / (total_active_min / 60):.1f}\u00d7"
                 if total_active_min > 0 else "—")

    h_str = _fmt_h(total_human_h)
    effort_sub = (f'<a href="#evidence-hdr" style="color:{C["accent"]};'
                  f'text-decoration:none;font-size:9px" onclick="toggleDetail(\'evidence\');'
                  f'return false;">see evidence &#9656;</a>')

    lines_val = f"+{lines_added:,}" if lines_added else "—"
    lines_sub = f"{lines_removed:,} removed" if lines_removed else ""

    pr_sub = f"{total_commits} commit{'s' if total_commits != 1 else ''}"

    return f"""
  <tr>
    <td style="background:{C['bg']};padding:12px 24px;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          {_kpi_card(h_str, "Human Effort<br>Equivalent", effort_sub)}
          {_kpi_card(active_val, "Active<br>Time", active_sub)}
          {_kpi_card(speed_val, "Speed<br>Multiplier", "vs. unassisted expert")}
          {_kpi_card(lines_val, "Lines of Code<br>Added", lines_sub)}
          {_kpi_card(str(total_prs), "PRs<br>Merged", pr_sub)}
        </tr>
      </table>
    </td>
  </tr>"""


def _date_badge(iso_date: str) -> str:
    """Small pill showing a short date like 'Mar 9'."""
    if not iso_date:
        return ""
    try:
        from datetime import date as _date
        d = _date.fromisoformat(iso_date)
        label = d.strftime("%-d %b") if hasattr(d, "strftime") else iso_date[5:]
    except Exception:
        label = iso_date[5:]
    return (f'<span style="font-size:10px;font-weight:600;color:{C["accent"]};'
            f'background:{C["accent_lt"]};padding:1px 7px;border-radius:8px;'
            f'margin-right:6px;white-space:nowrap">{label}</span>')


def _narrative_block(goals: list, fallback: str) -> str:
    """Story-style summary."""
    n = len(goals)
    if not goals:
        return f'<div style="font-size:13px;line-height:1.65;color:{C["text"]}">{fallback}</div>'

    if n == 1:
        g     = goals[0]
        label = g.get("label") or g.get("title", "Goal 1")
        summary = g.get("summary", "")
        return (
            f'<div style="font-size:14px;font-weight:700;color:{C["text"]};margin-bottom:6px">'
            f'{label}</div>'
            f'<div style="font-size:13px;color:{C["muted"]};line-height:1.6">{summary}</div>'
        )

    total_tasks = sum(len(g.get("tasks", [])) for g in goals)
    total_h     = sum(g.get("human_hours", 0) for g in goals)
    intro = (
        f'<div style="font-size:13px;color:{C["text"]};margin-bottom:10px;line-height:1.5">'
        f'Drove {n} projects forward, spanning {total_tasks} tasks and '
        f'{_fmt_h(total_h)} of professional effort:</div>'
    )

    TOP = 5
    visible_items = ""
    hidden_items  = ""
    for i, g in enumerate(goals):
        label      = g.get("label") or g.get("title", f"Goal {i+1}")
        summary    = g.get("summary", "")
        date_badge = _date_badge(g.get("date", ""))
        item = (
            f'<div style="display:flex;align-items:baseline;margin-bottom:7px;'
            f'font-size:13px;line-height:1.55">'
            f'<span style="color:{C["accent"]};font-weight:700;min-width:18px;'
            f'margin-right:6px">{i+1}.</span>'
            f'<span>{date_badge}'
            f'<span style="font-weight:700;color:{C["text"]}">{label}:</span>'
            f'&nbsp;<span style="color:{C["muted"]}">{summary}</span></span>'
            f'</div>'
        )
        if i < TOP:
            visible_items += item
        else:
            hidden_items += item

    extra = n - TOP
    more_btn = ""
    more_div = ""
    if extra > 0:
        more_div = (
            f'<div id="narrative-more" style="display:none">{hidden_items}</div>'
        )
        more_btn = (
            f'<div style="margin-top:4px">'
            f'<span id="narrative-more-btn" data-open="0" '
            f'onclick="toggleNarrativeMore({extra})" '
            f'style="cursor:pointer;font-size:12px;color:{C["accent"]};user-select:none">'
            f'&#9654; See {extra} more project{"s" if extra != 1 else ""}</span>'
            f'</div>'
        )

    return intro + visible_items + more_div + more_btn


# ─────────────────────────────────────────────────────────────────────────────
# ROI Leverage Banner
# ─────────────────────────────────────────────────────────────────────────────

def _leverage_banner(goals: list, analysis: dict) -> str:
    """Hero-style ROI banner."""
    total_human_h = sum(g.get("human_hours", 0) for g in goals)
    human_value   = total_human_h * HOURLY_RATE

    dates = analysis.get("active_dates", [])
    months = set()
    for d in dates:
        try:
            from datetime import datetime
            dt = datetime.strptime(str(d)[:10], "%Y-%m-%d")
            months.add((dt.year, dt.month))
        except ValueError:
            pass
    n_months  = max(1, len(months))
    seat_cost = SEAT_COST_PER_MONTH * n_months

    leverage = round(human_value / seat_cost) if seat_cost > 0 else 0
    if leverage <= 0:
        return ""

    seat_label = f"${seat_cost}/mo" if n_months == 1 else f"${seat_cost} ({n_months}mo)"

    tokens      = analysis.get("tokens", {})
    market_cost = (tokens.get("input", 0) * 3.00 + tokens.get("output", 0) * 15.00
                 + tokens.get("cache_read", 0) * 0.30
                 + tokens.get("cache_creation", 0) * 3.75) / 1_000_000
    api_savings = max(0, market_cost - seat_cost)

    return f"""
  <tr>
    <td style="padding:0 24px 0;border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <div style="background:linear-gradient(135deg,{C['green']} 0%,#145f2a 100%);
                  border-radius:8px;padding:20px 24px;margin-bottom:4px">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="vertical-align:middle;width:30%">
              <div style="font-size:52px;font-weight:800;color:#fff;line-height:1;
                          letter-spacing:-2px">{leverage}x</div>
              <div style="font-size:10px;font-weight:700;color:rgba(255,255,255,0.75);
                          text-transform:uppercase;letter-spacing:1px;margin-top:4px">
                Return on Claude Investment
              </div>
            </td>
            <td style="vertical-align:middle;padding-left:24px">
              <table cellpadding="0" cellspacing="8">
                <tr>
                  <td style="padding:4px 16px 4px 0;border-right:1px solid rgba(255,255,255,0.2)">
                    <div style="font-size:18px;font-weight:700;color:#fff">${human_value:,.0f}</div>
                    <div style="font-size:10px;color:rgba(255,255,255,0.7)">
                      Professional Services Equivalent
                    </div>
                    <div style="font-size:10px;color:rgba(255,255,255,0.5)">
                      {total_human_h:.0f}h @ ${HOURLY_RATE}/hr
                    </div>
                  </td>
                  <td style="padding:4px 16px;border-right:1px solid rgba(255,255,255,0.2)">
                    <div style="font-size:18px;font-weight:700;color:#fff">{seat_label}</div>
                    <div style="font-size:10px;color:rgba(255,255,255,0.7)">
                      Claude Subscription Cost
                    </div>
                    <div style="font-size:10px;color:rgba(255,255,255,0.5)">Pro plan</div>
                  </td>
                  <td style="padding:4px 16px">
                    <div style="font-size:18px;font-weight:700;color:#fff">${api_savings:,.0f}</div>
                    <div style="font-size:10px;color:rgba(255,255,255,0.7)">
                      API Token Savings
                    </div>
                    <div style="font-size:10px;color:rgba(255,255,255,0.5)">
                      vs ${market_cost:,.0f} at market rate
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </div>
    </td>
  </tr>"""


# ─────────────────────────────────────────────────────────────────────────────
# "When I Worked" section
# ─────────────────────────────────────────────────────────────────────────────

def _work_pattern(sessions: list) -> str:
    """GHCP-style time-of-day bar chart with 5 named buckets + expandable daily heatmap."""
    # (label, sub-label, start_hour, end_hour)  Night wraps midnight: 21-24 + 0-5
    BUCKETS = [
        ("Early Morning", "5–9am",    5,  9),
        ("Morning",       "9am–12pm", 9, 12),
        ("Afternoon",     "12–5pm",  12, 17),
        ("Evening",       "5–9pm",   17, 21),
        ("Night",         "9pm–5am", 21,  5),  # wraps midnight
    ]
    BUCKET_LABELS = [b[0] for b in BUCKETS]

    def _bucket_for_hour(h: int) -> str:
        for label, _, start, end in BUCKETS:
            if start < end:
                if start <= h < end:
                    return label
            else:  # wraps midnight (Night: 21-24 + 0-5)
                if h >= start or h < end:
                    return label
        return BUCKET_LABELS[-1]

    counts = {b[0]: 0 for b in BUCKETS}
    for s in sessions:
        for m in s.get("messages", []):
            ts = m.get("timestamp", "")
            if not ts:
                continue
            try:
                local_dt = _utc_to_local(ts)
                counts[_bucket_for_hour(local_dt.hour)] += 1
            except Exception:
                pass

    total = sum(counts.values())
    if total == 0:
        return ""
    max_count = max(counts.values()) or 1
    peak_label = max(counts, key=counts.get)

    rows = ""
    for label, sub, _, _ in BUCKETS:
        n   = counts[label]
        pct = n / max_count * 100
        is_peak = (label == peak_label and n > 0)
        lbl_style = (f"font-size:12px;font-weight:700;color:{C['text']}"
                     if is_peak else
                     f"font-size:12px;color:{C['muted']}")
        cnt_style = (f"font-size:12px;font-weight:700;color:{C['text']}"
                     if is_peak else
                     f"font-size:12px;color:{C['muted']}")
        peak_tag  = (f'&nbsp;<span style="font-size:11px;color:{C["accent"]}">— Peak</span>'
                     if is_peak else "")
        rows += f"""
        <tr style="height:28px">
          <td style="padding:4px 12px 4px 0;white-space:nowrap;vertical-align:middle;width:170px">
            <span style="{lbl_style}">{label}</span>
            <span style="font-size:10px;color:{C['muted']}"> ({sub})</span>
          </td>
          <td style="padding:4px 0;width:100%;vertical-align:middle">
            <div style="background:#e8f0fe;border-radius:4px;height:16px;position:relative">
              <div style="background:{C['accent']};border-radius:4px;height:16px;
                          width:{pct:.1f}%;min-width:{3 if n else 0}px"></div>
            </div>
          </td>
          <td style="padding:4px 0 4px 10px;white-space:nowrap;vertical-align:middle">
            <span style="{cnt_style}">{n} msgs</span>{peak_tag}
          </td>
        </tr>"""

    daily_detail = _daily_activity_detail(sessions, BUCKETS, BUCKET_LABELS)

    return f"""
  <tr>
    <td style="background:{C['card']};padding:0;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td bgcolor="#24292f" style="background:linear-gradient(135deg,#24292f,#1b1f23);padding:10px 24px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;
                      color:rgba(255,255,255,0.7)">When I Worked</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">
            When Copilot-assisted work happened during the day</div>
        </td></tr>
      </table>
      <div style="padding:16px 24px 18px">
        <table cellpadding="0" cellspacing="0" style="width:100%">
          {rows}
        </table>
        {f'''<div id="daily-detail-hdr" style="margin-top:14px;padding:10px 14px;background:{C['accent_lt']};border-radius:6px;cursor:pointer;border:1px solid rgba(0,120,212,0.15)" onclick="toggleDetail('daily-detail')">
          <span id="daily-detail-arrow" style="font-size:10px;color:{C['accent']};margin-right:6px">&#9654;</span>
          <span style="font-size:12px;font-weight:600;color:{C['accent']}">See daily breakdown</span>
          <span style="font-size:11px;color:{C['muted']};margin-left:10px">Hourly activity heatmap per day</span>
        </div>
        <div id="daily-detail-tasks" style="display:none;margin-top:12px">{daily_detail}</div>''' if daily_detail else ""}
      </div>
    </td>
  </tr>"""


def _daily_activity_detail(sessions: list, buckets=None, bucket_labels=None) -> str:
    """GHCP-style heatmap grid: large cells, date+day labels, color legend."""
    if buckets is None:
        buckets = [
            ("Early Morning", "5–9am",    5,  9),
            ("Morning",       "9am–12pm", 9, 12),
            ("Afternoon",     "12–5pm",  12, 17),
            ("Evening",       "5–9pm",   17, 21),
            ("Night",         "9pm–5am", 21,  5),
        ]
    if bucket_labels is None:
        bucket_labels = [b[0] for b in buckets]

    def _bucket_for_hour(h: int) -> str:
        for label, _, start, end in buckets:
            if start < end:
                if start <= h < end:
                    return label
            else:
                if h >= start or h < end:
                    return label
        return bucket_labels[-1]

    from collections import defaultdict
    grid = defaultdict(lambda: defaultdict(int))
    dates_seen = set()

    for s in sessions:
        for m in s.get("messages", []):
            ts = m.get("timestamp", "")
            if not ts:
                continue
            try:
                local_dt = _utc_to_local(ts)
                day_str  = local_dt.strftime("%Y-%m-%d")
                dates_seen.add(day_str)
                grid[day_str][_bucket_for_hour(local_dt.hour)] += 1
            except Exception:
                pass

    if not dates_seen:
        return ""

    sorted_dates = sorted(dates_seen)
    max_val = max((grid[d][p] for d in sorted_dates for p in bucket_labels), default=1) or 1

    # 5-level color scale matching GHCP
    COLORS = ["#e8f0fe", "#c6dafc", "#7ec8f7", "#0078d4", "#1b3a5c"]
    def _cell_color(n: int) -> str:
        if n == 0:
            return "#eef0f3"
        t = min(n / max_val, 1.0)
        if t < 0.15: return COLORS[0]
        if t < 0.35: return COLORS[1]
        if t < 0.60: return COLORS[2]
        if t < 0.85: return COLORS[3]
        return COLORS[4]

    def _text_color(n: int) -> str:
        if n == 0:
            return "transparent"
        t = min(n / max_val, 1.0)
        return "#fff" if t >= 0.35 else C["text"]

    # Column headers
    header_cells = "".join(
        f'<th style="padding:0 6px 10px;text-align:center;min-width:110px">'
        f'<div style="font-size:10px;font-weight:700;color:{C["muted"]};'
        f'text-transform:uppercase;letter-spacing:0.6px">{label}</div>'
        f'<div style="font-size:10px;color:{C["muted"]};margin-top:1px">{sub}</div>'
        f'</th>'
        for label, sub, _, _ in buckets
    )

    body_rows = ""
    for day in sorted_dates:
        try:
            from datetime import date as _date
            d_obj = _date.fromisoformat(day)
            month_str = d_obj.strftime("%b")
            day_num   = d_obj.strftime("%d").lstrip("0")
            dow       = d_obj.strftime("%a")
        except Exception:
            month_str = day[5:7]
            day_num   = day[8:]
            dow       = ""

        row_total = sum(grid[day][p] for p in bucket_labels)
        cells = ""
        for p in bucket_labels:
            n   = grid[day][p]
            bg  = _cell_color(n)
            tc  = _text_color(n)
            cells += (
                f'<td style="padding:4px 6px;text-align:center">'
                f'<div style="background:{bg};border-radius:6px;padding:10px 8px;'
                f'font-size:13px;font-weight:600;color:{tc};min-width:90px;'
                f'min-height:36px;display:flex;align-items:center;justify-content:center">'
                f'{"" if n == 0 else str(n)}</div>'
                f'</td>'
            )

        body_rows += (
            f'<tr>'
            f'<td style="padding:4px 14px 4px 0;vertical-align:middle;white-space:nowrap">'
            f'<div style="font-size:12px;font-weight:700;color:{C["text"]}">{month_str}</div>'
            f'<div style="font-size:13px;font-weight:700;color:{C["text"]};line-height:1">'
            f'{day_num} <span style="font-size:11px;font-weight:400;color:{C["muted"]}">{dow}</span></div>'
            f'</td>'
            f'{cells}'
            f'<td style="padding:4px 0 4px 10px;font-size:12px;color:{C["muted"]};'
            f'vertical-align:middle;text-align:right;white-space:nowrap">{row_total}</td>'
            f'</tr>'
        )

    # Color legend
    legend_swatches = "".join(
        f'<span style="display:inline-block;width:18px;height:18px;background:{c};'
        f'border-radius:3px;margin:0 2px;vertical-align:middle"></span>'
        for c in COLORS
    )
    legend = (
        f'<div style="text-align:right;margin-top:10px;font-size:10px;color:{C["muted"]}">'
        f'Less &nbsp;{legend_swatches}&nbsp; More'
        f'</div>'
    )

    return f"""<div style="overflow-x:auto">
        <table cellpadding="0" cellspacing="0" style="border-collapse:collapse;min-width:500px">
          <thead>
            <tr>
              <th style="padding:0 14px 10px 0"></th>
              {header_cells}
              <th style="padding:0"></th>
            </tr>
          </thead>
          <tbody>{body_rows}</tbody>
        </table>
      </div>
      {legend}"""


# ─────────────────────────────────────────────────────────────────────────────
# "How I Collaborated" section
# ─────────────────────────────────────────────────────────────────────────────

def _collaboration_intent(sessions: list, goals: list = None, project_label_map: dict = None) -> str:
    """Card grid showing how Claude contributed — quality modes with % and time."""
    from harvest import compute_active_time_quality, _QUALITY_COLORS

    MODE_META = {
        "Creative partner":    {"icon": "&#127912;", "desc": "Design, strategy, architecture"},
        "Research assistant":  {"icon": "&#128300;", "desc": "Exploring options, investigating"},
        "Builder":             {"icon": "&#128679;", "desc": "Writing code, generating files"},
        "Refinement partner":  {"icon": "&#128260;", "desc": "Iterating, polishing, improving"},
        "Needed hand-holding": {"icon": "&#128295;", "desc": "Errors, retries, course-correcting AI"},
        "Grunt work handled":  {"icon": "&#9889;",   "desc": "Git ops, config, installs, routine"},
    }

    modes = compute_active_time_quality(sessions)
    total = sum(modes.values())
    if total < 1:
        return ""

    sorted_modes = sorted(modes.items(), key=lambda x: -x[1])

    handholding_raw = modes.get("Needed hand-holding", 0) / total * 100
    grunt_raw       = modes.get("Grunt work handled",  0) / total * 100
    high_value_raw  = 100 - handholding_raw - grunt_raw
    handholding_pct = round(handholding_raw)
    grunt_pct       = round(grunt_raw)
    high_value_pct  = max(0, min(100, round(high_value_raw)))
    total_str = f"{total:.0f}m" if total < 60 else f"{total / 60:.1f}h"
    n_modes   = len([m for m in sorted_modes if m[1] >= 0.1])

    headline = (f"{high_value_pct}% of your collaboration was high-value work "
                f"&mdash; creating, researching, building, and refining.")
    sub_parts = []
    if grunt_pct > 0:
        sub_parts.append(f"Claude automated {grunt_pct}% of routine grunt work")
    if handholding_pct > 0:
        sub_parts.append(f"{handholding_pct}% was spent course-correcting AI output")
    subtitle = " &middot; ".join(sub_parts) if sub_parts else ""

    visible = [(mode, mins) for mode, mins in sorted_modes if mins >= 0.1]
    grid_rows = []
    for pair_start in range(0, len(visible), 2):
        pair = visible[pair_start:pair_start + 2]
        cells = ""
        for mode, mins in pair:
            pct   = mins / total * 100
            meta  = MODE_META.get(mode, {"icon": "", "desc": ""})
            color = _QUALITY_COLORS.get(mode, C["muted"])
            mins_str  = f"{mins:.0f}m" if mins < 60 else f"{mins / 60:.1f}h"
            bar_width = max(pct, 4)
            cells += f"""
          <td style="padding:5px;width:50%;vertical-align:top">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border:1px solid {C['border']};border-left:4px solid {color};
                          border-radius:6px;overflow:hidden">
              <tr>
                <td style="padding:10px 12px">
                  <div style="display:flex;align-items:baseline;margin-bottom:6px">
                    <span style="font-size:18px;margin-right:6px">{meta['icon']}</span>
                    <span style="font-size:12px;font-weight:700;color:{C['text']}">{mode}</span>
                    <span style="font-size:16px;font-weight:800;color:{color};margin-left:auto">
                      {pct:.0f}%</span>
                  </div>
                  <div style="background:{C['bg']};border-radius:3px;height:8px;margin-bottom:6px;
                              overflow:hidden">
                    <div style="width:{bar_width:.0f}%;background:{color};height:100%;
                                border-radius:3px"></div>
                  </div>
                  <div style="font-size:11px;color:{C['muted']};line-height:1.3">
                    {meta['desc']} &middot; <strong style="color:{C['text']}">{mins_str}</strong></div>
                </td>
              </tr>
            </table>
          </td>"""
        if len(pair) == 1:
            cells += '<td style="padding:5px;width:50%"></td>'
        grid_rows.append(f"<tr>{cells}</tr>")

    grid_html = "\n          ".join(grid_rows)

    return f"""
  <tr>
    <td style="background:{C['card']};padding:0;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0"><tr><td bgcolor="#24292f"
             style="background:linear-gradient(135deg,#24292f,#1b1f23);padding:10px 24px">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;
                    color:rgba(255,255,255,0.7)">How I Collaborated</div>
        <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">
          The different types of work Claude handled for you</div>
      </td></tr></table>
      <div style="padding:16px 24px 18px">
        <div style="font-size:14px;font-weight:700;color:{C['text']};margin-bottom:4px;line-height:1.4">
          {headline}</div>
        <div style="font-size:11px;color:{C['muted']};margin-bottom:16px">
          {total_str} of active collaboration across {n_modes} modes &middot; {subtitle}</div>
        <table width="100%" cellpadding="0" cellspacing="0">
          {grid_html}
        </table>
      </div>
    </td>
  </tr>"""


# ─────────────────────────────────────────────────────────────────────────────
# "Skills Mobilized" section
# ─────────────────────────────────────────────────────────────────────────────

def _skills_mobilized(goals: list) -> str:
    """Professional roles by hours — full GHCP version with icons and tech affinity."""
    from collections import defaultdict

    ROLE_ICONS = {
        "Software Engineer":         "&#128187;",
        "Frontend Developer":        "&#127760;",
        "Data Analyst":              "&#128200;",
        "Data Engineer":             "&#128202;",
        "DevOps Engineer":           "&#9881;",
        "Solutions Architect":       "&#127959;",
        "Security Engineer":         "&#128274;",
        "QA Engineer":               "&#128269;",
        "UX Designer":               "&#9998;",
        "Visual Designer":           "&#127912;",
        "Technical Writer":          "&#128221;",
        "Product Manager":           "&#127919;",
        "Program Manager":           "&#128203;",
        "Business Analyst":          "&#128196;",
        "Management Consultant":     "&#128188;",
        "Research Scientist":        "&#128300;",
        "Financial Analyst":         "&#128185;",
        "Risk & Compliance Analyst": "&#128737;",
        "Domain Expert":             "&#127891;",
    }
    TECH_AFFINITY: dict = {
        "Python":     {"Software Engineer": 3, "Data Analyst": 1, "Data Engineer": 2},
        "SQL":        {"Data Analyst": 3, "Data Engineer": 2},
        "JavaScript": {"Software Engineer": 3, "Frontend Developer": 2},
        "TypeScript": {"Software Engineer": 3, "Frontend Developer": 2},
        "HTML/CSS":   {"Frontend Developer": 2, "UX Designer": 2, "Visual Designer": 1},
        "Bash/Shell": {"Software Engineer": 2, "DevOps Engineer": 2},
    }

    role_data: dict = defaultdict(lambda: {"count": 0, "hours": 0.0})
    for g in goals:
        for t in g.get("tasks", []):
            task_hours = t.get("human_hours", 0) or 0
            roles = t.get("professional_roles", [])
            if not roles:
                roles = t.get("domain_skills", []) + t.get("tech_skills", [])
            if not roles:
                continue
            tech = [s for s in t.get("tech_skills", []) if s in TECH_AFFINITY]
            scores: dict = {}
            for r in roles:
                scores[r] = sum(TECH_AFFINITY[sk].get(r, 0) for sk in tech)
            total_score = sum(scores.values())
            for r in roles:
                role_data[r]["count"] += 1
                if total_score > 0:
                    role_data[r]["hours"] += task_hours * (scores[r] / total_score)
                else:
                    role_data[r]["hours"] += task_hours / len(roles)

    if not role_data:
        return ""

    sorted_roles = sorted(role_data.items(), key=lambda x: x[1]["hours"], reverse=True)
    max_hours = sorted_roles[0][1]["hours"] or 1
    total_hours = sum(d["hours"] for _, d in sorted_roles)
    n_roles = len(sorted_roles)
    total_tasks = sum(d["count"] for _, d in sorted_roles)

    rows = ""
    for role, data in sorted_roles:
        icon  = ROLE_ICONS.get(role, "&#128161;")
        hrs   = data["hours"]
        count = data["count"]
        bar   = round(hrs / max_hours * 100)
        h_str = _fmt_h(hrs)
        rows += f"""
          <tr>
            <td style="padding:5px 10px 5px 0;white-space:nowrap;vertical-align:middle;width:24px">
              <span style="font-size:15px">{icon}</span>
            </td>
            <td style="padding:5px 12px 5px 0;white-space:nowrap;vertical-align:middle;width:160px">
              <span style="font-size:12px;font-weight:600;color:{C['text']}">{role}</span>
            </td>
            <td style="padding:5px 0;vertical-align:middle">
              <div style="background:{C['bg']};border-radius:4px;height:14px;width:100%">
                <div style="background:{C['accent']};border-radius:4px;height:14px;width:{bar}%;
                            min-width:4px"></div>
              </div>
            </td>
            <td style="padding:5px 0 5px 12px;white-space:nowrap;vertical-align:middle;width:40px;text-align:right">
              <span style="font-size:13px;font-weight:700;color:{C['accent']}">{h_str}</span>
            </td>
            <td style="padding:5px 0 5px 8px;white-space:nowrap;vertical-align:middle;width:55px">
              <span style="font-size:10px;color:{C['muted']}">{count} task{'s' if count != 1 else ''}</span>
            </td>
          </tr>"""

    return f"""
  <tr>
    <td style="background:{C['card']};padding:0;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td bgcolor="#24292f" style="background:linear-gradient(135deg,#24292f,#1b1f23);padding:10px 24px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;
                      color:rgba(255,255,255,0.7)">Skills Augmented</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">
            This is the team Claude assembled for me &mdash; on demand, at zero headcount cost.</div>
        </td></tr>
      </table>
      <div style="padding:14px 24px 18px">
        <div style="font-size:11px;color:{C['muted']};margin-bottom:14px">
          {_fmt_h(total_hours)} of expert-level assistance across {n_roles} professional discipline{'s' if n_roles != 1 else ''} &middot; {total_tasks} tasks delivered</div>
        <table width="100%" cellpadding="0" cellspacing="0">
          {rows}
        </table>
      </div>
    </td>
  </tr>"""


# ─────────────────────────────────────────────────────────────────────────────
# "What Got Produced" section
# ─────────────────────────────────────────────────────────────────────────────

def _what_got_produced(goals: list, sessions: list) -> str:
    """Deliverables: doc files referenced, GitHub repos, and git operations."""
    import re as _r

    # Collect docs referenced across goals
    docs: dict = {}
    for g in goals:
        for d in g.get("docs_referenced", []):
            if d and d not in docs:
                docs[d] = g.get("project", "")

    # Collect GitHub repos and git ops from sessions
    git_repos: dict = {}    # repo → project
    git_ops_by_proj: dict = {}  # project → set of op types
    for s in sessions:
        proj = s.get("project", "")
        for repo in s.get("git_repos", []):
            git_repos.setdefault(repo, proj)
        ops = set()
        for op in s.get("git_ops", []):
            op_lower = str(op).lower()
            if "pr" in op_lower or "pull-request" in op_lower:
                ops.add("PR")
            elif "push" in op_lower:
                ops.add("push")
            elif "commit" in op_lower:
                ops.add("commit")
        if ops:
            git_ops_by_proj.setdefault(proj, set()).update(ops)

    if not docs and not git_repos and not git_ops_by_proj:
        return ""

    # Doc file categories
    DOC_CATS = {
        "Scripts":       {"icon": "&#128187;", "exts": {".py", ".js", ".ts", ".sh", ".ps1"}},
        "Reports":       {"icon": "&#128202;", "exts": {".html", ".htm"}},
        "Documents":     {"icon": "&#128196;", "exts": {".md", ".txt", ".docx", ".pdf", ".doc"}},
        "Data":          {"icon": "&#9881;",   "exts": {".json", ".yaml", ".yml", ".csv", ".toml"}},
        "Presentations": {"icon": "&#128209;", "exts": {".pptx", ".ppt"}},
        "Notebooks":     {"icon": "&#128218;", "exts": {".ipynb"}},
    }
    cat_files: dict = {k: [] for k in DOC_CATS}
    for fname, proj in docs.items():
        ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        for cat, info in DOC_CATS.items():
            if ext in info["exts"]:
                cat_files[cat].append((fname, proj))
                break

    # Build category counts row
    cat_cells = ""
    for cat, info in DOC_CATS.items():
        n = len(cat_files[cat])
        if n == 0:
            continue
        cat_cells += (
            f'<td style="padding:8px 12px;text-align:center;vertical-align:top">'
            f'<div style="font-size:22px;font-weight:700;color:{C["accent"]};line-height:1">{n}</div>'
            f'<div style="font-size:9px;font-weight:600;color:{C["muted"]};margin-top:3px;'
            f'text-transform:uppercase;letter-spacing:0.4px">{info["icon"]} {cat}</div>'
            f'</td>'
        )

    # Repo rows
    repo_html = ""
    if git_repos:
        repo_items = ""
        for repo, proj in list(git_repos.items())[:6]:
            ops = git_ops_by_proj.get(proj, set())
            ops_str = " · ".join(sorted(ops)) if ops else ""
            repo_items += (
                f'<div style="display:inline-block;margin:3px 6px 3px 0;padding:3px 10px;'
                f'background:{C["green_lt"]};border:1px solid rgba(26,127,55,0.2);'
                f'border-radius:10px;font-size:11px">'
                f'<span style="color:{C["green"]};font-weight:600">&#128257; {repo}</span>'
                + (f'<span style="color:{C["muted"]};margin-left:6px">({ops_str})</span>' if ops_str else "")
                + f'</div>'
            )
        repo_html = f'<div style="margin-top:10px"><div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:{C["muted"]};margin-bottom:6px">GitHub Repos</div>{repo_items}</div>'
    elif git_ops_by_proj:
        ops_items = ""
        for proj, ops in git_ops_by_proj.items():
            ops_str = " · ".join(sorted(ops))
            ops_items += (
                f'<div style="display:inline-block;margin:3px 6px 3px 0;padding:3px 10px;'
                f'background:{C["green_lt"]};border-radius:10px;font-size:11px">'
                f'<span style="color:{C["green"]};font-weight:600">&#10003; {proj}</span>'
                f'<span style="color:{C["muted"]};margin-left:6px">({ops_str})</span>'
                f'</div>'
            )
        repo_html = f'<div style="margin-top:10px">{ops_items}</div>'

    doc_count = len(docs)
    doc_summary = f'<strong style="color:{C["text"]}">{doc_count} file{"s" if doc_count != 1 else ""}</strong> referenced or produced' if doc_count else ""

    # Build "see all files" expandable list grouped by category
    all_files_html = ""
    if doc_count:
        cat_sections = ""
        for cat, info in DOC_CATS.items():
            files = cat_files[cat]
            if not files:
                continue
            file_items = "".join(
                f'<span style="display:inline-block;margin:2px 6px 2px 0;font-size:11px;'
                f'color:{C["accent"]};font-weight:500">'
                f'{info["icon"]} {fname}</span>'
                for fname, _ in files
            )
            cat_sections += (
                f'<div style="margin-bottom:8px">'
                f'<div style="font-size:9px;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.6px;color:{C["muted"]};margin-bottom:4px">'
                f'{cat} ({len(files)})</div>'
                f'<div>{file_items}</div>'
                f'</div>'
            )
        all_files_html = (
            f'<div style="margin-top:8px">'
            f'<span id="all-files-btn" data-open="0" onclick="toggleAllFiles()" '
            f'style="cursor:pointer;font-size:11px;color:{C["accent"]};user-select:none">'
            f'&#9654; See all files</span>'
            f'</div>'
            f'<div id="all-files-list" style="display:none;margin-top:10px;'
            f'padding:10px 12px;background:{C["subtle"]};border-radius:6px;'
            f'border:1px solid {C["border"]}">'
            f'{cat_sections}'
            f'</div>'
        )

    return f"""
  <tr>
    <td style="background:{C['card']};padding:0;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td bgcolor="#24292f" style="background:linear-gradient(135deg,#24292f,#1b1f23);padding:10px 24px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;
                      color:rgba(255,255,255,0.7)">What Got Produced</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">
            Real deliverables that exist because Claude was on your team.</div>
        </td></tr>
      </table>
      <div style="padding:14px 24px 18px">
        {f'<div style="font-size:11px;color:{C["muted"]};margin-bottom:10px">{doc_summary}</div>' if doc_summary else ""}
        {f'<table cellpadding="0" cellspacing="0"><tr>{cat_cells}</tr></table>' if cat_cells else ""}
        {all_files_html}
        {repo_html}
      </div>
    </td>
  </tr>"""


# ─────────────────────────────────────────────────────────────────────────────
# Activity / pricing bar
# ─────────────────────────────────────────────────────────────────────────────

def _activity_bar(analysis: dict) -> str:
    """Token cost breakdown bar."""
    tokens = analysis.get("tokens", {})
    in_tok  = tokens.get("input", 0)
    out_tok = tokens.get("output", 0)
    cr_tok  = tokens.get("cache_read", 0)
    cc_tok  = tokens.get("cache_creation", 0)
    total_tok = tokens.get("total", 0) or (in_tok + out_tok + cr_tok + cc_tok)
    total_s   = total_tok or 1

    market_cost = (in_tok * 3.00 + out_tok * 15.00
                 + cr_tok * 0.30 + cc_tok * 3.75) / 1_000_000

    premium_req = analysis.get("premium_requests", 0)
    prem_html = ""
    if premium_req:
        prem_html = (f'&nbsp;&nbsp;·&nbsp;&nbsp;'
                     f'<span style="font-size:11px;color:{C["text"]}">'
                     f'<span style="color:{C["muted"]}">Model requests</span> '
                     f'<strong>{premium_req:,}</strong></span>')

    tok_str = f"{total_tok/1_000:.0f}K" if total_tok < 1_000_000 else f"{total_tok/1_000_000:.1f}M"

    return f"""
  <tr>
    <td style="background:{C['card']};padding:0;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td bgcolor="#24292f" style="background:linear-gradient(135deg,#24292f,#1b1f23);padding:10px 24px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;
                      color:rgba(255,255,255,0.7)">By the Numbers</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">
            Every token has a return. Here&rsquo;s yours.</div>
        </td></tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style="background:{C['subtle']};padding:9px 24px;
               border:1px solid {C['border']};border-top:none">
      <span style="font-size:10px;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.7px;color:{C['muted']};margin-right:10px">Tokens</span>
      <span style="font-size:11px;color:{C['text']}">
        <span style="color:{C['muted']}">Input</span> <strong>{in_tok:,}</strong>
        &nbsp;({in_tok/total_s*100:.0f}%)
      </span>
      &nbsp;&nbsp;·&nbsp;&nbsp;
      <span style="font-size:11px;color:{C['text']}">
        <span style="color:{C['muted']}">Output</span> <strong>{out_tok:,}</strong>
        &nbsp;({out_tok/total_s*100:.0f}%)
      </span>
      &nbsp;&nbsp;·&nbsp;&nbsp;
      <span style="font-size:11px;color:{C['text']}">
        <span style="color:{C['muted']}">Cache hits</span> <strong>{cr_tok:,}</strong>
        &nbsp;({cr_tok/total_s*100:.0f}%)
      </span>
      &nbsp;&nbsp;·&nbsp;&nbsp;
      <span style="font-size:11px;color:{C['text']}">
        <span style="color:{C['muted']}">Cache written</span> <strong>{cc_tok:,}</strong>
      </span>
    </td>
  </tr>"""


# ─────────────────────────────────────────────────────────────────────────────
# Estimation Evidence section
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_metrics(project: str, session_metrics: dict, goal_date: str = "") -> dict:
    """Find the best-matching session metrics entry for a project+date."""
    if not session_metrics:
        return {}
    if goal_date:
        dated_key = goal_date + "|" + project
        metrics = session_metrics.get(dated_key, {})
        if metrics:
            return metrics
        last = project.replace("\\", "/").split("/")[-1]
        metrics = session_metrics.get(goal_date + "|" + last, {})
        if metrics:
            return metrics
    # Fall back to non-dated key (single-day reports)
    if project in session_metrics:
        return session_metrics[project]
    last = project.replace("\\", "/").split("/")[-1]
    if last in session_metrics:
        return session_metrics[last]
    if len(session_metrics) == 1:
        return next(iter(session_metrics.values()))
    return {}


# ── Deterministic effort formula ─────────────────────────────────────────────

def compute_formula_estimate(metrics: dict) -> dict:
    """Additive log formula — deterministic transparency floor.

    total = turns_h + lines_h + reads_h

    turns_h  = max(0, -0.15 + 0.67 × ln(turns + 1))
    lines_h  = 0.40 × log2(lines_logic / 100 + 1)
    reads_h  = 0.10 × log2(read_calls + 1)

    Calibrated on OLS regression of 48 days of AI-analysed sessions (R²≈0.40).
    This is a floor — AI semantic judgment explains the remaining variance.
    """
    import math

    turns  = metrics.get("substantive_turns", 0) or metrics.get("conversation_turns", 0)
    lines_logic = metrics.get("lines_logic", 0)
    reads  = metrics.get("reads", 0)
    searches = metrics.get("searches", 0)
    read_calls = reads + searches

    turns_h = max(0.0, -0.15 + 0.67 * math.log(turns + 1))
    lines_h = 0.40 * math.log2(lines_logic / 100 + 1)
    reads_h = 0.10 * math.log2(read_calls + 1)

    # Per-day formula total for multi-day merged goals
    per_day_total = metrics.get("_per_day_formula_total")
    if per_day_total is not None:
        return {
            "turns_h": round(turns_h, 2), "lines_h": round(lines_h, 2),
            "reads_h": round(reads_h, 2), "total": per_day_total,
        }

    raw = turns_h + lines_h + reads_h
    total = max(raw, 0.25)
    total = round(total * 4) / 4

    return {
        "turns_h": round(turns_h, 2),
        "lines_h": round(lines_h, 2),
        "reads_h": round(reads_h, 2),
        "total":   total,
    }


def _evidence_strip(goal: dict, session_metrics: dict) -> str:
    """Compact metrics bar showing evidence and formula behind a goal's estimate."""
    project = goal.get("project", "")
    metrics = _resolve_metrics(project, session_metrics, goal.get("date", ""))
    if not metrics:
        return ""

    fe = compute_formula_estimate(metrics)

    turns = metrics.get("substantive_turns", 0) or metrics.get("conversation_turns", 0)
    lines_logic = metrics.get("lines_logic", 0)
    lines_bp    = metrics.get("lines_boilerplate", 0)
    reads       = metrics.get("reads", 0)
    searches    = metrics.get("searches", 0)
    read_calls  = reads + searches

    # Formula component display
    parts = []
    if turns:
        parts.append(f"<strong>{turns}</strong> turns &rarr; {_fmt_h(fe['turns_h'])}")
    if lines_logic:
        logic_str = f"<strong>+{lines_logic:,}</strong> logic lines &rarr; {_fmt_h(fe['lines_h'])}"
        if lines_bp:
            logic_str += ' <span style="color:' + C["muted"] + ';font-size:9px">+' + f'{lines_bp:,}' + 'bp</span>'
        parts.append(logic_str)
    if read_calls:
        parts.append(f"<strong>{read_calls}</strong> reads &rarr; {_fmt_h(fe['reads_h'])}")

    if not parts:
        return ""

    formula_h = _fmt_h(fe["total"])
    ai_h      = _fmt_h(goal.get("human_hours", 0))
    import hashlib as _hl
    _key = (goal.get('title', '') + goal.get('date', '')).encode()
    fid  = "fs-" + _hl.sha1(_key).hexdigest()[:12]

    return f"""
            <div style="padding:8px 24px;background:{C['subtle']};border-bottom:1px solid {C['border']}">
              <div style="font-size:10px;color:{C['muted']};line-height:1.5">
                <span style="font-weight:700;color:{C['accent']};margin-right:4px">&#128202;</span>
                {' &middot; '.join(parts)}
                &nbsp;&nbsp;
                <strong style="color:{C['green']}">{ai_h}</strong>
                <span style="color:{C['muted']}"> AI est.</span>
                &nbsp;|&nbsp;
                <span style="color:{C['muted']}">{formula_h} det. floor</span>
              </div>
            </div>"""


def _signal_tier_table(title: str, icon: str, description: str, tiers: list) -> str:
    """Render a single signal explanation table with tiers and multipliers."""
    rows = ""
    for i, (range_label, hour_label, example) in enumerate(tiers):
        bg = C["subtle"] if i % 2 == 0 else C["card"]
        rows += (
            f'<tr style="background:{bg}">'
            f'<td style="padding:3px 10px;font-size:10px;font-weight:600;color:{C["text"]};'
            f'border-bottom:1px solid {C["border"]};width:14%;white-space:nowrap">{range_label}</td>'
            f'<td style="padding:3px 10px;border-bottom:1px solid {C["border"]};width:12%;text-align:center">'
            f'<span style="font-size:10px;font-weight:700;color:{C["accent"]};'
            f'background:{C["accent_lt"]};padding:1px 8px;border-radius:8px">{hour_label}</span></td>'
            f'<td style="padding:3px 10px;font-size:10px;color:{C["muted"]};'
            f'border-bottom:1px solid {C["border"]};width:74%">{example}</td>'
            f'</tr>'
        )
    return f"""
        <div style="margin-top:14px">
          <div style="font-size:10px;font-weight:700;color:{C['text']};margin-bottom:2px">
            {icon} {title}</div>
          <div style="font-size:10px;color:{C['muted']};margin-bottom:6px;line-height:1.4">
            {description}</div>
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border:1px solid {C['border']};border-radius:5px;overflow:hidden">
            <tr style="background:{C['accent_lt']}">
              <th style="padding:3px 10px;font-size:9px;font-weight:700;color:{C['accent']};
                         text-transform:uppercase;letter-spacing:0.5px;
                         border-bottom:1px solid {C['border']};width:14%">Range</th>
              <th style="padding:3px 10px;font-size:9px;font-weight:700;color:{C['accent']};
                         text-transform:uppercase;letter-spacing:0.5px;text-align:center;
                         border-bottom:1px solid {C['border']};width:12%">Multiplier</th>
              <th style="padding:3px 10px;font-size:9px;font-weight:700;color:{C['accent']};
                         text-transform:uppercase;letter-spacing:0.5px;
                         border-bottom:1px solid {C['border']};width:74%">What this means</th>
            </tr>
            {rows}
          </table>
        </div>"""


def _signal_guide() -> str:
    """Detailed explanation of each session signal with tiered examples."""
    turns = _signal_tier_table(
        "Conversation Turns", "&#128172;",
        "Substantive user instructions (≥20 chars, not trivial confirmations like 'ok', 'commit', 'push'). "
        "~5–7 min/turn average for a human, accounting for a mix of quick directives and deep thinking.",
        [
            ("1–3",   "0.25h", "Quick Q&A &mdash; a single instruction or question. "
                               "<em>\"Fix this typo in config.yaml\"</em>"),
            ("4–8",   "0.75h", "Focused task &mdash; a clear goal with a few refinements. "
                               "<em>\"Add error handling to the upload endpoint\"</em>"),
            ("9–15",  "1.5h",  "Working session &mdash; iterating on a feature or bug fix. "
                               "<em>\"Refactor the auth module to use JWT\"</em>"),
            ("16–30", "3h",    "Extended session &mdash; design + implement + iterate. "
                               "<em>\"Build the report generation pipeline\"</em>"),
            ("31–60", "5h",    "Deep collaboration &mdash; complex feature from scratch. "
                               "<em>\"Ship an executive deck builder from concept to working system\"</em>"),
            ("61–100","8h",    "Full-day partnership &mdash; comprehensive system build. "
                               "<em>\"Redesign the entire report layout with data pipeline\"</em>"),
            ("100+",  "10h",   "Multi-day project &mdash; extensive system overhaul. "
                               "<em>\"Architect and ship a complete analytics platform\"</em>"),
        ]
    )
    lines = _signal_tier_table(
        "Lines of Code", "&#128196;",
        "Net lines added to the project. Expert writes 100–150 LoC/hr; used as an additive "
        "component on top of the base signal (turns/tools/active).",
        [
            ("1–50",    "0.25h", "Config tweak &mdash; a setting, a one-liner, a small fix"),
            ("50–150",  "0.75h", "Small feature &mdash; a new function, helper, or template. "
                                 "<em>\"Add a utility function with error handling\"</em>"),
            ("150–300", "1.5h",  "Moderate module &mdash; a new component or significant feature. "
                                 "<em>\"Build the session harvester with event parsing\"</em>"),
            ("300–500", "2.5h",  "Major implementation &mdash; substantial new capability. "
                                 "<em>\"Implement the full report generation pipeline\"</em>"),
            ("500–800", "4h",    "Large feature &mdash; a complete subsystem or tool. "
                                 "<em>\"Ship 700+ lines of dashboard conversion code\"</em>"),
            ("800+",    "n/200h","Continuous scale &mdash; e.g. 1,000 lines = 5h, 2,000 lines = 10h. "
                                 "<em>\"Full system build with extensive scaffolding\"</em>"),
        ]
    )
    active = _signal_tier_table(
        "Active Engagement Time", "&#9201;",
        "Time actively engaged with Claude, excluding idle gaps longer than 10 minutes. "
        "Multiplier is <strong>3&times; active time</strong> &mdash; midpoint of the 1.4&ndash;4&times; "
        "range found in peer-reviewed research (Cambon 2023, Peng 2023).",
        [
            ("&lt; 5m",    "0.25h", "Quick task &mdash; one-shot edit, single question"),
            ("5–15m",      "0.75h", "Focused task &mdash; fix a bug, write a function"),
            ("15–45m",     "1.5–2h","Working session &mdash; implement and test a feature"),
            ("45m–2h",     "2–6h",  "Deep work &mdash; multi-step design, implementation, and refinement"),
            ("2–6h",       "6–18h", "Extended session &mdash; full feature build across multiple iterations"),
            ("6h+",        "18h+",  "Marathon project &mdash; comprehensive system build over many hours"),
        ]
    )
    return f"""
        <div style="margin-top:16px;padding-top:12px;border-top:1px solid {C['border']}">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;
                      color:{C['muted']};margin-bottom:4px;cursor:pointer;user-select:none"
               onclick="toggleSignalGuide()">
            <span id="signal-guide-arrow" style="margin-right:4px">&#9654;</span>What each signal means
          </div>
          <div id="signal-guide-body" style="display:none">
            <div style="font-size:10px;color:{C['muted']};line-height:1.5;margin-bottom:4px">
              Each session signal maps to a multiplier representing equivalent human effort. The AI
              reads all signals together and assigns an estimate within the highest applicable range.
              <br><strong style="color:{C['text']}">Reading the table:</strong> find your value in the
              Range column &rarr; the Multiplier shows the hour contribution from that signal alone.
            </div>
            {turns}
            {lines}
            {active}
          </div>
        </div>"""


def _estimation_waterfall_inner(goals: list, analysis: dict) -> str:
    """Evidence table — raw signals, complexity multipliers, formula vs AI estimate."""
    session_metrics = analysis.get("session_metrics", {})
    if not goals:
        return ""

    VISIBLE = 5
    total_h = sum(g.get("human_hours", 0) for g in goals)
    total_formula_h = 0.0

    rows = ""
    for i, g in enumerate(goals):
        bg = C["subtle"] if i % 2 == 0 else C["card"]
        project = g.get("project", "")
        metrics = _resolve_metrics(project, session_metrics, g.get("date", ""))
        fe = compute_formula_estimate(metrics)
        total_formula_h += fe["total"]

        turns      = metrics.get("substantive_turns", 0) or metrics.get("conversation_turns", 0)
        lines_logic = metrics.get("lines_logic", 0)
        lines_bp   = metrics.get("lines_boilerplate", 0)
        reads      = metrics.get("reads", 0)
        searches   = metrics.get("searches", 0)
        read_calls = reads + searches
        ai_h       = _fmt_h(g.get("human_hours", 0))
        formula_h  = _fmt_h(fe["total"])

        turns_h_str  = _fmt_h(fe["turns_h"]) if fe["turns_h"] > 0 else "&mdash;"
        lines_h_str  = _fmt_h(fe["lines_h"]) if fe["lines_h"] > 0 else "&mdash;"
        reads_h_str  = _fmt_h(fe["reads_h"]) if fe["reads_h"] > 0 else "&mdash;"

        title = g.get("label") or g.get("title", "")
        if len(title) > 40:
            title = title[:37] + "..."

        lines_display = f"+{lines_logic:,}"
        if lines_bp:
            lines_display += f' <span style="font-size:8px;color:{C["muted"]}">+{lines_bp:,}bp</span>'

        # See-more toggle row before row VISIBLE
        if i == VISIBLE and len(goals) > VISIBLE:
            n_extra = len(goals) - VISIBLE
            rows += f"""
        <tr id="evidence-more-toggle" style="cursor:pointer;background:{C['accent_lt']}"
            onclick="var rows=document.getElementsByClassName('evidence-extra-row');
                     var show=rows.length && rows[0].style.display==='none';
                     for(var j=0;j<rows.length;j++){{rows[j].style.display=show?'':'none';}}
                     this.style.display='none';">
          <td colspan="7" style="padding:6px 10px;text-align:center;font-size:11px;
                     font-weight:600;color:{C['accent']}">
            &#9660; Show {n_extra} more project{'s' if n_extra != 1 else ''}</td>
        </tr>"""

        extra = len(goals) > VISIBLE and i >= VISIBLE
        extra_attrs = (f' class="evidence-extra-row" style="display:none;background:{bg}"'
                       if extra else f' style="background:{bg}"')

        rows += f"""
        <tr{extra_attrs}>
          <td style="padding:6px 8px;border-bottom:1px solid {C['border']};vertical-align:middle">
            <div style="font-size:11px;font-weight:600;color:{C['text']};line-height:1.3">{title}</div>
          </td>
          <td style="padding:4px 5px;font-size:11px;color:{C['text']};text-align:center;
                     font-weight:600">{turns}</td>
          <td style="padding:4px 5px;font-size:10px;color:{C['muted']};text-align:center">
            {turns_h_str}</td>
          <td style="padding:4px 5px;font-size:11px;color:{C['text']};text-align:center">
            {lines_display}</td>
          <td style="padding:4px 5px;font-size:10px;color:{C['muted']};text-align:center">
            {lines_h_str}</td>
          <td style="padding:4px 5px;font-size:11px;color:{C['text']};text-align:center;
                     font-weight:600">{read_calls}</td>
          <td style="padding:4px 5px;text-align:center;vertical-align:middle">
            <div style="font-size:14px;font-weight:700;color:{C['green']}">{ai_h}</div>
            <div style="font-size:8px;color:{C['muted']};text-transform:uppercase;margin-top:1px">AI est.</div>
            <div style="font-size:11px;font-weight:600;color:{C['accent']};margin-top:2px">{formula_h}</div>
            <div style="font-size:8px;color:{C['muted']};text-transform:uppercase">det. floor</div>
          </td>
        </tr>"""

    # Total row
    rows += f"""
        <tr style="background:{C['accent_lt']}">
          <td style="padding:8px 8px;border-top:2px solid {C['border']};
                     font-size:11px;font-weight:700;color:{C['accent']};text-align:right" colspan="6">
            Total</td>
          <td style="padding:8px 5px;border-top:2px solid {C['border']};text-align:center">
            <div style="font-size:16px;font-weight:700;color:{C['green']}">{_fmt_h(total_h)}</div>
            <div style="font-size:11px;font-weight:600;color:{C['accent']}">{_fmt_h(total_formula_h)}</div>
          </td>
        </tr>"""

    th_style = (f"padding:6px 5px;text-align:center;font-size:8px;font-weight:700;"
                f"color:{C['accent']};text-transform:uppercase;letter-spacing:0.4px;"
                f"border-bottom:1px solid {C['border']}")
    th_muted = th_style.replace(f"color:{C['accent']}", f"color:{C['muted']}")
    th_green = th_style.replace(f"color:{C['accent']}", f"color:{C['green']}")

    return f"""
  <tr>
    <td style="background:{C['card']};padding:0;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td bgcolor="#24292f" style="background:linear-gradient(135deg,#24292f,#1b1f23);padding:10px 24px;
                cursor:pointer" onclick="toggleEstimation()">
          <div id="evidence-hdr" style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;
                      color:rgba(255,255,255,0.7)">
            <span id="estimation-arrow" style="margin-right:6px">&#9654;</span>Estimation Evidence</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">
            How human effort estimates were calculated — signal by signal.</div>
        </td></tr>
      </table>
      <div id="estimation-body" style="display:none;padding:14px 24px 18px">
        <div style="font-size:11px;color:{C['text']};margin-bottom:14px;line-height:1.7">
          <strong>Why we lead with AI estimation:</strong>
          The AI reads your full session transcript — every instruction, every tool action,
          every code change — and understands <em>what</em> was accomplished, not just how many
          actions were taken. It distinguishes a 200-line boilerplate scaffold from a 50-line
          algorithm that required deep design thinking, and recognises that "commit and push"
          is 0.25h regardless of how many tool calls it triggered.
          <br><span style="font-size:10px;color:{C['muted']}">
          Calibrated against peer-reviewed research (Cambon 2023, Alaswad 2026, Ziegler 2024, Tregubov 2017)</span>
        </div>
        <div style="font-size:10px;color:{C['muted']};margin-bottom:10px;padding:8px 12px;
                    background:{C['subtle']};border-radius:6px;border:1px solid {C['border']}">
          Det. Est. = turns_h + lines_h + reads_h (deterministic formula)
          &nbsp;&middot;&nbsp;
          Lines = logic code only (.py/.ts/.go/&hellip; &mdash; HTML/CSS/JSON/MD excluded)
          &nbsp;&middot;&nbsp;
          AI Est. = semantic AI analysis
        </div>
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border:1px solid {C['border']};border-radius:7px;overflow:hidden">
          <tr style="background:{C['accent_lt']}">
            <th style="{th_style};text-align:left;width:24%">Project</th>
            <th style="{th_style};width:8%">Turns</th>
            <th style="{th_muted};width:8%">turns_h</th>
            <th style="{th_style};width:12%">Logic Lines</th>
            <th style="{th_muted};width:8%">lines_h</th>
            <th style="{th_style};width:8%">Reads</th>
            <th style="{th_green};width:12%">AI Est. / Det.</th>
          </tr>
          {rows}
        </table>
        <div style="margin-top:12px;padding:10px 12px;
                    background:{C['subtle']};border:1px solid {C['border']};border-radius:6px">
          <div style="font-size:10px;font-weight:700;color:{C['text']};margin-bottom:6px">
            Deterministic Formula (transparency floor)</div>
          <div style="font-family:monospace;font-size:10px;color:{C['muted']};line-height:1.5;
                      padding:6px 8px;background:{C['card']};border-radius:4px;margin-bottom:8px">
            total = turns_h + lines_h + reads_h<br>
            turns_h  = max(0, &minus;0.15 + 0.67 &times; ln(turns + 1))<br>
            lines_h  = 0.40 &times; log&#8322;(logic_lines / 100 + 1)<br>
            reads_h  = 0.10 &times; log&#8322;(read_calls + 1)
          </div>
          <div style="font-size:10px;color:{C['muted']};line-height:1.5;margin-bottom:8px">
            Three questions added together: How deep was the collaboration? How much logic code was
            written (not HTML/CSS/JSON/MD)? How much investigation happened?
          </div>
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border:1px solid {C['border']};border-radius:5px;overflow:hidden;font-size:10px">
            <tr style="background:{C['accent_lt']}">
              <th style="padding:4px 8px;text-align:left;color:{C['accent']};font-weight:700">Term</th>
              <th style="padding:4px 8px;text-align:left;color:{C['accent']};font-weight:700">Formula</th>
              <th style="padding:4px 8px;text-align:left;color:{C['accent']};font-weight:700">Sample values</th>
            </tr>
            <tr style="background:{C['card']}">
              <td style="padding:3px 8px;border-bottom:1px solid {C['border']}">turns_h</td>
              <td style="padding:3px 8px;border-bottom:1px solid {C['border']};font-family:monospace">max(0, &minus;0.15 + 0.67&times;ln(n+1))</td>
              <td style="padding:3px 8px;border-bottom:1px solid {C['border']};color:{C['muted']}">5 turns=0.9h &middot; 15=1.7h &middot; 40=2.5h</td>
            </tr>
            <tr style="background:{C['subtle']}">
              <td style="padding:3px 8px;border-bottom:1px solid {C['border']}">lines_h</td>
              <td style="padding:3px 8px;border-bottom:1px solid {C['border']};font-family:monospace">0.40&times;log&#8322;(logic/100+1)</td>
              <td style="padding:3px 8px;border-bottom:1px solid {C['border']};color:{C['muted']}">100 lines=0.4h &middot; 500=0.93h &middot; 1000=1.2h</td>
            </tr>
            <tr style="background:{C['card']}">
              <td style="padding:3px 8px">reads_h</td>
              <td style="padding:3px 8px;font-family:monospace">0.10&times;log&#8322;(reads+searches+1)</td>
              <td style="padding:3px 8px;color:{C['muted']}">10 reads=0.33h &middot; 50=0.57h &middot; 100=0.66h</td>
            </tr>
          </table>
        </div>
      </div>
    </td>
  </tr>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main generate_html
# ─────────────────────────────────────────────────────────────────────────────

def generate_html(target_date: str, analysis: dict, sessions: list, max_width: int = 700) -> str:
    goals           = analysis.get("goals", [])
    narrative       = analysis.get("day_narrative", "")
    headline        = analysis.get("headline", f"Daily Report — {target_date}")
    focus           = analysis.get("primary_focus", "")
    tokens          = analysis.get("tokens", {})
    n_sessions      = analysis.get("sessions_count", len(sessions))
    session_metrics = analysis.get("session_metrics", {})
    # Use live session data for projects — never the cached list
    projects = sorted({s["project"] for s in sessions})

    total_human_h = sum(g.get("human_hours", 0) for g in goals)
    total_tasks   = sum(len(g.get("tasks", [])) for g in goals)

    # Build project-name → session lookup for directory + git context.
    # Include both full decoded names AND last path segment so cached analyses
    # (which stored short names like "whatidid") still resolve correctly.
    session_lookup = {}
    for s in sessions:
        session_lookup[s["project"]] = s
        last = s["project"].replace("\\", "/").split("/")[-1]
        session_lookup.setdefault(last, s)

    # Build mapping from raw session project names → goal display labels
    # so session-based sections (collaboration) use consistent names.
    _norm = lambda s: s.lower().replace("-", " ").replace("_", " ").strip()
    project_label_map: dict = {}
    for g in goals:
        raw = g.get("project", "")
        label = g.get("label") or g.get("title", "")
        if raw and label:
            project_label_map[raw] = label
            last = raw.replace("\\", "/").split("/")[-1]
            project_label_map.setdefault(last, label)
    # Fuzzy-match unmapped session projects by normalized name
    goal_norm_map = {_norm(g.get("project", "")): g for g in goals if g.get("project")}
    for s in sessions:
        sp = s.get("project", "")
        if sp and sp not in project_label_map:
            matched = goal_norm_map.get(_norm(sp))
            if matched:
                lbl = matched.get("label") or matched.get("title", "")
                if lbl:
                    project_label_map[sp] = lbl

    # Compute PR and commit counts from session data
    _seen_prs: set = set()
    _total_commits = 0
    for s in sessions:
        for pr in s.get("pull_requests", []):
            _seen_prs.add(pr)
        _total_commits += s.get("git_commits", 0)
    total_prs     = len(_seen_prs)
    total_commits = _total_commits

    js = """
<script>
function toggleDetail(id) {
  var tasks  = document.getElementById(id + '-tasks');
  var arrow  = document.getElementById(id + '-arrow');
  var hdr    = document.getElementById(id + '-hdr');
  if (!tasks) return;
  var showVal = tasks.tagName.toLowerCase() === 'tr' ? 'table-row' : 'block';
  var open = tasks.style.display === showVal;
  tasks.style.display      = open ? 'none'      : showVal;
  hdr.style.background     = open ? ''           : '#e8f2fb';
  if (arrow) arrow.innerHTML = open ? '&#9654;' : '&#9660;';
}
function toggleFormula(id) {
  var el = document.getElementById(id);
  var arrow = document.getElementById(id + '-arrow');
  if (!el) return;
  var open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  if (arrow) arrow.innerHTML = open ? '&#9654; formula' : '&#9660; formula';
}
function toggleFormulaCol() {
  var cols = document.querySelectorAll('.formula-col');
  var btn = document.getElementById('formula-col-toggle');
  var open = btn && btn.getAttribute('data-open') === '1';
  cols.forEach(function(c) { c.style.display = open ? 'none' : ''; });
  if (btn) {
    btn.setAttribute('data-open', open ? '0' : '1');
    btn.innerHTML = open ? '&#9654; Show formula column' : '&#9660; Hide formula column';
  }
}
function toggleGoalsMore(n) {
  var extras = document.querySelectorAll('.goal-extra');
  var btn = document.getElementById('goals-more-btn');
  var open = btn && btn.getAttribute('data-open') === '1';
  extras.forEach(function(el) { el.style.display = open ? 'none' : ''; });
  if (btn) {
    btn.setAttribute('data-open', open ? '0' : '1');
    btn.innerHTML = open ? '&#9654; See ' + n + ' more projects' : '&#9660; See fewer';
  }
}
function toggleNarrativeMore(n) {
  var more = document.getElementById('narrative-more');
  var btn  = document.getElementById('narrative-more-btn');
  var open = btn && btn.getAttribute('data-open') === '1';
  if (more) more.style.display = open ? 'none' : 'block';
  if (btn) {
    btn.setAttribute('data-open', open ? '0' : '1');
    btn.innerHTML = open ? '&#9654; See ' + n + ' more projects' : '&#9660; See fewer';
  }
}
function toggleAllFiles() {
  var list = document.getElementById('all-files-list');
  var btn  = document.getElementById('all-files-btn');
  var open = btn && btn.getAttribute('data-open') === '1';
  if (list) list.style.display = open ? 'none' : 'block';
  if (btn) {
    btn.setAttribute('data-open', open ? '0' : '1');
    btn.innerHTML = open ? '&#9654; See all files' : '&#9660; Hide files';
  }
}
function toggleEstimation() {
  var body  = document.getElementById('estimation-body');
  var arrow = document.getElementById('estimation-arrow');
  if (!body) return;
  var open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (arrow) arrow.innerHTML = open ? '&#9654;' : '&#9660;';
}
function toggleSignalGuide() {
  var body  = document.getElementById('signal-guide-body');
  var arrow = document.getElementById('signal-guide-arrow');
  if (!body) return;
  var open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (arrow) arrow.innerHTML = open ? '&#9654;' : '&#9660;';
}
window.onload = function() {
  var hint = document.getElementById('expand-hint');
  if (hint) hint.style.display = 'block';
};
</script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>What I Did — {target_date}</title>
{js}
</head>
<body style="margin:0;padding:0;background:{C['bg']};
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:{C['text']}">

<table width="100%" cellpadding="0" cellspacing="0" style="background:{C['bg']};padding:24px 16px">
<tr><td align="center">
<table width="{max_width}" cellpadding="0" cellspacing="0" style="max-width:{max_width}px;width:100%">

  <!-- PRIVACY BANNER -->
  <tr>
    <td style="background:#f0f8ff;border-bottom:1px solid {C['border']};
               border-left:1px solid {C['border']};border-right:1px solid {C['border']};
               padding:6px 24px;text-align:center">
      <span style="font-size:10px;color:{C['muted']}">
        &#128274; Your data, private to you. No telemetry, no cloud uploads.
      </span>
    </td>
  </tr>

  <!-- HEADER -->
  <tr>
    <td style="background:{C['accent']};border-radius:9px 9px 0 0;padding:22px 24px">
      <div style="font-size:10px;color:rgba(255,255,255,0.6);letter-spacing:1.2px;
                  text-transform:uppercase;margin-bottom:4px">{target_date} &nbsp;·&nbsp; Daily Digest</div>
      <div style="font-size:20px;font-weight:700;color:#fff;line-height:1.3">{headline}</div>
      {f'<div style="margin-top:6px;font-size:12px;color:rgba(255,255,255,0.8)">Focus: <strong>{focus}</strong></div>' if focus else ''}
    </td>
  </tr>

  <!-- NARRATIVE -->
  <tr>
    <td style="background:{C['card']};padding:16px 24px 18px;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      {_narrative_block(goals, narrative)}
    </td>
  </tr>

  {_kpi_section(goals, analysis, n_sessions, total_prs=total_prs, total_commits=total_commits)}

  <!-- WHAT GOT ACCOMPLISHED: summary table + task accordion in one dark-header section -->
  <tr>
    <td style="background:{C['card']};padding:0;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td bgcolor="#24292f" style="background:linear-gradient(135deg,#24292f,#1b1f23);padding:10px 24px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;
                      color:rgba(255,255,255,0.7)">What Got Accomplished</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">
            {len(goals)} project{'s' if len(goals) != 1 else ''} &middot; {total_tasks} task{'s' if total_tasks != 1 else ''} &middot; {_fmt_h(total_human_h)} estimated effort</div>
        </td></tr>
      </table>
      <!-- Inline task accordion -->
      <table width="100%" cellpadding="0" cellspacing="0">
        {_goal_detail_headers(goals, session_lookup, session_metrics)}
      </table>
    </td>
  </tr>

  {_what_got_produced(goals, sessions)}

  {_collaboration_intent(sessions, goals, project_label_map)}

  {_work_pattern(sessions)}

  {_skills_mobilized(goals)}

  {_activity_bar(analysis)}

  {_estimation_waterfall_inner(goals, analysis)}

  <!-- FOOTER -->
  <tr>
    <td style="background:{C['text']};border-radius:0 0 9px 9px;padding:12px 24px;
               text-align:center">
      <div style="font-size:10px;color:rgba(255,255,255,0.4)">
        <strong style="color:rgba(255,255,255,0.65)">whatidid</strong>
        &nbsp;·&nbsp; Claude &nbsp;·&nbsp; {target_date}
      </div>
      <div style="margin-top:6px;font-size:10px;color:rgba(255,255,255,0.35)">
        Get your own report &rarr;
        <a href="https://github.com/shailendrahegde/What-I-Did-Claude"
           style="color:rgba(255,255,255,0.55);text-decoration:none"
           target="_blank">github.com/shailendrahegde/What-I-Did-Claude</a>
      </div>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _top_skills_for_goal(goal: dict, max_domain: int = 2, max_tech: int = 2) -> tuple:
    """Aggregate and deduplicate skills across all tasks in a goal, ranked by frequency."""
    from collections import Counter
    domain_counts: Counter = Counter()
    tech_counts:   Counter = Counter()
    for t in goal.get("tasks", []):
        for s in t.get("domain_skills", []):
            domain_counts[s] += 1
        for s in t.get("tech_skills", []):
            tech_counts[s] += 1
    top_domain = [s for s, _ in domain_counts.most_common(max_domain)]
    top_tech   = [s for s, _ in tech_counts.most_common(max_tech)]
    return top_domain, top_tech


def _doc_refs_html(docs: list) -> str:
    """Show up to 2 doc names then '+N more'."""
    if not docs:
        return ""
    shown   = docs[:2]
    extra   = len(docs) - 2
    parts   = [f'<span style="font-size:11px;color:{C["accent"]};font-weight:500">'
               f'&#128196; {d}</span>' for d in shown]
    if extra > 0:
        parts.append(f'<span style="font-size:11px;color:{C["muted"]}">+{extra} more</span>')
    return '<span style="margin-right:8px">' + '</span><span style="margin-right:8px">'.join(parts) + '</span>'


def _goals_summary(goals: list) -> str:
    """Summary table — skill pills + doc references per goal."""
    rows = ""
    for i, g in enumerate(goals):
        n            = len(g.get("tasks", []))
        h            = _fmt_h(g.get("human_hours", 0))
        bg           = C["subtle"] if i % 2 == 0 else C["card"]
        top_d, top_t = _top_skills_for_goal(g)
        skill_pills  = _pills(top_d, top_t)
        task_sub     = f'{n} task{"s" if n != 1 else ""}'
        docs         = g.get("docs_referenced", [])
        doc_html     = _doc_refs_html(docs)

        date_badge = _date_badge(g.get("date", ""))
        rows += f"""
        <tr style="background:{bg}">
          <td style="padding:12px 16px;border-bottom:1px solid {C['border']};
                     vertical-align:top;width:5%">
            <div style="width:22px;height:22px;background:{C['accent']};border-radius:50%;
                        color:#fff;font-size:11px;font-weight:700;text-align:center;
                        line-height:22px">{i+1}</div>
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid {C['border']};
                     vertical-align:top;width:53%">
            <div style="font-size:13px;font-weight:600;color:{C['text']};line-height:1.35">
              {date_badge}{g.get('label') or g.get('title','')}
            </div>
            {f'<div style="margin-top:5px">{doc_html}</div>' if doc_html else ''}
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid {C['border']};
                     vertical-align:middle;width:28%">
            <div>{skill_pills}</div>
            <div style="font-size:10px;color:{C['muted']};margin-top:5px">{task_sub}</div>
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid {C['border']};
                     vertical-align:middle;text-align:right;width:14%">
            <div style="font-size:16px;font-weight:700;color:{C['accent']}">{h}</div>
            <div style="font-size:10px;color:{C['muted']};margin-top:1px">human est.</div>
          </td>
        </tr>"""
    return rows


def _goal_context_bar(g: dict, session_lookup: dict) -> str:
    """Renders a small context bar showing working directory, git activity, and GitHub repos."""
    project = g.get("project", "")
    sess = session_lookup.get(project, {})
    if not sess:
        return ""

    path      = sess.get("project_path", "")
    git_ops   = sess.get("git_ops", [])
    git_repos = sess.get("git_repos", [])

    parts = []
    if path:
        parts.append(
            f'<span style="font-size:10px;color:{C["muted"]};margin-right:12px">'
            f'&#128193; <code style="font-size:10px;background:{C["bg"]};padding:1px 5px;'
            f'border-radius:3px;color:{C["text"]}">{path}</code></span>'
        )
    if git_repos:
        for repo in git_repos:
            parts.append(
                f'<span style="font-size:10px;color:{C["green"]};font-weight:600;'
                f'margin-right:10px">'
                f'&#128257; <a href="https://github.com/{repo}" style="color:{C["green"]};'
                f'text-decoration:none">{repo}</a></span>'
            )
    elif git_ops:
        # No repo URL found — show a summary of git operations
        import re as _re
        ops_text = "git: " + " · ".join(dict.fromkeys(
            ("push" if "push" in o.lower() else
             "pr"   if "pr create" in o.lower() or "pull-request" in o.lower() else
             "commit" if "commit" in o.lower() else "git")
            for o in git_ops
        ))
        parts.append(
            f'<span style="font-size:10px;color:{C["green"]};font-weight:600">'
            f'&#10003; {ops_text}</span>'
        )

    if not parts:
        return ""
    return (f'<div style="padding:5px 24px 6px;background:{C["subtle"]};'
            f'border-bottom:1px solid {C["border"]}">'
            + "".join(parts) + "</div>")


def _goal_detail_headers(goals: list, session_lookup: dict = None,
                          session_metrics: dict = None) -> str:
    """Interleaved goal header + hidden task detail rows for the detail table."""
    if session_lookup is None:
        session_lookup = {}
    if session_metrics is None:
        session_metrics = {}
    TOP = 5
    extra = max(0, len(goals) - TOP)
    html = ""
    for i, g in enumerate(goals):
        gid   = f"goal-{i}"
        tasks = g.get("tasks", [])
        n     = len(tasks)
        h     = _fmt_h(g.get("human_hours", 0))

        evidence_html = _evidence_strip(g, session_metrics) if session_metrics else ""

        # Goals beyond TOP are hidden; toggled by the "see more" row
        extra_class = ' class="goal-extra"' if i >= TOP else ""
        hdr_style = f"cursor:pointer;background:{C['card']}{';display:none' if i >= TOP else ''}"

        # Clickable goal header row
        html += f"""
        <tr id="{gid}-hdr"{extra_class} style="{hdr_style}"
            onclick="toggleDetail('{gid}')">
          <td style="padding:11px 24px;border-bottom:1px solid {C['border']}">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="vertical-align:middle;width:85%">
                  <span id="{gid}-arrow" style="font-size:11px;color:{C['accent']};
                                                 margin-right:6px">&#9654;</span>
                  <span style="font-size:13px;font-weight:600;color:{C['text']}">
                    {g.get('label') or g.get('title','')}
                  </span>
                  <span style="font-size:11px;color:{C['muted']};margin-left:8px">
                    {n} task{'s' if n!=1 else ''}
                  </span>
                </td>
                <td style="text-align:right;vertical-align:middle;width:15%">
                  <span style="font-size:14px;font-weight:700;color:{C['accent']}">{h}</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Hidden task rows for this goal -->
        <tr id="{gid}-tasks"{extra_class} style="display:none">
          <td style="padding:0 16px 12px;background:{C['bg']}">
            {_goal_context_bar(g, session_lookup)}
            {evidence_html}
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border:1px solid {C['border']};border-radius:6px;overflow:hidden">
              <tr style="background:{C['accent_lt']}">
                <td style="width:3px;padding:0"></td>
                <th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;
                           color:{C['accent']};text-transform:uppercase;letter-spacing:0.5px;
                           border-bottom:1px solid {C['border']};width:35%">Task &amp; Skills</th>
                <th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;
                           color:{C['accent']};text-transform:uppercase;letter-spacing:0.5px;
                           border-bottom:1px solid {C['border']};width:52%">What Got Done</th>
                <th style="padding:6px 12px;text-align:center;font-size:10px;font-weight:700;
                           color:{C['accent']};text-transform:uppercase;letter-spacing:0.5px;
                           border-bottom:1px solid {C['border']};width:13%">Time</th>
              </tr>
              {_task_rows(tasks)}
            </table>
          </td>
        </tr>"""

        # After the 5th goal, insert the "see more" toggle row
        if i == TOP - 1 and extra > 0:
            html += f"""
        <tr id="goals-more-hdr">
          <td style="padding:9px 24px;border-bottom:1px solid {C['border']};
                     background:{C['subtle']}">
            <span id="goals-more-btn" data-open="0"
                  onclick="toggleGoalsMore({extra})"
                  style="cursor:pointer;font-size:12px;color:{C['accent']};
                         user-select:none;font-weight:500">
              &#9654; See {extra} more project{"s" if extra != 1 else ""}
            </span>
          </td>
        </tr>"""

    return html


def _task_rows(tasks: list) -> str:
    rows = ""
    for j, t in enumerate(tasks):
        bg     = C["card"] if j % 2 == 0 else C["subtle"]
        skills = _pills(t.get("domain_skills",[]), t.get("tech_skills",[]))
        h      = _fmt_h(t.get("human_hours", 0))
        rows += f"""
              <tr style="background:{bg}">
                <td style="width:3px;background:{C['accent_lt']};padding:0"></td>
                <td style="padding:10px 12px;border-bottom:1px solid {C['border']};
                           vertical-align:top;width:35%">
                  <div style="font-size:10px;color:{C['muted']};font-weight:600;
                              text-transform:uppercase;letter-spacing:0.4px">Task {j+1}</div>
                  <div style="font-size:12px;font-weight:600;color:{C['text']};
                              margin-top:2px;line-height:1.3">{t.get('title','')}</div>
                  <div style="margin-top:5px">{skills}</div>
                </td>
                <td style="padding:10px 12px;border-bottom:1px solid {C['border']};
                           vertical-align:top;width:52%">
                  <div style="font-size:12px;color:{C['text']};line-height:1.55">
                    {t.get('what_got_done','')}
                  </div>
                </td>
                <td style="padding:10px 12px;border-bottom:1px solid {C['border']};
                           vertical-align:middle;text-align:center;width:13%">
                  <div style="font-size:15px;font-weight:700;color:{C['accent']}">{h}</div>
                  <div style="font-size:9px;color:{C['muted']};text-transform:uppercase;
                              letter-spacing:0.4px;margin-top:1px">human</div>
                </td>
              </tr>"""
    return rows
