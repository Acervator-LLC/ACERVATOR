"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
main_window.py - Primary application window v1.7
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


try:
    from PySide6.QtWidgets import (
        QMainWindow,
        QTabWidget,
        QLabel,
        QPushButton,
        QStatusBar,
        QGroupBox,
        QPlainTextEdit,
        QMessageBox,
    )  # v3.19.12 removed unused QToolTip
    from PySide6.QtCore import QTimer, Slot
    from PySide6.QtGui import QIcon

    from .main_tabs.bot_swarm_tab import BotSwarmTabMixin
    from .main_tabs.charts_tab import ChartsTabMixin
    from .main_tabs.console_tab import ConsoleTabMixin
    from .main_tabs.header_strip import HeaderStripMixin
    from .main_tabs.history_tab import HistoryTabMixin
    from .main_tabs.market_inspector_tab import MarketInspectorTabMixin
    from .main_tabs.retired_tabs import RetiredTabsMixin
    from .main_tabs.simulator_tab import SimulatorTabMixin
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

    # v3.19.12 removed unused QPropertyAnimation, QEasingCurve, QAction
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
from src.gui.qt_safe_events import safe_process_events  # v3.15.99 P4.1

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

    # ---------------------------------------------------------------
    # The Console Pause flag
    # ---------------------------------------------------------------
    def _set_console_paused(window: MainWindow, *, paused: bool) -> None:
        """Set the flag the signals pane's drain is gated on.

        issue #49. `_drain_signals` has always read
        `getattr(self, "_console_paused", False)`, and its docstring has
        always said it "honours the same Pause the log pane uses, so one
        control quiets both". NOTHING IN THE TREE EVER ASSIGNED THAT
        ATTRIBUTE, so the `False` default won every read: the operator
        pressed Pause, `_QtLogHandler.set_paused` stopped the log pane,
        and the signals pane under it went on scrolling. Driven on the
        real widgets before this repair -- 10 blocks on the signals pane
        at the press, 51 four drain ticks later, while the log pane held
        at 10.

        THE DOCSTRING IS THE SPECIFICATION AND THE CODE DISAGREED WITH
        IT. The repair makes the code do what the prose says. Rewriting
        the prose to describe the broken behaviour would have deleted
        the only record of what the button is for.

        IT IS A MODULE-LEVEL FUNCTION, resolved through globals on every
        call, for the same reason `_reanchor_bot_selection` (issue #51)
        and `_select_row_for_bot` (issue #52) are. The falsifier for
        `console.14.004` has to be able to put the pre-repair tree back
        for the length of one drive. Written inline as
        `self._console_paused = paused` the assignment is unreachable
        from a test, the pin's red condition becomes unreachable with
        it, and a pin that cannot be driven to red is a pin nobody can
        read when it is green.

        `bool()` because `console.14.004` reads this value back and
        compares it against the button's own `isChecked()`, which is a
        bool. A truthy int here would report green about a different
        type.

        KEYWORD-ONLY, because the argument is a bare bool.
        `paused=paused` at the one call site says what the value means;
        a positional `True` would say only which function it belongs
        to. The falsifier's stand-in carries the same signature, so a
        call that went back to positional raises there rather than
        patching a function nobody calls.
        """
        window._console_paused = bool(paused)

    # ---------------------------------------------------------------
    # The signals-pane gap marker
    # ---------------------------------------------------------------
    def _signal_gap_marker_text(skipped: int) -> str:
        """Return the line the signals pane draws over a skipped stretch.

        issue #48, and it is the operator's requirement in his own
        words: "The Emitter Network just needs to work. No part should
        get back logged or clogged or fall out of sync."

        THE PANE IS ONE CONSUMER FALLING BEHIND AND IT IS NOT DATA
        LOSS, AND THE WORDING SAYS SO. `SignalSink` appends and flushes
        on every emit, so every record this pass steps over is already
        on disk in `~/.acervator_logs/signals/session.jsonl`. A marker
        reading "not shown" alone would send the operator hunting a
        defect that is not there; this one names the file, so the next
        move is `Get-Content`, not a bug report.

        "SKIPPED TO STAY CURRENT" IS THE OTHER HALF OF THE SENTENCE.
        The alternative design -- advance the watermark only as far as
        the render reached -- would leave the pane falling further
        behind under sustained load, showing older and older records
        while the sink races ahead, with nothing on the screen to say
        whether it is a live monitor or a historical one. The pane
        stays current and draws the gap instead, and the marker states
        which of the two it chose.

        `NOT LOST` IS UPPER CASE ON PURPOSE. It is the one clause a
        reader scanning a scrolling pane has to catch.

        The count is the FIRST number in the line so the eye finds it
        without reading the sentence, and it is the same quantity
        `console.14.001` reports as `lost_to_slice`.

        Split out from `_draw_signal_gap_marker` so a test can assert
        the WORDING without a widget, and so the drawing test and the
        wording test fail separately when they fail.
        """
        return (
            f"──── [SIGNALS GAP] {skipped} earlier records skipped "
            f"to stay current · NOT LOST · on disk in "
            f"~/.acervator_logs/signals/session.jsonl ────"
        )

    def _draw_signal_gap_marker(view: QPlainTextEdit, *, skipped: int) -> int:
        """Draw one gap marker into the signals pane. Returns blocks added.

        issue #48. The return value is the number of BLOCKS this call
        put on the pane, and `_drain_signals` adds it to
        `_signal_markers`, which `console.14.002` then counts as part
        of what the drain wrote. A marker line IS a block, so leaving
        it out of that ledger would paint `14-002` red for drawing the
        very thing that makes the skip visible.

        `skipped <= 0` DRAWS NOTHING AND RETURNS ZERO. A pass that kept
        every record must leave no trace at all, or the marker becomes
        pane furniture the operator learns to read past.

        IT IS A MODULE-LEVEL FUNCTION, resolved through globals on
        every call, for the same reason `_set_console_paused` (issue
        #49), `_reanchor_bot_selection` (issue #51) and
        `_select_row_for_bot` (issue #52) are: `_without_the_gap_marker`
        has to be able to put the pre-repair tree back for the length
        of one drive. Written inline in the drain, the pre-repair
        behaviour is unreachable from a test and the tests below would
        be asserting about arithmetic rather than about this code.

        ESCAPED, like every other line the drain appends. `appendHtml`
        parses its input and the count is interpolated into it; the
        escape is here so this line can never become the one place a
        payload reaches the parser.

        AMBER ON A DARK GROUND, and the only line in the pane that
        carries a background colour. `OK`/`FAIL`/`--` records are green,
        red and grey text on `#05050a`; nothing else paints its own
        ground, so the marker cannot be misread as a record even at the
        10 px this pane renders at. The rules on both ends do the same
        work in a plain-text copy, where the colour is gone.
        """
        if skipped <= 0:
            return 0
        from html import escape as _esc

        view.appendHtml(
            "<span "
            f'style="color:{ds.MAIN_HIGHLIGHT_AMBER_TEXT};background-color:{ds.MAIN_HIGHLIGHT_AMBER}">'
            f"{_esc(_signal_gap_marker_text(skipped))}</span>"
        )
        return 1

    # ---------------------------------------------------------------
    # Main Window
    # ---------------------------------------------------------------
    class MainWindow(
        BotSwarmTabMixin,
        ChartsTabMixin,
        ConsoleTabMixin,
        HeaderStripMixin,
        HistoryTabMixin,
        MarketInspectorTabMixin,
        RetiredTabsMixin,
        SimulatorTabMixin,
        TradingTabMixin,
        QMainWindow,
    ):

        # DECLARED, NOT ASSIGNED. The dashboard tick asks
        # `hasattr(self, '_last_equity_snap')` to tell a first snapshot
        # from a ten-second one, so giving this a value here would make
        # the first branch unreachable and change when the first equity
        # snapshot is taken. A bare annotation creates no attribute: it
        # tells the type checker what the value will be without
        # bringing it into existence.
        _last_equity_snap: float

        # DECLARED, NOT ASSIGNED, for the same reason and with the same
        # consequence. `_drain_signals` reads this through
        # `getattr(self, "_console_paused", False)` and must keep
        # reading the default until the operator's first press, so a
        # value here would create the attribute and change which branch
        # a fresh window takes. The annotation exists so the type
        # checkers know `_set_console_paused` is writing a real member
        # of this class rather than inventing one.
        _console_paused: bool

        def __init__(self, bot_manager=None, settings_manager=None, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Acervator v" + __version__ + "")
            self.setMinimumSize(1400, 900)
            self._bot_manager = bot_manager
            # Trade historian callback will be registered in _post_init_hook()
            # after the history tab is constructed.
            self._settings = settings_manager
            self._exchange_tabs: dict[str, ExchangeTab] = {}
            self._bus = get_event_bus()
            self._async_loop = None
            self._exchange_connectors: dict[str, object] = {}

            # MEM-228 (Session 24, 2026-04-22) — Buy confirmation broker.
            # Must be constructed on the GUI main thread so Qt.AutoConnection
            # queues cross-thread signal emissions (from bot async workers)
            # into the main event loop. Bot-side `_execute_buy` awaits the
            # broker's request_confirmation(); the modal runs on this thread.
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

            # --- Advanced subsystems ---
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

            # Event bus handlers
            self._bus.subscribe("bot.log", self._on_bot_log)
            self._bus.subscribe("wire.created", self._on_wire_created)
            self._bus.subscribe("indicator.tf_lock_changed", self._on_tf_lock_changed)
            self._bus.subscribe("ai.feedback", self._on_ai_feedback)
            # MEM-236 — Fire SFX on scrum/fold/dist fills
            self._bus.subscribe("trade.filled", self._on_trade_filled_sfx)
            # v3.16.52 — Rolling error buffer for the clickable Errors card.
            # bot_container emits "bot.error" on every tick exception;
            # we capture (timestamp, bot_id, error_msg, consecutive)
            # tuples in a bounded deque so the dialog can show them.
            from collections import deque as _deque

            self._error_log_buffer: _deque = _deque(maxlen=200)
            self._bus.subscribe("bot.error", self._on_bot_error_for_log)

            # Set window icon for taskbar/dock
            icon_path = Path(__file__).parent.parent.parent / "resources" / "icon.ico"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

            self._setup_menu()
            self._setup_ui()
            self._setup_status_bar()
            self._setup_refresh_timer()
            self._setup_pulse()
            self._setup_tooltips()

            # Configure LiveMonitor AFTER _setup_ui (needs _status_log)
            self._init_live_monitor()

            self._status_log.log("Acervator v" + __version__ + " started.", "success")
            logger.info(
                "Acervator v"
                + __version__
                + " — Console logging active. All system messages appear here."
            )
            self._verify_exchanges_on_startup()

        def set_async_loop(self, loop) -> None:
            """Set the persistent asyncio event loop from main.py."""
            self._async_loop = loop
            # v3.18.7 Phase B — propagate the loop into the Simulator
            # tab so Nuclear Mode can schedule its scout bot + world-
            # clock coroutines on the same loop. Guarded with hasattr
            # to keep backwards compatibility with the Phase A skeleton
            # that didn't expose set_async_loop on SimulatorTab.
            try:
                if getattr(self, "_simulator", None) is not None and hasattr(
                    self._simulator, "set_async_loop"
                ):
                    self._simulator.set_async_loop(loop)
            except Exception as _exc:  # R28-OK: propagation best-effort
                logger.warning(
                    "set_async_loop: SimulatorTab propagation failed: %s", _exc
                )

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
                    lambda n=name: self._switch_theme(n),
                )
            help_menu = menu_bar.addMenu("&Help")
            help_menu.addAction("&About", self._show_about)

        def _setup_ui(self) -> None:
            main_layout = self._build_header_strip()

            # === Shared TestNet bridge — ONE LocalTestnet instance ===
            # Must be installed BEFORE tab construction so any tab
            # that wants chain state finds it via main_win.
            # Nuclear mode and TestnetTab both write through this.
            # sadp: R28 FL + bridge = MEM-136 architecture
            try:
                from .shared_testnet import SharedTestnetBridge

                SharedTestnetBridge.install_on(self)
            except Exception as _e:
                import traceback as _tb

                logging.getLogger("acervator").warning(
                    f"SharedTestnetBridge install failed: {_e}\n" f"{_tb.format_exc()}"
                )
                # Non-fatal — tabs degrade to their own LocalTestnet
                self._local_testnet = None
                self._testnet_bridge = None

            # === Main content: two top-level tabs (Trading / Charts) ===
            self._main_tabs = QTabWidget()
            self._main_tabs.setMovable(True)  # User can drag tabs to rearrange

            self._build_trading_tab()
            self._build_charts_tab()
            self._build_bot_swarm_tab()
            self._build_market_inspector_tab()
            self._build_simulator_tab()
            self._install_retired_tab_sentinels()
            self._build_history_tab()
            self._build_console_tab()

            # v3.23.77 — enforce operator's canonical tab order
            # (directive 2026-08-XX). The per-tab builders above run
            # in construction order and produce the wrong default
            # order; rather than resequence the calls
            # (risky — sibling code may reference specific indices),
            # a single reorder pass at the end moves each named
            # tab into its target slot. If the operator wants a
            # different order later, edit CANONICAL_TAB_ORDER only.
            CANONICAL_TAB_ORDER = [
                "Trading",
                "Market Inspector",
                "Bot Swarm",
                "Asset Charts",
                "History",
                "Simulator",
                "Console",
            ]
            self._reorder_main_tabs(CANONICAL_TAB_ORDER)

            # v3.18.3 — connect tab-change signal so the window-level
            # header stat strip can be hidden on isolated tabs
            # (Simulator and, when Phase E lands, Paper Trader). Per
            # operator directive 2026-05-19 the absence of the live
            # strip on those tabs IS the context differentiator.
            self._main_tabs.currentChanged.connect(self._on_main_tab_changed)

            main_layout.addWidget(self._main_tabs, 1)

        def _reorder_main_tabs(self, desired: list[str]) -> None:
            """v3.23.77 — move tabs into the canonical order the
            operator specified. Tabs whose labels are NOT in
            ``desired`` keep their relative position at the end (so
            future tab additions don't get silently reordered until
            they're listed here).

            Uses QTabBar.moveTab so widget instances + connected
            signals are preserved; only the visual index changes.
            """
            tab_bar = self._main_tabs.tabBar()
            for target_idx, name in enumerate(desired):
                for cur_idx in range(self._main_tabs.count()):
                    if self._main_tabs.tabText(cur_idx) == name:
                        if cur_idx != target_idx:
                            tab_bar.moveTab(cur_idx, target_idx)
                        break

        def _on_main_tab_changed(self, index: int) -> None:
            """v3.18.3 — toggle the window-level header strip's
            visibility based on the active tab. Hidden on Simulator
            and Paper Trader (the isolated tabs that carry their own
            inline stat strips). Visible everywhere else.

            v3.20.36 — also closes the History-tab auto-fetch wiring
            gap. The HistoryTab docstring (history_tab.py line 21)
            promised "Manual refresh + auto-refresh on tab activation"
            but the activation hook was never wired here. Operator
            reported 2026-05-31: setting filters + clicking Apply
            produced "0 of 0 trades · no fetch yet" forever because
            no fetch ever kicked off. The Apply-side fallback fix
            lives in history_tab.py::_apply_filters; this is the
            primary fix — when the operator selects the History tab,
            trigger a refresh if none has occurred yet.
            """
            try:
                tab_name = self._main_tabs.tabText(index)
            except Exception:  # R28-OK: defensive — tab index race during teardown
                return
            isolated_tabs = {"Simulator", "Paper Trader"}
            container = getattr(self, "_header_strip_container", None)
            if container is not None:
                container.setVisible(tab_name not in isolated_tabs)

            # v3.20.36 — History tab auto-refresh on activation. Only
            # fires on first visit (when _last_fetched_ts == 0); the
            # operator can still manually re-Refresh thereafter.
            # Defensive: tolerate missing tab / missing bot manager /
            # missing async loop — _kick_async_fetch handles each
            # with a status-line message rather than raising.
            if tab_name == "History":
                hist = getattr(self, "_history_tab", None)
                if hist is not None:
                    try:
                        # Honor staleness: only auto-refresh on first
                        # activation OR if the prior fetch is > 5 min
                        # old. Operator can manually Refresh anytime.
                        last_ts = getattr(hist, "_last_fetched_ts", 0.0)
                        in_flight = getattr(hist, "_fetch_in_flight", False)
                        import time as _t

                        is_stale = last_ts == 0 or _t.time() - last_ts > 300
                        if is_stale and not in_flight:
                            hist.refresh()
                    except Exception as _hexc:  # R28-OK: defensive
                        logger.debug(
                            "History auto-refresh on tab-activate " "skipped: %s", _hexc
                        )

        # v3.16.7 — Console Tab pause function (operator directive
        # 2026-04-28: "the Console Tab needs its own pause function.
        # Capturing the above error properly was very difficult.").
        def _drain_signals(self) -> None:
            """Poll the signal sink and render new records.

            v3.24.81. Reads only records NEWER than the last watermark, so
            the cost is proportional to what arrived, not to the run.

            Never raises: instrumentation display must not be able to take
            down the window it is displayed in. Honours the same Pause the
            log pane uses, so one control quiets both.

            The flag that Pause is spelled with is `_console_paused`, and
            `_set_console_paused` -- called by `_toggle_console_pause` --
            is the only thing that writes it (issue #49). A paused drain
            advances NO watermark, so the sink keeps every record for the
            resume: see the note on `_signal_read` below for what the
            resume pass then does with a backlog.

            THE PANE STAYS CURRENT AND DRAWS THE GAP (issue #48). Two
            paths reach the same slice: a long pause and then a resume,
            and a live burst of more than 200 records inside one 500 ms
            window with no pause at all. On both, the watermark moves to
            `new[-1].seq` and the render keeps the newest 200 -- so this
            consumer steps over the rest. It is NOT data loss: the sink
            appends and flushes on every emit, and every stepped-over
            record is on disk in
            `~/.acervator_logs/signals/session.jsonl`. What was missing
            was any sign of it ON THE SCREEN, and
            `_draw_signal_gap_marker` is that sign.
            """
            try:
                # 10.7 -- THE TICK COUNTER IS THE FIRST STATEMENT AND NO
                # RETURN BELOW IT CAN SKIP IT. It counts INVOCATIONS of
                # this slot, which is what `console.14.003` reads to
                # tell a live timer from a dead one. Counted further
                # down it would count RECORDS ARRIVING instead, and a
                # quiet sink would then read exactly like a stopped
                # timer -- the one fault the pin exists to separate from
                # ordinary silence.
                #
                # `getattr` rather than `+= 1`:
                # `tests/test_signal_timing.py` drives this method off a
                # stub that owns three attributes, and an AttributeError
                # here would be swallowed by the `except` below and take
                # the whole drain down with it.
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
                # 10.7 -- THE WATERMARK HAS ALREADY MOVED PAST EVERY
                # RECORD IN `new`, INCLUDING THE ONES THE SLICE BELOW
                # THROWS AWAY. `_signal_read` counts what the watermark
                # consumed; `_signal_rendered` counts what reached the
                # pane. The gap between them is the permanent, silent
                # loss `console.14.001` reports, and `_signal_slice_
                # dropped` says which mechanism took it. Nothing here
                # emits: see the ledger comment beside the timer.
                _shown = new[-200:]
                _skipped = len(new) - len(_shown)
                self._signal_read = getattr(self, "_signal_read", 0) + len(new)
                self._signal_slice_dropped = (
                    getattr(self, "_signal_slice_dropped", 0) + _skipped
                )
                self._signal_rendered = getattr(self, "_signal_rendered", 0)
                # issue #48. THE GAP IS DRAWN, NOT ONLY COUNTED. A
                # number that lives in the emitter stream helps whoever
                # reads `session.jsonl`; it does nothing at all for the
                # operator watching the pane, who until now saw the
                # newest 200 records appear with no sign that 4800
                # older ones had been stepped over.
                #
                # ABOVE THE SLICE, NOT BELOW IT, and that is the whole
                # of the placement argument. The skipped records are
                # OLDER than the 200 about to be drawn, so the marker
                # that describes them belongs above them. Below, on a
                # pane that then goes quiet, the marker would sit at
                # the bottom as the newest thing on the screen and read
                # as a gap at the live edge -- a lie about a pane that
                # is in fact fully current.
                #
                # AND IT CANNOT BE EVICTED BY ITS OWN PASS. One pass
                # appends at most 1 marker + 200 records against a
                # 2000-block cap, so a marker drawn first still has
                # about 1800 blocks of headroom when its own pass ends.
                # The 200-line slice and the 2000-block cap both stay:
                # an unbounded render would stall the Qt GUI thread,
                # and that is an arc of its own.
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
                    # ESCAPE EVERYTHING. appendHtml parses its input, so
                    # an unescaped payload containing < or > is silently
                    # SWALLOWED — and repr() of most objects looks like
                    # "<Foo at 0x...>". Observed: a site of "<stdin>"
                    # vanished, leaving a bare ":23". That is data loss in
                    # the one pane whose job is to show data faithfully.
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
                    # AFTER the append, never before. A raise inside
                    # `appendHtml` leaves the count truthful about what
                    # is really on the pane rather than about what this
                    # loop intended to put there.
                    self._signal_rendered += 1
            except Exception as exc:  # noqa: BLE001 - display is best-effort
                logger.debug("signal drain failed: %s", exc)

        def _toggle_console_pause(self) -> None:
            """Toggle the Console log handler's pause state.

            10.7 -- `console.14.004` and `console.14.005`. BOTH ARE
            TOGGLE PINS. They fire when the operator presses this
            button and at no other time, so silence from either says
            nothing about the tab's health; only the three cadence pins
            in `_emit_console_health` may be read that way.

            Neither reads `paused` back out as though the argument were
            the result. 004 asks the flag the SIGNAL drain consults;
            005 asks the console widget how many blocks it now holds.
            """
            paused = self._console_pause_btn.isChecked()
            # issue #49 -- THE SIGNALS HALF OF THE BUTTON, AND IT IS SET
            # BEFORE THE HANDLER GUARD ON PURPOSE. `_drain_signals`
            # gates the signals pane on this flag; `set_paused` below
            # stops the log pane. Two panes, two mechanisms, one press.
            # A missing `_console_log_handler` returns two lines down,
            # and quieting one pane must not be conditional on the other
            # pane's plumbing existing.
            #
            # NO DRAIN CAN INTERLEAVE with what follows. `_drain_signals`
            # is a `QTimer` slot and this is a `clicked` slot; both run
            # on the Qt GUI thread, so the order of the statements here
            # is a readability decision and not a race.
            _set_console_paused(self, paused=paused)
            handler = getattr(self, "_console_log_handler", None)
            if handler is None:
                return
            import contextlib
            import time as _pause_clock

            # READ BEFORE THE DRAIN RUNS. Once `set_paused(False)`
            # returns, the buffer is empty and the drop counter is
            # zeroed, so the size of the debt is unrecoverable. The
            # empty document counts as ZERO lines, not one: an empty
            # QPlainTextEdit reports `blockCount() == 1`, and the first
            # line lands IN that block rather than after it.
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
            except Exception:  # noqa: BLE001 - observation only
                _console = None
            _t0 = _pause_clock.monotonic()
            handler.set_paused(paused)
            _elapsed = _pause_clock.monotonic() - _t0
            # Read the widget back out HERE, before the button text and
            # the indicator label are touched, so nothing between the
            # operation and its observation can add a line.
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
            # 10.7 -- console.14.004. THE BUTTON QUIETS BOTH PANES,
            # and since issue #49 it really does: `_drain_signals`
            # gates on `self._console_paused`, `_set_console_paused`
            # above assigns it, and `set_paused` stopped the log pane.
            # This asks the flag the drain actually reads, after the
            # toggle has run, against the button the operator just
            # pressed -- so a repair that is reverted, renamed away or
            # skipped by an early return reports red here instead of
            # going quiet.
            #
            # NO DURATION (E8): reading a flag follows no operation, so
            # a number here would be fabricated.
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
            # 10.7 -- console.14.005, THE RESUME ONLY. On the pause
            # press `set_paused` delivers nothing, so there is no
            # delivery to judge and the pin stays quiet rather than
            # asserting a vacuous zero.
            #
            # `expected` is what the resume OWED: the lines the buffer
            # was holding, plus the one notice line `set_paused` adds
            # when it dropped any. `actual` is the widget's own block
            # count afterwards. They part company when the pane's block
            # cap eats the delivery -- the operator paused precisely to
            # keep those lines, and the cap throws them away silently.
            #
            # THE DURATION IS THE ONLY ONE IN THIS TAB and it is the
            # only site that may carry one (E8): the drain paints up to
            # `_buffer_max` lines into a widget on the GUI thread, which
            # is a real bounded operation. The bracket opens one line
            # above `set_paused` and closes one line below it.
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
            """While paused, update the buffered-count display every 500ms."""
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
            """Report the signal drain FROM OUTSIDE THE DRAIN.

            10.7 -- `console.14.001`, `console.14.002` and
            `console.14.003`.

            WHY THIS METHOD EXISTS AT ALL, rather than three pins inside
            `_drain_signals`. The Console is a CONSUMER of the sink the
            emitter network writes to. A pin on the drain path writes a
            record into the collection it is draining; the next tick
            reads that record, renders it and emits again, so the pin's
            own rate becomes a function of the quantity it measures.
            `every=` reduces that rate and does not break the coupling,
            and the synchroniser never folds a FAILING check -- so the
            one state worth reporting is the one state that would run
            un-throttled.

            THE COUPLING IS BROKEN BY MAKING THE EMISSION RATE
            INDEPENDENT OF THE SINK. This method is driven by its own
            5000 ms QTimer, so it writes at most three records per
            interval whatever the sink holds: a constant slope, exactly
            like every other cadence pin in the tree. `_drain_signals`
            only counts.

            THE THREE QUANTITIES ARE ALSO CHOSEN SO A CONSOLE RECORD
            MOVES BOTH SIDES OF EVERY COMPARISON BY THE SAME AMOUNT. A
            record written here is read once and rendered once, so
            `read - rendered` is unchanged by it; it adds one block and
            one rendered line, so the pane's count and the ledger's
            count move together. No verdict here can be driven by this
            method's own traffic. `evicted` is the one quantity that
            does grow with it, which is why it rides in `context` as a
            number and is not part of any expectation.

            WHAT ISSUE #48 CHANGED ABOUT `14-002`, STATED AND NOT LEFT
            TO DRIFT. The drain now draws two kinds of line: records,
            and a gap marker over a stretch the slice stepped over. The
            pin still asks whether the pane holds what the drain drew,
            but "what the drain drew" is now `_signal_rendered +
            _signal_markers` rather than `_signal_rendered` alone, and
            `gap_markers` rides in `context` so a reader of
            `session.jsonl` can take the two apart. `14-001` is
            UNCHANGED: it asks whether every record the watermark
            consumed reached the pane, a marker is not a record, and a
            Console that quietly keeps up must stay distinguishable in
            the record stream from one that quietly skips.

            THE ONE THING IT CANNOT REPORT IS ITS OWN SILENCE. If the
            GUI thread wedges, this timer stops with the drain and
            nothing is written at all. That is the seam the Watchdog arc
            takes: the sink's JSONL is append-only, and a cadence pin
            that stops writing is readable from outside the process when
            nothing inside it can still speak.

            Never raises, for the reason `_drain_signals` never does.
            """
            try:
                view = getattr(self, "_signal_view", None)
                if view is None:
                    return
                import contextlib

                from src.core.signal_contract import emit as _co_emit

                _ticks = getattr(self, "_signal_drain_ticks", 0)
                _seen = getattr(self, "_signal_health_ticks_seen", 0)
                # Advanced on EVERY invocation, admitted or folded. The
                # window an admitted record reports is therefore the
                # last look's window, not the throttle's -- and a look
                # that found nothing is a FAIL, which is never folded.
                self._signal_health_ticks_seen = _ticks
                _read = getattr(self, "_signal_read", 0)
                _rendered = getattr(self, "_signal_rendered", 0)
                _markers = getattr(self, "_signal_markers", 0)
                _blocks = int(view.blockCount())
                _cap = int(view.maximumBlockCount())
                _timer = getattr(self, "_signal_timer", None)
                _look = getattr(self, "_console_health_timer", None)
                # An empty QPlainTextEdit reports one block, so the
                # floor is 1 rather than 0. Above the cap the pane keeps
                # exactly `_cap` blocks -- measured, not assumed.
                #
                # issue #48. `+ _markers` IS THE RESTATEMENT, WRITTEN
                # DOWN RATHER THAN LEFT TO DRIFT. Before the gap marker
                # this pin compared the pane's block count against
                # `_signal_rendered` alone, because records were the
                # only thing the drain drew. A gap marker is a block
                # too, so the drain now draws two kinds of line and
                # `14-002` counts both. Left as `_rendered` alone the
                # pin would go red by exactly the number of markers --
                # red for drawing the notice that makes a skip visible,
                # which is the `06-014` defect wearing a new hat.
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
            except Exception as exc:  # noqa: BLE001 - display is best-effort
                logger.debug("console health emit failed: %s", exc)

        def _setup_status_bar(self) -> None:
            status = QStatusBar()
            status.showMessage("Ready")

            # v3.23.40 — API-load pill. Reads api_load_monitor per
            # connected exchange; shows worst-case CPM + colour band
            # (green ≤ 50 %, amber 50-75 %, red > 75 %). Refresh-timer
            # driven via _refresh_api_load_pill().
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

            # AI Monitor indicator
            self._ai_monitor_label = QLabel("AI: OFF")
            self._ai_monitor_label.setStyleSheet(
                f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; padding: 0 8px; "
                "font-family: Consolas;"
            )
            status.addPermanentWidget(self._ai_monitor_label)

            # Update AI monitor indicator from saved settings
            if self._settings:
                ai_cfg = self._settings.get("ai_monitor", {})
                if ai_cfg.get("enabled") and ai_cfg.get("api_key"):
                    self._ai_monitor_label.setText("AI: READY")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.STATUS_AUTHENTICATED}; font-size: 10px; padding: 0 "
                        "8px; font-family: Consolas;"
                    )

            self.setStatusBar(status)

        # Fault records for the two pumps below, at ERROR then one
        # summary per window. Class attributes: process lifetime, the
        # same as the singletons they speak for.
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
            """v3.23.41 — schedule a lazy CurrencyRateMonitor refresh
            and push the current snapshot into the Indicator Voting
            Panel. Lazy: the monitor's ``refresh_from_connectors``
            short-circuits when its snapshot is still fresh (60 s
            cadence), so this fires at 2 s tick without hammering
            the exchange."""
            try:
                from ..exchange.currency_rate_monitor import get_currency_monitor

                mon = get_currency_monitor()
                if mon is None:
                    return  # down; the monitor reported itself
                connectors = getattr(self, "_exchange_connectors", {}) or {}
                if connectors:
                    self._schedule_async(mon.refresh_from_connectors(connectors))
                # Push whatever snapshot we currently have (may still
                # be empty on the very first tick).
                if hasattr(self, "_indicator_panel"):
                    self._indicator_panel.update_currency_rates(mon.snapshot())
                self._currency_pump_fault.note_success()
            except Exception as exc:  # noqa: BLE001 - pump best-effort
                self._currency_pump_fault.note_failure(exc)

        def _pump_market_pairs_scout(self) -> None:
            """v3.23.47 — schedule a lazy MarketPairsScout refresh so
            every bot (and the Bot Details Status tab in v3.23.48) has
            a fresh view of all pairs trading each target asset on
            each connected exchange. Lazy: the scout's own
            ``refresh_from_connectors`` short-circuits when its per-
            exchange snapshot is still fresh (10 s cadence), so this
            fires safely at every dashboard tick."""
            try:
                from ..exchange.market_pairs_scout import get_scout

                scout = get_scout()
                if scout is None:
                    return  # down; the scout reported itself
                connectors = getattr(self, "_exchange_connectors", {}) or {}
                if connectors:
                    # v3.23.59 — coalesce (same reason as chart
                    # fetch above): cancel the last pending scout
                    # refresh before scheduling the next.
                    self._cancel_if_pending(
                        getattr(self, "_pending_scout_refresh", None)
                    )
                    self._pending_scout_refresh = self._schedule_async(
                        scout.refresh_from_connectors(connectors)
                    )
                self._scout_pump_fault.note_success()
            except Exception as exc:  # noqa: BLE001 - pump best-effort
                self._scout_pump_fault.note_failure(exc)

        def _refresh_api_load_pill(self) -> None:
            """Update the status-bar API-load pill from api_load_monitor.
            Reports the worst-loaded connected exchange."""
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
            except Exception as _pill_exc:  # noqa: BLE001 - pill best-effort
                # DEBUG: the API-load pill is a decoration on the status
                # bar. When it cannot be refreshed it keeps its previous
                # text, and the rate-limit data behind it is still
                # readable in the API log. Nothing an operator acts on
                # is dropped, so this stays out of the warning stream
                # that a timer would otherwise flood once a second.
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
            """Subtle pulsation on accent elements using QGraphicsOpacityEffect.
            This approach does NOT interfere with theme stylesheets."""
            from PySide6.QtWidgets import QGraphicsOpacityEffect

            self._pulse_phase = 0.0
            self._pulse_effects: list[QGraphicsOpacityEffect] = []
            # MEM-239 — registry of Fire button drop-shadow glow effects;
            # pulse-ticker animates their blur radius so armed bots
            # visually throb rather than sitting as a static glow.
            self._fire_glow_effects: list = []

            # Apply opacity effects to stat cards, accent buttons, group box titles
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
            """MEM-239 — called from BotStatusTable when it creates a
            new QGraphicsDropShadowEffect for an ARMED Fire button.
            The pulse ticker then animates its blur radius for a
            throbbing glow.

            Prunes dead references on each call so the registry doesn't
            grow unbounded across refresh cycles (BotStatusTable
            recreates widgets per refresh; old effects become dangling)."""
            # Trim dead/deleted effects (calling a method on a deleted
            # Qt object raises RuntimeError)
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
            # Subtle opacity oscillation: 0.82 to 1.0
            opacity = 0.91 + 0.09 * math.sin(self._pulse_phase)
            for effect in self._pulse_effects:
                try:  # noqa: SIM105
                    effect.setOpacity(opacity)
                except RuntimeError:
                    pass
            # MEM-239 — throb Fire button glows between blur radius 12 and 22
            # (stronger oscillation than the opacity pulse — the glow should
            # read as "alive", not subtle).
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

        # v3.23.7 — Global privacy-mask refresh hook
        def refresh_all_privacy_widgets(self) -> None:
            """Repaint every dot + re-render every masked value after a
            registry mutation (typically the global Privacy Mode flip).

            Walks the widget tree once and calls the per-widget refresh
            hooks where they exist. Tolerates missing hooks: components
            that haven't opted into the privacy contract are skipped.
            """
            # 1. Spendable widget — 5 KPI dots + values
            try:
                if (
                    hasattr(self, "_spendable_widget")
                    and self._spendable_widget is not None
                ):
                    self._spendable_widget.refresh_privacy_dots()
            except Exception:  # R28-OK  # noqa: S110
                pass
            # 2. Top-right StatCards — 5 counter dots + values
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
                except Exception:  # R28-OK  # noqa: S110
                    pass
            # 3. ExchangeTab Privacy Mode button(s) — re-style based on
            # the new state. Also re-render the bot tables so masked
            # values reflow into the cells.
            try:
                for tab in getattr(self, "_exchange_tabs", {}).values():
                    if hasattr(tab, "_refresh_privacy_mode_btn_style"):
                        tab._refresh_privacy_mode_btn_style()
                    # Re-render last bot statuses to push mask_or through.
                    # tab.update_bots is idempotent — calling it with the
                    # last known list re-applies all cell formatting.
                    try:
                        if self._bot_manager and hasattr(tab, "exchange_id"):
                            statuses = self._bot_manager.list_bots_by_exchange(
                                tab.exchange_id
                            )
                            tab.update_bots(statuses)
                    except Exception:  # R28-OK  # noqa: S110
                        pass
            except Exception:  # R28-OK  # noqa: S110
                pass
            # 4. IVP / Indicator panel — refresh bot-selector dot
            try:
                if (
                    hasattr(self, "_indicator_panel")
                    and self._indicator_panel is not None
                    and hasattr(self._indicator_panel, "refresh_privacy_dot")
                ):
                    self._indicator_panel.refresh_privacy_dot()
            except Exception:  # R28-OK  # noqa: S110
                pass

        def _setup_tooltips(self) -> None:
            """Apply tooltips for all abbreviated and technical terms. Rescans periodically."""
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
                # Trading terms
                "P/L": "Profit / Loss - net gain or loss from closed trades",
                "P&L": "Profit and Loss - same as P/L",
                "Realised": "Realised P/L - profit/loss from positions that have been closed",
                "Locked": "Locked - value committed to open positions less than 30 days old",
                "Mature": "Mature - profits from positions filled 30+ days ago, safely withdrawable",
                "Spendable": "Spendable Profits - estimated expendable liquidity from mature positions",
                "Extended": "Extended Position - extra position created when accumulated profit reaches position size",
                "Grid": "Grid Mode - stacked buy/sell pairs at fixed price intervals",
                "Scrumming": "Speculative Scrumming - TA-driven delta trading against a target balance",
                "Phantom": "Phantom Balance Bot - shadow bot analyzing a different timeframe",
                "Folding": "Profit Folding - distributing realized sell profits back into buy positions",
                "Distribution": "Upward Distribution - distributing accumulated asset into sell positions",
                # Technical Analysis
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
                # Data terms
                "TF": "Timeframe - candle duration (1m, 5m, 15m, 1h, 4h, 1d, 1w)",
                "OHLCV": "Open, High, Low, Close, Volume - the five data points per candle",
                "Vol": "Volume - total value traded in a given period",
                "Volat": "Volatility - measure of price variation; higher = more price movement",
                # System terms
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

            # Run scan immediately and then every 5 seconds for new widgets
            QTimer.singleShot(500, self._apply_abbreviation_tooltips)
            self._tooltip_timer = QTimer(self)
            self._tooltip_timer.timeout.connect(self._apply_abbreviation_tooltips)
            self._tooltip_timer.start(5000)

        def _apply_abbreviation_tooltips(self) -> None:
            """Scan all widgets and set tooltips for matching abbreviated terms."""
            # Scan QLabel widgets
            for label in self.findChildren(QLabel):
                text = label.text()
                if not text or label.toolTip():
                    continue
                for abbrev, explanation in self._abbreviation_tooltips.items():
                    if abbrev in text:
                        label.setToolTip(explanation)
                        break

            # Scan QPushButton text
            for btn in self.findChildren(QPushButton):
                text = btn.text()
                if not text or btn.toolTip():
                    continue
                for abbrev, explanation in self._abbreviation_tooltips.items():
                    if abbrev in text:
                        btn.setToolTip(explanation)
                        break

            # Scan QGroupBox titles
            for gb in self.findChildren(QGroupBox):
                text = gb.title()
                if not text or gb.toolTip():
                    continue
                for abbrev, explanation in self._abbreviation_tooltips.items():
                    if abbrev in text:
                        gb.setToolTip(explanation)
                        break

        def _on_api_event(self, entry: dict) -> None:
            """Handle incoming API interaction log entry and display in UI."""
            # MEM-216 — cross-thread detector. This slot writes to a
            # QPlainTextEdit, which MUST happen on the main (GUI) thread.
            # If api_logger.record() is ever called from a background
            # thread (direct listener dispatch via a to_thread executor,
            # future refactor regression, etc.), touching the widget
            # here would crash the app via Qt qFatal. Detect and log
            # the violation instead of crashing; the log preserves the
            # diagnostic the operator lost in Session 23.
            import threading as _threading

            current = _threading.current_thread().name
            origin = entry.get("_thread_name", "unknown")
            if current != "MainThread":
                # We are about to touch a widget from the wrong thread.
                # Log the violation and REFUSE — dropping the UI update
                # is strictly better than crashing the process.
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
                    # Suppression audit 2026-08-13, H7. The
                    # refusal above still happens; only the
                    # evidence was lost. This record is the
                    # asyncio-on-GUI-thread arc's only field
                    # instrument, so when the file cannot be
                    # written it goes to the logger rather than
                    # nowhere. No widget is touched here: this
                    # branch runs on the offending thread.
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

            # MEM-204 — plain-text append, no HTML parsing. Colors dropped
            # here (less critical than the main Console). Reason, endpoint,
            # result, timing are all self-explanatory from the text prefix.
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
            # v3.15.67 — when the operator has the API log paused, buffer
            # the block instead of appending. Cap at 2000 to keep memory
            # bounded; oldest dropped (deque-style trim from the front).
            if getattr(self, "_api_log_paused", False):
                buf = self._api_log_pause_buffer
                buf.append(block_text)
                cap = self._api_log_pause_buffer_cap
                if len(buf) > cap:
                    del buf[: len(buf) - cap]
                return
            self._api_log_view.appendPlainText(block_text)
            # Auto-scroll only if already at bottom (respects manual scroll)
            sb = self._api_log_view.verticalScrollBar()
            if sb.value() >= sb.maximum() - 20:
                sb.setValue(sb.maximum())

        # --- Startup exchange verification ---
        def _verify_exchanges_on_startup(self) -> None:
            """Check exchange connectivity on launch and log to API panel."""
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
                    reason="Application launched, checking configured exchanges",
                    result="No exchanges configured",
                    level="warning",
                    data_usage="User needs to add an exchange in Settings before creating bots",
                )
                return

            _log.record(
                exchange="app",
                action="STARTUP_CHECK",
                reason=f"Application launched, verifying {len(exchanges)} exchange(s)",
                result="Checking credentials...",
                level="info",
                data_usage="Each exchange will be checked for stored API credentials",
            )

            self._status_log.log(f"Verifying {len(exchanges)} exchange(s)...")
            for exch in exchanges:
                eid = exch.get("exchange_id", "")
                has_key = bool(exch.get("api_key_enc", ""))
                if has_key:
                    self._status_log.log(
                        f"  {eid.capitalize()}: credentials stored", "info"
                    )
                    self._spool.notify(
                        f"{eid.capitalize()}: credentials present, ready to trade",
                        "info",
                    )
                    _log.record(
                        exchange=eid,
                        action="CREDENTIAL_CHECK",
                        reason=f"Checking if {eid.capitalize()} has stored API credentials",
                        result="Credentials found (encrypted). Ready for authenticated API calls.",
                        level="success",
                        data_usage="Bot can be started for this exchange. Will authenticate on first API call.",
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
                # v3.15.50 — high-score cards. Format with comma thousands
                # + 2dp; numbers are cumulative USD so 2dp is plenty.
                _scr = float(agg.get("total_scrummed_usd", 0.0) or 0.0)
                _fld = float(agg.get("total_folded_usd", 0.0) or 0.0)
                self._stat_scrummed.set_value(f"${_scr:,.2f}")
                self._stat_folded.set_value(f"${_fld:,.2f}")
                # P/L card is hidden from header but still updated for
                # any consumer that reads its current value programmatically.
                self._stat_pnl.set_value(f"${agg['total_realised_pnl']:+,.4f}")
                self._stat_trades.set_value(str(agg["total_trades"]))
                self._stat_bots.set_value(str(agg["running"]))
                # v3.16.46 — show lifetime cumulative count, not current-state.
                self._stat_errors.set_value(str(agg.get("total_errors_lifetime", 0)))

                # v3.16.48 — Operator directive 2026-05-10:
                #   "How and why are you calculating the P/L!?
                #    Pull the data and display it. Spendable balance
                #    is my cash."
                #
                # Direct exchange-pulled values:
                #   Spendable = wallet cash (USD + USDC, fetched from
                #               connector during periodic refresh)
                #   Locked    = sum of bot position values (pulled from
                #               exchange via tick-time MEM-226 handshake)
                #
                # No P/L calculation. No 30/70 split. No FIFO matching.
                # Realised / Mature pass as None (the operator hasn't
                # specified what they want shown there; if added later,
                # it must come from a direct exchange-pulled source).
                exchanges = len(self._exchange_tabs)
                _wallet_cash = float(agg.get("wallet_cash_usd", 0.0) or 0.0)
                _crypto_value = float(agg.get("crypto_position_value_usd", 0.0) or 0.0)
                # If no bot has refreshed cash yet AND no positions are
                # known, show "—" (early-startup state). Otherwise show
                # whatever we have, even partial.
                if _wallet_cash > 0 or _crypto_value > 0:
                    self._spendable_widget.update_profits(
                        {
                            "spendable": _wallet_cash,
                            "total_realised": None,  # not exchange-pulled — show "—"
                            "locked": _crypto_value,
                            "mature": None,  # not exchange-pulled — show "—"
                            "exchange_count": exchanges,
                        }
                    )
                else:
                    # Pre-refresh state — show "—"
                    self._spendable_widget.update_profits(
                        {
                            "spendable": None,
                            "total_realised": None,
                            "locked": None,
                            "mature": None,
                            "exchange_count": exchanges,
                        }
                    )

                # Update exchange tabs
                all_statuses = []
                for eid, tab in self._exchange_tabs.items():
                    exchange_statuses = self._bot_manager.list_bots_by_exchange(eid)
                    tab.update_bots(exchange_statuses)
                    all_statuses.extend(exchange_statuses)

                # Also include bots not in any exchange tab
                all_bot_statuses = self._bot_manager.list_bots()
                seen_ids = {s.get("bot_id") for s in all_statuses}
                for s in all_bot_statuses:
                    if s.get("bot_id") not in seen_ids:
                        all_statuses.append(s)

                # v3.24.38 (C10 / SWARM-A8) — the Swarm must be updated
                # UNCONDITIONALLY. It used to sit behind `if
                # all_statuses:`, so deleting the last bot meant
                # update_bots([]) was never called and the Swarm went on
                # rendering bots that no longer existed, indefinitely.
                # update_bots already handles the empty list correctly:
                # its removal pass drops every widget whose id is absent
                # from the incoming set, which for [] is all of them.
                try:
                    self._bot_viz.update_bots(all_statuses)
                except Exception as e:
                    logger.error("DASHBOARD: Bot Viz CRASHED: %s", e)
                    import traceback

                    traceback.print_exc()

                # Update charts and market map with ALL bots
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

                    # v3.23.40 — refresh API-load pill on the dashboard
                    # tick. Cheap (reads in-memory api_log).
                    try:
                        self._refresh_api_load_pill()
                    except Exception as _api_pill_exc:
                        logger.debug("API-load pill refresh raised: %s", _api_pill_exc)

                    # v3.23.41 — schedule a lazy BTC/USD + ETH/USD
                    # rate refresh (short-circuits if snapshot is
                    # still fresh at CurrencyRateMonitor's 60s
                    # cadence) and push the current snapshot into the
                    # Indicator Voting Panel's rate strip.
                    try:
                        self._pump_currency_rates()
                    except Exception as _rate_exc:
                        logger.debug("currency rate pump raised: %s", _rate_exc)

                    # v3.23.47 — schedule a lazy MarketPairsScout
                    # refresh so every bot (and the Bot Details Status
                    # tab in v3.23.48) has fresh per-pair data for its
                    # target asset. Short-circuits when the scout's
                    # per-exchange snapshot is still fresh at its 10s
                    # cadence, so this is safe to fire every tick.
                    try:
                        self._pump_market_pairs_scout()
                    except Exception as _scout_exc:
                        logger.debug("market pairs scout pump raised: %s", _scout_exc)

                    # MEM-236 — Tracking beep dispatcher. Operator
                    # directive: "Have bots beep at increasing speeds
                    # when tracking."
                    #
                    # SEARCH phase = silent (nothing interesting yet).
                    # TRACK phase  = slow beep (band approached; scrum
                    #                may fire soon).
                    # FIRE phase   = fast beep (scrum condition met;
                    #                bot is about to shoot).
                    #
                    # One beep per cadence period ACROSS all bots (not
                    # per-bot) — multiple beeps from simultaneous
                    # tracking would overlap into noise. The cadence
                    # is determined by the "hottest" phase among all
                    # bots: any bot in FIRE → fast cadence.
                    #
                    # Volume is controlled by SoundConfig.volume (set
                    # via Settings dialog SFX volume slider — see
                    # MEM-236 settings wire-up).
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

                # Feed Indicator Panel
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
                                # v3.23.40 — fold in phantom-bot per-TF
                                # summaries as additional rows, and
                                # compute a Composite Net on the parent
                                # row using the rank-weighted formula
                                # from phantom_balance (higher-TF
                                # phantoms only, confidence >= 0.30).
                                merged: dict = {tf: parent_tf_data}
                                composite_net = parent_net
                                try:
                                    if getattr(bot, "_phantoms_enabled", False):
                                        pmulti = (
                                            bot.get_multi_tf_summary()
                                            if hasattr(bot, "get_multi_tf_summary")
                                            else {}
                                        )
                                        # Add phantom rows that aren't
                                        # the same TF as parent.
                                        for p_tf, p_data in (pmulti or {}).items():
                                            if p_tf == tf:
                                                continue
                                            merged[p_tf] = dict(p_data)
                                        # Composite Net: linear rank-
                                        # weighted using tf_rank from
                                        # phantom_balance. Parent gets
                                        # weight = rank(parent_tf).
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
                                                continue  # LTF phantoms don't feed composite
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
                                # UNIT 1 — keep the reading that was
                                # just rendered. `_last_summary` lives
                                # only on the bot object, so a restart
                                # discards it and a bot that parks in
                                # its dust band never produces another
                                # one. Nothing is computed or fetched
                                # here: `merged` is the dict that was
                                # rendered on the line above, and the
                                # panel skips the write unless the
                                # reading actually changed.
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
                                # v3.24.54 (R1) — neither `if` above had
                                # an else, so a selected bot with no
                                # `_last_summary` produced NOTHING: the
                                # panel kept whatever was last on it and
                                # no log line was written on either the
                                # success or the failure path. That
                                # absence is the reason diagnosing the
                                # blank panel needed a four-lane
                                # investigation arguing from silence.
                                #
                                # Name the actual state. These are
                                # genuinely different situations and only
                                # one of them is a fault.
                                #
                                # UNIT 2 (2026-08-13) — the branch that
                                # used to live here answered the two
                                # RUNNING cases with one sentence:
                                # "running — no TA read yet (first read
                                # can take ~60s; a bot parked at target
                                # evaluates no TA)". It led with the
                                # transient cause, so the operator read
                                # "~60s", waited, and switched bots for
                                # minutes while the real answer was the
                                # second clause — which never resolves
                                # on its own. The bot already records
                                # which applies. Ask it.
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
                            # v3.23.59 — coalesce: cancel any still-
                            # pending fetch before spawning the next.
                            # Prevents the "Task was destroyed but
                            # pending" warnings at shutdown when
                            # exchange latency lets multiple ticks'
                            # fetches pile up.
                            self._cancel_if_pending(
                                getattr(self, "_pending_chart_fetch", None)
                            )
                            self._pending_chart_fetch = self._schedule_async(
                                self._charts_tab.fetch_chart_data(
                                    self._exchange_connectors
                                )
                            )
                        except Exception:  # noqa: S110
                            pass
                        # v3.23.37 — Market Inspector owns its own
                        # fetch cycle (CoinGecko OHLC on Refresh button;
                        # rate-limited to 15 min). No periodic tick
                        # dispatch needed here; the previous market_map
                        # periodic fetch was tuned for the 60 s ticker
                        # refresh, which does not apply to the HTF
                        # analyzer.

                # --- Advanced subsystem updates (every 2s cycle) ---
                try:
                    # Risk manager evaluation
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

                    # Analytics equity snapshot (every 10s)
                    if self._analytics and hasattr(self, "_last_equity_snap"):
                        if time.time() - self._last_equity_snap >= 10:
                            self._analytics.snapshot_equity(self._bot_manager)
                            self._last_equity_snap = time.time()
                    elif self._analytics:
                        self._analytics.snapshot_equity(self._bot_manager)
                        self._last_equity_snap = time.time()

                    # Crash recovery snapshot (every 30s)
                    if self._crash_recovery:
                        self._crash_recovery.save_snapshot(self._bot_manager)

                    # P/L milestone check
                    if self._notif_manager and agg:
                        self._notif_manager.check_pnl_milestone(
                            agg.get("total_realised_pnl", 0)
                        )

                    # Refresh new tabs (throttled to every 4s to avoid UI churn)
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

                    # AI Monitor check (async, only when interval elapsed)
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

        # --- Exchange tab management ---
        def _is_equity_exchange(self, exchange_id: str) -> bool:
            """Return True if this exchange ID belongs to the stock/equity layer."""
            return exchange_id.lower() in self._equity_exchange_ids

        def add_exchange_tab(self, exchange_id: str, display_name: str) -> None:
            """Add exchange tab to the correct layer (crypto or stock)."""
            is_equity = self._is_equity_exchange(exchange_id)

            # Route to the correct layer regardless of which mode is active
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

            # Remove empty state placeholder from the target layer if present
            ph = getattr(self, target_ph_attr, None)
            if ph is not None:
                idx = target_widget.indexOf(ph)
                if idx >= 0:
                    target_widget.removeTab(idx)
                setattr(self, target_ph_attr, None)
                # Keep legacy alias in sync if this is the active layer
                if target_tabs is self._exchange_tabs:
                    self._empty_placeholder = None

            tab = ExchangeTab(
                exchange_id,
                display_name,
                on_new_bot=self._create_bot,
                on_bot_clicked=self._on_bot_clicked,
                on_bot_cmd=self._on_bot_command,
                on_bot_fire=self._on_bot_fire,  # MEM-236
                status_log=self._status_log,
            )
            target_widget.addTab(tab, display_name)
            target_tabs[exchange_id] = tab

            # Keep legacy alias in sync if this is the active layer
            if target_tabs is self._exchange_tabs:
                self._exchange_tabs[exchange_id] = tab

            # 10.5 -- EXCHANGE TAB ROUTING.
            #
            # This is the Bot Swarm misroute in another building.
            # Two layers take the same shape of argument, the
            # routing decision is one boolean, and a tab added to
            # the wrong layer returns exactly as cleanly as a tab
            # added to the right one -- the operator finds out when
            # a broker he configured is simply not on screen.
            #
            # So actual ASKS THE TWO LAYER WIDGETS which of them is
            # holding the new tab, and reports none when neither is.
            # expected is the layer this call was routed to. Neither
            # reads target_widget, which is the argument that went
            # in.
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

        # --- v3.16.52 — Error-log capture + click-to-open dialog ----
        def _on_bot_error_for_log(self, event) -> None:
            """Capture bot.error events into a rolling buffer for the
            Errors-card click dialog.

            Never raises out of this slot: every failure inside is
            caught and logged. Suppression audit 2026-08-13, H6:
            "must not raise" and "must not record" are different
            requirements, and this handler used to do both. A
            non-numeric "consecutive" field raises ValueError on
            the int() below, which dropped the WHOLE error record
            in silence, so the Errors card under-reported with
            nothing anywhere to say that it had.
            """
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
            except Exception:  # R28-OK: telemetry capture must never raise
                logger.exception(
                    "bot.error capture failed; this error record "
                    "was dropped and the Errors card under-reports "
                    "by one"
                )

        @Slot()
        def _show_error_log_dialog(self) -> None:
            """v3.16.52 — open the Error Log dialog. Shows:
              (a) rolling buffer of bot.error events captured this session
              (b) per-bot snapshot of total_errors / consecutive_errors /
                  last_error read live from BotStats
            Operator directive 2026-05-10: 'Need to be able to click on
            the errors read out and open an error log display.'
            """
            try:
                dlg = self._build_error_log_dialog()
                dlg.exec()
            except Exception as exc:
                logger.exception("Error Log dialog raised: %s", exc)

        def _wire_manager(self):
            """The live SmartWireManager, or None.

            v3.24.37 (C06c). The adopt path talks to the wire engine
            only by emitting on the bus, which is fire-and-forget, so
            it could never read back what the engine actually holds.
            """
            try:
                mgr = getattr(self._bot_manager, "smart_wire_manager", None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("C06c: wire manager unreachable: %s", exc)
                return None
            return mgr

        def _wire_is_registered(self, src_id: str, tgt_id: str) -> bool:
            """Did the engine actually take this wire?

            Closed over four inputs. Only the last row moved.

              manager absent  -> True. The caller is confirming an
                  emit it already made, and a missing engine is
                  not evidence the wire was rejected. Answering
                  False here would report a healthy adopt as
                  refused.
              read-back holds tgt_id -> True.
              read-back lacks tgt_id, or returns None -> False.
              read-back raises -> False. Suppression audit
                  2026-08-13, H2. This row used to answer True,
                  so a renamed manager interface raising
                  AttributeError counted as "the engine took it"
                  and reinstated the false success this verifier
                  exists to stop. An engine that is present and
                  unreadable has confirmed nothing.
            """
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
            """Which proposal wires land on a pair that is ALREADY wired.

            Only existing-to-existing pairs can appear here: a bot the
            wizard has not created yet has no wires, so a collision is
            impossible for it. Returns [] rather than raising � a
            pre-flight that can abort the adopt is worse than one that
            discloses nothing, and the caller says so either way.
            """
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
            """Copy the wire registry aside BEFORE an adopt mutates it.

            Same shape as StateManager.preflight_snapshot: a dated file
            in its own subdirectory, bounded retention, never raises.
            This is the data rollback for an adopt that has already been
            applied. Returns the path written, or None.
            """
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
                # Ask the LIVE StateManager where it keeps state rather
                # than re-deriving it: it may have been constructed with
                # a custom config_dir, and a second one built here would
                # resolve to the default and write the snapshot into a
                # directory the app is not using.
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
            """Point the Indicator Panel's TA snapshot store at the LIVE
            state directory.

            UNIT 1. Same rule as ``_snapshot_wires_for_adopt``: ask the
            running StateManager where it keeps state rather than
            re-deriving the default. A StateManager built with a custom
            ``config_dir`` puts its files elsewhere, and a panel that
            re-derived the default would read and write a directory the
            application is not using — the snapshots would be written,
            and never found again.

            Idempotent and cheap; safe to call on every dashboard tick.
            """
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
                # Named rather than blanket: the only things reachable
                # here are a missing StateManager attribute, the lazy
                # import, and Path() rejecting whatever `_dir` turned
                # out to be. Anything else is a real fault and belongs
                # in the tick's own handler, which logs it as a crash.
                logger.warning(
                    "IVP: TA snapshot directory not wired (%s); stored "
                    "readings will fall back to the default state dir",
                    exc,
                )

        def _ivp_cached_candle_count(self, bot) -> int | None:
            """Rows the shared MarketDataPool ALREADY holds for this bot.

            UNIT 2. Reads the pool's in-memory cache dict. It performs no
            fetch, awaits nothing and cannot reach the network: the only
            operation is a dictionary lookup on data some earlier tick
            already paid for. Returns None when there is no cache slot
            at all, which is a different statement from "the slot holds
            zero candles" and must not be collapsed into it.
            """
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
                # The only reachable failures are the lazy import and a
                # bot whose config is missing a field. Named, not
                # blanket, so a genuine fault still surfaces.
                logger.debug("IVP: candle count unavailable: %s", exc)
                return None

        def _ivp_empty_state_cause(self, bot, bot_id: str = "") -> tuple:
            """The ONE reason this bot is showing no TA. Never a list.

            UNIT 2. Returns ``(cause_token, detail_dict)`` for
            ``IndicatorVotingPanel.show_no_data``, which owns the
            wording. Kept as its own method, off the 700-line dashboard
            body, so the decision can be driven directly.

            ORDER MATTERS, and it is not arbitrary:

              1. no bot object       — nothing else can be established.
              2. idle / stopped      — a bot that is not running
                                       evaluates nothing, whatever its
                                       candles look like.
              3. ERROR               — it stopped, and the message is
                                       the actionable part.
              4. parked at target    — the bot's OWN record of the
                                       decision. ``_at_target_counter``
                                       is incremented on the dust-band
                                       return in ScrummingBot.tick and
                                       reset to 0 the moment the tick
                                       gets past that check, so a
                                       non-zero value means the last
                                       tick exited before the TA block.
                                       This is checked BEFORE candles
                                       because a parked bot returns
                                       before it would even ask for
                                       candles, so its cache slot is
                                       whatever the last unparked tick
                                       left there.
              5. too few candles     — a cache slot exists and holds
                                       fewer than the 30 rows both
                                       ``_last_summary`` assignments
                                       require.
              6. cold start          — running, nothing above applies,
                                       no reading yet.

            Reads only fields already in memory. No API call, no TA.
            """
            if bot is None:
                return "bot_missing", {"bot_id": str(bot_id or "")}

            detail: dict = {"bot_id": str(bot_id or "")}
            state = ""
            try:
                state = str(getattr(getattr(bot, "state", None), "value", "")).lower()
            except (AttributeError, TypeError, ValueError) as exc:
                # A state object whose __str__ raises. Named rather than
                # blanket: an unreadable state must leave `state` empty
                # and fall through to the checks below, not swallow a
                # fault from somewhere else.
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
            """Name the bots an aborted adopt left behind.

            The adopt has always left already-created bots in place on
            abort (its own docstring says so), but never said WHICH, so
            the operator was told "aborted" and left to find them by
            eye. They are not deleted here � destroying a bot the
            operator may have wanted is a worse failure than leaving
            one, and it is their call.
            """
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
            """v3.23.69 — hand a topology proposal from the Market
            Inspector right pane into the live bot roster.

            Flow (per design doc § 5):
              1. Confirmation summary (last-guard before any state change).
              2. For each proposal bot with empty ``existing_bot_id``:
                 open the Bot Wizard pre-filled with the suggested
                 target USD. Snapshot ``BotManager.list_bots()`` before
                 and after to capture the newly-created bot_id. If the
                 operator cancels the wizard → abort adoption entirely
                 (leaving any already-created bots in place but drawing
                 NO wires — R70 audit-trail discipline).
              3. Resolve each proposal wire's source + target bot_ids
                 (from ``existing_bot_id`` or the freshly-created map).
              4. Emit ``wire.created`` per wire — BotManager's existing
                 handler calls ``SmartWireManager.register_wire`` and
                 the Bot Swarm tab repaints (both are already subscribed
                 to that event).
            """
            from PySide6.QtWidgets import QMessageBox

            if not isinstance(proposal, dict) or not proposal.get("bots"):
                return
            if not self._bot_manager:
                QMessageBox.warning(
                    self, "Adopt topology", "Bot manager not available."
                )
                return

            # v3.24.39 (D23, operator 2026-08-06) � an adopt APPLIES the
            # whole topology, including pairs that are already wired.
            #
            # A previous revision gated this behind a policy constant and
            # defaulted to skipping collisions. That was wrong twice
            # over. A wire pct is an ordinary user setting, adjustable
            # whenever the operator likes, so there was no permission
            # question to ask. And skipping produced a topology that
            # matched NEITHER the proposal nor the prior state � you
            # adopt "AAA->BBB 25%" and silently get 10%, so the thing on
            # screen is not the thing you applied.
            #
            # What actually matters is DISCLOSURE plus a way back: every
            # changed pair is listed old -> new at the confirm gate
            # before anything is applied, and _snapshot_wires_for_adopt
            # writes the pre-adopt registry to disk, so an adopt the
            # operator regrets is recoverable.
            new_bots = [
                b for b in proposal.get("bots", []) if not b.get("existing_bot_id")
            ]
            wires = list(proposal.get("wires", []))
            new_count = len(new_bots)
            new_budget = sum(
                float(b.get("suggested_target_usd", 0.0)) for b in new_bots
            )

            # asset symbol � bot_id (existing OR freshly created).
            # v3.24.37 (C06c) � hoisted ABOVE the confirmation. It used
            # to be built after the operator had already said Ok, which
            # made it impossible to tell them what the adopt would
            # collide with.
            asset_to_bot: dict[str, str] = {}
            for b in proposal.get("bots", []):
                if b.get("existing_bot_id"):
                    asset_to_bot[str(b.get("asset", "")).upper()] = str(
                        b["existing_bot_id"]
                    )

            # Pre-flight the collisions. Only existing-to-existing pairs
            # can collide: a bot that does not exist yet has no wires.
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

            # v3.24.37 (C06c) � snapshot the wire registry before the
            # first mutation. This is the data rollback for an adopt
            # that has already been applied; without it the only record
            # of the pre-adopt topology was the operator's memory.
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
                except Exception as _cb_exc:  # noqa: BLE001 - wizard surface
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
                # Wizard could in theory create multiple bots if the
                # operator re-opened it; take the first as the mapped id.
                chosen = sorted(new_ids)[0]

                # v3.24.37 (C06c) � validate the binding before trusting
                # it. The wizard is opened with exchange_id="" and only
                # default_target_balance overridden � the symbol is NOT
                # pre-filled and NOT constrained, so the operator can
                # create a bot for any pair at all. Whatever came out
                # used to be bound to this proposal's asset unchecked,
                # which means a proposal wire ETH->BTC could be drawn
                # FROM a bot that trades SOL. That is a live-money
                # misrouting of fold profit, and nothing downstream
                # would ever flag it.
                # `dict` is the element type BotManager.list_bots()
                # declares, and the {} default is one too.
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
                    # Unknown symbol is not proof of a mismatch, so this
                    # does not abort � but it must not read as verified.
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

            # All new bots exist. Draw wires by emitting wire.created
            # on the bus — BotManager's handler calls register_wire on
            # the SmartWireManager, and the Bot Swarm tab repaints.
            # v3.24.39 (D23) � the pairs disclosed as already-wired at
            # the confirm gate. They ARE applied; this is kept only so
            # the closing summary can say how many were changes rather
            # than new wires.
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
                except Exception as _emit_exc:  # noqa: BLE001 - bus surface
                    logger.exception("Topology adopt: wire emit raised: %s", _emit_exc)
                    continue
                # v3.24.37 (C06c) � count what the ENGINE accepted, not
                # what we emitted. register_wire refuses a non-numeric,
                # <= 0 or > 100 pct, and the bus handler discards that
                # refusal, so "N wires drawn" used to count emits and
                # could report a full success for a topology the engine
                # took none of.
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
            """v3.23.68 — assemble live topology-detector context and
            return the ranked proposals. Wired to the Market Inspector
            right pane via ``set_proposal_source``. Runs on the GUI
            thread inside the pane's Refresh + auto-timer callbacks;
            keep it cheap (all detectors are pure over the fixture).
            """
            try:
                from ..trading.topology_proposals import detect_all_topologies
                from ..trading.market_inspector import get_shared_inspector
                from ..exchange.market_pairs_scout import get_scout
            except Exception as _imp_exc:  # noqa: BLE001 - import guard
                logger.debug("topology proposals unavailable: %s", _imp_exc)
                return []

            # Assemble tickers_by_asset from the scout snapshot. We
            # aggregate across every polled exchange; if the same
            # asset is listed on more than one, keep the highest-
            # volume row (matches the "active/selected exchange"
            # discipline — the scout only holds exchanges the app has
            # connected to).
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
            except Exception as _scout_exc:  # noqa: BLE001 - scout best-effort
                logger.debug("topology: scout snapshot unavailable: %s", _scout_exc)

            # Tag existing_bot_id when a running bot targets this asset.
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
            except Exception as _bot_exc:  # noqa: BLE001 - manager surface
                logger.debug("topology: bot snapshot unavailable: %s", _bot_exc)

            # Pull opposing pairs from the shared MarketInspector.
            opposing: list[dict] = []
            try:
                inspector = get_shared_inspector()
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
                        }
                    )
            except Exception as _op_exc:  # noqa: BLE001 - inspector surface
                logger.debug("topology: opposing-pairs unavailable: %s", _op_exc)

            # Correlations for momentum funnel: reuse opposing-pair
            # data where available (both directions), leave the rest
            # zero. Momentum needs positive corrs which the opposing
            # table does NOT contain, so this cascade emits momentum
            # only when the scout has been extended to compute
            # cross-pair positive correlations (v3.23.6x future work).
            # Distance-to-band and mean-reversion + sector still fire.
            correlations: dict[tuple[str, str], float] = {}

            ctx = {
                "tickers_by_asset": tickers,
                "correlations": correlations,
                "opposing_pairs": opposing,
                "bots_snapshot": bots_snapshot,
            }
            try:
                return detect_all_topologies(ctx)
            except Exception as _det_exc:  # noqa: BLE001 - detector surface
                logger.exception("topology: detect_all_topologies raised: %s", _det_exc)
                return []

        def _build_error_log_dialog(self):
            """Construct the dialog. Separated from the click slot so
            tests can introspect the contents without running .exec().
            """
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

            # Header summary (v3.23.60 — drop the "Lifetime" wording;
            # the counter now represents "since last reset").
            try:
                agg = self._bot_manager.get_aggregate_stats()
                _life = int(agg.get("total_errors_lifetime", 0) or 0)
            except Exception:  # R28-OK: best-effort header read
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

            # ── Tab 1 — recent error events ──
            ev_tab = QTableWidget()
            ev_tab.setColumnCount(4)
            ev_tab.setHorizontalHeaderLabels(
                ["Timestamp", "Bot", "Consecutive", "Error"]
            )
            ev_tab.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            ev_tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
            # Most-recent-first
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

            # ── Tab 2 — per-bot snapshot ──
            snap = QTableWidget()
            snap.setColumnCount(5)
            snap.setHorizontalHeaderLabels(
                ["Bot", "Asset", "Lifetime errors", "Consecutive (now)", "Last error"]
            )
            snap.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
            snap.setEditTriggers(QAbstractItemView.NoEditTriggers)
            try:
                _bots = list(self._bot_manager._bots.values())
            except Exception:  # R28-OK: probe; empty fallback
                _bots = []
            snap.setRowCount(len(_bots))
            for row, bot in enumerate(_bots):
                try:
                    _bid = str(getattr(bot, "bot_id", ""))[:8]
                    _asset = str(getattr(bot.config, "target_asset", ""))
                    _tot = int(getattr(bot.stats, "total_errors", 0) or 0)
                    _con = int(getattr(bot.stats, "consecutive_errors", 0) or 0)
                    _last = str(getattr(bot.stats, "last_error", "") or "—")
                except Exception:  # R28-OK: row probe; partial fallback
                    _bid, _asset, _tot, _con, _last = "?", "?", 0, 0, "?"
                snap.setItem(row, 0, QTableWidgetItem(_bid))
                snap.setItem(row, 1, QTableWidgetItem(_asset))
                snap.setItem(row, 2, QTableWidgetItem(str(_tot)))
                snap.setItem(row, 3, QTableWidgetItem(str(_con)))
                snap.setItem(row, 4, QTableWidgetItem(_last))
            tabs.addTab(snap, f"Per-bot snapshot ({len(_bots)})")

            # Footer — actions
            btns = QHBoxLayout()
            btns.addStretch(1)
            # v3.23.60 — Reset button. Operator directive 2026-07-31:
            # "add a reset button for the errors and this should
            # clear out all the previous faults." Zeros per-bot
            # total_errors / consecutive_errors / last_error and
            # clears the in-memory rolling buffer. Header card drops
            # to 0 on next dashboard tick.
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
                        except (
                            Exception
                        ) as _bot_reset_exc:  # noqa: BLE001 - per-bot best-effort
                            # WARNING: the operator pressed "Reset all
                            # errors" and this bot's counters survived
                            # it. The header card will keep counting a
                            # fault the operator believes they cleared,
                            # which is a wrong reading of live state.
                            # The bot is not named: its stats object is
                            # what just failed, so reading an id off it
                            # here could raise inside the handler.
                            logger.warning(
                                "Reset all errors: one bot's counters "
                                "were NOT cleared (%s: %s); the error "
                                "card still counts it.",
                                type(_bot_reset_exc).__name__,
                                _bot_reset_exc,
                            )
                            continue
                    # Persist so a restart doesn't restore the old
                    # counters from disk.
                    try:
                        self._bot_manager.save_all_state()
                    except Exception as _save_exc:  # noqa: BLE001
                        # WARNING: the screen now shows zero but disk
                        # still holds the old counters, so the next
                        # launch restores every fault the operator just
                        # cleared. That gap between what is displayed
                        # and what persists is exactly what an operator
                        # relies on this button to close.
                        logger.warning(
                            "Reset all errors: state was cleared in "
                            "memory but NOT saved (%s: %s); a restart "
                            "will restore the old counters.",
                            type(_save_exc).__name__,
                            _save_exc,
                        )
                except Exception as _reset_exc:  # noqa: BLE001
                    # WARNING: the roster itself could not be walked, so
                    # the reset did not run at all. The dialog still
                    # closes below (unchanged), and the operator would
                    # otherwise read that as success.
                    logger.warning(
                        "Reset all errors: the bot roster could not be "
                        "walked (%s: %s); per-bot counters were left "
                        "as they were.",
                        type(_reset_exc).__name__,
                        _reset_exc,
                    )
                dlg.accept()  # operator reopens to see empty state

            btn_reset.clicked.connect(_reset_all_errors)
            btns.addWidget(btn_reset)
            btn_close = QPushButton("Close")
            btn_close.clicked.connect(dlg.accept)
            btns.addWidget(btn_close)
            v.addLayout(btns)
            return dlg

        # --- Trade verification popup ---
        def _on_bot_log(self, event) -> None:
            """Log bot messages to the activity log.

            MEM-245 — Prefix the message with [TICKER/idsuffix] so the
            operator can see which bot emitted each line. Without this
            prefix the activity log becomes ambiguous the moment two
            bots run at once — operator has to reverse-engineer which
            bot is which from the numbers alone (target, price, delta).

            Format: '[TICKER/last4]' where:
              TICKER  — bot.config.target_asset (e.g. 'BONK', 'RAVE')
              last4   — last 4 chars of bot_id, disambiguates when two
                        bots share the same ticker with different targets
            Fallback: if bot lookup fails for any reason, use
            '[bot_id_last8]' so the line is still attributable.
            """
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
                        # Bot not in manager — still show the id tail
                        prefix = (
                            f"[{bot_id[-8:]}] " if len(bot_id) >= 8 else f"[{bot_id}] "
                        )
                except Exception:
                    # Best-effort: unknown errors should not silence logs
                    prefix = f"[{bot_id[-8:]}] " if len(bot_id) >= 8 else ""
            self._status_log.log(prefix + message, "info")

        def _on_wire_created(self, event) -> None:
            """Report wire creation. Does NOT modify bot config.

            v3.24.35 (C39f). This handler used to execute

                bot.config.profit_folding_active = True

            on every ``wire.created`` event. Three things made that
            indefensible rather than merely convenient:

            1. It rewrote PERSISTED TRADING CONFIG from a GUI event
               handler. The 60-second save then wrote it to disk, so an
               operator who deliberately turned Profit Folding OFF found
               it back on with no record of who changed it.
            2. ``bot_container.py:2404`` re-emits ``wire.created`` for
               every stored wire on EVERY BOOT. So the override was not
               a one-time convenience at draw time — it re-applied at
               every launch, permanently. Turning the setting off was
               impossible to make stick.
            3. The setting is load-bearing: it gates target growth
               (``scrumming_bot.py:1356``) and the DIST tranche rebuild
               (``:8688``).

            If a wire needs folding enabled to be useful, the correct
            behaviour is to SAY SO and let the operator decide. That is
            what this now does. Persisted configuration changes when the
            operator changes it, and at no other time.

            Note for anyone tempted to restore the override "so wires
            work": the DOMINANT wire flow does not depend on this flag.
            ``_route_scrum_proceeds_via_wires`` (scrum-time routing, the
            primary path) never reads it. Only the secondary
            fold-compound route is gated, indirectly via
            ``_growth_applied``.
            """
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
                # Informative, not coercive. The wire still routes at
                # scrum time; only the fold-compound contribution is off.
                self._status_log.log(
                    f"Wire active: {source_id[:8]} — NOTE: Profit "
                    f"Folding is OFF for this bot, so its fold-compound "
                    f"contribution will not fire. Scrum-time routing is "
                    f"unaffected. Enable it in Live Settings if you want "
                    f"compounding from this wire.",
                    "warning",
                )

        def _on_tf_lock_changed(self, event) -> None:
            """Propagate TF lock from Indicator Panel to all Accumulation Bot coordinators."""
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
            """Handle AI feedback received from LiveMonitor."""
            data = event.data if hasattr(event, "data") else {}
            feedback = data.get("feedback", "")
            authenticated = data.get("authenticated", False)

            # Update status bar indicator
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
                # Show in status log
                tag = "✓ AUTH" if authenticated else "⚠ UNAUTH"
                self._status_log.log(
                    f"[AI MONITOR {tag}] {feedback[:200]}",
                    ds.STATUS_AUTHENTICATED if authenticated else ds.WARNING,
                )
                # Log to journal if configured
                ai_cfg = self._settings.get("ai_monitor", {}) if self._settings else {}
                if ai_cfg.get("log_feedback"):
                    try:
                        from ..trading.live_monitor import TradeRecord

                        rec = TradeRecord(
                            timestamp=data.get("timestamp", ""),
                            unix_ts=time.time(),
                            bot_id="AI_MONITOR",
                            asset="SYSTEM",
                            action="AI_FEEDBACK",
                            side="neutral",
                            price=0,
                            quantity=0,
                            usd_value=0,
                            target_balance=0,
                            portfolio_value=0,
                            delta_pct=0,
                            confidence=0,
                            notes=feedback[:500],
                        )
                        if hasattr(self, "_journal") and hasattr(
                            self._journal, "record"
                        ):
                            self._journal.record(rec)
                    except Exception:
                        # Suppression audit 2026-08-13, H5. A
                        # dropped journal write loses an
                        # AI_FEEDBACK note, not a trade. The note
                        # itself is already in the status log
                        # above; this says the durable copy did
                        # not land, which nothing used to say.
                        logger.exception(
                            "AI feedback note was not written to " "the journal"
                        )

        # --- Bot click - show detail ---
        def _on_bot_clicked(self, bot_id: str) -> None:
            if not self._bot_manager:
                return
            bot = self._bot_manager.get_bot(bot_id)
            if not bot:
                return

            from .bot_live_settings import BotLiveSettingsDialog

            # v3.16.18 — Prev/Next navigation loop.
            # The dialog now exposes Prev/Next buttons that close it
            # with `_pending_navigate_to` set to a sibling bot's id.
            # When that happens, re-open the dialog for the target
            # bot at the SAME geometry and on the SAME active tab so
            # the operator's navigation feels seamless. Loop until
            # the dialog is dismissed without a pending navigation
            # (i.e., operator clicked Close or hit Esc).
            saved_geometry = None
            saved_tab_index = None
            current_bot = bot
            while current_bot is not None:
                dlg = BotLiveSettingsDialog(current_bot, self._bot_manager, self)
                dlg.settings_changed.connect(self._on_live_settings_changed)
                if saved_geometry is not None:
                    try:  # noqa: SIM105
                        dlg.setGeometry(saved_geometry)
                    except (
                        Exception
                    ):  # R28-OK: geometry restore is best-effort UX polish  # noqa: S110
                        pass
                if saved_tab_index is not None:
                    try:  # noqa: SIM105
                        dlg._tabs.setCurrentIndex(int(saved_tab_index))
                    except (
                        Exception
                    ):  # R28-OK: tab-restore is best-effort UX polish  # noqa: S110
                        pass
                dlg.exec()
                # Capture geometry + tab BEFORE handling navigation so
                # the next iteration's dialog opens identically placed.
                try:
                    saved_geometry = dlg.geometry()
                except Exception:  # R28-OK: geometry capture is best-effort UX polish
                    saved_geometry = None
                try:
                    saved_tab_index = dlg.active_tab_index()
                except Exception:  # R28-OK: tab capture is best-effort UX polish
                    saved_tab_index = None
                # Decide whether to loop
                target_id = getattr(dlg, "_pending_navigate_to", None)
                if not target_id:
                    break
                next_bot = self._bot_manager.get_bot(target_id)
                if next_bot is None:
                    # Sibling was unregistered between click and lookup
                    break
                current_bot = next_bot

        def _on_live_settings_changed(self, bot_id: str, changes: dict):
            """Handle live settings changes from the detail dialog."""
            self._status_log.log(
                f"Bot {bot_id[:8]}: settings updated live — "
                f"{', '.join(f'{k}={v}' for k, v in changes.items())}",
                "success",
            )
            from ..core.sound_engine import get_sound_engine

            get_sound_engine().play_state_change()

        # --- Bot commands ---
        def _schedule_async(self, coro):
            """Schedule a coroutine on the persistent asyncio loop.
            v3.23.59 — returns the ``concurrent.futures.Future`` so
            callers that need per-slot coalescing (chart fetch,
            scout refresh) can cancel the previous instance before
            spawning the next. Returns ``None`` when running in the
            fallback thread-pool path (rare / test-only)."""
            if self._async_loop:
                return asyncio.run_coroutine_threadsafe(coro, self._async_loop)
            # Fallback: run in thread pool (one-shot, no persistent task)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, coro)
            return None

        @staticmethod
        def _cancel_if_pending(fut) -> None:
            """v3.23.59 — cancel a Future/Task if it exists and is
            not yet done. Silent on any failure — the caller is
            about to schedule its replacement anyway."""
            if fut is None:
                return
            try:
                if not fut.done():
                    fut.cancel()
            except Exception as _cancel_exc:  # noqa: BLE001 - cancel best-effort
                # DEBUG: the caller is about to schedule the replacement
                # for this future either way, so a refused cancel costs
                # at most one stale result that the replacement
                # supersedes. Nothing the operator reads changes.
                logger.debug(
                    "Pending future not cancelled: %s: %s",
                    type(_cancel_exc).__name__,
                    _cancel_exc,
                )

        def _connect_exchange_for_bot(self, bot) -> tuple[bool, str]:
            """
            Create a real exchange connector for a bot, replacing the placeholder.
            Returns (success, message).
            """
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

            # Find credentials in settings
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

            # Decrypt credentials and connect
            try:
                from ..core.encryption import decrypt

                master = f"qat_{self._settings.get('username', 'user')}_vault"
                api_key = decrypt(exch_config["api_key_enc"], master)
                api_secret = decrypt(exch_config["api_secret_enc"], master)
                # None means "this exchange stores no passphrase", which
                # is a different statement from "the passphrase is the
                # empty string" — the second is a credential value, and
                # this code has no business asserting one. The connector
                # still receives "" for the absent case (see the
                # sync_connect call below), so nothing on the wire
                # changes.
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

                # MEM-231 (2026-04-22) — wire history-scan state BEFORE
                # connect(). The scan thread spawns inside sync_connect()
                # with whatever _scan_symbols contains AT THAT MOMENT.
                # MEM-222 wired these calls AFTER connect, so on first-bot
                # start the scan thread found an empty set and exited
                # with "TradeHistorian: no symbols registered". Symbols
                # added later never triggered a re-scan — Refresh works
                # but requires an explicit click, and the History tab
                # appears permanently empty on passive bot-start.
                #
                # Fix: register symbol + callback BEFORE sync_connect().
                # Whole-manager set_connector remains post-connect since
                # it's only needed for the manual Refresh button path.
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
                    # Never let history wiring break bot-start.
                    logger.warning(
                        "MEM-231 pre-connect history wiring " "failed: %s", _exc
                    )

                # Connect synchronously - no asyncio needed
                # sync_connect's contract is a str with "" for absent;
                # convert at that boundary and nowhere earlier.
                connector.sync_connect(api_key, api_secret, passphrase or "")

                _log.record(
                    exchange=eid,
                    action="BOT_CONNECTED",
                    reason="Exchange API authenticated successfully",
                    result="Markets loaded, checking balances...",
                    level="success",
                    data_usage="Bot now has a live exchange connection for trading",
                )

                # Check balance using sync CCXT
                balances_raw = (
                    connector._ccxt_sync.fetch_balance()
                    if hasattr(connector, "_ccxt_sync")
                    else {}
                )

                base = bot.config.base_currency

                # Sync fetch_balance returns dict with 'free', 'used', 'total' sub-dicts
                free_bals = (
                    balances_raw.get("free", {})
                    if isinstance(balances_raw, dict)
                    else {}
                )
                base_free = float(free_bals.get(base, 0) or 0)
                # v3.20.31 ROOT-CAUSE FIX (operator-reported 2026-05-25).
                # Extractor and ScrummingBot have OPPOSITE semantics
                # for base_currency:
                #   - ScrummingBot: base = what you SPEND (e.g. USD
                #     quote of ONDO/USD); target = what you ACCUMULATE
                #     (e.g. ONDO); symbol = ONDO/USD.
                #   - Extractor: base = what you ACCUMULATE (the pool,
                #     e.g. USDC); target = "*" (pool sigil, no single
                #     target); symbol = */USDC.
                # The notification format `f"{base}: X free, {target}:
                # Y free"` only makes sense for ScrummingBot. For
                # Extractor, target="*" makes free_bals.get("*") == 0
                # — BUT if a STALE config from a pre-v3.19.28 wizard
                # write has a real ticker in target_asset (e.g.
                # "ONDO"), the operator sees an UNRELATED wallet
                # balance and is rightfully confused. Worse, if the
                # operator THINKS they created an Extractor but the
                # wizard mode-tag got dropped, they have no way to
                # see it.
                # FIX: tag the message with [MODE SYMBOL] so any
                # mode-tag drift is immediately VISIBLE to the
                # operator at start time, AND show pool semantics
                # for Extractor / spend-and-target for Scrumming.
                from ..trading.bot_container import BotMode as _BM
                from src.trading.start_balance_check import check_start_balance

                _is_extractor_mode = bot.config.mode == _BM.EXTRACTOR

                # Compute target / target_free only for Scrumming;
                # for Extractor, target is the pool sigil "*" and
                # is not a real wallet ticker.
                if _is_extractor_mode:
                    _target_for_helper = ""
                    _target_free_for_helper = 0.0
                else:
                    _target_for_helper = bot.config.target_asset
                    _target_free_for_helper = float(
                        free_bals.get(_target_for_helper, 0) or 0
                    )

                # For non-USD-like base assets on Extractor, fetch
                # the spot price so the USD-denominated chunk threshold
                # check can be applied. v3.20.66 fix MEM-412: pre-fix
                # check used a raw `base_free < 1.0` threshold that
                # demanded ≥ 1 BTC ($63k+) to start a $50-chunk bot.
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

                # Audit-log the check
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
                    # check_start_balance returns the reason as
                    # Optional[str]: None means "no error", which it only
                    # ever pairs with sufficient=True. Every insufficient
                    # branch carries real text, so this fallback does not
                    # fire today. It exists because the alternative is
                    # worse than a redundant line: this reason is handed
                    # straight to the operator and to the API record, and
                    # a None arriving here would render the literal word
                    # "None" as the explanation for why a bot would not
                    # start. The balance summary is always a real string,
                    # so it is what the operator gets instead.
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

                # Replace placeholder exchange with real connector
                bot.exchange = connector
                self._exchange_connectors[eid] = connector

                # MEM-222 (2026-04-22) — register the connector with
                # BotManager so refresh_trade_history() can delegate to it
                # when the user clicks the History tab Refresh button.
                # Symbol + callback registration moved to MEM-231
                # pre-connect wiring (see above) — they must be set
                # BEFORE sync_connect spawns the scan thread.
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
                # Use CCXTConnector's detailed error formatter if available
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
            """MEM-236 + MEM-241 — Manual Fire button handler.

            MEM-241 changes semantic: Manual Fire is now an AGGRESSIVE
            rebalance-to-target. Calls BotManager.force_fire with
            aggressive=True; next tick the scrumming bot executes a
            MARKET order sized to the current delta, bypassing
            TA/BB/MEM-171 gates. Plays the fire SFX on success.
            """
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
            """MEM-236 — Auto-play Fire SFX on scrum/fold/dist fills.
            MEM-238 — Additionally: coins-in-bucket on profit > 0,
            water drip on FOLD events (accumulation moment).

            Operator directives:
              MEM-236: "Try to synthesize a sniper rifle shot for the
                       Fire sound."
              MEM-238: "Coins dropping into a bucket for P/L increases.
                       Dripping water for accumulation."

            Routing rules (all three can fire on the same event):
              - ttype in (SCRUM, FOLD, DIST)  → rifle
              - profit > 0 (from event.data)  → coins
              - ttype == FOLD                  → drip (accumulation)

            "Accumulation" in Acervator is the MEM-171-grade event:
            units gained by buying back more asset than was sold.
            That happens on FOLD. SCRUM and DIST convert direction
            but don't accumulate; they stay silent on drip.
            """
            try:
                ttype = (event.data.get("type") or "").upper()
                profit = event.data.get("profit", 0) or 0
                from ..core.sound_engine import get_sound_engine

                se = get_sound_engine()
                # Rifle — scrum/fold/dist firing events (MEM-236)
                if ttype in ("SCRUM", "FOLD", "DIST"):
                    se.play_fire()
                # Coins — any trade event with positive profit (MEM-238)
                if profit > 0:
                    se.play_profit()
                # Drip — fold events specifically (accumulation, MEM-238)
                if ttype == "FOLD":
                    se.play_drip()
            except Exception:  # noqa: S110
                pass

        def _dispatch_tracking_beep(self, statuses: list) -> None:
            """MEM-236 — Pace tracking beeps by scrum phase.

            Scans status dicts for scrum_target_mode. The "hottest"
            phase among all bots drives the beep cadence:
              - any bot in FIRE  → 200ms cadence (fast)
              - else any in TRACK → 800ms cadence (slow)
              - else              → silent

            Only one beep per cadence period regardless of bot count —
            overlapping beeps would just sound like noise.

            State (lazily initialised on first call):
              self._beep_last_ts: timestamp of last beep emitted
            """
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
                return  # silent

            cadence_s = 0.2 if hottest == "fire" else 0.8
            now = time.monotonic()
            last_ts = getattr(self, "_beep_last_ts", 0.0)
            if now - last_ts < cadence_s:
                return  # throttled

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
                # MEM-215 (Session 23 Addendum 12, 2026-04-22) — REVERT
                # of MEM-213 + MEM-214. Background-thread dispatch with
                # QThread + worker QObject + cross-thread signals kept
                # producing silent app crashes (Qt qFatal) on Start click
                # that we could not root-cause without a live Qt runtime.
                # Reverting to the 3.14.10 synchronous connect flow:
                # GUI freezes briefly during the 5-15s CCXT sync_connect
                # + fetch_balance round-trip, but the app does not crash.
                #
                # UX: emit a prominent "Connecting to <exchange>..."
                # log + spool notification + processEvents() so the user
                # sees visible feedback that the app is working, not
                # hung. Status log writes are cheap and always happen on
                # the main thread.
                eid_display = bot.config.exchange_id.capitalize()
                self._status_log.log(
                    f"⏳ Starting bot {bot_id}... Connecting to {eid_display} "
                    f"(this can take 5-15 seconds, app may appear frozen)",
                    "info",
                )
                self._spool.notify(
                    f"⏳ Bot {bot_id}: connecting to {eid_display}...", "info"
                )

                safe_process_events(
                    "legacy P4.1 site"
                )  # paint the "Connecting..." message

                # Step 1: Connect to real exchange and verify balance.
                # Synchronous on the main thread — blocks GUI during
                # sync_connect + fetch_balance. User sees the feedback
                # message posted above.
                success, msg = self._connect_exchange_for_bot(bot)
                if not success:
                    self._status_log.log(f"Cannot start bot {bot_id}: {msg}", "error")
                    self._spool.notify(f"Bot {bot_id} FAILED: {msg}", "error")
                    sound.play_error()
                    return

                self._status_log.log(f"✓ Bot {bot_id}: {msg}", "success")
                safe_process_events("legacy P4.1 site")

                # MEM-212 — Real Money config paper trail (once per session).
                # Popup was removed in MEM-212; this is the non-blocking
                # replacement that logs the bot's config for audit.
                if not getattr(bot, "_user_verified", False):
                    cfg = bot.config
                    sym = cfg.symbol
                    vis = "Invisible" if cfg.visibility == "internal" else "Order Book"
                    mode = cfg.mode.value.upper()

                    # v3.20.4 — grid-mode detail branch removed
                    # (grid_bot deleted v3.16.0; cfg.mode.value can
                    # never be "grid" since BotMode.GRID was dropped
                    # from the enum). Detail line is now uniform for
                    # all surviving bot types (ScrummingBot and
                    # ExtractorBot both read these fields).
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

                # Step 2: Schedule bot.start() on the persistent asyncio loop
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
                # MEM-215 — synchronous restart (reverts MEM-213/214
                # background worker). Same frozen-but-not-crashed
                # trade-off as the "start" command path.
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
                    # Suppression audit 2026-08-13, H1.
                    # bot.stop() is the ONLY stop on this path.
                    # unregister() releases the reservation, pops
                    # the bot, drops the scan symbol and detaches
                    # the wires; it never sets the stop event and
                    # never cancels an open order. So a scheduling
                    # failure here leaves a live task trading real
                    # money that the manager no longer holds a
                    # reference to, and the dashboard enumerates
                    # from the manager. Record it at error level,
                    # exactly as the "stop" command above does.
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
                # Redirect to the live settings dialog (Adjust Stack tab)
                self._on_bot_clicked(bot_id)

        def _global_bot_cmd(self, command: str) -> None:
            if not self._bot_manager:
                return
            self._status_log.log(f"Executing {command} on all bots...", "info")
            try:
                if command == "start_all":
                    # v3.16.7 — staggered start with progress dialog.
                    # Operator directive 2026-04-28: "need to stagger
                    # auto-start bots with a pop-up notice. Tired of
                    # starting them one by one with each new build."
                    from .start_all_progress_dialog import StartAllProgressDialog

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
                    # Show the progress dialog BEFORE scheduling so it can
                    # subscribe to the 'begin' event.
                    dlg = StartAllProgressDialog(self._bot_manager, parent=self)
                    dlg.show()
                    self._schedule_async(self._bot_manager.start_all())
                elif command == "pause_all":
                    self._schedule_async(self._bot_manager.pause_all())
                elif command == "stop_all":
                    self._schedule_async(self._bot_manager.stop_all())
                self._status_log.log(f"{command} completed.", "success")
            except Exception as exc:
                self._status_log.log(f"{command} failed: {exc}", "error")

        # --- Actions with feedback ---
        def _open_settings(self) -> None:
            # v3.16.20 — pass the current trading-mode wing for the
            # same reason as _add_exchange (Exchanges tab needs to
            # show the broker set that matches the current wing).
            _wing = getattr(self, "_trading_mode", "crypto") or "crypto"
            self._status_log.log(f"Opening settings ({_wing} wing)...")
            from .settings_dialog import SettingsDialog

            dlg = SettingsDialog(self._settings, self._status_log, self, wing=_wing)
            dlg.settings_changed.connect(self._on_settings_changed)
            dlg.exec()

        def _on_settings_changed(self) -> None:
            if not self._settings:
                return
            theme = self._settings.get("theme", "cyberpunk_dark")
            self._switch_theme(theme)

            # Reconfigure LiveMonitor if settings changed
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
            """Reset all settings to defaults and clear stored exchanges."""
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
            """Switch between Crypto and Stock trading layers.

            Duplex architecture: flips the Trading-tab QStackedWidget AND
            the Paper Trader stack together. Both tabs swap atomically
            so the user is always in one wing of the duplex, never
            straddling.

            v3.16.28 — Multi-Scale Paper Trader removed (operator
            directive 2026-05-05: redundant with Paper Trader). The
            Multi-Scale flip code is gone; sentinel checks remain
            harmless because the attrs are None.
            """
            if self._trading_mode == "crypto":
                self._trading_mode = "stock"
                self._mode_btn.setText("Stock Mode")
                self._mode_btn.setChecked(True)
                self._trading_stack.setCurrentIndex(1)
                # Flip the duplex — all stateful wing tabs.
                # v3.16.46 — Paper Trader tab removed; sentinel-None
                # check skips the flip safely when stack is absent.
                if getattr(self, "_paper_trader_stack", None) is not None:
                    self._paper_trader_stack.setCurrentIndex(1)
                    self._paper_trader = self._paper_trader_equity
                # Point aliases at the stock layer
                self._tab_widget = self._stock_tab_widget
                self._exchange_tabs = self._stock_exchange_tabs
                self._empty_placeholder = self._stock_placeholder
                self.setWindowTitle("Acervator — STOCK WING")
                self._status_log.log(
                    "→ STOCK WING: equity exchanges + equity Paper Trader. "
                    "(Crypto wing paused.)",
                    "info",
                )
            else:
                self._trading_mode = "crypto"
                self._mode_btn.setText("Crypto Mode")
                self._mode_btn.setChecked(False)
                self._trading_stack.setCurrentIndex(0)
                # v3.16.46 — Paper Trader tab removed; sentinel-None
                # check skips the flip safely when stack is absent.
                if getattr(self, "_paper_trader_stack", None) is not None:
                    self._paper_trader_stack.setCurrentIndex(0)
                    self._paper_trader = self._paper_trader_crypto
                # Point aliases at the crypto layer
                self._tab_widget = self._crypto_tab_widget
                self._exchange_tabs = self._crypto_exchange_tabs
                self._empty_placeholder = self._crypto_placeholder
                self.setWindowTitle("Acervator — CRYPTO WING")
                self._status_log.log(
                    "→ CRYPTO WING: crypto exchanges + crypto Paper Trader. "
                    "(Stock wing paused.)",
                    "info",
                )
            self._update_mode_btn_style()

            # 10.5 -- THE LEGACY ALIAS TRACKS THE VISIBLE LAYER.
            #
            # _tab_widget, _exchange_tabs and _empty_placeholder are
            # aliases repointed BY HAND in the two branches above.
            # Nothing binds them to the stack. A branch that flips
            # the stack and forgets an alias leaves the operator
            # looking at one layer while every caller of the alias
            # works on the other, and both sides return success.
            #
            # actual is the stack page that OWNS the alias widget,
            # found with indexOf on the widget's real parent.
            # expected is the page the stack really shows. The two
            # branches assign neither, so this cannot echo them.
            # The other two aliases ride in the context, checked by
            # identity against the layer stores.
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
            """Update mode button and layer tab headers to reflect the active layer.
            Tab widget tinting is skipped if the stack hasn't been built yet
            (safe to call early during _setup_ui before the trading stack exists).
            """
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
            # v3.16.20 — pass the current trading-mode wing so the
            # SettingsDialog filters its Exchanges tab to the
            # corresponding broker set (crypto vs stock). Operator
            # 2026-05-02: "Crypto and Stock Wings appear to be using
            # the same Settings screen" — pre-fix, the Stock Wing's
            # Add Exchange button opened a dialog listing CCXT crypto
            # exchanges, which is misleading.
            _wing = getattr(self, "_trading_mode", "crypto") or "crypto"
            self._status_log.log(
                f"Opening settings to add exchange " f"({_wing} wing)..."
            )
            from .settings_dialog import SettingsDialog

            dlg = SettingsDialog(self._settings, self._status_log, self, wing=_wing)
            dlg.exec()
            # Sync exchange tabs with settings after dialog closes
            self._sync_exchange_tabs()

        def _sync_exchange_tabs(self) -> None:
            """Create tabs for any exchanges in settings that don't have tabs yet.
            Routes each exchange to the correct layer (crypto or stock)
            regardless of which layer is currently visible.
            """
            if not self._settings:
                return
            _wanted: list[str] = []
            for exch in self._settings.list_exchanges():
                eid = exch.get("exchange_id", "")
                name = exch.get("display_name", eid.capitalize())
                if not eid:
                    continue
                # Collected HERE, from the read the loop already
                # made. A second list_exchanges() for the pin below
                # would be a second trip through stored exchange
                # records for instrumentation alone.
                _wanted.append(eid)
                # Route to correct layer dict
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

            # 10.5 -- EVERY CONFIGURED EXCHANGE REACHED A TAB BAR.
            #
            # The loop above adds a tab when the layer STORE lacks
            # the id, so the store agreeing with the settings is the
            # loop's own bookkeeping and proves nothing about what
            # the operator sees. This walks the configured ids again
            # and asks the LAYER TAB BAR whether it is really
            # holding that exchange's tab. A store entry whose
            # widget never reached the bar counts as missing.
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
                    "trading.12.003.postcondition" ".exchange_tabs_synced",
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

        def _refuse_extractor_without_parent(
            self,
            base_currency: str,
            exchange_id: str,
        ) -> bool:
            """Refuse this Extractor if nothing can parent it.

            Returns True when creation must stop. The caller returns on
            True and has already been told everything it needs; the
            operator has been shown the reason and the refusal is on
            both the activity log and the API record.

            This lives beside `_create_bot` rather than inside it
            because that function is already far past every size limit
            the checkers set, and a refusal that reports itself is a
            whole paragraph of reporting.

            The refusal is worded like the pre-flight refusal above it —
            a critical box the operator must dismiss, an error line in
            the activity log, and no bot — because it is the same kind
            of event: a check that ran before anything was built and
            said no.
            """
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
            """Say why an Extractor may not be created here, or nothing.

            THE REQUIREMENT (operator, 2026-08-10): "Given the design
            change of the Extractor bot as a sibling of the Scrumming
            Bot, it would seem logical to require a Scrumming Bot
            first."

            An Extractor works in one base currency and hands that
            currency back when it closes a position. It goes to the
            Scrumming Bot that HOLDS that currency, which raises its
            target balance to keep the gain. With no such bot the money
            has nowhere to go. Requiring the holder to exist BEFORE the
            Extractor is created removes that case by construction,
            instead of meeting it later with a live position open.

            REFUSED AT CREATION, TOLERATED AT RESTORE. This is the
            creation side and it refuses. The restore path in
            `BotManager.restore_bots_from_state` does NOT, deliberately:
            an Extractor whose parent was deleted after the fact still
            holds a real position, and refusing to load it would leave
            that position unmanaged. A rejected form costs nothing; a
            stranded position costs money.

            TWO REASONS, NEVER ONE. `find_parent_bot_for_base_currency`
            answers nothing both when NO bot holds the currency and when
            TWO OR MORE do -- it will not guess an owner. The remedies
            are opposite, so the two are never collapsed into one
            message: the first wants a Scrumming Bot created, the second
            wants one of several existing ones designated, which is the
            operator's call and not this window's.

            Returns the reason as operator-facing text, or None when
            creation may go ahead.
            """
            _asset = (base_currency or "").strip().upper() or "?"
            _venue = (exchange_id or "").strip() or "this exchange"
            manager = self._bot_manager
            if manager is None:
                # No roster means the requirement cannot be CHECKED, and
                # an unchecked requirement is not a met one. Refusing
                # costs a form; proceeding would create exactly the
                # parentless Extractor this exists to prevent.
                return (
                    f"The bot roster is not available, so it cannot be "
                    f"confirmed that a Scrumming Bot on {_venue} holds "
                    f"{_asset}.\n\n"
                    f"An Extractor hands its base currency back to the "
                    f"Scrumming Bot that holds it, so it may not be "
                    f"created until that bot is known to exist."
                )

            # The decision is the shipped lookup's, not this window's.
            # It is exchange-bound and refuses to guess between two
            # holders; both refusals arrive here as nothing.
            parent = manager.find_parent_bot_for_base_currency(
                base_currency, exchange_id=exchange_id
            )
            if parent is not None:
                return None

            # Only now, to EXPLAIN a refusal already decided, is the
            # roster counted. Same matching rules, one copy of them.
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
            """Open the Bot Creation Wizard.

            ``defaults_override`` (v3.23.69) merges into the settings-
            based defaults dict passed to the wizard, so callers (the
            topology-proposal Adopt handoff) can pre-fill fields such
            as ``default_target_balance``.
            """
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

                    # v3.13.8 MEM-185 / Chunk 1.5c — pre-flight symbol check.
                    # Verifies (exchange, symbol) is actually tradeable before
                    # committing to bot creation. Uses sync CCXT public-markets
                    # endpoint (no credentials required). On failure: block.
                    # On success with warnings: show + require operator ack.
                    try:
                        from .preflight_check import (
                            check_symbol,
                            format_result_for_user,
                        )

                        # v3.19.28 — Extractor is MULTI-PAIR by design.
                        # There is no canonical symbol to validate at
                        # creation time:
                        #   • Auto-scan mode: target pairs determined at
                        #     runtime via top-N by volume
                        #   • Manual mode: target pairs are a list, not
                        #     a single symbol — choosing one to validate
                        #     would be arbitrary
                        # The bot validates each watch-list symbol at
                        # runtime via _refresh_watch_list's exchange
                        # market scan (delisted pairs dropped with log).
                        # Skip the single-symbol preflight for Extractor;
                        # SCRUM/Grid still pre-validate as before.
                        # BOUND BEFORE THE BRANCH, ON PURPOSE. The two
                        # names below are read by the pre-flight FAILURE
                        # message further down. That message used to be
                        # reachable only through the else-branch that
                        # binds them, by way of the `_pf is not None`
                        # guard — a correlation held by convention, not
                        # by the language. If the Extractor branch ever
                        # produced a real result (a multi-pair pre-flight
                        # is the obvious next step), the FAILURE path
                        # would raise NameError and the operator would
                        # see a crash instead of the reason a live-money
                        # bot was refused. Pre-binding costs nothing and
                        # removes the case. The else-branch overwrites
                        # both with the real values before any check runs.
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
                        # v3.19.28 — Extractor skip path leaves _pf as None;
                        # guard the failure/warning branches accordingly.
                        if _pf is not None:
                            if not _pf.success:
                                QMessageBox.critical(
                                    self,
                                    "Pre-flight check failed",
                                    f"{_pf_text}\n\nBot creation aborted.",
                                )
                                self._status_log.log(
                                    f"Pre-flight FAILED for {_pf_symbol} on "
                                    f"{_pf_exchange}: {_pf.message}",
                                    "error",
                                )
                                return
                            if _pf.warnings:
                                _pf_reply = QMessageBox.question(
                                    self,
                                    "Pre-flight check — warnings",
                                    f"{_pf_text}\n\nProceed with bot creation?",
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No,
                                )
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
                        # CCXT not available or preflight_check module missing.
                        # Log and continue — bot creation not blocked by
                        # tooling gap, only by actual failure.
                        self._status_log.log(
                            "Pre-flight check skipped (module unavailable)", "warning"
                        )
                    except Exception as _pf_exc:
                        # Unexpected failure in the check itself; do not
                        # block bot creation — surface the issue and continue.
                        self._status_log.log(
                            f"Pre-flight check errored: {type(_pf_exc).__name__}: "
                            f"{_pf_exc} — continuing anyway",
                            "warning",
                        )

                    # v3.20.4 — two-way mode dispatch (grid removed
                    # v3.20.4; was already dead since v3.16.0).
                    # v3.19.20 — three-way mode dispatch closed the
                    # P0 ExtractorBot wizard bug surfaced 2026-05-22.
                    # Pre-v3.19.20 this line read `mode=BotMode.GRID
                    # if ... else BotMode.SCRUMMING` — Extractor
                    # selections in the wizard silently coerced to
                    # SCRUMMING (mode-drop) and the downstream factory
                    # hardcoded ScrummingBot (no ExtractorBot branch).
                    # The observed "2x target balance" was a
                    # side-effect: SCRUMMING-fallback used default
                    # target_balance=200 while Extractor
                    # chunk_size_usd defaulted to 100, yielding the
                    # canonical 2:1 ratio operator reported.
                    _mode_str = config.get("mode", "scrumming")
                    if _mode_str == "extractor":
                        _mode = BotMode.EXTRACTOR
                    else:
                        _mode = BotMode.SCRUMMING
                    # v3.20.32 — mode-aware defaults for the
                    # overloaded fields (audit P3 fix). target_asset
                    # default of "BTC" silently re-introduced the
                    # ScrummingBot-shaped output bug on Extractor
                    # configs if the wizard dict ever omits the key
                    # (operator-reported 2026-05-25). Use mode-
                    # specific defaults instead:
                    #   - Extractor: target_asset = "*" (pool sigil)
                    #   - Scrumming: target_asset = "BTC" (historical
                    #     default for missing-key fallback)
                    # base_currency default of "USDT" was historically
                    # a Scrumming-leaning value; v3.19.28+ Extractors
                    # use USDC/ETH as canonical pool bases. Keep
                    # "USDT" for back-compat but the operator's
                    # canonical Extractor workflow always supplies
                    # base_currency from the ExtractorPoolPage —
                    # the default is only a fallback.
                    # v3.20.34 — migrate to make_bot_config typed
                    # factory (introduced v3.20.33). The factory
                    # enforces mode-shape at construction time:
                    # mode-foreign kwargs (Scrumming-only on
                    # Extractor or vice versa) raise ValueError.
                    # This eliminates the operator-reported
                    # 2026-05-25 bug class structurally — bad
                    # configs can't be constructed in the first
                    # place. Construction is now in three layers:
                    #   1) shared kwargs (passed for both modes)
                    #   2) mode-specific kwargs (only the matching
                    #      block reaches the factory)
                    #   3) factory call with **shared, **mode_specific
                    from ..trading.bot_container import make_bot_config

                    _ta_default = "*" if _mode == BotMode.EXTRACTOR else "BTC"

                    # Shared kwargs — always passed.
                    _shared_kwargs = {
                        "exchange_id": config.get("exchange_id", exchange_id),
                        "base_currency": config.get("base_currency", "USDT"),
                        "target_asset": config.get("target_asset", _ta_default),
                        # MEM-244 risk controls — shared on the dataclass
                        # but manifest-grouped as SCRUMMING_ONLY since
                        # Extractor doesn't consume them. Skip in
                        # _scrum_kwargs (factory enforces).
                        "target_balance": config.get(
                            "target_balance",
                            (
                                config.get("extractor_chunk_size_usd", 200.0)
                                if _mode == BotMode.EXTRACTOR
                                else 200.0
                            ),
                        ),
                        "ta_timeframe": config.get("ta_timeframe", "1h"),
                        "visibility": config.get("visibility", "orderbook"),
                        "aggressive_trading": config.get("aggressive_trading", False),
                        # v3.23.25 — Stack Mode (renamed from
                        # bulk_trading). See bot_container.py:
                        # _sanitize_deprecated_kwargs for the
                        # older-bot_state.json compatibility path.
                        "stack_mode": config.get(
                            "stack_mode", config.get("bulk_trading", False)
                        ),
                        "split_distance": config.get("split_distance", 1.0),
                        "stack_tranche_count_target": config.get(
                            "stack_tranche_count_target", 3
                        ),
                        "stack_spacing_mode": config.get(
                            "stack_spacing_mode", "linear"
                        ),
                        # v3.23.25 bulk_partial_on_return retired
                    }

                    if _mode == BotMode.SCRUMMING:
                        _mode_kwargs = {
                            # v3.23.21 — position_count + position_distance_pct
                            # removed here to match v3.23.3 R-CLN Phase 1 grid-
                            # bot dead-code excision from BotConfig dataclass
                            # (bot_container.py). Emitting them here caused
                            # operator-visible "Bot creation REJECTED — mode-
                            # shape violation: BotConfig.__init__() got an
                            # unexpected keyword argument 'position_count'"
                            # in v3.23.20.
                            "investment_amount": config.get("investment_amount", 200.0),
                            "increment_style": config.get("increment_style", "linear"),
                            # v3.23.25 market_check_interval kwarg removed
                            "max_target_growth_pct": config.get(
                                "max_target_growth_pct", 1.0
                            ),
                            "scrumming_interval_pct": config.get(
                                "scrumming_interval_pct", 1.0
                            ),
                            "profit_folding_active": config.get(
                                "profit_folding_active", True
                            ),
                            "bb_tolerance_pct": config.get("bb_tolerance_pct", 1.0),
                            "bb_landing_strip_candles": config.get(
                                "bb_landing_strip_candles", 3
                            ),
                            "scrum_detect_pct": config.get("scrum_detect_pct", 75),
                            "scrum_fire_pct": config.get("scrum_fire_pct", 0.5),
                            "bb_midline_gate": config.get("bb_midline_gate", True),
                            "scrum_read_rate_min": config.get("scrum_read_rate_min", 5),
                            "band_travel_pct": config.get("band_travel_pct", 70),
                            "bb_bullseye_check": config.get("bb_bullseye_check", True),
                            "hedge_rebalance_active": config.get(
                                "hedge_rebalance_active", True
                            ),
                            "hedge_balance": config.get("hedge_balance", 200.0),
                        }
                    else:  # BotMode.EXTRACTOR
                        _mode_kwargs = {
                            "extractor_chunk_size_usd": config.get(
                                "extractor_chunk_size_usd", 100.0
                            ),
                            "extractor_artillery_size_usd": config.get(
                                "extractor_artillery_size_usd", 5.0
                            ),
                            "extractor_scan_top_n": config.get(
                                "extractor_scan_top_n", 8
                            ),
                            "extractor_scan_refresh_candles": config.get(
                                "extractor_scan_refresh_candles", 60
                            ),
                            "extractor_pool_reserve_pct": config.get(
                                "extractor_pool_reserve_pct", 50.0
                            ),
                            "extractor_exit_pct": config.get(
                                "extractor_exit_pct", 100.0
                            ),
                            "extractor_max_compounding_tier": config.get(
                                "extractor_max_compounding_tier", 3
                            ),
                            "extractor_max_cost_basis_multiple": config.get(
                                "extractor_max_cost_basis_multiple", 2.0
                            ),
                            "extractor_alt_targets": list(
                                config.get("extractor_alt_targets", []) or []
                            ),
                        }

                    try:
                        bot_config = make_bot_config(
                            _mode, **_shared_kwargs, **_mode_kwargs
                        )
                    except (ValueError, TypeError) as _bc_err:
                        # Factory rejected — this is OPERATOR-VISIBLE.
                        # Better to fail loudly at construction than
                        # to let a malformed config reach the runtime.
                        msg = (
                            f"Bot creation REJECTED — mode-shape "
                            f"violation: {_bc_err}"
                        )
                        self._status_log.log(msg, "error")
                        self._spool.notify(msg, "error")
                        logger.error("Bot creation rejected: %s", _bc_err)
                        return

                    # v3.20.32 → v3.20.34 — validate_mode_shape() is
                    # now called BY THE FACTORY (raises on violation).
                    # The legacy warning-only path below is preserved
                    # for stale persisted configs that bypass the
                    # factory (loaded by restore_bots_from_state, not
                    # created via this site). New configs reaching
                    # this point are factory-validated; the call is
                    # a defense-in-depth no-op.
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

                    # STANDING QUEUE ITEM 3 (operator, 2026-08-10) — a
                    # Scrumming Bot holding the base currency must exist
                    # BEFORE its Extractor sibling does. Checked here,
                    # which is after the config is shaped and BEFORE the
                    # bot is constructed or registered: nothing has been
                    # written yet, so a refusal leaves no trace to undo.
                    # See _extractor_parent_refusal for why the restore
                    # path deliberately does NOT do this.
                    if (
                        bot_config.mode == BotMode.EXTRACTOR
                        and self._refuse_extractor_without_parent(
                            bot_config.base_currency, bot_config.exchange_id
                        )
                    ):
                        return

                    # v3.20.4 — grid legacy migration warning removed
                    # (BotMode.GRID dropped from the enum). v3.19.20
                    # introduced the three-way factory dispatch that
                    # closed the silent-mutation P0; with grid gone
                    # it reduces to two-way.
                    from ..trading.scrumming_bot import ScrummingBot

                    if bot_config.mode == BotMode.EXTRACTOR:
                        from ..trading.extractor_bot import ExtractorBot

                        bot = ExtractorBot(
                            bot_config,
                            _PlaceholderExchange(bot_config.exchange_id),
                            enable_phantoms=False,  # Extractor never uses phantoms
                        )
                    else:
                        bot = ScrummingBot(
                            bot_config,
                            _PlaceholderExchange(bot_config.exchange_id),
                            enable_phantoms=config.get("enable_phantoms", False),
                            phantom_timeframes=config.get("phantom_timeframes", []),
                        )

                    if self._bot_manager:
                        # v3.20.71 Phase B-2 — register() returns
                        # (granted, reason); refused on over-allocation.
                        # Locked Q3: refuse outright, no warn-and-confirm.
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

                    # Force indicator panel to show this bot immediately
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

        def _switch_theme(self, name: str) -> None:
            from .theme_engine import ThemeManager

            tm = ThemeManager()
            app = self.parent()
            if app is None:
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
            if app:
                tm.apply_theme(name, app)
                self._status_log.log(f"Theme switched to {name}.", "info")

        def _show_about(self) -> None:
            QMessageBox.about(
                self,
                "About Acervator",
                "Acervator v1.7\n\n"
                "A multi-exchange crypto auto-trading platform.\n"
                "Grid Mode - Speculative Scrumming\n"
                "Profit Folding - Upward Distribution\n"
                "Phantom Balance Bots - 7-Indicator TA Voting\n"
                "TradingView Charts - Multi-Timeframe Analysis\n"
                "Verbose API Interaction Logging",
            )
