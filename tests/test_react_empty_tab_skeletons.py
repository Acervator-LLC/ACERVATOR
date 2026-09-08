"""Drives the two empty-tab skeletons against their Python surfaces.

Each ``Skeleton`` pairs a renderer module with a surface, a bridge method and a
manifest entry, and ``payload_of`` drives that surface for real. ``JsRuntime``
runs the module and ``Browser`` mounts its panel on ``acervatorPanelHost`` in a
real page. ``drawn_text`` holds the whole host text against the payload, and
``test_the_host_refuses_a_panel_the_manifest_does_not_name`` is the control on
every mount.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src._variant import ENV_VAR, QT
from src.core import desktop_bridge
from src.gui.main_tabs import empty_tabs
from src.gui.main_tabs import proof_of_accumulation_tab_surface
from src.gui.main_tabs import system_status_tab_surface
from src.gui.main_tabs.empty_tabs import EmptyTabsMixin
from tests.fixtures.web_js_modules import JsEngine, js_literals, new_engine
from tools import sync_renderer_modules

WEB = REPO_ROOT / "src" / "gui" / "web"
RENDERER = REPO_ROOT / "desktop" / "renderer"
INDEX_HTML = RENDERER / "index.html"
MANIFEST_JS = RENDERER / "module_manifest.js"

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 300
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2
VIEW_SIZE_PX = (1400, 900)

#: A method name no surface registers, for the bridge control.
ABSENT_METHOD = "no_such_tab.state"

#: A panel name the manifest does not carry, for the host control.
ABSENT_PANEL = "no_such_tab"

#: Generated per run, so no reader can hold a copy of it.
SENTINEL = "zz" + uuid.uuid4().hex


@dataclass(frozen=True)
class Skeleton:
    """One empty tab: its module, its surface and the globals it publishes."""

    name: str
    surface: Any
    setter: str
    published: str


SKELETONS = (
    Skeleton(
        name="proof_of_accumulation_tab",
        surface=proof_of_accumulation_tab_surface,
        setter="acervatorSetProofOfAccumulationTab",
        published="acervatorProofOfAccumulationTab",
    ),
    Skeleton(
        name="system_status_tab",
        surface=system_status_tab_surface,
        setter="acervatorSetSystemStatusTab",
        published="acervatorSystemStatusTab",
    ),
)

SKELETON_IDS = tuple(one.name for one in SKELETONS)


def module_path(one: Skeleton) -> Path:
    """The renderer module file one skeleton ships."""
    return WEB / (one.name + ".js")


def module_source(one: Skeleton) -> str:
    """The text of one skeleton's renderer module."""
    return module_path(one).read_text(encoding="utf-8")


def payload_of(one: Skeleton) -> dict:
    """One skeleton's view model, through the JSON the bridge would send."""
    return json.loads(json.dumps(one.surface.view_model({}), ensure_ascii=True))


def painted_values(one: Skeleton) -> set:
    """Every word one skeleton's tab puts on screen."""
    model = payload_of(one)
    return {
        model["heading"],
        model["state_text"],
        model["issue_text"],
        model["accessible_name"],
    }


def drawn_text(one: Skeleton) -> str:
    """The whole text the empty state draws, in the order it draws it."""
    model = payload_of(one)
    return model["heading"] + model["state_text"] + model["issue_text"]


def manifest_names() -> list:
    """The module file names ``module_manifest.js`` declares, in order."""
    return sync_renderer_modules.manifest_entries(
        MANIFEST_JS.read_text(encoding="utf-8")
    )


# -- 1. the surface answers a view model -------------------------------------


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_surface_answers_every_field_it_declares(one: Skeleton):
    model = one.surface.view_model({})
    assert sorted(model) == sorted(one.surface.DECLARED_FIELDS), (
        one.name + " answers " + str(sorted(model))
    )


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_surface_names_the_issue_that_owns_the_tab(one: Skeleton):
    model = one.surface.view_model({})
    assert model["issue"] == one.surface.ISSUE
    assert str(one.surface.ISSUE) in model["issue_text"], model["issue_text"]


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_surface_reports_the_tab_as_not_built(one: Skeleton):
    assert one.surface.view_model({})["built"] is False


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_surface_publishes_no_value_a_bot_could_have_moved(one: Skeleton):
    """An unbuilt screen answers words and one issue number, never a figure."""
    model = one.surface.view_model({})
    numbers = {
        key: value
        for key, value in model.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    assert numbers == {"issue": one.surface.ISSUE}, numbers


def test_the_skeletons_name_different_issues():
    """The control for the issue checks: two surfaces copied from one
    another would answer the same number and pass every check above."""
    issues = [one.surface.ISSUE for one in SKELETONS]
    assert len(set(issues)) == len(issues), issues


# -- 2. the bridge answers each method ---------------------------------------


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_bridge_answers_the_method_the_surface_names(one: Skeleton):
    registry = desktop_bridge.build_registry()
    answered = desktop_bridge.dispatch(one.surface.METHOD, {}, registry)
    assert answered == one.surface.view_model({})


def test_the_bridge_refuses_a_method_no_surface_registers():
    """The control for the check above: a registry answering anything would
    report every method as reachable."""
    registry = desktop_bridge.build_registry()
    with pytest.raises(desktop_bridge.UnknownMethod):
        desktop_bridge.dispatch(ABSENT_METHOD, {}, registry)


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_bridge_answer_survives_the_line_the_protocol_writes(one: Skeleton):
    """``encode_frame`` writes the line the frontend parses, and this reads
    that line back."""
    registry = desktop_bridge.build_registry()
    frame = desktop_bridge.handle_line(
        json.dumps({"id": 1, "method": one.surface.METHOD, "params": {}}),
        registry,
    )
    read_back = json.loads(desktop_bridge.encode_frame(frame).decode("utf-8"))
    assert read_back["ok"] is True, read_back
    assert read_back["result"] == payload_of(one)


# -- 3. the manifest names each module ---------------------------------------


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_manifest_names_the_module(one: Skeleton):
    assert module_path(one).name in manifest_names(), (
        "run python -m tools.sync_renderer_modules; the page loads no "
        + module_path(one).name
    )


def test_the_manifest_check_reports_a_module_the_manifest_leaves_out():
    """The control for the check above, run against the parser's own output."""
    assert ABSENT_PANEL + ".js" not in manifest_names()


# -- 4. the module holds what the surface published --------------------------


class JsRuntime(JsEngine):
    """A QJSEngine holding one empty-tab module and a ``window`` global."""

    def __init__(self, one: Skeleton) -> None:
        self.module_path = module_path(one)
        self.setter = one.setter
        super().__init__(new_engine(), module_source(one))


@pytest.fixture()
def js_for(qapp):
    """``JsRuntime``, with the Qt application the engine needs already up."""
    assert qapp is not None
    return JsRuntime


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_module_publishes_the_bridge_method_the_surface_answers(
    js_for, one: Skeleton
):
    js = js_for(one)
    assert js.json(one.published + ".method") == one.surface.METHOD


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_module_raises_no_fault_on_the_payload_the_surface_produced(
    js_for, one: Skeleton
):
    js = js_for(one)
    report = js.push(payload_of(one))
    assert report["faults"] == [], report["faults"]
    assert report["held"]["fields"] == report["declared"]["fields"]


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_module_reports_a_field_the_payload_left_out(js_for, one: Skeleton):
    """The control for the check above."""
    js = js_for(one)
    payload = payload_of(one)
    del payload["issue_text"]
    report = js.push(payload)
    wanted = {"field": "issue_text", "fault": "missing", "detail": None}
    assert wanted in report["faults"], report["faults"]


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_module_reports_a_payload_that_claims_the_tab_is_built(
    js_for, one: Skeleton
):
    """The module draws an empty state, and a payload declaring a built tab
    is a fault."""
    js = js_for(one)
    payload = payload_of(one)
    payload["built"] = True
    report = js.push(payload)
    wanted = {"field": "built", "fault": "claims-built", "detail": "boolean"}
    assert wanted in report["faults"], report["faults"]


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_module_spells_out_none_of_the_words_the_tab_paints(one: Skeleton):
    found = set(js_literals(module_source(one))["strings"])
    written = sorted(found & painted_values(one))
    assert not written, module_path(one).name + " spells out: " + str(written)


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_literal_scan_reports_a_word_written_into_the_module(one: Skeleton):
    """The control for the check above, run against a copy of the source."""
    tail = "var painted = " + json.dumps(one.surface.HEADING) + ";"
    found = set(js_literals(module_source(one) + tail)["strings"])
    assert found & painted_values(one) == {one.surface.HEADING}


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_module_writes_the_issue_number_nowhere(one: Skeleton):
    numbers = js_literals(module_source(one))["numbers"]
    assert str(one.surface.ISSUE) not in numbers, numbers


# -- 5. the host draws the panel in a real page ------------------------------


PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "document.body.appendChild(window.HOST);"
    "window.mountPanel = function (name, model) {"
    "  return window.acervatorPanelHost.mount(name, window.HOST, model); };"
    "window.hostFault = function () {"
    "  return window.HOST.getAttribute("
    "    window.acervatorPanelHost.faultAttribute); };"
    "window.partText = function (name) {"
    "  var found = window.HOST.querySelector('[data-part=\"' + name + '\"]');"
    "  return found === null ? null : found.textContent; };"
)


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._view.resize(*VIEW_SIZE_PX)
        self.open_page()
        self.wait_for_host()
        self.js(PAGE_HELPERS)

    def open_page(self) -> None:
        """Load ``INDEX_HTML`` and wait for the page's own load signal."""
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        connection = self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(connection)
        assert box.get("ok") is True, INDEX_HTML.name + " did not load: " + str(box)

    def wait_for_host(self) -> None:
        """Turn the loop until ``acervatorPanelHost`` is on the page."""
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorPanelHost") == "object":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the panel host: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
        )

    def js(self, script: str) -> Any:
        """Run one script in the page and bring its value back."""
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        box: dict = {}

        def _answered(value: Any) -> None:
            box.setdefault("v", value)
            loop.quit()

        self._view.page().runJavaScript(script, _answered)
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert "v" in box, "the browser never answered: " + script[:80]
        return box["v"]

    def parsed(self, expression: str) -> Any:
        """Evaluate one expression and bring its JSON back as Python."""
        return json.loads(self.js("JSON.stringify(" + expression + ")"))

    def mount(self, name: str, model: Any) -> Any:
        """Ask ``acervatorPanelHost`` to draw one panel into ``HOST``."""
        self.js("window.PAYLOAD = " + json.dumps(model) + ";")
        wanted = json.dumps(name)
        return self.parsed("window.mountPanel(" + wanted + ", window.PAYLOAD)")

    def settle(self, milliseconds: int) -> None:
        """Turn the event loop for one interval."""
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def close(self) -> None:
        """Drop the view."""
        self._view.deleteLater()


@pytest.fixture()
def browser(qapp):
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


@pytest.mark.slow
def test_every_skeleton_registers_a_panel_with_the_host(browser: Browser):
    registered = browser.parsed("window.acervatorPanelHost.registered()")
    absent = [one.name for one in SKELETONS if one.name not in registered]
    assert not absent, (
        "the page registers no panel for "
        + ", ".join(absent)
        + "; it registered "
        + ", ".join(registered)
    )


@pytest.mark.slow
@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_host_draws_the_empty_state_from_the_surface_payload(
    browser: Browser, one: Skeleton
):
    model = payload_of(one)
    drew = browser.mount(one.name, model)
    assert drew is True, browser.parsed("window.acervatorPanelHost.faults()")
    assert browser.parsed("window.hostFault()") is None
    assert browser.parsed("window.partText('heading')") == model["heading"]
    assert browser.parsed("window.partText('state')") == model["state_text"]
    assert browser.parsed("window.partText('issue')") == model["issue_text"]


@pytest.mark.slow
@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_drawn_panel_carries_no_word_the_surface_did_not_publish(
    browser: Browser, one: Skeleton
):
    """An unbuilt screen that invents a row is the defect this guards."""
    browser.mount(one.name, payload_of(one))
    assert browser.parsed("window.HOST.textContent") == drawn_text(one)


@pytest.mark.slow
@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_drawn_panel_names_the_issue_the_surface_named(
    browser: Browser, one: Skeleton
):
    browser.mount(one.name, payload_of(one))
    read = browser.parsed(
        "window.HOST.querySelector('[data-issue]').getAttribute('data-issue')"
    )
    assert read == str(one.surface.ISSUE)


@pytest.mark.slow
def test_the_host_refuses_a_panel_the_manifest_does_not_name(browser: Browser):
    """The control for every mount above: a host that drew anything asked of
    it would report each skeleton as drawn without running its module."""
    assert browser.mount(ABSENT_PANEL, {}) is False
    assert browser.parsed("window.hostFault()") is not None
    assert browser.parsed("window.partText('heading')") is None


@pytest.mark.slow
def test_the_page_reader_reports_a_heading_it_was_given(browser: Browser):
    """The control for the reads above: a reader answering the surface
    constant would match whatever the page drew."""
    one = SKELETONS[0]
    payload = payload_of(one)
    payload["heading"] = SENTINEL
    browser.mount(one.name, payload)
    assert browser.parsed("window.partText('heading')") == SENTINEL


# -- 6. the Qt tab and the React panel draw the same words -------------------


def qt_tabs(qapp) -> Any:
    """A ``QTabWidget`` the two shipped builders have added their tabs to."""
    from PySide6.QtWidgets import QTabWidget

    assert qapp is not None

    class Host(EmptyTabsMixin):
        def __init__(self) -> None:
            self._main_tabs = QTabWidget()

    host = Host()
    host._build_system_status_tab()
    host._build_proof_of_accumulation_tab()
    return host


def qt_words(panel: Any) -> dict:
    """The three sentences one Qt empty tab paints, read off its labels."""
    from PySide6.QtWidgets import QLabel

    return {
        field: panel.findChild(QLabel, name).text()
        for name, field, _ in empty_tabs.LABELS
    }


@pytest.fixture()
def tabs(qapp, monkeypatch):
    """The Qt tab book, or a skip on a host without PySide6.

    ``ENV_VAR`` is pinned to ``QT`` so the builders draw the Qt panels these
    checks read; the React build draws the same words in a browser instead.
    """
    pytest.importorskip("PySide6.QtWidgets")
    monkeypatch.setenv(ENV_VAR, QT)
    return qt_tabs(qapp)


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_qt_tab_carries_the_label_its_surface_names(tabs, one: Skeleton):
    labels = [tabs._main_tabs.tabText(at) for at in range(tabs._main_tabs.count())]
    assert one.surface.HEADING in labels, labels


@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_qt_tab_paints_the_words_its_surface_publishes(tabs, one: Skeleton):
    words = qt_words(tabs._empty_tabs[one.surface.METHOD])
    assert words["heading"] == one.surface.HEADING
    assert words["state_text"] == one.surface.STATE_TEXT
    assert words["issue_text"] == one.surface.ISSUE_TEXT


def test_the_qt_reader_reports_the_words_the_widget_was_given(qapp):
    """The control for the two checks above: a reader answering the surface
    constant would match whatever the widget painted."""
    assert qapp is not None
    model = payload_of(SKELETONS[0])
    model["heading"] = SENTINEL
    assert qt_words(empty_tabs.EmptyTabQtPanel(model))["heading"] == SENTINEL


@pytest.mark.slow
@pytest.mark.parametrize("one", SKELETONS, ids=SKELETON_IDS)
def test_the_qt_tab_and_the_react_panel_draw_the_same_words(
    browser: Browser, tabs, one: Skeleton
):
    """Both sides read one view model, so neither can drift from the other."""
    browser.mount(one.name, payload_of(one))
    drawn = browser.parsed("window.HOST.textContent")
    words = qt_words(tabs._empty_tabs[one.surface.METHOD])
    assert drawn == words["heading"] + words["state_text"] + words["issue_text"]
    assert drawn == drawn_text(one)
