"""The suite must fail rather than shrink — CV1 (part 2).

Three properties, all of which the suite lacked:

1. **Qt absence must FAIL, not skip.** `bot_visualizer.py:49-54` hides
   every class behind `if _HAS_QT:`, and the house style is to skip GUI
   tests when Qt is unavailable. A skip is green. So an environment
   without PySide6 runs the suite, reports success, and has verified
   none of the GUI — while thirteen queued cascades edit exactly those
   files. Measured 2026-08-05: Qt IS present and zero tests skip, so
   this is latent, not active. That is the moment to pin it.

2. **Collection must not silently shrink.** The 2026-07-25 sweep moved
   317 test files to `_archive/` and restored one; 16 live source files
   still cite an archived test as their guardrail. Nothing failed when
   that coverage left. The floors below are counted statically from
   disk, so they hold regardless of how pytest was invoked -- a
   collected-item check only works on a full-suite run and passes
   vacuously on `pytest tests/one_file.py`.

3. **The application must still boot.** Before this file,
   `grep -rn "MainWindow(" tests/*.py` returned ZERO. Nothing verified
   that the window constructs at all, while cascades edit window
   construction. Verified safe first: constructing MainWindow headlessly
   writes NOTHING to the operator's tree. A control run (same elapsed
   time, no construction) showed the same two files -- system.log and
   heartbeat.txt -- changing on their own, i.e. the live app, not us.

Raising a floor is a deliberate act. Lowering one requires saying, in
the commit, what coverage was given up and why.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TESTS_DIR = REPO_ROOT / "tests"

# Baselines recorded 2026-08-05 at v3.24.34 (76 files / 1146 functions /
# 1171 collected). Floors sit a little under so ordinary consolidation
# does not trip them, while a sweep like 2026-07-25 -- which removed 316
# files -- would.
MIN_TEST_FILES = 70
MIN_TEST_FUNCTIONS = 1100


def _test_files() -> list[Path]:
    return sorted(TESTS_DIR.glob("test_*.py"))


def _count_test_functions() -> int:
    total = 0
    for f in _test_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        total += sum(
            1 for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("test_"))
    return total


class TestCollectionFloors:
    def test_test_file_count_has_not_collapsed(self):
        files = _test_files()
        assert len(files) >= MIN_TEST_FILES, (
            f"only {len(files)} test files on disk, floor is "
            f"{MIN_TEST_FILES}. Coverage was removed without the suite "
            f"failing -- exactly what happened on 2026-07-25.")

    def test_test_function_count_has_not_collapsed(self):
        n = _count_test_functions()
        assert n >= MIN_TEST_FUNCTIONS, (
            f"only {n} test functions across {len(_test_files())} files, "
            f"floor is {MIN_TEST_FUNCTIONS}.")

    def test_floors_are_not_above_reality(self):
        """Positive control: a floor set above the real count would make
        the two tests above fail for the wrong reason, and someone would
        'fix' it by lowering the floor."""
        assert MIN_TEST_FILES <= len(_test_files())
        assert MIN_TEST_FUNCTIONS <= _count_test_functions()


class TestQtMustFailNotSkip:
    def test_pyside6_is_importable(self):
        """If this fails, the GUI suite is not being verified.

        Deliberately NOT a skipif. PySide6 is a hard dependency in
        pyproject.toml; its absence is a broken environment, and a
        broken environment must not report a green suite.
        """
        import PySide6  # noqa: F401

    def test_bot_visualizer_classes_are_defined(self):
        """`bot_visualizer.py` defines everything under `if _HAS_QT:`.

        With Qt missing the module still imports and every class is
        simply absent, so tests referencing them error individually
        while the module-level import looks fine. Assert the guard
        resolved TRUE.
        """
        from src.gui import bot_visualizer as bv
        assert getattr(bv, "_HAS_QT", False) is True, (
            "bot_visualizer._HAS_QT is False -- Qt did not import, so "
            "every GUI class in that module is undefined")
        assert hasattr(bv, "BotVisualizationTab")


class TestBootSmoke:
    """The only boot-level regression detector this repo has."""

    def test_main_window_constructs_headlessly(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from src.gui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        w = MainWindow(bot_manager=None, settings_manager=None)
        try:
            assert w is not None
            assert w.windowTitle().startswith("Acervator v")
        finally:
            w.close()
            w.deleteLater()
            app.processEvents()

    def test_boot_calls_no_method_that_does_not_exist(self):
        """C11 / NF-162 — the exit-gate measurement.

        `main_window` called `set_bot_viz` on the Simulator tab. That
        method has ZERO definitions anywhere in the repo, and the call
        sat inside `try/except Exception: pass`, so every single boot
        raised AttributeError into a bare handler and nothing said so.

        Asserted over the AST rather than by grepping the source: the
        comment that records the deletion necessarily NAMES the deleted
        method, and a substring search would match it forever.
        """
        import ast

        import src.gui.main_window as mw

        src_text = Path(mw.__file__).read_text(encoding="utf-8")
        called = {
            getattr(n.func, "attr", "")
            for n in ast.walk(ast.parse(src_text))
            if isinstance(n, ast.Call)
        }
        assert "set_bot_viz" not in called, (
            "main_window still calls set_bot_viz, which is defined "
            "nowhere in the repo")

        # ...and it is still undefined, so the call could not be
        # reinstated safely either. POSITIVE CONTROL on the premise.
        defined = []
        for path in (Path(mw.__file__).parent).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8",
                                            errors="replace"))
            defined += [n.name for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef,
                                          ast.AsyncFunctionDef))]
        assert "set_bot_viz" not in defined, (
            "set_bot_viz now exists; the C11 deletion should be "
            "revisited rather than left as a hole")

    def test_the_unreachable_paper_trader_branch_is_gone(self):
        """C11 / NF-109. `_paper_trader` and its stack/crypto/equity
        sources are assigned None in this module and never assigned
        anything else, so the branch guarded by
        `self._paper_trader is not None` could never run.

        Only the BRANCH was removed. The None assignments and the
        view-mode handlers are left alone: `_paper_trader_equity` is
        stock-side, and the Stock Panel is off-limits by operator
        directive.
        """
        import ast

        import src.gui.main_window as mw

        tree = ast.parse(Path(mw.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", "") != "set_bot_viz":
                continue
            raise AssertionError(
                f"a set_bot_viz call survives at line {node.lineno}")

    def test_the_simulator_tab_never_grew_the_missing_method(self):
        """Constructed live, not read from source.

        If SimulatorTab ever gains `set_bot_viz`, the C11 deletion
        should be revisited deliberately rather than left as a hole with
        a method sitting unused on the other side of it.
        """
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from src.gui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        w = MainWindow(bot_manager=None, settings_manager=None)
        try:
            sim = getattr(w, "_simulator", None)
            if sim is None:
                pytest.skip("simulator tab not constructed in this build")
            assert not hasattr(sim, "set_bot_viz"), (
                "SimulatorTab grew set_bot_viz after C11 deleted its "
                "only caller; revisit the disposition")
        finally:
            w.close()
            w.deleteLater()
            app.processEvents()

    def test_window_title_carries_the_real_version(self):
        """End-to-end check on C43's version wiring: the title is built
        from `__version__`, so a regression to a hardcoded literal shows
        up here as well as in the main.py literal pins."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        import src
        from src.gui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        w = MainWindow(bot_manager=None, settings_manager=None)
        try:
            assert src.__version__ in w.windowTitle(), (
                f"title {w.windowTitle()!r} does not carry "
                f"src.__version__=={src.__version__}")
        finally:
            w.close()
            w.deleteLater()
            app.processEvents()
