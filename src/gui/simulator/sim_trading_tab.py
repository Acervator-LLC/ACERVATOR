"""The Simulator tab in Qt: Live's tab body, forked under the Simulator's name.

``SimTradingTab`` is ``TradingTabMixin._build_trading_tab`` from
``src/gui/main_tabs/trading_tab.py`` as a widget of its own: the exchange layer
stack, the forked ``SimIndicatorVotingPanel``, and the Activity Log and API
Interaction Log spools, in Live's four splitters at Live's sizes.
``add_exchange_tab`` is the window's method of that name, forked, and seats a
``SimExchangeTab``; ``_sync_exchange_tabs`` seats one per exchange
``FleetSource.exchanges`` names, at build and on every ``fleet_changed``, drops
the rest as the window's ``_drop_unlisted_exchange_tabs`` does, and then
``refresh_bots`` hands each venue its rows from ``FleetSource.statuses`` and
``refresh_votes`` hands the panel the fleet, its own rates and the selected
bot's ``ivp_feed`` over ``TabletSource``, run again by ``bot_selected``; every
``fleet_changed`` first writes the sim fleet file through ``FleetSource.save``. The
tab holds the run mode, ``mode``, the first of ``MODES`` at open; a venue
page's mode button reaches ``set_mode``, which draws the active sheet on every
seated page through ``SimExchangeTab.show_mode`` and redraws the way-ins
through ``_draw_way_ins``. The corner Live gives ``＋ Add Crypto Exchange``
holds the two way-in buttons the run mode offers, from ``reserved_rows``, and
the Get Started card holds the same two where Live's card holds its add
button; each reaches ``_way_in``, which opens the wizard for Create New Bots,
runs ``_import_live_fleet`` for Import Live Fleet, runs
``_generate_from_ytd`` for Generate From YTD, and logs the ``SendRefused``
``FleetSource`` raises for every other action. ``_import_live_fleet`` puts
``exchange_choice`` over ``FleetSource.stored_exchanges``, opens
``SimExchangeChoiceDialog`` when it prompts, copies the chosen exchange's
records through ``FleetSource.import_live_fleet`` and fires ``fleet_changed``,
so the venue seats and its rows draw; the tab starts empty because
``FleetSource.bots`` answers the held records alone. ``_generate_from_ytd``
reads ``YtdTradeSource.root_state`` and writes one line for a directory that
is missing, empty or without a manifest, puts ``exchange_choice`` over the
exchanges the manifest names, opens the same chooser under Generate From
YTD's title, holds one record per traded pair through
``FleetSource.generate_from_ytd``, writes one line per manifest row whose
file is missing, the generation line and the no-target line, and fires
``fleet_changed``. ``_run_battery`` opens ``SimPortfolioChoiceDialog``, holds
the ``plan_run`` bots through ``FleetSource.hold_battery_fleet``, fires
``fleet_changed`` and runs ``_compute_battery`` on a daemon thread, whose
``battery_line``, ``battery_trade`` and ``battery_finished`` signals reach the
Activity Log, ``log_trade`` and ``_take_battery`` on the GUI thread.
The replay layer, ``LineView`` over ``PlaybackView``, sits behind the
panel in ``_layer_stack``, reached by ``flip_layer``; its header row holds the
flip button, the ``Tablet:`` chooser and the retrieval button.
``_refresh_replay`` fills the chooser from ``tablet_choices`` and
``_feed_replay`` draws ``replay_feed`` on the two windows, at build, on every
``fleet_changed``, on the flip, on the chooser's change, on ``bot_selected``
and after a retrieval. ``_retrieve_tablet`` runs ``tablet_retrieval.retrieve``
on a daemon thread over the tab's ``ReadOnlyConnector``, the one venue path,
which answers ``get_ohlcv`` over the public candle endpoint and raises
``SendRefused`` for every other name; each venue call crosses on
``retrieval_call`` and ``_record_venue_call`` records it on ``api_log``, each
line crosses on ``retrieval_line``, and ``_take_retrieval`` writes the finished
or refused line and redraws. A venue's ``+ New Bot``
reaches ``_create_bot``, which opens ``SimBotCreationWizard`` and hands its
config to ``FleetSource.create``. A row's Fire reaches ``_on_bot_fire``, which
asks ``FleetSource`` and logs its refusal; a row's Detail reaches
``_on_bot_detail``, which opens the Simulator's Bot Settings window through
``surface_class(SIM_BOT_DETAIL)`` over a ``SimBotView``. The command bar's
Start, Pause, Stop, Restart and Delete reach ``_on_bot_command``, the window's
handler forked over ``SimBotManager`` with no venue connect, which logs Live's
lines, opens Live's Delete box, and fires ``fleet_changed`` on every state
move. ``TabletSource`` and ``FleetSource`` are the tab's only sources, and
neither answers a send. The API Interaction Log is written by
``_on_api_event``, the window's writer forked over the tab's own
``SimApiLog``, never the process-wide ``get_api_log``: each entry
recorded on ``api_log()`` draws Live's block, or is held while Pause API Log is
down and flushed in order on Resume. That log accepts ``ALLOWED_ACTIONS``
only, the ``FETCH_TABLET`` entries ``_record_venue_call`` records and the
``FETCH_YTD`` entry ``_generate_from_ytd`` records, and raises ``SendRefused``
for any other action before anything is drawn.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.sound_engine import get_sound_engine
from ...simulator import portfolio_battery
from ...simulator.back_test import SimTrade
from ...simulator.fleet_source import (
    EXTRACTOR_MODE,
    FleetSource,
    SendRefused,
    exchange_choice,
)
from ...simulator import tablet_retrieval
from ...simulator.parity_report import ParityReport, report_line
from ...simulator.portfolios import PORTFOLIOS
from ...simulator.read_only_connector import ReadOnlyConnector, VenueCall
from ...simulator.sim_api_log import SimApiLog
from ...simulator.sim_bot_manager import SimBotManager
from ...simulator.sim_bot_view import SimBotView
from ...simulator.tablet_source import TabletSource, tablet_key
from ...simulator.ytd_trade_source import ROOT_READY, YtdTradeSource
from ...trading.stone_tablets.storage import tablet_filename
from .. import design_system as ds
from ..color_alpha import rgba
from ..main_tabs import simulator_tab_surface as surface
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
from ..simulator_tab import LineView, PlaybackView
from ..theme_engine import NIGREDO, TONE_PROPERTY
from ..variant_surface import SIM_BOT_DETAIL, SIM_BOT_WIZARD, surface_class
from . import sim_bot_wizard_surface as wizard_surface
from .sim_bot_status_table_surface import usd_rates
from .sim_exchange_choice import SimExchangeChoiceDialog, SimPortfolioChoiceDialog
from .sim_exchange_tab import SimExchangeTab
from .sim_indicator_panel import SimIndicatorVotingPanel
from .sim_status_log import SimStatusLog
from . import sim_trading_tab_surface as tab_surface
from .sim_trading_tab_surface import (
    card_button_name,
    notification_line,
    placeholder_hint_text,
    placeholder_title_text,
)

logger = logging.getLogger("acervator.gui")

PLACEHOLDER_CARD_BORDER_ALPHA = 68

ACCESSIBLE_NAME = "Sim"

FLIP_BUTTON_NAME = "sim-flip-button"
TABLET_LABEL_NAME = tab_surface.TABLET_LABEL_NAME
TABLET_CHOOSER_NAME = tab_surface.TABLET_CHOOSER_NAME
RETRIEVE_BUTTON_NAME = tab_surface.RETRIEVE_BUTTON_NAME

TABLET_CHOOSER_WIDTH_PX = tab_surface.TABLET_CHOOSER_WIDTH_PX

#: The theme gives a button 20 px of side padding; the flip button keeps 4 px
#: so its text draws whole beside the panel title at the window's floor.
FLIP_BUTTON_SIDE_PADDING_PX = 4
FLIP_BUTTON_QSS = (
    f"QPushButton#{FLIP_BUTTON_NAME} {{ padding-left: {FLIP_BUTTON_SIDE_PADDING_PX}px; "
    f"padding-right: {FLIP_BUTTON_SIDE_PADDING_PX}px; }}"
)

#: Live's corner button is 24 px tall: its ＋ glyph sets that height, and the
#: way-in buttons carry no such glyph.
WAY_IN_BUTTON_HEIGHT_PX = 24


class WayInSlot:
    """One layer's two way-in positions: ``corner``, the corner row, and
    ``card``, the Get Started card's column, with the buttons drawn in each."""

    def __init__(self, corner: QHBoxLayout, card: QVBoxLayout, accent: str) -> None:
        self.corner = corner
        self.card = card
        self.accent = accent
        self.corner_buttons: list[QPushButton] = []
        self.card_buttons: list[QPushButton] = []


class FlipButton(QPushButton):
    """A ``QPushButton`` named ``FLIP_BUTTON_NAME`` whose layout may shrink it to width 0."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName(FLIP_BUTTON_NAME)
        self.setAccessibleName(FLIP_BUTTON_NAME)
        self.setSizePolicy(QSizePolicy.Preferred, self.sizePolicy().verticalPolicy())
        self.setStyleSheet(FLIP_BUTTON_QSS)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """The base hint's height over a width of 0."""
        return QSize(0, super().minimumSizeHint().height())


class SimTradingTab(QWidget):
    """The Sim tab: Live's tab body over the Simulator's two sources."""

    #: Fired by whatever loads a fleet; the venue sub-tabs re-seat on it.
    fleet_changed = Signal()
    #: One Activity Log line and its level from the Battery's worker thread.
    battery_line = Signal(str, str)
    #: One ``SimTrade`` the Battery's walk filled on the worker thread.
    battery_trade = Signal(object)
    #: The ``BatteryRun`` the Battery's worker thread finished with.
    battery_finished = Signal(object)
    #: One Activity Log line and its level from a retrieval's worker thread.
    retrieval_line = Signal(str, str)
    #: One ``VenueCall`` the read-only connector made on the worker thread.
    retrieval_call = Signal(object)
    #: The ``RetrievalOutcome`` a retrieval's worker thread finished with.
    retrieval_finished = Signal(object)

    def __init__(
        self,
        tablet_source: Optional[TabletSource] = None,
        fleet_source: Optional[FleetSource] = None,
        parent: Optional[QWidget] = None,
        api_log: Optional[SimApiLog] = None,
        battery_tablet_source: Optional[TabletSource] = None,
        connector: Optional[ReadOnlyConnector] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(ACCESSIBLE_NAME)
        self.setAccessibleName(ACCESSIBLE_NAME)
        # The theme's nigredo_qss paints this tree, and the windows it parents.
        # A QWidget subclass paints its stylesheet ground only with this attribute.
        self.setProperty(TONE_PROPERTY, NIGREDO)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._tablet_source = (
            tablet_source
            if tablet_source is not None
            else TabletSource(surface.TABLET_ROOT)
        )
        self._battery_tablet_source = (
            battery_tablet_source
            if battery_tablet_source is not None
            else TabletSource(surface.BATTERY_TABLET_ROOT)
        )
        self._fleet_source = fleet_source if fleet_source is not None else FleetSource()
        self._api_log = api_log if api_log is not None else SimApiLog()
        self._bot_manager = SimBotManager(self._fleet_source)
        self._connector = (
            connector
            if connector is not None
            else ReadOnlyConnector(on_call=self._on_venue_call)
        )
        self._layer = surface.LAYER_INDICATORS
        self._mode = surface.MODES[0]
        self._battery_thread: Optional[threading.Thread] = None
        self._retrieval_thread: Optional[threading.Thread] = None
        self._retrieval: dict = {}
        self._tablet_key: str = ""
        self._replay: dict = {}
        self._build()
        self._draw_way_ins()
        self._api_log.add_listener(self._on_api_event)
        self._indicator_panel.bot_selected.connect(self._feed_votes)
        self._indicator_panel.bot_selected.connect(self._follow_bot_tablet)
        self.fleet_changed.connect(self._fleet_source.save)
        self.fleet_changed.connect(self._sync_exchange_tabs)
        self.battery_line.connect(self._status_log.log)
        self.battery_trade.connect(self.log_trade)
        self.battery_finished.connect(self._take_battery)
        self.retrieval_line.connect(self._status_log.log)
        self.retrieval_call.connect(self._record_venue_call)
        self.retrieval_finished.connect(self._take_retrieval)
        self._sync_exchange_tabs()

    # -- what the window reads ------------------------------------------

    def tablet_source(self) -> TabletSource:
        """The tablet reader the panel is fed from."""
        return self._tablet_source

    def battery_tablet_source(self) -> TabletSource:
        """The RA-StoneTablet reader the Portfolio Battery runs over."""
        return self._battery_tablet_source

    def battery_running(self) -> bool:
        """True while a Battery worker thread is alive."""
        thread = self._battery_thread
        return thread is not None and thread.is_alive()

    def connector(self) -> ReadOnlyConnector:
        """The read-only connector a retrieval reads candles through."""
        return self._connector

    def retrieval_running(self) -> bool:
        """True while a retrieval worker thread is alive."""
        thread = self._retrieval_thread
        return thread is not None and thread.is_alive()

    def tablet_key(self) -> str:
        """The chooser's chosen key, the item the two windows draw."""
        return self._tablet_key

    def replay(self) -> dict:
        """The ``replay_feed`` the two windows last drew."""
        return dict(self._replay)

    def fleet_source(self) -> FleetSource:
        """The fleet reader the tables are fed from."""
        return self._fleet_source

    def aggregate(self) -> dict:
        """The header strip's figures, ``fleet_aggregate`` over the held fleet in
        the tab's ``mode``."""
        return surface.fleet_aggregate(self._fleet_source, self._mode)

    def api_log(self) -> SimApiLog:
        """The tab's own API log; every entry it accepts reaches the pane, and
        it accepts ``ALLOWED_ACTIONS`` only."""
        return self._api_log

    def exchange_count(self) -> int:
        """How many venue sub-tabs ``add_exchange_tab`` has seated; EXCH reads it."""
        return len(self._exchange_tabs)

    def layer(self) -> str:
        """The layer the stack is showing, ``indicators`` or ``playback``."""
        return self._layer

    def way_in_buttons(self) -> dict[str, QPushButton]:
        """The corner buttons, keyed by action."""
        return dict(self._way_in_buttons)

    def card_way_in_buttons(self) -> dict[str, QPushButton]:
        """The Get Started card's buttons, keyed by action."""
        return dict(self._card_way_in_buttons)

    def mode(self) -> str:
        """The run mode in force, one of ``MODES``."""
        return self._mode

    # -- the run mode -----------------------------------------------------

    def set_mode(self, mode: str) -> str:
        """Make ``mode`` the run mode: the active sheet on every seated venue
        page's header and the mode's two ways in at each corner and card.
        A name outside ``MODES`` changes nothing; answers the mode in force."""
        if mode not in surface.MODES:
            return self._mode
        self._mode = mode
        for venue in list(self._crypto_exchange_tabs.values()) + list(
            self._stock_exchange_tabs.values()
        ):
            venue.show_mode(mode)
        self._draw_way_ins()
        return self._mode

    def _draw_way_ins(self) -> None:
        """Draw the run mode's two way-in buttons at each layer's corner, at
        Live's corner-button size, and on each layer's Get Started card between
        its title and its hint, replacing the buttons drawn before."""
        rows = surface.reserved_rows(self._mode)
        self._way_in_buttons.clear()
        self._card_way_in_buttons.clear()
        for slot in self._way_in_slots:
            for layout, drawn in (
                (slot.corner, slot.corner_buttons),
                (slot.card, slot.card_buttons),
            ):
                for old in drawn:
                    layout.removeWidget(old)
                    old.setParent(None)
                    old.deleteLater()
                drawn.clear()
            for row in rows:
                way_in = QPushButton(row["text"])
                way_in.setMinimumWidth(140)
                way_in.setMinimumHeight(WAY_IN_BUTTON_HEIGHT_PX)
                way_in.setAccessibleName(surface.button_name(row["action"]))
                way_in.clicked.connect(
                    lambda _checked=False, action=row["action"]: self._way_in(action)
                )
                slot.corner.addWidget(way_in)
                slot.corner_buttons.append(way_in)
                self._way_in_buttons.setdefault(row["action"], way_in)
            for at, row in enumerate(rows):
                card_way_in = QPushButton(row["text"])
                card_way_in.setMinimumSize(180, 36)
                card_way_in.setStyleSheet(
                    f"QPushButton {{ border: 1px solid {slot.accent}; "
                    f"color: {slot.accent}; border-radius: 4px; }}"
                )
                card_way_in.setAccessibleName(card_button_name(row["action"]))
                card_way_in.clicked.connect(
                    lambda _checked=False, action=row["action"]: self._way_in(action)
                )
                slot.card.insertWidget(1 + at, card_way_in, alignment=Qt.AlignCenter)
                slot.card_buttons.append(card_way_in)
                self._card_way_in_buttons.setdefault(row["action"], card_way_in)

    def _current_venue_id(self) -> str:
        """The exchange of the venue sub-tab on show, or ``""`` with none seated."""
        shown = self._tab_widget.currentWidget()
        return str(getattr(shown, "exchange_id", "") or "")

    def _way_in(self, action: str) -> None:
        """One way-in pressed at the corner or on the card: Create New Bots
        opens the wizard through ``_create_bot``, Import Live Fleet runs
        ``_import_live_fleet``, Generate From YTD runs ``_generate_from_ytd``,
        Run Portfolio and Run Every Portfolio run ``_run_battery``; every
        other action asks ``FleetSource`` for it by name, which raises
        ``SendRefused``, and the refusal is logged to the Activity Log."""
        if action == surface.CREATE_NEW_BOTS_ACTION:
            self._create_bot(self._current_venue_id())
            return
        if action == surface.IMPORT_LIVE_FLEET_ACTION:
            self._import_live_fleet()
            return
        if action == surface.GENERATE_FROM_YTD_ACTION:
            self._generate_from_ytd()
            return
        if action in (surface.RUN_PORTFOLIO_ACTION, surface.RUN_EVERY_PORTFOLIO_ACTION):
            self._run_battery(action)
            return
        try:
            getattr(self._fleet_source, action)
        except SendRefused as exc:
            self._status_log.log(tab_surface.way_in_refused_line(action, exc), "error")

    def _run_battery(self, action: str) -> None:
        """Run Portfolio or Run Every Portfolio: one line and nothing started
        while ``battery_running``; ``SimPortfolioChoiceDialog`` over
        ``PORTFOLIOS`` and ``BATTERY_SPANS``, the portfolio row left out for
        ``RUN_EVERY_PORTFOLIO_ACTION``; then ``plan_run`` over the held fleet,
        ``FleetSource.hold_battery_fleet`` on the plan's bots, ``fleet_changed``,
        the started line, and ``_compute_battery`` on a daemon thread; a
        cancelled chooser writes one line and moves nothing."""
        if self.battery_running():
            self._status_log.log(tab_surface.BATTERY_RUNNING_TEXT, "warning")
            return
        every = action == surface.RUN_EVERY_PORTFOLIO_ACTION
        dialog = SimPortfolioChoiceDialog(
            PORTFOLIOS, surface.BATTERY_SPANS, self, every=every
        )
        if dialog.exec() != QDialog.Accepted:
            self._status_log.log(tab_surface.BATTERY_CANCELLED_TEXT, "warning")
            return
        names = () if every else (dialog.chosen_portfolio(),)
        span = dialog.chosen_span() or surface.DEFAULT_SPAN
        plan = portfolio_battery.plan_run(
            names, self._battery_tablet_source, self._fleet_source.bots()
        )
        self._fleet_source.hold_battery_fleet(plan.bots)
        self.fleet_changed.emit()
        subject = tab_surface.EVERY_PORTFOLIO_SUBJECT if every else names[0]
        self._status_log.log(
            tab_surface.battery_started_line(
                subject, span, len(plan.bots), plan.plan_origins, plan.budget_usd
            ),
            "success",
        )
        self._battery_thread = threading.Thread(
            target=self._compute_battery,
            args=(plan, span),
            name="sim-portfolio-battery",
            daemon=True,
        )
        self._battery_thread.start()

    def _compute_battery(self, plan, span: str) -> None:
        """Run ``portfolio_battery.run_battery`` over ``battery_tablet_source``
        on ``plan`` and hand the ``BatteryRun`` to the GUI thread through
        ``battery_finished``, each portfolio's line through ``battery_line`` and
        each ``SimTrade`` through ``battery_trade``; a run that raises writes
        one failed line instead."""
        try:
            outcome = portfolio_battery.run_battery(
                self._battery_tablet_source,
                names=plan.names,
                span=span,
                ticks=surface.BATTERY_TICKS_PER_SYMBOL,
                plan=plan,
                progress=lambda line: self.battery_line.emit(line, "info"),
                on_trade=self.battery_trade.emit,
            )
        except Exception as exc:  # noqa: BLE001 - the run runs off-thread
            logger.exception("Portfolio Battery failed: %s", exc)
            self.battery_line.emit(tab_surface.battery_failed_line(exc), "error")
            return
        self.battery_finished.emit(outcome)

    def _take_battery(self, outcome) -> None:
        """Write the finished run's ``lines`` and its report line through
        ``log_report`` on the GUI thread."""
        for line in outcome.lines:
            self._status_log.log(line, "info")
        if outcome.report is not None:
            self.log_report(outcome.report)

    def _generate_from_ytd(self) -> None:
        """Generate From YTD: one line and nothing held unless
        ``YtdTradeSource.root_state`` is ``ROOT_READY`` and the manifest names
        a pair; ``exchange_choice`` over the exchanges it names,
        ``SimExchangeChoiceDialog`` under ``GENERATE_FROM_YTD_TEXT`` when it
        prompts, then ``FleetSource.generate_from_ytd`` on the exchange chosen,
        one ``ytd_api_entry`` recorded on ``api_log`` for that read, one line
        per manifest row whose file is missing, the generation line, the
        no-target line and ``fleet_changed``; a cancelled chooser writes one
        line and moves nothing."""
        source = YtdTradeSource()
        state = source.root_state()
        if state != ROOT_READY:
            self._status_log.log(
                tab_surface.ytd_root_line(state, source.root()), "warning"
            )
            return
        options = sorted({entry.exchange_id for entry in source.entries()})
        if not options:
            self._status_log.log(tab_surface.ytd_no_pair_line(source.root()), "warning")
            return
        choice = exchange_choice(options)
        chosen = choice["chosen"]
        if choice["prompt"]:
            dialog = SimExchangeChoiceDialog(
                options, self, title=surface.GENERATE_FROM_YTD_TEXT
            )
            if dialog.exec() != QDialog.Accepted:
                self._status_log.log(tab_surface.GENERATE_CANCELLED_TEXT, "warning")
                return
            chosen = dialog.chosen()
        started = time.perf_counter()
        made = self._fleet_source.generate_from_ytd(source, chosen)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._api_log.record(
            **tab_surface.ytd_api_entry(made, chosen, source.root(), elapsed_ms)
        )
        for entry in made.missing:
            self._status_log.log(tab_surface.ytd_file_missing_line(entry), "warning")
        if not made.bots:
            return
        self._status_log.log(
            tab_surface.generated_line(len(made.bots), made.files_read, chosen),
            "success",
        )
        without_target = sum(1 for bot in made.bots if bot.target_usd is None)
        if without_target:
            self._status_log.log(tab_surface.no_target_line(without_target), "warning")
        self.fleet_changed.emit()

    def _import_live_fleet(self) -> None:
        """Import Live Fleet: ``exchange_choice`` over the exchanges
        ``FleetSource.stored_exchanges`` names, ``SimExchangeChoiceDialog`` when
        it prompts, then ``FleetSource.import_live_fleet`` on the exchange chosen,
        one Activity Log line and ``fleet_changed``; a file naming no bot and a
        cancelled chooser each write one line and move nothing."""
        options = self._fleet_source.stored_exchanges()
        if not options:
            self._status_log.log(tab_surface.no_stored_bot_line(), "warning")
            return
        choice = exchange_choice(options)
        chosen = choice["chosen"]
        if choice["prompt"]:
            dialog = SimExchangeChoiceDialog(options, self)
            if dialog.exec() != QDialog.Accepted:
                self._status_log.log(tab_surface.IMPORT_CANCELLED_TEXT, "warning")
                return
            chosen = dialog.chosen()
        imported = self._fleet_source.import_live_fleet(chosen)
        self._status_log.log(
            tab_surface.imported_line(len(imported), chosen), "success"
        )
        self.fleet_changed.emit()

    def log_report(self, report: ParityReport) -> None:
        """One Activity Log line, ``report_line`` over ``report``, through
        ``SimStatusLog.log`` at the ``success`` level ``_import_live_fleet`` uses."""
        self._status_log.log(report_line(report), "success")

    def log_trade(self, trade: SimTrade) -> None:
        """One Activity Log line per ``SimTrade``: ``trade_line`` under
        ``trade_stamp`` through ``SimStatusLog.log_at`` at ``TRADE_LINE_LEVEL``."""
        self._status_log.log_at(
            tab_surface.trade_stamp(trade),
            tab_surface.trade_line(trade),
            tab_surface.TRADE_LINE_LEVEL,
        )

    # -- construction ---------------------------------------------------

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
        self._trading_stack = QStackedWidget()
        self._way_in_buttons: dict[str, QPushButton] = {}
        self._card_way_in_buttons: dict[str, QPushButton] = {}
        self._way_in_slots: list[WayInSlot] = []

        def _make_layer(label_text: str, accent: str) -> tuple:
            """Build one trading layer — returns (page_widget, tab_widget,
            exchange_tabs_dict, placeholder_widget)."""
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)

            tab_w = QTabWidget()
            # The corner Live gives ＋ Add Crypto Exchange holds the run
            # mode's two way-in buttons, drawn by _draw_way_ins.
            corner = QWidget()
            corner_row = QHBoxLayout(corner)
            corner_row.setContentsMargins(0, 0, 0, 0)
            corner_row.setSpacing(2)
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
            # The card's button position, between the title and the hint,
            # holds the run mode's two way-ins, drawn by _draw_way_ins.
            self._way_in_slots.append(WayInSlot(corner_row, ph_layout, accent))
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

        # Right panel: the forked voting panel, with the replay layer behind it
        self._indicator_panel = SimIndicatorVotingPanel()
        self._chart = None  # No chart in trading tab
        self._flip_button = FlipButton(
            surface.FLIP_BUTTON_TEXT[surface.LAYER_INDICATORS]
        )
        self._flip_button.clicked.connect(self.flip_layer)
        # After the title and before the stretch, so the bot selector and the
        # privacy dot keep Live's right-aligned geometry.
        self._indicator_panel.header_row().insertWidget(1, self._flip_button)
        self._layer_stack = QStackedWidget()
        self._layer_stack.addWidget(self._indicator_panel)
        self._layer_stack.addWidget(self._build_chart_pane())
        top_splitter.addWidget(self._layer_stack)

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
        self._status_log = SimStatusLog()
        self._status_log.setMaximumHeight(16777215)  # Remove height limit
        activity_layout.addWidget(self._status_log)
        log_splitter.addWidget(activity_widget)

        # Polls SimStatusLog.health_stats() every 60s on the GUI thread.
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
        # _on_api_event reads this flag; QPlainTextEdit has no SimStatusLog subclass.
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

    def _build_chart_pane(self) -> QWidget:
        """The replay layer: a header row for the flip button, the ``Tablet:``
        chooser and the retrieval button, over ``LineView`` and
        ``PlaybackView`` in one splitter."""
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        # The same margins as the panel's header, so the flip button keeps
        # its row when it moves here.
        self._chart_header = QHBoxLayout()
        self._chart_header.setContentsMargins(4, 2, 4, 2)
        self._chart_header.addStretch()
        self._tablet_label = QLabel(surface.TABLET_LABEL_TEXT)
        self._tablet_label.setObjectName(TABLET_LABEL_NAME)
        self._tablet_label.setAccessibleName(TABLET_LABEL_NAME)
        self._chart_header.addWidget(self._tablet_label)
        self._tablet_chooser = QComboBox()
        self._tablet_chooser.setObjectName(TABLET_CHOOSER_NAME)
        self._tablet_chooser.setAccessibleName(TABLET_CHOOSER_NAME)
        self._tablet_chooser.setFixedWidth(TABLET_CHOOSER_WIDTH_PX)
        self._tablet_chooser.currentIndexChanged.connect(self._on_tablet_chosen)
        self._chart_header.addWidget(self._tablet_chooser)
        self._retrieve_button = QPushButton(surface.RETRIEVE_TABLET_TEXT)
        self._retrieve_button.setObjectName(RETRIEVE_BUTTON_NAME)
        self._retrieve_button.setAccessibleName(RETRIEVE_BUTTON_NAME)
        self._retrieve_button.clicked.connect(self._retrieve_tablet)
        self._chart_header.addWidget(self._retrieve_button)
        column.addLayout(self._chart_header)
        self._layer_splitter = QSplitter(Qt.Vertical)
        self._layer_splitter.setHandleWidth(surface.HANDLE_WIDTH_PX)
        self._layer_splitter.setChildrenCollapsible(False)
        self._vwap_view = LineView()
        self._playback_view = PlaybackView()
        self._layer_splitter.addWidget(self._vwap_view)
        self._layer_splitter.addWidget(self._playback_view)
        self._layer_splitter.setSizes(surface.LAYER_SPLITTER_SIZES)
        column.addWidget(self._layer_splitter, 1)
        return pane

    # -- the venue sub-tabs ---------------------------------------------

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

        tab = SimExchangeTab(
            exchange_id,
            display_name,
            on_new_bot=self._create_bot,
            on_bot_clicked=self._on_bot_detail,
            on_bot_cmd=self._on_bot_command,
            on_bot_fire=self._on_bot_fire,
            status_log=self._status_log,
            on_mode=self.set_mode,
            mode=self._mode,
        )
        target_widget.addTab(tab, display_name)
        target_tabs[exchange_id] = tab

        if target_tabs is self._exchange_tabs:
            self._exchange_tabs[exchange_id] = tab

    def _drop_unlisted_exchange_tabs(self, listed: list) -> int:
        """Take off every venue sub-tab whose id is not in ``listed``.

        The layer's Get Started page is added back once its bar empties.
        """
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
        """Seat a sub-tab for each exchange the fleet names and drop the rest.

        The caption is ``exchange_display_name`` over the id, as Live captions
        an exchange saved with no name.
        """
        wanted = [str(eid) for eid in self._fleet_source.exchanges() if eid]
        for eid in wanted:
            self.add_exchange_tab(eid, exchange_display_name({"exchange_id": eid}))
        self._drop_unlisted_exchange_tabs(wanted)
        self.refresh_bots()
        self.refresh_votes()
        self._refresh_replay()

    # -- the rows -------------------------------------------------------

    def refresh_bots(self) -> int:
        """Hand every seated venue its rows from ``FleetSource.statuses``.

        Answers how many rows were handed out. A venue whose list is empty
        hides its tables, as Live's does.
        """
        handed = 0
        for store in (self._crypto_exchange_tabs, self._stock_exchange_tabs):
            for eid, tab in list(store.items()):
                statuses = self._fleet_source.statuses(eid)
                tab.update_bots(statuses)
                handed += len(statuses)
        return handed

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
        """Draw ``ivp_feed`` for ``bot_id``, or the selected bot, on the panel:
        ``show_stored`` over a reading, ``show_no_data`` with its cause."""
        panel = self._indicator_panel
        chosen = str(bot_id or panel.selected_bot_id or "")
        if not chosen:
            panel.show_no_data(cause="no_selection")
            return {"cause": "no_selection"}
        feed = tab_surface.ivp_feed(
            self._tablet_source, self._fleet_source.bot_for(chosen)
        )
        if feed.get("summary"):
            panel.show_stored(
                feed["stored"], feed["when"], feed["age"], feed["message"]
            )
        else:
            panel.show_no_data(
                bot_id=chosen,
                symbol=feed["symbol"],
                reason=feed["reason"],
                cause=feed["cause"],
                detail=feed["detail"],
            )
        return feed

    # -- the replay layer -----------------------------------------------

    def _selected_bot(self):
        chosen = str(self._indicator_panel.selected_bot_id or "")
        return self._fleet_source.bot_for(chosen) if chosen else None

    def _refresh_replay(self, follow_bot: bool = False) -> dict:
        """Rebuild the chooser from ``tablet_choices`` over the disk and the
        held fleet, keep the chosen key when it is still listed or take
        ``default_tablet_key`` for the selected bot, then ``_feed_replay``."""
        choices = surface.tablet_choices(self._tablet_source, self._fleet_source.bots())
        keys = [str(one["key"]) for one in choices]
        if follow_bot or self._tablet_key not in keys:
            wanted = surface.default_tablet_key(
                self._tablet_source, self._selected_bot()
            )
            self._tablet_key = wanted if wanted in keys else (keys[0] if keys else "")
        held = self._tablet_chooser.blockSignals(True)
        try:
            self._tablet_chooser.clear()
            for one in choices:
                self._tablet_chooser.addItem(str(one["text"]), str(one["key"]))
            if self._tablet_key in keys:
                self._tablet_chooser.setCurrentIndex(keys.index(self._tablet_key))
        finally:
            self._tablet_chooser.blockSignals(held)
        return self._feed_replay()

    def _feed_replay(self) -> dict:
        """Draw ``replay_feed`` for the chosen key on the two windows and read
        the retrieval button's text off it."""
        feed = surface.replay_feed(self._tablet_source, self._tablet_key)
        self._replay = feed
        self._vwap_view.set_payload(feed["vwap"])
        self._playback_view.set_payload(feed["playback"])
        self._retrieve_button.setText(feed["button_text"])
        self._retrieve_button.setEnabled(
            bool(self._tablet_key) and not self.retrieval_running()
        )
        return feed

    def _on_tablet_chosen(self, index: int) -> None:
        """The chooser moved: draw the item it names."""
        key = self._tablet_chooser.itemData(index) if index >= 0 else ""
        self._tablet_key = str(key or "")
        self._feed_replay()

    def _follow_bot_tablet(self, bot_id: str = "") -> None:
        """The panel's bot changed: the chooser takes that bot's tablet."""
        del bot_id
        self._refresh_replay(follow_bot=True)

    def _retrieve_tablet(self) -> None:
        """Retrieve Tablet or Update Tablet: one line and nothing started while
        ``retrieval_running`` or with no item chosen; else ``retrieval_span``
        over the chosen item, the started line, and ``_compute_retrieval`` on a
        daemon thread over the read-only connector."""
        if self.retrieval_running():
            self._status_log.log(tab_surface.RETRIEVAL_RUNNING_TEXT, "warning")
            return
        choice = next(
            (
                one
                for one in surface.tablet_choices(
                    self._tablet_source, self._fleet_source.bots()
                )
                if str(one["key"]) == self._tablet_key
            ),
            None,
        )
        if choice is None:
            self._status_log.log(tab_surface.RETRIEVAL_NO_CHOICE_TEXT, "warning")
            return
        entry = self._tablet_source.entry_for(self._tablet_key)
        since_ms, until_ms = tablet_retrieval.retrieval_span(entry)
        if since_ms > until_ms:
            self._status_log.log(
                tab_surface.retrieval_current_line(self._tablet_key, until_ms), "info"
            )
            return
        asset = str(choice["asset"])
        exchange_id = str(choice["exchange_id"])
        year = datetime.fromtimestamp(until_ms / 1000.0, tz=timezone.utc).year
        self._retrieval = {
            "key": self._tablet_key,
            "asset": asset,
            "exchange_id": exchange_id,
            "on_disk": entry is not None,
            "file": tablet_filename(
                asset, tablet_retrieval.TIMEFRAME, year, exchange_id=exchange_id
            ),
            "root": self._tablet_source.root(),
        }
        self._status_log.log(
            tab_surface.retrieval_started_line(
                self._tablet_key,
                asset,
                exchange_id,
                entry is not None,
                since_ms,
                until_ms,
            ),
            "success",
        )
        self._retrieval_thread = threading.Thread(
            target=self._compute_retrieval,
            args=(asset, exchange_id, since_ms, until_ms),
            name="sim-tablet-retrieval",
            daemon=True,
        )
        self._retrieval_thread.start()
        self._retrieve_button.setEnabled(False)

    def _compute_retrieval(
        self, asset: str, exchange_id: str, since_ms: int, until_ms: int
    ) -> None:
        """Run ``tablet_retrieval.retrieve`` over the tablet root and the
        connector and hand the ``RetrievalOutcome`` to the GUI thread through
        ``retrieval_finished``; a walk that raises hands one carrying the error."""
        try:
            outcome = asyncio.run(
                tablet_retrieval.retrieve(
                    self._tablet_source.root(),
                    self._connector,
                    asset,
                    exchange_id,
                    since_ms,
                    until_ms,
                )
            )
        except Exception as exc:  # noqa: BLE001 - the walk runs off-thread
            logger.exception("Stone Tablet retrieval failed: %s", exc)
            outcome = tablet_retrieval.RetrievalOutcome(
                asset=asset,
                exchange_id=exchange_id,
                since_ms=since_ms,
                until_ms=until_ms,
                error=f"{type(exc).__name__}: {exc}",
            )
        self.retrieval_finished.emit(outcome)

    def _on_venue_call(self, call: VenueCall) -> None:
        """The connector's report, on the worker thread: cross to the GUI thread."""
        self.retrieval_call.emit(call)

    def _record_venue_call(self, call: VenueCall) -> None:
        """Record one venue call on ``api_log`` as ``retrieval_api_entry`` and
        write its progress line, on the GUI thread."""
        held = self._retrieval
        key = str(held.get("key") or "")
        self._api_log.record(
            **tab_surface.retrieval_api_entry(
                call,
                key,
                str(held.get("file") or ""),
                held.get("root", ""),
                bool(held.get("on_disk")),
            )
        )
        if not call.error:
            self._status_log.log(tab_surface.retrieval_progress_line(key, call), "info")

    def _take_retrieval(self, outcome) -> None:
        """Write the finished or refused line, point the chooser at the tablet
        now on disk, redraw the two windows and re-read the panel."""
        held = self._retrieval
        key = str(held.get("key") or "")
        self._status_log.log(
            tab_surface.retrieval_finished_line(
                key, outcome, str(held.get("file") or ""), held.get("root", "")
            ),
            "error" if outcome.refused else "success",
        )
        written = surface.tablet_for(
            self._tablet_source,
            outcome.exchange_id,
            outcome.asset,
            tablet_retrieval.TIMEFRAME,
        )
        if written is not None:
            self._tablet_key = tablet_key(written)
        self._refresh_replay()
        self._feed_votes()

    def _create_bot(
        self,
        exchange_id: str = "",
        defaults_override: Optional[dict] = None,
    ) -> None:
        """Open the Simulator's Bot Creation Wizard over ``wizard_exchanges``, the
        stored defaults and the tablet market table; on Finish hand its config
        to ``FleetSource.create`` and fire ``fleet_changed``.

        The window's ``_create_bot``, forked, with no pre-flight, no ``ScrummingBot``
        and no bot manager; ``defaults_override`` merges over the stored defaults.
        """
        self._status_log.log(
            wizard_surface.OPENING_FORMAT.format(exchange_id=exchange_id)
        )
        wizard_class = surface_class(SIM_BOT_WIZARD)
        exchanges = wizard_surface.wizard_exchanges(
            self._exchange_tabs, self._tablet_source
        )
        defaults = wizard_surface.stored_defaults()
        if defaults_override:
            defaults = {**defaults, **defaults_override}
        markets = wizard_surface.tablet_markets(self._tablet_source)
        wizard = wizard_class(exchanges, defaults, self, markets=markets)
        if wizard.exec() != wizard.DialogCode.Accepted:
            self._status_log.log(wizard_surface.CANCELLED_TEXT, "warning")
            return
        config = wizard.get_bot_config()
        logger.info("Sim bot creation config: %s", config)
        if config.get("mode") == EXTRACTOR_MODE:
            reason = wizard_surface.extractor_parent_refusal(
                self._fleet_source.bots(),
                str(config.get("base_currency") or ""),
                str(config.get("exchange_id") or exchange_id),
            )
            if reason is not None:
                QMessageBox.critical(
                    self,
                    wizard_surface.REFUSAL_TITLE,
                    wizard_surface.REFUSAL_BOX_FORMAT.format(reason=reason),
                )
                self._status_log.log(
                    wizard_surface.REFUSED_FORMAT.format(reason=reason), "error"
                )
                return
        try:
            bot = self._fleet_source.create(config)
        except (ValueError, TypeError) as exc:
            self._status_log.log(
                wizard_surface.REJECTED_FORMAT.format(error=exc), "error"
            )
            logger.error("Sim bot creation rejected: %s", exc)
            return
        self._status_log.log(wizard_surface.created_line(bot), "success")
        self.fleet_changed.emit()

    def _on_bot_fire(self, bot_id: str) -> None:
        """Manual Fire on a sim bot: ask ``FleetSource`` to ``fire`` and log the
        refusal to the Activity Log, as the window logs a failed Fire."""
        try:
            self._fleet_source.fire(bot_id)
        except SendRefused as exc:
            self._status_log.log(f"Fire on {bot_id[:8]} failed: {exc}", "error")

    def _notify(self, message: str, level: str) -> None:
        """Write the window notification's line, ``notification_line``, into
        the Activity Log through ``SimStatusLog.notice``."""
        self._status_log.notice(notification_line(message, level))

    def _activity_log_watchdog(self) -> None:
        """One tick of Live's Activity-Log watchdog over ``SimStatusLog`` and
        ``SimBotManager.bots``: each line ``watchdog_lines`` answers is written
        through ``force_log`` and to the file logger."""
        try:
            stats = self._status_log.health_stats()
        except Exception as exc:
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

    def _on_api_event(self, entry: dict) -> None:
        """Append one ``api_log()`` entry to ``_api_log_view`` as Live's block,
        refusing a call off the GUI thread; while ``_api_log_paused`` the
        block goes to ``_api_log_pause_buffer``, the oldest dropped past its
        cap, and the view follows its newest block when already at the bottom.
        """
        current = threading.current_thread().name
        if tab_surface.api_event_off_thread(
            entry, "SimTradingTab._on_api_event", current
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
        forked over ``SimBotManager``, with no venue connect, Live's Activity
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
            except Exception as exc:
                self._status_log.log(f"Failed to start bot {bot_id}: {exc}", "error")
                sound.play_error()

        elif command == "pause":
            self._status_log.log(f"Pausing bot {bot_id}...", "info")
            try:
                moved = self._bot_manager.pause(bot_id) != bot.state
                self._status_log.log(f"Bot {bot_id} paused.", "warning")
                self._notify(f"Bot {bot_id} PAUSED", "warning")
                sound.play_state_change()
            except Exception as exc:
                self._status_log.log(f"Failed to pause bot {bot_id}: {exc}", "error")

        elif command == "stop":
            self._status_log.log(f"Stopping bot {bot_id}...", "info")
            try:
                moved = self._bot_manager.stop(bot_id) != bot.state
                self._status_log.log(f"Bot {bot_id} stopped.", "info")
                self._notify(f"Bot {bot_id} STOPPED", "info")
                sound.play_state_change()
            except Exception as exc:
                self._status_log.log(f"Failed to stop bot {bot_id}: {exc}", "error")

        elif command == "restart":
            try:
                self._bot_manager.restart(bot_id)
                moved = True
                self._status_log.log(f"✓ Bot {bot_id} restarted.", "success")
                self._notify(f"Bot {bot_id} RESTARTED", "success")
                sound.play_state_change()
            except Exception as exc:
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
                except Exception as exc:
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

    def _on_bot_detail(self, bot_id: str) -> None:
        """Open the Simulator's Bot Settings window, ``surface_class(SIM_BOT_DETAIL)``,
        for ``bot_id`` over its ``SimBotView`` and follow Prev and Next over the
        venue's sim fleet, keeping the geometry and the tab."""
        bot = self._fleet_source.bot_for(bot_id)
        if bot is None:
            return
        window_class = surface_class(SIM_BOT_DETAIL)
        saved_geometry = None
        saved_tab_index = None
        while bot is not None:
            siblings = [
                one.bot_id
                for one in self._fleet_source.bots()
                if one.exchange_id == bot.exchange_id
            ]
            rates = usd_rates(self._fleet_source.statuses(bot.exchange_id))
            view = SimBotView(bot, self._fleet_source.record_for(bot.bot_id))
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

    # -- what the operator presses --------------------------------------

    def flip_layer(self) -> str:
        """Swap the stack between the panel layer and the chart layer."""
        self._layer = (
            surface.LAYER_PLAYBACK
            if self._layer == surface.LAYER_INDICATORS
            else surface.LAYER_INDICATORS
        )
        # One button, seated on whichever layer is showing, so the way back
        # is never hidden with the panel.
        if self._layer == surface.LAYER_PLAYBACK:
            self._indicator_panel.header_row().removeWidget(self._flip_button)
            self._chart_header.insertWidget(0, self._flip_button)
        else:
            self._chart_header.removeWidget(self._flip_button)
            self._indicator_panel.header_row().insertWidget(1, self._flip_button)
        self._layer_stack.setCurrentIndex(surface.LAYERS.index(self._layer))
        self._flip_button.setText(surface.FLIP_BUTTON_TEXT[self._layer])
        self._flip_button.show()
        if self._layer == surface.LAYER_PLAYBACK:
            self._refresh_replay()
        return self._layer
