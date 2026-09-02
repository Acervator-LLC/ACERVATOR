"""The Qt teardown walk, driven against a top-level list holding a non-widget.

`QApplication.topLevelWidgets()` is documented to hold windows, and the
suite read one entry that was not a window: a C++ address came back
through a `QWidgetItem` wrapper, which has no `hide()`, so the autouse
teardown raised for every test that followed it. These drive the real
teardown and the real leak guard, both taken from `tests/conftest.py`.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from PySide6.QtWidgets import QWidget, QWidgetItem
from shiboken6 import Shiboken

CONFTEST: Any = sys.modules["conftest"]


def _body(fixture: Any) -> Any:
    """Return the function a pytest fixture object wraps."""
    return getattr(fixture, "__wrapped__", fixture)


def _fake_qapplication(entries: list[Any]) -> Any:
    """Return a QApplication stand-in whose top-level list is `entries`."""
    app = types.SimpleNamespace(
        topLevelWidgets=lambda: list(entries),
        processEvents=lambda: None,
    )
    return types.SimpleNamespace(instance=lambda: app)


def _run_teardown(monkeypatch: pytest.MonkeyPatch, entries: list[Any]) -> None:
    monkeypatch.setattr(
        "PySide6.QtWidgets.QApplication", _fake_qapplication(entries), raising=True
    )
    generator = _body(CONFTEST._destroy_qt_widgets)()
    next(generator)
    with pytest.raises(StopIteration):
        next(generator)


def _leak_guard() -> Any:
    request = types.SimpleNamespace(
        module=types.SimpleNamespace(__file__="left_alive.py")
    )
    return _body(CONFTEST._assert_no_widget_leak)(request)


@pytest.mark.usefixtures("qapp")
def test_teardown_survives_a_top_level_entry_that_is_not_a_widget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = QWidget()
    window.show()
    carrier = QWidget()
    entry = QWidgetItem(carrier)

    _run_teardown(monkeypatch, [window, entry])

    assert not Shiboken.isValid(window), (
        "the teardown must still destroy the real window when an entry that "
        "is not a widget shares the list with it"
    )


@pytest.mark.usefixtures("qapp")
def test_a_non_widget_entry_is_recorded_by_its_type_and_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    carrier = QWidget()
    entry = QWidgetItem(carrier)
    address = Shiboken.getCppPointer(entry)[0]
    CONFTEST._ALIASED_ENTRIES.pop(address, None)

    _run_teardown(monkeypatch, [entry])

    assert CONFTEST._ALIASED_ENTRIES.get(address) == "QWidgetItem", (
        "a skipped entry must name itself by type and address, or the next "
        "occurrence is diagnosed from nothing; recorded: "
        f"{CONFTEST._ALIASED_ENTRIES}"
    )


@pytest.mark.usefixtures("qapp")
def test_a_list_of_real_windows_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = QWidget()
    window.show()
    before = dict(CONFTEST._ALIASED_ENTRIES)

    _run_teardown(monkeypatch, [window])

    added = {a: n for a, n in CONFTEST._ALIASED_ENTRIES.items() if a not in before}
    assert added == {}, (
        "a real window must never be recorded as a non-widget entry, or the "
        f"record fills with noise and names nothing; added: {added}"
    )


@pytest.mark.usefixtures("qapp")
def test_the_leak_guard_still_names_a_window_left_alive() -> None:
    generator = _leak_guard()
    next(generator)

    survivor = QWidget()
    survivor.show()

    with pytest.raises(AssertionError) as caught:
        next(generator)

    message = str(caught.value)
    assert "QWidget" in message and "left_alive.py" in message, (
        "the leak guard must still name the type and the file that left a "
        f"top-level widget alive; it said: {message}"
    )
    del survivor


@pytest.mark.usefixtures("qapp")
def test_the_leak_guard_is_quiet_when_nothing_is_left_alive() -> None:
    generator = _leak_guard()
    next(generator)
    with pytest.raises(StopIteration):
        next(generator)
