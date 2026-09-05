"""The Qt Status tab and the Qt-free surface, driven side by side.

A failure means the view model describes a different row, a different
label, a different colour, a different number format, a different
tooltip, a different layout number or a different branch than
``StatusTabMixin`` builds on the same input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import live_status_tab_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
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
TAB_SOURCE = REPO_ROOT / "src" / "gui" / "live_settings" / "status_tab.py"
WIRING_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (1320, 620)

CONNECT_TOTAL = 0
WIRING_NEIGHBOUR_CONNECT_TOTAL = 1
TIMER_NEIGHBOUR_BUILD_TOTAL = 1
BUS_NEIGHBOUR_TOPIC_TOTAL = 2
SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 1
SHIPPED_FUNCTION_TOTAL = 1
PAYLOAD_KEY_TOTAL = 23
CONSTANT_TOTAL = 109

FIXED_NOW = 1_700_000_000.0


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


# The bot and stats the Qt tab is driven with; the surface is driven with
# its own and neither side reads the other's.


class Stats:
    """The bot's stats object, holding the seven exchange readings.

    A reading named in `missing` is absent, which drives the tab's own
    defaults.
    """

    def __init__(
        self,
        realised=0.0,
        avg_entry=0.0,
        cost_basis=0.0,
        unrealised=0.0,
        fees=0.0,
        trade_count=0,
        fresh_ts=0.0,
        missing=(),
    ):
        held = [
            ["realized_pnl_exchange", realised],
            ["avg_entry_exchange", avg_entry],
            ["cost_basis_total_exchange", cost_basis],
            ["unrealised_pnl", unrealised],
            ["fees_paid_exchange", fees],
            ["exchange_trade_count", trade_count],
            ["exchange_data_fresh_ts", fresh_ts],
        ]
        for name, value in held:
            if name not in missing:
                setattr(self, name, value)


class Bot:
    """The running bot the tab reads its status and its stats from."""

    def __init__(self, status=None, stats=None, status_raises=None, with_stats=True):
        self.held_status = {} if status is None else status
        self.status_raises = status_raises
        if with_stats:
            self.stats = stats

    def get_status(self):
        if self.status_raises is not None:
            raise self.status_raises
        return self.held_status


HOST_ACCESSIBLE_NAME = ""


def host_class():
    """The window the tab lives in, holding only what the mixin declares."""
    from PySide6.QtWidgets import QWidget

    from src.gui.live_settings.status_tab import StatusTabMixin

    class Host(StatusTabMixin, QWidget):
        def __init__(self, bot):
            super().__init__()
            self.setAccessibleName(HOST_ACCESSIBLE_NAME)
            self._bot = bot
            self.forms = []

        def _configure_form(self, form):
            self.forms.append(form)

    return Host


class FixedClock:
    """Hold the process clock still, and put it back on the way out.

    Both sides read the age of the exchange data from ``time.time``, so
    one swap drives them together and neither depends on when the run
    happened.
    """

    def __init__(self, reading=FIXED_NOW):
        self.reading = reading
        self.first = None

    def __enter__(self):
        self.first = time.time
        time.time = lambda: self.reading
        return self

    def __exit__(self, _kind, _value, _trace):
        time.time = self.first
        return False


# The inputs. One scenario drives both sides.


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "O'Brien's venue said no"
LAST_ERROR_TEXT = "venue refused the order"

FRESH_TS_HAPPY = FIXED_NOW - 125.0


def stats_reading(**named):
    """The status dictionary the bot hands the tab."""
    fields = {
        "total_trades": 12,
        "active_buys": 2,
        "active_sells": 3,
        "current_price": 0.00002345,
        "uptime": 3661.4,
        "last_error": LAST_ERROR_TEXT,
    }
    fields.update(named)
    return {"stats": fields}


def scenario(name, **named):
    """One driving set: the bot's status reading and its stats object."""
    spec = {
        "name": name,
        "status": stats_reading(),
        "status_raises": None,
        "with_stats": True,
        "has_stats_object": True,
        "realised": 12.5,
        "avg_entry": 0.000123,
        "cost_basis": 456.789,
        "unrealised": -3.25,
        "fees": 1.5,
        "trade_count": 7,
        "fresh_ts": FRESH_TS_HAPPY,
        "missing": (),
    }
    spec.update(named)
    return spec


ALL_READINGS = (
    "realized_pnl_exchange",
    "avg_entry_exchange",
    "cost_basis_total_exchange",
    "unrealised_pnl",
    "fees_paid_exchange",
    "exchange_trade_count",
    "exchange_data_fresh_ts",
)

SCENARIOS = [
    scenario("happy"),
    scenario("no_stats_attribute", with_stats=False),
    scenario("stats_object_is_none", has_stats_object=False),
    scenario("every_reading_missing", missing=ALL_READINGS),
    scenario("refresh_pending", fresh_ts=0.0),
    scenario("fresh_ts_is_negative", fresh_ts=-5.0),
    scenario("age_under_a_minute", fresh_ts=FIXED_NOW - 30.0),
    scenario("age_exactly_a_minute", fresh_ts=FIXED_NOW - 60.0),
    scenario("age_in_the_future", fresh_ts=FIXED_NOW + 45.0),
    scenario(
        "zero_everywhere",
        realised=0.0,
        avg_entry=0.0,
        cost_basis=0.0,
        unrealised=0.0,
        fees=0.0,
        trade_count=0,
        fresh_ts=FIXED_NOW - 10.0,
    ),
    scenario(
        "negative_everywhere",
        realised=-12.5,
        avg_entry=-0.000123,
        cost_basis=-456.789,
        unrealised=-3.25,
        fees=-1.5,
        trade_count=-7,
    ),
    scenario(
        "a_thousand_million",
        realised=1e9,
        avg_entry=1e9,
        cost_basis=1e9,
        unrealised=1e9,
        fees=1e9,
        trade_count=1_000_000_000,
    ),
    scenario(
        "one_billionth",
        realised=1e-9,
        avg_entry=1e-9,
        cost_basis=1e-9,
        unrealised=1e-9,
        fees=1e-9,
    ),
    scenario(
        "infinity",
        realised=math.inf,
        avg_entry=math.inf,
        cost_basis=math.inf,
        unrealised=math.inf,
        fees=math.inf,
    ),
    scenario(
        "minus_infinity",
        realised=-math.inf,
        avg_entry=-math.inf,
        cost_basis=-math.inf,
        unrealised=-math.inf,
        fees=-math.inf,
    ),
    scenario(
        "not_a_number",
        realised=math.nan,
        avg_entry=math.nan,
        cost_basis=math.nan,
        unrealised=math.nan,
        fees=math.nan,
    ),
    scenario("realised_is_none", realised=None),
    scenario("realised_is_empty_text", realised=""),
    scenario("realised_is_a_number_written_as_text", realised="12.5"),
    scenario("realised_is_text", realised="lots"),
    scenario("trade_count_is_a_number_written_as_text", trade_count="7"),
    scenario("trade_count_is_text", trade_count="seven"),
    scenario("trade_count_is_infinite", trade_count=math.inf),
    scenario("trade_count_is_not_a_number", trade_count=math.nan),
    scenario("status_read_failed", status_raises=RuntimeError("bot is gone")),
    scenario("status_is_a_list", status=["not a mapping"]),
    scenario("status_has_no_stats", status={}),
    scenario("stats_reading_is_empty", status={"stats": {}}),
    scenario("stats_reading_is_a_list", status={"stats": ["a", "b"]}),
    scenario(
        "stats_keys_in_wrong_capitals",
        status={
            "stats": {
                "Total_Trades": 12,
                "Active_Buys": 2,
                "Active_Sells": 3,
                "Current_Price": 0.5,
                "Uptime": 60.0,
                "Last_Error": "boom",
            }
        },
    ),
    scenario("price_is_zero", status=stats_reading(current_price=0)),
    scenario("price_is_negative", status=stats_reading(current_price=-1.5)),
    scenario("price_is_a_thousand_million", status=stats_reading(current_price=1e9)),
    scenario("price_is_one_billionth", status=stats_reading(current_price=1e-9)),
    scenario("price_is_infinite", status=stats_reading(current_price=math.inf)),
    scenario("price_is_minus_infinity", status=stats_reading(current_price=-math.inf)),
    scenario("price_is_not_a_number", status=stats_reading(current_price=math.nan)),
    scenario("price_is_text", status=stats_reading(current_price="30")),
    scenario("price_is_none", status=stats_reading(current_price=None)),
    scenario("uptime_is_zero", status=stats_reading(uptime=0)),
    scenario("uptime_is_negative", status=stats_reading(uptime=-90.5)),
    scenario("uptime_is_infinite", status=stats_reading(uptime=math.inf)),
    scenario("uptime_is_not_a_number", status=stats_reading(uptime=math.nan)),
    scenario("uptime_is_text", status=stats_reading(uptime="30")),
    scenario("total_trades_is_none", status=stats_reading(total_trades=None)),
    scenario("total_trades_is_text", status=stats_reading(total_trades="many")),
    scenario(
        "total_trades_is_a_thousand_million",
        status=stats_reading(total_trades=1_000_000_000),
    ),
    scenario("last_error_is_unicode", status=stats_reading(last_error=UNICODE_TEXT)),
    scenario(
        "last_error_is_two_hundred_characters",
        status=stats_reading(last_error=LONG_TEXT),
    ),
    scenario("last_error_is_markup", status=stats_reading(last_error=MARKUP_TEXT)),
    scenario(
        "last_error_has_an_apostrophe", status=stats_reading(last_error=APOSTROPHE_TEXT)
    ),
    scenario("last_error_has_a_newline", status=stats_reading(last_error=NEWLINE_TEXT)),
    scenario("last_error_in_wrong_capitals", status=stats_reading(last_error="BOOM")),
    scenario("last_error_is_empty", status=stats_reading(last_error="")),
    scenario("last_error_is_zero", status=stats_reading(last_error=0)),
    scenario("last_error_is_a_number", status=stats_reading(last_error=12345)),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}


# Driving the two sides


def old_stats(spec):
    if not spec["has_stats_object"]:
        return None
    return Stats(
        realised=spec["realised"],
        avg_entry=spec["avg_entry"],
        cost_basis=spec["cost_basis"],
        unrealised=spec["unrealised"],
        fees=spec["fees"],
        trade_count=spec["trade_count"],
        fresh_ts=spec["fresh_ts"],
        missing=spec["missing"],
    )


def old_bot(spec):
    return Bot(
        status=spec["status"],
        stats=old_stats(spec),
        status_raises=spec["status_raises"],
        with_stats=spec["with_stats"],
    )


def new_bot(spec):
    stats = None
    if spec["has_stats_object"]:
        stats = surface.BotStats(
            realised=spec["realised"],
            avg_entry=spec["avg_entry"],
            cost_basis=spec["cost_basis"],
            unrealised=spec["unrealised"],
            fees=spec["fees"],
            trade_count=spec["trade_count"],
            fresh_ts=spec["fresh_ts"],
            missing=spec["missing"],
        )
    return surface.BotSource(
        status=spec["status"],
        stats=stats,
        status_raises=spec["status_raises"],
        with_stats=spec["with_stats"],
    )


def drive_old(spec):
    """Build the Qt tab against a held clock and hand it back."""
    app()
    host = host_class()(old_bot(spec))
    with FixedClock():
        tab = host._create_status_tab()
    return {"tab": tab, "host": host}


def drive_new(spec):
    """Build the surface model against the same held clock."""
    model = surface.LiveStatusTabModel(new_bot(spec))
    with FixedClock():
        model.build()
    return {"model": model}


# Reading the two sides


def layout_order(layout):
    """The class of each item the layout holds, in the order it was added."""
    order = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        order.append("stretch" if widget is None else type(widget).__name__)
    return order


def form_rows(form):
    """Every row of the Statistics form: label, value, skin, note and wrap."""
    from PySide6.QtWidgets import QFormLayout

    rows = []
    for index in range(form.rowCount()):
        label = form.itemAt(index, QFormLayout.ItemRole.LabelRole).widget()
        field = form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget()
        rows.append(
            [
                label.text(),
                field.text(),
                field.styleSheet(),
                field.toolTip(),
                field.wordWrap(),
            ]
        )
    return rows


def qt_trace(driven):
    """Every value the built Qt tab can be asked for, as plain data."""
    tab = driven["tab"]
    outer = tab.layout()
    group = outer.itemAt(0).widget()
    form = group.layout()
    return {
        "accessible_name": tab.accessibleName(),
        "container": {"spacing_px": outer.spacing()},
        "order": layout_order(outer),
        "stats_group": {"title": group.title()},
        "stats_form": {"configured": len(driven["host"].forms) == 1},
        "rows": form_rows(form),
        "row_count": form.rowCount(),
    }


def surface_trace(driven):
    """The same values, read from the Qt-free view model."""
    model = driven["model"]
    payload = surface.build_view_model(model)
    order = []
    if payload["stats_group"]["shown"]:
        order.append("QGroupBox")
    if payload["stretch_shown"]:
        order.append("stretch")
    return {
        "accessible_name": payload["accessible_name"],
        "container": {"spacing_px": payload["container"]["spacing_px"]},
        "order": order,
        "stats_group": {"title": payload["stats_group"]["title"]},
        "stats_form": {"configured": payload["stats_form"]["configured"]},
        "rows": [list(one) for one in payload["rows"]],
        "row_count": payload["row_count"],
    }


def headline(text: str) -> str:
    """The first line of an error message.

    A message that goes on to list every type it accepts would make a
    comparison of the whole text pass on wording alone.
    """
    lines = str(text).splitlines()
    return lines[0] if lines else ""


def outcome(work):
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": headline(exc),
        }


def old_outcome(spec):
    return outcome(lambda: qt_trace(drive_old(spec)))


def new_outcome(spec):
    return outcome(lambda: surface_trace(drive_new(spec)))


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_tab(name):
    """A row, label, colour, number, tooltip or branch differs between them."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        assert new["message"] == old["message"], (name, old, new)
        return
    assert as_text(new["value"]) == as_text(old["value"]), name
    assert digest(new["value"]) == digest(old["value"]), name


REFUSING_SCENARIOS = (
    "realised_is_text",
    "trade_count_is_text",
    "trade_count_is_infinite",
    "trade_count_is_not_a_number",
    "status_read_failed",
    "status_is_a_list",
    "stats_reading_is_a_list",
    "price_is_text",
    "price_is_none",
    "uptime_is_text",
    "last_error_is_a_number",
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
    """One side refused an input the other accepted, or named another error."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["message"]) == (old["error"], old["message"])
    assert old["error"] in (
        "ValueError",
        "TypeError",
        "OverflowError",
        "AttributeError",
        "RuntimeError",
    )
    assert old["message"], name


def test_the_refusal_wording_is_read_one_line_at_a_time():
    """A refusal is compared whole, so its wording carries the check."""
    assert headline("only one line") == "only one line"
    assert headline("first line\nsecond line") == "first line"
    assert headline("") == ""
    spoken = old_outcome(BY_NAME["realised_is_text"])["message"]
    assert "\n" not in spoken
    assert spoken
    assert spoken == new_outcome(BY_NAME["realised_is_text"])["message"]


DIFFERENT_INPUT_PAIR = ("happy", "no_stats_attribute")


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    first, second = DIFFERENT_INPUT_PAIR
    one = old_outcome(BY_NAME[first])["value"]
    other = old_outcome(BY_NAME[second])["value"]
    assert one["row_count"] != other["row_count"], (one["row_count"],)
    assert one["rows"] != other["rows"]
    assert digest(one) != digest(other)
    assert digest(one) == digest(old_outcome(BY_NAME[first])["value"])
    assert len(digest(one)) == 64


def test_the_hash_tells_a_whole_number_from_a_decimal():
    """A whole number and a decimal of one value hash the same."""
    assert 12 == 12.0
    assert digest({"count": 12}) != digest({"count": 12.0})
    assert as_text(12) == "12"
    assert as_text(12.0) == "12.0"


def test_two_not_a_numbers_read_as_one_value_before_comparing():
    """Two not-a-numbers compared directly report a difference that is none."""
    assert math.nan != math.nan
    assert as_text(math.nan) == as_text(math.nan)
    assert digest({"reading": math.nan}) == digest({"reading": math.nan})
    assert digest({"reading": math.nan}) != digest({"reading": math.inf})


@pytest.mark.parametrize(
    "name", ["happy", "refresh_pending", "no_stats_attribute", "every_reading_missing"]
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == 7, sorted(value)
    assert value["rows"], name
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


# Step sequences


def test_a_second_build_carries_the_same_rows_on_both_sides():
    """The second paint of the tab shows the rows of the first twice over."""
    spec = BY_NAME["happy"]
    app()
    host = host_class()(old_bot(spec))
    with FixedClock():
        first_tab = host._create_status_tab()
        second_tab = host._create_status_tab()
    first_rows = form_rows(first_tab.layout().itemAt(0).widget().layout())
    second_rows = form_rows(second_tab.layout().itemAt(0).widget().layout())
    assert first_rows == second_rows
    assert len(host.forms) == 2

    model = surface.LiveStatusTabModel(new_bot(spec))
    with FixedClock():
        model.build()
        one = [list(row) for row in model.rows]
        model.build()
        other = [list(row) for row in model.rows]
    assert one == other
    assert one == first_rows


def test_a_rebuild_after_a_different_reading_keeps_nothing_from_the_first():
    """A row from an earlier paint stayed on the tab after a new reading."""
    pending = BY_NAME["refresh_pending"]
    fresh = BY_NAME["happy"]
    app()
    host = host_class()(old_bot(pending))
    host_two = host_class()(old_bot(fresh))
    with FixedClock():
        pending_tab = host._create_status_tab()
        fresh_tab = host_two._create_status_tab()
    pending_rows = form_rows(pending_tab.layout().itemAt(0).widget().layout())
    fresh_rows = form_rows(fresh_tab.layout().itemAt(0).widget().layout())
    assert pending_rows != fresh_rows

    model = surface.LiveStatusTabModel(new_bot(pending))
    with FixedClock():
        model.build()
        assert [list(row) for row in model.rows] == pending_rows
        model.bot = new_bot(fresh)
        model.build()
        assert [list(row) for row in model.rows] == fresh_rows
    assert [call[0] for call in model.calls].count(surface.BUILD_START) == 1


def test_a_refused_reading_after_a_good_one_leaves_the_error_and_not_the_rows():
    """A refused reading left the last good rows standing under a new paint."""
    model = surface.LiveStatusTabModel(new_bot(BY_NAME["happy"]))
    with FixedClock():
        model.build()
        assert len(model.rows) == 11
        model.bot = new_bot(BY_NAME["realised_is_text"])
        with pytest.raises(ValueError):
            model.build()
    assert model.rows == []
    assert model.group_shown is False


# The enumeration: wiring, signals, classes, methods, timers, topics


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
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


def timer_sites(path) -> list:
    """Every ``QTimer(`` construction in `path`, counted as a call."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        dotted(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path) -> list:
    """Every ``subscribe(`` site in `path`, as the topic it names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def source_functions(path) -> list:
    """Every function the source declares, nested ones included."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def declared_methods(holder) -> list:
    """Every real method `holder` declares. A signal is not a method."""
    from PySide6.QtCore import Signal

    return sorted(
        name
        for name, value in vars(holder).items()
        if callable(value)
        and not name.startswith("__")
        and not isinstance(value, Signal)
    )


def loose_methods(holder) -> list:
    """Every callable `holder` declares, signals counted as methods."""
    return sorted(
        name
        for name, value in vars(holder).items()
        if callable(value) and not name.startswith("__")
    )


def test_the_tab_connects_nothing_and_the_wiring_counter_can_report():
    """The tab wires an action the surface names none of.

    The tab wires nothing, so the counter is pointed at a neighbouring
    control that really does wire one. A counter returning nothing on
    both would be no measurement.
    """
    assert connect_sites(TAB_SOURCE) == []
    assert TAB_SOURCE.read_text(encoding="utf-8").count(".connect(") == CONNECT_TOTAL
    assert surface.ACTIONS == {}
    assert len(surface.ACTIONS) == CONNECT_TOTAL
    neighbour = connect_sites(WIRING_NEIGHBOUR)
    assert len(neighbour) == WIRING_NEIGHBOUR_CONNECT_TOTAL, neighbour
    assert neighbour[0][0] == "self.clicked"


def test_every_shipped_class_method_and_function_has_a_counterpart():
    """The shipped tab gained or lost a class, a method or a function."""
    from src.gui.live_settings import status_tab as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == ["StatusTabMixin"], classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    methods = declared_methods(shipped.StatusTabMixin)
    assert methods == ["_create_status_tab"], methods
    assert len(methods) == SHIPPED_METHOD_TOTAL
    functions = source_functions(TAB_SOURCE)
    assert functions == ["_create_status_tab"], functions
    assert len(functions) == SHIPPED_FUNCTION_TOTAL
    assert callable(surface.LiveStatusTabModel.build)


def test_a_signal_is_not_counted_as_a_method():
    """A signal is callable, so a loose counter reads it as a method.

    The shipped class declares one method and two annotations. The
    counter is pointed at a neighbouring card that really does declare a
    signal, and must leave it out while the loose counter takes it in.
    """
    from PySide6.QtCore import Signal

    from src.gui.launcher import ModeCard
    from src.gui.live_settings.status_tab import StatusTabMixin

    assert isinstance(vars(ModeCard)["clicked"], Signal)
    assert callable(vars(ModeCard)["clicked"])
    assert "clicked" in loose_methods(ModeCard)
    assert "clicked" not in declared_methods(ModeCard)
    assert "mousePressEvent" in declared_methods(ModeCard)
    assert declared_methods(StatusTabMixin) == ["_create_status_tab"]
    assert loose_methods(StatusTabMixin) == ["_create_status_tab"]
    assert "_bot" not in vars(StatusTabMixin)
    assert "_configure_form" not in vars(StatusTabMixin)
    assert StatusTabMixin.__annotations__ == {
        "_bot": "Any",
        "_configure_form": "Callable[..., Any]",
    }


SURFACE_CLASSES = {
    "LiveStatusTabModel": "StatusTabMixin",
    "BotSource": "the running bot StatusTabMixin reads",
    "BotStats": "the stats object StatusTabMixin pulls exchange health from",
}

SURFACE_MODEL_METHODS = ("__init__", "build", "build_exchange_rows", "now")


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["LiveStatusTabModel"] == "StatusTabMixin"
    model_methods = sorted(
        name
        for name, value in vars(surface.LiveStatusTabModel).items()
        if callable(value) and (not name.startswith("__") or name == "__init__")
    )
    assert model_methods == sorted(SURFACE_MODEL_METHODS), model_methods


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "InventedModel" not in SURFACE_CLASSES
    assert not hasattr(surface, "InventedModel")
    with pytest.raises(AttributeError):
        getattr(surface.LiveStatusTabModel, "invented_method")


def test_the_tab_holds_no_timer_and_the_counter_can_report():
    """The tab runs a timer the surface declares no delay for.

    The shipped tab builds none, so the counter is pointed at the
    screen that really does build one. The counter reads a construction
    and not a name, so an import line alone is not a timer.
    """
    assert timer_sites(TAB_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    built = timer_sites(TIMER_NEIGHBOUR)
    assert len(built) == TIMER_NEIGHBOUR_BUILD_TOTAL, built
    named = TIMER_NEIGHBOUR.read_text(encoding="utf-8").count("QTimer")
    assert named > len(built), (named, built)


def test_the_tab_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The tab listens on a topic the surface names none of."""
    assert bus_sites(TAB_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) == BUS_NEIGHBOUR_TOPIC_TOTAL, neighbour
    assert neighbour == ["wire.created", "wire.removed"]


def test_the_signal_neighbour_and_the_wiring_neighbour_are_different_files():
    """Two controls read one file, so one of the two was never measured."""
    assert SIGNAL_NEIGHBOUR != WIRING_NEIGHBOUR
    assert TIMER_NEIGHBOUR != REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
    assert timer_sites(REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py") == []
    assert timer_sites(TIMER_NEIGHBOUR) != []


# The completeness check


PAYLOAD_KEYS = {
    "ACCESSIBLE_NAME": "accessible_name",
    "ACTIONS": "actions",
    "ACTIVE_BUYS_KEY": "keys.active_buys",
    "ACTIVE_BUYS_ROW_LABEL": "labels.active_buys",
    "ACTIVE_SELLS_KEY": "keys.active_sells",
    "ACTIVE_SELLS_ROW_LABEL": "labels.active_sells",
    "AGE_MINUTES_CUTOFF_S": "thresholds.age_minutes_cutoff_s",
    "AGE_MINUTES_FORMAT": "formats.age_minutes",
    "AGE_SECONDS_FORMAT": "formats.age_seconds",
    "AVG_ENTRY_ATTRIBUTE": "attributes.avg_entry",
    "AVG_ENTRY_ROW_LABEL": "labels.avg_entry",
    "AVG_ENTRY_SHOWN_ABOVE": "thresholds.avg_entry_shown_above",
    "AVG_ENTRY_VALUE_FORMAT": "formats.avg_entry_value",
    "BUS_TOPICS": "bus_topics",
    "CALL_NAMES": "call_names",
    "CONTENT_MARGINS_SET": "container.margins_set",
    "CONTENT_SPACING_PX": "container.spacing_px",
    "COST_BASIS_ATTRIBUTE": "attributes.cost_basis",
    "COST_BASIS_ROW_LABEL": "labels.cost_basis",
    "COST_BASIS_VALUE_FORMAT": "formats.cost_basis_value",
    "CURRENT_PRICE_KEY": "keys.current_price",
    "CURRENT_PRICE_ROW_LABEL": "labels.current_price",
    "DEFAULT_COUNT": "defaults.count",
    "DEFAULT_FRESH_TS": "defaults.fresh_ts",
    "DEFAULT_MONEY": "defaults.money",
    "DEFAULT_PRICE": "defaults.price",
    "DEFAULT_TRADE_COUNT": "defaults.trade_count",
    "DEFAULT_UPTIME": "defaults.uptime",
    "FEES_ATTRIBUTE": "attributes.fees",
    "FEES_ROW_LABEL": "labels.fees",
    "FEES_SHOWN_ABOVE": "thresholds.fees_shown_above",
    "FORM_FIELD_GROWS": "stats_form.field_grows",
    "FORM_HORIZONTAL_SPACING_PX": "stats_form.horizontal_spacing_px",
    "FORM_MARGINS_PX": "stats_form.margins_px",
    "FORM_ROWS_WRAP": "stats_form.rows_wrap",
    "FORM_VERTICAL_SPACING_PX": "stats_form.vertical_spacing_px",
    "FEES_VALUE_FORMAT": "formats.fees_value",
    "FRESH_TS_ATTRIBUTE": "attributes.fresh_ts",
    "FRESH_TS_SHOWN_ABOVE": "thresholds.fresh_ts_shown_above",
    "GAIN_COLOR": "colors.gain",
    "LAST_ERROR_CHARACTER_LIMIT": "thresholds.last_error_character_limit",
    "LAST_ERROR_COLOR": "colors.last_error",
    "LAST_ERROR_KEY": "keys.last_error",
    "LAST_ERROR_ROW_LABEL": "labels.last_error",
    "LAST_ERROR_STYLE_FORMAT": "formats.last_error_style",
    "LOSS_COLOR": "colors.loss",
    "NO_PRICE_TEXT": "texts.no_price",
    "NO_STATS": "no_stats",
    "NO_STYLE": "texts.no_style",
    "NO_TOOLTIP": "texts.no_tooltip",
    "PENDING_COLOR": "colors.pending",
    "PENDING_STYLE_FORMAT": "formats.pending_style",
    "PENDING_TEXT": "texts.pending",
    "PENDING_TOOLTIP": "texts.pending_tooltip",
    "PRICE_SHOWN_ABOVE": "thresholds.price_shown_above",
    "REALISED_ATTRIBUTE": "attributes.realised",
    "REALISED_ROW_LABEL": "labels.realised",
    "REALISED_STYLE_FORMAT": "formats.realised_style",
    "REALISED_TOOLTIP_FORMAT": "formats.realised_tooltip",
    "REALISED_VALUE_FORMAT": "formats.realised_value",
    "ROW_NO_WORD_WRAP": "word_wrap.other_rows",
    "ROW_WORD_WRAP": "word_wrap.error_row",
    "SECONDS_PER_MINUTE": "thresholds.seconds_per_minute",
    "STATS_ATTRIBUTE": "attributes.stats",
    "STATS_FORM_CONFIGURED_BY_HOST": "stats_form.configured_by_host",
    "STATS_GROUP_TITLE": "stats_group.title",
    "STATS_KEY": "keys.stats",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TOTAL_TRADES_KEY": "keys.total_trades",
    "TOTAL_TRADES_ROW_LABEL": "labels.total_trades",
    "TRADE_COUNT_ATTRIBUTE": "attributes.trade_count",
    "UNREALISED_ATTRIBUTE": "attributes.unrealised",
    "UNREALISED_HIDDEN_AT": "thresholds.unrealised_hidden_at",
    "UNREALISED_ROW_LABEL": "labels.unrealised",
    "UNREALISED_STYLE_FORMAT": "formats.unrealised_style",
    "UNREALISED_VALUE_FORMAT": "formats.unrealised_value",
    "UPTIME_KEY": "keys.uptime",
    "UPTIME_ROW_LABEL": "labels.uptime",
    "UPTIME_VALUE_FORMAT": "formats.uptime_value",
}

# The branch markers, each carried inside call_names.
CALL_CONSTANTS = (
    "BUILD_START",
    "BUILD_STATUS",
    "BUILD_FORM",
    "BUILD_EXCHANGE_STATS",
    "BUILD_NO_EXCHANGE_STATS",
    "BUILD_FRESH",
    "BUILD_PENDING",
    "BUILD_AGE_SECONDS",
    "BUILD_AGE_MINUTES",
    "BUILD_REALISED",
    "BUILD_UNREALISED",
    "BUILD_NO_UNREALISED",
    "BUILD_AVG_ENTRY",
    "BUILD_COST_BASIS",
    "BUILD_NO_AVG_ENTRY",
    "BUILD_FEES",
    "BUILD_NO_FEES",
    "BUILD_TOTAL_TRADES",
    "BUILD_ACTIVE_BUYS",
    "BUILD_ACTIVE_SELLS",
    "BUILD_PRICE",
    "BUILD_NO_PRICE",
    "BUILD_UPTIME",
    "BUILD_LAST_ERROR",
    "BUILD_NO_LAST_ERROR",
    "BUILD_GROUP",
    "BUILD_RETURN",
)

# The two values no snapshot key carries: METHOD is the bridge's
# registered name and PANE_MODEL is the tab state it keeps between calls.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_live_status_method",
    "PANE_MODEL": "test_the_bridge_resets_the_tab_state_on_request",
}

STATE_ONLY_KEYS = {"rows", "row_count", "stretch_shown", "calls"}


def at_path(payload, path):
    """The payload value one dotted path names."""
    found = payload
    for step in path.split("."):
        found = found[step]
    return found


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


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read.

    A comparison that reads some of the values passes whether the rest
    match or not. Every value is accounted for here: a snapshot path,
    one of the branch markers, or one of the two named with the check
    that covers it.
    """
    payload = surface.build_view_model(surface.LiveStatusTabModel())
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            carried = at_path(payload, PAYLOAD_KEYS[name])
            if isinstance(value, tuple):
                assert carried == list(value), name
            else:
                assert carried == value, name
        elif name in CALL_CONSTANTS:
            assert value in payload["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(PAYLOAD_KEYS) == 80
    assert len(CALL_CONSTANTS) == 27
    assert len(NOT_IN_THE_SNAPSHOT) == 2


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.LiveStatusTabModel())
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    assert len(payload) == PAYLOAD_KEY_TOTAL
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing.

    A value that reaches no snapshot path and no named exception must
    land in the unaccounted list, or the check above is empty.
    """
    payload = surface.build_view_model(surface.LiveStatusTabModel())
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in CALL_CONSTANTS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "PENDING_TEXT" in surface_constants()
    assert "REALISED_ROW_LABEL" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "LiveStatusTabModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "colors.invented")


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        seen.update(call[0] for call in drive_new(spec)["model"].calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    pending = drive_new(BY_NAME["refresh_pending"])["model"]
    marks = [call[0] for call in pending.calls]
    assert marks.count(surface.BUILD_PENDING) == 1
    assert surface.BUILD_REALISED not in marks
    filled = drive_new(BY_NAME["happy"])["model"]
    filled_marks = [call[0] for call in filled.calls]
    assert surface.BUILD_PENDING not in filled_marks
    assert filled_marks.count(surface.BUILD_REALISED) == 1


# The surface carries its own values


class MovedTokens:
    """A token table whose colours are unlike any the design system holds."""

    SUCCESS = "#111111"
    ERROR = "#222222"
    CARD_METRIC_LABEL = "#333333"


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_tab(monkeypatch):
    """The surface read its values off the tab it replaces.

    A surface that read the shipped tab would follow it, and the whole
    comparison above would be one side read twice. The shipped tab's
    tokens are moved and the surface must not move with them.
    """
    app()
    from src.gui.live_settings import status_tab as shipped

    first = shipped.ds
    spec = BY_NAME["happy"]
    before = qt_trace(drive_old(spec))
    monkeypatch.setattr(shipped, "ds", MovedTokens)
    moved = qt_trace(drive_old(spec))
    moved_skins = [row[2] for row in moved["rows"]]
    before_skins = [row[2] for row in before["rows"]]
    assert any(MovedTokens.SUCCESS in skin for skin in moved_skins), moved_skins
    assert any(MovedTokens.ERROR in skin for skin in moved_skins), moved_skins
    assert moved_skins != before_skins
    assert not any(MovedTokens.SUCCESS in skin for skin in before_skins)
    new = surface_trace(drive_new(spec))
    new_skins = [row[2] for row in new["rows"]]
    assert not any(MovedTokens.SUCCESS in skin for skin in new_skins), new_skins
    assert not any(MovedTokens.ERROR in skin for skin in new_skins), new_skins
    assert new["rows"] == before["rows"]
    monkeypatch.undo()
    assert shipped.ds is first
    assert qt_trace(drive_old(spec))["rows"] == before["rows"]


def test_the_comparison_names_exactly_which_value_moved(monkeypatch):
    """The comparison reports that something moved without saying what."""
    app()
    from src.gui.live_settings import status_tab as shipped

    spec = BY_NAME["happy"]
    before = qt_trace(drive_old(spec))
    monkeypatch.setattr(shipped, "ds", MovedTokens)
    moved = qt_trace(drive_old(spec))
    monkeypatch.undo()
    apart = [
        index
        for index, (was, now) in enumerate(zip(before["rows"], moved["rows"]))
        if was != now
    ]
    assert apart == [0, 1, 10], apart
    assert before["rows"][0][0] == surface.REALISED_ROW_LABEL
    assert before["rows"][1][0] == surface.UNREALISED_ROW_LABEL
    assert before["rows"][10][0] == surface.LAST_ERROR_ROW_LABEL
    assert [before["rows"][i][1] for i in apart] == [
        moved["rows"][i][1] for i in apart
    ], "the value text moved as well as the colour"


def test_the_surface_does_not_follow_a_tab_that_builds_nothing(monkeypatch):
    """The surface asked the shipped tab to build its controls."""
    app()
    from src.gui.live_settings import status_tab as shipped

    first = shipped.StatusTabMixin._create_status_tab
    payload = surface.build_view_model(surface.LiveStatusTabModel())
    monkeypatch.setattr(shipped.StatusTabMixin, "_create_status_tab", lambda self: None)
    host = host_class()(old_bot(BY_NAME["happy"]))
    assert host._create_status_tab() is None
    again = surface.build_view_model(surface.LiveStatusTabModel())
    assert again == payload
    assert again["labels"]["realised"] == surface.REALISED_ROW_LABEL
    assert again["texts"]["pending"] == surface.PENDING_TEXT
    monkeypatch.undo()
    assert shipped.StatusTabMixin._create_status_tab is first
    assert host_class()(old_bot(BY_NAME["happy"]))._create_status_tab() is not None


def test_the_shipped_tab_writes_to_no_shared_table():
    """The shipped tab changed something every later test would inherit.

    The tab reads the design tokens and builds widgets. It writes no
    module value and touches no process-wide register, so two builds
    leave the token table, the tab module and the privacy register
    exactly as they were.
    """
    app()
    from src.core import privacy_mask_registry
    from src.gui import design_system
    from src.gui.live_settings import status_tab as shipped

    before_tokens = {
        name: getattr(design_system, name)
        for name in ("SUCCESS", "ERROR", "CARD_METRIC_LABEL")
    }
    before_module = sorted(vars(shipped))
    before_register = privacy_mask_registry._SINGLETON
    drive_old(BY_NAME["happy"])
    drive_old(BY_NAME["refresh_pending"])
    assert {name: getattr(design_system, name) for name in before_tokens} == (
        before_tokens
    )
    assert sorted(vars(shipped)) == before_module
    assert shipped.ds is design_system
    assert privacy_mask_registry._SINGLETON is before_register


def test_the_surface_writes_to_no_shared_table():
    """The surface changed a module value every later test would inherit."""
    before = sorted(vars(surface))
    before_actions = dict(surface.ACTIONS)
    before_timers = dict(surface.TIMERS)
    drive_new(BY_NAME["happy"])
    drive_new(BY_NAME["refresh_pending"])
    assert sorted(vars(surface)) == before
    assert surface.ACTIONS == before_actions == {}
    assert surface.TIMERS == before_timers == {}
    assert surface.BUS_TOPICS == ()


# The colours


def canonical(colour):
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    return QColor(colour).name().lower()


DECLARED_COLOURS = (
    ("gain", "GAIN_COLOR"),
    ("loss", "LOSS_COLOR"),
    ("pending", "PENDING_COLOR"),
    ("last_error", "LAST_ERROR_COLOR"),
)


def test_a_colour_written_short_is_compared_written_long():
    """Two colours of one value read as different because one is short."""
    app()
    assert surface.PENDING_COLOR == "#888"
    assert canonical(surface.PENDING_COLOR) == "#888888"
    assert canonical("#888888") == canonical(surface.PENDING_COLOR)
    assert canonical(surface.GAIN_COLOR) == "#00ff88"
    assert canonical(surface.LOSS_COLOR) == "#ff3366"


def test_the_colour_with_equal_channels_is_compared_as_exact_text():
    """A colour with equal channels reads the same with any two swapped.

    The pending colour has three equal channels, so no picture and no
    channel check can report a swap in it. It is compared as text
    against the token the shipped tab reads.
    """
    app()
    from src.gui import design_system

    written = canonical(surface.PENDING_COLOR)
    assert written[1:3] == written[3:5] == written[5:7]
    assert surface.PENDING_COLOR == design_system.CARD_METRIC_LABEL
    equal_channelled = []
    for label, name in DECLARED_COLOURS:
        value = canonical(getattr(surface, name))
        if value[1:3] == value[3:5] == value[5:7]:
            equal_channelled.append(label)
    assert equal_channelled == ["pending"], equal_channelled


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour check passes a value with its channels swapped."""
    app()
    assert canonical(surface.GAIN_COLOR) != canonical("#0088ff")
    assert canonical(surface.LOSS_COLOR) != canonical("#ff6633")
    assert canonical(surface.GAIN_COLOR) != canonical(surface.LOSS_COLOR)


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two declared colours become one when written in full."""
    app()
    written = {
        label: canonical(getattr(surface, name)) for label, name in DECLARED_COLOURS
    }
    assert written["loss"] == written["last_error"]
    assert len(set(written.values())) == 3, written
    assert all(len(value) == 7 for value in written.values()), written


@pytest.mark.parametrize(
    "amount,expected",
    [
        (12.5, surface.GAIN_COLOR),
        (0.0, surface.GAIN_COLOR),
        (-0.0, surface.GAIN_COLOR),
        (-12.5, surface.LOSS_COLOR),
        (math.inf, surface.GAIN_COLOR),
        (-math.inf, surface.LOSS_COLOR),
        (math.nan, surface.LOSS_COLOR),
    ],
)
def test_the_money_colour_follows_the_amount_exactly(amount, expected):
    """A profit of exactly nothing was painted as a loss."""
    assert surface.money_color(amount) == expected


@pytest.mark.parametrize(
    "age_sec,expected",
    [
        (0.0, "0s"),
        (0.4, "0s"),
        (30.0, "30s"),
        (59.9, "60s"),
        (60.0, "1.0m"),
        (125.0, "2.1m"),
        (-45.0, "-45s"),
        (math.inf, "infm"),
        (-math.inf, "-infs"),
    ],
)
def test_the_age_reads_in_seconds_under_a_minute_and_minutes_above(age_sec, expected):
    """The age crossed the minute mark on the wrong side."""
    assert surface.age_text(age_sec) == expected


def test_the_age_of_a_not_a_number_reading_is_read_as_minutes():
    """A not-a-number age took the seconds branch, which its test cannot see."""
    assert surface.age_text(math.nan) == "nanm"
    assert not (math.nan < surface.AGE_MINUTES_CUTOFF_S)


# The pictures


def model_payload(spec=None):
    """The view model after the same driving, stamped."""
    driven = drive_new(spec or BY_NAME["happy"])
    return sealed(surface.build_view_model(driven["model"]))


def widget_painted_by_the_tab(spec=None):
    """The tab the shipped Qt mixin builds, after the same driving."""
    return drive_old(spec or BY_NAME["happy"])["tab"]


def widget_painted_by_the_model(payload):
    """A tab built only from the payload, never from the shipped mixin.

    A payload the caller changed after it came off the surface is
    refused.
    """
    payload = unaltered(payload)
    from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

    app()
    screen = QWidget()
    screen.setAccessibleName(payload["accessible_name"])
    outer = QVBoxLayout(screen)
    outer.setSpacing(payload["container"]["spacing_px"])
    group = QGroupBox(payload["stats_group"]["title"])
    form = QFormLayout(group)
    for label, text, style_sheet, tooltip, word_wrap in payload["rows"]:
        field = QLabel(text)
        if style_sheet:
            field.setStyleSheet(style_sheet)
        if tooltip:
            field.setToolTip(tooltip)
        if word_wrap:
            field.setWordWrap(word_wrap)
        form.addRow(label, field)
    outer.addWidget(group)
    outer.addStretch()
    return screen


PICTURE_SCENARIOS = [
    "happy",
    "refresh_pending",
    "no_stats_attribute",
    "every_reading_missing",
    "last_error_is_two_hundred_characters",
    "negative_everywhere",
]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different tab than the shipped mixin."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(widget_painted_by_the_tab(BY_NAME[name]), PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
        note=note,
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real bot readings, one driven into each side. One carries six
    plain rows and the other eleven, so the two end in different
    states whatever fonts the host holds.
    """
    app()
    first, second = DIFFERENT_INPUT_PAIR
    one = qt_trace(drive_old(BY_NAME[first]))
    other = surface_trace(drive_new(BY_NAME[second]))
    assert one["row_count"] == 11, one["row_count"]
    assert other["row_count"] == 6, other["row_count"]
    assert one["rows"] != other["rows"]
    assert_pictures_differ(
        old_side=render_offscreen(
            widget_painted_by_the_tab(BY_NAME[first]), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[second])), PIXEL_SIZE
        ),
        note="the happy reading against a bot with no exchange stats",
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_tab_shows_more_than_one_colour(name):
    """The two sides matched because the tab painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    for image in (
        render_offscreen(widget_painted_by_the_tab(BY_NAME[name]), PIXEL_SIZE),
        render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
    ):
        assert image.width() > 0 and image.height() > 0, name
        seen = set()
        for x in range(0, image.width(), 5):
            for y in range(0, image.height(), 5):
                seen.add(QColor(image.pixelColor(x, y)).name())
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload()
    payload["rows"][0][1] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(
            surface.build_view_model(surface.LiveStatusTabModel())
        )


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
def test_two_equal_length_row_values_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length values still differ."""
    app()
    assert app_font_advance_px("$+12.5000") == app_font_advance_px("$+99.9999")


@skip_unless_real_fonts
def test_the_two_marker_strings_measure_apart_with_fonts():
    """The glyphs decide their own width, and the marker pair measures alike."""
    app()
    assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)


# What a picture cannot see, read off both sides instead


def test_the_tooltips_are_read_off_both_sides():
    """A note the operator hovers for was compared by picture, which never shows it."""
    app()
    for name in ("happy", "refresh_pending"):
        old = qt_trace(drive_old(BY_NAME[name]))
        new = surface_trace(drive_new(BY_NAME[name]))
        assert [row[3] for row in old["rows"]] == [row[3] for row in new["rows"]], name
    fresh = qt_trace(drive_old(BY_NAME["happy"]))
    assert fresh["rows"][0][3] == surface.realised_tooltip(7, "2.1m")
    assert "FIFO-matched" in fresh["rows"][0][3]
    pending = qt_trace(drive_old(BY_NAME["refresh_pending"]))
    assert pending["rows"][0][3] == surface.PENDING_TOOLTIP
    assert pending["rows"][0][3] != fresh["rows"][0][3]


def test_the_accessible_name_and_the_form_call_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report."""
    app()
    spec = BY_NAME["happy"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    assert new["accessible_name"] == old["accessible_name"] == surface.ACCESSIBLE_NAME
    assert new["stats_form"] == old["stats_form"] == {"configured": True}
    assert surface.STATS_FORM_CONFIGURED_BY_HOST is True


def configured_form():
    """A QFormLayout the shipped dialog's own `_configure_form` has set."""
    from PySide6.QtWidgets import QFormLayout

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    form = QFormLayout()
    BotLiveSettingsDialog._configure_form(None, form)
    return form


def test_the_form_geometry_the_surface_publishes_is_what_the_host_sets():
    from PySide6.QtWidgets import QFormLayout

    app()
    form = configured_form()
    margins = form.contentsMargins()
    assert (
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ) == surface.FORM_MARGINS_PX
    assert form.horizontalSpacing() == surface.FORM_HORIZONTAL_SPACING_PX
    assert form.verticalSpacing() == surface.FORM_VERTICAL_SPACING_PX
    grows = form.fieldGrowthPolicy() == QFormLayout.AllNonFixedFieldsGrow
    assert grows is surface.FORM_FIELD_GROWS
    wraps = form.rowWrapPolicy() != QFormLayout.DontWrapRows
    assert wraps is surface.FORM_ROWS_WRAP


def test_the_form_geometry_check_reads_an_unconfigured_form_apart():
    """The host's own numbers, against a form it never touched."""
    from PySide6.QtWidgets import QFormLayout

    app()
    bare = QFormLayout()
    configured = configured_form()
    assert bare.horizontalSpacing() != configured.horizontalSpacing()
    assert bare.verticalSpacing() != configured.verticalSpacing()


def test_the_word_wrap_is_read_off_both_sides():
    """The error line wraps on one side and runs off the tab on the other."""
    app()
    spec = BY_NAME["last_error_is_two_hundred_characters"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    assert [row[4] for row in old["rows"]] == [row[4] for row in new["rows"]]
    assert old["rows"][-1][0] == surface.LAST_ERROR_ROW_LABEL
    assert old["rows"][-1][4] is surface.ROW_WORD_WRAP
    assert all(row[4] is surface.ROW_NO_WORD_WRAP for row in old["rows"][:-1])


def test_the_long_error_is_cut_to_the_same_length_on_both_sides():
    """A long error line was cut short on one side only."""
    app()
    spec = BY_NAME["last_error_is_two_hundred_characters"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    shown = old["rows"][-1][1]
    assert shown == new["rows"][-1][1]
    assert len(shown) == surface.LAST_ERROR_CHARACTER_LIMIT
    assert len(LONG_TEXT) == 200
    assert shown != LONG_TEXT


def box_of(layout) -> list:
    """One layout's four margins, as plain numbers."""
    margins = layout.contentsMargins()
    return [margins.left(), margins.top(), margins.right(), margins.bottom()]


def untouched_layout_margins():
    """The margins and spacing a fresh column layout starts with.

    The holder widget is kept alive for the read: a layout whose owner
    is collected raises rather than reporting.
    """
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    holder = QWidget()
    plain = QVBoxLayout(holder)
    reading = (box_of(plain), plain.spacing())
    assert holder.layout() is plain
    return reading


def test_the_outer_layout_sets_no_margins_on_either_side():
    """The tab set its own margins on one side and not on the other."""
    app()
    untouched, _untouched_spacing = untouched_layout_margins()
    tab = widget_painted_by_the_tab(BY_NAME["happy"])
    built = widget_painted_by_the_model(model_payload(BY_NAME["happy"]))
    for layout in (tab.layout(), built.layout()):
        assert box_of(layout) == untouched
        assert layout.spacing() == surface.CONTENT_SPACING_PX
    assert surface.CONTENT_MARGINS_SET is False


def test_the_layout_reader_reports_a_spacing_and_a_margin_that_moved():
    """The layout reader returns one answer whatever the layout holds.

    A fresh column layout on this host already spaces its rows by the
    number the tab asks for, so an unset layout cannot be told from a
    set one by that number alone. The reader is proved on a layout
    given a spacing and margins of its own instead.
    """
    app()
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    holder = QWidget()
    moved = QVBoxLayout(holder)
    moved.setSpacing(surface.CONTENT_SPACING_PX + 7)
    moved.setContentsMargins(3, 5, 7, 11)
    assert holder.layout() is moved
    assert moved.spacing() == surface.CONTENT_SPACING_PX + 7
    assert box_of(moved) == [3, 5, 7, 11]
    untouched, _untouched_spacing = untouched_layout_margins()
    assert box_of(moved) != untouched


def test_the_layout_order_is_read_off_both_sides():
    """The stretch that holds the box at the top sits somewhere else."""
    app()
    spec = BY_NAME["happy"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    assert old["order"] == new["order"] == ["QGroupBox", "stretch"]


# The bridge


@pytest.fixture
def fresh_pane_model():
    """Put the tab state the bridge keeps back exactly as it was found.

    A brand-new model is handed to the test, never a cleared one: a
    cleared model keeps any field the clearing does not name.
    """
    first = surface.PANE_MODEL
    surface.PANE_MODEL = surface.LiveStatusTabModel()
    yield
    surface.PANE_MODEL = first


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


BRIDGE_BOT = {
    "status": {
        "stats": {
            "total_trades": 12,
            "active_buys": 2,
            "active_sells": 3,
            "current_price": 0.00002345,
            "uptime": 3661.4,
            "last_error": LAST_ERROR_TEXT,
        }
    },
    "stats": {
        "realised": 12.5,
        "avg_entry": 0.000123,
        "cost_basis": 456.789,
        "unrealised": -3.25,
        "fees": 1.5,
        "trade_count": 7,
        "fresh_ts": FRESH_TS_HAPPY,
    },
}


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_registers_the_live_status_method():
    """The renderer cannot reach the Status tab over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "live_status_tab.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["stats_group"]["title"] == surface.STATS_GROUP_TITLE
    assert result["labels"]["realised"] == surface.REALISED_ROW_LABEL


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_resets_the_tab_state_on_request():
    """The tab state the bridge keeps was never cleared."""
    filled = bridge_answer({"reset": True, "bot": BRIDGE_BOT, "now": FIXED_NOW})[
        "result"
    ]
    assert filled["row_count"] == 11
    assert filled["rows"][0][0] == surface.REALISED_ROW_LABEL
    assert filled["rows"][0][1] == "$+12.5000"
    kept = bridge_answer({})["result"]
    assert kept["row_count"] == 11
    assert kept["rows"] == filled["rows"]
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["row_count"] == 0
    assert cleared["rows"] == []
    assert cleared["stats_group"]["shown"] is False
    assert cleared["calls"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_paints_the_pending_row_when_the_exchange_has_not_answered():
    """A bot awaiting its first exchange refresh showed a profit of zero."""
    pending = dict(BRIDGE_BOT)
    pending["stats"] = dict(BRIDGE_BOT["stats"], fresh_ts=0.0)
    result = bridge_answer({"reset": True, "bot": pending, "now": FIXED_NOW})["result"]
    assert result["rows"][0][1] == surface.PENDING_TEXT
    assert result["rows"][0][3] == surface.PENDING_TOOLTIP
    assert result["row_count"] == 7


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"reset": True, "bot": BRIDGE_BOT, "now": FIXED_NOW})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["row_count"] == 11
    assert encoded["result"]["rows"][-1][0] == surface.LAST_ERROR_ROW_LABEL


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_reports_a_reading_it_cannot_use():
    """A bad reading ended the session instead of answering with an error."""
    broken = dict(BRIDGE_BOT)
    broken["stats"] = dict(BRIDGE_BOT["stats"], realised="lots")
    answer = bridge_answer({"reset": True, "bot": broken, "now": FIXED_NOW})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"
    assert "lots" in answer["error"]["message"]


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'live_status_tab.state', 'params':"
    " {'reset': True, 'now': 1700000000.0, 'bot': {'status': {'stats':"
    " {'total_trades': 12, 'active_buys': 2, 'active_sells': 3,"
    " 'current_price': 0.00002345, 'uptime': 3661.4, 'last_error': 'venue refused the order'}},"
    " 'stats': {'realised': 12.5, 'avg_entry': 0.000123,"
    " 'cost_basis': 456.789, 'unrealised': -3.25, 'fees': 1.5,"
    " 'trade_count': 7, 'fresh_ts': 1699999875.0}}}}),"
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
    """Reaching the Status tab pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["row_count"] == 11
    assert result["rows"][0] == [
        "Realised P/L:",
        "$+12.5000",
        "font-weight: bold; font-size: 13px; color: #00ff88;",
        "Realized P/L pulled from the exchange (FIFO-matched buy/sell pairs "
        "from 7 trades). Refreshed 2.1m ago.",
        False,
    ]
    assert result["rows"][-1] == [
        "Last Error:",
        "venue refused the order",
        "color: #ff3366;",
        "",
        True,
    ]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
