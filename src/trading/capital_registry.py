"""src/trading/capital_registry.py — central broker for wallet capital
across all bots on the same exchange + base currency.

Born v3.20.70 (Phase B of the v3.20.67 design doc). Closes the
three confidence gaps documented in
`docs/audits/2026-06-05_bot_coordination_audit.md`:

  • Two Scrumming bots, same exchange/base — was 85%; broker enforces
    via reservation invariant: sum(reservations) ≤ wallet_total.
  • Scrumming + Extractor, same exchange/base — was 40% (Scrumming saw
    Extractor's claim but not vice versa); broker is consulted by
    BOTH classes; the asymmetry is closed.
  • Two Extractors, same exchange/base — was 30% (no mutual visibility);
    broker enforces the same invariant.

Operator-locked parameters from v3.20.69 design lock-in:
  • Q3 over-allocation UX in wizard: REFUSE OUTRIGHT (no warn-and-confirm)
  • Q4 persistence: persisted to settings.json (survives crash)
  • (Q1 reconciliation cadence + Q2 rate-spike threshold consumed in
    Phases D + C respectively)

R57 EPM binding: this module MUST be mirrored in
sadp/RAIntSimBat/RAIntSimBat.py via a parallel
`CapitalRegistryBattery` so the offline battery has matching semantics.
The R6 cascade-gate check (v3.20.69, MEM-415) enforces that any cascade
touching `src/trading/extractor_bot.py` or `scrumming_bot.py` must
ALSO touch RAIntSimBat in the same cascade.

MEM-416.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger("acervator.capital_registry")


# ---------------------------------------------------------------------------
# Public data class
# ---------------------------------------------------------------------------


@dataclass
class Reservation:
    """One bot's claim on capital for a specific (exchange, base) pair.

    Fields:
      bot_id: bot identifier
      exchange_id: exchange the reservation is against (e.g. "coinbase")
      base_currency: base/quote currency of the reservation (e.g. "USD")
      reserved_usd: canonical USD-denominated reservation amount
      reserved_base: snapshot of reserved_usd in base-currency units at
          last_rate_usd_per_base — refreshed on rate updates
      last_rate_usd_per_base: last known rate used to convert
          reserved_usd to reserved_base
      reserved_at_ts: unix seconds; when the reservation was originally
          requested
      last_refreshed_ts: unix seconds; when the snapshot was last updated
      bot_mode: "scrumming" or "extractor" — used by reconciliation
          and the GUI registry table (Phase D)
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


# ---------------------------------------------------------------------------
# CapitalRegistry — the broker
# ---------------------------------------------------------------------------

# Maps the canonical settings.json key for persistence
_SETTINGS_KEY = "capital_registry_reservations"

# USD-like assets — no rate conversion needed
_USD_LIKE = frozenset({"USD", "USDC", "USDT", "DAI", "BUSD", "PYUSD", "FDUSD"})


class CrossLoopAccessError(RuntimeError):
    """Raised when the registry is accessed from an asyncio loop
    different from the one it was created in. Mirrors the DataPool
    v3.16.19 cross-loop poisoning detection (MEM-219)."""


class CapitalRegistry:
    """Central broker for capital reservations across bots.

    Thread-safety: a single re-entrant lock guards all mutations and
    most reads. Asyncio-loop discipline: the registry remembers the
    loop it was created in (if any) and raises CrossLoopAccessError
    if a future async user tries to mutate it from a different loop.
    The current v3.20.70 surface is synchronous, but the loop check
    is in place for Phase D's periodic-reconciliation coroutine.

    Persistence: when `settings_callback` is provided at construction,
    every mutation triggers a serialize-and-persist of the
    reservations to settings.json via the callback. The callback
    receives a dict that the caller embeds under the `_SETTINGS_KEY`
    settings entry. On startup, callers can pass `initial_reservations`
    (loaded from settings.json) to rehydrate the broker.
    """

    def __init__(
        self,
        *,
        wallet_balances_provider=None,
        settings_callback=None,
        initial_reservations: Optional[list[dict]] = None,
    ) -> None:
        """Construct the broker.

        Args:
          wallet_balances_provider: optional callable
            ``(exchange_id, base_currency) -> float`` returning the
            current wallet balance in base-currency units. Used by
            ``reconcile_with_exchange()`` and ``get_free()`` to compute
            the free pool. If None, the registry operates in a degraded
            mode where ``get_free()`` returns the negative of total
            reservations (caller computes "free" as wallet - returned).
          settings_callback: optional callable
            ``(dict) -> None`` invoked after every mutation with the
            registry's serializable state. Caller persists this under
            the canonical settings key (`_SETTINGS_KEY`).
          initial_reservations: optional list of dicts (as produced by
            ``Reservation.to_dict()``) used to rehydrate state on
            startup. Reservations with bot_ids not currently registered
            with any active bot are kept (paused bots still own their
            allocation per the v3.18.18 sibling-claim discipline).
        """
        self._lock = threading.RLock()
        self._reservations: dict[str, Reservation] = {}  # keyed by bot_id
        self._wallet_provider = wallet_balances_provider
        self._settings_callback = settings_callback
        # Loop-poisoning detection — record the loop the registry was
        # constructed in (None if no loop running). v3.16.19 pattern.
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
                    # Malformed entry — skip without crashing the broker
                    pass

    # ------------------------------------------------------------------
    # Cross-loop guard (mirrors data_pool.py v3.16.19 fix)
    # ------------------------------------------------------------------
    def _check_loop(self) -> None:
        """Raise if called from a different running loop than the one
        the registry was created in. Only fires when both the origin
        and the current call site are inside an asyncio loop."""
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            return  # not in an async context; sync access is allowed
        if self._origin_loop is not None and self._origin_loop is not current:
            raise CrossLoopAccessError(
                f"CapitalRegistry created in loop {id(self._origin_loop)} "
                f"but accessed from loop {id(current)}. This causes "
                f"silent reservation corruption — see the DataPool "
                f"v3.16.19 / MEM-219 lineage for the same bug class."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
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
        """Request a reservation. Returns ``(granted, reason, granted_usd)``.

        - If the bot already has a reservation, the request is treated as
          an UPDATE (the new usd_amount replaces the old).
        - If the resulting sum-of-reservations exceeds the wallet pool,
          the request is REFUSED OUTRIGHT (operator-locked Q3 — no
          partial grant, no warn-and-confirm) and granted_usd == 0.
        - On success, granted_usd == usd_amount.
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

            # Compute the would-be total: sum of all OTHER reservations
            # on this (exchange, base) plus the new request
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
                # No wallet provider — degrade gracefully: grant the
                # reservation but log a sentinel rate so reconciliation
                # can catch the gap on first wallet query.
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

            # Grant — create or replace
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
        """Release the reservation for `bot_id`. Returns the freed USD."""
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
        """Grow an existing reservation by additional_usd. Born v3.20.72
        Phase C-1 (MEM-418) for Extractor profit-cascade prevention.

        Locked operator Q6 — "Allow overshoot only on the SAME bot
        that earned the profit; reject for other bots' requests during
        the window":

        - The bot's OWN reservation grows immediately (even if the
          wallet provider hasn't yet observed the profit settlement).
        - When OTHER bots call request_reservation() while wallet still
          lags, the over-allocation check uses the freshly-grown
          reservation totals — so a sibling can't claim the same USD.
        - When the wallet eventually catches up, the cumulative
          reservations equal the wallet (modulo lag) — no leak.

        Returns ``(success, reason, new_total_usd)``. On success,
        ``new_total_usd`` is the bot's reservation after growth.
        Failure modes:
        - bot_id unknown (no existing reservation) → False
        - additional_usd ≤ 0 → False

        Persistence callback fires on success.
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

            # Q6 same-bot-only overshoot: the bot's own profit auto-
            # grows its reservation EVEN IF the wallet provider hasn't
            # caught up yet. The settlement-lag protection comes from
            # the next sibling request_reservation, which will see the
            # full new_usd as a "claim against the wallet" — so
            # siblings can't claim against profit they didn't earn.
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
        """Update an existing reservation. Equivalent to a fresh
        ``request_reservation()`` with the cached exchange/base from
        the existing reservation. Returns ``(success, reason)``."""
        self._check_loop()
        with self._lock:
            r = self._reservations.get(bot_id)
            if r is None:
                return False, (
                    f"No existing reservation for bot {bot_id}; "
                    f"call request_reservation() instead."
                )
            # Delegate to request_reservation (which handles the cap
            # check for the new amount).
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
        """Refresh the snapshot rate on all reservations for the given
        (exchange, base). Returns count of reservations updated.
        Called by the connector/ticker pipeline when a fresh price
        arrives so reserved_base snapshots track the USD anchor."""
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
        """Returns ``(free_usd, free_base)`` for this (exchange, base).
        free = wallet_total - sum(reservations). If the wallet provider
        is unavailable, returns ``(-total_usd, -total_base)`` so the
        caller can compute free = wallet + returned (the negative is
        a sentinel that means "wallet unknown; subtract from raw")."""
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
            # No rate — only USD is meaningful
            return free_usd, 0.0

    def reconcile_with_exchange(
        self,
        *,
        exchange_id: str,
        base_currency: str,
        exchange_balance_base: float,
        current_rate_usd_per_base: float,
    ) -> dict:
        """Compare the registry's view of (exchange, base) against the
        live exchange balance. Refreshes the snapshot rate on the
        relevant reservations and returns a drift report:

        ``{wallet_base, wallet_usd, reserved_usd, reserved_base,
        free_usd, free_base, drift_usd, drift_pct}``

        Phase D will invoke this periodically (every 5 min per the
        operator-locked Q1 cadence) and emit operator notifications
        when drift_pct exceeds the operator-tuned threshold.
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
        """Snapshot list of reservations (optionally filtered). Used
        by the GUI registry table in Phase D."""
        self._check_loop()
        with self._lock:
            base = (base_currency or "").upper() if base_currency else None
            result = []
            for r in self._reservations.values():
                if exchange_id is not None and r.exchange_id != exchange_id:
                    continue
                if base is not None and r.base_currency != base:
                    continue
                # Shallow copy to avoid external mutation
                result.append(Reservation(**asdict(r)))
            return result

    def serialize(self) -> dict:
        """Serializable snapshot for settings.json persistence."""
        with self._lock:
            return {_SETTINGS_KEY: [r.to_dict() for r in self._reservations.values()]}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _wallet_usd(
        self,
        exchange_id: str,
        base_currency: str,
        rate: Optional[float],
    ) -> Optional[float]:
        """Convert wallet base balance to USD using the provider + rate.
        Returns None if the provider is unavailable or the rate is
        missing for a non-USD-like base."""
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
        """Invoke the settings callback with the current state. Caller
        is responsible for actually writing to settings.json — we just
        hand them the dict."""
        if self._settings_callback is None:
            return
        try:
            payload = {
                _SETTINGS_KEY: [r.to_dict() for r in self._reservations.values()]
            }
            self._settings_callback(payload)
        except Exception as _pers_exc:  # noqa: BLE001 - see below
            # Persistence failure must not crash the broker; the
            # registry is in-memory authoritative and the next
            # mutation will retry persistence.
            #
            # v3.24.21 — but it must not be SILENT. In-memory
            # authoritative only holds for this process: if every
            # persist fails, the reservations are gone on restart and
            # capital the operator believes is reserved is free for
            # other bots to claim. That is the shape of the 16,523
            # orphaned reservations already cleaned up once. An
            # operator who can see this line can act on it; one who
            # cannot, cannot.
            logger.warning(
                "Capital reservation persistence FAILED (%s): %s — "
                "%d reservation(s) held in memory only and will be LOST "
                "on restart",
                type(_pers_exc).__name__,
                _pers_exc,
                len(self._reservations),
            )


# ---------------------------------------------------------------------------
# Module-level convenience for the bot lifecycle
# ---------------------------------------------------------------------------


def settings_key() -> str:
    """The canonical settings.json key for persisted reservations."""
    return _SETTINGS_KEY
