# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Volume-aware order chunking.

``VolumeGuard.execute`` profiles a symbol with ``_get_market_profile``, sizes a
safe order with ``_compute_safe_sizes``, then places it whole or spreads it over
``_execute_iceberg`` chunks. ``VolumeGuard.enabled`` returns False and
``BotContainer.guarded_place_order`` tests that property, leaving ``execute``
unreached on a live order. A False ``MarketProfile.is_tradeable`` does not
refuse the order; ``_execute_passthrough`` still places it.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.execution")


@dataclass
class VolumeGuardConfig:
    """Tunable parameters ``VolumeGuard`` reads.

    ``max_slippage_pct`` is tested only against ``MarketProfile.spread_pct`` in
    ``_execute_iceberg``, and ``max_hourly_participation_pct`` only sizes
    ``_get_hourly_budget``, which no execution path consults.
    """

    # Fraction of ``MarketProfile.volume_24h_quote`` allowed in one order.
    max_single_order_volume_pct: float = 0.001

    max_hourly_participation_pct: float = 0.02

    # Fraction of the thinner book side allowed in one order.
    max_book_depth_pct: float = 0.25

    max_slippage_pct: float = 1.0

    min_chunk_delay_ms: int = 200
    max_chunk_delay_ms: int = 5000

    # Fraction of the safe size that sets the chunk count, not the chunk size.
    chunk_headroom_pct: float = 0.7

    book_depth_levels: int = 20

    # Sets ``MarketProfile.low_volume``; ``is_tradeable`` needs only a non-zero volume.
    min_daily_volume_usd: float = 1000.0

    # ``execute`` passes through when False; the ``enabled`` property ignores it.
    enabled: bool = True

    profile_cache_ttl: float = 30.0


@dataclass
class MarketProfile:
    """One symbol's conditions, as ``_get_market_profile`` builds them.

    ``last_price``, ``bid``, ``ask`` and ``volume_24h_quote`` come from
    ``get_ticker`` and the depth fields sum ``get_orderbook``; every other field
    is derived here.
    """

    symbol: str
    timestamp: float

    last_price: float = 0
    bid: float = 0
    ask: float = 0
    spread_pct: float = 0  # (ask - bid) / mid * 100

    volume_24h_quote: float = 0
    volume_hourly_est: float = 0  # volume_24h_quote / 24
    avg_trade_size_est: float = 0  # volume_24h_quote / TRADES_PER_DAY_EST[tier]

    # Price times amount over ``book_depth_levels``, or a synthesized fallback.
    bid_depth_quote: float = 0
    ask_depth_quote: float = 0
    # Levels the venue returned, which can exceed ``book_depth_levels``.
    bid_depth_levels: int = 0
    ask_depth_levels: int = 0

    safe_single_order_quote: float = 0
    safe_single_order_base: float = 0
    hourly_budget_remaining: float = 0

    # False only when the ticker reports no volume or the profile raises.
    is_tradeable: bool = True
    # Set from book depth against ``volume_hourly_est``; no execution path reads it.
    thin_market: bool = False
    wide_spread: bool = False  # spread_pct > 0.5
    low_volume: bool = False


@dataclass
class ChunkPlan:
    """How ``_compute_chunk_plan`` splits one order.

    ``chunks`` are base-currency sizes and ``estimated_slippage_pct`` is the
    quote value over the opposite book side, capped at 10.
    """

    original_amount: float
    original_quote_value: float
    needs_chunking: bool
    chunks: list[float] = field(default_factory=list)
    chunk_delay_ms: int = 500
    estimated_slippage_pct: float = 0
    # One of within_safe_limits, above_safe, very_large, extreme_size.
    reason: str = ""
    market_profile: Optional[MarketProfile] = None


@dataclass
class ExecutionReport:
    """What ``VolumeGuard.execute`` returns for one trade.

    ``executed_amount`` and ``avg_fill_price`` fall back to the requested size
    and the tick price when the venue leaves ``order.filled`` or
    ``order.average`` empty.
    """

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
    # Elapsed wall time for the call, not a point in time.
    execution_time_ms: float
    strategy: str  # "passthrough", "single", "error", or "iceberg_N"
    reason: str = ""
    fills: list[dict] = field(default_factory=list)
    completed_at: float = field(default_factory=time.time)


class VolumeGuard:
    """Volume-aware order chunking.

    ``execute`` profiles the market and places an order whole or in chunks, and
    ``set_exchange`` supplies the connector when the constructor had none.
    """

    # Divisor ``_get_market_profile`` uses for ``avg_trade_size_est``, keyed by
    # ``_classify_volume_tier``.
    TRADES_PER_DAY_EST = {
        "mega": 200_000,
        "large": 50_000,
        "mid": 15_000,
        "small": 3_000,
        "micro": 500,
    }

    def __init__(self, exchange=None, config: VolumeGuardConfig = None):
        self._exchange = exchange
        self.config = config or VolumeGuardConfig()
        self._profile_cache: dict[str, MarketProfile] = {}
        self._hourly_usage: dict[str, float] = {}
        self._last_hour_reset: float = 0
        self._execution_history: list[ExecutionReport] = []
        self._max_history = 500

    def set_exchange(self, exchange):
        """Set or update the exchange connector."""
        self._exchange = exchange

    @property
    def enabled(self) -> bool:
        """Return False on every call, whatever ``config.enabled`` holds.

        ``BotContainer.guarded_place_order`` reads this property and takes the
        direct ``exchange.place_order`` path while it is False.
        """
        return False

    @enabled.setter
    def enabled(self, val: bool):
        """Store ``val`` on ``config.enabled``, which the getter above ignores."""
        self.config.enabled = val

    async def execute(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float = 0,
        order_type: str = "market",
        exchange=None,
    ) -> ExecutionReport:
        """Place ``amount`` of ``symbol`` under the ``VolumeGuardConfig`` limits.

        A False ``config.enabled`` or a non-tradeable ``MarketProfile`` goes to
        ``_execute_passthrough``, a missing connector returns strategy ``error``,
        and otherwise ``_compute_chunk_plan`` picks ``_execute_single`` or
        ``_execute_iceberg``.
        """
        start = time.monotonic()
        ex = exchange or self._exchange

        if not self.config.enabled:
            return await self._execute_passthrough(
                symbol, side, amount, price, order_type, start, ex
            )

        if not ex:
            return ExecutionReport(
                success=False,
                symbol=symbol,
                side=side,
                requested_amount=amount,
                executed_amount=0,
                chunks_planned=0,
                chunks_executed=0,
                avg_fill_price=0,
                estimated_slippage_pct=0,
                actual_slippage_pct=0,
                total_quote=0,
                execution_time_ms=0,
                strategy="error",
                reason="No exchange connector set",
            )

        profile = await self._get_market_profile(symbol, ex)

        if not profile.is_tradeable:
            logger.warning(
                "VolumeGuard: %s not tradeable — %s",
                symbol,
                "low volume" if profile.low_volume else "no data",
            )
            return await self._execute_passthrough(
                symbol, side, amount, price, order_type, start, ex
            )

        ref_price = price if price > 0 else profile.last_price
        plan = self._compute_chunk_plan(amount, ref_price, side, profile)

        logger.info(
            "VolumeGuard [%s %s %s]: amount=%.8f, quote=$%.2f, "
            "safe=$%.2f, chunks=%d, reason=%s",
            side.upper(),
            symbol,
            "CHUNK" if plan.needs_chunking else "PASS",
            amount,
            plan.original_quote_value,
            profile.safe_single_order_quote,
            len(plan.chunks),
            plan.reason,
        )

        if not plan.needs_chunking:
            report = await self._execute_single(
                symbol, side, amount, price, order_type, profile, start, ex
            )
        else:
            report = await self._execute_iceberg(
                symbol, side, plan, price, order_type, profile, start, ex
            )

        self._track_hourly_usage(symbol, report.total_quote)

        self._execution_history.append(report)
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history :]

        return report

    async def _get_market_profile(self, symbol: str, ex=None) -> MarketProfile:
        """Return the cached ``MarketProfile`` for ``symbol``, or build a fresh one.

        A profile older than ``config.profile_cache_ttl`` is rebuilt from
        ``get_ticker`` and ``get_orderbook``, and any failure there leaves
        ``is_tradeable`` False.
        """
        now = time.time()
        exchange = ex or self._exchange

        cached = self._profile_cache.get(symbol)
        if cached and (now - cached.timestamp) < self.config.profile_cache_ttl:
            cached.hourly_budget_remaining = self._get_hourly_budget(
                symbol, cached.volume_hourly_est
            )
            return cached

        profile = MarketProfile(symbol=symbol, timestamp=now)

        try:
            ticker = await exchange.get_ticker(symbol)
            profile.last_price = ticker.last
            profile.bid = ticker.bid
            profile.ask = ticker.ask
            profile.volume_24h_quote = ticker.volume_24h

            mid = (
                (ticker.bid + ticker.ask) / 2
                if (ticker.bid and ticker.ask)
                else ticker.last
            )
            if mid > 0 and ticker.bid > 0 and ticker.ask > 0:
                profile.spread_pct = (ticker.ask - ticker.bid) / mid * 100
            profile.wide_spread = profile.spread_pct > 0.5

            profile.volume_hourly_est = profile.volume_24h_quote / 24
            profile.low_volume = (
                profile.volume_24h_quote < self.config.min_daily_volume_usd
            )
            profile.is_tradeable = (
                not profile.low_volume or profile.volume_24h_quote > 0
            )

            tier = self._classify_volume_tier(profile.volume_24h_quote)
            est_trades = self.TRADES_PER_DAY_EST.get(tier, 5000)
            profile.avg_trade_size_est = profile.volume_24h_quote / est_trades

            try:
                book = await exchange.get_orderbook(
                    symbol, self.config.book_depth_levels
                )
                profile.bid_depth_quote = sum(
                    p * a for p, a in book.bids[: self.config.book_depth_levels]
                )
                profile.ask_depth_quote = sum(
                    p * a for p, a in book.asks[: self.config.book_depth_levels]
                )
                profile.bid_depth_levels = len(book.bids)
                profile.ask_depth_levels = len(book.asks)
            except Exception:
                # A synthesized depth, not a venue value.
                profile.bid_depth_quote = profile.volume_hourly_est * 0.1
                profile.ask_depth_quote = profile.volume_hourly_est * 0.1

            book_depth = min(profile.bid_depth_quote, profile.ask_depth_quote)
            profile.thin_market = book_depth < profile.volume_hourly_est * 0.02

            self._compute_safe_sizes(profile)

        except Exception as exc:
            logger.warning("VolumeGuard: Failed to profile %s: %s", symbol, exc)
            profile.is_tradeable = False

        self._profile_cache[symbol] = profile
        return profile

    def _compute_safe_sizes(self, profile: MarketProfile):
        """Set the safe order sizes and the hourly budget on ``profile``.

        ``safe_single_order_quote`` is the smallest of the volume, book-depth
        and average-trade limits, floored at 0.01 quote.
        """
        cfg = self.config

        vol_limit_quote = profile.volume_24h_quote * cfg.max_single_order_volume_pct

        if profile.bid_depth_quote > 0 and profile.ask_depth_quote > 0:
            book_limit_quote = (
                min(profile.bid_depth_quote, profile.ask_depth_quote)
                * cfg.max_book_depth_pct
            )
        else:
            book_limit_quote = vol_limit_quote

        avg_limit_quote = profile.avg_trade_size_est * 10

        safe_quote = max(
            min(vol_limit_quote, book_limit_quote, avg_limit_quote),
            0.01,
        )

        profile.safe_single_order_quote = safe_quote
        if profile.last_price > 0:
            profile.safe_single_order_base = safe_quote / profile.last_price
        else:
            profile.safe_single_order_base = 0

        profile.hourly_budget_remaining = self._get_hourly_budget(
            profile.symbol, profile.volume_hourly_est
        )

    def _classify_volume_tier(self, daily_volume_quote: float) -> str:
        """Return the ``TRADES_PER_DAY_EST`` key for ``daily_volume_quote``."""
        if daily_volume_quote >= 100_000_000:
            return "mega"
        if daily_volume_quote >= 10_000_000:
            return "large"
        if daily_volume_quote >= 1_000_000:
            return "mid"
        if daily_volume_quote >= 100_000:
            return "small"
        return "micro"

    def _compute_chunk_plan(
        self, amount: float, ref_price: float, side: str, profile: MarketProfile
    ) -> ChunkPlan:
        """Decide whether ``amount`` needs splitting against ``profile``.

        Returns a ``ChunkPlan`` of at most 50 equal chunks whose
        ``chunk_delay_ms`` shortens as ``volume_hourly_est`` rises.
        """
        quote_value = amount * ref_price if ref_price > 0 else 0
        plan = ChunkPlan(
            original_amount=amount,
            original_quote_value=quote_value,
            needs_chunking=False,
            market_profile=profile,
        )

        safe_quote = profile.safe_single_order_quote
        safe_base = profile.safe_single_order_base

        if safe_base <= 0 or amount <= safe_base:
            plan.needs_chunking = False
            plan.chunks = [amount]
            plan.reason = "within_safe_limits"
            return plan

        plan.needs_chunking = True

        chunk_base = safe_base * self.config.chunk_headroom_pct
        if chunk_base <= 0:
            chunk_base = amount
            plan.needs_chunking = False

        n_chunks = math.ceil(amount / chunk_base)
        n_chunks = min(n_chunks, 50)
        chunk_base = amount / n_chunks

        plan.chunks = [chunk_base] * n_chunks
        total_planned = sum(plan.chunks)
        if total_planned != amount:
            plan.chunks[-1] += amount - total_planned

        if profile.volume_hourly_est > 0:
            volume_factor = min(profile.volume_hourly_est / 100_000, 10)
            delay = int(self.config.max_chunk_delay_ms / max(volume_factor, 0.5))
            delay = max(
                self.config.min_chunk_delay_ms,
                min(delay, self.config.max_chunk_delay_ms),
            )
        else:
            delay = self.config.max_chunk_delay_ms
        plan.chunk_delay_ms = delay

        relevant_depth = (
            profile.ask_depth_quote if side == "buy" else profile.bid_depth_quote
        )
        if relevant_depth > 0:
            plan.estimated_slippage_pct = (quote_value / relevant_depth) * 100
            plan.estimated_slippage_pct = min(plan.estimated_slippage_pct, 10)
        else:
            plan.estimated_slippage_pct = 0

        ratio = quote_value / safe_quote if safe_quote > 0 else 0
        if ratio > 20:
            plan.reason = f"extreme_size ({ratio:.0f}× safe limit)"
        elif ratio > 5:
            plan.reason = f"very_large ({ratio:.1f}× safe limit)"
        else:
            plan.reason = f"above_safe ({ratio:.1f}× safe limit)"

        return plan

    async def _execute_passthrough(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        order_type: str,
        start: float,
        ex=None,
    ) -> ExecutionReport:
        """Place all of ``amount`` through ``exchange.place_order`` with no sizing.

        ``executed_amount`` falls back to ``amount`` and ``avg_fill_price`` to
        ``price`` when the venue leaves ``order.filled`` or ``order.average`` empty.
        """
        from ..exchange.base import OrderSide, OrderType as OT

        exchange = ex or self._exchange
        os = OrderSide.BUY if side == "buy" else OrderSide.SELL
        ot = OT.MARKET if order_type == "market" else OT.LIMIT

        try:
            order = await exchange.place_order(
                symbol, os, ot, amount, price if price > 0 else None
            )
            fill_price = order.average or price or 0
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionReport(
                success=True,
                symbol=symbol,
                side=side,
                requested_amount=amount,
                executed_amount=order.filled or amount,
                chunks_planned=1,
                chunks_executed=1,
                avg_fill_price=fill_price,
                estimated_slippage_pct=0,
                actual_slippage_pct=0,
                total_quote=fill_price * (order.filled or amount),
                execution_time_ms=elapsed,
                strategy="passthrough",
                fills=[{"price": fill_price, "amount": order.filled or amount}],
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionReport(
                success=False,
                symbol=symbol,
                side=side,
                requested_amount=amount,
                executed_amount=0,
                chunks_planned=1,
                chunks_executed=0,
                avg_fill_price=0,
                estimated_slippage_pct=0,
                actual_slippage_pct=0,
                total_quote=0,
                execution_time_ms=elapsed,
                strategy="passthrough",
                reason=str(exc),
            )

    async def _execute_single(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        order_type: str,
        profile: MarketProfile,
        start: float,
        ex=None,
    ) -> ExecutionReport:
        """Place ``amount`` in one order and score it against ``profile``.

        ``actual_slippage_pct`` is the fill price away from
        ``profile.last_price``, and stays 0 while either is not positive.
        """
        from ..exchange.base import OrderSide, OrderType as OT

        exchange = ex or self._exchange
        os = OrderSide.BUY if side == "buy" else OrderSide.SELL
        ot = OT.MARKET if order_type == "market" else OT.LIMIT

        try:
            order = await exchange.place_order(
                symbol, os, ot, amount, price if price > 0 else None
            )
            fill_price = order.average or price or profile.last_price
            elapsed = (time.monotonic() - start) * 1000
            actual_slip = 0
            if profile.last_price > 0 and fill_price > 0:
                actual_slip = (
                    abs(fill_price - profile.last_price) / profile.last_price * 100
                )

            return ExecutionReport(
                success=True,
                symbol=symbol,
                side=side,
                requested_amount=amount,
                executed_amount=order.filled or amount,
                chunks_planned=1,
                chunks_executed=1,
                avg_fill_price=fill_price,
                estimated_slippage_pct=0,
                actual_slippage_pct=actual_slip,
                total_quote=fill_price * (order.filled or amount),
                execution_time_ms=elapsed,
                strategy="single",
                fills=[{"price": fill_price, "amount": order.filled or amount}],
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionReport(
                success=False,
                symbol=symbol,
                side=side,
                requested_amount=amount,
                executed_amount=0,
                chunks_planned=1,
                chunks_executed=0,
                avg_fill_price=0,
                estimated_slippage_pct=0,
                actual_slippage_pct=0,
                total_quote=0,
                execution_time_ms=elapsed,
                strategy="single",
                reason=str(exc),
            )

    async def _execute_iceberg(
        self,
        symbol: str,
        side: str,
        plan: ChunkPlan,
        price: float,
        order_type: str,
        profile: MarketProfile,
        start: float,
        ex=None,
    ) -> ExecutionReport:
        """Place every entry of ``plan.chunks``, sleeping ``plan.chunk_delay_ms``.

        Every fifth chunk rebuilds the profile and abandons the rest once
        ``spread_pct`` passes twice ``config.max_slippage_pct``.
        """
        from ..exchange.base import OrderSide, OrderType as OT

        exchange = ex or self._exchange
        os = OrderSide.BUY if side == "buy" else OrderSide.SELL
        ot = OT.MARKET if order_type == "market" else OT.LIMIT

        fills = []
        total_filled = 0.0
        total_quote = 0.0
        chunks_done = 0

        logger.info(
            "VolumeGuard ICEBERG: %s %s — %d chunks, %.0fms delay, "
            "est slippage %.2f%%",
            side.upper(),
            symbol,
            len(plan.chunks),
            plan.chunk_delay_ms,
            plan.estimated_slippage_pct,
        )

        for i, chunk_amount in enumerate(plan.chunks):
            try:
                order = await exchange.place_order(
                    symbol, os, ot, chunk_amount, price if price > 0 else None
                )

                fill_price = order.average or price or profile.last_price
                filled = order.filled or chunk_amount
                total_filled += filled
                total_quote += fill_price * filled
                chunks_done += 1

                fills.append(
                    {
                        "chunk": i + 1,
                        "price": fill_price,
                        "amount": filled,
                    }
                )

                logger.debug(
                    "  Chunk %d/%d: %.8f @ $%.8f",
                    i + 1,
                    len(plan.chunks),
                    filled,
                    fill_price,
                )

            except Exception as exc:
                logger.warning("  Chunk %d/%d FAILED: %s", i + 1, len(plan.chunks), exc)
                fills.append(
                    {"chunk": i + 1, "price": 0, "amount": 0, "error": str(exc)}
                )

            if i < len(plan.chunks) - 1:
                if i > 0 and i % 5 == 0:
                    try:
                        self._profile_cache.pop(symbol, None)
                        fresh = await self._get_market_profile(symbol)
                        if fresh.spread_pct > self.config.max_slippage_pct * 2:
                            logger.warning(
                                "VolumeGuard: Spread widened to %.2f%%, "
                                "aborting remaining chunks",
                                fresh.spread_pct,
                            )
                            break
                    except Exception as exc:
                        logger.warning(
                            "VolumeGuard: %s profile refresh failed between "
                            "chunks; the remaining chunks are unchecked: %s",
                            symbol,
                            exc,
                        )

                await asyncio.sleep(plan.chunk_delay_ms / 1000)

        elapsed = (time.monotonic() - start) * 1000
        avg_price = total_quote / total_filled if total_filled > 0 else 0
        actual_slip = 0
        if profile.last_price > 0 and avg_price > 0:
            actual_slip = abs(avg_price - profile.last_price) / profile.last_price * 100

        return ExecutionReport(
            success=total_filled > 0,
            symbol=symbol,
            side=side,
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
            fills=fills,
        )

    def _track_hourly_usage(self, symbol: str, quote_amount: float):
        """Add ``quote_amount`` to ``_hourly_usage`` for ``symbol``.

        The whole map is cleared the first time ``_track_hourly_usage`` runs in
        a new clock hour.
        """
        now = time.time()
        current_hour = int(now // 3600)
        last_hour = int(self._last_hour_reset // 3600) if self._last_hour_reset else 0

        if current_hour != last_hour:
            self._hourly_usage.clear()
            self._last_hour_reset = now

        self._hourly_usage[symbol] = self._hourly_usage.get(symbol, 0) + abs(
            quote_amount
        )

    def _get_hourly_budget(self, symbol: str, hourly_volume: float) -> float:
        """Return ``hourly_volume`` scaled by ``max_hourly_participation_pct``.

        The ``_hourly_usage`` already booked for ``symbol`` is subtracted, and
        the result never falls below zero.
        """
        max_hourly = hourly_volume * self.config.max_hourly_participation_pct
        used = self._hourly_usage.get(symbol, 0)
        return max(0, max_hourly - used)

    def get_status(self) -> dict:
        """Return the config, the cache size and the ``_execution_history`` counts.

        ``recent_executions`` and ``iceberg_executions`` count only reports
        whose ``completed_at`` is inside the last hour.
        """
        recent = [
            r for r in self._execution_history if time.time() - r.completed_at < 3600
        ]
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
        """Return the cached ``MarketProfile`` for ``symbol`` as a dict, or None."""
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
        """Return the last ``limit`` ``ExecutionReport`` entries as dicts."""
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


_instance: Optional[VolumeGuard] = None


def get_volume_guard(exchange=None, config: VolumeGuardConfig = None) -> VolumeGuard:
    """Return the process-wide ``VolumeGuard``, building it on the first call.

    ``config`` is read only on that first call; a later ``exchange`` reaches the
    existing instance through ``set_exchange``.
    """
    global _instance
    if _instance is None:
        _instance = VolumeGuard(exchange, config)
    elif exchange:
        _instance.set_exchange(exchange)
    return _instance
