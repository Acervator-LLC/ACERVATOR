"""The analytics tab paints the same colours after the token migration.

A failure means a `design_system` token edit, or a change to
`src/gui/analytics_tab.py`, moved pixels in the operator's live GUI.

Every expected colour is the LITERAL the file shipped before the tokens
replaced it. An assertion fed by the token it measures cannot falsify that
token: both sides move together and a wrong colour passes.

Colours are read off the RENDER. `QPainter` calls and stylesheet strings
report what the widget was told to paint, not what reached the screen.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

CHART_SIZE = (640, 320)
TAB_SIZE = (1200, 700)
CARD_SIZE = (220, 90)

CHART_GROUND = "#0a0a12"
CHART_PLACEHOLDER = "#555555"
CHART_VALUE = "#e0e0f0"
CHART_FLOOR = "#666666"
CURVE_UP = "#00ff88"
CURVE_DOWN = "#ff3366"
CARD_BORDER = "#2a2a3f"
GROUP_TITLE = "#00ffcc"
DRAWDOWN_AMBER = "#ffaa00"

# The gridline pen is #1a1a2e drawn antialiased over CHART_GROUND, so no
# pixel carries the pen colour itself. This is the blend it lands on.
GRID_BLEND = "#121220"
GRID_POINT = (45, 100)

RISING = [100.0, 101.0, 100.5, 103.0, 104.5]
FALLING = [104.5, 103.0, 100.5, 99.0, 97.0]


def _curve(equities):
    return [{"timestamp": 1000 + i * 60, "equity": e} for i, e in enumerate(equities)]


def _count_colour(image, expected_hex: str) -> int:
    """Pixels in `image` whose painted colour equals `expected_hex`."""
    from PySide6.QtGui import QColor

    want = QColor(expected_hex).rgb()
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).rgb() == want
    )


class _Perf:
    """One row of the per-bot performance table."""

    def __init__(self, pnl: float):
        self.bot_id = "abcdef1234"
        self.symbol = "BTC/USD"
        self.total_trades = 7
        self.win_rate = 57.5
        self.total_pnl = pnl
        self.profit_factor = 1.75
        self.sharpe_ratio = 0.9
        self.max_drawdown_pct = 4.25
        self.avg_hold_seconds = 3600
        self.expectancy = 1.0


class _Engine:
    """The analytics engine surface `AnalyticsTab.refresh` reads."""

    def __init__(self, pnl: float):
        self._pnl = pnl

    def get_portfolio_summary(self):
        return {
            "total_pnl": self._pnl,
            "win_rate": 57.5,
            "sharpe_ratio": 0.9,
            "profit_factor": 1.75,
            "total_trades": 7,
            "max_drawdown": 4.25,
            "expectancy": 1.0,
            "trades_today": 3,
        }

    def get_equity_curve(self, hours: int = 24):
        return _curve(RISING if self._pnl >= 0 else FALLING)[-hours:]

    def get_bot_performance(self):
        return [_Perf(self._pnl), _Perf(-self._pnl)]

    def get_timeframe_comparison(self):
        return {"1h": {"total_trades": 4, "win_rate": 50.0, "total_pnl": 1.0}}

    def _format_duration(self, seconds: float) -> str:
        return f"{int(seconds) // 3600}h {int(seconds) % 3600 // 60}m"


def _chart(equities=None):
    from src.gui.analytics_tab import MiniEquityChart

    widget = MiniEquityChart()
    if equities is not None:
        widget.set_data(_curve(equities))
    return widget


def test_empty_chart_paints_its_ground_and_placeholder() -> None:
    """A failure means the empty-state chart changed colour."""
    from tests.qt_pixel import ensure_app, render_widget

    ensure_app()
    image = render_widget(_chart(), size=CHART_SIZE)
    assert _count_colour(image, CHART_GROUND) > CHART_SIZE[0] * CHART_SIZE[1] // 2
    assert _count_colour(image, CHART_PLACEHOLDER) > 0


def test_chart_gridline_paints_its_blend() -> None:
    """A failure means the gridline pen or the ground behind it changed."""
    from PySide6.QtCore import QPoint

    from tests.qt_pixel import assert_pixel_colour, ensure_app

    ensure_app()
    assert_pixel_colour(
        _chart(RISING), QPoint(*GRID_POINT), GRID_BLEND, size=CHART_SIZE
    )


def test_rising_curve_paints_the_gain_colour_only() -> None:
    """A failure means the gain curve, its labels or the loss colour moved."""
    from tests.qt_pixel import ensure_app, render_widget

    ensure_app()
    image = render_widget(_chart(RISING), size=CHART_SIZE)
    assert _count_colour(image, CURVE_UP) > 0
    assert _count_colour(image, CURVE_DOWN) == 0
    assert _count_colour(image, CHART_VALUE) > 0
    assert _count_colour(image, CHART_FLOOR) > 0


def test_falling_curve_paints_the_loss_colour_only() -> None:
    """A failure means the loss curve or the gain colour moved."""
    from tests.qt_pixel import ensure_app, render_widget

    ensure_app()
    image = render_widget(_chart(FALLING), size=CHART_SIZE)
    assert _count_colour(image, CURVE_DOWN) > 0
    assert _count_colour(image, CURVE_UP) == 0


def test_drawdown_card_paints_the_warning_colour() -> None:
    """A failure means the drawdown card no longer renders amber."""
    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.analytics_tab import MetricCard

    ensure_app()
    card = MetricCard("Max Drawdown")
    card.set_value("4.2%", DRAWDOWN_AMBER)
    image = render_widget(card, size=CARD_SIZE)
    assert _count_colour(image, DRAWDOWN_AMBER) > 0
    assert _count_colour(image, CARD_BORDER) > 0


@pytest.mark.parametrize("pnl", [12.5, -12.5])
def test_tab_paints_its_group_boxes_and_pnl_colours(pnl) -> None:
    """A failure means a group box, card or P/L cell repainted."""
    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.analytics_tab import AnalyticsTab

    ensure_app()
    tab = AnalyticsTab()
    tab.refresh(_Engine(pnl))
    image = render_widget(tab, size=TAB_SIZE)
    assert _count_colour(image, CHART_GROUND) > 0
    assert _count_colour(image, CARD_BORDER) > 0
    assert _count_colour(image, GROUP_TITLE) > 0
    assert _count_colour(image, DRAWDOWN_AMBER) > 0
    assert _count_colour(image, CURVE_UP) > 0
    assert _count_colour(image, CURVE_DOWN) > 0


def test_group_boxes_carry_and_render_the_shipped_stylesheet() -> None:
    """A failure means the QSS text changed, or the box stopped painting it."""
    from PySide6.QtWidgets import QGroupBox

    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.analytics_tab import AnalyticsTab

    ensure_app()
    tab = AnalyticsTab()
    shipped = {
        "Equity Curve": (
            "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
            "border-radius: 6px; color: #00ffcc; font-weight: bold; }"
        ),
        "Bot Performance": (
            "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
            "border-radius: 6px; color: #00ffcc; }"
        ),
        "Timeframe Performance": (
            "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
            "border-radius: 6px; color: #00ffcc; }"
        ),
    }
    boxes = [b for b in tab.findChildren(QGroupBox) if b.title() in shipped]
    assert {b.title(): b.styleSheet() for b in boxes} == shipped
    for box in boxes:
        image = render_widget(box, size=(400, 200))
        assert _count_colour(image, CHART_GROUND) > 0, box.title()
        assert _count_colour(image, CARD_BORDER) > 0, box.title()
        assert _count_colour(image, GROUP_TITLE) > 0, box.title()
