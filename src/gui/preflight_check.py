"""Pre-flight validation of an (exchange, symbol) pair before a bot exists.

check_symbol runs sync CCXT against public market data and returns a
PreflightResult carrying the venue's constraints and any warnings.
format_result_for_user renders that for the wizard's Yes/No gate. The
authoritative guard is still CCXT's precision rounding at order time.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ..exchange.ccxt_connector import (
    CCXT_DECIMAL_PLACES,
    LISTED_MARKET_KEY,
    is_listed_market,
    precision_to_decimals,
)

logger = logging.getLogger("acervator.preflight")


@dataclass
class PreflightResult:
    """Summary of the pre-flight check."""

    success: bool
    exchange_id: str
    symbol: str
    message: str
    # Market details (populated on success)
    market_active: bool = False
    # False when the market carried no active field, so market_active is a default.
    active_reported: bool = False
    min_order_amount: float = 0.0  # in base units
    min_order_cost: float = 0.0  # in quote units (USD for USD-quoted pairs)
    price_precision: int = 0
    amount_precision: int = 0
    last_price: float = 0.0
    # False when fetch_ticker raised, so last_price is a default and not a price.
    price_read: bool = False
    elapsed_ms: float = 0.0
    warnings: list = field(default_factory=list)


def check_symbol(
    exchange_id: str,
    symbol: str,
    target_balance: float,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    passphrase: Optional[str] = None,
) -> PreflightResult:
    """Verify a (exchange, symbol) pair is tradeable at the target balance.

    Args:
        exchange_id: "coinbase", "binance", etc.
        symbol: "RAVE/USD", "BTC/USDT", etc.
        target_balance: operator's intended trading capital (quote units)
        api_key/api_secret/passphrase: OPTIONAL — public markets data
            works without authentication on most exchanges. If provided,
            an authenticated ticker fetch runs as a connectivity sanity
            check.

    Returns PreflightResult with success flag + diagnostic details.
    """
    start = time.monotonic()

    try:
        import ccxt  # sync CCXT
    except ImportError:
        return PreflightResult(
            success=False,
            exchange_id=exchange_id,
            symbol=symbol,
            message="CCXT library not available. Install with: pip install ccxt",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        ExchCls = getattr(ccxt, exchange_id, None)
        if ExchCls is None:
            return PreflightResult(
                success=False,
                exchange_id=exchange_id,
                symbol=symbol,
                message=(
                    f"Exchange '{exchange_id}' not recognized by CCXT. "
                    f"Check spelling (e.g. 'coinbase', 'binance')."
                ),
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

        # Build config — credentials optional
        cfg = {"enableRateLimit": True, "timeout": 15000}
        if api_key:
            cfg["apiKey"] = api_key
        if api_secret:
            cfg["secret"] = api_secret
        if passphrase:
            cfg["password"] = passphrase

        exch = ExchCls(cfg)

        # Step 1: load markets (public endpoint, no auth required)
        markets = exch.load_markets()

        if symbol not in markets:
            # Attempt casing / separator variations
            alternatives = [
                symbol.upper(),
                symbol.lower(),
                symbol.replace("/", "-"),
                symbol.replace("-", "/"),
            ]
            hit = next((a for a in alternatives if a in markets), None)
            if hit is not None:
                return PreflightResult(
                    success=False,
                    exchange_id=exchange_id,
                    symbol=symbol,
                    message=(
                        f"Symbol '{symbol}' not found but '{hit}' exists. "
                        f"Use the exact casing/format listed by the exchange."
                    ),
                    elapsed_ms=(time.monotonic() - start) * 1000,
                )
            return PreflightResult(
                success=False,
                exchange_id=exchange_id,
                symbol=symbol,
                message=(
                    f"Symbol '{symbol}' is not listed on "
                    f"{exchange_id.capitalize()}. Check the asset is "
                    f"actively traded on this exchange."
                ),
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

        market = markets[symbol]

        # Step 2: extract constraints
        active_reported = market.get(LISTED_MARKET_KEY) is not None
        active = is_listed_market(market)
        limits = market.get("limits", {}) or {}
        amt_limits = limits.get("amount", {}) or {}
        cost_limits = limits.get("cost", {}) or {}
        min_amt = float(amt_limits.get("min", 0.0) or 0.0)
        min_cost = float(cost_limits.get("min", 0.0) or 0.0)
        precision = market.get("precision", {}) or {}
        precision_mode = getattr(exch, "precisionMode", CCXT_DECIMAL_PLACES)
        price_prec = precision_to_decimals(
            precision.get("price"), precision_mode, default=0
        )
        amt_prec = precision_to_decimals(
            precision.get("amount"), precision_mode, default=0
        )

        # Step 3: fetch ticker to confirm market is live and get current price
        try:
            ticker = exch.fetch_ticker(symbol)
            last_price = float(ticker.get("last", 0) or 0)
            price_read = True
        except Exception:
            last_price = 0.0
            price_read = False

        warnings = []
        if not active:
            warnings.append(
                f"Market reported as inactive by {exchange_id.capitalize()}"
            )
        if min_cost > 0 and target_balance < min_cost * 3:
            warnings.append(
                f"Target balance ${target_balance:.2f} is less than 3x min-order-cost "
                f"(${min_cost:.2f}). Bot may only place a handful of trades."
            )
        elapsed = (time.monotonic() - start) * 1000

        return PreflightResult(
            success=True,
            exchange_id=exchange_id,
            symbol=symbol,
            message=f"Symbol verified on {exchange_id.capitalize()}.",
            market_active=active,
            active_reported=active_reported,
            min_order_amount=min_amt,
            min_order_cost=min_cost,
            price_precision=price_prec,
            amount_precision=amt_prec,
            last_price=last_price,
            price_read=price_read,
            elapsed_ms=elapsed,
            warnings=warnings,
        )

    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        logger.error("Preflight check failed: %s", exc)
        return PreflightResult(
            success=False,
            exchange_id=exchange_id,
            symbol=symbol,
            message=f"Pre-flight check failed: {type(exc).__name__}: {exc}",
            elapsed_ms=elapsed,
        )


def format_result_for_user(result: PreflightResult) -> str:
    """Human-readable rendering of a PreflightResult for modal display."""
    if not result.success:
        return (
            f"⚠ Pre-flight check FAILED\n\n"
            f"{result.message}\n\n"
            f"Elapsed: {result.elapsed_ms:.0f} ms"
        )

    if result.active_reported:
        active_word = "Yes" if result.market_active else "No"
    else:
        active_word = "not reported"
    lines = [
        "✓ Pre-flight check passed",
        "",
        f"Exchange: {result.exchange_id.capitalize()}",
        f"Symbol: {result.symbol}",
        f"Market active: {active_word}",
    ]
    if not result.price_read:
        lines.append("Current price: not read")
    elif result.last_price > 0:
        lines.append(f"Current price: ${result.last_price:.8f}")
    if result.min_order_amount > 0:
        lines.append(
            f"Min order amount: {result.min_order_amount} "
            f"({result.amount_precision} decimals)"
        )
    if result.min_order_cost > 0:
        lines.append(f"Min order cost: ${result.min_order_cost:.4f}")
    if result.price_precision > 0:
        lines.append(f"Price precision: {result.price_precision} decimals")

    lines.append("")
    lines.append(f"Check elapsed: {result.elapsed_ms:.0f} ms")

    if result.warnings:
        lines.append("")
        lines.append("⚠ WARNINGS:")
        for w in result.warnings:
            lines.append(f"  • {w}")

    return "\n".join(lines)
