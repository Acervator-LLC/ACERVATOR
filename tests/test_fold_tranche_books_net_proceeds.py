"""A fold tranche is worth what the VENUE credited, not the notional.

THE OPERATOR'S RULE, issue #133 unit 9b, 2026-08-26
===================================================
    "If an Exchange provides a value, you are not allowed to
     synthesize it. This is why understanding each API's capability
     and data is so important."

THE DEFECT
==========
Three loops in ``scrumming_bot.py`` build fold tranches -- the
autonomous SCRUM sell in ``tick``, the DIST re-fold sell in ``tick``,
and ``_execute_manual_rebalance``, which serves Manual Fire, Wire Stack
and Max Cartridge. All three valued the sale at ``units x fill_price``.
That is the GROSS notional. A venue credits the NET: it keeps its fee
out of the proceeds.

THE NUMBERS, EACH WITH ITS PROVENANCE
=====================================
Bot ``c8e5c5db``, 2026-08-26 21:50:57, 473 CHIP at $0.03376:

* **$15.96848 gross -- LOGGED.** ``~/.acervator_logs/trade/trade.log``
  and ``trade/pnl/daily/2026-08-26.ndjson`` both record it, and neither
  carries a fee field at all.
* **1.2% -- THE VENUE'S OWN RATE.** Coinbase's CSV export of CHIP fills
  shows 92 of 92 August 2026 fills at exactly 1.2000% of subtotal, on
  both sides.
* **$15.77686 net -- INFERRED from those two.** The export ends
  2026-08-20, so the amount actually credited for THIS trade is
  recorded nowhere. It is not claimed as measured, here or in the
  source.

The bot's configured ``trading_fee_pct`` is 1.6, which gives $15.71298
and does not match the venue's rate. That gap is the whole reason the
fee must be carried from the venue and never computed: a synthesised
fee books a number the exchange never charged, which is the same class
of defect as the one being fixed.

WHAT REACHES THE BOT FROM COINBASE, AND WHAT DOES NOT
=====================================================
Established from ``ccxt/coinbase.py``, not from a live call.
``create_order`` returns ``parse_order(response["success_response"])``,
and that body carries four keys -- ``order_id``, ``product_id``,
``side``, ``client_order_id``. No ``total_fees``, so ``fee.cost``
parses to ``None`` and ``Order.fee`` is 0.0 on every just-placed
Coinbase order. ``fetch_order`` is a DIFFERENT endpoint whose body does
carry ``total_fees``; whether Coinbase has settled a non-zero value
into it seconds after a market fill is UNOBSERVED and is not assumed.

So on live Coinbase the SCRUM and DIST paths book the gross and say so
every time, because they read the placed order and never re-read it.
That is the specified no-fee behaviour. The manual paths re-read
through ``_settled_fill`` and are the only ones a Coinbase fee can
currently reach. Both readings are pinned below.

WHAT CARRIES THE FEE
====================
``Order.fee`` / ``Order.fee_currency`` are filled by the connector's
``_parse_order`` from the venue's own ``fee.cost`` / ``fee.currency``
(``src/exchange/ccxt_connector.py``). Two places hold a settled
order and both now record it:

* ``_execute_sell`` -- the only point SCRUM and DIST ever see an order;
* ``_settled_fill`` -- the manual paths, recording from whichever order
  object the accepted fill came from, which is the RE-READ order when a
  re-read is what settled.

``_settled_sale_proceeds`` consumes the record ONCE and returns the net.

WHAT EACH FAILURE HERE MEANS
============================
Every test states it in one line. The four that matter most:

* THE RED PROOF going green on $15.96848 means a loop books gross again;
* THE VACUOUS-PASS CONTROL going red means the path books zero, which
  also never books gross and would satisfy a "not gross" assertion
  while destroying the number;
* THE SYNTHESIS CONTROL going red means a path started deriving the fee
  from ``trading_fee_pct`` instead of reading the venue's;
* THE NO-FEE CONTROL going red means the code stopped booking gross, and
  stopped saying so, when the venue reported nothing -- so it is
  guessing.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import sys
import textwrap
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.base import OrderSide  # noqa: E402
from src.exchange.ccxt_connector import CCXTConnector  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot, SettledSellFee  # noqa: E402

# A recorded venue fill, quoted rather than recomputed from the code
# under test.
UNITS = 473.0
PRICE = 0.03376
VENUE_FEE = 0.19162
GROSS = 15.96848
NET = 15.77686

# The configured rate, deliberately 1.6% against the venue's 1.2%.
CONFIG_FEE_PCT = 1.6
SYNTHESISED = 15.71298

# Money is compared to five decimals, the reconciliation's precision.
PLACES = 5


def _round(value: float) -> float:
    return round(float(value), PLACES)


# ── STUBS ────────────────────────────────────────────────────────────


class _Bus:
    def __init__(self):
        self.messages = []

    def emit(self, event, **kwargs):
        self.messages.append((event, kwargs))


class _Config:
    def __init__(self, **overrides):
        self.symbol = "CHIP/USD"
        self.target_asset = "CHIP"
        self.scrumming_interval_pct = 1.0
        self.trading_fee_pct = CONFIG_FEE_PCT
        self.stack_mode = False
        self.position_ceiling_enabled = False
        self.max_target_growth_pct = 1.0
        for key, value in overrides.items():
            setattr(self, key, value)


class _Stats:
    def __init__(self):
        self.verify_samples = 0
        self.verify_clean = 0
        self.verify_adjusted = 0
        self.verify_canceled = 0
        self.total_sells = 0
        self.total_buys = 0
        self.total_trades = 0
        self.trade_volume = 0.0
        self.last_trade_time = 0.0


class _Order:
    """A settled order in the shape the connector builds one."""

    def __init__(
        self,
        *,
        price,
        fee=0.0,
        currency="USD",
        side=OrderSide.SELL,
        filled=0.0,
        order_id="stub-order",
    ):
        self.id = order_id
        self.side = side
        self.average = price
        self.price = price
        self.filled = filled
        self.fee = fee
        self.fee_currency = currency


class _Exchange:
    """Returns nothing open, and whatever order the test parks on it."""

    def __init__(self, fetched=None):
        self.fetched = fetched
        self.get_order_calls = 0

    async def get_open_orders(self, symbol):
        return []

    async def get_order(self, order_id, symbol):
        self.get_order_calls += 1
        return self.fetched


class _Summary:
    consensus_direction = "sell"
    consensus_confidence = 0.75


class _StubBot:
    """Minimum surface to run the REAL fee plumbing to completion.

    The four methods under test are bound off ``ScrummingBot`` itself,
    so the shipping code runs. Everything else is a permissive stub, in
    the pattern ``tests/test_ytd_per_trade_increment.py`` already uses
    to drive ``_execute_sell``.
    """

    def __init__(self, *, order=None, fetched=None, **config_overrides):
        self.bot_id = "net-proceeds-stub"
        self.config = _Config(**config_overrides)
        self.stats = _Stats()
        self._bus = _Bus()
        self.exchange = _Exchange(fetched=fetched)
        self._order = order
        self._quote_to_usd = 1.0
        self._current_holdings = 100000.0
        self._target_balance = 100000.0
        self._anchor_target_balance = 100000.0
        self._fold_tranches = []
        self._main_lots = []
        self._initialised = True
        self._invisible = True
        self._hyst_armed_scrum_side = False
        self._hyst_ref_scrum_side = 0.0
        self._hyst_armed_fold_side = False
        self._hyst_ref_fold_side = 0.0
        self._memorised_trades = []
        self._last_sell_venue_fee = None
        self.placed_orders = []
        self.notifications = []
        self.reconciles = []
        for name in (
            "_record_venue_fee",
            "_take_venue_fee",
            "_venue_quote_currency",
            "_settled_sale_proceeds",
        ):
            setattr(self, name, types.MethodType(getattr(ScrummingBot, name), self))
        self._settled_fill_label = ScrummingBot._settled_fill_label

    def _crr(self):
        return None

    def _emit_trade_notification(self, kind, state, detail):
        # Recorded rather than discarded: a stub that drops what it was
        # told cannot be asserted against.
        self.notifications.append((kind, state, detail))

    async def _reconcile_holdings(self, reason=""):
        self.reconciles.append(reason)
        return None

    async def guarded_place_order(self, symbol, side, order_type, amount, price):
        self.placed_orders.append(
            {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "amount": amount,
                "price": price,
            }
        )
        return self._order

    def log(self):
        return [kwargs.get("message", "") for _, kwargs in self._bus.messages]


def _sell(bot, amount, price):
    return asyncio.run(
        ScrummingBot._execute_sell(
            bot, amount=amount, price=price, summary=_Summary(), bypass_stack=True
        )
    )


def _settled(bot, order, requested, quoted):
    return asyncio.run(
        ScrummingBot._settled_fill(bot, order, bot.config.symbol, requested, quoted)
    )


def _proceeds(bot, units=UNITS, price=PRICE, label="SCRUM"):
    return bot._settled_sale_proceeds(units, price, label=label)


# ── THE RED PROOF ────────────────────────────────────────────────────


def test_a_settled_sale_books_what_the_venue_credited():
    """Red means a fold loop values a sale at the gross notional again.

    This is the operator's measured trade, driven through the REAL
    ``_execute_sell`` so the carry is proved rather than assumed.
    """
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))

    fill = _sell(bot, UNITS, PRICE)
    assert fill == pytest.approx(PRICE), "the fill price must not move"

    booked = _proceeds(bot)

    # THE VACUOUS-PASS CONTROL. A path that books zero also never books
    # gross, so the exact value is asserted BEFORE the inequality.
    assert booked > 0.0, "a settled sale that books nothing is not a fix"
    assert _round(booked) == NET

    # THE RED PROOF.
    assert _round(booked) != GROSS, (
        f"booked ${booked:.5f}; the gross notional ${GROSS:.5f} is what "
        f"the venue did NOT credit"
    )
    assert _round(GROSS - booked) == _round(VENUE_FEE)


def test_the_gross_is_the_number_this_unit_refuses():
    """Red means the fixtures stopped describing the measured trade.

    Without this the red proof above could pass because GROSS and NET
    were never different numbers in the first place.
    """
    assert _round(UNITS * PRICE) == GROSS
    assert _round(GROSS - VENUE_FEE) == NET
    assert GROSS != NET


# ── THE SYNTHESIS CONTROL ────────────────────────────────────────────


def test_the_venue_fee_wins_over_the_configured_rate():
    """Red means a path derives the fee from ``trading_fee_pct``.

    The config is deliberately wrong: 1.6% against the venue's 1.2%.
    The venue's number must be the one booked.
    """
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    assert bot.config.trading_fee_pct == CONFIG_FEE_PCT

    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)

    assert _round(booked) == NET
    assert _round(booked) != SYNTHESISED, (
        f"booked ${booked:.5f}, which is the CONFIGURED "
        f"{CONFIG_FEE_PCT}% and not the venue's fee"
    )


@pytest.mark.parametrize("venue_fee", [0.05, 0.19162, 0.4, 1.25])
def test_any_fee_the_venue_reports_is_the_one_booked(venue_fee):
    """Red means the booked fee stopped tracking the venue's number.

    A single fixture cannot tell "reads the venue" from "happens to
    agree with the venue on one trade". Four unrelated rates can.
    """
    bot = _StubBot(order=_Order(price=PRICE, fee=venue_fee))
    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)
    assert _round(booked) == _round(UNITS * PRICE - venue_fee)


def _code_without_the_docstring(func) -> str:
    """The method's executable body, with its prose removed.

    The docstrings NAME ``trading_fee_pct`` in order to say the code
    must never read it. Matching on raw source would flag the very
    sentence that forbids the thing.
    """
    node = ast.parse(textwrap.dedent(inspect.getsource(func))).body[0]
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return "\n".join(ast.unparse(stmt) for stmt in body)


def test_the_fee_plumbing_never_reads_the_configured_rate():
    """Red means ``trading_fee_pct`` entered the fee path."""
    checked = 0
    for name in (
        "_record_venue_fee",
        "_take_venue_fee",
        "_venue_quote_currency",
        "_settled_sale_proceeds",
    ):
        code = _code_without_the_docstring(getattr(ScrummingBot, name))
        assert code.strip(), f"{name} has no body left to check"
        checked += 1
        assert "trading_fee_pct" not in code, (
            f"{name} reads the configured rate; the venue's fee is the "
            f"only permitted source"
        )
    assert checked == 4


def test_the_configured_rate_check_can_see_a_read_at_all():
    """Red means the check above is blind and its pass means nothing."""
    code = _code_without_the_docstring(ScrummingBot._execute_sell)
    assert "trading_fee_pct" in code, (
        "_execute_sell reads the configured rate for its hysteresis "
        "band; a checker that cannot see it there cannot see it anywhere"
    )


# ── THE NO-FEE CONTROL ───────────────────────────────────────────────


def test_no_reported_fee_books_the_gross_and_says_so():
    """Red means the code guesses when the venue reports nothing."""
    bot = _StubBot(order=_Order(price=PRICE, fee=0.0))

    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)

    assert _round(booked) == GROSS
    assert any("BOOKED GROSS" in line for line in bot.log())
    assert any("venue reported no fee" in line for line in bot.log())


def test_a_fee_in_another_currency_books_the_gross_and_says_so():
    """Red means a base-denominated fee is subtracted from quote."""
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE, currency="CHIP"))

    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)

    assert _round(booked) == GROSS
    assert any("not the USD this sale is credited in" in line for line in bot.log())


def test_a_fee_that_swallows_the_sale_books_the_gross_and_says_so():
    """Red means an absurd fee can drive a tranche to zero or below."""
    bot = _StubBot(order=_Order(price=PRICE, fee=GROSS * 2.0))

    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)

    assert _round(booked) == GROSS
    assert any("is not smaller than the gross" in line for line in bot.log())


def test_the_net_case_says_so_too():
    """Red means only the refusals are visible in the operator's log.

    The gross tests above pass on a code path that emits nothing at
    all. This is the control that refuses that reading.
    """
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    _sell(bot, UNITS, PRICE)
    _proceeds(bot)
    assert any("BOOKED NET" in line for line in bot.log())
    assert any("the venue reported" in line for line in bot.log())


# ── THE CARRY, AND WHAT IT REFUSES TO CARRY ──────────────────────────


def test_a_fee_is_spent_once():
    """Red means one venue fee can be subtracted from two valuations."""
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    _sell(bot, UNITS, PRICE)

    assert _round(_proceeds(bot)) == NET
    assert _round(_proceeds(bot)) == GROSS


@pytest.mark.parametrize(
    "units, price",
    [(UNITS + 1.0, PRICE), (UNITS, PRICE * 2.0), (UNITS * 0.5, PRICE * 0.5)],
)
def test_a_fee_from_another_order_is_not_applied(units, price):
    """Red means a stale fee can be booked against an unrelated fill."""
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    _sell(bot, UNITS, PRICE)

    booked = bot._settled_sale_proceeds(units, price, label="SCRUM")
    assert _round(booked) == _round(units * price)


def test_a_sell_that_never_reached_the_exchange_clears_the_record():
    """Red means a refused sell leaves the previous sell's fee live."""
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    _sell(bot, UNITS, PRICE)
    assert bot._last_sell_venue_fee is not None

    bot._order = None
    assert _sell(bot, UNITS, PRICE) is None
    assert bot._last_sell_venue_fee is None
    assert _round(_proceeds(bot)) == GROSS


def test_a_bot_built_without_init_can_still_value_a_sale():
    """Red means a sell raises AttributeError on a restored bot.

    The fee record has a CLASS-level default because bots are built
    with ``object.__new__`` -- across this suite and on the restore
    paths -- and a sale that raises rather than books is strictly
    worse than a sale booked at the gross.
    """
    bare = object.__new__(ScrummingBot)
    bare.bot_id = "no-init"
    bare.config = _Config()
    bare._bus = _Bus()

    assert bare._last_sell_venue_fee is None
    assert _round(bare._settled_sale_proceeds(UNITS, PRICE, label="SCRUM")) == GROSS


def test_one_bots_fee_is_never_readable_by_another():
    """Red means the class-level default became shared mutable state."""
    first = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    second = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))

    _sell(first, UNITS, PRICE)

    assert second._last_sell_venue_fee is None
    assert _round(_proceeds(second)) == GROSS
    assert _round(_proceeds(first)) == NET


def test_a_buy_fee_is_never_recorded_as_a_sale_fee():
    """Red means a fold's buy fee can be taken off a scrum's proceeds."""
    bot = _StubBot()
    buy = _Order(price=PRICE, fee=VENUE_FEE, side=OrderSide.BUY, filled=UNITS)

    bot._record_venue_fee(buy, UNITS, PRICE)

    assert bot._last_sell_venue_fee is None
    assert _round(_proceeds(bot)) == GROSS


# ── THE MANUAL PATH: ``_settled_fill`` CARRIES IT ────────────────────


def test_the_manual_path_carries_the_fee_off_the_placed_order():
    """Red means Manual Fire lost the venue's fee on a settled order."""
    bot = _StubBot()
    order = _Order(price=PRICE, fee=VENUE_FEE, filled=UNITS)

    amount, price, is_real = _settled(bot, order, UNITS, PRICE)

    assert (amount, price, is_real) == (UNITS, PRICE, True)
    assert _round(_proceeds(bot, amount, price)) == NET


def test_the_manual_path_carries_the_fee_off_the_RE_READ_order():
    """Red means the fee is read from the wrong order object.

    ``_settled_fill`` re-reads when the placed order carries no fill.
    The fee belongs to whichever object supplied the accepted fill --
    reading the caller's stale object would book a fee of zero.
    """
    stale = _Order(price=0.0, fee=0.0, currency="", filled=0.0)
    fetched = _Order(price=PRICE, fee=VENUE_FEE, filled=UNITS)
    bot = _StubBot(fetched=fetched)

    amount, price, is_real = _settled(bot, stale, UNITS, PRICE)

    assert bot.exchange.get_order_calls >= 1, "the re-read never happened"
    assert (amount, price, is_real) == (UNITS, PRICE, True)
    assert _round(_proceeds(bot, amount, price)) == NET


def test_an_estimated_fill_carries_no_fee_at_all():
    """Red means an unconfirmed fill books a fee the venue never gave.

    ``_settled_fill`` books an ESTIMATE when the venue confirms
    nothing. There is no settled order behind it, so there is no fee.
    """
    unsettled = _Order(price=0.0, fee=0.0, currency="", filled=0.0, order_id="")
    bot = _StubBot()

    amount, price, is_real = _settled(bot, unsettled, UNITS, PRICE)

    assert is_real is False
    assert bot._last_sell_venue_fee is None
    assert _round(_proceeds(bot, amount, price)) == GROSS


#: Every module the ScrummingBot engine is spread across. A scan of one
#: of them alone would pass over code that moved to another.
ENGINE_PATHS = tuple(
    [REPO / "src" / "trading" / "scrumming_bot.py"]
    + [
        REPO / "src" / "trading" / "scrumming" / _n
        for _n in (
            "execution.py",
            "fold_tranches.py",
            "reconciliation.py",
            "tick_phases.py",
        )
    ]
)
ENGINE_SRC = "\n".join(_p.read_text(encoding="utf-8") for _p in ENGINE_PATHS)
_SOURCE = ENGINE_SRC
_TREE = ast.parse(_SOURCE)


def _proceeds_assignments():
    """Every ``x = self._settled_sale_proceeds(...)`` in the module."""
    found = []
    for node in ast.walk(_TREE):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "_settled_sale_proceeds":
            continue
        target = node.targets[0]
        found.append((target.id if isinstance(target, ast.Name) else "?", call))
    return found


def test_all_three_fold_loops_value_the_sale_through_the_helper():
    """Red means a loop values a sale without the venue's fee."""
    names = sorted(name for name, _ in _proceeds_assignments())
    assert names == ["dist_usd", "fill_usd", "scrum_usd"], (
        f"expected the SCRUM, DIST and MANUAL proceeds to come from "
        f"the helper; found {names}"
    )


def test_each_loop_values_its_own_units_at_its_own_fill():
    """Red means a loop values one sale's units at another's price."""
    expected = {
        "scrum_usd": ("scrum_asset", "sell_fill"),
        "dist_usd": ("dist_asset", "dist_fill"),
        "fill_usd": ("fill_amount", "fill_price"),
    }
    for name, call in _proceeds_assignments():
        units, price = call.args
        assert isinstance(units, ast.Name) and isinstance(price, ast.Name)
        assert (units.id, price.id) == expected[name], (
            f"{name} is valued from ({units.id}, {price.id}), not " f"{expected[name]}"
        )
        labels = [kw for kw in call.keywords if kw.arg == "label"]
        assert labels, f"{name} names no path in the operator's log"


def _enclosing_function(lineno: int):
    """The innermost ``def`` containing ``lineno``."""
    best = None
    for node in ast.walk(_TREE):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.lineno <= lineno <= (node.end_lineno or node.lineno):
            if best is None or node.lineno > best.lineno:
                best = node
    return best


@pytest.mark.parametrize(
    "target, units, price",
    [
        ("scrum_usd", "scrum_asset", "sell_fill"),
        ("dist_usd", "dist_asset", "dist_fill"),
        ("fill_usd", "fill_amount", "fill_price"),
    ],
)
def test_no_loop_multiplies_the_units_by_the_fill_any_more(target, units, price):
    """Red means the gross notional came back into a build loop.

    This is the pin that goes red if unit 9b is reverted.

    It is scoped to an ASSIGNMENT of the loop's own proceeds variable,
    inside the loop's own function, because two untouched sites read
    alike and neither belongs to this unit: ``_execute_detonation``
    assigns ``fill_usd = fill_price * fill_amount`` for a sale it then
    discards the tranches of, and the manual FOLD branch multiplies
    ``fill_amount * fill_price`` into ``total_folded_usd``, which is a
    BUY's cost. A module-wide sweep would report both as this unit's
    regression.
    """
    site = [call for name, call in _proceeds_assignments() if name == target]
    assert len(site) == 1, f"{target} is not assigned from the helper once"
    owner = _enclosing_function(site[0].lineno)
    assert owner is not None

    for node in ast.walk(owner):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == target for t in node.targets):
            continue
        value = node.value
        if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.Mult):
            continue
        left, right = value.left, value.right
        if not (isinstance(left, ast.Name) and isinstance(right, ast.Name)):
            continue
        assert {left.id, right.id} != {units, price}, (
            f"{owner.name} line {node.lineno} sets {target} to "
            f"{left.id} * {right.id}, which is the GROSS notional"
        )


def test_the_gross_notional_pin_can_see_the_shape_it_refuses():
    """Red means the pin above is blind and its pass means nothing.

    Two TERMINAL LIQUIDATIONS still carry the exact shape the three
    loops were fixed out of. Neither is in this unit's scope, and
    neither builds a fold tranche -- both CLEAR ``_fold_tranches`` --
    but both value a sale at the gross notional, so this list is also
    the standing record of where the same class of defect remains.
    """
    found = []
    for node in ast.walk(_TREE):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "fill_usd" for t in node.targets
        ):
            continue
        value = node.value
        if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.Mult):
            continue
        owner = _enclosing_function(node.lineno)
        found.append(owner.name if owner else "?")
    assert sorted(found) == ["_execute_detonation", "self_destruct"], (
        f"expected the two liquidation paths to be the remaining sites; "
        f"found {found}"
    )


# ── THE RECORD TYPE ──────────────────────────────────────────────────


def test_the_record_cannot_be_edited_after_the_venue_wrote_it():
    """Red means a settled fee became rewritable in flight."""
    record = SettledSellFee(
        units=UNITS, price=PRICE, fee_amount=VENUE_FEE, currency="USD", reported=True
    )
    with pytest.raises(Exception):
        record.fee_amount = 0.0


# The two ccxt order dicts Coinbase can produce, as
# ``CCXTConnector._parse_order`` receives them.

# A Coinbase placement: `success_response` carries no `total_fees`, so
# the fee parses to None.
_PLACED = {
    "id": "52cfe5e2-0b29-4c19-a245-a6a773de5030",
    "symbol": "CHIP/USD",
    "side": "sell",
    "type": "market",
    "amount": None,
    "price": None,
    "filled": None,
    "remaining": None,
    "status": None,
    "average": None,
    "cost": None,
    "fee": {"cost": None, "currency": None},
    "timestamp": None,
}

# What ccxt builds from a Coinbase RE-READ, whose body does carry
# ``total_fees``. ccxt passes it through as a string.
_REREAD = dict(
    _PLACED,
    filled=UNITS,
    average=PRICE,
    status="closed",
    cost=GROSS,
    fee={"cost": str(VENUE_FEE), "currency": "USD"},
)


def test_a_coinbase_placement_carries_no_fee_and_a_re_read_does():
    """Red means the connector contract this unit relies on changed.

    Both halves matter. The first is why SCRUM and DIST book gross on
    live Coinbase; the second is why the manual path can book net.
    """
    placed = CCXTConnector._parse_order(_PLACED)
    reread = CCXTConnector._parse_order(_REREAD)

    assert placed.fee == 0.0
    assert placed.average == 0.0
    assert placed.filled == 0.0

    assert reread.fee == pytest.approx(VENUE_FEE)
    assert reread.fee_currency == "USD"
    assert reread.average == pytest.approx(PRICE)


def test_a_placed_coinbase_order_books_the_gross_and_says_so():
    """Red means the bot invented a fee Coinbase never sent it."""
    bot = _StubBot()
    bot._record_venue_fee(CCXTConnector._parse_order(_PLACED), UNITS, PRICE)

    assert bot._last_sell_venue_fee.reported is False
    assert bot._last_sell_venue_fee.fee_amount == 0.0
    assert _round(_proceeds(bot)) == GROSS
    assert any("venue reported no fee" in line for line in bot.log())


def test_a_re_read_coinbase_order_books_the_net():
    """Red means the manual path drops a fee the venue did send."""
    bot = _StubBot()
    bot._record_venue_fee(CCXTConnector._parse_order(_REREAD), UNITS, PRICE)

    booked = _proceeds(bot)
    assert booked > 0.0, "a settled sale that books nothing is not a fix"
    assert _round(booked) == NET
    assert _round(booked) != GROSS
