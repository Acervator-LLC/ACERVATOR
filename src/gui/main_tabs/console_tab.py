"""Console tab of the main window."""

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
    """The raw log tail, the signals pane and their timers."""

    # Supplied by MainWindow at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
    _drain_signals: Callable[..., Any]
    _emit_console_health: Callable[..., Any]
    _main_tabs: Any
    _refresh_console_pause_indicator: Callable[..., Any]
    _toggle_console_pause: Callable[..., Any]

    def _build_console_tab(self) -> None:
        """Build the Console tab and add it to the main tab widget."""
        # --- Console / Terminal Tab ---
        # MEM-204 — QPlainTextEdit instead of QTextEdit. QTextEdit is a
        # rich-text widget that re-tokenizes HTML on every append + runs
        # a full document layout on every selection drag. QPlainTextEdit
        # is the Qt-canonical widget for log streams: O(1) append, fast
        # selection, bounded by setMaximumBlockCount. Colorization is
        # preserved via QTextCharFormat instead of HTML spans.
        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setFont(QFont("Consolas", 9))
        self._console.setStyleSheet(
            f"QPlainTextEdit {{ background: {ds.SURFACE_CHART}; color: "
            f"{ds.TEXT_CONSOLE}; "
            "border: none; padding: 4px; }"
        )
        self._console.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._console.setMaximumBlockCount(2000)  # cap buffer
        # Qt built-in auto-scroll when cursor is at end — no manual
        # verticalScrollBar().setValue() per append needed.
        self._console.setCenterOnScroll(False)

        qt_handler = _QtLogHandler(self._console)
        qt_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        # Two attach points serving disjoint sets. `logging_engine` sets
        # `acervator.propagate = False`, so `acervator` terminates its
        # own subtree and root reaches only the third-party loggers
        # (ccxt, urllib3, asyncio). A third attach inside the acervator
        # subtree makes `callHandlers` fire this handler twice for one
        # record: `acervator.gui` and `acervator.scrumming` each painted
        # every record from their subtree a second time.
        root_logger = logging.getLogger()
        root_logger.addHandler(qt_handler)
        root_logger.setLevel(logging.DEBUG)
        logging.getLogger("acervator").addHandler(qt_handler)
        self._console_log_handler = qt_handler  # keep ref for pause toggle

        # v3.16.7 — operator directive 2026-04-28: Console Tab needs
        # its own pause function so errors can be captured before
        # they scroll past. Wrap the QPlainTextEdit in a container
        # with a control bar above it.
        #
        # v3.16.10 — IMPORTANT: do NOT add `from PySide6.QtWidgets
        # import QWidget, ...` here. Those names are imported at
        # module top (line 24-26). Importing them inside this method
        # makes them function-locals; line 1720's `central = QWidget()`
        # then UnboundLocalErrors. R77 SBR violation, operator-
        # reported v3.16.9. Use the module-level names directly.
        console_container = QWidget()
        console_layout = QVBoxLayout(console_container)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(0)

        # Control bar
        control_bar = QWidget()
        control_bar.setStyleSheet(
            f"QWidget {{ background: {ds.MAIN_TOOLBAR_SURFACE}; border-bottom: 1px "
            f"solid {ds.MAIN_SEPARATOR}; }}"
        )
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(6, 4, 6, 4)
        control_layout.setSpacing(8)

        # Pause / Resume toggle button
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

        # Buffered-message indicator (visible while paused)
        self._console_pause_indicator = QLabel("")
        self._console_pause_indicator.setStyleSheet(
            f"color: {ds.WARNING}; font-family: Consolas; font-size: 10px; "
            "padding: 0 8px;"
        )
        control_layout.addWidget(self._console_pause_indicator)

        control_layout.addStretch(1)

        # Clear button (since we're already adding a control bar)
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

        # ── SIGNALS PANE ──────────────────────────────────────
        # v3.24.81 — operator directive 2026-08-08: "As soon as the
        # emitters are built, wire them into the console for later
        # refinement when upgrading the Watchdog."
        #
        # The pane above this one is a RAW LOG TAIL: _QtLogHandler
        # appends every logging record from every module, which is
        # why the operator's read is that it "is very spammy and its
        # messages generally do not add value". This pane is the
        # opposite — only records that carry a declared expectation
        # and an observation, in the standardized format.
        #
        # POLLED, NOT PUSHED. `signal_contract.emit` must stay free
        # of I/O and callbacks because it runs on the tick path, and
        # a push would arrive on whatever thread emitted — a
        # cross-thread touch for a Qt widget. A timer poll sidesteps
        # both and batches naturally. `since(seq)` is the
        # incremental read.
        #
        # This is the seam the Watchdog arc takes over later: the
        # sink is the single source, the Console is one consumer of
        # it, and an out-of-process collector reading the same
        # append-only JSONL is another.
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

        self._signal_seq = 0
        # 10.7 -- THE DRAIN LEDGER, AND WHY THE DRAIN ONLY COUNTS.
        #
        # This tab is a CONSUMER of the sink every pin writes to.
        # An `emit` anywhere on the drain path writes a record into
        # the collection the drain is draining: the next tick reads
        # that record, renders it, and emits again, so the pin's own
        # RATE becomes a function of the quantity it measures.
        # `every=` slows that loop without breaking it, and the
        # synchroniser never folds a FAILING check at all -- so the
        # one state worth reporting would be the one state that ran
        # un-throttled.
        #
        # So `_drain_signals` writes these six integers and emits
        # NOTHING, and `_emit_console_health` -- driven by the timer
        # below, at a rate that is a function of the clock and of
        # nothing in the sink -- is the only thing that reads them
        # back out.
        self._signal_drain_ticks = 0
        self._signal_read = 0
        self._signal_rendered = 0
        self._signal_slice_dropped = 0
        # issue #48. GAP MARKERS ARE COUNTED SEPARATELY FROM
        # RECORDS AND THE TWO MUST NEVER BE ADDED INTO ONE NUMBER.
        # `console.14.001` asks whether every record the watermark
        # consumed reached the pane, so a marker must not inflate
        # `_signal_rendered` and turn a real skip green.
        # `console.14.002` asks whether the pane holds what the
        # drain drew, and a marker IS a block, so it must be in
        # that sum. One counter each is the only shape that
        # answers both questions honestly.
        self._signal_markers = 0
        self._signal_health_ticks_seen = 0
        self._signal_timer = QTimer(self)
        self._signal_timer.setInterval(500)
        self._signal_timer.timeout.connect(self._drain_signals)
        self._signal_timer.start()

        # 10.7 -- the console health cadence. LOOKING OFTEN AND
        # WRITING RARELY ARE DIFFERENT DECISIONS AND ARE MADE
        # SEPARATELY HERE. 5000 ms so a stopped drain is visible
        # inside two of the drain's own 500 ms windows; `every=30.0`
        # on the three pins so the WRITE rate stays at one record
        # per pin per 30 s, the same window the Asset Charts pins
        # fold to. A failing check is never folded, so a drain that
        # has stopped reports every 5 s until it starts again.
        self._console_health_timer = QTimer(self)
        self._console_health_timer.setInterval(5000)
        self._console_health_timer.timeout.connect(self._emit_console_health)
        self._console_health_timer.start()

        # Refresh the buffered-count label every 500ms while paused
        # v3.16.10 — QTimer is already imported at module top (line 31);
        # no need for in-function import.
        self._console_pause_refresh = QTimer(self)
        self._console_pause_refresh.setInterval(500)
        self._console_pause_refresh.timeout.connect(
            self._refresh_console_pause_indicator
        )

        self._main_tabs.addTab(console_container, "Console")
