# Analysis Rules

These rules govern how `analyze.py` instructs Claude to interpret and summarise a day's work. They are embedded directly in the prompt sent to the model. Editing them here won't automatically update the prompt — keep this file and `analyze.py` in sync.

---

## Rule 1 — Goal grouping

Goals represent **business outcomes**, not implementation steps. One goal = one thing that now exists or works that didn't before.

### Default: when in doubt, merge

Too few goals is always better than too many.

### Iron rule

Everything in the same session that touches the same system is **one goal**. Iterating, refining, tweaking layout, fixing bugs, adjusting prompts, adding features, debugging — these are all tasks within the original goal, not separate goals.

### Merge when any of these are true

- Same session and work touches files created or modified earlier in that session
- The work configures, enables, fixes, refines, or extends something already built today
- The goal title would reference the same tool/project/subject as an existing goal
- Setting up auth/keys/config *for* a tool = part of building that tool
- Iterating on the report layout/format/prompt = part of building the analytics system

### Create a new goal only when all of these are true

- Completely different subject matter (e.g. analytics tool vs. reviewing an unrelated document)
- Different deliverable (e.g. code vs. a strategic recommendation)
- No dependency — could have been done in a totally separate session with zero shared context

### What counts as a task, never a separate goal

- Fixing a bug or encoding error in something just built
- Refining layout, format, or visual hierarchy of a report you built
- Adjusting the analysis prompt or goal-grouping rules for a tool you built
- Adding a new feature to a tool you built
- Setting up API keys or config for a tool you built
- Debugging compatibility issues in a tool you built

### Goal title format

Verb-first, business outcome, confident tone.

```
✓ "Shipped a daily work digest tool from concept to working system"
✓ "Provided strategic rewrite recommendations for the presentation"
✓ "Diagnosed and resolved checkout regression in production"

✗ "Set up API authentication"       ← this is a task
✗ "Built HTML report generator"     ← this is a task
✗ "Refined report formatting"       ← this is a task
```

---

## Rule 2 — Language

Write as if briefing a senior executive. Confident, direct, outcome-focused.

### Forbidden phrases

These imply the human was unclear or needed to course-correct. Never use them.

| Forbidden | Why |
|---|---|
| "vague need" / "vague request" / "unclear requirements" | Implies the human wasn't sure what they wanted |
| "initially" / "eventually" / "after some iteration" | Implies direction changed |
| "settled on" / "ended up with" / "finally decided" | Implies uncertainty |
| "the user clarified" / "after feedback" / "upon reflection" | Implies correction |

### No assumed context

Only use information visible in the transcript.

```
✗ "investor presentation" — forbidden unless the transcript says so
✗ "sales deck" / "board deck" — forbidden unless stated
✓ Use the actual filename if visible: "Viva Insights - Customer Jobs and Challenges.pptx"
✓ If no title is visible, use the generic type: "the presentation", "the document"
```

### Good framing

```
✓ "Designed and shipped X"
✓ "Built X with Y capability"
✓ "Delivered X that does Y"
✓ "Refined X to include Y"
```

---

## Rule 3 — Effort estimates

`human_hours` = what a skilled senior professional would need starting from scratch, without AI.

- Single number, nearest 0.5h. No ranges.
- Lean conservative (high, not low).
- `goal.human_hours` must exactly equal the sum of its task hours.

---

## Rule 4 — Docs referenced

Only include documents that were the **actual subject of work** — a PPTX whose content was analysed, a report that was generated.

```
✓ A PPTX whose text was extracted and analysed
✓ A report file that was generated as output
✗ Files found in a directory scan but not actually opened or processed
✗ Config files, lock files, internal tool files (unless the explicit deliverable)
```

Use just the filename, not the full path.
