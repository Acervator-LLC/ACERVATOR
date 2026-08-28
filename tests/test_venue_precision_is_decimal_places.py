"""A venue's market precision reaches the order sizer as decimal places.

WHAT A FAILURE HERE MEANS, stated before the tests are read.

``BotContainer._get_market_limits`` returns ``amount_precision`` and
``guarded_place_order`` truncates the order size to that many decimal
places before comparing it against the venue minimum. The number must
therefore BE a count of decimal places.

CCXT only reports decimal places under ``DECIMAL_PLACES`` mode. Every
venue in the registry that answered a public ``load_markets`` on
2026-08-28 was in ``TICK_SIZE`` mode except Bitfinex, and under
``TICK_SIZE`` the same field carries a step size — ``1e-06``, ``0.01``,
``1.0``. Reading it with ``int(...)`` truncates every step below one to
zero, at which point an ``or 8`` fallback fires and the sizer is handed
the constant 8 for the market it just looked up.

THE MEASURED DEFECT THIS PINS. Driven against the unmodified expression
on 2026-08-28 over every active spot market each venue publishes:
886 of 929 Coinbase markets, 968 of 1437 Kraken, 2232 of 2232 Gate.io
and 2158 of 2159 HTX received the wrong amount precision. Coinbase is
the venue the operator trades on with real money, and BTC/USD is one of
the 43 markets the defect happens to get right, which is why a year of
live trading never surfaced it.

The fixture carries the raw CCXT values that produced those numbers,
so nothing here needs a network. Public market metadata only; no
credentials were used to capture it and none are needed to read it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.exchange.ccxt_connector import (
    CCXT_DECIMAL_PLACES,
    CCXT_SIGNIFICANT_DIGITS,
    CCXT_TICK_SIZE,
    CCXTConnector,
    precision_to_decimals,
)

FIXTURE = Path(__file__).parent / "fixtures" / "venue_precision_metadata.json"
MEASURED = json.loads(FIXTURE.read_text(encoding="utf-8"))
MARKETS = MEASURED["markets"]


class _MetadataBackend:
    """Minimum backend surface ``get_markets`` reads: markets + mode."""

    def __init__(self, markets: dict, precision_mode: int) -> None:
        self.markets = markets
        self.precisionMode = precision_mode


def _market_dict(row: dict) -> dict:
    base, _, quote = row["symbol"].partition("/")
    return {
        "symbol": row["symbol"],
        "base": base,
        "quote": quote,
        "active": True,
        "limits": {
            "amount": {"min": row["min_amount"]},
            "cost": {"min": row["min_cost"]},
        },
        "precision": {
            "amount": row["raw_precision_amount"],
            "price": row["raw_precision_price"],
        },
        "maker": 0.004,
        "taker": 0.006,
    }


@pytest.mark.parametrize("row", MARKETS, ids=[r["exchange"] for r in MARKETS])
def test_measured_venue_metadata_yields_the_decimal_places_the_venue_allows(row):
    """Each venue's real published precision converts to its real step."""
    assert (
        precision_to_decimals(row["raw_precision_amount"], row["precision_mode"])
        == row["expected_amount_decimals"]
    )
    assert (
        precision_to_decimals(row["raw_precision_price"], row["precision_mode"])
        == row["expected_price_decimals"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("row", MARKETS, ids=[r["exchange"] for r in MARKETS])
async def test_the_sizer_sees_the_venue_step_not_the_fallback_constant(row):
    """``get_markets`` is the only producer of ``AssetInfo.amount_precision``
    and ``BotContainer`` truncates a live order size with it. Drive the real
    producer with the real metadata and read the field the sizer reads."""
    conn = CCXTConnector("coinbase")
    conn.attach_backend(
        _MetadataBackend({row["symbol"]: _market_dict(row)}, row["precision_mode"])
    )
    assets = await conn.get_markets()
    assert len(assets) == 1
    assert assets[0].amount_precision == row["expected_amount_decimals"]
    assert assets[0].price_precision == row["expected_price_decimals"]


def test_a_tick_size_below_one_is_not_truncated_to_the_fallback():
    """The defect's exact shape: ``int(1e-06)`` is 0, 0 is falsy, and the
    ``or 8`` fallback then answers for a market that published its step."""
    assert precision_to_decimals(1e-06, CCXT_TICK_SIZE) == 6
    assert precision_to_decimals(0.01, CCXT_TICK_SIZE) == 2
    assert precision_to_decimals(0.1, CCXT_TICK_SIZE) == 1
    assert precision_to_decimals(1e-08, CCXT_TICK_SIZE) == 8


def test_a_whole_unit_tick_means_zero_decimal_places():
    """Gate.io publishes ``1.0`` as an amount step on markets that trade in
    whole units. ``int(1.0)`` is 1 and truthy, so the fallback does NOT
    fire and the old reading returned 1 — one decimal place on a market
    that accepts none."""
    assert precision_to_decimals(1.0, CCXT_TICK_SIZE) == 0
    assert precision_to_decimals(10.0, CCXT_TICK_SIZE) == 0


def test_decimal_places_mode_passes_the_count_through():
    """The tablet backend publishes integer decimal places and declares no
    ``precisionMode``; ``get_markets`` defaults to this mode so the
    Simulator path keeps the exact number it publishes."""
    assert precision_to_decimals(8, CCXT_DECIMAL_PLACES) == 8
    assert precision_to_decimals(2, CCXT_DECIMAL_PLACES) == 2


def test_significant_digits_mode_refuses_to_invent_a_decimal_count():
    """Bitfinex reports significant digits. A decimal-place count does not
    exist independently of the number being rounded, so the caller's own
    default answers rather than the digit count being misread as places."""
    assert precision_to_decimals(5, CCXT_SIGNIFICANT_DIGITS) == 8
    assert precision_to_decimals(5, CCXT_SIGNIFICANT_DIGITS, default=0) == 0


@pytest.mark.parametrize(
    "bad", [None, "", "abc", float("nan"), float("inf"), 0, -1, -0.5]
)
def test_an_unusable_precision_value_falls_back_rather_than_raising(bad):
    """Market metadata is venue-supplied. A missing or nonsense value must
    reach the caller's default, not an exception on the order path."""
    assert precision_to_decimals(bad, CCXT_TICK_SIZE, default=8) == 8


def test_the_fixture_records_a_defect_that_was_actually_present():
    """The red side of this control is a measurement, not an invention: the
    fixture carries what the old expression produced for each venue, and it
    must disagree with the truth on the rows the sweep found wrong."""
    disagreeing = [
        r
        for r in MARKETS
        if r["legacy_amount_decimals"] != r["expected_amount_decimals"]
        or r["legacy_price_decimals"] != r["expected_price_decimals"]
    ]
    assert len(disagreeing) == 13, [r["exchange"] for r in disagreeing]
