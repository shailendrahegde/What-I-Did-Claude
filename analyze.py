"""
analyze.py — Semantic analysis of the day's Claude sessions.
Goals = business outcomes (one per session/coherent block of work).
Tasks = implementation steps within a goal.
"""
from __future__ import annotations
import json
import re
import urllib.request
import urllib.error
from pathlib import Path

from harvest import compute_elapsed_minutes

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-haiku-4-5"

DOMAIN_SKILLS = (
    "System Architecture", "Product Planning", "Requirements Analysis",
    "Technical Research", "Data Analysis", "Statistical Modelling",
    "UX Design", "Product Management", "Project Management",
    "Technical Writing", "Documentation", "Stakeholder Communication",
    "Prompt Engineering", "Security Review", "Code Review",
)
TECH_SKILLS = (
    "Python", "JavaScript", "TypeScript", "Bash/Shell",
    "HTML/CSS", "SQL", "API Integration", "DevOps/CI-CD",
    "Cloud Infrastructure", "Database Design", "Machine Learning",
    "Data Engineering", "Debugging", "Refactoring", "Frontend Development",
)

TASK_TYPES = (
    "Development",
    "Bug Fix & Debug",
    "Analysis & Research",
    "Design & UX",
    "Execution & Ops",
)

PROFESSIONAL_ROLES = (
    "Software Engineer", "Frontend Developer", "Data Analyst", "Data Engineer",
    "DevOps Engineer", "Solutions Architect", "Security Engineer", "QA Engineer",
    "UX Designer", "Visual Designer", "Technical Writer", "Product Manager",
    "Program Manager", "Business Analyst", "Management Consultant",
    "Research Scientist", "Financial Analyst", "Risk & Compliance Analyst",
    "Domain Expert",
)


# ── API helpers ───────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    import os
    # 1. Explicit env var override — works for everyone including OAuth users
    if key := os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return key
    # 2. Claude Code API-key auth — stored in ~/.claude/config.json
    try:
        config = json.loads((Path.home() / ".claude" / "config.json").read_text(encoding="utf-8"))
        if key := config.get("primaryApiKey", "").strip():
            return key
    except Exception:
        pass
    return ""


def _claude_cli_available() -> bool:
    """Return True if the `claude` CLI is on PATH and responds to --version."""
    import subprocess
    try:
        subprocess.run(
            ["claude", "--version"],
            capture_output=True, timeout=10, check=True,
        )
        return True
    except Exception:
        return False


def _claude_cli_analyze(prompt: str) -> str:
    """
    Run `claude -p <prompt>` and return the raw text output.
    Raises subprocess.SubprocessError / TimeoutExpired on failure.
    """
    import subprocess
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise subprocess.SubprocessError(
            f"claude -p exited {result.returncode}: {result.stderr[:200]}"
        )
    return result.stdout.strip()


def _explain_missing_key() -> None:
    """Print a clear, actionable message when no API key can be found."""
    claude_dir = Path.home() / ".claude"
    has_config  = (claude_dir / "config.json").exists()
    # Detect OAuth-only setup: config exists but primaryApiKey is absent/empty
    oauth_mode = False
    if has_config:
        try:
            cfg = json.loads((claude_dir / "config.json").read_text(encoding="utf-8"))
            oauth_mode = not cfg.get("primaryApiKey", "").strip()
        except Exception:
            pass

    if oauth_mode:
        print(
            "  NOTE: You signed in to Claude Code via Claude.ai (OAuth) and the `claude` CLI\n"
            "  was not found on PATH. This tool needs one of:\n"
            "    1. The `claude` CLI installed (npm install -g @anthropic-ai/claude-code)\n"
            "    2. An API key: export ANTHROPIC_API_KEY=sk-ant-...\n"
            "       (get one at https://console.anthropic.com → API Keys)\n"
            "  Falling back to heuristic analysis for now."
        )
    elif not has_config:
        print(
            "  NOTE: ~/.claude/config.json not found and `claude` CLI not on PATH.\n"
            "  To enable AI analysis, either:\n"
            "    1. Install Claude Code: npm install -g @anthropic-ai/claude-code\n"
            "    2. Set an API key: export ANTHROPIC_API_KEY=sk-ant-...\n"
            "  Falling back to heuristic analysis for now."
        )
    else:
        print("  (No API key found — using heuristic analysis.)")


def check_api_health() -> tuple:
    """
    Check if the Anthropic API is reachable and the key is valid.
    Returns a tuple of (status, message) where status is one of:
      "ok"   — API reachable and key accepted (or claude CLI available as fallback)
      "auth" — no API key and no claude CLI found
      "down" — API unreachable or unexpected error
    """
    api_key = _get_api_key()
    if not api_key:
        if _claude_cli_available():
            return ("ok", "No API key — will use `claude -p` via your Claude Code session.")
        return ("auth", "No API key found. Set ANTHROPIC_API_KEY or add primaryApiKey to ~/.claude/config.json")

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "ping"}],
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL, data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return ("ok", "Anthropic API reachable and key accepted")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            body = e.read().decode()[:200]
            return ("auth", f"API key rejected (HTTP {e.code}): {body}")
        body = e.read().decode()[:200]
        return ("down", f"API returned HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        return ("down", f"Cannot reach Anthropic API: {e.reason}")
    except Exception as e:
        return ("down", f"Unexpected error: {e}")


# ── Transcript builder ────────────────────────────────────────────────────────

def _build_transcript(sessions: list) -> str:
    lines = []
    for s in sessions:
        lines.append(f"\n=== PROJECT: {s['project']} | SESSION: {s['session_id'][:8]} ===")
        if s.get("session_start") and s.get("session_end"):
            lines.append(f"Time: {s['session_start'][11:19]} → {s['session_end'][11:19]} UTC")
        for msg in s["messages"]:
            if msg["role"] != "user":
                continue
            lines.append(f"\n[INSTRUCTION] {msg['text']}")
            for t in msg.get("tools_after", []):
                lines.append(f"  • {t}")
    return "\n".join(lines)


# ── Cache ─────────────────────────────────────────────────────────────────────

_CACHE_DIR = Path(__file__).parent / "cache"


def _cache_path(target_date: str) -> Path:
    return _CACHE_DIR / f"{target_date}.json"


# ── Session metrics ───────────────────────────────────────────────────────────

def _compute_active_minutes(session: dict) -> float:
    """
    Estimate active minutes in a session by summing gaps between consecutive
    user messages, capping each gap at 10 minutes (longer gaps = idle time).
    Falls back to elapsed minutes if only one timestamp is available.
    """
    messages = [m for m in session.get("messages", []) if m.get("timestamp")]
    if len(messages) < 2:
        return compute_elapsed_minutes(
            session.get("session_start", ""),
            session.get("session_end", ""),
        )
    from datetime import datetime
    fmt = "%Y-%m-%dT%H:%M:%S"
    active = 0.0
    for i in range(1, len(messages)):
        try:
            t0 = datetime.strptime(messages[i - 1]["timestamp"][:19], fmt)
            t1 = datetime.strptime(messages[i]["timestamp"][:19], fmt)
            gap = max(0, (t1 - t0).total_seconds() / 60)
            active += min(gap, 10.0)   # cap idle gaps at 10 min
        except Exception:
            pass
    return active


def _build_session_metrics(sessions: list) -> dict:
    """
    Build a dict keyed by project name (and also by basename) with per-project
    aggregated metrics across all sessions for that project.
    """
    aggregated: dict = {}

    for s in sessions:
        proj = s["project"]
        basename = proj.split("/")[-1].split("\\")[-1]

        tok = s.get("tokens", {})
        tools_count = sum(len(m.get("tools_after", [])) for m in s.get("messages", []))
        lines_added = s.get("lines_added", 0)
        active_min  = _compute_active_minutes(s)
        wall_min    = compute_elapsed_minutes(
            s.get("session_start", ""),
            s.get("session_end", ""),
        )

        entry = {
            "tokens":           tok.get("input", 0) + tok.get("output", 0),
            "tool_invocations": tools_count,
            "lines_added":      lines_added,
            "active_minutes":   active_min,
            "wall_clock_minutes": wall_min,
            "sessions":         1,
        }

        for key in (proj, basename):
            if key not in aggregated:
                aggregated[key] = dict(entry)
            else:
                aggregated[key]["tokens"]             += entry["tokens"]
                aggregated[key]["tool_invocations"]   += entry["tool_invocations"]
                aggregated[key]["lines_added"]        += entry["lines_added"]
                aggregated[key]["active_minutes"]     += entry["active_minutes"]
                aggregated[key]["wall_clock_minutes"] += entry["wall_clock_minutes"]
                aggregated[key]["sessions"]           += 1

    return aggregated


# ── Main analysis entry point ─────────────────────────────────────────────────

def analyze_day(
    target_date: str,
    sessions: list,
    refresh: bool = False,
    use_api: bool = True,
) -> dict:
    total_tokens = {
        "input":          sum(s["tokens"]["input"]          for s in sessions),
        "output":         sum(s["tokens"]["output"]         for s in sessions),
        "cache_read":     sum(s["tokens"]["cache_read"]     for s in sessions),
        "cache_creation": sum(s["tokens"]["cache_creation"] for s in sessions),
    }
    total_tokens["total"] = sum(total_tokens.values())

    # Return cached result if available (tokens always refreshed from live data)
    cache_file = _cache_path(target_date)
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            # Locked entries are never overwritten, even with --refresh
            if cached.get("locked"):
                print("  (Analysis is locked — skipping refresh. Remove 'locked' field to re-analyse.)")
                cached["tokens"] = total_tokens
                _attach_metrics(cached, sessions)
                return cached
            if not refresh:
                cached["tokens"] = total_tokens  # always use live token counts
                _attach_metrics(cached, sessions)  # always attach live session metrics
                print("  (Using cached analysis — pass --refresh to re-analyse.)")
                return cached
        except Exception:
            pass

    # If caller explicitly disabled API, jump straight to heuristic
    if not use_api:
        result = _fallback_analysis(target_date, sessions)
        result["tokens"] = total_tokens
        _attach_metrics(result, sessions)
        return result

    api_key = _get_api_key()
    if not api_key:
        if _claude_cli_available():
            print("  (No API key — using `claude -p` via your Claude Code session.)")
        else:
            _explain_missing_key()
            result = _fallback_analysis(target_date, sessions)
            result["tokens"] = total_tokens
            _attach_metrics(result, sessions)
            return result

    # Build session metrics before calling the API so we can include them in
    # calibration signals for the prompt
    session_metrics = _build_session_metrics(sessions)
    total_tool_calls = sum(
        len(m.get("tools_after", []))
        for s in sessions
        for m in s.get("messages", [])
    )

    transcript = _build_transcript(sessions)
    domain_list = "\n".join(f"  - {s}" for s in DOMAIN_SKILLS)
    tech_list   = "\n".join(f"  - {s}" for s in TECH_SKILLS)
    task_type_list = " | ".join(TASK_TYPES)
    role_list      = ", ".join(PROFESSIONAL_ROLES)

    prompt = f"""Analyze this day of Claude-assisted work and produce a JSON digest.

SESSION TRANSCRIPT:
{transcript}

═══════════════════════════════════════════
RULE 0 — PERSONAL / OFF-TOPIC FILTER
═══════════════════════════════════════════

Skip any session or instruction that is purely personal, off-topic, or unrelated
to professional work. Examples to skip: health queries, fitness plans, food/recipes,
personal scheduling, casual conversation, entertainment requests.
If an entire session is personal, do NOT include it in the goals list at all.

═══════════════════════════════════════════
RULE 1 — GOAL GROUPING (most important rule)
═══════════════════════════════════════════

Group work into BUSINESS GOALS. A goal = the high-level outcome accomplished, not the technical steps.

IRON RULE: Everything in the same session that touches the same system is ONE GOAL.
Iterating, refining, tweaking layout, fixing bugs, adjusting prompts, adding features, debugging encoding
— these are ALL tasks within the original goal, not separate goals.

DEFAULT RULE: When in doubt, MERGE. Too few goals is better than too many.

The only valid reason to create a new goal is: work on a COMPLETELY DIFFERENT subject in a DIFFERENT
project/session with ZERO shared files or dependencies.

SPECIFICALLY — these are TASKS, never separate goals:
  • Fixing a bug or encoding error in something just built
  • Refining the layout, format, or visual hierarchy of a report you built
  • Adjusting the analysis prompt or goal-grouping rules for a tool you built
  • Adding a new feature (KPI cards, skill pills, doc refs) to a tool you built
  • Setting up API keys or config for a tool you built
  • Debugging compatibility issues in a tool you built

WORKED EXAMPLE — today's sessions should produce exactly 2 goals:
  SESSION "whatidid":
    built analytics tool → fixed API auth → refined report layout → added KPI cards → fixed bugs
    → ONE GOAL: all of it is the same system, built in the same session.
    "Refined report semantics" is NOT a separate goal — it's a task inside building the tool.
  SESSION "Adhoc":
    reviewed a presentation unrelated to the analytics tool
    → SEPARATE GOAL: different subject, different deliverable, zero shared files

GOOD GOAL TITLES (business outcome, verb-first, based on the MOST SUBSTANTIAL work done):
  "Shipped a daily work digest tool from concept to working system"
  "Provided strategic rewrite recommendations for the presentation"
  "Diagnosed and resolved checkout regression in production"

BAD GOAL TITLES (too granular, based on first message instead of overall outcome):
  "Set up API authentication"        ← part of a larger goal
  "Built HTML report generator"      ← a task within a goal
  "Refined report formatting"        ← a task within a goal
  "Initialized git repository"       ← setup step, not the goal itself
  "Prepared directory for checkin"   ← describes first action, not the outcome

TITLE RULE: The goal title must describe the PRIMARY DELIVERABLE, not the first thing done.
If a session starts with "prepare for github" but spends 80% of time building a report tool,
the title should be about the report tool, not the git setup.

═══════════════════════════════════════════
RULE 2 — LANGUAGE
═══════════════════════════════════════════

Write as if briefing a senior executive on what was accomplished.

NEVER write anything that implies the human was unclear, imprecise, or needed to course-correct. The human always had clear intent. Claude was the one adapting and implementing.

FORBIDDEN phrases and patterns:
  ✗ "vague need" / "vague request" / "unclear requirements"
  ✗ "initially" / "eventually" / "after some iteration" / "after refining"
  ✗ "settled on" / "ended up with" / "finally decided"
  ✗ "the user clarified" / "after feedback" / "upon reflection"
  ✗ Any phrase that implies the direction changed because the human wasn't sure

NEVER ASSUME CONTEXT NOT IN THE TRANSCRIPT:
  ✗ Do NOT infer purpose, audience, or intent beyond what is stated.
  ✗ "investor presentation", "sales deck", "board deck" are all assumptions — forbidden unless the transcript says so.
  ✓ DO use the actual file or document name when it appears in the tool calls (e.g. if a file called
    "Q2_Roadmap.pptx" or "AuthDesign.md" is visible, use that name — it's a fact, not an assumption).
  ✓ If no title is visible, use the generic type: "the presentation", "the document", "the report".

GOOD framing:
  ✓ "Designed and shipped X" — confident, direct
  ✓ "Built X with Y capability" — outcome-focused
  ✓ "Delivered X that does Y" — value-focused
  ✓ "Refined X to include Y" — extending intentionally, not correcting a mistake

═══════════════════════════════════════════
RULE 3 — EFFORT ESTIMATES (calibrated)
═══════════════════════════════════════════

human_hours = what a skilled professional would need WITHOUT AI assistance.
Estimate realistically — what would an expert actually bill for this work?
Use this calibration scale — match the task to the closest anchor:

  0.25h    — Trivial: install a package, run a CLI command, toggle a config, copy files, push to git
  0.5h     — Simple: minor code edit, format/style tweak, rename, small config change, answer a question
  0.75h    — Light: write a helper function, fix a known bug, small template change
  1.0-1.5h — Moderate: implement a small feature, debug an unknown issue, draft a short document
  2-3h     — Substantial: design + implement a feature, write a detailed report, complex data analysis
  4-8h     — Major: architect a new module, build a complete tool, comprehensive multi-step research
  8-16h    — Large: build a full system from scratch, multi-day design-implement-test cycle, extensive refactor

Trivial/mechanical tasks (installing, deploying, git operations, answering questions) → 0.25-0.5h max.
Complex tasks involving DESIGN, ANALYSIS, NOVEL CODING, or MULTI-STEP IMPLEMENTATION should scale up
based on the quantitative signals below. An expert human writing 500 lines of production code needs
4+ hours; researching and iterating through 100+ tool invocations is a full workday.

USE THESE QUANTITATIVE SIGNALS to calibrate estimates:
- Tool invocations: 1-10 = simple, 10-30 = moderate, 30-75 = substantial, 75-150 = major, 150+ = large
- Code impact (lines added): <50 = minor, 50-150 = moderate, 150-300 = substantial, 300+ = major development
- Expert human writes 100-150 lines of code per hour (including boilerplate, comments, config)
- Total tool invocations today: {total_tool_calls}
- Total tokens today: {total_tokens['total']}

IMPORTANT RULES:
- Mechanical execution (installing, deploying, running existing code, copying files) → 0.25-0.5h max
- If total tool invocations < 10, ALL tasks combined should be ≤ 1h total
- Each number must be nearest 0.25h (not just 0.5h increments)
- goal.human_hours must exactly equal the sum of its task hours

═══════════════════════════════════════════
OUTPUT SCHEMA
═══════════════════════════════════════════

Return ONLY this JSON (no markdown fences, no explanation before or after):

{{
  "headline": "One punchy sentence — the most significant thing accomplished today",
  "primary_focus": "2-4 words (e.g. 'Productivity tooling', 'Deck strategy')",
  "day_narrative": "Exactly 2 sentences. What was accomplished and why it matters. Confident tone, plain English.",
  "analysis_method": "ai",
  "goals": [
    {{
      "title": "Business outcome title (verb-first)",
      "label": "2-5 word noun phrase naming the deliverable (e.g. 'Daily work digest tool', 'Viva customer analysis'). Used as the bold heading in the summary list.",
      "summary": "1 sentence, max 20 words. What exists now that didn't before. Confident tone.",
      "human_hours": <sum of task hours>,
      "project": "exact project name from the SESSION header (e.g. 'whatidid', 'Adhoc')",
      "docs_referenced": ["filenames of documents ACTUALLY ANALYZED OR PRODUCED in this goal — only include if work was clearly done ON that file. Exclude files merely found during a directory scan. Exclude config/lock/internal tool files. Use just the filename. Empty list if none."],
      "tasks": [
        {{
          "title": "Implementation step (verb-first)",
          "what_got_done": "One sentence, max 18 words. Outcome only — no tool names, no file names.",
          "task_type": "One of: {task_type_list}",
          "domain_skills": ["1-2 from: {', '.join(DOMAIN_SKILLS)}"],
          "tech_skills": ["0-2 from: {', '.join(TECH_SKILLS)} (omit if none)"],
          "professional_roles": ["1-2 from: {role_list}"],
          "human_hours": <single conservative number, nearest 0.25h>
        }}
      ]
    }}
  ]
}}"""

    try:
        if api_key:
            payload = json.dumps({
                "model": MODEL,
                "max_tokens": 4000,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8")
            req = urllib.request.Request(
                API_URL, data=payload,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                response = json.loads(resp.read().decode("utf-8"))
            raw = response["content"][0]["text"].strip()
        else:
            # OAuth users: delegate to the claude CLI using their session auth
            raw = _claude_cli_analyze(prompt)

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        analysis = json.loads(raw)
        analysis["analysis_method"] = "ai"
        analysis["tokens"]          = total_tokens
        analysis["sessions_count"]  = len(sessions)
        analysis["projects"]        = list({s["project"] for s in sessions})
        _attach_metrics(analysis, sessions, session_metrics=session_metrics)
        # Cache for future runs
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        except Exception:
            pass
        return analysis

    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  API error {e.code}: {body}")
        print("  Falling back to heuristic analysis.")
    except Exception as e:
        print(f"  Analysis failed ({e}). Falling back to heuristic analysis.")

    result = _fallback_analysis(target_date, sessions)
    result["tokens"] = total_tokens
    _attach_metrics(result, sessions)
    return result


# ── Metrics attachment ────────────────────────────────────────────────────────

def _attach_metrics(result: dict, sessions: list, session_metrics: dict | None = None) -> None:
    """
    Attach aggregated session metrics to the analysis result in-place.
    If session_metrics is not provided it will be computed from sessions.
    """
    if session_metrics is None:
        session_metrics = _build_session_metrics(sessions)
    result["session_metrics"]  = session_metrics
    result["sessions_count"]   = len(sessions)
    result["projects"]         = list({s["project"] for s in sessions})
    result["lines_added"]      = sum(s.get("lines_added", 0) for s in sessions)
    result["lines_removed"]    = sum(s.get("lines_removed", 0) for s in sessions)
    # Ensure tokens total is present
    tok = result.get("tokens", {})
    if tok and "total" not in tok:
        tok["total"] = sum(tok.values())


# ── Heuristic fallback ────────────────────────────────────────────────────────

def _word(w: str, s: str) -> bool:
    return bool(re.search(r'\b' + re.escape(w) + r'\b', s))


def _infer_skills(text: str, tools: list) -> tuple:
    """
    Infer domain skills, tech skills, task_type, and professional_roles
    from a user message and its associated tool calls.

    Returns: (domain_skills, tech_skills, task_type, professional_roles)
    """
    t, ts = text.lower(), " ".join(tools).lower()
    domain, tech, roles = [], [], []

    # ── Domain skills ──────────────────────────────────────────────────────
    if any(_word(w, t) for w in ("plan", "design", "architect", "structure")):
        domain.append("System Architecture")
    if any(_word(w, t) for w in ("research", "find", "look up", "understand")):
        domain.append("Technical Research")
    if any(_word(w, t) for w in ("analyze", "report", "metric", "data", "dashboard")):
        domain.append("Data Analysis")
    if any(_word(w, t) for w in ("write", "draft", "document")):
        domain.append("Technical Writing")
    if any(_word(w, t) for w in ("review", "audit", "assess")):
        domain.append("Code Review")
    if not domain:
        domain.append("Product Planning")

    # ── Tech skills ────────────────────────────────────────────────────────
    if any(_word(w, t) for w in ("debug", "fix", "error", "bug", "traceback")):
        tech.append("Debugging")
    if ".py" in ts or "python" in ts or ".py" in t:
        tech.append("Python")
    if ".js" in ts or ".ts" in ts or "javascript" in t or "typescript" in t:
        tech.append("JavaScript")
    if ".html" in ts or "html" in ts or ".css" in ts:
        tech.append("HTML/CSS")
    if ".sql" in ts or "sql" in t or "query" in t:
        tech.append("SQL")
    if any(_word(w, t) for w in ("deploy", "commit", "push", "pipeline", "ci", "cd")):
        tech.append("DevOps/CI-CD")
    if any(_word(w, t) for w in ("api", "endpoint", "request", "response", "http")):
        tech.append("API Integration")
    if not tech and any(_word(w, t) for w in ("refactor", "restructure", "clean")):
        tech.append("Refactoring")

    # ── Task type ──────────────────────────────────────────────────────────
    if any(_word(w, t) for w in ("debug", "fix", "error", "bug", "traceback", "broken", "crash")):
        task_type = "Bug Fix & Debug"
    elif any(_word(w, t) for w in ("analyze", "research", "investigate", "explore", "find", "look up")):
        task_type = "Analysis & Research"
    elif any(_word(w, t) for w in ("design", "mockup", "wireframe", "layout", "ui", "ux", "style")):
        task_type = "Design & UX"
    elif any(_word(w, t) for w in ("deploy", "run", "execute", "install", "setup", "configure", "push")):
        task_type = "Execution & Ops"
    else:
        task_type = "Development"

    # ── Professional roles (heuristic) ────────────────────────────────────
    if any(_word(w, t) for w in ("build", "implement", "code", "write", "develop", "create", "refactor")):
        roles.append("Software Engineer")
    if any(_word(w, t) for w in ("html", "css", "frontend", "ui", "ux", "layout", "style", "design")):
        roles.append("Frontend Developer")
    if any(_word(w, t) for w in ("data", "analyze", "metric", "dashboard", "report", "insight")):
        if "Data Analyst" not in roles:
            roles.append("Data Analyst")
    if any(_word(w, t) for w in ("pipeline", "etl", "ingest", "schema", "warehouse")):
        roles.append("Data Engineer")
    if any(_word(w, t) for w in ("deploy", "ci", "cd", "docker", "kubernetes", "infra", "terraform")):
        roles.append("DevOps Engineer")
    if any(_word(w, t) for w in ("architect", "design", "system", "scalab", "integrat")):
        roles.append("Solutions Architect")
    if any(_word(w, t) for w in ("security", "auth", "permission", "vulnerab", "encrypt")):
        roles.append("Security Engineer")
    if any(_word(w, t) for w in ("test", "qa", "quality", "assert", "coverage")):
        roles.append("QA Engineer")
    if any(_word(w, t) for w in ("write", "document", "readme", "guide", "spec")):
        roles.append("Technical Writer")
    if any(_word(w, t) for w in ("product", "roadmap", "priorit", "feature request", "backlog")):
        roles.append("Product Manager")
    if any(_word(w, t) for w in ("plan", "schedule", "stakeholder", "milestone", "risk")):
        roles.append("Program Manager")
    if any(_word(w, t) for w in ("analys", "business", "process", "workflow", "requirement")):
        roles.append("Business Analyst")
    if any(_word(w, t) for w in ("research", "literature", "experiment", "hypothesis")):
        roles.append("Research Scientist")
    if not roles:
        roles.append("Software Engineer")

    return domain[:2], tech[:2], task_type, roles[:2]


def _conservative_hours(text: str, tools: list) -> float:
    n, t = len(tools), text.lower()
    # Quick/trivial operations first
    if any(_word(w, t) for w in ("install", "deploy", "push", "config", "setup")):
        return 0.25
    if any(_word(w, t) for w in ("update", "change", "small", "quick", "rename", "tweak")):
        return 0.5
    # Tool-count-based calibration
    if n <= 1:
        return 0.25
    if n <= 3:
        return 0.5
    # Bug fix
    if any(_word(w, t) for w in ("fix", "debug", "error", "bug")):
        return 1.5 if n > 10 else 1.0
    # Substantial build
    if any(_word(w, t) for w in ("implement", "build", "create", "write", "code")):
        return 4.0 if n > 15 else 2.0
    # Planning / design
    if any(_word(w, t) for w in ("plan", "design", "architect")):
        return 1.5
    # Analysis / research
    if any(_word(w, t) for w in ("analyze", "research")):
        return 1.5
    return 1.0


def _fallback_analysis(target_date: str, sessions: list) -> dict:
    goals = []
    for s in sessions:
        user_msgs = [m for m in s["messages"] if m["role"] == "user"]
        if not user_msgs:
            continue
        proj  = s["project"].replace("/", " › ").replace("\\", " › ").title()
        tasks = []
        for msg in user_msgs:
            text, tools = msg["text"], msg.get("tools_after", [])
            hours = _conservative_hours(text, tools)
            domain, tech, task_type, roles = _infer_skills(text, tools)
            first = text.split("\n")[0].strip()
            title = (first if len(first) > 5 else text[:75])[:75]
            tasks.append({
                "title":             title,
                "what_got_done":     "Heuristic summary — enable API for plain-English descriptions.",
                "task_type":         task_type,
                "domain_skills":     domain,
                "tech_skills":       tech,
                "professional_roles": roles,
                "human_hours":       hours,
            })
        goals.append({
            "title":       f"Worked on {proj}",
            "label":       proj,
            "summary":     "Heuristic analysis — enable API access for full semantic breakdown.",
            "human_hours": sum(t["human_hours"] for t in tasks),
            "project":     s["project"],
            "tasks":       tasks,
        })

    projects = list({s["project"] for s in sessions})
    return {
        "headline":        f"Activity on {target_date}",
        "primary_focus":   sessions[0]["project"].split("/")[-1].split("\\")[-1].title() if sessions else "Mixed",
        "day_narrative":   "Heuristic analysis of the day's activity. Enable API access for a full semantic digest.",
        "analysis_method": "heuristic",
        "goals":           goals,
        "tokens":          {},
        "sessions_count":  len(sessions),
        "projects":        projects,
    }
