"""Daily historical prices for the Portfolio Battery symbols.

``YahooChartAdapter`` is the non-crypto ``ExchangeAdapter``; crypto keeps the
existing ``CoinbaseAdapter``, driven by ``CoinbasePublicCandles`` so no
credential is sent. ``RaTabletBuilder.build_year`` writes one ``Tablet`` per
asset and year under ``RA_STONE_TABLETS_DIR`` and records a ``TabletGap``
wherever a source returns no rows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.error import HTTPError, URLError

from src.core.io_utils import atomic_write_json
from src.core.retry import exponential_delay, retry_async
from src.core.safe_url import SafeRequest, safe_urlopen

from .fetcher import CoinbaseAdapter, ExchangeAdapter, FetchAttempt
from .ra_paths import RA_GAPS_PATH, RA_STONE_TABLETS_DIR, get_ra_root
from .storage import (
    Tablet,
    entry_from_tablet,
    read_manifest,
    read_tablet,
    tablet_filename,
    tablet_path,
    write_manifest,
    write_tablet,
)

logger = logging.getLogger("acervator.stone_tablets.ra_fetcher")

RA_TIMEFRAME: str = "1d"
"""The timeframe ``RaTabletBuilder`` writes; both sources serve daily candles.
A crypto asset's 5m tablet lands beside them through ``StoneTabletsRegistry``
on ``RA_STONE_TABLETS_DIR``, keyed by ``tablet_filename`` as these are."""

DAY_MS: int = 86_400_000

HOUR_MS: int = 3_600_000

#: The chart endpoint's own interval spelling for each ATA-SPM timeframe key.
YAHOO_INTERVALS: dict[str, str] = {
    "1h": "1h",
    RA_TIMEFRAME: "1d",
    "1w": "1wk",
    "1M": "1mo",
}

#: No measured limit on how far back one interval reaches.
UNCAPPED_REACH_DAYS: int = 0

#: Days each ``YAHOO_INTERVALS`` key reaches; 1h answered 729 and refused 730.
YAHOO_REACH_DAYS: dict[str, int] = {
    "1h": 729,
    RA_TIMEFRAME: UNCAPPED_REACH_DAYS,
    "1w": UNCAPPED_REACH_DAYS,
    "1M": UNCAPPED_REACH_DAYS,
}

#: Milliseconds one bar covers, for the keys whose bar is a fixed length.
YAHOO_STEP_MS: dict[str, int] = {"1h": HOUR_MS, RA_TIMEFRAME: DAY_MS}

RA_CHUNK_DAYS: int = 300
"""Coinbase Exchange returns at most 300 candles per request."""

FUTURES_CANDLE_CAP: int = 350
"""Coinbase Advanced Trade's market candles endpoint returns at most 350 a request."""

#: The endpoint's granularity name for each ATA-SPM timeframe key it serves.
FUTURES_GRANULARITIES: dict[str, str] = {"1h": "ONE_HOUR", RA_TIMEFRAME: "ONE_DAY"}

#: Milliseconds one bar of each ``FUTURES_GRANULARITIES`` key covers.
FUTURES_STEP_MS: dict[str, int] = {"1h": HOUR_MS, RA_TIMEFRAME: DAY_MS}

FUTURES_CANDLES_KEY: str = "candles"

USER_AGENT: str = "acervator-stone-tablets/1.0"

RATE_LIMIT_HTTP_CODE: int = 429
RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})
"""Rate limit and server-side codes worth a second attempt; 400 and 404 are not."""

RETRY_AFTER_HEADER: str = "Retry-After"
RETRY_AFTER_FORMAT: str = "{error}; retry after {seconds:g} s"


def is_transient_http(
    exc: BaseException, codes: frozenset[int] = RETRYABLE_HTTP_CODES
) -> bool:
    """True when ``exc`` is a ``codes`` answer, a server error or a transport failure."""
    if isinstance(exc, HTTPError):
        return exc.code in codes
    return isinstance(exc, (URLError, TimeoutError, json.JSONDecodeError))


def error_text(exc: BaseException) -> str:
    """One failed request as its refusal: the exception's name and text, and the
    ``Retry-After`` seconds an ``HTTPError`` carries, in ``RETRY_AFTER_FORMAT``."""
    text = f"{type(exc).__name__}: {exc}"
    headers = getattr(exc, "headers", None)
    held = headers.get(RETRY_AFTER_HEADER) if headers is not None else None
    if held is None:
        return text
    try:
        seconds = float(str(held).strip())
    except ValueError:
        return text
    return RETRY_AFTER_FORMAT.format(error=text, seconds=seconds)


class RaCoinbaseAdapter(CoinbaseAdapter):
    """``CoinbaseAdapter`` driven by ``CoinbasePublicCandles``, which raises ``HTTPError``.

    ``is_retryable`` narrows the base adapter's retry-everything rule to
    ``is_transient_http``.
    """

    @staticmethod
    def is_retryable(exc: BaseException) -> bool:
        """True for a rate limit, a server error or a transport failure."""
        return is_transient_http(exc)


def _get_json(url: str, params: dict[str, Any], timeout_s: float) -> Any:
    """GET ``url`` with ``params`` and return the decoded JSON body."""
    request = SafeRequest(f"{url}?{urllib.parse.urlencode(params)}")
    request.add_header("User-Agent", USER_AGENT)
    with safe_urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _floor_to_step_ms(ts_ms: int, step_ms: int) -> int:
    """Return ``ts_ms`` moved back to the start of its own ``step_ms`` period."""
    return ts_ms - (ts_ms % step_ms)


def _floor_to_day_ms(ts_ms: int) -> int:
    """Return ``ts_ms`` moved back to the UTC midnight of its own day."""
    return _floor_to_step_ms(ts_ms, DAY_MS)


def _last_per_stamp(rows: list[list[float]]) -> list[list[float]]:
    """One row per timestamp, keeping the last, oldest first.

    A running period the endpoint sends twice floors onto one ``YAHOO_STEP_MS``
    step, so ``_rows_from_series`` would otherwise carry both.
    """
    held: dict[float, list[float]] = {}
    for row in rows:
        held[row[0]] = row
    return [held[ts] for ts in sorted(held)]


def year_bounds_ms(year: int) -> tuple[int, int]:
    """Return the first and last UTC midnight of ``year``, capped at today."""
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year, 12, 31, tzinfo=timezone.utc)
    now_ms = _floor_to_day_ms(int(datetime.now(timezone.utc).timestamp() * 1000))
    return int(start.timestamp() * 1000), min(int(end.timestamp() * 1000), now_ms)


class CoinbasePublicCandles:
    """The ``get_ohlcv`` surface ``CoinbaseAdapter`` calls, over public candles.

    ``BASE_URL`` reaches no account or order endpoint and carries no key.
    """

    BASE_URL: str = "https://api.exchange.coinbase.com/products"
    GRANULARITY_S: dict[str, int] = {"1d": 86_400, "1h": 3_600, "5m": 300}
    SOURCE: str = "coinbase_exchange_candles_ONE_DAY"

    def __init__(self, timeout_s: float = 20.0) -> None:
        self._timeout_s = timeout_s

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = RA_TIMEFRAME,
        limit: int = RA_CHUNK_DAYS,
        since: Optional[int] = None,
    ) -> list[list[float]]:
        """Return ``[ts_ms, open, high, low, close, volume]`` rows, oldest first.

        ``since`` is epoch milliseconds and ``limit`` counts candles, clamped to
        ``RA_CHUNK_DAYS``.
        """
        granularity = self.GRANULARITY_S.get(timeframe)
        if granularity is None:
            raise ValueError(
                f"coinbase public candles: unsupported timeframe {timeframe!r}; "
                f"supported: {sorted(self.GRANULARITY_S)}"
            )
        rows = min(int(limit), RA_CHUNK_DAYS)
        start_s = int(since or 0) // 1000
        end_s = start_s + rows * granularity
        product = symbol.replace("/", "-").upper()
        payload = await asyncio.to_thread(
            _get_json,
            f"{self.BASE_URL}/{product}/candles",
            {
                "granularity": granularity,
                "start": datetime.fromtimestamp(start_s, tz=timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(end_s, tz=timezone.utc).isoformat(),
            },
            self._timeout_s,
        )
        if not isinstance(payload, list):
            raise ValueError(f"coinbase public candles: {payload}")
        # The venue sends [time_s, low, high, open, close, volume], newest first.
        out: list[list[float]] = [
            [
                float(int(row[0]) * 1000),
                float(row[3]),
                float(row[2]),
                float(row[1]),
                float(row[4]),
                float(row[5]),
            ]
            for row in payload
        ]
        out.sort(key=lambda r: r[0])
        return out


class CoinbaseFuturesCandles(ExchangeAdapter):
    """Candles for one Coinbase Advanced Trade futures or perpetual product.

    ``BASE_URL`` is the public market data route and carries no key.
    ``fetch_chunk`` reads the newest ``FUTURES_CANDLE_CAP`` candles of a
    ``FUTURES_GRANULARITIES`` key ending at ``until_ms``, the way
    ``ata_asset_maps.venue_candle_read`` asks ``YahooChartAdapter``.
    """

    exchange_id = "coinbase-futures"
    chunk_limit = FUTURES_CANDLE_CAP

    BASE_URL: str = "https://api.coinbase.com/api/v3/brokerage/market/products"
    SOURCE: str = "coinbase_advanced_trade_market_candles"

    def __init__(self, timeout_s: float = 20.0) -> None:
        super().__init__(connector=None)
        self._timeout_s = timeout_s

    async def fetch_chunk(
        self,
        asset: str,
        quote: str,
        since_ms: int,
        until_ms: int,
        timeframe: str = RA_TIMEFRAME,
    ) -> FetchAttempt:
        """Fetch ``asset``'s newest candles on ``timeframe`` and return a ``FetchAttempt``.

        ``asset`` is the venue's ``product_id``; ``quote`` is carried, not checked.
        """
        del quote
        granularity = FUTURES_GRANULARITIES.get(str(timeframe))
        if granularity is None:
            return FetchAttempt(
                since_ms=since_ms,
                until_ms=until_ms,
                error=(
                    f"{self.exchange_id} serves {sorted(FUTURES_GRANULARITIES)}, "
                    f"not {timeframe}"
                ),
            )
        step_s = FUTURES_STEP_MS[str(timeframe)] // 1000
        end_s = int(until_ms) // 1000
        start_s = max(int(since_ms) // 1000, end_s - FUTURES_CANDLE_CAP * step_s)
        try:
            payload = await asyncio.to_thread(
                _get_json,
                f"{self.BASE_URL}/{asset}/candles",
                {"start": start_s, "end": end_s, "granularity": granularity},
                self._timeout_s,
            )
        except Exception as exc:
            return FetchAttempt(
                since_ms=since_ms,
                until_ms=until_ms,
                error=error_text(exc),
            )
        return FetchAttempt(
            since_ms=since_ms,
            until_ms=until_ms,
            candles=self._rows_from_candles(payload, since_ms, until_ms),
        )

    @staticmethod
    def _rows_from_candles(
        payload: Any, since_ms: int, until_ms: int
    ) -> list[list[float]]:
        """The ``FUTURES_CANDLES_KEY`` dicts of ``payload`` as OHLCV rows, oldest first.

        Each dict carries ``start`` in seconds and ``open``, ``high``, ``low``,
        ``close`` and ``volume`` as strings; a dict missing one is dropped.
        """
        rows: list[list[float]] = []
        held = (
            (payload or {}).get(FUTURES_CANDLES_KEY)
            if isinstance(payload, dict)
            else None
        )
        for one in held or []:
            if not isinstance(one, dict):
                continue
            try:
                ts_ms = int(one["start"]) * 1000
                values = [float(one[key]) for key in ("open", "high", "low", "close")]
                volume = float(one.get("volume") or 0.0)
            except (KeyError, TypeError, ValueError):
                continue
            if ts_ms < since_ms or ts_ms > until_ms:
                continue
            rows.append([float(ts_ms), *values, volume])
        rows.sort(key=lambda r: r[0])
        return _last_per_stamp(rows)


class YahooChartAdapter(ExchangeAdapter):
    """Non-crypto candles from the Yahoo Finance chart endpoint.

    ``fetch_chunk`` serves every ``YAHOO_INTERVALS`` key, clamps ``since_ms``
    to ``YAHOO_REACH_DAYS``, and retries a failure in ``retry_codes`` or a
    transport failure ``retry_max`` times; ``ticker_suffix`` reaches a ticker
    the endpoint spells with one.
    """

    exchange_id = "yahoo"
    chunk_limit = RA_CHUNK_DAYS
    chunk_sleep_s = 1.0
    retry_max = 3
    retry_base_s = 2.0

    BASE_URL: str = "https://query1.finance.yahoo.com/v8/finance/chart"
    SOURCE: str = "yahoo_chart_v8_ONE_DAY_SPLIT_ADJUSTED"

    def __init__(
        self,
        timeout_s: float = 20.0,
        ticker_suffix: str = "",
        retry_codes: frozenset[int] = RETRYABLE_HTTP_CODES,
    ) -> None:
        super().__init__(connector=None)
        self._timeout_s = timeout_s
        self._ticker_suffix = ticker_suffix
        self._retry_codes = frozenset(retry_codes)

    def ticker_for(self, asset: str) -> str:
        """Return the endpoint's ticker for ``asset``, with ``ticker_suffix``."""
        return f"{asset.upper()}{self._ticker_suffix}"

    @staticmethod
    def reach_start_ms(timeframe: str, since_ms: int, end_ms: int) -> int:
        """The oldest millisecond ``timeframe`` reaches, never before ``since_ms``.

        A key whose ``YAHOO_REACH_DAYS`` row is ``UNCAPPED_REACH_DAYS`` keeps
        ``since_ms``, so only the hourly window is moved forward.
        """
        reach = YAHOO_REACH_DAYS.get(timeframe, UNCAPPED_REACH_DAYS)
        if reach == UNCAPPED_REACH_DAYS:
            return int(since_ms)
        return max(int(since_ms), int(end_ms) - reach * DAY_MS)

    async def fetch_chunk(
        self,
        asset: str,
        quote: str,
        since_ms: int,
        until_ms: int,
        timeframe: str = RA_TIMEFRAME,
    ) -> FetchAttempt:
        """Fetch one range of ``timeframe`` candles and return a ``FetchAttempt``."""
        interval = YAHOO_INTERVALS.get(str(timeframe))
        if interval is None:
            return FetchAttempt(
                since_ms=since_ms,
                until_ms=until_ms,
                error=(
                    f"{self.exchange_id} serves {sorted(YAHOO_INTERVALS)}, "
                    f"not {timeframe}"
                ),
            )
        ticker = self.ticker_for(asset)
        end_ms = int(until_ms) + DAY_MS
        start_ms = self.reach_start_ms(str(timeframe), int(since_ms), end_ms)

        async def _fetch_once() -> Any:
            return await asyncio.to_thread(
                _get_json,
                f"{self.BASE_URL}/{ticker}",
                {
                    "period1": start_ms // 1000,
                    "period2": end_ms // 1000,
                    "interval": interval,
                },
                self._timeout_s,
            )

        try:
            payload = await self._with_retry(_fetch_once, ticker)
        except Exception as exc:
            return FetchAttempt(
                since_ms=since_ms,
                until_ms=until_ms,
                error=error_text(exc),
            )
        return self._read_payload(payload, quote, start_ms, until_ms, str(timeframe))

    async def _with_retry(
        self,
        op: Callable[[], Awaitable[Any]],
        ticker: str,
    ) -> Any:
        """Await ``op`` up to ``retry_max`` times, backing off on a transient error."""

        def _note(
            exc: BaseException, attempt: int, will_retry: bool, delay: float
        ) -> None:
            logger.warning(
                "yahoo chart %s attempt %d/%d failed: %s %s",
                ticker,
                attempt + 1,
                self.retry_max,
                exc,
                f"— sleeping {delay:.1f}s" if will_retry else "— no attempts left",
            )

        def _retryable(exc: BaseException) -> bool:
            return is_transient_http(exc, self._retry_codes)

        return await retry_async(
            op,
            attempts=self.retry_max,
            delay_for=exponential_delay(self.retry_base_s),
            is_retryable=_retryable,
            on_failure=_note,
        )

    def _read_payload(
        self,
        payload: Any,
        quote: str,
        since_ms: int,
        until_ms: int,
        timeframe: str = RA_TIMEFRAME,
    ) -> FetchAttempt:
        """Turn one chart response into a ``FetchAttempt``."""
        chart = (payload or {}).get("chart") or {}
        error = chart.get("error")
        results = chart.get("result") or []
        if error or not results:
            return FetchAttempt(
                since_ms=since_ms,
                until_ms=until_ms,
                error=f"chart error: {error}" if error else "chart returned no result",
            )
        result = results[0]
        currency = str((result.get("meta") or {}).get("currency") or "")
        if currency.upper() != quote.upper():
            return FetchAttempt(
                since_ms=since_ms,
                until_ms=until_ms,
                error=f"series is quoted in {currency!r}, not {quote!r}",
            )
        stamps = result.get("timestamp") or []
        quotes = (result.get("indicators") or {}).get("quote") or [{}]
        candles = self._rows_from_series(
            stamps, quotes[0], since_ms, until_ms, timeframe
        )
        return FetchAttempt(since_ms=since_ms, until_ms=until_ms, candles=candles)

    @staticmethod
    def _rows_from_series(
        stamps: list,
        series: dict,
        since_ms: int,
        until_ms: int,
        timeframe: str = RA_TIMEFRAME,
    ) -> list[list[float]]:
        """Return the rows inside the window, dropping every bar with a null.

        A ``YAHOO_STEP_MS`` key floors its stamps to that step; ``1w`` and
        ``1M`` carry no fixed step and keep the stamp the endpoint sent.
        """
        step_ms = YAHOO_STEP_MS.get(timeframe)
        opens = series.get("open") or []
        highs = series.get("high") or []
        lows = series.get("low") or []
        closes = series.get("close") or []
        volumes = series.get("volume") or []
        rows: list[list[float]] = []
        for i, stamp in enumerate(stamps):
            values = (
                opens[i] if i < len(opens) else None,
                highs[i] if i < len(highs) else None,
                lows[i] if i < len(lows) else None,
                closes[i] if i < len(closes) else None,
            )
            if stamp is None or any(v is None for v in values):
                continue
            raw_ms = int(stamp) * 1000
            ts_ms = _floor_to_step_ms(raw_ms, step_ms) if step_ms else raw_ms
            if ts_ms < since_ms or ts_ms > until_ms:
                continue
            volume = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0
            rows.append([ts_ms, *(float(v) for v in values), float(volume)])
        rows.sort(key=lambda r: r[0])
        return _last_per_stamp(rows) if step_ms else rows


@dataclass
class TabletGap:
    """One requested period a source returned no rows for."""

    asset: str
    exchange_id: str
    timeframe: str
    year: int
    since_ms: int
    until_ms: int
    reason: str
    checked_at: str


@dataclass
class YearBuild:
    """What ``build_year`` did for one asset and year."""

    asset: str
    exchange_id: str
    year: int
    candles_written: int
    tablet_file: str = ""
    gaps: list[TabletGap] = field(default_factory=list)
    ranges_requested: list[tuple[int, int]] = field(default_factory=list)


def _edge_gaps(
    since_ms: int,
    until_ms: int,
    first_served_ms: float,
    last_served_ms: float,
) -> list[tuple[int, int, str]]:
    """Return the requested days outside the served span, as gap arguments."""
    first = int(first_served_ms)
    last = int(last_served_ms)
    out: list[tuple[int, int, str]] = []
    if since_ms < first:
        out.append((since_ms, first - DAY_MS, f"no rows before {_iso_day(first)}"))
    if last < until_ms:
        out.append((last + DAY_MS, until_ms, f"no rows after {_iso_day(last)}"))
    return out


def _iso_day(ts_ms: int) -> str:
    """Return ``ts_ms`` as a ``YYYY-MM-DD`` UTC date."""
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def read_gaps(root: Optional[Path] = None) -> list[TabletGap]:
    """Return the ``TabletGap`` rows under ``root``, empty when GAPS.json is absent."""
    path = (root / "GAPS.json") if root is not None else RA_GAPS_PATH
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("ra_tablets: GAPS.json unreadable: %s", exc)
        return []
    out: list[TabletGap] = []
    for row in data.get("gaps", []):
        try:
            out.append(TabletGap(**row))
        except TypeError:
            continue
    return out


def write_gaps(gaps: list[TabletGap], root: Optional[Path] = None) -> Path:
    """Write ``gaps`` to GAPS.json under ``root`` and return that path."""
    base = root or get_ra_root()
    base.mkdir(parents=True, exist_ok=True)
    path = base / "GAPS.json"
    atomic_write_json(
        path,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "gaps": [asdict(g) for g in gaps],
        },
        indent=2,
    )
    return path


class RaTabletBuilder:
    """Writes RA-StoneTablets through one ``ExchangeAdapter``.

    ``build_year`` fetches only the part of a year the stored tablet does not
    hold, and records a ``TabletGap`` for a requested range that returns no rows.
    """

    def __init__(
        self,
        adapter: ExchangeAdapter,
        source: str = "",
        root: Optional[Path] = None,
        quote_currency: str = "USD",
    ) -> None:
        resolved = source or str(getattr(adapter, "SOURCE", ""))
        if not resolved:
            raise ValueError(
                f"{type(adapter).__name__} carries no SOURCE; pass source= naming "
                f"the endpoint the candles come from. {adapter.exchange_id!r} is "
                f"an exchange id, not provenance."
            )
        self._adapter = adapter
        self._source = resolved
        self._root = root or get_ra_root()
        self._quote = quote_currency

    async def build_year(self, asset: str, year: int) -> YearBuild:
        """Fetch and store ``asset``'s daily candles for ``year``."""
        exchange_id = self._adapter.exchange_id
        asset_u = asset.upper()
        since_ms, until_ms = year_bounds_ms(year)
        build = YearBuild(
            asset=asset_u, exchange_id=exchange_id, year=year, candles_written=0
        )
        if until_ms < since_ms:
            build.gaps = self._record_gaps(
                asset_u, year, [(since_ms, until_ms, "year has not started")]
            )
            return build

        path = tablet_path(
            asset_u, RA_TIMEFRAME, year, root=self._root, exchange_id=exchange_id
        )
        existing = read_tablet(path)
        held = {
            int(row[0]): list(row) for row in (existing.candles if existing else [])
        }
        ranges = self._missing_ranges(existing, since_ms, until_ms)
        build.ranges_requested = ranges
        merged = dict(held)
        if ranges:
            fetched, errors = await self._fetch_ranges(asset_u, ranges)
            for row in fetched:
                merged[int(row[0])] = list(row)
            if not fetched and not held:
                build.gaps = self._record_gaps(
                    asset_u,
                    year,
                    [
                        (
                            since_ms,
                            until_ms,
                            "; ".join(errors) if errors else "source returned no rows",
                        )
                    ],
                )
                return build
        if not merged:
            return build

        candles = [merged[ts] for ts in sorted(merged)]
        build.candles_written = len(candles)
        # Rewriting an unchanged tablet would restamp fetched_at on candles
        # nothing fetched this run.
        build.tablet_file = (
            path.name if merged == held else self._store(asset_u, year, candles).name
        )
        build.gaps = self._record_gaps(
            asset_u, year, _edge_gaps(since_ms, until_ms, candles[0][0], candles[-1][0])
        )
        return build

    def _missing_ranges(
        self,
        existing: Optional[Tablet],
        since_ms: int,
        until_ms: int,
    ) -> list[tuple[int, int]]:
        """Return the parts of the window outside the stored tablet's span."""
        if existing is None or not existing.candles:
            return [(since_ms, until_ms)]
        ranges: list[tuple[int, int]] = []
        if since_ms < existing.first_ts_ms:
            ranges.append((since_ms, existing.first_ts_ms - DAY_MS))
        if existing.last_ts_ms < until_ms:
            ranges.append((existing.last_ts_ms + DAY_MS, until_ms))
        return ranges

    async def _fetch_ranges(
        self,
        asset_u: str,
        ranges: list[tuple[int, int]],
    ) -> tuple[list[list[float]], list[str]]:
        """Walk every range in ``RA_CHUNK_DAYS`` steps and collect its rows."""
        span_ms = RA_CHUNK_DAYS * DAY_MS
        rows: list[list[float]] = []
        errors: list[str] = []
        for range_start, range_end in ranges:
            cursor = range_start
            while cursor <= range_end:
                chunk_end = min(cursor + span_ms - DAY_MS, range_end)
                attempt = await self._adapter.fetch_chunk(
                    asset_u, self._quote, cursor, chunk_end, RA_TIMEFRAME
                )
                if attempt.error:
                    errors.append(f"[{cursor}..{chunk_end}]: {attempt.error}")
                    logger.warning(
                        "ra_tablets %s@%s chunk failed: %s",
                        asset_u,
                        self._adapter.exchange_id,
                        attempt.error,
                    )
                    cursor = chunk_end + DAY_MS
                    continue
                rows.extend(attempt.candles)
                newest = max((int(r[0]) for r in attempt.candles), default=0)
                cursor = max(newest + DAY_MS, chunk_end + DAY_MS)
                await asyncio.sleep(self._adapter.chunk_sleep_s)
        return rows, errors

    def _store(self, asset_u: str, year: int, candles: list[list[float]]) -> Path:
        """Write the tablet and replace its row in the RA MANIFEST."""
        tablet = Tablet(
            asset=asset_u,
            exchange_id=self._adapter.exchange_id,
            timeframe=RA_TIMEFRAME,
            year=year,
            source=self._source,
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            candles=candles,
        )
        path = write_tablet(tablet, root=self._root)
        filename = tablet_filename(
            asset_u, RA_TIMEFRAME, year, exchange_id=self._adapter.exchange_id
        )
        entries = [e for e in read_manifest(self._root) if e.file != filename]
        entries.append(entry_from_tablet(tablet))
        entries.sort(key=lambda e: (e.asset, e.exchange_id, e.timeframe, e.year))
        write_manifest(entries, root=self._root)
        return path

    def _record_gaps(
        self,
        asset_u: str,
        year: int,
        windows: list[tuple[int, int, str]],
    ) -> list[TabletGap]:
        """Replace this asset and year's rows in GAPS.json with ``windows``."""
        checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        exchange_id = self._adapter.exchange_id
        gaps = [
            TabletGap(
                asset=asset_u,
                exchange_id=exchange_id,
                timeframe=RA_TIMEFRAME,
                year=year,
                since_ms=since_ms,
                until_ms=until_ms,
                reason=reason,
                checked_at=checked_at,
            )
            for since_ms, until_ms, reason in windows
        ]
        key = (asset_u, exchange_id, RA_TIMEFRAME, year)
        kept = [
            g
            for g in read_gaps(self._root)
            if (g.asset, g.exchange_id, g.timeframe, g.year) != key
        ]
        write_gaps(kept + gaps, root=self._root)
        return gaps


__all__ = [
    "DAY_MS",
    "FUTURES_CANDLE_CAP",
    "FUTURES_GRANULARITIES",
    "FUTURES_STEP_MS",
    "HOUR_MS",
    "RA_CHUNK_DAYS",
    "RA_STONE_TABLETS_DIR",
    "RA_TIMEFRAME",
    "RETRYABLE_HTTP_CODES",
    "UNCAPPED_REACH_DAYS",
    "YAHOO_INTERVALS",
    "YAHOO_REACH_DAYS",
    "YAHOO_STEP_MS",
    "CoinbaseFuturesCandles",
    "CoinbasePublicCandles",
    "RaCoinbaseAdapter",
    "RaTabletBuilder",
    "TabletGap",
    "YahooChartAdapter",
    "YearBuild",
    "is_transient_http",
    "read_gaps",
    "write_gaps",
    "year_bounds_ms",
]
