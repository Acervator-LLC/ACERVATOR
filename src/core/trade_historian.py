"""Trade-history scan and Acervator-role classification.

``TradeHistorian.analyze_sync`` fetches one symbol's ccxt trades and
``TradeClassifier.classify`` labels each SCRUM, FOLD, HEDGE, RAPID_FIRE
or UNKNOWN. ``TradeClassifier.pair_cycles`` joins a SCRUM to the next
buy and reports ``CycleSummary.cycle_advantage``. ``scan_on_connect``
runs the scan over a list of symbols and returns one ``HistoryAnalysis``
each. ``_FETCH_GATE`` spaces every fetch at ``HISTORY_FETCH_INTERVAL_S``.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.core.retry import exponential_delay, is_transient, retry_sync

logger = logging.getLogger("acervator.trade_historian")

RAPID_FIRE_WINDOW_S = 60
HEDGE_SIZE_MULTIPLE = 2.0
# Above this and at or below HEDGE_SIZE_MULTIPLE, a buy classifies UNKNOWN.
FOLD_SIZE_TOLERANCE = 1.5
# Below this many buys, median_buy falls back to the first buy size, or 1.0.
MIN_TRADES_FOR_STATS = 3
# ccxt caps one fetch_my_trades page here on most venues.
MAX_HISTORY_FETCH = 500
# Coinbase publishes 10 requests per second per profile on the private
# /fills endpoint: docs.cdp.coinbase.com/exchange/introduction/rate-limits-overview
PUBLISHED_FILLS_RPS = 10.0
HISTORY_FETCH_INTERVAL_S = 1.0 / PUBLISHED_FILLS_RPS
HISTORY_FETCH_ATTEMPTS = 3
HISTORY_RETRY_BASE_DELAY_S = 1.0
MISSING_HISTORY_FORMAT = (
    "Trade history missing for {refused} of {scanned} markets — "
    "the venue refused the fetch."
)


def missing_history_line(refused: int, scanned: int) -> str:
    """The line a surface shows once a history fetch has come back refused.

    ``refused`` and ``scanned`` are symbol counts the caller has recorded.
    """
    return MISSING_HISTORY_FORMAT.format(refused=int(refused), scanned=int(scanned))


class _HistoryFetchGate:
    """Holds each history fetch back until ``interval_s`` since the last one.

    ``_FETCH_GATE`` is the one instance every ``TradeHistorian`` shares.
    """

    def __init__(self, interval_s: float) -> None:
        self._interval_s = float(interval_s)
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> float:
        """Sleep until this caller's turn and return the seconds slept."""
        with self._lock:
            now = time.monotonic()
            turn_at = max(now, self._next_at)
            self._next_at = turn_at + self._interval_s
        delay = turn_at - now
        if delay > 0:
            time.sleep(delay)
        return delay


_FETCH_GATE = _HistoryFetchGate(HISTORY_FETCH_INTERVAL_S)


@dataclass
class MappedTrade:
    """One ccxt trade record with an Acervator role attached.

    ``order_id``, ``timestamp_ms``, ``side``, ``quantity``, ``price``,
    ``cost_usd`` and ``fee_usd`` come from the exchange record;
    ``acervator_role``, ``cycle_id``, ``confidence`` and ``note`` are
    derived by ``TradeClassifier``.
    """

    order_id: str
    timestamp_ms: int
    symbol: str
    side: str  # 'buy' | 'sell'
    quantity: float  # asset units
    price: float
    cost_usd: float  # quantity * price, before fee
    fee_usd: float
    acervator_role: str  # SCRUM | FOLD | HEDGE | RAPID_FIRE | UNKNOWN
    cycle_id: Optional[str]  # set on both legs by pair_cycles
    confidence: float  # 0.0 to 1.0
    note: str = ""

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=timezone.utc)

    def __repr__(self):
        return (
            f"MappedTrade({self.side.upper()} {self.quantity:.6f} "
            f"{self.symbol} @ {self.price:.4f} "
            f"[{self.acervator_role}] {self.dt.strftime('%Y-%m-%d %H:%M')})"
        )


@dataclass
class CycleSummary:
    """A SCRUM joined to the buy that followed it.

    ``pair_cycles`` sets ``scrum_proceeds`` net of fee, ``fold_cost``
    gross of fee, and ``cycle_advantage`` as their difference.
    """

    cycle_id: str
    scrum: MappedTrade
    fold: MappedTrade
    duration_hours: float
    scrum_proceeds: float
    fold_cost: float
    cycle_advantage: float

    @property
    def profitable(self) -> bool:
        return self.cycle_advantage > 0


@dataclass
class HistoryAnalysis:
    """One symbol's scan result on one exchange.

    ``_build_analysis`` fills every field; the counts, the cycles and the
    three estimates are derived from ``trades``, never read from the venue.
    """

    symbol: str
    exchange_id: str
    trade_count: int
    analysis_ts: float = field(default_factory=time.time)

    scrum_count: int = 0
    fold_count: int = 0
    hedge_count: int = 0
    rapid_fire_count: int = 0
    unknown_count: int = 0

    complete_cycles: int = 0
    profitable_cycles: int = 0
    avg_cycle_duration_h: float = 0.0
    total_advantage_usd: float = 0.0

    est_holdings: float = 0.0  # buy quantity less sell quantity, floored at 0
    est_cost_basis: float = 0.0  # buy cost plus fee, over buy quantity
    net_pnl_usd: float = 0.0  # sell cost less fee, minus buy cost plus fee

    history_truncated: bool = False  # the fetch returned at least `limit` rows
    has_unrecognized_trades: bool = False
    analysis_error: Optional[str] = None

    trades: list = field(default_factory=list)  # list[MappedTrade]
    cycles: list = field(default_factory=list)  # list[CycleSummary]

    def summary(self) -> str:
        """Render the counts, cycles and estimates as text lines."""
        lines = [
            f"Trade History Analysis — {self.symbol} on {self.exchange_id}",
            f"  {self.trade_count} trades fetched"
            + (
                " (TRUNCATED — exchange history limit reached)"
                if self.history_truncated
                else ""
            ),
            f"  Classification: {self.scrum_count} scrums  "
            f"{self.fold_count} folds  {self.hedge_count} hedges  "
            f"{self.rapid_fire_count} rapid-fire  "
            f"{self.unknown_count} unknown",
        ]
        if self.complete_cycles:
            lines.append(
                f"  Cycles: {self.complete_cycles} complete  "
                f"({self.profitable_cycles} profitable)  "
                f"avg duration {self.avg_cycle_duration_h:.1f}h  "
                f"total advantage ${self.total_advantage_usd:+,.2f}"
            )
        lines += [
            f"  Est. holdings: {self.est_holdings:.6f} {self.symbol.split('/')[0]}  "
            f"@ avg cost ${self.est_cost_basis:.4f}",
            f"  Net P&L from history: ${self.net_pnl_usd:+,.2f}",
        ]
        if self.has_unrecognized_trades:
            lines.append(
                "  ⚠  UNKNOWN trades detected — manual activity or "
                "pre-Acervator trades present"
            )
        if self.history_truncated:
            lines.append(
                "  ⚠  History truncated — earlier trades not included "
                "in state reconstruction"
            )
        if self.analysis_error:
            lines.append(f"  ✗  Error during analysis: {self.analysis_error}")
        return "\n".join(lines)


class TradeClassifier:
    """Stateless classification of ccxt trade dicts for one symbol.

    ``classify`` returns ``MappedTrade`` records and ``pair_cycles``
    joins them into ``CycleSummary`` pairs.
    """

    @staticmethod
    def classify(raw_trades: list[dict], symbol: str) -> list[MappedTrade]:
        """Label every ccxt trade dict in ``raw_trades`` under ``symbol``.

        Reads ``id``, ``timestamp``, ``side``, ``amount``, ``price``,
        ``cost`` and ``fee.cost`` from each record.
        """
        if not raw_trades:
            return []

        trades = sorted(raw_trades, key=lambda t: t.get("timestamp", 0))

        buy_sizes = [t["amount"] for t in trades if t.get("side") == "buy"]
        if len(buy_sizes) >= MIN_TRADES_FOR_STATS:
            median_buy = statistics.median(buy_sizes)
        else:
            median_buy = buy_sizes[0] if buy_sizes else 1.0

        mapped: list[MappedTrade] = []
        prev_buy_ts: Optional[int] = None

        for t in trades:
            try:
                side = t.get("side", "").lower()
                amount = float(t.get("amount", 0) or 0)
                price = float(t.get("price", 0) or 0)
                cost = float(t.get("cost", 0) or amount * price)
                fee_info = t.get("fee") or {}
                fee_cost = float(fee_info.get("cost", 0) or 0)
                ts_ms = int(t.get("timestamp", 0) or 0)
                order_id = str(t.get("id", t.get("order", "?")))

                if side == "sell":
                    role = "SCRUM"
                    confidence = 0.90
                    note = "Sell — consistent with scrum harvest"
                    prev_buy_ts = None  # a sell breaks the rapid-fire chain

                elif side == "buy":
                    # Tested before size, so a fast large buy reads RAPID_FIRE.
                    if (
                        prev_buy_ts is not None
                        and (ts_ms - prev_buy_ts) <= RAPID_FIRE_WINDOW_S * 1000
                    ):
                        role = "RAPID_FIRE"
                        confidence = 0.80
                        note = (
                            f"Buy within {RAPID_FIRE_WINDOW_S}s of prior buy "
                            "— consistent with BB Bullseye rapid-fire"
                        )

                    elif amount > median_buy * HEDGE_SIZE_MULTIPLE:
                        role = "HEDGE"
                        confidence = 0.70
                        note = (
                            f"Buy size {amount:.4f} > "
                            f"{HEDGE_SIZE_MULTIPLE}× median "
                            f"({median_buy:.4f}) — consistent with "
                            "hedge rebalance"
                        )

                    elif amount <= median_buy * FOLD_SIZE_TOLERANCE:
                        role = "FOLD"
                        confidence = 0.85
                        note = "Buy within normal fold size range"

                    else:
                        role = "UNKNOWN"
                        confidence = 0.40
                        note = (
                            f"Buy size {amount:.4f} — "
                            "ambiguous, could be fold or hedge"
                        )

                    prev_buy_ts = ts_ms

                else:
                    role = "UNKNOWN"
                    confidence = 0.20
                    note = f"Unrecognized side: {side!r}"

                mapped.append(
                    MappedTrade(
                        order_id=order_id,
                        timestamp_ms=ts_ms,
                        symbol=symbol,
                        side=side,
                        quantity=amount,
                        price=price,
                        cost_usd=cost,
                        fee_usd=fee_cost,
                        acervator_role=role,
                        cycle_id=None,
                        confidence=confidence,
                        note=note,
                    )
                )

            except Exception as e:
                logger.debug("Skipping malformed trade record: %s", e)
                continue

        return mapped

    @staticmethod
    def pair_cycles(trades: list[MappedTrade]) -> list[CycleSummary]:
        """Pair each SCRUM with the next trade whose ``side`` is buy.

        The pairing reads ``side``, not ``acervator_role``, so an UNKNOWN
        buy closes a cycle; both legs get the same ``cycle_id``.
        """
        cycles: list[CycleSummary] = []
        pending_scrum: Optional[MappedTrade] = None
        cycle_seq = 0

        for trade in trades:
            if trade.acervator_role == "SCRUM":
                pending_scrum = trade

            elif trade.side == "buy" and pending_scrum is not None:
                cycle_seq += 1
                cid = f"CYC-{cycle_seq:04d}"
                dur_h = (trade.timestamp_ms - pending_scrum.timestamp_ms) / 3_600_000
                proceeds = pending_scrum.cost_usd - pending_scrum.fee_usd
                cost = trade.cost_usd + trade.fee_usd
                advantage = proceeds - cost

                pending_scrum.cycle_id = cid
                trade.cycle_id = cid

                cycles.append(
                    CycleSummary(
                        cycle_id=cid,
                        scrum=pending_scrum,
                        fold=trade,
                        duration_hours=max(dur_h, 0.0),
                        scrum_proceeds=proceeds,
                        fold_cost=cost,
                        cycle_advantage=advantage,
                    )
                )
                pending_scrum = None

        return cycles


class TradeHistorian:
    """Fetches and analyses trade history for one symbol at a time.

    Every ``analyze_sync`` call re-fetches; a fetch failure comes back in
    ``HistoryAnalysis.analysis_error``.
    """

    def __init__(self, exchange, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Hold a ccxt ``exchange`` instance, sync or async.

        ``loop`` is stored on ``_loop`` and no method reads it.
        """
        self._exchange = exchange
        self._loop = loop
        self._cache: dict[str, HistoryAnalysis] = {}

    def analyze_sync(
        self, symbol: str, limit: int = MAX_HISTORY_FETCH
    ) -> HistoryAnalysis:
        """Fetch and classify one symbol through the sync ccxt API.

        Returns a ``HistoryAnalysis`` whatever the fetch does.
        """
        try:
            raw = self._fetch_sync(symbol, limit)
            return self._build_analysis(raw, symbol, limit)
        except Exception as e:
            logger.error("TradeHistorian.analyze_sync(%s): %s", symbol, e)
            return HistoryAnalysis(
                symbol=symbol,
                exchange_id=getattr(self._exchange, "id", "unknown"),
                trade_count=0,
                analysis_error=str(e),
            )

    async def analyze_async(
        self, symbol: str, limit: int = MAX_HISTORY_FETCH
    ) -> HistoryAnalysis:
        """Fetch and classify one symbol through the async ccxt API.

        Returns a ``HistoryAnalysis`` whatever the fetch does.
        """
        try:
            raw = await self._fetch_async(symbol, limit)
            return self._build_analysis(raw, symbol, limit)
        except Exception as e:
            logger.error("TradeHistorian.analyze_async(%s): %s", symbol, e)
            return HistoryAnalysis(
                symbol=symbol,
                exchange_id=getattr(self._exchange, "id", "unknown"),
                trade_count=0,
                analysis_error=str(e),
            )

    def analyze_all_sync(
        self, symbols: list[str], limit: int = MAX_HISTORY_FETCH
    ) -> dict[str, HistoryAnalysis]:
        """Run ``analyze_sync`` for every entry in ``symbols``.

        Each result is also written to ``_cache`` for ``get_cached``.
        """
        results = {}
        for sym in symbols:
            logger.info("TradeHistorian: scanning %s...", sym)
            results[sym] = self.analyze_sync(sym, limit)
            self._cache[sym] = results[sym]
        return results

    def get_cached(self, symbol: str) -> Optional[HistoryAnalysis]:
        """Return what ``analyze_all_sync`` last stored in ``_cache``."""
        return self._cache.get(symbol)

    def clear_cache(self):
        self._cache.clear()

    def _fetch_sync(self, symbol: str, limit: int) -> list[dict]:
        """Call ``fetch_my_trades`` on the sync ccxt exchange, paced and retried.

        ``_FETCH_GATE`` spaces the call at ``HISTORY_FETCH_INTERVAL_S`` and
        ``retry_sync`` repeats a transient refusal up to
        ``HISTORY_FETCH_ATTEMPTS`` times before the ``RuntimeError``.
        """

        def one_fetch() -> list[dict]:
            _FETCH_GATE.wait()
            trades = self._exchange.fetch_my_trades(symbol, limit=limit) or []
            logger.info("TradeHistorian: fetched %d trades for %s", len(trades), symbol)
            return trades

        def note(
            exc: BaseException, attempt: int, will_retry: bool, delay: float
        ) -> None:
            if not will_retry:
                return
            logger.warning(
                "TradeHistorian: %s on %s (attempt %d/%d), retrying in %.1fs",
                type(exc).__name__,
                symbol,
                attempt + 1,
                HISTORY_FETCH_ATTEMPTS,
                delay,
            )

        try:
            return retry_sync(
                one_fetch,
                attempts=HISTORY_FETCH_ATTEMPTS,
                delay_for=exponential_delay(HISTORY_RETRY_BASE_DELAY_S),
                is_retryable=is_transient,
                on_failure=note,
            )
        except Exception as e:
            raise RuntimeError(
                f"Exchange trade history fetch failed for {symbol}: {e}"
            ) from e

    async def _fetch_async(self, symbol: str, limit: int) -> list[dict]:
        """Await ``fetch_my_trades`` on the async ccxt exchange.

        A ccxt failure is re-raised as ``RuntimeError`` naming ``symbol``.
        """
        try:
            trades = await self._exchange.fetch_my_trades(symbol, limit=limit)
            return trades or []
        except Exception as e:
            raise RuntimeError(
                f"Exchange trade history fetch failed for {symbol}: {e}"
            ) from e

    def _build_analysis(
        self, raw: list[dict], symbol: str, limit: int
    ) -> HistoryAnalysis:
        """Build a ``HistoryAnalysis`` from ``raw`` ccxt trade records.

        ``exchange_id`` is read off the ccxt object; every count, cycle and
        estimate is derived from the ``MappedTrade`` list.
        """
        exc_id = getattr(self._exchange, "id", "unknown")

        analysis = HistoryAnalysis(
            symbol=symbol,
            exchange_id=exc_id,
            trade_count=len(raw),
            history_truncated=(len(raw) >= limit),
        )

        if not raw:
            return analysis

        trades = TradeClassifier.classify(raw, symbol)
        analysis.trades = trades

        analysis.scrum_count = sum(1 for t in trades if t.acervator_role == "SCRUM")
        analysis.fold_count = sum(1 for t in trades if t.acervator_role == "FOLD")
        analysis.hedge_count = sum(1 for t in trades if t.acervator_role == "HEDGE")
        analysis.rapid_fire_count = sum(
            1 for t in trades if t.acervator_role == "RAPID_FIRE"
        )
        analysis.unknown_count = sum(1 for t in trades if t.acervator_role == "UNKNOWN")
        analysis.has_unrecognized_trades = analysis.unknown_count > 0

        cycles = TradeClassifier.pair_cycles(trades)
        analysis.cycles = cycles
        analysis.complete_cycles = len(cycles)
        analysis.profitable_cycles = sum(1 for c in cycles if c.profitable)
        analysis.total_advantage_usd = sum(c.cycle_advantage for c in cycles)
        if cycles:
            analysis.avg_cycle_duration_h = statistics.mean(
                c.duration_hours for c in cycles
            )

        net_qty = 0.0
        total_buy_cost = 0.0
        total_buy_qty = 0.0
        net_pnl = 0.0

        for t in trades:
            if t.side == "buy":
                net_qty += t.quantity
                total_buy_cost += t.cost_usd + t.fee_usd
                total_buy_qty += t.quantity
                net_pnl -= t.cost_usd + t.fee_usd
            elif t.side == "sell":
                net_qty -= t.quantity
                net_pnl += t.cost_usd - t.fee_usd

        analysis.est_holdings = max(net_qty, 0.0)
        analysis.est_cost_basis = (
            total_buy_cost / total_buy_qty if total_buy_qty > 0 else 0.0
        )
        analysis.net_pnl_usd = net_pnl

        logger.info(
            "TradeHistorian: %s — %d scrums, %d folds, "
            "%d hedges, %d RF, %d unknown | "
            "%d cycles | est holdings %.6f",
            symbol,
            analysis.scrum_count,
            analysis.fold_count,
            analysis.hedge_count,
            analysis.rapid_fire_count,
            analysis.unknown_count,
            analysis.complete_cycles,
            analysis.est_holdings,
        )

        return analysis


def scan_on_connect(
    exchange,
    symbols: list[str],
    limit: int = MAX_HISTORY_FETCH,
    on_result: Optional[Callable[[str, HistoryAnalysis], None]] = None,
    pace_s: float = 0.0,
) -> dict[str, HistoryAnalysis]:
    """Run ``TradeHistorian.analyze_sync`` over ``symbols`` in order.

    ``on_result`` is called with each symbol and its ``HistoryAnalysis``
    as that symbol finishes.
    """
    if not symbols:
        logger.info("TradeHistorian: no symbols provided — skipping scan")
        return {}

    historian = TradeHistorian(exchange)
    results = {}

    for _i, sym in enumerate(symbols):
        # `_fetch_sync` calls the raw ccxt object, past the connector's
        # own rate limiting; `pace_s` spaces the symbols after the first.
        if _i and pace_s > 0:
            time.sleep(pace_s)
        logger.info("TradeHistorian: scanning history for %s...", sym)
        analysis = historian.analyze_sync(sym, limit)
        results[sym] = analysis

        if on_result:
            try:
                on_result(sym, analysis)
            except Exception as e:
                logger.warning("on_result callback error for %s: %s", sym, e)

        logger.info(analysis.summary())

    return results
