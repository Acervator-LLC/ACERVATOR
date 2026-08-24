"""The fold-hold diagnostic must name the condition that actually failed.

THE DEFECT
`is_bearish` requires BOTH a direction in (BEARISH, NEUTRAL) AND
`eff_confidence >= 0.25`. The hold message printed only the direction:

    message=f"HOLD FOLD: {n} tranche(s) (${usd}) queued but "
            f"TA={eff_direction.name} — waiting for BEARISH"

So when the direction WAS bearish and only the confidence floor blocked
the fold, it rendered:

    HOLD FOLD: 178 tranche(s) ($10.1001) queued but TA=BEARISH
    — waiting for BEARISH

Waiting for the condition it reports as already met. Measured 1,377
times in a 27-minute window across the live fleet, alongside
`TA-not-bearish(dir=BEARISH)` in the blocker list. This is why the
confidence floor was never suspected: the log actively pointed away from
it.

Same family as C51 (fabricated TA) and NF-5 (inverted Ammo) —
confidently wrong rather than silent.

SCOPE
Diagnostic only. `_TA_CONFIDENCE_FLOOR` is the same 0.25 the code always
enforced; naming it changes no behaviour, and no gate is moved. Whether
that floor belongs where it is remains an open strategy question for the
operator and is deliberately untouched.

2026-08-24, ISSUE #102. Half of that question is now answered, and the
answer was that the floor was not being enforced at all on one arm. The
BB-priority arm added 0.30 to `eff_confidence` before comparing it
against 0.25, so on that arm the conjunct read `conf >= -0.05` and
refused nothing. The gate site therefore reads `_eff_conf_floor` now:
`_TA_CONFIDENCE_FLOOR` normally, `_BB_PRIORITY_CONFIDENCE_FLOOR` on the
arm. The three source-level pins in `TestTheFloorIsNamed` were RESTATED
for the new name rather than deleted, and two were added -- one that
both floors can refuse, one that no addition reaches the measurement.

These tests exercise the message-construction logic against the real
constant rather than driving `tick()`, which needs a live ticker, a
populated TA engine and an exchange. What they pin is that no input
combination can produce a self-contradicting line.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import (  # noqa: E402
    _BB_PRIORITY_CONFIDENCE_FLOOR, _TA_CONFIDENCE_FLOOR)
from src.trading.ta_engine import SignalDirection  # noqa: E402

SRC = (REPO_ROOT / "src" / "trading" / "scrumming_bot.py").read_text(
    encoding="utf-8")


def _gate_source() -> str:
    """The ScrummingBot.tick() body.

    Selected as the LARGEST function named `tick`: several classes in
    this module define one, and ast.walk order does not favour the right
    one. Picking by span is unambiguous -- the live tick is ~4,000 lines.
    """
    # tick() is `async def`, so AsyncFunctionDef -- filtering on
    # FunctionDef alone finds nothing and max() raises on the empty list.
    ticks = [n for n in ast.walk(ast.parse(SRC))
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == "tick"]
    assert ticks, "no tick() found -- the extractor is broken, not the code"
    biggest = max(ticks, key=lambda n: (n.end_lineno or 0) - n.lineno)
    return ast.get_source_segment(SRC, biggest) or ""


def _hold_reason(direction, confidence: float) -> str:
    """Reproduce the message's reason clause exactly as tick() builds it."""
    dir_ok = direction in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
    if not dir_ok:
        return f"TA={direction.name} is not BEARISH or NEUTRAL"
    if confidence < _TA_CONFIDENCE_FLOOR:
        return (f"TA={direction.name} but confidence {confidence:.2f} < "
                f"{_TA_CONFIDENCE_FLOOR:.2f} floor")
    return (f"TA={direction.name}, confidence {confidence:.2f} — blocked "
            f"by an override, not by direction or confidence")


class TestTheFloorIsNamed:
    def test_the_constant_exists_and_is_unchanged(self):
        """POSITIVE CONTROL and a behaviour lock in one. If naming the
        literal had altered its value, every gate on the platform would
        shift; 0.25 is what the code has always enforced."""
        assert _TA_CONFIDENCE_FLOOR == 0.25

    def test_the_bare_literal_is_gone_from_the_gate(self):
        """The point of naming it is that it becomes greppable. A stray
        inlined 0.25 would drift away from the constant silently.

        RESTATED 2026-08-24, issue #102. The gate used to read
        ``eff_confidence >= _TA_CONFIDENCE_FLOOR`` at both sites. It now
        reads ``eff_confidence >= _eff_conf_floor``, a local that IS
        ``_TA_CONFIDENCE_FLOOR`` on every tick except the BB-priority
        arm, where it is ``_BB_PRIORITY_CONFIDENCE_FLOOR``. What this
        test pins is unchanged -- no bare literal reaches the gate -- so
        it pins the new name and, below, that both constants are still
        the only things the local can be.
        """
        seg = _gate_source()
        assert "eff_confidence >= 0.25" not in seg
        assert "eff_confidence >= _eff_conf_floor" in seg
        assert ("_eff_conf_floor = (_BB_PRIORITY_CONFIDENCE_FLOOR "
                "if _bb_priority_arm" in seg)
        assert "else _TA_CONFIDENCE_FLOOR)" in seg

    def test_both_directions_use_it(self):
        """The floor gates SCRUM as well as FOLD. Fixing one side only
        would leave the other lying."""
        seg = _gate_source()
        assert seg.count("eff_confidence >= _eff_conf_floor") == 2

    def test_the_priority_floor_can_still_refuse(self):
        """ISSUE #102, and the reason the local exists at all.

        The BB-priority arm used to ADD 0.30 to the measurement and then
        compare the sum against 0.25. On a quantity whose indicator
        output is bounded [0, 1] that is ``conf >= -0.05``: the conjunct
        had no false case. A floor that cannot refuse is not a floor.

        Both floors must therefore be strictly positive, and the
        priority floor must be the LOWER of the two -- it is a favour,
        not a promotion.
        """
        assert _TA_CONFIDENCE_FLOOR > 0.0
        assert _BB_PRIORITY_CONFIDENCE_FLOOR > 0.0
        assert _BB_PRIORITY_CONFIDENCE_FLOOR < _TA_CONFIDENCE_FLOOR
        # A reading of exactly 0.0 -- the case the issue names -- is
        # refused on both arms.
        assert not 0.0 >= _BB_PRIORITY_CONFIDENCE_FLOOR
        assert not 0.0 >= _TA_CONFIDENCE_FLOOR

    def test_the_measurement_is_not_edited_before_the_gate(self):
        """The favour lands on the threshold, never on the reading.

        POSITIVE CONTROL for the repair. If a later change reinstates an
        addition onto ``eff_confidence`` inside the priority block, the
        gate stops judging what the indicators measured and the nine
        diagnostics below it start printing a confidence no indicator
        produced. That is the half of the defect the floor value alone
        does not cover.
        """
        seg = _gate_source()
        assert "eff_confidence + _BB_PRIORITY_SKEW" not in seg
        assert "eff_confidence = max(" not in seg


class TestTheHoldReasonIsNeverSelfContradicting:
    @pytest.mark.parametrize("direction", list(SignalDirection))
    @pytest.mark.parametrize("confidence", [0.0, 0.10, 0.2499, 0.25, 0.9])
    def test_it_never_says_waiting_for_what_it_reports(self, direction,
                                                       confidence):
        """THE defect, stated as an invariant over every input: the line
        must not report a direction as BEARISH while claiming to wait
        for BEARISH."""
        reason = _hold_reason(direction, confidence)
        contradiction = ("TA=BEARISH" in reason
                         and "waiting for BEARISH" in reason)
        assert not contradiction, f"self-contradicting line: {reason!r}"

    def test_a_wrong_direction_names_the_direction(self):
        r = _hold_reason(SignalDirection.BULLISH, 0.9)
        assert "BULLISH" in r and "not BEARISH" in r

    def test_a_low_confidence_names_the_confidence(self):
        """The case that produced 1,377 misleading lines: direction is
        right, confidence is the blocker, and the old message said
        nothing about it."""
        r = _hold_reason(SignalDirection.BEARISH, 0.18)
        assert "0.18" in r
        assert "0.25" in r
        assert "confidence" in r
        assert "waiting for BEARISH" not in r

    def test_the_boundary_is_reported_correctly(self):
        """Exactly at the floor is NOT blocked -- the gate is >=."""
        at_floor = _hold_reason(SignalDirection.BEARISH,
                                _TA_CONFIDENCE_FLOOR)
        below = _hold_reason(SignalDirection.BEARISH,
                             _TA_CONFIDENCE_FLOOR - 0.01)
        # Match on "floor", not "confidence": the override branch says
        # "not by direction or confidence" and would match either way.
        assert "floor" not in at_floor, at_floor
        assert "floor" in below, below

    def test_an_unexplained_block_says_so(self):
        """NEGATIVE CONTROL. When neither conjunct explains the hold, the
        message must admit that rather than blame whichever it checked
        last -- that is how the original defect was born."""
        r = _hold_reason(SignalDirection.BEARISH, 0.9)
        assert "override" in r


class TestTheBlockerLabelsAgree:
    def test_fold_label_no_longer_contradicts_itself(self):
        seg = _gate_source()
        assert "TA-conf-below-floor" in seg

    def test_both_sides_were_fixed(self):
        """The scrum label had the identical defect."""
        seg = _gate_source()
        assert seg.count("TA-conf-below-floor") == 2

    def test_the_plain_direction_labels_survive(self):
        """NEGATIVE CONTROL: when the direction really is wrong, the
        label must still say so plainly rather than blaming confidence."""
        seg = _gate_source()
        assert "TA-not-bearish(dir=" in seg
        assert "TA-not-bullish(dir=" in seg
