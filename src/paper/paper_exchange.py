"""The Paper Trader's exchange adapter, ``PaperExchange``: every read a paper
bot asks of the venue, from the Coinbase Advanced Trade public market
endpoints, and no write.

``PaperExchange`` answers ``READ_NAMES`` and nothing else: ``products`` narrowed
by ``_product_trades``, ``ticker`` with ``best_bid`` and ``best_ask``,
``candles`` at the nine ``GRANULARITY`` names with ``1w`` rolled from daily
pages through ``weekly_rows`` over ``_rollup``, ``windows`` per higher
timeframe, and ``quote_rate`` off the ``{QUOTE}/USD`` ticker. Each venue call
waits ``PUBLIC_MIN_INTERVAL_S`` after the one before it, is recorded as one
``APIInteractionLog`` entry with Live's fields, and on a 429 is recorded,
waited out once and asked again. Answers are held in a ``TickerEntry`` or a
``CacheEntry``, whose ``is_stale`` are Live's two cache windows, and
``__getattribute__`` raises ``SendRefused`` for every public name outside
``READ_NAMES``.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Sequence
from urllib.error import HTTPError

from ..core.fmt import fmt_price_coerced
from ..core.safe_url import SafeRequest, safe_urlopen
from ..exchange.api_logger import APIInteractionLog
from ..exchange.data_pool import CacheEntry, TickerEntry
from ..exchange.market_inspector_fetcher import (
    API_LEVEL_ERROR,
    API_LEVEL_SUCCESS,
    API_LEVEL_WARNING,
    DAYS_PER_WEEK,
    MONDAY_OFFSET_MS,
    PUBLIC_MIN_INTERVAL_S,
    WEEK_MS,
    _product_trades,
)
from ..trading.stone_tablets.registry import _rollup
from .live_feed_source import (
    BAR_SECONDS,
    GRANULARITY,
    MARKET_BASE_URL,
    MAX_CANDLES,
    REQUEST_HEADERS,
    REQUEST_TIMEOUT_S,
    VENUE,
    WINDOW_CANDLES,
    SendRefused,
    bar_seconds,
    candle_row,
    product_id_for,
)

#: Every name ``PaperExchange`` answers. ``__getattribute__`` refuses the rest.
READ_NAMES = (
    "venue",
    "product_id",
    "granularity",
    "timeframes",
    "products",
    "ticker",
    "candles",
    "windows",
    "quote_rate",
    "asked_at",
    "calls",
)

USD = "USD"
DAILY_TIMEFRAME = "1d"
WEEKLY_TIMEFRAME = "1w"

TICKER_LIMIT = 1
TOO_MANY_REQUESTS = 429
RETRY_AFTER_HEADER = "Retry-After"

#: The action words Live's connector records for the same reads.
FETCH_TICKER_ACTION = "FETCH_TICKER"
FETCH_OHLCV_ACTION = "FETCH_OHLCV"
FETCH_MARKETS_ACTION = "FETCH_MARKETS"

TICKER_REASON_FORMAT = "Get current price for {symbol}"
CANDLES_REASON_FORMAT = "Get {count} candles ({timeframe}) for {symbol} - needed for TA indicator computation"
PRODUCTS_REASON = "Paper Trader: which products the venue trades"
TICKER_RESULT_FORMAT = "last={last} bid={bid} ask={ask}"
CANDLES_RESULT_FORMAT = "{count} candles received, latest close={close}"
PRODUCTS_RESULT_FORMAT = "{trading} trading, {dead} not trading"
NO_DATA_RESULT = "No data"
REFUSED_RESULT_FORMAT = "HTTP {status}: {message}"
WAIT_RESULT_FORMAT = (
    "HTTP {status}: {message}; waited {waited_ms:.0f}ms, asking once more"
)
TICKER_DATA_USAGE = (
    "Held for the paper bots' price, bid and ask; the Paper Trader sends nothing"
)
CANDLES_DATA_USAGE = (
    "Held for the paper bots' voting window; the Paper Trader sends nothing"
)
PRODUCTS_DATA_USAGE = "Held to name the fleet products the venue does not trade"
REFUSED_FORMAT = (
    "PaperExchange answers {read_names} and cannot {name!r}. "
    "The Paper Trader receives and asks; it sends nothing."
)


@dataclass(frozen=True)
class Product:
    """One row of the venue's product list: ``product_id``, ``base``,
    ``quote``, ``price`` and ``trades``, the fields a paper fleet reads."""

    product_id: str
    base: str
    quote: str
    price: Optional[float]
    trades: bool


@dataclass
class _Call:
    """One venue call: ``status``, ``body``, the venue's ``message`` on a
    refusal, ``elapsed_ms``, and ``waited_ms`` on a 429."""

    status: int
    body: Any
    message: str
    elapsed_ms: float
    waited_ms: float = 0.0


def _number(value: Any) -> Optional[float]:
    """``value`` as a positive float, None otherwise."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _retry_after_s(headers: Any) -> Optional[float]:
    """The ``RETRY_AFTER_HEADER`` seconds ``headers`` carry, None without one."""
    try:
        raw = headers.get(RETRY_AFTER_HEADER) if headers is not None else None
        return float(raw) if raw is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def _venue_message(exc: HTTPError) -> str:
    """The ``message`` or ``error`` text in ``exc``'s JSON body, or ``exc.reason``."""
    try:
        body = json.loads(exc.read().decode("utf-8"))
        text = (
            body.get("message") or body.get("error") if isinstance(body, dict) else ""
        )
    except (OSError, ValueError, AttributeError):
        text = ""
    return str(text or exc.reason or "")


def _trade_time_s(raw: Any) -> float:
    """A trade's ``time`` stamp ``raw`` as epoch seconds, zero when unreadable."""
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def product_row(raw: dict) -> Optional[Product]:
    """One venue product ``raw`` as a ``Product``; None when it names no id."""
    product_id = str(raw.get("product_id") or "").upper()
    if not product_id:
        return None
    base, _, quote = product_id.partition("-")
    return Product(
        product_id=product_id,
        base=str(raw.get("base_currency_id") or base).upper(),
        quote=str(raw.get("quote_currency_id") or quote).upper(),
        price=_number(raw.get("price")),
        trades=_product_trades(raw.get("status"), raw.get("trading_disabled"), None),
    )


def weekly_rows(daily: Sequence[Sequence[float]]) -> list[list[float]]:
    """One weekly row per calendar week of ``daily`` through ``_rollup``, each
    bucket starting on Monday 00:00 UTC by ``MONDAY_OFFSET_MS``."""
    shifted = [[row[0] - MONDAY_OFFSET_MS, *row[1:6]] for row in daily]
    return [
        [float(int(row[0]) + MONDAY_OFFSET_MS), *row[1:6]]
        for row in _rollup(shifted, DAYS_PER_WEEK, WEEK_MS)
    ]


class PaperExchange:
    """The venue's public market reads, paced by ``_wait``, cached in
    ``TickerEntry`` and ``CacheEntry`` slots, recorded by ``_record``, with
    every write name refused by ``__getattribute__``."""

    def __init__(
        self,
        api_log: Optional[APIInteractionLog] = None,
        base_url: str = MARKET_BASE_URL,
        timeout_s: float = REQUEST_TIMEOUT_S,
        min_interval_s: float = PUBLIC_MIN_INTERVAL_S,
    ) -> None:
        """Read from ``base_url``, record each call on ``api_log``, give up on
        one call after ``timeout_s``, keep ``min_interval_s`` between calls."""
        self._api_log = api_log if api_log is not None else APIInteractionLog()
        self._base_url = str(base_url).rstrip("/")
        self._endpoint_root = urllib.parse.urlsplit(self._base_url).path
        self._timeout_s = float(timeout_s)
        self._min_interval_s = float(min_interval_s)
        self._pace_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._last_call_mono = 0.0
        self._asked_at_ms = 0
        self._calls = 0
        self._tickers: dict[str, TickerEntry] = {}
        self._candles: dict[tuple[str, str], CacheEntry] = {}

    # -- the small reads ---------------------------------------------------

    def venue(self) -> str:
        """The exchange id ``VENUE`` every answer here comes from."""
        return VENUE

    def product_id(self, symbol: str) -> str:
        """``symbol`` through ``product_id_for``, ``BTC/USD`` giving ``BTC-USD``."""
        return product_id_for(symbol)

    def granularity(self, timeframe: str) -> str:
        """The ``GRANULARITY`` name for ``timeframe``; a timeframe outside the
        table is sent as spelled, so the venue's own 400 answers it."""
        return GRANULARITY.get(str(timeframe or ""), str(timeframe or ""))

    def timeframes(self) -> tuple[str, ...]:
        """Every timeframe ``candles`` answers: ``GRANULARITY`` and ``WEEKLY_TIMEFRAME``."""
        return tuple(GRANULARITY) + (WEEKLY_TIMEFRAME,)

    def asked_at(self) -> int:
        """Wall-clock milliseconds of the last answered call, zero before one."""
        return self._asked_at_ms

    def calls(self) -> int:
        """How many venue calls ``_call`` has made; a cache hit adds none."""
        return self._calls

    # -- the venue reads ---------------------------------------------------

    def products(self) -> list[Product]:
        """The products the venue trades, one ``Product`` each by id, from one
        ``FETCH_MARKETS_ACTION`` call; an empty list on a refusal."""
        call = self._call(
            "", FETCH_MARKETS_ACTION, PRODUCTS_REASON, {}, PRODUCTS_DATA_USAGE
        )
        rows = call.body.get("products") if isinstance(call.body, dict) else None
        found = [
            one
            for one in map(product_row, [r for r in rows or [] if isinstance(r, dict)])
            if one is not None
        ]
        if call.status != 200:
            self._record(
                FETCH_MARKETS_ACTION, PRODUCTS_REASON, "", {}, call, API_LEVEL_ERROR
            )
            return []
        trading = [one for one in found if one.trades]
        self._record(
            FETCH_MARKETS_ACTION,
            PRODUCTS_REASON,
            "",
            {},
            call,
            API_LEVEL_SUCCESS,
            PRODUCTS_RESULT_FORMAT.format(
                trading=len(trading), dead=len(found) - len(trading)
            ),
            PRODUCTS_DATA_USAGE,
        )
        return sorted(trading, key=lambda one: one.product_id)

    def ticker(self, symbol: str) -> Optional[dict]:
        """``symbol``'s ``last`` (None when the venue answers no trade),
        ``best_bid``, ``best_ask`` and ``timestamp``, from the held
        ``TickerEntry`` within its window or one ``FETCH_TICKER_ACTION`` call;
        None when the venue answers nothing."""
        key = product_id_for(symbol)
        with self._cache_lock:
            held = self._tickers.get(key)
        if held is not None and not held.is_stale:
            return self._ticker_view(symbol, held)
        path = f"{key}/ticker?limit={TICKER_LIMIT}"
        reason = TICKER_REASON_FORMAT.format(symbol=symbol)
        params = {"symbol": symbol, "limit": TICKER_LIMIT}
        call = self._call(path, FETCH_TICKER_ACTION, reason, params, TICKER_DATA_USAGE)
        if call.status != 200:
            self._record(
                FETCH_TICKER_ACTION, reason, path, params, call, API_LEVEL_ERROR
            )
            return None
        body = call.body if isinstance(call.body, dict) else {}
        trades = [one for one in body.get("trades") or [] if isinstance(one, dict)]
        first = trades[0] if trades else {}
        entry = TickerEntry(
            exchange_id=VENUE,
            symbol=key,
            last=_number(first.get("price")) or 0.0,
            bid=_number(body.get("best_bid")) or 0.0,
            ask=_number(body.get("best_ask")) or 0.0,
            timestamp=_trade_time_s(first.get("time")),
            fetch_time=time.time(),
        )
        if not (entry.last or entry.bid or entry.ask):
            self._record(
                FETCH_TICKER_ACTION,
                reason,
                path,
                params,
                call,
                API_LEVEL_WARNING,
                NO_DATA_RESULT,
            )
            return None
        with self._cache_lock:
            self._tickers[key] = entry
        self._record(
            FETCH_TICKER_ACTION,
            reason,
            path,
            params,
            call,
            API_LEVEL_SUCCESS,
            TICKER_RESULT_FORMAT.format(
                last=fmt_price_coerced(entry.last),
                bid=fmt_price_coerced(entry.bid),
                ask=fmt_price_coerced(entry.ask),
            ),
            TICKER_DATA_USAGE,
        )
        return self._ticker_view(symbol, entry)

    def candles(
        self, symbol: str, timeframe: str = "5m", count: int = WINDOW_CANDLES
    ) -> list[list[float]]:
        """The newest ``count`` bars of ``symbol`` at ``timeframe`` as
        ``[ts_ms, open, high, low, close, volume]`` rows oldest first, from the
        held ``CacheEntry`` within its bar window when it holds enough rows,
        else ``_weekly`` for ``WEEKLY_TIMEFRAME`` or one ``_read_candles``."""
        key = product_id_for(symbol)
        bars = max(1, min(int(count), MAX_CANDLES))
        with self._cache_lock:
            held = self._candles.get((key, timeframe))
        if held is not None and not held.is_stale and len(held.candles) >= bars:
            return list(held.candles[-bars:])
        if timeframe == WEEKLY_TIMEFRAME:
            rows = self._weekly(symbol, key, bars)
        else:
            end_s = int(time.time())
            start_s = end_s - bar_seconds(timeframe) * bars
            rows = self._read_candles(symbol, key, timeframe, start_s, end_s, bars)
        with self._cache_lock:
            self._candles[(key, timeframe)] = CacheEntry(
                exchange_id=VENUE,
                symbol=key,
                timeframe=timeframe,
                candles=rows,
                fetch_time=time.time(),
            )
        return list(rows[-bars:])

    def windows(
        self, symbol: str, timeframes: Sequence[str], count: int = WINDOW_CANDLES
    ) -> dict[str, list[list[float]]]:
        """One ``candles`` window of ``count`` bars per name in ``timeframes``."""
        return {str(one): self.candles(symbol, str(one), count) for one in timeframes}

    def quote_rate(self, quote: str) -> Optional[float]:
        """How many ``USD`` one unit of ``quote`` is worth: 1.0 for ``USD`` with
        no call, else the ``{QUOTE}/USD`` ``ticker``'s ``last``, the book's mid
        when the venue answers no trade, None when it answers nothing."""
        wanted = str(quote or "").upper()
        if not wanted or wanted == USD:
            return 1.0
        view = self.ticker(f"{wanted}/{USD}")
        if view is None:
            return None
        if view["last"]:
            return float(view["last"])
        if view["best_bid"] and view["best_ask"]:
            return (float(view["best_bid"]) + float(view["best_ask"])) / 2.0
        return None

    # -- the mechanism -----------------------------------------------------

    def _ticker_view(self, symbol: str, entry: TickerEntry) -> dict:
        """The ``ticker`` answer built from ``entry``, zero fields as None."""
        return {
            "symbol": symbol,
            "product_id": entry.symbol,
            "last": entry.last or None,
            "best_bid": entry.bid or None,
            "best_ask": entry.ask or None,
            "timestamp": entry.timestamp,
        }

    def _weekly(self, symbol: str, key: str, weeks: int) -> list[list[float]]:
        """``weeks`` rows through ``weekly_rows`` from ``DAILY_TIMEFRAME`` pages
        of at most ``MAX_CANDLES``, newest page first, until ``DAYS_PER_WEEK``
        times ``weeks`` days are held or ``_read_candles`` answers a short page."""
        needed = weeks * DAYS_PER_WEEK
        daily: dict[float, list[float]] = {}
        end_s = int(time.time())
        while len(daily) < needed:
            chunk = min(MAX_CANDLES, needed - len(daily))
            start_s = end_s - BAR_SECONDS[DAILY_TIMEFRAME] * chunk
            page = self._read_candles(
                symbol, key, DAILY_TIMEFRAME, start_s, end_s, chunk
            )
            if not page:
                break
            for row in page:
                daily[row[0]] = row
            end_s = int(page[0][0] // 1000) - 1
            if len(page) < chunk:
                break
        return weekly_rows([daily[ts] for ts in sorted(daily)])

    def _read_candles(
        self,
        symbol: str,
        key: str,
        timeframe: str,
        start_s: int,
        end_s: int,
        limit: int,
    ) -> list[list[float]]:
        """One ``FETCH_OHLCV_ACTION`` call for ``limit`` bars of ``timeframe``
        between ``start_s`` and ``end_s``, as sorted ``candle_row`` rows."""
        granularity = self.granularity(timeframe)
        path = (
            f"{key}/candles?start={start_s}&end={end_s}"
            f"&granularity={granularity}&limit={limit}"
        )
        reason = CANDLES_REASON_FORMAT.format(
            count=limit, timeframe=timeframe, symbol=symbol
        )
        params = {
            "symbol": symbol,
            "timeframe": timeframe,
            "granularity": granularity,
            "start": start_s,
            "end": end_s,
            "limit": limit,
        }
        call = self._call(path, FETCH_OHLCV_ACTION, reason, params, CANDLES_DATA_USAGE)
        if call.status != 200:
            self._record(
                FETCH_OHLCV_ACTION, reason, path, params, call, API_LEVEL_ERROR
            )
            return []
        body = call.body if isinstance(call.body, dict) else {}
        answered = [one for one in body.get("candles") or [] if isinstance(one, dict)]
        rows = [row for row in map(candle_row, answered) if row is not None]
        rows.sort(key=lambda row: row[0])
        self._record(
            FETCH_OHLCV_ACTION,
            reason,
            path,
            params,
            call,
            API_LEVEL_SUCCESS if rows else API_LEVEL_WARNING,
            (
                CANDLES_RESULT_FORMAT.format(
                    count=len(rows), close=fmt_price_coerced(rows[-1][4])
                )
                if rows
                else NO_DATA_RESULT
            ),
            CANDLES_DATA_USAGE,
        )
        return rows[-limit:]

    def _wait(self) -> None:
        """Sleep until ``_min_interval_s`` has passed since ``_last_call_mono``."""
        gap = self._min_interval_s - (time.monotonic() - self._last_call_mono)
        if gap > 0:
            time.sleep(gap)

    def _open(self, path: str) -> _Call:
        """One HTTP GET of ``path`` under ``_base_url`` as a ``_Call``, its
        ``status`` 0 when no answer arrived."""
        url = f"{self._base_url}/{path}" if path else self._base_url
        request = SafeRequest(url)
        for name, value in REQUEST_HEADERS:
            request.add_header(name, value)
        started = time.monotonic()
        try:
            with safe_urlopen(request, timeout=self._timeout_s) as answer:
                body = json.loads(answer.read().decode("utf-8"))
                status = int(answer.status)
        except HTTPError as exc:
            elapsed = (time.monotonic() - started) * 1000
            retry_after = _retry_after_s(exc.headers)
            call = _Call(int(exc.code), {}, _venue_message(exc), elapsed)
            if call.status == TOO_MANY_REQUESTS:
                call.waited_ms = (
                    retry_after if retry_after is not None else self._min_interval_s
                ) * 1000
            return call
        except (OSError, ValueError) as exc:
            elapsed = (time.monotonic() - started) * 1000
            return _Call(0, {}, f"{type(exc).__name__}: {exc}", elapsed)
        self._asked_at_ms = int(time.time() * 1000)
        return _Call(status, body, "", (time.monotonic() - started) * 1000)

    def _call(
        self, path: str, action: str, reason: str, params: dict, data_usage: str
    ) -> _Call:
        """One ``_open`` of ``path`` under ``_pace_lock``, ``_wait`` before it
        and ``_last_call_mono`` stamped after it; a ``TOO_MANY_REQUESTS`` answer
        is recorded through ``_record``, waited out for its ``waited_ms``, and
        asked once more."""
        with self._pace_lock:
            self._wait()
            self._calls += 1
            call = self._open(path)
            self._last_call_mono = time.monotonic()
            if call.status != TOO_MANY_REQUESTS:
                return call
            self._record(
                action,
                reason,
                path,
                params,
                call,
                API_LEVEL_WARNING,
                WAIT_RESULT_FORMAT.format(
                    status=call.status, message=call.message, waited_ms=call.waited_ms
                ),
                data_usage,
            )
            time.sleep(call.waited_ms / 1000)
            self._wait()
            self._calls += 1
            call = self._open(path)
            self._last_call_mono = time.monotonic()
            return call

    def _record(
        self,
        action: str,
        reason: str,
        path: str,
        params: dict,
        call: _Call,
        level: str,
        result: str = "",
        data_usage: str = "",
    ) -> None:
        """One ``APIInteractionLog.record`` entry for ``call`` with Live's
        fields; at ``API_LEVEL_ERROR`` the result is ``REFUSED_RESULT_FORMAT``."""
        endpoint = f"{self._endpoint_root}/{path.split('?', 1)[0]}".rstrip("/")
        self._api_log.record(
            exchange=VENUE,
            action=action,
            reason=reason,
            endpoint=endpoint,
            params=dict(params),
            result=(
                result
                if level != API_LEVEL_ERROR
                else REFUSED_RESULT_FORMAT.format(
                    status=call.status, message=call.message
                )
            ),
            elapsed_ms=call.elapsed_ms,
            level=level,
            data_usage=data_usage,
        )

    def __getattribute__(self, name: str):
        """Answer a private name or one of ``READ_NAMES``; refuse the rest."""
        if not name.startswith("_") and name not in READ_NAMES:
            raise SendRefused(REFUSED_FORMAT.format(read_names=READ_NAMES, name=name))
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str):
        """Refuse a name outside ``READ_NAMES`` the class does not define."""
        raise SendRefused(REFUSED_FORMAT.format(read_names=READ_NAMES, name=name))


def read_fleet(exchange: PaperExchange, symbols: Sequence[str]) -> dict:
    """One ``products`` read and one ``ticker`` read per symbol in ``symbols``
    through ``exchange``, answering the counts and the symbols the venue's
    trading products do not carry; ``untraded`` stays empty while
    ``products_answered`` is False, an unanswered list naming no product."""
    trading = {one.product_id for one in exchange.products()}
    products_answered = bool(trading)
    untraded = [
        one
        for one in symbols
        if products_answered and exchange.product_id(one) not in trading
    ]
    answered = sum(1 for one in symbols if exchange.ticker(one) is not None)
    return {
        "exchange": exchange.venue(),
        "products": len(trading),
        "products_answered": products_answered,
        "records": len(symbols),
        "traded": len(symbols) - len(untraded) if products_answered else 0,
        "answered": answered,
        "untraded": untraded,
        "calls": exchange.calls(),
    }


__all__ = [
    "FETCH_MARKETS_ACTION",
    "FETCH_OHLCV_ACTION",
    "FETCH_TICKER_ACTION",
    "READ_NAMES",
    "WEEKLY_TIMEFRAME",
    "PaperExchange",
    "Product",
    "product_row",
    "read_fleet",
    "weekly_rows",
]
