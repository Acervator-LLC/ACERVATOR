"""Volume suite -- OBV, MFI, CMF, A/D line and volume ratio.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

from .types import (
    PERCENT_PER_RATIO_UNIT,
    VOLUME_SPIKE_PCT,
    SignalDirection,
    Signal,
)
from .helpers import (
    _ema,
)


# ---------------------------------------------------------------------------
# 6. Volume Analysis
# ---------------------------------------------------------------------------
# Helper: simple EMA used for MFI smoothing (already defined as _ema above)

class VolumeAnalysis:
    """
    Multi-indicator volume analysis suite.

    INDICATORS (in order of practical usefulness for accumulation):

    1. OBV DIVERGENCE (most powerful signal)
         Price makes lower low but OBV makes higher low  → bullish divergence
         = smart money accumulating despite price decline → strong FOLD signal
         Price makes higher high but OBV makes lower high → bearish divergence
         = distribution at peak levels                   → strong SCRUM signal

    2. MFI (Money Flow Index) — volume-weighted RSI (14-period)
         MFI > 80: volume-confirmed overbought            → SCRUM signal
         MFI < 20: volume-confirmed oversold              → FOLD signal
         MFI divergence mirrors OBV divergence but filters by volume weight.

    3. CMF (Chaikin Money Flow) — 20-period
         CMF > +0.05: net buying pressure (accumulation)
         CMF < -0.05: net selling pressure (distribution)
         CMF near zero: balanced / consolidation

    4. A/D LINE TREND — Accumulation/Distribution
         A/D rising while price flat/falling → underlying accumulation
         A/D falling while price flat/rising → underlying distribution

    5. VOLUME RATIO — current vs N-period average
         ratio > 1.5: above-average participation
         ratio > 2.5: significant spike
         Direction of the candle determines bullish/bearish interpretation.

    6. OBV TREND — slow trend component
         OBV EMA(5) vs EMA(20): basic direction of money flow.

    ACCUMULATION STRATEGY WIRING:
         Bullish divergence (OBV or MFI) → fold confidence +0.15 to +0.20
         Volume spike on DOWN candle + OBV rising → capitulation fold +0.18
         MFI < 20 → fold +0.12
         MFI > 80 → scrum +0.10
         Bearish divergence → scrum +0.12
         CMF strongly negative while OBV rising → premium fold (distribution
           near surface but net accumulation in the background)
    """

    def __init__(self, period: int = 20,
                 spike_threshold_pct: float = VOLUME_SPIKE_PCT,
                 weight: float = 0.8):
        self.period          = period
        # `vol_ratio` in compute() is this candle's volume over the
        # window average: a RATIO, 1.0 for an average candle. The spike
        # limit is the same ratio, so it is carried in percent and
        # divided down here once -- see the Units note at the top.
        self.spike_threshold = spike_threshold_pct / PERCENT_PER_RATIO_UNIT
        self.weight          = weight
        self.mfi_period      = 14
        # A BAR COUNT, not a CMF reading. `cmf_period` read as a CMF
        # quantity, which is bounded [-1, 1], and 20 bars is not.
        self.chaikin_money_flow_period = 20
        self.div_lookback    = 20   # candles to check for divergence

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _mfi(candles: list, period: int = 14) -> float:
        """Money Flow Index: volume-weighted RSI on typical price."""
        if len(candles) < period + 1:
            return 50.0
        pos_mf = neg_mf = 0.0
        for i in range(len(candles) - period, len(candles)):
            tp  = (candles[i].high + candles[i].low + candles[i].close) / 3.0
            ptp = (candles[i-1].high + candles[i-1].low + candles[i-1].close) / 3.0
            mf  = tp * candles[i].volume
            if tp > ptp:
                pos_mf += mf
            elif tp < ptp:
                neg_mf += mf
        # No negative money flow but SOME positive flow is the defined
        # case: the ratio diverges and MFI is 100. With NEITHER flow the
        # ratio is 0/0 and there is no reading, yet the test below
        # answered 100.0 -- the TOP of the scale, read by `mfi_ob` as
        # maximum overbought -- on a market where the typical price never
        # changed and so neither bucket was ever credited. 50.0 is this
        # function's own no-information value, returned by the
        # short-history branch above, and it leaves both `mfi_ob` and
        # `mfi_os` False.
        if pos_mf < 1e-9 and neg_mf < 1e-9:
            return 50.0
        if neg_mf < 1e-9:
            return 100.0
        return 100.0 - 100.0 / (1.0 + pos_mf / neg_mf)

    @staticmethod
    def _cmf(candles: list, period: int = 20) -> float:
        """Chaikin Money Flow: sum(CLV×Vol) / sum(Vol) over period."""
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
            num   += clv * c.volume
            denom += c.volume
        return num / denom if denom > 0 else 0.0

    @staticmethod
    def _obv(candles: list) -> list:
        """On-Balance Volume cumulative series."""
        obv = [0.0]
        for i in range(1, len(candles)):
            if candles[i].close > candles[i-1].close:
                obv.append(obv[-1] + candles[i].volume)
            elif candles[i].close < candles[i-1].close:
                obv.append(obv[-1] - candles[i].volume)
            else:
                obv.append(obv[-1])
        return obv

    def _detect_divergence(self, closes: list, indicator: list,
                           lookback: int) -> str:
        """
        Detect price/indicator divergence over `lookback` candles.
        Returns: 'bullish' | 'bearish' | 'none'
        Bullish: price lower low + indicator higher low (accumulation)
        Bearish: price higher high + indicator lower high (distribution)
        """
        if len(closes) < lookback + 1 or len(indicator) < lookback + 1:
            return "none"
        curr_close = closes[-1]
        curr_ind   = indicator[-1]
        past_close = min(closes[-lookback:])
        past_ind_at_price_low = indicator[-lookback + closes[-lookback:].index(past_close)]

        # Bullish divergence: price at/near low but indicator higher than its prior low
        price_near_low = curr_close <= past_close * 1.03
        ind_higher     = curr_ind > past_ind_at_price_low * 1.01
        if price_near_low and ind_higher:
            return "bullish"

        # Bearish divergence: price at/near high but indicator lower than its prior high
        past_high  = max(closes[-lookback:])
        past_ind_at_price_high = indicator[-lookback + closes[-lookback:].index(past_high)]
        price_near_high = curr_close >= past_high * 0.97
        ind_lower       = curr_ind < past_ind_at_price_high * 0.99
        if price_near_high and ind_lower:
            return "bearish"

        return "none"

    # ── main compute ────────────────────────────────────────────────────────

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        min_len = max(self.period, self.mfi_period,
                      self.chaikin_money_flow_period,
                      self.div_lookback) + 5
        if len(candles) < min_len:
            return Signal("volume", timeframe, SignalDirection.NEUTRAL,
                          0.0, self.weight)

        closes  = [c.close  for c in candles]
        volumes = [c.volume for c in candles]

        # ── OBV ──────────────────────────────────────────────────────────
        obv = self._obv(candles)
        obv_ema_s = _ema(obv, 5)
        obv_ema_l = _ema(obv, self.period)
        # ``_ema`` has no value before its seed and says so with None
        # (issue #99). Both reads here are the LAST entry and the guard
        # above admits only ``len(candles) >= self.period + 5``, so both
        # are real on every reachable path. The None test is what makes
        # that a stated precondition instead of an assumption: with no
        # EMA there is no OBV trend, and "not rising" is the abstention.
        # It replaces a silent fabrication -- ``_ema`` used to hand back
        # the RAW OBV relabelled as its own moving average on a short
        # series, which made this line compare OBV against itself.
        _obv_s = obv_ema_s[-1]
        _obv_l = obv_ema_l[-1]
        obv_rising = (_obv_s is not None and _obv_l is not None
                      and _obv_s > _obv_l)
        obv_accel  = obv[-1] > obv[-2]          # OBV up this candle?

        # OBV divergence
        obv_div = self._detect_divergence(closes, obv, self.div_lookback)

        # ── MFI ──────────────────────────────────────────────────────────
        mfi = self._mfi(candles, self.mfi_period)
        mfi_ob   = mfi > 80
        mfi_os   = mfi < 20
        # MFI direction (compare to 3 candles ago for stability)
        mfi_prev = self._mfi(candles[:-3], self.mfi_period) if len(candles) > self.mfi_period + 3 else mfi
        mfi_rising = mfi > mfi_prev

        # Simple MFI divergence: price new low vs MFI higher
        mfi_closes  = closes[-self.div_lookback:]
        if mfi_os and closes[-1] <= min(mfi_closes) * 1.02:
            mfi_div = "bullish"
        elif mfi_ob and closes[-1] >= max(mfi_closes) * 0.98:
            mfi_div = "bearish"
        else:
            mfi_div = "none"

        # ── CMF ──────────────────────────────────────────────────────────
        cmf  = self._cmf(candles, self.chaikin_money_flow_period)
        cmf_bull    = cmf >  0.05
        cmf_bear    = cmf < -0.05
        cmf_strong_bull = cmf >  0.15
        cmf_strong_bear = cmf < -0.15

        # ── A/D LINE ─────────────────────────────────────────────────────
        # NOTE: a forward recurrence — each element reads ad[-1] — so this
        # one genuinely needs the full history and cannot be tail-bounded
        # the way the window statistics above were.
        ad: list[float] = []
        for c in candles:
            hl = c.high - c.low
            clv = ((c.close - c.low) - (c.high - c.close)) / hl if hl > 0 else 0.0
            ad.append(clv * c.volume + (ad[-1] if ad else 0.0))

        ad_trend    = ad[-1] - ad[-self.period]   # + = net accumulation
        ad_rising   = ad[-1] > ad[-2]
        # A/D vs price divergence: A/D rising while price falling
        price_trend = closes[-1] - closes[-self.period]
        ad_price_div_bull = ad_trend > 0 and price_trend < 0  # A/D up, price down
        ad_price_div_bear = ad_trend < 0 and price_trend > 0  # A/D down, price up

        # ── VOLUME RATIO ─────────────────────────────────────────────────
        avg_vol   = sum(volumes[-self.period:]) / self.period
        curr_vol  = volumes[-1]
        # A window that traded no volume has no average for the current
        # bar to be measured against, so the ratio is 0/0 -- and
        # `is_spike`, `is_high` and `is_low` below are all statements
        # about that ratio. Volumes are SOURCE values and non-negative
        # (candles_from_raw refuses a negative one), so their sum is 0.0
        # exactly when every bar traded nothing.
        if avg_vol <= 0.0:
            return Signal("volume", timeframe,
                          SignalDirection.NEUTRAL, 0.0, self.weight)
        vol_ratio = curr_vol / (avg_vol + 1e-9)
        is_spike  = vol_ratio > self.spike_threshold
        is_high   = vol_ratio > 1.5
        is_low    = vol_ratio < 0.6   # low-volume move = weak conviction

        # Current candle direction
        candle_up = candles[-1].close >= candles[-1].open
        candle_dn = not candle_up

        # ── CAPITULATION SIGNAL ──────────────────────────────────────────
        # High/spike volume on a DOWN candle BUT OBV still rising:
        # Aggressive selling is being absorbed by buyers = premium fold entry
        capitulation = (is_spike and candle_dn and obv_accel)

        # ── WEAK RALLY ───────────────────────────────────────────────────
        # Price up but volume below average = rally not supported = caution on scrum
        weak_rally = (candle_up and is_low and obv_rising)

        # ── VOLUME CONFIRMATION ──────────────────────────────────────────
        # Strong volume confirming directional move = high conviction
        vol_confirms_bull = (is_high and candle_up and obv_accel)
        vol_confirms_bear = (is_high and candle_dn and not obv_accel)

        # ── COMPOSITE SCORE ──────────────────────────────────────────────
        score = 0.0

        # OBV divergence (most powerful)
        if obv_div == "bullish":
            score += 0.35
        elif obv_div == "bearish":
            score -= 0.35

        # MFI extreme + divergence
        if mfi_div == "bullish" or mfi_os:
            score += 0.25
        elif mfi_div == "bearish" or mfi_ob:
            score -= 0.25

        # CMF
        if cmf_strong_bull:
            score += 0.20
        elif cmf_bull:
            score += 0.10
        elif cmf_strong_bear:
            score -= 0.20
        elif cmf_bear:
            score -= 0.10

        # A/D divergence
        if ad_price_div_bull:
            score += 0.15
        elif ad_price_div_bear:
            score -= 0.15

        # OBV trend
        if obv_rising:
            score += 0.10
        else:
            score -= 0.10

        # Volume confirmation
        if capitulation:
            score += 0.20   # sellers exhausted, buyers absorbing
        elif vol_confirms_bull:
            score += 0.10
        elif vol_confirms_bear:
            score -= 0.10
        elif weak_rally:
            score -= 0.08

        if score > 0.1:
            direction  = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, score))
        elif score < -0.1:
            direction  = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(score)))
        else:
            direction  = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="volume",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "obv_rising":         obv_rising,
                "obv_divergence":     obv_div,
                "mfi":                round(mfi, 1),
                "mfi_overbought":     mfi_ob,
                "mfi_oversold":       mfi_os,
                "mfi_divergence":     mfi_div,
                "cmf":                round(cmf, 4),
                "cmf_bull":           cmf_bull,
                "cmf_bear":           cmf_bear,
                "ad_rising":          ad_rising,
                "ad_price_div_bull":  ad_price_div_bull,
                "ad_price_div_bear":  ad_price_div_bear,
                "vol_ratio":          round(vol_ratio, 2),
                "vol_spike":          is_spike,
                "vol_high":           is_high,
                "vol_low":            is_low,
                "capitulation":       capitulation,
                "weak_rally":         weak_rally,
                "vol_confirms_bull":  vol_confirms_bull,
                "vol_confirms_bear":  vol_confirms_bear,
            },
        )
