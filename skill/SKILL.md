---
name: whatidid
description: "Generate a daily analytics report of what Claude helped accomplish today. Shows tasks completed, human effort equivalent, token usage, and a narrative story. Sends a formatted email summary. Use when the user asks about their daily activity, what Claude helped with today, or wants a digest of the day's work."
---

# whatidid — Daily Digest

Run the following to generate and email today's activity report:

```bash
python ~/claude/whatidid/whatidid.py --email shahegde@microsoft.com
```

If the user asks for a specific date, use:
```bash
python ~/claude/whatidid/whatidid.py --date YYYY-MM-DD --email shahegde@microsoft.com
```

If the user just wants to view (no email):
```bash
python ~/claude/whatidid/whatidid.py --html
```

After running, tell the user:
- How many sessions and projects were found
- The headline and primary focus identified
- The total human effort estimate vs elapsed time (leverage ratio)
- That the email has been sent (or HTML saved)

If there are no sessions for the date, explain that Claude Code session data is stored in ~/.claude/projects/ and suggest checking the date.
