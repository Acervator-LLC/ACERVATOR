"""``ElidingLabel``, the label the header strip and its cards draw text in."""

from __future__ import annotations

try:
    from PySide6.QtWidgets import QLabel
    from PySide6.QtCore import QSize, Qt

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class ElidingLabel(QLabel):
        """A label that keeps its whole text and draws what the width holds.

        ``sizeHint`` answers the whole text's width while ``minimumSizeHint``
        answers none, so a row gives the label its full room where there is
        room and takes every pixel back where there is not.
        """

        def __init__(self, text: str = "", parent=None):
            super().__init__(parent)
            self._full = str(text)
            self._draw()

        def setText(self, text) -> None:
            """Keep ``text`` whole and draw what the current width holds."""
            self._full = str(text)
            self._draw()

        def fullText(self) -> str:
            """The whole text, whatever the width is drawing of it."""
            return self._full

        def sizeHint(self) -> "QSize":
            """The width the whole text asks for, and the label's own height."""
            hint = super().sizeHint()
            metrics = self.fontMetrics()
            pad = hint.width() - metrics.horizontalAdvance(super().text())
            return QSize(
                metrics.horizontalAdvance(self._full) + max(pad, 0), hint.height()
            )

        def minimumSizeHint(self) -> "QSize":
            """No width floor, so the row can take the label's room back."""
            return QSize(0, super().minimumSizeHint().height())

        def resizeEvent(self, event) -> None:
            """Redraw the whole text at the room the resize gave the label."""
            super().resizeEvent(event)
            self._draw()

        def _draw(self) -> None:
            """Draw the whole text shortened to the width the label has.

            ``setAccessibleName`` carries the whole text, which the drawn
            text no longer holds once a narrow row has shortened it.
            """
            room = max(self.width(), 0)
            super().setText(
                self.fontMetrics().elidedText(self._full, Qt.ElideRight, room)
            )
            self.setAccessibleName(self._full)
