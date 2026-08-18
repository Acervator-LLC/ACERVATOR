"""Nuclear v2 must vary market structure between cycles (missing feature).

OPERATOR, 2026-08-07: "It does not run on a single tape or stone tablet. It runs
stone tablets in a loop through the simulator bots. These loops are supposed to
have varied market structure via an oscillator that injects noise to simulate
varied market structures WITHOUT WRITING OVER THE STONE TABLETS."

WHAT WAS MISSING. `NuclearFleetController` loaded tablets once
(`nuclear_fleet_controller.py:283`) and handed the same dict to every cycle
(`:427`). Its oscillator is `SystemLoadOscillator` — CPU load, not market
structure — so the loop varied HOW HARD the machine worked while replaying a
byte-identical tape. A bot can learn one fixed tape; that is the whole reason
the noise exists.

The perturbation itself was never missing. `NuclearCandleSource._Tape` has had
it since v3.24.20 (operator directive 2026-08-04: "plays tapes forward and then
backwards with a 10~25% random noise injection to vary the market structure
conditions"). Only v1 used it. This wires v2 to the same implementation rather
than adding a third — `topology_stress._noised_rows` already documents why:
a second implementation "could drift from it, and then a stress result would
describe a market structure the operator never actually simulates."

NOT A VALIDATION INSTRUMENT. Nuclear's noised tape deliberately is NOT history,
so nothing here compares trades to YTD or live. Nuclear runs AFTER trade-logic
alignment is proven on the real tablets; its criteria are coverage and survival.
See the audit's section 1.0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.simulator_tab.nuclear_candle_source import (  # noqa: E402
    _NOISE_MAX_PCT,
    _NOISE_MIN_PCT,
    noised_series,
)

BASE = 1_700_000_000_000
STEP = 300_000


def _rows(n=60, px=100.0):
    return [[BASE + i * STEP, px, px * 1.02, px * 0.98, px * 1.01, 5.0]
            for i in range(n)]


class TestTheInstrumentWorks:
    def test_noise_actually_changes_the_series(self):
        """POSITIVE CONTROL. Every 'cycles differ' assertion below is
        vacuous if the perturbation is a no-op."""
        src = _rows()
        out, pct = noised_series(src, seed=1)
        assert pct > 0.0
        assert any(o[4] != s[4] for o, s in zip(out, src))

    def test_the_amplitude_is_in_the_declared_band(self):
        for seed in range(8):
            _, pct = noised_series(_rows(), seed=seed)
            assert _NOISE_MIN_PCT <= pct <= _NOISE_MAX_PCT


class TestTheStoneTabletsAreNeverWrittenOver:
    """Operator constraint, stated verbatim. The tablets are immutable —
    'You do not modify the fucking stone tablets.'"""

    def test_the_source_rows_are_not_mutated(self):
        src = _rows()
        before = [list(r) for r in src]
        noised_series(src, seed=7)
        assert src == before

    def test_the_output_does_not_alias_the_input(self):
        src = _rows()
        out, _ = noised_series(src, seed=7)
        out[0][4] = -999.0
        assert src[0][4] != -999.0


class TestAPassIsInternallyCoherent:
    """Deterministic in (seed, idx), NOT drawn fresh per read. `history()`
    re-reads the same indices every tick; if values moved between reads the
    bot's TA would be computed over a series that never existed."""

    def test_the_same_seed_gives_the_same_series(self):
        a, pa = noised_series(_rows(), seed=42)
        b, pb = noised_series(_rows(), seed=42)
        assert a == b
        assert pa == pb

    def test_different_seeds_give_different_market_structure(self):
        a, _ = noised_series(_rows(), seed=1)
        b, _ = noised_series(_rows(), seed=2)
        assert a != b


class TestAPerturbedCandleIsStillAWellFormedCandle:
    def test_timestamps_are_never_touched(self):
        src = _rows()
        out, _ = noised_series(src, seed=3)
        assert [r[0] for r in out] == [r[0] for r in src], (
            "the master clock must stay authoritative")

    def test_the_ohlc_invariant_holds(self):
        out, _ = noised_series(_rows(), seed=5)
        for ts, o, h, low, c, v in out:
            assert h >= max(o, c, low)
            assert low <= min(o, c, h)

    def test_prices_and_volume_stay_non_negative(self):
        out, _ = noised_series(_rows(), seed=9)
        for _ts, o, h, low, c, v in out:
            assert min(o, h, low, c) > 0.0
            assert v >= 0.0

    def test_the_row_shape_is_preserved(self):
        src = _rows()
        out, _ = noised_series(src, seed=11)
        assert len(out) == len(src)
        assert all(len(r) == 6 for r in out)


class TestOneImplementationNotThree:
    """`topology_stress._noised_rows` documented the reason: a second
    perturbation implementation would drift, and a stress result would then
    describe a market structure the operator never actually simulates."""

    def test_topology_stress_produces_the_identical_series(self):
        from src.trading.topology_stress import _noised_rows
        src = _rows()
        a, pa = _noised_rows(src, seed=17)
        b, pb = noised_series(src, seed=17)
        assert a == b
        assert pa == pb


class TestTheControllerVariesStructurePerCycle:
    """The actual missing feature, at the consumer."""

    @staticmethod
    def _ctl():
        from src.gui.simulator_tab.nuclear_fleet_controller import (
            NuclearFleetController)
        ctl = NuclearFleetController()
        ctl._candles = {"BTC/USD": _rows(), "ETH/USD": _rows(px=50.0)}
        return ctl

    def test_successive_cycles_see_different_market_structure(self):
        ctl = self._ctl()
        c0, _ = ctl._noised_candles_for_cycle(0)
        c1, _ = ctl._noised_candles_for_cycle(1)
        assert c0["BTC/USD"] != c1["BTC/USD"], (
            "every cycle replayed a byte-identical tape; the loop varied "
            "system load only")

    def test_the_same_cycle_index_is_reproducible(self):
        """A soak that cannot be re-run is not a diagnostic."""
        a, pa = self._ctl()._noised_candles_for_cycle(3)
        b, pb = self._ctl()._noised_candles_for_cycle(3)
        assert a == b
        assert pa == pb

    def test_every_symbol_in_the_fleet_is_noised(self):
        ctl = self._ctl()
        out, _ = ctl._noised_candles_for_cycle(0)
        assert set(out) == set(ctl._candles)
        for sym in ctl._candles:
            assert out[sym] != ctl._candles[sym]

    def test_the_loaded_tablets_are_never_mutated(self):
        ctl = self._ctl()
        before = {s: [list(r) for r in rows]
                  for s, rows in ctl._candles.items()}
        for i in range(4):
            ctl._noised_candles_for_cycle(i)
        assert ctl._candles == before

    def test_the_cycle_reports_its_noise_amplitude(self):
        """A varied structure the operator cannot see is indistinguishable
        from an unvaried one."""
        _, pct = self._ctl()._noised_candles_for_cycle(0)
        assert _NOISE_MIN_PCT <= pct <= _NOISE_MAX_PCT

    def test_a_symbol_within_one_cycle_shares_the_cycle_seed(self):
        """Workers inside a cycle must replay the SAME structure — the
        cycle is the unit of varied structure, concurrency is the load
        stressor. Two calls for the same index agree, which is what lets
        all workers share one tape."""
        ctl = self._ctl()
        assert ctl._noised_candles_for_cycle(2)[1] == ctl._noised_candles_for_cycle(2)[1]


class TestNoiseCanBeDisabled:
    def test_disabling_returns_the_tablets_unchanged(self):
        """Needed to isolate a defect: if a soak fails, the first question
        is whether it fails on the unperturbed tape too."""
        from src.gui.simulator_tab.nuclear_fleet_controller import (
            NuclearFleetController)
        ctl = NuclearFleetController(noise_enabled=False)
        ctl._candles = {"BTC/USD": _rows()}
        out, pct = ctl._noised_candles_for_cycle(0)
        assert pct == pytest.approx(0.0)
        assert out["BTC/USD"] == ctl._candles["BTC/USD"]
