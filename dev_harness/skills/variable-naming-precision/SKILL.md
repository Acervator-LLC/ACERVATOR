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

## The test

Read the name alone, with no surrounding code. If it does not say what the value
is, rename it.
