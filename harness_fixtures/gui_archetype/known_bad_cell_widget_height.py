"""A table whose cell buttons are pinned to numbers the row height never gives.

GUI011 refuses this file: ``fire`` is pinned to the literal 22 and ``detail`` to
``BUTTON_HEIGHT_PX``, declared as 22 beside a ``ROW_HEIGHT_PX`` of 36, so each
button falls fourteen pixels short of the cell it is placed in and the row's
selection band paints above and below it.
"""

from typing import Any

#: The height every row of the table is given.
ROW_HEIGHT_PX = 36

#: The height a button in a cell takes, declared without reading the row's.
BUTTON_HEIGHT_PX = 22

FIRE_COLUMN = 8
DETAIL_COLUMN = 9


def declare_row_height(table: Any) -> None:
    """Give every row of ``table`` the declared height."""
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT_PX)


def place_cell_buttons(table: Any, fire: Any, detail: Any, row: int) -> None:
    """Pin both buttons to their own number and place them in ``row``."""
    fire.setFixedHeight(22)
    table.setCellWidget(row, FIRE_COLUMN, fire)

    detail.setFixedHeight(BUTTON_HEIGHT_PX)
    table.setCellWidget(row, DETAIL_COLUMN, detail)
