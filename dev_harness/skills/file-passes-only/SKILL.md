---
name: file-passes-only
description: Load before every reply to the operator while a conversion item is open. One six-line block per converted file, under 30 words, and nothing else. Invoke by name when he says report, shut up, or no more reports.
---

# One block per file, under 30 words

**He reads one thing: which file is done.** Operator, 2026-09-05, verbatim:

> "FILE CONVERTED. FILE TESTED. FILE VERIFIED. TABLES UPDATED. MANUAL UPDATED.
>  MERGED. REPEAT UNTIL 128 IS COMPLETE"
>
> "IT TAKES LESS THAN 30 WORDS PER FILE STATUS REPORT TO TELL ME WHAT I NEED TO
>  KNOW."

## The format, exactly

```
<path>
converted · tested · verified · tables updated · manual updated · merged
```

Under 30 words. One block per file. Nothing above, nothing below.

A step that did not happen is named instead of claimed. A file with any step
missing is not reported at all — it is not done.

When no file is done, say nothing. An empty turn is the correct reply.

## What each step means, and none of them is a claim

- **converted** — the screen draws from React in the running program.
- **tested** — the canonical check ran on that row.
- **verified** — it rendered on screen and its controls were driven, with the
  change read back off the real object. Not a green suite.
- **tables updated** — the row is marked in the issue body and in the manual.
- **manual updated** — the manual's section matches what the file now does.
- **merged** — landed on `current` and pushed.

## What never goes in a reply

- A pushed SHA, a branch, a unit, a merge detail.
- What is running, what is next, what is blocked.
- A measurement, a count, a table, a total, a gate result.
- A defect found, a control proved.
- An explanation of why a file is not done.

All of it lives in the issue and the manual. He reads those when he wants them.

**No category labels.** Writing `Chrome:` or `Status:` in front of a sentence to
make it look organised is the defect he named — *"useless information
categorization trying to sound official"*.

## Answering a direct question

He asks something — answer it, in as few lines as it takes, and stop. That is
not a report and this rule does not forbid it.

## The measurement behind this

Every long reply during #128 was true and unread. He said so five times in one
session — *"I do not read them"*, *"dozens of meaningless fucking paragraphs"*,
*"no more reports"*, *"stop talking"*, *"shut the fuck up"*. The words were never
the deliverable. A converted file is.

## Falsification

This skill is wrong if he asks for a status summary and gets one block. Then he
has asked a question, and the section above governs.
