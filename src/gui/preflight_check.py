"""
src/gui/preflight_check.py
──────────────────────────────────────────────────────────────────────
v3.13.8 MEM-185 / Chunk 1.5c — pre-flight symbol validation.

Runs AFTER the bot wizard collects config but BEFORE BotConfig is
instantiated. Verifies the chosen (exchange, symbol) pair is actually
tradeable, surfaces Coinbase-style market constraints to the operator,
and blocks bot creation when the constraints can't be met.

Uses sync CCXT (same pattern as src/exchange/api_validator.py) so the
check is quick, self-contained, and doesn't require the async event
loop. Credentials are OPTIONAL — public market data works without auth
on most exchanges including Coinbase.

Returns a PreflightResult. Caller renders a QMessageBox with the
findings and a Yes/No gate. This is DIAGNOSTIC + ADVISORY, not
authoritative — the actual order-placement guard is CCXT's
amount_to_precision / price_to_precision at order time.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

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
    min_order_amount: float = 0.0  # in base units
    min_order_cost: float = 0.0  # in quote units (USD for USD-quoted pairs)
    price_precision: int = 0
    amount_precision: int = 0
    last_price: float = 0.0
    elapsed_ms: float = 0.0
    warnings: list = field(default_factory=list)


def check_symbol(
    exchange_id: str,
    symbol: str,
    target_balance: float,
    api_key: str = "",
    api_secret: str = "",
    passphrase: str = "",
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
        active = bool(market.get("active", True))
        limits = market.get("limits", {}) or {}
        amt_limits = limits.get("amount", {}) or {}
        cost_limits = limits.get("cost", {}) or {}
        min_amt = float(amt_limits.get("min", 0.0) or 0.0)
        min_cost = float(cost_limits.get("min", 0.0) or 0.0)
        precision = market.get("precision", {}) or {}
        price_prec = int(precision.get("price", 0) or 0)
        amt_prec = int(precision.get("amount", 0) or 0)

        # Step 3: fetch ticker to confirm market is live and get current price
        try:
            ticker = exch.fetch_ticker(symbol)
            last_price = float(ticker.get("last", 0) or 0)
        except Exception:
            last_price = 0.0

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
        # MEM-250 (Session 26 operator directive): no "full unit" warning.
        # Acervator is a USD-denominated accumulation strategy. Crypto is
        # divisible. A $50 target on BTC buys 0.0005 BTC — that's entirely
        # normal and correct. The only legitimate capacity warning is
        # target_balance vs min_cost above (which uses USD). The previous
        # "Current price exceeds target balance. Bot cannot buy a full unit."
        # warning trained the wrong mental model (whole-unit thinking) and
        # blocked operators from testing the strategy on BTC/ETH/expensive
        # tokens. Deleted.

        elapsed = (time.monotonic() - start) * 1000

        return PreflightResult(
            success=True,
            exchange_id=exchange_id,
            symbol=symbol,
            message=f"Symbol verified on {exchange_id.capitalize()}.",
            market_active=active,
            min_order_amount=min_amt,
            min_order_cost=min_cost,
            price_precision=price_prec,
            amount_precision=amt_prec,
            last_price=last_price,
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

    lines = [
        "✓ Pre-flight check passed",
        "",
        f"Exchange: {result.exchange_id.capitalize()}",
        f"Symbol: {result.symbol}",
        f"Market active: {'Yes' if result.market_active else 'No'}",
    ]
    if result.last_price > 0:
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
