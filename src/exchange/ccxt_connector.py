"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
ccxt_connector.py — CCXT-based exchange connector
===================================================
Implements :class:`ExchangeInterface` on top of the ``ccxt.async_support``
library, providing unified access to 100+ crypto exchanges.

Features:
  • Async I/O via ``ccxt.async_support``
  • Automatic rate limiting with per-exchange backoff
  • Retry logic for transient failures (network, rate-limit)
  • Symbol normalisation and precision enforcement
  • Logo URL resolution via CoinGecko or CryptoCompare CDN
"""

from __future__ import annotations

from ..core.fmt import fmt_price_coerced
from ..core.retry import linear_delay, retry_any, retry_sync, with_retry
from ..core.safe_url import SafeRequest, safe_urlopen
import asyncio
import logging
import threading
import time
from decimal import Decimal, InvalidOperation
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from src.core.trade_historian import HistoryAnalysis, scan_on_connect
from typing import Any, Optional

# Signature of the per-symbol callback registered through
# `set_history_callback`. The historian thread invokes it as
# `cb(symbol, analysis)` and discards the result, so the return type
# is `object`: a callback that returns something is accepted and its
# value ignored, exactly as before.
HistoryCallback = Callable[[str, HistoryAnalysis], object]


# ─────────────────────────────────────────────────────────────────
# MEM-220 — sync-CCXT serialization constants + exceptions
# ─────────────────────────────────────────────────────────────────
# CCXT's sync methods are not thread-safe. Prior to MEM-220 every
# caller used `asyncio.to_thread(self._ex.fetch_X, ...)` which put
# each call on Python's default ThreadPoolExecutor (up to 32 workers).
# Multiple concurrent callers (bot.tick + dashboard refresh +
# market_map refresh) all hammered the same sync CCXT instance,
# triggering an access violation in urllib3/OpenSSL C extensions.
#
# Fix: single-worker dedicated executor per CCXTConnector.
# Every sync call goes through `self._call_sync(fn, ...)` which:
#   1. Enforces a queue-depth cap (refuses excess with QueueFullError)
#   2. Submits to the single worker (inherent serialization)
#   3. Awaits with a timeout slightly longer than CCXT's own timeout
#      so CCXT can abort cleanly before our timeout fires
#
# See also: tests/test_mem220_ccxt_serialization.py

# Queue cap chosen for ~5 calls per 2-second cycle + 3x safety margin.
# If exceeded, network or exchange is degraded; fail fast is correct.
MEM_220_QUEUE_CAP: int = 8

# sync_connect market-load budget: 3 tries, waiting 2s then 4s.
CONNECT_ATTEMPTS: int = 3
CONNECT_BACKOFF_STEP_S: float = 2.0

# Slightly above CCXT's 20-second default so CCXT's own timeout
# aborts the request before our outer wait_for cancels the awaiter.
# Net effect: outer callers always see TimeoutError either from CCXT
# (clean, connection released) or from us (worker thread leaks,
# logged).
MEM_220_CALL_TIMEOUT_SEC: float = 25.0


# v3.24.83 — THE NUMBER OF CANDLES A LIVE CALL ACTUALLY RETURNS.
#
# Not the number requested. `get_ohlcv` passes `limit` into ccxt's
# `since` slot (see the KNOWN DEFECT note on that method), so every live
# caller receives the exchange's default page size no matter what it
# asked for. Coinbase's default is 300.
#
# This exists so the Simulator can reproduce live's real behaviour
# instead of its documented intent. `FleetSimExchange` carries a
# matching constant, deliberately duplicated rather than imported —
# the sim must not import from the live exchange layer — and
# `test_sim_live_ohlcv_parity.py` fails if the two ever disagree.
#
# When the underlying defect is fixed in its own gated cascade, this
# constant and the sim's copy move together, and that test is what
# forces it.
EFFECTIVE_OHLCV_PAGE_SIZE = 300


class CCXTQueueFullError(RuntimeError):
    """Raised by _call_sync when the per-connector queue is at capacity.

    Callers should treat this as a transient network/rate-limit signal
    (log, skip this iteration, retry next tick). It is strictly
    preferable to the alternative (native access violation from
    concurrent CCXT access).
    """


from .base import (
    AssetInfo,
    Balance,
    ExchangeInterface,
    Order,
    OrderBook,
    OrderSide,
    OrderStatus,
    OrderType,
    Ticker,
)
from .api_logger import get_api_log

logger = logging.getLogger("acervator.exchange")

# ---------------------------------------------------------------------------
# Supported exchanges — maps exchange_id to the CCXT class name
# ---------------------------------------------------------------------------
SUPPORTED_EXCHANGES: dict[str, str] = {
    "binance": "binance",
    "coinbase": "coinbase",
    "kraken": "kraken",
    "kucoin": "kucoin",
    "bybit": "bybit",
    "okx": "okx",
    "gateio": "gateio",
    "bitget": "bitget",
    "huobi": "huobi",  # Renamed to 'htx' in newer CCXT — see CCXT_CLASS_ALIASES
    "mexc": "mexc",
    "bitfinex": "bitfinex",
    "gemini": "gemini",
    "poloniex": "poloniex",  # NOT available to US users since Nov 2019
    "bitstamp": "bitstamp",
    "cryptocom": "cryptocom",
}

# CCXT has renamed several exchange classes over its lifetime. The registry
# above keeps the historical id (e.g. "gateio", "huobi") because that is what
# the rest of Acervator — settings, saved bot state, logs — has always used;
# newer CCXT exposes those venues under a new class name ("gate", "htx") and
# drops the old one. Without a fallback, `getattr(ccxt, "gateio")` returns
# None on current CCXT and the connector raises "CCXT does not have class
# 'gateio'", so gateio and huobi cannot connect at all. This map lets
# resolution try the historical id first, then the rename — working on both
# old and new CCXT.
CCXT_CLASS_ALIASES: dict[str, str] = {
    "gateio": "gate",
    "huobi": "htx",
}


def resolve_ccxt_class(ccxt_module: Any, ccxt_id: str) -> Any:
    """Return the CCXT exchange class for ``ccxt_id`` from ``ccxt_module``.

    Tries the registry id first, then its documented rename from
    ``CCXT_CLASS_ALIASES``. Returns ``None`` when neither name resolves, so
    callers can report which id failed rather than crashing on a bare
    ``getattr``. Works against both ``ccxt`` and ``ccxt.async_support``.
    """
    cls = getattr(ccxt_module, ccxt_id, None)
    if cls is None:
        alias = CCXT_CLASS_ALIASES.get(ccxt_id)
        if alias:
            cls = getattr(ccxt_module, alias, None)
    return cls


# Exchanges that require a user-chosen API passphrase in addition to key+secret.
# In CCXT this is passed as the 'password' parameter.
PASSPHRASE_EXCHANGES: set[str] = {
    "kucoin",
    "okx",
    "bitget",
}

# Date of the last public-endpoint measurement behind the three venue
# facts below: IP block, timeframe availability, market metadata.
VENUE_MEASUREMENT_DATE: str = "2026-08-28"

# Venues whose PUBLIC endpoints refuse a request from a US IP. Measured
# by requesting each PREFLIGHT_URLS entry from Oregon, United States on
# VENUE_MEASUREMENT_DATE: binance answered HTTP 451, bybit HTTP 403.
# A venue here cannot be reached at all, with or without credentials.
US_IP_BLOCKED_EXCHANGES: set[str] = {
    "binance",
    "bybit",
}

# Venues whose public endpoints answer from a US IP but whose own terms
# refuse a US account. Not measurable without opening an account there,
# so this set is sourced from venue documentation, not from a probe.
US_ACCOUNT_RESTRICTED_EXCHANGES: set[str] = {
    "poloniex",
    "huobi",
}

# Union of both refusals — the set the connect path warns on.
US_RESTRICTED_EXCHANGES: set[str] = (
    US_IP_BLOCKED_EXCHANGES | US_ACCOUNT_RESTRICTED_EXCHANGES
)

# Venues Acervator has actually traded on. Every other entry in
# SUPPORTED_EXCHANGES is a registry declaration whose order placement,
# fills, balance reads and order lifecycle have never been exercised.
VERIFIED_EXCHANGES: set[str] = {
    "coinbase",
}

# Pre-flight test URLs — public endpoints requiring no auth
PREFLIGHT_URLS: dict[str, str] = {
    "binance": "https://api.binance.com/api/v3/ping",
    "coinbase": "https://api.coinbase.com/api/v3/brokerage/market/products?limit=1",
    "kraken": "https://api.kraken.com/0/public/SystemStatus",
    "kucoin": "https://api.kucoin.com/api/v1/timestamp",
    "bybit": "https://api.bybit.com/v5/market/time",
    "okx": "https://www.okx.com/api/v5/public/time",
    "gateio": "https://api.gateio.ws/api/v4/spot/currencies",
    "bitget": "https://api.bitget.com/api/v2/public/time",
    "huobi": "https://api.huobi.pro/v1/common/timestamp",
    "mexc": "https://api.mexc.com/api/v3/ping",
    "bitfinex": "https://api-pub.bitfinex.com/v2/platform/status",
    "gemini": "https://api.gemini.com/v1/symbols",
    "poloniex": "https://api.poloniex.com/markets",
    "bitstamp": "https://www.bitstamp.net/api/v2/ticker/btcusd/",
    "cryptocom": "https://api.crypto.com/exchange/v1/public/get-instruments",
}

# Exchange-specific CCXT options applied during sync_connect
EXCHANGE_OPTIONS: dict[str, dict] = {
    "coinbase": {
        "advanced": True,
        "fetchMarkets": "fetchMarketsV3",
        "fetchTicker": "fetchTickerV3",
        "fetchTickers": "fetchTickersV3",
        "fetchAccounts": "fetchAccountsV3",
        "fetchBalance": "v3PrivateGetBrokerageAccounts",
    },
}

# Exchanges where fetchCurrencies must be disabled (deprecated v2 endpoints)
DISABLE_FETCH_CURRENCIES: set[str] = {
    "coinbase",  # v2/currencies deprecated for CDP keys
}

# CCXT's precisionMode values. A market's `precision` dict means a
# DIFFERENT THING under each, and CCXT publishes these as module-level
# integers rather than an enum. Mirrored here because ccxt is imported
# lazily inside the connect path; test_exchange_registry pins them
# against the installed ccxt so a renumbering cannot pass silently.
CCXT_DECIMAL_PLACES: int = 2
CCXT_SIGNIFICANT_DIGITS: int = 3
CCXT_TICK_SIZE: int = 4

DEFAULT_PRECISION_DECIMALS: int = 8


def precision_to_decimals(
    value: Any,
    precision_mode: int,
    default: int = DEFAULT_PRECISION_DECIMALS,
) -> int:
    """Convert one CCXT market ``precision`` entry to a count of decimal places.

    ``AssetInfo.price_precision`` and ``AssetInfo.amount_precision`` are
    consumed as decimal places — ``BotContainer`` truncates an order size
    to that many places before its minimum-size check — but CCXT only
    reports decimal places under ``DECIMAL_PLACES`` mode. Under
    ``TICK_SIZE``, which is what nearly every venue uses, the same field
    carries a step size such as ``1e-06``, and reading it as a count is
    wrong for every venue including Coinbase.

    Returns ``default`` when the value is missing, unparseable, or in
    ``SIGNIFICANT_DIGITS`` mode, where a decimal-place count does not
    exist independently of the number being rounded.
    """
    if value is None:
        return default
    if precision_mode == CCXT_SIGNIFICANT_DIGITS:
        return default
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default
    if not dec.is_finite():
        return default
    if precision_mode == CCXT_DECIMAL_PLACES:
        return max(0, int(dec))
    if precision_mode != CCXT_TICK_SIZE:
        return default
    if dec <= 0:
        return default
    return max(0, -dec.normalize().as_tuple().exponent)


# Logo CDN fallback
_LOGO_CDN = "https://assets.coingecko.com/coins/images/{id}/small/{symbol}.png"
_LOGO_FALLBACK = "https://www.cryptocompare.com/media/img/cc_icons/{symbol}.png"


# ---------------------------------------------------------------------------
# Retry decorator for transient failures
# ---------------------------------------------------------------------------
def _with_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Bind :func:`src.core.retry.with_retry` to this module's logger.

    Keeps the retry warning on the ``acervator.exchange`` logger.
    """
    return with_retry(max_retries=max_retries, base_delay=base_delay, log=logger)


# ---------------------------------------------------------------------------
# CCXT connector
# ---------------------------------------------------------------------------
class CCXTConnector(ExchangeInterface):
    """
    Production exchange connector built on ``ccxt.async_support``.

    Usage::

        conn = CCXTConnector("binance")
        await conn.connect(api_key="...", api_secret="...")
        ticker = await conn.get_ticker("BTC/USDT")
        await conn.disconnect()
    """

    def __init__(self, exchange_id: str) -> None:
        if exchange_id not in SUPPORTED_EXCHANGES:
            raise ValueError(
                f"Unsupported exchange '{exchange_id}'. "
                f"Supported: {list(SUPPORTED_EXCHANGES.keys())}"
            )
        self._exchange_id = exchange_id
        self._ccxt_id = SUPPORTED_EXCHANGES[exchange_id]
        # Non-None only when a backend is attached (Simulator / Paper).
        # Live never sets it, so `_ex` resolves exactly as before.
        self._injected_ex: Any = None
        self._ccxt: Any = None  # ccxt.async_support exchange instance
        self._ccxt_sync: Any = None  # ccxt (sync) exchange instance
        self._connected = False
        self._markets_cache: list[AssetInfo] | None = None
        self._last_request_time: float = 0.0
        self._min_request_interval: float = 0.1  # 100ms default rate limit

        # MEM-218 (Session 24, 2026-04-22) — trade-historian attributes.
        # These three were missing from __init__ but referenced from
        # _scan_trade_history (background thread spawned on every
        # successful sync_connect) and _on_history_result (fires as
        # each symbol's scan completes). An uninitialised set()/dict
        # causes AttributeError on first access from that thread,
        # which the MEM-216 threading.excepthook surfaced in the
        # operator's 2026-04-22 23:47:48 session:
        #   UNCAUGHT EXCEPTION in thread trade-historian:
        #   AttributeError: 'CCXTConnector' object has no attribute
        #   '_scan_symbols'
        # Initialising them here means the background thread can
        # run cleanly (or exit early if no symbols registered) and
        # the history callback branch is a no-op until set.
        self._scan_symbols: set[str] = set()
        self._history_analyses: dict = {}
        self._on_history_ready: Optional[HistoryCallback] = None

        # MEM-220 (Session 24, 2026-04-22) — serialization for sync CCXT.
        # Single-worker executor means all sync CCXT calls serialize
        # through one thread, eliminating the urllib3/OpenSSL race
        # that was producing Windows access violations. See module
        # docstring and test_mem220 for full context.
        self._sync_executor: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"ccxt-{exchange_id}",
        )
        # Tracks in-flight + queued calls for cap enforcement.
        # Incremented BEFORE submit, decremented in finally regardless
        # of outcome. Accessed from the asyncio loop thread only.
        self._sync_queue_depth: int = 0
        # Lock only needed because disconnect() may run on a different
        # thread than _call_sync. Not hot-path (~never contended).
        self._sync_executor_lock = threading.Lock()
        # v3.24.95 — serialises history scans. `add_scan_symbol`
        # spawns one daemon thread per symbol; without this they
        # all fetch at once.
        self._history_scan_lock = threading.Lock()

    # -- Properties -----------------------------------------------------
    @property
    def exchange_id(self) -> str:
        return self._exchange_id

    @property
    def display_name(self) -> str:
        return self._exchange_id.capitalize()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # -- Connection lifecycle -------------------------------------------
    async def connect(
        self, api_key: str, api_secret: str, passphrase: str = ""
    ) -> None:
        """Connect without holding the calling thread.

        ``sync_connect`` is synchronous by design and by name, and its
        contract is unchanged: :mod:`src.exchange.api_validator` calls it
        directly and legitimately wants a blocking connect.

        What was wrong here is that this coroutine *awaited nothing*.  It
        called ``sync_connect`` inline, so awaiting it never yielded and
        the caller's thread sat inside the entire connect.  Every
        coroutine in this application runs on the Qt GUI thread (see the
        pump timer in ``main.py``), so that is a frozen window.

        THREE calls inside ``sync_connect`` block, not one:

            the pre-flight ``safe_urlopen(..., timeout=15)``  up to  15 s
            ``sync_exchange.load_markets()``                  up to  30 s
                                                             x 3 attempts
            ``time.sleep(2 * (attempt + 1))`` between attempts    2 s + 4 s

        Worst case is therefore about 111 s, and wrapping only
        ``load_markets`` would leave roughly 21 s of it on the caller.
        The whole call moves instead, its body untouched.

        The mechanism is this file's own, taken from :meth:`_call_sync`:
        the single-worker ``_sync_executor`` plus ``run_in_executor``
        with ``functools.partial``.  Reusing that executor is deliberate,
        not incidental — MEM-220 exists because concurrent sync CCXT
        calls on one instance produced Windows access violations, and
        routing connect through the same one-worker queue keeps that
        serialization true while a connect is in flight.

        It deliberately does NOT route through :meth:`_call_sync`, whose
        ``MEM_220_CALL_TIMEOUT_SEC`` is 25 s: a legitimate three-attempt
        connect runs far longer than that, so borrowing the timeout would
        turn a slow connect into a spurious ``TimeoutError``.  For the
        same reason ``_sync_queue_depth`` is left alone — that counter is
        cap accounting for ``_call_sync`` alone.

        Exceptions are unchanged.  ``run_in_executor`` re-raises whatever
        ``sync_connect`` raised, in the awaiting coroutine.
        """
        # Grab the executor under the lock, exactly as `_call_sync`
        # does, so a `disconnect()` on another thread cannot shut it
        # down between the check and the submit.
        with self._sync_executor_lock:
            executor = self._sync_executor
            if executor is None:
                raise RuntimeError(
                    f"CCXTConnector({self._exchange_id}) has been "
                    f"disconnected; cannot open a new connection."
                )

        import functools

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            executor,
            functools.partial(self.sync_connect, api_key, api_secret, passphrase),
        )

    def sync_connect(
        self,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
    ) -> None:
        """Connect using SYNCHRONOUS CCXT (uses requests, not aiohttp).

        This avoids Windows asyncio ProactorEventLoop incompatibilities
        with aiohttp that cause silent connection failures.
        """
        if self._injected_ex is not None:
            # A backend is serving this connector; there is no network
            # session to open and no credentials to consume.
            self._connected = True
            return
        try:
            import ccxt as ccxt_sync
        except ImportError:
            raise ImportError(
                "The 'ccxt' package is required. Install via: "
                "pip install ccxt --break-system-packages"
            )

        exchange_class = resolve_ccxt_class(ccxt_sync, self._ccxt_id)
        if exchange_class is None:
            raise ValueError(f"CCXT does not have class '{self._ccxt_id}'")

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": 30000,
            "options": {"defaultType": "spot"},
        }

        _log = get_api_log()

        # --- Coinbase CDP key PEM newline fix ---
        if self._exchange_id == "coinbase" and api_secret:
            if "\\n" in api_secret:
                api_secret = api_secret.replace("\\n", "\n")
                config["secret"] = api_secret
            if "BEGIN EC PRIVATE KEY" in api_secret and "\n" not in api_secret.strip():
                api_secret = api_secret.replace(
                    "-----BEGIN EC PRIVATE KEY-----", "-----BEGIN EC PRIVATE KEY-----\n"
                )
                api_secret = api_secret.replace(
                    "-----END EC PRIVATE KEY-----", "\n-----END EC PRIVATE KEY-----\n"
                )
                config["secret"] = api_secret

            is_cdp = api_key.startswith("organizations/")
            # sadp: R28 — TD-013: do NOT log key prefix. Last-4 only, banking convention.
            _key_tail = api_key[-4:] if len(api_key) >= 4 else "****"
            _log.record(
                exchange=self._exchange_id,
                action="KEY_TYPE_DETECTED",
                reason=f"{'CDP (JWT/ECDSA)' if is_cdp else 'Legacy (HMAC)'} API key format",
                result=f"Key ...{_key_tail} (prefix redacted per TD-013)",
                level="info",
                data_usage="CDP keys use JWT auth with EC signing. Legacy keys use HMAC-SHA256.",
            )

        # --- Apply exchange-specific options ---
        exch_opts = EXCHANGE_OPTIONS.get(self._exchange_id)
        if exch_opts:
            config["options"].update(exch_opts)

        # --- Passphrase ---
        if self._exchange_id in PASSPHRASE_EXCHANGES:
            if not passphrase:
                raise ValueError(
                    f"{self.display_name} requires an API passphrase. "
                    f"This is set when you create the API key on the exchange."
                )
            config["password"] = passphrase

        # --- US restriction warning ---
        if self._exchange_id in US_RESTRICTED_EXCHANGES:
            _log.record(
                exchange=self._exchange_id,
                action="US_RESTRICTION_WARNING",
                reason=f"{self.display_name} may restrict US-based users",
                result="Proceeding with connection attempt. If it fails with 403/Forbidden, "
                "this exchange does not serve your region.",
                level="warning",
                data_usage="Check exchange terms of service for your region.",
            )

        # --- Pre-flight connectivity check ---
        preflight_url = PREFLIGHT_URLS.get(self._exchange_id)
        if preflight_url:
            _log.record(
                exchange=self._exchange_id,
                action="PREFLIGHT_CHECK",
                reason=f"Testing connectivity to {preflight_url}",
                result="Checking...",
                level="info",
                data_usage="Direct HTTP request to verify endpoint is reachable",
            )
            import ssl as _ssl

            try:
                ssl_ctx = _ssl.create_default_context()
                try:
                    import certifi

                    ssl_ctx = _ssl.create_default_context(cafile=certifi.where())
                except ImportError:
                    pass
                req = SafeRequest(preflight_url)
                req.add_header("User-Agent", "Acervator/1.8")
                req.add_header("Accept", "application/json")
                start = time.monotonic()
                with safe_urlopen(req, timeout=15, context=ssl_ctx) as resp:
                    elapsed = (time.monotonic() - start) * 1000
                    _log.record(
                        exchange=self._exchange_id,
                        action="PREFLIGHT_OK",
                        reason=f"HTTP {resp.status} from {preflight_url}",
                        result=f"Endpoint reachable ({elapsed:.0f}ms)",
                        elapsed_ms=elapsed,
                        level="success",
                        data_usage="Pre-flight passed. Proceeding with CCXT.",
                    )
            except Exception as pf_exc:
                _log.record(
                    exchange=self._exchange_id,
                    action="PREFLIGHT_FAILED",
                    reason=f"Cannot reach {preflight_url}",
                    result=f"{type(pf_exc).__name__}: {pf_exc}",
                    level="error",
                    data_usage="Network/SSL issue. Check firewall and internet connection.",
                )
                raise ConnectionError(
                    f"Cannot reach {self._exchange_id} API. "
                    f"Pre-flight check failed: {type(pf_exc).__name__}: {pf_exc} | "
                    f"URL: {preflight_url}"
                )

        # --- Create SYNC CCXT exchange and load markets ---
        _log.record(
            exchange=self._exchange_id,
            action="CONNECTING",
            reason="Creating synchronous CCXT connection",
            endpoint="load_markets",
            params={"exchange": self._exchange_id},
            result="Connecting...",
            level="info",
            data_usage="Sync CCXT (requests library, not aiohttp)",
        )

        sync_exchange = exchange_class(config)

        # Disable fetchCurrencies for exchanges with deprecated endpoints
        if self._exchange_id in DISABLE_FETCH_CURRENCIES:
            sync_exchange.has["fetchCurrencies"] = False

        attempt_count = 0

        def _load_markets_once() -> None:
            nonlocal attempt_count
            attempt_count += 1
            start = time.monotonic()
            sync_exchange.load_markets()
            elapsed = (time.monotonic() - start) * 1000
            market_count = len(sync_exchange.markets) if sync_exchange.markets else 0
            self._connected = True
            self._ccxt_sync = sync_exchange

            # Prepare async exchange for trading loop (shares loaded markets)
            try:
                import ccxt.async_support as ccxt_async

                async_class = resolve_ccxt_class(ccxt_async, self._ccxt_id)
                if async_class is None:
                    raise RuntimeError(f"CCXT async has no class for '{self._ccxt_id}'")
                self._ccxt = async_class(config)
                if self._exchange_id in DISABLE_FETCH_CURRENCIES:
                    self._ccxt.has["fetchCurrencies"] = False
                self._ccxt.markets = sync_exchange.markets
                self._ccxt.markets_by_id = sync_exchange.markets_by_id
                self._ccxt.currencies = sync_exchange.currencies
                self._ccxt.symbols = sync_exchange.symbols
            except (
                Exception
            ):  # R28-OK: field-copy fallback; whole exchange swap is the recovery
                self._ccxt = sync_exchange

            _log.record(
                exchange=self._exchange_id,
                action="CONNECTED",
                reason="Markets loaded successfully",
                endpoint="load_markets",
                params={"attempt": attempt_count},
                result=f"Connected to {self.display_name}. {market_count} trading pairs.",
                elapsed_ms=elapsed,
                level="success",
                data_usage="Market metadata cached for trading.",
            )
            logger.info("Connected to %s (%d markets)", self.display_name, market_count)

            # ── Trade history scan on connect (R29 — idempotent) ──────
            # Runs in a background thread so it never delays GUI startup.
            # Results are stored in self._history_analyses and reported
            # via self._on_history_ready callback if set.
            import threading

            threading.Thread(
                target=self._scan_trade_history,
                daemon=True,
                name="trade-historian",
            ).start()

        def _note_load_failure(
            exc: BaseException, attempt: int, will_retry: bool, delay: float
        ) -> None:
            del delay
            _log.record(
                exchange=self._exchange_id,
                action="CONNECT_RETRY",
                reason=f"Attempt {attempt + 1}/{CONNECT_ATTEMPTS} failed",
                endpoint="load_markets",
                params={"attempt": attempt + 1},
                result=self._format_exchange_error(exc),
                level="warning" if will_retry else "error",
                data_usage=("Retrying..." if will_retry else "All attempts exhausted"),
            )

        try:
            retry_sync(
                _load_markets_once,
                attempts=CONNECT_ATTEMPTS,
                delay_for=linear_delay(CONNECT_BACKOFF_STEP_S),
                is_retryable=retry_any,
                on_failure=_note_load_failure,
            )
        except Exception as exc:
            # `from None` keeps the operator-facing traceback single-frame,
            # as it was when the loop fell through to this raise.
            raise ConnectionError(self._format_exchange_error(exc)) from None

    # ── MEM-220: Sync CCXT serialization ────────────────────────────────────

    async def _call_sync(self, fn, *args, **kwargs):
        """Single choke point for all sync CCXT calls.

        All ``self._ex.fetch_*`` / ``self._ex.create_*`` / etc. MUST go
        through this method.  Rationale:

        1.  CCXT's sync methods are not thread-safe.  Multiple concurrent
            callers against the same sync instance produced Windows
            access violations in urllib3 / OpenSSL C code.
        2.  The per-connector single-worker ``_sync_executor`` guarantees
            serialization without adding an explicit lock around each
            caller (locks around blocking I/O cause other bugs).
        3.  The queue-depth cap (``MEM_220_QUEUE_CAP``) is fail-fast
            backpressure: if the 2-second dashboard timer + bot ticks
            ever produce a backlog, we reject further submissions
            with :class:`CCXTQueueFullError` rather than letting
            calls queue unboundedly.
        4.  ``wait_for`` enforces an outer timeout slightly above
            CCXT's own (20s default).  Normal case: CCXT times out
            first, worker finishes cleanly.  Pathological case: our
            outer timeout fires, awaiter sees TimeoutError, worker
            thread leaks for up to a few more seconds until CCXT
            finishes on its own.  Leaks are logged.

        Raises:
            CCXTQueueFullError: queue is at cap; caller should retry later.
            TimeoutError: the call exceeded MEM_220_CALL_TIMEOUT_SEC.
            asyncio.CancelledError: awaiter was cancelled (app shutdown,
                caller gave up).  The worker thread continues running
                in the background; its result is discarded.
            Any CCXT exception: propagated unchanged.
        """
        # Queue depth check.  No lock needed — we only read/write from
        # the asyncio loop thread.  Fail-fast semantics.
        if self._sync_queue_depth >= MEM_220_QUEUE_CAP:
            raise CCXTQueueFullError(
                f"CCXT call queue at capacity ({self._sync_queue_depth}/"
                f"{MEM_220_QUEUE_CAP}) for {self._exchange_id}; "
                f"exchange is likely rate-limited or network is degraded. "
                f"Call: {getattr(fn, '__name__', repr(fn))}"
            )

        # Grab executor under lock so a disconnect() on another thread
        # cannot shutdown() the executor between our check and submit().
        with self._sync_executor_lock:
            executor = self._sync_executor
            if executor is None:
                raise RuntimeError(
                    f"CCXTConnector({self._exchange_id}) has been disconnected; "
                    f"cannot submit new sync calls."
                )

        self._sync_queue_depth += 1
        try:
            loop = asyncio.get_event_loop()
            # Submit to single-worker executor → serialized by construction
            if kwargs:
                # run_in_executor doesn't accept kwargs — wrap in functools.partial
                import functools

                fut = loop.run_in_executor(
                    executor, functools.partial(fn, *args, **kwargs)
                )
            else:
                fut = loop.run_in_executor(executor, fn, *args)

            try:
                result = await asyncio.wait_for(fut, timeout=MEM_220_CALL_TIMEOUT_SEC)
                return result
            except asyncio.TimeoutError:
                # CCXT should have timed out first; our outer timeout
                # only fires if CCXT's timeout logic is broken or the
                # underlying syscall is stuck in C code.  Worker thread
                # leaks — log so we know.
                logger.warning(
                    "MEM-220: sync CCXT call exceeded outer timeout "
                    "(%ss) for %s on %s; worker thread is leaked until "
                    "CCXT's own timeout fires",
                    MEM_220_CALL_TIMEOUT_SEC,
                    getattr(fn, "__name__", repr(fn)),
                    self._exchange_id,
                )
                raise
            except asyncio.CancelledError:
                # Awaiter cancelled (e.g., app shutdown).  Worker keeps
                # running until CCXT returns; we don't try to stop it.
                # This is the correct behaviour — abandoning a HTTP
                # request mid-flight would leave connection state
                # inconsistent.
                raise
        finally:
            self._sync_queue_depth = max(0, self._sync_queue_depth - 1)

    # ── Trade history scanning ───────────────────────────────────────────────

    def set_history_callback(self, callback: HistoryCallback) -> None:
        """
        Register a callback that receives (symbol, HistoryAnalysis) as
        each symbol's history scan completes.  Called from the background
        thread — use Qt signals if updating the GUI from this callback.
        """
        self._on_history_ready = callback

    def _scan_trade_history(self, symbols=None) -> None:
        """
        Background thread entry point.  Called automatically after every
        successful connect / reconnect.

        Scans all active symbols (derived from loaded markets and any
        bots currently running).  Safe to call multiple times (R29).
        """
        if not self._ccxt_sync:
            return

        # Collect symbols to scan — use BATTERY_ASSETS as a fallback set
        # when no bots are running yet.  In production the BotManager will
        # add its active symbols via add_scan_symbol().
        # v3.24.95 - SYMBOLS COME IN AS AN ARGUMENT, NOT VIA THE FIELD.
        #
        # `refresh_history(symbol)` used to do this:
        #     orig = self._scan_symbols.copy()
        #     self._scan_symbols = {symbol}
        #     self._scan_trade_history()
        #     self._scan_symbols = orig
        # and `add_scan_symbol` calls it in a DAEMON THREAD PER SYMBOL.
        #
        # 37 threads racing on one mutable set: each replaced it, and
        # this method then iterated whatever happened to be there --
        # frequently another thread's restored snapshot of every symbol.
        # Each thread therefore scanned up to N symbols instead of 1.
        #
        # MEASURED on the operator's 3.24.94 launch: 37 distinct symbols,
        # 1,294 scans, exactly 35.0 per symbol where 1 is correct. N^2
        # for N=37 is 1,369. 200 fetches in the first 24 seconds, no
        # pacing, so Coinbase rate-limited and 1,708 fetch failures were
        # logged as TradeHistorian errors.
        #
        # Passing the list in removes the shared mutable state, and with
        # it the race.
        symbols = (
            [str(x) for x in symbols]
            if symbols is not None
            else (list(self._scan_symbols) if self._scan_symbols else [])
        )
        if not symbols:
            logger.info("TradeHistorian: no symbols registered — skipping auto-scan")
            return

        logger.info(
            "TradeHistorian: starting post-connect history scan "
            "for %d symbol(s): %s",
            len(symbols),
            symbols,
        )
        # v3.24.95 - SERIALISED AND PACED.
        #
        # `TradeHistorian._fetch_sync` calls the RAW ccxt object, so it
        # bypasses this connector's `_rate_limit()`, its single-worker
        # `_call_sync` executor and its retry decorator -- every guard
        # built to keep this exchange happy. Concurrent daemon threads
        # then hit it with no spacing at all.
        #
        # The lock makes concurrent scans queue instead of pile up; the
        # pace is the connector's own configured interval, so history
        # fetches obey the same limit as every other call.
        with self._history_scan_lock:
            try:
                # 10.3 phase 2 — BRACKET THE SCAN, NOT THE QUEUEING.
                #
                # The timer starts INSIDE `_history_scan_lock` on purpose.
                # That lock makes concurrent scans queue rather than pile
                # up, so a caller can wait a long time before its own scan
                # begins. Starting the clock before the `with` would fold
                # lock-wait and fetch time into one number, and a reader
                # could no longer tell "the venue was slow" from "this
                # scan waited its turn" -- two different causes behind one
                # value, which is the disjunction defect this repo has
                # been bitten by before.
                #
                # So this measures what `scan_complete` actually observes:
                # the scan. Queue depth, if it is ever wanted, is a
                # separate observation and would be its own emitter.
                _dur_t0 = time.monotonic()
                results = scan_on_connect(
                    exchange=self._ccxt_sync,
                    symbols=symbols,
                    on_result=self._on_history_result,
                    pace_s=float(getattr(self, "_min_request_interval", 0.1) or 0.0),
                )
                _dur_elapsed = time.monotonic() - _dur_t0
                self._history_analyses.update(results)
                logger.info(
                    "TradeHistorian: scan complete — %d symbol(s) analysed",
                    len(results),
                )
                try:
                    from src.core.signal_contract import emit as _hs_emit

                    _hs_emit(
                        "history.05.001.postcondition.scan_complete",
                        actual=len(results),
                        expected=len(symbols),
                        duration=_dur_elapsed,
                        context={"symbols": len(symbols)},
                    )
                except Exception:  # noqa: BLE001,S110 - advisory
                    pass
            except Exception as e:
                # R28: fail loudly — log at ERROR, do not swallow
                logger.error("TradeHistorian: scan failed: %s", e)

    def _on_history_result(
        self,
        symbol: str,
        analysis: HistoryAnalysis,
    ) -> None:
        """Called by scan_on_connect for each symbol as it completes."""
        self._history_analyses[symbol] = analysis
        if self._on_history_ready:
            try:
                self._on_history_ready(symbol, analysis)
            except Exception as e:
                logger.warning("history callback error: %s", e)

    def add_scan_symbol(self, symbol: str):
        """Register a symbol to be included in the next history scan.

        MEM-248 (Session 26 operator report): Trade Historian was silently
        skipping every post-connect bot. Order-of-ops bug: connector connects
        -> _scan_trade_history runs with empty _scan_symbols -> logs 'no
        symbols registered — skipping' -> nothing ever re-scans when bots
        register later. Fix: if we're already connected when a new symbol is
        registered, kick off a targeted scan for JUST that symbol. Cheap
        (one symbol's history ~1 API call + analysis) and restores the
        advertised Trade Historian behavior.
        """
        if symbol in self._scan_symbols:
            return  # idempotent — already registered
        self._scan_symbols.add(symbol)
        # Post-connect late registration: spawn a targeted scan for this
        # symbol immediately so the GUI surfaces trade history without
        # waiting for the next connect/reconnect.
        if self._ccxt_sync is not None:
            try:
                import threading

                threading.Thread(
                    target=self.refresh_history,
                    kwargs={"symbol": symbol},
                    daemon=True,
                    name=f"trade-historian-late-{symbol}",
                ).start()
                logger.info(
                    "TradeHistorian: late registration for %s — "
                    "spawning targeted scan in background",
                    symbol,
                )
            except Exception as exc:  # sadp: R28 — surface
                logger.warning(
                    "TradeHistorian: late-scan spawn failed for %s: %s", symbol, exc
                )

    def remove_scan_symbol(self, symbol: str):
        self._scan_symbols.discard(symbol)

    def get_history(self, symbol: str) -> HistoryAnalysis | None:
        """Return the most recent history analysis for a symbol."""
        return self._history_analyses.get(symbol)

    def refresh_history(self, symbol: str | None = None):
        """
        Trigger a fresh history scan.  If symbol is None, re-scans all
        registered symbols.  Safe to call from GUI 'Refresh' button.
        """
        # v3.24.95 — pass it down instead of swapping the field out
        # from under 36 other threads. See `_scan_trade_history`.
        if symbol:
            self._scan_trade_history(symbols=[symbol])
        else:
            self._scan_trade_history()

    @staticmethod
    def _format_exchange_error(exc: Exception) -> str:
        """Extract every available detail from a CCXT exception."""
        parts = [f"{type(exc).__name__}: {exc}"]

        # CCXT exceptions carry HTTP details under various attribute names
        # depending on the version. Try all known ones.
        http_code = None
        for attr in ("http_status", "http_code", "status_code", "code"):
            val = getattr(exc, attr, None)
            if val is not None:
                http_code = val
                parts.append(f"HTTP Status: {val}")
                break

        url = getattr(exc, "url", None)
        if url:
            parts.append(f"URL: {url}")

        method = getattr(exc, "method", None)
        if method:
            parts.append(f"Method: {method}")

        # Raw response body - the actual server reply
        body = None
        for attr in ("http_response", "body", "response_body", "message"):
            val = getattr(exc, attr, None)
            if val and isinstance(val, str) and val != str(exc):
                body = val[:500]
                break

        # Parsed JSON response
        parsed = getattr(exc, "response", None)
        if parsed and isinstance(parsed, dict):
            import json

            body = json.dumps(parsed, indent=2)[:500]

        if body:
            parts.append(f"Response Body: {body}")

        # Build diagnosis from actual data
        exc_name = type(exc).__name__
        exc_str = str(exc)
        code = http_code or ""
        code_str = str(code)

        if "ExchangeNotAvailable" in exc_name:
            if (
                code_str.startswith("5")
                or "503" in exc_str
                or "502" in exc_str
                or "500" in exc_str
            ):
                parts.append(
                    f"DIAGNOSIS: Server error (HTTP {code or '5xx'}). Exchange is likely under maintenance."
                )
            elif code_str == "403" or "403" in exc_str:
                parts.append(
                    "DIAGNOSIS: HTTP 403 Forbidden. Your API key may lack permissions, or your IP may be blocked by the exchange."
                )
            elif code_str == "429" or "429" in exc_str:
                parts.append(
                    "DIAGNOSIS: HTTP 429 Rate Limited. Too many requests. Wait 60 seconds."
                )
            elif code_str == "401" or "401" in exc_str:
                parts.append(
                    "DIAGNOSIS: HTTP 401 Unauthorized. API credentials are invalid or expired."
                )
            elif "cloudflare" in exc_str.lower() or "ddos" in exc_str.lower():
                parts.append(
                    "DIAGNOSIS: DDoS protection triggered. Wait 30 seconds and retry."
                )
            elif not code:
                parts.append(
                    "DIAGNOSIS: No HTTP status received. Likely causes: "
                    "DNS resolution failure, network timeout, firewall blocking outbound HTTPS, "
                    "or the exchange domain is unreachable from your network. "
                    "Try: 1) Open https://api.coinbase.com in a browser to verify connectivity. "
                    "2) Check if a VPN or corporate firewall is active. "
                    "3) Try again in 60 seconds (transient outage)."
                )
            else:
                parts.append(
                    f"DIAGNOSIS: HTTP {code}. Unexpected status. Check Response Body above for details."
                )
        elif "AuthenticationError" in exc_name:
            parts.append(
                "DIAGNOSIS: API credentials rejected. Verify key, secret, and passphrase. Ensure trading permissions are enabled on the exchange website."
            )
        elif "RateLimitExceeded" in exc_name or "429" in exc_str:
            parts.append("DIAGNOSIS: Rate limited. Application will retry after delay.")
        elif "NetworkError" in exc_name or "Timeout" in exc_name:
            parts.append(
                "DIAGNOSIS: Network connectivity issue. Check internet connection and firewall."
            )
        elif "PermissionDenied" in exc_name or "403" in exc_str:
            parts.append("DIAGNOSIS: API key lacks required permissions.")
        elif "BadRequest" in exc_name or "400" in exc_str:
            parts.append(
                "DIAGNOSIS: Malformed request. May indicate CCXT version mismatch. Try: pip install ccxt --upgrade"
            )

        return " | ".join(parts)

    async def disconnect(self) -> None:
        if self._ccxt:
            await self._ccxt.close()
            self._ccxt = None
        self._connected = False
        self._markets_cache = None

        # MEM-220: tear down the single-worker sync executor under lock.
        # Any _call_sync in flight will either already have submitted
        # (its worker runs to completion) or will see None and raise
        # RuntimeError cleanly.  wait=True ensures worker cleanup
        # before we return — matters for tests and clean shutdown.
        with self._sync_executor_lock:
            executor = self._sync_executor
            self._sync_executor = None
        if executor is not None:
            try:
                executor.shutdown(wait=True)
            except Exception as exc:
                logger.warning("MEM-220: sync executor shutdown failed: %s", exc)
        logger.info("Disconnected from %s", self.display_name)

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError(f"Not connected to {self.display_name}")
        # v3.24.84 — resolve through `_ex`, the single point that knows
        # about an attached backend. Reading `_ccxt_sync`/`_ccxt`
        # directly bypassed the injection and rejected every call on a
        # backend-served connector, which is the same class of bug as a
        # guard that verifies its own path instead of the property.
        if self._ex is None:
            raise RuntimeError(f"No exchange instance for {self.display_name}")

    @property
    def _ex(self):
        """Return the best available exchange instance (sync preferred).

        v3.24.84 — SINGLE INJECTION POINT FOR A NON-CCXT BACKEND.

        Operator directive 2026-08-09: the Simulator must process Stone
        Tablet and YTD data "in the exact same manner that Live Mode
        processes API pulls from the exchange... just a different data
        source."

        Previously the Simulator satisfied that by RE-IMPLEMENTING this
        connector — `FleetSimExchange` carried its own ticker, balance
        ledger, order settlement, market metadata and fee arithmetic. Two
        implementations of one behaviour cannot be kept in agreement:
        a seam-by-seam audit found 16 divergences on the fields the bot
        actually reads, and each one fixed only reopens when live moves.

        The seam belongs BELOW this class, not beside it. Everything in
        `CCXTConnector` — normalisation, fee reading, Order and Trade
        construction, and the documented ccxt quirks the bots have been
        calibrated against — now runs unmodified against tablets, because
        the only thing that changes is the object this property returns.

        Live is untouched: with nothing injected this is the original
        expression, evaluated in the original order.
        """
        injected = getattr(self, "_injected_ex", None)
        if injected is not None:
            return injected
        return getattr(self, "_ccxt_sync", None) or self._ccxt

    def attach_backend(self, backend: Any) -> None:
        """Serve every ccxt call from *backend* instead of the network.

        `backend` must implement the ccxt surface this connector
        actually uses — the 14 members reached through `self._ex`:
        fetch_ohlcv, fetch_ticker, fetch_tickers, fetch_balance,
        create_order, cancel_order, fetch_order, fetch_open_orders,
        fetch_my_trades, fetch_order_book, markets, market,
        amount_to_precision, price_to_precision.

        Marks the connector connected: there is no network handshake to
        perform, and every read path guards on `_ensure_connected`.
        """
        self._injected_ex = backend
        self._connected = True
        # NO NETWORK, SO NO RATE LIMIT.
        #
        # `_min_request_interval` is 0.1s, enforced by `_rate_limit()`
        # before every call, because Coinbase will throttle a caller
        # that goes faster. A Stone Tablet will not.
        #
        # MEASURED before this line existed: 107 ms per call, 5,942x
        # slower than the exchange it replaces. A 35-bot / 15,000-candle
        # replay would have spent ~31 HOURS asleep in the rate limiter.
        #
        # This changes no computed value. The replay's clock is the
        # tape's timestamps, not wall time, so every price, indicator
        # and gate decision is identical -- only the waiting is gone.
        self._min_request_interval = 0.0

    # -- Rate limiting --------------------------------------------------
    async def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.monotonic()

    # -- Market data (all methods use sync CCXT via self._call_sync) ----
    @_with_retry()
    async def get_ticker(self, symbol: str) -> Ticker:
        self._ensure_connected()
        await self._rate_limit()
        _log = get_api_log()
        start = time.monotonic()
        raw = await self._call_sync(self._ex.fetch_ticker, symbol)
        elapsed = (time.monotonic() - start) * 1000
        ticker = Ticker(
            symbol=symbol,
            bid=float(raw.get("bid", 0) or 0),
            ask=float(raw.get("ask", 0) or 0),
            last=float(raw.get("last", 0) or 0),
            volume_24h=float(raw.get("quoteVolume", 0) or 0),
            timestamp=float(raw.get("timestamp", 0) or 0) / 1000,
        )
        _log.record(
            exchange=self._exchange_id,
            action="FETCH_TICKER",
            reason=f"Get current price for {symbol}",
            endpoint="fetch_ticker",
            params={"symbol": symbol},
            result=f"last={fmt_price_coerced(ticker.last)} bid={fmt_price_coerced(ticker.bid)} ask={fmt_price_coerced(ticker.ask)} vol24h={ticker.volume_24h:.0f}",
            elapsed_ms=elapsed,
            level="success",
            data_usage="Used by bots for delta calculation, grid level checks, and P/L computation",
        )
        return ticker

    async def get_all_tickers(self) -> dict:
        """Fetch all tickers for this exchange in one bulk call.

        MEM-220: previously market_map.py reached directly into
        ``connector._ex.fetch_tickers()`` which bypassed the
        serialization executor.  This method exists so external
        callers have an API boundary and all sync CCXT traffic
        goes through ``_call_sync``.

        Returns the raw CCXT tickers dict (symbol → ticker info).
        Does not normalise into ``Ticker`` dataclasses — callers
        (market_map) need the raw 24h percentage data that
        ``Ticker`` doesn't model.
        """
        self._ensure_connected()
        await self._rate_limit()
        return await self._call_sync(self._ex.fetch_tickers)

    @_with_retry()
    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        self._ensure_connected()
        await self._rate_limit()
        raw = await self._call_sync(self._ex.fetch_order_book, symbol, limit)
        return OrderBook(
            symbol=symbol,
            bids=[(float(p), float(a)) for p, a in raw.get("bids", [])],
            asks=[(float(p), float(a)) for p, a in raw.get("asks", [])],
            timestamp=float(raw.get("timestamp", 0) or 0) / 1000,
        )

    @_with_retry()
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: Optional[int] = None,
    ) -> list[list[float]]:
        """Fetch OHLCV candles.

        ``since`` (epoch MILLISECONDS) was added v3.24.33 for the Stone
        Tablet auto-updater, which must ask for candles AFTER a known
        timestamp rather than "the most recent page". Without it the
        tablet fetcher raised TypeError on every call — see
        stone_tablets/fetcher.py.

        KNOWN DEFECT, DELIBERATELY NOT CHANGED HERE
        ===========================================
        The legacy call below passes ``limit`` as ccxt's THIRD
        positional argument, and ccxt's signature is::

            fetch_ohlcv(symbol, timeframe='1m', since=None, limit=None, ...)

        so ``limit`` has always landed in the ``since`` slot and the
        requested limit has never been applied on any live call — the
        exchange returns its own default page size instead (Coinbase:
        300). Every live caller (data_pool, chart_data,
        market_inspector_fetcher, phantom_balance) asks for a specific
        limit and silently gets that default.

        Fixing it is NOT a free correction: Heikin-Ashi is a forward
        recurrence seeded at index 0 (ta_engine.py:2522) and EMA is
        SMA-seeded, so feeding TA 100 candles instead of 300 changes
        indicator values and therefore live gate decisions. That is an
        operator-visible behaviour change and needs its own gated
        cascade, not a drive-by fix inside a tablet-updater task.

        So: when ``since`` is None the call is byte-identical to before,
        preserving live behaviour exactly. When ``since`` is supplied —
        only the tablet updater does — both arguments are passed in
        their correct slots.
        """
        self._ensure_connected()
        await self._rate_limit()
        _log = get_api_log()
        start = time.monotonic()
        if since is None:
            # Legacy path — unchanged, including the positional quirk
            # documented above. Live callers land here.
            data = await self._call_sync(self._ex.fetch_ohlcv, symbol, timeframe, limit)
        else:
            data = await self._call_sync(
                self._ex.fetch_ohlcv, symbol, timeframe, int(since), int(limit)
            )
        elapsed = (time.monotonic() - start) * 1000
        _log.record(
            exchange=self._exchange_id,
            action="FETCH_OHLCV",
            reason=f"Get {limit} candles ({timeframe}) for {symbol} - needed for TA indicator computation",
            endpoint="fetch_ohlcv",
            params={"symbol": symbol, "timeframe": timeframe, "limit": limit},
            result=(
                f"{len(data)} candles received, latest close={fmt_price_coerced(data[-1][4])}"
                if data
                else "No data"
            ),
            elapsed_ms=elapsed,
            level="success",
            data_usage="Fed into 7-indicator TA engine (BB, Vortex, MACD, StochRSI, Ichimoku, Volume, Slingshot) for voting",
        )
        return data

    # -- Account --------------------------------------------------------
    @_with_retry()
    async def get_balances(self) -> dict[str, Balance]:
        self._ensure_connected()
        await self._rate_limit()
        _log = get_api_log()
        start = time.monotonic()
        raw = await self._call_sync(self._ex.fetch_balance)
        elapsed = (time.monotonic() - start) * 1000
        result: dict[str, Balance] = {}
        for currency, info in raw.get("total", {}).items():
            total = float(info or 0)
            if total > 0:
                free = float(raw.get("free", {}).get(currency, 0) or 0)
                used = float(raw.get("used", {}).get(currency, 0) or 0)
                result[currency] = Balance(
                    currency=currency,
                    free=free,
                    used=used,
                    total=total,
                )
        bal_summary = ", ".join(
            f"{c}: {b.total:.6g}" for c, b in list(result.items())[:8]
        )
        _log.record(
            exchange=self._exchange_id,
            action="FETCH_BALANCES",
            reason="Retrieve account balances to verify funds and calculate position values",
            endpoint="fetch_balance",
            params={},
            result=f"{len(result)} assets with balance. {bal_summary}",
            elapsed_ms=elapsed,
            level="success",
            data_usage="Compared against bot target balances to determine available resources and P/L",
        )
        return result

    @_with_retry()
    async def get_balance(self, currency: str) -> Balance:
        # Distinguish "exchange said zero" from "exchange omitted this
        # currency from the response." The old code fabricated
        # Balance(free=0.0) for both cases. Defense-in-depth alongside the
        # MEM-259 VolumeGuard-disable fix for phantom-rebuy.
        balances = await self.get_balances()
        if currency in balances:
            return balances[currency]

        # get_balances filters out currencies with total <= 0, so a missing
        # key can mean EITHER "omitted" OR "present but zero". Re-check the
        # raw response to differentiate.
        self._ensure_connected()
        await self._rate_limit()
        raw = await self._call_sync(self._ex.fetch_balance)
        total_map = raw.get("total", {}) or {}
        if currency in total_map:
            # Exchange explicitly reported this currency, value was zero
            # (or a rounding-down to zero). Treat as a legitimate zero.
            return Balance(
                currency=currency, free=0.0, used=0.0, total=0.0, absent=False
            )

        # Currency not in raw response at all — the exchange did NOT
        # report it. Caller must decide whether to trust this as real.
        return Balance(currency=currency, free=0.0, used=0.0, total=0.0, absent=True)

    # -- Orders ---------------------------------------------------------
    # TD-014: NO @_with_retry on order submission. Rationale: create_order
    # is NOT idempotent on any exchange without a client_order_id. If the
    # exchange accepted the order but the response got lost (network flake,
    # 500 after accept), a naive retry books the SAME order again. Operator
    # ends up with 2-3x position. Fail-closed is the correct posture: on
    # any submission-path exception, halt and surface, let the caller (the
    # bot) decide whether to retry after reconciling exchange state.
    #
    # For true idempotent retry, callers can pass `client_order_id` and the
    # exchange-side dedup handles duplicate submissions (Binance:
    # newClientOrderId, Coinbase: client_order_id, Kraken: userref). When
    # retry idempotency is added, it must query exchange order history by
    # this id before resubmitting.
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Order:
        self._ensure_connected()
        await self._rate_limit()

        # v3.15.98 — TD-003 closure. Per-(exchange, symbol) circuit breaker
        # short-circuits during outages, preventing retry-storm rate-limit
        # depletion. Failure threshold + cooldown defaults are tuned for
        # spot trading; tighter thresholds for low-volume venues are an
        # operator-tunable next-session item.
        from .circuit_breaker import get_breaker_registry, CircuitBreakerOpenError

        _breaker_key = f"{self._exchange_id}:{symbol}"
        _breaker = get_breaker_registry().get(_breaker_key)
        if not _breaker.is_call_allowed():
            _breaker.record_short_circuit()
            raise CircuitBreakerOpenError(_breaker_key, _breaker.cooldown_remaining())
        _log = get_api_log()

        self._ex.market(symbol)
        amount = self._ex.amount_to_precision(symbol, amount)

        # Coinbase (and some other exchanges) require a price for market BUY
        # orders on spot to calculate total cost (amount * price).
        # If price is None for a market buy, fetch current price.
        exec_price = price
        if (
            order_type == OrderType.MARKET
            and side == OrderSide.BUY
            and exec_price is None
        ):
            try:
                ticker = await self._call_sync(self._ex.fetch_ticker, symbol)
                exec_price = float(ticker.get("last", 0) or ticker.get("ask", 0) or 0)
                if exec_price <= 0:
                    exec_price = None  # Fall back to no price
            except Exception:  # R28-OK: market-buy price probe; exchange handles None
                exec_price = None  # Exchange may not need it

        if exec_price is not None:
            exec_price = float(self._ex.price_to_precision(symbol, exec_price))

        _log.record(
            exchange=self._exchange_id,
            action="PLACE_ORDER",
            reason=f"Execute {side.value.upper()} {order_type.value} order for {symbol}",
            endpoint="create_order",
            params={
                "symbol": symbol,
                "side": side.value,
                "type": order_type.value,
                "amount": float(amount),
                "price": exec_price,
            },
            result="Sending to exchange...",
            elapsed_ms=0,
            level="info",
            data_usage="Order will be tracked for fill status; fills trigger profit folding or grid cycling",
        )

        # v3.16.12 FIX — operator-reported 2026-04-28: Coinbase rejected
        # `newClientOrderId` with proto-strict error:
        #   {"error":"unknown","error_details":"proto: (line 1:150):
        #    unknown field \"newClientOrderId\""}
        # The v3.15.98 idempotency layer set ALL common aliases assuming
        # CCXT would filter unknowns. Coinbase Advanced Trade is
        # protobuf-strict and rejects the order on unknown fields.
        # Pick the EXCHANGE-SPECIFIC field only.
        extra_params: dict = {}
        if client_order_id:
            _eid = (self._exchange_id or "").lower()
            if "coinbase" in _eid:
                # Coinbase Advanced Trade
                extra_params["client_order_id"] = client_order_id
            elif "binance" in _eid or "binanceus" in _eid:
                extra_params["newClientOrderId"] = client_order_id
            elif "kraken" in _eid:
                extra_params["userref"] = client_order_id
            else:
                # Default to ccxt canonical; CCXT translates per-exchange
                extra_params["clientOrderId"] = client_order_id

        # v3.23.28 — Translate IOC_LIMIT to ccxt's "limit" + timeInForce=IOC
        # since ccxt has no native ioc_limit type. The extra param travels
        # via extra_params so it flows through the create_order call below
        # regardless of the client_order_id branch.
        _ccxt_type = order_type.value
        if order_type == OrderType.IOC_LIMIT:
            _ccxt_type = "limit"
            extra_params["timeInForce"] = "IOC"

        start = time.monotonic()
        try:
            if extra_params:
                raw = await self._call_sync(
                    self._ex.create_order,
                    symbol,
                    _ccxt_type,
                    side.value,
                    float(amount),
                    exec_price,
                    extra_params,
                )
            else:
                raw = await self._call_sync(
                    self._ex.create_order,
                    symbol,
                    _ccxt_type,
                    side.value,
                    float(amount),
                    exec_price,
                )
        except Exception as _exc:
            # v3.15.98 — record failure with the breaker. The breaker will
            # OPEN after threshold consecutive failures; subsequent calls
            # short-circuit until cooldown.
            _breaker.record_failure(_exc)
            raise
        elapsed = (time.monotonic() - start) * 1000
        _breaker.record_success()  # Successful round-trip → reset failure run
        order = self._parse_order(raw)

        _log.record(
            exchange=self._exchange_id,
            action="ORDER_PLACED",
            reason=f"{side.value.upper()} order accepted by exchange",
            endpoint="create_order",
            params={"order_id": order.id},
            result=f"ID={order.id} status={order.status.value} filled={order.filled}/{float(amount)}",
            elapsed_ms=elapsed,
            level="success",
            data_usage="Order ID stored for fill monitoring. Bot will check status each tick cycle.",
        )
        return order

    @_with_retry()
    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        self._ensure_connected()
        await self._rate_limit()
        raw = await self._call_sync(self._ex.cancel_order, order_id, symbol)
        return self._parse_order(raw)

    @_with_retry()
    async def get_order(self, order_id: str, symbol: str) -> Order:
        self._ensure_connected()
        await self._rate_limit()
        raw = await self._call_sync(self._ex.fetch_order, order_id, symbol)
        return self._parse_order(raw)

    @_with_retry()
    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        self._ensure_connected()
        await self._rate_limit()
        raw_list = await self._call_sync(self._ex.fetch_open_orders, symbol)
        return [self._parse_order(r) for r in raw_list]

    # v3.16.46 — Trade history fetch for exchange-truth migration.
    # Operator directive 2026-05-10: position health data should be
    # exchange-pulled, not locally derived. This method exposes ccxt's
    # fetch_my_trades so the bot can compute avg_entry and realized
    # P/L from authoritative trade records instead of approximations
    # like ticker.last-at-init or internal accumulators.
    @_with_retry()
    async def get_my_trades(
        self,
        symbol: str,
        since: Optional[float] = None,
        limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list:
        """Fetch executed trades. Accepts an optional ``params`` dict
        that forwards to ccxt (per-exchange overrides). v3.23.57
        callers use ``params={'paginate': True}`` for automatic
        cursor-based multi-page fetch on exchanges like Coinbase
        Advanced Trade whose fills endpoint returns "most recent
        N within window" rather than oldest-first — our manual
        forward-cursor loop can't paginate that shape."""
        from .base import Trade, OrderSide

        self._ensure_connected()
        await self._rate_limit()
        # ccxt's `since` is millisecond unix; convert from seconds
        _since_ms = int(since * 1000) if since else None
        _params = params if params is not None else {}
        raw_list = await self._call_sync(
            self._ex.fetch_my_trades, symbol, _since_ms, limit, _params
        )
        result: list = []
        for r in raw_list or []:
            try:
                _side_str = str(r.get("side", "buy")).lower()
                _side = OrderSide.BUY if _side_str == "buy" else OrderSide.SELL
                _ts = float(r.get("timestamp", 0) or 0) / 1000.0
                _fee_dict = r.get("fee") or {}
                _fee_amt = float(_fee_dict.get("cost", 0) or 0)
                _fee_cur = str(_fee_dict.get("currency", "") or "")
                result.append(
                    Trade(
                        id=str(r.get("id", "") or ""),
                        symbol=str(r.get("symbol", symbol) or symbol),
                        side=_side,
                        amount=float(r.get("amount", 0) or 0),
                        price=float(r.get("price", 0) or 0),
                        fee=_fee_amt,
                        fee_currency=_fee_cur,
                        timestamp=_ts,
                        raw=r,
                    )
                )
            except (TypeError, ValueError, KeyError) as _exc:
                logger.warning(
                    "get_my_trades: skipping malformed trade %s: %s",
                    r.get("id", "?"),
                    _exc,
                )
                continue
        return result

    # -- Asset discovery ------------------------------------------------
    @_with_retry()
    async def get_markets(self) -> list[AssetInfo]:
        self._ensure_connected()
        if self._markets_cache is not None:
            return self._markets_cache

        markets = []
        precision_mode = getattr(self._ex, "precisionMode", CCXT_DECIMAL_PLACES)
        for sym, info in self._ex.markets.items():
            if not info.get("active", True):
                continue
            limits = info.get("limits", {})
            precision = info.get("precision", {})

            markets.append(
                AssetInfo(
                    symbol=sym,
                    base=info.get("base", ""),
                    quote=info.get("quote", ""),
                    min_amount=float(limits.get("amount", {}).get("min", 0) or 0),
                    min_cost=float(limits.get("cost", {}).get("min", 0) or 0),
                    price_precision=precision_to_decimals(
                        precision.get("price"), precision_mode
                    ),
                    amount_precision=precision_to_decimals(
                        precision.get("amount"), precision_mode
                    ),
                    maker_fee=float(info.get("maker", 0.001) or 0.001),
                    taker_fee=float(info.get("taker", 0.001) or 0.001),
                    active=info.get("active", True),
                )
            )
        self._markets_cache = markets
        return markets

    async def get_asset_logo_url(self, currency: str) -> str:
        """Return a CDN URL for the asset's logo."""
        return _LOGO_FALLBACK.format(symbol=currency.upper())

    # -- Helpers --------------------------------------------------------
    @staticmethod
    def _parse_order(raw: dict) -> Order:
        """Convert CCXT order dict to our Order dataclass.

        MEM-224 (2026-04-22): CCXT returns ``{"type": None}`` on Coinbase for
        market orders and certain advanced order configurations. The old
        pattern ``raw.get("type", "limit")`` returns ``None`` when the key
        exists with a ``None`` value — the default ONLY fires when the key
        is absent. ``OrderType(None)`` then throws ``ValueError: None is not
        a valid OrderType``.

        The exception was raised AFTER the order had been submitted via
        ``create_order``, so every trade that hit this path executed on the
        exchange but was reported upstream as a failure. Internal bot state
        (main_lots, _current_holdings, cost basis) was never updated; only
        the periodic ``_reconcile_holdings`` drift-detection caught the
        position changes 1-90 minutes later. Net result: the bot placed
        16+ invisible real-money trades on 2026-04-22 across RAVE and BONK.

        Fix: use ``or`` short-circuit so any falsy value (None, "") falls
        through to the documented safe default. Applied to side, type, and
        status for defence in depth (same pattern, same class of latent
        bug). Numeric fields already used ``or 0`` and are unaffected.
        """
        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "rejected": OrderStatus.FAILED,
        }
        fee_info = raw.get("fee") or {}
        # v3.24.xx — `average` was declared on the Order dataclass
        # (base.py:90) for exactly this purpose and then never populated
        # here. This is the ONLY place the connector builds an Order, so
        # `order.average` was 0.0 on every live order ever placed.
        #
        # Eleven call sites read it as the PRIMARY fill price --
        # scrumming_bot.py:2952/9334/9533/10042/10359,
        # extractor_bot.py:1043/1242/1402, volume_guard.py:493/530/584 --
        # and each has an `or` fallback to a reference or tick price, so
        # the omission never raised. It just meant every fill price
        # booked in live trading was an estimate. sim_exchange.py:440
        # DOES set it, so the simulator had real fill prices and live
        # never did.
        #
        # Fall back to cost/filled: CCXT populates `cost` (= filled x
        # average) on venues that omit `average` outright.
        _avg = raw.get("average")
        _filled = float(raw.get("filled", 0) or 0)
        if _avg in (None, "", 0) and _filled > 0:
            _cost = float(raw.get("cost", 0) or 0)
            _avg = (_cost / _filled) if _cost > 0 else 0.0
        return Order(
            id=str(raw.get("id") or ""),
            symbol=str(raw.get("symbol") or ""),
            side=OrderSide(raw.get("side") or "buy"),
            type=OrderType(raw.get("type") or "limit"),
            amount=float(raw.get("amount", 0) or 0),
            price=float(raw.get("price", 0) or 0),
            filled=_filled,
            remaining=float(raw.get("remaining", 0) or 0),
            status=status_map.get(raw.get("status") or "", OrderStatus.OPEN),
            timestamp=float(raw.get("timestamp", 0) or 0) / 1000,
            fee=float(fee_info.get("cost", 0) or 0),
            fee_currency=str(fee_info.get("currency") or ""),
            average=float(_avg or 0),
            raw=raw,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def create_connector(exchange_id: str) -> CCXTConnector:
    """Factory function to create a connector by exchange ID."""
    return CCXTConnector(exchange_id)


def list_supported_exchanges() -> list[dict[str, str | bool]]:
    """Return every registry entry with its name, credential shape and status.

    ``verified`` says whether Acervator has ever traded on the venue.
    ``us_ip_blocked`` says whether its public endpoints refused a US IP at
    ``VENUE_MEASUREMENT_DATE``. Both are False for most of the registry,
    which is the point: the registry is a declaration, not a record of use.
    """
    return [
        {
            "id": eid,
            "name": eid.capitalize(),
            "requires_passphrase": eid in PASSPHRASE_EXCHANGES,
            "verified": eid in VERIFIED_EXCHANGES,
            "us_ip_blocked": eid in US_IP_BLOCKED_EXCHANGES,
            "label": exchange_label(eid),
        }
        for eid in SUPPORTED_EXCHANGES
    ]


def exchange_label(exchange_id: str) -> str:
    """Return the picker label for an exchange, carrying its status.

    Follows the equity-broker wording already used in the settings
    dialog: a venue that cannot be reached or has never been traded on
    says so in the list, so it is not offered as the equal of one that
    has.
    """
    label = exchange_id.capitalize()
    notes: list[str] = []
    if exchange_id in US_IP_BLOCKED_EXCHANGES:
        notes.append("blocked from US")
    elif exchange_id not in VERIFIED_EXCHANGES:
        notes.append("untested")
    if exchange_id in PASSPHRASE_EXCHANGES:
        notes.append("passphrase required")
    if notes:
        label += f" ({', '.join(notes)})"
    return label


def requires_passphrase(exchange_id: str) -> bool:
    """Return True if the exchange requires an API passphrase."""
    return exchange_id in PASSPHRASE_EXCHANGES
