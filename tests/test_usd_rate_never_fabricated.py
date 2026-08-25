"""The dollar rate lookup must never invent a number.

BotManager._usd_per_base_for asks the exchange what one unit of an
asset is worth in dollars. Before this file existed, every way that
question could fail returned 1.0 — a made-up rate of one dollar per
unit. One Bitcoin was then priced at one dollar, silently, on a path
that decides how much money each bot may claim.

Two things were measured with the made-up rate in place:

  * register() refused a $2,000 bot on a real 0.5 BTC wallet, saying
    "wallet has $0.50 ... deposit more BTC", and dropped the bot.
  * reconcile_capital_registry() rewrote a stored claim of 0.0327 BTC
    into 2000.0 BTC and saved it, then raised a 399,900% drift alarm.

The rule this file pins: when no honest rate can be had, the lookup
returns nothing. Callers must then do something visible and true
instead of pricing a Bitcoin at a dollar.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.trading.bot_container import BotConfig, BotManager
from src.trading.capital_registry import CapitalRegistry

BTC_USD = 61234.5
WALLET_BTC = 0.5
UNREACHABLE = "exchange unreachable"

# Sentinel for the row where no exchange client exists at all.
NO_CONNECTOR = object()


def _half_a_bitcoin(_exchange_id: str, _base_currency: str) -> float:
    """Wallet provider: the operator really holds half a Bitcoin."""
    return WALLET_BTC


class _Ticker:
    """Stands in for the exchange's synchronous price client."""

    def __init__(self, answer: Any) -> None:
        self._answer = answer

    def fetch_ticker(self, _symbol: str) -> Any:
        if callable(self._answer):
            return self._answer()
        return self._answer

    def fetch_balance(self) -> dict:
        return {"free": {"BTC": WALLET_BTC}}


def _boom() -> Any:
    raise RuntimeError(UNREACHABLE)


def _manager(answer: Any) -> BotManager:
    """A manager whose price client answers exactly one way."""
    mgr = BotManager()
    if answer is NO_CONNECTOR:
        mgr._connector = None
    else:
        mgr._connector = type(
            "_Conn",
            (),
            {
                "_ccxt_sync": _Ticker(answer),
                # register() hands every new bot's symbol to the connector
                # for history scanning; a no-op keeps that path quiet.
                "add_scan_symbol": lambda _self, _symbol: None,
            },
        )()
    return mgr


# ---------------------------------------------------------------------
# The whole set of ways the question can be answered.
# ---------------------------------------------------------------------


def test_rate_available_is_returned_unchanged() -> None:
    """A real price comes back as itself."""
    mgr = _manager({"last": BTC_USD})
    assert mgr._usd_per_base_for("coinbase", "BTC") == BTC_USD


def test_dollar_pegged_base_is_one_dollar() -> None:
    """A dollar-pegged coin really is one dollar per unit. This is the
    one place 1.0 is a true answer, not an invented one."""
    mgr = _manager({"last": BTC_USD})
    assert mgr._usd_per_base_for("coinbase", "USDC") == 1.0


@pytest.mark.parametrize(
    ("answer", "label"),
    [
        (_boom, "request throws"),
        ({"last": 0, "close": 0}, "request returns zero"),
        ({"last": -3.0}, "request returns a negative"),
        ({"last": "not-a-number"}, "request returns something not a number"),
        (None, "request returns nothing at all"),
        (NO_CONNECTOR, "no connector at all"),
    ],
)
def test_no_honest_rate_returns_nothing(answer: Any, label: str) -> None:
    """Every failing row must return nothing, not a number.

    This is the control that catches the old made-up 1.0: put the
    fallback back and every row here reports 1.0 instead of nothing.
    """
    got = _manager(answer)._usd_per_base_for("coinbase", "BTC")
    assert got is None, f"{label}: expected nothing, got {got!r}"


def test_failing_rows_are_not_confusable_with_a_dollar_coin() -> None:
    """A failed lookup and a genuine one-dollar coin must not look the
    same. Without this the caller cannot tell them apart."""
    mgr = _manager(_boom)
    assert mgr._usd_per_base_for("coinbase", "USDC") == 1.0
    assert mgr._usd_per_base_for("coinbase", "BTC") is None


# ---------------------------------------------------------------------
# What the two callers do with the answer.
# ---------------------------------------------------------------------


def _bot(bot_id: str = "bot-1") -> Any:
    cfg = BotConfig(
        exchange_id="coinbase",
        base_currency="BTC",
        target_asset="ETH",
        symbol="ETH/BTC",
        target_balance=2000.0,
    )
    return type(
        "_Bot",
        (),
        {
            "bot_id": bot_id,
            "config": cfg,
            "set_smart_wire": lambda _self, _mgr: None,
        },
    )()


def _registry_holding_one_claim(bot_id: str) -> CapitalRegistry:
    reg = CapitalRegistry(wallet_balances_provider=_half_a_bitcoin)
    reg.request_reservation(
        bot_id=bot_id,
        exchange_id="coinbase",
        base_currency="BTC",
        usd_amount=2000.0,
        current_rate_usd_per_base=BTC_USD,
        bot_mode="scrumming",
    )
    return reg


def test_register_with_a_real_rate_records_the_real_amount() -> None:
    """With a price in hand, the claim is recorded in real coins."""
    reg = CapitalRegistry(wallet_balances_provider=_half_a_bitcoin)
    mgr = _manager({"last": BTC_USD})
    mgr.set_capital_registry(reg)

    granted, reason = mgr.register(_bot())

    assert granted is True, reason
    held = reg.get_reservations()[0]
    assert held.reserved_base == pytest.approx(2000.0 / BTC_USD)
    assert held.last_rate_usd_per_base == pytest.approx(BTC_USD)


def test_register_without_a_rate_keeps_the_bot_and_records_no_claim() -> None:
    """A price outage must not delete a bot.

    With the made-up rate this refused the bot outright and dropped it,
    blaming a wallet it had mispriced by five orders of magnitude. The
    bot now survives, and no claim is written from a number nobody has.
    """
    reg = CapitalRegistry(wallet_balances_provider=_half_a_bitcoin)
    mgr = _manager(_boom)
    mgr.set_capital_registry(reg)

    granted, reason = mgr.register(_bot())

    assert granted is True, reason
    assert "bot-1" in mgr._bots
    assert reg.get_reservations() == []


def test_reconcile_without_a_rate_leaves_the_saved_claim_alone() -> None:
    """A price outage must not rewrite what is already saved.

    With the made-up rate this overwrote a saved claim of 0.0327 BTC
    with 2000.0 BTC and saved that to disk.
    """
    reg = _registry_holding_one_claim("bot-2")
    honest_base = reg.get_reservations()[0].reserved_base

    mgr = _manager(_boom)
    mgr.set_capital_registry(reg)
    report = mgr.reconcile_capital_registry(exchange_id="coinbase", base_currency="BTC")

    assert report is None
    after = reg.get_reservations()[0]
    assert after.reserved_base == pytest.approx(honest_base)
    assert after.last_rate_usd_per_base == pytest.approx(BTC_USD)


def test_reconcile_without_a_rate_raises_no_false_alarm() -> None:
    """The made-up rate produced a 399,900% drift alarm out of nothing.
    No rate means no comparison, so no alarm."""
    reg = _registry_holding_one_claim("bot-3")
    mgr = _manager(_boom)
    mgr.set_capital_registry(reg)
    alarms: list = []
    mgr._bus.subscribe("capital.drift_alert", lambda evt: alarms.append(evt))

    mgr.reconcile_capital_registry(exchange_id="coinbase", base_currency="BTC")

    assert alarms == []


def test_reconcile_with_a_real_rate_still_reports() -> None:
    """The working path must keep working — the control that proves the
    test above is not passing merely because reconcile does nothing."""
    reg = _registry_holding_one_claim("bot-4")
    mgr = _manager({"last": BTC_USD})
    mgr.set_capital_registry(reg)

    report = mgr.reconcile_capital_registry(exchange_id="coinbase", base_currency="BTC")

    assert report is not None
    assert report["wallet_usd"] == pytest.approx(WALLET_BTC * BTC_USD)
