"""Inter-bot capital reservation registry.

``CapitalReservationRegistry.effective_available`` returns holdings minus every
other bot's ``Reservation`` on the same asset, excluding the caller's own.
``reserve``, ``update`` and ``release`` take quantities in asset units.
``prune_expired`` drops a ``Reservation`` past its ``expires_at`` or past
``HEARTBEAT_TTL`` of silence, and ``sweep_unknown_bots`` drops one whose
``bot_id`` is outside the fleet it is given. ``effective_available`` and
``heartbeat`` run ``_prune_on_schedule`` first, so a dead bot's claim expires
on ``HEARTBEAT_INTERVAL`` rather than waiting for a sibling to reserve.
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

_DEFAULT_STATE_DIR = Path.home() / ".acervator"
_DEFAULT_STATE_FILE = _DEFAULT_STATE_DIR / "reservation_state.json"

# Read by _resolve_state_file at call time, never frozen at import.
RESERVATION_ROOT_ENV = "ACERVATOR_RESERVATION_ROOT"


def _resolve_state_file() -> Path:
    """Return ``RESERVATION_ROOT_ENV``/reservation_state.json, else
    ``_DEFAULT_STATE_FILE``."""
    override = os.environ.get(RESERVATION_ROOT_ENV)
    if override:
        return Path(override) / "reservation_state.json"
    return _DEFAULT_STATE_FILE


# _prune_on_schedule reads HEARTBEAT_INTERVAL; no operator setting changes it.
HEARTBEAT_INTERVAL = 30.0
HEARTBEAT_TTL = 120.0

# Without it, the first prune_expired() after a restart drops every claim.
RESTART_GRACE_SECONDS = 60.0


@dataclass
class Reservation:
    """One ``bot_id``'s claim on ``qty`` units of ``asset``.

    ``asset`` is compared as an exact string. ``reason`` and ``bot_kind`` are
    logged and read by nothing.
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
        # Unknown keys are dropped; a state file from an older schema loads.
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    def is_expired(self, now: float) -> bool:
        """Report whether ``expires_at`` has passed.

        ``prune_expired`` applies heartbeat staleness separately.
        """
        return self.expires_at is not None and now >= self.expires_at


class CapitalReservationRegistry:
    """Single source of truth for inter-bot capital reservations.

    Every method holds one registry-level lock. ``reserve`` returns a token
    that ``release`` and ``update`` require alongside the owning ``bot_id``,
    while ``release_for`` addresses a ``Reservation`` by ``bot_id`` alone.
    """

    def __init__(
        self,
        state_path: Optional[Path] = None,
        autosave: bool = True,
        restart_grace_seconds: float = RESTART_GRACE_SECONDS,
    ):
        """Construct the registry and run ``_load``.

        Args:
            state_path: persistence target, defaulting to ``_resolve_state_file``.
            autosave: when False, ``_save`` writes nothing.
            restart_grace_seconds: seconds after construction during which
                ``prune_expired`` ignores heartbeat staleness.
        """
        self._lock = threading.Lock()
        self._state_path = (
            Path(state_path) if state_path is not None else _resolve_state_file()
        )
        self._autosave = autosave
        self._boot_time = time.time()
        self._restart_grace = restart_grace_seconds

        self._reservations: dict[str, Reservation] = {}
        # bot_id -> last heartbeat, in epoch seconds.
        self._heartbeats: dict[str, float] = {}
        self._last_prune = self._boot_time
        self._unpersisted = 0

        self._load()

    def _save(self) -> bool:
        """Write ``_reservations`` and ``_heartbeats`` to ``_state_path``.

        Returns False only when a write was attempted and failed, leaving the
        table in memory alone and ``_unpersisted`` counting the lost changes.
        Writes nothing, and returns True, when ``_autosave`` is False.
        """
        if not self._autosave:
            return True
        try:
            payload = {
                "version": "1.0",
                "saved_at": time.time(),
                "reservations": [r.to_dict() for r in self._reservations.values()],
                "heartbeats": self._heartbeats,
            }
            atomic_write_json(self._state_path, payload, indent=2)
        except Exception as e:
            self._unpersisted += 1
            logger.error(
                "CapitalReservationRegistry persist failed (%s): %s — the "
                "table is in memory only. %d change(s) are not on disk: a "
                "restart loses them, and no other reader of %s can see them.",
                self._state_path,
                e,
                self._unpersisted,
                self._state_path.name,
            )
            # A failed write never raises; _reservations stays authoritative.
            return False
        self._unpersisted = 0
        return True

    def _load(self):
        """Read ``_state_path`` into ``_reservations`` and ``_heartbeats``.

        A missing file returns silently; a corrupt one is logged and leaves
        both empty.
        """
        if not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
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
                "CapitalReservationRegistry load failed (%s) (%s: %s) — "
                "starting with empty state. This is NOT the same as a file "
                "holding no claims: every other bot's claim on every asset "
                "now reads as 0, so effective_available returns the caller's "
                "whole holding and no sell is bounded by a sibling. Operator "
                "should inspect the file for manual recovery.",
                self._state_path,
                type(e).__name__,
                e,
            )

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
        """Store a ``Reservation`` and return its token.

        Args:
            bot_id:         owner recorded on the ``Reservation``.
            asset:          asset symbol, matched by exact string.
            qty:            asset units, greater than 0.
            reason:         audit text, logged only.
            bot_kind:       "scrumming" or "extractor", logged only.
            ttl_seconds:    when set, fixes ``expires_at`` this far ahead.
            total_holdings: when set, caps this ``qty`` plus every existing
                            ``Reservation`` on ``asset``.

        Returns:
            The token ``release`` and ``update`` require.

        Raises:
            ValueError: ``qty`` is not positive, or the cap is exceeded.
        """
        if qty <= 0:
            raise ValueError(f"reserve: qty must be > 0, got {qty}")
        if not asset:
            raise ValueError("reserve: asset symbol required")
        if not bot_id:
            raise ValueError("reserve: bot_id required")

        # Prune first: the sum below counts a dead bot's Reservation too.
        self.prune_expired()

        with self._lock:
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
            self._heartbeats[bot_id] = now
            persisted = self._save()
            logger.log(
                logging.INFO if persisted else logging.ERROR,
                "CRR.reserve: %s reserved %.10g %s (token %s, on_disk=%s, "
                "reason=%r)",
                bot_id,
                qty,
                asset,
                token[:8],
                persisted,
                reason,
            )
            return token

    def release(self, token: str, bot_id: str) -> bool:
        """Drop the ``Reservation`` at ``token``, returning False when unknown.

        Raises ValueError when ``bot_id`` is not the recorded owner.
        """
        with self._lock:
            r = self._reservations.get(token)
            if r is None:
                return False
            if r.bot_id != bot_id:
                raise ValueError(
                    f"release: token {token[:8]} owned by {r.bot_id!r}, "
                    f"not {bot_id!r}. Only the owner releases a claim."
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
        """Drop every ``Reservation`` owned by ``bot_id``, narrowed to ``asset``
        when one is given.

        Returns the count dropped, and 0 for an empty ``bot_id``.
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
        """Set the ``qty`` of the ``Reservation`` at ``token`` to ``new_qty``.

        Returns False when ``token`` is unknown, and raises ValueError on a
        foreign ``bot_id``, a non-positive ``new_qty``, or a breached
        ``total_holdings``.
        """
        if new_qty <= 0:
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

    def sweep_unknown_bots(self, known_bot_ids, note: str = "") -> list[Reservation]:
        """Drop every ``Reservation``, and every heartbeat, whose ``bot_id`` is
        absent from ``known_bot_ids``.

        Returns the dropped ``Reservation`` list, empty when ``known_bot_ids``
        is empty or not iterable.
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

    def _prune_on_schedule(self) -> None:
        """Run ``prune_expired`` once ``HEARTBEAT_INTERVAL`` has passed.

        Takes no lock of its own: ``prune_expired`` takes it, so every caller
        must be outside the lock.
        """
        if (time.time() - self._last_prune) >= HEARTBEAT_INTERVAL:
            self.prune_expired()

    def effective_available(
        self, asset: str, bot_id: str, total_holdings: float
    ) -> float:
        """Return ``total_holdings`` minus every ``Reservation`` on ``asset``
        whose owner is not ``bot_id``.

        Runs ``_prune_on_schedule`` first, so a dead owner's claim does not
        bound this caller. A negative result is logged at ERROR and clamped
        to 0.0.
        """
        self._prune_on_schedule()
        with self._lock:
            others_reserved = sum(
                r.qty
                for r in self._reservations.values()
                if r.asset == asset and r.bot_id != bot_id
            )
            effective = total_holdings - others_reserved
            if effective < 0:
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
        """Return copied ``Reservation`` objects matching every filter given.

        Args:
            asset:            keep only this ``asset``.
            bot_id:           keep only this owner.
            excluding_bot_id: drop this owner.
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
                out.append(Reservation.from_dict(r.to_dict()))
            return out

    def heartbeat(self, bot_id: str):
        """Stamp ``bot_id`` in ``_heartbeats`` with the current epoch.

        Stamps before ``_prune_on_schedule`` so a live caller never prunes
        its own claim.
        """
        with self._lock:
            self._heartbeats[bot_id] = time.time()
            # Not persisted here; the next _save call writes _heartbeats.
        self._prune_on_schedule()

    def prune_expired(self, now: Optional[float] = None) -> list[Reservation]:
        """Drop each ``Reservation`` past ``is_expired``, or whose owner has
        been silent longer than ``HEARTBEAT_TTL``.

        Silence is ignored for ``_restart_grace`` seconds after construction,
        and the dropped objects are returned. Stamps ``_last_prune``, which
        is what ``_prune_on_schedule`` measures its interval from.
        """
        if now is None:
            now = time.time()
        within_grace = (now - self._boot_time) < self._restart_grace
        self._last_prune = time.time()

        with self._lock:
            pruned: list[Reservation] = []
            for token, r in list(self._reservations.items()):
                drop = False
                drop_reason = ""

                if r.is_expired(now):
                    drop = True
                    drop_reason = f"explicit TTL expired at {r.expires_at}"

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

    def reset(self):
        """Empty ``_reservations`` and ``_heartbeats``, then ``_save``."""
        with self._lock:
            self._reservations.clear()
            self._heartbeats.clear()
            self._save()
            logger.warning("CRR.reset: all reservations cleared.")


_global_registry: Optional[CapitalReservationRegistry] = None


def get_registry() -> CapitalReservationRegistry:
    """Return the shared ``CapitalReservationRegistry``, constructing it once."""
    global _global_registry
    if _global_registry is None:
        _global_registry = CapitalReservationRegistry()
    return _global_registry


def set_registry(reg: CapitalReservationRegistry):
    """Replace what ``get_registry`` returns with ``reg``."""
    global _global_registry
    _global_registry = reg
