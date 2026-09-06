# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Console tab drawn by Qt widgets.

``ConsoleQtTab`` holds the log pane, the control bar with its Pause and
Clear buttons, the buffered-message indicator and the signals pane, and
names them ``log_pane``, ``signal_view``, ``pause_button``,
``pause_indicator`` and ``pause_refresh`` for the main window to drive.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .main_tabs import console_tab_surface as surface
from .main_tabs.console_log_handler import _QtLogHandler

ACCESSIBLE_NAME = "Console Tab"

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )

    _HAS_QT = True
except ImportError:
    # Without Qt, ConsoleQtTab is never defined and its import fails by name.
    _HAS_QT = False


if _HAS_QT:

    class ConsoleQtTab(QWidget):
        """The Console tab's two panes and its control bar."""

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._pressed: Optional[Callable[[str], None]] = None

            self.log_pane = QPlainTextEdit()
            self.log_pane.setReadOnly(True)
            self.log_pane.setFont(
                QFont(surface.PANE_FONT_FAMILY, surface.PANE_FONT_POINT_SIZE)
            )
            self.log_pane.setStyleSheet(surface.PANE_STYLE)
            self.log_pane.setLineWrapMode(QPlainTextEdit.NoWrap)
            self.log_pane.setMaximumBlockCount(surface.PANE_MAX_BLOCKS)
            self.log_pane.setCenterOnScroll(False)

            self.log_handler = _QtLogHandler(self.log_pane)
            self.log_handler.setFormatter(
                logging.Formatter(surface.LOG_FORMAT, datefmt=surface.LOG_DATEFMT)
            )
            # The tab sets its own handler's level and leaves every logger level alone.
            self.log_handler.setLevel(surface.HANDLER_LEVEL)

            console_layout = QVBoxLayout(self)
            console_layout.setContentsMargins(0, 0, 0, 0)
            console_layout.setSpacing(0)

            control_bar = QWidget()
            control_bar.setStyleSheet(surface.CONTROL_BAR_STYLE)
            control_layout = QHBoxLayout(control_bar)
            control_layout.setContentsMargins(6, 4, 6, 4)
            control_layout.setSpacing(8)

            self.pause_button = QPushButton(surface.PAUSE_BUTTON_TEXT)
            self.pause_button.setCheckable(True)
            self.pause_button.setStyleSheet(surface.PAUSE_BUTTON_STYLE)
            self.pause_button.clicked.connect(self._pause_clicked)
            control_layout.addWidget(self.pause_button)

            self.pause_indicator = QLabel(surface.PAUSE_INDICATOR_TEXT)
            self.pause_indicator.setStyleSheet(surface.PAUSE_INDICATOR_STYLE)
            control_layout.addWidget(self.pause_indicator)

            control_layout.addStretch(1)

            self.clear_button = QPushButton(surface.CLEAR_BUTTON_TEXT)
            self.clear_button.setStyleSheet(surface.CLEAR_BUTTON_STYLE)
            self.clear_button.clicked.connect(self._clear_clicked)
            control_layout.addWidget(self.clear_button)

            console_layout.addWidget(control_bar)

            signal_box = QWidget()
            signal_layout = QVBoxLayout(signal_box)
            signal_layout.setContentsMargins(0, 0, 0, 0)
            signal_layout.setSpacing(0)

            self.signal_header = QLabel(surface.SIGNAL_HEADER_TEXT)
            self.signal_header.setStyleSheet(surface.SIGNAL_HEADER_STYLE)
            signal_layout.addWidget(self.signal_header)

            self.signal_view = QPlainTextEdit()
            self.signal_view.setReadOnly(True)
            self.signal_view.setMaximumBlockCount(surface.SIGNAL_MAX_BLOCKS)
            self.signal_view.setStyleSheet(surface.SIGNAL_PANE_STYLE)
            signal_layout.addWidget(self.signal_view, 1)

            self.splitter = QSplitter(Qt.Vertical)
            self.splitter.addWidget(self.log_pane)
            self.splitter.addWidget(signal_box)
            self.splitter.setStretchFactor(0, surface.SPLIT_STRETCH_LOG)
            self.splitter.setStretchFactor(1, surface.SPLIT_STRETCH_SIGNALS)
            console_layout.addWidget(self.splitter, 1)

            # Started and stopped by the pause action, never here.
            self.pause_refresh = QTimer(self)
            self.pause_refresh.setInterval(surface.PAUSE_REFRESH_INTERVAL_MS)

        def on_pressed(self, handler: Callable[[str], None]) -> None:
            """Take the callable the main window answers a button press with."""
            self._pressed = handler

        def _pause_clicked(self) -> None:
            if self._pressed is not None:
                self._pressed(surface.ACTIONS["pause_button.clicked"])

        def _clear_clicked(self) -> None:
            if self._pressed is not None:
                self._pressed(surface.ACTIONS["clear_button.clicked"])
                return
            self.log_pane.clear()


__all__ = ["ConsoleQtTab"] if _HAS_QT else []
