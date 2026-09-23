"""The Paper Trader's Bot Settings window, forked from ``bot_live_settings``.

``PaperBotDetailDialog`` is ``BotLiveSettingsDialog`` under the Paper Trader's name
over one ``PaperBotView``: the title, the header with the pair, the mode and the
state badge, Prev and Next over ``sibling_ids``, the tabs Live gives the
bot's mode from the seven forked mixins, Apply Changes, Close and the
pending-change line. ``_mark_changed`` records an edit as Live records it;
``_apply_changes`` asks the view for every pending field, and the view raises
``SendRefused`` for each, so the pending line reads ``refused_text`` and
nothing is written.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.fmt import fmt_price
from ...paper.paper_bot_view import PaperBotView
from ...paper.fleet_source import SendRefused
from .. import design_system as ds
from ..main_tabs import bot_live_settings_surface as surface
from ..main_tabs.live_status_tab_surface import (
    age_text,
    money_color,
    realised_tooltip,
)
from . import paper_bot_live_settings_surface as paper_surface
from .paper_bot_swarm_tab import PaperBotSwarmTabMixin
from .paper_fold_tranches_tab import PaperFoldTranchesTabMixin
from .paper_market_inspector_tab import PaperMarketInspectorTabMixin
from .paper_phantom_bots_tab import PaperPhantomBotsTabMixin
from .paper_positions_held_tab import PaperPositionsHeldTabMixin
from .paper_settings_tab import PaperSettingsTabMixin
from .paper_stack_tranches_tab import PaperStackTranchesTabMixin

logger = logging.getLogger(surface.LOGGER_NAME)

ACCESSIBLE_NAME = "Paper Bot Detail"

#: Written when the window opens: the bot, the tab count and the tab names.
OPENED_LOG = "Paper Bot Settings opened for %s: %d tab(s): %s"

PENDING_TEXT = "— (refresh pending)"
PENDING_TIP = "No exchange figures are stored for this bot."
NO_PRICE_TEXT = "—"
LAST_ERROR_MAX_CHARS = 80


class PaperBotDetailDialog(
    PaperBotSwarmTabMixin,
    PaperFoldTranchesTabMixin,
    PaperMarketInspectorTabMixin,
    PaperPhantomBotsTabMixin,
    PaperPositionsHeldTabMixin,
    PaperSettingsTabMixin,
    PaperStackTranchesTabMixin,
    QDialog,
):
    """Live's Bot Settings window over one ``PaperBotView``; every write refused."""

    _fold_sort_key: str = surface.FOLD_SORT_QUEUE_ORDER

    def __init__(
        self,
        bot: PaperBotView,
        sibling_ids: list,
        parent: QWidget | None = None,
        rates: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self._bot = bot
        self._bm = None
        self._status = dict(bot.get_status())
        self._sibling_ids = [str(one) for one in sibling_ids]
        self._denom_rates = dict(rates or {})
        self._changes: dict = {}
        # The host reads this after exec() returns, as the window does.
        self._pending_navigate_to: str | None = None
        self.setAccessibleName(ACCESSIBLE_NAME)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the header, the tabs the bot's mode is given and the footer."""
        bot = self._bot
        cfg = bot.config
        mode = cfg.mode.value
        self.setWindowTitle(surface.window_title(cfg.symbol, bot.bot_id))
        self.setMinimumSize(surface.MINIMUM_W_PX, surface.MINIMUM_H_PX)

        layout = QVBoxLayout(self)

        hdr_row = QHBoxLayout()
        hdr = QLabel(surface.header_text(cfg.symbol, mode))
        hdr.setStyleSheet(
            surface.HEADER_STYLE_FORMAT.format(color_hex=surface.HEADER_COLOR)
        )
        hdr_row.addWidget(hdr)

        state_lbl = QLabel(surface.state_text(bot.state))
        state_lbl.setStyleSheet(surface.state_style(bot.state))
        hdr_row.addWidget(state_lbl)
        hdr_row.addStretch()

        self._prev_btn = QPushButton(surface.PREV_LABEL)
        self._prev_btn.setStyleSheet(surface.NAV_BUTTON_STYLE)
        self._prev_btn.setToolTip(surface.PREV_TOOLTIP)
        self._prev_btn.clicked.connect(
            lambda: self._navigate_to_sibling(surface.PREV_STEP)
        )
        hdr_row.addWidget(self._prev_btn)

        self._next_btn = QPushButton(surface.NEXT_LABEL)
        self._next_btn.setStyleSheet(surface.NAV_BUTTON_STYLE)
        self._next_btn.setToolTip(surface.NEXT_TOOLTIP)
        self._next_btn.clicked.connect(
            lambda: self._navigate_to_sibling(surface.NEXT_STEP)
        )
        hdr_row.addWidget(self._next_btn)

        can_nav = len(self._sibling_ids) >= surface.NAV_NEEDS_SIBLINGS
        self._prev_btn.setVisible(can_nav)
        self._next_btn.setVisible(can_nav)
        layout.addLayout(hdr_row)

        tabs = QTabWidget()
        self._tabs = tabs
        tabs.addTab(
            self._wrap_scrollable(self._create_status_tab()), surface.TAB_STATUS
        )
        tabs.addTab(
            self._wrap_scrollable(self._create_settings_tab()), surface.TAB_SETTINGS
        )
        if mode == surface.MODE_SCRUMMING:
            self._install_fold_tranches_tab(tabs)
            self._install_stack_tranches_tab(tabs)
            tabs.addTab(
                self._wrap_scrollable(self._create_bot_swarm_tab()),
                surface.TAB_BOT_SWARM,
            )
            tabs.addTab(
                self._wrap_scrollable(self._create_market_inspector_tab()),
                surface.TAB_MARKET_INSPECTOR,
            )
            tabs.addTab(
                self._wrap_scrollable(self._create_phantom_bots_tab()),
                surface.TAB_PHANTOM_BOTS,
            )
        if mode == surface.MODE_EXTRACTOR:
            tabs.addTab(
                self._wrap_scrollable(self._create_positions_held_tab()),
                surface.TAB_POSITIONS_HELD,
            )
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._apply_btn = QPushButton(surface.APPLY_LABEL)
        self._apply_btn.setStyleSheet(surface.APPLY_STYLE)
        self._apply_btn.setEnabled(surface.APPLY_ENABLED_AT_START)
        self._apply_btn.clicked.connect(self._apply_changes)
        btn_row.addWidget(self._apply_btn)

        close_btn = QPushButton(surface.CLOSE_LABEL)
        close_btn.setStyleSheet(surface.CLOSE_STYLE)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._change_lbl = QLabel(surface.CHANGE_EMPTY_TEXT)
        self._change_lbl.setStyleSheet(surface.CHANGE_PENDING_STYLE)
        layout.addWidget(self._change_lbl)

        if can_nav:
            for keys, step in surface.SHORTCUTS:
                shortcut = QShortcut(QKeySequence(keys), self)
                shortcut.activated.connect(
                    lambda step=step: self._navigate_to_sibling(step)
                )

        self.open_at_content_size()
        self._log_opened([tabs.tabText(i) for i in range(tabs.count())])

    def _log_opened(self, names: list) -> None:
        """One line naming the bot and the tabs, ``OPENED_LOG``."""
        logger.info(OPENED_LOG, self._bot.bot_id[:8], len(names), ", ".join(names))

    def _create_status_tab(self) -> QWidget:
        """The read-only Statistics form over the row's ``stats``."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(6)

        stats = self._status.get("stats", {}) or {}

        stats_group = QGroupBox("Statistics")
        sf = QFormLayout(stats_group)
        self._configure_form(sf)

        realised = float(stats.get("realized_pnl_exchange", 0.0) or 0.0)
        avg_entry = float(stats.get("avg_entry_exchange", 0.0) or 0.0)
        cost_basis = float(stats.get("cost_basis_total_exchange", 0.0) or 0.0)
        unrealised = float(stats.get("unrealised_pnl", 0.0) or 0.0)
        fees = float(stats.get("fees_paid_exchange", 0.0) or 0.0)
        trade_count = int(stats.get("exchange_trade_count", 0) or 0)
        fresh_ts = float(stats.get("exchange_data_fresh_ts", 0.0) or 0.0)

        if fresh_ts > 0:
            age = age_text(time.time() - fresh_ts)
            rep_lbl = QLabel(f"${realised:+,.4f}")
            rep_lbl.setStyleSheet(
                f"font-weight: bold; font-size: 13px; color: {money_color(realised)};"
            )
            rep_lbl.setToolTip(realised_tooltip(trade_count, age))
            sf.addRow("Realised P/L:", rep_lbl)
            if unrealised != 0:
                ue_lbl = QLabel(f"${unrealised:+,.4f}")
                ue_lbl.setStyleSheet(f"color: {money_color(unrealised)};")
                sf.addRow("Unrealised P/L:", ue_lbl)
            if avg_entry > 0:
                sf.addRow("Avg Entry (exchange):", QLabel(f"${avg_entry:.8f}"))
                sf.addRow("Cost Basis Total:", QLabel(f"${cost_basis:,.4f}"))
            if fees > 0:
                sf.addRow("Fees Paid:", QLabel(f"${fees:,.4f}"))
        else:
            pending_lbl = QLabel(PENDING_TEXT)
            pending_lbl.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL};")
            pending_lbl.setToolTip(PENDING_TIP)
            sf.addRow("Realised P/L:", pending_lbl)

        sf.addRow("Total Trades:", QLabel(str(stats.get("total_trades", 0))))
        sf.addRow("Active Buys:", QLabel(str(stats.get("active_buys", 0))))
        sf.addRow("Active Sells:", QLabel(str(stats.get("active_sells", 0))))

        price = float(stats.get("current_price", 0) or 0)
        sf.addRow(
            "Current Price:", QLabel(fmt_price(price) if price > 0 else NO_PRICE_TEXT)
        )
        sf.addRow("Uptime:", QLabel(f"{float(stats.get('uptime', 0) or 0):.0f}s"))

        if stats.get("last_error"):
            err = QLabel(str(stats["last_error"])[:LAST_ERROR_MAX_CHARS])
            err.setStyleSheet(f"color: {ds.ERROR};")
            err.setWordWrap(True)
            sf.addRow("Last Error:", err)
        layout.addWidget(stats_group)
        layout.addStretch()
        return w

    def _wrap_scrollable(self, content: QWidget) -> QScrollArea:
        """``content`` inside a frameless, resizable ``QScrollArea``."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(surface.SCROLL_RESIZABLE)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _configure_form(self, form: QFormLayout) -> None:
        """Live's row-sizing defaults on ``form``."""
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setHorizontalSpacing(surface.FORM_HORIZONTAL_SPACING_PX)
        form.setVerticalSpacing(surface.FORM_VERTICAL_SPACING_PX)
        form.setContentsMargins(*surface.FORM_MARGINS_PX)

    def _mark_changed(self, field: str, value) -> None:
        """Record one edited field and enable Apply, as Live records it."""
        if field == surface.PHANTOM_ENABLE_FIELD:
            original = getattr(self._bot, surface.PHANTOM_ENABLE_ATTRIBUTE, None)
        elif field == surface.PHANTOM_TIMEFRAMES_FIELD:
            original = list(
                getattr(self._bot, surface.PHANTOM_TIMEFRAMES_ATTRIBUTE, [])
            )
            value = list(value)
        elif field == surface.PHANTOM_LOCK_FIELD:
            coord = getattr(self._bot, surface.COORDINATOR_ATTRIBUTE, None)
            original = (
                getattr(coord, surface.COORDINATOR_LOCK_ATTRIBUTE, None)
                if coord
                else None
            )
        else:
            original = getattr(self._bot.config, field, None)

        if value == original:
            self._changes.pop(field, None)
        else:
            self._changes[field] = value

        if self._changes:
            self._apply_btn.setEnabled(True)
            self._change_lbl.setText(surface.pending_text(self._changes.keys()))
        else:
            self._apply_btn.setEnabled(False)
            self._change_lbl.setText(surface.CHANGE_EMPTY_TEXT)

    def _apply_changes(self) -> None:
        """Ask the view for every pending field; each is refused and logged."""
        if not self._changes:
            return
        refused = []
        for field, value in list(self._changes.items()):
            try:
                self._route_change(field, value)
            except SendRefused as exc:
                logger.warning(
                    surface.ROUTE_REFUSED_LOG, self._bot.bot_id[:8], field, exc
                )
                refused.append(
                    surface.APPLIED_REFUSED_FORMAT.format(
                        field=field, value=value, reason=exc
                    )
                )
        logger.info(
            surface.APPLIED_LOG,
            self._bot.bot_id[:8],
            surface.APPLIED_JOIN.join(refused),
        )
        self._changes.clear()
        self._apply_btn.setEnabled(False)
        self._change_lbl.setText(paper_surface.refused_text(len(refused)))
        self._change_lbl.setStyleSheet(paper_surface.CHANGE_REFUSED_STYLE)

    def _route_change(self, field: str, value) -> None:
        """Send one field the way Live routes it; every route raises."""
        if field in surface.PHANTOM_FIELDS:
            self._bot.update_phantom_config(**{field: value})
            return
        route = surface.RUNTIME_ROUTED.get(field)
        if route:
            getattr(self._bot, route)(value)
            return
        self._bot.set_config_field(field, value)

    def _bot_manager_for_save(self) -> object | None:
        """No bot manager is attached to the Paper Trader's window."""
        return None

    def _save_fleet_state_now(self, what: str) -> tuple[bool, str]:
        """No fleet is saved from the Paper Trader's window: ``NO_MANAGER_REASON``."""
        del what
        return (False, surface.NO_MANAGER_REASON)

    @staticmethod
    def _format_age(seconds: float) -> str:
        """``surface.format_age`` for the tranche tabs' age rows."""
        return surface.format_age(seconds)

    def _tab_pages(self) -> list:
        """One ``(content size, page size)`` pair per tab, each polished first."""
        pages = []
        for index in range(self._tabs.count()):
            page = self._tabs.widget(index)
            if page is None:
                continue
            page.ensurePolished()
            content = page.widget() if isinstance(page, QScrollArea) else None
            if content is None:
                content = page
            content.ensurePolished()
            chint = content.sizeHint()
            phint = page.sizeHint()
            pages.append(
                ((chint.width(), chint.height()), (phint.width(), phint.height()))
            )
        return pages

    def open_at_content_size(
        self, available: tuple[int, int] | None = None
    ) -> tuple[int, int]:
        """Resize so the largest tab fits inside ``available``, and report the size."""
        content_w, content_h, page_w, page_h = surface.tab_content_demand_px(
            self._tab_pages()
        )
        hint = self.layout().sizeHint()
        needed_w, needed_h = surface.dialog_content_size_px(
            hint.width(), hint.height(), page_w, page_h, content_w, content_h
        )
        if available is None:
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen is None:
                available = (needed_w, needed_h)
            else:
                size = screen.availableGeometry()
                available = (size.width(), size.height())
        width, height = surface.dialog_open_size_px(
            needed_w,
            needed_h,
            available[0],
            available[1],
            self.minimumWidth(),
            self.minimumHeight(),
        )
        self.resize(width, height)
        return width, height

    def _navigate_to_sibling(self, direction: int) -> None:
        """Stage the next or previous bot of ``sibling_ids`` and close."""
        ids = self._sibling_ids
        if len(ids) < surface.NAV_NEEDS_SIBLINGS:
            return
        try:
            cur_idx = ids.index(self._bot.bot_id)
        except ValueError:
            cur_idx = 0 if direction > 0 else 1
        self._pending_navigate_to = ids[(cur_idx + direction) % len(ids)]
        self.accept()

    def active_tab_index(self) -> int:
        """The index of the tab showing, so the next bot opens on it."""
        return int(self._tabs.currentIndex())

    def status(self) -> dict:
        """A copy of the row status this window was drawn from."""
        return dict(self._status)
