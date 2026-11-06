# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Bridge methods of the surfaces behind the tabs ``MainWindow`` does not build.

``on_demand_handlers`` imports each surface on the first request for its method.
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable

ALERTS_TAB_METHOD = "alerts_tab.state"
ANALYTICS_TAB_METHOD = "analytics.tab"
AUDIO_SUITE_METHOD = "audio_suite.state"
COMPETITION_TAB_METHOD = "competition_tab.state"
JOURNAL_TAB_METHOD = "journal_tab.state"
RISK_TAB_METHOD = "risk_tab.state"
TESTNET_TAB_METHOD = "testnet_tab.state"

#: The ``src.gui.main_tabs`` module that answers each method.
SURFACE_MODULES: dict[str, str] = {
    ALERTS_TAB_METHOD: "alerts_tab_surface",
    ANALYTICS_TAB_METHOD: "analytics_tab_surface",
    AUDIO_SUITE_METHOD: "audio_suite_surface",
    COMPETITION_TAB_METHOD: "competition_tab_surface",
    JOURNAL_TAB_METHOD: "journal_tab_surface",
    RISK_TAB_METHOD: "risk_tab_surface",
    TESTNET_TAB_METHOD: "testnet_tab_surface",
}


def on_demand_handlers() -> dict[str, Callable[[dict], dict]]:
    """Return one handler per ``SURFACE_MODULES`` method, unimported until called.

    A method whose module ``_is_carried`` cannot find gets no handler.
    """
    return {
        method: _handler(module)
        for method, module in SURFACE_MODULES.items()
        if _is_carried(module)
    }


def _is_carried(module_name: str) -> bool:
    """Return True when ``find_spec`` finds ``module_name`` beside this module."""
    return importlib.util.find_spec("." + module_name, __package__) is not None


def _handler(module_name: str) -> Callable[[dict], dict]:
    """Return a handler that imports ``module_name`` and answers its ``view_model``."""

    def answer(params: dict) -> dict:
        surface = importlib.import_module("src.gui.main_tabs." + module_name)
        return surface.view_model(params)

    return answer
