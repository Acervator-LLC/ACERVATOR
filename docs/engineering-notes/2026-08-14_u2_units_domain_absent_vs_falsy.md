# U2 follow-up: an absent units key is not a falsy units value

Date: 2026-08-14
Island: `U2_UNITS_DOMAIN`
Files: `src/trading/scrumming_bot.py`, `tests/test_reconcile_lot_book.py`,
`tests/test_extractor_tranche_containment.py`

## The finding, restated

`_reconcilable_lot_book` read each lot as `_raw if _raw else 0.0` before
handing it to `_reconcilable_units`. That is a truthiness test on the
VALUE where the question is about the KEY. Every falsy non-number
short-circuited to a clean `0.0` and never met the exact int/float type
ground, so the reader that refuses `"0"` accepted `""`.

The finding is real and reproduces. It is not inert either: on the
drift-down branch the lot is written back as `0.0 * ratio` and dropped
by the `> 1e-12` filter, so the audit would DELETE the lot and its
`initial_buy_price` in silence.

## The reachability claim in the finding is wrong

The finding said the falsy rows have "the same reachability as the
`"12.5"` row the table names explicitly", citing the lot-shape filter at
`_restore_state`. That filter is not the last word. Eleven lines below
it, `import_scrumming_state` totals the book with a BARE coercion and no
`or 0`, and that expression is not inside a `try`.

Driven on the promoted tree, one row per value, against the real
`import_scrumming_state` and the real `_reconcilable_lot_book`:

| units value | restore | audit (before) | audit (after) |
|---|---|---|---|
| no `units` key | SURVIVES | ACCEPT 0.0 | ACCEPT 0.0 |
| `12.5` | SURVIVES | ACCEPT 12.5 | ACCEPT 12.5 |
| `0`, `0.0`, `-0.0` | SURVIVES | ACCEPT 0.0 | ACCEPT 0.0 |
| `nan`, `inf`, `-5.0` | SURVIVES | REFUSE | REFUSE |
| `True` | SURVIVES | REFUSE | REFUSE |
| `"12.5"`, `"0"` | SURVIVES | REFUSE | REFUSE |
| `""` | **ABORT ValueError** | ACCEPT 0.0 | REFUSE |
| `"banana"` | **ABORT ValueError** | REFUSE | REFUSE |
| `None` | **ABORT TypeError** | ACCEPT 0.0 | REFUSE |
| `[]`, `{}`, `()` | **ABORT TypeError** | ACCEPT 0.0 | REFUSE |
| `0j` | **ABORT TypeError** | ACCEPT 0.0 | REFUSE |

Every value the audit mis-accepted aborts the restore. `bot_container`'s
`restore_bots_from_state` catches that abort, skips registration, and
the on-disk record is carried forward intact. A bot that never registers
never ticks and never reconciles.

`""` and `"12.5"` therefore do NOT have the same reachability. `"12.5"`
reaches a registered bot; `""` cannot.

## The decision

**A PRESENT units value that is not exactly an int or a float is
REFUSED. An ABSENT key stays a zero.**

The docstring's argument for the zero — "refusing it would leave a bot
permanently unreconcilable over a lot that holds nothing" — is earned by
the ABSENT key, which is `.get`'s default and a shape the restore really
does load. It is not earned by a key that is present holding `""`, `[]`
or `{}`. Those are not a quantity of zero coins; they are a units field
`float()` cannot read at all, which is the broken state this reader
exists to refuse, and it already refuses the strictly less broken `"0"`.

The tension the finding raised — that tightening the audit would strand
a bot whose restore loaded such a book — is dissolved by measurement
rather than by argument. No such book reaches a registered bot.

## What changed, and why both readers move together

1. `_reconcilable_lot_book` now reads
   `0.0 if "units" not in _lot else _lot["units"]`. The key decides the
   default; the value never does.

2. The restore gate at `import_scrumming_state` is unchanged in
   BEHAVIOUR and corrected in DESCRIPTION. Its comment said "warn but
   don't block". The drift comparison warns; the coercion blocks, and
   that block is what the whole tightening rests on. The comment now
   says so, and names the consequence of adding `or 0` for symmetry
   with the two loose readers.

3. Both parser docstrings record the split, the driven table, and the
   reason the one-way divergence costs nothing.

The gate was NOT made stricter. Making it apply the exact type ground
would abort the restore on `"12.5"`, which today survives and is refused
by the audit — that would invert the declared one-way divergence, not
preserve it.

## Verification

- 596 tests in the two touched units, all green.
- Full release gate ON THE ISLAND: `[OK] Release-ready (v3.25.5, 4417
  tests)`, exit 0. `claim_ledger check` exit 0, no open claims.
- `coding_archetype` and `ta_archetype` `passed=true` on all three
  files, `tool_availability` clean.
- Instrument control: `known_good.py` exit 0, `known_bad.py` exit 1.
- Three blinding mutations, each restored byte-identical:

  | mutation | tests that went red |
  |---|---|
  | revert the truthiness shortcut | 5 |
  | give the restore gate an `or 0` | 2 |
  | drop one attribute from the restore fixture | 5 |

  The third matters most: it proves the gate test cannot pass on
  fixture rot wearing the costume of a refusal.

## Two defects this work produced and the harness caught

1. The first source-level pin read `inspect.getsource`, which includes
   the docstring — and the docstring deliberately QUOTES the retired
   spelling, so the pin tripped on its own documentation. The stripper
   that fixes it cannot use `func.__doc__`: Python 3.13 began dedenting
   docstrings at compile time, so `__doc__` is no longer a substring of
   the source and the obvious `.replace` removes nothing SILENTLY. The
   docstring is located with `ast` instead. A positive control asserts
   both halves.

2. The first rebuild of `CITATION_ANCHORS` keyed the table by anchor
   TEXT. Six rows share `self._main_lots.append({`, so all six
   collapsed onto one number — and
   `test_every_citation_points_at_the_line_it_claims` stayed GREEN,
   because each of those lines really does hold that text. Only
   `test_every_cited_number_has_an_anchor` caught it. The table is
   keyed by ROW POSITION now. Two range citations `:NNNN-NNNN` were
   missed on the same pass, because the tail number follows a dash and
   not a colon; the checker reads both ends and caught those too.

## Recorded, not acted on

- The restore gate's abort message names the bad value but not the lot
  INDEX (`could not convert string to float: ''`). Adding the index
  would help the operator find it in `bot_state.json`. Left alone: it
  is a live restore path and this unit is one thing.
- `_main_lots` assignment happens ~127 lines BEFORE the gate that
  rejects it, so the aborted object carries the corrupt book. Nothing
  reads it — the container refuses to register — but validating at the
  assignment would shorten the half-applied window.
- Both items unreachable today by the same measurement as above.

## Not promoted

The island is green and shows `0 in-scope file(s) STALE`. Promotion was
not run: the deliverable was scoped to an island.
