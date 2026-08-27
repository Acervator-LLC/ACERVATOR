"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
widgets.py — shared themed widgets for src/gui/
===============================================

Holds `StatCard`, the label-above-value card the stock window and the
analytics tab render, and `ColumnarTableWidget`, the column setup the
three bot tables share. Each caller passes a frozen preset built from
`design_system` tokens, so one class carries every skin and no widget
repeats a hex literal.

The frame stylesheet is keyed on the runtime class name, so a Qt type
selector written against a subclass still matches its instances.

`main_window.StatCard` is a third card of this shape and does NOT
subclass this one: it adds methods that reach inherited Qt attributes,
and the scaffolding rule resolves a base class only within one module,
so a cross-module base costs 7 S003 findings on that file.

The cost is specific to a subclass sharing its base's name. S003 skips
a class whose base it cannot resolve, and resolves an aliased base back
to the real name, which then matches the same-named local class. The
tables below subclass `ColumnarTableWidget` under their own names and
draw no findings.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QLabel,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from . import design_system as ds

_NO_COLUMN_MAP: Mapping[int, str] = MappingProxyType({})
_NO_WIDTH_MAP: Mapping[int, int] = MappingProxyType({})


@dataclass(frozen=True)
class CardStyle:
    """Colors, type sizes and spacing for one `StatCard` skin.

    `surface` of None emits no frame stylesheet, leaving the application
    stylesheet to paint the card.
    """

    label_color: str
    value_color: str
    label_size: int = ds.TYPE_CAPTION
    value_size: int = ds.TYPE_CARD_VALUE
    padding: tuple[int, int, int, int] = (
        ds.SPACE_S,
        ds.SPACE_S,
        ds.SPACE_S,
        ds.SPACE_S,
    )
    spacing: int = ds.SPACE_XXS
    surface: Optional[str] = None
    border: Optional[str] = None
    radius: int = ds.RADIUS_SM
    accessible_name: str = "Stat Card"


STOCK_CARD = CardStyle(
    label_color=ds.CARD_STOCK_LABEL,
    value_color=ds.CARD_STOCK_VALUE,
    padding=(
        ds.SPACE_CARD_PAD,
        ds.SPACE_CARD_TIGHT,
        ds.SPACE_CARD_PAD,
        ds.SPACE_CARD_TIGHT,
    ),
    surface=ds.CARD_STOCK_SURFACE,
    border=ds.CARD_STOCK_BORDER,
    radius=ds.RADIUS_SM,
    accessible_name="Stock Stat Card",
)
"""Stock window stat strip."""

METRIC_CARD = CardStyle(
    label_color=ds.CARD_METRIC_LABEL,
    value_color=ds.TEXT_HIGH,
    padding=(
        ds.SPACE_CARD_TIGHT,
        ds.SPACE_S,
        ds.SPACE_CARD_TIGHT,
        ds.SPACE_S,
    ),
    surface=ds.CARD_METRIC_SURFACE,
    border=ds.CARD_METRIC_BORDER,
    radius=ds.RADIUS_CARD,
    accessible_name="Metric Card",
)
"""Analytics tab metric grid."""


class StatCard(QFrame):
    """A label above a value, themed by a `CardStyle`.

    Subclasses set `STYLE` or pass `style=`. `set_value` accepts a
    per-call color that overrides the skin's `value_color`.
    """

    STYLE = CardStyle(label_color=ds.TEXT_MED, value_color=ds.TEXT_HIGH)

    def __init__(
        self,
        label: str,
        value: str = "---",
        parent: Optional[QWidget] = None,
        style: Optional[CardStyle] = None,
    ) -> None:
        super().__init__(parent)
        self._style = style or self.STYLE
        self.setAccessibleName(self._style.accessible_name)
        self.setFrameShape(QFrame.StyledPanel)
        if self._style.surface is not None:
            self.setStyleSheet(
                f"{type(self).__name__} {{ background: {self._style.surface}; "
                f"border: 1px solid {self._style.border}; "
                f"border-radius: {self._style.radius}px; }}"
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*self._style.padding)
        layout.setSpacing(self._style.spacing)

        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"color: {self._style.label_color}; "
            f"font-size: {self._style.label_size}px;"
        )

        self._value = QLabel(value)
        self._apply_value_style(self._style.value_color)

        layout.addWidget(self._label)
        layout.addWidget(self._value)

    def _apply_value_style(self, color: str) -> None:
        self._value.setStyleSheet(
            f"color: {color}; "
            f"font-size: {self._style.value_size}px; "
            f"font-weight: bold;"
        )

    def set_value(self, value: str, color: Optional[str] = None) -> None:
        """Show `value`. `color` overrides the skin's value color for this
        call only; the type size and weight are unchanged."""
        self._value.setText(str(value))
        self._apply_value_style(color or self._style.value_color)


@dataclass(frozen=True)
class ColumnSpec:
    """Header labels, header tooltips and fixed widths for one table.

    A column absent from `fixed_widths` stretches. An empty
    `accessible_name` leaves the widget's name unset.
    """

    labels: tuple[str, ...]
    tooltips: Mapping[int, str] = _NO_COLUMN_MAP
    fixed_widths: Mapping[int, int] = _NO_WIDTH_MAP
    accessible_name: str = ""


class ColumnarTableWidget(QTableWidget):
    """A read-only, row-selecting table whose columns come from a `ColumnSpec`.

    Subclasses set `COLUMN_SPEC` or pass `spec=`, then add their own
    `update_bots` and signal wiring. The vertical header is hidden and
    rows alternate colour.
    """

    COLUMN_SPEC = ColumnSpec(labels=())

    def __init__(
        self,
        spec: Optional[ColumnSpec] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        columns = spec or self.COLUMN_SPEC
        self._column_spec = columns
        if columns.accessible_name:
            self.setAccessibleName(columns.accessible_name)
        self.setColumnCount(len(columns.labels))
        self.setHorizontalHeaderLabels(list(columns.labels))
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        for col, width in columns.fixed_widths.items():
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.setColumnWidth(col, width)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        for col, tip in columns.tooltips.items():
            item = self.horizontalHeaderItem(col)
            if item:
                item.setToolTip(tip)


__all__ = [
    "CardStyle",
    "ColumnSpec",
    "ColumnarTableWidget",
    "METRIC_CARD",
    "STOCK_CARD",
    "StatCard",
]
