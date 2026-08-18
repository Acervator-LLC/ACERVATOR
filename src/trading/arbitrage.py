"""
arbitrage.py — Cross-exchange price awareness and routing.

Monitors prices across connected exchanges and provides:
- Best-price routing for scrumming/folding decisions
- Spread alerts when significant price divergence is detected
- Historical spread tracking for reporting
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.arbitrage")


@dataclass
class PriceQuote:
    """Price snapshot from a single exchange."""
    exchange_id: str
    symbol: str
    bid: float          # Best bid (sell into)
    ask: float          # Best ask (buy from)
    last: float
    timestamp: float
    volume_24h: float = 0


@dataclass
class SpreadOpportunity:
    """A detected cross-exchange spread."""
    symbol: str
    buy_exchange: str   # Cheaper exchange (lower ask)
    sell_exchange: str   # More expensive exchange (higher bid)
    buy_price: float
    sell_price: float
    spread_pct: float
    estimated_profit_pct: float  # After estimated fees
    timestamp: float


class ArbitrageMonitor:
    """
    Monitors prices across exchanges for the same trading pairs.
    Does NOT execute arbitrage — instead provides price-aware routing
    recommendations to existing bots.
    """

    TYPICAL_FEE_PCT = 0.1  # 0.1% taker fee per side

    def __init__(self):
        self._quotes: dict[str, dict[str, PriceQuote]] = {}  # symbol → {exchange → quote}
        self._spreads: list[SpreadOpportunity] = []
        self._max_spreads = 5000
        self._fee_override: dict[str, float] = {}  # exchange → fee %

    def update_price(self, exchange_id: str, symbol: str,
                     bid: float, ask: float, last: float,
                     volume_24h: float = 0):
        """Update price quote for a symbol on an exchange."""
        if symbol not in self._quotes:
            self._quotes[symbol] = {}

        self._quotes[symbol][exchange_id] = PriceQuote(
            exchange_id=exchange_id, symbol=symbol,
            bid=bid, ask=ask, last=last,
            timestamp=time.time(), volume_24h=volume_24h)

    def set_exchange_fee(self, exchange_id: str, fee_pct: float):
        """Override default fee for an exchange."""
        self._fee_override[exchange_id] = fee_pct

    def get_best_buy_exchange(self, symbol: str) -> Optional[str]:
        """Return exchange with the lowest ask price for a symbol."""
        quotes = self._quotes.get(symbol, {})
        if not quotes:
            return None
        # Filter stale quotes (> 60 seconds old)
        now = time.time()
        fresh = {eid: q for eid, q in quotes.items()
                 if now - q.timestamp < 60 and q.ask > 0}
        if not fresh:
            return None
        return min(fresh, key=lambda eid: fresh[eid].ask)

    def get_best_sell_exchange(self, symbol: str) -> Optional[str]:
        """Return exchange with the highest bid price for a symbol."""
        quotes = self._quotes.get(symbol, {})
        if not quotes:
            return None
        now = time.time()
        fresh = {eid: q for eid, q in quotes.items()
                 if now - q.timestamp < 60 and q.bid > 0}
        if not fresh:
            return None
        return max(fresh, key=lambda eid: fresh[eid].bid)

    def get_price_comparison(self, symbol: str) -> list[dict]:
        """Get all exchange prices for a symbol, sorted by price."""
        quotes = self._quotes.get(symbol, {})
        result = []
        for eid, q in quotes.items():
            age = time.time() - q.timestamp
            result.append({
                "exchange": eid,
                "bid": q.bid,
                "ask": q.ask,
                "last": q.last,
                "spread_pct": ((q.ask - q.bid) / q.bid * 100) if q.bid > 0 else 0,
                "volume_24h": q.volume_24h,
                "age_seconds": round(age, 1),
                "stale": age > 60,
            })
        return sorted(result, key=lambda x: x["last"])

    def detect_spreads(self, min_spread_pct: float = 0.3) -> list[SpreadOpportunity]:
        """
        Scan all symbols for cross-exchange spread opportunities.
        Returns opportunities where spread > min_spread_pct after fees.
        """
        now = time.time()
        new_opps = []

        for symbol, quotes in self._quotes.items():
            fresh = {eid: q for eid, q in quotes.items()
                     if now - q.timestamp < 60 and q.bid > 0 and q.ask > 0}
            if len(fresh) < 2:
                continue

            exchanges = list(fresh.keys())
            for i in range(len(exchanges)):
                for j in range(i + 1, len(exchanges)):
                    a, b = exchanges[i], exchanges[j]
                    qa, qb = fresh[a], fresh[b]

                    # Check a→b spread (buy on a, sell on b)
                    if qb.bid > qa.ask:
                        spread = (qb.bid - qa.ask) / qa.ask * 100
                        fee_a = self._fee_override.get(a, self.TYPICAL_FEE_PCT)
                        fee_b = self._fee_override.get(b, self.TYPICAL_FEE_PCT)
                        net = spread - fee_a - fee_b
                        if net >= min_spread_pct:
                            opp = SpreadOpportunity(
                                symbol=symbol, buy_exchange=a, sell_exchange=b,
                                buy_price=qa.ask, sell_price=qb.bid,
                                spread_pct=round(spread, 4),
                                estimated_profit_pct=round(net, 4),
                                timestamp=now)
                            new_opps.append(opp)

                    # Check b→a spread
                    if qa.bid > qb.ask:
                        spread = (qa.bid - qb.ask) / qb.ask * 100
                        fee_a = self._fee_override.get(a, self.TYPICAL_FEE_PCT)
                        fee_b = self._fee_override.get(b, self.TYPICAL_FEE_PCT)
                        net = spread - fee_a - fee_b
                        if net >= min_spread_pct:
                            opp = SpreadOpportunity(
                                symbol=symbol, buy_exchange=b, sell_exchange=a,
                                buy_price=qb.ask, sell_price=qa.bid,
                                spread_pct=round(spread, 4),
                                estimated_profit_pct=round(net, 4),
                                timestamp=now)
                            new_opps.append(opp)

        self._spreads.extend(new_opps)
        if len(self._spreads) > self._max_spreads:
            self._spreads = self._spreads[-self._max_spreads:]

        return new_opps

    def get_routing_recommendation(self, symbol: str, side: str) -> dict:
        """
        Get a routing recommendation for a trade.
        Returns the best exchange and price for the given side.
        """
        if side == "buy":
            best_eid = self.get_best_buy_exchange(symbol)
            quotes = self._quotes.get(symbol, {})
            if best_eid and best_eid in quotes:
                q = quotes[best_eid]
                others = {eid: qq.ask for eid, qq in quotes.items()
                          if eid != best_eid and qq.ask > 0}
                savings = 0
                if others:
                    avg_other = sum(others.values()) / len(others)
                    savings = (avg_other - q.ask) / avg_other * 100
                return {
                    "exchange": best_eid,
                    "price": q.ask,
                    "savings_pct": round(savings, 4),
                    "alternatives": len(others),
                }
        else:
            best_eid = self.get_best_sell_exchange(symbol)
            quotes = self._quotes.get(symbol, {})
            if best_eid and best_eid in quotes:
                q = quotes[best_eid]
                others = {eid: qq.bid for eid, qq in quotes.items()
                          if eid != best_eid and qq.bid > 0}
                premium = 0
                if others:
                    avg_other = sum(others.values()) / len(others)
                    premium = (q.bid - avg_other) / avg_other * 100
                return {
                    "exchange": best_eid,
                    "price": q.bid,
                    "premium_pct": round(premium, 4),
                    "alternatives": len(others),
                }

        return {"exchange": None, "price": 0, "savings_pct": 0, "alternatives": 0}

    def get_spread_history(self, symbol: str = "", hours: float = 24) -> list[dict]:
        """Get historical spread opportunities."""
        cutoff = time.time() - hours * 3600
        return [
            {"symbol": s.symbol, "buy_on": s.buy_exchange, "sell_on": s.sell_exchange,
             "spread_pct": s.spread_pct, "net_pct": s.estimated_profit_pct,
             "timestamp": s.timestamp}
            for s in self._spreads
            if s.timestamp >= cutoff and (not symbol or s.symbol == symbol)
        ]

    def get_monitored_symbols(self) -> list[str]:
        """Return list of symbols being monitored across exchanges."""
        return sorted(self._quotes.keys())

    def get_summary(self) -> dict:
        """Return summary of arbitrage monitoring state."""
        now = time.time()
        active_symbols = len(self._quotes)
        active_exchanges = set()
        for quotes in self._quotes.values():
            for eid in quotes:
                active_exchanges.add(eid)

        recent_opps = [s for s in self._spreads if now - s.timestamp < 3600]
        return {
            "monitored_symbols": active_symbols,
            "monitored_exchanges": len(active_exchanges),
            "exchange_names": sorted(active_exchanges),
            "opportunities_1h": len(recent_opps),
            "best_spread": max((s.spread_pct for s in recent_opps), default=0),
            "avg_spread": (sum(s.spread_pct for s in recent_opps) / len(recent_opps)
                           if recent_opps else 0),
        }


# v3.19.41 (sadp R28 FL): `from typing import Optional` moved from
# end-of-file to top with the other imports. Pre-fix the import was at
# the bottom AFTER class definitions that referenced `Optional[str]` —
# only `from __future__ import annotations` (PEP 563) prevented a
# NameError at module load by making annotations lazy strings. If
# anyone called `typing.get_type_hints(ArbitrageMonitor)` at runtime
# they would have hit the broken ordering. Now correct-by-construction.
