# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Status tab drawn by Qt widgets.

``SystemStatusQtTab`` asks ``system_status_tab_surface.view_model`` for the
Watchdog's read-out and lays it out as the heading, the feed line, the totals,
the legend, one panel per subsystem with that subsystem's emitter table, and one
group per tab. Every word comes from the surface module and every colour from
``design_system``.
"""

from __future__ import annotations

from typing import Any

from . import design_system as ds
from .main_tabs import system_status_tab_surface as surface

ACCESSIBLE_NAME = surface.HEADING

#: The value a cell draws where the read-out holds none.
BLANK_VALUE = ""

HEADER_BAR_STYLE = (
    f"QWidget{{background:{ds.MAIN_TOOLBAR_SURFACE};"
    f"border-bottom:1px solid {ds.MAIN_SEPARATOR};}}"
)

HEADING_STYLE = (
    f"QLabel{{background:{ds.MAIN_TOOLBAR_SURFACE};color:{ds.TEXT_MAX};"
    f"font-size:{ds.TYPE_H2}px;font-weight:{ds.WEIGHT_BOLD};}}"
)

FEED_STYLE = (
    f"QLabel{{background:{ds.MAIN_TOOLBAR_SURFACE};color:{ds.TEXT_MED};"
    f"font-size:{ds.TYPE_SMALL}px;}}"
)

LEGEND_STYLE = (
    f"QLabel{{background:{ds.SURFACE_CHART};color:{ds.TEXT_LOW};"
    f"font-size:{ds.TYPE_SMALL}px;"
    f"padding:{ds.SPACE_S}px {ds.SPACE_M}px;}}"
)

BODY_STYLE = f"QWidget{{background:{ds.SURFACE_CHART};}}"

#: A container that carries no ground of its own, so the panel behind it shows.
INNER_STYLE = "QWidget{background:transparent;}"

SCROLL_STYLE = f"QScrollArea{{background:{ds.SURFACE_CHART};border:none;}}"

SECTION_STYLE = (
    f"QLabel{{background:{ds.SURFACE_CHART};color:{ds.PRIMARY};"
    f"font-size:{ds.TYPE_H4}px;font-weight:{ds.WEIGHT_BOLD};}}"
)

#: QLabel is a QFrame, so the panel and the chip rules name their own object
#: and never reach the labels inside them.
PANEL_OBJECT = "statusPanel"
CHIP_OBJECT = "statusChip"

PANEL_STYLE = (
    f"QFrame#{PANEL_OBJECT}{{background:{ds.SURFACE_1};"
    f"border:1px solid {ds.OUTLINE};border-radius:{ds.RADIUS_SM}px;}}"
)

PANEL_NAME_STYLE = (
    f"QLabel{{background:{ds.SURFACE_1};color:{ds.TEXT_MAX};"
    f"font-size:{ds.TYPE_H4}px;font-weight:{ds.WEIGHT_BOLD};}}"
)

PANEL_TAB_STYLE = (
    f"QLabel{{background:{ds.SURFACE_1};color:{ds.TEXT_MED};"
    f"font-size:{ds.TYPE_SMALL}px;}}"
)

CHIP_STYLE = (
    f"QFrame#{CHIP_OBJECT}{{background:{ds.SURFACE_2};"
    f"border-radius:{ds.RADIUS_XS}px;}}"
)

CHIP_LABEL_STYLE = (
    f"QLabel{{background:{ds.SURFACE_2};color:{ds.TEXT_MED};"
    f"font-size:{ds.TYPE_SMALL}px;}}"
)

CHIP_VALUE_STYLE = (
    f"QLabel{{background:{ds.SURFACE_2};color:{ds.TEXT_HIGH};"
    f"font-size:{ds.TYPE_SMALL}px;font-weight:{ds.WEIGHT_BOLD};}}"
)

COLUMN_HEAD_STYLE = (
    f"QLabel{{background:{ds.SURFACE_2};color:{ds.MAIN_TABLE_HEADER};"
    f"font-size:{ds.TYPE_SMALL}px;font-weight:{ds.WEIGHT_BOLD};"
    f"padding:{ds.SPACE_XXS}px {ds.SPACE_XS}px;}}"
)

CELL_STYLE = (
    f"QLabel{{background:{ds.SURFACE_1};color:{ds.TEXT_MED};"
    f"font-size:{ds.TYPE_SMALL}px;padding:{ds.SPACE_XXS}px {ds.SPACE_XS}px;}}"
)

CELL_NAME_STYLE = (
    f"QLabel{{background:{ds.SURFACE_1};color:{ds.TEXT_HIGH};"
    f"font-size:{ds.TYPE_SMALL}px;padding:{ds.SPACE_XXS}px {ds.SPACE_XS}px;}}"
)

HEALTH_GREEN_STYLE = (
    f"QLabel{{background:{ds.SURFACE_1};color:{ds.SUCCESS};"
    f"font-size:{ds.TYPE_SMALL}px;font-weight:{ds.WEIGHT_BOLD};}}"
)

HEALTH_YELLOW_STYLE = (
    f"QLabel{{background:{ds.SURFACE_1};color:{ds.WARNING};"
    f"font-size:{ds.TYPE_SMALL}px;font-weight:{ds.WEIGHT_BOLD};}}"
)

HEALTH_QUIET_STYLE = (
    f"QLabel{{background:{ds.SURFACE_1};color:{ds.TEXT_LOW};"
    f"font-size:{ds.TYPE_SMALL}px;}}"
)

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    _HAS_QT = True
except ImportError:
    # Without Qt, SystemStatusQtTab is never defined and its import fails by name.
    _HAS_QT = False


if _HAS_QT:

    from src.core.signal_contract import HEALTH_GREEN, HEALTH_YELLOW

    HEALTH_STYLES = {
        HEALTH_GREEN: HEALTH_GREEN_STYLE,
        HEALTH_YELLOW: HEALTH_YELLOW_STYLE,
    }

    def cell_text(value: Any) -> str:
        """The text one cell draws for ``value``, blank where it holds none."""
        return BLANK_VALUE if value is None else str(value)

    def plain_label(text: str, style: str, parent: QWidget) -> QLabel:
        """A QLabel on ``parent`` carrying ``text`` under ``style``."""
        made = QLabel(text, parent)
        made.setStyleSheet(style)
        return made

    def chip(name: str, value: Any, parent: QWidget) -> QFrame:
        """One reading as a chip: its label beside its value."""
        held = QFrame(parent)
        held.setObjectName(CHIP_OBJECT)
        held.setStyleSheet(CHIP_STYLE)
        row = QHBoxLayout(held)
        row.setContentsMargins(ds.SPACE_S, ds.SPACE_XXS, ds.SPACE_S, ds.SPACE_XXS)
        row.setSpacing(ds.SPACE_XS)
        row.addWidget(plain_label(name, CHIP_LABEL_STYLE, held))
        row.addWidget(plain_label(cell_text(value), CHIP_VALUE_STYLE, held))
        return held

    def chip_row(reading: dict, pairs: list, parent: QWidget) -> QWidget:
        """One chip per declared pair, read off ``reading`` by field name."""
        held = QWidget(parent)
        held.setStyleSheet(INNER_STYLE)
        row = QHBoxLayout(held)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(ds.SPACE_XS)
        for pair in pairs:
            row.addWidget(chip(pair[1], reading.get(pair[0]), held))
        row.addStretch(1)
        return held

    def health_label(reading: dict, model: dict, parent: QWidget) -> QLabel:
        """The health light: its state, or the no-records words when it has none."""
        state = reading.get("health")
        if state is None:
            return plain_label(model["no_records_text"], HEALTH_QUIET_STYLE, parent)
        return plain_label(
            str(state), HEALTH_STYLES.get(state, HEALTH_QUIET_STYLE), parent
        )

    def emitter_table(reading: dict, columns: list, parent: QWidget) -> QWidget:
        """The emitter columns and one row per emitter the subsystem holds."""
        held = QWidget(parent)
        held.setStyleSheet(INNER_STYLE)
        grid = QGridLayout(held)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(ds.SPACE_XS)
        grid.setVerticalSpacing(0)
        for at, name in enumerate(columns):
            grid.addWidget(plain_label(str(name), COLUMN_HEAD_STYLE, held), 0, at)
        for index, emitter in enumerate(reading.get("emitters") or [], start=1):
            for at, field in enumerate(surface.EMITTER_FIELDS):
                style = CELL_NAME_STYLE if at == 0 else CELL_STYLE
                grid.addWidget(
                    plain_label(cell_text(emitter.get(field)), style, held), index, at
                )
        grid.setColumnStretch(len(columns) - 1, 1)
        return held

    def subsystem_panel(reading: dict, model: dict, labels: dict, parent) -> QFrame:
        """One subsystem: its name, its health, its tab, its counts, its emitters."""
        held = QFrame(parent)
        held.setObjectName(PANEL_OBJECT)
        held.setStyleSheet(PANEL_STYLE)
        body = QVBoxLayout(held)
        body.setContentsMargins(ds.SPACE_M, ds.SPACE_S, ds.SPACE_M, ds.SPACE_S)
        body.setSpacing(ds.SPACE_S)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(ds.SPACE_S)
        head.addWidget(plain_label(str(reading["subsystem"]), PANEL_NAME_STYLE, held))
        head.addWidget(health_label(reading, model, held))
        head.addStretch(1)
        head.addWidget(plain_label(str(reading["tab"]), PANEL_TAB_STYLE, held))
        body.addLayout(head)

        body.addWidget(chip_row(reading, labels["counts"], held))
        body.addWidget(emitter_table(reading, labels["emitter_columns"], held))
        return held

    def tab_group(reading: dict, model: dict, labels: dict, parent) -> QFrame:
        """One tab: its name, its health, the subsystems it holds, its counts."""
        held = QFrame(parent)
        held.setObjectName(PANEL_OBJECT)
        held.setStyleSheet(PANEL_STYLE)
        body = QVBoxLayout(held)
        body.setContentsMargins(ds.SPACE_M, ds.SPACE_S, ds.SPACE_M, ds.SPACE_S)
        body.setSpacing(ds.SPACE_S)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(ds.SPACE_S)
        head.addWidget(plain_label(str(reading["tab"]), PANEL_NAME_STYLE, held))
        head.addWidget(health_label(reading, model, held))
        head.addStretch(1)
        names = reading.get("subsystems") or []
        head.addWidget(
            plain_label(
                (
                    ", ".join(str(one) for one in names)
                    if names
                    else model["no_emitters_text"]
                ),
                PANEL_TAB_STYLE,
                held,
            )
        )
        body.addLayout(head)
        body.addWidget(chip_row(reading, labels["counts"], held))
        return held

    class SystemStatusQtTab(QWidget):
        """The Status tab's Watchdog read-out, drawn by Qt widgets.

        Asks the surface for the read-out when no ``model`` is handed in, so the
        tab draws what the sink holds at build time.
        """

        def __init__(self, model: dict | None = None, parent=None) -> None:
            """Hold ``model``, or ask the surface for one, and draw all of it."""
            super().__init__(parent)
            self._model = dict(model) if model is not None else surface.view_model({})
            self.setAccessibleName(self._model["accessible_name"])
            self.setStyleSheet(BODY_STYLE)

            labels = self._model["labels"]
            page = QVBoxLayout(self)
            page.setContentsMargins(0, 0, 0, 0)
            page.setSpacing(0)
            page.addWidget(self._header_bar(labels))
            page.addWidget(self._legend())
            page.addWidget(self._columns(labels), 1)

        def model(self) -> dict:
            """A copy of the read-out the tab draws."""
            return dict(self._model)

        def _header_bar(self, labels: dict) -> QWidget:
            """The heading, the feed readings and the totals, on one strip."""
            bar = QWidget(self)
            bar.setStyleSheet(HEADER_BAR_STYLE)
            row = QHBoxLayout(bar)
            row.setContentsMargins(ds.SPACE_M, ds.SPACE_S, ds.SPACE_M, ds.SPACE_S)
            row.setSpacing(ds.SPACE_M)
            row.addWidget(plain_label(self._model["heading"], HEADING_STYLE, bar))
            row.addWidget(self._feed(labels, bar))
            row.addStretch(1)
            row.addWidget(chip_row(self._model["totals"], labels["totals"], bar))
            return bar

        def _feed(self, labels: dict, parent: QWidget) -> QWidget:
            """The feed's own counters, or the words saying no sink is installed."""
            feed = self._model["feed"]
            if not feed.get("installed"):
                return plain_label(self._model["no_feed_text"], FEED_STYLE, parent)
            return chip_row(feed, labels["feed"], parent)

        def _legend(self) -> QLabel:
            """The legend, wrapped so no width cuts it off."""
            made = plain_label(self._model["legend"], LEGEND_STYLE, self)
            made.setWordWrap(True)
            return made

        def _columns(self, labels: dict) -> QWidget:
            """The by-subsystem column beside the by-tab column."""
            body = QWidget(self)
            body.setStyleSheet(BODY_STYLE)
            row = QHBoxLayout(body)
            row.setContentsMargins(ds.SPACE_M, 0, ds.SPACE_M, ds.SPACE_M)
            row.setSpacing(ds.SPACE_M)
            row.addWidget(
                self._column(
                    labels["subsystems"],
                    [
                        subsystem_panel(one, self._model, labels, body)
                        for one in self._model["subsystems"]
                    ],
                    body,
                ),
                3,
            )
            row.addWidget(
                self._column(
                    labels["tabs"],
                    [
                        tab_group(one, self._model, labels, body)
                        for one in self._model["tabs"]
                    ],
                    body,
                ),
                2,
            )
            return body

        def _column(self, title: str, panels: list, parent: QWidget) -> QWidget:
            """One titled column scrolling the panels it was handed."""
            held = QWidget(parent)
            column = QVBoxLayout(held)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(ds.SPACE_S)
            column.addWidget(plain_label(title, SECTION_STYLE, held))

            inner = QWidget()
            inner.setStyleSheet(BODY_STYLE)
            stack = QVBoxLayout(inner)
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(ds.SPACE_S)
            for panel in panels:
                panel.setParent(inner)
                stack.addWidget(panel)
            stack.addStretch(1)

            scroller = QScrollArea(held)
            scroller.setStyleSheet(SCROLL_STYLE)
            scroller.setWidgetResizable(True)
            scroller.setFrameShape(QFrame.NoFrame)
            scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroller.setWidget(inner)
            column.addWidget(scroller, 1)
            return held


__all__ = ["SystemStatusQtTab"] if _HAS_QT else []
