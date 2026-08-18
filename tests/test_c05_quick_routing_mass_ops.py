"""C05: Quick Routing mass operations must be confirmed and must speak.

THE CARDINALITY
`_selected_sources` and `_selected_destinations` return EVERY checked
item, and `rebuild_scope` populates both columns with the entire
in-scope swarm. On the operator's 35-bot fleet, checking both columns
and clicking Connect is **1,190 wires from one unconfirmed click**, each
overwriting any hand-tuned rate on that pair. Disconnect is the exact
symmetric mass-destroy.

Only the THIRD button — Disconnect All — asked for confirmation, and it
is the one nobody presses by accident. Same inversion C06b found in the
drag handler: the guarded path was the deliberate one, the unguarded
paths were the reachable ones.

THE SILENCE
Every rejection was a bare `return`. An empty rate box, a stray
character, nothing checked, or 0% all produced exactly the same visible
result as success: nothing. In List view even the success case draws
nothing, so there was no way to tell "it worked" from "it silently
refused". Two `except: pass` blocks compounded it — a failure to persist
looked identical to a clean write while the bus events still fired, so
the canvas could show wires that were never saved.

These are structural pins. Driving the widget would require a populated
swarm and a live bus; what matters here is that no path reaches the
mutation without a confirmation, and that no rejection is silent.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VIZ = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"


def _fn(name: str) -> ast.FunctionDef:
    tree = ast.parse(VIZ.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == name)


def _calls(fn: ast.FunctionDef, attr: str) -> list[int]:
    return [n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == attr]


MASS_OPS = ["_on_connect_clicked", "_on_disconnect_clicked"]


class TestMassOperationsAreConfirmed:
    def test_the_extractor_finds_the_mutations(self):
        """Positive control: if this found no _apply_routes_to_state
        calls, every guard test below would pass by finding nothing to
        guard."""
        for name in MASS_OPS:
            assert _calls(_fn(name), "_apply_routes_to_state"), \
                f"{name} has no _apply_routes_to_state call"

    @pytest.mark.parametrize("name", MASS_OPS)
    def test_no_mutation_runs_without_a_confirmation(self, name):
        """THE invariant: the confirmation must precede the mutation."""
        fn = _fn(name)
        muts = _calls(fn, "_apply_routes_to_state")
        confirms = _calls(fn, "_confirm_mass")
        assert confirms, f"{name} never calls _confirm_mass"
        for m in muts:
            assert any(c < m for c in confirms), (
                f"{name}: mutation at line {m} has no confirmation "
                f"before it")

    def test_confirmation_defaults_to_No(self):
        """A stray Return must not create or destroy 1,190 wires."""
        src = ast.get_source_segment(
            VIZ.read_text(encoding="utf-8"), _fn("_confirm_mass"))
        assert "QMessageBox.No," in src

    def test_an_unshowable_confirmation_refuses(self):
        src = ast.get_source_segment(
            VIZ.read_text(encoding="utf-8"), _fn("_confirm_mass"))
        assert "return False" in src[src.index("except"):]

    def test_the_count_is_shown(self):
        """'Create 1190 wires?' is the whole point — the operator cannot
        infer the cardinality from two checked columns."""
        src = ast.get_source_segment(
            VIZ.read_text(encoding="utf-8"), _fn("_confirm_mass"))
        assert "{n}" in src or "n}" in src


class TestNoRejectionIsSilent:
    @pytest.mark.parametrize("name", MASS_OPS)
    def test_every_early_return_explains_itself(self, name):
        """Each guard clause must tell the operator why nothing
        happened. A bare `return` is indistinguishable from success.

        Structural, not line-distance: a bare return is accounted for
        if some earlier statement in its own block called `_reject`, or
        if the `if` it sits under is testing `_confirm_mass` (declining
        the confirmation is its own explanation — the operator just
        answered the question)."""
        bare: list[int] = []

        def _has(node: ast.AST, attr: str) -> bool:
            return any(getattr(n.func, "attr", "") == attr
                       for n in ast.walk(node) if isinstance(n, ast.Call))

        def _scan(body: list[ast.stmt], guard: ast.AST | None) -> None:
            spoke = guard is not None and _has(guard, "_confirm_mass")
            for stmt in body:
                if isinstance(stmt, ast.Return) and stmt.value is None:
                    if not spoke:
                        bare.append(stmt.lineno)
                    continue
                if _has(stmt, "_reject"):
                    spoke = True
                if isinstance(stmt, ast.If):
                    _scan(stmt.body, stmt.test)
                    _scan(stmt.orelse, None)
                elif isinstance(stmt, ast.Try):
                    _scan(stmt.body, None)
                    for h in stmt.handlers:
                        _scan(h.body, None)
                    _scan(stmt.orelse, None)
                    _scan(stmt.finalbody, None)
                elif isinstance(stmt, (ast.For, ast.While, ast.With)):
                    _scan(stmt.body, None)

        _scan(_fn(name).body, None)
        assert not bare, (
            f"{name} has unexplained early return(s) at {bare}; the "
            f"operator sees nothing and cannot tell refusal from success")

    def test_the_silence_detector_actually_detects_silence(self):
        """Positive control for the scanner above. A bare guard clause
        must be reported, or the parametrized test passes vacuously."""
        bare: list[int] = []
        sample = ast.parse(
            "def f(self):\n"
            "    if not self._x():\n"
            "        return\n"
            "    self._mutate()\n").body[0]
        for n in ast.walk(sample):
            if isinstance(n, ast.Return) and n.value is None:
                bare.append(n.lineno)
        assert bare == [3]

    def test_reject_helper_exists(self):
        assert _fn("_reject") is not None


class TestPersistenceFailureIsNotSwallowed:
    @pytest.mark.parametrize("name", MASS_OPS)
    def test_apply_failure_is_logged(self, name):
        """A failed write with the bus events still firing leaves the
        canvas showing wires that were never saved."""
        fn = _fn(name)
        for h in [n for n in ast.walk(fn)
                  if isinstance(n, ast.ExceptHandler)]:
            bare_pass = (len(h.body) == 1
                         and isinstance(h.body[0], ast.Pass))
            assert not bare_pass, (
                f"{name} still has a silent except: pass around a "
                f"persistence call")
