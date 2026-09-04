"""Slingshot -- volatility squeeze plus directional snapback.

Carter's TTM squeeze and Bollinger's band rules. The class computes
its own True Range, Donchian midline and linear regression rather
than reading another indicator's output.
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
    """Volatility squeeze plus directional snapback, over one candle list.

    ATTRIBUTION. The NAME is Chris Moody's; the SQUEEZE is not. Moody's
    ``CM_SlingShotSystem`` (TradingView, 10-05-2014) is an EMA
    trend-and-pullback system -- ``emaSlow = ema(close, 62)``,
    ``emaFast = ema(close, 38)`` -- with no Bollinger Band, no Keltner
    Channel and no squeeze. The squeeze half is John Carter's TTM
    Squeeze, whose public reference implementation is LazyBear's
    ``SQZMOM_LB``. The snapback half is John Bollinger's band rules.

    SIGNAL 1, THE VOLATILITY SQUEEZE (Carter / TTM, via LazyBear). The
    squeeze is ON while the Bollinger Bands sit inside the Keltner
    Channel, comparing standard deviation against true range:

        sqzOn = (lowerBB > lowerKC) and (upperBB < upperKC)

    It FIRES on the release, the bar where ``sqzOn`` turns off. Direction
    at the fire is the sign of the canonical momentum value, never the
    price's own side of the midline:

        delta = close - (donchian_mid + sma(close, N)) / 2
        val   = linreg(delta, N, 0)          # val > 0 bullish

    SIGNAL 2, THE BAND SNAPBACK (Bollinger's rules 6 and 8). Rule 8: a
    close OUTSIDE a band is a continuation signal, not a reversal. The
    later close back INSIDE is what makes it a mean-reversion signal, and
    re-entry is the only requirement. A break below the lower band that
    re-enters is BULLISH.

    SEQUENCE, NOT COINCIDENCE. All three sources order these: the TTM
    squeeze is a state that persists and then releases, Moody's
    conservative entry is a two-bar sequence, and Bollinger's re-entry is
    on a LATER bar than the break. The agreement bonus therefore needs
    the snapback to resolve after the fire, not two flags true on one bar.

    NOT REDUNDANT WITH ``BollingerBands``, which reports where price sits
    relative to the bands. This reports the compression-to-expansion
    cycle: it fires when a consolidation ENDS and direction is clear.

    NO BLENDING. Every input is raw candle data (close, high, low) or
    this class's own arithmetic over the module's shared scalar helpers.
    The Keltner Channel, the Donchian midline, the True Range series and
    the linear regression are computed inside this class because the
    module has none of them. ``ATRIndicator``, ``BollingerBands``,
    ``IchimokuCloud`` and ``compute_heikin_ashi`` are deliberately NOT
    called.
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
        # Carter and StockCharts both specify BB 20/2.0 against KC 20/1.5.
        # LazyBear's script multiplies the BB deviation by multKC instead.
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
        """Vote on ``candles``: the squeeze release first, the snapback second.

        Returns an abstaining :class:`Signal` when the tape is shorter than
        the formula needs, or when the window it reads carries no price
        range and every volatility denominator below is therefore zero.
        """
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
        # The delta loop reaches `bb_period` bars deeper than the `bb` loop,
        # because each linreg segment spans that many deltas.
        _need = self.squeeze_lookback + 5 + self.bb_period
        sma_v = _sma_tail(closes, self.bb_period, tail=_need)
        std_v = _stdev_tail(closes, self.bb_period, tail=_need)

        # Carter's Keltner leg needs True Range; computing it here avoids
        # reading `ATRIndicator`, which is another voter's output.
        tr_all = [candles[0].high - candles[0].low]
        for i in range(1, n):
            c = candles[i]
            prev_close = candles[i - 1].close
            tr_all.append(
                max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
            )
        trma_v = _sma_tail(tr_all, self.bb_period, tail=_need)

        win = self.squeeze_lookback + 5
        delta_lo = max(0, n - win - self.bb_period)
        deltas: dict = {}
        for i in range(delta_lo, n):
            j0 = max(0, i - self.bb_period + 1)
            hi_n = max(candles[k].high for k in range(j0, i + 1))
            lo_n = min(candles[k].low for k in range(j0, i + 1))
            donchian_mid = (hi_n + lo_n) / 2.0
            sma_i = sma_v[i]
            deltas[i] = closes[i] - (donchian_mid + sma_i) / 2.0

        bb = []
        for i in range(n - win, n):
            if i < self.bb_period:
                continue
            mid = sma_v[i]
            std = std_v[i]
            up = mid + self.bb_std * std
            lo = mid - self.bb_std * std
            bw = self._bandwidth(up, lo, mid)
            # LazyBear's KC shares the BB basis; rangema is the SMA of
            # True Range over the same period.
            rangema = trma_v[i] if trma_v[i] is not None else 0.0
            up_kc = mid + rangema * self.kc_mult
            lo_kc = mid - rangema * self.kc_mult
            sqz_on = (lo > lo_kc) and (up < up_kc)
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

        # Reported fields only; the BB-inside-KC test above is what
        # decides the squeeze.
        avg_bw = sum(b[4] for b in bb[:-1]) / max(len(bb) - 1, 1)
        prev_bw = bb[-2][4] if len(bb) >= 2 else curr_bw
        prev2_bw = bb[-3][4] if len(bb) >= 3 else prev_bw
        recent_bw = [b[4] for b in bb[-4:]]

        # `expansion_rate`, `squeeze_depth` and `mom_norm` below each
        # divide by a volatility that is zero on a halted window.
        # The bandwidths inherit `_stdev_tail`'s rounding and land on ULPs
        # rather than on zero, so the decisive test is on the source bars.
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

        # StockCharts: the squeeze is released when the bands expand back
        # outside the Keltner Channel, the sqzOn -> not sqzOn transition.
        fire_idx = -1
        for k in range(last, 0, -1):
            if bb[k - 1][5] and not bb[k][5]:
                fire_idx = k
                break

        bars_since_fire = (last - fire_idx) if fire_idx >= 0 else -1
        # The release stays live for `snapback_lookback` bars after it, so
        # a snapback on a later bar can confirm the same fire.
        squeeze_live = 0 <= bars_since_fire <= self.snapback_lookback
        fire_val = bb[fire_idx][6] if fire_idx >= 0 else 0.0

        # Direction at the fire is the sign of the momentum value, never
        # the price's own side of the midline.
        squeeze_bull = squeeze_live and fire_val > 0.0
        squeeze_bear = squeeze_live and fire_val < 0.0
        just_fired = squeeze_live

        # TTM's output IS the momentum histogram, so squeeze strength is
        # |val| in the Keltner range unit from the same formula.
        # The clamp to [0, 1] is `Signal`'s contract, not Carter's.
        mom_norm = abs(fire_val) / (curr_rangema + 1e-9)
        squeeze_conf = max(0.0, min(1.0, mom_norm))

        # Bollinger rule 8: a close outside the band is continuation, and
        # the close back INSIDE is the only requirement for the signal.
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

        # Reports the discard the precedence above makes: a snapback the
        # squeeze outranked while pointing the other way.
        snapback_conflict = bool(
            snapback_type
            and (
                (squeeze_bull and snapback_type == "bearish_snapback")
                or (squeeze_bear and snapback_type == "bullish_snapback")
            )
        )

        # The break must land at or after the fire, and the re-entry on
        # this bar must be strictly later than the fire.
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
