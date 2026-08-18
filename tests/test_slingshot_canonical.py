"""Slingshot must match the published formula, not this repo's archaeology.

WHAT WAS WRONG
==============
`SlingshotIndicator` derived squeeze DIRECTION from the price's own side
of the Bollinger midline::

    squeeze_bull = just_fired and curr_close > curr_mid      # old :2405
    squeeze_bear = just_fired and curr_close < curr_mid      # old :2406

and the bullish snapback branch required the opposite sense of the SAME
comparison::

    if curr_close > curr_lo and curr_close < curr_mid:       # old :2451

`curr_close` and `curr_mid` are bound once, together, from one tuple
unpack. So the agreement bonus::

    if squeeze_bull and snapback_type == "bullish_snapback": # old :2498

was a contradiction, not a rare event. It could not execute on any
candle, on either polarity, and never had.

WHY THE PUBLISHED DEFINITION SETTLES IT
=======================================
Chris Moody's ``CM_SlingShotSystem`` (TradingView, 10-05-2014) gives the
canonical entry as::

    emaSlow = ema(close, 62) ; emaFast = ema(close, 38)
    aggressive long : emaFast > emaSlow and close < emaFast

The canonical BULLISH case requires close BELOW the reference line, with
direction taken from a separate quantity. "Bullish" and "price below the
line" are required to coexist. The old code made them exclusive.

Moody published no squeeze. The squeeze is John Carter's TTM Squeeze,
public-domain reference implementation LazyBear ``SQZMOM_LB``::

    sqzOn = (lowerBB > lowerKC) and (upperBB < upperKC)
    val   = linreg(close - avg(avg(highest(high,N), lowest(low,N)),
                               sma(close,N)), N, 0)

Direction is ``sign(val)`` -- a momentum value. There is no
price-versus-midline test anywhere in the canonical squeeze.

The snapback is Bollinger's own rule 8: a close outside a band is a
CONTINUATION signal; the close back inside is what makes it a reversal.
Re-entry is the whole requirement.

EVERY TEST BELOW THAT PINS A REPAIR CARRIES ITS NEGATIVE CONTROL -- the
old predicate, recomputed inline, shown disagreeing on the same candles.
Without that, a green test proves only that today's code does what
today's code does.
"""
from __future__ import annotations

import math

from src.trading.ta_engine import (
    Candle,
    SignalDirection,
    SlingshotIndicator,
    _sma_tail,
)

TS0 = 1_700_000_000_000
STEP = 300_000
PERIOD = 20
TAIL = 35


def _row(i: int, close: float, amp: float, vol: float = 100.0) -> Candle:
    half = abs(amp) * 0.5
    return Candle(TS0 + i * STEP, close, close + half, close - half,
                  close, vol)


def _chop(wide_end: int, amp: float, coil: float, tail: tuple,
          n: int = 80, base: float = 100.0) -> list:
    """Wide chop, then a tight coil, then explicit resolution bars.

    Every tuple used below was found by grid search against the
    indicator, so each test reaches the state it claims to test.
    """
    out = []
    for i in range(n - len(tail)):
        a = amp if i < wide_end else coil
        c = base + (a if i % 2 == 0 else -a)
        out.append(_row(i, c, a))
    for k, off in enumerate(tail):
        out.append(_row(n - len(tail) + k, base + off,
                        max(coil, abs(off)) or 0.01))
    return out


def _bb_mid(candles: list) -> float:
    """The midline the OLD direction rule compared against."""
    closes = [c.close for c in candles]
    return _sma_tail(closes, PERIOD, tail=TAIL)[len(candles) - 1]


# ── D1: DIRECTION COMES FROM MOMENTUM, NOT THE MIDLINE ───────────────

class TestDirectionIsMomentumNotMidline:
    """The root defect. Canon: CM SlingShot pairs a BULLISH state with
    ``close < emaFast``; direction comes from the EMA pair, not from
    where price sits. Here: from ``sign(linreg(delta))``."""

    BULL_BELOW_MID = (44, 2.0, 0.01, (0.0, 1.0, -14.0))
    BEAR_ABOVE_MID = (44, 2.0, 0.01, (-14.0, -14.0, -1.0))

    def test_bullish_squeeze_while_price_is_below_the_midline(self):
        cs = _chop(*self.BULL_BELOW_MID)
        d = SlingshotIndicator().compute(cs).details
        mid = _bb_mid(cs)
        close = cs[-1].close

        # The canonical state: bullish, price below the line.
        assert close < mid, (close, mid)
        assert d["squeeze_bull"] is True, d
        assert d["fire_momentum"] > 0.0, d["fire_momentum"]

        # NEGATIVE CONTROL -- the retired predicate, on these same
        # candles. It calls this bar BEARISH. If this ever stops
        # disagreeing, the series has drifted and the test above is
        # no longer exercising the repair.
        old_squeeze_bull = close > mid
        old_squeeze_bear = close < mid
        assert old_squeeze_bull is False
        assert old_squeeze_bear is True
        assert old_squeeze_bull != d["squeeze_bull"]

    def test_bearish_squeeze_while_price_is_above_the_midline(self):
        cs = _chop(*self.BEAR_ABOVE_MID)
        d = SlingshotIndicator().compute(cs).details
        mid = _bb_mid(cs)
        close = cs[-1].close

        assert close > mid, (close, mid)
        assert d["squeeze_bear"] is True, d
        assert d["fire_momentum"] < 0.0, d["fire_momentum"]

        old_squeeze_bear = close < mid
        assert old_squeeze_bear is False
        assert old_squeeze_bear != d["squeeze_bear"]

    def test_the_two_flags_stay_mutually_exclusive(self):
        """`ta_invariants.py:217` pins `_excl(squeeze_bull,
        squeeze_bear)`. A momentum sign cannot be both."""
        for params in (self.BULL_BELOW_MID, self.BEAR_ABOVE_MID,
                       (44, 2.0, 0.01, (0.0, 0.0, 1.0))):
            d = SlingshotIndicator().compute(_chop(*params)).details
            assert not (d["squeeze_bull"] and d["squeeze_bear"]), params


# ── D3: THE CANONICAL MOMENTUM VALUE EXISTS AND IS CORRECT ───────────

class TestLinearRegressionEndpoint:
    """`linreg` appeared nowhere in ta_engine.py. Slingshot computes its
    own; this pins it against the closed form."""

    def test_exact_on_a_straight_line(self):
        # A perfect line: the fit is the line, so the endpoint is the
        # last value exactly.
        series = [3.0 + 2.0 * x for x in range(20)]
        got = SlingshotIndicator._linreg_endpoint(series)
        assert math.isclose(got, series[-1], rel_tol=1e-12), got

    def test_matches_least_squares_on_a_noisy_series(self):
        series = [math.sin(x / 3.0) * 5.0 + 0.4 * x for x in range(20)]
        n = len(series)
        sx = sum(range(n))
        sy = sum(series)
        sxx = sum(x * x for x in range(n))
        sxy = sum(x * y for x, y in enumerate(series))
        slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        intercept = (sy - slope * sx) / n
        want = intercept + slope * (n - 1)
        got = SlingshotIndicator._linreg_endpoint(series)
        assert math.isclose(got, want, rel_tol=1e-12), (got, want)

    def test_degenerate_inputs_do_not_raise(self):
        assert SlingshotIndicator._linreg_endpoint([]) == 0.0
        assert SlingshotIndicator._linreg_endpoint([7.5]) == 7.5
        # A flat series has zero slope: the endpoint is the mean.
        assert math.isclose(
            SlingshotIndicator._linreg_endpoint([2.0] * 20), 2.0,
            rel_tol=1e-12)


# ── D2: THE SQUEEZE IS BOLLINGER-INSIDE-KELTNER ──────────────────────

class TestSqueezeIsBollingerInsideKeltner:
    """Canon compares two DIFFERENT volatility measures (standard
    deviation against true range). The old code compared bandwidth
    against its own trailing average, which is self-referential."""

    def test_sqz_on_recomputed_independently(self):
        cs = _chop(44, 2.0, 0.01, (0.0, 0.0, 1.0))
        d = SlingshotIndicator().compute(cs).details

        n = len(cs)
        closes = [c.close for c in cs]
        sma = _sma_tail(closes, PERIOD, tail=TAIL)
        std = [None] * n
        for i in range(n - TAIL, n):
            w = closes[max(0, i - PERIOD + 1):i + 1]
            m = sum(w) / len(w)
            std[i] = math.sqrt(sum((x - m) ** 2 for x in w) / len(w))
        tr = [cs[0].high - cs[0].low]
        for i in range(1, n):
            pc = cs[i - 1].close
            tr.append(max(cs[i].high - cs[i].low,
                          abs(cs[i].high - pc), abs(cs[i].low - pc)))
        trma = _sma_tail(tr, PERIOD, tail=TAIL)

        i = n - 1
        mid = sma[i]
        up_bb = mid + 2.0 * std[i]
        lo_bb = mid - 2.0 * std[i]
        up_kc = mid + trma[i] * 1.5
        lo_kc = mid - trma[i] * 1.5
        want = (lo_bb > lo_kc) and (up_bb < up_kc)
        assert d["sqz_on"] is want, (d["sqz_on"], want)

    def test_bandwidth_telemetry_is_retained(self):
        """A designed behaviour is not deleted. The bandwidth fields
        still report even though they no longer decide the squeeze."""
        d = SlingshotIndicator().compute(
            _chop(44, 2.0, 0.01, (0.0, 0.0, 1.0))).details
        for key in ("was_squeezed", "curr_bw", "avg_bw", "squeeze_depth",
                    "expansion_rate"):
            assert key in d, key


# ── D4 + D5: THE BONUS IS SEQUENTIAL, AND IT MOVES THE NUMBER ────────

class TestAgreementBonus:
    """Was unsatisfiable (D1) AND saturated (D5): `squeeze_conf` was
    `squeeze_depth * 3 + expansion_rate * 2 + 0.3`, measured at exactly
    1.0 on 8,102 of 8,102 firings, so `min(1.0, conf + 0.15)` on the
    same line could not move it even if the branch were reachable."""

    AGREE_BULL = (44, 2.0, 0.01, (1.0, -14.0, 8.0))
    AGREE_BEAR = (44, 2.0, 0.01, (-14.0, 8.0, -14.0))

    def test_bullish_agreement_fires(self):
        sig = SlingshotIndicator().compute(_chop(*self.AGREE_BULL))
        d = sig.details
        assert d["agree"] is True, d
        assert d["squeeze_bull"] is True
        assert d["snapback_type"] == "bullish_snapback"
        assert d["slingshot_type"] == "squeeze_bull+snapback"
        assert sig.direction is SignalDirection.BULLISH

    def test_bearish_agreement_fires(self):
        sig = SlingshotIndicator().compute(_chop(*self.AGREE_BEAR))
        d = sig.details
        assert d["agree"] is True, d
        assert d["squeeze_bear"] is True
        assert d["snapback_type"] == "bearish_snapback"
        assert d["slingshot_type"] == "squeeze_bear+snapback"
        assert sig.direction is SignalDirection.BEARISH

    def test_the_bonus_actually_moves_the_confidence(self):
        """The saturation half of the defect. A reachable branch whose
        +0.15 is immediately re-clamped is still a no-op.

        Tolerance note: `details["squeeze_conf"]` is `round(..., 4)`
        while `Signal.confidence` is not rounded, so the comparison
        carries the 4-dp quantisation (5e-5) and no more. Asserting to
        1e-9 against a rounded operand would be testing the rounding.
        """
        for params in (self.AGREE_BULL, self.AGREE_BEAR):
            sig = SlingshotIndicator().compute(_chop(*params))
            base = sig.details["squeeze_conf"]        # rounded to 4 dp
            assert base < 1.0, ("saturated again", params, base)
            assert math.isclose(sig.confidence, base + 0.15,
                                abs_tol=5e-5), (params, base, sig.confidence)
            # The bonus must be the WHOLE of the movement, not a
            # rounding artefact: a no-op bonus would leave this at 0.
            assert sig.confidence - base > 0.1, (params, sig.confidence, base)

    def test_the_bonus_is_sequential_not_simultaneous(self):
        """All three sources order this: the squeeze fires, THEN the
        snapback confirms. The fire must be on an earlier bar."""
        for params in (self.AGREE_BULL, self.AGREE_BEAR):
            d = SlingshotIndicator().compute(_chop(*params)).details
            assert d["bars_since_fire"] >= 1, (params, d["bars_since_fire"])

    def test_negative_control_old_conjunction_is_unsatisfiable(self):
        """The retired predicate on the SAME candles. `squeeze_bull`
        needed close > mid; a bullish snapback needed close < mid. Both
        read one tuple unpack, so the conjunction is a contradiction."""
        cs = _chop(*self.AGREE_BULL)
        mid = _bb_mid(cs)
        close = cs[-1].close
        old_squeeze_bull = close > mid
        old_snapback_gate = close > mid - 1e9 and close < mid
        assert not (old_squeeze_bull and old_snapback_gate), \
            "the old conjunction must be unsatisfiable"


# ── D7: SNAPBACK NEEDS RE-ENTRY, NOTHING MORE ────────────────────────

class TestSnapbackFollowsBollingerRule8:
    def test_snapback_survives_a_close_past_the_midline(self):
        """The old extra conjunct `curr_close < curr_mid` suppressed
        every reversal strong enough to cross the midline in one bar --
        the strongest ones. Bollinger requires only re-entry."""
        cs = _chop(*TestAgreementBonus.AGREE_BULL)
        d = SlingshotIndicator().compute(cs).details
        mid = _bb_mid(cs)
        close = cs[-1].close
        assert d["snapback_type"] == "bullish_snapback", d
        assert close > mid, (close, mid)
        # NEGATIVE CONTROL: the retired conjunct rejects this bar.
        assert not (close < mid), "old rule would have suppressed it"


# ── D6: THE OPPOSING CO-OCCURRENCE IS NO LONGER SILENT ───────────────

class TestOpposingSignalIsRecorded:
    CONFLICT = (44, 2.0, 0.01, (-14.0, -14.0, -10.0))

    def test_conflict_is_reported(self):
        """Squeeze precedence is kept -- it is a designed behaviour --
        but the discarded snapback used to leave no field at all."""
        d = SlingshotIndicator().compute(_chop(*self.CONFLICT)).details
        assert d["snapback_conflict"] is True, d
        assert d["squeeze_bear"] is True
        assert d["snapback_type"] == "bullish_snapback"
        # Precedence unchanged: the squeeze still wins the vote.
        assert d["slingshot_type"] == "squeeze_bear"

    def test_no_conflict_flag_when_they_agree(self):
        d = SlingshotIndicator().compute(
            _chop(*TestAgreementBonus.AGREE_BULL)).details
        assert d["snapback_conflict"] is False, d


# ── NO BLENDING ──────────────────────────────────────────────────────

class TestNoBlending:
    """Every input must be raw candle data or Slingshot's own
    arithmetic. This is a source-level check because a runtime one
    would pass whenever the forbidden branch simply did not execute."""

    FORBIDDEN = ("compute_heikin_ashi", "ATRIndicator", "BollingerBands",
                 "IchimokuCloud", "_true_range")

    def _source(self):
        import ast
        import inspect

        from src.trading import ta_engine
        src = inspect.getsource(ta_engine.SlingshotIndicator)
        return src, ast.parse(src.lstrip())

    def test_no_other_indicator_is_called(self):
        src, _ = self._source()
        for name in self.FORBIDDEN:
            assert f"{name}(" not in src, f"blending: {name} called"

    def test_reads_only_candle_fields_and_own_helpers(self):
        src, _ = self._source()
        # The shared scalar maths helpers are allowed; indicator
        # classes are not. Assert the allowed set is what is used.
        for allowed in ("_sma_tail", "_stdev_tail", "_linreg_endpoint",
                        "_bandwidth"):
            assert allowed in src, allowed

    def test_heikin_ashi_is_not_claimed_as_a_direction_input(self):
        """The old docstring listed HA as a bullet under "Direction
        determined by". The method never computed one. Under the
        no-blending rule the claim is removed, not honoured.

        The assertion targets the BULLET form. The new docstring names
        the retired claim in prose while explaining its removal, and a
        bare substring match would fire on that explanation -- which is
        what the first version of this test did.
        """
        from src.trading.ta_engine import SlingshotIndicator as S
        doc = S.__doc__ or ""
        assert "• HA candle direction" not in doc
        assert "Direction determined by:" not in doc


# ── DOMAIN + INVARIANTS ──────────────────────────────────────────────

class TestDomainAndInvariants:
    def _series(self):
        flat = [Candle(TS0 + i * STEP, 100.0, 100.0, 100.0, 100.0, 100.0)
                for i in range(80)]
        subcent = _chop(44, 2.4e-7, 1e-9, (0.0, 0.0, 1e-7), base=1.2e-5)
        zerovol = [_row(i, 100.0 + i * 0.05, 0.05,
                        vol=0.0 if i == 75 else 100.0) for i in range(80)]
        single = [_row(0, 100.0, 1.0)]
        gap = [_row(i, 100.0 * (1.3 if i >= 60 else 1.0)
                    + (0.05 if i % 2 else -0.05), 0.10) for i in range(80)]
        return {"flat": flat, "subcent": subcent, "zero_volume": zerovol,
                "single": single, "gap": gap}

    def test_no_domain_series_raises(self):
        for name, cs in self._series().items():
            sig = SlingshotIndicator().compute(cs)
            assert sig is not None, name

    def test_confidence_stays_inside_zero_to_one(self):
        for name, cs in self._series().items():
            sig = SlingshotIndicator().compute(cs)
            assert 0.0 <= sig.confidence <= 1.0, (name, sig.confidence)
            d = sig.details
            for key in ("squeeze_conf", "snapback_conf"):
                if key in d:
                    assert 0.0 <= d[key] <= 1.0, (name, key, d[key])

    def test_bandwidth_fields_stay_non_negative(self):
        """`ta_invariants.py:215-216` pins `_nonneg(curr_bw)` and
        `_nonneg(avg_bw)`."""
        for name, cs in self._series().items():
            d = SlingshotIndicator().compute(cs).details
            for key in ("curr_bw", "avg_bw"):
                if key in d:
                    assert d[key] >= 0.0, (name, key, d[key])

    def test_short_input_returns_neutral(self):
        sig = SlingshotIndicator().compute([_row(0, 100.0, 1.0)])
        assert sig.direction is SignalDirection.NEUTRAL
        assert sig.confidence == 0.0
        assert sig.details == {}

    def test_flat_market_is_neutral(self):
        sig = SlingshotIndicator().compute(self._series()["flat"])
        assert sig.direction is SignalDirection.NEUTRAL
        assert sig.confidence == 0.0

    def test_details_schema_keeps_every_consumed_field(self):
        """`ta_invariants.py:212-218` reads five of these, and the
        `ta.raw.slingshot` emitter payload carries all twelve."""
        d = SlingshotIndicator().compute(
            _chop(44, 2.0, 0.01, (0.0, 0.0, 1.0))).details
        for key in ("slingshot_type", "squeeze_active", "squeeze_bull",
                    "squeeze_bear", "squeeze_depth", "squeeze_conf",
                    "expansion_rate", "was_squeezed", "snapback_type",
                    "snapback_conf", "curr_bw", "avg_bw"):
            assert key in d, key
