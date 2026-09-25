"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.

CCXT-backed :class:`ExchangeInterface` for the venues in ``SUPPORTED_EXCHANGES``.
"""

from __future__ import annotations

from ..core.encryption import unescape_pem_newlines
from ..core.fmt import fmt_price_coerced
from ..core.retry import linear_delay, retry_any, retry_sync, with_retry
from ..core.safe_url import SafeRequest, safe_urlopen
import asyncio
import logging
import math
import threading
import time
from decimal import Decimal, InvalidOperation
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from src.core.trade_historian import HistoryAnalysis, scan_on_connect
from typing import Any, Optional

# The historian thread calls it as cb(symbol, analysis) and discards the result.
HistoryCallback = Callable[[str, HistoryAnalysis], object]


# Submissions past this depth are refused rather than queued.
MEM_220_QUEUE_CAP: int = 8

# sync_connect market-load budget: 3 tries, waiting 2s then 4s.
CONNECT_ATTEMPTS: int = 3
CONNECT_BACKOFF_STEP_S: float = 2.0

# Outer wait_for budget for one sync CCXT call.
MEM_220_CALL_TIMEOUT_SEC: float = 25.0


# ccxt caps a coinbase fetch_ohlcv page at this many candles.
EFFECTIVE_OHLCV_PAGE_SIZE = 300

# get_spot_positions answers from _spot_positions_cache within this many seconds.
SPOT_POSITIONS_CACHE_SEC: float = 60.0


class CCXTQueueFullError(RuntimeError):
    """Raised by ``_call_sync`` when the connector's queue is at capacity."""


from .base import (
    AssetInfo,
    Balance,
    ExchangeInterface,
    MarketRules,
    Order,
    OrderBook,
    OrderSide,
    OrderStatus,
    OrderType,
    Ticker,
)
from .api_logger import get_api_log
from .market_pairs_scout import row_quote_volume_24h

logger = logging.getLogger("acervator.exchange")

# Supported exchanges — maps exchange_id to the CCXT class name
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
    "poloniex": "poloniex",
    "bitstamp": "bitstamp",
    "cryptocom": "cryptocom",
}

# Historical registry ids mapped to the class names newer CCXT uses.
CCXT_CLASS_ALIASES: dict[str, str] = {
    "gateio": "gate",
    "huobi": "htx",
}


def resolve_ccxt_class(ccxt_module: Any, ccxt_id: str) -> Any:
    """Return the CCXT class for ``ccxt_id``, trying its alias, or ``None``."""
    cls = getattr(ccxt_module, ccxt_id, None)
    if cls is None:
        alias = CCXT_CLASS_ALIASES.get(ccxt_id)
        if alias:
            cls = getattr(ccxt_module, alias, None)
    return cls


# Exchanges needing an API passphrase, passed to CCXT as 'password'.
PASSPHRASE_EXCHANGES: set[str] = {
    "kucoin",
    "okx",
    "bitget",
}

# Date the venue facts below were last measured.
VENUE_MEASUREMENT_DATE: str = "2026-08-28"

# Venues whose public endpoints refused a US IP at VENUE_MEASUREMENT_DATE.
US_IP_BLOCKED_EXCHANGES: set[str] = {
    "binance",
    "bybit",
}

# Venues reachable from a US IP whose terms refuse a US account.
US_ACCOUNT_RESTRICTED_EXCHANGES: set[str] = {
    "poloniex",
    "huobi",
}

# Union of both refusals — the set the connect path warns on.
US_RESTRICTED_EXCHANGES: set[str] = (
    US_IP_BLOCKED_EXCHANGES | US_ACCOUNT_RESTRICTED_EXCHANGES
)

# Venues Acervator has actually traded on.
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

# CCXT precisionMode values — precision means a different thing under each.
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

    Returns ``default`` when the value is missing, unparseable, or in
    ``SIGNIFICANT_DIGITS`` mode, where no decimal-place count exists.
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


def precision_to_increment(value: Any, precision_mode: int) -> Optional[float]:
    """One CCXT market ``precision`` entry as the step a value moves by, None
    where the venue published none and under ``SIGNIFICANT_DIGITS``, which names
    no step."""
    if value is None:
        return None
    if precision_mode == CCXT_SIGNIFICANT_DIGITS:
        return None
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not dec.is_finite() or dec <= 0:
        return None
    if precision_mode == CCXT_TICK_SIZE:
        return float(dec)
    if precision_mode == CCXT_DECIMAL_PLACES:
        return float(Decimal(1).scaleb(-int(dec)))
    return None


def limit_to_float(value: Any) -> Optional[float]:
    """One CCXT market ``limits`` bound as a float, None where the venue
    published none."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def market_rules(market: Any, precision_mode: int) -> MarketRules:
    """The ``MarketRules`` one loaded CCXT market record publishes.

    ``get_markets`` and ``market_inspector_fetcher.trading_rules`` both read a
    record through this, so one record maps to one rule set.
    """
    limits = (market or {}).get("limits") or {}
    precision = (market or {}).get("precision") or {}
    return MarketRules(
        min_amount=limit_to_float((limits.get("amount") or {}).get("min")),
        min_cost=limit_to_float((limits.get("cost") or {}).get("min")),
        amount_increment=precision_to_increment(
            precision.get("amount"), precision_mode
        ),
        # CCXT maps Coinbase's price_increment, else its quote_increment, here.
        price_increment=precision_to_increment(precision.get("price"), precision_mode),
    )


def record_price(market: Any) -> Optional[float]:
    """The last price the venue's own product record carries under ``info``,
    None where the record carries none; no venue is asked."""
    raw = (market or {}).get("info") or {}
    parsed = limit_to_float(raw.get("price"))
    if parsed is None or parsed <= 0.0:
        return None
    return parsed


_LOGO_CDN = "https://assets.coingecko.com/coins/images/{id}/small/{symbol}.png"
_LOGO_FALLBACK = "https://www.cryptocompare.com/media/img/cc_icons/{symbol}.png"


# Retry decorator for transient failures
def _with_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Bind :func:`src.core.retry.with_retry` to this module's logger."""
    return with_retry(max_retries=max_retries, base_delay=base_delay, log=logger)


class CCXTConnector(ExchangeInterface):
    """Exchange connector for live trading on ``ccxt.async_support``.

    Usage::

        conn = CCXTConnector("coinbase")
        await conn.connect(api_key="...", api_secret="...")
        ticker = await conn.get_ticker("BTC/USD")
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
        # Set only when a backend is attached; live leaves it None.
        self._injected_ex: Any = None
        self._ccxt: Any = None  # ccxt.async_support exchange instance
        self._ccxt_sync: Any = None  # ccxt (sync) exchange instance
        self._connected = False
        self._markets_cache: list[AssetInfo] | None = None
        self._spot_positions_cache: tuple[float, dict] | None = None
        self._last_request_time: float = 0.0
        self._min_request_interval: float = 0.1

        # fetch_ticker serves no volume on coinbase; get_all_tickers fills this.
        self._quote_volumes: dict[str, float] = {}

        self._scan_symbols: set[str] = set()
        self._history_analyses: dict = {}
        self._on_history_ready: Optional[HistoryCallback] = None

        # One worker serialises every sync CCXT call on this connector.
        self._sync_executor: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"ccxt-{exchange_id}",
        )
        # In-flight plus queued calls; touched only on the asyncio loop thread.
        self._sync_queue_depth: int = 0
        # disconnect() may run on a different thread than _call_sync.
        self._sync_executor_lock = threading.Lock()
        # Serialises history scans; add_scan_symbol spawns one thread per symbol.
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
        """Run ``sync_connect`` on the single-worker executor, off the caller's thread.

        ``sync_connect`` blocks for up to about 111 s: a 15 s pre-flight plus
        three 30 s ``load_markets`` attempts spaced 2 s and 4 s apart. It does
        not use :meth:`_call_sync`, whose 25 s budget is shorter than a
        legitimate connect, and does not count against ``_sync_queue_depth``.
        """
        # Under the lock so disconnect() cannot close the executor before the
        # submit.
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
        """Connect with synchronous CCXT, which uses requests rather than aiohttp."""
        if self._injected_ex is not None:
            # A backend serves this connector: no session to open, no credentials.
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
        # A secret stored before the dialog converted on the way in still
        # arrives escaped, so this repeats the conversion and changes nothing
        # when the stored secret already carries real newlines.
        if self._exchange_id == "coinbase" and api_secret:
            api_secret = unescape_pem_newlines(api_secret)
            config["secret"] = api_secret

            is_cdp = api_key.startswith("organizations/")
            # Log the last four characters only, never the key prefix.
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
            except Exception:  # Fall back to the sync exchange when async fails
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

            # Background thread so the scan never delays startup.
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
            # `from None` keeps the traceback single-frame.
            raise ConnectionError(self._format_exchange_error(exc)) from None

    # ── Sync CCXT serialization ─────────────────────────────────────────────

    async def _call_sync(self, fn, *args, **kwargs):
        """Run one sync CCXT call on the single worker, with a queue cap and a timeout.

        Raises:
            CCXTQueueFullError: queue depth is at ``MEM_220_QUEUE_CAP``.
            TimeoutError: the call exceeded ``MEM_220_CALL_TIMEOUT_SEC``.
            asyncio.CancelledError: the awaiter was cancelled; the worker runs on.
            Any CCXT exception: propagated unchanged.
        """
        # Read and written only on the asyncio loop thread, so no lock.
        if self._sync_queue_depth >= MEM_220_QUEUE_CAP:
            raise CCXTQueueFullError(
                f"CCXT call queue at capacity ({self._sync_queue_depth}/"
                f"{MEM_220_QUEUE_CAP}) for {self._exchange_id}; "
                f"exchange is likely rate-limited or network is degraded. "
                f"Call: {getattr(fn, '__name__', repr(fn))}"
            )

        # Under the lock so disconnect() cannot close the executor before the
        # submit.
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
                # The worker thread runs on until CCXT returns; log the leak.
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
                # The worker keeps running until CCXT returns.
                raise
        finally:
            self._sync_queue_depth = max(0, self._sync_queue_depth - 1)

    # ── Trade history scanning ───────────────────────────────────────────────

    def set_history_callback(self, callback: HistoryCallback) -> None:
        """Register a callback the historian thread calls as ``(symbol, analysis)``."""
        self._on_history_ready = callback

    def _scan_trade_history(self, symbols=None) -> None:
        """Scan trade history for *symbols*, or for the registered set when None."""
        if not self._ccxt_sync:
            return

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
        # The lock queues concurrent scans; pace_s is this connector's own interval.
        with self._history_scan_lock:
            try:
                # Timed inside the lock so the duration excludes waiting for a turn.
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
                except Exception:  # noqa: BLE001,S110
                    pass
            except Exception as e:
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
        """Register *symbol* for history scans, scanning it now if already connected."""
        if symbol in self._scan_symbols:
            return  # idempotent — already registered
        self._scan_symbols.add(symbol)
        # Scan now rather than waiting for the next connect.
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
            except Exception as exc:
                logger.warning(
                    "TradeHistorian: late-scan spawn failed for %s: %s", symbol, exc
                )

    def remove_scan_symbol(self, symbol: str):
        self._scan_symbols.discard(symbol)

    def get_history(self, symbol: str) -> HistoryAnalysis | None:
        """Return the most recent history analysis for a symbol."""
        return self._history_analyses.get(symbol)

    def refresh_history(self, symbol: str | None = None):
        """Re-scan *symbol*, or every registered symbol when None."""
        if symbol:
            self._scan_trade_history(symbols=[symbol])
        else:
            self._scan_trade_history()

    @staticmethod
    def _format_exchange_error(exc: Exception) -> str:
        """Extract every available detail from a CCXT exception."""
        parts = [f"{type(exc).__name__}: {exc}"]

        # CCXT puts HTTP details under different attribute names per version.
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

        # Shut the executor down under the lock; in-flight calls run to completion.
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
        # Through `_ex`, so an attached backend is not rejected.
        if self._ex is None:
            raise RuntimeError(f"No exchange instance for {self.display_name}")

    @property
    def _ex(self):
        """Return the attached backend, else the sync CCXT instance, else the async."""
        injected = getattr(self, "_injected_ex", None)
        if injected is not None:
            return injected
        return getattr(self, "_ccxt_sync", None) or self._ccxt

    def attach_backend(self, backend: Any) -> None:
        """Serve every ccxt call from *backend* and mark the connector connected.

        *backend* must provide the fifteen ccxt members reached through ``_ex``:
        fetch_ohlcv, fetch_ticker, fetch_tickers, fetch_balance, create_order,
        cancel_order, fetch_order, fetch_open_orders, fetch_my_trades,
        fetch_order_book, markets, market, precisionMode, amount_to_precision
        and price_to_precision.
        """
        self._injected_ex = backend
        self._connected = True
        # A backend has no venue to throttle, so no interval is enforced.
        self._min_request_interval = 0.0

    # -- Rate limiting --------------------------------------------------
    async def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.monotonic()

    # -- Market data (all methods use sync CCXT via self._call_sync) ----
    def _quote_volume_for(self, symbol: str, raw: dict) -> float:
        """Return ``symbol``'s 24h quote volume from ``raw``, else the recorded one.

        Coinbase's ``fetch_ticker`` serves neither ``quoteVolume`` nor
        ``baseVolume``, so ``get_ticker`` falls back to what the last
        ``get_all_tickers`` recorded for that symbol, and 0.0 before the first.
        """
        served = row_quote_volume_24h(raw)
        if served > 0:
            return served
        return float(self._quote_volumes.get(symbol, 0.0))

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
            volume_24h=self._quote_volume_for(symbol, raw),
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
        """Return the raw CCXT tickers dict for every symbol in one call.

        Not normalised into :class:`Ticker`, which does not carry the 24h
        percentage change callers need. Each row's quote volume is recorded for
        ``get_ticker``, whose own call serves none on coinbase.
        """
        self._ensure_connected()
        await self._rate_limit()
        rows = await self._call_sync(self._ex.fetch_tickers)
        for symbol, row in (rows or {}).items():
            volume = row_quote_volume_24h(row)
            if volume > 0:
                self._quote_volumes[symbol] = volume
        return rows

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
        """Fetch ``limit`` OHLCV candles ending at the newest bar, or starting
        at ``since`` epoch milliseconds."""
        self._ensure_connected()
        await self._rate_limit()
        _log = get_api_log()
        start = time.monotonic()
        data = await self._call_sync(
            self._ex.fetch_ohlcv,
            symbol,
            timeframe,
            None if since is None else int(since),
            int(limit),
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
        # Tell "exchange said zero" apart from "exchange omitted this currency".
        balances = await self.get_balances()
        if currency in balances:
            return balances[currency]

        # get_balances drops totals <= 0, so re-read raw to tell the two apart.
        self._ensure_connected()
        await self._rate_limit()
        raw = await self._call_sync(self._ex.fetch_balance)
        total_map = raw.get("total", {}) or {}
        if currency in total_map:
            # The exchange reported it as zero.
            return Balance(
                currency=currency, free=0.0, used=0.0, total=0.0, absent=False
            )

        # The exchange did not report this currency at all.
        return Balance(currency=currency, free=0.0, used=0.0, total=0.0, absent=True)

    # -- Orders ---------------------------------------------------------

    # Submission is never retried: create_order is not idempotent without a
    # client_order_id.
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

        # Per-(exchange, symbol) breaker short-circuits while a venue is failing.
        from .circuit_breaker import get_breaker_registry, CircuitBreakerOpenError

        _breaker_key = f"{self._exchange_id}:{symbol}"
        _breaker = get_breaker_registry().get(_breaker_key)
        if not _breaker.is_call_allowed():
            _breaker.record_short_circuit()
            raise CircuitBreakerOpenError(_breaker_key, _breaker.cooldown_remaining())
        _log = get_api_log()

        self._ex.market(symbol)
        amount = self._ex.amount_to_precision(symbol, amount)

        # Coinbase needs a price on a spot market BUY to compute total cost.
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
            except Exception:  # The exchange accepts None here
                exec_price = None

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

        # Coinbase Advanced Trade is protobuf-strict: send only its own field name.
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

        # ccxt has no ioc_limit type: send limit with timeInForce=IOC.
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
            # The breaker opens after enough consecutive failures.
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

    @_with_retry()
    async def get_my_trades(
        self,
        symbol: str,
        since: Optional[float] = None,
        limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list:
        """Fetch executed trades; ``params`` forwards per-exchange overrides to ccxt."""
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

    async def get_spot_positions(self) -> Optional[dict]:
        """The venue's open spot positions keyed by asset, from ccxt ``fetch_portfolio_details``.

        None when the ccxt exchange has no ``fetch_portfolios``, when a call
        raises, or when no portfolio answers; a positive answer is held for
        ``SPOT_POSITIONS_CACHE_SEC``. Positions for one asset across several
        portfolios sum, and ``avg_entry_price`` is that sum's cost over balance.
        """
        from .base import SpotPosition

        self._ensure_connected()
        if not hasattr(self._ex, "fetch_portfolios") or not hasattr(
            self._ex, "fetch_portfolio_details"
        ):
            return None
        cached = self._spot_positions_cache
        if cached is not None and time.time() - cached[0] < SPOT_POSITIONS_CACHE_SEC:
            return cached[1]
        try:
            await self._rate_limit()
            portfolios = await self._call_sync(self._ex.fetch_portfolios)
            positions: dict = {}
            answered = 0
            for entry in portfolios or []:
                uuid = str(entry.get("id", "") or "")
                if not uuid:
                    continue
                await self._rate_limit()
                rows = await self._call_sync(self._ex.fetch_portfolio_details, uuid)
                answered += 1
                for row in rows or []:
                    if row.get("is_cash"):
                        continue
                    asset = str(row.get("currency", "") or "")
                    if not asset:
                        continue
                    basis = float(row.get("cost_basis", 0) or 0)
                    balance = float(row.get("total_balance_crypto", 0) or 0)
                    unrealized = float(row.get("unrealized_pnl", 0) or 0)
                    avg = float(row.get("average_entry_price", 0) or 0)
                    held = positions.get(asset)
                    if held is None:
                        positions[asset] = SpotPosition(
                            asset=asset,
                            cost_basis_usd=basis,
                            avg_entry_price=avg,
                            unrealized_pnl_usd=unrealized,
                            balance=balance,
                            raw=dict(row),
                        )
                        continue
                    held.cost_basis_usd += basis
                    held.unrealized_pnl_usd += unrealized
                    held.balance += balance
                    if held.balance > 0:
                        held.avg_entry_price = held.cost_basis_usd / held.balance
        except Exception as exc:
            logger.warning(
                "get_spot_positions: %s portfolio breakdown failed: %s",
                self._exchange_id,
                exc,
            )
            return None
        if answered == 0:
            return None
        self._spot_positions_cache = (time.time(), positions)
        return positions

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

            markets.append(
                AssetInfo(
                    symbol=sym,
                    base=info.get("base", ""),
                    quote=info.get("quote", ""),
                    rules=market_rules(info, precision_mode),
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
        """Convert a CCXT order dict to an :class:`Order`.

        Side, type and status use ``or`` rather than a ``get`` default: CCXT
        returns an explicit ``None`` for them, which a default never replaces.
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
        # CCXT omits `average` on some venues; derive it from cost / filled.
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


def create_connector(exchange_id: str) -> CCXTConnector:
    """Return a connector for *exchange_id*."""
    return CCXTConnector(exchange_id)


def list_supported_exchanges() -> list[dict[str, str | bool]]:
    """Return every registry entry with its name, credential shape and status."""
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
    """Return the picker label for *exchange_id*, carrying its status notes."""
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
