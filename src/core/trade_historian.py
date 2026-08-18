"""
trade_historian.py — Trade History Scanner and Acervator Logic Mapper
======================================================================
Triggered on every API connect, reconnect, or manual refresh.
Fetches the user's trade history from the exchange and classifies
each trade in the context of Acervator's accumulation logic.

CLASSIFICATION RULES
--------------------
  SCRUM       SELL order.  Acervator only sells in scrums (selling excess
              holdings above target after band travel / bullseye trigger).

  FOLD        BUY order, size within 1.5× the median buy size for this
              symbol.  Regular accumulation buy — price dipped below the
              detect threshold and the bot bought back.

  HEDGE       BUY order, size > 2× median buy size.  Consistent with a
              hedge rebalance — buying during a drawdown from the separate
              hedge reserve rather than the normal fold mechanism.

  RAPID_FIRE  BUY order arriving within 60 seconds of a prior BUY on the
              same symbol.  Consistent with BB Bullseye rapid-fire mode.

  UNKNOWN     Trade that does not fit any of the above patterns.  Could
              be a manual trade, a partial fill, or a trade from before
              the user started using Acervator.

CYCLE PAIRING
-------------
  A scrum at time T is paired with the next BUY of any kind (FOLD, HEDGE,
  or RAPID_FIRE) to form a complete scrum-fold cycle.  The cycle advantage
  is: sell_proceeds - buy_cost.  Positive advantage = the scrum captured
  more than the subsequent fold cost.

USAGE
-----
  historian = TradeHistorian(ccxt_exchange)
  analysis  = await historian.analyze("BTC/USDT", limit=500)
  print(analysis.summary())

  # Or call from connector on every connect event:
  results = await historian.analyze_all(["BTC/USDT", "ETH/USDT"])
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("acervator.trade_historian")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RAPID_FIRE_WINDOW_S  = 60      # seconds — two buys within this = RAPID_FIRE
HEDGE_SIZE_MULTIPLE  = 2.0     # × median buy → HEDGE classification
FOLD_SIZE_TOLERANCE  = 1.5     # × median buy — above this is HEDGE territory
MIN_TRADES_FOR_STATS = 3       # need at least this many buys for median calc
MAX_HISTORY_FETCH    = 500     # ccxt limit per call (most exchanges cap here)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MappedTrade:
    """A single exchange trade classified against Acervator logic."""
    order_id:        str
    timestamp_ms:    int            # millisecond UTC timestamp from exchange
    symbol:          str
    side:            str            # 'buy' | 'sell'
    quantity:        float          # asset units traded
    price:           float          # execution price
    cost_usd:        float          # quantity × price (before fee)
    fee_usd:         float          # fee paid
    acervator_role:  str            # SCRUM | FOLD | HEDGE | RAPID_FIRE | UNKNOWN
    cycle_id:        Optional[str]  # pairs scrum with following fold
    confidence:      float          # 0.0–1.0 classification confidence
    note:            str = ""       # human-readable classification note

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(
            self.timestamp_ms / 1000, tz=timezone.utc)

    def __repr__(self):
        return (f"MappedTrade({self.side.upper()} {self.quantity:.6f} "
                f"{self.symbol} @ {self.price:.4f} "
                f"[{self.acervator_role}] {self.dt.strftime('%Y-%m-%d %H:%M')})")


@dataclass
class CycleSummary:
    """A matched scrum–fold pair."""
    cycle_id:         str
    scrum:            MappedTrade
    fold:             MappedTrade
    duration_hours:   float    # time from scrum to fold
    scrum_proceeds:   float    # sell proceeds after fee
    fold_cost:        float    # buy cost after fee
    cycle_advantage:  float    # scrum_proceeds - fold_cost

    @property
    def profitable(self) -> bool:
        return self.cycle_advantage > 0


@dataclass
class HistoryAnalysis:
    """Complete analysis result for one symbol on one exchange."""
    symbol:           str
    exchange_id:      str
    trade_count:      int
    analysis_ts:      float = field(default_factory=time.time)

    # Classification counts
    scrum_count:      int = 0
    fold_count:       int = 0
    hedge_count:      int = 0
    rapid_fire_count: int = 0
    unknown_count:    int = 0

    # Cycle analysis
    complete_cycles:       int   = 0
    profitable_cycles:     int   = 0
    avg_cycle_duration_h:  float = 0.0
    total_advantage_usd:   float = 0.0

    # Reconstructed state (approximate)
    est_holdings:     float = 0.0   # net asset balance from history
    est_cost_basis:   float = 0.0   # avg cost of current holdings
    net_pnl_usd:      float = 0.0   # all sell proceeds - all buy costs

    # Quality flags
    history_truncated:         bool = False  # exchange returned max limit
    has_unrecognized_trades:   bool = False
    analysis_error:            Optional[str] = None

    # Detailed records
    trades:  list = field(default_factory=list)   # list[MappedTrade]
    cycles:  list = field(default_factory=list)   # list[CycleSummary]

    def summary(self) -> str:
        """One-paragraph human-readable summary."""
        lines = [
            f"Trade History Analysis — {self.symbol} on {self.exchange_id}",
            f"  {self.trade_count} trades fetched"
            + (" (TRUNCATED — exchange history limit reached)"
               if self.history_truncated else ""),
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


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class TradeClassifier:
    """
    Stateless classifier — given a list of raw ccxt trade dicts for one
    symbol, classifies each trade and pairs scrums with folds.
    """

    @staticmethod
    def classify(raw_trades: list[dict], symbol: str) -> list[MappedTrade]:
        """
        Classify a list of ccxt trade dicts.

        Expected ccxt trade format:
          {
            'id': str, 'timestamp': int (ms), 'symbol': str,
            'side': 'buy'|'sell', 'amount': float, 'price': float,
            'cost': float, 'fee': {'cost': float, 'currency': str}
          }
        """
        if not raw_trades:
            return []

        # Sort ascending by timestamp
        trades = sorted(raw_trades, key=lambda t: t.get("timestamp", 0))

        # Compute median buy size for FOLD vs HEDGE discrimination
        buy_sizes = [t["amount"] for t in trades if t.get("side") == "buy"]
        if len(buy_sizes) >= MIN_TRADES_FOR_STATS:
            median_buy = statistics.median(buy_sizes)
        else:
            median_buy = buy_sizes[0] if buy_sizes else 1.0

        mapped: list[MappedTrade] = []
        prev_buy_ts: Optional[int] = None

        for t in trades:
            try:
                side      = t.get("side", "").lower()
                amount    = float(t.get("amount", 0) or 0)
                price     = float(t.get("price", 0) or 0)
                cost      = float(t.get("cost", 0) or amount * price)
                fee_info  = t.get("fee") or {}
                fee_cost  = float(fee_info.get("cost", 0) or 0)
                ts_ms     = int(t.get("timestamp", 0) or 0)
                order_id  = str(t.get("id", t.get("order", "?")))

                # Classify
                if side == "sell":
                    role        = "SCRUM"
                    confidence  = 0.90
                    note        = "Sell — consistent with scrum harvest"
                    prev_buy_ts = None  # reset rapid-fire window after sell

                elif side == "buy":
                    # Check rapid-fire window first
                    if (prev_buy_ts is not None
                            and (ts_ms - prev_buy_ts) <= RAPID_FIRE_WINDOW_S * 1000):
                        role       = "RAPID_FIRE"
                        confidence = 0.80
                        note       = (f"Buy within {RAPID_FIRE_WINDOW_S}s of prior buy "
                                      "— consistent with BB Bullseye rapid-fire")

                    elif amount > median_buy * HEDGE_SIZE_MULTIPLE:
                        role       = "HEDGE"
                        confidence = 0.70
                        note       = (f"Buy size {amount:.4f} > "
                                      f"{HEDGE_SIZE_MULTIPLE}× median "
                                      f"({median_buy:.4f}) — consistent with "
                                      "hedge rebalance")

                    elif amount <= median_buy * FOLD_SIZE_TOLERANCE:
                        role       = "FOLD"
                        confidence = 0.85
                        note       = "Buy within normal fold size range"

                    else:
                        role       = "UNKNOWN"
                        confidence = 0.40
                        note       = (f"Buy size {amount:.4f} — "
                                      "ambiguous, could be fold or hedge")

                    prev_buy_ts = ts_ms

                else:
                    role       = "UNKNOWN"
                    confidence = 0.20
                    note       = f"Unrecognized side: {side!r}"

                mapped.append(MappedTrade(
                    order_id       = order_id,
                    timestamp_ms   = ts_ms,
                    symbol         = symbol,
                    side           = side,
                    quantity       = amount,
                    price          = price,
                    cost_usd       = cost,
                    fee_usd        = fee_cost,
                    acervator_role = role,
                    cycle_id       = None,
                    confidence     = confidence,
                    note           = note,
                ))

            except Exception as e:
                logger.debug("Skipping malformed trade record: %s", e)
                continue

        return mapped

    @staticmethod
    def pair_cycles(trades: list[MappedTrade]) -> list[CycleSummary]:
        """
        Pair each SCRUM with the next BUY (FOLD / HEDGE / RAPID_FIRE) to
        form complete scrum-fold cycles.  Assigns cycle_id to both legs.
        """
        cycles: list[CycleSummary] = []
        pending_scrum: Optional[MappedTrade] = None
        cycle_seq = 0

        for trade in trades:
            if trade.acervator_role == "SCRUM":
                pending_scrum = trade

            elif (trade.side == "buy"
                  and pending_scrum is not None):
                cycle_seq += 1
                cid       = f"CYC-{cycle_seq:04d}"
                dur_h     = ((trade.timestamp_ms - pending_scrum.timestamp_ms)
                             / 3_600_000)
                proceeds  = (pending_scrum.cost_usd - pending_scrum.fee_usd)
                cost      = (trade.cost_usd + trade.fee_usd)
                advantage = proceeds - cost

                pending_scrum.cycle_id = cid
                trade.cycle_id         = cid

                cycles.append(CycleSummary(
                    cycle_id        = cid,
                    scrum           = pending_scrum,
                    fold            = trade,
                    duration_hours  = max(dur_h, 0.0),
                    scrum_proceeds  = proceeds,
                    fold_cost       = cost,
                    cycle_advantage = advantage,
                ))
                pending_scrum = None

        return cycles


# ---------------------------------------------------------------------------
# Main historian class
# ---------------------------------------------------------------------------

class TradeHistorian:
    """
    Fetches and analyses trade history for one or more symbols.
    Designed to be called on every API connect / reconnect / refresh.

    R29 (Idempotency): safe to call multiple times — each call fetches
    fresh data and produces a fresh HistoryAnalysis; no side effects.
    R28 (Fail Loudly): exchange fetch errors are caught and reported in
    HistoryAnalysis.analysis_error, not swallowed silently.
    """

    def __init__(self, exchange, loop: Optional[asyncio.AbstractEventLoop] = None):
        """
        exchange  — an initialised ccxt exchange instance (sync or async).
        loop      — event loop for async ccxt; None uses the running loop.
        """
        self._exchange = exchange
        self._loop     = loop
        self._cache:   dict[str, HistoryAnalysis] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze_sync(self, symbol: str,
                     limit: int = MAX_HISTORY_FETCH) -> HistoryAnalysis:
        """
        Synchronous wrapper.  Fetches and classifies trade history for one
        symbol.  Returns a HistoryAnalysis regardless of errors.
        """
        try:
            raw = self._fetch_sync(symbol, limit)
            return self._build_analysis(raw, symbol, limit)
        except Exception as e:
            logger.error("TradeHistorian.analyze_sync(%s): %s", symbol, e)
            return HistoryAnalysis(
                symbol       = symbol,
                exchange_id  = getattr(self._exchange, "id", "unknown"),
                trade_count  = 0,
                analysis_error = str(e),
            )

    async def analyze_async(self, symbol: str,
                            limit: int = MAX_HISTORY_FETCH) -> HistoryAnalysis:
        """Async version for use in async exchange contexts."""
        try:
            raw = await self._fetch_async(symbol, limit)
            return self._build_analysis(raw, symbol, limit)
        except Exception as e:
            logger.error("TradeHistorian.analyze_async(%s): %s", symbol, e)
            return HistoryAnalysis(
                symbol       = symbol,
                exchange_id  = getattr(self._exchange, "id", "unknown"),
                trade_count  = 0,
                analysis_error = str(e),
            )

    def analyze_all_sync(self, symbols: list[str],
                         limit: int = MAX_HISTORY_FETCH
                         ) -> dict[str, HistoryAnalysis]:
        """Scan all provided symbols. Returns {symbol: HistoryAnalysis}."""
        results = {}
        for sym in symbols:
            logger.info("TradeHistorian: scanning %s...", sym)
            results[sym] = self.analyze_sync(sym, limit)
            self._cache[sym] = results[sym]
        return results

    def get_cached(self, symbol: str) -> Optional[HistoryAnalysis]:
        """Return the most recent analysis for a symbol without re-fetching."""
        return self._cache.get(symbol)

    def clear_cache(self):
        self._cache.clear()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fetch_sync(self, symbol: str, limit: int) -> list[dict]:
        """Fetch trade history from exchange using ccxt sync API."""
        try:
            trades = self._exchange.fetch_my_trades(symbol, limit=limit)
            logger.info("TradeHistorian: fetched %d trades for %s",
                        len(trades), symbol)
            return trades or []
        except Exception as e:
            # R28: fail loudly — propagate to caller for transparent error
            raise RuntimeError(
                f"Exchange trade history fetch failed for {symbol}: {e}"
            ) from e

    async def _fetch_async(self, symbol: str, limit: int) -> list[dict]:
        """Fetch trade history from exchange using ccxt async API."""
        try:
            trades = await self._exchange.fetch_my_trades(symbol, limit=limit)
            return trades or []
        except Exception as e:
            raise RuntimeError(
                f"Exchange trade history fetch failed for {symbol}: {e}"
            ) from e

    def _build_analysis(self, raw: list[dict],
                        symbol: str, limit: int) -> HistoryAnalysis:
        """Build HistoryAnalysis from raw ccxt trade records."""
        exc_id = getattr(self._exchange, "id", "unknown")

        analysis = HistoryAnalysis(
            symbol      = symbol,
            exchange_id = exc_id,
            trade_count = len(raw),
            history_truncated = (len(raw) >= limit),
        )

        if not raw:
            return analysis

        # Classify all trades
        trades = TradeClassifier.classify(raw, symbol)
        analysis.trades = trades

        # Count by role
        analysis.scrum_count      = sum(1 for t in trades
                                        if t.acervator_role == "SCRUM")
        analysis.fold_count       = sum(1 for t in trades
                                        if t.acervator_role == "FOLD")
        analysis.hedge_count      = sum(1 for t in trades
                                        if t.acervator_role == "HEDGE")
        analysis.rapid_fire_count = sum(1 for t in trades
                                        if t.acervator_role == "RAPID_FIRE")
        analysis.unknown_count    = sum(1 for t in trades
                                        if t.acervator_role == "UNKNOWN")
        analysis.has_unrecognized_trades = analysis.unknown_count > 0

        # Pair cycles
        cycles = TradeClassifier.pair_cycles(trades)
        analysis.cycles              = cycles
        analysis.complete_cycles     = len(cycles)
        analysis.profitable_cycles   = sum(1 for c in cycles if c.profitable)
        analysis.total_advantage_usd = sum(c.cycle_advantage for c in cycles)
        if cycles:
            analysis.avg_cycle_duration_h = statistics.mean(
                c.duration_hours for c in cycles)

        # Reconstruct estimated state
        net_qty   = 0.0
        total_buy_cost  = 0.0
        total_buy_qty   = 0.0
        net_pnl         = 0.0

        for t in trades:
            if t.side == "buy":
                net_qty        += t.quantity
                total_buy_cost += t.cost_usd + t.fee_usd
                total_buy_qty  += t.quantity
                net_pnl        -= (t.cost_usd + t.fee_usd)
            elif t.side == "sell":
                net_qty        -= t.quantity
                net_pnl        += (t.cost_usd - t.fee_usd)

        analysis.est_holdings  = max(net_qty, 0.0)
        analysis.est_cost_basis = (total_buy_cost / total_buy_qty
                                   if total_buy_qty > 0 else 0.0)
        analysis.net_pnl_usd   = net_pnl

        logger.info("TradeHistorian: %s — %d scrums, %d folds, "
                    "%d hedges, %d RF, %d unknown | "
                    "%d cycles | est holdings %.6f",
                    symbol,
                    analysis.scrum_count, analysis.fold_count,
                    analysis.hedge_count, analysis.rapid_fire_count,
                    analysis.unknown_count,
                    analysis.complete_cycles,
                    analysis.est_holdings)

        return analysis


# ---------------------------------------------------------------------------
# Convenience function for the ccxt connector
# ---------------------------------------------------------------------------

def scan_on_connect(exchange,
                    symbols:    list[str],
                    limit:      int = MAX_HISTORY_FETCH,
                    on_result:  Optional[callable] = None,
                    pace_s:     float = 0.0,
                    ) -> dict[str, HistoryAnalysis]:
    """
    Entry point called by ccxt_connector on every connect / reconnect /
    refresh.  Runs synchronously.  Calls on_result(symbol, analysis)
    for each symbol as results come in (for incremental GUI updates).

    Returns {symbol: HistoryAnalysis} for all symbols.

    R29: Safe to call multiple times — each call is a fresh read.
    R28: Errors are surfaced in HistoryAnalysis.analysis_error, never
         swallowed.
    """
    if not symbols:
        logger.info("TradeHistorian: no symbols provided — skipping scan")
        return {}

    historian = TradeHistorian(exchange)
    results   = {}

    for _i, sym in enumerate(symbols):
        # v3.24.95 — SPACE THE FETCHES.
        #
        # `_fetch_sync` calls the RAW ccxt object, so none of the
        # connector's rate limiting, serialisation or retry applies
        # here. MEASURED on the 3.24.94 launch: 200 fetches in the
        # first 24 seconds, all rate-limited by Coinbase.
        #
        # Sleeps BETWEEN symbols only, never before the first, so a
        # single-symbol refresh stays immediate.
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

        # Log a brief summary at INFO level
        logger.info(analysis.summary())

    return results
