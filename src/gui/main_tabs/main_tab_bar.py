# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The main window's tab bar, one ground colour per tab.

``MainWindowTabBar`` paints each tab on the ground ``TAB_GROUNDS`` gives its
label and draws the label in that ground's text colour. The three grounds are
Qt properties the theme's own style sheet sets, so a theme switch repaints the
bar. ``MainTabBookQt`` is the ``QTabWidget`` carrying that bar, which
``variant_surface`` hands to ``MainWindow`` under ``MAIN_TAB_BOOK``.
"""

from __future__ import annotations

from PySide6.QtCore import Property, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyleOptionTab, QTabBar, QTabWidget

from ..theme_engine import MAIN_TAB_BAR_OBJECT_NAME
from .main_window_surface import (
    BLACK_GROUND,
    GOLD_GROUND,
    TAB_GROUNDS,
    WHITE_GROUND,
)

ACCESSIBLE_NAME = "Main Window Tab Bar"
BOOK_ACCESSIBLE_NAME = "Main Tab Book"


class MainWindowTabBar(QTabBar):
    """A tab bar that paints each tab on the ground its label names."""

    def __init__(self, parent=None) -> None:
        """Name the bar so the theme's style sheet reaches its six colours."""
        super().__init__(parent)
        self.setObjectName(MAIN_TAB_BAR_OBJECT_NAME)
        self.setAccessibleName(ACCESSIBLE_NAME)
        self._black_bg = QColor()
        self._black_text = QColor()
        self._white_bg = QColor()
        self._white_text = QColor()
        self._gold_bg = QColor()
        self._gold_text = QColor()

    def _read_black_bg(self) -> QColor:
        return self._black_bg

    def _write_black_bg(self, colour) -> None:
        self._black_bg = QColor(colour)
        self.update()

    def _read_black_text(self) -> QColor:
        return self._black_text

    def _write_black_text(self, colour) -> None:
        self._black_text = QColor(colour)
        self.update()

    def _read_white_bg(self) -> QColor:
        return self._white_bg

    def _write_white_bg(self, colour) -> None:
        self._white_bg = QColor(colour)
        self.update()

    def _read_white_text(self) -> QColor:
        return self._white_text

    def _write_white_text(self, colour) -> None:
        self._white_text = QColor(colour)
        self.update()

    def _read_gold_bg(self) -> QColor:
        return self._gold_bg

    def _write_gold_bg(self, colour) -> None:
        self._gold_bg = QColor(colour)
        self.update()

    def _read_gold_text(self) -> QColor:
        return self._gold_text

    def _write_gold_text(self, colour) -> None:
        self._gold_text = QColor(colour)
        self.update()

    tab_black_bg = Property(QColor, _read_black_bg, _write_black_bg)
    tab_black_text = Property(QColor, _read_black_text, _write_black_text)
    tab_white_bg = Property(QColor, _read_white_bg, _write_white_bg)
    tab_white_text = Property(QColor, _read_white_text, _write_white_text)
    tab_gold_bg = Property(QColor, _read_gold_bg, _write_gold_bg)
    tab_gold_text = Property(QColor, _read_gold_text, _write_gold_text)

    def ground_colours(self, ground) -> tuple:
        """The ground colour and the text colour one ground paints with."""
        if ground == BLACK_GROUND:
            return (self._black_bg, self._black_text)
        if ground == WHITE_GROUND:
            return (self._white_bg, self._white_text)
        if ground == GOLD_GROUND:
            return (self._gold_bg, self._gold_text)
        return (QColor(), QColor())

    def tab_colours(self, index: int) -> tuple:
        """The ground and text colour the tab at ``index`` paints with."""
        return self.ground_colours(TAB_GROUNDS.get(self.tabText(index)))

    def paintEvent(self, event) -> None:
        """Fill each tab with its ground and draw its label over it."""
        del event
        painter = QPainter(self)
        option = QStyleOptionTab()
        for index in range(self.count()):
            self.initStyleOption(option, index)
            ground, text = self.tab_colours(index)
            if not ground.isValid() or not text.isValid():
                self.style().drawControl(QStyle.CE_TabBarTab, option, painter, self)
                continue
            painter.fillRect(self.tabRect(index), ground)
            painter.setPen(text)
            painter.drawText(
                self.tabRect(index),
                int(Qt.AlignCenter),
                self.tabText(index),
            )
        painter.end()


class MainTabBookQt(QTabWidget):
    """The Qt main tab book, carrying ``MainWindowTabBar``."""

    def __init__(self, parent=None) -> None:
        """Build the book on the painted bar."""
        super().__init__(parent)
        self.setAccessibleName(BOOK_ACCESSIBLE_NAME)
        self.setTabBar(MainWindowTabBar(self))
