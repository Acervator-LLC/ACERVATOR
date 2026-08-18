"""
src/trading/buy_safety.py — MEM-257 FAIL-CLOSED state-vs-exchange verification.

PURPOSE
───────
Lift the MEM-257 buy-safety check from `ScrummingBot._verify_buy_safe_or_refuse`
(introduced in v3.18.14, lifted to auto-fire call sites only in v3.18.15) into
a free function so the SAME check applies to the upcoming ExtractorBot's buy
sites (v3.19.x) without requiring inheritance, mixin, or per-bot duplication.

ARCHITECTURE
────────────
The original v3.18.14/v3.18.15 helper was an instance method on ScrummingBot
that read `self._main_lots` to compute the bot's expected position. That
worked when only ScrummingBot needed the check, but ExtractorBot's state
shape is different (`_positions[pair].alt_units` keyed by pair, not a
flat list of lots). Rather than carry two parallel implementations or
build a class hierarchy just for this one check, v3.18.19 parameterizes
the function on `(exchange, target_asset, expected_units, path)` and lets
each bot compute its own `expected_units` before calling.

This is the Tier-1 Q1.2 decision from the Extractor final design
consideration: option (a), "generalize the helper." Cleanest of the
three options surfaced; lowest-risk; no inheritance change.

CONTRACT
────────
Returns `(verified_units, refuse_reason)`:

  - If `refuse_reason` is non-empty: caller MUST refuse the buy and emit
    the reason to `bot.log`. `verified_units` is None in that case.
  - Otherwise: `verified_units` is the bot's verified current position
    in base-asset units (may be 0.0 for legitimately-empty positions).

Behavior matches the v3.18.14 original semantic exactly:
  1. Fetch fresh exchange balance for `target_asset`.
  2. Prefer `.total` over `.free` (catches the "BTC locked in open order
     so free=0 but total>0" case).
  3. If both report zero, cross-check `expected_units`. If the caller
     expects nonzero units while exchange shows zero — REFUSE
     (the BONK phantom-zero pattern).
  4. If both report zero AND caller expects zero — proceed with 0
     as the verified units (legitimate empty position).
  5. On any fetch exception — REFUSE (fail-closed under uncertainty).

CALLERS
───────
v3.18.19+:
  • `ScrummingBot._verify_buy_safe_or_refuse` — wraps with
    `expected_units = sum(lot["units"] for lot in self._main_lots)`.
  • `ExtractorBot._verify_buy_safe_or_refuse` (future, v3.19.1) — wraps
    with `expected_units = self._positions[pair].alt_units` for the
    pair being acted on.

The free-function form means the same regression tests pin the
identical contract for both callers; each bot only owns its
expected-units computation.

REFERENCES
──────────
  • `docs/operator_logs/INCIDENT_2026-04-23_bonk_restart_phantom_buy.md`
  • `docs/audits/2026-05-20_p0_bonk_restart_phantom_buy_investigation.md`
  • `docs/audits/2026-05-20_extractor_bot_final_design_consideration.md`
    (Tier-1 Q1.2 resolution)
  • MEM-272 (v3.18.14 P0 BONK closure)
  • MEM-273 (v3.18.15 P1 Manual Fire operator-sovereignty correction)

sadp: R28 R29 R55  # buy-safety verify: fail-loudly + idempotent + invariant-preserving
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("acervator.buy_safety")


async def verify_buy_safe_or_refuse(
    exchange: Any,
    target_asset: str,
    expected_units: float,
    *,
    path: str,
) -> tuple[Optional[float], str]:
    """MEM-257 FAIL-CLOSED — verify a buy is safe against current
    exchange state.

    Args:
        exchange: An ExchangeInterface-shaped object with
            ``async get_balance(currency) -> Balance``. Balance must
            have ``.total``, ``.free``, and ideally ``.absent`` flags
            (the latter set by Layer 1 in
            ``ccxt_connector.get_balance`` for omitted currencies).
        target_asset: Base asset being bought (e.g. ``"BONK"``,
            ``"RAVE"``, the alt portion of an Extractor's ``RAVE/ETH``
            pair).
        expected_units: Bot's internal record of how many units of
            ``target_asset`` it should currently hold. For
            ``ScrummingBot``: ``sum(lot["units"] for lot in
            self._main_lots)``. For ``ExtractorBot``: the alt_units
            of the position keyed by the pair being acted on. Pass
            ``0.0`` for a "fresh-bot, expects nothing" scenario.
        path: Caller-identifier string included in the refusal message
            so the operator can see at a glance which buy path the
            refusal came from. Examples: ``"manual_rebalance_fold"``,
            ``"cartridge_fold"``, ``"wire_stack"``, ``"fold_rebuy"``,
            ``"extractor_artillery"``, ``"extractor_correction"``.

    Returns:
        ``(verified_units, refuse_reason)``:
          * If ``refuse_reason`` is non-empty (refusal), caller MUST
            emit the reason to ``bot.log`` and refuse the buy.
            ``verified_units`` is ``None`` in this case.
          * Otherwise, ``verified_units`` is the bot's verified
            current position in ``target_asset`` units (may be
            ``0.0`` for legitimately-empty positions).

    The check semantics (unchanged from v3.18.14 / v3.18.15):
      1. Fetch ``exchange.get_balance(target_asset)``.
      2. Prefer ``.total`` (everything owned including used/locked).
         Fall back to ``.free`` if total is None/zero. This catches
         the "BTC locked in open order so free=0 but total>0" case.
      3. If both are None/zero, compare ``expected_units``. If
         ``expected_units > 0``, refuse — this is the BONK phantom-
         zero pattern (exchange lies, bot's state was right).
      4. If both are None/zero AND ``expected_units == 0``, proceed
         with verified_units = 0.0 (legitimate empty).
      5. On any fetch exception — refuse (fail-closed under
         uncertainty).
    """
    _fresh_units: Optional[float] = None
    _refuse_reason: str = ""
    try:
        _fresh_bal = await exchange.get_balance(target_asset)
        # Prefer .total over .free per MEM-257 (catches BTC locked
        # in open order). DO NOT default to 0 on None — that would
        # let a bad response pass the check.
        _t = getattr(_fresh_bal, "total", None)
        _f = getattr(_fresh_bal, "free", None)
        if _t is not None and float(_t or 0) > 0:
            _fresh_units = float(_t)
        elif _f is not None and float(_f or 0) > 0:
            _fresh_units = float(_f)
        else:
            # Both are None or 0. Cross-check against caller's expected
            # units — if the caller's local state shows real units,
            # the exchange response is suspicious (BONK-class
            # phantom-zero). REFUSE.
            if expected_units > 0:
                _refuse_reason = (
                    f"exchange reports {target_asset} total/free both 0 "
                    f"but caller's local state expects "
                    f"{expected_units:.8f} units — refusing to buy "
                    f"against a suspicious zero")
            else:
                # Legitimately empty position. Proceed with 0.
                _fresh_units = 0.0
    except Exception as _gb_exc:  # R28-OK: fail-closed downstream
        _refuse_reason = (
            f"fresh balance fetch raised "
            f"{type(_gb_exc).__name__}: {_gb_exc} "
            f"— cannot verify position, fail-closed")

    if _refuse_reason or _fresh_units is None:
        return None, (
            f"MEM-257 FAIL-CLOSED — buy REFUSED. "
            f"Path={path}. Cannot positively verify current position. "
            f"{_refuse_reason or 'fresh_units=None'}. "
            f"No buy proceeds when position cannot be verified.")
    return _fresh_units, ""
