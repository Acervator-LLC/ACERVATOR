# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""``ClassFilterTabMixin`` makes every tab but Status and Console follow the class.

``_wrap_tabs_for_class`` puts each filtered tab page and its note page in one
``QStackedWidget``, ``select_asset_class`` extends the header strip's chooser,
and ``_apply_asset_class`` narrows the Live sub-tabs, the fleet the Swarm, the
Charts and the Inspector are fed, and the rows the History, the Sim and the
Paper tab hold. ``class_filter_surface`` decides which class a market belongs
to and writes the sentence an emptied tab draws.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtWidgets import QStackedWidget

from . import class_filter_surface as cfs

logger = logging.getLogger("acervator.gui")

CONTENT_PAGE = 0
NOTE_PAGE = 1

#: The window attribute holding each filtered tab, for the tabs that offer
#: ``set_asset_class`` and count their own class-bearing rows.
SELF_COUNTING_TABS = {
    "History": "_history_tab",
    "Sim": "_simulator_tab",
    "Paper": "_paper_trader_tab",
}


class ClassFilterTabMixin:
    """Supplies the asset class filter to the main window.

    It sits before ``HeaderStripMixin`` in the bases, so ``select_asset_class``
    runs the strip's own chooser first and then refilters every tab.
    """

    # MainWindow supplies these; the bare annotations create no attribute.
    _main_tabs: Any
    _bot_manager: Any
    _exchange_tabs: dict
    _crypto_exchange_tabs: dict
    _stock_exchange_tabs: dict
    _crypto_tab_widget: Any
    _stock_tab_widget: Any
    _tab_widget: Any
    _trading_stack: Any
    _push_live_tab: Callable[..., Any]

    # `_wrap_tabs_for_class` assigns this.
    _class_stacks: dict

    def _wrap_tabs_for_class(self) -> dict:
        """Put every ``cfs.filters`` tab page and its note page in one stack.

        Answers the stacks by tab title.
        """
        from .empty_tabs import _empty_tab_class

        self._class_stacks = {}
        for index in range(self._main_tabs.count()):
            title = self._main_tabs.tabText(index)
            if not cfs.filters(title):
                continue
            page = self._main_tabs.widget(index)
            if page is None:
                continue
            self._main_tabs.removeTab(index)
            stack = QStackedWidget()
            stack.setAccessibleName(f"{title} class filter stack")
            stack.addWidget(page)
            stack.addWidget(_empty_tab_class()(cfs.note_model(title)))
            self._main_tabs.insertTab(index, stack, title)
            self._class_stacks[title] = stack
        return self._class_stacks

    def _redraw_class_note(self, title: str, stack: Any) -> None:
        """Rebuild one stack's note page for the active asset class."""
        from .empty_tabs import _empty_tab_class

        old = stack.widget(NOTE_PAGE)
        stack.addWidget(_empty_tab_class()(cfs.note_model(title)))
        if old is not None:
            stack.removeWidget(old)
            old.deleteLater()

    def _show_class_note(self, title: str, empty: bool) -> None:
        """Show one tab's note page while it holds nothing for the class."""
        stack = (getattr(self, "_class_stacks", None) or {}).get(title)
        if stack is None:
            return
        if empty:
            self._redraw_class_note(title, stack)
        stack.setCurrentIndex(NOTE_PAGE if empty else CONTENT_PAGE)

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
        for store, widget in (
            (self._crypto_exchange_tabs, self._crypto_tab_widget),
            (self._stock_exchange_tabs, self._stock_tab_widget),
        ):
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

        A class ``has_layer`` refuses still shows the venues serving it.
        """
        stack = getattr(self, "_trading_stack", None)
        if stack is None or not venues:
            return
        if set(venues) & set(self._stock_exchange_tabs):
            tabs, store = self._stock_tab_widget, self._stock_exchange_tabs
        elif set(venues) & set(self._crypto_exchange_tabs):
            tabs, store = self._crypto_tab_widget, self._crypto_exchange_tabs
        else:
            return
        host = tabs.parentWidget()
        while host is not None and stack.indexOf(host) < 0:
            host = host.parentWidget()
        if host is not None:
            stack.setCurrentWidget(host)
        self._tab_widget = tabs
        self._exchange_tabs = store

    def _apply_asset_class(self) -> None:
        """Refilter every tab that follows the active asset class."""
        key = cfs.set_active(getattr(self, "_asset_class", None))
        configured = sorted(
            set(self._crypto_exchange_tabs) | set(self._stock_exchange_tabs)
        )
        venues = cfs.venues_of_class(configured, key)
        self._live_layer_for(key, venues)
        shown = self._filter_live_sub_tabs(key)
        fleet = self._class_fleet()
        self._feed_class_tabs(fleet)
        self._refresh_class_notes(fleet, shown)
        self._push_live_tab({"asset_class": key, "class_venues": venues})

    def _refresh_class_notes(self, fleet: Any, shown: Any = None) -> None:
        """Show or hide every filtered tab's note for the active class.

        A tab draws the note while the class holds no bot anywhere, or while
        the tab holds rows and none of them belong to the class.
        """
        key = cfs.active()
        bare = not fleet
        visible = self._filter_live_sub_tabs(key) if shown is None else shown
        self._show_class_note("Live", bare and bool(visible))
        for title in ("Swarm", "Charts", "Inspector"):
            self._show_class_note(title, bare)
        for title, attr in SELF_COUNTING_TABS.items():
            kept, held = self._ask_tab_for_class(attr, key)
            self._show_class_note(title, bare or (held > 0 and kept == 0))

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
