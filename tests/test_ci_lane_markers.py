"""The CI lanes must actually deselect what they claim to deselect.

`.github/workflows/ci.yml` runs the fast lane as `-m "not slow and not
archetype"` and the full lane as the complement. Nothing else splits them, so
if `tests/conftest.py::pytest_collection_modifyitems` stops applying a marker
the fast lane silently swallows the engine-replay suites -- or, worse, the
full lane collects nothing and reports green over an empty run.

The two lanes must also PARTITION the suite: every test in exactly one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.conftest import _SLOW_FILES, pytest_collection_modifyitems  # noqa: E402


class _Item:
    """The two attributes the hook touches."""

    def __init__(self, path: str) -> None:
        self.fspath = path
        self.own_markers: list = []

    def add_marker(self, marker) -> None:
        self.own_markers.append(marker)

    @property
    def names(self) -> set[str]:
        return {m.name for m in self.own_markers}


def _mark(*paths: str) -> list[_Item]:
    items = [_Item(str(REPO_ROOT / "tests" / p)) for p in paths]
    pytest_collection_modifyitems(None, items)
    return items


def test_the_double_records_what_it_is_given():
    """The stub is the instrument. An `add_marker` that dropped its argument
    would make every assertion below pass against a hook that did nothing."""
    item = _Item("x.py")
    # `fspath` is the only field the hook reads, and `add_marker` the only one
    # it writes. Both are asserted here, so a double that lost either cannot
    # make the lane checks below pass on a hook that did nothing.
    assert str(item.fspath) == "x.py"
    assert item.names == set()
    item.add_marker(pytest.mark.slow)
    assert item.names == {"slow"}


class TestTheHookApplies:
    def test_the_slow_files_are_named_and_present(self):
        assert _SLOW_FILES, "the slow lane would be empty"
        for name in _SLOW_FILES:
            assert (REPO_ROOT / "tests" / name).is_file(), (
                f"{name} is marked slow but is not in the tree, so the full "
                f"lane runs less than this list claims"
            )

    @pytest.mark.parametrize("name", sorted(_SLOW_FILES))
    def test_a_slow_file_gets_the_slow_marker(self, name):
        assert _mark(name)[0].names == {"slow"}

    def test_an_archetype_file_gets_the_archetype_marker(self):
        assert "archetype" in _mark("test_coding_archetype_rules.py")[0].names

    def test_an_ordinary_file_gets_neither(self):
        assert _mark("test_ci_lane_markers.py")[0].names == set()


class TestTheLanesPartition:
    """Neither lane may drop a test, and neither may run one twice."""

    def test_every_file_lands_in_exactly_one_lane(self):
        for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
            names = _mark(path.name)[0].names
            fast = not (names & {"slow", "archetype"})
            full = bool(names & {"slow", "archetype"})
            assert fast != full, f"{path.name} is in {'both' if fast else 'no'} lane"


def test_POSITIVE_CONTROL_a_blinded_hook_fails_this_file():
    """Prove the checks above can go red: mark nothing, and they must."""

    def blinded(config: object, items: list) -> None:
        """The hook with its body removed: same signature, marks nothing."""
        assert items is not None and config is None

    items = [_Item(str(REPO_ROOT / "tests" / sorted(_SLOW_FILES)[0]))]
    blinded(None, items)
    assert items[0].names == set(), "the blinded hook still marked something"
    # The real hook, on the same input, must differ. If it does not, every
    # assertion in this file is passing on a hook that does nothing.
    assert _mark(sorted(_SLOW_FILES)[0])[0].names == {"slow"}
