"""TA011 - fixed-precision rounding of a price.

Assets below about 5e-5 collapse to 0.0, and this fleet holds one
at 0.0000045.
"""
from PySide6.QtGui import QPainter


class PriceTag:
    """Draws a price."""

    def __init__(self, price):
        """Hold the price to draw."""
        self.price = price

    def paintEvent(self, _event):
        """Paint the price."""
        painter = QPainter(self)
        painter.drawText(0, 0, str(round(self.price, 2)))
