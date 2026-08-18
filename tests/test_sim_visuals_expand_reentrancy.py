"""A second Expand must not orphan the chart into a hidden dialog.

C28, cascade 25. Findings SN-10, SN-36.

THE DEFECT
`_show_expanded` reparents the chart into a modeless `QDialog` and hands
it back on close, remembering where it came from:

    prior_parent = widget.parentWidget()

With the dialog already open, `widget.parentWidget()` is the DIALOG's
container — not the panel. So a second Expand records the dialog as
"home", and on close the chart is handed back into a widget the operator
cannot see. The chart disappears from the panel and there is no way to
retrieve it (SN-10).

SN-36: the dialog is modeless and carries no `WA_DeleteOnClose`, so it
is kept alive by the parent-window chain. Every Expand leaks one.

WHY THE WEAKREF ASSERTION IS DONE THIS WAY
Qt object lifetime is not Python lifetime. A `QDialog` can be destroyed
C++-side while the Python wrapper survives, so `weakref` on the wrapper
proves nothing on its own. The pin below checks the C++ side via
shiboken's `isValid`, and falls back to the wrapper weakref only when
shiboken is unavailable.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.gui.simulator_tab.fleet.sim_visuals import (  # noqa: E402
    _show_expanded,
)


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _panel_with_chart():
    """A panel holding a chart, as the Simulator tab arranges it."""
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    win = QWidget()
    panel = QWidget(win)
    lay = QVBoxLayout(panel)
    chart = QWidget(panel)
    lay.addWidget(chart)
    win.show()
    return win, panel, chart


def _open_dialogs(app):
    from PySide6.QtWidgets import QDialog
    return [w for w in app.topLevelWidgets() if isinstance(w, QDialog)]


class TestTheInstrumentWorks:
    def test_one_expand_reparents_the_chart_away_from_the_panel(self):
        """POSITIVE CONTROL. If Expand did not reparent at all, every
        assertion below would pass for the wrong reason."""
        app = _app()
        win, panel, chart = _panel_with_chart()
        try:
            _show_expanded(chart, "Chart")
            app.processEvents()
            assert chart.parentWidget() is not panel
        finally:
            for d in _open_dialogs(app):
                d.close()
            app.processEvents()
            win.close()

    def test_closing_hands_the_chart_back(self):
        """NEGATIVE CONTROL for the restore path — it must keep working."""
        app = _app()
        win, panel, chart = _panel_with_chart()
        try:
            _show_expanded(chart, "Chart")
            app.processEvents()
            for d in _open_dialogs(app):
                d.close()
            app.processEvents()
            assert chart.parentWidget() is panel
        finally:
            win.close()
            app.processEvents()


class TestASecondExpandCannotOrphanTheChart:
    def test_two_expands_still_return_the_chart_to_the_panel(self):
        """THE exit-gate measurement. Without a guard the second call
        records the DIALOG as home, and the chart is handed back into a
        widget the operator cannot see."""
        app = _app()
        win, panel, chart = _panel_with_chart()
        try:
            _show_expanded(chart, "Chart")
            app.processEvents()
            _show_expanded(chart, "Chart")   # the second click
            app.processEvents()

            for d in _open_dialogs(app):
                d.close()
            app.processEvents()

            assert chart.parentWidget() is panel, (
                "the chart was handed back to a dialog, not the panel")
        finally:
            win.close()
            app.processEvents()

    def test_the_second_expand_opens_no_second_dialog(self):
        app = _app()
        win, panel, chart = _panel_with_chart()
        before = len(_open_dialogs(app))
        try:
            _show_expanded(chart, "Chart")
            app.processEvents()
            _show_expanded(chart, "Chart")
            app.processEvents()
            assert len(_open_dialogs(app)) - before == 1, (
                "a second dialog was opened over the first")
        finally:
            for d in _open_dialogs(app):
                d.close()
            app.processEvents()
            win.close()

    def test_expand_works_again_after_closing(self):
        """The guard must CLEAR. A one-shot Expand would be a worse
        defect than the one being fixed."""
        app = _app()
        win, panel, chart = _panel_with_chart()
        try:
            _show_expanded(chart, "Chart")
            app.processEvents()
            for d in _open_dialogs(app):
                d.close()
            app.processEvents()

            _show_expanded(chart, "Chart")
            app.processEvents()
            assert chart.parentWidget() is not panel, (
                "Expand stopped working after the first use"
            )
        finally:
            for d in _open_dialogs(app):
                d.close()
            app.processEvents()
            win.close()


class TestTheDialogIsDestroyed:
    def test_the_dialog_does_not_outlive_its_close(self):
        """SN-36. Modeless and parented to the window, so without
        WA_DeleteOnClose it is kept alive by the parent chain and every
        Expand leaks one."""
        app = _app()
        win, panel, chart = _panel_with_chart()
        try:
            _show_expanded(chart, "Chart")
            app.processEvents()
            dlgs = _open_dialogs(app)
            assert dlgs, "no dialog was created"
            dlg = dlgs[0]

            dlg.close()
            app.processEvents()
            app.processEvents()

            try:
                import shiboken6
                alive = shiboken6.isValid(dlg)
            except Exception:
                import weakref
                ref = weakref.ref(dlg)
                del dlg
                alive = ref() is not None
            assert not alive, (
                "the dialog survived its close; WA_DeleteOnClose is not "
                "set and each Expand leaks one")
        finally:
            win.close()
            app.processEvents()


class TestTheGuardIsStructural:
    def test_show_expanded_checks_for_an_existing_dialog(self):
        """Asserted over the AST so a comment describing the guard
        cannot satisfy it."""
        import ast

        import src.gui.simulator_tab.fleet.sim_visuals as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_show_expanded")
        # An early return guarding re-entry must exist before the
        # QDialog is constructed.
        ctor = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "QDialog"]
        rets = [n.lineno for n in ast.walk(fn)
                if isinstance(n, ast.Return)]
        assert ctor, "QDialog construction not found"
        assert rets and min(rets) < min(ctor), (
            "no early return guards dialog construction")

    def test_delete_on_close_is_set(self):
        import ast

        import src.gui.simulator_tab.fleet.sim_visuals as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_show_expanded")
        seg = ast.get_source_segment(src, fn) or ""
        assert "WA_DeleteOnClose" in seg
