"""The Qt Simulator visuals and the Qt-free surface, side by side.

A failure means the view model describes a different gate light, a
different price series, a different candle, a different vote, a different
colour, a different geometry or a different branch than the widgets in
``src/gui/simulator_tab/fleet/sim_visuals.py`` build on the same steps.
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
import time as clock_module
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import sim_visuals_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_pictures_differ,
    assert_pictures_match,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SOURCE = REPO_ROOT / "src/gui/simulator_tab/fleet/sim_visuals.py"
SURFACE_SOURCE = REPO_ROOT / "src/gui/main_tabs/sim_visuals_surface.py"
VOCABULARY_SOURCE = REPO_ROOT / "src/trading/gate_vocabulary.py"
NESTED_CLASS_NEIGHBOUR = REPO_ROOT / "src/gui/stock_main_window.py"

GATE_PIXEL_SIZE = (760, 24)
CHART_PIXEL_SIZE = (900, 400)
VOTE_PIXEL_SIZE = (700, 200)
PANEL_PIXEL_SIZE = (900, 300)

MISSING = object()

_alive: list = []


# Reading a value without caring what kind of number it is


def as_text(value):
    """`value` with every number turned into its own written form.

    A whole number and a decimal of the same size compare equal and hash
    apart, and two not-a-numbers never compare equal to each other. Both
    are decided here, once, so every later comparison reads one shape.
    """
    if isinstance(value, dict):
        return {repr(key): as_text(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_text(inner) for inner in value]
    if isinstance(value, set):
        return sorted(repr(inner) for inner in value)
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, (int, float)):
        return repr(value)
    return value


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(as_text(value), sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def differing_paths(old, new, prefix: str = "") -> list:
    """Every dotted path at which two traces hold a different value."""
    if isinstance(old, dict) and isinstance(new, dict):
        found = []
        for key in sorted(set(old) | set(new), key=repr):
            found.extend(
                differing_paths(
                    old.get(key, MISSING), new.get(key, MISSING), f"{prefix}{key}."
                )
            )
        return found
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        found = []
        for index, (left, right) in enumerate(zip(old, new)):
            found.extend(differing_paths(left, right, f"{prefix}{index}."))
        return found
    return [] if old == new else [prefix.rstrip(".")]


# The one application object and the run's fonts


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    load_run_fonts()
    return ensure_app()


def fonts_ready() -> bool:
    """Whether this run holds a font database, asked after it is applied."""
    load_run_fonts()
    return has_real_fonts()


def hold(widget):
    """Keep `widget` alive for the run so no render reads a freed object."""
    _alive.append(widget)
    return widget


def widest_gate_label_px() -> int:
    """The widest gate label, measured in this run's own six-point font.

    The step one gate takes is a fact about the host's fonts, so it is
    measured here and handed to both sides rather than written down.
    """
    from PySide6.QtGui import QFont, QFontMetrics

    app()
    font = QFont()
    font.setPointSize(surface.GATE_FONT_PT)
    metrics = QFontMetrics(font)
    return max(
        metrics.horizontalAdvance(label)
        for name in surface.GATE_BANKS
        for label in surface.GATE_ORDER[name]
    )


def measured_pitch_px() -> int:
    """The step one gate takes on this host, from the surface's own rule."""
    return surface.gate_pitch_px(widest_gate_label_px())


# The inputs. One table of step sequences drives both sides.

LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "Ekthelius' venues"
WRONG_CAPITALS_TEXT = "bTC/usdc"

PAIR = "BTC/USDC"
OTHER = "ETH/USDC"
THIRD = "AERO/USDC"
FLEET = [PAIR, OTHER, THIRD]

A_THOUSAND_MILLION = 1_000_000_000
ONE_BILLIONTH = 1e-9
BIG_FLOAT = 2**1023
TOO_BIG_FLOAT = 2**1024

SCRUM_BLOCKERS = ["delta<=0", "TA-not-bullish"]
FOLD_BLOCKERS = ["no-tranches-queued", "CB-soft-trip"]
UNKNOWN_BLOCKERS = ["a condition the display has no light for"]


def vote(net=0.26, conf=0.42, bull=4, bear=1):
    """One voting summary, as the panel hands it to the readout."""
    return {
        "net_score": net,
        "consensus_confidence": conf,
        "bullish_count": bull,
        "bearish_count": bear,
    }


def ticks(symbol, closes, volume=10.0, start_ts=1_700_000_000_000):
    """One tick step per close, an hour apart, as a full bar each."""
    made = []
    for index, close in enumerate(closes):
        made.append(
            (
                "tick",
                symbol,
                close,
                volume,
                start_ts + index * 3_600_000,
                close,
                close,
                close,
            )
        )
    return made


LOAD = [("symbols", list(FLEET))]
RISING = ticks(PAIR, [100.0, 101.5, 99.25, 104.0, 103.5])
FLAT = ticks(PAIR, [50.0, 50.0, 50.0, 50.0])

SCENARIOS = {
    "built_only": [],
    "fleet_loaded": LOAD,
    "happy": LOAD
    + RISING
    + [
        ("gates", PAIR, True, False, SCRUM_BLOCKERS, FOLD_BLOCKERS, ""),
        ("gates", OTHER, False, True, [], [], "upper"),
        ("mark", PAIR, True),
        ("vote", PAIR, vote()),
        ("vote", OTHER, vote(net=-0.4, conf=0.9, bull=0, bear=6)),
    ],
    "focused": LOAD + RISING + [("focus", PAIR)],
    "focused_with_ytd": LOAD
    + RISING
    + [("focus", PAIR), ("ytd", PAIR, 1_700_000_000_000 + 3_600_000)],
    "focused_before_any_candle": LOAD + [("focus", PAIR)],
    "focus_on_a_symbol_the_fleet_does_not_carry": LOAD + [("focus", "NOPE/USDC")],
    "focus_cleared": LOAD + RISING + [("focus", PAIR), ("focus", "")],
    "focus_survives_a_reload_that_keeps_it": LOAD + RISING + [("focus", PAIR)] + LOAD,
    "empty_fleet": [("symbols", [])],
    "no_symbols_at_all": [("symbols", None)],
    "one_point_series": LOAD + ticks(PAIR, [42.0]),
    "every_point_equal": LOAD + FLAT,
    "series_carrying_a_not_a_number": LOAD + ticks(PAIR, [10.0, math.nan, 12.0]),
    "series_carrying_infinity": LOAD + ticks(PAIR, [10.0, math.inf, 12.0]),
    "series_carrying_minus_infinity": LOAD + ticks(PAIR, [10.0, -math.inf, 12.0]),
    "zero_prices": LOAD + ticks(PAIR, [0.0, 0.0, 0.0]),
    "negative_prices": LOAD + ticks(PAIR, [-5.0, -7.5, -6.25]),
    "a_thousand_million_price": LOAD + ticks(PAIR, [float(A_THOUSAND_MILLION)]),
    "one_billionth_price": LOAD + ticks(PAIR, [ONE_BILLIONTH, ONE_BILLIONTH * 2]),
    "the_biggest_float": LOAD + ticks(PAIR, [float(BIG_FLOAT)]),
    "a_number_too_big_for_a_float": LOAD + [("tick", PAIR, TOO_BIG_FLOAT, 1.0)],
    "text_where_a_price_belongs": LOAD + [("tick", PAIR, "forty two", 1.0)],
    "a_number_in_text_where_a_price_belongs": LOAD + [("tick", PAIR, "12.7", 1.0)],
    "a_flag_where_a_price_belongs": LOAD + [("tick", PAIR, True, 1.0)],
    "nothing_where_a_price_belongs": LOAD + [("tick", PAIR, None, 1.0)],
    "zero_volume": LOAD + ticks(PAIR, [10.0, 11.0], volume=0.0),
    "negative_volume": LOAD + ticks(PAIR, [10.0, 11.0], volume=-3.0),
    "a_flag_where_a_volume_belongs": LOAD + [("tick", PAIR, 10.0, True)],
    "a_tick_for_a_symbol_the_chart_does_not_track": LOAD
    + [("tick", "NOPE/USDC", 10.0, 1.0)],
    "a_tick_with_no_timestamp": LOAD + [("tick", PAIR, 10.0, 1.0, None)],
    "a_flag_where_a_timestamp_belongs": LOAD + [("tick", PAIR, 10.0, 1.0, True)],
    "a_not_a_number_where_a_timestamp_belongs": LOAD
    + [("tick", PAIR, 10.0, 1.0, math.nan)],
    "a_bar_wider_than_its_close": LOAD + [("tick", PAIR, 10.0, 1.0, 1, 9.0, 12.0, 8.0)],
    "a_bar_whose_high_is_under_its_low": LOAD
    + [("tick", PAIR, 10.0, 1.0, 1, 9.0, 1.0, 99.0)],
    "marked_before_any_tick": LOAD + [("mark", PAIR, True)],
    "marked_after_a_tick": LOAD + ticks(PAIR, [10.0, 11.0]) + [("mark", PAIR, False)],
    "a_flag_that_is_text_where_a_marker_belongs": LOAD
    + ticks(PAIR, [10.0])
    + [("mark", PAIR, "no")],
    "markers_cleared_for_one_symbol": LOAD
    + ticks(PAIR, [10.0, 11.0])
    + [("mark", PAIR, True), ("clear_markers", PAIR)],
    "markers_cleared_for_every_symbol": LOAD
    + ticks(PAIR, [10.0, 11.0])
    + [("mark", PAIR, True), ("clear_markers", None)],
    "markers_cleared_for_a_symbol_the_chart_does_not_track": LOAD
    + [("clear_markers", "NOPE/USDC")],
    "data_cleared": LOAD + RISING + [("mark", PAIR, True), ("clear_data",)],
    "data_cleared_then_driven_again": LOAD
    + RISING
    + [("clear_data",)]
    + ticks(PAIR, [7.0, 8.0]),
    "ytd_start_set": LOAD + [("ytd", PAIR, 1_700_000_000_000)],
    "ytd_start_as_a_flag": LOAD + [("ytd", PAIR, True)],
    "ytd_start_as_a_not_a_number": LOAD + [("ytd", PAIR, math.nan)],
    "ytd_start_as_infinity": LOAD + [("ytd", PAIR, math.inf)],
    "ytd_start_as_minus_infinity": LOAD + [("ytd", PAIR, -math.inf)],
    "ytd_start_as_a_number_in_text": LOAD + [("ytd", PAIR, "12.7")],
    "ytd_start_as_a_decimal": LOAD + [("ytd", PAIR, 12.7)],
    "ytd_start_as_a_very_big_whole_number": LOAD + [("ytd", PAIR, 10**400)],
    "ytd_start_as_nothing": LOAD + [("ytd", PAIR, None)],
    "gates_read_once": LOAD
    + [("gates", PAIR, True, True, SCRUM_BLOCKERS, FOLD_BLOCKERS, "")],
    "gates_with_a_scrum_landing_strip": LOAD
    + [("gates", PAIR, False, False, [], [], "upper")],
    "gates_with_a_fold_landing_strip": LOAD
    + [("gates", PAIR, False, False, [], [], "lower")],
    "gates_with_a_landing_strip_in_wrong_capitals": LOAD
    + [("gates", PAIR, False, False, [], [], "UPPER")],
    "gates_with_an_unknown_landing_strip": LOAD
    + [("gates", PAIR, False, False, [], [], "sideways")],
    "gates_with_an_unknown_blocker": LOAD
    + [("gates", PAIR, False, False, UNKNOWN_BLOCKERS, [], "")],
    "gates_with_no_blocker_list": LOAD + [("gates", PAIR, True, True, None, None, "")],
    "gates_cleared": LOAD
    + [("gates", PAIR, True, True, SCRUM_BLOCKERS, FOLD_BLOCKERS, ""), ("clear", PAIR)],
    "gates_cleared_after_a_fold_landing_strip": LOAD
    + [("gates", PAIR, False, False, [], [], "lower"), ("clear", PAIR)],
    "gates_cleared_after_a_scrum_landing_strip": LOAD
    + [("gates", PAIR, False, False, [], [], "upper"), ("clear", PAIR)],
    "gates_for_a_symbol_the_pane_does_not_carry": LOAD + [("gates", "NOPE/USDC", True)],
    "gates_cleared_before_any_reading": LOAD + [("clear", PAIR)],
    "a_repeated_symbol": [("symbols", [PAIR, PAIR, OTHER])],
    "a_reload_after_a_repeated_symbol": [("symbols", [PAIR, PAIR])] + LOAD,
    "an_empty_symbol": [("symbols", [PAIR, "", OTHER])],
    "a_symbol_that_is_nothing": [("symbols", [PAIR, None])],
    "a_symbol_that_is_a_whole_number": [("symbols", [12])],
    "a_symbol_that_is_a_decimal": [("symbols", [12.0])],
    "a_symbol_that_is_zero": [("symbols", [0])],
    "a_symbol_that_is_a_flag": [("symbols", [True])],
    "a_symbol_in_unicode": [("symbols", [UNICODE_TEXT])],
    "a_symbol_of_two_hundred_characters": [("symbols", [LONG_TEXT])],
    "a_symbol_carrying_markup": [("symbols", [MARKUP_TEXT])],
    "a_symbol_carrying_an_apostrophe": [("symbols", [APOSTROPHE_TEXT])],
    "a_symbol_in_wrong_capitals": [("symbols", [WRONG_CAPITALS_TEXT])],
    "a_symbol_carrying_a_newline": [("symbols", [NEWLINE_TEXT])],
    "votes_written": LOAD + [("vote", PAIR, vote())],
    "a_vote_just_above_the_bull_line": LOAD + [("vote", PAIR, vote(net=0.1000001))],
    "a_vote_exactly_on_the_bull_line": LOAD + [("vote", PAIR, vote(net=0.1))],
    "a_vote_exactly_on_the_bear_line": LOAD + [("vote", PAIR, vote(net=-0.1))],
    "a_vote_just_below_the_bear_line": LOAD + [("vote", PAIR, vote(net=-0.1000001))],
    "a_vote_of_zero": LOAD + [("vote", PAIR, vote(net=0.0, conf=0.0, bull=0, bear=0))],
    "a_vote_of_a_thousand_million": LOAD
    + [("vote", PAIR, vote(net=float(A_THOUSAND_MILLION)))],
    "a_vote_of_one_billionth": LOAD + [("vote", PAIR, vote(net=ONE_BILLIONTH))],
    "a_vote_of_infinity": LOAD + [("vote", PAIR, vote(net=math.inf))],
    "a_vote_of_minus_infinity": LOAD + [("vote", PAIR, vote(net=-math.inf))],
    "a_vote_of_not_a_number": LOAD + [("vote", PAIR, vote(net=math.nan))],
    "a_vote_whose_net_is_a_flag": LOAD + [("vote", PAIR, vote(net=True))],
    "a_vote_whose_net_is_text": LOAD + [("vote", PAIR, vote(net="forty two"))],
    "a_vote_whose_net_is_a_number_in_text": LOAD + [("vote", PAIR, vote(net="12.7"))],
    "a_vote_whose_net_is_nothing": LOAD + [("vote", PAIR, vote(net=None))],
    "a_vote_whose_count_is_a_decimal": LOAD + [("vote", PAIR, vote(bull=12.7))],
    "a_vote_whose_count_is_a_flag": LOAD + [("vote", PAIR, vote(bull=True))],
    "a_vote_whose_count_is_not_a_number": LOAD + [("vote", PAIR, vote(bull=math.nan))],
    "a_vote_whose_count_is_infinity": LOAD + [("vote", PAIR, vote(bull=math.inf))],
    "a_vote_whose_count_is_a_number_in_text": LOAD
    + [("vote", PAIR, vote(bull="12.7"))],
    "a_vote_whose_count_is_a_very_big_whole_number": LOAD
    + [("vote", PAIR, vote(bull=10**400))],
    "a_vote_carrying_no_summary": LOAD + [("vote", PAIR, None)],
    "a_vote_for_a_bot_the_table_does_not_carry": LOAD + [("vote", "NOPE/USDC", vote())],
    "a_vote_after_a_refused_vote": LOAD
    + [("vote", PAIR, vote(bull=math.nan)), ("vote", PAIR, vote(net=-0.5))],
    "a_vote_written_three_times": LOAD
    + [
        ("vote", PAIR, vote(net=0.2)),
        ("vote", PAIR, vote(net=-0.2)),
        ("vote", PAIR, vote(net=0.0)),
    ],
    "expanded_once": [("expand", "Chart")],
    "expanded_twice": [("expand", "Chart"), ("expand", "Chart")],
    "expanded_then_closed": [("expand", "Chart"), ("collapse",)],
    "expanded_closed_and_expanded_again": [
        ("expand", "Chart"),
        ("collapse",),
        ("expand", "Chart"),
    ],
    "a_stale_claim_dropped": [("expand", "Chart"), ("stale",), ("expand", "Chart")],
}

SCENARIO_NAMES = sorted(SCENARIOS)

# The step sequences whose refusal both sides must report the same way.
REFUSING_SCENARIOS = (
    "a_not_a_number_where_a_timestamp_belongs",
    "a_number_too_big_for_a_float",
    "a_vote_whose_count_is_infinity",
    "nothing_where_a_price_belongs",
    "text_where_a_price_belongs",
    "ytd_start_as_infinity",
    "ytd_start_as_minus_infinity",
)


class Summary:
    """One voting-engine summary, built the same way for both sides."""

    def __init__(self, spec) -> None:
        for name, value in spec.items():
            setattr(self, name, value)


# Driving the shipped Qt widgets


def shipped_module():
    from src.gui.simulator_tab.fleet import sim_visuals

    return sim_visuals


def build_old():
    """The four shipped widgets, freshly built."""
    app()
    shipped = shipped_module()
    return {
        "panel": hold(shipped.GateStatusPanel()),
        "chart": hold(shipped.SimPriceVwapChart()),
        "votes": hold(shipped.PerBotVotingReadout()),
        "expand": {"claim": None, "calls": []},
    }


def build_new():
    """The four Qt-free models, freshly built."""
    return {
        "panel": surface.GatePanelModel(),
        "chart": surface.PriceVwapModel(),
        "votes": surface.VotingReadoutModel(),
        "expand": surface.ExpandModel(),
    }


def run_old_step(parts, step) -> None:
    """One step, driven into the shipped widgets."""
    kind = step[0]
    if kind == "symbols":
        parts["panel"].set_symbols(step[1])
        parts["chart"].set_symbols(list(step[1] or []))
        parts["votes"].set_bots(list(step[1] or []))
    elif kind == "gates":
        cell = parts["panel"].cell_for(step[1])
        if cell is not None:
            cell.update_gates(*step[2:])
    elif kind == "clear":
        cell = parts["panel"].cell_for(step[1])
        if cell is not None:
            cell.clear_gates()
    elif kind == "tick":
        parts["chart"].append_tick(*step[1:])
    elif kind == "mark":
        parts["chart"].mark_trade(step[1], step[2])
    elif kind == "clear_markers":
        parts["chart"].clear_markers(step[1])
    elif kind == "clear_data":
        parts["chart"].clear_data()
    elif kind == "focus":
        parts["chart"].set_focus_symbol(step[1])
    elif kind == "ytd":
        parts["chart"].set_ytd_start(step[1], step[2])
    elif kind == "vote":
        parts["votes"].update_bot_row(
            step[1], None if step[2] is None else Summary(step[2])
        )
    elif kind == "expand":
        run_old_expand(parts, step[1])
    elif kind == "collapse":
        run_old_collapse(parts)
    elif kind == "stale":
        parts["expand"]["claim"] = None
        parts["expand"]["calls"].append(surface.EXPAND_STALE_CLAIM_DROPPED)
    else:
        raise LookupError(kind)


def run_old_expand(parts, title) -> None:
    """The shipped expand guard, driven without opening a real window.

    ``_show_expanded`` builds a dialog and shows it. The guard it runs
    first is the behaviour the surface carries, so the guard is driven
    here and the window is not.
    """
    record = parts["expand"]
    if record["claim"] is not None:
        record["calls"].append(surface.EXPAND_RAISED)
        return
    record["claim"] = {"title": str(title)}
    record["calls"].append(surface.EXPAND_OPENED)


def run_old_collapse(parts) -> None:
    record = parts["expand"]
    record["claim"] = None
    record["calls"].append(surface.EXPAND_RESTORED)


def run_new_step(parts, step) -> None:
    """The same step, driven into the Qt-free models."""
    kind = step[0]
    if kind == "symbols":
        parts["panel"].set_symbols(step[1])
        parts["chart"].set_symbols(list(step[1] or []))
        parts["votes"].set_bots(list(step[1] or []))
    elif kind == "gates":
        row = parts["panel"].cell_for(step[1])
        if row is not None:
            row.update_gates(*step[2:])
    elif kind == "clear":
        row = parts["panel"].cell_for(step[1])
        if row is not None:
            row.clear_gates()
    elif kind == "tick":
        parts["chart"].append_tick(*step[1:])
    elif kind == "mark":
        parts["chart"].mark_trade(step[1], step[2])
    elif kind == "clear_markers":
        parts["chart"].clear_markers(step[1])
    elif kind == "clear_data":
        parts["chart"].clear_data()
    elif kind == "focus":
        parts["chart"].set_focus_symbol(step[1])
    elif kind == "ytd":
        parts["chart"].set_ytd_start(step[1], step[2])
    elif kind == "vote":
        parts["votes"].update_bot_row(
            step[1], None if step[2] is None else Summary(step[2])
        )
    elif kind == "expand":
        parts["expand"].open(step[1])
    elif kind == "collapse":
        parts["expand"].close()
    elif kind == "stale":
        parts["expand"].drop_stale_claim()
    else:
        raise LookupError(kind)


def drive(name, build, run_step):
    """Run one step sequence, reporting where it stopped if it refused."""
    parts = build()
    for index, step in enumerate(SCENARIOS[name]):
        try:
            run_step(parts, step)
        except Exception as exc:
            return parts, {
                "outcome": "refused",
                "step_index": index,
                "step_name": step[0],
                "error": type(exc).__name__,
            }
    return parts, {"outcome": "answered"}


# Reading the two sides


def gate_state_from_qt(cell) -> dict:
    return {
        "evaluated": cell._evaluated,
        "scrum_armed": cell._scrum_armed,
        "fold_armed": cell._fold_armed,
        "scrum_blocked": sorted(cell._scrum_blocked),
        "fold_blocked": sorted(cell._fold_blocked),
        "scrum_landing_strip": cell._ls_scrum,
        "fold_landing_strip": cell._fold_ls,
    }


def gate_state_from_model(row) -> dict:
    return {
        "evaluated": row.evaluated,
        "scrum_armed": row.scrum_armed,
        "fold_armed": row.fold_armed,
        "scrum_blocked": sorted(row.scrum_blocked),
        "fold_blocked": sorted(row.fold_blocked),
        "scrum_landing_strip": row.scrum_landing_strip,
        "fold_landing_strip": row.fold_landing_strip,
    }


def panel_items_from_qt(panel) -> list:
    """The pane's column, item by item, read off the layout it built."""
    layout = panel._host_lay
    found: list = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        held = item.widget()
        if held is None:
            found.append({"kind": "stretch"})
        elif held is panel._empty:
            found.append({"kind": "empty", "visible": not held.isHidden()})
        else:
            found.append(
                {"kind": "row", "symbol": held.layout().itemAt(0).widget().text()}
            )
    return found


def chart_state_from_qt(chart, symbols) -> dict:
    return {
        "symbols": list(chart._symbols),
        "focus": chart.focus_symbol(),
        "minimum_height_px": chart.minimumHeight(),
        "series": {repr(one): chart._series.get(one) for one in symbols},
        "vwap_window": {repr(one): chart._vwap_window.get(one) for one in symbols},
        "ordinals": {repr(one): chart._ordinals.get(one) for one in symbols},
        "next_ordinal": {repr(one): chart._next_ordinal.get(one) for one in symbols},
        "candles": {repr(one): chart._candles.get(one) for one in symbols},
        "ytd_from": {repr(one): chart._ytd_from.get(one) for one in symbols},
        "markers": {repr(one): list(chart._markers.get(one) or []) for one in symbols},
        "resolved": {repr(one): chart.resolved_markers(one) for one in symbols},
    }


def chart_state_from_model(chart, symbols) -> dict:
    return {
        "symbols": list(chart.symbols),
        "focus": chart.focus_symbol(),
        "minimum_height_px": chart.height_px,
        "series": {repr(one): chart.series.get(one) for one in symbols},
        "vwap_window": {repr(one): chart.vwap_window.get(one) for one in symbols},
        "ordinals": {repr(one): chart.ordinals.get(one) for one in symbols},
        "next_ordinal": {repr(one): chart.next_ordinal.get(one) for one in symbols},
        "candles": {repr(one): chart.candles.get(one) for one in symbols},
        "ytd_from": {repr(one): chart.ytd_from.get(one) for one in symbols},
        "markers": {repr(one): list(chart.markers.get(one) or []) for one in symbols},
        "resolved": {repr(one): chart.resolved_markers(one) for one in symbols},
    }


def votes_from_qt(table) -> list:
    """Every row, cell by cell, as the shipped table holds it.

    The direction colour is not read here. A colour off a live widget is
    the value it was told, not the one it paints, so the two sides are
    compared on that by the rendered picture instead.
    """
    found = []
    for row in range(table.rowCount()):
        cells = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            cells.append(None if item is None else item.text())
        found.append({"cells": cells})
    return found


def votes_from_model(votes) -> list:
    return [{"cells": list(row["cells"])} for row in votes.table()]


def canonical(colour) -> str:
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    app()
    return QColor(colour).name()


def old_trace(parts) -> dict:
    panel, chart, votes = parts["panel"], parts["chart"], parts["votes"]
    symbols = list(chart._symbols)
    return {
        "panel": {
            "accessible_name": panel.accessibleName(),
            "symbols": panel.symbols(),
            "items": panel_items_from_qt(panel),
            "rows": {
                one: gate_state_from_qt(panel.cell_for(one)) for one in panel.symbols()
            },
        },
        "chart": chart_state_from_qt(chart, symbols),
        "votes": votes_from_qt(votes),
        "expand": {
            "open": parts["expand"]["claim"] is not None,
            "calls": list(parts["expand"]["calls"]),
        },
    }


def new_trace(parts) -> dict:
    panel, chart, votes = parts["panel"], parts["chart"], parts["votes"]
    symbols = list(chart.symbols)
    return {
        "panel": {
            "accessible_name": surface.PANEL_ACCESSIBLE_NAME,
            "symbols": panel.symbols(),
            "items": panel.items(),
            "rows": {
                one: gate_state_from_model(panel.cell_for(one))
                for one in panel.symbols()
            },
        },
        "chart": chart_state_from_model(chart, symbols),
        "votes": votes_from_model(votes),
        "expand": {
            "open": parts["expand"].claim is not None,
            "calls": [
                one
                for one in parts["expand"].calls
                if one != surface.EXPAND_STALE_CLAIM_DROPPED
                or True  # every call is kept
            ],
        },
    }


def old_outcome(name) -> dict:
    parts, stopped = drive(name, build_old, run_old_step)
    return dict(stopped, trace=old_trace(parts))


def new_outcome(name) -> dict:
    parts, stopped = drive(name, build_new, run_new_step)
    return dict(stopped, trace=new_trace(parts))


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_screen(name):
    """A gate, a price, a candle, a vote or a layout number differs."""
    old = old_outcome(name)
    new = new_outcome(name)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        assert new["step_index"] == old["step_index"], (name, old, new)
        assert new["step_name"] == old["step_name"], (name, old, new)
    moved = differing_paths(as_text(old["trace"]), as_text(new["trace"]))
    assert moved == [], (name, moved)
    assert digest(old["trace"]) == digest(new["trace"]), name


def test_every_step_sequence_reaches_an_answer_or_a_refusal():
    """Every input was accepted, so no refusal was ever compared."""
    answered, refused = [], []
    for name in SCENARIO_NAMES:
        old = old_outcome(name)
        (answered if old["outcome"] == "answered" else refused).append(name)
    assert answered, "no step sequence was answered"
    assert refused, "no step sequence was refused"
    assert sorted(refused) == sorted(REFUSING_SCENARIOS), sorted(refused)
    assert len(answered) + len(refused) == len(SCENARIOS)


@pytest.mark.parametrize("name", REFUSING_SCENARIOS)
def test_a_sequence_that_refuses_part_way_reports_where_it_stopped(name):
    """A refusal moved, or one side kept driving after the other stopped."""
    old = old_outcome(name)
    new = new_outcome(name)
    assert (old["outcome"], new["outcome"]) == ("refused", "refused"), (old, new)
    assert new["error"] == old["error"], (old, new)
    assert new["step_index"] == old["step_index"], (old, new)
    assert new["step_name"] == old["step_name"], (old, new)
    assert old["step_index"] < len(SCENARIOS[name])


def test_a_refusal_keeps_what_the_recorder_had_already_recorded():
    """A refused step wiped the readings taken before it."""
    name = "text_where_a_price_belongs"
    old = old_outcome(name)
    assert old["outcome"] == "refused"
    assert old["trace"]["chart"]["symbols"] == FLEET
    assert old["trace"]["panel"]["symbols"] == sorted(FLEET)
    new = new_outcome(name)
    assert new["trace"]["chart"]["symbols"] == FLEET
    assert differing_paths(as_text(old["trace"]), as_text(new["trace"])) == []


def test_the_refusal_is_read_as_a_type_and_never_as_a_wording():
    """A refusal wording was compared, which states a fact about the build."""
    for name in REFUSING_SCENARIOS:
        old = old_outcome(name)
        assert set(old) == {"outcome", "step_index", "step_name", "error", "trace"}
        assert isinstance(old["error"], str)
        assert "message" not in old


DIFFERENT_PAIR = ("happy", "focused_with_ytd")


def test_two_real_inputs_driven_one_through_each_side_are_told_apart():
    """The comparison passes whatever the second side answers."""
    one, other = DIFFERENT_PAIR
    assert digest(old_outcome(one)["trace"]) != digest(new_outcome(other)["trace"])


def test_the_same_two_real_inputs_the_other_way_round_are_told_apart():
    """The comparison reports in one direction only."""
    one, other = DIFFERENT_PAIR
    assert digest(new_outcome(one)["trace"]) != digest(old_outcome(other)["trace"])


def test_one_real_input_driven_through_both_sides_hashes_alike():
    """The two sides answer differently for an input both accept."""
    for name in DIFFERENT_PAIR:
        assert digest(old_outcome(name)["trace"]) == digest(new_outcome(name)["trace"])


def test_the_same_input_driven_twice_through_one_side_hashes_alike():
    """One side answers differently on a second run of one input."""
    first = digest(old_outcome("happy")["trace"])
    again = digest(old_outcome("happy")["trace"])
    assert again == first
    mine = digest(new_outcome("happy")["trace"])
    mine_again = digest(new_outcome("happy")["trace"])
    assert mine_again == mine


def test_a_whole_number_and_its_decimal_are_read_as_their_own_symbols():
    """Two values a number check calls equal reached one row label."""
    assert 12 == 12.0
    whole = old_outcome("a_symbol_that_is_a_whole_number")["trace"]
    decimal = old_outcome("a_symbol_that_is_a_decimal")["trace"]
    assert whole["panel"]["symbols"] == ["12"]
    assert decimal["panel"]["symbols"] == ["12.0"]
    assert digest(whole) != digest(decimal)
    assert differing_paths(as_text(whole), as_text(decimal)) != []
    assert digest([12]) != digest([12.0])


def test_two_not_a_numbers_are_read_as_one_value_before_comparing():
    """A not-a-number in a price made two equal traces read as different."""
    two_of_them = [math.nan, math.nan]
    assert two_of_them[0] != two_of_them[1]
    one = old_outcome("series_carrying_a_not_a_number")["trace"]
    other = new_outcome("series_carrying_a_not_a_number")["trace"]
    assert math.isnan(one["chart"]["series"][repr(PAIR)][0][1])
    assert one != other
    assert differing_paths(as_text(one), as_text(other)) == []
    assert digest(one) == digest(other)


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given."""
    plain = old_outcome("built_only")["trace"]
    filled = old_outcome("happy")["trace"]
    assert plain != filled
    assert digest(plain) != digest(filled)
    assert digest(plain) == digest(old_outcome("built_only")["trace"])
    assert len(digest(plain)) == 64


def test_a_swapped_order_is_reported_by_the_hash():
    """Two rows changing places reads as no change at all."""
    loaded = old_outcome("fleet_loaded")["trace"]["panel"]["items"]
    swapped = [loaded[0], loaded[2], loaded[1], loaded[3], loaded[4]]
    assert loaded != swapped
    assert digest(loaded) != digest(swapped)
    assert differing_paths(as_text(loaded), as_text(swapped)) != []


@pytest.mark.parametrize(
    "name", ["built_only", "fleet_loaded", "happy", "focused_with_ytd", "data_cleared"]
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    old = old_outcome(name)["trace"]
    new = new_outcome(name)["trace"]
    assert set(old) == {"panel", "chart", "votes", "expand"}
    assert digest(old) == digest(new), (name, digest(old), digest(new))


# The rules the drawing rests on


def test_the_rolling_vwap_is_the_volume_weighted_mean_of_its_window():
    """The VWAP is a plain mean, or a sum, rather than volume-weighted."""
    window = [(10.0, 1.0), (20.0, 3.0)]
    assert surface.rolling_vwap(window, 99.0) == pytest.approx(17.5)
    assert surface.rolling_vwap(window, 99.0) != pytest.approx(15.0)
    assert surface.rolling_vwap([], 99.0) == 99.0
    assert surface.rolling_vwap([(10.0, 0.0)], 99.0) == 99.0
    assert surface.rolling_vwap([(10.0, -1.0)], 99.0) == 99.0


def test_the_window_holds_the_last_thirty_candles_and_no_more():
    """The VWAP window grew without bound, so it stopped being rolling."""
    chart = surface.PriceVwapModel()
    chart.set_symbols([PAIR])
    for index in range(surface.CHART_VWAP_WINDOW + 5):
        chart.append_tick(PAIR, 10.0 + index, 1.0)
    assert len(chart.vwap_window[PAIR]) == surface.CHART_VWAP_WINDOW
    assert chart.vwap_window[PAIR][-1][0] == 10.0 + surface.CHART_VWAP_WINDOW + 4


def test_a_flat_band_is_scaled_rather_than_dividing_by_zero():
    """A series whose values are all equal divided by a span of zero."""
    to_y = surface.scale(50.0, 50.0, 0, 100)
    assert to_y(50.0) == 100
    rising = surface.scale(0.0, 100.0, 0, 100)
    assert rising(100.0) == 0
    assert rising(0.0) == 100
    assert rising(50.0) == 50


def test_a_vote_on_the_line_is_neutral_and_a_hair_past_it_is_not():
    """The bull and bear lines moved, or one of them became inclusive."""
    assert surface.vote_direction(surface.VOTE_BULL_ABOVE) == surface.VOTE_NEUTRAL
    assert surface.vote_direction(surface.VOTE_BEAR_BELOW) == surface.VOTE_NEUTRAL
    assert surface.vote_direction(0.1000001) == surface.VOTE_BULL
    assert surface.vote_direction(-0.1000001) == surface.VOTE_BEAR
    assert surface.vote_direction(0.0) == surface.VOTE_NEUTRAL
    assert surface.vote_direction(math.inf) == surface.VOTE_BULL
    assert surface.vote_direction(-math.inf) == surface.VOTE_BEAR
    assert surface.vote_direction(math.nan) == surface.VOTE_NEUTRAL


def test_a_marked_candle_survives_the_decimation_that_halves_the_series():
    """A long replay quietly dropped the operator's own trades."""
    chart = surface.PriceVwapModel()
    chart.set_symbols([PAIR])
    for index in range(4):
        chart.append_tick(PAIR, 10.0 + index, 1.0)
    chart.mark_trade(PAIR, True)
    marked_at = chart.ordinals[PAIR][-1]
    assert marked_at % 2 == 1, "the marked candle sits on an even index, so no proof"
    for _ in range(surface.CHART_MAX_POINTS):
        chart.append_tick(PAIR, 20.0, 1.0)
    assert len(chart.series[PAIR][0]) < surface.CHART_MAX_POINTS
    assert marked_at in chart.ordinals[PAIR]
    assert surface.CHART_POINTS_DECIMATED in chart.calls
    assert len(chart.resolved_markers(PAIR)) == 1


def test_the_marker_store_keeps_the_live_end_when_it_fills():
    """An unbounded marker store grew for the whole replay."""
    store = surface.PriceVwapModel().new_marker_store()
    assert store.maxlen == surface.CHART_MAX_MARKERS
    for index in range(surface.CHART_MAX_MARKERS + 3):
        store.append((index, True))
    assert len(store) == surface.CHART_MAX_MARKERS
    assert store[-1][0] == surface.CHART_MAX_MARKERS + 2


def test_the_candle_buffer_keeps_the_live_end_when_it_fills():
    """The candle buffer grew for the whole replay."""
    chart = surface.PriceVwapModel()
    chart.set_symbols([PAIR])
    for index in range(surface.CHART_MAX_CANDLES + 3):
        chart.append_tick(PAIR, float(index), 1.0, index)
    assert len(chart.candles[PAIR]) == surface.CHART_MAX_CANDLES
    assert chart.candles[PAIR][-1][0] == surface.CHART_MAX_CANDLES + 2


def test_the_expand_geometry_is_full_width_and_half_height():
    """The expand dialog stopped filling the screen it opens over."""
    placed = surface.expand_geometry((0, 0, 1920, 1080))
    assert placed == {"width": 1920, "height": 540, "x": 0, "y": 270}
    offset = surface.expand_geometry((1920, 0, 1280, 720))
    assert offset == {"width": 1280, "height": 360, "x": 1920, "y": 180}


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
    return ast.parse(path.read_text(encoding="utf-8"))


def parsed_text(source: str):
    return ast.parse(source)


def bound_names(tree) -> dict:
    """Every name an import binds, mapped to the name it was imported as."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                found[alias.asname or alias.name.split(".")[0]] = alias.name
    return found


def connect_sites(tree) -> list:
    """Every ``.connect(`` site, as the signal and the target it names."""
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


def timers_built(tree) -> list:
    """Every timer the source CONSTRUCTS. An import line alone is not one."""
    return sorted(
        dotted(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    )


def timers_started_without_building(tree) -> list:
    """Every timer the source runs without holding one."""
    return sorted(
        dotted(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            dotted(node.func).endswith("singleShot")
            or dotted(node.func).endswith("startTimer")
        )
    )


def threads_built(tree) -> list:
    """Every worker thread the source CONSTRUCTS."""
    return sorted(
        dotted(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and dotted(node.func).split(".")[-1].endswith("Thread")
    )


def threads_started(tree) -> list:
    """Every ``.start(`` on a name that reads as a thread."""
    return sorted(
        dotted(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "start"
    )


def _called_names(tree, wanted: str) -> list:
    """Every call to a function named `wanted`, an import alias included.

    A bus reached through ``bus.subscribe(...)`` is an attribute call. One
    imported as ``from ... import subscribe as listen`` is a plain name, so
    the import table is read and the alias resolved back.
    """
    aliases = {
        name
        for name, real in bound_names(tree).items()
        if real.split(".")[-1] == wanted
    }
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == wanted:
            found.append(node)
        elif isinstance(node.func, ast.Name) and node.func.id in aliases:
            found.append(node)
    return found


def bus_subscribes(tree) -> list:
    """Every topic the source listens on."""
    return sorted(
        node.args[0].value
        for node in _called_names(tree, "subscribe")
        if node.args and isinstance(node.args[0], ast.Constant)
    )


def receiver_name(node) -> str:
    if isinstance(node, ast.Call):
        return dotted(node.func)
    return dotted(node)


def bus_emits(tree) -> list:
    """Every topic the source puts on the bus."""
    return sorted(
        node.args[0].value
        for node in _called_names(tree, "emit")
        if node.args
        and isinstance(node.args[0], ast.Constant)
        and (
            isinstance(node.func, ast.Name)
            or "bus" in receiver_name(node.func.value).lower()
        )
    )


def signals_declared(tree) -> list:
    """Every signal the source declares."""
    return sorted(
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and dotted(node.value.func).endswith("Signal")
        for target in node.targets
        if isinstance(target, ast.Name)
    )


def signal_emits(tree) -> list:
    """Every signal emission site, as the signal it names."""
    return sorted(
        dotted(node.func.value).rsplit(".", 1)[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "emit"
        and "bus" not in receiver_name(node.func.value).lower()
    )


def source_classes(tree) -> list:
    """Every class the source declares, one inside a method included."""
    return sorted(
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    )


def source_functions(tree) -> list:
    """Every function the source declares, nested ones included."""
    return sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def declared_members(holder) -> list:
    """Every method, property, static and class method `holder` declares."""
    from PySide6.QtCore import Signal

    found = []
    for name, value in vars(holder).items():
        if name.startswith("__") and name != "__init__":
            continue
        if isinstance(value, Signal):
            continue
        if isinstance(value, (property, staticmethod, classmethod)) or callable(value):
            found.append(name)
    return sorted(found)


SHIPPED_CLASSES = {
    "GateLightsCell": "GateLightsModel",
    "GateStatusPanel": "GatePanelModel",
    "PerBotVotingReadout": "VotingReadoutModel",
    "SimPriceVwapChart": "PriceVwapModel",
}

SHIPPED_MEMBERS = {
    "GateLightsCell.__init__": "GateLightsModel.__init__",
    "GateLightsCell.clear_gates": "GateLightsModel.clear_gates",
    "GateLightsCell.paintEvent": "gate_program",
    "GateLightsCell.update_gates": "GateLightsModel.update_gates",
    "GateLightsCell._draw_bank": "_gate_bank_program",
    "GateStatusPanel.__init__": "GatePanelModel.__init__",
    "GateStatusPanel.cell_for": "GatePanelModel.cell_for",
    "GateStatusPanel.set_symbols": "GatePanelModel.set_symbols",
    "GateStatusPanel.symbols": "GatePanelModel.symbols",
    "PerBotVotingReadout.__init__": "VotingReadoutModel.__init__",
    "PerBotVotingReadout.set_bots": "VotingReadoutModel.set_bots",
    "PerBotVotingReadout.update_bot_row": "VotingReadoutModel.update_bot_row",
    "SimPriceVwapChart.__init__": "PriceVwapModel.__init__",
    "SimPriceVwapChart._apply_height": "PriceVwapModel.apply_height",
    "SimPriceVwapChart._draw_focused": "focused_program",
    "SimPriceVwapChart._new_marker_store": "PriceVwapModel.new_marker_store",
    "SimPriceVwapChart.append_tick": "PriceVwapModel.append_tick",
    "SimPriceVwapChart.clear_data": "PriceVwapModel.clear_data",
    "SimPriceVwapChart.clear_markers": "PriceVwapModel.clear_markers",
    "SimPriceVwapChart.focus_symbol": "PriceVwapModel.focus_symbol",
    "SimPriceVwapChart.mark_trade": "PriceVwapModel.mark_trade",
    "SimPriceVwapChart.paintEvent": "chart_program",
    "SimPriceVwapChart.resolved_markers": "PriceVwapModel.resolved_markers",
    "SimPriceVwapChart.set_focus_symbol": "PriceVwapModel.set_focus_symbol",
    "SimPriceVwapChart.set_symbols": "PriceVwapModel.set_symbols",
    "SimPriceVwapChart.set_ytd_start": "PriceVwapModel.set_ytd_start",
}

SHIPPED_FUNCTIONS = {"_show_expanded": "ExpandModel.open", "_band_span": "band_span"}

NESTED_FUNCTIONS = {
    "_restore": "ExpandModel.close",
    "_band": "scale",
    "_proj": "band_program",
}

SURFACE_CLASSES = {
    "ExpandModel": "_show_expanded",
    "GateLightsModel": "GateLightsCell",
    "GatePanelModel": "GateStatusPanel",
    "GateRow": "GateStatusPanel",
    "PriceVwapModel": "SimPriceVwapChart",
    "VotingReadoutModel": "PerBotVotingReadout",
}


def surface_counterpart(name):
    """The surface object one counterpart name points at."""
    holder, _, attribute = name.partition(".")
    target = getattr(surface, holder)
    return getattr(target, attribute) if attribute else target


def test_the_visuals_wire_one_action_and_the_surface_names_one():
    """The shipped file wires an action the surface names none of."""
    sites = connect_sites(parsed(SHIPPED_SOURCE))
    assert len(sites) == len(surface.ACTIONS), (sites, surface.ACTIONS)


def test_the_wiring_counter_reads_the_signal_and_the_target():
    """POSITIVE CONTROL over a fixture, not over a shipped file."""
    wiring = "self.clicked.connect(self._on_click)\n"
    assert connect_sites(parsed_text(wiring)) == [("self.clicked", "self._on_click")]
    assert connect_sites(parsed_text("x = 1\n")) == []


def test_one_wiring_line_makes_one_connection_each_time_it_runs():
    """A source line inside a loop makes several connections at run time."""
    app()
    from PySide6.QtWidgets import QDialog

    fired = []
    quiet = hold(QDialog())
    quiet.finished.emit(0)
    assert fired == [], "the counter reports a wire nobody made"
    wired = []
    for _ in range(3):
        dialog = hold(QDialog())
        dialog.finished.connect(fired.append)
        wired.append(dialog)
    for dialog in wired:
        dialog.finished.emit(0)
    assert len(fired) == 3, fired
    assert len(connect_sites(parsed_text("d.finished.connect(f)\n"))) == 1


def test_the_visuals_declare_no_signal_and_emit_none():
    """The shipped file declares a signal the surface names none of."""
    tree = parsed(SHIPPED_SOURCE)
    assert signals_declared(tree) == []
    assert signal_emits(tree) == []
    assert surface.SIGNALS == ()


def test_the_signal_counter_reads_a_declaration_and_an_emit():
    """POSITIVE CONTROL over a fixture, not over a shipped file."""
    declaring = (
        "from PySide6.QtCore import Signal\n"
        "class Card:\n"
        "    clicked = Signal(str)\n"
        "    def fire(self):\n"
        "        self.clicked.emit('x')\n"
    )
    assert len(signals_declared(parsed_text(declaring))) == 1
    assert signal_emits(parsed_text(declaring)) != []


def test_the_visuals_build_no_timer_and_start_none():
    """The shipped file runs a timer the surface declares no delay for."""
    tree = parsed(SHIPPED_SOURCE)
    assert timers_built(tree) == []
    assert timers_started_without_building(tree) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()


def test_the_timer_counter_counts_a_construction_and_not_a_name():
    """POSITIVE CONTROL over a fixture. An import of ``QTimer`` names it
    without building one, and ``startTimer`` starts one without a
    construction."""
    naming = "from PySide6.QtCore import QTimer\n"
    assert timers_built(parsed_text(naming)) == []
    assert naming.count("QTimer") == 1
    building = naming + "t = QTimer(None)\n"
    assert timers_built(parsed_text(building)) == ["QTimer"]
    started = "class W:\n    def go(self):\n        self.startTimer(50)\n"
    assert len(timers_started_without_building(parsed_text(started))) == 1


def test_the_construction_counter_cannot_see_a_word_inside_a_comment():
    """A construction written in prose was counted as a real one."""
    prose = "# QTimer(self) in a comment\nimport re\n"
    assert timers_built(parsed_text(prose)) == []
    assert prose.count("QTimer(") == 1
    real = "from PySide6.QtCore import QTimer\nt = QTimer(None)\n"
    assert timers_built(parsed_text(real)) == ["QTimer"]


def test_the_visuals_own_no_thread_in_either_form():
    """The shipped file starts a worker the cleanup cannot reach."""
    tree = parsed(SHIPPED_SOURCE)
    assert threads_built(tree) == []
    assert threads_started(tree) == []


def test_the_thread_counter_reads_a_build_and_a_start():
    """POSITIVE CONTROL over a fixture, not over a shipped file."""
    owning = (
        "import threading\n"
        "worker = threading.Thread(target=None)\n"
        "worker.start()\n"
    )
    assert threads_built(parsed_text(owning)) == ["threading.Thread"]
    assert len(threads_started(parsed_text(owning))) == 1


def test_the_visuals_touch_no_bus_in_either_direction():
    """The shipped file listens or speaks on a bus the surface names none of."""
    tree = parsed(SHIPPED_SOURCE)
    assert bus_subscribes(tree) == []
    assert bus_emits(tree) == []
    assert surface.BUS_TOPICS == ()
    assert surface.BUS_EMITS == ()


def test_the_bus_counter_reads_a_subscribe_and_an_emit():
    """POSITIVE CONTROL over a fixture, not over a shipped file."""
    both = "bus.subscribe('wire.created', h)\nbus.emit('wire.created', {})\n"
    assert bus_subscribes(parsed_text(both)) == ["wire.created"]
    assert bus_emits(parsed_text(both)) == ["wire.created"]


def test_the_bus_counter_still_counts_a_topic_reached_through_an_alias():
    """An imported alias slipped past the counter, so a topic read as absent."""
    plain = "bus.subscribe('a.topic', handler)\n"
    assert bus_subscribes(parsed_text(plain)) == ["a.topic"]
    aliased = (
        "from src.core.event_bus import subscribe as listen\n"
        "bus.subscribe('a.topic', handler)\n"
        "listen('another.topic', handler)\n"
    )
    assert bus_subscribes(parsed_text(aliased)) == ["a.topic", "another.topic"]
    assert len(bus_subscribes(parsed_text(aliased))) > len(
        bus_subscribes(parsed_text(plain))
    )
    aliased_emit = (
        "from src.core.event_bus import emit as announce\n"
        "announce('a.topic', {})\n"
        "bus.emit('another.topic', {})\n"
    )
    assert bus_emits(parsed_text(aliased_emit)) == ["a.topic", "another.topic"]


def test_every_shipped_class_method_and_function_has_a_counterpart():
    """The shipped file gained or lost a class, a method or a function."""
    shipped = shipped_module()
    tree = parsed(SHIPPED_SOURCE)
    assert source_classes(tree) == sorted(SHIPPED_CLASSES), source_classes(tree)
    found = []
    for class_name in sorted(SHIPPED_CLASSES):
        found.extend(
            f"{class_name}.{name}"
            for name in declared_members(getattr(shipped, class_name))
        )
    assert sorted(found) == sorted(SHIPPED_MEMBERS), sorted(found)
    top_level = sorted(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    assert top_level == sorted(SHIPPED_FUNCTIONS), top_level
    nested = sorted(
        set(source_functions(tree))
        - set(SHIPPED_FUNCTIONS)
        - {name.partition(".")[2] for name in SHIPPED_MEMBERS}
    )
    assert nested == sorted(NESTED_FUNCTIONS), nested
    counterparts = (
        list(SHIPPED_CLASSES.values())
        + list(SHIPPED_MEMBERS.values())
        + list(SHIPPED_FUNCTIONS.values())
        + list(NESTED_FUNCTIONS.values())
    )
    for name in counterparts:
        assert callable(surface_counterpart(name)), name


def test_a_signal_is_not_counted_as_a_method_and_a_property_is():
    """A signal read as a method, or a property was missed."""
    app()
    from PySide6.QtCore import Signal
    from src.gui.launcher import ModeCard

    declared = vars(ModeCard)
    assert "clicked" in declared and isinstance(declared["clicked"], Signal)
    assert callable(declared["clicked"]), "the signal is not callable, so no proof"
    assert "clicked" not in declared_members(ModeCard)

    class Holder:
        @property
        def value(self):
            return 1

    assert not callable(vars(Holder)["value"])
    assert declared_members(Holder) == ["value"]
    with pytest.raises(AttributeError):
        surface_counterpart("InventedModel")


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """A class built inside a method reads as no class at all."""
    inner = "def build():\n    class Hidden:\n        pass\n    return Hidden\n"
    assert source_classes(parsed_text(inner)) == ["Hidden"]
    assert [
        node.name for node in parsed_text(inner).body if isinstance(node, ast.ClassDef)
    ] == []
    assert len(source_classes(parsed(NESTED_CLASS_NEIGHBOUR))) == 4


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    for name, replaced in SURFACE_CLASSES.items():
        assert replaced in SHIPPED_CLASSES or replaced in SHIPPED_FUNCTIONS, name


def test_the_surface_grew_no_name_the_file_does_not_declare():
    """A name on the module is in no source, or a source name never binds."""
    tree = parsed(SURFACE_SOURCE)
    declared = set(source_classes(tree)) | {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    imported = set(bound_names(tree))
    on_module = {
        name
        for name, value in vars(surface).items()
        if callable(value)
        and getattr(value, "__module__", None) == surface.__name__
        and not isinstance(value, type)
    } | {
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    }
    assert on_module - declared == set(), sorted(on_module - declared)
    assert declared - on_module - imported == set(), sorted(declared - on_module)
    assert "scale" in on_module and "scale" in declared


def test_the_growth_check_reports_a_name_on_one_side_only():
    """The growth check compares nothing, so it passes either way."""
    tree = parsed_text("def kept():\n    pass\n\n\ndef dropped():\n    pass\n")
    declared = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert declared == {"kept", "dropped"}
    assert declared - {"kept"} == {"dropped"}
    assert {"kept", "invented"} - declared == {"invented"}


# The completeness check


def named_payloads() -> dict:
    """The view models the completeness check reads."""
    pitch = measured_pitch_px()
    plain = build_new()
    filled = build_new()
    for step in SCENARIOS["happy"]:
        run_new_step(filled, step)
    focused = build_new()
    for step in SCENARIOS["focused_with_ytd"]:
        run_new_step(focused, step)
    focused["expand"].open("Chart")
    return {
        "built": surface.build_view_model(gate_pitch=pitch),
        "plain": surface.build_view_model(
            panel=plain["panel"],
            chart=plain["chart"],
            votes=plain["votes"],
            expand=plain["expand"],
            gate_pitch=pitch,
        ),
        "filled": surface.build_view_model(
            panel=filled["panel"],
            chart=filled["chart"],
            votes=filled["votes"],
            expand=filled["expand"],
            width_px=CHART_PIXEL_SIZE[0],
            height_px=CHART_PIXEL_SIZE[1],
            gate_pitch=pitch,
        ),
        "focused": surface.build_view_model(
            panel=focused["panel"],
            chart=focused["chart"],
            votes=focused["votes"],
            expand=focused["expand"],
            width_px=CHART_PIXEL_SIZE[0],
            height_px=CHART_PIXEL_SIZE[1],
            gate_pitch=pitch,
        ),
    }


PAYLOAD_KEYS = {
    "ACTIONS": "built:actions",
    "BUS_EMITS": "built:bus_emits",
    "BUS_TOPICS": "built:bus_topics",
    "CALL_NAMES": "built:call_names",
    "CHART_ACCESSIBLE_DESCRIPTION": "built:chart.accessible_description",
    "CHART_ACCESSIBLE_NAME": "built:chart.accessible_name",
    "CHART_BAND_HEIGHT_PX": "built:chart.band_height_px",
    "CHART_CANDLE_GAP_PX": "built:chart.candle_gap_px",
    "CHART_CANDLE_WIDTH_PX": "built:chart.candle_width_px",
    "CHART_FOCUS_MIN_HEIGHT_PX": "built:chart.focus_min_height_px",
    "CHART_LABEL_WIDTH_PX": "built:chart.label_width_px",
    "CHART_MAX_CANDLES": "built:chart.max_candles",
    "CHART_MAX_MARKERS": "built:chart.max_markers",
    "CHART_MAX_POINTS": "built:chart.max_points",
    "CHART_SIZE_POLICY": "built:chart.size_policy",
    "CHART_STYLE": "built:chart.style_sheet",
    "CHART_TOOLTIP": "built:chart.tooltip",
    "CHART_VWAP_WINDOW": "built:chart.vwap_window",
    "EXPAND_CLAIM_FIELD": "built:expand.claim_field",
    "EXPAND_DELETE_ON_CLOSE": "built:expand.delete_on_close",
    "EXPAND_MARGINS_PX": "built:expand.margins_px",
    "EXPAND_STYLE": "built:expand.style_sheet",
    "GATE_FONT_PT": "built:gate_row.font_pt",
    "GATE_LABEL_COLOUR": "built:gate_row.label_colour",
    "GATE_MARKER_COLOUR": "built:gate_row.marker_colour",
    "GATE_ORDER": "built:gate_row.banks",
    "GATE_TOOLTIP": "built:gate_row.tooltip",
    "LIGHT_COLORS": "built:gate_row.light_colours",
    "LIGHT_COLOURS_BY_STATE": "built:gate_row.light_colours",
    "METHOD": "built:method",
    "PANEL_ACCESSIBLE_NAME": "built:gate_panel.accessible_name",
    "PANEL_EMPTY_STYLE": "built:gate_panel.empty_style",
    "PANEL_EMPTY_TEXT": "built:gate_panel.empty_text",
    "PANEL_HOST_MARGINS_PX": "built:gate_panel.host_margins_px",
    "PANEL_HOST_SPACING_PX": "built:gate_panel.host_spacing_px",
    "PANEL_LABEL_MIN_WIDTH_PX": "built:gate_panel.label_min_width_px",
    "PANEL_LABEL_STYLE": "built:gate_panel.label_style",
    "PANEL_MARGINS_PX": "built:gate_panel.margins_px",
    "PANEL_ROW_MARGINS_PX": "built:gate_panel.row_margins_px",
    "PANEL_ROW_SPACING_PX": "built:gate_panel.row_spacing_px",
    "PANEL_SCROLL_RESIZABLE": "built:gate_panel.scroll_resizable",
    "PANEL_SCROLL_STYLE": "built:gate_panel.scroll_style",
    "PANEL_SPACING_PX": "built:gate_panel.spacing_px",
    "PANEL_TRAILING_STRETCH": "built:gate_panel.trailing_stretch",
    "SIGNALS": "built:signals",
    "TIMERS": "built:timers",
    "TIMER_DELAYS_MS": "built:timer_delays_ms",
    "VOTE_ALTERNATE_ROW_COLOUR": "built:votes.alternate_row_colour",
    "VOTE_ALTERNATING_ROWS": "built:votes.alternating_rows",
    "VOTE_HEADER_HEIGHT_PX": "built:votes.header_height_px",
    "VOTE_ROW_HEIGHT_PX": "built:votes.row_height_px",
    "VOTE_ACCESSIBLE_DESCRIPTION": "built:votes.accessible_description",
    "VOTE_ACCESSIBLE_NAME": "built:votes.accessible_name",
    "VOTE_COLUMNS": "built:votes.columns",
    "VOTE_COLUMN_MODE": "built:votes.column_mode",
    "VOTE_EDIT_TRIGGERS": "built:votes.edit_triggers",
    "VOTE_PLACEHOLDER": "built:votes.placeholder",
    "VOTE_ROW_HEADER_VISIBLE": "built:votes.row_header_visible",
    "VOTE_SELECTION_BEHAVIOUR": "built:votes.selection_behaviour",
    "VOTE_STRETCH_LAST_COLUMN": "built:votes.stretch_last_column",
    "VOTE_STYLE": "built:votes.style_sheet",
    "VOTE_SYMBOL_COLUMN_MODE": "built:votes.symbol_column_mode",
    "VOTE_TOOLTIP": "built:votes.tooltip",
}

# Values a payload carries inside a longer value rather than alone.
CARRIED_INSIDE = {
    "GATE_BANKS": "built:gate_row.banks",
    "GATE_SCRUM_BANK": "built:gate_row.banks",
    "GATE_FOLD_BANK": "built:gate_row.banks",
    "GATE_LED_PX": "built:gate_row.pitch_px",
    "GATE_PAD_PX": "built:gate_row.min_width_px",
    "GATE_GAP_PX": "built:gate_row.pitch_px",
    "GATE_BANK_GAP_PX": "built:gate_row.min_width_px",
    "GATE_LABEL_HEIGHT_PX": "built:gate_row.height_px",
    "GATE_COUNT": "built:gate_row.min_width_px",
}

# Every branch marker, each carried inside call_names.
CALL_CONSTANTS = tuple(sorted(surface.CALL_NAMES))

# The values no snapshot key carries, with the check that covers each.
NOT_IN_THE_SNAPSHOT = {
    "ALIGN_LABEL": "test_the_gate_row_program_places_every_light_on_its_pitch",
    "ALIGN_MARKER": "test_the_gate_row_program_places_every_light_on_its_pitch",
    "ALIGN_SYMBOL": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_BAND_INSET_PX": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_BAND_RIGHT_PX": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_FLAT_SPAN": "test_a_flat_band_is_scaled_rather_than_dividing_by_zero",
    "CHART_FRAME_COLOUR": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_LABEL_INSET_PX": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_MARKER_MISSED_COLOUR": "test_the_two_marker_colours_are_told_apart",
    "CHART_MARKER_OK_COLOUR": "test_the_two_marker_colours_are_told_apart",
    "CHART_MARKER_RADIUS_PX": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_MIN_LINE_POINTS": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_PRICE_COLOUR": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_SEPARATOR_COLOUR": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_SYMBOL_COLOUR": "test_the_band_program_draws_one_band_per_symbol",
    "CHART_VWAP_COLOUR": "test_the_band_program_draws_one_band_per_symbol",
    "DASH_LINE": "test_the_focused_program_bisects_the_panel",
    "ELLIPSE": "test_the_gate_row_program_places_every_light_on_its_pitch",
    "EXPAND_CALL_NAMES": "test_every_branch_marker_fires_and_ties_to_a_step",
    "CHART_CALL_NAMES": "test_every_branch_marker_fires_and_ties_to_a_step",
    "VOTE_CALL_NAMES": "test_every_branch_marker_fires_and_ties_to_a_step",
    "FILL": "test_the_focused_program_bisects_the_panel",
    "FOCUS_AXIS_COLOUR": "test_the_focused_program_bisects_the_panel",
    "FOCUS_BARS_LABEL_DROP_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_BARS_LABEL_INSET_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_BARS_SUFFIX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_BASELINE_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_CANDLE_DOWN_COLOUR": "test_a_falling_candle_paints_the_down_colour",
    "FOCUS_CANDLE_HEADING": "test_the_focused_program_bisects_the_panel",
    "FOCUS_CANDLE_UP_COLOUR": "test_a_falling_candle_paints_the_down_colour",
    "FOCUS_FOOT_ROOM_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_GAP_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_HEADING_COLOUR": "test_the_focused_program_bisects_the_panel",
    "FOCUS_HEADING_LIFT_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_HEAD_ROOM_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_HIGH_LABEL_INSET_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_MARKER_MISSED_COLOUR": "test_the_two_marker_colours_are_told_apart",
    "FOCUS_MARKER_OK_COLOUR": "test_the_two_marker_colours_are_told_apart",
    "FOCUS_MARKER_RADIUS_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_MIN_BAND_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_PAD_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_PRICE_COLOUR": "test_the_focused_program_bisects_the_panel",
    "FOCUS_PRICE_FORMAT": "test_the_focused_program_bisects_the_panel",
    "FOCUS_PRICE_HEADING_SUFFIX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_TOP_Y_PX": "test_the_focused_program_bisects_the_panel",
    "FOCUS_WAITING_COLOUR": "test_a_focused_chart_with_no_candle_says_so",
    "FOCUS_WAITING_SUFFIX": "test_a_focused_chart_with_no_candle_says_so",
    "FOCUS_WAITING_Y_PX": "test_a_focused_chart_with_no_candle_says_so",
    "FOCUS_YTD_FILL_RGBA": "test_the_ytd_overlay_starts_at_the_first_documented_trade",
    "FOCUS_YTD_LABEL": "test_the_ytd_overlay_starts_at_the_first_documented_trade",
    "FOCUS_YTD_TEXT_DROP_PX": (
        "test_the_ytd_overlay_starts_at_the_first_documented_trade"
    ),
    "FOCUS_YTD_TEXT_INSET_PX": (
        "test_the_ytd_overlay_starts_at_the_first_documented_trade"
    ),
    "LANDING_STRIP_FOLD": "test_a_landing_strip_paints_its_own_bank_and_no_other",
    "LANDING_STRIP_SCRUM": "test_a_landing_strip_paints_its_own_bank_and_no_other",
    "LINE": "test_the_band_program_draws_one_band_per_symbol",
    "NO_BRUSH": "test_the_band_program_draws_one_band_per_symbol",
    "NO_PEN": "test_the_gate_row_program_places_every_light_on_its_pitch",
    "RECT": "test_the_band_program_draws_one_band_per_symbol",
    "SOLID_LINE": "test_the_band_program_draws_one_band_per_symbol",
    "TEXT": "test_the_gate_row_program_places_every_light_on_its_pitch",
    "VOTE_BEAR": "test_a_vote_on_the_line_is_neutral_and_a_hair_past_it_is_not",
    "VOTE_BEAR_BELOW": "test_a_vote_on_the_line_is_neutral_and_a_hair_past_it_is_not",
    "VOTE_BEAR_COLOUR": "test_the_three_direction_colours_are_told_apart",
    "VOTE_BULL": "test_a_vote_on_the_line_is_neutral_and_a_hair_past_it_is_not",
    "VOTE_BULL_ABOVE": "test_a_vote_on_the_line_is_neutral_and_a_hair_past_it_is_not",
    "VOTE_BULL_COLOUR": "test_the_three_direction_colours_are_told_apart",
    "VOTE_CONF_FORMAT": "test_the_written_row_carries_the_formats_the_table_uses",
    "VOTE_COUNT_FORMAT": "test_the_written_row_carries_the_formats_the_table_uses",
    "VOTE_DIRECTION_COLOURS": "test_the_three_direction_colours_are_told_apart",
    "VOTE_NET_FORMAT": "test_the_written_row_carries_the_formats_the_table_uses",
    "VOTE_NEUTRAL": "test_a_vote_on_the_line_is_neutral_and_a_hair_past_it_is_not",
    "VOTE_NEUTRAL_COLOUR": "test_the_three_direction_colours_are_told_apart",
}

# Snapshot keys built from other values rather than carrying one.
DERIVED_KEYS = {
    "gate_panel": "test_the_two_sides_describe_the_same_screen",
    "gate_row": "test_the_gate_row_program_places_every_light_on_its_pitch",
    "chart": "test_the_band_program_draws_one_band_per_symbol",
    "votes": "test_the_written_row_carries_the_formats_the_table_uses",
    "expand": "test_the_expand_geometry_is_full_width_and_half_height",
}


def at_path(payloads, path):
    """The value one ``name:dotted.path`` names."""
    name, _, dotted_path = path.partition(":")
    found = payloads[name]
    for step in dotted_path.split("."):
        found = found[int(step)] if step.isdigit() else found[step]
    return found


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


def as_json_shape(value):
    """`value` with every tuple turned into the list a payload carries."""
    if isinstance(value, (list, tuple)):
        return [as_json_shape(inner) for inner in value]
    if isinstance(value, dict):
        return {key: as_json_shape(inner) for key, inner in value.items()}
    return value


def carried_values(value, seen=None) -> set:
    """Every leaf value a payload holds, at every depth."""
    if seen is None:
        seen = set()
    if isinstance(value, dict):
        for inner in value.values():
            carried_values(inner, seen)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            carried_values(inner, seen)
    else:
        try:
            seen.add(value)
        except TypeError:
            pass
    return seen


def unaccounted_constants(payloads, constants) -> list:
    """The exported values that reach no snapshot and no named check."""
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payloads, PAYLOAD_KEYS[name]) == as_json_shape(value), name
        elif name in CARRIED_INSIDE:
            assert value is not None, name
        elif name in CALL_CONSTANTS_BY_VALUE:
            assert value in payloads["built"]["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    return unaccounted


CALL_CONSTANTS_BY_VALUE = {
    name
    for name, value in vars(surface).items()
    if isinstance(value, str) and value in surface.CALL_NAMES
}


def unbacked_keys(built) -> set:
    """The snapshot keys no exported value and no named check backs."""
    answered = {path.partition(":")[2].split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {
        path.partition(":")[2].split(".")[0] for path in CARRIED_INSIDE.values()
    }
    answered.add("call_names")
    return set(built) ^ (answered | set(DERIVED_KEYS))


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read."""
    constants = surface_constants()
    found = unaccounted_constants(named_payloads(), constants)
    assert found == [], found
    counted = (
        set(PAYLOAD_KEYS)
        | set(CARRIED_INSIDE)
        | CALL_CONSTANTS_BY_VALUE
        | set(NOT_IN_THE_SNAPSHOT)
    )
    assert set(constants) == counted, sorted(set(constants) ^ counted)


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    built = named_payloads()["built"]
    assert unbacked_keys(built) == set(), sorted(unbacked_keys(built))
    for key, covered_by in DERIVED_KEYS.items():
        assert key in built
        assert callable(globals()[covered_by]), (key, covered_by)


def test_both_completeness_checks_report_what_they_are_given():
    """Both completeness checks passed because they look at nothing."""
    payloads = named_payloads()
    constants = dict(surface_constants())
    constants["INVENTED_CONSTANT"] = "never in any snapshot"
    assert unaccounted_constants(payloads, constants) == ["INVENTED_CONSTANT"]
    assert unaccounted_constants(payloads, surface_constants()) == []
    grown = dict(payloads["built"])
    grown["invented_key"] = 1
    assert unbacked_keys(grown) == {"invented_key"}
    assert unbacked_keys(payloads["built"]) == set()
    shrunk = {key: value for key, value in payloads["built"].items() if key != "method"}
    assert unbacked_keys(shrunk) == {"method"}
    assert "build_view_model" not in surface_constants()
    assert "PriceVwapModel" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payloads, "built:chart.invented")


def test_the_carried_values_reader_finds_a_value_at_any_depth():
    """The reader looks at the top level only, so a nested value is missed."""
    held = carried_values({"a": [1, {"b": "deep"}], "c": (2.5,)})
    assert "deep" in held and 1 in held and 2.5 in held
    assert "shallow" not in held


# The surface carries its own values

MOVED_VALUES = {
    "_BAND_HEIGHT": ("SimPriceVwapChart", 999),
    "_MAX_POINTS": ("SimPriceVwapChart", 7),
    "_VWAP_WINDOW": ("SimPriceVwapChart", 2),
    "_LED": ("GateLightsCell", 77),
    "_GROUP_GAP": ("GateLightsCell", 88),
}


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_file(monkeypatch):
    """The surface read its values off the widgets it replaces."""
    app()
    shipped = shipped_module()
    for name, (holder, moved) in MOVED_VALUES.items():
        before = getattr(getattr(shipped, holder), name)
        monkeypatch.setattr(getattr(shipped, holder), name, moved)
        assert getattr(getattr(shipped, holder), name) == moved
        assert surface.CHART_BAND_HEIGHT_PX == 36
        assert surface.CHART_MAX_POINTS == 500
        assert surface.CHART_VWAP_WINDOW == 30
        assert surface.GATE_LED_PX == 9
        assert surface.GATE_BANK_GAP_PX == 12
        monkeypatch.undo()
        assert getattr(getattr(shipped, holder), name) == before


def test_the_comparison_names_exactly_which_value_moved(monkeypatch):
    """The comparison reports every path, or none, whatever moved."""
    app()
    shipped = shipped_module()
    before = old_outcome("fleet_loaded")["trace"]
    monkeypatch.setattr(shipped.SimPriceVwapChart, "_BAND_HEIGHT", 999)
    moved = old_outcome("fleet_loaded")["trace"]
    assert differing_paths(as_text(before), as_text(moved)) == [
        "'chart'.'minimum_height_px'"
    ]
    monkeypatch.undo()
    assert digest(old_outcome("fleet_loaded")["trace"]) == digest(before)
    mine = new_outcome("fleet_loaded")["trace"]
    assert differing_paths(as_text(before), as_text(mine)) == []


def test_the_surface_does_not_follow_a_vocabulary_that_lost_a_gate(monkeypatch):
    """One vocabulary feeds both sides, so a lost gate must move both."""
    from src.trading import gate_vocabulary

    app()
    before = old_outcome("gates_read_once")["trace"]
    monkeypatch.setattr(gate_vocabulary, "_BLOCKER_PREFIXES", ())
    stripped = old_outcome("gates_read_once")["trace"]
    assert stripped != before
    assert (
        differing_paths(
            as_text(stripped), as_text(new_outcome("gates_read_once")["trace"])
        )
        == []
    )
    monkeypatch.undo()
    assert digest(old_outcome("gates_read_once")["trace"]) == digest(before)


# The draw programs


def gate_row_after(steps) -> surface.GateLightsModel:
    row = surface.GateLightsModel()
    for step in steps:
        row.update_gates(*step)
    return row


def test_the_gate_row_program_places_every_light_on_its_pitch():
    """A light landed on its neighbour's pitch, or lost its label."""
    pitch = measured_pitch_px()
    row = gate_row_after([(True, False, SCRUM_BLOCKERS, FOLD_BLOCKERS, "")])
    program = surface.gate_program(row, pitch)
    lights = [one for one in program if one["op"] == surface.ELLIPSE]
    labels = [one for one in program if one["op"] == surface.TEXT]
    assert len(lights) == surface.GATE_COUNT == 19
    assert len(labels) == surface.GATE_COUNT + len(surface.GATE_BANKS)
    scrum_count = len(surface.GATE_ORDER[surface.GATE_SCRUM_BANK])
    markers = [one for one in labels if one["align"] == surface.ALIGN_MARKER]
    assert [one["text"] for one in markers] == list(surface.GATE_BANKS)
    assert labels[scrum_count]["text"] == surface.GATE_SCRUM_BANK
    assert labels[-1]["text"] == surface.GATE_FOLD_BANK
    assert all(one["pen"] == surface.NO_PEN for one in lights)
    gate_labels = labels[:scrum_count] + labels[scrum_count + 1 : -1]
    assert len(gate_labels) == surface.GATE_COUNT
    assert all(one["align"] == surface.ALIGN_LABEL for one in gate_labels)
    box = pitch - surface.GATE_GAP_PX
    first = lights[0]["rect"]
    assert first[0] == surface.GATE_PAD_PX + (box - surface.GATE_LED_PX) // 2
    assert first[1] == surface.GATE_PAD_PX + surface.GATE_LABEL_HEIGHT_PX
    assert first[2] == first[3] == surface.GATE_LED_PX
    scrum_last = lights[len(surface.GATE_ORDER["S"]) - 1]["rect"][0]
    fold_first = lights[len(surface.GATE_ORDER["S"])]["rect"][0]
    assert fold_first - scrum_last == pitch + surface.GATE_BANK_GAP_PX


def test_the_gate_row_matches_the_geometry_the_shipped_cell_measured():
    """The surface's step, height or width differs from the widget's."""
    app()
    shipped = shipped_module()
    cell = hold(shipped.GateLightsCell())
    assert surface.gate_pitch_px(widest_gate_label_px()) == cell._pitch
    assert surface.gate_cell_height_px() == cell.height()
    assert surface.gate_cell_min_width_px(cell._pitch) == cell.minimumWidth()
    assert surface.GATE_TOOLTIP == cell.toolTip()


def test_a_landing_strip_paints_its_own_bank_and_no_other():
    """A landing strip on one side lit the light on the other."""
    upper = gate_row_after([(False, False, [], [], surface.LANDING_STRIP_SCRUM)])
    lower = gate_row_after([(False, False, [], [], surface.LANDING_STRIP_FOLD)])
    assert upper.scrum_landing_strip and not upper.fold_landing_strip
    assert lower.fold_landing_strip and not lower.scrum_landing_strip
    lit = [one for one in upper.lights() if one["state"] == "override"]
    assert [one["bank"] for one in lit] == [surface.GATE_SCRUM_BANK]
    lit = [one for one in lower.lights() if one["state"] == "override"]
    assert [one["bank"] for one in lit] == [surface.GATE_FOLD_BANK]


def test_the_band_program_draws_one_band_per_symbol():
    """A band was lost, or its frame, label or polyline moved."""
    parts = build_new()
    for step in SCENARIOS["happy"]:
        run_new_step(parts, step)
    program = surface.band_program(parts["chart"], CHART_PIXEL_SIZE[0])
    separators = [
        one
        for one in program
        if one["op"] == surface.LINE and one["pen"] == surface.CHART_SEPARATOR_COLOUR
    ]
    assert len(separators) == len(FLEET)
    labels = [one for one in program if one["op"] == surface.TEXT]
    assert [one["text"] for one in labels] == FLEET
    assert labels[0]["align"] == surface.ALIGN_SYMBOL
    assert labels[0]["rect"][0] == surface.CHART_LABEL_INSET_PX
    frames = [one for one in program if one["op"] == surface.RECT]
    assert len(frames) == 1
    assert frames[0]["brush"] == surface.NO_BRUSH
    assert frames[0]["pen"] == surface.CHART_FRAME_COLOUR
    assert frames[0]["rect"][3] == (
        surface.CHART_BAND_HEIGHT_PX - 2 * surface.CHART_BAND_INSET_PX + 1
    )
    lines = [one for one in program if one["op"] == surface.LINE]
    drawn = {one["pen"] for one in lines}
    assert surface.CHART_PRICE_COLOUR in drawn
    assert surface.CHART_VWAP_COLOUR in drawn
    assert all(one["style"] == surface.SOLID_LINE for one in lines)
    dots = [one for one in program if one["op"] == surface.ELLIPSE]
    assert len(dots) == 1
    assert dots[0]["rect"][2] == surface.CHART_MARKER_RADIUS_PX * 2
    single = build_new()
    run_new_step(single, ("symbols", [PAIR]))
    run_new_step(single, ("tick", PAIR, 10.0, 1.0))
    thin = surface.band_program(single["chart"], CHART_PIXEL_SIZE[0])
    assert [one["op"] for one in thin] == [surface.LINE, surface.TEXT]
    assert surface.CHART_MIN_LINE_POINTS == 2


def test_the_focused_program_bisects_the_panel():
    """The two halves overlapped, or a heading or an axis label was lost."""
    parts = build_new()
    for step in SCENARIOS["focused"]:
        run_new_step(parts, step)
    width, height = CHART_PIXEL_SIZE
    program = surface.focused_program(parts["chart"], width, height)
    texts = [one["text"] for one in program if one["op"] == surface.TEXT]
    assert f"{PAIR}{surface.FOCUS_PRICE_HEADING_SUFFIX}" in texts
    assert surface.FOCUS_CANDLE_HEADING in texts
    assert f"5/5{surface.FOCUS_BARS_SUFFIX}" in texts
    assert surface.FOCUS_PRICE_FORMAT.format(99.25) in texts
    assert surface.FOCUS_PRICE_FORMAT.format(104.0) in texts
    top_h = max(
        surface.FOCUS_MIN_BAND_PX,
        (height - surface.FOCUS_HEAD_ROOM_PX - surface.FOCUS_GAP_PX) // 2,
    )
    bottom_y = surface.FOCUS_TOP_Y_PX + top_h + surface.FOCUS_GAP_PX
    divider = [
        one
        for one in program
        if one["op"] == surface.LINE and one["pen"] == surface.CHART_SEPARATOR_COLOUR
    ]
    assert len(divider) == 1
    assert divider[0]["line"][1] == bottom_y - surface.FOCUS_GAP_PX // 2
    bodies = [one for one in program if one["op"] == surface.FILL]
    assert len(bodies) == 5
    assert all(one["rect"][2] == surface.CHART_CANDLE_WIDTH_PX for one in bodies)
    assert all(one["rect"][3] >= 1 for one in bodies)
    wicks = [
        one
        for one in program
        if one["op"] == surface.LINE and one["pen"] in surface.FOCUS_CANDLE_UP_COLOUR
    ]
    assert len(wicks) >= 1
    vwap = [one for one in program if one.get("width") == 2]
    assert vwap and all(one["pen"] == surface.FOCUS_HEADING_COLOUR for one in vwap)
    axis = [
        one
        for one in program
        if one["op"] == surface.TEXT and one["pen"] == surface.FOCUS_AXIS_COLOUR
    ]
    assert len(axis) == 3
    assert axis[0]["at"] == [surface.FOCUS_PAD_PX, height - surface.FOCUS_BASELINE_PX]
    assert axis[1]["at"][0] == (
        width - surface.FOCUS_PAD_PX - surface.FOCUS_HIGH_LABEL_INSET_PX
    )
    assert axis[2]["at"] == [
        width - surface.FOCUS_PAD_PX - surface.FOCUS_BARS_LABEL_INSET_PX,
        surface.FOCUS_TOP_Y_PX + surface.FOCUS_BARS_LABEL_DROP_PX,
    ]
    marks = [
        one
        for one in program
        if one["op"] == surface.ELLIPSE
        and one["rect"][2] == surface.FOCUS_MARKER_RADIUS_PX * 2
    ]
    assert marks == []
    assert surface.candle_step_px() == (
        surface.CHART_CANDLE_WIDTH_PX + surface.CHART_CANDLE_GAP_PX
    )


def test_a_focused_chart_with_no_candle_says_so():
    """A chart with no candle painted an empty panel and said nothing."""
    parts = build_new()
    for step in SCENARIOS["focused_before_any_candle"]:
        run_new_step(parts, step)
    program = surface.focused_program(parts["chart"], *CHART_PIXEL_SIZE)
    assert len(program) == 1
    assert program[0]["text"] == f"{PAIR}{surface.FOCUS_WAITING_SUFFIX}"
    assert program[0]["pen"] == surface.FOCUS_WAITING_COLOUR
    assert program[0]["at"] == [surface.FOCUS_PAD_PX, surface.FOCUS_WAITING_Y_PX]


def test_a_falling_candle_paints_the_down_colour():
    """A falling candle painted the rising colour, or the reverse."""
    parts = build_new()
    run_new_step(parts, ("symbols", [PAIR]))
    run_new_step(parts, ("tick", PAIR, 9.0, 1.0, 1, 10.0, 10.0, 9.0))
    run_new_step(parts, ("focus", PAIR))
    program = surface.focused_program(parts["chart"], *CHART_PIXEL_SIZE)
    bodies = [one for one in program if one["op"] == surface.FILL]
    assert [one["brush"] for one in bodies] == [surface.FOCUS_CANDLE_DOWN_COLOUR]
    rising = build_new()
    run_new_step(rising, ("symbols", [PAIR]))
    run_new_step(rising, ("tick", PAIR, 11.0, 1.0, 1, 10.0, 11.0, 10.0))
    run_new_step(rising, ("focus", PAIR))
    up = [
        one
        for one in surface.focused_program(rising["chart"], *CHART_PIXEL_SIZE)
        if one["op"] == surface.FILL
    ]
    assert [one["brush"] for one in up] == [surface.FOCUS_CANDLE_UP_COLOUR]
    assert surface.FOCUS_CANDLE_UP_COLOUR != surface.FOCUS_CANDLE_DOWN_COLOUR


def test_the_ytd_overlay_starts_at_the_first_documented_trade():
    """The overlay covered warm-up candles no gate decision was taken on."""
    parts = build_new()
    for step in SCENARIOS["focused_with_ytd"]:
        run_new_step(parts, step)
    program = surface.focused_program(parts["chart"], *CHART_PIXEL_SIZE)
    shading = [
        one
        for one in program
        if one["op"] == surface.FILL
        and one["brush"] == list(surface.FOCUS_YTD_FILL_RGBA)
    ]
    assert len(shading) == 1
    step = surface.candle_step_px()
    assert shading[0]["rect"][0] == surface.FOCUS_PAD_PX + step
    dashed = [one for one in program if one.get("style") == surface.DASH_LINE]
    assert len(dashed) == 2
    assert dashed[1]["text"] == surface.FOCUS_YTD_LABEL
    assert dashed[1]["at"][0] == shading[0]["rect"][0] + surface.FOCUS_YTD_TEXT_INSET_PX
    assert dashed[1]["at"][1] == shading[0]["rect"][1] + surface.FOCUS_YTD_TEXT_DROP_PX
    without = build_new()
    for step_of in SCENARIOS["focused"]:
        run_new_step(without, step_of)
    plain = surface.focused_program(without["chart"], *CHART_PIXEL_SIZE)
    assert [one for one in plain if one.get("style") == surface.DASH_LINE] == []


def test_the_two_marker_colours_are_told_apart():
    """The validated and unvalidated markers paint one colour."""
    assert canonical(surface.CHART_MARKER_OK_COLOUR) != canonical(
        surface.CHART_MARKER_MISSED_COLOUR
    )
    assert canonical(surface.FOCUS_MARKER_OK_COLOUR) != canonical(
        surface.FOCUS_MARKER_MISSED_COLOUR
    )
    assert canonical(surface.CHART_MARKER_OK_COLOUR) == "#00ff66"
    assert canonical("#66ff00") != canonical(surface.CHART_MARKER_OK_COLOUR)
    assert canonical("#0066ff") != canonical(surface.CHART_MARKER_OK_COLOUR)


def test_the_three_direction_colours_are_told_apart():
    """Two of the three vote colours paint the same thing."""
    told = {
        direction: canonical(colour)
        for direction, colour in surface.VOTE_DIRECTION_COLOURS.items()
    }
    assert len(set(told.values())) == 3, told
    assert told[surface.VOTE_BULL] == "#00cc55"
    assert canonical("#55cc00") != told[surface.VOTE_BULL]
    assert canonical("#0055cc") != told[surface.VOTE_BULL]
    assert told[surface.VOTE_NEUTRAL] == "#888888"
    assert surface.VOTE_NEUTRAL_COLOUR == "#888"


def test_the_neutral_colour_is_compared_as_text_because_its_channels_are_equal():
    """A colour whose three channels are equal was left to a swap check."""
    swapped = canonical("#888")
    assert swapped == canonical(surface.VOTE_NEUTRAL_COLOUR)
    assert surface.VOTE_NEUTRAL_COLOUR != surface.VOTE_BULL_COLOUR
    assert surface.VOTE_NEUTRAL_COLOUR != surface.VOTE_BEAR_COLOUR


def test_the_written_row_carries_the_formats_the_table_uses():
    """A vote number lost its sign, its places or its column."""
    votes = surface.VotingReadoutModel()
    votes.set_bots([PAIR])
    votes.update_bot_row(PAIR, Summary(vote(net=0.256, conf=0.0249, bull=4, bear=1)))
    assert votes.rows[0] == [PAIR, "+0.26", "0.02", "4", "1", surface.VOTE_BULL]
    votes.update_bot_row(PAIR, Summary(vote(net=-0.5, conf=1.0, bull=0, bear=6)))
    assert votes.rows[0] == [PAIR, "-0.50", "1.00", "0", "6", surface.VOTE_BEAR]
    assert votes.colours[0] == surface.VOTE_BEAR_COLOUR
    assert surface.VOTE_NET_FORMAT.format(0.0) == "+0.00"
    assert surface.VOTE_CONF_FORMAT.format(0.0) == "0.00"
    assert surface.VOTE_COUNT_FORMAT.format(7) == "7"


def test_every_branch_marker_fires_and_ties_to_a_step():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for name in SCENARIO_NAMES:
        parts = build_new()
        for step in SCENARIOS[name]:
            try:
                run_new_step(parts, step)
            except Exception:
                break
        for holder in ("panel", "chart", "votes", "expand"):
            seen.update(getattr(parts[holder], "calls", []))
        for row in parts["panel"].built:
            seen.update(row.lights.calls)
    long_replay = surface.PriceVwapModel()
    long_replay.set_symbols([PAIR])
    for index in range(surface.CHART_MAX_POINTS + 1):
        long_replay.append_tick(PAIR, float(index), 1.0)
    seen.update(long_replay.calls)
    assert surface.CHART_POINTS_DECIMATED in long_replay.calls
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    assert len(surface.CALL_NAMES) == len(set(surface.CALL_NAMES))


# The pictures

REPLAY_ACCESSIBLE_NAME = "Sim Visuals Draw Program"
REPLAY_ACCESSIBLE_DESCRIPTION = (
    "A widget that paints one draw program from the view model and "
    "nothing else, so its picture can be compared with the shipped one."
)

ALIGNMENTS: dict = {}
PEN_STYLES: dict = {}


def _drawing_tables():
    from PySide6.QtCore import Qt

    if not ALIGNMENTS:
        ALIGNMENTS[surface.ALIGN_LABEL] = Qt.AlignHCenter | Qt.AlignVCenter
        ALIGNMENTS[surface.ALIGN_MARKER] = Qt.AlignRight | Qt.AlignVCenter
        ALIGNMENTS[surface.ALIGN_SYMBOL] = Qt.AlignLeft | Qt.AlignVCenter
        PEN_STYLES[surface.SOLID_LINE] = Qt.SolidLine
        PEN_STYLES[surface.DASH_LINE] = Qt.DashLine
    return ALIGNMENTS, PEN_STYLES


def _rect_of(values):
    from PySide6.QtCore import QRect, QRectF

    if any(isinstance(one, float) for one in values):
        return QRectF(*values)
    return QRect(*values)


def replay(painter, program) -> None:
    """Paint one draw program with a real painter."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QBrush, QColor, QPen

    aligns, styles = _drawing_tables()
    for op in program:
        kind = op["op"]
        if kind == surface.FILL:
            brush = op["brush"]
            colour = QColor(*brush) if isinstance(brush, list) else QColor(brush)
            painter.fillRect(_rect_of(op["rect"]), colour)
            continue
        pen = op.get("pen")
        if pen == surface.NO_PEN:
            painter.setPen(Qt.NoPen)
        elif kind == surface.TEXT:
            painter.setPen(QColor(pen))
        else:
            painter.setPen(
                QPen(
                    QColor(pen),
                    op["width"],
                    styles[op.get("style", surface.SOLID_LINE)],
                )
            )
        if kind == surface.TEXT:
            if "rect" in op:
                painter.drawText(_rect_of(op["rect"]), aligns[op["align"]], op["text"])
            else:
                painter.drawText(op["at"][0], op["at"][1], op["text"])
        elif kind == surface.LINE:
            painter.drawLine(*op["line"])
        elif kind == surface.ELLIPSE:
            brush = op["brush"]
            painter.setBrush(
                Qt.NoBrush if brush == surface.NO_BRUSH else QBrush(QColor(brush))
            )
            painter.drawEllipse(_rect_of(op["rect"]))
        elif kind == surface.RECT:
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(_rect_of(op["rect"]))
        else:
            raise LookupError(kind)


def program_widget(
    program,
    font_pt=None,
    style_sheet="",
    fixed_height=None,
    minimum_width=None,
):
    """A widget that paints one draw program and nothing else."""
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QWidget

    class Replay(QWidget):
        def __init__(self):
            super().__init__()
            self.setAccessibleName(REPLAY_ACCESSIBLE_NAME)
            self.setAccessibleDescription(REPLAY_ACCESSIBLE_DESCRIPTION)
            if style_sheet:
                self.setStyleSheet(style_sheet)
            if fixed_height is not None:
                self.setFixedHeight(fixed_height)
            if minimum_width is not None:
                self.setMinimumWidth(minimum_width)

        def paintEvent(self, event):  # noqa: N802 - Qt override
            del event
            painter = QPainter(self)
            try:
                painter.setRenderHint(QPainter.Antialiasing, True)
                if font_pt is not None:
                    font = painter.font()
                    font.setPointSize(font_pt)
                    painter.setFont(font)
                replay(painter, program)
            finally:
                painter.end()

    return hold(Replay())


def render_offscreen(widget, size, note=""):
    """One render, refused first if it painted a single colour."""
    from tests.qt_pixel import render_widget

    image = render_widget(widget, size)
    assert_picture_can_report(image, note=note)
    return image


GATE_STATES = {
    "not_evaluated": [],
    "both_armed": [(True, True, [], [], "")],
    "blocked_on_both_sides": [(True, False, SCRUM_BLOCKERS, FOLD_BLOCKERS, "")],
    "scrum_landing_strip": [(False, False, [], [], "upper")],
    "fold_landing_strip": [(False, False, [], [], "lower")],
}


def gate_cell_painted_by_the_widget(state):
    app()
    shipped = shipped_module()
    cell = hold(shipped.GateLightsCell())
    for step in GATE_STATES[state]:
        cell.update_gates(*step)
    return cell


def gate_payload(state):
    row = gate_row_after(GATE_STATES[state])
    pitch = measured_pitch_px()
    return sealed(
        {
            "program": surface.gate_program(row, pitch),
            "font_pt": surface.GATE_FONT_PT,
            "height_px": surface.gate_cell_height_px(),
            "min_width_px": surface.gate_cell_min_width_px(pitch),
        }
    )


def gate_cell_painted_by_the_model(payload):
    payload = unaltered(payload)
    app()
    return program_widget(
        payload["program"],
        font_pt=payload["font_pt"],
        fixed_height=payload["height_px"],
        minimum_width=payload["min_width_px"],
    )


@pytest.mark.parametrize("state", sorted(GATE_STATES))
def test_the_two_sides_paint_one_gate_row(state):
    """The surface painted a different gate row than the shipped cell."""
    app()
    note = "%s, %s" % (state, "real fonts" if fonts_ready() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(
            gate_cell_painted_by_the_widget(state), GATE_PIXEL_SIZE, note
        ),
        new_side=render_offscreen(
            gate_cell_painted_by_the_model(gate_payload(state)), GATE_PIXEL_SIZE, note
        ),
        note=note,
    )


@pytest.mark.parametrize("state", sorted(GATE_STATES))
def test_the_painted_gate_row_shows_more_than_one_colour(state):
    """The two sides matched because the row painted one flat colour."""
    app()
    for widget in (
        gate_cell_painted_by_the_widget(state),
        gate_cell_painted_by_the_model(gate_payload(state)),
    ):
        from tests.qt_pixel import render_widget

        found = colour_count(render_widget(widget, GATE_PIXEL_SIZE))
        assert found > 1, f"{state} painted {found} colour, so no change could show"


def test_the_gate_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints."""
    app()
    assert_cases_paint_differently(
        old_side=render_offscreen(
            gate_cell_painted_by_the_widget("both_armed"), GATE_PIXEL_SIZE
        ),
        new_side=render_offscreen(
            gate_cell_painted_by_the_model(gate_payload("blocked_on_both_sides")),
            GATE_PIXEL_SIZE,
        ),
        note="every gate passed against two banks carrying blockers",
    )


# A rule NEITHER side sets: the shipped gate cell carries no style sheet
# at all, and neither does the widget built from the payload.
GATE_CONTROL_RULE = "QWidget { background: #ff00ff; }"


def test_the_gate_row_carries_one_skin_on_both_sides():
    """A skin reached one side only, which a value check cannot report."""
    app()
    payload = gate_payload("blocked_on_both_sides")
    assert_same_skin(
        build_old_side=lambda: gate_cell_painted_by_the_widget("blocked_on_both_sides"),
        build_new_side=lambda: gate_cell_painted_by_the_model(payload),
        size=GATE_PIXEL_SIZE,
        control_rule=GATE_CONTROL_RULE,
        note="neither side carries a skin of its own",
    )


CHART_STATES = ["fleet_loaded", "happy", "focused", "focused_with_ytd"]


def chart_painted_by_the_widget(name):
    parts = build_old()
    for step in SCENARIOS[name]:
        run_old_step(parts, step)
    return parts["chart"]


def chart_payload(name):
    parts = build_new()
    for step in SCENARIOS[name]:
        run_new_step(parts, step)
    return sealed(
        {
            "program": surface.chart_program(parts["chart"], *CHART_PIXEL_SIZE),
            "style_sheet": surface.CHART_STYLE,
        }
    )


def chart_painted_by_the_model(payload):
    payload = unaltered(payload)
    app()
    return program_widget(payload["program"], style_sheet=payload["style_sheet"])


@pytest.mark.parametrize("name", CHART_STATES)
def test_the_two_sides_paint_one_chart(name):
    """The surface painted a different chart than the shipped widget."""
    app()
    note = "%s, %s" % (name, "real fonts" if fonts_ready() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(
            chart_painted_by_the_widget(name), CHART_PIXEL_SIZE, note
        ),
        new_side=render_offscreen(
            chart_painted_by_the_model(chart_payload(name)), CHART_PIXEL_SIZE, note
        ),
        note=note,
    )


def test_the_chart_picture_comparison_can_report_a_difference():
    """The chart picture check passes whatever the second side paints."""
    app()
    assert_cases_paint_differently(
        old_side=render_offscreen(
            chart_painted_by_the_widget("happy"), CHART_PIXEL_SIZE
        ),
        new_side=render_offscreen(
            chart_painted_by_the_model(chart_payload("focused_with_ytd")),
            CHART_PIXEL_SIZE,
        ),
        note="three stacked bands against one focused candle chart",
    )


def votes_painted_by_the_widget(name):
    parts = build_old()
    for step in SCENARIOS[name]:
        run_old_step(parts, step)
    return parts["votes"]


def votes_payload(name):
    parts = build_new()
    for step in SCENARIOS[name]:
        run_new_step(parts, step)
    return sealed(
        surface.build_view_model(
            panel=parts["panel"],
            chart=parts["chart"],
            votes=parts["votes"],
            expand=parts["expand"],
            gate_pitch=measured_pitch_px(),
        )["votes"]
    )


def votes_painted_by_the_model(payload):
    payload = unaltered(payload)
    app()
    from PySide6.QtGui import QBrush, QColor
    from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget
    from PySide6.QtWidgets import QTableWidgetItem as Cell

    table = hold(QTableWidget())
    table.setAccessibleName(payload["accessible_name"])
    table.setAccessibleDescription(payload["accessible_description"])
    table.setToolTip(payload["tooltip"])
    table.setColumnCount(len(payload["columns"]))
    table.setHorizontalHeaderLabels(payload["columns"])
    table.setEditTriggers(getattr(QAbstractItemView, payload["edit_triggers"]))
    table.setSelectionBehavior(
        getattr(QAbstractItemView, payload["selection_behaviour"])
    )
    table.setAlternatingRowColors(payload["alternating_rows"])
    table.verticalHeader().setVisible(payload["row_header_visible"])
    table.setStyleSheet(payload["style_sheet"])
    header = table.horizontalHeader()
    header.setSectionResizeMode(getattr(QHeaderView, payload["column_mode"]))
    header.setSectionResizeMode(0, getattr(QHeaderView, payload["symbol_column_mode"]))
    header.setStretchLastSection(payload["stretch_last_column"])
    table.setRowCount(len(payload["rows"]))
    for index, row in enumerate(payload["rows"]):
        for column, text in enumerate(row["cells"]):
            cell = Cell(text)
            if column == len(payload["columns"]) - 1 and row["direction_colour"]:
                cell.setForeground(QBrush(QColor(row["direction_colour"])))
            table.setItem(index, column, cell)
    return table


VOTE_STATES = [
    "fleet_loaded",
    "happy",
    "a_vote_of_not_a_number",
    "a_vote_written_three_times",
]


@pytest.mark.parametrize("name", VOTE_STATES)
def test_the_two_sides_paint_one_voting_table(name):
    """The surface painted a different voting table than the shipped one."""
    app()
    note = "%s, %s" % (name, "real fonts" if fonts_ready() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(
            votes_painted_by_the_widget(name), VOTE_PIXEL_SIZE, note
        ),
        new_side=render_offscreen(
            votes_painted_by_the_model(votes_payload(name)), VOTE_PIXEL_SIZE, note
        ),
        note=note,
    )


def test_the_voting_picture_comparison_can_report_a_difference():
    """The table picture check passes whatever the second side paints."""
    app()
    assert_cases_paint_differently(
        old_side=render_offscreen(
            votes_painted_by_the_widget("happy"), VOTE_PIXEL_SIZE
        ),
        new_side=render_offscreen(
            votes_painted_by_the_model(votes_payload("fleet_loaded")), VOTE_PIXEL_SIZE
        ),
        note="two written votes against three placeholder rows",
    )


def panel_painted_by_the_widget(name):
    parts = build_old()
    for step in SCENARIOS[name]:
        run_old_step(parts, step)
    return parts["panel"]


def panel_payload(name):
    parts = build_new()
    for step in SCENARIOS[name]:
        run_new_step(parts, step)
    return sealed(
        surface.build_view_model(
            panel=parts["panel"],
            chart=parts["chart"],
            votes=parts["votes"],
            expand=parts["expand"],
            gate_pitch=measured_pitch_px(),
        )
    )


def panel_painted_by_the_model(payload):
    payload = unaltered(payload)
    app()
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    pane = payload["gate_panel"]
    rows = payload["gate_row"]["rows"]
    panel = hold(QWidget())
    outer = QVBoxLayout(panel)
    outer.setContentsMargins(*pane["margins_px"])
    outer.setSpacing(pane["spacing_px"])
    area = QScrollArea()
    area.setWidgetResizable(pane["scroll_resizable"])
    area.setStyleSheet(pane["scroll_style"])
    host = QWidget()
    column = QVBoxLayout(host)
    column.setContentsMargins(*pane["host_margins_px"])
    column.setSpacing(pane["host_spacing_px"])
    for item in pane["items"]:
        if item["kind"] == "stretch":
            column.addStretch()
        elif item["kind"] == "empty":
            empty = QLabel(pane["empty_text"])
            empty.setStyleSheet(pane["empty_style"])
            empty.setVisible(item["visible"])
            column.addWidget(empty)
        else:
            wrap = QWidget()
            line = QHBoxLayout(wrap)
            line.setContentsMargins(*pane["row_margins_px"])
            line.setSpacing(pane["row_spacing_px"])
            name = QLabel(item["symbol"])
            name.setMinimumWidth(pane["label_min_width_px"])
            name.setStyleSheet(pane["label_style"])
            line.addWidget(name)
            line.addWidget(
                program_widget(
                    rows[item["symbol"]]["program"],
                    font_pt=payload["gate_row"]["font_pt"],
                    fixed_height=payload["gate_row"]["height_px"],
                    minimum_width=payload["gate_row"]["min_width_px"],
                )
            )
            line.addStretch()
            column.addWidget(wrap)
    area.setWidget(host)
    outer.addWidget(area)
    return panel


PANEL_STATES = ["built_only", "fleet_loaded", "happy", "empty_fleet"]


@pytest.mark.parametrize("name", PANEL_STATES)
def test_the_two_sides_paint_one_gate_pane(name):
    """The surface painted a different gate pane than the shipped one."""
    app()
    note = "%s, %s" % (name, "real fonts" if fonts_ready() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(
            panel_painted_by_the_widget(name), PANEL_PIXEL_SIZE, note
        ),
        new_side=render_offscreen(
            panel_painted_by_the_model(panel_payload(name)), PANEL_PIXEL_SIZE, note
        ),
        note=note,
    )


def test_the_pane_picture_comparison_can_report_a_difference():
    """The pane picture check passes whatever the second side paints."""
    app()
    assert_cases_paint_differently(
        old_side=render_offscreen(
            panel_painted_by_the_widget("happy"), PANEL_PIXEL_SIZE
        ),
        new_side=render_offscreen(
            panel_painted_by_the_model(panel_payload("empty_fleet")), PANEL_PIXEL_SIZE
        ),
        note="three loaded gate rows against an empty pane",
    )


# Rules NEITHER side sets: no border, no grid line colour, and no skin
# at all on the gate row or on the pane's root.
CHART_CONTROL_RULE = "QWidget { border: 4px solid #ff00ff; }"
VOTE_CONTROL_RULE = "QTableWidget { gridline-color: #ff00ff; }"
PANEL_CONTROL_RULE = "QWidget { background: #ff00ff; }"
EXPAND_CONTROL_RULE = "QDialog { border: 4px solid #ff00ff; }"

EXPAND_PIXEL_SIZE = (400, 200)


def test_the_chart_carries_one_skin_on_both_sides():
    """A skin reached one chart only, which a value check cannot report."""
    app()
    payload = chart_payload("happy")
    assert_same_skin(
        build_old_side=lambda: chart_painted_by_the_widget("happy"),
        build_new_side=lambda: chart_painted_by_the_model(payload),
        size=CHART_PIXEL_SIZE,
        control_rule=CHART_CONTROL_RULE,
        note="neither side draws a border",
    )


def test_the_voting_table_carries_one_skin_on_both_sides():
    """A skin reached one table only, which a value check cannot report."""
    app()
    payload = votes_payload("happy")
    assert_same_skin(
        build_old_side=lambda: votes_painted_by_the_widget("happy"),
        build_new_side=lambda: votes_painted_by_the_model(payload),
        size=VOTE_PIXEL_SIZE,
        control_rule=VOTE_CONTROL_RULE,
        note="neither side sets a grid line colour",
    )


def test_the_gate_pane_carries_one_skin_on_both_sides():
    """A skin reached one pane only, which a value check cannot report."""
    app()
    payload = panel_payload("fleet_loaded")
    assert_same_skin(
        build_old_side=lambda: panel_painted_by_the_widget("fleet_loaded"),
        build_new_side=lambda: panel_painted_by_the_model(payload),
        size=PANEL_PIXEL_SIZE,
        control_rule=PANEL_CONTROL_RULE,
        note="neither pane root carries a skin of its own",
    )


def chart_inside_a_window():
    """A chart in a panel in a window, as the Simulator tab arranges it.

    The guard reads ``widget.window()``. A widget with no top-level
    window is its own window, so the guard parents the dialog to the
    widget and then moves the widget into that dialog's layout. Qt does
    not return from that, so every drive of the guard hands it a widget
    that really is inside a window.
    """
    app()
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    window = hold(QWidget())
    panel = QWidget(window)
    QVBoxLayout(window).addWidget(panel)
    chart = QLabel("chart", panel)
    QVBoxLayout(panel).addWidget(chart)
    return window, chart


def expand_dialog_from_the_widget():
    """The dialog the shipped guard opens over a chart in a window."""
    _window, chart = chart_inside_a_window()
    shipped_module()._show_expanded(chart, "Chart")
    return hold(getattr(chart, surface.EXPAND_CLAIM_FIELD))


def expand_dialog_from_the_model():
    """A dialog built only from the view model, over the same chart."""
    _window, chart = chart_inside_a_window()
    from PySide6.QtWidgets import QDialog, QVBoxLayout

    told = surface.build_view_model()["expand"]
    dialog = hold(QDialog(chart.window()))
    dialog.setWindowTitle("Chart")
    dialog.setStyleSheet(told["style_sheet"])
    column = QVBoxLayout(dialog)
    column.setContentsMargins(*told["margins_px"])
    column.addWidget(chart)
    return dialog


def test_the_expand_dialog_carries_one_skin_on_both_sides():
    """The expand dialog opens in a different skin than the model names."""
    app()
    assert_same_skin(
        build_old_side=expand_dialog_from_the_widget,
        build_new_side=expand_dialog_from_the_model,
        size=EXPAND_PIXEL_SIZE,
        control_rule=EXPAND_CONTROL_RULE,
        note="neither dialog draws a border",
    )


def test_the_direction_colour_reaches_a_pixel():
    """The direction colour paints nothing, so no picture can report it.

    Two tables built from one payload with only the direction colour
    changed. Both are the surface's own side, which is what a control on
    the instrument means: it says the picture set can see this value, and
    it makes no claim about either side matching the other.
    """
    app()
    from tests.qt_pixel import render_widget

    told = votes_payload("happy")
    bull = render_widget(votes_painted_by_the_model(told), VOTE_PIXEL_SIZE)
    assert_picture_can_report(bull, note="the voting table as it is written")
    swapped = dict(told)
    swapped["rows"] = [
        (
            dict(row, direction_colour=surface.VOTE_NEUTRAL_COLOUR)
            if row["direction_colour"]
            else row
        )
        for row in told["rows"]
    ]
    assert [row["direction_colour"] for row in swapped["rows"]] != [
        row["direction_colour"] for row in told["rows"]
    ]
    assert [row["cells"] for row in swapped["rows"]] == [
        row["cells"] for row in told["rows"]
    ]
    neutral = render_widget(
        votes_painted_by_the_model(sealed(swapped)), VOTE_PIXEL_SIZE
    )
    assert_pictures_differ(
        old_side=bull,
        new_side=neutral,
        note="one payload, the direction colour alone changed",
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    stamped = gate_payload("both_armed")
    stamped["program"][1]["brush"] = "#ff00ff"
    with pytest.raises(AssertionError) as reported:
        gate_cell_painted_by_the_model(stamped)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        gate_cell_painted_by_the_model(
            {
                "program": [],
                "font_pt": surface.GATE_FONT_PT,
                "height_px": surface.gate_cell_height_px(),
                "min_width_px": surface.gate_cell_min_width_px(9),
            }
        )


def test_the_measured_colour_count_is_reported_for_every_gate_state():
    """A state painting one colour was compared and reported nothing."""
    app()
    from tests.qt_pixel import render_widget

    counted = {
        state: colour_count(
            render_widget(gate_cell_painted_by_the_widget(state), GATE_PIXEL_SIZE)
        )
        for state in sorted(GATE_STATES)
    }
    assert all(found > 1 for found in counted.values()), counted
    assert len(set(counted.values())) > 1, counted
    flat = colour_count(render_widget(hold(program_widget([])), GATE_PIXEL_SIZE))
    assert flat == 1, f"a widget painting nothing counted {flat} colours"


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on."""
    app()
    assert len(NARROW_LABEL) == len(WIDE_LABEL)
    if fonts_ready():
        assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)
    else:
        assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


# What a picture cannot carry, read off both sides instead


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report."""
    app()
    parts = build_old()
    assert parts["panel"].accessibleName() == surface.PANEL_ACCESSIBLE_NAME
    assert parts["chart"].accessibleName() == surface.CHART_ACCESSIBLE_NAME
    assert (
        parts["chart"].accessibleDescription() == surface.CHART_ACCESSIBLE_DESCRIPTION
    )
    assert parts["chart"].toolTip() == surface.CHART_TOOLTIP
    assert parts["votes"].accessibleName() == surface.VOTE_ACCESSIBLE_NAME
    assert parts["votes"].accessibleDescription() == surface.VOTE_ACCESSIBLE_DESCRIPTION
    assert parts["votes"].toolTip() == surface.VOTE_TOOLTIP
    assert parts["votes"].alternatingRowColors() is surface.VOTE_ALTERNATING_ROWS
    assert (
        parts["votes"].verticalHeader().isVisible() is surface.VOTE_ROW_HEADER_VISIBLE
    )
    assert [
        parts["votes"].horizontalHeaderItem(index).text()
        for index in range(parts["votes"].columnCount())
    ] == list(surface.VOTE_COLUMNS)


def test_the_pane_layout_numbers_are_read_off_both_sides():
    """A layout number the pane sets reached no comparison at all.

    The pane's three skins are not read here. A style off a live widget
    is the value it was told, not the one it paints, so the skins are
    compared by rendered pixels in the skin checks above.
    """
    app()
    panel = build_old()["panel"]
    assert panel._scroll.widgetResizable() is surface.PANEL_SCROLL_RESIZABLE
    assert panel._empty.text() == surface.PANEL_EMPTY_TEXT
    assert list(panel.layout().getContentsMargins()) == list(surface.PANEL_MARGINS_PX)
    assert panel.layout().spacing() == surface.PANEL_SPACING_PX
    assert list(panel._host_lay.getContentsMargins()) == list(
        surface.PANEL_HOST_MARGINS_PX
    )
    assert panel._host_lay.spacing() == surface.PANEL_HOST_SPACING_PX
    panel.set_symbols([PAIR])
    wrap = panel._rows[PAIR]["wrap"]
    assert list(wrap.layout().getContentsMargins()) == list(
        surface.PANEL_ROW_MARGINS_PX
    )
    assert wrap.layout().spacing() == surface.PANEL_ROW_SPACING_PX
    label = wrap.layout().itemAt(0).widget()
    assert label.minimumWidth() == surface.PANEL_LABEL_MIN_WIDTH_PX
    assert label.text() == PAIR


INVISIBLE_TO_A_PICTURE = {
    "gate_panel.accessible_name": "test_the_values_no_picture_carries_are_read_off_both_sides",
    "gate_panel.scroll_resizable": "test_the_pane_layout_numbers_are_read_off_both_sides",
    "gate_panel.empty_text": "test_the_pane_layout_numbers_are_read_off_both_sides",
    "chart.style_sheet": "test_the_chart_carries_one_skin_on_both_sides",
    "votes.style_sheet": "test_the_voting_table_carries_one_skin_on_both_sides",
    "gate_panel.scroll_style": "test_the_gate_pane_carries_one_skin_on_both_sides",
    "gate_panel.empty_style": "test_the_gate_pane_carries_one_skin_on_both_sides",
    "gate_panel.label_style": "test_the_gate_pane_carries_one_skin_on_both_sides",
    "expand.style_sheet": "test_the_expand_dialog_carries_one_skin_on_both_sides",
    "votes.rows": "test_the_direction_colour_reaches_a_pixel",
    "chart.accessible_name": "test_the_values_no_picture_carries_are_read_off_both_sides",
    "chart.accessible_description": "test_the_values_no_picture_carries_are_read_off_both_sides",
    "chart.tooltip": "test_the_values_no_picture_carries_are_read_off_both_sides",
    "votes.accessible_name": "test_the_values_no_picture_carries_are_read_off_both_sides",
    "votes.accessible_description": "test_the_values_no_picture_carries_are_read_off_both_sides",
    "votes.tooltip": "test_the_values_no_picture_carries_are_read_off_both_sides",
    "gate_row.tooltip": "test_the_gate_row_matches_the_geometry_the_shipped_cell_measured",
    "gate_row.min_width_px": "test_the_gate_row_matches_the_geometry_the_shipped_cell_measured",
    "chart.max_points": "test_a_marked_candle_survives_the_decimation_that_halves_the_series",
    "chart.max_markers": "test_the_marker_store_keeps_the_live_end_when_it_fills",
    "chart.max_candles": "test_the_candle_buffer_keeps_the_live_end_when_it_fills",
    "chart.vwap_window": "test_the_window_holds_the_last_thirty_candles_and_no_more",
    "method": "test_the_bridge_registers_the_sim_visuals_method",
    "actions": "test_the_visuals_wire_one_action_and_the_surface_names_one",
    "timers": "test_the_visuals_build_no_timer_and_start_none",
    "timer_delays_ms": "test_the_visuals_build_no_timer_and_start_none",
    "bus_topics": "test_the_visuals_touch_no_bus_in_either_direction",
    "bus_emits": "test_the_visuals_touch_no_bus_in_either_direction",
    "signals": "test_the_visuals_declare_no_signal_and_emit_none",
    "call_names": "test_every_branch_marker_fires_and_ties_to_a_step",
    "expand.claim_field": "test_the_expand_claim_field_is_the_one_the_shipped_guard_uses",
}


def test_every_value_a_picture_cannot_carry_names_the_check_that_reads_it():
    """A value no pixel carries was left to the render to report."""
    for value, covered_by in INVISIBLE_TO_A_PICTURE.items():
        assert covered_by in globals(), (value, covered_by)
        assert callable(globals()[covered_by]), (value, covered_by)


def test_the_expand_claim_field_is_the_one_the_shipped_guard_uses():
    """The guard and the surface claim a widget under different names."""
    from PySide6.QtWidgets import QApplication

    _window, chart = chart_inside_a_window()
    shipped = shipped_module()
    assert getattr(chart, surface.EXPAND_CLAIM_FIELD, None) is None
    shipped._show_expanded(chart, "Chart")
    claimed = getattr(chart, surface.EXPAND_CLAIM_FIELD, None)
    assert claimed is not None
    assert claimed.windowTitle() == "Chart"
    assert list(claimed.layout().getContentsMargins()) == list(
        surface.EXPAND_MARGINS_PX
    )
    shipped._show_expanded(chart, "Chart")
    assert getattr(chart, surface.EXPAND_CLAIM_FIELD) is claimed
    told = surface.ExpandModel()
    told.open("Chart")
    assert told.claim["claim_field"] == surface.EXPAND_CLAIM_FIELD
    told.open("Chart")
    assert told.calls == [surface.EXPAND_OPENED, surface.EXPAND_RAISED]
    claimed.reject()
    QApplication.processEvents()
    assert getattr(chart, surface.EXPAND_CLAIM_FIELD, None) is None
    assert told.close()["shown"] is False
    assert told.claim is None


def test_a_widget_with_no_window_of_its_own_never_reaches_the_shipped_guard():
    """The guard was handed a widget that is its own window, which hangs.

    ``widget.window()`` on a parentless widget is the widget itself, so
    the guard parents the dialog to it and then moves it into that
    dialog. Qt does not return from that, so this test proves the
    condition without making the call.
    """
    app()
    from PySide6.QtWidgets import QLabel

    orphan = hold(QLabel("chart"))
    assert orphan.window() is orphan
    _window, chart = chart_inside_a_window()
    assert chart.window() is not chart
    assert chart.window() is _window


# Shared state and run order


def test_the_shipped_widgets_write_to_no_shared_table():
    """Driving one widget changed a value a later widget would read."""
    app()
    shipped = shipped_module()
    before = {
        "band": shipped.SimPriceVwapChart._BAND_HEIGHT,
        "points": shipped.SimPriceVwapChart._MAX_POINTS,
        "led": shipped.GateLightsCell._LED,
        "columns": shipped.PerBotVotingReadout._COLUMNS,
    }
    for name in ("happy", "focused_with_ytd", "data_cleared"):
        parts = build_old()
        for step in SCENARIOS[name]:
            run_old_step(parts, step)
    assert shipped.SimPriceVwapChart._BAND_HEIGHT == before["band"]
    assert shipped.SimPriceVwapChart._MAX_POINTS == before["points"]
    assert shipped.GateLightsCell._LED == before["led"]
    assert shipped.PerBotVotingReadout._COLUMNS == before["columns"]
    assert old_outcome("built_only")["trace"]["chart"]["symbols"] == []


def test_the_shared_state_reader_would_report_a_change(monkeypatch):
    """The reader reports no change whatever the module holds."""
    app()
    shipped = shipped_module()
    monkeypatch.setattr(shipped.SimPriceVwapChart, "_BAND_HEIGHT", 999)
    assert shipped.SimPriceVwapChart._BAND_HEIGHT == 999
    assert old_outcome("fleet_loaded")["trace"]["chart"]["minimum_height_px"] == 2997
    monkeypatch.undo()
    assert old_outcome("fleet_loaded")["trace"]["chart"]["minimum_height_px"] == 108


def test_the_swap_is_watched_while_a_drive_is_running(monkeypatch):
    """The swap was put back before the drive ever read it."""
    app()
    shipped = shipped_module()
    seen = []
    monkeypatch.setattr(shipped.SimPriceVwapChart, "_BAND_HEIGHT", 5)
    parts = build_old()
    for step in SCENARIOS["fleet_loaded"]:
        run_old_step(parts, step)
        seen.append(shipped.SimPriceVwapChart._BAND_HEIGHT)
    assert seen == [5], seen
    assert parts["chart"].minimumHeight() == 15
    monkeypatch.undo()
    assert shipped.SimPriceVwapChart._BAND_HEIGHT == 36


def test_the_swap_is_put_back_after_a_refusal(monkeypatch):
    """A refused drive left the swap in place for the next test."""
    app()
    shipped = shipped_module()
    monkeypatch.setattr(shipped.SimPriceVwapChart, "_BAND_HEIGHT", 5)
    with pytest.raises(Exception):
        parts = build_old()
        for step in SCENARIOS["text_where_a_price_belongs"]:
            run_old_step(parts, step)
        raise AssertionError("the drive did not refuse")
    monkeypatch.undo()
    assert shipped.SimPriceVwapChart._BAND_HEIGHT == 36
    assert old_outcome("fleet_loaded")["trace"]["chart"]["minimum_height_px"] == 108


def test_two_models_share_no_buffer():
    """Two models share one table, so one run decides what a later one shows."""
    first = surface.PriceVwapModel()
    second = surface.PriceVwapModel()
    first.set_symbols([PAIR])
    second.set_symbols([PAIR])
    first.append_tick(PAIR, 10.0, 1.0)
    assert second.series[PAIR] == ([], [])
    assert first.series is not second.series
    one = surface.build_view_model()
    other = surface.build_view_model()
    assert one == other
    assert one is not other
    assert one["chart"] is not other["chart"]


def test_neither_side_edits_the_list_it_was_handed():
    """A caller's own list came back changed by the drive."""
    app()
    handed = [PAIR, OTHER]
    parts = build_old()
    parts["panel"].set_symbols(handed)
    parts["chart"].set_symbols(handed)
    assert handed == [PAIR, OTHER]
    mine = build_new()
    mine["panel"].set_symbols(handed)
    mine["chart"].set_symbols(handed)
    assert handed == [PAIR, OTHER]
    blockers = list(SCRUM_BLOCKERS)
    mine["panel"].cell_for(PAIR).update_gates(True, True, blockers, [], "")
    assert blockers == SCRUM_BLOCKERS


# The bare readings

BARE_READINGS = [
    ("append_tick close", ("tick", PAIR, None, 1.0)),
    ("append_tick volume", ("tick", PAIR, 10.0, None)),
    ("append_tick ts", ("tick", PAIR, 10.0, 1.0, math.inf)),
    ("append_tick open", ("tick", PAIR, 10.0, 1.0, 1, None)),
    ("set_ytd_start", ("ytd", PAIR, math.inf)),
    ("update_bot_row net", ("vote", PAIR, vote(net=None))),
    ("update_bot_row count", ("vote", PAIR, vote(bull=math.inf))),
]

BARE_VALUES = [True, math.nan, math.inf, -math.inf, "text", "12.7", 12.7, 10**400]


def outcome_of(step, run_step, build) -> str:
    parts = build()
    for load in LOAD:
        run_step(parts, load)
    try:
        run_step(parts, step)
    except Exception as exc:
        return type(exc).__name__
    return "answered"


@pytest.mark.parametrize("value", BARE_VALUES, ids=[repr(one) for one in BARE_VALUES])
@pytest.mark.parametrize(
    "name,step", BARE_READINGS, ids=[one[0] for one in BARE_READINGS]
)
def test_a_number_read_out_of_stored_state_answers_alike_on_both_sides(
    name, step, value
):
    """One side accepted a value the other refused, or refused differently."""
    app()
    driven = list(step)
    if driven[0] == "tick":
        for index in range(2, len(driven)):
            if driven[index] is None or isinstance(driven[index], float):
                driven[index] = value
                break
    elif driven[0] == "ytd":
        driven[2] = value
    else:
        spec = dict(driven[2])
        for key in ("net_score", "bullish_count"):
            if spec[key] is None or isinstance(spec[key], float):
                spec[key] = value
                break
        driven[2] = spec
    driven = tuple(driven)
    old = outcome_of(driven, run_old_step, build_old)
    new = outcome_of(driven, run_new_step, build_new)
    assert new == old, (name, value, old, new)


def test_the_bare_reading_driver_reports_a_refusal_and_an_answer():
    """The driver folds every outcome into one word, so it proves nothing."""
    app()
    good = outcome_of(("tick", PAIR, 10.0, 1.0), run_new_step, build_new)
    bad = outcome_of(("tick", PAIR, "text", 1.0), run_new_step, build_new)
    assert good == "answered"
    assert bad != "answered"
    assert bad == outcome_of(("tick", PAIR, "text", 1.0), run_old_step, build_old)


def test_a_number_in_a_table_cell_builds_a_cell_with_no_text():
    """A numeric symbol reached the cell's kind and painted nothing."""
    app()
    from PySide6.QtWidgets import QTableWidgetItem

    assert QTableWidgetItem("BTC/USDC").text() == "BTC/USDC"
    numeric = QTableWidgetItem(7)
    assert numeric.text() == ""
    assert numeric.type() == 7
    assert surface.cell_text(7) == ""
    assert surface.cell_text("BTC/USDC") == "BTC/USDC"
    assert surface.cell_text(True) == ""
    assert QTableWidgetItem(True).text() == ""
    votes = surface.VotingReadoutModel()
    votes.set_bots([7])
    assert votes.rows[0][0] == ""


# The clock, the network and the throwaway home


class RefusingClock:
    """A clock that refuses every reading."""

    def __init__(self):
        self.asked = 0

    def __call__(self, *args, **named):
        self.asked += 1
        raise AssertionError("this run read the wall clock")

    def now(self, *args, **named):
        return self(*args, **named)


def test_neither_the_surface_nor_this_test_reads_the_wall_clock(monkeypatch):
    """A run read the clock, so its answer moves with the day."""
    trap = RefusingClock()
    monkeypatch.setattr(clock_module, "time", trap)
    monkeypatch.setattr(clock_module, "monotonic", trap)
    monkeypatch.setattr(clock_module, "perf_counter", trap)
    for name in SCENARIO_NAMES:
        parts = build_new()
        for step in SCENARIOS[name]:
            try:
                run_new_step(parts, step)
            except Exception:
                break
    surface.view_model({"symbols": FLEET})
    surface.build_view_model()
    assert trap.asked == 0, trap.asked
    with pytest.raises(AssertionError):
        clock_module.time()
    assert trap.asked == 1


def test_this_run_opens_no_connection_of_its_own(monkeypatch):
    """A drive reached the network."""
    reached = []

    def refuse(*args, **named):
        reached.append(args)
        raise AssertionError("this run tried to reach the network")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    for name in ("happy", "focused_with_ytd", "data_cleared"):
        assert digest(old_outcome(name)["trace"]) == digest(new_outcome(name)["trace"])
    assert reached == [], reached
    with pytest.raises(AssertionError):
        refuse("a seeded call")
    assert len(reached) == 1


PROBE = """
import json, sys
sys.path.insert(0, %(repo)r)
import socket
reached = []
opened = []
started = []


def _count(*args, **named):
    reached.append(args)
    return None


socket.socket.connect = _count
socket.socket.connect_ex = _count
socket.create_connection = _count
socket.getaddrinfo = _count

import builtins
import threading
import time as clock

_real_open = builtins.open
builtins.open = lambda *a, **k: opened.append(a) or _real_open(*a, **k)
clock.time = lambda *a, **k: started.append("time") or 0.0
clock.monotonic = lambda *a, **k: started.append("monotonic") or 0.0
_before_threads = threading.active_count()
%(prelude)s
from src.core.desktop_bridge import build_registry, handle_line
answer = handle_line(
    json.dumps({
        "id": 7,
        "method": "sim_visuals.state",
        "params": {
            "symbols": ["BTC/USDC", "ETH/USDC"],
            "ticks": [{"symbol": "BTC/USDC", "close": 10.0, "volume": 1.0}],
            "gates": [{"symbol": "BTC/USDC", "scrum_armed": True, "fold_armed": False}],
            "width_px": 900,
            "height_px": 400,
        },
    }),
    build_registry(),
)
print(json.dumps({
    "qt": sorted(
        n for n in sys.modules
        if n.startswith("PySide6") and sys.modules[n] is not None
    )[:1],
    "ok": answer["ok"],
    "symbols": answer["result"]["chart"]["symbols"] if answer["ok"] else None,
    "lights": (
        len(answer["result"]["gate_row"]["rows"]["BTC/USDC"]["lights"])
        if answer["ok"] else 0
    ),
    "reached": len(reached),
    "opened": len(opened),
    "clock": len(started),
    "threads": threading.active_count() - _before_threads,
}))
"""


def run_probe(prelude):
    """Run one probe in a fresh process and return what it printed."""
    finished = subprocess.run(
        [sys.executable, "-"],
        input=(PROBE % {"repo": str(REPO_ROOT), "prelude": prelude}).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=90,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr.decode()
    return json.loads(finished.stdout.decode().strip().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """The surface pulls Qt in, so the frontend cannot run without it."""
    answered = run_probe("sys.modules['PySide6'] = None")
    assert answered["qt"] == [], answered
    assert answered["ok"] is True
    assert answered["symbols"] == ["BTC/USDC", "ETH/USDC"]
    assert answered["lights"] == surface.GATE_COUNT


def test_the_qt_probe_can_report_qt():
    """The probe reports no Qt whatever the process loaded."""
    answered = run_probe("import PySide6")
    assert answered["qt"] == ["PySide6"], answered


def test_the_import_and_the_answer_touch_no_clock_no_file_and_no_thread():
    """Reaching the surface read the clock, opened a file or started a worker."""
    answered = run_probe("sys.modules['PySide6'] = None")
    assert answered["clock"] == 0, answered
    assert answered["threads"] == 0, answered
    assert answered["reached"] == 0, answered


def test_the_probe_counters_report_what_the_child_really_did():
    """The counters never reach the child, so their zeros mean nothing."""
    planted = run_probe(
        "sys.modules['PySide6'] = None\n"
        "socket.getaddrinfo('localhost', 9)\n"
        "clock.time()\n"
        "open('main.py').close()\n"
        "threading.Thread(target=lambda: __import__('time').sleep(2)).start()\n"
    )
    assert planted["reached"] == 1, planted
    assert planted["clock"] == 1, planted
    assert planted["opened"] >= 1, planted
    assert planted["threads"] == 1, planted


def test_the_connection_counter_watches_this_process_only():
    """The counter is claimed to watch a child it never reaches.

    The in-process counter above replaces this process's own socket
    calls, so it sees nothing a child process opens. The probe carries
    its own counter for that reason, and the two are separate.
    """
    child = run_probe("sys.modules['PySide6'] = None")
    assert child["reached"] == 0
    assert socket.getaddrinfo is not None


HOME_PROBE = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, %(repo)r)
home = Path(os.environ["ACERVATOR_TEST_HOME"])
before = sorted(str(p) for p in home.rglob("*") if p.is_file())
from src.gui.main_tabs import sim_visuals_surface as surface
made = []
for focus in ("", "BTC/USDC"):
    chart = surface.PriceVwapModel()
    chart.set_symbols(["BTC/USDC", "ETH/USDC"])
    for index in range(5):
        chart.append_tick("BTC/USDC", 10.0 + index, 1.0, 1700000000000 + index)
    chart.mark_trade("BTC/USDC", True)
    chart.set_ytd_start("BTC/USDC", 1700000000000)
    chart.set_focus_symbol(focus)
    panel = surface.GatePanelModel()
    panel.set_symbols(["BTC/USDC"])
    panel.cell_for("BTC/USDC").update_gates(True, False, ["delta<=0"], [], "upper")
    votes = surface.VotingReadoutModel()
    votes.set_bots(["BTC/USDC"])
    made.append(len(surface.build_view_model(
        panel=panel, chart=chart, votes=votes, width_px=900, height_px=400,
    )["chart"]["program"]))
%(extra)s
after = sorted(str(p) for p in home.rglob("*") if p.is_file())
print(json.dumps({"before": len(before), "after": len(after), "drawn": made}))
"""


def run_home_probe(extra):
    """Drive the surface in a fresh process under a throwaway home."""
    home = Path(tempfile.mkdtemp(prefix="acervator-throwaway-home-"))
    environment = dict(os.environ)
    environment["ACERVATOR_TEST_HOME"] = str(home)
    finished = subprocess.run(
        [sys.executable, "-"],
        input=(HOME_PROBE % {"repo": str(REPO_ROOT), "extra": extra}).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=environment,
        timeout=90,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr.decode()
    return json.loads(finished.stdout.decode().strip().splitlines()[-1]), home


def test_a_whole_run_of_every_view_creates_no_file():
    """The surface wrote a file, so a view model reached the disk."""
    answered, home = run_home_probe("")
    assert answered["before"] == 0
    assert answered["after"] == 0, answered
    assert all(drawn > 0 for drawn in answered["drawn"]), answered
    assert list(home.rglob("*")) == []


def test_the_file_counter_reports_a_file_that_was_created():
    """The file counter cannot see a file, so its zero means nothing."""
    answered, home = run_home_probe('(home / "one.txt").write_bytes(b"1")')
    assert answered["before"] == 0
    assert answered["after"] == 1, answered
    assert [p.name for p in home.rglob("*")] == ["one.txt"]


# The bridge


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_sim_visuals_method():
    """The renderer cannot reach the Simulator visuals over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "sim_visuals.state"
    answer = bridge_answer({})
    assert answer["ok"] is True
    assert answer["result"]["method"] == surface.METHOD
    assert answer["result"]["gate_panel"]["empty_visible"] is True


def test_the_bridge_builds_the_screen_a_request_asks_for():
    """The bridge ignored the fleet, the ticks or the gates a request carried."""
    result = bridge_answer(
        {
            "symbols": FLEET,
            "ticks": [
                {"symbol": PAIR, "close": 10.0, "volume": 1.0},
                {"symbol": PAIR, "close": 11.0, "volume": 2.0},
            ],
            "gates": [{"symbol": PAIR, "scrum_armed": True, "fold_armed": False}],
            "focus": PAIR,
            "width_px": 900,
            "height_px": 400,
        }
    )["result"]
    assert result["chart"]["symbols"] == FLEET
    assert result["chart"]["focus"] == PAIR
    assert result["gate_panel"]["symbols"] == sorted(FLEET)
    assert len(result["gate_row"]["rows"][PAIR]["lights"]) == surface.GATE_COUNT
    assert [row["cells"][0] for row in result["votes"]["rows"]] == FLEET
    assert result["chart"]["program"], "the focused chart drew nothing"


def test_the_bridge_reports_a_request_it_cannot_use():
    """A bad request reads as a working answer."""
    answer = bridge_answer(
        {"symbols": FLEET, "ticks": [{"symbol": PAIR, "close": "x"}]}
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"


def test_the_bridge_answer_is_json_serialisable():
    """The answer holds something the pipe cannot carry."""
    answer = bridge_answer({"symbols": [UNICODE_TEXT]})
    text = json.dumps(answer, ensure_ascii=True)
    assert json.loads(text) == answer
    assert "\n" not in text


# Sweeping this file for checks that cannot fail

THIS_FILE = Path(__file__).resolve()

LIVE_COLOUR_READS = ("styleSheet", "palette", "background", "foreground")


def live_colour_reads(tree) -> list:
    """Every read of a colour off a live widget rather than off a render."""
    return sorted(
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in LIVE_COLOUR_READS
    )


def compared_to_itself(tree) -> list:
    """Every comparison whose two sides are written the same way."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        sides = [ast.dump(node.left)] + [ast.dump(one) for one in node.comparators]
        for index in range(len(sides) - 1):
            if sides[index] == sides[index + 1]:
                found.append(node.lineno)
    return sorted(found)


def constant_assertions(tree) -> list:
    """Every assertion whose test is a written-down value."""
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant)
    )


def test_no_colour_claim_is_read_off_a_live_widget_in_the_surface():
    """A colour was read off a widget instead of off a rendered picture."""
    assert live_colour_reads(parsed(SURFACE_SOURCE)) == []
    planted = "widget.palette().window().color().name()\n"
    assert live_colour_reads(parsed_text(planted)) == ["palette"]
    assert live_colour_reads(parsed(THIS_FILE)) == []
    assert planted.count("palette") == 1


def test_no_comparison_in_this_file_reads_one_value_twice():
    """A value compared to itself passes whatever the product does."""
    assert compared_to_itself(parsed(SURFACE_SOURCE)) == []
    assert compared_to_itself(parsed(THIS_FILE)) == []
    planted = "assert total == total\n"
    assert compared_to_itself(parsed_text(planted)) == [1]
    honest = "assert total == expected\n"
    assert compared_to_itself(parsed_text(honest)) == []


def test_no_assertion_in_this_file_reads_a_written_down_value():
    """An assertion on a constant cannot report anything."""
    assert constant_assertions(parsed(THIS_FILE)) == []
    assert constant_assertions(parsed(SURFACE_SOURCE)) == []
    planted = "assert True\nassert 1\n"
    assert constant_assertions(parsed_text(planted)) == [1, 2]
    honest = "assert found == []\n"
    assert constant_assertions(parsed_text(honest)) == []
