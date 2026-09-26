"""The Paper tab in Qt: Live's tab body, forked under the Paper Trader's name.

``PaperTradingTab`` is ``TradingTabMixin._build_trading_tab`` from
``src/gui/main_tabs/trading_tab.py`` as a widget of its own: the exchange layer
stack, the forked ``PaperIndicatorVotingPanel``, and the Activity Log and API
Interaction Log spools, in Live's four splitters at Live's sizes; the corner
Live gives ``＋ Add Crypto Exchange`` holds ``tab_surface.corner_buttons`` —
Add Exchange, Import Live Fleet and Start Paper Run at Live's corner-button
width — and the Get Started card holds the same three, each reaching
``_way_in``. Add Exchange reads its text, its tooltip and whether it can act
from ``asset_class_surface`` over the active asset class, ``set_asset_class``
relabels it through ``_retitle_add_exchange``, and its press seats a venue of
that class through ``_add_exchange``; a class no venue serves draws its note
and seats nothing. ``add_exchange_tab`` is the window's method of that name, forked,
and seats a ``PaperExchangeTab``; ``_sync_exchange_tabs`` seats one per
exchange ``PaperFleetSource.exchanges`` names, at build and on every
``fleet_changed``, drops the rest as the window's ``_drop_unlisted_exchange_tabs``
does, and then ``refresh_bots`` hands each venue its rows from
``PaperFleetSource.statuses`` and ``refresh_votes`` hands the panel the fleet,
its own rates and the selected bot's ``ivp_feed``; every ``fleet_changed``
first writes the paper fleet file through ``PaperFleetSource.save``.
``_start_paper_run`` is the Simulator's ``_start_run`` forked: Start Paper
Run opens ``paper_run.start`` over the held fleet under ``run_rule`` and
starts one ``PaperRunner`` on the ``RUN_THREAD_NAME`` thread, which ticks
every record whose state reads ``running`` over ``exchange()``; while it
runs the run button reads ``STOP_RUN_TEXT`` and its press reaches
``_stop_paper_run``, the fork of ``_stop_run``, and ``_take_paper_run`` on
``run_finished`` writes ``run_ended_line`` and relabels the button; each
fill crosses on ``run_trade``, each runner line on ``run_line`` and the
ledger's figures on ``run_figures`` to ``_take_figures``, so ``aggregate``
reads a snapshot and never the runner's balances. Each ``BotStatsSnapshot``
crosses on ``bot_stats`` to ``_take_bot_stats``, which writes the held record
through ``PaperFleetSource.write_stats`` and arms ``_stats_redraw_timer`` at
``STATS_REDRAW_MS``, so the row's Trades, Current Position Value and Target
follow a fill; a ``running`` or ``stopped`` mark moves the record through
``PaperBotManager`` and redraws at once.
``_import_live_fleet`` puts ``exchange_choice`` over
``PaperFleetSource.stored_exchanges``, opens ``PaperExchangeChoiceDialog`` when
it prompts, copies the chosen exchange's records through
``PaperFleetSource.import_live_fleet`` and fires ``fleet_changed``. A venue's
``+ New Bot`` reaches ``_create_bot``, which writes ``new_bot_line``; the
command bar's Start, Pause, Stop, Restart and Delete reach ``_on_bot_command``,
the window's handler forked over ``PaperBotManager`` with no venue connect; a
row's Detail reaches ``_on_bot_detail``, which opens the Paper Trader's Bot
Settings window through ``surface_class(PAPER_BOT_DETAIL)`` over a
``PaperBotView``; a row's Fire reaches ``_on_bot_fire``, which logs the
``SendRefused`` ``PaperFleetSource`` raises. ``aggregate`` is
``strip_aggregate`` over the held records and ``PaperLedger.figures``, what the
header strip reads while Paper is in front. The API Interaction Log is written
by ``_on_api_event``, the window's writer forked over the tab's own
``APIInteractionLog``, never the process-wide ``get_api_log``; every entry
reaches it through ``_cross_api_event`` and ``apiEntryLogged``, the window's
crossing, so a read on a worker thread lands on the GUI thread. The tab holds
one ``PaperExchange`` over that log, and ``_read_feed`` runs ``read_fleet``
over it on a worker thread after each Import Live Fleet, one products read and
one ticker read per record, whose summary ``feedRead`` carries to
``_on_feed_read`` and one ``feed_line`` on the Activity Log.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.sound_engine import get_sound_engine
from ...exchange.api_logger import APIInteractionLog
from ...paper import paper_run
from ...paper.fake_balance import PaperLedger
from ...paper.fleet_source import (
    PaperFleetSource,
    SendRefused,
    exchange_choice,
    strip_aggregate,
)
from ...paper.paper_bot_manager import PaperBotManager
from ...paper.paper_bot_view import PaperBotView
from ...paper.paper_exchange import PaperExchange, read_fleet
from ...paper.paper_run import PaperRun, PaperRunner, PaperTrade
from .. import design_system as ds
from ..color_alpha import rgba
from ..main_tabs import asset_class_surface as acs
from ..main_tabs import class_filter_surface
from ..main_tabs.exchange_tab_surface import FLEET_COMMANDS
from ..main_tabs.header_strip import HeaderStripMixin
from ..main_tabs.trading_tab_surface import (
    BOTTOM_SPLITTER_SIZES_PX,
    LOG_SPLITTER_SIZES_PX,
    MAIN_SPLITTER_SIZES_PX,
    PLACEHOLDER_TAB_TITLE,
    TOP_SPLITTER_SIZES_PX,
    WATCHDOG_INTERVAL_MS,
    WATCHDOG_STAT_FAILURE_FORMAT,
    WatchdogState,
    exchange_display_name,
)
from ..variant_surface import PAPER_BOT_DETAIL, surface_class
from ..widgets.bot_selection import BotListPanelLink
from . import paper_trading_tab_surface as tab_surface
from .paper_bot_status_table_surface import usd_rates
from .paper_exchange_choice import PaperExchangeChoiceDialog
from .paper_exchange_tab import PaperExchangeTab
from .paper_indicator_panel import PaperIndicatorVotingPanel
from .paper_status_log import PaperStatusLog
from .paper_trading_tab_surface import (
    notification_line,
    placeholder_hint_text,
    placeholder_title_text,
)

logger = logging.getLogger("acervator.gui")

PLACEHOLDER_CARD_BORDER_ALPHA = 68

ACCESSIBLE_NAME = "Paper"

#: The four all-bots verbs a SHIFT press on the command bar may name.
FLEET_VERBS = tuple(pair[1] for pair in FLEET_COMMANDS.values())


class PaperTradingTab(QWidget):
    """The Paper tab: Live's tab body over the Paper Trader's fleet source."""

    #: Fired by whatever loads a fleet; the venue sub-tabs re-seat on it.
    fleet_changed = Signal()
    #: One ``APIInteractionLog`` entry, queued onto the GUI thread for ``_on_api_event``.
    apiEntryLogged = Signal(object)  # noqa: N815 - Qt signal name
    #: One ``read_fleet`` summary, queued onto the GUI thread for ``_on_feed_read``.
    feedRead = Signal(object)  # noqa: N815 - Qt signal name
    #: One runner line and its level, queued onto the GUI thread.
    run_line = Signal(str, str)
    #: One ``PaperTrade``, queued onto the GUI thread for ``_take_trade``.
    run_trade = Signal(object)
    #: The ``PaperRun`` the runner ended with, queued for ``_take_paper_run``.
    run_finished = Signal(object)
    #: The ledger's figures after a worked pass, queued for ``_take_figures``.
    run_figures = Signal(object)
    #: One ``BotStatsSnapshot``, queued off the runner's thread so
    #: ``_take_bot_stats`` writes the held record on the GUI thread.
    bot_stats = Signal(object)

    def __init__(
        self,
        fleet_source: Optional[PaperFleetSource] = None,
        parent: Optional[QWidget] = None,
        api_log: Optional[APIInteractionLog] = None,
        exchange: Optional[PaperExchange] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(ACCESSIBLE_NAME)
        self.setAccessibleName(ACCESSIBLE_NAME)
        self._fleet_source = (
            fleet_source if fleet_source is not None else PaperFleetSource()
        )
        self._api_log = api_log if api_log is not None else APIInteractionLog()
        self._exchange = (
            exchange if exchange is not None else PaperExchange(api_log=self._api_log)
        )
        self._bot_manager = PaperBotManager(self._fleet_source)
        self._asset_class = class_filter_surface.active()
        self._ledger = PaperLedger()
        self._figures: dict = {}
        self._states: dict = {}
        self._runner: Optional[PaperRunner] = None
        self._fills: list[PaperTrade] = []
        self._corner_buttons: dict[str, QPushButton] = {}
        self._card_buttons: dict[str, QPushButton] = {}
        self._run_buttons: list[QPushButton] = []
        self._add_exchange_buttons: list[QPushButton] = []
        self._stats_redraw_timer = QTimer(self)
        self._stats_redraw_timer.setSingleShot(True)
        self._stats_redraw_timer.setInterval(tab_surface.STATS_REDRAW_MS)
        self._stats_redraw_timer.timeout.connect(self._redraw_stats)
        self._build()
        self.run_line.connect(self._status_log.log)
        self.run_trade.connect(self._take_trade)
        self.run_finished.connect(self._take_paper_run)
        self.run_figures.connect(self._take_figures)
        self.bot_stats.connect(self._take_bot_stats)
        self.apiEntryLogged.connect(self._on_api_event)
        self._api_log.add_listener(self._cross_api_event)
        self.feedRead.connect(self._on_feed_read)
        self._indicator_panel.bot_selected.connect(self._feed_votes)
        self._bot_list_link = BotListPanelLink(
            self._indicator_panel, self._bot_list_hosts
        )
        self._indicator_panel.bot_selected.connect(self._bot_list_link.panel_moved)
        self.fleet_changed.connect(self._fleet_source.save)
        self.fleet_changed.connect(self._sync_exchange_tabs)
        self._sync_exchange_tabs()

    # -- what the window reads ------------------------------------------

    def fleet_source(self) -> PaperFleetSource:
        """The fleet reader the tables are fed from."""
        return self._fleet_source

    def bot_manager(self) -> PaperBotManager:
        """The forked bot manager the command bar moves records through."""
        return self._bot_manager

    def ledger(self) -> PaperLedger:
        """The paper ledger the strip's four money figures read."""
        return self._ledger

    def aggregate(self) -> dict:
        """The header strip's figures, ``strip_aggregate`` over the held fleet
        and the ledger figures the runner last posted through ``run_figures``."""
        return strip_aggregate(self._fleet_source.bots(), self._figures)

    def figures(self) -> dict:
        """The ledger figures the runner last posted, empty before a run."""
        return dict(self._figures)

    def runner(self) -> Optional[PaperRunner]:
        """The ``PaperRunner`` of the run in flight or last finished, or None."""
        return self._runner

    def run(self) -> Optional[PaperRun]:
        """The ``PaperRun`` in flight or last finished, or None before one."""
        return self._runner.run if self._runner is not None else None

    def run_running(self) -> bool:
        """True while the ``RUN_THREAD_NAME`` worker thread is alive."""
        return self._runner is not None and self._runner.running()

    def fills(self) -> list[PaperTrade]:
        """Every ``PaperTrade`` the run in flight or last finished handed
        ``run_trade``, in fill order; empty before the first run."""
        return list(self._fills)

    def api_log(self) -> APIInteractionLog:
        """The tab's own API log; every entry it records reaches the pane."""
        return self._api_log

    def exchange(self) -> PaperExchange:
        """The tab's ``PaperExchange``, recording every venue call on ``api_log``."""
        return self._exchange

    def exchange_count(self) -> int:
        """How many venue sub-tabs ``add_exchange_tab`` has seated; EXCH reads it."""
        return len(self._exchange_tabs)

    def _bot_list_hosts(self) -> list:
        """Every venue sub-tab that draws a bot list, both layers together."""
        return list(self._crypto_exchange_tabs.values()) + list(
            self._stock_exchange_tabs.values()
        )

    def _on_bot_row_selected(self, bot_id: str) -> str:
        """Draw the pressed bot on the Paper Trader's own Voting Panel.

        Every venue sub-tab calls this, so the tab does not wait for its next
        refresh to show what the operator just pressed.
        """
        return self._bot_list_link.row_selected(bot_id)

    def corner_buttons(self) -> dict[str, QPushButton]:
        """The crypto layer's corner buttons, keyed by action."""
        return dict(self._corner_buttons)

    def card_buttons(self) -> dict[str, QPushButton]:
        """The crypto layer's Get Started card buttons, keyed by action."""
        return dict(self._card_buttons)

    # -- the ways in ------------------------------------------------------

    def _way_in(self, action: str) -> None:
        """Run the corner or card press ``action``: ``_add_exchange`` for Add
        Exchange, ``_import_live_fleet`` for Import Live Fleet,
        ``_start_paper_run`` for Start Paper Run with no run up,
        ``_stop_paper_run`` for the same seat while one is up."""
        if action == tab_surface.ADD_EXCHANGE_ACTION:
            self._add_exchange()
            return
        if action == tab_surface.IMPORT_LIVE_FLEET_ACTION:
            self._import_live_fleet()
            return
        if action in (tab_surface.START_RUN_ACTION, tab_surface.STOP_RUN_ACTION):
            if self.run_running():
                self._stop_paper_run()
            elif action == tab_surface.START_RUN_ACTION:
                self._start_paper_run()
            return
        self._status_log.log(f"{action} is not a way in.", "error")

    def _start_paper_run(self) -> None:
        """Start Paper Run: ``paper_run.start`` over the held fleet under
        ``run_rule`` of ``exchange().venue()``, one ``PaperRunner`` on the
        ``RUN_THREAD_NAME`` thread reading ``_states``, the started line,
        and the run button relabelled Stop; a fleet holding no record or a
        venue with no cited rule writes one line and starts nothing."""
        bots = self._fleet_source.bots()
        if not bots:
            self._status_log.log(tab_surface.RUN_NO_BOT_TEXT, "warning")
            return
        venue = self._exchange.venue()
        rule = paper_run.run_rule(venue)
        if rule is None:
            self._status_log.log(tab_surface.run_no_rule_line(venue), "warning")
            return
        run = paper_run.start(bots, rule)
        self._ledger = run.ledger
        self._figures = run.figures()
        self._fills = []
        self._refresh_states()
        self._runner = PaperRunner(
            run,
            self._exchange,
            self._read_states,
            on_trade=self.run_trade.emit,
            on_figures=self.run_figures.emit,
            on_finished=self.run_finished.emit,
            on_stats=self.bot_stats.emit,
            say=lambda line: self.run_line.emit(line, "info"),
        )
        self._runner.start()
        self._status_log.log(
            tab_surface.run_started_line(
                len(bots),
                len(tab_surface.running_bot_ids(bots)),
                run.ledger.fleet_target_usd,
            ),
            "success",
        )
        self._relabel_run_buttons(True)

    def _stop_paper_run(self) -> None:
        """Stop Paper Run: ``RUN_STOPPING_TEXT`` and the event the runner
        reads before each tick; ``run_finished`` follows from the thread."""
        self._status_log.log(tab_surface.RUN_STOPPING_TEXT, "warning")
        if self._runner is not None:
            self._runner.stop()

    def _take_paper_run(self, run: PaperRun) -> None:
        """The runner's end on the GUI thread: the final figures held,
        ``run_ended_line`` written and the run button relabelled Start."""
        self._figures = run.figures()
        self._status_log.log(tab_surface.run_ended_line(run), "info")
        self._relabel_run_buttons(False)

    def _take_figures(self, figures: dict) -> None:
        """Hold the ledger figures the runner posted, what ``aggregate`` reads."""
        self._figures = dict(figures or {})

    # One sentence of the docstring below is overtaken. Quoted whole:
    #   "Hold one fill the runner posted, in fill order."
    # The fill also writes ``fill_line`` through ``log_at`` at ``fill_stamp``.
    def _take_trade(self, trade: PaperTrade) -> None:
        """Hold one fill the runner posted, in fill order."""
        self._fills.append(trade)
        self._status_log.log_at(
            tab_surface.fill_stamp(trade),
            tab_surface.fill_line(trade),
            tab_surface.FILL_LINE_LEVEL,
            tab_surface.FILL_LINE_KIND,
        )

    def _take_bot_stats(self, snapshot: Any) -> None:
        """Write one ``BotStatsSnapshot`` into the held record through
        ``PaperFleetSource.write_stats`` on the GUI thread.

        A ``running`` mark moves the bot through ``PaperBotManager.start`` with
        Live's RUNNING line and redraws the rows at once, a ``stopped`` mark
        moves it through ``PaperBotManager.stop`` with the run's ended line and
        redraws at once, and every other snapshot arms ``_stats_redraw_timer``
        so the rows redraw once per ``STATS_REDRAW_MS``. A snapshot for a
        record no longer held is dropped.
        """
        bot_id = str(getattr(snapshot, "bot_id", ""))
        try:
            self._fleet_source.write_stats(
                bot_id, snapshot.stats, snapshot.scrumming_state
            )
            if snapshot.state == paper_run.RUNNING_STATE:
                self._bot_manager.start(bot_id)
                self._status_log.log(tab_surface.bot_running_line(bot_id), "success")
                self._status_log.log(tab_surface.bot_opened_line(snapshot), "info")
                self._redraw_stats()
                return
            if snapshot.state == paper_run.STOPPED_STATE:
                self._bot_manager.stop(bot_id)
                self._status_log.log(tab_surface.bot_stopped_line(bot_id), "info")
                self._status_log.log(tab_surface.bot_ended_line(snapshot), "info")
                self._redraw_stats()
                return
        except KeyError:
            logger.debug("paper stats for %s dropped: no record held", bot_id)
            return
        if not self._stats_redraw_timer.isActive():
            self._stats_redraw_timer.start()

    def _redraw_stats(self) -> None:
        """Redraw every venue's rows through ``refresh_bots``, refresh the
        state map the runner reads; the header strip
        reads the same records on the window's own tick."""
        self._stats_redraw_timer.stop()
        self._refresh_states()
        self.refresh_bots()

    def _read_states(self) -> dict:
        """The state per held ``bot_id`` as of the last ``_refresh_states``,
        the map the runner reads on its own thread."""
        return self._states

    def _refresh_states(self) -> dict:
        """Rebuild ``_states`` from ``PaperBotManager.bots`` on the GUI thread."""
        self._states = {bot.bot_id: bot.state for bot in self._bot_manager.bots()}
        return self._states

    def _relabel_run_buttons(self, running: bool) -> None:
        """Give every run button the face ``run_buttons`` names for ``running``:
        its text and its accessible name."""
        action, text = tab_surface.run_buttons(running)[1]
        for button in self._run_buttons:
            button.setText(text)
            card = button.accessibleName().endswith("-card")
            button.setAccessibleName(
                tab_surface.card_button_name(action)
                if card
                else tab_surface.button_name(action)
            )

    def _add_exchange(self) -> None:
        """Add Exchange: seat a venue of the active asset class.

        A class ``asset_class_surface`` reports unserved writes its note and
        seats nothing, as Live's own Add Exchange refuses; otherwise the
        stored venues narrowed to that class are offered and the one chosen
        is imported, which seats its sub-tab.
        """
        key = acs.normalise(self._asset_class)
        if not acs.add_exchange_enabled(key):
            self._status_log.log(acs.class_state(key)["note"], "warning")
            return
        self._import_live_fleet(key)

    def _import_live_fleet(self, asset_class: Any = None) -> None:
        """Import Live Fleet: ``exchange_choice`` over the exchanges
        ``PaperFleetSource.stored_exchanges`` names, ``PaperExchangeChoiceDialog``
        when it prompts, then ``PaperFleetSource.import_live_fleet`` on the
        exchange chosen, one Activity Log line and ``fleet_changed``.

        ``asset_class`` narrows the options to the venues serving that class.
        """
        options = self._fleet_source.stored_exchanges()
        if asset_class is not None:
            narrowed = class_filter_surface.venues_of_class(options, asset_class)
            if options and not narrowed:
                self._status_log.log(
                    tab_surface.no_class_venue_line(asset_class), "warning"
                )
                return
            options = narrowed
        if not options:
            self._status_log.log(tab_surface.no_stored_bot_line(), "warning")
            return
        choice = exchange_choice(options)
        chosen = choice["chosen"]
        if choice["prompt"]:
            dialog = PaperExchangeChoiceDialog(options, self)
            if dialog.exec() != QDialog.Accepted:
                self._status_log.log(tab_surface.IMPORT_CANCELLED_TEXT, "warning")
                return
            chosen = dialog.chosen()
        imported = self._fleet_source.import_live_fleet(chosen)
        self._status_log.log(
            tab_surface.imported_line(len(imported), chosen), "success"
        )
        self.fleet_changed.emit()
        self._read_feed([bot.symbol for bot in imported])

    def _read_feed(self, symbols: list) -> None:
        """Run ``read_fleet`` over ``exchange()`` for ``symbols`` on one
        ``FEED_THREAD_NAME`` worker thread; its summary crosses ``feedRead``."""
        if not symbols:
            return

        def run() -> None:
            summary = read_fleet(self._exchange, symbols)
            try:
                self.feedRead.emit(summary)
            except RuntimeError:
                # The host was deleted while the reads ran; nothing draws the line.
                return

        threading.Thread(
            target=run, name=tab_surface.FEED_THREAD_NAME, daemon=True
        ).start()

    def _on_feed_read(self, summary: dict) -> None:
        """Write one ``feed_line`` for ``summary`` on the Activity Log."""
        text, level = tab_surface.feed_line(summary)
        self._status_log.log(text, level)

    # -- construction -----------------------------------------------------

    def _build(self) -> None:
        trading_layout = QVBoxLayout(self)
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

        # ── QStackedWidget: page 0 = Crypto, page 1 = Stock ────────
        self._trading_stack = QStackedWidget()

        def _make_layer(label_text: str, accent: str) -> tuple:
            """Build one trading layer — returns (page_widget, tab_widget,
            exchange_tabs_dict, placeholder_widget)."""
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)

            tab_w = QTabWidget()
            # The corner Live gives its add button holds Add Exchange and the
            # two ways in, each seat read from tab_surface.corner_buttons.
            corner = QWidget()
            corner_row = QHBoxLayout(corner)
            corner_row.setContentsMargins(0, 0, 0, 0)
            corner_row.setSpacing(2)
            for seat in tab_surface.corner_buttons(False, self._asset_class):
                action = seat["action"]
                way_btn = QPushButton(seat["text"])
                way_btn.setMinimumWidth(seat["minimum_width_px"])
                way_btn.setAccessibleName(seat["accessible_name"])
                way_btn.setToolTip(seat.get("tooltip", ""))
                way_btn.setEnabled(bool(seat.get("enabled", True)))
                way_btn.clicked.connect(
                    lambda _checked=False, key=action: self._way_in(key)
                )
                corner_row.addWidget(way_btn)
                if label_text == "Crypto":
                    self._corner_buttons[action] = way_btn
                if action == tab_surface.START_RUN_ACTION:
                    self._run_buttons.append(way_btn)
                if action == tab_surface.ADD_EXCHANGE_ACTION:
                    self._add_exchange_buttons.append(way_btn)
            tab_w.setCornerWidget(corner)

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
            # The card's button position holds Add Exchange and the two ways
            # in, each seat read from tab_surface.placeholder_way_in_buttons.
            for seat in tab_surface.placeholder_way_in_buttons(
                accent, False, self._asset_class
            ):
                action = seat["action"]
                ph_add = QPushButton(seat["text"])
                ph_add.setMinimumSize(*seat["minimum_size_px"])
                ph_add.setStyleSheet(seat["style_sheet"])
                ph_add.setAccessibleName(seat["accessible_name"])
                ph_add.setToolTip(seat.get("tooltip", ""))
                ph_add.setEnabled(bool(seat.get("enabled", True)))
                ph_add.clicked.connect(
                    lambda _checked=False, key=action: self._way_in(key)
                )
                ph_layout.addWidget(ph_add, alignment=Qt.AlignCenter)
                if label_text == "Crypto":
                    self._card_buttons[action] = ph_add
                if action == tab_surface.START_RUN_ACTION:
                    self._run_buttons.append(ph_add)
                if action == tab_surface.ADD_EXCHANGE_ACTION:
                    self._add_exchange_buttons.append(ph_add)
            ph_hint = QLabel(placeholder_hint_text(label_text))
            ph_hint.setStyleSheet(
                f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; border: none;"
            )
            ph_hint.setAlignment(Qt.AlignCenter)
            ph_layout.addWidget(ph_hint)
            ph_outer.addWidget(ph_card, alignment=Qt.AlignCenter)
            tab_w.addTab(placeholder, PLACEHOLDER_TAB_TITLE)

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
        self._tab_widget = self._crypto_tab_widget
        self._exchange_tabs = self._crypto_exchange_tabs
        self._empty_placeholder = self._crypto_placeholder

        top_splitter.addWidget(self._trading_stack)

        # Right panel: the forked voting panel
        self._indicator_panel = PaperIndicatorVotingPanel()
        self._chart = None  # No chart in trading tab
        top_splitter.addWidget(self._indicator_panel)

        top_splitter.setSizes(list(TOP_SPLITTER_SIZES_PX))

        main_splitter.addWidget(top_splitter)

        # Bottom section: spool + two symmetrical log panels
        bottom_splitter = QSplitter(Qt.Vertical)
        bottom_splitter.setHandleWidth(5)
        bottom_splitter.setChildrenCollapsible(False)

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

        self._activity_pause_btn.toggled.connect(_on_activity_pause_toggled)
        activity_header_row.addWidget(self._activity_pause_btn)
        activity_layout.addLayout(activity_header_row)
        self._status_log = PaperStatusLog()
        self._status_log.setMaximumHeight(16777215)  # Remove height limit
        activity_layout.addWidget(self._status_log)
        log_splitter.addWidget(activity_widget)

        # Polls PaperStatusLog.health_stats() every 60s on the GUI thread.
        self._activity_log_watchdog_state = WatchdogState()
        self._activity_log_watchdog_timer = QTimer(self)
        self._activity_log_watchdog_timer.timeout.connect(self._activity_log_watchdog)
        self._activity_log_watchdog_timer.start(WATCHDOG_INTERVAL_MS)

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
        # _on_api_event reads this flag; QPlainTextEdit has no PaperStatusLog subclass.
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

        tab = PaperExchangeTab(
            exchange_id,
            display_name,
            on_new_bot=self._create_bot,
            on_bot_clicked=self._on_bot_detail,
            on_bot_cmd=self._on_bot_command,
            on_fleet_cmd=self._global_bot_cmd,
            on_bot_fire=self._on_bot_fire,
            status_log=self._status_log,
            on_bot_selected=self._on_bot_row_selected,
        )
        target_widget.addTab(tab, display_name)
        target_tabs[exchange_id] = tab

        if target_tabs is self._exchange_tabs:
            self._exchange_tabs[exchange_id] = tab

    def _drop_unlisted_exchange_tabs(self, listed: list) -> int:
        """Take off every venue sub-tab whose id is not in ``listed``; the
        layer's Get Started page is added back once its bar empties."""
        kept = set(listed)
        dropped = 0
        layers = (
            (
                self._crypto_exchange_tabs,
                self._crypto_tab_widget,
                "_crypto_placeholder",
            ),
            (
                self._stock_exchange_tabs,
                self._stock_tab_widget,
                "_stock_placeholder",
            ),
        )
        for store, bar, ph_attr in layers:
            for eid in [one for one in store if one not in kept]:
                tab = store.pop(eid)
                self._exchange_tabs.pop(eid, None)
                at = bar.indexOf(tab)
                if at >= 0:
                    bar.removeTab(at)
                tab.setParent(None)
                tab.deleteLater()
                dropped += 1
            ph = getattr(self, ph_attr, None)
            if ph is not None and not store and bar.indexOf(ph) < 0:
                bar.addTab(ph, PLACEHOLDER_TAB_TITLE)
        return dropped

    def _sync_exchange_tabs(self) -> None:
        """Seat a sub-tab for each exchange the fleet names and drop the rest;
        the caption is ``exchange_display_name`` over the id, as Live captions
        an exchange saved with no name."""
        wanted = [str(eid) for eid in self._fleet_source.exchanges() if eid]
        for eid in wanted:
            self.add_exchange_tab(eid, exchange_display_name({"exchange_id": eid}))
        self._drop_unlisted_exchange_tabs(wanted)
        self._refresh_states()
        self.refresh_bots()
        self.refresh_votes()

    # -- the rows -------------------------------------------------------

    def refresh_bots(self) -> int:
        """Hand every seated venue its rows from ``PaperFleetSource.statuses``
        and answer how many rows were handed out."""
        handed = 0
        for store in (self._crypto_exchange_tabs, self._stock_exchange_tabs):
            for eid, tab in list(store.items()):
                statuses = class_filter_surface.bots_of_class(
                    self._fleet_source.statuses(eid), self._asset_class
                )
                tab.update_bots(statuses)
                handed += len(statuses)
        return handed

    def set_asset_class(self, name) -> tuple:
        """Hold ``name`` as the class this tab shows and relabel Add Exchange.

        Answers the rows ``refresh_bots`` kept for ``name`` and the rows
        ``PaperFleetSource.statuses`` holds in all.
        """
        self._asset_class = class_filter_surface.normalise(name)
        self._retitle_add_exchange()
        return (self.refresh_bots(), len(self._fleet_source.statuses()))

    #: Live's relabel loop, over this tab's own buttons and its own class.
    _retitle_add_exchange = HeaderStripMixin._retitle_add_exchange

    def class_venues(self, name: Any = None) -> list:
        """The venue ids this tab has seated that serve one asset class."""
        key = class_filter_surface.normalise(
            self._asset_class if name is None else name
        )
        seated = list(self._crypto_exchange_tabs) + list(self._stock_exchange_tabs)
        return class_filter_surface.venues_of_class(seated, key)

    # -- the voting panel -----------------------------------------------

    def refresh_votes(self) -> dict:
        """Hand the panel the fleet's statuses, the fleet's own rate snapshot
        and the selected bot's reading, as the window's tick feeds Live's."""
        statuses = self._fleet_source.statuses()
        panel = self._indicator_panel
        held = panel.blockSignals(True)
        try:
            panel.update_bot_list(statuses)
        finally:
            panel.blockSignals(held)
        panel.update_currency_rates(tab_surface.rate_snapshot(statuses))
        return self._feed_votes(panel.selected_bot_id)

    def _feed_votes(self, bot_id: str = "") -> dict:
        """Draw ``ivp_feed`` for ``bot_id``, or the selected bot, on the panel
        through ``show_no_data`` with its cause."""
        panel = self._indicator_panel
        chosen = str(bot_id or panel.selected_bot_id or "")
        if not chosen:
            panel.show_no_data(cause=tab_surface.NO_SELECTION_CAUSE)
            return {"cause": tab_surface.NO_SELECTION_CAUSE}
        feed = tab_surface.ivp_feed(self._fleet_source.bot_for(chosen))
        panel.show_no_data(
            bot_id=chosen,
            symbol=feed["symbol"],
            reason=feed["reason"],
            cause=feed["cause"],
            detail=feed["detail"],
        )
        return feed

    # -- what the operator presses --------------------------------------

    def _create_bot(self, exchange_id: str = "") -> None:
        """A venue's ``+ New Bot`` press: one Activity Log line,
        ``new_bot_line``, naming Import Live Fleet as the fleet's way in."""
        self._status_log.log(tab_surface.new_bot_line(exchange_id), "warning")

    def _on_bot_fire(self, bot_id: str) -> None:
        """Manual Fire on a paper bot: ask ``PaperFleetSource`` to ``fire`` and
        log the refusal to the Activity Log, as the window logs a failed Fire."""
        try:
            self._fleet_source.fire(bot_id)
        except SendRefused as exc:
            self._status_log.log(f"Fire on {bot_id[:8]} failed: {exc}", "error")

    def _notify(self, message: str, level: str) -> None:
        """Write the window notification's line, ``notification_line``, into
        the Activity Log through ``PaperStatusLog.notice``."""
        self._status_log.notice(notification_line(message, level))

    def _activity_log_watchdog(self) -> None:
        """One tick of Live's Activity-Log watchdog over ``PaperStatusLog`` and
        ``PaperBotManager.bots``: each line ``watchdog_lines`` answers is
        written through ``force_log`` and to the file logger."""
        try:
            stats = self._status_log.health_stats()
        except Exception as exc:  # noqa: BLE001 - Live's watchdog catches all
            logger.warning(WATCHDOG_STAT_FAILURE_FORMAT, exc)
            return
        lines = tab_surface.watchdog_lines(
            self._activity_log_watchdog_state,
            stats,
            self._bot_manager.bots(),
            time.time(),
        )
        for text, level in lines:
            self._status_log.force_log(text, level)
            logger.log(logging.ERROR if level == "error" else logging.WARNING, text)

    def _cross_api_event(self, entry: dict) -> None:
        """The ``api_log()`` listener: emit ``apiEntryLogged``, which Qt queues
        onto the GUI thread for ``_on_api_event`` from any other thread."""
        self.apiEntryLogged.emit(entry)

    def _on_api_event(self, entry: dict) -> None:
        """Append one ``api_log()`` entry to ``_api_log_view`` as Live's block,
        refusing a call off the GUI thread; while ``_api_log_paused`` the
        block goes to ``_api_log_pause_buffer``, the oldest dropped past its
        cap, and the view follows its newest block when already at the bottom.
        """
        current = threading.current_thread().name
        if tab_surface.api_event_off_thread(
            entry, "PaperTradingTab._on_api_event", current
        ):
            return
        block_text = tab_surface.api_block(entry)
        if self._api_log_paused:
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

    def _on_bot_command(self, bot_id: str, command: str) -> None:
        """One command-bar press on ``bot_id``: the window's ``_on_bot_command``
        forked over ``PaperBotManager``, with no venue connect, Live's Activity
        Log lines, Live's sounds and Live's Delete box, and ``fleet_changed``
        fired when the state moved or the record left."""
        bot = self._bot_manager.get_bot(bot_id)
        if not bot:
            self._status_log.log(f"Bot {bot_id} not found.", "error")
            return

        sound = get_sound_engine()
        moved = False

        if command == "start":
            try:
                moved = self._bot_manager.start(bot_id) != bot.state
                self._status_log.log(f"✓ Bot {bot_id} RUNNING.", "success")
                self._notify(f"Bot {bot_id} RUNNING", "success")
                sound.play_state_change()
            except Exception as exc:  # noqa: BLE001 - Live's handler catches all
                self._status_log.log(f"Failed to start bot {bot_id}: {exc}", "error")
                sound.play_error()

        elif command == "pause":
            self._status_log.log(f"Pausing bot {bot_id}...", "info")
            try:
                moved = self._bot_manager.pause(bot_id) != bot.state
                self._status_log.log(f"Bot {bot_id} paused.", "warning")
                self._notify(f"Bot {bot_id} PAUSED", "warning")
                sound.play_state_change()
            except Exception as exc:  # noqa: BLE001 - Live's handler catches all
                self._status_log.log(f"Failed to pause bot {bot_id}: {exc}", "error")

        elif command == "stop":
            self._status_log.log(f"Stopping bot {bot_id}...", "info")
            try:
                moved = self._bot_manager.stop(bot_id) != bot.state
                self._status_log.log(f"Bot {bot_id} stopped.", "info")
                self._notify(f"Bot {bot_id} STOPPED", "info")
                sound.play_state_change()
            except Exception as exc:  # noqa: BLE001 - Live's handler catches all
                self._status_log.log(f"Failed to stop bot {bot_id}: {exc}", "error")

        elif command == "restart":
            try:
                self._bot_manager.restart(bot_id)
                moved = True
                self._status_log.log(f"✓ Bot {bot_id} restarted.", "success")
                self._notify(f"Bot {bot_id} RESTARTED", "success")
                sound.play_state_change()
            except Exception as exc:  # noqa: BLE001 - Live's handler catches all
                self._status_log.log(f"Failed to restart bot {bot_id}: {exc}", "error")
                sound.play_error()

        elif command == "delete":
            confirm = QMessageBox.question(
                self,
                "Delete Bot",
                f"Delete bot {bot_id}? This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm == QMessageBox.Yes:
                try:
                    self._bot_manager.stop(bot_id)
                except Exception as exc:  # noqa: BLE001 - Live's handler catches all
                    self._status_log.log(
                        f"Failed to stop bot {bot_id} before delete: {exc}.",
                        "error",
                    )
                moved = self._bot_manager.unregister(bot_id)
                self._status_log.log(f"Bot {bot_id} deleted.", "warning")
                self._notify(f"Bot {bot_id} DELETED", "warning")
                sound.play_state_change()

        if moved:
            self.fleet_changed.emit()

    def _global_bot_cmd(self, command: str) -> None:
        """One SHIFT press on the command bar: the named all-bots verb run over
        ``PaperBotManager``, which moves a saved state per bot and connects to
        no venue."""
        if command not in FLEET_VERBS:
            self._status_log.log(f"{command} is not a fleet command.", "error")
            return
        self._status_log.log(f"Executing {command} on all paper bots...", "info")
        sound = get_sound_engine()
        try:
            moved = getattr(self._bot_manager, command)()
        except Exception as exc:  # noqa: BLE001 - Live's handler catches all
            self._status_log.log(f"{command} failed: {exc}", "error")
            sound.play_error()
            return
        self._status_log.log(f"{command}: {moved} bot(s) moved.", "success")
        self._notify(f"{moved} paper bot(s): {command}", "success")
        sound.play_state_change()
        if moved:
            self.fleet_changed.emit()

    def _on_bot_detail(self, bot_id: str) -> None:
        """Open the Paper Trader's Bot Settings window,
        ``surface_class(PAPER_BOT_DETAIL)``, for ``bot_id`` over its
        ``PaperBotView`` and follow Prev and Next over the venue's paper fleet,
        keeping the geometry and the tab."""
        bot = self._fleet_source.bot_for(bot_id)
        if bot is None:
            return
        window_class = surface_class(PAPER_BOT_DETAIL)
        saved_geometry = None
        saved_tab_index = None
        while bot is not None:
            siblings = [
                one.bot_id
                for one in self._fleet_source.bots()
                if one.exchange_id == bot.exchange_id
            ]
            rates = usd_rates(self._fleet_source.statuses(bot.exchange_id))
            view = PaperBotView(
                bot,
                self._fleet_source.record_for(bot.bot_id),
                tab_surface.config_writer(
                    self._fleet_source, bot.bot_id, self.fleet_changed.emit
                ),
            )
            dlg = window_class(view, siblings, self, rates)
            if saved_geometry is not None:
                dlg.setGeometry(saved_geometry)
            if saved_tab_index is not None:
                dlg._tabs.setCurrentIndex(int(saved_tab_index))
            dlg.exec()
            saved_geometry = dlg.geometry()
            saved_tab_index = dlg.active_tab_index()
            target_id = dlg._pending_navigate_to
            bot = self._fleet_source.bot_for(target_id) if target_id else None


__all__ = ["ACCESSIBLE_NAME", "PaperTradingTab"]
