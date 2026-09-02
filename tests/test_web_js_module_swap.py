"""Drives ``swap_module`` in ``tests/fixtures/web_js_modules.py``.

``swap_module`` writes a changed copy of a shipped ``src/gui/web``
module and puts the original back. A restore that failed quietly once
left a written line in the product, so every check here asks the
helper to fail and reads what it did to the file on disk.
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from tests.fixtures.web_js_modules import SWAP_ATTEMPTS, swap_module

#: The module the swap lives in, so a check can stand in for its ``os``.
web_js_modules = importlib.import_module("tests.fixtures.web_js_modules")

ORIGINAL = b"(function (w) {\n  w.acervatorThing = 1;\n})(window);\n"
CHANGED = ORIGINAL + b"var written = 12;\n"
OTHER = b"var not_what_was_written = 1;\n"

#: Every React test file this helper replaced a local copy in.
CALL_SITE_MODULES = (
    "test_react_bot_status_table",
    "test_react_bot_visualizer",
    "test_react_console_log",
    "test_react_console_tab",
    "test_react_dashboard_stat_card",
    "test_react_header_strip",
    "test_react_journal_tab",
    "test_react_live_status_tab",
    "test_react_market_inspector_tab",
    "test_react_notification_spool",
    "test_react_privacy_dot",
    "test_react_sim_stat_strip",
    "test_react_simulator_tab",
    "test_react_status_log",
    "test_react_trade_charts_tab",
    "test_react_trading_tab",
)


@pytest.fixture()
def module_file(tmp_path: Path) -> Path:
    target = tmp_path / "thing.js"
    target.write_bytes(ORIGINAL)
    return target


class DeniesTheFirstReplaces:
    """Stands in for ``os`` and denies the first ``denials`` replaces."""

    def __init__(self, denials: int) -> None:
        self.denials = denials
        self.calls = 0

    def getpid(self) -> int:
        return os.getpid()

    def replace(self, src: Any, dst: Any) -> None:
        self.calls += 1
        if self.calls <= self.denials:
            raise PermissionError(5, "Access is denied")
        os.replace(src, dst)


class LandsOtherBytes:
    """Stands in for ``os`` and replaces with bytes nobody asked for."""

    def getpid(self) -> int:
        return os.getpid()

    def replace(self, src: Any, dst: Any) -> None:
        Path(str(dst)).write_bytes(OTHER)
        Path(str(src)).unlink()


def a_swap_module_of_its_own(module_path: Path, content: bytes) -> None:
    """A second ``swap_module``, bound into a module by the check below."""
    module_path.write_bytes(content)


def uses_the_shared_swap(module: types.ModuleType) -> bool:
    """Whether ``module`` binds the shared ``swap_module`` and no other."""
    return getattr(module, "swap_module", None) is web_js_modules.swap_module


def test_a_denied_first_replace_still_leaves_the_file_holding_the_content(
    module_file: Path, monkeypatch: pytest.MonkeyPatch
):
    denier = DeniesTheFirstReplaces(denials=1)
    monkeypatch.setattr(web_js_modules, "os", denier)
    swap_module(module_file, CHANGED)
    assert denier.calls == 2, f"the retry made {denier.calls} attempts, wanted 2"
    assert module_file.read_bytes() == CHANGED


def test_a_denied_first_replace_still_puts_the_original_back(
    module_file: Path, monkeypatch: pytest.MonkeyPatch
):
    module_file.write_bytes(CHANGED)
    denier = DeniesTheFirstReplaces(denials=1)
    monkeypatch.setattr(web_js_modules, "os", denier)
    swap_module(module_file, ORIGINAL)
    assert module_file.read_bytes() == ORIGINAL, "the original did not come back"


def test_the_swap_stops_at_its_bound_when_every_replace_is_denied(
    module_file: Path, monkeypatch: pytest.MonkeyPatch
):
    denier = DeniesTheFirstReplaces(denials=10_000)
    monkeypatch.setattr(web_js_modules, "os", denier)
    with pytest.raises(AssertionError) as raised:
        swap_module(module_file, CHANGED, attempts=7)
    assert denier.calls == 7, f"the retry made {denier.calls} attempts, wanted 7"
    assert "thing.js" in str(raised.value)
    assert "7 attempts" in str(raised.value)
    assert module_file.read_bytes() == ORIGINAL


def test_the_default_bound_is_the_one_the_shared_helper_publishes():
    taken = inspect.signature(swap_module).parameters["attempts"].default
    assert SWAP_ATTEMPTS == 2000
    assert taken == SWAP_ATTEMPTS, f"the swap defaults to {taken} attempts"


def test_a_swap_with_no_attempts_left_reports_and_writes_nothing(module_file: Path):
    with pytest.raises(AssertionError) as raised:
        swap_module(module_file, CHANGED, attempts=0)
    assert "thing.js" in str(raised.value)
    assert module_file.read_bytes() == ORIGINAL


def test_a_restore_that_lands_the_wrong_bytes_is_reported_by_name(
    module_file: Path, monkeypatch: pytest.MonkeyPatch
):
    module_file.write_bytes(CHANGED)
    monkeypatch.setattr(web_js_modules, "os", LandsOtherBytes())
    with pytest.raises(AssertionError) as raised:
        swap_module(module_file, ORIGINAL)
    assert "thing.js" in str(raised.value)
    assert module_file.read_bytes() == OTHER


def test_a_restore_that_lands_the_right_bytes_is_not_reported(module_file: Path):
    module_file.write_bytes(CHANGED)
    swap_module(module_file, ORIGINAL)
    assert module_file.read_bytes() == ORIGINAL


def test_the_swap_leaves_no_spare_file_beside_the_module(module_file: Path):
    swap_module(module_file, CHANGED)
    swap_module(module_file, ORIGINAL)
    left = sorted(p.name for p in module_file.parent.iterdir())
    assert left == ["thing.js"], f"the swap left these files behind: {left}"


def test_a_spare_left_by_a_used_up_swap_is_taken_away(
    module_file: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(web_js_modules, "os", DeniesTheFirstReplaces(denials=10_000))
    with pytest.raises(AssertionError):
        swap_module(module_file, CHANGED, attempts=3)
    left = sorted(p.name for p in module_file.parent.iterdir())
    assert left == ["thing.js"], f"the used-up swap left these files behind: {left}"


@pytest.mark.parametrize("name", CALL_SITE_MODULES)
def test_no_react_test_file_binds_a_swap_module_of_its_own(name: str):
    module = importlib.import_module(name)
    assert uses_the_shared_swap(
        module
    ), f"{name} binds {getattr(module, 'swap_module', None)}, not the shared one"


def test_a_module_with_its_own_swap_module_is_reported_as_such():
    """Proves the check above reads the binding, and does not accept
    every module it is given."""
    local = types.ModuleType("local_swap_example")
    setattr(local, "swap_module", a_swap_module_of_its_own)
    assert not uses_the_shared_swap(local)
    assert not uses_the_shared_swap(types.ModuleType("no_swap_example"))
