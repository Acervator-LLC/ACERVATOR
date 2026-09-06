"""The shipped Bot Swarm tab and the Qt-free surface, side by side.

A failure means the view model carries a different row colour, a
different column width, a different label, a different number format, a
different wire offset, a different hit distance, a different route, a
different exchange list, a different privacy glyph or a different empty
message than ``src.gui.bot_visualizer`` builds.

The fleet every case is driven with comes from a stored fleet load in
the shape of ``bot_state.json``. Nothing here reads the operator's own
file: ``StateManager`` is stood in for, and the stand-in hands back
``STORED_FLEET`` and nothing else.
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
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QTimer, SignalInstance, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from src.core import event_bus as eb
from src.core import privacy_mask_registry as pmr
from src.core import state_manager as sm
from src.gui import bot_visualizer as shipped
from src.gui.main_tabs import bot_visualizer_surface as surface
from tests.fixtures.host_fonts import has_real_fonts, load_run_fonts
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

SHIPPED_PATH = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
SURFACE_PATH = REPO_ROOT / "src" / "gui" / "main_tabs" / "bot_visualizer_surface.py"

SHIPPED_SOURCE = SHIPPED_PATH.read_text(encoding="utf-8")
SURFACE_SOURCE = SURFACE_PATH.read_text(encoding="utf-8")

METHOD_NAME = "bot_visualizer.state"
MASK_FIELD = "bot_swarm.identifiers"

ROW_SIZE = (720, 40)
CONTROL_RULE = "QFrame { background: #7d1a4a; }"

LOOPBACK = {"127.0.0.1", "::1", "localhost"}

LONG_TEXT = "y" * 200
UNICODE_TEXT = "\u00e9\u4e2d\U0001f600 caf\u00e9"
MARKUP_TEXT = "<b>bold</b> & <i>x</i>"
APOSTROPHE_TEXT = "it's the operator's bot"
NEWLINE_TEXT = "first\nsecond"
WRONG_CAPITALS_TEXT = "rEaLiSeD"
THOUSAND_MILLION = 1_000_000_000
ONE_BILLIONTH = 1e-09
NOT_A_NUMBER = float("nan")
INFINITY = float("inf")
MINUS_INFINITY = float("-inf")
TWO_TO_1023 = 2**1023
TWO_TO_1024 = 2**1024
HUGE_INTEGER = 10**400


@pytest.fixture(autouse=True, scope="module")
def app():
    """One application object for every render in this file."""
    load_run_fonts()
    return QApplication.instance() or QApplication([])


# The stored fleet load every case is driven with

STORED_FLEET = {
    "bots": {
        "BTC-USD-0001": {
            "symbol": "BTC/USD",
            "exchange": "coinbase",
            "stats": {"ytd_folded_usd": 120.5, "ytd_scrummed_usd": 340.25},
            "scrumming_state": {
                "smart_wire_routes": [
                    {"dest_bot_id": "ETH-USD-0002", "pct": 25.0},
                    {"dest_bot_id": "", "pct": 10.0},
                ]
            },
        },
        "ETH-USD-0002": {
            "symbol": "ETH/USD",
            "exchange": "coinbase",
            "stats": {"ytd_folded_usd": 0.0, "ytd_scrummed_usd": 12.0},
            "scrumming_state": {
                "smart_wire_routes": [{"dest_bot_id": "SOL-USD-0003", "pct": 0.0}]
            },
        },
        "SOL-USD-0003": {
            "symbol": "SOL/USD",
            "exchange": "kraken",
            "stats": {"ytd_folded_usd": 9.75, "ytd_scrummed_usd": 0.0},
            "scrumming_state": {
                "smart_wire_routes": [{"dest_bot_id": "GONE-0009", "pct": 40.0}]
            },
        },
    }
}

STORED_FLEET_EMPTY: dict = {"bots": {}}

STORED_FLEET_ONE_BOT = {
    "bots": {
        "BTC-USD-0001": {
            "symbol": "BTC/USD",
            "exchange": "coinbase",
            "stats": {"ytd_folded_usd": 1.0, "ytd_scrummed_usd": 2.0},
            "scrumming_state": {"smart_wire_routes": []},
        }
    }
}

STORED_FLEET_WRONG_TYPES = {
    "bots": {
        "BTC-USD-0001": {
            "symbol": 42,
            "exchange": 7,
            "stats": "not-a-mapping",
            "ytd_folded_usd": True,
            "ytd_scrummed_usd": "12.7",
            "scrumming_state": {"smart_wire_routes": "not-a-list"},
        },
        "ETH-USD-0002": "not-a-bot",
        "SOL-USD-0003": {
            "symbol": None,
            "exchange": None,
            "scrumming_state": {"smart_wire_routes": ["not-a-route", 7]},
        },
    }
}

STORED_FLEET_NO_WIRES = {
    "bots": {
        "BTC-USD-0001": {
            "symbol": "BTC/USD",
            "exchange": "coinbase",
            "stats": {"ytd_folded_usd": 5.0, "ytd_scrummed_usd": 6.0},
        },
        "ETH-USD-0002": {
            "symbol": "ETH/USD",
            "exchange": "gemini",
            "stats": {"ytd_folded_usd": 7.0, "ytd_scrummed_usd": 8.0},
        },
    }
}

STATUS_KEYS = ("symbol", "exchange", "stats", "ytd_folded_usd", "ytd_scrummed_usd")


def fleet_statuses(state: dict) -> list:
    """The status list a stored fleet load produces for the locust grid.

    This stands in for the running fleet: every field it carries is read
    straight out of the load, so the grid and the wires describe one
    fleet rather than two.
    """
    found = []
    for bot_id, bot in (state.get("bots") or {}).items():
        status = {"bot_id": bot_id}
        if isinstance(bot, dict):
            for key in STATUS_KEYS:
                if key in bot:
                    status[key] = bot[key]
        found.append(status)
    return found


# The cases both sides are driven with


def case(name, state=None, steps=()):
    """One driven case: a stored fleet load and the steps applied to it."""
    return {
        "name": name,
        "state": STORED_FLEET if state is None else state,
        "steps": list(steps),
    }


LOAD = ("update_bots",)

CASES = [
    case("happy", steps=[LOAD]),
    case("empty_fleet", STORED_FLEET_EMPTY, [LOAD]),
    case("one_bot", STORED_FLEET_ONE_BOT, [LOAD]),
    case("bot_with_no_wires", STORED_FLEET_NO_WIRES, [LOAD]),
    case("wire_names_a_bot_that_is_not_there", steps=[LOAD]),
    case("fleet_stored_with_wrong_types", STORED_FLEET_WRONG_TYPES, [LOAD]),
    case(
        "sim_run",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"asset": "BTC-2021", "capital": 400}),
            ("update", "sim", "s1", {"pnl": 12.5, "trades": 4, "candle_idx": 50}),
        ],
    ),
    case(
        "sim_run_zero_progress",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"capital": 0, "candle_total": 0}),
            ("update", "sim", "s1", {"pnl": 0, "trades": 0, "candle_idx": 0}),
        ],
    ),
    case(
        "sim_run_negative_pnl",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"capital": -25}),
            ("update", "sim", "s1", {"pnl": -99.5, "trades": -3, "candle_idx": -5}),
        ],
    ),
    case(
        "sim_run_over_the_end",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"candle_total": 10}),
            ("update", "sim", "s1", {"pnl": 1, "trades": 1, "candle_idx": 99}),
            ("stop", "sim", "s1", {"pnl": 2.25, "trades": 7}),
        ],
    ),
    case(
        "sim_run_thousand_million",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"capital": THOUSAND_MILLION}),
            (
                "update",
                "sim",
                "s1",
                {"pnl": THOUSAND_MILLION, "trades": THOUSAND_MILLION, "candle_idx": 1},
            ),
        ],
    ),
    case(
        "sim_run_one_billionth",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"capital": ONE_BILLIONTH}),
            ("update", "sim", "s1", {"pnl": ONE_BILLIONTH, "trades": 0}),
        ],
    ),
    case(
        "sim_run_two_to_1023",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"capital": TWO_TO_1023}),
            ("update", "sim", "s1", {"pnl": float(TWO_TO_1023), "trades": 1}),
        ],
    ),
    case(
        "sim_run_two_to_1024",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"capital": TWO_TO_1024}),
            ("update", "sim", "s1", {"pnl": TWO_TO_1024, "trades": 1}),
        ],
    ),
    case(
        "sim_run_stored_true_where_a_number_belongs",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"capital": True}),
            ("update", "sim", "s1", {"pnl": True, "trades": True, "candle_idx": True}),
        ],
    ),
    case(
        "sim_run_text_where_a_number_belongs",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {"capital": "four hundred"}),
        ],
    ),
    case(
        "sim_run_not_a_number_capital",
        steps=[LOAD, ("register", "sim", "s1", "SIM-01", {"capital": NOT_A_NUMBER})],
    ),
    case(
        "sim_run_infinity_capital",
        steps=[LOAD, ("register", "sim", "s1", "SIM-01", {"capital": INFINITY})],
    ),
    case(
        "sim_run_minus_infinity_capital",
        steps=[LOAD, ("register", "sim", "s1", "SIM-01", {"capital": MINUS_INFINITY})],
    ),
    case(
        "sim_run_not_a_number_progress",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {}),
            (
                "update",
                "sim",
                "s1",
                {"pnl": 0, "trades": 0, "candle_idx": NOT_A_NUMBER},
            ),
        ],
    ),
    case(
        "sim_run_infinite_progress",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {}),
            ("update", "sim", "s1", {"pnl": 0, "trades": 0, "candle_idx": INFINITY}),
        ],
    ),
    case(
        "sim_run_not_a_number_pnl",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {}),
            ("update", "sim", "s1", {"pnl": NOT_A_NUMBER, "trades": 0}),
        ],
    ),
    case(
        "sim_run_minus_infinity_pnl",
        steps=[
            LOAD,
            ("register", "sim", "s1", "SIM-01", {}),
            ("update", "sim", "s1", {"pnl": MINUS_INFINITY, "trades": 0}),
        ],
    ),
    case(
        "sim_run_unicode_label",
        steps=[
            LOAD,
            ("register", "sim", "s1", UNICODE_TEXT, {"asset": UNICODE_TEXT}),
        ],
    ),
    case(
        "sim_run_long_label",
        steps=[LOAD, ("register", "sim", "s1", LONG_TEXT, {"asset": LONG_TEXT})],
    ),
    case(
        "sim_run_markup_label",
        steps=[LOAD, ("register", "sim", "s1", MARKUP_TEXT, {"asset": MARKUP_TEXT})],
    ),
    case(
        "sim_run_apostrophe_label",
        steps=[
            LOAD,
            ("register", "sim", "s1", APOSTROPHE_TEXT, {"asset": APOSTROPHE_TEXT}),
        ],
    ),
    case(
        "sim_run_newline_label",
        steps=[LOAD, ("register", "sim", "s1", NEWLINE_TEXT, {"asset": NEWLINE_TEXT})],
    ),
    case(
        "sim_run_wrong_capitals",
        steps=[
            LOAD,
            (
                "register",
                "sim",
                "s1",
                WRONG_CAPITALS_TEXT,
                {"mode": WRONG_CAPITALS_TEXT},
            ),
        ],
    ),
    case(
        "sim_run_empty_label",
        steps=[LOAD, ("register", "sim", "s1", "", {"asset": "", "mode": ""})],
    ),
    case(
        "paper_run",
        steps=[
            LOAD,
            ("register", "paper", "p1", "PAP-01", {"pair": "ETH/USD", "capital": 200}),
            ("update", "paper", "p1", {"price": 12.75, "pnl": -3.5, "trades": 2}),
        ],
    ),
    case(
        "paper_run_price_over_a_thousand",
        steps=[
            LOAD,
            ("register", "paper", "p1", "PAP-01", {"pair": "BTC/USD"}),
            ("update", "paper", "p1", {"price": 65432.1, "pnl": 0, "trades": 0}),
        ],
    ),
    case(
        "paper_run_price_exactly_a_thousand",
        steps=[
            LOAD,
            ("register", "paper", "p1", "PAP-01", {"pair": "BTC/USD"}),
            ("update", "paper", "p1", {"price": 1000, "pnl": 0, "trades": 0}),
        ],
    ),
    case(
        "paper_run_not_a_number_price",
        steps=[
            LOAD,
            ("register", "paper", "p1", "PAP-01", {}),
            ("update", "paper", "p1", {"price": NOT_A_NUMBER, "pnl": 0, "trades": 0}),
        ],
    ),
    case(
        "paper_run_infinite_price",
        steps=[
            LOAD,
            ("register", "paper", "p1", "PAP-01", {}),
            ("update", "paper", "p1", {"price": INFINITY, "pnl": 0, "trades": 0}),
        ],
    ),
    case(
        "paper_run_text_price",
        steps=[
            LOAD,
            ("register", "paper", "p1", "PAP-01", {}),
            ("update", "paper", "p1", {"price": "12.7", "pnl": 0, "trades": 0}),
        ],
    ),
    case(
        "paper_run_stopped",
        steps=[
            LOAD,
            ("register", "paper", "p1", "PAP-01", {"pair": "ETH/USD"}),
            ("stop", "paper", "p1", {"pnl": 4.5, "trades": 9}),
        ],
    ),
    case(
        "a_live_row_is_updated_without_one_being_built",
        steps=[
            LOAD,
            (
                "update",
                "live",
                "BTC-USD-0001",
                {"price": 5.25, "pnl": 1.5, "trades": 3, "status": "SCRUM"},
            ),
            ("stop", "live", "BTC-USD-0001", {"pnl": -1.25, "trades": 11}),
        ],
    ),
    case(
        "an_unknown_layer_takes_the_simulator_colours",
        steps=[LOAD, ("register", "sim", "s1", "SIM-01", {"mode": "NUCLEAR"})],
    ),
    case(
        "update_a_run_that_was_never_registered",
        steps=[LOAD, ("update", "sim", "absent", {"pnl": 1, "trades": 1})],
    ),
    case(
        "stop_a_run_that_was_never_registered",
        steps=[LOAD, ("stop", "paper", "absent", {"pnl": 1, "trades": 1})],
    ),
    case(
        "a_wire_arrives_from_outside",
        steps=[
            LOAD,
            ("wire_created", "BTC-USD-0001", "SOL-USD-0003", 15.0),
        ],
    ),
    case(
        "the_same_wire_twice_changes_only_its_rate",
        steps=[
            LOAD,
            ("wire_created", "BTC-USD-0001", "ETH-USD-0002", 70.0),
        ],
    ),
    case(
        "a_wire_with_no_rate_is_refused",
        steps=[LOAD, ("wire_created", "BTC-USD-0001", "SOL-USD-0003", 0)],
    ),
    case(
        "a_wire_with_a_negative_rate_is_refused",
        steps=[LOAD, ("wire_created", "BTC-USD-0001", "SOL-USD-0003", -5)],
    ),
    case(
        "a_wire_with_no_target_is_refused",
        steps=[LOAD, ("wire_created", "BTC-USD-0001", "", 15.0)],
    ),
    case(
        "a_wire_rate_stored_as_text",
        steps=[LOAD, ("wire_created", "BTC-USD-0001", "SOL-USD-0003", "12.7")],
    ),
    case(
        "a_wire_rate_stored_as_words",
        steps=[LOAD, ("wire_created", "BTC-USD-0001", "SOL-USD-0003", "twelve")],
    ),
    case(
        "a_wire_rate_stored_as_true",
        steps=[LOAD, ("wire_created", "BTC-USD-0001", "SOL-USD-0003", True)],
    ),
    case(
        "a_wire_is_cut",
        steps=[LOAD, ("remove_wire", "BTC-USD-0001", "ETH-USD-0002")],
    ),
    case(
        "a_wire_that_is_not_there_is_cut",
        steps=[LOAD, ("remove_wire", "BTC-USD-0001", "GONE-0009")],
    ),
    case(
        "a_wire_is_removed_from_outside",
        steps=[LOAD, ("wire_removed", "BTC-USD-0001", "ETH-USD-0002")],
    ),
    case(
        "a_bot_leaves_the_fleet",
        steps=[LOAD, ("update_bots_partial", ["BTC-USD-0001"])],
    ),
    case(
        "every_bot_leaves_the_fleet",
        steps=[LOAD, ("update_bots_partial", [])],
    ),
    case("the_grid_view_is_chosen", steps=[LOAD, ("view_mode", "grid")]),
    case("the_list_view_is_chosen", steps=[LOAD, ("view_mode", "list")]),
    case("one_exchange_is_filtered", steps=[LOAD, ("exchange", "kraken")]),
    case("every_exchange_is_shown", steps=[LOAD, ("exchange", "")]),
    case(
        "an_exchange_no_bot_trades_on",
        steps=[LOAD, ("exchange", "binance")],
    ),
    case(
        "the_only_bot_on_an_exchange_leaves",
        steps=[
            LOAD,
            ("exchange", "kraken"),
            ("update_bots_partial", ["BTC-USD-0001", "ETH-USD-0002"]),
        ],
    ),
    case("the_mask_is_turned_on", steps=[LOAD, ("mask", True), LOAD]),
    case(
        "the_mask_is_turned_off_again",
        steps=[LOAD, ("mask", True), ("mask", False), LOAD],
    ),
    case("privacy_mode_is_turned_on", steps=[LOAD, ("privacy_mode",), LOAD]),
    case(
        "privacy_mode_is_turned_off_again",
        steps=[LOAD, ("privacy_mode",), ("privacy_mode",), LOAD],
    ),
    case(
        "privacy_mode_follows_the_identifier_mask",
        steps=[LOAD, ("mask", True), ("privacy_mode",), LOAD],
    ),
    case("the_theme_is_changed", steps=[LOAD, ("theme", "nebula")]),
    case("the_glow_moves_one_frame", steps=[LOAD, ("animate", 0.5)]),
    case(
        "the_glow_moves_two_frames", steps=[LOAD, ("animate", 0.25), ("animate", 0.25)]
    ),
]

BY_NAME = {spec["name"]: spec for spec in CASES}


def digest(value) -> str:
    """SHA-256 over one answer, ordered so a swap changes it."""
    return hashlib.sha256(repr(canonical(value)).encode("utf-8")).hexdigest()


def canonical(value):
    """`value` as nested lists of text, ordered so a swap changes it.

    Every leaf becomes its printed form with its type, so a whole number
    and a decimal of the same size are told apart and two not-a-numbers
    read alike.
    """
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: repr(item[0]))
        return [[repr(key), canonical(inner)] for key, inner in pairs]
    if isinstance(value, (list, tuple)):
        return [canonical(inner) for inner in value]
    return f"{type(value).__name__}:{value!r}"


# The shared names both sides borrow, and putting them back


class StandInStateManager:
    """Hands back one stored fleet load, and never touches a real file."""

    state: dict = {}
    loads: list = []

    def load_state(self):
        StandInStateManager.loads.append(1)
        return json.loads(json.dumps(StandInStateManager.state, default=str))


class Seams:
    """Give this drive its own fleet loader, bus, mask register and clock.

    Every swapped name is put back on the way out, including after a
    refusal, so no case can read what another left behind.
    """

    def __init__(self, state: dict, home: Path) -> None:
        self.state = state
        self.home = home
        self.saved: dict = {}
        self.connections: list = []
        self.timers: list = []
        self.rows_sent: list = []
        self.clock = 1000.0

    def __enter__(self) -> "Seams":
        self.saved = {
            "StateManager": sm.StateManager,
            "bus": eb._global_bus,
            "registry": pmr._SINGLETON,
            "connect": SignalInstance.connect,
            "timer_start": QTimer.start,
            "monotonic": time.monotonic,
            "state": StandInStateManager.state,
        }
        StandInStateManager.state = self.state
        sm.StateManager = StandInStateManager
        eb._global_bus = eb.EventBus()
        pmr._SINGLETON = pmr.PrivacyMaskRegistry(
            settings_path=self.home / "settings.json", autosave=False
        )
        record = self
        real_connect = self.saved["connect"]
        real_timer_start = self.saved["timer_start"]

        def watched_connect(signal, *found, **named):
            record.connections.append(str(signal))
            return real_connect(signal, *found, **named)

        def watched_timer_start(timer, *found):
            record.timers.append(tuple(found))
            return real_timer_start(timer, *found)

        setattr(SignalInstance, "connect", watched_connect)
        setattr(QTimer, "start", watched_timer_start)
        setattr(time, "monotonic", lambda: record.clock)
        return self

    def __exit__(self, *_unused) -> None:
        sm.StateManager = self.saved["StateManager"]
        eb._global_bus = self.saved["bus"]
        pmr._SINGLETON = self.saved["registry"]
        setattr(SignalInstance, "connect", self.saved["connect"])
        setattr(QTimer, "start", self.saved["timer_start"])
        setattr(time, "monotonic", self.saved["monotonic"])
        StandInStateManager.state = self.saved["state"]

    def in_place(self) -> bool:
        """Whether the swapped names are the ones this drive installed."""
        return (
            sm.StateManager is StandInStateManager
            and eb._global_bus is not self.saved["bus"]
            and pmr._SINGLETON is not self.saved["registry"]
            and SignalInstance.connect is not self.saved["connect"]
        )

    def restored(self) -> bool:
        """Whether every swapped name now holds what it held before."""
        return (
            sm.StateManager is self.saved["StateManager"]
            and eb._global_bus is self.saved["bus"]
            and pmr._SINGLETON is self.saved["registry"]
            and SignalInstance.connect is self.saved["connect"]
            and QTimer.start is self.saved["timer_start"]
            and time.monotonic is self.saved["monotonic"]
        )


THROWAWAY_HOME_NAME = "bv-parity-home"


def throwaway_home() -> Path:
    """A home directory no drive is allowed to write into."""
    import tempfile

    made = Path(tempfile.mkdtemp(prefix=THROWAWAY_HOME_NAME))
    return made


# The shipped side

ROW_COLUMNS = (
    "dot",
    "id_lbl",
    "context_lbl",
    "mode_lbl",
    "feed_lbl",
    "cap_lbl",
    "status_lbl",
    "metric_lbl",
    "pnl_lbl",
    "trades_lbl",
)

LAYER_STORES = {
    "sim": "_live_sim_rows",
    "paper": "_live_paper_rows",
    "live": "_live_bot_rows",
}


def old_row_state(handle: dict) -> dict:
    """One shipped row read back off its widgets."""
    read = {
        "kind": handle["kind"],
        "accent": handle["_accent"],
        "running": handle["running"],
        "total_candles": handle.get("total_candles"),
        "widget_style_sheet": handle["widget"].styleSheet(),
        "pnl": handle.get("_pnl"),
    }
    for name in ROW_COLUMNS:
        label = handle[name]
        read[name] = [label.text(), label.maximumWidth(), label.styleSheet()]
    return read


def new_row_state(handle: dict) -> dict:
    """One surface row read back off the answer it carries."""
    read = {
        "kind": handle["kind"],
        "accent": handle["_accent"],
        "running": handle["running"],
        "total_candles": handle.get("total_candles"),
        "widget_style_sheet": handle["widget"]["style_sheet"],
        "pnl": handle.get("_pnl"),
    }
    for name in ROW_COLUMNS:
        column = handle[name]
        read[name] = [column["text"], column["width"], column["style_sheet"]]
    return read


def build_tab(seams: Seams):
    """One shipped tab, hydrated from the stored fleet load."""
    tab = shipped.BotVisualizationTab()
    real_set_bots = tab._bot_list.set_bots

    def watched_set_bots(rows):
        seams.rows_sent.append([dict(one) for one in rows])
        return real_set_bots(rows)

    tab._bot_list.set_bots = watched_set_bots
    return tab


def release(tab) -> None:
    """Stop a tab's timer and let it go, so no drive keeps its widgets.

    A tab the session already destroyed raises on every call, so each
    step is taken on its own: releasing must never be the thing that
    fails a run.
    """
    for step in (
        lambda: tab._anim_timer.stop(),
        lambda: tab.setParent(None),
        lambda: tab.deleteLater(),
    ):
        try:
            step()
        except (AttributeError, RuntimeError):
            pass


def apply_old(tab, seams: Seams, step) -> None:
    """Run one step against the shipped tab, through its own paths."""
    kind = step[0]
    if kind == "update_bots":
        tab.update_bots(fleet_statuses(seams.state))
    elif kind == "update_bots_partial":
        kept = set(step[1])
        tab.update_bots(
            [one for one in fleet_statuses(seams.state) if one["bot_id"] in kept]
        )
    elif kind == "register":
        _, layer, run_id, label, cfg = step
        {
            "sim": tab.register_sim_run,
            "paper": tab.register_paper_run,
            "live": tab.register_live_run,
        }[layer](run_id, label, cfg)
    elif kind == "update":
        _, layer, run_id, named = step
        if layer == "sim":
            tab.update_sim_run(
                run_id,
                named.get("pnl", 0.0),
                named.get("trades", 0),
                named.get("candle_idx", 0),
            )
        elif layer == "paper":
            tab.update_paper_run(
                run_id,
                named.get("price", 0.0),
                named.get("pnl", 0.0),
                named.get("trades", 0),
            )
        else:
            tab.update_live_run(
                run_id,
                named.get("price", 0.0),
                named.get("pnl", 0.0),
                named.get("trades", 0),
                named.get("status"),
            )
    elif kind == "stop":
        _, layer, run_id, named = step
        {
            "sim": tab.stop_sim_run,
            "paper": tab.stop_paper_run,
            "live": tab.stop_live_run,
        }[layer](run_id, named.get("pnl", 0.0), named.get("trades", 0))
    elif kind == "wire_created":
        eb._global_bus.emit(
            "wire.created", source_id=step[1], target_id=step[2], pct=step[3]
        )
    elif kind == "wire_removed":
        eb._global_bus.emit("wire.removed", source_id=step[1], target_id=step[2])
    elif kind == "remove_wire":
        tab.remove_wire(step[1], step[2])
    elif kind == "animate":
        seams.clock += step[1]
        tab._animate()
    elif kind == "view_mode":
        tab._view_combo.setCurrentIndex(1 if step[1] == "grid" else 0)
    elif kind == "exchange":
        chosen = 0
        for at in range(tab._exchange_combo.count()):
            if str(tab._exchange_combo.itemData(at) or "") == step[1]:
                chosen = at
        tab._exchange_combo.setCurrentIndex(chosen)
    elif kind == "mask":
        if pmr._SINGLETON.is_masked(MASK_FIELD) != step[1]:
            tab._toggle_bot_swarm_identifier_mask()
    elif kind == "privacy_mode":
        tab._on_privacy_mode_btn_clicked()
    elif kind == "theme":
        for at in range(tab._theme_combo.count()):
            if tab._theme_combo.itemData(at) == step[1]:
                tab._theme_combo.setCurrentIndex(at)


def read_old(tab, seams: Seams) -> dict:
    """Everything one shipped tab carries, read off its widgets."""
    return {
        "wires": [dict(one) for one in tab._wires],
        "bot_ids": list(tab._bot_widgets),
        "grid_cells": old_grid_cells(tab),
        "empty_visible": not tab._empty_label.isHidden(),
        "empty_text": tab._empty_label.text(),
        "exchange_items": [
            [tab._exchange_combo.itemText(at), tab._exchange_combo.itemData(at)]
            for at in range(tab._exchange_combo.count())
        ],
        "exchange": str(tab._exchange_combo.currentData() or ""),
        "visible_bots": {
            bot_id: not widget.isHidden() for bot_id, widget in tab._bot_widgets.items()
        },
        "ids_in_scope": tab._all_bot_ids_in_scope(),
        "exchanges": {
            bot_id: tab._bot_exchange_id(bot_id) for bot_id in tab._bot_widgets
        },
        "privacy_glyph": tab._bot_swarm_privacy_dot.text(),
        "privacy_mode_text": tab._privacy_mode_btn.text(),
        "privacy_mode_style_sheet": tab._privacy_mode_btn.styleSheet(),
        "view_mode": tab._view_mode,
        "view_index": tab._view_stack.currentIndex(),
        "canvas_visible": not tab._wire_canvas.isHidden(),
        "theme_key": tab._theme_key,
        "rows_sent": [list(one) for one in seams.rows_sent],
        "sim_summary": {
            "wins": tab._sim_swarm_wins.text(),
            "pnl": tab._sim_swarm_pnl.text(),
            "trades": tab._sim_swarm_trades.text(),
        },
        "paper_summary": {
            "active": tab._paper_swarm_active.text(),
            "total": tab._paper_swarm_total.text(),
            "pnl": tab._paper_swarm_pnl.text(),
        },
        "rows": {
            layer: {
                run_id: old_row_state(handle)
                for run_id, handle in getattr(tab, store).items()
            }
            for layer, store in LAYER_STORES.items()
        },
    }


def old_grid_cells(tab) -> list:
    """Where each locust sits in the shipped grid."""
    found = []
    for bot_id, widget in tab._bot_widgets.items():
        at = tab._grid_layout.indexOf(widget)
        if at < 0:
            found.append([bot_id, -1, -1])
            continue
        row, col, _rows, _cols = tab._grid_layout.getItemPosition(at)
        found.append([bot_id, row, col])
    return found


def drive_old(spec) -> dict:
    """Run one case on the shipped tab and read back what it carries."""
    home = throwaway_home()
    with Seams(spec["state"], home) as seams:
        tab = build_tab(seams)
        try:
            assert seams.in_place(), "the drive lost its own bus or fleet loader"
            for step in spec["steps"]:
                apply_old(tab, seams, step)
            return read_old(tab, seams)
        finally:
            release(tab)


# The Qt-free side


def apply_new(model, spec, step) -> None:
    """Run one step against the surface model."""
    kind = step[0]
    if kind == "update_bots":
        model.update_bots(fleet_statuses(spec["state"]))
    elif kind == "update_bots_partial":
        kept = set(step[1])
        model.update_bots(
            [one for one in fleet_statuses(spec["state"]) if one["bot_id"] in kept]
        )
    elif kind == "register":
        _, layer, run_id, label, cfg = step
        model.layer(layer).register(run_id, label, cfg)
    elif kind == "update":
        _, layer, run_id, named = step
        model.layer(layer).update(
            run_id,
            pnl=named.get("pnl", 0.0),
            trades=named.get("trades", 0),
            candle_idx=named.get("candle_idx", 0),
            price=named.get("price", 0.0) if layer != "sim" else None,
            status=named.get("status"),
        )
    elif kind == "stop":
        _, layer, run_id, named = step
        model.layer(layer).stop(
            run_id, pnl=named.get("pnl", 0.0), trades=named.get("trades", 0)
        )
    elif kind == "wire_created":
        model.board.on_created(
            {"source_id": step[1], "target_id": step[2], "pct": step[3]}
        )
    elif kind == "wire_removed":
        model.board.on_removed({"source_id": step[1], "target_id": step[2]})
    elif kind == "remove_wire":
        model.board.remove(step[1], step[2])
    elif kind == "animate":
        model.board.advance(step[1])
    elif kind == "view_mode":
        model.view_mode = step[1]
    elif kind == "exchange":
        model.set_exchange(step[1])
    elif kind == "mask":
        model.toggle_identifier_mask(step[1])
    elif kind == "privacy_mode":
        model.toggle_privacy_mode()
    elif kind == "theme":
        model.grid.set_theme(step[1])


def read_new(model) -> dict:
    """Everything one surface model carries, read off its answer."""
    payload = surface.build_payload(model)
    return {
        "wires": [dict(one) for one in payload["wires"]],
        "bot_ids": list(payload["bot_ids"]),
        "grid_cells": [list(one) for one in payload["grid_cells"]],
        "empty_visible": payload["empty_visible"],
        "empty_text": payload["empty_text"],
        "exchange_items": [list(one) for one in payload["exchange_items"]],
        "exchange": payload["exchange"],
        "visible_bots": dict(payload["visible_bots"]),
        "ids_in_scope": list(payload["ids_in_scope"]),
        "exchanges": dict(payload["exchanges"]),
        "privacy_glyph": payload["privacy_glyph"],
        "privacy_mode_text": payload["privacy_mode_text"],
        "privacy_mode_style_sheet": payload["privacy_mode_style_sheet"],
        "view_mode": payload["view_mode"],
        "view_index": payload["view_index"],
        "canvas_visible": payload["canvas_visible"],
        "theme_key": payload["theme_key"],
        "rows_sent": [list(one) for one in payload["rows_sent"]],
        "sim_summary": dict(payload["sim_summary"]),
        "paper_summary": dict(payload["paper_summary"]),
        "rows": {
            layer: {
                run_id: new_row_state(handle)
                for run_id, handle in payload[f"{layer}_rows"].items()
            }
            for layer in LAYER_STORES
        },
    }


def drive_new(spec) -> dict:
    """Run one case on the surface and read back what it carries."""
    model = surface.BotVisualizerModel()
    model.hydrate(spec["state"])
    for step in spec["steps"]:
        apply_new(model, spec, step)
    return read_new(model)


def outcome(drive, spec):
    """One drive's answer, or the type of the refusal it raised."""
    try:
        return ("built", drive(spec))
    except Exception as exc:
        return ("refused", type(exc).__name__)


# Both sides, value for value and by hash


@pytest.mark.parametrize("name", [spec["name"] for spec in CASES])
def test_the_two_sides_describe_the_same_screen(name):
    """The surface carries a different value than the shipped tab."""
    spec = BY_NAME[name]
    old_kind, old = outcome(drive_old, spec)
    new_kind, new = outcome(drive_new, spec)
    assert (new_kind, new) == (
        old_kind,
        old,
    ), f"{name}: surface {new_kind} {new!r} against shipped {old_kind} {old!r}"


@pytest.mark.parametrize("name", [spec["name"] for spec in CASES])
def test_the_two_sides_hash_alike(name):
    """A value the two sides disagree on reaches no comparison."""
    spec = BY_NAME[name]
    old_kind, old = outcome(drive_old, spec)
    new_kind, new = outcome(drive_new, spec)
    assert old_kind == new_kind, (old_kind, new_kind)
    assert digest(new) == digest(old), f"{name}: {new!r} against {old!r}"


LIVE_CFGS = [
    ("pair_and_capital", {"pair": "BTC/USD", "capital": 800}),
    ("asset_instead_of_pair", {"asset": "BTC", "source": "coinbase"}),
    ("nothing_given", {}),
    ("its_own_metric", {"metric_init": "42%", "mode": "SCRUM"}),
]


@pytest.mark.parametrize("name", [one[0] for one in LIVE_CFGS])
def test_the_two_sides_build_the_same_live_row(name, row_factory):
    """The surface builds a different live row than the shipped tab.

    The live row is compared through the row factory, not through
    ``register_live_run``: that method cannot run at all, which the
    next test pins.
    """
    cfg = dict(LIVE_CFGS)[name]
    old = old_row_state(row_factory("live", "BTC-USD-0001", shipped_live_cfg(cfg)))
    new = new_row_state(
        surface.swarm_row("live", "BTC-USD-0001", surface.live_cfg(cfg))
    )
    assert new == old, f"{name}: surface {new!r}, shipped {old!r}"


def shipped_live_cfg(cfg: dict) -> dict:
    """The settings ``register_live_run`` hands the row factory.

    Copied from the shipped method because the method itself stops
    before it reaches the factory.
    """
    return {
        "context": cfg.get("pair", cfg.get("asset", "—")),
        "mode": cfg.get("mode", "LIVE"),
        "feed": cfg.get("timeframe", cfg.get("source", "—")),
        "capital": cfg.get("capital", 0),
        "status": "RUNNING",
        "metric_init": cfg.get("metric_init", "—"),
    }


def test_registering_a_live_bot_row_stops_on_a_name_the_tab_never_sets():
    """``register_live_run`` builds a row, so the live layer works.

    Measured on the shipped file: ``_live_rows_empty`` is read behind a
    ``hasattr`` guard and its twin ``_live_rows_layout`` is read bare on
    the next line, and nothing in the file ever sets it. Every call
    stops there, after the row was built and before it was stored, so
    the Bot Swarm tab shows no live row at all.
    """
    assert "_live_rows_layout" not in {
        node.attr
        for node in ast.walk(parsed(SHIPPED_SOURCE))
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
    }, "the shipped file now sets _live_rows_layout, so this pin is stale"
    home = throwaway_home()
    with Seams(STORED_FLEET, home) as seams:
        tab = build_tab(seams)
        try:
            with pytest.raises(AttributeError) as raised:
                tab.register_live_run("BTC-USD-0001", "BTC-USD-0001", {})
            assert "_live_rows_layout" in str(raised.value), str(raised.value)
            assert tab._live_bot_rows == {}, tab._live_bot_rows
        finally:
            release(tab)


def test_the_missing_name_reader_reports_a_name_a_file_does_set():
    """The reader reports missing whatever a file assigns."""
    stored = {
        node.attr
        for node in ast.walk(parsed("self._live_rows_layout = 1\n"))
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
    }
    assert "_live_rows_layout" in stored


REFUSING_CASES = [
    "sim_run_text_where_a_number_belongs",
    "sim_run_not_a_number_progress",
    "sim_run_infinite_progress",
    "paper_run_text_price",
]


@pytest.mark.parametrize("name", REFUSING_CASES)
def test_a_refused_input_names_the_same_error_on_both_sides(name):
    """A refusal that names a different fault on the two sides."""
    spec = BY_NAME[name]
    old_kind, old = outcome(drive_old, spec)
    new_kind, new = outcome(drive_new, spec)
    assert (old_kind, old) == (new_kind, new), (old_kind, old, new_kind, new)


def test_at_least_one_driven_case_refuses_on_both_sides():
    """Every case builds, so the refusal comparison reports nothing."""
    refused = [
        name
        for name in REFUSING_CASES
        if outcome(drive_old, BY_NAME[name])[0] == "refused"
    ]
    assert refused, "no case refuses, so the refusal comparison cannot report"


def test_two_different_real_inputs_are_told_apart_in_both_directions():
    """The comparison passes whatever the surface answers."""
    first = BY_NAME["happy"]
    second = BY_NAME["one_bot"]
    assert digest(drive_old(first)) != digest(drive_new(second))
    assert digest(drive_old(second)) != digest(drive_new(first))


def test_the_same_input_twice_describes_one_screen():
    """One case read twice describes two different screens.

    Each side is driven and recorded on its own, so the comparison is
    between two separate runs and not one expression against itself.
    """
    spec = BY_NAME["happy"]
    first_new = digest(drive_new(spec))
    second_new = digest(drive_new(spec))
    first_old = digest(drive_old(spec))
    second_old = digest(drive_old(spec))
    assert second_new == first_new
    assert second_old == first_old


def test_a_whole_number_and_a_decimal_are_told_apart_by_the_hash():
    """A whole number and a decimal of one size read alike."""
    whole = {"pct": 12}
    decimal = {"pct": 12.0}
    equal_whole = {"pct": 12}
    assert digest(whole) != digest(decimal)
    assert digest(equal_whole) == digest(whole)


def test_two_not_a_numbers_hash_alike_and_apart_from_an_infinity():
    """Two not-a-numbers read as a difference that is not one."""
    one_nan = {"v": float("nan")}
    other_nan = {"v": float("nan")}
    endless = {"v": INFINITY}
    assert digest(other_nan) == digest(one_nan)
    assert digest(one_nan) != digest(endless)
    assert float("nan") != float("nan")


def test_a_stored_true_where_a_number_belongs_prints_as_one_dollar():
    """A stored True reaches the capital column as something other than $1."""
    spec = BY_NAME["sim_run_stored_true_where_a_number_belongs"]
    old = drive_old(spec)
    assert old["rows"]["sim"]["s1"]["cap_lbl"][0] == "$1", old["rows"]["sim"]["s1"]
    assert digest(drive_new(spec)) == digest(old)


def test_the_sample_hashes_are_reported():
    """The hash of every case, so a change is visible in the failure."""
    found = {}
    for spec in CASES:
        kind, answer = outcome(drive_old, spec)
        found[spec["name"]] = answer if kind == "refused" else digest(answer)
    assert len(found) == len(CASES), found
    assert len(set(found.values())) > 1, found


# Step sequences

SEQUENCE = ("happy", "sim_run", "paper_run", "one_bot", "a_wire_is_cut")
REFUSING_SEQUENCE = ("happy", "sim_run", "paper_run_text_price", "one_bot")


def drive_sequence(drive, names) -> dict:
    """Run each named case in turn, stopping at the first refusal."""
    kept: list = []
    for at, name in enumerate(names):
        try:
            kept.append(digest(drive(BY_NAME[name])))
        except Exception as exc:
            return {
                "kept": kept,
                "stopped_at": at,
                "step_name": name,
                "refusal": type(exc).__name__,
            }
    return {"kept": kept, "stopped_at": None, "step_name": None, "refusal": None}


def test_a_step_sequence_takes_the_same_path_on_both_sides():
    """A sequence of drives reaches a different place on the two sides."""
    old = drive_sequence(drive_old, SEQUENCE)
    new = drive_sequence(drive_new, SEQUENCE)
    assert old["stopped_at"] is None, old
    assert len(old["kept"]) == len(SEQUENCE), old
    assert new == old, f"surface {new!r}, shipped {old!r}"


def test_a_sequence_that_refuses_part_way_keeps_what_it_recorded():
    """A refusal part way through loses the steps that already ran."""
    old = drive_sequence(drive_old, REFUSING_SEQUENCE)
    new = drive_sequence(drive_new, REFUSING_SEQUENCE)
    assert old["stopped_at"] == 2, old
    assert old["step_name"] == "paper_run_text_price", old
    assert old["refusal"] == "TypeError", old
    assert len(old["kept"]) == 2, old
    assert new == old, f"surface {new!r}, shipped {old!r}"


def test_the_sequence_recorder_reports_a_sequence_that_finishes():
    """The recorder reports a refusal whatever a sequence does."""
    finished = drive_sequence(drive_new, SEQUENCE)
    assert finished["refusal"] is None, finished
    assert finished["stopped_at"] is None, finished


# Enumerating the shipped file


def parsed(source: str):
    return ast.parse(source)


def declared_classes(source: str) -> dict:
    """Every class the file declares, with the bases it names."""
    return {
        node.name: [ast.unparse(base) for base in node.bases]
        for node in ast.walk(parsed(source))
        if isinstance(node, ast.ClassDef)
    }


def declared_functions(source: str) -> list:
    """Every function and method the file declares, sorted."""
    return sorted(
        node.name
        for node in ast.walk(parsed(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def import_aliases(source: str) -> dict:
    """Every imported name mapped to the name the file calls it by."""
    found: dict = {}
    for node in ast.walk(parsed(source)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                found[alias.asname or alias.name] = alias.name
    return found


def constructor_calls(source: str) -> list:
    """Every call by a plain name, resolved through its import alias."""
    aliases = import_aliases(source)
    return sorted(
        aliases.get(node.func.id, node.func.id)
        for node in ast.walk(parsed(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    )


def function_calls(source: str, name: str) -> list:
    """Every line calling one function by name, alias resolved.

    A call written through an alias counts, so renaming the import at
    the top does not hide it.
    """
    aliases = import_aliases(source)
    found = []
    for node in ast.walk(parsed(source)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == name:
            found.append(node.lineno)
        elif isinstance(node.func, ast.Name) and aliases.get(node.func.id) == name:
            found.append(node.lineno)
    return sorted(found)


def bus_topics(source: str, method: str) -> list:
    """The topic every call to one bus method names, alias resolved."""
    aliases = import_aliases(source)
    found = []
    for node in ast.walk(parsed(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        named = None
        if isinstance(node.func, ast.Attribute):
            named = node.func.attr
        elif isinstance(node.func, ast.Name):
            named = aliases.get(node.func.id)
        if named != method:
            continue
        first = node.args[0]
        found.append(first.value if isinstance(first, ast.Constant) else "?")
    return sorted(found)


def test_the_shipped_file_declares_one_class_and_seventy_four_functions():
    """A class or a method was added to the shipped file and not carried."""
    assert declared_classes(SHIPPED_SOURCE) == {
        "BotVisualizationTab": ["QWidget"]
    }, declared_classes(SHIPPED_SOURCE)
    found = declared_functions(SHIPPED_SOURCE)
    assert len(found) == 74, len(found)
    assert found.count("_remove") == 2, found
    for name in ("update_bots", "remove_wire", "register_sim_run", "_get_wire_offset"):
        assert name in found, name


def test_the_class_counter_finds_a_class_it_is_shown():
    """The class counter reports nothing whatever a file declares."""
    assert declared_classes("class Inner(Base):\n    pass\n") == {"Inner": ["Base"]}


def test_the_function_counter_finds_a_method_inside_a_class():
    """The function counter reads module level only."""
    assert declared_functions("class A:\n    def b(self):\n        pass\n") == ["b"]


def test_the_shipped_file_subscribes_to_two_topics_and_emits_seven_times():
    """A bus topic was added to the shipped file and not carried."""
    subscribed = bus_topics(SHIPPED_SOURCE, "subscribe")
    emitted = function_calls(SHIPPED_SOURCE, "emit")
    assert subscribed == ["wire.created", "wire.removed"], subscribed
    assert len(emitted) == 7, emitted
    aliased = [
        node.lineno
        for node in ast.walk(parsed(SHIPPED_SOURCE))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and import_aliases(SHIPPED_SOURCE).get(node.func.id) == "emit"
    ]
    assert len(aliased) == 2, aliased
    assert SHIPPED_SOURCE.count(".emit(") == 5
    assert sorted(surface.BUS_TOPICS) == subscribed


def test_the_emit_reader_counts_a_call_written_through_an_alias():
    """The emit reader misses a call an alias renames."""
    aliased = "from x import emit as e\ne('a.b')\nbus.emit('c.d')\n"
    assert function_calls(aliased, "emit") == [2, 3]
    assert aliased.count(".emit(") == 1


def test_the_emit_reader_ignores_a_call_written_in_a_comment():
    """A call inside prose inflates a text count."""
    prose = "# bus.emit('a.b')\nbus.emit('c.d')\n"
    assert function_calls(prose, "emit") == [2]
    assert prose.count(".emit(") == 2


def test_the_constructor_counter_resolves_an_import_alias():
    """An aliased import reads as a name the counter never counts."""
    assert constructor_calls("from x import Widget as W\nW()\nW()\n") == [
        "Widget",
        "Widget",
    ]


def test_the_shipped_file_builds_one_timer_and_no_thread():
    """A timer or a thread was added to the shipped file."""
    built = constructor_calls(SHIPPED_SOURCE)
    assert built.count("QTimer") == 1, built
    assert built.count("Thread") == 0, built
    assert surface.THREADS == ()
    assert surface.TIMERS == {"animation": 33}
    assert surface.TIMER_DELAYS_MS == (33,)


def test_the_constructor_set_reports_a_thread_a_file_builds():
    """The constructor counter reports nothing whatever a file builds."""
    assert constructor_calls("from threading import Thread\nThread()\n") == ["Thread"]


def test_the_running_widget_wires_seventeen_connections():
    """Building the tab wires a different number of signals than before.

    The counter watches every connection made in Python while the tab is
    built, which is this file's own wiring plus the wiring the widgets
    it builds do for themselves. It is scoped to that: a bare widget
    reads zero, proved below.
    """
    home = throwaway_home()
    with Seams(STORED_FLEET, home) as seams:
        tab = build_tab(seams)
        try:
            assert len(seams.connections) == 17, len(seams.connections)
            assert seams.timers == [(33,)], seams.timers
        finally:
            release(tab)
    assert seams.restored() is True


def test_the_connection_counter_reads_zero_on_a_bare_widget():
    """The connection counter counts the framework's own wiring."""
    home = throwaway_home()
    with Seams(STORED_FLEET, home) as seams:
        bare = QWidget()
        assert len(seams.connections) == 0, seams.connections
        from PySide6.QtWidgets import QPushButton

        QPushButton("x", bare).clicked.connect(lambda: None)
        assert len(seams.connections) == 1, seams.connections
        bare.setParent(None)
        bare.deleteLater()
    assert seams.restored() is True


def test_the_shipped_file_names_twenty_connect_sites():
    """A source count reported as a measurement, never as the contract.

    Seventeen of these run while the tab is built. The rest sit in the
    bench-row builders and the wire dialog, which run only when the
    operator adds a row or sets a rate.
    """
    assert len(function_calls(SHIPPED_SOURCE, "connect")) == 20


# The comparison is complete


def leaves(value) -> set:
    """Every leaf inside one value, as the text a comparison reads."""
    found: set = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            found.add(repr(key))
            found |= leaves(inner)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for inner in value:
            found |= leaves(inner)
    else:
        found.add(repr(value))
    return found


def values_of(payload) -> set:
    """Every value inside one answer, with the answer own keys left out."""
    found: set = set()
    if isinstance(payload, dict):
        for inner in payload.values():
            found |= values_of(inner)
    elif isinstance(payload, (list, tuple, set, frozenset)):
        for inner in payload:
            found |= values_of(inner)
    else:
        found.add(repr(payload))
    return found


def surface_constants() -> dict:
    """Every value the surface declares at module level."""
    return {
        name: getattr(surface, name)
        for name in dir(surface)
        if name.isupper() and not name.startswith("_")
    }


def snapshot() -> dict:
    """One answer wide enough to carry every value the surface exports."""
    model = surface.BotVisualizerModel()
    model.hydrate(STORED_FLEET)
    model.update_bots(fleet_statuses(STORED_FLEET))
    for kind, run_id, label in (
        ("sim", "s1", "SIM-01"),
        ("paper", "p1", "PAP-01"),
        ("live", "BTC-USD-0001", "BTC-USD-0001"),
    ):
        model.layer(kind).register(run_id, label, {"capital": 400})
        model.layer(kind).stop(run_id, pnl=1.0, trades=1)
    model.board.start_drag("BTC-USD-0001", (1.0, 2.0))
    model.board.finish_drag("")
    return surface.build_payload(model)


NOT_IN_THE_ANSWER = {
    "SWARM_ACCENTS",
    "SWARM_TINTS",
    "COLORS",
    "LAYER_CFG_BUILDERS",
    "REGISTERED_SIGNALS",
    "HIT_SAMPLES",
    "ROW_HANDLE_KEYS",
    "LAYER_OF_ACTION",
    "SIM_SUMMARY_START",
    "PAPER_SUMMARY_START",
    "PANE_MODEL",
}


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A constant the comparison never reads passes whatever it holds."""
    carried = leaves(snapshot())
    missing = sorted(
        name
        for name, value in surface_constants().items()
        if name not in NOT_IN_THE_ANSWER and not leaves(value) <= carried
    )
    assert missing == [], missing


def test_the_names_left_out_of_the_completeness_check_are_still_carried():
    """A constant excused from the check reaches the answer nowhere.

    Each of these is a lookup whose keys are the answer's own key names,
    so only its VALUES reach the payload. Every value is checked here.
    """
    carried = leaves(snapshot())
    for name in sorted(NOT_IN_THE_ANSWER - {"LAYER_CFG_BUILDERS", "PANE_MODEL"}):
        value = getattr(surface, name)
        inner = list(value.values()) if isinstance(value, dict) else list(value)
        for one in inner:
            assert leaves(one) <= carried, (name, one)


# A tuple, not a set: `True` equals `1`, so a set would keep only one of them.
DRIVEN_INTO_THE_SNAPSHOT = (
    "BTC-USD-0001",
    "ETH-USD-0002",
    "SOL-USD-0003",
    "GONE-0009",
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "coinbase",
    "kraken",
    "SIM-01",
    "PAP-01",
    "s1",
    "p1",
    "$400",
    "PnL +1.00",
    "1 trades",
    "Bots: 0/1 running",
    "Total PnL: $+1.00",
    "Active: 0/0",
    "Total Capital: $0",
    25.0,
    40.0,
    120.5,
    340.25,
    12.0,
    9.75,
    1.0,
    0.0,
    2,
    3,
    4,
    True,
    False,
    "Total PnL: $+0.00",
    surface.row_style_sheet(surface.VIZ_PANEL_SURFACE_COLOR, surface.SUCCESS_COLOR),
    surface.stopped_row_style_sheet(),
    surface.stopped_status_style_sheet(),
    surface.dot_style_sheet(surface.SUCCESS_COLOR),
    surface.dot_style_sheet(surface.ACCENT_GOLD_COLOR),
    surface.dot_style_sheet(surface.VIZ_CAPTION_COLOR),
    surface.id_style_sheet(surface.SUCCESS_COLOR),
    surface.id_style_sheet(surface.PRIMARY_BRIGHT_COLOR),
    surface.id_style_sheet(surface.ACCENT_GOLD_COLOR),
    surface.context_style_sheet(),
    surface.bold_small_style_sheet(surface.SUCCESS_COLOR),
    surface.bold_small_style_sheet(surface.PRIMARY_BRIGHT_COLOR),
    surface.bold_small_style_sheet(surface.ACCENT_GOLD_COLOR),
    surface.small_style_sheet(surface.SUCCESS_COLOR),
    surface.small_style_sheet(surface.CARD_METRIC_LABEL_COLOR),
    surface.small_style_sheet(surface.VIZ_CAPTION_COLOR),
    surface.small_style_sheet(surface.VIZ_CAPTION_DIM_COLOR),
)


def test_every_value_in_the_snapshot_is_backed_by_a_declared_one():
    """A value in the answer is backed by nothing the surface declares.

    ``locust_cards`` is read by ``test_each_locust_card_is_the_node_answer``.
    """
    declared: set = set()
    for value in surface_constants().values():
        declared |= leaves(value)
    declared |= {repr(one) for one in DRIVEN_INTO_THE_SNAPSHOT}
    whole = snapshot()
    assert whole.pop("locust_cards"), "the snapshot carried no locust card"
    unbacked = sorted(values_of(whole) - declared)
    assert unbacked == [], unbacked


def test_each_locust_card_is_the_node_answer():
    """``locust_cards`` holds what ``bot_node_surface`` answers for each bot."""
    from src.gui.main_tabs import bot_node_surface

    model = surface.BotVisualizerModel()
    model.update_bots(fleet_statuses(STORED_FLEET))
    cards = surface.locust_cards(model)
    assert set(cards) == set(model.grid.bot_data), sorted(cards)
    hide = bot_node_surface.masking(())
    for bot_id, data in model.grid.bot_data.items():
        answered = bot_node_surface.build_view_model(
            bot_node_surface.BotNodeModel(
                theme_key=model.grid.theme_key, bot_data=data
            ),
            mask=hide,
        )
        assert cards[bot_id] == answered, bot_id


def test_a_masked_locust_card_hides_the_bot_identifier():
    """A masked model asks ``bot_node_surface`` to hide the same field."""
    model = surface.BotVisualizerModel()
    model.update_bots(fleet_statuses(STORED_FLEET))
    plain = surface.locust_cards(model)
    model.toggle_identifier_mask(True)
    masked = surface.locust_cards(model)
    assert plain != masked, "the mask changed no locust card"


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check reports nothing whatever the answer drops."""
    carried = leaves({"row": {"width": 88}})
    assert not leaves({"width": 89}) <= carried
    assert leaves({"width": 88}) <= carried


def test_the_driven_value_list_keeps_a_boolean_beside_its_number():
    """A boolean and the number equal to it share one place in the list.

    `True` equals `1` and `False` equals `0`, so a set would keep one of
    each pair and the other would read as never driven.
    """
    printed = [repr(one) for one in DRIVEN_INTO_THE_SNAPSHOT]
    assert "True" in printed and "1.0" in printed, printed
    assert "False" in printed and "0.0" in printed, printed
    assert len({True, 1.0}) == 1


def test_the_unbacked_value_check_can_report_an_invented_value():
    """The unbacked-value check reports nothing whatever an answer invents."""
    declared = values_of({"a": 1})
    assert sorted(values_of({"a": 1, "b": 2}) - declared) == ["2"]
    assert sorted(values_of({"a": 1}) - declared) == []


def test_the_leaf_reader_walks_into_a_container():
    """The leaf reader compares a container as text, so a value inside it
    reads as missing whatever it holds."""
    assert leaves({"skin": {"radius": 4}}) == {"'skin'", "'radius'", "4"}
    assert values_of({"radius": 4}) == {"4"}


def test_the_surface_grew_no_name_the_file_does_not_declare():
    """A name reached the module without being written in the file."""
    written = {
        node.targets[0].id
        for node in parsed(SURFACE_SOURCE).body
        if isinstance(node, ast.Assign)
        and node.targets
        and isinstance(node.targets[0], ast.Name)
    }
    written |= {
        node.target.id
        for node in parsed(SURFACE_SOURCE).body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    imported = set(surface_constants())
    assert imported - written == set(), sorted(imported - written)
    assert {name for name in written if name.isupper()} - imported == set()


# The geometry and the words, read off both sides

CENTERS = {
    "a": (100.0, 100.0),
    "b": (300.0, 100.0),
    "c": (100.0, 300.0),
}


def old_offset(tab, wire) -> float:
    """The shipped offset for one wire, with the centres stood in for."""
    real = tab._get_bot_center
    tab._get_bot_center = lambda bot_id: _as_point(CENTERS.get(bot_id))
    try:
        return tab._get_wire_offset(wire)
    finally:
        tab._get_bot_center = real


def _as_point(found):
    """One centre as the shipped code expects it, or nothing."""
    if found is None:
        return None
    from PySide6.QtCore import QPointF

    return QPointF(found[0], found[1])


WIRE_SETS = [
    ("one_way", [("a", "b", 20.0)]),
    ("both_ways_left_to_right", [("a", "b", 20.0), ("b", "a", 30.0)]),
    ("both_ways_same_column", [("a", "c", 20.0), ("c", "a", 30.0)]),
    ("an_end_that_is_not_there", [("a", "gone", 20.0)]),
]


@pytest.mark.parametrize("name", [one[0] for one in WIRE_SETS])
def test_the_two_sides_place_a_wire_at_the_same_offset(name):
    """The surface moves a wire off the line by a different distance."""
    pairs = dict(WIRE_SETS)[name]
    home = throwaway_home()
    with Seams(STORED_FLEET_EMPTY, home) as seams:
        tab = build_tab(seams)
        try:
            tab._wires = [
                {"source_id": s, "target_id": t, "pct": p, "phase": 0.0}
                for s, t, p in pairs
            ]
            old = [old_offset(tab, wire) for wire in tab._wires]
        finally:
            release(tab)
    board = surface.WireBoard()
    for source, target, pct in pairs:
        board.on_created({"source_id": source, "target_id": target, "pct": pct})
    new = [board.offset(wire, CENTERS) for wire in board.wires]
    assert new == old, f"{name}: surface {new}, shipped {old}"


HIT_POINTS = [
    ("on_the_line", (200.0, 100.0)),
    ("just_off_the_line", (200.0, 111.0)),
    ("too_far_from_the_line", (200.0, 140.0)),
    ("at_the_source", (100.0, 100.0)),
    ("at_the_target", (300.0, 100.0)),
]


@pytest.mark.parametrize("name", [one[0] for one in HIT_POINTS])
def test_the_two_sides_agree_which_wire_a_click_landed_on(name):
    """The surface picks a different wire for a click than the tab."""
    pos = dict(HIT_POINTS)[name]
    pairs = [("a", "b", 20.0), ("a", "c", 30.0)]
    home = throwaway_home()
    with Seams(STORED_FLEET_EMPTY, home) as seams:
        tab = build_tab(seams)
        try:
            tab._wires = [
                {"source_id": s, "target_id": t, "pct": p, "phase": 0.0}
                for s, t, p in pairs
            ]
            real = tab._get_bot_center
            tab._get_bot_center = lambda bot_id: _as_point(CENTERS.get(bot_id))
            try:
                from PySide6.QtCore import QPointF

                found = tab._wire_at_pos(QPointF(pos[0], pos[1]))
            finally:
                tab._get_bot_center = real
            old = None if found is None else dict(found)
        finally:
            release(tab)
    board = surface.WireBoard()
    for source, target, pct in pairs:
        board.on_created({"source_id": source, "target_id": target, "pct": pct})
    picked = board.wire_at(pos, CENTERS)
    new = None if picked is None else dict(picked)
    assert new == old, f"{name}: surface {new}, shipped {old}"


def test_a_number_where_a_row_label_belongs_stops_the_shipped_row(row_factory):
    """A number given as a row label builds a row on the shipped side.

    The refusal is the framework's: its label takes text only. The view
    model carries the number through, so a frontend building the row
    decides what to print. This is the one place the two sides differ
    on purpose, and the difference is stated here rather than compared.
    """
    with pytest.raises(TypeError):
        row_factory("sim", 12, {"context": 7})
    carried = surface.swarm_row("sim", 12, {"context": 7})
    assert carried["id_lbl"]["text"] == 12
    assert carried["context_lbl"]["text"] == 7


def test_the_view_selector_offers_two_names_and_nothing_else():
    """A third view name reached the selector, so a name can be unknown."""
    home = throwaway_home()
    with Seams(STORED_FLEET, home) as seams:
        tab = build_tab(seams)
        try:
            offered = [
                tab._view_combo.itemData(at) for at in range(tab._view_combo.count())
            ]
        finally:
            release(tab)
    assert offered == list(surface.VIEW_MODES), offered
    assert surface.view_index("sideways") == surface.VIEW_LIST_INDEX
    assert surface.canvas_visible("sideways") is False


def test_the_click_reader_finds_a_wire_and_misses_a_far_one():
    """The click reader answers the same whatever the click was."""
    board = surface.WireBoard()
    board.on_created({"source_id": "a", "target_id": "b", "pct": 20.0})
    assert board.wire_at((200.0, 100.0), CENTERS) is not None
    assert board.wire_at((200.0, 400.0), CENTERS) is None


CONFIRM_CASES = [
    ("one_wire_with_a_rate", [("BTC-USD-0001", "ETH-USD-0002")], "why it happened"),
    ("one_wire_with_no_rate", [("nobody", "nowhere")], ""),
    (
        "two_wires",
        [("BTC-USD-0001", "ETH-USD-0002"), ("SOL-USD-0003", "GONE-0009")],
        "",
    ),
]


@pytest.mark.parametrize("name", [one[0] for one in CONFIRM_CASES])
def test_the_two_sides_write_the_same_disconnect_question(name, monkeypatch):
    """The confirmation asks a different question on the two sides."""
    pairs, why = {one[0]: (one[1], one[2]) for one in CONFIRM_CASES}[name]
    home = throwaway_home()
    asked: list = []
    with Seams(STORED_FLEET, home) as seams:
        tab = build_tab(seams)
        try:
            from PySide6.QtWidgets import QMessageBox

            def watched(_owner, title, body, *_found):
                asked.append([title, body])
                return QMessageBox.No

            monkeypatch.setattr(QMessageBox, "question", staticmethod(watched))
            tab._confirm_wire_removal(pairs, why)
        finally:
            release(tab)
    board = surface.WireBoard()
    board.on_created(
        {"source_id": "BTC-USD-0001", "target_id": "ETH-USD-0002", "pct": 25.0}
    )
    board.on_created(
        {"source_id": "SOL-USD-0003", "target_id": "GONE-0009", "pct": 40.0}
    )
    new = surface.confirm_body(
        [list(one) for one in pairs],
        [board.pct_of(source, target) for source, target in pairs],
        why,
    )
    assert asked, "the shipped tab asked nothing, so nothing was compared"
    assert [surface.CONFIRM_TITLE, new] == asked[0], (new, asked[0])


def test_an_empty_pair_list_refuses_on_both_sides():
    """An empty list of wires is confirmed rather than refused."""
    home = throwaway_home()
    with Seams(STORED_FLEET, home) as seams:
        tab = build_tab(seams)
        try:
            assert tab._confirm_wire_removal([], "") is False
        finally:
            release(tab)


# The routes a stored fleet load holds

ROUTE_CASES = [
    ("add_one", [("BTC-USD-0001", "SOL-USD-0003", 15.0)], []),
    ("replace_a_rate", [("BTC-USD-0001", "ETH-USD-0002", 90.0)], []),
    ("add_to_a_bot_not_in_the_load", [("NEW-0004", "ETH-USD-0002", 5.0)], []),
    ("remove_one", [], [("BTC-USD-0001", "ETH-USD-0002")]),
    ("remove_from_a_bot_not_in_the_load", [], [("NEW-0004", "ETH-USD-0002")]),
    (
        "add_and_remove_together",
        [("SOL-USD-0003", "ETH-USD-0002", 8.0)],
        [("BTC-USD-0001", "")],
    ),
]


@pytest.mark.parametrize("name", [one[0] for one in ROUTE_CASES])
def test_the_two_sides_write_the_same_routes_into_a_stored_fleet_load(name):
    """The surface saves a different route set than the shipped tab."""
    add, remove = {one[0]: (one[1], one[2]) for one in ROUTE_CASES}[name]
    home = throwaway_home()
    written: list = []
    with Seams(STORED_FLEET, home) as seams:
        tab = build_tab(seams)
        try:
            real = tab._save_bot_state_dict
            tab._save_bot_state_dict = lambda state: written.append(
                json.loads(json.dumps(state, default=str))
            )
            try:
                tab._apply_routes_to_state(list(add), list(remove))
            finally:
                tab._save_bot_state_dict = real
        finally:
            release(tab)
    fresh = json.loads(json.dumps(STORED_FLEET, default=str))
    new = surface.apply_routes(fresh, list(add), list(remove))
    assert written, "the shipped tab saved nothing, so nothing was compared"
    assert new == written[0], f"{name}: surface {new!r}, shipped {written[0]!r}"


def test_the_two_sides_clear_the_same_routes():
    """Disconnect All leaves a different load on the two sides."""
    home = throwaway_home()
    written: list = []
    with Seams(STORED_FLEET, home) as seams:
        tab = build_tab(seams)
        try:
            tab._save_bot_state_dict = lambda state: written.append(
                json.loads(json.dumps(state, default=str))
            )
            old_pairs = tab._clear_all_routes_in_state()
        finally:
            release(tab)
    fresh = json.loads(json.dumps(STORED_FLEET, default=str))
    new_pairs = surface.clear_all_routes(fresh)
    assert [list(one) for one in old_pairs] == new_pairs, (old_pairs, new_pairs)
    assert written[0] == fresh, (written[0], fresh)


def test_the_route_writer_reports_a_route_it_did_not_write():
    """The route comparison passes whatever the surface writes."""
    fresh = json.loads(json.dumps(STORED_FLEET, default=str))
    changed = surface.apply_routes(fresh, [("BTC-USD-0001", "NEW", 1.0)], [])
    assert changed != json.loads(json.dumps(STORED_FLEET, default=str))


HYDRATION_LOADS = [
    ("the_stored_fleet", STORED_FLEET, 2, 4),
    ("no_bots", STORED_FLEET_EMPTY, 0, 0),
    ("one_bot_no_routes", STORED_FLEET_ONE_BOT, 0, 0),
    ("routes_stored_with_wrong_types", STORED_FLEET_WRONG_TYPES, 0, 2),
]


@pytest.mark.parametrize("name", [one[0] for one in HYDRATION_LOADS])
def test_the_two_sides_paint_the_same_wires_from_a_stored_fleet_load(name):
    """A route on disk reaches the canvas on one side only."""
    state, painted, seen = {one[0]: one[1:] for one in HYDRATION_LOADS}[name]
    home = throwaway_home()
    with Seams(state, home) as seams:
        tab = build_tab(seams)
        try:
            old_wires = [dict(one) for one in tab._wires]
            old_painted = tab._hydrate_smart_wire_routes_from_disk()
        finally:
            release(tab)
    model = surface.BotVisualizerModel()
    counted = model.hydrate(state)
    assert old_painted == painted, (name, old_painted)
    assert counted["painted"] == painted, counted
    assert counted["seen"] == seen, counted
    assert [dict(one) for one in model.board.wires] == old_wires, (
        model.board.wires,
        old_wires,
    )


def test_the_shortfall_record_is_silent_when_every_route_painted():
    """A record written when nothing fell short means nothing."""
    assert surface.hydration_shortfall(4, 4, 0) is None
    assert surface.hydration_shortfall(2, 4, 1) is not None


def test_the_two_sides_write_the_same_shortfall_line(monkeypatch):
    """The shortfall names a different count on the two sides."""
    home = throwaway_home()
    kept: list = []
    with Seams(STORED_FLEET, home) as seams:
        tab = build_tab(seams)
        try:
            monkeypatch.setattr(
                shipped.logger,
                "warning",
                lambda message, *found, **named: kept.append([message, *found]),
            )
            tab._report_wire_hydration_shortfall(1, 4, 1)
        finally:
            release(tab)
    new = surface.hydration_shortfall(1, 4, 1)
    assert kept, "the shipped tab logged nothing, so nothing was compared"
    assert new[1:] == kept[0], (new, kept[0])
    assert new[0] == "WARNING"


# Pictures

PICTURE_CASES = ("sim", "paper", "live")


@pytest.fixture(scope="module")
def row_factory():
    """One shipped tab kept for the renders, and let go afterwards."""
    home = throwaway_home()
    seams = Seams(STORED_FLEET, home)
    with seams:
        tab = build_tab(seams)
    try:
        yield tab._create_swarm_row
    finally:
        release(tab)


PICTURE_CFG = {
    "context": "BTC/USD",
    "mode": "SCRUM",
    "feed": "1h",
    "capital": 400,
    "status": "RUNNING",
    "metric_init": "42%",
}


def widget_payload(factory, kind):
    """The row the shipped tab builds, read into a sealed payload."""
    handle = factory(kind, f"{kind}-01", dict(PICTURE_CFG))
    return sealed(old_row_state(handle)), handle["widget"]


def model_payload(kind):
    """The row the surface builds, as a sealed payload."""
    return sealed(
        new_row_state(surface.swarm_row(kind, f"{kind}-01", dict(PICTURE_CFG)))
    )


def row_painted_by_the_model(payload):
    """One row built from the answer alone, with no shipped code in it."""
    payload = unaltered(payload)
    row = QFrame()
    row.setStyleSheet(payload["widget_style_sheet"])
    strip = QHBoxLayout(row)
    strip.setContentsMargins(*surface.ROW_MARGINS)
    strip.setSpacing(surface.ROW_SPACING)
    for name in ROW_COLUMNS:
        text, width, style_sheet = payload[name]
        label = QLabel(str(text))
        label.setFixedWidth(width)
        label.setStyleSheet(style_sheet)
        strip.addWidget(label)
    strip.addStretch()
    return row


def row_painted_by_the_widget(factory, kind):
    """The shipped row, ready to render."""
    _payload, widget = widget_payload(factory, kind)
    return widget


@pytest.mark.parametrize("kind", PICTURE_CASES)
def test_the_two_sides_paint_one_row_and_carry_one_skin(kind, row_factory):
    """The surface paints a different row than the shipped tab."""
    assert_same_skin(
        build_old_side=lambda: row_painted_by_the_widget(row_factory, kind),
        build_new_side=lambda: row_painted_by_the_model(model_payload(kind)),
        size=ROW_SIZE,
        control_rule=CONTROL_RULE,
        note=kind,
    )


@pytest.mark.parametrize("kind", PICTURE_CASES)
def test_the_painted_row_shows_more_than_one_colour(kind, row_factory):
    """A render painting one colour reports nothing it is compared to."""
    from tests.qt_pixel import render_widget

    found = assert_picture_can_report(
        render_widget(row_painted_by_the_widget(row_factory, kind), ROW_SIZE),
        note=kind,
    )
    assert found > 1, found


def test_the_row_colour_counts_are_reported(row_factory):
    """A render painting too few colours reports nothing."""
    from tests.qt_pixel import render_widget
    from tests.fixtures.surface_pictures import colour_count

    counts = {
        kind: colour_count(
            render_widget(row_painted_by_the_widget(row_factory, kind), ROW_SIZE)
        )
        for kind in PICTURE_CASES
    }
    assert all(found > 1 for found in counts.values()), counts
    assert len(set(counts.values())) >= 1, counts


def test_the_picture_comparison_can_report_a_difference(row_factory):
    """Two different real rows paint one picture, so nothing is compared."""
    from tests.qt_pixel import render_widget

    assert_cases_paint_differently(
        old_side=render_widget(
            row_painted_by_the_widget(row_factory, "live"), ROW_SIZE
        ),
        new_side=render_widget(
            row_painted_by_the_model(model_payload("paper")), ROW_SIZE
        ),
        note="live against paper",
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload is rendered, so the picture measures the host."""
    payload = model_payload("sim")
    payload["kind"] = "changed"
    with pytest.raises(AssertionError):
        row_painted_by_the_model(payload)


def test_the_host_font_question_is_asked_and_not_assumed():
    """The run states what fonts the host has rather than assuming."""
    assert has_real_fonts() in (True, False)


# Order, shared state, the home directory and the world


def test_every_swapped_name_is_put_back_after_a_drive_and_after_a_refusal():
    """A swapped name outlived its drive and reached the next test."""
    home = throwaway_home()
    seams = Seams(STORED_FLEET, home)
    with seams:
        assert seams.in_place() is True
        assert seams.restored() is False
    assert seams.restored() is True
    with pytest.raises(ValueError):
        drive_old(BY_NAME["sim_run_text_where_a_number_belongs"])
    assert sm.StateManager is not StandInStateManager
    assert SignalInstance.connect is seams.saved["connect"]
    assert time.monotonic is seams.saved["monotonic"]
    assert QTimer.start is seams.saved["timer_start"]


def test_the_swap_watcher_reports_a_name_that_was_not_put_back():
    """The swap watcher answers restored whatever the names hold."""
    home = throwaway_home()
    seams = Seams(STORED_FLEET, home)
    with seams:
        pass
    assert seams.restored() is True
    saved = sm.StateManager
    sm.StateManager = StandInStateManager
    try:
        assert seams.restored() is False
    finally:
        sm.StateManager = saved
    assert seams.restored() is True


def test_a_case_reads_the_same_whatever_ran_before_it():
    """A driven case depends on what another case left behind."""
    first = digest(drive_new(BY_NAME["happy"]))
    for name in ("sim_run", "paper_run", "the_mask_is_turned_on"):
        drive_new(BY_NAME[name])
    assert digest(drive_new(BY_NAME["happy"])) == first
    first_old = digest(drive_old(BY_NAME["happy"]))
    for name in ("sim_run", "the_grid_view_is_chosen"):
        drive_old(BY_NAME[name])
    assert digest(drive_old(BY_NAME["happy"])) == first_old


def test_the_shipped_accents_are_the_same_objects_after_every_drive():
    """A drive edited the accent table every row in the tab shares."""
    before = repr(shipped.BotVisualizationTab._SWARM_ACCENTS)
    for name in ("happy", "sim_run", "paper_run", "one_bot"):
        drive_old(BY_NAME[name])
        drive_new(BY_NAME[name])
    assert repr(shipped.BotVisualizationTab._SWARM_ACCENTS) == before


def test_the_surface_hands_out_a_copy_of_each_row():
    """A caller editing one answer changed the row the next one reads."""
    model = surface.BotVisualizerModel()
    model.layer("sim").register("s1", "SIM-01", {"capital": 400})
    first = surface.build_payload(model)
    first["sim_rows"]["s1"]["kind"] = "changed"
    assert surface.build_payload(model)["sim_rows"]["s1"]["kind"] == "sim"


def test_the_shipped_file_edits_only_the_route_key_of_a_stored_load():
    """A save touched a key of the operator's load it does not own."""
    fresh = json.loads(json.dumps(STORED_FLEET, default=str))
    changed = surface.apply_routes(fresh, [("BTC-USD-0001", "SOL-USD-0003", 5.0)], [])
    before = json.loads(json.dumps(STORED_FLEET, default=str))
    for bot_id, bot in changed["bots"].items():
        for key, value in bot.items():
            if key == "scrumming_state":
                continue
            assert value == before["bots"][bot_id][key], (bot_id, key)


@pytest.fixture
def refuse_outside_connections(monkeypatch):
    """Count and refuse every outward connection this test attempts.

    The counter watches this process only. A child process opens its own
    sockets and is never seen here; the subprocess probes below carry
    their own refusal.
    """
    attempted: list = []
    real_connect = socket.socket.connect

    def outside(address) -> bool:
        host = address[0] if isinstance(address, tuple) else address
        return str(host) not in LOOPBACK

    def refuse(address):
        attempted.append(address)
        raise OSError("this test may not reach outside the process")

    def watched_connect(self, address, *found, **named):
        if outside(address):
            return refuse(address)
        return real_connect(self, address, *found, **named)

    monkeypatch.setattr(socket.socket, "connect", watched_connect)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda address, *_found, **_named: refuse(address),
    )
    yield attempted


def test_no_driven_case_reaches_outside_the_process(refuse_outside_connections):
    """A driven case opened a socket to a host."""
    for name in ("happy", "sim_run", "paper_run", "one_bot", "a_wire_is_cut"):
        drive_new(BY_NAME[name])
        drive_old(BY_NAME[name])
    assert refuse_outside_connections == [], refuse_outside_connections


def test_the_connection_counter_reports_two_real_outside_addresses(
    refuse_outside_connections,
):
    """The connection counter reports nothing whatever a test reaches for."""
    first = ("api.exchange.coinbase.com", 443)
    second = ("api.alpaca.markets", 443)
    with pytest.raises(OSError):
        socket.create_connection(first, timeout=1)
    with pytest.raises(OSError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(second)
    assert len(refuse_outside_connections) == 2, refuse_outside_connections
    assert first in refuse_outside_connections


def test_no_driven_case_writes_a_file_under_a_throwaway_home(tmp_path, monkeypatch):
    """A driven case wrote into the operator's own tree."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACERVATOR_TEST_HOME", str(home))
    for name in ("happy", "sim_run", "paper_run", "the_mask_is_turned_on"):
        drive_new(BY_NAME[name])
        drive_old(BY_NAME[name])
    assert sorted(home.rglob("*")) == [], sorted(home.rglob("*"))


def test_the_throwaway_home_check_reports_a_file_that_was_written(tmp_path):
    """The throwaway-home check reports nothing whatever a run writes."""
    home = tmp_path / "home"
    home.mkdir()
    assert sorted(home.rglob("*")) == []
    (home / "seeded.json").write_text("{}", encoding="utf-8", newline="\n")
    assert sorted(home.rglob("*")) == [home / "seeded.json"]


def test_no_drive_reads_the_operator_own_fleet_file(monkeypatch):
    """A drive read the operator's own bot_state.json."""
    opened: list = []
    import builtins

    real_open = builtins.open

    def watched_open(file, *found, **named):
        opened.append(str(file))
        return real_open(file, *found, **named)

    monkeypatch.setattr(builtins, "open", watched_open)
    drive_old(BY_NAME["happy"])
    drive_new(BY_NAME["happy"])
    named = [one for one in opened if "bot_state.json" in one]
    assert named == [], named


def test_the_file_watcher_reports_a_file_that_was_opened(tmp_path, monkeypatch):
    """The file watcher reports nothing whatever a run opens."""
    opened: list = []
    import builtins

    real_open = builtins.open

    def watched_open(file, *found, **named):
        opened.append(str(file))
        return real_open(file, *found, **named)

    monkeypatch.setattr(builtins, "open", watched_open)
    seeded = tmp_path / "bot_state.json"
    seeded.write_text("{}", encoding="utf-8", newline="\n")
    with watched_open(seeded, encoding="utf-8") as handle:
        handle.read()
    assert [one for one in opened if "bot_state.json" in one] != []


# The bridge, and a process that never loads Qt


def test_the_bridge_registers_the_bot_visualizer_method():
    """The Electron renderer cannot reach the Bot Swarm screen."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD == METHOD_NAME
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model


def test_the_bridge_import_list_is_in_order():
    """A surface added out of order in the bridge's import list."""
    from src.core import desktop_bridge

    source = Path(desktop_bridge.__file__).read_text(encoding="utf-8")
    named = [
        [alias.name for alias in node.names]
        for node in ast.walk(parsed(source))
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs"
    ]
    assert len(named) == 1, named
    assert named[0] == sorted(named[0]), named[0]
    assert "bot_visualizer_surface" in named[0]


def test_the_bridge_answer_is_json_serialisable():
    """A value in the answer cannot cross the bridge."""
    answered = surface.view_model({"reset": True})
    text = json.dumps(answered)
    assert json.loads(text)["method"] == METHOD_NAME


def test_the_bridge_handler_carries_state_between_calls():
    """The screen forgets its fleet between two calls."""
    surface.view_model({"reset": True})
    surface.view_model(
        {"action": "update_bots", "bot_statuses": fleet_statuses(STORED_FLEET)}
    )
    answered = surface.view_model({})
    assert answered["bot_ids"] == list(STORED_FLEET["bots"]), answered["bot_ids"]
    fresh = surface.view_model({"reset": True})
    assert fresh["bot_ids"] == [], fresh["bot_ids"]


#: One request per named action, each shaped to move the answer.
ACTION_ARGUMENTS = {
    "register_sim": {"action": "register_sim", "run_id": "s1", "label": "S", "cfg": {}},
    "update_sim": {"action": "update_sim", "run_id": "s1", "pnl": 3.0, "trades": 2},
    "stop_sim": {"action": "stop_sim", "run_id": "s1", "pnl": 1.0, "trades": 1},
    "register_paper": {
        "action": "register_paper",
        "run_id": "p1",
        "label": "P",
        "cfg": {},
    },
    "update_paper": {"action": "update_paper", "run_id": "p1", "pnl": 4.0, "trades": 3},
    "stop_paper": {"action": "stop_paper", "run_id": "p1", "pnl": 2.0, "trades": 1},
    "register_live": {
        "action": "register_live",
        "run_id": "BTC-USD-0001",
        "label": "L",
        "cfg": {},
    },
    "update_live": {
        "action": "update_live",
        "run_id": "BTC-USD-0001",
        "pnl": 5.0,
        "trades": 4,
    },
    "stop_live": {
        "action": "stop_live",
        "run_id": "BTC-USD-0001",
        "pnl": 6.0,
        "trades": 5,
    },
    "update_bots": {"action": "update_bots", "bot_statuses": []},
    "wire_created": {
        "action": "wire_created",
        "event": {
            "source_id": "BTC-USD-0001",
            "target_id": "ETH-USD-0002",
            "pct": 25.0,
        },
    },
    "wire_removed": {
        "action": "wire_removed",
        "event": {"source_id": "BTC-USD-0001", "target_id": "ETH-USD-0002"},
    },
    "remove_wire": {
        "action": "remove_wire",
        "source_id": "BTC-USD-0001",
        "target_id": "ETH-USD-0002",
    },
    "animate": {"action": "animate", "dt": 0.5},
    "set_view_mode": {"action": "set_view_mode", "mode": "grid"},
    "set_opacity": {"action": "set_opacity", "pct": 40},
    "set_exchange": {"action": "set_exchange", "exchange": "coinbase"},
    "set_theme": {"action": "set_theme", "theme_key": "matrix"},
    "set_masked": {"action": "set_masked", "masked": True},
    "toggle_privacy_mode": {"action": "toggle_privacy_mode"},
    "wire_sheet": {
        "action": "wire_sheet",
        "boxes": {"BTC-USD-0001": [0, 0, 112, 98], "ETH-USD-0002": [122, 0, 112, 98]},
    },
    "finish_drag": {
        "action": "finish_drag",
        "source_id": "BTC-USD-0001",
        "target_id": "ETH-USD-0002",
    },
    "answer_panel": {"action": "answer_panel", "choice": "cancel"},
    "hydrate": {"action": "hydrate", "state": STORED_FLEET},
}


#: What each action needs already done before it can move anything.
ACTION_PRECONDITION = {
    "update_sim": ("register_sim",),
    "stop_sim": ("register_sim",),
    "update_paper": ("register_paper",),
    "stop_paper": ("register_paper",),
    "update_live": ("register_live",),
    "stop_live": ("register_live",),
    "wire_removed": ("wire_created",),
    "wire_sheet": ("wire_created",),
    "remove_wire": ("wire_created",),
    "animate": ("wire_created",),
}


def _prepared(action: str):
    """A fleet-loaded model with whatever ``action`` needs already applied."""
    model = surface.BotVisualizerModel()
    model.update_bots(fleet_statuses(STORED_FLEET))
    for earlier in ACTION_PRECONDITION.get(action, ()):
        surface.apply_action(model, ACTION_ARGUMENTS[earlier])
    if action == "answer_panel":
        model.finish_drag("BTC-USD-0001", "ETH-USD-0002")
    return model


def test_every_named_action_moves_the_answer():
    """An action the bridge names does nothing when it is asked for."""
    surface.view_model({"reset": True})
    before = digest(surface.view_model({}))
    surface.view_model(
        {"action": "update_bots", "bot_statuses": fleet_statuses(STORED_FLEET)}
    )
    assert digest(surface.view_model({})) != before
    for action in surface.ACTIONS:
        model = _prepared(action)
        rested = digest(surface.build_payload(model))
        moved = digest(surface.apply_action(model, ACTION_ARGUMENTS[action]))
        assert moved != rested, action
    model = _prepared("")
    rested = digest(surface.build_payload(model))
    unnamed = digest(surface.apply_action(model, {"action": "no such action"}))
    assert unnamed == rested, "an action the surface does not name moved the answer"
    surface.view_model({"reset": True})


BRIDGE_PROBE = (
    "import json\n"
    "import sys\n"
    "from src.core import desktop_bridge\n"
    "line = json.dumps({'id': 1, 'method': 'bot_visualizer.state',"
    " 'params': {'reset': True, 'action': 'hydrate', 'state':"
    " {'bots': {'BTC-USD-0001': {'scrumming_state':"
    " {'smart_wire_routes': [{'dest_bot_id': 'ETH-USD-0002',"
    " 'pct': 25.0}]}}}}}})\n"
    "answered = desktop_bridge.handle_line(line, desktop_bridge.build_registry())\n"
    "print(json.dumps({'frame': answered, 'qt': [name for name in sys.modules"
    " if name.startswith('PySide6')]}))\n"
)

NOTHING_AT_IMPORT_PROBE = """
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-botviz-probe-'))
os.environ['HOME'] = str(root)
os.environ['USERPROFILE'] = str(root)

opened = []
real_open = open


def watched_open(file, *found, **named):
    opened.append(str(file))
    return real_open(file, *found, **named)


import builtins
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
from src.gui.main_tabs import bot_visualizer_surface as s

opened_at_import = opened[opened_before:]
clock_at_import = clock[clock_before:]
threads_at_import = threading.active_count() - threads_before
built = s.view_model({'reset': True})
answer = {'frame_ms': s.FRAME_INTERVAL_MS,
          'built_on_request': built['method'],
          'method': s.METHOD,
          'qt': [name for name in sys.modules if name.startswith('PySide6')],
          'opened_at_import': opened_at_import,
          'clock_at_import': clock_at_import,
          'threads_at_import': threads_at_import,
          'reached_at_import': list(reached),
          'made_under_home': sorted(str(p) for p in root.rglob('*'))}
builtins.open = real_open
print(json.dumps(answer))
"""


def run_script(source, env=None):
    """Run one probe in a fresh process and return what it printed."""
    where = dict(os.environ)
    where.pop("ACERVATOR_TEST_HOME", None)
    where["PYTHONIOENCODING"] = "utf-8"
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


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the Bot Swarm screen pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] == [], answered["qt"]
    assert answered["frame"]["ok"] is True, answered["frame"]
    result = answered["frame"]["result"]
    assert result["wire_count"] == 1, result["wire_count"]
    assert result["wires"][0]["source_id"] == "BTC-USD-0001", result["wires"]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore\n" + BRIDGE_PROBE)
    assert loaded["qt"] != []
    assert loaded["frame"]["ok"] is True


def test_importing_the_surface_reads_no_file_and_no_clock():
    """Loading the surface read a file, read the clock or started a thread."""
    answered = run_script(NOTHING_AT_IMPORT_PROBE)
    assert answered["qt"] == [], answered["qt"]
    assert answered["clock_at_import"] == [], answered
    assert answered["threads_at_import"] == 0, answered
    assert answered["reached_at_import"] == [], answered
    assert answered["made_under_home"] == [], answered
    assert [
        one for one in answered["opened_at_import"] if "bot_visualizer" in one
    ] == [], answered
    assert answered["frame_ms"] == 33
    assert answered["method"] == METHOD_NAME


def test_the_import_probe_can_report_a_file_a_clock_and_a_connection():
    """The import probe reports nothing whatever the module does."""
    probe = NOTHING_AT_IMPORT_PROBE.replace(
        "from src.gui.main_tabs import bot_visualizer_surface as s",
        "time.time()\n"
        "with open(root / 'bot_visualizer-seeded.json', 'w') as fh:\n"
        "    fh.write('{}')\n"
        "try:\n"
        "    socket.create_connection(('example.invalid', 443))\n"
        "except OSError:\n"
        "    pass\n"
        "threading.Thread(target=lambda: None).start()\n"
        "from src.gui.main_tabs import bot_visualizer_surface as s",
    )
    answered = run_script(probe)
    assert answered["clock_at_import"] == ["time"], answered
    assert answered["reached_at_import"] != [], answered
    assert answered["made_under_home"] != [], answered
    assert [
        one for one in answered["opened_at_import"] if "bot_visualizer" in one
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
    for forbidden in (
        "read_text",
        "write_text",
        "mkdir",
        "urlopen",
        "monotonic",
        "time",
    ):
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
    """The surface copies the shipped file rather than carrying its own."""
    named = {
        node.module or ""
        for node in ast.walk(parsed(SURFACE_SOURCE))
        if isinstance(node, ast.ImportFrom)
    }
    assert "src.gui.bot_visualizer" not in named, named
    assert not any(name.endswith("bot_visualizer") for name in named), named
    assert not any("design_system" in name for name in named), named


def test_the_tokens_the_two_sides_read_have_not_drifted():
    """A token was copied and then changed on the shipped side only."""
    from src.gui import design_system as ds

    assert surface.SUCCESS_COLOR == ds.SUCCESS
    assert surface.ERROR_COLOR == ds.ERROR
    assert surface.ACCENT_GOLD_COLOR == ds.ACCENT_GOLD
    assert surface.PRIMARY_BRIGHT_COLOR == ds.PRIMARY_BRIGHT
    assert surface.VIZ_LANE_LIVE_COLOR == ds.VIZ_LANE_LIVE
    assert surface.VIZ_LANE_PAPER_COLOR == ds.VIZ_LANE_PAPER
    assert surface.VIZ_CAPTION_COLOR == ds.VIZ_CAPTION
    assert surface.VIZ_PANEL_SURFACE_COLOR == ds.VIZ_PANEL_SURFACE
    assert surface.VIZ_PANEL_BORDER_COLOR == ds.VIZ_PANEL_BORDER
    assert surface.TEXT_PLACEHOLDER_COLOR == ds.TEXT_PLACEHOLDER
    assert surface.CARD_METRIC_LABEL_COLOR == ds.CARD_METRIC_LABEL


def flat_colours() -> list:
    """Every colour whose channels all match, which a swap cannot report."""
    return sorted(
        f"{name}={value}"
        for name, value in surface_constants().items()
        if isinstance(value, str) and value.startswith("#") and len(set(value[1:])) == 1
    )


def test_three_colours_on_this_screen_have_equal_channels():
    """A colour a channel swap cannot report was added or removed.

    These three are grey, so swapping their channels paints the same
    pixel and no picture proves them. Every other colour on the screen
    is proved by the swap check below.
    """
    assert flat_colours() == [
        "CARD_METRIC_LABEL_COLOR=#888",
        "TEXT_INACTIVE_COLOR=#aaaaaa",
        "TEXT_PLACEHOLDER_COLOR=#555555",
    ], flat_colours()


def test_the_channel_reader_reports_a_colour_whose_channels_match():
    """The channel reader reports nothing whatever a colour holds."""
    assert len(set("888")) == 1
    assert len(set("0c0c1a")) > 1


def test_this_file_imports_only_what_the_fast_lane_installs():
    """This file needs a package the CI fast lane never installs."""
    from tests.test_ci_fast_lane_packages import offending_imports

    offences = [
        line
        for line in offending_imports(REPO_ROOT / "tests")
        if Path(__file__).name in line
    ]
    assert offences == [], offences


# The bare-reading audit

BARE_READINGS = (
    True,
    NOT_A_NUMBER,
    INFINITY,
    MINUS_INFINITY,
    "twelve",
    "12.7",
    12.7,
    HUGE_INTEGER,
)

BARE_READING_NAMES = (
    "True",
    "nan",
    "inf",
    "-inf",
    "text",
    "12.7 as text",
    "12.7",
    "10**400",
)


def read_one(build) -> str:
    """One reading's result, or the name of the fault it raised."""
    try:
        return f"shows {build()!r}"
    except Exception as exc:
        return f"stops with {type(exc).__name__}"


def audit_row(tab, value) -> dict:
    """What one stored value does to each number the tab reads."""
    found = {}
    found["capital"] = read_one(lambda: _capital_of(tab, value))
    found["pnl"] = read_one(lambda: _pnl_of(tab, value))
    found["trades"] = read_one(lambda: _trades_of(tab, value))
    found["progress"] = read_one(lambda: _progress_of(tab, value))
    found["price"] = read_one(lambda: _price_of(tab, value))
    found["route_pct"] = read_one(lambda: _route_pct_of(tab, value))
    found["list_flows"] = read_one(lambda: _flows_of(tab, value))
    return found


def _capital_of(tab, value):
    """The capital column for one stored value.

    The whole handle is held while the text is read: the row owns every
    column, so letting it go frees the label and the read raises instead
    of reporting.
    """
    handle = tab._create_swarm_row("sim", "x", {"capital": value})
    return handle["cap_lbl"].text()


def _pnl_of(tab, value):
    handle = tab._create_swarm_row("sim", "x", {})
    tab._apply_pnl_color(handle, value)
    return handle["pnl_lbl"].text()


def _trades_of(tab, value):
    tab.register_sim_run("audit", "x", {})
    tab.update_sim_run("audit", 0.0, value, 0)
    return tab._live_sim_rows["audit"]["trades_lbl"].text()


def _progress_of(tab, value):
    tab.register_sim_run("audit", "x", {"candle_total": 10})
    tab.update_sim_run("audit", 0.0, 0, value)
    return tab._live_sim_rows["audit"]["metric_lbl"].text()


def _price_of(tab, value):
    tab.register_paper_run("audit", "x", {})
    tab.update_paper_run("audit", value, 0.0, 0)
    return tab._live_paper_rows["audit"]["metric_lbl"].text()


def _route_pct_of(tab, value):
    tab._wires = []
    state = {
        "bots": {
            "A": {
                "scrumming_state": {
                    "smart_wire_routes": [{"dest_bot_id": "B", "pct": value}]
                }
            }
        }
    }
    real = tab._load_bot_state_dict
    tab._load_bot_state_dict = lambda: state
    try:
        tab._hydrate_smart_wire_routes_from_disk()
    finally:
        tab._load_bot_state_dict = real
    return [dict(one) for one in tab._wires]


def _flows_of(tab, value):
    tab.update_bots(
        [
            {
                "bot_id": "AUDIT-0001",
                "symbol": "AUD/USD",
                "stats": {"ytd_folded_usd": value, "ytd_scrummed_usd": value},
            }
        ]
    )
    return "sent"


def test_the_bare_reading_audit_is_reported():
    """Every number read out of stored state, driven with eight values.

    The table is the point. A reading that shows a number nobody stored
    is the shape this audit is looking for; a reading that stops takes
    its own row with it.
    """
    table = {}
    for name, value in zip(BARE_READING_NAMES, BARE_READINGS):
        home = throwaway_home()
        with Seams(STORED_FLEET_EMPTY, home) as seams:
            tab = build_tab(seams)
            try:
                table[name] = audit_row(tab, value)
            finally:
                release(tab)
    assert len(table) == len(BARE_READINGS), table
    assert table["True"]["capital"] == "shows '$1'", table["True"]
    assert table["nan"]["capital"] == "shows '$nan'", table["nan"]
    assert table["text"]["capital"].startswith("stops with"), table["text"]
    assert table["12.7 as text"]["capital"].startswith("stops with"), table[
        "12.7 as text"
    ]


def test_the_two_sides_read_a_bare_stored_value_the_same_way():
    """The surface hides a bad stored number the shipped tab shows."""
    for value in BARE_READINGS:
        old_capital = read_one(
            lambda v=value: surface.CAPITAL_TEXT_FORMAT.format(capital=v)
        )
        home = throwaway_home()
        with Seams(STORED_FLEET_EMPTY, home) as seams:
            tab = build_tab(seams)
            try:
                shipped_capital = read_one(lambda v=value: _capital_of(tab, v))
            finally:
                release(tab)
        assert old_capital == shipped_capital, (value, old_capital, shipped_capital)


def test_the_audit_reader_reports_a_reading_that_stops():
    """The audit reader reports a number whatever the reading did."""
    assert read_one(lambda: 1 / 0) == "stops with ZeroDivisionError"
    assert read_one(lambda: "$1") == "shows '$1'"


def test_a_stored_not_a_number_reaches_the_flow_columns_unguarded():
    """A stored not-a-number is stopped before it reaches the list."""
    rows = surface.list_rows(
        {"A": {"symbol": "A/B", "stats": {"ytd_folded_usd": NOT_A_NUMBER}}}, []
    )
    assert math.isnan(rows[0]["inflow_usd"]), rows


def test_the_math_import_is_used_by_the_hit_reader():
    """The hit reader stopped measuring distance."""
    assert surface.math.sqrt(4) == 2.0
    assert Qt is not None
