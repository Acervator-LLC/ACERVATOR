"""Relative Strength Index (Wilder, 14-period).

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)


class RSIIndicator:
    """Relative Strength Index (Wilder 14-period) with divergence detection.

    v3.19.18: refactored from dict-returning to Signal-returning compute()
    so it can be wired into VotingEngine. Closes the last UNWIRED indicator
    from the v3.19.16 indicator-coverage audit. The dict-form metrics are
    still available via ``_compute_metrics()`` for any consumer that needs
    the rich detail.

    Used for:
      - Overbought (>70) / oversold (<30) regime signals
      - Bullish divergence (price new low, RSI higher low) = fold boost
      - Bearish divergence (price new high, RSI lower high) = scrum boost

    Signal mapping (v3.19.18):
      RSI > 70  → BEARISH (classical overbought; SCRUM-eligible signal)
      RSI < 30  → BULLISH (classical oversold; FOLD-eligible signal)
      else      → NEUTRAL
    Confidence scaled by distance from the neutral 50 line; divergence
    boosts confidence by +0.15 (capped at 1.0). Plain RSI is weighted
    lower (0.8) in VotingEngine than StochasticRSI (1.0) since StochRSI
    is the more refined two-stage indicator and they overlap.
    """
    def __init__(self, period: int = 14, weight: float = 0.8):
        self.period = period
        self.weight = weight

    def _compute_metrics(self, candles: list) -> dict:
        """Compute the rich-detail RSI dict. Pre-v3.19.18 callers used
        this signature (with the public name ``compute``). Now private,
        retained for any consumer needing the divergence / series detail."""
        if len(candles) < self.period + 1:
            # `rs_indeterminate` is False here on purpose: this is the
            # warm-up path, not a degenerate one. The rsi = 50.0 it
            # already returns maps to NEUTRAL at confidence 0.0, so the
            # behaviour of this branch is untouched.
            return {"rsi": 50.0, "overbought": False, "oversold": False,
                    "bull_div": False, "bear_div": False, "rsi_series": [],
                    "rs_indeterminate": False}
        closes = [c.close for c in candles]
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains  = [max(d, 0) for d in deltas]
        losses = [max(-d, 0) for d in deltas]
        avg_gain = sum(gains[:self.period]) / self.period
        avg_loss = sum(losses[:self.period]) / self.period
        rsi_series = []
        rs_indeterminate = False
        for i in range(self.period, len(deltas)):
            avg_gain = (avg_gain * (self.period - 1) + gains[i]) / self.period
            avg_loss = (avg_loss * (self.period - 1) + losses[i]) / self.period
            # Wilder's RS with no losses but SOME gains is an infinite
            # ratio, i.e. RSI 100, and that case is defined and left
            # alone. With neither gains nor losses it is 0/0. Resolved
            # through the epsilon that gave rs = 0.0 and rsi EXACTLY 0.0
            # -- the bottom of the scale -- which the mapping below reads
            # as maximum oversold and votes BULLISH at confidence 1.0000.
            rs_indeterminate = avg_gain <= 0.0 and avg_loss <= 0.0
            rs  = avg_gain / (avg_loss + 1e-9)
            rsi_series.append(100 - 100 / (1 + rs))
        rsi = rsi_series[-1] if rsi_series else 50.0
        # Divergence: compare last 2 swing lows/highs
        bull_div = bear_div = False
        if len(rsi_series) >= 20 and len(closes) >= 20:
            p_lo1 = min(closes[-20:-10]); p_lo2 = min(closes[-10:])
            r_lo1 = min(rsi_series[-20:-10]); r_lo2 = min(rsi_series[-10:])
            bull_div = p_lo2 < p_lo1 and r_lo2 > r_lo1  # price lower, RSI higher
            p_hi1 = max(closes[-20:-10]); p_hi2 = max(closes[-10:])
            r_hi1 = max(rsi_series[-20:-10]); r_hi2 = max(rsi_series[-10:])
            bear_div = p_hi2 > p_hi1 and r_hi2 < r_hi1  # price higher, RSI lower
        return {
            "rsi":        round(rsi, 2),
            "rs_indeterminate": rs_indeterminate,
            "overbought": rsi > 70,
            "oversold":   rsi < 30,
            "bull_div":   bull_div,
            "bear_div":   bear_div,
            "rsi_series": rsi_series[-20:],  # last 20 values for chart overlay
        }

    def compute(self, candles: list, timeframe: str = "1h") -> "Signal":
        """v3.19.18 — Signal-returning compute() matching the VotingEngine
        protocol used by every other voter.

        Classical Wilder mapping:
          rsi > 70 → BEARISH (overbought)
          rsi < 30 → BULLISH (oversold)
          else     → NEUTRAL
        Confidence: scaled by absolute distance from the neutral 50 line,
        normalized so |rsi-50|=20 (i.e. crossing the 70 or 30 threshold)
        gives baseline confidence 0.4; saturates near 1.0 at the extremes.
        Divergence adds +0.15 to confidence (capped at 1.0).
        """
        metrics = self._compute_metrics(candles)
        if metrics["rs_indeterminate"]:
            return Signal("rsi", timeframe,
                          SignalDirection.NEUTRAL, 0.0, self.weight)
        rsi = metrics["rsi"]

        # Direction
        if rsi > 70:
            direction = SignalDirection.BEARISH
        elif rsi < 30:
            direction = SignalDirection.BULLISH
        else:
            direction = SignalDirection.NEUTRAL

        # Confidence — distance from neutral, scaled so a threshold cross
        # (|rsi-50|=20) starts producing meaningful signal
        dist = abs(rsi - 50.0)
        if dist <= 20.0:
            confidence = (dist / 20.0) * 0.4   # 0 at center, 0.4 at threshold
        else:
            # Beyond the threshold: linear ramp to ~1.0 at the extremes
            confidence = 0.4 + ((dist - 20.0) / 30.0) * 0.6
        confidence = min(1.0, max(0.0, confidence))

        # Divergence boost
        if metrics["bull_div"] and direction == SignalDirection.BULLISH:
            confidence = max(0.0, min(1.0, confidence + 0.15))
        elif metrics["bear_div"] and direction == SignalDirection.BEARISH:
            confidence = max(0.0, min(1.0, confidence + 0.15))

        # NEUTRAL signals have zero confidence by VotingEngine convention
        if direction == SignalDirection.NEUTRAL:
            confidence = 0.0

        return Signal(
            indicator="rsi",
            timeframe=timeframe,
            direction=direction,
            confidence=round(confidence, 4),
            weight=self.weight,
            details={
                "rsi":        rsi,
                "overbought": metrics["overbought"],
                "oversold":   metrics["oversold"],
                "bull_div":   metrics["bull_div"],
                "bear_div":   metrics["bear_div"],
            },
        )
