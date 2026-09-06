---
name: canonized-code-testing
description: Load before running or writing any test. Tests are canon — you run one, you never write one, and only the owning archetype runs its own type. Invoke by name when the task mentions tests, coverage, verification or a check.
---

# Canonized code testing

**You do not create tests. You run one from the canon.**

Operator, 2026-09-06, verbatim:

> "You are not allowed to create fucking tests. You are allowed to run one from
>  the canon and tool box and they are only to be ran by their owning archetype
>  based on test type."

## The measurement that forced this

One session, 2026-09-05 to 2026-09-06, `git log`:

```
commits                        321
  touching tests/              202
  touching src/gui/             60
  touching src/gui/web/         48
  touching desktop/             14
  whose subject is a fix        71

test files added                29
test files modified            284
test lines      +23,151  -18,106
product lines   +14,872   -6,134
```

**More test churn than product, and 284 modifications.** That is the write-run-
fail-edit-rerun loop, and it is where the hours went. Fourteen commits reached
the Electron shell, which was the item.

## The canon

A test belongs to exactly one archetype, by type. Run it through that archetype
and no other path.

| type | owner | command |
|---|---|---|
| all code | Coding Archetype | `python -m dev_harness.harness.coding_archetype <path>` |
| any arithmetic | TA Quant | `python -m dev_harness.harness.ta_archetype <path>` |
| PySide6 and JavaScript screens | GUI Archetype | `python -m dev_harness.harness.gui_archetype <path>` |
| markdown | Docs Archetype | `python -m dev_harness.harness.docs_archetype <path>` |
| a report or a claim | Truth Archetype | `python -m dev_harness.harness.truth_archetype <path>` |
| the emitters | Watchdog Archetype | `python -m dev_harness.harness.watchdog_archetype <path>` |

Beside those sit the repository's own canonical checks — the one that runs the
same steps over every conversion row, and `tests/test_desktop_shell_assets.py`
for shipped JavaScript. Run the one that covers the behaviour.

## When no canon test covers it

**Say so. Do not fill the gap yourself.**

The deliverable is a proposed rule for the operator, naming the behaviour and
the archetype that should own it. A missing check is a harness finding, and the
harness is his.

This is the same rule as `harness-law`: you are a referee, not an author. A test
you wrote and then edited until it passed proves what you wrote, not what the
code does.

## Running a canon check

- **Prove the instrument first, once per session.** `known_good` exits 0,
  `known_bad` exits 1. A check nobody has watched fail is not a check.
- **Read the exit code directly**, never through a pipe. 139 is a crash and
  prints no summary.
- **Check `tool_availability`.** A tool marked `missing` did not run, and
  silence from it is not a pass.
- **Report `passed`, never a delta.** Fewer findings than last time is not a
  pass.

## What a green means

"Nothing already thought of is broken." Not correctness.

The runtime observation is the evidence: the object was constructed, the panel
drew, the record was written. **A passing check is never the deliverable of a
conversion unit** — the screen on screen is.

## Falsification

This skill is wrong if a defect reaches the operator that a canon check could
have caught and none existed. Then the missing rule is the finding, and it goes
to him as a proposal.
