"""`tools.conversion_state` counts a module as a Qt surface only when it imports Qt.

The report drives which surface gets converted next. A module that merely names
PySide6 in a docstring, a comment or a warning string is not Qt, and listing one
as remaining work sends a conversion unit at a file with nothing to convert.
"""

from __future__ import annotations

from tools.conversion_state import imports_pyside


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
