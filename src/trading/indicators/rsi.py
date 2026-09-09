"""Relative Strength Index.

``RSIIndicator.compute`` casts the vote; ``RSIIndicator._compute_metrics``
carries the divergence flags and the trailing series.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)


class RSIIndicator:
    """Wilder RSI with divergence detection.

    ``compute`` returns a ``Signal``: RSI above 70 is BEARISH, below 30 is
    BULLISH, otherwise NEUTRAL. ``period`` and ``weight`` default to 14 and
    0.8.
    """

    def __init__(self, period: int = 14, weight: float = 0.8):
        self.period = period
        self.weight = weight

    def _compute_metrics(self, candles: list) -> dict:
        """Return the RSI value, its overbought/oversold flags, both
        divergence flags and the trailing series.

        ``rs_indeterminate`` is True when the last bar has neither gains nor
        losses.
        """
        if len(candles) < self.period + 1:
            return {
                "rsi": 50.0,
                "overbought": False,
                "oversold": False,
                "bull_div": False,
                "bear_div": False,
                "rsi_series": [],
                "rs_indeterminate": False,
            }
        closes = [c.close for c in candles]
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        # `losses` are positive magnitudes; the leading float zero keeps
        # `max` at +0.0 on a flat bar.
        gains = [max(0.0, d) for d in deltas]
        losses = [max(0.0, -d) for d in deltas]
        avg_gain = sum(gains[: self.period]) / self.period
        avg_loss = sum(losses[: self.period]) / self.period
        rsi_series = []
        rs_indeterminate = False
        for i in range(self.period, len(deltas)):
            avg_gain = (avg_gain * (self.period - 1) + gains[i]) / self.period
            avg_loss = (avg_loss * (self.period - 1) + losses[i]) / self.period
            rs_indeterminate = avg_gain <= 0.0 and avg_loss <= 0.0
            if avg_loss > 0.0:
                rsi_series.append(100 - 100 / (1 + avg_gain / avg_loss))
            else:
                # Wilder: a zero `avg_loss` with any gain is an infinite RS,
                # i.e. RSI 100.
                rsi_series.append(100.0 if avg_gain > 0.0 else 0.0)
        rsi = rsi_series[-1] if rsi_series else 50.0
        bull_div = bear_div = False
        if len(rsi_series) >= 20 and len(closes) >= 20:
            p_lo1 = min(closes[-20:-10])
            p_lo2 = min(closes[-10:])
            r_lo1 = min(rsi_series[-20:-10])
            r_lo2 = min(rsi_series[-10:])
            bull_div = p_lo2 < p_lo1 and r_lo2 > r_lo1
            p_hi1 = max(closes[-20:-10])
            p_hi2 = max(closes[-10:])
            r_hi1 = max(rsi_series[-20:-10])
            r_hi2 = max(rsi_series[-10:])
            bear_div = p_hi2 > p_hi1 and r_hi2 < r_hi1
        return {
            "rsi": rsi,
            "rs_indeterminate": rs_indeterminate,
            "overbought": rsi > 70,
            "oversold": rsi < 30,
            "bull_div": bull_div,
            "bear_div": bear_div,
            "rsi_series": rsi_series[-20:],
        }

    def compute(self, candles: list, timeframe: str = "1h") -> "Signal":
        """Return the RSI ``Signal`` for ``candles``.

        ``confidence`` scales with the distance of ``rsi`` from 50, reaching
        0.4 at the 70 and 30 thresholds and 1.0 at the extremes; a matching
        divergence adds 0.15.
        """
        metrics = self._compute_metrics(candles)
        if metrics["rs_indeterminate"]:
            return Signal(
                "rsi",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )
        rsi = metrics["rsi"]

        # `_compute_metrics` returns a placeholder 50.0 below `period` + 1
        # candles; `len(candles)` is the warm-up test.
        warming_up = len(candles) < self.period + 1

        if rsi > 70:
            direction = SignalDirection.BEARISH
        elif rsi < 30:
            direction = SignalDirection.BULLISH
        else:
            direction = SignalDirection.NEUTRAL

        dist = abs(rsi - 50.0)
        if dist <= 20.0:
            confidence = (dist / 20.0) * 0.4
        else:
            confidence = 0.4 + ((dist - 20.0) / 30.0) * 0.6
        confidence = min(1.0, max(0.0, confidence))

        if metrics["bull_div"] and direction == SignalDirection.BULLISH:
            confidence = max(0.0, min(1.0, confidence + 0.15))
        elif metrics["bear_div"] and direction == SignalDirection.BEARISH:
            confidence = max(0.0, min(1.0, confidence + 0.15))

        # A NEUTRAL vote carries no confidence into `VotingEngine`.
        if direction == SignalDirection.NEUTRAL:
            confidence = 0.0

        return Signal(
            indicator="rsi",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "rsi": rsi,
                "overbought": metrics["overbought"],
                "oversold": metrics["oversold"],
                "bull_div": metrics["bull_div"],
                "bear_div": metrics["bear_div"],
            },
            abstained=warming_up,
        )
