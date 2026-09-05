"""C10 / SWARM-A8: deleting the last bot must clear the Swarm.

`self._bot_viz.update_bots(all_statuses)` lived inside `if
all_statuses:` on the 2 s dashboard tick. So when the fleet emptied,
the ONE call that would have cleared it was the one call that got
skipped, and the Swarm went on rendering bots that no longer existed --
indefinitely, since every subsequent tick skipped it too.

The removal logic was never broken. `update_bots` drops every widget
whose id is absent from the incoming set, which for `[]` is all of
them. It was simply never called with `[]`.

Two tests, because either alone is insufficient:
  * the behavioural one proves update_bots([]) really does clear, so
    hoisting it out of the guard is a fix and not just a call;
  * the structural one proves it is actually reachable with an empty
    list, which is the part that was broken. A behavioural test alone
    passes on the unfixed source.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.gui.bot_visualizer import BotVisualizationTab  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _main_window_source() -> str:
    import src.gui.main_window as mw

    return Path(mw.__file__).read_text(encoding="utf-8")


def _status(bid):
    return {
        "bot_id": bid,
        "symbol": "BTC/USD",
        "mode": "live",
        "current_holdings": 0.0,
        "stats": {},
    }


class TestUpdateBotsClearsOnEmpty:
    def test_bots_render_first(self, qapp):
        """Positive control: if nothing ever populated, the clearing
        assertion below would pass against any implementation."""
        tab = BotVisualizationTab()
        tab.update_bots([_status("a"), _status("b")])
        assert len(tab._bot_widgets) == 2
        tab.deleteLater()

    def test_an_empty_list_removes_every_widget(self, qapp):
        tab = BotVisualizationTab()
        tab.update_bots([_status("a"), _status("b")])
        tab.update_bots([])
        assert len(tab._bot_widgets) == 0
        tab.deleteLater()

    def test_a_partial_delete_removes_only_the_missing(self, qapp):
        """Negative control: clearing on empty must not mean clearing
        on every update."""
        tab = BotVisualizationTab()
        tab.update_bots([_status("a"), _status("b")])
        tab.update_bots([_status("a")])
        assert set(tab._bot_widgets) == {"a"}
        tab.deleteLater()


class TestTheTickCanActuallyReachIt:
    def test_bot_viz_update_is_not_gated_on_a_non_empty_fleet(self):
        """THE defect. The call must not sit under `if all_statuses:`,
        or the empty case -- the only case that needs it -- is the one
        case it never runs for."""
        # The module file, not `inspect.getsource(MainWindow)`: the class
        # is nested in a `try`, so its source comes back indented.
        tree = ast.parse(_main_window_source())

        gated = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = ast.unparse(node.test)
            if "all_statuses" not in test or test.startswith("not "):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and getattr(inner.func, "attr", "") == "update_bots"
                    and "_bot_viz" in ast.unparse(inner.func)
                ):
                    gated.append((test, inner.lineno))

        assert not gated, (
            f"_bot_viz.update_bots is still gated on a non-empty fleet "
            f"at {gated}; deleting the last bot will leave the Swarm "
            f"rendering bots that no longer exist"
        )

    def test_the_call_still_exists_at_all(self):
        """Positive control for the scanner above: deleting the call
        entirely would also satisfy it."""
        found = [
            n.lineno
            for n in ast.walk(ast.parse(_main_window_source()))
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == "update_bots"
            and "_bot_viz" in ast.unparse(n.func)
        ]
        assert found, "the Swarm is never updated at all"
