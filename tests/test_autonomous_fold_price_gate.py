"""An autonomous fold must not rebuy above the price it sold at.

``_execute_manual_rebalance`` is reached by three callers, two of which
fire with no operator present -- Wire Stack and Max Cartridge, via
``caller_intent="wire_stack"`` and ``"max_cartridge"``. On that path the
operator gates are bypassed by design, and nothing compared the rebuy
price against the price a tranche was sold at.

The autonomous tick fold-back already owns the rule as a per-tranche
filter whose arithmetic lives in ``src/trading/otd_math.py``::

    eligible  <=>  ticker.last <= ref * fold_rebuy_factor(interval, fee)

The gate asks ``otd_math`` the same question at this second site and
REFUSES the whole fire when not one queued tranche is eligible. The
order is placed before the discharge loop runs, so refusing is the only
way to withhold the trade rather than merely relocate the bought units.
When some tranches are eligible the fire proceeds unchanged.

Three things stay as they were: the operator's own button
(``manual_button``), which bypasses the gate; the SCRUM side of the same
method, which sells; and a fold on an empty ladder, where no ``ref``
exists to measure a distance against.

Every test here constructs a real ``ScrummingBot`` and runs the real
method. Only the outward edges are stubbed -- the exchange, the
emitters, the settled-fill read; the discharge loop and fold-growth
code are the shipping code.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from src.trading.otd_math import fold_rebuy_factor
from src.trading.scrumming_bot import ScrummingBot

AUTONOMOUS = ("wire_stack", "max_cartridge")
EVERY_INTENT = ("manual_button", "wire_stack", "max_cartridge")


# ── the least bot that can run the real method ───────────────────────


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.events: list[tuple] = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")
        if "data" in payload:
            self.events.append((topic, payload["data"]))


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_folded_usd = 0.0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0


class _Config:
    def __init__(self, *, symbol="CHIP/USD", interval=1.0, fee=0.6):
        self.symbol = symbol
        self.target_asset = symbol.split("/")[0]
        self.exchange_id = "coinbase"
        self.scrumming_interval_pct = interval
        self.trading_fee_pct = fee
        self.max_target_growth_pct = 1.0
        self.profit_folding_active = True
        self.scrum_fold_pct = 100


class _Order:
    id = "order-u3"
    filled = 0.0
    average = 0.0


class _Ticker:
    def __init__(self, last):
        self.last = last


def _bot(
    *,
    tranches,
    holdings,
    target,
    price,
    symbol="CHIP/USD",
    interval=1.0,
    fee=0.6,
    quote_free=1_000_000.0,
    qrate=1.0,
    fill_price=None,
):
    """A ``ScrummingBot`` that runs the real ``_execute_manual_rebalance``.

    Only the outward edges are stubbed: the exchange, the emitters, the
    settled-fill read. ``_preview_fold_growth``,
    ``_apply_fold_target_growth``, ``reset_swos_cycle`` and the whole
    discharge loop are the shipping code.
    """
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "u3-bot"
    bot.seen = {"placed": None, "settled": None, "balances": []}
    bot._bus = _Bus()
    bot.config = _Config(symbol=symbol, interval=interval, fee=fee)
    bot.stats = _Stats()
    bot._fold_tranches = [dict(t) for t in tranches]
    bot._main_lots = [{"units": holdings, "initial_buy_price": price}]
    bot._current_holdings = holdings
    bot._target_balance = target
    bot._anchor_target_balance = target
    bot._quote_to_usd = qrate
    bot._manual_fire_pending = True
    bot._fold_queue_usd = sum(float(t.get("usd", 0.0)) for t in tranches)
    bot._fold_cycle_cap_consumed = 0.0
    bot._standing_surplus_usd = 0.0
    bot._retained_this_cycle_usd = 0.0
    bot._fold_accumulator = 0.0
    bot._target_grow_last_side = None
    bot._tranches_closed_lifetime = 0
    bot._tranches_created_lifetime = 0
    bot._pending_wire_credits = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = None

    settled_price = price if fill_price is None else fill_price

    async def _refresh():
        return qrate

    async def _place(**kwargs):
        bot.seen["placed"] = dict(kwargs)
        return _Order()

    async def _settled(order, symbol_, requested, tick_price):
        bot.seen["settled"] = (order.id, symbol_, requested, tick_price)
        return requested, settled_price, True

    async def _balance(currency):
        bot.seen["balances"].append(currency)
        if currency == bot.config.target_asset:
            free = holdings
        else:
            free = quote_free
        return type("B", (), {"total": free, "free": free, "absent": False})()

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._emit_voting_panel_snapshot_at_fire = lambda **kw: bot.seen.setdefault(
        "snapshots", []
    ).append(kw)
    bot._emit_gate_decision_at_fire = lambda **kw: bot.seen.setdefault(
        "gates", []
    ).append(kw)
    bot._reset_opposing_hysteresis_after_fill = lambda: bot.seen.setdefault(
        "disarms", []
    ).append(True)
    bot._route_scrum_proceeds_via_wires = lambda scrum_usd, sell_fill, label: (
        bot.seen.setdefault("routed", []).append((scrum_usd, sell_fill, label)) or 0.0
    )
    bot.note_scrum_retention_usd = lambda retained_usd: bot.seen.setdefault(
        "retained", []
    ).append(retained_usd)
    return bot


def _fire(bot, price, intent):
    asyncio.run(bot._execute_manual_rebalance(_Ticker(price), intent))
    return bot


def _observable(bot):
    """Everything a caller of this method can see it having done."""
    return {
        "placed": bot.seen["placed"],
        "settled": bot.seen["settled"],
        "balances": bot.seen["balances"],
        "tranches": [
            (t.get("usd"), t.get("units"), t.get("ref")) for t in bot._fold_tranches
        ],
        "lots": [
            (
                lot.get("units"),
                lot.get("initial_buy_price"),
                lot.get("operator_initiated"),
            )
            for lot in bot._main_lots
        ],
        "holdings": bot._current_holdings,
        "target": bot._target_balance,
        "queue_usd": bot._fold_queue_usd,
        "closed_lifetime": bot._tranches_closed_lifetime,
        "trades": bot.stats.total_trades,
        "folded_usd": bot.stats.total_folded_usd,
        "last_side": bot._last_trade_side,
        "last_price": bot._last_trade_price,
        "messages": bot._bus.messages,
        "events": bot._bus.events,
    }


def _refusal(bot):
    """The refusal lines this gate emits, and only those."""
    return [
        m
        for m in bot._bus.messages
        if "AUTONOMOUS FIRE REFUSED (opposing distance" in m
    ]


def _refusal_free(observable):
    return not [
        m
        for m in observable["messages"]
        if "AUTONOMOUS FIRE REFUSED (opposing distance" in m
    ]


# ── scenario vocabulary ──────────────────────────────────────────────
#
# A ladder is built from the refs alone; ``usd`` and ``units`` follow
# from them so the numbers are self-consistent.


def _ladder(*refs, units=100.0):
    return [
        {"usd": ref * units, "units": units, "ref": ref, "initial_buy_price": ref * 0.8}
        for ref in refs
    ]


def _tick_factor(interval=1.0, fee=0.6):
    """The rebuy factor the autonomous tick path computes for this config.

    Reproduces its coercion, ``or``-fallbacks included: a configured fee
    of 0.0 is falsy and becomes 0.6, matching the tick path exactly.
    """
    return fold_rebuy_factor(interval or 0, fee or 0.6)


def _threshold(ref, interval=1.0, fee=0.6):
    """The highest price at which ``ref`` alone is still eligible."""
    return ref * _tick_factor(interval, fee)


def _admits(ladder, interval=1.0, fee=0.6):
    """The highest price at which ANY tranche in ``ladder`` is eligible.

    The dearest ref sets it; a cheap tranche is the strictest.
    """
    return max(
        _threshold(float(t.get("ref", 0.0) or 0.0), interval, fee) for t in ladder
    )


def _one_float_above(ladder, interval=1.0, fee=0.6):
    """The cheapest price at which the whole ladder is refused."""
    return math.nextafter(_admits(ladder, interval, fee), math.inf)


def _ladder_units(bot):
    return sum(float(t.get("units", 0.0) or 0.0) for t in bot._fold_tranches)


# ── the gate refuses when no tranche is eligible ─────────────────────


@pytest.mark.parametrize("intent", AUTONOMOUS)
def test_an_autonomous_fold_is_refused_when_no_tranche_is_eligible(intent):
    """The gate bites: an autonomous rebuy above every ref is withheld."""
    ladder = _ladder(1.00, 0.99, 0.98)
    price = _one_float_above(ladder)
    bot = _fire(
        _bot(tranches=ladder, holdings=50.0, target=100.0, price=price),
        price,
        intent,
    )

    assert bot.seen["placed"] is None, (
        f"an order was placed at ${price:.8f} although the most "
        f"permissive tranche only allows ${_admits(ladder):.8f}"
    )
    assert len(_refusal(bot)) == 1, bot._bus.messages
    assert bot._fold_tranches == [
        dict(t) for t in ladder
    ], "the ladder was disturbed by a fire that never happened"
    assert bot._current_holdings == 50.0
    assert bot.stats.total_trades == 0


def test_the_refusal_names_the_price_the_ladder_and_the_money():
    """The operator must be able to check a refusal against his ladder."""
    ladder = _ladder(2.00, 1.50)
    price = _admits(ladder) * 1.05
    bot = _fire(
        _bot(tranches=ladder, holdings=10.0, target=100.0, price=price),
        price,
        "max_cartridge",
    )
    line = _refusal(bot)[0]
    for fragment in (
        f"${price:.8f}",
        "2 queued tranche(s)",
        f"${_admits(ladder):.8f}",
        "withheld",
    ):
        assert fragment in line, f"{fragment!r} missing from {line!r}"


# ── every fold that should fire, still fires ─────────────────────────

IN_SPEC = [
    (
        "a deep drop, whole ladder eligible",
        dict(
            tranches=_ladder(1.00, 0.99, 0.98), holdings=50.0, target=100.0, price=0.50
        ),
    ),
    (
        "exactly on the threshold of the cheapest ref",
        dict(
            tranches=_ladder(1.00, 0.99, 0.98),
            holdings=50.0,
            target=100.0,
            price=_threshold(0.98),
        ),
    ),
    (
        "exactly on the threshold of the dearest ref",
        dict(
            tranches=_ladder(2.00, 0.10),
            holdings=10.0,
            target=100.0,
            price=_threshold(2.00),
        ),
    ),
    (
        "fifty tranches, the dearest eligible and the cheapest not",
        dict(
            tranches=_ladder(*([1.00] * 49 + [0.20])),
            holdings=50.0,
            target=100.0,
            price=_threshold(1.00),
        ),
    ),
    (
        "a wide interval, so the distance demanded is larger",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.80,
            interval=15.0,
        ),
    ),
    (
        "a zero fee, which the tick path's own idiom turns into 0.6",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=_threshold(1.00, interval=2.0, fee=0.0),
            interval=2.0,
            fee=0.0,
        ),
    ),
    (
        "a crypto-quoted pair, where delta routes via the quote rate",
        dict(
            tranches=_ladder(0.002),
            holdings=1000.0,
            target=100.0,
            price=0.001,
            qrate=50.0,
            symbol="IMU/BTC",
        ),
    ),
    (
        "an empty ladder, which has no ref to measure against",
        dict(tranches=[], holdings=50.0, target=100.0, price=0.50),
    ),
    (
        "a zero ref and a negative ref sit beside a good one",
        dict(
            tranches=(
                _ladder(1.00)
                + [
                    {"usd": 0.0, "units": 5.0, "ref": 0.0},
                    {"usd": 0.0, "units": 5.0, "ref": -1.0},
                ]
            ),
            holdings=50.0,
            target=100.0,
            price=0.50,
        ),
    ),
    (
        "the buy is clipped by a thin wallet",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            quote_free=3.0,
        ),
    ),
    (
        "the fill lands below the tick price",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            fill_price=0.45,
        ),
    ),
]


@pytest.mark.parametrize("intent", EVERY_INTENT)
@pytest.mark.parametrize("label, scenario", IN_SPEC, ids=[row[0] for row in IN_SPEC])
def test_an_in_spec_fold_still_fires(intent, label, scenario):
    """An in-spec fold reaches the order and is never refused.

    Too strict is the dangerous direction: a withheld in-spec fold leaves
    the position off centre, the deficit unshrunk, and the ladder
    stranded with money queued and no path to spend it.
    """
    bot = _fire(_bot(**scenario), scenario["price"], intent)
    obs = _observable(bot)
    assert bot.seen["placed"] is not None, f"{label} / {intent}: the fold did not fire"
    assert _refusal_free(obs), f"{label} / {intent}: an in-spec fold was refused"


def test_a_partly_eligible_ladder_still_fires():
    """Some eligible means the fire proceeds. The gate refuses only when
    NONE is eligible, not when some are."""
    ladder = _ladder(5.00, 0.10)
    price = _threshold(5.00)
    assert price > _threshold(0.10), "this row is not partly eligible"
    bot = _fire(
        _bot(tranches=ladder, holdings=10.0, target=100.0, price=price),
        price,
        "max_cartridge",
    )
    assert bot.seen["placed"] is not None
    assert _refusal(bot) == []


# ── the operator's own button is untouched ───────────────────────────


REFUSED_IF_AUTONOMOUS = [
    (
        "no tranche is eligible",
        dict(tranches=_ladder(1.00), holdings=50.0, target=100.0, price=0.999),
    ),
    (
        "the interval cannot be read",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            interval="abc",
        ),
    ),
    (
        "the fee cannot be read",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            fee=object(),
        ),
    ),
]


@pytest.mark.parametrize(
    "label, scenario",
    REFUSED_IF_AUTONOMOUS,
    ids=[row[0] for row in REFUSED_IF_AUTONOMOUS],
)
def test_the_operator_button_is_never_refused(label, scenario):
    """Operator sovereignty: a scenario an autonomous caller is refused
    still trades when pressed by the operator, and is never gated."""
    bot = _fire(_bot(**scenario), scenario["price"], "manual_button")
    assert bot.seen["placed"] is not None, f"{label}: the operator's fire was withheld"
    assert _refusal_free(_observable(bot)), f"{label}: the gate captured the override"


@pytest.mark.parametrize(
    "label, scenario",
    REFUSED_IF_AUTONOMOUS,
    ids=[row[0] for row in REFUSED_IF_AUTONOMOUS],
)
@pytest.mark.parametrize("intent", AUTONOMOUS)
def test_the_same_scenario_is_refused_for_an_autonomous_caller(label, scenario, intent):
    """The mirror of the sovereignty test: the same scenarios ARE refused
    on the autonomous path, so the manual pass above means an exemption."""
    bot = _fire(_bot(**scenario), scenario["price"], intent)
    assert bot.seen["placed"] is None, f"{label}: {intent} was not refused"
    assert len(_refusal(bot)) == 1


# ── the SCRUM side of the same method sells, and still does ──────────


@pytest.mark.parametrize("intent", EVERY_INTENT)
def test_the_scrum_side_still_sells(intent):
    """The gate lives in the FOLD branch only: a scrum still sells and is
    never refused, whatever the caller intent."""
    scenario = dict(
        tranches=_ladder(1.00, 0.99), holdings=1000.0, target=100.0, price=1.0
    )
    bot = _fire(_bot(**scenario), 1.0, intent)
    obs = _observable(bot)
    assert obs["placed"] is not None, f"{intent}: the scrum did not fire"
    assert obs["placed"]["side"].value == "sell", f"{intent}: this row is not a scrum"
    assert _refusal_free(obs), f"{intent}: the refusal leaked onto the sell side"


# ── the value domain, because floats are in the accepted set ─────────


@pytest.mark.parametrize("intent", AUTONOMOUS)
def test_a_nan_price_refuses(intent):
    """Fail closed on NaN: the validity check admits it, and the gate's
    empty-eligible-set refuses the fire before an order is placed."""
    bot = _fire(
        _bot(tranches=_ladder(1.00), holdings=50.0, target=100.0, price=1.0),
        float("nan"),
        intent,
    )
    assert bot.seen["placed"] is None
    assert len(_refusal(bot)) == 1


@pytest.mark.parametrize("intent", AUTONOMOUS)
@pytest.mark.parametrize("price", [float("-inf"), 0.0, -0.0, -1.0])
def test_a_price_the_validity_check_rejects_is_still_rejected(intent, price):
    """These four never reach the gate: the validity check at the top of
    the method returns first, naming "no valid price"."""
    bot = _fire(
        _bot(tranches=_ladder(1.00), holdings=50.0, target=100.0, price=1.0),
        price,
        intent,
    )
    assert bot.seen["placed"] is None
    assert _refusal(bot) == [], (
        "this price reached the gate; it used to be rejected before the "
        "method got that far"
    )
    assert any("no valid price" in m for m in bot._bus.messages)


BAD_CONFIG = [
    ("a non-numeric interval", dict(interval="abc")),
    ("a non-numeric fee", dict(fee="wide")),
    ("an interval that is not a number at all", dict(interval=object())),
    ("a list where a fee should be", dict(fee=[1, 2])),
]


@pytest.mark.parametrize("intent", AUTONOMOUS)
@pytest.mark.parametrize(
    "label, override", BAD_CONFIG, ids=[row[0] for row in BAD_CONFIG]
)
def test_an_unreadable_distance_refuses(intent, label, override):
    """Fail closed on a config whose distance cannot be computed, rather
    than inherit the tick path's silent fallback to no gate at all."""
    bot = _fire(
        _bot(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            **override,
        ),
        0.50,
        intent,
    )
    assert bot.seen["placed"] is None, f"{label} traded"
    assert any(
        "opposing distance unreadable" in m for m in bot._bus.messages
    ), bot._bus.messages


REF_EDGE = [
    ("ref of zero", 0.0),
    ("ref missing entirely", None),
    ("a negative ref", -1.0),
]


@pytest.mark.parametrize("intent", AUTONOMOUS)
@pytest.mark.parametrize("label, ref", REF_EDGE, ids=[row[0] for row in REF_EDGE])
def test_a_ladder_of_only_malformed_refs_refuses(intent, label, ref):
    """A ref that cannot be traded against is not a licence to trade."""
    tranche = {"usd": 1.0, "units": 5.0}
    if ref is not None:
        tranche["ref"] = ref
    bot = _fire(
        _bot(tranches=[tranche], holdings=50.0, target=100.0, price=0.50),
        0.50,
        intent,
    )
    assert bot.seen["placed"] is None, f"{label} traded"
    assert len(_refusal(bot)) == 1


def test_the_threshold_boundary_is_inclusive_and_one_float_above_refuses():
    """The boundary is exactly ``otd_math``'s: a price ON the threshold
    trades (the rule is ``<=``), one float above it is refused."""
    ref, interval, fee = 1.0, 1.0, 0.6
    edge = ref * fold_rebuy_factor(interval, fee)
    assert not math.isnan(edge)

    at = _fire(
        _bot(tranches=_ladder(ref), holdings=50.0, target=100.0, price=edge),
        edge,
        "wire_stack",
    )
    assert (
        at.seen["placed"] is not None
    ), "a price exactly ON the threshold was refused; the rule is <="

    above = math.nextafter(edge, math.inf)
    over = _fire(
        _bot(tranches=_ladder(ref), holdings=50.0, target=100.0, price=above),
        above,
        "wire_stack",
    )
    assert (
        over.seen["placed"] is None
    ), "one float above the threshold was still admitted"


@pytest.mark.parametrize(
    "interval, fee",
    [
        (1.0, 0.6),
        (2.0, 0.0),
        (0.0, 0.6),
        (15.0, 0.6),
        (60.0, 0.6),
    ],
)
def test_the_gate_agrees_with_the_tick_path_on_every_config(interval, fee):
    """One rule, two sites: the boundary this gate enforces is the
    boundary the autonomous tick fold-back enforces for the same config,
    including a falsy 0.0 fee and a clamped 60 interval."""
    ref = 1.0
    edge = ref * _tick_factor(interval, fee)
    at = _fire(
        _bot(
            tranches=_ladder(ref),
            holdings=1.0,
            target=100.0,
            price=edge,
            interval=interval,
            fee=fee,
        ),
        edge,
        "max_cartridge",
    )
    assert at.seen["placed"] is not None, (
        f"interval={interval} fee={fee}: the tick path's own boundary "
        f"price ${edge:.8f} was refused here"
    )

    above = math.nextafter(edge, math.inf)
    over = _fire(
        _bot(
            tranches=_ladder(ref),
            holdings=1.0,
            target=100.0,
            price=above,
            interval=interval,
            fee=fee,
        ),
        above,
        "max_cartridge",
    )
    assert over.seen["placed"] is None, (
        f"interval={interval} fee={fee}: one float past the tick path's "
        f"boundary was admitted here"
    )
