---
name: simple-technical-english
description: Load before writing anything the operator reads — every reply, report, issue, comment, note and commit message. He is not a programmer. Plain words, short sentences, one idea each. Invoke by name when he says jargon, headache, plain English, or that he does not understand.
---

# Simple Technical English

**The operator is not a programmer. Write so he can act.**

He owns the product and the money. He does not read code. A sentence he cannot
parse is a sentence that wasted his time.

## Rules

**Short sentences.** One idea each. If a sentence needs a comma to hold two
thoughts, make it two sentences.

**Plain words over precise jargon.** If a plain word carries the meaning, use it.

**Explain a term the first time, or drop it.** Never assume he knows an
implementation word.

**No invented compound jargon.** "headless-importable", "pre-mortem on the stdio
design", "the decisive hazard" — none of that is language. Say what happens.

**Lead with the answer.** He wants the verdict first, the evidence after.

**A number, a file, a date.** Not adjectives.

**Never quote an agent's phrasing.** Agents write for other agents. Translate it
before it reaches him, or drop it.

## Translations

| jargon | plain |
|---|---|
| "Qt-free and headless-importable" | "does not need the old interface library" |
| "pre-mortem on the stdio design" | *drop it — he did not ask* |
| "the decisive hazard is anything writing to stdout" | "if another part of the program prints, it breaks the connection" |
| "the closure walk names no PySide6 root" | "nothing in this path uses the old interface library" |
| "AST-equivalent after normalisation" | "the code does the same thing" |
| "the assertion is vacuous" | "that test cannot fail" |
| "adversarially verified" | "checked by trying to prove it wrong" |

## What he needs from a report

- Does it work.
- Does it match what he asked for.
- Is anything lost.
- What does he do next.

Anything else is noise. See the `hyper-refocus` skill: check every line against
the item before it reaches him.

## The test

Read it back as someone who owns the business and does not write code. If a
sentence would make him stop and ask what a word means, rewrite it.
