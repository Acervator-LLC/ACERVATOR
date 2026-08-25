# v3.23.96 justification: test files legitimately access private
# members (SLF001) and use pytest's `assert` idiom (S101).
"""v3.23.96 — regression pin for the _get_balance self-recursion bug.

Root cause (v3.23.76): a global replace of
``self.exchange.get_balance(`` -> ``self._get_balance(`` ate its own
tail inside the fallback path of the `_get_balance` wrapper itself,
producing a self-recursive call when `_data_pool is None`. Live bots
never hit it (BotManager wires the pool on start -> early-return
branch). Sim bots (v3.23.72+ Fleet Replay) had `_data_pool = None`
and blew up with RecursionError on every tick.

This test binds `_get_balance` to a bare object with `_data_pool =
None` and a fake exchange, calls the method, and asserts:
  (a) it returns the fake exchange's balance without raising
      RecursionError
  (b) the fake exchange's `get_balance` was called EXACTLY ONCE
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


class _FakeBalance:
    def __init__(self, currency):
        self.currency = currency
        self.free = 100.0
        self.used = 0.0
        self.total = 100.0
        self.absent = False


class _FakeExchange:
    def __init__(self):
        self.calls = 0

    async def get_balance(self, currency):
        self.calls += 1
        return _FakeBalance(currency)


def _stub_bot_with_pool_none():
    stub = SimpleNamespace()
    stub.bot_id = "regression-test"
    stub.config = SimpleNamespace(exchange_id="fake")
    stub._data_pool = None
    stub.exchange = _FakeExchange()
    stub._get_balance = MethodType(ScrummingBot._get_balance, stub)
    return stub


def test_get_balance_no_self_recursion_when_pool_missing():
    """Prior bug: self._get_balance called itself instead of
    self.exchange.get_balance in the pool-missing fallback ->
    RecursionError. This test would have caught it on day 1."""
    bot = _stub_bot_with_pool_none()
    result = asyncio.run(bot._get_balance("USD"))
    assert result is not None
    assert result.currency == "USD"
    assert bot.exchange.calls == 1


def test_get_balance_uses_pool_when_wired():
    """Ensure the pool-wired path is unchanged."""
    stub = _stub_bot_with_pool_none()

    class _FakePool:
        def __init__(self):
            self.calls = 0

        async def get_or_fetch_balance(self, exchange, _eid, currency):
            self.calls += 1
            return _FakeBalance(currency)

    stub._data_pool = _FakePool()
    result = asyncio.run(stub._get_balance("USDC"))
    assert result is not None
    assert stub._data_pool.calls == 1
    assert stub.exchange.calls == 0
