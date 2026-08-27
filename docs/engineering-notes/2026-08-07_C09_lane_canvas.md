# C09 — Lane canvas: exhaustion visibility + endpoint resolution

Cascade 19 of the remediation sequence, shipped v3.24.52, tier
gui-truth. Findings SWARM-A3 and SWARM-4.14.

Pin replacement recorded before the edit in
[2026-08-07_C09_pin_replacement_record.md](2026-08-07_C09_pin_replacement_record.md),
operator acknowledgement 2026-08-07.

## Cold read (R68 / M1)

Every cited location re-verified against current source before design.
One correction to the methodology text:

| Cited | Actual |
|---|---|
| `:284-286` `if lane is None: continue` | Confirmed. |
| `row_of_bot` linear scan at `:287-288` | Confirmed — `self._bot_ids.index(bot_id)` at `:207`. |
| — | **`:289-290` `if ra < 0 or rb < 0: continue` is a SECOND silent skip.** The methodology cites only the lane branch. |

The second branch matters because it is the one the unknown-bot case
was expected to take — and, as the failing-first run showed, does not.

## Failing-first (M4) — recorded failure text

Both pins written and observed RED against the unmodified baseline:

```
E  AttributeError: 'LaneWireCanvas' object has no attribute
   'undrawable_wire_count'
tests/test_bot_swarm_list.py:284

E  AssertionError: paint called row_of_bot 16 times; endpoints must
   come from a mapping built once per paint
E  assert 16 == 0
tests/test_bot_swarm_list.py:324
```

The second is a measurement, not an assertion of style: **16 lookups for
8 wires over 30 rows**, two per wire, every repaint.

## What shipped

1. `_undrawable_wires` reset per paint (not per wire — carrying it
   across frames would grow without bound at ~2.5 repaints/sec).
2. `undrawable_wire_count()` and `undrawable_wires()` accessors.
3. `BotListView.row_index_map()` — built once per paint. `row_of_bot`
   remains for single lookups, where a scan beats allocating a dict.
4. A log line emitted **on change**, naming each wire and its reason.

## The defect my own first implementation introduced

The reason label was wrong, and the pin caught it rather than review.

`set_wires` filters wires with unlisted endpoints *before* handing
triples to the allocator. Those wires therefore never receive a lane, so
at paint time they arrive at the `lane is None` branch — indistinguish-
able from genuine allocator exhaustion. My first version reported all of
them as `no-lane`.

That is an actively misleading report: it points the operator at lane
capacity when the row set is what has gone stale. Two different problems
with two different fixes. `set_wires` now records which wires it
dropped, and the paint attributes `unlisted-bot` accordingly.

The test that caught it originally asserted
`reasons == {"no-lane"} or reasons == {"unlisted-bot"}` — weak enough to
pass either way. It now asserts the exact pair, so the distinction
cannot silently regress.

## Exit gate (measurement)

| Requirement | Result |
|---|---|
| Unlisted-bot wire leaves `_lane_assignments` without an entry | ✅ asserted, unchanged from the old pin |
| ...AND increments the reported skip counter by exactly 1 | ✅ asserted, including that a drawable wire alongside it does **not** count |
| Paint performs O(1) endpoint lookups | ✅ `row_of_bot` call count during paint: **16 → 0** |
| `test_returns_none_when_all_lanes_full` still green | ✅ untouched |

Suite **1767 passing, zero failures** — the first fully green run in this
series, the last two having been the proselint defect fixed in 3.24.51.

## Not done here

The counter is surfaced to the log, not to the Bot Swarm tab's chrome.
A visible on-screen badge needs a home in `bot_visualizer.py` and a
decision about where it lives; that is UI design, not gui-truth
remediation, and is left for the operator to place.
