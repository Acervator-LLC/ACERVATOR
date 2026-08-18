"""The TA011 body, corrected: no fixed-precision price round."""
from PySide6.QtGui import QPainter


class PriceTag:
    """Draws a price."""

    def __init__(self, price):
        """Hold the price to draw."""
        self.price = price

    def paintEvent(self, _event):
        """Paint the price."""
        painter = QPainter(self)
        painter.drawText(0, 0, f"{self.price:.10g}")
