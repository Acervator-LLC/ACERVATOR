"""Unit C — behaviour pins for src/exchange/ccxt_connector.py.

Unit C cleared ten pre-existing coding_archetype HIGH findings in a file
that places real orders. The only defensible way to clear a finding in
such a file is to change nothing an operator can observe, so this module
pins the observable behaviour the clean-up had to preserve, plus the two
places where the clean-up is itself the invariant.

What each group would mean if it went red
-----------------------------------------
preflight    The connect handshake changed shape: a different request
             object, header, URL, timeout or TLS context reaches the
             opener, or a refused scheme reports differently.
passphrase   The ``sync_connect`` default changed meaning. ``""``,
             ``None`` and "argument omitted" must remain one behaviour;
             a real passphrase must still reach ccxt as ``password``.
retry        A retry budget moved. These counts are INSTRUMENTED — the
             fake counts its own invocations — never read back from the
             decorator's own bookkeeping.
orders       ``place_order`` submitted more than once, or the circuit
             breaker stopped short-circuiting. Either is live money.
annotations  ``HistoryAnalysis`` stopped resolving, which is the defect
             mypy and pyright both reported before Unit C.
"""

from __future__ import annotations

import asyncio
import sys
import types
import typing
import urllib.request
from typing import Any

import pytest

from src.core import retry as R
from src.core.safe_url import SafeRequest
from src.exchange import ccxt_connector as M
from src.exchange.base import OrderSide, OrderType
from src.exchange.circuit_breaker import (
    CircuitBreakerOpenError,
    get_breaker_registry,
)

RETRYABLE_ATTEMPTS = 3
CONNECT_ATTEMPTS = 3
# one for the sync exchange, one for the async exchange built beside it
CONFIGS_PER_CONNECT = 2


# ---------------------------------------------------------------------
# doubles
# ---------------------------------------------------------------------
class RequestTimeout(Exception):
    """Class name carries the decorator's 'timeout' keyword."""


class NetworkError(Exception):
    """Class name carries the decorator's 'network' keyword."""


class ExchangeError(Exception):
    """Class name carries none of the decorator's keywords."""


class FakeSyncExchange:
    """The slice of a ccxt exchange class that sync_connect touches."""

    configs: list[dict[str, Any]] = []
    calls: list[str] = []
    raises: BaseException | None = None

    def __init__(self, config: dict[str, Any]) -> None:
        FakeSyncExchange.configs.append(dict(config))
        self.has: dict[str, bool] = {}
        self.markets: dict[str, Any] = {"BTC/USD": {"id": "BTC-USD"}}
        self.markets_by_id: dict[str, Any] = {"BTC-USD": {}}
        self.currencies: dict[str, Any] = {"BTC": {}}
        self.symbols: list[str] = ["BTC/USD"]

    def load_markets(self) -> dict[str, Any]:
        """Count this attempt, then succeed or raise as configured."""
        FakeSyncExchange.calls.append("load_markets")
        if FakeSyncExchange.raises is not None:
            raise FakeSyncExchange.raises
        return self.markets

    @classmethod
    def reset(cls) -> None:
        """Forget every recorded config and call."""
        cls.configs = []
        cls.calls = []
        cls.raises = None


class FakeBackend:
    """The ccxt surface `CCXTConnector._ex` reaches, with call recording."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.create_order_raises: BaseException | None = None
        self.fetch_ticker_raises: BaseException | None = None
        self.markets: dict[str, Any] = {"BTC/USD": {"id": "BTC-USD"}}

    def count(self, name: str) -> int:
        """How many times the named member actually ran."""
        return sum(1 for call in self.calls if call[0] == name)

    def market(self, symbol: str) -> dict[str, Any]:
        """Return market metadata, recording the lookup."""
        self.calls.append(("market", symbol))
        return {"id": symbol.replace("/", "-")}

    def amount_to_precision(self, symbol: str, amount: Any) -> str:
        """Mimic ccxt: precision helpers hand back strings."""
        self.calls.append(("amount_to_precision", symbol, float(amount)))
        return f"{float(amount):.8f}"

    def price_to_precision(self, symbol: str, price: Any) -> str:
        """Mimic ccxt: precision helpers hand back strings."""
        self.calls.append(("price_to_precision", symbol, float(price)))
        return f"{float(price):.2f}"

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Return a fixed ticker, or raise the configured error."""
        self.calls.append(("fetch_ticker", symbol))
        if self.fetch_ticker_raises is not None:
            raise self.fetch_ticker_raises
        return {
            "bid": 100.0,
            "ask": 101.0,
            "last": 100.5,
            "quoteVolume": 5000.0,
            "timestamp": 1700000000000,
        }

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: Any,
        price: Any,
        params: Any = None,
    ) -> dict[str, Any]:
        """Return a filled order, or raise the configured error."""
        self.calls.append(
            ("create_order", symbol, order_type, side, float(amount), price, params)
        )
        if self.create_order_raises is not None:
            raise self.create_order_raises
        return {
            "id": "ORD-1",
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "amount": amount,
            "price": price or 0,
            "filled": amount,
            "remaining": 0,
            "status": "closed",
            "timestamp": 1700000000000,
            "average": price or 0,
            "fee": {"cost": 0.1, "currency": "USD"},
        }


# ---------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------
@pytest.fixture
def fake_ccxt(monkeypatch: pytest.MonkeyPatch) -> type[FakeSyncExchange]:
    """Shadow ccxt so no connect attempt in this module can reach a network."""
    FakeSyncExchange.reset()
    mod = types.ModuleType("ccxt")
    asy = types.ModuleType("ccxt.async_support")
    for ccxt_name in set(M.SUPPORTED_EXCHANGES.values()):
        setattr(mod, ccxt_name, FakeSyncExchange)
        setattr(asy, ccxt_name, FakeSyncExchange)
    mod.async_support = asy
    monkeypatch.setitem(sys.modules, "ccxt", mod)
    monkeypatch.setitem(sys.modules, "ccxt.async_support", asy)
    return FakeSyncExchange


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[float]]:
    """Record every delay the connector asks for; never actually wait.

    Both waits are issued from ``src.core.retry``, so that module is
    shimmed alongside the connector.
    """
    record: dict[str, list[float]] = {"blocking": [], "awaited": []}
    # Bind the REAL modules before patching. Delegating to `M.time`
    # after the patch lands resolves to the shim itself and recurses.
    real_time = M.time
    real_asyncio = M.asyncio

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

    monkeypatch.setattr(M, "time", TimeShim(), raising=True)
    monkeypatch.setattr(M, "asyncio", AsyncioShim(), raising=True)
    monkeypatch.setattr(R, "time", TimeShim(), raising=True)
    monkeypatch.setattr(R, "asyncio", AsyncioShim(), raising=True)
    return record


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture what the preflight hands to safe_urlopen, opening nothing."""
    seen: list[dict[str, Any]] = []

    class FakeResp:
        status = 200

        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *_exc_info: Any) -> None:
            return None

    def recorder(req: Any, data: Any = None, **kwargs: Any) -> FakeResp:
        seen.append({"req": req, "data": data, "kwargs": kwargs})
        return FakeResp()

    monkeypatch.setattr(M, "safe_urlopen", recorder, raising=True)
    return seen


def connected(eid: str = "coinbase") -> tuple[Any, FakeBackend]:
    """A connector served entirely by a fake backend, no network."""
    conn = M.CCXTConnector(eid)
    backend = FakeBackend()
    conn.attach_backend(backend)
    return conn, backend


def shutdown(conn: Any) -> None:
    """Release the connector's single-worker executor."""
    conn._sync_executor.shutdown(wait=False)


# =====================================================================
# preflight — the S310 finding
# =====================================================================
@pytest.mark.usefixtures("fake_ccxt")
def test_preflight_request_is_checked_at_construction(
    opened: list[dict[str, Any]],
) -> None:
    """The preflight must build a request whose scheme is already checked.

    safe_urlopen validates at OPEN time. Between building the request and
    opening it, a plain urllib Request is an ordinary object holding an
    unchecked URL — the window SafeRequest exists to close. Pinning the
    type here is what stops the site drifting back to the plain form.
    """
    conn = M.CCXTConnector("coinbase")
    try:
        conn.sync_connect("key-abc", "secret-xyz")
    finally:
        shutdown(conn)

    assert len(opened) == 1
    req = opened[0]["req"]
    assert isinstance(req, SafeRequest)
    assert isinstance(req, urllib.request.Request)


@pytest.mark.usefixtures("fake_ccxt")
def test_preflight_call_shape_is_unchanged(
    opened: list[dict[str, Any]],
) -> None:
    """URL, both headers, timeout and TLS context must all survive."""
    import ssl

    for eid, url in sorted(M.PREFLIGHT_URLS.items()):
        opened.clear()
        conn = M.CCXTConnector(eid)
        passphrase = "pp" if eid in M.PASSPHRASE_EXCHANGES else ""
        try:
            conn.sync_connect("key-abc", "secret-xyz", passphrase)
        finally:
            shutdown(conn)

        assert len(opened) == 1, eid
        req = opened[0]["req"]
        assert req.full_url == url
        assert req.get_header("User-agent") == "Acervator/1.8"
        assert req.get_header("Accept") == "application/json"
        assert opened[0]["data"] is None
        assert opened[0]["kwargs"]["timeout"] == 15
        assert isinstance(opened[0]["kwargs"]["context"], ssl.SSLContext)


@pytest.mark.parametrize(
    "bad_url",
    [
        "file:///C:/Windows/win.ini",
        "ftp://example.com/x",
        "data:text/plain;base64,QQ==",
        "gopher://x/1",
    ],
)
@pytest.mark.usefixtures("fake_ccxt")
def test_preflight_refuses_non_http_scheme(
    monkeypatch: pytest.MonkeyPatch,
    bad_url: str,
) -> None:
    """A refused scheme reaches the operator as one specific message.

    The refusal moved earlier (construction, not open). The text the
    operator sees must not move with it, so it is asserted in full.
    """
    monkeypatch.setitem(M.PREFLIGHT_URLS, "kraken", bad_url)
    scheme = bad_url.split(":")[0]
    conn = M.CCXTConnector("kraken")
    try:
        with pytest.raises(ConnectionError) as caught:
            conn.sync_connect("key-abc", "secret-xyz")
    finally:
        shutdown(conn)

    assert str(caught.value) == (
        f"Cannot reach kraken API. Pre-flight check failed: "
        f"ValueError: safe_urlopen: refused scheme {scheme!r} "
        f"(URL: {bad_url!r}). Allowed schemes: ['http', 'https']. "
        f"| URL: {bad_url}"
    )
    assert conn.is_connected is False
    assert FakeSyncExchange.calls == []


@pytest.mark.usefixtures("fake_ccxt")
def test_refused_scheme_never_reaches_a_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No opener may be driven at all for a file: preflight URL."""
    driven: list[Any] = []
    real_open = urllib.request.OpenerDirector.open

    def spy(self: Any, *args: Any, **kwargs: Any) -> Any:
        driven.append(args)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", spy)
    monkeypatch.setitem(M.PREFLIGHT_URLS, "kraken", "file:///C:/Windows/win.ini")

    conn = M.CCXTConnector("kraken")
    try:
        with pytest.raises(ConnectionError):
            conn.sync_connect("key-abc", "secret-xyz")
    finally:
        shutdown(conn)

    assert driven == []


@pytest.mark.usefixtures("fake_ccxt")
def test_preflight_failure_stops_before_markets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead network is one ConnectionError, and no markets load."""

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("network is unreachable")

    monkeypatch.setattr(M, "safe_urlopen", boom, raising=True)
    conn = M.CCXTConnector("coinbase")
    try:
        with pytest.raises(ConnectionError) as caught:
            conn.sync_connect("key-abc", "secret-xyz")
    finally:
        shutdown(conn)

    assert "OSError: network is unreachable" in str(caught.value)
    assert FakeSyncExchange.calls == []


# =====================================================================
# passphrase — the B107 finding
# =====================================================================
@pytest.mark.parametrize("supplied", ["OMIT", "", None])
@pytest.mark.usefixtures("fake_ccxt", "opened")
def test_absent_passphrase_is_one_behaviour(
    supplied: str | None,
) -> None:
    """Omitted, empty and None must stay indistinguishable.

    The default changed from ``""`` to ``None`` to clear B107. If these
    three ever diverge, that change was not behaviour-neutral.
    """
    conn = M.CCXTConnector("kucoin")
    try:
        with pytest.raises(ValueError) as caught:
            if supplied == "OMIT":
                conn.sync_connect("key-abc", "secret-xyz")
            else:
                conn.sync_connect("key-abc", "secret-xyz", supplied)
    finally:
        shutdown(conn)

    assert str(caught.value) == (
        "Kucoin requires an API passphrase. "
        "This is set when you create the API key on the exchange."
    )
    assert conn.is_connected is False
    assert FakeSyncExchange.configs == []


@pytest.mark.usefixtures("fake_ccxt", "opened")
def test_supplied_passphrase_reaches_ccxt() -> None:
    """A real passphrase still arrives as ccxt's `password` field."""
    conn = M.CCXTConnector("okx")
    try:
        conn.sync_connect("key-abc", "secret-xyz", "the-passphrase")
    finally:
        shutdown(conn)

    # sync_connect builds the sync exchange and then the async one from
    # the same config, so both instantiations are recorded.
    assert len(FakeSyncExchange.configs) == CONFIGS_PER_CONNECT
    for config in FakeSyncExchange.configs:
        assert config["password"] == "the-passphrase"


@pytest.mark.parametrize("supplied", ["OMIT", "", None])
@pytest.mark.usefixtures("fake_ccxt", "opened")
def test_venue_without_passphrase_never_sets_password(
    supplied: str | None,
) -> None:
    """Coinbase must not gain a `password` key from any absent form."""
    conn = M.CCXTConnector("coinbase")
    try:
        if supplied == "OMIT":
            conn.sync_connect("key-abc", "secret-xyz")
        else:
            conn.sync_connect("key-abc", "secret-xyz", supplied)
    finally:
        shutdown(conn)

    assert conn.is_connected is True
    assert len(FakeSyncExchange.configs) == CONFIGS_PER_CONNECT
    for config in FakeSyncExchange.configs:
        assert "password" not in config


@pytest.mark.usefixtures("fake_ccxt", "opened")
def test_async_connect_still_delegates() -> None:
    """`await connect(...)` reaches sync_connect with the same meaning."""
    conn = M.CCXTConnector("kucoin")
    try:
        with pytest.raises(ValueError):
            asyncio.run(conn.connect("key-abc", "secret-xyz"))
    finally:
        shutdown(conn)


# =====================================================================
# retry budgets — instrumented, never read back
# =====================================================================
@pytest.mark.usefixtures("fake_ccxt", "opened")
def test_connect_retry_budget(
    sleeps: dict[str, list[float]],
) -> None:
    """load_markets is attempted three times, backing off 2s then 4s."""
    FakeSyncExchange.raises = RuntimeError("exchange said no")
    conn = M.CCXTConnector("binance")
    try:
        with pytest.raises(ConnectionError) as caught:
            conn.sync_connect("key-abc", "secret-xyz")
    finally:
        shutdown(conn)

    assert len(FakeSyncExchange.calls) == CONNECT_ATTEMPTS
    assert sleeps["blocking"] == [2.0, 4.0]
    assert str(caught.value) == "RuntimeError: exchange said no"


@pytest.mark.parametrize(
    ("error", "attempts", "backoff"),
    [
        (RequestTimeout("read timed out"), RETRYABLE_ATTEMPTS, [1.0, 2.0]),
        (NetworkError("conn reset"), RETRYABLE_ATTEMPTS, [1.0, 2.0]),
        (ExchangeError("bad symbol"), 1, []),
        (ValueError("nope"), 1, []),
    ],
)
def test_get_ticker_retry_budget(
    sleeps: dict[str, list[float]],
    error: BaseException,
    attempts: int,
    backoff: list[float],
) -> None:
    """Only transient-looking names retry, and only twice more."""
    conn, backend = connected()
    backend.fetch_ticker_raises = error
    try:
        with pytest.raises(type(error)):
            asyncio.run(conn.get_ticker("BTC/USD"))
    finally:
        shutdown(conn)

    assert backend.count("fetch_ticker") == attempts
    assert sleeps["awaited"] == backoff


def test_get_ticker_success_is_one_call(
    sleeps: dict[str, list[float]],
) -> None:
    """A healthy fetch costs exactly one call and no backoff."""
    conn, backend = connected()
    try:
        ticker = asyncio.run(conn.get_ticker("BTC/USD"))
    finally:
        shutdown(conn)

    assert backend.count("fetch_ticker") == 1
    assert sleeps["awaited"] == []
    assert ticker.bid == 100.0
    assert ticker.ask == 101.0
    assert ticker.last == 100.5


# =====================================================================
# orders — live money
# =====================================================================
@pytest.mark.parametrize(
    "error",
    [
        ExchangeError("insufficient funds"),
        RequestTimeout("read timed out"),
        NetworkError("connection reset"),
    ],
)
def test_place_order_never_retries(error: BaseException) -> None:
    """TD-014: a failed submission is submitted once and only once.

    A second submission on a timeout is how an account ends up with two
    positions for one intent, so the count is instrumented in the fake
    rather than inferred from the decorator.
    """
    conn, backend = connected()
    backend.create_order_raises = error
    try:
        with pytest.raises(type(error)) as caught:
            asyncio.run(
                conn.place_order(
                    "UNITC-NORETRY", OrderSide.SELL, OrderType.LIMIT, 1.0, 50.0
                )
            )
    finally:
        shutdown(conn)

    assert backend.count("create_order") == 1
    assert str(caught.value) == str(error)


def test_place_order_success_shape() -> None:
    """A limit order reaches ccxt with the arguments it always had."""
    conn, backend = connected()
    try:
        order = asyncio.run(
            conn.place_order("BTC/USD", OrderSide.BUY, OrderType.LIMIT, 0.5, 100.0)
        )
    finally:
        shutdown(conn)

    submitted = [c for c in backend.calls if c[0] == "create_order"]
    assert submitted == [("create_order", "BTC/USD", "limit", "buy", 0.5, 100.0, None)]
    assert order.id == "ORD-1"
    assert order.filled == 0.5
    assert order.fee == 0.1
    assert order.fee_currency == "USD"


def test_place_order_short_circuits_on_open_breaker() -> None:
    """An OPEN breaker refuses before any order can be submitted.

    This is the branch whose import line lost the unused ``BreakerState``
    name. The branch itself must be untouched.
    """
    conn, backend = connected()
    breaker = get_breaker_registry().get("coinbase:UNITC-OPEN")
    breaker._transition_to_open(ExchangeError("forced"))
    before = breaker.stats.total_short_circuits
    try:
        with pytest.raises(CircuitBreakerOpenError) as caught:
            asyncio.run(
                conn.place_order(
                    "UNITC-OPEN", OrderSide.BUY, OrderType.LIMIT, 1.0, 10.0
                )
            )
    finally:
        shutdown(conn)

    assert backend.count("create_order") == 0
    assert breaker.stats.total_short_circuits == before + 1
    assert str(caught.value).startswith(
        "Circuit breaker for 'coinbase:UNITC-OPEN' is OPEN;"
    )


def test_unconnected_connector_refuses_orders() -> None:
    """No exchange instance means no order, with the original message."""
    conn = M.CCXTConnector("coinbase")
    try:
        with pytest.raises(RuntimeError) as caught:
            asyncio.run(
                conn.place_order("BTC/USD", OrderSide.BUY, OrderType.LIMIT, 1.0, 1.0)
            )
    finally:
        shutdown(conn)

    assert str(caught.value) == "Not connected to Coinbase"


def test_queue_cap_fails_fast() -> None:
    """A saturated queue is refused without touching the exchange."""
    conn, backend = connected()
    conn._sync_queue_depth = M.MEM_220_QUEUE_CAP
    try:
        with pytest.raises(M.CCXTQueueFullError):
            asyncio.run(conn.get_ticker("BTC/USD"))
    finally:
        shutdown(conn)

    assert backend.count("fetch_ticker") == 0


# =====================================================================
# annotations — the name-defined finding
# =====================================================================
@pytest.mark.parametrize(
    "method",
    [
        "_on_history_result",
        "get_history",
        "set_history_callback",
    ],
)
def test_history_annotations_resolve(method: str) -> None:
    """Every annotation on the history surface must name a real type.

    mypy and pyright both reported ``HistoryAnalysis`` as undefined here.
    ``get_type_hints`` is the runtime form of the same question, so it
    raises NameError against the unfixed file and passes against the
    fixed one.
    """
    hints = typing.get_type_hints(getattr(M.CCXTConnector, method))
    assert hints


def test_history_callback_roundtrip() -> None:
    """Register, fire, cache — and survive a callback that raises."""
    from src.core.trade_historian import HistoryAnalysis

    conn = M.CCXTConnector("coinbase")
    seen: list[tuple[str, Any]] = []
    analysis = HistoryAnalysis(symbol="BTC/USD", exchange_id="coinbase", trade_count=3)
    try:
        assert conn._on_history_ready is None

        def good(symbol: str, payload: Any) -> str:
            seen.append((symbol, payload))
            return "a non-None return value"

        conn.set_history_callback(good)
        assert conn._on_history_ready is good
        conn._on_history_result("BTC/USD", analysis)
        assert seen == [("BTC/USD", analysis)]
        assert conn.get_history("BTC/USD") is analysis
        assert conn.get_history("NOPE/USD") is None

        def boom(symbol: str, payload: Any) -> None:
            raise RuntimeError("callback exploded")

        conn.set_history_callback(boom)
        conn._on_history_result("ETH/USD", analysis)
        assert conn.get_history("ETH/USD") is analysis
    finally:
        shutdown(conn)


def test_supported_exchange_listing_shape() -> None:
    """The listing's passphrase flag is a bool, as the annotation says."""
    rows = M.list_supported_exchanges()
    assert len(rows) == len(M.SUPPORTED_EXCHANGES)
    for row in rows:
        assert sorted(row) == ["id", "name", "requires_passphrase"]
        assert isinstance(row["requires_passphrase"], bool)
        assert row["requires_passphrase"] == (row["id"] in M.PASSPHRASE_EXCHANGES)
