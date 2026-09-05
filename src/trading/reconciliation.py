"""State recovery, order reconciliation, and trade journaling.

``TradeJournal.record`` and ``CrashRecovery.save_snapshot`` are driven from
``main_window``'s tick. ``ReconciliationEngine`` is constructed there and
handed to the journal tab, but nothing calls ``reconcile`` or
``cancel_orphaned``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.reconciliation")


@dataclass
class JournalEntry:
    """A single trade journal entry with full context."""

    timestamp: float
    bot_id: str
    symbol: str
    action: str  # "scrum", "fold", "distribute", "grid_buy", "grid_sell"
    side: str  # "buy" or "sell"
    price: float
    quantity: float
    cost: float
    pnl: float = 0.0
    # TA context at time of trade
    ta_direction: str = ""
    ta_confidence: float = 0.0
    ta_timeframe: str = ""
    ta_signals: dict = field(default_factory=dict)  # indicator → direction
    # Market context
    market_price: float = 0.0
    spread_pct: float = 0.0
    volume_24h: float = 0.0
    # Execution details
    order_id: str = ""
    exchange_id: str = ""
    execution_strategy: str = "market"
    slippage_pct: float = 0.0
    fill_time_ms: float = 0.0
    # Decision reasoning
    reason: str = ""  # Why this trade was made


@dataclass
class OrphanedOrder:
    """An order found on exchange with no matching local bot state."""

    exchange_id: str
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    filled: float
    status: str
    created_at: float
    recommendation: str  # "cancel", "adopt", "monitor"


@dataclass
class ReconciliationResult:
    """Result of a reconciliation check."""

    timestamp: float
    exchange_id: str
    orders_checked: int
    matched: int
    orphaned: list[OrphanedOrder] = field(default_factory=list)
    mismatched: list[dict] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)


class TradeJournal:
    """
    Persistent trade journal that records every trade with full TA and market context.
    Writes to disk for post-mortem analysis.
    """

    def __init__(self, data_dir: Path = None):
        self._dir = data_dir or Path.home() / ".acervator" / "journal"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._entries: list[JournalEntry] = []
        self._max_memory = 10000
        self._load_recent()

    def record(self, entry: JournalEntry):

        # sadp: R28 R29 R33  # reconcile record: fail-loudly(R28) idempotent(R29) append-only(R33)
        """Record a journal entry (memory + disk)."""
        self._entries.append(entry)
        if len(self._entries) > self._max_memory:
            self._entries = self._entries[-self._max_memory :]
        self._write_entry(entry)
        logger.debug(
            "Journal: %s %s %.8f %s @ $%.8f (P/L=$%.4f)",
            entry.action,
            entry.side,
            entry.quantity,
            entry.symbol,
            entry.price,
            entry.pnl,
        )

    def record_from_trade(
        self,
        bot_id: str,
        symbol: str,
        action: str,
        side: str,
        price: float,
        quantity: float,
        cost: float = 0,
        pnl: float = 0,
        ta_summary=None,
        exchange_id: str = "",
        order_id: str = "",
        reason: str = "",
        execution_strategy: str = "market",
        slippage_pct: float = 0,
    ):

        # sadp: R28 R29 R33  # reconcile record: fail-loudly(R28) idempotent(R29) append-only(R33)
        """Convenience method to record from trade parameters."""
        ta_dir = ""
        ta_conf = 0.0
        ta_tf = ""
        ta_sigs = {}
        if ta_summary:
            ta_dir = getattr(ta_summary, "consensus_direction", None)
            if ta_dir:
                ta_dir = ta_dir.name if hasattr(ta_dir, "name") else str(ta_dir)
            ta_conf = getattr(ta_summary, "consensus_confidence", 0)
            ta_tf = getattr(ta_summary, "timeframe", "")
            for sig in getattr(ta_summary, "signals", []):
                ta_sigs[sig.indicator] = sig.direction.name

        entry = JournalEntry(
            timestamp=time.time(),
            bot_id=bot_id,
            symbol=symbol,
            action=action,
            side=side,
            price=price,
            quantity=quantity,
            cost=cost or price * quantity,
            pnl=pnl,
            ta_direction=ta_dir or "",
            ta_confidence=ta_conf,
            ta_timeframe=ta_tf,
            ta_signals=ta_sigs,
            order_id=order_id,
            exchange_id=exchange_id,
            execution_strategy=execution_strategy,
            slippage_pct=slippage_pct,
            reason=reason,
        )
        self.record(entry)

    def get_entries(
        self, bot_id: str = "", symbol: str = "", hours: float = 24, limit: int = 200
    ) -> list[dict]:
        """Query journal entries."""
        cutoff = time.time() - hours * 3600
        results = []
        for e in reversed(self._entries):
            if e.timestamp < cutoff:
                break
            if bot_id and e.bot_id != bot_id:
                continue
            if symbol and e.symbol != symbol:
                continue
            results.append(asdict(e))
            if len(results) >= limit:
                break
        return results

    def get_statistics(self) -> dict:
        """Get journal statistics."""
        if not self._entries:
            return {"total_entries": 0, "unique_bots": 0, "date_range": ""}

        actions: dict[str, int] = {}
        for e in self._entries:
            actions[e.action] = actions.get(e.action, 0) + 1

        return {
            "total_entries": len(self._entries),
            "unique_bots": len(set(e.bot_id for e in self._entries)),
            "unique_symbols": len(set(e.symbol for e in self._entries)),
            "actions": actions,
            "total_pnl": round(sum(e.pnl for e in self._entries), 4),
            "date_range": f"{time.ctime(self._entries[0].timestamp)} → "
            f"{time.ctime(self._entries[-1].timestamp)}",
            "journal_dir": str(self._dir),
        }

    def _write_entry(self, entry: JournalEntry):

        # sadp: R28 R33  # journal write: fail-loudly(R28) append-only(R33)
        """Append entry to daily journal file."""
        try:
            date_str = time.strftime("%Y-%m-%d", time.localtime(entry.timestamp))
            filepath = self._dir / f"journal_{date_str}.jsonl"
            with open(filepath, "a") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        except Exception as e:
            logger.error("Failed to write journal entry: %s", e)

    def _load_recent(self):
        """Load recent journal entries from disk."""
        try:
            files = sorted(self._dir.glob("journal_*.jsonl"))
            # Load last 3 days
            for f in files[-3:]:
                with open(f) as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                d = json.loads(line)
                                entry = JournalEntry(
                                    **{
                                        k: v
                                        for k, v in d.items()
                                        if k in JournalEntry.__dataclass_fields__
                                    }
                                )
                                self._entries.append(entry)
                            except Exception as _line_exc:
                                logger.debug(
                                    "journal line skipped (%s): %s",
                                    type(_line_exc).__name__,
                                    _line_exc,
                                )
            logger.info("Loaded %d journal entries from disk", len(self._entries))
        except Exception as e:
            logger.warning("Failed to load journal: %s", e)


class ReconciliationEngine:
    """
    Compares local bot state against actual exchange orders.
    Detects orphaned orders and state mismatches after crashes.
    """

    def __init__(self):
        self._results: list[ReconciliationResult] = []

    async def reconcile(
        self, exchange, bot_manager, exchange_id: str
    ) -> ReconciliationResult:
        """Compare ``exchange.fetch_open_orders`` against ``local_order_ids``.

        No caller invokes this; ``_results`` stays empty for
        ``get_latest_result``.
        """
        now = time.time()
        result = ReconciliationResult(
            timestamp=now, exchange_id=exchange_id, orders_checked=0, matched=0
        )

        try:
            # Fetch all open orders from exchange
            open_orders = await exchange.fetch_open_orders()
            result.orders_checked = len(open_orders)

            # Never populated, so every open order below is called an orphan.
            local_order_ids: set = set()

            for order in open_orders:
                oid = order.get("id", "")
                if oid in local_order_ids:
                    result.matched += 1
                else:
                    orphan = OrphanedOrder(
                        exchange_id=exchange_id,
                        order_id=oid,
                        symbol=order.get("symbol", ""),
                        side=order.get("side", ""),
                        price=order.get("price", 0),
                        quantity=order.get("amount", 0),
                        filled=order.get("filled", 0),
                        status=order.get("status", ""),
                        created_at=(
                            order.get("timestamp", 0) / 1000
                            if order.get("timestamp")
                            else 0
                        ),
                        recommendation=self._recommend_action(order),
                    )
                    result.orphaned.append(orphan)

            logger.info(
                "Reconciliation %s: %d orders checked, %d matched, " "%d orphaned",
                exchange_id,
                result.orders_checked,
                result.matched,
                len(result.orphaned),
            )

        except Exception as e:
            logger.error("Reconciliation failed for %s: %s", exchange_id, e)
            result.actions_taken.append(f"ERROR: {e}")

        self._results.append(result)
        return result

    async def cancel_orphaned(self, exchange, orphan: OrphanedOrder) -> bool:
        """Cancel an orphaned order."""
        try:
            await exchange.cancel_order(orphan.order_id, orphan.symbol)
            logger.info(
                "Cancelled orphaned order %s on %s", orphan.order_id, orphan.exchange_id
            )
            return True
        except Exception as e:
            logger.error("Failed to cancel orphan %s: %s", orphan.order_id, e)
            return False

    def _recommend_action(self, order: dict) -> str:
        """Recommend action for an orphaned order."""
        filled = order.get("filled", 0)
        amount = order.get("amount", 0)
        age = time.time() - (
            order.get("timestamp", 0) / 1000 if order.get("timestamp") else time.time()
        )

        if filled > 0 and filled < amount:
            return "monitor"  # Partially filled, don't cancel
        if age > 86400:
            return "cancel"  # Over 24 hours old
        if age > 3600:
            return "cancel"  # Over 1 hour old
        return "monitor"

    def get_latest_result(self, exchange_id: str = "") -> Optional[dict]:
        """Get most recent reconciliation result."""
        for r in reversed(self._results):
            if not exchange_id or r.exchange_id == exchange_id:
                return {
                    "timestamp": r.timestamp,
                    "exchange": r.exchange_id,
                    "orders_checked": r.orders_checked,
                    "matched": r.matched,
                    "orphaned_count": len(r.orphaned),
                    "orphaned": [
                        {
                            "order_id": o.order_id[:12],
                            "symbol": o.symbol,
                            "side": o.side,
                            "price": o.price,
                            "recommendation": o.recommendation,
                        }
                        for o in r.orphaned
                    ],
                }
        return None


class CrashRecovery:
    """
    Saves periodic state snapshots for crash recovery.
    On startup, compares saved state against exchange state.
    """

    def __init__(self, data_dir: Path = None):
        self._dir = data_dir or Path.home() / ".acervator" / "recovery"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._snapshot_interval = 30  # seconds
        self._last_snapshot = 0

    def save_snapshot(self, bot_manager, force: bool = False):
        """Save a state snapshot if interval has elapsed."""
        now = time.time()
        if not force and now - self._last_snapshot < self._snapshot_interval:
            return

        self._last_snapshot = now
        try:
            statuses = bot_manager.list_bots()
            snapshot = {
                "timestamp": now,
                "bots": statuses,
                "bot_count": len(statuses),
            }
            filepath = self._dir / "last_snapshot.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
        except Exception as e:
            logger.error("Snapshot save failed: %s", e)

    def load_snapshot(self) -> Optional[dict]:
        """Load the most recent crash recovery snapshot."""
        filepath = self._dir / "last_snapshot.json"
        if not filepath.exists():
            return None
        try:
            with open(filepath) as f:
                return json.load(f)
        except Exception as e:
            logger.error("Snapshot load failed: %s", e)
            return None

    def get_recovery_info(self) -> dict:
        """Get info about available recovery data."""
        snapshot = self.load_snapshot()
        journal_dir = self._dir.parent / "journal"
        journal_files = (
            list(journal_dir.glob("journal_*.jsonl")) if journal_dir.exists() else []
        )

        return {
            "has_snapshot": snapshot is not None,
            "snapshot_age": (time.time() - snapshot["timestamp"] if snapshot else 0),
            "snapshot_bots": snapshot.get("bot_count", 0) if snapshot else 0,
            "journal_files": len(journal_files),
            "recovery_dir": str(self._dir),
        }
