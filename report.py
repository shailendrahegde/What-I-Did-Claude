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


def _kpi_section(goals: list, analysis: dict, n_sessions: int) -> str:
    total_human_h = sum(g.get("human_hours", 0) for g in goals)
    n_goals       = len(goals)
    lines_added   = analysis.get("lines_added", 0)
    lines_removed = analysis.get("lines_removed", 0)
    active_dates  = analysis.get("active_dates", [])
    n_active_days = len(active_dates) if active_dates else 1
    total_tasks   = sum(len(g.get("tasks", [])) for g in goals)

    h_str = _fmt_h(total_human_h)
    sessions_label = f"{n_sessions} sessions"

    if lines_added:
        lines_val = f"+{lines_added:,}"
        lines_sub = f"{lines_removed:,} removed"
    else:
        lines_val = "—"
        lines_sub = ""

    return f"""
  <tr>
    <td style="background:{C['bg']};padding:12px 24px;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          {_kpi_card(str(n_goals), "Projects<br>Assisted", sessions_label)}
          {_kpi_card(h_str, "Human Effort<br>Equivalent", f"@ ${HOURLY_RATE}/hr")}
          {_kpi_card(str(total_tasks), "Tasks<br>Delivered", "")}
          {_kpi_card(lines_val, "Lines of Code<br>Added", lines_sub)}
          {_kpi_card(str(n_active_days), "Active<br>Days", "")}
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

def _collaboration_intent(sessions: list, goals: list) -> str:
    """Conic-gradient donut chart with intent legend + per-project bars."""
    from harvest import aggregate_intents, _INTENT_COLORS, _INTENT_ICONS

    data = aggregate_intents(sessions)
    counts   = data.get("counts", {})
    by_proj  = data.get("by_project", {})
    grand_total = data.get("total", 0) or 1

    if not counts:
        return ""

    # Sort descending
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    # Build conic-gradient stops
    stops = []
    cumulative = 0
    for cat, n in sorted_items:
        pct_start = cumulative / grand_total * 100
        cumulative += n
        pct_end = cumulative / grand_total * 100
        color = _INTENT_COLORS.get(cat, "#999")
        stops.append(f"{color} {pct_start:.1f}% {pct_end:.1f}%")
    gradient = ", ".join(stops)

    # Legend rows
    legend_rows = ""
    for cat, n in sorted_items:
        pct   = n / grand_total * 100
        color = _INTENT_COLORS.get(cat, "#999")
        icon  = _INTENT_ICONS.get(cat, "")
        legend_rows += f"""
          <tr>
            <td style="padding:3px 8px 3px 0;vertical-align:middle">
              <span style="display:inline-block;width:10px;height:10px;border-radius:2px;
                           background:{color};vertical-align:middle;margin-right:4px"></span>
              <span style="font-size:11px;color:{C['text']}">{icon} {cat}</span>
            </td>
            <td style="padding:3px 0;width:120px;vertical-align:middle">
              <div style="background:{C['border']};border-radius:3px;height:10px">
                <div style="background:{color};border-radius:3px;height:10px;
                            width:{pct:.0f}%"></div>
              </div>
            </td>
            <td style="padding:3px 0 3px 6px;font-size:10px;color:{C['muted']};
                       white-space:nowrap">{n} ({pct:.0f}%)</td>
          </tr>"""

    # Per-project bars (top 5 projects)
    proj_rows = ""
    top_projs = sorted(by_proj.items(), key=lambda x: sum(x[1].values()), reverse=True)[:5]
    for proj, pcounts in top_projs:
        ptotal = sum(pcounts.values()) or 1
        bar_segments = ""
        for cat, n in sorted(pcounts.items(), key=lambda x: x[1], reverse=True):
            if n == 0:
                continue
            w   = n / ptotal * 100
            col = _INTENT_COLORS.get(cat, "#999")
            bar_segments += (
                f'<div title="{cat}: {n}" style="background:{col};width:{w:.0f}%;'
                f'height:12px;display:inline-block"></div>'
            )
        short_proj = proj.replace("\\", "/").split("/")[-1] if proj else "unknown"
        proj_rows += f"""
          <tr>
            <td style="font-size:11px;color:{C['muted']};padding:3px 8px 3px 0;
                       white-space:nowrap;max-width:120px;overflow:hidden;
                       text-overflow:ellipsis">{short_proj}</td>
            <td style="padding:3px 0;width:100%">
              <div style="display:flex;border-radius:3px;overflow:hidden;height:12px">
                {bar_segments}
              </div>
            </td>
            <td style="font-size:10px;color:{C['muted']};padding:3px 0 3px 6px;
                       white-space:nowrap">{ptotal}</td>
          </tr>"""

    return f"""
  <tr>
    <td style="background:{C['card']};padding:16px 24px 18px;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']};
               border-top:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td bgcolor="#24292f" style="background:linear-gradient(135deg,#24292f,#1b1f23);padding:10px 24px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;
                      color:rgba(255,255,255,0.7)">How I Collaborated</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">
            Intent behind every interaction &mdash; from research to shipping.</div>
        </td></tr>
      </table>
      <div style="padding:14px 24px 16px">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="vertical-align:top;width:120px;padding-right:20px">
            <div style="width:100px;height:100px;border-radius:50%;
                        background:conic-gradient({gradient});
                        margin:0 auto"></div>
          </td>
          <td style="vertical-align:top">
            <table cellpadding="0" cellspacing="0">
              {legend_rows}
            </table>
          </td>
          {f'<td style="vertical-align:top;padding-left:20px;border-left:1px solid {C["border"]};min-width:220px"><div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.7px;color:{C["muted"]};margin-bottom:6px">By project</div><table cellpadding="0" cellspacing="0" style="width:100%">{proj_rows}</table></td>' if proj_rows else ""}
        </tr>
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
                   letter-spacing:0.7px;color:{C['muted']};margin-right:10px">Cost</span>
      <span style="font-size:11px;color:{C['text']}">
        <span style="color:{C['muted']}">Claude subscription</span>
        <strong>${SEAT_COST_PER_MONTH}/mo</strong>
      </span>
      &nbsp;&nbsp;·&nbsp;&nbsp;
      <span style="font-size:11px;color:{C['text']}">
        <span style="color:{C['muted']}">Market API rate</span>
        <strong>~${market_cost:.2f}</strong>
        <span style="font-size:10px;color:{C['muted']}">({tok_str} tokens)</span>
      </span>
      {prem_html}
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

def _tier_tools(n: int) -> float:
    """Tool invocations → hour multiplier."""
    if n <= 0:   return 0.0
    if n <= 5:   return 0.25
    if n <= 15:  return 0.5
    if n <= 50:  return 0.75
    if n <= 150: return 1.5
    if n <= 400: return 3.0
    return 5.0


def _tier_tokens(n: int) -> float:
    """Token usage → hour multiplier (replaces premium_requests for Claude)."""
    if n <= 0:       return 0.0
    if n <= 5000:    return 0.25
    if n <= 20000:   return 0.5
    if n <= 50000:   return 1.0
    if n <= 150000:  return 2.0
    return 3.0


def _tier_lines(n: int) -> float:
    """Lines added → additive hour contribution."""
    if n <= 0:   return 0.0
    if n <= 25:  return 0.1
    if n <= 100: return 0.25
    if n <= 300: return 0.5
    return 1.0


def _tier_active(m: float) -> float:
    """Active engagement minutes → hours (4× multiplier — human without AI needs ~4× longer)."""
    return round(m * 4 / 60, 1)


def compute_formula_estimate(metrics: dict) -> dict:
    """Deterministic effort estimate: max(tools, tokens, active) + lines.

    Returns dict with per-signal multipliers and final estimate.
    """
    tool_h   = _tier_tools(metrics.get("tool_invocations", 0))
    tok_h    = _tier_tokens(metrics.get("tokens", 0))
    active_h = _tier_active(metrics.get("active_minutes", 0))
    lines_h  = _tier_lines(metrics.get("lines_added", 0))

    base  = max(tool_h, tok_h, active_h)
    total = max(base + lines_h, 0.25)   # Floor at 0.25h

    return {
        "tool_h":   tool_h,
        "tok_h":    tok_h,
        "active_h": active_h,
        "lines_h":  lines_h,
        "base":     base,
        "total":    round(total * 4) / 4,  # Nearest 0.25h
    }


def _evidence_strip(goal: dict, session_metrics: dict) -> str:
    """Compact metrics bar showing evidence and formula behind a goal's estimate."""
    project = goal.get("project", "")
    metrics = _resolve_metrics(project, session_metrics, goal.get("date", ""))
    if not metrics:
        return ""

    fe = compute_formula_estimate(metrics)

    parts = []
    tools = metrics.get("tool_invocations", 0)
    if tools:
        parts.append(f"<strong>{tools}</strong> tools &rarr; {_fmt_h(fe['tool_h'])}")
    tok = metrics.get("tokens", 0)
    if tok:
        parts.append(f"<strong>{tok:,}</strong> tokens &rarr; {_fmt_h(fe['tok_h'])}")
    la = metrics.get("lines_added", 0)
    if la:
        parts.append(f"<strong>+{la}</strong> lines &rarr; {_fmt_h(fe['lines_h'])}")
    active = metrics.get("active_minutes", 0)
    if active:
        parts.append(f"<strong>{active:.0f}m</strong> active &rarr; {_fmt_h(fe['active_h'])}")

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
                <span style="font-size:9px;color:{C['muted']}"> AI-calibrated</span>
                <span id="{fid}-arrow" onclick="toggleFormula('{fid}')"
                      style="cursor:pointer;font-size:9px;color:{C['accent']};
                             margin-left:10px;user-select:none">&#9654; formula</span>
              </div>
              <div id="{fid}" style="display:none;margin-top:4px;font-size:10px;color:{C['muted']}">
                <code style="font-size:9px;background:{C['bg']};padding:1px 5px;border-radius:3px;
                             color:{C['text']}">max({_fmt_h(fe['tool_h'])}, {_fmt_h(fe['tok_h'])}, {_fmt_h(fe['active_h'])}) + {_fmt_h(fe['lines_h'])}</code>
                = <strong style="color:{C['accent']}">{formula_h}</strong> deterministic
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
    tools = _signal_tier_table(
        "Tool Invocations", "&#128295;",
        "Each discrete action Claude performs: read a file, edit code, run a command, "
        "search, create a file. Higher counts indicate more complex, multi-step work.",
        [
            ("1–5",    "0.25h", "Quick task &mdash; open a file, make one edit, done. "
                                "<em>\"Fix this typo in config.yaml\"</em>"),
            ("5–15",   "0.5h",  "Small focused change &mdash; read a few files, edit a function, run tests. "
                                "<em>\"Add error handling to the upload endpoint\"</em>"),
            ("15–50",  "0.75h", "Moderate multi-file work &mdash; touch 3–4 files, debug, iterate. "
                                "<em>\"Refactor the auth module to use JWT\"</em>"),
            ("50–150", "1.5h",  "Substantial feature &mdash; design + implement across a module with tests. "
                                "<em>\"Build the report generation pipeline\"</em>"),
            ("150–400","3h",    "Major implementation &mdash; full tool or feature from scratch with iteration. "
                                "<em>\"Ship an executive deck builder from concept to working system\"</em>"),
            ("400+",   "5h",    "System overhaul &mdash; extensive multi-session redesign across many files. "
                                "<em>\"Redesign the entire report layout with branding\"</em>"),
        ]
    )
    tokens = _signal_tier_table(
        "Token Usage", "&#9889;",
        "Total tokens consumed (input + output + cache). Reflects the scale of AI reasoning "
        "and context &mdash; more tokens means more back-and-forth depth and complexity.",
        [
            ("0",           "0h",    "No tokens &mdash; session data only, no AI calls"),
            ("1–5k",        "0.25h", "Quick consultation &mdash; ask one question, get answer, done. "
                                     "<em>\"What does this error mean?\"</em>"),
            ("5k–20k",      "0.5h",  "Moderate back-and-forth &mdash; debug a problem, explore options. "
                                     "<em>\"Why is this test failing? Try a different approach\"</em>"),
            ("20k–50k",     "1h",    "Extended collaboration &mdash; iterative feature build with refinement. "
                                     "<em>\"Build this component, now adjust the styling, now add tests\"</em>"),
            ("50k–150k",    "2h",    "Deep work session &mdash; complex design + implementation + review. "
                                     "<em>\"Architect the data pipeline and implement each stage\"</em>"),
            ("150k+",       "3h",    "Marathon partnership &mdash; sustained, intensive multi-hour collaboration. "
                                     "<em>\"Full system design through to delivery with extensive context\"</em>"),
        ]
    )
    lines = _signal_tier_table(
        "Lines of Code", "&#128196;",
        "Net code added to the project. Indicates the volume of deliverable output &mdash; "
        "more lines generally means more development and review work for a human.",
        [
            ("0",      "0h",    "Research or analysis only &mdash; investigation, planning, no code written"),
            ("1–25",   "0.1h",  "Config tweak or small fix &mdash; change a setting, fix a one-liner"),
            ("25–100", "0.25h", "Small feature &mdash; a new function, helper, or template. "
                                "<em>\"Add a utility function with error handling\"</em>"),
            ("100–300","0.5h",  "Moderate development &mdash; a new module or significant feature. "
                                "<em>\"Build the session harvester with event parsing\"</em>"),
            ("300+",   "1h",    "Substantial build &mdash; major feature, new tool, or extensive refactor. "
                                "<em>\"Ship 400+ lines of report generation code\"</em>"),
        ]
    )
    active = _signal_tier_table(
        "Active Engagement Time", "&#9201;",
        "Time actively engaged with Claude, excluding idle gaps longer than 5 minutes. "
        "Multiplier is <strong>4&times; active time</strong> &mdash; reflecting that a human "
        "without AI would need roughly four times longer to achieve the same result.",
        [
            ("&lt; 5m",    "0.3h",  "Quick task &mdash; one-shot edit, single question"),
            ("5–15m",      "1h",    "Focused task &mdash; fix a bug, write a function"),
            ("15–45m",     "2–3h",  "Working session &mdash; implement and test a feature"),
            ("45m–2h",     "3–8h",  "Deep work &mdash; multi-step design, implementation, and refinement"),
            ("2–6h",       "8–24h", "Extended session &mdash; full feature build across multiple iterations"),
            ("6h+",        "24h+",  "Marathon project &mdash; comprehensive system build over many hours"),
        ]
    )
    return f"""
        <div style="margin-top:16px;padding-top:12px;border-top:1px solid {C['border']}">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;
                      color:{C['muted']};margin-bottom:4px">What each signal means</div>
          <div style="font-size:10px;color:{C['muted']};line-height:1.5;margin-bottom:4px">
            Each session signal maps to a multiplier representing equivalent human effort. The AI
            reads all signals together and assigns an estimate within the highest applicable range.
            <br><strong style="color:{C['text']}">Reading the table:</strong> find your value in the
            Range column &rarr; the Multiplier shows the hour contribution from that signal alone.
          </div>
          {tools}
          {tokens}
          {lines}
          {active}
        </div>"""


def _estimation_waterfall_inner(goals: list, analysis: dict) -> str:
    """Evidence table showing raw signals, per-signal multipliers, and formula result."""
    session_metrics = analysis.get("session_metrics", {})
    if not goals:
        return ""

    total_h = sum(g.get("human_hours", 0) for g in goals)
    total_formula_h = 0.0

    rows = ""
    for i, g in enumerate(goals):
        bg = C["subtle"] if i % 2 == 0 else C["card"]
        project = g.get("project", "")
        metrics = _resolve_metrics(project, session_metrics, g.get("date", ""))
        fe = compute_formula_estimate(metrics)
        total_formula_h += fe["total"]

        tools      = metrics.get("tool_invocations", 0)
        tok        = metrics.get("tokens", 0)
        la         = metrics.get("lines_added", 0)
        active     = metrics.get("active_minutes", 0)
        active_str = f"{active:.0f}m" if active else "&mdash;"
        tok_str    = f"{tok:,}" if tok else "&mdash;"
        ai_h       = _fmt_h(g.get("human_hours", 0))
        formula_h  = _fmt_h(fe["total"])

        title = g.get("title", "")
        if len(title) > 40:
            title = title[:37] + "..."

        # Bold whichever signal is the base driver (the max)
        max_val = fe["base"]
        def _hl(v: float) -> str:
            s = _fmt_h(v) if v > 0 else "&mdash;"
            if v > 0 and v == max_val:
                return f'<strong style="color:{C["accent"]}">{s}</strong>'
            return f'<span style="color:{C["muted"]}">{s}</span>'

        lines_m = _fmt_h(fe["lines_h"]) if fe["lines_h"] > 0 else "&mdash;"

        rows += f"""
        <tr style="background:{bg}">
          <td style="padding:6px 10px;border-bottom:1px solid {C['border']};vertical-align:top;width:22%"
              rowspan="2">
            <div style="font-size:11px;font-weight:600;color:{C['text']};line-height:1.3">{title}</div>
          </td>
          <td style="padding:4px 6px;font-size:11px;color:{C['text']};text-align:center;
                     font-weight:600;width:13%">{tools}</td>
          <td style="padding:4px 6px;font-size:11px;color:{C['text']};text-align:center;
                     font-weight:600;width:13%">{tok_str}</td>
          <td style="padding:4px 6px;font-size:11px;color:{C['text']};text-align:center;
                     font-weight:600;width:13%">{active_str}</td>
          <td style="padding:4px 6px;font-size:11px;color:{C['text']};text-align:center;
                     font-weight:600;width:13%">+{la}</td>
          <td class="formula-col" style="padding:4px 6px;text-align:center;width:13%;
                     vertical-align:middle;display:none" rowspan="2">
            <div style="font-size:14px;font-weight:700;color:{C['accent']}">{formula_h}</div>
            <div style="font-size:8px;color:{C['muted']};text-transform:uppercase;margin-top:1px">formula</div>
          </td>
          <td style="padding:4px 6px;text-align:center;width:13%;vertical-align:middle" rowspan="2">
            <div style="font-size:14px;font-weight:700;color:{C['green']}">{ai_h}</div>
            <div style="font-size:8px;color:{C['muted']};text-transform:uppercase;margin-top:1px">AI est.</div>
          </td>
        </tr>
        <tr style="background:{bg}">
          <td style="padding:2px 6px 6px;text-align:center;border-bottom:1px solid {C['border']}">
            {_hl(fe["tool_h"])}</td>
          <td style="padding:2px 6px 6px;text-align:center;border-bottom:1px solid {C['border']}">
            {_hl(fe["tok_h"])}</td>
          <td style="padding:2px 6px 6px;text-align:center;border-bottom:1px solid {C['border']}">
            {_hl(fe["active_h"])}</td>
          <td style="padding:2px 6px 6px;text-align:center;border-bottom:1px solid {C['border']}">
            <span style="color:{C['muted']}">{lines_m}</span></td>
        </tr>"""

    # Total row
    rows += f"""
        <tr style="background:{C['accent_lt']}">
          <td style="padding:8px 10px;border-top:2px solid {C['border']};
                     font-size:11px;font-weight:700;color:{C['accent']};text-align:right"
              colspan="5">Total</td>
          <td class="formula-col" style="padding:8px 6px;border-top:2px solid {C['border']};
                     text-align:center;display:none">
            <div style="font-size:16px;font-weight:700;color:{C['accent']}">{_fmt_h(total_formula_h)}</div>
          </td>
          <td style="padding:8px 6px;border-top:2px solid {C['border']};text-align:center">
            <div style="font-size:16px;font-weight:700;color:{C['green']}">{_fmt_h(total_h)}</div>
          </td>
        </tr>"""

    return f"""
  <tr>
    <td style="background:{C['card']};padding:0;
               border-left:1px solid {C['border']};border-right:1px solid {C['border']}">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td bgcolor="#24292f" style="background:linear-gradient(135deg,#24292f,#1b1f23);padding:10px 24px">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;
                      color:rgba(255,255,255,0.7)">Estimation Evidence</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">
            How human effort estimates were calculated &mdash; signal by signal.</div>
        </td></tr>
      </table>
      <div style="padding:14px 24px 18px">
        <div style="font-size:11px;color:{C['muted']};margin-bottom:10px;line-height:1.6">
          <strong style="color:{C['text']}">How to read this table:</strong>
          Each row shows a project's raw session data (top) and the hour multiplier each signal
          maps to (bottom). The <strong style="color:{C['accent']}">highest multiplier</strong>
          among tools, tokens, and active time becomes the base estimate.
          Lines of code are added on top.
        </div>
        <div style="font-size:10px;color:{C['muted']};margin-bottom:10px;padding:8px 12px;
                    background:{C['subtle']};border-radius:6px;border:1px solid {C['border']}">
          <span style="color:{C['green']}">&#9632;</span> AI-calibrated estimate &nbsp;·&nbsp;
          <strong style="color:{C['accent']}">Bold</strong> = highest signal (base driver)
          &nbsp;&nbsp;
          <span id="formula-col-toggle" data-open="0" onclick="toggleFormulaCol()"
                style="cursor:pointer;font-size:9px;color:{C['accent']};user-select:none">
            &#9654; Show formula column
          </span>
        </div>
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border:1px solid {C['border']};border-radius:7px;overflow:hidden">
          <tr style="background:{C['accent_lt']}">
            <th style="padding:6px 10px;text-align:left;font-size:9px;font-weight:700;
                       color:{C['accent']};text-transform:uppercase;letter-spacing:0.5px;
                       border-bottom:1px solid {C['border']};width:22%">Project</th>
            <th style="padding:6px 6px;text-align:center;font-size:9px;font-weight:700;
                       color:{C['accent']};text-transform:uppercase;letter-spacing:0.5px;
                       border-bottom:1px solid {C['border']};width:13%">Tools</th>
            <th style="padding:6px 6px;text-align:center;font-size:9px;font-weight:700;
                       color:{C['accent']};text-transform:uppercase;letter-spacing:0.5px;
                       border-bottom:1px solid {C['border']};width:13%">Tokens</th>
            <th style="padding:6px 6px;text-align:center;font-size:9px;font-weight:700;
                       color:{C['accent']};text-transform:uppercase;letter-spacing:0.5px;
                       border-bottom:1px solid {C['border']};width:13%">Active</th>
            <th style="padding:6px 6px;text-align:center;font-size:9px;font-weight:700;
                       color:{C['accent']};text-transform:uppercase;letter-spacing:0.5px;
                       border-bottom:1px solid {C['border']};width:13%">Lines</th>
            <th class="formula-col" style="padding:6px 6px;text-align:center;font-size:9px;font-weight:700;
                       color:{C['accent']};text-transform:uppercase;letter-spacing:0.5px;
                       border-bottom:1px solid {C['border']};width:13%;display:none">Formula</th>
            <th style="padding:6px 6px;text-align:center;font-size:9px;font-weight:700;
                       color:{C['green']};text-transform:uppercase;letter-spacing:0.5px;
                       border-bottom:1px solid {C['border']};width:13%">AI Est.</th>
          </tr>
          {rows}
        </table>
        {_signal_guide()}
      </div>
    </td>
  </tr>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main generate_html
# ─────────────────────────────────────────────────────────────────────────────

def generate_html(target_date: str, analysis: dict, sessions: list) -> str:
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
<table width="700" cellpadding="0" cellspacing="0" style="max-width:700px;width:100%">

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

  {_kpi_section(goals, analysis, n_sessions)}

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

  {_collaboration_intent(sessions, goals)}

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
              {date_badge}{g.get('title','')}
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
                    {g.get('title','')}
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
