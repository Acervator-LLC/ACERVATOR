"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
MainWindow builds the tab shell, header strip, status bar and dashboard timer.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from pathlib import Path
from typing import Optional

from ..core.event_bus import get_event_bus
from .. import __version__
from . import design_system as ds
from .main_tabs.main_window_surface import (
    CANONICAL_TAB_ORDER,
    HISTORY_TAB,
    ISOLATED_TABS,
)
from .main_tabs.trading_tab_surface import exchange_display_name


from .table_cells import (
    _AMMO_FOLD,
    _AMMO_NEUTRAL,
    _AMMO_SCRUM,
    _MANUAL_FIRE_DUST_PCT,
    _PRICE_STALE_AFTER_S,
    _STALE_MARKER,
    _ammo_price_pool,
    _compose_ammo_cell,
    _compose_table_target_denom_cell,
    _fresh_display_price,
)

logger = logging.getLogger("acervator.gui")


def _main_tab_book_class() -> type:
    """The main tab book class the running variant draws, Qt or React."""
    from .variant_surface import MAIN_TAB_BOOK, surface_class

    return surface_class(MAIN_TAB_BOOK)


try:
    from PySide6.QtWidgets import (
        QMainWindow,
        QLabel,
        QPushButton,
        QStatusBar,
        QGroupBox,
        QPlainTextEdit,
        QMessageBox,
    )
    from PySide6.QtCore import Qt, QTimer, Slot
    from PySide6.QtGui import QIcon

    from .main_tabs.bot_swarm_tab import BotSwarmTabMixin
    from .main_tabs.charts_tab import ChartsTabMixin
    from .main_tabs.console_tab import ConsoleTabMixin
    from .main_tabs import header_strip_surface
    from .main_tabs.header_strip import HeaderStripMixin
    from .main_tabs.history_tab import HistoryTabMixin
    from .main_tabs.market_inspector_tab import MarketInspectorTabMixin
    from .main_tabs.paper_trader_tab import PaperTraderTabMixin
    from .main_tabs.proof_of_accumulation_tab import ProofOfAccumulationTabMixin
    from .main_tabs.retired_tabs import RetiredTabsMixin
    from .main_tabs.simulator_tab import SimulatorTabMixin
    from .main_tabs.system_status_tab import SystemStatusTabMixin
    from .main_tabs.trading_tab import TradingTabMixin
    from .widgets.api_tester_tab import APITesterTab
    from .widgets.bot_selection import _reanchor_bot_selection, _select_row_for_bot
    from .widgets.bot_status_table import SCRUMMING_COLUMNS, BotStatusTable
    from .widgets.capital_registry_panel import CapitalRegistryPanel
    from .widgets.dashboard_stat_card import StatCard
    from .widgets.exchange_tab import ExchangeTab
    from .widgets.extractor_bot_table import EXTRACTOR_COLUMNS, ExtractorBotTable
    from .widgets.notification_spool import NotificationSpool
    from .widgets.placeholder_exchange import _PlaceholderExchange
    from .widgets.privacy_dot import PrivacyDot
    from .widgets.pulse_manager import PULSE_CSS, PulseManager
    from .widgets.spendable_profits import SpendableProfitsWidget
    from .widgets.status_log import StatusLog
    from .widgets.trade_charts_tab import TradeChartsTab

    _HAS_QT = True
except ImportError:
    _HAS_QT = False
from src.gui.qt_safe_events import safe_process_events

__all__ = [
    "APITesterTab",
    "BotStatusTable",
    "CapitalRegistryPanel",
    "EXTRACTOR_COLUMNS",
    "ExchangeTab",
    "ExtractorBotTable",
    "MainWindow",
    "NotificationSpool",
    "PULSE_CSS",
    "PrivacyDot",
    "PulseManager",
    "SCRUMMING_COLUMNS",
    "SpendableProfitsWidget",
    "StatCard",
    "StatusLog",
    "TradeChartsTab",
    "_AMMO_FOLD",
    "_AMMO_NEUTRAL",
    "_AMMO_SCRUM",
    "_MANUAL_FIRE_DUST_PCT",
    "_PRICE_STALE_AFTER_S",
    "_PlaceholderExchange",
    "_STALE_MARKER",
    "_ammo_price_pool",
    "_compose_ammo_cell",
    "_compose_table_target_denom_cell",
    "_fresh_display_price",
    "_reanchor_bot_selection",
    "_select_row_for_bot",
]


if _HAS_QT:

    def _set_console_paused(window: MainWindow, *, paused: bool) -> None:
        """Set `window._console_paused`; `_drain_signals` reads it before rendering."""
        window._console_paused = bool(paused)

    def _signal_gap_marker_text(skipped: int) -> str:
        """Return the marker line naming how many signal records the pane skipped."""
        return (
            f"──── [SIGNALS GAP] {skipped} earlier records skipped "
            f"to stay current · NOT LOST · on disk in "
            f"~/.acervator_logs/signals/session.jsonl ────"
        )

    def _draw_signal_gap_marker(view: QPlainTextEdit, *, skipped: int) -> int:
        """Append an escaped gap marker to `view`; returns 1, or 0 if `skipped <= 0`."""
        if skipped <= 0:
            return 0
        from html import escape as _esc

        view.appendHtml(
            "<span "
            f'style="color:{ds.MAIN_HIGHLIGHT_AMBER_TEXT};background-color:{ds.MAIN_HIGHLIGHT_AMBER}">'
            f"{_esc(_signal_gap_marker_text(skipped))}</span>"
        )
        return 1

    class MainWindow(
        BotSwarmTabMixin,
        ChartsTabMixin,
        ConsoleTabMixin,
        HeaderStripMixin,
        HistoryTabMixin,
        MarketInspectorTabMixin,
        PaperTraderTabMixin,
        ProofOfAccumulationTabMixin,
        RetiredTabsMixin,
        SimulatorTabMixin,
        SystemStatusTabMixin,
        TradingTabMixin,
        QMainWindow,
    ):

        # Annotated, not assigned: the dashboard tick reads `hasattr` on the first pass.
        _last_equity_snap: float

        # Annotated only: `_drain_signals` reads it by `getattr`, default False.
        _console_paused: bool

        def __init__(self, bot_manager=None, settings_manager=None, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Acervator v" + __version__ + "")
            self.setMinimumSize(1400, 900)
            self._bot_manager = bot_manager
            self._settings = settings_manager
            self._exchange_tabs: dict[str, ExchangeTab] = {}
            self._bus = get_event_bus()
            self._async_loop = None
            self._exchange_connectors: dict[str, object] = {}

            try:
                from .buy_confirmation_dialog import get_broker as _get_bcd_broker

                self._buy_confirmation_broker = _get_bcd_broker()
            except Exception as _bcd_exc:
                logger.warning(
                    "MEM-228 buy confirmation broker init failed: %s; "
                    "buys requiring confirmation will fail-closed.",
                    _bcd_exc,
                )
                self._buy_confirmation_broker = None

            from ..trading.risk_manager import RiskManager
            from ..trading.analytics_engine import AnalyticsEngine
            from ..trading.reconciliation import (
                TradeJournal,
                ReconciliationEngine,
                CrashRecovery,
            )
            from ..core.notifications import get_notification_manager

            self._risk_manager = RiskManager(bot_manager)
            self._analytics = AnalyticsEngine()
            self._journal = TradeJournal()
            self._recon_engine = ReconciliationEngine()
            self._crash_recovery = CrashRecovery()
            self._notif_manager = get_notification_manager()

            self._bus.subscribe("bot.log", self._on_bot_log)
            self._bus.subscribe("wire.created", self._on_wire_created)
            self._bus.subscribe("indicator.tf_lock_changed", self._on_tf_lock_changed)
            self._bus.subscribe("ai.feedback", self._on_ai_feedback)
            self._bus.subscribe("trade.filled", self._on_trade_filled_sfx)
            from collections import deque as _deque

            self._error_log_buffer: _deque = _deque(maxlen=200)
            self._bus.subscribe("bot.error", self._on_bot_error_for_log)

            icon_path = Path(__file__).parent.parent.parent / "resources" / "icon.ico"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

            self._setup_menu()
            self._setup_ui()
            self._setup_status_bar()
            self._setup_refresh_timer()
            self._setup_pulse()
            self._setup_tooltips()

            self._init_live_monitor()

            self._status_log.log("Acervator v" + __version__ + " started.", "success")
            logger.info(
                "Acervator v"
                + __version__
                + " — Console logging active. All system messages appear here."
            )
            self._report_stored_credentials_on_startup()

        def set_async_loop(self, loop) -> None:
            """Store the asyncio loop `main.py` runs every coroutine on."""
            self._async_loop = loop

        def _setup_menu(self) -> None:
            menu_bar = self.menuBar()
            file_menu = menu_bar.addMenu("&File")
            file_menu.addAction("&Settings", self._open_settings)
            file_menu.addAction("&Reset All Settings", self._reset_settings)
            file_menu.addSeparator()
            file_menu.addAction("E&xit", self.close)
            exchange_menu = menu_bar.addMenu("&Exchange")
            exchange_menu.addAction("&Add Exchange", self._add_exchange)
            theme_menu = menu_bar.addMenu("&Theme")
            from .theme_engine import THEMES

            for name, tokens in THEMES.items():
                theme_menu.addAction(
                    tokens.display_name,
                    lambda n=name: self._switch_theme(n, self._stored_accent()),
                )
            help_menu = menu_bar.addMenu("&Help")
            help_menu.addAction("&About", self._show_about)

        def _setup_ui(self) -> None:
            main_layout = self._build_header_strip()

            try:
                from .shared_testnet import SharedTestnetBridge

                SharedTestnetBridge.install_on(self)
            except Exception as _e:
                import traceback as _tb

                logging.getLogger("acervator").warning(
                    f"SharedTestnetBridge install failed: {_e}\n" f"{_tb.format_exc()}"
                )
                self._local_testnet = None
                self._testnet_bridge = None

            self._main_tabs = _main_tab_book_class()()
            self._main_tabs.setMovable(True)

            self._build_trading_tab()
            self._build_charts_tab()
            self._build_bot_swarm_tab()
            self._build_market_inspector_tab()
            self._build_simulator_tab()
            self._install_retired_tab_sentinels()
            self._build_history_tab()
            self._build_console_tab()
            self._build_paper_trader_tab()
            self._build_system_status_tab()
            self._build_proof_of_accumulation_tab()

            self._reorder_main_tabs(list(CANONICAL_TAB_ORDER))

            self._main_tabs.currentChanged.connect(self._on_main_tab_changed)

            main_layout.addWidget(self._main_tabs, 1)

        def _reorder_main_tabs(self, desired: list[str]) -> None:
            """Move each label in ``desired`` to its index; unlisted tabs stay put."""
            tab_bar = self._main_tabs.tabBar()
            for target_idx, name in enumerate(desired):
                for cur_idx in range(self._main_tabs.count()):
                    if self._main_tabs.tabText(cur_idx) == name:
                        if cur_idx != target_idx:
                            tab_bar.moveTab(cur_idx, target_idx)
                        break

        def _on_main_tab_changed(self, index: int) -> None:
            """Hide the header strip on the isolated tabs; refresh History if stale."""
            try:
                tab_name = self._main_tabs.tabText(index)
            except Exception:
                return
            isolated_tabs = set(ISOLATED_TABS)
            container = getattr(self, "_header_strip_container", None)
            if container is not None:
                container.setVisible(tab_name not in isolated_tabs)

            if tab_name == HISTORY_TAB:
                hist = getattr(self, "_history_tab", None)
                if hist is not None:
                    try:
                        last_ts = getattr(hist, "_last_fetched_ts", 0.0)
                        in_flight = getattr(hist, "_fetch_in_flight", False)
                        import time as _t

                        is_stale = last_ts == 0 or _t.time() - last_ts > 300
                        if is_stale and not in_flight:
                            hist.refresh()
                    except Exception as _hexc:
                        logger.debug(
                            "History auto-refresh on tab-activate " "skipped: %s", _hexc
                        )

        def _drain_signals(self) -> None:
            """Render sink records past `_signal_seq`, keeping the newest 200."""
            try:
                # Counts invocations, not records: a quiet sink is not a stopped timer.
                self._signal_drain_ticks = getattr(self, "_signal_drain_ticks", 0) + 1
                if getattr(self, "_console_paused", False):
                    return
                view = getattr(self, "_signal_view", None)
                if view is None:
                    return
                from html import escape as _esc

                from src.core.signal_contract import get_sink, render

                sink = get_sink()
                if sink is None:
                    return
                new = sink.since(getattr(self, "_signal_seq", 0))
                if not new:
                    return
                self._signal_seq = new[-1].seq
                # The watermark passed all of `new`, including what the slice drops.
                _shown = new[-200:]
                _skipped = len(new) - len(_shown)
                self._signal_read = getattr(self, "_signal_read", 0) + len(new)
                self._signal_slice_dropped = (
                    getattr(self, "_signal_slice_dropped", 0) + _skipped
                )
                self._signal_rendered = getattr(self, "_signal_rendered", 0)
                # Drawn above the slice: skipped records are older than the 200 below.
                self._signal_markers = getattr(
                    self, "_signal_markers", 0
                ) + _draw_signal_gap_marker(view, skipped=_skipped)
                for r in _shown:
                    if r.ok is True:
                        mark, colour = "OK  ", ds.SUCCESS
                    elif r.ok is False:
                        mark, colour = "FAIL", ds.ERROR
                    else:
                        mark, colour = "--  ", ds.STATUS_NEUTRAL
                    # `appendHtml` parses its input, so an unescaped `<` is swallowed.
                    exp = (
                        ""
                        if r.expected is None
                        else f"  exp={_esc(render(r.expected))}"
                    )
                    view.appendHtml(
                        f'<span style="color:{colour}">{mark}</span> '
                        f'<span style="color:{ds.MAIN_LOG_NAME}">{_esc(r.name)}</span>'
                        f'<span style="color:{ds.MAIN_LOG_SITE}"> {_esc(r.site)}</span>'
                        f'<span style="color:{ds.TEXT_LOG_MINT}">  '
                        f"got={_esc(render(r.actual))}{exp}</span>"
                    )
                    # Incremented after the append, so a raise leaves the count true.
                    self._signal_rendered += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("signal drain failed: %s", exc)

        def _toggle_console_pause(self) -> None:
            """Pause or resume the log pane and the signals drain together."""
            paused = self._console_pause_btn.isChecked()
            _set_console_paused(self, paused=paused)
            handler = getattr(self, "_console_log_handler", None)
            if handler is None:
                return
            import contextlib
            import time as _pause_clock

            # Read before resume drains it; an empty QPlainTextEdit reports one block.
            _console = getattr(self, "_console", None)
            _held = 0
            _dropped = 0
            _before = 0
            try:
                _held = int(handler.buffered_count())
                _dropped = int(getattr(handler, "_buffer_dropped", 0))
                if _console is not None:
                    _before = (
                        0
                        if _console.document().isEmpty()
                        else int(_console.blockCount())
                    )
            except Exception:  # noqa: BLE001
                _console = None
            _t0 = _pause_clock.monotonic()
            handler.set_paused(paused)
            _elapsed = _pause_clock.monotonic() - _t0
            # Read back before the button text and the label change.
            _after = -1
            if _console is not None:
                with contextlib.suppress(Exception):
                    _after = int(_console.blockCount())
            if paused:
                self._console_pause_btn.setText("▶  Resume")
                self._console_pause_indicator.setText("PAUSED · 0 buffered")
                self._console_pause_refresh.start()
            else:
                self._console_pause_btn.setText("⏸  Pause")
                self._console_pause_indicator.setText("")
                self._console_pause_refresh.stop()
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _co_emit

                _co_emit(
                    "console.14.004.postcondition.pause_quiets_both_panes",
                    actual=bool(getattr(self, "_console_paused", False)),
                    expected=paused,
                    context={
                        "log_pane_paused": bool(getattr(handler, "_paused", False)),
                        "button_checked": paused,
                        "buffered": _held,
                    },
                )
            if not paused and _after >= 0 and _console is not None:
                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _co_emit

                    _co_emit(
                        "console.14.005.postcondition.pause_buffer_delivered",
                        actual=_after,
                        expected=max(_before + _held + (1 if _dropped else 0), 1),
                        duration=_elapsed,
                        context={
                            "held": _held,
                            "dropped_at_cap": _dropped,
                            "buffer_cap": int(getattr(handler, "_buffer_max", 0)),
                            "blocks_before": _before,
                            "max_blocks": int(_console.maximumBlockCount()),
                        },
                    )

        def _refresh_console_pause_indicator(self) -> None:
            """Show the buffered count in `_console_pause_indicator` while paused."""
            handler = getattr(self, "_console_log_handler", None)
            if handler is None or not handler._paused:
                return
            n = handler.buffered_count()
            cap = handler._buffer_max
            dropped = handler._buffer_dropped
            if dropped > 0:
                msg = f"PAUSED · {n} buffered (cap {cap}, {dropped} dropped)"
            else:
                msg = f"PAUSED · {n} buffered (cap {cap})"
            self._console_pause_indicator.setText(msg)

        def _emit_console_health(self) -> None:
            """Emit the three console.14 invariants over read, rendered and blocks."""
            try:
                view = getattr(self, "_signal_view", None)
                if view is None:
                    return
                import contextlib

                from src.core.signal_contract import emit as _co_emit

                _ticks = getattr(self, "_signal_drain_ticks", 0)
                _seen = getattr(self, "_signal_health_ticks_seen", 0)
                # Advanced every call, so `console.14.003` compares `_ticks` to `_seen`.
                self._signal_health_ticks_seen = _ticks
                _read = getattr(self, "_signal_read", 0)
                _rendered = getattr(self, "_signal_rendered", 0)
                _markers = getattr(self, "_signal_markers", 0)
                _blocks = int(view.blockCount())
                _cap = int(view.maximumBlockCount())
                _timer = getattr(self, "_signal_timer", None)
                _look = getattr(self, "_console_health_timer", None)
                # An empty QPlainTextEdit reports one block; a gap marker adds one.
                _want = max(_rendered + _markers, 1)
                if _cap > 0:
                    _want = min(_want, _cap)
                with contextlib.suppress(Exception):
                    _co_emit(
                        "console.14.001.invariant.records_rendered",
                        actual=_rendered,
                        expected=_read,
                        every=30.0,
                        context={
                            "lost_to_slice": getattr(self, "_signal_slice_dropped", 0),
                            "slice_cap": 200,
                            "watermark": getattr(self, "_signal_seq", 0),
                            "drain_ticks": _ticks,
                        },
                    )
                with contextlib.suppress(Exception):
                    _co_emit(
                        "console.14.002.invariant.view_holds_rendered",
                        actual=_blocks,
                        expected=_want,
                        every=30.0,
                        context={
                            "evicted": max(0, _rendered + _markers - _blocks),
                            "max_blocks": _cap,
                            "rendered": _rendered,
                            "gap_markers": _markers,
                        },
                    )
                with contextlib.suppress(Exception):
                    _co_emit(
                        "console.14.003.invariant.drain_alive",
                        actual=bool(_ticks - _seen > 0),
                        expected=True,
                        every=30.0,
                        context={
                            "ticks_since_last_look": _ticks - _seen,
                            "drain_timer_active": bool(
                                _timer is not None and _timer.isActive()
                            ),
                            "drain_interval_ms": (
                                int(_timer.interval()) if _timer is not None else 0
                            ),
                            "look_interval_ms": (
                                int(_look.interval()) if _look is not None else 0
                            ),
                        },
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("console health emit failed: %s", exc)

        def _setup_status_bar(self) -> None:
            status = QStatusBar()
            status.showMessage("Ready")

            # Worst-case calls per minute on the busiest connected exchange.
            self._api_load_label = QLabel("API: —")
            self._api_load_label.setStyleSheet(
                f"color: {ds.CARD_METRIC_LABEL}; font-size: 10px; padding: 0 8px; "
                "font-family: Consolas;"
            )
            self._api_load_label.setToolTip(
                "Trailing 60 s calls-per-minute on the busiest "
                "connected exchange. Green ≤ 50 %, amber ≤ 75 %, "
                "red above the 75 % phantom-creation safety threshold."
            )
            status.addPermanentWidget(self._api_load_label)

            self._ai_monitor_label = QLabel("AI: OFF")
            self._ai_monitor_label.setStyleSheet(
                f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; padding: 0 8px; "
                "font-family: Consolas;"
            )
            status.addPermanentWidget(self._ai_monitor_label)

            if self._settings:
                ai_cfg = self._settings.get("ai_monitor", {})
                if ai_cfg.get("enabled") and ai_cfg.get("api_key"):
                    self._ai_monitor_label.setText("AI: READY")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.STATUS_AUTHENTICATED}; font-size: 10px; padding: 0 "
                        "8px; font-family: Consolas;"
                    )

            self.setStatusBar(status)

        # Class attributes: one ThrottledFault per pump, shared by every MainWindow.
        from ..exchange.lazy_singleton import ThrottledFault

        _currency_pump_fault = ThrottledFault(
            "the currency rate pump",
            "The BTC/USD and ETH/USD rates on the dashboard, and the "
            "satoshi and wei prices derived from them, will stop "
            "updating.",
        )
        _scout_pump_fault = ThrottledFault(
            "the market pairs scout pump",
            "Cross-pair readings on the dashboard and in the Bot "
            "Details Status tab will stop updating.",
        )

        def _pump_currency_rates(self) -> None:
            """Refresh CurrencyRateMonitor and push its snapshot to the voting panel."""
            try:
                from ..exchange.currency_rate_monitor import get_currency_monitor

                mon = get_currency_monitor()
                if mon is None:
                    return
                connectors = getattr(self, "_exchange_connectors", {}) or {}
                if connectors:
                    self._schedule_async(mon.refresh_from_connectors(connectors))
                if hasattr(self, "_indicator_panel"):
                    self._indicator_panel.update_currency_rates(mon.snapshot())
                self._currency_pump_fault.note_success()
            except Exception as exc:  # noqa: BLE001
                self._currency_pump_fault.note_failure(exc)

        def _pump_market_pairs_scout(self) -> None:
            """Refresh MarketPairsScout for connected exchanges, one at a time."""
            try:
                from ..exchange.market_pairs_scout import get_scout

                scout = get_scout()
                if scout is None:
                    return
                connectors = getattr(self, "_exchange_connectors", {}) or {}
                if connectors:
                    self._schedule_coalesced(
                        "_pending_scout_refresh",
                        scout.refresh_from_connectors(connectors),
                    )
                self._scout_pump_fault.note_success()
            except Exception as exc:  # noqa: BLE001
                self._scout_pump_fault.note_failure(exc)

        def _refresh_api_load_pill(self) -> None:
            """Set the API-load pill from the worst-loaded connected exchange."""
            try:
                from ..exchange.api_load_monitor import get_load_monitor

                mon = get_load_monitor()
                connectors = getattr(self, "_exchange_connectors", {}) or {}
                if not connectors:
                    self._api_load_label.setText("API: —")
                    self._api_load_label.setStyleSheet(
                        f"color: {ds.CARD_METRIC_LABEL}; font-size: 10px; padding: 0 "
                        "8px; "
                        "font-family: Consolas;"
                    )
                    return
                worst = None
                for eid in connectors.keys():
                    r = mon.sample(eid)
                    if worst is None or r.load_score > worst.load_score:
                        worst = r
                if worst is None:
                    return
                pct = int(worst.load_score * 100)
                text = (
                    f"API {worst.exchange}: "
                    f"{worst.calls_per_minute:.0f}/"
                    f"{worst.ceiling_cpm:.0f} CPM ({pct} %)"
                )
                if worst.load_score > mon.safety_pct:
                    colour = ds.ERROR
                elif worst.load_score > 0.5:
                    colour = ds.FOLD_RATIO_AMBER
                else:
                    colour = ds.SUCCESS
                self._api_load_label.setText(text)
                self._api_load_label.setStyleSheet(
                    f"color: {colour}; font-size: 10px; padding: 0 8px; "
                    f"font-family: Consolas;"
                )
            except Exception as _pill_exc:  # noqa: BLE001
                # Logged at debug: the 2 s dashboard tick would flood a warning stream.
                logger.debug(
                    "API-load pill refresh skipped: %s: %s",
                    type(_pill_exc).__name__,
                    _pill_exc,
                )

        def _setup_refresh_timer(self) -> None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh_dashboard)
            self._timer.start(2000)

        def _setup_pulse(self) -> None:
            """Animate accent widgets with QGraphicsOpacityEffect on an 80 ms timer."""
            from PySide6.QtWidgets import QGraphicsOpacityEffect

            self._pulse_phase = 0.0
            self._pulse_effects: list[QGraphicsOpacityEffect] = []
            # Drop-shadow of each armed Fire button; `_pulse_tick` animates its blur.
            self._fire_glow_effects: list = []

            pulse_targets = [
                self._stat_pnl,
                self._stat_trades,
                self._stat_bots,
                self._stat_errors,
                self._spendable_widget,
            ]
            for widget in pulse_targets:
                effect = QGraphicsOpacityEffect(widget)
                effect.setOpacity(1.0)
                widget.setGraphicsEffect(effect)
                self._pulse_effects.append(effect)

            self._pulse_timer = QTimer(self)
            self._pulse_timer.timeout.connect(self._pulse_tick)
            self._pulse_timer.start(80)

        def _register_fire_glow(self, effect) -> None:
            """Add `effect` to `_fire_glow_effects` and drop the deleted Qt objects."""
            # Calling a method on a deleted Qt object raises RuntimeError.
            live = []
            for e in self._fire_glow_effects:
                try:
                    _ = e.blurRadius()
                    live.append(e)
                except RuntimeError:
                    pass
                except Exception:  # noqa: S110
                    pass
            live.append(effect)
            self._fire_glow_effects = live

        def _pulse_tick(self) -> None:
            self._pulse_phase += 0.05
            # Opacity swings 0.82 to 1.00.
            opacity = 0.91 + 0.09 * math.sin(self._pulse_phase)
            for effect in self._pulse_effects:
                try:  # noqa: SIM105
                    effect.setOpacity(opacity)
                except RuntimeError:
                    pass
            # Glow blur swings 12 to 22.
            import math as _math

            glow_blur = 17.0 + 5.0 * _math.sin(self._pulse_phase * 1.6)
            dead = []
            for effect in self._fire_glow_effects:
                try:
                    effect.setBlurRadius(glow_blur)
                except RuntimeError:
                    dead.append(effect)
                except Exception:
                    dead.append(effect)
            if dead:
                self._fire_glow_effects = [
                    e for e in self._fire_glow_effects if e not in dead
                ]

        def refresh_all_privacy_widgets(self) -> None:
            """Call every privacy refresh hook on the cards, tabs and panels."""
            try:
                if (
                    hasattr(self, "_spendable_widget")
                    and self._spendable_widget is not None
                ):
                    self._spendable_widget.refresh_privacy_dots()
            except Exception:  # noqa: S110
                pass
            for attr_name in (
                "_stat_scrummed",
                "_stat_folded",
                "_stat_trades",
                "_stat_bots",
                "_stat_errors",
            ):
                try:
                    card = getattr(self, attr_name, None)
                    if card is not None and hasattr(card, "refresh_privacy_dot"):
                        card.refresh_privacy_dot()
                except Exception:  # noqa: S110
                    pass
            try:
                for tab in getattr(self, "_exchange_tabs", {}).values():
                    if hasattr(tab, "_refresh_privacy_mode_btn_style"):
                        tab._refresh_privacy_mode_btn_style()
                    try:
                        if self._bot_manager and hasattr(tab, "exchange_id"):
                            statuses = self._bot_manager.list_bots_by_exchange(
                                tab.exchange_id
                            )
                            tab.update_bots(statuses)
                    except Exception:  # noqa: S110
                        pass
            except Exception:  # noqa: S110
                pass
            try:
                if (
                    hasattr(self, "_indicator_panel")
                    and self._indicator_panel is not None
                    and hasattr(self._indicator_panel, "refresh_privacy_dot")
                ):
                    self._indicator_panel.refresh_privacy_dot()
            except Exception:  # noqa: S110
                pass

        def _setup_tooltips(self) -> None:
            """Build `_abbreviation_tooltips` and rescan widgets every 5000 ms."""
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app:
                current = app.styleSheet() or ""
                app.setStyleSheet(
                    current + "\nQToolTip { font-size: 12px; padding: 8px; "
                    f"background: {ds.SURFACE_CONTROL}; color: {ds.TEXT_HIGH}; border: "
                    f"1px solid {ds.MAIN_TOOLTIP_BORDER}; }}"
                )

            self._abbreviation_tooltips = {
                "P/L": "Profit / Loss - net gain or loss from closed trades",
                "P&L": "Profit and Loss - same as P/L",
                "Realised": "Realised P/L - profit/loss from positions that have been closed",
                "Locked": "Locked - value committed to open positions less than 30 days old",
                "Mature": "Mature - profits from positions filled 30+ days ago, safely withdrawable",
                "Spendable": "Spendable Profits - estimated expendable liquidity from mature positions",
                "Extended": "Extended Position - extra position created when accumulated profit reaches position size",
                "Grid": "Grid Mode - stacked buy/sell pairs at fixed price intervals",
                "Scrumming": "Speculative Scrumming - TA-driven delta trading against a target balance",
                "Phantom": "Phantom Bot - shadow bot analyzing a different timeframe",
                "Folding": "Profit Folding - distributing realized sell profits back into buy positions",
                "Distribution": "Upward Distribution - distributing accumulated asset into sell positions",
                "TA": "Technical Analysis - mathematical indicators computed from price/volume data",
                "BB": "Bollinger Bands - volatility envelope 2 std deviations from a moving average",
                "MACD": "Moving Average Convergence Divergence - trend-following momentum indicator",
                "RSI": "Relative Strength Index - momentum oscillator measuring overbought/oversold (0-100)",
                "StochRSI": "Stochastic RSI - RSI applied to its own values, more sensitive to extremes",
                "EMA": "Exponential Moving Average - weighted average favoring recent data points",
                "SMA": "Simple Moving Average - arithmetic mean of prices over N periods",
                "Ichimoku": "Ichimoku Cloud - trend, momentum, and support/resistance indicator system",
                "Vortex": "Vortex Indicator - identifies trend direction and reversals using true range",
                "Slingshot": "Slingshot Entry - custom momentum signal detecting sharp directional moves",
                "TF": "Timeframe - candle duration (1m, 5m, 15m, 1h, 4h, 1d, 1w)",
                "OHLCV": "Open, High, Low, Close, Volume - the five data points per candle",
                "Vol": "Volume - total value traded in a given period",
                "Volat": "Volatility - measure of price variation; higher = more price movement",
                "API": "Application Programming Interface - how this app communicates with exchanges",
                "WS": "WebSocket - persistent bidirectional connection for real-time data",
                "CCXT": "CryptoCurrency eXchange Trading - library connecting to 100+ exchanges",
                "Bots": "Automated trading agents executing buy/sell strategies continuously",
                "IDLE": "Bot is created but not started. Click Start to begin.",
                "RUNNING": "Bot is actively monitoring the market and executing trades.",
                "PAUSED": "Bot is suspended. Open orders remain but no new trades.",
                "COOLDOWN": "Bot hit max errors and is waiting before retrying.",
                "Exch": "Exchange - cryptocurrency trading platform",
            }

            QTimer.singleShot(500, self._apply_abbreviation_tooltips)
            self._tooltip_timer = QTimer(self)
            self._tooltip_timer.timeout.connect(self._apply_abbreviation_tooltips)
            self._tooltip_timer.start(5000)

        def _apply_abbreviation_tooltips(self) -> None:
            """Set a tooltip on each QLabel, QPushButton and QGroupBox lacking one."""
            for label in self.findChildren(QLabel):
                text = label.text()
                if not text or label.toolTip():
                    continue
                for abbrev, explanation in self._abbreviation_tooltips.items():
                    if abbrev in text:
                        label.setToolTip(explanation)
                        break

            for btn in self.findChildren(QPushButton):
                text = btn.text()
                if not text or btn.toolTip():
                    continue
                for abbrev, explanation in self._abbreviation_tooltips.items():
                    if abbrev in text:
                        btn.setToolTip(explanation)
                        break

            for gb in self.findChildren(QGroupBox):
                text = gb.title()
                if not text or gb.toolTip():
                    continue
                for abbrev, explanation in self._abbreviation_tooltips.items():
                    if abbrev in text:
                        gb.setToolTip(explanation)
                        break

        def _on_api_event(self, entry: dict) -> None:
            """Append one API entry to `_api_log_view`, refusing off-thread calls."""
            # Touching a widget off the GUI thread ends the process through Qt.
            import threading as _threading

            current = _threading.current_thread().name
            origin = entry.get("_thread_name", "unknown")
            if current != "MainThread":
                try:
                    from pathlib import Path as _P
                    from datetime import datetime as _dt

                    log_path = (
                        _P.home()
                        / ".acervator_logs"
                        / f"thread_violation_{_dt.now().strftime('%Y%m%d')}.log"
                    )
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(
                            f"[{_dt.now().isoformat()}] _on_api_event "
                            f"called on thread={current} "
                            f"(origin={origin}) — REFUSED to avoid Qt "
                            f"qFatal. Entry action={entry.get('action')}.\n"
                        )
                except Exception:
                    # No widget is touched here: this branch runs on the wrong thread.
                    logger.exception(
                        "_on_api_event called on thread=%s "
                        "(origin=%s) - REFUSED to avoid Qt qFatal; "
                        "the thread_violation log file could not "
                        "be written",
                        current,
                        origin,
                    )
                return

            import time as _time

            ts = _time.strftime("%H:%M:%S", _time.localtime(entry["timestamp"]))

            exchange_tag = entry["exchange"].upper()
            plain_lines = [
                f"[{ts}] {exchange_tag} {entry['action']}",
                f"  Reason: {entry['reason']}",
            ]
            if entry.get("endpoint"):
                plain_lines.append(f"  Endpoint: {entry['endpoint']}")
            if entry.get("result"):
                plain_lines.append(f"  Result: {entry['result']}")
            if entry.get("elapsed_ms", 0) > 0:
                plain_lines.append(f"  Response: {entry['elapsed_ms']}ms")
            if entry.get("data_usage"):
                plain_lines.append(f"  Data usage: {entry['data_usage']}")

            block_text = "\n".join(plain_lines)
            if getattr(self, "_api_log_paused", False):
                buf = self._api_log_pause_buffer
                buf.append(block_text)
                cap = self._api_log_pause_buffer_cap
                if len(buf) > cap:
                    del buf[: len(buf) - cap]
                return
            self._api_log_view.appendPlainText(block_text)
            sb = self._api_log_view.verticalScrollBar()
            if sb.value() >= sb.maximum() - 20:
                sb.setValue(sb.maximum())

        def _report_stored_credentials_on_startup(self) -> None:
            """Report which configured exchanges hold a stored credential.

            Reads the settings entries at launch and writes one line per
            exchange to the Activity Log, the notification spool and the
            API panel. No exchange is contacted, so a stored credential
            is unverified here: a revoked, expired, wrong or malformed
            key is indistinguishable from a working one until the first
            authenticated call.
            """
            from ..exchange.api_logger import get_api_log

            _log = get_api_log()

            exchanges = self._settings.list_exchanges() if self._settings else []
            if not exchanges:
                self._status_log.log(
                    "No exchanges configured. Go to Settings to add one.", "warning"
                )
                self._spool.notify("No exchanges configured.", "warning")
                _log.record(
                    exchange="app",
                    action="STARTUP_CHECK",
                    reason="Application launched, reading exchanges from settings",
                    result="No exchanges configured",
                    level="warning",
                    data_usage="User needs to add an exchange in Settings before creating bots",
                )
                return

            _log.record(
                exchange="app",
                action="STARTUP_CHECK",
                reason=f"Application launched, reading {len(exchanges)} exchange(s)",
                result="Reading settings. No exchange is contacted.",
                level="info",
                data_usage="Each exchange is read for a stored API credential",
            )

            self._status_log.log(
                f"Reading stored credentials for {len(exchanges)} exchange(s)...",
            )
            for exch in exchanges:
                eid = exch.get("exchange_id", "")
                has_key = bool(exch.get("api_key_enc", ""))
                if has_key:
                    self._status_log.log(
                        f"  {eid.capitalize()}: credentials stored, unverified", "info"
                    )
                    self._spool.notify(
                        f"{eid.capitalize()}: credentials stored, unverified",
                        "info",
                    )
                    _log.record(
                        exchange=eid,
                        action="CREDENTIAL_CHECK",
                        reason=f"Checking if {eid.capitalize()} has stored API credentials",
                        result=(
                            "Encrypted credentials found in settings. "
                            "Not verified against the exchange."
                        ),
                        level="info",
                        data_usage=(
                            "A revoked, expired or malformed key reads the "
                            "same as a working one here."
                        ),
                    )
                else:
                    self._status_log.log(
                        f"  {eid.capitalize()}: no credentials - add in Settings",
                        "warning",
                    )
                    self._spool.notify(
                        f"{eid.capitalize()}: no API credentials", "warning"
                    )
                    _log.record(
                        exchange=eid,
                        action="CREDENTIAL_CHECK",
                        reason=f"Checking if {eid.capitalize()} has stored API credentials",
                        result="No credentials found. Cannot make authenticated API calls.",
                        level="warning",
                        data_usage="User must add API key and secret in Settings before trading on this exchange.",
                    )

        @Slot()
        def _refresh_dashboard(self) -> None:
            if not self._bot_manager:
                return
            try:
                agg = self._bot_manager.get_aggregate_stats()
                _scr = float(agg.get("total_scrummed_usd", 0.0) or 0.0)
                _fld = float(agg.get("total_folded_usd", 0.0) or 0.0)
                self._stat_scrummed.set_value(f"${_scr:,.2f}")
                self._stat_folded.set_value(f"${_fld:,.2f}")
                self._stat_pnl.set_value(f"${agg['total_realised_pnl']:+,.4f}")
                self._stat_trades.set_value(str(agg["total_trades"]))
                self._stat_bots.set_value(str(agg["running"]))
                self._stat_errors.set_value(str(agg.get("total_errors_lifetime", 0)))

                exchanges = len(self._exchange_tabs)
                # One builder for both hosts: the React strip reads the same
                # `profits_payload` over the bridge.
                self._spendable_widget.update_profits(
                    header_strip_surface.profits_payload(agg, exchanges)
                )

                all_statuses = []
                for eid, tab in self._exchange_tabs.items():
                    exchange_statuses = self._bot_manager.list_bots_by_exchange(eid)
                    tab.update_bots(exchange_statuses)
                    all_statuses.extend(exchange_statuses)

                all_bot_statuses = self._bot_manager.list_bots()
                seen_ids = {s.get("bot_id") for s in all_statuses}
                for s in all_bot_statuses:
                    if s.get("bot_id") not in seen_ids:
                        all_statuses.append(s)

                # Unconditional: `update_bots([])` drops every widget when all bots go.
                try:
                    self._bot_viz.update_bots(all_statuses)
                except Exception as e:
                    logger.error("DASHBOARD: Bot Viz CRASHED: %s", e)
                    import traceback

                    traceback.print_exc()

                if all_statuses:
                    try:
                        self._charts_tab.update_charts(
                            all_statuses, bot_manager=self._bot_manager
                        )
                    except Exception as e:
                        logger.error("DASHBOARD: Asset Charts CRASHED: %s", e)
                        import traceback

                        traceback.print_exc()
                    try:
                        self._market_inspector.update_active_symbols(all_statuses)
                    except Exception as e:
                        logger.error("DASHBOARD: Market Inspector CRASHED: %s", e)
                        import traceback

                        traceback.print_exc()

                    try:
                        self._refresh_api_load_pill()
                    except Exception as _api_pill_exc:
                        logger.debug("API-load pill refresh raised: %s", _api_pill_exc)

                    try:
                        self._pump_currency_rates()
                    except Exception as _rate_exc:
                        logger.debug("currency rate pump raised: %s", _rate_exc)

                    try:
                        self._pump_market_pairs_scout()
                    except Exception as _scout_exc:
                        logger.debug("market pairs scout pump raised: %s", _scout_exc)

                    try:
                        self._dispatch_tracking_beep(all_statuses)
                    except Exception as exc:
                        logger.debug("tracking beep failed: %s", exc)
                else:
                    if not getattr(self, "_dash_empty_warned", False):
                        logger.warning(
                            "DASHBOARD: all_statuses EMPTY — tabs not fed. "
                            "exchange_tabs=%d, list_bots=%d",
                            len(self._exchange_tabs),
                            len(all_bot_statuses),
                        )
                        self._dash_empty_warned = True

                if self._bot_manager:
                    try:
                        all_bot_statuses = self._bot_manager.list_bots()
                        self._indicator_panel.update_bot_list(all_bot_statuses)
                        self._wire_ivp_snapshot_dir()
                        sel_bid = self._indicator_panel.selected_bot_id
                        if sel_bid:
                            bot = self._bot_manager.get_bot(sel_bid)
                            if bot and getattr(bot, "_last_summary", None):
                                summary = bot._last_summary
                                tf = (
                                    getattr(bot.config, "ta_timeframe", None)
                                    or getattr(summary, "timeframe", None)
                                    or "1h"
                                )
                                parent_net = float(summary.net_score)
                                parent_tf_data = {
                                    "bullish": summary.bullish_count,
                                    "bearish": summary.bearish_count,
                                    "neutral": summary.neutral_count,
                                    "net_score": parent_net,
                                    "confidence": summary.consensus_confidence,
                                    "direction": summary.consensus_direction.name,
                                    "signals": [
                                        {
                                            "indicator": s.indicator,
                                            "direction": s.direction.name,
                                            "confidence": s.confidence,
                                            "details": getattr(s, "details", {}),
                                        }
                                        for s in summary.signals
                                    ],
                                    "locks": [],
                                }
                                merged: dict = {tf: parent_tf_data}
                                composite_net = parent_net
                                try:
                                    if getattr(bot, "_phantoms_enabled", False):
                                        pmulti = (
                                            bot.get_multi_tf_summary()
                                            if hasattr(bot, "get_multi_tf_summary")
                                            else {}
                                        )
                                        for p_tf, p_data in (pmulti or {}).items():
                                            if p_tf == tf:
                                                continue
                                            merged[p_tf] = dict(p_data)
                                        from ..trading.phantom_balance import (
                                            tf_rank as _tf_rank,
                                        )

                                        num = parent_net * max(1, _tf_rank(tf))
                                        den = max(1, _tf_rank(tf))
                                        for p_tf, p_data in (pmulti or {}).items():
                                            if p_tf == tf:
                                                continue
                                            p_rank = _tf_rank(p_tf)
                                            if p_rank <= _tf_rank(tf):
                                                continue
                                            p_conf = float(
                                                p_data.get("confidence", 0) or 0
                                            )
                                            if p_conf < 0.30:
                                                continue
                                            p_net = float(
                                                p_data.get("net_score", 0) or 0
                                            )
                                            num += p_net * p_rank * p_conf
                                            den += p_rank * p_conf
                                        if den > 0:
                                            composite_net = num / den
                                except Exception as _cp_exc:
                                    logger.debug(
                                        "phantom composite Net calc raised: %s", _cp_exc
                                    )
                                parent_tf_data["composite_net"] = composite_net
                                symbol = bot.config.symbol
                                self._indicator_panel.update_data(merged, symbol)
                                self._indicator_panel.remember_ta(
                                    sel_bid, symbol, merged
                                )
                                logger.debug(
                                    "IVP feed: %s %s -> %d timeframe(s)",
                                    sel_bid[:8],
                                    symbol,
                                    len(merged),
                                )
                            else:
                                _sym = (
                                    ""
                                    if bot is None
                                    else getattr(bot.config, "symbol", "") or ""
                                )
                                _cause, _detail = self._ivp_empty_state_cause(
                                    bot, sel_bid
                                )
                                self._indicator_panel.show_no_data(
                                    bot_id=sel_bid,
                                    symbol=_sym,
                                    cause=_cause,
                                    detail=_detail,
                                )
                        else:
                            self._indicator_panel.show_no_data(cause="no_selection")
                    except Exception as exc:
                        logger.error("DASHBOARD: Indicator panel CRASHED: %s", exc)

                if all_statuses:
                    if (
                        hasattr(self, "_exchange_connectors")
                        and self._exchange_connectors
                    ):
                        try:  # noqa: SIM105
                            self._schedule_coalesced(
                                "_pending_chart_fetch",
                                self._charts_tab.fetch_chart_data(
                                    self._exchange_connectors
                                ),
                            )
                        except Exception:  # noqa: S110
                            pass

                try:
                    if self._risk_manager:
                        from ..core.notifications import AlertEvent

                        new_alerts = self._risk_manager.evaluate(self._bot_manager)
                        for alert in new_alerts:
                            if alert.severity == "critical":
                                self._notif_manager.send(
                                    AlertEvent.DRAWDOWN_CRITICAL,
                                    f"Risk: {alert.rule_name}",
                                    alert.message,
                                )

                    if self._analytics and hasattr(self, "_last_equity_snap"):
                        if time.time() - self._last_equity_snap >= 10:
                            self._analytics.snapshot_equity(self._bot_manager)
                            self._last_equity_snap = time.time()
                    elif self._analytics:
                        self._analytics.snapshot_equity(self._bot_manager)
                        self._last_equity_snap = time.time()

                    if self._crash_recovery:
                        self._crash_recovery.save_snapshot(self._bot_manager)

                    if self._notif_manager and agg:
                        self._notif_manager.check_pnl_milestone(
                            agg.get("total_realised_pnl", 0)
                        )

                    if not hasattr(self, "_last_tab_refresh"):
                        self._last_tab_refresh = 0
                    if time.time() - self._last_tab_refresh >= 4:
                        self._last_tab_refresh = time.time()
                        if self._analytics_tab:
                            self._analytics_tab.refresh(self._analytics)
                        if self._risk_tab:
                            self._risk_tab.refresh(self._risk_manager)
                        if self._journal_tab:
                            self._journal_tab.refresh(
                                self._journal, self._recon_engine, self._crash_recovery
                            )
                        if self._alerts_tab:
                            self._alerts_tab.refresh(self._notif_manager)

                    if (
                        self._bot_manager
                        and self._bot_manager._live_monitor
                        and self._bot_manager._live_monitor.should_check
                    ):
                        self._schedule_async(self._bot_manager.check_live_monitor())

                except Exception as sub_exc:
                    logger.error("DASHBOARD: Subsystem update error: %s", sub_exc)

            except Exception as exc:
                logger.error("DASHBOARD: _refresh_dashboard CRASHED: %s", exc)
                import traceback

                traceback.print_exc()

        def _is_equity_exchange(self, exchange_id: str) -> bool:
            """Return True if this exchange ID belongs to the stock/equity layer."""
            return exchange_id.lower() in self._equity_exchange_ids

        def add_exchange_tab(self, exchange_id: str, display_name: str) -> None:
            """Add exchange tab to the correct layer (crypto or stock)."""
            is_equity = self._is_equity_exchange(exchange_id)

            if is_equity:
                target_tabs = self._stock_exchange_tabs
                target_widget = self._stock_tab_widget
                target_ph_attr = "_stock_placeholder"
            else:
                target_tabs = self._crypto_exchange_tabs
                target_widget = self._crypto_tab_widget
                target_ph_attr = "_crypto_placeholder"

            if exchange_id in target_tabs:
                return

            ph = getattr(self, target_ph_attr, None)
            if ph is not None:
                idx = target_widget.indexOf(ph)
                if idx >= 0:
                    target_widget.removeTab(idx)
                setattr(self, target_ph_attr, None)
                if target_tabs is self._exchange_tabs:
                    self._empty_placeholder = None

            tab = ExchangeTab(
                exchange_id,
                display_name,
                on_new_bot=self._create_bot,
                on_bot_clicked=self._on_bot_clicked,
                on_bot_cmd=self._on_bot_command,
                on_bot_fire=self._on_bot_fire,
                status_log=self._status_log,
            )
            target_widget.addTab(tab, display_name)
            target_tabs[exchange_id] = tab

            if target_tabs is self._exchange_tabs:
                self._exchange_tabs[exchange_id] = tab

            # `_landed` asks both layer widgets, never `target_widget`, the argument.
            _landed = "none"
            if self._stock_tab_widget.indexOf(tab) >= 0:
                _landed = "stock"
            elif self._crypto_tab_widget.indexOf(tab) >= 0:
                _landed = "crypto"
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _tr_emit

                _tr_emit(
                    "trading.12.002.postcondition.exchange_tab_routed",
                    actual=_landed,
                    expected="stock" if is_equity else "crypto",
                    context={
                        "exchange": exchange_id,
                        "stock_tabs": self._stock_tab_widget.count(),
                        "crypto_tabs": self._crypto_tab_widget.count(),
                        "in_layer_store": target_tabs.get(exchange_id) is tab,
                        "placeholder_dropped": ph is not None,
                    },
                )

        def _on_bot_error_for_log(self, event) -> None:
            """Append (timestamp, bot_id, error, consecutive) to `_error_log_buffer`."""
            try:
                from datetime import datetime as _dt

                _ts = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
                _bot_id = str(
                    getattr(event, "data", {}).get("bot_id", "")
                    or getattr(event, "bot_id", "")
                    or ""
                )
                _err = str(
                    getattr(event, "data", {}).get("error", "")
                    or getattr(event, "error", "")
                    or ""
                )
                _consec = int(getattr(event, "data", {}).get("consecutive", 0) or 0)
                self._error_log_buffer.append((_ts, _bot_id, _err, _consec))
            except Exception:
                logger.exception(
                    "bot.error capture failed; this error record "
                    "was dropped and the Errors card under-reports "
                    "by one"
                )

        @Slot()
        def _show_error_log_dialog(self) -> None:
            """Open the Error Log dialog built by `_build_error_log_dialog`."""
            try:
                dlg = self._build_error_log_dialog()
                dlg.exec()
            except Exception as exc:
                logger.exception("Error Log dialog raised: %s", exc)

        def _wire_manager(self):
            """Return `self._bot_manager.smart_wire_manager`, or None if unreachable."""
            try:
                mgr = getattr(self._bot_manager, "smart_wire_manager", None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("C06c: wire manager unreachable: %s", exc)
                return None
            return mgr

        def _wire_is_registered(self, src_id: str, tgt_id: str) -> bool:
            """True when `tgt_id` is in the source's outgoing wires, or no manager."""
            mgr = self._wire_manager()
            if mgr is None:
                return True
            try:
                return tgt_id in (mgr.get_outgoing_wires(src_id) or {})
            except Exception:
                logger.exception(
                    "C06c: wire read-back raised for %s -> %s; the "
                    "wire is reported as NOT confirmed",
                    src_id,
                    tgt_id,
                )
                return False

        def _topology_wire_collisions(
            self, wires: list, asset_to_bot: dict
        ) -> list[dict]:
            """Return one dict per proposal wire whose bot pair is already wired."""
            mgr = self._wire_manager()
            if mgr is None:
                return []
            out: list[dict] = []
            for w in wires or []:
                try:
                    src_asset = str(w.get("source_asset", "")).upper()
                    tgt_asset = str(w.get("target_asset", "")).upper()
                    src_id = asset_to_bot.get(src_asset, "")
                    tgt_id = asset_to_bot.get(tgt_asset, "")
                    if not src_id or not tgt_id or src_id == tgt_id:
                        continue
                    current = (mgr.get_outgoing_wires(src_id) or {}).get(tgt_id)
                    if current is None:
                        continue
                    out.append(
                        {
                            "source_asset": src_asset,
                            "target_asset": tgt_asset,
                            "source_id": src_id,
                            "target_id": tgt_id,
                            "current_pct": float(current),
                            "proposed_pct": float(w.get("pct", 0.0)),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("C06c: collision pre-flight skipped a wire: %s", exc)
            return out

        def _snapshot_wires_for_adopt(self, title: str):
            """Write the wires to a dated JSON file, keep the newest 20, return it."""
            import json
            from datetime import datetime

            mgr = self._wire_manager()
            if mgr is None:
                return None
            try:
                wires = mgr.export_wires()
            except Exception as exc:  # noqa: BLE001
                logger.warning("C06c: export_wires failed: %s", exc)
                return None
            try:
                # Read the StateManager's `_dir`, which may differ from `_DEFAULT_DIR`.
                sm = getattr(self._bot_manager, "_state_manager", None)
                base = getattr(sm, "_dir", None)
                if base is None:
                    from ..core.state_manager import _DEFAULT_DIR

                    base = _DEFAULT_DIR
                root = base / "topology_snapshots"
                root.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = root / f"wires_before_adopt.{ts}.json"
                dest.write_text(
                    json.dumps(
                        {"title": title, "taken_at": ts, "wires": wires}, indent=2
                    ),
                    encoding="utf-8",
                )
                for old in sorted(root.glob("wires_before_adopt.*.json"))[:-20]:
                    old.unlink(missing_ok=True)
                return dest
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "C06c: wire snapshot FAILED (%s) — the adopt will "
                    "proceed with no restore point",
                    exc,
                )
                return None

        def _wire_ivp_snapshot_dir(self) -> None:
            """Point the Indicator Panel's TA snapshots at the live state directory."""
            if getattr(self, "_ivp_snapshot_dir_wired", False):
                return
            panel = getattr(self, "_indicator_panel", None)
            if panel is None or not hasattr(panel, "set_ta_state_dir"):
                return
            try:
                sm = getattr(self._bot_manager, "_state_manager", None)
                base = getattr(sm, "_dir", None)
                if base is None:
                    from ..core.state_manager import _DEFAULT_DIR

                    base = _DEFAULT_DIR
                panel.set_ta_state_dir(base)
                self._ivp_snapshot_dir_wired = True
                logger.info("IVP: TA snapshots resolved to %s", base)
            except (AttributeError, ImportError, OSError, TypeError, ValueError) as exc:
                logger.warning(
                    "IVP: TA snapshot directory not wired (%s); stored "
                    "readings will fall back to the default state dir",
                    exc,
                )

        def _ivp_cached_candle_count(self, bot) -> int | None:
            """Candles MarketDataPool holds for this bot; None when it has no slot."""
            try:
                pool = _ammo_price_pool()
                if pool is None:
                    return None
                from ..exchange.data_pool import _candle_key

                key = _candle_key(
                    getattr(bot.config, "exchange_id", ""),
                    getattr(bot.config, "symbol", ""),
                    getattr(bot.config, "ta_timeframe", "1h") or "1h",
                )
                entry = getattr(pool, "_candles", {}).get(key)
                if entry is None:
                    return None
                return len(getattr(entry, "candles", None) or [])
            except (AttributeError, ImportError, TypeError) as exc:
                logger.debug("IVP: candle count unavailable: %s", exc)
                return None

        def _ivp_empty_state_cause(self, bot, bot_id: str = "") -> tuple:
            """Return one (cause_token, detail) pair saying why this bot shows no TA."""
            if bot is None:
                return "bot_missing", {"bot_id": str(bot_id or "")}

            detail: dict = {"bot_id": str(bot_id or "")}
            state = ""
            try:
                state = str(getattr(getattr(bot, "state", None), "value", "")).lower()
            except (AttributeError, TypeError, ValueError) as exc:
                logger.debug("IVP: bot state unreadable: %s", exc)

            if state in ("idle", "stopped"):
                detail["state"] = state
                return "not_running", detail
            if state == "error":
                detail["error"] = str(
                    getattr(getattr(bot, "stats", None), "last_error", "") or ""
                )
                return "bot_error", detail

            try:
                parked_ticks = int(getattr(bot, "_at_target_counter", 0) or 0)
            except (TypeError, ValueError):
                parked_ticks = 0
            if parked_ticks > 0:
                try:
                    position = float(getattr(bot, "position_value_usd", 0.0) or 0.0)
                    target = float(getattr(bot, "_target_balance", 0.0) or 0.0)
                except (TypeError, ValueError):
                    position, target = 0.0, 0.0
                detail.update(
                    {
                        "position": position,
                        "target": target,
                        "delta": position - target,
                    }
                )
                return "parked_at_target", detail

            cached = self._ivp_cached_candle_count(bot)
            if cached is not None and cached < 30:
                detail.update(
                    {
                        "candles": cached,
                        "symbol": getattr(bot.config, "symbol", "") or "",
                        "timeframe": (getattr(bot.config, "ta_timeframe", "") or "1h"),
                    }
                )
                return "too_few_candles", detail

            return "cold_start", detail

        def _report_adopt_orphans(self, created_ids: list) -> None:
            """Log the bot ids an aborted adopt created and left unwired."""
            if not created_ids:
                return
            self._status_log.log(
                f"Topology adopt: {len(created_ids)} bot(s) were already "
                f"created before the abort and remain: "
                f"{', '.join(str(b)[:8] for b in created_ids)}. "
                f"They are not wired. Remove them from the Bot Swarm tab "
                f"if they are not wanted.",
                "warning",
            )

        def _adopt_topology_proposal(self, proposal: dict) -> None:
            """Confirm, open the wizard for each new bot, then emit `wire.created`."""
            from PySide6.QtWidgets import QMessageBox

            if not isinstance(proposal, dict) or not proposal.get("bots"):
                return
            if not self._bot_manager:
                QMessageBox.warning(
                    self, "Adopt topology", "Bot manager not available."
                )
                return

            new_bots = [
                b for b in proposal.get("bots", []) if not b.get("existing_bot_id")
            ]
            wires = list(proposal.get("wires", []))
            new_count = len(new_bots)
            new_budget = sum(
                float(b.get("suggested_target_usd", 0.0)) for b in new_bots
            )

            asset_to_bot: dict[str, str] = {}
            for b in proposal.get("bots", []):
                if b.get("existing_bot_id"):
                    asset_to_bot[str(b.get("asset", "")).upper()] = str(
                        b["existing_bot_id"]
                    )

            # Only existing-to-existing pairs can collide: a bot that does not
            # exist yet has no wires.
            collisions = self._topology_wire_collisions(wires, asset_to_bot)

            summary_lines = [
                f"Adopt proposal: {proposal.get('title', 'topology')}",
                "",
                f"New bots to create: {new_count} (${new_budget:,.0f} total)",
                f"Wires to draw: {len(wires)}",
            ]
            if collisions:
                summary_lines += [
                    "",
                    f"{len(collisions)} of these wire(s) ALREADY EXIST. "
                    f"Adopting CHANGES them:",
                ]
                for c in collisions[:12]:
                    summary_lines.append(
                        f"    {c['source_asset']} -> {c['target_asset']}: "
                        f"{c['current_pct']:.2f}% -> "
                        f"{c['proposed_pct']:.2f}%"
                    )
                if len(collisions) > 12:
                    summary_lines.append(f"    ... and {len(collisions) - 12} more")
                summary_lines.append(
                    "The previous rates are saved to a snapshot file "
                    "before anything is applied."
                )
            summary_lines += [
                "",
                "The Bot Wizard will open for each new bot; cancel any "
                "wizard to abort the entire adoption. Existing bots are "
                "not modified.",
            ]
            reply = QMessageBox.question(
                self,
                "Adopt topology",
                "\n".join(summary_lines),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Ok:
                self._status_log.log(
                    "Topology adoption cancelled at confirm gate.", "info"
                )
                return

            snap = self._snapshot_wires_for_adopt(
                str(proposal.get("title", "topology"))
            )
            if snap:
                self._status_log.log(
                    f"Topology adopt: wire snapshot saved to {snap.name}", "info"
                )

            created_ids: list[str] = []
            for i, b in enumerate(new_bots, start=1):
                asset = str(b.get("asset", "")).upper()
                target_usd = float(b.get("suggested_target_usd", 25.0))
                self._status_log.log(
                    f"Topology adopt: creating bot {i}/{new_count} — "
                    f"{asset} target ${target_usd:.0f}",
                    "info",
                )
                before_ids = {
                    str(s.get("bot_id", ""))
                    for s in (self._bot_manager.list_bots() or [])
                }
                try:
                    self._create_bot(
                        exchange_id="",
                        defaults_override={"default_target_balance": target_usd},
                    )
                except Exception as _cb_exc:  # noqa: BLE001
                    logger.exception("Topology adopt: _create_bot raised: %s", _cb_exc)
                    self._status_log.log(
                        f"Topology adopt aborted: bot creation raised "
                        f"({_cb_exc}). No wires drawn.",
                        "error",
                    )
                    return
                after = self._bot_manager.list_bots() or []
                after_ids = {str(s.get("bot_id", "")) for s in after}
                new_ids = after_ids - before_ids
                if not new_ids:
                    self._status_log.log(
                        f"Topology adopt aborted at bot {i}/{new_count} "
                        f"({asset}): wizard cancelled. No wires drawn.",
                        "warning",
                    )
                    self._report_adopt_orphans(created_ids)
                    return
                # The wizard can create several bots; the lowest sorted id is mapped.
                chosen = sorted(new_ids)[0]

                # The wizard opens with exchange_id="" and only the target balance set.
                made: dict = next(
                    (s for s in after if str(s.get("bot_id", "")) == chosen), {}
                )
                made_symbol = str(made.get("symbol", "") or "")
                made_base = made_symbol.split("/")[0].split("-")[0].upper()
                if asset and made_base and made_base != asset:
                    self._status_log.log(
                        f"Topology adopt ABORTED at bot {i}/{new_count}: "
                        f"the proposal asked for {asset} but the wizard "
                        f"created {made_symbol}. Binding {asset} to that "
                        f"bot would route this topology's wires through "
                        f"the wrong asset. No wires drawn.",
                        "error",
                    )
                    QMessageBox.warning(
                        self,
                        "Adopt topology",
                        f"Adoption stopped.\n\nStep {i} of {new_count} "
                        f"asked for a {asset} bot, but the bot that was "
                        f"created trades {made_symbol}.\n\nNo wires have "
                        f"been drawn. Any bots already created are "
                        f"listed in the status log and were left in "
                        f"place.",
                    )
                    self._report_adopt_orphans(created_ids + [chosen])
                    return
                if asset and not made_base:
                    logger.warning(
                        "Topology adopt: bot %s reports no symbol; "
                        "binding %s to it UNVERIFIED",
                        chosen,
                        asset,
                    )
                    self._status_log.log(
                        f"Topology adopt: could not read a symbol from "
                        f"the new bot; binding {asset} unverified.",
                        "warning",
                    )
                created_ids.append(chosen)
                asset_to_bot[asset] = chosen

            changed_pairs = {(c["source_asset"], c["target_asset"]) for c in collisions}

            wires_drawn = 0
            wires_changed = 0
            for w in wires:
                src_asset = str(w.get("source_asset", "")).upper()
                tgt_asset = str(w.get("target_asset", "")).upper()
                pct = float(w.get("pct", 0.0))
                src_id = asset_to_bot.get(src_asset, "")
                tgt_id = asset_to_bot.get(tgt_asset, "")
                if not src_id or not tgt_id or src_id == tgt_id:
                    self._status_log.log(
                        f"Topology adopt: skip wire {src_asset}→"
                        f"{tgt_asset} (unresolved bot id)",
                        "warning",
                    )
                    continue
                if (src_asset, tgt_asset) in changed_pairs:
                    wires_changed += 1
                try:
                    self._bus.emit(
                        "wire.created", source_id=src_id, target_id=tgt_id, pct=pct
                    )
                except Exception as _emit_exc:  # noqa: BLE001
                    logger.exception("Topology adopt: wire emit raised: %s", _emit_exc)
                    continue
                # Counted from the engine read-back: the emit above reports no refusal.
                if self._wire_is_registered(src_id, tgt_id):
                    wires_drawn += 1
                else:
                    self._status_log.log(
                        f"Topology adopt: {src_asset}→{tgt_asset} @ "
                        f"{pct:.2f}% was REFUSED by the wire engine and "
                        f"is not routing profit",
                        "error",
                    )

            tail = (
                f" ({wires_changed} replaced an existing rate)" if wires_changed else ""
            )
            self._status_log.log(
                f"Topology adopted: {proposal.get('title','')} — "
                f"{new_count} new bot(s), {wires_drawn}/{len(wires)} "
                f"wire(s) drawn{tail}.",
                "success" if wires_drawn or not wires else "warning",
            )
            try:
                self._spool.notify(
                    f"Topology adopted: {new_count} bot(s), "
                    f"{wires_drawn} wire(s){tail}",
                    "success",
                )
            except Exception as _spool_exc:  # noqa: BLE001
                logger.warning("Topology adopt: spool notify failed: %s", _spool_exc)

        def _build_topology_proposals(self) -> list[dict]:
            """Build detector context from scout, roster and inspector, then rank."""
            try:
                from ..trading.topology_proposals import detect_all_topologies
                from ..trading.market_inspector import get_shared_inspector
                from ..exchange.market_pairs_scout import get_scout
            except Exception as _imp_exc:  # noqa: BLE001
                logger.debug("topology proposals unavailable: %s", _imp_exc)
                return []

            # Aggregated across every polled exchange; the highest-volume row wins.
            tickers: dict[str, dict] = {}
            try:
                scout = get_scout()
                for eid, book in getattr(scout, "_snapshots", {}).items():
                    for _sym, snap in (book or {}).items():
                        base = (snap.base or "").upper()
                        quote = (snap.quote or "").upper()
                        if not base or quote not in ("USD", "USDC"):
                            continue
                        cur = tickers.get(base)
                        vol = float(getattr(snap, "volume_24h", 0.0) or 0.0)
                        if cur is None or vol > float(
                            cur.get("baseVolume", 0.0) or 0.0
                        ):
                            tickers[base] = {
                                "quote": quote,
                                "symbol": snap.symbol,
                                "baseVolume": vol,
                                "last": float(getattr(snap, "last", 0.0) or 0.0),
                                "existing_bot_id": "",
                            }
            except Exception as _scout_exc:  # noqa: BLE001
                logger.debug("topology: scout snapshot unavailable: %s", _scout_exc)

            bots_snapshot: list[dict] = []
            try:
                if self._bot_manager:
                    for st in self._bot_manager.list_bots() or []:
                        sym = st.get("symbol", "") or ""
                        base = sym.split("/")[0].upper() if "/" in sym else ""
                        if not base:
                            continue
                        if base in tickers and not tickers[base]["existing_bot_id"]:
                            tickers[base]["existing_bot_id"] = str(st.get("bot_id", ""))
                        bots_snapshot.append(
                            {
                                "bot_id": st.get("bot_id", ""),
                                "asset": base,
                                "quote": (
                                    sym.split("/")[1].upper() if "/" in sym else "USD"
                                ),
                                "symbol": sym,
                                "position_val": float(
                                    st.get("stats", {}).get("position_value", 0.0)
                                    or 0.0
                                ),
                                "target_balance": float(
                                    st.get("target_balance", 0.0) or 0.0
                                ),
                            }
                        )
            except Exception as _bot_exc:  # noqa: BLE001
                logger.debug("topology: bot snapshot unavailable: %s", _bot_exc)

            opposing: list[dict] = []
            closes_by_asset: dict[str, list] = {}
            try:
                inspector = get_shared_inspector()
                closes_by_asset = dict(getattr(inspector, "last_closes", {}) or {})
                for op in getattr(inspector, "_last_pairs", []) or []:
                    l_sym = op.long_side.symbol
                    s_sym = op.short_side.symbol
                    l_asset = (
                        l_sym.split("/")[0].upper() if "/" in l_sym else l_sym.upper()
                    )
                    s_asset = (
                        s_sym.split("/")[0].upper() if "/" in s_sym else s_sym.upper()
                    )
                    opposing.append(
                        {
                            "long_asset": l_asset,
                            "short_asset": s_asset,
                            "corr": float(op.correlation_30d),
                            "method": op.method,
                        }
                    )
            except Exception as _op_exc:  # noqa: BLE001
                logger.debug("topology: opposing-pairs unavailable: %s", _op_exc)

            ctx = {
                "tickers_by_asset": tickers,
                "closes_by_asset": closes_by_asset,
                "opposing_pairs": opposing,
                "bots_snapshot": bots_snapshot,
            }
            try:
                return detect_all_topologies(ctx)
            except Exception as _det_exc:  # noqa: BLE001
                logger.exception("topology: detect_all_topologies raised: %s", _det_exc)
                return []

        def _build_error_log_dialog(self):
            """Build and return the Error Log QDialog without executing it."""
            from PySide6.QtWidgets import (
                QDialog,
                QVBoxLayout,
                QHBoxLayout,
                QLabel,
                QTabWidget,
                QTableWidget,
                QTableWidgetItem,
                QPushButton,
                QHeaderView,
                QAbstractItemView,
            )

            dlg = QDialog(self)
            dlg.setWindowTitle("Error Log")
            dlg.resize(900, 480)
            v = QVBoxLayout(dlg)

            try:
                agg = self._bot_manager.get_aggregate_stats()
                _life = int(agg.get("total_errors_lifetime", 0) or 0)
            except Exception:
                _life = 0
            hdr = QLabel(
                f"<b>Errors:</b> {_life} &nbsp;·&nbsp; "
                f"<b>Buffered events:</b> "
                f"{len(self._error_log_buffer)} (capped at 200)"
            )
            hdr.setStyleSheet(f"padding: 6px 4px; color: {ds.MAIN_TABLE_HEADER};")
            v.addWidget(hdr)

            tabs = QTabWidget()
            v.addWidget(tabs, stretch=1)

            ev_tab = QTableWidget()
            ev_tab.setColumnCount(4)
            ev_tab.setHorizontalHeaderLabels(
                ["Timestamp", "Bot", "Consecutive", "Error"]
            )
            ev_tab.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            ev_tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
            events = list(reversed(list(self._error_log_buffer)))
            ev_tab.setRowCount(len(events))
            for row, (ts, bot_id, err, consec) in enumerate(events):
                ev_tab.setItem(row, 0, QTableWidgetItem(str(ts)))
                _bid_short = (
                    str(bot_id)[:8] + "…" if len(str(bot_id)) > 8 else str(bot_id)
                )
                ev_tab.setItem(row, 1, QTableWidgetItem(_bid_short))
                ev_tab.setItem(row, 2, QTableWidgetItem(str(consec)))
                ev_tab.setItem(row, 3, QTableWidgetItem(str(err)))
            tabs.addTab(ev_tab, f"Recent events ({len(events)})")

            snap = QTableWidget()
            snap.setColumnCount(5)
            snap.setHorizontalHeaderLabels(
                ["Bot", "Asset", "Lifetime errors", "Consecutive (now)", "Last error"]
            )
            snap.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
            snap.setEditTriggers(QAbstractItemView.NoEditTriggers)
            try:
                _bots = list(self._bot_manager._bots.values())
            except Exception:
                _bots = []
            snap.setRowCount(len(_bots))
            for row, bot in enumerate(_bots):
                try:
                    _bid = str(getattr(bot, "bot_id", ""))[:8]
                    _asset = str(getattr(bot.config, "target_asset", ""))
                    _tot = int(getattr(bot.stats, "total_errors", 0) or 0)
                    _con = int(getattr(bot.stats, "consecutive_errors", 0) or 0)
                    _last = str(getattr(bot.stats, "last_error", "") or "—")
                except Exception:
                    _bid, _asset, _tot, _con, _last = "?", "?", 0, 0, "?"
                snap.setItem(row, 0, QTableWidgetItem(_bid))
                snap.setItem(row, 1, QTableWidgetItem(_asset))
                snap.setItem(row, 2, QTableWidgetItem(str(_tot)))
                snap.setItem(row, 3, QTableWidgetItem(str(_con)))
                snap.setItem(row, 4, QTableWidgetItem(_last))
            tabs.addTab(snap, f"Per-bot snapshot ({len(_bots)})")

            btns = QHBoxLayout()
            btns.addStretch(1)
            btn_reset = QPushButton("Reset all errors")
            btn_reset.setToolTip(
                "Clear the rolling event buffer AND zero every "
                "bot's total_errors, consecutive_errors, and "
                "last_error snapshot. Cannot be undone."
            )

            def _reset_all_errors():
                self._error_log_buffer.clear()
                try:
                    for _bot in self._bot_manager._bots.values():
                        try:
                            _bot.stats.total_errors = 0
                            _bot.stats.consecutive_errors = 0
                            _bot.stats.last_error = ""
                        except Exception as _bot_reset_exc:  # noqa: BLE001
                            logger.warning(
                                "Reset all errors: one bot's counters "
                                "were NOT cleared (%s: %s); the error "
                                "card still counts it.",
                                type(_bot_reset_exc).__name__,
                                _bot_reset_exc,
                            )
                            continue
                    try:
                        self._bot_manager.save_all_state()
                    except Exception as _save_exc:  # noqa: BLE001
                        logger.warning(
                            "Reset all errors: state was cleared in "
                            "memory but NOT saved (%s: %s); a restart "
                            "will restore the old counters.",
                            type(_save_exc).__name__,
                            _save_exc,
                        )
                except Exception as _reset_exc:  # noqa: BLE001
                    logger.warning(
                        "Reset all errors: the bot roster could not be "
                        "walked (%s: %s); per-bot counters were left "
                        "as they were.",
                        type(_reset_exc).__name__,
                        _reset_exc,
                    )
                dlg.accept()

            btn_reset.clicked.connect(_reset_all_errors)
            btns.addWidget(btn_reset)
            btn_close = QPushButton("Close")
            btn_close.clicked.connect(dlg.accept)
            btns.addWidget(btn_close)
            v.addLayout(btns)
            return dlg

        def _on_bot_log(self, event) -> None:
            """Prefix each bot log line with [TICKER/last4] for the activity log."""
            message = event.data.get("message", "")
            if not (message and self._status_log):
                return
            bot_id = event.data.get("bot_id", "")
            prefix = ""
            if bot_id:
                try:
                    bot = (
                        self._bot_manager.get_bot(bot_id) if self._bot_manager else None
                    )
                    if bot is not None:
                        ticker = getattr(bot.config, "target_asset", "")
                        id_tail = bot_id[-4:] if len(bot_id) >= 4 else bot_id
                        if ticker:
                            prefix = f"[{ticker}/{id_tail}] "
                        else:
                            prefix = f"[{id_tail}] "
                    else:
                        prefix = (
                            f"[{bot_id[-8:]}] " if len(bot_id) >= 8 else f"[{bot_id}] "
                        )
                except Exception:
                    prefix = f"[{bot_id[-8:]}] " if len(bot_id) >= 8 else ""
            self._status_log.log(prefix + message, "info")

        def _on_wire_created(self, event) -> None:
            """Log whether the source bot has profit folding on; writes no config."""
            source_id = event.data.get("source_id", "")
            if not self._bot_manager:
                return
            bot = self._bot_manager.get_bot(source_id)
            if not bot:
                return
            if getattr(bot.config, "profit_folding_active", True):
                self._status_log.log(
                    f"Wire active: {source_id[:8]} " f"(profit folding is ON)",
                    "success",
                )
            else:
                self._status_log.log(
                    f"Wire active: {source_id[:8]} — NOTE: Profit "
                    f"Folding is OFF for this bot, so its fold-compound "
                    f"contribution will not fire. Scrum-time routing is "
                    f"unaffected. Enable it in Live Settings if you want "
                    f"compounding from this wire.",
                    "warning",
                )

        def _on_tf_lock_changed(self, event) -> None:
            """Set `_lock_timeframe` on each ScrummingBot coordinator from the event."""
            tf = event.data.get("timeframe", "")
            if not self._bot_manager:
                return
            from ..trading.scrumming_bot import ScrummingBot

            for bot in self._bot_manager._bots.values():
                if isinstance(bot, ScrummingBot) and hasattr(bot, "_coordinator"):
                    bot._coordinator._lock_timeframe = tf
            if tf:
                self._status_log.log(
                    f"TF Lock set: {tf} — Accumulation Bots will respect higher-TF direction",
                    "info",
                )

        def _init_live_monitor(self) -> None:
            """Initialize LiveMonitor from saved settings."""
            if not self._settings or not self._bot_manager:
                return
            ai_cfg = self._settings.get("ai_monitor", {})
            if ai_cfg.get("enabled") and ai_cfg.get("api_key"):
                self._bot_manager.configure_live_monitor(ai_cfg)
                phrase = ai_cfg.get("connect_phrase", "")[:20]
                self._status_log.log(
                    f"AI Monitor enabled (phrase: '{phrase}...', "
                    f"interval: {ai_cfg.get('interval_hours', 4)}h)",
                    "info",
                )
            else:
                self._status_log.log(
                    "AI Monitor: disabled (configure in Settings → AI Monitor)",
                    ds.TEXT_MUTED,
                )

        def _on_ai_feedback(self, event) -> None:
            """Update the AI status label, log the feedback, journal it when enabled."""
            data = event.data if hasattr(event, "data") else {}
            feedback = data.get("feedback", "")
            authenticated = data.get("authenticated", False)

            if hasattr(self, "_ai_monitor_label"):
                if authenticated:
                    self._ai_monitor_label.setText("AI: ✓ AUTH")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.SUCCESS}; font-size: 10px; padding: 0 8px; "
                        "font-family: Consolas; font-weight: bold;"
                    )
                else:
                    self._ai_monitor_label.setText("AI: ⚠ UNAUTH")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.WARNING}; font-size: 10px; padding: 0 8px; "
                        "font-family: Consolas; font-weight: bold;"
                    )
            if feedback:
                tag = "✓ AUTH" if authenticated else "⚠ UNAUTH"
                self._status_log.log(
                    f"[AI MONITOR {tag}] {feedback[:200]}",
                    ds.STATUS_AUTHENTICATED if authenticated else ds.WARNING,
                )
                ai_cfg = self._settings.get("ai_monitor", {}) if self._settings else {}
                if ai_cfg.get("log_feedback"):
                    try:
                        # _journal is reconciliation.TradeJournal, so the note
                        # goes in through record_from_trade as a JournalEntry.
                        self._journal.record_from_trade(
                            bot_id="AI_MONITOR",
                            symbol="SYSTEM",
                            action="AI_FEEDBACK",
                            side="neutral",
                            price=0.0,
                            quantity=0.0,
                            reason=feedback[:500],
                        )
                    except Exception:
                        logger.exception(
                            "AI feedback note was not written to " "the journal"
                        )

        def _on_bot_clicked(self, bot_id: str) -> None:
            if not self._bot_manager:
                return
            bot = self._bot_manager.get_bot(bot_id)
            if not bot:
                return

            from .variant_surface import BOT_LIVE_SETTINGS, surface_class

            _cls = surface_class(BOT_LIVE_SETTINGS)
            saved_geometry = None
            saved_tab_index = None
            current_bot = bot
            while current_bot is not None:
                dlg = _cls(current_bot, self._bot_manager, self)
                dlg.settings_changed.connect(self._on_live_settings_changed)
                if saved_geometry is not None:
                    try:  # noqa: SIM105
                        dlg.setGeometry(saved_geometry)
                    except Exception:  # noqa: S110
                        pass
                if saved_tab_index is not None:
                    try:  # noqa: SIM105
                        dlg._tabs.setCurrentIndex(int(saved_tab_index))
                    except Exception:  # noqa: S110
                        pass
                dlg.exec()
                try:
                    saved_geometry = dlg.geometry()
                except Exception:
                    saved_geometry = None
                try:
                    saved_tab_index = dlg.active_tab_index()
                except Exception:
                    saved_tab_index = None
                target_id = getattr(dlg, "_pending_navigate_to", None)
                if not target_id:
                    break
                next_bot = self._bot_manager.get_bot(target_id)
                if next_bot is None:
                    break
                current_bot = next_bot

        def _on_live_settings_changed(self, bot_id: str, changes: dict):
            """Log the changed live-settings fields and play the state-change sound."""
            self._status_log.log(
                f"Bot {bot_id[:8]}: settings updated live — "
                f"{', '.join(f'{k}={v}' for k, v in changes.items())}",
                "success",
            )
            from ..core.sound_engine import get_sound_engine

            get_sound_engine().play_state_change()

        def _schedule_async(self, coro):
            """Run `coro` on `_async_loop`, returning its Future or None on fallback."""
            if self._async_loop:
                return asyncio.run_coroutine_threadsafe(coro, self._async_loop)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, coro)
            return None

        def _schedule_coalesced(self, slot: str, coro):
            """Cancel the future in ``slot``, schedule ``coro`` and store it there.

            Every pump that must not stack a second in-flight task calls this,
            so no call site carries a coalescing rule of its own.
            """
            self._cancel_if_pending(getattr(self, slot, None))
            found = self._schedule_async(coro)
            setattr(self, slot, found)
            return found

        @staticmethod
        def _cancel_if_pending(fut) -> None:
            """Cancel `fut` when it exists and is not done; failures log at debug."""
            if fut is None:
                return
            try:
                if not fut.done():
                    fut.cancel()
            except Exception as _cancel_exc:  # noqa: BLE001 - cancel best-effort
                logger.debug(
                    "Pending future not cancelled: %s: %s",
                    type(_cancel_exc).__name__,
                    _cancel_exc,
                )

        def _connect_exchange_for_bot(self, bot) -> tuple[bool, str]:
            """Build a CCXTConnector from stored credentials; returns (ok, message)."""
            from ..exchange.api_logger import get_api_log

            _log = get_api_log()
            eid = bot.config.exchange_id

            _log.record(
                exchange=eid,
                action="BOT_CONNECT",
                reason=f"Connecting bot {bot.bot_id} to {eid.capitalize()}",
                result="Looking up stored credentials...",
                level="info",
                data_usage="Will authenticate with exchange API and verify balance",
            )

            exchanges = self._settings.list_exchanges() if self._settings else []
            exch_config = None
            for e in exchanges:
                if e.get("exchange_id") == eid:
                    exch_config = e
                    break

            if not exch_config:
                msg = f"Exchange {eid} not found in settings. Add it in Settings first."
                _log.record(
                    exchange=eid,
                    action="BOT_CONNECT_FAILED",
                    reason="No exchange configuration found",
                    result=msg,
                    level="error",
                    data_usage="Bot cannot start without exchange configuration",
                )
                return False, msg

            if not exch_config.get("api_key_enc"):
                msg = (
                    f"No API credentials for {eid.capitalize()}. Add them in Settings."
                )
                _log.record(
                    exchange=eid,
                    action="BOT_CONNECT_FAILED",
                    reason="No API credentials stored",
                    result=msg,
                    level="error",
                    data_usage="Bot requires authenticated API access to check balances and place orders",
                )
                return False, msg

            try:
                from ..core.encryption import decrypt

                master = f"qat_{self._settings.get('username', 'user')}_vault"
                api_key = decrypt(exch_config["api_key_enc"], master)
                api_secret = decrypt(exch_config["api_secret_enc"], master)
                # None means no stored passphrase; `sync_connect` still receives "".
                passphrase: str | None = None
                if exch_config.get("passphrase_enc"):
                    passphrase = decrypt(exch_config["passphrase_enc"], master)

                _log.record(
                    exchange=eid,
                    action="BOT_AUTHENTICATING",
                    reason="Credentials decrypted, connecting to exchange API",
                    result="Calling exchange.connect()...",
                    level="info",
                    data_usage="Will load markets and verify API key validity",
                )

                from ..exchange.ccxt_connector import CCXTConnector

                connector = CCXTConnector(eid)

                # Registered before `sync_connect`, which starts the scan thread.
                try:
                    connector.add_scan_symbol(bot.config.symbol)
                    if (
                        hasattr(self, "_trade_history_tab")
                        and self._trade_history_tab is not None
                    ):
                        connector.set_history_callback(
                            self._trade_history_tab.get_history_callback()
                        )
                except Exception as _exc:
                    logger.warning(
                        "MEM-231 pre-connect history wiring " "failed: %s", _exc
                    )

                connector.sync_connect(api_key, api_secret, passphrase or "")

                _log.record(
                    exchange=eid,
                    action="BOT_CONNECTED",
                    reason="Exchange API authenticated successfully",
                    result="Markets loaded, checking balances...",
                    level="success",
                    data_usage="Bot now has a live exchange connection for trading",
                )

                balances_raw = (
                    connector._ccxt_sync.fetch_balance()
                    if hasattr(connector, "_ccxt_sync")
                    else {}
                )

                base = bot.config.base_currency

                free_bals = (
                    balances_raw.get("free", {})
                    if isinstance(balances_raw, dict)
                    else {}
                )
                base_free = float(free_bals.get(base, 0) or 0)
                # Extractor mode passes no target asset to `check_start_balance`.
                from ..trading.bot_container import BotMode as _BM
                from src.trading.start_balance_check import check_start_balance

                _is_extractor_mode = bot.config.mode == _BM.EXTRACTOR

                if _is_extractor_mode:
                    _target_for_helper = ""
                    _target_free_for_helper = 0.0
                else:
                    _target_for_helper = bot.config.target_asset
                    _target_free_for_helper = float(
                        free_bals.get(_target_for_helper, 0) or 0
                    )

                _base_usd_price = None
                if _is_extractor_mode and base.upper() not in {
                    "USD",
                    "USDC",
                    "USDT",
                    "DAI",
                    "BUSD",
                    "PYUSD",
                    "FDUSD",
                }:
                    try:
                        if hasattr(connector, "_ccxt_sync"):
                            _t = connector._ccxt_sync.fetch_ticker(f"{base}/USD")
                            _base_usd_price = float(
                                _t.get("last") or _t.get("close") or 0 or 0
                            )
                            if _base_usd_price <= 0:
                                _base_usd_price = None
                    except Exception as _exc:
                        logger.warning(
                            "v3.20.66: could not fetch %s/USD price "
                            "for start-balance check: %s",
                            base,
                            _exc,
                        )
                        _base_usd_price = None

                _sufficient, _start_msg, bal_summary = check_start_balance(
                    is_extractor=_is_extractor_mode,
                    exchange_label=eid.capitalize(),
                    base=base,
                    base_free=base_free,
                    target=_target_for_helper,
                    target_free=_target_free_for_helper,
                    chunk_size_usd=float(
                        getattr(bot.config, "extractor_chunk_size_usd", 0) or 0
                    ),
                    target_balance=float(getattr(bot.config, "target_balance", 0) or 0),
                    base_usd_price=_base_usd_price,
                )

                if _is_extractor_mode:
                    _bc_reason = (
                        f"Checking available {base} pool for "
                        f"Extractor bot {bot.bot_id}"
                    )
                    _bc_data = (
                        f"Extractor needs {base} pool to fund "
                        f"chunks. Chunk size: "
                        f"${float(getattr(bot.config, 'extractor_chunk_size_usd', 0) or 0):.2f}"
                    )
                else:
                    _bc_reason = (
                        f"Checking available {base} and "
                        f"{bot.config.target_asset} for bot "
                        f"{bot.bot_id}"
                    )
                    _bc_data = (
                        f"Bot needs {base} to place buy orders. "
                        f"Target balance: ${bot.config.target_balance:.2f}"
                    )
                _log.record(
                    exchange=eid,
                    action="BALANCE_CHECK",
                    reason=_bc_reason,
                    result=bal_summary,
                    level="info",
                    data_usage=_bc_data,
                )

                if not _sufficient:
                    _start_reason = _start_msg or (
                        f"Insufficient balance on {eid.capitalize()} to "
                        f"start trading. {bal_summary}"
                    )
                    _log.record(
                        exchange=eid,
                        action="INSUFFICIENT_BALANCE",
                        reason="Not enough funds to start trading",
                        result=_start_reason,
                        level="error",
                        data_usage="Bot will NOT start. User must deposit funds or adjust bot configuration.",
                    )
                    return False, _start_reason

                bot.exchange = connector
                self._exchange_connectors[eid] = connector

                try:
                    if hasattr(self, "_bot_manager") and self._bot_manager:
                        self._bot_manager.set_connector(connector)
                except Exception as _exc:
                    logger.warning("MEM-222 set_connector failed: %s", _exc)

                _log.record(
                    exchange=eid,
                    action="BOT_READY",
                    reason="Balance verified, exchange connected",
                    result=f"Bot {bot.bot_id} ready to trade. {bal_summary}",
                    level="success",
                    data_usage="Bot will now enter the trading loop: fetch price, compute grid, place orders",
                )

                return True, f"Connected. {bal_summary}"

            except Exception as exc:
                from ..exchange.ccxt_connector import CCXTConnector

                detail = CCXTConnector._format_exchange_error(exc)
                msg = f"Connection failed: {detail}"
                _log.record(
                    exchange=eid,
                    action="BOT_CONNECT_FAILED",
                    reason=detail,
                    result=msg,
                    level="error",
                    data_usage="See DIAGNOSIS above for specific troubleshooting steps",
                )
                return False, msg

        def _on_bot_fire(self, bot_id: str) -> None:
            """Call `force_fire(bot_id, aggressive=True)` and play the fire sound."""
            if not self._bot_manager:
                return
            try:
                ok = self._bot_manager.force_fire(bot_id, aggressive=True)
            except Exception as exc:
                self._status_log.log(f"Fire on {bot_id[:8]} failed: {exc}", "error")
                return
            if ok:
                self._status_log.log(
                    f"🎯 Manual Fire (aggressive): {bot_id[:8]} will "
                    f"rebalance to target on next tick "
                    f"(bypasses gates).",
                    "info",
                )
                try:
                    from ..core.sound_engine import get_sound_engine

                    get_sound_engine().play_fire()
                except Exception:  # noqa: S110
                    pass
            else:
                self._status_log.log(
                    f"Manual Fire unavailable for {bot_id[:8]} "
                    f"(grid bot or unknown id).",
                    "warning",
                )

        def _on_trade_filled_sfx(self, event) -> None:
            """Rifle on SCRUM/FOLD/DIST, coins on profit above zero, drip on FOLD."""
            try:
                ttype = (event.data.get("type") or "").upper()
                profit = event.data.get("profit", 0) or 0
                from ..core.sound_engine import get_sound_engine

                se = get_sound_engine()
                if ttype in ("SCRUM", "FOLD", "DIST"):
                    se.play_fire()
                if profit > 0:
                    se.play_profit()
                if ttype == "FOLD":
                    se.play_drip()
            except Exception:  # noqa: S110
                pass

        def _dispatch_tracking_beep(self, statuses: list) -> None:
            """Beep every 200 ms when a scrumming bot is in FIRE, 800 ms in TRACK."""
            import time

            hottest = None
            for s in statuses:
                if s.get("mode") != "scrumming":
                    continue
                if s.get("state") not in ("running", "paused"):
                    continue
                phase = s.get("scrum_target_mode")
                if phase == "fire":
                    hottest = "fire"
                    break
                if phase == "track" and hottest != "fire":
                    hottest = "track"

            if hottest is None:
                return

            cadence_s = 0.2 if hottest == "fire" else 0.8
            now = time.monotonic()
            last_ts = getattr(self, "_beep_last_ts", 0.0)
            if now - last_ts < cadence_s:
                return

            self._beep_last_ts = now
            try:
                from ..core.sound_engine import get_sound_engine

                get_sound_engine().play_track()
            except Exception:  # noqa: S110
                pass

        def _on_bot_command(self, bot_id: str, command: str) -> None:
            if not self._bot_manager:
                return
            bot = self._bot_manager.get_bot(bot_id)
            if not bot:
                self._status_log.log(f"Bot {bot_id} not found.", "error")
                return

            from ..exchange.api_logger import get_api_log

            get_api_log()
            from ..core.sound_engine import get_sound_engine

            sound = get_sound_engine()

            if command == "start":
                # Synchronous connect on the GUI thread: the window freezes until done.
                eid_display = bot.config.exchange_id.capitalize()
                self._status_log.log(
                    f"⏳ Starting bot {bot_id}... Connecting to {eid_display} "
                    f"(this can take 5-15 seconds, app may appear frozen)",
                    "info",
                )
                self._spool.notify(
                    f"⏳ Bot {bot_id}: connecting to {eid_display}...", "info"
                )

                safe_process_events("legacy P4.1 site")

                success, msg = self._connect_exchange_for_bot(bot)
                if not success:
                    self._status_log.log(f"Cannot start bot {bot_id}: {msg}", "error")
                    self._spool.notify(f"Bot {bot_id} FAILED: {msg}", "error")
                    sound.play_error()
                    return

                self._status_log.log(f"✓ Bot {bot_id}: {msg}", "success")
                safe_process_events("legacy P4.1 site")

                if not getattr(bot, "_user_verified", False):
                    cfg = bot.config
                    sym = cfg.symbol
                    vis = "Invisible" if cfg.visibility == "internal" else "Order Book"
                    mode = cfg.mode.value.upper()

                    pf = "ON" if cfg.profit_folding_active else "OFF"
                    mg = "ON" if cfg.bb_midline_gate else "OFF"
                    be = "ON" if cfg.bb_bullseye_check else "OFF"
                    hr = "ON" if cfg.hedge_rebalance_active else "OFF"
                    detail = (
                        f"Mode: {mode} — {vis} | "
                        f"Target: ${cfg.target_balance:.2f} | "
                        f"Interval: {cfg.scrumming_interval_pct}% | "
                        f"TA TF: {cfg.ta_timeframe} | "
                        f"BB tol: {cfg.bb_tolerance_pct}%, strip: {cfg.bb_landing_strip_candles} | "
                        f"P1.9: detect={cfg.scrum_detect_pct}%, fire={cfg.scrum_fire_pct}%, "
                        f"midline={mg}, bullseye={be}, travel={cfg.band_travel_pct}%, "
                        f"read={cfg.scrum_read_rate_min}min | "
                        f"Hedge: {hr} (${cfg.hedge_balance:.2f}) | "
                        f"Fold: {pf}"
                    )

                    self._status_log.log(
                        f"⚠ REAL MONEY: Bot {bot_id[:8]} on "
                        f"{cfg.exchange_id.capitalize()} — {sym} — {detail}",
                        "warning",
                    )
                    self._spool.notify(
                        f"⚠ Bot {bot_id[:8]} starting on REAL — {sym}", "warning"
                    )
                    bot._user_verified = True

                try:
                    self._schedule_async(bot.start())
                    self._status_log.log(f"✓ Bot {bot_id} RUNNING.", "success")
                    self._spool.notify(f"Bot {bot_id} RUNNING", "success")
                    sound.play_state_change()
                except Exception as exc:
                    self._status_log.log(
                        f"Failed to start bot {bot_id}: {exc}", "error"
                    )
                    sound.play_error()

            elif command == "pause":
                self._status_log.log(f"Pausing bot {bot_id}...", "info")
                try:
                    self._schedule_async(bot.pause())
                    self._status_log.log(f"Bot {bot_id} paused.", "warning")
                    self._spool.notify(f"Bot {bot_id} PAUSED", "warning")
                    sound.play_state_change()
                except Exception as exc:
                    self._status_log.log(
                        f"Failed to pause bot {bot_id}: {exc}", "error"
                    )

            elif command == "stop":
                self._status_log.log(f"Stopping bot {bot_id}...", "info")
                try:
                    self._schedule_async(bot.stop())
                    self._status_log.log(f"Bot {bot_id} stopped.", "info")
                    self._spool.notify(f"Bot {bot_id} STOPPED", "info")
                    sound.play_state_change()
                except Exception as exc:
                    self._status_log.log(f"Failed to stop bot {bot_id}: {exc}", "error")

            elif command == "restart":
                eid_display = bot.config.exchange_id.capitalize()
                self._status_log.log(
                    f"⏳ Restarting bot {bot_id}... Reconnecting to "
                    f"{eid_display} (5-15 seconds, app may appear frozen)",
                    "info",
                )

                safe_process_events("legacy P4.1 site")
                try:
                    self._schedule_async(bot.stop())
                    success, msg = self._connect_exchange_for_bot(bot)
                    if success:
                        self._schedule_async(bot.start())
                        self._status_log.log(f"✓ Bot {bot_id} restarted.", "success")
                        self._spool.notify(f"Bot {bot_id} RESTARTED", "success")
                        sound.play_state_change()
                    else:
                        self._status_log.log(
                            f"Cannot restart bot {bot_id}: {msg}", "error"
                        )
                        sound.play_error()
                except Exception as exc:
                    self._status_log.log(
                        f"Failed to restart bot {bot_id}: {exc}", "error"
                    )
                    sound.play_error()

            elif command == "delete":
                confirm = QMessageBox.question(
                    self,
                    "Delete Bot",
                    f"Delete bot {bot_id}? This cannot be undone.",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if confirm == QMessageBox.Yes:
                    # Scheduled before `unregister` so the bot is told to stop first.
                    try:
                        self._schedule_async(bot.stop())
                    except Exception as exc:
                        self._status_log.log(
                            f"Failed to stop bot {bot_id} before "
                            f"delete: {exc}. It was NOT told to "
                            f"stop and may still be trading.",
                            "error",
                        )
                    self._bot_manager.unregister(bot_id)
                    self._status_log.log(f"Bot {bot_id} deleted.", "warning")
                    self._spool.notify(f"Bot {bot_id} DELETED", "warning")
                    sound.play_state_change()

            elif command == "adjust_stack":
                self._on_bot_clicked(bot_id)

        def _global_bot_cmd(self, command: str) -> None:
            if not self._bot_manager:
                return
            self._status_log.log(f"Executing {command} on all bots...", "info")
            try:
                if command == "start_all":
                    from .variant_surface import START_ALL_PROGRESS, surface_class

                    eligible = [
                        b
                        for b in self._bot_manager._bots.values()
                        if b.state.value in ("idle", "stopped")
                    ]
                    if not eligible:
                        self._status_log.log(
                            "start_all: no bots eligible (none idle/stopped).", "info"
                        )
                        return
                    _cls = surface_class(START_ALL_PROGRESS)
                    dlg = _cls(self._bot_manager, parent=self)
                    dlg.show()
                    self._schedule_async(self._bot_manager.start_all())
                elif command == "pause_all":
                    self._schedule_async(self._bot_manager.pause_all())
                elif command == "stop_all":
                    self._schedule_async(self._bot_manager.stop_all())
                self._status_log.log(f"{command} completed.", "success")
            except Exception as exc:
                self._status_log.log(f"{command} failed: {exc}", "error")

        def _open_settings(self) -> None:
            _wing = getattr(self, "_trading_mode", "crypto") or "crypto"
            self._status_log.log(f"Opening settings ({_wing} wing)...")
            from .variant_surface import SETTINGS_DIALOG, surface_class

            _cls = surface_class(SETTINGS_DIALOG)
            dlg = _cls(self._settings, self._status_log, self, wing=_wing)
            dlg.settings_changed.connect(self._on_settings_changed)
            dlg.exec()

        def _on_settings_changed(self) -> None:
            if not self._settings:
                return
            from .theme_engine import DEFAULT_THEME_NAME, stored_theme

            theme = stored_theme(self._settings.get("theme", DEFAULT_THEME_NAME))
            self._switch_theme(theme, self._stored_accent())

            # A saved SMS page reaches the engine here, so a changed number or
            # switch applies without a restart.
            from src.core.sms_engine import (
                SETTINGS_GROUP,
                get_sms_engine,
                sms_config_from_settings,
            )

            get_sms_engine().update_config(
                sms_config_from_settings(self._settings.get(SETTINGS_GROUP, {}))
            )

            ai_cfg = self._settings.get("ai_monitor", {})
            if self._bot_manager:
                self._bot_manager.configure_live_monitor(ai_cfg)
                if ai_cfg.get("enabled") and ai_cfg.get("api_key"):
                    self._ai_monitor_label.setText("AI: READY")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.STATUS_AUTHENTICATED}; font-size: 10px; padding: 0 "
                        "8px; font-family: Consolas;"
                    )
                    self._status_log.log(
                        f"AI Monitor reconfigured (phrase: '{ai_cfg.get('connect_phrase', '')[:20]}...')",
                        "info",
                    )
                else:
                    self._ai_monitor_label.setText("AI: OFF")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; padding: 0 "
                        "8px; font-family: Consolas;"
                    )

            self._status_log.log("Settings saved.", "success")

        def _reset_settings(self) -> None:
            """Confirm, then call `reset_defaults` and tell the operator to restart."""
            confirm = QMessageBox.question(
                self,
                "Reset All Settings",
                "This will clear ALL settings, exchanges, and stored credentials.\n"
                "The application will restart with the setup wizard.\n\n"
                "Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm == QMessageBox.Yes:
                if self._settings:
                    self._settings.reset_defaults()
                self._status_log.log(
                    "All settings reset. Restart the application.", "warning"
                )
                self._spool.notify("Settings reset. Please restart.", "warning")
                QMessageBox.information(
                    self,
                    "Settings Reset",
                    "All settings have been cleared.\n"
                    "Close and reopen the application to run the setup wizard.",
                )

        def _toggle_trading_mode(self):
            """Flip the Trading stack and the Paper Trader stack together."""
            if self._trading_mode == "crypto":
                self._trading_mode = "stock"
                self._mode_btn.setText("Stock Mode")
                self._mode_btn.setChecked(True)
                self._trading_stack.setCurrentIndex(1)
                self._tab_widget = self._stock_tab_widget
                self._exchange_tabs = self._stock_exchange_tabs
                self._empty_placeholder = self._stock_placeholder
                self.setWindowTitle("Acervator — STOCK WING")
                self._status_log.log(
                    "→ STOCK WING: equity exchanges. (Crypto wing paused.)",
                    "info",
                )
            else:
                self._trading_mode = "crypto"
                self._mode_btn.setText("Crypto Mode")
                self._mode_btn.setChecked(False)
                self._trading_stack.setCurrentIndex(0)
                self._tab_widget = self._crypto_tab_widget
                self._exchange_tabs = self._crypto_exchange_tabs
                self._empty_placeholder = self._crypto_placeholder
                self.setWindowTitle("Acervator — CRYPTO WING")
                self._status_log.log(
                    "→ CRYPTO WING: crypto exchanges. (Stock wing paused.)",
                    "info",
                )
            self._update_mode_btn_style()

            # `_alias_page` comes from `_tab_widget`'s parent, not from either branch.
            _alias_host = self._tab_widget.parentWidget() if self._tab_widget else None
            _alias_page = (
                self._trading_stack.indexOf(_alias_host)
                if _alias_host is not None
                else -1
            )
            _stock_wing = self._trading_mode == "stock"
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _tr_emit

                _tr_emit(
                    "trading.12.004.postcondition.active_layer_alias",
                    actual=_alias_page,
                    expected=self._trading_stack.currentIndex(),
                    context={
                        "mode": self._trading_mode,
                        "tabs_alias_ok": self._exchange_tabs
                        is (
                            self._stock_exchange_tabs
                            if _stock_wing
                            else self._crypto_exchange_tabs
                        ),
                        "placeholder_alias_ok": self._empty_placeholder
                        is (
                            self._stock_placeholder
                            if _stock_wing
                            else self._crypto_placeholder
                        ),
                        "tabs_in_alias": self._tab_widget.count(),
                        "stack_pages": self._trading_stack.count(),
                    },
                )

        def _update_mode_btn_style(self):
            """Restyle the mode button, and tint the layer tab bars once both exist."""
            tabs_ready = hasattr(self, "_crypto_tab_widget") and hasattr(
                self, "_stock_tab_widget"
            )

            if self._trading_mode == "crypto":
                self._mode_btn.setStyleSheet(
                    "QPushButton { background: rgba(0, 200, 160, 40); "
                    f"color: {ds.LAYER_CRYPTO}; border: 1px solid rgba(0, 200, 160, "
                    "100); "
                    "border-radius: 4px; font-weight: bold; font-size: 11px; }"
                    "QPushButton:hover { background: rgba(0, 200, 160, 70); }"
                )
                if tabs_ready:
                    self._crypto_tab_widget.setStyleSheet(
                        "QTabBar::tab:selected { border-bottom: 2px solid "
                        f"{ds.LAYER_CRYPTO}; "
                        f"color: {ds.LAYER_CRYPTO}; }}"
                    )
                    self._stock_tab_widget.setStyleSheet("")
            else:
                self._mode_btn.setStyleSheet(
                    "QPushButton { background: rgba(80, 140, 255, 40); "
                    f"color: {ds.LAYER_STOCK}; border: 1px solid rgba(80, 140, 255, "
                    "100); "
                    "border-radius: 4px; font-weight: bold; font-size: 11px; }"
                    "QPushButton:hover { background: rgba(80, 140, 255, 70); }"
                )
                if tabs_ready:
                    self._stock_tab_widget.setStyleSheet(
                        "QTabBar::tab:selected { border-bottom: 2px solid "
                        f"{ds.LAYER_STOCK}; "
                        f"color: {ds.LAYER_STOCK}; }}"
                    )
                    self._crypto_tab_widget.setStyleSheet("")

        def _add_exchange(self) -> None:
            _wing = getattr(self, "_trading_mode", "crypto") or "crypto"
            self._status_log.log(
                f"Opening settings to add exchange " f"({_wing} wing)..."
            )
            from .variant_surface import SETTINGS_DIALOG, surface_class

            _cls = surface_class(SETTINGS_DIALOG)
            dlg = _cls(self._settings, self._status_log, self, wing=_wing)
            dlg.exec()
            self._sync_exchange_tabs()

        def _sync_exchange_tabs(self) -> None:
            """Add a tab for each configured exchange missing one, in its own layer."""
            if not self._settings:
                return
            _wanted: list[str] = []
            for exch in self._settings.list_exchanges():
                eid = exch.get("exchange_id", "")
                name = exchange_display_name(exch)
                if not eid:
                    continue
                _wanted.append(eid)
                target = (
                    self._stock_exchange_tabs
                    if self._is_equity_exchange(eid)
                    else self._crypto_exchange_tabs
                )
                if eid not in target:
                    self.add_exchange_tab(eid, name)
                    self._status_log.log(
                        f"Exchange tab added: {name} "
                        f"({'stock' if self._is_equity_exchange(eid) else 'crypto'} layer)",
                        "success",
                    )

            # `_missing` asks the layer tab bar, not the store the loop above wrote.
            _missing = 0
            for _eid in _wanted:
                if self._is_equity_exchange(_eid):
                    _store = self._stock_exchange_tabs
                    _bar = self._stock_tab_widget
                else:
                    _store = self._crypto_exchange_tabs
                    _bar = self._crypto_tab_widget
                _tab = _store.get(_eid)
                if _tab is None or _bar.indexOf(_tab) < 0:
                    _missing += 1
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _tr_emit

                _tr_emit(
                    "trading.12.003.postcondition.exchange_tabs_synced",
                    actual=_missing,
                    expected=0,
                    context={
                        "configured": len(_wanted),
                        "crypto_bar": self._crypto_tab_widget.count(),
                        "stock_bar": self._stock_tab_widget.count(),
                        "crypto_store": len(self._crypto_exchange_tabs),
                        "stock_store": len(self._stock_exchange_tabs),
                    },
                )

        def _stored_ta_weights(self):
            """The indicator weights a new bot votes with, read off the store.

            Falls back to the manager's copy, then to None, which leaves the
            engine on ``ta_engine.DEFAULT_WEIGHTS``.
            """
            if self._settings is not None:
                from ..trading.ta_engine import weights_from_settings

                return weights_from_settings(
                    self._settings.get("ta_indicator_weights", {})
                )
            if self._bot_manager is not None:
                return getattr(self._bot_manager, "ta_weights", None)
            return None

        def _refuse_extractor_without_parent(
            self,
            base_currency: str,
            exchange_id: str,
        ) -> bool:
            """Show the `_extractor_parent_refusal` reason; True when creation stops."""
            reason = self._extractor_parent_refusal(base_currency, exchange_id)
            if reason is None:
                return False
            QMessageBox.critical(
                self,
                "Extractor needs a parent bot",
                f"{reason}\n\nBot creation aborted.",
            )
            self._status_log.log(f"Extractor creation REFUSED — {reason}", "error")
            logger.warning(
                "Extractor creation refused for %s on %s: no single "
                "Scrumming Bot holds it",
                base_currency,
                exchange_id,
            )
            from ..exchange.api_logger import get_api_log

            get_api_log().record(
                exchange=exchange_id,
                action="BOT_CREATE_REFUSED",
                reason="Extractor has no single parent Scrumming Bot "
                "for its base currency",
                result=f"REFUSED: {base_currency}",
                level="warning",
                data_usage="No bot was created and no state was written.",
            )
            return True

        def _extractor_parent_refusal(
            self,
            base_currency: str,
            exchange_id: str,
        ) -> str | None:
            """Operator-facing text when no single Scrumming Bot holds this currency."""
            _asset = (base_currency or "").strip().upper() or "?"
            _venue = (exchange_id or "").strip() or "this exchange"
            manager = self._bot_manager
            if manager is None:
                return (
                    f"The bot roster is not available, so it cannot be "
                    f"confirmed that a Scrumming Bot on {_venue} holds "
                    f"{_asset}.\n\n"
                    f"An Extractor hands its base currency back to the "
                    f"Scrumming Bot that holds it, so it may not be "
                    f"created until that bot is known to exist."
                )

            parent = manager.find_parent_bot_for_base_currency(
                base_currency, exchange_id=exchange_id
            )
            if parent is not None:
                return None

            candidates = manager.list_parent_bot_candidates_for_base_currency(
                base_currency, exchange_id=exchange_id
            )

            if not candidates:
                return (
                    f"No Scrumming Bot on {_venue} holds {_asset}.\n\n"
                    f"An Extractor is a sibling of the Scrumming Bot "
                    f"that holds its base currency: when the Extractor "
                    f"closes a position it hands {_asset} back to that "
                    f"bot, which raises its target balance to keep the "
                    f"gain. With no such bot there is nowhere for the "
                    f"money to go.\n\n"
                    f"Create a Scrumming Bot for {_asset} on {_venue} "
                    f"first, then create this Extractor."
                )

            _ids = ", ".join(bot_id for bot_id, _bot in candidates)
            return (
                f"{len(candidates)} Scrumming Bots on {_venue} hold "
                f"{_asset}: {_ids}.\n\n"
                f"The parent is ambiguous. An Extractor hands {_asset} "
                f"back to ONE holder, and nothing here can tell which "
                f"of these earned it — choosing for you would raise the "
                f"wrong bot's target on money it never received, while "
                f"the right one stayed short.\n\n"
                f"Naming the parent is your call. Leave exactly one "
                f"Scrumming Bot holding {_asset} on {_venue}, then "
                f"create this Extractor."
            )

        def _create_bot(
            self,
            exchange_id: str = "",
            defaults_override: Optional[dict] = None,
        ) -> None:
            """Open the Bot Creation Wizard; ``defaults_override`` merges in."""
            self._status_log.log(f"Creating new bot for {exchange_id}...")
            from ..exchange.api_logger import get_api_log

            _log = get_api_log()
            _log.record(
                exchange=exchange_id or "app",
                action="BOT_WIZARD_OPEN",
                reason="User clicked +New Bot",
                result="Opening wizard...",
                level="info",
                data_usage="Wizard will fetch available markets from exchange API for asset selection",
            )

            from .bot_wizard import BotCreationWizard

            exchanges = self._settings.list_exchanges() if self._settings else []
            defaults = self._settings.get_all() if self._settings else {}
            if defaults_override:
                defaults = {**defaults, **defaults_override}
            wizard = BotCreationWizard(exchanges, defaults, self)
            if wizard.exec() == wizard.DialogCode.Accepted:
                config = wizard.get_bot_config()
                logger.info("Bot creation config: %s", config)

                _log.record(
                    exchange=config.get("exchange_id", exchange_id),
                    action="BOT_CREATE",
                    reason=f"Creating {config.get('mode','').upper()} bot for {config.get('target_asset','')}/{config.get('base_currency','')}",
                    result=f"Balance=${config.get('target_balance',0):.2f}, Positions={config.get('position_count',0)}",
                    level="info",
                    data_usage="Bot will be registered with BotManager in IDLE state. Must be started manually.",
                )

                try:
                    from ..trading.bot_container import BotMode

                    try:
                        from .preflight_check import (
                            check_symbol,
                            format_result_for_user,
                        )

                        # Bound early: the Extractor path skips the else binding them.
                        _pf_symbol = "(no single symbol)"
                        _pf_exchange = str(exchange_id or "the exchange")
                        if config.get("mode") == "extractor":
                            self._status_log.log(
                                "Pre-flight skipped (Extractor mode is "
                                "multi-pair; symbol validation deferred "
                                "to runtime watch-list refresh)",
                                "info",
                            )
                            _pf = None
                            _pf_text = ""
                        else:
                            _pf_symbol = (
                                config.get("target_asset", "BTC")
                                + "/"
                                + config.get("base_currency", "USDT")
                            )
                            _pf_exchange = config.get("exchange_id", exchange_id)
                            _pf_target = config.get(
                                "target_balance", config.get("investment_amount", 200.0)
                            )
                            _pf = check_symbol(
                                exchange_id=_pf_exchange,
                                symbol=_pf_symbol,
                                target_balance=_pf_target,
                            )
                            _pf_text = format_result_for_user(_pf)
                        if _pf is not None:
                            if not _pf.success:
                                # Plain text: a symbol carrying tags is words, not markup.
                                _pf_box = QMessageBox(
                                    QMessageBox.Critical,
                                    "Pre-flight check failed",
                                    f"{_pf_text}\n\nBot creation aborted.",
                                    QMessageBox.Ok,
                                    self,
                                )
                                _pf_box.setTextFormat(Qt.PlainText)
                                _pf_box.exec()
                                self._status_log.log(
                                    f"Pre-flight FAILED for {_pf_symbol} on "
                                    f"{_pf_exchange}: {_pf.message}",
                                    "error",
                                )
                                return
                            if _pf.warnings:
                                _pf_ask = QMessageBox(
                                    QMessageBox.Question,
                                    "Pre-flight check — warnings",
                                    f"{_pf_text}\n\nProceed with bot creation?",
                                    QMessageBox.Yes | QMessageBox.No,
                                    self,
                                )
                                _pf_ask.setTextFormat(Qt.PlainText)
                                _pf_ask.setDefaultButton(QMessageBox.No)
                                _pf_reply = _pf_ask.exec()
                                if _pf_reply != QMessageBox.Yes:
                                    self._status_log.log(
                                        f"Bot creation declined at pre-flight "
                                        f"({len(_pf.warnings)} warning(s))",
                                        "warning",
                                    )
                                    return
                            self._status_log.log(
                                f"Pre-flight OK for {_pf_symbol} on "
                                f"{_pf_exchange} ({_pf.elapsed_ms:.0f} ms)",
                                "info",
                            )
                    except ImportError:
                        self._status_log.log(
                            "Pre-flight check skipped (module unavailable)", "warning"
                        )
                    except Exception as _pf_exc:
                        self._status_log.log(
                            f"Pre-flight check errored: {type(_pf_exc).__name__}: "
                            f"{_pf_exc} — continuing anyway",
                            "warning",
                        )

                    _mode_str = config.get("mode", "scrumming")
                    if _mode_str == "extractor":
                        _mode = BotMode.EXTRACTOR
                    else:
                        _mode = BotMode.SCRUMMING
                    from ..trading.bot_container import (
                        bot_config_kwargs,
                        make_bot_config,
                    )

                    _wizard_kwargs = bot_config_kwargs(
                        _mode, config, exchange_id=exchange_id
                    )

                    try:
                        bot_config = make_bot_config(_mode, **_wizard_kwargs)
                    except (ValueError, TypeError) as _bc_err:
                        msg = (
                            f"Bot creation REJECTED — mode-shape "
                            f"violation: {_bc_err}"
                        )
                        self._status_log.log(msg, "error")
                        self._spool.notify(msg, "error")
                        logger.error("Bot creation rejected: %s", _bc_err)
                        return

                    _mode_violations = bot_config.validate_mode_shape()
                    if _mode_violations:
                        for _v in _mode_violations:
                            logger.warning(
                                "Mode-shape violation on bot config " "(mode=%s): %s",
                                bot_config.mode.value,
                                _v,
                            )
                            self._status_log.log(
                                f"⚠ Bot config mode-shape " f"violation: {_v}",
                                "warning",
                            )

                    # Checked after the config is shaped and before the bot is built.
                    if (
                        bot_config.mode == BotMode.EXTRACTOR
                        and self._refuse_extractor_without_parent(
                            bot_config.base_currency, bot_config.exchange_id
                        )
                    ):
                        return

                    from ..trading.scrumming_bot import ScrummingBot

                    if bot_config.mode == BotMode.EXTRACTOR:
                        from ..trading.extractor_bot import ExtractorBot

                        bot = ExtractorBot(
                            bot_config,
                            _PlaceholderExchange(bot_config.exchange_id),
                            enable_phantoms=False,
                        )
                    else:
                        bot = ScrummingBot(
                            bot_config,
                            _PlaceholderExchange(bot_config.exchange_id),
                            enable_phantoms=config.get("enable_phantoms", False),
                            phantom_timeframes=config.get("phantom_timeframes", []),
                            ta_weights=self._stored_ta_weights(),
                        )

                    if self._bot_manager:
                        # `register` may return a bool or a (granted, reason) tuple.
                        _reg_result = self._bot_manager.register(bot)
                        if isinstance(_reg_result, tuple):
                            _granted, _refuse_reason = _reg_result
                        else:
                            _granted, _refuse_reason = True, None
                        if not _granted:
                            _msg = (
                                f"Bot creation refused by CapitalRegistry: "
                                f"{_refuse_reason or 'over-allocation'}"
                            )
                            try:  # noqa: SIM105
                                self._status_log.log(_msg, "error")
                            except Exception:  # noqa: S110
                                pass
                            return

                    if bot_config.mode == BotMode.SCRUMMING:
                        try:
                            self._indicator_panel.update_bot_list(
                                self._bot_manager.list_bots()
                            )
                            self._indicator_panel.force_refresh(
                                bot_id=bot.bot_id,
                                symbol=bot_config.symbol,
                                ta_timeframe=bot_config.ta_timeframe,
                            )
                        except Exception:  # noqa: S110
                            pass

                    msg = (
                        f"Bot {bot.bot_id} created: {bot_config.symbol} "
                        f"({bot_config.mode.value}) - IDLE"
                    )
                    self._status_log.log(msg, "success")
                    self._spool.notify(msg, "success")
                    self.statusBar().showMessage(msg, 5000)

                    _log.record(
                        exchange=bot_config.exchange_id,
                        action="BOT_CREATED",
                        reason="Bot instantiated and registered with BotManager",
                        result=f"ID={bot.bot_id}, State=IDLE, Symbol={bot_config.symbol}",
                        level="success",
                        data_usage="Bot is IDLE. Click Start to connect to exchange and begin trading. "
                        "Starting will authenticate API, load markets, fetch balances, and enter the trading loop.",
                    )

                    from ..core.sound_engine import get_sound_engine

                    get_sound_engine().play_state_change()

                except Exception as exc:
                    self._status_log.log(f"Failed to create bot: {exc}", "error")
                    logger.error("Bot creation failed: %s", exc)
                    _log.record(
                        exchange=exchange_id,
                        action="BOT_CREATE_FAILED",
                        reason=str(exc),
                        result=f"ERROR: {type(exc).__name__}",
                        level="error",
                        data_usage="Bot was not created. Check error details above.",
                    )
            else:
                self._status_log.log("Bot creation cancelled.", "warning")
                _log.record(
                    exchange=exchange_id or "app",
                    action="BOT_WIZARD_CANCELLED",
                    reason="User cancelled bot creation wizard",
                    result="No bot created",
                    level="warning",
                    data_usage="No action taken",
                )

        def _stored_accent(self) -> object:
            """The accent field the store holds, None when there is no store."""
            return self._settings.get("accent_color") if self._settings else None

        def _switch_theme(self, name: str, accent: object = None) -> None:
            from .theme_engine import ThemeManager, stored_accent

            tm = ThemeManager()
            taken = stored_accent(accent)
            if not taken and str(accent or "").strip():
                self._status_log.log(
                    f"Accent colour {accent!r} is not a hex colour; "
                    f"painting the {name} accent.",
                    "warning",
                )
            app = self.parent()
            if app is None:
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
            if app:
                tm.apply_theme(name, app, taken)
                book = getattr(self, "_main_tabs", None)
                if hasattr(book, "set_theme"):
                    book.set_theme(name)
                swarm = getattr(self, "_bot_viz", None)
                if hasattr(swarm, "set_app_theme"):
                    swarm.set_app_theme(name)
                self._status_log.log(f"Theme switched to {name}.", "info")

        def _show_about(self) -> None:
            QMessageBox.about(
                self,
                "About Acervator",
                "Acervator v1.7\n\n"
                "A multi-exchange crypto auto-trading platform.\n"
                "Grid Mode - Speculative Scrumming\n"
                "Profit Folding - Upward Distribution\n"
                "Phantom Bots - 7-Indicator TA Voting\n"
                "TradingView Charts - Multi-Timeframe Analysis\n"
                "Verbose API Interaction Logging",
            )
