"""Definitional bounds for indicator output, checked at runtime.

WHY THIS EXISTS. `ADXIndicator` returned ADX at ~14x its definitional
maximum for four minor versions. 99.8% of readings were above 100 on an
index whose formula bounds it to [0, 100]; the max was 761.5. Every one
of those readings was recorded by the `ta.raw.adx` emitter, and none was
flagged, because that emitter passed no `expected` -- so `Signal.ok`
came back `None` and the record was a TRANSCRIPT, not a check. The bug
was eventually found by hand-writing an offline comparison script.

Measured across a full replay before this module existed: 15,381 of
16,574 records (92.8%) were `ok=None`. Every `ta.raw.*` record was in
that group.

WHAT GOES IN HERE. Only bounds that follow from the indicator's standard
published formula. RSI is [0, 100] because it is 100 - 100/(1 + RS) with
RS >= 0. Kaufman's Efficiency Ratio is [0, 1] because a net displacement
cannot exceed the summed absolute displacements that produced it.

WHAT DOES NOT. Anything tuned, conventional, or observed. "RSI > 70 is
overbought" is a convention. "ADX is usually below 60" is an
observation of current behaviour -- encoding it would pin the bug in
place, which is exactly how `ADXTrendSuppressionGate.adx_threshold` came
to be 500. A bound here must be derivable from the formula alone, so
that it stays true no matter what the implementation does.

REJECTED CANDIDATES, and why -- both looked definitional and are not.
Each was measured against real records before being dropped:

  * `0 <= bb_position <= 1`. Violated on 148 of 1181 records, high
    1.1324. The bound is WRONG, not the code: bb_position is
    (price - lower) / (upper - lower), which legitimately exceeds 1
    whenever price breaks above the upper band. That is the signal, not
    an error.
  * `kijun_rising` and `kijun_flat` are mutually exclusive. Both true on
    43 of 1086. Also not a defect: `rising` is a strict sign test
    (kijun > prev) and `flat` is a deadband (|delta| < price * 0.0003),
    so any delta inside the deadband but above zero satisfies both.
    They answer different questions and no consumer outside ta_engine
    reads either.

The lesson both encode: measure a candidate against real output before
adding it. A plausible-sounding bound that fires on correct data is
worse than no bound, because it teaches the reader to ignore the
channel.

FAIL-SOFT, ALWAYS. An invariant whose fields are absent is skipped, not
failed: several indicators return a partial details dict from an
early-return path during warm-up, and a bound that fires on warm-up
trains the reader to ignore the channel. Nothing here raises. A broken
check must never break a trading tick.
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
    """One definitional bound over an indicator's emitted details."""

    fields: tuple[str, ...]
    rule: str
    predicate: Callable[[dict], bool]
    # Which presence test decides whether this invariant APPLIES to a
    # given details dict. Numeric bounds need real numbers; flag
    # invariants need bools. `_num` deliberately rejects bools (bool is
    # a subclass of int), so a flag invariant checked with `_num` would
    # be silently skipped on every record -- present in the table,
    # never evaluated, and indistinguishable from passing.
    numeric: bool = True


def _num(d: dict, *names: str) -> bool:
    """True when every name is present and a real (non-bool) number.

    `bool` is a subclass of `int`, so an indicator that emits a flag
    where a magnitude is expected would otherwise sail through a
    numeric comparison.
    """
    for n in names:
        v = d.get(n)
        if isinstance(v, bool) or not isinstance(v, _NUM):
            return False
        if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
            return False
    return True


def _pct(name: str) -> Invariant:
    """A field bounded to [0, 100] by its own definition."""
    return Invariant(
        (name,), f"0 <= {name} <= 100", lambda d, _n=name: 0.0 <= float(d[_n]) <= 100.0
    )


def _unit(name: str) -> Invariant:
    """A field bounded to [0, 1] -- ratios and confidences."""
    return Invariant(
        (name,), f"0 <= {name} <= 1", lambda d, _n=name: 0.0 <= float(d[_n]) <= 1.0
    )


def _flags(d: dict, *names: str) -> bool:
    """True when every name is present AND actually a bool."""
    return all(isinstance(d.get(n), bool) for n in names)


def _excl(*names: str) -> Invariant:
    """At most one of these flags may be true at once.

    Mutual exclusivity is definitional even where the cut points are
    conventional: ADX's ranging / developing / strong_trend bands are a
    PARTITION of one number, so whatever the thresholds are, two of them
    cannot hold together. Same for a bull cross and a bear cross on one
    bar, or a price being above and below the same cloud.
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
    # RSI = 100 - 100/(1 + RS), RS = avg_gain/avg_loss >= 0.
    "rsi": (_pct("rsi"),),
    # Stochastic of RSI: (x - min) / (max - min) * 100, so both the raw
    # %K and its %D smoothing are bounded by construction.
    "stochastic_rsi": (_pct("k"), _pct("d")),
    # +DI and -DI are 100 * smoothed(DM) / smoothed(TR), and |DM| <= TR
    # for each bar. DX = 100 * |+DI - -DI| / (+DI + -DI) is bounded by
    # the triangle inequality, and ADX is a MEAN of DX values -- an
    # average cannot leave the range of what it averages. This is the
    # bound the sum-form smoother broke.
    "adx": (
        _pct("adx"),
        _pct("di_plus"),
        _pct("di_minus"),
        _excl("ranging", "developing", "strong_trend"),
        _excl("bull_dominant", "bear_dominant"),
        _excl("di_bull_cross", "di_bear_cross"),
    ),
    # Bands are middle +/- k*sigma with k > 0 and sigma >= 0, so the
    # ordering holds with equality only when sigma == 0 (a flat window).
    "bollinger_bands": (
        Invariant(
            ("lower", "middle", "upper"),
            "lower <= middle <= upper",
            lambda d: (float(d["lower"]) <= float(d["middle"]) <= float(d["upper"])),
        ),
        _nonneg("band_width"),
    ),
    # sigma is a square root of a mean of squares.
    "zscore": (_nonneg("std"),),
    # |sum of changes| <= sum of |changes|; the numerator of ER is the
    # former and the denominator the latter.
    "kaufman_er": (_unit("er"),),
    # VI+ and VI- are sums of absolute differences over summed true
    # range -- non-negative, though NOT bounded above by 1.
    "vortex": (_nonneg("vi_plus"), _nonneg("vi_minus")),
    # MFI is a 0-100 oscillator on the RSI pattern. CMF is a weighted
    # mean of the money-flow multiplier, itself bounded [-1, 1].
    "volume": (
        _pct("mfi"),
        Invariant(("cmf",), "-1 <= cmf <= 1", lambda d: -1.0 <= float(d["cmf"]) <= 1.0),
        _excl("mfi_overbought", "mfi_oversold"),
        _excl("cmf_bull", "cmf_bear"),
    ),
    # ATR is a mean of true ranges, each a max of non-negative spans.
    # dist_pct is reported as a magnitude.
    "supertrend": (
        _nonneg("curr_atr"),
        _nonneg("dist_pct"),
        _excl("flip_bull", "flip_bear"),
    ),
    # The cloud is bounded by max/min of the two senkou spans, so the
    # ordering is definitional however the spans are computed.
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
    # Confidences. squeeze_conf breached this at -0.2722 on 30 of 1173
    # records: it was `min(1.0, ...)` with no floor, and its
    # expansion_rate term is signed.
    "slingshot": (
        _unit("squeeze_conf"),
        _unit("snapback_conf"),
        _nonneg("curr_bw"),
        _nonneg("avg_bw"),
        _excl("squeeze_bull", "squeeze_bear"),
    ),
    # An identity, not a bound -- histogram is DEFINED as the gap
    # between the two lines. Tolerance is the stored precision (6 dp on
    # these fields), doubled, since all three are rounded independently
    # before they reach us.
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
    """Evaluate the bounds for one indicator's details.

    Returns ``(ok, rule)``:
      * ``(None, None)``  nothing applicable -- no invariants for this
        indicator, or none of their fields are present. The emitter then
        records as before, with no verdict, rather than inventing one.
      * ``(True, "<n> invariants")`` every applicable bound held.
      * ``(False, "<the rule that broke>")`` names the FIRST failure, so
        a reader gets the specific violated statement and not a count.

    Never raises. A predicate that throws is treated as inapplicable --
    the alternative is an instrumentation bug taking down a trading tick.
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
            applied += 1
            if not inv.predicate(details):
                return (False, inv.rule)
        except Exception as exc:  # noqa: BLE001
            # A predicate that throws is INAPPLICABLE, not violated.
            # Logged at debug because the alternative -- an
            # instrumentation bug propagating into a trading tick -- is
            # the failure this whole module exists to avoid. Silent
            # would be worse: a bound that never evaluates looks
            # identical to a bound that always passes.
            logger.debug(
                "ta invariant %r on %s not evaluable: %s", inv.rule, indicator, exc
            )
            continue
    if applied == 0:
        return (None, None)
    return (True, f"{applied} invariants")
