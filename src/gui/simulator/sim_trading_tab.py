"""The Simulator tab in Qt: Live's tab body, forked under the Simulator's name.

``SimTradingTab`` is ``TradingTabMixin._build_trading_tab`` from
``src/gui/main_tabs/trading_tab.py`` as a widget of its own: the exchange layer
stack, the forked ``SimIndicatorVotingPanel``, and the Activity Log and API
Interaction Log spools, in Live's four splitters at Live's sizes.
``add_exchange_tab`` is the window's method of that name, forked, and seats a
``SimExchangeTab``; ``_sync_exchange_tabs`` seats one per exchange
``FleetSource.exchanges`` names, at build and on every ``fleet_changed``, drops
the rest as the window's ``_drop_unlisted_exchange_tabs`` does, and then
``refresh_bots`` hands each venue its rows from ``FleetSource.statuses``; every
``fleet_changed`` first writes the sim fleet file through ``FleetSource.save``. The
corner Live gives ``＋ Add Crypto Exchange`` holds the three way-in buttons, and
the Get Started card holds the same three where Live's card holds its add
button. The replay layer, ``LineView`` over ``PlaybackView``, sits behind the
panel in ``_layer_stack``, reached by ``flip_layer``. A venue's ``+ New Bot``
reaches ``_create_bot``, which opens ``SimBotCreationWizard`` and hands its
config to ``FleetSource.create``. A row's Fire reaches ``_on_bot_fire``, which
asks ``FleetSource`` and logs its refusal; a row's Detail reaches
``_on_bot_detail``, which opens the Simulator's Bot Settings window through
``surface_class(SIM_BOT_DETAIL)`` over a ``SimBotView``. ``TabletSource`` and
``FleetSource`` are the tab's only sources, and neither answers a send.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
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

from ...simulator.fleet_source import (
    EXTRACTOR_MODE,
    FleetSource,
    SendRefused,
)
from ...simulator.sim_bot_view import SimBotView
from ...simulator.tablet_source import TabletSource
from .. import design_system as ds
from ..color_alpha import rgba
from ..main_tabs import simulator_tab_surface as surface
from ..main_tabs.trading_tab_surface import (
    BOTTOM_SPLITTER_SIZES_PX,
    LOG_SPLITTER_SIZES_PX,
    MAIN_SPLITTER_SIZES_PX,
    PLACEHOLDER_TAB_TITLE,
    TOP_SPLITTER_SIZES_PX,
    exchange_display_name,
)
from ..simulator_tab import LineView, PlaybackView
from ..variant_surface import SIM_BOT_DETAIL, SIM_BOT_WIZARD, surface_class
from . import sim_bot_wizard_surface as wizard_surface
from .sim_bot_status_table_surface import usd_rates
from .sim_exchange_tab import SimExchangeTab
from .sim_indicator_panel import SimIndicatorVotingPanel
from .sim_status_log import SimStatusLog
from .sim_trading_tab_surface import (
    card_button_name,
    placeholder_hint_text,
    placeholder_title_text,
)

logger = logging.getLogger("acervator.gui")

PLACEHOLDER_CARD_BORDER_ALPHA = 68

ACCESSIBLE_NAME = "Sim"

#: The three way-in buttons at the corner position, in the order they sit.
WAY_IN_BUTTONS = (
    (surface.IMPORT_LIVE_FLEET_ACTION, surface.IMPORT_LIVE_FLEET_TEXT),
    (surface.GENERATE_FROM_YTD_ACTION, surface.GENERATE_FROM_YTD_TEXT),
    (surface.CREATE_NEW_BOTS_ACTION, surface.CREATE_NEW_BOTS_TEXT),
)

FLIP_BUTTON_NAME = "sim-flip-button"

#: Live's corner button is 24 px tall: its ＋ glyph sets that height, and the
#: way-in buttons carry no such glyph.
WAY_IN_BUTTON_HEIGHT_PX = 24


class FlipButton(QPushButton):
    """A ``QPushButton`` named ``FLIP_BUTTON_NAME`` whose layout may shrink it to width 0."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName(FLIP_BUTTON_NAME)
        self.setAccessibleName(FLIP_BUTTON_NAME)
        self.setSizePolicy(QSizePolicy.Preferred, self.sizePolicy().verticalPolicy())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """The base hint's height over a width of 0."""
        return QSize(0, super().minimumSizeHint().height())


class SimTradingTab(QWidget):
    """The Sim tab: Live's tab body over the Simulator's two sources."""

    #: Fired by whatever loads a fleet; the venue sub-tabs re-seat on it.
    fleet_changed = Signal()

    def __init__(
        self,
        tablet_source: Optional[TabletSource] = None,
        fleet_source: Optional[FleetSource] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(ACCESSIBLE_NAME)
        self.setAccessibleName(ACCESSIBLE_NAME)
        self._tablet_source = (
            tablet_source
            if tablet_source is not None
            else TabletSource(surface.TABLET_ROOT)
        )
        self._fleet_source = fleet_source if fleet_source is not None else FleetSource()
        self._layer = surface.LAYER_INDICATORS
        self._build()
        self.fleet_changed.connect(self._fleet_source.save)
        self.fleet_changed.connect(self._sync_exchange_tabs)
        self._sync_exchange_tabs()

    # -- what the window reads ------------------------------------------

    def tablet_source(self) -> TabletSource:
        """The tablet reader the panel is fed from."""
        return self._tablet_source

    def fleet_source(self) -> FleetSource:
        """The fleet reader the tables are fed from."""
        return self._fleet_source

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

        def _make_layer(label_text: str, accent: str) -> tuple:
            """Build one trading layer — returns (page_widget, tab_widget,
            exchange_tabs_dict, placeholder_widget)."""
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)

            tab_w = QTabWidget()
            # The corner Live gives ＋ Add Crypto Exchange holds the three
            # way-in buttons; their handlers arrive in later units.
            corner = QWidget()
            corner_row = QHBoxLayout(corner)
            corner_row.setContentsMargins(0, 0, 0, 0)
            corner_row.setSpacing(2)
            for action, text in WAY_IN_BUTTONS:
                way_in = QPushButton(text)
                way_in.setMinimumWidth(140)
                way_in.setMinimumHeight(WAY_IN_BUTTON_HEIGHT_PX)
                way_in.setAccessibleName(surface.button_name(action))
                corner_row.addWidget(way_in)
                self._way_in_buttons.setdefault(action, way_in)
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
            # The card's button position holds the three way-ins, one under
            # the other, each at Live's card-button size and sheet.
            for action, text in WAY_IN_BUTTONS:
                ph_way_in = QPushButton(text)
                ph_way_in.setMinimumSize(180, 36)
                ph_way_in.setStyleSheet(
                    f"QPushButton {{ border: 1px solid {accent}; "
                    f"color: {accent}; border-radius: 4px; }}"
                )
                ph_way_in.setAccessibleName(card_button_name(action))
                ph_layout.addWidget(ph_way_in, alignment=Qt.AlignCenter)
                self._card_way_in_buttons.setdefault(action, ph_way_in)
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
        self._flip_button = FlipButton(surface.FLIP_BUTTON_TEXT[surface.LAYER_INDICATORS])
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
        # The pane's writer reads this flag; QPlainTextEdit has no SimStatusLog subclass.
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
        """The replay layer: a header row for the flip button over ``LineView``
        and ``PlaybackView`` in one splitter."""
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        # The same margins as the panel's header, so the flip button keeps
        # its row when it moves here.
        self._chart_header = QHBoxLayout()
        self._chart_header.setContentsMargins(4, 2, 4, 2)
        self._chart_header.addStretch()
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
            on_bot_fire=self._on_bot_fire,
            status_log=self._status_log,
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

    def _create_bot(
        self,
        exchange_id: str = "",
        defaults_override: Optional[dict] = None,
    ) -> None:
        """Open the Simulator's Bot Creation Wizard over the seated venues, the
        stored defaults and the tablet market table; on Finish hand its config
        to ``FleetSource.create`` and fire ``fleet_changed``.

        The window's ``_create_bot``, forked, with no pre-flight, no ``ScrummingBot``
        and no bot manager; ``defaults_override`` merges over the stored defaults.
        """
        self._status_log.log(
            wizard_surface.OPENING_FORMAT.format(exchange_id=exchange_id)
        )
        wizard_class = surface_class(SIM_BOT_WIZARD)
        exchanges = wizard_surface.seated_exchanges(self._exchange_tabs)
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
        return self._layer
