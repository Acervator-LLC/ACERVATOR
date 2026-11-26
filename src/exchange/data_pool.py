"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
Shared market-data cache for candles, tickers and balances: ``get_data_pool`` returns
the process-wide ``MarketDataPool``, and ``SharedReads`` paces the reads that fill it.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import math
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from ..core.price_age import DEFAULT_PRICE_AGE_LIMIT_S, ReadMoment, price_age_limit_s
from ..core.tick_driver import PUMP_INTERVAL_MS
from ..trading.ta_engine import MIN_CANDLES_FOR_TA
from .api_load_monitor import DEFAULT_WINDOW_SECONDS
from .base import Ticker, in_order_turn
from .lazy_singleton import BACKOFF_FACTOR, DEFAULT_MAX_COOLOFF_S, ThrottledFault
from .market_pairs_scout import row_quote_volume_24h

logger = logging.getLogger("acervator.data_pool")

# MIN_CANDLES_FOR_TA periods per candle MIN_CANDLES_FOR_TA needs, so
# next_reach_back_ms stops at one traded row in MIN_CANDLES_FOR_TA.
REACH_BACK_PERIODS = MIN_CANDLES_FOR_TA * MIN_CANDLES_FOR_TA

#: Lifetime of a ticker slot, seconds. `TickerEntry.is_stale` is the contract.
TICKER_TTL_SECONDS = 5.0
#: Lifetime of a balance slot, seconds. `BalanceEntry.is_stale` is the contract.
BALANCE_TTL_SECONDS = 10.0

#: How long a fetch waits on a slot's lock before it asks whether the pool has
#: taken any reading at all. ``APILoadMonitor``'s rate window, which is the span
#: ``fetch_stall.STALL_THRESHOLD_SECONDS`` reports a stop over.
LOCK_WAIT_BUDGET_SECONDS = DEFAULT_WINDOW_SECONDS

#: Budgets a waiter gives a holder that is slow while other slots still refresh.
#: Four budgets is 240 s, above the 189 s one fetch can legitimately hold:
#: ``SHARED_WAIT_SECONDS``, ``READ_TURN_WAIT_SEC``, one run of
#: ``SYNC_CALL_TIMEOUT_SEC`` and the last retry backoff.
LOCK_WAIT_BUDGETS_BEFORE_CLEAR = 4

# Seconds a turn lasts for each second its reads hold the worker, which they then hold
# for two thirds of the time at most.
TURN_PER_HELD_SECOND = 1.5

# Reads in one turn of an exchange: its prices, then its account.
READS_PER_TURN = 2

# Longest a caller waits for a shared read, for its turn to ask alone or for a place.
SHARED_WAIT_SECONDS = LOCK_WAIT_BUDGET_SECONDS

# Gap between two looks of a waiting caller, one step of the app's loop.
SHARED_WAIT_SLICE_SECONDS = PUMP_INTERVAL_MS / 1000.0

# Longest an ask stays out of depth: CCXTConnector's 0.1 s request gap and two steps.
ASK_SETTLE_SECONDS = 0.1 + 2.0 * SHARED_WAIT_SLICE_SECONDS

# Places of the call queue that every caller but a shared read leaves free.
SPARE_PLACES = 1

# Age past which a ReadTurn holder counts as one that never finishes.
TURN_CEILING_SECONDS = LOCK_WAIT_BUDGET_SECONDS * LOCK_WAIT_BUDGETS_BEFORE_CLEAR

# The two kinds of shared read, each named for the ccxt call behind it.
PRICES_CALL = "fetch_tickers"
ACCOUNT_CALL = "fetch_balance"

# Header of an HTTP answer that states when to ask again, RFC 9110 section 10.2.3.
RETRY_AFTER_HEADER = "Retry-After"

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


def _row_ticker(symbol: str, row: Any, read_at: ReadMoment) -> Optional[Ticker]:
    """The ``Ticker`` one raw bulk row holds, mapped as ``CCXTConnector.get_ticker`` maps
    it, and None for a row with no ``last`` above zero."""
    if not isinstance(row, dict):
        return None
    last = float(row.get("last", 0) or 0)
    if last <= 0:
        return None
    return Ticker(
        symbol=symbol,
        bid=float(row.get("bid", 0) or 0),
        ask=float(row.get("ask", 0) or 0),
        last=last,
        volume_24h=row_quote_volume_24h(row),
        timestamp=float(row.get("timestamp", 0) or 0) / 1000,
        read_at=read_at,
    )


def longest_period_s() -> float:
    """Longest lengthened period: ``price_age_limit_s``, its default at most."""
    return min(price_age_limit_s(), DEFAULT_PRICE_AGE_LIMIT_S)


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


def _retry_after_seconds(stated: str) -> float:
    """Seconds from now a ``RETRY_AFTER_HEADER`` value names, 0.0 for neither a number
    nor a date."""
    try:
        return max(0.0, float(stated))
    except ValueError:
        pass
    try:
        at = email.utils.parsedate_to_datetime(stated).timestamp()
    except (OSError, OverflowError, TypeError, ValueError):
        return 0.0
    return max(0.0, at - time.time())


def stated_wait_seconds(exc: BaseException) -> float:
    """Seconds the ``RETRY_AFTER_HEADER`` of the HTTP answer behind ``exc`` asks for, 0.0
    without one."""
    link: Optional[BaseException] = exc
    seen: set[int] = set()
    while link is not None and id(link) not in seen:
        seen.add(id(link))
        headers = getattr(getattr(link, "response", link), "headers", None)
        read = getattr(headers, "get", None)
        stated = read(RETRY_AFTER_HEADER) if callable(read) else None
        if stated is not None:
            return _retry_after_seconds(str(stated))
        link = link.__cause__ or link.__context__
    return 0.0


def held_seconds(connector, kind: str, asked: float) -> float:
    """Seconds the run of ``kind`` that began after ``asked`` held the worker, else every
    second since ``asked``."""
    newest = getattr(connector, "latest_run", None)
    began, seconds = newest(kind) if newest is not None else (0.0, 0.0)
    return seconds if began >= asked else time.monotonic() - asked


class LinePlaces:
    """Free places of one call queue, less the asks its ``depth`` does not show yet."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._asked: list[float] = []

    def take(self, connector, spare: int) -> bool:
        """True where more than ``spare`` places are left, one of them now taken; always
        without ``sync_queue_load``."""
        reader = getattr(connector, "sync_queue_load", None)
        with self._guard:
            now = time.monotonic()
            self._asked = [at for at in self._asked if now - at < ASK_SETTLE_SECONDS]
            if reader is not None:
                load = reader()
                free = float(load["cap"]) - float(load["depth"]) - len(self._asked)
                if free <= spare:
                    return False
            self._asked.append(now)
            return True


class ReadTurn:
    """One read at a time across every thread's loop, lost past
    ``TURN_CEILING_SECONDS``."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._holder: Optional[object] = None
        self._since = 0.0
        self.displaced_s = 0.0

    def take(self) -> Optional[object]:
        """The token of the turn now held, None while another caller holds it."""
        with self._guard:
            now = time.monotonic()
            held_s = 0.0 if self._holder is None else now - self._since
            if self._holder is not None and held_s < TURN_CEILING_SECONDS:
                return None
            self.displaced_s = held_s
            self._holder = object()
            self._since = now
            return self._holder

    def give_back(self, token: object) -> None:
        """End the turn ``token`` names, unless another caller has it already."""
        with self._guard:
            if self._holder is token:
                self._holder = None


@dataclass
class SharedReads:
    """When one exchange's shared reads run, attended by ``BotManager._refresh_exchange``,
    and which callers leave a slot to them."""

    interval_s: float = 0.0
    min_rest_s: float = 0.0
    attendant: Optional[object] = None
    reading: str = ""
    due_at: float = 0.0
    turn_began: float = 0.0
    turn_reads: int = 0
    held_s: float = 0.0
    steps: int = 0
    unanswered: bool = False
    wait_until: float = 0.0
    answered_at: float = 0.0
    answer_s: dict[str, float] = field(
        default_factory=lambda: {PRICES_CALL: 0.0, ACCOUNT_CALL: 0.0}
    )
    lost_at: dict[str, float] = field(default_factory=dict)
    refused: set[str] = field(default_factory=set)
    places: LinePlaces = field(default_factory=LinePlaces)
    account_turn: ReadTurn = field(default_factory=ReadTurn)
    price_turn: ReadTurn = field(default_factory=ReadTurn)

    def attend(self, interval_s: float, min_rest_s: float) -> object:
        """Serve callers every ``interval_s`` from now, and answer the token ``leave``
        takes."""
        self.interval_s = interval_s
        self.min_rest_s = min_rest_s
        self.reading = ""
        self.turn_reads = 0
        self.held_s = 0.0
        self.unanswered = False
        self.due_at = time.monotonic()
        self.attendant = object()
        return self.attendant

    def leave(self, token: object) -> None:
        """Stop serving callers, unless another refresher attends by now."""
        if self.attendant is token:
            self.attendant = None

    def open_read(self) -> None:
        """Count one read about to be asked, the first of which begins a turn."""
        if self.turn_reads == 0:
            self.turn_began = time.monotonic()
        self.turn_reads += 1

    @contextmanager
    def on_its_way(self, kind: str) -> Iterator[None]:
        """Name ``kind`` as the read on its way inside the block."""
        self.reading = kind
        try:
            yield
        finally:
            self.reading = ""

    def note_good(self, kind: str) -> None:
        """Note an answer of ``kind``, which takes back one of ``steps``."""
        self.refused.discard(kind)
        self.lost_at.pop(kind, None)
        self.steps = max(0, self.steps - 1)
        self.answered_at = time.monotonic()

    def note_failed(self, kind: str, exc: BaseException) -> bool:
        """True where ``exc`` lost or throttled a read of ``kind``, adding to ``steps``;
        the venue's own refusal adds to ``refused``."""
        from .ccxt_connector import (
            VENUE_LOST,
            VENUE_RATE_LIMITED,
            CCXTQueueFullError,
            classify_venue_refusal,
        )

        if isinstance(exc, CCXTQueueFullError):
            return False
        label = classify_venue_refusal(exc)
        self.lost_at.pop(kind, None)
        if label not in (VENUE_LOST, VENUE_RATE_LIMITED):
            self.refused.add(kind)
            return False
        self.refused.discard(kind)
        if 0.0 < self.interval_s * BACKOFF_FACTOR**self.steps < longest_period_s():
            self.steps += 1
        if label == VENUE_LOST:
            self.lost_at[kind] = time.monotonic()
        else:
            stated = min(stated_wait_seconds(exc), DEFAULT_MAX_COOLOFF_S)
            self.wait_until = max(self.wait_until, time.monotonic() + stated)
        return True

    def period_s(self) -> float:
        """Seconds from one turn to the next, from ``held_s`` and ``steps``."""
        own = max(self.interval_s, self.held_s * TURN_PER_HELD_SECOND)
        return max(own, min(own * BACKOFF_FACTOR**self.steps, longest_period_s()))

    def rest_s(self) -> float:
        """Seconds to rest after a read; ``READS_PER_TURN`` of them end a turn, as one
        ``unanswered`` does."""
        now = time.monotonic()
        rest = max(0.0, self.wait_until - now)
        if self.unanswered or self.turn_reads >= READS_PER_TURN:
            paced = max(self.min_rest_s, self.turn_began + self.period_s() - now)
            if self.unanswered:
                paced = min(paced, longest_period_s())
            rest = max(rest, paced)
            self.held_s = 0.0
            self.turn_reads = 0
            self.unanswered = False
        self.due_at = now + rest
        return rest

    def slowed(self) -> bool:
        """True while ``steps`` or a stated wait lengthens the period of an attended
        exchange."""
        if self.attendant is None:
            return False
        return self.steps > 0 or time.monotonic() < self.wait_until

    def left_alone(self, kind: str) -> bool:
        """True where callers ask alone: the venue refused ``kind``, or lost the shared
        prices and has answered another call since."""
        if kind in self.refused:
            return True
        lost_at = self.lost_at.get(kind, math.inf)
        return kind == PRICES_CALL and lost_at < self.answered_at

    def awaited(self, kind: str, ends_at: float) -> bool:
        """True while a caller leaves an expired slot to ``kind``; one on its way or due
        soon counts until ``ends_at``."""
        now = time.monotonic()
        if self.attendant is None:
            return False
        if self.left_alone(kind):
            return kind in self.refused and self.reading == kind and now < ends_at
        if self.slowed():
            return True
        soon = self.due_at - now <= sum(self.answer_s.values())
        return now < ends_at and (bool(self.reading) or soon)

    def replaces(self, kind: str, age_s: float) -> bool:
        """True where ``age_s`` passes ``interval_s`` and the newest answers with
        ``min_rest_s``, so a caller waits for the next read."""
        if self.attendant is None or self.left_alone(kind):
            return False
        answers_s = sum(self.answer_s.values())
        return age_s > max(self.interval_s, answers_s + self.min_rest_s)


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
    reach_back_since: Optional[int] = None

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

    def next_reach_back_ms(self, requested: int) -> Optional[int]:
        """Epoch milliseconds of the window before the oldest row or last
        ``reach_back_since``, recorded, None at ``MIN_CANDLES_FOR_TA`` rows or past
        ``REACH_BACK_PERIODS``."""
        if self.venue_row_cap is None or len(self.candles) >= MIN_CANDLES_FOR_TA:
            return None
        stamps = [
            at for at in (_row_timestamp(row) for row in self.candles) if at is not None
        ]
        if not stamps:
            return None
        edge = min(stamps)
        if self.reach_back_since is not None:
            edge = min(edge, float(self.reach_back_since))
        period = TF_SECONDS.get(self.timeframe, 3600)
        since = int(edge) - max(1, int(requested)) * period * 1000
        if since < int((time.time() - REACH_BACK_PERIODS * period) * 1000):
            return None
        self.reach_back_since = since
        return since


@dataclass
class BalanceEntry:
    """Free, used and total for one exchange and currency.

    ``is_stale`` turns True 10 seconds after ``fetch_time``. ``has_data`` is
    False until the first fetch lands. ``end_count`` is the pool's
    ``_balance_end_count`` when ``invalidate_balance`` last ended this slot.
    ``answered`` turns True when a venue answer first writes the figures, and
    ``invalidate_balance`` leaves it.
    """

    exchange_id: str
    currency: str
    free: float = 0.0
    used: float = 0.0
    total: float = 0.0
    absent: bool = True
    fetch_time: float = 0.0
    subscribers: int = 0
    end_count: int = 0
    answered: bool = False

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetch_time

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > BALANCE_TTL_SECONDS

    @property
    def has_data(self) -> bool:
        return self.fetch_time > 0.0

    @property
    def is_fresh(self) -> bool:
        """True where the slot ``has_data`` and is not ``is_stale``."""
        return self.has_data and not self.is_stale

    @property
    def ended(self) -> bool:
        """True from ``invalidate_balance`` to the next answer begun after it."""
        return self.end_count > 0 and not self.has_data


@dataclass(slots=True)
class TickerEntry:
    """Last, bid and ask for one exchange and symbol, and ``read_at``, the moment the
    venue answered them.

    ``is_stale`` turns True 5 seconds after ``read_at``, and ``left_out`` where the
    newest shared answer asked for this slot held no price.
    """

    exchange_id: str
    symbol: str
    last: float = 0
    bid: float = 0
    ask: float = 0
    volume_24h: float = 0
    timestamp: float = 0.0
    read_at: Optional[ReadMoment] = None
    subscribers: int = 0
    left_out: bool = False

    @classmethod
    def answered_now(
        cls, exchange_id: str, symbol: str, **figures: float
    ) -> TickerEntry:
        """A slot holding ``figures`` the venue answered at this moment."""
        return cls(exchange_id, symbol, read_at=ReadMoment.now(), **figures)

    @property
    def age_seconds(self) -> float:
        """Seconds since ``read_at``, infinite before the first read."""
        return math.inf if self.read_at is None else self.read_at.age_s()

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > TICKER_TTL_SECONDS

    @property
    def has_data(self) -> bool:
        """True once a read left ``last`` above zero."""
        return self.read_at is not None and self.last > 0.0

    @property
    def is_fresh(self) -> bool:
        """True where the slot ``has_data`` and is not ``is_stale``."""
        return self.has_data and not self.is_stale

    def take(self, ticker: Ticker) -> bool:
        """Hold the figures of ``ticker``, and answer False where this slot already holds
        a later read."""
        if self.read_at is not None and ticker.read_at.before(self.read_at):
            return False
        self.last = float(ticker.last or 0)
        self.bid = float(ticker.bid or 0)
        self.ask = float(ticker.ask or 0)
        self.volume_24h = float(ticker.volume_24h or 0)
        self.timestamp = float(ticker.timestamp or 0)
        self.read_at = ticker.read_at
        return True

    def ticker(self) -> Ticker:
        """This slot as the ``Ticker`` a connector answers, its ``read_at`` included."""
        return Ticker(
            symbol=self.symbol,
            bid=self.bid,
            ask=self.ask,
            last=self.last,
            volume_24h=self.volume_24h,
            timestamp=self.timestamp,
            read_at=self.read_at or ReadMoment(0.0),
        )


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
        self._balance_fetches = 0
        self._balance_cache_hits = 0
        self._balance_batch_fills = 0
        self._balance_batch_slots = 0
        self._balance_end_count = 0
        self._shared_reads: dict[str, SharedReads] = {}
        self._slot_turns: dict[str, ReadTurn] = {}
        self._wedged_locks_cleared = 0
        self._fetch_lock_fault = ThrottledFault(
            "exchange fetching through the shared market data pool",
            "Prices, balances and candles stop updating.",
        )

    @property
    def wedged_locks_cleared(self) -> int:
        """Fetch locks replaced because their holder never finished."""
        return self._wedged_locks_cleared

    def _live_lock(
        self, locks: dict[str, asyncio.Lock], key: str, label: str
    ) -> asyncio.Lock:
        """The fetch lock for ``key``, replacing one bound to a dead loop.

        ``asyncio.Lock`` records its loop in the private ``_loop`` on first
        acquire, and acquiring it from another loop raises rather than waits.
        """
        lock = locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            locks[key] = lock
            return lock
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            return lock
        bound = getattr(lock, "_loop", None)
        if bound is not None and bound is not running:
            logger.warning(
                "DataPool: cross-loop fetch lock for %s (bound=%s running=%s); "
                "replacing.",
                label,
                id(bound),
                id(running),
            )
            lock = asyncio.Lock()
            locks[key] = lock
        return lock

    def _no_reading_landed(self) -> bool:
        """True when the freshest slot in the pool is past the wait budget.

        A reading landing on any slot means the venue is answering and a waiter
        on one lock is merely queued behind another fetch.
        """
        freshest = self.slot_ages()["freshest_age_s"]
        return freshest is None or float(freshest) > LOCK_WAIT_BUDGET_SECONDS

    async def _clear_wedged_lock(
        self, locks: dict[str, asyncio.Lock], key: str, label: str, waited_s: float
    ) -> asyncio.Lock:
        """Replace ``key``'s lock with a fresh one this caller holds.

        The holder of the old lock keeps it and is abandoned. Reporting carries
        ``ThrottledFault``'s window, so a venue that stays blocked costs one
        Console line per widening window rather than one per slot per wait.
        """
        self._wedged_locks_cleared += 1
        self._fetch_lock_fault.note_cleared(label, waited_s)
        fresh = asyncio.Lock()
        locks[key] = fresh
        await fresh.acquire()
        return fresh

    async def _acquire_fetch_lock(
        self, locks: dict[str, asyncio.Lock], key: str, label: str
    ) -> asyncio.Lock:
        """Return the held fetch lock for ``key``. Never waits without a bound.

        Concurrent misses on one ``key`` still queue on one lock. A waiter that
        reaches ``LOCK_WAIT_BUDGET_SECONDS`` while no slot in the pool took a
        reading treats the holder as blocked and clears the lock, so a stop
        recovers on the next fetch instead of on a restart. One that reaches it
        while the pool is still refreshing waits again, up to
        ``LOCK_WAIT_BUDGETS_BEFORE_CLEAR`` budgets, so a slow read that still
        returns keeps its lock.
        """
        ceiling_s = LOCK_WAIT_BUDGET_SECONDS * LOCK_WAIT_BUDGETS_BEFORE_CLEAR
        waited_s = 0.0
        while True:
            lock = self._live_lock(locks, key, label)
            try:
                await asyncio.wait_for(lock.acquire(), LOCK_WAIT_BUDGET_SECONDS)
                return lock
            except asyncio.TimeoutError:
                waited_s += LOCK_WAIT_BUDGET_SECONDS
            if waited_s >= ceiling_s or self._no_reading_landed():
                return await self._clear_wedged_lock(locks, key, label, waited_s)

    def shared_reads(self, exchange_id: str) -> SharedReads:
        """The one ``SharedReads`` of ``exchange_id``."""
        return self._shared_reads.setdefault(exchange_id, SharedReads())

    def _take_turn(self, turn: ReadTurn, label: str) -> Optional[object]:
        """``turn.take``, counting a holder it displaced as a lock cleared."""
        token = turn.take()
        if token is not None and turn.displaced_s > 0.0:
            self._wedged_locks_cleared += 1
            self._fetch_lock_fault.note_cleared(label, turn.displaced_s)
        return token

    async def _turn_to_ask(
        self,
        turn: ReadTurn,
        connector,
        reads: SharedReads,
        label: str,
        served: Callable[[], bool],
        awaits: Callable[[float], bool],
    ) -> Optional[object]:
        """A token of ``turn`` once this caller has to ask alone, None once ``served``;
        in an order's step, one no turn holds at once.

        Raises:
            asyncio.TimeoutError: neither came inside ``SHARED_WAIT_SECONDS``.
        """
        if in_order_turn():
            return None if served() else object()
        ends_at = time.monotonic() + SHARED_WAIT_SECONDS
        while not served():
            now = time.monotonic()
            if now >= reads.wait_until and not awaits(ends_at):
                token = self._ask_alone(turn, connector, reads, label)
                if token is not None:
                    return token
            if now >= ends_at:
                raise asyncio.TimeoutError(
                    f"{label} did not come in {SHARED_WAIT_SECONDS:.0f}s"
                )
            await asyncio.sleep(SHARED_WAIT_SLICE_SECONDS)
        return None

    def _ask_alone(
        self, turn: ReadTurn, connector, reads: SharedReads, label: str
    ) -> Optional[object]:
        """A token of ``turn`` with a place in the call queue, None without both."""
        token = self._take_turn(turn, label)
        if token is None or reads.places.take(connector, SPARE_PLACES):
            return token
        turn.give_back(token)
        return None

    async def _await_place(self, connector, exchange_id: str, spare: int) -> None:
        """Take a place past ``spare`` in the call queue, after a wait of
        ``SHARED_WAIT_SECONDS`` at most."""
        places = self.shared_reads(exchange_id).places
        ends_at = time.monotonic() + SHARED_WAIT_SECONDS
        while not places.take(connector, spare) and time.monotonic() < ends_at:
            await asyncio.sleep(SHARED_WAIT_SLICE_SECONDS)

    async def _noted_read(
        self,
        connector,
        exchange_id: str,
        kind: str,
        read: Callable[[], Awaitable[Any]],
    ) -> Any:
        """What ``read`` answers from a free place, its outcome and the worker's seconds
        noted in ``shared_reads``."""
        from .ccxt_connector import run_timed_as

        reads = self.shared_reads(exchange_id)
        await self._await_place(connector, exchange_id, 0)
        asked = time.monotonic()
        try:
            with run_timed_as(kind):
                answer = await read()
        except Exception as exc:
            reads.unanswered = reads.note_failed(kind, exc)
            reads.held_s += held_seconds(connector, kind, asked)
            raise
        reads.note_good(kind)
        reads.answer_s[kind] = held_seconds(connector, kind, asked)
        reads.held_s += reads.answer_s[kind]
        return answer

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

    def _ticker_slot(self, exchange_id: str, symbol: str) -> TickerEntry:
        """The slot of ``symbol``, made here for one ``register`` never named."""
        tkey = _ticker_key(exchange_id, symbol)
        entry = self._tickers.get(tkey)
        if entry is not None:
            return entry
        fresh = TickerEntry(exchange_id=exchange_id, symbol=symbol)
        return self._tickers.setdefault(tkey, fresh)

    def _price_turn(self, connector, exchange_id: str, symbol: str) -> ReadTurn:
        """The turn of a price asked alone: one for a call queue, else one for a slot."""
        if hasattr(connector, "sync_queue_load"):
            return self.shared_reads(exchange_id).price_turn
        key = f"price|{_ticker_key(exchange_id, symbol)}"
        return self._slot_turns.setdefault(key, ReadTurn())

    async def get_or_fetch_ticker(
        self,
        connector,
        exchange_id: str,
        symbol: str,
    ) -> Ticker:
        """The ``Ticker`` of ``symbol`` from its slot, the shared price read on its way
        or due, or one ``get_ticker``."""
        reads = self.shared_reads(exchange_id)
        bulk = hasattr(connector, "get_all_tickers")

        def slot() -> TickerEntry:
            return self._ticker_slot(exchange_id, symbol)

        def served() -> bool:
            entry = slot()
            if not entry.is_fresh:
                return False
            listed = bulk and not entry.left_out
            return not (listed and reads.replaces(PRICES_CALL, entry.age_seconds))

        def awaits(ends_at: float) -> bool:
            entry = slot()
            if not bulk or entry.left_out:
                return False
            return entry.is_fresh or reads.awaited(PRICES_CALL, ends_at)

        turn = self._price_turn(connector, exchange_id, symbol)
        label = f"the price for {symbol} on {exchange_id}"
        token = await self._turn_to_ask(turn, connector, reads, label, served, awaits)
        if token is None:
            self._ticker_cache_hits += 1
            return slot().ticker()
        try:
            return await self._ask_ticker(connector, slot())
        finally:
            turn.give_back(token)

    async def _ask_ticker(self, connector, entry: TickerEntry) -> Ticker:
        """``entry`` after one ``get_ticker``; a full queue answers where it ``has_data``,
        whose ``Ticker.read_at`` says how old it is."""
        from .ccxt_connector import CCXTQueueFullError

        try:
            entry.take(await connector.get_ticker(entry.symbol))
        except CCXTQueueFullError:
            self._ticker_queue_full_skips += 1
            if not entry.has_data:
                raise
            logger.debug(
                "DataPool: queue-full on %s/%s; serving stale (age=%.1fs)",
                entry.exchange_id,
                entry.symbol,
                entry.age_seconds,
            )
            return entry.ticker()
        self.shared_reads(entry.exchange_id).answered_at = time.monotonic()
        self._ticker_fetches += 1
        return entry.ticker()

    def _slots_held(self, slots: dict, exchange_id: str) -> int:
        """How many of ``slots`` belong to ``exchange_id``; a refresh of none makes no
        venue call."""
        held = list(slots.values())
        return sum(1 for slot in held if slot.exchange_id == exchange_id)

    async def refresh_all_tickers(self, connector, exchange_id: str) -> int:
        """Refill every ``_tickers`` entry for ``exchange_id`` from one
        ``get_all_tickers`` call given their symbols, and return how many it updated.

        An ``exchange_id`` with no entry makes no call, and every exception is logged
        and noted in its ``SharedReads``. Rows that carry no ``read_at`` of their own
        count from the ask.
        """
        reader = getattr(connector, "get_all_tickers", None)
        if reader is None or not self._slots_held(self._tickers, exchange_id):
            return 0
        reads = self.shared_reads(exchange_id)
        asked: list[str] = []
        asked_at = ReadMoment.now()

        async def read() -> Any:
            nonlocal asked, asked_at
            asked = [
                entry.symbol
                for entry in list(self._tickers.values())
                if entry.exchange_id == exchange_id
            ]
            asked_at = ReadMoment.now()
            return await reader(asked)

        with reads.on_its_way(PRICES_CALL):
            try:
                raw = await self._noted_read(connector, exchange_id, PRICES_CALL, read)
            except Exception as exc:
                # The text of a failed request holds its URL, whose query lists symbols.
                said = " ".join(word.partition("?")[0] for word in str(exc).split(" "))
                logger.warning(
                    "DataPool: shared price read of %s failed (%s: %s)",
                    exchange_id,
                    type(exc).__name__,
                    said,
                )
                return 0
            if not isinstance(raw, dict):
                reads.refused.add(PRICES_CALL)
                logger.warning(
                    "DataPool: bulk ticker refresh for %s returned %s, not a "
                    "dict; ignoring.",
                    exchange_id,
                    type(raw).__name__,
                )
                return 0
            read_at = getattr(raw, "read_at", asked_at)
            return self._fill_ticker_entries(exchange_id, raw, set(asked), read_at)

    def _fill_ticker_entries(
        self, exchange_id: str, raw: dict, asked: set[str], read_at: ReadMoment
    ) -> int:
        """Write every ``_tickers`` slot ``raw`` prices, and return how many.

        One in ``asked`` that ``raw`` does not price is ``left_out``, and one holding a
        read later than ``read_at`` is left alone.
        """
        updated = 0
        held = 0
        for entry in list(self._tickers.values()):
            if entry.exchange_id != exchange_id:
                continue
            held += 1
            answered = _row_ticker(entry.symbol, raw.get(entry.symbol), read_at)
            entry.left_out = answered is None and entry.symbol in asked
            if answered is None:
                continue
            if not entry.take(answered):
                # A newer individual fetch already wrote this entry.
                self._ticker_batch_races += 1
                continue
            updated += 1

        self._ticker_batch_refreshes += 1
        self._ticker_batch_symbols += updated
        logger.debug(
            "DataPool: bulk ticker refresh %s updated %d/%d cached "
            "entries in one call.",
            exchange_id,
            updated,
            held,
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

        lock = await self._acquire_fetch_lock(
            self._ohlcv_fetch_locks,
            key,
            f"the {timeframe} candles for {symbol} on {exchange_id}",
        )
        try:
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
            await self._await_place(connector, exchange_id, SPARE_PLACES)
            candles = await connector.get_ohlcv(
                symbol,
                timeframe,
                limit=requested,
                since=entry.next_reach_back_ms(requested),
            )
            entry.merge_fetch(list(candles or []), requested)
            entry.fetch_time = time.time()
            entry.fetch_count += 1
            self._ohlcv_fetches += 1
            return list(entry.candles[-limit:])
        finally:
            lock.release()

    def _balance_slot(self, exchange_id: str, currency: str) -> BalanceEntry:
        """The slot of ``currency``, made here on its first ask."""
        bkey = _balance_key(exchange_id, currency)
        entry = self._balances.get(bkey)
        if entry is not None:
            return entry
        fresh = BalanceEntry(exchange_id=exchange_id, currency=currency)
        return self._balances.setdefault(bkey, fresh)

    def _balance_turn(self, connector, exchange_id: str, currency: str) -> ReadTurn:
        """The turn of a balance asked alone: one for an account, else one for a slot."""
        if hasattr(connector, "get_account_balances"):
            return self.shared_reads(exchange_id).account_turn
        key = f"balance|{_balance_key(exchange_id, currency)}"
        return self._slot_turns.setdefault(key, ReadTurn())

    async def get_or_fetch_balance(
        self,
        connector,
        exchange_id: str,
        currency: str,
    ):
        """Return a ``Balance`` for ``currency`` from its slot, the account read on its
        way or due, or one account read of its own.

        ``BalanceEntry.is_stale`` sets the 10-second window, ``invalidate_balance``
        ends it early, and a read during which ``invalidate_balance`` ends this slot
        is taken again.
        """
        from .base import Balance

        reads = self.shared_reads(exchange_id)
        bulk = hasattr(connector, "get_account_balances")

        def slot() -> BalanceEntry:
            return self._balance_slot(exchange_id, currency)

        def served() -> bool:
            entry = slot()
            if not entry.is_fresh:
                return False
            return not (bulk and reads.replaces(ACCOUNT_CALL, entry.age_seconds))

        def awaits(ends_at: float) -> bool:
            entry = slot()
            if not bulk:
                return False
            if entry.ended:
                return reads.slowed()
            return entry.is_fresh or reads.awaited(ACCOUNT_CALL, ends_at)

        turn = self._balance_turn(connector, exchange_id, currency)
        label = f"the {currency} balance on {exchange_id}"
        token = await self._turn_to_ask(turn, connector, reads, label, served, awaits)
        if token is None:
            self._balance_cache_hits += 1
            entry = slot()
            return Balance(
                currency=entry.currency,
                free=entry.free,
                used=entry.used,
                total=entry.total,
                absent=entry.absent,
            )
        try:
            return await self._ask_balance(connector, slot())
        finally:
            turn.give_back(token)

    async def _ask_balance(self, connector, entry: BalanceEntry):
        """The ``Balance`` of ``entry`` from one account read, or ``get_balance`` without
        one; a read ``invalidate_balance`` ended is taken again."""
        from .base import Balance

        exchange_id, currency = entry.exchange_id, entry.currency
        ends_at = time.monotonic() + SHARED_WAIT_SECONDS
        while True:
            begun = self._balance_end_count
            reported = await self._read_account(connector, exchange_id)
            if reported is None:
                balance = await connector.get_balance(currency)
                self._balance_fetches += 1
                if entry.end_count > begun:
                    self._note_read_again(exchange_id, currency, ends_at)
                    continue
                self._write_balance_entry(entry, currency, balance)
                return balance

            self._fill_balance_entries(exchange_id, reported, begun)
            self._balance_fetches += 1
            if entry.end_count > begun:
                self._note_read_again(exchange_id, currency, ends_at)
                continue
            held = reported.get(currency)
            if held is not None:
                return held
            absent = Balance(
                currency=currency, free=0.0, used=0.0, total=0.0, absent=True
            )
            self._write_balance_entry(entry, currency, absent)
            return absent

    @staticmethod
    def _note_read_again(exchange_id: str, currency: str, ends_at: float) -> None:
        """Log one ``get_or_fetch_balance`` read that ``invalidate_balance`` ended.

        Raises:
            asyncio.TimeoutError: ``ends_at`` has passed.
        """
        if time.monotonic() >= ends_at:
            raise asyncio.TimeoutError(
                f"fills ended every read of the {currency} balance on {exchange_id} "
                f"for {SHARED_WAIT_SECONDS:.0f}s"
            )
        logger.debug(
            "DataPool: the %s balance on %s was ended while its read was in "
            "flight; reading it again.",
            currency,
            exchange_id,
        )

    async def _read_account(self, connector, exchange_id: str):
        """One account read naming every currency, None where ``connector`` has none, and
        its error raised with no second read."""
        reader = getattr(connector, "get_account_balances", None)
        if reader is None:
            return None
        reads = self.shared_reads(exchange_id)
        try:
            reported = await reader()
        except Exception as exc:
            reads.note_failed(ACCOUNT_CALL, exc)
            raise
        reads.note_good(ACCOUNT_CALL)
        if isinstance(reported, dict):
            return reported
        reads.refused.add(ACCOUNT_CALL)
        return None

    def _fill_balance_entries(
        self, exchange_id: str, reported: dict, begun: int
    ) -> int:
        """Write every ``_balances`` slot this exchange holds from one account read
        begun at ``_balance_end_count`` ``begun``, and return how many it filled.

        A slot ``invalidate_balance`` ended after ``begun`` stays stale, and a
        currency the read reports a holding in gets a slot it did not have.
        """
        from .base import Balance

        now = time.time()
        for currency, held in reported.items():
            if float(getattr(held, "total", 0) or 0) <= 0:
                continue
            bkey = _balance_key(exchange_id, currency)
            if bkey not in self._balances:
                self._balances[bkey] = BalanceEntry(
                    exchange_id=exchange_id, currency=currency
                )
        filled = 0
        for slot in list(self._balances.values()):
            if slot.exchange_id != exchange_id:
                continue
            if slot.end_count > begun:
                continue
            held = reported.get(slot.currency)
            if held is None:
                held = Balance(
                    currency=slot.currency,
                    free=0.0,
                    used=0.0,
                    total=0.0,
                    absent=True,
                )
            self._write_balance_entry(slot, slot.currency, held, at=now)
            filled += 1
        self._balance_batch_fills += 1
        self._balance_batch_slots += filled
        logger.debug(
            "DataPool: one account read filled %d/%d balance slots for %s.",
            filled,
            sum(1 for s in self._balances.values() if s.exchange_id == exchange_id),
            exchange_id,
        )
        return filled

    @staticmethod
    def _write_balance_entry(
        entry: "BalanceEntry",
        currency: str,
        balance,
        at: Optional[float] = None,
    ) -> None:
        """Copy one ``Balance`` into a ``BalanceEntry`` and stamp its fetch time."""
        entry.free = float(getattr(balance, "free", 0) or 0)
        entry.used = float(getattr(balance, "used", 0) or 0)
        entry.total = float(getattr(balance, "total", 0) or 0)
        entry.absent = bool(getattr(balance, "absent", False))
        entry.currency = str(getattr(balance, "currency", currency) or currency)
        entry.fetch_time = time.time() if at is None else at
        entry.answered = True

    def answered_totals(
        self, currencies: tuple
    ) -> dict[str, dict[str, Optional[float]]]:
        """``total`` per exchange and currency in ``currencies``, read from ``_balances``
        with no venue call; a slot no answer has written reads None."""
        held: dict[str, dict[str, Optional[float]]] = {}
        for slot in list(self._balances.values()):
            if slot.currency in currencies:
                held.setdefault(slot.exchange_id, {})[slot.currency] = (
                    slot.total if slot.answered else None
                )
        return held

    async def refresh_all_balances(self, connector, exchange_id: str) -> int:
        """Refill every ``_balances`` slot for ``exchange_id`` from one account read.

        Returns the number of slots filled, and zero without a venue call when
        this exchange holds no balance slot, the connector serves no account
        read, or the read raised.
        """
        if not hasattr(connector, "get_account_balances"):
            return 0
        if not self._slots_held(self._balances, exchange_id):
            return 0
        reads = self.shared_reads(exchange_id)
        once = getattr(connector, "get_account_balances_once", None)
        reader = connector.get_account_balances if once is None else once
        begun = self._balance_end_count

        async def read() -> Any:
            nonlocal begun
            begun = self._balance_end_count
            return await reader()

        with reads.on_its_way(ACCOUNT_CALL):
            token = await self._hold_account_turn(reads, exchange_id)
            if token is None:
                return 0
            try:
                reported = await self._noted_read(
                    connector, exchange_id, ACCOUNT_CALL, read
                )
                if not isinstance(reported, dict):
                    reads.refused.add(ACCOUNT_CALL)
                    return 0
                return self._fill_balance_entries(exchange_id, reported, begun)
            except Exception as exc:
                logger.warning(
                    "DataPool: shared account read of %s failed (%s: %s)",
                    exchange_id,
                    type(exc).__name__,
                    exc,
                )
                return 0
            finally:
                reads.account_turn.give_back(token)

    async def _hold_account_turn(
        self, reads: SharedReads, exchange_id: str
    ) -> Optional[object]:
        """A token of ``account_turn``, None where a caller's read kept it for
        ``interval_s``."""
        ends_at = time.monotonic() + reads.interval_s
        label = f"the account read of {exchange_id}"
        while True:
            token = self._take_turn(reads.account_turn, label)
            if token is not None or time.monotonic() >= ends_at:
                return token
            await asyncio.sleep(SHARED_WAIT_SLICE_SECONDS)

    def invalidate_balance(
        self,
        exchange_id: str,
        currency: Optional[str] = None,
    ) -> int:
        """Zero ``fetch_time`` on matching ``_balances`` slots and stamp each with a
        new ``_balance_end_count``; the next ``get_or_fetch_balance`` then re-fetches.

        A ``currency`` of None clears every slot for ``exchange_id``. Returns
        the number cleared.
        """
        self._balance_end_count += 1
        invalidated = 0
        for bkey, entry in list(self._balances.items()):
            if entry.exchange_id != exchange_id:
                continue
            if currency is not None and entry.currency != currency:
                continue
            entry.fetch_time = 0.0
            entry.end_count = self._balance_end_count
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
            if te.read_at is None:
                continue
            remaining = max(0.0, TICKER_TTL_SECONDS - te.age_seconds)
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
            remaining = max(0.0, BALANCE_TTL_SECONDS - (now - be.fetch_time))
            if remaining < best:
                best = remaining
        return best

    def slot_ages(self) -> dict:
        """Return freshness telemetry across the ticker, candle and balance
        slots, ignoring any that was never read.

        The dict carries ``freshest_age_s`` and ``oldest_age_s`` (None when
        nothing has been fetched), ``fetched_slots`` and ``stale_slots``.
        """
        now = time.time()
        ages: list[tuple[float, bool]] = []  # (age, is_stale)
        for te in self._tickers.values():
            if te.read_at is None:
                continue
            age = te.age_seconds
            ages.append((age, age > TICKER_TTL_SECONDS))
        for ce in self._candles.values():
            if ce.fetch_time <= 0:
                continue
            age = now - ce.fetch_time
            ages.append((age, age > ce.ttl_seconds))
        for be in self._balances.values():
            if be.fetch_time <= 0:
                continue
            age = now - be.fetch_time
            ages.append((age, age > BALANCE_TTL_SECONDS))
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
        drives. ``wedged_locks_cleared`` is what the Exchange sub-tab's data
        pool line draws beside the red stopped line.
        """
        ages = self.slot_ages()
        return {
            "wedged_locks_cleared": self.wedged_locks_cleared,
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
                    te.take(await connector.get_ticker(te.symbol))
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
                        entry.symbol,
                        entry.timeframe,
                        limit=rows_requested,
                        since=entry.next_reach_back_ms(rows_requested),
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
