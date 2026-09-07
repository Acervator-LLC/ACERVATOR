"""The published tests the Market Inspector gates every proposal with.

``cointegration_test`` runs the Engle-Granger two-step and the Johansen trace
test from statsmodels; ``correlation_test`` runs the Pearson coefficient and
its two-sided t test from scipy. Both answer a ``MethodResult`` naming the
method, the window it ran on and the statistic, which is what the Opposing
Pairs table and the topology cards print beside every proposal.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np
from scipy.stats import pearsonr  # type: ignore[import-untyped]
from statsmodels.tsa.stattools import coint  # type: ignore[import-untyped]
from statsmodels.tsa.vector_ar.vecm import (  # type: ignore[import-untyped]
    coint_johansen,
)

logger = logging.getLogger("acervator.pair_selection")

METHOD_COINTEGRATION = "cointegration"
METHOD_CORRELATION = "correlation"
METHOD_BAND_DISTANCE = "band_distance"

METHOD_LABELS = {
    METHOD_COINTEGRATION: "Cointegration",
    METHOD_CORRELATION: "Correlation",
    METHOD_BAND_DISTANCE: "Band distance",
}
METHOD_TESTS = {
    METHOD_COINTEGRATION: "Engle-Granger + Johansen",
    METHOD_CORRELATION: "Pearson",
    METHOD_BAND_DISTANCE: "Distance from target balance",
}

WINDOW_BARS = 365
MIN_OBSERVATIONS = 120
SIGNIFICANCE = 0.05

JOHANSEN_DET_ORDER = 0
JOHANSEN_LAG_DIFF = 1
JOHANSEN_TRACE_ROW = 0
JOHANSEN_CV_95_COLUMN = 1

FLAT_SERIES_TOLERANCE = 1e-12

LIVE_STATE_WINDOW_TEXT = "live"
SHORT_SERIES_DETAIL = "series shorter than {minimum} bars"
FLAT_SERIES_DETAIL = "series holds one repeated price"
TEST_FAILED_DETAIL = "{name}: {message}"

COINTEGRATION_STATISTIC_FORMAT = "p={p_value:.4f} · trace {trace:.1f}>{critical:.1f}"
CORRELATION_STATISTIC_FORMAT = "r={correlation:+.3f} · p={p_value:.4f}"
BAND_DISTANCE_STATISTIC_FORMAT = "{scrum:+.1f}% / {fold:+.1f}% vs {deep:.1f}%"


@dataclass(frozen=True)
class MethodResult:
    """One published test's verdict on one candidate, as the screens print it."""

    method: str
    passed: bool
    observations: int = 0
    statistic: float = 0.0
    p_value: float = 1.0
    statistic_text: str = ""
    detail: str = ""

    @property
    def label(self) -> str:
        """The method name the card and the table cell carry."""
        return METHOD_LABELS.get(self.method, self.method)

    @property
    def test_name(self) -> str:
        """The published test behind ``method``."""
        return METHOD_TESTS.get(self.method, "")

    @property
    def window_text(self) -> str:
        """The window the test ran on, in bars."""
        if self.method == METHOD_BAND_DISTANCE:
            return LIVE_STATE_WINDOW_TEXT
        return f"{self.observations}d"

    def as_dict(self) -> dict[str, Any]:
        """The verdict as the proposal dicts and the page payload carry it."""
        return {
            "method": self.method,
            "label": self.label,
            "test": self.test_name,
            "window": self.window_text,
            "observations": self.observations,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "statistic_text": self.statistic_text,
            "passed": self.passed,
            "detail": self.detail,
        }


def window_of(
    series: Optional[Sequence[float]], window_bars: int = WINDOW_BARS
) -> list:
    """The last ``window_bars`` finite values of ``series``."""
    if not series:
        return []
    tail = list(series)[-int(window_bars) :]
    return [float(v) for v in tail if isinstance(v, (int, float)) and np.isfinite(v)]


def is_flat(values: Sequence[float]) -> bool:
    """Whether every value in ``values`` is the same price."""
    if not values:
        return True
    return (max(values) - min(values)) <= FLAT_SERIES_TOLERANCE


def daily_returns(closes: Sequence[float]) -> list:
    """Simple returns of ``closes``, skipping any bar whose predecessor is zero."""
    out = []
    for index in range(1, len(closes)):
        previous = closes[index - 1]
        if previous > 0:
            out.append((closes[index] - previous) / previous)
    return out


def _refused(method: str, observations: int, detail: str) -> MethodResult:
    """A verdict for a candidate the test could not run on."""
    return MethodResult(
        method=method, passed=False, observations=observations, detail=detail
    )


def _aligned(
    closes_a: Optional[Sequence[float]],
    closes_b: Optional[Sequence[float]],
    window_bars: int,
) -> tuple:
    """Both series cut to the same length inside ``window_bars``."""
    left = window_of(closes_a, window_bars)
    right = window_of(closes_b, window_bars)
    length = min(len(left), len(right))
    return left[-length:], right[-length:]


def engle_granger_p_value(left: Sequence[float], right: Sequence[float]) -> float:
    """The Engle-Granger two-step p-value from ``statsmodels.tsa.stattools.coint``."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(coint(np.asarray(left, float), np.asarray(right, float))[1])


def johansen_trace(left: Sequence[float], right: Sequence[float]) -> tuple:
    """The Johansen trace statistic for rank zero and its 95% critical value."""
    data = np.column_stack([np.asarray(left, float), np.asarray(right, float)])
    with warnings.catch_warnings():
        # coint_johansen casts complex eigenvalues to real inside statsmodels.
        warnings.simplefilter("ignore")
        result = coint_johansen(
            data, det_order=JOHANSEN_DET_ORDER, k_ar_diff=JOHANSEN_LAG_DIFF
        )
    trace = float(result.lr1[JOHANSEN_TRACE_ROW])
    critical = float(result.cvt[JOHANSEN_TRACE_ROW][JOHANSEN_CV_95_COLUMN])
    return trace, critical


def cointegration_test(
    closes_a: Optional[Sequence[float]],
    closes_b: Optional[Sequence[float]],
    window_bars: int = WINDOW_BARS,
    significance: float = SIGNIFICANCE,
    min_observations: int = MIN_OBSERVATIONS,
) -> MethodResult:
    """Whether two close series share a long-run equilibrium.

    ``passed`` needs Engle-Granger to reject the null of no cointegration at
    ``significance`` and the Johansen trace statistic for rank zero to clear
    its 95% critical value.
    """
    left, right = _aligned(closes_a, closes_b, window_bars)
    if len(left) < int(min_observations):
        return _refused(
            METHOD_COINTEGRATION,
            len(left),
            SHORT_SERIES_DETAIL.format(minimum=int(min_observations)),
        )
    if is_flat(left) or is_flat(right):
        return _refused(METHOD_COINTEGRATION, len(left), FLAT_SERIES_DETAIL)
    try:
        p_value = engle_granger_p_value(left, right)
        trace, critical = johansen_trace(left, right)
    except Exception as exc:  # noqa: BLE001 - statsmodels refuses degenerate input
        logger.debug("cointegration test refused: %s", exc)
        return _refused(
            METHOD_COINTEGRATION,
            len(left),
            TEST_FAILED_DETAIL.format(name=type(exc).__name__, message=exc),
        )
    if not np.isfinite(p_value) or not np.isfinite(trace):
        return _refused(METHOD_COINTEGRATION, len(left), FLAT_SERIES_DETAIL)
    return MethodResult(
        method=METHOD_COINTEGRATION,
        passed=bool(p_value <= float(significance) and trace > critical),
        observations=len(left),
        statistic=p_value,
        p_value=p_value,
        statistic_text=COINTEGRATION_STATISTIC_FORMAT.format(
            p_value=p_value, trace=trace, critical=critical
        ),
    )


def correlation_test(
    closes_a: Optional[Sequence[float]],
    closes_b: Optional[Sequence[float]],
    window_bars: int = WINDOW_BARS,
    significance: float = SIGNIFICANCE,
    min_observations: int = MIN_OBSERVATIONS,
) -> MethodResult:
    """The Pearson coefficient of two close series' daily returns, and its t test.

    ``passed`` needs the two-sided p-value at or below ``significance``, which
    leaves the sign and the size of the coefficient for the caller to threshold.
    """
    left, right = _aligned(closes_a, closes_b, window_bars)
    if len(left) < int(min_observations):
        return _refused(
            METHOD_CORRELATION,
            len(left),
            SHORT_SERIES_DETAIL.format(minimum=int(min_observations)),
        )
    returns_left = daily_returns(left)
    returns_right = daily_returns(right)
    length = min(len(returns_left), len(returns_right))
    returns_left = returns_left[-length:]
    returns_right = returns_right[-length:]
    if is_flat(returns_left) or is_flat(returns_right):
        return _refused(METHOD_CORRELATION, len(left), FLAT_SERIES_DETAIL)
    try:
        measured = pearsonr(returns_left, returns_right)
        correlation = float(measured.statistic)
        p_value = float(measured.pvalue)
    except Exception as exc:  # noqa: BLE001 - scipy refuses degenerate input
        logger.debug("correlation test refused: %s", exc)
        return _refused(
            METHOD_CORRELATION,
            len(left),
            TEST_FAILED_DETAIL.format(name=type(exc).__name__, message=exc),
        )
    if not np.isfinite(correlation) or not np.isfinite(p_value):
        return _refused(METHOD_CORRELATION, len(left), FLAT_SERIES_DETAIL)
    return MethodResult(
        method=METHOD_CORRELATION,
        passed=bool(p_value <= float(significance)),
        observations=len(left),
        statistic=correlation,
        p_value=p_value,
        statistic_text=CORRELATION_STATISTIC_FORMAT.format(
            correlation=correlation, p_value=p_value
        ),
    )


def band_distance_result(
    scrum_distance_pct: float, fold_distance_pct: float, deep_pct: float
) -> MethodResult:
    """Whether both bots sit at or past ``deep_pct`` from their target balance."""
    passed = abs(scrum_distance_pct) >= deep_pct and abs(fold_distance_pct) >= deep_pct
    return MethodResult(
        method=METHOD_BAND_DISTANCE,
        passed=passed,
        statistic=abs(scrum_distance_pct) + abs(fold_distance_pct),
        p_value=0.0,
        statistic_text=BAND_DISTANCE_STATISTIC_FORMAT.format(
            scrum=scrum_distance_pct, fold=fold_distance_pct, deep=deep_pct
        ),
    )


def score_from_p_value(p_value: float) -> float:
    """The 0..100 score a p-value carries, as ``100 * (1 - p)``."""
    return max(0.0, min(100.0, 100.0 * (1.0 - float(p_value))))


def score_from_correlation(correlation: float) -> float:
    """The 0..100 score a correlation carries, as ``100 * |r|``."""
    return max(0.0, min(100.0, 100.0 * abs(float(correlation))))


__all__ = [
    "METHOD_COINTEGRATION",
    "METHOD_CORRELATION",
    "METHOD_BAND_DISTANCE",
    "METHOD_LABELS",
    "METHOD_TESTS",
    "WINDOW_BARS",
    "MIN_OBSERVATIONS",
    "SIGNIFICANCE",
    "MethodResult",
    "window_of",
    "is_flat",
    "daily_returns",
    "engle_granger_p_value",
    "johansen_trace",
    "cointegration_test",
    "correlation_test",
    "band_distance_result",
    "score_from_p_value",
    "score_from_correlation",
]
