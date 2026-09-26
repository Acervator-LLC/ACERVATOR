"""``HeaderStripMixin`` builds the header stat strip of the main window."""

from __future__ import annotations

from functools import partial
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


from .asset_class_surface import BUTTON_MIN_W as CLASS_BUTTON_MIN_W
from .asset_class_surface import BUTTON_TEXT_PAD as CLASS_BUTTON_TEXT_PAD
from .asset_class_surface import GROUP_SPACING_PX as CLASS_GROUP_SPACING


class ClassGroupBar(QWidget):
    """The segmented asset class group, one square holding one segment per class.

    ``set_labels`` keeps each button's full class name, and every resize
    re-elides that name to the width its own segment has.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels: dict = {}
        self.setAccessibleName("Asset class group")
        self.setAccessibleDescription(
            "One segment per asset class, in one square. The active class "
            "filters the exchanges and bots every tab shows."
        )

    def set_labels(self, labels: dict) -> None:
        """Hold the full name every button draws before elision."""
        self._labels = dict(labels)
        self._elide()

    def set_side(self, side: int) -> None:
        """Fix both of the square's sides to ``side`` pixels.

        The same number reaches the React page, so neither variant measures a
        row height and the two squares cannot differ in size.
        """
        self.setFixedSize(int(side), int(side))

    def resizeEvent(self, event):
        """Re-elide every label to the width its own segment now has."""
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        """Shorten each button's text to the room that button now has."""
        for button, full in self._labels.items():
            room = max(button.width() - CLASS_BUTTON_TEXT_PAD, 0)
            button.setText(button.fontMetrics().elidedText(full, Qt.ElideRight, room))


def _spendable_profits_class() -> type:
    """The strip class the running variant draws, Qt or React."""
    from ..variant_surface import SPENDABLE_PROFITS, surface_class

    return surface_class(SPENDABLE_PROFITS)


def _stat_card_class() -> type:
    """The stat card class the running variant draws, Qt or React."""
    from ..variant_surface import DASHBOARD_STAT_CARD, surface_class

    return surface_class(DASHBOARD_STAT_CARD)


class HeaderStripMixin:
    """``HeaderStripMixin`` owns the header strip widgets.

    ``_build_header_strip`` lays out the spendable-profits strip, five
    ``StatCard`` counters and the segmented ``ClassGroupBar``.
    """

    # MainWindow supplies these; the bare annotations create no attribute.
    _show_error_log_dialog: Callable[..., Any]
    _update_mode_btn_style: Callable[..., Any]
    _push_live_tab: Callable[..., Any]
    setCentralWidget: Callable[..., Any]
    setWindowTitle: Callable[..., Any]

    # TradingTabMixin builds these; select_asset_class reads them by name.
    _trading_stack: Any
    _crypto_tab_widget: Any
    _stock_tab_widget: Any
    _crypto_exchange_tabs: dict
    _stock_exchange_tabs: dict
    _crypto_placeholder: Any
    _stock_placeholder: Any
    _unlayered_title: Any
    _unlayered_note: Any
    _tab_widget: Any
    _exchange_tabs: Any
    _empty_placeholder: Any
    _status_log: Any
    _settings: Any

    # _build_class_group assigns these three.
    _class_group: dict
    _class_group_widget: Any
    _asset_class: str

    def _build_class_group(self) -> QWidget:
        """Build the one square the asset classes segment, on the header top row.

        One checkable button per ``asset_class_surface.asset_classes`` entry
        sits at its ``segment_cell`` in a ``QGridLayout`` of zero spacing.
        """
        from .asset_class_surface import (
            class_buttons,
            grid_shape,
            group_side_px,
            normalise,
        )

        stored = None
        settings = getattr(self, "_settings", None)
        if settings is not None and hasattr(settings, "get"):
            stored = settings.get("active_asset_class", None)
        self._asset_class = normalise(stored)
        self._trading_mode = self._asset_class

        rows, columns = grid_shape()
        holder = ClassGroupBar()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(CLASS_GROUP_SPACING)
        grid.setVerticalSpacing(CLASS_GROUP_SPACING)
        for at in range(columns):
            grid.setColumnStretch(at, 1)
        for at in range(rows):
            grid.setRowStretch(at, 1)

        self._class_buttons = QButtonGroup(holder)
        self._class_buttons.setExclusive(True)
        self._class_group = {}
        self._class_names: dict = {}

        for model in class_buttons(self._asset_class):
            button = QPushButton(model["text"])
            button.setCheckable(True)
            button.setChecked(model["class"] == self._asset_class)
            button.setToolTip(model["tooltip"])
            button.setStyleSheet(model["style_sheet"])
            # Preferred, never Minimum: the group must give width back to the
            # counters when the window is narrow.
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            button.setMinimumWidth(CLASS_BUTTON_MIN_W)
            button.clicked.connect(partial(self._on_class_clicked, model["class"]))
            self._class_buttons.addButton(button)
            self._class_group[model["class"]] = button
            self._class_names[model["class"]] = model["text"]
            grid.addWidget(
                button,
                int(model["row"]),
                int(model["grid_column"]),
                1,
                int(model["column_span"]),
            )

        holder.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        holder.set_side(group_side_px())
        holder.set_labels(
            {
                button: self._class_names[key]
                for key, button in self._class_group.items()
            }
        )
        self._class_group_widget = holder
        return holder

    def _on_class_clicked(self, name: str) -> None:
        """Hand one segmented button's press to the window's class selector."""
        chooser = getattr(self, "select_asset_class", None)
        if callable(chooser):
            chooser(name)

    def select_asset_class(self, name: Any) -> None:
        """Make one asset class active, and store it for the next launch.

        The layer a class carries becomes the current ``_trading_stack`` page;
        a class with no layer draws ``_show_unlayered_class``.
        """
        from .asset_class_surface import (
            has_layer,
            layer_page,
            normalise,
            selection_log,
            window_title,
        )

        key = normalise(name)
        self._asset_class = key
        self._trading_mode = key

        stack = getattr(self, "_trading_stack", None)
        if stack is not None:
            if not has_layer(key):
                self._show_unlayered_class(key)
            else:
                stack.setCurrentIndex(layer_page(key))
                stock = key == "stocks"
                self._tab_widget = (
                    self._stock_tab_widget if stock else self._crypto_tab_widget
                )
                self._exchange_tabs = (
                    self._stock_exchange_tabs if stock else self._crypto_exchange_tabs
                )
                self._empty_placeholder = (
                    self._stock_placeholder if stock else self._crypto_placeholder
                )

        self.setWindowTitle(window_title(key))
        self._status_log.log(selection_log(key), "info")
        self._store_asset_class(key)
        self._sync_class_group()
        self._retitle_add_exchange()
        self._push_live_tab({"layer": key, "asset_class": key})
        self._update_mode_btn_style()

    def _store_asset_class(self, key: Any) -> None:
        """Write the active asset class into settings for the next launch."""
        settings = getattr(self, "_settings", None)
        if settings is None or not hasattr(settings, "set"):
            return
        try:
            settings.set("active_asset_class", key)
        except (KeyError, TypeError) as exc:
            self._status_log.log(f"Asset class not stored: {exc}", "warning")

    def _show_unlayered_class(self, key: Any) -> None:
        """Draw the page a class with no trading layer shows."""
        from .asset_class_surface import class_state

        page = getattr(self, "_unlayered_page", None)
        if page is None:
            return
        state = class_state(key)
        self._unlayered_title.setText(f"{state['name']} — no trading layer")
        self._unlayered_note.setText(state["note"])
        self._trading_stack.setCurrentWidget(page)
        self._tab_widget = None
        self._exchange_tabs = {}
        self._empty_placeholder = page

    def _retitle_add_exchange(self) -> None:
        """Relabel every Add Exchange button for the active asset class."""
        from .asset_class_surface import (
            add_exchange_enabled,
            add_exchange_label,
            add_exchange_tooltip,
        )

        key = getattr(self, "_asset_class", "crypto")
        text = add_exchange_label(key)
        tip = add_exchange_tooltip(key)
        live = add_exchange_enabled(key)
        for button in getattr(self, "_add_exchange_buttons", ()):
            button.setText(text)
            button.setToolTip(tip)
            button.setEnabled(live)

    def _sync_class_group(self) -> None:
        """Check the button the active class names, and leave the rest clear."""
        from .asset_class_surface import class_button

        active = getattr(self, "_asset_class", None)
        for key, button in (getattr(self, "_class_group", None) or {}).items():
            model = class_button(key, active)
            was = button.blockSignals(True)
            button.setChecked(model["checked"])
            button.blockSignals(was)
            button.setToolTip(model["tooltip"])

    def _build_header_strip(self) -> QVBoxLayout:
        """Build the central ``QWidget``.

        Returns the ``QVBoxLayout`` the main tab widget is added to.
        """
        from . import header_strip_surface as surface

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(surface.TOP_ROW_SPACING_PX)
        top_row.setContentsMargins(0, 0, 0, 0)

        self._spendable_widget = _spendable_profits_class()()
        self._spendable_widget.setMinimumWidth(surface.slot_min_w("spendable"))
        top_row.addWidget(
            self._spendable_widget, stretch=surface.slot_stretch("spendable")
        )

        card_class = _stat_card_class()
        self._stat_scrummed = card_class("Scrummed", "$0.00")
        self._stat_scrummed.setToolTip(
            "Total Scrummed (high score) — cumulative USD sold "
            "across all bots since the platform run started. Grows "
            "with every SCRUM (sell at upper-band) + MANUAL_SCRUM "
            "fill. Resets to $0.00 only on a fresh process start."
        )
        self._stat_folded = card_class("Folded", "$0.00")
        self._stat_folded.setToolTip(
            "Total Folded (high score) — cumulative USD bought "
            "across all bots since the platform run started. Grows "
            "with every FOLD (buy at lower-band) + MANUAL_FOLD "
            "fill. Resets to $0.00 only on a fresh process start."
        )
        # _stat_pnl is never added to top_row; MainWindow still calls set_value on it.
        self._stat_pnl = card_class("P/L", "$0.00")
        self._stat_pnl.setVisible(False)
        self._stat_trades = card_class("Trades", "0")
        self._stat_trades.setToolTip(
            "Total executed buy and sell trades across all active bots."
        )
        self._stat_bots = card_class("Bots", "0")
        self._stat_bots.setToolTip(
            "Bots currently in RUNNING state (actively trading)."
        )
        self._stat_errors = card_class("Errors", "0")
        self._stat_errors.setToolTip(
            "Error count across all bots since last reset. "
            "Click to open the Error Log; use the Reset button "
            "inside to clear all previous faults.\n\n"
            "Hover bot rows to see current ERROR/COOLDOWN state."
        )
        self._stat_errors.set_clickable(True, "Click to open the error log.")
        self._stat_errors.clicked.connect(self._show_error_log_dialog)
        # set_value renders through mask_or once a dot is attached.
        self._stat_scrummed.attach_privacy_dot("counter.scrummed")
        self._stat_folded.attach_privacy_dot("counter.folded")
        self._stat_trades.attach_privacy_dot("counter.trades")
        self._stat_bots.attach_privacy_dot("counter.bots")
        self._stat_errors.attach_privacy_dot("counter.errors")
        for slot, card in zip(
            surface.COUNTER_SLOTS,
            [
                self._stat_scrummed,
                self._stat_folded,
                self._stat_trades,
                self._stat_bots,
                self._stat_errors,
            ],
        ):
            card.setMinimumWidth(surface.slot_min_w(slot))
            top_row.addWidget(card, stretch=surface.slot_stretch(slot))

        # The square is one fixed side, so it takes no room from the figures
        # and sits centred on the row's height at the row's right end.
        class_group = self._build_class_group()
        top_row.addWidget(
            class_group,
            surface.slot_stretch("mode_button"),
            Qt.AlignVCenter | Qt.AlignRight,
        )

        # _on_main_tab_changed hides _header_strip_container on the Simulator tab.
        self._header_strip_container = QWidget()
        self._header_strip_container.setLayout(top_row)
        main_layout.addWidget(self._header_strip_container)

        return main_layout
