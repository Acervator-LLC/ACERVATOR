"""One sell opens one fold tranche, unless the trend is strong.

``_bound_new_fold_tranches`` merges the slice a single sell appended and
carries ``_scrum_sells_lifetime``, so ``_tranches_created_lifetime``
counts sells and not ``_main_lots`` entries. The three build loops that
answer it are ``_tick_execute_scrum``, ``_tick_distribute`` and
``_execute_manual_rebalance``. The exception keeps the per-lot split
when ``_last_trend_bull_candles`` passes
``_STRONG_TREND_MIN_BULL_CANDLES`` out of ``_STRONG_TREND_CANDLES``.
"""

from __future__ import annotations

import asyncio

import pytest

from src.trading.scrumming.fold_tranches import (
    _STRONG_TREND_CANDLES,
    _STRONG_TREND_MIN_BULL_CANDLES,
)
from src.trading.scrumming_bot import (
    _STRONG_TREND_MIN_BULL_SHARE,
    ScrummingBot,
)

# Money is compared to the bit. A tolerance would hide the drift these
# comparisons exist to catch.
EXACT = 0.0

# Two ULP of double precision, the worst case measured over 20,000 sales.
# Exact is unavailable: a weighted mean divides.
TWO_ULP = 1e-15


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")


class _Config:
    def __init__(self, fold_pct=100):
        self.scrum_fold_pct = fold_pct
        self.symbol = "BONK/USD"
        self.target_asset = "BONK"
        self.max_target_growth_pct = 1.0
        self.profit_folding_active = True


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_sells = 0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0
        self.tranches_discarded_lifetime = 0


class _Order:
    id = "order-1"
    filled = 0.0
    average = 0.0


class _Ticker:
    def __init__(self, last):
        self.last = last


def _lots(n, offset=0):
    """``n`` lots with distinct sizes and distinct cost bases.

    A FIXED WALK, not a generator. The live fleet's lot books run from 2
    to 278 entries at prices spanning 1e-8 to 61234, so the shape that
    matters is "many entries, all different, wide basis spread". Two
    coprime strides give that without a value that moves between runs --
    a fixture that moves cannot be quoted in a failure message.
    """
    return [
        {
            "units": 1.0 + ((i + offset) * 7 % 23) * 0.5,
            "initial_buy_price": 0.2 + ((i + offset) * 13 % 29) * 0.1,
        }
        for i in range(n)
    ]


def _bot(*, lots, bull=0, created=0, sells=0, standing=None, fold_pct=100):
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "bound-bot"
    bot._bus = _Bus()
    bot.config = _Config(fold_pct)
    bot.stats = _Stats()
    bot._fold_tranches = list(standing or [])
    bot._main_lots = [dict(lot) for lot in lots]
    bot._tranches_created_lifetime = created
    bot._scrum_sells_lifetime = sells
    bot._last_trend_bull_candles = bull
    return bot


def _build(bot, sale_usd, sale_units, ref):
    """The shipping build loop, run against ``bot``'s own lot book.

    Reproduced rather than imported because it is inline in ``tick``.
    ``test_the_reproduced_build_loop_matches_the_shipping_one`` pins it
    against the real ``_execute_manual_rebalance``, so a drift in either
    is caught rather than assumed away.
    """
    first = len(bot._fold_tranches)
    bot._main_lots.sort(key=lambda lot: lot["initial_buy_price"], reverse=True)
    remaining = sale_units
    for lot in list(bot._main_lots):
        if remaining <= 1e-12:
            break
        take = min(lot["units"], remaining)
        if take <= 1e-12:
            continue
        bot._fold_tranches.append(
            {
                "usd": (take / sale_units) * sale_usd,
                "units": take,
                "ref": ref,
                "initial_buy_price": lot["initial_buy_price"],
                "created_ts": 1.0,
            }
        )
        bot._tranches_created_lifetime += 1
        lot["units"] -= take
        remaining -= take
        if lot["units"] <= 1e-12:
            bot._main_lots.remove(lot)
    return first


# ── THE BOUND ────────────────────────────────────────────────────────


@pytest.mark.parametrize("n_lots", [2, 3, 7, 12, 40])
def test_one_sell_opens_one_tranche_however_many_lots_it_walks(n_lots):
    """Red here means a sell can again open one tranche per lot."""
    lots = _lots(n_lots)
    bot = _bot(lots=lots)
    units = sum(lot["units"] for lot in lots)
    first = _build(bot, units * 1.1, units, 1.1)
    assert len(bot._fold_tranches) == n_lots, "the build loop is not the shipping one"

    bot._bound_new_fold_tranches(first)

    assert len(bot._fold_tranches) == 1
    assert bot._tranches_created_lifetime == 1
    assert bot._scrum_sells_lifetime == 1


def test_the_count_tracks_the_sells_that_produced_it():
    """Red here means the created counter outruns the sells again."""
    bot = _bot(lots=_lots(30))
    for sale in range(6):
        units = sum(lot["units"] for lot in bot._main_lots) / 6.0
        first = _build(bot, units * (1.0 + sale), units, 1.0 + sale)
        bot._bound_new_fold_tranches(first)
        assert bot._tranches_created_lifetime <= bot._scrum_sells_lifetime, (
            f"after {sale + 1} sell(s) the bot has opened "
            f"{bot._tranches_created_lifetime} tranches against "
            f"{bot._scrum_sells_lifetime} sells"
        )
    assert bot._scrum_sells_lifetime == 6
    assert bot._tranches_created_lifetime == 6
    assert len(bot._fold_tranches) == 6


def test_a_sell_that_opens_no_tranche_is_not_counted_as_a_scrum():
    """Red means an empty lot book inflates the rule's denominator."""
    bot = _bot(lots=[])
    assert bot._bound_new_fold_tranches(0) == 0
    assert bot._scrum_sells_lifetime == 0


def test_an_earlier_sells_tranches_are_never_merged_in():
    """Red means the merge reaches back past this sell's own slice."""
    older = [
        {"usd": 5.0, "units": 5.0, "ref": 1.0, "initial_buy_price": 0.9},
        {"usd": 6.0, "units": 6.0, "ref": 1.2, "initial_buy_price": 0.8},
    ]
    bot = _bot(lots=_lots(4), standing=[dict(t) for t in older], created=2, sells=2)
    units = sum(lot["units"] for lot in bot._main_lots)
    first = _build(bot, units * 2.0, units, 2.0)
    assert first == 2
    bot._bound_new_fold_tranches(first)
    assert len(bot._fold_tranches) == 3
    for kept, was in zip(bot._fold_tranches[:2], older):
        assert kept == was


# ── THE EXCEPTION. THIS IS THE VACUOUS-PASS CONTROL. ─────────────────


def _fires_by_share(bull_candles):
    """TREND-HOLD's own test, spelled the way ``tick`` spells it.

    The code under test compares two INTEGERS -- ``bull_count`` against
    13. This is the SHARE form the threshold was born in, kept whole so
    the tests below assert that the two formulations answer alike
    rather than restating the one they are checking.
    """
    return bull_candles / _STRONG_TREND_CANDLES > _STRONG_TREND_MIN_BULL_SHARE


def test_the_share_form_and_the_count_form_agree_over_the_whole_domain():
    """Red means the exception stopped meaning what TREND-HOLD means.

    ``bull_count`` is an integer in [0, 20]. Both readings are driven
    over every value of it, and the two sets must be the same set --
    not the same size.
    """
    domain = range(_STRONG_TREND_CANDLES + 1)
    by_share = [n for n in domain if _fires_by_share(n)]
    by_count = [n for n in domain if n > _STRONG_TREND_MIN_BULL_CANDLES]
    assert by_share == by_count
    assert by_share, "no reading fires; the comparison has no true case"
    assert (
        len(by_share) < _STRONG_TREND_CANDLES + 1
    ), "every reading fires; the comparison has no false case"


@pytest.mark.parametrize("n_lots", [2, 5, 12])
def test_a_strong_trend_keeps_the_per_lot_split(n_lots):
    """Red means the bound became unconditional and the exception died.

    A cap that always caps passes every bound-only assertion in this
    file. This is the test that tells the two apart.
    """
    lots = _lots(n_lots)
    bot = _bot(lots=lots, bull=_STRONG_TREND_MIN_BULL_CANDLES + 1)
    units = sum(lot["units"] for lot in lots)
    first = _build(bot, units, units, 1.0)

    assert bot._bound_new_fold_tranches(first) == 0
    assert len(bot._fold_tranches) == n_lots
    assert bot._tranches_created_lifetime == n_lots
    assert bot._scrum_sells_lifetime == 1, "the sell is counted either way"
    assert any("BOUND LIFTED" in m for m in bot._bus.messages)


@pytest.mark.parametrize("bull", range(_STRONG_TREND_CANDLES + 1))
def test_the_exception_answers_the_whole_closed_domain(bull):
    """Red means the exception fires on a reading that is not a trend.

    ``bull_count`` is an integer in [0, 20], so the domain is CLOSED and
    every value in it is driven rather than a few rows chosen by hand.
    The expectation is derived from TREND-HOLD's own share test, which
    is the definition this exception borrows -- not from the count test
    the code under test uses, which would be the instrument agreeing
    with itself.
    """
    trend_hold_fires = _fires_by_share(bull)

    lots = _lots(4)
    bot = _bot(lots=[dict(lot) for lot in lots], bull=bull)
    assert bot._strong_trend_now() is trend_hold_fires

    units = sum(lot["units"] for lot in lots)
    bot._bound_new_fold_tranches(_build(bot, units, units, 1.0))
    want_rows = 4 if trend_hold_fires else 1
    assert len(bot._fold_tranches) == want_rows


@pytest.mark.parametrize("reading", [None, float("nan"), float("inf"), "20", True])
def test_an_unreadable_trend_reading_does_not_lift_the_bound(reading):
    """Red means a corrupt reading can loosen a bound. It must not."""
    lots = _lots(5)
    bot = _bot(lots=lots)
    bot._last_trend_bull_candles = reading
    assert bot._strong_trend_now() is False
    units = sum(lot["units"] for lot in lots)
    bot._bound_new_fold_tranches(_build(bot, units, units, 1.0))
    assert len(bot._fold_tranches) == 1


def test_a_bot_that_has_not_measured_the_market_gets_the_bound():
    """Red means a fresh bot takes the exception before any candle."""
    bot = object.__new__(ScrummingBot)
    assert bot._strong_trend_now() is False


# ── THE VALUES. A SECOND WITNESS, ON A DIFFERENT CODE PATH. ──────────


@pytest.mark.parametrize("n_lots", [2, 3, 9, 25])
def test_the_merge_conserves_every_money_quantity(n_lots):
    """Red means the collapse moved money, not just record count."""
    lots = _lots(n_lots, offset=n_lots)
    bot = _bot(lots=lots)
    units = sum(lot["units"] for lot in lots)
    first = _build(bot, units * 0.87, units, 0.87)
    before = list(bot._fold_tranches[first:])

    want_usd = sum(t["usd"] for t in before)
    want_units = sum(t["units"] for t in before)
    want_cost = sum(t["units"] * t["initial_buy_price"] for t in before)
    want_at_sale = sum(t["usd"] / t["ref"] for t in before)

    bot._bound_new_fold_tranches(first)
    got = bot._fold_tranches[-1]

    assert abs(got["usd"] - want_usd) <= EXACT
    assert abs(got["units"] - want_units) <= EXACT
    assert got["ref"] == before[0]["ref"], "one fill wrote them all; keep it verbatim"

    got_cost = got["units"] * got["initial_buy_price"]
    assert got_cost == pytest.approx(want_cost, rel=TWO_ULP)

    got_at_sale = got["usd"] / got["ref"]
    assert got_at_sale == pytest.approx(want_at_sale, rel=TWO_ULP)


def test_the_skim_cost_basis_is_the_second_witness():
    """Red means ``_apply_scrum_fold_pct`` now sees a different basis.

    ``_apply_scrum_fold_pct`` is a separate method that sums
    ``units x initial_buy_price`` for its own purpose. Running it on the
    merged record and on the unmerged slice must leave the same dollars
    queued -- that is the conservation asserted above, read at a
    consumer written without knowing this method exists.
    """
    lots = _lots(8, offset=3)
    units = sum(lot["units"] for lot in lots)

    unmerged = _bot(lots=[dict(lot) for lot in lots], fold_pct=40)
    first = _build(unmerged, units * 1.3, units, 1.3)
    unmerged._apply_scrum_fold_pct(first, units * 1.3, units)

    merged = _bot(lots=[dict(lot) for lot in lots], fold_pct=40)
    first = _build(merged, units * 1.3, units, 1.3)
    merged._bound_new_fold_tranches(first)
    merged._apply_scrum_fold_pct(first, units * 1.3, units)

    want_usd = sum(t["usd"] for t in unmerged._fold_tranches)
    got_usd = sum(t["usd"] for t in merged._fold_tranches)
    assert got_usd == pytest.approx(want_usd, rel=TWO_ULP)

    want_units = sum(t["units"] for t in unmerged._fold_tranches)
    got_units = sum(t["units"] for t in merged._fold_tranches)
    assert got_units == pytest.approx(want_units, rel=TWO_ULP)


def test_the_basis_is_units_weighted_and_not_the_lowest():
    """Red means the merged basis stopped conserving the cost book.

    Both candidate bases are computed here, independently of the
    shipping code, and the fixture is required to SEPARATE them. If
    they agree, the fixture no longer discriminates and this test
    proves nothing.

    Every comparison is stated as a COST -- a basis times the units it
    covers -- so both sides carry the same units. Dividing to get a
    per-unit basis and comparing that against a price is the
    units-mixing shape ``ta_archetype`` refuses by name.
    """
    lots = _lots(20, offset=11)
    bot = _bot(lots=lots)
    units = sum(lot["units"] for lot in lots)
    first = _build(bot, units, units, 1.0)
    fresh = list(bot._fold_tranches[first:])

    total_units = sum(t["units"] for t in fresh)
    total_cost = sum(t["units"] * t["initial_buy_price"] for t in fresh)
    lowest = min(t["initial_buy_price"] for t in fresh)
    assert lowest * total_units < total_cost * 0.75, (
        "the fixture no longer separates the two candidate bases, so "
        "this test cannot tell them apart"
    )

    bot._bound_new_fold_tranches(first)
    got = bot._fold_tranches[-1]
    got_cost = got["initial_buy_price"] * total_units
    assert got_cost == pytest.approx(total_cost, rel=TWO_ULP)
    assert got["units"] * got["initial_buy_price"] == pytest.approx(
        total_cost, rel=TWO_ULP
    )


# ── MALFORMED RECORDS ARE LEFT WHERE THE DROPPER CAN SEE THEM ────────


@pytest.mark.parametrize(
    "field,value",
    [
        ("units", float("nan")),
        ("usd", float("inf")),
        ("ref", 0.0),
        ("ref", "1.0"),
        ("initial_buy_price", None),
    ],
)
def test_an_unreadable_record_stops_the_merge_rather_than_absorbing_it(field, value):
    """Red means a malformed row can be folded into a good one."""
    lots = _lots(4)
    bot = _bot(lots=lots)
    units = sum(lot["units"] for lot in lots)
    first = _build(bot, units, units, 1.0)
    bot._fold_tranches[-1][field] = value

    assert bot._bound_new_fold_tranches(first) == 0
    assert len(bot._fold_tranches) == 4
    assert bot._scrum_sells_lifetime == 1


# ── THE THREE SHIPPING PATHS ─────────────────────────────────────────


def _manual_bot(*, lots, bull=0, holdings=1000.0, target=100.0, price=1.0):
    """A bot that can run the real ``_execute_manual_rebalance``.

    Only the outward edges are stubbed -- the exchange, the wire
    routing, the emitters. Everything between the sell and the tranche
    list is the shipping code. Every stub RECORDS its arguments, so a
    test can read what the shipping code actually asked for rather than
    only what it did afterwards.
    """
    bot = _bot(lots=lots, bull=bull)
    bot.seen = {"placed": None, "settled": None, "routed": [], "balances": []}
    bot._current_holdings = holdings
    bot._target_balance = target
    bot._anchor_target_balance = target
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._fold_queue_usd = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._pending_wire_credits = 0.0

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.seen["placed"] = kwargs
        return _Order()

    async def _settled(order, symbol, requested, tick_price):
        bot.seen["settled"] = (order.id, symbol, requested, tick_price)
        return requested, price, True

    async def _balance(currency):
        bot.seen["balances"].append(currency)
        return type("B", (), {"total": holdings, "free": holdings, "absent": False})()

    def _route(scrum_usd, sell_fill, label):
        bot.seen["routed"].append((scrum_usd, sell_fill, label))
        return 0.0

    def _snapshot(side, trade_action):
        bot.seen.setdefault("snapshots", []).append((side, trade_action))

    def _gate(side, trade_action):
        bot.seen.setdefault("gates", []).append((side, trade_action))

    def _retained(retained_usd):
        bot.seen.setdefault("retained", []).append(retained_usd)

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._route_scrum_proceeds_via_wires = _route
    bot._emit_voting_panel_snapshot_at_fire = _snapshot
    bot._emit_gate_decision_at_fire = _gate
    bot._reset_opposing_hysteresis_after_fill = lambda: bot.seen.setdefault(
        "disarms", []
    ).append(True)
    bot.note_scrum_retention_usd = _retained
    return bot


def test_a_real_manual_fire_leaves_one_tranche():
    """Red means the third build loop escaped the rule.

    Two of this method's three callers -- Wire Stack and Max Cartridge
    -- fire autonomously, so an escape here is not bounded by clicks.
    """
    bot = _manual_bot(lots=_lots(9))
    asyncio.run(bot._execute_manual_rebalance(_Ticker(1.0), "manual_button"))
    assert bot.seen["placed"] is not None, "no sell was placed; nothing was driven"
    assert len(bot._fold_tranches) == 1
    assert bot._scrum_sells_lifetime == 1
    assert bot._tranches_created_lifetime == 1


def test_a_real_manual_fire_in_a_strong_trend_keeps_its_split():
    """Red means the exception does not reach the shipping path."""
    bot = _manual_bot(lots=_lots(9), bull=_STRONG_TREND_MIN_BULL_CANDLES + 1)
    asyncio.run(bot._execute_manual_rebalance(_Ticker(1.0), "manual_button"))
    assert len(bot._fold_tranches) > 1
    assert bot._scrum_sells_lifetime == 1


def test_the_reproduced_build_loop_matches_the_shipping_one():
    """Red means ``_build`` above has drifted from the real loop.

    Every bound test in this file is driven through ``_build``. If it
    stops reproducing what ``tick`` and ``_execute_manual_rebalance``
    write, those tests measure a fixture and not the code.
    """
    lots = _lots(6)
    real = _manual_bot(
        lots=[dict(lot) for lot in lots],
        bull=_STRONG_TREND_MIN_BULL_CANDLES + 1,
    )
    asyncio.run(real._execute_manual_rebalance(_Ticker(1.0), "manual_button"))

    mine = _bot(lots=[dict(lot) for lot in lots])
    # holdings 1000 at $1.00 against a $100 target sells $900 of units.
    _build(mine, 900.0, 900.0, 1.0)

    assert len(real._fold_tranches) == len(mine._fold_tranches)
    for got, want in zip(real._fold_tranches, mine._fold_tranches):
        for key in ("usd", "units", "ref", "initial_buy_price"):
            assert abs(got[key] - want[key]) <= EXACT, key


class _BbResult:
    lower = 0.0
    upper = 0.0


def _tick_bot(*, lots, bull=0, fill=1.0, units=60.0):
    """A bot the real tick sell phases run against.

    ``_execute_sell`` and ``_get_balance`` are stubbed and everything
    from the build loop to ``_bound_new_fold_tranches`` is the shipping
    code.
    """
    bot = _bot(lots=lots, bull=bull)
    bot._quote_to_usd = 1.0
    bot._target_balance = 100.0
    bot._anchor_target_balance = 100.0
    bot._fold_cycle_cap_consumed = 0.0
    bot._fold_queue_usd = 0.0
    bot._fold_queue_ref_price = 0.0
    bot._pending_wire_credits = 0.0
    bot._dist_accumulator = units
    bot._below_min_scrum_log_ts = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._scrum_target_mode = "usd"
    bot._scrum_target_side = None

    async def _sell(_amount, _price, _summary):
        return fill

    async def _balance(_asset):
        return units

    async def _limits(_symbol):
        return 0.0, 0.0, 0.0

    bot._execute_sell = _sell
    bot._get_balance = _balance
    bot._get_market_limits = _limits
    bot._settled_sale_proceeds = lambda amount, price, label: amount * price
    bot._route_scrum_proceeds_via_wires = lambda **_kw: 0.0
    bot._emit_trade_fire_snapshot = lambda *_a, **_kw: None
    bot._emit_voting_panel_snapshot_at_fire = lambda **_kw: None
    bot._emit_gate_decision_at_fire = lambda **_kw: None
    bot._reset_opposing_hysteresis_after_fill = lambda: None
    bot.note_scrum_retention_usd = lambda _usd: None
    return bot


def _scrum_tick(bot, units=60.0, fill=1.0):
    """One ``_tick_bot`` run through the real SCRUM sell phase."""
    asyncio.run(
        bot._tick_execute_scrum(
            _Ticker(fill),
            None,
            _BbResult(),
            units * fill,
            1.0,
            units * fill,
            0.5,
            type("D", (), {"name": "BULLISH"}),
            1.0,
            0.0,
            0.0,
            None,
        )
    )
    return bot


def _dist_tick(bot):
    """One ``_tick_bot`` run through the real DIST re-fold phase."""
    asyncio.run(bot._tick_distribute(_Ticker(1.0), None, _BbResult(), True))
    return bot


def test_the_scrum_sell_phase_leaves_one_tranche():
    """Red means the SCRUM build loop escaped
    ``_bound_new_fold_tranches``."""
    bot = _scrum_tick(_tick_bot(lots=_lots(9)))
    assert bot._main_lots == [], "the sell never walked the lot book"
    assert len(bot._fold_tranches) == 1
    assert bot._tranches_created_lifetime == 1
    assert bot._scrum_sells_lifetime == 1


def test_the_scrum_sell_phase_keeps_its_split_in_a_strong_trend():
    """Red means ``_strong_trend_now`` does not reach the SCRUM path."""
    bot = _scrum_tick(_tick_bot(lots=_lots(9), bull=_STRONG_TREND_MIN_BULL_CANDLES + 1))
    assert len(bot._fold_tranches) > 1
    assert bot._scrum_sells_lifetime == 1


def test_the_dist_refold_phase_leaves_one_tranche():
    """Red means the DIST build loop escaped
    ``_bound_new_fold_tranches``."""
    bot = _dist_tick(_tick_bot(lots=_lots(9)))
    assert bot._main_lots == [], "the sell never walked the lot book"
    assert len(bot._fold_tranches) == 1
    assert bot._tranches_created_lifetime == 1
    assert bot._scrum_sells_lifetime == 1


def test_the_dist_refold_phase_keeps_its_split_in_a_strong_trend():
    """Red means ``_strong_trend_now`` does not reach the DIST path."""
    bot = _dist_tick(_tick_bot(lots=_lots(9), bull=_STRONG_TREND_MIN_BULL_CANDLES + 1))
    assert len(bot._fold_tranches) > 1
    assert bot._scrum_sells_lifetime == 1


def test_the_top_up_opens_no_sell_and_counts_none():
    """NEGATIVE CONTROL. ``_top_up_remnant_fold_tranches`` is not a sell,
    so it must not move ``_scrum_sells_lifetime``."""
    bot = _tick_bot(lots=_lots(9))
    bot._fold_tranches = [
        {
            "usd": 1.0,
            "units": 1.0,
            "ref": 1.0,
            "initial_buy_price": 0.5,
            "created_ts": 1.0,
        }
    ]
    bot._top_up_remnant_fold_tranches(0, 0.0, 0.0)
    assert bot._scrum_sells_lifetime == 0
    assert bot._tranches_created_lifetime == 0


# ── THE COUNTER SURVIVES A ROUND TRIP ────────────────────────────────


def _persisting_bot(**kwargs):
    """A bot the real export and import can both run against.

    The two state methods read scalars that no bound test needs, so
    they are set HERE rather than widening every other fixture.
    """
    bot = _bot(**kwargs)
    bot._target_balance = 100.0
    bot._anchor_target_balance = 100.0
    bot._current_holdings = 1.0
    bot._quote_to_usd = 1.0
    bot._cb_hard_tripped = False
    bot._dist_accumulator = 0.0
    bot._fold_accumulator = 0.0
    bot._fold_cycle_cap_consumed = 0.0
    bot._fold_queue_usd = 0.0
    bot._hedge_bal = 0.0
    bot._hedge_trades = 0
    bot._hyst_armed_fold_side = False
    bot._hyst_armed_scrum_side = False
    bot._hyst_ref_fold_side = 0.0
    bot._hyst_ref_scrum_side = 0.0
    bot._last_trade_price = 0.0
    bot._last_trade_side = None
    bot._pending_wire_credits = 0.0
    bot._standing_surplus_usd = 0.0
    bot._scrum_target_mode = "usd"
    bot._scrum_target_side = None
    return bot


def test_the_sell_counter_persists_and_restores():
    """Red means the rule's denominator is lost on every restart."""
    bot = _persisting_bot(lots=_lots(3), sells=17)
    exported = ScrummingBot.export_scrumming_state(bot)
    assert exported["scrum_sells_lifetime"] == 17

    fresh = _persisting_bot(lots=[], sells=0)
    ScrummingBot.import_scrumming_state(fresh, exported)
    assert fresh._scrum_sells_lifetime == 17


def test_a_state_file_without_the_key_restores_zero_and_invents_nothing():
    """Red means a legacy save fabricates a sell history it never had."""
    fresh = _persisting_bot(lots=[], sells=99)
    ScrummingBot.import_scrumming_state(
        fresh, {"tranches_created_lifetime": 4925, "tranches_closed_lifetime": 4813}
    )
    assert fresh._scrum_sells_lifetime == 0
    assert fresh._tranches_created_lifetime == 4925


def test_clearing_the_lifetime_counters_leaves_the_denominator_alone():
    """Red means a clear can make the rule read as violated.

    ``clear_lifetime_tranche_counters`` zeroes ``created``. Zeroing the
    sell count with it would leave ``created <= scrums`` true only
    until the next sell; zeroing ``created`` alone keeps it true
    immediately and for ever after.
    """
    bot = _bot(lots=[], created=4925, sells=440)
    bot._tranches_closed_lifetime = 4813
    bot._tranches_discarded_lifetime = 91
    bot._tranches_malformed_dropped = 0
    bot._tranches_counters_reset_ts = 0.0

    bot.clear_lifetime_tranche_counters(reason="test")

    assert bot._tranches_created_lifetime == 0
    assert bot._scrum_sells_lifetime == 440
    assert bot._tranches_created_lifetime <= bot._scrum_sells_lifetime
