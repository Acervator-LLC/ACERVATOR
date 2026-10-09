"""A table whose cell widgets take their size from the row height it declares.

GUI011 passes this file: ``BUTTON_HEIGHT_PX`` is declared from
``ROW_HEIGHT_PX``, and the logo square reads ``ROW_HEIGHT_PX`` itself, so no
cell widget carries a number of its own and each fills its cell at whatever
height the rows are given.
"""

from typing import Any

#: The height every row of the table is given.
ROW_HEIGHT_PX = 36

#: The height a button in a cell takes, read from the row's own height.
BUTTON_HEIGHT_PX = ROW_HEIGHT_PX

LOGO_COLUMN = 0
FIRE_COLUMN = 8
DETAIL_COLUMN = 9


def declare_row_height(table: Any) -> None:
    """Give every row of ``table`` the declared height."""
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT_PX)


def place_cell_buttons(table: Any, fire: Any, detail: Any, row: int) -> None:
    """Size both buttons from the row height and place them in ``row``."""
    fire.setFixedHeight(BUTTON_HEIGHT_PX)
    table.setCellWidget(row, FIRE_COLUMN, fire)

    detail.setFixedHeight(BUTTON_HEIGHT_PX)
    table.setCellWidget(row, DETAIL_COLUMN, detail)


def place_cell_logo(table: Any, logo: Any, row: int) -> None:
    """Size the logo square from ``ROW_HEIGHT_PX`` and place it in ``row``."""
    logo.setFixedSize(ROW_HEIGHT_PX, ROW_HEIGHT_PX)
    table.setCellWidget(row, LOGO_COLUMN, logo)
