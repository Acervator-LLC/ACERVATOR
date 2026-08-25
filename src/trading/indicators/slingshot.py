"""Slingshot -- volatility squeeze plus directional snapback.

Carter's TTM squeeze and Bollinger's band rules. The class
computes its own True Range, Donchian midline and linear
regression deliberately: reading another indicator's output
would be blending. See the class docstring.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _sma_tail,
    _stdev_tail,
    _window_has_no_range,
)


class SlingshotIndicator:
    """
    Slingshot — Volatility Squeeze + Directional Snapback.

    ── ATTRIBUTION, CORRECTED ────────────────────────────────────────────
    The NAME is Chris Moody's. The SQUEEZE is not. Moody's public-domain
    ``CM_SlingShotSystem`` (TradingView, 10-05-2014) is an EMA
    trend-and-pullback system — ``emaSlow = ema(close, 62)``,
    ``emaFast = ema(close, 38)`` — and contains no Bollinger Band, no
    Keltner Channel and no squeeze. The squeeze half descends from John
    Carter's TTM Squeeze, whose public-domain reference implementation is
    LazyBear's ``SQZMOM_LB``. The snapback half is John Bollinger's own
    published band rules. Each block below cites the source it implements.

    ── THE RULE MOODY'S SYSTEM SETTLES ───────────────────────────────────
    Moody's canonical BULLISH entry is ``emaFast > emaSlow and
    close < emaFast`` — bullish WHILE price sits below the reference
    line. Direction comes from a separate quantity (the EMA pair); it is
    never read off the price's own side of that line. The published
    pattern therefore REQUIRES "bullish" and "price below the line" to be
    expressible together.

    This class used to compute ``squeeze_bull = close > bb_mid``, which
    made those two mutually exclusive by construction. The snapback
    branch tests the same midline with the opposite sense, so the
    agreement bonus — which needs both at once — was a contradiction on a
    single tuple unpack and could not execute on any candle. Direction
    now comes from the canonical momentum value, and the contradiction is
    gone with it.

    ── SIGNAL 1: VOLATILITY SQUEEZE (Carter / TTM, via LazyBear) ─────────
    Squeeze ON when the Bollinger Bands close INSIDE the Keltner Channel:

        sqzOn = (lowerBB > lowerKC) and (upperBB < upperKC)

    Two different volatility measures are compared — standard deviation
    against true range — so "squeezed" has an absolute meaning. The
    squeeze FIRES on the release, the bar where ``sqzOn`` turns off.

    DIRECTION at the fire is the sign of the canonical momentum value:

        delta = close - (donchian_mid + sma(close, N)) / 2
        val   = linreg(delta, N, 0)          # val > 0 bullish

    ``val`` is a momentum quantity. ``close > sma`` is not, and the two
    disagree exactly when price coils under its own average while
    momentum turns up — the case the pattern exists to catch.

    ── SIGNAL 2: BAND SNAPBACK (Bollinger's rules 6 and 8) ───────────────
    Rule 8: a close OUTSIDE a band is a continuation signal, not a
    reversal. The re-entry is what converts it into a mean-reversion
    signal. So: a past close outside a band, then a later close back
    inside. A break below the lower band that re-enters is BULLISH.

    Bollinger requires re-entry and nothing more. The old code also
    demanded the close stay on the far side of the midline, which
    suppressed every reversal strong enough to cross the midline in one
    bar — the strongest ones — and was the term that collided with the
    direction test above.

    ── SEQUENCE, NOT COINCIDENCE ────────────────────────────────────────
    All three sources make this ordered: the TTM squeeze is a STATE that
    persists and then releases; Moody's conservative entry is literally a
    two-bar sequence; Bollinger's re-entry is on a LATER bar than the
    break. The bonus therefore rewards a snapback that resolves in the
    squeeze's direction on a bar AFTER the fire, not two flags that
    happen to be true on the same bar.

    ── WHY THIS IS NOT REDUNDANT WITH BB ────────────────────────────────
    BB detects WHERE price is relative to the bands (position).
    Slingshot detects the COMPRESSION→EXPANSION CYCLE (timing).
    A narrow band with price at 0.40 bb_pos = consolidation inside cloud.
    Slingshot fires when that consolidation ENDS and direction is clear.
    These are different questions about different market states.

    ── NO BLENDING ──────────────────────────────────────────────────────
    Every input here is raw candle data (close, high, low) or this
    class's own arithmetic over the module's shared scalar helpers. The
    Keltner Channel, the Donchian midline, the True Range series and the
    linear regression are all computed inside this class because the
    module has none of them. No other indicator's output is read.
    ``ATRIndicator``, ``BollingerBands``, ``IchimokuCloud`` and
    ``compute_heikin_ashi`` are deliberately NOT called. The previous
    docstring claimed "HA candle direction at expansion" as a direction
    input; the method never computed one, and importing one would be
    blending, so the claim is removed rather than honoured.
    """

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        squeeze_lookback: int = 30,
        snapback_lookback: int = 5,
        squeeze_threshold: float = 0.6,
        weight: float = 1.0,
        kc_mult: float = 1.5,
    ):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.squeeze_lookback = squeeze_lookback  # periods to measure avg bandwidth
        self.snapback_lookback = (
            snapback_lookback  # candles to look back for band break
        )
        self.squeeze_threshold = (
            squeeze_threshold  # fraction of avg bandwidth = squeeze
        )
        self.weight = weight
        # Keltner multiplier. Carter and StockCharts both specify BB 20/2.0
        # against KC 20/1.5. LazyBear's script multiplies the BB deviation
        # by multKC instead of its own mult -- a known quirk of that one
        # transcription. `bb_std` stays 2.0, which is what this class
        # already declared and what the two prose sources agree on.
        self.kc_mult = kc_mult

    @staticmethod
    def _bandwidth(upper: float, lower: float, mid: float) -> float:
        """BB bandwidth as fraction of midline (normalised)."""
        return (upper - lower) / (mid + 1e-9)

    @staticmethod
    def _linreg_endpoint(series: list) -> float:
        """Least-squares fit over ``series``, evaluated at the last point.

        This is Pine's ``linreg(src, length, 0)``: fit y = a + b*x over
        x = 0..N-1 oldest-to-newest, return the fitted value at x = N-1.
        Computed here because the module has no regression helper --
        ``linreg`` appears nowhere else in this file.
        """
        n = len(series)
        if n == 0:
            return 0.0
        if n == 1:
            return float(series[0])
        sum_x = n * (n - 1) / 2.0
        sum_xx = (n - 1) * n * (2 * n - 1) / 6.0
        sum_y = 0.0
        sum_xy = 0.0
        for x, y in enumerate(series):
            sum_y += y
            sum_xy += x * y
        denom = n * sum_xx - sum_x * sum_x
        if denom == 0.0:
            return sum_y / n
        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n
        return intercept + slope * (n - 1)

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        n = len(candles)
        min_len = self.bb_period + self.squeeze_lookback + 2
        if n < min_len:
            return Signal(
                "slingshot",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        closes = [c.close for c in candles]
        # v3.24.22 — suffix-only. The loop below reads indices
        # range(n - win, n) where win = squeeze_lookback + 5, so that is
        # the exact depth required.
        _need = self.squeeze_lookback + 5
        sma_v = _sma_tail(closes, self.bb_period, tail=_need)
        std_v = _stdev_tail(closes, self.bb_period, tail=_need)

        # ── TRUE RANGE, COMPUTED HERE ────────────────────────────────
        # Carter's Keltner leg needs True Range. `_true_range` exists at
        # module level and `VortexIndicator` uses it, but it is inlined
        # here so that every input this class reads is unambiguously raw
        # candle data or its own arithmetic. `ATRIndicator.compute()`
        # would also return this number and is deliberately NOT called:
        # it is a voter's output, and reading it would be blending.
        tr_all = [candles[0].high - candles[0].low]
        for i in range(1, n):
            c = candles[i]
            prev_close = candles[i - 1].close
            tr_all.append(
                max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
            )
        trma_v = _sma_tail(tr_all, self.bb_period, tail=_need)

        # ── MOMENTUM DELTA SERIES, COMPUTED HERE ─────────────────────
        # delta = close - (donchian_mid + sma(close, N)) / 2, where
        # donchian_mid = (highest(high, N) + lowest(low, N)) / 2.
        # `IchimokuCloud` has a (highest+lowest)/2 helper; it is another
        # indicator's method, so this class builds its own.
        win = self.squeeze_lookback + 5
        delta_lo = max(0, n - win - self.bb_period)
        deltas: dict = {}
        for i in range(delta_lo, n):
            j0 = max(0, i - self.bb_period + 1)
            hi_n = max(candles[k].high for k in range(j0, i + 1))
            lo_n = min(candles[k].low for k in range(j0, i + 1))
            donchian_mid = (hi_n + lo_n) / 2.0
            sma_i = sma_v[i] if sma_v[i] is not None else closes[i]
            deltas[i] = closes[i] - (donchian_mid + sma_i) / 2.0

        # Build per-candle values (last squeeze_lookback + 5)
        bb = []
        for i in range(n - win, n):
            if i < self.bb_period:
                continue
            mid = sma_v[i]
            std = std_v[i]
            up = mid + self.bb_std * std
            lo = mid - self.bb_std * std
            bw = self._bandwidth(up, lo, mid)
            # Keltner Channel, this class's own: ma is the same SMA the
            # bands are built on, rangema is the SMA of True Range.
            rangema = trma_v[i] if trma_v[i] is not None else 0.0
            up_kc = mid + rangema * self.kc_mult
            lo_kc = mid - rangema * self.kc_mult
            # sqzOn = (lowerBB > lowerKC) and (upperBB < upperKC)
            sqz_on = (lo > lo_kc) and (up < up_kc)
            # val = linreg(delta, N, 0)
            seg = [
                deltas[k] for k in range(max(delta_lo, i - self.bb_period + 1), i + 1)
            ]
            val = self._linreg_endpoint(seg)
            bb.append((candles[i].close, up, lo, mid, bw, sqz_on, val, rangema))

        if len(bb) < self.squeeze_lookback:
            return Signal(
                "slingshot",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        last = len(bb) - 1
        (
            curr_close,
            curr_up,
            curr_lo,
            curr_mid,
            curr_bw,
            curr_sqz_on,
            curr_val,
            curr_rangema,
        ) = bb[last]

        # ── BANDWIDTH TELEMETRY ───────────────────────────────────────
        # Retained. This is no longer what decides a squeeze -- the
        # canonical BB-inside-KC test above is -- but `was_squeezed`,
        # `curr_bw`, `avg_bw`, `squeeze_depth` and `expansion_rate` are
        # all reported fields with live consumers, and a designed
        # behaviour is not deleted.
        avg_bw = sum(b[4] for b in bb[:-1]) / max(len(bb) - 1, 1)
        prev_bw = bb[-2][4] if len(bb) >= 2 else curr_bw
        prev2_bw = bb[-3][4] if len(bb) >= 3 else prev_bw
        recent_bw = [b[4] for b in bb[-4:]]

        # ── NO VOLATILITY UNIT, NO READING ────────────────────────────
        # `avg_bw` and `prev2_bw` are Bollinger bandwidths and
        # `curr_rangema` is the Keltner range. On a halted or pegged
        # window all three are zero, and `expansion_rate`,
        # `squeeze_depth` and `mom_norm` below each divide by one of
        # them. A squeeze is a statement about volatility; with no
        # volatility there is nothing to state. Measured on a halted
        # tape, `mom_norm` reached 6.6e7 and this indicator voted BEARISH
        # at confidence 1.0000 on weight 1.0.
        #
        # The bandwidths are 2*bb_std*sigma over the midline, so they
        # inherit `_stdev_tail`'s rounding and land on ULPs rather than
        # on zero. The decisive test is therefore on the SOURCE bars that
        # feed this window -- every high, low and close across the span
        # the `bb` loop reads. The three derived tests stay underneath as
        # subordinate floors; they can only make this abstain more often.
        _span = candles[max(0, n - win - self.bb_period) :]
        _span_px: list[float] = []
        for _c in _span:
            _span_px.extend((_c.high, _c.low, _c.close))
        if (
            _window_has_no_range(_span_px)
            or avg_bw <= 0.0
            or prev2_bw <= 0.0
            or curr_rangema <= 0.0
        ):
            return Signal(
                "slingshot",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        squeeze_bw_limit = avg_bw * self.squeeze_threshold
        n_squeezed = sum(1 for bw in recent_bw if bw < squeeze_bw_limit)
        was_squeezed = n_squeezed >= 2
        expanding = curr_bw > prev_bw * 1.02
        expansion_rate = (curr_bw - prev2_bw) / (prev2_bw + 1e-9)
        min_recent_bw = min(b[4] for b in bb[-4:])
        squeeze_depth = max(0.0, avg_bw - min_recent_bw) / (avg_bw + 1e-9)

        # ── SQUEEZE FIRE: THE RELEASE BAR ─────────────────────────────
        # StockCharts: the squeeze "is said to have 'fired'" when the
        # bands expand back outside the Keltner Channel. That is the
        # sqzOn -> not sqzOn transition. Find the most recent one.
        fire_idx = -1
        for k in range(last, 0, -1):
            if bb[k - 1][5] and not bb[k][5]:
                fire_idx = k
                break

        bars_since_fire = (last - fire_idx) if fire_idx >= 0 else -1
        # The release is live for `snapback_lookback` bars after it, which
        # is the same window the snapback search uses -- so a snapback can
        # confirm a fire without either being forced onto one bar.
        squeeze_live = 0 <= bars_since_fire <= self.snapback_lookback
        fire_val = bb[fire_idx][6] if fire_idx >= 0 else 0.0

        # Direction at the fire = sign of the momentum value. NOT the
        # price's side of the midline. `_excl(squeeze_bull, squeeze_bear)`
        # holds: a float is > 0, < 0, or neither.
        squeeze_bull = squeeze_live and fire_val > 0.0
        squeeze_bear = squeeze_live and fire_val < 0.0
        just_fired = squeeze_live

        # ── SQUEEZE CONFIDENCE ────────────────────────────────────────
        # Was `squeeze_depth * 3 + expansion_rate * 2 + 0.3`. Measured
        # across a 15,680-tuple grid, that expression was EXACTLY 1.0 on
        # 8,102 of 8,102 firings: `squeeze_depth` alone drives it past
        # the ceiling above 0.2334, so `min(1.0, ...)` pinned it. A
        # confidence that is always 1.0 carries no information, and it
        # also made the +0.15 agreement bonus a numeric no-op -- the
        # bonus re-clamps on the same line it is added.
        #
        # This is NOT a recalibration of those coefficients. It is the
        # canonical strength quantity replacing an invented one: TTM's
        # output IS the momentum histogram, so the squeeze's strength is
        # |val|, expressed in the volatility unit from the same formula
        # (the Keltner range). Both terms come from the published
        # definition. The clamp to [0, 1] is this codebase's `Signal`
        # contract, not Carter's -- TTM emits a raw histogram.
        mom_norm = abs(fire_val) / (curr_rangema + 1e-9)
        squeeze_conf = max(0.0, min(1.0, mom_norm))

        # ── SNAPBACK DETECTION ────────────────────────────────────────
        # Bollinger rule 8: a close outside the band is continuation; the
        # close back INSIDE is the signal. Re-entry is the only
        # requirement. The old `curr_close < curr_mid` conjunct is gone:
        # it has no basis in the published rules, it suppressed the
        # strongest reversals, and it was the term that contradicted the
        # direction test.
        snapback_type = ""
        snapback_conf = 0.0
        snapback_break_idx = -1

        for j in range(-self.snapback_lookback, -1):
            idx = len(bb) + j
            if idx < 1 or idx >= len(bb):
                continue

            past_close, past_up, past_lo, past_mid = bb[idx][:4]

            # BULLISH: past close below lower band, now back inside
            if past_close < past_lo:
                if curr_close > curr_lo:
                    penetration = (past_lo - past_close) / (past_lo + 1e-9)
                    # Better if the prior close was a significant penetration
                    # and current close is moving toward midline (not just touching lo)
                    midward = curr_close > past_close
                    snapback_conf = max(
                        0.0,
                        min(1.0, penetration * 8 + (0.2 if midward else 0.0) + 0.35),
                    )
                    snapback_type = "bullish_snapback"
                    snapback_break_idx = idx
                    break

            # BEARISH: past close above upper band, now back inside
            elif past_close > past_up:
                if curr_close < curr_up:
                    penetration = (past_close - past_up) / (past_up + 1e-9)
                    midward = curr_close < past_close
                    snapback_conf = max(
                        0.0,
                        min(1.0, penetration * 8 + (0.2 if midward else 0.0) + 0.35),
                    )
                    snapback_type = "bearish_snapback"
                    snapback_break_idx = idx
                    break

        # ── COMBINE ──────────────────────────────────────────────────
        # Squeeze takes precedence (predictive); snapback is reactive.
        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        active_type = ""

        if squeeze_bull:
            direction = SignalDirection.BULLISH
            confidence = squeeze_conf
            active_type = "squeeze_bull"
        elif squeeze_bear:
            direction = SignalDirection.BEARISH
            confidence = squeeze_conf
            active_type = "squeeze_bear"
        elif snapback_type == "bullish_snapback":
            direction = SignalDirection.BULLISH
            confidence = snapback_conf
            active_type = snapback_type
        elif snapback_type == "bearish_snapback":
            direction = SignalDirection.BEARISH
            confidence = snapback_conf
            active_type = snapback_type

        # A squeeze that outranks a CONTRADICTING snapback is a
        # precedence choice this codebase makes; canon has no such rule.
        # The precedence is kept -- it is a designed behaviour -- but the
        # discard is no longer silent. Measured at 7.2% of evaluations on
        # the grid, and it had no reported field at all.
        snapback_conflict = bool(
            snapback_type
            and (
                (squeeze_bull and snapback_type == "bearish_snapback")
                or (squeeze_bear and snapback_type == "bullish_snapback")
            )
        )

        # ── AGREEMENT BONUS ──────────────────────────────────────────
        # Sequential, per all three sources: the snapback's break must
        # land at or after the squeeze fire, and the re-entry (this bar)
        # must be strictly later than the fire. Two flags true on one bar
        # is not what the published pattern describes.
        sequential = (
            fire_idx >= 0 and bars_since_fire >= 1 and snapback_break_idx >= fire_idx
        )
        agree = False
        if sequential and squeeze_bull and snapback_type == "bullish_snapback":
            agree = True
            confidence = max(0.0, min(1.0, confidence + 0.15))
            active_type = "squeeze_bull+snapback"
        elif sequential and squeeze_bear and snapback_type == "bearish_snapback":
            agree = True
            confidence = max(0.0, min(1.0, confidence + 0.15))
            active_type = "squeeze_bear+snapback"

        return Signal(
            indicator="slingshot",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "slingshot_type": active_type,
                "squeeze_active": just_fired,
                "squeeze_bull": squeeze_bull,
                "squeeze_bear": squeeze_bear,
                "squeeze_depth": round(squeeze_depth, 4),
                "squeeze_conf": round(squeeze_conf, 4),
                "expansion_rate": round(expansion_rate, 4),
                "was_squeezed": was_squeezed,
                "snapback_type": snapback_type,
                "snapback_conf": round(snapback_conf, 4),
                "curr_bw": round(curr_bw, 6),
                "avg_bw": round(avg_bw, 6),
                "sqz_on": curr_sqz_on,
                "momentum": round(curr_val, 8),
                "fire_momentum": round(fire_val, 8),
                "mom_norm": round(mom_norm, 4),
                "bars_since_fire": bars_since_fire,
                "expanding": expanding,
                "snapback_conflict": snapback_conflict,
                "agree": agree,
            },
        )
