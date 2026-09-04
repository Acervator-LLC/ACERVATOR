"""The Qt Quick Routing matrix and the Qt-free surface, driven side by side.

A failure means the view model describes a different row, label, tick,
scroll position, question, refusal, saved wire, bus event or stopping
point than ``QuickRoutingMatrix`` produces on the same input.

No test here opens a real socket, writes into the operator's tree or
reads the wall clock. The matrix is driven with a stand-in for every
outward edge it has: the two columns, the rate box, the visualizer tab,
the stored settings, the message boxes and the event bus.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import quick_routing_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_SOURCE = REPO_ROOT / "src" / "gui" / "visualizer" / "quick_routing.py"
SURFACE_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "quick_routing_surface.py"
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
QUIET_TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
PAINT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
DECORATED_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "indicator_panel.py"
NESTED_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "stock_main_window.py"

MATRIX_SIZE = (600, 220)


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def canonical(value):
    """`value` as nested lists of text, so two not-a-numbers compare equal.

    A rate can be not-a-number, and Python holds that such a value is
    unequal to itself. Reading every number as its own text lets the two
    sides be compared while keeping a whole number apart from a decimal
    one.
    """
    if isinstance(value, dict):
        return [[repr(key), canonical(inner)] for key, inner in sorted(value.items())]
    if isinstance(value, (list, tuple)):
        return [canonical(inner) for inner in value]
    return repr(value)


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(canonical(value), sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


# The inputs

LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "30 交易 ₿"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "the operator's share"

ALPHA = "alpha-0001"
BETA = "beta-0002"
GAMMA = "gamma-0003"
THREE_BOTS = [ALPHA, BETA, GAMMA]

SYMBOLS = {ALPHA: "BTC/USD", BETA: "ETH/USD"}
STORED = {GAMMA: "SOL/USD"}


def tab_spec(**named):
    """One set of the answers the matrix reads off the visualizer tab."""
    spec = {
        "widget_symbols": dict(SYMBOLS),
        "state_symbols": dict(STORED),
        "cleared_pairs": [[ALPHA, BETA], [BETA, GAMMA]],
    }
    spec.update(named)
    return spec


TAB_SPECS = {
    "happy_three_bots": tab_spec(),
    "no_symbols_anywhere": tab_spec(widget_symbols={}, state_symbols={}),
    "a_card_with_an_empty_symbol": tab_spec(widget_symbols={ALPHA: ""}),
    "a_card_the_settings_also_know": tab_spec(state_symbols={ALPHA: "XRP/USD"}),
    "the_settings_cannot_be_read": tab_spec(state_refusal="settings unreadable"),
    "the_cards_cannot_be_read": tab_spec(widget_refusal="cards unreadable"),
    "unicode_symbol": tab_spec(widget_symbols={ALPHA: UNICODE_TEXT}),
    "two_hundred_character_symbol": tab_spec(widget_symbols={ALPHA: LONG_TEXT}),
    "markup_symbol": tab_spec(widget_symbols={ALPHA: MARKUP_TEXT}),
    "an_apostrophe_symbol": tab_spec(widget_symbols={ALPHA: APOSTROPHE_TEXT}),
    "a_newline_symbol": tab_spec(widget_symbols={ALPHA: NEWLINE_TEXT}),
    "wrong_capitals_symbol": tab_spec(widget_symbols={ALPHA: "bTc/uSd"}),
    "a_number_where_a_symbol_belongs": tab_spec(widget_symbols={ALPHA: 42}),
    "an_infinite_symbol": tab_spec(widget_symbols={ALPHA: math.inf}),
    "a_not_a_number_symbol": tab_spec(widget_symbols={ALPHA: math.nan}),
    "hidden_names": tab_spec(masked=True),
    "empty_everywhere": {},
    "the_operator_says_no": tab_spec(default_answer=False),
    "the_question_cannot_be_put": tab_spec(ask_refusal="no screen"),
    "the_refusal_cannot_be_shown": tab_spec(warn_refusal="no screen"),
    "saving_fails": tab_spec(apply_refusal="the disk refused"),
    "the_redraw_fails": tab_spec(bus_refusal="the bus is down"),
    "clearing_fails": tab_spec(clear_refusal="nothing to clear"),
    "nothing_was_cleared": tab_spec(cleared_pairs=[]),
}

RATE_TEXTS = {
    "a_plain_rate": "25",
    "a_rate_with_a_sign": " 25 % ",
    "empty": "",
    "zero": "0",
    "negative": "-5",
    "a_thousand_million": "1000000000",
    "one_billionth": "0.000000001",
    "the_upper_edge": "100",
    "just_over_the_upper_edge": "100.0000000000001",
    "unicode": UNICODE_TEXT,
    "two_hundred_characters": LONG_TEXT,
    "markup": MARKUP_TEXT,
    "an_apostrophe": APOSTROPHE_TEXT,
    "wrong_capitals": "TwentyFive",
    "a_newline": NEWLINE_TEXT,
    "text_where_a_number_belongs": "fifty",
    "a_number_where_text_belongs": 25,
    "nothing_at_all": None,
    "infinity": "inf",
    "minus_infinity": "-inf",
    "not_a_number": "nan",
}

CONNECT = surface.CONNECT_STEP
DISCONNECT = surface.DISCONNECT_STEP
DISCONNECT_ALL = surface.DISCONNECT_ALL_STEP
REBUILD = surface.REBUILD_STEP

STEP_SPECS = {
    "just_a_rebuild": [[REBUILD, THREE_BOTS]],
    "rebuild_then_connect": [[REBUILD, THREE_BOTS], CONNECT],
    "rebuild_then_disconnect": [[REBUILD, THREE_BOTS], DISCONNECT],
    "rebuild_then_disconnect_all": [[REBUILD, THREE_BOTS], DISCONNECT_ALL],
    "connect_with_no_rebuild": [CONNECT],
    "disconnect_with_no_rebuild": [DISCONNECT],
    "rebuild_over_an_empty_scope": [[REBUILD, []]],
    "two_rebuilds": [[REBUILD, THREE_BOTS], [REBUILD, [ALPHA, BETA]]],
    "connect_then_disconnect": [[REBUILD, THREE_BOTS], CONNECT, DISCONNECT],
    "every_button_in_turn": [
        [REBUILD, THREE_BOTS],
        CONNECT,
        DISCONNECT,
        DISCONNECT_ALL,
    ],
    "connect_twice": [[REBUILD, THREE_BOTS], CONNECT, CONNECT],
    "rebuild_between_two_connects": [
        [REBUILD, THREE_BOTS],
        CONNECT,
        [REBUILD, [ALPHA, BETA]],
        CONNECT,
    ],
}

TICK_SPECS = {
    "one_each_way": ([ALPHA], [BETA]),
    "nothing_ticked": ([], []),
    "sources_only": ([ALPHA], []),
    "destinations_only": ([], [BETA]),
    "the_same_bot_both_ways": ([ALPHA], [ALPHA]),
    "every_bot_both_ways": (THREE_BOTS, THREE_BOTS),
    "two_sources_one_destination": ([ALPHA, BETA], [GAMMA]),
    "a_bot_that_is_not_in_view": (["nowhere"], [BETA]),
}

SCROLL_SPECS = {
    "not_scrolled": (0, 0),
    "the_source_column_scrolled": (35, 0),
    "the_destination_column_scrolled": (0, 12),
    "both_columns_scrolled": (35, 12),
    "a_negative_offset": (-4, 0),
}


def spec(
    tab="happy_three_bots",
    rate="a_plain_rate",
    steps="rebuild_then_connect",
    ticks="one_each_way",
    scroll="not_scrolled",
):
    """One whole input: the tab, the rate box, the ticks and the clicks."""
    return {
        "tab": TAB_SPECS[tab],
        "rate": RATE_TEXTS[rate],
        "steps": STEP_SPECS[steps],
        "ticks": TICK_SPECS[ticks],
        "scroll": SCROLL_SPECS[scroll],
    }


SPECS = {}
for _name in TAB_SPECS:
    SPECS["tab_" + _name] = spec(tab=_name)
for _name in RATE_TEXTS:
    SPECS["rate_" + _name] = spec(rate=_name)
for _name in STEP_SPECS:
    SPECS["steps_" + _name] = spec(steps=_name)
for _name in TICK_SPECS:
    SPECS["ticks_" + _name] = spec(ticks=_name)
for _name in SCROLL_SPECS:
    SPECS["scroll_" + _name] = spec(scroll=_name)
SPECS["a_hidden_swarm_disconnecting_everything"] = spec(
    tab="hidden_names", steps="rebuild_then_disconnect_all", ticks="every_bot_both_ways"
)
SPECS["a_refused_save_over_every_pair"] = spec(
    tab="saving_fails", steps="rebuild_then_connect", ticks="every_bot_both_ways"
)
SPECS["a_scrolled_rebuild_between_two_connects"] = spec(
    steps="rebuild_between_two_connects", scroll="both_columns_scrolled"
)
SPECS["a_clear_that_fails"] = spec(
    tab="clearing_fails", steps="rebuild_then_disconnect_all"
)
SPECS["a_clear_that_removed_nothing"] = spec(
    tab="nothing_was_cleared", steps="rebuild_then_disconnect_all"
)
SPECS["asking_live"] = spec(ticks="every_bot_both_ways")


# The shipped side, driven through a stand-in for every outward edge


class ScrollStandIn:
    """The scroll bar of one column, holding its position as a number.

    A real list under the offscreen driver keeps its scroll range at
    zero whatever it holds, so the position the matrix saves and puts
    back could never be anything but zero there. Holding the position
    itself lets the restore path be driven on every host.
    """

    def __init__(self, column, value, trace):
        self.column = column
        self.position = value
        self.trace = trace

    def value(self):
        self.trace.append([surface.READ_SCROLL, self.column, self.position])
        return self.position

    def setValue(self, value):
        self.position = value
        self.trace.append([surface.SET_SCROLL, self.column, value])


class ColumnStandIn:
    """One column of the matrix, standing in for the platform's list.

    Records what the matrix does to it. Every method here is one the
    matrix really calls; anything else fails loudly rather than
    answering nothing.
    """

    def __init__(self, column, trace, scroll=0):
        self.column = column
        self.trace = trace
        self.entries = []
        self.bar = ScrollStandIn(column, scroll, trace)

    def verticalScrollBar(self):
        return self.bar

    def clear(self):
        self.trace.append([surface.CLEAR_COLUMN, self.column, len(self.entries)])
        self.entries = []

    def addItem(self, entry):
        from PySide6.QtCore import Qt

        self.trace.append(
            [
                surface.ADD_ROW,
                self.column,
                entry.text(),
                entry.data(Qt.UserRole),
                entry.checkState().value,
                entry.flags().value,
            ]
        )
        self.entries.append(entry)

    def count(self):
        return len(self.entries)

    def item(self, index):
        return self.entries[index]

    def rows(self):
        """Every row now in this column, as the surface describes one."""
        from PySide6.QtCore import Qt

        return [
            {
                "label": entry.text(),
                "bot_id": entry.data(Qt.UserRole),
                "check_state": entry.checkState().value,
                "flags": entry.flags().value,
            }
            for entry in self.entries
        ]

    def tick(self, bot_ids):
        """Tick exactly the named bots, as the operator does with a mouse."""
        from PySide6.QtCore import Qt

        wanted = list(bot_ids)
        for entry in self.entries:
            entry.setCheckState(
                Qt.Checked if entry.data(Qt.UserRole) in wanted else Qt.Unchecked
            )

    def __getattr__(self, name):
        raise AssertionError(
            f"the matrix asked its {self.column} column for {name!r}, which this "
            "stand-in does not answer, so the run measured nothing"
        )


class RateStandIn:
    """The Rate box, answering whatever the input put in it."""

    def __init__(self, typed):
        self.typed = typed

    def text(self):
        return self.typed


class CardStandIn:
    """One bot's on-screen card, carrying the symbol it shows."""

    def __init__(self, symbol):
        self._bot_data = {"symbol": symbol}


class CardTable:
    """The matrix's view of the bot cards, answering through the tab."""

    def __init__(self, tab):
        self.tab = tab

    def get(self, bot_id):
        symbol = self.tab.widget_symbol(bot_id)
        return None if symbol is None else CardStandIn(symbol)


class StoredBots:
    """The stored settings, answering one bot at a time through the tab."""

    def __init__(self, tab):
        self.tab = tab

    def get(self, bot_id, *_unused):
        return {"config": {"symbol": self.tab.state_symbol(bot_id)}}


def stored_settings(tab):
    """A stand-in for the settings reader the matrix falls back to."""

    class SettingsStandIn:
        def load_state(self):
            return {"bots": StoredBots(tab)}

    return SettingsStandIn


def bus_for(tab):
    """A stand-in for the event bus the matrix tells about a change."""

    class BusStandIn:
        def emit(self, topic, **named):
            tab.emit(topic, **named)

    return BusStandIn()


def viz_for(tab):
    """A stand-in for the visualizer tab the matrix saves through."""
    from PySide6.QtWidgets import QWidget

    class VizStandIn(QWidget):
        def __init__(self):
            super().__init__()
            self.setAccessibleName("Bot Visualization Tab")
            self._bot_widgets = CardTable(tab)

        def _apply_routes_to_state(self, add, remove):
            tab.apply_routes(add, remove)

        def _clear_all_routes_in_state(self):
            return [tuple(one) for one in tab.clear_all_routes()]

    return VizStandIn()


class Swapped:
    """Put the process-wide names a run replaces back when it is done.

    The message boxes, the settings reader and the event bus are one
    per process. Each side gets its own for the length of one drive, so
    a parallel run cannot order two drives into each other.
    """

    def __init__(self):
        self.restore = []

    def put(self, holder, name, value):
        self.restore.append((holder, name, getattr(holder, name)))
        setattr(holder, name, value)

    def undo(self):
        for holder, name, was in reversed(self.restore):
            setattr(holder, name, was)
        self.restore = []


def widget_block(matrix, col_row, btn_row, rate_zone):
    """Every value the built matrix carries, read off the platform."""

    def margins(layout):
        found = layout.contentsMargins()
        return [found.left(), found.top(), found.right(), found.bottom()]

    outer = matrix.layout()
    return {
        "outer_margins": margins(outer),
        "outer_spacing": outer.spacing(),
        "column_margins": margins(col_row),
        "column_spacing": col_row.spacing(),
        "column_stretches": [col_row.stretch(i) for i in range(col_row.count())],
        "rate_margins": margins(rate_zone.layout()),
        "button_margins": margins(btn_row),
        "button_spacing": btn_row.spacing(),
        "button_row_stretches": sum(
            1
            for index in range(btn_row.count())
            if btn_row.itemAt(index).spacerItem() is not None
        ),
        "list_style": matrix._source_list.styleSheet(),
        "dest_style": matrix._dest_list.styleSheet(),
        "rate_zone_style": rate_zone.styleSheet(),
        "rate_label_style": matrix._rate_label.styleSheet(),
        "rate_input_style": matrix._rate_input.styleSheet(),
        "rate_label_text": matrix._rate_label.text(),
        "default_rate_text": matrix._rate_input.text(),
        "button_texts": [
            matrix._connect_btn.text(),
            matrix._disconnect_btn.text(),
            matrix._disconnect_all_btn.text(),
        ],
        "tooltips": {
            "source": matrix._source_list.toolTip(),
            "destination": matrix._dest_list.toolTip(),
            "rate": matrix._rate_input.toolTip(),
            "connect": matrix._connect_btn.toolTip(),
            "disconnect": matrix._disconnect_btn.toolTip(),
            "disconnect_all": matrix._disconnect_all_btn.toolTip(),
        },
        "selection_mode": matrix._source_list.selectionMode().value,
        "scroll_policy": matrix._source_list.verticalScrollBarPolicy().value,
        "label_alignment": matrix._rate_label.alignment().value,
        "input_alignment": matrix._rate_input.alignment().value,
        "frame_shape": rate_zone.frameShape().name,
        "size_policy": matrix._source_list.sizePolicy().horizontalPolicy().name,
    }


def surface_widget_block():
    """The same values, written out by the surface rather than measured."""
    return {
        "outer_margins": list(surface.OUTER_MARGINS),
        "outer_spacing": surface.OUTER_SPACING,
        "column_margins": list(surface.COLUMN_MARGINS),
        "column_spacing": surface.COLUMN_SPACING,
        "column_stretches": [surface.COLUMN_STRETCH]
        * len(surface.SCREEN_ELEMENTS[1:4]),
        "rate_margins": list(surface.RATE_MARGINS),
        "button_margins": list(surface.BUTTON_MARGINS),
        "button_spacing": surface.BUTTON_SPACING,
        "button_row_stretches": surface.BUTTON_ROW_STRETCHES,
        "list_style": surface.LIST_STYLE,
        "dest_style": surface.LIST_STYLE,
        "rate_zone_style": surface.RATE_ZONE_STYLE,
        "rate_label_style": surface.RATE_LABEL_STYLE,
        "rate_input_style": surface.RATE_INPUT_STYLE,
        "rate_label_text": surface.RATE_LABEL_TEXT,
        "default_rate_text": surface.DEFAULT_RATE_TEXT,
        "button_texts": list(surface.BUTTON_TEXTS),
        "tooltips": {
            "source": surface.SOURCE_TOOLTIP,
            "destination": surface.DEST_TOOLTIP,
            "rate": surface.RATE_TOOLTIP,
            "connect": surface.CONNECT_TOOLTIP,
            "disconnect": surface.DISCONNECT_TOOLTIP,
            "disconnect_all": surface.DISCONNECT_ALL_TOOLTIP,
        },
        "selection_mode": surface.NO_SELECTION_VALUE,
        "scroll_policy": surface.SCROLL_AS_NEEDED_VALUE,
        "label_alignment": surface.ALIGN_CENTER_VALUE,
        "input_alignment": surface.ALIGN_CENTER_VALUE,
        "frame_shape": surface.FRAME_SHAPE,
        "size_policy": surface.EXPANDING,
    }


def hiding_register(masked):
    """A privacy register of this run's own, hiding the bot names or not.

    The shipped matrix asks the process-wide register whether the bot
    names are hidden. Each drive gets its own so a parallel run cannot
    order two drives into each other, and it saves nothing, so no run
    writes into the operator's tree.
    """
    from src.core.privacy_mask_registry import PrivacyMaskRegistry

    register = PrivacyMaskRegistry(
        settings_path=Path(tempfile.mkdtemp()) / "settings.json", autosave=False
    )
    register.set_masked(surface.MASK_FIELD_ID, bool(masked))
    return register


def build_matrix(tab):
    """Build the shipped matrix over a stand-in visualizer tab."""
    from src.gui.visualizer import quick_routing as shipped

    app()
    return shipped.QuickRoutingMatrix(viz_for(tab))


def swapped_world(tab, deferred=None):
    """Replace every process-wide name one drive of the matrix reaches.

    The message boxes, the settings reader, the event bus, the privacy
    register and the deferred-call timer are one per process. Each drive
    gets its own, so no drive reads the operator's settings, writes into
    their tree, or leaves a name replaced for the next test.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox

    import src.core.event_bus as event_bus
    import src.core.privacy_mask_registry as privacy_mask_registry
    import src.core.state_manager as state_manager

    swapped = Swapped()
    if deferred is not None:
        swapped.put(
            QTimer, "singleShot", staticmethod(lambda ms, fn: deferred.append([ms, fn]))
        )
    swapped.put(
        QMessageBox,
        "warning",
        staticmethod(lambda _parent, title, body: tab.warn(title, body)),
    )
    swapped.put(
        QMessageBox,
        "question",
        staticmethod(
            lambda _parent, title, body, *rest: (
                QMessageBox.Yes if tab.ask(title, body) else QMessageBox.No
            )
        ),
    )
    swapped.put(state_manager, "StateManager", stored_settings(tab))
    swapped.put(event_bus, "get_event_bus", lambda: bus_for(tab))
    swapped.put(
        privacy_mask_registry,
        "get_privacy_mask_registry",
        lambda: hiding_register(tab.masked),
    )
    return swapped


def old_trace(spec_name):
    """Drive the shipped matrix and return what it did, in one dict."""
    one = SPECS[spec_name]
    tab = surface.RoutingTabState(**one["tab"])
    matrix = build_matrix(tab)
    outer = matrix.layout()
    col_row = outer.itemAt(0).layout()
    btn_row = outer.itemAt(1).layout()
    rate_zone = col_row.itemAt(1).widget()
    block = widget_block(matrix, col_row, btn_row, rate_zone)

    trace = []
    source_scroll, dest_scroll = one["scroll"]
    columns = {
        surface.SOURCE_COLUMN: ColumnStandIn(
            surface.SOURCE_COLUMN, trace, source_scroll
        ),
        surface.DEST_COLUMN: ColumnStandIn(surface.DEST_COLUMN, trace, dest_scroll),
    }
    matrix._source_list = columns[surface.SOURCE_COLUMN]
    matrix._dest_list = columns[surface.DEST_COLUMN]
    matrix._rate_input = RateStandIn(one["rate"])

    deferred = []
    swapped = swapped_world(tab, deferred)

    reader = StopReader(tab)
    stops = []
    raised = None
    try:
        for step in one["steps"]:
            named = isinstance(step, (list, tuple))
            name = step[0] if named else step
            rest = list(step[1:]) if named else []
            if name == REBUILD:
                matrix.rebuild_scope(rest[0] if rest else [])
                reader.read()
                stops.append(REBUILD)
                for column, ticks in zip(
                    (surface.SOURCE_COLUMN, surface.DEST_COLUMN), one["ticks"]
                ):
                    columns[column].tick(ticks)
            elif name == CONNECT:
                matrix._on_connect_clicked()
                stops.append(reader.read())
            elif name == DISCONNECT:
                matrix._on_disconnect_clicked()
                stops.append(reader.read())
            elif name == DISCONNECT_ALL:
                matrix._on_disconnect_all_clicked()
                stops.append(reader.read())
    except Exception as exc:
        raised = exc
    finally:
        swapped.undo()

    mark = len(trace)
    for _ms, run in deferred:
        run()
    applied = [
        [entry[1], entry[2]] for entry in trace[mark:] if entry[0] == surface.SET_SCROLL
    ]

    return {
        "widget": block,
        "rows": {name: columns[name].rows() for name in columns},
        "scroll": {
            surface.SOURCE_COLUMN: columns[surface.SOURCE_COLUMN].bar.position,
            surface.DEST_COLUMN: columns[surface.DEST_COLUMN].bar.position,
            "deferred": applied,
        },
        "stops": stops,
        "calls": [list(one_call) for one_call in trace],
        "tab": tab.state(),
        "deferred_delays": [entry[0] for entry in deferred],
        "raised": None if raised is None else type(raised).__name__,
    }


def fixed_part(pattern, before=False):
    """The part of a refusal's wording no value can change."""
    return pattern.split("{")[0] if before else pattern.split("}")[-1]


EXACT_REFUSALS = (
    (surface.REFUSED_NO_SOURCES, surface.NO_SOURCES_TEXT),
    (surface.REFUSED_NO_DESTINATIONS, surface.NO_DESTINATIONS_TEXT),
    (surface.REFUSED_ZERO_RATE, surface.ZERO_RATE_TEXT),
    (surface.REFUSED_SELF_WIRE, surface.SELF_WIRE_CONNECT_TEXT),
    (surface.REFUSED_SELF_WIRE, surface.SELF_WIRE_DISCONNECT_TEXT),
)

PART_REFUSALS = (
    (surface.REFUSED_NOT_A_NUMBER, fixed_part(surface.NOT_A_NUMBER_FORMAT)),
    (surface.REFUSED_OUT_OF_RANGE, fixed_part(surface.OUT_OF_RANGE_FORMAT)),
    (
        surface.REFUSED_SAVE_FAILED,
        fixed_part(surface.SAVE_FAILED_FORMAT, before=True),
    ),
)


class StopReader:
    """Where each shipped click stopped, read off what it did to the tab.

    The shipped buttons answer nothing, so their stopping point is read
    from the tab: which refusal they showed, whether they asked, whether
    they saved, whether the clear landed and whether the bus took every
    event they handed it.
    """

    def __init__(self, tab):
        self.tab = tab
        self.marks = self.now()

    def now(self):
        return {
            "calls": len(self.tab.calls),
            "emitted": len(self.tab.emitted),
            "cleared": len(self.tab.cleared),
        }

    def read(self):
        """The branch name for the click that has just run."""
        was = self.marks
        self.marks = self.now()
        since = self.tab.calls[was["calls"] :]
        names = [one[0] for one in since]
        warned = [one for one in since if one[0] == surface.TAB_WARN]
        if warned:
            wording = warned[-1][2]
            for branch, text in EXACT_REFUSALS:
                if wording == text:
                    return branch
            for branch, part in PART_REFUSALS:
                if part and part in wording:
                    return branch
            raise AssertionError("no branch owns the refusal %r" % wording)
        saved = surface.TAB_APPLY_ROUTES in names
        cleared = surface.TAB_CLEAR_ROUTES in names
        if not saved and not cleared:
            return surface.REFUSED_UNCONFIRMED
        asked = names.count(surface.TAB_EMIT)
        if asked > self.marks["emitted"] - was["emitted"]:
            return surface.REDRAW_FAILED
        if cleared and self.marks["cleared"] == was["cleared"]:
            return surface.CLEAR_FAILED
        return surface.DONE


def new_trace(spec_name):
    """Drive the surface and return what it did, in the same shape."""
    one = SPECS[spec_name]
    tab = surface.RoutingTabState(**one["tab"])
    source_scroll, dest_scroll = one["scroll"]
    model = surface.QuickRoutingModel(
        tab, one["rate"], source_scroll=source_scroll, dest_scroll=dest_scroll
    )
    stops = []
    raised = None
    try:
        stops = model.apply(one["steps"], one["ticks"][0], one["ticks"][1])
    except Exception as exc:
        raised = exc
    mark = len(model.calls)
    model.run_deferred_scroll()
    applied = [
        [entry[1], entry[2]]
        for entry in model.calls[mark:]
        if entry[0] == surface.SET_SCROLL
    ]
    return {
        "widget": surface_widget_block(),
        "rows": {
            surface.SOURCE_COLUMN: [dict(row) for row in model.source_rows],
            surface.DEST_COLUMN: [dict(row) for row in model.dest_rows],
        },
        "scroll": {
            surface.SOURCE_COLUMN: model.source_scroll,
            surface.DEST_COLUMN: model.dest_scroll,
            "deferred": applied,
        },
        "stops": stops,
        "calls": [list(one_call) for one_call in model.calls],
        "tab": tab.state(),
        "deferred_delays": [
            surface.TIMERS[surface.SCROLL_RESTORE_TIMER] for _entry in applied
        ],
        "raised": None if raised is None else type(raised).__name__,
    }


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", sorted(SPECS))
def test_the_two_sides_describe_one_matrix(name):
    """The surface describes a different matrix than the shipped one."""
    old = old_trace(name)
    new = new_trace(name)
    for key in sorted(old):
        assert canonical(old[key]) == canonical(new[key]), (name, key)
    assert digest(old) == digest(new), (name, digest(old), digest(new))


def test_the_hash_tells_two_different_matrices_apart():
    """The hash reports one value whatever the two sides did."""
    first = old_trace("ticks_one_each_way")
    second = new_trace("ticks_two_sources_one_destination")
    assert digest(first) != digest(second)
    third = old_trace("ticks_two_sources_one_destination")
    fourth = new_trace("ticks_one_each_way")
    assert digest(third) != digest(fourth)
    assert digest(first) == digest(new_trace("ticks_one_each_way"))
    assert digest(third) == digest(old_trace("ticks_two_sources_one_destination"))


def test_the_same_input_twice_hashes_the_same_on_both_sides():
    """A drive carried something from the run before it."""
    assert digest(old_trace("tab_happy_three_bots")) == digest(
        old_trace("tab_happy_three_bots")
    )
    assert digest(new_trace("tab_happy_three_bots")) == digest(
        new_trace("tab_happy_three_bots")
    )


SAMPLE_SPECS = (
    "tab_happy_three_bots",
    "tab_hidden_names",
    "rate_not_a_number",
    "steps_every_button_in_turn",
    "scroll_both_columns_scrolled",
)


@pytest.mark.parametrize("name", SAMPLE_SPECS)
def test_the_sample_matrix_hashes_are_reported(name):
    """The sample hashes could not be taken."""
    old = digest(old_trace(name))
    new = digest(new_trace(name))
    assert old == new, (name, old, new)
    assert len(old) == len(hashlib.sha256(b"").hexdigest())


@pytest.mark.parametrize("name", sorted(STEP_SPECS))
def test_a_step_sequence_stops_in_the_same_place_on_both_sides(name):
    """A run of clicks went further on one side than the other."""
    key = "steps_" + name
    old = old_trace(key)
    new = new_trace(key)
    assert old["stops"] == new["stops"], (name, old["stops"], new["stops"])
    assert len(old["stops"]) == len(SPECS[key]["steps"])
    for stop in old["stops"]:
        assert stop in surface.BRANCH_NAMES or stop == REBUILD, stop


def test_every_stopping_point_the_surface_names_is_reached():
    """The surface names a stopping point no input can produce."""
    reached = set()
    for name in SPECS:
        reached.update(new_trace(name)["stops"])
    reached.discard(REBUILD)
    assert reached == set(surface.BRANCH_NAMES), sorted(
        set(surface.BRANCH_NAMES) ^ reached
    )


def test_the_two_sides_refuse_an_unknown_step_with_one_type():
    """A step neither side knows ended one of them differently."""
    tab = surface.RoutingTabState()
    model = surface.QuickRoutingModel(tab)
    with pytest.raises(ValueError):
        model.apply(["fly"])
    with pytest.raises(ValueError):
        surface.build_view_model(surface.QuickRoutingModel(tab), ["fly"])


def test_a_question_that_cannot_be_put_ends_disconnect_all_the_same_way():
    """One side swallowed a question the other let out."""
    name = "tab_the_question_cannot_be_put"
    steps = [[REBUILD, THREE_BOTS], DISCONNECT_ALL]
    SPECS["a_disconnect_all_with_no_screen"] = dict(SPECS[name], steps=steps)
    old = old_trace("a_disconnect_all_with_no_screen")
    new = new_trace("a_disconnect_all_with_no_screen")
    assert old["raised"] == new["raised"] == "RuntimeError"
    assert canonical(old["tab"]) == canonical(new["tab"])


# The enumeration


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def parsed(path):
    """The file at `path` as a tree, so prose cannot be counted as code."""
    return ast.parse(path.read_text(encoding="utf-8"))


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
                    "lambda" if isinstance(target, ast.Lambda) else dotted(target),
                )
            )
    return sorted(found)


def signal_sites(path) -> list:
    """Every ``Signal()`` a class in `path` declares, as class and name."""
    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            value = statement.value
            if isinstance(value, ast.Call) and dotted(value.func).endswith("Signal"):
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        found.append("%s.%s" % (node.name, target.id))
    return sorted(found)


def narrow_timer_sites(path) -> list:
    """Every ``QTimer(`` construction in `path`, and nothing else."""
    return [
        node
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def timer_sites(path) -> list:
    """Every timer `path` starts, built one or asked for a single shot.

    ``QTimer.singleShot`` runs a timer without building one, so a
    counter that only looks for a construction reports none where the
    file really starts one.
    """
    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.Call):
            continue
        name = dotted(node.func)
        if name.endswith("QTimer") or name.split(".")[:-1][-1:] == ["QTimer"]:
            found.append(name)
    return sorted(found)


def bus_sites(path) -> list:
    """Every bus topic `path` names, listened for or told about."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("subscribe", "emit")
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def classes_in_file(path) -> list:
    """Every class `path` declares, at any depth."""
    return sorted(
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    )


def methods_in_file(path) -> list:
    """Every method a class in `path` declares, read off the parsed file.

    Reading the file rather than the built class finds a decorated
    method, a class declared inside another method, and a method the
    platform would have added to the class object. A declared signal is
    a value, not a function, so it is not counted.
    """
    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.ClassDef):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append("%s.%s" % (node.name, inner.name))
    return sorted(set(found))


def paints_on_screen(name: str) -> bool:
    """True when the platform can paint a thing of this name."""
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtWidgets import QWidget

    for module in (QtWidgets, QtGui, QtCore):
        found = getattr(module, name, None)
        if isinstance(found, type):
            return issubclass(found, QWidget)
    return False


def screen_elements(path) -> list:
    """Every screen element `path` builds: a class it declares, one it makes."""
    found = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if paints_on_screen(dotted(base).split(".")[-1]):
                    found.append(("declares", node.name))
        elif isinstance(node, ast.Call):
            name = dotted(node.func).split(".")[-1]
            if paints_on_screen(name):
                found.append(("builds", name))
    return found


SHIPPED_CLASSES = {"QuickRoutingMatrix": "QuickRoutingModel"}
EXTRA_SURFACE_CLASSES = {"RoutingTabState": "BotVisualizationTab"}

SHIPPED_METHODS = {
    "QuickRoutingMatrix.__init__": "QuickRoutingModel.__init__",
    "QuickRoutingMatrix.rebuild_scope": "QuickRoutingModel.rebuild_scope",
    "QuickRoutingMatrix._symbol_for": "QuickRoutingModel.symbol_for",
    "QuickRoutingMatrix._selected_sources": "QuickRoutingModel.selected_sources",
    "QuickRoutingMatrix._selected_destinations": (
        "QuickRoutingModel.selected_destinations"
    ),
    "QuickRoutingMatrix._reject": "QuickRoutingModel.reject",
    "QuickRoutingMatrix._confirm_mass": "QuickRoutingModel.confirm_mass",
    "QuickRoutingMatrix._on_connect_clicked": "QuickRoutingModel.connect_clicked",
    "QuickRoutingMatrix._on_disconnect_clicked": "QuickRoutingModel.disconnect_clicked",
    "QuickRoutingMatrix._on_disconnect_all_clicked": (
        "QuickRoutingModel.disconnect_all_clicked"
    ),
}


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped matrix gained or lost a class or a method."""
    assert classes_in_file(MATRIX_SOURCE) == sorted(SHIPPED_CLASSES), classes_in_file(
        MATRIX_SOURCE
    )
    found = methods_in_file(MATRIX_SOURCE)
    assert found == sorted(SHIPPED_METHODS), found
    for counterpart in SHIPPED_METHODS.values():
        holder, _, name = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), name)), counterpart
    for counterpart in SHIPPED_CLASSES.values():
        assert isinstance(getattr(surface, counterpart), type), counterpart


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing."""
    built = classes_in_file(SURFACE_SOURCE)
    assert built == sorted(
        list(SHIPPED_CLASSES.values()) + list(EXTRA_SURFACE_CLASSES)
    ), built
    from src.gui import bot_visualizer

    for named in EXTRA_SURFACE_CLASSES.values():
        assert named in classes_in_file(
            REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
        ), named
    assert hasattr(bot_visualizer, "BotVisualizationTab")


def test_the_method_counter_leaves_a_declared_signal_out():
    """The method counter counts a declared signal as a method."""
    declared = signal_sites(SIGNAL_NEIGHBOUR)
    assert len(declared) == 3, declared
    assert "ModeCard.clicked" in declared
    counted = methods_in_file(SIGNAL_NEIGHBOUR)
    assert counted, "the method counter reports nothing"
    for name in declared:
        assert name not in counted, name
    assert "ModeCard.__init__" in counted


def test_the_method_counter_finds_a_decorated_method():
    """The counter misses a method a decorator wraps."""
    counted = methods_in_file(DECORATED_NEIGHBOUR)
    for name in ("lock_timeframe", "selected_bot_id", "_reading_fingerprint"):
        assert any(one.endswith("." + name) for one in counted), (name, len(counted))


def test_the_method_counter_finds_a_class_declared_inside_a_method():
    """The counter misses a class one method declares."""
    counted = methods_in_file(NESTED_NEIGHBOUR)
    assert "_StockLogHandler.emit" in counted, len(counted)
    assert "_StockLogHandler._append_to_widget" in counted
    assert "_StockLogHandler" in classes_in_file(NESTED_NEIGHBOUR)


def test_the_matrix_wires_three_buttons_and_the_surface_names_three_actions():
    """A wired button has no action beside it on the surface."""
    sites = connect_sites(MATRIX_SOURCE)
    assert sites == [
        ("self._connect_btn.clicked", "self._on_connect_clicked"),
        ("self._disconnect_all_btn.clicked", "self._on_disconnect_all_clicked"),
        ("self._disconnect_btn.clicked", "self._on_disconnect_clicked"),
    ], sites
    assert len(surface.ACTIONS) == len(sites)
    assert MATRIX_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    assert sorted(surface.ACTIONS) == [
        "connect_btn.clicked",
        "disconnect_all_btn.clicked",
        "disconnect_btn.clicked",
    ]
    for target in surface.ACTIONS.values():
        assert callable(getattr(surface.QuickRoutingModel, target)), target


def test_the_wiring_counter_reports_on_a_file_that_wires_one():
    """The wiring counter reports nothing whatever file it reads."""
    assert connect_sites(CONNECT_NEIGHBOUR) == [("self.clicked", "self._on_click")]


def test_the_matrix_declares_no_signal_and_the_counter_can_report():
    """The matrix declares a signal the surface answers with nothing."""
    assert signal_sites(MATRIX_SOURCE) == []
    assert surface.SIGNALS == ()
    assert len(signal_sites(SIGNAL_NEIGHBOUR)) == 3, "the signal counter is blind"


def test_the_matrix_runs_one_timer_and_the_surface_declares_its_delay():
    """A timer the matrix runs has no delay beside it on the surface."""
    found = timer_sites(MATRIX_SOURCE)
    assert found == ["QTimer.singleShot"], found
    assert len(surface.TIMERS) == len(found)
    assert surface.TIMER_DELAYS_MS == (0,)
    assert surface.SINGLE_SHOT_TIMERS == (surface.SCROLL_RESTORE_TIMER,)


def test_the_narrow_timer_counter_misses_the_one_the_matrix_runs():
    """The wide timer counter counts nothing the narrow one misses."""
    assert narrow_timer_sites(MATRIX_SOURCE) == []
    assert len(timer_sites(MATRIX_SOURCE)) == 1
    assert len(narrow_timer_sites(TIMER_NEIGHBOUR)) == 1
    assert len(timer_sites(TIMER_NEIGHBOUR)) >= 1
    assert timer_sites(QUIET_TIMER_NEIGHBOUR) == []
    assert TIMER_NEIGHBOUR != QUIET_TIMER_NEIGHBOUR
    assert TIMER_NEIGHBOUR.name == QUIET_TIMER_NEIGHBOUR.name


def test_the_matrix_names_two_bus_topics_and_the_surface_carries_both():
    """A topic the matrix names is missing from the surface."""
    found = bus_sites(MATRIX_SOURCE)
    assert sorted(set(found)) == sorted(surface.BUS_TOPICS), found
    assert len(found) == 3, found
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter is blind"
    assert "wire.created" in neighbour


def test_the_matrix_builds_nine_screen_elements_and_the_surface_names_them():
    """A screen element the matrix builds is missing from the surface."""
    found = screen_elements(MATRIX_SOURCE)
    assert found == [tuple(one) for one in surface.SCREEN_ELEMENTS], found
    assert len(found) == len(surface.SCREEN_ELEMENTS)
    neighbour = screen_elements(PAINT_NEIGHBOUR)
    assert neighbour == [
        ("declares", "StatCard"),
        ("builds", "QLabel"),
        ("builds", "QLabel"),
    ], neighbour


def test_the_screen_counter_counts_a_painted_class_and_not_a_layout():
    """The counter calls a layout or a timer a screen element."""
    assert paints_on_screen("QListWidget") is True
    assert paints_on_screen("QPushButton") is True
    assert paints_on_screen("QVBoxLayout") is False
    assert paints_on_screen("QHBoxLayout") is False
    assert paints_on_screen("QTimer") is False
    assert paints_on_screen("QListWidgetItem") is False
    assert paints_on_screen("NotAQtClass") is False


def test_the_counters_read_the_parsed_file_and_not_its_prose():
    """A counter counts a name inside a comment or a string."""
    body = "# QTimer(0)\nTEXT = 'QTimer(1)'\nimport x\nx.connect(1)\n"
    scratch = Path(tempfile.mkdtemp()) / "prose.py"
    scratch.write_text(body, encoding="utf-8", newline="\n")
    assert timer_sites(scratch) == []
    assert body.count("QTimer(") == 2
    assert len(connect_sites(scratch)) == 1


# The completeness check

PAYLOAD_KEYS = {
    "LIST_SURFACE": "colors.list_surface",
    "LIST_BORDER": "colors.list_border",
    "LIST_TEXT": "colors.list_text",
    "INPUT_SURFACE": "colors.input_surface",
    "INPUT_BORDER": "colors.input_border",
    "COLOR_NAMES": "colors.names",
    "OUTER_MARGINS": "layout.outer_margins",
    "OUTER_SPACING": "layout.outer_spacing",
    "COLUMN_MARGINS": "layout.column_margins",
    "COLUMN_SPACING": "layout.column_spacing",
    "COLUMN_STRETCH": "layout.column_stretch",
    "RATE_MARGINS": "layout.rate_margins",
    "BUTTON_MARGINS": "layout.button_margins",
    "BUTTON_SPACING": "layout.button_spacing",
    "BUTTON_ROW_STRETCHES": "layout.button_row_stretches",
    "LIST_STYLE": "styles.list",
    "RATE_ZONE_STYLE": "styles.rate_zone",
    "RATE_LABEL_STYLE": "styles.rate_label",
    "RATE_INPUT_STYLE": "styles.rate_input",
    "FRAME_SHAPE": "styles.frame_shape",
    "EXPANDING": "styles.size_policy",
    "RATE_LABEL_TEXT": "texts.rate_label",
    "DEFAULT_RATE_TEXT": "texts.default_rate",
    "CONNECT_TEXT": "texts.connect",
    "DISCONNECT_TEXT": "texts.disconnect",
    "DISCONNECT_ALL_TEXT": "texts.disconnect_all",
    "BUTTON_TEXTS": "texts.buttons",
    "SOURCE_TOOLTIP": "tooltips.source",
    "DEST_TOOLTIP": "tooltips.destination",
    "RATE_TOOLTIP": "tooltips.rate",
    "CONNECT_TOOLTIP": "tooltips.connect",
    "DISCONNECT_TOOLTIP": "tooltips.disconnect",
    "DISCONNECT_ALL_TOOLTIP": "tooltips.disconnect_all",
    "NO_SELECTION": "platform_values.selection_mode",
    "NO_SELECTION_VALUE": "platform_values.selection_mode_value",
    "SCROLL_AS_NEEDED": "platform_values.scroll_policy",
    "SCROLL_AS_NEEDED_VALUE": "platform_values.scroll_policy_value",
    "ALIGN_CENTER": "platform_values.alignment",
    "ALIGN_CENTER_VALUE": "platform_values.alignment_value",
    "USER_ROLE": "platform_values.user_role",
    "USER_ROLE_VALUE": "platform_values.user_role_value",
    "USER_CHECKABLE_VALUE": "platform_values.user_checkable_value",
    "ROW_FLAGS": "platform_values.row_flags",
    "CHECKED": "platform_values.checked",
    "UNCHECKED": "platform_values.unchecked",
    "ROW_FORMAT": "labels.format",
    "SHORT_ID_LENGTH": "labels.short_id_length",
    "MASK_FIELD_ID": "labels.mask_field_id",
    "SYMBOL_MASK": "labels.symbol_mask",
    "SHORT_ID_MASK": "labels.short_id_mask",
    "UNKNOWN_SYMBOL": "labels.unknown_symbol",
    "EMPTY_SYMBOL": "labels.empty_symbol",
    "PERCENT_SUFFIX": "rate.suffix",
    "RATE_MIN_PCT": "rate.min_pct",
    "RATE_MAX_PCT": "rate.max_pct",
    "ZERO_RATE_PCT": "rate.zero_pct",
    "REFUSAL_TITLE": "refusals.title",
    "NOT_A_NUMBER_FORMAT": "refusals.not_a_number",
    "OUT_OF_RANGE_FORMAT": "refusals.out_of_range",
    "NO_SOURCES_TEXT": "refusals.no_sources",
    "NO_DESTINATIONS_TEXT": "refusals.no_destinations",
    "ZERO_RATE_TEXT": "refusals.zero_rate",
    "SELF_WIRE_CONNECT_TEXT": "refusals.self_wire_connect",
    "SELF_WIRE_DISCONNECT_TEXT": "refusals.self_wire_disconnect",
    "SAVE_FAILED_FORMAT": "refusals.save_failed",
    "STEP_REFUSAL": "refusals.step",
    "CREATE_VERB": "confirmation.create_verb",
    "DISCONNECT_VERB": "confirmation.disconnect_verb",
    "CONFIRM_TITLE_FORMAT": "confirmation.title",
    "CONFIRM_BODY_FORMAT": "confirmation.body",
    "PLURAL_SUFFIX": "confirmation.plural_suffix",
    "SINGULAR_COUNT": "confirmation.singular_count",
    "CREATE_WARNING": "confirmation.create_warning",
    "DISCONNECT_WARNING": "confirmation.disconnect_warning",
    "CONNECT_DETAIL_FORMAT": "confirmation.connect_detail",
    "DISCONNECT_DETAIL_FORMAT": "confirmation.disconnect_detail",
    "DISCONNECT_ALL_TITLE": "confirmation.all_title",
    "DISCONNECT_ALL_BODY": "confirmation.all_body",
    "WIRE_CREATED": "bus.created",
    "WIRE_REMOVED": "bus.removed",
    "BUS_TOPICS": "bus.topics",
    "ACTIONS": "wiring.actions",
    "ACTION_ORDER": "wiring.action_order",
    "BUTTON_KEYS": "wiring.button_keys",
    "SIGNALS": "wiring.signals",
    "TIMERS": "wiring.timers",
    "TIMER_DELAYS_MS": "wiring.timer_delays_ms",
    "SINGLE_SHOT_TIMERS": "wiring.single_shot_timers",
    "SCROLL_RESTORE_TIMER": "wiring.scroll_restore_timer",
    "SCREEN_ELEMENTS": "wiring.screen_elements",
    "COLUMN_NAMES": "names.columns",
    "SOURCE_COLUMN": "names.source_column",
    "DEST_COLUMN": "names.dest_column",
    "ROUTE_NAMES": "names.routes",
    "RATE_PARAM": "names.rate_param",
    "STEPS_PARAM": "names.steps_param",
    "CHECKED_PARAMS": "names.checked_params",
    "PANEL_CALL_NAMES": "names.panel_calls",
    "BRANCH_NAMES": "names.branches",
    "STEP_NAMES": "names.steps",
}

LIST_MEMBERS = {
    "TAB_WIDGET_SYMBOL": "names.routes",
    "TAB_STATE_SYMBOL": "names.routes",
    "TAB_APPLY_ROUTES": "names.routes",
    "TAB_CLEAR_ROUTES": "names.routes",
    "TAB_EMIT": "names.routes",
    "TAB_WARN": "names.routes",
    "TAB_ASK": "names.routes",
    "READ_SCROLL": "names.panel_calls",
    "CLEAR_COLUMN": "names.panel_calls",
    "ADD_ROW": "names.panel_calls",
    "SET_SCROLL": "names.panel_calls",
    "REFUSED_NOT_A_NUMBER": "names.branches",
    "REFUSED_OUT_OF_RANGE": "names.branches",
    "REFUSED_NO_SOURCES": "names.branches",
    "REFUSED_NO_DESTINATIONS": "names.branches",
    "REFUSED_ZERO_RATE": "names.branches",
    "REFUSED_SELF_WIRE": "names.branches",
    "REFUSED_UNCONFIRMED": "names.branches",
    "REFUSED_SAVE_FAILED": "names.branches",
    "REDRAW_FAILED": "names.branches",
    "CLEAR_FAILED": "names.branches",
    "DONE": "names.branches",
    "CONNECT_STEP": "names.steps",
    "DISCONNECT_STEP": "names.steps",
    "DISCONNECT_ALL_STEP": "names.steps",
    "REBUILD_STEP": "names.steps",
}

NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_quick_routing_method",
    "MODEL": "test_the_bridge_builds_its_panel_on_the_first_request",
}

STATE_ONLY_KEYS = {
    "rate",
    "rows",
    "scroll",
    "selected",
    "scope_ids",
    "stops",
    "calls",
    "tab",
}


def at_path(payload, path):
    """The payload value one dotted path names; a number steps into a list."""
    found = payload
    for step in path.split("."):
        found = found[int(step)] if step.isdigit() else found[step]
    return found


def as_lists(value):
    """`value` with every tuple turned into a list, at every depth."""
    if isinstance(value, dict):
        return {key: as_lists(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_lists(inner) for inner in value]
    return value


def surface_constants() -> dict:
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


def sample_payload():
    """One view model over a matrix that has been rebuilt and clicked."""
    tab = surface.RoutingTabState(**TAB_SPECS["happy_three_bots"])
    model = surface.QuickRoutingModel(tab)
    return surface.build_view_model(
        model, [[REBUILD, THREE_BOTS], CONNECT], [ALPHA], [BETA]
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read."""
    payload = sample_payload()
    constants = surface_constants()
    assert constants, "the constant reader reports nothing"
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payload, PAYLOAD_KEYS[name]) == as_lists(value), name
        elif name in LIST_MEMBERS:
            assert value in at_path(payload, LIST_MEMBERS[name]), name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(constants) == len(PAYLOAD_KEYS) + len(LIST_MEMBERS) + len(
        NOT_IN_THE_SNAPSHOT
    )


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = sample_payload()
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {path.split(".")[0] for path in LIST_MEMBERS.values()}
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing."""
    payload = sample_payload()
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in LIST_MEMBERS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "LIST_STYLE" in surface_constants()
    assert "ACTIONS" in surface_constants()
    assert "row_label" not in surface_constants()
    assert "QuickRoutingModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "colors.invented")
    with pytest.raises(IndexError):
        at_path(payload, "colors.names.99")


# The surface carries its own values


@pytest.fixture
def restored_design_tokens():
    """Put the shipped colour tokens back after a test changes one."""
    from src.gui import design_system

    names = ("VIZ_LIST_SURFACE", "VIZ_LIST_BORDER", "VIZ_LIST_TEXT")
    was = {name: getattr(design_system, name) for name in names}
    yield design_system
    for name, value in was.items():
        setattr(design_system, name, value)


def test_the_surface_does_not_follow_a_colour_moved_in_the_shipped_tokens(
    restored_design_tokens,
):
    """The surface read its colours off the tokens it replaces."""
    import importlib

    from src.gui.visualizer import quick_routing as shipped

    before = old_trace("tab_happy_three_bots")["widget"]["list_style"]
    assert surface.LIST_SURFACE in before
    restored_design_tokens.VIZ_LIST_SURFACE = "#010203"
    importlib.reload(shipped)
    try:
        moved = old_trace("tab_happy_three_bots")["widget"]["list_style"]
    finally:
        restored_design_tokens.VIZ_LIST_SURFACE = "#0a0a18"
        importlib.reload(shipped)
    assert "#010203" in moved, moved
    assert moved != before
    assert surface.LIST_SURFACE == "#0a0a18"
    assert surface_widget_block()["list_style"] == before
    assert old_trace("tab_happy_three_bots")["widget"]["list_style"] == before


def test_the_comparison_names_the_value_that_moved():
    """The comparison reports a difference without saying what it was."""
    old = old_trace("tab_happy_three_bots")
    new = new_trace("tab_happy_three_bots")
    changed = json.loads(json.dumps(new["widget"]))
    changed["rate_label_text"] = "Ratio"
    differing = [
        key
        for key in sorted(old["widget"])
        if canonical(old["widget"][key]) != canonical(changed[key])
    ]
    assert differing == ["rate_label_text"], differing
    assert old["widget"]["rate_label_text"] == "Rate"


def test_the_surface_keeps_no_state_between_two_matrices():
    """A matrix built after another carried the first one's values."""
    first = new_trace("steps_every_button_in_turn")
    second = new_trace("tab_happy_three_bots")
    third = new_trace("tab_happy_three_bots")
    assert digest(second) == digest(third)
    assert digest(first) != digest(second)


def test_the_shipped_matrix_writes_to_no_shared_table(restored_design_tokens):
    """The shipped matrix changes a value other tests read."""
    names = ("VIZ_LIST_SURFACE", "VIZ_LIST_BORDER", "VIZ_LIST_TEXT")
    before = {name: getattr(restored_design_tokens, name) for name in names}
    for spec_name in ("tab_happy_three_bots", "steps_every_button_in_turn"):
        old_trace(spec_name)
    after = {name: getattr(restored_design_tokens, name) for name in names}
    assert after == before
    restored_design_tokens.VIZ_LIST_SURFACE = "#010203"
    changed = {name: getattr(restored_design_tokens, name) for name in names}
    assert changed != before, "the shared-value check cannot report a change"


def test_the_swaps_are_live_during_a_drive_and_gone_after():
    """A drive that says it replaces a process-wide name never did."""
    from PySide6.QtWidgets import QMessageBox

    import src.core.event_bus as event_bus
    import src.core.privacy_mask_registry as privacy_mask_registry
    import src.core.state_manager as state_manager

    watched = (
        (QMessageBox, "question"),
        (QMessageBox, "warning"),
        (event_bus, "get_event_bus"),
        (state_manager, "StateManager"),
        (privacy_mask_registry, "get_privacy_mask_registry"),
    )
    before = [getattr(holder, name) for holder, name in watched]
    tab = surface.RoutingTabState(**TAB_SPECS["happy_three_bots"])
    swapped = swapped_world(tab)
    try:
        during = [getattr(holder, name) for holder, name in watched]
    finally:
        swapped.undo()
    assert all(one is not two for one, two in zip(before, during)), during
    assert [getattr(holder, name) for holder, name in watched] == before
    driven = old_trace("asking_live")
    assert driven["tab"]["shown"], "the swapped message boxes saw nothing"
    assert [getattr(holder, name) for holder, name in watched] == before


def test_the_swap_is_undone_even_when_a_drive_refuses():
    """A run that refuses part way left a process-wide name replaced."""
    from PySide6.QtWidgets import QMessageBox

    real_warning = QMessageBox.warning
    swapped = Swapped()
    swapped.put(QMessageBox, "warning", staticmethod(lambda *_unused: None))
    assert QMessageBox.warning is not real_warning
    swapped.undo()
    assert QMessageBox.warning is real_warning
    SPECS["a_refused_disconnect_all"] = dict(
        SPECS["tab_the_question_cannot_be_put"],
        steps=[[REBUILD, THREE_BOTS], DISCONNECT_ALL],
    )
    assert old_trace("a_refused_disconnect_all")["raised"] == "RuntimeError"
    assert QMessageBox.warning is real_warning


def test_the_column_stand_in_refuses_a_call_it_does_not_answer():
    """The column stand-in answers nothing and swallows a wrong call."""
    column = ColumnStandIn(surface.SOURCE_COLUMN, [])
    assert column.count() == 0
    with pytest.raises(AssertionError):
        column.setStyleSheet("x")


# The colours, read as values


def test_every_declared_colour_matches_the_shipped_token():
    """A colour on the surface is not the one the matrix paints."""
    from src.gui import design_system

    assert surface.LIST_SURFACE == design_system.VIZ_LIST_SURFACE
    assert surface.LIST_BORDER == design_system.VIZ_LIST_BORDER
    assert surface.LIST_TEXT == design_system.VIZ_LIST_TEXT
    assert surface.INPUT_SURFACE == design_system.VIZ_INPUT_SURFACE
    assert surface.INPUT_BORDER == design_system.VIZ_INPUT_BORDER


def test_a_colour_with_two_equal_channels_is_compared_as_numbers():
    """A red and green swap in the list ground reads as no change.

    The list ground is ``#0a0a18``: its red and green are the same, so
    swapping them paints an identical picture. The channels are read as
    numbers here instead, where a swap of the two that differ reports.
    """

    def channels(value):
        return [int(value[index : index + 2], 16) for index in (1, 3, 5)]

    ground = channels(surface.LIST_SURFACE)
    assert ground[0] == ground[1], surface.LIST_SURFACE
    assert ground[0] != ground[2], surface.LIST_SURFACE
    swapped_red_green = [ground[1], ground[0], ground[2]]
    assert swapped_red_green == ground, "a red-green swap is invisible here"
    swapped_red_blue = [ground[2], ground[1], ground[0]]
    assert swapped_red_blue != ground
    for name in ("LIST_BORDER", "LIST_TEXT", "INPUT_SURFACE", "INPUT_BORDER"):
        one = channels(getattr(surface, name))
        assert len(set(one)) == 3, (name, one)


# The pictures


def model_payload(spec_name):
    """The view model of one matrix, stamped."""
    one = SPECS[spec_name]
    tab = surface.RoutingTabState(**one["tab"])
    model = surface.QuickRoutingModel(tab, one["rate"])
    return sealed(
        surface.build_view_model(model, one["steps"], one["ticks"][0], one["ticks"][1])
    )


def image_painted_by_the_matrix(spec_name):
    """The picture the shipped Qt matrix paints."""
    from tests.qt_pixel import pin_text_rendering, render_widget

    one = SPECS[spec_name]
    tab = surface.RoutingTabState(**one["tab"])
    matrix = build_matrix(tab)
    swapped = swapped_world(tab)
    try:
        matrix.rebuild_scope(list(one["steps"][0][1]))
    finally:
        swapped.undo()
    tick_shipped(matrix, one["ticks"])
    pin_text_rendering(matrix)
    return render_widget(matrix, MATRIX_SIZE)


def tick_shipped(matrix, ticks):
    """Tick the named bots in the shipped matrix's two columns."""
    from PySide6.QtCore import Qt

    for column, wanted in zip((matrix._source_list, matrix._dest_list), ticks):
        for index in range(column.count()):
            entry = column.item(index)
            entry.setCheckState(
                Qt.Checked if entry.data(Qt.UserRole) in list(wanted) else Qt.Unchecked
            )


def image_painted_by_the_model(payload):
    """A picture drawn only from the view model, never from the matrix."""
    payload = unaltered(payload)
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )

    from tests.qt_pixel import pin_text_rendering, render_widget

    app()
    built = QWidget()
    outer = QVBoxLayout(built)
    outer.setContentsMargins(*payload["layout"]["outer_margins"])
    outer.setSpacing(payload["layout"]["outer_spacing"])
    col_row = QHBoxLayout()
    col_row.setSpacing(payload["layout"]["column_spacing"])
    col_row.setContentsMargins(*payload["layout"]["column_margins"])

    columns = []
    for column in payload["names"]["columns"]:
        listing = QListWidget()
        listing.setSelectionMode(
            getattr(QListWidget, payload["platform_values"]["selection_mode"])
        )
        listing.setSizePolicy(
            getattr(QSizePolicy, payload["styles"]["size_policy"]),
            getattr(QSizePolicy, payload["styles"]["size_policy"]),
        )
        listing.setVerticalScrollBarPolicy(
            getattr(Qt, payload["platform_values"]["scroll_policy"])
        )
        listing.setStyleSheet(payload["styles"]["list"])
        for row in payload["rows"][column]:
            entry = QListWidgetItem(row["label"])
            entry.setData(
                getattr(Qt, payload["platform_values"]["user_role"]), row["bot_id"]
            )
            entry.setCheckState(Qt.CheckState(row["check_state"]))
            listing.addItem(entry)
        columns.append(listing)

    col_row.addWidget(columns[0], stretch=payload["layout"]["column_stretch"])
    rate_zone = QFrame()
    rate_zone.setFrameShape(getattr(QFrame, payload["styles"]["frame_shape"]))
    rate_zone.setSizePolicy(
        getattr(QSizePolicy, payload["styles"]["size_policy"]),
        getattr(QSizePolicy, payload["styles"]["size_policy"]),
    )
    rate_zone.setStyleSheet(payload["styles"]["rate_zone"])
    rate_lay = QVBoxLayout(rate_zone)
    rate_lay.setContentsMargins(*payload["layout"]["rate_margins"])
    rate_label = QLabel(payload["texts"]["rate_label"])
    rate_label.setAlignment(
        Qt.AlignmentFlag(payload["platform_values"]["alignment_value"])
    )
    rate_label.setStyleSheet(payload["styles"]["rate_label"])
    rate_lay.addWidget(rate_label)
    rate_box = QLineEdit(payload["texts"]["default_rate"])
    rate_box.setAlignment(
        Qt.AlignmentFlag(payload["platform_values"]["alignment_value"])
    )
    rate_box.setStyleSheet(payload["styles"]["rate_input"])
    rate_lay.addWidget(rate_box)
    rate_lay.addStretch()
    col_row.addWidget(rate_zone, stretch=payload["layout"]["column_stretch"])
    col_row.addWidget(columns[1], stretch=payload["layout"]["column_stretch"])
    outer.addLayout(col_row, stretch=payload["layout"]["column_stretch"])

    btn_row = QHBoxLayout()
    btn_row.setSpacing(payload["layout"]["button_spacing"])
    btn_row.setContentsMargins(*payload["layout"]["button_margins"])
    btn_row.addStretch()
    for text in payload["texts"]["buttons"]:
        btn_row.addWidget(QPushButton(text))
    btn_row.addStretch()
    outer.addLayout(btn_row)

    pin_text_rendering(built)
    return render_widget(built, MATRIX_SIZE)


PICTURE_SPECS = (
    "tab_happy_three_bots",
    "tab_hidden_names",
    "ticks_every_bot_both_ways",
    "ticks_nothing_ticked",
)


@pytest.mark.parametrize("name", PICTURE_SPECS)
def test_the_two_sides_paint_one_matrix(name):
    """The surface painted a different matrix than the widget."""
    SPECS.setdefault(name, spec())
    picture_spec = dict(SPECS[name], steps=[[REBUILD, THREE_BOTS]])
    SPECS["picture_" + name] = picture_spec
    assert_pictures_match(
        old_side=image_painted_by_the_matrix("picture_" + name),
        new_side=image_painted_by_the_model(model_payload("picture_" + name)),
        note=name,
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture comparison passes whatever the surface painted."""
    SPECS["picture_a"] = dict(
        SPECS["tab_happy_three_bots"], steps=[[REBUILD, THREE_BOTS]]
    )
    SPECS["picture_b"] = dict(SPECS["tab_hidden_names"], steps=[[REBUILD, THREE_BOTS]])
    assert_pictures_differ(
        old_side=image_painted_by_the_matrix("picture_a"),
        new_side=image_painted_by_the_model(model_payload("picture_b")),
    )


def colours_in(image) -> set:
    """Every colour the render painted."""
    found = set()
    for y in range(image.height()):
        for x in range(image.width()):
            found.add(image.pixel(x, y))
    return found


def test_the_painted_matrix_shows_more_than_one_colour():
    """A matrix painting one colour cannot fail a picture check."""
    SPECS["picture_colours"] = dict(
        SPECS["tab_happy_three_bots"], steps=[[REBUILD, THREE_BOTS]]
    )
    found = colours_in(image_painted_by_the_matrix("picture_colours"))
    assert len(found) > 1, len(found)


def test_an_empty_matrix_is_compared_by_value_and_not_by_picture():
    """An empty matrix was trusted to a picture that cannot report."""
    SPECS["picture_empty"] = dict(SPECS["tab_happy_three_bots"], steps=[[REBUILD, []]])
    old = old_trace("picture_empty")
    new = new_trace("picture_empty")
    assert old["rows"] == new["rows"]
    assert old["rows"][surface.SOURCE_COLUMN] == []
    assert canonical(old) == canonical(new)


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload was painted, so the render measured the host."""
    SPECS["picture_seal"] = dict(
        SPECS["tab_happy_three_bots"], steps=[[REBUILD, THREE_BOTS]]
    )
    payload = model_payload("picture_seal")
    payload["texts"]["rate_label"] = "Ratio"
    with pytest.raises(AssertionError):
        image_painted_by_the_model(payload)


@skip_unless_no_fonts
def test_two_row_labels_of_equal_length_measure_the_same_width():
    """Every family is a box font here, so equal lengths must measure alike."""
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_two_row_labels_of_equal_length_measure_different_widths():
    """Glyphs decide their own width here, so the pair must separate."""
    assert app_font_advance_px(NARROW_LABEL) < app_font_advance_px(WIDE_LABEL)


# The values no picture carries


def test_the_questions_the_matrix_asks_are_read_off_both_sides():
    """A question one side puts differently reaches no pixel."""
    SPECS["asking"] = spec(steps="rebuild_then_connect", ticks="every_bot_both_ways")
    old = old_trace("asking")["tab"]["shown"]
    new = new_trace("asking")["tab"]["shown"]
    assert old == new, (old, new)
    asked = [one for one in old if one[0] == surface.TAB_ASK]
    assert len(asked) == 1, old
    assert asked[0][1] == "Create 6 Smart Wires?"


def test_the_wires_the_matrix_saves_are_read_off_both_sides():
    """A wire saved on one side only reaches no pixel."""
    SPECS["saving"] = spec(ticks="two_sources_one_destination")
    old = old_trace("saving")["tab"]["saved"]
    new = new_trace("saving")["tab"]["saved"]
    assert old == new, (old, new)
    assert old == [[[[ALPHA, GAMMA, 25.0], [BETA, GAMMA, 25.0]], []]]


def test_the_events_the_matrix_emits_are_read_off_both_sides():
    """A bus event one side skips reaches no pixel."""
    SPECS["emitting"] = spec(ticks="two_sources_one_destination")
    old = old_trace("emitting")["tab"]["emitted"]
    new = new_trace("emitting")["tab"]["emitted"]
    assert old == new, (old, new)
    assert [one[0] for one in old] == [surface.WIRE_CREATED] * 2


def test_the_scroll_positions_are_read_off_both_sides():
    """A scroll position one side loses reaches no pixel."""
    old = old_trace("scroll_both_columns_scrolled")
    new = new_trace("scroll_both_columns_scrolled")
    assert old["scroll"] == new["scroll"], (old["scroll"], new["scroll"])
    assert old["scroll"]["deferred"] == [
        [surface.SOURCE_COLUMN, 35],
        [surface.DEST_COLUMN, 12],
    ]
    assert old["deferred_delays"] == new["deferred_delays"] == [0, 0]


def test_a_column_that_was_not_scrolled_defers_nothing():
    """A column at the top was scrolled a second time for no reason."""
    old = old_trace("scroll_the_source_column_scrolled")
    new = new_trace("scroll_the_source_column_scrolled")
    assert old["scroll"]["deferred"] == new["scroll"]["deferred"]
    assert old["scroll"]["deferred"] == [[surface.SOURCE_COLUMN, 35]]
    assert old["deferred_delays"] == [0]


# The bridge


@pytest.fixture(autouse=True)
def restored_bridge_panel():
    """Put the panel the bridge keeps back after a test replaces it."""
    was = surface.MODEL
    yield
    surface.MODEL = was


BRIDGE_TAB = {
    "widget_symbols": {ALPHA: "BTC/USD"},
    "state_symbols": {BETA: "ETH/USD"},
    "cleared_pairs": [[ALPHA, BETA]],
}


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


def test_the_bridge_registers_the_quick_routing_method():
    """The renderer cannot reach the routing matrix over the bridge."""
    from src.core import desktop_bridge

    assert surface.METHOD in desktop_bridge.build_registry()
    assert surface.METHOD == "quick_routing.state"
    answer = bridge_answer(
        {
            "tab": BRIDGE_TAB,
            "steps": [[REBUILD, [ALPHA, BETA]]],
            "checked_sources": [ALPHA],
            "checked_destinations": [BETA],
        }
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["texts"]["rate_label"] == surface.RATE_LABEL_TEXT
    assert [row["label"] for row in result["rows"]["source"]] == [
        "BTC/USD [alpha-00]",
        "ETH/USD [beta-000]",
    ]


def test_the_bridge_builds_its_panel_on_the_first_request():
    """The panel was built while the module was imported."""
    surface.MODEL = None
    assert surface.MODEL is None
    built = surface.active_model()
    assert built is surface.MODEL
    assert surface.active_model() is built
    assert surface.active_model(fresh=True) is not built


def test_the_bridge_resets_the_panel_state_on_request():
    """The panel state the bridge keeps was never cleared."""
    filled = bridge_answer({"tab": BRIDGE_TAB, "steps": [[REBUILD, [ALPHA, BETA]]]})[
        "result"
    ]
    assert len(filled["rows"]["source"]) == 2
    kept = bridge_answer({})["result"]
    assert len(kept["rows"]["source"]) == 2
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["rows"]["source"] == []
    assert cleared["scope_ids"] == []


def test_the_bridge_reports_a_value_the_panel_refuses():
    """A value the panel refuses ended the session instead of answering."""
    answer = bridge_answer({"tab": BRIDGE_TAB, "steps": ["fly"]})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer(
        {
            "tab": BRIDGE_TAB,
            "rate": "40",
            "steps": [[REBUILD, [ALPHA, BETA]], CONNECT],
            "checked_sources": [ALPHA],
            "checked_destinations": [BETA],
        }
    )
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["stops"] == [REBUILD, surface.DONE]
    assert encoded["result"]["bus"]["topics"] == list(surface.BUS_TOPICS)


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'quick_routing.state', 'params':"
    " {'tab': {'widget_symbols': {'a': 'BTC/USD'}},"
    " 'steps': [['rebuild', ['a', 'b']]]}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def run_probe(prelude):
    done = subprocess.run(
        [sys.executable, "-"],
        input=(prelude + QT_PROBE).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the routing matrix pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["texts"]["connect"] == "Connect"
    assert len(result["rows"]["source"]) == 2


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_importing_the_surface_needs_no_qt_and_touches_nothing():
    """Importing the surface reached the platform or the world."""
    body = (
        "import sys, json;"
        "sys.modules['PySide6'] = None;"
        "from src.gui.main_tabs import quick_routing_surface as s;"
        "print(json.dumps({'model': s.MODEL is None,"
        " 'method': s.METHOD, 'qt': 'PySide6.QtWidgets' in sys.modules}))"
    )
    done = subprocess.run(
        [sys.executable, "-"],
        input=body.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    answered = json.loads(done.stdout.decode().splitlines()[-1])
    assert answered == {"model": True, "method": surface.METHOD, "qt": False}


def test_the_surface_source_reaches_no_file_no_clock_and_no_address():
    """The surface reached for a file, a clock or a network address."""
    tree = parsed(SURFACE_SOURCE)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("PySide6") for name in imported), imported
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    reached = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in (
        "read_text",
        "write_text",
        "mkdir",
        "urlopen",
        "create_connection",
        "socket",
        "now",
        "time",
        "monotonic",
    ):
        assert forbidden not in reached, forbidden
    text = SURFACE_SOURCE.read_text(encoding="utf-8")
    for forbidden in ("Path.home", "acervator_logs", "datetime", "webbrowser"):
        assert forbidden not in text, forbidden
    matrix_imports = {
        (node.module or "")
        for node in ast.walk(parsed(MATRIX_SOURCE))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in matrix_imports), matrix_imports


def test_no_test_here_opens_a_socket():
    """A test reached a network address."""
    real = socket.create_connection
    reached = []

    def refuse(*args, **_named):
        reached.append(args)
        raise AssertionError("this run tried to reach the network")

    socket.create_connection = refuse
    try:
        for name in ("tab_happy_three_bots", "steps_every_button_in_turn"):
            old_trace(name)
            new_trace(name)
    finally:
        socket.create_connection = real
    assert reached == [], reached
    with pytest.raises(AssertionError):
        refuse("a seeded call")
    assert len(reached) == 1
