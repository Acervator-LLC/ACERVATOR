"""Live tab of the main window."""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import design_system as ds
from ..color_alpha import rgba
from ..widgets.status_log import StatusLog
from .main_window_surface import LIVE_TAB
from .trading_tab_surface import (
    BOTTOM_SPLITTER_SIZES_PX,
    LOG_SPLITTER_SIZES_PX,
    MAIN_SPLITTER_SIZES_PX,
    TOP_SPLITTER_SIZES_PX,
)
from .notify_stub import _NotifyStub

logger = logging.getLogger("acervator.gui")

PLACEHOLDER_CARD_BORDER_ALPHA = 68


class TradingTabMixin:
    """Exchange layers, the indicator panel and the two log panes.

    ``variant_surface`` decides whether the Live tab shows that Qt page or the
    React one, and ``_react_trading_page`` keeps the Qt page either way.
    """

    # Annotations only; MainWindow supplies these at runtime.
    _add_exchange: Callable[..., Any]
    _bot_manager: Any
    _cross_api_event: Callable[..., Any]
    _main_tabs: Any
    _on_api_event: Callable[..., Any]
    _settings: Any
    apiEntryLogged: Any  # noqa: N815 - Qt signal name
    _status_log: Any
    _trading_tab: Any

    def _react_trading_page(self, qt_page: QWidget) -> QWidget:
        """The React Live tab, holding ``qt_page`` as a hidden child.

        ``LiveSystem`` carries ``_bot_manager`` and ``_settings`` to
        ``trading_tab_surface``, which is the bridge method the Qt tab reads.
        """
        from ...core.desktop_bridge import LiveSystem
        from ..variant_surface import TRADING, surface_class

        page = surface_class(TRADING)(LiveSystem(self._bot_manager, self._settings))
        # MainWindow writes to the Qt widgets, so qt_page stays alive off screen.
        qt_page.setParent(page)
        qt_page.setVisible(False)
        return page

    def _push_live_tab(self, asked: Any) -> bool:
        """Hand the React Live tab one fresh ``trading.tab`` request.

        The Qt page answers False, so a caller routes a feed with one call
        whichever variant is drawing.
        """
        show = getattr(getattr(self, "_trading_tab", None), "show_tab", None)
        if not callable(show):
            return False
        return bool(show(asked))

    def _wire_live_feeds(self) -> None:
        """Route every ``StatusLog`` call to the React Live tab as it paints.

        ``set_relay`` reaches ``log``, ``force_log``, ``notice``, ``pause`` and
        ``resume``, which is every path that writes the Activity Log.
        """
        relay = getattr(getattr(self, "_trading_tab", None), "show_log_call", None)
        if callable(relay):
            self._status_log.set_relay(relay)

    def _build_trading_tab(self) -> None:
        """Build the Trading tab and add it to the main tab widget."""
        # --- Tab 1: Trading ---
        trading_tab = QWidget()
        trading_layout = QVBoxLayout(trading_tab)
        trading_layout.setContentsMargins(2, 2, 2, 2)
        trading_layout.setSpacing(2)

        # Full-height splitter: exchange tabs + indicators on top, logs on bottom
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.setHandleWidth(5)
        main_splitter.setChildrenCollapsible(False)

        # Top section: exchange tabs + indicator panel side by side
        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.setHandleWidth(5)
        top_splitter.setChildrenCollapsible(False)

        # ── Equity exchange IDs (routes to Stock layer) ────────────
        self._equity_exchange_ids = {
            "alpaca",
            "ibkr",
            "schwab",
            "tdameritrade",
            "webull",
            "tastytrade",
            "fidelity",
            "etrade",
            "interactivebrokers",
        }

        # ── QStackedWidget: page 0 = Crypto, page 1 = Stock ────────
        from PySide6.QtWidgets import QStackedWidget

        self._trading_stack = QStackedWidget()

        def _make_layer(label_text: str, accent: str) -> tuple:
            """Build one trading layer — returns (page_widget, tab_widget,
            exchange_tabs_dict, placeholder_widget)."""
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)

            tab_w = QTabWidget()
            add_btn = QPushButton(f"＋ Add {label_text} Exchange")
            add_btn.setMinimumWidth(140)
            add_btn.setToolTip(f"Add a {label_text} exchange connection")
            add_btn.clicked.connect(self._add_exchange)
            tab_w.setCornerWidget(add_btn)

            # Empty state placeholder
            placeholder = QWidget()
            ph_outer = QVBoxLayout(placeholder)
            ph_outer.setAlignment(Qt.AlignCenter)
            ph_card = QFrame()
            ph_card.setMinimumSize(280, 140)
            ph_card.setStyleSheet(
                f"QFrame {{ background: rgba(0,255,204,8); "
                f"border: 1px solid {rgba(accent, PLACEHOLDER_CARD_BORDER_ALPHA)}; "
                f"border-radius: 6px; }}"
            )
            ph_layout = QVBoxLayout(ph_card)
            ph_layout.setAlignment(Qt.AlignCenter)
            ph_layout.setSpacing(12)
            ph_title = QLabel(f"No {label_text} Exchanges Configured")
            ph_title.setStyleSheet(f"color: {ds.TEXT_INACTIVE}; border: none;")
            ph_title.setAlignment(Qt.AlignCenter)
            ph_layout.addWidget(ph_title)
            ph_add = QPushButton(f"＋ Add {label_text} Exchange")
            ph_add.setMinimumSize(180, 36)
            ph_add.setStyleSheet(
                f"QPushButton {{ border: 1px solid {accent}; "
                f"color: {accent}; border-radius: 4px; }}"
            )
            ph_add.clicked.connect(self._add_exchange)
            ph_layout.addWidget(ph_add, alignment=Qt.AlignCenter)
            ph_hint = QLabel(f"Add a {label_text} exchange to begin trading")
            ph_hint.setStyleSheet(
                f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; border: none;"
            )
            ph_hint.setAlignment(Qt.AlignCenter)
            ph_layout.addWidget(ph_hint)
            ph_outer.addWidget(ph_card, alignment=Qt.AlignCenter)
            tab_w.addTab(placeholder, "Get Started")

            page_layout.addWidget(tab_w)
            return page, tab_w, {}, placeholder

        # Build both layers
        (
            crypto_page,
            self._crypto_tab_widget,
            _crypto_tabs,
            self._crypto_placeholder,
        ) = _make_layer("Crypto", ds.LAYER_CRYPTO)
        (
            stock_page,
            self._stock_tab_widget,
            _stock_tabs,
            self._stock_placeholder,
        ) = _make_layer("Stock", ds.LAYER_STOCK)

        self._crypto_exchange_tabs: dict = _crypto_tabs
        self._stock_exchange_tabs: dict = _stock_tabs

        self._trading_stack.addWidget(crypto_page)  # index 0
        self._trading_stack.addWidget(stock_page)  # index 1
        self._trading_stack.setCurrentIndex(0)  # start in crypto

        # Legacy alias: points to whichever layer is active
        # Updated by _toggle_trading_mode()
        self._tab_widget = self._crypto_tab_widget
        self._exchange_tabs = self._crypto_exchange_tabs
        self._empty_placeholder = self._crypto_placeholder

        top_splitter.addWidget(self._trading_stack)

        # Right panel: indicator voting only (Price Chart removed per request)
        from ..indicator_panel import IndicatorVotingPanel

        self._indicator_panel = IndicatorVotingPanel()
        self._chart = None  # No chart in trading tab
        top_splitter.addWidget(self._indicator_panel)

        top_splitter.setSizes(list(TOP_SPLITTER_SIZES_PX))

        _crypto_host = (
            self._crypto_tab_widget.parentWidget() if self._crypto_tab_widget else None
        )
        _stock_host = (
            self._stock_tab_widget.parentWidget() if self._stock_tab_widget else None
        )
        _alias_host = self._tab_widget.parentWidget() if self._tab_widget else None
        _crypto_page = (
            self._trading_stack.indexOf(_crypto_host)
            if _crypto_host is not None
            else -1
        )
        _stock_page = (
            self._trading_stack.indexOf(_stock_host) if _stock_host is not None else -1
        )
        _alias_page = (
            self._trading_stack.indexOf(_alias_host) if _alias_host is not None else -1
        )
        _visible_page = self._trading_stack.currentIndex()
        _stack_slot = top_splitter.indexOf(self._trading_stack)
        _panel_slot = top_splitter.indexOf(self._indicator_panel)
        _faults = sum(
            (
                self._trading_stack.count() != 2,
                _crypto_page != 0,
                _stock_page != 1,
                _stack_slot != 0,
                _panel_slot != 1,
                _alias_page != _visible_page,
            )
        )
        import contextlib

        with contextlib.suppress(Exception):
            from src.core.signal_contract import emit as _tr_emit

            _tr_emit(
                "trading.12.001.postcondition.tab_assembled",
                actual=_faults,
                expected=0,
                context={
                    "stack_pages": self._trading_stack.count(),
                    "crypto_page": _crypto_page,
                    "stock_page": _stock_page,
                    "stack_slot": _stack_slot,
                    "panel_slot": _panel_slot,
                    "splitter_slots": top_splitter.count(),
                    "alias_page": _alias_page,
                    "visible_page": _visible_page,
                    "chart_removed": self._chart is None,
                    "equity_ids": len(self._equity_exchange_ids),
                },
            )

        main_splitter.addWidget(top_splitter)

        # Bottom section: spool + two symmetrical log panels
        bottom_splitter = QSplitter(Qt.Vertical)
        bottom_splitter.setHandleWidth(5)
        bottom_splitter.setChildrenCollapsible(False)

        # _spool is assigned after self._status_log exists.
        self._NotifyStub = _NotifyStub
        # Notifications block intentionally not added to bottom_splitter.

        # Two symmetrical log panels side by side
        log_splitter = QSplitter(Qt.Horizontal)
        log_splitter.setHandleWidth(5)
        log_splitter.setChildrenCollapsible(False)

        activity_widget = QWidget()
        activity_layout = QVBoxLayout(activity_widget)
        activity_layout.setContentsMargins(2, 2, 2, 2)
        activity_layout.setSpacing(2)
        # The pause toggle freezes the spool so the operator can read errors.
        activity_header_row = QHBoxLayout()
        activity_label = QLabel("Activity Log")
        activity_label.setStyleSheet(f"color: {ds.PRIMARY}; font-weight: bold;")
        activity_header_row.addWidget(activity_label)
        activity_header_row.addStretch()
        self._activity_pause_btn = QPushButton("⏸  Pause Console")
        self._activity_pause_btn.setStyleSheet(
            f"QPushButton{{background:{ds.MAIN_TOGGLE_SURFACE};color:{ds.WARNING};"
            f"border:1px solid {ds.WARNING};border-radius:3px;"
            "padding:3px 10px;font-size:11px;}"
            f"QPushButton:hover{{background:{ds.MAIN_TOGGLE_HOVER};}}"
            f"QPushButton:checked{{background:{ds.MAIN_TOGGLE_CHECKED};color:{ds.ERROR};"
            f"border:1px solid {ds.ERROR};}}"
        )
        self._activity_pause_btn.setCheckable(True)
        self._activity_pause_btn.setToolTip(
            "Pause the Activity Log spool so errors don't scroll "
            "off-screen. Messages received while paused are "
            "buffered (cap 2000) and flushed on resume in "
            "chronological order. v3.15.67."
        )

        def _on_activity_pause_toggled(checked: bool):
            if checked:
                self._status_log.pause()
                self._activity_pause_btn.setText("▶  Resume Console")
            else:
                self._status_log.resume()
                self._activity_pause_btn.setText("⏸  Pause Console")
            self._push_live_tab({"activity_paused": checked})
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _tr_emit

                _stats = self._status_log.health_stats()
                _tr_emit(
                    "trading.12.005.postcondition.activity_log_paused",
                    actual=_stats["paused"],
                    expected=checked,
                    context={
                        "buffered": _stats["pause_buffer_size"],
                        "renders": _stats["total_renders"],
                        "render_errors": _stats["render_errors"],
                        "blocks": _stats["document_blocks"],
                    },
                )

        self._activity_pause_btn.toggled.connect(_on_activity_pause_toggled)
        activity_header_row.addWidget(self._activity_pause_btn)
        activity_layout.addLayout(activity_header_row)
        self._status_log = StatusLog()
        self._status_log.setMaximumHeight(16777215)  # Remove height limit
        activity_layout.addWidget(self._status_log)
        # self._status_log must exist before the stub wraps it.
        self._spool = self._NotifyStub(self._status_log)
        log_splitter.addWidget(activity_widget)

        # Polls StatusLog.health_stats() every 60s on the GUI thread.
        self._activity_log_last_errors = 0
        self._activity_log_alert_sent_at = 0.0
        self._activity_log_critical_sent_at = 0.0

        def _activity_log_watchdog():
            try:
                stats = self._status_log.health_stats()
            except Exception as _wd_exc:
                logger.warning("Activity-Log watchdog stat fetch failed: %s", _wd_exc)
                return
            import time as _t

            now = _t.time()
            # New render errors since last check?
            cur_errs = stats["render_errors"]
            if cur_errs > self._activity_log_last_errors:
                delta = cur_errs - self._activity_log_last_errors
                self._activity_log_last_errors = cur_errs
                msg = (
                    f"⚠ ACTIVITY-LOG WATCHDOG: {delta} new render "
                    f"error(s) since last check (total {cur_errs}). "
                    f"Last: {stats['last_render_error']}. "
                    f"Output messages may be missing — see "
                    f"acervator.log for raw exception detail."
                )
                self._status_log.force_log(msg, "error")
                logger.error(msg)
            # No-activity windows
            age = stats["last_render_age_sec"]
            # Only alert if bots are active — quiet idle is fine
            bots_active = self._bot_manager and any(
                b.state.value == "running"
                for b in getattr(self._bot_manager, "_bots", {}).values()
            )
            if bots_active and age > 600:
                # Throttle: re-alert every 10 min while silent
                if now - self._activity_log_alert_sent_at > 600:
                    msg = (
                        f"⚠ ACTIVITY-LOG WATCHDOG: no new log "
                        f"messages for {age:.0f}s while {sum(1 for b in self._bot_manager._bots.values() if b.state.value == 'running')} "
                        f"bot(s) running. paused={stats['paused']}, "
                        f"buffered={stats['pause_buffer_size']}, "
                        f"document_blocks={stats['document_blocks']}."
                    )
                    self._status_log.force_log(msg, "warning")
                    logger.warning(msg)
                    self._activity_log_alert_sent_at = now
            if bots_active and age > 1800:
                # Critical: 30+ min silence with bots running
                if now - self._activity_log_critical_sent_at > 1800:
                    msg = (
                        f"🚨 ACTIVITY-LOG WATCHDOG CRITICAL: no "
                        f"new log messages for {age:.0f}s. Likely "
                        f"silent failure — check acervator.log "
                        f"and bot status panels directly."
                    )
                    self._status_log.force_log(msg, "error")
                    logger.error(msg)
                    self._activity_log_critical_sent_at = now

        self._activity_log_watchdog_timer = QTimer(self)
        self._activity_log_watchdog_timer.timeout.connect(_activity_log_watchdog)
        self._activity_log_watchdog_timer.start(60_000)  # 60s

        api_widget = QWidget()
        api_layout = QVBoxLayout(api_widget)
        api_layout.setContentsMargins(2, 2, 2, 2)
        api_layout.setSpacing(2)
        api_header_row = QHBoxLayout()
        api_label = QLabel("API Interaction Log")
        api_label.setStyleSheet(f"color: {ds.PRIMARY}; font-weight: bold;")
        api_header_row.addWidget(api_label)
        api_header_row.addStretch()
        self._api_pause_btn = QPushButton("⏸  Pause API Log")
        self._api_pause_btn.setStyleSheet(
            f"QPushButton{{background:{ds.MAIN_TOGGLE_SURFACE};color:{ds.WARNING};"
            f"border:1px solid {ds.WARNING};border-radius:3px;"
            "padding:3px 10px;font-size:11px;}"
            f"QPushButton:hover{{background:{ds.MAIN_TOGGLE_HOVER};}}"
        )
        self._api_pause_btn.setCheckable(True)
        self._api_pause_btn.setToolTip(
            "Freeze the API Interaction Log so you can capture an "
            "error without it scrolling away. Internal events keep "
            "happening; the buffer just stops appending to the view. "
            "v3.15.67."
        )
        # _on_api_event reads this flag; QPlainTextEdit has no StatusLog subclass.
        self._api_log_paused: bool = False
        self._api_log_pause_buffer: list[str] = []
        self._api_log_pause_buffer_cap: int = 2000

        def _on_api_pause_toggled(checked: bool):
            self._api_log_paused = checked
            if checked:
                self._api_pause_btn.setText("▶  Resume API Log")
            else:
                # Flush the buffer
                buf = list(self._api_log_pause_buffer)
                self._api_log_pause_buffer.clear()
                for line in buf:
                    self._api_log_view.appendPlainText(line)
                if buf:
                    self._api_log_view.appendPlainText(
                        f"--- (resumed; {len(buf)} buffered line(s) above) ---"
                    )
                self._api_pause_btn.setText("⏸  Pause API Log")
            self._push_live_tab({"api_paused": checked})

        self._api_pause_btn.toggled.connect(_on_api_pause_toggled)
        api_header_row.addWidget(self._api_pause_btn)
        api_layout.addLayout(api_header_row)
        self._api_log_view = QPlainTextEdit()
        self._api_log_view.setReadOnly(True)
        self._api_log_view.setPlaceholderText(
            "API calls, responses, timing, data usage..."
        )
        self._api_log_view.setToolTip(
            "Every API call: endpoint, reason, result, timing, data usage"
        )
        self._api_log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._api_log_view.setMaximumBlockCount(2000)
        api_layout.addWidget(self._api_log_view)
        log_splitter.addWidget(api_widget)

        # Equal sizes for symmetry
        log_splitter.setSizes(list(LOG_SPLITTER_SIZES_PX))
        bottom_splitter.addWidget(log_splitter)

        bottom_splitter.setSizes(list(BOTTOM_SPLITTER_SIZES_PX))
        main_splitter.addWidget(bottom_splitter)

        main_splitter.setSizes(list(MAIN_SPLITTER_SIZES_PX))
        trading_layout.addWidget(main_splitter)

        from ...exchange.api_logger import get_api_log

        self._api_logger = get_api_log()
        # Every entry crosses apiEntryLogged, so a record on a worker thread
        # reaches _on_api_event on the GUI thread instead of the thread guard.
        self.apiEntryLogged.connect(self._on_api_event)
        self._api_logger.add_listener(self._cross_api_event)

        from ..variant_surface import TRADING, draws_react

        if draws_react(TRADING):
            trading_tab = self._react_trading_page(trading_tab)
        self._trading_tab = trading_tab
        self._wire_live_feeds()
        self._main_tabs.addTab(trading_tab, LIVE_TAB)
