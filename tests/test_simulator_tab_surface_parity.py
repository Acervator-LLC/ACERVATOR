"""The Qt Simulator tab and the Qt-free surface, side by side.

A failure means the view model describes a different tab, a different
dropdown, a different log, a different bot row, a different refusal or a
different pin than ``src.gui.simulator_tab.simulator_tab`` produces on
the same input.

The fleet every case drives is read by the real bot-state loader out of a
file this test writes under ``tmp_path``. Nothing here invents a bot, a
symbol or a topology.
"""

from __future__ import annotations

import ast
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.core import signal_contract
from src.gui import bot_live_settings as shipped_settings
from src.gui.main_tabs import simulator_tab_surface as surface
from src.gui.simulator_tab import simulator_tab as shipped
from src.simulator.fleet.bot_state_loader import load_bot_configs_from_state
from tests.fixtures.host_fonts import has_real_fonts
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "simulator_tab_surface.py"
BRIDGE_SOURCE = REPO_ROOT / "src" / "core" / "desktop_bridge.py"

PIXEL_SIZE = (420, 180)
LOG_PIXEL_SIZE = (420, 140)

LONG_TEXT = "z" * 200
UNICODE_TEXT = "БТЦ ➜ 日本 · ünïcødé"
MARKUP_TEXT = "<b>bold</b> & <i>tilt</i>"
APOSTROPHE_TEXT = "the bot's own tape"
NEWLINE_TEXT = "first\nsecond"
WRONG_CAPITALS = "cHiP/uSd"
HUGE_INT = 2**1023
HUGER_INT = 2**1024


def app():
    """The one application object every render is taken against.

    ``ACERVATOR_TEST_FONTS=1`` lends this run a real family, so every
    picture below is taken twice: once on a host with no fonts and once
    with one loaded into the offscreen driver.
    """
    from tests.fixtures.host_fonts import load_run_fonts
    from tests.qt_pixel import ensure_app

    held = ensure_app()
    load_run_fonts()
    return held


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
        return {str(key): as_text(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_text(inner) for inner in value]
    return value


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    import hashlib

    return hashlib.sha256(
        json.dumps(
            as_text(value), sort_keys=True, ensure_ascii=True, default=repr
        ).encode("utf-8")
    ).hexdigest()


def first_difference(one, other, path="") -> str:
    """The first place two payloads disagree, named by its own key."""
    if isinstance(one, dict) and isinstance(other, dict):
        for key in sorted(set(one) | set(other)):
            if key not in one:
                return f"{path}.{key}: missing on the old side"
            if key not in other:
                return f"{path}.{key}: missing on the new side"
            found = first_difference(one[key], other[key], f"{path}.{key}")
            if found:
                return found
        return ""
    if isinstance(one, list) and isinstance(other, list):
        if len(one) != len(other):
            return f"{path}: {len(one)} rows against {len(other)}"
        for at, (left, right) in enumerate(zip(one, other)):
            found = first_difference(left, right, f"{path}[{at}]")
            if found:
                return found
        return ""
    if as_text(one) != as_text(other):
        return f"{path}: {one!r} against {other!r}"
    return ""


# ---------------------------------------------------------------------
# The stored fleet load. One file, read by the real loader.
# ---------------------------------------------------------------------

STORED_LOTS = [
    {"units": 4000.5, "price": 0.021},
    {"units": 7018.26, "price": 0.0195},
    {"not_a_lot": True},
]

STORED_FLEET = {
    "bots": {
        "04e1cafcd0f14b1e9c77": {
            "config": {
                "symbol": "CHIP/USD",
                "mode": "scrumming",
                "exchange_id": "coinbase",
                "target_balance": 250.0,
            },
            "scrumming_state": {
                "main_lots": STORED_LOTS,
                "anchor_target_balance": 250.0,
                "target_balance": 252.1391,
                "quote_to_usd": 1.0,
            },
            "stats": {
                "current_price": 0.0212,
                "position_value": 233.6,
                "total_trades": 363,
            },
        },
        "092428b2ab114c2d8e51": {
            "config": {
                "symbol": "SPK/USD",
                "mode": "scrumming",
                "exchange_id": "coinbase",
                "target_balance": 100.0,
            },
            "scrumming_state": {
                "main_lots": [{"units": 120.0}],
                "anchor_target_balance": 100.0,
                "target_balance": 101.5,
                "quote_to_usd": 1.0,
            },
            "stats": {
                "current_price": 0.0,
                "position_value": 0.0,
                "total_trades": 0,
            },
        },
    }
}


def stored_fleet_configs(tmp_path, fleet=None) -> list:
    """The configs the real loader reads out of a stored bot_state file."""
    written = tmp_path / "bot_state.json"
    written.write_text(
        json.dumps(fleet if fleet is not None else STORED_FLEET), encoding="utf-8"
    )
    return load_bot_configs_from_state(path=written)


def with_stored_number(configs, where, key, value) -> list:
    """The same fleet with one stored number replaced by `value`."""
    changed = [dict(one) for one in configs]
    section = dict(changed[0].get(where) or {})
    section[key] = value
    changed[0][where] = section
    return changed


# ---------------------------------------------------------------------
# The stand-ins. One per side, never shared.
# ---------------------------------------------------------------------


class RecordingSink:
    """Collect the pins one side emits, keeping the module that emitted."""

    def __init__(self, module_name):
        self.module_name = module_name
        self.rows = []
        self.every = []

    def emit(
        self,
        name,
        actual,
        expected=None,
        ok=None,
        context=None,
        site=None,
        module=None,
        count=1,
        duration=None,
        every=0.0,
    ):
        self.every.append([name, site, module, ok, count, duration, every])
        if module == self.module_name:
            self.rows.append(
                {
                    "name": name,
                    "actual": actual,
                    "expected": expected,
                    "context": context,
                }
            )
        return None


class SideDialog:
    """The settings screen the Simulator opens for one bot row."""

    opened: list = []

    def __init__(self, bot, manager=None, parent=None):
        self.bot = bot
        self.manager = manager
        self.parent = parent

    def exec(self):
        SideDialog.opened.append(str(getattr(self.bot, "bot_id", "")))


def qt_table_class(columns):
    """A Qt bot table that records the rows it is given.

    A ``QWidget`` because the shipped mount adds it to a layout; a table
    that is not a widget would refuse for the wrong reason.
    """
    from PySide6.QtWidgets import QWidget

    class QtTable(QWidget):
        COLUMNS = columns

        def __init__(self, on_bot_clicked=None, on_fire_clicked=None):
            super().__init__()
            self.setAccessibleName("Simulator bot table stand-in")
            self.on_bot_clicked = on_bot_clicked
            self.on_fire_clicked = on_fire_clicked
            self.rows = []
            self.fire_cells = []

        def update_bots(self, statuses):
            self.rows = list(statuses)
            self.fire_cells = [surface.FireCell() for _ in self.rows]

        def rowCount(self):
            return len(self.rows)

        def cellWidget(self, row, column):
            try:
                fire = list(type(self).COLUMNS).index(surface.FIRE_COLUMN)
            except ValueError:
                return None
            if column != fire:
                return None
            if 0 <= row < len(self.fire_cells):
                return QtFireCell(self.fire_cells[row])
            return None

    return QtTable


class QtFireCell:
    """The Fire control the shipped disable pass reaches for."""

    def __init__(self, held):
        self.held = held

    def setEnabled(self, enabled):
        self.held.set_enabled(enabled)

    def setToolTip(self, tooltip):
        self.held.set_tool_tip(tooltip)


class QtPanel:
    """The fleet panel the shipped tab hangs everything off.

    Handed the statuses a fleet load already produced. Nothing here
    builds a fleet.
    """

    def __init__(self, statuses=None, table=True, bots=(), statuses_raises=None):
        self.statuses = statuses
        self.table = table
        self.statuses_raises = statuses_raises
        self._controller = surface.SimController([surface.SimBot(one) for one in bots])
        self._bot_status_table_widget = None
        self._bot_table_columns = []
        self.sim_mode_calls = []
        self.emitted_table_counts = []
        self.bot_manager = None
        self.connectors_getter = None

    def _bot_status_table(self):
        return qt_table_class(surface.BotTable.COLUMNS) if self.table else None

    def sim_bot_statuses(self):
        if self.statuses_raises is not None:
            raise self.statuses_raises
        return list(self.statuses) if self.statuses is not None else []

    def set_sim_mode(self, key):
        self.sim_mode_calls.append(key)

    def emit_bot_table(self, total):
        self.emitted_table_counts.append(total)

    def set_connectors_getter(self, getter):
        self.connectors_getter = getter

    def set_bot_manager(self, bot_manager):
        self.bot_manager = bot_manager


class QtChart:
    """The price chart the shipped fleet load points at."""

    def __init__(self, set_symbols_raises=None):
        self.set_symbols_raises = set_symbols_raises
        self.symbols = []
        self.focus_symbol = ""
        self.focus_calls = 0

    def set_symbols(self, symbols):
        if self.set_symbols_raises is not None:
            raise self.set_symbols_raises
        self.symbols = list(symbols)

    def set_focus_symbol(self, symbol):
        self.focus_calls += 1
        self.focus_symbol = symbol


class QtNuclear:
    """The Nuclear page, as far as the shipped tab talks to it."""

    def __init__(self):
        self.swarm_getter = None
        self.topology_getter = None

    def set_swarm_getter(self, getter):
        self.swarm_getter = getter

    def set_topology_getter(self, getter):
        self.topology_getter = getter


# ---------------------------------------------------------------------
# The two sides, driven through one step language.
# ---------------------------------------------------------------------

LIVE_TABS: list = []


class ShippedSide:
    """Drive the real ``SimulatorTab`` and read its values back."""

    name = "old"

    def __init__(self, spec):
        app()
        self.sink = RecordingSink(shipped.__name__)
        self.previous_sink = signal_contract.get_sink()
        signal_contract.set_sink(self.sink)
        self.previous_dialog = shipped_settings.BotLiveSettingsDialog
        shipped_settings.BotLiveSettingsDialog = SideDialog
        SideDialog.opened = []
        try:
            self.tab = shipped.SimulatorTab()
        finally:
            LIVE_TABS.append(getattr(self, "tab", None))
        self.sink.rows = []
        self.panel = QtPanel(**spec.get("panel", {}))
        self.tab.fleet_replay = self.panel
        self.chart = QtChart(**spec.get("chart", {}))
        self.tab._sim_price_chart = self.chart
        self.nuclear = QtNuclear()
        self.tab.nuclear_mode = self.nuclear
        self.tab._active_bot_picker.clear()
        self.tab._active_bot_picker.addItem(
            surface.ALL_BOTS_TEXT, surface.ALL_BOTS_DATA
        )
        self.tab._chart_bot_picker.blockSignals(True)
        self.tab._chart_bot_picker.clear()
        self.tab._chart_bot_picker.addItem(
            surface.CHART_PICKER_EMPTY_TEXT, surface.CHART_PICKER_EMPTY_DATA
        )
        self.tab._chart_bot_picker.blockSignals(False)
        self.steps = []

    def close(self):
        signal_contract.set_sink(self.previous_sink)
        shipped_settings.BotLiveSettingsDialog = self.previous_dialog

    def step(self, index, name, argument=None):
        tab = self.tab
        try:
            if name == "build":
                tab.mount_bot_status_table()
                tab._on_sim_mode_changed()
            elif name == "mode":
                at = tab._mode_selector.findData(argument)
                tab._mode_selector.setCurrentIndex(at)
            elif name == "mount":
                self.mounted = tab.mount_bot_status_table()
            elif name == "fleet":
                tab._on_fleet_loaded(argument)
            elif name == "statuses":
                tab.refresh_active_bot_roster(argument)
            elif name == "symbols":
                tab.refresh_chart_bot_roster(argument)
            elif name == "chart_bot":
                at = tab._chart_bot_picker.findData(argument)
                tab._chart_bot_picker.setCurrentIndex(at)
                tab._on_chart_bot_changed(at)
            elif name == "detail":
                tab._on_sim_bot_detail(argument)
            elif name == "pause":
                tab._on_activity_paused(argument)
            elif name == "activity":
                tab.log_activity(argument)
            elif name == "performance":
                tab.log_performance(argument)
            elif name == "disable_fire":
                tab._disable_fire_buttons()
            elif name == "async_loop":
                tab.set_async_loop(argument)
            elif name == "swarm":
                tab.set_swarm_getter(argument)
            elif name == "topology":
                tab.set_topology_getter(argument)
            elif name == "connectors":
                tab.set_connectors_getter(argument)
            elif name == "bot_manager":
                tab.set_bot_manager(argument)
            else:
                raise LookupError(name)
        except Exception as exc:
            self.steps.append([index, name, type(exc).__name__])
            return type(exc).__name__
        self.steps.append([index, name, None])
        return None

    def payload(self):
        tab = self.tab
        widget = self.panel._bot_status_table_widget
        return {
            "identity": {
                "accessible_name": tab.accessibleName(),
                "object_name": tab.objectName(),
            },
            "modes": {
                "items": [
                    [tab._mode_selector.itemText(at), tab._mode_selector.itemData(at)]
                    for at in range(tab._mode_selector.count())
                ],
                "selected": tab.sim_mode(),
                "hint_text": tab._mode_hint.text(),
                "stack_index": tab._stack.currentIndex(),
                "stack_count": tab._stack.count(),
                "index": tab._mode_selector.currentIndex(),
                "selector_min_width": tab._mode_selector.minimumWidth(),
                "selector_tooltip": tab._mode_selector.toolTip(),
            },
            "pickers": {
                "active": {
                    "items": [
                        [
                            tab._active_bot_picker.itemText(at),
                            tab._active_bot_picker.itemData(at),
                        ]
                        for at in range(tab._active_bot_picker.count())
                    ],
                    "index": tab._active_bot_picker.currentIndex(),
                    "selected": tab.active_bot_id(),
                    "blocked": tab._active_bot_picker.signalsBlocked(),
                },
                "chart": {
                    "items": [
                        [
                            tab._chart_bot_picker.itemText(at),
                            tab._chart_bot_picker.itemData(at),
                        ]
                        for at in range(tab._chart_bot_picker.count())
                    ],
                    "index": tab._chart_bot_picker.currentIndex(),
                    "blocked": tab._chart_bot_picker.signalsBlocked(),
                    "focus_symbol": self.chart.focus_symbol,
                    "symbols": list(self.chart.symbols),
                },
            },
            "log": {
                "text": tab.simulator_log.toPlainText(),
                "maximum_blocks": tab.simulator_log.maximumBlockCount(),
                "activity_paused": tab._activity_paused,
                "performance_paused": tab._perf_paused,
                "pause_button_text": tab._activity_pause_btn.text(),
                "merged": tab.activity_log is tab.performance_log,
            },
            "table": {
                "mounted": widget is not None,
                "columns": list(self.panel._bot_table_columns),
                "rows": [dict(one) for one in getattr(widget, "rows", [])],
                "fire_enabled": [
                    cell.enabled for cell in getattr(widget, "fire_cells", [])
                ],
                "fire_tooltips": [
                    cell.tooltip for cell in getattr(widget, "fire_cells", [])
                ],
                "emitted_counts": list(self.panel.emitted_table_counts),
            },
            "wiring": {
                "sim_mode_calls": list(self.panel.sim_mode_calls),
                "async_loop_set": tab._async_loop is not None,
                "swarm_getter_set": tab._swarm_getter is not None,
                "topology_getter_set": tab._topology_getter is not None,
                "connectors_getter_set": tab._connectors_getter is not None,
                "nuclear_swarm_getter_set": self.nuclear.swarm_getter is not None,
                "nuclear_topology_getter_set": (
                    self.nuclear.topology_getter is not None
                ),
                "panel_bot_manager_set": self.panel.bot_manager is not None,
                "panel_connectors_getter_set": (
                    self.panel.connectors_getter is not None
                ),
            },
            "pins": list(self.sink.rows),
            "steps": [list(one) for one in self.steps],
            "dialogs": list(SideDialog.opened),
        }


class SurfaceSide:
    """Drive the Qt-free model and read the same values back."""

    name = "new"

    def __init__(self, spec):
        self.model = surface.SimulatorTabModel()
        panel_spec = dict(spec.get("panel", {}))
        self.panel = surface.FleetPanel(
            statuses=panel_spec.get("statuses"),
            table_class=(surface.BotTable if panel_spec.get("table", True) else None),
            controller=surface.SimController(
                [surface.SimBot(one) for one in panel_spec.get("bots", ())]
            ),
            statuses_raises=panel_spec.get("statuses_raises"),
        )
        self.model.set_fleet_panel(self.panel)
        self.chart = surface.PriceChart(**spec.get("chart", {}))
        self.model.set_price_chart(self.chart)
        self.nuclear = surface.NuclearPanel()
        self.model.set_nuclear_panel(self.nuclear)
        self.dialog = surface.BotSettingsDialog()
        self.model.settings_dialog = self.dialog
        self.opened = []
        self.steps = []

    def close(self):
        return None

    def step(self, index, name, argument=None):
        model = self.model
        try:
            if name == "build":
                model.mount_bot_status_table()
                model.on_sim_mode_changed()
            elif name == "mode":
                model.select_mode(argument)
            elif name == "mount":
                self.mounted = model.mount_bot_status_table()
            elif name == "fleet":
                model.on_fleet_loaded(argument)
            elif name == "statuses":
                model.refresh_active_bot_roster(argument)
            elif name == "symbols":
                model.refresh_chart_bot_roster(argument)
            elif name == "chart_bot":
                model.select_chart_bot(argument)
            elif name == "detail":
                before = self.dialog.shown
                model.on_sim_bot_detail(argument)
                if self.dialog.shown > before:
                    self.opened.append(str(argument))
            elif name == "pause":
                model.on_activity_paused(argument)
            elif name == "activity":
                model.log_activity(argument)
            elif name == "performance":
                model.log_performance(argument)
            elif name == "disable_fire":
                model.disable_fire_buttons()
            elif name == "async_loop":
                model.set_async_loop(argument)
            elif name == "swarm":
                model.set_swarm_getter(argument)
            elif name == "topology":
                model.set_topology_getter(argument)
            elif name == "connectors":
                model.set_connectors_getter(argument)
            elif name == "bot_manager":
                model.set_bot_manager(argument)
            else:
                raise LookupError(name)
        except Exception as exc:
            self.steps.append([index, name, type(exc).__name__])
            return type(exc).__name__
        self.steps.append([index, name, None])
        return None

    def payload(self):
        built = surface.build_view_model(self.model)
        model = self.model
        return {
            "identity": {
                "accessible_name": built["identity"]["accessible_name"],
                "object_name": built["identity"]["object_name"],
            },
            "modes": {
                "items": [list(one) for one in built["modes"]["items"]],
                "selected": built["modes"]["selected"],
                "hint_text": built["modes"]["hint_text"],
                "stack_index": built["modes"]["stack_index"],
                "stack_count": built["modes"]["stack_count"],
                "index": built["modes"]["index"],
                "selector_min_width": built["modes"]["selector_min_width"],
                "selector_tooltip": built["modes"]["selector_tooltip"],
            },
            "pickers": {
                "active": {
                    "items": built["pickers"]["active"]["items"],
                    "index": built["pickers"]["active"]["index"],
                    "selected": built["pickers"]["active"]["selected"],
                    "blocked": model.active_bot_picker.signals_blocked,
                },
                "chart": {
                    "items": built["pickers"]["chart"]["items"],
                    "index": built["pickers"]["chart"]["index"],
                    "blocked": model.chart_bot_picker.signals_blocked,
                    "focus_symbol": built["pickers"]["chart"]["focus_symbol"],
                    "symbols": built["pickers"]["chart"]["symbols"],
                },
            },
            "log": {
                "text": built["log"]["text"],
                "maximum_blocks": built["log"]["maximum_blocks"],
                "activity_paused": built["log"]["activity_paused"],
                "performance_paused": built["log"]["performance_paused"],
                "pause_button_text": built["log"]["pause_button_text"],
                "merged": True,
            },
            "table": built["table"],
            "wiring": {
                key: built["wiring"][key]
                for key in (
                    "sim_mode_calls",
                    "async_loop_set",
                    "swarm_getter_set",
                    "topology_getter_set",
                    "connectors_getter_set",
                    "nuclear_swarm_getter_set",
                    "nuclear_topology_getter_set",
                    "panel_bot_manager_set",
                    "panel_connectors_getter_set",
                )
            },
            "pins": built["pins"]["emitted"],
            "steps": [list(one) for one in self.steps],
            "dialogs": list(self.opened),
        }


def drive(side_class, spec):
    """Run one spec's steps through one side and take its payload."""
    side = side_class(spec)
    try:
        for index, step in enumerate(spec["steps"]):
            side.step(index, step[0], *step[1:])
        return side.payload()
    finally:
        side.close()


def both(spec):
    """The same spec driven through each side, old first."""
    return drive(ShippedSide, spec), drive(SurfaceSide, spec)


# ---------------------------------------------------------------------
# The cases. One per state the tab can be in.
# ---------------------------------------------------------------------


def case_no_run():
    return {"panel": {}, "steps": [("build",)]}


def case_part_way(configs):
    return {
        "panel": {"bots": ["04e1cafcd0f14b1e9c77"]},
        "steps": [
            ("build",),
            ("fleet", configs),
            ("activity", "replay started"),
            ("performance", "tick 1 of 400"),
        ],
    }


def case_finished(configs):
    return {
        "panel": {
            "statuses": [
                {
                    "bot_id": "04e1cafcd0f14b1e9c77",
                    "symbol": "CHIP/USD",
                    "mode": "scrumming",
                    "state": "RUNNING",
                    "exchange": "coinbase",
                    "target_balance": 250.0,
                    "live_target_balance": 252.1391,
                    "current_holdings": 11018.76,
                    "quote_to_usd": 1.0,
                    "stats": {
                        "current_price": 0.0212,
                        "position_value": 233.6,
                        "total_trades": 363,
                    },
                }
            ],
            "bots": ["04e1cafcd0f14b1e9c77"],
        },
        "steps": [
            ("build",),
            ("fleet", configs),
            ("mode", "nuclear"),
            ("activity", "replay finished"),
            ("performance", "363 trades"),
            ("chart_bot", "CHIP/USD"),
            ("detail", "04e1cafcd0f14b1e9c77"),
            ("disable_fire",),
        ],
    }


def case_refused(configs):
    return {
        "panel": {"statuses_raises": RuntimeError("the adapter refused")},
        "steps": [("build",), ("fleet", configs), ("statuses", None)],
    }


def case_empty_fleet():
    return {"panel": {}, "steps": [("build",), ("fleet", []), ("symbols", [])]}


def case_wrong_types(configs):
    return {"panel": {}, "steps": [("build",), ("fleet", configs)]}


def case_setters():
    return {
        "panel": {},
        "steps": [
            ("build",),
            ("async_loop", object()),
            ("swarm", lambda: None),
            ("topology", lambda: None),
            ("connectors", lambda: None),
            ("bot_manager", object()),
        ],
    }


# ---------------------------------------------------------------------
# The surface stands alone
# ---------------------------------------------------------------------

IMPORT_PROBE = """
import json, sys
sys.path.insert(0, {root!r})
for name in [n for n in list(sys.modules) if n.split(".")[0] == "PySide6"]:
    del sys.modules[name]
{plant}
import src.gui.main_tabs.simulator_tab_surface as s
from src.core.desktop_bridge import build_registry, handle_line, encode_frame
answer = json.loads(
    encode_frame(handle_line(json.dumps(
        {{"id": 1, "method": s.METHOD, "params": {{"reset": True}}}}
    ), build_registry())).decode("utf-8")
)
print(json.dumps({{
    "qt_modules": sorted(n for n in sys.modules if n.split(".")[0] == "PySide6"),
    "ok": answer["ok"],
    "modes": answer["result"]["modes"]["selected"] if answer["ok"] else None,
}}))
"""

PLANT_QT = "import PySide6.QtCore  # planted"


def run_probe(source):
    """Run one probe in its own process and return what it printed."""
    finished = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        timeout=300,
        cwd=str(REPO_ROOT),
        check=False,
    )
    if finished.returncode != 0:
        raise AssertionError(
            f"the probe exited {finished.returncode}: "
            f"{finished.stderr.decode(errors='replace')}"
        )
    printed = finished.stdout.decode(errors="replace").strip().splitlines()
    return json.loads(printed[-1])


def test_the_surface_answers_over_the_bridge_with_no_qt_loaded():
    """The surface needs the old interface library to answer."""
    found = run_probe(IMPORT_PROBE.format(root=str(REPO_ROOT), plant=""))
    assert found["qt_modules"] == [], found["qt_modules"]
    assert found["ok"] is True
    assert found["modes"] == surface.DEFAULT_MODE_KEY


def test_the_qt_probe_reports_a_planted_import():
    """The no-Qt probe passes whatever the surface imports."""
    found = run_probe(IMPORT_PROBE.format(root=str(REPO_ROOT), plant=PLANT_QT))
    assert found["qt_modules"], "the probe saw no PySide6 module after one was planted"


WORLD_PROBE = """
import builtins, json, sys, threading, time
sys.path.insert(0, {root!r})
import src  # the package's own cost, taken before the counters start
seen = {{"clock": 0, "opens": 0, "threads": 0, "processes": 0}}
for holder, name in (
    (time, "time"), (time, "monotonic"), (time, "perf_counter"), (time, "time_ns")
):
    original = getattr(holder, name)
    def watched(*a, _o=original, **k):
        seen["clock"] += 1
        return _o(*a, **k)
    setattr(holder, name, watched)
real_open = builtins.open
def watched_open(*a, **k):
    seen["opens"] += 1
    return real_open(*a, **k)
builtins.open = watched_open
real_start = threading.Thread.start
def watched_start(self, *a, **k):
    seen["threads"] += 1
    return real_start(self, *a, **k)
threading.Thread.start = watched_start
import subprocess as _sp
real_popen = _sp.Popen.__init__
def watched_popen(self, *a, **k):
    seen["processes"] += 1
    return real_popen(self, *a, **k)
_sp.Popen.__init__ = watched_popen
{plant}
import src.gui.main_tabs.simulator_tab_surface as s
at_import = dict(seen)
s.view_model({{"reset": True, "panel": {{}}, "chart": True, "nuclear": True,
               "build": True, "mode": "nuclear", "fleet": [],
               "activity": ["one"], "performance": ["two"]}})
print(json.dumps({{
    "at_import": at_import,
    "after_request": dict(seen),
    "qt_modules": sorted(n for n in sys.modules if n.split(".")[0] == "PySide6"),
}}))
"""

PLANT_CLOCK = "import time as _t\n_t.time()\nopen({probe!r}).close()"

NOTHING_TOUCHED = {"clock": 0, "opens": 0, "threads": 0, "processes": 0}

PACKAGE_COST_PROBE = """
import json, subprocess, sys, threading
sys.path.insert(0, {root!r})
seen = {{"threads": 0, "processes": 0}}
real_start = threading.Thread.start
def watched_start(self, *a, **k):
    seen["threads"] += 1
    return real_start(self, *a, **k)
threading.Thread.start = watched_start
real_popen = subprocess.Popen.__init__
def watched_popen(self, *a, **k):
    seen["processes"] += 1
    return real_popen(self, *a, **k)
subprocess.Popen.__init__ = watched_popen
import src
print(json.dumps(dict(seen)))
"""


def test_the_surface_touches_nothing_at_import_and_nothing_on_a_request():
    """The surface read a clock, opened a file or started a run.

    The counters start after ``src`` is imported, because the package
    itself runs one process to derive its version; charging that to this
    module would name the wrong unit.
    """
    found = run_probe(WORLD_PROBE.format(root=str(REPO_ROOT), plant=""))
    assert found["at_import"] == NOTHING_TOUCHED, found["at_import"]
    assert found["after_request"] == NOTHING_TOUCHED, found["after_request"]
    assert found["qt_modules"] == []


def test_the_package_and_not_the_surface_is_what_starts_a_process():
    """The package cost moved, so the counters above name the wrong unit."""
    found = run_probe(PACKAGE_COST_PROBE.format(root=str(REPO_ROOT)))
    assert found["processes"] >= 1, found
    assert found["threads"] >= 1, found


def test_the_world_probe_reports_a_planted_clock_read_and_file_open():
    """The world probe passes whatever the surface touches."""
    found = run_probe(
        WORLD_PROBE.format(
            root=str(REPO_ROOT),
            plant=PLANT_CLOCK.format(probe=str(SURFACE_SOURCE)),
        )
    )
    assert found["at_import"]["clock"] >= 1, found["at_import"]
    assert found["at_import"]["opens"] >= 1, found["at_import"]


def test_the_surface_imports_nothing_but_the_standard_library():
    """The surface reached for a module, so it can carry a shipped value."""
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    named = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            named.add("." * node.level + (node.module or ""))
    assert named == {"__future__", "typing"}, named


SHIPPED_PROBE = """
import json, sys
sys.path.insert(0, {root!r})
{plant}
import src.gui.main_tabs.simulator_tab_surface  # noqa: F401
print(json.dumps({{
    "shipped_loaded": "src.gui.simulator_tab.simulator_tab" in sys.modules,
}}))
"""

PLANT_SHIPPED = "import src.gui.simulator_tab.simulator_tab  # planted"


def test_importing_the_surface_never_loads_the_shipped_module():
    """The surface reads its values off the file it replaces."""
    found = run_probe(SHIPPED_PROBE.format(root=str(REPO_ROOT), plant=""))
    assert found["shipped_loaded"] is False


def test_the_shipped_module_probe_reports_a_planted_import():
    """The independence probe passes whatever the surface loads."""
    found = run_probe(SHIPPED_PROBE.format(root=str(REPO_ROOT), plant=PLANT_SHIPPED))
    assert found["shipped_loaded"] is True


def test_the_comparison_names_exactly_what_moved():
    """The comparison says a payload differs without saying where."""
    model = surface.SimulatorTabModel()
    one = surface.build_view_model(model)
    other = surface.build_view_model(model)
    assert first_difference(one, other) == ""
    other["modes"]["hint_text"] = "planted"
    assert first_difference(one, other) == (
        ".modes.hint_text: '' against 'planted'"
    ), first_difference(one, other)
    other = surface.build_view_model(model)
    other["log"]["lines"] = ["planted"]
    assert first_difference(one, other) == ".log.lines: 0 rows against 1"


# ---------------------------------------------------------------------
# Both sides, value for value and by hash
# ---------------------------------------------------------------------


def cases(tmp_path):
    """Every state the tab can be in, each driven from one stored fleet."""
    configs = stored_fleet_configs(tmp_path)
    wrong = with_stored_number(configs, "_src_stats", "current_price", "0.0212")
    return {
        "no_run": case_no_run(),
        "part_way": case_part_way(configs),
        "finished": case_finished(configs),
        "refused": case_refused(configs),
        "empty_fleet": case_empty_fleet(),
        "wrong_types": case_wrong_types(wrong),
        "setters": case_setters(),
    }


CASE_NAMES = [
    "no_run",
    "part_way",
    "finished",
    "refused",
    "empty_fleet",
    "wrong_types",
    "setters",
]


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_two_sides_hold_one_state(name, tmp_path):
    """The surface holds a different tab state than the shipped tab."""
    old, new = both(cases(tmp_path)[name])
    assert first_difference(old, new) == "", first_difference(old, new)
    assert digest(old) == digest(new), (
        f"{name}: old {digest(old)} against new {digest(new)}; "
        f"first difference {first_difference(old, new)}"
    )


def test_the_comparison_reports_two_different_real_fleets(tmp_path):
    """The comparison passes whatever the second side holds."""
    every = cases(tmp_path)
    one = drive(ShippedSide, every["part_way"])
    other = drive(SurfaceSide, every["finished"])
    assert digest(one) != digest(other)
    assert first_difference(one, other) != ""
    back_one = drive(SurfaceSide, every["part_way"])
    back_other = drive(ShippedSide, every["finished"])
    assert digest(back_one) != digest(back_other)
    assert digest(one) == digest(back_one), "the two sides disagree on part_way"
    assert digest(other) == digest(back_other), "the two sides disagree on finished"


def test_the_same_fleet_driven_twice_hashes_the_same(tmp_path):
    """Driving one case twice gave two answers."""
    case = cases(tmp_path)["finished"]
    old_once, old_again = drive(ShippedSide, case), drive(ShippedSide, case)
    new_once, new_again = drive(SurfaceSide, case), drive(SurfaceSide, case)
    assert digest(old_once) == digest(old_again), first_difference(old_once, old_again)
    assert digest(new_once) == digest(new_again), first_difference(new_once, new_again)


def test_a_whole_number_and_a_decimal_are_told_apart(tmp_path):
    """The comparison read 12 and 12.0 as one number."""
    configs = stored_fleet_configs(tmp_path)
    whole = with_stored_number(configs, "_src_stats", "total_trades", 12)
    decimal = with_stored_number(configs, "_src_stats", "total_trades", 12.0)
    one = drive(ShippedSide, case_wrong_types(whole))
    other = drive(SurfaceSide, case_wrong_types(decimal))
    assert one["table"]["rows"] == other["table"]["rows"]
    assert digest(one) == digest(other), "int and float total_trades both round to 12"
    price_whole = with_stored_number(configs, "_src_stats", "current_price", 12)
    price_decimal = with_stored_number(configs, "_src_stats", "current_price", 12.0)
    left = drive(ShippedSide, case_wrong_types(price_whole))
    right = drive(SurfaceSide, case_wrong_types(price_decimal))
    assert digest(left) == digest(right)
    assert as_text(12) != as_text(12.0), "the reader folds 12 into 12.0"


def test_two_not_a_numbers_are_told_apart(tmp_path):
    """A not-a-number compared to itself reports a difference that is not one."""
    configs = stored_fleet_configs(tmp_path)
    planted = with_stored_number(configs, "_src_stats", "current_price", float("nan"))
    old, new = both(case_wrong_types(planted))
    assert math.isnan(old["table"]["rows"][0]["stats"]["current_price"])
    assert math.isnan(new["table"]["rows"][0]["stats"]["current_price"])
    assert digest(old) == digest(new)
    one_nan, other_nan = float("nan"), float("nan")
    assert one_nan is not other_nan
    assert as_text(one_nan) == as_text(other_nan)
    assert one_nan != other_nan


# ---------------------------------------------------------------------
# Step sequences, including ones that refuse part way
# ---------------------------------------------------------------------

REFUSING_SEQUENCE = [
    ("build",),
    ("statuses", [{"bot_id": "b1", "symbol": "CHIP/USD"}]),
    ("statuses", [{"bot_id": "b2", "symbol": "SPK/USD"}, "not a status"]),
    ("activity", "after the refusal"),
]


def test_a_sequence_that_refuses_part_way_refuses_at_the_same_step():
    """The two sides refused at different steps or for different reasons."""
    spec = {"panel": {}, "steps": REFUSING_SEQUENCE}
    old, new = both(spec)
    assert old["steps"] == new["steps"], f"{old['steps']} against {new['steps']}"
    assert old["steps"][2] == [2, "statuses", "AttributeError"], old["steps"]
    assert old["steps"][3] == [3, "activity", None]


def test_the_roster_keeps_what_it_recorded_before_the_refusal():
    """A refusal part way through a roster threw away the rows already added."""
    spec = {"panel": {}, "steps": REFUSING_SEQUENCE}
    old, new = both(spec)
    for side in (old, new):
        items = side["pickers"]["active"]["items"]
        assert items[0] == [surface.ALL_BOTS_TEXT, surface.ALL_BOTS_DATA]
        assert items[1] == [surface.active_bot_item("SPK/USD", "b2"), "b2"]
        assert len(items) == 2, items
        assert side["pickers"]["active"]["blocked"] is True
    assert digest(old) == digest(new)


def test_the_step_recorder_can_report_a_refusal():
    """The step recorder writes None whatever the step did."""
    spec = {"panel": {}, "steps": [("build",), ("statuses", ["not a status"])]}
    old, new = both(spec)
    assert old["steps"][1][2] == "AttributeError"
    assert new["steps"][1][2] == "AttributeError"
    clean = {"panel": {}, "steps": [("build",), ("statuses", [])]}
    assert drive(ShippedSide, clean)["steps"][1][2] is None


REFUSAL_CASES = [
    ("statuses", ["not a status"], "AttributeError"),
    ("statuses", [12], "AttributeError"),
    ("statuses", "a string", "AttributeError"),
    ("activity", 12, "TypeError"),
    ("activity", 12.7, "TypeError"),
    ("activity", True, "TypeError"),
    ("performance", object(), None),
    ("detail", "no such bot", None),
]


@pytest.mark.parametrize("name,argument,refusal", REFUSAL_CASES)
def test_a_refusal_carries_the_same_type_on_both_sides(name, argument, refusal):
    """The two sides refused with different exception types."""
    spec = {"panel": {}, "steps": [("build",), (name, argument)]}
    old, new = both(spec)
    assert old["steps"][1][2] == refusal, old["steps"]
    assert new["steps"][1][2] == refusal, new["steps"]
    assert digest(old) == digest(new), first_difference(old, new)


# ---------------------------------------------------------------------
# Every kind of value, through the values the tab shows
# ---------------------------------------------------------------------

TEXT_VALUES = [
    ("empty", ""),
    ("zero", "0"),
    ("negative", "-1"),
    ("a_thousand_million", "1000000000"),
    ("one_billionth", "0.000000001"),
    ("unicode", UNICODE_TEXT),
    ("two_hundred_characters", LONG_TEXT),
    ("markup", MARKUP_TEXT),
    ("apostrophe", APOSTROPHE_TEXT),
    ("wrong_capitals", WRONG_CAPITALS),
    ("newline", NEWLINE_TEXT),
    ("number_where_text_belongs", "12"),
    ("infinity", "inf"),
    ("minus_infinity", "-inf"),
    ("not_a_number", "nan"),
]


@pytest.mark.parametrize("name,value", TEXT_VALUES)
def test_one_symbol_of_every_kind_reaches_both_chart_pickers(name, value):
    """A symbol of this kind reached one picker and not the other."""
    spec = {"panel": {}, "steps": [("build",), ("symbols", [value, "CHIP/USD"])]}
    old, new = both(spec)
    assert digest(old) == digest(new), first_difference(old, new)
    expected = 3 if value else 2
    assert len(old["pickers"]["chart"]["items"]) == expected, old["pickers"]["chart"]


@pytest.mark.parametrize("name,value", TEXT_VALUES)
def test_one_log_line_of_every_kind_lands_the_same_way(name, value):
    """A log line of this kind reached one pane and not the other."""
    spec = {
        "panel": {},
        "steps": [("build",), ("activity", value), ("performance", value)],
    }
    old, new = both(spec)
    assert digest(old) == digest(new), first_difference(old, new)
    assert old["log"]["text"].endswith(surface.performance_line(value))


STORED_NUMBERS = [
    ("stored_true", True),
    ("not_a_number", float("nan")),
    ("infinity", math.inf),
    ("minus_infinity", -math.inf),
    ("text", "not a price"),
    ("number_as_text", "12.7"),
    ("decimal", 12.7),
    ("whole", 12),
    ("zero", 0),
    ("negative", -1.0),
    ("a_thousand_million", 1000000000.0),
    ("one_billionth", 1e-9),
    ("huge_int", HUGE_INT),
    ("huger_int", HUGER_INT),
    ("four_hundred_digits", 10**400),
    ("unicode", UNICODE_TEXT),
    ("none", None),
]

READ_FIELDS = [
    ("_src_stats", "current_price"),
    ("_src_stats", "position_value"),
    ("_src_stats", "total_trades"),
    ("_src_scrumming_state", "anchor_target_balance"),
    ("_src_scrumming_state", "target_balance"),
    ("_src_scrumming_state", "quote_to_usd"),
]


@pytest.mark.parametrize("where,key", READ_FIELDS)
@pytest.mark.parametrize("name,value", STORED_NUMBERS)
def test_one_stored_number_of_every_kind_lands_the_same_way(
    where, key, name, value, tmp_path
):
    """A stored value of this kind reached one side and not the other."""
    configs = stored_fleet_configs(tmp_path)
    planted = with_stored_number(configs, where, key, value)
    old, new = both(case_wrong_types(planted))
    assert old["steps"] == new["steps"], f"{old['steps']} against {new['steps']}"
    assert digest(old) == digest(new), first_difference(old, new)


def test_a_stored_lot_of_the_wrong_kind_lands_the_same_way(tmp_path):
    """A lot carrying text reached one side and not the other."""
    configs = stored_fleet_configs(tmp_path)
    planted = with_stored_number(
        configs, "_src_scrumming_state", "main_lots", [{"units": "many"}]
    )
    old, new = both(case_wrong_types(planted))
    assert old["steps"][1][2] is None, old["steps"]
    assert old["steps"] == new["steps"]
    assert digest(old) == digest(new), first_difference(old, new)


def test_the_bare_reading_audit_names_the_readings_that_lose_the_row(tmp_path):
    """The table of what one stored value of the wrong kind does.

    ``_on_fleet_loaded`` catches its own failure, so a bad reading never
    raises out of the step. What the operator sees is the row: a reading
    that refuses ends the whole pass and leaves the bot table empty.
    This reads the row, not the step.
    """
    configs = stored_fleet_configs(tmp_path)
    abandoned = {}
    kept = {}
    for where, key in READ_FIELDS:
        for name, value in STORED_NUMBERS:
            planted = with_stored_number(configs, where, key, value)
            old = drive(ShippedSide, case_wrong_types(planted))
            new = drive(SurfaceSide, case_wrong_types(planted))
            assert digest(old["table"]) == digest(new["table"]), (
                key,
                name,
                first_difference(old["table"], new["table"]),
            )
            if old["table"]["rows"]:
                kept[f"{key}/{name}"] = "row built"
            else:
                abandoned[f"{key}/{name}"] = "pass abandoned"
    assert abandoned, "no stored value of the wrong kind lost the row: probe is blind"
    assert (
        kept
    ), "every stored value lost the row: the probe reports the same either way"


def test_a_bad_reading_takes_the_whole_refresh_pass_with_it(tmp_path):
    """One bad stored price left the other bot's row on screen.

    Both bots come from one stored fleet. A price the reading cannot take
    ends the pass before either row is written, so the operator loses the
    good bot too.
    """
    configs = stored_fleet_configs(tmp_path)
    good = drive(ShippedSide, case_wrong_types(configs))
    assert len(good["table"]["rows"]) == 2, good["table"]["rows"]
    planted = with_stored_number(configs, "_src_stats", "current_price", "not a price")
    old, new = both(case_wrong_types(planted))
    assert old["table"]["rows"] == [], old["table"]["rows"]
    assert old["pickers"]["active"]["items"] == [
        [surface.ALL_BOTS_TEXT, surface.ALL_BOTS_DATA]
    ]
    assert digest(old) == digest(new), first_difference(old, new)


# ---------------------------------------------------------------------
# Completeness of the comparison
# ---------------------------------------------------------------------


def flat(payload, path=""):
    """Every leaf in a payload, keyed by its own path."""
    if isinstance(payload, dict):
        found = {}
        for key, inner in payload.items():
            found.update(flat(inner, f"{path}.{key}"))
        return found
    if isinstance(payload, (list, tuple)):
        found = {}
        for at, inner in enumerate(payload):
            found.update(flat(inner, f"{path}[{at}]"))
        return found or {path: []}
    return {path: payload}


def surface_constants():
    """Every module-level constant the surface declares."""
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    named = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    named.append(target.id)
    return named


def leaves(value) -> set:
    """Every scalar inside a value, at every depth, by its own reading.

    A reading rather than the value, so ``12`` and ``12.0`` stay two
    leaves and two not-a-numbers stay one.
    """
    if isinstance(value, dict):
        found = set()
        for key, inner in value.items():
            found.update(leaves(key))
            found.update(leaves(inner))
        return found
    if isinstance(value, (list, tuple, set)):
        found = set()
        for inner in value:
            found.update(leaves(inner))
        return found
    return {repr(value)}


NOT_A_SHOWN_VALUE = ("METHOD", "ERROR_TYPES", "TAB_MODEL")


def test_every_constant_the_surface_declares_reaches_the_view_model():
    """A constant no view model carries is a value the comparison cannot see."""
    carried = leaves(surface.build_view_model(surface.SimulatorTabModel()))
    missing = {}
    for name in surface_constants():
        if name in NOT_A_SHOWN_VALUE:
            continue
        absent = leaves(getattr(surface, name)) - carried
        if absent:
            missing[name] = sorted(str(one) for one in absent)
    assert missing == {}, missing


def test_the_completeness_check_reports_a_constant_the_view_model_drops():
    """The completeness check passes whatever the view model carries."""
    carried = leaves(surface.build_view_model(surface.SimulatorTabModel()))
    planted = "a value no view model carries: 8f3a1c"
    assert leaves(planted) - carried == {repr(planted)}
    assert leaves(surface.SIM_LOG_TITLE) - carried == set()


def test_the_view_model_carries_no_key_nothing_backs():
    """A view model key with no constant and no model value behind it."""
    model = surface.SimulatorTabModel()
    built = surface.build_view_model(model)
    for section in ("identity", "chrome", "text", "modes", "wiring"):
        assert built[section], section
        for key, value in built[section].items():
            assert value is not None or key in (
                "focus_symbol",
            ), f"{section}.{key} is empty"


def test_the_names_on_the_file_and_on_the_module_agree():
    """A name on one and not the other means the module drifted from its file."""
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    on_file = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            on_file.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            on_file.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            on_file.add(node.name)
    on_module = {
        name
        for name in dir(surface)
        if not name.startswith("__")
        and name not in ("annotations", "Any", "Callable", "Optional")
    }
    assert on_file - on_module == set(), on_file - on_module
    assert on_module - on_file == set(), on_module - on_file


def test_the_name_check_reports_a_name_only_one_side_holds():
    """The name check passes whatever either side holds."""
    on_file = {"MODE_HINTS", "planted_name"}
    on_module = {"MODE_HINTS"}
    assert on_file - on_module == {"planted_name"}


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def test_the_bridge_answers_the_surface_method():
    """The renderer cannot reach the Simulator tab."""
    from src.core.desktop_bridge import build_registry, dispatch

    registry = build_registry()
    assert surface.METHOD in registry
    answered = dispatch(surface.METHOD, {"reset": True}, registry)
    assert answered["modes"]["selected"] == surface.DEFAULT_MODE_KEY


def test_the_bridge_import_list_is_in_order():
    """The import list is not the sorted list of its own names."""
    tree = ast.parse(BRIDGE_SOURCE.read_text(encoding="utf-8"))
    named = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs":
            named = [alias.name for alias in node.names]
    assert named, "no src.gui.main_tabs import found on the bridge"
    assert "simulator_tab_surface" in named
    assert named == sorted(named), named


def test_the_order_check_reports_a_list_out_of_order():
    """The order check passes whatever order the list is in."""
    out_of_order = ["spendable_profits_surface", "simulator_tab_surface"]
    assert out_of_order != sorted(out_of_order)


# ---------------------------------------------------------------------
# Order independence and the world
# ---------------------------------------------------------------------


def test_each_side_takes_its_own_sink_and_gives_it_back(tmp_path):
    """One side's pin sink outlived the drive that installed it."""
    before = signal_contract.get_sink()
    side = ShippedSide(case_no_run())
    try:
        assert signal_contract.get_sink() is side.sink
        assert signal_contract.get_sink() is not before
    finally:
        side.close()
    assert signal_contract.get_sink() is before


def test_a_side_gives_the_sink_back_after_a_refusal():
    """A refusal part way through a drive left the sink installed."""
    before = signal_contract.get_sink()
    spec = {"panel": {}, "steps": [("build",), ("statuses", ["not a status"])]}
    drive(ShippedSide, spec)
    assert signal_contract.get_sink() is before


def test_each_side_takes_its_own_settings_screen_and_gives_it_back():
    """One side's settings-screen stand-in outlived its drive."""
    before = shipped_settings.BotLiveSettingsDialog
    side = ShippedSide(case_no_run())
    try:
        assert shipped_settings.BotLiveSettingsDialog is SideDialog
    finally:
        side.close()
    assert shipped_settings.BotLiveSettingsDialog is before


def test_the_surface_creates_no_file_in_a_throwaway_home(tmp_path):
    """The surface wrote into the operator's home directory."""
    home = tmp_path / "home"
    home.mkdir()
    probe = (
        "import json, os, sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        f"os.environ['ACERVATOR_TEST_HOME'] = {str(home)!r}\n"
        f"os.environ['HOME'] = {str(home)!r}\n"
        f"os.environ['USERPROFILE'] = {str(home)!r}\n"
        "import src.gui.main_tabs.simulator_tab_surface as s\n"
        "s.view_model({'reset': True, 'panel': {}, 'build': True, "
        "'chart': True, 'nuclear': True, 'activity': ['one']})\n"
        f"print(json.dumps(sorted(str(p) for p in "
        f"__import__('pathlib').Path({str(home)!r}).rglob('*'))))\n"
    )
    found = run_probe(probe)
    assert found == [], found


def test_the_throwaway_home_probe_reports_a_planted_file(tmp_path):
    """The throwaway-home probe passes whatever the surface writes."""
    home = tmp_path / "home"
    home.mkdir()
    (home / "planted.txt").write_text("planted", encoding="utf-8")
    probe = (
        "import json\n"
        f"print(json.dumps(sorted(str(p) for p in "
        f"__import__('pathlib').Path({str(home)!r}).rglob('*'))))\n"
    )
    found = run_probe(probe)
    assert len(found) == 1, found


def test_two_surface_models_do_not_share_state():
    """Two tabs built in one process shared a dropdown or a log."""
    one = surface.SimulatorTabModel()
    other = surface.SimulatorTabModel()
    one.log_activity("only on the first")
    one.refresh_active_bot_roster([{"bot_id": "b1", "symbol": "CHIP/USD"}])
    assert other.log_pane.lines == []
    assert other.active_bot_picker.count() == 1
    assert one.active_bot_picker.count() == 2


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------

CONTROL_RULE = "QWidget { background: #7d1a4a; }"


def picture_payload(lines=("replay started",), mode=surface.NUCLEAR_KEY, paused=False):
    """The view model after one drive, stamped."""
    model = surface.SimulatorTabModel()
    model.set_fleet_panel(surface.FleetPanel())
    model.select_mode(mode)
    for line in lines:
        model.log_activity(line)
    model.on_activity_paused(paused)
    return sealed(surface.build_view_model(model))


def shipped_tab(mode=surface.NUCLEAR_KEY, lines=("replay started",)):
    """A fresh shipped tab, driven the same way and kept alive."""
    app()
    tab = shipped.SimulatorTab()
    LIVE_TABS.append(tab)
    tab._mode_selector.setCurrentIndex(tab._mode_selector.findData(mode))
    for line in lines:
        tab.log_activity(line)
    return tab


def taken_out(widget):
    """One live child, taken out of its parent so it can be rendered."""
    widget.setParent(None)
    return widget


def old_section_label():
    app()
    return shipped._section_label(surface.SIM_LOG_TITLE)


def new_section_label(payload):
    payload = unaltered(payload)
    from PySide6.QtWidgets import QLabel

    app()
    label = QLabel(payload["text"]["sim_log_title"])
    label.setStyleSheet(payload["identity"]["section_label_style"])
    return label


def old_pause_button():
    return taken_out(shipped_tab()._activity_pause_btn)


def new_pause_button(payload):
    payload = unaltered(payload)
    from PySide6.QtWidgets import QPushButton

    app()
    button = QPushButton(payload["log"]["pause_button_text"])
    button.setCheckable(payload["text"]["pause_checkable"])
    button.setStyleSheet(payload["text"]["pause_style"])
    return button


def old_mode_hint():
    return taken_out(shipped_tab()._mode_hint)


def new_mode_hint(payload):
    payload = unaltered(payload)
    from PySide6.QtWidgets import QLabel

    app()
    label = QLabel(payload["modes"]["hint_text"])
    label.setStyleSheet(payload["text"]["mode_hint_style"])
    return label


def old_log_pane(lines):
    return taken_out(shipped_tab(lines=lines).simulator_log)


def new_log_pane(payload):
    payload = unaltered(payload)
    from PySide6.QtWidgets import QPlainTextEdit

    app()
    pane = QPlainTextEdit()
    pane.setReadOnly(payload["text"]["log_read_only"])
    pane.setMaximumBlockCount(payload["log"]["maximum_blocks"])
    pane.setStyleSheet(payload["text"]["log_style"])
    for line in payload["log"]["lines"]:
        pane.appendPlainText(line)
    return pane


def old_mode_selector():
    return taken_out(shipped_tab()._mode_selector)


def new_mode_selector(payload):
    payload = unaltered(payload)
    from PySide6.QtWidgets import QComboBox

    app()
    box = QComboBox()
    box.setMinimumWidth(payload["modes"]["selector_min_width"])
    box.setToolTip(payload["modes"]["selector_tooltip"])
    for label, key, _tip in payload["modes"]["rows"]:
        box.addItem(label, key)
    box.setCurrentIndex(payload["modes"]["index"])
    return box


SKIN_ELEMENTS = {
    "section_label": (old_section_label, new_section_label),
    "pause_button": (old_pause_button, new_pause_button),
    "mode_hint": (old_mode_hint, new_mode_hint),
    "log_pane": (lambda: old_log_pane(("replay started",)), new_log_pane),
    "mode_selector": (old_mode_selector, new_mode_selector),
}


@pytest.mark.parametrize("name", sorted(SKIN_ELEMENTS))
def test_the_two_sides_carry_one_skin(name):
    """The surface painted a different skin than the shipped tab."""
    app()
    build_old, build_new = SKIN_ELEMENTS[name]
    assert_same_skin(
        build_old_side=build_old,
        build_new_side=lambda: build_new(picture_payload()),
        size=PIXEL_SIZE,
        control_rule=CONTROL_RULE,
        note=f"{name}, {'real fonts' if has_real_fonts() else 'no fonts'}",
    )


@pytest.mark.parametrize("name", sorted(SKIN_ELEMENTS))
def test_each_painted_element_shows_more_than_one_colour(name):
    """An element that paints one colour cannot report a difference."""
    app()
    build_old, build_new = SKIN_ELEMENTS[name]
    old_count = assert_picture_can_report(
        render_offscreen(build_old(), PIXEL_SIZE), note=f"{name}, old side"
    )
    new_count = assert_picture_can_report(
        render_offscreen(build_new(picture_payload()), PIXEL_SIZE),
        note=f"{name}, new side",
    )
    assert old_count == new_count, f"{name}: {old_count} against {new_count}"
    assert old_count >= 2, (name, old_count)


TEXT_PAIRS = {
    "section_label": (
        lambda: shipped._section_label(surface.SIM_LOG_TITLE),
        lambda: shipped._section_label(surface.GATE_TITLE),
        surface.SIM_LOG_TITLE,
        surface.GATE_TITLE,
    ),
    "pause_button": (
        lambda: new_pause_button(picture_payload()),
        lambda: new_pause_button(picture_payload(paused=True)),
        surface.PAUSE_TEXT,
        surface.RESUME_TEXT,
    ),
    "mode_selector": (
        lambda: new_mode_selector(picture_payload(mode=surface.VALIDATION_KEY)),
        lambda: new_mode_selector(picture_payload(mode=surface.NUCLEAR_KEY)),
        surface.SIM_MODES[0][0],
        surface.SIM_MODES[2][0],
    ),
    "mode_hint": (
        lambda: new_mode_hint(picture_payload(mode=surface.VALIDATION_KEY)),
        lambda: new_mode_hint(picture_payload(mode=surface.NUCLEAR_KEY)),
        surface.MODE_HINTS[surface.VALIDATION_KEY],
        surface.MODE_HINTS[surface.NUCLEAR_KEY],
    ),
    "log_pane": (
        lambda: new_log_pane(picture_payload(lines=("aaa",))),
        lambda: new_log_pane(picture_payload(lines=("bbb",))),
        "aaa",
        "bbb",
    ),
}

TEXT_NEEDS_FONTS = ("log_pane", "mode_hint")


@pytest.mark.parametrize("name", sorted(TEXT_PAIRS))
def test_a_changed_text_reaches_a_pixel_or_is_read_off_both_sides(name):
    """The picture set cannot see this element's text change.

    On a host with no fonts the log pane and the mode hint paint the same
    picture whatever they were told to show, so for those two the claim
    is proved by reading the two texts rather than by a picture. Every
    other element moves a pixel on either host.
    """
    app()
    build_one, build_other, one_text, other_text = TEXT_PAIRS[name]
    assert one_text != other_text
    if name in TEXT_NEEDS_FONTS and not has_real_fonts():
        pytest.skip(f"{name} paints no glyph on a host with no fonts")
    assert_cases_paint_differently(
        old_side=render_offscreen(build_one(), PIXEL_SIZE),
        new_side=render_offscreen(build_other(), PIXEL_SIZE),
        note=f"{name}, {'real fonts' if has_real_fonts() else 'no fonts'}",
    )


def test_every_element_pair_carries_two_different_product_texts():
    """Two elements in a pair carry one text, so no check of them can report.

    Read off both sides rather than off a render, because whether a text
    change moves a pixel is a fact about the host's fonts and not about
    the product.
    """
    for name, (_one, _other, one_text, other_text) in TEXT_PAIRS.items():
        assert one_text != other_text, name
        assert one_text and other_text, name
    for name in TEXT_NEEDS_FONTS:
        assert name in TEXT_PAIRS, name


def test_the_picture_comparison_reports_two_different_real_log_panes():
    """The picture comparison passes whatever the second side paints."""
    app()
    short = ("a",)
    long_lines = (LONG_TEXT, UNICODE_TEXT, MARKUP_TEXT)
    assert_cases_paint_differently(
        old_side=render_offscreen(old_log_pane(short), LOG_PIXEL_SIZE),
        new_side=render_offscreen(
            new_log_pane(picture_payload(lines=long_lines)), LOG_PIXEL_SIZE
        ),
        note="one short line against three long ones",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """The seal lets a changed payload reach a render."""
    payload = picture_payload()
    payload["log"]["pause_button_text"] = "planted"
    with pytest.raises(AssertionError):
        new_pause_button(payload)


# ---------------------------------------------------------------------
# What the shipped tab does that the model must not
# ---------------------------------------------------------------------


def test_the_pause_button_holds_the_activity_stream_only():
    """The pause button holds both streams, or neither.

    The shipped button sets one flag. A model that held both would show
    the operator a pane that stops when the shipped one keeps writing.
    """
    spec = {
        "panel": {},
        "steps": [
            ("build",),
            ("pause", True),
            ("activity", "held"),
            ("performance", "still written"),
        ],
    }
    old, new = both(spec)
    assert old["log"]["activity_paused"] is True
    assert old["log"]["performance_paused"] is False
    assert old["log"]["text"] == surface.performance_line("still written")
    assert digest(old) == digest(new), first_difference(old, new)


def test_the_two_log_names_reach_one_pane():
    """The merged pane split back into two."""
    old = drive(ShippedSide, {"panel": {}, "steps": [("build",)]})
    assert old["log"]["merged"] is True


def test_the_mode_pin_reads_the_page_back_off_the_stack(tmp_path):
    """The mode pin reported a page the stack is not on."""
    old, new = both({"panel": {}, "steps": [("build",), ("mode", "nuclear")]})
    assert digest(old["pins"]) == digest(new["pins"]), first_difference(
        old["pins"], new["pins"]
    )
    last = old["pins"][-1]
    assert last["name"] == surface.MODE_PIN
    assert last["actual"] == surface.NUCLEAR_PAGE_INDEX
    assert last["expected"] == surface.NUCLEAR_PAGE_INDEX
    assert last["context"]["mode"] == "nuclear"


def test_the_log_pin_carries_the_stream_that_produced_the_line():
    """The log pin lost the stream identity a pane merge destroys."""
    spec = {
        "panel": {},
        "steps": [("build",), ("activity", "one"), ("performance", "two")],
    }
    old, new = both(spec)
    streams = [row["actual"] for row in old["pins"] if row["name"] == surface.LOG_PIN]
    assert streams == [surface.ACTIVITY_STREAM, surface.PERFORMANCE_STREAM]
    assert digest(old["pins"]) == digest(new["pins"])


def test_the_pin_recorder_can_report_a_missing_pin():
    """The pin comparison passes whatever either side emits."""
    one = drive(ShippedSide, {"panel": {}, "steps": [("build",), ("activity", "a")]})
    other = drive(ShippedSide, {"panel": {}, "steps": [("build",)]})
    assert len(one["pins"]) > len(other["pins"])


# ---------------------------------------------------------------------
# The connections the tab makes when it is built
# ---------------------------------------------------------------------


def test_the_tab_builds_two_expand_buttons_from_one_wiring_line():
    """One expand button, or three: the titled-box wiring changed.

    Both halves of the indicator pane are titled by one call site, so the
    connection it makes happens twice at run time.
    """
    from PySide6.QtWidgets import QPushButton

    app()
    tab = shipped_tab(mode=surface.VALIDATION_KEY, lines=())
    found = [
        one
        for one in tab.findChildren(QPushButton)
        if one.text() == surface.EXPAND_TEXT
    ]
    assert len(found) == 2, [one.text() for one in tab.findChildren(QPushButton)]


def test_the_surface_declares_every_connection_the_tab_makes():
    """The surface names a different set of connections than the tab makes."""
    assert surface.CONNECTIONS_AT_BUILD == len(surface.ACTIONS)
    assert set(surface.ACTIONS) == {
        "mode_selector.currentIndexChanged",
        "fleet_replay.fleetLoaded",
        "chart_expand_button.clicked",
        "voting_expand_button.clicked",
        "chart_bot_picker.currentIndexChanged",
        "activity_pause_button.toggled",
    }


CONNECTED_SIGNALS = ["mode", "chart_bot", "pause", "fleet"]


@pytest.mark.parametrize("name", CONNECTED_SIGNALS)
def test_driving_one_connected_signal_moves_the_tab(name, tmp_path):
    """A connection the tab used to make is gone."""
    configs = stored_fleet_configs(tmp_path)
    argument = {
        "mode": surface.NUCLEAR_KEY,
        "chart_bot": "CHIP/USD",
        "pause": True,
        "fleet": configs,
    }[name]
    before = drive(ShippedSide, {"panel": {}, "steps": [("build",)]})
    after = drive(ShippedSide, {"panel": {}, "steps": [("build",), (name, argument)]})
    assert digest(before) != digest(after), name


def test_an_unconnected_signal_moves_nothing():
    """The connection counter reports movement whatever is driven.

    The active-bot dropdown carries no connection, so selecting in it must
    leave the tab exactly where it was.
    """
    app()
    side = ShippedSide({"panel": {}})
    try:
        side.step(0, "build")
        side.step(1, "statuses", [{"bot_id": "b1", "symbol": "CHIP/USD"}])
        before = digest(side.payload())
        side.tab._active_bot_picker.setCurrentIndex(1)
        side.steps.pop()
        side.steps.append([1, "statuses", None])
        after = side.payload()
        assert after["pickers"]["active"]["selected"] == "b1"
        assert digest(after) != before, "the payload never sees the selection"
        side.tab._active_bot_picker.setCurrentIndex(0)
        assert digest(side.payload()) == before
    finally:
        side.close()
