# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""``ClassFilterTabMixin`` makes every tab but Status and Console follow the class.

``select_asset_class`` extends the header strip's chooser, and
``_apply_asset_class`` narrows the Live sub-tabs, the fleet the Swarm, the
Charts and the Inspector are fed, and the rows the History, the Sim and the
Paper tab hold. ``_refilter_class_tabs`` replaces no tab's page: a sector
holding no bot draws the same tab with empty lists.
``class_filter_surface`` decides which class a market belongs to.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtWidgets import QLabel

from .. import design_system as ds
from . import class_filter_surface as cfs

logger = logging.getLogger("acervator.gui")

#: The window attribute holding each tab that offers ``set_asset_class`` and
#: counts its own class-bearing rows.
SELF_COUNTING_TABS = ("_history_tab", "_simulator_tab", "_paper_trader_tab")

#: Each self-counting tab's label mapped to the attribute holding that tab, so
#: ``_draw_class_notes`` reads the count that tab answered.
COUNTED_TAB_ATTRS = {
    "History": "_history_tab",
    "Sim": "_simulator_tab",
    "Paper": "_paper_trader_tab",
}

#: Each class-following tab's label mapped to the attribute holding that tab.
#: ``_draw_class_notes`` seats a note only on the page that is this object, so
#: ``simulator_tab.BuildFailureNote`` keeps its own page.
CLASS_TAB_ATTRS = {
    "Live": "_trading_tab",
    "Charts": "_charts_tab",
    "Inspector": "_market_inspector",
    "Swarm": "_bot_viz",
    "History": "_history_tab",
    "Sim": "_simulator_tab",
    "Paper": "_paper_trader_tab",
}

#: The one note a class-following tab draws while it keeps no row of the class.
NOTE_NAME = "class-empty-note"

NOTE_STYLE = f"QLabel {{ color: {ds.TEXT_EMPTY_STATE}; font-size: {ds.TYPE_BODY}px; }}"
NOTE_MARGINS_PX = (ds.SPACE_L, ds.SPACE_L, ds.SPACE_L, ds.SPACE_L)


class ClassFilterTabMixin:
    """Supplies the asset class filter to the main window.

    It sits before ``HeaderStripMixin`` in the bases, so ``select_asset_class``
    runs the strip's own chooser first and then refilters every tab.
    """

    # MainWindow supplies these; the bare annotations create no attribute.
    _bot_manager: Any
    _exchange_tabs: dict
    _crypto_exchange_tabs: dict
    _stock_exchange_tabs: dict
    _crypto_tab_widget: Any
    _stock_tab_widget: Any
    _class_layers: dict
    _tab_widget: Any
    _trading_stack: Any
    _push_live_tab: Callable[..., Any]

    def select_asset_class(self, name: Any) -> None:
        """Make one asset class active, then refilter every tab that follows it.

        ``HeaderStripMixin.select_asset_class`` moves the Live stack, retitles
        Add Exchange and stores the choice; ``_apply_asset_class`` adds the tabs.
        """
        super().select_asset_class(name)  # type: ignore[misc]
        self._apply_asset_class()

    def _live_fleet(self) -> list:
        """Every live bot status, or an empty list while no fleet is held."""
        manager = getattr(self, "_bot_manager", None)
        if manager is None:
            return []
        try:
            return list(manager.list_bots())
        except Exception as exc:  # noqa: BLE001 - a silent tab is worse
            logger.debug("asset class filter read no fleet: %s", exc)
            return []

    def _class_fleet(self, statuses: Any = None) -> list:
        """Every bot status whose market belongs to the active asset class."""
        rows = self._live_fleet() if statuses is None else statuses
        return cfs.bots_of_class(rows, cfs.active())

    def _filter_live_sub_tabs(self, key: str) -> list:
        """Hide the Live exchange sub-tabs whose venue does not serve ``key``.

        Answers the venue ids left visible; a venue ``venue_classes`` gives two
        classes is answered under both.
        """
        shown: list = []
        for held in (getattr(self, "_class_layers", None) or {}).values():
            store, widget = held["exchange_tabs"], held["tabs"]
            for eid, tab in store.items():
                at = widget.indexOf(tab)
                if at < 0:
                    continue
                serves = key in _classes_of(eid)
                widget.setTabVisible(at, serves)
                if serves:
                    shown.append(eid)
        return sorted(shown)

    def _live_layer_for(self, key: str, venues: list) -> None:
        """Put the Live stack on the layer widget holding ``venues``.

        ``key``'s own layer is taken where it holds one of ``venues``, so a
        venue seated on several layers does not pull the stack to the first.
        """
        stack = getattr(self, "_trading_stack", None)
        if stack is None or not venues:
            return
        tabs = store = None
        layers = getattr(self, "_class_layers", None) or {}
        asked = layers.get(key)
        order = [asked] if asked is not None else []
        order += [held for held in layers.values() if held is not asked]
        for held in order:
            if set(venues) & set(held["exchange_tabs"]):
                tabs, store = held["tabs"], held["exchange_tabs"]
                break
        if tabs is None or store is None:
            return
        host = tabs.parentWidget()
        while host is not None and stack.indexOf(host) < 0:
            host = host.parentWidget()
        if host is not None:
            stack.setCurrentWidget(host)
        self._tab_widget = tabs
        self._exchange_tabs = store

    def _apply_asset_class(self) -> None:
        """Refilter every tab that follows the active asset class.

        ``_repaint_header_strip`` runs last, so the strip's AMMO total reads the
        sector just pressed rather than waiting for the dashboard tick.
        """
        key = cfs.set_active(getattr(self, "_asset_class", None))
        held: set = set()
        for layer in (getattr(self, "_class_layers", None) or {}).values():
            held |= set(layer["exchange_tabs"])
        venues = cfs.venues_of_class(sorted(held), key)
        self._live_layer_for(key, venues)
        self._refilter_class_tabs()
        self._feed_class_tabs(self._class_fleet())
        self._push_live_tab({"asset_class": key, "class_venues": venues})
        self._repaint_header_strip()

    def _repaint_header_strip(self) -> None:
        """Redraw the header strip for the active asset class.

        A window whose strip is not built yet offers no
        ``_refresh_header_strip``, and nothing is redrawn.
        """
        repaint = getattr(self, "_refresh_header_strip", None)
        if not callable(repaint):
            return
        try:
            repaint()
        except Exception as exc:  # noqa: BLE001 - a silent tab is worse
            logger.debug("header strip refused the asset class: %s", exc)

    def _refilter_class_tabs(self) -> None:
        """Narrow the Live sub-tabs and every self-counting tab to the class.

        ``MainWindow._refresh_dashboard`` calls this on its own timer, so
        ``_ask_tab_for_class`` reaches the rows with no sector pressed.
        """
        key = cfs.active()
        self._filter_live_sub_tabs(key)
        counts: dict = {}
        for attr in SELF_COUNTING_TABS:
            counts[attr] = self._ask_tab_for_class(attr, key)
        self._class_tab_counts = counts
        self._draw_class_notes()

    def _class_note_label(self, name: str, page: Any) -> Any:
        """The note label ``name``'s page carries, seated at the top of its layout.

        Answers None for a page holding no layout, and seats one label per tab
        name so ``NOTE_NAME`` is never drawn twice.
        """
        held = getattr(self, "_class_notes", None)
        if held is None:
            held = {}
            self._class_notes = held
        label = held.get(name)
        if label is not None:
            return label
        layout = page.layout() if page is not None else None
        if layout is None:
            return None
        label = QLabel("", page)
        label.setObjectName(NOTE_NAME)
        label.setAccessibleName(NOTE_NAME)
        label.setStyleSheet(NOTE_STYLE)
        label.setContentsMargins(*NOTE_MARGINS_PX)
        label.setWordWrap(True)
        label.hide()
        layout.insertWidget(0, label)
        held[name] = label
        return label

    def _draw_class_notes(self) -> None:
        """Draw each class-following tab's own note while it keeps no row.

        ``class_filter_surface.empty_note`` supplies the sentence, and a tab
        outside ``TAB_SUBJECTS`` is left alone.
        """
        book = getattr(self, "_main_tabs", None)
        if book is None:
            return
        key = cfs.active()
        counts = getattr(self, "_class_tab_counts", None) or {}
        fleet = len(self._class_fleet())
        for at in range(book.count()):
            name = book.tabText(at)
            held = CLASS_TAB_ATTRS.get(name)
            if name not in cfs.TAB_SUBJECTS or held is None:
                continue
            tab = getattr(self, held, None)
            page = book.widget(at)
            if tab is None or page is not tab:
                continue
            attr = COUNTED_TAB_ATTRS.get(name)
            kept = counts.get(attr, (fleet, fleet))[0] if attr else fleet
            label = self._class_note_label(name, page)
            if label is None:
                continue
            label.setText(cfs.empty_note(name, key))
            label.setVisible(not kept)

    def _ask_tab_for_class(self, attr: str, key: str) -> tuple:
        """The rows one tab keeps for ``key`` and the rows it holds in all.

        A tab offering no ``set_asset_class`` answers two zeros, so nothing is
        reported empty on its behalf.
        """
        tab = getattr(self, attr, None)
        setter = getattr(tab, "set_asset_class", None)
        if not callable(setter):
            return (0, 0)
        try:
            kept, held = setter(key)
        except Exception as exc:  # noqa: BLE001 - a silent tab is worse
            logger.debug("%s refused the asset class: %s", attr, exc)
            return (0, 0)
        return (int(kept or 0), int(held or 0))

    def _feed_class_tabs(self, fleet: list) -> None:
        """Hand the class's fleet to the Swarm, the Charts and the Inspector."""
        swarm = getattr(self, "_bot_viz", None)
        if swarm is not None:
            try:
                swarm.update_bots(fleet)
            except Exception as exc:  # noqa: BLE001 - a silent tab is worse
                logger.debug("swarm refused the class fleet: %s", exc)
        charts = getattr(self, "_charts_tab", None)
        if charts is not None:
            try:
                charts.update_charts(fleet, bot_manager=self._bot_manager)
            except Exception as exc:  # noqa: BLE001 - a silent tab is worse
                logger.debug("charts refused the class fleet: %s", exc)
        inspector = getattr(self, "_market_inspector", None)
        if inspector is not None:
            try:
                inspector.update_active_symbols(fleet)
                inspector.set_asset_class(cfs.active())
            except Exception as exc:  # noqa: BLE001 - a silent tab is worse
                logger.debug("inspector refused the class fleet: %s", exc)


def _classes_of(venue_id: Any) -> frozenset:
    """Every asset class one venue serves, read from the venue map."""
    from .asset_class_surface import venue_classes

    return venue_classes(venue_id)
