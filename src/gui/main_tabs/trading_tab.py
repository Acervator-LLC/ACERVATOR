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
from . import asset_class_surface as acs
from ..widgets.status_log import StatusLog
from .main_window_surface import LIVE_TAB
from .trading_tab_surface import (
    BOTTOM_SPLITTER_SIZES_PX,
    LOG_SPLITTER_SIZES_PX,
    MAIN_SPLITTER_SIZES_PX,
    TOP_SPLITTER_SIZES_PX,
    placeholder_hint_text,
    placeholder_title_text,
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
        ``set_votes_handler`` carries the other way: a press on the page
        reaches ``MainWindow._answer_votes`` and moves the Qt voting panel.
        """
        relay = getattr(getattr(self, "_trading_tab", None), "show_log_call", None)
        if callable(relay):
            self._status_log.set_relay(relay)
        bind = getattr(getattr(self, "_trading_tab", None), "set_votes_handler", None)
        answer = getattr(self, "_answer_votes", None)
        if callable(bind) and callable(answer):
            bind(answer)

    def _make_unlayered_page(self) -> QWidget:
        """Build the page every asset class with no trading layer shows.

        ``MainWindow._show_unlayered_class`` writes ``_unlayered_title`` and
        ``_unlayered_note`` from ``asset_class_surface.class_state``.
        """
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setMinimumSize(280, 140)
        card.setStyleSheet(
            f"QFrame {{ background: rgba(0,0,0,0); "
            f"border: 1px solid {rgba(ds.OUTLINE, PLACEHOLDER_CARD_BORDER_ALPHA)}; "
            f"border-radius: 6px; }}"
        )
        inner = QVBoxLayout(card)
        inner.setAlignment(Qt.AlignCenter)
        inner.setSpacing(12)

        self._unlayered_title = QLabel("No trading layer")
        self._unlayered_title.setStyleSheet(f"color: {ds.TEXT_INACTIVE}; border: none;")
        self._unlayered_title.setAlignment(Qt.AlignCenter)
        inner.addWidget(self._unlayered_title)

        self._unlayered_note = QLabel("")
        self._unlayered_note.setWordWrap(True)
        self._unlayered_note.setStyleSheet(
            f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; border: none;"
        )
        self._unlayered_note.setAlignment(Qt.AlignCenter)
        inner.addWidget(self._unlayered_note)

        outer.addWidget(card, alignment=Qt.AlignCenter)
        self._unlayered_page = page
        return page

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
        self._equity_exchange_ids = acs.EQUITY_VENUES

        # ── QStackedWidget: one page per layered class, then the note page ──
        from PySide6.QtWidgets import QStackedWidget

        self._trading_stack = QStackedWidget()
        self._add_exchange_buttons: list = []

        def _make_layer(asset_class: str, accent: str) -> tuple:
            """Build one trading layer — returns (page_widget, tab_widget,
            exchange_tabs_dict, placeholder_widget)."""
            label_text = acs.display_name(asset_class)
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)

            tab_w = QTabWidget()
            add_btn = QPushButton(acs.add_exchange_label(asset_class))
            add_btn.setMinimumWidth(140)
            add_btn.setToolTip(acs.add_exchange_tooltip(asset_class))
            add_btn.clicked.connect(self._add_exchange)
            self._add_exchange_buttons.append(add_btn)
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
            ph_title = QLabel(placeholder_title_text(label_text))
            ph_title.setStyleSheet(f"color: {ds.TEXT_INACTIVE}; border: none;")
            ph_title.setAlignment(Qt.AlignCenter)
            ph_layout.addWidget(ph_title)
            ph_add = QPushButton(acs.add_exchange_label(asset_class))
            ph_add.setMinimumSize(180, 36)
            ph_add.setStyleSheet(
                f"QPushButton {{ border: 1px solid {accent}; "
                f"color: {accent}; border-radius: 4px; }}"
            )
            ph_add.clicked.connect(self._add_exchange)
            self._add_exchange_buttons.append(ph_add)
            ph_layout.addWidget(ph_add, alignment=Qt.AlignCenter)
            ph_hint = QLabel(placeholder_hint_text(label_text))
            ph_hint.setStyleSheet(
                f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; border: none;"
            )
            ph_hint.setAlignment(Qt.AlignCenter)
            ph_layout.addWidget(ph_hint)
            ph_outer.addWidget(ph_card, alignment=Qt.AlignCenter)
            tab_w.addTab(placeholder, "Get Started")

            page_layout.addWidget(tab_w)
            return page, tab_w, {}, placeholder

        # One layer per layered class, added in the order layer_page numbers.
        self._class_layers: dict = {}
        for layered in acs.layered_classes():
            page, bar, store, card = _make_layer(layered, acs.accent(layered))
            self._class_layers[layered] = {
                "page": page,
                "tabs": bar,
                "exchange_tabs": store,
                "placeholder": card,
            }
            self._trading_stack.addWidget(page)

        self._crypto_tab_widget = self._class_layers["crypto"]["tabs"]
        self._crypto_placeholder = self._class_layers["crypto"]["placeholder"]
        self._stock_tab_widget = self._class_layers["stocks"]["tabs"]
        self._stock_placeholder = self._class_layers["stocks"]["placeholder"]

        self._crypto_exchange_tabs: dict = self._class_layers["crypto"]["exchange_tabs"]
        self._stock_exchange_tabs: dict = self._class_layers["stocks"]["exchange_tabs"]

        self._trading_stack.addWidget(self._make_unlayered_page())
        self._trading_stack.setCurrentIndex(acs.layer_page("crypto"))

        # Alias: whichever layer select_asset_class made current.
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
                self._trading_stack.count() != acs.stack_pages(),
                _crypto_page != acs.layer_page("crypto"),
                _stock_page != acs.layer_page("stocks"),
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
            "chronological order."
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
            "happening; the buffer just stops appending to the view."
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
