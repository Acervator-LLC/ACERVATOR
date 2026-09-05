"""Drives `shared_testnet.js` against `shared_testnet_surface.py`.

The shared TestNet bridge holds the one chain the accumulation engine
and the Local Testnet tab both reach. It draws nothing, so this module
draws nothing: it holds the bridge's answer so a panel can show the
chain, the queue and the last save without asking again.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import shared_testnet_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "shared_testnet.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

API = "acervatorSharedTestnet."
SETTER = "acervatorSetSharedTestnet"
LOADER = "module_loader.js"

MODULE_TAIL = "})(window);"
MODULE_READ_ATTEMPTS = 200
#: A pause between reads, so retrying does not hold MODULE_PATH open
#: against the os.replace in another worker.
MODULE_READ_PAUSE_S = 0.01


def read_module() -> str:
    """Return MODULE_PATH text ending with MODULE_TAIL, retrying while not."""
    for _ in range(MODULE_READ_ATTEMPTS):
        found = MODULE_PATH.read_text(encoding="utf-8")
        if found.rstrip().endswith(MODULE_TAIL):
            return found
        time.sleep(MODULE_READ_PAUSE_S)
    raise AssertionError(MODULE_PATH.name + " never read back whole")


#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = read_module()

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3

SAVED_AT = 111.0
SYMBOL = "BTC/USDT"
SEASON = 2
BOTS = 4
COMPETITION = "C-1"

#: One request, one drain, one finished worker and one save, so the
#: queue, the worker flags and the saved payload each carry a value.
WHOLE_ROUND = {
    "steps": [
        {
            "do": "request",
            "request": {"symbol": SYMBOL, "season": SEASON, "n_bots": BOTS},
        },
        {"do": "drain"},
        {"do": "worker_done", "result": {"competition_id": COMPETITION}},
        {"do": "save", "saved_at": SAVED_AT},
    ]
}

#: One request that is still waiting, so the queue is not empty.
ONE_QUEUED = {
    "steps": [
        {
            "do": "request",
            "request": {"symbol": SYMBOL, "season": SEASON, "n_bots": BOTS},
        }
    ]
}

#: A request taken by a worker that has not finished, so one runs.
MID_RUN = {"steps": ONE_QUEUED["steps"] + [{"do": "drain"}]}

RESET_REASON = "a stated reason"
AFTER_RESET = {"steps": [{"do": "reset", "reason": RESET_REASON}]}


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def answer(params: dict) -> dict:
    """A real ``shared_testnet.state`` answer for one list of steps."""
    return as_json(surface.view_model(params))


class JsRuntime(JsEngine):
    """A QJSEngine holding this module and a ``window`` global."""

    module_path = MODULE_PATH
    setter = SETTER

    def called(self, method: str, *args: Any) -> Any:
        names = []
        for at, value in enumerate(args):
            name = "ARG" + str(at)
            self.bind_json(name, value)
            names.append("JSON.parse(" + name + ")")
        return self.json(API + method + "(" + ", ".join(names) + ")")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The runtime after one whole round has been pushed into it."""
    js.push(answer(WHOLE_ROUND))
    return js


# What the module holds


def test_the_module_defines_its_globals(js: JsRuntime):
    assert js.json("typeof " + API.rstrip(".")) == "object"
    assert js.json("typeof " + SETTER) == "function"
    assert js.json(API + "method") == surface.METHOD


def test_a_pushed_answer_is_held_whole(js: JsRuntime):
    given = answer(WHOLE_ROUND)
    assert js.push(given) == {"loaded": True, "fault": None}
    assert js.json(API + "isLoaded()") is True
    assert js.json(API + "payload()") == given


def test_a_push_of_something_that_is_not_an_answer_is_refused(js: JsRuntime):
    """The positive control for the acceptance above."""
    assert js.push("not an answer") == {"loaded": False, "fault": "not-an-object"}
    assert js.json(API + "isLoaded()") is False
    assert js.json(API + "payload()") is None


def test_forget_drops_the_answer_a_push_stored(loaded: JsRuntime):
    assert loaded.json(API + "isLoaded()") is True
    loaded.run(API + "forget()")
    assert loaded.json(API + "isLoaded()") is False
    assert loaded.json(API + "chain()") == {}
    assert loaded.json(API + "summary()") is None


def test_the_saved_file_is_named_the_way_the_surface_names_it(loaded: JsRuntime):
    given = answer(WHOLE_ROUND)
    assert loaded.json(API + "schemaVersion()") == surface.SCHEMA_VERSION
    assert loaded.json(API + "persistParts()") == given["persist"]["parts"]
    assert loaded.json(API + "persistPath()") == surface.persist_relative_text()
    assert loaded.json(API + "persistWired()") is True
    assert loaded.json(API + "loggerName()") == surface.LOGGER_NAME


def test_a_bridge_with_no_saved_file_reports_itself_unwired(js: JsRuntime):
    """The positive control for the wiring report above."""
    model = surface.SharedTestnetModel(persist_parts=None)
    js.push(as_json(surface.build_view_model(model)))
    assert js.json(API + "persistWired()") is False


def test_every_chain_field_is_read_by_the_name_the_answer_publishes(
    loaded: JsRuntime,
):
    given = answer(WHOLE_ROUND)
    assert loaded.json(API + "chain()") == given["chain"]
    for name, value in given["chain"].items():
        assert loaded.called("chainField", name) == value, name
    assert loaded.json(API + "payloadKeys()") == given["payload_keys"]
    assert loaded.json(API + "genesisHash()") == surface.GENESIS_HASH
    assert loaded.json(API + "txKeyField()") == surface.TX_KEY_FIELD


def test_a_chain_field_the_answer_never_carried_reads_as_nothing(loaded: JsRuntime):
    """The positive control for the chain reader above."""
    assert loaded.called("chainField", "no_such_field") is None
    assert loaded.called("chainList", "no_such_field") == []


@pytest.mark.parametrize("row", sorted(surface.build_view_model()["rows"]))
def test_each_chain_row_carries_its_own_required_fields(loaded: JsRuntime, row: str):
    given = answer(WHOLE_ROUND)["rows"][row]
    assert given["required"], row
    assert loaded.called("rowRequired", row) == given["required"]
    assert loaded.called("rowDefaults", row) == given["defaults"]


def test_the_three_chain_rows_require_three_different_field_lists(loaded: JsRuntime):
    """Two empty lists would compare equal and hide a crossed row."""
    names = loaded.json(API + "rowNames()")
    assert sorted(names) == ["Block", "ChainEvent", "TxRecord"], names
    seen = [loaded.called("rowRequired", name) for name in names]
    assert all(one for one in seen), seen
    assert len({json.dumps(one) for one in seen}) == len(names), seen


def test_a_row_name_the_answer_never_carried_requires_nothing(loaded: JsRuntime):
    """The positive control for the row reader above."""
    assert loaded.called("rowRequired", "NoSuchRow") == []
    assert loaded.called("rowDefaults", "NoSuchRow") == {}


# The queue, the worker and the save


def test_a_waiting_request_is_reported_on_the_queue(js: JsRuntime):
    given = answer(ONE_QUEUED)
    assert given["queued"], "the queue fixture is empty"
    js.push(given)
    assert js.json(API + "queueDepth()") == len(given["queued"])
    assert js.json(API + "queued()") == given["queued"]
    assert js.json(API + "queued()")[0]["symbol"] == SYMBOL


def test_a_drained_queue_is_reported_empty(js: JsRuntime):
    """The positive control for the queue report above."""
    js.push(answer(MID_RUN))
    assert js.json(API + "queueDepth()") == 0
    assert js.json(API + "queued()") == []


def test_a_worker_that_is_still_running_is_reported_running(js: JsRuntime):
    js.push(answer(MID_RUN))
    assert js.json(API + "workerRunning()") is True
    assert js.json(API + "workerHeld()") is True


def test_a_worker_that_has_finished_is_reported_stopped(loaded: JsRuntime):
    """The positive control for the running report above."""
    assert loaded.json(API + "workerRunning()") is False
    assert loaded.json(API + "workerHeld()") is False


def test_a_finished_round_reports_the_payload_the_save_wrote(loaded: JsRuntime):
    found = loaded.json(API + "persisted()")
    assert found is not None
    assert found["saved_at"] == SAVED_AT
    assert found["schema_version"] == surface.SCHEMA_VERSION
    assert loaded.json(API + "savePending()") is False


def test_a_round_that_has_not_saved_yet_owes_a_save_and_holds_no_payload(
    js: JsRuntime,
):
    """The positive control for the saved-payload report above."""
    unsaved = {"steps": WHOLE_ROUND["steps"][:-1]}
    js.push(answer(unsaved))
    assert js.json(API + "persisted()") is None
    assert js.json(API + "savePending()") is True


def test_the_recorded_calls_are_the_ones_the_bridge_made(loaded: JsRuntime):
    given = answer(WHOLE_ROUND)
    assert given["calls"], "the call fixture is empty"
    assert loaded.json(API + "calls()") == given["calls"]
    assert loaded.json(API + "callNames()") == given["call_names"]
    for name in set(given["calls"]):
        assert loaded.called("callCount", name) == given["calls"].count(name), name


def test_a_call_the_bridge_never_made_is_counted_zero(loaded: JsRuntime):
    """The positive control for the call counter above."""
    assert loaded.called("callCount", surface.DRAIN_BUSY) == 0
    assert surface.DRAIN_BUSY in loaded.json(API + "callNames()")


def test_a_reset_reports_the_signals_it_raised(js: JsRuntime):
    given = answer(AFTER_RESET)
    js.push(given)
    assert js.json(API + "raisedSignals()") == given["raised_signals"]
    assert js.json(API + "raisedSignals()") == ["chain_reset", "chain_updated"]
    assert js.json(API + "signals()") == list(surface.SIGNALS)
    assert js.json(API + "workerSignal()") == surface.WORKER_SIGNAL


def test_a_bridge_that_raised_nothing_reports_no_signal(js: JsRuntime):
    """The positive control for the raised-signal report above."""
    js.push(answer({"steps": []}))
    assert js.json(API + "raisedSignals()") == []
    assert js.json(API + "signals()") == list(surface.SIGNALS)


def test_the_timers_and_topics_are_the_ones_the_surface_published(loaded: JsRuntime):
    given = answer(WHOLE_ROUND)
    assert loaded.json(API + "timers()") == given["timers"]
    assert loaded.json(API + "timerDelaysMs()") == given["timer_delays_ms"]
    assert loaded.json(API + "singleShotTimers()") == given["single_shot_timers"]
    assert loaded.json(API + "autostartTimers()") == given["autostart_timers"]
    assert loaded.json(API + "busTopics()") == given["bus_topics"]
    assert loaded.json(API + "actions()") == given["actions"]
    assert loaded.json(API + "installAttributes()") == given["install_attributes"]


def test_a_request_carries_the_four_fields_the_surface_names_and_no_other(
    loaded: JsRuntime,
):
    built = loaded.called(
        "requestFrom",
        {"symbol": SYMBOL, "season": SEASON, "n_bots": BOTS, "invented": "dropped"},
    )
    assert list(built) == list(surface.REQUEST_FIELDS)
    assert built == surface.request_payload(SYMBOL, SEASON, BOTS)
    assert loaded.json(API + "requestFields()") == list(surface.REQUEST_FIELDS)
    assert loaded.json(API + "defaultBotCount()") == surface.DEFAULT_BOT_COUNT
    assert loaded.json(API + "defaultResetReason()") == surface.DEFAULT_RESET_REASON


def test_a_request_given_nothing_still_names_every_field(loaded: JsRuntime):
    """The positive control for the request builder above."""
    built = loaded.called("requestFrom", {})
    assert list(built) == list(surface.REQUEST_FIELDS)
    assert set(built.values()) == {None}


def test_the_summary_counts_each_chain_list_and_the_queue(js: JsRuntime):
    given = answer(MID_RUN)
    found = js.push(given) and js.json(API + "summary()")
    assert found["blocks"] == len(given["chain"]["blocks"])
    assert found["blocks"] > 0, "the genesis block is missing from the fixture"
    assert found["transactions"] == len(given["chain"]["transactions"])
    assert found["block_number"] == given["chain"]["block_number"]
    assert found["queued"] == 0
    assert found["worker_running"] is True
    assert found["save_pending"] is False


def test_the_summary_moves_when_the_bridge_state_moves(js: JsRuntime):
    """The positive control: two real rounds summarise differently."""
    js.push(answer(ONE_QUEUED))
    waiting = js.json(API + "summary()")
    js.push(answer(WHOLE_ROUND))
    done = js.json(API + "summary()")
    assert waiting["queued"] == 1
    assert done["queued"] == 0
    assert waiting["worker_running"] is False
    assert done["worker_running"] is False
    assert waiting != done


# The module writes no value of its own


def test_the_module_writes_no_number():
    """A numeric literal typed here has no publisher to compare it against."""
    found = js_literals(MODULE_SOURCE)["numbers"]
    assert not found, f"{MODULE_PATH.name} holds numeric literals: {found}"


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"{MODULE_PATH.name} holds colour literals: {found}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    found = js_literals(MODULE_SOURCE)["slashes"]
    assert not found, (
        f"{MODULE_PATH.name} holds a slash outside a comment, which the"
        f" literal scan cannot read: {found}"
    )


def carried_values() -> set:
    """Every value the bridge carries that is not also a field name.

    A reader must hold the answer's own field names to read anything, so
    a value that doubles as one of them is not evidence of a copied value.
    """
    carried = set(surface.CALL_NAMES)
    carried.update(surface.PAYLOAD_KEYS)
    carried.update(surface.PERSIST_PARTS)
    carried.add(surface.GENESIS_HASH)
    carried.add(surface.DEFAULT_RESET_REASON)
    return carried - set(surface.build_view_model())


def test_no_string_in_the_module_spells_out_a_value_the_bridge_carries():
    written = carried_values().intersection(js_literals(MODULE_SOURCE)["strings"])
    assert not written, f"{MODULE_PATH.name} spells out bridge values: {written}"


def test_the_value_scan_still_watches_the_values_that_are_not_field_names():
    """The positive control: dropping the field names leaves a real set."""
    watched = carried_values()
    assert surface.GENESIS_HASH in watched
    assert surface.DEFAULT_RESET_REASON in watched
    assert surface.DRAIN_BUSY in watched
    assert "queued" not in watched
    assert "queued" in set(surface.build_view_model())


WRITTEN_LINES = {
    "colour": 'var written = "#00ffcc";',
    "number": "var written = 12;",
    "regex": "var written = /ab+c/;",
    "carried": 'var written = "' + surface.GENESIS_HASH + '";',
}


def caught_by_scan(source: str) -> set:
    literals = js_literals(source)
    found = set()
    if literals["numbers"]:
        found.add("number")
    if HEX_COLOUR.findall(source):
        found.add("colour")
    if literals["slashes"]:
        found.add("regex")
    if surface.GENESIS_HASH in literals["strings"]:
        found.add("carried")
    return found


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    assert kind in caught_by_scan(
        WRITTEN_LINES[kind]
    ), f"the scan reported nothing on the {kind} line"


def test_each_written_literal_is_caught_in_the_module_file_itself():
    """The positive control: the file itself would report the fault it lacks."""
    original = MODULE_PATH.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    assert original.decode("utf-8") == MODULE_SOURCE
    caught_each = {}
    try:
        for kind in sorted(WRITTEN_LINES):
            swap_module(MODULE_PATH, original + WRITTEN_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(MODULE_PATH, original)
            assert (
                hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before
            ), f"the file was not restored after the {kind} line"
    finally:
        swap_module(MODULE_PATH, original)
    quiet = sorted(kind for kind, caught in caught_each.items() if kind not in caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_renderer_loads_this_module_after_the_loader_that_injects_it():
    order = load_order()
    assert MODULE_PATH.name in order, order
    assert runs_after(order, MODULE_PATH.name, LOADER), order


def test_the_order_reading_answers_no_for_the_two_the_other_way_round():
    """The positive control for the load-order reading above."""
    assert not runs_after([MODULE_PATH.name, LOADER], MODULE_PATH.name, LOADER)
    assert not runs_after([LOADER], MODULE_PATH.name, LOADER)


# The module inside the real renderer page


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        for _ in range(PAGE_ATTEMPTS):
            self.open_page()
            if self.module_ready():
                return
        raise AssertionError(
            "the page never defined the shared testnet module in "
            + str(PAGE_ATTEMPTS)
            + " loads: readyState "
            + str(self.js("document.readyState"))
        )

    def open_page(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        link = self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(link)
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def module_ready(self) -> bool:
        for _ in range(READY_ROUNDS):
            if self.js("typeof window." + SETTER) == "function":
                return True
            self.settle(READY_STEP_MS)
        return False

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
        assert "v" in box, "the browser never answered: " + script[:80]
        return box["v"]

    def parsed(self, expression: str) -> Any:
        return json.loads(self.js("JSON.stringify(" + expression + ")"))

    def settle(self, milliseconds: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def close(self) -> None:
        self._view.deleteLater()


@pytest.fixture()
def browser(qapp):
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


def test_the_page_runs_this_module_and_it_answers_a_real_round(browser: Browser):
    given = answer(WHOLE_ROUND)
    browser.js("window.GIVEN = " + json.dumps(json.dumps(given)) + ";")
    browser.js(SETTER + "(JSON.parse(window.GIVEN));")
    assert browser.parsed(API + "isLoaded()") is True
    assert browser.parsed(API + "persistPath()") == surface.persist_relative_text()
    assert browser.parsed(API + "summary()")["queued"] == 0
    assert browser.parsed(API + "calls()") == given["calls"]


def test_the_page_answers_nothing_before_a_round_is_pushed(browser: Browser):
    """The positive control for the page check above."""
    browser.js(API + "forget();")
    assert browser.parsed(API + "isLoaded()") is False
    assert browser.parsed(API + "summary()") is None
