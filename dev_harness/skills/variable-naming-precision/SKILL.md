---
name: variable-naming-precision
description: Load before naming any variable, function, class, parameter, test or module in Acervator. Names are short, functional and exact. Invoke by name when the operator comments on naming, or when a name needs a comment to explain it.
---

# Variable naming precision

**Short. Functional. Exact.**

A name says what the thing IS or what it DOES. If a name needs a comment to
explain it, the name is wrong — fix the name, do not add the comment.

## Short

Two or three words. A name that reads as a sentence is describing something the
code should express structurally.

Wrong: `the_total_amount_of_usd_currently_reserved_across_siblings`
Right: `sibling_reserved_usd`

## Functional

The name says its job, not its history, its type, or its provenance.

- No version names, issue numbers, item numbers, PR numbers, MEM-numbers.
- No `new_`, `old_`, `v2`, `_final`, `_fixed`, `temp_`, `_real`.
- No type in the name when the type is obvious — `bot_list` not
  `bot_list_array`.
- No `data`, `info`, `stuff`, `thing`, `obj`, `val`, `result` alone.

## Exact

The name matches what the value actually holds. A near-miss is a defect waiting
to happen.

- **Units belong in the name** where a bare number is ambiguous:
  `cooldown_s`, `notional_usd`, `size_units`, `bb_pos_pct`, `interval_ms`.
- **A count is not a total.** `fold_count` and `fold_total_usd` are different
  things and must not share a stem.
- **A flag reads as a predicate**: `is_armed`, `has_tranches`, `should_fire`.
  Never `flag`, never `check`, never a bare noun.
- **A boolean's name matches its true case.** `hold_in_uptrend` being true must
  mean it holds.

Measured defect of this class in this project: a field named
`amount_precision` documented as "Decimal places for amount" received a
step size like `1e-06`. The name was exact; the value was not — and 886 of 929
markets sized wrong for a year because nothing forced them to agree.

## Match the surrounding code

An existing name for the same concept is the name. Two spellings of one thing is
the defect — `scrum_fold_pct` and `fold_ratio` cannot both exist for the same
value.

Read the file before naming. The tree's vocabulary wins over a better idea.

## Labels for work follow the same rules

Operator, 2026-11-18:

> "For the sake of avoiding future instances not being able to properly
> interpret the labels, let's try to avoid of the recent alpha-numeric cryptic
> naming and stick with rules similar to variable naming. We have to be
> considerate of future Claude."

A unit's name, a branch, a worktree folder, a scratch file, a data set, a record
file and an experiment step are read later by a session that was not there.
Each one says what the thing is or does, in plain words.

| Wrong | Right |
|---|---|
| unit `E30` | unit "sigil feedback folder switch" |
| branch `u1633-e30` | branch `sigil-feedback-folder-switch` |
| worktree `wt-1633-e30` | worktree `wt-sigil-feedback-folder-switch` |
| scratch file `u1633e30_drive.py` | scratch file `folder_switch_readings.py` |
| `GR_pr.md` | `grounding_rule_pull_request.md` |
| step "E3.0" | "experiment 3's per-folder switch" |

- A task is named `Task_##_Description`, two digits and then its subject in
  words, such as `Task_10_Stock_Check`. Operator, 2026-11-18: "Task naming
  should be Task_##_Description. This is just an expansion of our broader
  naming conventions."
- An issue number may sit beside the words, never replace them:
  `1633-folder-switch`.
- Name each scratch artefact for its unit, as `branch-discipline` requires, and
  make that prefix the unit's words.
- An id that a registry defines stays as it is: an OCIR row (`C155`), a rule code
  (`LOOP001`, `B602`), a comment id. Never coin a new code for a label.

## The test

Read the name alone, with no surrounding code. If it does not say what the value
is, rename it.
