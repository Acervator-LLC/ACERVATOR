"""Three grounds for one asset column, each a departure ``GUI010`` names.

``ASSET_COLUMN_GROUND`` holds a hex value no palette token holds,
``asset_cell_skin`` puts ``#555577`` on ``#1a1a28``, and ``ASSET_STATE_GROUNDS``
gives the one column three grounds.
"""

from typing import Any

from PySide6.QtGui import QColor

#: D1 off-palette: no token in the declared palette holds this value, and it
#: stands at no published harmony separation from one.
ASSET_COLUMN_GROUND = "#f7931a"

#: D2 under the floor: this sits on ``#1a1a28`` at 2.42 to 1.
ASSET_MARK_FAINT = "#555577"

#: D3 several grounds: three palette tokens down one column.
ASSET_STATE_GROUNDS = {
    "running": "#1a1a28",
    "paused": "#22223a",
    "stopped": "#2a2a44",
}


def asset_cell_skin() -> str:
    """The declarations one asset cell carries, its ground and its mark colour."""
    return (
        f"QTableWidget::item{{background-color: #1a1a28;"
        f"color: {ASSET_MARK_FAINT};font-size: 11px;}}"
    )


def paint_asset_cell(item: Any) -> None:
    """Put the column ground and its mark colour on ``item``."""
    item.setBackground(QColor(ASSET_COLUMN_GROUND))
