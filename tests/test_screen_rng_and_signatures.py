"""The two presentation screens must not use the ``random`` module.

WHY THIS TEST EXISTS
====================
``splash_screen.py`` and ``investor_screen.py`` draw the splash and the
investor deck. Both drew their decoration from the ``random`` module,
which ruff reports as S311 (a non-cryptographic generator). The repair
uses ``secrets.SystemRandom()``, which reads the operating-system
entropy source, in both files.

``splash_screen`` also seeded the module-level generator with a constant.
That call sets the PROCESS-WIDE generator, so opening the splash changed
the numbers every other part of the application drew from ``random``.
That call is gone with the rest.

``investor_screen._cached_prices`` lost its ``mode`` parameter in the
same repair. ``mode`` picked one of two seeds. It had one call site,
that call site passed nothing, so the second seed was never reached,
and the two seeds changed only a +/-1.25% jitter on one curve.

THE INSTRUMENT
==============
These tests parse each file with ``ast``. A first draft searched the
raw text and failed on the repair's own explanatory COMMENT, which
names the call it removed. Text search cannot tell code from prose;
the parse tree can, so the parse tree is what is read here.

These tests import the modules only. They build no widget and they need
no QApplication, so they cost the suite nothing and cannot crash it.

TWO-SIDED
=========
Put an ``import random`` back in either file and
``test_screen_imports_no_random_module`` fails. Call ``random.seed`` in
either file and ``test_screen_calls_nothing_in_the_random_module``
fails. Add a ``mode`` parameter back to ``_cached_prices`` and
``test_cached_prices_takes_no_mode_argument`` fails.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCREENS = ("splash_screen.py", "investor_screen.py")


def _tree(name: str) -> ast.Module:
    return ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)


def _bound_random_names(tree: ast.Module) -> set[str]:
    """Every local name that the file binds to the ``random`` module."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "random":
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "random":
                names.update(a.asname or a.name for a in node.names)
    return names


@pytest.mark.parametrize("name", SCREENS)
def test_screen_imports_no_random_module(name):
    """No ``import random`` under any alias, no ``from random import``."""
    bound = _bound_random_names(_tree(name))
    assert bound == set(), (
        f"{name} binds the random module as {sorted(bound)}. Use "
        f"secrets.SystemRandom(); ruff reports the random module as S311."
    )


@pytest.mark.parametrize("name", SCREENS)
def test_screen_calls_nothing_in_the_random_module(name):
    """No attribute access on any name bound to ``random``.

    Kept separate from the import check so a reintroduced import and a
    reintroduced call name themselves apart.
    """
    tree = _tree(name)
    bound = _bound_random_names(tree)
    hits = [
        f"{node.value.id}.{node.attr} (line {node.lineno})"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in bound
    ]
    assert hits == [], f"{name} calls into the random module: {hits}"


@pytest.mark.parametrize("name", SCREENS)
def test_screen_uses_the_os_entropy_source(name):
    """Each screen builds its generator with ``SystemRandom()``."""
    tree = _tree(name)
    found = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "SystemRandom"
        for node in ast.walk(tree)
    )
    assert found, f"{name} calls no SystemRandom() constructor"


def test_cached_prices_takes_no_mode_argument():
    """The dead ``mode`` selector stays out of the signature."""
    import investor_screen

    params = list(inspect.signature(investor_screen._cached_prices).parameters)
    assert "mode" not in params, (
        "mode is back. It selected one of two seeds, and the one call "
        "site passes nothing, so the second seed is unreachable."
    )
    assert params == ["n"], params


def test_proof_series_is_built_once_and_is_sane():
    """The cached price series keeps its shape after the RNG swap."""
    import investor_screen

    prices = investor_screen._PROOF_PRICES
    assert len(prices) == 80
    assert all(0.0 < p < 1.5 for p in prices), (min(prices), max(prices))
    # rising curve: the last quarter must sit above the first quarter
    assert sum(prices[-20:]) > sum(prices[:20])
    # the module-level cache is one object, not recomputed per read
    assert investor_screen._PROOF_PRICES is prices


def test_splash_slide_table_stays_paired():
    """Ten slides, ten end times, and ten ``_s_`` callbacks to match."""
    import splash_screen

    assert len(splash_screen.SLIDES) == len(splash_screen.ENDS) == 10
    callbacks = [n for n in dir(splash_screen.SplashScreen) if n.startswith("_s_")]
    assert len(callbacks) == 10, callbacks
    for _start, label in splash_screen.SLIDES:
        assert hasattr(splash_screen.SplashScreen, f"_s_{label}"), label
