"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
data_pool.py — Shared Market Data Pool

Centralises API data fetching so that all bots on the same symbol+timeframe
share a single cached result rather than each bot making its own API call.

Architecture:
  - One data fetch per (exchange, symbol, timeframe) combination per cycle
  - Bots register their data needs; the pool fetches once and distributes
  - Stale data detection: each cache entry has a TTL matching its timeframe
  - At most one API pull per available timeframe, not one per bot

Example:
  pool = get_data_pool()
  pool.register("binance", "BTC/USDT", "5m")   # Bot A
  pool.register("binance", "BTC/USDT", "5m")   # Bot B — same cache slot
  pool.register("binance", "BTC/USDT", "1h")   # Bot C — separate slot
  await pool.refresh_all(connectors)            # 2 API calls, not 3
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, cast

logger = logging.getLogger("acervator.data_pool")

# Timeframe to seconds
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


@dataclass
class CacheEntry:
    """Cached data for one (exchange, symbol, timeframe) key."""

    exchange_id: str
    symbol: str
    timeframe: str
    candles: list = field(default_factory=list)
    fetch_time: float = 0.0
    subscribers: int = 0
    fetch_count: int = 0
    errors: int = 0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetch_time if self.fetch_time else float("inf")

    @property
    def ttl_seconds(self) -> float:
        return TF_SECONDS.get(self.timeframe, 3600)

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > self.ttl_seconds


@dataclass
class BalanceEntry:
    """Cached balance for one (exchange, currency) pair.

    v3.23.76 — mirror of TickerEntry / CacheEntry. Balances change only
    on trades or wire transfers, so a generous TTL (10s default) cuts
    the CPM burn from the 9+ get_balance sites ScrummingBot hits per
    action tick without introducing meaningful staleness."""

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
        # 10s TTL — balances change on trade fills / wire transfers,
        # which the caller's post-trade paths invalidate explicitly.
        return (time.time() - self.fetch_time) > 10.0

    @property
    def has_data(self) -> bool:
        return self.fetch_time > 0.0


@dataclass
class TickerEntry:
    """Cached ticker for one (exchange, symbol)."""

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
        return (time.time() - self.fetch_time) > 5.0  # 5s TTL for tickers

    @property
    def has_data(self) -> bool:
        """True once at least one successful fetch has populated the entry."""
        return self.fetch_time > 0.0 and self.last > 0.0


def _candle_key(exchange_id: str, symbol: str, timeframe: str) -> str:
    return f"{exchange_id}|{symbol}|{timeframe}"


def _ticker_key(exchange_id: str, symbol: str) -> str:
    return f"{exchange_id}|{symbol}"


def _balance_key(exchange_id: str, currency: str) -> str:
    return f"{exchange_id}|{currency}"


class MarketDataPool:
    """
    Shared market data pool with time-aligned caching.

    All bots on the same (exchange, symbol, timeframe) share a single
    API fetch. One call per unique combination per refresh cycle.
    """

    def __init__(self):
        self._candles: dict[str, CacheEntry] = {}
        self._tickers: dict[str, TickerEntry] = {}
        self._lock = asyncio.Lock()
        self._total_fetches = 0
        self._cache_hits = 0
        # v3.16.17 (P0d) — per-(exchange,symbol) ticker fetch locks.
        # Prevents the "thundering herd" where N bots simultaneously
        # observe a stale entry, all decide to fetch, and all flood
        # CCXT's per-connector queue. The first awaiter populates the
        # entry; the rest read from cache after the lock releases.
        self._ticker_fetch_locks: dict[str, asyncio.Lock] = {}
        # v3.16.17 — per-symbol coalesced fetch counters (telemetry only)
        self._ticker_fetches = 0
        self._ticker_cache_hits = 0
        self._ticker_queue_full_skips = 0
        self._ticker_batch_refreshes = 0
        self._ticker_batch_symbols = 0
        self._ticker_batch_races = 0
        # v3.23.74 — mirror of ticker locks for OHLCV slot fetches.
        # Prior to v3.23.74, ScrummingBot bypassed the pool for OHLCV,
        # calling self.exchange.get_ohlcv directly at two hot sites on
        # every action tick, so 35 bots × 2 hot sites =
        # ~70 raw OHLCV calls / TRACK-mode 30s cycle — the biggest
        # contributor to the operator-observed 500/600 CPM saturation.
        # Those two direct call sites no longer exist; both routed
        # through the ScrummingBot._get_ohlcv wrapper below instead.
        # v3.23.74 adds get_or_fetch_ohlcv (this pool method) + a
        # ScrummingBot._get_ohlcv wrapper that routes through it, so
        # N bots on the same (exchange, symbol, TF) share ONE fetch
        # per TF-matched TTL window.
        self._ohlcv_fetch_locks: dict[str, asyncio.Lock] = {}
        self._ohlcv_fetches = 0
        self._ohlcv_cache_hits = 0
        # v3.23.76 — balance coalescing. ScrummingBot calls
        # self.exchange.get_balance() at 9+ sites per action tick
        # (target-asset check, USD sweep, USDC sweep, sanity gates,
        # etc.). Prior to v3.23.76 those all hit the connector
        # directly. Now they share ONE fetch per (exchange, currency)
        # per 10s TTL.
        self._balances: dict[str, BalanceEntry] = {}
        self._balance_fetch_locks: dict[str, asyncio.Lock] = {}
        self._balance_fetches = 0
        self._balance_cache_hits = 0

    # ── Registration ───────────────────────────────────────────────

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

    # ── Data Access ────────────────────────────────────────────────

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

    # ── Coalesced fetch (v3.16.17 P0d) ─────────────────────────────

    async def get_or_fetch_ticker(
        self,
        connector,
        exchange_id: str,
        symbol: str,
    ):
        """Coalesced ticker fetch. One concurrent fetch per (exchange, symbol).

        Decision flow:
          1. If a fresh cache entry exists (within 5s TTL), return it
             immediately as a Ticker dataclass (zero API calls).
          2. Else acquire the per-(exchange, symbol) fetch lock.
             A second awaiter that arrives while the first is fetching
             will block here, then double-check freshness on entry —
             if the first awaiter populated the entry, the second
             returns from cache without fetching.
          3. On CCXTQueueFullError specifically: if we have ANY
             prior successful fetch (even stale), return it with a
             debug telemetry increment rather than raising. The
             caller's loop will retry next tick. If we have no prior
             data, the exception propagates so the caller can decide.

        Returns
        -------
        Ticker dataclass (from src.exchange.base). Drop-in compatible
        with the result of ``connector.get_ticker(symbol)``.

        Raises
        ------
        Whatever ``connector.get_ticker`` raises, EXCEPT
        CCXTQueueFullError when a prior cache entry exists (served
        from cache instead).
        """
        # Lazy import to avoid circular dependency at module load
        from .base import Ticker

        try:
            from .ccxt_connector import CCXTQueueFullError
        except (
            Exception
        ):  # R28-OK: import-resolution probe; defensive fallback when ccxt module unavailable
            CCXTQueueFullError = RuntimeError  # type: ignore

        tkey = _ticker_key(exchange_id, symbol)
        entry = self._tickers.get(tkey)

        # Fast path: entry exists and is fresh
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

        # Slow path: need to fetch. Get/create the per-symbol lock.
        # v3.16.19 — defense-in-depth against cross-loop Lock
        # poisoning. v3.16.19 fixed the primary cause (bootstrap
        # dispatched on a throwaway loop), but a stale Lock from
        # an in-flight operator session, or any future code path
        # that accidentally awaits on a different loop, would
        # leave the cached Lock bound to a dead loop. We detect
        # that case via RuntimeError matching "different event
        # loop" / "got Future <Future ...> attached to a different
        # loop" and self-heal by replacing the poisoned Lock.
        lock = self._ticker_fetch_locks.get(tkey)
        _need_new_lock = False
        if lock is None:
            _need_new_lock = True
        else:
            # Sanity check: if the lock has a recorded loop and it
            # differs from the current running loop, it's poisoned.
            # asyncio.Lock stores the loop it was bound to in
            # ._loop on first acquire (private API; cheap to read,
            # falls through harmlessly if attribute is missing).
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
            except (
                RuntimeError
            ):  # R28-OK: get_running_loop raises when no loop running; treat as "trust the cached lock"
                pass
        if _need_new_lock:
            lock = asyncio.Lock()
            self._ticker_fetch_locks[tkey] = lock

        # v3.23.94: pyright's flow analysis can't see that lock is
        # non-None here (either the cached lock passed the loop check
        # OR _need_new_lock allocated a fresh one). cast() narrows
        # the type at zero runtime cost — no assert (bandit B101).
        async with cast(asyncio.Lock, lock):
            # Double-check freshness — another awaiter may have
            # populated the entry while we were waiting for the lock.
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

            # Create entry if missing (e.g., USD-conversion symbols
            # that aren't formally registered)
            if entry is None:
                entry = TickerEntry(exchange_id=exchange_id, symbol=symbol)
                self._tickers[tkey] = entry

            # Actually fetch
            try:
                ticker = await connector.get_ticker(symbol)
            except CCXTQueueFullError:
                # Queue saturated. Serve last-known data if we have any.
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
                # No prior data — propagate so caller skips this iteration
                raise

            # Successful fetch — populate cache and return
            entry.last = float(getattr(ticker, "last", 0) or 0)
            entry.bid = float(getattr(ticker, "bid", 0) or 0)
            entry.ask = float(getattr(ticker, "ask", 0) or 0)
            entry.volume_24h = float(getattr(ticker, "volume_24h", 0) or 0)
            entry.timestamp = float(getattr(ticker, "timestamp", 0) or 0)
            entry.fetch_time = time.time()
            self._ticker_fetches += 1
            return ticker

    async def refresh_all_tickers(self, connector, exchange_id: str) -> int:
        """Warm every already-cached ticker for one exchange in ONE call.

        WHY THIS EXISTS (operator item 1, 2026-08-06: "the Ammo read out
        is not updating often enough")

        ``stats.current_price`` is written after the read-rate gate in
        ``ScrummingBot.tick``, so a bot's displayed price refreshes at
        its DECISION cadence. Measured on live state: 18 of 35 bots
        refreshed at 60s or slower, worst ALLO/USDC at 300s, while the
        dashboard repainted every 2s.

        The fleet runs 35 distinct symbols with zero overlap, so the
        per-symbol cache has exactly one writer each and reading it
        cannot be fresher than the bot that owns it. A bulk fetch has no
        such ceiling: ``get_all_tickers`` returns every symbol for one
        rate-limited call, where per-bot polling spends 35 to cover the
        same ground.

        Warming the shared cache here means bots hit the fast path in
        ``get_or_fetch_ticker`` instead of issuing their own request, so
        this REPLACES per-bot traffic rather than adding to it. Measured
        projection: 10,272 ticker fetches/hour becomes ~720 at a 5s
        batch interval.

        WHAT THIS DOES **NOT** FIX, corrected 2026-08-07
        An earlier version of this docstring claimed worst-case display
        staleness drops from 300s to 5s. That was wrong. The dashboard
        reads ``stats.current_price`` (``BotStatusTable.update_bots`` in
        ``src/gui/widgets/bot_status_table.py``), whose only recurring
        writer is ``ScrummingBot.tick`` in ``src/trading/scrumming_bot.py``
        -- downstream of the gate. Warming this cache does not write that field, so
        the READOUT is exactly as stale as before. What does improve is
        the price a bot sees when it does fetch, and the fleet's API
        volume. Display freshness requires a reader that consults this
        cache directly; see ``MarketDataPool.get_ticker``.

        This does NOT change any bot's decision cadence. Bots still act
        on their own gated schedule; that schedule now sees a fresher
        price. Operator ruled pool-level over display-only on 2026-08-06
        with that distinction stated.

        ONLY refreshes symbols already present in the cache. The bulk
        response carries every pair the exchange lists, and adopting all
        of them would grow this dict without bound for symbols no bot
        trades.

        Never raises. A background refresher that can take down its
        caller is worse than a stale price.

        Returns the number of entries updated.
        """
        batch_start = time.time()
        try:
            raw = await connector.get_all_tickers()
        except (
            Exception
        ) as exc:  # R28-OK: background refresher must not propagate; bots retain their own fetch path
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
                # A junk row must not blank a good entry.
                continue
            if entry.fetch_time > batch_start:
                # An individual fetch landed while this batch was in
                # flight. That value is newer; leave it alone.
                self._ticker_batch_races += 1
                continue
            # Field mapping matches CCXTConnector.get_ticker exactly:
            # volume_24h comes from quoteVolume (NOT baseVolume) and
            # timestamp is milliseconds converted to seconds. Diverging
            # here would silently corrupt the cache for every consumer.
            entry.last = last
            entry.bid = float(row.get("bid", 0) or 0)
            entry.ask = float(row.get("ask", 0) or 0)
            entry.volume_24h = float(row.get("quoteVolume", 0) or 0)
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

    # ── Coalesced OHLCV fetch (v3.23.74) ───────────────────────────

    async def get_or_fetch_ohlcv(
        self,
        connector,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> list:
        """Coalesced OHLCV fetch. Mirrors get_or_fetch_ticker.

        Cache TTL matches the timeframe (5m TF → 300s TTL, 1h → 3600s,
        etc.) so bots on the same (exchange, symbol, TF) share one
        API call per candle interval. Before v3.23.74 ScrummingBot
        called ``self.exchange.get_ohlcv`` directly on every action
        tick — with 35 bots × 30s TRACK-mode cadence that produced
        ~70 raw candle calls per minute alone.

        Behaviour:
          1. Fresh cache entry (age < TTL) with enough rows → return
             immediately (zero API calls).
          2. Stale or missing → acquire the per-slot lock; the first
             awaiter fetches, populates cache; subsequent awaiters
             hit the cache after the lock releases.
          3. On fetch exception → propagate; caller decides what to
             do (typically ScrummingBot skips the TA pass this tick).
        """
        key = _candle_key(exchange_id, symbol, timeframe)
        entry = self._candles.get(key)

        # Fast path: fresh + has enough rows
        if (
            entry is not None
            and not entry.is_stale
            and entry.candles
            and len(entry.candles) >= limit
        ):
            self._ohlcv_cache_hits += 1
            # Return the last `limit` rows (bots ask for a window
            # of the most-recent-N).
            return list(entry.candles[-limit:])

        # Slow path: acquire per-slot lock.
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

        # v3.23.94: pyright's flow analysis can't see that lock is
        # non-None here (either the cached lock passed the loop check
        # OR _need_new_lock allocated a fresh one). cast() narrows
        # the type at zero runtime cost — no assert (bandit B101).
        async with cast(asyncio.Lock, lock):
            # Double-check freshness (another awaiter may have filled)
            entry = self._candles.get(key)
            if (
                entry is not None
                and not entry.is_stale
                and entry.candles
                and len(entry.candles) >= limit
            ):
                self._ohlcv_cache_hits += 1
                return list(entry.candles[-limit:])

            # Create slot on demand (bots that never called `register`
            # for this (exchange, symbol, TF) can still coalesce here).
            if entry is None:
                entry = CacheEntry(
                    exchange_id=exchange_id, symbol=symbol, timeframe=timeframe
                )
                self._candles[key] = entry

            candles = await connector.get_ohlcv(
                symbol, timeframe, limit=max(limit, 100)
            )
            entry.candles = list(candles or [])
            entry.fetch_time = time.time()
            entry.fetch_count += 1
            self._ohlcv_fetches += 1
            return list(entry.candles[-limit:])

    # ── Coalesced balance fetch (v3.23.76) ─────────────────────────

    async def get_or_fetch_balance(
        self,
        connector,
        exchange_id: str,
        currency: str,
    ):
        """Coalesced balance fetch. Mirrors get_or_fetch_ticker /
        get_or_fetch_ohlcv.

        Cache TTL 10s: balances change on trade fills or wire
        transfers, both of which the callers explicitly invalidate
        via ``invalidate_balance`` after a fill. Between events,
        multiple balance reads for the same (exchange, currency)
        collapse to one API call per 10s window.

        Returns a ``Balance`` dataclass (matches connector.get_balance).
        """
        from .base import Balance

        bkey = _balance_key(exchange_id, currency)
        entry = self._balances.get(bkey)

        # Fast path
        if entry is not None and not entry.is_stale and entry.has_data:
            self._balance_cache_hits += 1
            return Balance(
                currency=entry.currency,
                free=entry.free,
                used=entry.used,
                total=entry.total,
                absent=entry.absent,
            )

        # Slow path — per-slot lock, cross-loop self-heal
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

        # v3.23.94: pyright's flow analysis can't see that lock is
        # non-None here (either the cached lock passed the loop check
        # OR _need_new_lock allocated a fresh one). cast() narrows
        # the type at zero runtime cost — no assert (bandit B101).
        async with cast(asyncio.Lock, lock):
            # Double-check freshness
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
        """Force the next get_or_fetch_balance for this (exchange,
        currency) to re-fetch from the connector. Called by
        post-trade paths so the freshly-adjusted balance shows up
        immediately.

        If ``currency`` is None, invalidates every balance slot for
        the exchange. Returns count invalidated.
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

    # ── Pull-rate telemetry (v3.23.74) ─────────────────────────────

    def seconds_until_next_pull(self) -> float:
        """DEPRECATED semantically. With passive on-demand coalescing
        (bots pull → cache serves; no scheduler), "seconds until next
        pull" isn't well-defined: as soon as any slot goes stale, the
        min-remaining-TTL hits 0 and stays there until a bot requests
        that slot. The GUI now uses ``freshest_age_s`` /
        ``oldest_age_s`` instead. Kept for back-compat callers.

        Returns min remaining TTL across ticker/OHLCV/balance slots,
        or inf when no slots have been fetched yet.
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
        """v3.23.76 — return freshness telemetry across all slot
        types. Ignores never-fetched slots (fetch_time=0).

        Returns dict with:
            freshest_age_s : age of the most recently fetched slot
            oldest_age_s   : age of the least recently fetched slot
            fetched_slots  : number of slots with fetch_time > 0
            stale_slots    : number of fetched slots past their TTL
        Both ages are None when no slot has been fetched yet.
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
        """Return telemetry for the GUI's pull-rate indicator.

        Fields:
            next_pull_s   — seconds until the next expected fetch
            ticker_slots  — number of ticker cache slots
            ohlcv_slots   — number of candle cache slots
            ticker_hits   — cumulative coalesced-cache hits
            ohlcv_hits    — cumulative coalesced-cache hits
            ticker_fetches — cumulative actual API pulls
            ohlcv_fetches  — cumulative actual API pulls
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

    # ── Refresh ────────────────────────────────────────────────────

    async def refresh_all(self, connectors: dict) -> dict:
        """
        Refresh all stale cache entries. One API call per unique slot.

        Parameters
        ----------
        connectors : dict[str, exchange_connector]

        Returns
        -------
        {fetched, skipped, errors}
        """
        async with self._lock:
            fetched = 0
            skipped = 0
            errors = 0

            # Refresh stale tickers
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

            # Refresh stale candle caches
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
                    candles = await connector.get_ohlcv(
                        entry.symbol, entry.timeframe, limit=100
                    )
                    entry.candles = candles
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

    # ── Status ─────────────────────────────────────────────────────

    def get_status(self) -> dict:
        unique = len(self._candles)
        total_subs = sum(e.subscribers for e in self._candles.values())
        saved = max(0, total_subs - unique)
        # v3.16.17 — ticker coalescing telemetry
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


# Singleton
_pool: Optional[MarketDataPool] = None


def get_data_pool() -> MarketDataPool:
    global _pool
    if _pool is None:
        _pool = MarketDataPool()
    return _pool
