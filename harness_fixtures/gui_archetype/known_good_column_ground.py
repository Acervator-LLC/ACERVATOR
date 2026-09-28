"""One ground for the asset column, the value ``SURFACE_2`` holds.

``ASSET_COLUMN_GROUND`` names it once, ``asset_cell_skin`` writes it under every
state, and ``paint_asset_cell`` hands the same ground to every cell.
"""

from typing import Any

from PySide6.QtGui import QColor

#: The one ground every asset cell draws on, the value ``SURFACE_2`` holds.
ASSET_COLUMN_GROUND = "#1a1a28"

#: The colours the column draws on that ground, ``TEXT_HIGH`` and ``PRIMARY``.
ASSET_MARK_PLAIN = "#e0e0f0"
ASSET_MARK_ACCENT = "#00ffcc"

#: Every state names the one ground, so the set holds a single colour.
ASSET_STATE_GROUNDS = {
    "running": ASSET_COLUMN_GROUND,
    "paused": ASSET_COLUMN_GROUND,
    "stopped": ASSET_COLUMN_GROUND,
}


def asset_cell_skin() -> str:
    """The declarations one asset cell carries, its ground and its mark colour."""
    return (
        f"QTableWidget::item{{background-color: {ASSET_COLUMN_GROUND};"
        f"color: {ASSET_MARK_PLAIN};font-size: 11px;}}"
        f"QTableWidget::item:selected{{background-color: {ASSET_COLUMN_GROUND};"
        f"color: {ASSET_MARK_ACCENT};}}"
    )


def paint_asset_cell(item: Any) -> None:
    """Put the one column ground and its mark colour on ``item``."""
    item.setBackground(QColor(ASSET_COLUMN_GROUND))
    item.setForeground(QColor(ASSET_MARK_PLAIN))
