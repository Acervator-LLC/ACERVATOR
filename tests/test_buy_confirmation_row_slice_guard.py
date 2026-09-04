"""The detail-row slice refuses a template it no longer matches.

`_detail_row_value` cuts a row's value by the length of `<b>{label}</b>`.
That is right only while every template starts with exactly that. A
template edited to put the label anywhere else would leave the slice
cutting the wrong characters, and this dialog shows the figures of an
order about to be placed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import buy_confirmation_surface as surface

ARGS = {
    "symbol": "BTC/USD",
    "cost_usd": 100.0,
    "price": 50000.0,
    "amount_asset": 0.002,
    "holdings_before": 0.5,
    "target_balance": 250.0,
}


def test_every_row_value_comes_back_for_a_real_request():
    values = surface.detail_row_values(**ARGS)
    assert sorted(values) == sorted(surface.DETAIL_ROW_ORDER)
    assert all(isinstance(one, str) for one in values.values())


def test_every_template_starts_with_its_own_label():
    """The condition the slice rests on, asserted directly."""
    for row, whole in surface.detail_row_values(**ARGS).items():
        assert "<b>" not in whole, (row, whole)


@pytest.mark.parametrize("row", sorted(surface.DETAIL_ROW_LABELS))
def test_a_template_that_moved_its_label_is_refused(row):
    """The positive control: a line the prefix does not open is refused."""
    moved = f"the value first, then <b>{surface.DETAIL_ROW_LABELS[row]}</b>"
    with pytest.raises(ValueError) as refused:
        surface._detail_row_value(row, moved)
    assert row in str(refused.value)


def test_a_line_that_does_start_with_its_label_is_sliced():
    """The negative control: the same reading accepts a matching line."""
    row = surface.DETAIL_ROW_COST
    whole = f"<b>{surface.DETAIL_ROW_LABELS[row]}</b> $100.00{surface._ROW_END}"
    assert surface._detail_row_value(row, whole) == "$100.00"


@pytest.mark.parametrize(
    "row",
    sorted(
        one
        for one in surface.DETAIL_ROW_LABELS
        if surface._DETAIL_ROW_KEEPS_ROW_END[one]
    ),
)
def test_a_line_that_lost_its_row_end_is_refused(row):
    """Stripping the tail by length ate real digits: $100.00 became $10."""
    whole = f"<b>{surface.DETAIL_ROW_LABELS[row]}</b> $100.00"
    with pytest.raises(ValueError) as refused:
        surface._detail_row_value(row, whole)
    assert surface._ROW_END in str(refused.value)
