"""`tools.conversion_state` counts a module as a Qt surface only when it imports Qt.

The report drives which surface gets converted next. A module that merely names
PySide6 in a docstring, a comment or a warning string is not Qt, and listing one
as remaining work sends a conversion unit at a file with nothing to convert.
"""

from __future__ import annotations

import pathlib

from tools.conversion_state import imports_pyside, split_surfaces


def test_a_plain_import_of_pyside_counts_as_a_qt_surface() -> None:
    text = "import PySide6\n"
    assert imports_pyside(text) is True, "a plain `import PySide6` is a Qt surface"


def test_a_submodule_import_of_pyside_counts_as_a_qt_surface() -> None:
    text = "import PySide6.QtWidgets\n"
    assert imports_pyside(text) is True, "`import PySide6.QtWidgets` is a Qt surface"


def test_a_from_import_of_pyside_counts_as_a_qt_surface() -> None:
    text = "from PySide6.QtWidgets import QWidget\n"
    assert imports_pyside(text) is True, "a `from PySide6...` import is a Qt surface"


def test_pyside_named_only_in_a_string_does_not_count_as_a_qt_surface() -> None:
    text = 'WARNING = "TradingView charts require PySide6-WebEngine"\n'
    assert imports_pyside(text) is False, (
        "a module that only names PySide6 inside a string imports no Qt "
        "and must not be reported as remaining conversion work"
    )


def test_pyside_named_only_in_a_comment_does_not_count_as_a_qt_surface() -> None:
    text = "# the Qt path still uses PySide6\nVALUE = 1\n"
    assert imports_pyside(text) is False, (
        "a comment naming PySide6 imports no Qt"
    )


def test_pyside_named_only_in_a_docstring_does_not_count_as_a_qt_surface() -> None:
    text = '"""Nothing here imports PySide6."""\nVALUE = 1\n'
    assert imports_pyside(text) is False, (
        "a docstring naming PySide6 imports no Qt"
    )


def test_a_module_that_never_names_pyside_does_not_count_as_a_qt_surface() -> None:
    text = "import json\n"
    assert imports_pyside(text) is False, "a module with no PySide6 at all is not Qt"


def test_a_module_naming_pyside_that_cannot_be_parsed_stays_counted() -> None:
    text = "import PySide6\nthis is not python(\n"
    assert imports_pyside(text) is True, (
        "an unparseable module naming PySide6 stays counted, so a file the "
        "tool cannot read is reported rather than dropped from the total"
    )


def _write(folder: pathlib.Path, name: str, text: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def test_a_surface_naming_pyside_in_a_string_is_absent_from_both_lists(
    tmp_path: pathlib.Path,
) -> None:
    gui = tmp_path / "gui"
    _write(gui, "chart_surface.py", 'WARNING = "requires PySide6-WebEngine"\n')

    paired, unpaired = split_surfaces(gui, set())

    assert [p.name for p in unpaired] == [], (
        "a surface that imports no Qt is not remaining conversion work; got "
        + str([p.name for p in unpaired])
    )
    assert [p.name for p in paired] == [], (
        "a surface that imports no Qt is not a Qt surface at all; got "
        + str([p.name for p in paired])
    )


def test_a_widget_that_imports_qt_and_has_no_react_module_is_unpaired(
    tmp_path: pathlib.Path,
) -> None:
    gui = tmp_path / "gui"
    _write(gui, "chart_widget.py", "from PySide6.QtWidgets import QWidget\n")

    paired, unpaired = split_surfaces(gui, set())

    assert [p.name for p in unpaired] == ["chart_widget.py"], (
        "a Qt widget with no React module of the same stem is remaining work; got "
        + str([p.name for p in unpaired])
    )
    assert paired == [], "nothing pairs when no React module exists"


def test_a_widget_that_imports_qt_and_has_a_react_module_is_paired(
    tmp_path: pathlib.Path,
) -> None:
    gui = tmp_path / "gui"
    _write(gui, "chart_widget.py", "from PySide6.QtWidgets import QWidget\n")

    paired, unpaired = split_surfaces(gui, {"chart_widget"})

    assert [p.name for p in paired] == ["chart_widget.py"], (
        "a Qt widget whose stem matches a React module is paired; got "
        + str([p.name for p in paired])
    )
    assert unpaired == [], "a paired widget is not remaining work"
