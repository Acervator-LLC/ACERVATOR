"""B0 - the red that shipped in bot_visualizer.py, pinned so it cannot return.

Measured on the unmodified tree by ``python -m dev_harness.touchset baseline``:
``coding_archetype passed=False, 9 high`` and ``gui_archetype
passed=False, 5 high``. The touch-set tool REFUSED to pin the file. Three
distinct defects produced those fourteen rows:

1. Five ``S311``. The module drew its locust start phase and its particle
   velocities from the ``random`` module's global Mersenne-Twister
   generator.
2. Two ``unused variable`` at 100% confidence. The fallback ``_mask_or``,
   installed when the privacy-mask registry fails to import, took
   ``field_id`` and ``mask`` and read neither.
3. Two ``unused import`` at 90% confidence. ``QCheckBox`` and
   ``QSplitter`` came from ``PySide6.QtWidgets`` and were referenced
   nowhere in the file.

WHAT A FAILURE HERE WOULD MEAN
==============================
``TestNoGlobalPseudoRandom`` - a global-generator draw came back and the
five ``S311`` highs are re-armed, or the generator swap changed the draw
contract rather than only its source.

``TestFallbackMaskOrSignatureParity`` - the fallback drifted from the real
``mask_or``. This is not cosmetic. Two live call sites in this same module
pass ``mask=`` BY KEYWORD, so a renamed parameter raises ``TypeError`` at
paint time, and only on the path where the registry import already failed.

``TestUnusedQtImportsStayRemoved`` - an unused import returned and the two
``dead-code`` highs are re-armed.

EVERY MECHANISM HERE CARRIES A PAIRED CONTROL
=============================================
A probe that answers "no" is worth nothing until it is shown answering
"yes". Each control drives the same probe against a case whose answer is
known to be positive. A failing control means the probe beside it is
blind, so its verdict is void rather than passing.

The registry is broken with a STUB MODULE that lacks the two names, not
with ``None``. That is the realistic shape - a module that loads and does
not carry the symbol - and the ``from ... import`` then raises
``ImportError``, which is what selects the fallback.
"""

from __future__ import annotations

import importlib
import inspect
import math
import os
import secrets
import sys
import types
from collections.abc import Callable, Iterator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from src.core.privacy_mask_registry import mask_or
from src.gui import bot_visualizer as bv

REGISTRY_MODULE = "src.core.privacy_mask_registry"
VISUALIZER_MODULE = "src.gui.bot_visualizer"


@pytest.fixture(scope="module")
def qapp() -> QCoreApplication:
    """Return the process application, creating an offscreen one if needed."""
    existing = QApplication.instance()
    if existing is not None:
        return existing
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication([])


# --------------------------------------------------------------------
# Probes. Each is driven by a test AND by that test's paired control.
# --------------------------------------------------------------------
def _binds_random_module(module: types.ModuleType) -> bool:
    """Report whether ``module`` holds a reference to the stdlib ``random``."""
    return getattr(module, "random", None) is importlib.import_module("random")


def _binds_name(module: types.ModuleType, name: str) -> bool:
    """Report whether ``name`` is bound in the namespace of ``module``."""
    return hasattr(module, name)


def _same_signature(
    left: Callable[..., object],
    right: Callable[..., object],
) -> bool:
    """Report whether two callables accept exactly the same parameters.

    Compare the name, kind and default of every parameter in order. A
    renamed keyword parameter counts as a difference, which is the point:
    callers of the fallback pass ``mask=`` by keyword.
    """
    left_params = list(inspect.signature(left).parameters.values())
    right_params = list(inspect.signature(right).parameters.values())
    if len(left_params) != len(right_params):
        return False
    return all(
        a.name == b.name and a.kind == b.kind and a.default == b.default
        for a, b in zip(left_params, right_params, strict=True)
    )


def _module_that_binds_random() -> types.ModuleType:
    """Build a module that certainly binds ``random``. Control input only."""
    module = types.ModuleType("b0_control_binds_random")
    module.random = importlib.import_module("random")
    return module


class TestNoGlobalPseudoRandom:
    """The five S311 rows, and the draw contract they sat on."""

    def test_module_does_not_bind_the_random_module(self) -> None:
        """Fail means the five S311 highs are re-armed."""
        assert not _binds_random_module(bv)

    def test_the_random_probe_is_not_blind(self) -> None:
        """CONTROL. Fail means the probe cannot see a real binding."""
        assert _binds_random_module(_module_that_binds_random())

    def test_module_draws_from_a_system_entropy_generator(self) -> None:
        """Fail means the replacement generator is not the intended one."""
        assert isinstance(bv._RNG, secrets.SystemRandom)

    @pytest.mark.usefixtures("qapp")
    def test_start_phase_stays_inside_its_declared_range(self) -> None:
        """Fail means the swap changed the draw contract, not only its source."""
        phases = [bv.BotNodeWidget()._phase for _ in range(64)]
        assert all(0.0 <= phase < 2.0 * math.pi for phase in phases)
        assert len(set(phases)) > 1

    @pytest.mark.usefixtures("qapp")
    def test_a_new_trade_still_spawns_the_five_particles(self) -> None:
        """Fail means the particle draw stopped producing usable values."""
        widget = bv.BotNodeWidget()
        widget.resize(112, 98)
        assert widget._particles == []
        widget.set_bot_data({"stats": {"total_trades": 1, "current_price": 10.0}})
        assert len(widget._particles) == 5
        for particle in widget._particles:
            assert -30.0 <= particle.vx <= 30.0
            assert -30.0 <= particle.vy <= 30.0
            assert 0.5 <= particle.life <= 1.5
            assert 1.5 <= particle.size <= 3.5


class TestFallbackMaskOrSignatureParity:
    """The two unused-variable rows, and the contract they sat on."""

    @pytest.fixture
    def fallback_module(self) -> Iterator[types.ModuleType]:
        """Import bot_visualizer with the registry import forced to fail."""
        saved_visualizer = sys.modules.pop(VISUALIZER_MODULE)
        saved_registry = sys.modules.get(REGISTRY_MODULE)
        sys.modules[REGISTRY_MODULE] = types.ModuleType(REGISTRY_MODULE)
        try:
            yield importlib.import_module(VISUALIZER_MODULE)
        finally:
            if saved_registry is not None:
                sys.modules[REGISTRY_MODULE] = saved_registry
            else:
                del sys.modules[REGISTRY_MODULE]
            sys.modules[VISUALIZER_MODULE] = saved_visualizer

    def test_the_fallback_is_the_one_under_test(
        self,
        fallback_module: types.ModuleType,
    ) -> None:
        """CONTROL. Fail means the except branch was never reached, so every
        assertion below was aimed at the real helper instead.
        """
        assert fallback_module._get_privacy_mask_registry is None
        assert fallback_module._mask_or.__module__ == VISUALIZER_MODULE
        assert bv._get_privacy_mask_registry is not None
        assert bv._mask_or.__module__ == REGISTRY_MODULE

    def test_fallback_signature_matches_the_real_helper(
        self,
        fallback_module: types.ModuleType,
    ) -> None:
        """Fail means a keyword caller raises TypeError on the fallback path."""
        assert _same_signature(fallback_module._mask_or, mask_or)

    def test_the_signature_comparison_can_see_a_drift(self) -> None:
        """CONTROL. Fail means the comparison accepts anything."""

        def drifted(value: object, field_id: str, _mask: str = "****") -> str:
            del field_id
            return str(value)

        def shorter(value: object, field_id: str) -> str:
            del field_id
            return str(value)

        assert _same_signature(mask_or, mask_or)
        assert not _same_signature(mask_or, drifted)
        assert not _same_signature(mask_or, shorter)

    def test_fallback_accepts_mask_by_keyword(
        self,
        fallback_module: types.ModuleType,
    ) -> None:
        """Fail means the two live keyword call sites raise on this path."""
        assert (
            fallback_module._mask_or("abcdef", "bot_swarm.identifiers", mask="********")
            == "abcdef"
        )

    def test_fallback_returns_the_plain_value_unmasked(
        self,
        fallback_module: types.ModuleType,
    ) -> None:
        """Fail means discarding the parameters changed what it returns."""
        assert fallback_module._mask_or("SOL-USD", "bot_swarm.identifiers") == "SOL-USD"
        assert fallback_module._mask_or(1234, "bot_swarm.identifiers") == "1234"


class TestUnusedQtImportsStayRemoved:
    """The two unused-import rows."""

    @pytest.mark.parametrize("name", ["QCheckBox", "QSplitter"])
    def test_removed_widget_name_is_not_bound(self, name: str) -> None:
        """Fail means an unused import returned and the high is re-armed."""
        assert not _binds_name(bv, name)

    @pytest.mark.parametrize("name", ["QMenu", "QLineEdit", "QWidget"])
    def test_the_binding_probe_is_not_blind(self, name: str) -> None:
        """CONTROL. Fail means the probe cannot see a name that IS bound."""
        assert _binds_name(bv, name)
