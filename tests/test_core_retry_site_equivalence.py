"""Behaviour pins for the three retry sites now served by src/core/retry.py.

The three sites disagreed on attempt count, delay schedule, which
exceptions are transient, and whether exhaustion raises or is reported.
This module pins each one's observable behaviour separately, so a shared
helper cannot quietly flatten them into one.

What each group would mean if it went red
-----------------------------------------
inventory   The set of ``CCXTConnector`` methods that retry has changed.
            If ``place_order`` joined it, a lost response on an accepted
            order re-submits the same order (TD-014, live money).
decorator   A retry budget, a delay, or the transient-name rule moved on
            the connector's read paths.
fetcher     The Stone Tablet fetcher's budget, delays or report-vs-raise
            outcome moved. A delay after the FINAL attempt would mean the
            16-second dead wait is back.
primitives  ``src/core/retry.py`` no longer offers the four independent
            knobs each site needs.

Every count and delay below is a literal. Nothing is read back from the
constant the code under test reads.
"""

from __future__ import annotations

import ast
import asyncio
import itertools
from pathlib import Path
from typing import Any

import pytest

from src.core import retry as R
from src.exchange import ccxt_connector as M
from src.exchange.base import OrderSide, OrderType
from src.trading.stone_tablets import fetcher as F

RETRY_CARRYING_METHODS = frozenset(
    {
        "cancel_order",
        "get_balance",
        "get_balances",
        "get_markets",
        "get_my_trades",
        "get_ohlcv",
        "get_open_orders",
        "get_order",
        "get_orderbook",
        "get_ticker",
    }
)

# get_balance calls get_balances, and both carry the decorator, so a
# transient error costs 3 x 3 venue calls.
TRANSIENT_ATTEMPTS = {
    "cancel_order": 3,
    "get_all_tickers": 1,
    "get_balance": 9,
    "get_balances": 3,
    "get_markets": 3,
    "get_my_trades": 3,
    "get_ohlcv": 3,
    "get_open_orders": 3,
    "get_order": 3,
    "get_orderbook": 3,
    "get_ticker": 3,
    "place_order": 1,
}

TRANSIENT_DELAYS = {
    "cancel_order": [1.0, 2.0],
    "get_all_tickers": [],
    "get_balance": [1.0, 2.0, 1.0, 1.0, 2.0, 2.0, 1.0, 2.0],
    "get_balances": [1.0, 2.0],
    "get_markets": [1.0, 2.0],
    "get_my_trades": [1.0, 2.0],
    "get_ohlcv": [1.0, 2.0],
    "get_open_orders": [1.0, 2.0],
    "get_order": [1.0, 2.0],
    "get_orderbook": [1.0, 2.0],
    "get_ticker": [1.0, 2.0],
    "place_order": [],
}

_SYMBOL_SEQ = itertools.count()


# doubles
class RequestTimeout(Exception):
    """Class name carries the transient keyword 'request'."""


class NetworkError(Exception):
    """Class name carries the transient keyword 'network'."""


class RateLimitExceeded(Exception):
    """Class name carries the transient keyword 'ratelimit'."""


class ExchangeError(Exception):
    """Class name carries no transient keyword."""


class FetchBoom(Exception):
    """A fetch failure with no transient keyword in its name."""


class RaisingBackend:
    """Every ccxt member the connector reaches raises one error."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def _boom(self, *_args: Any, **_kwargs: Any) -> Any:
        """Count this venue call, then fail."""
        self.calls += 1
        raise self.error

    fetch_ticker = _boom
    fetch_order_book = _boom
    fetch_ohlcv = _boom
    fetch_balance = _boom
    cancel_order = _boom
    fetch_order = _boom
    fetch_open_orders = _boom
    fetch_my_trades = _boom
    fetch_tickers = _boom
    create_order = _boom

    def market(self, symbol: str) -> dict[str, Any]:
        """Metadata lookup, which never fails in these pins."""
        return {"id": symbol.replace("/", "-")}

    def amount_to_precision(self, _symbol: str, amount: Any) -> str:
        """Mimic ccxt: precision helpers hand back strings."""
        return f"{float(amount):.8f}"

    def price_to_precision(self, _symbol: str, price: Any) -> str:
        """Mimic ccxt: precision helpers hand back strings."""
        return f"{float(price):.2f}"

    @property
    def markets(self) -> Any:
        """Reading the market map is get_markets' one venue call."""
        self.calls += 1
        raise self.error


class FailingConn:
    """A tablet-fetch connector whose every call fails."""

    def __init__(self) -> None:
        self.calls = 0

    async def get_ohlcv(self, *_args: Any, **_kwargs: Any) -> Any:
        """Count this fetch, then fail."""
        self.calls += 1
        raise FetchBoom("venue down")


class OneChunkConn:
    """A tablet-fetch connector that answers with one candle."""

    def __init__(self) -> None:
        self.calls = 0

    async def get_ohlcv(self, *_args: Any, **_kwargs: Any) -> Any:
        """Count this fetch, then answer."""
        self.calls += 1
        return [[1700000000000, 1.0, 2.0, 0.5, 1.5, 10.0]]


class ZeroBudgetAdapter(F.CoinbaseAdapter):
    """An adapter configured to permit no attempt at all."""

    retry_max = 0


def _invoke(conn: Any, method: str) -> Any:
    """Return the coroutine for one connector method with valid arguments."""
    calls = {
        "get_ticker": lambda: conn.get_ticker("BTC/USD"),
        "get_orderbook": lambda: conn.get_orderbook("BTC/USD"),
        "get_ohlcv": lambda: conn.get_ohlcv("BTC/USD"),
        "get_balances": lambda: conn.get_balances(),
        "get_balance": lambda: conn.get_balance("BTC"),
        "cancel_order": lambda: conn.cancel_order("1", "BTC/USD"),
        "get_order": lambda: conn.get_order("1", "BTC/USD"),
        "get_open_orders": lambda: conn.get_open_orders("BTC/USD"),
        "get_my_trades": lambda: conn.get_my_trades("BTC/USD"),
        "get_markets": lambda: conn.get_markets(),
        "get_all_tickers": lambda: conn.get_all_tickers(),
        "place_order": lambda: conn.place_order(
            f"RETRY-{next(_SYMBOL_SEQ)}/USD",
            OrderSide.BUY,
            OrderType.LIMIT,
            1.0,
            10.0,
        ),
    }
    return calls[method]()


# fixtures
@pytest.fixture
def delays(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[float]]:
    """Record every delay asked for; never actually wait."""
    record: dict[str, list[float]] = {"blocking": [], "awaited": []}
    real_time = R.time
    real_asyncio = R.asyncio

    class TimeShim:
        def __getattr__(self, name: str) -> Any:
            return getattr(real_time, name)

        def sleep(self, secs: float) -> None:
            record["blocking"].append(round(float(secs), 6))

    class AsyncioShim:
        def __getattr__(self, name: str) -> Any:
            return getattr(real_asyncio, name)

        async def sleep(self, secs: float) -> None:
            record["awaited"].append(round(float(secs), 6))

    monkeypatch.setattr(R, "time", TimeShim(), raising=True)
    monkeypatch.setattr(R, "asyncio", AsyncioShim(), raising=True)
    monkeypatch.setattr(F, "asyncio", AsyncioShim(), raising=True)
    return record


def _run(error: BaseException, method: str) -> tuple[int, BaseException]:
    """Drive one connector method against a backend that always fails."""
    conn = M.CCXTConnector("coinbase")
    backend = RaisingBackend(error)
    conn.attach_backend(backend)
    try:
        with pytest.raises(type(error)) as caught:
            asyncio.run(_invoke(conn, method))
    finally:
        conn._sync_executor.shutdown(wait=False)
    return backend.calls, caught.value


# inventory — which methods retry at all
def test_decorator_is_applied_to_exactly_these_methods() -> None:
    """The retry-carrying method set is fixed and excludes order submission.

    Read from the source rather than from the wrapped objects, so the
    check survives any change to how the decorator wraps.
    """
    tree = ast.parse(Path(M.__file__).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "CCXTConnector":
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in item.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(target, ast.Name) and target.id == "_with_retry":
                    found.add(item.name)

    assert found == set(RETRY_CARRYING_METHODS)
    assert "place_order" not in found
    assert len(found) == 10


@pytest.mark.parametrize("method", sorted(TRANSIENT_ATTEMPTS))
def test_transient_error_attempt_budget(
    delays: dict[str, list[float]], method: str
) -> None:
    """A transient failure costs each method its own fixed number of calls.

    ``place_order`` at 1 is TD-014: a second submission of an accepted
    order is a duplicate position.
    """
    calls, _ = _run(RequestTimeout("read timed out"), method)
    assert calls == TRANSIENT_ATTEMPTS[method]
    assert delays["awaited"] == TRANSIENT_DELAYS[method]
    assert delays["blocking"] == []


@pytest.mark.parametrize("method", sorted(TRANSIENT_ATTEMPTS))
def test_non_transient_error_is_never_retried(
    delays: dict[str, list[float]], method: str
) -> None:
    """An error with no transient keyword costs exactly one venue call."""
    calls, _ = _run(ExchangeError("bad symbol"), method)
    assert calls == 1
    assert delays["awaited"] == []


@pytest.mark.parametrize(
    "error",
    [
        RequestTimeout("read timed out"),
        NetworkError("connection reset"),
        RateLimitExceeded("slow down"),
    ],
)
def test_every_transient_keyword_retries(
    delays: dict[str, list[float]], error: BaseException
) -> None:
    """Each of the three transient keywords must still trigger a retry."""
    calls, raised = _run(error, "get_ticker")
    assert calls == 3
    assert delays["awaited"] == [1.0, 2.0]
    assert str(raised) == str(error)


@pytest.mark.parametrize(
    "error",
    [
        RequestTimeout("read timed out"),
        NetworkError("connection reset"),
        RateLimitExceeded("slow down"),
        ExchangeError("insufficient funds"),
    ],
)
def test_order_submission_is_never_retried(
    delays: dict[str, list[float]], error: BaseException
) -> None:
    """TD-014: no error class may cause a second create_order."""
    calls, raised = _run(error, "place_order")
    assert calls == 1
    assert delays["awaited"] == []
    assert str(raised) == str(error)


# fetcher — reports, never raises
def test_fetcher_retries_every_error_and_reports_it(
    delays: dict[str, list[float]],
) -> None:
    """Four attempts, three waits, and the failure comes back as a value.

    The Stone Tablet fetcher retries EVERY exception, unlike the
    connector, and hands GapFiller an error string instead of raising.
    """
    conn = FailingConn()
    adapter = F.CoinbaseAdapter(connector=conn)
    out = asyncio.run(adapter.fetch_chunk("BTC", "USD", 1000, 2000))

    assert conn.calls == 4
    assert delays["awaited"] == [2.0, 4.0, 8.0]
    assert isinstance(out, F.FetchAttempt)
    assert out.error == "FetchBoom: venue down"
    assert out.candles == []
    assert out.since_ms == 1000
    assert out.until_ms == 2000


def test_fetcher_does_not_wait_after_its_last_attempt(
    delays: dict[str, list[float]],
) -> None:
    """One fewer wait than attempts.

    A fourth wait is the 16-second dead sleep before an error the
    fetcher already held.
    """
    conn = FailingConn()
    asyncio.run(F.CoinbaseAdapter(connector=conn).fetch_chunk("BTC", "USD", 0, 1))

    assert conn.calls == 4
    assert len(delays["awaited"]) == 3
    assert 16.0 not in delays["awaited"]


def test_fetcher_success_costs_one_call(delays: dict[str, list[float]]) -> None:
    """A healthy chunk fetch makes one call and waits for nothing."""
    conn = OneChunkConn()
    adapter = F.CoinbaseAdapter(connector=conn)
    out = asyncio.run(adapter.fetch_chunk("BTC", "USD", 1600000000000, 1800000000000))

    assert conn.calls == 1
    assert delays["awaited"] == []
    assert out.error is None
    assert out.candles == [[1700000000000, 1.0, 2.0, 0.5, 1.5, 10.0]]


def test_fetcher_zero_budget_reports_exhausted(
    delays: dict[str, list[float]],
) -> None:
    """An adapter permitting no attempt reports, and still never raises."""
    conn = FailingConn()
    out = asyncio.run(ZeroBudgetAdapter(connector=conn).fetch_chunk("X", "USD", 1, 2))

    assert conn.calls == 0
    assert delays["awaited"] == []
    assert out.error == "all retries exhausted"


def test_fetcher_budgets_are_unchanged() -> None:
    """The two adapters' declared budgets are the pinned numbers."""
    assert F.ExchangeAdapter.retry_max == 3
    assert F.ExchangeAdapter.retry_base_s == 2.0
    assert F.CoinbaseAdapter.retry_max == 4
    assert F.CoinbaseAdapter.retry_base_s == 2.0
    assert F.CoinGeckoAdapter.retry_max == 3
    assert F.CoinGeckoAdapter.retry_base_s == 5.0


def test_coingecko_placeholder_makes_no_call(delays: dict[str, list[float]]) -> None:
    """CoinGecko's budget is declared but unreachable: it fetches nothing."""
    conn = FailingConn()
    out = asyncio.run(F.CoinGeckoAdapter(connector=conn).fetch_chunk("X", "USD", 1, 2))

    assert conn.calls == 0
    assert delays["awaited"] == []
    assert out.error is not None


# primitives — the four knobs must stay independent
@pytest.mark.parametrize(
    ("name", "transient"),
    [
        ("RequestTimeout", True),
        ("NetworkError", True),
        ("RateLimitExceeded", True),
        ("RateLimitError", True),
        ("ReadTimeoutError", True),
        ("ExchangeError", False),
        ("InsufficientFunds", False),
        ("ValueError", False),
        ("InvalidOrder", False),
    ],
)
def test_is_transient_reads_the_class_name(name: str, transient: bool) -> None:
    """The transient rule matches on the class NAME, not the type."""
    assert R.is_transient(type(name, (Exception,), {})()) is transient


def test_retry_any_accepts_everything() -> None:
    """The fetcher's policy must keep retrying non-transient errors."""
    assert R.retry_any(ValueError("x")) is True
    assert R.retry_any(KeyboardInterrupt()) is True


def test_delay_schedules_are_distinct() -> None:
    """Exponential and linear are different curves from the same base."""
    exp = R.exponential_delay(2.0)
    assert [exp(0), exp(1), exp(2), exp(3)] == [2.0, 4.0, 8.0, 16.0]
    lin = R.linear_delay(2.0)
    assert [lin(0), lin(1), lin(2)] == [2.0, 4.0, 6.0]


def test_retry_async_stops_at_the_attempt_budget(
    delays: dict[str, list[float]],
) -> None:
    """Five attempts, four waits, and the last exception reaches the caller."""
    seen: list[int] = []

    async def op() -> None:
        seen.append(len(seen))
        raise RequestTimeout("nope")

    with pytest.raises(RequestTimeout):
        asyncio.run(
            R.retry_async(
                op,
                attempts=5,
                delay_for=R.exponential_delay(1.0),
                is_retryable=R.is_transient,
            )
        )

    assert len(seen) == 5
    assert delays["awaited"] == [1.0, 2.0, 4.0, 8.0]


def test_retry_sync_stops_at_the_attempt_budget(
    delays: dict[str, list[float]],
) -> None:
    """The blocking variant follows the same budget on time.sleep."""
    seen: list[int] = []

    def op() -> None:
        seen.append(len(seen))
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        R.retry_sync(
            op,
            attempts=3,
            delay_for=R.linear_delay(2.0),
            is_retryable=R.retry_any,
            on_failure=None,
        )

    assert len(seen) == 3
    assert delays["blocking"] == [2.0, 4.0]
    assert delays["awaited"] == []


def test_retry_reports_every_failure_once(delays: dict[str, list[float]]) -> None:
    """on_failure fires per failed attempt, and only the last says no retry."""
    hook: list[tuple[str, int, bool, float]] = []

    async def op() -> None:
        raise RequestTimeout("nope")

    with pytest.raises(RequestTimeout):
        asyncio.run(
            R.retry_async(
                op,
                attempts=3,
                delay_for=R.exponential_delay(1.0),
                is_retryable=R.is_transient,
                on_failure=lambda e, a, w, d: hook.append((type(e).__name__, a, w, d)),
            )
        )

    assert hook == [
        ("RequestTimeout", 0, True, 1.0),
        ("RequestTimeout", 1, True, 2.0),
        ("RequestTimeout", 2, False, 0.0),
    ]


def test_retry_returns_the_first_success(delays: dict[str, list[float]]) -> None:
    """A call that recovers returns its value and stops calling."""
    seen: list[int] = []

    async def op() -> str:
        seen.append(len(seen))
        if len(seen) < 3:
            raise RequestTimeout("not yet")
        return "value"

    got = asyncio.run(
        R.retry_async(
            op,
            attempts=9,
            delay_for=R.exponential_delay(1.0),
            is_retryable=R.is_transient,
        )
    )

    assert got == "value"
    assert len(seen) == 3
    assert delays["awaited"] == [1.0, 2.0]


@pytest.mark.parametrize("attempts", [0, -1])
def test_a_budget_below_one_is_refused(attempts: int) -> None:
    """A zero budget is a programming error, not a silent no-op."""

    async def op() -> None:
        raise AssertionError("must not be called")

    with pytest.raises(ValueError):
        asyncio.run(
            R.retry_async(
                op,
                attempts=attempts,
                delay_for=R.exponential_delay(1.0),
                is_retryable=R.is_transient,
            )
        )
    with pytest.raises(ValueError):
        R.retry_sync(
            lambda: None,
            attempts=attempts,
            delay_for=R.exponential_delay(1.0),
            is_retryable=R.is_transient,
        )


def test_policy_arguments_have_no_defaults() -> None:
    """Attempts, delay and retryability must be stated at every call site.

    A default would let a new site inherit another site's policy.
    """
    import inspect

    for fn in (R.retry_async, R.retry_sync):
        params = inspect.signature(fn).parameters
        for name in ("attempts", "delay_for", "is_retryable"):
            assert params[name].default is inspect.Parameter.empty, (fn, name)
            assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
