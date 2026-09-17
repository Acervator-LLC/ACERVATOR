"""The Simulator's bot detail window, forked from ``bot_live_settings``.

``SimBotDetailDialog`` is the frame of ``BotLiveSettingsDialog`` under the
Simulator's name over one ``SimBot`` and the ``row_status`` its row was drawn
from: the title, the header with the pair, the mode and the state badge, Prev
and Next over ``sibling_ids``, the Status tab of ``StatusTabMixin`` over that
status, and Close. It edits nothing and holds no bot manager; the six tabs
that read a live bot's runtime state are not forked.
"""

from __future__ import annotations

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
from ...simulator.fleet_source import SimBot
from .. import design_system as ds
from ..main_tabs import bot_live_settings_surface as surface
from ..main_tabs.live_status_tab_surface import (
    age_text,
    money_color,
    realised_tooltip,
)

ACCESSIBLE_NAME = "Sim Bot Detail"

PENDING_TEXT = "— (refresh pending)"
PENDING_TIP = "No exchange figures are stored for this bot."
NO_PRICE_TEXT = "—"
LAST_ERROR_MAX_CHARS = 80


class SimBotDetailDialog(QDialog):
    """Live's Bot Settings frame over one ``SimBot``, read only."""

    def __init__(
        self,
        bot: SimBot,
        status: dict,
        sibling_ids: list,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bot = bot
        self._status = dict(status)
        self._sibling_ids = [str(one) for one in sibling_ids]
        # The host reads this after exec() returns, as the window does.
        self._pending_navigate_to: str | None = None
        self.setAccessibleName(ACCESSIBLE_NAME)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the header, the Status tab and the footer."""
        bot = self._bot
        self.setWindowTitle(surface.window_title(bot.symbol, bot.bot_id))
        self.setMinimumSize(surface.MINIMUM_W_PX, surface.MINIMUM_H_PX)

        layout = QVBoxLayout(self)

        hdr_row = QHBoxLayout()
        hdr = QLabel(surface.header_text(bot.symbol, bot.mode))
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
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton(surface.CLOSE_LABEL)
        close_btn.setStyleSheet(surface.CLOSE_STYLE)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        if can_nav:
            for keys, step in surface.SHORTCUTS:
                shortcut = QShortcut(QKeySequence(keys), self)
                shortcut.activated.connect(
                    lambda step=step: self._navigate_to_sibling(step)
                )

        self.open_at_content_size()

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
