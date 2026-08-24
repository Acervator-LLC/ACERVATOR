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
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import (  # noqa: E402
    _BB_PRIORITY_CONFIDENCE_FLOOR, _TA_CONFIDENCE_FLOOR,
    _skewed_confidence_floor)
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
        reads ``eff_confidence >= _eff_conf_floor``. What this test pins
        is unchanged -- no bare literal reaches the gate -- so it pins
        the new name and, below, what the local is allowed to be.

        RESTATED AGAIN 2026-08-24, issue #104. The local was a two-way
        choice between two module constants while the BB-priority skew
        was the only favour on the threshold. Two more favours joined it,
        so the local is now DERIVED: `_skewed_confidence_floor` divides
        the standing floor by one plus the sum of the three. Pinning the
        old two-way expression would now pin the shape of a repair that
        has been superseded, so this pins the derivation instead -- the
        floor still comes from a named helper and never from a literal.
        """
        seg = _gate_source()
        assert "eff_confidence >= 0.25" not in seg
        assert "eff_confidence >= _eff_conf_floor" in seg
        assert "_eff_conf_floor = _skewed_confidence_floor(_ta_conf_skew)" in seg
        assert "_ta_conf_skew = position_boost + bb_confidence_boost" in seg
        assert "_ta_conf_skew += _BB_PRIORITY_SKEW" in seg

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
        # ISSUE #104. The same rule over the whole method, not only the
        # priority block: NOTHING adds to the measurement any more.
        # Two more favours were spent here -- `position_boost` and
        # `bb_confidence_boost` -- and the sweep measured what they cost:
        # 123 trades fired on a confidence the indicators had not
        # produced, and 316 readings carried a NEGATIVE confidence into
        # nine diagnostics.
        #
        # READ AS CODE, NOT AS TEXT. A substring search for
        # `eff_confidence +=` also matches the prose that RECORDS what
        # those lines used to read, so it would go red on the repair's
        # own explanation and green on a comment that quietly said
        # `eff_confidence  +=`. The AST is the exact instrument.
        augmented = [n for n in ast.walk(ast.parse(seg))
                     if isinstance(n, ast.AugAssign)
                     and isinstance(n.target, ast.Name)
                     and n.target.id == "eff_confidence"]
        assert augmented == [], (
            "something adds to `eff_confidence` again at line(s) "
            f"{[n.lineno for n in augmented]} of the method; the favour "
            "belongs on the threshold, not on the measurement")

    def test_POSITIVE_CONTROL_the_augassign_scanner_sees_one(self):
        """The scanner above must not report empty for every input."""
        sample = "\n".join((
            "def f():", "    eff_confidence += position_boost", ""))
        found = [n for n in ast.walk(ast.parse(sample))
                 if isinstance(n, ast.AugAssign)
                 and isinstance(n.target, ast.Name)
                 and n.target.id == "eff_confidence"]
        assert len(found) == 1

    def test_the_skewed_floor_can_refuse_at_every_reachable_skew(self):
        """ISSUE #104. The property the whole repair exists for.

        A favour must never make the comparison unfailable. The largest
        favour this module can build is the three summed at their
        ceilings -- +0.30 BB-priority, +0.40 position by enumeration of
        its own terms, +0.60 BB-confidence by derivation from its two
        component bounds. Even there the floor stays strictly positive,
        so a reading of exactly 0.0 is refused. That is what dividing
        buys and subtracting does not.
        """
        for skew in (0.0, 0.30, 0.40, 0.60, 1.30):
            floor = _skewed_confidence_floor(skew)
            assert floor > 0.0, skew
            assert not 0.0 >= floor, skew
        # And it is a RELAXATION, monotonically, never a promotion.
        assert _skewed_confidence_floor(0.0) == _TA_CONFIDENCE_FLOOR
        assert (_skewed_confidence_floor(0.30)
                == _BB_PRIORITY_CONFIDENCE_FLOOR)
        rungs = [_skewed_confidence_floor(s)
                 for s in (-0.29, 0.0, 0.30, 0.40, 0.60, 1.30)]
        assert rungs == sorted(rungs, reverse=True)

    def test_a_negative_skew_tightens_rather_than_relaxes(self):
        """`position_boost` reaches -0.29, and that has to mean something.

        Under the addition a negative favour SUBTRACTED from the
        measurement, so evidence against made the reading look weaker.
        Under the division it RAISES the bar instead. The direction is
        preserved; only the arithmetic changed. Eleven of the 134
        decision flips the sweep measured are exactly this case, and
        every one of them carries a negative `position_boost`.
        """
        assert _skewed_confidence_floor(-0.29) > _TA_CONFIDENCE_FLOOR
        assert _skewed_confidence_floor(-0.05) > _TA_CONFIDENCE_FLOOR

    def test_a_total_penalty_refuses_everything(self):
        """NEGATIVE CONTROL for the guard branch nothing live reaches.

        At a skew of -1 the division is undefined. The continuous limit
        is a floor no reading can clear, and that is what is returned --
        not a friendlier fallback that would REWARD total evidence
        against.
        """
        assert _skewed_confidence_floor(-1.0) == math.inf
        assert _skewed_confidence_floor(-2.0) == math.inf
        assert not 1.0 >= _skewed_confidence_floor(-1.0)


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
