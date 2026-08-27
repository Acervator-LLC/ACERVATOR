"""Byte-identical output pins for the adaptive-precision price formatters.

The ladder in src/core/fmt.py was reimplemented in ccxt_connector and in
native_chart. The two ccxt copies were folded into fmt.py; the chart's
ladder is a DIFFERENT ladder and stays where it is. These tests pin the
output of every survivor against a frozen copy of the pre-consolidation
code, so any drift in a rendered price shows up as a failing string.
"""

from __future__ import annotations

import pytest

from src.core.fmt import fmt_price, fmt_price_coerced, fmt_price_raw
import src.gui.native_chart as native_chart

GRID = [
    0,
    0.0,
    -0.0,
    None,
    "0.005",
    "42.5",
    "",
    "not-a-number",
    1e-12,
    0.00009,
    0.0001,
    0.005,
    0.01,
    0.5,
    0.999999,
    1,
    1.0,
    42.5,
    999.99,
    999.9999,
    1000,
    1000.0,
    1e6,
    -0.00009,
    -0.005,
    -0.5,
    -1.0,
    -42.5,
    -1000.0,
    -1e6,
    float("nan"),
    float("inf"),
    float("-inf"),
    True,
]


def _legacy_fmt_price(value: float) -> str:
    """Frozen copy of src/core/fmt.py::fmt_price before consolidation."""
    if value == 0:
        return "$0.00"
    av = abs(value)
    if av >= 1000:
        return f"${value:,.2f}"
    elif av >= 1:
        return f"${value:.4f}"
    elif av >= 0.01:
        return f"${value:.6f}"
    else:
        return f"${value:.8f}"


def _legacy_fmt_price_raw(value: float) -> str:
    """Frozen copy of src/core/fmt.py::fmt_price_raw before consolidation."""
    if value == 0:
        return "0.00"
    av = abs(value)
    if av >= 1000:
        return f"{value:,.2f}"
    elif av >= 1:
        return f"{value:.4f}"
    elif av >= 0.01:
        return f"{value:.6f}"
    else:
        return f"{value:.8f}"


def _legacy_fmt_p(value) -> str:
    """Frozen copy of ccxt_connector.py::_fmt_p before it was deleted."""
    v = float(value or 0)
    if v == 0:
        return "0"
    av = abs(v)
    if av >= 1000:
        return f"{v:,.2f}"
    elif av >= 1:
        return f"{v:.4f}"
    elif av >= 0.01:
        return f"{v:.6f}"
    else:
        return f"{v:.8f}"


def _legacy_chart_fmt_price(price: float) -> str:
    """Frozen copy of native_chart.py::_fmt_price. Kept, not consolidated."""
    if price < 0.0001:
        return f"{price:.8f}"
    elif price < 0.01:
        return f"{price:.6f}"
    elif price < 1:
        return f"{price:.4f}"
    elif price < 1000:
        return f"{price:.2f}"
    else:
        return f"{price:,.2f}"


def _outcome(fn, value):
    """Return the returned string, or the exception type name prefixed by '!'."""
    try:
        return fn(value)
    except Exception as exc:  # noqa: BLE001
        return f"!{type(exc).__name__}"


@pytest.mark.parametrize("value", GRID, ids=repr)
def test_fmt_price_raw_matches_its_pre_consolidation_output(value):
    """A failure means a log line or GUI label prints a different price."""
    assert _outcome(fmt_price_raw, value) == _outcome(_legacy_fmt_price_raw, value)


@pytest.mark.parametrize("value", GRID, ids=repr)
def test_fmt_price_matches_its_pre_consolidation_output(value):
    """A failure means a $-prefixed price label changed."""
    assert _outcome(fmt_price, value) == _outcome(_legacy_fmt_price, value)


@pytest.mark.parametrize("value", GRID, ids=repr)
def test_fmt_price_coerced_matches_the_deleted_ccxt_helper(value):
    """A failure means an exchange API log line prints a different price."""
    assert _outcome(fmt_price_coerced, value) == _outcome(_legacy_fmt_p, value)


def test_ccxt_connector_no_longer_defines_its_own_ladder():
    """A failure means the duplicate ccxt formatter came back."""
    import src.exchange.ccxt_connector as cc

    assert not hasattr(cc, "_fmt_p")
    assert cc.fmt_price_coerced is fmt_price_coerced


@pytest.mark.skipif(not native_chart._HAS_QT, reason="PySide6 not available")
@pytest.mark.parametrize("value", GRID, ids=repr)
def test_chart_fmt_price_is_unchanged(value):
    """A failure means a chart axis or OHLC label changed. It must not."""
    from tests.qt_pixel import ensure_app

    ensure_app()
    chart = native_chart.CandlestickChart()
    assert _outcome(chart._fmt_price, value) == _outcome(_legacy_chart_fmt_price, value)


CHART_DIVERGES_FROM_CANONICAL = {
    0.0: ("0.00000000", "0.00"),
    0.005: ("0.005000", "0.00500000"),
    0.5: ("0.5000", "0.500000"),
    42.5: ("42.50", "42.5000"),
    -42.5: ("-42.50000000", "-42.5000"),
}


@pytest.mark.skipif(not native_chart._HAS_QT, reason="PySide6 not available")
@pytest.mark.parametrize("value", sorted(CHART_DIVERGES_FROM_CANONICAL), ids=repr)
def test_chart_ladder_is_deliberately_not_the_canonical_ladder(value):
    """A failure means the chart was folded into fmt.py and labels moved.

    Four bands disagree: zero, 0.0001<=p<0.01, 0.01<=p<1, 1<=p<1000, plus
    every negative value, which the chart's ladder sends to .8f for want
    of an abs(). Whether an axis shows 2 or 4 decimals is a product call.
    """
    from tests.qt_pixel import ensure_app

    ensure_app()
    chart = native_chart.CandlestickChart()
    expected_chart, expected_canonical = CHART_DIVERGES_FROM_CANONICAL[value]
    assert chart._fmt_price(value) == expected_chart
    assert fmt_price_raw(value) == expected_canonical
