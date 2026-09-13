"""Live Bot Settings dialog.

``BotLiveSettingsDialog`` opens from the Detail button on a running bot and
edits its configuration while the bot runs.
"""

from __future__ import annotations

import logging

from . import design_system as ds
from .color_alpha import rgba
from .live_settings.fold_tokens import (
    ARBITER_COLUMN_HEADER,
    ARBITER_COLUMN_INDEX,
    ARBITER_NOT_APPLICABLE,
    EXTRACTOR_TRANCHE_BG_HEX,
    EXTRACTOR_TRANCHE_BORDER_HEX,
    EXTRACTOR_TRANCHE_FG_HEX,
    FOLD_CLOSED_TOOLTIP,
    FOLD_CLOSE_RATIO_TOOLTIP,
    FOLD_COLUMN_TOOLTIPS,
    FOLD_COUNTERS_RESET_TOOLTIP,
    FOLD_CYCLE_CAP_TOOLTIP,
    FOLD_DISCARDED_TOOLTIP,
    FOLD_FILTER_PLACEHOLDER,
    FOLD_FILTER_TOOLTIP,
    FOLD_MALFORMED_TOOLTIP,
    FOLD_OLDEST_AGE_TOOLTIP,
    FOLD_OPENED_TOOLTIP,
    FOLD_OPEN_COUNT_TOOLTIP,
    FOLD_OVER_ALLOTMENT_FG_HEX,
    FOLD_PARKED_USD_TOOLTIP,
    FOLD_RATIO_AMBER_FG_HEX,
    FOLD_RATIO_GREEN_FG_HEX,
    FOLD_RATIO_RED_FG_HEX,
    FOLD_SORT_KEYS,
    FOLD_SORT_LARGEST_FIRST,
    FOLD_SORT_NEWEST_FIRST,
    FOLD_SORT_OLDEST_FIRST,
    FOLD_SORT_ORDERS,
    FOLD_SORT_QUEUE_ORDER,
    FOLD_SORT_SMALLEST_FIRST,
    FOLD_SORT_TOOLTIP,
    FOLD_SOURCE_AUTO_REBALANCE,
    FOLD_SOURCE_AUTO_SCRUM,
    FOLD_SOURCE_MANUAL_FG_HEX,
    FOLD_SOURCE_MANUAL_SCRUM,
    FOLD_SOURCE_TOOLTIPS,
    FOLD_TRANCHE_BG_HEX,
    FOLD_TRANCHE_BORDER_HEX,
    FOLD_TRANCHE_FG_HEX,
    FOLD_UNITS_MARKED_TOOLTIP,
    FOLD_WIRE_DISCARDED_TOOLTIP,
    TRANCHE_FIRE_BTN_INSET_PX,
    TRANCHE_ROW_BORDER_BY_BG,
    TRANCHE_ROW_BORDER_PX,
    TRANCHE_ROW_HEIGHT_PX,
    TRANCHE_TABLE_FRAME_PX,
    TRANCHE_TABLE_HEADER_PX,
    TRANCHE_TABLE_VISIBLE_ROWS,
    _arbiter_label,
    _compose_arbiter_tooltip,
    _compose_extractor_tranche_cells,
    _compose_extractor_tranche_tooltip,
    _fold_tranche_source_label,
    _format_tranche_age,
    compose_cycle_close_ratio,
    compose_units_marked_row,
    fold_display_order,
    fold_row_matches_filter,
    fold_table_chrome_px,
    fold_table_max_height_px,
    fold_table_natural_width_px,
    install_health_row,
)
from .live_settings.denom_rows import _compose_denom_row_text

__all__ = [
    "ARBITER_COLUMN_HEADER",
    "ARBITER_COLUMN_INDEX",
    "ARBITER_NOT_APPLICABLE",
    "BotLiveSettingsDialog",
    "BotSwarmTabMixin",
    "DESPAWN_ROW_TOOLTIP",
    "DIALOG_SCREEN_MARGIN_H_PX",
    "DIALOG_SCREEN_MARGIN_W_PX",
    "EXTRACTOR_TRANCHE_BG_HEX",
    "EXTRACTOR_TRANCHE_BORDER_HEX",
    "EXTRACTOR_TRANCHE_FG_HEX",
    "FOLD_CLOSED_TOOLTIP",
    "FOLD_CLOSE_RATIO_TOOLTIP",
    "FOLD_COLUMN_TOOLTIPS",
    "FOLD_COUNTERS_RESET_TOOLTIP",
    "FOLD_CYCLE_CAP_TOOLTIP",
    "FOLD_DISCARDED_TOOLTIP",
    "FOLD_FILTER_PLACEHOLDER",
    "FOLD_FILTER_TOOLTIP",
    "FOLD_MALFORMED_TOOLTIP",
    "FOLD_OLDEST_AGE_TOOLTIP",
    "FOLD_OPENED_TOOLTIP",
    "FOLD_OPEN_COUNT_TOOLTIP",
    "FOLD_OVER_ALLOTMENT_FG_HEX",
    "FOLD_PARKED_USD_TOOLTIP",
    "FOLD_RATIO_AMBER_FG_HEX",
    "FOLD_RATIO_GREEN_FG_HEX",
    "FOLD_RATIO_RED_FG_HEX",
    "FOLD_SORT_KEYS",
    "FOLD_SORT_LARGEST_FIRST",
    "FOLD_SORT_NEWEST_FIRST",
    "FOLD_SORT_OLDEST_FIRST",
    "FOLD_SORT_ORDERS",
    "FOLD_SORT_QUEUE_ORDER",
    "FOLD_SORT_SMALLEST_FIRST",
    "FOLD_SORT_TOOLTIP",
    "FOLD_SOURCE_AUTO_REBALANCE",
    "FOLD_SOURCE_AUTO_SCRUM",
    "FOLD_SOURCE_MANUAL_FG_HEX",
    "FOLD_SOURCE_MANUAL_SCRUM",
    "FOLD_SOURCE_TOOLTIPS",
    "FOLD_TRANCHE_BG_HEX",
    "FOLD_TRANCHE_BORDER_HEX",
    "FOLD_TRANCHE_FG_HEX",
    "FOLD_UNITS_MARKED_TOOLTIP",
    "FOLD_WIRE_DISCARDED_TOOLTIP",
    "FoldTranchesTabMixin",
    "MarketInspectorTabMixin",
    "PhantomBotsTabMixin",
    "PositionsHeldTabMixin",
    "SettingsTabMixin",
    "StackTranchesTabMixin",
    "StatusTabMixin",
    "TRANCHE_FIRE_BTN_INSET_PX",
    "TRANCHE_ROW_BORDER_BY_BG",
    "TRANCHE_ROW_BORDER_PX",
    "TRANCHE_ROW_HEIGHT_PX",
    "TRANCHE_TABLE_FRAME_PX",
    "TRANCHE_TABLE_HEADER_PX",
    "TRANCHE_TABLE_VISIBLE_ROWS",
    "_TrancheRowBorderDelegate",
    "_arbiter_label",
    "_compose_arbiter_tooltip",
    "_compose_denom_row_text",
    "_compose_extractor_tranche_cells",
    "_compose_extractor_tranche_tooltip",
    "_fold_tranche_source_label",
    "_format_tranche_age",
    "build_fold_row_controls",
    "compose_cycle_close_ratio",
    "compose_units_marked_row",
    "despawn_preview_text",
    "despawn_timer_text",
    "dialog_content_size_px",
    "dialog_open_size_px",
    "fold_display_order",
    "fold_row_matches_filter",
    "fold_sort_order",
    "fold_table_chrome_px",
    "fold_table_max_height_px",
    "fold_table_natural_width_px",
    "install_despawn_rows",
    "install_health_row",
    "on_fold_filter_changed",
    "on_fold_sort_changed",
    "pin_despawn_rows",
    "tab_content_demand_px",
]

logger = logging.getLogger("acervator.gui")

STATE_BACKGROUND_ALPHA = 34

try:
    from PySide6.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QFormLayout,
        QPushButton,
        QTabWidget,
        QWidget,
        QFrame,
        QScrollArea,
    )
    from PySide6.QtCore import Signal
    from PySide6.QtGui import QGuiApplication

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


#: Screen pixels left clear of the dialog; the window frame sits outside this size.
DIALOG_SCREEN_MARGIN_W_PX = 32
DIALOG_SCREEN_MARGIN_H_PX = 72


def tab_content_demand_px(tabs: QTabWidget) -> tuple[int, int, int, int]:
    """`(content_w, content_h, page_w, page_h)` across every tab.

    `content_*` reads the widget INSIDE each `QScrollArea`; `page_*`
    reads the scroll area itself. On the Fold Tranches tab the two
    disagree by 1475px of width, and that gap is the whole defect.

    `ensurePolished` BEFORE EVERY READ. An unpolished widget answers
    `frameWidth() == 1` where the same widget polished answers 13, so a
    hint taken before the theme resolves is measuring a different
    widget.
    """
    content_w = content_h = page_w = page_h = 0
    for index in range(tabs.count()):
        page = tabs.widget(index)
        if page is None:
            continue
        page.ensurePolished()
        content = page.widget() if isinstance(page, QScrollArea) else None
        if content is None:
            content = page
        content.ensurePolished()
        chint = content.sizeHint()
        phint = page.sizeHint()
        content_w = max(content_w, chint.width())
        content_h = max(content_h, chint.height())
        page_w = max(page_w, phint.width())
        page_h = max(page_h, phint.height())
    return content_w, content_h, page_w, page_h


def dialog_content_size_px(
    dialog_hint_w: int,
    dialog_hint_h: int,
    page_w: int,
    page_h: int,
    content_w: int,
    content_h: int,
) -> tuple[int, int]:
    """The dialog size that puts `content` inside the tab viewport.

    `dialog_hint - page` is the chrome the dialog's layout draws around
    its largest tab page — margins, tab bar, header row, button row —
    measured at 70px across and 162px down. It over-charges by whatever
    a non-tab row is wider than that page; erring large is correct for
    a floor, and here that error is 44px.
    """
    return (
        int(content_w) + int(dialog_hint_w) - int(page_w),
        int(content_h) + int(dialog_hint_h) - int(page_h),
    )


def dialog_open_size_px(
    needed_w: int,
    needed_h: int,
    available_w: int,
    available_h: int,
    minimum_w: int,
    minimum_h: int,
) -> tuple[int, int]:
    """The size the dialog opens at: content, capped by the screen.

    A window larger than the display is worse than one too small — the
    operator cannot drag back the part that hangs off the edge. The cap
    never falls below the dialog's own minimum, because Qt enforces
    that minimum whatever this returns; on a display smaller than
    640x720 the minimum is what wins, and it always did.
    """
    ceiling_w = max(int(minimum_w), int(available_w) - DIALOG_SCREEN_MARGIN_W_PX)
    ceiling_h = max(int(minimum_h), int(available_h) - DIALOG_SCREEN_MARGIN_H_PX)
    return (
        min(max(int(needed_w), int(minimum_w)), ceiling_w),
        min(max(int(needed_h), int(minimum_h)), ceiling_h),
    )


if _HAS_QT:
    from .live_settings.fold_chrome import (
        DESPAWN_ROW_TOOLTIP,
        _TrancheRowBorderDelegate,
        build_fold_row_controls,
        despawn_preview_text,
        despawn_timer_text,
        fold_sort_order,
        install_despawn_rows,
        on_fold_filter_changed,
        on_fold_sort_changed,
        pin_despawn_rows,
    )
    from .live_settings.bot_swarm_tab import BotSwarmTabMixin
    from .live_settings.fold_tranches_tab import FoldTranchesTabMixin
    from .live_settings.market_inspector_tab import MarketInspectorTabMixin
    from .live_settings.phantom_bots_tab import PhantomBotsTabMixin
    from .live_settings.positions_held_tab import PositionsHeldTabMixin
    from .live_settings.settings_tab import SettingsTabMixin
    from .live_settings.stack_tranches_tab import StackTranchesTabMixin
    from .live_settings.status_tab import StatusTabMixin

    class BotLiveSettingsDialog(
        BotSwarmTabMixin,
        FoldTranchesTabMixin,
        MarketInspectorTabMixin,
        PhantomBotsTabMixin,
        PositionsHeldTabMixin,
        SettingsTabMixin,
        StackTranchesTabMixin,
        StatusTabMixin,
        QDialog,
    ):
        """Editable bot detail dialog for running bots.

        The Status tab is read-only; the Settings tab applies each edited
        config field immediately.
        """

        settings_changed = Signal(str, dict)  # bot_id, {field: new_value}

        # A class default, so a stub dialog that never runs __init__ still reads it.
        _fold_sort_key: str = FOLD_SORT_QUEUE_ORDER

        def __init__(self, bot, bot_manager=None, parent=None):
            super().__init__(parent)
            self._bot = bot
            self._bm = bot_manager
            self._changes: dict = {}
            # main_window._on_bot_clicked reads this after exec() returns.
            self._pending_navigate_to: str | None = None
            self._setup_ui()

        def _setup_ui(self) -> None:
            """Build the header, the tabs the bot's mode is given and the footer."""
            bot = self._bot
            cfg = bot.config
            bid = bot.bot_id
            self.setWindowTitle(f"Bot Settings — {cfg.symbol} [{bid[:8]}]")
            # Qt cannot paint a spin box or combo box below about 24px tall.
            self.setMinimumSize(640, 720)

            layout = QVBoxLayout(self)

            # Header
            hdr_row = QHBoxLayout()
            hdr = QLabel(f"{cfg.symbol}  •  {cfg.mode.value.upper()}")
            hdr.setStyleSheet(
                f"font-size: 18px; font-weight: bold; color: {ds.PRIMARY};"
            )
            hdr_row.addWidget(hdr)

            state = bot.state.value
            state_colors = {
                "running": ds.SUCCESS,
                "idle": ds.CARD_METRIC_LABEL,
                "paused": ds.WARNING,
                "error": ds.ERROR,
                "stopped": ds.TEXT_MUTED,
                "cooldown": ds.WARNING,
            }
            state_colour = state_colors.get(state, ds.TEXT_NEUTRAL)
            state_lbl = QLabel(f"  {state.upper()}")
            state_lbl.setStyleSheet(
                f"font-size: 14px; font-weight: bold; "
                f"color: {state_colour}; "
                f"background: {rgba(state_colour, STATE_BACKGROUND_ALPHA)}; "
                f"padding: 2px 8px; border-radius: 4px;"
            )
            hdr_row.addWidget(state_lbl)
            hdr_row.addStretch()

            # Order follows BotManager._bots insertion order, wrapping at both ends.
            nav_btn_qss = (
                f"QPushButton {{ background: {ds.SURFACE_CONTROL}; color: {ds.PRIMARY}; "
                f"border: 1px solid {ds.GLOW_PRIMARY_EDGE}; border-radius: 4px; "
                "padding: 4px 10px; font-weight: bold; font-size: 12px; "
                "min-width: 70px; }"
                f"QPushButton:hover {{ background: {ds.GLOW_PRIMARY_FAINT}; "
                f"border: 1px solid {ds.PRIMARY}; }}"
                f"QPushButton:disabled {{ background: {ds.CARD_METRIC_BORDER}; "
                f"color: {ds.TEXT_PLACEHOLDER}; border: 1px solid {ds.CARD_METRIC_BORDER}; }}"
            )
            self._prev_btn = QPushButton("◀ Prev")
            self._prev_btn.setStyleSheet(nav_btn_qss)
            self._prev_btn.setToolTip(
                "Switch to the previous bot in the swarm without "
                "closing this dialog (Ctrl+Left)"
            )
            self._prev_btn.clicked.connect(lambda: self._navigate_to_sibling(-1))
            hdr_row.addWidget(self._prev_btn)

            self._next_btn = QPushButton("Next ▶")
            self._next_btn.setStyleSheet(nav_btn_qss)
            self._next_btn.setToolTip(
                "Switch to the next bot in the swarm without "
                "closing this dialog (Ctrl+Right)"
            )
            self._next_btn.clicked.connect(lambda: self._navigate_to_sibling(1))
            hdr_row.addWidget(self._next_btn)

            # Hide both if we can't navigate (single-bot or no manager)
            _siblings = self._sibling_bot_ids()
            _can_nav = len(_siblings) > 1
            self._prev_btn.setVisible(_can_nav)
            self._next_btn.setVisible(_can_nav)

            layout.addLayout(hdr_row)

            # Tabs
            tabs = QTabWidget()
            self._tabs = tabs

            # --- Tab 1: Status ---
            tabs.addTab(self._wrap_scrollable(self._create_status_tab()), "Status")

            # --- Tab 2: Settings ---
            tabs.addTab(self._wrap_scrollable(self._create_settings_tab()), "Settings")

            # --- Tab 3: Fold Tranches (Scrumming only) ---
            if cfg.mode.value == "scrumming":
                self._install_fold_tranches_tab(tabs)

            # --- Tab 3.5: Stack Tranches (Scrumming only) ---
            if cfg.mode.value == "scrumming":
                self._install_stack_tranches_tab(tabs)

            # --- Tab 4: Bot Swarm (Scrumming only) ---
            if cfg.mode.value == "scrumming":
                tabs.addTab(
                    self._wrap_scrollable(self._create_bot_swarm_tab()), "Bot Swarm"
                )

            # --- Tab 5: Market Inspector (Scrumming only) ---
            # The top-level Market Inspector tab owns the fetch cycle; this reads its scan.
            if cfg.mode.value == "scrumming":
                tabs.addTab(
                    self._wrap_scrollable(self._create_market_inspector_tab()),
                    "Market Inspector",
                )

            # --- Tab 6: Phantom Bots (Scrumming only) ---
            if cfg.mode.value == "scrumming":
                tabs.addTab(
                    self._wrap_scrollable(self._create_phantom_bots_tab()),
                    "Phantom Bots",
                )

            # --- Positions Held (Extractor only) ---
            # Each open position has its own Fire button; there is no global fire.
            if cfg.mode.value == "extractor":
                tabs.addTab(
                    self._wrap_scrollable(self._create_positions_held_tab()),
                    "Positions Held",
                )

            layout.addWidget(tabs)

            # Bottom buttons
            btn_row = QHBoxLayout()
            btn_row.addStretch()

            self._apply_btn = QPushButton("Apply Changes")
            self._apply_btn.setStyleSheet(
                f"QPushButton {{ background: {ds.PRIMARY}; color: {ds.SURFACE_CHART}; "
                "border: none; border-radius: 6px; padding: 8px 20px; "
                "font-weight: bold; font-size: 12px; }"
                f"QPushButton:hover {{ background: {ds.SETTINGS_PRIMARY_HOVER}; }}"
                f"QPushButton:disabled {{ background: {ds.SETTINGS_DISABLED_DEEP}; color: {ds.TEXT_MUTED}; }}"
            )
            self._apply_btn.setEnabled(False)
            self._apply_btn.clicked.connect(self._apply_changes)
            btn_row.addWidget(self._apply_btn)

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(
                f"QPushButton {{ background: {ds.CARD_METRIC_BORDER}; color: {ds.TEXT_INACTIVE}; "
                f"border: 1px solid {ds.MENU_BORDER}; border-radius: 6px; "
                "padding: 8px 20px; }"
                f"QPushButton:hover {{ background: {ds.MENU_BORDER}; }}"
            )
            close_btn.clicked.connect(self.accept)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

            # Change indicator
            self._change_lbl = QLabel("")
            self._change_lbl.setStyleSheet(f"color: {ds.WARNING}; font-size: 11px;")
            layout.addWidget(self._change_lbl)

            try:
                from PySide6.QtGui import QShortcut, QKeySequence

                if _can_nav:
                    back = QShortcut(QKeySequence("Ctrl+Left"), self)
                    back.activated.connect(lambda: self._navigate_to_sibling(-1))
                    forward = QShortcut(QKeySequence("Ctrl+Right"), self)
                    forward.activated.connect(lambda: self._navigate_to_sibling(1))
            except Exception as _shortcut_exc:
                logger.debug(
                    "sibling navigation shortcuts unavailable: %s", _shortcut_exc
                )

            # Last: it measures the tabs, so every tab must already exist.
            self.open_at_content_size()

        def open_at_content_size(
            self, available: tuple[int, int] | None = None
        ) -> tuple[int, int]:
            """Resize so the largest tab fits, and report the size set.

            ``available`` overrides the screen; left None it reads
            ``availableGeometry``. This sets the size the dialog opens at and
            leaves ``setMinimumSize`` alone.
            """
            tabs = getattr(self, "_tabs", None)
            layout = self.layout()
            if tabs is None or layout is None:
                return self.width(), self.height()
            content_w, content_h, page_w, page_h = tab_content_demand_px(tabs)
            hint = layout.sizeHint()
            needed_w, needed_h = dialog_content_size_px(
                hint.width(), hint.height(), page_w, page_h, content_w, content_h
            )
            if available is None:
                screen = self.screen() or QGuiApplication.primaryScreen()
                if screen is None:
                    # No screen to respect, so nothing to clamp against.
                    available = (needed_w, needed_h)
                else:
                    size = screen.availableGeometry()
                    available = (size.width(), size.height())
            width, height = dialog_open_size_px(
                needed_w,
                needed_h,
                available[0],
                available[1],
                self.minimumWidth(),
                self.minimumHeight(),
            )
            self.resize(width, height)
            return width, height

        def _sibling_bot_ids(self) -> list:
            """Return the ordered list of bot ids in the current
            BotManager, in insertion order. Empty list when no
            manager is attached (e.g., dialog opened in test
            harness)."""
            if self._bm is None:
                return []
            try:
                return list(self._bm._bots.keys())
            except Exception:
                return []

        def _navigate_to_sibling(self, direction: int) -> None:
            """Stage a navigation request and close this dialog.

            ``direction`` is +1 (Next) or -1 (Prev). Wraps around
            both ends so the operator can cycle through the swarm
            indefinitely. The actual close+reopen is performed by
            ``main_window._on_bot_clicked`` once exec() returns —
            this method only sets ``self._pending_navigate_to``
            with the target bot_id, then accepts the dialog.

            Pending unsaved changes are discarded (consistent with
            the existing Close button behaviour). Apply Changes
            must be clicked first to commit edits.
            """
            ids = self._sibling_bot_ids()
            if len(ids) < 2:
                return
            try:
                cur_idx = ids.index(self._bot.bot_id)
            except ValueError:
                # The current bot was unregistered while the dialog was open.
                cur_idx = 0 if direction > 0 else 1
            new_idx = (cur_idx + direction) % len(ids)
            self._pending_navigate_to = ids[new_idx]
            self.accept()

        def active_tab_index(self) -> int:
            """The index of the tab the operator is viewing.

            ``main_window`` reads it so the next bot's dialog opens on the
            same tab.
            """
            try:
                return int(self._tabs.currentIndex())
            except Exception:
                return 0

        def _wrap_scrollable(self, content: QWidget) -> QScrollArea:
            """Wrap a tab's ``content`` widget in a ``QScrollArea``.

            ``setWidgetResizable(True)`` lets ``content`` keep its own
            vertical size, so a ``QFormLayout`` row is never compressed below
            the height Qt needs to paint its controls.
            """
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(content)
            return scroll

        def _configure_form(self, form: QFormLayout) -> None:
            """Apply row-sizing defaults to ``form``.

            Sets ``AllNonFixedFieldsGrow``, ``DontWrapRows`` and the row
            spacing that keeps a row at its natural height.
            """
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.DontWrapRows)
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(8)
            form.setContentsMargins(8, 8, 8, 8)

        def _mark_changed(self, field: str, value):
            """Track a changed field and enable Apply button."""
            # Phantom fields are runtime attributes on ScrummingBot, not BotConfig fields.
            if field == "enable_phantoms":
                original = getattr(self._bot, "_phantoms_enabled", None)
            elif field == "phantom_timeframes":
                original = list(getattr(self._bot, "_phantom_timeframes", []))
                value = list(value)
            elif field == "lock_candle_count":
                coord = getattr(self._bot, "_coordinator", None)
                original = getattr(coord, "lock_candle_count", None) if coord else None
            else:
                original = getattr(self._bot.config, field, None)

            if value == original:
                self._changes.pop(field, None)
            else:
                self._changes[field] = value

            if self._changes:
                self._apply_btn.setEnabled(True)
                fields = ", ".join(self._changes.keys())
                self._change_lbl.setText(f"Pending changes: {fields}")
            else:
                self._apply_btn.setEnabled(False)
                self._change_lbl.setText("")

        def _apply_changes(self):
            """Apply all pending changes to the bot config."""
            if not self._changes:
                return

            cfg = self._bot.config
            applied = []

            # Routed through update_phantom_config, which is safe mid-session.
            _PHANTOM_FIELDS = {
                "enable_phantoms",
                "phantom_timeframes",
                "lock_candle_count",
            }
            phantom_changes = {
                f: v for f, v in self._changes.items() if f in _PHANTOM_FIELDS
            }
            other_changes = {
                f: v for f, v in self._changes.items() if f not in _PHANTOM_FIELDS
            }

            if phantom_changes and hasattr(self._bot, "update_phantom_config"):
                try:
                    result = self._bot.update_phantom_config(**phantom_changes)
                    for k, v in result.get("applied", {}).items():
                        applied.append(f"{k}={v}")
                    for caveat in result.get("caveats", []):
                        logger.info(
                            "Bot %s phantom caveat: %s", self._bot.bot_id[:8], caveat
                        )
                except Exception as exc:
                    logger.warning(
                        "Bot %s: phantom config update failed: %s",
                        self._bot.bot_id[:8],
                        exc,
                    )

            # A field snapshotted into a runtime attribute is routed through a bot method.
            _RUNTIME_ROUTED = {
                "target_balance": "set_target_balance_live",
                "visibility": "set_visibility_live",
                "aggressive_trading": "set_aggressive_live",
                "hedge_balance": "set_hedge_balance_live",
                # setattr alone moves the flag and leaves _hedge_bal at zero.
                "hedge_rebalance_active": "set_hedge_rebalance_active_live",
                # set_chunk_size_usd also rescales _chunk_free_base and the registry claim.
                "extractor_chunk_size_usd": "set_chunk_size_usd",
            }
            for field, value in other_changes.items():
                route = _RUNTIME_ROUTED.get(field)
                if route and hasattr(self._bot, route):
                    try:
                        result = getattr(self._bot, route)(value)
                        if result.get("applied"):
                            applied.append(f"{field}={value} (runtime+anchor synced)")
                        else:
                            reason = result.get("reason", "unknown")
                            logger.warning(
                                "Bot %s: %s live-update refused: %s",
                                self._bot.bot_id[:8],
                                field,
                                reason,
                            )
                            applied.append(f"{field}={value} (REFUSED: {reason})")
                    except Exception as exc:
                        logger.warning(
                            "Bot %s: %s live-update raised: %s",
                            self._bot.bot_id[:8],
                            field,
                            exc,
                        )
                        applied.append(f"{field}={value} (ERROR: {exc})")
                elif hasattr(cfg, field):
                    setattr(cfg, field, value)
                    applied.append(f"{field}={value}")

            logger.info(
                "Bot %s: live settings changed: %s",
                self._bot.bot_id[:8],
                ", ".join(applied),
            )
            self._changes.clear()
            self._apply_btn.setEnabled(False)
            self._change_lbl.setText(
                f"Applied {len(applied)} change(s) — active immediately"
            )
            self._change_lbl.setStyleSheet(f"color: {ds.SUCCESS}; font-size: 11px;")

            self.settings_changed.emit(
                self._bot.bot_id,
                {f: getattr(cfg, f, None) for f in [a.split("=")[0] for a in applied]},
            )

        def _bot_manager_for_save(self) -> object | None:
            """Return the object that owns `save_all_state`, or None.

            `self._bm` FIRST, THEN THE BOT'S OWN MANAGER. The Simulator
            builds this dialog with no manager, and so do the listing
            tests, so `self._bm` is None on those paths; the parent
            bot's `_bot_manager` is the object that produced these rows
            in the first place. The Arbiter handler resolves its manager
            the same way and for the same reason.
            """
            for candidate in (
                getattr(self, "_bm", None),
                getattr(self._bot, "_bot_manager", None),
            ):
                if callable(getattr(candidate, "save_all_state", None)):
                    return candidate
            return None

        def _save_fleet_state_now(self, what: str) -> tuple[bool, str]:
            """Persist the fleet in this click. Return (saved, reason).

            ``clear_fold_tranches`` and ``clear_pending_wire_credits`` write
            memory only, so ``what`` is not on disk until this runs. The call
            blocks the GUI thread for the length of the serialise, and a
            failure comes back as the reason string.
            """
            manager = self._bot_manager_for_save()
            saver = getattr(manager, "save_all_state", None)
            if not callable(saver):
                return (False, "no bot manager is attached to this panel")
            try:
                saver()
            except Exception as exc:  # noqa: BLE001 - operator surface
                logger.warning(
                    "%s: cleared in memory but NOT saved (%s: %s); a "
                    "restart before the next rolling save will restore "
                    "it.",
                    what,
                    type(exc).__name__,
                    exc,
                )
                return (False, f"{type(exc).__name__}: {exc}")
            return (True, "")

        @staticmethod
        def _format_age(seconds: float) -> str:
            """Human-readable age string. v3.16.39 P2-VIS helper."""
            if seconds < 60:
                return f"{int(seconds)}s"
            if seconds < 3600:
                return f"{int(seconds / 60)}m"
            if seconds < 86400:
                hrs = seconds / 3600
                return f"{hrs:.1f}h"
            days = seconds / 86400
            return f"{days:.1f}d"
