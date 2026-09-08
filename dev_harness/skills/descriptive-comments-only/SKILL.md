---
name: descriptive-comments-only
description: Load before writing or reviewing any comment, docstring, commit message, PR body, issue body or engineering note. Comments state a technical fact or do not exist. Invoke by name when the operator says narrative, story, verbose, or diary.
---

# Descriptive comments only

**Say something valuable or say nothing at all.**

A comment states a technical fact the code does not state. It does not tell a
story, explain a decision, justify itself, or address the reader.

## Default to no comment

The code is the source of truth. A reader gets more from a clear name than from
prose describing one. When in doubt, leave it out — a reviewer can ask for a
comment; noise is harder to remove later.

## Never

- **Narrative.** No "this exists because", no "we do X so that Y", no account of
  what was tried first or what was rejected.
- **History.** What a previous version did belongs in `git blame`, not the file.
- **Identifiers from outside the code.** No version names, no issue numbers, no
  PR numbers, no item numbers, no MEM-numbers.
- **Restatement.** If the comment paraphrases the line below it, delete it.
- **Hedging.** No "this should", "we may want to", "in theory".
- **Quoting the operator.** Never put his words into a comment or a file.

## The hard cap — 20 words, one sentence, no second paragraph

**A comment or docstring is at most 20 words and one sentence.** Over 20, cut it
or delete it. A second paragraph is never allowed. This is a count, not a
judgement: if it will not fit in 20 words, the code needs a better name.

**Every word names something in the block it sits on** — a function, a variable,
a file, a number, a type. A word naming nothing in that block is cut.

## Never write in metaphor

**Banned in any comment or docstring**, however natural they feel: *gate, plant,
planted, blind, fires, holder, reader, harness, island, ratchet, seam*,
*control* as a noun, and any sentence that personifies code.

Those words come from **briefs and reports**, where they are precise. Inside a
file they read as invention, because the reader has no brief. Caught live in a
docstring reading *"The control on the gate the plant runs behind"* — every noun
a metaphor, meaningless to anyone holding only the code.

**Write what the code does, in the identifiers it uses.**

Wrong: *"The control on the gate the plant runs behind."*
Right: *"`module_file_held` refuses a second holder while `LOCK_PATH` exists."*

## Always

- One or two lines. A paragraph means the code needs restructuring, not prose.
- A number or a name beats an adjective. `retries every 2 s at GUI tick rate`,
  not `retries frequently`. `60 s cool-off`, not `a reasonable delay`.
- Active voice, present tense.
- Match the surrounding file's comment density. Do not raise it.

## Pull request and issue bodies — 200 words, read by a non-programmer

The operator reads these and does not read code. **If he cannot tell what changed
and what it means for him, the body is wrong.**

**Cap: 200 words.** Four headings at most.

**Every sentence names a screen, a file, a number, or a behaviour he can see.**
A sentence that names none of those is cut.

**Banned in a body:** catalogue ids (`C72`, `C80`), rule ids (`R1`, `R10`),
instrument words — *probe, control, declared, held, blind, plant, harness,
surface* used as jargon — and any account of how the checking was done. Those
belong in the agent's report, not in what he reads.

**Structure:**

1. **What changed** — the screen, in his words.
2. **What it does now** — behaviour, not mechanism.
3. **What is proved** — one line, in plain counts.
4. **What is not done** — always present, always plain.

Wrong: *"Whole payload compared both directions with both counts; rendered
result compared against a probe styled from the surface's own declarations,
never a typed number."*

Right: *"The React header strip shows the same 16 values as the Qt one, checked
against every state. Nothing on screen changes yet — no window draws it."*

## Shapes

Wrong:
`# Read the venue fee here because the config value is an estimate and using it
would book a number the exchange never charged.`

Right:
`# Venue fee. Config trading_fee_pct is an estimate, not charged.`

A docstring explains what the function does and how it ties into the
application. A test docstring states **what a failure means**, in one line — not
the steps.

## This binds every artifact

Comments, docstrings, commit messages, PR titles and bodies, issue titles and
bodies, issue comments, engineering notes, memory files.

The narrative tells, and what replaces them:

| narrative | descriptive |
|---|---|
| "It passes alone, so it must be an interaction" | "Passes in isolation. Fails at position N of the full run." |
| "Opening this so CI can adjudicate" | "CI does not run on `current`. A PR fires the `pull_request` trigger." |
| "This has been fixed before and regrew" | "Purged 2026-08-03. 468 entries on 2026-08-28." |
| "I should have checked first" | omit — not a fact about the subject |

A verdict, a number, a `file:line`, a date. No reasoning shown, no decisions
justified, no account of what was done or not done.
