"""``MainWindow`` draws its tab bar in React under the React build.

``Window`` builds the shipped ``MainWindow`` under one variant and shows it.
Under ``REACT`` the book is ``MainTabBookReact`` with its ``tabBar`` hidden;
under ``QT`` it is ``QTabWidget`` with that bar on screen. ``press`` clicks a
button the browser drew and reads the tab off ``currentIndex``.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
pytest.importorskip("PySide6.QtWebEngineWidgets")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QTabWidget  # noqa: E402

from src._variant import ENV_VAR, QT, REACT  # noqa: E402
from src.gui import react_main_window as chrome  # noqa: E402
from src.gui.main_tabs import main_window_surface as surface  # noqa: E402
from tests.fixtures.quiet_news_ticker import install_quiet_ticker  # noqa: E402

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 400
READY_STEP_MS = 50
WINDOW_SIZE_PX = (1400, 900)

THEME_LOG_HEAD = "Theme switched to"

#: The three tabs the presses walk through, and none of them is the first.
PRESSED_TABS = ("History", "Console", "Live")

#: Reads back the text of every button the bar drew, left to right.
DRAWN_LABELS_JS = chrome.LABELS_JS

#: Reads back the text of every button carrying the selected mark.
MARKED_LABELS_JS = (
    "(function () {"
    "  var found = document.querySelectorAll("
    '    "[" + window.acervatorTabBar.selectedAttribute + "]");'
    "  var names = [];"
    "  for (var i = 0; i < found.length; i++) {"
    "    names.push(found[i].textContent);"
    "  }"
    "  return names;"
    "})()"
)


@pytest.fixture(autouse=True)
def quiet_ticker(monkeypatch):
    """``install_quiet_ticker`` gives the Trading tab a strip that opens no socket."""
    yield install_quiet_ticker(monkeypatch)


@pytest.fixture(scope="module")
def qapp():
    """The one ``QApplication`` every ``Window`` in this file is built under."""
    return QApplication.instance() or QApplication(sys.argv)


def settle(milliseconds: int) -> None:
    """Run the event loop for ``milliseconds``."""
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def click_script(label: str) -> str:
    """The JS that presses the drawn button reading ``label``."""
    return (
        "(function () {"
        "  var found = document.querySelectorAll("
        '    "[" + window.acervatorTabBar.tabAttribute + "]");'
        "  for (var i = 0; i < found.length; i++) {"
        "    if (found[i].textContent === " + json.dumps(label) + ") {"
        "      found[i].click();"
        "      return true;"
        "    }"
        "  }"
        "  return false;"
        "})()"
    )


class Window:
    """One shipped ``MainWindow``, built and shown under one variant."""

    def __init__(self, monkeypatch, variant: str) -> None:
        """Build ``MainWindow`` with ``ENV_VAR`` set to ``variant`` and show it."""
        monkeypatch.setenv(ENV_VAR, variant)
        from src.gui.main_window import MainWindow

        self.variant = variant
        self.window = MainWindow(bot_manager=None, settings_manager=None)
        self.window.resize(*WINDOW_SIZE_PX)
        self.window.show()
        settle(READY_STEP_MS)

    @property
    def book(self):
        """The tab book ``_setup_ui`` left on ``_main_tabs``."""
        return self.window._main_tabs

    def labels(self) -> list:
        """Every label ``tabText`` answers, left to right."""
        return [self.book.tabText(at) for at in range(self.book.count())]

    def wait_for_bar(self) -> Any:
        """The view ``bar_view`` answers once ``page_ready`` holds and a button drew."""
        view = self.book.bar_view()
        assert view is not None, (
            "showing the window built no React bar; the book is "
            f"{type(self.book).__name__}"
        )
        for _ in range(READY_ROUNDS):
            if self.book.page_ready and self.js(DRAWN_LABELS_JS):
                return view
            settle(READY_STEP_MS)
        raise AssertionError(
            "the React tab bar never drew a button: page_ready="
            f"{self.book.page_ready}, labels={self.js(DRAWN_LABELS_JS)!r}"
        )

    def js(self, script: str) -> Any:
        """Evaluate ``script`` in the bar's page and bring the value back."""
        loop = QEventLoop()
        box: dict = {}

        def _answered(value: Any) -> None:
            box.setdefault("v", value)
            loop.quit()

        self.book.bar_view().page().runJavaScript(
            "JSON.stringify(" + script + ")", _answered
        )
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert "v" in box, "the bar never answered: " + script[:80]
        return None if box["v"] is None else json.loads(box["v"])

    def press(self, label: str) -> None:
        """Click the drawn button reading ``label`` and wait for ``currentIndex``."""
        assert self.js(click_script(label)) is True, (
            f"the bar drew no button reading {label!r}; it drew "
            f"{self.js(DRAWN_LABELS_JS)!r}"
        )
        for _ in range(READY_ROUNDS):
            if self.book.tabText(self.book.currentIndex()) == label:
                return
            settle(READY_STEP_MS)

    def close(self) -> None:
        """Close the ``MainWindow`` and let ``deleteLater`` run."""
        self.window.close()
        self.window.deleteLater()
        settle(READY_STEP_MS)


@pytest.fixture()
def react_window(qapp, monkeypatch):
    """A ``Window`` built under ``REACT``."""
    assert qapp is not None
    built = Window(monkeypatch, REACT)
    yield built
    built.close()


@pytest.fixture()
def qt_window(qapp, monkeypatch):
    """A ``Window`` built under ``QT``."""
    assert qapp is not None
    built = Window(monkeypatch, QT)
    yield built
    built.close()


def test_the_react_window_builds_the_react_tab_book(react_window) -> None:
    """``_main_tabs`` is ``MainTabBookReact`` under the React build."""
    assert type(react_window.book).__name__ == "MainTabBookReact", type(
        react_window.book
    ).__name__


def test_the_qt_window_builds_the_qt_tab_book(qt_window) -> None:
    """The control: ``_main_tabs`` is the Qt tab book under the Qt build."""
    assert type(qt_window.book).__name__ == "MainTabBookQt", type(
        qt_window.book
    ).__name__
    assert isinstance(qt_window.book, QTabWidget), type(qt_window.book).__name__


def test_the_react_window_hides_the_qt_tab_bar(react_window) -> None:
    """``tabBar`` is off screen under the React build, so Qt paints no strip."""
    assert not react_window.book.tabBar().isVisible(), (
        "the Qt tab bar is still on screen under the React build, so the "
        "window draws two"
    )


def test_the_qt_window_shows_the_qt_tab_bar(qt_window) -> None:
    """The control: ``tabBar`` is on screen under the Qt build."""
    assert qt_window.book.tabBar().isVisible(), (
        "the Qt build's own tab bar is hidden, so the React check above "
        "cannot tell the two builds apart"
    )


def test_the_qt_window_draws_no_web_view_for_its_bar(qt_window) -> None:
    """The control: the Qt book answers no ``bar_view``."""
    assert not hasattr(qt_window.book, "bar_view"), (
        "the Qt tab book answers bar_view, so every React check here would "
        "pass on both builds"
    )


def test_the_react_bar_draws_the_canonical_labels_in_order(react_window) -> None:
    """The browser drew one button per ``CANONICAL_TAB_ORDER`` entry, in order."""
    react_window.wait_for_bar()
    drawn = react_window.js(DRAWN_LABELS_JS)
    assert drawn == list(surface.CANONICAL_TAB_ORDER), drawn


def test_the_react_bar_draws_the_labels_the_book_holds(react_window) -> None:
    """``DRAWN_LABELS_JS`` and ``labels`` name the same tabs in the same order."""
    react_window.wait_for_bar()
    assert react_window.js(DRAWN_LABELS_JS) == react_window.labels()


def test_the_react_bar_marks_the_selected_tab_and_only_that_one(
    react_window,
) -> None:
    """One drawn button carries the selected mark, and ``currentIndex`` names it."""
    react_window.wait_for_bar()
    marked = react_window.js(MARKED_LABELS_JS)
    current = react_window.book.tabText(react_window.book.currentIndex())
    assert marked == [current], (marked, current)


@pytest.mark.parametrize("label", PRESSED_TABS)
def test_pressing_a_react_tab_button_shows_that_tab(react_window, label) -> None:
    """``press`` moves ``currentIndex`` to ``label`` and the page behind it."""
    react_window.wait_for_bar()
    react_window.press(label)
    book = react_window.book
    assert book.tabText(book.currentIndex()) == label, book.tabText(book.currentIndex())
    shown = book.widget(book.currentIndex())
    assert shown is not None, f"{label} has no page behind its tab"
    assert book.indexOf(shown) == book.currentIndex()


def test_a_press_the_bar_never_drew_moves_nothing(react_window) -> None:
    """The control for ``press``: an unknown tab leaves ``currentIndex`` alone."""
    react_window.wait_for_bar()
    book = react_window.book
    before = book.currentIndex()
    book.run_action(json.dumps({"tab": "No Such Tab"}))
    assert book.currentIndex() == before, book.currentIndex()


def test_dropping_a_tab_on_another_moves_it_in_the_book(react_window) -> None:
    """A move ``run_action`` takes reorders ``labels`` and carries each ``widget``."""
    react_window.wait_for_bar()
    book = react_window.book
    before = react_window.labels()
    carried = book.widget(0)
    book.run_action(json.dumps({"move": {"from": 0, "to": 2}}))
    after = react_window.labels()
    assert after != before, after
    assert after[2] == before[0], after
    assert book.widget(2) is carried, "the page did not travel with its label"
    book.run_action(json.dumps({"move": {"from": 2, "to": 0}}))
    assert react_window.labels() == before, react_window.labels()


def test_the_theme_menu_action_writes_to_the_status_log(react_window) -> None:
    """A Theme action puts ``THEME_LOG_HEAD`` into ``_status_log``."""
    window = react_window.window
    menus = [
        menu
        for menu in window.menuBar().findChildren(QMenu)
        if menu.title() == surface.THEME_MENU_TITLE
    ]
    assert menus, [menu.title() for menu in window.menuBar().findChildren(QMenu)]
    actions = menus[0].actions()
    assert actions, "the Theme menu carries no action"
    actions[-1].trigger()
    settle(READY_STEP_MS)
    written = window._status_log.toPlainText()
    assert THEME_LOG_HEAD in written, written[-400:]


@pytest.mark.parametrize("variant", [REACT, QT])
def test_the_launcher_module_imports_under_both_builds(monkeypatch, variant) -> None:
    """``main`` imports with ``ENV_VAR`` set either way and still offers ``main``."""
    monkeypatch.setenv(ENV_VAR, variant)
    launcher = importlib.import_module("main")
    assert callable(launcher.main), type(launcher.main).__name__


def test_the_launcher_builds_the_window_this_file_builds(react_window) -> None:
    """``main`` names ``MainWindow`` and the two arguments ``Window`` passes it."""
    from src.gui.main_window import MainWindow

    assert isinstance(react_window.window, MainWindow)
    taken = set(inspect.signature(MainWindow.__init__).parameters)
    assert {"bot_manager", "settings_manager"} <= taken, sorted(taken)


def test_every_menu_the_surface_declares_is_on_the_react_window(
    react_window,
) -> None:
    """``menuBar`` carries every title in ``MENU_TITLES``, in that order."""
    titles = [action.text() for action in react_window.window.menuBar().actions()]
    assert titles == list(surface.MENU_TITLES), titles


def test_every_menu_item_the_surface_declares_is_on_the_react_window(
    react_window,
) -> None:
    """Each menu carries the items ``menu_model`` declares for it."""
    from src.gui.theme_engine import THEMES

    themes = [(name, tokens.display_name) for name, tokens in THEMES.items()]
    declared = {menu["title"]: menu["items"] for menu in surface.menu_model(themes)}
    for menu in react_window.window.menuBar().findChildren(QMenu):
        if menu.title() not in declared:
            continue
        drawn = [
            surface.MENU_SEPARATOR if action.isSeparator() else action.text()
            for action in menu.actions()
        ]
        assert drawn == declared[menu.title()], (menu.title(), drawn)
