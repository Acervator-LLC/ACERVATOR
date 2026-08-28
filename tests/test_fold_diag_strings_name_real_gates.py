"""Phase 1 Step 1 — the fold diagnostics must name gates that exist.

THE EXECUTOR'S ACTUAL PREDICATE (scrumming_bot.py, the `_eligible` filter):

    _otd_pct_for_gate = float(config.scrumming_interval_pct or 0)
    _otd_pct_for_gate = max(0.0, min(50.0, _otd_pct_for_gate))
    _otd_factor = 1.0 - (_otd_pct_for_gate / 100.0)
    _eligible = [t for t in self._fold_tranches
                 if ticker.last <= float(t.get("ref", 0)) * _otd_factor]

There is NO `initial_buy_price` term in it. Two operator-facing strings
claimed otherwise:

1. `FOLD: Bought ... (others gated by MEM-171 initial_buy_price floor)`
   named a gate that does not participate in the filter at all.

2. `FOLD_DIAG_NO_STRICT_ELIGIBLE` reported the activation price as
   `_min_ref`, when the executor requires `_min_ref * _otd_factor` --
   materially lower. It told the operator price was closer to firing
   than it was, on every diagnostic tick, and additionally printed a
   `minimum initial_buy` figure that was never binding.

The repair plan's own words: these strings "are the reason seven prior
attempts failed. Every subsequent step is diagnosed by reading the log;
fix the log first."

BLAST RADIUS: zero. String and comment text, plus one variable bound
earlier than before so it is always available to the message. No control
flow, no order size, no order timing.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SRC = (REPO_ROOT / "src" / "trading" / "scrumming_bot.py").read_text(encoding="utf-8")

#: Every module holding part of the ScrummingBot engine.
ENGINE_SRC = "\n".join(
    [SRC]
    + [
        (REPO_ROOT / "src" / "trading" / "scrumming" / name).read_text(encoding="utf-8")
        for name in ("execution.py", "fold_tranches.py", "reconciliation.py")
    ]
)


def _owning_source(method_name: str) -> str:
    """Source of the module that defines ``method_name``, wherever it
    has been extracted to."""
    import inspect

    from src.trading.scrumming_bot import ScrummingBot

    path = inspect.getsourcefile(getattr(ScrummingBot, method_name))
    assert path is not None, method_name
    return Path(path).read_text(encoding="utf-8")


def _tick_source() -> str:
    """ScrummingBot.tick(), selected as the largest `tick` -- several
    classes define one and ast.walk order does not favour the right."""
    ticks = [
        n
        for n in ast.walk(ast.parse(SRC))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "tick"
    ]
    assert ticks, "no tick() found -- the extractor is broken, not the code"
    return (
        ast.get_source_segment(
            SRC, max(ticks, key=lambda n: (n.end_lineno or 0) - n.lineno)
        )
        or ""
    )


def _method_source(name: str) -> str:
    """A named ScrummingBot method, read from the module that owns it."""
    src = _owning_source(name)
    found = [
        n
        for n in ast.walk(ast.parse(src))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    assert found, f"no {name}() found -- the extractor is broken, not the code"
    return (
        ast.get_source_segment(
            src, max(found, key=lambda n: (n.end_lineno or 0) - n.lineno)
        )
        or ""
    )


def _emitted_text(marker: str) -> str:
    """The literal text of the f-string containing `marker`.

    Assertions about what a MESSAGE says must read the message, not the
    source block around it. Source-text matching kept catching the code
    comments that explain each fix -- a comment quoting the phrase it
    removed is indistinguishable from the phrase surviving. The AST has
    no comments in it, so this cannot happen here.

    Returns every constant part of the JoinedStr concatenated, plus the
    source of its interpolations so tests can assert on variable names.
    """
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        parts = [
            v.value
            for v in node.values
            if isinstance(v, ast.Constant) and isinstance(v.value, str)
        ]
        text = "".join(parts)
        if marker not in text:
            continue
        exprs = [
            ast.unparse(v.value)
            for v in node.values
            if isinstance(v, ast.FormattedValue)
        ]
        return text + " || " + " ".join(exprs)
    raise AssertionError(f"no f-string containing {marker!r} was found")


class TestTheExtractorWorks:
    def test_it_finds_the_fold_bought_message(self):
        """POSITIVE CONTROL. Every assertion below is about the content
        of these strings; if the extractor found nothing they would all
        pass vacuously."""
        seg = _tick_source()
        assert 'f"FOLD: Bought' in seg
        assert "FOLD_DIAG_NO_STRICT_ELIGIBLE" in seg

    def test_the_executor_predicate_is_still_otd_only(self):
        """The whole case for these string changes rests on the filter
        having no initial_buy_price term. If that ever changes, these
        pins are wrong and should fail loudly rather than enforce a
        stale claim."""
        seg = _method_source("_fold_eligible_tranches")
        assert "otd_factor" in seg
        assert "initial_buy_price" not in seg


class TestTheBoughtMessageNamesRealGates:
    def test_it_no_longer_blames_the_mem171_floor(self):
        msg = _emitted_text("FOLD: Bought")
        assert "MEM-171 initial_buy_price floor" not in msg, (
            "the success message still blames a gate absent from the "
            "executor's filter"
        )

    def test_it_names_the_otd_gate(self):
        msg = _emitted_text("FOLD: Bought")
        assert "OTD price gate" in msg
        assert "_otd_factor" in msg

    def test_it_names_the_cycle_cap_when_it_bit(self):
        """The cap clause is appended conditionally, so it is its OWN
        f-string node rather than part of the FOLD: Bought literal --
        it only renders when _excluded is non-zero. Asserted by its own
        marker."""
        msg = _emitted_text("more were price-eligible")
        assert "per-cycle cap" in msg
        assert "_excluded" in msg


class TestTheExcludedCounterIsAlwaysBound:
    def test_it_is_initialised_before_the_guard(self):
        """`_excluded` is assigned inside `if _eligible:`. Every path
        reaching the success message passes through that block today,
        but relying on it is one refactor away from a NameError raised
        while reporting a SUCCESSFUL buy -- the worst possible moment."""
        seg = _tick_source()
        init = seg.index("_excluded = 0")
        conditional = seg.index("_excluded = len(_eligible)")
        assert init < conditional, (
            "_excluded is not bound before the conditional assignment " "it backstops"
        )


class TestTheActivationPriceIsTheRealOne:
    def test_it_applies_the_otd_factor(self):
        msg = _emitted_text("FOLD_DIAG_NO_STRICT_ELIGIBLE")
        assert "_otd_diag_factor" in msg or "_activation" in msg

    def test_it_no_longer_quotes_bare_min_ref_as_the_trigger(self):
        """The old text was: "Price needs to drop below ${_min_ref}"."""
        msg = _emitted_text("FOLD_DIAG_NO_STRICT_ELIGIBLE")
        assert "Price needs to drop below" not in msg

    def test_the_irrelevant_initial_buy_figure_is_gone(self):
        msg = _emitted_text("FOLD_DIAG_NO_STRICT_ELIGIBLE")
        assert "minimum initial_buy" not in msg

    def test_the_dead_variable_was_removed_not_orphaned(self):
        """It existed only to be printed. Leaving it computed would be
        dead work on every diagnostic tick."""
        names = {
            n.id for n in ast.walk(ast.parse(ENGINE_SRC)) if isinstance(n, ast.Name)
        }
        assert "_min_initial" not in names, "_min_initial is still a live binding"

    def test_it_still_reports_the_lowest_ref(self):
        """NEGATIVE CONTROL: the fix must not strip the diagnostic bare.
        The operator still needs to know where the queue sits."""
        msg = _emitted_text("FOLD_DIAG_NO_STRICT_ELIGIBLE")
        assert "_min_ref" in msg
