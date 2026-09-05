"""The shipped bot-table cells and the Qt-free surface, side by side.

A failure means the view model returns a different Ammo cell, a
different Target-denom cell, a different display price, a different
colour, a different tooltip or a different debug log than
``_compose_ammo_cell``, ``_compose_table_target_denom_cell``,
``_fresh_display_price`` and ``_ammo_price_pool``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import table_cells as shipped
from src.gui.main_tabs import table_cells_surface as surface
from tests.fixtures.qt_wiring_counts import qt_free
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

CELLS_PATH = REPO_ROOT / "src/gui/table_cells.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/table_cells_surface.py"
CALLER_PATH = REPO_ROOT / "src/gui/widgets/bot_status_table.py"

LOGGER_NAME = "acervator.gui"

PIXEL_SIZE = (900, 120)

CALLS: list[list] = []

CLOCK_NOW = 1_700_000_000.0

# Typed out, not read from the surface, so the two sides cannot agree by
# definition. `test_the_cell_placement_is_the_tables_own` checks each.
CALLER_TARGET_BTC_COLUMN = 5
CALLER_TARGET_ETH_COLUMN = 6
CALLER_AMMO_COLUMN = 7
CALLER_COLUMN_COUNT = 10
CALLER_ALIGNMENT_VALUE = 132
CALLER_AMMO_MASK_KEY = "bot_table.ammo"
CALLER_TARGET_MASK_KEY = "bot_table.target"

# The three colours the design system ships for these cells, typed out
# so a renamed token cannot move both sides together.
SUCCESS_HEX = "#00ff88"
ERROR_HEX = "#ff3366"
TEXT_MED_HEX = "#a8a8c5"

STALE_MARKER_TEXT = "(stale)"
NO_TARGET_DASHES = "---"
PENDING_PRICE_WORD = "pending…"
PENDING_RATE_WORD = "pending"
UNLISTED_DASH = "—"

UNICODE_ASSET = "Δ→⚡"
MARKUP_ASSET = "<b>BTC</b>"
LONG_ASSET = "X" * 200
LONG_SYMBOL = "X" * 200 + "/USD"

FILLER_TEXT = "row"

# The collaborators both sides reach, each recording what it was asked.


class FakeTicker:
    """One cached ticker entry, with the two fields the reader wants."""

    def __init__(self, last, fetch_time):
        self.last = last
        self.fetch_time = fetch_time


class FakePool:
    """A price cache whose one call is recorded and steerable."""

    def __init__(self, entries=None, error=None, truthy=True):
        self.entries = dict(entries or {})
        self.error = error
        self.truthy = truthy

    def __bool__(self):
        return self.truthy

    def get_ticker(self, exchange_id, symbol):
        CALLS.append([surface.PRICE_LOOKUP, exchange_id, symbol])
        if self.error is not None:
            raise self.error
        return self.entries.get((exchange_id, symbol))


class FakeRates:
    """The two spot rates the Target-denom cell divides by."""

    def __init__(self, btc_usd, eth_usd):
        self.btc_usd = btc_usd
        self.eth_usd = eth_usd


class FakeMonitor:
    """A currency monitor whose snapshot is recorded."""

    def __init__(self, rates, error=None):
        self.rates = rates
        self.error = error

    def snapshot(self):
        if self.error is not None:
            raise self.error
        CALLS.append([surface.DENOM_RATES, self.rates.btc_usd, self.rates.eth_usd])
        return self.rates


class FakePair:
    """One listed pair, carrying the 24-hour change the cell reads."""

    def __init__(self, pct_24h):
        self.pct_24h = pct_24h


class FakeScout:
    """A pair scout whose every lookup is recorded and steerable."""

    def __init__(self, pairs=None, error=None):
        self.pairs = dict(pairs or {})
        self.error = error

    def get_pair(self, base, quote, exchange_id=None):
        CALLS.append([surface.DENOM_PAIR, base, quote, exchange_id])
        if self.error is not None:
            raise self.error
        return self.pairs.get((base, quote))


def install_pool(monkeypatch, spec):
    """Put one steerable data pool in place of the shared one."""
    module = types.ModuleType("src.exchange.data_pool")
    if spec.get("import_error"):

        def refuse(name, *args, **kwargs):
            raise ImportError("data_pool is unavailable")

        monkeypatch.setattr(
            "builtins.__import__", _refusing_import("src.exchange.data_pool")
        )
        return None
    pool = spec.get("pool")

    def get_data_pool():
        CALLS.append([surface.POOL_IMPORT, pool is not None])
        if spec.get("raises") is not None:
            raise spec["raises"]
        return pool

    module.get_data_pool = get_data_pool
    monkeypatch.setitem(sys.modules, "src.exchange.data_pool", module)
    return pool


def _refusing_import(blocked):
    """An import hook that refuses exactly one module name."""
    real = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if name == blocked or name.endswith(blocked.rsplit(".", 1)[-1]):
            if name.endswith("data_pool"):
                raise ImportError("data_pool is unavailable")
        return real(name, globals, locals, fromlist, level)

    return guarded


def install_market(monkeypatch, spec):
    """Put one steerable rate monitor and pair scout in place."""
    rates = FakeRates(spec.get("btc_usd", 60000.0), spec.get("eth_usd", 3000.0))
    monitor = FakeMonitor(rates, spec.get("monitor_error"))
    scout = FakeScout(spec.get("pairs"), spec.get("scout_error"))
    rate_module = types.ModuleType("src.exchange.currency_rate_monitor")
    rate_module.get_currency_monitor = lambda: monitor
    scout_module = types.ModuleType("src.exchange.market_pairs_scout")
    if spec.get("scout_missing"):

        def refuse_scout():
            raise RuntimeError("the pair scout is not built")

        scout_module.get_scout = refuse_scout
    else:
        scout_module.get_scout = lambda: scout
    monkeypatch.setitem(sys.modules, "src.exchange.currency_rate_monitor", rate_module)
    monkeypatch.setitem(sys.modules, "src.exchange.market_pairs_scout", scout_module)
    return monitor, scout


def freeze_clock(monkeypatch):
    """Both sides read one fixed wall clock, so an age is reproducible."""
    monkeypatch.setattr(time, "time", lambda: CLOCK_NOW)


# The engine calls both cells make, wrapped so the trace is real.

TERRITORY_ASK = "band.territory"
DUST_ASK = "band.dust"
NOOP_ASK = "band.noop"


def watch_bands(monkeypatch, module):
    """Record every band question `module` asks, and answer it for real."""
    from src.trading import target_bands

    def watched_territory(position_value, target_balance):
        answer = target_bands.target_territory(position_value, target_balance)
        CALLS.append([TERRITORY_ASK, position_value, target_balance, answer])
        return answer

    def watched_dust(target_balance):
        answer = target_bands.manual_fire_dust_band(target_balance)
        CALLS.append([DUST_ASK, target_balance, answer])
        return answer

    def watched_noop(position_value, target_balance):
        answer = target_bands.manual_fire_will_noop(position_value, target_balance)
        CALLS.append([NOOP_ASK, position_value, target_balance, answer])
        return answer

    monkeypatch.setattr(module, "target_territory", watched_territory)
    monkeypatch.setattr(module, "manual_fire_dust_band", watched_dust)
    monkeypatch.setattr(module, "manual_fire_will_noop", watched_noop)


# Cases

AMMO_CASES = {
    "scrum": (0.0, 5.0, 20.0, 1.0, 50.0, None),
    "fold": (0.0, 5.0, 5.0, 1.0, 50.0, None),
    "at_target": (0.0, 5.0, 10.0, 1.0, 50.0, None),
    "at_target_edge": (0.0, 5.0, 10.0, 1.0, 50.005, None),
    "manual_fire_noop": (0.0, 5.0, 10.06, 1.0, 50.0, None),
    "manual_fire_noop_fold": (0.0, 5.0, 9.94, 1.0, 50.0, None),
    "empty": (0.0, 0.0, 0.0, 1.0, 50.0, None),
    "empty_no_target": (0.0, 0.0, 0.0, 1.0, 0.0, None),
    "empty_negative_target": (0.0, 0.0, 0.0, 1.0, -50.0, None),
    "pending": (0.0, 5.0, 0.0, 1.0, 50.0, None),
    "pending_tiny_holdings": (0.0, 1e-08, 0.0, 1.0, 50.0, None),
    "pending_huge_holdings": (0.0, 1e18, 0.0, 1.0, 50.0, None),
    "stale": (100.0, 0.0, 0.0, 1.0, 50.0, None),
    "stale_no_price": (100.0, 5.0, 0.0, 1.0, 50.0, None),
    "stale_and_noop": (50.4, 0.0, 0.0, 1.0, 50.0, None),
    "aged_price": (0.0, 5.0, 20.0, 1.0, 50.0, 25.0),
    "aged_price_edge": (0.0, 5.0, 20.0, 1.0, 50.0, 20.0),
    "aged_price_just_over": (0.0, 5.0, 20.0, 1.0, 50.0, 20.0000001),
    "aged_price_huge": (0.0, 5.0, 20.0, 1.0, 50.0, 1e9),
    "fresh_price_age": (0.0, 5.0, 20.0, 1.0, 50.0, 2.0),
    "zero_price_age": (0.0, 5.0, 20.0, 1.0, 50.0, 0.0),
    "negative_price_age": (0.0, 5.0, 20.0, 1.0, 50.0, -5.0),
    "no_target": (0.0, 5.0, 20.0, 1.0, 0.0, None),
    "negative_target": (0.0, 5.0, 20.0, 1.0, -50.0, None),
    "negative_holdings": (0.0, -5.0, 20.0, 1.0, 50.0, None),
    "negative_price": (0.0, 5.0, -20.0, 1.0, 50.0, None),
    "negative_stats": (-100.0, 0.0, 0.0, 1.0, 50.0, None),
    "zero_rate": (0.0, 5.0, 20.0, 0.0, 50.0, None),
    "negative_rate": (0.0, 5.0, 20.0, -1.0, 50.0, None),
    "crypto_quote": (0.0, 5.0, 20.0, 60000.0, 50.0, None),
    "very_large": (0.0, 1e12, 1e6, 1.0, 1e15, None),
    "very_large_delta": (0.0, 1e12, 1e6, 1.0, 1.0, None),
    "tiny_target": (0.0, 5.0, 20.0, 1.0, 1e-09, None),
    "tiny_everything": (1e-12, 1e-12, 1e-12, 1.0, 1e-12, None),
    "unknown_input": (0.0, 5.0, 20.0, 1.0, "fifty", None),
    "unknown_holdings": (0.0, "five", 20.0, 1.0, 50.0, None),
    "unknown_age": (0.0, 5.0, 20.0, 1.0, 50.0, "old"),
}

AMMO_RAISING_CASES = ("unknown_input", "unknown_holdings", "unknown_age")

EMPTY_CASES = (
    "empty",
    "empty_no_target",
    "empty_negative_target",
    "negative_holdings",
    "negative_stats",
)
PENDING_CASES = (
    "pending",
    "pending_tiny_holdings",
    "pending_huge_holdings",
    "negative_price",
    "zero_rate",
    "negative_rate",
)
STALE_CASES = ("stale", "stale_no_price", "stale_and_noop")

PAIRS_FULL = {
    ("RAVE", "BTC"): FakePair(3.5),
    ("RAVE", "ETH"): FakePair(-2.5),
    ("RAVE", "USD"): FakePair(1.0),
}
PAIRS_NO_USD = {("RAVE", "BTC"): FakePair(3.5)}
PAIRS_USDC = {("RAVE", "BTC"): FakePair(3.5), ("RAVE", "USDC"): FakePair(1.0)}
PAIRS_FLAT = {("RAVE", "BTC"): FakePair(1.05), ("RAVE", "USD"): FakePair(1.0)}
PAIRS_DOWN = {("RAVE", "BTC"): FakePair(-4.0), ("RAVE", "USD"): FakePair(1.0)}
PAIRS_UNICODE = {
    (UNICODE_ASSET, "BTC"): FakePair(3.5),
    (UNICODE_ASSET, "USD"): FakePair(1.0),
}
PAIRS_MARKUP = {
    (MARKUP_ASSET.upper(), "BTC"): FakePair(3.5),
    (MARKUP_ASSET.upper(), "USD"): FakePair(1.0),
}
PAIRS_LONG = {
    (LONG_ASSET, "BTC"): FakePair(3.5),
    (LONG_ASSET, "USD"): FakePair(1.0),
}

DENOM_CASES = {
    "btc_up": ({"pairs": PAIRS_FULL}, ("BTC", "RAVE", "coinbase", 500.0)),
    "eth_down": ({"pairs": PAIRS_FULL}, ("ETH", "RAVE", "coinbase", 500.0)),
    "flat": ({"pairs": PAIRS_FLAT}, ("BTC", "RAVE", "coinbase", 500.0)),
    "down": ({"pairs": PAIRS_DOWN}, ("BTC", "RAVE", "coinbase", 500.0)),
    "no_usd_pair": ({"pairs": PAIRS_NO_USD}, ("BTC", "RAVE", "coinbase", 500.0)),
    "usdc_fallback": ({"pairs": PAIRS_USDC}, ("BTC", "RAVE", "coinbase", 500.0)),
    "unlisted": ({"pairs": {}}, ("BTC", "RAVE", "coinbase", 500.0)),
    "no_btc_rate": ({"pairs": PAIRS_FULL, "btc_usd": 0.0}, ("BTC", "R", "cb", 500.0)),
    "no_eth_rate": ({"pairs": PAIRS_FULL, "eth_usd": 0.0}, ("ETH", "R", "cb", 500.0)),
    "negative_rate": (
        {"pairs": PAIRS_FULL, "btc_usd": -1.0},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "unknown_quote": ({"pairs": PAIRS_FULL}, ("USD", "RAVE", "coinbase", 500.0)),
    "self_reference": ({"pairs": PAIRS_FULL}, ("BTC", "BTC", "coinbase", 500.0)),
    "self_reference_case": ({"pairs": PAIRS_FULL}, ("BTC", "btc", "coinbase", 500.0)),
    "blank_quote": ({"pairs": PAIRS_FULL}, ("", "RAVE", "coinbase", 500.0)),
    "blank_base": ({"pairs": PAIRS_FULL}, ("BTC", "", "coinbase", 500.0)),
    "none_quote": ({"pairs": PAIRS_FULL}, (None, "RAVE", "coinbase", 500.0)),
    "none_base": ({"pairs": PAIRS_FULL}, ("BTC", None, "coinbase", 500.0)),
    "zero_target": ({"pairs": PAIRS_FULL}, ("BTC", "RAVE", "coinbase", 0.0)),
    "negative_target": ({"pairs": PAIRS_FULL}, ("BTC", "RAVE", "coinbase", -500.0)),
    "blank_exchange": ({"pairs": PAIRS_FULL}, ("BTC", "RAVE", "", 500.0)),
    "lower_case_names": ({"pairs": PAIRS_FULL}, ("btc", "rave", "coinbase", 500.0)),
    "whole_units": (
        {"pairs": PAIRS_FULL, "btc_usd": 100.0},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "small_units": (
        {"pairs": PAIRS_FULL, "btc_usd": 20000.0},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "tiny_units": (
        {"pairs": PAIRS_FULL, "btc_usd": 1e9},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "unit_boundary_one": (
        {"pairs": PAIRS_FULL, "btc_usd": 500.0},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "unit_boundary_hundredth": (
        {"pairs": PAIRS_FULL, "btc_usd": 50000.0},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "very_large_target": (
        {"pairs": PAIRS_FULL},
        ("BTC", "RAVE", "coinbase", 1e18),
    ),
    "unicode_base": (
        {"pairs": PAIRS_UNICODE},
        ("BTC", UNICODE_ASSET, "coinbase", 500.0),
    ),
    "markup_base": (
        {"pairs": PAIRS_MARKUP},
        ("BTC", MARKUP_ASSET, "coinbase", 500.0),
    ),
    "long_base": ({"pairs": PAIRS_LONG}, ("BTC", LONG_ASSET, "coinbase", 500.0)),
    "unicode_exchange": (
        {"pairs": PAIRS_FULL},
        ("BTC", "RAVE", UNICODE_ASSET, 500.0),
    ),
    "monitor_raises": (
        {"pairs": PAIRS_FULL, "monitor_error": RuntimeError("rates are down")},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "scout_raises": (
        {"pairs": PAIRS_FULL, "scout_error": RuntimeError("the scout broke")},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "scout_missing": (
        {"pairs": PAIRS_FULL, "scout_missing": True},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "unknown_input": ({"pairs": PAIRS_FULL}, ("BTC", "RAVE", "coinbase", "lots")),
}

DENOM_RAISING_CASES = ("unknown_input",)
DENOM_BLANK_CASES = (
    "self_reference",
    "self_reference_case",
    "blank_quote",
    "blank_base",
    "none_quote",
    "none_base",
    "zero_target",
    "negative_target",
    "monitor_raises",
    "scout_raises",
    "scout_missing",
)

PRICE_CASES = {
    "hit": (
        {"pool": FakePool({("coinbase", "RAVE/USD"): FakeTicker(0.5, CLOCK_NOW - 3)})},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "hit_old": (
        {
            "pool": FakePool(
                {("coinbase", "RAVE/USD"): FakeTicker(0.5, CLOCK_NOW - 900)}
            )
        },
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "future_fetch_time": (
        {"pool": FakePool({("coinbase", "RAVE/USD"): FakeTicker(0.5, CLOCK_NOW + 60)})},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "no_entry": ({"pool": FakePool({})}, ("coinbase", "RAVE/USD", 0.25)),
    "zero_last": (
        {"pool": FakePool({("coinbase", "RAVE/USD"): FakeTicker(0.0, CLOCK_NOW - 3)})},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "negative_last": (
        {"pool": FakePool({("coinbase", "RAVE/USD"): FakeTicker(-2.0, CLOCK_NOW - 3)})},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "no_fetch_time": (
        {"pool": FakePool({("coinbase", "RAVE/USD"): FakeTicker(0.5, 0.0)})},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "blank_last": (
        {"pool": FakePool({("coinbase", "RAVE/USD"): FakeTicker(None, CLOCK_NOW - 3)})},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "very_large_last": (
        {"pool": FakePool({("coinbase", "RAVE/USD"): FakeTicker(1e18, CLOCK_NOW - 3)})},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "unknown_last": (
        {"pool": FakePool({("coinbase", "RAVE/USD"): FakeTicker("lots", CLOCK_NOW)})},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "pool_raises": (
        {"pool": FakePool({}, error=RuntimeError("the cache is broken"))},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "no_pool": ({"pool": None}, ("coinbase", "RAVE/USD", 0.25)),
    "falsy_pool": ({"pool": FakePool({}, truthy=False)}, ("cb", "RAVE/USD", 0.25)),
    "pool_import_raises": (
        {"pool": None, "raises": RuntimeError("the pool never wired")},
        ("coinbase", "RAVE/USD", 0.25),
    ),
    "unicode_symbol": (
        {"pool": FakePool({})},
        ("coinbase", UNICODE_ASSET + "/USD", 0.25),
    ),
    "long_symbol": ({"pool": FakePool({})}, ("coinbase", LONG_SYMBOL, 0.25)),
    "markup_symbol": (
        {"pool": FakePool({})},
        ("coinbase", MARKUP_ASSET + "/USD", 0.25),
    ),
    "blank_names": ({"pool": FakePool({})}, ("", "", 0.0)),
    "zero_fallback": ({"pool": FakePool({})}, ("coinbase", "RAVE/USD", 0.0)),
    "negative_fallback": ({"pool": FakePool({})}, ("coinbase", "RAVE/USD", -1.0)),
    "unknown_fallback": ({"pool": FakePool({})}, ("coinbase", "RAVE/USD", "cheap")),
}

PRICE_HIT_CASES = ("hit", "hit_old", "future_fetch_time", "very_large_last")


# Drivers


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


def snapshot(body):
    """One case's whole state: its outputs and the ordered call list."""
    found = {"calls": [list(call) for call in CALLS]}
    found.update(body)
    return found


def _guarded(run):
    """Run one composition, keeping either its value or its failure."""
    try:
        return {"value": run(), "error": "", "message": ""}
    except Exception as exc:
        return {"value": None, "error": type(exc).__name__, "message": str(exc)}


def run_old_ammo(name, monkeypatch):
    """Drive the shipped Ammo cell over one case."""
    args = AMMO_CASES[name]
    watch_bands(monkeypatch, shipped)
    CALLS.clear()
    found = _guarded(lambda: shipped._compose_ammo_cell(*args))
    return snapshot({"cell": found})


def run_new_ammo(name, monkeypatch):
    """Drive the surface's Ammo cell over the same case."""
    args = AMMO_CASES[name]
    watch_bands(monkeypatch, surface)
    CALLS.clear()
    model = surface.TableCellsModel()
    found = _guarded(lambda: model.ammo_cell(*args))
    return snapshot({"cell": found})


def new_ammo_model(name, monkeypatch):
    """The surface model for one Ammo case, and how the drive ended."""
    args = AMMO_CASES[name]
    watch_bands(monkeypatch, surface)
    CALLS.clear()
    model = surface.TableCellsModel()
    return model, _guarded(lambda: model.ammo_cell(*args))


def run_old_denom(name, monkeypatch):
    """Drive the shipped Target-denom cell over one case."""
    spec, args = DENOM_CASES[name]
    install_market(monkeypatch, spec)
    CALLS.clear()
    found = _guarded(lambda: list(shipped._compose_table_target_denom_cell(*args)))
    return snapshot({"cell": found})


def run_new_denom(name, monkeypatch):
    """Drive the surface's Target-denom cell over the same case."""
    spec, args = DENOM_CASES[name]
    install_market(monkeypatch, spec)
    CALLS.clear()
    model = surface.TableCellsModel()
    found = _guarded(lambda: list(model.target_denom_cell(*args)))
    return snapshot({"cell": found})


def new_denom_model(name, monkeypatch):
    """The surface model for one Target-denom case, and how it ended."""
    spec, args = DENOM_CASES[name]
    install_market(monkeypatch, spec)
    CALLS.clear()
    model = surface.TableCellsModel()
    return model, _guarded(lambda: model.target_denom_cell(*args))


def run_old_price(name, monkeypatch):
    """Drive the shipped pool reader and price reader over one case."""
    spec, args = PRICE_CASES[name]
    install_pool(monkeypatch, spec)
    freeze_clock(monkeypatch)
    CALLS.clear()
    pool = shipped._ammo_price_pool()
    found = _guarded(lambda: list(shipped._fresh_display_price(pool, *args)))
    return snapshot({"price": found, "pool_found": pool is not None})


def run_new_price(name, monkeypatch):
    """Drive the surface's pool reader and price reader over the same case."""
    spec, args = PRICE_CASES[name]
    install_pool(monkeypatch, spec)
    freeze_clock(monkeypatch)
    CALLS.clear()
    model = surface.TableCellsModel()
    pool = model.price_pool()
    found = _guarded(lambda: list(model.fresh_price(pool, *args)))
    return snapshot({"price": found, "pool_found": pool is not None})


def new_price_model(name, monkeypatch):
    """The surface model for one price case, and how the drive ended."""
    spec, args = PRICE_CASES[name]
    install_pool(monkeypatch, spec)
    freeze_clock(monkeypatch)
    CALLS.clear()
    model = surface.TableCellsModel()
    return model, _guarded(lambda: model.fresh_price(model.price_pool(), *args))


# Side by side, value for value and by hash


@pytest.mark.parametrize("name", sorted(AMMO_CASES))
def test_the_ammo_cell_is_the_shipped_cell(name, monkeypatch):
    """The surface composed a different Ammo cell than the shipped one."""
    old = run_old_ammo(name, monkeypatch)
    new = run_new_ammo(name, monkeypatch)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(AMMO_CASES))
def test_the_ammo_trace_holds_the_whole_cell(name, monkeypatch):
    """The comparison passed by measuring nothing."""
    old = run_old_ammo(name, monkeypatch)
    cell = old["cell"]
    assert (cell["error"] != "") is (name in AMMO_RAISING_CASES), name
    if name in AMMO_RAISING_CASES:
        assert cell["value"] is None, name
        assert cell["message"] != "", name
        return
    found = cell["value"]
    assert isinstance(found["text"], str) and found["text"] != "", name
    assert found["color"] in (SUCCESS_HEX, ERROR_HEX, TEXT_MED_HEX), name
    assert isinstance(found["tip"], str) and found["tip"] != "", name
    assert isinstance(found["position_val"], float), name
    if name in EMPTY_CASES or name in PENDING_CASES:
        assert list(found) == list(surface.AMMO_EARLY_FIELDS), name
    else:
        assert list(found) == list(surface.AMMO_FIELDS), name
        assert old["calls"] != [], name


@pytest.mark.parametrize("name", sorted(DENOM_CASES))
def test_the_denom_cell_is_the_shipped_cell(name, monkeypatch):
    """The surface composed a different Target-denom cell than shipped."""
    old = run_old_denom(name, monkeypatch)
    new = run_new_denom(name, monkeypatch)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(DENOM_CASES))
def test_the_denom_trace_holds_the_whole_cell(name, monkeypatch):
    """The comparison passed by measuring nothing."""
    old = run_old_denom(name, monkeypatch)
    cell = old["cell"]
    assert (cell["error"] != "") is (name in DENOM_RAISING_CASES), name
    if name in DENOM_RAISING_CASES:
        assert cell["value"] is None, name
        return
    text, color = cell["value"]
    assert isinstance(text, str), name
    assert color in (SUCCESS_HEX, ERROR_HEX, TEXT_MED_HEX), name
    assert (text == "") is (name in DENOM_BLANK_CASES), name


@pytest.mark.parametrize("name", sorted(PRICE_CASES))
def test_the_display_price_is_the_shipped_readers(name, monkeypatch):
    """The surface read a different display price than the shipped reader."""
    old = run_old_price(name, monkeypatch)
    new = run_new_price(name, monkeypatch)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(PRICE_CASES))
def test_the_price_trace_holds_the_whole_reading(name, monkeypatch):
    """The comparison passed by measuring nothing."""
    old = run_old_price(name, monkeypatch)
    assert old["price"]["error"] == "", name
    price, age = old["price"]["value"]
    assert (age is not None) is (name in PRICE_HIT_CASES), name
    if name in PRICE_HIT_CASES:
        assert price == 0.5 or price == 1e18, name
        assert age >= 0.0, name
    else:
        assert age is None, name


def test_the_sample_hashes_are_reported(monkeypatch):
    """Two sides agreed by both returning nothing at all."""
    samples = {}
    for name in ("scrum", "empty", "pending", "stale", "aged_price"):
        old = run_old_ammo(name, monkeypatch)
        new = run_new_ammo(name, monkeypatch)
        samples[name] = (digest(old), digest(new))
        assert samples[name][0] == samples[name][1], name
    assert len({pair[0] for pair in samples.values()}) == 5
    changed = run_old_ammo("scrum", monkeypatch)
    changed["cell"]["value"]["text"] = "$1.0000"
    assert digest(changed) != samples["scrum"][0]


# The paths every case reaches


def test_every_ammo_case_reaches_the_path_it_names(monkeypatch):
    """A case was renamed and stopped reaching the path it stands for."""
    reached = {}
    ended = {}
    for name in AMMO_CASES:
        model, outcome = new_ammo_model(name, monkeypatch)
        reached[name] = model.ammo_path
        ended[name] = outcome["error"]
    assert {name for name, error in ended.items() if error} == set(AMMO_RAISING_CASES)
    for name in EMPTY_CASES:
        assert reached[name] == surface.AMMO_PATH_EMPTY, name
    for name in PENDING_CASES:
        assert reached[name] == surface.AMMO_PATH_PENDING, name
    for name in STALE_CASES:
        assert reached[name] == surface.AMMO_PATH_SIGNAL, name
    for name in AMMO_RAISING_CASES:
        assert reached[name] == "", name
    assert set(reached.values()) == {""} | set(surface.AMMO_PATHS)
    assert reached["scrum"] == surface.AMMO_PATH_SIGNAL
    assert reached["negative_holdings"] == surface.AMMO_PATH_EMPTY
    assert reached["negative_price"] == surface.AMMO_PATH_PENDING
    assert reached["zero_rate"] == surface.AMMO_PATH_PENDING
    assert reached["negative_rate"] == surface.AMMO_PATH_PENDING
    assert reached["tiny_everything"] == surface.AMMO_PATH_SIGNAL


def test_every_ammo_case_carries_the_signal_it_names(monkeypatch):
    """A colour or a tooltip stopped matching the case that drives it."""
    cells = {}
    for name in AMMO_CASES:
        if name in AMMO_RAISING_CASES:
            continue
        cells[name] = run_old_ammo(name, monkeypatch)["cell"]["value"]
    assert cells["scrum"]["color"] == SUCCESS_HEX
    assert cells["scrum"]["tip"] == surface.SCRUM_TIP
    assert cells["fold"]["color"] == ERROR_HEX
    assert cells["fold"]["tip"] == surface.FOLD_TIP
    assert cells["at_target"]["color"] == TEXT_MED_HEX
    assert cells["at_target"]["tip"] == surface.AT_TARGET_TIP
    assert cells["at_target_edge"]["color"] == TEXT_MED_HEX
    assert cells["empty"]["color"] == ERROR_HEX
    assert cells["empty"]["tip"] == surface.EMPTY_POSITION_TIP
    assert cells["empty"]["text"] == "$50.0000"
    assert cells["empty_no_target"]["text"] == NO_TARGET_DASHES
    assert cells["empty_negative_target"]["text"] == NO_TARGET_DASHES
    assert cells["pending"]["text"] == PENDING_PRICE_WORD
    assert cells["pending"]["color"] == TEXT_MED_HEX
    assert "5.000000" in cells["pending"]["tip"]
    assert cells["stale"]["stale"] is True
    assert cells["stale"]["color"] == TEXT_MED_HEX
    assert cells["stale"]["text"].endswith(STALE_MARKER_TEXT)
    assert cells["stale"]["tip"].startswith("STALE — ")
    assert cells["stale_and_noop"]["manual_fire_noop"] is True
    assert "MANUAL FIRE WILL NOT ACT" not in cells["stale_and_noop"]["tip"]
    assert cells["manual_fire_noop"]["manual_fire_noop"] is True
    assert "MANUAL FIRE WILL NOT ACT" in cells["manual_fire_noop"]["tip"]
    assert cells["manual_fire_noop"]["color"] == SUCCESS_HEX
    assert cells["manual_fire_noop_fold"]["color"] == ERROR_HEX
    assert "MANUAL FIRE WILL NOT ACT" in cells["manual_fire_noop_fold"]["tip"]
    assert cells["aged_price"]["text"].endswith(STALE_MARKER_TEXT)
    assert cells["aged_price"]["tip"].startswith("PRICE 25s OLD")
    assert cells["aged_price_edge"]["text"] == "$50.0000"
    assert not cells["aged_price_edge"]["text"].endswith(STALE_MARKER_TEXT)
    assert cells["aged_price_just_over"]["text"].endswith(STALE_MARKER_TEXT)
    assert cells["fresh_price_age"]["price_age_s"] == 2.0
    assert not cells["fresh_price_age"]["text"].endswith(STALE_MARKER_TEXT)
    assert not cells["negative_price_age"]["text"].endswith(STALE_MARKER_TEXT)
    assert cells["no_target"]["text"] == NO_TARGET_DASHES
    assert cells["negative_target"]["text"] == NO_TARGET_DASHES
    assert cells["very_large"]["text"] == "$999,000,000,000,000,000.0000"
    assert cells["crypto_quote"]["position_val"] == 5.0 * 20.0 * 60000.0
    assert len(cells) == len(AMMO_CASES) - len(AMMO_RAISING_CASES)


def test_every_denom_case_reaches_the_path_it_names(monkeypatch):
    """A case was renamed and stopped reaching the path it stands for."""
    reached = {}
    ended = {}
    for name in DENOM_CASES:
        model, outcome = new_denom_model(name, monkeypatch)
        reached[name] = model.denom_path
        ended[name] = outcome["error"]
    assert {name for name, error in ended.items() if error} == set(DENOM_RAISING_CASES)
    assert reached["btc_up"] == surface.DENOM_PATH_PRICED
    assert reached["eth_down"] == surface.DENOM_PATH_PRICED
    assert reached["self_reference"] == surface.DENOM_PATH_SELF
    assert reached["self_reference_case"] == surface.DENOM_PATH_SELF
    assert reached["blank_quote"] == surface.DENOM_PATH_NO_NAMES
    assert reached["blank_base"] == surface.DENOM_PATH_NO_NAMES
    assert reached["none_quote"] == surface.DENOM_PATH_NO_NAMES
    assert reached["none_base"] == surface.DENOM_PATH_NO_NAMES
    assert reached["zero_target"] == surface.DENOM_PATH_NO_TARGET
    assert reached["negative_target"] == surface.DENOM_PATH_NO_TARGET
    assert reached["no_btc_rate"] == surface.DENOM_PATH_NO_RATE
    assert reached["no_eth_rate"] == surface.DENOM_PATH_NO_RATE
    assert reached["negative_rate"] == surface.DENOM_PATH_NO_RATE
    assert reached["unknown_quote"] == surface.DENOM_PATH_NO_RATE
    assert reached["unlisted"] == surface.DENOM_PATH_UNLISTED
    assert reached["monitor_raises"] == surface.DENOM_PATH_ERRORED
    assert reached["scout_raises"] == surface.DENOM_PATH_ERRORED
    assert reached["scout_missing"] == surface.DENOM_PATH_ERRORED
    assert reached["unknown_input"] == ""
    assert set(reached.values()) == {""} | set(surface.DENOM_PATHS)


def test_every_denom_case_carries_the_text_it_names(monkeypatch):
    """A cell text or colour stopped matching the case that drives it."""
    cells = {}
    for name in DENOM_CASES:
        if name in DENOM_RAISING_CASES:
            continue
        cells[name] = run_old_denom(name, monkeypatch)["cell"]["value"]
    assert cells["btc_up"] == ["0.008333 (+2.5%)", SUCCESS_HEX]
    assert cells["eth_down"] == ["0.16667 (-3.5%)", ERROR_HEX]
    assert cells["flat"] == ["0.008333 (0.1%)", TEXT_MED_HEX]
    assert cells["down"] == ["0.008333 (-5.0%)", ERROR_HEX]
    assert cells["no_usd_pair"] == ["0.008333 (+3.5%)", SUCCESS_HEX]
    assert cells["usdc_fallback"] == ["0.008333 (+2.5%)", SUCCESS_HEX]
    assert cells["unlisted"] == [UNLISTED_DASH, TEXT_MED_HEX]
    assert cells["no_btc_rate"] == [PENDING_RATE_WORD, TEXT_MED_HEX]
    assert cells["no_eth_rate"] == [PENDING_RATE_WORD, TEXT_MED_HEX]
    assert cells["negative_rate"] == [PENDING_RATE_WORD, TEXT_MED_HEX]
    assert cells["unknown_quote"] == [PENDING_RATE_WORD, TEXT_MED_HEX]
    assert cells["whole_units"] == ["5.0000 (+2.5%)", SUCCESS_HEX]
    assert cells["small_units"] == ["0.02500 (+2.5%)", SUCCESS_HEX]
    assert cells["tiny_units"] == ["0.000000 (+2.5%)", SUCCESS_HEX]
    assert cells["unit_boundary_one"] == ["1.0000 (+2.5%)", SUCCESS_HEX]
    assert cells["unit_boundary_hundredth"] == ["0.01000 (+2.5%)", SUCCESS_HEX]
    assert cells["lower_case_names"] == cells["btc_up"]
    assert cells["blank_exchange"] == cells["btc_up"]
    assert cells["unicode_base"][1] == SUCCESS_HEX
    assert cells["markup_base"][1] == SUCCESS_HEX
    assert cells["long_base"][1] == SUCCESS_HEX
    assert cells["very_large_target"][0].startswith("16666666666666.6660")
    for name in DENOM_BLANK_CASES:
        assert cells[name] == ["", TEXT_MED_HEX], name
    assert len(cells) == len(DENOM_CASES) - len(DENOM_RAISING_CASES)


# The pieces both sides share


def test_the_magnitude_format_is_the_shipped_cells_own(monkeypatch):
    """The dollar figure stopped being written the way the cell writes it."""
    assert surface.magnitude(50.0) == "$50.0000"
    assert surface.magnitude(-50.0) == "$50.0000"
    assert surface.magnitude(0.0) == "$0.0000"
    assert surface.magnitude(1234567.891) == "$1,234,567.8910"
    assert surface.magnitude(1e-09) == "$0.0000"
    assert surface.MAGNITUDE_FORMAT == "${magnitude:,.4f}"
    assert surface.MAGNITUDE_FORMAT.count("{") == 1
    assert "{magnitude" in surface.MAGNITUDE_FORMAT
    assert surface.NO_TARGET_TEXT == NO_TARGET_DASHES
    assert surface.ammo_text(-50.0, 50.0) == "$50.0000"
    assert surface.ammo_text(-50.0, 0.0) == NO_TARGET_DASHES
    assert surface.ammo_text(-50.0, -1.0) == NO_TARGET_DASHES
    for name, delta in (("scrum", 50.0), ("fold", -25.0), ("empty", -50.0)):
        cell = run_old_ammo(name, monkeypatch)["cell"]["value"]
        assert cell["delta"] == pytest.approx(delta), name
        assert cell["text"].split(" ")[0] == surface.magnitude(cell["delta"]), name


def test_the_units_widths_are_the_shipped_cells_own():
    """The units figure changed width at a different size."""
    assert surface.units_text(5.0) == "5.0000"
    assert surface.units_text(1.0) == "1.0000"
    assert surface.units_text(0.999999) == "0.991000"[:0] + "1.00000"
    assert surface.units_text(0.025) == "0.02500"
    assert surface.units_text(0.01) == "0.01000"
    assert surface.units_text(0.009) == "0.009000"
    assert surface.units_text(0.0) == "0.000000"
    assert surface.units_text(1e18) == "1000000000000000000.0000"
    assert surface.UNITS_WHOLE_MIN == 1
    assert surface.UNITS_SMALL_MIN == 0.01
    assert surface.UNITS_WHOLE_FORMAT == "{units:.4f}"
    assert surface.UNITS_SMALL_FORMAT == "{units:.5f}"
    assert surface.UNITS_TINY_FORMAT == "{units:.6f}"
    for template in (
        surface.UNITS_WHOLE_FORMAT,
        surface.UNITS_SMALL_FORMAT,
        surface.UNITS_TINY_FORMAT,
    ):
        assert template.count("{") == 1
        assert "{units" in template
    assert surface.DENOM_TEXT_FORMAT == "{units_text} ({sign}{delta:.1f}%)"
    assert surface.DENOM_TEXT_FORMAT.count("{") == 3
    assert (
        surface.DENOM_TEXT_FORMAT.format(units_text="1.0000", sign="+", delta=2.5)
        == "1.0000 (+2.5%)"
    )


def test_the_divergence_colours_are_the_shipped_cells_own():
    """A divergence changed colour or sign at a different size."""
    assert surface.divergence_colour(2.5) == (SUCCESS_HEX, "+")
    assert surface.divergence_colour(-2.5) == (ERROR_HEX, "")
    assert surface.divergence_colour(0.0) == (TEXT_MED_HEX, "")
    assert surface.divergence_colour(0.09) == (TEXT_MED_HEX, "")
    assert surface.divergence_colour(-0.09) == (TEXT_MED_HEX, "")
    assert surface.divergence_colour(0.1) == (SUCCESS_HEX, "+")
    assert surface.divergence_colour(-0.1) == (ERROR_HEX, "")
    assert surface.DIVERGENCE_DUST_PCT == 0.1
    assert surface.SIGN_UP == "+"
    assert surface.SIGN_FLAT == ""
    assert surface.SIGN_DOWN == ""
    assert surface.DENOM_UP_COLOR == SUCCESS_HEX
    assert surface.DENOM_DOWN_COLOR == ERROR_HEX
    assert surface.DENOM_NEUTRAL_COLOR == TEXT_MED_HEX


def test_the_colours_are_three_and_distinct():
    """Two of the three cell colours became one, so a swap reads the same."""
    from src.gui import design_system as ds

    assert surface.AMMO_SCRUM_COLOR == ds.SUCCESS == SUCCESS_HEX
    assert surface.AMMO_FOLD_COLOR == ds.ERROR == ERROR_HEX
    assert surface.AMMO_NEUTRAL_COLOR == ds.TEXT_MED == TEXT_MED_HEX
    three = {SUCCESS_HEX, ERROR_HEX, TEXT_MED_HEX}
    assert len(three) == 3
    for value in three:
        assert len(value) == 7 and value.startswith("#")
        red, green, blue = value[1:3], value[3:5], value[5:7]
        assert not (red == green == blue), value
        assert red != blue, value
    assert set(surface.TERRITORY_COLORS.values()) == three
    assert len(surface.TERRITORY_COLORS) == 3
    assert len(set(surface.TERRITORY_TIPS.values())) == 3
    assert set(surface.TERRITORY_COLORS) == set(surface.TERRITORIES)
    assert set(surface.TERRITORY_TIPS) == set(surface.TERRITORIES)


def test_the_bands_are_the_engines_own(monkeypatch):
    """The cell computed a threshold instead of asking the engine."""
    from src.trading import target_bands

    assert surface.MANUAL_FIRE_DUST_PCT == target_bands.MANUAL_FIRE_PCT == 0.01
    assert surface.TERRITORIES == ("scrum", "fold", "at_target")
    for position, target, expected in (
        (60.0, 50.0, "scrum"),
        (40.0, 50.0, "fold"),
        (50.0, 50.0, "at_target"),
    ):
        assert target_bands.target_territory(position, target) == expected
    old = run_old_ammo("manual_fire_noop", monkeypatch)
    new = run_new_ammo("manual_fire_noop", monkeypatch)
    asked = [call for call in old["calls"] if call[0] in (TERRITORY_ASK, DUST_ASK)]
    assert [call[0] for call in asked] == [TERRITORY_ASK, DUST_ASK]
    assert [call for call in new["calls"] if call[0] in (TERRITORY_ASK, DUST_ASK)] == (
        asked
    )
    assert asked[1][2] == target_bands.manual_fire_dust_band(50.0) == 0.5
    quiet = run_old_ammo("empty", monkeypatch)
    assert [call for call in quiet["calls"] if call[0] == TERRITORY_ASK] == []


def test_the_ammo_field_lists_are_the_shipped_cells_own(monkeypatch):
    """A key appeared on one Ammo cell and not the other."""
    signal = run_old_ammo("scrum", monkeypatch)["cell"]["value"]
    empty = run_old_ammo("empty", monkeypatch)["cell"]["value"]
    pending = run_old_ammo("pending", monkeypatch)["cell"]["value"]
    assert tuple(signal) == surface.AMMO_FIELDS
    assert tuple(empty) == surface.AMMO_EARLY_FIELDS
    assert tuple(pending) == surface.AMMO_EARLY_FIELDS
    assert len(surface.AMMO_FIELDS) == 8
    assert len(surface.AMMO_EARLY_FIELDS) == 6
    assert set(surface.AMMO_EARLY_FIELDS) < set(surface.AMMO_FIELDS)
    assert set(surface.AMMO_FIELDS) - set(surface.AMMO_EARLY_FIELDS) == {
        "manual_fire_noop",
        "price_age_s",
    }
    assert surface.AMMO_PATH_FIELDS == {
        surface.AMMO_PATH_EMPTY: surface.AMMO_EARLY_FIELDS,
        surface.AMMO_PATH_PENDING: surface.AMMO_EARLY_FIELDS,
        surface.AMMO_PATH_SIGNAL: surface.AMMO_FIELDS,
    }
    assert set(surface.AMMO_PATH_FIELDS) == set(surface.AMMO_PATHS)
    assert len(surface.AMMO_PATHS) == 3
    assert len(surface.DENOM_PATHS) == 7
    assert len(set(surface.DENOM_PATHS)) == 7
    assert set(surface.DENOM_PATH_TEXTS) == set(surface.DENOM_PATHS) - {
        surface.DENOM_PATH_PRICED
    }


def test_the_format_strings_carry_their_own_placeholders():
    """A placeholder was dropped, so a value never reaches the operator."""
    named = {
        surface.MAGNITUDE_FORMAT: ("magnitude",),
        surface.STALE_TEXT_FORMAT: ("text", "marker"),
        surface.PENDING_PRICE_TIP_FORMAT: ("holdings",),
        surface.MANUAL_FIRE_NOOP_TIP_FORMAT: ("tip", "magnitude", "dust_band"),
        surface.STALE_TIP_FORMAT: ("stats_pv",),
        surface.AGED_PRICE_TIP_FORMAT: ("price_age_s",),
        surface.UNITS_WHOLE_FORMAT: ("units",),
        surface.UNITS_SMALL_FORMAT: ("units",),
        surface.UNITS_TINY_FORMAT: ("units",),
        surface.DENOM_TEXT_FORMAT: ("units_text", "sign", "delta"),
    }
    for template, fields in named.items():
        for field in fields:
            assert "{" + field in template, (template, field)
        assert template.count("{") == len(fields), template
    assert len(named) == 10
    assert "{holdings:.6f}" in surface.PENDING_PRICE_TIP_FORMAT
    assert "{magnitude:,.4f}" in surface.MANUAL_FIRE_NOOP_TIP_FORMAT
    assert "{dust_band:,.2f}" in surface.MANUAL_FIRE_NOOP_TIP_FORMAT
    assert "{stats_pv:,.4f}" in surface.STALE_TIP_FORMAT
    assert "{price_age_s:,.0f}" in surface.AGED_PRICE_TIP_FORMAT
    assert "{delta:.1f}" in surface.DENOM_TEXT_FORMAT
    assert surface.PENDING_PRICE_TIP_FORMAT.format(holdings=5.0).startswith(
        "Holdings present (5.000000)"
    )
    assert surface.STALE_TIP_FORMAT.format(stats_pv=1234.5).startswith(
        "STALE — price unavailable"
    )
    assert "($1,234.5000)" in surface.STALE_TIP_FORMAT.format(stats_pv=1234.5)
    assert surface.AGED_PRICE_TIP_FORMAT.format(price_age_s=25.6).startswith(
        "PRICE 26s OLD"
    )
    assert surface.STALE_TEXT_FORMAT.format(text="$1.0000", marker="(stale)") == (
        "$1.0000 (stale)"
    )


def test_the_tips_are_the_shipped_cells_own(monkeypatch):
    """A tooltip the operator reads drifted from the shipped cell's."""
    for name, tip in (
        ("scrum", surface.SCRUM_TIP),
        ("fold", surface.FOLD_TIP),
        ("at_target", surface.AT_TARGET_TIP),
        ("empty", surface.EMPTY_POSITION_TIP),
    ):
        assert run_old_ammo(name, monkeypatch)["cell"]["value"]["tip"] == tip, name
    noop = run_old_ammo("manual_fire_noop", monkeypatch)["cell"]["value"]
    assert noop["tip"] == surface.MANUAL_FIRE_NOOP_TIP_FORMAT.format(
        tip=surface.SCRUM_TIP, magnitude=abs(noop["delta"]), dust_band=0.5
    )
    stale = run_old_ammo("stale", monkeypatch)["cell"]["value"]
    assert stale["tip"] == surface.STALE_TIP_FORMAT.format(stats_pv=100.0)
    aged = run_old_ammo("aged_price", monkeypatch)["cell"]["value"]
    assert aged["tip"] == surface.AGED_PRICE_TIP_FORMAT.format(price_age_s=25.0)
    pending = run_old_ammo("pending", monkeypatch)["cell"]["value"]
    assert pending["tip"] == surface.PENDING_PRICE_TIP_FORMAT.format(holdings=5.0)


def test_the_stale_marker_is_one_string(monkeypatch):
    """The marker on a stale figure drifted between the two branches."""
    assert surface.STALE_MARKER == STALE_MARKER_TEXT
    assert surface.PRICE_STALE_AFTER_S == 20.0
    from_cache = run_old_ammo("stale", monkeypatch)["cell"]["value"]
    from_age = run_old_ammo("aged_price", monkeypatch)["cell"]["value"]
    assert from_cache["text"].endswith(" " + STALE_MARKER_TEXT)
    assert from_age["text"].endswith(" " + STALE_MARKER_TEXT)
    assert from_cache["color"] == from_age["color"] == TEXT_MED_HEX
    assert from_cache["tip"] != from_age["tip"]
    fresh = run_old_ammo("scrum", monkeypatch)["cell"]["value"]
    assert STALE_MARKER_TEXT not in fresh["text"]
    assert fresh["color"] == SUCCESS_HEX


def test_the_stale_branch_overwrites_the_manual_fire_note(monkeypatch):
    """The Manual Fire note survived onto a stale cell.

    The shipped cell asks for the note only when the figure is fresh,
    then rewrites the whole tooltip on the stale path a few lines later.
    Measured: removing that freshness test changes no output, on either
    side, because the rewrite lands after it either way. The flag the
    cell reports is what still carries the fact, and it is compared.
    """
    old = run_old_ammo("stale_and_noop", monkeypatch)["cell"]["value"]
    new = run_new_ammo("stale_and_noop", monkeypatch)["cell"]["value"]
    assert old["stale"] is True
    assert old["manual_fire_noop"] is True
    assert new["manual_fire_noop"] is old["manual_fire_noop"]
    assert old["tip"] == surface.STALE_TIP_FORMAT.format(stats_pv=50.4)
    assert new["tip"] == old["tip"]
    assert "MANUAL FIRE WILL NOT ACT" not in old["tip"]
    noted = surface.MANUAL_FIRE_NOOP_TIP_FORMAT.format(
        tip=surface.SCRUM_TIP, magnitude=abs(old["delta"]), dust_band=0.5
    )
    assert "MANUAL FIRE WILL NOT ACT" in noted
    assert noted != old["tip"]
    fresh = run_old_ammo("manual_fire_noop", monkeypatch)["cell"]["value"]
    assert fresh["stale"] is False
    assert fresh["manual_fire_noop"] is True
    assert "MANUAL FIRE WILL NOT ACT" in fresh["tip"]
    aged = run_old_ammo("aged_price", monkeypatch)["cell"]["value"]
    assert aged["stale"] is False
    assert aged["manual_fire_noop"] is False
    assert aged["tip"] == surface.AGED_PRICE_TIP_FORMAT.format(price_age_s=25.0)


# The debug logs


def test_the_debug_logs_are_the_shipped_modules_own(monkeypatch, capture_log):
    """The line the console carries drifted from the shipped module's."""
    for name in ("pool_raises", "unknown_last"):
        with capture_log(LOGGER_NAME) as old_records:
            run_old_price(name, monkeypatch)
        old_logs = [record.getMessage() for record in old_records]
        with capture_log(LOGGER_NAME) as new_records:
            run_new_price(name, monkeypatch)
        assert [record.getMessage() for record in new_records] == old_logs, name
        assert len(old_logs) == 1, name
        assert [record.levelname for record in old_records] == ["DEBUG"], name
        assert old_logs[0] == "Ammo: pool price lookup failed for coinbase/RAVE/USD"
        assert old_records[0].exc_info is not None, name
    with capture_log(LOGGER_NAME) as pool_records:
        run_old_price("pool_import_raises", monkeypatch)
    assert [record.getMessage() for record in pool_records] == [
        "Ammo: data pool unavailable"
    ]
    with capture_log(LOGGER_NAME) as new_pool:
        run_new_price("pool_import_raises", monkeypatch)
    assert [record.getMessage() for record in new_pool] == [
        record.getMessage() for record in pool_records
    ]
    with capture_log(LOGGER_NAME) as quiet:
        run_old_price("hit", monkeypatch)
    assert [record.getMessage() for record in quiet] == []
    with capture_log(LOGGER_NAME) as also_quiet:
        run_new_price("hit", monkeypatch)
    assert [record.getMessage() for record in also_quiet] == []
    assert surface.LOGGER_NAME == LOGGER_NAME
    assert surface.logger.name == shipped.logger.name == LOGGER_NAME
    assert surface.POOL_UNAVAILABLE_LOG == "Ammo: data pool unavailable"
    assert surface.POOL_LOOKUP_FAILED_LOG.count("%s") == 2


def test_the_denom_cell_writes_no_log(monkeypatch, capture_log):
    """The best-effort cell started writing a line the shipped one does not."""
    with capture_log(LOGGER_NAME) as old_records:
        run_old_denom("scout_raises", monkeypatch)
    with capture_log(LOGGER_NAME) as new_records:
        run_new_denom("scout_raises", monkeypatch)
    assert [record.getMessage() for record in old_records] == []
    assert [record.getMessage() for record in new_records] == []
    with capture_log(LOGGER_NAME) as heard:
        run_old_price("pool_raises", monkeypatch)
    assert len(heard) == 1


# The table the two cells are painted into


def app():
    """The process application object every render needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def real_table():
    """One real BotStatusTable, built with no rows."""
    from src.gui.widgets.bot_status_table import BotStatusTable

    app()
    return BotStatusTable()


def build_row(cells):
    """One table row painted from three cell values, as the table paints it.

    `cells` carries the Ammo text, colour and tooltip, and the two
    Target-denom texts and colours. Every other column is filler, so the
    row has the shape the operator sees. Values the caller changed after
    they came off a side are refused.
    """
    unaltered(cells)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    app()
    table = QTableWidget(1, CALLER_COLUMN_COUNT)
    table.verticalHeader().setVisible(False)
    for column in range(CALLER_COLUMN_COUNT):
        item = QTableWidgetItem(FILLER_TEXT)
        item.setTextAlignment(Qt.AlignCenter)
        table.setItem(0, column, item)
    for column, text, color, tip in (
        (
            CALLER_TARGET_BTC_COLUMN,
            cells["target_btc_text"],
            cells["target_btc_color"],
            None,
        ),
        (
            CALLER_TARGET_ETH_COLUMN,
            cells["target_eth_text"],
            cells["target_eth_color"],
            None,
        ),
        (
            CALLER_AMMO_COLUMN,
            cells["ammo_text"],
            cells["ammo_color"],
            cells["ammo_tip"],
        ),
    ):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QColor(color))
        if tip is not None:
            item.setToolTip(tip)
        table.setItem(0, column, item)
    return table


ROW_CASES = {
    "scrum": ("scrum", "btc_up"),
    "fold": ("fold", "eth_down"),
    "at_target": ("at_target", "flat"),
    "empty": ("empty", "unlisted"),
    "pending": ("pending", "no_btc_rate"),
    "stale": ("stale", "self_reference"),
    "aged": ("aged_price", "down"),
    "noop": ("manual_fire_noop", "whole_units"),
    "no_target": ("no_target", "zero_target"),
    "unicode": ("scrum", "unicode_base"),
    "markup": ("scrum", "markup_base"),
    "long": ("scrum", "long_base"),
    "large": ("very_large", "very_large_target"),
}


def row_denom_args(denom_name, quote):
    """One Target-denom call for a row: the case's row, this quote."""
    _, args = DENOM_CASES[denom_name]
    return (quote,) + tuple(args[1:])


def old_row_values(name, monkeypatch):
    """The three cell values the shipped module composes for one row, stamped."""
    ammo_name, denom_name = ROW_CASES[name]
    watch_bands(monkeypatch, shipped)
    CALLS.clear()
    ammo = shipped._compose_ammo_cell(*AMMO_CASES[ammo_name])
    install_market(monkeypatch, DENOM_CASES[denom_name][0])
    btc_text, btc_color = shipped._compose_table_target_denom_cell(
        *row_denom_args(denom_name, "BTC")
    )
    eth_text, eth_color = shipped._compose_table_target_denom_cell(
        *row_denom_args(denom_name, "ETH")
    )
    return sealed(
        {
            "ammo_text": ammo["text"],
            "ammo_color": ammo["color"],
            "ammo_tip": ammo["tip"],
            "target_btc_text": btc_text,
            "target_btc_color": btc_color,
            "target_eth_text": eth_text,
            "target_eth_color": eth_color,
        }
    )


def new_row_values(name, monkeypatch):
    """The three cell values the surface payload carries for one row, stamped."""
    ammo_name, denom_name = ROW_CASES[name]
    watch_bands(monkeypatch, surface)
    CALLS.clear()
    model = surface.TableCellsModel()
    ammo = surface.build_view_model(
        model, ammo=dict(zip(AMMO_ARG_NAMES, AMMO_CASES[ammo_name]))
    )["ammo"]
    install_market(monkeypatch, DENOM_CASES[denom_name][0])
    btc = surface.build_view_model(
        surface.TableCellsModel(),
        denom=dict(zip(DENOM_ARG_NAMES, row_denom_args(denom_name, "BTC"))),
    )["denom"]
    eth = surface.build_view_model(
        surface.TableCellsModel(),
        denom=dict(zip(DENOM_ARG_NAMES, row_denom_args(denom_name, "ETH"))),
    )["denom"]
    return sealed(
        {
            "ammo_text": ammo["text"],
            "ammo_color": ammo["color"],
            "ammo_tip": ammo["tip"],
            "target_btc_text": btc["text"],
            "target_btc_color": btc["color"],
            "target_eth_text": eth["text"],
            "target_eth_color": eth["color"],
        }
    )


AMMO_ARG_NAMES = (
    "stats_pv",
    "holdings",
    "cur_price",
    "qrate",
    "target_val",
    "price_age_s",
)
DENOM_ARG_NAMES = ("quote_currency", "base_asset", "exchange_id", "target_usd")


@pytest.mark.parametrize("name", sorted(ROW_CASES))
def test_the_two_sides_render_the_same_pixels(name, monkeypatch):
    """The surface paints a cell the shipped module does not."""
    app()
    assert_pictures_match(
        old_side=render_offscreen(
            build_row(old_row_values(name, monkeypatch)), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            build_row(new_row_values(name, monkeypatch)), PIXEL_SIZE
        ),
        note=name,
    )


@pytest.mark.parametrize("name", sorted(ROW_CASES))
def test_the_two_sides_carry_the_same_cell_values(name, monkeypatch):
    """A cell value drifted between the shipped module and the surface."""
    old = old_row_values(name, monkeypatch)
    new = new_row_values(name, monkeypatch)
    assert new == old, name
    assert digest(new) == digest(old), name
    assert old["ammo_color"] in (SUCCESS_HEX, ERROR_HEX, TEXT_MED_HEX), name
    assert old["ammo_tip"] != "", name


def test_the_picture_reports_a_different_row_case(monkeypatch):
    """The image comparison passes whatever the second side paints.

    Two real row cases, one composed by each side. One carries an Ammo
    figure and two Target-denom figures; the other carries a blank BTC
    cell, so a pass proves the comparison reports a row painted
    differently.
    """
    app()
    scrum = old_row_values("scrum", monkeypatch)
    stale = new_row_values("stale", monkeypatch)
    assert scrum != stale
    assert_pictures_differ(
        old_side=render_offscreen(build_row(scrum), PIXEL_SIZE),
        new_side=render_offscreen(build_row(stale), PIXEL_SIZE),
        note="scrum from the shipped module against stale from the surface",
    )


def disguise(text):
    """The same text, one letter for another, at the same length."""
    return "".join("Z" if letter.isalpha() else letter for letter in text)


def test_a_same_length_text_change_is_compared_as_an_exact_string(monkeypatch):
    """A same-length text swap was left to the render to report.

    Whether a swap of equal length and equal word shape moves a pixel
    depends on the fonts the host installs, so no render carries this
    proof on every machine. The Ammo text is read off the shipped module
    and off the surface and compared character for character.
    """
    for name in ROW_CASES:
        old = old_row_values(name, monkeypatch)
        new = new_row_values(name, monkeypatch)
        assert new["ammo_text"] == old["ammo_text"], name
    painted = old_row_values("pending", monkeypatch)["ammo_text"]
    swapped = disguise(painted)
    assert swapped != painted
    assert len(swapped) == len(painted)


TEXT_SHAPE_EDITS = {
    "drop_the_dollar_sign": lambda text: text.replace("$", ""),
    "drop_the_thousands_commas": lambda text: text.replace(",", ""),
    "shorten_the_decimals": lambda text: text.replace(".0000", ".00"),
    "sign_the_figure": lambda text: "-" + text,
    "drop_the_stale_marker": lambda text: text.replace(" " + STALE_MARKER_TEXT, ""),
    "add_a_stale_marker": lambda text: text + " " + STALE_MARKER_TEXT,
    "swap_the_decimal_point": lambda text: text.replace(".", ","),
}


def test_the_text_shape_a_picture_may_not_see_is_compared_as_a_string(monkeypatch):
    """A reshaped cell string was left to the render to report.

    Measured on a host with no fonts: dropping the dollar sign from
    ``$50.0000`` paints the same picture, because a missing font
    database makes every family a box font and the cell elides to the
    same run of boxes. Whether any of these edits moves a pixel is a
    fact about the machine, so each is compared as an exact string on
    both sides instead.
    """
    app()
    for name in ROW_CASES:
        old = old_row_values(name, monkeypatch)
        new = new_row_values(name, monkeypatch)
        for field in ("ammo_text", "target_btc_text", "target_eth_text"):
            assert new[field] == old[field], (name, field)
    changed = {}
    stale = old_row_values("stale", monkeypatch)["ammo_text"]
    large = old_row_values("large", monkeypatch)["ammo_text"]
    scrum = old_row_values("scrum", monkeypatch)["ammo_text"]
    for edit_name, edit in TEXT_SHAPE_EDITS.items():
        source = scrum
        if edit_name == "drop_the_stale_marker":
            source = stale
        if edit_name == "drop_the_thousands_commas":
            source = large
        changed[edit_name] = edit(source)
        assert changed[edit_name] != source, edit_name
    assert changed["drop_the_dollar_sign"] == "50.0000"
    assert changed["shorten_the_decimals"] == "$50.00"
    assert changed["sign_the_figure"] == "-$50.0000"
    assert changed["drop_the_stale_marker"] == "$50.0000"
    assert changed["add_a_stale_marker"] == "$50.0000 (stale)"
    assert changed["swap_the_decimal_point"] == "$50,0000"
    assert changed["drop_the_thousands_commas"] == "$999000000000000000.0000"
    assert len(TEXT_SHAPE_EDITS) == 7
    assert len(set(changed.values())) == 7


# What a picture cannot see


def test_the_tooltip_a_picture_cannot_see_is_compared_as_a_string(monkeypatch):
    """The tooltip is not painted into a render.

    A grab of a table carries the cells, not the tooltip that appears
    when the pointer rests on one. Both tooltips are read off the two
    sides and compared character for character.
    """
    app()
    for name in ROW_CASES:
        old = old_row_values(name, monkeypatch)
        new = new_row_values(name, monkeypatch)
        assert new["ammo_tip"] == old["ammo_tip"], name
        assert old["ammo_tip"] != "", name
    painted = build_row(old_row_values("scrum", monkeypatch))
    mirrored = build_row(new_row_values("scrum", monkeypatch))
    assert mirrored.item(0, CALLER_AMMO_COLUMN).toolTip() == (
        painted.item(0, CALLER_AMMO_COLUMN).toolTip()
    )
    assert (
        len({old_row_values(name, monkeypatch)["ammo_tip"] for name in ROW_CASES}) > 5
    )


def test_the_numbers_a_picture_cannot_see_are_compared_as_values(monkeypatch):
    """The delta, the position and the two flags are painted nowhere.

    None of them reaches a pixel, so no render can report a wrong one.
    All four are compared as exact values in every Ammo case, and the
    values they can hold are pinned here.
    """
    app()
    for name in AMMO_CASES:
        if name in AMMO_RAISING_CASES:
            continue
        old = run_old_ammo(name, monkeypatch)["cell"]["value"]
        new = run_new_ammo(name, monkeypatch)["cell"]["value"]
        assert new["delta"] == old["delta"], name
        assert new["position_val"] == old["position_val"], name
        assert new["stale"] is old["stale"], name
        assert new.get("manual_fire_noop") == old.get("manual_fire_noop"), name
        assert new.get("price_age_s") == old.get("price_age_s"), name
    scrum = run_old_ammo("scrum", monkeypatch)["cell"]["value"]
    noop = run_old_ammo("manual_fire_noop", monkeypatch)["cell"]["value"]
    assert scrum["manual_fire_noop"] is False
    assert noop["manual_fire_noop"] is True
    assert scrum["delta"] == pytest.approx(50.0)
    assert scrum["position_val"] == pytest.approx(100.0)
    assert run_old_ammo("at_target", monkeypatch)["cell"]["value"]["delta"] == 0.0
    values = new_row_values("scrum", monkeypatch)
    shipped_side = render_offscreen(
        build_row(old_row_values("scrum", monkeypatch)), PIXEL_SIZE
    )
    assert_pictures_match(
        old_side=shipped_side,
        new_side=render_offscreen(build_row(values), PIXEL_SIZE),
        note="the delta and the flags reach no pixel",
    )


def test_the_denom_units_a_picture_cannot_see_are_compared_as_values(monkeypatch):
    """The units and the drift behind the Target-denom text are not painted.

    The cell paints one string built from both. The two numbers are read
    off the surface and checked against the shipped cell's own text.
    """
    for name in DENOM_CASES:
        if name in DENOM_RAISING_CASES:
            continue
        model, outcome = new_denom_model(name, monkeypatch)
        assert outcome["error"] == "", name
        old_text, old_color = run_old_denom(name, monkeypatch)["cell"]["value"]
        assert model.denom["text"] == old_text, name
        assert model.denom["color"] == old_color, name
        if model.denom_path == surface.DENOM_PATH_PRICED:
            assert surface.units_text(model.denom["units"]) in old_text, name
            assert f"{model.denom['delta']:.1f}%" in old_text, name
        else:
            assert model.denom["units"] == 0.0, name
            assert model.denom["delta"] == 0.0, name
    priced, priced_outcome = new_denom_model("btc_up", monkeypatch)
    assert priced_outcome["error"] == ""
    assert priced.denom["units"] == pytest.approx(500.0 / 60000.0)
    assert priced.denom["delta"] == pytest.approx(2.5)


def test_a_blank_cells_colour_is_compared_as_a_string(monkeypatch):
    """A blank cell paints no glyph, so its colour reaches no pixel.

    Every blank path still declares a colour, and a wrong one would show
    the moment the cell carried text. Both colours are read as strings.
    """
    app()
    for name in DENOM_BLANK_CASES:
        old_text, old_color = run_old_denom(name, monkeypatch)["cell"]["value"]
        new_text, new_color = run_new_denom(name, monkeypatch)["cell"]["value"]
        assert old_text == "", name
        assert new_text == old_text, name
        assert new_color == old_color == TEXT_MED_HEX, name
    blank = new_row_values("stale", monkeypatch)
    assert blank["target_btc_text"] == ""
    assert blank["target_btc_color"] == TEXT_MED_HEX
    assert old_row_values("stale", monkeypatch)["target_btc_color"] == TEXT_MED_HEX
    filled = new_row_values("scrum", monkeypatch)
    assert filled["target_btc_text"] != ""


def test_the_cell_placement_is_the_tables_own():
    """A column, an alignment or a sort rule drifted from the real table."""
    from PySide6.QtCore import Qt

    table = real_table()
    assert table.columnCount() == CALLER_COLUMN_COUNT == surface.COLUMN_COUNT
    assert table.isSortingEnabled() is SORTING_OFF is surface.SORTING_ENABLED
    assert surface.SORT_KEYS == {}
    assert surface.CELL_COLUMNS == {
        surface.TARGET_BTC_CELL: CALLER_TARGET_BTC_COLUMN,
        surface.TARGET_ETH_CELL: CALLER_TARGET_ETH_COLUMN,
        surface.AMMO_CELL: CALLER_AMMO_COLUMN,
    }
    assert len(set(surface.CELL_COLUMNS.values())) == 3
    for column in surface.CELL_COLUMNS.values():
        assert 0 <= column < table.columnCount()
    assert surface.ALIGNMENT_VALUE == CALLER_ALIGNMENT_VALUE
    assert surface.ALIGNMENT_VALUE == int(Qt.AlignCenter.value)
    assert surface.ALIGNMENT == "AlignCenter"
    assert surface.CELL_MASK_KEYS == {
        surface.TARGET_BTC_CELL: CALLER_TARGET_MASK_KEY,
        surface.TARGET_ETH_CELL: CALLER_TARGET_MASK_KEY,
        surface.AMMO_CELL: CALLER_AMMO_MASK_KEY,
    }
    assert surface.CELL_TOOLTIPS == {
        surface.TARGET_BTC_CELL: False,
        surface.TARGET_ETH_CELL: False,
        surface.AMMO_CELL: True,
    }
    assert set(surface.CELL_ICONS.values()) == {False}
    assert surface.CELL_QUOTES == {
        surface.TARGET_BTC_CELL: "BTC",
        surface.TARGET_ETH_CELL: "ETH",
    }
    assert set(surface.CELLS) == set(surface.CELL_COLUMNS)
    assert list(surface.CELLS) == sorted(surface.CELLS, key=surface.CELL_COLUMNS.get)


PAINTED_STATUS = {
    "bot_id": "bot-cells-0001",
    "symbol": "XRP/USD",
    "mode": "scrumming",
    "state": "running",
    "exchange": "coinbase",
    "current_holdings": 104.8,
    "quote_to_usd": 1.0,
    "live_target_balance": 50.0,
    "target_balance": 40.0,
    "stats": {"total_trades": 7, "position_value": 149.85, "current_price": 1.43},
}


def painted_table():
    """One real BotStatusTable carrying one painted row."""
    table = real_table()
    table.update_bots([dict(PAINTED_STATUS)])
    assert table.rowCount() == 1, table.rowCount()
    return table


def test_the_painted_row_places_the_three_cells_where_the_surface_says():
    """The real table paints the row; every column read here is the
    surface's own number."""
    from PySide6.QtCore import Qt

    table = painted_table()
    for cell, column in surface.CELL_COLUMNS.items():
        item = table.item(0, column)
        assert item is not None, cell
        assert item.textAlignment() == int(Qt.AlignCenter.value), cell
        assert item.text() != "", cell
    assert table.isSortingEnabled() is False, "the table started sorting itself"


def test_the_painted_row_carries_a_tooltip_only_where_the_surface_says():
    """The Ammo cell explains itself; the two denom cells do not."""
    table = painted_table()
    for cell, wanted in surface.CELL_TOOLTIPS.items():
        item = table.item(0, surface.CELL_COLUMNS[cell])
        assert bool(item.toolTip()) is wanted, (cell, item.toolTip())


def test_the_painted_row_carries_the_cells_own_tooltip():
    """The Ammo item's tooltip is the string the shipped cell composed."""
    table = painted_table()
    ammo = table.item(0, surface.CELL_COLUMNS[surface.AMMO_CELL])
    cell = shipped._compose_ammo_cell(
        PAINTED_STATUS["stats"]["position_value"],
        PAINTED_STATUS["current_holdings"],
        PAINTED_STATUS["stats"]["current_price"],
        PAINTED_STATUS["quote_to_usd"],
        PAINTED_STATUS["live_target_balance"],
    )
    assert ammo.toolTip() == cell["tip"]
    assert ammo.text() == cell["text"]


def test_the_painted_row_takes_the_ammo_colour_from_the_cell(monkeypatch):
    """Only the cell's colour is swapped, so a different picture can come
    from nothing else."""
    import src.gui.widgets.bot_status_table as table_module

    real = shipped._compose_ammo_cell

    def recoloured(*args, **kwargs):
        cell = dict(real(*args, **kwargs))
        cell["color"] = surface.TERRITORY_COLORS[surface.TERRITORY_FOLD]
        return cell

    before = render_offscreen(painted_table(), PIXEL_SIZE)
    monkeypatch.setattr(table_module, "_compose_ammo_cell", recoloured)
    after = render_offscreen(painted_table(), PIXEL_SIZE)
    assert_pictures_differ(
        old_side=before,
        new_side=after,
        note="the table paints the Ammo cell's own colour",
    )


@pytest.mark.parametrize(
    ("masked_key", "hidden_cells"),
    [
        (CALLER_TARGET_MASK_KEY, (surface.TARGET_BTC_CELL, surface.TARGET_ETH_CELL)),
        (CALLER_AMMO_MASK_KEY, (surface.AMMO_CELL,)),
    ],
)
def test_masking_one_key_hides_exactly_the_cells_that_carry_it(
    masked_key, hidden_cells
):
    """The mask key each cell is painted under, read off the painted row."""
    from src.core.privacy_mask_registry import get_privacy_mask_registry

    registry = get_privacy_mask_registry()
    revealed = {
        cell: painted_table().item(0, column).text()
        for cell, column in surface.CELL_COLUMNS.items()
    }
    registry.set_masked(masked_key, True)
    try:
        masked = {
            cell: painted_table().item(0, column).text()
            for cell, column in surface.CELL_COLUMNS.items()
        }
    finally:
        registry.set_masked(masked_key, False)
    for cell in surface.CELL_COLUMNS:
        if cell in hidden_cells:
            assert masked[cell] != revealed[cell], cell
        else:
            assert masked[cell] == revealed[cell], cell
    assert surface.CELL_MASK_KEYS[hidden_cells[0]] == masked_key


SORTING_OFF = False


def test_the_cells_start_no_timer(monkeypatch):
    """A wait appeared on one side and not the other.

    A cell composes from values it is handed; it waits on nothing. The
    watcher counts every timer any Qt object starts while both rows are
    built, and its positive control proves it counts.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
    started: list = []
    original_start_timer = QObject.startTimer
    original_timer_start = QTimer.start
    original_single_shot = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return original_start_timer(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return original_timer_start(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", args))
        return original_single_shot(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        for name in ("scrum", "stale"):
            build_row(old_row_values(name, monkeypatch))
            build_row(new_row_values(name, monkeypatch))
        observed = list(started)
        started.clear()
        QTimer().start(250)
    finally:
        QObject.startTimer = original_start_timer
        QTimer.start = original_timer_start
        QTimer.singleShot = original_single_shot
    assert started == [("QTimer.start", (250,))]
    assert observed == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(surface.TIMERS) == len(observed) == 0


def test_the_cells_declare_no_skin_of_their_own(monkeypatch):
    """A colour the surface ships is one the table never paints.

    The cells carry no style sheet of their own. ``SKIN`` and
    ``STYLE_SHEET`` are empty on the surface and in the payload, and the two
    shipped sides paint one picture.
    """
    app()
    assert surface.SKIN == {}
    assert surface.STYLE_SHEET == ""
    payload = surface.build_view_model(surface.TableCellsModel())
    assert payload["skin"] == {}
    assert payload["style_sheet"] == ""
    assert_pictures_match(
        old_side=render_offscreen(
            build_row(old_row_values("scrum", monkeypatch)), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            build_row(new_row_values("scrum", monkeypatch)), PIXEL_SIZE
        ),
        note="neither side carries a skin of its own",
    )


BLIND_TO_THE_PICTURE = {
    "ammo_tooltip": "test_the_tooltip_a_picture_cannot_see_is_compared_as_a_string",
    "ammo_delta": "test_the_numbers_a_picture_cannot_see_are_compared_as_values",
    "ammo_position_val": (
        "test_the_numbers_a_picture_cannot_see_are_compared_as_values"
    ),
    "ammo_stale_flag": ("test_the_numbers_a_picture_cannot_see_are_compared_as_values"),
    "manual_fire_noop": (
        "test_the_numbers_a_picture_cannot_see_are_compared_as_values"
    ),
    "price_age_s": "test_the_numbers_a_picture_cannot_see_are_compared_as_values",
    "denom_units": ("test_the_denom_units_a_picture_cannot_see_are_compared_as_values"),
    "denom_delta": ("test_the_denom_units_a_picture_cannot_see_are_compared_as_values"),
    "blank_cell_colour": "test_a_blank_cells_colour_is_compared_as_a_string",
    "mask_key": "test_the_cell_placement_is_the_tables_own",
    "sorting_enabled": "test_the_cell_placement_is_the_tables_own",
    "column_count": "test_the_cell_placement_is_the_tables_own",
    "debug_log": "test_the_debug_logs_are_the_shipped_modules_own",
    "pool_found": "test_the_price_pool_is_the_shipped_pools_own",
    "display_price": "test_the_display_price_is_the_shipped_readers",
    "timer_delay": "test_the_cells_start_no_timer",
    "same_length_text": (
        "test_a_same_length_text_change_is_compared_as_an_exact_string"
    ),
    "text_shape": ("test_the_text_shape_a_picture_may_not_see_is_compared_as_a_string"),
}


def test_everything_a_picture_cannot_see_is_named_and_covered(monkeypatch):
    """A value no render can report was left to the render to report.

    Eighteen values never reach a pixel comparison, each named here
    with the check that does cover it. The tooltip appears only under
    the pointer. The delta, the position value, the two flags and the
    price age are numbers behind the text, never drawn. The units and
    the drift behind a Target-denom string are the same. A blank cell
    paints no glyph, so its colour reaches nothing. The mask key, the
    sort rule and the column count are table settings. The debug line
    goes to the console. Whether the shared price cache was found, and
    which price came back, are read rather than drawn. The cells start
    no timer, so no delay can be seen. Two strings of one length paint
    the same cells on a host with no glyphs, and so do two strings of
    one shape.
    """
    app()
    assert len(BLIND_TO_THE_PICTURE) == 18
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert_pictures_match(
        old_side=render_offscreen(
            build_row(old_row_values("scrum", monkeypatch)), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            build_row(new_row_values("scrum", monkeypatch)), PIXEL_SIZE
        ),
    )


# The pool and the price reader


def test_the_price_pool_is_the_shipped_pools_own(monkeypatch):
    """The surface reached a different shared price cache."""
    for name in ("hit", "no_pool", "pool_import_raises"):
        old = run_old_price(name, monkeypatch)
        new = run_new_price(name, monkeypatch)
        assert new["pool_found"] is old["pool_found"], name
        assert new["calls"] == old["calls"], name
    assert run_old_price("hit", monkeypatch)["pool_found"] is True
    assert run_old_price("no_pool", monkeypatch)["pool_found"] is False
    assert run_old_price("pool_import_raises", monkeypatch)["pool_found"] is False
    model, outcome = new_price_model("hit", monkeypatch)
    assert model.pool_found is True
    assert outcome["error"] == ""
    assert new_price_model("no_pool", monkeypatch)[0].pool_found is False
    assert new_price_model("pool_import_raises", monkeypatch)[0].pool_found is False


def test_the_price_reader_prefers_the_cache(monkeypatch):
    """The reader stopped preferring the cache over the passed price."""
    hit = run_old_price("hit", monkeypatch)["price"]["value"]
    assert hit == [0.5, pytest.approx(3.0)]
    assert run_new_price("hit", monkeypatch)["price"]["value"] == hit
    for name in (
        "no_entry",
        "zero_last",
        "negative_last",
        "no_fetch_time",
        "blank_last",
        "no_pool",
        "falsy_pool",
        "pool_raises",
        "unknown_last",
    ):
        old = run_old_price(name, monkeypatch)["price"]["value"]
        assert old == [0.25, None], name
        assert run_new_price(name, monkeypatch)["price"]["value"] == old, name
    assert run_old_price("future_fetch_time", monkeypatch)["price"]["value"] == [
        0.5,
        0.0,
    ]
    assert run_old_price("hit_old", monkeypatch)["price"]["value"] == [
        0.5,
        pytest.approx(900.0),
    ]
    assert run_old_price("unknown_fallback", monkeypatch)["price"]["value"] == [
        "cheap",
        None,
    ]
    assert surface.MISSING_PRICE_AGE_S is None
    assert surface.YOUNGEST_AGE_S == 0.0


def test_the_price_reader_asks_the_cache_for_the_row_it_paints(monkeypatch):
    """The reader asked the cache for a different exchange or pair."""
    for name in ("hit", "no_entry", "unicode_symbol", "long_symbol", "markup_symbol"):
        old = run_old_price(name, monkeypatch)
        new = run_new_price(name, monkeypatch)
        asked = [call for call in old["calls"] if call[0] == surface.PRICE_LOOKUP]
        assert len(asked) == 1, name
        assert asked[0][1:] == list(PRICE_CASES[name][1][:2]), name
        assert [
            call for call in new["calls"] if call[0] == surface.PRICE_LOOKUP
        ] == asked, name
    absent = run_old_price("no_pool", monkeypatch)
    assert [call for call in absent["calls"] if call[0] == surface.PRICE_LOOKUP] == []
    falsy = run_old_price("falsy_pool", monkeypatch)
    assert [call for call in falsy["calls"] if call[0] == surface.PRICE_LOOKUP] == []


def test_the_price_feeds_the_ammo_cells_age(monkeypatch):
    """The age the reader returns stopped reaching the Ammo cell."""
    fresh = run_old_price("hit", monkeypatch)["price"]["value"]
    old_reading = run_old_price("hit_old", monkeypatch)["price"]["value"]
    assert fresh[1] < surface.PRICE_STALE_AFTER_S
    assert old_reading[1] > surface.PRICE_STALE_AFTER_S
    watch_bands(monkeypatch, shipped)
    marked = shipped._compose_ammo_cell(0.0, 5.0, 20.0, 1.0, 50.0, old_reading[1])
    unmarked = shipped._compose_ammo_cell(0.0, 5.0, 20.0, 1.0, 50.0, fresh[1])
    assert marked["text"].endswith(STALE_MARKER_TEXT)
    assert not unmarked["text"].endswith(STALE_MARKER_TEXT)
    watch_bands(monkeypatch, surface)
    assert (
        surface.TableCellsModel().ammo_cell(0.0, 5.0, 20.0, 1.0, 50.0, old_reading[1])
        == marked
    )
    assert (
        surface.TableCellsModel().ammo_cell(0.0, 5.0, 20.0, 1.0, 50.0, fresh[1])
        == unmarked
    )


# The counterpart map


METHOD_MAP = {
    "_ammo_price_pool": "TableCellsModel.price_pool",
    "_fresh_display_price": "TableCellsModel.fresh_price",
    "_compose_ammo_cell": "TableCellsModel.ammo_cell",
    "_compose_table_target_denom_cell": "TableCellsModel.target_denom_cell",
}

NESTED_MAP = {"_compose_ammo_cell._mag": "magnitude"}

MODEL_MEMBERS = {
    "__init__",
    "price_pool",
    "fresh_price",
    "_priced",
    "ammo_cell",
    "_empty_cell",
    "_pending_cell",
    "_signal_cell",
    "_finish",
    "target_denom_cell",
    "_priced_denom",
    "_denom_finish",
}

HELPER_MAP = {
    "dollar_figure": "magnitude",
    "ammo_figure": "ammo_text",
    "units_figure": "units_text",
    "divergence_signal": "divergence_colour",
    "payload": "build_view_model",
    "bridge_handler": "view_model",
}


def members(owner):
    """Every method and property a class defines, by name."""
    import inspect

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if inspect.isfunction(value) or isinstance(value, property):
            found.add(name)
    return found


def resolve(dotted):
    """The member a dotted name in the map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def shipped_member_names():
    """Every function and class the shipped module defines, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if (inspect.isfunction(value) or inspect.isclass(value))
        and getattr(value, "__module__", "") == shipped.__name__
    }


def test_every_shipped_member_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    assert shipped_member_names() == set(METHOD_MAP)
    assert len(METHOD_MAP) == 4
    for target in METHOD_MAP.values():
        assert resolve(target) is not None, target
    assert members(surface.TableCellsModel) == MODEL_MEMBERS
    assert len(MODEL_MEMBERS) == 12
    assert {target.split(".")[-1] for target in METHOD_MAP.values()} < MODEL_MEMBERS
    assert len(NESTED_MAP) == 1
    for target in NESTED_MAP.values():
        assert callable(resolve(target)), target
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 6


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "_compose_ammo_cell" in shipped_member_names()
    assert "_compose_table_target_denom_cell" in shipped_member_names()
    assert "_ammo_price_pool" in shipped_member_names()
    assert "_fresh_display_price" in shipped_member_names()
    assert "logger" not in shipped_member_names()
    assert "target_territory" not in shipped_member_names()
    assert "manual_fire_dust_band" not in shipped_member_names()
    assert "_mag" not in shipped_member_names()
    with pytest.raises(AttributeError):
        resolve("TableCellsModel.no_such_member")
    assert MODEL_MEMBERS - {"ammo_cell"} != MODEL_MEMBERS
    assert members(surface.TableCellsModel) - {"price_pool"} != MODEL_MEMBERS
    assert set(METHOD_MAP) - {"_compose_ammo_cell"} != set(METHOD_MAP)
    assert set(HELPER_MAP.values()) & MODEL_MEMBERS == set()


def test_the_nested_formatter_is_the_shipped_cells_own(monkeypatch):
    """The dollar formatter inside the cell was left without a counterpart.

    ``_compose_ammo_cell`` defines ``_mag`` inside itself, so it has no
    module name. Its behaviour is read back off the cell text the
    shipped function returns.
    """
    for name, expected in (
        ("scrum", "$50.0000"),
        ("fold", "$25.0000"),
        ("empty", "$50.0000"),
        ("very_large", "$999,000,000,000,000,000.0000"),
    ):
        cell = run_old_ammo(name, monkeypatch)["cell"]["value"]
        assert cell["text"] == expected, name
        assert surface.magnitude(cell["delta"]) == expected, name
    assert surface.magnitude(-25.0) == surface.magnitude(25.0)
    assert surface.magnitude(-25.0) != "-$25.0000"


def test_the_signatures_match_the_shipped_functions():
    """A function stopped taking the arguments the table passes it."""
    import inspect

    pairs = {
        "_ammo_price_pool": "price_pool",
        "_fresh_display_price": "fresh_price",
        "_compose_ammo_cell": "ammo_cell",
        "_compose_table_target_denom_cell": "target_denom_cell",
    }
    for old_name, new_name in pairs.items():
        old = inspect.signature(getattr(shipped, old_name)).parameters
        new = inspect.signature(getattr(surface.TableCellsModel, new_name)).parameters
        assert list(new) == ["self"] + list(old), old_name
    assert list(inspect.signature(shipped._compose_ammo_cell).parameters) == [
        "stats_pv",
        "holdings",
        "cur_price",
        "qrate",
        "target_val",
        "price_age_s",
    ]
    assert list(inspect.signature(shipped._fresh_display_price).parameters) == [
        "pool",
        "exchange_id",
        "symbol",
        "fallback_price",
    ]
    assert list(
        inspect.signature(shipped._compose_table_target_denom_cell).parameters
    ) == ["quote_currency", "base_asset", "exchange_id", "target_usd"]
    assert list(inspect.signature(shipped._ammo_price_pool).parameters) == []
    old_age = inspect.signature(shipped._compose_ammo_cell).parameters["price_age_s"]
    new_age = inspect.signature(surface.TableCellsModel.ammo_cell).parameters[
        "price_age_s"
    ]
    assert old_age.default is None
    assert new_age.default is None
    assert list(AMMO_ARG_NAMES) == list(
        inspect.signature(shipped._compose_ammo_cell).parameters
    )
    assert list(DENOM_ARG_NAMES) == list(
        inspect.signature(shipped._compose_table_target_denom_cell).parameters
    )


def test_neither_cell_module_declares_a_signal_to_wire():
    """The surface exports no action, and neither module carries a Signal
    for the table to connect."""
    from PySide6.QtCore import Signal

    assert surface.ACTIONS == {}
    for module in (shipped, surface):
        signals = [
            name for name, value in vars(module).items() if isinstance(value, Signal)
        ]
        assert signals == [], (module.__name__, signals)


def test_the_table_that_paints_the_cells_does_wire_its_own_signals():
    """The signal check reports none whatever a module declares."""
    from PySide6.QtCore import SignalInstance

    table = real_table()
    wired = [
        name
        for name in dir(type(table))
        if isinstance(getattr(table, name, None), SignalInstance)
    ]
    assert wired, "the real table declares no signal at all"


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    answered = qt_free("src.gui.main_tabs.table_cells_surface", "TableCellsModel")
    assert answered["imported"] is True, answered
    assert answered["qt"] == [], answered


def test_the_qt_block_stops_the_shipped_side():
    """POSITIVE CONTROL for ``qt_free``: src.gui.widgets.bot_status_table needs Qt to load."""
    answered = qt_free("src.gui.widgets.bot_status_table", "BotStatusTable")
    assert answered["imported"] is False, answered


# The bridge


def test_view_model_is_json_serialisable(monkeypatch):
    """The bridge cannot encode what the surface returns."""
    install_market(monkeypatch, DENOM_CASES["btc_up"][0])
    watch_bands(monkeypatch, surface)
    model = surface.TableCellsModel()
    payload = surface.build_view_model(
        model,
        ammo=dict(zip(AMMO_ARG_NAMES, AMMO_CASES["scrum"])),
        denom=dict(zip(DENOM_ARG_NAMES, DENOM_CASES["btc_up"][1])),
    )
    encoded = json.loads(json.dumps(payload))
    assert encoded["ammo"]["text"] == "$50.0000"
    assert encoded["ammo"]["color"] == SUCCESS_HEX
    assert encoded["ammo"]["tip"] == surface.SCRUM_TIP
    assert encoded["ammo"]["manual_fire_noop"] is False
    assert encoded["ammo_path"] == "signal"
    assert encoded["denom"]["text"] == "0.008333 (+2.5%)"
    assert encoded["denom"]["color"] == SUCCESS_HEX
    assert encoded["denom_path"] == "priced"
    assert encoded["cells"] == ["target_btc", "target_eth", "ammo"]
    assert encoded["cell_columns"] == {"target_btc": 5, "target_eth": 6, "ammo": 7}
    assert encoded["alignment_value"] == 132
    assert encoded["column_count"] == 10
    assert encoded["sorting_enabled"] is False
    assert encoded["actions"] == {}
    assert encoded["timer_delays_ms"] == []
    assert encoded["skin"] == {}
    assert encoded["stale_marker"] == STALE_MARKER_TEXT
    assert encoded["price_stale_after_s"] == 20.0
    assert encoded["manual_fire_dust_pct"] == 0.01
    assert encoded["territory_colors"]["scrum"] == SUCCESS_HEX
    assert encoded["ammo_fields"] == list(surface.AMMO_FIELDS)
    assert encoded["denom_paths"] == list(surface.DENOM_PATHS)
    assert encoded["calls"][-1][0] == "denom.return"
    assert [call[0] for call in encoded["calls"]] == [
        "ammo.start",
        "ammo.fresh",
        "ammo.territory",
        "ammo.return",
        "denom.start",
        "denom.rates",
        "denom.pair",
        "denom.usd_pair",
        "denom.delta",
        "denom.return",
    ]
    assert len(encoded["calls"]) == 10


def test_bridge_registers_the_table_cells_method(monkeypatch):
    """The renderer cannot reach the cell surface through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "table_cells.state"
    assert registry[surface.METHOD] is surface.view_model
    install_market(monkeypatch, DENOM_CASES["btc_up"][0])
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 71,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "ammo": dict(zip(AMMO_ARG_NAMES, AMMO_CASES["scrum"])),
                    "denom": dict(zip(DENOM_ARG_NAMES, DENOM_CASES["btc_up"][1])),
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["ammo"]["text"] == "$50.0000"
    assert result["ammo"]["color"] == SUCCESS_HEX
    assert result["ammo_path"] == "signal"
    assert result["denom"]["text"] == "0.008333 (+2.5%)"
    assert result["denom_path"] == "priced"


def test_the_bridge_carries_every_ammo_path(monkeypatch):
    """A path over the bridge returned the wrong cell."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 72, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    for name, path in (
        ("scrum", surface.AMMO_PATH_SIGNAL),
        ("empty", surface.AMMO_PATH_EMPTY),
        ("pending", surface.AMMO_PATH_PENDING),
        ("stale", surface.AMMO_PATH_SIGNAL),
    ):
        painted = call(
            {"reset": True, "ammo": dict(zip(AMMO_ARG_NAMES, AMMO_CASES[name]))}
        )
        assert painted["ammo_path"] == path, name
        expected = run_old_ammo(name, monkeypatch)["cell"]["value"]
        assert painted["ammo"]["text"] == expected["text"], name
        assert painted["ammo"]["color"] == expected["color"], name
        assert painted["ammo"]["tip"] == expected["tip"], name
    idle = call({"reset": True})
    assert idle["ammo"] == {}
    assert idle["ammo_path"] == ""
    assert idle["calls"] == []
    assert idle["pool_found"] is False
    call({"reset": True})


def test_the_bridge_keeps_the_cell_until_a_reset(monkeypatch):
    """The surface forgot its cell between two bridge calls."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 73, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    first = call(
        {"reset": True, "ammo": dict(zip(AMMO_ARG_NAMES, AMMO_CASES["scrum"]))}
    )
    kept = call({})
    assert kept["ammo"] == first["ammo"]
    assert kept["ammo_path"] == first["ammo_path"]
    assert kept["calls"] == first["calls"]
    fresh = call({"reset": True})
    assert fresh["ammo"] == {}
    assert fresh["calls"] == []
    call({"reset": True})


def test_the_bridge_carries_the_price_reading(monkeypatch):
    """A price reading over the bridge returned nothing."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    install_pool(monkeypatch, PRICE_CASES["hit"][0])
    freeze_clock(monkeypatch)
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 74,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "price": {
                        "exchange_id": "coinbase",
                        "symbol": "RAVE/USD",
                        "fallback_price": 0.25,
                    },
                },
            }
        ),
        registry,
    )["result"]
    assert answer["price"] == 0.5
    assert answer["price_age_s"] == pytest.approx(3.0)
    assert answer["pool_found"] is True
    install_pool(monkeypatch, PRICE_CASES["no_pool"][0])
    absent = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 75,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "price": {"exchange_id": "coinbase", "symbol": "RAVE/USD"},
                },
            }
        ),
        registry,
    )["result"]
    assert absent["price"] == 0
    assert absent["price_age_s"] is None
    assert absent["pool_found"] is False
    desktop_bridge.handle_line(
        json.dumps({"id": 76, "method": surface.METHOD, "params": {"reset": True}}),
        registry,
    )


# Without Qt at all

BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

FAKE_MARKET = (
    "import sys, types\n"
    "_rates = types.SimpleNamespace(btc_usd=60000.0, eth_usd=3000.0)\n"
    "_monitor = types.SimpleNamespace(snapshot=lambda: _rates)\n"
    "class _Pair:\n"
    "    def __init__(self, pct):\n"
    "        self.pct_24h = pct\n"
    "_pairs = {('RAVE', 'BTC'): _Pair(3.5), ('RAVE', 'USD'): _Pair(1.0)}\n"
    "class _Scout:\n"
    "    def get_pair(self, base, quote, exchange_id=None):\n"
    "        return _pairs.get((base, quote))\n"
    "_rate_module = types.ModuleType('src.exchange.currency_rate_monitor')\n"
    "_rate_module.get_currency_monitor = lambda: _monitor\n"
    "_scout_module = types.ModuleType('src.exchange.market_pairs_scout')\n"
    "_scout_module.get_scout = lambda: _Scout()\n"
    "sys.modules['src.exchange.currency_rate_monitor'] = _rate_module\n"
    "sys.modules['src.exchange.market_pairs_scout'] = _scout_module\n"
)

BRIDGE_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'table_cells.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = (
    BLOCK_QT + FAKE_MARKET + "import json, sys\n"
    "from src.gui.main_tabs import table_cells_surface as s\n"
    "model = s.TableCellsModel()\n"
    "ammo = model.ammo_cell(0.0, 5.0, 20.0, 1.0, 50.0, None)\n"
    "denom = model.target_denom_cell('BTC', 'RAVE', 'coinbase', 500.0)\n"
    "stale = s.TableCellsModel().ammo_cell(100.0, 0.0, 0.0, 1.0, 50.0, None)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'ammo_text': ammo['text'], 'ammo_color': ammo['color'],\n"
    "    'ammo_tip': ammo['tip'], 'ammo_path': model.ammo_path,\n"
    "    'denom': list(denom), 'denom_path': model.denom_path,\n"
    "    'stale_text': stale['text'], 'stale_color': stale['color'],\n"
    "    'calls': len(model.calls)}))\n"
)


def run_script(source):
    """Run one probe in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the cell surface pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["cells"] == ["target_btc", "target_eth", "ammo"]
    assert result["cell_columns"] == {"target_btc": 5, "target_eth": 6, "ammo": 7}
    assert result["territory_colors"]["scrum"] == SUCCESS_HEX
    assert result["territory_colors"]["fold"] == ERROR_HEX
    assert result["territory_colors"]["at_target"] == TEXT_MED_HEX
    assert result["stale_marker"] == STALE_MARKER_TEXT
    assert result["alignment_value"] == 132
    assert result["ammo"] == {}
    assert result["denom"] == {}


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_composes_both_cells_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["ammo_text"] == "$50.0000"
    assert answered["ammo_color"] == SUCCESS_HEX
    assert answered["ammo_tip"] == surface.SCRUM_TIP
    assert answered["ammo_path"] == "signal"
    assert answered["denom"] == ["0.008333 (+2.5%)", SUCCESS_HEX]
    assert answered["denom_path"] == "priced"
    assert answered["stale_text"] == "$50.0000 (stale)"
    assert answered["stale_color"] == TEXT_MED_HEX
    assert answered["calls"] == 10


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_paints_the_table():
    """The Qt block let a module through that imports PySide6."""
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui import instance_consent_dialog\n"
        "    blocked = False\n"
        "except ImportError:\n"
        "    blocked = True\n"
        "print(json.dumps({'blocked': blocked}))\n"
    )
    assert run_script(probe)["blocked"] is True


def test_the_shipped_cells_need_no_qt_either():
    """The shipped module grew a Qt import the surface would inherit."""
    probe = BLOCK_QT + (
        "import json, sys\n"
        "from src.gui import table_cells\n"
        "cell = table_cells._compose_ammo_cell(0.0, 5.0, 20.0, 1.0, 50.0)\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
        "    'text': cell['text'], 'color': cell['color'],\n"
        "    'fields': list(cell)}))\n"
    )
    answered = run_script(probe)
    assert answered["qt"] is False
    assert answered["text"] == "$50.0000"
    assert answered["color"] == SUCCESS_HEX
    assert answered["fields"] == list(surface.AMMO_FIELDS)
