"""``CapitalRegistry`` — one ``Reservation`` per bot against a wallet.

``request_reservation`` refuses outright when the reservations on an
(exchange, base) pair would exceed the wallet, and grants when
``_wallet_usd`` cannot price the wallet. ``get_free`` and
``reconcile_with_exchange`` report the wallet against those claims, and
``_persist_locked`` hands the state to ``settings_callback``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger("acervator.capital_registry")


@dataclass
class Reservation:
    """One bot's claim on an (``exchange_id``, ``base_currency``) pair.

    ``reserved_usd`` is the anchor and ``reserved_base`` its snapshot at
    ``last_rate_usd_per_base``, which ``refresh_rate`` renews; ``bot_mode``
    reaches the capital registry table and ``reconcile_with_exchange`` never
    reads it.
    """

    bot_id: str
    exchange_id: str
    base_currency: str
    reserved_usd: float
    reserved_base: float
    last_rate_usd_per_base: float
    reserved_at_ts: float
    last_refreshed_ts: float
    bot_mode: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Reservation":
        return cls(
            bot_id=str(d["bot_id"]),
            exchange_id=str(d["exchange_id"]),
            base_currency=str(d["base_currency"]).upper(),
            reserved_usd=float(d["reserved_usd"]),
            reserved_base=float(d["reserved_base"]),
            last_rate_usd_per_base=float(d["last_rate_usd_per_base"]),
            reserved_at_ts=float(d["reserved_at_ts"]),
            last_refreshed_ts=float(d["last_refreshed_ts"]),
            bot_mode=str(d.get("bot_mode", "scrumming")),
        )


_SETTINGS_KEY = "capital_registry_reservations"

# _wallet_usd takes a balance in one of these as already USD.
_USD_LIKE = frozenset({"USD", "USDC", "USDT", "DAI", "BUSD", "PYUSD", "FDUSD"})


class CrossLoopAccessError(RuntimeError):
    """Raised by ``_check_loop`` when a call arrives from a different running
    loop than the one that built the ``CapitalRegistry``."""


class CapitalRegistry:
    """Holds every bot's ``Reservation`` in ``_reservations``, keyed by bot_id,
    behind one re-entrant ``_lock``.

    Every method that changes ``_reservations`` reaches ``_persist_locked``, and
    every public method except ``serialize`` opens with ``_check_loop``.
    """

    def __init__(
        self,
        *,
        wallet_balances_provider=None,
        settings_callback=None,
        initial_reservations: Optional[list[dict]] = None,
    ) -> None:
        """Build the registry, rehydrating ``_reservations`` from
        ``initial_reservations`` and dropping any entry
        ``Reservation.from_dict`` rejects.

        ``wallet_balances_provider`` returns a base-currency balance for
        ``_wallet_usd``; when it is None ``get_free`` returns negated totals.
        """
        self._lock = threading.RLock()
        self._reservations: dict[str, Reservation] = {}  # keyed by bot_id
        self._wallet_provider = wallet_balances_provider
        self._settings_callback = settings_callback
        try:
            self._origin_loop = asyncio.get_event_loop()
        except RuntimeError:
            self._origin_loop = None

        if initial_reservations:
            for d in initial_reservations:
                try:
                    r = Reservation.from_dict(d)
                    self._reservations[r.bot_id] = r
                except (KeyError, ValueError, TypeError):
                    pass

    def _check_loop(self) -> None:
        """Raise ``CrossLoopAccessError`` when the running loop differs from
        ``_origin_loop``.

        Returns without raising unless both loops exist.
        """
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._origin_loop is not None and self._origin_loop is not current:
            raise CrossLoopAccessError(
                f"CapitalRegistry created in loop {id(self._origin_loop)} "
                f"but accessed from loop {id(current)}. This causes "
                f"silent reservation corruption — see the DataPool "
                f"v3.16.19 / MEM-219 lineage for the same bug class."
            )

    def request_reservation(
        self,
        *,
        bot_id: str,
        exchange_id: str,
        base_currency: str,
        usd_amount: float,
        current_rate_usd_per_base: float,
        bot_mode: str,
    ) -> tuple[bool, Optional[str], float]:
        """Create or replace ``bot_id``'s ``Reservation`` and return
        ``(granted, reason, granted_usd)``.

        A total above the ``_wallet_usd`` figure is refused whole with
        ``granted_usd`` 0, and a ``_wallet_usd`` of None grants unchecked.
        """
        self._check_loop()
        with self._lock:
            base = (base_currency or "").upper()
            mode = bot_mode.lower()
            if mode not in ("scrumming", "extractor"):
                return (
                    False,
                    (
                        f"Unknown bot_mode {bot_mode!r}; expected "
                        f"'scrumming' or 'extractor'"
                    ),
                    0.0,
                )
            if usd_amount <= 0:
                return False, (f"usd_amount must be positive, got {usd_amount}"), 0.0
            rate = float(current_rate_usd_per_base or 0)
            if rate <= 0:
                return (
                    False,
                    (
                        f"current_rate_usd_per_base must be positive, "
                        f"got {current_rate_usd_per_base}"
                    ),
                    0.0,
                )

            other_total_usd = 0.0
            for r in self._reservations.values():
                if r.bot_id == bot_id:
                    continue
                if r.exchange_id != exchange_id:
                    continue
                if r.base_currency != base:
                    continue
                other_total_usd += r.reserved_usd

            wallet_usd = self._wallet_usd(exchange_id, base, rate)
            if wallet_usd is None:
                # Nothing is logged or recorded here; the grant below is silent.
                pass
            else:
                if other_total_usd + usd_amount > wallet_usd + 1e-6:
                    return (
                        False,
                        (
                            f"REFUSED — over-allocation. Bot {bot_id} "
                            f"requested ${usd_amount:.2f} but wallet has "
                            f"${wallet_usd:.2f} on {exchange_id}/{base} "
                            f"and other bots already reserve "
                            f"${other_total_usd:.2f}. Reduce other bot "
                            f"allocations or deposit more "
                            f"{base}."
                        ),
                        0.0,
                    )

            now_ts = float(time.time())
            reserved_base = usd_amount / rate
            self._reservations[bot_id] = Reservation(
                bot_id=bot_id,
                exchange_id=exchange_id,
                base_currency=base,
                reserved_usd=usd_amount,
                reserved_base=reserved_base,
                last_rate_usd_per_base=rate,
                reserved_at_ts=now_ts,
                last_refreshed_ts=now_ts,
                bot_mode=mode,
            )
            self._persist_locked()
            return True, None, usd_amount

    def release_reservation(self, *, bot_id: str) -> float:
        """Drop ``bot_id`` from ``_reservations`` and return its
        ``reserved_usd``, or 0.0 when it held none."""
        self._check_loop()
        with self._lock:
            r = self._reservations.pop(bot_id, None)
            self._persist_locked()
            return float(r.reserved_usd) if r is not None else 0.0

    def grow_reservation(
        self,
        *,
        bot_id: str,
        additional_usd: float,
        current_rate_usd_per_base: Optional[float] = None,
    ) -> tuple[bool, Optional[str], float]:
        """Add ``additional_usd`` to ``bot_id``'s ``reserved_usd`` and return
        ``(success, reason, new_total_usd)``.

        The growth is not checked against ``_wallet_usd``; a later
        ``request_reservation`` from another bot counts the grown total.
        """
        self._check_loop()
        with self._lock:
            if additional_usd <= 0:
                return (
                    False,
                    (f"additional_usd must be positive, got " f"{additional_usd}"),
                    0.0,
                )
            r = self._reservations.get(bot_id)
            if r is None:
                return (
                    False,
                    (
                        f"No existing reservation for bot {bot_id} — "
                        f"cannot grow what doesn't exist. Call "
                        f"request_reservation() first."
                    ),
                    0.0,
                )

            new_usd = r.reserved_usd + additional_usd
            rate = (
                float(current_rate_usd_per_base)
                if current_rate_usd_per_base and current_rate_usd_per_base > 0
                else float(r.last_rate_usd_per_base)
            )
            if rate <= 0:
                return (
                    False,
                    (
                        f"Cannot grow reservation for bot {bot_id} with "
                        f"non-positive rate {rate}"
                    ),
                    0.0,
                )

            now_ts = float(time.time())
            r.reserved_usd = new_usd
            r.reserved_base = new_usd / rate
            r.last_rate_usd_per_base = rate
            r.last_refreshed_ts = now_ts
            self._persist_locked()
            return True, None, new_usd

    def update_reservation(
        self,
        *,
        bot_id: str,
        new_usd: float,
        current_rate_usd_per_base: float,
    ) -> tuple[bool, Optional[str]]:
        """Re-run ``request_reservation`` for ``bot_id`` at ``new_usd``, reusing
        the ``exchange_id``, ``base_currency`` and ``bot_mode`` it already holds.

        Returns ``(success, reason)`` and refuses when ``bot_id`` holds none.
        """
        self._check_loop()
        with self._lock:
            r = self._reservations.get(bot_id)
            if r is None:
                return False, (
                    f"No existing reservation for bot {bot_id}; "
                    f"call request_reservation() instead."
                )
            granted, reason, _ = self.request_reservation(
                bot_id=bot_id,
                exchange_id=r.exchange_id,
                base_currency=r.base_currency,
                usd_amount=new_usd,
                current_rate_usd_per_base=current_rate_usd_per_base,
                bot_mode=r.bot_mode,
            )
            return granted, reason

    def refresh_rate(
        self,
        *,
        exchange_id: str,
        base_currency: str,
        current_rate_usd_per_base: float,
    ) -> int:
        """Recompute ``reserved_base`` and ``last_rate_usd_per_base`` on every
        reservation matching ``exchange_id`` and ``base_currency``.

        Returns how many were updated, and 0 for a non-positive rate.
        """
        self._check_loop()
        with self._lock:
            base = (base_currency or "").upper()
            rate = float(current_rate_usd_per_base or 0)
            if rate <= 0:
                return 0
            n = 0
            now_ts = float(time.time())
            for r in self._reservations.values():
                if r.exchange_id == exchange_id and r.base_currency == base:
                    r.reserved_base = r.reserved_usd / rate
                    r.last_rate_usd_per_base = rate
                    r.last_refreshed_ts = now_ts
                    n += 1
            if n > 0:
                self._persist_locked()
            return n

    def get_free(
        self,
        *,
        exchange_id: str,
        base_currency: str,
        current_rate_usd_per_base: Optional[float] = None,
    ) -> tuple[float, float]:
        """Return ``(free_usd, free_base)``, the ``_wallet_usd`` figure less the
        reservations on this ``exchange_id`` and ``base_currency``.

        A ``_wallet_usd`` of None returns the negated totals, and the caller
        adds them to its own wallet figure.
        """
        self._check_loop()
        with self._lock:
            base = (base_currency or "").upper()
            total_usd = sum(
                r.reserved_usd
                for r in self._reservations.values()
                if r.exchange_id == exchange_id and r.base_currency == base
            )
            total_base = sum(
                r.reserved_base
                for r in self._reservations.values()
                if r.exchange_id == exchange_id and r.base_currency == base
            )
            rate = current_rate_usd_per_base
            wallet_usd = self._wallet_usd(exchange_id, base, rate)
            if wallet_usd is None:
                return -total_usd, -total_base
            free_usd = wallet_usd - total_usd
            if rate and rate > 0:
                return free_usd, free_usd / rate
            return free_usd, 0.0

    def reconcile_with_exchange(
        self,
        *,
        exchange_id: str,
        base_currency: str,
        exchange_balance_base: float,
        current_rate_usd_per_base: float,
    ) -> dict:
        """Call ``refresh_rate``, then compare ``exchange_balance_base`` against
        the reservations on this ``exchange_id`` and ``base_currency``.

        Returns ``wallet_base``, ``wallet_usd``, ``reserved_usd``,
        ``reserved_base``, ``free_usd``, ``free_base``, ``drift_usd`` and
        ``drift_pct``, or an error entry for a non-positive rate.
        """
        self._check_loop()
        with self._lock:
            base = (base_currency or "").upper()
            rate = float(current_rate_usd_per_base or 0)
            if rate <= 0:
                return {"error": "invalid rate", "rate": rate}
            self.refresh_rate(
                exchange_id=exchange_id,
                base_currency=base,
                current_rate_usd_per_base=rate,
            )
            wallet_base = float(exchange_balance_base or 0)
            wallet_usd = wallet_base * rate
            reserved_usd = sum(
                r.reserved_usd
                for r in self._reservations.values()
                if r.exchange_id == exchange_id and r.base_currency == base
            )
            reserved_base = reserved_usd / rate
            free_usd = wallet_usd - reserved_usd
            free_base = wallet_base - reserved_base
            drift_usd = wallet_usd - sum(
                r.reserved_usd
                for r in self._reservations.values()
                if r.exchange_id == exchange_id and r.base_currency == base
            )
            drift_pct = 100.0 * abs(drift_usd) / wallet_usd if wallet_usd > 0 else 0.0
            return {
                "wallet_base": wallet_base,
                "wallet_usd": wallet_usd,
                "reserved_usd": reserved_usd,
                "reserved_base": reserved_base,
                "free_usd": free_usd,
                "free_base": free_base,
                "drift_usd": drift_usd,
                "drift_pct": drift_pct,
            }

    def get_reservations(
        self,
        *,
        exchange_id: Optional[str] = None,
        base_currency: Optional[str] = None,
    ) -> list[Reservation]:
        """Return copied ``Reservation`` objects, narrowed by ``exchange_id``
        and ``base_currency`` when either is given.

        Each copy leaves ``_reservations`` unreachable to the caller.
        """
        self._check_loop()
        with self._lock:
            base = (base_currency or "").upper() if base_currency else None
            result = []
            for r in self._reservations.values():
                if exchange_id is not None and r.exchange_id != exchange_id:
                    continue
                if base is not None and r.base_currency != base:
                    continue
                result.append(Reservation(**asdict(r)))
            return result

    def serialize(self) -> dict:
        """Return every ``Reservation`` as dicts under ``_SETTINGS_KEY``."""
        with self._lock:
            return {_SETTINGS_KEY: [r.to_dict() for r in self._reservations.values()]}

    def _wallet_usd(
        self,
        exchange_id: str,
        base_currency: str,
        rate: Optional[float],
    ) -> Optional[float]:
        """Return the ``_wallet_provider`` balance in USD, taking a
        ``_USD_LIKE`` base as already USD.

        None when ``_wallet_provider`` is absent or raises, or when ``rate`` is
        missing for a base outside ``_USD_LIKE``.
        """
        if self._wallet_provider is None:
            return None
        try:
            wallet_base = float(self._wallet_provider(exchange_id, base_currency) or 0)
        except Exception:
            return None
        if base_currency.upper() in _USD_LIKE:
            return wallet_base
        if rate is None or rate <= 0:
            return None
        return wallet_base * rate

    def _persist_locked(self) -> None:
        """Hand ``_settings_callback`` every ``Reservation`` under
        ``_SETTINGS_KEY``, leaving the write to the caller.

        A raising callback is logged and swallowed.
        """
        if self._settings_callback is None:
            return
        try:
            payload = {
                _SETTINGS_KEY: [r.to_dict() for r in self._reservations.values()]
            }
            self._settings_callback(payload)
        except Exception as _pers_exc:  # noqa: BLE001
            logger.warning(
                "Capital reservation persistence FAILED (%s): %s — "
                "%d reservation(s) held in memory only and will be LOST "
                "on restart",
                type(_pers_exc).__name__,
                _pers_exc,
                len(self._reservations),
            )


def settings_key() -> str:
    """Return ``_SETTINGS_KEY``, the settings entry ``serialize`` writes under."""
    return _SETTINGS_KEY
