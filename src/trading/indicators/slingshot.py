"""Slingshot -- volatility squeeze plus directional snapback.

``SlingshotIndicator`` implements Carter's TTM squeeze with Bollinger's
band rules. It builds ``tr_all``, the Donchian midline and
``_linreg_endpoint`` from raw candles.
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

    ATTRIBUTION: the NAME is Chris Moody's ``CM_SlingShotSystem``
    (TradingView, 2014), an EMA trend-and-pullback system with no
    Bollinger Band, no Keltner Channel and no squeeze; the SQUEEZE is
    John Carter's TTM Squeeze, public reference LazyBear's
    ``SQZMOM_LB``; the SNAPBACK is Bollinger's rules 6 and 8, a close
    outside a band and then a later close back inside; and ``compute``
    reads only raw candle fields and this class's own arithmetic,
    calling no other voter, over

        sqzOn = (lowerBB > lowerKC) and (upperBB < upperKC)
        delta = close - (donchian_mid + sma(close, N)) / 2
        val   = linreg(delta, N, 0)
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
        # Carter and StockCharts specify BB 20/2.0 against KC 20/1.5;
        # LazyBear scales the BB deviation by multKC.
        self.kc_mult = kc_mult

    @staticmethod
    def _bandwidth(upper: float, lower: float, mid: float) -> float:
        """BandWidth: ``(upper - lower) / mid``, Bollinger's normalisation."""
        return (upper - lower) / mid

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
        # `_need` covers the delta loop, which reaches `bb_period` bars
        # below the `bb` loop.
        _need = self.squeeze_lookback + 5 + self.bb_period
        sma_v = _sma_tail(closes, self.bb_period, tail=_need)
        std_v = _stdev_tail(closes, self.bb_period, tail=_need)

        # Carter's Keltner leg needs True Range; `tr_all` computes it
        # without `ATRIndicator`.
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
            # `mid` averages closes `candles_from_raw` admits only when
            # positive, so it cannot be zero.
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

        # `expansion_rate`, `squeeze_depth` and `mom_norm` divide by a
        # volatility a halted window zeroes; bandwidths round to ULPs.
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
        expansion_rate = (curr_bw - prev2_bw) / prev2_bw
        min_recent_bw = min(b[4] for b in bb[-4:])
        squeeze_depth = max(0.0, avg_bw - min_recent_bw) / avg_bw

        # StockCharts: the squeeze releases when the bands expand back
        # outside the Keltner Channel, the sqzOn -> not sqzOn transition.
        fire_idx = -1
        for k in range(last, 0, -1):
            if bb[k - 1][5] and not bb[k][5]:
                fire_idx = k
                break

        bars_since_fire = (last - fire_idx) if fire_idx >= 0 else -1
        # The release stays live for `snapback_lookback` bars, so a later
        # snapback confirms the same fire.
        squeeze_live = 0 <= bars_since_fire <= self.snapback_lookback
        fire_val = bb[fire_idx][6] if fire_idx >= 0 else 0.0

        # Direction at the fire is the sign of `fire_val`, never the
        # price's own side of the midline.
        squeeze_bull = squeeze_live and fire_val > 0.0
        squeeze_bear = squeeze_live and fire_val < 0.0
        just_fired = squeeze_live

        # TTM's output is the momentum histogram: `mom_norm` is |fire_val|
        # in the Keltner range unit, clamped by `Signal`'s [0, 1] contract.
        mom_norm = abs(fire_val) / curr_rangema
        squeeze_conf = max(0.0, min(1.0, mom_norm))

        # Bollinger rule 8: a close outside the band is continuation; the
        # close back inside is the signal.
        snapback_type = ""
        snapback_conf = 0.0
        snapback_break_idx = -1

        for j in range(-self.snapback_lookback, -1):
            idx = len(bb) + j
            if idx < 1 or idx >= len(bb):
                continue

            past_close, past_up, past_lo, past_mid = bb[idx][:4]

            if past_close < past_lo:
                if curr_close > curr_lo:
                    # The branch puts `past_close` under `past_lo`, and
                    # `candles_from_raw` keeps it above zero.
                    penetration = (past_lo - past_close) / past_lo
                    midward = curr_close > past_close
                    snapback_conf = max(
                        0.0,
                        min(1.0, penetration * 8 + (0.2 if midward else 0.0) + 0.35),
                    )
                    snapback_type = "bullish_snapback"
                    snapback_break_idx = idx
                    break

            elif past_close > past_up:
                if curr_close < curr_up:
                    # `past_up` is `mid` plus a non-negative deviation, so
                    # it carries `mid`'s positive sign.
                    penetration = (past_close - past_up) / past_up
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

        # `snapback_conflict` reports a snapback the squeeze outranked
        # while pointing the other way.
        snapback_conflict = bool(
            snapback_type
            and (
                (squeeze_bull and snapback_type == "bearish_snapback")
                or (squeeze_bear and snapback_type == "bullish_snapback")
            )
        )

        # The break lands at or after the fire; the re-entry is strictly
        # later.
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
                "squeeze_depth": squeeze_depth,
                "squeeze_conf": squeeze_conf,
                "expansion_rate": expansion_rate,
                "was_squeezed": was_squeezed,
                "snapback_type": snapback_type,
                "snapback_conf": snapback_conf,
                "curr_bw": curr_bw,
                "avg_bw": avg_bw,
                "sqz_on": curr_sqz_on,
                "momentum": curr_val,
                "fire_momentum": fire_val,
                "mom_norm": mom_norm,
                "bars_since_fire": bars_since_fire,
                "expanding": expanding,
                "snapback_conflict": snapback_conflict,
                "agree": agree,
            },
        )
