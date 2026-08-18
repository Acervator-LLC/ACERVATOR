"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
smart_orders.py — Intelligent order execution strategies.

Provides execution wrappers that reduce slippage and improve fill quality:
- Iceberg: Split large orders into smaller visible chunks
- TWAP: Time-Weighted Average Price across a time window
- Limit-with-timeout: Place limit order, convert to market if unfilled
- Adaptive: Choose strategy based on order size vs. book depth
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
    """Extract the base asset from a trading-pair symbol.

    Supports the two common formats Coinbase / CCXT emit:
      "ETH/USDT"  -> "ETH"   (CCXT canonical, slash-separated)
      "ETH-USD"   -> "ETH"   (Coinbase product-id, dash-separated)
      "BTC"       -> "BTC"   (fallback — already a base asset)

    Empty/None input returns empty string (caller's pre-flight will
    treat that as a soft-skip — see SmartOrderEngine.execute).

    sadp: R28 FL  R68 DPA
    """
    if not symbol:
        return ""
    # Try slash first (CCXT canonical), then dash (Coinbase product-id)
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
    """Configuration for an execution strategy."""
    strategy: ExecutionStrategy = ExecutionStrategy.MARKET
    # Iceberg params
    iceberg_slices: int = 5              # Number of chunks
    iceberg_delay_ms: int = 500          # Delay between chunks (ms)
    # TWAP params
    twap_duration_seconds: int = 60      # Spread order over this window
    twap_slices: int = 10                # Number of TWAP intervals
    # Limit-timeout params
    limit_offset_pct: float = 0.1        # Place limit X% from market
    limit_timeout_seconds: int = 30      # Convert to market after timeout
    # Adaptive thresholds
    large_order_pct: float = 5.0         # % of daily volume = "large"


@dataclass
class ExecutionResult:
    """Result of an order execution."""
    success: bool
    strategy_used: str
    total_quantity: float
    avg_fill_price: float
    slippage_pct: float  # vs. market price at start
    total_cost: float
    fills: list[dict] = field(default_factory=list)
    elapsed_ms: float = 0
    error: str = ""


class SmartOrderEngine:
    """
    Manages intelligent order execution.
    Wraps the exchange connector to provide smarter order placement.
    """

    def __init__(self, config: ExecutionConfig = None):
        self.config = config or ExecutionConfig()
        self._active_executions: dict[str, dict] = {}

    async def execute(self, exchange, symbol: str, side: str,
                      quantity: float, config: ExecutionConfig = None,
                      *,
                      bot_id: Optional[str] = None,
                      total_holdings: Optional[float] = None
                      ) -> ExecutionResult:

        # sadp: R28 R29  # smart order: fail-loudly(R28) idempotent(R29)
        """
        Execute an order using the configured strategy.

        Parameters
        ----------
        exchange : Exchange connector with create_order method
        symbol : Trading pair (e.g. "BTC/USDT" or "ETH-USD")
        side : "buy" or "sell"
        quantity : Amount to trade (in base-asset units)
        config : Override default execution config

        Keyword-only (v3.20.1 — capital reservation chokepoint)
        -------------------------------------------------------
        bot_id : Optional[str]
            Identifier of the bot placing this order. When provided
            together with ``total_holdings`` and ``side == "sell"``,
            the pre-flight check below consults the
            CapitalReservationRegistry to verify the sell quantity
            does not violate another bot's reservation on this asset.
            **Opt-in for backwards compatibility** — callers from
            pre-v3.20.1 code paths pass nothing and skip the check.
        total_holdings : Optional[float]
            Caller-supplied asset quantity currently held on the
            exchange (in base-asset units). Required alongside
            ``bot_id`` for the registry pre-flight. We do NOT call
            ``exchange.fetch_balance()`` here — that's slow and the
            caller usually already has this number.

        Returns
        -------
        ExecutionResult. If the registry pre-flight rejects the sell,
        returns ``success=False`` with ``strategy_used="rejected_by_
        reservation"`` and a descriptive ``error`` field; no order
        is placed on the exchange.

        sadp: R28 FL  R68 DPA  R76 DMW
        """
        cfg = config or self.config
        start = time.time()

        # ── v3.20.1 capital-reservation pre-flight (chokepoint) ──
        # Defense-in-depth backstop: the PRIMARY enforcement is the
        # ScrummingBot._delta() decision-level gate (lands v3.20.2),
        # but if a race or bug routes around it, the registry catches
        # the violation here before the order hits the exchange.
        #
        # Opt-in: requires bot_id + total_holdings. Skipping is logged
        # at DEBUG so operators can grep audit logs for bypass cases.
        # Only fires on sells — buys add to holdings, can't violate
        # another bot's claim.
        if bot_id is not None and total_holdings is not None \
                and side.lower() == "sell":
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
                # R28 FL — if the registry call itself fails, log the
                # exception but DO NOT block the trade. The primary
                # gate at bot decision-level is still in effect; we
                # don't want a registry bug to cripple all trading.
                # Reconciliation (v3.20.4) will catch drift if any.
                logger.error(
                    "smart_orders.execute: registry pre-flight raised "
                    "%s — falling through to exchange placement. "
                    "Investigate immediately.", exc,
                )
        elif (bot_id is None or total_holdings is None) \
                and side.lower() == "sell":
            # Operator-greppable audit trail for bypass cases.
            logger.debug(
                "smart_orders.execute: sell with bot_id=%r "
                "total_holdings=%r — registry pre-flight skipped "
                "(opt-in path).",
                bot_id, total_holdings,
            )

        # Get reference price
        try:
            ticker = await exchange.fetch_ticker(symbol)
            ref_price = ticker.get("last", 0) or ticker.get("close", 0)
        except Exception:  # R28-OK: ref-price probe; 0 disables price-aware logic downstream
            ref_price = 0

        strategy = cfg.strategy
        if strategy == ExecutionStrategy.ADAPTIVE:
            strategy = await self._choose_strategy(exchange, symbol, quantity, cfg)

        try:
            if strategy == ExecutionStrategy.ICEBERG:
                result = await self._execute_iceberg(
                    exchange, symbol, side, quantity, cfg, ref_price)
            elif strategy == ExecutionStrategy.TWAP:
                result = await self._execute_twap(
                    exchange, symbol, side, quantity, cfg, ref_price)
            elif strategy == ExecutionStrategy.LIMIT_TIMEOUT:
                result = await self._execute_limit_timeout(
                    exchange, symbol, side, quantity, cfg, ref_price)
            else:
                result = await self._execute_market(
                    exchange, symbol, side, quantity, ref_price)

            result.elapsed_ms = (time.time() - start) * 1000
            result.strategy_used = strategy.value
            return result

        except Exception as exc:
            logger.error("Smart order execution failed: %s", exc)
            return ExecutionResult(
                success=False, strategy_used=strategy.value,
                total_quantity=quantity, avg_fill_price=0,
                slippage_pct=0, total_cost=0,
                elapsed_ms=(time.time() - start) * 1000,
                error=str(exc))

    async def _execute_market(self, exchange, symbol: str, side: str,
                               quantity: float, ref_price: float
                               ) -> ExecutionResult:

        # sadp: R28 R29  # smart order: fail-loudly(R28) idempotent(R29)
        """Simple market order."""
        order = await exchange.create_order(symbol, "market", side, quantity)
        fill_price = order.get("average", ref_price) or ref_price
        cost = order.get("cost", fill_price * quantity)
        slippage = ((fill_price - ref_price) / ref_price * 100) if ref_price else 0
        if side == "buy":
            slippage = abs(slippage)  # Positive = paid more than ref
        else:
            slippage = -slippage  # Negative = received less than ref

        return ExecutionResult(
            success=True, strategy_used="market",
            total_quantity=quantity, avg_fill_price=fill_price,
            slippage_pct=round(slippage, 4), total_cost=cost,
            fills=[{"price": fill_price, "quantity": quantity, "type": "market"}])

    async def _execute_iceberg(self, exchange, symbol: str, side: str,
                                quantity: float, cfg: ExecutionConfig,
                                ref_price: float) -> ExecutionResult:

        # sadp: R28 R29  # smart order: fail-loudly(R28) idempotent(R29)
        """Split order into smaller chunks with delays."""
        slices = cfg.iceberg_slices
        chunk_size = quantity / slices
        delay = cfg.iceberg_delay_ms / 1000

        fills = []
        total_cost = 0
        total_filled = 0

        for i in range(slices):
            try:
                order = await exchange.create_order(
                    symbol, "market", side, chunk_size)
                fill_price = order.get("average", ref_price) or ref_price
                cost = order.get("cost", fill_price * chunk_size)
                fills.append({
                    "price": fill_price, "quantity": chunk_size,
                    "type": "iceberg", "slice": i + 1})
                total_cost += cost
                total_filled += chunk_size
                logger.debug("Iceberg %d/%d: %.8f @ $%.2f",
                             i + 1, slices, chunk_size, fill_price)
            except Exception as e:
                logger.warning("Iceberg slice %d failed: %s", i + 1, e)

            if i < slices - 1:
                await asyncio.sleep(delay)

        avg_price = total_cost / total_filled if total_filled else 0
        slippage = ((avg_price - ref_price) / ref_price * 100) if ref_price else 0

        return ExecutionResult(
            success=total_filled > 0, strategy_used="iceberg",
            total_quantity=total_filled, avg_fill_price=avg_price,
            slippage_pct=round(abs(slippage), 4), total_cost=total_cost,
            fills=fills)

    async def _execute_twap(self, exchange, symbol: str, side: str,
                             quantity: float, cfg: ExecutionConfig,
                             ref_price: float) -> ExecutionResult:

        # sadp: R28 R29  # smart order: fail-loudly(R28) idempotent(R29)
        """Spread order across time window."""
        slices = cfg.twap_slices
        interval = cfg.twap_duration_seconds / slices
        chunk_size = quantity / slices

        fills = []
        total_cost = 0
        total_filled = 0

        for i in range(slices):
            try:
                order = await exchange.create_order(
                    symbol, "market", side, chunk_size)
                fill_price = order.get("average", ref_price) or ref_price
                cost = order.get("cost", fill_price * chunk_size)
                fills.append({
                    "price": fill_price, "quantity": chunk_size,
                    "type": "twap", "interval": i + 1})
                total_cost += cost
                total_filled += chunk_size
            except Exception as e:
                logger.warning("TWAP interval %d failed: %s", i + 1, e)

            if i < slices - 1:
                await asyncio.sleep(interval)

        avg_price = total_cost / total_filled if total_filled else 0
        slippage = ((avg_price - ref_price) / ref_price * 100) if ref_price else 0

        return ExecutionResult(
            success=total_filled > 0, strategy_used="twap",
            total_quantity=total_filled, avg_fill_price=avg_price,
            slippage_pct=round(abs(slippage), 4), total_cost=total_cost,
            fills=fills)

    async def _execute_limit_timeout(self, exchange, symbol: str, side: str,
                                      quantity: float, cfg: ExecutionConfig,
                                      ref_price: float) -> ExecutionResult:

        # sadp: R28 R29  # smart order: fail-loudly(R28) idempotent(R29)
        """Place limit order, fall back to market if not filled."""
        offset = cfg.limit_offset_pct / 100
        if side == "buy":
            limit_price = ref_price * (1 - offset)
        else:
            limit_price = ref_price * (1 + offset)

        try:
            order = await exchange.create_order(
                symbol, "limit", side, quantity, limit_price)
            order_id = order.get("id", "")

            # Wait for fill
            filled = 0
            deadline = time.time() + cfg.limit_timeout_seconds
            while time.time() < deadline:
                await asyncio.sleep(2)
                try:
                    status = await exchange.fetch_order(order_id, symbol)
                    filled = status.get("filled", 0)
                    if status.get("status") in ("closed", "filled"):
                        break
                except Exception:  # R28-OK: order helper best-effort fallback
                    pass

            # If not fully filled, cancel and market-order the rest
            remaining = quantity - filled
            fills = []
            total_cost = 0

            if filled > 0:
                avg = order.get("average", limit_price)
                fills.append({"price": avg, "quantity": filled, "type": "limit"})
                total_cost += avg * filled

            if remaining > 0.001 * quantity:  # More than 0.1% remaining
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:  # R28-OK: order helper best-effort fallback
                    pass
                # Market order remainder
                mkt = await exchange.create_order(
                    symbol, "market", side, remaining)
                mkt_price = mkt.get("average", ref_price) or ref_price
                fills.append({"price": mkt_price, "quantity": remaining, "type": "market_fallback"})
                total_cost += mkt_price * remaining

            total_filled = filled + remaining
            avg_price = total_cost / total_filled if total_filled else 0
            slippage = ((avg_price - ref_price) / ref_price * 100) if ref_price else 0

            return ExecutionResult(
                success=True, strategy_used="limit_timeout",
                total_quantity=total_filled, avg_fill_price=avg_price,
                slippage_pct=round(abs(slippage), 4), total_cost=total_cost,
                fills=fills)

        except Exception as exc:
            # Fall back to pure market
            logger.warning("Limit-timeout failed, falling back to market: %s", exc)
            return await self._execute_market(exchange, symbol, side, quantity, ref_price)

    async def _choose_strategy(self, exchange, symbol: str,
                                quantity: float, cfg: ExecutionConfig
                                ) -> ExecutionStrategy:
        """Adaptively choose execution strategy based on order size."""
        try:
            ticker = await exchange.fetch_ticker(symbol)
            volume_24h = ticker.get("quoteVolume", 0) or ticker.get("baseVolume", 0) * ticker.get("last", 1)
            order_value = quantity * (ticker.get("last", 0) or 1)

            if volume_24h > 0:
                order_pct = (order_value / volume_24h) * 100
                if order_pct >= cfg.large_order_pct:
                    logger.info("Adaptive: order is %.2f%% of daily volume → ICEBERG", order_pct)
                    return ExecutionStrategy.ICEBERG
                elif order_pct >= cfg.large_order_pct / 2:
                    logger.info("Adaptive: order is %.2f%% of daily volume → LIMIT_TIMEOUT", order_pct)
                    return ExecutionStrategy.LIMIT_TIMEOUT

        except Exception:  # R28-OK: order helper best-effort fallback
            pass

        return ExecutionStrategy.MARKET
