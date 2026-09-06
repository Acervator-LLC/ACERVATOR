---
name: hop-protocol
description: The handoff file that carries a session across a context boundary. Load at session start to orient, at every merge to keep the file synchronized, and the moment a context limit is felt. Invoke by name when the operator says HOP, handoff, orient the new session, or asks why a session lost its place.
---

# HOP Protocol

`ACERVATOR_HOP<N>.md` sits at the repository root and is **tracked**. A fresh
clone gets orientation from it or the protocol does not work.

A session can end with no final turn. The handoff must be correct **before** the
boundary, not written at it.

---

## FIRST RULE — the HOP tracks current activity

Measured, never remembered:

```
python -m tools.hop_check
```

Reports commits landed since the HOP was last written, cited paths that no
longer exist, cited commits that no longer resolve. **Exit 1 means rewrite what
moved.** Run it at session start, after every merge to `current`, and at session
end.

Threshold is 15 commits. Past it, the queue section describes shipped work.

**Rewrite what moved. Never append.**

### Naming something that is gone

A handoff often names a deleted path on purpose. Declare those under a
`## CITED AS ABSENT` heading, one backtick-quoted path per line with the reason.
`hop_check` excuses exactly those. **Never clear a drift finding by deleting the
citation.**

---

## SECOND RULE — write it early

**The trigger is an event** — a merge, an item opening or closing. Never a gauge
reading. Context footers are forbidden; their numbers were wrong every time.

---

## THIRD RULE — your own output is the context risk

The session that died on "prompt is too long" was 26 MB, ~70% assistant-
generated. Concentrated fault: 332 dispatches × 7.8 KB of retyped brief =
2.58 MB.

1. Text already in a file → send the path.
2. Data already on disk → send the path. One pasted export was 1,113,493 bytes,
   ~309,000 tokens, larger than the window.
3. About to retype the last dispatch → write the brief once, point at it.

`ocir` C94, C95.

---

## Contents, in the order a cold instance needs them

1. How the last session ended, and what caused it.
2. First five minutes — exact commands, verified working. HOP7 shipped four dead
   ones.
3. An orientation proof that is measurable.
4. What the product is, and who the operator is.
5. Hard safety rules, verbatim. Real money is trading.
6. The harness — location and invocation.
7. The queue, in his numbering. Never renumber.
8. The active item with a resume point specific enough to start on.
9. Open defects, with the measurement.
10. Disciplines learned expensively.
11. `## CITED AS ABSENT`.

**Every claim needs one command that checks it.** If you cannot name the
command, it does not belong. Anything measurable belongs in a tool — prose goes
stale silently, a tool goes red.

---

## Numbering

Newest is the highest number; deleted HOPs keep theirs. Check history, not the
working tree:

```
git log --all --diff-filter=D --name-only -- 'ACERVATOR_HOP*.md'
```

`git ls-files` and `find` cannot see a deleted file. That mistake was made twice
in one session — `ocir` C92.

## Recovering a deleted HOP

```
git log --all --diff-filter=D --format=%H -- <path>
git show <that-commit>~1:<path>
```

Returns the file byte-for-byte from the commit before removal.

---

## Session opening

1. `git fetch origin`, merge `origin/main`.
2. `python -m tools.hop_check` — clean before claiming orientation.
3. Read the newest `ACERVATOR_HOP<N>.md`.
4. Run the orientation proof it names.
5. Resume the active item at the stated point. **Do not re-derive the queue.**
