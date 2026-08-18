"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
volume_guard.py — Volume-Aware Trade Execution Guard

Prevents disproportionately large trades relative to current market
conditions. Sits between bot trade decisions and exchange execution.

Core Algorithm:
  1. Profile the market: 24h volume, orderbook depth, spread
  2. Compute safe trade size from volume participation limits
  3. If trade exceeds safe size → split into adaptive iceberg chunks
  4. Chunks sized and timed to market rhythm (high volume = bigger/faster)

This is a smart version of iceberg trading that adapts in real-time
to actual market conditions rather than using fixed chunk sizes.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.execution")


# ───────────────────────────────────────────────────────────────────
# Configuration
# ───────────────────────────────────────────────────────────────────

@dataclass
class VolumeGuardConfig:
    """Tunable parameters for volume-aware execution."""

    # Max fraction of 24h volume per single order (0.001 = 0.1%)
    max_single_order_volume_pct: float = 0.001

    # Max fraction of hourly volume our bot can consume per hour
    max_hourly_participation_pct: float = 0.02  # 2% of hourly volume

    # Max fraction of top-of-book liquidity to hit in one order
    max_book_depth_pct: float = 0.25  # Take max 25% of visible book depth

    # Price slippage threshold — abort if estimated slippage exceeds this
    max_slippage_pct: float = 1.0  # 1% max acceptable slippage

    # Chunk execution timing
    min_chunk_delay_ms: int = 200      # Minimum ms between chunks
    max_chunk_delay_ms: int = 5000     # Maximum ms between chunks
    chunk_headroom_pct: float = 0.7    # Use 70% of safe size per chunk

    # Orderbook analysis depth (levels from top)
    book_depth_levels: int = 20

    # Minimum volume required to consider a market tradeable
    min_daily_volume_usd: float = 1000.0  # $1K minimum

    # Enable/disable the guard (pass-through when disabled)
    enabled: bool = True

    # Cache TTL for market profiles (seconds)
    profile_cache_ttl: float = 30.0


# ───────────────────────────────────────────────────────────────────
# Market Profile (point-in-time snapshot)
# ───────────────────────────────────────────────────────────────────

@dataclass
class MarketProfile:
    """Snapshot of market conditions for a symbol at a given moment."""
    symbol: str
    timestamp: float

    # Price
    last_price: float = 0
    bid: float = 0
    ask: float = 0
    spread_pct: float = 0  # (ask - bid) / mid * 100

    # Volume
    volume_24h_quote: float = 0      # Total 24h volume in quote currency
    volume_hourly_est: float = 0     # Estimated hourly volume
    avg_trade_size_est: float = 0    # Estimated average trade size (quote)

    # Orderbook depth
    bid_depth_quote: float = 0       # Total bid liquidity in quote (N levels)
    ask_depth_quote: float = 0       # Total ask liquidity in quote (N levels)
    bid_depth_levels: int = 0        # Number of bid levels analyzed
    ask_depth_levels: int = 0        # Number of ask levels analyzed

    # Computed safe sizes
    safe_single_order_quote: float = 0   # Max safe order in quote currency
    safe_single_order_base: float = 0    # Max safe order in base currency
    hourly_budget_remaining: float = 0   # Quote budget for this hour

    # Market health indicators
    is_tradeable: bool = True
    thin_market: bool = False        # Low liquidity warning
    wide_spread: bool = False        # Spread > 0.5%
    low_volume: bool = False         # Volume below threshold


@dataclass
class ChunkPlan:
    """Execution plan: how to split a large order into market-safe chunks."""
    original_amount: float       # Requested trade amount (base)
    original_quote_value: float  # Estimated quote value
    needs_chunking: bool         # Whether splitting is needed
    chunks: list[float] = field(default_factory=list)  # Chunk sizes (base)
    chunk_delay_ms: int = 500    # Delay between chunks
    estimated_slippage_pct: float = 0
    reason: str = ""
    market_profile: Optional[MarketProfile] = None


@dataclass
class ExecutionReport:
    """Post-execution report for a volume-guarded trade."""
    success: bool
    symbol: str
    side: str
    requested_amount: float
    executed_amount: float
    chunks_planned: int
    chunks_executed: int
    avg_fill_price: float
    estimated_slippage_pct: float
    actual_slippage_pct: float
    total_quote: float
    execution_time_ms: float
    strategy: str  # "passthrough", "single", "iceberg_N"
    reason: str = ""
    fills: list[dict] = field(default_factory=list)


# ───────────────────────────────────────────────────────────────────
# Volume Guard
# ───────────────────────────────────────────────────────────────────

class VolumeGuard:
    """
    Volume-aware trade execution guard.

    Wraps exchange.place_order to prevent market-moving trades.
    Analyzes real-time volume and orderbook depth to compute safe
    trade sizes, then executes as adaptive iceberg if needed.

    Usage:
        guard = VolumeGuard(exchange, config)
        report = await guard.execute(symbol, "sell", amount)
        if report.success:
            print(f"Filled {report.executed_amount} in {report.chunks_executed} chunks")
    """

    # Estimated trades per day for common market tiers
    # (Used to estimate avg trade size when recent trade data unavailable)
    TRADES_PER_DAY_EST = {
        "mega":   200_000,   # BTC/ETH top pairs: ~200K trades/day
        "large":   50_000,   # Top 20 coins: ~50K trades/day
        "mid":     15_000,   # Top 100 coins: ~15K trades/day
        "small":    3_000,   # Long tail: ~3K trades/day
        "micro":      500,   # Very low volume: ~500 trades/day
    }

    def __init__(self, exchange=None, config: VolumeGuardConfig = None):
        self._exchange = exchange
        self.config = config or VolumeGuardConfig()
        self._profile_cache: dict[str, MarketProfile] = {}
        self._hourly_usage: dict[str, float] = {}  # symbol → quote used this hour
        self._last_hour_reset: float = 0
        self._execution_history: list[ExecutionReport] = []
        self._max_history = 500

    def set_exchange(self, exchange):
        """Set or update the exchange connector."""
        self._exchange = exchange

    @property
    def enabled(self) -> bool:
        # MEM-259 (Session 26 operator directive): "Disable the fucking thing."
        # VolumeGuard is force-disabled. Always reports enabled=False so
        # BotContainer.guarded_place_order falls through to the direct
        # exchange.place_order path, which is still gated upstream by
        # _execute_buy's MEM-251/257 ceiling guards. Re-enabling requires
        # explicit operator action (edit this file).
        return False

    @enabled.setter
    def enabled(self, val: bool):
        # Setter retained for API compatibility but does not affect
        # the disabled property. MEM-259.
        self.config.enabled = val

    # ─── Main execution entry point ────────────────────────────────

    async def execute(self, symbol: str, side: str, amount: float,
                      price: float = 0, order_type: str = "market",
                      exchange=None) -> ExecutionReport:

        # sadp: R28 R29  # volume-gated order: fail-loudly(R28) idempotent(R29)
        """
        Execute a trade with volume-aware protection.

        If the trade is safe for market conditions, executes normally.
        If too large, splits into adaptive iceberg chunks.

        Parameters
        ----------
        symbol : Trading pair (e.g. "BTC/USDT")
        side : "buy" or "sell"
        amount : Amount in base currency
        price : Limit price (0 = market)
        order_type : "market" or "limit"
        exchange : Exchange connector (overrides default)

        Returns
        -------
        ExecutionReport with fill details
        """
        start = time.monotonic()
        ex = exchange or self._exchange

        # Pass-through if disabled
        if not self.config.enabled:
            return await self._execute_passthrough(
                symbol, side, amount, price, order_type, start, ex)

        if not ex:
            return ExecutionReport(
                success=False, symbol=symbol, side=side,
                requested_amount=amount, executed_amount=0,
                chunks_planned=0, chunks_executed=0,
                avg_fill_price=0, estimated_slippage_pct=0,
                actual_slippage_pct=0, total_quote=0,
                execution_time_ms=0, strategy="error",
                reason="No exchange connector set")

        # 1. Profile the market
        profile = await self._get_market_profile(symbol, ex)

        if not profile.is_tradeable:
            logger.warning("VolumeGuard: %s not tradeable — %s",
                          symbol,
                          "low volume" if profile.low_volume else "no data")
            # Still allow the trade but log warning
            return await self._execute_passthrough(
                symbol, side, amount, price, order_type, start, ex)

        # 2. Plan the execution
        ref_price = price if price > 0 else profile.last_price
        plan = self._compute_chunk_plan(amount, ref_price, side, profile)

        logger.info("VolumeGuard [%s %s %s]: amount=%.8f, quote=$%.2f, "
                    "safe=$%.2f, chunks=%d, reason=%s",
                    side.upper(), symbol, "CHUNK" if plan.needs_chunking else "PASS",
                    amount, plan.original_quote_value,
                    profile.safe_single_order_quote,
                    len(plan.chunks), plan.reason)

        # 3. Execute
        if not plan.needs_chunking:
            report = await self._execute_single(
                symbol, side, amount, price, order_type, profile, start, ex)
        else:
            report = await self._execute_iceberg(
                symbol, side, plan, price, order_type, profile, start, ex)

        # 4. Track hourly usage
        self._track_hourly_usage(symbol, report.total_quote)

        # 5. Record history
        self._execution_history.append(report)
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]

        return report

    # ─── Market Profiling ──────────────────────────────────────────

    async def _get_market_profile(self, symbol: str, ex=None) -> MarketProfile:
        """Build or retrieve cached market profile for a symbol."""
        now = time.time()
        exchange = ex or self._exchange

        # Check cache
        cached = self._profile_cache.get(symbol)
        if cached and (now - cached.timestamp) < self.config.profile_cache_ttl:
            # Update hourly budget from current usage
            cached.hourly_budget_remaining = self._get_hourly_budget(
                symbol, cached.volume_hourly_est)
            return cached

        profile = MarketProfile(symbol=symbol, timestamp=now)

        try:
            # Fetch ticker for price + volume
            ticker = await exchange.get_ticker(symbol)
            profile.last_price = ticker.last
            profile.bid = ticker.bid
            profile.ask = ticker.ask
            profile.volume_24h_quote = ticker.volume_24h

            # Spread analysis
            mid = (ticker.bid + ticker.ask) / 2 if (ticker.bid and ticker.ask) else ticker.last
            if mid > 0 and ticker.bid > 0 and ticker.ask > 0:
                profile.spread_pct = (ticker.ask - ticker.bid) / mid * 100
            profile.wide_spread = profile.spread_pct > 0.5

            # Volume analysis
            profile.volume_hourly_est = profile.volume_24h_quote / 24
            profile.low_volume = profile.volume_24h_quote < self.config.min_daily_volume_usd
            profile.is_tradeable = not profile.low_volume or profile.volume_24h_quote > 0

            # Estimate average trade size
            tier = self._classify_volume_tier(profile.volume_24h_quote)
            est_trades = self.TRADES_PER_DAY_EST.get(tier, 5000)
            profile.avg_trade_size_est = profile.volume_24h_quote / est_trades

            # Fetch orderbook for depth analysis
            try:
                book = await exchange.get_orderbook(
                    symbol, self.config.book_depth_levels)
                profile.bid_depth_quote = sum(
                    p * a for p, a in book.bids[:self.config.book_depth_levels])
                profile.ask_depth_quote = sum(
                    p * a for p, a in book.asks[:self.config.book_depth_levels])
                profile.bid_depth_levels = len(book.bids)
                profile.ask_depth_levels = len(book.asks)
            except Exception:  # R28-OK: orderbook probe; volume-derived estimate is the documented fallback
                # Orderbook unavailable — use volume-only estimates
                profile.bid_depth_quote = profile.volume_hourly_est * 0.1
                profile.ask_depth_quote = profile.volume_hourly_est * 0.1

            # Thin market detection
            book_depth = min(profile.bid_depth_quote, profile.ask_depth_quote)
            profile.thin_market = book_depth < profile.volume_hourly_est * 0.02

            # Compute safe trade sizes
            self._compute_safe_sizes(profile)

        except Exception as exc:
            logger.warning("VolumeGuard: Failed to profile %s: %s", symbol, exc)
            profile.is_tradeable = False

        self._profile_cache[symbol] = profile
        return profile

    def _compute_safe_sizes(self, profile: MarketProfile):
        """Compute maximum safe trade sizes from market profile."""
        cfg = self.config

        # Method 1: Volume-based limit
        # Don't exceed X% of daily volume in a single order
        vol_limit_quote = profile.volume_24h_quote * cfg.max_single_order_volume_pct

        # Method 2: Orderbook depth limit
        # Don't take more than X% of visible book depth
        if profile.bid_depth_quote > 0 and profile.ask_depth_quote > 0:
            book_limit_quote = (min(profile.bid_depth_quote, profile.ask_depth_quote)
                                * cfg.max_book_depth_pct)
        else:
            book_limit_quote = vol_limit_quote  # Fallback to volume-only

        # Method 3: Average trade size limit
        # Don't exceed N multiples of the estimated average trade size
        # (even a "large" trade should be at most 10x average)
        avg_limit_quote = profile.avg_trade_size_est * 10

        # Take the most conservative (smallest) limit
        safe_quote = max(
            min(vol_limit_quote, book_limit_quote, avg_limit_quote),
            0.01  # Absolute minimum to avoid zero
        )

        profile.safe_single_order_quote = safe_quote
        if profile.last_price > 0:
            profile.safe_single_order_base = safe_quote / profile.last_price
        else:
            profile.safe_single_order_base = 0

        # Hourly participation budget
        profile.hourly_budget_remaining = self._get_hourly_budget(
            profile.symbol, profile.volume_hourly_est)

    def _classify_volume_tier(self, daily_volume_quote: float) -> str:
        """Classify a market's volume tier."""
        if daily_volume_quote >= 100_000_000:    # $100M+
            return "mega"
        if daily_volume_quote >= 10_000_000:     # $10M+
            return "large"
        if daily_volume_quote >= 1_000_000:      # $1M+
            return "mid"
        if daily_volume_quote >= 100_000:        # $100K+
            return "small"
        return "micro"

    # ─── Chunk Planning ────────────────────────────────────────────

    def _compute_chunk_plan(self, amount: float, ref_price: float,
                            side: str, profile: MarketProfile) -> ChunkPlan:
        """Determine if and how to split an order into chunks."""
        quote_value = amount * ref_price if ref_price > 0 else 0
        plan = ChunkPlan(
            original_amount=amount,
            original_quote_value=quote_value,
            needs_chunking=False,
            market_profile=profile)

        safe_quote = profile.safe_single_order_quote
        safe_base = profile.safe_single_order_base

        # Check if order fits within safe limits
        if safe_base <= 0 or amount <= safe_base:
            plan.needs_chunking = False
            plan.chunks = [amount]
            plan.reason = "within_safe_limits"
            return plan

        # Order too large — compute chunks
        plan.needs_chunking = True

        # Chunk size = safe_size * headroom factor
        chunk_base = safe_base * self.config.chunk_headroom_pct
        if chunk_base <= 0:
            chunk_base = amount  # Fallback: execute as single
            plan.needs_chunking = False

        n_chunks = math.ceil(amount / chunk_base)
        # Cap at reasonable number of chunks (no more than 50)
        n_chunks = min(n_chunks, 50)
        chunk_base = amount / n_chunks

        plan.chunks = [chunk_base] * n_chunks
        # Adjust last chunk for remainder
        total_planned = sum(plan.chunks)
        if total_planned != amount:
            plan.chunks[-1] += (amount - total_planned)

        # Compute inter-chunk delay
        # Higher volume → shorter delays (market absorbs faster)
        if profile.volume_hourly_est > 0:
            # Scale delay inversely with volume
            # At $1M/hr volume, ~500ms delay; at $10K/hr, ~3000ms
            volume_factor = min(profile.volume_hourly_est / 100_000, 10)
            delay = int(self.config.max_chunk_delay_ms / max(volume_factor, 0.5))
            delay = max(self.config.min_chunk_delay_ms,
                       min(delay, self.config.max_chunk_delay_ms))
        else:
            delay = self.config.max_chunk_delay_ms
        plan.chunk_delay_ms = delay

        # Estimate slippage from orderbook depth
        relevant_depth = (profile.ask_depth_quote if side == "buy"
                          else profile.bid_depth_quote)
        if relevant_depth > 0:
            plan.estimated_slippage_pct = (quote_value / relevant_depth) * 100
            plan.estimated_slippage_pct = min(plan.estimated_slippage_pct, 10)
        else:
            plan.estimated_slippage_pct = 0

        # Classify reason
        ratio = quote_value / safe_quote if safe_quote > 0 else 0
        if ratio > 20:
            plan.reason = f"extreme_size ({ratio:.0f}× safe limit)"
        elif ratio > 5:
            plan.reason = f"very_large ({ratio:.1f}× safe limit)"
        else:
            plan.reason = f"above_safe ({ratio:.1f}× safe limit)"

        return plan

    # ─── Execution Strategies ──────────────────────────────────────

    async def _execute_passthrough(self, symbol: str, side: str,
                                    amount: float, price: float,
                                    order_type: str, start: float,
                                    ex=None) -> ExecutionReport:

        # sadp: R28 R29  # volume-gated order: fail-loudly(R28) idempotent(R29)
        """Execute without any volume protection (disabled or fallback)."""
        from ..exchange.base import OrderSide, OrderType as OT
        exchange = ex or self._exchange
        os = OrderSide.BUY if side == "buy" else OrderSide.SELL
        ot = OT.MARKET if order_type == "market" else OT.LIMIT

        try:
            order = await exchange.place_order(
                symbol, os, ot, amount, price if price > 0 else None)
            fill_price = order.average or price or 0
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionReport(
                success=True, symbol=symbol, side=side,
                requested_amount=amount, executed_amount=order.filled or amount,
                chunks_planned=1, chunks_executed=1,
                avg_fill_price=fill_price,
                estimated_slippage_pct=0, actual_slippage_pct=0,
                total_quote=fill_price * (order.filled or amount),
                execution_time_ms=elapsed, strategy="passthrough",
                fills=[{"price": fill_price, "amount": order.filled or amount}])
        except Exception as exc:  # R28-OK: error surfaced via ExecutionReport(success=False)
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionReport(
                success=False, symbol=symbol, side=side,
                requested_amount=amount, executed_amount=0,
                chunks_planned=1, chunks_executed=0,
                avg_fill_price=0, estimated_slippage_pct=0,
                actual_slippage_pct=0, total_quote=0,
                execution_time_ms=elapsed, strategy="passthrough",
                reason=str(exc))

    async def _execute_single(self, symbol: str, side: str,
                               amount: float, price: float,
                               order_type: str, profile: MarketProfile,
                               start: float, ex=None) -> ExecutionReport:

        # sadp: R28 R29  # volume-gated order: fail-loudly(R28) idempotent(R29)
        """Execute a single order that's within safe limits."""
        from ..exchange.base import OrderSide, OrderType as OT
        exchange = ex or self._exchange
        os = OrderSide.BUY if side == "buy" else OrderSide.SELL
        ot = OT.MARKET if order_type == "market" else OT.LIMIT

        try:
            order = await exchange.place_order(
                symbol, os, ot, amount, price if price > 0 else None)
            fill_price = order.average or price or profile.last_price
            elapsed = (time.monotonic() - start) * 1000
            actual_slip = 0
            if profile.last_price > 0 and fill_price > 0:
                actual_slip = abs(fill_price - profile.last_price) / profile.last_price * 100

            return ExecutionReport(
                success=True, symbol=symbol, side=side,
                requested_amount=amount, executed_amount=order.filled or amount,
                chunks_planned=1, chunks_executed=1,
                avg_fill_price=fill_price,
                estimated_slippage_pct=0, actual_slippage_pct=actual_slip,
                total_quote=fill_price * (order.filled or amount),
                execution_time_ms=elapsed, strategy="single",
                fills=[{"price": fill_price, "amount": order.filled or amount}])
        except Exception as exc:  # R28-OK: error surfaced via ExecutionReport(success=False)
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionReport(
                success=False, symbol=symbol, side=side,
                requested_amount=amount, executed_amount=0,
                chunks_planned=1, chunks_executed=0,
                avg_fill_price=0, estimated_slippage_pct=0,
                actual_slippage_pct=0, total_quote=0,
                execution_time_ms=elapsed, strategy="single",
                reason=str(exc))

    async def _execute_iceberg(self, symbol: str, side: str,
                                plan: ChunkPlan, price: float,
                                order_type: str, profile: MarketProfile,
                                start: float, ex=None) -> ExecutionReport:

        # sadp: R28 R29  # volume-gated order: fail-loudly(R28) idempotent(R29)
        """Execute as volume-aware iceberg: adaptive chunks with delays."""
        from ..exchange.base import OrderSide, OrderType as OT
        exchange = ex or self._exchange
        os = OrderSide.BUY if side == "buy" else OrderSide.SELL
        ot = OT.MARKET if order_type == "market" else OT.LIMIT

        fills = []
        total_filled = 0.0
        total_quote = 0.0
        chunks_done = 0

        logger.info("VolumeGuard ICEBERG: %s %s — %d chunks, %.0fms delay, "
                    "est slippage %.2f%%",
                    side.upper(), symbol, len(plan.chunks),
                    plan.chunk_delay_ms, plan.estimated_slippage_pct)

        for i, chunk_amount in enumerate(plan.chunks):
            try:
                order = await exchange.place_order(
                    symbol, os, ot, chunk_amount,
                    price if price > 0 else None)

                fill_price = order.average or price or profile.last_price
                filled = order.filled or chunk_amount
                total_filled += filled
                total_quote += fill_price * filled
                chunks_done += 1

                fills.append({
                    "chunk": i + 1,
                    "price": fill_price,
                    "amount": filled,
                })

                logger.debug("  Chunk %d/%d: %.8f @ $%.8f",
                            i + 1, len(plan.chunks), filled, fill_price)

            except Exception as exc:
                logger.warning("  Chunk %d/%d FAILED: %s", i + 1, len(plan.chunks), exc)
                fills.append({
                    "chunk": i + 1, "price": 0, "amount": 0,
                    "error": str(exc)})

            # Inter-chunk delay (skip after last chunk)
            if i < len(plan.chunks) - 1:
                # Re-check market between chunks for adaptive timing
                if i > 0 and i % 5 == 0:
                    try:
                        # Refresh profile every 5 chunks
                        self._profile_cache.pop(symbol, None)
                        fresh = await self._get_market_profile(symbol)
                        # Abort if market conditions deteriorated
                        if fresh.spread_pct > self.config.max_slippage_pct * 2:
                            logger.warning("VolumeGuard: Spread widened to %.2f%%, "
                                         "aborting remaining chunks", fresh.spread_pct)
                            break
                    except Exception:  # R28-OK: volume probe best-effort fallback
                        pass

                await asyncio.sleep(plan.chunk_delay_ms / 1000)

        elapsed = (time.monotonic() - start) * 1000
        avg_price = total_quote / total_filled if total_filled > 0 else 0
        actual_slip = 0
        if profile.last_price > 0 and avg_price > 0:
            actual_slip = abs(avg_price - profile.last_price) / profile.last_price * 100

        return ExecutionReport(
            success=total_filled > 0,
            symbol=symbol, side=side,
            requested_amount=plan.original_amount,
            executed_amount=total_filled,
            chunks_planned=len(plan.chunks),
            chunks_executed=chunks_done,
            avg_fill_price=avg_price,
            estimated_slippage_pct=plan.estimated_slippage_pct,
            actual_slippage_pct=actual_slip,
            total_quote=total_quote,
            execution_time_ms=elapsed,
            strategy=f"iceberg_{len(plan.chunks)}",
            reason=plan.reason,
            fills=fills)

    # ─── Hourly Participation Tracking ─────────────────────────────

    def _track_hourly_usage(self, symbol: str, quote_amount: float):
        """Track how much volume we've consumed this hour."""
        now = time.time()
        current_hour = int(now // 3600)
        last_hour = int(self._last_hour_reset // 3600) if self._last_hour_reset else 0

        if current_hour != last_hour:
            self._hourly_usage.clear()
            self._last_hour_reset = now

        self._hourly_usage[symbol] = self._hourly_usage.get(symbol, 0) + abs(quote_amount)

    def _get_hourly_budget(self, symbol: str, hourly_volume: float) -> float:
        """Get remaining hourly participation budget."""
        max_hourly = hourly_volume * self.config.max_hourly_participation_pct
        used = self._hourly_usage.get(symbol, 0)
        return max(0, max_hourly - used)

    # ─── Reporting & Status ────────────────────────────────────────

    def get_status(self) -> dict:
        """Return current guard status and statistics."""
        recent = [r for r in self._execution_history
                  if time.time() - r.execution_time_ms / 1000 < 3600]
        icebergs = [r for r in recent if r.strategy.startswith("iceberg")]

        return {
            "enabled": self.config.enabled,
            "cached_profiles": len(self._profile_cache),
            "hourly_usage": dict(self._hourly_usage),
            "total_executions": len(self._execution_history),
            "recent_executions": len(recent),
            "iceberg_executions": len(icebergs),
            "config": {
                "max_single_pct": self.config.max_single_order_volume_pct * 100,
                "max_hourly_pct": self.config.max_hourly_participation_pct * 100,
                "max_book_depth_pct": self.config.max_book_depth_pct * 100,
                "max_slippage_pct": self.config.max_slippage_pct,
            },
        }

    def get_market_profile(self, symbol: str) -> Optional[dict]:
        """Get cached market profile as dict (for UI display)."""
        p = self._profile_cache.get(symbol)
        if not p:
            return None
        return {
            "symbol": p.symbol,
            "last_price": p.last_price,
            "spread_pct": round(p.spread_pct, 4),
            "volume_24h": round(p.volume_24h_quote, 2),
            "volume_hourly": round(p.volume_hourly_est, 2),
            "avg_trade_size": round(p.avg_trade_size_est, 2),
            "bid_depth": round(p.bid_depth_quote, 2),
            "ask_depth": round(p.ask_depth_quote, 2),
            "safe_order_quote": round(p.safe_single_order_quote, 2),
            "safe_order_base": round(p.safe_single_order_base, 8),
            "hourly_budget": round(p.hourly_budget_remaining, 2),
            "is_tradeable": p.is_tradeable,
            "thin_market": p.thin_market,
            "wide_spread": p.wide_spread,
            "tier": self._classify_volume_tier(p.volume_24h_quote),
            "age_seconds": round(time.time() - p.timestamp, 1),
        }

    def get_execution_history(self, limit: int = 50) -> list[dict]:
        """Get recent execution reports as dicts."""
        return [
            {
                "symbol": r.symbol,
                "side": r.side,
                "requested": r.requested_amount,
                "executed": r.executed_amount,
                "chunks": f"{r.chunks_executed}/{r.chunks_planned}",
                "avg_price": round(r.avg_fill_price, 8),
                "slippage": f"{r.actual_slippage_pct:.3f}%",
                "strategy": r.strategy,
                "time_ms": round(r.execution_time_ms, 1),
            }
            for r in self._execution_history[-limit:]
        ]


# ───────────────────────────────────────────────────────────────────
# Singleton
# ───────────────────────────────────────────────────────────────────

_instance: Optional[VolumeGuard] = None


def get_volume_guard(exchange=None, config: VolumeGuardConfig = None) -> VolumeGuard:
    """Get or create the global VolumeGuard instance."""
    global _instance
    if _instance is None:
        _instance = VolumeGuard(exchange, config)
    elif exchange:
        _instance.set_exchange(exchange)
    return _instance
