"""TA010 - range normalisation with no zero guard.

A flat series is a real market state, and it divides by zero here.
"""

from PySide6.QtGui import QPainter


class Sparkline:
    """Draws a series."""

    def __init__(self, series):
        """Hold the series to draw."""
        self.series = list(series)

    def paintEvent(self, _event):
        """Paint the series."""
        painter = QPainter(self)
        hi, lo = max(self.series), min(self.series)
        for value in self.series:
            y = (value - lo) / (hi - lo)
            painter.drawPoint(0, int(y))
