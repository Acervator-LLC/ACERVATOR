"""The crash logger must be redirectable away from the live tree.

HOW THIS WAS FOUND
Not by reading code. `tests/conftest.py`'s live-tree guard failed a full
suite run on 2026-08-07 and named the exact file it had modified:

    modified 1 pre-existing file(s) with no live Acervator process
      C:\\Users\\brown\\.acervator_logs\\crash_20260807_064256.log

`main._get_crash_log_path` resolved `Path.home() / ".acervator_logs"`
with no override, so any test that tripped an excepthook appended to a
REAL crash log in the operator's runtime tree. Every other writer
already had this hook -- SIM_LOG_ROOT_ENV, ACERVATOR_TELEMETRY_ROOT,
ACERVATOR_SETTINGS_ROOT -- and this one was missed.

The operator's standing rule: never write to ~/.acervator or
~/.acervator_logs from tests or tooling.

WHY THE CONSTANT IS PINNED HERE
`conftest.py` sets the variable as a LITERAL rather than importing it,
because importing `main` installs the diagnostic hooks and emits a BOOT
line -- which is itself a write, in the fixture meant to prevent writes.
That leaves a rename free to silently un-redirect the guard, so this
test locks the literal to the constant.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MAIN_SRC = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
CONFTEST_SRC = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")


def _module_constant(src: str, name: str):
    """Read a module-level string constant without importing the module."""
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return ast.literal_eval(node.value)
    return None


class TestTheOverrideExists:
    def test_main_declares_a_crash_log_root_env(self):
        """POSITIVE CONTROL: everything below reads this constant."""
        assert _module_constant(MAIN_SRC, "CRASH_LOG_ROOT_ENV") is not None

    def test_the_path_resolver_consults_it(self):
        """Asserted over the AST of the function itself, so a mention in
        a comment cannot satisfy it."""
        fn = next(
            n
            for n in ast.walk(ast.parse(MAIN_SRC))
            if isinstance(n, ast.FunctionDef) and n.name == "_get_crash_log_path"
        )
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
        assert "CRASH_LOG_ROOT_ENV" in names, "_get_crash_log_path ignores the override"

    def test_it_still_defaults_to_the_runtime_tree(self):
        """NEGATIVE CONTROL. With no override set, a real crash on the
        operator's machine must still land where they look for it."""
        fn = next(
            n
            for n in ast.walk(ast.parse(MAIN_SRC))
            if isinstance(n, ast.FunctionDef) and n.name == "_get_crash_log_path"
        )
        seg = ast.get_source_segment(MAIN_SRC, fn) or ""
        assert ".acervator_logs" in seg


class TestConftestActuallyRedirectsIt:
    def test_the_literal_matches_the_constant(self):
        """The whole point. If these drift, the suite writes to the
        operator's tree again and nothing says so."""
        declared = _module_constant(MAIN_SRC, "CRASH_LOG_ROOT_ENV")
        assert declared in CONFTEST_SRC, (
            f"conftest does not set {declared!r}; the crash logger is "
            f"no longer redirected during tests"
        )

    def test_the_variable_is_set_during_this_run(self):
        """Runtime proof, not just source inspection: the fixture is
        session-scoped and autouse, so it is active right now."""
        declared = _module_constant(MAIN_SRC, "CRASH_LOG_ROOT_ENV")
        assert os.environ.get(
            declared
        ), f"{declared} is unset while the suite is running"

    def test_the_redirect_points_outside_the_home_tree(self):
        declared = _module_constant(MAIN_SRC, "CRASH_LOG_ROOT_ENV")
        target = Path(os.environ[declared]).resolve()
        for forbidden in (Path.home() / ".acervator", Path.home() / ".acervator_logs"):
            assert (
                forbidden not in target.parents and target != forbidden
            ), f"crash log redirect resolves into the live tree: {target}"

    def test_conftest_does_not_import_main(self):
        """Importing main installs the excepthooks and emits a BOOT
        line -- a write, from the fixture that exists to stop writes."""
        tree = ast.parse(CONFTEST_SRC)
        imported = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imported.update(a.name.split(".")[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module:
                imported.add(n.module.split(".")[0])
        assert "main" not in imported
