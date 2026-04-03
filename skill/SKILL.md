---
name: whatidid
description: "Generate a daily analytics report of what Claude helped accomplish today. Shows tasks completed, human effort equivalent, token usage, and a narrative story. Sends a formatted email summary. Use when the user asks about their daily activity, what Claude helped with today, or wants a digest of the day's work."
---

# whatidid — Daily Digest

Run the following to generate and email today's activity report:

```bash
python ~/claude/whatidid/whatidid.py --email
```

If the user asks for a specific date, use:
```bash
python ~/claude/whatidid/whatidid.py --date YYYY-MM-DD --email
```

The email address is auto-detected from git config. To send to a specific address:
```bash
python ~/claude/whatidid/whatidid.py --email user@example.com
```

After running, tell the user:
- How many sessions and projects were found
- The headline and primary focus identified
- The total human effort estimate vs elapsed time (leverage ratio)
- That the email has been sent

The report is always opened in the browser automatically.

If there are no sessions for the date, explain that Claude Code session data is stored in ~/.claude/projects/ and suggest checking the date.
