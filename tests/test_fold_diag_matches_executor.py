"""Phase 1 Step 2 — the fold instrument must measure the executor.

THE DEFECT
The FOLD_DIAG counters used

    ticker.last < ref AND ticker.last <= initial_buy_price

while the executor that actually fires uses

    ticker.last <= ref * _otd_factor

Three differences, each wrong in some regime: strict `<` versus `<=`; an
`initial_buy_price` term the executor does not have; and no OTD factor at
all, so the counter reported tranches eligible at prices the executor
would refuse and ignored the OTD margin entirely.

WHY IT MATTERS MORE THAN A WRONG NUMBER
These counters are the instrument used to verify Phase 3. An instrument
measuring a different predicate than the thing it reports on cannot
confirm or refute a change to that thing. Every "N of M strict-eligible"
figure ever read out of this log was computed on the wrong criterion --
including the 62.6% figure in
`2026-08-06_analysis_why_folds_do_not_fire.md`, which is corrected there.

THE PREREQUISITE THE PLAN SET, AND WHAT IT FOUND
The repair plan required verifying that `_per_tranche_eligible` and
`_patent_only_eligible` are not read by control flow, and to STOP if
either is. Both ARE read by control flow -- so the check was honoured
rather than waved through, and the branches were read: both gate only
`self._bus.emit("bot.log", ...)`. Neither touches trading. The block sits
inside a `try` and is marked "temporary instrumentation, not
load-bearing". The gate's letter failed, its intent held, and the
deviation is recorded here rather than in a commit nobody re-reads.

SINGLE BINDING
`_otd_pct_for_gate` / `_otd_factor` are hoisted above the diagnostic
block and read by both it and the executor. Two copies of that
arithmetic is precisely how they drifted apart, so the pins below assert
there is exactly one assignment.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SRC = (REPO_ROOT / "src" / "trading" / "scrumming_bot.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)


def _tick():
    ticks = [
        n
        for n in ast.walk(TREE)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "tick"
    ]
    assert ticks, "no tick() found -- extractor broken, not the code"
    return max(ticks, key=lambda n: (n.end_lineno or 0) - n.lineno)


def _comparisons_against(varname: str) -> list[str]:
    """Every comparison in tick() whose source mentions `varname`."""
    out = []
    for n in ast.walk(_tick()):
        if isinstance(n, ast.Compare):
            s = ast.unparse(n)
            if varname in s:
                out.append(s)
    return out


class TestTheExtractorWorks:
    def test_it_finds_eligibility_comparisons(self):
        """POSITIVE CONTROL: if this found none, every assertion below
        would pass against any implementation."""
        assert _comparisons_against("_otd_factor")


class TestOnePredicate:
    def test_every_eligibility_test_uses_the_otd_factor(self):
        """Both the diagnostic counter and the executor filter must
        compare against ref * _otd_factor."""
        cmps = _comparisons_against("_otd_factor")
        assert len(cmps) >= 2, (
            f"expected the diagnostic AND the executor to share the "
            f"predicate; found {len(cmps)}: {cmps}"
        )
        for c in cmps:
            assert "ticker.last <=" in c, c
            assert "_otd_factor" in c

    def test_no_eligibility_test_uses_initial_buy_price_as_a_gate(self):
        """The executor has no such term. A counter that applies one is
        measuring a gate that does not run."""
        for c in _comparisons_against("_otd_factor"):
            assert "initial_buy_price" not in c, (
                f"an eligibility predicate still mixes in " f"initial_buy_price: {c}"
            )

    def test_the_strict_less_than_form_is_gone(self):
        """`ticker.last < ref` (strict) disagrees with the executor's
        `<=` exactly at the boundary.

        Scoped to comparisons that actually involve a TRANCHE ref. The
        first draft matched any strict `<` against ticker.last and
        caught `ticker.last < _required_min`, which is SCRUM-side
        hysteresis against `_hyst_ref_scrum_side` and has nothing to do
        with fold eligibility -- the test was wrong, not the code.
        """
        bad = [
            c
            for c in _comparisons_against("ticker.last")
            if "ticker.last <" in c
            and "ticker.last <=" not in c
            and ("ref" in c or "_t.get" in c or "t.get" in c)
        ]
        assert not bad, f"strict-< eligibility comparison survives: {bad}"


class TestSingleBinding:
    def test_otd_factor_is_assigned_exactly_once(self):
        """Two copies of the arithmetic is how the instrument and the
        executor drifted apart. One binding makes that impossible."""
        assigns = [
            n
            for n in ast.walk(_tick())
            if isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") == "_otd_factor" for t in n.targets)
        ]
        assert len(assigns) == 1, (
            f"_otd_factor is assigned {len(assigns)} times; it must be "
            f"computed once and shared"
        )

    def test_it_is_bound_before_the_diagnostic_block(self):
        seg = ast.get_source_segment(SRC, _tick()) or ""
        assert seg.index("_otd_factor = ") < seg.index("_fold_diag_tick")


class TestTheSecondaryReadingIsLabelled:
    def test_patent_only_is_kept_but_not_called_a_gate(self):
        """NEGATIVE CONTROL on the fix: the initial_buy_price reading is
        still WORTH observing for MEM-171 provenance. It must survive --
        just not as an eligibility criterion."""
        seg = ast.get_source_segment(SRC, _tick()) or ""
        assert "_patent_only_eligible" in seg
        i = seg.index("_patent_only_eligible")
        assert "not a gate" in seg[max(0, i - 700) : i].lower(), (
            "the secondary reading is unlabelled and will be mistaken "
            "for an eligibility criterion again"
        )
