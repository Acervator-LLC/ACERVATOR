"""The per-tranche FOLD eligibility OTD must include the trading fee.

THE DEFECT
The Minimum Opposing Trade Distance was computed at four sites. Three
included the trading fee:

  * ``HysteresisGate``  -- ``gate_chain.py``:
    ``eff_pct = ctx.scrumming_interval_pct + ctx.trading_fee_pct``
  * the FOLD blocker diagnostic in ``scrumming_bot.tick``
  * the STACK open, ``_open_stack_from_scrum``

The fourth -- the per-tranche FOLD eligibility filter that actually
selects which tranches get re-bought -- used ``scrumming_interval_pct``
alone. A tranche could therefore be re-bought at a price that cleared
its interval but still lost the round trip to fees.

WHY THE HYSTERESIS GATE DID NOT ALREADY COVER IT
Two independent reasons, both verified against the source:

  (a) ``HysteresisGate.evaluate`` short-circuits -- ``if ok: return
      GateResult(passed=True)`` -- so it binds only while ARMED; and
  (b) when armed it measures from the ARMING PIVOT
      (``_hyst_ref_fold_side``, captured at the tick the target delta
      crossed negative), NOT from each tranche's own ``ref``. It can
      pass while an individual tranche is still short of interval+fee
      from where IT sold.

Sharper still: the FOLD side only arms while ``_last_trade_side ==
"SCRUM"``, and every fill calls
``_reset_opposing_hysteresis_after_fill``. Consecutive FOLD rebuys down
a decline -- exactly the case where several tranches dequeue -- are
never gated by it at all. The per-tranche filter is the only distance
gate there.

OPERATOR RULING, 2026-08-12
    "This issue should be getting mitigated by the trade fee being added
     to the Minimum Opposing Trading Distance."
    "Functionality should be mirrored between either side of the
     ladder."

BOUNDARY VALUES ARE LITERALS, NOT ARITHMETIC
Every threshold below is a pasted literal at full ``repr`` precision. A
boundary recomputed inside the test as ``ref * factor`` lands on
whatever the implementation happens to produce, so the test would agree
with the code by construction and pass for the wrong reason.

FALSIFICATION: these tests are wrong if the executor's predicate stops
being ``ticker.last <= ref * _otd_factor``, or if ``_otd_factor`` stops
coming from a single ``otd_math`` call shared with the diagnostic.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from src.trading.otd_math import (
    OTD_MAX_PCT,
    OTD_MIN_PCT,
    fold_rebuy_factor,
    fold_rebuy_factor_from_pct,
    minimum_opposing_trade_distance_pct,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = (REPO_ROOT / "src" / "trading" / "scrumming_bot.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)

# ── the executor's predicate, stated once ───────────────────────────
# Verbatim from scrumming_bot.py:
#     ticker.last <= float(t.get("ref", 0)) * _otd_factor


def eligible(price: float, ref: float, factor: float) -> bool:
    """The executor's eligibility predicate."""
    return price <= ref * factor


# ── literals, computed offline at full precision ────────────────────
# ref=100.0, scrumming_interval_pct=5.0, trading_fee_pct=0.6
REF = 100.0
INTERVAL = 5.0
FEE = 0.6

# interval ONLY -- what the old code demanded: 100.0 * 0.95
THRESHOLD_INTERVAL_ONLY = 95.0
# interval + fee -- what it must demand now: 100.0 * 0.944
THRESHOLD_WITH_FEE = 94.39999999999999
# one ulp either side of THRESHOLD_WITH_FEE
ONE_ULP_BELOW = 94.39999999999998
ONE_ULP_ABOVE = 94.4


class TestTheInstrumentWorks:
    """POSITIVE CONTROLS. Without these every assertion below could be
    passing against nothing."""

    def test_the_literals_are_the_real_thresholds(self):
        """The pasted literals must be the values the module actually
        produces. If this drifts, every boundary test below is grading a
        threshold that does not exist."""
        assert REF * fold_rebuy_factor(INTERVAL, FEE) == THRESHOLD_WITH_FEE
        assert REF * fold_rebuy_factor(INTERVAL, 0.0) == THRESHOLD_INTERVAL_ONLY

    def test_the_ulp_neighbours_really_are_adjacent_floats(self):
        """A 'boundary' that is two ulps out tests nothing at the
        boundary."""
        assert math.nextafter(THRESHOLD_WITH_FEE, 0.0) == ONE_ULP_BELOW
        assert math.nextafter(THRESHOLD_WITH_FEE, math.inf) == ONE_ULP_ABOVE

    def test_the_fee_actually_moves_the_threshold(self):
        """If fee inclusion were a no-op the accept/reject tests would
        pass trivially."""
        assert THRESHOLD_WITH_FEE < THRESHOLD_INTERVAL_ONLY

    def test_the_source_extractor_finds_the_tick(self):
        assert _tick() is not None


def _tick() -> ast.AST:
    """One tick pass: ``tick`` plus every ``_tick_*`` phase method.

    The phases are separate methods on the class, so a scan of ``tick``
    alone would pass over the code that runs inside them.
    """
    found: dict = {}
    for tree in [TREE] + [ast.parse(s) for s in _phase_sources()]:
        for n in ast.walk(tree):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if n.name != "tick" and not n.name.startswith("_tick_"):
                continue
            prev = found.get(n.name)
            span = (n.end_lineno or 0) - n.lineno
            if prev is None or span > (prev.end_lineno or 0) - prev.lineno:
                found[n.name] = n
    assert found, "no tick pass found -- extractor broken, not the code"
    return ast.Module(body=list(found.values()), type_ignores=[])


def _phase_sources() -> list[str]:
    """Source of every module defining a ``_tick_*`` phase method."""
    import inspect

    from src.trading.scrumming_bot import ScrummingBot

    paths = set()
    for name in dir(ScrummingBot):
        if not name.startswith("_tick_"):
            continue
        member = getattr(ScrummingBot, name, None)
        if not callable(member):
            continue
        path = inspect.getsourcefile(member)
        if path:
            paths.add(path)
    return [Path(p).read_text(encoding="utf-8") for p in sorted(paths)]


def _method(name: str) -> ast.AST:
    """The named ScrummingBot method, read from the module that owns it."""
    import inspect

    from src.trading.scrumming_bot import ScrummingBot

    path = inspect.getsourcefile(getattr(ScrummingBot, name))
    assert path is not None, name
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    found = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    assert found, f"no {name}() found -- extractor broken, not the code"
    return max(found, key=lambda n: (n.end_lineno or 0) - n.lineno)


class TestTheFeeIsRequired:
    def test_a_tranche_at_interval_only_distance_is_no_longer_eligible(self):
        """THE DEFECT, stated as a test. A price exactly one interval
        below the tranche ref used to fire. It must not: that round trip
        does not clear its own fees."""
        assert not eligible(
            THRESHOLD_INTERVAL_ONLY, REF, fold_rebuy_factor(INTERVAL, FEE)
        )

    def test_that_same_price_WAS_eligible_before(self):
        """NEGATIVE CONTROL on the test above -- proves it is detecting
        the change rather than a price that was never eligible."""
        assert eligible(THRESHOLD_INTERVAL_ONLY, REF, fold_rebuy_factor(INTERVAL, 0.0))

    def test_a_tranche_at_interval_plus_fee_distance_is_eligible(self):
        """The gate must not be a lockout: at the full distance it
        fires."""
        assert eligible(THRESHOLD_WITH_FEE, REF, fold_rebuy_factor(INTERVAL, FEE))


class TestTheBoundary:
    """`<=`, so the threshold itself is INSIDE."""

    def test_exactly_at_the_threshold_is_eligible(self):
        assert eligible(THRESHOLD_WITH_FEE, REF, fold_rebuy_factor(INTERVAL, FEE))

    def test_one_ulp_below_is_eligible(self):
        assert eligible(ONE_ULP_BELOW, REF, fold_rebuy_factor(INTERVAL, FEE))

    def test_one_ulp_above_is_not_eligible(self):
        assert not eligible(ONE_ULP_ABOVE, REF, fold_rebuy_factor(INTERVAL, FEE))


class TestFeeZeroReproducesTheOldBehaviour:
    """A zero fee must collapse to the interval-only rule EXACTLY --
    not approximately. This is the guarantee that the change adds the
    fee and does nothing else."""

    @pytest.mark.parametrize("interval", [0.0, 0.1, 1.0, 5.0, 12.5, 49.9])
    def test_zero_fee_equals_interval_only(self, interval):
        assert fold_rebuy_factor(interval, 0.0) == fold_rebuy_factor_from_pct(
            max(OTD_MIN_PCT, min(OTD_MAX_PCT, interval))
        )

    def test_zero_fee_leaves_the_threshold_bit_identical(self):
        assert REF * fold_rebuy_factor(INTERVAL, 0.0) == THRESHOLD_INTERVAL_ONLY


class TestTheClamp:
    """The clamp applies to the SUM, after the fee. The bound exists to
    keep the factor inside [0.5, 1.0], which is a property of the TOTAL
    distance."""

    def test_upper_bound_holds(self):
        assert minimum_opposing_trade_distance_pct(1e9, 0.6) == OTD_MAX_PCT

    def test_lower_bound_holds(self):
        assert minimum_opposing_trade_distance_pct(-5.0, 0.6) == OTD_MIN_PCT

    def test_the_clamp_binds_on_the_SUM_not_the_interval(self):
        """interval 49.5 is under the cap; 49.5 + 0.6 is not. Clamping
        the interval FIRST and adding the fee after would give 50.1 and
        a factor of 0.499 -- outside the range the clamp asserts."""
        assert minimum_opposing_trade_distance_pct(49.5, 0.6) == 50.0
        assert fold_rebuy_factor(49.5, 0.6) == 0.5

    def test_a_sum_landing_exactly_on_the_cap_is_unclamped(self):
        assert minimum_opposing_trade_distance_pct(49.4, 0.6) == 50.0

    @pytest.mark.parametrize("interval", [-1e9, -1.0, 0.0, 25.0, 49.9, 50.0, 1e9])
    @pytest.mark.parametrize("fee", [0.0, 0.6, 1.6, 5.0])
    def test_factor_never_leaves_its_range(self, interval, fee):
        assert 0.5 <= fold_rebuy_factor(interval, fee) <= 1.0
        assert (
            OTD_MIN_PCT
            <= minimum_opposing_trade_distance_pct(interval, fee)
            <= OTD_MAX_PCT
        )


class TestTheDiagnosticAndTheExecutorAgree:
    """The hoist comment exists to prevent instrument/executor drift.
    Adding the fee in one place and not the other would recreate exactly
    the defect that hoist was written to fix."""

    def _tick_src(self) -> str:
        return ast.get_source_segment(SRC, _tick()) or ""

    def test_the_otd_pct_is_computed_exactly_once(self):
        calls = [
            n
            for n in ast.walk(_tick())
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "minimum_opposing_trade_distance_pct"
        ]
        assert len(calls) == 1, (
            f"the OTD is computed {len(calls)} times in tick(); a second "
            f"copy is how the instrument and the executor drift apart"
        )

    def test_the_factor_is_assigned_exactly_once(self):
        assigns = [
            n
            for n in ast.walk(_tick())
            if isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") == "_otd_factor" for t in n.targets)
        ]
        assert len(assigns) == 1

    def test_the_single_call_passes_the_trading_fee(self):
        """The whole point. A call that passes only the interval is the
        defect back again."""
        calls = [
            n
            for n in ast.walk(_tick())
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "minimum_opposing_trade_distance_pct"
        ]
        src = ast.unparse(calls[0])
        assert "trading_fee_pct" in src, src
        assert "scrumming_interval_pct" in src, src

    def test_both_the_counter_and_the_executor_read_that_factor(self):
        """Both sites must take their eligible set from one predicate.

        They used to hold two look-alike comparisons and this test
        counted them. They now call one shared helper, which is the
        same invariant held more tightly: two callers of one method
        cannot drift, where two copies of one comparison can.
        """
        calls = [
            n
            for n in ast.walk(_tick())
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == "_fold_eligible_tranches"
        ]
        assert len(calls) >= 2, (
            f"expected the diagnostic AND the executor to share the "
            f"predicate; found {len(calls)} call(s) to "
            f"_fold_eligible_tranches in tick()"
        )
        for c in calls:
            src = ast.unparse(c)
            assert "_otd_factor" in src, src
            assert "ticker.last" in src, src

    def test_the_shared_predicate_is_the_executors_comparison(self):
        """The helper must hold the comparison the executor used inline."""
        helper = _method("_fold_eligible_tranches")
        cmps = [ast.unparse(n) for n in ast.walk(helper) if isinstance(n, ast.Compare)]
        assert len(cmps) == 1, f"expected one comparison, found {cmps}"
        assert "ticker_last <= float(t.get('ref', 0)) * otd_factor" in cmps[0], cmps[0]

    def test_the_fee_is_not_re_added_at_the_comparison_sites(self):
        """The factor already carries the fee. A comparison that adds it
        again would double-charge."""
        for node in (_tick(), _method("_fold_eligible_tranches")):
            for n in ast.walk(node):
                if isinstance(n, ast.Compare):
                    s = ast.unparse(n)
                    if "_otd_factor" in s or "otd_factor" in s:
                        assert "trading_fee_pct" not in s, s


class TestMonotonicity:
    """More interval or more fee can never make MORE tranches eligible."""

    @pytest.mark.parametrize("fee", [0.0, 0.6, 1.6])
    def test_distance_non_decreasing_in_interval(self, fee):
        prev = -1.0
        step = 0.25
        for i in range(200):
            cur = minimum_opposing_trade_distance_pct(i * step, fee)
            assert cur >= prev
            prev = cur

    @pytest.mark.parametrize("interval", [0.0, 1.0, 5.0])
    def test_distance_non_decreasing_in_fee(self, interval):
        prev = -1.0
        step = 0.05
        for i in range(120):
            cur = minimum_opposing_trade_distance_pct(interval, i * step)
            assert cur >= prev
            prev = cur

    def test_adding_a_fee_never_widens_the_eligible_set(self):
        refs = [1e-8, 0.02329, 1.0, 8.758, 492.29, 64000.0]
        for ref in refs:
            for price_mult in (0.90, 0.94, 0.9439, 0.944, 0.95, 1.0, 1.1):
                price = ref * price_mult
                with_fee = eligible(price, ref, fold_rebuy_factor(INTERVAL, FEE))
                without = eligible(price, ref, fold_rebuy_factor(INTERVAL, 0.0))
                assert not (with_fee and not without), (
                    f"fee made ref={ref} price={price} eligible when the "
                    f"interval-only rule did not"
                )


class TestTheCallSiteCarriesTheFeeIntoTheArithmetic:
    """tick()'s own call site is EVALUATED here, not just read.

    A name check passes on a call that mentions ``trading_fee_pct`` but
    passes it somewhere it cannot change the result -- a swapped
    argument, a shadowed name, a value read from the wrong object.
    Running the real expression against two configs that differ only in
    the fee closes that gap.

    IF THIS GOES RED: the fee no longer reaches the fold gate. Every
    fold rebuy then fires at a price that does not clear its own round
    trip. 24 of the 38 live bots run a 1.6 % fee.
    """

    @staticmethod
    def _call_src() -> str:
        """tick()'s single OTD call, as source."""
        calls = [
            n
            for n in ast.walk(_tick())
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "minimum_opposing_trade_distance_pct"
        ]
        assert len(calls) == 1, f"expected one OTD call, found {len(calls)}"
        return ast.unparse(calls[0])

    @classmethod
    def _threshold(cls, interval: float, fee: float) -> float:
        """Evaluate tick()'s call site, then price the $100 reference."""

        class _Config:
            scrumming_interval_pct = interval
            trading_fee_pct = fee

        class _Self:
            config = _Config()

        pct = eval(  # noqa: S307 - our own source, closed namespace
            cls._call_src(),
            {
                "minimum_opposing_trade_distance_pct": (
                    minimum_opposing_trade_distance_pct
                ),
                "getattr": getattr,
                "__builtins__": {},
            },
            {"self": _Self()},
        )
        return REF * fold_rebuy_factor_from_pct(pct)

    def test_the_gate_demands_the_interval_AND_the_fee(self):
        assert self._threshold(1.0, 0.6) == pytest.approx(98.4)

    def test_the_interval_alone_would_put_the_gate_higher(self):
        """What the gate demands when the fee does not reach it.

        This is the number a fee-less call site produces, and it is the
        number this class exists to keep the gate away from.
        """
        assert REF * fold_rebuy_factor_from_pct(
            minimum_opposing_trade_distance_pct(1.0, 0.0)
        ) == pytest.approx(99.0)

    def test_the_gate_is_not_at_the_interval_only_number(self):
        """The discrimination this class rests on."""
        interval_only = REF * fold_rebuy_factor_from_pct(
            minimum_opposing_trade_distance_pct(1.0, 0.0)
        )
        assert self._threshold(1.0, 0.6) != pytest.approx(interval_only)

    def test_the_live_fee_moves_the_gate_further_still(self):
        """24 of the operator's 38 bots run a 1.6 % fee."""
        assert self._threshold(1.0, 1.6) < self._threshold(1.0, 0.6)

    def test_the_call_site_reads_both_fields_off_the_config(self):
        src = self._call_src()
        assert "scrumming_interval_pct" in src, src
        assert "trading_fee_pct" in src, src
