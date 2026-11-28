"""``ZoneTimingRow``, the TA-IVP Timing row the Live, Paper and Simulator panels draw."""

from __future__ import annotations

try:
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:
    from ..tooltips import set_description
    from .eliding_label import ElidingLabel

    TRACK_NAME = "timing-track"
    FILL_NAME = "timing-fill"

    class ZoneTimingRow(QWidget):
        """Draws one ``indicator_panel_surface.timing_payload``: its words, its gap bar and its gap figure."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._layout = QHBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._words = ElidingLabel("")
            self._track = QFrame(self)
            self._track.setObjectName(TRACK_NAME)
            self._fill = QFrame(self._track)
            self._fill.setObjectName(FILL_NAME)
            self._gap = ElidingLabel("")
            self._layout.addWidget(self._words, 1)
            self._layout.addWidget(self._track)
            self._layout.addWidget(self._gap)
            self._row: dict = {}

        def draw(self, row: dict) -> None:
            """Show ``row``'s words, fill, gap figure, colours, tooltip and accessible name."""
            self._row = dict(row)
            self._layout.setSpacing(int(row["spacing_px"]))
            text_sheet = f"color: {row['text_color']}; font-size: {row['font_px']}px;"
            self._words.setStyleSheet(text_sheet)
            self._words.setText(str(row["text"]))
            self._gap.setStyleSheet(text_sheet)
            self._gap.setText(str(row["gap_text"]))
            width = int(row["bar_width_px"])
            height = int(row["bar_height_px"])
            self._track.setFixedSize(width, height)
            self._track.setStyleSheet(
                f"QFrame#{TRACK_NAME} {{ background: {row['track_color']}; border: none; }}"
            )
            self._fill.setGeometry(0, 0, int(row["fill_px"]), height)
            self._fill.setStyleSheet(
                f"QFrame#{FILL_NAME} {{ background: {row['bar_color']}; border: none; }}"
            )
            set_description(self, str(row["tooltip"]))
            self.setAccessibleName(str(row["accessible_name"]))

        def reading(self) -> dict:
            """The words, the gap figure, the fill and track widths and the tooltip this row draws."""
            return {
                "text": self._words.fullText(),
                "gap_text": self._gap.fullText(),
                "fill_px": self._fill.width(),
                "bar_width_px": self._track.width(),
                "tooltip": self.toolTip(),
                "state": str(self._row.get("state", "")),
            }
