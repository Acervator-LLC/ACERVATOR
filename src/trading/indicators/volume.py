"""``VolumeAnalysis``, the volume indicator suite.

``compute`` returns a ``Signal`` named ``volume`` carrying OBV, MFI, CMF,
A/D and volume-ratio readings. ``_obv``, ``_mfi`` and ``_cmf`` build those
series and ``_detect_divergence`` compares one of them against ``closes``.
"""

from __future__ import annotations

import math

from .types import (
    PERCENT_PER_RATIO_UNIT,
    VOLUME_SPIKE_PCT,
    SignalDirection,
    Signal,
)
from .helpers import (
    _ema,
)


class VolumeAnalysis:
    """Volume analysis over ``period`` candles.

    ``compute`` reports ``obv_rising``, ``obv_divergence``, ``mfi``,
    ``cmf``, ``vol_ratio``, ``capitulation`` and ``weak_rally`` in the
    ``Signal`` details.
    """

    def __init__(
        self,
        period: int = 20,
        spike_threshold_pct: float = VOLUME_SPIKE_PCT,
        weight: float = 0.8,
    ):
        self.period = period
        # spike_threshold is a ratio; vol_ratio is 1.0 on an average candle.
        self.spike_threshold = spike_threshold_pct / PERCENT_PER_RATIO_UNIT
        self.weight = weight
        self.mfi_period = 14
        self.chaikin_money_flow_period = 20
        self.div_lookback = 20  # candles to check for divergence

    @staticmethod
    def _mfi(candles: list, period: int = 14) -> float:
        """Quong and Soudack's Money Flow Index over ``period`` candles.

        ``_mfi`` returns ``math.nan`` where neither money flow was credited.
        """
        if len(candles) < period + 1:
            return math.nan
        pos_mf = neg_mf = 0.0
        for i in range(len(candles) - period, len(candles)):
            tp = (candles[i].high + candles[i].low + candles[i].close) / 3.0
            ptp = (
                candles[i - 1].high + candles[i - 1].low + candles[i - 1].close
            ) / 3.0
            mf = tp * candles[i].volume
            if tp > ptp:
                pos_mf += mf
            elif tp < ptp:
                neg_mf += mf
        # `pos_mf` and `neg_mf` sum non-negative terms, exact at every scale.
        total_mf = pos_mf + neg_mf
        if total_mf <= 0.0:
            return math.nan
        return 100.0 * (pos_mf / total_mf)

    @staticmethod
    def _cmf(candles: list, period: int = 20) -> float:
        """Chaikin Money Flow over ``period``: sum(clv * volume) / sum(volume)."""
        if len(candles) < period:
            return 0.0
        window = candles[-period:]
        num = denom = 0.0
        for c in window:
            hl = c.high - c.low
            if hl > 0:
                clv = ((c.close - c.low) - (c.high - c.close)) / hl
            else:
                clv = 0.0
            num += clv * c.volume
            denom += c.volume
        return num / denom if denom > 0 else 0.0

    @staticmethod
    def _obv(candles: list) -> list:
        """Granville's On-Balance Volume, one entry per candle in ``candles``."""
        obv = [0.0]
        for i in range(1, len(candles)):
            if candles[i].close > candles[i - 1].close:
                obv.append(obv[-1] + candles[i].volume)
            elif candles[i].close < candles[i - 1].close:
                obv.append(obv[-1] - candles[i].volume)
            else:
                obv.append(obv[-1])
        return obv

    def _detect_divergence(self, closes: list, indicator: list, lookback: int) -> str:
        """Compare ``closes`` against ``indicator`` over ``lookback`` candles.

        Returns ``"bullish"``, ``"bearish"`` or ``"none"``.
        """
        if len(closes) < lookback + 1 or len(indicator) < lookback + 1:
            return "none"
        curr_close = closes[-1]
        curr_ind = indicator[-1]
        past_close = min(closes[-lookback:])
        past_ind_at_price_low = indicator[
            -lookback + closes[-lookback:].index(past_close)
        ]

        price_near_low = curr_close <= past_close * 1.03
        ind_higher = curr_ind > past_ind_at_price_low * 1.01
        if price_near_low and ind_higher:
            return "bullish"

        past_high = max(closes[-lookback:])
        past_ind_at_price_high = indicator[
            -lookback + closes[-lookback:].index(past_high)
        ]
        price_near_high = curr_close >= past_high * 0.97
        ind_lower = curr_ind < past_ind_at_price_high * 0.99
        if price_near_high and ind_lower:
            return "bearish"

        return "none"

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        min_len = (
            max(
                self.period,
                self.mfi_period,
                self.chaikin_money_flow_period,
                self.div_lookback,
            )
            + 5
        )
        if len(candles) < min_len:
            return Signal(
                "volume",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        closes = [c.close for c in candles]
        volumes = [c.volume for c in candles]

        obv = self._obv(candles)
        obv_ema_s = _ema(obv, 5)
        obv_ema_l = _ema(obv, self.period)
        _obv_s = obv_ema_s[-1]
        _obv_l = obv_ema_l[-1]
        obv_rising = _obv_s is not None and _obv_l is not None and _obv_s > _obv_l
        obv_accel = obv[-1] > obv[-2]

        obv_div = self._detect_divergence(closes, obv, self.div_lookback)

        mfi = self._mfi(candles, self.mfi_period)
        if math.isnan(mfi):
            # `_mfi` has no money ratio; `mfi_ob` and `mfi_os` read False on nan.
            return Signal(
                "volume",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )
        mfi_ob = mfi > 80
        mfi_os = mfi < 20
        mfi_prev = (
            self._mfi(candles[:-3], self.mfi_period)
            if len(candles) > self.mfi_period + 3
            else mfi
        )
        # No consumer reads the MFI slope.
        mfi > mfi_prev

        mfi_closes = closes[-self.div_lookback :]
        if mfi_os and closes[-1] <= min(mfi_closes) * 1.02:
            mfi_div = "bullish"
        elif mfi_ob and closes[-1] >= max(mfi_closes) * 0.98:
            mfi_div = "bearish"
        else:
            mfi_div = "none"

        cmf = self._cmf(candles, self.chaikin_money_flow_period)
        cmf_bull = cmf > 0.05
        cmf_bear = cmf < -0.05
        cmf_strong_bull = cmf > 0.15
        cmf_strong_bear = cmf < -0.15

        ad: list[float] = []
        for c in candles:
            hl = c.high - c.low
            clv = ((c.close - c.low) - (c.high - c.close)) / hl if hl > 0 else 0.0
            ad.append(clv * c.volume + (ad[-1] if ad else 0.0))

        ad_trend = ad[-1] - ad[-self.period]
        ad_rising = ad[-1] > ad[-2]
        price_trend = closes[-1] - closes[-self.period]
        ad_price_div_bull = ad_trend > 0 and price_trend < 0
        ad_price_div_bear = ad_trend < 0 and price_trend > 0

        avg_vol = sum(volumes[-self.period :]) / self.period
        curr_vol = volumes[-1]
        if avg_vol <= 0.0:
            return Signal(
                "volume",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )
        vol_ratio = curr_vol / avg_vol
        is_spike = vol_ratio > self.spike_threshold
        is_high = vol_ratio > 1.5
        is_low = vol_ratio < 0.6

        candle_up = candles[-1].close >= candles[-1].open
        candle_dn = not candle_up

        capitulation = is_spike and candle_dn and obv_accel

        weak_rally = candle_up and is_low and obv_rising

        vol_confirms_bull = is_high and candle_up and obv_accel
        vol_confirms_bear = is_high and candle_dn and not obv_accel

        score = 0.0

        if obv_div == "bullish":
            score += 0.35
        elif obv_div == "bearish":
            score -= 0.35

        if mfi_div == "bullish" or mfi_os:
            score += 0.25
        elif mfi_div == "bearish" or mfi_ob:
            score -= 0.25

        if cmf_strong_bull:
            score += 0.20
        elif cmf_bull:
            score += 0.10
        elif cmf_strong_bear:
            score -= 0.20
        elif cmf_bear:
            score -= 0.10

        if ad_price_div_bull:
            score += 0.15
        elif ad_price_div_bear:
            score -= 0.15

        if obv_rising:
            score += 0.10
        else:
            score -= 0.10

        if capitulation:
            score += 0.20
        elif vol_confirms_bull:
            score += 0.10
        elif vol_confirms_bear:
            score -= 0.10
        elif weak_rally:
            score -= 0.08

        if score > 0.1:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, score))
        elif score < -0.1:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(score)))
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="volume",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "obv_rising": obv_rising,
                "obv_divergence": obv_div,
                "mfi": mfi,
                "mfi_overbought": mfi_ob,
                "mfi_oversold": mfi_os,
                "mfi_divergence": mfi_div,
                "cmf": round(cmf, 4),
                "cmf_bull": cmf_bull,
                "cmf_bear": cmf_bear,
                "ad_rising": ad_rising,
                "ad_price_div_bull": ad_price_div_bull,
                "ad_price_div_bear": ad_price_div_bear,
                "vol_ratio": round(vol_ratio, 2),
                "vol_spike": is_spike,
                "vol_high": is_high,
                "vol_low": is_low,
                "capitulation": capitulation,
                "weak_rally": weak_rally,
                "vol_confirms_bull": vol_confirms_bull,
                "vol_confirms_bear": vol_confirms_bear,
            },
        )
