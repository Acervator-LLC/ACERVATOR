"""``ConsoleTabMixin`` builds the Console tab of the main window."""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import design_system as ds
from .console_log_handler import _QtLogHandler


class ConsoleTabMixin:
    """Builds the Console tab's ``_console`` pane and ``_signal_view`` pane.

    ``_build_console_tab`` attaches a ``_QtLogHandler`` and starts the drain
    and health timers.
    """

    # Annotations only; MainWindow supplies these and no attribute is created here.
    _drain_signals: Callable[..., Any]
    _emit_console_health: Callable[..., Any]
    _main_tabs: Any
    _refresh_console_pause_indicator: Callable[..., Any]
    _toggle_console_pause: Callable[..., Any]

    def _build_console_tab(self) -> None:
        """Build the Console tab and add it to ``_main_tabs``."""
        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setFont(QFont("Consolas", 9))
        self._console.setStyleSheet(
            f"QPlainTextEdit {{ background: {ds.SURFACE_CHART}; color: "
            f"{ds.TEXT_CONSOLE}; "
            "border: none; padding: 4px; }"
        )
        self._console.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._console.setMaximumBlockCount(2000)
        self._console.setCenterOnScroll(False)

        qt_handler = _QtLogHandler(self._console)
        qt_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        # The tab sets its own handler's level and leaves every logger level alone.
        qt_handler.setLevel(logging.DEBUG)
        # Two disjoint attach points: `logging_engine` clears `acervator.propagate`.
        logging.getLogger().addHandler(qt_handler)
        logging.getLogger("acervator").addHandler(qt_handler)
        # Read by _toggle_console_pause and _refresh_console_pause_indicator.
        self._console_log_handler = qt_handler

        console_container = QWidget()
        console_layout = QVBoxLayout(console_container)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(0)

        control_bar = QWidget()
        control_bar.setStyleSheet(
            f"QWidget {{ background: {ds.MAIN_TOOLBAR_SURFACE}; border-bottom: 1px "
            f"solid {ds.MAIN_SEPARATOR}; }}"
        )
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(6, 4, 6, 4)
        control_layout.setSpacing(8)

        self._console_pause_btn = QPushButton("⏸  Pause")
        self._console_pause_btn.setCheckable(True)
        self._console_pause_btn.setStyleSheet(
            f"QPushButton {{ background: {ds.MAIN_BUTTON_SURFACE}; color: "
            f"{ds.TEXT_CONSOLE}; "
            f"border: 1px solid {ds.MAIN_BUTTON_BORDER}; padding: 4px 12px; "
            "font-family: Consolas; font-size: 10px; }"
            f"QPushButton:checked {{ background: {ds.MAIN_TOGGLE_CHECKED_AMBER}; "
            f"color: {ds.WARNING}; "
            f"border-color: {ds.WARNING}; }}"
            f"QPushButton:hover {{ background: {ds.MAIN_BUTTON_HOVER}; }}"
        )
        self._console_pause_btn.clicked.connect(self._toggle_console_pause)
        control_layout.addWidget(self._console_pause_btn)

        self._console_pause_indicator = QLabel("")
        self._console_pause_indicator.setStyleSheet(
            f"color: {ds.WARNING}; font-family: Consolas; font-size: 10px; "
            "padding: 0 8px;"
        )
        control_layout.addWidget(self._console_pause_indicator)

        control_layout.addStretch(1)

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {ds.MAIN_BUTTON_SURFACE}; color: "
            f"{ds.TEXT_CONSOLE}; "
            f"border: 1px solid {ds.MAIN_BUTTON_BORDER}; padding: 4px 12px; "
            "font-family: Consolas; font-size: 10px; }"
            f"QPushButton:hover {{ background: {ds.MAIN_BUTTON_HOVER}; }}"
        )
        clear_btn.clicked.connect(self._console.clear)
        control_layout.addWidget(clear_btn)

        console_layout.addWidget(control_bar)

        from PySide6.QtWidgets import QSplitter as _Splitter

        _sig_box = QWidget()
        _sig_lay = QVBoxLayout(_sig_box)
        _sig_lay.setContentsMargins(0, 0, 0, 0)
        _sig_lay.setSpacing(0)

        _sig_hdr = QLabel("  SIGNALS — name · expected · actual")
        _sig_hdr.setStyleSheet(
            f"background:{ds.SURFACE_CONSOLE_HEADER};color:{ds.PRIMARY};font-family:Consolas;"
            f"font-size:10px;padding:3px;border-top:1px solid {ds.SURFACE_4};"
        )
        _sig_lay.addWidget(_sig_hdr)

        self._signal_view = QPlainTextEdit()
        self._signal_view.setReadOnly(True)
        self._signal_view.setMaximumBlockCount(2000)
        self._signal_view.setStyleSheet(
            f"QPlainTextEdit{{background:{ds.SURFACE_CONSOLE};color:{ds.TEXT_LOG_MINT};"
            "font-family:Consolas;font-size:10px;border:none;}"
        )
        _sig_lay.addWidget(self._signal_view, 1)

        _split = _Splitter(Qt.Vertical)
        _split.addWidget(self._console)
        _split.addWidget(_sig_box)
        _split.setStretchFactor(0, 3)
        _split.setStretchFactor(1, 2)
        console_layout.addWidget(_split, 1)

        # `_drain_signals` writes every counter below bar `_signal_health_ticks_seen`.
        self._signal_seq = 0
        self._signal_drain_ticks = 0
        self._signal_read = 0
        self._signal_rendered = 0
        self._signal_slice_dropped = 0
        # A gap marker is a block but not a record, so `_signal_rendered` skips it.
        self._signal_markers = 0
        self._signal_health_ticks_seen = 0
        self._signal_timer = QTimer(self)
        self._signal_timer.setInterval(500)
        self._signal_timer.timeout.connect(self._drain_signals)
        self._signal_timer.start()

        self._console_health_timer = QTimer(self)
        self._console_health_timer.setInterval(5000)
        self._console_health_timer.timeout.connect(self._emit_console_health)
        self._console_health_timer.start()

        # Started and stopped by `_toggle_console_pause`, never here.
        self._console_pause_refresh = QTimer(self)
        self._console_pause_refresh.setInterval(500)
        self._console_pause_refresh.timeout.connect(
            self._refresh_console_pause_indicator
        )

        self._main_tabs.addTab(console_container, "Console")
