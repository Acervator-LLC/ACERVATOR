"""The Fold Tranches tokens answer the same as the panel they replace.

A failure means the Qt-free surface and the shipped Live Bot Settings
module disagree about a colour, a size, a row order, a filter, a health
verdict or a composed row -- on a panel that opens over a running bot.

Both sides are driven in one run, on the same inputs, and every answer is
compared by value and by hash. The shipped module's row composers carry a
leading underscore and the panel builder calls them by that name; there is
no public route to them, so this file names them directly.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.gui.live_settings import fold_tokens as shipped
from src.gui.main_tabs import fold_tokens_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SOURCE = REPO_ROOT / "src" / "gui" / "live_settings" / "fold_tokens.py"
SURFACE_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "fold_tokens_surface.py"

# Controls proving each counter reports; two modules in this tree share
# the basename history_tab.py, so each is named with its directory.
WIRING_CONTROL = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_CONTROL = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_BUILT_CONTROL = REPO_ROOT / "src" / "gui" / "history_tab.py"
TIMER_NONE_CONTROL = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
TIMER_STARTED_CONTROL = REPO_ROOT / "src" / "gui" / "indicator_panel.py"
BUS_CONTROL = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
ELEMENTS_CONTROL = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
NESTED_CLASS_CONTROL = REPO_ROOT / "src" / "gui" / "stock_main_window.py"

PIXEL_SIZE = (520, 260)
SKIN_CONTROL_RULE = (
    "QTableWidget { gridline-color: #3a1414; border: 3px solid #7a1414; }"
)


# Comparing two answers


def canonical(value):
    """`value` as text that keeps its type and separates every shape.

    A whole number and a decimal compare equal and must not; a
    not-a-number never equals itself and must. Both are settled by
    printing the type beside the value rather than comparing the values.
    """
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: canonical(item[0]))
        return ["dict", [[canonical(key), canonical(inner)] for key, inner in pairs]]
    if isinstance(value, (list, tuple)):
        return [type(value).__name__, [canonical(inner) for inner in value]]
    return f"{type(value).__name__}:{value!r}"


def digest(value) -> str:
    """SHA-256 over the canonical form of one answer."""
    return hashlib.sha256(repr(canonical(value)).encode("utf-8")).hexdigest()


class Answer:
    """What one side returned, or the type of refusal it raised."""

    def __init__(self, value=None, refusal=None):
        self.value = value
        self.refusal = refusal

    @property
    def key(self):
        return ["refused", self.refusal] if self.refusal else ["answered", self.value]

    @property
    def digest(self) -> str:
        return digest(self.key)

    def __repr__(self) -> str:
        if self.refusal:
            return f"<refused {self.refusal}>"
        return f"<answered {self.value!r}>"


def call(fn, args) -> Answer:
    """Run one side and keep its answer, or the TYPE of its refusal.

    The wording is never kept: the platform words a refusal differently
    by operand type and by release.
    """
    try:
        return Answer(value=fn(*args))
    except Exception as exc:
        return Answer(refusal=type(exc).__name__)


# The cases both sides are driven with


class RefusingTranche(dict):
    """A stored tranche whose every read raises, as a corrupt record does.

    A dict subclass, so both sides admit it at the ``isinstance`` gate and
    then meet the refusal on the read itself.
    """

    def get(self, *args):
        raise RuntimeError("this tranche refuses to be read")


LONG_TEXT = "t" * 200
MARKUP = "<b>BTC</b> & <i>ETH</i>"
NEWLINE_NAME = "BTC\nUSD"
APOSTROPHE = "it's the operator's"
UNICODE_PAIR = "straße/₿"
THOUSAND_MILLION = 1_000_000_000.0
ONE_BILLIONTH = 1e-9
NAN = float("nan")
INF = float("inf")
NEG_INF = float("-inf")
HUGE_INT = 2**1024

TRANCHES = [
    {"created_ts": 300.0, "usd": 10.0, "units": 1.5},
    {"created_ts": 100.0, "usd": 30.0, "units": 0.25},
    {"created_ts": 100.0, "usd": 20.0, "units": 2.0},
]
EXTRACTOR_ROW = {
    "opened_at": 100.0,
    "base_deployed": 2.5,
    "mark_value_usd": 33.5,
    "mark_price_base_per_alt": 0.004,
    "alt_units": 12.5,
    "state": "IN_FLIGHT",
    "pair": "ETH/BTC",
    "base_asset": "BTC",
    "child_bot_name": "extractor-1",
    "child_bot_id": "c8e5c5db",
}

# name -> (step, args). Every case is driven through BOTH sides.
CASES = {
    # --- happy paths, one per step -----------------------------------
    "finite_happy": (surface.STEP_FINITE, [12.5]),
    "order_queue": (surface.STEP_ORDER, [TRANCHES, "Queue order"]),
    "order_oldest": (surface.STEP_ORDER, [TRANCHES, "Oldest first"]),
    "order_newest": (surface.STEP_ORDER, [TRANCHES, "Newest first"]),
    "order_largest": (surface.STEP_ORDER, [TRANCHES, "Largest USD first"]),
    "order_smallest": (surface.STEP_ORDER, [TRANCHES, "Smallest USD first"]),
    "filter_hit": (surface.STEP_FILTER, [["BTC", "$5.00"], "btc"]),
    "height_happy": (surface.STEP_HEIGHT, [3]),
    "chrome_happy": (surface.STEP_CHROME, [13, 14]),
    "health_row_happy": (surface.STEP_HEALTH_ROW, ["Open tranches:", "a tooltip"]),
    "units_happy": (surface.STEP_UNITS_ROW, [TRANCHES, 8.0]),
    "ratio_happy": (surface.STEP_RATIO, [10, 9, 0]),
    "source_manual": (surface.STEP_SOURCE, [{"operator_initiated": True}]),
    "source_auto_rebalance": (surface.STEP_SOURCE, [{"operator_initiated": False}]),
    "source_auto_scrum": (surface.STEP_SOURCE, [{}]),
    "arbiter_parent": (surface.STEP_ARBITER, ["parent"]),
    "arbiter_sibling": (surface.STEP_ARBITER, ["sibling"]),
    "arbiter_tip_parent": (surface.STEP_ARBITER_TIP, ["parent"]),
    "arbiter_tip_sibling": (surface.STEP_ARBITER_TIP, ["sibling"]),
    "age_days": (surface.STEP_AGE, [90061]),
    "age_hours": (surface.STEP_AGE, [3661]),
    "age_minutes": (surface.STEP_AGE, [61]),
    "cells_happy": (surface.STEP_CELLS, [EXTRACTOR_ROW, 90000.0]),
    "extractor_tip_happy": (surface.STEP_EXTRACTOR_TIP, [EXTRACTOR_ROW]),
    "border_fold": (surface.STEP_BORDER, [surface.FOLD_TRANCHE_BG_HEX]),
    "border_extractor": (surface.STEP_BORDER, [surface.EXTRACTOR_TRANCHE_BG_HEX]),
    "border_unknown_fill": (surface.STEP_BORDER, ["#123456"]),
    # --- empty, zero, negative ---------------------------------------
    "order_no_tranches": (surface.STEP_ORDER, [[], "Oldest first"]),
    "order_none_list": (surface.STEP_ORDER, [None, "Oldest first"]),
    "units_no_tranches": (surface.STEP_UNITS_ROW, [[], 1.0]),
    "units_none_list": (surface.STEP_UNITS_ROW, [None, 1.0]),
    "units_zero_held": (surface.STEP_UNITS_ROW, [TRANCHES, 0]),
    "units_negative_held": (surface.STEP_UNITS_ROW, [TRANCHES, -2.0]),
    "units_negative_units": (surface.STEP_UNITS_ROW, [[{"units": -5.0}], 1.0]),
    "ratio_all_zero": (surface.STEP_RATIO, [0, 0, 0]),
    "ratio_negative_created": (surface.STEP_RATIO, [-1, 0, 0]),
    "height_zero_rows": (surface.STEP_HEIGHT, [0]),
    "height_none_rows": (surface.STEP_HEIGHT, [None]),
    "height_negative_rows": (surface.STEP_HEIGHT, [-5]),
    "age_zero": (surface.STEP_AGE, [0]),
    "age_negative": (surface.STEP_AGE, [-1]),
    "age_none": (surface.STEP_AGE, [None]),
    "filter_empty_cells": (surface.STEP_FILTER, [[], "btc"]),
    "filter_blank_needle": (surface.STEP_FILTER, [["BTC"], "   "]),
    "filter_none_needle": (surface.STEP_FILTER, [["BTC"], None]),
    "filter_zero_needle": (surface.STEP_FILTER, [["BTC 0"], 0]),
    "filter_none_cell": (surface.STEP_FILTER, [[None, "BTC"], "btc"]),
    "finite_zero": (surface.STEP_FINITE, [0]),
    "finite_negative": (surface.STEP_FINITE, [-4.5]),
    # --- the extremes -------------------------------------------------
    "units_thousand_million": (
        surface.STEP_UNITS_ROW,
        [[{"units": THOUSAND_MILLION}], 1.0],
    ),
    "units_one_billionth": (surface.STEP_UNITS_ROW, [[{"units": ONE_BILLIONTH}], 1.0]),
    "finite_thousand_million": (surface.STEP_FINITE, [THOUSAND_MILLION]),
    "finite_one_billionth": (surface.STEP_FINITE, [ONE_BILLIONTH]),
    "finite_nan": (surface.STEP_FINITE, [NAN]),
    "finite_inf": (surface.STEP_FINITE, [INF]),
    "finite_neg_inf": (surface.STEP_FINITE, [NEG_INF]),
    "finite_huge_int": (surface.STEP_FINITE, [HUGE_INT]),
    "finite_at_the_bound": (surface.STEP_FINITE, [2**1023]),
    "finite_over_the_bound": (surface.STEP_FINITE, [2**1023 + 1]),
    "finite_under_the_bound": (surface.STEP_FINITE, [-(2**1023) - 1]),
    "finite_true": (surface.STEP_FINITE, [True]),
    "finite_false": (surface.STEP_FINITE, [False]),
    "units_nan": (surface.STEP_UNITS_ROW, [[{"units": NAN}], 1.0]),
    "units_inf": (surface.STEP_UNITS_ROW, [[{"units": INF}], 1.0]),
    "units_neg_inf": (surface.STEP_UNITS_ROW, [[{"units": NEG_INF}], 1.0]),
    "units_held_nan": (surface.STEP_UNITS_ROW, [TRANCHES, NAN]),
    "units_held_inf": (surface.STEP_UNITS_ROW, [TRANCHES, INF]),
    "age_nan": (surface.STEP_AGE, [NAN]),
    "age_inf": (surface.STEP_AGE, [INF]),
    "age_neg_inf": (surface.STEP_AGE, [NEG_INF]),
    "ratio_nan_created": (surface.STEP_RATIO, [NAN, 1, 0]),
    "ratio_inf_created": (surface.STEP_RATIO, [INF, 1, 0]),
    "order_nan_key": (
        surface.STEP_ORDER,
        [[{"usd": NAN}, {"usd": 2.0}], "Largest USD first"],
    ),
    "order_inf_key": (
        surface.STEP_ORDER,
        [[{"usd": INF}, {"usd": 2.0}], "Largest USD first"],
    ),
    "order_huge_int_key": (
        surface.STEP_ORDER,
        [[{"usd": HUGE_INT}, {"usd": 2.0}], "Largest USD first"],
    ),
    "order_bool_key": (
        surface.STEP_ORDER,
        [[{"usd": True}, {"usd": 2.0}], "Largest USD first"],
    ),
    # --- text where a number belongs, and the reverse -----------------
    "ratio_text_created": (surface.STEP_RATIO, ["x", 1, 0]),
    "ratio_text_discarded_that_parses": (surface.STEP_RATIO, [10, 5, "2"]),
    "age_text": (surface.STEP_AGE, ["x"]),
    "height_text_rows": (surface.STEP_HEIGHT, ["4"]),
    "finite_text": (surface.STEP_FINITE, ["5.0"]),
    "cells_text_where_a_number_belongs": (
        surface.STEP_CELLS,
        [dict(EXTRACTOR_ROW, base_deployed="x"), 90000.0],
    ),
    "cells_number_where_text_belongs": (
        surface.STEP_CELLS,
        [dict(EXTRACTOR_ROW, state=7, pair=42), 90000.0],
    ),
    "filter_number_where_text_belongs": (surface.STEP_FILTER, [[7, 8.5], "8.5"]),
    "arbiter_number": (surface.STEP_ARBITER, [7]),
    "arbiter_none": (surface.STEP_ARBITER, [None]),
    "source_number_flag": (surface.STEP_SOURCE, [{"operator_initiated": 0}]),
    # --- text shapes ---------------------------------------------------
    "filter_unicode": (surface.STEP_FILTER, [[UNICODE_PAIR], "STRASSE"]),
    "filter_long_text": (surface.STEP_FILTER, [[LONG_TEXT], LONG_TEXT]),
    "filter_markup": (surface.STEP_FILTER, [[MARKUP], "<b>btc</b>"]),
    "filter_apostrophe": (surface.STEP_FILTER, [[APOSTROPHE], "IT'S"]),
    "filter_wrong_capitals": (surface.STEP_FILTER, [["BtC/UsD"], "bTc/uSd"]),
    "filter_newline_name": (surface.STEP_FILTER, [[NEWLINE_NAME], "btc\nusd"]),
    "cells_unicode_pair": (
        surface.STEP_CELLS,
        [dict(EXTRACTOR_ROW, pair=UNICODE_PAIR), 90000.0],
    ),
    "cells_long_state": (
        surface.STEP_CELLS,
        [dict(EXTRACTOR_ROW, state=LONG_TEXT), 90000.0],
    ),
    "cells_markup_pair": (
        surface.STEP_CELLS,
        [dict(EXTRACTOR_ROW, pair=MARKUP), 90000.0],
    ),
    "cells_newline_pair": (
        surface.STEP_CELLS,
        [dict(EXTRACTOR_ROW, pair=NEWLINE_NAME), 90000.0],
    ),
    "extractor_tip_apostrophe": (
        surface.STEP_EXTRACTOR_TIP,
        [dict(EXTRACTOR_ROW, child_bot_name=APOSTROPHE)],
    ),
    "extractor_tip_unicode": (
        surface.STEP_EXTRACTOR_TIP,
        [dict(EXTRACTOR_ROW, base_asset=UNICODE_PAIR)],
    ),
    "arbiter_tip_long_text": (surface.STEP_ARBITER_TIP, [LONG_TEXT]),
    "arbiter_wrong_capitals": (surface.STEP_ARBITER, ["  PaReNt  "]),
    "arbiter_newline": (surface.STEP_ARBITER, ["parent\n"]),
    # --- what a fold-token screen earns -------------------------------
    "order_tranche_with_no_parent": (
        surface.STEP_ORDER,
        [[{"usd": 5.0}, "not a tranche", None], "Largest USD first"],
    ),
    "units_tranche_with_no_parent": (
        surface.STEP_UNITS_ROW,
        [[{"units": 1.0}, "not a tranche", None], 1.0],
    ),
    "units_ratio_out_of_range": (surface.STEP_UNITS_ROW, [[{"units": 3.0}], 1.0]),
    "units_ratio_exactly_one": (surface.STEP_UNITS_ROW, [[{"units": 1.0}], 1.0]),
    "ratio_over_one_hundred": (surface.STEP_RATIO, [10, 20, 0]),
    "ratio_every_discarded": (surface.STEP_RATIO, [10, 0, 10]),
    "ratio_below_the_colour_floor": (surface.STEP_RATIO, [4, 4, 0]),
    "ratio_at_the_colour_floor": (surface.STEP_RATIO, [5, 5, 0]),
    "ratio_red_band": (surface.STEP_RATIO, [10, 4, 0]),
    "ratio_amber_band": (surface.STEP_RATIO, [10, 7, 0]),
    "ratio_the_live_btc_reading": (surface.STEP_RATIO, [160, 118, 42]),
    "order_bot_refuses": (
        surface.STEP_ORDER,
        [[RefusingTranche(), {"usd": 1.0}], "Largest USD first"],
    ),
    "units_bot_refuses": (surface.STEP_UNITS_ROW, [[RefusingTranche()], 1.0]),
    "source_bot_refuses": (surface.STEP_SOURCE, [RefusingTranche()]),
    "cells_venue_would_reject_the_mark": (
        surface.STEP_CELLS,
        [dict(EXTRACTOR_ROW, mark_value_usd=True), 90000.0],
    ),
    "cells_no_mark": (
        surface.STEP_CELLS,
        [dict(EXTRACTOR_ROW, mark_value_usd=None), 90000.0],
    ),
    "cells_empty_row": (surface.STEP_CELLS, [{}, 90000.0]),
    "cells_never_opened": (
        surface.STEP_CELLS,
        [dict(EXTRACTOR_ROW, opened_at=0), 90000.0],
    ),
    "cells_opened_in_the_future": (surface.STEP_CELLS, [EXTRACTOR_ROW, 50.0]),
    "extractor_tip_empty_row": (surface.STEP_EXTRACTOR_TIP, [{}]),
    "extractor_tip_no_mark": (
        surface.STEP_EXTRACTOR_TIP,
        [dict(EXTRACTOR_ROW, mark_price_base_per_alt=NAN)],
    ),
    "source_not_a_dict": (surface.STEP_SOURCE, ["x"]),
    "height_at_the_ceiling": (surface.STEP_HEIGHT, [18]),
    "height_over_the_ceiling": (surface.STEP_HEIGHT, [230]),
    "height_measured_chrome": (surface.STEP_HEIGHT, [3, 30, 26]),
    "chrome_unpolished_frame": (surface.STEP_CHROME, [1, 14]),
    "chrome_text_reading": (surface.STEP_CHROME, ["x", 14]),
    "width_happy": (surface.STEP_WIDTH, [1100, 13]),
    "width_no_vertical_header": (
        surface.STEP_WIDTH,
        [1100, 13, False, False, 40, True, 14],
    ),
    "width_hidden_vertical_header": (
        surface.STEP_WIDTH,
        [1100, 13, True, True, 40, True, 14],
    ),
    "width_no_scroll_bar": (
        surface.STEP_WIDTH,
        [1100, 13, True, False, 40, False, 14],
    ),
    "width_text_reading": (surface.STEP_WIDTH, ["x", 13]),
}

# The shipped name each step is driven through; the row composers are
# private on the shipped module.
SHIPPED_BY_STEP = {
    surface.STEP_ORDER: "fold_display_order",
    surface.STEP_FILTER: "fold_row_matches_filter",
    surface.STEP_HEIGHT: "fold_table_max_height_px",
    surface.STEP_UNITS_ROW: "compose_units_marked_row",
    surface.STEP_RATIO: "compose_cycle_close_ratio",
    surface.STEP_SOURCE: "_fold_tranche_source_label",
    surface.STEP_ARBITER: "_arbiter_label",
    surface.STEP_ARBITER_TIP: "_compose_arbiter_tooltip",
    surface.STEP_AGE: "_format_tranche_age",
    surface.STEP_CELLS: "_compose_extractor_tranche_cells",
    surface.STEP_EXTRACTOR_TIP: "_compose_extractor_tranche_tooltip",
}

# Steps the shipped module reaches through a widget or a constant, mapped
# to the test that drives each against the shipped side.
STEPS_DRIVEN_ELSEWHERE = {
    surface.STEP_FINITE: "test_the_admission_rule_matches_the_one_the_panel_imports",
    surface.STEP_CHROME: "test_the_chrome_arithmetic_matches_on_a_real_table",
    surface.STEP_WIDTH: "test_the_natural_width_matches_on_a_real_table",
    surface.STEP_HEALTH_ROW: "test_the_health_row_plan_matches_a_real_form",
    surface.STEP_BORDER: "test_the_row_border_map_matches",
}


def shipped_side(step):
    """The shipped callable one step is driven through, or None."""
    name = SHIPPED_BY_STEP.get(step)
    return getattr(shipped, name) if name else None


def surface_side(step):
    """The surface callable one step is driven through."""
    return surface.STEP_HANDLERS[step]


def drive_both(step, args):
    """Run one case through each side, on its own copy of the inputs.

    Each side gets a deep copy, so neither can reach the other's values
    and a side that edits what it is handed cannot change the comparison.
    """
    old_args = copy.deepcopy(args)
    new_args = copy.deepcopy(args)
    assert canonical(old_args) == canonical(
        new_args
    ), f"{step}: the two sides were handed different starting values"
    return call(shipped_side(step), old_args), call(surface_side(step), new_args)


COMPARED = sorted(name for name, (step, _) in CASES.items() if shipped_side(step))


# The two sides answer alike


@pytest.mark.parametrize("name", COMPARED)
def test_the_two_sides_answer_the_same_for_one_case(name):
    """The surface answered differently than the panel it replaces."""
    step, args = CASES[name]
    old, new = drive_both(step, args)
    assert canonical(old.key) == canonical(
        new.key
    ), f"{name} ({step}): shipped {old!r}, surface {new!r}"


@pytest.mark.parametrize("name", COMPARED)
def test_the_two_sides_hash_the_same_for_one_case(name):
    """The two answers compare equal but are not the same shape."""
    step, args = CASES[name]
    old, new = drive_both(step, args)
    assert (
        old.digest == new.digest
    ), f"{name} ({step}): shipped {old.digest}, surface {new.digest}"


def test_no_compared_case_differs():
    """The difference between the two sides is not zero."""
    differing = []
    for name in COMPARED:
        step, args = CASES[name]
        old, new = drive_both(step, args)
        if old.digest != new.digest:
            differing.append(f"{name}: shipped {old!r} vs surface {new!r}")
    assert differing == [], differing


def test_the_sample_hashes_are_reported():
    """Four sampled answers carry no hash to report."""
    sampled = {}
    for name in ("order_oldest", "units_happy", "ratio_happy", "cells_happy"):
        step, args = CASES[name]
        old, new = drive_both(step, args)
        assert old.digest == new.digest, name
        sampled[name] = old.digest
    assert len(sampled) == 4, sampled
    assert len({len(one) for one in sampled.values()}) == 1
    assert all(len(one) == 64 for one in sampled.values()), sampled
    assert (
        len(set(sampled.values())) == 4
    ), f"four different answers hashed alike, so the hash cannot report: {sampled}"


@pytest.mark.parametrize("name", COMPARED)
def test_a_refused_case_names_the_same_refusal_type_on_both_sides(name):
    """One side raised where the other answered, or raised differently."""
    step, args = CASES[name]
    old, new = drive_both(step, args)
    assert (old.refusal is None) == (
        new.refusal is None
    ), f"{name}: shipped {old!r}, surface {new!r}"
    assert old.refusal == new.refusal, f"{name}: {old.refusal} vs {new.refusal}"


def test_the_case_set_drives_every_refusal_the_panel_can_reach():
    """A refusal path is written down but never driven."""
    refused = {}
    for name in COMPARED:
        step, args = CASES[name]
        old, _ = drive_both(step, args)
        if old.refusal:
            refused.setdefault(old.refusal, []).append(name)
    reachable = {
        shipped_age_refusal(AGE_REFUSED_BY_TEXT),
        shipped_age_refusal(AGE_REFUSED_BY_NOT_A_NUMBER),
        shipped_age_refusal(AGE_REFUSED_BY_INFINITY),
        call(shipped._fold_tranche_source_label, ["x"]).refusal,
        call(shipped.compose_units_marked_row, [[RefusingTranche()], 1.0]).refusal,
    }
    assert set(refused) == reachable, sorted(set(refused) ^ reachable)
    assert len(reachable) >= 4, reachable
    assert all(refused.values()), refused


# The comparison can report


TWO_REAL_INPUTS = [
    (surface.STEP_ORDER, [TRANCHES, "Oldest first"], [TRANCHES, "Newest first"]),
    (surface.STEP_UNITS_ROW, [TRANCHES, 8.0], [TRANCHES, 1.0]),
    (surface.STEP_RATIO, [10, 9, 0], [10, 4, 0]),
    (surface.STEP_AGE, [90061], [3661]),
    (surface.STEP_CELLS, [EXTRACTOR_ROW, 90000.0], [EXTRACTOR_ROW, 200000.0]),
]


@pytest.mark.parametrize("step,first,second", TWO_REAL_INPUTS)
def test_two_different_real_inputs_are_told_apart_old_then_new(step, first, second):
    """The comparison passes whatever the surface answered.

    The first real input goes through the shipped side and the second
    through the surface. A pass here would mean the check reports nothing.
    """
    old = call(shipped_side(step), copy.deepcopy(first))
    new = call(surface_side(step), copy.deepcopy(second))
    assert old.digest != new.digest, (
        f"{step}: two different real inputs hashed alike ({old.digest}), so "
        "the comparison would pass whatever the surface returned"
    )


@pytest.mark.parametrize("step,first,second", TWO_REAL_INPUTS)
def test_two_different_real_inputs_are_told_apart_new_then_old(step, first, second):
    """The comparison reports in one direction only.

    The same pair driven the other way round: the first input through the
    surface, the second through the shipped side.
    """
    new = call(surface_side(step), copy.deepcopy(first))
    old = call(shipped_side(step), copy.deepcopy(second))
    assert new.digest != old.digest, f"{step}: {new.digest} on both sides"


@pytest.mark.parametrize("step,first,second", TWO_REAL_INPUTS)
def test_the_same_input_hashes_the_same_through_either_side(step, first, second):
    """The hash moves with something other than the answer."""
    assert second is not None
    old = call(shipped_side(step), copy.deepcopy(first))
    new = call(surface_side(step), copy.deepcopy(first))
    again = call(surface_side(step), copy.deepcopy(first))
    assert old.digest == new.digest == again.digest, (old, new, again)


def test_the_canonical_form_separates_a_whole_number_from_a_decimal():
    """A whole number and a decimal hash alike, so a type change hides."""
    assert digest(12) != digest(12.0)
    assert canonical(12) != canonical(12.0)


def test_the_canonical_form_calls_a_not_a_number_equal_to_itself():
    """A not-a-number reads as a difference that is not one."""
    assert NAN != NAN
    assert digest(NAN) == digest(float("nan"))
    assert digest(NAN) != digest(INF)
    assert digest(INF) != digest(NEG_INF)


def test_the_canonical_form_reports_a_reordered_mapping_and_list():
    """A swap inside an answer reads as unchanged."""
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})
    assert digest([1, 2]) != digest([2, 1])
    assert digest(("a", "b")) != digest(["a", "b"])


def test_the_refusal_recorder_keeps_the_type_and_not_the_wording():
    """The recorder kept a wording the platform chose."""
    refused = call(lambda: 1 / 0, [])
    assert refused.refusal == "ZeroDivisionError"
    assert refused.value is None
    answered = call(lambda: 5, [])
    assert answered.refusal is None
    assert answered.value == 5
    assert refused.digest != answered.digest


# The five steps the shipped side reaches another way


def test_the_admission_rule_matches_the_one_the_panel_imports():
    """The surface admits a stored number the panel would refuse."""
    from src.trading.bot_container import as_finite_float

    probes = [
        0,
        1,
        -1,
        12.5,
        -0.0,
        NAN,
        INF,
        NEG_INF,
        True,
        False,
        None,
        "5.0",
        b"5",
        [],
        2**1023,
        2**1023 + 1,
        -(2**1023),
        -(2**1023) - 1,
        HUGE_INT,
    ]
    for probe in probes:
        assert canonical(as_finite_float(probe)) == canonical(
            surface.finite_number(probe)
        ), probe
    assert as_finite_float(2**1023) is not None
    assert as_finite_float(2**1023 + 1) is None, "the measured bound moved"


def test_the_admission_rule_probe_can_report_a_difference():
    """The admission comparison passes on a rule that admits anything."""
    assert canonical(surface.finite_number(True)) != canonical(float(True))
    assert canonical(surface.finite_number(NAN)) != canonical(NAN)


def test_the_row_border_map_matches():
    """A tranche fill gets the wrong edge, or none at all."""
    assert dict(shipped.TRANCHE_ROW_BORDER_BY_BG) == dict(
        surface.TRANCHE_ROW_BORDER_BY_BG
    )
    for fill, border in shipped.TRANCHE_ROW_BORDER_BY_BG.items():
        assert surface.row_border_hex(fill) == border
    assert surface.row_border_hex("#123456") is None
    assert surface.row_border_hex(None) is None
    assert len(surface.TRANCHE_ROW_BORDER_BY_BG) == 2


# Step sequences, and one that refuses part way


GOOD_SEQUENCE = [
    [surface.STEP_ARBITER, "parent"],
    [surface.STEP_AGE, 3661],
    [surface.STEP_RATIO, 10, 9, 0],
]
# The three inputs the age step refuses; each refusal's wording is read
# off the shipped side.
AGE_REFUSED_BY_TEXT = "x"
AGE_REFUSED_BY_NOT_A_NUMBER = NAN
AGE_REFUSED_BY_INFINITY = INF


def shipped_age_refusal(value) -> str:
    """The refusal type the SHIPPED age composer raises for one value."""
    refused = call(shipped._format_tranche_age, [value])
    assert refused.refusal is not None, f"{value!r} no longer refuses"
    return refused.refusal


REFUSING_SEQUENCE = [
    [surface.STEP_ARBITER, "parent"],
    [surface.STEP_AGE, 3661],
    [surface.STEP_AGE, AGE_REFUSED_BY_TEXT],
    [surface.STEP_RATIO, 10, 9, 0],
]
UNKNOWN_STEP_SEQUENCE = [
    [surface.STEP_ARBITER, "parent"],
    ["a_step_that_is_not_registered"],
    [surface.STEP_AGE, 3661],
]


def test_a_sequence_that_runs_through_records_every_step():
    """A step that answered was not recorded."""
    driven = surface.FoldTokensModel().run_steps(GOOD_SEQUENCE)
    assert driven["ran"] == len(GOOD_SEQUENCE)
    assert driven["refused"] is None
    assert [call[0] for call in driven["calls"]] == [step[0] for step in GOOD_SEQUENCE]
    assert driven["calls"][0][1] == "Parent"
    assert driven["calls"][1][1] == "1h 1m"


def test_a_sequence_that_refuses_part_way_keeps_what_it_recorded():
    """The recorder threw away the steps taken before the refusal."""
    driven = surface.FoldTokensModel().run_steps(REFUSING_SEQUENCE)
    assert driven["ran"] == 2, driven
    assert [call[0] for call in driven["calls"]] == [
        surface.STEP_ARBITER,
        surface.STEP_AGE,
    ]
    assert driven["calls"][0][1] == "Parent"
    assert driven["refused"] == {
        "index": 2,
        "step": surface.STEP_AGE,
        "refusal_type": shipped_age_refusal(AGE_REFUSED_BY_TEXT),
    }, driven["refused"]


def test_the_refusal_index_names_the_step_that_refused():
    """The refusal is charged to the wrong step of the sequence."""
    driven = surface.FoldTokensModel().run_steps(REFUSING_SEQUENCE)
    index = driven["refused"]["index"]
    assert index == len(driven["calls"])
    assert REFUSING_SEQUENCE[index][0] == driven["refused"]["step"]
    assert driven["ran"] < len(REFUSING_SEQUENCE)


def test_a_step_the_surface_does_not_register_refuses_by_type():
    """An unknown step name ran something, or refused silently."""
    driven = surface.FoldTokensModel().run_steps(UNKNOWN_STEP_SEQUENCE)
    assert driven["ran"] == 1
    assert driven["refused"]["step"] == "a_step_that_is_not_registered"
    assert driven["refused"]["refusal_type"] == surface.UNKNOWN_STEP_REFUSAL.__name__
    assert driven["refused"]["index"] == 1
    assert len(driven["calls"]) == 1


@pytest.mark.parametrize(
    "value",
    [AGE_REFUSED_BY_TEXT, AGE_REFUSED_BY_NOT_A_NUMBER, AGE_REFUSED_BY_INFINITY],
)
def test_the_recorder_names_the_refusal_the_shipped_side_raises(value):
    """The recorder reports one refusal name whatever actually happened."""
    driven = surface.FoldTokensModel().run_steps(
        [[surface.STEP_ARBITER, "parent"], [surface.STEP_AGE, value]]
    )
    assert driven["ran"] == 1
    assert driven["refused"]["refusal_type"] == shipped_age_refusal(value)


def test_the_three_age_refusals_do_not_all_carry_one_name():
    """Three refusal paths share a name, so a swap between them hides."""
    named = {
        shipped_age_refusal(value)
        for value in (
            AGE_REFUSED_BY_TEXT,
            AGE_REFUSED_BY_NOT_A_NUMBER,
            AGE_REFUSED_BY_INFINITY,
        )
    }
    assert len(named) == 3, named


def test_the_sequence_recorder_can_report_a_lost_record():
    """The recorder reports the same thing whatever it recorded."""
    ran_through = surface.FoldTokensModel().run_steps(GOOD_SEQUENCE)
    refused = surface.FoldTokensModel().run_steps(REFUSING_SEQUENCE)
    assert ran_through["ran"] != refused["ran"]
    assert len(ran_through["calls"]) != len(refused["calls"])
    assert ran_through["refused"] is None and refused["refused"] is not None
    assert surface.FoldTokensModel().run_steps([])["calls"] == []


def test_a_model_reused_after_a_refusal_still_holds_its_earlier_records():
    """A second sequence on one model wiped the first sequence's records."""
    model = surface.FoldTokensModel()
    first = model.run_steps(REFUSING_SEQUENCE)
    assert len(first["calls"]) == 2
    second = model.run_steps(GOOD_SEQUENCE)
    assert second["refused"] is None
    assert len(second["calls"]) == 5, second["calls"]
    assert [call[0] for call in second["calls"]][:2] == [
        surface.STEP_ARBITER,
        surface.STEP_AGE,
    ]


# The three helpers that read a live widget


_alive: list = []


def hold(widget):
    """Keep `widget` alive for the run so no read reaches a freed object."""
    _alive.append(widget)
    return widget


def qt_app():
    """The one application object, with this run's font choice applied."""
    from PySide6.QtWidgets import QApplication

    load_run_fonts()
    return QApplication.instance()


def built_table(columns=11, rows=3, hide_vertical_header=False):
    """A real tranche table of the shape the panel builds."""
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    qt_app()
    table = hold(QTableWidget())
    table.setColumnCount(columns)
    table.setRowCount(rows)
    table.setHorizontalHeaderLabels([f"c{index}" for index in range(columns)])
    for row in range(rows):
        for column in range(columns):
            table.setItem(row, column, QTableWidgetItem(f"{row}-{column}"))
    if hide_vertical_header:
        table.verticalHeader().hide()
    table.ensurePolished()
    return table


def table_readings(table):
    """The numbers the shipped helpers read off one polished table.

    Taken after ``ensurePolished`` because an unpolished frame width is
    not the one the shipped helpers read.
    """
    table.ensurePolished()
    header = table.verticalHeader()
    scroll = table.verticalScrollBar()
    return {
        "frame_width_px": int(table.frameWidth()),
        "hscroll_height_px": int(table.horizontalScrollBar().sizeHint().height()),
        "header_length_px": int(table.horizontalHeader().length()),
        "vheader_present": header is not None,
        "vheader_hidden": bool(header is not None and header.isHidden()),
        "vheader_width_px": int(header.width()) if header is not None else 0,
        "vscroll_present": scroll is not None,
        "vscroll_width_px": int(scroll.sizeHint().width()) if scroll is not None else 0,
    }


@pytest.mark.parametrize("columns,rows", [(11, 3), (2, 1), (11, 40)])
def test_the_chrome_arithmetic_matches_on_a_real_table(columns, rows):
    """The surface budgets different chrome than the panel measures."""
    table = built_table(columns=columns, rows=rows)
    read = table_readings(table)
    assert shipped.fold_table_chrome_px(table) == surface.table_chrome_px(
        read["frame_width_px"], read["hscroll_height_px"]
    )


@pytest.mark.parametrize("hidden", [False, True])
def test_the_natural_width_matches_on_a_real_table(hidden):
    """The surface computes a different table width than the panel."""
    table = built_table(hide_vertical_header=hidden)
    read = table_readings(table)
    assert read["vheader_hidden"] is hidden
    assert shipped.fold_table_natural_width_px(table) == surface.table_natural_width_px(
        read["header_length_px"],
        read["frame_width_px"],
        vheader_present=read["vheader_present"],
        vheader_hidden=read["vheader_hidden"],
        vheader_width_px=read["vheader_width_px"],
        vscroll_present=read["vscroll_present"],
        vscroll_width_px=read["vscroll_width_px"],
    )


def test_the_width_reader_tells_the_two_tables_apart():
    """The width reader answers the same for every table it is given."""
    wide = built_table(columns=11)
    narrow = built_table(columns=2)
    assert shipped.fold_table_natural_width_px(wide) != (
        shipped.fold_table_natural_width_px(narrow)
    )


def test_a_missing_vertical_header_is_not_folded_into_a_hidden_one():
    """A table that lost its header reads as one that merely hid it.

    Both add nothing to the width, so the two absences are kept apart on
    the surface rather than reaching one value.
    """
    read = table_readings(built_table())
    absent = surface.table_natural_width_px(
        read["header_length_px"], read["frame_width_px"], vheader_present=False
    )
    hidden = surface.table_natural_width_px(
        read["header_length_px"],
        read["frame_width_px"],
        vheader_hidden=True,
        vheader_width_px=read["vheader_width_px"],
    )
    shown = surface.table_natural_width_px(
        read["header_length_px"], read["frame_width_px"], vheader_width_px=40
    )
    assert absent == hidden
    assert shown == absent + 40, "the shown branch adds nothing, so it cannot report"


def test_the_health_row_plan_matches_a_real_form():
    """The panel tooltips a half of the row the surface leaves bare."""
    from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

    qt_app()
    host = hold(QWidget())
    form = QFormLayout(host)
    untouched = QLabel("untouched")
    form.addRow("before:", untouched)

    value = QLabel("42")
    returned = shipped.install_health_row(form, "Open tranches:", value, "a tooltip")
    label = form.labelForField(value)
    plan = surface.health_row_plan("Open tranches:", "a tooltip", label is not None)

    assert (returned is value) is plan["returns_widget"]
    assert value.toolTip() == plan["widget_tooltip"]
    assert label is not None
    assert label.text() == plan["label_text"]
    assert label.toolTip() == plan["label_tooltip"]
    assert form.rowCount() == 2
    assert untouched.toolTip() == ""
    assert form.labelForField(untouched).toolTip() == ""


def test_the_health_row_leaves_no_label_when_the_form_holds_none():
    """A widget-only row is given a label tooltip that does not exist."""
    from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

    qt_app()
    host = hold(QWidget())
    form = QFormLayout(host)
    value = QLabel("42")
    form.addRow(value)
    assert form.labelForField(value) is None
    plan = surface.health_row_plan("Open tranches:", "a tooltip", False)
    assert plan["label_tooltip"] is None
    assert plan["widget_tooltip"] == "a tooltip"


def test_the_health_row_edits_only_what_it_is_handed():
    """The panel's row installer reached a widget it was not given."""
    from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

    qt_app()
    host = hold(QWidget())
    form = QFormLayout(host)
    bystander = QLabel("bystander")
    form.addRow("bystander:", bystander)
    bystander_label = form.labelForField(bystander)
    before = (bystander.toolTip(), bystander_label.toolTip(), form.rowCount())

    value = QLabel("42")
    shipped.install_health_row(form, "Open tranches:", value, "a tooltip")

    assert (bystander.toolTip(), bystander_label.toolTip()) == before[:2]
    assert form.rowCount() == before[2] + 1
    assert value.toolTip() == "a tooltip"


# Enumeration: what each side holds


def parsed(path):
    """The parsed tree of one source file."""
    return ast.parse(path.read_text(encoding="utf-8"))


def dotted(node) -> str:
    """A call target as its dotted name."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def owners(tree):
    """Every node in `tree` mapped to the node that holds it."""
    held = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            held[child] = parent
    return held


def enclosing_class(node, held):
    """The name of the class one node sits inside, or None."""
    current = held.get(node)
    while current is not None:
        if isinstance(current, ast.ClassDef):
            return current.name
        current = held.get(current)
    return None


def classes_in(path) -> list:
    """Every class one file declares, including one inside a method."""
    return sorted(
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    )


def methods_in(path) -> list:
    """Every method one file declares, as ``Class.name``.

    Walks the whole tree, so a class nested inside a method or inside a
    ``try`` block is counted. A signal declared in a class body is an
    assignment, not a function, so it is not counted here.
    """
    tree = parsed(path)
    held = owners(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = enclosing_class(node, held)
            if owner:
                found.append(f"{owner}.{node.name}")
    return sorted(found)


def functions_in(path) -> list:
    """Every module-level function one file declares."""
    tree = parsed(path)
    held = owners(tree)
    return sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and enclosing_class(node, held) is None
    )


def signals_in(path) -> list:
    """Every ``Signal()`` a class body declares, as ``Class.name``."""
    tree = parsed(path)
    held = owners(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if dotted(node.value.func).split(".")[-1] not in {"Signal", "pyqtSignal"}:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                found.append(f"{enclosing_class(node, held)}.{target.id}")
    return sorted(found)


def signal_emits_in(path) -> list:
    """Every ``.emit(`` call site in one file."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith(".emit")
    ]


def connects_in(path) -> list:
    """Every ``.connect(`` call site in one file."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith(".connect")
    ]


def threads_in(path) -> list:
    """Every worker-thread construction in one file."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and dotted(node.func).split(".")[-1]
        in {"QThread", "QRunnable", "QThreadPool", "Thread"}
    ]


def timers_built_in(path) -> list:
    """Every ``QTimer(`` construction in one file.

    Counted from the parsed tree, so a QTimer named in a comment or in a
    string is not counted and the import line is not counted either.
    """
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).split(".")[-1] == "QTimer"
    ]


def timers_started_in(path) -> list:
    """Every timer START in one file, in BOTH forms.

    ``QTimer.singleShot(...)`` starts a timer without building one that
    the file keeps, and ``something_timer.start(...)`` starts one it did.
    A count of constructions alone sees neither.
    """
    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.Call):
            continue
        name = dotted(node.func)
        if name.endswith("QTimer.singleShot"):
            found.append(("singleShot", name))
        elif name.endswith(".start") and "timer" in name.lower():
            found.append(("start", name))
    return found


def bus_subscribes_in(path) -> list:
    """Every event-bus subscribe in one file, as the topic it names."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and dotted(node.func).endswith(".subscribe")
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def bus_emits_in(path) -> list:
    """Every event-bus emit in one file, as the topic it names.

    Reads a bare ``emit(...)`` too, because an emit imported under
    another name and called as a plain function is invisible to a
    search for ``.emit(``.
    """
    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = dotted(node.func)
        tail = name.split(".")[-1]
        if tail in {"emit", "publish", "broadcast"} and isinstance(
            node.args[0], ast.Constant
        ):
            found.append(node.args[0].value)
    return sorted(found)


def imported_names_in(path) -> list:
    """Every name one file imports, as ``module.name``."""
    found = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                found.append(f"{'.' * node.level}{node.module or ''}.{alias.name}")
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return sorted(found)


def test_the_shipped_module_declares_no_class_no_signal_and_no_thread():
    """The panel's token module grew a class, a signal or a thread."""
    assert classes_in(SHIPPED_SOURCE) == []
    assert methods_in(SHIPPED_SOURCE) == []
    assert signals_in(SHIPPED_SOURCE) == []
    assert signal_emits_in(SHIPPED_SOURCE) == []
    assert threads_in(SHIPPED_SOURCE) == []


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """A class declared inside a method is invisible to the counter.

    Pointed at a neighbouring screen that really declares one, because a
    counter returning nothing on both files is no measurement.
    """
    found = classes_in(NESTED_CLASS_CONTROL)
    assert "_StockLogHandler" in found, found
    assert len(found) >= 2, found


def test_the_method_counter_finds_a_method_of_a_nested_class():
    """The method counter misses a class the file does not declare at top level."""
    found = methods_in(TIMER_STARTED_CONTROL)
    for wanted in (
        "IndicatorVotingPanel._reading_fingerprint",
        "IndicatorVotingPanel.lock_timeframe",
        "IndicatorVotingPanel.selected_bot_id",
    ):
        assert wanted in found, (wanted, len(found))


def test_the_method_counter_does_not_count_a_signal_as_a_method():
    """A signal is a class attribute, and a loose counter reads it as a method."""
    assert "ModeCard.clicked" in signals_in(SIGNAL_CONTROL)
    assert "ModeCard.clicked" not in methods_in(SIGNAL_CONTROL)
    assert len(signals_in(SIGNAL_CONTROL)) == 3, signals_in(SIGNAL_CONTROL)


def test_the_wiring_counter_reports_and_both_sides_wire_nothing():
    """The panel wires an action the surface names none of."""
    assert connects_in(SHIPPED_SOURCE) == []
    assert connects_in(SURFACE_SOURCE) == []
    assert surface.ACTIONS == {}
    assert len(connects_in(WIRING_CONTROL)) >= 1, "the wiring counter reports nothing"


def test_the_timer_counters_report_in_both_forms_and_both_sides_hold_none():
    """The panel runs a timer the surface declares no delay for."""
    assert timers_built_in(SHIPPED_SOURCE) == []
    assert timers_started_in(SHIPPED_SOURCE) == []
    assert timers_built_in(SURFACE_SOURCE) == []
    assert timers_started_in(SURFACE_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()

    built = timers_built_in(TIMER_BUILT_CONTROL)
    assert len(built) == 1, built
    assert (
        timers_built_in(TIMER_NONE_CONTROL) == []
    ), "two files share this basename and only one builds a timer"
    started = timers_started_in(TIMER_STARTED_CONTROL)
    assert {form for form, _ in started} == {"singleShot", "start"}, started
    assert len(started) > len(timers_built_in(TIMER_STARTED_CONTROL)), started


def test_the_bus_counters_report_in_both_directions_and_both_sides_are_silent():
    """The panel reaches the event bus and the surface does not say so."""
    assert bus_subscribes_in(SHIPPED_SOURCE) == []
    assert bus_emits_in(SHIPPED_SOURCE) == []
    assert bus_subscribes_in(SURFACE_SOURCE) == []
    assert bus_emits_in(SURFACE_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    assert surface.BUS_EMITS == ()

    subscribed = bus_subscribes_in(BUS_CONTROL)
    emitted = bus_emits_in(BUS_CONTROL)
    assert len(subscribed) >= 2, "the subscribe counter reports nothing"
    assert len(emitted) >= 2, "the emit counter reports nothing"


def test_the_emit_counter_sees_an_emit_called_as_a_plain_function():
    """An emit imported under another name walks past a dotted search."""
    plain_call = "def go():\n    shout('wire.created', usd=1)\n"
    found: list = []
    for node in ast.walk(ast.parse(plain_call)):
        if isinstance(node, ast.Call) and node.args:
            tail = dotted(node.func).split(".")[-1]
            if tail in {"emit", "publish", "broadcast", "shout"} and isinstance(
                node.args[0], ast.Constant
            ):
                found.append(node.args[0].value)
    assert found == ["wire.created"], found
    assert ".emit(" not in plain_call


def test_the_screen_element_counter_reports():
    """The element counter answers nothing whatever file it is given."""
    assert len(classes_in(ELEMENTS_CONTROL)) >= 1
    assert len(methods_in(ELEMENTS_CONTROL)) >= 5


def test_the_shipped_functions_all_have_a_counterpart():
    """The panel gained or lost a helper the surface does not carry."""
    declared = functions_in(SHIPPED_SOURCE)
    assert len(declared) == 14, declared
    counterparts = {
        "fold_table_chrome_px": "table_chrome_px",
        "fold_table_max_height_px": "table_max_height_px",
        "fold_table_natural_width_px": "table_natural_width_px",
        "fold_display_order": "fold_display_order",
        "fold_row_matches_filter": "fold_row_matches",
        "install_health_row": "health_row_plan",
        "compose_units_marked_row": "compose_units_marked_row",
        "compose_cycle_close_ratio": "compose_cycle_close_ratio",
        "_fold_tranche_source_label": "fold_source_label",
        "_arbiter_label": "arbiter_label",
        "_compose_arbiter_tooltip": "arbiter_tooltip",
        "_format_tranche_age": "format_tranche_age",
        "_compose_extractor_tranche_cells": "extractor_tranche_cells",
        "_compose_extractor_tranche_tooltip": "extractor_tranche_tooltip",
    }
    assert sorted(counterparts) == declared, sorted(set(counterparts) ^ set(declared))
    for shipped_name, surface_name in counterparts.items():
        assert callable(getattr(shipped, shipped_name)), shipped_name
        assert callable(getattr(surface, surface_name)), surface_name


def test_the_counterpart_reader_reports_a_name_neither_side_holds():
    """The counterpart reader accepts a helper that does not exist."""
    assert not hasattr(surface, "invented_helper")
    assert not hasattr(shipped, "invented_helper")
    assert "invented_helper" not in functions_in(SHIPPED_SOURCE)


def test_the_surface_declares_one_class_and_it_is_the_recorder():
    """The surface grew a class that stands in for nothing."""
    assert classes_in(SURFACE_SOURCE) == ["FoldTokensModel"]
    declared = [
        name
        for name in vars(surface.FoldTokensModel)
        if not name.startswith("__") or name == "__init__"
    ]
    assert sorted(declared) == ["__init__", "run", "run_steps"], declared


def test_the_recorder_overrides_no_method_the_class_never_declares():
    """A recorder that overrides a platform method counts it for ever.

    Every name on the recorder is one this file's source declares, so
    nothing was inherited and then re-counted.
    """
    from_source = {
        node.name
        for node in ast.walk(parsed(SURFACE_SOURCE))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    on_class = {
        name
        for name in vars(surface.FoldTokensModel)
        if not name.startswith("__") or name == "__init__"
    }
    assert on_class <= from_source, on_class - from_source
    assert surface.FoldTokensModel.__bases__ == (object,)


def test_the_shipped_module_imports_qt_for_annotations_only():
    """The panel's token module pulls Qt in at import time."""
    imported = imported_names_in(SHIPPED_SOURCE)
    assert any("PySide6" in one for one in imported), imported
    qt_at_runtime = [
        node
        for node in ast.walk(parsed(SHIPPED_SOURCE))
        if isinstance(node, ast.ImportFrom)
        and node.module
        and "PySide6" in node.module
        and not _inside_type_checking(node)
    ]
    assert qt_at_runtime == [], [node.lineno for node in qt_at_runtime]


def _inside_type_checking(node) -> bool:
    """Whether one import sits under ``if TYPE_CHECKING:``."""
    tree = parsed(SHIPPED_SOURCE)
    for outer in ast.walk(tree):
        if isinstance(outer, ast.If) and "TYPE_CHECKING" in ast.dump(outer.test):
            for inner in ast.walk(outer):
                if getattr(inner, "lineno", None) == node.lineno and isinstance(
                    inner, ast.ImportFrom
                ):
                    return True
    return False


def test_the_surface_names_no_qt_at_all():
    """The surface imports the interface library it exists to leave out."""
    assert [one for one in imported_names_in(SURFACE_SOURCE) if "PySide6" in one] == []
    assert "PySide6" not in SURFACE_SOURCE.read_text(encoding="utf-8")


def test_the_qt_import_reader_reports_a_runtime_import():
    """The Qt import reader reports nothing whatever the file holds."""
    assert any("PySide6" in one for one in imported_names_in(SHIPPED_SOURCE))
    assert imported_names_in(SURFACE_SOURCE) != imported_names_in(SHIPPED_SOURCE)


def test_neither_side_reads_the_clock_the_filesystem_or_the_environment():
    """A token module reached the clock, a file or the environment."""
    forbidden = {
        "time",
        "datetime",
        "os",
        "pathlib",
        "open",
        "random",
        "socket",
        "requests",
    }
    for path in (SHIPPED_SOURCE, SURFACE_SOURCE):
        imported = {one.split(".")[0].lstrip(".") for one in imported_names_in(path)}
        assert not (imported & forbidden), (path.name, imported & forbidden)
        names = {
            node.id
            for node in ast.walk(parsed(path))
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        assert "open" not in names, path.name


def test_the_clock_reader_reports_a_module_that_does_read_it():
    """The clock reader answers clean for every file it is given."""
    imported = {
        one.split(".")[0].lstrip(".")
        for one in imported_names_in(TIMER_STARTED_CONTROL)
    }
    assert imported & {"time", "datetime", "os", "math"}, imported


def test_the_row_age_takes_the_current_time_as_an_argument():
    """The row composer read the clock instead of being told the time."""
    first = surface.extractor_tranche_cells(EXTRACTOR_ROW, 90000.0)
    second = surface.extractor_tranche_cells(EXTRACTOR_ROW, 90000.0)
    later = surface.extractor_tranche_cells(EXTRACTOR_ROW, 900000.0)
    assert first == second
    assert first != later, "the age never moved, so the argument is unread"
    assert shipped._compose_extractor_tranche_cells(EXTRACTOR_ROW, 90000.0) == first


# Completeness: every exported value reaches the compared snapshot


# A value the snapshot does not carry, named with the test that covers it.
NOT_IN_THE_SNAPSHOT = {
    "ACTIONS": "test_the_wiring_counter_reports_and_both_sides_wire_nothing",
    "TIMERS": "test_the_timer_counters_report_in_both_forms_and_both_sides_hold_none",
    "TIMER_DELAYS_MS": (
        "test_the_timer_counters_report_in_both_forms_and_both_sides_hold_none"
    ),
    "BUS_TOPICS": (
        "test_the_bus_counters_report_in_both_directions_and_both_sides_are_silent"
    ),
    "BUS_EMITS": (
        "test_the_bus_counters_report_in_both_directions_and_both_sides_are_silent"
    ),
    "STEP_HANDLERS": "test_every_registered_step_is_driven_by_a_case_or_named",
}


def surface_constants() -> dict:
    """Every module-level value the surface exports, by its name."""
    tree = parsed(SURFACE_SOURCE)
    names: list = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names.extend(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return {name: getattr(surface, name) for name in names}


def as_snapshot_value(value):
    """One exported value in the shape the snapshot carries it."""
    if isinstance(value, tuple):
        return [as_snapshot_value(inner) for inner in value]
    if isinstance(value, dict):
        return {
            key: (
                [as_snapshot_value(one) for one in inner]
                if isinstance(inner, tuple)
                else inner
            )
            for key, inner in value.items()
        }
    if isinstance(value, int) and not isinstance(value, bool) and value > 2**64:
        return str(value)
    if isinstance(value, type):
        return value.__name__
    return value


def test_every_exported_value_reaches_the_compared_snapshot():
    """A value the comparison never reads can differ without reporting."""
    carried = surface.tokens()
    unaccounted = []
    for name, value in surface_constants().items():
        if name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
            continue
        if name not in carried:
            unaccounted.append(name)
            continue
        assert canonical(carried[name]) == canonical(as_snapshot_value(value)), name
    assert unaccounted == [], unaccounted
    assert len(NOT_IN_THE_SNAPSHOT) == 6


def test_no_snapshot_key_is_unbacked_by_an_exported_value():
    """The snapshot grew a key no value on the surface backs."""
    exported = set(surface_constants())
    unbacked = sorted(set(surface.tokens()) - exported)
    assert unbacked == [], unbacked
    assert len(surface.tokens()) == len(exported) - len(NOT_IN_THE_SNAPSHOT)


def test_the_completeness_check_can_report_both_ways():
    """The completeness pair passes because it reads nothing."""
    carried = surface.tokens()
    exported = surface_constants()
    invented = "A_VALUE_NOBODY_EXPORTS"
    assert invented not in carried
    assert invented not in exported
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert "FOLD_TRANCHE_BG_HEX" in carried and "FOLD_TRANCHE_BG_HEX" in exported
    assert "ACTIONS" in exported and "ACTIONS" not in carried
    assert "tokens" not in exported and "view_model" not in exported
    assert "FoldTokensModel" not in exported
    assert len(exported) > 100, len(exported)
    assert canonical(carried["FLOAT_SAFE_INT"]) != canonical(surface.FLOAT_SAFE_INT)
    assert carried["FLOAT_SAFE_INT"] == str(surface.FLOAT_SAFE_INT)


def test_every_registered_step_is_driven_by_a_case_or_named():
    """A step nobody drives can answer anything at all."""
    driven = {step for step, _ in CASES.values()}
    assert set(surface.STEP_HANDLERS) == set(surface.STEP_NAMES)
    assert driven == set(surface.STEP_NAMES), sorted(set(surface.STEP_NAMES) - driven)
    for step in surface.STEP_NAMES:
        assert shipped_side(step) or step in STEPS_DRIVEN_ELSEWHERE, step
    for step, test_name in STEPS_DRIVEN_ELSEWHERE.items():
        assert test_name in globals(), (step, test_name)
        assert callable(globals()[test_name]), (step, test_name)
    assert len(STEPS_DRIVEN_ELSEWHERE) + len(SHIPPED_BY_STEP) == len(surface.STEP_NAMES)


def test_the_case_table_is_driven_and_holds_no_case_it_never_runs():
    """A case is written down but reaches no comparison."""
    assert len(COMPARED) == len(
        [name for name, (step, _) in CASES.items() if step in SHIPPED_BY_STEP]
    )
    assert len(CASES) > len(COMPARED), "every case reaches the shipped side"
    not_compared = sorted(set(CASES) - set(COMPARED))
    for name in not_compared:
        assert CASES[name][0] in STEPS_DRIVEN_ELSEWHERE, name


# The surface carries its own values


SHARED_TOKENS = {
    "EXTRACTOR_TRANCHE_BG_HEX": "EXTRACTOR_TRANCHE_BG_HEX",
    "EXTRACTOR_TRANCHE_FG_HEX": "EXTRACTOR_TRANCHE_FG_HEX",
    "FOLD_TRANCHE_BG_HEX": "FOLD_TRANCHE_BG_HEX",
    "FOLD_TRANCHE_FG_HEX": "FOLD_TRANCHE_FG_HEX",
    "FOLD_TRANCHE_BORDER_HEX": "FOLD_TRANCHE_BORDER_HEX",
    "EXTRACTOR_TRANCHE_BORDER_HEX": "EXTRACTOR_TRANCHE_BORDER_HEX",
    "TRANCHE_ROW_BORDER_PX": "TRANCHE_ROW_BORDER_PX",
    "TRANCHE_ROW_HEIGHT_PX": "TRANCHE_ROW_HEIGHT_PX",
    "TRANCHE_FIRE_BTN_INSET_PX": "TRANCHE_FIRE_BTN_INSET_PX",
    "ARBITER_COLUMN_INDEX": "ARBITER_COLUMN_INDEX",
    "ARBITER_COLUMN_HEADER": "ARBITER_COLUMN_HEADER",
    "ARBITER_NOT_APPLICABLE": "ARBITER_NOT_APPLICABLE",
    "FOLD_SOURCE_MANUAL_SCRUM": "FOLD_SOURCE_MANUAL_SCRUM",
    "FOLD_SOURCE_AUTO_REBALANCE": "FOLD_SOURCE_AUTO_REBALANCE",
    "FOLD_SOURCE_AUTO_SCRUM": "FOLD_SOURCE_AUTO_SCRUM",
    "FOLD_SOURCE_MANUAL_FG_HEX": "FOLD_SOURCE_MANUAL_FG_HEX",
    "FOLD_SOURCE_TOOLTIPS": "FOLD_SOURCE_TOOLTIPS",
    "TRANCHE_TABLE_VISIBLE_ROWS": "TRANCHE_TABLE_VISIBLE_ROWS",
    "TRANCHE_TABLE_FRAME_PX": "TRANCHE_TABLE_FRAME_PX",
    "TRANCHE_TABLE_HEADER_PX": "TRANCHE_TABLE_HEADER_PX",
    "FOLD_SORT_QUEUE_ORDER": "FOLD_SORT_QUEUE_ORDER",
    "FOLD_SORT_OLDEST_FIRST": "FOLD_SORT_OLDEST_FIRST",
    "FOLD_SORT_NEWEST_FIRST": "FOLD_SORT_NEWEST_FIRST",
    "FOLD_SORT_LARGEST_FIRST": "FOLD_SORT_LARGEST_FIRST",
    "FOLD_SORT_SMALLEST_FIRST": "FOLD_SORT_SMALLEST_FIRST",
    "FOLD_SORT_ORDERS": "FOLD_SORT_ORDERS",
    "FOLD_SORT_KEYS": "FOLD_SORT_KEYS",
    "FOLD_COLUMN_TOOLTIPS": "FOLD_COLUMN_TOOLTIPS",
    "FOLD_SORT_TOOLTIP": "FOLD_SORT_TOOLTIP",
    "FOLD_FILTER_TOOLTIP": "FOLD_FILTER_TOOLTIP",
    "FOLD_FILTER_PLACEHOLDER": "FOLD_FILTER_PLACEHOLDER",
    "FOLD_OPEN_COUNT_TOOLTIP": "FOLD_OPEN_COUNT_TOOLTIP",
    "FOLD_PARKED_USD_TOOLTIP": "FOLD_PARKED_USD_TOOLTIP",
    "FOLD_OLDEST_AGE_TOOLTIP": "FOLD_OLDEST_AGE_TOOLTIP",
    "FOLD_UNITS_MARKED_TOOLTIP": "FOLD_UNITS_MARKED_TOOLTIP",
    "FOLD_WIRE_DISCARDED_TOOLTIP": "FOLD_WIRE_DISCARDED_TOOLTIP",
    "FOLD_MALFORMED_TOOLTIP": "FOLD_MALFORMED_TOOLTIP",
    "FOLD_CYCLE_CAP_TOOLTIP": "FOLD_CYCLE_CAP_TOOLTIP",
    "FOLD_OPENED_TOOLTIP": "FOLD_OPENED_TOOLTIP",
    "FOLD_CLOSED_TOOLTIP": "FOLD_CLOSED_TOOLTIP",
    "FOLD_CLOSE_RATIO_TOOLTIP": "FOLD_CLOSE_RATIO_TOOLTIP",
    "FOLD_DISCARDED_TOOLTIP": "FOLD_DISCARDED_TOOLTIP",
    "FOLD_COUNTERS_RESET_TOOLTIP": "FOLD_COUNTERS_RESET_TOOLTIP",
    "FOLD_OVER_ALLOTMENT_FG_HEX": "FOLD_OVER_ALLOTMENT_FG_HEX",
    "FOLD_RATIO_RED_FG_HEX": "FOLD_RATIO_RED_FG_HEX",
    "FOLD_RATIO_AMBER_FG_HEX": "FOLD_RATIO_AMBER_FG_HEX",
    "FOLD_RATIO_GREEN_FG_HEX": "FOLD_RATIO_GREEN_FG_HEX",
    "TRANCHE_ROW_BORDER_BY_BG": "TRANCHE_ROW_BORDER_BY_BG",
}


@pytest.mark.parametrize("name", sorted(SHARED_TOKENS))
def test_a_token_the_two_sides_share_carries_the_same_value(name):
    """A token moved on one side alone, so the two screens differ."""
    theirs = getattr(shipped, SHARED_TOKENS[name])
    ours = getattr(surface, name)
    assert canonical(theirs) == canonical(ours), f"{name}: {theirs!r} vs {ours!r}"


def test_the_surface_writes_its_own_values_and_reads_no_shipped_module():
    """The surface reads the module it replaces, so a change moves both."""
    imported = imported_names_in(SURFACE_SOURCE)
    assert imported == [
        "__future__.annotations",
        "math",
        "typing.Any",
        "typing.Optional",
    ], imported
    # Asked of the parsed tree; the docstring names the module this
    # surface replaces.
    tree = parsed(SURFACE_SOURCE)
    reached = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any(
            "fold_tokens" in one or "design_system" in one or "live_settings" in one
            for one in (
                [alias.name for alias in node.names]
                + [getattr(node, "module", "") or ""]
            )
        )
    ]
    assert reached == [], [node.lineno for node in reached]
    assert not hasattr(surface, "ds")
    assert not hasattr(surface, "shipped")
    assert not any(
        getattr(value, "__name__", "") == shipped.__name__
        for value in vars(surface).values()
    )


def test_the_shipped_side_still_reads_its_token_module():
    """The token comparison compares the surface with itself.

    The shipped side takes its colours from the design token module, and
    the surface writes them out. A run where both read one module would
    compare a value to itself.
    """
    imported = imported_names_in(SHIPPED_SOURCE)
    assert "..design_system" in imported or any(
        "design_system" in one for one in imported
    ), imported
    assert not any("design_system" in one for one in imported_names_in(SURFACE_SOURCE))


def test_the_shared_token_check_reports_a_value_that_moved():
    """The shared-token check passes whatever the surface holds."""
    assert canonical(surface.FOLD_TRANCHE_BG_HEX) != canonical(
        shipped.EXTRACTOR_TRANCHE_BG_HEX
    )
    shipped_constants = {
        target.id
        for node in parsed(SHIPPED_SOURCE).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id.isupper()
    }
    assert set(SHARED_TOKENS.values()) == shipped_constants, sorted(
        shipped_constants ^ set(SHARED_TOKENS.values())
    )
    assert len(SHARED_TOKENS) == len(shipped_constants) > 40
    for name in SHARED_TOKENS:
        assert hasattr(shipped, SHARED_TOKENS[name]), name
        assert hasattr(surface, name), name


# Nothing is edited that was not handed over


MUTATION_CASES = [
    (surface.STEP_ORDER, [TRANCHES, "Largest USD first"]),
    (surface.STEP_UNITS_ROW, [TRANCHES, 8.0]),
    (surface.STEP_CELLS, [EXTRACTOR_ROW, 90000.0]),
    (surface.STEP_SOURCE, [{"operator_initiated": True}]),
]


@pytest.mark.parametrize("step,args", MUTATION_CASES)
def test_neither_side_edits_the_values_it_is_handed(step, args):
    """A side changed the stored record it was only asked to read."""
    for side in (shipped_side(step), surface_side(step)):
        given = copy.deepcopy(args)
        before = canonical(given)
        call(side, given)
        assert canonical(given) == before, f"{step}: {side} edited its input"


def test_the_mutation_reader_reports_an_edit():
    """The mutation reader answers unchanged whatever happened."""
    given = [{"usd": 1.0}]
    before = canonical(given)
    given[0]["usd"] = 2.0
    assert canonical(given) != before


@pytest.mark.parametrize("step,args", MUTATION_CASES)
def test_a_refusing_run_edits_nothing_either(step, args):
    """A run that refused part way left the stored record changed."""
    given = copy.deepcopy(args)
    before = canonical(given)
    model = surface.FoldTokensModel()
    driven = model.run_steps([[step, *given], [surface.STEP_AGE, AGE_REFUSED_BY_TEXT]])
    assert driven["refused"]["refusal_type"] == shipped_age_refusal(
        AGE_REFUSED_BY_TEXT
    ), driven
    assert driven["ran"] == 1
    assert canonical(given) == before


# Order independence and process-wide state


def test_the_surface_keeps_no_state_between_two_requests():
    """One request read the steps another request drove."""
    first = surface.view_model({"steps": [[surface.STEP_ARBITER, "parent"]]})
    second = surface.view_model({"steps": [[surface.STEP_AGE, 61]]})
    third = surface.view_model({"steps": [[surface.STEP_ARBITER, "parent"]]})
    assert first["calls"] == [[surface.STEP_ARBITER, "Parent"]]
    assert second["calls"] == [[surface.STEP_AGE, "1m"]]
    assert third["calls"] == first["calls"]
    assert surface.view_model({})["calls"] == []


def test_a_request_that_refuses_leaves_the_next_request_clean():
    """A refusal in one request reached the next one."""
    refused = surface.view_model({"steps": [[surface.STEP_AGE, "x"]]})
    assert refused["refused"]["refusal_type"] == shipped_age_refusal(
        AGE_REFUSED_BY_TEXT
    )
    assert refused["ran"] == 0
    after = surface.view_model({"steps": [[surface.STEP_AGE, 61]]})
    assert after["refused"] is None
    assert after["ran"] == 1


def module_values(module) -> dict:
    """Every module-level value one side holds, in canonical form.

    Reads the values themselves, not the module list: a deferred import
    loading more modules is what a deferred import is for, and which run
    loads it first is a fact about the run order, not about the product.
    """
    return {
        name: canonical(value)
        for name, value in vars(module).items()
        if not name.startswith("__") and not callable(value)
    }


def test_the_environment_is_the_same_after_a_drive_and_after_a_refusal():
    """A drive changed process-wide state and left it changed."""
    before_env = dict(os.environ)
    before_shipped = module_values(shipped)
    before_surface = module_values(surface)
    for name in COMPARED:
        step, args = CASES[name]
        drive_both(step, args)
    surface.view_model({"steps": [[surface.STEP_AGE, AGE_REFUSED_BY_TEXT]]})
    assert dict(os.environ) == before_env
    assert module_values(shipped) == before_shipped
    assert module_values(surface) == before_surface


def test_the_module_value_reader_reports_a_changed_value():
    """The module reader answers unchanged whatever a drive did."""
    before = module_values(surface)
    assert before, "the reader found no values at all, so it cannot report"
    assert "FOLD_TRANCHE_BG_HEX" in before
    changed = dict(before)
    changed["FOLD_TRANCHE_BG_HEX"] = canonical("#000000")
    assert changed != before
    assert module_values(surface) == before


def test_the_environment_reader_reports_a_change():
    """The environment reader answers unchanged whatever happened."""
    before = dict(os.environ)
    os.environ["ACERVATOR_FOLD_TOKENS_PROBE"] = "1"
    try:
        assert dict(os.environ) != before
    finally:
        del os.environ["ACERVATOR_FOLD_TOKENS_PROBE"]
    assert dict(os.environ) == before


def test_the_shipped_module_holds_no_value_a_run_can_change():
    """The panel's token module keeps state one test can leave dirty."""
    tree = parsed(SHIPPED_SOURCE)
    assigned_in_functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            assigned_in_functions.extend(node.names)
    assert assigned_in_functions == [], assigned_in_functions
    assert [
        node
        for node in ast.walk(parsed(SURFACE_SOURCE))
        if isinstance(node, ast.Global)
    ] == []


# The bridge, with no Qt in the process


def bridge_answer(params):
    """One request answered through the real registry."""
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": 1, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_surface_is_registered_on_the_bridge():
    """The renderer cannot reach the Fold Tranches tokens."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model
    assert surface.METHOD == "fold_tokens.state"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"steps": [[surface.STEP_CELLS, EXTRACTOR_ROW, 90000.0]]})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["calls"][0][1][0] == "EXT"
    assert encoded["result"]["tokens"]["FOLD_TRANCHE_BG_HEX"] == "#123a63"


def test_a_step_that_produces_an_infinity_still_encodes():
    """A value the encoder cannot carry broke the whole frame."""
    answer = bridge_answer({"steps": [[surface.STEP_FINITE, 1e308]]})
    assert answer["ok"] is True
    assert json.loads(json.dumps(answer))["result"]["ran"] == 1
    assert surface.plain(INF) == repr(INF)
    assert surface.plain(NAN) == repr(NAN)
    assert surface.plain(1.5) == 1.5
    assert json.dumps(surface.plain([INF, NAN, 1.5]))


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'fold_tokens.state', 'params':"
    " {'steps': [['arbiter_label', 'parent'], ['format_tranche_age', 90061],"
    " ['compose_cycle_close_ratio', 160, 118, 42]]}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def run_python(script, env=None):
    """Run `script` in a fresh process and return the last line it printed.

    The script is handed to the interpreter on its standard input rather
    than as an argument, so nothing built at run time reaches the command
    line. Every probe in this file goes through here.
    """
    done = subprocess.run(
        [sys.executable, "-"],
        input=script.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
        env=env,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def run_probe(prelude, env=None):
    """Answer one bridge request in a fresh process."""
    return run_python(prelude + QT_PROBE, env=env)


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the Fold Tranches tokens pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["ran"] == 3
    assert result["calls"][0][1] == "Parent"
    assert result["calls"][1][1] == "1d 1h"
    assert result["calls"][2][1] == ["100.00%  (118/118)", "#00ff88"]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_importing_the_surface_touches_nothing_at_import_time(tmp_path):
    """Importing the surface read the clock or the filesystem."""
    watcher = (
        "import builtins, json, sys, time;"
        "opened = [];"
        "real_open = builtins.open;"
        "builtins.open = lambda *a, **k: (opened.append(a[0]), real_open(*a, **k))[1];"
        "clocked = [];"
        "real_time = time.time;"
        "time.time = lambda: (clocked.append(1), real_time())[1];"
        "import src.gui.main_tabs.fold_tokens_surface as s;"
        "builtins.open = real_open;"
        "time.time = real_time;"
        "print(json.dumps({'opened': [str(one) for one in opened],"
        " 'clocked': len(clocked), 'qt': 'PySide6' in sys.modules,"
        " 'method': s.METHOD}));"
    )
    seen = run_python(watcher)
    assert seen["opened"] == [], seen["opened"]
    assert seen["clocked"] == 0, seen["clocked"]
    assert seen["qt"] is False
    assert seen["method"] == surface.METHOD
    assert tmp_path.exists()


def test_the_import_watcher_reports_a_file_and_a_clock_read():
    """The import watcher reports clean whatever the module did."""
    watcher = (
        "import builtins, json, time;"
        "opened = [];"
        "real_open = builtins.open;"
        "builtins.open = lambda *a, **k: (opened.append(a[0]), real_open(*a, **k))[1];"
        "clocked = [];"
        "real_time = time.time;"
        "time.time = lambda: (clocked.append(1), real_time())[1];"
        "import src.gui.live_settings.fold_tokens as unused;"
        "open(__file__ if False else 'pyproject.toml').close();"
        "time.time();"
        "builtins.open = real_open;"
        "time.time = real_time;"
        "print(json.dumps({'opened': len(opened), 'clocked': len(clocked),"
        " 'named': unused.ARBITER_COLUMN_HEADER}));"
    )
    seen = run_python(watcher)
    assert seen["opened"] >= 1, "the file watcher saw nothing when a file was opened"
    assert seen["clocked"] >= 1, "the clock watcher saw nothing when the clock was read"
    assert seen["named"] == "Arbiter"


def test_a_run_against_a_throwaway_home_creates_no_file(tmp_path):
    """Driving the surface wrote into the operator's runtime tree."""
    home = tmp_path / "throwaway_home"
    home.mkdir()
    env = dict(os.environ)
    env["ACERVATOR_TEST_HOME"] = str(home)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    before = sorted(str(one.relative_to(home)) for one in home.rglob("*"))
    answered = run_probe("", env=env)
    assert answered["frame"]["ok"] is True
    after = sorted(str(one.relative_to(home)) for one in home.rglob("*"))
    assert after == before == [], after


def test_the_throwaway_home_reader_reports_a_file(tmp_path):
    """The empty-folder reader reports empty whatever was written."""
    home = tmp_path / "throwaway_home"
    home.mkdir()
    assert sorted(home.rglob("*")) == []
    (home / "written.txt").write_text("x", encoding="utf-8", newline="\n")
    assert [one.name for one in home.rglob("*")] == ["written.txt"]


def test_the_run_makes_no_network_call(tmp_path):
    """Driving the surface reached the network."""
    counter = tmp_path / "attempts.json"
    prelude = (
        "import json, socket, atexit;"
        "attempts = [];"
        "socket.socket.connect = lambda self, address: attempts.append(address);"
        "socket.socket.connect_ex = lambda self, address: attempts.append(address);"
        "socket.create_connection = lambda *a, **k: attempts.append(a);"
        "atexit.register(lambda: open(%r, 'w').write(json.dumps(len(attempts))));"
        % str(counter)
    )
    answered = run_probe(prelude)
    assert answered["frame"]["ok"] is True
    assert json.loads(counter.read_text(encoding="utf-8")) == 0


def test_the_connection_counter_reaches_the_child_process(tmp_path):
    """The connection counter reports zero from a process it never entered."""
    counter = tmp_path / "attempts.json"
    prelude = (
        "import json, socket, atexit;"
        "attempts = [];"
        "socket.socket.connect = lambda self, address: attempts.append(address);"
        "socket.create_connection = lambda *a, **k: attempts.append(a);"
        "socket.create_connection(('127.0.0.1', 9));"
        "atexit.register(lambda: open(%r, 'w').write(json.dumps(len(attempts))));"
        % str(counter)
    )
    answered = run_probe(prelude)
    assert answered["frame"]["ok"] is True
    assert counter.exists(), "the counter never reached the child process"
    assert json.loads(counter.read_text(encoding="utf-8")) == 1


# Pictures: the two sides paint one table


ROW_CASES = {
    "fold_rows": (
        [
            {"created_ts": 300.0, "usd": 10.0, "units": 1.5},
            {"created_ts": 100.0, "usd": 30.0, "units": 0.25},
        ],
        surface.FOLD_TRANCHE_BG_HEX,
        surface.FOLD_TRANCHE_FG_HEX,
    ),
    "extractor_rows": (
        [
            {"created_ts": 50.0, "usd": 5.0, "units": 9.75},
            {"created_ts": 20.0, "usd": 55.5, "units": 0.5},
        ],
        surface.EXTRACTOR_TRANCHE_BG_HEX,
        surface.EXTRACTOR_TRANCHE_FG_HEX,
    ),
}


def shipped_payload(case):
    """The rows and colours the SHIPPED module composes for one case."""
    tranches, fill, ink = ROW_CASES[case]
    fill = getattr(
        shipped,
        "FOLD_TRANCHE_BG_HEX" if case == "fold_rows" else "EXTRACTOR_TRANCHE_BG_HEX",
    )
    ink = getattr(
        shipped,
        "FOLD_TRANCHE_FG_HEX" if case == "fold_rows" else "EXTRACTOR_TRANCHE_FG_HEX",
    )
    ordered = shipped.fold_display_order(copy.deepcopy(tranches), "Largest USD first")
    rows = []
    for index, tranche in ordered:
        rows.append(
            [
                str(index),
                shipped._format_tranche_age(1000.0 - tranche["created_ts"]),
                f"{tranche['units']:.6f}",
                f"${tranche['usd']:,.4f}",
                shipped._fold_tranche_source_label(tranche),
            ]
        )
    marked = shipped.compose_units_marked_row(copy.deepcopy(tranches), 4.0)
    return sealed(
        {
            "rows": rows,
            "fill": fill,
            "ink": ink,
            "border": shipped.TRANCHE_ROW_BORDER_BY_BG[fill],
            "row_height": shipped.TRANCHE_ROW_HEIGHT_PX,
            "marked": list(marked),
            "headers": ["#", "Age", "Units", "USD parked", "Source"],
        }
    )


def surface_payload(case):
    """The rows and colours the SURFACE composes for one case."""
    tranches, fill, ink = ROW_CASES[case]
    ordered = surface.fold_display_order(copy.deepcopy(tranches), "Largest USD first")
    rows = []
    for index, tranche in ordered:
        rows.append(
            [
                str(index),
                surface.format_tranche_age(1000.0 - tranche["created_ts"]),
                surface.UNITS_CELL_FORMAT.format(units=tranche["units"]),
                surface.MARK_USD_FORMAT.format(mark_usd=tranche["usd"]),
                surface.fold_source_label(tranche),
            ]
        )
    marked = surface.compose_units_marked_row(copy.deepcopy(tranches), 4.0)
    return sealed(
        {
            "rows": rows,
            "fill": fill,
            "ink": ink,
            "border": surface.row_border_hex(fill),
            "row_height": surface.TRANCHE_ROW_HEIGHT_PX,
            "marked": list(marked),
            "headers": ["#", "Age", "Units", "USD parked", "Source"],
        }
    )


def table_painted_by(payload):
    """A real table painted from one sealed payload and nothing else."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout
    from PySide6.QtWidgets import QWidget

    payload = unaltered(payload)
    qt_app()
    host = hold(QWidget())
    box = QVBoxLayout(host)

    table = QTableWidget()
    table.setColumnCount(len(payload["headers"]))
    table.setRowCount(len(payload["rows"]))
    table.setHorizontalHeaderLabels(payload["headers"])
    for row_index, row in enumerate(payload["rows"]):
        table.setRowHeight(row_index, payload["row_height"])
        for column, text in enumerate(row):
            cell = QTableWidgetItem(text)
            cell.setBackground(QColor(payload["fill"]))
            cell.setForeground(QColor(payload["ink"]))
            table.setItem(row_index, column, cell)
    table.setStyleSheet(
        f"QTableWidget {{ border: {payload['row_height'] // 15}px solid "
        f"{payload['border']}; }}"
    )
    box.addWidget(table)

    marked = QLabel(payload["marked"][0])
    if payload["marked"][1]:
        marked.setStyleSheet(f"color: {payload['marked'][1]};")
    box.addWidget(marked)
    return host


def old_picture_table(case):
    """A table painted from the SHIPPED module's own values."""
    return table_painted_by(shipped_payload(case))


def new_picture_table(case):
    """A table painted from the SURFACE's values."""
    return table_painted_by(surface_payload(case))


def render(widget):
    """One render of `widget` at the size every picture check uses."""
    from tests.qt_pixel import render_widget

    return render_widget(widget, PIXEL_SIZE)


@pytest.mark.parametrize("case", sorted(ROW_CASES))
def test_the_two_sides_carry_one_skin(case):
    """The surface paints a different table than the panel it replaces."""
    qt_app()
    assert_same_skin(
        build_old_side=lambda: old_picture_table(case),
        build_new_side=lambda: new_picture_table(case),
        size=PIXEL_SIZE,
        control_rule=SKIN_CONTROL_RULE,
        note=case,
    )


@pytest.mark.parametrize("case", sorted(ROW_CASES))
def test_each_rendered_case_paints_enough_colours_to_report(case):
    """A render that paints one colour compares the same whatever it shows."""
    old = render(old_picture_table(case))
    new = render(new_picture_table(case))
    old_colours = assert_picture_can_report(old, note=f"old side, {case}")
    new_colours = assert_picture_can_report(new, note=f"new side, {case}")
    assert old_colours == new_colours, (case, old_colours, new_colours)
    assert colour_count(old) == old_colours


def test_two_different_cases_paint_different_pictures():
    """The picture comparison passes whatever the second side painted."""
    qt_app()
    assert_cases_paint_differently(
        old_side=render(old_picture_table("fold_rows")),
        new_side=render(new_picture_table("extractor_rows")),
        note="fold rows against extractor rows",
    )


def test_the_sealed_payload_refuses_a_value_changed_after_it_came_off():
    """A render of a changed payload measures the host, not the product."""
    payload = surface_payload("fold_rows")
    payload["fill"] = "#00ff00"
    with pytest.raises(AssertionError):
        table_painted_by(payload)


def test_an_unsealed_payload_is_refused():
    """A payload nobody produced reaches a render."""
    with pytest.raises(AssertionError):
        table_painted_by({"rows": [], "headers": [], "fill": "#000000"})


@skip_unless_no_fonts
def test_two_labels_of_one_length_measure_alike_with_no_fonts():
    """With no font database a box font advances one em per character."""
    qt_app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_a_narrow_label_is_narrower_than_a_wide_one_with_real_fonts():
    """With a font database the glyphs decide their own width."""
    qt_app()
    assert app_font_advance_px(NARROW_LABEL) < app_font_advance_px(WIDE_LABEL)


# The shipped defect this conversion reproduces rather than corrects


UNGUARDED_UNITS_SHAPES = [
    (True, "1.000000"),
    (False, "0.000000"),
    (NAN, "nan"),
    (INF, "inf"),
    (NEG_INF, "-inf"),
]


@pytest.mark.parametrize("stored,printed", UNGUARDED_UNITS_SHAPES)
def test_the_units_column_prints_a_shape_the_usd_column_refuses(stored, printed):
    """The Units column stopped printing a value the USD column refuses.

    ``mark_value_usd`` passes the admission rule and prints an em dash for
    every shape below. ``base_deployed`` is read with a plain float and
    prints the shape itself. Both sides do the same thing, so the
    conversion carries the behaviour rather than changing it.
    """
    row = dict(EXTRACTOR_ROW, base_deployed=stored, mark_value_usd=stored)
    theirs = shipped._compose_extractor_tranche_cells(row, 90000.0)
    ours = surface.extractor_tranche_cells(dict(row), 90000.0)
    assert theirs == ours
    assert ours[surface.EXTRACTOR_UNITS_COLUMN] == printed
    assert ours[surface.EXTRACTOR_USD_COLUMN] == surface.NO_MARK_TEXT


@pytest.mark.parametrize("field", ["base_deployed", "opened_at"])
@pytest.mark.parametrize("stored", ["x", HUGE_INT])
def test_an_unreadable_row_number_stops_the_whole_row_on_both_sides(field, stored):
    """One side raised where the other returned a row."""
    row = dict(EXTRACTOR_ROW, **{field: stored})
    theirs = call(shipped._compose_extractor_tranche_cells, [row, 90000.0])
    ours = call(surface.extractor_tranche_cells, [dict(row), 90000.0])
    assert theirs.refusal is not None, "the raise this pins has gone"
    assert theirs.refusal == ours.refusal
    assert theirs.digest == ours.digest


def test_the_guarded_usd_column_refuses_every_shape_the_units_column_prints():
    """The USD guard stopped refusing, so the pair above proves nothing."""
    for stored, _ in UNGUARDED_UNITS_SHAPES:
        assert surface.finite_number(stored) is None, stored
    assert surface.finite_number(33.5) == 33.5
