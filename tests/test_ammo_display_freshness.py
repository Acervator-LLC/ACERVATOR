"""The Ammo cell must not present an old price as a current one.

THE CORRECTION THIS PINS
The bulk ticker refresher was shipped 2026-08-06 believing it unstuck
the stale Ammo readout. It did not. The dashboard reads
`stats.current_price` (main_window.py), whose only recurring writer is
`scrumming_bot.py:5136` -- downstream of the read-rate gate. Warming the
shared cache never writes that field, so the READOUT was exactly as
stale as before: 60s on 29 bots, 300s on 6, against a 2s repaint.

`_fresh_display_price` is the half that was missing: it reads the pool
cache the refresher keeps warm. DISPLAY ONLY -- the trading path still
reads `stats.current_price` on its own cadence, so nothing here changes
what any bot decides or transacts.

THE PREFERENCE IS ALWAYS SAFE
A bot populates `stats.current_price` FROM a pool fetch, so the cache is
written at or before the same instant. The pool entry can therefore
never be older than the stats field, and preferring it is a freshness
win rather than a trade-off.

SECOND DEFECT PINNED HERE (the 10x band split)
The cell's actionable band is 0.1% of target; Manual Fire's own no-op
band is 1% (`scrumming_bot.py:9248`). In that 10x window the cell
rendered a confident signal colour for an order that silently never
happened -- "already within dust band ... No-op". Zero is one of the
operator's "strange, intermittent and hard to explain amounts".
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_window import (  # noqa: E402
    _MANUAL_FIRE_DUST_PCT,
    _PRICE_STALE_AFTER_S,
    _STALE_MARKER,
    _compose_ammo_cell,
    _fresh_display_price,
)


class _Entry:
    def __init__(self, last, age_s):
        self.last = last
        self.fetch_time = time.time() - age_s


class _Pool:
    def __init__(self, entry=None, boom=False):
        self._entry = entry
        self._boom = boom
        self.asked = []

    def get_ticker(self, exchange_id, symbol):
        self.asked.append((exchange_id, symbol))
        if self._boom:
            raise RuntimeError("pool exploded")
        return self._entry


class TestTheFreshPriceReader:
    def test_it_prefers_the_pool_price(self):
        """POSITIVE CONTROL: without this the whole fix is inert."""
        price, age = _fresh_display_price(
            _Pool(_Entry(250.0, 2.0)), "coinbase", "BTC/USD", 100.0
        )
        assert price == pytest.approx(250.0)
        assert age == pytest.approx(2.0, abs=1.0)

    def test_it_reports_the_age(self):
        _, age = _fresh_display_price(
            _Pool(_Entry(250.0, 120.0)), "coinbase", "BTC/USD", 100.0
        )
        assert age == pytest.approx(120.0, abs=2.0)

    def test_no_pool_falls_back_with_no_age(self):
        """Harnesses and paper mode never wire a pool; the dashboard
        must still render."""
        price, age = _fresh_display_price(None, "coinbase", "BTC/USD", 100.0)
        assert price == pytest.approx(100.0)
        assert age is None

    def test_a_missing_entry_falls_back(self):
        price, age = _fresh_display_price(_Pool(None), "coinbase", "NEW/USD", 100.0)
        assert price == pytest.approx(100.0) and age is None

    def test_a_zero_price_entry_falls_back(self):
        """A cache slot registered but never filled must not blank the
        readout."""
        price, _ = _fresh_display_price(
            _Pool(_Entry(0.0, 1.0)), "coinbase", "BTC/USD", 100.0
        )
        assert price == pytest.approx(100.0)

    def test_a_raising_pool_does_not_break_the_dashboard(self):
        price, age = _fresh_display_price(
            _Pool(boom=True), "coinbase", "BTC/USD", 100.0
        )
        assert price == pytest.approx(100.0) and age is None

    def test_it_asks_for_the_right_symbol(self):
        pool = _Pool(_Entry(1.0, 1.0))
        _fresh_display_price(pool, "kraken", "ETH/USD", 0.0)
        assert pool.asked == [("kraken", "ETH/USD")]


class TestTheAgeIsSurfaced:
    def test_a_fresh_price_is_not_marked(self):
        """NEGATIVE CONTROL: marking everything would be as useless as
        marking nothing."""
        out = _compose_ammo_cell(0.0, 2.0, 50.0, 1.0, 80.0, price_age_s=3.0)
        assert _STALE_MARKER not in out["text"]

    def test_an_old_price_is_marked(self):
        out = _compose_ammo_cell(
            0.0, 2.0, 50.0, 1.0, 80.0, price_age_s=_PRICE_STALE_AFTER_S + 60
        )
        assert _STALE_MARKER in out["text"]
        assert "old" in out["tip"].lower()

    def test_an_unknown_age_is_not_marked(self):
        """No pool wired is not evidence of staleness."""
        out = _compose_ammo_cell(0.0, 2.0, 50.0, 1.0, 80.0, price_age_s=None)
        assert _STALE_MARKER not in out["text"]

    def test_the_age_is_returned_for_callers(self):
        out = _compose_ammo_cell(0.0, 2.0, 50.0, 1.0, 80.0, price_age_s=42.0)
        assert out["price_age_s"] == pytest.approx(42.0)

    def test_the_default_keeps_existing_callers_working(self):
        out = _compose_ammo_cell(0.0, 2.0, 50.0, 1.0, 80.0)
        assert _STALE_MARKER not in out["text"]
        assert out["price_age_s"] is None

    def test_an_old_price_loses_its_signal_colour(self):
        """A confident green on a five-minute-old number is the defect."""
        fresh = _compose_ammo_cell(0.0, 2.0, 50.0, 1.0, 80.0, price_age_s=1.0)
        old = _compose_ammo_cell(
            0.0, 2.0, 50.0, 1.0, 80.0, price_age_s=_PRICE_STALE_AFTER_S + 60
        )
        assert fresh["color"] != old["color"]


class TestTheManualFireBandSplit:
    """0.1% cell band vs 1% Manual Fire band -- a 10x window where the
    cell says act and the button does nothing."""

    def test_a_delta_inside_manual_fires_band_is_flagged(self):
        # target 100 -> cell band 0.10, Manual Fire band 1.00.
        # position 100.5 -> delta 0.50: actionable to the cell, no-op to
        # Manual Fire.
        out = _compose_ammo_cell(0.0, 1.0, 100.5, 1.0, 100.0)
        assert out["manual_fire_noop"] is True
        assert "MANUAL FIRE WILL NOT ACT" in out["tip"]

    def test_a_delta_outside_it_is_not_flagged(self):
        out = _compose_ammo_cell(0.0, 1.0, 105.0, 1.0, 100.0)
        assert out["manual_fire_noop"] is False
        assert "MANUAL FIRE WILL NOT ACT" not in out["tip"]

    def test_the_band_matches_the_engine_constant(self):
        """If the engine's 1% ever moves, this must move with it or the
        warning starts lying."""
        import ast

        import src.trading.scrumming_bot as sb

        src = Path(sb.__file__).read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_execute_manual_rebalance"
        )
        seg = ast.get_source_segment(src, fn) or ""
        assert (
            f"* {_MANUAL_FIRE_DUST_PCT}" in seg
        ), "engine dust band no longer matches _MANUAL_FIRE_DUST_PCT"

    def test_an_exactly_zero_delta_is_not_flagged(self):
        """A bot sitting precisely on target is not a surprising no-op."""
        out = _compose_ammo_cell(0.0, 1.0, 100.0, 1.0, 100.0)
        assert out["manual_fire_noop"] is False

    def test_a_stale_reading_does_not_claim_to_know(self):
        """With no price the delta is not trustworthy enough to promise
        what Manual Fire will do."""
        out = _compose_ammo_cell(50.0, 1.0, 0.0, 1.0, 100.0)
        assert out["stale"] is True
        assert "MANUAL FIRE WILL NOT ACT" not in out["tip"]
