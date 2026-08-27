"""The shared StatCard paints each skin exactly as its own card did.

A failure here means a token edit, or a change to `src/gui/widgets.py`,
moved pixels in the operator's live GUI. Every expected colour below is
the LITERAL the card shipped before the classes were merged.

WHY LITERALS AND NOT TOKENS
==========================
Measured 2026-08-27: an earlier draft asserted the render against
`design_system.CARD_STOCK_SURFACE`. Changing that token from #0e1428 to
#0e1429 left every test GREEN, because the expected value and the
painted value moved together. An assertion fed by the thing it measures
cannot falsify it. The hex strings here are the pin, and
`test_card_tokens_hold_the_shipped_values` is what ties the tokens to
them.

EVERY COLOUR CLAIM IS READ OFF THE RENDER
=========================================
`card.styleSheet()` reports what the widget was TOLD to paint, and a
stylesheet rule for the same element overrides it while the getter keeps
returning the old string. Colours are sampled through `tests/qt_pixel.py`
so each assertion reads the surface the operator reads.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

STOCK_SIZE = (220, 90)
METRIC_SIZE = (220, 90)

INTERIOR = (110, 45)
LEFT_EDGE = (0, 45)

STOCK_SURFACE = "#0e1428"
STOCK_BORDER = "#1a2a4f"
STOCK_LABEL = "#6688aa"
STOCK_VALUE = "#e0e8f0"
METRIC_SURFACE = "#12121f"
METRIC_BORDER = "#2a2a3f"
METRIC_LABEL = "#888"
METRIC_VALUE = "#e0e0f0"
DRAWDOWN_AMBER = "#ffaa00"


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


def _margins(card) -> tuple[int, int, int, int]:
    m = card.layout().contentsMargins()
    return m.left(), m.top(), m.right(), m.bottom()


def test_card_tokens_hold_the_shipped_values() -> None:
    """If this fails a card token was edited. These are the colours the
    cards painted before they were merged into one class, so a change
    here is a product decision, not a refactor."""
    from src.gui import design_system as ds

    assert ds.CARD_STOCK_SURFACE == STOCK_SURFACE
    assert ds.CARD_STOCK_BORDER == STOCK_BORDER
    assert ds.CARD_STOCK_LABEL == STOCK_LABEL
    assert ds.CARD_STOCK_VALUE == STOCK_VALUE
    assert ds.CARD_METRIC_SURFACE == METRIC_SURFACE
    assert ds.CARD_METRIC_BORDER == METRIC_BORDER
    assert ds.CARD_METRIC_LABEL == METRIC_LABEL
    assert ds.TEXT_HIGH == METRIC_VALUE
    assert (ds.TYPE_CARD_VALUE, ds.TYPE_CAPTION) == (16, 10)
    assert (ds.RADIUS_SM, ds.RADIUS_CARD) == (8, 6)


def test_stock_stat_card_paints_its_skin() -> None:
    """If this fails the stock window's cards stopped painting #0e1428
    inside #1a2a4f, so the QSS type selector no longer matches the
    subclass."""
    from PySide6.QtCore import QPoint

    from tests.qt_pixel import assert_pixel_colour, ensure_app, render_widget
    from src.gui.stock_main_window import StockStatCard

    ensure_app()
    card = StockStatCard("Open P/L", "$12,345.67")
    assert_pixel_colour(card, QPoint(*INTERIOR), STOCK_SURFACE, size=STOCK_SIZE)
    assert_pixel_colour(card, QPoint(*LEFT_EDGE), STOCK_BORDER, size=STOCK_SIZE)

    image = render_widget(card, size=STOCK_SIZE)
    assert _count_colour(image, STOCK_LABEL) > 0
    assert _count_colour(image, STOCK_VALUE) > 0
    assert card.accessibleName() == "Stock Stat Card"
    assert _margins(card) == (12, 10, 12, 10)
    assert card.layout().spacing() == 2


def test_metric_card_paints_its_skin() -> None:
    """If this fails the analytics cards stopped painting #12121f inside
    #2a2a3f, so the QSS type selector no longer matches the subclass."""
    from PySide6.QtCore import QPoint

    from tests.qt_pixel import assert_pixel_colour, ensure_app, render_widget
    from src.gui.analytics_tab import MetricCard

    ensure_app()
    card = MetricCard("Win Rate", "61.4%")
    assert_pixel_colour(card, QPoint(*INTERIOR), METRIC_SURFACE, size=METRIC_SIZE)
    assert_pixel_colour(card, QPoint(*LEFT_EDGE), METRIC_BORDER, size=METRIC_SIZE)

    image = render_widget(card, size=METRIC_SIZE)
    assert _count_colour(image, METRIC_LABEL) > 0
    assert _count_colour(image, METRIC_VALUE) > 0
    assert card.accessibleName() == "Metric Card"
    assert _margins(card) == (10, 8, 10, 8)


def test_set_value_keeps_the_skin_colour() -> None:
    """If this fails a card's value changes colour the moment the
    dashboard writes to it."""
    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.analytics_tab import MetricCard
    from src.gui.stock_main_window import StockStatCard

    ensure_app()
    stock = StockStatCard("Open P/L")
    stock.set_value("$12,345.67")
    assert stock._value.text() == "$12,345.67"
    assert _count_colour(render_widget(stock, size=STOCK_SIZE), STOCK_VALUE) > 0

    metric = MetricCard("Win Rate")
    metric.set_value("61.4%")
    assert _count_colour(render_widget(metric, size=METRIC_SIZE), METRIC_VALUE) > 0


def test_set_value_colour_override_reaches_the_render() -> None:
    """If this fails a drawdown stops rendering amber at the callsites
    that pass a colour positionally."""
    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.analytics_tab import MetricCard

    ensure_app()
    card = MetricCard("Max Drawdown")
    card.set_value("-3.1%", DRAWDOWN_AMBER)
    image = render_widget(card, size=METRIC_SIZE)
    assert _count_colour(image, DRAWDOWN_AMBER) > 0
    assert _count_colour(image, METRIC_VALUE) == 0
