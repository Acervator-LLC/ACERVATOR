"""Acervator source-tree integration pins.

Purpose: catch import-integrity breakage across src/ subpackages
without spinning up Qt or a running app. These are the smallest
tests that would have caught the "SADP tree deleted, imports left
dangling" class of failure — plus a few end-to-end shape pins on
the entry points the build depends on.

If a src/ module refactor breaks module-level imports, at least
one of these will fail. If a module has runtime deps we can't
satisfy in a headless test env (e.g., PySide6 QApplication), the
test explicitly xfails with the reason so the gap is visible.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Import-integrity: every top-level src/ subpackage must import
# ---------------------------------------------------------------------------


class TestSrcImports:
    def test_src_package_importable(self):
        m = importlib.import_module("src")
        assert hasattr(m, "__version__")
        assert isinstance(m.__version__, str)
        assert len(m.__version__.split(".")) == 3, "SemVer expected"

    def test_src_version_matches_pyproject_or_at_least_looks_sane(self):
        import src
        # Must be a non-empty semver-looking string
        parts = src.__version__.split(".")
        assert all(p.isdigit() for p in parts), \
            f"non-numeric version parts: {src.__version__}"

    @pytest.mark.parametrize("subpkg", [
        "src.core",
        "src.trading",
        "src.exchange",
        "src.competition",
        "src.stocks",
        "src.utils",
    ])
    def test_subpackage_imports(self, subpkg):
        """Every non-Qt subpackage must import cleanly."""
        importlib.import_module(subpkg)

    def test_gui_subpackage_imports_under_offscreen_qt(self, monkeypatch):
        """src.gui pulls PySide6; run headless."""
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        try:
            importlib.import_module("src.gui")
        except ImportError as e:
            pytest.xfail(f"src.gui import failed (likely PySide6 env): {e}")


class TestWatchdog:
    def test_acervator_watchdog_importable(self):
        importlib.import_module("acervator_watchdog")

    def test_watchdog_has_public_surface(self):
        """MEM-219 self-supervising watchdog must expose at least one
        public entry point (class or function). Loose contract on
        purpose — the exact name may shift but SOMETHING must be
        importable."""
        m = importlib.import_module("acervator_watchdog")
        public = [n for n in dir(m) if not n.startswith("_")]
        assert public, "acervator_watchdog has no public attributes"


class TestMainEntry:
    def test_main_py_parses(self):
        """main.py is the PyInstaller entry. Must parse as valid Python."""
        import ast
        text = (REPO / "main.py").read_text(encoding="utf-8", errors="replace")
        ast.parse(text)  # will raise SyntaxError on breakage


# ---------------------------------------------------------------------------
# Entry-point contracts — modules the build spec's hiddenimports rely on
# ---------------------------------------------------------------------------


class TestBuildSpecHiddenImportsResolve:
    """Every module in Acervator_win.spec's hiddenimports MUST import
    cleanly, OR PyInstaller will silently produce a broken .exe."""

    @pytest.fixture(scope="class")
    def spec_hidden_imports(self):
        """Extract ccxt.async_support.* names from the win spec."""
        import re
        spec = (REPO / "Acervator_win.spec").read_text(encoding="utf-8")
        # Extract quoted strings inside hiddenimports=[...]
        m = re.search(
            r"hiddenimports=\(.*?collect_submodules\('src'\)\s*\+\s*\[(.*?)\]",
            spec, re.DOTALL,
        )
        assert m, "could not find hiddenimports block"
        return set(re.findall(r"['\"]([A-Za-z0-9_.]+)['\"]", m.group(1)))

    def test_hiddenimports_extraction_works(self, spec_hidden_imports):
        assert len(spec_hidden_imports) > 10, (
            f"unexpectedly few hidden imports: {spec_hidden_imports}"
        )

    def test_ccxt_exchange_hidden_imports_resolve(self, spec_hidden_imports):
        """ccxt.async_support.<exchange> imports declared in the spec
        must actually exist. If ccxt updates and drops an exchange, this
        catches it before PyInstaller does."""
        ccxt_names = [n for n in spec_hidden_imports
                      if n.startswith("ccxt.async_support.")]
        missing = []
        for name in ccxt_names:
            try:
                importlib.import_module(name)
            except ImportError:
                missing.append(name)
        assert not missing, f"ccxt hidden imports missing: {missing}"

    def test_watchdog_in_hidden_imports(self, spec_hidden_imports):
        """MEM-219 discipline: acervator_watchdog must always be a hidden
        import on both specs. Also pinned in test_specs_parity but this
        is a live-import check, not a text check."""
        assert "acervator_watchdog" in spec_hidden_imports
        importlib.import_module("acervator_watchdog")


# ---------------------------------------------------------------------------
# Trading subpackage contracts — key symbols must remain importable.
# These are pins against the specific class of failure the operator hit
# with the BotConfig position_count error (silent surface drift).
# ---------------------------------------------------------------------------


class TestTradingSurface:
    """The src/trading package exposes the primary bot machinery. A
    silent rename or removal of a public class here breaks the app at
    runtime. These pins catch that at test time."""

    def test_trading_package_importable(self):
        importlib.import_module("src.trading")

    def test_bot_config_or_equivalent_exists(self):
        """Locate the BotConfig class (or its current equivalent). If
        it doesn't exist at all under src.trading, the bot-creation
        flow is broken beyond a mere kwarg mismatch."""
        pkg = importlib.import_module("src.trading")
        # Search the package for a BotConfig-shaped class
        import pkgutil
        found: list[str] = []
        for info in pkgutil.iter_modules(pkg.__path__, prefix="src.trading."):
            try:
                mod = importlib.import_module(info.name)
            except Exception:
                continue
            for attr in dir(mod):
                if attr == "BotConfig":
                    found.append(f"{info.name}.BotConfig")
        assert found, (
            "No BotConfig class found anywhere in src.trading — the "
            "bot-creation flow has no configuration class at all"
        )
