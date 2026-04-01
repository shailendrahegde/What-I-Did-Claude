# Architecture

## Data flow

```
~/.claude/projects/*/session.jsonl
           │
           ▼
       harvest.py
  - Scans all session files for target date
  - Extracts user instructions (filters approvals)
  - Captures tool call summaries (Read, Write, Edit, Bash, Glob, …)
  - Extracts doc filenames from tool results (Glob/Bash output)
  - Accumulates real token counts (input, output, cache_read, cache_creation)
  - Detects git/GitHub operations
  - Returns: list of session dicts
           │
           ▼
       analyze.py
  - Builds a structured transcript from session data
  - Calls Claude Haiku API with goal-grouping + language rules
  - Returns: goals[] with tasks[], skills, hours, docs_referenced
  - Caches result to ~/.claude/whatidid/cache/YYYY-MM-DD.json
           │
           ▼
       report.py
  - Generates Outlook-compatible HTML
  - Layout: header → narrative → KPI cards → goals table → token bar → task accordion
           │
           ▼
   email_send.py (optional)
  - Writes HTML to temp file
  - PowerShell Outlook COM automation sends it
  - No extra packages required
```

## Session file format

Claude Code writes one JSONL file per session at:
```
~/.claude/projects/<encoded-path>/<session-id>.jsonl
```

Each line is a JSON object with `type`, `timestamp`, and `message`. Relevant types:

| Type | Content |
|---|---|
| `user` (string content) | Human instruction |
| `user` (list content) | Tool results (Glob output, Bash stdout, etc.) |
| `assistant` | Claude response — contains `tool_use` blocks and `usage` (token counts) |

## Project path encoding

The folder name encodes the working directory path:
```
C--Users-shahegde-claude-whatidid  →  C:\Users\shahegde\claude\whatidid
C--Users-shahegde-Downloads-Adhoc  →  C:\Users\shahegde\Downloads\Adhoc
```

## Token cost model

Uses Anthropic's published per-token rates (as of early 2026):

| Token type | Rate |
|---|---|
| Input | $3.00 / 1M |
| Output | $15.00 / 1M |
| Cache read | $0.30 / 1M |
| Cache creation | $3.75 / 1M |

Update these in `report.py → _cost()` and `_kpi_section()` if rates change.

## Leverage metric

```
human_value  = total_human_hours × HOURLY_RATE   ($150/hr default)
leverage     = human_value / api_cost_dollars
```

Example: 11h × $150 = $1,650 human value ÷ $16 API spend = **103×**

This measures return on AI spend, not speed. A higher number means you got more
senior-professional-equivalent work done per dollar of API cost.
