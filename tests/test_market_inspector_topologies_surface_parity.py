"""The Qt topology-proposal pane and the Qt-free surface, side by side.

A failure means the view model describes a different pane, a different
card, a different preview screen, a different log line, a different
branch or a different dismissal than
``src.gui.market_inspector_topologies`` produces on the same input.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import logging
import math
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import market_inspector_topologies_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.repo_tree import named
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PANE_SOURCE = REPO_ROOT / "src" / "gui" / "market_inspector_topologies.py"
WIRING_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
ELEMENT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
NESTED_CLASS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "stock_main_window.py"
GUI_READER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "market_inspector.py"
TRADING_READER_NEIGHBOUR = REPO_ROOT / "src" / "trading" / "market_inspector.py"

PANE_SIZE = (520, 460)
DIALOG_SIZE = (760, 520)

FIXED_NOW = 1700000000.0
LATER_NOW = 1700000600.0
SEEDED_MOMENTS = (FIXED_NOW, LATER_NOW)
PLATFORM_CHOSE = "<the platform chose this>"

MISSING = object()


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def as_text(value):
    """`value` with every number written as its own text.

    ``12`` and ``12.0`` are one value to a comparison and two different
    numbers to a reader, and two not-a-numbers are never equal to each
    other. Both are settled here before anything is compared.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, dict):
        return {key: as_text(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_text(inner) for inner in value]
    return value


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(
            as_text(value), sort_keys=True, ensure_ascii=True, default=repr
        ).encode("utf-8")
    ).hexdigest()


def settled(expiry):
    """One dismissal expiry, kept when the held clock seeded it.

    An expiry the wall clock chose is a fact about the second the run
    started, not about the product, so it is hidden behind one marker.
    """
    for moment in SEEDED_MOMENTS:
        if expiry == moment + surface.DISMISS_TTL_SECONDS:
            return expiry
    return PLATFORM_CHOSE


def settled_cache(held):
    """A whole dismissal cache with every unseeded expiry hidden."""
    return {str(key): settled(value) for key, value in held.items()}


# ---------------------------------------------------------------------
# The stand-ins. One of each, handed to both sides.
# ---------------------------------------------------------------------


class HeldClock:
    """Hold the shipped module's clock at one second for the block.

    The shipped pane reads ``time.time()`` in four places. The name is
    checked before it is replaced, so a module that stopped carrying it
    ends the test rather than reading as held.
    """

    def __init__(self, moment=FIXED_NOW):
        self.moment = moment
        self.module = None
        self.first = None

    def __enter__(self):
        import src.gui.market_inspector_topologies as shipped

        if not hasattr(shipped, "time"):
            raise AssertionError(
                "the shipped pane no longer carries a name called 'time', so "
                "holding the clock through it would invent an attribute and "
                "hold nothing"
            )
        self.module = shipped
        self.first = shipped.time
        held = self.moment

        class Held:
            @staticmethod
            def time():
                return held

        shipped.time = Held
        return self

    def __exit__(self, _kind, _value, _trace):
        self.module.time = self.first
        return False


class CollectingHandler(logging.Handler):
    """Holds the level and the text of every line written through it."""

    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append([record.levelname, record.getMessage()])


SEATS_TAKEN: list = []


class CapturedLog:
    """Every line the pane's own logger writes while the block runs.

    Each side takes its own seat on the process-wide logger and gives it
    back, so a run that stops part way leaves no handler behind.
    """

    def __init__(self, name=surface.LOGGER_NAME):
        self.logger = logging.getLogger(name)
        self.handler = CollectingHandler()
        self.first_level = None

    def __enter__(self):
        self.first_level = self.logger.level
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)
        SEATS_TAKEN.append(self.handler)
        return self

    def __exit__(self, _kind, _value, _trace):
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.first_level)
        return False

    @property
    def lines(self):
        return [list(one) for one in self.handler.lines]


class Confirm:
    """The question box the pane asks before it suppresses a proposal.

    ``Yes`` and ``No`` are the platform's own values, read off the real
    box rather than written down, so the pane compares what it always
    compares.
    """

    asked: list = []
    answer = None
    Yes = None
    No = None

    @classmethod
    def question(cls, _parent, title, text, buttons, default):
        cls.asked.append([title, text, int(buttons), int(default)])
        return cls.answer


class StubbedConfirm:
    """Put the question box in place of the shipped one, then restore."""

    def __init__(self, answer_yes=True):
        self.answer_yes = answer_yes
        self.module = None
        self.first = None

    def __enter__(self):
        from PySide6.QtWidgets import QMessageBox

        import src.gui.market_inspector_topologies as shipped

        if not hasattr(shipped, "QMessageBox"):
            raise AssertionError(
                "the shipped pane no longer carries a name called "
                "'QMessageBox', so replacing it would invent an attribute"
            )
        Confirm.Yes = QMessageBox.Yes
        Confirm.No = QMessageBox.No
        Confirm.asked = []
        Confirm.answer = QMessageBox.Yes if self.answer_yes else QMessageBox.No
        self.module = shipped
        self.first = shipped.QMessageBox
        shipped.QMessageBox = Confirm
        return self

    def __exit__(self, _kind, _value, _trace):
        self.module.QMessageBox = self.first
        return False

    @property
    def asked(self):
        return [list(one) for one in Confirm.asked]


class StubbedPreviewExec:
    """Hold every preview screen the pane opens instead of showing it."""

    def __init__(self):
        self.opened = []
        self.holder = None
        self.first = None
        self.declared = False

    def __enter__(self):
        import src.gui.market_inspector_topologies as shipped

        if not hasattr(shipped.TopologyPreviewDialog, "exec"):
            raise AssertionError(
                "the shipped preview screen no longer carries 'exec', so "
                "replacing it would invent an attribute"
            )
        self.holder = shipped.TopologyPreviewDialog
        self.declared = "exec" in vars(self.holder)
        self.first = vars(self.holder)["exec"] if self.declared else None
        opened = self.opened

        def held(screen):
            opened.append(screen)
            return 0

        shipped.TopologyPreviewDialog.exec = held
        return self

    def __exit__(self, _kind, _value, _trace):
        """Put the class back as it was found.

        The screen inherits ``exec`` rather than declaring it. Assigning
        the old value back would leave a declared name behind, and the
        method counter would read one method more in every later test.
        """
        if self.declared:
            self.holder.exec = self.first
        else:
            del self.holder.exec
        return False


class Store:
    """The settings manager both sides write their dismissals through."""

    def __init__(self, holds=None, get_raises=None, set_raises=None):
        self.holds = holds
        self.get_raises = get_raises
        self.set_raises = set_raises
        self.wrote = []
        self.read = 0

    def get(self, key, default=None):
        self.read += 1
        if self.get_raises is not None:
            raise self.get_raises
        return default if self.holds is MISSING else self.holds

    def set(self, key, value):
        if self.set_raises is not None:
            raise self.set_raises
        self.wrote.append([key, {str(k): settled(v) for k, v in value.items()}])


class Source:
    """The detector both sides ask for proposals."""

    def __init__(self, proposals=None, raises=None):
        self.proposals = proposals
        self.raises = raises
        self.asked = 0

    def __call__(self):
        self.asked += 1
        if self.raises is not None:
            raise self.raises
        return copy.deepcopy(self.proposals)


# ---------------------------------------------------------------------
# The inputs. One scenario builds one starting state for both sides.
# ---------------------------------------------------------------------


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 🚀"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "O'Brien's venue said no"
REFUSAL_TEXT = "venue refused the order"

THOUSAND_MILLION = 1e9
ONE_BILLIONTH = 1e-9


def bot(**named):
    """One bot row of a proposal."""
    row = {
        "asset": "ETH",
        "role": "target",
        "symbol": "ETH/USD",
        "existing_bot_id": "",
        "suggested_target_usd": 1500.0,
    }
    row.update(named)
    return row


def wire(**named):
    """One wire row of a proposal."""
    row = {
        "source_asset": "BTC",
        "target_asset": "ETH",
        "pct": 25.0,
        "rationale": "funnel",
    }
    row.update(named)
    return row


def proposal(**named):
    """One proposal, as the detector hands it over."""
    held = {
        "id": "p1",
        "title": "BTC funnel",
        "archetype": "momentum_funnel",
        "score": 88.0,
        "assets": ["BTC", "ETH"],
        "bots": [
            bot(asset="BTC", existing_bot_id="b1", suggested_target_usd=0.0),
            bot(),
        ],
        "wires": [wire()],
        "adopt_notes": ["note one", "note two"],
    }
    held.update(named)
    return held


SECOND_PROPOSAL = proposal(
    id="p2", title="ETH pair", archetype="mean_reversion_pair", score=40.0
)


def scenario(name, **named):
    """One driving set: what the detector answers and what the store holds."""
    spec = {
        "name": name,
        "proposals": [proposal(), SECOND_PROPOSAL],
        "error": None,
        "error_text": REFUSAL_TEXT,
        "store": MISSING,
        "store_holds": None,
        "store_get_error": None,
        "store_set_error": None,
        "now": FIXED_NOW,
        "refresh": True,
        "preview": None,
        "adopt": False,
        "dismiss": None,
        "confirm_yes": True,
    }
    spec.update(named)
    return spec


def refusing(name, error="RuntimeError", **named):
    """One driving set whose detector throws instead of answering."""
    return scenario(name, error=error, **named)


def one(name, **named):
    """One driving set holding a single proposal built from `named`."""
    return scenario(name, proposals=[proposal(**named)])


WIRED_STORE = "wired"

SCENARIOS = [
    scenario("happy"),
    scenario("no_proposals", proposals=[]),
    scenario("the_detector_answered_nothing", proposals=None),
    scenario("the_pane_was_never_refreshed", refresh=False),
    one("title_is_empty", title=""),
    one("title_is_unicode", title=UNICODE_TEXT),
    one("title_is_two_hundred_characters", title=LONG_TEXT),
    one("title_is_markup", title=MARKUP_TEXT),
    one("title_has_an_apostrophe", title=APOSTROPHE_TEXT),
    one("title_has_a_newline", title=NEWLINE_TEXT),
    one("title_in_wrong_capitals", title="BTC FUNNEL"),
    one("title_is_a_number_where_text_belongs", title=12345),
    one("title_is_missing", title=MISSING),
    one("score_is_zero", score=0),
    one("score_is_negative", score=-1),
    one("score_is_a_thousand_million", score=THOUSAND_MILLION),
    one("score_is_one_billionth", score=ONE_BILLIONTH),
    one("score_is_infinite", score=math.inf),
    one("score_is_minus_infinity", score=-math.inf),
    one("score_is_not_a_number", score=math.nan),
    one("score_is_at_the_high_edge", score=80.0),
    one("score_is_under_the_high_edge", score=79.9),
    one("score_is_at_the_mid_edge", score=50.0),
    one("score_is_under_the_mid_edge", score=49.9),
    one("score_is_a_number_written_as_text", score="88"),
    one("score_is_text_where_a_number_belongs", score="NOT A NUMBER"),
    one("score_is_nothing", score=None),
    one("score_is_missing", score=MISSING),
    one("archetype_is_unknown", archetype="a_shape_nobody_named"),
    one("archetype_is_empty", archetype=""),
    one("archetype_in_wrong_capitals", archetype="MOMENTUM_FUNNEL"),
    one("archetype_is_a_number_where_text_belongs", archetype=98765),
    one("archetype_is_missing", archetype=MISSING),
    one("no_bots_and_no_wires", bots=[], wires=[], assets=[]),
    one("every_bot_already_exists", bots=[bot(existing_bot_id="b1")]),
    one("target_capital_is_zero", bots=[bot(suggested_target_usd=0)]),
    one("target_capital_is_negative", bots=[bot(suggested_target_usd=-1)]),
    one(
        "target_capital_is_a_thousand_million",
        bots=[bot(suggested_target_usd=THOUSAND_MILLION)],
    ),
    one(
        "target_capital_is_one_billionth",
        bots=[bot(suggested_target_usd=ONE_BILLIONTH)],
    ),
    one("target_capital_is_infinite", bots=[bot(suggested_target_usd=math.inf)]),
    one(
        "target_capital_is_minus_infinity",
        bots=[bot(suggested_target_usd=-math.inf)],
    ),
    one("target_capital_is_not_a_number", bots=[bot(suggested_target_usd=math.nan)]),
    one(
        "target_capital_is_a_number_written_as_text",
        bots=[bot(suggested_target_usd="1500")],
    ),
    one("bot_asset_is_unicode", bots=[bot(asset=UNICODE_TEXT)]),
    one("bot_asset_is_two_hundred_characters", bots=[bot(asset=LONG_TEXT)]),
    one("bot_asset_is_markup", bots=[bot(asset=MARKUP_TEXT)]),
    one("bot_asset_has_an_apostrophe", bots=[bot(asset=APOSTROPHE_TEXT)]),
    one("bot_asset_has_a_newline", bots=[bot(asset=NEWLINE_TEXT)]),
    one("bot_asset_is_a_number_where_text_belongs", bots=[bot(asset=12345)]),
    one("bot_fields_are_missing", bots=[{}]),
    one("wire_rate_is_zero", wires=[wire(pct=0)]),
    one("wire_rate_is_negative", wires=[wire(pct=-1)]),
    one("wire_rate_is_a_thousand_million", wires=[wire(pct=THOUSAND_MILLION)]),
    one("wire_rate_is_one_billionth", wires=[wire(pct=ONE_BILLIONTH)]),
    one("wire_rate_is_infinite", wires=[wire(pct=math.inf)]),
    one("wire_rate_is_minus_infinity", wires=[wire(pct=-math.inf)]),
    one("wire_rate_is_not_a_number", wires=[wire(pct=math.nan)]),
    one("wire_rate_is_a_number_written_as_text", wires=[wire(pct="25")]),
    one("wire_rationale_is_two_hundred_characters", wires=[wire(rationale=LONG_TEXT)]),
    one("wire_rationale_is_unicode", wires=[wire(rationale=UNICODE_TEXT)]),
    one("wire_fields_are_missing", wires=[{}]),
    one("adopt_notes_are_empty", adopt_notes=[]),
    one("adopt_note_is_unicode", adopt_notes=[UNICODE_TEXT]),
    one("adopt_note_is_two_hundred_characters", adopt_notes=[LONG_TEXT]),
    one("proposal_has_no_id", id=MISSING),
    one("proposal_id_is_unicode", id=UNICODE_TEXT),
    one("proposal_id_is_a_number_where_text_belongs", id=12345),
    scenario("a_proposal_is_nothing", proposals=[proposal(), None]),
    scenario("the_detector_answered_a_number", proposals=12345),
    refusing("the_detector_refused"),
    refusing("the_detector_refused_on_a_value", error="ValueError"),
    refusing("the_detector_refused_on_a_type", error="TypeError"),
    refusing("the_detector_refused_on_a_key", error="KeyError", error_text="symbol"),
    refusing("the_detector_divided_by_zero", error="ZeroDivisionError"),
    refusing("the_detector_refused_plainly", error="Exception"),
    refusing("the_detector_name_is_invented", error="DetectorGone"),
    refusing("the_detector_name_in_wrong_capitals", error="runtimeerror"),
    refusing("the_detector_name_has_a_newline", error="Detector\nGone"),
    refusing("the_refusal_text_is_empty", error_text=""),
    refusing("the_refusal_text_is_zero", error_text=0),
    refusing("the_refusal_text_is_negative", error_text=-1),
    refusing("the_refusal_text_is_a_thousand_million", error_text=THOUSAND_MILLION),
    refusing("the_refusal_text_is_one_billionth", error_text=ONE_BILLIONTH),
    refusing("the_refusal_text_is_infinite", error_text=math.inf),
    refusing("the_refusal_text_is_minus_infinity", error_text=-math.inf),
    refusing("the_refusal_text_is_not_a_number", error_text=math.nan),
    refusing("the_refusal_text_is_a_number", error_text=12345),
    refusing("the_refusal_text_is_a_number_written_as_text", error_text="12345"),
    refusing("the_refusal_text_is_unicode", error_text=UNICODE_TEXT),
    refusing("the_refusal_text_is_two_hundred_characters", error_text=LONG_TEXT),
    refusing("the_refusal_text_is_markup", error_text=MARKUP_TEXT),
    refusing("the_refusal_text_has_an_apostrophe", error_text=APOSTROPHE_TEXT),
    refusing("the_refusal_text_has_a_newline", error_text=NEWLINE_TEXT),
    refusing("the_refusal_text_in_wrong_capitals", error_text="VENUE REFUSED"),
    refusing("the_refusal_text_is_nothing", error_text=None),
    refusing("the_operator_stopped_the_run", error="KeyboardInterrupt"),
    refusing("the_run_was_asked_to_exit", error="SystemExit"),
    scenario("the_store_holds_nothing", store=WIRED_STORE, store_holds=None),
    scenario(
        "the_store_holds_a_live_dismissal",
        store=WIRED_STORE,
        store_holds={"p1": FIXED_NOW + 5000},
    ),
    scenario(
        "the_store_holds_a_lapsed_dismissal",
        store=WIRED_STORE,
        store_holds={"p1": FIXED_NOW - 5000},
    ),
    scenario(
        "the_store_holds_a_dismissal_that_lapses_now",
        store=WIRED_STORE,
        store_holds={"p1": FIXED_NOW},
    ),
    scenario(
        "the_store_holds_an_expiry_that_is_not_a_number",
        store=WIRED_STORE,
        store_holds={"p1": "soon"},
    ),
    scenario(
        "the_store_holds_an_expiry_that_is_nothing",
        store=WIRED_STORE,
        store_holds={"p1": None},
    ),
    scenario(
        "the_store_holds_a_number_as_a_key",
        store=WIRED_STORE,
        store_holds={7: FIXED_NOW + 5000},
    ),
    scenario(
        "the_store_holds_an_infinite_expiry",
        store=WIRED_STORE,
        store_holds={"p1": math.inf},
    ),
    scenario(
        "the_store_holds_a_not_a_number_expiry",
        store=WIRED_STORE,
        store_holds={"p1": math.nan},
    ),
    scenario("the_store_is_empty", store=WIRED_STORE, store_holds={}),
    scenario("the_store_is_a_list", store=WIRED_STORE, store_holds=["p1"]),
    scenario("the_store_is_a_number", store=WIRED_STORE, store_holds=12345),
    scenario(
        "the_store_could_not_be_read",
        store=WIRED_STORE,
        store_get_error=OSError("store down"),
    ),
    scenario(
        "the_store_refused_the_write",
        store=WIRED_STORE,
        store_set_error=OSError("disk full"),
        dismiss="p1",
    ),
    scenario("a_proposal_was_dismissed", dismiss="p1"),
    scenario("a_proposal_was_dismissed_and_saved", store=WIRED_STORE, dismiss="p1"),
    scenario("the_dismissal_was_refused", dismiss="p1", confirm_yes=False),
    scenario("the_dismissed_id_is_empty", dismiss=""),
    scenario("the_dismissed_id_is_unknown", dismiss="nobody"),
    scenario("a_proposal_was_previewed", preview="p1"),
    scenario("a_proposal_was_previewed_and_adopted", preview="p1", adopt=True),
    scenario("the_previewed_id_is_unknown", preview="nobody"),
    scenario("the_second_proposal_was_previewed", preview="p2", adopt=True),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}

BASE_ERRORS = {
    "KeyboardInterrupt": KeyboardInterrupt,
    "SystemExit": SystemExit,
}


def spec_error(spec):
    """The exception the detector throws for `spec`, or nothing."""
    if spec["error"] is None:
        return None
    base = BASE_ERRORS.get(spec["error"])
    if base is not None:
        return base(spec["error_text"])
    return surface.error_from(spec["error"], spec["error_text"])


def cleaned(held):
    """One proposal with every field marked missing taken out."""
    if not isinstance(held, dict):
        return held
    return {key: value for key, value in held.items() if value is not MISSING}


def spec_proposals(spec):
    """The proposals `spec` hands the detector, missing fields removed."""
    held = spec["proposals"]
    if not isinstance(held, list):
        return held
    return [cleaned(item) for item in held]


def spec_source(spec):
    """A detector built from `spec`, fresh for the side that asks."""
    return Source(proposals=spec_proposals(spec), raises=spec_error(spec))


def spec_store(spec):
    """A settings store built from `spec`, or nothing when unwired."""
    if spec["store"] is MISSING:
        return None
    return Store(
        holds=spec["store_holds"],
        get_raises=spec["store_get_error"],
        set_raises=spec["store_set_error"],
    )


# ---------------------------------------------------------------------
# Driving the two sides. One scenario, one held clock, one set of steps.
# ---------------------------------------------------------------------


def flush_deleted():
    """Run the deletions the pane put off until the next loop turn.

    _clear_cards takes a card out of the layout and calls
    deleteLater. With no event loop turning, the card stays a child
    of the scroll body and still paints. The running app turns its loop,
    so the turn is made here before anything is read or rendered.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def drive_old(spec):
    """Build the shipped pane and walk the scenario's steps on it."""
    import src.gui.market_inspector_topologies as shipped

    app()
    source = spec_source(spec)
    store = spec_store(spec)
    adopted = []
    with HeldClock(spec["now"]), CapturedLog() as log, StubbedPreviewExec() as screens:
        with StubbedConfirm(spec["confirm_yes"]) as confirm:
            pane = shipped.MarketInspectorTopologies()
            pane.adoptRequested.connect(adopted.append)
            if store is not None:
                pane.set_dismiss_store(store)
            pane.set_proposal_source(source)
            if spec["refresh"]:
                pane.refresh()
            if spec["preview"] is not None:
                pane._on_preview(spec["preview"])
                if spec["adopt"] and screens.opened:
                    screens.opened[-1]._on_adopt()
            if spec["dismiss"] is not None:
                pane._on_dismiss(spec["dismiss"])
            asked = confirm.asked
    flush_deleted()
    return {
        "pane": pane,
        "source": source,
        "store": store,
        "log": log.lines,
        "screens": screens.opened,
        "confirms": asked,
        "adopted": adopted,
    }


def drive_new(spec):
    """Build the surface model and walk the same steps on it."""
    source = spec_source(spec)
    store = spec_store(spec)
    model = surface.TopologiesPaneModel(spec["now"])
    model.confirm_answer = (
        surface.CONFIRM_YES if spec["confirm_yes"] else surface.CONFIRM_DEFAULT_BUTTON
    )
    if store is not None:
        model.set_dismiss_store(store)
    model.set_proposal_source(source)
    if spec["refresh"]:
        model.refresh()
    if spec["preview"] is not None:
        opened = model.on_preview(spec["preview"])
        if spec["adopt"] and opened is not None:
            model.adopt_from(opened)
    if spec["dismiss"] is not None:
        model.on_dismiss(spec["dismiss"])
    return {"model": model, "source": source, "store": store}


# ---------------------------------------------------------------------
# Reading the two sides
# ---------------------------------------------------------------------


def order_of(layout):
    """What each item in `layout` is, in the order it was added."""
    found = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        if widget is not None:
            found.append(type(widget).__name__)
        elif item.layout() is not None:
            found.append("layout:" + type(item.layout()).__name__)
        else:
            found.append(surface.STRETCH)
    return found


def widget_at(layout, index):
    return layout.itemAt(index).widget()


def layout_at(layout, index):
    return layout.itemAt(index).layout()


def box_of(layout):
    """One layout's four margins, as plain numbers."""
    margins = layout.contentsMargins()
    return [margins.left(), margins.top(), margins.right(), margins.bottom()]


def card_reading(card):
    """Every value one proposal card shows."""
    root = card.layout()
    top = layout_at(root, 0)
    return {
        "accessible_name": card.accessibleName(),
        "title": widget_at(top, 0).text(),
        "badge": widget_at(top, 1).text(),
        "badge_style": widget_at(top, 1).styleSheet(),
        "meta": widget_at(root, 1).text(),
    }


def qt_screen(pane):
    """What the pane's scroll body holds, and each card's values."""
    group = widget_at(pane.layout(), 1)
    scroll = widget_at(group.layout(), 0)
    body = scroll.widget().layout()
    elements = order_of(body)
    cards = [
        card_reading(widget_at(body, index))
        for index, element in enumerate(elements)
        if element == surface.CARD_CLASS
    ]
    return elements, cards


def row_cells(item, columns):
    """The text of every cell one row carries."""
    return [item.text(column) for column in range(columns)]


def row_colors(item, columns):
    """The colour of every cell, with an unpainted cell read as nothing.

    A cell with no colour set and a cell that does not exist both answer
    black, so the paint is read off the row's own record instead.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    found = []
    for column in range(columns):
        painted = item.data(column, Qt.ForegroundRole)
        found.append(
            None if painted is None else QColor(item.foreground(column).color()).name()
        )
    return found


def tree_reading(tree):
    """Every value one of the preview's two lists shows."""
    columns = tree.columnCount()
    return {
        "columns": [tree.headerItem().text(index) for index in range(columns)],
        "column_total": columns,
        "tooltip": tree.toolTip(),
        "root_is_decorated": tree.rootIsDecorated(),
        "alternating": tree.alternatingRowColors(),
        "resize_mode": tree.header().sectionResizeMode(0).name,
        "rows": [
            row_cells(tree.topLevelItem(index), columns)
            for index in range(tree.topLevelItemCount())
        ],
        "colors": [
            row_colors(tree.topLevelItem(index), columns)
            for index in range(tree.topLevelItemCount())
        ],
        "cells_per_row": [
            tree.topLevelItem(index).columnCount()
            for index in range(tree.topLevelItemCount())
        ],
    }


def qt_preview_reading(screen):
    """Every value one preview screen shows."""
    root = screen.layout()
    header = layout_at(root, 0)
    body = layout_at(root, 1)
    bots_box = widget_at(body, 0)
    wires_box = widget_at(body, 1)
    notes = []
    index = 3
    while index < root.count() - 1:
        notes.append(widget_at(root, index).text())
        index += 1
    buttons = layout_at(root, root.count() - 1)
    adopt = widget_at(buttons, 2)
    return {
        "window_title": screen.windowTitle(),
        "minimum_size": [screen.minimumWidth(), screen.minimumHeight()],
        "margins": box_of(root),
        "spacing": root.spacing(),
        "body_spacing": body.spacing(),
        "title": widget_at(header, 0).text(),
        "title_style": widget_at(header, 0).styleSheet(),
        "badge": widget_at(header, 2).text(),
        "badge_style": widget_at(header, 2).styleSheet(),
        "header_order": order_of(header),
        "bots_box_title": bots_box.title(),
        "bots": tree_reading(widget_at(bots_box.layout(), 0)),
        "wires_box_title": wires_box.title(),
        "wires": tree_reading(widget_at(wires_box.layout(), 0)),
        "summary": widget_at(root, 2).text(),
        "summary_style": widget_at(root, 2).styleSheet(),
        "notes": notes,
        "note_styles": [
            widget_at(root, 3 + offset).styleSheet() for offset in range(len(notes))
        ],
        "note_word_wrap": [
            widget_at(root, 3 + offset).wordWrap() for offset in range(len(notes))
        ],
        "cancel_text": widget_at(buttons, 1).text(),
        "cancel_is_default": widget_at(buttons, 1).isDefault(),
        "adopt_text": adopt.text(),
        "adopt_enabled": adopt.isEnabled(),
        "adopt_tooltip": adopt.toolTip(),
        "order": order_of(root),
    }


def qt_timer_reading(pane):
    """Every timer the shipped pane built, as its delay and its state."""
    from PySide6.QtCore import QTimer

    return [
        [timer.interval(), timer.isActive(), timer.isSingleShot()]
        for timer in pane.findChildren(QTimer)
    ]


def qt_trace(driven, spec):
    """Every value the built Qt pane can be asked for, as plain data."""
    pane = driven["pane"]
    layout = pane.layout()
    top = layout_at(layout, 0)
    group = widget_at(layout, 1)
    scroll = widget_at(group.layout(), 0)
    elements, cards = qt_screen(pane)
    store = driven["store"]
    return {
        "status_text": widget_at(top, 2).text(),
        "status_style": widget_at(top, 2).styleSheet(),
        "refresh_text": widget_at(top, 0).text(),
        "refresh_tooltip": widget_at(top, 0).toolTip(),
        "group_title": group.title(),
        "scroll_resizable": scroll.widgetResizable(),
        "scroll_margins": box_of(scroll.widget().layout()),
        "scroll_spacing": scroll.widget().layout().spacing(),
        "footer_text": widget_at(layout, 2).text(),
        "footer_style": widget_at(layout, 2).styleSheet(),
        "margins": box_of(layout),
        "spacing": layout.spacing(),
        "order": order_of(layout),
        "top_order": order_of(top),
        "timers": qt_timer_reading(pane),
        "screen": elements,
        "cards": cards,
        "proposals": [held.get("id") for held in pane.current_proposals()],
        "dismissed": qt_dismissal_reading(pane, spec),
        "persisted": [] if store is None else [list(one) for one in store.wrote],
        "store_reads": 0 if store is None else store.read,
        "asked": driven["source"].asked,
        "warnings": driven["log"],
        "confirms": driven["confirms"],
        "previews": [qt_preview_reading(one) for one in driven["screens"]],
        "adopt_requests": [held.get("id") for held in driven["adopted"]],
    }


def watched_ids(spec):
    """Every proposal id the dismissal cache is asked about."""
    found = ["p1", "p2", "nobody", 7, spec["dismiss"]]
    holds = spec["store_holds"]
    if isinstance(holds, dict):
        found.extend(holds)
    return [held for held in found if held not in (None, "")]


def qt_dismissal_reading(pane, spec):
    """Whether each watched id is suppressed, read through the pane."""
    return {
        str(held): pane.is_dismissed(held, now=spec["now"])
        for held in watched_ids(spec)
    }


def surface_dismissal_reading(model, spec):
    """The same reading, taken through the surface's own accessor."""
    return {
        str(held): model.is_dismissed(held, now=spec["now"])
        for held in watched_ids(spec)
    }


def surface_trace(driven, spec):
    """The same values, read from the Qt-free view model."""
    model = driven["model"]
    payload = surface.build_view_model(model)
    pane = payload["pane"]
    dialog = payload["dialog"]
    return {
        "status_text": payload["status_text"],
        "status_style": pane["status_style"],
        "refresh_text": pane["refresh_text"],
        "refresh_tooltip": pane["refresh_tooltip"],
        "group_title": pane["list_group_title"],
        "scroll_resizable": pane["scroll_widget_resizable"],
        "scroll_margins": list(pane["scroll_margins"]),
        "scroll_spacing": pane["scroll_spacing"],
        "footer_text": pane["footer_text"],
        "footer_style": pane["footer_style"],
        "margins": list(pane["margins"]),
        "spacing": pane["spacing"],
        "order": [
            "layout:QHBoxLayout",
            "QGroupBox",
            surface.LABEL_CLASS,
        ],
        "top_order": ["QPushButton", surface.STRETCH, surface.LABEL_CLASS],
        "timers": [
            [
                payload["timer_interval_ms"],
                payload["timer_running"],
                payload["timer_single_shot"],
            ]
        ],
        "screen": list(payload["screen"]),
        "cards": [dict(one) for one in payload["cards"]],
        "proposals": list(payload["proposals"]),
        "dismissed": surface_dismissal_reading(model, spec),
        "persisted": list(payload["persisted"]),
        "store_reads": 0 if driven["store"] is None else driven["store"].read,
        "asked": driven["source"].asked,
        "warnings": [list(one) for one in payload["warnings"]],
        "confirms": [
            [title, text, confirm_value(buttons), confirm_value([default])]
            for title, text, buttons, default in payload["confirm"]["asked"]
        ],
        "previews": [
            surface_preview_reading(one, payload, dialog) for one in payload["previews"]
        ],
        "adopt_requests": list(payload["adopt_requests"]),
    }


def confirm_value(names):
    """The platform's own number for the buttons the surface names.

    The names come off the view model and the numbers off the real
    question box, so neither side of the comparison is written down.
    """
    from PySide6.QtWidgets import QMessageBox

    value = 0
    for name in names:
        value |= int(getattr(QMessageBox, name))
    return value


def surface_tree_reading(columns, tooltip, rows, colors, dialog):
    """One of the preview's two lists, in the shape the Qt reading takes."""
    return {
        "columns": list(columns),
        "column_total": dialog["column_total"],
        "tooltip": tooltip,
        "root_is_decorated": dialog["root_is_decorated"],
        "alternating": dialog["alternating_row_colors"],
        "resize_mode": dialog["resize_mode"],
        "rows": [list(row) for row in rows],
        "colors": [list(row) for row in colors],
        "cells_per_row": [len(row) for row in rows],
    }


def surface_preview_reading(preview, payload, dialog):
    """Every value one preview screen shows, off the view model."""
    notes = list(preview["notes"])
    return {
        "window_title": preview["window_title"],
        "minimum_size": [dialog["min_width"], dialog["min_height"]],
        "margins": list(dialog["margins"]),
        "spacing": dialog["spacing"],
        "body_spacing": dialog["body_spacing"],
        "title": preview["title"],
        "title_style": dialog["header_title_style"],
        "badge": preview["badge"],
        "badge_style": preview["badge_style"],
        "header_order": [
            surface.LABEL_CLASS,
            surface.STRETCH,
            surface.LABEL_CLASS,
        ],
        "bots_box_title": dialog["bots_box_title"],
        "bots": surface_tree_reading(
            dialog["bots_columns"],
            dialog["bots_tooltip"],
            preview["bot_rows"],
            preview["bot_colors"],
            dialog,
        ),
        "wires_box_title": dialog["wires_box_title"],
        "wires": surface_tree_reading(
            dialog["wires_columns"],
            dialog["wires_tooltip"],
            preview["wire_rows"],
            [[None] * dialog["column_total"] for _ in preview["wire_rows"]],
            dialog,
        ),
        "summary": preview["summary"],
        "summary_style": dialog["summary_style"],
        "notes": notes,
        "note_styles": [dialog["note_style"]] * len(notes),
        "note_word_wrap": [dialog["note_word_wrap"]] * len(notes),
        "cancel_text": dialog["cancel_text"],
        "cancel_is_default": dialog["cancel_is_default"],
        "adopt_text": dialog["adopt_text"],
        "adopt_enabled": preview["adopt_enabled"],
        "adopt_tooltip": preview["adopt_tooltip"],
        "order": [
            "layout:QHBoxLayout",
            "layout:QHBoxLayout",
            surface.LABEL_CLASS,
        ]
        + [surface.LABEL_CLASS] * len(notes)
        + ["layout:QHBoxLayout"],
    }


def headline(text) -> str:
    """The first line of an error message."""
    lines = str(text).splitlines()
    return lines[0] if lines else ""


def outcome(work):
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except BaseException as exc:
        return {"outcome": "refused", "error": type(exc).__name__}


def old_outcome(spec):
    return outcome(lambda: qt_trace(drive_old(spec), spec))


def new_outcome(spec):
    return outcome(lambda: surface_trace(drive_new(spec), spec))


# ---------------------------------------------------------------------
# The two sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_pane(name):
    """A card, a screen, a colour, a log line or a dismissal differs."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    assert as_text(new["value"]) == as_text(old["value"]), name
    assert digest(new["value"]) == digest(old["value"]), name


REFUSING_SCENARIOS = (
    "score_is_text_where_a_number_belongs",
    "score_is_nothing",
    "a_proposal_is_nothing",
    "the_detector_answered_a_number",
    "the_operator_stopped_the_run",
    "the_run_was_asked_to_exit",
)


def test_both_answers_and_refusals_are_in_the_measured_set():
    """Every input was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for spec in SCENARIOS:
        old = old_outcome(spec)
        (answered if old["outcome"] == "answered" else refused).append(spec["name"])
    assert answered, "no input was answered"
    assert refused, "no input was refused"
    assert set(refused) == set(REFUSING_SCENARIOS), sorted(refused)
    assert len(answered) + len(refused) == len(SCENARIOS)
    assert len(answered) == len(SCENARIOS) - len(REFUSING_SCENARIOS)


@pytest.mark.parametrize("name", REFUSING_SCENARIOS)
def test_a_refused_input_names_the_same_error_on_both_sides(name):
    """One side swallowed a refusal the other let through.

    Only the error's kind is compared. The wording of these refusals is
    the interpreter's, and this host runs a different release from the
    build machine.
    """
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert new["error"] == old["error"], (name, old, new)


def test_a_stop_and_an_exit_reach_the_operator_on_both_sides():
    """The pane swallowed a stop the operator asked for."""
    for name in ("the_operator_stopped_the_run", "the_run_was_asked_to_exit"):
        spec = BY_NAME[name]
        assert old_outcome(spec)["error"] in ("KeyboardInterrupt", "SystemExit"), name
        assert new_outcome(spec)["error"] == old_outcome(spec)["error"], name


def test_the_refusal_reader_takes_one_line_at_a_time():
    """A refusal read whole would carry its wording into the comparison."""
    assert headline("only one line") == "only one line"
    assert headline("first line\nsecond line") == "first line"
    assert headline("") == ""


DIFFERENT_INPUT_PAIR = ("happy", "no_proposals")


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    first, second = DIFFERENT_INPUT_PAIR
    one = old_outcome(BY_NAME[first])["value"]
    other = new_outcome(BY_NAME[second])["value"]
    assert one["cards"] and not other["cards"]
    assert one["status_text"] != other["status_text"]
    assert digest(one) != digest(other)
    assert digest(one) == digest(old_outcome(BY_NAME[first])["value"])
    assert len(digest(one)) == 64


def test_the_hash_tells_the_two_inputs_apart_the_other_way_round():
    """The comparison reports only when the shipped side is the first one."""
    first, second = DIFFERENT_INPUT_PAIR
    one = new_outcome(BY_NAME[first])["value"]
    other = old_outcome(BY_NAME[second])["value"]
    assert digest(one) != digest(other)
    assert digest(other) == digest(new_outcome(BY_NAME[second])["value"])


@pytest.mark.parametrize(
    "name",
    [
        "happy",
        "no_proposals",
        "the_detector_refused",
        "a_proposal_was_previewed_and_adopted",
        "a_proposal_was_dismissed_and_saved",
        "title_is_unicode",
    ],
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a reading that carries nothing."""
    old = old_outcome(BY_NAME[name])["value"]
    new = new_outcome(BY_NAME[name])["value"]
    assert isinstance(old, dict)
    assert len(old) > 20, sorted(old)
    assert digest(old) == digest(new)
    assert len(digest(old)) == 64


def test_the_hash_tells_a_whole_number_from_a_decimal():
    """A whole number and a decimal of one value hash the same."""
    assert 12 == 12.0
    assert digest({"spacing": 12}) != digest({"spacing": 12.0})
    assert as_text(12) == "12"
    assert as_text(12.0) == "12.0"


def test_two_not_a_numbers_read_as_one_value_before_comparing():
    """Two not-a-numbers compared directly report a difference that is none."""
    assert math.nan != math.nan
    assert as_text(math.nan) == as_text(math.nan)
    assert digest({"score": math.nan}) == digest({"score": math.nan})
    assert digest({"score": math.nan}) != digest({"score": math.inf})
    assert digest({"score": math.inf}) != digest({"score": -math.inf})


def test_a_swapped_screen_order_is_reported_by_the_hash():
    """A card and the stretch changed places and the hash said nothing."""
    straight = {"screen": [surface.CARD_CLASS, surface.STRETCH]}
    swapped = {"screen": [surface.STRETCH, surface.CARD_CLASS]}
    assert sorted(straight["screen"]) == sorted(swapped["screen"])
    assert digest(straight) != digest(swapped)


def test_two_cards_of_one_screen_are_not_compared_to_each_other():
    """The two cards carry one input, so swapping them compares nothing."""
    reading = old_outcome(BY_NAME["happy"])["value"]
    first, second = reading["cards"]
    assert first != second
    assert first["title"] != second["title"]
    assert first["badge"] != second["badge"]
    assert first["badge_style"] != second["badge_style"]
    assert digest(reading["cards"]) != digest([second, first])


# ---------------------------------------------------------------------
# The values the platform chooses
# ---------------------------------------------------------------------


def test_a_seeded_expiry_is_kept_and_an_unseeded_one_is_hidden():
    """The rule hides every expiry, so a real one could never be compared."""
    seeded = FIXED_NOW + surface.DISMISS_TTL_SECONDS
    assert settled(seeded) == seeded
    assert settled(LATER_NOW + surface.DISMISS_TTL_SECONDS) == (
        LATER_NOW + surface.DISMISS_TTL_SECONDS
    )
    assert settled(seeded + 1) == PLATFORM_CHOSE
    assert settled_cache({"p1": seeded, "p2": seeded + 1}) == {
        "p1": seeded,
        "p2": PLATFORM_CHOSE,
    }


def test_an_expiry_the_wall_clock_chose_is_hidden_on_the_shipped_side():
    """A dismissal taken with no held clock reached the comparison."""
    import src.gui.market_inspector_topologies as shipped

    app()
    store = Store()
    pane = shipped.MarketInspectorTopologies()
    pane.set_dismiss_store(store)
    with HeldClock(FIXED_NOW):
        pane.dismiss("held")
    pane.dismiss("loose")
    held, loose = store.wrote[-2][1], store.wrote[-1][1]
    assert held["held"] == FIXED_NOW + surface.DISMISS_TTL_SECONDS
    assert loose["loose"] == PLATFORM_CHOSE
    assert loose["held"] == FIXED_NOW + surface.DISMISS_TTL_SECONDS


# ---------------------------------------------------------------------
# Step sequences, including one that refuses part way
# ---------------------------------------------------------------------


def test_a_second_refresh_carries_the_same_screen_on_both_sides():
    """The second paint of the pane shows something other than the first."""
    import src.gui.market_inspector_topologies as shipped

    spec = BY_NAME["happy"]
    app()
    with HeldClock(FIXED_NOW):
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(spec_source(spec))
        pane.refresh()
        first = qt_screen(pane)
        pane.refresh()
        assert qt_screen(pane) == first

    model = surface.TopologiesPaneModel(FIXED_NOW)
    model.set_proposal_source(spec_source(spec))
    model.refresh()
    once = [list(model.scroll_body), model.status_text]
    model.refresh()
    assert once == [list(model.scroll_body), model.status_text]
    assert once[0] == first[0]


def test_a_refresh_that_refuses_leaves_the_earlier_screen_on_both_sides():
    """A detector failure wiped the cards the operator was reading."""
    import src.gui.market_inspector_topologies as shipped

    good = BY_NAME["happy"]
    app()
    with HeldClock(FIXED_NOW), CapturedLog() as log:
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(spec_source(good))
        pane.refresh()
        before = qt_screen(pane)
        pane.set_proposal_source(Source(raises=RuntimeError(REFUSAL_TEXT)))
        pane.refresh()
        after = qt_screen(pane)
    assert before[0] == [surface.CARD_CLASS, surface.CARD_CLASS, surface.STRETCH]
    assert after == before
    assert len(log.lines) == 1

    model = surface.TopologiesPaneModel(FIXED_NOW)
    model.set_proposal_source(spec_source(good))
    model.refresh()
    model.set_proposal_source(Source(raises=RuntimeError(REFUSAL_TEXT)))
    model.refresh()
    assert list(model.scroll_body) == after[0]
    assert model.status_text == surface.status_error(RuntimeError(REFUSAL_TEXT))
    assert [level for level, _text in model.warnings] == ["ERROR"]


def test_a_repaint_that_refuses_part_way_keeps_the_cards_already_drawn():
    """A card that will not build left the list half drawn.

    The shipped pane clears the whole list, then adds one card at a
    time. A card that refuses ends the repaint with the cards already
    added still on screen and no stretch under them. Both sides are
    driven with one starting state and must stop in the same place.
    """
    import src.gui.market_inspector_topologies as shipped

    app()
    good = proposal(id="a")
    bad = proposal(id="b", score="NOT A NUMBER")
    held = [good, bad, proposal(id="c")]
    with HeldClock(FIXED_NOW):
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(Source(proposals=held))
        with pytest.raises(ValueError):
            pane.refresh()
        left = qt_screen(pane)

    model = surface.TopologiesPaneModel(FIXED_NOW)
    model.set_proposal_source(Source(proposals=held))
    with pytest.raises(ValueError):
        model.refresh()
    assert list(model.scroll_body) == left[0]
    assert left[0] == [surface.CARD_CLASS]
    assert surface.STRETCH not in left[0]
    assert [one["title"] for one in model_cards(model)] == [
        one["title"] for one in left[1]
    ]


def model_cards(model):
    """The card values one surface model holds."""
    return [
        {
            "accessible_name": surface.CARD_ACCESSIBLE_NAME,
            "title": card.title_text,
            "badge": card.badge_text,
            "badge_style": card.badge_style,
            "meta": card.meta_text,
        }
        for card in model.cards
    ]


def test_a_dismissal_leaves_the_count_line_stale_on_both_sides():
    """The status line was refreshed after a dismissal on one side only.

    The shipped pane drops the card and repaints, but never rewrites the
    count line, so it keeps naming the numbers from the last refresh.
    """
    old = old_outcome(BY_NAME["a_proposal_was_dismissed"])["value"]
    new = new_outcome(BY_NAME["a_proposal_was_dismissed"])["value"]
    assert old["status_text"] == new["status_text"]
    assert old["proposals"] == new["proposals"] == ["p2"]
    assert old["status_text"] == surface.status_count(2, 0)
    assert old["status_text"] != surface.status_count(len(old["proposals"]), 1)


def test_a_refresh_after_a_dismissal_drops_the_card_on_both_sides():
    """A dismissed proposal came back on the next refresh."""
    import src.gui.market_inspector_topologies as shipped

    spec = BY_NAME["happy"]
    app()
    with HeldClock(FIXED_NOW), StubbedConfirm(True):
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(spec_source(spec))
        pane.refresh()
        pane._on_dismiss("p1")
        pane.refresh()
        after = qt_screen(pane)
        status = widget_at(layout_at(pane.layout(), 0), 2).text()

    model = surface.TopologiesPaneModel(FIXED_NOW)
    model.set_proposal_source(spec_source(spec))
    model.refresh()
    model.on_dismiss("p1")
    model.refresh()
    assert list(model.scroll_body) == after[0]
    assert model.status_text == status
    assert model.status_text == surface.status_count(1, 1)


def test_a_dismissal_lapses_after_the_full_day_on_both_sides():
    """The 24 h promise let the card back early, or held it for ever."""
    import src.gui.market_inspector_topologies as shipped

    spec = BY_NAME["happy"]
    app()
    lapsed = FIXED_NOW + surface.DISMISS_TTL_SECONDS
    with HeldClock(FIXED_NOW), StubbedConfirm(True):
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(spec_source(spec))
        pane.refresh()
        pane._on_dismiss("p1")
        assert pane.is_dismissed("p1", now=lapsed - 1) is True
        assert pane.is_dismissed("p1", now=lapsed) is False

    model = surface.TopologiesPaneModel(FIXED_NOW)
    model.set_proposal_source(spec_source(spec))
    model.refresh()
    model.on_dismiss("p1")
    assert model.is_dismissed("p1", now=lapsed - 1) is True
    assert model.is_dismissed("p1", now=lapsed) is False


def test_a_lapsed_dismissal_is_swept_and_saved_on_both_sides():
    """A lapsed dismissal stayed in the cache and in the settings file."""
    import src.gui.market_inspector_topologies as shipped

    spec = BY_NAME["happy"]
    app()
    lapsed = FIXED_NOW + surface.DISMISS_TTL_SECONDS + 1
    old_store = Store()
    with HeldClock(FIXED_NOW), StubbedConfirm(True):
        pane = shipped.MarketInspectorTopologies()
        pane.set_dismiss_store(old_store)
        pane.set_proposal_source(spec_source(spec))
        pane.refresh()
        pane._on_dismiss("p1")
    with HeldClock(lapsed):
        pane.refresh()
    assert old_store.wrote[-1][1] == {}

    new_store = Store()
    model = surface.TopologiesPaneModel(FIXED_NOW)
    model.set_dismiss_store(new_store)
    model.set_proposal_source(spec_source(spec))
    model.refresh()
    model.on_dismiss("p1")
    model.refresh(lapsed)
    assert new_store.wrote[-1][1] == old_store.wrote[-1][1]
    assert [one[1] for one in new_store.wrote] == [one[1] for one in old_store.wrote]


def test_the_preview_screen_is_built_once_per_request_on_both_sides():
    """The pane reused a stale preview screen, or built one per card."""
    import src.gui.market_inspector_topologies as shipped

    spec = BY_NAME["happy"]
    app()
    with HeldClock(FIXED_NOW), StubbedPreviewExec() as screens:
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(spec_source(spec))
        pane.refresh()
        pane._on_preview("p1")
        pane._on_preview("p2")
        pane._on_preview("nobody")
    assert len(screens.opened) == 2
    titles = [one.windowTitle() for one in screens.opened]

    model = surface.TopologiesPaneModel(FIXED_NOW)
    model.set_proposal_source(spec_source(spec))
    model.refresh()
    model.on_preview("p1")
    model.on_preview("p2")
    assert model.on_preview("nobody") is None
    assert len(model.previews) == 2
    assert [one.window_title for one in model.previews] == titles
    assert titles[0] != titles[1]


# ---------------------------------------------------------------------
# The enumeration: wiring, signals, classes, methods, timers, topics
# ---------------------------------------------------------------------


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def imported_names(tree) -> set:
    """Every name a module binds through an import."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                found.add(alias.asname or alias.name.split(".")[0])
    return found


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            target = node.args[0]
            found.append(
                (
                    dotted(node.func.value),
                    (
                        "lambda"
                        if isinstance(target, ast.Lambda)
                        else dotted(
                            target.func if isinstance(target, ast.Call) else target
                        )
                    ),
                )
            )
    return sorted(found)


def signal_sites(path) -> list:
    """Every ``Signal(`` the module declares, as the name it binds."""
    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        if not dotted(node.value.func).endswith("Signal"):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                found.append(target.id)
    return sorted(found)


def timer_sites(path) -> list:
    """Every ``QTimer(`` construction in `path`, counted as a call."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path) -> list:
    """Every ``subscribe(`` site in `path`, as the topic it names."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def built_classes(path, layouts: bool) -> list:
    """Every imported class `path` constructs, counted as a call.

    `layouts` picks the arrangers, whose names end in ``Layout``; False
    picks the screen elements the operator sees. A name is counted only
    where it is CONSTRUCTED, so an import line alone is not a build.
    """
    tree = parsed(path)
    names = imported_names(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        made = dotted(node.func)
        if made not in names or not made[:1].isupper() or made == "Signal":
            continue
        if made.endswith("Layout") is layouts:
            found.append(made)
    return sorted(found)


def source_functions(path) -> list:
    """Every function the source declares, nested ones included."""
    return sorted(
        node.name
        for node in ast.walk(parsed(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def source_classes(path) -> list:
    """Every class the source declares, including one inside a method."""
    return sorted(
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    )


def declared_methods(holder) -> list:
    """Every real member `holder` declares that a caller can reach.

    A plain function, a static one, a class one and a read-only value
    all count. A signal does not: it is callable and is not a method.
    """
    from PySide6.QtCore import Signal

    found = []
    for name, value in vars(holder).items():
        if name.startswith("__") and name != "__init__":
            continue
        if isinstance(value, Signal):
            continue
        if isinstance(value, (staticmethod, classmethod, property)) or callable(value):
            found.append(name)
    return sorted(found)


def loose_methods(holder) -> list:
    """Every callable `holder` declares, signals counted as methods."""
    return sorted(
        name
        for name, value in vars(holder).items()
        if callable(value) and not name.startswith("__")
    )


SHIPPED_ACTIONS = {
    ("card.dismissClicked", "self._on_dismiss"): "card.dismissClicked",
    ("card.previewClicked", "self._on_preview"): "card.previewClicked",
    ("dismiss_btn.clicked", "lambda"): "card.dismiss_button.clicked",
    ("dlg.adoptClicked", "self.adoptRequested.emit"): "preview.adoptClicked",
    ("preview_btn.clicked", "lambda"): "card.preview_button.clicked",
    ("self._adopt_btn.clicked", "self._on_adopt"): "preview.adopt_button.clicked",
    ("self._cancel_btn.clicked", "self.reject"): "preview.cancel_button.clicked",
    ("self._refresh_btn.clicked", "self.refresh"): "refresh_button.clicked",
    ("self._timer.timeout", "self.refresh"): "auto_refresh_timer.timeout",
}


def test_every_wired_action_has_a_counterpart_and_the_counter_can_report():
    """The pane wires an action the surface names none of.

    The counter reads a call, so a wiring written as a lambda and one
    written as a method name are both counted. It is proved on a
    neighbouring control that wires exactly one.
    """
    wired = connect_sites(PANE_SOURCE)
    assert len(wired) == len(SHIPPED_ACTIONS), wired
    assert sorted(wired) == sorted(SHIPPED_ACTIONS), wired
    assert sorted(SHIPPED_ACTIONS.values()) == sorted(surface.ACTIONS), sorted(
        surface.ACTIONS
    )
    assert len(surface.ACTIONS) == len(wired)
    written = PANE_SOURCE.read_text(encoding="utf-8").count(".connect(")
    assert written == len(wired), (written, wired)
    neighbour = connect_sites(WIRING_NEIGHBOUR)
    assert len(neighbour) == 1, neighbour
    assert neighbour[0][0] == "self.clicked"


def test_every_signal_has_a_counterpart_and_the_counter_can_report():
    """The pane emits a signal the surface names none of."""
    declared = signal_sites(PANE_SOURCE)
    assert declared == sorted(surface.SIGNALS), declared
    assert len(declared) == len(surface.SIGNALS)
    neighbour = signal_sites(SIGNAL_NEIGHBOUR)
    assert len(neighbour) == 3, neighbour
    assert "clicked" in neighbour


def test_the_pane_builds_one_timer_and_the_counter_can_report():
    """The pane runs a timer the surface declares no delay for.

    The counter reads a construction and not a name, so the import line
    alone is not a timer. It is proved on the screen that builds one and
    names it twice.
    """
    built = timer_sites(PANE_SOURCE)
    assert len(built) == 1, built
    assert len(surface.TIMERS) == len(built)
    assert list(surface.TIMER_DELAYS_MS) == [surface.AUTO_REFRESH_MS]
    written = PANE_SOURCE.read_text(encoding="utf-8").count("QTimer")
    assert written > len(built), (written, built)
    neighbour = timer_sites(TIMER_NEIGHBOUR)
    assert len(neighbour) == 1, neighbour


def test_the_pane_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The pane listens on a topic the surface names none of."""
    assert bus_sites(PANE_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) == 2, neighbour
    assert neighbour == ["wire.created", "wire.removed"]


SHIPPED_ELEMENTS = [
    "QGroupBox",
    "QLabel",
    "QPushButton",
    "QScrollArea",
    "QTimer",
    "QTreeWidget",
    "QTreeWidgetItem",
    "QWidget",
]


def test_every_screen_element_has_a_counterpart_and_the_counter_can_report():
    """The pane builds a control the surface's screen names none of.

    The counter reads a construction, so an import line alone is not a
    build. It is proved on a neighbouring card that builds three.
    """
    built = built_classes(PANE_SOURCE, layouts=False)
    assert sorted(set(built)) == SHIPPED_ELEMENTS, sorted(set(built))
    assert len(built) > len(set(built)), built
    arrangers = built_classes(PANE_SOURCE, layouts=True)
    assert sorted(set(arrangers)) == ["QHBoxLayout", "QVBoxLayout"], arrangers
    written = PANE_SOURCE.read_text(encoding="utf-8").count("QWidget")
    assert written > built.count("QWidget"), written
    neighbour = built_classes(ELEMENT_NEIGHBOUR, layouts=False)
    assert len(neighbour) == 3, neighbour
    assert neighbour == ["PrivacyDot", "QLabel", "QLabel"]


SHIPPED_CLASSES = {
    "TopologyPreviewDialog": "TopologyPreviewModel",
    "_ProposalCard": "ProposalCardModel",
    "MarketInspectorTopologies": "TopologiesPaneModel",
}

SHIPPED_METHODS = {
    "TopologyPreviewDialog": ["__init__", "_on_adopt"],
    "_ProposalCard": ["__init__"],
    "MarketInspectorTopologies": [
        "__init__",
        "_clear_cards",
        "_find_proposal",
        "_on_dismiss",
        "_on_preview",
        "_persist_dismissed",
        "_render",
        "_sweep_dismissed",
        "current_proposals",
        "dismiss",
        "is_dismissed",
        "refresh",
        "set_dismiss_store",
        "set_proposal_source",
    ],
}

SHIPPED_FUNCTIONS = ["_archetype_label", "_score_color"]

SURFACE_FUNCTIONS = {
    "_archetype_label": "archetype_label",
    "_score_color": "score_color",
}

SURFACE_METHODS = {
    "TopologyPreviewModel": ["__init__", "adopt", "build", "reject"],
    "ProposalCardModel": ["__init__", "build", "dismiss", "preview"],
    "TopologiesPaneModel": [
        "__init__",
        "adopt_from",
        "at",
        "clear_cards",
        "current_proposals",
        "dismiss",
        "find_proposal",
        "is_dismissed",
        "on_dismiss",
        "on_preview",
        "persist_dismissed",
        "refresh",
        "render",
        "set_dismiss_store",
        "set_proposal_source",
        "sweep_dismissed",
    ],
    "ProposalSource": ["__init__"],
    "DismissStore": ["__init__", "get", "set"],
}


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped pane gained or lost a class or a method."""
    import src.gui.market_inspector_topologies as shipped

    app()
    declared = source_classes(PANE_SOURCE)
    assert declared == sorted(SHIPPED_CLASSES), declared
    assert len(declared) == len(SHIPPED_CLASSES)
    for name, counterpart in SHIPPED_CLASSES.items():
        assert isinstance(getattr(shipped, name), type), name
        assert isinstance(getattr(surface, counterpart), type), counterpart
    total = 0
    for name, methods in SHIPPED_METHODS.items():
        found = declared_methods(getattr(shipped, name))
        assert found == sorted(methods), (name, found)
        total += len(found)
    functions = source_functions(PANE_SOURCE)
    assert sorted(set(functions) - {"__init__"}) == sorted(
        SHIPPED_FUNCTIONS
        + [m for ms in SHIPPED_METHODS.values() for m in ms if m != "__init__"]
    ), functions
    assert len(functions) == total + len(SHIPPED_FUNCTIONS)
    for name, counterpart in SURFACE_FUNCTIONS.items():
        assert callable(getattr(shipped, name)), name
        assert callable(getattr(surface, counterpart)), counterpart


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_METHODS), built
    assert sorted(SHIPPED_CLASSES.values()) == sorted(
        set(SURFACE_METHODS) - {"ProposalSource", "DismissStore"}
    )
    for name, methods in SURFACE_METHODS.items():
        found = declared_methods(getattr(surface, name))
        assert found == sorted(methods), (name, found)


def test_the_method_counter_leaves_a_signal_out_and_takes_a_value_in():
    """The counter reads a signal as a method, or misses a read-only value.

    A signal is callable, so a loose counter takes it in. A read-only
    value is not callable, so a loose counter leaves it out. Both are
    proved on the neighbouring screens that really declare them.
    """
    from PySide6.QtCore import Signal

    from src.gui.indicator_panel import IndicatorVotingPanel
    from src.gui.launcher import ModeCard

    app()
    assert isinstance(vars(ModeCard)["clicked"], Signal)
    assert callable(vars(ModeCard)["clicked"])
    assert "clicked" in loose_methods(ModeCard)
    assert "clicked" not in declared_methods(ModeCard)
    assert "mousePressEvent" in declared_methods(ModeCard)

    assert isinstance(vars(IndicatorVotingPanel)["lock_timeframe"], property)
    assert not callable(vars(IndicatorVotingPanel)["lock_timeframe"])
    assert "lock_timeframe" not in loose_methods(IndicatorVotingPanel)
    assert "lock_timeframe" in declared_methods(IndicatorVotingPanel)
    assert "selected_bot_id" in declared_methods(IndicatorVotingPanel)
    assert isinstance(vars(IndicatorVotingPanel)["_reading_fingerprint"], staticmethod)
    assert "_reading_fingerprint" in declared_methods(IndicatorVotingPanel)


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """A class built inside a method is invisible to the counter."""
    found = source_classes(NESTED_CLASS_NEIGHBOUR)
    assert "_StockLogHandler" in found, found
    top_level = sorted(
        node.name
        for node in parsed(NESTED_CLASS_NEIGHBOUR).body
        if isinstance(node, ast.ClassDef)
    )
    assert "_StockLogHandler" not in top_level
    assert len(found) > len(top_level)


def test_the_readers_match_a_whole_path_and_not_a_name():
    """Two files share a name and the reader added them together."""
    assert GUI_READER_NEIGHBOUR.name == TRADING_READER_NEIGHBOUR.name
    assert GUI_READER_NEIGHBOUR != TRADING_READER_NEIGHBOUR
    assert GUI_READER_NEIGHBOUR.is_file() and TRADING_READER_NEIGHBOUR.is_file()
    joined = source_functions(GUI_READER_NEIGHBOUR) + source_functions(
        TRADING_READER_NEIGHBOUR
    )
    assert len(joined) > len(source_functions(GUI_READER_NEIGHBOUR))
    assert PANE_SOURCE.name not in (
        GUI_READER_NEIGHBOUR.name,
        TRADING_READER_NEIGHBOUR.name,
    )
    assert named(PANE_SOURCE.name) == [PANE_SOURCE]


def test_the_neighbouring_controls_are_seven_different_files():
    """Two controls read one file, so one of the two was never measured."""
    named = [
        WIRING_NEIGHBOUR,
        SIGNAL_NEIGHBOUR,
        TIMER_NEIGHBOUR,
        BUS_NEIGHBOUR,
        ELEMENT_NEIGHBOUR,
        NESTED_CLASS_NEIGHBOUR,
        PANE_SOURCE,
    ]
    assert len(set(named)) == len(named), named
    for path in named:
        assert path.is_file(), path
    assert TIMER_NEIGHBOUR != REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
    assert timer_sites(REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py") == []
    assert timer_sites(TIMER_NEIGHBOUR) != []


# ---------------------------------------------------------------------
# The completeness check
# ---------------------------------------------------------------------


PAYLOAD_KEYS = {
    "ACTIONS": "actions",
    "ADOPT_DISABLED_TOOLTIP": "dialog.adopt_disabled_tooltip",
    "ADOPT_TEXT": "dialog.adopt_text",
    "ADOPT_TOOLTIP": "dialog.adopt_tooltip",
    "ARCHETYPE_LABELS": "archetypes",
    "AUTO_REFRESH_MS": "timer_delays_ms",
    "BOTS_BOX_TITLE": "dialog.bots_box_title",
    "BOTS_COLUMNS": "dialog.bots_columns",
    "BOTS_TOOLTIP": "dialog.bots_tooltip",
    "BOT_STATUS_EXISTING": "dialog.bot_status_existing",
    "BOT_STATUS_NEW_FORMAT": "dialog.bot_status_new_format",
    "BUS_TOPICS": "bus_topics",
    "CALL_NAMES": "call_names",
    "CANCEL_IS_DEFAULT": "dialog.cancel_is_default",
    "CANCEL_TEXT": "dialog.cancel_text",
    "CARD_ACCESSIBLE_NAME": "card.accessible_name",
    "CARD_BADGE_FORMAT": "card.badge_format",
    "CARD_BADGE_STYLE_FORMAT": "card.badge_style_format",
    "CARD_CLASS": "card.class_name",
    "CARD_FRAME_SHADOW": "card.frame_shadow",
    "CARD_FRAME_SHAPE": "card.frame_shape",
    "CARD_MARGINS": "card.margins",
    "CARD_META_FORMAT": "card.meta_format",
    "CARD_META_STYLE": "card.meta_style",
    "CARD_SIZE_POLICY": "card.size_policy",
    "CARD_SPACING": "card.spacing",
    "CARD_STYLE": "card.style",
    "CARD_TITLE_FORMAT": "card.title_format",
    "CARD_TITLE_MARK": "marks.card_title_mark",
    "CARD_TITLE_WORD_WRAP": "card.title_word_wrap",
    "CONFIRM_BUTTONS": "confirm.buttons",
    "CONFIRM_DEFAULT_BUTTON": "confirm.default_button",
    "CONFIRM_TEXT_FORMAT": "confirm.text_format",
    "CONFIRM_TITLE": "confirm.title",
    "CONFIRM_YES": "confirm.yes",
    "DEFAULT_ERROR_TYPE": "defaults.error_type",
    "EMPHASIS_CLOSE": "marks.emphasis_close",
    "EMPHASIS_OPEN": "marks.emphasis_open",
    "EMPHASIS_SLANT": "marks.emphasis_slant",
    "STRONG_CLOSE": "marks.strong_close",
    "STRONG_OPEN": "marks.strong_open",
    "STRONG_WEIGHT": "marks.strong_weight",
    "DIALOG_BODY_SPACING": "dialog.body_spacing",
    "DIALOG_MARGINS": "dialog.margins",
    "DIALOG_MIN_HEIGHT": "dialog.min_height",
    "DIALOG_MIN_WIDTH": "dialog.min_width",
    "DIALOG_SPACING": "dialog.spacing",
    "DIALOG_TITLE_FALLBACK": "dialog.title_fallback",
    "DIALOG_TITLE_FORMAT": "dialog.title_format",
    "DISMISS_SETTINGS_KEY": "dismissal.settings_key",
    "DISMISS_STYLE": "card.dismiss_style",
    "DISMISS_TEXT": "card.dismiss_text",
    "DISMISS_TOOLTIP": "card.dismiss_tooltip",
    "DISMISS_TTL_SECONDS": "dismissal.ttl_seconds",
    "EMPTY_STYLE": "pane.empty_style",
    "EMPTY_TEXT": "pane.empty_text",
    "EMPTY_WORD_WRAP": "pane.empty_word_wrap",
    "ERROR_TYPES": "error_types",
    "FOOTER_STYLE": "pane.footer_style",
    "FOOTER_TEXT": "pane.footer_text",
    "HEADER_BADGE_FORMAT": "dialog.badge_format",
    "HEADER_BADGE_STYLE_FORMAT": "dialog.badge_style_format",
    "HEADER_TITLE_FORMAT": "dialog.header_title_format",
    "HEADER_TITLE_STYLE": "dialog.header_title_style",
    "LABEL_CLASS": "pane.label_class",
    "LIST_GROUP_TITLE": "pane.list_group_title",
    "LOAD_FAILED_FORMAT": "logger.load_failed_format",
    "LOAD_NOT_A_DICT_FORMAT": "logger.load_not_a_dict_format",
    "LOAD_RESTORED_FORMAT": "logger.load_restored_format",
    "LOGGER_NAME": "logger.name",
    "LOG_LEVELS": "logger.levels",
    "NEW_BOT_COLOR": "dialog.new_bot_color",
    "NOTE_FORMAT": "dialog.note_format",
    "NOTE_STYLE": "dialog.note_style",
    "NOTE_WORD_WRAP": "dialog.note_word_wrap",
    "NO_TEXT": "defaults.no_text",
    "PANE_MARGINS": "pane.margins",
    "PANE_SPACING": "pane.spacing",
    "PERSIST_FAILED_FORMAT": "logger.persist_failed_format",
    "PREVIEW_TEXT": "card.preview_text",
    "PREVIEW_TOOLTIP": "card.preview_tooltip",
    "REFRESH_FAILED_FORMAT": "logger.refresh_failed_format",
    "REFRESH_TEXT": "pane.refresh_text",
    "REFRESH_TOOLTIP": "pane.refresh_tooltip",
    "SCORE_HIGH": "score.high",
    "SCORE_HIGH_COLOR": "score.high_color",
    "SCORE_LOW_COLOR": "score.low_color",
    "SCORE_MID": "score.mid",
    "SCORE_MID_COLOR": "score.mid_color",
    "SCROLL_MARGINS": "pane.scroll_margins",
    "SCROLL_SPACING": "pane.scroll_spacing",
    "SCROLL_WIDGET_RESIZABLE": "pane.scroll_widget_resizable",
    "SIGNALS": "signals",
    "START_OF_TIME": "defaults.start_of_time",
    "STATUS_COUNT_FORMAT": "pane.status_count_format",
    "STATUS_ERROR_FORMAT": "pane.status_error_format",
    "STATUS_READY": "pane.status_ready",
    "STATUS_STYLE": "pane.status_style",
    "STATUS_UNWIRED": "pane.status_unwired",
    "STRETCH": "pane.stretch_name",
    "SUMMARY_FORMAT": "dialog.summary_format",
    "SUMMARY_STYLE": "dialog.summary_style",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TIMER_SINGLE_SHOT": "timer_single_shot",
    "TIMER_STARTED_AT_BUILD": "timer_started_at_build",
    "TREE_ALTERNATING_ROW_COLORS": "dialog.alternating_row_colors",
    "TREE_COLUMN_TOTAL": "dialog.column_total",
    "TREE_RESIZE_MODE": "dialog.resize_mode",
    "TREE_ROOT_IS_DECORATED": "dialog.root_is_decorated",
    "WIRES_BOX_TITLE": "dialog.wires_box_title",
    "WIRES_COLUMNS": "dialog.wires_columns",
    "WIRES_TOOLTIP": "dialog.wires_tooltip",
    "WIRE_PCT_FORMAT": "dialog.wire_pct_format",
}

# The branch markers, each carried inside call_names.
CALL_CONSTANTS = (
    "CONFIRM_ASKED",
    "CONFIRM_REFUSED",
    "DISMISS_DROPPED",
    "DISMISS_HELD",
    "DISMISS_IGNORED",
    "DISMISS_PERSISTED",
    "PREVIEW_ADOPTED",
    "PREVIEW_MISSING",
    "PREVIEW_OPENED",
    "REFRESH_ASKED",
    "REFRESH_COUNTED",
    "REFRESH_FAILED",
    "REFRESH_FILTERED",
    "REFRESH_RENDERED",
    "REFRESH_START",
    "REFRESH_SWEPT",
    "REFRESH_UNWIRED",
    "RENDER_CARD",
    "RENDER_CLEARED",
    "RENDER_EMPTY",
    "RENDER_STRETCH",
    "STORE_CLEARED",
    "STORE_LOADED",
    "STORE_NOT_A_DICT",
    "STORE_UNREADABLE",
)

# The log levels, each carried inside logger.levels.
LEVEL_CONSTANTS = ("LEVEL_ERROR", "LEVEL_INFO", "LEVEL_WARNING")

# The two values no snapshot key carries, each with the check that
# covers it. METHOD is the name the bridge registers under and
# PANE_MODEL is the pane state the bridge keeps between calls.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_topology_method",
    "PANE_MODEL": "test_the_bridge_resets_the_pane_state_on_request",
}

STATE_ONLY_KEYS = {
    "adopt_requests",
    "cards",
    "calls",
    "now",
    "persisted",
    "previews",
    "proposals",
    "screen",
    "status_text",
    "timer_interval_ms",
    "timer_running",
    "warnings",
}

# A constant whose payload shape is not the constant itself.
PAYLOAD_READERS = {
    "ERROR_TYPES": sorted,
    "AUTO_REFRESH_MS": lambda value: [value],
}


def at_path(payload, path):
    """The payload value one dotted path names."""
    found = payload
    for step in path.split("."):
        found = found[step]
    return found


def as_carried(name, value):
    """`value` in the shape the payload carries it."""
    reader = PAYLOAD_READERS.get(name)
    if reader is not None:
        return reader(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def surface_constants():
    """Every value the surface exports that is not a function or a class."""
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def fresh_payload():
    """The view model of a pane nothing has driven."""
    return surface.build_view_model(surface.TopologiesPaneModel(FIXED_NOW))


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read.

    A comparison that reads some of the values passes whether the rest
    match or not. Every value is accounted for here: a snapshot path, a
    branch marker, a log level, or one of the two named with the check
    that covers it.
    """
    payload = fresh_payload()
    constants = surface_constants()
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payload, PAYLOAD_KEYS[name]) == as_carried(name, value), name
        elif name in CALL_CONSTANTS:
            assert value in payload["call_names"], name
        elif name in LEVEL_CONSTANTS:
            assert value in payload["logger"]["levels"].values(), name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    named = len(PAYLOAD_KEYS) + len(CALL_CONSTANTS) + len(LEVEL_CONSTANTS)
    assert named + len(NOT_IN_THE_SNAPSHOT) == len(constants), (
        named,
        len(constants),
    )


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = fresh_payload()
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    for key in STATE_ONLY_KEYS:
        assert key in payload
    assert len(payload) == len(answered) + len(STATE_ONLY_KEYS)


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing.

    A value that reaches no snapshot path and no named exception must
    land in the unaccounted list, and a snapshot key nothing backs must
    land in the difference above.
    """
    payload = fresh_payload()
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in CALL_CONSTANTS
    assert invented not in LEVEL_CONSTANTS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "FOOTER_TEXT" in surface_constants()
    assert "SCORE_HIGH_COLOR" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "TopologiesPaneModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "dialog.invented")
    assert set(payload) != {"invented"} | STATE_ONLY_KEYS


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        seen.update(call[0] for call in drive_new(spec)["model"].calls)
    model = surface.TopologiesPaneModel(FIXED_NOW)
    model.set_dismiss_store(None)
    model.refresh()
    seen.update(call[0] for call in model.calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)

    failed = drive_new(BY_NAME["the_detector_refused"])["model"]
    marks = [call[0] for call in failed.calls]
    assert marks.count(surface.REFRESH_FAILED) == 1
    assert surface.REFRESH_COUNTED not in marks
    answered = drive_new(BY_NAME["happy"])["model"]
    answered_marks = [call[0] for call in answered.calls]
    assert answered_marks.count(surface.REFRESH_COUNTED) == 1
    assert answered_marks.index(surface.RENDER_CLEARED) < answered_marks.index(
        surface.RENDER_STRETCH
    )
    assert surface.REFRESH_FAILED not in answered_marks


def test_the_call_trace_reports_a_branch_that_never_ran():
    """The branch reader answers the same whatever the pane did."""
    quiet = surface.TopologiesPaneModel(FIXED_NOW)
    assert quiet.calls == []
    quiet.refresh()
    assert [call[0] for call in quiet.calls] == [
        surface.REFRESH_START,
        surface.REFRESH_UNWIRED,
    ]
    busy = drive_new(BY_NAME["happy"])["model"]
    assert len(busy.calls) > len(quiet.calls)
    assert set(call[0] for call in busy.calls) != set(call[0] for call in quiet.calls)


# ---------------------------------------------------------------------
# The surface carries its own values
# ---------------------------------------------------------------------


MOVED_COLOR = "#123456"
MOVED_TEXT = "MOVED"


def test_the_surface_does_not_follow_a_colour_moved_in_the_shipped_pane(monkeypatch):
    """The surface read its values off the pane it replaces.

    A surface that read the shipped pane would follow it, and the whole
    comparison above would be one side read twice. The shipped ramp is
    moved and the surface must not move with it.
    """
    import src.gui.market_inspector_topologies as shipped

    app()
    spec = BY_NAME["happy"]
    before = qt_trace(drive_old(spec), spec)
    monkeypatch.setattr(shipped, "_score_color", lambda score: MOVED_COLOR)
    moved = qt_trace(drive_old(spec), spec)
    assert MOVED_COLOR in moved["cards"][0]["badge_style"]
    assert MOVED_COLOR not in before["cards"][0]["badge_style"]
    new = surface_trace(drive_new(spec), spec)
    assert MOVED_COLOR not in new["cards"][0]["badge_style"]
    assert new == before
    monkeypatch.undo()
    assert qt_trace(drive_old(spec), spec) == before


def test_the_comparison_names_exactly_which_value_moved(monkeypatch):
    """The comparison reports that something moved without saying what."""
    import src.gui.market_inspector_topologies as shipped

    app()
    spec = BY_NAME["happy"]
    before = qt_trace(drive_old(spec), spec)
    monkeypatch.setattr(shipped, "_score_color", lambda score: MOVED_COLOR)
    moved = qt_trace(drive_old(spec), spec)
    monkeypatch.undo()
    apart = sorted(key for key in before if before[key] != moved[key])
    assert apart == ["cards"], apart
    assert [one["title"] for one in before["cards"]] == [
        one["title"] for one in moved["cards"]
    ]
    assert [one["meta"] for one in before["cards"]] == [
        one["meta"] for one in moved["cards"]
    ]
    assert [one["badge_style"] for one in before["cards"]] != [
        one["badge_style"] for one in moved["cards"]
    ]


def test_the_surface_does_not_follow_a_text_moved_in_the_shipped_pane(monkeypatch):
    """The surface read the pane's own words rather than writing them out."""
    import src.gui.market_inspector_topologies as shipped

    app()
    spec = BY_NAME["happy"]
    before = qt_trace(drive_old(spec), spec)
    monkeypatch.setattr(shipped, "_archetype_label", lambda archetype: MOVED_TEXT)
    monkeypatch.setattr(shipped, "AUTO_REFRESH_MS", 1)
    moved = qt_trace(drive_old(spec), spec)
    assert moved["timers"] == [[1, True, False]]
    assert before["timers"] != moved["timers"]
    new = surface_trace(drive_new(spec), spec)
    assert new["timers"] == before["timers"]
    assert surface.AUTO_REFRESH_MS != 1
    monkeypatch.undo()
    assert qt_trace(drive_old(spec), spec)["timers"] == before["timers"]


def test_the_surface_does_not_follow_a_pane_that_builds_nothing(monkeypatch):
    """The surface asked the shipped pane to build its screen."""
    import src.gui.market_inspector_topologies as shipped

    app()
    payload = fresh_payload()
    monkeypatch.setattr(shipped.MarketInspectorTopologies, "refresh", lambda self: None)
    with HeldClock(FIXED_NOW):
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(spec_source(BY_NAME["happy"]))
        pane.refresh()
        assert pane.current_proposals() == []
    again = surface.build_view_model(surface.TopologiesPaneModel(FIXED_NOW))
    assert again == payload
    assert again["pane"]["footer_text"] == surface.FOOTER_TEXT
    assert again["score"]["high_color"] == surface.SCORE_HIGH_COLOR
    monkeypatch.undo()
    assert drive_new(BY_NAME["happy"])["model"].current_proposals()


# ---------------------------------------------------------------------
# Order independence: what each side leaves behind
# ---------------------------------------------------------------------


def test_the_shipped_pane_writes_to_no_shared_table():
    """The shipped pane changed something every later test would inherit."""
    import src.gui.market_inspector_topologies as shipped

    app()
    before_module = sorted(vars(shipped))
    before_ttl = shipped.DISMISS_TTL_SECONDS
    before_interval = shipped.AUTO_REFRESH_MS
    before_time = shipped.time
    before_confirm = shipped.QMessageBox
    before_exec = shipped.TopologyPreviewDialog.exec
    drive_old(BY_NAME["happy"])
    drive_old(BY_NAME["a_proposal_was_dismissed_and_saved"])
    drive_old(BY_NAME["the_detector_refused"])
    assert sorted(vars(shipped)) == before_module
    assert shipped.DISMISS_TTL_SECONDS == before_ttl
    assert shipped.AUTO_REFRESH_MS == before_interval
    assert shipped.time is before_time
    assert shipped.QMessageBox is before_confirm
    assert shipped.TopologyPreviewDialog.exec is before_exec


def test_the_surface_writes_to_no_shared_table():
    """The surface changed a module value every later test would inherit."""
    before = sorted(vars(surface))
    before_actions = dict(surface.ACTIONS)
    before_timers = dict(surface.TIMERS)
    before_labels = dict(surface.ARCHETYPE_LABELS)
    before_errors = dict(surface.ERROR_TYPES)
    drive_new(BY_NAME["happy"])
    drive_new(BY_NAME["a_proposal_was_dismissed_and_saved"])
    drive_new(BY_NAME["the_detector_refused"])
    assert sorted(vars(surface)) == before
    assert surface.ACTIONS == before_actions
    assert surface.TIMERS == before_timers
    assert surface.ARCHETYPE_LABELS == before_labels
    assert surface.ERROR_TYPES == before_errors
    assert surface.BUS_TOPICS == ()


def test_the_shipped_pane_reaches_the_process_wide_logger():
    """The pane wrote its failure line somewhere nothing reads.

    The logger is process-wide and shared with every other pane in the
    run, which is why each side takes its own seat on it.
    """
    import src.gui.market_inspector_topologies as shipped

    app()
    named = logging.getLogger(surface.LOGGER_NAME)
    assert shipped.logger is named
    with HeldClock(FIXED_NOW), CapturedLog() as log:
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(Source(raises=RuntimeError(REFUSAL_TEXT)))
        assert log.lines == []
        pane.refresh()
    assert log.lines == [
        ["ERROR", surface.refresh_failed_line(RuntimeError(REFUSAL_TEXT))]
    ]
    assert REFUSAL_TEXT in log.lines[0][1]


def test_each_side_takes_its_own_seat_on_the_logger():
    """Both sides wrote into one recorder, so a lost line was hidden."""
    import src.gui.market_inspector_topologies as shipped

    app()
    spec = BY_NAME["the_detector_refused"]
    with HeldClock(FIXED_NOW), CapturedLog() as old_log:
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(spec_source(spec))
        pane.refresh()
        with CapturedLog() as new_log:
            model = surface.TopologiesPaneModel(FIXED_NOW)
            model.set_proposal_source(spec_source(spec))
            model.refresh()
    assert len(old_log.lines) == 1
    assert new_log.lines == []
    assert [list(one) for one in model.warnings] == old_log.lines


def test_a_log_seat_is_given_back_when_the_block_ends():
    """A recorder left on the logger would read every later test's lines."""
    named = logging.getLogger(surface.LOGGER_NAME)
    before = list(named.handlers)
    with CapturedLog() as log:
        assert log.handler in named.handlers
    assert log.handler not in named.handlers
    assert list(named.handlers) == before
    assert log.handler in SEATS_TAKEN


def test_no_earlier_seat_is_still_on_the_logger():
    """A seat from an earlier test is still reading this one's lines."""
    named = logging.getLogger(surface.LOGGER_NAME)
    with CapturedLog() as log:
        assert log.handler in named.handlers
    assert SEATS_TAKEN, "no seat was ever recorded, so this reports nothing"
    for handler in SEATS_TAKEN:
        assert handler not in named.handlers, handler


def test_the_held_clock_is_given_back_and_refuses_a_name_that_is_absent(monkeypatch):
    """The clock guard invented a name and held nothing."""
    import src.gui.market_inspector_topologies as shipped

    first = shipped.time
    with HeldClock(FIXED_NOW):
        assert shipped.time is not first
        assert shipped.time.time() == FIXED_NOW
    assert shipped.time is first
    monkeypatch.delattr(shipped, "time")
    with pytest.raises(AssertionError):
        with HeldClock(FIXED_NOW):
            pass
    monkeypatch.undo()
    assert shipped.time is first


def test_the_question_box_and_the_preview_screen_are_given_back():
    """A stand-in left in place would drive every later test in the run."""
    import src.gui.market_inspector_topologies as shipped

    app()
    first_box = shipped.QMessageBox
    first_exec = shipped.TopologyPreviewDialog.exec
    with StubbedConfirm(True):
        assert shipped.QMessageBox is Confirm
    assert shipped.QMessageBox is first_box
    declared = sorted(vars(shipped.TopologyPreviewDialog))
    with StubbedPreviewExec():
        assert shipped.TopologyPreviewDialog.exec is not first_exec
        assert "exec" in vars(shipped.TopologyPreviewDialog)
    assert shipped.TopologyPreviewDialog.exec is first_exec
    assert "exec" not in vars(shipped.TopologyPreviewDialog)
    assert sorted(vars(shipped.TopologyPreviewDialog)) == declared


def test_a_run_that_refuses_part_way_still_gives_the_stand_ins_back():
    """A recorder that stops on a failure keeps its seat for ever."""
    import src.gui.market_inspector_topologies as shipped

    app()
    first_box = shipped.QMessageBox
    first_time = shipped.time
    named = logging.getLogger(surface.LOGGER_NAME)
    before = list(named.handlers)
    with pytest.raises(RuntimeError):
        with HeldClock(FIXED_NOW), CapturedLog(), StubbedConfirm(True):
            raise RuntimeError("the run stopped part way")
    assert shipped.QMessageBox is first_box
    assert shipped.time is first_time
    assert list(named.handlers) == before


# ---------------------------------------------------------------------
# The colours and the words
# ---------------------------------------------------------------------


def canonical(colour):
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    return QColor(colour).name().lower()


def channels(colour):
    """The three channel pairs of one written colour."""
    written = canonical(colour)
    return [written[1:3], written[3:5], written[5:7]]


SCORE_COLOURS = [
    (100.0, "SCORE_HIGH_COLOR"),
    (80.0, "SCORE_HIGH_COLOR"),
    (79.9, "SCORE_MID_COLOR"),
    (50.0, "SCORE_MID_COLOR"),
    (49.9, "SCORE_LOW_COLOR"),
    (0.0, "SCORE_LOW_COLOR"),
    (-1.0, "SCORE_LOW_COLOR"),
    (math.inf, "SCORE_HIGH_COLOR"),
    (-math.inf, "SCORE_LOW_COLOR"),
    (math.nan, "SCORE_LOW_COLOR"),
]


@pytest.mark.parametrize("score,named", SCORE_COLOURS)
def test_the_score_ramp_picks_the_same_colour_on_both_sides(score, named):
    """The badge wears a different colour on one side of the ramp."""
    import src.gui.market_inspector_topologies as shipped

    wanted = getattr(surface, named)
    assert shipped._score_color(score) == wanted, score
    assert surface.score_color(score) == wanted, score


def test_the_low_colour_has_three_equal_channels_and_is_compared_as_text():
    """A channel swap in the low colour reads as no change at all.

    ``#888888`` carries one value in all three channels, so red, green
    and blue can be exchanged without the colour moving. The comparison
    is on the written text, and the digit count is part of that text: a
    rule that appends a transparency pair writes nine characters where
    the pane writes seven.
    """
    from PySide6.QtGui import QColor

    low = surface.SCORE_LOW_COLOR
    assert channels(low)[0] == channels(low)[1] == channels(low)[2]
    assert canonical(low) == canonical("#" + channels(low)[2] * 3)
    assert low == "#888888"
    assert len(low) == 7
    assert len(QColor(low).name(QColor.HexArgb)) == 9
    assert QColor(low).name(QColor.HexArgb) != low


def test_the_high_and_mid_colours_would_report_a_channel_swap():
    """Every colour in the ramp is grey, so no swap could ever show."""
    for constant in ("SCORE_HIGH_COLOR", "SCORE_MID_COLOR", "NEW_BOT_COLOR"):
        written = getattr(surface, constant)
        red, green, blue = channels(written)
        assert not red == green == blue, (constant, written)
        swapped = "#" + blue + green + red
        assert canonical(swapped) != canonical(written), constant


def test_the_three_ramp_colours_are_different_from_each_other():
    """Two steps of the ramp paint the same colour."""
    written = [
        surface.SCORE_HIGH_COLOR,
        surface.SCORE_MID_COLOR,
        surface.SCORE_LOW_COLOR,
    ]
    assert len(set(written)) == 3, written
    assert len({canonical(one) for one in written}) == 3


def test_the_new_bot_colour_is_the_one_the_shipped_pane_paints():
    """A bot the adoption would create is painted another colour."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    app()
    assert canonical(QColor(Qt.yellow)) == surface.NEW_BOT_COLOR
    assert len(surface.NEW_BOT_COLOR) == 7


@pytest.mark.parametrize(
    "score,written",
    [
        (0.0, "0"),
        (-1.0, "-1"),
        (88.0, "88"),
        (49.9, "50"),
        (1e9, "1000000000"),
        (1e-9, "0"),
        (math.inf, "inf"),
        (-math.inf, "-inf"),
        (math.nan, "nan"),
    ],
)
def test_the_badge_prints_the_score_the_same_way_on_both_sides(score, written):
    """The badge rounds a score differently on one side."""
    assert surface.whole(score) == written
    assert surface.CARD_BADGE_FORMAT.format(score=written) == " %s " % written


@pytest.mark.parametrize(
    "budget,written",
    [
        (0.0, "0"),
        (-1.0, "-1"),
        (1500.0, "1,500"),
        (1234.6, "1,235"),
        (1e9, "1,000,000,000"),
        (1e-9, "0"),
        (math.inf, "inf"),
        (-math.inf, "-inf"),
        (math.nan, "nan"),
    ],
)
def test_the_summary_prints_the_capital_the_same_way_on_both_sides(budget, written):
    """The target-capital line groups its thousands differently."""
    assert surface.grouped(budget) == written
    assert surface.summary_line(1, budget).endswith("${}</i>".format(written))


@pytest.mark.parametrize(
    "pct,written",
    [
        (0.0, "0.0"),
        (-1.0, "-1.0"),
        (25.0, "25.0"),
        (12.34, "12.3"),
        (1e9, "1000000000.0"),
        (1e-9, "0.0"),
        (math.inf, "inf"),
        (-math.inf, "-inf"),
        (math.nan, "nan"),
    ],
)
def test_the_wire_rate_prints_the_same_way_on_both_sides(pct, written):
    """The wire rate shows a different number of decimals."""
    assert surface.one_decimal(pct) == written
    assert surface.WIRE_PCT_FORMAT.format(pct=written) == written + "%"


ARCHETYPE_CASES = [
    ("momentum_funnel", "Momentum funnel"),
    ("mean_reversion_pair", "Mean-reversion pair"),
    ("sector_cluster", "Sector cluster"),
    ("distance_to_band", "Distance handoff"),
    ("a_shape_nobody_named", "a_shape_nobody_named"),
    ("MOMENTUM_FUNNEL", "MOMENTUM_FUNNEL"),
    ("", ""),
]


@pytest.mark.parametrize("archetype,written", ARCHETYPE_CASES)
def test_the_archetype_name_is_printed_the_same_way_on_both_sides(archetype, written):
    """An archetype prints under a different name on one side."""
    import src.gui.market_inspector_topologies as shipped

    assert shipped._archetype_label(archetype) == written
    assert surface.archetype_label(archetype) == written


def test_the_archetype_table_holds_the_same_four_names_on_both_sides():
    """The surface named an archetype the pane has never heard of."""
    import src.gui.market_inspector_topologies as shipped

    named = [
        one for one, _written in ARCHETYPE_CASES if one in surface.ARCHETYPE_LABELS
    ]
    assert sorted(surface.ARCHETYPE_LABELS) == sorted(named)
    assert len(surface.ARCHETYPE_LABELS) == 4
    for archetype in surface.ARCHETYPE_LABELS:
        assert (
            shipped._archetype_label(archetype) == surface.ARCHETYPE_LABELS[archetype]
        )


def test_the_bot_status_reads_the_same_on_both_sides():
    """A bot the adoption would create is described as already live."""
    assert surface.bot_status("b1", 0.0) == surface.BOT_STATUS_EXISTING
    assert surface.bot_status("", 1500.0) == "WILL CREATE ($1500)"
    assert surface.bot_status("", math.nan) == "WILL CREATE ($nan)"
    assert surface.bot_status("", 0) != surface.bot_status("b1", 0)


def test_the_status_lines_read_the_same_on_both_sides():
    """The pane counts its proposals or its dismissals differently."""
    assert surface.status_count(2, 0) == "2 proposal(s); 0 dismissed"
    assert surface.status_count(0, 0) != surface.status_count(1, 0)
    assert surface.status_count(1, 0) != surface.status_count(0, 1)
    assert surface.status_error(RuntimeError(REFUSAL_TEXT)).endswith(REFUSAL_TEXT)
    assert surface.status_error("a") != surface.status_error("b")


def test_the_log_lines_read_the_same_on_both_sides():
    """A log line named something other than the failure."""
    assert surface.refresh_failed_line(RuntimeError("boom")).endswith("boom")
    assert surface.refresh_failed_line(KeyError("symbol")).endswith("'symbol'")
    assert surface.refresh_failed_line(RuntimeError("boom")) != (
        surface.refresh_failed_line(RuntimeError("bang"))
    )
    assert surface.load_restored_line(1, 4).startswith("topology dismissals restored")
    assert surface.load_restored_line(1, 4) != surface.load_restored_line(4, 1)
    assert surface.load_not_a_dict_line("list") != surface.load_not_a_dict_line("int")
    assert surface.load_failed_line("a") != surface.persist_failed_line("a")


def test_an_invented_error_name_reaches_the_screen_under_its_own_name():
    """A failure the renderer reports arrived under another name."""
    built = surface.error_from("DetectorGone", "the scan never ran")
    assert type(built).__name__ == "DetectorGone"
    assert isinstance(built, Exception)
    assert str(built) == "the scan never ran"
    known = surface.error_from("ValueError", "bad reading")
    assert type(known) is ValueError
    assert surface.error_from("valueerror", "x").__class__ is not ValueError


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------


def card_class(accessible_name):
    """A frame whose class name is the one the pane's skin selects.

    The shipped skin selects by class name, so a frame of any other
    class would take none of the border, the radius or the padding.
    """
    from PySide6.QtWidgets import QFrame

    class _ProposalCard(QFrame):
        """One card, built only from the view model."""

        def __init__(self):
            super().__init__()
            self.setAccessibleName(accessible_name)

    return _ProposalCard


def card_painted_by_the_model(values, payload):
    """One card built only from the payload, never from the shipped pane."""
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
    )

    skin = payload["card"]
    card = card_class(skin["accessible_name"])()
    card.setFrameShape(getattr(QFrame, skin["frame_shape"]))
    card.setFrameShadow(getattr(QFrame, skin["frame_shadow"]))
    card.setStyleSheet(skin["style"])
    card.setSizePolicy(
        getattr(QSizePolicy, skin["size_policy"][0]),
        getattr(QSizePolicy, skin["size_policy"][1]),
    )
    root = QVBoxLayout(card)
    root.setContentsMargins(*skin["margins"])
    root.setSpacing(skin["spacing"])
    top = QHBoxLayout()
    title = QLabel(values["title"])
    title.setWordWrap(skin["title_word_wrap"])
    top.addWidget(title, 1)
    badge = QLabel(values["badge"])
    badge.setStyleSheet(values["badge_style"])
    top.addWidget(badge)
    root.addLayout(top)
    meta = QLabel(values["meta"])
    meta.setStyleSheet(skin["meta_style"])
    root.addWidget(meta)
    buttons = QHBoxLayout()
    buttons.addStretch()
    preview = QPushButton(skin["preview_text"])
    preview.setToolTip(skin["preview_tooltip"])
    buttons.addWidget(preview)
    dismiss = QPushButton(skin["dismiss_text"])
    dismiss.setToolTip(skin["dismiss_tooltip"])
    dismiss.setStyleSheet(skin["dismiss_style"])
    buttons.addWidget(dismiss)
    root.addLayout(buttons)
    return card


def pane_painted_by_the_model(payload):
    """The whole pane built only from the payload.

    A payload the caller changed after it came off the surface is
    refused.
    """
    from PySide6.QtWidgets import (
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    payload = unaltered(payload)
    app()
    skin = payload["pane"]
    pane = QWidget()
    layout = QVBoxLayout(pane)
    layout.setContentsMargins(*skin["margins"])
    layout.setSpacing(skin["spacing"])
    top = QHBoxLayout()
    button = QPushButton(skin["refresh_text"])
    button.setToolTip(skin["refresh_tooltip"])
    top.addWidget(button)
    top.addStretch()
    status = QLabel(payload["status_text"])
    status.setStyleSheet(skin["status_style"])
    top.addWidget(status)
    layout.addLayout(top)
    group = QGroupBox(skin["list_group_title"])
    inner = QVBoxLayout(group)
    scroll = QScrollArea()
    scroll.setWidgetResizable(skin["scroll_widget_resizable"])
    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(*skin["scroll_margins"])
    body_layout.setSpacing(skin["scroll_spacing"])
    cards = list(payload["cards"])
    for element in payload["screen"]:
        if element == skin["stretch_name"]:
            body_layout.addStretch()
        elif element == payload["card"]["class_name"]:
            body_layout.addWidget(card_painted_by_the_model(cards.pop(0), payload))
        else:
            empty = QLabel(skin["empty_text"])
            empty.setWordWrap(skin["empty_word_wrap"])
            empty.setStyleSheet(skin["empty_style"])
            body_layout.addWidget(empty)
    scroll.setWidget(body)
    inner.addWidget(scroll)
    layout.addWidget(group, 1)
    footer = QLabel(skin["footer_text"])
    footer.setStyleSheet(skin["footer_style"])
    layout.addWidget(footer)
    return pane


def tree_painted_by_the_model(box, columns, tooltip, rows, colors, skin):
    """One of the preview's two lists, built only from the payload."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem

    tree = QTreeWidget(box)
    tree.setColumnCount(skin["column_total"])
    tree.setHeaderLabels(list(columns))
    tree.setToolTip(tooltip)
    tree.setRootIsDecorated(skin["root_is_decorated"])
    tree.setAlternatingRowColors(skin["alternating_row_colors"])
    for index, row in enumerate(rows):
        item = QTreeWidgetItem(list(row))
        painted = colors[index] if index < len(colors) else []
        for column, colour in enumerate(painted):
            if colour is not None:
                item.setForeground(column, QColor(colour))
        tree.addTopLevelItem(item)
    tree.header().setSectionResizeMode(getattr(QHeaderView, skin["resize_mode"]))
    return tree


def preview_painted_by_the_model(payload, index=0):
    """One preview screen built only from the payload."""
    from PySide6.QtWidgets import (
        QDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    payload = unaltered(payload)
    app()
    skin = payload["dialog"]
    values = payload["previews"][index]
    screen = QDialog()
    screen.setWindowTitle(values["window_title"])
    screen.setMinimumSize(skin["min_width"], skin["min_height"])
    root = QVBoxLayout(screen)
    root.setContentsMargins(*skin["margins"])
    root.setSpacing(skin["spacing"])
    header = QHBoxLayout()
    title = QLabel(values["title"])
    title.setStyleSheet(skin["header_title_style"])
    header.addWidget(title)
    header.addStretch()
    badge = QLabel(values["badge"])
    badge.setStyleSheet(values["badge_style"])
    header.addWidget(badge)
    root.addLayout(header)
    body = QHBoxLayout()
    body.setSpacing(skin["body_spacing"])
    bots_box = QGroupBox(skin["bots_box_title"])
    QVBoxLayout(bots_box).addWidget(
        tree_painted_by_the_model(
            bots_box,
            skin["bots_columns"],
            skin["bots_tooltip"],
            values["bot_rows"],
            values["bot_colors"],
            skin,
        )
    )
    body.addWidget(bots_box, 1)
    wires_box = QGroupBox(skin["wires_box_title"])
    QVBoxLayout(wires_box).addWidget(
        tree_painted_by_the_model(
            wires_box,
            skin["wires_columns"],
            skin["wires_tooltip"],
            values["wire_rows"],
            [],
            skin,
        )
    )
    body.addWidget(wires_box, 1)
    root.addLayout(body, 1)
    summary = QLabel(values["summary"])
    summary.setStyleSheet(skin["summary_style"])
    root.addWidget(summary)
    for note in values["notes"]:
        line = QLabel(note)
        line.setWordWrap(skin["note_word_wrap"])
        line.setStyleSheet(skin["note_style"])
        root.addWidget(line)
    buttons = QHBoxLayout()
    buttons.addStretch()
    cancel = QPushButton(skin["cancel_text"])
    cancel.setDefault(skin["cancel_is_default"])
    buttons.addWidget(cancel)
    adopt = QPushButton(skin["adopt_text"])
    adopt.setEnabled(values["adopt_enabled"])
    adopt.setToolTip(values["adopt_tooltip"])
    buttons.addWidget(adopt)
    root.addLayout(buttons)
    return screen


def model_payload(spec):
    """The view model after the same driving, stamped."""
    return sealed(surface.build_view_model(drive_new(spec)["model"]))


def pane_painted_by_the_pane(spec):
    """The screen the shipped Qt pane builds, after the same driving."""
    return drive_old(spec)["pane"]


PICTURE_SCENARIOS = [
    "happy",
    "no_proposals",
    "the_pane_was_never_refreshed",
    "the_detector_refused",
    "title_is_empty",
    "title_is_unicode",
    "title_is_two_hundred_characters",
    "title_is_markup",
    "title_has_a_newline",
    "score_is_not_a_number",
    "score_is_a_thousand_million",
    "a_proposal_was_dismissed",
    "the_store_holds_a_live_dismissal",
]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_pane(name):
    """The surface painted a different pane than the shipped one."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(pane_painted_by_the_pane(BY_NAME[name]), PANE_SIZE),
        new_side=render_offscreen(
            pane_painted_by_the_model(model_payload(BY_NAME[name])), PANE_SIZE
        ),
        note=note,
    )


PREVIEW_PICTURE_SCENARIOS = [
    "a_proposal_was_previewed",
    "the_second_proposal_was_previewed",
]


@pytest.mark.parametrize("name", PREVIEW_PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_preview_screen(name):
    """The surface painted a different preview than the shipped pane."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    spec = BY_NAME[name]
    driven = drive_old(spec)
    assert_pictures_match(
        old_side=render_offscreen(driven["screens"][0], DIALOG_SIZE),
        new_side=render_offscreen(
            preview_painted_by_the_model(model_payload(spec)), DIALOG_SIZE
        ),
        note=note,
    )


PICTURE_DIFFERENT_PAIR = ("happy", "no_proposals")


def test_the_pane_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real inputs, one driven into each side: a screen holding two
    cards against a screen holding none. They end in different states
    whatever fonts the host holds.
    """
    app()
    first, second = PICTURE_DIFFERENT_PAIR
    assert old_outcome(BY_NAME[first])["value"]["cards"]
    assert not new_outcome(BY_NAME[second])["value"]["cards"]
    assert_pictures_differ(
        old_side=render_offscreen(pane_painted_by_the_pane(BY_NAME[first]), PANE_SIZE),
        new_side=render_offscreen(
            pane_painted_by_the_model(model_payload(BY_NAME[second])), PANE_SIZE
        ),
        note="two cards against an empty list",
    )


def test_the_pane_picture_comparison_reports_the_difference_the_other_way():
    """The comparison reports only when the shipped side is the first one."""
    app()
    first, second = PICTURE_DIFFERENT_PAIR
    assert_pictures_differ(
        old_side=render_offscreen(
            pane_painted_by_the_model(model_payload(BY_NAME[first])), PANE_SIZE
        ),
        new_side=render_offscreen(pane_painted_by_the_pane(BY_NAME[second]), PANE_SIZE),
        note="two cards against an empty list, the other way round",
    )


def test_the_preview_picture_comparison_can_report_a_difference():
    """The preview picture check passes whatever the second side paints."""
    app()
    first, second = PREVIEW_PICTURE_SCENARIOS
    driven = drive_old(BY_NAME[first])
    assert_pictures_differ(
        old_side=render_offscreen(driven["screens"][0], DIALOG_SIZE),
        new_side=render_offscreen(
            preview_painted_by_the_model(model_payload(BY_NAME[second])), DIALOG_SIZE
        ),
        note="one proposal's preview against the other's",
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_pane_shows_more_than_one_colour(name):
    """The two sides matched because the pane painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    for image in (
        render_offscreen(pane_painted_by_the_pane(BY_NAME[name]), PANE_SIZE),
        render_offscreen(
            pane_painted_by_the_model(model_payload(BY_NAME[name])), PANE_SIZE
        ),
    ):
        assert image.width() > 0 and image.height() > 0, name
        seen = set()
        for x in range(0, image.width(), 5):
            for y in range(0, image.height(), 5):
                seen.add(QColor(image.pixelColor(x, y)).name())
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"


def test_a_pane_with_no_skin_paints_a_different_picture():
    """The skin reaches no pixel, so a lost style would never show.

    The rule turned off is one neither side sets: the shipped pane and
    the surface both leave the group box's own border alone.
    """
    app()
    payload = model_payload(BY_NAME["happy"])
    with_skin = pane_painted_by_the_model(payload)
    without_skin = pane_painted_by_the_model(payload)
    without_skin.setStyleSheet("QGroupBox { border: none; }")
    assert_pictures_differ(
        old_side=render_offscreen(with_skin, PANE_SIZE),
        new_side=render_offscreen(without_skin, PANE_SIZE),
        note="the same payload with the group box border turned off",
    )
    assert "QGroupBox" not in payload["card"]["style"]
    assert "border" not in payload["pane"]["status_style"]


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload(BY_NAME["happy"])
    payload["status_text"] = MOVED_TEXT
    with pytest.raises(AssertionError) as reported:
        pane_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        pane_painted_by_the_model(fresh_payload())
    with pytest.raises(AssertionError):
        preview_painted_by_the_model(fresh_payload())


def test_the_card_skin_selects_the_class_the_test_builds():
    """A card of another class takes none of the pane's skin."""
    app()
    from PySide6.QtWidgets import QFrame

    built = card_class(surface.CARD_ACCESSIBLE_NAME)
    assert built.__name__ == surface.CARD_CLASS
    assert issubclass(built, QFrame)
    assert built().accessibleName() == surface.CARD_ACCESSIBLE_NAME
    assert surface.CARD_STYLE.startswith(surface.CARD_CLASS + " {")


# ---------------------------------------------------------------------
# The host's fonts
# ---------------------------------------------------------------------


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on.

    With no font database every family resolves to a box advancing one
    em per character, so two strings of equal length need equal width.
    With a font database the glyphs decide the width. Both answers are
    handled here and the file is run both ways.
    """
    app()
    assert len(NARROW_LABEL) == len(WIDE_LABEL)
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert narrow != wide, "the host reports fonts and every glyph has one width"
    else:
        assert narrow == wide, "the host reports no fonts and the glyphs differ"


@skip_unless_no_fonts
def test_two_equal_length_card_titles_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length lines still differ."""
    app()
    assert app_font_advance_px("Momentum funnel") == app_font_advance_px(
        "Sector clusterr"
    )


@skip_unless_real_fonts
def test_the_two_marker_strings_measure_apart_with_fonts():
    """The glyphs decide their own width, and the marker pair measures alike."""
    app()
    assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)


# ---------------------------------------------------------------------
# What a picture cannot see, read off both sides instead
# ---------------------------------------------------------------------


def test_the_tooltips_are_read_off_both_sides():
    """A tooltip reaches no pixel and was left to the render to report."""
    spec = BY_NAME["a_proposal_was_previewed"]
    old = qt_trace(drive_old(spec), spec)
    new = surface_trace(drive_new(spec), spec)
    assert old["refresh_tooltip"] == new["refresh_tooltip"] == surface.REFRESH_TOOLTIP
    assert old["previews"][0]["bots"]["tooltip"] == surface.BOTS_TOOLTIP
    assert old["previews"][0]["wires"]["tooltip"] == surface.WIRES_TOOLTIP
    assert (
        new["previews"][0]["bots"]["tooltip"] == old["previews"][0]["bots"]["tooltip"]
    )
    assert new["previews"][0]["adopt_tooltip"] == old["previews"][0]["adopt_tooltip"]
    assert surface.BOTS_TOOLTIP != surface.WIRES_TOOLTIP


def test_a_lost_cell_is_told_apart_from_a_cell_with_no_colour():
    """A cell that does not exist reads the same as one left unpainted.

    Both answer empty text and no paint record, so the colour reading
    folds them together. The row's own cell count is what separates
    them, and both are carried in the reading the two sides compare.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QTreeWidgetItem

    app()
    full = QTreeWidgetItem(["a", "b", "c", "d"])
    short = QTreeWidgetItem(["a"])
    assert full.text(3) == "d"
    assert short.text(3) == ""
    assert full.data(3, Qt.ForegroundRole) is None
    assert short.data(3, Qt.ForegroundRole) is None
    assert row_colors(full, 4) == row_colors(short, 4) == [None] * 4
    assert short.columnCount() < full.columnCount()
    assert row_cells(short, 4) == ["a", "", "", ""]
    full.setForeground(0, QColor(surface.NEW_BOT_COLOR))
    assert full.data(0, Qt.ForegroundRole) is not None
    assert row_colors(full, 4) == [surface.NEW_BOT_COLOR, None, None, None]
    assert row_colors(full, 4) != row_colors(short, 4)


def test_the_new_bot_row_is_painted_and_the_existing_one_is_not():
    """A row the adoption would create is painted like an existing one."""
    spec = BY_NAME["a_proposal_was_previewed"]
    old = qt_trace(drive_old(spec), spec)
    new = surface_trace(drive_new(spec), spec)
    bots = old["previews"][0]["bots"]
    assert bots["colors"][0] == [None] * 4
    assert bots["colors"][1] == [surface.NEW_BOT_COLOR] * 4
    assert new["previews"][0]["bots"]["colors"] == bots["colors"]
    assert bots["cells_per_row"] == [4, 4]
    assert new["previews"][0]["bots"]["cells_per_row"] == bots["cells_per_row"]


def test_the_margins_and_spacing_are_read_off_both_sides():
    """One side sets a margin the other leaves alone."""
    spec = BY_NAME["happy"]
    old = qt_trace(drive_old(spec), spec)
    new = surface_trace(drive_new(spec), spec)
    assert old["margins"] == new["margins"] == list(surface.PANE_MARGINS)
    assert old["spacing"] == new["spacing"] == surface.PANE_SPACING
    assert (
        old["scroll_margins"] == new["scroll_margins"] == list(surface.SCROLL_MARGINS)
    )
    assert old["scroll_spacing"] == new["scroll_spacing"] == surface.SCROLL_SPACING


def test_the_layout_reader_reports_a_margin_that_moved():
    """The margin reader returns one answer whatever the layout holds."""
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    app()
    holder = QWidget()
    moved = QVBoxLayout(holder)
    moved.setContentsMargins(3, 5, 7, 11)
    moved.setSpacing(29)
    assert holder.layout() is moved
    assert box_of(moved) == [3, 5, 7, 11]
    assert moved.spacing() == 29
    assert box_of(moved) != list(surface.PANE_MARGINS)


def test_the_timer_is_read_off_both_sides():
    """The auto-refresh timer runs at a different rate, or not at all."""
    spec = BY_NAME["happy"]
    old = qt_trace(drive_old(spec), spec)
    new = surface_trace(drive_new(spec), spec)
    assert old["timers"] == new["timers"]
    assert old["timers"] == [[surface.AUTO_REFRESH_MS, True, False]]
    assert surface.AUTO_REFRESH_MS == 10 * 60 * 1000


def test_the_preview_minimum_size_is_read_off_both_sides():
    """The preview screen opens at a different smallest size."""
    spec = BY_NAME["a_proposal_was_previewed"]
    old = qt_trace(drive_old(spec), spec)
    new = surface_trace(drive_new(spec), spec)
    assert old["previews"][0]["minimum_size"] == new["previews"][0]["minimum_size"]
    assert old["previews"][0]["minimum_size"] == [
        surface.DIALOG_MIN_WIDTH,
        surface.DIALOG_MIN_HEIGHT,
    ]


# ---------------------------------------------------------------------
# The card the pane stopped showing but did not let go of
# ---------------------------------------------------------------------


def cards_parented_to(pane):
    """Every card still owned by the pane's scroll body."""
    group = widget_at(pane.layout(), 1)
    body = widget_at(group.layout(), 0).widget()
    return [
        child for child in body.children() if type(child).__name__ == surface.CARD_CLASS
    ]


def test_a_dropped_card_stays_owned_until_the_loop_turns():
    """The pane lets a dropped card go at once, so the flush proves nothing.

    ``_clear_cards`` takes each card out of the layout and asks for it
    to be deleted later. Until the loop turns, the card is still owned
    by the scroll body and still paints. Both counts are measured here,
    so the flush in the driver is a step with something to do.
    """
    import src.gui.market_inspector_topologies as shipped

    app()
    spec = BY_NAME["happy"]
    with HeldClock(FIXED_NOW), StubbedConfirm(True):
        pane = shipped.MarketInspectorTopologies()
        pane.set_proposal_source(spec_source(spec))
        pane.refresh()
        assert len(cards_parented_to(pane)) == 2
        pane._on_dismiss("p1")
        held = len(cards_parented_to(pane))
    assert order_of(
        widget_at(widget_at(pane.layout(), 1).layout(), 0).widget().layout()
    ) == [surface.CARD_CLASS, surface.STRETCH]
    assert held > 1, held
    flush_deleted()
    assert len(cards_parented_to(pane)) == 1


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


@pytest.fixture
def fresh_pane_model():
    """Put the pane state the bridge keeps back exactly as it was found.

    Nothing is handed to the test: the bridge builds the pane on its
    first request, and that is the behaviour under test.
    """
    first = surface.PANE_MODEL
    surface.PANE_MODEL = None
    yield
    surface.PANE_MODEL = first


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


BRIDGE_PROPOSALS = [
    {
        "id": "p1",
        "title": "BTC funnel",
        "archetype": "momentum_funnel",
        "score": 88.0,
        "assets": ["BTC", "ETH"],
        "bots": [
            {"asset": "ETH", "existing_bot_id": "", "suggested_target_usd": 1500.0}
        ],
        "wires": [{"source_asset": "BTC", "target_asset": "ETH", "pct": 25.0}],
        "adopt_notes": ["note one"],
    }
]

BRIDGE_REFRESH = {
    "reset": True,
    "now": FIXED_NOW,
    "proposals": BRIDGE_PROPOSALS,
    "refresh": True,
}


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_registers_the_topology_method():
    """The renderer cannot reach the topology pane over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "market_inspector_topologies.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["pane"]["footer_text"] == surface.FOOTER_TEXT
    assert result["score"]["high_color"] == surface.SCORE_HIGH_COLOR
    assert result["dismissal"]["ttl_seconds"] == surface.DISMISS_TTL_SECONDS


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_builds_the_pane_on_the_first_request_and_not_at_import():
    """The bridge answered from a pane nothing ever built."""
    assert surface.PANE_MODEL is None
    result = bridge_answer({})["result"]
    assert surface.PANE_MODEL is not None
    assert result["status_text"] == surface.STATUS_UNWIRED
    assert result["screen"] == [surface.STRETCH]
    assert result["calls"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_resets_the_pane_state_on_request():
    """The pane state the bridge keeps was never cleared."""
    filled = bridge_answer(BRIDGE_REFRESH)["result"]
    assert filled["proposals"] == ["p1"]
    assert filled["screen"] == [surface.CARD_CLASS, surface.STRETCH]
    assert filled["status_text"] == surface.status_count(1, 0)
    kept = bridge_answer({})["result"]
    assert kept["proposals"] == filled["proposals"]
    assert kept["screen"] == filled["screen"]
    cleared = bridge_answer({"reset": True, "now": FIXED_NOW})["result"]
    assert cleared["proposals"] == []
    assert cleared["screen"] == [surface.STRETCH]
    assert cleared["status_text"] == surface.STATUS_UNWIRED
    assert cleared["calls"] == []
    assert cleared["warnings"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_reports_a_detector_that_refused():
    """A detector failure was reported as an empty list of proposals."""
    result = bridge_answer(
        {
            "reset": True,
            "now": FIXED_NOW,
            "error": {"type": "RuntimeError", "text": REFUSAL_TEXT},
            "refresh": True,
        }
    )["result"]
    assert result["status_text"] == "Detector error: " + REFUSAL_TEXT
    assert result["warnings"] == [
        ["ERROR", "topology proposals refresh failed: " + REFUSAL_TEXT]
    ]
    assert result["proposals"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_previews_adopts_and_dismisses():
    """A card's three actions cannot be reached over the bridge."""
    bridge_answer(BRIDGE_REFRESH)
    previewed = bridge_answer({"preview": "p1", "adopt": True})["result"]
    assert len(previewed["previews"]) == 1
    assert previewed["previews"][0]["window_title"] == "Preview: BTC funnel"
    assert previewed["adopt_requests"] == ["p1"]
    dismissed = bridge_answer({"dismiss": "p1", "store": {}})["result"]
    assert dismissed["proposals"] == []
    assert dismissed["confirm"]["asked"][0][0] == surface.CONFIRM_TITLE
    assert dismissed["persisted"][-1][0] == surface.DISMISS_SETTINGS_KEY
    refused = bridge_answer(
        {
            "reset": True,
            "now": FIXED_NOW,
            "proposals": BRIDGE_PROPOSALS,
            "refresh": True,
        }
    )
    assert refused["result"]["proposals"] == ["p1"]
    held = bridge_answer({"confirm": surface.CONFIRM_DEFAULT_BUTTON, "dismiss": "p1"})
    assert held["result"]["proposals"] == ["p1"]


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    bridge_answer(BRIDGE_REFRESH)
    answer = bridge_answer({"preview": "p1", "adopt": True, "store": {}})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["screen"] == [surface.CARD_CLASS, surface.STRETCH]
    assert encoded["result"]["previews"][0]["bot_colors"] == [
        [surface.NEW_BOT_COLOR] * surface.TREE_COLUMN_TOTAL
    ]


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_reports_a_request_it_cannot_use():
    """A bad request ended the session instead of answering with an error."""
    answer = bridge_answer({"reset": True, "error": "not a mapping"})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "AttributeError"
    assert answer["error"]["message"]


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_takes_the_clock_as_a_value():
    """The bridge read the wall clock instead of the second it was given."""
    bridge_answer(BRIDGE_REFRESH)
    dismissed = bridge_answer({"dismiss": "p1", "store": {}})["result"]
    held = dismissed["dismissal"]["held"]
    assert held == {"p1": FIXED_NOW + surface.DISMISS_TTL_SECONDS}
    assert dismissed["now"] == FIXED_NOW
    later = bridge_answer({"reset": True, "now": LATER_NOW})["result"]
    assert later["now"] == LATER_NOW
    assert later["dismissal"]["held"] == {}


def test_the_import_list_on_the_bridge_is_alphabetical():
    """A surface was inserted out of order and the next one will follow it."""
    bridge_source = REPO_ROOT / "src" / "core" / "desktop_bridge.py"
    tree = parsed(bridge_source)
    named = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs":
            named = [alias.name for alias in node.names]
    assert named, "the bridge no longer imports the main-tab surfaces"
    assert named == sorted(named), named
    assert "market_inspector_topologies_surface" in named
    assert named.index("market_inspector_tab_surface") < named.index(
        "market_inspector_topologies_surface"
    )


# ---------------------------------------------------------------------
# The surface answers without Qt, and builds nothing while it is imported
# ---------------------------------------------------------------------


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'market_inspector_topologies.state',"
    " 'params': {'reset': True, 'now': 1700000000.0, 'refresh': True,"
    " 'proposals': [{'id': 'p1', 'title': 'BTC funnel', 'score': 88.0}]}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def run_probe(prelude, environment=None):
    """Run one probe in a fresh process and read its last line as JSON."""
    settings = dict(os.environ)
    settings.update(environment or {})
    done = subprocess.run(
        [sys.executable, "-"],
        input=(prelude + QT_PROBE).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=settings,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return json.loads(done.stdout.decode(errors="replace").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the topology pane pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["screen"] == ["_ProposalCard", "stretch"]
    assert result["status_text"] == "1 proposal(s); 0 dismissed"
    assert result["cards"][0]["title"] == "<b>▸ BTC funnel</b>"
    assert result["cards"][0]["badge"] == " 88 "
    assert result["pane"]["footer_text"] == (
        "Auto-refresh: every 10 min  ·  Adopt: live (Bot Wizard handoff)"
    )
    assert result["timer_delays_ms"] == [600000]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


IMPORT_PROBE = """
import json, os, sys
from pathlib import Path

first_root = os.environ['FIRST_ROOT']
second_root = os.environ['SECOND_ROOT']


def entries(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob('*'))


os.environ['ACERVATOR_SETTINGS_ROOT'] = first_root
from src.core.privacy_mask_registry import PrivacyMaskRegistry
from src.gui.main_tabs import market_inspector_topologies_surface as surface

at_import = {
    'model_built': surface.PANE_MODEL is not None,
    'root': str(PrivacyMaskRegistry(autosave=False).settings_path),
    'first_entries': entries(first_root),
    'second_entries': entries(second_root),
}
os.environ['ACERVATOR_SETTINGS_ROOT'] = second_root
answer = surface.view_model({'reset': True, 'now': 1700000000.0})
at_request = {
    'model_built': surface.PANE_MODEL is not None,
    'root': str(PrivacyMaskRegistry(autosave=False).settings_path),
    'first_entries': entries(first_root),
    'second_entries': entries(second_root),
    'status': answer['status_text'],
    'qt': 'PySide6' in sys.modules,
}
print(json.dumps({'at_import': at_import, 'at_request': at_request}))
"""


def test_nothing_runs_at_import_and_the_first_request_uses_the_later_root(tmp_path):
    """The surface read the world while it was being imported.

    One settings root is in force while the module is imported and a
    different one before the first request. A module that resolved a
    path at import would have taken the first. The pane is built on the
    first request, and neither folder gains a file.
    """
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    settings = dict(os.environ)
    settings.update({"FIRST_ROOT": str(first_root), "SECOND_ROOT": str(second_root)})
    done = subprocess.run(
        [sys.executable, "-"],
        input=IMPORT_PROBE.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=settings,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    read = json.loads(done.stdout.decode(errors="replace").splitlines()[-1])
    assert read["at_import"]["model_built"] is False
    assert read["at_request"]["model_built"] is True
    assert read["at_import"]["root"].startswith(str(first_root))
    assert read["at_request"]["root"].startswith(str(second_root))
    assert read["at_import"]["root"] != read["at_request"]["root"]
    assert read["at_import"]["first_entries"] == []
    assert read["at_import"]["second_entries"] == []
    assert read["at_request"]["first_entries"] == []
    assert read["at_request"]["second_entries"] == []
    assert read["at_request"]["status"] == surface.STATUS_UNWIRED
    assert read["at_request"]["qt"] is False


# ---------------------------------------------------------------------
# Nothing is written outside the run, and nothing leaves the machine
# ---------------------------------------------------------------------


def files_under(root) -> list:
    """Every file below `root`, as paths relative to it."""
    return sorted(
        str(path.relative_to(root)) for path in Path(root).rglob("*") if path.is_file()
    )


def test_driving_both_sides_writes_no_file_into_a_throwaway_home(tmp_path):
    """A drive of either side wrote into the operator's own tree.

    The counter is proved on the same folder: it reports nothing before,
    and reports the one file when a file is really written.
    """
    home = tmp_path / "home"
    home.mkdir()
    assert files_under(home) == []
    for name in (
        "happy",
        "a_proposal_was_dismissed_and_saved",
        "the_store_could_not_be_read",
        "a_proposal_was_previewed_and_adopted",
    ):
        drive_old(BY_NAME[name])
        drive_new(BY_NAME[name])
    assert files_under(home) == []
    (home / ".acervator").mkdir()
    (home / ".acervator" / "settings.json").write_text("{}", encoding="utf-8")
    written = files_under(home)
    assert len(written) == 1, written
    assert written[0].endswith("settings.json")


class NoNetwork:
    """Refuse and count every attempt to reach outside this machine."""

    def __init__(self):
        self.attempts = []
        self.first_lookup = None
        self.first_connect = None

    def __enter__(self):
        self.first_lookup = socket.getaddrinfo
        self.first_connect = socket.socket.connect
        attempts = self.attempts

        def refuse_lookup(host, port, *_rest, **_named):
            attempts.append(["lookup", host, port])
            raise AssertionError(f"this run may not look up {host!r}")

        def refuse_connect(_self_socket, address, *_rest):
            attempts.append(["connect", address])
            raise AssertionError(f"this run may not connect to {address!r}")

        socket.getaddrinfo = refuse_lookup
        socket.socket.connect = refuse_connect
        return self

    def __exit__(self, _kind, _value, _trace):
        socket.getaddrinfo = self.first_lookup
        socket.socket.connect = self.first_connect
        return False


OUTSIDE_ADDRESSES = [("example.com", 80), ("1.1.1.1", 443)]


def test_driving_both_sides_makes_no_attempt_to_leave_the_machine():
    """A drive of either side reached a name server or a venue."""
    with NoNetwork() as guard:
        for name in (
            "happy",
            "a_proposal_was_dismissed_and_saved",
            "the_detector_refused",
            "a_proposal_was_previewed_and_adopted",
        ):
            drive_old(BY_NAME[name])
            drive_new(BY_NAME[name])
        assert guard.attempts == [], guard.attempts


def test_the_network_counter_reports_two_real_outside_addresses():
    """The counter stays quiet whatever a run reaches for.

    Two addresses outside this machine are offered to it. Both are
    refused before a packet is sent, and both are counted.
    """
    with NoNetwork() as guard:
        for address in OUTSIDE_ADDRESSES:
            with pytest.raises(AssertionError):
                socket.create_connection(address, timeout=1)
        assert len(guard.attempts) == len(OUTSIDE_ADDRESSES), guard.attempts
        assert [one[1] for one in guard.attempts] == [
            address[0] for address in OUTSIDE_ADDRESSES
        ]
    assert socket.getaddrinfo is guard.first_lookup
    assert socket.socket.connect is guard.first_connect


NETWORK_PACKAGES = frozenset(
    {
        "aiohttp",
        "ccxt",
        "http",
        "httpx",
        "requests",
        "socket",
        "ssl",
        "urllib",
        "urllib3",
        "websocket",
        "websockets",
    }
)

SURFACE_SOURCE = (
    REPO_ROOT / "src" / "gui" / "main_tabs" / "market_inspector_topologies_surface.py"
)


def test_neither_side_imports_a_package_that_can_leave_the_machine():
    """A side that imports a network package could reach outside.

    The reader is proved on this file, which imports one of them.
    """
    for path in (PANE_SOURCE, SURFACE_SOURCE):
        reachable = imported_names(parsed(path)) & NETWORK_PACKAGES
        assert reachable == set(), (path.name, sorted(reachable))
    mine = imported_names(parsed(Path(__file__))) & NETWORK_PACKAGES
    assert mine == {"socket"}, sorted(mine)
