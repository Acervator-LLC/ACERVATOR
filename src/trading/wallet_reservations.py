"""Soft reservations against a wallet many bots share.

THE DEFECT THIS CLOSES (operator item 2, M3, 2026-08-06)
The Manual Fire FOLD branch clips its buy to available cash:

    usd_balance = quote_free * _qrate
    buy_usd = min(buy_usd_target, usd_balance)

Measured against live state 2026-08-07: all 35 bots report the SAME
``cash_balance_usd`` -- they share one wallet -- and each reads it with
no reservation. A single fire is safe (0 of 20 eligible bots clipped
today). Concurrent fires are not: every bot sees the full balance, each
believes it can afford its own buy, and collectively they can commit
more than exists. The exchange then rejects or partially fills whichever
arrive last, which lands as an unexplained amount.

WHAT THIS IS AND IS NOT
It is a PROCESS-LOCAL advisory ledger. It cannot stop an order placed by
another process, another machine, or the operator's own hand on the
Coinbase site. It exists so the fleet does not race ITSELF, which is the
only party it can actually coordinate.

WHY NO LOCK
Every bot runs on the manager's single asyncio loop.
``reserve``/``release`` contain no ``await``, so they are atomic with
respect to other coroutines: nothing can interleave between reading the
outstanding total and adding to it. Introducing a lock would add an
await point and make the operation genuinely interruptible -- the
opposite of what is wanted.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("acervator.trading.wallet")


def wallet_key(exchange_id: str, currency: str) -> str:
    return f"{exchange_id}|{currency}"


class WalletReservations:
    """Outstanding soft holds per (exchange, currency)."""

    def __init__(self) -> None:
        self._held: dict[str, float] = {}

    def reserved(self, key: str) -> float:
        """USD-equivalent currently spoken for by in-flight orders."""
        return float(self._held.get(key, 0.0))

    def available(self, key: str, free_usd: float) -> float:
        """What THIS caller may still spend, given what others hold.

        Never negative: an over-reserved wallet reports zero headroom
        rather than a negative budget that would flip a comparison.
        """
        return max(0.0, float(free_usd) - self.reserved(key))

    def reserve(self, key: str, amount_usd: float) -> float:
        """Claim ``amount_usd``. Returns the amount actually claimed.

        Contains no await: atomic against other coroutines on the loop.
        """
        amt = max(0.0, float(amount_usd))
        if amt <= 0:
            return 0.0
        self._held[key] = self.reserved(key) + amt
        return amt

    def release(self, key: str, amount_usd: float) -> None:
        """Drop a hold. Clamped at zero and pruned when it empties.

        Releasing more than is held would drive the total negative and
        hand the next caller a budget larger than the wallet.
        """
        amt = max(0.0, float(amount_usd))
        if amt <= 0:
            return
        remaining = self.reserved(key) - amt
        if remaining <= 1e-9:
            self._held.pop(key, None)
        else:
            self._held[key] = remaining

    def clear(self) -> None:
        """Drop every hold. For shutdown and for tests."""
        self._held.clear()

    def snapshot(self) -> dict[str, float]:
        return dict(self._held)


_RESERVATIONS = WalletReservations()


def get_wallet_reservations() -> WalletReservations:
    """The process-wide ledger. One wallet, one ledger."""
    return _RESERVATIONS
