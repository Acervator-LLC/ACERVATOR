"""``MarketPairsScout`` keeps each exchange's pairs of the bases its readers ask for.

``refresh_from_connectors`` reads them by name through ``get_all_tickers`` where
``NAMED_TICKERS`` holds the exchange, and asks for every market elsewhere.
``every_ticker_answer`` fills the rest of a book, which ``pairs_on`` and
``_build_topology_proposals`` read whole. ``_carry_pairs`` shares the books, the asks
and the readings of a stopped scout with its replacement.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .base import TickerRows
from .lazy_singleton import LazySingleton

if TYPE_CHECKING:
    from .ccxt_connector import CCXTConnector

logger = logging.getLogger("acervator.market_pairs_scout")

DEFAULT_REFRESH_SECONDS = 10.0  # per prior-art research § 6.2

#: The quotes the Target cells and Detail rows read one base in.
READER_QUOTES = ("USD", "USDC", "BTC", "ETH")

#: The quote of an ask for every pair of a base, and the exchange of an ask for any.
EVERY_QUOTE = ""
ANY_EXCHANGE = "*"

#: Pairs one call names: 200 ids of up to 26 characters fit ``REQUEST_URI_OCTETS``.
PAIRS_PER_CALL = 200

#: Seconds of rest per second of answer, which leaves a reading a third of the worker.
REST_PER_ANSWER = 2.0

#: Longest ``refresh_from_connectors`` waits for the readings it started, which run on.
REFRESH_WAIT_S = 2.0


def row_quote_volume_24h(row: object) -> float:
    """Return one raw ticker ``row``'s 24h volume in quote units.

    Reads ``quoteVolume`` where the venue serves it, and otherwise multiplies
    ``baseVolume`` by ``last``, so a ranking across markets never mixes a
    base-unit figure with a quote-unit one. Returns 0.0 for a row carrying
    neither.
    """
    getter = getattr(row, "get", None)
    if not callable(getter):
        return 0.0
    try:
        quote_volume = float(getter("quoteVolume") or 0.0)
    except (TypeError, ValueError):
        quote_volume = 0.0
    if quote_volume > 0:
        return quote_volume
    try:
        base_volume = float(getter("baseVolume") or 0.0)
        last = float(getter("last") or 0.0) or float(getter("close") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    derived = base_volume * last
    if derived > 0:
        logger.debug(
            "row_quote_volume_24h: %s served no quoteVolume; %s x %s used",
            getter("symbol"),
            base_volume,
            last,
        )
    return max(0.0, derived)


def takes_names(exchange_id: str) -> bool:
    """True where ``NAMED_TICKERS`` holds ``exchange_id``."""
    from .ccxt_connector import NAMED_TICKERS, venue_record_key

    return venue_record_key(exchange_id) in NAMED_TICKERS


@dataclass
class PairSnapshot:
    """One trading pair on one exchange at one moment.

    Fields chosen so the same struct powers both the GUI rendering AND
    any future calibration work (spread, volume, drift are all here).
    """

    symbol: str  # e.g. "ETH/BTC"
    base: str  # e.g. "ETH"
    quote: str  # e.g. "BTC"
    last: float = 0.0  # last trade price, in quote units per base
    pct_24h: float = 0.0  # 24h % change, from ccxt ticker.percentage
    bid: float = 0.0  # best-bid price (quote per base)
    ask: float = 0.0  # best-ask price (quote per base)
    volume_24h: float = 0.0  # 24h base-unit volume
    quote_volume_24h: float = 0.0  # 24h volume in quote units; rank on this one
    exchange_id: str = ""
    last_updated: float = 0.0

    @property
    def spread(self) -> float:
        """Absolute quote-price spread (ask - bid); 0 when either is
        missing. Prefer ``spread_pct`` for cross-pair comparisons."""
        if self.ask <= 0 or self.bid <= 0:
            return 0.0
        return max(0.0, self.ask - self.bid)

    @property
    def spread_pct(self) -> float:
        """Spread as a percentage of mid, or 0 when unavailable."""
        if self.ask <= 0 or self.bid <= 0:
            return 0.0
        mid = 0.5 * (self.ask + self.bid)
        if mid <= 0:
            return 0.0
        return 100.0 * (self.ask - self.bid) / mid

    def age_seconds(self, now: Optional[float] = None) -> float:
        _now = time.time() if now is None else now
        if self.last_updated <= 0:
            return float("inf")
        return max(0.0, _now - self.last_updated)

    def usd_per_base(self, btc_usd: float, eth_usd: float) -> float:
        """Convert this pair's ``last`` into USD-per-base-unit.

        Uses the currency-rate-monitor's BTC/USD + ETH/USD as external
        reference for non-USD quote currencies. Returns 0 when the
        conversion cannot be computed (unknown quote + no known rate).
        """
        q = (self.quote or "").upper()
        if q in ("USD", "USDC", "USDT", "DAI"):
            return float(self.last or 0.0)
        if q == "BTC" and btc_usd > 0:
            return float(self.last or 0.0) * btc_usd
        if q == "ETH" and eth_usd > 0:
            return float(self.last or 0.0) * eth_usd
        return 0.0


@dataclass
class VenueBook:
    """One exchange's ``pairs``, and the ``rest_until`` its next reading waits for."""

    pairs: dict[str, PairSnapshot] = field(default_factory=dict)
    read_at: float = 0.0  # time.time() of the last successful reading
    error: Optional[str] = None  # last error message (kept for diagnostic display)
    rest_until: float = 0.0  # time.monotonic() the next reading may start
    reading: Optional[asyncio.Task[None]] = None  # on its way, or the last one


class MarketPairsScout:
    """One ``VenueBook`` per exchange, filled by ``refresh_from_connectors``."""

    def __init__(self, refresh_seconds: float = DEFAULT_REFRESH_SECONDS) -> None:
        self._refresh_s = float(refresh_seconds)
        # exchange_id -> its book; hold_books shares this dict with a replacement
        self.books: dict[str, VenueBook] = {}
        # (exchange_id, base, quote) -> time.monotonic() of the last ask; shared too
        self.asked: dict[tuple[str, str, str], float] = {}

    @property
    def refresh_seconds(self) -> float:
        return self._refresh_s

    @property
    def _allowed_age_s(self) -> float:
        """Age past which ``is_stale`` reports a book."""
        return self._refresh_s * 2

    @property
    def _snapshots(self) -> dict[str, dict[str, PairSnapshot]]:
        """Each exchange's pairs, which ``_build_topology_proposals`` reads."""
        return {eid: book.pairs for eid, book in list(self.books.items())}

    def _note_ask(self, base: str, quote: str, exchange_id: Optional[str]) -> None:
        """Keep one ask for ``base`` in ``quote``, which ``_pairs_asked`` reads."""
        venue = ANY_EXCHANGE if exchange_id is None else exchange_id
        self.asked[(venue, base, quote)] = time.monotonic()

    def _held(self, base: str, exchange_id: Optional[str]) -> list[PairSnapshot]:
        """``base``'s pairs on ``exchange_id``, or on every one, by symbol."""
        out: list[PairSnapshot] = []
        for eid, book in list(self.books.items()):
            if exchange_id is None or eid == exchange_id:
                out.extend(s for s in book.pairs.values() if s.base == base)
        out.sort(key=lambda s: s.symbol)
        return out

    def pairs_for(
        self,
        asset: str,
        exchange_id: Optional[str] = None,
    ) -> list[PairSnapshot]:
        """All pairs whose BASE == asset. If ``exchange_id`` is given,
        restrict to that exchange; otherwise merge across all
        exchanges the scout has polled. Deterministic order: symbol
        ascending.
        """
        _asset = (asset or "").upper()
        if not _asset:
            return []
        self._note_ask(_asset, EVERY_QUOTE, exchange_id)
        return self._held(_asset, exchange_id)

    def pairs_on(self, exchange_id: str) -> list[PairSnapshot]:
        """Every pair the book of ``exchange_id`` holds, symbol ascending."""
        book = self.books.get(exchange_id, VenueBook())
        return sorted(book.pairs.values(), key=lambda s: s.symbol)

    def hold_books(self, other: MarketPairsScout) -> int:
        """Share every book, ask and reading of ``other``, and answer the pair count.

        ``_carry_pairs`` calls it, and a reading ``other`` started lands here too.
        """
        self.books = other.books
        self.asked = other.asked
        return sum(len(book.pairs) for book in self.books.values())

    def quote_currencies_for(
        self,
        asset: str,
        exchange_id: Optional[str] = None,
    ) -> list[str]:
        """Return the unique quote currencies (uppercased) for the
        given base asset across polled exchanges. Order deterministic.
        """
        return sorted({s.quote for s in self.pairs_for(asset, exchange_id)})

    def has_pair(
        self,
        base: str,
        quote: str,
        exchange_id: Optional[str] = None,
    ) -> bool:
        return self.get_pair(base, quote, exchange_id) is not None

    def get_pair(
        self,
        base: str,
        quote: str,
        exchange_id: Optional[str] = None,
    ) -> Optional[PairSnapshot]:
        _b = (base or "").upper()
        _q = (quote or "").upper()
        if not _b or not _q:
            return None
        self._note_ask(_b, _q, exchange_id)
        for s in self._held(_b, exchange_id):
            if s.quote == _q:
                return s
        return None

    def last_refresh(self, exchange_id: str) -> float:
        return float(self.books.get(exchange_id, VenueBook()).read_at)

    def polled_exchanges(self) -> list[str]:
        """Exchange ids whose ``read_at`` a reading has set, ascending."""
        return sorted(eid for eid, book in list(self.books.items()) if book.read_at > 0)

    def last_error(self, exchange_id: str) -> Optional[str]:
        return self.books.get(exchange_id, VenueBook()).error

    def is_stale(
        self,
        exchange_id: str,
        now: Optional[float] = None,
    ) -> bool:
        """True when the exchange's last refresh was longer than
        2 × ``refresh_seconds`` ago (or never)."""
        _now = time.time() if now is None else now
        last = self.last_refresh(exchange_id)
        if last <= 0:
            return True
        return (_now - last) > self._allowed_age_s

    def is_paced(self, exchange_id: str) -> bool:
        """True with no ``error`` and the next reading on its way, at rest or due."""
        book = self.books.get(exchange_id, VenueBook())
        if book.error is not None:
            return False
        if book.reading is not None and not book.reading.done():
            return True
        return time.monotonic() < book.rest_until + self._allowed_age_s

    # Ingest — either directly from a raw tickers dict (tests) or
    # by polling a set of connectors (production).

    def _snapshots_of(
        self, exchange_id: str, tickers: dict, now: float
    ) -> dict[str, PairSnapshot]:
        """One ``PairSnapshot`` per good row of ``tickers``, each stamped ``now``."""
        pairs: dict[str, PairSnapshot] = {}
        for symbol, row in (tickers or {}).items():
            try:
                if not symbol or "/" not in symbol:
                    continue
                base, quote = symbol.split("/", 1)
                base = base.upper()
                quote = quote.upper()
                last = float(row.get("last", 0) or 0)
                if last <= 0:
                    # some Coinbase products list without last trade
                    last = float(row.get("close", 0) or 0)
                bid = float(row.get("bid", 0) or 0)
                ask = float(row.get("ask", 0) or 0)
                pct = float(row.get("percentage", 0) or 0)
                vol = float(row.get("baseVolume", 0) or 0)
                pairs[symbol] = PairSnapshot(
                    symbol=symbol,
                    base=base,
                    quote=quote,
                    last=last,
                    pct_24h=pct,
                    bid=bid,
                    ask=ask,
                    volume_24h=vol,
                    quote_volume_24h=row_quote_volume_24h(row),
                    exchange_id=exchange_id,
                    last_updated=now,
                )
            except Exception as _row_exc:  # noqa: BLE001 - per-row best-effort
                logger.debug(
                    "MarketPairsScout: skip row %s on %s (%s)",
                    symbol,
                    exchange_id,
                    _row_exc,
                )
        return pairs

    def _put_book(
        self, exchange_id: str, pairs: dict[str, PairSnapshot], now: float
    ) -> int:
        """Make ``pairs`` the book of ``exchange_id``, read at ``now``."""
        book = self.books.setdefault(exchange_id, VenueBook())
        book.pairs = pairs
        book.read_at = now
        book.error = None
        return len(pairs)

    def ingest_tickers(
        self,
        exchange_id: str,
        tickers: dict,
        now: Optional[float] = None,
    ) -> int:
        """Make a raw CCXT ``fetch_tickers`` dict of every market the book.

        A row ``_snapshots_of`` cannot read is left out of the count returned.
        """
        _now = time.time() if now is None else now
        pairs = self._snapshots_of(exchange_id, tickers, _now)
        return self._put_book(exchange_id, pairs, _now)

    def _take_every_ticker(self, exchange_id: str, connector: CCXTConnector) -> bool:
        """Make ``connector``'s ``every_ticker_answer`` the book, where it is newer."""
        answer = getattr(connector, "every_ticker_answer", None)
        if answer is None:
            return False
        read_at, rows = answer()
        if read_at <= self.last_refresh(exchange_id):
            return False
        self.ingest_tickers(exchange_id, rows, now=read_at)
        return True

    def _land(
        self,
        exchange_id: str,
        connector: CCXTConnector,
        names: list[str],
        rows: object,
    ) -> bool:
        """Put the answer to ``names`` in the book, and say if it held every market."""
        if not rows or not isinstance(rows, dict):
            raise LookupError(f"{exchange_id} answered no market")
        self._take_every_ticker(exchange_id, connector)
        if rows is connector.every_ticker_answer()[1]:
            return True
        read_s = rows.read_at.wall_s if isinstance(rows, TickerRows) else time.time()
        landed = self._snapshots_of(exchange_id, rows, read_s)
        left_out = set(names) - landed.keys()
        held = self.books[exchange_id].pairs
        kept = {name: pair for name, pair in held.items() if name not in left_out}
        self._put_book(exchange_id, {**kept, **landed}, read_s)
        return False

    def _pairs_asked(self, exchange_id: str, listed: set[str]) -> list[str]:
        """Each pair asked of ``exchange_id`` in ``DEFAULT_MIN_REFRESH_S``, by base."""
        from .market_inspector_fetcher import DEFAULT_MIN_REFRESH_S

        oldest = time.monotonic() - DEFAULT_MIN_REFRESH_S
        names: set[str] = set()
        for ask, asked_at in list(self.asked.items()):
            venue, base, quote = ask
            if asked_at < oldest:
                self.asked.pop(ask, None)
            elif venue not in (exchange_id, ANY_EXCHANGE):
                continue
            elif quote == EVERY_QUOTE:
                names.update(one for one in listed if one.split("/")[0] == base)
            else:
                quotes = {*READER_QUOTES, quote} - {base}
                names.update(f"{base}/{one}" for one in quotes)
        return sorted(one for one in names if ":" not in one)

    def _calls(
        self, exchange_id: str, connector: CCXTConnector
    ) -> list[Optional[list[str]]]:
        """The pairs each call of a ``_read`` names; None names every market."""
        if not takes_names(exchange_id):
            return [None]
        markets = getattr(getattr(connector, "_ex", None), "markets", None) or {}
        listed = {*markets, *self.books[exchange_id].pairs}
        names = self._pairs_asked(exchange_id, listed)
        calls = [
            names[at : at + PAIRS_PER_CALL]
            for at in range(0, len(names), PAIRS_PER_CALL)
        ]
        return [one for one in calls if not listed or not listed.isdisjoint(one)]

    async def _free_place(self, connector: CCXTConnector) -> bool:
        """True once ``connector`` admits a bulk read, False past ``_allowed_age_s``."""
        try:
            async with asyncio.timeout(self._allowed_age_s):
                await connector.await_bulk_read_slot()
        except TimeoutError:
            return False
        return True

    async def _read(self, exchange_id: str, connector: CCXTConnector) -> None:
        """Make each of ``_calls`` in a free place, then set ``rest_until``."""
        from .ccxt_connector import SYNC_CALL_TIMEOUT_SEC

        book = self.books[exchange_id]
        took = 0.0
        shortest_rest = 0.0
        try:
            for names in self._calls(exchange_id, connector):
                if not await self._free_place(connector):
                    book.error = "no free place in the call queue"
                    break
                shortest_rest = self._refresh_s
                asked_at = time.monotonic()
                try:
                    rows = await connector.get_all_tickers(names)
                finally:
                    took += min(time.monotonic() - asked_at, SYNC_CALL_TIMEOUT_SEC)
                if self._land(exchange_id, connector, names or [], rows):
                    break
        except Exception as _conn_exc:  # noqa: BLE001 - per-connector probe
            shortest_rest = self._allowed_age_s
            # The text of a failed request holds its URL, whose query lists pairs.
            said = str(_conn_exc).partition("?")[0]
            book.error = f"{type(_conn_exc).__name__}: {said}"
            logger.debug(
                "MarketPairsScout: connector %s refresh failed: %s",
                exchange_id,
                book.error,
            )
        rest = max(shortest_rest, REST_PER_ANSWER * took)
        book.rest_until = time.monotonic() + rest

    def _at_rest(self, exchange_id: str, connector: CCXTConnector) -> bool:
        """True before ``rest_until``, or where another read of every market serves."""
        book = self.books[exchange_id]
        if time.monotonic() < book.rest_until:
            return True
        if self._take_every_ticker(exchange_id, connector):
            rest = self._refresh_s - max(0.0, time.time() - book.read_at)
            book.rest_until = time.monotonic() + rest
            if rest > 0:
                return True
        on_way = getattr(connector, "every_ticker_on_way", False)
        return on_way and not takes_names(exchange_id)

    async def refresh_from_connectors(
        self,
        connectors: dict,
        force: bool = False,
    ) -> dict[str, int]:
        """Start a ``_read`` task per exchange past ``rest_until``; answer pair counts.

        A caller that gives up ends no ``reading``, and ``force`` reads one at rest.
        """
        started: list[asyncio.Task[None]] = []
        for eid, connector in (connectors or {}).items():
            book = self.books.setdefault(eid, VenueBook())
            if book.reading is not None and not book.reading.done():
                continue
            if not force and self._at_rest(eid, connector):
                continue
            book.reading = asyncio.create_task(self._read(eid, connector))
            started.append(book.reading)
        if started:
            await asyncio.wait(started, timeout=REFRESH_WAIT_S)
        return {eid: len(self.books[eid].pairs) for eid in connectors or {}}


# Process-wide shared scout


def _scout_has_stopped(scout: MarketPairsScout) -> bool:
    """True when each of ``polled_exchanges`` ``is_stale`` and not ``is_paced``.

    ``_SCOUT`` passes this as ``has_stopped``, and an empty ``polled_exchanges``
    keeps the scout.
    """
    polled = scout.polled_exchanges()
    return bool(polled) and all(
        scout.is_stale(eid) and not scout.is_paced(eid) for eid in polled
    )


def _carry_pairs(previous: MarketPairsScout, replacement: MarketPairsScout) -> None:
    """Share ``previous``'s books, asks and readings with ``replacement``.

    ``_SCOUT`` passes this as ``carry_reading``.
    """
    replacement.hold_books(previous)


_SCOUT: LazySingleton[MarketPairsScout] = LazySingleton(
    MarketPairsScout,
    "the market pairs scout",
    "The Target BTC and Target ETH rows, and every other cross-pair "
    "reading, will hold their last value and stop updating.",
    has_stopped=_scout_has_stopped,
    carry_reading=_carry_pairs,
)


def get_scout() -> Optional[MarketPairsScout]:
    """Return the shared scout, or None while it is down.

    Never raises. None means skip cross-pair readings this tick.
    """
    return _SCOUT.get()


def reset_scout_for_tests() -> None:
    """Clear the singleton and its cooling-off — test-only helper."""
    _SCOUT.reset()
