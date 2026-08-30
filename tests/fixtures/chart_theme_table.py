"""The shipped chart's theme table, and a way to put it back.

``TradingViewChart`` writes the symbol into the shared theme row it reads,
so any test that builds one leaves that row changed for the rest of the
process. Tests that read the table, and tests that build a chart, call
``restore_chart_themes`` so neither depends on what ran before it.
"""

from __future__ import annotations

from src.gui.tradingview_chart import CHART_THEMES

PRISTINE_CHART_THEMES = {name: dict(row) for name, row in CHART_THEMES.items()}


def restore_chart_themes() -> None:
    """Put the shared theme table back to what the shipped module defined."""
    for name in [name for name in CHART_THEMES if name not in PRISTINE_CHART_THEMES]:
        del CHART_THEMES[name]
    for name, row in PRISTINE_CHART_THEMES.items():
        CHART_THEMES.setdefault(name, {})
        CHART_THEMES[name].clear()
        CHART_THEMES[name].update(row)
