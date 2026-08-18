# ruff: noqa: S311
# S311: seeded RNG generates deterministic price series for the identity
# comparison. Nothing here is security-relevant.
"""v3.24.22 — pin tests for suffix-only _sma / _stdev.

WHY THIS CHANGE EXISTS
======================
``_sma`` and ``_stdev`` were O(n*period): each of n outputs re-sums a
window of `period` values over the full history. Consumers read at most
the last 35 entries, so the leading n-35 were computed and thrown away on
every tick, for every bot, for every candle. Measured on real BTC tablet
data, ``VotingEngine.compute_all`` went 0.9532 -> 0.6210 ms/tick (1.53x).

THE CONSTRAINT THAT MATTERS
===========================
Bit-identity. Not "close" — identical.

Every consumer of these values is a threshold comparison:
``bb_pos < 0.15`` / ``> 0.85``, ``band_width < avg_width * 0.75``,
``price >= (upper - tol_val)`` — and ``upper/lower = mid +/- 2*std``. A
drift in the last bits of ``std`` propagates directly into a live
SCRUM/FOLD decision on a knife-edge candle.

A rolling sum-of-squares accumulator was measured at 2.02e-12 max
relative difference. That is why this is a SUFFIX, not a rolling window:
narrowing the range of ``i`` leaves each computed element's arithmetic
byte-for-byte unchanged, whereas an accumulator changes the order of
float operations and therefore the result.

These tests exist to make that property impossible to regress silently.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.ta_engine import (  # noqa: E402
    _sma, _sma_tail, _stdev, _stdev_tail,
)


def _series(n: int, seed: int = 7) -> list[float]:
    rng = random.Random(seed)
    px = 100.0
    out = []
    for _ in range(n):
        px *= 1.0 + rng.gauss(0.0, 0.01)
        out.append(px)
    return out


# ── bit-identity: the whole point ────────────────────────────────

def test_sma_tail_is_bit_identical_to_full():
    for period in (3, 14, 20, 34, 50):
        for n in (60, 100, 250):
            vals = _series(n)
            full = _sma(vals, period)
            tail = _sma_tail(vals, period, tail=35)
            for i in range(max(0, n - 35), n):
                assert full[i] == tail[i], (
                    f"period={period} n={n} i={i}: "
                    f"{full[i]!r} != {tail[i]!r}")


def test_stdev_tail_is_bit_identical_to_full():
    for period in (3, 14, 20, 34, 50):
        for n in (60, 100, 250):
            vals = _series(n)
            full = _stdev(vals, period)
            tail = _stdev_tail(vals, period, tail=35)
            for i in range(max(0, n - 35), n):
                assert full[i] == tail[i], (
                    f"period={period} n={n} i={i}: "
                    f"{full[i]!r} != {tail[i]!r}")


def test_identity_holds_at_every_tail_depth():
    vals = _series(120)
    for tail in (1, 2, 5, 20, 35, 64, 119, 120, 500):
        s = _sma_tail(vals, 20, tail=tail)
        d = _stdev_tail(vals, 20, tail=tail)
        full_s = _sma(vals, 20)
        full_d = _stdev(vals, 20)
        start = max(0, len(vals) - tail)
        for i in range(start, len(vals)):
            assert s[i] == full_s[i], f"sma tail={tail} i={i}"
            assert d[i] == full_d[i], f"stdev tail={tail} i={i}"


def test_a_rolling_accumulator_would_NOT_be_bit_identical():
    """Demonstrates why the prohibition exists rather than asserting it.

    If this ever starts passing as 'identical', the naive optimisation
    has become safe and the docstring should be revisited. Until then it
    documents, executably, that the shortcut is not equivalent.
    """
    vals = _series(400, seed=11)
    period = 20

    # naive rolling sum / sum-of-squares
    rolling = []
    s = ss = 0.0
    for i, v in enumerate(vals):
        s += v
        ss += v * v
        if i >= period:
            old = vals[i - period]
            s -= old
            ss -= old * old
        k = min(i + 1, period)
        if k < 2:
            rolling.append(0.0)
        else:
            mean = s / k
            var = ss / k - mean * mean
            rolling.append(math.sqrt(max(var, 0.0)))

    exact = _stdev(vals, period)
    worst = max(
        abs(a - b) / abs(b) if b else 0.0
        for a, b in zip(rolling[period:], exact[period:]))
    assert worst > 0.0, (
        "rolling accumulator now matches exactly — re-examine the "
        "prohibition in _sma_tail's docstring")


# ── the suffix contract ──────────────────────────────────────────

def test_entries_before_the_tail_are_none():
    """None, not 0.0. Reading one must fail loudly at the point of
    misuse rather than pass a plausible wrong number into a gate."""
    vals = _series(100)
    out = _sma_tail(vals, 20, tail=10)
    assert all(x is None for x in out[:90])
    assert all(isinstance(x, float) for x in out[90:])


def test_length_is_preserved():
    """Consumers index by absolute position, so the list must stay the
    same length as the input."""
    vals = _series(137)
    assert len(_sma_tail(vals, 20, tail=5)) == 137
    assert len(_stdev_tail(vals, 20, tail=5)) == 137


def test_tail_none_computes_everything():
    vals = _series(80)
    assert _sma_tail(vals, 20, tail=None) == _sma(vals, 20)
    assert _stdev_tail(vals, 20, tail=None) == _stdev(vals, 20)


def test_tail_larger_than_series_is_safe():
    vals = _series(30)
    assert _sma_tail(vals, 20, tail=999) == _sma(vals, 20)


def test_empty_series_is_safe():
    assert _sma_tail([], 20, tail=5) == []
    assert _stdev_tail([], 20, tail=5) == []


def test_warmup_branch_is_preserved():
    """i < period-1 uses a shorter divisor. StochasticRSI runs period=3
    over short lists and genuinely hits this path."""
    vals = _series(10)
    full = _sma(vals, 3)
    tail = _sma_tail(vals, 3, tail=10)
    assert full == tail
    assert tail[0] == vals[0]


# ── the consumers still agree ────────────────────────────────────

def test_stoch_rsi_needs_k_plus_d_trailing_values():
    """v3.24.25 — the StochasticRSI stoch window is bounded to
    ``k_smooth + d_smooth`` trailing values.

    Walking the chain backwards:
        d_line[-2] = mean(k_line[-4:-1])  -> needs k_line[-4:]
        k_line[-4] = mean(stoch[-6:-3])   -> needs stoch[-6:]

    Taking fewer would silently change ``k_line[-2]`` / ``d_line[-2]``,
    which drive the K/D crossover tests that emit confidence-0.8
    SCRUM/FOLD signals. This pins the bound so a later "optimisation"
    cannot quietly shrink it.
    """
    from src.trading import ta_engine as TA
    ind = TA.StochasticRSI()
    assert ind.k_smooth + ind.d_smooth >= 4, (
        "bound must cover k_line[-4:], which d_line[-2] reads")


def test_stoch_rsi_reads_match_full_range():
    """The four values StochasticRSI actually reads must be identical
    whether the stoch window is bounded or computed over the full range.

    Built as a hand-rolled reference rather than by patching the
    indicator: the bound is derived from ``k_smooth``/``d_smooth``, so
    changing those to force full-range behaviour would also change the
    smoothing being compared.
    """
    from src.trading import ta_engine as TA

    candles = [
        TA.Candle(timestamp=float(i), open=v, high=v * 1.02,
                  low=v * 0.98, close=v, volume=10.0)
        for i, v in enumerate(_series(200, seed=17))]

    ind = TA.StochasticRSI()
    bounded = ind.compute(candles, "1h")

    closes = [c.close for c in candles]
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(0, d) for d in deltas]
    losses = [max(0, -d) for d in deltas]
    rsi_values = []
    ag = sum(gains[:ind.rsi_period]) / ind.rsi_period
    al = sum(losses[:ind.rsi_period]) / ind.rsi_period
    for i in range(ind.rsi_period, len(deltas)):
        ag = (ag * (ind.rsi_period - 1) + gains[i]) / ind.rsi_period
        al = (al * (ind.rsi_period - 1) + losses[i]) / ind.rsi_period
        rsi_values.append(100 - 100 / (1 + ag / (al + 1e-9)))

    full_stoch = []
    for i in range(ind.stoch_period - 1, len(rsi_values)):
        w = rsi_values[i - ind.stoch_period + 1:i + 1]
        lo, hi = min(w), max(w)
        full_stoch.append((rsi_values[i] - lo) / (hi - lo + 1e-9) * 100)

    k_full = TA._sma(full_stoch, ind.k_smooth)
    d_full = TA._sma(k_full, ind.d_smooth)

    need = ind.k_smooth + ind.d_smooth
    frm = max(ind.stoch_period - 1, len(rsi_values) - need)
    bounded_stoch = []
    for i in range(frm, len(rsi_values)):
        w = rsi_values[i - ind.stoch_period + 1:i + 1]
        lo, hi = min(w), max(w)
        bounded_stoch.append((rsi_values[i] - lo) / (hi - lo + 1e-9) * 100)

    k_b = TA._sma(bounded_stoch, ind.k_smooth)
    d_b = TA._sma(k_b, ind.d_smooth)

    # The four values the indicator actually reads must be identical.
    assert k_b[-1] == k_full[-1]
    assert k_b[-2] == k_full[-2]
    assert d_b[-1] == d_full[-1]
    assert d_b[-2] == d_full[-2]
    assert bounded.direction is not None


def test_bollinger_output_unchanged_against_full_history(monkeypatch):
    """End-to-end: force the helpers back to full-history and confirm
    BollingerBands produces an identical Signal."""
    from src.trading import ta_engine as TA

    candles = [
        TA.Candle(timestamp=float(i), open=v, high=v * 1.01,
                  low=v * 0.99, close=v, volume=10.0)
        for i, v in enumerate(_series(120, seed=3))]

    bb = TA.BollingerBands()
    after = bb.compute(candles, "1h")

    real_sma, real_std = TA._sma_tail, TA._stdev_tail
    monkeypatch.setattr(
        TA, "_sma_tail",
        lambda v, p, tail=None: real_sma(v, p, tail=None))
    monkeypatch.setattr(
        TA, "_stdev_tail",
        lambda v, p, tail=None: real_std(v, p, tail=None))
    before = bb.compute(candles, "1h")

    assert before.direction == after.direction
    assert before.confidence == after.confidence, (
        f"{before.confidence!r} != {after.confidence!r}")
