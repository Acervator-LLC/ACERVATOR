"""John Bollinger's bands, and the vote the engine casts on them."""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
    Candle,
)
from .helpers import (
    _sma_tail,
    _stdev_tail,
    _window_has_no_range,
)

#: ``(upper, middle, lower)`` for one candle, or ``None`` before the
#: window closes -- see ``BollingerBands.bands``.
_Band = tuple[float, float, float] | None


class BollingerBands:
    """A voting indicator over Bollinger's bands, and the band series itself.

    ``bands`` draws the envelope one entry per candle for the chart.
    ``compute`` returns the vote ``VotingEngine.compute_all`` collects: a
    close near the lower band is bullish (oversold), near the upper band
    bearish (overbought), and a band narrow beside its own recent history
    damps whichever vote it produced.
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0, weight: float = 1.0):
        self.period = period
        self.std_dev = std_dev
        self.weight = weight

    def bands(self, candles: list[Candle]) -> list[_Band]:
        """Upper, middle and lower band, ONE ENTRY PER CANDLE.

        THE PUBLISHED DEFINITION. Bollinger, and StockCharts
        reproducing him:

            Middle Band = SMA(period)
            Upper Band  = Middle + std_dev * sigma(period)
            Lower Band  = Middle - std_dev * sigma(period)

        with sigma the POPULATION deviation over the same window --
        ``helpers._stdev_tail``, the one this package already uses.

        NO BAND BEFORE THE WINDOW CLOSES. A 20-period band needs 20
        closes, so entries below ``period - 1`` are ``None``.
        ``_sma_tail`` and ``_stdev_tail`` keep their own lists
        candle-aligned by averaging however many closes they have at
        those indices; no band is built from one of those entries.

        ``CandlestickChart`` in ``native_chart.py`` draws this series.
        """
        closes = [c.close for c in candles]
        sma = _sma_tail(closes, self.period, tail=None)
        std = _stdev_tail(closes, self.period, tail=None)
        out: list[_Band] = [None] * len(closes)
        for i in range(self.period - 1, len(closes)):
            mid = sma[i]
            out[i] = (
                mid + self.std_dev * std[i],
                mid,
                mid - self.std_dev * std[i],
            )
        return out

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        """Vote on where the last close sits inside the bands.

        Abstains below ``period`` closes and on a window with no range.
        ``details`` carries the three bands, %B, BandWidth and the
        squeeze flag, which ``VotingEngine.compute_all`` records per
        candle and ``detect_volume_confirmed_spring`` reads.
        """
        closes = [c.close for c in candles]
        if len(closes) < self.period:
            return Signal(
                "bollinger_bands",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        # `self.period` is the exact depth read below, and it comes from
        # config, not a module default.
        sma = _sma_tail(closes, self.period, tail=self.period)
        std = _stdev_tail(closes, self.period, tail=self.period)

        mid = sma[-1]
        upper = mid + self.std_dev * std[-1]
        lower = mid - self.std_dev * std[-1]
        price = closes[-1]
        band_width = (upper - lower) / (mid + 1e-9)

        # The history starts at the first closed window; below
        # `period - 1` the helpers hold no band.
        widths = [
            # Spelt out, not folded to `2 * std_dev * std[i]`, to keep
            # `band_width`'s float operation order.
            ((sma[i] + self.std_dev * std[i]) - (sma[i] - self.std_dev * std[i]))
            / (sma[i] + 1e-9)
            for i in range(max(self.period - 1, len(sma) - self.period), len(sma))
        ]
        # Both sides of the comparison are BandWidths over the midline,
        # so the flag is free of the asset's price scale.
        width_count = len(widths)
        avg_width = sum(widths) / width_count if width_count else band_width
        squeeze = band_width < avg_width * 0.75

        # Tested on the closes: sigma over a halted window rounds to ULPs,
        # so `upper - lower` does not reach zero.
        if _window_has_no_range(closes[-self.period :]) or upper - lower <= 0.0:
            return Signal(
                "bollinger_bands",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        # %B: 0 at the lower band, 1 at the upper, outside [0, 1] beyond them.
        bb_pos = (price - lower) / (upper - lower + 1e-9)

        direction = SignalDirection.NEUTRAL
        confidence = 0.0

        if bb_pos < 0.15:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, (0.15 - bb_pos) / 0.15 * 0.8 + 0.3))
        elif bb_pos > 0.85:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, (bb_pos - 0.85) / 0.15 * 0.8 + 0.3))
        elif bb_pos < 0.35:
            direction = SignalDirection.BULLISH
            confidence = 0.2
        elif bb_pos > 0.65:
            direction = SignalDirection.BEARISH
            confidence = 0.2

        if squeeze:
            confidence *= 0.7

        return Signal(
            indicator="bollinger_bands",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "upper": round(upper, 6),
                "middle": round(mid, 6),
                "lower": round(lower, 6),
                "bb_position": round(bb_pos, 4),
                "band_width": round(band_width, 6),
                "squeeze": squeeze,
            },
        )
