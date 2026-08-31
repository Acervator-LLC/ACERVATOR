"""The Settings tab of the Live Bot Settings window, both sides at once.

A failure here means the Qt-free surface and the shipped tab disagree:
one of them seeds a control with a different value, puts a row in a
different place, wires a different action, or refuses a stored value
where the other accepts it.

Every case drives the shipped mixin and the surface in one run, from one
input, and compares value for value and by hash. A stored value that
makes one side refuse must make the other side refuse with the same type
of exception; the wording is never compared.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.host_fonts import load_run_fonts
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)
from src.gui.main_tabs import live_settings_tab_surface as surface

REPO = Path(__file__).resolve().parents[1]
SHIPPED = REPO / "src" / "gui" / "live_settings" / "settings_tab.py"
SURFACE_FILE = REPO / "src" / "gui" / "main_tabs" / "live_settings_tab_surface.py"

PICTURE_SIZE = (760, 900)
CONTROL_RULE = "QGroupBox { border: 3px solid #7a1414; background: #201014; }"

_alive: list[object] = []


def hold(widget):
    """Keep `widget` alive for the run so no render reads a freed object."""
    _alive.append(widget)
    return widget


def canonical(value):
    """`value` as nested lists of text, ordered so a swap changes it."""
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: repr(item[0]))
        return [[repr(key), canonical(inner)] for key, inner in pairs]
    if isinstance(value, (list, tuple)):
        return [canonical(inner) for inner in value]
    return repr(value)


def digest(payload) -> str:
    """SHA-256 over every value a payload carries, at every depth.

    Uses ``repr`` at the leaves, so a whole number and a decimal of the
    same size hash apart and a not-a-number hashes equal to itself.
    """
    return hashlib.sha256(repr(canonical(payload)).encode("utf-8")).hexdigest()


BASE_CONFIG = {
    "visibility": "orderbook",
    "aggressive_trading": False,
    "stack_mode": False,
    "split_distance": 1.0,
    "stack_tranche_count_target": 3,
    "stack_spacing_mode": "linear",
    "personal_hold_qty": 0.0,
    "scrumming_interval_pct": 1.5,
    "bb_tolerance_pct": 1.0,
    "bb_landing_strip_candles": 3,
    "ta_timeframe": "1h",
    "target_balance": 100.0,
    "exchange_id": "coinbase",
    "target_asset": "AERO",
    "max_entry_price": None,
    "min_entry_price": None,
    "trading_fee_pct": 0.6,
    "max_target_growth_pct": 1.0,
    "profit_folding_active": True,
    "scrum_detect_pct": 75,
    "scrum_fire_pct": 1.0,
    "bb_midline_gate": True,
    "scrum_read_rate_min": 5,
    "band_travel_pct": 0,
    "bb_bullseye_check": True,
    "scrum_fold_pct": 100,
    "tranche_despawn_days": 0,
    "wire_inflow_stack_pct": 1.0,
    "hedge_rebalance_active": False,
    "hedge_balance": 0.0,
    "circuit_breaker_soft_pct": 25.0,
    "circuit_breaker_hard_pct": 35.0,
    "circuit_breaker_cooldown_candles": 3,
    "max_cartridge_size_pct": 10.0,
    "max_cartridge_smart": False,
    "max_cartridge_smart_ceiling_pct": 30.0,
    "position_ceiling_enabled": False,
    "position_ceiling_multiple": 5.0,
    "detonation_enabled": False,
    "detonation_timeframe": "1d",
    "detonation_confidence_min": 0.75,
    "scrum_require_ta_bullish": True,
    "scrum_hold_in_uptrend": True,
    "scrum_defer_to_htf": True,
    "fold_require_ta_bearish": True,
    "fold_defer_to_htf": True,
    "profit_route": "fold_to_target",
    "profit_route_bot_id": "",
    "extractor_chunk_size_usd": 100.0,
    "extractor_artillery_size_usd": 5.0,
    "extractor_scan_top_n": 8,
    "extractor_scan_refresh_candles": 60,
    "extractor_pool_reserve_pct": 50.0,
    "extractor_exit_pct": 100.0,
    "extractor_max_compounding_tier": 3,
    "extractor_max_cost_basis_multiple": 2.0,
    "extractor_alt_targets": [],
}

BASE_BOT = {
    "bot_id": "abcdef1234567890",
    "symbol": "AERO/USDC",
    "live_target": 0.0,
    "anchor_target": 0.0,
    "surplus": 0.0,
    "budget": 0.0,
    "consumed": 0.0,
    "tranches": [],
}

BASE_MARKET = {
    "pairs": {},
    "btc_usd": 0.0,
    "eth_usd": 0.0,
}


def case(
    mode: str = "scrumming",
    config: dict | None = None,
    bot: dict | None = None,
    market: dict | None = None,
) -> dict:
    """One input both sides are driven with."""
    return {
        "mode": mode,
        "config": {**BASE_CONFIG, **(config or {})},
        "bot": {**BASE_BOT, **(bot or {})},
        "market": {**BASE_MARKET, **(market or {})},
    }


class _Mode:
    """The bot mode, reachable through ``value`` as the shipped enum is."""

    def __init__(self, value):
        self.value = value


class ShippedConfig:
    """The config object the shipped tab reads, from a plain mapping.

    A field whose value is ``ABSENT`` is genuinely not set, so the tab's
    own fallback decides; every other field is set as an attribute.
    """

    def __init__(self, mode, fields):
        self.mode = _Mode(mode)
        for name, value in fields.items():
            if value is not ABSENT:
                setattr(self, name, value)


ABSENT = object()


class ShippedBot:
    """The running bot the shipped tab reads, from plain values."""

    def __init__(
        self,
        mode,
        config_fields,
        bot_fields,
        has_self_destruct=True,
        has_reset=True,
        reset_applied=None,
        reset_raises=None,
    ):
        self.config = ShippedConfig(mode, config_fields)
        self.bot_id = bot_fields["bot_id"]
        self.config.symbol = bot_fields["symbol"]
        self._target_balance = bot_fields["live_target"]
        self._anchor_target_balance = bot_fields["anchor_target"]
        self._standing_surplus_usd = bot_fields["surplus"]
        self.cycle_growth_cap_usd = bot_fields["budget"]
        self._fold_cycle_cap_consumed = bot_fields["consumed"]
        self._fold_tranches = list(bot_fields["tranches"])
        self.reset_applied = reset_applied
        self.reset_raises = reset_raises
        self.reset_scopes: list = []
        self.destruct_phrases: list = []
        if has_self_destruct:
            self.self_destruct = self._self_destruct
        if has_reset:
            self.reset_circuit_breaker = self._reset_circuit_breaker

    def _self_destruct(self, confirmation_token=None):
        self.destruct_phrases.append(confirmation_token)
        return ["self_destruct", confirmation_token]

    def _reset_circuit_breaker(self, scope):
        if self.reset_raises is not None:
            raise self.reset_raises
        self.reset_scopes.append(scope)
        return {"applied": list(self.reset_applied or [])}


class FakePair:
    """One market pair the stubbed scout hands back."""

    def __init__(self, pct_24h):
        self.pct_24h = pct_24h


class FakeScout:
    """The market-pair scout, answering from a plain table of pairs."""

    def __init__(self, pairs):
        self.pairs = dict(pairs)
        self.asked: list = []

    def get_pair(self, base, quote, exchange_id=None):
        self.asked.append([base, quote, exchange_id])
        found = self.pairs.get((base, quote))
        return FakePair(found) if found is not None else None


class FakeRates:
    """The currency-rate monitor, holding one BTC and one ETH price."""

    def __init__(self, btc_usd, eth_usd):
        self.btc_usd = btc_usd
        self.eth_usd = eth_usd

    def snapshot(self):
        return self


RECORDED_SETTERS = (
    "setValue",
    "setChecked",
    "setCurrentIndex",
    "setText",
    "setRange",
    "setDecimals",
    "setSuffix",
    "setPrefix",
    "setSingleStep",
    "setSpecialValueText",
    "setPlaceholderText",
    "setToolTip",
    "addItem",
    "addItems",
)

WIDGET_NAMES = (
    "QDoubleSpinBox",
    "QSpinBox",
    "QCheckBox",
    "QComboBox",
    "QLineEdit",
    "QLabel",
    "QPushButton",
)


def make_recorder(base):
    """A subclass of `base` that keeps the arguments it was asked for.

    Every name in ``RECORDED_SETTERS`` is declared by one of the five
    widget classes this wraps, so nothing here overrides a name the
    class does not carry. The base call still runs, so a value the
    platform refuses raises exactly as it does in the shipped tab.
    """

    class Recorder(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.asked: dict = {}
            self.item_list: list = []
            self.built_with = list(args)

        def _keep(self, name, args):
            if hasattr(self, "asked"):
                self.asked.setdefault(name, list(args))

    def bind(name):
        def recorded(self, *args, **kwargs):
            self._keep(name, args)
            if hasattr(self, "item_list"):
                if name == "addItem":
                    self.item_list.append(list(args))
                if name == "addItems":
                    self.item_list.extend([one] for one in args[0])
            return getattr(base, name)(self, *args, **kwargs)

        return recorded

    for setter in RECORDED_SETTERS:
        if hasattr(base, setter):
            setattr(Recorder, setter, bind(setter))
    Recorder.__name__ = f"Recording{base.__name__}"
    return Recorder


def swap_in_recorders(monkeypatch, module):
    """Point the shipped module's widget names at recording subclasses.

    ``raising=True`` throughout: a name the module does not carry must
    fail here rather than be created, which would swap nothing while
    reading as a swap.
    """
    swapped = {}
    from PySide6 import QtWidgets

    for name in WIDGET_NAMES:
        base = getattr(QtWidgets, name)
        recorder = make_recorder(base)
        monkeypatch.setattr(module, name, recorder, raising=True)
        swapped[name] = recorder
    return swapped


def stub_market(monkeypatch, scout, rates):
    """Point the scout and the rate monitor at values, not at a network.

    Both are read through their own modules at call time, so the swap
    lands on the module attribute the shipped tab imports.
    """
    from src.exchange import currency_rate_monitor, market_pairs_scout

    monkeypatch.setattr(market_pairs_scout, "get_scout", lambda: scout, raising=True)
    monkeypatch.setattr(
        currency_rate_monitor,
        "get_currency_monitor",
        lambda: rates,
        raising=True,
    )


def app():
    """The one application object, with this run's font choice applied.

    Building a Qt widget with no application object ends the process
    without a traceback, and a run that dies that way prints nothing at
    all, so every path that builds a widget passes through here first.
    """
    from PySide6.QtWidgets import QApplication

    load_run_fonts()
    return QApplication.instance()


def shipped_host(bot):
    """A real window carrying the shipped mixin, ready to build its tab."""
    from PySide6.QtWidgets import QWidget

    app()

    from src.gui.live_settings.settings_tab import SettingsTabMixin

    class Host(QWidget, SettingsTabMixin):
        def __init__(self):
            super().__init__()
            self.setAccessibleName("Live Bot Settings test host")
            self._bot = bot
            self.changed: list = []
            self.forms = 0

        def _configure_form(self, form):
            self.forms += 1

        def _mark_changed(self, field, value):
            self.changed.append([field, value])

    return hold(Host())


def scout_and_rates(market):
    """The two stand-ins one case drives the cross-pair rows with."""
    return (
        FakeScout(market["pairs"]),
        FakeRates(market["btc_usd"], market["eth_usd"]),
    )


def named_widgets(host):
    """Every recorded control the host built, keyed by its control name.

    Read off the host's own attributes, so a build that refused part way
    still names every control it managed to build.
    """
    found = {}
    for attribute, value in vars(host).items():
        if hasattr(value, "asked") and attribute.startswith("_"):
            found[attribute[1:]] = value
    return found


def form_rows(tab):
    """Every labelled row of every form on the tab, in painted order."""
    from PySide6.QtWidgets import QFormLayout, QGroupBox

    rows = []
    for group in tab.findChildren(QGroupBox):
        layout = group.layout()
        if not isinstance(layout, QFormLayout):
            continue
        for index in range(layout.rowCount()):
            label_item = layout.itemAt(index, QFormLayout.ItemRole.LabelRole)
            label = None
            if label_item is not None and label_item.widget() is not None:
                label = label_item.widget().text()
            rows.append([group.title(), label])
    return rows


def label_text_for(tab, wanted):
    """The text of the field beside the form row labelled `wanted`."""
    from PySide6.QtWidgets import QFormLayout, QGroupBox

    for group in tab.findChildren(QGroupBox):
        layout = group.layout()
        if not isinstance(layout, QFormLayout):
            continue
        for index in range(layout.rowCount()):
            label_item = layout.itemAt(index, QFormLayout.ItemRole.LabelRole)
            if label_item is None or label_item.widget() is None:
                continue
            if label_item.widget().text() != wanted:
                continue
            field = layout.itemAt(index, QFormLayout.ItemRole.FieldRole)
            if field is None or field.widget() is None:
                return None
            return field.widget().text()
    return None


def group_titles(tab):
    """Every boxed group title on the tab, in painted order."""
    from PySide6.QtWidgets import QGroupBox

    return [group.title() for group in tab.findChildren(QGroupBox)]


READ_ONLY_LABELS = (
    "Live target (traded against):",
    "Standing surplus:",
    "Cycle growth budget:",
    "Over-cap tranches:",
    "Target BTC:",
    "Target ETH:",
)


def old_snapshot(monkeypatch, spec):
    """Drive the shipped tab once and return what it painted.

    Returns ``("built", payload)`` or ``("refused", exception type name)``
    so a stored value that stops the tab being built is compared by the
    type of its refusal rather than by any wording.
    """
    import src.gui.live_settings.settings_tab as shipped

    swap_in_recorders(monkeypatch, shipped)
    scout, rates = scout_and_rates(spec["market"])
    stub_market(monkeypatch, scout, rates)
    bot = ShippedBot(spec["mode"], spec["config"], spec["bot"])
    host = shipped_host(bot)
    try:
        tab = hold(host._create_settings_tab())
    except BaseException as exc:
        return ("refused", type(exc).__name__, named_widgets(host))
    stop_timer(host)
    controls = named_widgets(host)
    payload = {
        "group_titles": group_titles(tab),
        "rows": form_rows(tab),
        "spin_values": {},
        "check_values": {},
        "combo_index": {},
        "line_values": {},
        "combo_items": {},
        "ranges": {},
        "decimals": {},
        "suffix": {},
        "prefix": {},
        "step": {},
        "special_value_text": {},
        "check_text": {},
        "tooltips": {},
        "placeholder": {},
        "read_only_texts": {
            wanted: label_text_for(tab, wanted) for wanted in READ_ONLY_LABELS
        },
        "forms_configured": host.forms,
        "changed": [list(one) for one in host.changed],
    }
    fill_control_payload(payload, controls)
    add_local_tooltips(payload, tab)
    return ("built", payload, controls)


def fill_control_payload(payload, controls):
    """Copy every recorded request off the controls into `payload`."""
    from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QSpinBox
    from PySide6.QtWidgets import QDoubleSpinBox

    scalar = {
        "setToolTip": "tooltips",
        "setDecimals": "decimals",
        "setSuffix": "suffix",
        "setPrefix": "prefix",
        "setSingleStep": "step",
        "setSpecialValueText": "special_value_text",
        "setPlaceholderText": "placeholder",
    }
    for name, widget in controls.items():
        asked = widget.asked
        for setter, key in scalar.items():
            if setter in asked:
                payload[key][name] = asked[setter][0]
        if "setRange" in asked:
            payload["ranges"][name] = list(asked["setRange"])
        if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
            payload["spin_values"][name] = first_argument(asked, "setValue")
        elif isinstance(widget, QCheckBox):
            payload["check_values"][name] = first_argument(asked, "setChecked")
            payload["check_text"][name] = widget.built_with[0]
        elif isinstance(widget, QComboBox):
            payload["combo_index"][name] = first_argument(asked, "setCurrentIndex", 0)
            payload["combo_items"][name] = [list(one) for one in widget.item_list]
        elif isinstance(widget, QLineEdit):
            payload["line_values"][name] = first_argument(asked, "setText")


def first_argument(asked, setter, missing=None):
    """The first argument one setter was asked for, or `missing`."""
    recorded = asked.get(setter)
    return recorded[0] if recorded else missing


def stop_timer(host):
    """Stop the 5 s cross-pair refresh so no timer outlives this test."""
    timer = getattr(host, "_denom_refresh_timer", None)
    if timer is not None:
        timer.stop()


def label_tooltip_for(tab, wanted):
    """The tooltip of the field beside the form row labelled `wanted`."""
    from PySide6.QtWidgets import QFormLayout, QGroupBox

    for group in tab.findChildren(QGroupBox):
        layout = group.layout()
        if not isinstance(layout, QFormLayout):
            continue
        for index in range(layout.rowCount()):
            label_item = layout.itemAt(index, QFormLayout.ItemRole.LabelRole)
            if label_item is None or label_item.widget() is None:
                continue
            if label_item.widget().text() != wanted:
                continue
            field = layout.itemAt(index, QFormLayout.ItemRole.FieldRole)
            if field is None or field.widget() is None:
                return None
            return field.widget().toolTip()
    return None


LOCAL_LABEL_TOOLTIPS = {
    "live_lbl": "Live target (traded against):",
    "surplus_lbl": "Standing surplus:",
    "over_lbl": "Over-cap tranches:",
}

SKIPPED_GROUPS = (surface.DANGER_GROUP, surface.ALT_TARGETS_GROUP)

KIND_BUCKET = {
    surface.DOUBLE_SPIN: "spin_values",
    surface.SPIN: "spin_values",
    surface.CHECK: "check_values",
    surface.COMBO_DATA: "combo_index",
    surface.COMBO_TEXT: "combo_index",
    surface.LINE: "line_values",
}


def new_model(spec):
    """The surface model for one case, with its own stand-ins."""
    from src.exchange.timeframes import available_timeframes

    config = surface.BotConfigSource(
        mode=spec["mode"],
        **{k: v for k, v in spec["config"].items() if v is not ABSENT},
    )
    bot = surface.BotSource(
        config=config,
        bot_id=spec["bot"]["bot_id"],
        symbol=spec["bot"]["symbol"],
        live_target=spec["bot"]["live_target"],
        anchor_target=spec["bot"]["anchor_target"],
        surplus=spec["bot"]["surplus"],
        budget=spec["bot"]["budget"],
        consumed=spec["bot"]["consumed"],
        tranches=spec["bot"]["tranches"],
    )
    return surface.LiveSettingsTabModel(
        bot=bot,
        scout=surface.ScoutSource(spec["market"]["pairs"]),
        rates=surface.RateSource(spec["market"]["btc_usd"], spec["market"]["eth_usd"]),
        timeframes=available_timeframes,
    )


def new_snapshot(spec):
    """Drive the surface once and return what it says the tab paints.

    Same two-part answer as ``old_snapshot``: built with a payload, or
    refused with the type name of the exception that stopped it.
    """
    model = new_model(spec)
    try:
        model.build()
    except BaseException as exc:
        return ("refused", type(exc).__name__, model)
    view = surface.build_view_model(model)
    titles = dict(view["groups"])
    payload = {
        "group_titles": [title for _, title in view["groups"]],
        "rows": [
            [titles[group], label]
            for group, label, _ in view["rows"]
            if group not in SKIPPED_GROUPS
        ],
        "spin_values": {},
        "check_values": {},
        "combo_index": {},
        "line_values": {},
        "combo_items": {},
        "ranges": {},
        "decimals": {},
        "suffix": {},
        "prefix": {},
        "step": {},
        "special_value_text": {},
        "check_text": {},
        "tooltips": {},
        "placeholder": {},
        "read_only_texts": read_only_texts_from(view),
        "forms_configured": view["forms"]["configured"],
        "changed": [list(one) for one in view["changed"]],
    }
    for spec_row in view["control_specs"]:
        name = spec_row["name"]
        if name not in view["values"]:
            continue
        bucket = KIND_BUCKET[spec_row["kind"]]
        if bucket == "combo_index":
            payload[bucket][name] = view["combo_index"][name]
        else:
            payload[bucket][name] = view["values"][name]
        payload["combo_items"].update(combo_items_for(spec_row, view))
        for key, source in (
            ("ranges", "range"),
            ("decimals", "decimals"),
            ("suffix", "suffix"),
            ("prefix", "prefix"),
            ("step", "step"),
            ("special_value_text", "special_value_text"),
            ("check_text", "text"),
            ("placeholder", "placeholder"),
        ):
            if source in spec_row:
                value = spec_row[source]
                payload[key][name] = list(value) if key == "ranges" else value
    payload["tooltips"] = dict(view["tooltips_applied"])
    return ("built", payload, model)


def combo_items_for(spec_row, view):
    """The item list one combo was filled with, in the recorded shape."""
    name = spec_row["name"]
    if spec_row["reading"] == surface.TIMEFRAME_READING:
        return {name: [[one] for one in view["timeframe_items"]]}
    if spec_row["kind"] == surface.COMBO_DATA:
        return {name: [list(one) for one in spec_row["items"]]}
    if spec_row["kind"] == surface.COMBO_TEXT:
        return {name: [[one] for one in spec_row["items"]]}
    return {}


def read_only_texts_from(view):
    """The six read-only row texts, keyed by the label beside each."""
    return {
        "Live target (traded against):": (
            view["compound_row"][0] if view["compound_row"] else None
        ),
        "Standing surplus:": (view["surplus_row"][0] if view["surplus_row"] else None),
        "Cycle growth budget:": (view["budget_row"][0] if view["budget_row"] else None),
        "Over-cap tranches:": (
            view["over_cap_row"][0] if view["over_cap_row"] else None
        ),
        "Target BTC:": view["denom_rows"].get("BTC", [None])[0],
        "Target ETH:": view["denom_rows"].get("ETH", [None])[0],
    }


def add_local_tooltips(payload, tab):
    """Copy the three read-only row tooltips into an old-side payload."""
    for name, row_label in LOCAL_LABEL_TOOLTIPS.items():
        found = label_tooltip_for(tab, row_label)
        if found:
            payload["tooltips"][name] = found


def drive_both(monkeypatch, spec):
    """Drive the shipped tab and the surface once each, from one input."""
    old = old_snapshot(monkeypatch, spec)
    new = new_snapshot(spec)
    return old, new


def assert_same(old, new, note=""):
    """Fail unless both sides built the same tab, or refused alike."""
    assert old[0] == new[0], (
        f"one side built the tab and the other refused{note}: "
        f"shipped {old[0]} {old[1] if old[0] == 'refused' else ''}, "
        f"surface {new[0]} {new[1] if new[0] == 'refused' else ''}"
    )
    if old[0] == "refused":
        assert old[1] == new[1], (
            f"the two sides refused with different exception types{note}: "
            f"shipped {old[1]}, surface {new[1]}"
        )
        return
    old_payload, new_payload = old[1], new[1]
    for key in sorted(set(old_payload) | set(new_payload)):
        assert old_payload.get(key) == new_payload.get(key), (
            f"the surface and the shipped tab disagree on {key!r}{note}:\n"
            f"  shipped: {old_payload.get(key)!r}\n"
            f"  surface: {new_payload.get(key)!r}"
        )
    assert digest(old_payload) == digest(new_payload), (
        f"the two sides hashed apart{note}: "
        f"shipped {digest(old_payload)}, surface {digest(new_payload)}"
    )


def test_a_scrumming_bot_paints_the_same_tab_on_both_sides(monkeypatch):
    """The surface and the shipped tab disagree on a plain scrumming bot."""
    old, new = drive_both(monkeypatch, case())
    assert_same(old, new)


LONG_NAME = "z" * 200
MARKUP_NAME = "<b>bot</b> & <i>co</i>"
NEWLINE_NAME = "first\nsecond"
UNICODE_ASSET = "ÆRO"

PAIRED_CASES = {
    "extractor mode": case(
        mode="extractor",
        config={"extractor_alt_targets": ["AERO/USDC", "IMU/USDC"]},
    ),
    "extractor with an empty override list": case(mode="extractor"),
    "a mode that is neither scrumming nor extractor": case(mode="phantom"),
    "every optional field absent": case(
        config={
            name: ABSENT
            for name in (
                "stack_mode",
                "split_distance",
                "stack_tranche_count_target",
                "stack_spacing_mode",
                "personal_hold_qty",
                "max_entry_price",
                "min_entry_price",
                "trading_fee_pct",
                "max_target_growth_pct",
                "profit_folding_active",
                "scrum_fold_pct",
                "tranche_despawn_days",
                "wire_inflow_stack_pct",
                "circuit_breaker_soft_pct",
                "circuit_breaker_hard_pct",
                "circuit_breaker_cooldown_candles",
                "max_cartridge_size_pct",
                "max_cartridge_smart",
                "max_cartridge_smart_ceiling_pct",
                "position_ceiling_enabled",
                "position_ceiling_multiple",
                "detonation_enabled",
                "detonation_timeframe",
                "detonation_confidence_min",
                "scrum_require_ta_bullish",
                "scrum_hold_in_uptrend",
                "scrum_defer_to_htf",
                "fold_require_ta_bearish",
                "fold_defer_to_htf",
                "profit_route",
                "profit_route_bot_id",
                "target_asset",
                "exchange_id",
            )
        }
    ),
    "zero everywhere it is allowed": case(
        config={
            "split_distance": 0.0,
            "personal_hold_qty": 0.0,
            "target_balance": 0.0,
            "trading_fee_pct": 0.0,
            "max_target_growth_pct": 0.0,
            "band_travel_pct": 0,
            "hedge_balance": 0.0,
        },
        bot={"live_target": 0.0, "anchor_target": 0.0, "budget": 0.0},
    ),
    "negative numbers": case(
        config={
            "split_distance": -5.0,
            "target_balance": -100.0,
            "hedge_balance": -1.0,
            "band_travel_pct": -20,
        },
        bot={"live_target": -5.0, "anchor_target": -1.0, "surplus": -2.0},
    ),
    "a thousand million": case(
        config={"target_balance": 1_000_000_000.0, "hedge_balance": 1e9},
        bot={"live_target": 1e9, "anchor_target": 1.0, "budget": 1e9},
    ),
    "one billionth": case(
        config={"personal_hold_qty": 1e-9, "split_distance": 1e-9},
        bot={"live_target": 1e-9, "anchor_target": 0.0, "surplus": 1e-9},
    ),
    "a unicode target asset": case(config={"target_asset": UNICODE_ASSET}),
    "a two hundred character bot id": case(config={"profit_route_bot_id": LONG_NAME}),
    "markup in the routing bot id": case(config={"profit_route_bot_id": MARKUP_NAME}),
    "an apostrophe in the routing bot id": case(
        config={"profit_route_bot_id": "o'brien"}
    ),
    "a newline in the routing bot id": case(
        config={"profit_route_bot_id": NEWLINE_NAME}
    ),
    "a number where the routing bot id belongs": case(
        config={"profit_route_bot_id": 12}
    ),
    "wrong capitals on the target asset": case(config={"target_asset": "aero"}),
    "a timeframe this exchange no longer offers": case(config={"ta_timeframe": "4h"}),
    "a timeframe nothing on the list carries": case(config={"ta_timeframe": "99y"}),
    "a visibility nothing on the list carries": case(
        config={"visibility": "carrier-pigeon"}
    ),
    "a profit route nothing on the list carries": case(
        config={"profit_route": "burn-it"}
    ),
    "a detonation timeframe nothing on the list carries": case(
        config={"detonation_timeframe": "1y"}
    ),
    "a spacing mode nothing on the list carries": case(
        config={"stack_spacing_mode": "spiral"}
    ),
    "fold tranches larger than the whole budget": case(
        bot={
            "budget": 1.0103,
            "consumed": 0.5,
            "tranches": [
                {"usd": 16.0523},
                {"usd": 0.5},
                {"usd": 4.25},
                "not a tranche",
            ],
        }
    ),
    "fold tranches with no budget to exceed": case(
        bot={"budget": 0.0, "tranches": [{"usd": 16.0523}]}
    ),
    "a target that has compounded": case(
        bot={"live_target": 120.5, "anchor_target": 100.0, "surplus": 3.25}
    ),
    "both cross-pair rows listed": case(
        market={
            "pairs": {
                ("AERO", "USD"): 1.5,
                ("AERO", "BTC"): 3.0,
                ("AERO", "ETH"): -2.0,
            },
            "btc_usd": 60000.0,
            "eth_usd": 3000.0,
        }
    ),
    "the target asset is bitcoin itself": case(
        config={"target_asset": "BTC"},
        market={"btc_usd": 60000.0, "eth_usd": 3000.0},
    ),
    "the target asset is ether itself": case(
        config={"target_asset": "ETH"},
        market={"btc_usd": 60000.0, "eth_usd": 3000.0},
    ),
    "no rate for the quote yet": case(
        market={"pairs": {("AERO", "BTC"): 1.0}, "btc_usd": 0.0}
    ),
    "only the dollar-coin pair is listed": case(
        market={
            "pairs": {("AERO", "USDC"): 2.0, ("AERO", "BTC"): 2.05},
            "btc_usd": 60000.0,
        }
    ),
    "a despawn timer stored as a whole number": case(
        config={"tranche_despawn_days": 30}
    ),
    "a despawn timer stored as true": case(config={"tranche_despawn_days": True}),
    "a despawn timer stored as not-a-number": case(
        config={"tranche_despawn_days": float("nan")}
    ),
    "a despawn timer stored below zero": case(config={"tranche_despawn_days": -5}),
    "a despawn timer stored above the safe integer": case(
        config={"tranche_despawn_days": 2**1024}
    ),
    "a despawn timer stored as text": case(config={"tranche_despawn_days": "30"}),
    "a stored true where a guarded number belongs": case(
        config={"max_target_growth_pct": True, "hedge_balance": True}
    ),
    "an entry price bound set on both sides": case(
        config={"max_entry_price": 12.5, "min_entry_price": 0.25}
    ),
    "an entry price bound stored as zero": case(
        config={"max_entry_price": 0.0, "min_entry_price": 0.0}
    ),
    "a trading fee stored as zero falls back": case(config={"trading_fee_pct": 0.0}),
    "a whole number one in the aggressive trading flag": case(
        config={"aggressive_trading": 1}
    ),
    "a whole number zero in the stack mode flag": case(config={"stack_mode": 0}),
}


@pytest.mark.parametrize("name", sorted(PAIRED_CASES))
def test_both_sides_paint_the_same_tab(monkeypatch, name):
    """The surface and the shipped tab disagree on one stored input."""
    old, new = drive_both(monkeypatch, PAIRED_CASES[name])
    assert_same(old, new, note=f" [{name}]")


REFUSING_CASES = {
    "text where a guarded number belongs": case(config={"hedge_balance": "abc"}),
    "a guarded number above the float range": case(config={"hedge_balance": 2**1024}),
    "a guarded number that is ten to the four hundred": case(
        config={"max_cartridge_size_pct": 10**400}
    ),
    "text where a guarded whole number belongs": case(
        config={"scrum_detect_pct": "seventy"}
    ),
    "not-a-number where a guarded whole number belongs": case(
        config={"scrum_read_rate_min": float("nan")}
    ),
    "infinity where a guarded whole number belongs": case(
        config={"band_travel_pct": float("inf")}
    ),
    "minus infinity where a guarded whole number belongs": case(
        config={"band_travel_pct": float("-inf")}
    ),
}


@pytest.mark.parametrize("name", sorted(REFUSING_CASES))
def test_both_sides_refuse_the_same_stored_value(monkeypatch, name):
    """One side accepted a stored value the other refused."""
    old, new = drive_both(monkeypatch, REFUSING_CASES[name])
    assert old[0] == "refused", (
        f"the shipped tab built a settings tab from {name}; this case is "
        f"here because it must refuse, so the case no longer controls "
        f"anything: {old[1] if old[0] == 'refused' else 'built'}"
    )
    assert_same(old, new, note=f" [{name}]")


BARE_FIELD_CASES = {
    "text in the opposing trade interval": (
        case(config={"scrumming_interval_pct": "abc"}),
        "TypeError",
        "scrum_interval",
        "abc",
    ),
    "text in the split distance": (
        case(config={"split_distance": "wide"}),
        "TypeError",
        "split_distance",
        "wide",
    ),
    "text in the landing strip candles": (
        case(config={"bb_landing_strip_candles": "three"}),
        "TypeError",
        "landing",
        "three",
    ),
    "ten to the four hundred in the target balance": (
        case(config={"target_balance": 10**400}),
        "OverflowError",
        "target_bal",
        10**400,
    ),
    "not-a-number in the landing strip candles": (
        case(config={"bb_landing_strip_candles": float("nan")}),
        "OverflowError",
        "landing",
        float("nan"),
    ),
    "a decimal in the aggressive trading flag": (
        case(config={"aggressive_trading": 12.7}),
        "TypeError",
        "aggressive",
        12.7,
    ),
    "text in the stack mode flag": (
        case(config={"stack_mode": "yes"}),
        "TypeError",
        "stack_mode",
        "yes",
    ),
}


@pytest.mark.parametrize("name", sorted(BARE_FIELD_CASES))
def test_a_bare_read_stops_the_shipped_tab_and_the_surface_carries_it(
    monkeypatch, name
):
    """A stored value reached a bare control without stopping the tab.

    These are the reads the shipped tab hands to a control with no
    coercion of its own. The control refuses, so the operator gets no
    Settings tab at all. The surface carries the stored value, which is
    what makes the gap visible rather than silent.
    """
    spec, wanted_type, control, stored = BARE_FIELD_CASES[name]
    old, new = drive_both(monkeypatch, spec)
    assert old[0] == "refused", (
        f"the shipped tab built a tab from {name}; the whole point of "
        "this case is that a bare read stops it"
    )
    assert (
        old[1] == wanted_type
    ), f"the shipped tab refused {name} with {old[1]}, not {wanted_type}"
    assert new[0] == "built", (
        f"the surface refused {name} with {new[1]}; it has no control to "
        "refuse with, so it must carry the stored value instead"
    )
    carried = new[1]["check_values"].get(control, new[1]["spin_values"].get(control))
    assert repr(carried) == repr(stored), (
        f"the surface changed the stored value on the way to {control}: "
        f"stored {stored!r}, carried {carried!r}"
    )


def test_a_guarded_read_refuses_the_same_text_on_both_sides(monkeypatch):
    """The bare-read cases would pass if every read stopped the tab.

    This is the other half of the pair above: a field the shipped tab
    coerces itself refuses the same text on both sides, so a run where
    every read refused would fail this test rather than pass silently.
    """
    old, new = drive_both(monkeypatch, case(config={"hedge_balance": "abc"}))
    assert old[0] == "refused" and new[0] == "refused", (old[0], new[0])
    assert old[1] == new[1] == "ValueError", (old[1], new[1])


def built_tab(monkeypatch, spec=None):
    """The shipped host and its tab, built once from `spec`."""
    import src.gui.live_settings.settings_tab as shipped

    spec = spec or case()
    swap_in_recorders(monkeypatch, shipped)
    scout, rates = scout_and_rates(spec["market"])
    stub_market(monkeypatch, scout, rates)
    host = shipped_host(ShippedBot(spec["mode"], spec["config"], spec["bot"]))
    tab = hold(host._create_settings_tab())
    stop_timer(host)
    return host, tab


def poke(widget):
    """Move `widget` once, the way an operator moves it.

    Returns the value it was moved to, or None when the widget carries
    no signal an operator can fire from a keyboard.
    """
    from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit
    from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox

    if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
        widget.setValue(widget.minimum())
        widget.setValue(widget.maximum())
        return widget.value()
    if isinstance(widget, QCheckBox):
        widget.setChecked(not widget.isChecked())
        return widget.isChecked()
    if isinstance(widget, QComboBox):
        widget.setCurrentIndex((widget.currentIndex() + 1) % max(widget.count(), 1))
        return widget.currentIndex()
    if isinstance(widget, QLineEdit):
        widget.setText("moved")
        widget.editingFinished.emit()
        return widget.text()
    return None


def moveable_controls(host):
    """Every named control on the host an operator can move."""
    from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit
    from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox

    kinds = (QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox, QLineEdit)
    return {
        name: widget
        for name, widget in named_widgets(host).items()
        if isinstance(widget, kinds)
    }


def wiring_of(monkeypatch, mode):
    """Which field each control on a `mode` bot records when it is moved."""
    host, _ = built_tab(monkeypatch, case(mode=mode))
    wired = {}
    for name, widget in moveable_controls(host).items():
        before = len(host.changed)
        poke(widget)
        gained = host.changed[before:]
        assert gained, f"moving {name} on a {mode} bot recorded no edit at all"
        wired[name] = gained[0][0]
    return wired


MODE_CONTROL_COUNTS = {"scrumming": 46, "extractor": 49}


@pytest.mark.parametrize("mode", sorted(MODE_CONTROL_COUNTS))
def test_every_control_on_the_tab_reports_one_edit_when_it_is_moved(monkeypatch, mode):
    """A control was wired to nothing, or wired to the wrong field.

    Counted by moving each control and reading what the host recorded,
    not by looking at the source: a connection that exists but reaches
    no handler records nothing here.
    """
    wired = wiring_of(monkeypatch, mode)
    expected = {
        one["name"]: one["field"]
        for one in surface.CONTROL_SPECS
        if one["name"] in wired
    }
    assert wired == expected, (
        "the shipped tab records a different field than the surface names:"
        f" shipped {wired}, surface {expected}"
    )
    assert len(wired) == MODE_CONTROL_COUNTS[mode], (
        f"the shipped tab wired {len(wired)} controls on a {mode} bot, "
        f"not {MODE_CONTROL_COUNTS[mode]}"
    )


def test_the_two_modes_together_wire_every_control_the_surface_names(monkeypatch):
    """A control the surface names is shown by neither bot mode.

    No single mode shows them all: the five scrumming controls and the
    eight Extractor controls never appear on one tab.
    """
    both = set(wiring_of(monkeypatch, "scrumming")) | set(
        wiring_of(monkeypatch, "extractor")
    )
    named = {one["name"] for one in surface.CONTROL_SPECS}
    assert both == named, (
        f"only on the shipped tab: {sorted(both - named)}; "
        f"only in the surface: {sorted(named - both)}"
    )
    assert sum(MODE_CONTROL_COUNTS.values()) > len(named), (
        "the two modes share no control, so the union proves nothing "
        "the two counts did not already"
    )


def test_a_control_wired_to_nothing_is_reported(monkeypatch):
    """The wiring count passes a control that reports no edit.

    The control here is real and built by the shipped tab; its
    connection is broken before it is moved, and the check must see
    that rather than count it as wired.
    """
    host, _ = built_tab(monkeypatch)
    widget = moveable_controls(host)["split_distance"]
    widget.valueChanged.disconnect()
    before = len(host.changed)
    poke(widget)
    assert host.changed[before:] == [], (
        "a disconnected control still recorded an edit, so the wiring "
        "count cannot tell a wired control from an unwired one"
    )


def test_the_tab_wires_one_action_for_every_control_and_three_handlers():
    """The surface names a different number of actions than it has."""
    wired = surface.actions()
    handlers = {
        surface.TIMER_ACTION,
        f"cb_reset_all_btn.{surface.SIGNAL_FOR_KIND[surface.BUTTON]}",
        f"self_destruct_btn.{surface.SIGNAL_FOR_KIND[surface.BUTTON]}",
    }
    assert len(wired) == len(surface.CONTROL_SPECS) + len(handlers), (
        f"the surface names {len(wired)} actions for "
        f"{len(surface.CONTROL_SPECS)} controls and {len(handlers)} handlers"
    )
    assert handlers <= set(wired), sorted(set(wired))
    assert surface.SIGNALS_DECLARED == (), surface.SIGNALS_DECLARED


def test_the_tab_builds_one_repeating_timer_and_starts_it(monkeypatch):
    """The cross-pair refresh timer was not built, or not started."""
    host, _ = built_tab(monkeypatch)
    timer = getattr(host, "_denom_refresh_timer", None)
    assert timer is not None, "the shipped tab built no refresh timer"
    assert timer.interval() == surface.DENOM_REFRESH_INTERVAL_MS, timer.interval()
    assert surface.TIMERS == {
        "denom_refresh_timer": surface.DENOM_REFRESH_INTERVAL_MS
    }, surface.TIMERS
    assert surface.TIMERS_STARTED == ("denom_refresh_timer",), surface.TIMERS_STARTED


def test_the_refresh_timer_is_running_before_the_test_stops_it(monkeypatch):
    """The built-and-started reading would pass on a timer never started.

    The test above reads a timer this file has already stopped, so it
    cannot tell a started timer from a built one. This one reads it
    before the stop.
    """
    import src.gui.live_settings.settings_tab as shipped

    spec = case()
    swap_in_recorders(monkeypatch, shipped)
    scout, rates = scout_and_rates(spec["market"])
    stub_market(monkeypatch, scout, rates)
    host = shipped_host(ShippedBot(spec["mode"], spec["config"], spec["bot"]))
    hold(host._create_settings_tab())
    timer = host._denom_refresh_timer
    running = timer.isActive()
    timer.stop()
    assert running, "the shipped tab built the refresh timer but never started it"
    assert not timer.isActive(), "the timer kept running after it was stopped"


def test_the_reset_button_flashes_its_outcome_and_asks_for_a_restore(monkeypatch):
    """The Reset All Breakers button lost its delayed text restore."""
    from PySide6.QtCore import QTimer

    delays: list = []
    original = QTimer.singleShot
    monkeypatch.setattr(
        QTimer,
        "singleShot",
        staticmethod(lambda ms, fn: delays.append([ms, callable(fn)])),
        raising=True,
    )
    host, _ = built_tab(monkeypatch)
    host._bot.reset_applied = ["soft"]
    host._cb_reset_all_btn.click()
    assert (
        host._cb_reset_all_btn.text() == surface.RESET_APPLIED_TEXT
    ), host._cb_reset_all_btn.text()
    assert delays == [[surface.RESET_RESTORE_DELAY_MS, True]], delays
    assert list(surface.TIMER_DELAYS_MS) == [
        one[0] for one in delays
    ], surface.TIMER_DELAYS_MS
    assert original is not QTimer.singleShot


RESET_OUTCOMES = {
    "a breaker was cleared": (["soft"], None, True, surface.RESET_APPLIED_TEXT),
    "nothing was armed": ([], None, True, surface.RESET_NOTHING_TEXT),
    "the bot refused": (None, RuntimeError("down"), True, surface.RESET_FAILED_TEXT),
    "the bot has no reset": (None, None, False, surface.RESET_FAILED_TEXT),
}


@pytest.mark.parametrize("name", sorted(RESET_OUTCOMES))
def test_the_reset_button_reports_each_outcome_on_both_sides(monkeypatch, name):
    """The Reset All Breakers button shows the wrong line for an outcome."""
    from PySide6.QtCore import QTimer

    applied, raises, has_reset, wanted = RESET_OUTCOMES[name]
    restores: list = []
    monkeypatch.setattr(
        QTimer,
        "singleShot",
        staticmethod(lambda ms, fn: restores.append([ms, callable(fn)])),
        raising=True,
    )
    import src.gui.live_settings.settings_tab as shipped

    spec = case()
    swap_in_recorders(monkeypatch, shipped)
    scout, rates = scout_and_rates(spec["market"])
    stub_market(monkeypatch, scout, rates)
    bot = ShippedBot(
        spec["mode"],
        spec["config"],
        spec["bot"],
        has_reset=has_reset,
        reset_applied=applied,
        reset_raises=raises,
    )
    host = shipped_host(bot)
    hold(host._create_settings_tab())
    stop_timer(host)
    host._cb_reset_all_btn.click()

    model = new_model(spec)
    model.bot = surface.BotSource(
        config=model.bot.config,
        has_reset=has_reset,
        reset_applied=applied,
        reset_raises=raises,
    )
    model.build()
    model.reset_breakers()
    assert host._cb_reset_all_btn.text() == model.reset_button_text == wanted, (
        f"[{name}] shipped {host._cb_reset_all_btn.text()!r}, "
        f"surface {model.reset_button_text!r}, wanted {wanted!r}"
    )
    assert bot.reset_scopes == model.bot.reset_scopes, (
        bot.reset_scopes,
        model.bot.reset_scopes,
    )
    assert restores == [[surface.RESET_RESTORE_DELAY_MS, True]], restores


DESTRUCT_OUTCOMES = {
    "the operator typed the phrase": (
        True,
        "SELF-DESTRUCT",
        True,
        surface.OUTCOME_DISPATCHED,
    ),
    "the operator typed it with spaces around it": (
        True,
        "  SELF-DESTRUCT  ",
        True,
        surface.OUTCOME_DISPATCHED,
    ),
    "the operator typed the wrong capitals": (
        True,
        "self-destruct",
        True,
        surface.OUTCOME_PHRASE_MISMATCH,
    ),
    "the operator typed nothing": (True, "", True, surface.OUTCOME_PHRASE_MISMATCH),
    "the operator closed the prompt": (
        False,
        "SELF-DESTRUCT",
        True,
        surface.OUTCOME_CANCELLED,
    ),
    "this bot type cannot self-destruct": (
        True,
        "SELF-DESTRUCT",
        False,
        surface.OUTCOME_UNAVAILABLE,
    ),
}


@pytest.mark.parametrize("name", sorted(DESTRUCT_OUTCOMES))
def test_the_danger_button_reports_each_outcome_on_both_sides(monkeypatch, name):
    """The self-destruct button took a different path on the two sides."""
    from PySide6 import QtWidgets

    confirmed, typed, has_destruct, wanted = DESTRUCT_OUTCOMES[name]
    boxes: list = []
    started: list = []

    class StubInput:
        @staticmethod
        def getText(parent, title, prompt, echo, initial):
            boxes.append(["prompt", title, prompt, type(parent).__name__, echo])
            return (typed, confirmed)

    class StubMessage:
        @staticmethod
        def warning(parent, title, text):
            boxes.append(["warning", title, text, type(parent).__name__])

        @staticmethod
        def information(parent, title, text):
            boxes.append(["information", title, text, type(parent).__name__])

    class StubThread:
        def __init__(self, target=None, daemon=None, name=None):
            self.target = target
            self.daemon = daemon
            self.name = name

        def start(self):
            started.append([self.name, self.daemon])

    monkeypatch.setattr(QtWidgets, "QInputDialog", StubInput, raising=True)
    monkeypatch.setattr(QtWidgets, "QMessageBox", StubMessage, raising=True)
    import threading

    monkeypatch.setattr(threading, "Thread", StubThread, raising=True)

    spec = case()
    import src.gui.live_settings.settings_tab as shipped

    swap_in_recorders(monkeypatch, shipped)
    scout, rates = scout_and_rates(spec["market"])
    stub_market(monkeypatch, scout, rates)
    bot = ShippedBot(
        spec["mode"], spec["config"], spec["bot"], has_self_destruct=has_destruct
    )
    host = shipped_host(bot)
    hold(host._create_settings_tab())
    stop_timer(host)
    host._self_destruct_btn.click()

    model = new_model(spec)
    model.bot = surface.BotSource(
        config=model.bot.config,
        bot_id=spec["bot"]["bot_id"],
        symbol=spec["bot"]["symbol"],
        has_self_destruct=has_destruct,
    )
    model.build()
    outcome = model.self_destruct(typed, confirmed)

    assert outcome == wanted, f"[{name}] the surface reported {outcome}"
    shipped_dispatched = bool(started)
    assert shipped_dispatched == (outcome == surface.OUTCOME_DISPATCHED), (
        f"[{name}] the shipped tab started {len(started)} thread(s) while "
        f"the surface reported {outcome}"
    )
    if shipped_dispatched:
        wanted_name = surface.thread_name(spec["bot"]["bot_id"][:8])
        assert started == [[wanted_name, surface.THREAD_IS_DAEMON]], started
        assert model.thread.started == started, (model.thread.started, started)
    assert list(surface.THREADS) == ["self_destruct"], surface.THREADS


def test_the_danger_button_prompt_reads_the_same_on_both_sides(monkeypatch):
    """The confirmation prompt names a different bot or symbol."""
    from PySide6 import QtWidgets

    seen: list = []

    class StubInput:
        @staticmethod
        def getText(parent, title, prompt, echo, initial):
            seen.append([title, prompt, initial, type(parent).__name__, echo])
            return ("", False)

    monkeypatch.setattr(QtWidgets, "QInputDialog", StubInput, raising=True)
    spec = case()
    host, _ = built_tab(monkeypatch, spec)
    host._self_destruct_btn.click()

    model = new_model(spec)
    model.build()
    model.self_destruct("", False)
    assert seen[0][0] == surface.CONFIRM_TITLE, seen[0][0]
    assert seen[0][1] == model.prompts[0][1], (
        f"the two sides ask a different question:\n  shipped: {seen[0][1]!r}\n"
        f"  surface: {model.prompts[0][1]!r}"
    )
    assert seen[0][2] == surface.CONFIRM_INITIAL_TEXT, seen[0][2]


TWO_REAL_CASES = (
    case(config={"target_balance": 100.0, "scrum_detect_pct": 75}),
    case(config={"target_balance": 250.0, "scrum_detect_pct": 40}),
)


def test_two_different_real_inputs_hash_apart_on_each_side(monkeypatch):
    """The hash passes whatever the second input carries.

    One input through the shipped tab and the other through the
    surface, then the same pair the other way round: both orders must
    hash apart, or the comparison reports nothing.
    """
    first, second = TWO_REAL_CASES
    old_first = old_snapshot(monkeypatch, first)[1]
    new_second = new_snapshot(second)[1]
    assert digest(old_first) != digest(new_second), (
        "two genuinely different inputs hashed the same, so the hash "
        "comparison would pass whatever the surface produced"
    )
    old_second = old_snapshot(monkeypatch, second)[1]
    new_first = new_snapshot(first)[1]
    assert digest(old_second) != digest(
        new_first
    ), "the same pair the other way round hashed the same"


def test_the_same_input_twice_hashes_the_same(monkeypatch):
    """The tab paints something different from one build to the next."""
    spec = case()
    first = old_snapshot(monkeypatch, spec)[1]
    second = old_snapshot(monkeypatch, spec)[1]
    assert digest(first) == digest(second), (
        f"the shipped tab hashed apart on two builds of one input: "
        f"{digest(first)} then {digest(second)}"
    )


def test_a_whole_number_and_a_decimal_hash_apart():
    """The hash folds 12 and 12.0 together, so a type change is invisible."""
    assert digest({"n": 12}) != digest({"n": 12.0}), (
        "12 and 12.0 hashed the same; a control seeded with the wrong "
        "type would pass"
    )


def test_a_not_a_number_hashes_equal_to_itself():
    """The hash reports a difference between one value and itself.

    The two payloads are built apart so no comparison here reads one
    value twice.
    """
    first = digest({"n": float("nan")})
    second = digest({"n": float("nan")})
    assert first == second, (
        f"not-a-number hashed apart from itself ({first} then {second}), so "
        "every case carrying one would fail for a reason the product did "
        "not decide"
    )


def test_a_swapped_pair_of_values_changes_the_hash():
    """The hash ignores which value sat in which place."""
    assert digest({"a": 1, "b": 2}) != digest(
        {"a": 2, "b": 1}
    ), "two values swapped between their keys hashed the same"


STEP_SEQUENCE = (
    ("split_distance", 4.5),
    ("stack_count", 7),
    ("hedge_active", True),
    ("profit_route", 2),
    ("profit_route_bot_id", "other-bot"),
    ("deto_conf", 0.9),
)


def test_a_sequence_of_edits_is_recorded_in_order_on_both_sides(monkeypatch):
    """A run of operator edits reached the host in a different order."""
    spec = case()
    host, _ = built_tab(monkeypatch, spec)
    controls = moveable_controls(host)
    for index, (name, value) in enumerate(STEP_SEQUENCE):
        widget = controls[name]
        step_value(widget, value)
        assert len(host.changed) == index + 1, (
            f"step {index} ({name}) recorded {len(host.changed)} edits, "
            f"not {index + 1}"
        )
    model = new_model(spec)
    model.build()
    for field, value in host.changed:
        model.mark_changed(field, value)
    assert [
        list(one) for one in host.changed
    ] == model.changed, f"shipped {host.changed}, surface {model.changed}"
    assert len(model.changed) == len(STEP_SEQUENCE), model.changed


def step_value(widget, value):
    """Set `value` on `widget` the way the operator would."""
    from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit
    from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox

    if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
        widget.setValue(value)
    elif isinstance(widget, QCheckBox):
        widget.setChecked(value)
    elif isinstance(widget, QComboBox):
        widget.setCurrentIndex(value)
    elif isinstance(widget, QLineEdit):
        widget.setText(value)
        widget.editingFinished.emit()


REFUSING_STEP = 3


def test_a_sequence_that_refuses_part_way_keeps_what_it_recorded(monkeypatch):
    """The recorder lost the steps taken before one of them refused."""
    spec = case()
    host, _ = built_tab(monkeypatch, spec)
    controls = moveable_controls(host)
    model = new_model(spec)
    model.build()
    refusal = None
    reached = 0
    for index, (name, value) in enumerate(STEP_SEQUENCE):
        try:
            if index == REFUSING_STEP:
                step_value(controls[name], "not an index")
            else:
                step_value(controls[name], value)
        except Exception as exc:
            refusal = type(exc).__name__
            break
        reached = index + 1
    assert refusal is not None, (
        f"step {REFUSING_STEP} of the sequence did not refuse, so this "
        "test proves nothing about a part-way refusal"
    )
    assert refusal == "TypeError", refusal
    assert reached == REFUSING_STEP, reached
    assert len(host.changed) == REFUSING_STEP, (
        f"the shipped host kept {len(host.changed)} of the {REFUSING_STEP} "
        f"edits made before the refusal: {host.changed}"
    )
    for field, value in host.changed:
        model.mark_changed(field, value)
    assert model.changed == [list(one) for one in host.changed], model.changed
    assert model.calls[-1][0] == surface.CHANGED, model.calls[-1]


COMPARED_KEYS = (
    "combo_index",
    "control_specs",
    "changed",
    "compound_row",
    "budget_row",
    "denom_rows",
    "forms",
    "groups",
    "over_cap_row",
    "rows",
    "surplus_row",
    "timeframe_items",
    "tooltips_applied",
    "values",
)

COVERED_ELSEWHERE = {
    "accessible_name": "test_the_tab_carries_the_note_line_and_its_spacing",
    "container": "test_the_tab_carries_the_note_line_and_its_spacing",
    "info_label": "test_the_tab_carries_the_note_line_and_its_spacing",
    "row_count": "test_the_tab_carries_the_note_line_and_its_spacing",
    "built": "test_the_tab_carries_the_note_line_and_its_spacing",
    "control_names": "test_the_two_modes_together_wire_every_control",
    "actions": "test_the_tab_wires_one_action_for_every_control",
    "signals_declared": "test_the_tab_wires_one_action_for_every_control",
    "timers": "test_the_tab_builds_one_repeating_timer_and_starts_it",
    "timers_started": "test_the_tab_builds_one_repeating_timer_and_starts_it",
    "timer_started": "test_the_tab_builds_one_repeating_timer_and_starts_it",
    "timer_delays_ms": "test_the_reset_button_flashes_its_outcome",
    "threads": "test_the_danger_button_reports_each_outcome",
    "bus_subscribes": "test_the_tab_touches_no_event_bus",
    "bus_emits": "test_the_tab_touches_no_event_bus",
    "reset_button": "test_the_reset_button_reports_each_outcome",
    "danger_button": "test_the_danger_button_reports_each_outcome",
    "boxes": "test_the_danger_button_reports_each_outcome",
    "prompts": "test_the_danger_button_prompt_reads_the_same",
    "titles": "test_the_danger_button_prompt_reads_the_same",
    "texts": "test_the_danger_button_reports_each_outcome",
    "outcomes": "test_the_danger_button_reports_each_outcome",
    "group_titles": "test_both_sides_paint_the_same_tab",
    "denom_visible": "test_a_cross_pair_row_hides_when_the_asset_is_the_quote",
    "denom_labels": "test_both_sides_paint_the_same_tab",
    "read_only_labels": "test_both_sides_paint_the_same_tab",
    "alt_targets": "test_the_alt_targets_group_lists_the_pairs_it_holds",
    "timeframe_fallback": "test_the_timeframe_fallback_leaves_the_week_out",
    "timeframe_fallback_choice": "test_the_timeframe_fallback_leaves_the_week_out",
    "tooltips": "test_the_tooltip_table_covers_every_control_that_has_one",
    "reading_kinds": "test_the_tab_names_the_numbers_it_reads_bare",
    "bare_number_fields": "test_the_tab_names_the_numbers_it_reads_bare",
    "modes": "test_both_sides_paint_the_same_tab",
    "items": "test_both_sides_paint_the_same_tab",
    "defaults": "test_both_sides_paint_the_same_tab",
    "formats": "test_both_sides_paint_the_same_tab",
    "colors": "test_the_row_colours_follow_the_values_they_report",
    "thresholds": "test_the_row_colours_follow_the_values_they_report",
    "attributes": "test_the_named_attributes_are_the_ones_read_off_the_bot",
    "call_names": "test_every_recorded_step_carries_a_name_the_surface_names",
    "calls": "test_every_recorded_step_carries_a_name_the_surface_names",
}


def one_view():
    """One built view model, for the completeness checks to read."""
    model = new_model(case(mode="extractor"))
    model.build()
    return surface.build_view_model(model)


def test_every_exported_value_is_compared_or_named_with_its_covering_test():
    """The surface exports a value no test on either list looks at."""
    unclaimed = sorted(set(one_view()) - set(COMPARED_KEYS) - set(COVERED_ELSEWHERE))
    assert unclaimed == [], (
        f"these exported values reach no comparison and name no covering "
        f"test: {unclaimed}"
    )


def test_no_compared_key_is_missing_from_the_view_model():
    """The compared list names a key the surface does not export."""
    exported = set(one_view())
    unbacked = sorted(set(COMPARED_KEYS) - exported)
    assert unbacked == [], (
        f"the comparison names keys the surface does not export, so they "
        f"compare nothing: {unbacked}"
    )
    stale = sorted(set(COVERED_ELSEWHERE) - exported)
    assert (
        stale == []
    ), f"the covered list names keys the surface no longer exports: {stale}"


def test_both_completeness_checks_report_when_the_lists_drift():
    """Either completeness check passes a list that has drifted."""
    exported = set(one_view())
    grown = exported | {"a value nobody claimed"}
    assert sorted(grown - set(COMPARED_KEYS) - set(COVERED_ELSEWHERE)) == [
        "a value nobody claimed"
    ], "the first check would not see a newly exported value"
    assert sorted({"a key nothing exports"} - exported) == [
        "a key nothing exports"
    ], "the second check would not see a compared key nothing backs"


def parsed_names(path):
    """Every module-level name the file at `path` binds, read by parsing.

    Parsed rather than imported, so a name the module gains at run time
    and a name it declares in its own text are two different lists.
    """
    import ast

    found = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
    return found


def imported_names():
    """Every name the imported surface module carries, minus its imports."""
    skipped = {"annotations", "math", "Any", "Optional", "ds"}
    return {
        name
        for name in vars(surface)
        if not name.startswith("__") and name not in skipped
    }


def test_the_surface_declares_and_carries_the_same_names():
    """A name grew on one of the two lists and not the other.

    Both directions, and no count is typed anywhere: the two sets are
    compared to each other.
    """
    declared = parsed_names(SURFACE_FILE)
    carried = imported_names()
    assert declared - carried == set(), (
        f"declared in the file but absent from the module: "
        f"{sorted(declared - carried)}"
    )
    assert carried - declared == set(), (
        f"on the module but declared nowhere in the file: "
        f"{sorted(carried - declared)}"
    )


def test_the_name_check_reports_a_name_on_one_side_only():
    """The name check passes a name that is on one list and not the other."""
    declared = parsed_names(SURFACE_FILE)
    assert (declared | {"a name nothing declares"}) - imported_names() == {
        "a name nothing declares"
    }, "the name check would not see a name missing from the module"


PROCESS_WIDE = (
    ("src.gui.live_settings.settings_tab", "QDoubleSpinBox"),
    ("src.gui.live_settings.settings_tab", "QCheckBox"),
    ("src.exchange.market_pairs_scout", "get_scout"),
    ("src.exchange.currency_rate_monitor", "get_currency_monitor"),
)


def read_process_wide():
    """What each process-wide name points at right now."""
    import importlib

    return {
        f"{module}.{name}": getattr(importlib.import_module(module), name)
        for module, name in PROCESS_WIDE
    }


@pytest.mark.parametrize(
    "spec_name", ["a tab that builds", "a stored value that refuses"]
)
def test_the_process_wide_swaps_are_restored_after_a_drive(monkeypatch, spec_name):
    """A swap this file made outlived the drive that needed it.

    Watched during the drive as well as after it: a check that only
    reads afterwards passes on a run that swapped nothing.
    """
    spec = (
        case()
        if spec_name == "a tab that builds"
        else case(config={"hedge_balance": "abc"})
    )
    before = read_process_wide()
    with monkeypatch.context() as scoped:
        old, new = drive_both(scoped, spec)
        during = read_process_wide()
    after = read_process_wide()
    for key, was in before.items():
        assert during[key] is not was, (
            f"{key} was not swapped during the drive, so this run measured "
            "the live object and the restore check proves nothing"
        )
        assert (
            after[key] is was
        ), f"{key} was left pointing at this file's stand-in after the drive"
    assert old[0] == new[0], (old[0], new[0])
    if spec_name == "a stored value that refuses":
        assert old[0] == "refused", old[0]


def test_the_tab_touches_no_event_bus(monkeypatch):
    """The Settings tab subscribed to or emitted on the event bus.

    Counted on the bus class itself, so a caller reaching the bus
    through any alias is still counted.
    """
    from src.core.event_bus import EventBus

    counted = {"subscribe": 0, "emit": 0}
    for name in counted:
        original = getattr(EventBus, name)

        def wrapper(self, *args, __name=name, __original=original, **kwargs):
            counted[__name] += 1
            return __original(self, *args, **kwargs)

        monkeypatch.setattr(EventBus, name, wrapper, raising=True)

    host, _ = built_tab(monkeypatch, case(mode="extractor"))
    poke(moveable_controls(host)["split_distance"])
    assert counted == {"subscribe": 0, "emit": 0}, counted
    assert list(surface.BUS_SUBSCRIBES) == [], surface.BUS_SUBSCRIBES
    assert list(surface.BUS_EMITS) == [], surface.BUS_EMITS

    from src.core.event_bus import get_event_bus

    bus = get_event_bus()
    delivered: list = []
    bus.subscribe("live_settings.probe", lambda event: delivered.append(event))
    bus.emit("live_settings.probe")
    assert counted == {"subscribe": 1, "emit": 1}, (
        f"the bus counter reported {counted} after one real subscribe and "
        "one real emit, so its zero above was a fact about the counter"
    )


def module_test_names():
    """Every test this file defines, read off the imported module."""
    import inspect

    return {
        name
        for name, value in inspect.getmembers(sys.modules[__name__])
        if name.startswith("test_") and inspect.isfunction(value)
    }


def test_every_named_covering_test_exists_in_this_file():
    """The covered list names a test nobody wrote.

    A key covered by a test that does not exist is covered by nothing,
    and the completeness check would still pass.
    """
    written = module_test_names()
    missing = sorted(
        {
            named
            for named in COVERED_ELSEWHERE.values()
            if not any(one.startswith(named) for one in written)
        }
    )
    assert missing == [], f"named as covering tests but never written: {missing}"


def test_the_covering_test_check_reports_a_name_nobody_wrote():
    """The check above passes a covering test that does not exist."""
    written = module_test_names()
    assert not any(
        one.startswith("test_a_covering_test_nobody_wrote") for one in written
    ), "the control name is itself a test, so the check cannot report"


def test_the_tab_carries_the_note_line_and_its_spacing(monkeypatch):
    """The note above the groups, its spacing, or the row count moved."""
    spec = case()
    host, tab = built_tab(monkeypatch, spec)
    model = new_model(spec)
    model.build()
    view = surface.build_view_model(model)
    assert tab.layout().spacing() == view["container"]["spacing_px"], (
        tab.layout().spacing(),
        view["container"]["spacing_px"],
    )
    first = tab.layout().itemAt(0).widget()
    assert first.text() == view["info_label"]["text"], first.text()
    assert first.wordWrap() == view["info_label"]["word_wrap"], first.wordWrap()
    assert view["row_count"] == len(view["rows"]), view["row_count"]
    assert view["built"] is True, view["built"]
    assert view["accessible_name"] == surface.ACCESSIBLE_NAME
    assert view["container"]["trailing_stretch"] is True


def test_a_cross_pair_row_hides_when_the_asset_is_the_quote():
    """A cross-pair row stayed visible against its own quote currency."""
    model = new_model(
        case(
            config={"target_asset": "BTC"},
            market={"btc_usd": 60000.0, "eth_usd": 3000.0},
        )
    )
    model.build()
    view = surface.build_view_model(model)
    assert view["denom_visible"] == {"BTC": False, "ETH": True}, view["denom_visible"]
    other = new_model(case(market={"btc_usd": 60000.0, "eth_usd": 3000.0}))
    other.build()
    assert surface.build_view_model(other)["denom_visible"] == {
        "BTC": True,
        "ETH": True,
    }, "no asset hides a row, so the hidden reading above is not a reading"
    assert view["denom_labels"]["btc_row"] == surface.DENOM_BTC_ROW_LABEL


def test_the_alt_targets_group_lists_the_pairs_it_holds(monkeypatch):
    """The manual override list showed the wrong pairs, or none."""
    pairs = ["AERO/USDC", "IMU/USDC", "BICO/USDC"]
    spec = case(mode="extractor", config={"extractor_alt_targets": pairs})
    host, tab = built_tab(monkeypatch, spec)
    model = new_model(spec)
    model.build()
    view = surface.build_view_model(model)
    assert view["alt_targets"]["pairs"] == pairs, view["alt_targets"]
    joined = view["alt_targets"]["join"].join(pairs)
    assert joined in painted_texts(
        tab
    ), f"the shipped tab does not paint {joined!r} anywhere"
    heading = view["alt_targets"]["active_format"].format(count=len(pairs))
    assert heading in painted_texts(tab), heading
    empty = new_model(case(mode="extractor"))
    empty.build()
    empty_view = surface.build_view_model(empty)
    assert empty_view["alt_targets"]["pairs"] == [], empty_view["alt_targets"]


def painted_texts(tab):
    """Every text the tab's labels carry."""
    from PySide6.QtWidgets import QLabel

    return [one.text() for one in tab.findChildren(QLabel)]


def test_an_empty_override_list_paints_the_auto_scan_line(monkeypatch):
    """The empty override branch paints the wrong line."""
    _, tab = built_tab(monkeypatch, case(mode="extractor"))
    assert surface.ALT_TARGETS_EMPTY_TEXT in painted_texts(
        tab
    ), surface.ALT_TARGETS_EMPTY_TEXT


def test_the_timeframe_fallback_leaves_the_week_out():
    """The fallback timeframe list drifted from what the tab falls back to."""
    from src.exchange.timeframes import ALL_TIMEFRAMES

    assert surface.TIMEFRAME_FALLBACK_CHOICE in surface.FALLBACK_TIMEFRAMES
    assert "1w" in ALL_TIMEFRAMES, ALL_TIMEFRAMES
    assert "1w" not in surface.FALLBACK_TIMEFRAMES, surface.FALLBACK_TIMEFRAMES
    assert set(surface.FALLBACK_TIMEFRAMES) < set(ALL_TIMEFRAMES), (
        "the fallback list is not a shorter version of the full list, so "
        "the missing week says nothing"
    )


def test_the_tooltip_table_covers_every_control_that_has_one(monkeypatch):
    """The tooltip table names a control the tab never gives one.

    Driven on both modes, because the two never share a tab.
    """
    applied = {}
    for mode in ("scrumming", "extractor"):
        model = new_model(case(mode=mode))
        model.build()
        applied.update(surface.build_view_model(model)["tooltips_applied"])
    surplus = new_model(case(bot={"surplus": 5.0}))
    surplus.build()
    over = new_model(case(bot={"budget": 1.0, "tranches": [{"usd": 9.0}]}))
    over.build()
    applied.update(surface.build_view_model(surplus)["tooltips_applied"])
    applied.update(surface.build_view_model(over)["tooltips_applied"])
    assert set(applied) == set(surface.TOOLTIPS), (
        f"named but never applied: {sorted(set(surface.TOOLTIPS) - set(applied))}; "
        f"applied but never named: {sorted(set(applied) - set(surface.TOOLTIPS))}"
    )
    assert applied == {
        name: surface.TOOLTIPS[name] for name in applied
    }, "an applied tooltip carries different words from the table"


def test_the_tab_names_the_numbers_it_reads_bare():
    """The bare-read list drifted from the readings the surface declares."""
    kinds = surface.reading_kinds()
    bare = set(surface.bare_number_fields())
    assert bare == {
        name for name, kind in kinds.items() if kind == "bare"
    }, f"the bare list says {sorted(bare)}"
    assert bare == {
        "split_distance",
        "scrumming_interval_pct",
        "bb_tolerance_pct",
        "bb_landing_strip_candles",
        "target_balance",
    }, sorted(bare)
    assert len(kinds) > len(
        bare
    ), "every numeric reading is bare, so naming the bare ones says nothing"


def test_the_row_colours_follow_the_values_they_report():
    """A read-only row is drawn in the wrong colour for its value."""
    flat = new_model(case(bot={"live_target": 5.0, "anchor_target": 5.0}))
    flat.build()
    grown = new_model(case(bot={"live_target": 6.0, "anchor_target": 5.0}))
    grown.build()
    assert flat.compound_row[1] == surface.AMBER_COLOR, flat.compound_row
    assert grown.compound_row[1] == surface.SUCCESS_COLOR, grown.compound_row
    assert flat.compound_row[1] != grown.compound_row[1]

    cold = new_model(case(bot={"surplus": 0.0}))
    cold.build()
    hot = new_model(case(bot={"surplus": 1.0}))
    hot.build()
    assert cold.surplus_row[1] is None, cold.surplus_row
    assert hot.surplus_row[1] == surface.AMBER_COLOR, hot.surplus_row

    over = new_model(case(bot={"budget": 1.0, "tranches": [{"usd": 9.0}]}))
    over.build()
    assert over.over_cap_row[1] == surface.ERROR_COLOR, over.over_cap_row
    assert surface.style_for(None) == surface.NO_STYLE
    assert surface.style_for(surface.ERROR_COLOR) == surface.STYLE_FORMAT.format(
        color=surface.ERROR_COLOR
    )
    assert abs(0.0) < surface.COMPOUND_FLAT_EPSILON < 1.0


DENOM_BANDS = {
    "above the band": (3.0, 1.0, surface.SUCCESS_COLOR, "+"),
    "below the band": (1.0, 3.0, surface.ERROR_COLOR, ""),
    "inside the band": (1.05, 1.0, surface.GREY_COLOR, ""),
}


@pytest.mark.parametrize("name", sorted(DENOM_BANDS))
def test_a_cross_pair_row_is_coloured_by_its_divergence(name):
    """A cross-pair row is drawn in the wrong colour for its divergence."""
    pair_pct, usd_pct, wanted, sign = DENOM_BANDS[name]
    text, color = surface.denom_row("BTC", 100.0, 60000.0, pair_pct, usd_pct)
    assert color == wanted, f"[{name}] {color}"
    assert text.startswith("0.001667 BTC"), text
    assert f"USD: {sign}" in text, text


def test_a_cross_pair_row_waits_while_the_rate_is_unknown():
    """A row with no rate yet printed a number instead of waiting."""
    text, color = surface.denom_row("BTC", 100.0, 0.0, 1.0, 1.0)
    assert (text, color) == (surface.DENOM_PENDING, surface.GREY_COLOR)


DENOM_WIDTHS = {
    "a whole unit or more": (60000.0, 60000.0, "1.0000 BTC"),
    "between a hundredth and one": (600.0, 60000.0, "0.01000 BTC"),
    "below a hundredth": (6.0, 60000.0, "0.000100 BTC"),
}


@pytest.mark.parametrize("name", sorted(DENOM_WIDTHS))
def test_a_cross_pair_row_widens_as_the_unit_figure_shrinks(name):
    """A cross-pair row printed the wrong number of decimal places."""
    target_usd, quote_usd, wanted = DENOM_WIDTHS[name]
    text, _ = surface.denom_row("BTC", target_usd, quote_usd, 1.0, 1.0)
    assert text.startswith(wanted), f"[{name}] {text}"


def test_the_named_attributes_are_the_ones_read_off_the_bot(monkeypatch):
    """The surface names an attribute the shipped tab does not read."""
    spec = case(
        bot={
            "live_target": 120.0,
            "anchor_target": 100.0,
            "surplus": 2.0,
            "budget": 1.5,
            "consumed": 0.25,
            "tranches": [{"usd": 9.0}],
        }
    )
    model = new_model(spec)
    model.build()
    view = surface.build_view_model(model)
    bot = ShippedBot(spec["mode"], spec["config"], spec["bot"])
    for key, name in view["attributes"].items():
        if key in ("tranche_usd_key", "despawn_field", "alt_targets_field"):
            continue
        assert hasattr(bot, name), (
            f"the surface names {name!r} for {key}, and the shipped bot "
            "carries no such attribute"
        )
    assert not hasattr(
        bot, "_a_name_the_bot_never_carries"
    ), "the attribute check would pass a name nothing carries"
    assert view["attributes"]["tranche_usd_key"] == "usd"


def test_every_recorded_step_carries_a_name_the_surface_names(monkeypatch):
    """The recorder wrote a step under a name nothing declares."""
    model = new_model(
        case(mode="extractor", bot={"budget": 1.0, "tranches": [{"usd": 9.0}]})
    )
    model.build()
    model.mark_changed("split_distance", 2.0)
    model.reset_breakers()
    model.self_destruct("SELF-DESTRUCT", True)
    view = surface.build_view_model(model)
    names = {call[0] for call in view["calls"]}
    assert names <= set(view["call_names"]), sorted(names - set(view["call_names"]))
    assert len(names) > 10, sorted(names)
    assert "a step nobody declares" not in set(view["call_names"])


INERT_PROBE = '''
import builtins
import json
import sys
import time

counts = {"clock": 0, "open": 0}
CLOCKS = ("time", "monotonic", "perf_counter", "time_ns", "monotonic_ns")
for _name in CLOCKS:
    _original = getattr(time, _name)

    def _counted(*args, _original=_original, **kwargs):
        counts["clock"] += 1
        return _original(*args, **kwargs)

    setattr(time, _name, _counted)

_open = builtins.open


def _counted_open(*args, **kwargs):
    counts["open"] += 1
    return _open(*args, **kwargs)


builtins.open = _counted_open


class RefuseQt:
    """Answer every Qt import with the error an absent package raises."""

    def find_module(self, name, path=None):
        return None

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("PySide6", "shiboken6"):
            raise ImportError("PySide6 is absent from this run")
        return None


import os

sys.meta_path.insert(0, RefuseQt())
sys.path.insert(0, os.environ["PROBE_REPO"])

import src.gui.main_tabs.live_settings_tab_surface as surface

reached_qt = [name for name in sys.modules if name.startswith("PySide6")]
model = surface.LiveSettingsTabModel(
    bot=surface.BotSource(config=surface.BotConfigSource(mode="scrumming")),
    scout=surface.ScoutSource(),
    rates=surface.RateSource(),
)
after_import = dict(counts)

if os.environ.get("PROBE_PLANT") == "1":
    time.time()
    _counted_open(os.environ["PROBE_REPO"] + "/README.md", "rb").close()

print(
    json.dumps(
        {
            "after_import": after_import,
            "final": dict(counts),
            "qt_modules": reached_qt,
            "method": surface.METHOD,
            "controls": len(surface.CONTROL_SPECS),
            "built_model": model.__class__.__name__,
        }
    )
)
'''


def run_probe(tmp_path, plant=False):
    """Run the inert-import probe in its own process and read its answer."""
    running = dict(os.environ)
    running.pop("PYTHONPATH", None)
    running["PROBE_REPO"] = str(REPO)
    running["PROBE_PLANT"] = "1" if plant else "0"
    done = subprocess.run(
        [sys.executable, "-"],
        input=INERT_PROBE,
        capture_output=True,
        text=True,
        timeout=120,
        env=running,
        cwd=str(tmp_path),
        check=False,
    )
    assert done.returncode == 0, (
        f"the probe exited {done.returncode} stdout: {done.stdout} "
        f"stderr: {done.stderr}"
    )
    import json

    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_surface_imports_with_no_qt_and_touches_nothing(tmp_path):
    """Importing the surface read a clock, opened a file, or reached Qt.

    Run in its own process with every Qt import refused, so a run that
    quietly found PySide6 on the path cannot pass.
    """
    found = run_probe(tmp_path)
    assert found["qt_modules"] == [], found["qt_modules"]
    assert found["after_import"] == {"clock": 0, "open": 0}, found["after_import"]
    assert found["method"] == surface.METHOD, found["method"]
    assert found["controls"] == len(surface.CONTROL_SPECS), found["controls"]
    assert found["built_model"] == "LiveSettingsTabModel", found["built_model"]


def test_the_inert_probe_reports_a_planted_clock_read_and_file_open(tmp_path):
    """The probe's zero is a fact about the probe, not about the surface."""
    found = run_probe(tmp_path, plant=True)
    assert found["after_import"] == {"clock": 0, "open": 0}, found["after_import"]
    assert found["final"]["clock"] >= 1, found["final"]
    assert found["final"]["open"] >= 1, found["final"]


HOME_PROBE = """
import json
import os
import sys
from pathlib import Path

import os

sys.path.insert(0, os.environ["PROBE_REPO"])
home = Path(os.environ["PROBE_HOME"])


def count_files():
    return sorted(str(one.relative_to(home)) for one in home.rglob("*") if one.is_file())


before = count_files()

import src.gui.main_tabs.live_settings_tab_surface as surface

REQUIRED = {
    "visibility": "orderbook",
    "aggressive_trading": False,
    "scrumming_interval_pct": 1.5,
    "bb_tolerance_pct": 1.0,
    "bb_landing_strip_candles": 3,
    "ta_timeframe": "1h",
    "target_balance": 100.0,
    "scrum_detect_pct": 75,
    "scrum_fire_pct": 1.0,
    "bb_midline_gate": True,
    "scrum_read_rate_min": 5,
    "band_travel_pct": 0,
    "bb_bullseye_check": True,
    "hedge_rebalance_active": False,
    "hedge_balance": 0.0,
}

model = surface.LiveSettingsTabModel(
    bot=surface.BotSource(
        config=surface.BotConfigSource(mode="extractor", **REQUIRED)
    ),
    scout=surface.ScoutSource({("AERO", "BTC"): 1.0}),
    rates=surface.RateSource(60000.0, 3000.0),
)
model.build()
model.reset_breakers()
model.self_destruct("SELF-DESTRUCT", True)
surface.build_view_model(model)
surface.view_model(
    {"reset": True, "bot": {"mode": "scrumming"}, "config": REQUIRED}
)

after = count_files()

if os.environ.get("PROBE_PLANT") == "1":
    (home / "planted.txt").write_text("planted", encoding="utf-8")

print(
    json.dumps(
        {
            "before": before,
            "after": after,
            "planted": count_files(),
            "rows": len(model.rows),
        }
    )
)
"""


def run_home_probe(tmp_path, plant=False):
    """Drive the surface with home pointed at a throwaway folder."""
    home = tmp_path / "throwaway_home"
    home.mkdir(exist_ok=True)
    running = dict(os.environ)
    running.pop("PYTHONPATH", None)
    running["ACERVATOR_TEST_HOME"] = str(home)
    running["HOME"] = str(home)
    running["USERPROFILE"] = str(home)
    running["PROBE_REPO"] = str(REPO)
    running["PROBE_HOME"] = str(home)
    running["PROBE_PLANT"] = "1" if plant else "0"
    done = subprocess.run(
        [sys.executable, "-"],
        input=HOME_PROBE,
        capture_output=True,
        text=True,
        timeout=120,
        env=running,
        cwd=str(tmp_path),
        check=False,
    )
    assert done.returncode == 0, (
        f"the home probe exited {done.returncode} stdout: {done.stdout} "
        f"stderr: {done.stderr}"
    )
    import json

    return json.loads(done.stdout.strip().splitlines()[-1])


def test_driving_the_surface_writes_no_file_into_a_throwaway_home(tmp_path):
    """The surface wrote into the operator's home while it was driven."""
    found = run_home_probe(tmp_path)
    assert (
        found["after"] == found["before"] == []
    ), f"the surface left {found['after']} under a throwaway home"
    assert found["rows"] > 0, found["rows"]


def test_the_throwaway_home_counter_reports_a_planted_file(tmp_path):
    """The empty home reading is a fact about the counter, not the surface."""
    found = run_home_probe(tmp_path, plant=True)
    assert found["after"] == [], found["after"]
    assert found["planted"] == ["planted.txt"], found["planted"]


def test_neither_side_opens_a_network_connection(monkeypatch):
    """The tab reached the network while it was built.

    The counter watches this process only. Nothing here starts a child
    process, so a connection opened by one would not be seen; the two
    probes that do start children are the ones above, and they import
    the surface rather than drive a socket.
    """
    import socket

    attempts: list = []

    def refuse(*args, **kwargs):
        attempts.append(args[1:] if args else kwargs)
        raise OSError("no network in this test")

    monkeypatch.setattr(socket.socket, "connect", refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", refuse, raising=True)

    old, new = drive_both(monkeypatch, case(mode="extractor"))
    assert old[0] == new[0] == "built", (old[0], new[0])
    assert attempts == [], f"the tab tried to reach {attempts}"

    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", 1))
    assert len(attempts) == 1, (
        f"the network counter reported {len(attempts)} after one real "
        "attempt, so its zero above was a fact about the counter"
    )


HOSTILE_VALUES = {
    "True": True,
    "nan": float("nan"),
    "inf": float("inf"),
    "-inf": float("-inf"),
    "text": "abc",
    "numeric string": "12.7",
    "12.7": 12.7,
    "10**400": 10**400,
}

STOPS_THE_DIALOG = {
    ("double_spin", "bare"): {"10**400", "numeric string", "text"},
    ("double_spin", "float"): {"10**400", "text"},
    ("double_spin", "float_or_default"): {"10**400", "text"},
    ("double_spin", "float_or_zero"): {"10**400", "text"},
    ("spin", "bare"): {"-inf", "10**400", "inf", "nan", "numeric string", "text"},
    ("spin", "int"): {"-inf", "10**400", "inf", "nan", "numeric string", "text"},
    ("spin", "despawn_days"): set(),
}

NUMERIC_SPECS = tuple(
    one
    for one in surface.CONTROL_SPECS
    if one["kind"] in (surface.DOUBLE_SPIN, surface.SPIN)
)


def drive_one_stored_number(monkeypatch, spec, value):
    """Put `value` in one config field and report what the real tab does."""
    mode = "extractor" if spec["group"] == surface.EXTRACTOR_GROUP else "scrumming"
    one = case(mode=mode, config={spec["field"]: value})
    scout, rates = scout_and_rates(one["market"])
    stub_market(monkeypatch, scout, rates)
    host = shipped_host(ShippedBot(one["mode"], one["config"], one["bot"]))
    try:
        hold(host._create_settings_tab())
    except BaseException as exc:
        return ("stops", type(exc).__name__)
    stop_timer(host)
    return ("shows", getattr(host, "_" + spec["name"]).value())


@pytest.mark.qt_no_exception_capture
@pytest.mark.parametrize("label", sorted(HOSTILE_VALUES))
def test_a_stored_number_reaches_each_control_the_same_way(monkeypatch, label):
    """A stored value stops the Settings tab where it used to open, or opens
    it where it used to stop.

    Whether the dialog opens depends only on the kind of control and the
    coercion the tab applies before it, never on which field it is. The
    one field read through a guard absorbs every value here.
    """
    value = HOSTILE_VALUES[label]
    seen = {}
    for spec in NUMERIC_SPECS:
        outcome = drive_one_stored_number(monkeypatch, spec, value)
        key = (spec["kind"], spec["reading"])
        wanted = "stops" if label in STOPS_THE_DIALOG[key] else "shows"
        assert outcome[0] == wanted, (
            f"{spec['field']} ({spec['kind']}, reads {spec['reading']}) "
            f"{outcome[0]} on a stored {label}, not {wanted}: {outcome[1]!r}"
        )
        seen.setdefault(key, set()).add(outcome[0])
    assert seen, "no numeric control was driven at all"


def test_the_guarded_reading_absorbs_every_value_the_others_let_through():
    """The despawn guard stopped absorbing a value the bare reads pass on.

    This is the pair the audit turns on: one field is read through a
    rule that refuses a value it cannot use, and the rest hand what they
    read straight to a control.
    """
    absorbed = STOPS_THE_DIALOG[("spin", "despawn_days")]
    bare = STOPS_THE_DIALOG[("spin", "bare")]
    assert absorbed == set(), absorbed
    assert bare, "the bare whole-number read stops on nothing, so the pair says nothing"
    for label, value in HOSTILE_VALUES.items():
        days = surface.despawn_days(
            surface.BotConfigSource(**{surface.DESPAWN_FIELD: value})
        )
        assert isinstance(days, int), (label, days)
        assert 0 <= days <= surface.DESPAWN_MAX_DAYS, (label, days)


DECIMAL_SILENT_VALUES = ("nan", "inf", "-inf", "True")


@pytest.mark.qt_no_exception_capture
@pytest.mark.parametrize("label", DECIMAL_SILENT_VALUES)
def test_a_decimal_control_shows_a_number_nobody_stored(monkeypatch, label):
    """A stored value that is not a number now stops the tab.

    It does not: the control clamps it and prints a plausible figure.
    Target Balance stored as not-a-number prints the top of its range.
    """
    spec = surface.spec_for("target_bal")
    kind, shown = drive_one_stored_number(monkeypatch, spec, HOSTILE_VALUES[label])
    assert kind == "shows", (kind, shown)
    assert isinstance(shown, float), shown
    low, high = spec["range"]
    assert shown in (low, high), (
        f"a stored {label} printed {shown}, which is neither bound of "
        f"{spec['range']}"
    )


SKIN_READERS = (
    "styleSheet",
    "palette",
    "background",
    "foreground",
    "property",
    "color",
    "brush",
)


def skin_reads_in(path):
    """Every call in `path` that reads a skin off a live object.

    Parsed, never matched against the file's text: a text sweep reports
    the pattern strings the sweep itself writes down.
    """
    import ast

    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in SKIN_READERS:
            found.append([node.lineno, ast.unparse(node)[:70]])
    return found


OWN_FILES = (
    "tests/test_live_settings_tab_surface_parity.py",
    "src/gui/main_tabs/live_settings_tab_surface.py",
)


@pytest.mark.parametrize("name", OWN_FILES)
def test_this_unit_reads_no_skin_off_a_live_object(name):
    """A colour, palette or style was read off a live widget.

    The rendered picture is the only place a skin is read here.
    """
    found = skin_reads_in(REPO / name)
    assert found == [], f"{name} reads a live skin at {found}"


def test_the_skin_sweep_reports_a_file_that_really_does_read_one():
    """The sweep's empty answer is a fact about the sweep.

    Pointed at a parity file that genuinely reads a live skin, the sweep
    must name it.
    """
    other = REPO / "tests" / "test_alerts_tab_surface_parity.py"
    assert other.is_file(), other
    found = skin_reads_in(other)
    assert found, (
        f"the sweep found no live-skin read in {other.name}, so its empty "
        "answer on this unit's own files says nothing"
    )


def self_comparisons_in(path):
    """Every assertion in `path` comparing a value to itself."""
    import ast

    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
            continue
        if ast.unparse(test.left) == ast.unparse(test.comparators[0]):
            found.append([node.lineno, ast.unparse(test)[:70]])
    return found


def constant_assertions_in(path):
    """Every assertion in `path` whose answer is a constant."""
    import ast

    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if isinstance(test, ast.Constant):
            found.append([node.lineno, ast.unparse(test)[:70]])
        elif isinstance(test, ast.Compare) and all(
            isinstance(one, ast.Constant) for one in [test.left, *test.comparators]
        ):
            found.append([node.lineno, ast.unparse(test)[:70]])
    return found


@pytest.mark.parametrize("name", OWN_FILES)
def test_no_assertion_here_compares_a_value_to_itself(name):
    """An assertion compares one value to itself and can never fail."""
    found = self_comparisons_in(REPO / name)
    assert found == [], f"{name} compares a value to itself at {found}"


@pytest.mark.parametrize("name", OWN_FILES)
def test_no_assertion_here_reads_a_constant(name):
    """An assertion reads a constant and can never fail."""
    found = constant_assertions_in(REPO / name)
    assert found == [], f"{name} asserts a constant at {found}"


def parsed_from(text, tmp_path, name):
    """`text` written to a throwaway file the sweeps can parse."""
    written = tmp_path / name
    written.write_text(text, encoding="utf-8", newline="\n")
    return written


SELF_COMPARE_SAMPLE = "def sample(one):\n    assert one.count == one.count\n"
CONSTANT_SAMPLE = "def sample():\n    assert 1 == 1\n"
CLEAN_SAMPLE = "def sample(one, two):\n    assert one.count == two.count\n"


def test_the_self_comparison_sweep_reports_one_and_stays_quiet_otherwise(
    tmp_path,
):
    """The self-comparison sweep passes a value compared to itself."""
    hit = self_comparisons_in(parsed_from(SELF_COMPARE_SAMPLE, tmp_path, "a.py"))
    quiet = self_comparisons_in(parsed_from(CLEAN_SAMPLE, tmp_path, "b.py"))
    assert len(hit) == 1, hit
    assert quiet == [], quiet


def test_the_constant_assertion_sweep_reports_one_and_stays_quiet_otherwise(
    tmp_path,
):
    """The constant-assertion sweep passes an assertion on a constant."""
    hit = constant_assertions_in(parsed_from(CONSTANT_SAMPLE, tmp_path, "c.py"))
    quiet = constant_assertions_in(parsed_from(CLEAN_SAMPLE, tmp_path, "d.py"))
    assert len(hit) == 1, hit
    assert quiet == [], quiet


SKIN_SAMPLE = "def sample(one):\n    assert one.styleSheet() == ''\n"


def test_the_skin_sweep_reports_a_planted_read_and_stays_quiet_otherwise(
    tmp_path,
):
    """The skin sweep passes a style read off a live object."""
    hit = skin_reads_in(parsed_from(SKIN_SAMPLE, tmp_path, "e.py"))
    quiet = skin_reads_in(parsed_from(CLEAN_SAMPLE, tmp_path, "f.py"))
    assert len(hit) == 1, hit
    assert quiet == [], quiet


PICTURE_CASES = {
    "a scrumming bot with both cross-pair rows live": case(
        bot={"live_target": 120.5, "anchor_target": 100.0, "surplus": 3.25},
        market={
            "pairs": {
                ("AERO", "USD"): 1.5,
                ("AERO", "BTC"): 3.0,
                ("AERO", "ETH"): -2.0,
            },
            "btc_usd": 60000.0,
            "eth_usd": 3000.0,
        },
    ),
    "an extractor bot with a manual override list": case(
        mode="extractor",
        config={"extractor_alt_targets": ["AERO/USDC", "IMU/USDC"]},
        bot={"budget": 1.0103, "tranches": [{"usd": 16.0523}]},
    ),
}


def model_payload(spec):
    """The surface's view model for one case, stamped as it comes off."""
    model = new_model(spec)
    model.build()
    return sealed(surface.build_view_model(model))


def shipped_tab_widget(monkeypatch, spec):
    """The real Settings tab, built by the shipped mixin."""
    _, tab = built_tab(monkeypatch, spec)
    return tab


def spin_from(spec_row, value, integer):
    """One spin box, set up in the order the shipped tab sets it up."""
    from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox

    built = QSpinBox() if integer else QDoubleSpinBox()
    low, high = spec_row["range"]
    built.setRange(low, high)
    if "decimals" in spec_row:
        built.setDecimals(spec_row["decimals"])
    if "suffix" in spec_row:
        built.setSuffix(spec_row["suffix"])
    if "prefix" in spec_row:
        built.setPrefix(spec_row["prefix"])
    if "step" in spec_row:
        built.setSingleStep(spec_row["step"])
    if "special_value_text" in spec_row:
        built.setSpecialValueText(spec_row["special_value_text"])
    built.setValue(value)
    return built


def control_from(spec_row, view):
    """One control, built from the payload alone."""
    from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit

    name = spec_row["name"]
    kind = spec_row["kind"]
    value = view["values"][name]
    if kind in (surface.DOUBLE_SPIN, surface.SPIN):
        return spin_from(spec_row, value, kind == surface.SPIN)
    if kind == surface.CHECK:
        built = QCheckBox(spec_row["text"])
        built.setChecked(value)
        return built
    if kind == surface.COMBO_DATA:
        built = QComboBox()
        for text, data in spec_row["items"]:
            built.addItem(text, data)
        built.setCurrentIndex(view["combo_index"][name])
        return built
    if kind == surface.COMBO_TEXT:
        built = QComboBox()
        texts = (
            view["timeframe_items"]
            if spec_row["reading"] == surface.TIMEFRAME_READING
            else list(spec_row["items"])
        )
        built.addItems(texts)
        built.setCurrentIndex(view["combo_index"][name])
        return built
    built = QLineEdit()
    built.setText(value)
    built.setPlaceholderText(spec_row["placeholder"])
    return built


READ_ONLY_FROM_PAYLOAD = {
    "live_lbl": "compound_row",
    "surplus_lbl": "surplus_row",
    "budget_lbl": "budget_row",
    "over_lbl": "over_cap_row",
}


def read_only_from(name, view):
    """One read-only row label, built from the payload alone."""
    from PySide6.QtWidgets import QLabel

    if name in READ_ONLY_FROM_PAYLOAD:
        row = view[READ_ONLY_FROM_PAYLOAD[name]]
        built = QLabel(row[0])
        if len(row) > 1 and row[1] is not None:
            built.setStyleSheet(surface.style_for(row[1]))
        return built
    quote = surface.DENOM_BTC if name == "target_btc_lbl" else surface.DENOM_ETH
    text, color = view["denom_rows"][quote]
    built = QLabel(text)
    built.setStyleSheet(surface.style_for(color))
    built.setVisible(view["denom_visible"][quote])
    return built


def form_group_from(group_key, title, view, specs):
    """One boxed group whose rows sit in a form, built from the payload."""
    from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout
    from PySide6.QtWidgets import QPushButton

    box = QGroupBox(title)
    form = QFormLayout(box)
    for key, label, name in view["rows"]:
        if key != group_key:
            continue
        if name == "cb_reset_all_btn":
            row = QHBoxLayout()
            button = QPushButton(view["reset_button"]["current_text"])
            row.addWidget(button)
            form.addRow(row)
            continue
        if name in specs:
            widget = control_from(specs[name], view)
        else:
            widget = read_only_from(name, view)
        if label is None:
            form.addRow(widget)
        else:
            form.addRow(label, widget)
    return box


def danger_group_from(title, view):
    """The danger box, built from the payload alone."""
    from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout

    box = QGroupBox(title)
    box.setStyleSheet(surface.DANGER_GROUP_STYLE)
    column = QVBoxLayout(box)
    hint = QLabel(view["danger_button"]["hint_text"])
    hint.setWordWrap(view["danger_button"]["hint_word_wrap"])
    hint.setStyleSheet(surface.DANGER_HINT_STYLE)
    column.addWidget(hint)
    button = QPushButton(view["danger_button"]["text"])
    button.setStyleSheet(surface.DANGER_BUTTON_STYLE)
    column.addWidget(button)
    return box


def alt_targets_group_from(title, view):
    """The manual override box, built from the payload alone."""
    from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout

    box = QGroupBox(title)
    column = QVBoxLayout(box)
    pairs = view["alt_targets"]["pairs"]
    if pairs:
        heading = QLabel(view["alt_targets"]["active_format"].format(count=len(pairs)))
        heading.setStyleSheet(surface.ALT_TARGETS_ACTIVE_STYLE)
        column.addWidget(heading)
        listed = QLabel(view["alt_targets"]["join"].join(pairs))
        listed.setWordWrap(surface.ALT_TARGETS_LIST_WORD_WRAP)
        listed.setStyleSheet(surface.ALT_TARGETS_LIST_STYLE)
        column.addWidget(listed)
    else:
        empty = QLabel(view["alt_targets"]["empty_text"])
        empty.setStyleSheet(surface.ALT_TARGETS_EMPTY_STYLE)
        column.addWidget(empty)
    return box


def tab_from_payload(view):
    """The whole Settings tab, built from the surface's payload alone."""
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    view = unaltered(view)
    specs = {one["name"]: one for one in view["control_specs"]}
    tab = QWidget()
    tab.setAccessibleName("Live Bot Settings tab painted by the surface")
    layout = QVBoxLayout(tab)
    layout.setSpacing(view["container"]["spacing_px"])
    info = QLabel(view["info_label"]["text"])
    info.setStyleSheet(view["info_label"]["style_sheet"])
    info.setWordWrap(view["info_label"]["word_wrap"])
    layout.addWidget(info)
    for group_key, title in view["groups"]:
        if group_key == surface.DANGER_GROUP:
            layout.addWidget(danger_group_from(title, view))
        elif group_key == surface.ALT_TARGETS_GROUP:
            layout.addWidget(alt_targets_group_from(title, view))
        else:
            layout.addWidget(form_group_from(group_key, title, view, specs))
    layout.addStretch()
    return tab


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_the_two_sides_paint_one_picture(monkeypatch, name):
    """The surface paints a different Settings tab from the shipped one.

    One render from each side, at one size, on this machine. No pixel
    count, no colour count and no fingerprint is written down here.
    """
    app()
    spec = PICTURE_CASES[name]
    payload = model_payload(spec)
    assert_same_skin(
        build_old_side=lambda: hold(shipped_tab_widget(monkeypatch, spec)),
        build_new_side=lambda: hold(tab_from_payload(payload)),
        size=PICTURE_SIZE,
        control_rule=CONTROL_RULE,
        note=name,
    )


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_each_rendered_state_can_report_before_it_is_compared(monkeypatch, name):
    """A render paints one colour, so no comparison of it reports.

    The colour count each state paints is measured and returned rather
    than written down, so nothing here pins a number this machine
    happens to produce.
    """
    from tests.qt_pixel import render_widget

    app()
    spec = PICTURE_CASES[name]
    old = render_widget(hold(shipped_tab_widget(monkeypatch, spec)), PICTURE_SIZE)
    new = render_widget(hold(tab_from_payload(model_payload(spec))), PICTURE_SIZE)
    old_colours = assert_picture_can_report(old, note=f"old side, {name}")
    new_colours = assert_picture_can_report(new, note=f"new side, {name}")
    assert old_colours == new_colours, (
        f"[{name}] the two sides painted {old_colours} and {new_colours} "
        "colours, so they are not painting one picture"
    )
    assert colour_count(old) == old_colours


def test_two_different_real_cases_paint_two_pictures(monkeypatch):
    """The picture comparison passes whatever the second side paints."""
    from tests.qt_pixel import render_widget

    app()
    first, second = sorted(PICTURE_CASES)
    assert_cases_paint_differently(
        old_side=render_widget(
            hold(shipped_tab_widget(monkeypatch, PICTURE_CASES[first])),
            PICTURE_SIZE,
        ),
        new_side=render_widget(
            hold(tab_from_payload(model_payload(PICTURE_CASES[second]))),
            PICTURE_SIZE,
        ),
        note=f"{first} against {second}",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused(monkeypatch):
    """A render was taken of a payload somebody edited."""
    spec = PICTURE_CASES[sorted(PICTURE_CASES)[0]]
    payload = model_payload(spec)
    payload["values"]["target_bal"] = 999.0
    with pytest.raises(AssertionError) as reported:
        tab_from_payload(payload)
    assert "altered after it came off" in str(reported.value)


def test_a_payload_that_never_came_off_a_side_is_refused():
    """A render was taken of a payload nobody produced."""
    with pytest.raises(AssertionError) as reported:
        tab_from_payload({"values": {}, "groups": [], "rows": []})
    assert "never came off" in str(reported.value)
