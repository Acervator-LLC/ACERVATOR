"""Target Delta's first operand must come from the exchange.

Operator directive, 2026-08-22, verbatim:

    "Target Delta is supposed to be a simple calculation of Current
     Balance (from the exchange) vs. Target Balance (anchor / in app).
     There should be no other control."

    "ANYTHING that induces disagreement with exchange values is broken."

THE DEFECT THESE PIN. ``_reconcile_holdings`` refused every upward
correction. A bot whose lot book fell behind the wallet kept trading on
the stale number for as long as it ran.

Measured on the live fleet 2026-08-22, bot 95340bda (BILL/USD): the book
held 14131 units, the exchange held 15778, and the gap was 1647 units the
bot had itself bought and failed to book. The Ammo cell then rendered
"buy $16.27" on a position roughly $17 ABOVE its target -- the signal
inverted, on an accumulation platform.

WHAT MUST SURVIVE. The refusal existed for a reason: on 2026-07-27 a
fresh ETH/BTC bot claimed about $178 of the operator's personal coin.
That protection is kept, expressed as attribution rather than as a
blanket refusal:

    claimable = exchange - personal_hold_qty - sibling_tracked_units

Both subtrahends are declarations, not inferences. Anything above
``claimable`` is genuinely foreign and is still refused.
"""

import asyncio

import pytest

from src.trading.scrumming_bot import ScrummingBot


class _Bal:
    def __init__(self, total, absent=False):
        self.total = total
        self.free = total
        self.absent = absent


class _Bus:
    def __init__(self):
        self.messages = []

    def emit(self, _topic, **kw):
        self.messages.append(str(kw.get("message", "")))


class _Mgr:
    """Stands in for BotManager. ``sibling_units`` is what other bots on
    this asset already track."""

    def __init__(self, sibling_units=0.0, raises=False):
        self._sibling_units = sibling_units
        self._raises = raises

    def has_sibling_target_bots(self, *_a, **_kw):
        return self._sibling_units > 0

    def sum_sibling_tracked_units(self, *_a, **_kw):
        if self._raises:
            raise RuntimeError("manager unreadable")
        return self._sibling_units


def _bot(
    internal_units,
    exchange_units,
    *,
    personal=0.0,
    sibling=0.0,
    mgr_raises=False,
    price=0.02059,
):
    """A bot whose book holds ``internal_units`` and whose wallet holds
    ``exchange_units``. Built without __init__ so the test does not boot
    an exchange, a Qt window or an event loop."""
    bot = ScrummingBot.__new__(ScrummingBot)
    bot.bot_id = "95340bda"
    bot._bus = _Bus()
    bot._main_lots = [
        {
            "units": internal_units,
            "initial_buy_price": 0.0199995,
            "operator_initiated": False,
        }
    ]
    bot._current_holdings = internal_units
    bot._quote_to_usd = 1.0

    class _Cfg:
        target_asset = "BILL"
        symbol = "BILL/USD"
        personal_hold_qty = personal

    class _Stats:
        current_price = price
        position_value = 0.0

    bot.config = _Cfg()
    bot.stats = _Stats()
    bot._bot_manager = _Mgr(sibling, raises=mgr_raises)

    async def _get_balance(_asset):
        return _Bal(exchange_units)

    bot._get_balance = _get_balance
    return bot


def _run(bot):
    return asyncio.run(bot._reconcile_holdings("test"))


def _book(bot):
    return sum(float(l["units"]) for l in bot._main_lots)


# The live defect


class TestTheBillDefect:
    """The exact numbers the operator was looking at."""

    def test_the_bot_adopts_the_exchange_balance(self):
        bot = _bot(14131.0, 15778.0)
        assert _run(bot) is True
        assert bot._current_holdings == pytest.approx(15778.0)

    def test_the_lot_book_follows_the_scalar(self):
        # sum(_main_lots units) == _current_holdings is what makes the
        # delta computable at all. An adopt that moved only the scalar
        # would trade one broken invariant for another.
        bot = _bot(14131.0, 15778.0)
        _run(bot)
        assert _book(bot) == pytest.approx(bot._current_holdings)
        assert _book(bot) == pytest.approx(15778.0)

    def test_the_reconciliation_lot_is_flagged_not_disguised(self):
        bot = _bot(14131.0, 15778.0)
        _run(bot)
        added = [l for l in bot._main_lots if l.get("reconciled_to_exchange")]
        assert len(added) == 1
        assert added[0]["units"] == pytest.approx(1647.0)
        # Booked at the reconcile price, not at an invented fill price.
        assert added[0]["initial_buy_price"] == pytest.approx(0.02059)

    def test_the_target_delta_is_computed_from_the_exchange(self):
        # The whole point. Target 307.65; the wallet's 15778 units at
        # 0.02059 is 324.87, so the delta is POSITIVE -- sell surplus.
        # On the stale 14131 it read negative, i.e. buy.
        bot = _bot(14131.0, 15778.0)
        stale_delta = bot._current_holdings * 0.02059 - 307.65431093420716
        _run(bot)
        live_delta = bot._current_holdings * 0.02059 - 307.65431093420716
        assert stale_delta < 0, "precondition: the stale book said BUY"
        assert live_delta > 0, "the exchange figure says SELL"

    def test_the_log_line_reports_what_it_actually_did(self):
        # The defect emitted "Resetting internal state to exchange
        # reality" and then preserved -- 735 times on BILL. A line that
        # names an action the code did not take is the thing that hid
        # this for weeks.
        bot = _bot(14131.0, 15778.0)
        _run(bot)
        joined = "\n".join(bot._bus.messages)
        assert "adopted the exchange balance" in joined
        assert "Preserving internal state" not in joined


# What must still be refused — the 2026-07-27 protection


class TestTheOperatorsCoinIsStillSafe:

    def test_a_personal_hold_is_not_claimed(self):
        # 1647 surplus, all of it declared personal. Claim nothing.
        bot = _bot(14131.0, 15778.0, personal=1647.0)
        _run(bot)
        assert bot._current_holdings == pytest.approx(14131.0)
        assert _book(bot) == pytest.approx(14131.0)

    def test_a_partial_personal_hold_claims_only_the_remainder(self):
        bot = _bot(14131.0, 15778.0, personal=1000.0)
        _run(bot)
        assert bot._current_holdings == pytest.approx(14778.0)
        assert _book(bot) == pytest.approx(14778.0)

    def test_sibling_tracked_units_are_not_claimed(self):
        bot = _bot(14131.0, 15778.0, sibling=1647.0)
        _run(bot)
        assert bot._current_holdings == pytest.approx(14131.0)

    def test_an_unreadable_sibling_total_claims_nothing(self):
        # Unknown attribution must fail closed, not open.
        bot = _bot(14131.0, 15778.0, mgr_raises=True)
        _run(bot)
        assert bot._current_holdings == pytest.approx(14131.0)

    def test_the_refusal_still_names_its_reason(self):
        bot = _bot(14131.0, 15778.0, personal=1647.0)
        _run(bot)
        joined = "\n".join(bot._bus.messages)
        assert "Preserving internal state" in joined
        assert "Personal hold" in joined


# No regression on the arm this repair does not touch


class TestDownwardDriftIsUnchanged:

    def test_drift_down_still_rescales_the_book(self):
        # The exchange holds LESS than the book. That is a real loss and
        # the book must come down to it, exactly as before.
        bot = _bot(15778.0, 14131.0)
        _run(bot)
        assert bot._current_holdings == pytest.approx(14131.0)
        assert _book(bot) == pytest.approx(14131.0)

    def test_alignment_within_tolerance_changes_nothing(self):
        bot = _bot(14131.0, 14131.0)
        _run(bot)
        assert bot._current_holdings == pytest.approx(14131.0)
        assert len(bot._main_lots) == 1


# Falsifier, restated rather than deleted


def test_without_the_adopt_the_book_stayed_behind_the_wallet():
    """Records what the code did before this repair.

    Reads the live source so it cannot drift into describing a tree that
    does not exist. If someone restores the blanket refusal, this fails.
    """
    from pathlib import Path

    import inspect

    from src.trading.scrumming_bot import ScrummingBot

    src = Path(inspect.getsourcefile(ScrummingBot._reconcile_holdings))
    text = src.read_text(encoding="utf-8")
    # Matched on a contiguous token. The operator-facing sentence is
    # split across f-string literals, so asserting the rendered phrase
    # against the SOURCE would pass or fail on line wrapping rather
    # than on behaviour.
    assert "reconciled_to_exchange" in text, (
        "the drift-UP branch no longer books a reconciliation lot -- "
        "the Target Delta operand has stopped coming from the exchange"
    )
    # v3.25.10 moved this expression out of the branch and into
    # `_claimable_exchange_units`, so that `bootstrap_exchange_state`
    # asks the same question the same way. The token asserted here
    # moved with it; the arithmetic is character-for-character the one
    # that was in the branch.
    assert "exchange_units - _personal - _sib_units" in text, (
        "the attribution arithmetic is gone; upward drift is either "
        "refused wholesale again or claiming units it has not attributed"
    )
    assert "def _claimable_exchange_units(" in text, (
        "the shared attribution helper is gone, so the reconcile and "
        "the bootstrap pre-fill can drift apart again"
    )
