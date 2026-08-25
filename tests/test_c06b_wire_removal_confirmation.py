"""C06b: destructive wire gestures must be confirmed.

THE DEFECT
`_finish_wire_drag` had two paths that destroyed a live Smart Wire with
no dialog and no undo:

  1. dragging between two ALREADY-CONNECTED bots — the gesture the
     header advertises as "Drag between bots to connect"
  2. releasing a drag on empty space, when the source bot had exactly
     ONE outgoing wire

`mousePressEvent` starts a drag on ANY left-press landing on a locust —
no handle, no hotspot, no modifier — and `mouseReleaseEvent` calls
`_finish_wire_drag` unconditionally. So a press that slips 2-3 px off a
locust edge counted as "dragged to empty space" and deleted that bot's
only wire. `remove_wire` emits `wire.removed`, which reaches
`SmartWireManager.unregister_wire` — engine state, not a drawing.

THE ASYMMETRY THAT HID IT
With MORE than one outgoing wire the operator got a disconnect picker.
With exactly one, nothing. Having fewer wires was more dangerous. And
the confirmation that did exist was on "Disconnect All" — the button
nobody presses by accident — while the two paths reachable from an
ordinary mouse slip had none.

Ordered before C04 deliberately: the broken wire-canvas overlay is
currently the only thing shielding the default List view from these
gestures, so fixing the overlay first would ARM them.
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
    return next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name
    )


def _calls(fn: ast.FunctionDef, attr: str) -> list[int]:
    return [
        n.lineno
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == attr
    ]


class TestEveryRemovalIsGuarded:
    def test_the_extractor_finds_the_removals(self):
        """Positive control: if this walk found no remove_wire calls,
        every test below would pass by finding nothing to guard."""
        assert _calls(
            _fn("_finish_wire_drag"), "remove_wire"
        ), "no remove_wire calls found in _finish_wire_drag"

    def test_no_removal_runs_without_a_confirmation(self):
        """THE invariant. Every remove_wire in the drag handler must be
        preceded by a confirmation call in the same function."""
        fn = _fn("_finish_wire_drag")
        removals = _calls(fn, "remove_wire")
        confirms = _calls(fn, "_confirm_wire_removal")
        assert len(confirms) >= len(removals), (
            f"{len(removals)} remove_wire call(s) but only "
            f"{len(confirms)} confirmation(s) in _finish_wire_drag"
        )
        for r in removals:
            assert any(
                c < r for c in confirms
            ), f"remove_wire at line {r} has no confirmation before it"

    def test_the_helper_exists_and_returns_a_decision(self):
        fn = _fn("_confirm_wire_removal")
        returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
        assert (
            len(returns) >= 2
        ), "confirmation helper must be able to both accept and refuse"


class TestTheDialogDefaultsToSafety:
    def test_default_button_is_No(self):
        """A stray Return keypress must not destroy a wire. Mirrors the
        Disconnect All dialog, which already defaulted to No."""
        src = ast.get_source_segment(
            VIZ.read_text(encoding="utf-8"), _fn("_confirm_wire_removal")
        )
        assert (
            "QMessageBox.No," in src
        ), "confirmation does not pass No as the default button"

    def test_an_unshowable_dialog_refuses(self):
        """If the dialog cannot be shown, the destructive action must
        NOT proceed unconfirmed. Fail closed."""
        src = ast.get_source_segment(
            VIZ.read_text(encoding="utf-8"), _fn("_confirm_wire_removal")
        )
        tail = src[src.index("except") :]
        assert (
            "return False" in tail
        ), "an unshowable confirmation must refuse, not proceed"

    def test_the_pct_is_shown(self):
        """The routing percentage is the part that cannot be
        reconstructed from memory — the operator knows which bots were
        wired, rarely at what rate."""
        src = ast.get_source_segment(
            VIZ.read_text(encoding="utf-8"), _fn("_confirm_wire_removal")
        )
        assert "pct" in src


class TestLoggerIsBound:
    """Found while adding a logger.error to this file.

    `logger` was used at one pre-existing site with NO module-level
    binding and no `import logging` — a latent NameError sitting inside
    an `except` handler, so firing it would have raised OUT of the
    handler. Same shape as NF-154 in main.py earlier in this series.
    """

    def test_module_binds_logger(self):
        import src.gui.bot_visualizer as bv

        assert hasattr(bv, "logger"), (
            "bot_visualizer uses logger.* but never binds it; every "
            "such call is a NameError waiting inside an except handler"
        )

    def test_every_logger_use_has_a_binding(self):
        """Generalised: any module-level name used as `logger.x` must be
        bound in the module."""
        tree = ast.parse(VIZ.read_text(encoding="utf-8"))
        uses = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "logger"
        ]
        assert uses, "positive control: no logger.* uses found"
        bound = any(
            isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "logger" for t in n.targets)
            for n in tree.body
        )
        assert bound, f"{len(uses)} logger.* uses, no module-level binding"
