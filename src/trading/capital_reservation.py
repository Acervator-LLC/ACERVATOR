"""
capital_reservation.py — Inter-bot capital reservation registry.

OPERATOR INTENT (2026-05-23)
────────────────────────────
> "Thinking that a graceful solution for preventing overlapping
>  Scrumming Bots attempting to sell excess Base Currencies reserved
>  for Extractors could be for them to have an automatically populating
>  field that tells them how much of a given Base Currency position to
>  ignore. So if I have a $100 ETH Extractor running then this field
>  will tell the Scrumming Bot to start ignoring $100 of the ETH
>  budget. Similarly, when an Extractor Bot is created its own field
>  populates with the amount of the Base Currency being used by any
>  other bots so that there is no predation at any phase of these two
>  or future bot types predating each others' resources."

ARCHITECTURE
────────────
Each bot, before deciding what to do with an asset, consults the
registry for an "effective available" quantity — total holdings minus
all reservations placed by OTHER bots. The bot's own reservations don't
count against itself (a bot can always act within its own claim).

Reservations are stored in **asset quantity** (not USD), because USD
notional drifts with price while the underlying budget being protected
is a fixed number of asset units. The display layer converts qty → USD
at current price for human-readable presentation.

Two enforcement layers (defense in depth):
  1. **Decision-level**: bots read effective_available() during their
     position-math (e.g., ScrummingBot._delta) and decide based on
     reduced budgets.
  2. **Execution-level**: order placement (smart_orders.py) pre-flights
     against the registry before submitting to exchange. Catches races
     between decision and execution.

CRASH RECOVERY
──────────────
Each bot heartbeats to the registry periodically. If a bot stops
heartbeating for HEARTBEAT_TTL seconds, its reservations are pruned
automatically. Explicit per-reservation TTL is also supported (Extractor
can declare "I'll be done within 45 min" up front). prune_expired() runs
at the head of reserve(), so the over-commit sum never counts a dead
bot's claim; sweep_unknown_bots() drops claims whose bot id is not in the
fleet at all, which no heartbeat rule can express.

PERSISTENCE
───────────
Registry state is persisted to ~/.acervator/reservation_state.json on
every mutation. On startup, state is reloaded; pruning runs immediately
to drop reservations whose heartbeats are stale beyond the restart
grace window.

INVARIANTS (R28 FL)
───────────────────
  1. Total reservations on an asset MUST NOT exceed the bot's own
     declared holdings of that asset. Over-commit is rejected with a
     loud ValueError at reserve()/update() time.
  2. A bot cannot release another bot's reservations except via
     force_release() (operator-explicit override).
  3. The registry's view of "what's available" is authoritative for
     all bots inside the platform; the exchange-side balance is the
     ultimate truth and the reconciliation hook (separate file) handles
     drift between registry and exchange.

sadp: R26 CHR  R28 FL  R49 MDEL  R55 GOV  R62 FRG  R68 DPA  R76 DMW
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from ..core.io_utils import atomic_write_json
from typing import Optional

logger = logging.getLogger("acervator.capital_reservation")

# ─────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────

_DEFAULT_STATE_DIR = Path.home() / ".acervator"
_DEFAULT_STATE_FILE = _DEFAULT_STATE_DIR / "reservation_state.json"

# Live-tree redirect hook, mirroring TELEMETRY_ROOT_ENV / SETTINGS_ROOT_ENV
# in src/core. get_registry()'s singleton autosaves to reservation_state.json,
# so every test that resolved the singleton wrote into the operator's real
# ~/.acervator — on a clean machine (CI) it CREATED the file outright, which
# is what turned a silent leak into a red build. When this env var is set, the
# state file lives under it instead. Resolved at call time (never frozen at
# import) so tests/conftest.py can point it at a tmp dir after this module is
# already imported. The default path constant above is kept unchanged for the
# tests that assert on its shape.
RESERVATION_ROOT_ENV = "ACERVATOR_RESERVATION_ROOT"


def _resolve_state_file() -> Path:
    """The reservation-state path, honoring the redirect override."""
    override = os.environ.get(RESERVATION_ROOT_ENV)
    if override:
        return Path(override) / "reservation_state.json"
    return _DEFAULT_STATE_FILE


# Heartbeat: bot pings every HEARTBEAT_INTERVAL; if no ping in
# HEARTBEAT_TTL the bot's reservations are pruned as zombie.
HEARTBEAT_INTERVAL = 30.0  # seconds between pings (advisory)
HEARTBEAT_TTL = 120.0  # 4 missed pings = zombie

# Restart grace: after a fresh process start, give all bots this long
# to re-establish heartbeats before pruning zombies. Otherwise the
# first prune_expired() call after startup would nuke everything.
RESTART_GRACE_SECONDS = 60.0


# ─────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────


@dataclass
class Reservation:
    """A single capital reservation entry.

    Fields:
      token:        unique UUID — bots track their own reservations
                    via the token returned from reserve(); release()
                    requires the token to prevent cross-bot interference.
      bot_id:       the bot holding this reservation.
      asset:        symbol (e.g., "ETH", "BTC"). Case-sensitive — match
                    the exchange's casing.
      qty:          asset units reserved. Always positive.
      reason:       human-readable rationale (audit trail).
      reserved_at:  epoch seconds when reserve() was called.
      expires_at:   optional epoch seconds — if set, reservation is
                    auto-released after this time. None = no explicit
                    TTL, relies on heartbeat liveness only.
      bot_kind:     "scrumming" | "extractor" | "manual" | <other> —
                    advisory categorization for the dashboard.
    """

    token: str
    bot_id: str
    asset: str
    qty: float
    reason: str
    reserved_at: float
    expires_at: Optional[float] = None
    bot_kind: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Reservation":
        # Filter to known fields — defensive against schema drift.
        # Same pattern as RuleEntry.from_dict (MEM-335 / v3.19.56).
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    def is_expired(self, now: float) -> bool:
        """True if this reservation's explicit TTL has passed.
        Heartbeat liveness is checked separately at the registry level."""
        return self.expires_at is not None and now >= self.expires_at


# ─────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────


class CapitalReservationRegistry:
    """Single source of truth for inter-bot capital reservations.

    Thread-safe via a single registry-level lock. Reservation grants
    and queries are short, so contention should be negligible.

    Typical usage:

        registry = CapitalReservationRegistry()

        # Extractor on start:
        token = registry.reserve(
            bot_id="extractor_001",
            asset="ETH",
            qty=0.0410,                       # 0.0410 ETH ≈ $100 at $2438
            reason="Staged $100 ETH extraction",
            bot_kind="extractor",
            ttl_seconds=2700,                 # 45 min budget
        )

        # ScrummingBot every tick:
        eff = registry.effective_available(
            asset="ETH",
            bot_id="scrumming_eth_usdt",
            total_holdings=current_eth_qty,
        )
        delta = eff * price - target

        # Extractor on completion:
        registry.release(token)
    """

    def __init__(
        self,
        state_path: Optional[Path] = None,
        autosave: bool = True,
        restart_grace_seconds: float = RESTART_GRACE_SECONDS,
    ):
        """
        Args:
            state_path: where to persist the reservation table.
                Defaults to ~/.acervator/reservation_state.json.
                Pass an explicit path in tests so the helper never
                touches the production state file. Same pattern as
                v3.19.57 RuleRegistry hotfix (MEM-336).
            autosave: persist on every mutation. Disable in tests for
                speed when persistence isn't being verified.
            restart_grace_seconds: bots get this long to heartbeat
                after registry boot before zombie-pruning fires.
        """
        self._lock = threading.Lock()
        self._state_path = (
            Path(state_path) if state_path is not None else _resolve_state_file()
        )
        self._autosave = autosave
        self._boot_time = time.time()
        self._restart_grace = restart_grace_seconds

        # Primary storage: token -> Reservation
        self._reservations: dict[str, Reservation] = {}
        # Liveness: bot_id -> last_heartbeat epoch
        self._heartbeats: dict[str, float] = {}

        # Load persisted state if file exists
        self._load()

    # ─────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────

    def _save(self):
        """Atomic write to state file. Same temp-rename pattern as
        state_manager.py."""
        if not self._autosave:
            return
        try:
            payload = {
                "version": "1.0",
                "saved_at": time.time(),
                "reservations": [r.to_dict() for r in self._reservations.values()],
                "heartbeats": self._heartbeats,
            }
            atomic_write_json(self._state_path, payload, indent=2)
        except Exception as e:
            logger.error("CapitalReservationRegistry persist failed: %s", e)
            # Don't raise — persistence failure should not break trading.
            # The in-memory state is still authoritative for the
            # running process. R28 FL: log loudly.

    def _load(self):
        """Load persisted state. Silently tolerates missing file
        (first run) and corrupt file (logged but state stays empty)."""
        if not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text())
            for d in payload.get("reservations", []):
                r = Reservation.from_dict(d)
                self._reservations[r.token] = r
            self._heartbeats = dict(payload.get("heartbeats", {}))
            logger.info(
                "CapitalReservationRegistry loaded %d reservations from %s",
                len(self._reservations),
                self._state_path,
            )
        except Exception as e:
            logger.error(
                "CapitalReservationRegistry load failed (%s): %s — "
                "starting with empty state. Operator should inspect "
                "the file for manual recovery.",
                self._state_path,
                e,
            )

    # ─────────────────────────────────────────────────────────
    # Core API: reserve / release / update
    # ─────────────────────────────────────────────────────────

    def reserve(
        self,
        bot_id: str,
        asset: str,
        qty: float,
        reason: str,
        bot_kind: str = "unknown",
        ttl_seconds: Optional[float] = None,
        total_holdings: Optional[float] = None,
    ) -> str:
        """Place a reservation. Returns a unique token used to
        release/update the reservation later.

        Args:
            bot_id:         caller's bot identifier.
            asset:          asset symbol (e.g., "ETH").
            qty:            asset units to reserve. Must be > 0.
            reason:         human-readable rationale (audit trail).
            bot_kind:       "scrumming" | "extractor" | etc.
            ttl_seconds:    optional explicit TTL. If set, the
                            reservation auto-releases this many seconds
                            after creation. None = relies on heartbeat
                            liveness.
            total_holdings: optional. If provided, the registry
                            validates that the new reservation + all
                            existing reservations on this asset
                            (across all bots) does not exceed
                            total_holdings. Raises ValueError on
                            over-commit (R28 FL).

        Returns:
            token (str) — pass to release() or update() to refer back.

        Raises:
            ValueError on qty <= 0 or over-commit.
        """
        if qty <= 0:
            raise ValueError(f"reserve: qty must be > 0, got {qty}")
        if not asset:
            raise ValueError("reserve: asset symbol required")
        if not bot_id:
            raise ValueError("reserve: bot_id required")

        # The over-commit sum below counts every reservation on the asset,
        # including those of bots that stopped heartbeating. Collect them
        # first or a dead bot's claim refuses a live bot's forever.
        self.prune_expired()

        with self._lock:
            # Over-commit check (R28 FL — fail loudly)
            if total_holdings is not None:
                existing = sum(
                    r.qty for r in self._reservations.values() if r.asset == asset
                )
                if existing + qty > total_holdings + 1e-12:
                    raise ValueError(
                        f"reserve: over-commit on {asset} — "
                        f"existing reservations {existing:.10g} + "
                        f"requested {qty:.10g} > total holdings "
                        f"{total_holdings:.10g}. "
                        f"Release stale reservations or reduce request."
                    )

            token = uuid.uuid4().hex
            now = time.time()
            r = Reservation(
                token=token,
                bot_id=bot_id,
                asset=asset,
                qty=qty,
                reason=reason,
                reserved_at=now,
                expires_at=(now + ttl_seconds) if ttl_seconds else None,
                bot_kind=bot_kind,
            )
            self._reservations[token] = r
            # Implicit heartbeat — reserving is proof of life
            self._heartbeats[bot_id] = now
            self._save()
            logger.info(
                "CRR.reserve: %s reserved %.10g %s (token %s, reason=%r)",
                bot_id,
                qty,
                asset,
                token[:8],
                reason,
            )
            return token

    def release(self, token: str, bot_id: str) -> bool:
        """Release a reservation. The bot_id must match the
        reservation's owner (R28 FL — no cross-bot release).

        Returns True if released, False if token unknown.
        Raises ValueError if token exists but bot_id mismatches.
        """
        with self._lock:
            r = self._reservations.get(token)
            if r is None:
                return False
            if r.bot_id != bot_id:
                raise ValueError(
                    f"release: token {token[:8]} owned by {r.bot_id!r}, "
                    f"not {bot_id!r}. Use force_release() for operator "
                    f"override."
                )
            del self._reservations[token]
            self._heartbeats[bot_id] = time.time()
            self._save()
            logger.info(
                "CRR.release: %s released %s (%.10g %s)",
                bot_id,
                token[:8],
                r.qty,
                r.asset,
            )
            return True

    def release_for(self, bot_id: str, asset: Optional[str] = None) -> int:
        """Release every reservation held by ``bot_id``, optionally narrowed
        to one asset, addressing them by ownership rather than by token.

        ``reserve()`` raises before it returns a token, so a caller whose
        reserve failed holds no handle to what it may have created. This is
        the only way to reach such a reservation. Returns the count released.
        """
        if not bot_id:
            return 0
        with self._lock:
            doomed = [
                t
                for t, r in self._reservations.items()
                if r.bot_id == bot_id and (asset is None or r.asset == asset)
            ]
            if not doomed:
                return 0
            for t in doomed:
                r = self._reservations.pop(t)
                logger.info(
                    "CRR.release_for: %s released %s (%.10g %s) by ownership",
                    bot_id,
                    t[:8],
                    r.qty,
                    r.asset,
                )
            self._heartbeats[bot_id] = time.time()
            self._save()
            return len(doomed)

    def update(
        self,
        token: str,
        bot_id: str,
        new_qty: float,
        total_holdings: Optional[float] = None,
    ) -> bool:
        """Adjust an existing reservation's quantity. Used by
        Extractor as it consumes its budget in slices.

        Returns True if updated, False if token unknown.
        Raises ValueError on cross-bot update, over-commit, or
        non-positive qty.
        """
        if new_qty <= 0:
            # Treat as a release — calling update with 0 should not
            # leave a zero-qty zombie in the table.
            raise ValueError(
                f"update: new_qty must be > 0 (got {new_qty}); "
                f"call release() to drop the reservation instead."
            )
        with self._lock:
            r = self._reservations.get(token)
            if r is None:
                return False
            if r.bot_id != bot_id:
                raise ValueError(
                    f"update: token {token[:8]} owned by {r.bot_id!r}, "
                    f"not {bot_id!r}."
                )
            # Over-commit check excludes the reservation being updated
            if total_holdings is not None:
                existing = sum(
                    rr.qty
                    for rr in self._reservations.values()
                    if rr.asset == r.asset and rr.token != token
                )
                if existing + new_qty > total_holdings + 1e-12:
                    raise ValueError(
                        f"update: over-commit on {r.asset} — "
                        f"other reservations {existing:.10g} + new "
                        f"{new_qty:.10g} > total holdings "
                        f"{total_holdings:.10g}."
                    )
            old_qty = r.qty
            r.qty = new_qty
            self._heartbeats[bot_id] = time.time()
            self._save()
            logger.info(
                "CRR.update: %s adjusted %s on %s from %.10g to %.10g",
                bot_id,
                token[:8],
                r.asset,
                old_qty,
                new_qty,
            )
            return True

    def force_release(self, token: str, operator_note: str = "") -> bool:
        """Operator-explicit override — release a reservation regardless
        of owning bot_id. Logs at WARNING level for audit visibility.

        Returns True if released, False if token unknown.
        """
        with self._lock:
            r = self._reservations.get(token)
            if r is None:
                return False
            del self._reservations[token]
            self._save()
            logger.warning(
                "CRR.force_release: OPERATOR override — released %s "
                "(was %s/%.10g %s). Note: %r",
                token[:8],
                r.bot_id,
                r.qty,
                r.asset,
                operator_note,
            )
            return True

    def force_release_all(self, bot_id: str, operator_note: str = "") -> int:
        """Operator-explicit override — release every reservation held
        by bot_id. Useful when a bot has crashed and isn't coming back.
        Returns count of reservations released.
        """
        with self._lock:
            to_release = [
                t for t, r in self._reservations.items() if r.bot_id == bot_id
            ]
            for t in to_release:
                del self._reservations[t]
            # Also drop the bot's heartbeat so it doesn't linger
            self._heartbeats.pop(bot_id, None)
            if to_release:
                self._save()
                logger.warning(
                    "CRR.force_release_all: OPERATOR override — released "
                    "%d reservations held by %s. Note: %r",
                    len(to_release),
                    bot_id,
                    operator_note,
                )
            return len(to_release)

    def sweep_unknown_bots(self, known_bot_ids, note: str = "") -> list[Reservation]:
        """Drop every reservation, and every heartbeat, whose ``bot_id`` is
        absent from ``known_bot_ids``.

        A bot id outside the fleet has no owner that can release it, and the
        persisted table is inherited by every launch. An empty or non-iterable
        fleet is refused with an empty result: sweeping against a fleet that
        failed to load would drop live bots' claims. Returns what was dropped.
        """
        try:
            known = {str(b) for b in known_bot_ids}
        except TypeError:
            logger.error(
                "CRR.sweep_unknown_bots: known_bot_ids is not iterable (%s); "
                "refusing to sweep.",
                type(known_bot_ids).__name__,
            )
            return []
        if not known:
            logger.warning(
                "CRR.sweep_unknown_bots: empty fleet supplied; refusing to "
                "sweep so a failed fleet load cannot drop live claims."
            )
            return []
        with self._lock:
            dropped = [r for r in self._reservations.values() if r.bot_id not in known]
            for r in dropped:
                del self._reservations[r.token]
            stale_beats = [b for b in self._heartbeats if b not in known]
            for b in stale_beats:
                del self._heartbeats[b]
            if dropped or stale_beats:
                self._save()
                logger.warning(
                    "CRR.sweep_unknown_bots: dropped %d reservation(s) and %d "
                    "heartbeat(s) held by bot ids outside the %d-bot fleet. "
                    "Note: %r",
                    len(dropped),
                    len(stale_beats),
                    len(known),
                    note,
                )
            return dropped

    # ─────────────────────────────────────────────────────────
    # Query API
    # ─────────────────────────────────────────────────────────

    def effective_available(
        self, asset: str, bot_id: str, total_holdings: float
    ) -> float:
        """The core query: how much of this asset is bot_id allowed
        to consider available?

        Returns total_holdings minus the sum of all OTHER bots'
        reservations on this asset. The querying bot's own reservations
        do NOT subtract (a bot can always act inside its own claim).

        Never returns negative — if reservations exceed holdings (which
        should be prevented at reserve-time but defended here), clamps
        to 0 with a logged warning.
        """
        with self._lock:
            others_reserved = sum(
                r.qty
                for r in self._reservations.values()
                if r.asset == asset and r.bot_id != bot_id
            )
            effective = total_holdings - others_reserved
            if effective < 0:
                # R28 FL — log loudly. Over-reservation should have
                # been caught at reserve-time; if we're here, the
                # invariant is broken.
                logger.error(
                    "CRR.effective_available: %s on %s — others reserved "
                    "%.10g > total_holdings %.10g. Clamping to 0. "
                    "Investigate: registry state may be inconsistent with "
                    "exchange balance.",
                    bot_id,
                    asset,
                    others_reserved,
                    total_holdings,
                )
                return 0.0
            return effective

    def reservations_for(
        self,
        asset: Optional[str] = None,
        bot_id: Optional[str] = None,
        excluding_bot_id: Optional[str] = None,
    ) -> list[Reservation]:
        """Inspect current reservations. Filters are AND-combined.

        Args:
            asset:            if set, only reservations on this asset.
            bot_id:           if set, only reservations BY this bot.
            excluding_bot_id: if set, exclude reservations by this bot.

        Returns list of Reservation objects (copies — caller can mutate
        without affecting the registry).
        """
        with self._lock:
            out = []
            for r in self._reservations.values():
                if asset is not None and r.asset != asset:
                    continue
                if bot_id is not None and r.bot_id != bot_id:
                    continue
                if excluding_bot_id is not None and r.bot_id == excluding_bot_id:
                    continue
                # Return a copy so caller can't mutate the registry
                # by accident
                out.append(Reservation.from_dict(r.to_dict()))
            return out

    def snapshot(self) -> dict:
        """Full audit-friendly view of the registry. Returns:

            {
                "reservations": [{...}, ...],  # all current reservations
                "heartbeats":   {bot_id: epoch, ...},
                "total_by_asset": {"ETH": 0.123, "BTC": 0.001, ...},
                "now": epoch,
            }

        For dashboard / Mini Display / Settings tab display.
        """
        with self._lock:
            now = time.time()
            total_by_asset: dict[str, float] = {}
            for r in self._reservations.values():
                total_by_asset[r.asset] = total_by_asset.get(r.asset, 0.0) + r.qty
            return {
                "reservations": [r.to_dict() for r in self._reservations.values()],
                "heartbeats": dict(self._heartbeats),
                "total_by_asset": total_by_asset,
                "now": now,
            }

    # ─────────────────────────────────────────────────────────
    # Heartbeat + zombie pruning (next step in cascade)
    # ─────────────────────────────────────────────────────────

    def heartbeat(self, bot_id: str):
        """Record that bot_id is alive at this moment. Bots should
        call this on a timer (HEARTBEAT_INTERVAL recommended)."""
        with self._lock:
            self._heartbeats[bot_id] = time.time()
            # Note: NOT autosaved on each heartbeat — would be too much
            # disk churn. Heartbeats are recovered from in-memory state
            # on restart's grace period; if the process dies, the next
            # boot's grace window covers the freshly-restarted bots'
            # heartbeats anyway.

    def prune_expired(self, now: Optional[float] = None) -> list[Reservation]:
        """Drop reservations whose explicit TTL has passed OR whose
        bot has stopped heartbeating for > HEARTBEAT_TTL seconds.

        Within the restart grace window (first RESTART_GRACE_SECONDS
        after registry boot), heartbeat-staleness is NOT enforced —
        gives all bots time to re-establish heartbeats after an app
        restart.

        Returns list of pruned Reservation objects for audit logging.
        """
        if now is None:
            now = time.time()
        within_grace = (now - self._boot_time) < self._restart_grace

        with self._lock:
            pruned: list[Reservation] = []
            for token, r in list(self._reservations.items()):
                drop = False
                drop_reason = ""

                # Explicit TTL expiry — always enforced
                if r.is_expired(now):
                    drop = True
                    drop_reason = f"explicit TTL expired at {r.expires_at}"

                # Heartbeat staleness — only enforced post-grace
                elif not within_grace:
                    last_hb = self._heartbeats.get(r.bot_id, r.reserved_at)
                    silence = now - last_hb
                    if silence > HEARTBEAT_TTL:
                        drop = True
                        drop_reason = (
                            f"heartbeat stale by {silence:.1f}s "
                            f"(TTL {HEARTBEAT_TTL}s)"
                        )

                if drop:
                    del self._reservations[token]
                    pruned.append(r)
                    logger.warning(
                        "CRR.prune_expired: dropped %s/%.10g %s by %s — %s",
                        token[:8],
                        r.qty,
                        r.asset,
                        r.bot_id,
                        drop_reason,
                    )

            if pruned:
                self._save()
            return pruned

    # ─────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────

    def reset(self):
        """Clear all reservations and heartbeats. Used in tests +
        operator-explicit nuke. Persists the empty state."""
        with self._lock:
            self._reservations.clear()
            self._heartbeats.clear()
            self._save()
            logger.warning("CRR.reset: all reservations cleared.")


# ─────────────────────────────────────────────────────────────────
# Module-level singleton (lazy-initialized)
# ─────────────────────────────────────────────────────────────────

_global_registry: Optional[CapitalReservationRegistry] = None


def get_registry() -> CapitalReservationRegistry:
    """Return the module-level singleton registry. Bots use this
    rather than constructing their own instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = CapitalReservationRegistry()
    return _global_registry


def set_registry(reg: CapitalReservationRegistry):
    """Inject a registry (for tests). Use sparingly."""
    global _global_registry
    _global_registry = reg
