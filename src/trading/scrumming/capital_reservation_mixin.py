"""Capital-reservation wiring for ScrummingBot.

``_crr`` resolves the registry this bot claims against, answering None in
sim mode with no injected ``_capital_registry``. ``_compute_reservation_qty``
sizes the claim in target-asset units, the units a later sell is checked
against. ``_ensure_capital_reservation`` places and updates that claim, and
``_release_capital_reservation`` drops it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger("acervator.scrumming")

if TYPE_CHECKING:
    from ..capital_reservation import CapitalReservationRegistry
    from ..scrumming_bot import ScrummingBot as _Host
else:
    _Host = object


class CapitalReservationMixin(_Host):
    _capital_registry: CapitalReservationRegistry | None
    _crr_token: str | None
    _crr_last_reserved_qty: float

    def _crr(self) -> CapitalReservationRegistry | None:
        """Return the registry this bot claims against.

        An injected ``_capital_registry`` wins, ``_sim_mode`` without one
        answers None, and ``_crr_get_registry`` answers otherwise.
        """
        if self._capital_registry is not None:
            return self._capital_registry
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
        """Return the target-asset units this bot claims.

        ``_target_balance`` over the product of ``current_price`` and
        ``_quote_to_usd``, scaled by 1.10, plus ``personal_hold_qty``.
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
        """Reserve on the first eligible call and update on later ones.

        Returns without claiming when ``current_price`` or ``target_asset``
        is unusable, or when ``_crr`` answers None; failures log at WARNING
        and clear ``_crr_token``. No setting turns the claim off.
        """
        if current_price is None or current_price <= 0:
            return
        _asset = str(getattr(self.config, "target_asset", "") or "").upper()
        if not _asset:
            return
        _qty = self._compute_reservation_qty(current_price)
        if _qty <= 0:
            return
        _total_holdings = await self._get_cached_exchange_balance(_asset)

        # Passing _total_holdings None skips reserve()'s over-commit check.
        if getattr(self, "_sim_mode", False) and self._crr_token is None:
            _total_holdings = None
        try:
            _crr_reg = self._crr()
            if _crr_reg is None:
                return
            if self._crr_token is None:
                # release_for clears a standing reservation no token can reach.
                _crr_reg.release_for(self.bot_id, _asset)
            if _total_holdings is not None:
                # _headroom leaves a co-tenant Extractor's claim untouched.
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
                        # update() answers False for a token the registry pruned.
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
            # Releasing before clearing keeps _stale out of the next
            # reserve()'s over-commit sum.
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
                        # reserve() raises before returning a token, so
                        # release_for is the only reach into this claim.
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
            except Exception as _sup:  # noqa: BLE001
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_ensure_capital_reservation",
                    type(_sup).__name__,
                    _sup,
                )
        else:
            # ok is explicit: _held and _need differ legitimately inside the band.
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
            except Exception as _sup:  # noqa: BLE001
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_ensure_capital_reservation",
                    type(_sup).__name__,
                    _sup,
                )

    def _release_capital_reservation(self) -> None:
        """Release ``_crr_token`` and zero ``_crr_last_reserved_qty``.

        A failure logs at WARNING and leaves ``_crr_reg`` to prune the
        reservation on heartbeat staleness.
        """
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
