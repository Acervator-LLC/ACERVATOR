"""The shipped main window and the Qt-free surface, side by side.

A failure means the view model carries a different window title, a
different smallest size, a different menu, a different tab set or tab
order, a different status-line pill, a different card value, a different
spendable payload, a different console-pause line, a different signals
gap marker, a different API-log block, a different indicator empty-state
cause, a different Extractor refusal, a different adopt summary, a
different confirmation, a different sound choice or a different pulse
value than ``src.gui.main_window`` produces.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from types import MethodType

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QTabWidget,
)

import src.gui.main_window as mw
from src.gui import design_system as ds
from src.gui.main_tabs import main_window_surface as surface
from tests.fixtures.host_fonts import load_run_fonts
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_PATH = REPO_ROOT / "src" / "gui" / "main_window.py"
SURFACE_PATH = REPO_ROOT / "src" / "gui" / "main_tabs" / "main_window_surface.py"
SHIPPED_SOURCE = SHIPPED_PATH.read_text(encoding="utf-8")
SURFACE_SOURCE = SURFACE_PATH.read_text(encoding="utf-8")

METHOD_NAME = "main_window.state"

PILL_SIZE = (300, 40)
CONTROL_RULE = "QLabel { background: #7d1a4a; border: 3px solid #14407d; }"

LONG_TEXT = "y" * 200
UNICODE_TEXT = "é中\U0001f600 café"
MARKUP_TEXT = "<b>bold</b> & <i>x</i>"
APOSTROPHE_TEXT = "it's the operator's bot"
NEWLINE_TEXT = "first\nsecond"
WRONG_CAPITALS_TEXT = "cOnSoLe"
THOUSAND_MILLION = 1_000_000_000
ONE_BILLIONTH = 1e-09
NOT_A_NUMBER = float("nan")
INFINITY = float("inf")
MINUS_INFINITY = float("-inf")
TWO_TO_1023 = 2**1023
TWO_TO_1024 = 2**1024
TEN_TO_400 = 10**400

_alive: list = []


@pytest.fixture(autouse=True, scope="module")
def app():
    """One application object for every render in this file."""
    load_run_fonts()
    return QApplication.instance() or QApplication([])


def hold(widget):
    """Keep `widget` alive for one drive, and let the drive release it."""
    _alive.append(widget)
    return widget


def release():
    """Drop every widget this file is holding.

    A child goes with its parent, so an object already gone is skipped
    rather than read: reaching a freed object raises instead of
    reporting, and an error in a large run reads as noise.
    """
    while _alive:
        try:
            _alive.pop().deleteLater()
        except RuntimeError:
            continue


def canonical(value):
    """`value` as nested lists of text, ordered so a swap changes it.

    Every leaf becomes its printed form with its type, so a whole number
    and a decimal of the same size are told apart and two
    not-a-numbers read alike.
    """
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: repr(item[0]))
        return [[repr(key), canonical(inner)] for key, inner in pairs]
    if isinstance(value, (list, tuple)):
        return [canonical(inner) for inner in value]
    return f"{type(value).__name__}:{value!r}"


def digest(value) -> str:
    """SHA-256 over one answer, ordered so a swap changes it."""
    return hashlib.sha256(repr(canonical(value)).encode("utf-8")).hexdigest()


def leaves(value, path=""):
    """Every leaf in `value`, keyed by where it sits."""
    found = {}
    if isinstance(value, dict):
        for key, inner in value.items():
            found.update(leaves(inner, f"{path}.{key!r}"))
    elif isinstance(value, (list, tuple)):
        for index, inner in enumerate(value):
            found.update(leaves(inner, f"{path}[{index}]"))
    else:
        found[path] = f"{type(value).__name__}:{value!r}"
    return found


# The process-wide names each side gets its own of


class BoxRecorder:
    """Stands in for the message boxes the window raises.

    Answers each question with whatever `answers` holds for it, so a
    confirmed and a declined path can both be driven. Every raised box
    is kept.
    """

    Ok = 1
    Cancel = 2
    Yes = 4
    No = 8

    def __init__(self, answer=None):
        self.answer = answer
        self.raised: list = []
        self.buttons: list = []
        self.before_question = None

    def _keep(self, kind, title, text, buttons):
        self.raised.append({"kind": kind, "title": title, "text": text})
        self.buttons.append(len(buttons))

    def question(self, _parent, title, text, *buttons):
        if self.before_question is not None:
            self.before_question()
        self._keep("question", title, text, buttons)
        return self.answer

    def warning(self, _parent, title, text, *buttons):
        self._keep("warning", title, text, buttons)

    def critical(self, _parent, title, text, *buttons):
        self._keep("critical", title, text, buttons)

    def information(self, _parent, title, text, *buttons):
        self._keep("information", title, text, buttons)

    def about(self, _parent, title, text, *buttons):
        self._keep("about", title, text, buttons)


class LoggerRecorder:
    """Stands in for the module logger, keeping what each level was told."""

    def __init__(self):
        self.records: list = []

    def _keep(self, level, message, *args):
        self.records.append({"level": level, "message": message, "args": args})

    def debug(self, message, *args, **named):
        self._keep("debug", message, *args)

    def info(self, message, *args, **named):
        self._keep("info", message, *args)

    def warning(self, message, *args, **named):
        self._keep("warning", message, *args)

    def error(self, message, *args, **named):
        self._keep("error", message, *args)

    def exception(self, message, *args, **named):
        self._keep("exception", message, *args)

    def crashes(self) -> list:
        """Every exception the window's own handler caught and logged."""
        return [
            record["args"][0]
            for record in self.records
            if record["level"] == "error" and record["args"]
        ]


class ApiLogRecorder:
    """Stands in for the API record the refusal path writes to."""

    def __init__(self):
        self.records: list = []

    def record(self, **named):
        self.records.append(dict(named))


class SwappedNames:
    """Give this drive its own of every process-wide name it touches.

    Every swapped name is put back on the way out, including after a
    refusal. `seen_during` records what each name held while the drive
    ran, so a swap that never took effect is reported rather than read
    as a pass.
    """

    def __init__(self, names):
        self.names = list(names)
        self.saved: list = []
        self.seen_during: dict = {}

    def __enter__(self):
        for owner, attribute, replacement in self.names:
            self.saved.append((owner, attribute, getattr(owner, attribute)))
            setattr(owner, attribute, replacement)
            short = owner.__name__.rsplit(".", 1)[-1]
            self.seen_during[f"{short}.{attribute}"] = getattr(owner, attribute)
        return self

    def __exit__(self, *raised):
        for owner, attribute, original in reversed(self.saved):
            setattr(owner, attribute, original)
        return False

    def restored(self) -> bool:
        """Whether every swapped name holds what it held before."""
        return all(
            getattr(owner, attribute) is original
            for owner, attribute, original in self.saved
        )


# The stand-ins the shipped window is driven against


class LogSink:
    """Stands in for the activity log the window writes lines to."""

    def __init__(self):
        self.lines: list = []

    def log(self, text, level="info"):
        self.lines.append({"text": text, "level": level})


class SpoolSink:
    """Stands in for the notification spool."""

    def __init__(self):
        self.lines: list = []

    def notify(self, text, level="info"):
        self.lines.append({"text": text, "level": level})


class CardSink:
    """Stands in for one stat card, keeping every value written to it."""

    def __init__(self):
        self.values: list = []

    def set_value(self, text):
        self.values.append(text)

    def latest(self):
        return self.values[-1] if self.values else None


class SpendableSink:
    """Stands in for the spendable panel."""

    def __init__(self):
        self.payloads: list = []

    def update_profits(self, payload):
        self.payloads.append(dict(payload))


class VizSink:
    """Stands in for the Bot Swarm view the tick feeds."""

    def __init__(self):
        self.updates: list = []

    def update_bots(self, statuses):
        self.updates.append(list(statuses))


class PanelSink:
    """Stands in for the indicator panel the tick feeds."""

    def __init__(self):
        self.selected_bot_id = None
        self.bot_lists: list = []
        self.no_data: list = []

    def update_bot_list(self, statuses):
        self.bot_lists.append(list(statuses))

    def show_no_data(self, **named):
        self.no_data.append(dict(named))


class LabelSink:
    """Stands in for one status-line label."""

    def __init__(self):
        self.texts: list = []
        self.styles: list = []
        self.tooltips: list = []

    def setText(self, text):
        self.texts.append(text)

    def setStyleSheet(self, style):
        self.styles.append(style)

    def setToolTip(self, text):
        self.tooltips.append(text)

    def latest_text(self):
        return self.texts[-1] if self.texts else None

    def latest_style(self):
        return self.styles[-1] if self.styles else None


class HandlerSink:
    """Stands in for the console log handler the Pause button drives."""

    def __init__(self, held=0, cap=0, dropped=0):
        self._paused = False
        self._buffer_max = cap
        self._buffer_dropped = dropped
        self._held = held

    def buffered_count(self):
        return self._held

    def set_paused(self, paused):
        self._paused = paused


class FleetStub:
    """Stands in for the bot manager the window reads its totals from."""

    def __init__(self, aggregate=None, statuses=None, parent=None, candidates=None):
        self.aggregate = aggregate if aggregate is not None else {}
        self.statuses = list(statuses or [])
        self.parent = parent
        self.candidates = list(candidates or [])
        self.unregistered: list = []
        self._live_monitor = None

    def get_aggregate_stats(self):
        return self.aggregate

    def list_bots(self):
        return self.statuses

    def list_bots_by_exchange(self, exchange_id):
        return [one for one in self.statuses if one.get("exchange") == exchange_id]

    def find_parent_bot_for_base_currency(self, base_currency, exchange_id=""):
        return self.parent

    def list_parent_bot_candidates_for_base_currency(
        self, base_currency, exchange_id=""
    ):
        return self.candidates

    def unregister(self, bot_id):
        self.unregistered.append(bot_id)


class SettingsStub:
    """Stands in for the settings store the window reads."""

    def __init__(self, values=None, reset_raises=None):
        self.values = dict(values or {})
        self.reset_raises = reset_raises
        self.reset_count = 0

    def get(self, key, default=None):
        return self.values.get(key, default)

    def reset_defaults(self):
        if self.reset_raises is not None:
            raise self.reset_raises
        self.reset_count += 1


class LoadMonitorStub:
    """Stands in for the API-load monitor the pill reads."""

    def __init__(self, samples=None, safety_pct=0.75):
        self.samples = dict(samples or {})
        self.safety_pct = safety_pct

    def sample(self, exchange_id):
        return self.samples[exchange_id]


class Window(QMainWindow):
    """A real window carrying only the members the driven methods read."""

    def __init__(self) -> None:
        super().__init__()
        self.setAccessibleName("Main Window Parity Host")


class Plain:
    """A holder for the methods that read no Qt member off their window.

    `parent` answers with whatever was handed in, which is the seam the
    theme switch resolves its application object through.
    """

    def __init__(self, parent=None):
        self._parent = parent

    def parent(self):
        """The object the theme switch applies a style sheet to."""
        return self._parent


class StyleSink:
    """Stands in for the application object a theme is applied to."""

    def __init__(self):
        self.sheets: list = []

    def setStyleSheet(self, sheet):
        self.sheets.append(sheet)


class StatusBarSink:
    """Stands in for the status bar the window builds and fills."""

    def __init__(self):
        self.messages: list = []
        self.permanent: list = []

    def showMessage(self, text):
        self.messages.append(text)

    def addPermanentWidget(self, widget):
        self.permanent.append(widget)


def furnish(window, named):
    """Give `window` the stand-ins one drive needs, and nothing else."""
    window._status_log = LogSink()
    window._spool = SpoolSink()
    window._stat_scrummed = CardSink()
    window._stat_folded = CardSink()
    window._stat_pnl = CardSink()
    window._stat_trades = CardSink()
    window._stat_bots = CardSink()
    window._stat_errors = CardSink()
    window._spendable_widget = SpendableSink()
    window._bot_viz = VizSink()
    window._indicator_panel = PanelSink()
    window._api_load_label = LabelSink()
    window._ai_monitor_label = LabelSink()
    window._console_pause_indicator = LabelSink()
    window._exchange_tabs = {}
    window._exchange_connectors = {}
    window._bot_manager = None
    window._settings = None
    window._risk_manager = None
    window._analytics = None
    window._crash_recovery = None
    window._notif_manager = None
    window._journal = None
    window._recon_engine = None
    window._analytics_tab = None
    window._risk_tab = None
    window._journal_tab = None
    window._alerts_tab = None
    window._ivp_snapshot_dir_wired = True
    window._last_tab_refresh = float("inf")
    window._console_log_handler = None
    window._wire_ivp_snapshot_dir = lambda: None
    for key, value in named.items():
        setattr(window, key, value)
    return window


def shipped_window(**named):
    """A plain holder for every drive that reads no Qt member off its window.

    A real ``QMainWindow`` per drive costs a live C++ object this file
    cannot free without an event loop, and none of these drives asks its
    window for a Qt service.
    """
    return furnish(Plain(named.pop("parent", None)), named)


def qt_window(**named):
    """A real window, for the drives that ask it for a Qt service.

    ``_setup_menu`` asks for a menu bar, the three timer builders parent a
    ``QTimer`` to it, and the tooltip scan walks its children.
    """
    return furnish(hold(Window()), named)


def driven(window, name):
    """One shipped method as a plain callable bound to `window`."""
    return MethodType(mw.MainWindow.__dict__[name], window)


# The cases both sides are driven with


def aggregate(**named):
    """One aggregate reading, with the shipped defaults for everything unsaid."""
    reading = {
        "total_scrummed_usd": 1234.5,
        "total_folded_usd": 987.25,
        "total_realised_pnl": 12.3456,
        "total_trades": 42,
        "running": 7,
        "total_errors_lifetime": 3,
        "wallet_cash_usd": 500.0,
        "crypto_position_value_usd": 2500.0,
    }
    reading.update(named)
    return reading


AGGREGATE_CASES = {
    "happy": aggregate(),
    "empty": {
        "total_realised_pnl": 0.0,
        "total_trades": 0,
        "running": 0,
    },
    "zero": aggregate(
        total_scrummed_usd=0.0,
        total_folded_usd=0.0,
        total_realised_pnl=0.0,
        total_trades=0,
        running=0,
        total_errors_lifetime=0,
        wallet_cash_usd=0.0,
        crypto_position_value_usd=0.0,
    ),
    "negative": aggregate(
        total_scrummed_usd=-1.5,
        total_folded_usd=-2.5,
        total_realised_pnl=-3.5,
        total_trades=-1,
        running=-1,
        total_errors_lifetime=-1,
        wallet_cash_usd=-10.0,
        crypto_position_value_usd=-20.0,
    ),
    "thousand_million": aggregate(total_scrummed_usd=THOUSAND_MILLION),
    "one_billionth": aggregate(total_scrummed_usd=ONE_BILLIONTH),
    "whole_number_pnl": aggregate(total_realised_pnl=12),
    "decimal_pnl": aggregate(total_realised_pnl=12.0),
    "infinity": aggregate(total_scrummed_usd=INFINITY),
    "minus_infinity": aggregate(total_scrummed_usd=MINUS_INFINITY),
    "not_a_number": aggregate(total_scrummed_usd=NOT_A_NUMBER),
    "true_where_a_number_belongs": aggregate(total_scrummed_usd=True),
    "text_where_a_number_belongs": aggregate(total_scrummed_usd="12.7"),
    "number_as_text_trades": aggregate(total_trades="42"),
    "unicode_trades": aggregate(total_trades=UNICODE_TEXT),
    "two_hundred_characters": aggregate(total_trades=LONG_TEXT),
    "markup_trades": aggregate(total_trades=MARKUP_TEXT),
    "apostrophe_trades": aggregate(total_trades=APOSTROPHE_TEXT),
    "newline_trades": aggregate(total_trades=NEWLINE_TEXT),
    "wrong_capitals_trades": aggregate(total_trades=WRONG_CAPITALS_TEXT),
    "two_to_1023": aggregate(total_scrummed_usd=TWO_TO_1023),
    "not_a_number_cash": aggregate(wallet_cash_usd=NOT_A_NUMBER),
    "true_cash": aggregate(wallet_cash_usd=True),
    "text_cash": aggregate(wallet_cash_usd="12.7"),
}

REFUSING_AGGREGATE_CASES = {
    "no_pnl_key": {"total_trades": 1, "running": 1},
    "text_pnl": aggregate(total_realised_pnl="12.7"),
    "two_to_1024": aggregate(total_scrummed_usd=TWO_TO_1024),
    "ten_to_400": aggregate(total_scrummed_usd=TEN_TO_400),
    "ten_to_400_cash": aggregate(wallet_cash_usd=TEN_TO_400),
    "text_scrummed_not_a_number": aggregate(total_scrummed_usd="not a number"),
    "aggregate_is_not_a_mapping": None,
}


# One tick, driven through both sides


def shipped_tick(reading):
    """One dashboard tick on the shipped window. Returns what it wrote."""
    boxes = BoxRecorder()
    log = LoggerRecorder()
    window = shipped_window(_bot_manager=FleetStub(aggregate=reading, statuses=[]))
    with SwappedNames([(mw, "QMessageBox", boxes), (mw, "logger", log)]) as swapped:
        driven(window, "_refresh_dashboard")()
        during = swapped.seen_during["main_window.logger"] is log
    written = {
        "cards": {
            "scrummed": window._stat_scrummed.latest(),
            "folded": window._stat_folded.latest(),
            "pnl": window._stat_pnl.latest(),
            "trades": window._stat_trades.latest(),
            "bots": window._stat_bots.latest(),
            "errors": window._stat_errors.latest(),
        },
        "spendable": (
            window._spendable_widget.payloads[-1]
            if window._spendable_widget.payloads
            else None
        ),
        "tick_error": (type(log.crashes()[0]).__name__ if log.crashes() else None),
        "swap_seen": during,
        "swap_restored": swapped.restored(),
    }
    release()
    return written


def surface_tick(reading):
    """One dashboard tick on the surface. Returns what it wrote."""
    model = surface.MainWindowModel(
        fleet=surface.FleetSource(aggregate=reading, statuses=[]),
        exchange_tab_ids=[],
    )
    model.refresh()
    cards = {name: model.card_values.get(name) for name in surface.CARD_ORDER}
    return {
        "cards": cards,
        "spendable": model.spendable,
        "tick_error": model.tick_error,
        "swap_seen": True,
        "swap_restored": True,
    }


ALL_TICK_CASES = dict(AGGREGATE_CASES)
ALL_TICK_CASES.update(REFUSING_AGGREGATE_CASES)


@pytest.mark.parametrize("name", sorted(ALL_TICK_CASES))
def test_one_tick_writes_the_same_cards_on_both_sides(name):
    """The surface wrote a different card, panel or refusal than the tick."""
    reading = ALL_TICK_CASES[name]
    old_side = shipped_tick(reading)
    new_side = surface_tick(reading)
    old_leaves = leaves(old_side)
    new_leaves = leaves(new_side)
    assert old_leaves == new_leaves, (
        f"{name}: the two sides differ at "
        f"{sorted(set(old_leaves.items()) ^ set(new_leaves.items()))}"
    )
    assert digest(old_side) == digest(new_side), name


def test_two_different_readings_are_told_apart_by_the_tick_comparison():
    """The tick comparison passes whatever the surface wrote."""
    one = shipped_tick(AGGREGATE_CASES["happy"])
    other = surface_tick(AGGREGATE_CASES["zero"])
    assert digest(one) != digest(other)


def test_the_other_direction_is_told_apart_too():
    """The tick comparison reports one way round and not the other."""
    one = surface_tick(AGGREGATE_CASES["happy"])
    other = shipped_tick(AGGREGATE_CASES["zero"])
    assert digest(one) != digest(other)


def test_the_same_reading_twice_gives_one_answer():
    """The tick answer moved between two runs of one reading."""
    first_drive = shipped_tick(AGGREGATE_CASES["happy"])
    second_drive = shipped_tick(AGGREGATE_CASES["happy"])
    assert digest(first_drive) == digest(second_drive)


def test_a_whole_number_and_a_decimal_are_told_apart():
    """`12` and `12.0` read alike, so a type change reaches no check."""
    whole = surface_tick(AGGREGATE_CASES["whole_number_pnl"])
    decimal = surface_tick(AGGREGATE_CASES["decimal_pnl"])
    assert whole["cards"]["pnl"] == decimal["cards"]["pnl"]
    assert digest(AGGREGATE_CASES["whole_number_pnl"]) != digest(
        AGGREGATE_CASES["decimal_pnl"]
    )


def test_two_not_a_numbers_read_alike():
    """Two not-a-numbers read as a difference that is not one.

    A plain comparison of two not-a-numbers answers "different", so the
    printed form is what the answer comparison reads.
    """
    first = surface_tick(aggregate(total_scrummed_usd=float("nan")))
    second = surface_tick(aggregate(total_scrummed_usd=float("nan")))
    assert digest(first) == digest(second)
    plain = [one == other for one, other in ((NOT_A_NUMBER, float("nan")),)]
    assert plain == [False]
    assert canonical(NOT_A_NUMBER) == canonical(float("nan"))


def tick_error_records(reading):
    """Every error the shipped tick's own handlers logged for one reading."""
    log = LoggerRecorder()
    window = shipped_window(_bot_manager=FleetStub(aggregate=reading, statuses=[]))
    with SwappedNames([(mw, "logger", log)]):
        driven(window, "_refresh_dashboard")()
    release()
    return [type(one).__name__ for one in log.crashes()]


def test_a_clean_tick_logs_no_error_at_all():
    """A handler inside the tick logs on a clean reading.

    The refusal reader takes the exception the tick's handlers logged.
    The tick has handlers inside it as well as the one around it, so a
    clean drive that logs nothing is what makes the reader's answer the
    outer refusal rather than an inner one.
    """
    assert tick_error_records(AGGREGATE_CASES["happy"]) == []
    assert tick_error_records(AGGREGATE_CASES["zero"]) == []


def test_the_refusal_reader_reports_a_reading_that_stops_the_tick():
    """The refusal reader reads nothing whatever the tick did."""
    assert tick_error_records(REFUSING_AGGREGATE_CASES["no_pnl_key"]) == ["KeyError"]
    assert tick_error_records(REFUSING_AGGREGATE_CASES["ten_to_400"]) == [
        "OverflowError"
    ]


TICK_STEPS = ("scrummed", "folded", "pnl", "trades", "bots", "errors", "spendable")


def tick_step_trace(reading):
    """Which step of the tick each side reached, and how it stopped."""
    old_side = shipped_tick(reading)
    new_side = surface_tick(reading)
    written = [
        name for name in surface.CARD_ORDER if old_side["cards"].get(name) is not None
    ]
    reached = len(written) + (1 if old_side["spendable"] is not None else 0)
    return {
        "step_index": reached,
        "step_name": TICK_STEPS[reached] if reached < len(TICK_STEPS) else "done",
        "refusal": old_side["tick_error"],
        "kept": {name: old_side["cards"][name] for name in written},
        "surface_kept": {
            name: new_side["cards"][name]
            for name in written
            if new_side["cards"].get(name) is not None
        },
    }


@pytest.mark.parametrize("name", sorted(REFUSING_AGGREGATE_CASES))
def test_a_tick_that_refuses_part_way_keeps_what_it_wrote_before(name):
    """A refusal part way through the tick lost a card already written."""
    traced = tick_step_trace(REFUSING_AGGREGATE_CASES[name])
    assert traced["refusal"] is not None, (
        f"{name}: the reading was expected to stop the tick, "
        f"but it reached step {traced['step_index']} ({traced['step_name']})"
    )
    assert traced["kept"] == traced["surface_kept"], (
        f"{name}: stopped at step {traced['step_index']} "
        f"({traced['step_name']}) with {traced['refusal']}; "
        f"shipped kept {traced['kept']}, surface kept {traced['surface_kept']}"
    )


def test_a_surviving_card_matches_the_clean_build_of_that_card():
    """A card written before a refusal carries a value no clean tick wrote.

    Comparing the two sides alone cannot report a card both sides
    compute wrongly, so each surviving card is read against the value a
    clean reading of the same number produces.
    """
    reading = REFUSING_AGGREGATE_CASES["no_pnl_key"]
    traced = tick_step_trace(reading)
    clean = surface_tick(aggregate(total_scrummed_usd=0.0, total_folded_usd=0.0))
    for name, value in traced["kept"].items():
        assert value == clean["cards"][name], (
            f"{name}: kept {value!r} where a clean tick of the same "
            f"numbers writes {clean['cards'][name]!r}"
        )


def test_the_swap_was_in_place_during_the_drive_and_put_back_after():
    """A process-wide name was not swapped, or was left swapped."""
    written = shipped_tick(AGGREGATE_CASES["happy"])
    assert written["swap_seen"] is True
    assert written["swap_restored"] is True
    assert mw.logger.name == "acervator.gui"


def test_the_swap_is_put_back_after_a_refusal_too():
    """A refusal mid-drive left a process-wide name swapped."""
    boxes = BoxRecorder()
    swapped = SwappedNames([(mw, "QMessageBox", boxes)])
    with pytest.raises(RuntimeError):
        with swapped:
            raise RuntimeError("the drive refused part way")
    assert swapped.restored() is True
    assert mw.QMessageBox is not boxes


# The window's chrome


def test_the_two_sides_carry_one_window_title():
    """The surface names the window differently than the shipped window."""
    window = hold(Window())
    window.setWindowTitle("Acervator v" + mw.__version__ + "")
    assert window.windowTitle() == surface.window_title(mw.__version__)
    release()


def test_the_two_sides_carry_one_smallest_size():
    """The surface allows a different smallest window than the shipped one."""
    window = hold(Window())
    window.setMinimumSize(1400, 900)
    assert (window.minimumWidth(), window.minimumHeight()) == (
        surface.MINIMUM_WIDTH_PX,
        surface.MINIMUM_HEIGHT_PX,
    )
    release()


def shipped_menu_titles():
    """The four menus the shipped window builds, read off a real menu bar."""
    chosen: list = []
    window = qt_window()
    window._open_settings = lambda: chosen.append("settings")
    window._reset_settings = lambda: chosen.append("reset")
    window._add_exchange = lambda: chosen.append("add exchange")
    window._switch_theme = lambda name: chosen.append(name)
    window._show_about = lambda: chosen.append("about")
    driven(window, "_setup_menu")()
    menus = []
    for action in window.menuBar().actions():
        menu = action.menu()
        items = []
        for item in menu.actions():
            items.append(surface.MENU_SEPARATOR if item.isSeparator() else item.text())
        menus.append({"title": action.text(), "items": items})
    release()
    return menus


def test_the_two_sides_build_one_menu():
    """The surface builds a different menu than the shipped window."""
    from src.gui.theme_engine import THEMES

    themes = [(name, tokens.display_name) for name, tokens in THEMES.items()]
    assert digest(shipped_menu_titles()) == digest(surface.menu_model(themes))


def test_the_menu_comparison_reports_a_missing_item():
    """The menu comparison passes whatever the surface builds."""
    from src.gui.theme_engine import THEMES

    themes = [(name, tokens.display_name) for name, tokens in THEMES.items()]
    thinned = surface.menu_model(themes)
    thinned[0]["items"] = thinned[0]["items"][:-1]
    assert digest(shipped_menu_titles()) != digest(thinned)


TAB_ORDER_CASES = {
    "shipped_build_order": list(surface.BUILT_TAB_ORDER),
    "already_canonical": list(surface.CANONICAL_TAB_ORDER),
    "reversed": list(reversed(surface.CANONICAL_TAB_ORDER)),
    "no_tabs": [],
    "one_tab": ["Trading"],
    "a_tab_the_order_does_not_name": list(surface.BUILT_TAB_ORDER) + ["Paper Trader"],
    "a_tab_that_failed_to_build": [
        name for name in surface.BUILT_TAB_ORDER if name != "History"
    ],
    "two_tabs_share_a_name": ["Trading", "Trading", "Console"],
    "unicode_tab": [UNICODE_TEXT] + list(surface.BUILT_TAB_ORDER),
}


@pytest.mark.parametrize("name", sorted(TAB_ORDER_CASES))
def test_the_two_sides_order_the_tabs_the_same_way(name):
    """The surface puts the tabs in a different order than the reorder pass."""
    labels = TAB_ORDER_CASES[name]
    tabs = hold(QTabWidget())
    for label in labels:
        tabs.addTab(hold(QLabel(str(label))), label)
    window = shipped_window(_main_tabs=tabs)
    driven(window, "_reorder_main_tabs")(list(surface.CANONICAL_TAB_ORDER))
    old_side = [tabs.tabText(index) for index in range(tabs.count())]
    new_side = surface.reordered_tabs(labels, surface.CANONICAL_TAB_ORDER)
    assert old_side == new_side, name
    release()


def test_the_tab_order_comparison_reports_a_swap():
    """The tab-order comparison passes whatever order the surface produces."""
    ordered = surface.reordered_tabs(
        surface.BUILT_TAB_ORDER, surface.CANONICAL_TAB_ORDER
    )
    swapped = list(ordered)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert ordered != swapped


HEADER_STRIP_CASES = [
    "Trading",
    "Simulator",
    "Paper Trader",
    "Console",
    "",
    UNICODE_TEXT,
    LONG_TEXT,
    NEWLINE_TEXT,
    "simulator",
]


class ContainerSink:
    """Stands in for the header strip, keeping what it was told to show."""

    def __init__(self):
        self.shown: list = []

    def setVisible(self, visible):
        self.shown.append(visible)


@pytest.mark.parametrize("tab_name", HEADER_STRIP_CASES)
def test_the_two_sides_hide_the_header_strip_on_one_set_of_tabs(tab_name):
    """The surface shows the stat strip on a tab the window hides it on."""
    tabs = hold(QTabWidget())
    tabs.addTab(hold(QLabel("t")), tab_name)
    container = ContainerSink()
    window = shipped_window(
        _main_tabs=tabs, _header_strip_container=container, _history_tab=None
    )
    driven(window, "_on_main_tab_changed")(0)
    assert container.shown == [surface.header_strip_visible(tab_name)]
    release()


def test_the_header_strip_check_reports_both_answers():
    """The strip check reads one answer whatever the tab is called."""
    assert surface.header_strip_visible("Trading") is True
    assert surface.header_strip_visible("Simulator") is False


# The status line


class Sample:
    """One API-load reading, as the monitor answers with it."""

    def __init__(self, exchange, calls_per_minute, ceiling_cpm, load_score):
        self.exchange = exchange
        self.calls_per_minute = calls_per_minute
        self.ceiling_cpm = ceiling_cpm
        self.load_score = load_score


PILL_CASES = {
    "green": Sample("coinbase", 12.0, 100.0, 0.12),
    "amber": Sample("coinbase", 60.0, 100.0, 0.6),
    "red": Sample("coinbase", 90.0, 100.0, 0.9),
    "exactly_the_amber_edge": Sample("coinbase", 50.0, 100.0, 0.5),
    "exactly_the_red_edge": Sample("coinbase", 75.0, 100.0, 0.75),
    "zero": Sample("coinbase", 0.0, 0.0, 0.0),
    "negative": Sample("coinbase", -1.0, -1.0, -0.5),
    "thousand_million": Sample("coinbase", THOUSAND_MILLION, THOUSAND_MILLION, 0.1),
    "one_billionth": Sample("coinbase", ONE_BILLIONTH, ONE_BILLIONTH, ONE_BILLIONTH),
    "unicode_name": Sample(UNICODE_TEXT, 1.0, 2.0, 0.1),
    "two_hundred_characters": Sample(LONG_TEXT, 1.0, 2.0, 0.1),
    "markup_name": Sample(MARKUP_TEXT, 1.0, 2.0, 0.1),
    "apostrophe_name": Sample(APOSTROPHE_TEXT, 1.0, 2.0, 0.1),
    "newline_name": Sample(NEWLINE_TEXT, 1.0, 2.0, 0.1),
    "wrong_capitals_name": Sample(WRONG_CAPITALS_TEXT, 1.0, 2.0, 0.1),
    "true_where_a_number_belongs": Sample("coinbase", True, True, 0.1),
    "whole_number_calls": Sample("coinbase", 12, 100, 0.12),
}

REFUSING_PILL_CASES = {
    "not_a_number_score": Sample("coinbase", 1.0, 2.0, NOT_A_NUMBER),
    "infinity_score": Sample("coinbase", 1.0, 2.0, INFINITY),
    "minus_infinity_score": Sample("coinbase", 1.0, 2.0, MINUS_INFINITY),
    "text_where_a_number_belongs": Sample("coinbase", "12.7", "100", 0.1),
    "not_a_number_calls": Sample("coinbase", NOT_A_NUMBER, 2.0, 0.1),
    "two_to_1024_score": Sample("coinbase", 1.0, 2.0, TWO_TO_1024),
}


def shipped_pill(sample):
    """The status-line pill the shipped window writes for one reading."""
    from src.exchange import api_load_monitor

    log = LoggerRecorder()
    monitor = LoadMonitorStub({"coinbase": sample})
    window = shipped_window(_exchange_connectors={"coinbase": object()})
    with SwappedNames(
        [
            (api_load_monitor, "get_load_monitor", lambda: monitor),
            (mw, "logger", log),
        ]
    ) as swapped:
        driven(window, "_refresh_api_load_pill")()
        during = swapped.seen_during["api_load_monitor.get_load_monitor"]() is monitor
    written = {
        "text": window._api_load_label.latest_text(),
        "style": window._api_load_label.latest_style(),
        "refused": bool(log.records),
        "swap_seen": during,
        "swap_restored": swapped.restored(),
    }
    release()
    return written


def surface_pill(sample):
    """The status-line pill the surface writes for one reading."""
    model = surface.MainWindowModel(
        load_monitor=surface.LoadMonitorSource({"coinbase": sample}, safety_pct=0.75),
        connector_ids=["coinbase"],
    )
    try:
        model.refresh_api_pill()
        refused = False
    except Exception:
        refused = True
    return {
        "text": model.api_pill_text or None,
        "style": model.api_pill_style or None,
        "refused": refused,
        "swap_seen": True,
        "swap_restored": True,
    }


@pytest.mark.parametrize("name", sorted(PILL_CASES))
def test_the_two_sides_write_one_api_load_pill(name):
    """The surface wrote a different pill than the status line."""
    old_side = shipped_pill(PILL_CASES[name])
    new_side = surface_pill(PILL_CASES[name])
    assert old_side["text"] == new_side["text"], name
    assert old_side["style"] == new_side["style"], name
    assert digest(old_side) == digest(new_side), name


@pytest.mark.parametrize("name", sorted(REFUSING_PILL_CASES))
def test_a_pill_reading_that_refuses_refuses_on_both_sides(name):
    """One side accepted a reading the other refused."""
    old_side = shipped_pill(REFUSING_PILL_CASES[name])
    new_side = surface_pill(REFUSING_PILL_CASES[name])
    assert old_side["refused"] == new_side["refused"], (
        f"{name}: shipped refused {old_side['refused']}, "
        f"surface refused {new_side['refused']}"
    )


def test_the_pill_with_no_connector_reads_the_idle_text():
    """The surface shows a pill where the window shows nothing connected."""
    window = shipped_window()
    from src.exchange import api_load_monitor

    with SwappedNames(
        [(api_load_monitor, "get_load_monitor", lambda: LoadMonitorStub())]
    ):
        driven(window, "_refresh_api_load_pill")()
    idle = surface.api_pill_idle()
    assert window._api_load_label.latest_text() == idle["text"]
    assert window._api_load_label.latest_style() == idle["style"]
    release()


def test_the_pill_comparison_reports_two_different_real_readings():
    """The pill comparison passes whatever text the surface wrote."""
    assert_pill_differs = (
        shipped_pill(PILL_CASES["green"])["text"]
        != surface_pill(PILL_CASES["red"])["text"]
    )
    assert assert_pill_differs


AI_CASES = {
    "off": {},
    "enabled_without_key": {"enabled": True},
    "key_without_enabled": {"api_key": "abc"},
    "ready": {"enabled": True, "api_key": "abc"},
    "empty_key": {"enabled": True, "api_key": ""},
    "true_key": {"enabled": True, "api_key": True},
    "zero_enabled": {"enabled": 0, "api_key": "abc"},
    "unicode_key": {"enabled": True, "api_key": UNICODE_TEXT},
}


def shipped_status_bar(ai_config):
    """What the shipped status-bar build writes, read off recorders.

    `QLabel` and `QStatusBar` are swapped for recorders for the length
    of the drive, so every text and every style rule is read from what
    the window WROTE rather than off a live Qt object.
    """
    made: list = []
    bar = StatusBarSink()
    holder = shipped_window(_settings=SettingsStub({"ai_monitor": ai_config}))
    holder.setStatusBar = bar.messages.append
    with SwappedNames(
        [
            (mw, "QLabel", lambda text="": _made_label(made, text)),
            (mw, "QStatusBar", lambda: bar),
        ]
    ) as swapped:
        driven(holder, "_setup_status_bar")()
    assert swapped.restored() is True
    return {
        "status_message": bar.messages[0] if bar.messages else None,
        "api_text": holder._api_load_label.latest_text(),
        "api_style": holder._api_load_label.latest_style(),
        "api_tooltip": (
            holder._api_load_label.tooltips[-1]
            if holder._api_load_label.tooltips
            else None
        ),
        "ai_text": holder._ai_monitor_label.latest_text(),
        "ai_style": holder._ai_monitor_label.latest_style(),
        "permanent": len(bar.permanent),
    }


def _made_label(made, text):
    """One recorder standing in for a status-line label the window builds."""
    label = LabelSink()
    label.setText(text)
    made.append(label)
    return label


@pytest.mark.parametrize("name", sorted(AI_CASES))
def test_the_two_sides_write_one_ai_monitor_pill(name):
    """The surface wrote a different AI pill than the status line."""
    old_side = shipped_status_bar(AI_CASES[name])
    new_side = surface.ai_pill(AI_CASES[name])
    idle = surface.api_pill_idle()
    assert old_side["status_message"] == surface.STATUS_READY_TEXT
    assert old_side["api_text"] == idle["text"], name
    assert old_side["api_style"] == idle["style"], name
    assert old_side["api_tooltip"] == surface.API_PILL_TOOLTIP, name
    assert old_side["ai_text"] == new_side["text"], name
    assert old_side["ai_style"] == new_side["style"], name
    assert old_side["permanent"] == 2, name
    release()


def test_the_ai_pill_check_reports_both_answers():
    """The AI pill check reads one answer whatever the settings hold."""
    assert surface.ai_pill({})["text"] == surface.AI_OFF_TEXT
    assert (
        surface.ai_pill({"enabled": True, "api_key": "a"})["text"]
        == surface.AI_READY_TEXT
    )


# The console pause line


CONSOLE_CASES = {
    "none_buffered": (0, 500, 0),
    "some_buffered": (12, 500, 0),
    "some_dropped": (500, 500, 37),
    "one_dropped": (1, 1, 1),
    "negative_dropped": (1, 1, -1),
    "zero_cap": (0, 0, 0),
    "thousand_million": (THOUSAND_MILLION, THOUSAND_MILLION, THOUSAND_MILLION),
    "true_held": (True, 1, 0),
    "decimal_held": (12.7, 500, 0),
    "text_held": ("12.7", 500, 0),
    "not_a_number_dropped": (1, 1, NOT_A_NUMBER),
    "infinity_dropped": (1, 1, INFINITY),
    "minus_infinity_dropped": (1, 1, MINUS_INFINITY),
    "two_to_1024_held": (TWO_TO_1024, 1, 0),
}


@pytest.mark.parametrize("name", sorted(CONSOLE_CASES))
def test_the_two_sides_write_one_buffered_console_line(name):
    """The surface wrote a different paused line than the console tab."""
    held, cap, dropped = CONSOLE_CASES[name]
    handler = HandlerSink(held=held, cap=cap, dropped=dropped)
    handler._paused = True
    window = shipped_window(_console_log_handler=handler)
    driven(window, "_refresh_console_pause_indicator")()
    old_side = window._console_pause_indicator.latest_text()
    new_side = surface.console_buffered_text(held, cap, dropped)
    assert old_side == new_side, name
    release()


def test_the_console_line_is_not_written_while_the_console_runs():
    """The paused line is written when nothing is paused."""
    handler = HandlerSink(held=5, cap=10, dropped=0)
    window = shipped_window(_console_log_handler=handler)
    driven(window, "_refresh_console_pause_indicator")()
    assert window._console_pause_indicator.texts == []
    model = surface.MainWindowModel(
        console_handler=surface.ConsoleHandlerSource(5, 10, 0)
    )
    model.refresh_console_indicator()
    assert model.console_indicator == surface.CONSOLE_RUNNING_INDICATOR
    release()


def test_the_console_line_check_reports_the_dropped_wording():
    """The console line check reads one line whatever was dropped."""
    assert surface.console_buffered_text(1, 2, 0) != surface.console_buffered_text(
        1, 2, 3
    )


# The signals gap marker


GAP_CASES = [
    1,
    0,
    -1,
    THOUSAND_MILLION,
    ONE_BILLIONTH,
    True,
    12.7,
    "12.7",
    UNICODE_TEXT,
    LONG_TEXT,
    MARKUP_TEXT,
    APOSTROPHE_TEXT,
    NEWLINE_TEXT,
    NOT_A_NUMBER,
    INFINITY,
    MINUS_INFINITY,
    TWO_TO_1023,
    TWO_TO_1024,
]


@pytest.mark.parametrize("skipped", GAP_CASES, ids=repr)
def test_the_two_sides_write_one_signals_gap_marker(skipped):
    """The surface writes a different gap marker than the signals pane."""
    assert mw._signal_gap_marker_text(skipped) == surface.signal_gap_marker_text(
        skipped
    )


def test_the_gap_marker_comparison_reports_a_different_count():
    """The gap marker comparison passes whatever count the surface puts in."""
    assert surface.signal_gap_marker_text(1) != surface.signal_gap_marker_text(2)


# The API interaction log


def entry(**named):
    """One API log entry, with the shipped defaults for everything unsaid."""
    row = {
        "timestamp": 0,
        "exchange": "coinbase",
        "action": "FETCH_TICKER",
        "reason": "dashboard tick",
        "endpoint": "/products/BTC-USD/ticker",
        "result": "200 OK",
        "elapsed_ms": 42,
        "data_usage": "1 read",
    }
    row.update(named)
    return row


API_ENTRY_CASES = {
    "happy": entry(),
    "no_endpoint": entry(endpoint=""),
    "no_result": entry(result=""),
    "no_elapsed": entry(elapsed_ms=0),
    "negative_elapsed": entry(elapsed_ms=-1),
    "no_data_usage": entry(data_usage=""),
    "bare": entry(endpoint="", result="", elapsed_ms=0, data_usage=""),
    "unicode": entry(reason=UNICODE_TEXT, action=UNICODE_TEXT),
    "two_hundred_characters": entry(reason=LONG_TEXT),
    "markup": entry(reason=MARKUP_TEXT),
    "apostrophe": entry(reason=APOSTROPHE_TEXT),
    "newline": entry(reason=NEWLINE_TEXT),
    "wrong_capitals": entry(exchange=WRONG_CAPITALS_TEXT),
    "thousand_million_elapsed": entry(elapsed_ms=THOUSAND_MILLION),
    "one_billionth_elapsed": entry(elapsed_ms=ONE_BILLIONTH),
    "true_elapsed": entry(elapsed_ms=True),
    "decimal_elapsed": entry(elapsed_ms=12.7),
    "number_where_text_belongs": entry(reason=12.7),
    "true_where_text_belongs": entry(reason=True),
    "infinity_elapsed": entry(elapsed_ms=INFINITY),
    "two_to_1024_elapsed": entry(elapsed_ms=TWO_TO_1024),
}

REFUSING_API_ENTRY_CASES = {
    "no_exchange_key": {"action": "A", "reason": "R"},
    "exchange_is_a_number": entry(exchange=12.7),
    "not_a_number_elapsed": entry(elapsed_ms=NOT_A_NUMBER),
    "text_elapsed": entry(elapsed_ms="42"),
}


def shipped_api_block(row):
    """The block the shipped window appends for one API entry."""

    class ViewSink:
        def __init__(self):
            self.blocks: list = []

        def appendPlainText(self, text):
            self.blocks.append(text)

        def verticalScrollBar(self):
            return self

        def value(self):
            return 0

        def maximum(self):
            return 0

        def setValue(self, value):
            return None

    view = ViewSink()
    window = shipped_window(_api_log_view=view, _api_log_paused=False)
    try:
        driven(window, "_on_api_event")(row)
        answer = {"block": view.blocks[-1] if view.blocks else None, "refused": None}
    except Exception as exc:
        answer = {"block": None, "refused": type(exc).__name__}
    release()
    return answer


def surface_api_block(row, stamp):
    """The block the surface appends for one API entry."""
    model = surface.MainWindowModel()
    try:
        model.api_event(row, stamp)
        return {
            "block": model.api_log_lines[-1] if model.api_log_lines else None,
            "refused": None,
        }
    except Exception as exc:
        return {"block": None, "refused": type(exc).__name__}


def stamp_for(row):
    """The clock reading the shipped window puts at the head of a block."""
    import time as clock

    return clock.strftime("%H:%M:%S", clock.localtime(row["timestamp"]))


@pytest.mark.parametrize("name", sorted(API_ENTRY_CASES))
def test_the_two_sides_write_one_api_log_block(name):
    """The surface wrote a different API log block than the window."""
    row = API_ENTRY_CASES[name]
    old_side = shipped_api_block(row)
    new_side = surface_api_block(row, stamp_for(row))
    assert old_side == new_side, name


@pytest.mark.parametrize("name", sorted(REFUSING_API_ENTRY_CASES))
def test_an_api_entry_that_refuses_refuses_on_both_sides(name):
    """One side wrote a block for an entry the other refused."""
    row = REFUSING_API_ENTRY_CASES[name]
    old_side = shipped_api_block(row)
    try:
        stamp = stamp_for(row)
    except Exception as exc:
        assert old_side["refused"] == type(exc).__name__, name
        return
    new_side = surface_api_block(row, stamp)
    assert old_side["refused"] == new_side["refused"], (
        f"{name}: shipped refused {old_side['refused']}, "
        f"surface refused {new_side['refused']}"
    )


def test_an_api_event_off_the_main_thread_is_refused_by_the_surface():
    """The surface appends a block from a thread the window refuses."""
    model = surface.MainWindowModel()
    assert (
        model.api_event(entry(), "00:00:00", thread_name="worker-1")
        == surface.API_EVENT_WRONG_THREAD
    )
    assert model.api_log_lines == []
    assert model.api_event(entry(), "00:00:00") == surface.API_EVENT_APPENDED


# The indicator panel's empty state


def bot(**named):
    """One bot carrying only what the empty-state decision reads."""
    return surface.BotView(**named)


IVP_CASES = {
    "no_bot": None,
    "idle": bot(state="idle"),
    "stopped": bot(state="stopped"),
    "error": bot(state="error", last_error="boom"),
    "parked": bot(
        state="running",
        at_target_counter=3,
        position_value_usd=101.0,
        target_balance=100.0,
    ),
    "too_few_candles": bot(
        state="running", cached_candles=12, symbol="BTC/USD", ta_timeframe="4h"
    ),
    "no_cache_slot": bot(state="running", cached_candles=None),
    "enough_candles": bot(state="running", cached_candles=30),
    "cold_start": bot(state="running"),
    "wrong_capitals_state": bot(state="IDLE"),
    "empty_state": bot(state=""),
    "true_parked_counter": bot(state="running", at_target_counter=True),
    "text_parked_counter": bot(state="running", at_target_counter="3"),
    "not_a_number_parked_counter": bot(state="running", at_target_counter=NOT_A_NUMBER),
    "text_position": bot(
        state="running", at_target_counter=1, position_value_usd="12.7"
    ),
    "not_a_number_position": bot(
        state="running", at_target_counter=1, position_value_usd=NOT_A_NUMBER
    ),
    "infinity_position": bot(
        state="running", at_target_counter=1, position_value_usd=INFINITY
    ),
    "unicode_symbol": bot(state="running", cached_candles=1, symbol=UNICODE_TEXT),
    "empty_timeframe": bot(state="running", cached_candles=1, ta_timeframe=""),
    "negative_candles": bot(state="running", cached_candles=-5),
    "thousand_million_candles": bot(state="running", cached_candles=THOUSAND_MILLION),
}


def shipped_ivp_cause(one, bot_id):
    """The empty-state cause the shipped window decides on."""
    window = shipped_window()
    window._ivp_cached_candle_count = lambda given: getattr(
        given, "cached_candles", None
    )
    try:
        answer = driven(window, "_ivp_empty_state_cause")(one, bot_id)
        result = {"cause": answer[0], "detail": answer[1], "refused": None}
    except Exception as exc:
        result = {"cause": None, "detail": None, "refused": type(exc).__name__}
    release()
    return result


def surface_ivp_cause(one, bot_id):
    """The empty-state cause the surface decides on."""
    try:
        answer = surface.ivp_empty_state_cause(one, bot_id)
        return {"cause": answer[0], "detail": answer[1], "refused": None}
    except Exception as exc:
        return {"cause": None, "detail": None, "refused": type(exc).__name__}


@pytest.mark.parametrize("name", sorted(IVP_CASES))
@pytest.mark.parametrize("bot_id", ["", "abc12345", UNICODE_TEXT, 12.7, None])
def test_the_two_sides_name_one_empty_state_cause(name, bot_id):
    """The surface names a different reason the indicator panel is blank."""
    one = IVP_CASES[name]
    old_side = shipped_ivp_cause(one, bot_id)
    new_side = surface_ivp_cause(one, bot_id)
    assert leaves(old_side) == leaves(new_side), f"{name} / {bot_id!r}"


def test_the_empty_state_comparison_reports_a_different_cause():
    """The empty-state comparison passes whatever cause the surface names."""
    idle = surface_ivp_cause(IVP_CASES["idle"], "a")
    cold = surface_ivp_cause(IVP_CASES["cold_start"], "a")
    assert idle["cause"] != cold["cause"]


# The Extractor parent refusal


REFUSAL_CASES = {
    "one_parent": {"parent": object(), "candidates": [], "roster": True},
    "no_parent": {"parent": None, "candidates": [], "roster": True},
    "two_parents": {
        "parent": None,
        "candidates": [("aaa", object()), ("bbb", object())],
        "roster": True,
    },
    "no_roster": {"parent": None, "candidates": [], "roster": False},
}

REFUSAL_ARGUMENTS = [
    ("BTC", "coinbase"),
    ("", ""),
    ("  btc  ", "  coinbase  "),
    (None, None),
    (UNICODE_TEXT, UNICODE_TEXT),
    (LONG_TEXT, LONG_TEXT),
    (MARKUP_TEXT, MARKUP_TEXT),
    (APOSTROPHE_TEXT, APOSTROPHE_TEXT),
    (NEWLINE_TEXT, NEWLINE_TEXT),
    ("bTc", "CoInBaSe"),
]


@pytest.mark.parametrize("name", sorted(REFUSAL_CASES))
@pytest.mark.parametrize("base_currency,exchange_id", REFUSAL_ARGUMENTS)
def test_the_two_sides_word_one_extractor_refusal(name, base_currency, exchange_id):
    """The surface refuses an Extractor with different words than the window."""
    case = REFUSAL_CASES[name]
    fleet = FleetStub(parent=case["parent"], candidates=case["candidates"])
    window = shipped_window(_bot_manager=fleet if case["roster"] else None)
    old_side = driven(window, "_extractor_parent_refusal")(base_currency, exchange_id)
    new_side = surface.extractor_parent_refusal(
        base_currency,
        exchange_id,
        case["parent"],
        case["candidates"],
        case["roster"],
    )
    assert old_side == new_side, f"{name} / {base_currency!r}"
    release()


@pytest.mark.parametrize("value", [12.7, True, NOT_A_NUMBER, INFINITY, TEN_TO_400])
def test_a_refusal_argument_that_refuses_refuses_on_both_sides(value):
    """One side worded a refusal for an asset name the other refused."""
    window = shipped_window(_bot_manager=FleetStub(parent=None))
    try:
        driven(window, "_extractor_parent_refusal")(value, "coinbase")
        old_refused = None
    except Exception as exc:
        old_refused = type(exc).__name__
    try:
        surface.extractor_parent_refusal(value, "coinbase", None, [], True)
        new_refused = None
    except Exception as exc:
        new_refused = type(exc).__name__
    assert old_refused == new_refused, value
    release()


def test_the_refusal_comparison_reports_the_two_reasons_apart():
    """The refusal comparison reads one text whatever the roster holds."""
    none_hold = surface.extractor_parent_refusal("BTC", "coinbase", None, [], True)
    two_hold = surface.extractor_parent_refusal(
        "BTC", "coinbase", None, [("a", 1), ("b", 2)], True
    )
    assert none_hold != two_hold
    assert none_hold is not None
    assert (
        surface.extractor_parent_refusal("BTC", "coinbase", object(), [], True) is None
    )


def test_the_refusal_box_and_the_records_it_writes():
    """The window's refusal path raises a different box or writes a different record."""
    from src.exchange import api_logger

    boxes = BoxRecorder()
    api_log = ApiLogRecorder()
    log = LoggerRecorder()
    window = shipped_window(_bot_manager=FleetStub(parent=None))
    window._extractor_parent_refusal = driven(window, "_extractor_parent_refusal")
    with SwappedNames(
        [
            (mw, "QMessageBox", boxes),
            (mw, "logger", log),
            (api_logger, "get_api_log", lambda: api_log),
        ]
    ) as swapped:
        stopped = driven(window, "_refuse_extractor_without_parent")("BTC", "coinbase")
    assert swapped.restored() is True

    model = surface.MainWindowModel(fleet=surface.FleetSource(parent=None))
    model_stopped = model.create_extractor("BTC", "coinbase")

    assert stopped == model_stopped
    assert digest(boxes.raised) == digest(model.boxes)
    assert digest(
        [
            {"text": line["text"], "level": line["level"]}
            for line in window._status_log.lines
        ]
    ) == digest(model.log_lines)
    assert digest(api_log.records) == digest(model.api_records)
    release()


# The adopt gate


def proposal(**named):
    """One topology proposal, with the shipped defaults for everything unsaid."""
    row = {
        "title": "Two asset ring",
        "bots": [
            {"asset": "BTC", "suggested_target_usd": 250.0},
            {"asset": "ETH", "existing_bot_id": "abc"},
        ],
        "wires": [{"source_asset": "BTC", "target_asset": "ETH", "pct": 25.0}],
    }
    row.update(named)
    return row


def collision(**named):
    """One already-wired pair the adopt gate discloses."""
    row = {
        "source_asset": "BTC",
        "target_asset": "ETH",
        "source_id": "aaa",
        "target_id": "bbb",
        "current_pct": 10.0,
        "proposed_pct": 25.0,
    }
    row.update(named)
    return row


ADOPT_CASES = {
    "happy": (proposal(), []),
    "no_new_bots": (
        proposal(bots=[{"asset": "ETH", "existing_bot_id": "abc"}]),
        [],
    ),
    "no_wires": (proposal(wires=[]), []),
    "one_collision": (proposal(), [collision()]),
    "twelve_collisions": (proposal(), [collision() for _ in range(12)]),
    "thirteen_collisions": (proposal(), [collision() for _ in range(13)]),
    "no_title": (proposal(title=None), []),
    "missing_title": ({"bots": [{"asset": "BTC"}], "wires": []}, []),
    "unicode_title": (proposal(title=UNICODE_TEXT), []),
    "two_hundred_characters_title": (proposal(title=LONG_TEXT), []),
    "markup_title": (proposal(title=MARKUP_TEXT), []),
    "apostrophe_title": (proposal(title=APOSTROPHE_TEXT), []),
    "newline_title": (proposal(title=NEWLINE_TEXT), []),
    "number_title": (proposal(title=12.7), []),
    "zero_budget": (
        proposal(bots=[{"asset": "BTC", "suggested_target_usd": 0.0}]),
        [],
    ),
    "negative_budget": (
        proposal(bots=[{"asset": "BTC", "suggested_target_usd": -50.0}]),
        [],
    ),
    "thousand_million_budget": (
        proposal(bots=[{"asset": "BTC", "suggested_target_usd": THOUSAND_MILLION}]),
        [],
    ),
    "one_billionth_budget": (
        proposal(bots=[{"asset": "BTC", "suggested_target_usd": ONE_BILLIONTH}]),
        [],
    ),
    "true_budget": (
        proposal(bots=[{"asset": "BTC", "suggested_target_usd": True}]),
        [],
    ),
    "text_budget": (
        proposal(bots=[{"asset": "BTC", "suggested_target_usd": "250"}]),
        [],
    ),
    "infinity_budget": (
        proposal(bots=[{"asset": "BTC", "suggested_target_usd": INFINITY}]),
        [],
    ),
    "not_a_number_budget": (
        proposal(bots=[{"asset": "BTC", "suggested_target_usd": NOT_A_NUMBER}]),
        [],
    ),
    "negative_collision_pct": (
        proposal(),
        [collision(current_pct=-1.0, proposed_pct=-2.0)],
    ),
}


def shipped_adopt(row, collisions, confirmed):
    """The adopt confirmation the shipped window raises, up to the answer.

    The path past the confirm opens the Bot Wizard, which is another
    surface's work, so the wizard is stood in for and the comparison is
    the confirm gate: the boxes raised, and the lines logged before the
    operator answered.
    """
    boxes = BoxRecorder(answer=BoxRecorder.Ok if confirmed else BoxRecorder.Cancel)
    log = LoggerRecorder()
    window = shipped_window(_bot_manager=FleetStub())
    asked: list = []
    window._topology_wire_collisions = lambda wires, mapping: (
        asked.append((wires, mapping)) or list(collisions)
    )
    window._snapshot_wires_for_adopt = lambda title: asked.append(title)
    window._build_topology_proposals = lambda: asked.append("rebuild")
    window._create_bot = lambda exchange_id="", defaults_override=None: asked.append(
        defaults_override
    )
    window._report_adopt_orphans = lambda created: asked.append(list(created))
    logged_at_confirm: list = []
    boxes.before_question = lambda: logged_at_confirm.append(
        len(window._status_log.lines)
    )
    from PySide6 import QtWidgets

    with SwappedNames(
        [
            (mw, "QMessageBox", boxes),
            (mw, "logger", log),
            (QtWidgets, "QMessageBox", boxes),
        ]
    ) as swapped:
        try:
            driven(window, "_adopt_topology_proposal")(row)
            refused = None
        except Exception as exc:
            refused = type(exc).__name__
    cut = logged_at_confirm[0] if logged_at_confirm else len(window._status_log.lines)
    kept = window._status_log.lines if not confirmed else window._status_log.lines[:cut]
    answer = {
        "boxes": boxes.raised,
        "log": [line["text"] for line in kept],
        "refused": refused,
        "swap_restored": swapped.restored(),
    }
    release()
    return answer


def surface_adopt(row, collisions, confirmed):
    """The adopt confirmation the surface raises, up to the answer."""
    model = surface.MainWindowModel(fleet=surface.FleetSource())
    try:
        model.adopt_topology(row, collisions, confirmed)
        refused = None
    except Exception as exc:
        refused = type(exc).__name__
    return {
        "boxes": model.boxes,
        "log": [line["text"] for line in model.log_lines],
        "refused": refused,
        "swap_restored": True,
    }


@pytest.mark.parametrize("name", sorted(ADOPT_CASES))
@pytest.mark.parametrize("confirmed", [True, False])
def test_the_two_sides_word_one_adopt_confirmation(name, confirmed):
    """The surface worded the adopt gate differently than the window."""
    row, collisions = ADOPT_CASES[name]
    old_side = shipped_adopt(row, collisions, confirmed)
    new_side = surface_adopt(row, collisions, confirmed)
    assert old_side["refused"] == new_side["refused"], name
    assert digest(old_side["boxes"]) == digest(new_side["boxes"]), name
    assert old_side["log"] == new_side["log"], name


def test_the_adopt_gate_stops_on_a_proposal_with_no_bots():
    """The adopt gate raises a box for a proposal it should ignore."""
    for empty in ({}, {"bots": []}, None, "not a proposal", 12.7):
        assert shipped_adopt(empty, [], True)["boxes"] == []
        assert surface_adopt(empty, [], True)["boxes"] == []


def test_the_adopt_gate_reports_no_manager():
    """The adopt gate builds a summary with no bot manager to adopt into."""
    from PySide6 import QtWidgets

    boxes = BoxRecorder()
    window = shipped_window(_bot_manager=None)
    with SwappedNames([(mw, "QMessageBox", boxes), (QtWidgets, "QMessageBox", boxes)]):
        driven(window, "_adopt_topology_proposal")(proposal())
    model = surface.MainWindowModel(fleet=None)
    model.adopt_topology(proposal(), [], True)
    assert digest(boxes.raised) == digest(model.boxes)
    release()


def test_the_adopt_comparison_reports_a_missing_collision_line():
    """The adopt comparison passes whatever lines the surface builds."""
    with_one = surface.adopt_summary_lines(proposal(), [collision()])
    with_none = surface.adopt_summary_lines(proposal(), [])
    assert with_one != with_none


# Confirmations, theme and the About box


@pytest.mark.parametrize("confirmed", [True, False])
def test_the_two_sides_word_one_reset_confirmation(confirmed):
    """The surface worded Reset All Settings differently than the window."""
    boxes = BoxRecorder(answer=BoxRecorder.Yes if confirmed else BoxRecorder.No)
    settings = SettingsStub()
    window = shipped_window(_settings=settings)
    with SwappedNames([(mw, "QMessageBox", boxes)]) as swapped:
        driven(window, "_reset_settings")()
    assert swapped.restored() is True

    model = surface.MainWindowModel(settings=surface.SettingsSource())
    model.reset_settings(confirmed)

    assert digest(boxes.raised) == digest(model.boxes)
    assert digest(
        [
            {"text": one["text"], "level": one["level"]}
            for one in window._status_log.lines
        ]
    ) == digest(model.log_lines)
    assert digest(
        [{"text": one["text"], "level": one["level"]} for one in window._spool.lines]
    ) == digest(model.spool_lines)
    assert settings.reset_count == model.settings.reset_count
    release()


DELETE_BOT_IDS = [
    "abc12345",
    "",
    UNICODE_TEXT,
    LONG_TEXT,
    MARKUP_TEXT,
    APOSTROPHE_TEXT,
    NEWLINE_TEXT,
    WRONG_CAPITALS_TEXT,
    12.7,
    True,
    NOT_A_NUMBER,
    INFINITY,
    MINUS_INFINITY,
    TWO_TO_1024,
]


@pytest.mark.parametrize("bot_id", DELETE_BOT_IDS, ids=repr)
def test_the_two_sides_word_one_delete_confirmation(bot_id):
    """The surface worded the delete question differently than the window."""
    assert (
        surface.DELETE_TEXT_FORMAT.format(bot_id=bot_id)
        == f"Delete bot {bot_id}? This cannot be undone."
    )


def test_the_two_sides_word_one_about_box():
    """The surface worded the About box differently than the window."""
    boxes = BoxRecorder()
    window = shipped_window()
    with SwappedNames([(mw, "QMessageBox", boxes)]):
        driven(window, "_show_about")()
    model = surface.MainWindowModel()
    model.show_about()
    assert digest(boxes.raised) == digest(model.boxes)
    release()


def test_the_about_box_still_names_the_version_the_title_bar_does_not():
    """The About box and the title bar name the same version."""
    assert surface.ABOUT_TEXT.startswith("Acervator v1.7")
    assert surface.window_title(mw.__version__) != "Acervator v1.7"


THEME_CASES = ["cyberpunk_dark", "", UNICODE_TEXT, 12.7, True, None, NEWLINE_TEXT]


def shipped_theme_switch(name):
    """The theme switch, applied to a stand-in application object.

    The window resolves its application through ``self.parent()``, so a
    stand-in there keeps the drive off the real one and off every other
    test in this worker.
    """
    sink = StyleSink()
    holder = shipped_window(parent=sink)
    try:
        driven(holder, "_switch_theme")(name)
        refused = None
    except Exception as exc:
        refused = type(exc).__name__
    return {
        "refused": refused,
        "applied": len(sink.sheets),
        "log": [one["text"] for one in holder._status_log.lines],
    }


def surface_theme_switch(name, themes):
    """The theme switch on the surface."""
    model = surface.MainWindowModel(themes=surface.ThemeSource(themes))
    try:
        model.switch_theme(name)
        refused = None
    except Exception as exc:
        refused = type(exc).__name__
    return {
        "refused": refused,
        "applied": 0 if refused else 1,
        "log": [one["text"] for one in model.log_lines],
    }


@pytest.mark.parametrize("name", THEME_CASES, ids=repr)
def test_a_theme_name_the_register_does_not_hold_refuses_on_both_sides(name):
    """One side switched to a theme the other refused."""
    from src.gui.theme_engine import THEMES

    themes = [(one, one) for one in THEMES]
    old_side = shipped_theme_switch(name)
    new_side = surface_theme_switch(name, themes)
    assert old_side["refused"] == new_side["refused"], name
    assert old_side["applied"] == new_side["applied"], name
    assert old_side["log"] == new_side["log"], name


def test_the_theme_switch_check_reports_a_known_name_and_an_unknown_one():
    """The theme check reads one answer whatever name it is given."""
    from src.gui.theme_engine import THEMES

    themes = [(one, one) for one in THEMES]
    known = next(iter(THEMES))
    assert shipped_theme_switch(known)["refused"] is None
    assert shipped_theme_switch("no such theme")["refused"] == "ValueError"
    assert surface_theme_switch(known, themes)["refused"] is None
    assert surface_theme_switch("no such theme", themes)["refused"] == "ValueError"


# The sounds and the pulse


SOUND_CASES = [
    ("SCRUM", 1.0),
    ("FOLD", 1.0),
    ("DIST", 1.0),
    ("FOLD", 0.0),
    ("SCRUM", -1.0),
    ("", 0.0),
    (None, 0.0),
    ("fold", 5.0),
    ("fOlD", 0.0),
    ("BUY", 3.0),
    ("SCRUM", THOUSAND_MILLION),
    ("SCRUM", ONE_BILLIONTH),
    ("SCRUM", True),
    ("SCRUM", INFINITY),
    ("SCRUM", MINUS_INFINITY),
    ("SCRUM", NOT_A_NUMBER),
    ("SCRUM", TWO_TO_1024),
    (UNICODE_TEXT, 0.0),
    (LONG_TEXT, 0.0),
]


class SoundRecorder:
    """Stands in for the sound engine, keeping which sound was asked for."""

    def __init__(self):
        self.played: list = []

    def play_fire(self):
        self.played.append(surface.FIRE_SOUND)

    def play_profit(self):
        self.played.append(surface.PROFIT_SOUND)

    def play_drip(self):
        self.played.append(surface.DRIP_SOUND)

    def play_track(self):
        self.played.append(surface.BEEP_TRACK_PHASE)


class Event:
    """One bus event carrying the data the window reads off it."""

    def __init__(self, data):
        self.data = data


@pytest.mark.parametrize("trade_type,profit", SOUND_CASES, ids=repr)
def test_the_two_sides_play_one_set_of_sounds(trade_type, profit):
    """The surface plays a different sound on a fill than the window."""
    from src.core import sound_engine

    recorder = SoundRecorder()
    window = shipped_window()
    with SwappedNames(
        [(sound_engine, "get_sound_engine", lambda: recorder)]
    ) as swapped:
        driven(window, "_on_trade_filled_sfx")(
            Event({"type": trade_type, "profit": profit})
        )
    assert swapped.restored() is True
    assert recorder.played == surface.trade_filled_sounds(trade_type, profit)
    release()


def test_the_sound_check_reports_a_missing_sound():
    """The sound check reads one answer whatever the fill was."""
    assert surface.trade_filled_sounds("FOLD", 1.0) == ["fire", "profit", "drip"]
    assert surface.trade_filled_sounds("BUY", 0.0) == []


BEEP_FLEETS = {
    "empty": [],
    "one_firing": [
        {"mode": "scrumming", "state": "running", "scrum_target_mode": "fire"}
    ],
    "one_tracking": [
        {"mode": "scrumming", "state": "running", "scrum_target_mode": "track"}
    ],
    "tracking_then_firing": [
        {"mode": "scrumming", "state": "running", "scrum_target_mode": "track"},
        {"mode": "scrumming", "state": "running", "scrum_target_mode": "fire"},
    ],
    "paused_tracking": [
        {"mode": "scrumming", "state": "paused", "scrum_target_mode": "track"}
    ],
    "stopped_firing": [
        {"mode": "scrumming", "state": "stopped", "scrum_target_mode": "fire"}
    ],
    "wrong_mode": [
        {"mode": "extractor", "state": "running", "scrum_target_mode": "fire"}
    ],
    "no_phase": [{"mode": "scrumming", "state": "running"}],
    "bare_rows": [{}],
}


@pytest.mark.parametrize("name", sorted(BEEP_FLEETS))
def test_the_two_sides_pick_one_beep_phase(name):
    """The surface picks a different beep cadence than the window."""
    statuses = BEEP_FLEETS[name]
    from src.core import sound_engine

    recorder = SoundRecorder()
    window = shipped_window()
    window._beep_last_ts = 0.0
    with SwappedNames([(sound_engine, "get_sound_engine", lambda: recorder)]):
        driven(window, "_dispatch_tracking_beep")(statuses)
    model = surface.MainWindowModel()
    model.tracking_beep(statuses, now=10_000.0)
    assert recorder.played == model.sounds, name
    release()


def test_the_beep_is_throttled_by_its_own_cadence():
    """The surface beeps at a different cadence than the window."""
    model = surface.MainWindowModel()
    firing = BEEP_FLEETS["one_firing"]
    assert model.tracking_beep(firing, now=100.0) == surface.BEEP_PLAYED
    assert model.tracking_beep(firing, now=100.1) == surface.BEEP_THROTTLED
    assert model.tracking_beep(firing, now=100.3) == surface.BEEP_PLAYED
    tracking = BEEP_FLEETS["one_tracking"]
    assert model.tracking_beep(tracking, now=100.9) == surface.BEEP_THROTTLED
    assert model.tracking_beep(tracking, now=101.2) == surface.BEEP_PLAYED
    assert surface.beep_cadence_s("fire") == 0.2
    assert surface.beep_cadence_s("track") == 0.8


PULSE_TICKS = [1, 2, 5, 20, 100]


@pytest.mark.parametrize("ticks", PULSE_TICKS)
def test_the_two_sides_pulse_to_one_value(ticks):
    """The surface pulses to a different opacity or glow than the window."""

    class EffectSink:
        def __init__(self):
            self.opacities: list = []
            self.blurs: list = []

        def setOpacity(self, value):
            self.opacities.append(value)

        def setBlurRadius(self, value):
            self.blurs.append(value)

        def blurRadius(self):
            return 0.0

    effect = EffectSink()
    window = shipped_window()
    window._pulse_phase = 0.0
    window._pulse_effects = [effect]
    window._fire_glow_effects = [effect]
    tick = driven(window, "_pulse_tick")
    model = surface.MainWindowModel()
    for _ in range(ticks):
        tick()
        model.pulse_tick()
    assert effect.opacities[-1] == model.pulse_opacity
    assert effect.blurs[-1] == model.glow_blur
    assert window._pulse_phase == model.pulse_phase
    release()


def test_the_pulse_check_reports_a_changed_swing():
    """The pulse check reads one value whatever the formula produces."""
    assert surface.pulse_opacity(0.0) == pytest.approx(0.91)
    assert surface.pulse_opacity(math.pi / 2) == pytest.approx(1.0)
    assert surface.glow_blur(0.0) == pytest.approx(17.0)


# The History tab's auto-refresh, and every other decision


HISTORY_CASES = [
    (0.0, False, 1000.0),
    (999.0, False, 1000.0),
    (600.0, False, 1000.0),
    (700.0, False, 1000.0),
    (0.0, True, 1000.0),
    (600.0, True, 1000.0),
    (1000.0, False, 1000.0),
    (2000.0, False, 1000.0),
    (0, False, 0.0),
]


@pytest.mark.parametrize("last_ts,in_flight,now", HISTORY_CASES, ids=repr)
def test_the_history_tab_refreshes_on_one_rule(last_ts, in_flight, now):
    """The surface starts a History fetch the window does not, or misses one."""
    tab = surface.HistoryTabSource(last_ts, in_flight)
    model = surface.MainWindowModel(history_tab=tab)
    model.tab_labels = list(surface.CANONICAL_TAB_ORDER)
    model.change_tab(surface.CANONICAL_TAB_ORDER.index("History"), now=now)
    due = surface.history_refresh_due(last_ts, in_flight, now)
    assert (tab.refreshes == 1) == due


def test_the_history_rule_reports_both_answers():
    """The History rule reads one answer whatever the last fetch was."""
    assert surface.history_refresh_due(0.0, False, 10.0) is True
    assert surface.history_refresh_due(9.0, False, 10.0) is False


EQUITY_CASES = ["alpaca", "ALPACA", "coinbase", "", UNICODE_TEXT, "AlPaCa"]


@pytest.mark.parametrize("exchange_id", EQUITY_CASES, ids=repr)
def test_the_two_sides_route_one_exchange_to_one_layer(exchange_id):
    """The surface routes an exchange to a different layer than the window."""
    ids = {"alpaca", "ibkr"}
    window = shipped_window(_equity_exchange_ids=ids)
    old_side = driven(window, "_is_equity_exchange")(exchange_id)
    new_side = surface.is_equity_exchange(exchange_id, ids)
    assert old_side == new_side, exchange_id
    release()


TOOLTIP_CASES = [
    ("Total P/L", ""),
    ("Total P/L", "already set"),
    ("", ""),
    ("RSI reading", ""),
    ("nothing here", ""),
    ("TA and RSI", ""),
    (UNICODE_TEXT, ""),
    (LONG_TEXT, ""),
    ("api", ""),
    ("API", ""),
]


def tooltip_window():
    """A real window with the tooltip map built and its rescan timer stopped.

    The build also grows the application style sheet and queues a
    one-shot rescan; the sheet is put back and the one-shot is pointed at
    a plain callable, so nothing this drive starts outlives it.
    """
    window = qt_window()
    window._apply_abbreviation_tooltips = lambda: None
    app_object = QApplication.instance()
    saved = app_object.styleSheet()
    try:
        driven(window, "_setup_tooltips")()
    finally:
        app_object.setStyleSheet(saved)
    window._tooltip_timer.stop()
    return window


@pytest.mark.parametrize("text,existing", TOOLTIP_CASES, ids=repr)
def test_the_two_sides_pick_one_tooltip(text, existing):
    """The surface picks a different tooltip than the window's scan."""
    window = tooltip_window()
    label = hold(QLabel(text))
    label.setParent(window)
    if existing:
        label.setToolTip(existing)
    driven(window, "_apply_abbreviation_tooltips")()
    expected = surface.tooltip_for(text, existing)
    assert label.toolTip() == (expected if expected is not None else existing)
    release()


def test_the_tooltip_map_holds_the_same_pairs_on_both_sides():
    """The surface carries a different tooltip map than the window."""
    window = tooltip_window()
    assert list(window._abbreviation_tooltips.items()) == list(
        surface.ABBREVIATION_TOOLTIPS
    )
    release()


def test_the_orphan_report_is_worded_the_same_way():
    """The surface names the orphaned bots differently than the window."""
    for created in ([], ["abcdefghij"], ["a", "b"], [12.7], [UNICODE_TEXT]):
        window = shipped_window()
        driven(window, "_report_adopt_orphans")(created)
        old_side = [one["text"] for one in window._status_log.lines]
        text = surface.orphan_report_text(created)
        new_side = [] if text is None else [text]
        assert old_side == new_side, created
        release()


# The bus this window never unsubscribes from


def test_the_window_subscribes_to_the_topics_the_surface_names():
    """The surface names a different set of bus topics than the window takes."""
    from src.core.event_bus import EventBus

    bus = EventBus()
    seen: list = []
    for topic in surface.BUS_SUBSCRIPTIONS:
        bus.subscribe(topic, lambda event, name=topic: seen.append((name, event)))
    for topic in surface.BUS_SUBSCRIPTIONS:
        bus.emit(topic, carried=topic)
    assert [name for name, _event in seen] == list(surface.BUS_SUBSCRIPTIONS)
    assert [event.data["carried"] for _name, event in seen] == list(
        surface.BUS_SUBSCRIPTIONS
    )


def test_the_bus_counter_reports_a_topic_nobody_subscribed_to():
    """The bus counter reports a delivery whatever was subscribed."""
    from src.core.event_bus import EventBus

    bus = EventBus()
    seen: list = []
    bus.subscribe("bot.log", lambda event: seen.append(event.topic))
    bus.emit("wire.created")
    assert seen == []
    bus.emit("bot.log")
    assert seen == ["bot.log"]


def test_the_window_gives_back_none_of_the_topics_it_takes():
    """The surface claims the window drops a subscription it never drops."""
    assert surface.BUS_UNSUBSCRIPTIONS == ()
    assert len(surface.BUS_SUBSCRIPTIONS) == 6


# The timers, counted on the running window by what they drive


def test_a_bare_window_drives_none_of_the_products_timers():
    """A bare window already drives a timer, so a count of them means nothing."""
    window = hold(Window())
    assert [child for child in window.children() if child.inherits("QTimer")] == []
    release()


def test_the_dashboard_timer_drives_the_dashboard_every_two_seconds():
    """The dashboard timer runs at a different rate, or drives nothing."""
    window = qt_window()
    ran: list = []
    window._refresh_dashboard = lambda: ran.append("tick")
    driven(window, "_setup_refresh_timer")()
    assert window._timer.interval() == surface.DASHBOARD_TICK_MS
    assert window._timer.isActive() is True
    window._timer.timeout.emit()
    assert ran == ["tick"]
    window._timer.stop()
    release()


def test_the_pulse_timer_drives_the_pulse_every_eighty_milliseconds():
    """The pulse timer runs at a different rate, or drives nothing."""
    window = qt_window()
    ran: list = []
    window._pulse_tick = lambda: ran.append("pulse")
    window._stat_pnl = hold(QLabel("pnl"))
    window._stat_trades = hold(QLabel("trades"))
    window._stat_bots = hold(QLabel("bots"))
    window._stat_errors = hold(QLabel("errors"))
    window._spendable_widget = hold(QLabel("spendable"))
    driven(window, "_setup_pulse")()
    assert window._pulse_timer.interval() == surface.PULSE_TICK_MS
    assert window._pulse_timer.isActive() is True
    window._pulse_timer.timeout.emit()
    assert ran == ["pulse"]
    window._pulse_timer.stop()
    release()


def test_the_tooltip_timer_rescans_every_five_seconds():
    """The tooltip timer runs at a different rate, or drives nothing."""
    window = qt_window()
    ran: list = []
    window._apply_abbreviation_tooltips = lambda: ran.append("scan")
    app_object = QApplication.instance()
    saved = app_object.styleSheet()
    try:
        driven(window, "_setup_tooltips")()
    finally:
        app_object.setStyleSheet(saved)
    assert window._tooltip_timer.interval() == surface.TOOLTIP_TICK_MS
    assert window._tooltip_timer.isActive() is True
    window._tooltip_timer.timeout.emit()
    assert ran == ["scan"]
    window._tooltip_timer.stop()
    release()


def test_the_timer_check_reports_a_timer_that_drives_nothing():
    """The timer check passes a timer connected to nothing."""
    from PySide6.QtCore import QTimer

    bare = QTimer()
    bare.start(surface.DASHBOARD_TICK_MS)
    ran: list = []
    bare.timeout.emit()
    assert ran == []
    bare.stop()


# Completeness, unbacked keys and growth


def answer_for_completeness():
    """One full answer off the bridge, covering every key the surface names."""
    return surface.view_model(
        {
            "version": "3.25.8",
            "themes": [("cyberpunk_dark", "Cyberpunk Dark")],
            "settings": {"ai_monitor": {"enabled": True, "api_key": "k"}},
            "fleet": {"aggregate": aggregate(), "statuses": [{"bot_id": "a"}]},
            "exchange_tab_ids": ["coinbase"],
            "connector_ids": [],
            "equity_exchange_ids": ["alpaca"],
        }
    )


def test_every_key_the_model_declares_reaches_the_answer():
    """A field the model holds never reaches the answer, so nothing checks it."""
    model = surface.MainWindowModel()
    model.build()
    answered = set(model.as_dict())
    held = {
        name
        for name in vars(model)
        if not name.startswith("_")
        and name
        not in {
            "version",
            "fleet",
            "settings",
            "themes",
            "load_monitor",
            "history_tab",
            "console_handler",
            "equity_exchange_ids",
            "exchange_tab_ids",
            "connector_ids",
            "tabs_ready",
            "failed_tabs",
            "error_buffer",
            "beep_last_ts",
        }
    }
    missing = sorted(held - answered)
    assert missing == [], missing


def test_the_completeness_check_reports_a_field_left_out_of_the_answer():
    """The completeness check passes a field the answer never carries."""
    model = surface.MainWindowModel()
    model.build()
    model.a_field_no_answer_carries = "x"
    assert "a_field_no_answer_carries" not in model.as_dict()


def backing_names():
    """Every name that can back a key: a module name, or a field the model holds."""
    model = surface.MainWindowModel()
    model.build()
    return set(dir(surface)) | set(vars(model))


def unbacked_keys(answered, named):
    """Every key in `answered` that no name in `named` accounts for."""
    return sorted(key for key in answered if key not in named)


def test_no_key_in_the_answer_is_backed_by_nothing():
    """A key in the answer comes from no constant and no field."""
    assert unbacked_keys(answer_for_completeness(), backing_names()) == []


def test_the_unbacked_key_check_reports_a_key_nothing_names():
    """The unbacked-key check passes a key no name in the module backs."""
    answered = dict(answer_for_completeness())
    answered["zzz_no_name_backs_this"] = 1
    assert unbacked_keys(answered, backing_names()) == ["zzz_no_name_backs_this"]


def parsed(source):
    """`source` as a tree."""
    return ast.parse(source)


def module_level_names(source):
    """Every name the file binds at module level, read off the tree."""
    found = set()
    for node in parsed(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return found


def test_every_name_the_file_binds_is_on_the_imported_module():
    """A name the file binds is missing from the module the bridge imports."""
    parsed_names = module_level_names(SURFACE_SOURCE)
    live_names = {name for name in dir(surface) if not name.startswith("__")}
    assert sorted(parsed_names - live_names) == []


def test_every_name_on_the_module_is_bound_by_the_file():
    """The module grew a name the file does not bind."""
    parsed_names = module_level_names(SURFACE_SOURCE)
    imported = {"annotations", "math", "Any", "Optional", "ds"}
    live_names = {
        name
        for name in dir(surface)
        if not name.startswith("__") and name not in imported
    }
    assert sorted(live_names - parsed_names) == []


def test_the_growth_check_reports_a_name_added_to_the_module():
    """The growth check passes a name the file never bound."""
    parsed_names = module_level_names(SURFACE_SOURCE)
    assert "A_NAME_THE_FILE_NEVER_BOUND" not in parsed_names
    live_names = set(dir(surface)) | {"A_NAME_THE_FILE_NEVER_BOUND"}
    assert sorted(live_names - parsed_names - {"A_NAME_THE_FILE_NEVER_BOUND"}) != [
        "A_NAME_THE_FILE_NEVER_BOUND"
    ]


# The surface reaches for nothing


BRIDGE_PROBE = """
import json
import sys

from src.core.desktop_bridge import build_registry, dispatch

registry = build_registry()
frame = {}
try:
    frame['result'] = dispatch(
        'main_window.state',
        {
            'version': '3.25.8',
            'themes': [['cyberpunk_dark', 'Cyberpunk Dark']],
            'fleet': {'aggregate': {'total_realised_pnl': 1.0,
                                    'total_trades': 2,
                                    'running': 1},
                      'statuses': []},
        },
        registry,
    )
    frame['ok'] = True
except Exception as exc:
    frame['ok'] = False
    frame['error'] = repr(exc)
print(json.dumps({
    'qt': [name for name in sys.modules if name.startswith('PySide6')],
    'frame': frame,
}))
"""

NOTHING_AT_IMPORT_PROBE = """
import builtins
import json
import os
import sys
import threading
from pathlib import Path

root = Path(os.environ['ACERVATOR_TEST_HOME'])
opened = []
real_open = builtins.open


def watched_open(file, *found, **named):
    opened.append(str(file))
    return real_open(file, *found, **named)


builtins.open = watched_open

import time
clock = []
real_time = time.time
real_monotonic = time.monotonic
real_localtime = time.localtime
time.time = lambda: clock.append('time') or real_time()
time.monotonic = lambda: clock.append('monotonic') or real_monotonic()
time.localtime = lambda *a: clock.append('localtime') or real_localtime(*a)

import socket
reached = []


def refuse(address, *found, **named):
    reached.append(str(address))
    raise OSError('the probe may not reach outside')


socket.create_connection = refuse
socket.socket.connect = lambda self, address, *_f, **_n: refuse(address)

opened_before = len(opened)
clock_before = len(clock)
threads_before = threading.active_count()
from src.gui.main_tabs import main_window_surface as s

opened_at_import = opened[opened_before:]
clock_at_import = clock[clock_before:]
threads_at_import = threading.active_count() - threads_before
built = s.view_model({'version': '1.2.3'})
answer = {
    'title': built['window_title'],
    'built_on_request': built['tab_labels'] != [],
    'method': s.METHOD,
    'qt': [name for name in sys.modules if name.startswith('PySide6')],
    'opened_at_import': opened_at_import,
    'clock_at_import': clock_at_import,
    'threads_at_import': threads_at_import,
    'reached_at_import': list(reached),
    'made_under_home': sorted(str(p) for p in root.rglob('*')),
}
builtins.open = real_open
print(json.dumps(answer))
"""


def run_script(source, env=None):
    """Run one probe in a fresh process and return what it printed."""
    where = dict(os.environ)
    where.pop("ACERVATOR_TEST_HOME", None)
    if env:
        where.update(env)
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
        env=where,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt(tmp_path):
    """Reaching the window's own values pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE, {"ACERVATOR_TEST_HOME": str(tmp_path / "home")})
    assert answered["qt"] == [], answered["qt"]
    assert answered["frame"]["ok"] is True, answered["frame"]
    result = answered["frame"]["result"]
    assert result["window_title"] == "Acervator v3.25.8"
    assert result["tab_labels"] == list(surface.CANONICAL_TAB_ORDER)
    assert result["status_text"] == surface.STATUS_READY_TEXT


def test_the_qt_probe_can_report_qt(tmp_path):
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script(
        "import PySide6.QtCore\n" + BRIDGE_PROBE,
        {"ACERVATOR_TEST_HOME": str(tmp_path / "home")},
    )
    assert loaded["qt"] != []
    assert loaded["frame"]["ok"] is True


def test_importing_the_surface_reads_no_file_and_no_clock(tmp_path):
    """Loading the surface read a file, read the clock or started a thread."""
    home = tmp_path / "home"
    home.mkdir()
    answered = run_script(NOTHING_AT_IMPORT_PROBE, {"ACERVATOR_TEST_HOME": str(home)})
    assert answered["qt"] == [], answered["qt"]
    assert answered["clock_at_import"] == [], answered
    assert answered["threads_at_import"] == 0, answered
    assert answered["reached_at_import"] == [], answered
    assert answered["made_under_home"] == [], answered
    assert [
        one for one in answered["opened_at_import"] if "main_window" in one
    ] == [], answered
    assert answered["title"] == "Acervator v1.2.3"
    assert answered["built_on_request"] is True
    assert answered["method"] == METHOD_NAME


def test_the_import_probe_can_report_a_file_a_clock_and_a_connection(tmp_path):
    """The import probe reports nothing whatever the module does."""
    home = tmp_path / "home"
    home.mkdir()
    probe = NOTHING_AT_IMPORT_PROBE.replace(
        "from src.gui.main_tabs import main_window_surface as s",
        "time.time()\n"
        "with open(root / 'main_window-seeded.json', 'w') as fh:\n"
        "    fh.write('{}')\n"
        "try:\n"
        "    socket.create_connection(('example.invalid', 443))\n"
        "except OSError:\n"
        "    pass\n"
        "threading.Thread(target=lambda: None).start()\n"
        "from src.gui.main_tabs import main_window_surface as s",
    )
    answered = run_script(probe, {"ACERVATOR_TEST_HOME": str(home)})
    assert answered["clock_at_import"] == ["time"], answered
    assert answered["reached_at_import"] != [], answered
    assert answered["made_under_home"] != [], answered
    assert [
        one for one in answered["opened_at_import"] if "main_window" in one
    ] != [], answered


def test_the_surface_loads_no_qt_module_and_reaches_for_nothing():
    """The surface grew an import that pulls Qt into the backend."""
    tree = parsed(SURFACE_SOURCE)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    reached = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in ("read_text", "write_text", "mkdir", "urlopen", "monotonic"):
        assert forbidden not in reached, forbidden


def test_the_import_scan_reports_a_module_the_shipped_file_does_load():
    """The import scan reports nothing whatever a file imports."""
    imported = {
        node.module or ""
        for node in ast.walk(parsed(SHIPPED_SOURCE))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in imported), imported


def test_the_surface_reads_no_value_out_of_the_shipped_file():
    """The surface reads the shipped file rather than carrying its own values."""
    named = {
        node.module or ""
        for node in ast.walk(parsed(SURFACE_SOURCE))
        if isinstance(node, ast.ImportFrom)
    }
    assert "src.gui.main_window" not in named, named
    assert not any(name.endswith("main_window") for name in named), named


def test_the_tokens_the_two_sides_read_come_from_design_system():
    """A token was copied instead of read, so the two sides can drift."""
    assert surface.API_PILL_IDLE_COLOUR == ds.CARD_METRIC_LABEL
    assert surface.API_PILL_RED_COLOUR == ds.ERROR
    assert surface.API_PILL_AMBER_COLOUR == ds.FOLD_RATIO_AMBER
    assert surface.API_PILL_GREEN_COLOUR == ds.SUCCESS
    assert surface.AI_OFF_COLOUR == ds.TEXT_PLACEHOLDER
    assert surface.AI_READY_COLOUR == ds.STATUS_AUTHENTICATED
    assert surface.MODE_BUTTON_COLOUR["crypto"] == ds.LAYER_CRYPTO
    assert surface.MODE_BUTTON_COLOUR["stock"] == ds.LAYER_STOCK


def flat_colours(values) -> list:
    """Every colour whose channels all match, which a swap cannot report."""
    return sorted(
        f"{name}={value}"
        for name, value in values.items()
        if isinstance(value, str) and value.startswith("#") and len(set(value[1:])) == 1
    )


def test_two_pill_colours_have_channels_a_swap_cannot_report():
    """A pill colour a channel swap cannot report was added or removed.

    `#888` and `#555555` are grey: red, green and blue carry one value,
    so swapping two channels paints the same pixel. Every other pill
    colour is proved by the swap check below.
    """
    colours = {
        "idle": surface.API_PILL_IDLE_COLOUR,
        "red": surface.API_PILL_RED_COLOUR,
        "amber": surface.API_PILL_AMBER_COLOUR,
        "green": surface.API_PILL_GREEN_COLOUR,
        "ai_off": surface.AI_OFF_COLOUR,
        "ai_ready": surface.AI_READY_COLOUR,
    }
    assert flat_colours(colours) == ["ai_off=#555555", "idle=#888"]


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """A swapped colour channel reaches no comparison."""
    assert digest(surface.API_PILL_GREEN_COLOUR) != digest("#88ff00")
    assert surface.API_PILL_GREEN_COLOUR == "#00ff88"


def test_the_channel_reader_reports_a_colour_whose_channels_match():
    """The channel reader reports nothing whatever a colour holds."""
    assert flat_colours({"c": "#888"}) == ["c=#888"]
    assert flat_colours({"c": "#00ff88"}) == []


# Pictures


def pill_payload(case):
    """The pill payload one side produces, sealed as it comes off that side."""
    if case == "shipped":
        return sealed(shipped_pill(PILL_CASES["red"]))
    return sealed(surface_pill(PILL_CASES["red"]))


def pill_from_payload(payload):
    """One label painted only from a sealed pill payload."""
    payload = unaltered(payload)
    label = hold(QLabel(payload["text"]))
    label.setStyleSheet(payload["style"])
    return label


def test_the_two_sides_paint_one_status_line_pill():
    """The surface painted a different pill than the status line."""
    old_payload = pill_payload("shipped")
    new_payload = pill_payload("surface")
    assert_same_skin(
        build_old_side=lambda: pill_from_payload(old_payload),
        build_new_side=lambda: pill_from_payload(new_payload),
        size=PILL_SIZE,
        control_rule=CONTROL_RULE,
    )
    release()


def test_the_pill_render_reports_more_than_one_colour():
    """The pill render paints one colour, so no comparison of it can report."""
    from tests.qt_pixel import render_widget

    counts = {}
    for name in ("green", "amber", "red"):
        payload = sealed(surface_pill(PILL_CASES[name]))
        counts[name] = assert_picture_can_report(
            render_widget(pill_from_payload(payload), PILL_SIZE), note=name
        )
    assert all(count >= 2 for count in counts.values()), counts
    release()


def test_two_different_real_pills_paint_two_pictures():
    """The picture comparison passes whatever the surface painted."""
    from tests.qt_pixel import render_widget

    old_payload = pill_payload("shipped")
    new_payload = sealed(surface_pill(PILL_CASES["green"]))
    assert_cases_paint_differently(
        old_side=render_widget(pill_from_payload(old_payload), PILL_SIZE),
        new_side=render_widget(pill_from_payload(new_payload), PILL_SIZE),
    )
    release()


def test_the_seal_refuses_a_payload_that_moved_after_it_came_off_a_side():
    """A changed payload reaches a render, which measures the host's fonts."""
    payload = sealed(surface_pill(PILL_CASES["red"]))
    payload["text"] = "changed after the seal"
    with pytest.raises(AssertionError):
        pill_from_payload(payload)
    release()


def test_the_colour_count_moves_with_the_pill_state():
    """The colour counter reads one number whatever the pill shows."""
    from tests.qt_pixel import render_widget

    counted = {}
    for name in ("green", "red"):
        payload = sealed(surface_pill(PILL_CASES[name]))
        counted[name] = colour_count(
            render_widget(pill_from_payload(payload), PILL_SIZE)
        )
    assert counted["green"] >= 2 and counted["red"] >= 2, counted
    release()


# The build machine


# What one bad stored value does to this window


HOSTILE_VALUES = {
    "true": True,
    "not_a_number": NOT_A_NUMBER,
    "infinity": INFINITY,
    "minus_infinity": MINUS_INFINITY,
    "text": "not a number",
    "number_as_text": "12.7",
    "decimal": 12.7,
    "ten_to_400": TEN_TO_400,
}

STORED_FIELDS = (
    "total_scrummed_usd",
    "total_folded_usd",
    "total_realised_pnl",
    "total_trades",
    "running",
    "total_errors_lifetime",
    "wallet_cash_usd",
    "crypto_position_value_usd",
)


def bare_reading(field, value):
    """What the shipped window does when one stored value holds `value`."""
    written = shipped_tick(aggregate(**{field: value}))
    clean = shipped_tick(aggregate())
    cards = written["cards"]
    changed = [
        name
        for name in surface.CARD_ORDER
        if cards.get(name) != clean["cards"].get(name)
    ]
    lost = [
        name
        for name in surface.CARD_ORDER
        if clean["cards"].get(name) is not None and cards.get(name) is None
    ]
    return {
        "field": field,
        "stopped": written["tick_error"],
        "shown": {name: cards.get(name) for name in changed},
        "lost": lost,
        "panel_lost": clean["spendable"] is not None and written["spendable"] is None,
    }


@pytest.mark.parametrize("field", STORED_FIELDS)
@pytest.mark.parametrize("name", sorted(HOSTILE_VALUES))
def test_one_bad_stored_value_reads_the_same_way_on_both_sides(field, name):
    """The surface answers a bad stored value differently than the window."""
    value = HOSTILE_VALUES[name]
    reading = aggregate(**{field: value})
    old_side = shipped_tick(reading)
    new_side = surface_tick(reading)
    assert leaves(old_side) == leaves(new_side), f"{field} = {name}"


@pytest.mark.parametrize("field", STORED_FIELDS)
@pytest.mark.parametrize("name", sorted(HOSTILE_VALUES))
def test_the_bare_reading_audit_reports_what_one_bad_value_costs(field, name):
    """A bad stored value costs more than the audit table records.

    The audit is a measurement, not a repair: nothing here asks the
    window to guard a field. The assertion is that a bad value costs at
    most its own card and the panel below it, and never a card the
    reading never touched.
    """
    answer = bare_reading(field, HOSTILE_VALUES[name])
    if answer["stopped"] is None:
        assert answer["lost"] == [], (
            f"{field} = {name}: the tick did not stop, yet lost " f"{answer['lost']}"
        )
    else:
        assert answer["panel_lost"] is True, (
            f"{field} = {name}: the tick stopped with {answer['stopped']} "
            f"but the spendable panel was still written"
        )


def test_the_bare_reading_audit_reports_both_a_quiet_swap_and_a_stop():
    """The audit reads one answer whatever the stored value is."""
    substituted = bare_reading("total_scrummed_usd", True)
    assert substituted["stopped"] is None
    assert substituted["shown"]["scrummed"] == "$1.00"

    silent = bare_reading("total_scrummed_usd", NOT_A_NUMBER)
    assert silent["stopped"] is None
    assert silent["shown"]["scrummed"] == "$nan"

    stopped = bare_reading("total_scrummed_usd", TEN_TO_400)
    assert stopped["stopped"] == "OverflowError"
    assert stopped["panel_lost"] is True


def test_a_stored_theme_name_nobody_recognises_stops_the_settings_save():
    """A bad stored theme name costs only its own field."""
    from src.gui.theme_engine import THEMES

    themes = [(one, one) for one in THEMES]
    model = surface.MainWindowModel(
        settings=surface.SettingsSource({"theme": "no such theme"}),
        themes=surface.ThemeSource(themes),
        fleet=surface.FleetSource(),
    )
    with pytest.raises(ValueError):
        model.settings_changed()
    assert model.log_lines == []
    assert model.ai_pill_text == ""

    good = surface.MainWindowModel(
        settings=surface.SettingsSource({"theme": themes[0][0]}),
        themes=surface.ThemeSource(themes),
        fleet=surface.FleetSource(),
    )
    good.settings_changed()
    assert [one["text"] for one in good.log_lines][-1] == surface.SETTINGS_SAVED_LOG


def test_a_stored_ai_config_that_is_not_a_mapping_stops_the_settings_save():
    """A bad stored AI config costs only its own pill."""
    from src.gui.theme_engine import THEMES

    themes = [(one, one) for one in THEMES]
    model = surface.MainWindowModel(
        settings=surface.SettingsSource(
            {"theme": next(iter(THEMES)), "ai_monitor": True}
        ),
        themes=surface.ThemeSource(themes),
        fleet=surface.FleetSource(),
    )
    with pytest.raises(AttributeError):
        model.settings_changed()
    assert [one["text"] for one in model.log_lines] == [
        surface.THEME_SWITCHED_LOG_FORMAT.format(name=next(iter(THEMES)))
    ]


# The skin control, and which rule moves a pixel first


CANDIDATE_RULES = (
    "QLabel { background: #7d1a4a; }",
    "QLabel { border: 3px solid #14407d; }",
    "QLabel { color: #7d1a4a; }",
    CONTROL_RULE,
)


def test_the_control_rule_chosen_is_one_that_moves_a_pixel():
    """The skin control uses a rule that reaches no pixel on this label."""
    from tests.fixtures.surface_pictures import _picture_digest
    from tests.qt_pixel import render_widget

    payload = sealed(surface_pill(PILL_CASES["red"]))
    plain = _picture_digest(render_widget(pill_from_payload(payload), PILL_SIZE))
    moved = []
    for rule in CANDIDATE_RULES:
        widget = pill_from_payload(payload)
        widget.setStyleSheet(rule)
        if _picture_digest(render_widget(widget, PILL_SIZE)) != plain:
            moved.append(rule)
    assert CONTROL_RULE in moved, moved
    assert moved[0] == CANDIDATE_RULES[0], moved
    release()


def test_this_file_imports_only_what_the_fast_lane_installs():
    """This file needs a package the CI fast lane never installs."""
    from tests.test_ci_fast_lane_packages import offending_imports

    offences = [
        line
        for line in offending_imports(REPO_ROOT / "tests")
        if Path(__file__).name in line
    ]
    assert offences == [], offences
