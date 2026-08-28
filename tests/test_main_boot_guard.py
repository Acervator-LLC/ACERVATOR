"""The stale-binary boot guard must never raise — C43 step 7 (NF-154).

`_check_stale_dist_binary()` is invoked at main.py module level, and its
own comment states "Guard must NEVER raise - it's purely informational."
It could.

The guard runs at main.py:130. `logger` is not bound until main.py:225.
Bindings available at call time are `os` (:45) and `sys` (:129) - not
`logger`. All three of the guard's diagnostic calls therefore reference
an unbound name:

    :89   inside _read_version's  except -> logger.debug(...)
    :120  inside the marker-write except -> logger.debug(...)
    :124  inside the OUTER guard  except -> logger.debug(...)

The failure chain is what makes this a boot crash rather than a bad log
line:

    1. an inner except fires and calls logger.debug -> NameError
    2. that NameError propagates to the outer `except Exception` at :122
    3. the outer handler calls logger.debug at :124 -> NameError again
    4. nothing catches THIS one; it escapes _check_stale_dist_binary(),
       reaches module level, and kills the process before the GUI starts

The happy path is unaffected, which is why this has never fired: the
guard returns early unless a source tree and a bundle both state a
version and the two differ. It is armed only for the operator running a
source tree next to a stale build - exactly when the warning is
supposed to help.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import main  # noqa: E402


def test_guard_survives_an_exception_in_its_own_body(monkeypatch):
    """Force the guard's try block to throw and assert nothing escapes.

    Before the fix this raised NameError: name 'logger' is not defined,
    from the handler that exists to prevent exactly that.
    """

    def boom(*_a, **_kw):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(os.path, "isfile", boom)
    # Must not raise. A return value is not expected; not dying is.
    main._check_stale_dist_binary()


def test_guard_survives_a_version_parse_failure(monkeypatch):
    """Drive both version readers' failure branches at once.

    `builtins.open` covers the bundle literal reader; `Path.read_text`
    covers the baked-file reader `src._version` uses.
    """
    monkeypatch.setattr(os.path, "isfile", lambda _p: True)

    def bad_open(*_a, **_kw):
        raise OSError("simulated unreadable file")

    monkeypatch.setattr("builtins.open", bad_open)
    monkeypatch.setattr(Path, "read_text", bad_open)
    main._check_stale_dist_binary()


def test_guard_references_no_late_bound_module_global():
    """The only instrument here that can actually catch this.

    The two tests above CANNOT fail, and that is worth stating rather
    than letting them look like coverage: importing `main` executes the
    module to completion, including `logger = logging.getLogger(...)` at
    :225. By the time any in-process test can call the guard, `logger`
    is bound. The defect exists only during the module's own execution
    at :130, which no test can re-enter. Those two pin that the guard is
    robust when called LATER; they say nothing about boot.

    So check the property structurally: the guard must not read any
    module-level name that main.py binds AFTER the guard's call site.
    Only top-level bindings are collected, so nested-function locals
    (`p`, `f`, `line`) and dunders (`__file__`) cannot produce a false
    positive -- the previous version of this test flagged all four.
    """
    import ast

    src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_check_stale_dist_binary"
    )
    call_line = next(
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "id", "") == "_check_stale_dist_binary"
    )

    # Split top-level bindings by whether they land before or after the
    # guard's call site. A name is only a hazard if it is bound EXCLUSIVELY
    # after: main.py imports `os` at :45 and re-imports it at :135, and
    # likewise `sys` at :129/:136, so looking only at the later binding
    # reports both as unbound when neither is.
    early_bound: set[str] = set()
    late_bound: dict[str, int] = {}
    for node in tree.body:  # top level only, not walk
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [(a.asname or a.name).split(".")[0] for a in node.names]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        else:
            continue
        for name in names:
            if node.lineno < call_line:
                early_bound.add(name)
            else:
                late_bound.setdefault(name, node.lineno)

    used = {
        n.id
        for n in ast.walk(fn)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    unbound = sorted(
        f"{n} (bound at :{late_bound[n]})"
        for n in (used & late_bound.keys()) - early_bound
    )
    assert not unbound, (
        f"_check_stale_dist_binary() reads name(s) {unbound} that are not "
        f"bound before its call site at main.py:{call_line}; any branch "
        f"touching them raises NameError at module level and kills boot"
    )
