# C09 — record of a pin replacement, written before the edit

Required by M7 of the remediation methodology:

> **Never modify a test to make it pass.** When a green pin encodes the
> defect, record in writing that the pin encodes the defect, replace it
> with one encoding the requirement, and get operator acknowledgement
> *first*. The rule is absolute; the escape hatch is
> replacement-with-consent, not relaxation.

This document is the "in writing" half. Operator acknowledgement was
recorded 2026-08-07: **approve replacement**.

## The pin being replaced

`tests/test_bot_swarm_list.py:247` — `test_wire_canvas_ignores_unknown_bot`

```python
def test_wire_canvas_ignores_unknown_bot(self):
    ...
    lst.set_bots([{"bot_id": "a", "symbol": "A/USD"}])
    canvas = LaneWireCanvas(lst)
    # Bot "z" not in list — wire silently skipped
    canvas.set_wires([
        {"id": "w1", "source_id": "a", "target_id": "z"}])
    assert "w1" not in canvas._lane_assignments or \
        canvas._lane_assignments.get("w1") is None
```

## Why it encodes the defect

The finding (SWARM-A3) is that a wire which cannot be drawn is dropped
with nothing reported. This test does not merely tolerate that — its
**name** ("ignores"), its **comment** ("wire silently skipped") and its
**assertion** all state that the silent drop is the correct outcome.

A pin that names the defect as the requirement will stay green through
any fix that makes the behaviour honest, and will go red only if
someone repairs it. That is the wrong way round.

Verified against current source before writing this (R68 / M1):

- `src/gui/bot_swarm_list.py:284-286` — `lane = self._lane_assignments.get(_wid)`
  then `if lane is None: continue`.
- `src/gui/bot_swarm_list.py:289-290` — `if ra < 0 or rb < 0: continue`.
  **This** is the branch the unknown-bot case actually takes; the
  methodology text cites only the lane branch. Both are silent, and the
  replacement pin covers the reachable one.
- `src/gui/bot_swarm_list.py:207` — `row_of_bot` is
  `self._bot_ids.index(bot_id)`, a linear scan, called twice per wire on
  every paint.

## What replaces it

`test_wire_canvas_reports_unknown_bot`, asserting **strictly more** than
the old pin:

1. The wire still receives **no lane assignment** — the real invariant
   the old test was protecting, preserved verbatim.
2. The skip is **counted**, and the counter is readable.
3. The counter increments by **exactly 1** for one undrawable wire, so a
   fix that reports every wire as skipped cannot pass either.

The assertion is not relaxed in any direction. The old inequality
survives inside the new test; only the "and nothing is reported" silence
is withdrawn.

## What is deliberately NOT touched

`tests/test_bot_swarm_list.py:67` — `test_returns_none_when_all_lanes_full`.
Allocator exhaustion is a separate, legitimate invariant: when every
lane is genuinely occupied, returning `None` is correct behaviour and
not a defect. It stays green and unmodified.

## Failing-first (M4)

The replacement pin is written and observed **RED against the
unmodified baseline**, with the failure text recorded, before any edit
to `bot_swarm_list.py`. A pin never observed failing has not been
verified.

Recorded failure text appears in
[2026-08-07_C09_lane_canvas.md](2026-08-07_C09_lane_canvas.md).
