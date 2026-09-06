"""``ConsoleTabMixin`` builds the Console tab of the main window."""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QTimer

from . import console_tab_surface as surface

logger = logging.getLogger("acervator.gui.console_tab")


class ConsoleTabMixin:
    """Builds the Console tab's ``_console`` pane and ``_signal_view`` pane.

    ``variant_surface`` picks the Qt tab or the React tab, and
    ``_build_console_tab`` attaches its log handler and starts the timers.
    """

    # Annotations only; MainWindow supplies these and no attribute is created here.
    _drain_signals: Callable[..., Any]
    _emit_console_health: Callable[..., Any]
    _main_tabs: Any
    _refresh_console_pause_indicator: Callable[..., Any]
    _toggle_console_pause: Callable[..., Any]
    _console: Any

    def _build_console_tab(self) -> None:
        """Build the Console tab and add it to ``_main_tabs``."""
        from ..variant_surface import CONSOLE, surface_class

        tab = surface_class(CONSOLE)()
        self._console_tab = tab
        self._console = tab.log_pane
        self._signal_view = tab.signal_view
        self._console_pause_btn = tab.pause_button
        self._console_pause_indicator = tab.pause_indicator
        # Started and stopped by `_toggle_console_pause`, never here.
        self._console_pause_refresh = tab.pause_refresh
        # Read by _toggle_console_pause and _refresh_console_pause_indicator.
        self._console_log_handler = tab.log_handler

        tab.pause_refresh.timeout.connect(self._refresh_console_pause_indicator)
        tab.on_pressed(self._console_pressed)
        # Two disjoint attach points: `logging_engine` clears `acervator.propagate`.
        for name in surface.HANDLER_LOGGERS:
            logging.getLogger(name).addHandler(tab.log_handler)

        self._start_console_timers()
        self._main_tabs.addTab(tab, surface.TAB_TITLE)

    def _console_pressed(self, action: str) -> None:
        """Answer the Pause or the Clear the tab reports."""
        if action == surface.ACTIONS["pause_button.clicked"]:
            self._toggle_console_pause()
        elif action == surface.ACTIONS["clear_button.clicked"]:
            self._console.clear()

    def _start_console_timers(self) -> None:
        """Start the drain and health timers and zero the seven drain counters."""
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
        self._signal_timer.setInterval(surface.DRAIN_INTERVAL_MS)
        self._signal_timer.timeout.connect(self._drain_signals)
        self._signal_timer.start()

        self._console_health_timer = QTimer(self)
        self._console_health_timer.setInterval(surface.HEALTH_INTERVAL_MS)
        self._console_health_timer.timeout.connect(self._emit_console_health)
        self._console_health_timer.start()
