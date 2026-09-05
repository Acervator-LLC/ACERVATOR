"""A file held under ``quarantine/`` is out of the tree for every walker.

``classify_path`` must bucket it as junk so ``build_release_zip`` never ships
it, ``_walk`` must not enter the directory, and ``is_source`` must refuse it so
a citation of a retired file cannot resolve against the held copy. Each rule
here is paired with a control on ``LIVE``, ``pkg/test_live.py`` or ``named``.
"""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.repo_tree import is_source, named
from tests.test_every_test_file_is_collected import _walk
from tools.build_release_zip import classify_path

QUARANTINED = Path("quarantine/src/trading/retired_module.py")
LIVE = Path("main.py")


def test_the_release_zip_calls_a_quarantined_file_junk() -> None:
    """A retired module may not travel back to the operator inside the zip."""
    assert classify_path(QUARANTINED, None) == "junk", (
        "quarantine/ is not in JUNK_DIRS, so every retired file ships in the "
        "primary release zip"
    )


def test_the_release_zip_still_calls_a_live_file_primary() -> None:
    """The control: `classify_path` must not call everything junk."""
    assert classify_path(LIVE, None) == "primary"


def _plant(root: Path) -> None:
    """Writes one discovery-named file inside `quarantine/` and one beside it."""
    for rel in ("quarantine/tests/test_held.py", "pkg/test_live.py"):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def test_x():\n    assert True\n", encoding="utf-8")


def test_the_collection_walk_does_not_enter_the_quarantine(tmp_path: Path) -> None:
    """A held test file may not be reported as a test pytest failed to collect."""
    _plant(tmp_path)
    assert "quarantine/tests/test_held.py" not in _walk(tmp_path)[1]


def test_the_collection_walk_still_sees_a_test_beside_it(tmp_path: Path) -> None:
    """The control: `_walk` must still find a discovery-named file."""
    _plant(tmp_path)
    assert "pkg/test_live.py" in _walk(tmp_path)[1]


def test_a_quarantined_path_is_not_source() -> None:
    """A citation may not resolve against the copy held for retirement."""
    assert not is_source(Path("quarantine") / "src" / "trading" / "retired_module.py")


def test_a_repository_path_is_still_source() -> None:
    """The control: `is_source` must not refuse the tree it walks."""
    assert is_source(Path("src") / "trading" / "scrumming_bot.py")
    assert named("scrumming_bot.py"), "named() found no scrumming_bot.py at all"
