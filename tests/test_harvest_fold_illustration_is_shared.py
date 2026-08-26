"""One harvest-fold illustration, and the Proof scene draws it again.

Issue #128 R2. ``investor_screen.py`` and ``cartoon_screen.py`` each
carried the same 28-line harvest-fold loop -- character for character,
down to ``0.999``, ``st * 0.02``, ``fr * 0.994`` and ``st * 0.97`` --
and neither had a test. It is a caricature for a marketing animation,
not the engine, but a second copy of a strategy is what gets carried
into a rewrite, so it now lives once in ``screen_fx.py`` beside the
animation helpers those two screens already share.

AND THE CONSUMER WAS DEAD. ``InvestorScreen._draw_proof_chart`` called
``self._gen_prices("bull")`` and ``self._sim_hf(prices)``. Neither name
exists on that class or on ``AnimatedScreenBase``, so the Proof scene
raised AttributeError on every frame it was asked for and drew
nothing. ``_PROOF_PRICES``, ``_PROOF_BH`` and ``_PROOF_HF`` were built
at import for that exact chart and nothing read them.

WHAT IS NOT CHANGED. The loop's arithmetic, to the bit. Including
``st += max(0.0, (qty - fq / fr if fr else 0) * p * 0.8)``, where
``fq`` was set to ``0.0`` on the line above, so ``fq / fr`` is always
zero. That is recorded here rather than repaired: this unit moved the
code, it did not redesign the illustration.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

import screen_fx  # noqa: E402


def _prices(n: int = 80) -> list[float]:
    """A rising series with pullbacks, so every branch of the loop runs."""
    import math

    return [0.18 + (i / (n - 1)) * 0.75 + math.sin(i * 0.4) * 0.07 for i in range(n)]


#: The loop's own constants. A function holding all of them is the
#: loop, whatever it calls its variables.
_LOOP_CONSTANTS = frozenset({0.02, 0.005, 0.9, 0.999, 0.994, 0.97, 0.3, 0.8})


def test_neither_screen_carries_the_loop_any_more():
    """A failure means a second copy came back into a screen file.

    READ THROUGH THE AST, not as text. A screen that renamed ``st`` to
    something else would still be a second copy, and a substring scan
    would call it clean.
    """
    for name in ("investor_screen.py", "cartoon_screen.py"):
        source = REPO.joinpath(name).read_text(encoding="utf-8")
        assert "screen_fx.harvest_fold_curve(" in source, name
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            constants = {
                c.value
                for c in ast.walk(node)
                if isinstance(c, ast.Constant) and isinstance(c.value, float)
            }
            assert (
                not _LOOP_CONSTANTS <= constants
            ), f"{name}: {node.name} carries the whole harvest-fold loop again"


def test_every_branch_of_the_illustration_runs_on_this_series():
    """THE CONTROL ON THE FIXTURE.

    A flat or purely rising series never reaches the buy-back or the
    top-up arm, so a curve computed over one would prove nothing about
    the loop. This drives the real function and requires the equity to
    move both ways.
    """
    curve = screen_fx.harvest_fold_curve(_prices())
    assert len(curve) == 80
    assert any(b < a for a, b in zip(curve, curve[1:])), "no drawdown at all"
    assert curve[-1] > curve[0], "the illustration does not accumulate"
    assert all(isinstance(v, float) and v == v for v in curve)


def test_the_two_screens_get_the_same_curve_from_the_same_prices():
    """One spelling means one answer, read through both call sites."""
    import cartoon_screen

    prices = cartoon_screen._PRICES["bull"]
    assert cartoon_screen._SIM["bull"]["hf"] == screen_fx.harvest_fold_curve(prices)


def test_the_proof_chart_constants_are_the_ones_the_scene_reads():
    """The dead consumer, repaired.

    ``_draw_proof_chart``'s body must name the three module constants.
    A failure means it went back to calling methods that do not exist.
    """
    import investor_screen

    text = REPO.joinpath("investor_screen.py").read_text(encoding="utf-8")
    node = next(
        n
        for n in ast.walk(ast.parse(text))
        if isinstance(n, ast.FunctionDef) and n.name == "_draw_proof_chart"
    )
    # NAMES, not source text: the docstring above records what the old
    # body called, and a substring scan would read its own explanation.
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    assert {"_PROOF_PRICES", "_PROOF_HF", "_PROOF_BH"} <= names
    assert "_gen_prices" not in attrs and "_sim_hf" not in attrs
    assert investor_screen._PROOF_HF == screen_fx.harvest_fold_curve(
        investor_screen._PROOF_PRICES
    )


def test_the_proof_scene_paints_the_curve_instead_of_raising(monkeypatch):
    """THE VACUOUS-PASS CONTROL, read at the pixels.

    Every assertion above would pass on a Proof scene that still
    raised, because none of them calls it. This renders the widget at a
    time inside the Proof scene, twice, with ``_PROOF_HF`` swapped for
    the buy-and-hold curve the second time. Two identical curves put
    the green line on top of the red one, so the frames MUST differ.

    WHY THE SWAP AND NOT A SINGLE RENDER. ``_draw_proof_chart`` used to
    raise ``AttributeError`` on every call, and a paint handler that
    raises leaves the frame as it stood, identically, on both renders.
    So a raise collapses the difference to zero and this assertion
    fails. A single render would have been green on the defect.
    """
    from tests.qt_pixel import ensure_app, render_widget

    import investor_screen

    ensure_app()

    def _frame():
        screen = investor_screen.InvestorScreen()
        screen.resize(800, 600)
        screen._t = 48.0  # inside the Proof scene, chart faded in
        return render_widget(screen, (800, 600))

    real = _frame()
    monkeypatch.setattr(investor_screen, "_PROOF_HF", investor_screen._PROOF_BH)
    flattened = _frame()
    differing = sum(
        1
        for y in range(real.height())
        for x in range(0, real.width(), 2)
        if real.pixelColor(x, y) != flattened.pixelColor(x, y)
    )
    assert differing > 200, (
        "the Proof chart did not paint the harvest-fold curve: "
        f"{differing} differing pixels"
    )
