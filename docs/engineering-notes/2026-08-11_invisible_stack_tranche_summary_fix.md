# Invisible Stack tranche could never fire

Date: 2026-08-11
File: `src/trading/scrumming_bot.py`
Status: FIXED and promoted to live. Gate green.

## The defect

`_reconcile_stack_tranches_invisible` fired a pending Stack tranche with
`summary=None`. `_execute_sell` reads `summary.consensus_confidence` in
the "SELL signal:" emit, BEFORE it calls `guarded_place_order`. That
raised `AttributeError` inside the method's own `try`, so its
`except Exception` caught it, emitted
`SELL FAILED: 'NoneType' object has no attribute 'consensus_confidence'`,
and returned `None`.

The order was never placed. The reconciler's `if fill is not None:` was
never true, so `status` stayed `"pending"` and the bot re-attempted every
tick forever, spending one `get_open_orders` API call and one failure log
line per tick, per tranche.

## Root cause, one level deeper than reported

The report named the three `summary` dereferences. Two of them are real
crash sites. The third, `MemorisedTrade(voting_summary=summary)`, is NOT
a defect: `MemorisedTrade.voting_summary` is typed
`Optional[VotingSummary] = None`, so `None` is contract-legal there.

The actual root cause is upstream. The reconciler justified `summary=None`
with the comment:

> summary was recorded at stack-open time

That was false. `_open_stack_from_scrum` ACCEPTED a `summary` parameter
and never stored it — the tranche `entry` dict carried `index`, `price`,
`size`, `status`, `opened_ts`, `opened_at_scrum_price`, `order_id` and
`visible`, and nothing about the vote. Nothing was recorded, so there was
nothing to replay.

## The fix

Caller-side, in three parts. `_execute_sell` is NOT touched, so no gate
semantics change.

1. `StackTrancheSummary` dataclass, beside `MemorisedTrade`. Carries only
   the two attributes `_execute_sell` reads. Mirrors the minimal summary
   `manual_fire_tranche` already builds for `_execute_buy`.
2. `_open_stack_from_scrum` now records the opening vote on every tranche
   as `open_confidence` / `open_direction`. This makes the reconciler's
   comment true instead of aspirational.
3. The reconciler replays that recorded vote instead of passing `None`.
   Tranches opened before this change lack the key, so it falls back to
   `0.0` rather than assuming it.

`_execute_sell`'s signature is `summary: VotingSummary`, not `Optional`.
The caller was violating the contract, so the caller was fixed. Widening
`_execute_sell` to tolerate `None` would have relaxed a live-money path
to accommodate one broken caller.

## Why the existing tests missed it

`tests/test_stack_mode_execution.py` was regex-on-source shape checks.
They asserted the branch text was present and correctly wired. They never
executed `_execute_sell`, so they were blind to a runtime failure in the
fire path.

Nine behavioural tests were added that drive the REAL `_execute_sell`
through the reconciler, plus two positive controls:

- `test_stub_places_order_with_a_real_summary` — proves the stub's gates
  are permissive, so a later "no order placed" is caused by the summary
  and not by a gate refusing the stub.
- `test_stub_detects_a_missing_attribute` — proves the stub NOTICES a
  blinded summary. A stub that passes either way measures nothing.

## Verification

Reproduction before the fix: 7 failed, 16 passed, with
`'NoneType' object has no attribute 'consensus_confidence'` logged from
`_execute_sell`'s exception handler.

Adversarial mutation pass — each mechanism blinded, file restored and
confirmed byte-identical by sha256:

| mutation | result |
|---|---|
| M1 restore `summary=None` | CAUGHT |
| M2 stop recording the opening vote | CAUGHT |
| M3 fabricate a placeholder confidence | CAUGHT |

After the fix:

- `tests/test_stack_mode_execution.py` — 23 passed
- `check_release_readiness` on live — `[OK] Release-ready (v3.25.5, 3030 tests)`, exit 0
- `coding_archetype` on all three touched files — `passed=True`, exit 0,
  all ten tools reporting `ok`
- `ta_archetype` — `passed=True`

## Two things that went wrong during the work

**Live moved mid-task.** `src/trading/scrumming_bot.py` grew from 13180
to 13262 lines at 21:59 while the first island was open. `island status`
reported the island STALE and promotion would have refused. The work was
rebased onto a fresh island (`STACK_SUMMARY_R2`) rather than overridden.
The stale island `STACK_SUMMARY` is litter and can be removed.

This also explains an earlier wrong diagnosis: a citation remap produced
a degraded line map, which looked like a difflib flaw. It was not — the
live input had changed underneath the second run.

**Line-number citations rotted.** The insertion shifted every line below
it, so `tests/test_extractor_tranche_containment.py` failed exactly as
designed. The citations were re-pointed mechanically, never by hand, and
the remapper verifies all 34 anchors against the new file before it
writes anything.

difflib was the wrong tool for that map: this file has many duplicate
lines (`self._main_lots.append({` occurs eight times), and
`SequenceMatcher` returned a valid but wrong alignment. The anchor table
is the better oracle because each anchor carries the exact text its line
must hold. Because the change is a pure insertion, the shift must be
non-negative and non-decreasing; enforcing that removed the ambiguity and
produced exactly two distinct shifts, `+18` and `+49`, matching the two
insertion points.

The citations live in the WHOLE body of the five documented methods, not
just their docstrings — the checker collects them with
`inspect.getsource`, so a `:NNNN` in a body comment counts too.

## Reachability

`stack_mode` is False on all 37 bots in the live `bot_state.json` and no
bot holds Stack tranches, so this was unreachable in production. It is
fixed before `stack_mode` is ever enabled.

## Not done

No version bump and no CHANGELOG entry. The operator asked for the fix
only, and the queue discipline is one thing at a time.
