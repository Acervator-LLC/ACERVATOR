"""The scope column of the conversion table, driven against a built tree.

``make_tree`` writes a small repository whose window builds one screen and
leaves another unreachable, so a verdict read at the wrong index cannot pass.
Each test states the tree it built and the answer that tree must produce.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import conversion_scope, conversion_table  # noqa: E402

WINDOW_BUILDS = """
from .live_screen import LiveScreen
from .helpers import helper
from .skeleton_tabs import SkeletonMixin
from .dead_screen import DeadScreen
from .variant_surface import PANEL, surface_class

__all__ = ["DeadScreen"]


class MainWindow(SkeletonMixin):
    def build(self):
        helper()
        self._panel = surface_class(PANEL)()
        return LiveScreen()
"""

WINDOW_ONLY_IMPORTS = WINDOW_BUILDS.replace("        return LiveScreen()\n", "")

FILES = {
    "src/__init__.py": "",
    "src/core/__init__.py": "",
    "src/core/desktop_bridge.py": (
        "from src.gui.main_tabs import panel_surface\n\n\n"
        "def build_registry():\n"
        "    return {panel_surface.METHOD: panel_surface}\n"
    ),
    "src/gui/__init__.py": "",
    "src/gui/live_screen.py": "class LiveScreen:\n    pass\n",
    "src/gui/dead_screen.py": "class DeadScreen:\n    pass\n",
    "src/gui/helpers.py": "def helper():\n    return 1\n",
    "src/gui/skeleton_tabs.py": (
        "class SkeletonMixin:\n"
        "    def _add(self, panel):\n"
        '        self._main_tabs.addTab(panel, "Skeleton")\n'
    ),
    "src/gui/qt_panel.py": "class QtPanel:\n    pass\n",
    "src/gui/react_panel.py": (
        "class ReactPanel:\n" "    def load(self):\n" '        return "panel.js"\n'
    ),
    "src/gui/main_tabs/__init__.py": "",
    "src/gui/main_tabs/panel_surface.py": 'METHOD = "panel.state"\n',
    "src/gui/rendered_screen.py": "class RenderedScreen:\n    pass\n",
    "src/gui/variant_surface.py": (
        'PANEL = "Panel"\n\n\n'
        "def register(screen, qt_loader, react_loader):\n"
        "    return screen\n\n\n"
        "def surface_class(screen):\n"
        "    return screen\n\n\n"
        "def _qt_panel():\n"
        "    from .qt_panel import QtPanel\n\n"
        "    return QtPanel\n\n\n"
        "def _react_panel():\n"
        "    from .react_panel import ReactPanel\n\n"
        "    return ReactPanel\n\n\n"
        "register(PANEL, _qt_panel, _react_panel)\n"
    ),
    "desktop/renderer/module_manifest.js": 'var MODULES = ["panel.js"];\n',
    "desktop/renderer/index.html": '<script src="vendor/react.js"></script>\n',
}

TABLE = """# Heading

| Qt file | React module | Uses React | Bridge | Manifest | RENDERS |
| --- | --- | --- | --- | --- | --- |
| `src/gui/main_window.py` | no | - | yes | no | no |
| `src/gui/live_screen.py` | `live_screen.js` | yes | yes | yes | no |
| `src/gui/dead_screen.py` | `dead_screen.js` | yes | no | yes | no |
| `src/gui/helpers.py` | no | - | no | no | no |
| `src/gui/skeleton_tabs.py` | no | - | yes | no | no |
| `src/gui/qt_panel.py` | no | - | no | no | no |
| `src/gui/react_panel.py` | `react_panel.js` | yes | yes | yes | no |
| `src/gui/main_tabs/panel_surface.py` | no | - | yes | no | no |
| `src/gui/rendered_screen.py` | `rendered_screen.js` | yes | yes | yes | yes |

Totals:

```
React module             5
Uses React               4
Bridge                   5
Manifest                 5
RENDERS                  1
```

Tail sentence.
"""


def make_tree(root: pathlib.Path, window: str) -> pathlib.Path:
    """Write the fixture repository under ``root`` with the given window body."""
    for name, body in FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    (root / "src/gui/main_window.py").write_text(window, encoding="utf-8")
    return root


def cells(root: pathlib.Path) -> dict[str, str]:
    """The scope cell of every row of ``TABLE`` measured against ``root``."""
    lines = TABLE.split("\n")
    return conversion_scope.scope_cells(root, conversion_scope.table_rows(lines))


def test_a_screen_the_window_builds_is_in_scope(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_BUILDS))["src/gui/live_screen.py"]
    assert answer.startswith(conversion_scope.IN_SCOPE), answer
    assert "main_window.py" in answer, answer


def test_the_same_screen_is_shelved_when_the_window_stops_building_it(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_ONLY_IMPORTS))["src/gui/live_screen.py"]
    assert answer == conversion_scope.SHELVED, answer


def test_a_screen_nothing_imports_is_shelved(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_BUILDS))["src/gui/dead_screen.py"]
    assert answer == conversion_scope.SHELVED, answer


def test_a_reached_module_defining_no_class_is_not_a_screen(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_BUILDS))["src/gui/helpers.py"]
    assert answer == conversion_scope.NOT_A_SCREEN, answer


def test_a_module_filling_the_window_tab_bar_builds_the_shell(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_BUILDS))["src/gui/skeleton_tabs.py"]
    assert answer == conversion_scope.SHELL, answer


def test_the_window_itself_builds_the_shell(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_BUILDS))["src/gui/main_window.py"]
    assert answer == conversion_scope.SHELL, answer


def test_a_module_loading_a_renderer_file_is_the_react_side(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_BUILDS))["src/gui/react_panel.py"]
    assert answer == conversion_scope.REACT_SIDE, answer


def test_the_qt_half_of_a_loading_pair_is_the_react_side(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_BUILDS))["src/gui/qt_panel.py"]
    assert answer == conversion_scope.REACT_SIDE, answer


def test_a_view_model_the_bridge_registers_is_the_react_side(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_BUILDS))[
        "src/gui/main_tabs/panel_surface.py"
    ]
    assert answer == conversion_scope.REACT_SIDE, answer


def test_a_rendering_row_is_in_scope_whatever_the_walk_says(tmp_path):
    answer = cells(make_tree(tmp_path, WINDOW_BUILDS))["src/gui/rendered_screen.py"]
    assert answer == conversion_scope.IN_SCOPE, answer


def test_the_written_table_carries_one_scope_cell_per_row(tmp_path):
    root = make_tree(tmp_path, WINDOW_BUILDS)
    doc = tmp_path / "table.md"
    doc.write_text(TABLE, encoding="utf-8")
    assert conversion_scope.rewrite(root, doc) is True
    lines = doc.read_text(encoding="utf-8").split("\n")
    start, end = conversion_table.table_span(lines)
    heads = conversion_table.split_cells(lines[start])
    assert heads[-1] == conversion_table.SCOPE_COLUMN, heads
    widths = {
        len(conversion_table.split_cells(lines[i])) for i in range(start, end + 1)
    }
    assert widths == {len(heads)}, widths


def test_the_totals_report_rendering_against_in_scope_and_the_rest(tmp_path):
    root = make_tree(tmp_path, WINDOW_BUILDS)
    doc = tmp_path / "table.md"
    doc.write_text(TABLE, encoding="utf-8")
    conversion_scope.rewrite(root, doc)
    body = doc.read_text(encoding="utf-8")
    assert "RENDERS, in scope        1 of 2" in body, body
    assert "out of scope             7" in body, body


def test_the_totals_carry_no_scope_line_without_the_column():
    lines = TABLE.split("\n")
    block = conversion_table.totals_block(lines)
    assert not any(conversion_table.SCOPE_TOTAL in one for one in block), block
    assert any(one.startswith(conversion_table.LAST_COLUMN) for one in block), block
