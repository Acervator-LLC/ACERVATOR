"""The order amount reaching the venue is a finite positive number.

WHAT A FAILURE HERE MEANS, stated before the tests are read.

``BotContainer.guarded_place_order`` is the only route to a live
exchange from the trading engine. Two dispatch paths leave it, the
VolumeGuard call and the direct ``exchange.place_order`` call, and both
forward the caller's ``amount`` object unchanged.

If ``test_no_unusable_shape_reaches_the_venue`` fails, a value that is
not a finite positive number reached a recorder standing where the
exchange stands. On the operator's machine that recorder is Coinbase
and the money is real.

If ``test_a_real_amount_still_reaches_the_venue`` fails, the gate is
too tight and refuses legitimate orders. That is the opposite fault and
is just as serious: 37 live bots would stop trading.

If either below-minimum test fails, the gate altered the pre-existing
size behaviour instead of sitting in front of it. Those two read the
refusal REASON, not just the refusal, so a gate that swallowed the size
check would fail them even though the order was still refused.

THE MEASURED DEFECT THIS PINS. Before the gate existed, this same table
was driven against the unmodified file and 119 of 160 drives reached a
recorder, including NaN, +inf, ``True``, ``"5.0"``, ``Decimal("NaN")``,
a float subclass holding NaN and every numpy scalar. The red side of
this control is that measurement, not a mutation invented to make the
test go red.

NaN is reachable in production: when ``standing_surplus_usd`` cannot be
read the fold preview returns NaN, and that value is an addend in
``buy_usd_target``.

Nothing here touches ~/.acervator or any network. The recorders record.
"""

from __future__ import annotations

from decimal import Decimal
from enum import IntEnum
from fractions import Fraction

import pytest

from src.exchange.base import Order, OrderSide, OrderStatus, OrderType
from src.trading.bot_container import BotContainer

SYMBOL = "RAVE/USD"

# `(min_amount, min_cost, amount_precision)` as `_get_market_limits` returns
# them. NOMETA is the fail-open fallback when the metadata is absent.
REGIMES = {
    "LIMITS": (0.001, 0.0, 8),
    "NOMETA": (0.0, 0.0, 8),
}

REFUSED_BY_THE_GATE = "PRE-FLIGHT REJECTED"
REFUSED_BY_THE_SIZE_CHECK = "is below"


class _FloatSub(float):
    """A float subclass. isinstance admits it; an exact type test does not."""


class _IntSub(int):
    """An int subclass, admitted by isinstance for the same reason."""


class _Colour(IntEnum):
    FIVE = 5


class _FloatsToNan:
    """Answers NaN to float(), which is how a duck-typed size arrives."""

    def __float__(self) -> float:
        return float("nan")


class _FloatsToFive:
    """Answers a usable number to float() but is not itself a number."""

    def __float__(self) -> float:
        return 5.0


class _HasIndex:
    """Integer-like by protocol only."""

    def __index__(self) -> int:
        return 5


UNUSABLE = [
    ("nan", float("nan")),
    ("+inf", float("inf")),
    ("-inf", float("-inf")),
    ("zero", 0.0),
    ("negative-zero", -0.0),
    ("negative float", -3.0),
    ("int zero", 0),
    ("int negative", -5),
    ("True", True),
    ("False", False),
    ("str number", "5.0"),
    ("str nan", "nan"),
    ("bytes", b"5.0"),
    ("bytearray", bytearray(b"5.0")),
    ("None", None),
    ("list", [5.0]),
    ("Decimal number", Decimal("5.0")),
    ("Decimal NaN", Decimal("NaN")),
    ("Decimal Infinity", Decimal("Infinity")),
    ("Fraction", Fraction(5, 1)),
    ("float subclass", _FloatSub(5.0)),
    ("float subclass nan", _FloatSub(float("nan"))),
    ("int subclass", _IntSub(5)),
    ("IntEnum member", _Colour.FIVE),
    ("__float__ to nan", _FloatsToNan()),
    ("__float__ to number", _FloatsToFive()),
    ("__index__ to number", _HasIndex()),
    ("int too large for a float", 10**400),
    ("complex", complex(5, 0)),
]

try:
    import numpy
except ImportError:  # pragma: no cover
    numpy = None
else:
    UNUSABLE += [
        ("numpy float64", numpy.float64(5.0)),
        ("numpy float64 nan", numpy.float64("nan")),
        ("numpy float32", numpy.float32(5.0)),
        ("numpy int64", numpy.int64(5)),
    ]


class _Report:
    """The shape VolumeGuard.execute returns, with nothing executed."""

    success = True
    reason = ""
    requested_amount = 0.0
    executed_amount = 0.0
    avg_fill_price = 0.0


class _Recorder:
    """Stands where the venue stands. Records the call; sends nothing.

    One object serves as both the exchange and the VolumeGuard so a
    single ``calls`` list answers "did anything reach a venue at all",
    whichever dispatch path the method chose.
    """

    enabled = True

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def place_order(
        self, symbol, side, order_type, amount, price=None, client_order_id=None
    ):
        self.calls.append(
            {
                "path": "exchange.place_order",
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "amount": repr(amount),
                "price": price,
                "client_order_id": client_order_id,
            }
        )
        return Order(
            id="rec",
            symbol=symbol,
            side=side,
            type=order_type,
            amount=0.0,
            price=0.0,
            filled=0.0,
            remaining=0.0,
            average=0.0,
            status=OrderStatus.CLOSED,
            timestamp=0.0,
        )

    async def execute(
        self, symbol, side, amount, price=0, order_type="market", exchange=None
    ):
        self.calls.append(
            {
                "path": "volume_guard.execute",
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "amount": repr(amount),
                "price": price,
                "exchange": type(exchange).__name__,
            }
        )
        return _Report()

    async def get_markets(self):
        raise AssertionError("the limits cache is pre-seeded; no lookup")


def _bot(regime: str, guarded: bool):
    """A container holding exactly what guarded_place_order reads.

    ``__init__`` is bypassed: the real constructor wants a BotConfig and
    reaches the global event bus, and this method touches neither. The
    positive-control test proves the object really does reach the venue,
    so a REFUSED verdict elsewhere cannot be an artefact of the fixture.
    """
    bot = BotContainer.__new__(BotContainer)
    bot.bot_id = "u6test"
    venue = _Recorder()
    bot.exchange = venue
    bot._volume_guard = venue if guarded else None
    bot._market_limits_cache = {SYMBOL: REGIMES[regime]}
    return bot, venue


async def _place(bot, amount):
    """Drive the real method. Each caller states what should happen."""
    await bot.guarded_place_order(SYMBOL, OrderSide.BUY, OrderType.MARKET, amount, None)


@pytest.mark.parametrize("regime", sorted(REGIMES))
@pytest.mark.parametrize("guarded", [False, True])
@pytest.mark.parametrize("label,amount", UNUSABLE, ids=[row[0] for row in UNUSABLE])
async def test_no_unusable_shape_reaches_the_venue(label, amount, regime, guarded):
    """No value outside the domain reaches either dispatch path."""
    bot, venue = _bot(regime, guarded)
    with pytest.raises(Exception, match=REFUSED_BY_THE_GATE):
        await _place(bot, amount)
    assert venue.calls == [], (
        f"{label} reached the venue under {regime} "
        f"(guard={'on' if guarded else 'off'}): {venue.calls}. "
        f"An amount that is not a finite positive number was handed to "
        f"the exchange."
    )


@pytest.mark.parametrize("regime", sorted(REGIMES))
@pytest.mark.parametrize("guarded", [False, True])
@pytest.mark.parametrize("amount", [5.0, 5])
async def test_a_real_amount_still_reaches_the_venue(amount, regime, guarded):
    """POSITIVE CONTROL. A legitimate size must still be sent.

    Without this the test above is satisfied by a gate that refuses
    everything, which would stop all trading.
    """
    bot, venue = _bot(regime, guarded)
    await _place(bot, amount)
    assert len(venue.calls) == 1, (
        f"a legitimate amount {amount!r} was REFUSED under {regime} "
        f"(guard={'on' if guarded else 'off'}). The gate is too tight "
        f"and live bots would stop trading."
    )


async def test_below_minimum_is_refused_by_the_size_check_not_the_gate():
    """0.0005 is legitimate but below the 0.001 exchange minimum.

    The refusal must still name the minimum. If the gate refused it
    instead, the message would say "not a finite positive number" and
    this test would fail, which is the point: the gate must precede the
    size check, not replace it.
    """
    bot, venue = _bot("LIMITS", guarded=False)
    with pytest.raises(Exception, match=REFUSED_BY_THE_SIZE_CHECK):
        await _place(bot, 0.0005)
    assert venue.calls == []


async def test_below_minimum_is_sent_when_no_minimum_is_known():
    """With no metadata the method fails open, and still must.

    A legitimate small size is sent when the exchange minimum is
    unknown. The gate does not change that; it only refuses values that
    are not numbers at all.
    """
    bot, venue = _bot("NOMETA", guarded=False)
    await _place(bot, 0.0005)
    assert len(venue.calls) == 1


async def test_the_refusal_names_the_side_symbol_repr_and_type():
    """The refusal has to be diagnosable from the message alone."""
    bot, _venue = _bot("LIMITS", guarded=False)
    with pytest.raises(Exception, match=REFUSED_BY_THE_GATE) as caught:
        await _place(bot, float("nan"))
    message = str(caught.value)
    assert "BUY" in message
    assert SYMBOL in message
    assert "nan" in message
    assert "float" in message
