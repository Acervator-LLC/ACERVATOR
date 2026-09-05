"""Target Delta's first operand comes from the exchange.

``_reconcile_holdings`` adopts an exchange balance above the lot book and
books the difference as a ``reconciled_to_exchange`` lot.
``_claimable_exchange_units`` bounds what it may adopt::

    claimable = exchange - personal_hold_qty - sibling_tracked_units

Anything above ``claimable`` is still refused, and downward drift still
rescales the book.
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
        # `_main_lots` units must keep summing to `_current_holdings`.
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
        # Target 307.65 against the wallet's 324.87: a positive delta.
        bot = _bot(14131.0, 15778.0)
        stale_delta = bot._current_holdings * 0.02059 - 307.65431093420716
        _run(bot)
        live_delta = bot._current_holdings * 0.02059 - 307.65431093420716
        assert stale_delta < 0, "precondition: the stale book said BUY"
        assert live_delta > 0, "the exchange figure says SELL"

    def test_the_log_line_reports_what_it_actually_did(self):
        # The emitted line must name the action the code took.
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


def test_the_attribution_helper_subtracts_both_declarations():
    """``_claimable_exchange_units`` returns the wallet less both holds.

    It also reports the ``personal`` and ``sibling`` figures it subtracted.
    """
    bot = _bot(14131.0, 15778.0, personal=100.0, sibling=250.0)
    claimable, personal, sibling = bot._claimable_exchange_units(15778.0)

    assert personal == 100.0
    assert sibling == 250.0
    assert claimable == 15778.0 - 100.0 - 250.0


def test_the_reconcile_asks_the_shared_attribution_helper():
    """``_reconcile_holdings`` routes through ``_claimable_exchange_units``.

    That call is the seam ``bootstrap_exchange_state`` shares with it.
    """
    bot = _bot(14131.0, 15778.0)
    real = bot._claimable_exchange_units
    seen = []

    def _spy(exchange_units):
        seen.append(exchange_units)
        return real(exchange_units)

    bot._claimable_exchange_units = _spy
    _run(bot)

    assert seen == [15778.0], f"the reconcile did not ask the helper: {seen}"


def test_control_an_uninstalled_spy_records_nothing():
    """The control for ``test_the_reconcile_asks_the_shared_attribution_helper``.

    A ``seen`` list no ``_spy`` writes to stays empty across ``_run``.
    """
    bot = _bot(14131.0, 15778.0)
    seen = []
    _run(bot)
    assert seen == [], "the list recorded a call nothing was wired to make"
