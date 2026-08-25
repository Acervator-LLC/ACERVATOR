"""v3.23.64 — pin tests for the Smart Wire Outflow Safety
Arithmetic (SWOS) function.

Full spec:
docs/audits/2026-07-31_smart_wire_outflow_safety_arithmetic.md

Ten explicit tests locked per §7 of the spec plus one extra to
pin the operator-answered §8 decisions (steeper 0.2/2.0 endpoints
and 1 % minimum-export floor)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.smart_wire import compute_safe_outflow_pct  # noqa: E402


# Small helper: default-args kwargs so each test only supplies the
# fields it cares about. Everything else is chosen to be "already
# satisfied" (fold cash covered, no compound target, mid-band).
def _call(**overrides) -> float:
    defaults = dict(
        scrum_profit_usd=100.0,
        target_balance_usd=1000.0,
        current_price=105.0,  # mid-band
        band_lower=100.0,
        band_upper=110.0,
        next_fold_ammo_usd=0.0,  # no fold pressure
        current_cash_usd=1000.0,  # abundant cash
        compound_growth_pct=0.0,  # no compound demand
        retained_this_cycle_usd=0.0,
    )
    defaults.update(overrides)
    return compute_safe_outflow_pct(**defaults)


class TestSWOSFormula:
    # 1
    def test_zero_profit_returns_zero(self):
        assert _call(scrum_profit_usd=0.0) == 0.0

    # 2 — cash=0, price=band_lower, ammo=100, profit=200 → 150 reserved
    # → exportable = 50 → safe_pct = 25 %. Assert `<= 25 %`.
    def test_zero_cash_imminent_fold_high_reserve(self):
        pct = _call(
            scrum_profit_usd=200.0,
            current_price=100.0,  # at band_lower
            band_lower=100.0,
            band_upper=120.0,
            next_fold_ammo_usd=100.0,
            current_cash_usd=0.0,
            compound_growth_pct=0.0,
            retained_this_cycle_usd=0.0,
        )
        # Safety factor at band_lower = 2.0 (per v3.23.64 steeper
        # endpoints). shortfall=100, reserve=100*2.0=200, exportable=0
        assert pct == 0.0, (
            f"At band_lower with zero cash, 200 reserve > 200 profit "
            f"→ 0 exportable. Got {pct}"
        )

    # 3
    def test_full_cash_deep_scrum_high_export(self):
        pct = _call(
            scrum_profit_usd=100.0,
            current_price=120.0,  # at band_upper
            band_lower=100.0,
            band_upper=120.0,
            next_fold_ammo_usd=100.0,
            current_cash_usd=100.0,  # fully covered
            compound_growth_pct=0.0,
            retained_this_cycle_usd=0.0,
        )
        assert pct == 100.0

    # 4
    def test_compound_reserve_satisfies_on_prior_retention(self):
        pct = _call(
            scrum_profit_usd=100.0,
            target_balance_usd=1000.0,
            compound_growth_pct=5.0,  # target=50
            retained_this_cycle_usd=50.0,  # already retained
            next_fold_ammo_usd=0.0,
            current_cash_usd=1000.0,
        )
        assert pct == 100.0

    # 5
    def test_reserves_exceed_profit_returns_zero(self):
        pct = _call(
            scrum_profit_usd=10.0,
            current_price=100.0,  # imminent fold → factor 2.0
            band_lower=100.0,
            band_upper=120.0,
            next_fold_ammo_usd=100.0,  # shortfall=100
            current_cash_usd=0.0,
        )
        # reserve = 100 * 2.0 = 200 > profit=10 → 0
        assert pct == 0.0

    # 6 — Operator Rate binds LOW (composition, done at call site;
    # here we verify the pure function's output remains unclamped).
    def test_operator_rate_bind_composition_at_callsite(self):
        # Pure function returns 80 %; caller does min(rate, 80).
        pct = _call(
            scrum_profit_usd=100.0,
            next_fold_ammo_usd=40.0,  # shortfall=40
            current_cash_usd=0.0,
            current_price=110.0,  # mid → factor 1.1
            band_lower=100.0,
            band_upper=120.0,
        )
        # fold_reserve = 40 * 1.1 = 44 → exportable = 56 → 56 %
        assert pct == pytest.approx(56.0, abs=0.5)
        # Caller composes: min(operator_rate=25, 56) = 25 (illustrated
        # in the SmartWireManager path; the pure function itself does
        # NOT apply the operator ceiling — that's the spec).

    # 7 — Safety binds low case
    def test_safety_binds_low(self):
        pct = _call(
            scrum_profit_usd=100.0,
            next_fold_ammo_usd=80.0,  # big shortfall
            current_cash_usd=0.0,
            current_price=100.5,  # near band_lower
            band_lower=100.0,
            band_upper=120.0,
        )
        # distance=0.025 → factor=0.2+1.8*0.975=1.955
        # reserve=80*1.955=156.4 > 100 → exportable=0
        assert pct == 0.0

    # 8
    def test_degenerate_band_forces_conservative_factor(self):
        pct = _call(
            scrum_profit_usd=200.0,
            band_lower=100.0,
            band_upper=100.0,  # degenerate
            next_fold_ammo_usd=100.0,
            current_cash_usd=0.0,
        )
        # safety_factor = 2.0 forced → reserve=200 → exportable=0
        assert pct == 0.0

    # 9 — Bounded output over a range of inputs.
    def test_output_always_bounded_0_to_100(self):
        for profit in (0.1, 1, 10, 100, 10_000):
            for cash in (0, 100, 1_000_000):
                for ammo in (0, 10, 500):
                    for price in (99, 100, 105, 110, 121):
                        for growth in (0, 1, 10):
                            for retained in (0, 5, 500):
                                v = _call(
                                    scrum_profit_usd=profit,
                                    band_lower=100.0,
                                    band_upper=110.0,
                                    current_price=price,
                                    next_fold_ammo_usd=ammo,
                                    current_cash_usd=cash,
                                    compound_growth_pct=growth,
                                    retained_this_cycle_usd=retained,
                                )
                                assert 0.0 <= v <= 100.0, (
                                    f"Out of range: {v} for inputs "
                                    f"profit={profit} cash={cash} "
                                    f"ammo={ammo} price={price}"
                                )

    # 10 — ammo=0 (no fold reserve); compound alone gates.
    def test_next_fold_ammo_zero_gates_only_on_compound(self):
        pct = _call(
            scrum_profit_usd=200.0,
            next_fold_ammo_usd=0.0,  # no fold reserve
            compound_growth_pct=10.0,
            target_balance_usd=1000.0,  # compound_target=100
            retained_this_cycle_usd=0.0,
        )
        # reserve = 100; exportable = 100; safe_pct = 50 %
        assert pct == 50.0

    # +1 — pin the operator's §8 answers.
    def test_swos_v3_23_64_operator_decisions_pinned(self):
        """The v3.23.64 spec's §8 answers must remain locked:
        - steeper safety factor (0.2 → 2.0)
        - 1 % minimum-export floor drops sub-1 % results to 0."""
        # At band_lower + 0 cash + tiny shortfall, factor=2.0.
        pct = _call(
            scrum_profit_usd=100.0,
            next_fold_ammo_usd=10.0,  # shortfall=10
            current_cash_usd=0.0,
            current_price=100.0,  # band_lower → factor=2.0
            band_lower=100.0,
            band_upper=120.0,
        )
        # reserve = 10 * 2.0 = 20 → exportable = 80 → 80 %
        assert pct == pytest.approx(80.0, abs=0.5)
        # Now nudge to sub-1 % territory: profit is tiny, exportable
        # would be 0.5 % which should snap to 0 (floor).
        pct = _call(
            scrum_profit_usd=100.0,
            next_fold_ammo_usd=100.0,
            current_cash_usd=50.5,
            current_price=110.0,  # mid → factor 1.1
            band_lower=100.0,
            band_upper=120.0,
        )
        # shortfall=49.5, reserve=49.5*1.1=54.45, exportable=45.55
        # safe_pct=45.55 which is > 1 % so it does NOT snap. Confirm:
        assert pct > 40.0
        # Direct floor test: construct an input that yields ~0.5 %.
        pct_dust = _call(
            scrum_profit_usd=100.0,
            next_fold_ammo_usd=99.5,  # shortfall=99.5
            current_cash_usd=0.0,
            current_price=120.0,  # band_upper → factor=0.2
            band_lower=100.0,
            band_upper=120.0,
        )
        # reserve=99.5*0.2=19.9, exportable=80.1, safe_pct=80.1
        # Not dust. Ok — build a real dust case:
        pct_real_dust = _call(
            scrum_profit_usd=1000.0,  # big profit
            next_fold_ammo_usd=1000.0,
            current_cash_usd=100.0,  # shortfall=900
            current_price=120.0,  # factor=0.2
            band_lower=100.0,
            band_upper=120.0,
            compound_growth_pct=9.5,  # target=95
            target_balance_usd=1000.0,
        )
        # fold_reserve = 900 * 0.2 = 180
        # compound_reserve = 95
        # total reserve = 275, exportable = 725, safe_pct = 72.5
        assert pct_real_dust > 70.0
        # Actual dust construction: tune so exportable is 0.5 % of 1000
        pct_tiny = _call(
            scrum_profit_usd=1000.0,
            next_fold_ammo_usd=1000.0,
            current_cash_usd=0.0,
            current_price=120.0,  # factor 0.2
            band_lower=100.0,
            band_upper=120.0,
            compound_growth_pct=79.5,  # target=795
            target_balance_usd=1000.0,
        )
        # fold_reserve=200, compound_reserve=795, total=995
        # exportable=5, safe_pct=0.5 → FLOOR to 0
        assert (
            pct_tiny == 0.0
        ), f"1 % floor must snap sub-1 % results to 0, got {pct_tiny}"


# ------------------------------------------------------------------
# v3.23.65 — integration tests exercise the SmartWireManager call
# path: get_swos_inputs → compute_safe_outflow_pct → divide by N
# outbound wires → min(raw_pct, per_wire_safe_pct).
# ------------------------------------------------------------------

from unittest.mock import MagicMock  # noqa: E402

from src.trading.smart_wire import SmartWireManager  # noqa: E402


class TestSWOSIntegration:
    def _mk_manager(self):
        m = SmartWireManager(wire_back_pct=0.30, mr_fund_pct=0.15)
        m._enabled = True
        m._min_wire = 0.01
        return m

    def _mk_source_bot(self, swos_inputs=None):
        """Bot stub with a get_swos_inputs method returning the
        given dict (or None to simulate a bot without SWOS)."""
        b = MagicMock()
        if swos_inputs is None:
            b.get_swos_inputs = None
        else:
            b.get_swos_inputs = MagicMock(return_value=swos_inputs)
        return b

    def _mk_target_bot(self):
        """Target with apply_wire_income that accepts everything."""
        b = MagicMock()
        b.apply_wire_income = MagicMock(
            return_value={"applied": True, "placement": "tranche"}
        )
        return b

    def test_swos_caps_operator_pct_when_safety_binds_low(self):
        """Safety says 20 %, operator set 50 % → wire fires at 20 %."""
        m = self._mk_manager()
        src = self._mk_source_bot(
            swos_inputs=dict(
                target_balance_usd=1000.0,
                current_price=105.0,
                band_lower=100.0,
                band_upper=110.0,
                next_fold_ammo_usd=80.0,  # forces reserve
                current_cash_usd=20.0,
                compound_growth_pct=0.0,
                retained_this_cycle_usd=0.0,
            )
        )
        tgt = self._mk_target_bot()
        m._bot_refs["src"] = src
        m._bot_refs["tgt"] = tgt
        m._wires["src"] = {"tgt": 50.0}  # operator wants 50 %
        results = m.distribute_fold_profit("src", 100.0, ref="t")
        assert len(results) == 1
        # safe = (60 shortfall * 1.1 mid-safety) = 66 reserve;
        # exportable = 34 → 34 %. One wire, per_wire = 34.
        # min(50, 34) = 34.
        assert results[0]["pct"] == pytest.approx(34.0, abs=1.0)
        assert results[0]["applied"] is True

    def test_swos_divides_across_multiple_outbound_wires(self):
        """Safe = 60 %, 3 outbound wires → each gets 20 %."""
        m = self._mk_manager()
        src = self._mk_source_bot(
            swos_inputs=dict(
                target_balance_usd=1000.0,
                current_price=110.0,  # at upper band
                band_lower=100.0,
                band_upper=110.0,
                next_fold_ammo_usd=200.0,  # shortfall=200
                current_cash_usd=0.0,
                compound_growth_pct=0.0,
                retained_this_cycle_usd=0.0,
            )
        )
        # safety_factor at band_upper = 0.2 → reserve=200*0.2=40
        # exportable = 60 → safe = 60 %
        # 3 wires → per-wire = 20 %
        m._bot_refs["src"] = src
        for tid in ("t1", "t2", "t3"):
            m._bot_refs[tid] = self._mk_target_bot()
        m._wires["src"] = {"t1": 50.0, "t2": 50.0, "t3": 50.0}
        results = m.distribute_fold_profit("src", 100.0, ref="t")
        assert len(results) == 3
        for r in results:
            assert r["pct"] == pytest.approx(20.0, abs=1.0)

    def test_swos_no_op_when_source_lacks_get_swos_inputs(self):
        """Non-ScrummingBot source (e.g. Extractor) — SWOS silently
        skips, operator pct passes through unchanged."""
        m = self._mk_manager()
        src = self._mk_source_bot(swos_inputs=None)  # no getter
        tgt = self._mk_target_bot()
        m._bot_refs["src"] = src
        m._bot_refs["tgt"] = tgt
        m._wires["src"] = {"tgt": 30.0}
        results = m.distribute_fold_profit("src", 100.0, ref="t")
        assert results[0]["pct"] == pytest.approx(30.0)

    def test_swos_operator_pct_wins_when_lower(self):
        """Safety says 80 %, operator set 15 % → wire fires at 15 %."""
        m = self._mk_manager()
        src = self._mk_source_bot(
            swos_inputs=dict(
                target_balance_usd=1000.0,
                current_price=110.0,  # band_upper → factor 0.2
                band_lower=100.0,
                band_upper=110.0,
                next_fold_ammo_usd=50.0,
                current_cash_usd=50.0,  # cash covers fully
                compound_growth_pct=0.0,
                retained_this_cycle_usd=0.0,
            )
        )
        # cash covers fold, no compound → safe=100
        tgt = self._mk_target_bot()
        m._bot_refs["src"] = src
        m._bot_refs["tgt"] = tgt
        m._wires["src"] = {"tgt": 15.0}
        results = m.distribute_fold_profit("src", 100.0, ref="t")
        assert results[0]["pct"] == pytest.approx(15.0)

    def test_swos_zero_safe_pct_dust_skips_wire(self):
        """Safety = 0 (all reserves), operator = 50 → per-wire = 0 →
        share ≈ 0 → wire hits dust-skip (below _min_wire)."""
        m = self._mk_manager()
        src = self._mk_source_bot(
            swos_inputs=dict(
                target_balance_usd=1000.0,
                current_price=100.0,  # at band_lower (factor 2)
                band_lower=100.0,
                band_upper=110.0,
                next_fold_ammo_usd=1000.0,  # big shortfall
                current_cash_usd=0.0,
                compound_growth_pct=0.0,
                retained_this_cycle_usd=0.0,
            )
        )
        # reserve=1000*2=2000 > 100 profit → safe=0
        tgt = self._mk_target_bot()
        m._bot_refs["src"] = src
        m._bot_refs["tgt"] = tgt
        m._wires["src"] = {"tgt": 50.0}
        results = m.distribute_fold_profit("src", 100.0, ref="t")
        assert results[0]["applied"] is False
        assert "below min_wire_amount" in results[0]["reason"]
