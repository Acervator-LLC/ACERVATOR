# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Order-execution strategies behind ``SmartOrderEngine``.

``execute`` dispatches on ``ExecutionStrategy`` to ``_execute_market``,
``_execute_iceberg``, ``_execute_twap`` or ``_execute_limit_timeout``, and
``ADAPTIVE`` first asks ``_choose_strategy``. Nothing under ``src/`` imports
``SmartOrderEngine``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("acervator.execution")


def _extract_base_asset(symbol: str) -> str:
    """Return the base asset of ``symbol``: ``ETH/USDT`` and ``ETH-USD`` give ``ETH``.

    An empty ``symbol`` returns an empty string, and ``SmartOrderEngine.execute``
    then queries the registry with that empty asset.
    """
    if not symbol:
        return ""
    for sep in ("/", "-"):
        if sep in symbol:
            return symbol.split(sep, 1)[0].strip().upper()
    return symbol.strip().upper()


class ExecutionStrategy(Enum):
    MARKET = "market"
    ICEBERG = "iceberg"
    TWAP = "twap"
    LIMIT_TIMEOUT = "limit_timeout"
    ADAPTIVE = "adaptive"


@dataclass
class ExecutionConfig:
    """Tuning for one ``ExecutionStrategy``: slice counts, delays, thresholds."""

    strategy: ExecutionStrategy = ExecutionStrategy.MARKET
    iceberg_slices: int = 5
    iceberg_delay_ms: int = 500
    twap_duration_seconds: int = 60
    twap_slices: int = 10
    limit_offset_pct: float = 0.1
    limit_timeout_seconds: int = 30
    # Order value as a percent of 24h volume; _choose_strategy compares against it.
    large_order_pct: float = 5.0


@dataclass
class ExecutionResult:
    """What ``SmartOrderEngine.execute`` returns to its caller."""

    success: bool
    strategy_used: str
    total_quantity: float
    avg_fill_price: float
    # _execute_market signs a sell; every other strategy returns abs().
    slippage_pct: float
    total_cost: float
    fills: list[dict] = field(default_factory=list)
    elapsed_ms: float = 0
    error: str = ""


class SmartOrderEngine:
    """``execute`` places one order through a single ``ExecutionStrategy``."""

    def __init__(self, config: ExecutionConfig = None):
        self.config = config or ExecutionConfig()
        self._active_executions: dict[str, dict] = {}

    async def execute(
        self,
        exchange,
        symbol: str,
        side: str,
        quantity: float,
        config: ExecutionConfig = None,
        *,
        bot_id: Optional[str] = None,
        total_holdings: Optional[float] = None,
    ) -> ExecutionResult:
        """Trade ``quantity`` of ``symbol`` on ``exchange`` using ``config.strategy``.

        A sell that supplies both ``bot_id`` and ``total_holdings`` is refused
        with ``strategy_used="rejected_by_reservation"`` when ``quantity``
        exceeds ``effective_available``; omitting either one skips the check.
        """
        cfg = config or self.config
        start = time.time()

        if bot_id is not None and total_holdings is not None and side.lower() == "sell":
            try:
                from .capital_reservation import get_registry

                registry = get_registry()
                base_asset = _extract_base_asset(symbol)
                effective = registry.effective_available(
                    asset=base_asset,
                    bot_id=bot_id,
                    total_holdings=total_holdings,
                )
                if quantity > effective + 1e-12:
                    msg = (
                        f"sell of {quantity:.10g} {base_asset} rejected by "
                        f"CapitalReservationRegistry: effective available "
                        f"for {bot_id!r} is {effective:.10g} (other bots "
                        f"hold reservations on this asset). "
                        f"Either release the conflicting reservation or "
                        f"reduce the sell quantity."
                    )
                    logger.warning("smart_orders.execute: %s", msg)
                    return ExecutionResult(
                        success=False,
                        strategy_used="rejected_by_reservation",
                        total_quantity=0,
                        avg_fill_price=0,
                        slippage_pct=0,
                        total_cost=0,
                        elapsed_ms=(time.time() - start) * 1000,
                        error=msg,
                    )
            except Exception as exc:
                logger.error(
                    "smart_orders.execute: registry pre-flight raised "
                    "%s — falling through to exchange placement. "
                    "Investigate immediately.",
                    exc,
                )
        elif (bot_id is None or total_holdings is None) and side.lower() == "sell":
            logger.debug(
                "smart_orders.execute: sell with bot_id=%r "
                "total_holdings=%r — registry pre-flight skipped "
                "(opt-in path).",
                bot_id,
                total_holdings,
            )

        try:
            ticker = await exchange.fetch_ticker(symbol)
            ref_price = ticker.get("last", 0) or ticker.get("close", 0)
        except Exception:
            # A zero ref_price makes every reported slippage_pct zero.
            ref_price = 0

        strategy = cfg.strategy
        if strategy == ExecutionStrategy.ADAPTIVE:
            strategy = await self._choose_strategy(exchange, symbol, quantity, cfg)

        try:
            if strategy == ExecutionStrategy.ICEBERG:
                result = await self._execute_iceberg(
                    exchange, symbol, side, quantity, cfg, ref_price
                )
            elif strategy == ExecutionStrategy.TWAP:
                result = await self._execute_twap(
                    exchange, symbol, side, quantity, cfg, ref_price
                )
            elif strategy == ExecutionStrategy.LIMIT_TIMEOUT:
                result = await self._execute_limit_timeout(
                    exchange, symbol, side, quantity, cfg, ref_price
                )
            else:
                result = await self._execute_market(
                    exchange, symbol, side, quantity, ref_price
                )

            result.elapsed_ms = (time.time() - start) * 1000
            result.strategy_used = strategy.value
            return result

        except Exception as exc:
            logger.error("Smart order execution failed: %s", exc)
            return ExecutionResult(
                success=False,
                strategy_used=strategy.value,
                total_quantity=quantity,
                avg_fill_price=0,
                slippage_pct=0,
                total_cost=0,
                elapsed_ms=(time.time() - start) * 1000,
                error=str(exc),
            )

    async def _execute_market(
        self, exchange, symbol: str, side: str, quantity: float, ref_price: float
    ) -> ExecutionResult:
        """Place one market order for the whole ``quantity``.

        A buy reports ``slippage_pct`` as an absolute value; a sell reports it
        negated, so a fill under ``ref_price`` comes back positive.
        """
        order = await exchange.create_order(symbol, "market", side, quantity)
        fill_price = order.get("average", ref_price) or ref_price
        cost = order.get("cost", fill_price * quantity)
        slippage = ((fill_price - ref_price) / ref_price * 100) if ref_price else 0
        if side == "buy":
            slippage = abs(slippage)
        else:
            slippage = -slippage

        return ExecutionResult(
            success=True,
            strategy_used="market",
            total_quantity=quantity,
            avg_fill_price=fill_price,
            slippage_pct=round(slippage, 4),
            total_cost=cost,
            fills=[{"price": fill_price, "quantity": quantity, "type": "market"}],
        )

    async def _execute_iceberg(
        self,
        exchange,
        symbol: str,
        side: str,
        quantity: float,
        cfg: ExecutionConfig,
        ref_price: float,
    ) -> ExecutionResult:
        """Place ``cfg.iceberg_slices`` equal market orders with a delay between.

        A slice that raises is logged and left out of ``total_filled``.
        """
        slices = cfg.iceberg_slices
        chunk_size = quantity / slices
        delay = cfg.iceberg_delay_ms / 1000

        fills = []
        total_cost = 0
        total_filled = 0

        for i in range(slices):
            try:
                order = await exchange.create_order(symbol, "market", side, chunk_size)
                fill_price = order.get("average", ref_price) or ref_price
                cost = order.get("cost", fill_price * chunk_size)
                fills.append(
                    {
                        "price": fill_price,
                        "quantity": chunk_size,
                        "type": "iceberg",
                        "slice": i + 1,
                    }
                )
                total_cost += cost
                total_filled += chunk_size
                logger.debug(
                    "Iceberg %d/%d: %.8f @ $%.2f", i + 1, slices, chunk_size, fill_price
                )
            except Exception as e:
                logger.warning("Iceberg slice %d failed: %s", i + 1, e)

            if i < slices - 1:
                await asyncio.sleep(delay)

        avg_price = total_cost / total_filled if total_filled else 0
        slippage = ((avg_price - ref_price) / ref_price * 100) if ref_price else 0

        return ExecutionResult(
            success=total_filled > 0,
            strategy_used="iceberg",
            total_quantity=total_filled,
            avg_fill_price=avg_price,
            slippage_pct=round(abs(slippage), 4),
            total_cost=total_cost,
            fills=fills,
        )

    async def _execute_twap(
        self,
        exchange,
        symbol: str,
        side: str,
        quantity: float,
        cfg: ExecutionConfig,
        ref_price: float,
    ) -> ExecutionResult:
        """Place ``cfg.twap_slices`` equal market orders across the TWAP window.

        An interval that raises is logged and left out of ``total_filled``.
        """
        slices = cfg.twap_slices
        interval = cfg.twap_duration_seconds / slices
        chunk_size = quantity / slices

        fills = []
        total_cost = 0
        total_filled = 0

        for i in range(slices):
            try:
                order = await exchange.create_order(symbol, "market", side, chunk_size)
                fill_price = order.get("average", ref_price) or ref_price
                cost = order.get("cost", fill_price * chunk_size)
                fills.append(
                    {
                        "price": fill_price,
                        "quantity": chunk_size,
                        "type": "twap",
                        "interval": i + 1,
                    }
                )
                total_cost += cost
                total_filled += chunk_size
            except Exception as e:
                logger.warning("TWAP interval %d failed: %s", i + 1, e)

            if i < slices - 1:
                await asyncio.sleep(interval)

        avg_price = total_cost / total_filled if total_filled else 0
        slippage = ((avg_price - ref_price) / ref_price * 100) if ref_price else 0

        return ExecutionResult(
            success=total_filled > 0,
            strategy_used="twap",
            total_quantity=total_filled,
            avg_fill_price=avg_price,
            slippage_pct=round(abs(slippage), 4),
            total_cost=total_cost,
            fills=fills,
        )

    async def _execute_limit_timeout(
        self,
        exchange,
        symbol: str,
        side: str,
        quantity: float,
        cfg: ExecutionConfig,
        ref_price: float,
    ) -> ExecutionResult:
        """Place one limit order, then market-order whatever is left unfilled.

        ``total_quantity`` always comes back as ``quantity``, since ``remaining``
        is defined as ``quantity`` minus ``filled``.
        """
        offset = cfg.limit_offset_pct / 100
        if side == "buy":
            limit_price = ref_price * (1 - offset)
        else:
            limit_price = ref_price * (1 + offset)

        try:
            order = await exchange.create_order(
                symbol, "limit", side, quantity, limit_price
            )
            order_id = order.get("id", "")

            filled = 0
            deadline = time.time() + cfg.limit_timeout_seconds
            while time.time() < deadline:
                await asyncio.sleep(2)
                try:
                    status = await exchange.fetch_order(order_id, symbol)
                    filled = status.get("filled", 0)
                    if status.get("status") in ("closed", "filled"):
                        break
                except Exception as exc:
                    logger.debug(
                        "fetch_order %s on %s raised %s: %s",
                        order_id,
                        symbol,
                        type(exc).__name__,
                        exc,
                    )

            remaining = quantity - filled
            fills = []
            total_cost = 0

            if filled > 0:
                avg = order.get("average", limit_price)
                fills.append({"price": avg, "quantity": filled, "type": "limit"})
                total_cost += avg * filled

            if remaining > 0.001 * quantity:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception as exc:
                    logger.debug(
                        "cancel_order %s on %s raised %s: %s",
                        order_id,
                        symbol,
                        type(exc).__name__,
                        exc,
                    )
                mkt = await exchange.create_order(symbol, "market", side, remaining)
                mkt_price = mkt.get("average", ref_price) or ref_price
                fills.append(
                    {
                        "price": mkt_price,
                        "quantity": remaining,
                        "type": "market_fallback",
                    }
                )
                total_cost += mkt_price * remaining

            total_filled = filled + remaining
            avg_price = total_cost / total_filled if total_filled else 0
            slippage = ((avg_price - ref_price) / ref_price * 100) if ref_price else 0

            return ExecutionResult(
                success=True,
                strategy_used="limit_timeout",
                total_quantity=total_filled,
                avg_fill_price=avg_price,
                slippage_pct=round(abs(slippage), 4),
                total_cost=total_cost,
                fills=fills,
            )

        except Exception as exc:
            logger.warning("Limit-timeout failed, falling back to market: %s", exc)
            return await self._execute_market(
                exchange, symbol, side, quantity, ref_price
            )

    async def _choose_strategy(
        self, exchange, symbol: str, quantity: float, cfg: ExecutionConfig
    ) -> ExecutionStrategy:
        """Return ``ICEBERG``, ``LIMIT_TIMEOUT`` or ``MARKET`` for this order.

        A ticker with no 24h volume, or one that raises, returns ``MARKET``.
        """
        try:
            ticker = await exchange.fetch_ticker(symbol)
            volume_24h = ticker.get("quoteVolume", 0) or ticker.get(
                "baseVolume", 0
            ) * ticker.get("last", 1)
            order_value = quantity * (ticker.get("last", 0) or 1)

            if volume_24h > 0:
                order_pct = (order_value / volume_24h) * 100
                if order_pct >= cfg.large_order_pct:
                    logger.info(
                        "Adaptive: order is %.2f%% of daily volume → ICEBERG", order_pct
                    )
                    return ExecutionStrategy.ICEBERG
                elif order_pct >= cfg.large_order_pct / 2:
                    logger.info(
                        "Adaptive: order is %.2f%% of daily volume → LIMIT_TIMEOUT",
                        order_pct,
                    )
                    return ExecutionStrategy.LIMIT_TIMEOUT

        except Exception as exc:
            logger.debug(
                "_choose_strategy %s raised %s: %s", symbol, type(exc).__name__, exc
            )

        return ExecutionStrategy.MARKET
