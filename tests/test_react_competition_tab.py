"""competition_tab.js read back against competition_tab_surface, and the Qt tab it stands beside.

The shipped Qt tab is NOT replaced here. It is pinned: a test counts the
live Qt children the real tab builds, so deleting one fails the run.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.color_alpha import css_alpha
from src.gui.main_tabs import competition_tab_surface as surface
from tests.fixtures.web_js_modules import (
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "competition_tab.js"
HEADER_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
MANIFEST_PATH = REPO_ROOT / "desktop" / "renderer" / "module_manifest.js"

#: MODULE_SOURCE is read at collection, before any test body writes the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")

PLANTED_COLOUR = '\nvar planted = "#0b0b0b";\n'

#: A Qt alpha byte no shipped style carries, so a share of it is unmistakable.
BYTE_ALPHA = 38
SHARE_ALPHA = css_alpha(BYTE_ALPHA)

LEADER_TIER = "Grand Accumulator"
SECOND_TIER = "Harvest"


# -- the surface, as the bridge serialises it --------------------------


def tab_spec() -> dict:
    """One tab whose wallet and leaderboard both hold rows, and hold different ones.

    The two tables are deliberately asymmetric: four award columns
    against five leaderboard columns, and two award rows against three
    ranked rows. A comparison that lined the wrong table up would report.
    """
    return {
        "identity": {"bot_id": "abcdefghijklmnopqrstuvwxyz0123456789"},
        "balance": 4321,
        "awards": [
            {
                "tier_name": LEADER_TIER,
                "tier_emoji": "G",
                "amount": 2500,
                "competition_id": "c-one",
                "timestamp": 1_700_000_000.0,
            },
            {
                "tier_name": SECOND_TIER,
                "tier_emoji": "H",
                "amount": 40,
                "competition_id": "c-two",
                "timestamp": 1_700_086_400.0,
            },
        ],
        "summary": {"total_minted": 900, "remaining": 100, "total_holders": 7},
        "leaderboard": [
            {"rank": 1, "bot_id": "aaa", "rating": 1600, "w": 9, "l": 1, "win_rate": "90%"},
            {"rank": 2, "bot_id": "bbb", "rating": 1500, "w": 5, "l": 5, "win_rate": "50%"},
            {"rank": 3, "bot_id": "ccc", "rating": 1400, "w": 1, "l": 9, "win_rate": "10%"},
        ],
        "season": 2,
    }


def payload(**params: Any) -> dict:
    """One surface answer after the round trip through the bridge's JSON."""
    asked = {"reset": True, "state": tab_spec()}
    asked.update(params)
    return json.loads(json.dumps(surface.view_model(asked), ensure_ascii=True))


@pytest.fixture()
def model() -> dict:
    return payload()


# -- the module, in the engine the page runs it in ---------------------


class JsRuntime(JsEngine):
    module_path = MODULE_PATH
    setter = "acervatorSetCompetitionTab"


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module in a fresh engine, with the style-sheet reader beside it."""
    assert qapp is not None
    engine = new_engine()
    engine.evaluate("var window = this;")
    loaded = engine.evaluate(HEADER_PATH.read_text(encoding="utf-8"), HEADER_PATH.name)
    assert not loaded.isError(), HEADER_PATH.name + " did not run: " + loaded.toString()
    return JsRuntime(engine, MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime, model: dict) -> JsRuntime:
    js.push(model)
    return js


def test_the_module_answers_the_bridge_method_the_surface_registers(js: JsRuntime):
    """The module would call a method the bridge does not route."""
    assert js.json("acervatorCompetitionTab.method") == surface.METHOD


def test_every_field_the_module_declares_is_one_the_surface_publishes(
    js: JsRuntime, model: dict
):
    """The module reads a field the surface never writes, or the reverse."""
    declared = set(js.json("acervatorCompetitionTab.declaredFields()"))
    missing = sorted(declared - set(model))
    assert not missing, f"the module reads fields the surface does not publish: {missing}"


def test_the_field_check_names_a_field_the_surface_dropped(js: JsRuntime, model: dict):
    """The check above compares two full sets, or means nothing."""
    declared = set(js.json("acervatorCompetitionTab.declaredFields()"))
    thinned = {name: value for name, value in model.items() if name != "tier_colors"}
    assert sorted(declared - set(thinned)) == ["tier_colors"]


def test_the_module_holds_every_wallet_row_the_surface_publishes(loaded: JsRuntime, model: dict):
    """A wallet cell drifted between the surface and the module."""
    rows = model["wallet_panel"]["rows"]
    assert rows, "the wallet fixture holds no row, so the comparison proves nothing"
    assert loaded.json("acervatorCompetitionTab.walletPanel().rows") == rows


def test_the_module_holds_every_leaderboard_row_the_surface_publishes(
    loaded: JsRuntime, model: dict
):
    """A leaderboard cell drifted between the surface and the module."""
    rows = model["leaderboard_panel"]["rows"]
    assert len(rows) == 3, f"the leaderboard fixture holds {len(rows)} rows, not three"
    assert loaded.json("acervatorCompetitionTab.leaderboardPanel().rows") == rows


def test_the_row_comparison_reports_one_changed_cell(loaded: JsRuntime, model: dict):
    """The comparison above compares values, or a changed cell would pass."""
    changed = json.loads(json.dumps(model))
    changed["wallet_panel"]["rows"][0][0]["text"] = "moved"
    assert loaded.json("acervatorCompetitionTab.walletPanel().rows") != (
        changed["wallet_panel"]["rows"]
    )


def test_the_module_names_no_fault_on_the_shipped_payload(loaded: JsRuntime):
    """The module read something the surface publishes as the wrong shape."""
    assert loaded.json("acervatorCompetitionTab.faults()") == []


def test_a_wallet_row_short_of_a_cell_is_named_as_a_fault(js: JsRuntime, model: dict):
    """The fault list above is empty because nothing is wrong, not because it is blind."""
    broken = json.loads(json.dumps(model))
    broken["wallet_panel"]["rows"][0].pop()
    js.push(broken)
    faults = js.json("acervatorCompetitionTab.faults()")
    assert [one["fault"] for one in faults] == ["short-list"], faults


def test_a_tier_colour_the_surface_never_published_is_named_as_a_fault(
    js: JsRuntime, model: dict
):
    """A wallet cell painting an unpublished colour must be reported."""
    broken = json.loads(json.dumps(model))
    broken["wallet_panel"]["rows"][0][0]["color"] = "#123456"
    js.push(broken)
    faults = js.json("acervatorCompetitionTab.faults()")
    assert [one["fault"] for one in faults] == ["unnamed"], faults


def test_a_cell_paints_the_tier_colour_the_surface_gave_it(loaded: JsRuntime, model: dict):
    """The tier column is the only coloured cell the wallet table paints."""
    cell = model["wallet_panel"]["rows"][0][0]
    assert cell["color"] == model["tier_colors"][LEADER_TIER]
    painted = loaded.json(
        "acervatorCompetitionTab.cellStyle("
        "JSON.parse(PAYLOAD),"
        "acervatorCompetitionTab.walletPanel().rows[0][0])"
    )
    assert painted["color"] == cell["color"]


def test_a_cell_the_surface_left_uncoloured_paints_no_colour(loaded: JsRuntime, model: dict):
    """A column past the tier column carries the surface's own no-colour reading."""
    cell = model["wallet_panel"]["rows"][0][1]
    assert cell["color"] == model["colors"]["none"]
    painted = loaded.json(
        "acervatorCompetitionTab.cellStyle("
        "JSON.parse(PAYLOAD),"
        "acervatorCompetitionTab.walletPanel().rows[0][1])"
    )
    assert "color" not in painted, painted


def test_the_module_records_a_fault_when_the_bridge_is_absent(js: JsRuntime):
    """A page with no preload bridge must say so rather than fail silently."""
    js.run("acervatorLoadCompetitionTab({});")
    assert js.json("acervatorCompetitionTab.loadError()") is not None
    assert js.json("acervatorCompetitionTab.isLoaded()") is False


# -- the module carries no value of its own ----------------------------


def test_the_module_writes_no_colour_of_its_own():
    """A colour written into the module is a colour the surface cannot change."""
    assert HEX_COLOUR.findall(MODULE_SOURCE) == []


def test_the_colour_scan_reads_the_module_file_and_can_report():
    """The scan above is empty because the module is clean, not because it is blind."""
    original = MODULE_PATH.read_bytes()
    try:
        swap_module(MODULE_PATH, original + PLANTED_COLOUR.encode("utf-8"))
        planted = MODULE_PATH.read_text(encoding="utf-8")
        assert HEX_COLOUR.findall(planted) == ["#0b0b0b"]
    finally:
        swap_module(MODULE_PATH, original)
    assert MODULE_PATH.read_bytes() == original


def test_no_string_in_the_module_is_a_text_the_tab_shows(model: dict):
    """A caption written into the module would not follow the surface."""
    written = set(js_literals(MODULE_SOURCE)["strings"])
    shown = {one for one in model["texts"].values() if isinstance(one, str) and one.strip()}
    shown.update(model["section_names"])
    carried = sorted(written & shown)
    assert not carried, f"the module writes texts the surface owns: {carried}"


def test_the_string_scan_reads_the_module_and_finds_a_planted_caption():
    """The scan above is empty because the module is clean, not because it is blind."""
    found = js_literals(MODULE_SOURCE + '\nvar planted = "Proof of Accumulation";\n')
    assert "Proof of Accumulation" in found["strings"]
    assert "Proof of Accumulation" not in js_literals(MODULE_SOURCE)["strings"]


def test_the_renderer_manifest_names_the_module():
    """A module the manifest leaves out never runs on the page."""
    from tools import sync_renderer_modules

    named = sync_renderer_modules.manifest_entries(
        MANIFEST_PATH.read_text(encoding="utf-8")
    )
    assert MODULE_PATH.name in named


# -- which side converts the alpha -------------------------------------


def test_the_style_sheet_the_widget_sets_keeps_the_alpha_byte_qt_reads(monkeypatch):
    """build_view_model feeds a real setStyleSheet, so the byte must survive it."""
    monkeypatch.setattr(surface, "SEPARATOR_STYLE", f"color:rgba(0,255,238,{BYTE_ALPHA});")
    built = surface.build_view_model(surface.build_model(tab_spec()))
    assert built["styles"]["separator"] == f"color:rgba(0,255,238,{BYTE_ALPHA});"


def test_the_published_payload_carries_the_alpha_share_a_browser_reads(monkeypatch):
    """view_model is the boundary: past it the alpha is the share CSS reads."""
    monkeypatch.setattr(surface, "SEPARATOR_STYLE", f"color:rgba(0,255,238,{BYTE_ALPHA});")
    published = surface.view_model({"reset": True, "state": tab_spec()})
    assert published["styles"]["separator"] == f"color:rgba(0,255,238,{SHARE_ALPHA});"


def test_the_shipped_alphas_are_shares_already_and_cross_unchanged():
    """Every shipped alpha is under one, so the boundary leaves each as it is."""
    built = surface.build_view_model(surface.build_model(tab_spec()))
    published = surface.view_model({"reset": True, "state": tab_spec()})
    assert built["styles"] == published["styles"]
    assert "rgba(0,255,238,0.15)" in built["styles"]["separator"]


# -- the Qt tab is preserved, and counted ------------------------------


BOT_KEY = "aa11bb22cc33dd44ee55ff66aa77bb88cc99dd00ee11ff22aa33bb44cc55dd66"
OTHER_KEY = "bb22cc33dd44ee55ff66aa77bb88cc99dd00ee11ff22aa33bb44cc55dd66aa11"
PRIVATE_KEY_B64 = base64.b64encode(bytes(32)).decode()


def seed(where: Path) -> Path:
    """Write the three files the Qt tab reads, so both its tables are built."""
    (where / "bot_identity.json").write_text(
        json.dumps(
            {
                "version": 1,
                "bot_id": BOT_KEY,
                "created_at": 1_700_000_000.0,
                "pubkey_hex": BOT_KEY,
                "privkey_b64": PRIVATE_KEY_B64,
            }
        ),
        encoding="utf-8",
    )
    (where / "acrv_ledger.json").write_text(
        json.dumps(
            {
                "version": 1,
                "total_cap": 10_000_000,
                "events": [
                    {
                        "event_id": "event-0",
                        "bot_id": BOT_KEY,
                        "competition_id": "c-one",
                        "season": 1,
                        "tier_name": LEADER_TIER,
                        "tier_emoji": "G",
                        "amount": 2500,
                        "timestamp": 1_700_000_000.0,
                        "competition_root": "root",
                        "rank_pct": 0.4,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (where / "elo_registry.json").write_text(
        json.dumps(
            {
                "ratings": {
                    key: {
                        "bot_id": key,
                        "rating": rating,
                        "wins": 3,
                        "losses": 1,
                        "last_competed": 0.0,
                        "consecutive_top1": 0,
                    }
                    for key, rating in ((BOT_KEY, 1300), (OTHER_KEY, 1200))
                },
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    return where


def qt_tab(where: Path):
    """The shipped Qt tab, built over a seeded directory the test owns."""
    from tests.qt_pixel import ensure_app

    ensure_app()
    from src.gui import competition_tab as shipped

    return shipped.CompetitionTab(data_dir=str(seed(where)))


def live_children(widget) -> dict:
    """Every live Qt child of `widget`, counted by the Qt class it is."""
    from PySide6.QtWidgets import QWidget

    found: dict = {}
    for child in widget.findChildren(QWidget):
        for owner in type(child).__mro__:
            if owner.__name__.startswith("Q"):
                found[owner.__name__] = found.get(owner.__name__, 0) + 1
                break
    return found


#: MEASURED off the shipped tab over the seeded directory above. Only the
#: classes the tab builds itself: a scroll bar and a header view are Qt's.
SHIPPED_CHILDREN = {
    "QGroupBox": 5,
    "QLabel": 19,
    "QTableWidget": 2,
    "QLineEdit": 1,
    "QPushButton": 1,
    "QFrame": 1,
    "QScrollArea": 1,
}


def test_the_shipped_tab_still_builds_every_qt_child_it_shipped_with(tmp_path: Path):
    """A Qt widget was deleted before its React replacement was verified."""
    tab = qt_tab(tmp_path)
    counted = live_children(tab)
    held = {name: counted.get(name, 0) for name in SHIPPED_CHILDREN}
    assert held == SHIPPED_CHILDREN, counted


def test_the_child_counter_reports_a_widget_that_is_not_there(tmp_path: Path):
    """The count above is a pin because the counter can come up short."""
    from PySide6.QtWidgets import QWidget

    from tests.qt_pixel import ensure_app

    ensure_app()
    bare = QWidget()
    counted = live_children(bare)
    assert counted == {}
    assert live_children(qt_tab(tmp_path)) != counted


# -- the module drawn by the real page ---------------------------------

INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"
JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100


class Page:
    """The renderer page, loaded from disk in the Chromium view the shell embeds."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open()
        self.wait_for_module()

    def open(self) -> None:
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
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def settle(self, milliseconds: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def wait_for_module(self) -> None:
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetCompetitionTab") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the module: readyState "
            + str(self.js("document.readyState"))
        )

    def js(self, script: str) -> Any:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        box: dict = {}

        def _answered(value: Any) -> None:
            box.setdefault("v", value)
            loop.quit()

        self._view.page().runJavaScript(script, _answered)
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert "v" in box, "the page never answered: " + script[:80]
        return box["v"]

    def parsed(self, expression: str) -> Any:
        found = self.js("JSON.stringify(" + expression + ")")
        assert isinstance(found, str), (
            "the page answered nothing for " + expression + "; it drew no such element"
        )
        return json.loads(found)

    def close(self) -> None:
        self._view.deleteLater()


@pytest.fixture()
def page(qapp, model: dict):
    """The page with the tab drawn into a host node, or a skip with no Chromium."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    found = Page()
    found.js("window.PAYLOAD = " + json.dumps(json.dumps(model)) + ";")
    found.js(
        "window.HOST = document.createElement('div');"
        "document.body.appendChild(window.HOST);"
        "window.acervatorSetCompetitionTab(JSON.parse(window.PAYLOAD));"
        "window.acervatorCompetitionTab.renderTab(window.HOST,"
        " JSON.parse(window.PAYLOAD));"
    )
    yield found
    found.close()


def test_the_page_draws_the_five_sections_the_surface_names(page: Page, model: dict):
    """The module publishes components the page never actually drew."""
    drawn = page.parsed(
        "Array.prototype.map.call("
        "window.HOST.querySelectorAll('[data-part=\"section-title\"]'),"
        " function (one) { return one.textContent; })"
    )
    assert drawn == model["section_names"], drawn


def test_the_page_draws_every_wallet_and_leaderboard_row(page: Page, model: dict):
    """A table the page never built would report no row at all."""
    counted = page.parsed(
        "Array.prototype.map.call("
        "window.HOST.querySelectorAll('[data-part=\"table\"]'),"
        " function (one) { return Number(one.getAttribute('data-rows')); })"
    )
    assert counted == [
        len(model["wallet_panel"]["rows"]),
        len(model["leaderboard_panel"]["rows"]),
    ], counted


def test_the_page_paints_the_tier_colour_on_the_drawn_cell(page: Page, model: dict):
    """The colour is read back computed off the element the page really built."""
    painted = page.js(
        "getComputedStyle(window.HOST.querySelector("
        "'[data-part=\"table\"] tbody [data-part=\"table-cell\"]')).color"
    )
    channels = [int(one, 16) for one in re.findall(r"..", model["tier_colors"][LEADER_TIER][1:])]
    assert painted == "rgb(" + ", ".join(str(one) for one in channels) + ")", painted


def test_the_relay_field_and_connect_button_are_drawn_switched_off(page: Page):
    """This tab is read only: neither control may be reachable."""
    assert page.parsed(
        "[window.HOST.querySelector('[data-name=\"relay_url\"]').disabled,"
        " window.HOST.querySelector('[data-name=\"connect_button\"]').disabled]"
    ) == [True, True]


BOARD_SIZE = (520, 160)


def cell_colours(board, row: int, column: int) -> set:
    """Every colour painted inside one rendered cell of a live table."""
    from PySide6.QtCore import QPoint

    from tests.qt_pixel import pixel_at, render_widget

    image = render_widget(board, size=BOARD_SIZE)
    rect = board.visualRect(board.model().index(row, column))
    origin = board.viewport().mapTo(board, rect.topLeft())
    found = set()
    for down in range(rect.height()):
        for across in range(rect.width()):
            point = QPoint(origin.x() + across, origin.y() + down)
            if 0 <= point.x() < image.width() and 0 <= point.y() < image.height():
                found.add(pixel_at(image, point))
    return found


def test_the_leader_rank_cell_paints_the_colour_the_surface_names(tmp_path: Path):
    """Read off the composited pixels, never off a style sheet."""
    from PySide6.QtWidgets import QTableWidget

    tab = qt_tab(tmp_path)
    tables = tab.findChildren(QTableWidget)
    assert len(tables) == 2, f"the tab builds {len(tables)} tables, not two"
    board = tables[-1]
    painted = cell_colours(board, 0, 0)
    assert len(painted) > 1, f"the leader cell painted one colour only: {painted}"
    assert surface.AMBER.lower() in painted, sorted(painted)


def test_no_rank_cell_below_the_leader_paints_that_colour(tmp_path: Path):
    """The amber above is the leader's alone, so the pixel scan can report."""
    from PySide6.QtWidgets import QTableWidget

    tab = qt_tab(tmp_path)
    board = tab.findChildren(QTableWidget)[-1]
    painted = cell_colours(board, 1, 0)
    assert len(painted) > 1, f"the second cell painted one colour only: {painted}"
    assert surface.AMBER.lower() not in painted, sorted(painted)
