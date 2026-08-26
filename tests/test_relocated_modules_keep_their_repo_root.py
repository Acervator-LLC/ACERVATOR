"""Issue #128 R1 moved 16 modules out of `src/gui/`. Two things no other
test in this repository can see.

WHY THIS FILE EXISTS
====================
1. `__file__`-RELATIVE PATH MATH. `nuclear_candle_source.py` and
   `populate_nuclear_cache.py` each walk up from `__file__` to the repo
   root by a COUNT of parents. The move made them one directory
   shallower, so the count had to change from 3 to 2. Measured: with the
   old count `_default_cache_dir()` returned
   `.../Temp/sadp/RAIntSimBat/data/cache` instead of
   `.../Temp/r1/sadp/...` -- one level above the repo, silently, with no
   exception. `populate_nuclear_cache.py` is at 0% coverage from the
   whole suite, so nothing else would have caught it.

2. FUNCTION-LOCAL IMPORTS. A deferred import fails at RUNTIME, not at
   collection. Measured on 2026-08-26: `fleet_replay_panel.py:556` was
   deliberately broken back to its pre-move spelling and
   `test_fleet_replay_panel_state_machine.py` still reported 25 passed.
   Collection cannot see a defect inside a method body. The walker here
   grades deferred imports the same as top-level ones.

Both tests carry a control: blind the mechanism and each goes red.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_nuclear_candle_source_still_finds_the_repo_root() -> None:
    """The cache dir hangs off the repo root, not off its parent."""
    from src.simulator import nuclear_candle_source as ncs

    assert ncs._default_cache_dir() == (
        REPO_ROOT / "sadp" / "RAIntSimBat" / "data" / "cache"
    )


def test_populate_nuclear_cache_still_finds_the_repo_root() -> None:
    """0% covered by the rest of the suite. Its refusal names the path."""
    from src.simulator import populate_nuclear_cache as pnc

    with pytest.raises(RuntimeError) as excinfo:
        pnc._load_raintsimbat()
    wanted = (REPO_ROOT / "sadp" / "RAIntSimBat" / "RAIntSimBat.py").as_posix()
    assert wanted in str(excinfo.value).replace("\\", "/")


def _imports_of(path: Path) -> list[tuple[str, int]]:
    """Every import in a file, function-local ones included, resolved."""
    rel = path.resolve().relative_to(REPO_ROOT).with_suffix("")
    pkg = rel.parts if path.name == "__init__.py" else rel.parts[:-1]
    if path.name == "__init__.py":
        pkg = rel.parts[:-1]
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8", errors="replace"))):
        if isinstance(node, ast.Import):
            found += [(alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(pkg[: len(pkg) - (node.level - 1)])
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if module:
                found.append((module, node.lineno))
    return found


def _src_files() -> list[Path]:
    return [
        p
        for p in sorted((REPO_ROOT / "src").rglob("*.py"))
        if "__pycache__" not in p.parts
    ]


# Pre-existing on the unmodified tree and guarded by try/except at the call
# site. No commit ever added `src/gui/paper_trader_tab.py`.
KNOWN_UNRESOLVABLE = {"src/gui/stock_main_window.py:424 -> src.gui.paper_trader_tab"}


def test_every_import_under_src_resolves() -> None:
    """Grep cannot see a deferred import. This walks the AST instead."""
    broken = set()
    for path in _src_files():
        for module, line in _imports_of(path):
            if not module.startswith("src."):
                continue
            try:
                spec = importlib.util.find_spec(module)
            except (ImportError, ModuleNotFoundError, ValueError):
                spec = None
            if spec is None:
                broken.add(
                    f"{path.relative_to(REPO_ROOT).as_posix()}:{line} -> {module}"
                )
    assert broken - KNOWN_UNRESOLVABLE == set(), "unresolvable:\n  " + "\n  ".join(
        sorted(broken - KNOWN_UNRESOLVABLE)
    )
    assert broken == KNOWN_UNRESOLVABLE, f"the known finding changed: {sorted(broken)}"


def test_the_walker_reads_deferred_imports() -> None:
    """CONTROL. `fleet_replay_panel.py:556` sits inside a method.

    If the walker only read module-level imports these 2 names would be
    absent and the test above would grade nothing.
    """
    panel = REPO_ROOT / "src/gui/simulator_tab/fleet/fleet_replay_panel.py"
    top_level = {
        node.module
        for node in ast.parse(panel.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    walked = {module for module, _ in _imports_of(panel)}
    for deferred in (
        "src.simulator.fleet.fleet_replay_controller",
        "src.exchange.history_helpers",
    ):
        assert deferred in walked, deferred
        assert deferred not in top_level, f"{deferred} is no longer deferred"
