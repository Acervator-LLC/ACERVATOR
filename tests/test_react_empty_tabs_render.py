"""The three unbuilt tabs draw in React under the React build.

``Panel`` builds one empty tab through the shipped ``_add_empty_tab`` under one
variant and shows it. Under ``REACT`` the panel is ``EmptyTabReactPanel`` and
the browser's own text is read back; under ``QT`` it is ``EmptyTabQtPanel`` and
``qt_words`` reads the labels. Both sides are held against the same
``view_model``.
"""

from __future__ import annotations

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
from PySide6.QtWidgets import QApplication, QLabel, QTabWidget  # noqa: E402

from src._variant import ENV_VAR, QT, REACT  # noqa: E402
from src.gui import react_empty_tab as react_panel  # noqa: E402
from src.gui.main_tabs import empty_tabs  # noqa: E402

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 400
READY_STEP_MS = 50
PANEL_SIZE_PX = (900, 600)

SURFACES = empty_tabs.EMPTY_TAB_SURFACES
SURFACE_IDS = [one.HEADING for one in SURFACES]


@pytest.fixture(scope="module")
def qapp():
    """The one ``QApplication`` every ``Panel`` in this file is built under."""
    return QApplication.instance() or QApplication(sys.argv)


def settle(milliseconds: int) -> None:
    """Run the event loop for ``milliseconds``."""
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


class Host(empty_tabs.EmptyTabsMixin):
    """A stand-in for the window, carrying only the tab book the mixin fills."""

    def __init__(self) -> None:
        """Hold one ``QTabWidget`` for ``_add_empty_tab`` to add to."""
        self._main_tabs = QTabWidget()


class Panel:
    """One empty tab, built by the shipped mixin under one variant and shown."""

    def __init__(self, monkeypatch, variant: str, surface) -> None:
        """Build ``surface``'s tab with ``ENV_VAR`` set to ``variant``."""
        monkeypatch.setenv(ENV_VAR, variant)
        self.surface = surface
        self.host = Host()
        self.panel = self.host._add_empty_tab(surface)
        self.host._main_tabs.resize(*PANEL_SIZE_PX)
        self.host._main_tabs.show()
        settle(READY_STEP_MS)

    def wait_for_page(self) -> Any:
        """The view ``panel_view`` answers, once its page has drawn some text."""
        view = self.panel.panel_view()
        assert view is not None, (
            "showing the tab built no React page; the panel is "
            f"{type(self.panel).__name__}"
        )
        for _ in range(READY_ROUNDS):
            if self.panel.page_ready and self.js(react_panel.DRAWN_TEXT_JS):
                return view
            settle(READY_STEP_MS)
        raise AssertionError(
            "the React empty tab never drew any text: page_ready="
            f"{self.panel.page_ready}, text={self.js(react_panel.DRAWN_TEXT_JS)!r}"
        )

    def js(self, script: str) -> Any:
        """Evaluate ``script`` in the panel's page and bring the value back."""
        loop = QEventLoop()
        box: dict = {}

        def _answered(value: Any) -> None:
            box.setdefault("v", value)
            loop.quit()

        self.panel.panel_view().page().runJavaScript(
            "JSON.stringify(" + script + ")", _answered
        )
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert "v" in box, "the page never answered: " + script[:80]
        return None if box["v"] is None else json.loads(box["v"])

    def close(self) -> None:
        """Take the tab book down."""
        self.host._main_tabs.close()
        self.host._main_tabs.deleteLater()
        settle(READY_STEP_MS)


def qt_words(panel: Any) -> dict:
    """The three sentences one ``EmptyTabQtPanel`` paints, read off its labels."""
    return {
        field: panel.findChild(QLabel, name).text()
        for name, field, _ in empty_tabs.LABELS
    }


def words_of(surface) -> list:
    """The heading, the state sentence and the issue sentence, in drawn order."""
    model = surface.view_model({})
    return [model["heading"], model["state_text"], model["issue_text"]]


@pytest.mark.parametrize("surface", SURFACES, ids=SURFACE_IDS)
def test_the_react_build_draws_the_empty_tab_in_a_page(qapp, monkeypatch, surface):
    """``_add_empty_tab`` builds ``EmptyTabReactPanel`` under the React build."""
    assert qapp is not None
    built = Panel(monkeypatch, REACT, surface)
    try:
        assert type(built.panel).__name__ == "EmptyTabReactPanel", type(
            built.panel
        ).__name__
    finally:
        built.close()


@pytest.mark.parametrize("surface", SURFACES, ids=SURFACE_IDS)
def test_the_qt_build_draws_the_empty_tab_in_labels(qapp, monkeypatch, surface):
    """The control: ``_add_empty_tab`` builds ``EmptyTabQtPanel`` under Qt."""
    assert qapp is not None
    built = Panel(monkeypatch, QT, surface)
    try:
        assert type(built.panel) is empty_tabs.EmptyTabQtPanel, type(
            built.panel
        ).__name__
        assert not hasattr(built.panel, "panel_view"), (
            "the Qt panel answers panel_view, so the React checks here would "
            "pass on both builds"
        )
    finally:
        built.close()


@pytest.mark.parametrize("surface", SURFACES, ids=SURFACE_IDS)
def test_the_react_page_draws_the_words_the_surface_publishes(
    qapp, monkeypatch, surface
):
    """The browser's own text carries the three sentences ``view_model`` names."""
    assert qapp is not None
    built = Panel(monkeypatch, REACT, surface)
    try:
        built.wait_for_page()
        drawn = built.js(react_panel.DRAWN_TEXT_JS)
        assert drawn == "".join(words_of(surface)), drawn
    finally:
        built.close()


@pytest.mark.parametrize("surface", SURFACES, ids=SURFACE_IDS)
def test_the_react_page_and_the_qt_labels_draw_the_same_words(
    qapp, monkeypatch, surface
):
    """Neither build can drift: both read one ``view_model``."""
    assert qapp is not None
    drawing = Panel(monkeypatch, REACT, surface)
    try:
        drawing.wait_for_page()
        drawn = drawing.js(react_panel.DRAWN_TEXT_JS)
    finally:
        drawing.close()
    painted = Panel(monkeypatch, QT, surface)
    try:
        words = qt_words(painted.panel)
    finally:
        painted.close()
    assert drawn == words["heading"] + words["state_text"] + words["issue_text"]


def test_the_page_reader_reports_a_word_the_two_sides_do_not_share(qapp, monkeypatch):
    """The control for the comparison: a changed model changes the drawn text."""
    assert qapp is not None
    surface = SURFACES[0]
    built = Panel(monkeypatch, REACT, surface)
    try:
        built.wait_for_page()
        drawn = built.js(react_panel.DRAWN_TEXT_JS)
    finally:
        built.close()
    other = words_of(SURFACES[1])
    assert drawn != "".join(other), (drawn, other)


@pytest.mark.parametrize("surface", SURFACES, ids=SURFACE_IDS)
def test_the_react_panel_names_the_module_its_method_names(surface):
    """``module_name`` answers the renderer module the surface's method names."""
    model = surface.view_model({})
    name = react_panel.module_name(model)
    assert (REPO_ROOT / "src" / "gui" / "web" / (name + ".js")).is_file(), name
    assert model["method"].startswith(name + "."), (name, model["method"])


def test_the_page_carries_every_skin_value_both_sides_paint():
    """``skin_rule`` writes each ``SKIN`` entry into the page it builds."""
    model = SURFACES[0].view_model({})
    page = react_panel.panel_html(model)
    missing = [
        name
        for name, value in empty_tabs.SKIN.items()
        if f"{name}:{value};" not in page
    ]
    assert not missing, missing


def test_the_skin_check_reports_a_value_the_page_does_not_carry():
    """The control for the skin check: an entry no page carries is reported."""
    model = SURFACES[0].view_model({})
    page = react_panel.panel_html(model)
    assert "--empty-tab-ground:no-such-colour;" not in page
