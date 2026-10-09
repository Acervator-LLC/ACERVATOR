"""A table whose cell buttons are pinned from the row height it declares.

GUI011 passes this file: both pins read ``BUTTON_HEIGHT_PX``, which is declared
from ``ROW_HEIGHT_PX``, so neither button carries a number of its own and both
fill their cell at whatever height the rows are given.
"""

from typing import Any

#: The height every row of the table is given.
ROW_HEIGHT_PX = 36

#: The height a button in a cell takes, read from the row's own height.
BUTTON_HEIGHT_PX = ROW_HEIGHT_PX

FIRE_COLUMN = 8
DETAIL_COLUMN = 9


def declare_row_height(table: Any) -> None:
    """Give every row of ``table`` the declared height."""
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT_PX)


def place_cell_buttons(table: Any, fire: Any, detail: Any, row: int) -> None:
    """Pin both buttons to the row height and place them in ``row``."""
    fire.setFixedHeight(BUTTON_HEIGHT_PX)
    table.setCellWidget(row, FIRE_COLUMN, fire)

    detail.setFixedHeight(BUTTON_HEIGHT_PX)
    table.setCellWidget(row, DETAIL_COLUMN, detail)
