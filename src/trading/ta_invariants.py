"""Definitional bounds for indicator output, applied by ``check``.

``INDICATORS`` maps an indicator name to the ``Invariant`` entries its
published formula implies. ``check`` returns ``(None, None)`` when no
bound applies, ``(True, count)`` when every applicable bound held, and
``(False, rule)`` naming the first breach. ``check`` never raises, and
``invariants_for`` returns the table for one indicator.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from typing import Callable, Optional

__all__ = ["INDICATORS", "Invariant", "check", "invariants_for"]

logger = logging.getLogger(__name__)

_NUM = (int, float)


@dataclass(frozen=True)
class Invariant:
    """One definitional bound over the details dict ``check`` reads."""

    fields: tuple[str, ...]
    rule: str
    predicate: Callable[[dict], bool]
    # False routes the presence test through _flags; _num rejects bools.
    numeric: bool = True


def _num(d: dict, *names: str) -> bool:
    """Return True when every name is present and a finite, non-bool number."""
    for n in names:
        v = d.get(n)
        if isinstance(v, bool) or not isinstance(v, _NUM):
            return False
        if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
            return False
    return True


def _pct(name: str) -> Invariant:
    """Build an ``Invariant`` bounding ``name`` to [0, 100]."""
    return Invariant(
        (name,), f"0 <= {name} <= 100", lambda d, _n=name: 0.0 <= float(d[_n]) <= 100.0
    )


def _unit(name: str) -> Invariant:
    """Build an ``Invariant`` bounding ``name`` to [0, 1]."""
    return Invariant(
        (name,), f"0 <= {name} <= 1", lambda d, _n=name: 0.0 <= float(d[_n]) <= 1.0
    )


def _flags(d: dict, *names: str) -> bool:
    """Return True when every name in ``names`` is present and is a bool."""
    return all(isinstance(d.get(n), bool) for n in names)


def _excl(*names: str) -> Invariant:
    """Build an ``Invariant`` allowing at most one of ``names`` to be True.

    It sets ``numeric`` False, which routes its presence test to ``_flags``.
    """
    return Invariant(
        names,
        "at most one of: " + ", ".join(names),
        lambda d, _n=names: sum(1 for x in _n if d.get(x) is True) <= 1,
        numeric=False,
    )


def _nonneg(name: str) -> Invariant:
    return Invariant((name,), f"{name} >= 0", lambda d, _n=name: float(d[_n]) >= 0.0)


INDICATORS: dict[str, tuple[Invariant, ...]] = {
    # rsi = 100 - 100/(1 + RS) with RS = avg_gain/avg_loss >= 0.
    "rsi": (_pct("rsi"),),
    # k and d are (x - min) / (max - min) * 100.
    "stochastic_rsi": (_pct("k"), _pct("d")),
    # adx is a mean of DX = 100 * |di_plus - di_minus| / (di_plus + di_minus).
    "adx": (
        _pct("adx"),
        _pct("di_plus"),
        _pct("di_minus"),
        _excl("ranging", "developing", "strong_trend"),
        _excl("bull_dominant", "bear_dominant"),
        _excl("di_bull_cross", "di_bear_cross"),
    ),
    # Bands are middle +/- k*sigma with k > 0 and sigma >= 0.
    "bollinger_bands": (
        Invariant(
            ("lower", "middle", "upper"),
            "lower <= middle <= upper",
            lambda d: (float(d["lower"]) <= float(d["middle"]) <= float(d["upper"])),
        ),
        _nonneg("band_width"),
    ),
    # std is a square root of a mean of squares.
    "zscore": (_nonneg("std"),),
    # er is |sum of changes| / sum of |changes|.
    "kaufman_er": (_unit("er"),),
    # vi_plus and vi_minus are sums of absolute differences over summed true range.
    "vortex": (_nonneg("vi_plus"), _nonneg("vi_minus")),
    # cmf is a weighted mean of the money-flow multiplier, itself in [-1, 1].
    "volume": (
        _pct("mfi"),
        Invariant(("cmf",), "-1 <= cmf <= 1", lambda d: -1.0 <= float(d["cmf"]) <= 1.0),
        _excl("mfi_overbought", "mfi_oversold"),
        _excl("cmf_bull", "cmf_bear"),
    ),
    # curr_atr is a mean of true ranges, each a max of non-negative spans.
    "supertrend": (
        _nonneg("curr_atr"),
        _nonneg("dist_pct"),
        _excl("flip_bull", "flip_bear"),
    ),
    # cloud_top and cloud_bottom are the max and min of the two senkou spans.
    "ichimoku": (
        Invariant(
            ("cloud_top", "cloud_bottom"),
            "cloud_bottom <= cloud_top",
            lambda d: (float(d["cloud_bottom"]) <= float(d["cloud_top"])),
        ),
        _nonneg("cloud_thick_pct"),
        _excl("tk_above_cloud", "tk_inside_cloud", "tk_below_cloud"),
        _excl("tk_bull_cross", "tk_bear_cross"),
        _excl("twist_to_bull", "twist_to_bear"),
        _excl("chikou_bull", "chikou_bear"),
        _excl("breakout_up", "breakout_down"),
        _excl("san_ko_shu_bull", "san_ko_shu_bear"),
    ),
    "slingshot": (
        _unit("squeeze_conf"),
        _unit("snapback_conf"),
        _nonneg("curr_bw"),
        _nonneg("avg_bw"),
        _excl("squeeze_bull", "squeeze_bear"),
    ),
    # 2e-6 is the stored 6-dp precision doubled; the three fields round apart.
    "macd": (
        Invariant(
            ("macd_line", "signal_line", "histogram"),
            "histogram == macd_line - signal_line",
            lambda d: abs(
                float(d["histogram"])
                - (float(d["macd_line"]) - float(d["signal_line"]))
            )
            <= 2e-6,
        ),
    ),
}


def invariants_for(indicator: str) -> tuple[Invariant, ...]:
    return INDICATORS.get(indicator, ())


def check(
    indicator: str, details: Optional[dict]
) -> tuple[Optional[bool], Optional[str]]:
    """Evaluate every applicable ``Invariant`` for one indicator.

    Returns ``(None, None)`` when none applied, ``(True, "<n> invariants")``
    when all held, and ``(False, rule)`` naming the first breach.
    """
    if not details:
        return (None, None)
    applied = 0
    for inv in INDICATORS.get(indicator, ()):
        try:
            applicable = (
                _num(details, *inv.fields)
                if inv.numeric
                else _flags(details, *inv.fields)
            )
            if not applicable:
                continue
            if not inv.predicate(details):
                return (False, inv.rule)
            applied += 1
        except Exception as exc:  # noqa: BLE001
            # A predicate that raises leaves `applied` unchanged.
            logger.debug(
                "ta invariant %r on %s not evaluable: %s", inv.rule, indicator, exc
            )
            continue
    if applied == 0:
        return (None, None)
    return (True, f"{applied} invariants")
