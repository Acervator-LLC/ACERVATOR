"""The Ammo cell must not present an old price as a current one.

THE CORRECTION THIS PINS
The bulk ticker refresher was shipped 2026-08-06 believing it unstuck
the stale Ammo readout. It did not. The dashboard reads
`stats.current_price` (main_window.py), whose only recurring writer is
`ScrummingBot.tick` in `src/trading/scrumming_bot.py` -- downstream of
the read-rate gate. Warming the shared cache never writes that field,
so the READOUT was exactly as stale as before: 60s on 29 bots, 300s on
6, against a 2s repaint.

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
band is 1% (`manual_fire_dust_band` in `src/trading/target_bands.py`,
checked in `_execute_manual_rebalance`,
`src/trading/scrumming/execution.py`). In that 10x window the cell
rendered a confident signal colour for an order that silently never
happened -- "already within dust band ... No-op". Zero is one of the
operator's "strange, intermittent and hard to explain amounts".
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

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


class _FireBus:
    def __init__(self):
        self.messages = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")


class _FireStats:
    def __init__(self):
        self.total_trades = 0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0
        self.last_trade_time = 0.0


class _FireConfig:
    symbol = "CHIP/USD"
    target_asset = "CHIP"
    exchange_id = "coinbase"
    scrumming_interval_pct = 1.0
    trading_fee_pct = 0.6
    max_target_growth_pct = 0.0
    profit_folding_active = True
    scrum_fold_pct = 100


class _FireOrder:
    id = "ammo-1"
    filled = 0.0
    average = 0.0


class _FireTicker:
    def __init__(self, last):
        self.last = last


def _fire_at(position_usd: float, target: float):
    """One real ``_execute_manual_rebalance`` run at ``position_usd``.

    Price is $1, so holdings and USD are the same number and the delta the
    engine reads is ``position_usd - target``. Only the outward edges are
    stubbed; ``bot.placed`` records every order the run placed.
    """
    import asyncio

    from src.trading.scrumming_bot import ScrummingBot

    holdings = position_usd
    bot: Any = object.__new__(ScrummingBot)
    bot.bot_id = "ammo-bot"
    bot.placed = []
    bot._bus = _FireBus()
    bot.config = _FireConfig()
    bot.stats = _FireStats()
    bot._fold_tranches = []
    bot._main_lots = [{"units": holdings, "initial_buy_price": 0.9}]
    bot._current_holdings = holdings
    bot._target_balance = target
    bot._anchor_target_balance = target
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._tranches_created_lifetime = 0
    bot._fold_queue_usd = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = None
    bot._pending_wire_credits = 0.0

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.placed.append(dict(kwargs))
        return _FireOrder()

    async def _settled(order, symbol, requested, tick_price):
        del order, symbol, tick_price
        return requested, 1.0, True

    async def _balance(currency):
        del currency
        return type("B", (), {"total": holdings, "free": holdings, "absent": False})()

    def _ignore(*args, **kwargs):
        del args, kwargs

    def _route(scrum_usd, sell_fill, label):
        del scrum_usd, sell_fill, label
        return 0.0

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._route_scrum_proceeds_via_wires = _route
    bot._emit_voting_panel_snapshot_at_fire = _ignore
    bot._emit_gate_decision_at_fire = _ignore
    bot._reset_opposing_hysteresis_after_fill = _ignore
    bot.note_scrum_retention_usd = _ignore
    asyncio.run(bot._execute_manual_rebalance(_FireTicker(1.0), "manual_button"))
    return bot


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
        # Cell band 0.10, Manual Fire band 1.00: a 0.50 delta acts on the cell
        # alone.
        out = _compose_ammo_cell(0.0, 1.0, 100.5, 1.0, 100.0)
        assert out["manual_fire_noop"] is True
        assert "MANUAL FIRE WILL NOT ACT" in out["tip"]

    def test_a_delta_outside_it_is_not_flagged(self):
        out = _compose_ammo_cell(0.0, 1.0, 105.0, 1.0, 100.0)
        assert out["manual_fire_noop"] is False
        assert "MANUAL FIRE WILL NOT ACT" not in out["tip"]

    def test_the_cell_and_the_engine_read_one_band(self):
        """The cell's percentage is the engine's own object, not a copy."""
        from src.trading.target_bands import MANUAL_FIRE_PCT, manual_fire_dust_band

        assert _MANUAL_FIRE_DUST_PCT is MANUAL_FIRE_PCT
        for target in (0.0, 0.001, 0.5, 1.0, 1.0000001, 47.13, 100.0, 1e6):
            assert manual_fire_dust_band(target) == max(
                target * MANUAL_FIRE_PCT, 0.01
            ), target

    @pytest.mark.parametrize("target", [0.5, 47.13, 100.0, 12500.0])
    def test_the_engine_refuses_up_to_the_band_the_cell_warns_about(self, target):
        """The surplus at which the engine starts trading is measured by
        bisecting real fires, then compared with the band the cell reads."""
        from src.trading.target_bands import manual_fire_dust_band

        band = manual_fire_dust_band(target)
        low, high = 0.0, band * 4.0
        assert _fire_at(target + low, target).placed == [], "a zero surplus traded"
        opened = _fire_at(target + high, target).placed
        assert len(opened) == 1 and opened[0]["side"].value == "sell", opened
        for _ in range(40):
            middle = (low + high) / 2.0
            if _fire_at(target + middle, target).placed:
                high = middle
            else:
                low = middle
        assert high == pytest.approx(band, rel=1e-9), (
            f"the engine starts trading at a ${high:.10f} surplus, but the "
            f"cell warns up to ${band:.10f}"
        )

    @pytest.mark.parametrize("target", [0.5, 47.13, 100.0, 12500.0])
    def test_the_cell_warns_up_to_the_same_band(self, target):
        """The cell's warning boundary, bisected the same way."""
        from src.trading.target_bands import manual_fire_dust_band

        band = manual_fire_dust_band(target)
        low, high = 0.0, band * 4.0
        assert (
            _compose_ammo_cell(0.0, 1.0, target + high, 1.0, target)["manual_fire_noop"]
            is False
        ), "the cell warns past four times its own band"
        for _ in range(40):
            middle = (low + high) / 2.0
            if _compose_ammo_cell(0.0, 1.0, target + middle, 1.0, target)[
                "manual_fire_noop"
            ]:
                low = middle
            else:
                high = middle
        assert high == pytest.approx(band, rel=1e-9)

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
