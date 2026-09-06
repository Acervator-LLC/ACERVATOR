# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""One decision point for the Qt or the React build of a screen.

``register`` records a screen's two loaders. ``surface_class`` returns the
class the running variant selects and ``draws_react`` answers which side
that is. ``screens`` names every screen that carries both.
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple

from src._variant import QT, resolve_variant

BOT_LIVE_SETTINGS = "Bot live settings"
BOT_SWARM = "Bot Swarm"
CONSOLE = "Console"
HISTORY = "History"
HISTORY_TABLE = "History table"
MARKET_INSPECTOR = "Market Inspector"
FLEET_REPLAY = "Fleet replay panel"
GATE_STATUS_PANEL = "Gate status panel"
NUCLEAR_MODE = "Nuclear Mode"
SETTINGS_DIALOG = "Settings dialog"
SIM_PRICE_CHART = "Sim price chart"
SIM_STAT_STRIP = "Sim stat strip"

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


def _qt_market_inspector() -> type:
    """Import and return the Qt Market Inspector tab."""
    from .market_inspector import MarketInspectorTab

    return MarketInspectorTab


def _react_market_inspector() -> type:
    """Import and return the React Market Inspector tab."""
    from .react_market_inspector_tab import MarketInspectorReactTab

    return MarketInspectorReactTab


def _qt_nuclear_mode() -> type:
    """Import and return the Qt Nuclear Mode panel."""
    from .simulator_tab.nuclear_mode_panel import NuclearModePanel

    return NuclearModePanel


def _react_nuclear_mode() -> type:
    """Import and return the React Nuclear Mode panel."""
    from .react_nuclear_mode_panel import NuclearModeReactPanel

    return NuclearModeReactPanel


def _qt_fleet_replay() -> type:
    """Import and return the Qt Fleet Replay panel."""
    from .simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

    return FleetReplayPanel


def _react_fleet_replay() -> type:
    """Import and return the React Fleet Replay panel."""
    from .react_fleet_replay_panel import FleetReplayReactPanel

    return FleetReplayReactPanel


def _qt_gate_status_panel() -> type:
    """Import and return the Qt gate status panel."""
    from .simulator_tab.fleet.sim_visuals import GateStatusPanel

    return GateStatusPanel


def _react_gate_status_panel() -> type:
    """Import and return the React gate status panel."""
    from .react_sim_visuals import GateStatusPanelReact

    return GateStatusPanelReact


def _qt_sim_price_chart() -> type:
    """Import and return the Qt Simulator price and VWAP chart."""
    from .simulator_tab.fleet.sim_visuals import SimPriceVwapChart

    return SimPriceVwapChart


def _react_sim_price_chart() -> type:
    """Import and return the React Simulator price and VWAP chart."""
    from .react_sim_visuals import SimPriceVwapChartReact

    return SimPriceVwapChartReact


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


def _qt_sim_stat_strip() -> type:
    """Import and return the Qt Simulator stat strip."""
    from .simulator_tab.sim_stat_strip import SimStatStrip

    return SimStatStrip


def _react_sim_stat_strip() -> type:
    """Import and return the React Simulator stat strip."""
    from .react_sim_stat_strip import SimStatStripWebStrip

    return SimStatStripWebStrip


register(HISTORY, _qt_history, _react_history)
register(HISTORY_TABLE, _qt_history_table, _react_history_table)
register(BOT_SWARM, _qt_bot_swarm, _react_bot_swarm)
register(CONSOLE, _qt_console, _react_console)
register(MARKET_INSPECTOR, _qt_market_inspector, _react_market_inspector)
register(NUCLEAR_MODE, _qt_nuclear_mode, _react_nuclear_mode)
register(SIM_PRICE_CHART, _qt_sim_price_chart, _react_sim_price_chart)
register(GATE_STATUS_PANEL, _qt_gate_status_panel, _react_gate_status_panel)
register(FLEET_REPLAY, _qt_fleet_replay, _react_fleet_replay)
register(SIM_STAT_STRIP, _qt_sim_stat_strip, _react_sim_stat_strip)
register(SETTINGS_DIALOG, _qt_settings_dialog, _react_settings_dialog)
register(BOT_LIVE_SETTINGS, _qt_bot_live_settings, _react_bot_live_settings)
