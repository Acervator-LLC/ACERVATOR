"""Soft reservations against the wallet all 35 bots share (item 2, M3).

THE DEFECT
Manual Fire's FOLD branch clipped its buy with
``buy_usd = min(buy_usd_target, quote_free * _qrate)``. Measured against
live state 2026-08-07, all 35 bots report the SAME ``cash_balance_usd``
-- one wallet -- and each read it with no reservation. A single fire is
safe (0 of 20 eligible bots clipped that day). Concurrent fires are not:
every bot sees the whole balance, each believes it can afford its own
buy, and together they can commit more than exists. The orders that
arrive last get rejected or partially filled, which reaches the operator
as an unexplained amount.

SCOPE, STATED HONESTLY
This is a PROCESS-LOCAL advisory ledger. It cannot see an order placed
by another process or by the operator's own hand on the Coinbase site.
It stops the fleet racing ITSELF, which is the only party it can
coordinate. Tests below pin that boundary rather than implying more.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.wallet_reservations import (  # noqa: E402
    WalletReservations,
    get_wallet_reservations,
    wallet_key,
)


@pytest.fixture
def led():
    return WalletReservations()


class TestTheInstrumentWorks:
    def test_a_fresh_ledger_holds_nothing(self, led):
        """POSITIVE CONTROL for every 'reduces the budget' test below."""
        k = wallet_key("coinbase", "USD")
        assert led.reserved(k) == 0.0
        assert led.available(k, 1000.0) == pytest.approx(1000.0)

    def test_a_reservation_reduces_what_is_available(self, led):
        k = wallet_key("coinbase", "USD")
        led.reserve(k, 250.0)
        assert led.available(k, 1000.0) == pytest.approx(750.0)


class TestTheFleetStopsRacingItself:
    def test_a_second_bot_sees_the_first_bots_hold(self, led):
        """THE defect. Both bots read the same $100 wallet; without the
        ledger both would size a $100 buy and commit $200."""
        k = wallet_key("coinbase", "USD")
        wallet = 100.0
        bot_a_budget = led.available(k, wallet)
        led.reserve(k, bot_a_budget)
        bot_b_budget = led.available(k, wallet)
        assert bot_a_budget == pytest.approx(100.0)
        assert bot_b_budget == pytest.approx(0.0)
        assert bot_a_budget + bot_b_budget <= wallet

    def test_holds_accumulate_across_many_bots(self, led):
        k = wallet_key("coinbase", "USD")
        for _ in range(5):
            led.reserve(k, 10.0)
        assert led.reserved(k) == pytest.approx(50.0)
        assert led.available(k, 100.0) == pytest.approx(50.0)

    def test_releasing_returns_the_budget(self, led):
        k = wallet_key("coinbase", "USD")
        led.reserve(k, 60.0)
        led.release(k, 60.0)
        assert led.available(k, 100.0) == pytest.approx(100.0)

    def test_currencies_do_not_share_a_budget(self, led):
        led.reserve(wallet_key("coinbase", "USD"), 100.0)
        assert led.available(wallet_key("coinbase", "USDC"),
                             100.0) == pytest.approx(100.0)

    def test_exchanges_do_not_share_a_budget(self, led):
        led.reserve(wallet_key("coinbase", "USD"), 100.0)
        assert led.available(wallet_key("kraken", "USD"),
                             100.0) == pytest.approx(100.0)


class TestItCannotHandOutMoreThanExists:
    def test_over_reservation_reports_zero_not_negative(self, led):
        """A negative budget would flip `buy_usd <= 0` and let a clipped
        buy through as if it were affordable."""
        k = wallet_key("coinbase", "USD")
        led.reserve(k, 500.0)
        assert led.available(k, 100.0) == 0.0

    def test_over_release_does_not_drive_the_total_negative(self, led):
        """Releasing more than held would hand the next caller a budget
        LARGER than the wallet."""
        k = wallet_key("coinbase", "USD")
        led.reserve(k, 10.0)
        led.release(k, 999.0)
        assert led.reserved(k) == 0.0
        assert led.available(k, 100.0) == pytest.approx(100.0)

    def test_a_negative_reserve_is_ignored(self, led):
        k = wallet_key("coinbase", "USD")
        led.reserve(k, -50.0)
        assert led.reserved(k) == 0.0

    def test_an_emptied_hold_is_pruned(self, led):
        k = wallet_key("coinbase", "USD")
        led.reserve(k, 5.0)
        led.release(k, 5.0)
        assert k not in led.snapshot()


class TestTheSingletonIsShared:
    def test_the_module_getter_returns_one_ledger(self):
        """Two bots must not each get their own ledger -- that would
        restore the defect while looking fixed."""
        assert get_wallet_reservations() is get_wallet_reservations()

    def test_a_hold_is_visible_through_the_getter(self):
        k = wallet_key("coinbase", "TESTCOIN")
        led = get_wallet_reservations()
        try:
            led.reserve(k, 7.0)
            assert get_wallet_reservations().reserved(k) == pytest.approx(7.0)
        finally:
            led.release(k, 7.0)

    def test_clear_empties_everything(self):
        led = WalletReservations()
        led.reserve(wallet_key("coinbase", "USD"), 1.0)
        led.clear()
        assert led.snapshot() == {}


class TestTheReserveIsAtomic:
    def test_reserve_and_release_contain_no_await(self):
        """The no-lock design is only safe because these cannot be
        interleaved by another coroutine. An `await` here would make the
        operation interruptible and silently reintroduce the race."""
        import ast

        import src.trading.wallet_reservations as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for name in ("reserve", "release", "available", "reserved"):
            fn = next(n for n in ast.walk(tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name == name)
            assert not isinstance(fn, ast.AsyncFunctionDef), \
                f"{name} became a coroutine; the no-lock design is unsafe"
            assert not any(isinstance(x, ast.Await) for x in ast.walk(fn)), \
                f"{name} contains an await; reservation is no longer atomic"
