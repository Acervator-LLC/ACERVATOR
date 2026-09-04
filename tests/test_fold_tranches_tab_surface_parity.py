"""The Fold Tranches tab and its Qt-free surface, driven side by side.

A failure means the surface no longer says what the shipped tab says: a
health row, a table cell, a button, a message box, a refusal or the order
of the steps has moved on one side only.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.live_settings import fold_tranches_tab as shipped  # noqa: E402
from src.gui.main_tabs import fold_tranches_tab_surface as surface  # noqa: E402
from tests.fixtures.host_fonts import (  # noqa: E402
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (  # noqa: E402
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

TAB_PATH = REPO_ROOT / "src/gui/live_settings/fold_tranches_tab.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/fold_tranches_tab_surface.py"
NESTED_CLASS_CONTROL = REPO_ROOT / "src/gui/stock_main_window.py"
NESTED_METHOD_CONTROL = REPO_ROOT / "src/gui/indicator_panel.py"
SIGNAL_CONTROL = REPO_ROOT / "src/gui/launcher.py"
TIMER_CONTROL = REPO_ROOT / "src/gui/history_tab.py"
NO_TIMER_CONTROL = REPO_ROOT / "src/gui/main_tabs/history_tab.py"
BUS_CONTROL = REPO_ROOT / "src/gui/bot_visualizer.py"
LIVE_SKIN_CONTROL = REPO_ROOT / "tests/test_alerts_tab_surface_parity.py"

PIXEL_SIZE = (1180, 700)
CONTROL_RULE = "QGroupBox { background: #3a1414; border: 3px solid #7a1414; }"

NOW = 1_700_000_000.0
NAN = float("nan")
INFINITY = float("inf")
HUGE_INT = 10**400
BILLIONTH = 1e-9
THOUSAND_MILLION = 1_000_000_000.0

_alive: list = []


# The shipped side, driven through a stub host


class HostConfig:
    """The bot config the shipped builder reads."""

    def __init__(self, symbol="", despawn_days=0, interval=2.0, fee=1.6):
        self.symbol = symbol
        self.tranche_despawn_days = despawn_days
        self.scrumming_interval_pct = interval
        self.trading_fee_pct = fee


class HostBot:
    """The bot the shipped tab reads, from the same values the surface takes."""

    def __init__(self, spec):
        self.config = HostConfig(
            spec.get("symbol", ""),
            spec.get("despawn_days", 0),
            spec.get("interval", 2.0),
            spec.get("fee", 1.6),
        )
        self.bot_id = spec.get("bot_id", "")
        self._fold_tranches = [dict(one) for one in spec.get("tranches", [])]
        self._stack_tranches = [dict(one) for one in spec.get("stack", [])]
        self._pending_wire_credits = spec.get("parked", 0.0)
        self._pending_wire_ledger = list(spec.get("wire_ledger", []))
        self._tranches_created_lifetime = spec.get("created", 0)
        self._tranches_closed_lifetime = spec.get("closed", 0)
        self._tranches_discarded_lifetime = spec.get("discarded", 0)
        self._tranches_malformed_dropped = spec.get("malformed", 0)
        self._wire_credits_discarded_lifetime = spec.get("wire_discarded", 0.0)
        self._tranches_counters_reset_ts = spec.get("counters_reset_ts", 0.0)
        self.cycle_growth_cap_usd = spec.get("cap_budget", 0.0)
        self._fold_cycle_cap_consumed = spec.get("cap_spent", 0.0)
        self._current_holdings = spec.get("holdings", 0.0)
        self._bot_manager = None
        self.price = spec.get("price", 0.0)
        self.extractor_rows = spec.get("extractor_rows")

    def get_status(self):
        return {"stats": {"current_price": self.price}}

    def open_extractor_tranches(self):
        if self.extractor_rows is None:
            raise AttributeError("this bot lists no Extractor Tranches")
        return self.extractor_rows


class Host(shipped.FoldTranchesTabMixin):
    """A dialog carrying only what the shipped tab builder reads."""

    def __init__(self, bot):
        self._bot = bot
        self._bm = None
        self.saved: list = []

    def _wrap_scrollable(self, content):
        from PySide6.QtWidgets import QFrame, QScrollArea

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(content)
        return area

    def _configure_form(self, form):
        from PySide6.QtWidgets import QFormLayout

        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setContentsMargins(8, 8, 8, 8)

    @staticmethod
    def _format_age(seconds):
        if seconds < 60:
            return f"{int(seconds)}s"
        if seconds < 3600:
            return f"{int(seconds / 60)}m"
        if seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        return f"{seconds / 86400:.1f}d"

    def _save_fleet_state_now(self, what):
        self.saved.append(what)
        return (True, "")


class PinnedClock:
    """Hand every reader of `time.time` one second, then give it back.

    The shipped builder calls the wall clock and the surface does not, so
    a drive of both against one instant needs the shipped side's clock
    held still. `seen` records every read taken while the swap was up, so
    a drive that never read it is visible, and `restored` is proved after
    every drive, including one that refused part way.
    """

    def __init__(self, at):
        self.at = at
        self.seen = 0
        self.original = None
        self.refused = None
        self.refusal = None
        self.traced = False

    def __enter__(self):
        self.original = time.time
        clock = self

        def frozen():
            clock.seen += 1
            return clock.at

        time.time = frozen
        return self

    def __exit__(self, kind, value, trace):
        self.refused = kind
        self.refusal = value
        self.traced = trace is not None
        time.time = self.original
        return False


def app():
    """The one application object, with this run's font choice applied."""
    from PySide6.QtWidgets import QApplication

    load_run_fonts()
    return QApplication.instance()


def hold(widget):
    """Keep `widget` alive for the run so no render reads a freed object."""
    _alive.append(widget)
    return widget


def otd_for(spec):
    """The two OTD numbers the shipped builder reads for this bot."""
    from src.trading.otd_math import (
        fold_rebuy_factor_from_pct,
        minimum_opposing_trade_distance_pct_from_config,
    )

    config = HostConfig(
        spec.get("symbol", ""),
        spec.get("despawn_days", 0),
        spec.get("interval", 2.0),
        spec.get("fee", 1.6),
    )
    pct = minimum_opposing_trade_distance_pct_from_config(config)
    return [pct, fold_rebuy_factor_from_pct(pct)]


# Reading one side into one snapshot


def reset_stamp(value):
    """One reset stamp as the shipped row prints it, or None.

    Applied to the surface's raw number with the surface's own format, so
    the two sides carry one string and neither states this host's zone.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return time.strftime(
        surface.COUNTERS_RESET_TIME_FORMAT, time.localtime(float(value))
    )


def read_form(group):
    """Every label and value of one health form, in the order shown."""
    from PySide6.QtWidgets import QFormLayout

    form = group.layout()
    rows = []
    if not isinstance(form, QFormLayout):
        return rows
    for index in range(form.rowCount()):
        label = form.itemAt(index, QFormLayout.LabelRole)
        field = form.itemAt(index, QFormLayout.FieldRole)
        left = label.widget().text() if label and label.widget() else None
        widget = field.widget() if field else None
        right = (
            widget.text() if widget is not None and hasattr(widget, "text") else None
        )
        rows.append([left, right])
    return rows


def read_old_tab(host, page):
    """The whole shipped tab as one snapshot of plain values."""
    from PySide6.QtWidgets import (
        QComboBox,
        QGroupBox,
        QLabel,
        QLineEdit,
        QPushButton,
        QTableWidget,
    )

    groups = page.findChildren(QGroupBox)
    health = [one for one in groups if one.title() == surface.HEALTH_GROUP_TITLE]
    detail = [one for one in groups if one.title() != surface.HEALTH_GROUP_TITLE]
    rows = read_form(health[0]) if health else []
    rows = [
        [label, reset_stamp(value) if label == surface.COUNTERS_RESET_ROW else value]
        for label, value in rows
    ]
    tables = page.findChildren(QTableWidget)
    table = tables[0] if tables else None
    cells = []
    heads = []
    if table is not None:
        heads = [
            table.horizontalHeaderItem(column).text()
            for column in range(table.columnCount())
        ]
        for row in range(table.rowCount()):
            line = []
            for column in range(table.columnCount()):
                item = table.item(row, column)
                line.append("" if item is None else item.text())
            cells.append(line)
    buttons = [
        [one.text(), bool(one.isEnabled())]
        for one in page.findChildren(QPushButton)
        if one.text()
        in (
            surface.CLEAR_FOLD_IDLE_TEXT,
            surface.CLEAR_WIRE_IDLE_TEXT,
            surface.CLEAR_COUNTERS_IDLE_TEXT,
        )
        or one.text().startswith(("Clear ", "Clear$"))
    ]
    combo = page.findChildren(QComboBox)
    edit = page.findChildren(QLineEdit)
    empty = [
        one.text()
        for one in page.findChildren(QLabel)
        if one.text() == surface.EMPTY_TEXT
    ]
    return {
        "health_rows": rows,
        "table_shown": table is not None,
        "table_headers": heads,
        "table_rows": cells,
        "table_title": detail[0].title() if detail else surface.BLANK_LINE,
        "buttons": buttons,
        "orders": (
            [combo[0].itemText(i) for i in range(combo[0].count())] if combo else []
        ),
        "order": combo[0].currentText() if combo else None,
        "row_filter": edit[0].text() if edit else None,
        "placeholder": edit[0].placeholderText() if edit else None,
        "empty_shown": bool(empty),
        "panel_shows": host._fold_panel_shows(),
    }


def read_new_tab(model):
    """The whole surface as the same snapshot of plain values."""
    payload = surface.build_view_model(model)
    rows = [
        [
            label,
            reset_stamp(value) if label == surface.COUNTERS_RESET_ROW else value,
        ]
        for label, value in payload["health_rows"]
    ]
    return {
        "health_rows": rows,
        "table_shown": payload["table"]["shown"],
        "table_headers": (
            list(payload["table"]["columns"]) if payload["table"]["shown"] else []
        ),
        "table_rows": payload["table"]["rows"],
        "table_title": payload["table"]["title"],
        "buttons": payload["buttons"],
        "orders": (
            list(payload["row_controls"]["orders"]) if payload["table"]["shown"] else []
        ),
        "order": (
            payload["row_controls"]["order"] if payload["table"]["shown"] else None
        ),
        "row_filter": (
            payload["row_controls"]["filter"] if payload["table"]["shown"] else None
        ),
        "placeholder": (
            payload["row_controls"]["filter_placeholder"]
            if payload["table"]["shown"]
            else None
        ),
        "empty_shown": payload["empty_label"]["shown"],
        "panel_shows": dict(
            payload["panel_shows"],
            counters_reset_text=reset_stamp(
                payload["panel_shows"]["counters_reset_text"]
            ),
        ),
    }


def digest(body):
    """One hash over every value a snapshot carries, at every depth."""
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=repr).encode("utf-8")
    ).hexdigest()


# The cases, each driven through both sides


def tranche(**over):
    """One fold tranche with the four money keys the panel reads."""
    one = {
        "usd": 12.5,
        "units": 0.5,
        "ref": 100.0,
        "initial_buy_price": 90.0,
        "created_ts": NOW - 3600.0,
    }
    one.update(over)
    return one


def extractor(**over):
    """One Extractor Tranche row the child hands the parent's table."""
    one = {
        "tranche_id": "kid|ALT/BTC|1700000000.0",
        "child_bot_id": "kid",
        "opened_at": NOW - 7200.0,
        "base_deployed": 2.5,
        "mark_value_usd": 30.0,
        "state": "open",
        "pair": "ALT/BTC",
        "arbiter": "parent",
    }
    one.update(over)
    return one


CASES = {
    "empty": {"symbol": "BTC/USD"},
    "one_tranche": {
        "symbol": "BTC/USD",
        "tranches": [tranche()],
        "created": 10,
        "closed": 6,
        "discarded": 1,
        "malformed": 0,
        "holdings": 1.0,
        "price": 95.0,
        "parked": 5.0,
        "cap_budget": 100.0,
        "cap_spent": 25.0,
    },
    "many_tranches": {
        "symbol": "ETH/USD",
        "tranches": [
            tranche(usd=1.0, units=0.1, ref=10.0, created_ts=NOW - 100.0),
            tranche(usd=2.0, units=0.2, ref=20.0, created_ts=NOW - 200.0),
            tranche(usd=3.0, units=0.3, ref=30.0, created_ts=NOW - 900000.0),
        ],
        "created": 100,
        "closed": 90,
        "discarded": 5,
        "malformed": 2,
        "holdings": 0.3,
        "price": 9.0,
        "parked": 343.6824,
        "wire_discarded": 213.9,
        "counters_reset_ts": NOW - 86400.0,
        "cap_budget": 50.0,
        "cap_spent": 12.5,
    },
    "over_allotment": {
        "symbol": "PUMP/USD",
        "tranches": [tranche(units=1.99)],
        "holdings": 1.0,
        "price": 101.0,
        "created": 20,
        "closed": 2,
        "discarded": 0,
    },
    "zero": {
        "symbol": "ZERO/USD",
        "tranches": [tranche(usd=0.0, units=0.0, ref=0.0, initial_buy_price=0.0)],
        "holdings": 0.0,
        "price": 0.0,
    },
    "negative": {
        "symbol": "NEG/USD",
        "tranches": [tranche(usd=-5.0, units=-1.0, ref=-2.0)],
        "holdings": -1.0,
        "price": -3.0,
        "created": -5,
        "closed": -2,
        "discarded": -1,
        "malformed": -1,
        "cap_budget": -1.0,
        "cap_spent": -2.0,
    },
    "thousand_million": {
        "symbol": "BIG/USD",
        "tranches": [tranche(usd=THOUSAND_MILLION, units=THOUSAND_MILLION)],
        "holdings": THOUSAND_MILLION,
        "price": THOUSAND_MILLION,
        "created": 1_000_000_000,
        "closed": 999_999_999,
        "cap_budget": THOUSAND_MILLION,
    },
    "one_billionth": {
        "symbol": "TINY/USD",
        "tranches": [tranche(usd=BILLIONTH, units=BILLIONTH, ref=BILLIONTH)],
        "holdings": BILLIONTH,
        "price": BILLIONTH,
        "parked": BILLIONTH,
        "wire_discarded": BILLIONTH,
    },
    "unicode": {
        "symbol": "БТЦ/€ 日本",
        "tranches": [tranche()],
        "holdings": 1.0,
        "price": 95.0,
    },
    "long_symbol": {"symbol": "A" * 200, "tranches": [tranche()], "holdings": 1.0},
    "markup": {
        "symbol": "<b>BTC</b> & <script>x</script>",
        "tranches": [tranche()],
        "holdings": 1.0,
    },
    "apostrophe": {"symbol": "IT'S/USD", "tranches": [tranche()], "holdings": 1.0},
    "wrong_capitals": {
        "symbol": "btc/usd",
        "tranches": [tranche()],
        "holdings": 1.0,
    },
    "newline_symbol": {
        "symbol": "BTC\nUSD",
        "tranches": [tranche()],
        "holdings": 1.0,
    },
    "number_where_text_belongs": {
        "symbol": 42,
        "tranches": [tranche()],
        "holdings": 1.0,
    },
    "text_where_number_belongs": {
        "symbol": "TXT/USD",
        "tranches": [tranche(usd="20.0", units="1.5", ref="9")],
        "holdings": "3",
        "wire_discarded": "8",
        "counters_reset_ts": "7",
        "cap_budget": "6",
        "cap_spent": "5",
    },
    "not_a_number": {
        "symbol": "NAN/USD",
        "tranches": [tranche(usd=NAN, units=NAN, ref=NAN, created_ts=NAN)],
        "holdings": NAN,
        "wire_discarded": NAN,
        "counters_reset_ts": NAN,
        "cap_budget": NAN,
        "cap_spent": NAN,
    },
    "infinity": {
        "symbol": "INF/USD",
        "tranches": [tranche(usd=INFINITY, units=INFINITY, ref=INFINITY)],
        "holdings": INFINITY,
        "wire_discarded": INFINITY,
        "cap_budget": INFINITY,
    },
    "minus_infinity": {
        "symbol": "NINF/USD",
        "tranches": [tranche(usd=-INFINITY, units=-INFINITY, ref=-INFINITY)],
        "holdings": -INFINITY,
        "cap_spent": -INFINITY,
    },
    "huge_int": {
        "symbol": "HUGE/USD",
        "tranches": [tranche(usd=HUGE_INT, units=HUGE_INT, ref=HUGE_INT)],
        "holdings": HUGE_INT,
        "wire_discarded": HUGE_INT,
        "cap_budget": HUGE_INT,
    },
    "float_limit_below": {
        "symbol": "LIMIT/USD",
        "tranches": [tranche(usd=2**1023, units=2**1023)],
        "holdings": 2**1023,
    },
    "float_limit_above": {
        "symbol": "OVER/USD",
        "tranches": [tranche(usd=2**1024, units=2**1024)],
        "holdings": 2**1024,
    },
    "stored_true_money": {
        "symbol": "TRUE/USD",
        "tranches": [
            tranche(
                usd=True, units=True, ref=True, initial_buy_price=True, created_ts=True
            )
        ],
        "holdings": True,
        "wire_discarded": True,
        "counters_reset_ts": True,
        "cap_budget": True,
        "cap_spent": True,
    },
    "stored_true_counters": {
        "symbol": "TRUEC/USD",
        "created": True,
        "closed": True,
        "discarded": True,
        "malformed": True,
    },
    "stored_false_counters": {
        "symbol": "FALSEC/USD",
        "created": False,
        "closed": False,
        "discarded": False,
        "malformed": False,
        "tranches": [tranche()],
        "holdings": 1.0,
    },
    "missing_keys": {
        "symbol": "GAP/USD",
        "tranches": [{}],
        "holdings": 1.0,
        "price": 5.0,
    },
    "manual_scrum": {
        "symbol": "MAN/USD",
        "tranches": [tranche(operator_initiated=True)],
        "holdings": 1.0,
        "price": 95.0,
    },
    "auto_rebalance": {
        "symbol": "AUTO/USD",
        "tranches": [tranche(operator_initiated=False)],
        "holdings": 1.0,
        "price": 95.0,
    },
    "extractor_only": {
        "symbol": "EXT/USD",
        "extractor_rows": [extractor()],
        "holdings": 1.0,
    },
    "extractor_and_fold": {
        "symbol": "BOTH/USD",
        "tranches": [tranche(), tranche(usd=2.0)],
        "extractor_rows": [extractor(), extractor(arbiter="sibling", state="drawdown")],
        "holdings": 5.0,
        "price": 95.0,
        "created": 8,
        "closed": 4,
        "discarded": 1,
    },
    "extractor_true_units": {
        "symbol": "EXTT/USD",
        "extractor_rows": [extractor(base_deployed=True, mark_value_usd=True)],
    },
    "extractor_nan_units": {
        "symbol": "EXTN/USD",
        "extractor_rows": [extractor(base_deployed=NAN, mark_value_usd=NAN)],
    },
    "extractor_no_arbiter": {
        "symbol": "EXTA/USD",
        "extractor_rows": [extractor(arbiter="nobody")],
    },
    "despawn_armed": {
        "symbol": "OLD/USD",
        "despawn_days": 7,
        "tranches": [
            tranche(created_ts=NOW - 8 * 86400.0),
            tranche(created_ts=NOW - 100.0),
            tranche(created_ts=None),
        ],
        "holdings": 2.0,
    },
    "despawn_off_with_old_rows": {
        "symbol": "OFF/USD",
        "despawn_days": 0,
        "tranches": [tranche(created_ts=NOW - 90 * 86400.0)],
        "holdings": 1.0,
    },
    "despawn_with_stack": {
        "symbol": "STK/USD",
        "despawn_days": 14,
        "tranches": [tranche(created_ts=NOW - 20 * 86400.0)],
        "stack": [
            {"opened_ts": NOW - 30 * 86400.0, "status": "pending", "order_id": "x1"},
            {"opened_ts": NOW - 30 * 86400.0, "status": "filled", "order_id": None},
            {"opened_ts": None},
        ],
        "holdings": 1.0,
    },
    "no_otd": {
        "symbol": "NOOTD/USD",
        "interval": 0.0,
        "fee": 0.0,
        "tranches": [tranche()],
        "holdings": 1.0,
        "price": 95.0,
    },
    "price_above_ref": {
        "symbol": "HIGH/USD",
        "tranches": [tranche()],
        "holdings": 1.0,
        "price": 200.0,
    },
}

CASE_NAMES = tuple(sorted(CASES))


def old_tab(name):
    """The shipped tab built for one case, with the clock held still."""
    app()
    spec = CASES[name]
    host = Host(HostBot(spec))
    with PinnedClock(NOW) as clock:
        page = hold(host._create_fold_tranches_tab())
    assert clock.seen > 0, (
        f"the shipped builder read no clock on case {name!r}, so the pin "
        "measured nothing"
    )
    assert time.time is not clock, "the clock swap outlived the drive"
    return [host, page]


def new_model(name):
    """The surface's model built for one case."""
    spec = CASES[name]
    pct, factor = otd_for(spec)
    model = surface.FoldTranchesTabModel(
        surface.build_bot(spec), now=NOW, otd_pct=pct, otd_factor=factor
    )
    model.build()
    return model


def old_snapshot(name):
    """One case read off the shipped widget tree."""
    host, page = old_tab(name)
    return read_old_tab(host, page)


def new_snapshot(name):
    """One case read off the surface."""
    return read_new_tab(new_model(name))


# Value for value, and by hash


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_tab_and_the_surface_show_one_panel(name):
    """A value the operator reads moved on one side only."""
    old = old_snapshot(name)
    new = new_snapshot(name)
    for key in sorted(old):
        assert new[key] == old[key], (
            f"case {name!r}: {key} differs\n  shipped tab: {old[key]!r}\n"
            f"  surface:     {new[key]!r}"
        )
    assert digest(new) == digest(old), (
        f"case {name!r}: the two sides hash apart\n  shipped tab: "
        f"{digest(old)}\n  surface:     {digest(new)}"
    )


def test_the_sample_hashes_are_reported():
    """The hash of a case is not the hash of every other case."""
    hashes = {name: digest(old_snapshot(name)) for name in CASE_NAMES[:6]}
    assert len(set(hashes.values())) == len(hashes), hashes
    assert all(len(one) == 64 for one in hashes.values()), hashes


def test_two_genuinely_different_cases_hash_apart_old_then_new():
    """The comparison passes whatever the second side carries."""
    assert digest(old_snapshot("empty")) != digest(new_snapshot("many_tranches"))


def test_two_genuinely_different_cases_hash_apart_new_then_old():
    """The comparison reports only in one direction."""
    assert digest(new_snapshot("empty")) != digest(old_snapshot("many_tranches"))


def test_the_same_case_twice_hashes_alike_on_each_side():
    """A side does not agree with itself, so no comparison of it means anything."""
    first_old = digest(old_snapshot("one_tranche"))
    second_old = digest(old_snapshot("one_tranche"))
    assert first_old == second_old, (first_old, second_old)
    first_new = digest(new_snapshot("one_tranche"))
    second_new = digest(new_snapshot("one_tranche"))
    assert first_new == second_new, (first_new, second_new)
    assert first_old == first_new, (first_old, first_new)


# The number columns and the counters, guarded against bare

REFUSED_SHAPES = {
    "stored_true": True,
    "stored_false": False,
    "not_a_number": NAN,
    "infinity": INFINITY,
    "minus_infinity": -INFINITY,
    "text": "abc",
    "numeric_text": "20",
    "huge_int": HUGE_INT,
    "absent": None,
}
GUARDED_MONEY_KEYS = ("usd", "ref", "initial_buy_price", "units", "created_ts")


@pytest.mark.parametrize("shape", sorted(REFUSED_SHAPES))
@pytest.mark.parametrize("key", GUARDED_MONEY_KEYS)
def test_a_refused_fold_cell_prints_no_number_on_either_side(key, shape):
    """A stored value the panel cannot read reached a money cell."""
    spec = {
        "symbol": "AUD/USD",
        "tranches": [tranche(**{key: REFUSED_SHAPES[shape]})],
        "holdings": 1.0,
        "price": 95.0,
    }
    CASES["_audit"] = spec
    try:
        old = old_snapshot("_audit")
        new = new_snapshot("_audit")
    finally:
        CASES.pop("_audit")
    assert new["table_rows"] == old["table_rows"], (shape, key)
    if REFUSED_SHAPES[shape] is None or shape in (
        "stored_true",
        "not_a_number",
        "infinity",
        "minus_infinity",
        "text",
        "huge_int",
    ):
        column = {
            "usd": 3,
            "ref": 4,
            "initial_buy_price": 5,
            "units": 2,
            "created_ts": 1,
        }
        assert old["table_rows"][0][column[key]] == surface.NO_VALUE_TEXT, (
            f"{key} carrying {shape} printed "
            f"{old['table_rows'][0][column[key]]!r} rather than an em dash"
        )


@pytest.mark.parametrize("shape", sorted(REFUSED_SHAPES))
def test_a_lifetime_counter_reads_the_same_bare_value_on_both_sides(shape):
    """A counter reading moved on one side only.

    The shipped tab reads all four counters bare. Where the bare read
    raises, both sides must raise the same type; where it prints, both
    sides must print the same text.
    """
    value = REFUSED_SHAPES[shape]
    spec = {"symbol": "CNT/USD", "created": value, "closed": value}
    CASES["_counters"] = spec
    try:
        old_raised = None
        new_raised = None
        try:
            old = old_snapshot("_counters")
        except Exception as exc:
            old_raised = type(exc)
            old = None
        try:
            new = new_snapshot("_counters")
        except Exception as exc:
            new_raised = type(exc)
            new = None
    finally:
        CASES.pop("_counters")
    assert old_raised is new_raised, (shape, old_raised, new_raised)
    if old_raised is None:
        assert new["health_rows"] == old["health_rows"], shape


def test_the_shipped_counter_read_is_bare_and_the_guarded_one_is_offered():
    """The bare counter reading and the guarded one stopped disagreeing."""
    assert surface.whole_count(True) == 1
    assert surface.guarded_count(True) is None
    assert surface.whole_count("20") == 20
    assert surface.guarded_count("20") is None
    assert surface.whole_count(12.7) == 12
    assert surface.guarded_count(12.7) == 12
    with pytest.raises(ValueError):
        surface.whole_count(NAN)
    assert surface.guarded_count(NAN) is None
    with pytest.raises(OverflowError):
        surface.whole_count(INFINITY)
    assert surface.guarded_count(INFINITY) is None


def test_the_extractor_units_cell_is_bare_where_its_money_cell_refuses():
    """The Units cell stopped fabricating a quantity the USD cell refuses."""
    row = extractor(base_deployed=True, mark_value_usd=True)
    cells = surface.extractor_row_cells(row, NOW)
    assert cells[2] == surface.UNITS_FORMAT.format(units=1.0), cells
    assert cells[3] == surface.NO_VALUE_TEXT, cells
    assert surface.guarded_extractor_units(row) == surface.NO_VALUE_TEXT
    plain = extractor()
    assert surface.guarded_extractor_units(plain) == cells_units(plain)


def cells_units(row):
    """The Units cell one Extractor row shows, for the pair above."""
    return surface.extractor_row_cells(row, NOW)[2]


# The step sequences, including ones that refuse part way

CLEAR_STEPS = {
    "fold_declined": ["fold", surface.NO_BUTTON_VALUE, surface.OUTCOME_DECLINED],
    "fold_cleared": ["fold", surface.YES_BUTTON_VALUE, surface.OUTCOME_CLEARED],
    "wire_declined": ["wire", surface.NO_BUTTON_VALUE, surface.OUTCOME_DECLINED],
    "wire_cleared": ["wire", surface.YES_BUTTON_VALUE, surface.OUTCOME_CLEARED],
    "counters_declined": [
        "counters",
        surface.CANCEL_BUTTON_VALUE,
        surface.OUTCOME_DECLINED,
    ],
    "counters_cleared": [
        "counters",
        surface.YES_BUTTON_VALUE,
        surface.OUTCOME_CLEARED,
    ],
}


def clearing_model():
    """A model whose three clears all have work to do."""
    spec = {
        "symbol": "CLR/USD",
        "tranches": [tranche(), tranche(usd=1.0)],
        "parked": 343.6824,
        "wire_ledger": [1, 2, 3],
        "created": 4925,
        "closed": 4813,
        "discarded": 91,
        "malformed": 1,
        "holdings": 2.0,
        "clear_fold_report": {"count": 2, "usd": 13.5},
        "clear_wire_report": {"usd": 343.6824},
        "clear_counters_report": {
            "cleared": 9830,
            "before": {
                "created": 4925,
                "closed": 4813,
                "discarded": 91,
                "malformed": 1,
            },
        },
    }
    model = surface.FoldTranchesTabModel(surface.build_bot(spec), now=NOW)
    model.build()
    return model


@pytest.mark.parametrize("name", sorted(CLEAR_STEPS))
def test_every_clear_reaches_the_outcome_it_names(name):
    """A clear took a path other than the one it reports."""
    which, answer, wanted = CLEAR_STEPS[name]
    model = clearing_model()
    before = len(model.calls)
    got = getattr(model, "clear_" + which)(answer)
    assert got == wanted, (name, got)
    steps = [one[0] for one in model.calls[before:]]
    assert steps[0] == surface.CLEAR_START, steps
    assert surface.CLEAR_CONFIRM in steps, steps
    if wanted == surface.OUTCOME_DECLINED:
        assert steps[-1] == surface.CLEAR_DECLINED, steps
        assert surface.CLEAR_CALLED not in steps, steps
    else:
        assert steps[-1] == surface.CLEAR_REPORTED, steps
        assert surface.SETTLE_SAVE in steps, steps


def test_a_clear_that_refuses_part_way_keeps_what_it_recorded():
    """A refusal threw away the steps taken before it."""
    model = clearing_model()
    model.bot.clear_fold_raises = ValueError("the venue said no")
    before = len(model.calls)
    got = model.clear_fold(surface.YES_BUTTON_VALUE)
    assert got == surface.OUTCOME_CALL_FAILED
    steps = [one[0] for one in model.calls[before:]]
    assert steps == [
        surface.CLEAR_START,
        surface.CLEAR_CONFIRM,
        surface.CLEAR_FAILED,
    ], steps
    assert model.calls[before + 2][2] == "ValueError", model.calls[before + 2]
    assert len(model.boxes) == 2, model.boxes
    assert model.boxes[-1]["icon"] == surface.CRITICAL_ICON


def test_a_clear_with_no_work_stops_before_the_confirmation():
    """A clear offered a confirmation for something it could not do."""
    model = surface.FoldTranchesTabModel(surface.build_bot({"symbol": "X"}), now=NOW)
    model.build()
    assert model.clear_fold(surface.YES_BUTTON_VALUE) == surface.OUTCOME_NO_TRANCHES
    assert model.clear_wire(surface.YES_BUTTON_VALUE) == surface.OUTCOME_NO_TRANCHES
    assert (
        model.clear_counters(surface.YES_BUTTON_VALUE) == surface.OUTCOME_ALREADY_ZERO
    )
    steps = [one[0] for one in model.calls]
    assert surface.CLEAR_CONFIRM not in steps, steps
    assert steps.count(surface.CLEAR_NO_WORK) == 3, steps


def test_a_bot_that_cannot_clear_is_refused_by_name():
    """A clear was offered on a bot type that has no such method."""
    for which, flag in (
        ("fold", "can_clear_fold"),
        ("wire", "can_clear_wire"),
        ("counters", "can_clear_counters"),
    ):
        bot = surface.BotSource(
            symbol="NO/USD",
            tranches=[tranche()],
            parked=10.0,
            created=5,
            **{flag: False},
        )
        model = surface.FoldTranchesTabModel(bot, now=NOW)
        model.build()
        got = getattr(model, "clear_" + which)(surface.YES_BUTTON_VALUE)
        assert got == surface.OUTCOME_NOT_SUPPORTED, which


ARBITER_STEPS = {
    "no_registry": [None, surface.OUTCOME_NO_REGISTRY],
    "no_child": [{}, surface.OUTCOME_NO_CHILD],
    "raised": [{"kid": "raises"}, surface.OUTCOME_RAISED],
    "no_position": [{"kid": "none"}, surface.OUTCOME_NO_POSITION],
    "toggled": [{"kid": "sibling"}, surface.OUTCOME_TOGGLED],
}


@pytest.mark.parametrize("name", sorted(ARBITER_STEPS))
def test_every_arbiter_path_reaches_the_outcome_it_names(name):
    """An Arbiter click took a path other than the one it reports."""
    children, wanted = ARBITER_STEPS[name]
    manager = None
    if children is not None:
        made = {}
        for key, kind in children.items():
            if kind == "raises":
                made[key] = surface.ChildSource(
                    raises=RuntimeError("the child refused")
                )
            elif kind == "none":
                made[key] = surface.ChildSource(flips_to=None)
            else:
                made[key] = surface.ChildSource(flips_to=surface.ARBITER_SIBLING)
        manager = surface.ManagerSource(made)
    bot = surface.BotSource(symbol="ARB/USD", manager=manager)
    model = surface.FoldTranchesTabModel(bot, now=NOW)
    got = model.arbiter_toggle("kid|ALT/BTC|1", "kid")
    assert got == wanted, (name, got)
    assert model.calls[0][0] == surface.ARBITER_START
    if wanted == surface.OUTCOME_TOGGLED:
        assert model.arbiter_labels == [
            ["kid|ALT/BTC|1", "Sibling", surface.arbiter_tooltip("sibling")]
        ]
        assert model.boxes == []
    else:
        assert len(model.boxes) == 1, model.boxes
        assert model.boxes[0]["title"] == surface.ARBITER_REFUSED_TITLE


FIRE_STEPS = {
    "gone": ["gone", surface.YES_BUTTON_VALUE, surface.OUTCOME_GONE],
    "unreadable": ["bad", surface.YES_BUTTON_VALUE, surface.OUTCOME_UNREADABLE],
    "declined": ["good", surface.NO_BUTTON_VALUE, surface.OUTCOME_DECLINED],
    "no_loop": ["no_loop", surface.YES_BUTTON_VALUE, surface.OUTCOME_NO_LOOP],
    "schedule_failed": [
        "schedule_failed",
        surface.YES_BUTTON_VALUE,
        surface.OUTCOME_SCHEDULE_FAILED,
    ],
    "dispatched": ["good", surface.YES_BUTTON_VALUE, surface.OUTCOME_DISPATCHED],
}


def firing_model(kind):
    """A model whose Fire button reaches one named path."""
    rows = [tranche(), tranche(usd=2.0)]
    if kind == "bad":
        rows = [tranche(usd=NAN), tranche()]
    bot = surface.BotSource(symbol="FIRE/USD", tranches=rows, holdings=5.0)
    manager = surface.ManagerSource(loop=None if kind == "no_loop" else "a-loop")
    schedule = surface.ScheduleSink(
        raises=OSError("the loop is closed") if kind == "schedule_failed" else None
    )
    model = surface.FoldTranchesTabModel(bot, manager, schedule, now=NOW)
    model.build()
    return model


@pytest.mark.parametrize("name", sorted(FIRE_STEPS))
def test_every_fire_path_reaches_the_outcome_it_names(name):
    """A Fire click took a path other than the one it reports."""
    kind, answer, wanted = FIRE_STEPS[name]
    model = firing_model(kind)
    chosen = {"not": "in the queue"} if kind == "gone" else model.tranches()[0]
    got = model.fire(chosen, 1, answer)
    assert got == wanted, (name, got)
    steps = [one[0] for one in model.calls if one[0].startswith("fire.")]
    assert steps[0] == surface.FIRE_START, steps
    if wanted == surface.OUTCOME_DISPATCHED:
        assert steps[-1] == surface.FIRE_POLL_START, steps
        assert model.bot.fired == [0], model.bot.fired
    if wanted in (surface.OUTCOME_GONE, surface.OUTCOME_UNREADABLE):
        assert model.bot.fired == [], model.bot.fired
        assert surface.FIRE_CONFIRM not in steps, steps


def test_a_fire_refused_for_an_unreadable_value_names_the_field_and_places_no_order():
    """A market buy was offered for a value the dialog cannot show."""
    model = firing_model("bad")
    got = model.fire(model.tranches()[0], 7, surface.YES_BUTTON_VALUE)
    assert got == surface.OUTCOME_UNREADABLE
    text = model.boxes[-1]["text"]
    assert "USD parked" in text, text
    assert "'usd'" in text, text
    assert "float" in text, text
    assert model.bot.fired == []
    assert model.boxes[-1]["buttons_value"] == surface.OK_BUTTON_VALUE


def test_a_fire_on_a_queue_that_moved_names_both_numbers():
    """The confirmation named one number where the queue had shifted."""
    model = firing_model("good")
    moved = model.fire(model.tranches()[1], 9, surface.NO_BUTTON_VALUE)
    assert moved == surface.OUTCOME_DECLINED
    text = model.boxes[-1]["text"]
    assert "Fire tranche #9?" in text, text
    assert "now sits at #2" in text, text


def test_a_fire_with_no_clicked_number_uses_the_resolved_index():
    """A caller with no row number was shown a blank."""
    model = firing_model("good")
    model.fire(model.tranches()[1], None, surface.NO_BUTTON_VALUE)
    text = model.boxes[-1]["text"]
    assert "Fire tranche #2?" in text, text
    assert "THE QUEUE HAS MOVED" not in text, text


POLL_STEPS = {
    "pending": [{"done": False, "elapsed_s": 1.0}, surface.OUTCOME_PENDING],
    "gave_up": [{"done": False, "elapsed_s": 121.0}, surface.OUTCOME_GAVE_UP],
    "filled": [
        {
            "done": True,
            "result": {
                "applied": True,
                "fill_price": 94.5,
                "units_returned": 0.13,
                "remaining_tranches": 1,
            },
        },
        surface.OUTCOME_FILLED,
    ],
    "not_applied": [
        {"done": True, "result": {"applied": False, "reason": "smart ceiling"}},
        surface.OUTCOME_NOT_APPLIED,
    ],
    "no_dict": [{"done": True, "result": None}, surface.OUTCOME_NOT_APPLIED],
}


@pytest.mark.parametrize("name", sorted(POLL_STEPS))
def test_every_poll_turn_reaches_the_outcome_it_names(name):
    """The poll reported an outcome other than the one it took."""
    spec, wanted = POLL_STEPS[name]
    model = firing_model("good")
    got = model.poll(1, **spec)
    assert got == wanted, (name, got)


def test_a_poll_that_raises_reports_the_type_and_leaves_the_queue_alone():
    """A coroutine that raised was reported as a fill."""
    model = firing_model("good")
    got = model.poll(1, done=True, raises=TimeoutError("the venue timed out"))
    assert got == surface.OUTCOME_RAISED
    assert "TimeoutError" in model.boxes[-1]["text"]
    assert len(model.tranches()) == 2


def test_a_refusal_is_told_apart_by_type_and_never_by_wording():
    """Two refusals of different kinds were folded into one answer."""
    kinds = set()
    for raiser in (
        ValueError("a"),
        OverflowError("b"),
        TypeError("c"),
        RuntimeError("d"),
    ):
        model = clearing_model()
        model.bot.clear_fold_raises = raiser
        model.clear_fold(surface.YES_BUTTON_VALUE)
        kinds.add(model.calls[-1][2])
    assert kinds == {"ValueError", "OverflowError", "TypeError", "RuntimeError"}


# The enumeration, counted off the parsed file

TIMER_BUILDERS = {"QTimer"}
THREAD_BUILDERS = {"QThread", "Thread"}
EMIT_NAMES = {"emit"}
SUBSCRIBE_NAMES = {"subscribe"}


def imported_as(tree, wanted):
    """Every local name one of `wanted` was imported under."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for one in node.names:
                if one.name in wanted:
                    found[one.asname or one.name] = one.name
        elif isinstance(node, ast.Import):
            for one in node.names:
                if one.name.split(".")[-1] in wanted:
                    found[one.asname or one.name] = one.name
    return found


def called(node):
    """The name one call uses, whether plain or reached through a dot."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def enumerate_file(path):
    """What one file BUILDS, read off the parsed tree, aliases followed."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    timers = TIMER_BUILDERS | set(imported_as(tree, TIMER_BUILDERS))
    threads = THREAD_BUILDERS | set(imported_as(tree, THREAD_BUILDERS))
    emitters = EMIT_NAMES | set(imported_as(tree, EMIT_NAMES))
    subscribers = SUBSCRIBE_NAMES | set(imported_as(tree, SUBSCRIBE_NAMES))
    top_classes = {one for one in tree.body if isinstance(one, ast.ClassDef)}
    found = {
        "classes_top": [],
        "classes_all": [],
        "methods": [],
        "signals": [],
        "connects": [],
        "emits": [],
        "subscribes": [],
        "timers_built": [],
        "timers_started": [],
        "threads_built": [],
        "threads_started": [],
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            found["classes_all"].append(node.name)
            if node in top_classes:
                found["classes_top"].append(node.name)
            for inner in node.body:
                if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found["methods"].append(f"{node.name}.{inner.name}")
                if isinstance(inner, (ast.Assign, ast.AnnAssign)):
                    if "Signal(" in ast.unparse(inner):
                        targets = (
                            inner.targets
                            if isinstance(inner, ast.Assign)
                            else [inner.target]
                        )
                        for one in targets:
                            if isinstance(one, ast.Name):
                                found["signals"].append(f"{node.name}.{one.id}")
        if isinstance(node, ast.Call):
            name = called(node)
            if name == "connect":
                found["connects"].append(ast.unparse(node.func.value))
            elif name in emitters:
                found["emits"].append(name)
            elif name in subscribers:
                found["subscribes"].append(name)
            elif name in timers:
                found["timers_built"].append(name)
            elif name in threads:
                found["threads_built"].append(name)
            elif name in ("start", "singleShot", "startTimer") and isinstance(
                node.func, ast.Attribute
            ):
                owner = ast.unparse(node.func.value).lower()
                if name == "singleShot" or "timer" in owner:
                    found["timers_started"].append(name)
                elif "thread" in owner:
                    found["threads_started"].append(name)
    return found


OLD = enumerate_file(TAB_PATH)
NEW = enumerate_file(SURFACE_PATH)


def test_the_counter_sees_a_class_hidden_inside_a_method():
    """A full walk and a top-level read gave one answer."""
    control = enumerate_file(NESTED_CLASS_CONTROL)
    assert len(control["classes_all"]) == 4, control["classes_all"]
    assert control["classes_top"] == [], control["classes_top"]


def test_the_counter_sees_methods_on_a_nested_class():
    """Methods declared inside a nested class went uncounted."""
    control = enumerate_file(NESTED_METHOD_CONTROL)
    assert len(control["classes_all"]) == 4, control["classes_all"]
    assert len(control["methods"]) > 40, len(control["methods"])


def test_a_signal_is_counted_as_a_signal_and_not_as_a_method():
    """A declared signal was counted among the methods."""
    control = enumerate_file(SIGNAL_CONTROL)
    assert "ModeCard.clicked" in control["signals"], control["signals"]
    assert "ModeCard.clicked" not in control["methods"], control["methods"]


def test_the_timer_counter_tells_two_files_of_one_name_apart():
    """Two files sharing a basename were counted as one."""
    assert len(enumerate_file(TIMER_CONTROL)["timers_built"]) == 1
    assert enumerate_file(NO_TIMER_CONTROL)["timers_built"] == []


def test_the_bus_counter_reads_both_directions_and_follows_an_alias():
    """An emit imported under another name went uncounted."""
    control = enumerate_file(BUS_CONTROL)
    assert len(control["subscribes"]) == 2, control["subscribes"]
    assert len(control["emits"]) == 7, control["emits"]
    assert control["emits"].count("_sw_emit") == 2, control["emits"]


def test_the_tab_declares_one_class_and_twelve_methods():
    """A method appeared on one side and not the other."""
    assert OLD["classes_top"] == ["FoldTranchesTabMixin"], OLD["classes_top"]
    assert len(OLD["methods"]) == 12, OLD["methods"]
    assert OLD["signals"] == [], OLD["signals"]


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    assert len(OLD["connects"]) == 6, OLD["connects"]
    assert NEW["connects"] == [], NEW["connects"]
    assert len(surface.ACTIONS) == len(OLD["connects"])
    assert set(surface.ACTIONS) == {
        "clear_button.clicked",
        "wire_button.clicked",
        "counters_button.clicked",
        "arbiter_button.clicked",
        "fire_button.clicked",
        "poll_timer.timeout",
    }
    for handler in surface.ACTIONS.values():
        assert callable(getattr(surface.FoldTranchesTabModel, handler)), handler


def test_the_tab_builds_one_timer_and_starts_it():
    """A wait appeared on one side and not the other."""
    assert len(OLD["timers_built"]) == 1, OLD["timers_built"]
    assert len(OLD["timers_started"]) == 1, OLD["timers_started"]
    assert NEW["timers_built"] == [], NEW["timers_built"]
    assert NEW["timers_started"] == [], NEW["timers_started"]
    assert len(surface.TIMERS) == len(OLD["timers_built"])
    assert list(surface.TIMER_DELAYS_MS) == [surface.FIRE_POLL_INTERVAL_MS]


def test_the_tab_starts_no_thread():
    """A worker thread appeared on one side and not the other."""
    assert OLD["threads_built"] == [], OLD["threads_built"]
    assert OLD["threads_started"] == [], OLD["threads_started"]
    assert NEW["threads_built"] == [], NEW["threads_built"]
    assert surface.THREADS == ()


def test_the_tab_emits_once_and_subscribes_to_nothing():
    """A bus wiring appeared on one side and not the other."""
    assert len(OLD["emits"]) == 1, OLD["emits"]
    assert OLD["emits"] == ["_fold_emit"], OLD["emits"]
    assert OLD["subscribes"] == [], OLD["subscribes"]
    assert len(surface.BUS_TOPICS) == len(OLD["emits"])
    assert surface.BUS_SUBSCRIPTIONS == ()
    assert NEW["emits"] == [], NEW["emits"]


def test_the_surface_emits_the_topic_the_tab_emits():
    """The pin the shipped tab sends went missing on the surface."""
    model = clearing_model()
    model.clear_fold(surface.YES_BUTTON_VALUE)
    assert [one[0] for one in model.emitted] == [surface.SETTLE_SIGNAL]
    sent, actual, expected = model.emitted[0]
    assert sent == "gui.04.002.postcondition.clear_settled"
    assert set(actual) == set(expected)
    assert actual["fold_rows"] == expected["fold_rows"] == 0


# Completeness


def freeze(value):
    """One value in a form two equal values share and a swap changes."""
    if isinstance(value, dict):
        return ("dict", tuple(sorted((repr(k), freeze(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return ("seq", tuple(freeze(one) for one in value))
    return ("one", repr(value))


def surface_constants():
    """Every exported value the surface names, read off the module."""
    return {
        name: getattr(surface, name)
        for name in dir(surface)
        if name.isupper() and not name.startswith("_")
    }


def compared_payloads():
    """Every payload the comparison above reads."""
    made = []
    for name in CASE_NAMES:
        made.append(surface.build_view_model(new_model(name)))
    model = clearing_model()
    model.clear_fold(surface.YES_BUTTON_VALUE)
    made.append(surface.build_view_model(model))
    for kind in ("good", "bad", "no_loop", "schedule_failed"):
        one = firing_model(kind)
        one.fire(one.tranches()[0], 1, surface.YES_BUTTON_VALUE)
        one.poll(1, done=True, result={"applied": True})
        made.append(surface.build_view_model(one))
    arb = surface.FoldTranchesTabModel(
        surface.BotSource(
            symbol="A",
            manager=surface.ManagerSource({"kid": surface.ChildSource()}),
        ),
        now=NOW,
    )
    arb.arbiter_toggle("t", "kid")
    made.append(surface.build_view_model(arb))
    return made


def payload_values(payloads):
    """Every value any payload carries, at every depth, frozen."""
    found = set()

    def walk(value):
        found.add(freeze(value))
        if isinstance(value, dict):
            for key, inner in value.items():
                found.add(freeze(key))
                walk(inner)
        elif isinstance(value, (list, tuple)):
            for inner in value:
                walk(inner)

    for one in payloads:
        walk(one)
    return found


COVERED_ELSEWHERE = {
    "REFRESH_NOT_LOCATED_FORMAT": "test_the_refresh_outcomes_are_the_shipped_tabs",
    "REFRESH_RAISED_FORMAT": "test_the_refresh_outcomes_are_the_shipped_tabs",
    "NOT_A_NUMBER": "test_the_admission_rule_agrees_with_the_shipped_one",
    "COLOUR_STYLE_FORMAT": "test_a_coloured_row_carries_the_style_the_tab_writes",
    "SORT_TOOLTIP": "test_the_row_controls_carry_the_shipped_tooltips",
    "PANE_MODEL": "test_two_models_do_not_share_a_state",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped tab."""
    constants = surface_constants()
    assert len(constants) > 150, len(constants)
    assert missing_from_payload(constants, payload_values(compared_payloads())) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thin = payload_values([{"method": surface.METHOD}])
    assert "EMPTY_TEXT" in missing_from_payload(surface_constants(), thin)


PAYLOAD_KEY_SOURCES = {
    "method": "METHOD",
    "accessible_name": "ACCESSIBLE_NAME",
    "tab_label": "TAB_LABEL",
    "container": None,
    "health_group": "HEALTH_GROUP_TITLE",
    "health_rows": None,
    "health_colors": None,
    "health_labels": "OPEN_COUNT_ROW",
    "health_tooltips": "OPEN_COUNT_TOOLTIP",
    "empty_label": "EMPTY_TEXT",
    "table": "COLUMNS",
    "row_controls": "SORT_ORDERS",
    "buttons": None,
    "button_tooltips": "CLEAR_FOLD_TOOLTIP",
    "button_style": "DANGER_BUTTON_STYLE",
    "fire_button": "FIRE_BUTTON_TOOLTIP",
    "arbiter_button": "ARBITER_LABELS",
    "panel_shows": None,
    "boxes": None,
    "outcome": None,
    "outcomes": "OUTCOMES",
    "settled": None,
    "emitted": None,
    "poll_elapsed_s": None,
    "colors": "FOLD_TRANCHE_BG_HEX",
    "border_by_background": "TRANCHE_ROW_BORDER_BY_BG",
    "border_px": "TRANCHE_ROW_BORDER_PX",
    "no_cell_color": "NO_CELL_COLOR",
    "no_value_text": "NO_VALUE_TEXT",
    "extractor_row_number": "EXTRACTOR_ROW_NUMBER",
    "sources": "SOURCE_TOOLTIPS",
    "arbiter_values": "ARBITER_PARENT",
    "despawn": "DESPAWN_PREVIEW_WINDOWS",
    "sort_keys": "SORT_KEYS",
    "titles": "CLEAR_FOLD_TITLE",
    "texts": "NO_FOLD_TRANCHES_TEXT",
    "formats": "USD_FORMAT",
    "keys": "USD_KEY",
    "attributes": "FOLD_TRANCHES_ATTRIBUTE",
    "numbers": "WIRE_CREDIT_FLOOR_USD",
    "button_values": "YES_BUTTON_VALUE",
    "icons": "QUESTION_ICON",
    "joins": "BODY_JOIN",
    "clear_reason": "CLEAR_REASON",
    "fire_read_fields": "FIRE_READ_FIELDS",
    "actions": "ACTIONS",
    "timers": "TIMERS",
    "timer_delays_ms": "TIMER_DELAYS_MS",
    "bus_topics": "BUS_TOPICS",
    "bus_subscriptions": "BUS_SUBSCRIPTIONS",
    "threads": "THREADS",
    "signals": "SIGNALS",
    "call_names": "CALL_NAMES",
    "calls": None,
}


def backed(payload, key, source):
    """Whether the named surface value really is inside that payload key."""
    if source is None:
        return key in payload
    return freeze(getattr(surface, source)) in payload_values([payload[key]])


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    payload = surface.build_view_model(new_model("many_tranches"))
    assert set(payload) == set(PAYLOAD_KEY_SOURCES)
    for key, source in PAYLOAD_KEY_SOURCES.items():
        if source is not None:
            assert hasattr(surface, source), source
        assert backed(payload, key, source), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    payload = surface.build_view_model(new_model("many_tranches"))
    assert backed(payload, "outcomes", "OUTCOMES")
    assert not backed(payload, "outcomes", "COLUMNS")
    assert not backed(payload, "icons", "SORT_ORDERS")
    assert not backed({"absent": 1}, "missing", None)


def test_a_value_added_later_fails_rather_than_slipping_through():
    """A new exported value never reaches the comparison.

    The names are parsed off the file and matched against the names the
    imported module carries, so neither count is typed here.
    """
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    parsed = set()
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for one in targets:
            if isinstance(one, ast.Name) and one.id.isupper():
                parsed.add(one.id)
    imported = set(surface_constants())
    assert parsed - imported == set(), sorted(parsed - imported)
    assert imported - parsed == set(), sorted(imported - parsed)
    assert len(parsed) == len(imported)
    assert "USD_FORMAT" in parsed


# The rest of the surface, against the shipped side


def test_the_admission_rule_agrees_with_the_shipped_one():
    """The surface admits a value the shipped reader refuses, or the reverse."""
    from src.trading.bot_container import as_finite_float

    for value in (
        0,
        1,
        -1,
        12.7,
        -0.0,
        True,
        False,
        None,
        "20",
        "abc",
        NAN,
        INFINITY,
        -INFINITY,
        HUGE_INT,
        2**1023,
        2**1024,
        [],
        {},
        BILLIONTH,
        THOUSAND_MILLION,
    ):
        theirs = as_finite_float(value)
        mine = surface.finite_number(value)
        assert repr(mine) == repr(theirs), (value, mine, theirs)
    assert surface.NOT_A_NUMBER is None


def test_the_refresh_outcomes_are_the_shipped_tabs():
    """A refresh reported an outcome the shipped tab never returns."""
    app()
    host = Host(HostBot(CASES["one_tranche"]))
    assert host._refresh_fold_tranches_tab() == surface.REFRESH_NO_TAB
    assert surface.REFRESH_NOT_LOCATED_FORMAT.format(error="RuntimeError").startswith(
        "not refreshed: "
    )
    assert surface.REFRESH_RAISED_FORMAT.format(
        error="ValueError", message="x"
    ).startswith("not refreshed: rebuilding")
    model = surface.FoldTranchesTabModel(
        surface.build_bot(CASES["one_tranche"]),
        now=NOW,
        refresh_result=surface.REFRESH_NO_TAB,
    )
    model.build()
    assert model.refresh() == surface.REFRESH_NO_TAB
    assert model.settle("x")[0] == surface.SETTLE_NOT_REBUILT_FORMAT.format(
        refresh=surface.REFRESH_NO_TAB
    )


def test_the_save_is_told_which_clear_asked_for_it():
    """The save was run without being told what it was saving after."""
    app()
    host, page = old_tab("one_tranche")
    assert host.saved == []
    assert host._settle_after_clear(surface.CLEAR_FOLD_TITLE)
    assert host.saved == [surface.CLEAR_FOLD_TITLE], host.saved
    model = clearing_model()
    model.clear_wire(surface.YES_BUTTON_VALUE)
    assert model.save.saved == [surface.CLEAR_WIRE_TITLE], model.save.saved


def test_the_settle_lines_report_the_step_that_actually_ran():
    """A save that never happened was reported as done."""
    assert surface.settle_lines(surface.REFRESH_DONE, True, "") == [
        surface.SETTLE_REBUILT,
        surface.SETTLE_SAVED,
    ]
    got = surface.settle_lines("not refreshed: x", False, surface.SAVE_NO_MANAGER)
    assert got[0].startswith("The panel was not refreshed")
    assert surface.SAVE_NO_MANAGER in got[1]


def test_a_save_that_cannot_run_is_named_rather_than_swallowed():
    """A clear that never reached disk reported that it had."""
    model = clearing_model()
    model.save = surface.SaveSink(has_saver=False)
    model.clear_fold(surface.YES_BUTTON_VALUE)
    assert surface.SAVE_NO_MANAGER in model.settled[1]
    model = clearing_model()
    model.save = surface.SaveSink(raises=OSError("the disk is full"))
    model.clear_fold(surface.YES_BUTTON_VALUE)
    assert "OSError" in model.settled[1]


def test_a_coloured_row_carries_the_style_the_tab_writes():
    """A colour reached the row without the style the tab wraps it in."""
    assert (
        surface.COLOUR_STYLE_FORMAT.format(colour=surface.FOLD_OVER_ALLOTMENT_FG_HEX)
        == "color: #ff3366;"
    )
    text, colour = surface.units_marked_row([tranche(units=2.0)], 1.0)
    assert colour == surface.FOLD_OVER_ALLOTMENT_FG_HEX, text
    text, colour = surface.units_marked_row([tranche(units=0.5)], 1.0)
    assert colour is surface.NO_CELL_COLOR, text


def test_the_row_controls_carry_the_shipped_tooltips():
    """A control lost the words that say what it does."""
    app()
    from PySide6.QtWidgets import QComboBox, QLineEdit

    host, page = old_tab("many_tranches")
    combo = page.findChildren(QComboBox)[0]
    edit = page.findChildren(QLineEdit)[0]
    assert combo.toolTip() == surface.SORT_TOOLTIP
    assert edit.toolTip() == surface.FILTER_TOOLTIP
    assert edit.placeholderText() == surface.FILTER_PLACEHOLDER


ORDER_CASES = (
    surface.SORT_QUEUE_ORDER,
    surface.SORT_OLDEST_FIRST,
    surface.SORT_NEWEST_FIRST,
    surface.SORT_LARGEST_FIRST,
    surface.SORT_SMALLEST_FIRST,
    "an order this panel never offers",
)


@pytest.mark.parametrize("order", ORDER_CASES)
def test_the_row_order_is_the_shipped_tabs(order):
    """A row order put a tranche somewhere the shipped tab does not."""
    from src.gui.live_settings.fold_tokens import fold_display_order

    rows = [
        tranche(usd=3.0, created_ts=NOW - 30.0),
        tranche(usd=1.0, created_ts=NOW - 10.0),
        tranche(usd=2.0, created_ts=NOW - 20.0),
        tranche(usd=NAN, created_ts=NAN),
    ]
    theirs = [[index, one] for index, one in fold_display_order(rows, order)]
    mine = surface.display_order(rows, order)
    assert mine == theirs, order


FILTER_CASES = ("", "  ", "BTC", "btc", "$1", "—", "nothing here", "É")


@pytest.mark.parametrize("needle", FILTER_CASES)
def test_the_row_filter_is_the_shipped_tabs(needle):
    """The filter hid a row the shipped filter shows, or the reverse."""
    from src.gui.live_settings.fold_tokens import fold_row_matches_filter

    cells = ["1", "1.0h", "0.500000", "$12.5000", "BTC", None, "—"]
    assert surface.row_matches_filter(cells, needle) == fold_row_matches_filter(
        cells, needle
    ), needle


def test_the_filter_hides_rows_without_moving_any():
    """A filter re-ordered the rows the Fire buttons are drawn on."""
    model = new_model("many_tranches")
    before = [list(one) for one in model.rows]
    hidden = model.apply_filter("$1.0000")
    assert model.rows == before
    assert hidden.count(False) == 1, hidden
    assert model.apply_filter("").count(True) == 0


def test_choosing_an_order_the_panel_does_not_offer_changes_nothing():
    """An order nobody offers reached the sorter."""
    model = new_model("many_tranches")
    assert model.choose_order("no such order") == surface.SORT_QUEUE_ORDER
    assert model.choose_order(surface.SORT_QUEUE_ORDER) == surface.SORT_QUEUE_ORDER
    assert model.choose_order(surface.SORT_LARGEST_FIRST) == surface.SORT_LARGEST_FIRST
    assert model.rows[0][3] == surface.USD_FORMAT.format(usd=3.0), model.rows


def test_the_source_label_is_the_shipped_tabs():
    """A tranche's provenance was named differently on the two sides."""
    from src.gui.live_settings.fold_tokens import _fold_tranche_source_label

    for one in (
        {},
        {"operator_initiated": True},
        {"operator_initiated": False},
        {"operator_initiated": 0},
        {"operator_initiated": ""},
        {"operator_initiated": "yes"},
    ):
        assert surface.source_label(one) == _fold_tranche_source_label(one), one


def test_the_arbiter_label_is_the_shipped_tabs():
    """An Arbiter setting was worded differently on the two sides."""
    from src.gui.live_settings.fold_tokens import _arbiter_label

    for one in ("parent", "sibling", "PARENT", None, 1, "", "nobody"):
        assert surface.arbiter_label(one) == _arbiter_label(one), one


def test_the_close_ratio_is_the_shipped_tabs():
    """The health verdict read a different quantity on the two sides."""
    from src.gui.live_settings.fold_tokens import compose_cycle_close_ratio

    for created, closed, discarded in (
        (0, 0, 0),
        (10, 6, 1),
        (160, 118, 42),
        (4, 4, 0),
        (100, 40, 0),
        (100, 70, 0),
        (100, 90, 0),
        (5, 0, 10),
        (-5, -2, -1),
    ):
        theirs = compose_cycle_close_ratio(created, closed, discarded)
        assert surface.cycle_close_ratio(created, closed, discarded) == list(theirs), (
            created,
            closed,
            discarded,
        )


def test_the_units_marked_row_is_the_shipped_tabs():
    """The allotment row reported a different multiple on the two sides."""
    from src.gui.live_settings.fold_tokens import compose_units_marked_row

    for rows, held in (
        ([], 0.0),
        ([tranche()], 1.0),
        ([tranche(units=1.99)], 1.0),
        ([tranche(units=True)], 1.0),
        ([tranche(units=NAN)], 1.0),
        ([tranche()], NAN),
        ([tranche()], -1.0),
        ([tranche()], HUGE_INT),
    ):
        theirs = compose_units_marked_row(rows, held)
        assert surface.units_marked_row(rows, held) == list(theirs), (rows, held)


def test_the_despawn_preview_is_the_shipped_rule():
    """The preview counted a record the sweep would not take."""
    from src.trading.bot_container import despawn_preview

    fold = [
        tranche(created_ts=NOW - 8 * 86400.0),
        tranche(created_ts=NOW - 100.0),
        tranche(created_ts=None),
        tranche(created_ts=True),
        tranche(created_ts=NAN, usd=NAN, units=NAN),
    ]
    stack = [
        {"opened_ts": NOW - 30 * 86400.0, "status": "pending", "order_id": "x"},
        {"opened_ts": NOW - 30 * 86400.0, "status": "filled", "order_id": None},
        {"opened_ts": None},
    ]
    for days in (0, 7, 14, 30, 60, -5, NAN, INFINITY, HUGE_INT, True, "7"):
        theirs = despawn_preview(fold, stack, days, NOW)
        assert surface.despawn_preview(fold, stack, days, NOW) == theirs, days
    assert surface.despawn_preview(fold, stack, 7, NAN) == despawn_preview(
        fold, stack, 7, NAN
    )


def test_the_despawn_threshold_is_the_shipped_rule():
    """The armed threshold read differently on the two sides."""
    from src.trading.bot_container import despawn_threshold_days

    for days in (0, 7, 30.7, -5, NAN, INFINITY, HUGE_INT, True, "7", None):
        config = HostConfig(despawn_days=days)
        assert surface.despawn_threshold_days(config) == despawn_threshold_days(
            config
        ), days


# The bridge

BRIDGE_BOT = {
    "symbol": "BTC/USD",
    "tranches": [tranche()],
    "holdings": 1.0,
    "price": 95.0,
    "created": 10,
    "closed": 6,
    "discarded": 1,
}


def bridge_call(params):
    """One request through the real registry, as the frontend sends it."""
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": 58, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_fold_tranches_method():
    """The frontend cannot reach the tab it was given."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model
    frame = bridge_call({"reset": True, "bot": BRIDGE_BOT, "now": NOW})
    assert frame["ok"] is True, frame
    assert frame["result"]["method"] == "fold_tranches_tab.state"


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = surface.build_view_model(new_model("many_tranches"))
    back = json.loads(json.dumps(payload, default=repr))
    assert back["tab_label"] == "Fold Tranches"
    assert back["table"]["columns"][0] == "#"
    assert back["table"]["arbiter_column"] == 10


def test_the_bridge_keeps_what_was_typed_until_a_reset():
    """The tab forgot the operator's row order between two paints."""
    bridge_call({"reset": True, "bot": BRIDGE_BOT, "now": NOW})
    first = bridge_call({"order": surface.SORT_LARGEST_FIRST})["result"]
    assert first["row_controls"]["order"] == surface.SORT_LARGEST_FIRST
    kept = bridge_call({})["result"]
    assert kept["row_controls"]["order"] == surface.SORT_LARGEST_FIRST
    fresh = bridge_call({"reset": True})["result"]
    assert fresh["row_controls"]["order"] == surface.SORT_QUEUE_ORDER
    bridge_call({"reset": True})


def test_the_bridge_carries_every_action():
    """An action the tab offers cannot be reached over the bridge."""
    bridge_call({"reset": True, "bot": BRIDGE_BOT, "now": NOW})
    cleared = bridge_call({"clear": "fold", "clear_answer": surface.YES_BUTTON_VALUE})[
        "result"
    ]
    assert cleared["outcome"] == surface.OUTCOME_CLEARED
    bridge_call({"reset": True, "bot": BRIDGE_BOT, "now": NOW})
    fired = bridge_call(
        {
            "manager": {"async_loop": "a-loop"},
            "fire_index": 0,
            "fire_number": 1,
            "fire_answer": surface.YES_BUTTON_VALUE,
        }
    )["result"]
    assert fired["outcome"] == surface.OUTCOME_DISPATCHED
    polled = bridge_call({"poll": {"number": 1, "done": True, "result": None}})[
        "result"
    ]
    assert polled["outcome"] == surface.OUTCOME_NOT_APPLIED
    arb = bridge_call({"arbiter": {"tranche_id": "t", "child_bot_id": "kid"}})["result"]
    assert arb["outcome"] == surface.OUTCOME_NO_REGISTRY
    bridge_call({"reset": True})


# Without Qt at all

BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

COUNT_SOCKETS = (
    "import socket, json\n"
    "_tried = []\n"
    "_real_connect = socket.socket.connect\n"
    "def _watched(self, address, *rest):\n"
    "    _tried.append(repr(address))\n"
    "    return _real_connect(self, address, *rest)\n"
    "socket.socket.connect = _watched\n"
)

BRIDGE_PROBE = (
    COUNT_SOCKETS + "import json, sys\n"
    "from src.core import desktop_bridge\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
    "    'method': 'fold_tranches_tab.state', 'params': {'reset': True,\n"
    "    'now': 1700000000.0, 'bot': {'symbol': 'BTC/USD', 'created': 10,\n"
    "    'closed': 6, 'discarded': 1, 'holdings': 1.0, 'price': 95.0,\n"
    "    'tranches': [{'usd': 12.5, 'units': 0.5, 'ref': 100.0,\n"
    "    'initial_buy_price': 90.0, 'created_ts': 1699996400.0}]}}}),\n"
    "    desktop_bridge.build_registry())\n"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules,\n"
    "    'sockets': _tried}))\n"
)

HEADLESS_PROBE = (
    BLOCK_QT + COUNT_SOCKETS + "import json, sys\n"
    "from src.gui.main_tabs import fold_tranches_tab_surface as s\n"
    "bot = s.build_bot({'symbol': 'BTC/USD', 'created': 10, 'closed': 6,\n"
    "    'discarded': 1, 'holdings': 1.0, 'price': 95.0,\n"
    "    'tranches': [{'usd': 12.5, 'units': 0.5, 'ref': 100.0,\n"
    "    'initial_buy_price': 90.0, 'created_ts': 1699996400.0}]})\n"
    "m = s.FoldTranchesTabModel(bot, now=1700000000.0, otd_pct=3.6,\n"
    "    otd_factor=0.964)\n"
    "m.build()\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'rows': m.rows, 'health': m.health_rows, 'buttons': m.buttons,\n"
    "    'calls': len(m.calls), 'sockets': _tried}))\n"
)

INERT_PROBE = (
    BLOCK_QT + COUNT_SOCKETS + "import json, sys, io, os, time\n"
    "_opened = []\n"
    "_real_open = io.open\n"
    "def _watched_open(file, *rest, **kw):\n"
    "    _opened.append(str(file))\n"
    "    return _real_open(file, *rest, **kw)\n"
    "_clocks = []\n"
    "_real_time = time.time\n"
    "time.time = lambda: (_clocks.append(1), _real_time())[1]\n"
    "_real_mono = time.monotonic\n"
    "time.monotonic = lambda: (_clocks.append(1), _real_mono())[1]\n"
    "import src.gui.main_tabs.fold_tranches_tab_surface as s\n"
    "sys.modules.pop('src.gui.main_tabs.fold_tranches_tab_surface')\n"
    "io.open = _watched_open\n"
    "_clocks.clear()\n"
    "import importlib\n"
    "importlib.import_module('src.gui.main_tabs.fold_tranches_tab_surface')\n"
    "io.open = _real_open\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules, 'clocks': len(_clocks),\n"
    "    'opened': [one for one in _opened if 'fold_tranches' in one],\n"
    "    'sockets': _tried, 'method': s.METHOD}))\n"
)


def run_script(source, extra_env=None):
    """Run one probe in a fresh process and return what it printed."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    if extra_env:
        env.update(extra_env)
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return json.loads(done.stdout.decode(errors="replace").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the Fold Tranches tab pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["sockets"] == []
    assert answered["frame"]["ok"] is True, answered["frame"]
    result = answered["frame"]["result"]
    assert result["method"] == "fold_tranches_tab.state"
    assert result["table"]["columns"] == list(surface.COLUMNS)
    assert result["table"]["row_count"] == 1
    assert result["panel_shows"]["open_tranches_label"] == "1"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore\n" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_socket_counter_can_report_a_connection():
    """The connection counter reports none whatever the process opened."""
    probe = COUNT_SOCKETS + (
        "import json, socket\n"
        "keeper = socket.socket()\n"
        "keeper.bind(('127.0.0.1', 0))\n"
        "keeper.listen(1)\n"
        "talker = socket.create_connection(keeper.getsockname())\n"
        "talker.close()\n"
        "keeper.close()\n"
        "print(json.dumps({'sockets': _tried}))\n"
    )
    assert len(run_script(probe)["sockets"]) == 1


def test_the_socket_counter_reaches_a_child_process():
    """The counter watches only the process that installed it."""
    probe = COUNT_SOCKETS + (
        "import json, subprocess, sys, os\n"
        "child = subprocess.run([sys.executable, '-c',\n"
        "    'import socket,sys;"
        "k=socket.socket();k.bind((chr(49)+chr(50)+chr(55)+chr(46)+chr(48)"
        "+chr(46)+chr(48)+chr(46)+chr(49),0));k.listen(1);"
        "t=socket.create_connection(k.getsockname());"
        "sys.stdout.write(chr(49));t.close();k.close()'],\n"
        "    capture_output=True, timeout=60)\n"
        "print(json.dumps({'sockets': _tried, 'child': child.stdout.decode(),\n"
        "    'code': child.returncode}))\n"
    )
    answered = run_script(probe)
    assert answered["code"] == 0, answered
    assert answered["child"] == "1", answered
    assert answered["sockets"] == [], answered


def test_the_surface_builds_the_tab_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["sockets"] == []
    assert len(answered["rows"]) == 1
    assert answered["rows"][0][0] == "1"
    assert answered["rows"][0][3] == "$12.5000"
    assert answered["buttons"][0] == ["Clear 1 Fold Tranche(s)", True]
    assert answered["calls"] > 10
    labels = [one[0] for one in answered["health"]]
    assert labels[0] == surface.OPEN_COUNT_ROW


def test_the_qt_block_stops_the_module_that_paints_the_tab():
    """The Qt block let the shipped tab through."""
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui.live_settings import fold_tranches_tab\n"
        "    _reached = True\n"
        "except ImportError:\n"
        "    _reached = False\n"
        "print(json.dumps({'reached': _reached}))\n"
    )
    assert run_script(probe)["reached"] is False


def test_importing_the_surface_reads_no_clock_and_opens_no_file():
    """Importing the surface touched the world before it was asked to."""
    answered = run_script(INERT_PROBE)
    assert answered["qt"] is False
    assert answered["clocks"] == 0, answered
    assert answered["opened"] == [], answered
    assert answered["sockets"] == []
    assert answered["method"] == "fold_tranches_tab.state"


def test_a_run_under_a_throwaway_home_writes_no_file():
    """Building the tab wrote into the operator's runtime tree."""
    import tempfile

    with tempfile.TemporaryDirectory() as home:
        probe = HEADLESS_PROBE.replace(
            "print(json.dumps({'qt'",
            "import os as _os\n"
            "_seen = []\n"
            "for _root, _dirs, _files in _os.walk(_os.environ['ACERVATOR_TEST_HOME']):\n"
            "    _seen.extend(_os.path.join(_root, _one) for _one in _files)\n"
            "print(json.dumps({'written': _seen, 'qt'",
        )
        answered = run_script(
            probe,
            {"ACERVATOR_TEST_HOME": home, "HOME": home, "USERPROFILE": home},
        )
        assert answered["written"] == [], answered["written"]
        assert len(answered["rows"]) == 1
        control = Path(home) / "a-file-the-control-wrote"
        control.write_text("x", encoding="utf-8")
        answered = run_script(
            probe,
            {"ACERVATOR_TEST_HOME": home, "HOME": home, "USERPROFILE": home},
        )
        assert answered["written"] == [str(control)], answered["written"]


# Order independence


def test_the_clock_swap_is_restored_after_a_drive():
    """A pinned clock outlived the drive that needed it."""
    original = time.time
    with PinnedClock(NOW) as clock:
        assert time.time() == NOW
        assert time.time is not original
    assert time.time is original
    assert clock.seen == 1
    assert clock.refused is None, clock.refused
    assert clock.traced is False


def test_the_clock_swap_is_restored_after_a_refusal():
    """A drive that refused part way left the clock pinned."""
    original = time.time
    watched = PinnedClock(NOW)
    with pytest.raises(ValueError):
        with watched:
            time.time()
            raise ValueError("the drive refused")
    assert watched.refused is ValueError, watched.refused
    assert str(watched.refusal) == "the drive refused", watched.refusal
    assert watched.traced is True
    assert watched.seen == 1, watched.seen
    assert time.time is original
    assert time.time() != NOW


def test_the_shipped_builder_writes_only_onto_the_dialog_it_was_handed():
    """The shipped builder wrote onto something other than its own dialog."""
    app()
    before = dict(vars(shipped))
    host, page = old_tab("many_tranches")
    assert dict(vars(shipped)) == before, "the shipped module gained a value"
    written = {name for name in vars(host) if name.startswith("_fold")}
    assert written, "the builder set no handle on the dialog"
    other = Host(HostBot(CASES["empty"]))
    assert not [name for name in vars(other) if name.startswith("_fold")]


def test_two_models_do_not_share_a_state():
    """One model's build reached another model's rows."""
    first = new_model("many_tranches")
    second = new_model("empty")
    assert len(first.rows) == 3
    assert second.rows == []
    assert surface.PANE_MODEL is not first
    assert surface.PANE_MODEL is not second


# Pictures


def old_payload(name):
    """The shipped tab's snapshot, sealed as it comes off the widget."""
    return sealed(old_snapshot(name))


def new_payload(name):
    """The surface's snapshot, sealed as it comes off the model."""
    return sealed(new_snapshot(name))


def picture_tab(payload):
    """A widget painted only from what a sealed payload carries."""
    from PySide6.QtWidgets import (
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    payload = unaltered(payload)
    page = hold(QWidget())
    column = QVBoxLayout(page)
    column.setSpacing(surface.CONTENT_SPACING_PX)
    group = QGroupBox(surface.HEALTH_GROUP_TITLE)
    form = QFormLayout(group)
    form.setHorizontalSpacing(12)
    form.setVerticalSpacing(8)
    for label, value in payload["health_rows"]:
        form.addRow(str(label), QLabel(str(value)))
    column.addWidget(group)
    row = QHBoxLayout()
    for text, enabled in payload["buttons"]:
        button = QPushButton(str(text))
        button.setEnabled(bool(enabled))
        button.setStyleSheet(surface.DANGER_BUTTON_STYLE)
        row.addWidget(button)
    row.addStretch()
    column.addLayout(row)
    if payload["table_shown"]:
        table = QTableWidget()
        table.setColumnCount(len(payload["table_headers"]))
        table.setHorizontalHeaderLabels(list(payload["table_headers"]))
        table.setRowCount(len(payload["table_rows"]))
        for index, cells in enumerate(payload["table_rows"]):
            for column_index, text in enumerate(cells):
                table.setItem(index, column_index, QTableWidgetItem(str(text)))
        table.verticalHeader().setDefaultSectionSize(surface.TRANCHE_ROW_HEIGHT_PX)
        column.addWidget(table)
    else:
        note = QLabel(surface.EMPTY_TEXT)
        note.setWordWrap(surface.EMPTY_WORD_WRAP)
        note.setStyleSheet(surface.EMPTY_STYLE)
        column.addWidget(note)
    column.addStretch()
    return page


def old_picture(name):
    """One widget painted from the shipped tab's own values."""
    app()
    return picture_tab(old_payload(name))


def new_picture(name):
    """One widget painted from the surface's values."""
    app()
    return picture_tab(new_payload(name))


def render(widget):
    """One render at the size every picture check here uses."""
    from tests.qt_pixel import render_widget

    return render_widget(widget, PIXEL_SIZE)


PICTURE_CASES = ("empty", "one_tranche", "many_tranches", "extractor_and_fold")


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different panel than the shipped tab."""
    app()
    old = render(old_picture(name))
    new = render(new_picture(name))
    assert_picture_can_report(old, note=f"old side, {name}")
    assert_picture_can_report(new, note=f"new side, {name}")
    assert old.size() == new.size()
    assert colour_count(old) == colour_count(new), (
        f"case {name!r} painted {colour_count(old)} colours on the shipped "
        f"side and {colour_count(new)} on the surface"
    )


def test_the_picture_comparison_reports_two_different_real_cases():
    """The picture comparison passes whatever the second side paints."""
    app()
    assert_cases_paint_differently(
        old_side=render(old_picture("empty")),
        new_side=render(new_picture("many_tranches")),
        note="an empty queue against three tranches",
    )


def test_the_colour_count_per_state_is_reported():
    """A state paints one colour, so no comparison of it can report."""
    app()
    counted = {name: colour_count(render(old_picture(name))) for name in PICTURE_CASES}
    for name, found in counted.items():
        assert found > 1, (name, found)
    assert len(set(counted.values())) > 1, counted


def test_the_tab_declares_one_skin_on_both_sides():
    """A colour the surface ships is one the shipped tab never paints."""
    app()
    assert_same_skin(
        build_old_side=lambda: old_picture("many_tranches"),
        build_new_side=lambda: new_picture("many_tranches"),
        size=PIXEL_SIZE,
        control_rule=CONTROL_RULE,
        note="the health box and the table",
    )


@skip_unless_no_fonts
def test_without_fonts_two_equal_length_rows_paint_alike():
    """Every family resolved to a real glyph on a run that has none."""
    from tests.fixtures.host_fonts import (
        NARROW_LABEL,
        WIDE_LABEL,
        app_font_advance_px,
    )

    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_with_fonts_two_equal_length_rows_paint_apart():
    """A run holding fonts measured every glyph at one width."""
    from tests.fixtures.host_fonts import (
        NARROW_LABEL,
        WIDE_LABEL,
        app_font_advance_px,
    )

    app()
    assert app_font_advance_px(NARROW_LABEL) < app_font_advance_px(WIDE_LABEL)


# This file's own checks


SKIN_READERS = (
    "styleSheet",
    "palette",
    "background",
    "foreground",
    "property",
    "color",
    "brush",
)


def reads_a_live_skin(path):
    """Every CALL in one file that reads a skin off a live Qt object.

    Read off the parsed tree, never off the text, so the names listed
    above cannot match themselves where this check writes them down.
    """
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in SKIN_READERS:
            found.append(path.name + ":" + str(node.lineno) + " ." + node.func.attr)
    return found


def test_this_file_reads_no_skin_off_a_live_widget():
    """A colour was read off a live object rather than off a render."""
    assert reads_a_live_skin(Path(__file__)) == []
    assert reads_a_live_skin(SURFACE_PATH) == []


def test_the_live_skin_sweep_reports_a_file_that_really_reads_one():
    """The sweep returns nothing whatever a file reads."""
    found = reads_a_live_skin(LIVE_SKIN_CONTROL)
    assert len(found) >= 6, found


def compared_to_itself(path):
    """Every assertion in one file that compares a value with itself."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Assert):
            continue
        for inner in ast.walk(node.test):
            if not isinstance(inner, ast.Compare):
                continue
            sides = [ast.unparse(inner.left)] + [
                ast.unparse(one) for one in inner.comparators
            ]
            if len(set(sides)) != len(sides):
                found.append(f"{path.name}:{inner.lineno}")
    return found


def constant_only_assertions(path):
    """Every assertion in one file whose test reads only literals."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Assert):
            continue
        names = [
            one
            for one in ast.walk(node.test)
            if isinstance(one, (ast.Name, ast.Attribute, ast.Call, ast.Subscript))
        ]
        if not names:
            found.append(f"{path.name}:{node.lineno}")
    return found


def test_no_assertion_here_compares_a_value_with_itself():
    """An assertion reads one expression on both sides, so it cannot fail."""
    assert compared_to_itself(Path(__file__)) == []


def test_no_assertion_here_reads_only_a_constant():
    """An assertion reads no value the product produced."""
    assert constant_only_assertions(Path(__file__)) == []


def test_the_two_blind_assertion_sweeps_report_what_they_look_for():
    """Either sweep returns nothing whatever the source holds."""
    made = REPO_ROOT / "tests" / "_fold_tranches_sweep_control.py"
    made.write_text(
        "def check():\n    assert 1 == 1\n    assert len([]) == len([])\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        assert compared_to_itself(made) == [
            f"{made.name}:2",
            f"{made.name}:3",
        ], compared_to_itself(made)
        assert constant_only_assertions(made) == [f"{made.name}:2"]
        clean = REPO_ROOT / "tests" / "_fold_tranches_sweep_clean.py"
        clean.write_text(
            "def check(left, right):" + chr(10) + "    assert left == right" + chr(10),
            encoding="utf-8",
            newline=chr(10),
        )
        try:
            assert compared_to_itself(clean) == []
            assert constant_only_assertions(clean) == []
        finally:
            clean.unlink()
    finally:
        made.unlink()
