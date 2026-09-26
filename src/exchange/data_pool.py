"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
Shared market-data cache for candles, tickers and balances.

``MarketDataPool`` holds one ``CacheEntry``, ``TickerEntry`` or ``BalanceEntry``
per exchange, symbol and timeframe. ``get_or_fetch_ticker``,
``get_or_fetch_ohlcv`` and ``get_or_fetch_balance`` return a fresh entry from
cache and coalesce concurrent misses behind one ``asyncio.Lock``.
``get_data_pool`` returns the process-wide singleton.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional, cast

from .market_pairs_scout import row_quote_volume_24h

logger = logging.getLogger("acervator.data_pool")

TF_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


def _row_timestamp(row) -> Optional[float]:
    """The finite ``row[0]`` of one OHLCV row as a float, None when it has none."""
    try:
        at = float(row[0])
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    return at if math.isfinite(at) else None


def _merge_candle_rows(stored: list, fetched: list) -> Optional[list]:
    """One row per timestamp from ``stored`` then ``fetched``, oldest first, None
    when a row carries no finite ``row[0]``."""
    by_time: dict[float, list] = {}
    for row in list(stored) + list(fetched):
        at = _row_timestamp(row)
        if at is None:
            return None
        by_time[at] = row
    return [by_time[at] for at in sorted(by_time)]


@dataclass
class CacheEntry:
    """Candles for one exchange, symbol and timeframe.

    ``ttl_seconds`` reads ``TF_SECONDS`` for ``timeframe`` and falls back
    to 3600.
    """

    exchange_id: str
    symbol: str
    timeframe: str
    candles: list = field(default_factory=list)
    fetch_time: float = 0.0
    subscribers: int = 0
    fetch_count: int = 0
    errors: int = 0
    venue_row_cap: Optional[int] = None

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetch_time if self.fetch_time else float("inf")

    @property
    def ttl_seconds(self) -> float:
        return TF_SECONDS.get(self.timeframe, 3600)

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > self.ttl_seconds

    def can_serve(self, limit: int) -> bool:
        """True when this slot is fresh and holds ``limit`` rows, or holds every row
        ``venue_row_cap`` says the venue has."""
        if self.is_stale or not self.candles:
            return False
        if len(self.candles) >= limit:
            return True
        return (
            self.venue_row_cap is not None and len(self.candles) >= self.venue_row_cap
        )

    def merge_fetch(self, fetched: list, requested: int) -> None:
        """Merge ``fetched`` into ``candles`` on timestamp, keep the newest
        ``requested`` rows, and set ``venue_row_cap`` from the distinct rows fetched."""
        rows = list(fetched or [])
        if not rows:
            return
        keep = max(1, int(requested))
        merged = _merge_candle_rows(self.candles, rows)
        distinct_rows = _merge_candle_rows([], rows)
        supplied_rows = len(rows) if distinct_rows is None else len(distinct_rows)
        self.candles = rows[-keep:] if merged is None else merged[-keep:]
        self.venue_row_cap = supplied_rows if supplied_rows < keep else None


@dataclass
class BalanceEntry:
    """Free, used and total for one exchange and currency.

    ``is_stale`` turns True 10 seconds after ``fetch_time``. ``has_data`` is
    False until the first fetch lands.
    """

    exchange_id: str
    currency: str
    free: float = 0.0
    used: float = 0.0
    total: float = 0.0
    absent: bool = True
    fetch_time: float = 0.0
    subscribers: int = 0

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.fetch_time) > 10.0

    @property
    def has_data(self) -> bool:
        return self.fetch_time > 0.0


@dataclass
class TickerEntry:
    """Last, bid and ask for one exchange and symbol.

    ``is_stale`` turns True 5 seconds after ``fetch_time``.
    """

    exchange_id: str
    symbol: str
    last: float = 0
    bid: float = 0
    ask: float = 0
    volume_24h: float = 0
    timestamp: float = 0.0
    fetch_time: float = 0.0
    subscribers: int = 0

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.fetch_time) > 5.0

    @property
    def has_data(self) -> bool:
        """True once ``fetch_time`` and ``last`` are both above zero."""
        return self.fetch_time > 0.0 and self.last > 0.0


def _candle_key(exchange_id: str, symbol: str, timeframe: str) -> str:
    return f"{exchange_id}|{symbol}|{timeframe}"


def _ticker_key(exchange_id: str, symbol: str) -> str:
    return f"{exchange_id}|{symbol}"


def _balance_key(exchange_id: str, currency: str) -> str:
    return f"{exchange_id}|{currency}"


class MarketDataPool:
    """Cache of ``CacheEntry``, ``TickerEntry`` and ``BalanceEntry`` slots.

    Bots sharing an exchange, symbol and timeframe share one slot, and each
    ``get_or_fetch_*`` method fetches only when that slot is stale.
    """

    def __init__(self):
        self._candles: dict[str, CacheEntry] = {}
        self._tickers: dict[str, TickerEntry] = {}
        self._lock = asyncio.Lock()
        self._total_fetches = 0
        self._cache_hits = 0
        self._ticker_fetch_locks: dict[str, asyncio.Lock] = {}
        self._ticker_fetches = 0
        self._ticker_cache_hits = 0
        self._ticker_queue_full_skips = 0
        self._ticker_batch_refreshes = 0
        self._ticker_batch_symbols = 0
        self._ticker_batch_races = 0
        self._ohlcv_fetch_locks: dict[str, asyncio.Lock] = {}
        self._ohlcv_fetches = 0
        self._ohlcv_cache_hits = 0
        self._balances: dict[str, BalanceEntry] = {}
        self._balance_fetch_locks: dict[str, asyncio.Lock] = {}
        self._balance_fetches = 0
        self._balance_cache_hits = 0

    def register(self, exchange_id: str, symbol: str, timeframe: str):
        """Register a bot's data need. Same combo = shared cache slot."""
        key = _candle_key(exchange_id, symbol, timeframe)
        if key not in self._candles:
            self._candles[key] = CacheEntry(
                exchange_id=exchange_id, symbol=symbol, timeframe=timeframe
            )
            logger.info("DataPool: +slot %s/%s@%s", exchange_id, symbol, timeframe)
        self._candles[key].subscribers += 1

        tkey = _ticker_key(exchange_id, symbol)
        if tkey not in self._tickers:
            self._tickers[tkey] = TickerEntry(exchange_id=exchange_id, symbol=symbol)
        self._tickers[tkey].subscribers += 1

    def unregister(self, exchange_id: str, symbol: str, timeframe: str):
        """Remove a bot's subscription."""
        key = _candle_key(exchange_id, symbol, timeframe)
        entry = self._candles.get(key)
        if entry:
            entry.subscribers = max(0, entry.subscribers - 1)
            if entry.subscribers <= 0:
                del self._candles[key]

        tkey = _ticker_key(exchange_id, symbol)
        te = self._tickers.get(tkey)
        if te:
            te.subscribers = max(0, te.subscribers - 1)
            if te.subscribers <= 0:
                del self._tickers[tkey]

    def get_candles(self, exchange_id: str, symbol: str, timeframe: str) -> list:
        """Get cached OHLCV candles. Returns [] if none."""
        key = _candle_key(exchange_id, symbol, timeframe)
        entry = self._candles.get(key)
        if entry and entry.candles:
            self._cache_hits += 1
            return entry.candles
        return []

    def get_ticker(self, exchange_id: str, symbol: str) -> Optional[TickerEntry]:
        """Get cached ticker. Returns None if none."""
        tkey = _ticker_key(exchange_id, symbol)
        return self._tickers.get(tkey)

    def is_fresh(self, exchange_id: str, symbol: str, timeframe: str) -> bool:
        """Check if cached data is still within TTL."""
        key = _candle_key(exchange_id, symbol, timeframe)
        entry = self._candles.get(key)
        return entry is not None and not entry.is_stale

    async def get_or_fetch_ticker(
        self,
        connector,
        exchange_id: str,
        symbol: str,
    ):
        """Return a ``Ticker`` for ``symbol``, fetching when the entry is stale.

        Concurrent misses on one ``_ticker_key`` queue on a single lock, and a
        ``CCXTQueueFullError`` is answered from a stale entry that ``has_data``.
        """
        from .base import Ticker

        try:
            from .ccxt_connector import CCXTQueueFullError
        except Exception:
            CCXTQueueFullError = RuntimeError  # type: ignore

        tkey = _ticker_key(exchange_id, symbol)
        entry = self._tickers.get(tkey)

        if entry is not None and not entry.is_stale and entry.has_data:
            self._ticker_cache_hits += 1
            return Ticker(
                symbol=entry.symbol,
                bid=entry.bid,
                ask=entry.ask,
                last=entry.last,
                volume_24h=entry.volume_24h,
                timestamp=entry.timestamp,
            )

        # A Lock bound to a dead loop is replaced, not awaited.
        lock = self._ticker_fetch_locks.get(tkey)
        _need_new_lock = False
        if lock is None:
            _need_new_lock = True
        else:
            # asyncio.Lock records its loop in the private ``_loop`` on
            # first acquire.
            try:
                _bound_loop = getattr(lock, "_loop", None)
                _running_loop = asyncio.get_running_loop()
                if _bound_loop is not None and _bound_loop is not _running_loop:
                    logger.warning(
                        "DataPool: detected cross-loop Lock for %s/%s "
                        "(bound=%s running=%s); replacing.",
                        exchange_id,
                        symbol,
                        id(_bound_loop),
                        id(_running_loop),
                    )
                    _need_new_lock = True
            except RuntimeError:
                pass
        if _need_new_lock:
            lock = asyncio.Lock()
            self._ticker_fetch_locks[tkey] = lock

        async with cast(asyncio.Lock, lock):
            entry = self._tickers.get(tkey)
            if entry is not None and not entry.is_stale and entry.has_data:
                self._ticker_cache_hits += 1
                return Ticker(
                    symbol=entry.symbol,
                    bid=entry.bid,
                    ask=entry.ask,
                    last=entry.last,
                    volume_24h=entry.volume_24h,
                    timestamp=entry.timestamp,
                )

            # ``register`` is not a precondition; USD-conversion symbols
            # arrive here first.
            if entry is None:
                entry = TickerEntry(exchange_id=exchange_id, symbol=symbol)
                self._tickers[tkey] = entry

            try:
                ticker = await connector.get_ticker(symbol)
            except CCXTQueueFullError:
                self._ticker_queue_full_skips += 1
                if entry.has_data:
                    logger.debug(
                        "DataPool: queue-full on %s/%s; serving stale " "(age=%.1fs)",
                        exchange_id,
                        symbol,
                        time.time() - entry.fetch_time,
                    )
                    return Ticker(
                        symbol=entry.symbol,
                        bid=entry.bid,
                        ask=entry.ask,
                        last=entry.last,
                        volume_24h=entry.volume_24h,
                        timestamp=entry.timestamp,
                    )
                raise

            entry.last = float(getattr(ticker, "last", 0) or 0)
            entry.bid = float(getattr(ticker, "bid", 0) or 0)
            entry.ask = float(getattr(ticker, "ask", 0) or 0)
            entry.volume_24h = float(getattr(ticker, "volume_24h", 0) or 0)
            entry.timestamp = float(getattr(ticker, "timestamp", 0) or 0)
            entry.fetch_time = time.time()
            self._ticker_fetches += 1
            return ticker

    async def refresh_all_tickers(self, connector, exchange_id: str) -> int:
        """Refill every ``_tickers`` entry for ``exchange_id`` from one
        ``get_all_tickers`` call.

        Symbols absent from ``_tickers`` are skipped, an entry written after
        ``batch_start`` is left alone, and every exception is logged and
        swallowed. Returns the number of entries updated.
        """
        batch_start = time.time()
        try:
            raw = await connector.get_all_tickers()
        except Exception as exc:
            logger.warning(
                "DataPool: bulk ticker refresh failed for %s (%s); bots "
                "fall back to individual fetches.",
                exchange_id,
                exc,
            )
            return 0

        if not isinstance(raw, dict):
            logger.warning(
                "DataPool: bulk ticker refresh for %s returned %s, not a "
                "dict; ignoring.",
                exchange_id,
                type(raw).__name__,
            )
            return 0

        updated = 0
        for tkey, entry in list(self._tickers.items()):
            if entry.exchange_id != exchange_id:
                continue
            row = raw.get(entry.symbol)
            if not isinstance(row, dict):
                continue
            last = float(row.get("last", 0) or 0)
            if last <= 0:
                continue
            if entry.fetch_time > batch_start:
                # A newer individual fetch already wrote this entry.
                self._ticker_batch_races += 1
                continue
            # row_quote_volume_24h and millisecond timestamps match
            # CCXTConnector.get_ticker's own mapping.
            entry.last = last
            entry.bid = float(row.get("bid", 0) or 0)
            entry.ask = float(row.get("ask", 0) or 0)
            entry.volume_24h = row_quote_volume_24h(row)
            entry.timestamp = float(row.get("timestamp", 0) or 0) / 1000
            entry.fetch_time = time.time()
            updated += 1

        self._ticker_batch_refreshes += 1
        self._ticker_batch_symbols += updated
        logger.debug(
            "DataPool: bulk ticker refresh %s updated %d/%d cached "
            "entries in one call.",
            exchange_id,
            updated,
            sum(1 for e in self._tickers.values() if e.exchange_id == exchange_id),
        )
        return updated

    async def get_or_fetch_ohlcv(
        self,
        connector,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> list:
        """Return the last ``limit`` candles, fetching when the slot is stale.

        The slot lives ``CacheEntry.ttl_seconds`` for ``timeframe``, concurrent
        misses on one ``_candle_key`` queue on a single lock, and a connector
        exception propagates.
        """
        key = _candle_key(exchange_id, symbol, timeframe)
        entry = self._candles.get(key)

        if entry is not None and entry.can_serve(limit):
            self._ohlcv_cache_hits += 1
            return list(entry.candles[-limit:])

        lock = self._ohlcv_fetch_locks.get(key)
        _need_new_lock = False
        if lock is None:
            _need_new_lock = True
        else:
            try:
                _bound = getattr(lock, "_loop", None)
                _running = asyncio.get_running_loop()
                if _bound is not None and _bound is not _running:
                    logger.warning(
                        "DataPool: cross-loop OHLCV lock for %s "
                        "(bound=%s running=%s); replacing.",
                        key,
                        id(_bound),
                        id(_running),
                    )
                    _need_new_lock = True
            except RuntimeError:
                pass
        if _need_new_lock:
            lock = asyncio.Lock()
            self._ohlcv_fetch_locks[key] = lock

        async with cast(asyncio.Lock, lock):
            entry = self._candles.get(key)
            if entry is not None and entry.can_serve(limit):
                self._ohlcv_cache_hits += 1
                return list(entry.candles[-limit:])

            # ``register`` is not a precondition for a slot.
            if entry is None:
                entry = CacheEntry(
                    exchange_id=exchange_id, symbol=symbol, timeframe=timeframe
                )
                self._candles[key] = entry

            requested = max(limit, 100)
            candles = await connector.get_ohlcv(symbol, timeframe, limit=requested)
            entry.merge_fetch(list(candles or []), requested)
            entry.fetch_time = time.time()
            entry.fetch_count += 1
            self._ohlcv_fetches += 1
            return list(entry.candles[-limit:])

    async def get_or_fetch_balance(
        self,
        connector,
        exchange_id: str,
        currency: str,
    ):
        """Return a ``Balance`` for ``currency``, fetching when the entry is
        stale.

        ``BalanceEntry.is_stale`` sets the 10-second window and
        ``invalidate_balance`` ends it early.
        """
        from .base import Balance

        bkey = _balance_key(exchange_id, currency)
        entry = self._balances.get(bkey)

        if entry is not None and not entry.is_stale and entry.has_data:
            self._balance_cache_hits += 1
            return Balance(
                currency=entry.currency,
                free=entry.free,
                used=entry.used,
                total=entry.total,
                absent=entry.absent,
            )

        lock = self._balance_fetch_locks.get(bkey)
        _need_new_lock = False
        if lock is None:
            _need_new_lock = True
        else:
            try:
                _bound = getattr(lock, "_loop", None)
                _running = asyncio.get_running_loop()
                if _bound is not None and _bound is not _running:
                    logger.warning(
                        "DataPool: cross-loop balance lock for %s "
                        "(bound=%s running=%s); replacing.",
                        bkey,
                        id(_bound),
                        id(_running),
                    )
                    _need_new_lock = True
            except RuntimeError:
                pass
        if _need_new_lock:
            lock = asyncio.Lock()
            self._balance_fetch_locks[bkey] = lock

        async with cast(asyncio.Lock, lock):
            entry = self._balances.get(bkey)
            if entry is not None and not entry.is_stale and entry.has_data:
                self._balance_cache_hits += 1
                return Balance(
                    currency=entry.currency,
                    free=entry.free,
                    used=entry.used,
                    total=entry.total,
                    absent=entry.absent,
                )

            if entry is None:
                entry = BalanceEntry(exchange_id=exchange_id, currency=currency)
                self._balances[bkey] = entry

            balance = await connector.get_balance(currency)
            entry.free = float(getattr(balance, "free", 0) or 0)
            entry.used = float(getattr(balance, "used", 0) or 0)
            entry.total = float(getattr(balance, "total", 0) or 0)
            entry.absent = bool(getattr(balance, "absent", False))
            entry.currency = str(getattr(balance, "currency", currency) or currency)
            entry.fetch_time = time.time()
            self._balance_fetches += 1
            return balance

    def invalidate_balance(
        self,
        exchange_id: str,
        currency: Optional[str] = None,
    ) -> int:
        """Zero ``fetch_time`` on matching ``_balances`` slots; the next
        ``get_or_fetch_balance`` then re-fetches.

        A ``currency`` of None clears every slot for ``exchange_id``. Returns
        the number cleared.
        """
        invalidated = 0
        for bkey, entry in list(self._balances.items()):
            if entry.exchange_id != exchange_id:
                continue
            if currency is not None and entry.currency != currency:
                continue
            entry.fetch_time = 0.0
            invalidated += 1
        return invalidated

    def seconds_until_next_pull(self) -> float:
        """Return the smallest remaining TTL across the ticker, candle and
        balance slots.

        Returns inf when no slot has been fetched; ``pull_rate_summary`` is the
        only caller in ``src``.
        """
        best = float("inf")
        now = time.time()
        for te in self._tickers.values():
            if te.fetch_time <= 0:
                continue
            remaining = max(0.0, 5.0 - (now - te.fetch_time))
            if remaining < best:
                best = remaining
        for ce in self._candles.values():
            if ce.fetch_time <= 0:
                continue
            remaining = max(0.0, ce.ttl_seconds - (now - ce.fetch_time))
            if remaining < best:
                best = remaining
        for be in self._balances.values():
            if be.fetch_time <= 0:
                continue
            remaining = max(0.0, 10.0 - (now - be.fetch_time))
            if remaining < best:
                best = remaining
        return best

    def slot_ages(self) -> dict:
        """Return freshness telemetry across the ticker, candle and balance
        slots, ignoring any whose ``fetch_time`` is 0.

        The dict carries ``freshest_age_s`` and ``oldest_age_s`` (None when
        nothing has been fetched), ``fetched_slots`` and ``stale_slots``.
        """
        now = time.time()
        ages: list[tuple[float, bool]] = []  # (age, is_stale)
        for te in self._tickers.values():
            if te.fetch_time <= 0:
                continue
            age = now - te.fetch_time
            ages.append((age, age > 5.0))
        for ce in self._candles.values():
            if ce.fetch_time <= 0:
                continue
            age = now - ce.fetch_time
            ages.append((age, age > ce.ttl_seconds))
        for be in self._balances.values():
            if be.fetch_time <= 0:
                continue
            age = now - be.fetch_time
            ages.append((age, age > 10.0))
        if not ages:
            return {
                "freshest_age_s": None,
                "oldest_age_s": None,
                "fetched_slots": 0,
                "stale_slots": 0,
            }
        ages_only = [a for a, _ in ages]
        return {
            "freshest_age_s": min(ages_only),
            "oldest_age_s": max(ages_only),
            "fetched_slots": len(ages),
            "stale_slots": sum(1 for _, s in ages if s),
        }

    def pull_rate_summary(self) -> dict:
        """Return every ``slot_ages`` key plus the ticker, OHLCV and balance
        slot counts, cache hits and fetch counts.

        ``next_pull_s`` carries ``seconds_until_next_pull``, which no scheduler
        drives.
        """
        ages = self.slot_ages()
        return {
            "next_pull_s": self.seconds_until_next_pull(),
            "freshest_age_s": ages["freshest_age_s"],
            "oldest_age_s": ages["oldest_age_s"],
            "fetched_slots": ages["fetched_slots"],
            "stale_slots": ages["stale_slots"],
            "ticker_slots": len(self._tickers),
            "ohlcv_slots": len(self._candles),
            "balance_slots": len(self._balances),
            "ticker_hits": self._ticker_cache_hits,
            "ohlcv_hits": self._ohlcv_cache_hits,
            "balance_hits": self._balance_cache_hits,
            "ticker_fetches": self._ticker_fetches,
            "ohlcv_fetches": self._ohlcv_fetches,
            "balance_fetches": self._balance_fetches,
        }

    async def refresh_all(self, connectors: dict) -> dict:
        """Refresh every stale slot that still has subscribers, one connector
        call per slot.

        ``connectors`` maps an exchange_id to its connector. Returns counts
        under ``fetched``, ``skipped`` and ``errors``.
        """
        async with self._lock:
            fetched = 0
            skipped = 0
            errors = 0

            for tkey, te in self._tickers.items():
                if te.subscribers <= 0 or not te.is_stale:
                    continue
                connector = connectors.get(te.exchange_id)
                if not connector:
                    continue
                try:
                    ticker = await connector.get_ticker(te.symbol)
                    te.last = ticker.last
                    te.bid = ticker.bid
                    te.ask = ticker.ask
                    te.volume_24h = ticker.volume_24h
                    te.fetch_time = time.time()
                    fetched += 1
                except Exception as exc:
                    errors += 1
                    logger.debug(
                        "DataPool: ticker error %s/%s: %s",
                        te.exchange_id,
                        te.symbol,
                        exc,
                    )

            for key, entry in self._candles.items():
                if entry.subscribers <= 0:
                    continue
                if not entry.is_stale:
                    skipped += 1
                    continue
                connector = connectors.get(entry.exchange_id)
                if not connector:
                    continue
                try:
                    rows_requested = 100
                    candles = await connector.get_ohlcv(
                        entry.symbol, entry.timeframe, limit=rows_requested
                    )
                    entry.merge_fetch(list(candles or []), rows_requested)
                    entry.fetch_time = time.time()
                    entry.fetch_count += 1
                    fetched += 1
                    self._total_fetches += 1
                except Exception as exc:
                    entry.errors += 1
                    errors += 1
                    logger.debug(
                        "DataPool: OHLCV error %s/%s@%s: %s",
                        entry.exchange_id,
                        entry.symbol,
                        entry.timeframe,
                        exc,
                    )

            return {"fetched": fetched, "skipped": skipped, "errors": errors}

    def get_status(self) -> dict:
        unique = len(self._candles)
        total_subs = sum(e.subscribers for e in self._candles.values())
        saved = max(0, total_subs - unique)
        _t_total = self._ticker_fetches + self._ticker_cache_hits
        _t_savings_pct = round(self._ticker_cache_hits / max(_t_total, 1) * 100, 1)
        return {
            "cache_slots": unique,
            "total_subscribers": total_subs,
            "api_calls_saved": saved,
            "savings_pct": round(saved / max(total_subs, 1) * 100, 1),
            "total_fetches": self._total_fetches,
            "cache_hits": self._cache_hits,
            "ticker_slots": len(self._tickers),
            "ticker_fetches": self._ticker_fetches,
            "ticker_cache_hits": self._ticker_cache_hits,
            "ticker_queue_full_skips": self._ticker_queue_full_skips,
            "ticker_batch_refreshes": self._ticker_batch_refreshes,
            "ticker_batch_symbols": self._ticker_batch_symbols,
            "ticker_batch_races": self._ticker_batch_races,
            "ticker_savings_pct": _t_savings_pct,
        }


_pool: Optional[MarketDataPool] = None


def get_data_pool() -> MarketDataPool:
    global _pool
    if _pool is None:
        _pool = MarketDataPool()
    return _pool
