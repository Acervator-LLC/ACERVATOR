"""``FittedLabel``, the label a money amount is drawn in."""

from __future__ import annotations

try:
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QFont, QFontMetrics

    from .eliding_label import ElidingLabel

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class FittedLabel(ElidingLabel):
        """An ``ElidingLabel`` that shrinks its text to fit before shortening it.

        ``set_skin`` holds the colour and the weight, and ``_draw`` appends
        the largest size from ``declared_px`` down to ``floor_px`` that fits.
        """

        #: Read while ``ElidingLabel.__init__`` draws, before ``__init__``
        #: has set this label's own sizes.
        _declared_px = 14
        _floor_px = 10
        _fitted_px = 14
        _skin = ""
        _weight = "bold"
        _drawing = False

        def __init__(
            self, text="", declared_px=14, floor_px=10, parent=None, weight="bold"
        ):
            super().__init__("", parent)
            self._declared_px = int(declared_px)
            self._floor_px = int(floor_px)
            self._fitted_px = int(declared_px)
            self._skin = ""
            self._weight = str(weight)
            self._drawing = False
            self.setText(text)

        def set_skin(self, skin: str) -> None:
            """Hold ``skin``, which carries no size, and redraw at the fitted size."""
            self._skin = str(skin)
            self._draw()

        def fittedSize(self) -> int:
            """The pixel size the text is currently drawn at."""
            return self._fitted_px

        def declaredSize(self) -> int:
            """The pixel size the text draws at where the width allows it."""
            return self._declared_px

        def sizeHint(self) -> "QSize":
            """The room the whole text needs at ``_declared_px``, and that size's
            own height.

            Measured at the declared size and never at the fitted one: a hint
            read off the shrunk font asks for the width the shrunk font needs,
            so the label never grows back when the row widens. The row divides
            its height from this, so a shrunk amount never moves its line.
            """
            hint = super().sizeHint()
            pad = hint.width() - self.fontMetrics().horizontalAdvance(self.fullText())
            return QSize(
                self._advance_at(self._declared_px) + max(pad, 0),
                self._declared_height(),
            )

        def minimumSizeHint(self) -> "QSize":
            """No width floor, and the height ``_declared_px`` has."""
            return QSize(0, self._declared_height())

        def _sized_font(self, size_px) -> "QFont":
            """This label's font at ``size_px``, at the weight it draws in.

            The advance a style sheet's weight produces is wider than the
            default one, so a reading taken at the default weight over-fits.
            """
            font = QFont(self.font())
            font.setPixelSize(int(size_px))
            font.setWeight(
                QFont.Weight.Bold if self._weight == "bold" else QFont.Weight.DemiBold
            )
            return font

        def _declared_height(self) -> int:
            """The line height ``_declared_px`` draws at in this font."""
            return QFontMetrics(self._sized_font(self._declared_px)).height()

        def _advance_at(self, size_px) -> int:
            """The width the whole text draws at ``size_px`` in this font."""
            return QFontMetrics(self._sized_font(size_px)).horizontalAdvance(
                self.fullText()
            )

        def _fitted_for(self, room: int) -> int:
            """The largest size from ``_declared_px`` down that fits ``room``."""
            for size_px in range(self._declared_px, self._floor_px - 1, -1):
                if self._advance_at(size_px) <= room:
                    return size_px
            return self._floor_px

        def _draw(self) -> None:
            """Apply the size that fits, then shorten whatever still overflows."""
            if self._drawing:
                return
            self._drawing = True
            try:
                room = max(self.width(), 0)
                self._fitted_px = self._fitted_for(room)
                wanted = (
                    f"{self._skin} font-size: {self._fitted_px}px; "
                    f"font-weight: {self._weight};"
                )
                if self._skin and self.styleSheet() != wanted:
                    self.setStyleSheet(wanted)
                super(ElidingLabel, self).setText(
                    self.fontMetrics().elidedText(self.fullText(), Qt.ElideRight, room)
                )
                self.setAccessibleName(self.fullText())
            finally:
                self._drawing = False
