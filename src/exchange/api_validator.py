"""
api_validator.py - Test exchange API credentials (fully synchronous)
====================================================================
Uses SYNC CCXT (requests library) - no asyncio/aiohttp.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("acervator.exchange")

#: What a venue needing no extra phrase is asked with.
EMPTY_PHRASE = ""


@dataclass
class ValidationResult:
    """Result of an API credential validation test."""

    success: bool
    exchange_id: str
    message: str
    details: str = ""
    elapsed_ms: float = 0.0
    balances: dict = field(default_factory=dict)


def validate_credentials(
    exchange_id: str,
    api_key: str,
    api_secret: str,
    passphrase: str = EMPTY_PHRASE,
) -> ValidationResult:
    """
    Test API credentials synchronously. Single connection, single balance
    check, no retries, no async. Uses sync CCXT (requests library).
    """
    start = time.monotonic()

    if not api_key or not api_secret:
        return ValidationResult(
            success=False,
            exchange_id=exchange_id,
            message="API key and secret are required.",
        )

    try:
        from .ccxt_connector import CCXTConnector, PASSPHRASE_EXCHANGES

        if exchange_id in PASSPHRASE_EXCHANGES and not passphrase:
            return ValidationResult(
                success=False,
                exchange_id=exchange_id,
                message=f"{exchange_id.capitalize()} requires an API passphrase.",
            )

        connector = CCXTConnector(exchange_id)
        connector.sync_connect(api_key, api_secret, passphrase)

        # Fetch balances using the sync exchange directly
        sync_exch = getattr(connector, "_ccxt_sync", None)
        bal_summary = ""
        bal_dict = {}
        asset_count = 0

        if sync_exch:
            raw = sync_exch.fetch_balance()
            free = raw.get("free", {})
            total = raw.get("total", {})

            parts = []
            for currency, amount in total.items():
                amt = float(amount or 0)
                if amt > 0:
                    bal_dict[currency] = {
                        "free": float(free.get(currency, 0) or 0),
                        "total": amt,
                    }
                    parts.append(f"{currency}: {amt:.6g}")

            asset_count = len(bal_dict)
            bal_summary = ", ".join(parts[:10])
            if len(parts) > 10:
                bal_summary += f" (+{len(parts) - 10} more)"

        elapsed = (time.monotonic() - start) * 1000
        market_count = len(sync_exch.markets) if sync_exch and sync_exch.markets else 0

        from .credential_state import record_validated

        record_validated(exchange_id)
        return ValidationResult(
            success=True,
            exchange_id=exchange_id,
            message=f"Connected to {exchange_id.capitalize()}. {market_count} markets, {asset_count} assets with balance.",
            details=bal_summary if bal_summary else "No balances found.",
            elapsed_ms=elapsed,
            balances=bal_dict,
        )

    except ImportError:
        return ValidationResult(
            success=False,
            exchange_id=exchange_id,
            message="ccxt package not installed.",
        )
    except Exception as exc:  # R28-OK: error surfaced via ValidationResult below
        elapsed = (time.monotonic() - start) * 1000
        from .ccxt_connector import CCXTConnector
        from .credential_state import record_connection_lost

        record_connection_lost(exchange_id)
        detail = CCXTConnector._format_exchange_error(exc)
        return ValidationResult(
            success=False,
            exchange_id=exchange_id,
            message=detail,
            details="",
            elapsed_ms=elapsed,
        )
