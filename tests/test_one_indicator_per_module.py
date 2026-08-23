"""One indicator per module, and no indicator reads another's maths.

WHY THIS EXISTS. Indicator formulae are PUBLISHED. Each indicator has
its own discrete maths and is never blended with another's. Issue #73
moved nineteen of them out of one 4,009-line ``ta_engine.py`` into
``src/trading/indicators/``, one file each. A directory layout is a
convention until something fails when it is broken; this file is what
fails.

FOUR THINGS ARE PINNED.

  1. Every indicator module holds EXACTLY ONE indicator. A module that
     re-grows a second one fails here, whatever it is called.
  2. No indicator module imports another indicator module at run time.
     The two shared modules -- ``types`` and ``helpers`` -- are the only
     things an indicator may import, plus one declared exception.
  3. No indicator module CALLS another indicator's public name. Import
     is not the only way to blend: ``tests/test_slingshot_canonical.py``
     already pinned this for Slingshot alone by reading its source. This
     generalises the same check to every unit.
  4. ``ta_engine`` still exports every name it exported before the
     split, and each re-exported name is the SAME OBJECT the package
     defines -- not a copy that could drift.

THE ALLOWLIST IS THE POINT. ``ALLOWED_EDGES`` below is checked for
EQUALITY, not containment: an edge that disappears fails just as loudly
as one that appears. Adding a blend therefore means editing this file
and saying why, in front of the operator.

TWO-SIDED BY CONSTRUCTION. ``TestTheGuardCanFail`` reconstructs each
violation in a temporary directory and asserts the same helpers reject
it. A guard that has never been shown to fail is not evidence.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading import ta_engine  # noqa: E402
from src.trading.indicators import (  # noqa: E402
    INDICATOR_MODULES,
    SHARED_MODULES,
)

PKG = REPO_ROOT / "src" / "trading" / "indicators"

#: The only run-time edges between two units. Heikin Ashi is a candle
#: TRANSFORM -- it returns candles, not a Signal -- and both Landing
#: Strip detectors are defined in terms of it. The engine's own module
#: docstring has said so since Landing Strip v2 shipped: "Uses
#: compute_heikin_ashi() internally -- confirmed [HA/]".
ALLOWED_EDGES = frozenset({
    ("bb_proximity", "heikin_ashi"),
    ("landing_strip", "heikin_ashi"),
})

#: Names an allowed edge may call. Any other name from another module
#: is a blend even when the import is on the list.
ALLOWED_CALLS = frozenset({
    ("bb_proximity", "compute_heikin_ashi"),
    ("landing_strip", "compute_heikin_ashi"),
})


# ── the helpers the guard is built from ──────────────────────────────
# Each takes SOURCE TEXT, so TestTheGuardCanFail can hand them a
# reconstructed violation without writing anything into src/.

def indicator_defs(source: str) -> list[str]:
    """Names in ``source`` that define an indicator.

    An indicator is a top-level class with a ``compute`` method, or a
    top-level ``detect_*`` / ``compute_*`` function. A result dataclass
    such as ``BBProximityResult`` has no ``compute`` and is not one.
    """
    found = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef):
            if any(isinstance(m, ast.FunctionDef) and m.name == "compute"
                   for m in node.body):
                found.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            if node.name.startswith(("detect_", "compute_")):
                found.append(node.name)
    return found


def runtime_sibling_imports(source: str) -> set[str]:
    """Sibling modules ``source`` imports OUTSIDE ``if TYPE_CHECKING``.

    A type-only import cannot carry a number, so it is not a blend. A
    run-time one can.
    """
    tree = ast.parse(source)
    type_only = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for inner in ast.walk(node):
                type_only.add(id(inner))
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or id(node) in type_only:
            continue
        if node.level == 1 and node.module:
            out.add(node.module.split(".")[0])
        elif node.module and node.module.startswith(
                "src.trading.indicators."):
            out.add(node.module.split(".")[3])
    return out


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def called_names(source: str) -> set[str]:
    """Every name ``source`` uses in call position."""
    out = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            out.add(func.id)
        elif isinstance(func, ast.Attribute):
            out.add(func.attr)
    return out


def _read(module: str) -> str:
    return (PKG / (module + ".py")).read_text(encoding="utf-8")


# ── 1. one indicator per module ──────────────────────────────────────

class TestOneIndicatorPerModule:
    @pytest.mark.parametrize("module", sorted(INDICATOR_MODULES))
    def test_the_module_holds_exactly_one(self, module):
        found = indicator_defs(_read(module))
        assert found == [INDICATOR_MODULES[module]], (module, found)

    @pytest.mark.parametrize("module", SHARED_MODULES)
    def test_a_shared_module_holds_none(self, module):
        """``types`` and ``helpers`` carry the seam, not an indicator.

        An indicator that lands here would be shared by every reader
        while looking like infrastructure.
        """
        assert indicator_defs(_read(module)) == [], module

    def test_the_registry_is_the_directory(self):
        """A module added without a line in ``INDICATOR_MODULES`` fails.

        Without this, rule 1 could be satisfied by never registering the
        new module -- the guard would pass by not looking.
        """
        on_disk = {p.stem for p in PKG.glob("*.py")} - {"__init__"}
        declared = set(INDICATOR_MODULES) | set(SHARED_MODULES)
        assert on_disk == declared, on_disk ^ declared

    def test_no_two_modules_define_the_same_name(self):
        """A copied indicator is a blend that no import would reveal."""
        seen: dict[str, str] = {}
        clashes = []
        for module in sorted(INDICATOR_MODULES) + list(SHARED_MODULES):
            for name in indicator_defs(_read(module)):
                if name in seen:
                    clashes.append((name, seen[name], module))
                seen[name] = module
        assert clashes == [], clashes


# ── 2 + 3. no module reads another's maths ───────────────────────────

class TestNoBlending:
    def test_the_run_time_edges_are_exactly_the_allowlist(self):
        edges = set()
        for module in sorted(INDICATOR_MODULES):
            for other in runtime_sibling_imports(_read(module)):
                if other in SHARED_MODULES:
                    continue
                edges.add((module, other))
        assert edges == set(ALLOWED_EDGES), edges ^ set(ALLOWED_EDGES)

    @pytest.mark.parametrize("module", sorted(INDICATOR_MODULES))
    def test_no_other_indicators_name_is_called(self, module):
        others = {name for mod, name in INDICATOR_MODULES.items()
                  if mod != module}
        calls = called_names(_read(module))
        blends = {n for n in calls & others
                  if (module, n) not in ALLOWED_CALLS}
        assert blends == set(), (module, blends)

    def test_the_shared_modules_import_no_indicator(self):
        """The seam may not reach up into a unit.

        ``helpers`` importing ``bollinger`` would make every indicator
        that uses a moving average depend on Bollinger's arithmetic.
        """
        for module in SHARED_MODULES:
            siblings = runtime_sibling_imports(_read(module))
            assert siblings <= set(SHARED_MODULES), (module, siblings)


# ── 4. the public surface did not move ───────────────────────────────

#: Every name `ta_engine` exported before issue #73 split it. Read off
#: the pre-split file, not typed from memory.
PRE_SPLIT_SURFACE = (
    "ADXIndicator", "ATRIndicator", "BBProximityResult", "BollingerBands",
    "Candle", "CandleDomainError", "DEFAULT_WEIGHTS", "FVGIndicator",
    "FVG_BEAR_BOOST", "FVG_BULL_BOOST", "FVG_LOOKBACK", "FVG_PROXIMITY_PCT",
    "HACandle", "HA_BODY_PCT_UNIT", "IchimokuCloud", "KaufmanERIndicator",
    "MACD", "NO_SHRINK_RATIO", "PERCENT_PER_RATIO_UNIT", "RSIIndicator",
    "Signal", "SignalDirection", "SlingshotIndicator", "StochasticRSI",
    "SupertrendIndicator", "TA_RAW_PREFIX", "TighteningResult",
    "VOLUME_SPIKE_PCT", "VX_CEILING", "VX_CEILING_PCT", "VX_FLOOR",
    "VX_FLOOR_PCT", "VolumeAnalysis", "VortexIndicator", "VotingEngine",
    "VotingSummary", "ZScoreIndicator", "_ema", "_sma", "_sma_tail",
    "_stdev", "_stdev_tail", "_true_range", "_window_has_no_range",
    "analyze", "candles_from_raw", "compute_heikin_ashi",
    "detect_bb_proximity", "detect_landing_strip_v2", "detect_m_top",
    "detect_macd_taper", "detect_volume_confirmed_spring", "detect_w_bottom",
)


class TestThePublicSurface:
    @pytest.mark.parametrize("name", PRE_SPLIT_SURFACE)
    def test_the_name_still_resolves_from_ta_engine(self, name):
        assert hasattr(ta_engine, name), name

    @pytest.mark.parametrize("module,name", sorted(INDICATOR_MODULES.items()))
    def test_the_re_export_is_the_same_object(self, module, name):
        """Not a copy. A copy could be repaired on one side only."""
        import importlib
        real = getattr(importlib.import_module(
            "src.trading.indicators." + module), name)
        assert getattr(ta_engine, name) is real, name


# ── the two-sided control ────────────────────────────────────────────

class TestTheGuardCanFail:
    """Each helper is handed a reconstructed violation.

    A green report from a guard that cannot go red says nothing about
    the code. These bodies are the smallest thing that breaks each rule.
    """

    SECOND_INDICATOR = (
        "class AlphaIndicator:\n"
        "    def compute(self, candles):\n"
        "        return 1\n"
        "\n\n"
        "class BetaIndicator:\n"
        "    def compute(self, candles):\n"
        "        return 2\n")

    def test_a_second_indicator_in_one_module_is_seen(self):
        assert indicator_defs(self.SECOND_INDICATOR) == [
            "AlphaIndicator", "BetaIndicator"]

    def test_one_indicator_in_one_module_is_accepted(self):
        good = "class AlphaIndicator:\n    def compute(self, c):\n        return 1\n"
        assert indicator_defs(good) == ["AlphaIndicator"]

    def test_a_result_dataclass_is_not_counted_as_an_indicator(self):
        shape = ("from dataclasses import dataclass\n\n\n"
                 "@dataclass\nclass Result:\n    ok: bool\n")
        assert indicator_defs(shape) == []

    def test_a_run_time_sibling_import_is_seen(self):
        assert runtime_sibling_imports(
            "from .bollinger import BollingerBands\n") == {"bollinger"}

    def test_an_absolute_sibling_import_is_seen(self):
        """The relative form is not the only way in."""
        assert runtime_sibling_imports(
            "from src.trading.indicators.bollinger import BollingerBands\n"
        ) == {"bollinger"}

    def test_a_type_only_import_is_not_counted(self):
        src = ("from typing import TYPE_CHECKING\n\n"
               "if TYPE_CHECKING:\n"
               "    from .bollinger import BollingerBands\n")
        assert runtime_sibling_imports(src) == set()

    def test_a_call_to_another_indicator_is_seen(self):
        src = "def f(c):\n    return BollingerBands().compute(c)\n"
        assert "BollingerBands" in called_names(src)

    def test_a_method_call_is_seen_by_attribute_name(self):
        """``self._bb.compute(c)`` hides the class name behind an
        attribute; the called ATTRIBUTE is still read."""
        src = "def f(self, c):\n    return self._bb.compute_heikin_ashi(c)\n"
        assert "compute_heikin_ashi" in called_names(src)

    def test_a_clean_body_produces_no_finding(self):
        """The other half of the control: a correct module stays green."""
        src = ("from .types import Signal\n"
               "from .helpers import _sma\n\n\n"
               "class AlphaIndicator:\n"
               "    def compute(self, c):\n"
               "        return Signal('a', '1h', 0, _sma(c, 2)[-1])\n")
        assert indicator_defs(src) == ["AlphaIndicator"]
        assert runtime_sibling_imports(src) <= set(SHARED_MODULES)
        assert not (called_names(src) & set(INDICATOR_MODULES.values()))
