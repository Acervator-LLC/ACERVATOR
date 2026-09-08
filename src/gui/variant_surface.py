# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""One decision point for the Qt or the React build of a screen.

``register`` records a screen's two loaders. ``surface_class`` returns the
class the running variant selects and ``draws_react`` answers which side
that is. ``screens`` names every screen that carries both.
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

from src._variant import QT, resolve_variant

ALERTS = "Notifications and Alerts"
BOT_LIVE_SETTINGS = "Bot live settings"
BOT_SWARM = "Bot Swarm"
BUY_CONFIRMATION = "Buy confirmation dialog"
CONSOLE = "Console"
DASHBOARD_STAT_CARD = "Dashboard stat card"
EMPTY_TAB = "Empty tab"
HISTORY = "History"
HISTORY_TABLE = "History table"
MAIN_TAB_BOOK = "Main tab book"
MARKET_INSPECTOR = "Market Inspector"
SETTINGS_DIALOG = "Settings dialog"
SIMULATOR = "Sim"
SPENDABLE_PROFITS = "Spendable profits"
START_ALL_PROGRESS = "Start All progress dialog"

Loader = Callable[[], type]

_LOADERS: Dict[str, Tuple[Loader, Loader]] = {}


def register(screen: str, qt_loader: Loader, react_loader: Loader) -> None:
    """Record the Qt loader and the React loader for ``screen``."""
    _LOADERS[screen] = (qt_loader, react_loader)


def screens() -> Tuple[str, ...]:
    """Every screen name ``register`` holds, in name order."""
    return tuple(sorted(_LOADERS))


def draws_react(screen: str, variant: str | None = None) -> bool:
    """True when ``variant`` selects the React loader for ``screen``.

    A ``variant`` of None asks ``resolve_variant`` for the running build.
    """
    chosen = resolve_variant() if variant is None else variant
    return chosen != QT and screen in _LOADERS


def surface_class(screen: str, variant: str | None = None) -> type:
    """Return the widget class ``screen`` builds under ``variant``.

    Raises KeyError for a screen ``register`` never recorded, and
    ImportError when the chosen side's widget cannot be imported.
    """
    qt_loader, react_loader = _LOADERS[screen]
    return react_loader() if draws_react(screen, variant) else qt_loader()


def _qt_alerts() -> type:
    """Import and return the Qt Notifications and Alerts tab."""
    from .alerts_tab import AlertsTab

    return AlertsTab


def _react_alerts() -> type:
    """Import and return the React Notifications and Alerts tab."""
    from .react_alerts_tab import AlertsReactTab

    return AlertsReactTab


def _qt_history() -> type:
    """Import and return the Qt History tab."""
    from .history_tab import HistoryTab

    return HistoryTab


def _react_history() -> type:
    """Import and return the React History tab."""
    from .react_history_tab import HistoryReactTab

    return HistoryReactTab


def _qt_history_table() -> type:
    """Import and return the Qt History table."""
    from .history_qt_table import HistoryQtTable

    return HistoryQtTable


def _react_history_table() -> type:
    """Import and return the React History table."""
    from .react_history_panel import HistoryWebTable

    return HistoryWebTable


def _qt_bot_swarm() -> type:
    """Import and return the Qt Bot Swarm tab."""
    from .bot_visualizer import BotVisualizationTab

    return BotVisualizationTab


def _react_bot_swarm() -> type:
    """Import and return the React Bot Swarm tab."""
    from .react_bot_swarm_tab import BotSwarmReactTab

    return BotSwarmReactTab


def _qt_console() -> type:
    """Import and return the Qt Console tab."""
    from .qt_console_tab import ConsoleQtTab

    return ConsoleQtTab


def _react_console() -> type:
    """Import and return the React Console tab."""
    from .react_console_tab import ConsoleReactTab

    return ConsoleReactTab


def _qt_empty_tab() -> type:
    """Import and return the Qt empty-tab panel."""
    from .main_tabs.empty_tabs import EmptyTabQtPanel

    return EmptyTabQtPanel


def _react_empty_tab() -> type:
    """Import and return the React empty-tab panel."""
    from .react_empty_tab import EmptyTabReactPanel

    return EmptyTabReactPanel


def _qt_main_tab_book() -> type:
    """Import and return the Qt main tab book."""
    from .main_tabs.main_tab_bar import MainTabBookQt

    return MainTabBookQt


def _react_main_tab_book() -> type:
    """Import and return the React main tab book."""
    from .react_main_window import MainTabBookReact

    return MainTabBookReact


def _qt_market_inspector() -> type:
    """Import and return the Qt Market Inspector tab."""
    from .market_inspector import MarketInspectorTab

    return MarketInspectorTab


def _react_market_inspector() -> type:
    """Import and return the React Market Inspector tab."""
    from .react_market_inspector_tab import MarketInspectorReactTab

    return MarketInspectorReactTab


def _qt_bot_live_settings() -> type:
    """Import and return the Qt Live Bot Settings window."""
    from .bot_live_settings import BotLiveSettingsDialog

    return BotLiveSettingsDialog


def _react_bot_live_settings() -> type:
    """Import and return the React Live Bot Settings window."""
    from .react_bot_live_settings import dialog_class

    return dialog_class()


def _qt_settings_dialog() -> type:
    """Import and return the Qt Settings dialog."""
    from .settings_dialog import SettingsDialog

    return SettingsDialog


def _react_settings_dialog() -> type:
    """Import and return the React Settings dialog."""
    from .react_settings_dialog import SettingsDialogReact

    return SettingsDialogReact


def _qt_dashboard_stat_card() -> type:
    """Import and return the Qt header stat card."""
    from .widgets.dashboard_stat_card import StatCard

    return StatCard


def _react_dashboard_stat_card() -> type:
    """Import and return the React header stat card."""
    from .react_dashboard_stat_card import StatCardReact

    return StatCardReact


def _qt_spendable_profits() -> type:
    """Import and return the Qt spendable-profits strip."""
    from .widgets.spendable_profits import SpendableProfitsWidget

    return SpendableProfitsWidget


def _react_spendable_profits() -> type:
    """Import and return the React spendable-profits strip."""
    from .react_spendable_profits import SpendableProfitsReact

    return SpendableProfitsReact


def _qt_start_all_progress() -> type:
    """Import and return the Qt Start All progress dialog."""
    from .start_all_progress_dialog import StartAllProgressDialog

    return StartAllProgressDialog


def _react_start_all_progress() -> type:
    """Import and return the React Start All progress dialog."""
    from .react_start_all_progress import StartAllProgressReactDialog

    return StartAllProgressReactDialog


def _qt_simulator() -> type:
    """Import and return the Qt Sim tab."""
    from .simulator_tab import SimulatorTabQt

    return SimulatorTabQt


def _react_simulator() -> type:
    """Import and return the React Sim tab."""
    from .react_simulator_tab import SimulatorTabReact

    return SimulatorTabReact


def _qt_buy_confirmation() -> type:
    """Import and return the Qt buy confirmation dialog."""
    from .buy_confirmation_dialog import BuyConfirmationDialog

    return BuyConfirmationDialog


def _react_buy_confirmation() -> type:
    """Import and return the React buy confirmation dialog."""
    from .react_buy_confirmation import BuyConfirmationReactDialog

    return BuyConfirmationReactDialog


register(ALERTS, _qt_alerts, _react_alerts)
register(HISTORY, _qt_history, _react_history)
register(HISTORY_TABLE, _qt_history_table, _react_history_table)
register(MAIN_TAB_BOOK, _qt_main_tab_book, _react_main_tab_book)
register(EMPTY_TAB, _qt_empty_tab, _react_empty_tab)
register(BOT_SWARM, _qt_bot_swarm, _react_bot_swarm)
register(CONSOLE, _qt_console, _react_console)
register(MARKET_INSPECTOR, _qt_market_inspector, _react_market_inspector)
register(SETTINGS_DIALOG, _qt_settings_dialog, _react_settings_dialog)
register(BOT_LIVE_SETTINGS, _qt_bot_live_settings, _react_bot_live_settings)
register(SPENDABLE_PROFITS, _qt_spendable_profits, _react_spendable_profits)
register(DASHBOARD_STAT_CARD, _qt_dashboard_stat_card, _react_dashboard_stat_card)
register(START_ALL_PROGRESS, _qt_start_all_progress, _react_start_all_progress)
register(BUY_CONFIRMATION, _qt_buy_confirmation, _react_buy_confirmation)
register(SIMULATOR, _qt_simulator, _react_simulator)
