"""``scrum_fold_pct`` scales a sale the same way on every selling path.

``_apply_scrum_fold_pct`` holds the fold-ratio arithmetic and
``GOLDEN_PRE_CHANGE`` pins its outputs to the bit. ``PATHS`` fires the
real SCRUM, DIST and manual sells and compares each tranche book with
``_reference_for_the_same_sale``. Every ``_check_*`` helper runs twice,
once on the shipping code and once against a wrong arithmetic that must
turn it red.
"""

from __future__ import annotations

import asyncio

import pytest

from src.trading.scrumming_bot import ScrummingBot

# Money is compared to the bit; a tolerance would hide the drift.
EXACT = 0.0

# name -> (scrum_usd, scrum_asset, tranche_count_before, tranches,
#          {fold_pct: ((usd, units), ...)})
GOLDEN_PRE_CHANGE = {
    # One lot, no wire credit. The plain case.
    "plain_single": (
        100.0,
        10.0,
        0,
        lambda: [{"usd": 100.0, "units": 10.0, "ref": 10.0, "initial_buy_price": 8.0}],
        {
            0: ((0.0, 0.0),),
            1: ((1.0, 0.1),),
            25: ((25.0, 2.5),),
            37: ((37.0, 3.7),),
            50: ((50.0, 5.0),),
            66: ((66.0, 6.6000000000000005),),
            99: ((99.0, 9.9),),
            100: ((100.0, 10.0),),
        },
    ),
    # Two lots from one sale; each carries its own initial_buy_price.
    "two_lots": (
        100.0,
        10.0,
        0,
        lambda: [
            {"usd": 60.0, "units": 6.0, "ref": 10.0, "initial_buy_price": 12.0},
            {"usd": 40.0, "units": 4.0, "ref": 10.0, "initial_buy_price": 8.0},
        ],
        {
            0: ((0.0, 0.0), (0.0, 0.0)),
            1: ((0.6, 0.06), (0.4, 0.04)),
            25: ((15.0, 1.5), (10.0, 1.0)),
            37: ((22.2, 2.2199999999999998), (14.8, 1.48)),
            50: ((30.0, 3.0), (20.0, 2.0)),
            66: ((39.6, 3.96), (26.400000000000002, 2.64)),
            99: ((59.4, 5.9399999999999995), (39.6, 3.96)),
            100: ((60.0, 6.0), (40.0, 4.0)),
        },
    ),
    # The $343.68 of wire credit survives every percentage untouched;
    # only the $100 of scrum proceeds scales.
    "absorbed_wire": (
        100.0,
        10.0,
        0,
        lambda: [{"usd": 443.68, "units": 10.0, "ref": 10.0, "initial_buy_price": 8.0}],
        {
            0: ((343.68, 0.0),),
            1: ((344.68, 0.1),),
            25: ((368.68, 2.5),),
            37: ((380.68, 3.7),),
            50: ((393.68, 5.0),),
            66: ((409.68, 6.6000000000000005),),
            99: ((442.68, 9.9),),
            100: ((443.68, 10.0),),
        },
    ),
    # No usable rate. The fallback treats everything as scrum proceeds.
    "no_rate": (
        50.0,
        0.0,
        0,
        lambda: [{"usd": 50.0, "units": 0.0, "ref": 0.0, "initial_buy_price": 5.0}],
        {
            0: ((0.0, 0.0),),
            1: ((0.5, 0.0),),
            25: ((12.5, 0.0),),
            37: ((18.5, 0.0),),
            50: ((25.0, 0.0),),
            66: ((33.0, 0.0),),
            99: ((49.5, 0.0),),
            100: ((50.0, 0.0),),
        },
    ),
    # A tranche from an EARLIER sale is outside the slice.
    "older_tranche_present": (
        100.0,
        10.0,
        1,
        lambda: [
            {"usd": 999.0, "units": 99.0, "ref": 3.0, "initial_buy_price": 3.0},
            {"usd": 100.0, "units": 10.0, "ref": 10.0, "initial_buy_price": 8.0},
        ],
        {
            0: ((999.0, 99.0), (0.0, 0.0)),
            1: ((999.0, 99.0), (1.0, 0.1)),
            25: ((999.0, 99.0), (25.0, 2.5)),
            37: ((999.0, 99.0), (37.0, 3.7)),
            50: ((999.0, 99.0), (50.0, 5.0)),
            66: ((999.0, 99.0), (66.0, 6.6000000000000005)),
            99: ((999.0, 99.0), (99.0, 9.9)),
            100: ((999.0, 99.0), (100.0, 10.0)),
        },
    ),
    # The 3.55e-15 at 0% is float noise the reference arithmetic produces.
    "ragged_lots": (
        37.77,
        3.3333,
        0,
        lambda: [
            {
                "usd": (0.9805 / 3.3333) * 37.77,
                "units": 0.9805,
                "ref": 11.331,
                "initial_buy_price": 13.7,
            },
            {
                "usd": (2.3528 / 3.3333) * 37.77,
                "units": 2.3528,
                "ref": 11.331,
                "initial_buy_price": 9.02,
            },
        ],
        {
            0: ((0.0, 0.0), (3.552713678800501e-15, 0.0)),
            1: (
                (0.11110156601566017, 0.009805000000000001),
                (0.2665984339843434, 0.023527999999999997),
            ),
            25: ((2.777539150391504, 0.245125), (6.6649608496085, 0.5882)),
            37: (
                (4.110757942579426, 0.362785),
                (9.864142057420578, 0.8705359999999999),
            ),
            50: ((5.555078300783008, 0.49025), (13.329921699216996, 1.1764)),
            66: (
                (7.332703357033571, 0.6471300000000001),
                (17.595496642966435, 1.552848),
            ),
            99: (
                (10.999055035550356, 0.970695),
                (26.39324496444965, 2.3292719999999996),
            ),
            100: ((11.110156601566016, 0.9805), (26.65984339843399, 2.3528)),
        },
    ),
}


# ── stubs ────────────────────────────────────────────────────────────


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")


class _Config:
    def __init__(self, fold_pct=100, symbol="BONK/USD", target="BONK"):
        self.scrum_fold_pct = fold_pct
        self.symbol = symbol
        self.target_asset = target
        self.max_target_growth_pct = 1.0
        self.profit_folding_active = True
        self.trading_fee_pct = 1.6
        self.manual_fire_dust_band = 0.0


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0


def _bare_bot(fold_pct, tranches):
    """The least bot ``_apply_scrum_fold_pct`` needs to run."""
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "test-bot"
    bot._bus = _Bus()
    bot._fold_tranches = tranches
    bot.config = _Config(fold_pct)
    return bot


# ── the wrong arithmetics, for the controls ──────────────────────────
# Each one drives a _check_* helper that must go red on it.


def _ignores_the_setting(bot, before, usd, asset):
    """Queue the whole sale whatever ``scrum_fold_pct`` says."""
    return None


def _scales_wired_money(bot, before, usd, asset):
    """Scale a tranche's summed USD, wired-in credit included."""
    _frac = max(0, min(100, int(bot.config.scrum_fold_pct))) / 100.0
    if _frac >= 1.0:
        return None
    for _t in bot._fold_tranches[before:]:
        _t["usd"] = _t["usd"] * _frac
        _t["units"] = _t["units"] * _frac
    return None


def _leaves_units_unscaled(bot, before, usd, asset):
    """Scale the dollars and leave the units at their full quantity."""
    _frac = max(0, min(100, int(bot.config.scrum_fold_pct))) / 100.0
    if _frac >= 1.0:
        return None
    _rate = (usd / asset) if asset > 0 else 0.0
    for _t in bot._fold_tranches[before:]:
        _scrummed = (
            min(max(_t["units"] * _rate, 0.0), _t["usd"]) if asset > 0 else _t["usd"]
        )
        _t["usd"] = (_t["usd"] - _scrummed) + _scrummed * _frac
    return None


def _rescales_older_tranches(bot, before, usd, asset):
    """Scale every queued tranche, not only the ones this sale opened."""
    return ScrummingBot._apply_scrum_fold_pct(bot, 0, usd, asset)


def _runs_the_gate_at_one_hundred(bot, before, usd, asset):
    """Scale even at 100, where the setting must be inert."""
    _frac = max(0, min(100, int(bot.config.scrum_fold_pct))) / 100.0
    _rate = (usd / asset) if asset > 0 else 0.0
    _queued = 0.0
    for _t in bot._fold_tranches[before:]:
        _scrummed = (
            min(max(_t["units"] * _rate, 0.0), _t["usd"]) if asset > 0 else _t["usd"]
        )
        _t["usd"] = (_t["usd"] - _scrummed) + _scrummed * _frac
        _t["units"] = _t["units"] * _frac
        _queued += _t["usd"]
    bot._bus.emit("bot.log", bot_id=bot.bot_id, message=f"FOLD RATIO: {_queued}")
    return None


# ── check 1: the arithmetic is the pre-change arithmetic ─────────────


def _check_goldens(apply_fold) -> None:
    """Every recorded pre-change output must be reproduced exactly.

    ``apply_fold(bot, count_before, scrum_usd, scrum_asset)`` runs the
    thing under test, and the tranche dict is where the money is read.
    """
    for name, (usd, asset, before, factory, table) in GOLDEN_PRE_CHANGE.items():
        for pct, expected in table.items():
            tranches = factory()
            bot = _bare_bot(pct, tranches)
            apply_fold(bot, before, usd, asset)
            got = tuple((t["usd"], t["units"]) for t in tranches)
            if len(got) != len(expected):
                raise AssertionError(
                    f"{name} at {pct}%: tranche count changed, "
                    f"{len(expected)} -> {len(got)}"
                )
            for index, (want, have) in enumerate(zip(expected, got)):
                if abs(want[0] - have[0]) > EXACT:
                    raise AssertionError(
                        f"{name} at {pct}%, tranche {index}: usd was "
                        f"{want[0]!r} before the change and is {have[0]!r} "
                        f"now"
                    )
                if abs(want[1] - have[1]) > EXACT:
                    raise AssertionError(
                        f"{name} at {pct}%, tranche {index}: units were "
                        f"{want[1]!r} before the change and are {have[1]!r} "
                        f"now"
                    )


def _apply_via_method(bot, before, usd, asset):
    bot._apply_scrum_fold_pct(before, usd, asset)


def test_the_shipping_method_reproduces_the_pre_change_numbers():
    """The fold-ratio arithmetic is unchanged, read at the tranche."""
    _check_goldens(_apply_via_method)


@pytest.mark.parametrize(
    "wrong, label",
    [
        (_ignores_the_setting, "queue everything regardless of the setting"),
        (_scales_wired_money, "scale wired-in money too"),
        (_leaves_units_unscaled, "leave units unscaled"),
        (_rescales_older_tranches, "re-scale earlier sales' tranches"),
    ],
)
def test_control_the_goldens_catch_a_wrong_arithmetic(wrong, label):
    """CONTROL. Each wrong arithmetic must turn the golden check red."""
    with pytest.raises(AssertionError) as caught:
        _check_goldens(wrong)
    assert str(caught.value).strip(), (
        f"the wrong arithmetic '{label}' failed without saying what "
        f"changed; a control that cannot be read is not evidence"
    )


# ── the three real selling paths ─────────────────────────────────────


class _Order:
    id = "order-1"
    filled = 0.0
    average = 0.0
    side = "sell"
    fee = 0.0
    fee_currency = ""


class _Ticker:
    def __init__(self, last):
        self.last = last


class _BB:
    lower = 0.0
    upper = 0.0


DEFAULT_LOTS = (
    {"units": 600.0, "initial_buy_price": 0.9},
    {"units": 600.0, "initial_buy_price": 0.7},
)
SALE_UNITS = 900.0
SALE_PRICE = 1.0


def _path_bot(fold_pct, *, lots, price=SALE_PRICE, wire_out=0.0, bull_candles=0):
    """A bot that can run any of the three real selling paths.

    Only the outward edges are stubbed -- the exchange, the wire
    routing, the emitters; everything between the sell and the tranche
    list is the shipping code.
    """
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "path-bot"
    bot.seen = {"routed": [], "fold_calls": []}
    bot._bus = _Bus()
    bot.config = _Config(fold_pct)
    bot.stats = _Stats()
    bot._fold_tranches = []
    bot._main_lots = [dict(lot) for lot in lots]
    bot._quote_to_usd = 1.0
    bot._last_sell_venue_fee = None
    bot._tranches_created_lifetime = 0
    bot._tranches_discarded_lifetime = 0
    bot._tranches_closed_lifetime = 0
    bot._scrum_sells_lifetime = 0
    bot._last_trend_bull_candles = bull_candles
    bot._fold_queue_usd = 0.0
    bot._fold_queue_ref_price = 0.0
    bot._fold_cycle_cap_consumed = 0.0
    bot._pending_wire_credits = 0.0
    bot._standing_surplus_usd = 0.0
    bot._below_min_scrum_log_ts = 0.0
    bot._scrum_target_mode = "search"
    bot._scrum_target_side = None
    bot._dist_accumulator = 0.0
    bot._manual_fire_pending = True
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = _BB()
    bot._current_holdings = sum(float(lot["units"]) for lot in lots)
    bot._target_balance = 0.0
    bot._anchor_target_balance = 0.0

    def _route(scrum_usd, sell_fill, label):
        bot.seen["routed"].append((scrum_usd, sell_fill, label))
        return wire_out

    bot._route_scrum_proceeds_via_wires = _route
    bot._emit_trade_fire_snapshot = _record(bot, "fire_snapshots")
    bot._emit_voting_panel_snapshot_at_fire = _record(bot, "snapshots")
    bot._emit_gate_decision_at_fire = _record(bot, "gates")
    bot._reset_opposing_hysteresis_after_fill = _record(bot, "disarms")
    bot.note_scrum_retention_usd = _record(bot, "retained")
    bot._emit_trade_notification = _record(bot, "notifications")

    async def _limits(symbol):
        bot.seen.setdefault("limits", []).append(symbol)
        return 0.0, 0.0, 0.0

    async def _sell(amount, price_arg, summary):
        bot.seen.setdefault("sold", []).append((amount, price_arg, summary))
        return price

    async def _balance(currency):
        bot.seen.setdefault("balances", []).append(currency)
        _held = bot._current_holdings
        return type("B", (), {"total": _held, "free": _held, "absent": False})()

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.seen["placed"] = kwargs
        return _Order()

    async def _settled(order, symbol, requested, tick_price):
        bot.seen["settled"] = (order.id, symbol, requested, tick_price)
        return requested, price, True

    bot._get_market_limits = _limits
    bot._execute_sell = _sell
    bot._get_balance = _balance
    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled

    _real_apply = bot._apply_scrum_fold_pct

    def _spy(before, usd, asset):
        bot.seen["fold_calls"].append((before, usd, asset))
        return _real_apply(before, usd, asset)

    bot._apply_scrum_fold_pct = _spy
    return bot


def _record(bot, key):
    def _inner(*args, **kwargs):
        bot.seen.setdefault(key, []).append((args, kwargs))

    return _inner


def _fire_scrum(bot, sale_units, price=SALE_PRICE):
    asyncio.run(
        bot._tick_execute_scrum(
            _Ticker(price),
            None,
            _BB(),
            -sale_units * price,
            -1.0,
            0.0,
            0.5,
            type("D", (), {"name": "BEARISH"})(),
            0.9,
            0.5,
            0.0,
            None,
        )
    )


def _fire_dist(bot, sale_units, price=SALE_PRICE):
    bot._dist_accumulator = sale_units
    asyncio.run(bot._tick_distribute(_Ticker(price), None, _BB(), True))


def _fire_manual(bot, sale_units, price=SALE_PRICE):
    bot._current_holdings = sale_units
    bot._target_balance = 0.0
    bot._anchor_target_balance = 0.0
    asyncio.run(bot._execute_manual_rebalance(_Ticker(price), "manual_button"))


PATHS = {"DIST": _fire_dist, "MANUAL": _fire_manual, "SCRUM": _fire_scrum}
PATH_NAMES = sorted(PATHS)
FOLD_PCTS = [0, 1, 25, 50, 66, 99, 100]


def _book(bot):
    return [(t["usd"], t["units"]) for t in bot._fold_tranches]


def _reference_for_the_same_sale(fold_pct, sale_usd, sale_units, lots):
    """What the shared helpers leave, for the same sale.

    Runs the same highest-``initial_buy_price``-first split, then
    ``_bound_new_fold_tranches`` and ``_apply_scrum_fold_pct`` in the
    order every selling path calls them.
    """
    lots = [dict(lot) for lot in lots]
    lots.sort(key=lambda lot: lot["initial_buy_price"], reverse=True)
    tranches = []
    remaining = sale_units
    for lot in list(lots):
        if remaining <= 1e-12:
            break
        take = min(lot["units"], remaining)
        if take <= 1e-12:
            continue
        tranches.append(
            {
                "usd": (take / sale_units) * sale_usd,
                "units": take,
                "ref": sale_usd / sale_units,
                "initial_buy_price": lot["initial_buy_price"],
            }
        )
        remaining -= take
    bot = _bare_bot(fold_pct, tranches)
    bot._bound_new_fold_tranches(0)
    bot._apply_scrum_fold_pct(0, sale_usd, sale_units)
    # `_bound_new_fold_tranches` rebinds `_fold_tranches`, so the list
    # handed in goes stale the moment it merges.
    return [(t["usd"], t["units"]) for t in bot._fold_tranches]


def _check_path_matches_the_reference(path, fold_pct, *, scaled=True) -> None:
    """Read at the tranche list after a real sell on ``path``."""
    lots = [dict(lot) for lot in DEFAULT_LOTS]
    bot = _path_bot(fold_pct, lots=lots)
    if not scaled:
        bot._apply_scrum_fold_pct = lambda before, usd, asset: bot.seen.setdefault(
            "skipped", []
        ).append((before, usd, asset))
    PATHS[path](bot, SALE_UNITS)
    got = _book(bot)
    want = _reference_for_the_same_sale(
        fold_pct, SALE_UNITS * SALE_PRICE, SALE_UNITS, lots
    )
    if len(got) != len(want):
        raise AssertionError(
            f"{path} left {len(got)} tranche(s) at scrum_fold_pct="
            f"{fold_pct}, the shared helpers leave {len(want)}: "
            f"{got} vs {want}"
        )
    for index, (have, expect) in enumerate(zip(got, want)):
        if abs(have[0] - expect[0]) > EXACT:
            raise AssertionError(
                f"{path} tranche {index}: queued ${have[0]!r} but the "
                f"shared helpers queue ${expect[0]!r} at scrum_fold_pct="
                f"{fold_pct}"
            )
        if abs(have[1] - expect[1]) > EXACT:
            raise AssertionError(
                f"{path} tranche {index}: queued {have[1]!r} units, the "
                f"shared helpers queue {expect[1]!r}"
            )


@pytest.mark.parametrize("path", PATH_NAMES)
@pytest.mark.parametrize("fold_pct", FOLD_PCTS)
def test_every_selling_path_scales_the_sale_the_same_way(path, fold_pct):
    """The mirroring claim, read at the book after a real sell."""
    _check_path_matches_the_reference(path, fold_pct)


@pytest.mark.parametrize("path", PATH_NAMES)
@pytest.mark.parametrize("fold_pct", [0, 1, 25, 50, 66, 99])
def test_control_a_path_that_never_scales_is_caught(path, fold_pct):
    """CONTROL. With the setting not reaching the tranches the check
    must go red on every path."""
    with pytest.raises(AssertionError):
        _check_path_matches_the_reference(path, fold_pct, scaled=False)


@pytest.mark.parametrize("path", PATH_NAMES)
def test_every_selling_path_hands_the_helper_its_own_sale_figures(path):
    """The USD and units passed are the ones the sale was priced at."""
    bot = _path_bot(50, lots=[dict(lot) for lot in DEFAULT_LOTS])
    PATHS[path](bot, SALE_UNITS)
    assert bot.seen["fold_calls"] == [(0, SALE_UNITS * SALE_PRICE, SALE_UNITS)], (
        f"{path} called the fold-ratio helper with "
        f"{bot.seen['fold_calls']}; expected one call carrying this "
        f"sale's own ${SALE_UNITS * SALE_PRICE} over {SALE_UNITS} units"
    )


@pytest.mark.parametrize("path", PATH_NAMES)
def test_every_selling_path_queues_half_a_sale_at_fifty(path):
    """The plainest reading of the setting, on each real path."""
    bot = _path_bot(50, lots=[dict(lot) for lot in DEFAULT_LOTS])
    PATHS[path](bot, SALE_UNITS)
    total = sum(usd for usd, _ in _book(bot))
    assert abs(total - 450.0) <= 1e-9, (
        f"{path} queued ${total:.4f} of a $900 sale at "
        f"scrum_fold_pct=50; expected $450.00"
    )


@pytest.mark.parametrize("path", PATH_NAMES)
def test_every_selling_path_queues_the_whole_sale_at_one_hundred(path):
    """29 of the operator's 37 bots run at 100; nothing may be retired."""
    bot = _path_bot(100, lots=[dict(lot) for lot in DEFAULT_LOTS])
    PATHS[path](bot, SALE_UNITS)
    book = _book(bot)
    total = sum(usd for usd, _ in book)
    assert abs(total - 900.0) <= 1e-9, (
        f"{path} queued ${total:.4f} of a $900 sale at " f"scrum_fold_pct=100"
    )
    assert sum(units for _, units in book) == pytest.approx(900.0)
    assert not [
        m for m in bot._bus.messages if "FOLD RATIO" in m
    ], f"{path} emitted a FOLD RATIO line at 100, where the setting is inert"


@pytest.mark.parametrize("path", PATH_NAMES)
def test_the_operator_is_told_what_happened_on_every_path(path):
    """The FOLD RATIO line is the only signal that the setting acted."""
    bot = _path_bot(50, lots=[dict(lot) for lot in DEFAULT_LOTS])
    PATHS[path](bot, SALE_UNITS)
    ratio_lines = [m for m in bot._bus.messages if "FOLD RATIO" in m]
    assert len(ratio_lines) == 1, (
        f"expected one FOLD RATIO line after a {path} sell at 50%, got "
        f"{ratio_lines}"
    )
    assert "scrum_fold_pct=50%" in ratio_lines[0]


@pytest.mark.parametrize("intent", ["wire_stack", "max_cartridge"])
def test_the_autonomous_callers_of_the_manual_method_scale_too(intent):
    """Wire Stack and Max Cartridge run the manual method without the
    operator, so the gap was never "manual only"."""
    bot = _path_bot(50, lots=[dict(lot) for lot in DEFAULT_LOTS])
    bot._current_holdings = SALE_UNITS
    asyncio.run(bot._execute_manual_rebalance(_Ticker(SALE_PRICE), intent))
    book = _book(bot)
    assert book, f"{intent} built no tranche; the fire did not reach the build"
    total = sum(usd for usd, _ in book)
    assert abs(total - 450.0) <= 1e-9, (
        f"{intent} queued ${total:.4f} of a $900 sale at "
        f"scrum_fold_pct=50; expected $450.00"
    )


# ── a lot holding no units is not a tranche ──────────────────────────

EMPTY_LOT_LOTS = (
    {"units": 300.0, "initial_buy_price": 9.0},
    {"units": 0.0, "initial_buy_price": 5.0},
    {"units": 300.0, "initial_buy_price": 0.9},
)


@pytest.mark.parametrize("path", PATH_NAMES)
def test_a_lot_holding_no_units_opens_no_tranche(path):
    """A ``_main_lots`` entry with no units must leave no record."""
    bot = _path_bot(50, lots=[dict(lot) for lot in EMPTY_LOT_LOTS])
    PATHS[path](bot, 600.0)
    book = _book(bot)
    assert len(book) == 1, (
        f"{path} left {len(book)} tranche(s) for one sell over two "
        f"lots and one empty lot: {book}. The empty lot opened a "
        f"record and defeated the one-tranche-per-sell bound."
    )
    assert book[0][0] == pytest.approx(300.0), (
        f"{path} queued ${book[0][0]:.4f} of a $600 sale at "
        f"scrum_fold_pct=50; expected $300.00"
    )


@pytest.mark.parametrize("path", PATH_NAMES)
def test_a_lot_holding_no_units_does_not_raise_the_created_counter(path):
    """``created - closed - discarded == standing`` must still hold."""
    bot = _path_bot(50, lots=[dict(lot) for lot in EMPTY_LOT_LOTS])
    PATHS[path](bot, 600.0)
    assert bot._tranches_created_lifetime == len(bot._fold_tranches), (
        f"{path} counted {bot._tranches_created_lifetime} tranche(s) "
        f"created against {len(bot._fold_tranches)} standing"
    )


@pytest.mark.parametrize("path", PATH_NAMES)
def test_a_sale_over_only_empty_lots_leaves_an_empty_book(path):
    """Every lot holding no units must leave no record and not raise."""
    lots = [
        {"units": 0.0, "initial_buy_price": 9.0},
        {"units": 0.0, "initial_buy_price": 5.0},
    ]
    bot = _path_bot(50, lots=lots)
    bot._current_holdings = 600.0
    PATHS[path](bot, 600.0)
    assert _book(bot) == [], f"{path} queued {_book(bot)} over lots holding no units"
    assert bot._tranches_created_lifetime == 0, (
        f"{path} counted {bot._tranches_created_lifetime} tranche(s) "
        f"created and left none standing"
    )


@pytest.mark.parametrize("path", PATH_NAMES)
def test_control_the_empty_lot_check_sees_a_real_lot(path):
    """CONTROL. Give the empty lot units and the same sell keeps two
    per-lot records under the strong-trend exception, so the check
    above is reading the book and not a constant."""
    lots = [dict(lot) for lot in EMPTY_LOT_LOTS]
    lots[1]["units"] = 300.0
    bot = _path_bot(50, lots=lots, bull_candles=20)
    PATHS[path](bot, 600.0)
    assert len(_book(bot)) == 2, (
        f"{path} left {_book(bot)}; a strong trend keeps one record per "
        f"lot consumed and this sell consumed two"
    )


@pytest.mark.parametrize("path", PATH_NAMES)
def test_a_strong_trend_keeps_the_real_lots_and_drops_the_empty_one(path):
    """The bound-lifted branch must not keep an empty record either."""
    bot = _path_bot(100, lots=[dict(lot) for lot in EMPTY_LOT_LOTS], bull_candles=20)
    PATHS[path](bot, 600.0)
    book = _book(bot)
    assert len(book) == 2, (
        f"{path} left {book} under a strong trend; the two lots holding "
        f"units are the only records this sell opened"
    )
    assert all(units > 0 for _, units in book), f"{path} kept an empty record: {book}"


# ── at 100 nothing changes ───────────────────────────────────────────


def _check_hundred_is_a_no_op(apply_fold) -> None:
    """A bot at 100 -- 29 of the operator's 37 -- must see no change."""
    for name, (usd, asset, before, factory, _table) in GOLDEN_PRE_CHANGE.items():
        tranches = factory()
        untouched = [(t["usd"], t["units"]) for t in tranches]
        bot = _bare_bot(100, tranches)
        apply_fold(bot, before, usd, asset)
        got = [(t["usd"], t["units"]) for t in tranches]
        if got != untouched:
            raise AssertionError(
                f"{name}: scrum_fold_pct=100 changed the tranches from "
                f"{untouched} to {got}"
            )
        if bot._bus.messages:
            raise AssertionError(
                f"{name}: scrum_fold_pct=100 emitted {bot._bus.messages}; "
                f"the default must be silent as well as inert"
            )


def test_a_bot_at_one_hundred_percent_sees_no_change():
    _check_hundred_is_a_no_op(_apply_via_method)


def test_control_the_hundred_percent_check_catches_a_wrong_arithmetic():
    """CONTROL. An arithmetic that runs at 100 must turn it red."""
    with pytest.raises(AssertionError):
        _check_hundred_is_a_no_op(_runs_the_gate_at_one_hundred)


# ── wired-in money is exempt, told apart by units ────────────────────


def _check_wire_credit_survives(apply_fold) -> None:
    """Money another bot earned is not the operator's to retire here.

    A tranche's wired-in share is whatever it holds above its units at
    the sale's own rate, and that pool must come out whole at every
    percentage.
    """
    parked = 343.68
    for pct in range(0, 100):
        tranches = [
            {
                "usd": 100.0 + parked,
                "units": 10.0,
                "ref": 10.0,
                "initial_buy_price": 8.0,
            }
        ]
        bot = _bare_bot(pct, tranches)
        apply_fold(bot, 0, 100.0, 10.0)
        kept = tranches[0]["usd"]
        expected = parked + 100.0 * (pct / 100.0)
        if abs(kept - expected) > 1e-9:
            raise AssertionError(
                f"at scrum_fold_pct={pct} the tranche holds ${kept:.6f}; "
                f"${parked:.2f} of wired-in money plus ${100.0 * pct / 100:.6f} "
                f"of scrum proceeds is ${expected:.6f}. "
                f"${expected - kept:.6f} of another bot's money was "
                f"retired as cash."
            )


def test_wired_in_money_is_still_exempt():
    """Swept over the whole 0..99 domain, not a hand-written table."""
    _check_wire_credit_survives(_apply_via_method)


def test_control_the_wire_check_catches_a_scaled_wire_credit():
    """CONTROL. Scale the summed usd and the check must go red."""
    with pytest.raises(AssertionError):
        _check_wire_credit_survives(_scales_wired_money)


@pytest.mark.parametrize("path", PATH_NAMES)
def test_a_wire_credit_on_a_new_tranche_survives_every_path(path):
    """Dollars added without units are recognised as wired in."""
    parked = 40.0
    bot = _path_bot(50, lots=[dict(lot) for lot in DEFAULT_LOTS])
    _real_apply = bot._apply_scrum_fold_pct

    def _absorb_then_apply(before, usd, asset):
        bot._fold_tranches[before]["usd"] += parked
        return _real_apply(before, usd, asset)

    bot._apply_scrum_fold_pct = _absorb_then_apply
    PATHS[path](bot, SALE_UNITS)
    total = sum(usd for usd, _ in _book(bot))
    assert abs(total - (450.0 + parked)) <= 1e-9, (
        f"a $900 {path} sale at 50% with ${parked:.2f} of wired-in money "
        f"left ${total:.4f} queued; expected ${450.0 + parked:.2f}. The "
        f"wired-in money was scaled."
    )


# ── terminal actions leave no tranche ────────────────────────────────


def _seeded(bot):
    bot._fold_tranches = [
        {"usd": 100.0, "units": 10.0, "ref": 10.0, "initial_buy_price": 8.0},
        {"usd": 50.0, "units": 5.0, "ref": 10.0, "initial_buy_price": 7.0},
    ]
    bot._fold_queue_usd = 150.0
    return bot


def test_a_detonation_leaves_no_fold_tranche():
    """Detonation is terminal: it queues nothing and clears the book."""
    bot = _seeded(_path_bot(50, lots=[dict(lot) for lot in DEFAULT_LOTS]))
    bot._current_holdings = 900.0
    bot._anchor_target_balance = 100.0
    asyncio.run(bot._execute_detonation(_Ticker(SALE_PRICE)))
    assert bot._fold_tranches == [], (
        f"detonation left {bot._fold_tranches}; the operator's rule is "
        f"that a terminal action neither spawns nor populates tranches"
    )


def test_control_the_detonation_check_sees_a_book_that_survives():
    """CONTROL. A detonation refused for want of a price leaves the two
    seeded tranches, so the emptiness above is a real outcome."""
    bot = _seeded(_path_bot(50, lots=[dict(lot) for lot in DEFAULT_LOTS]))
    bot._current_holdings = 900.0
    bot._anchor_target_balance = 100.0
    asyncio.run(bot._execute_detonation(_Ticker(0.0)))
    assert len(bot._fold_tranches) == 2, (
        f"the seeded book did not survive a refused detonation: "
        f"{bot._fold_tranches}"
    )


def test_a_self_destruct_leaves_no_fold_tranche():
    """Self-destruct is terminal and empties the book as well."""
    bot = _seeded(_path_bot(50, lots=[dict(lot) for lot in DEFAULT_LOTS]))
    bot._current_holdings = 0.0

    async def _no_units(currency):
        bot.seen.setdefault("balances", []).append(currency)
        return type("B", (), {"total": 0.0, "free": 0.0, "absent": False})()

    bot._get_balance = _no_units
    asyncio.run(bot.self_destruct("SELF-DESTRUCT"))
    assert bot._fold_tranches == [], (
        f"self-destruct left {bot._fold_tranches}; a terminal action "
        f"neither spawns nor populates tranches"
    )


def test_control_the_self_destruct_check_sees_a_book_that_survives():
    """CONTROL. A refused self-destruct leaves the two seeded tranches."""
    bot = _seeded(_path_bot(50, lots=[dict(lot) for lot in DEFAULT_LOTS]))
    asyncio.run(bot.self_destruct("wrong-token"))
    assert len(bot._fold_tranches) == 2, (
        f"the seeded book did not survive a refused self-destruct: "
        f"{bot._fold_tranches}"
    )
