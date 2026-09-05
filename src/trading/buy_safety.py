"""Fail-closed check that a buy is safe against the exchange's own numbers.

``verify_buy_safe_or_refuse`` reads ``exchange.get_balance(target_asset)``
and returns ``(verified_units, refuse_reason)``; a non-empty
``refuse_reason`` means the caller refuses the buy. ``ExtractorBot`` calls
it directly, and ``ScrummingExecutionMixin._verify_buy_safe_or_refuse``
wraps it with the bot's own lot total as ``expected_units``.
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
    """Verify a buy against fresh exchange state, refusing under doubt.

    Args:
        exchange: object with ``async get_balance(currency) -> Balance``.
        target_asset: base asset being bought.
        expected_units: the caller's own record of units held.
        path: caller identifier carried in the refusal message.

    Returns:
        ``(verified_units, refuse_reason)``. A non-empty ``refuse_reason``
        pairs with ``verified_units`` of ``None``; otherwise
        ``verified_units`` is the position in ``target_asset`` units, and
        ``0.0`` is a legitimately empty position. ``.total`` is preferred
        over ``.free``; both zero with ``expected_units`` above zero
        refuses, and so does any exception from ``get_balance``.
    """
    _fresh_units: Optional[float] = None
    _refuse_reason: str = ""
    try:
        _fresh_bal = await exchange.get_balance(target_asset)
        # ``total`` includes units locked in an open order; ``None`` must
        # not become 0, or a bad response passes the check.
        _t = getattr(_fresh_bal, "total", None)
        _f = getattr(_fresh_bal, "free", None)
        if _t is not None and float(_t or 0) > 0:
            _fresh_units = float(_t)
        elif _f is not None and float(_f or 0) > 0:
            _fresh_units = float(_f)
        else:
            # A zero from the exchange against non-zero local units is a
            # phantom zero, not an empty position.
            if expected_units > 0:
                _refuse_reason = (
                    f"exchange reports {target_asset} total/free both 0 "
                    f"but caller's local state expects "
                    f"{expected_units:.8f} units — refusing to buy "
                    f"against a suspicious zero"
                )
            else:
                # Legitimately empty position. Proceed with 0.
                _fresh_units = 0.0
    except Exception as _gb_exc:
        _refuse_reason = (
            f"fresh balance fetch raised "
            f"{type(_gb_exc).__name__}: {_gb_exc} "
            f"— cannot verify position, fail-closed"
        )

    if _refuse_reason or _fresh_units is None:
        return None, (
            f"MEM-257 FAIL-CLOSED — buy REFUSED. "
            f"Path={path}. Cannot positively verify current position. "
            f"{_refuse_reason or 'fresh_units=None'}. "
            f"No buy proceeds when position cannot be verified."
        )
    return _fresh_units, ""
