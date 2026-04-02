"""
harvest.py — Read Claude Code session JSONL files and extract structured activity data.
"""
from __future__ import annotations
import ast
import json
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# Short affirmative/approval patterns to ignore
_APPROVALS = {
    "yes", "y", "yep", "yeah", "yup", "no", "n", "nope",
    "ok", "okay", "sure", "fine", "right", "correct",
    "proceed", "go ahead", "go for it", "do it", "do that",
    "looks good", "sounds good", "that's fine", "that works",
    "approved", "continue", "perfect", "great", "good",
    "got it", "understood", "makes sense",
}

import re as _re

_INTENT_CATEGORIES = {
    "Building":      _re.compile(r"\b(create|add|generate|implement|write|make|build|produce|include|set up|initialize|scaffold|install|open it|rerun|run)\b", _re.I),
    "Investigating": _re.compile(r"\b(examine|why does|why is|what.s going on|debug|diagnose|analyze what|look at this|can you examine|what.s wrong|trace|root cause|broken|fails|failing|error|identical.+different)\b", _re.I),
    "Designing":     _re.compile(r"\b(redesign|prominent|visual|layout|style|look like|look more|distinction|spacing|story|compelling|section|appearance|prototype|mockup|wireframe|branding|banner)\b", _re.I),
    "Researching":   _re.compile(r"\b(what.s the|how does|how do|are there|can i do|do they|what can|what would|how come|cost|limit|explain|compare|difference|option)\b", _re.I),
    "Iterating":     _re.compile(r"\b(adjust|simplify|change the|not impressed|didn.t like|better|improve|also like|refine|tweak|move this|swap|resize|reorder|reduce|remove the)\b", _re.I),
    "Shipping":      _re.compile(r"\b(commit|push|pr\b|pull request|merge|deploy|ship|tag|release|check.?in)\b", _re.I),
    "Planning":      _re.compile(r"\b(plan|propose|approach|strategy|stages|phases|priority|before that|options|go ahead|wait for)\b", _re.I),
    "Testing":       _re.compile(r"\b(test|verify|validate|check if|smoke|does it work|try it|confirm)\b", _re.I),
    "Configuring":   _re.compile(r"\b(config|setup|auth|login|permission|access|credential|settings|env|alias|profile)\b", _re.I),
    "Navigating":    _re.compile(r"\b(find|search|where is|show me|list|fetch|locate|get the latest|look for)\b", _re.I),
}

_INTENT_ICONS = {
    "Building":      "&#128679;",
    "Investigating": "&#128300;",
    "Designing":     "&#127912;",
    "Researching":   "&#128202;",
    "Iterating":     "&#128260;",
    "Shipping":      "&#128640;",
    "Planning":      "&#128203;",
    "Testing":       "&#9989;",
    "Configuring":   "&#9881;",
    "Navigating":    "&#129517;",
}

_INTENT_COLORS = {
    "Building":      "#0078d4",
    "Investigating": "#e65100",
    "Designing":     "#7b1fa2",
    "Researching":   "#1a7f37",
    "Iterating":     "#0969da",
    "Shipping":      "#cf222e",
    "Planning":      "#8250df",
    "Testing":       "#1a7f37",
    "Configuring":   "#6a737d",
    "Navigating":    "#bf8700",
}

# Document/data file extensions worth surfacing as referenced docs
_DOC_EXTS = {
    ".pptx", ".ppt", ".docx", ".doc", ".pdf",
    ".xlsx", ".xls", ".csv", ".md", ".txt",
    ".ipynb", ".json", ".yaml", ".yml",
}

def _is_approval(text: str) -> bool:
    """True if the message is purely an approval/permission grant, not a real instruction."""
    cleaned = text.strip().rstrip(".!").lower()
    # Single email address — it's context/data, not a standalone task
    if _re.fullmatch(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', cleaned):
        return True
    if len(cleaned.split()) > 8:
        return False
    return cleaned in _APPROVALS


def _resolve_path_segments(base: Path, segments: list) -> Path | None:
    """
    Recursively match encoded segments to an actual filesystem path.
    Each '-' could be a path separator OR a space in a folder name, so we try
    combining 1..N segments as a single folder name until we find a match.
    """
    if not segments:
        return base
    for n in range(1, len(segments) + 1):
        candidate = " ".join(segments[:n])
        child = base / candidate
        if child.exists():
            result = _resolve_path_segments(child, segments[n:])
            if result is not None:
                return result
    return None


def _decode_project_name(encoded: str) -> str:
    """
    Resolve the encoded folder name to a human-readable project name by
    checking the filesystem — distinguishes path separators from spaces.
    Falls back to simple dash-replacement if the path cannot be resolved.
    """
    m = _re.match(r'^([A-Z])--(.+)$', encoded)
    if not m:
        return encoded

    drive   = m.group(1)
    parts   = m.group(2).split("-")
    base    = Path(f"{drive}:/")
    resolved = _resolve_path_segments(base, parts)

    if resolved:
        try:
            rel = resolved.relative_to(Path.home())
            return str(rel)
        except ValueError:
            return str(resolved)

    # Full resolution failed. Try to resolve as much of the path as possible,
    # then show the remainder with dashes (preserving ambiguous segments).
    m2 = _re.match(r'^[A-Z]--Users-[^-]+-(.+)$', encoded)
    if not m2:
        return encoded
    rest_parts = m2.group(1).split("-")
    # Walk from home, consuming segments that exist
    cur = Path.home()
    consumed = 0
    for i in range(1, len(rest_parts) + 1):
        candidate = " ".join(rest_parts[consumed:consumed + i - consumed])
        # Try each length combination greedily one step at a time
        for n in range(1, len(rest_parts) - consumed + 1):
            candidate = " ".join(rest_parts[consumed:consumed + n])
            if (cur / candidate).exists():
                cur = cur / candidate
                consumed += n
                break
        else:
            break
    resolved_prefix = str(cur.relative_to(Path.home())) if cur != Path.home() else ""
    remainder = "-".join(rest_parts[consumed:])
    if resolved_prefix and remainder:
        return f"{resolved_prefix}\\{remainder}"
    return resolved_prefix or remainder or encoded


def _reconstruct_project_path(encoded: str) -> str:
    """
    Reconstruct the full filesystem path from the encoded folder name,
    using filesystem resolution to correctly handle spaces in folder names.
    """
    m = _re.match(r'^([A-Z])--(.+)$', encoded)
    if not m:
        return encoded

    drive    = m.group(1)
    parts    = m.group(2).split("-")
    base     = Path(f"{drive}:/")
    resolved = _resolve_path_segments(base, parts)
    return str(resolved) if resolved else encoded


def _extract_doc_names(result_text: str) -> list:
    """Pull document/file basenames out of a tool result string (e.g. Glob output).

    Only returns results when the result looks like a specific file access (1-5 matches),
    not a broad directory listing (>5 matches = noise, skip).
    """
    found = []
    seen = set()
    for token in _re.split(r'[\n\r]+', result_text):
        token = token.strip()
        if not token:
            continue
        # Must look like a file path (contains a path separator or is just a name with extension)
        # Skip lines that are clearly commands or descriptions (contain spaces before the extension)
        if " " in token and not (token.startswith("/") or token[1:3] in (":/", ":\\")):
            continue
        name = Path(token.replace("\\", "/")).name
        # Skip temp/lock files and glob patterns
        if name.startswith("~$") or name.startswith(".") or "*" in name:
            continue
        ext = Path(name).suffix.lower()
        if ext in _DOC_EXTS and name not in seen:
            found.append(name)
            seen.add(name)
        if len(found) >= 10:
            break
    # If this looks like a broad directory listing (>5 files), it's noise — skip
    return found if len(found) <= 5 else []


def _parse_tool_input(raw) -> dict:
    """Parse tool input which may be a Python repr string or dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return ast.literal_eval(raw)
        except Exception:
            return {"raw": raw[:200]}
    return {}


def _summarize_tool(name: str, inp: dict) -> str:
    """Create a short human-readable summary of a tool call."""
    if name == "Read":
        path = inp.get("file_path", "")
        return f"Read {Path(path).name if path else '?'}"
    if name == "Write":
        path = inp.get("file_path", "")
        return f"Write {Path(path).name if path else '?'}"
    if name == "Edit":
        path = inp.get("file_path", "")
        return f"Edit {Path(path).name if path else '?'}"
    if name == "Bash":
        cmd = inp.get("command", inp.get("description", ""))
        # Use description if available, else first 80 chars of command
        desc = inp.get("description", "")
        if desc:
            return f"Bash: {desc[:80]}"
        return f"Bash: {str(cmd)[:80]}"
    if name == "Glob":
        return f"Glob: {inp.get('pattern', '?')}"
    if name == "Grep":
        return f"Grep: {inp.get('pattern', '?')}"
    if name in ("WebSearch", "WebFetch"):
        return f"{name}: {str(inp.get('query', inp.get('url', '?')))[:80]}"
    if name == "Agent":
        return f"Agent: {str(inp.get('description', inp.get('prompt', '?')))[:80]}"
    if name in ("TaskCreate", "TaskUpdate"):
        return f"{name}: {str(inp.get('title', inp.get('taskId', '?')))[:60]}"
    return f"{name}: {str(list(inp.values())[0])[:60]}" if inp else name


def _parse_message(raw) -> dict:
    """
    The `message` field in session JSONL can be either:
      - a dict  (older format)
      - a Python repr string like "{'role': 'user', 'content': ...}"  (newer format)
    Returns a dict in both cases, or {} on failure.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return _parse_tool_input(raw)   # reuses ast.literal_eval logic
    return {}


def get_sessions_for_date(target_date: str) -> list:
    """
    Find all Claude sessions with activity on target_date (YYYY-MM-DD).
    Returns a list of session dicts.
    """
    sessions = []

    for jsonl_file in PROJECTS_DIR.glob("*/*.jsonl"):
        session_id = jsonl_file.stem

        messages = []
        tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        has_target_date = False
        session_start = None
        session_end   = None
        git_ops        = []
        git_repos      = set()
        lines_added_count = 0
        pull_requests  = []
        cwd_seen  = None   # actual working directory from entry metadata
        entrypoint = None  # 'cli', 'vscode', etc.

        try:
            with open(jsonl_file, encoding="utf-8") as f:
                raw_lines = f.readlines()
        except Exception:
            continue

        # First pass: check if this session touches target_date at all
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            ts = entry.get("timestamp", "")
            if ts and ts[:10] == target_date:
                has_target_date = True
                break

        if not has_target_date:
            continue

        # Second pass: extract content
        # Track pending tool calls to attach to the instruction that triggered them
        pending_tools = []

        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue

            ts = entry.get("timestamp", "")
            # Only process entries on target date
            if ts and ts[:10] != target_date:
                continue

            entry_type = entry.get("type")

            # Capture working directory and entrypoint from entry metadata
            if entry.get("cwd") and cwd_seen is None:
                cwd_seen = entry["cwd"]
            if entry.get("entrypoint") and entrypoint is None:
                entrypoint = entry["entrypoint"]

            if entry_type == "user":
                msg = _parse_message(entry.get("message", {}))
                # Skip sidechain/meta entries (internal tool plumbing)
                if entry.get("isSidechain") == "True" or entry.get("isMeta") == "True":
                    pass
                else:
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        text = content.strip()
                        if not _is_approval(text):
                            messages.append({
                                "role": "user",
                                "text": text,
                                "timestamp": ts,
                                "tools_after": [],
                            })
                    elif isinstance(content, list):
                        # Extract plain text from content blocks
                        text_parts = [
                            b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        ]
                        text = " ".join(text_parts).strip()
                        if text and not _is_approval(text):
                            messages.append({
                                "role": "user",
                                "text": text,
                                "timestamp": ts,
                                "tools_after": [],
                            })

                        # Tool results — extract doc filenames and GitHub repos
                        for item in content:
                            if not isinstance(item, dict):
                                continue
                            if item.get("type") != "tool_result":
                                continue
                            result_content = item.get("content", "")
                            if isinstance(result_content, str):
                                doc_names = _extract_doc_names(result_content)
                                if doc_names and messages:
                                    last = messages[-1]
                                    if last["role"] == "user":
                                        for dn in doc_names:
                                            summary = f"DocFound: {dn}"
                                            if summary not in last["tools_after"]:
                                                last["tools_after"].append(summary)
                                # Extract lines added from git diff/commit stats
                                for lm in _re.finditer(
                                    r'(\d+) insertion',
                                    result_content or ""
                                ):
                                    try:
                                        lines_added_count += int(lm.group(1))
                                    except (ValueError, AttributeError):
                                        pass
                if ts:
                    if not session_start:
                        session_start = ts
                    session_end = ts

            elif entry_type == "assistant":
                msg = _parse_message(entry.get("message", {}))
                usage = msg.get("usage", {})

                # Accumulate tokens
                tokens["input"] += usage.get("input_tokens", 0)
                tokens["output"] += usage.get("output_tokens", 0)
                tokens["cache_read"] += usage.get("cache_read_input_tokens", 0)
                tokens["cache_creation"] += usage.get("cache_creation_input_tokens", 0)

                # Extract tool calls
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            raw_input = item.get("input", {})
                            parsed_input = _parse_tool_input(raw_input)
                            tool_summary = _summarize_tool(item.get("name", ""), parsed_input)
                            # Attach to the most recent user instruction
                            if messages and messages[-1]["role"] == "user":
                                messages[-1]["tools_after"].append(tool_summary)
                            # Track git/gh operations and GitHub repo slugs
                            if item.get("name") == "Bash":
                                cmd = parsed_input.get("command", "")
                                desc = parsed_input.get("description", "")
                                text = (desc or cmd)[:200]
                                if _re.search(r'\bgit\b|\bgh\b', text, _re.IGNORECASE):
                                    git_ops.append((desc or cmd)[:120])
                                # Only extract repos from push/remote/clone commands to avoid hallucinations
                                if _re.search(r'\bpush\b|\bremote\b|\bclone\b', text, _re.IGNORECASE):
                                    for m in _re.finditer(
                                        r'github\.com[:/]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git|[\s"\']|$)',
                                        text, _re.IGNORECASE
                                    ):
                                        slug = m.group(1).rstrip("/")
                                        # Filter out obvious placeholder/template repos
                                        parts = slug.split("/")
                                        if len(parts) == 2 and parts[0] not in ("org", "user", "owner", "username") and parts[1] not in ("repo", "repository", "project", "emails", "myrepo"):
                                            git_repos.add(slug)
                                # Detect PR creation
                                if _re.search(r'\bgh\s+pr\s+create\b', text, _re.IGNORECASE):
                                    pr_url_m = _re.search(r'https://github\.com/[^\s"\']+/pull/\d+', text)
                                    if pr_url_m:
                                        pull_requests.append(pr_url_m.group(0))

                if ts:
                    if not session_start:
                        session_start = ts
                    session_end = ts

        # Only include sessions that have at least one real user instruction
        user_messages = [m for m in messages if m["role"] == "user"]
        if user_messages:
            # Use cwd from entry metadata when available — more reliable than
            # decoding the folder name (handles spaces, resolves exactly)
            if cwd_seen:
                resolved_path = cwd_seen
                try:
                    rel = Path(cwd_seen).relative_to(Path.home())
                    # "." means session was run from home dir itself — use folder name
                    resolved_name = str(rel) if str(rel) != "." else Path(cwd_seen).name
                except ValueError:
                    resolved_name = str(Path(cwd_seen).name)
            else:
                resolved_path = _reconstruct_project_path(jsonl_file.parent.name)
                resolved_name = _decode_project_name(jsonl_file.parent.name)

            sessions.append({
                "session_id":   session_id,
                "project":      resolved_name,
                "project_path": resolved_path,
                "entrypoint":   entrypoint or "cli",
                "date": target_date,
                "messages": messages,
                "tokens": tokens,
                "session_start": session_start,
                "session_end": session_end,
                "git_ops":      git_ops,
                "git_repos":    sorted(git_repos),
                "lines_added":  lines_added_count,
                "pull_requests": pull_requests,
            })

    return sessions


def compute_elapsed_minutes(session_start: str, session_end: str) -> float:
    """Return wall-clock minutes between session start and end."""
    if not session_start or not session_end:
        return 0
    try:
        fmt = "%Y-%m-%dT%H:%M:%S"
        t0 = datetime.strptime(session_start[:19], fmt)
        t1 = datetime.strptime(session_end[:19], fmt)
        return max(0, (t1 - t0).total_seconds() / 60)
    except Exception:
        return 0


def compute_active_minutes(messages: list) -> float:
    """Return estimated active minutes from a list of session messages.

    Sums intervals between consecutive messages where the gap is <= 5 minutes
    (300 seconds), then adds a 30-second buffer for final message processing.
    Returns 0.0 if no timestamps are present, 1.0 if only one message.
    """
    timestamps = []
    for m in messages:
        ts = m.get("timestamp", "")
        if ts:
            timestamps.append(ts)

    if not timestamps:
        return 0.0
    if len(timestamps) == 1:
        return 1.0

    timestamps.sort()

    fmt = "%Y-%m-%dT%H:%M:%S"
    total_seconds = 0.0
    for i in range(1, len(timestamps)):
        try:
            t0 = datetime.strptime(timestamps[i - 1][:19], fmt)
            t1 = datetime.strptime(timestamps[i][:19], fmt)
            gap = (t1 - t0).total_seconds()
            if gap <= 300:
                total_seconds += gap
        except Exception:
            continue

    # Add 30-second buffer for final message processing
    total_seconds += 30

    return round(total_seconds / 60, 1)


def classify_message_intent(text: str) -> list:
    """Classify a single user message into one or more intent categories."""
    matched = []
    for cat, rx in _INTENT_CATEGORIES.items():
        if rx.search(text[:300]):
            matched.append(cat)
    return matched or ["Building"]


def classify_session_intents(session: dict) -> dict:
    """Classify all user messages in a session and return aggregated intent data."""
    counts = {k: 0 for k in _INTENT_CATEGORIES}
    timeline = []

    for m in session.get("messages", []):
        if m.get("role") != "user":
            continue
        intents = classify_message_intent(m.get("text", ""))
        ts = m.get("timestamp", "")
        for cat in intents:
            counts[cat] += 1
        if ts and intents:
            timeline.append((ts, intents[0]))

    # Auto-collapse: categories < 5% merge into nearest semantic parent
    total = sum(counts.values()) or 1
    _MERGE_MAP = {
        "Navigating":  "Researching",
        "Configuring": "Building",
        "Testing":     "Building",
        "Planning":    "Researching",
    }
    collapsed = dict(counts)
    for small_cat, parent in _MERGE_MAP.items():
        if counts[small_cat] / total < 0.05 and counts[small_cat] > 0:
            collapsed[parent] += collapsed[small_cat]
            collapsed[small_cat] = 0

    collapsed = {k: v for k, v in collapsed.items() if v > 0}

    return {
        "counts": collapsed,
        "counts_raw": {k: v for k, v in counts.items() if v > 0},
        "timeline": timeline,
        "total": sum(counts.values()),
    }


def aggregate_intents(sessions: list) -> dict:
    """Aggregate intent data across multiple sessions."""
    totals = {k: 0 for k in _INTENT_CATEGORIES}
    by_project = {}
    timeline = []

    for s in sessions:
        proj = s.get("project", "unknown")
        si = classify_session_intents(s)

        for cat, n in si["counts_raw"].items():
            totals[cat] = totals.get(cat, 0) + n

        if proj not in by_project:
            by_project[proj] = {k: 0 for k in _INTENT_CATEGORIES}
        for cat, n in si["counts_raw"].items():
            by_project[proj][cat] = by_project[proj].get(cat, 0) + n

        timeline.extend(si["timeline"])

    # Auto-collapse at aggregate level
    total = sum(totals.values()) or 1
    _MERGE_MAP = {
        "Navigating":  "Researching",
        "Configuring": "Building",
        "Testing":     "Building",
        "Planning":    "Researching",
    }
    collapsed = dict(totals)
    for small_cat, parent in _MERGE_MAP.items():
        if totals[small_cat] / total < 0.05 and totals[small_cat] > 0:
            collapsed[parent] += collapsed[small_cat]
            collapsed[small_cat] = 0
    collapsed = {k: v for k, v in collapsed.items() if v > 0}

    # Collapse per-project too
    collapsed_by_project = {}
    for proj, pcounts in by_project.items():
        ptotal = sum(pcounts.values()) or 1
        pc = dict(pcounts)
        for small_cat, parent in _MERGE_MAP.items():
            if pcounts[small_cat] / ptotal < 0.05 and pcounts[small_cat] > 0:
                pc[parent] += pc[small_cat]
                pc[small_cat] = 0
        collapsed_by_project[proj] = {k: v for k, v in pc.items() if v > 0}

    timeline.sort(key=lambda x: x[0])

    return {
        "counts": collapsed,
        "by_project": collapsed_by_project,
        "timeline": timeline,
        "total": sum(totals.values()),
    }
