"""A table whose cell widgets are sized by numbers the row height never gives.

GUI011 refuses this file: ``fire`` takes the bare 22, ``detail`` takes a
``BUTTON_HEIGHT_PX`` of 22 declared beside a ``ROW_HEIGHT_PX`` of 36, and the
logo square takes 80 by 22, so each one falls short of the cell it sits in and
the row's selection band paints around it.
"""

from typing import Any

#: The height every row of the table is given.
ROW_HEIGHT_PX = 36

#: The height a button in a cell takes, declared without reading the row's.
BUTTON_HEIGHT_PX = 22

LOGO_COLUMN = 0
FIRE_COLUMN = 8
DETAIL_COLUMN = 9


def declare_row_height(table: Any) -> None:
    """Give every row of ``table`` the declared height."""
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT_PX)


def place_cell_buttons(table: Any, fire: Any, detail: Any, row: int) -> None:
    """Size both buttons by their own number and place them in ``row``."""
    fire.setFixedHeight(22)
    table.setCellWidget(row, FIRE_COLUMN, fire)

    detail.setFixedHeight(BUTTON_HEIGHT_PX)
    table.setCellWidget(row, DETAIL_COLUMN, detail)


def place_cell_logo(table: Any, logo: Any, row: int) -> None:
    """Size the logo square by its own two numbers and place it in ``row``."""
    logo.setFixedSize(80, 22)
    table.setCellWidget(row, LOGO_COLUMN, logo)
