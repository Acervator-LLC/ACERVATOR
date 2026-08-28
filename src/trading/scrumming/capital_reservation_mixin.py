"""Capital-reservation wiring for ScrummingBot.

Reserves the bot's buy-side capital with the CapitalReservationRegistry so
concurrent bots cannot double-spend the same shared wallet. ``_crr`` is the
registry accessor; the ensure/release pair drive the reservation lifecycle.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("acervator.scrumming")


class CapitalReservationMixin:

    # Supplied by ScrummingBot at runtime; declared so a type
    # checker can resolve them. Annotations only: no attribute is
    # created and the runtime base stays `object`.
    _capital_registry: Any
    _crr_last_reserved_qty: float
    _crr_token: Optional[str]
    _target_balance: Any
    bot_id: Any
    config: Any
    _get_cached_exchange_balance: Callable[..., Awaitable[Optional[float]]]

    def _crr(self):
        """The capital-reservation registry this bot should use.

        Injected instance when one was supplied (sim fleets get a
        private, non-persisting registry); the process-wide singleton
        otherwise. None only if the module cannot be imported.
        """
        if self._capital_registry is not None:
            return self._capital_registry
        # A sim bot with no injected registry must not resolve the
        # process-wide singleton — it persists to the operator's live
        # reservation_state.json. Return None (fail-closed) so reservation
        # is refused rather than performed against live state.
        if getattr(self, "_sim_mode", False):
            logger.warning(
                "Bot %s is in sim mode with no injected capital registry; "
                "refusing to resolve the process-wide registry, which "
                "persists to the operator's reservation_state.json. "
                "Reservation is unavailable for this bot.",
                self.bot_id,
            )
            return None
        try:
            from ..capital_reservation import get_registry as _crr_get_registry

            return _crr_get_registry()
        except ImportError as exc:
            logger.debug("capital registry unavailable: %s", exc)
            return None

    def _compute_reservation_qty(self, current_price: float) -> float:
        """Target-asset units this bot should claim in the registry.

        Formula: ``target_balance_USD / (current_price × quote_to_usd)``
        (with a 10 % safety margin so tick-to-tick price drift doesn't
        leave us under-reserved) plus ``personal_hold_qty``
        (operator-declared units this bot keeps out of both its own
        math AND other bots' reach).

        Multiplying by ``_quote_to_usd`` gives USD-per-target-asset, the
        correct denominator for a USD-denominated target on non-USD-quoted
        pairs (e.g. ETH/BTC, where ``current_price`` is BTC-per-ETH).
        """
        if current_price <= 0:
            return 0.0
        try:
            _target = float(self._target_balance or 0)
        except (TypeError, ValueError):
            _target = 0.0
        try:
            _hold = float(getattr(self.config, "personal_hold_qty", 0.0) or 0.0)
        except (TypeError, ValueError):
            _hold = 0.0
        _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
        if _qrate <= 0:
            _qrate = 1.0
        _usd_per_asset = current_price * _qrate
        if _usd_per_asset <= 0:
            return 0.0
        _base_units = (_target / _usd_per_asset) if _target > 0 else 0.0
        return _base_units * 1.10 + max(0.0, _hold)

    async def _ensure_capital_reservation(self, current_price: float) -> None:
        """Idempotent: reserve on first eligible call, update on
        subsequent calls, always heartbeat.

        No-ops when self_reserve_capital is disabled or price is
        unavailable. Failures log at WARNING and clear the token so the
        next tick retries. Never raises into the tick path. Async so it can
        pass ``total_holdings`` (from the balance cache) into
        ``reserve()`` / ``update()``, which the registry's over-commit
        check needs. Sim isolation comes from the bot holding a private
        registry, not from skipping this path.
        """
        if not bool(getattr(self.config, "self_reserve_capital", True)):
            return
        if current_price is None or current_price <= 0:
            return
        _asset = str(getattr(self.config, "target_asset", "") or "").upper()
        if not _asset:
            return
        _qty = self._compute_reservation_qty(current_price)
        if _qty <= 0:
            return
        _total_holdings = await self._get_cached_exchange_balance(_asset)

        # A sim bot's first reserve passes holdings=None: sim inventory is
        # seeded at exactly target/open_px, so the 110% claim would fail
        # over-commit on a private registry that isn't guarding a shared
        # live balance. Subsequent updates still pass holdings, so drift is
        # still caught.
        if getattr(self, "_sim_mode", False) and self._crr_token is None:
            _total_holdings = None
        try:
            _crr_reg = self._crr()
            if _crr_reg is None:
                return
            if self._crr_token is None:
                # No token means this bot believes it holds nothing. A
                # reservation still standing in its name is unreachable by
                # token, and the over-commit sum would count it against the
                # claim about to be made.
                _crr_reg.release_for(self.bot_id, _asset)
            if _total_holdings is not None:
                # Claim what this bot needs, bounded by what no other bot has
                # claimed. Capping at the whole balance instead left nothing
                # for a co-tenant Extractor on the same asset, which is the
                # sharing this registry exists to arbitrate. Skipped when
                # holdings are unknown so a transient fetch failure cannot
                # shrink a live claim.
                _others_reserved = sum(
                    r.qty
                    for r in _crr_reg.reservations_for(
                        asset=_asset, excluding_bot_id=self.bot_id
                    )
                )
                _headroom = max(0.0, float(_total_holdings) - _others_reserved)
                if _qty > _headroom:
                    _qty = _headroom
                if _qty <= 0:
                    _crr_reg.heartbeat(self.bot_id)
                    logger.debug(
                        "Bot %s has no unreserved %s to claim: holdings "
                        "%.10g, other bots hold %.10g",
                        self.bot_id,
                        _asset,
                        float(_total_holdings),
                        _others_reserved,
                    )
                    return
            if self._crr_token is None:
                _reason = (
                    f"Scrumming target — "
                    f"target_balance=${self._target_balance:.2f}, "
                    f"personal_hold={float(getattr(self.config, 'personal_hold_qty', 0.0)):.10g}, "
                    f"at_price=${current_price:.8f}"
                )
                self._crr_token = _crr_reg.reserve(
                    bot_id=self.bot_id,
                    asset=_asset,
                    qty=_qty,
                    reason=_reason,
                    bot_kind="scrumming",
                    total_holdings=_total_holdings,
                )
                self._crr_last_reserved_qty = _qty
                logger.info(
                    "Bot %s reserved %.10g %s with "
                    "CapitalReservationRegistry (token %s, "
                    "total_holdings=%s)",
                    self.bot_id,
                    _qty,
                    _asset,
                    self._crr_token[:8] if self._crr_token else "?",
                    (
                        f"{_total_holdings:.10g}"
                        if _total_holdings is not None
                        else "unavailable"
                    ),
                )
            else:
                # Only push an update when qty drift > 1 %.
                if self._crr_last_reserved_qty > 0:
                    _drift = (
                        abs(_qty - self._crr_last_reserved_qty)
                        / self._crr_last_reserved_qty
                    )
                else:
                    _drift = 1.0
                if _drift > 0.01:
                    _applied = _crr_reg.update(
                        self._crr_token,
                        self.bot_id,
                        _qty,
                        total_holdings=_total_holdings,
                    )
                    if _applied:
                        self._crr_last_reserved_qty = _qty
                    else:
                        # update() returns False for a token the registry no
                        # longer holds, having pruned or swept it. Forgetting
                        # it makes the next tick reserve afresh instead of
                        # updating nothing forever.
                        logger.info(
                            "Bot %s reservation token %s is no longer in the "
                            "registry; re-reserving on the next tick",
                            self.bot_id,
                            self._crr_token[:8],
                        )
                        self._crr_token = None
                        self._crr_last_reserved_qty = 0.0
            _crr_reg.heartbeat(self.bot_id)
        except Exception as _crr_exc:  # noqa: BLE001
            logger.warning(
                "Bot %s capital-reservation ensure raised %s: %s — "
                "continuing tick; will retry next call.",
                self.bot_id,
                type(_crr_exc).__name__,
                _crr_exc,
            )
            # Release the token before clearing it. Dropping it while the
            # reservation still stands would orphan units the next
            # reserve() then counts against itself in the over-commit
            # check, refusing forever. Releasing first makes the retry a
            # real retry rather than a collision with this bot's own ghost.
            _stale = self._crr_token
            _dropped = 0
            try:
                _reg = self._crr()
                if _reg is not None:
                    if _stale is not None:
                        _reg.release(_stale, self.bot_id)
                        _dropped = 1
                        logger.info(
                            "Bot %s released stale reservation %s after "
                            "a failed ensure",
                            self.bot_id,
                            _stale[:8],
                        )
                    elif _asset:
                        # reserve() raises before it returns a token, so the
                        # token branch above cannot reach a reservation this
                        # call left standing. Ownership can, and this is the
                        # branch that runs on the failing path.
                        _dropped = _reg.release_for(self.bot_id, _asset)
                        if _dropped:
                            logger.info(
                                "Bot %s released %d untokened reservation(s) "
                                "on %s after a failed ensure",
                                self.bot_id,
                                _dropped,
                                _asset,
                            )
            except Exception as _rel_exc:  # noqa: BLE001
                logger.warning(
                    "Bot %s could not release stale reservation " "%s: %s",
                    self.bot_id,
                    _stale[:8] if _stale else _asset,
                    _rel_exc,
                )
            self._crr_token = None
            self._crr_last_reserved_qty = 0.0
            try:
                from src.core.signal_contract import emit as _cr_emit

                _cr_emit(
                    "bot.01.001.postcondition.capital_reservation",
                    actual=0.0,
                    expected=round(float(_qty), 10),
                    every=30.0,
                    context={
                        "bot_id": str(self.bot_id),
                        "asset": _asset,
                        "holdings": (
                            round(float(_total_holdings), 10)
                            if _total_holdings is not None
                            else None
                        ),
                        "error": f"{type(_crr_exc).__name__}: {_crr_exc}"[:180],
                        "released_stale": bool(_dropped),
                    },
                )
            except Exception as _sup:  # noqa: BLE001,S110
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_ensure_capital_reservation",
                    type(_sup).__name__,
                    _sup,
                )
        else:
            # Success path reports too (throttled), so a green run is
            # evidence rather than silence. ``ok`` compares the held
            # quantity (_crr_last_reserved_qty) against what this tick
            # needs (_qty): True only when a reservation is held and the
            # two sit within the 1% band the update path maintains. A held
            # quantity <= 0 is not a pass. ``ok`` is passed explicitly
            # because the two numbers are legitimately unequal inside the
            # band.
            try:
                from src.core.signal_contract import emit as _cr_ok

                _held = round(float(self._crr_last_reserved_qty), 10)
                _need = round(float(_qty), 10)
                _cr_ok(
                    "bot.01.002.postcondition.capital_reservation",
                    actual=_held,
                    expected=_need,
                    ok=bool(_held > 0.0 and abs(_need - _held) / _held <= 0.01),
                    every=60.0,
                    context={
                        "bot_id": str(self.bot_id),
                        "asset": _asset,
                        "holdings": (
                            round(float(_total_holdings), 10)
                            if _total_holdings is not None
                            else None
                        ),
                        "capped": bool(
                            _total_holdings is not None
                            and abs(_qty - float(_total_holdings)) < 1e-12
                        ),
                    },
                )
            except Exception as _sup:  # noqa: BLE001,S110
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_ensure_capital_reservation",
                    type(_sup).__name__,
                    _sup,
                )

    def _release_capital_reservation(self) -> None:
        """Release the registry token in stop() / destroy paths.
        Non-raising; the registry's own heartbeat-staleness prune is
        the backstop if this call fails."""
        if self._crr_token is None:
            return
        try:
            _crr_reg = self._crr()
            if _crr_reg is None:
                return
            _crr_reg.release(self._crr_token, self.bot_id)
            logger.info(
                "Bot %s released capital reservation %s on stop()",
                self.bot_id,
                self._crr_token[:8] if self._crr_token else "?",
            )
            self._crr_token = None
            self._crr_last_reserved_qty = 0.0
        except Exception as _crr_exc:  # noqa: BLE001
            logger.warning(
                "Bot %s capital reservation release at stop raised "
                "%s: %s — leaving for heartbeat-staleness prune.",
                self.bot_id,
                type(_crr_exc).__name__,
                _crr_exc,
            )
