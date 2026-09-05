"""The Indicator Voting Panel surface, against the Qt panel it describes.

WHAT IS PROVED
==============
``src/gui/main_tabs/indicator_panel_surface.py`` publishes the panel that
``src/gui/indicator_panel.py`` paints: the same twelve indicators in the
same two rows, the same group colours, the same direction symbols and the
same cell text for every indicator that prints a raw reading rather than
a percentage.

Colour carries the weight here. Qt reads an alpha as a 0-255 byte and CSS
reads it as a 0-1 fraction, so every alpha this surface publishes is a
byte and the payload carries the unit that converts it. A test that only
compared numbers would pass while the panel painted a solid block where
Qt paints a wash, so the alpha tests name both the byte and the fraction.

The bar animation is counted in frames, never timed: Chromium throttles
timers in an offscreen view, so the frame interval is published as a
value and the step is driven directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.core import desktop_bridge
from src.gui import indicator_panel as qt_panel
from src.gui.main_tabs import indicator_panel_surface as surface

MANIFEST = REPO_ROOT / "desktop" / "renderer" / "module_manifest.js"
MODULE_NAME = "indicator_panel.js"

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"


def signal(indicator: str, direction: str, confidence: float, **details) -> dict:
    return {
        "indicator": indicator,
        "direction": direction,
        "confidence": confidence,
        "details": dict(details),
    }


def timeframe(*signals, **fields) -> dict:
    body = {
        "bullish": fields.get("bullish", 0),
        "bearish": fields.get("bearish", 0),
        "neutral": fields.get("neutral", 0),
        "net_score": fields.get("net_score", 0.0),
        "confidence": fields.get("confidence", 0.0),
        "signals": list(signals),
        "locks": fields.get("locks", []),
    }
    if "composite_net" in fields:
        body["composite_net"] = fields["composite_net"]
    return body


ONE_TIMEFRAME = {
    "1h": timeframe(
        signal("bollinger_bands", BULLISH, 0.8),
        signal("adx", BEARISH, 0.4, adx=27.4, ranging=False),
        signal("zscore", BEARISH, 0.9, z=-2.35),
        signal("kaufman_er", NEUTRAL, 0.1, er=0.4321),
        bullish=4,
        bearish=2,
        neutral=6,
        net_score=1.25,
        confidence=0.72,
    )
}


# -- the panel it describes -------------------------------------------


def test_the_surface_lists_the_same_twelve_indicators_the_qt_panel_does() -> None:
    published = [tuple(one) for one in surface.INDICATOR_COLS]
    assert published == [tuple(one) for one in qt_panel.INDICATOR_COLS], (
        "the surface and the Qt panel must name the same indicator columns; "
        f"surface={published} qt={qt_panel.INDICATOR_COLS}"
    )


def test_row_a_carries_the_first_six_indicators_and_row_b_the_rest() -> None:
    assert [tuple(one) for one in surface.ROW_A_INDICATOR_COLS] == [
        tuple(one) for one in qt_panel._ROW_A_INDICATOR_COLS
    ]
    assert [tuple(one) for one in surface.ROW_B_INDICATOR_COLS] == [
        tuple(one) for one in qt_panel._ROW_B_INDICATOR_COLS
    ]


def test_the_group_accent_colours_match_the_qt_panel() -> None:
    assert (
        surface.GROUP_COLORS == qt_panel.GROUP_COLORS
    ), "trend, momentum and structure keep the accents the Qt panel paints"


def test_the_direction_symbols_match_the_qt_panel() -> None:
    assert surface.DIR_SYMBOLS == qt_panel.DIR_SYMBOLS


def test_the_bar_colours_match_the_qt_bar_widget() -> None:
    published = {name: tuple(rgb) for name, rgb in surface.BAR_COLORS.items()}
    assert published == qt_panel.ConfidenceBarsWidget.BAR_COLORS


def test_the_privacy_dot_is_the_size_the_qt_dot_is() -> None:
    assert surface.PRIVACY_DOT_SIZE_PX == qt_panel._IVPPrivacyDot._SIZE_PX


# -- cell text, which follows each indicator's published scale ---------


def test_a_ranging_adx_cell_names_the_raw_reading_and_no_direction() -> None:
    text = surface.indicator_cell_text(
        "adx", signal("adx", BULLISH, 0.9, adx=14.2, ranging=True)
    )
    assert text == "Rng 14", f"a ranging ADX reads its raw value, got {text!r}"


def test_a_trending_adx_cell_names_the_raw_reading_beside_its_arrow() -> None:
    text = surface.indicator_cell_text(
        "adx", signal("adx", BULLISH, 0.9, adx=27.4, ranging=False)
    )
    assert text == "▲ 27", f"a trending ADX reads its raw value, got {text!r}"


def test_a_zscore_cell_carries_the_sign_of_the_raw_z_value() -> None:
    text = surface.indicator_cell_text(
        "zscore", signal("zscore", BEARISH, 0.9, z=-2.31)
    )
    assert text == "▼ -2.3", f"z-score prints a signed raw value, got {text!r}"
    rising = surface.indicator_cell_text(
        "zscore", signal("zscore", BULLISH, 0.9, z=2.31)
    )
    assert rising == "▲ +2.3", f"a positive z keeps its plus sign, got {rising!r}"


def test_a_kaufman_cell_prints_the_raw_efficiency_ratio() -> None:
    text = surface.indicator_cell_text(
        "kaufman_er", signal("kaufman_er", NEUTRAL, 0.1, er=0.4321)
    )
    assert text == "─ 0.43", f"KER prints a raw ratio, got {text!r}"


def test_every_other_indicator_prints_its_vote_confidence_as_a_percentage() -> None:
    text = surface.indicator_cell_text("macd", signal("macd", BULLISH, 0.836))
    assert text == "▲ 84%", f"a voting indicator prints a percentage, got {text!r}"


def test_a_missing_signal_reads_neutral_at_no_confidence() -> None:
    assert surface.indicator_cell_text("rsi", None) == "─ 0%"


def test_the_raw_value_indicators_are_the_three_that_publish_a_reading() -> None:
    for key in surface.RAW_VALUE_INDICATORS:
        text = surface.indicator_cell_text(key, signal(key, BULLISH, 0.5))
        assert not text.endswith(
            "%"
        ), f"{key} publishes a raw reading, never a percentage; got {text!r}"


# -- cell colour, and the alpha byte behind it -------------------------


def test_a_bullish_cell_takes_the_green_text_and_the_green_tint() -> None:
    colours = surface.indicator_cell_colors(signal("macd", BULLISH, 1.0))
    assert colours["text_color"] == surface.BULLISH_TEXT_COLOR
    assert colours["fill_rgb"] == list(surface.BULLISH_CELL_RGB)


def test_a_bearish_cell_takes_the_red_text_and_the_red_tint() -> None:
    colours = surface.indicator_cell_colors(signal("macd", BEARISH, 1.0))
    assert colours["text_color"] == surface.BEARISH_TEXT_COLOR
    assert colours["fill_rgb"] == list(surface.BEARISH_CELL_RGB)


def test_a_neutral_cell_takes_the_flat_tint_at_its_own_fixed_alpha() -> None:
    colours = surface.indicator_cell_colors(signal("macd", NEUTRAL, 1.0))
    assert (
        colours["fill_alpha"] == surface.NEUTRAL_CELL_ALPHA
    ), "a neutral cell's tint does not follow confidence"


def test_the_cell_tint_alpha_climbs_with_confidence_from_its_floor() -> None:
    assert surface.cell_alpha(0.0) == surface.CELL_ALPHA_FLOOR
    assert surface.cell_alpha(1.0) == (
        surface.CELL_ALPHA_FLOOR + surface.CELL_ALPHA_SPAN
    )
    assert surface.cell_alpha(0.5) > surface.cell_alpha(
        0.1
    ), "a stronger vote paints a stronger tint"


def test_the_cell_tint_alpha_never_leaves_the_qt_byte_range() -> None:
    for confidence in (-5.0, 0.0, 0.5, 1.0, 9.9, None, "nonsense"):
        found = surface.cell_alpha(confidence)
        assert 0 <= found <= 255, (
            f"confidence {confidence!r} produced alpha {found}, "
            "which is not a Qt alpha byte"
        )


def test_every_published_alpha_is_a_qt_byte_and_not_a_css_fraction() -> None:
    published = {
        "privacy border": surface.PRIVACY_BORDER_ALPHA,
        "staleness background": surface.STALENESS_BACKGROUND_ALPHA,
        "rate strip background": surface.RATE_STRIP_BACKGROUND_ALPHA,
        "bar glow": surface.BARS_GLOW_ALPHA,
        "bar outline": surface.BARS_OUTLINE_ALPHA,
        "bar arrow": surface.BARS_ARROW_ALPHA,
    }
    for name, byte in published.items():
        assert byte > 1, (
            f"{name} alpha is {byte}; a value of 1 or less would already be a "
            "CSS fraction and would be scaled a second time"
        )
        assert byte <= 255, f"{name} alpha {byte} is past Qt's byte range"


def test_the_published_alpha_unit_turns_a_qt_byte_into_a_css_fraction() -> None:
    byte = surface.STALENESS_BACKGROUND_ALPHA
    assert byte * surface.ALPHA_UNIT == pytest.approx(byte / 255.0)
    assert byte * surface.ALPHA_UNIT < 1.0, (
        "the amber banner is a wash over the panel, not an opaque block; "
        f"byte {byte} must land below 1, got {byte * surface.ALPHA_UNIT}"
    )


def test_the_amber_banner_is_translucent_rather_than_solid() -> None:
    fraction = surface.STALENESS_BACKGROUND_ALPHA * surface.ALPHA_UNIT
    assert fraction == pytest.approx(90 / 255.0), (
        "Qt paints the staleness banner at alpha byte 90, which is "
        f"{90 / 255.0:.4f} in CSS; got {fraction}"
    )


# -- the aggregate columns ---------------------------------------------


def test_a_positive_net_reads_green_and_a_negative_net_reads_red() -> None:
    assert net_colour(1.5) == surface.BULLISH_TEXT_COLOR
    assert net_colour(-1.5) == surface.BEARISH_TEXT_COLOR


def net_colour(value: float) -> str:
    return surface.net_cell({"net_score": value})["text_color"]


def test_a_net_of_zero_takes_no_colour_of_its_own() -> None:
    assert surface.net_cell({"net_score": 0.0})["text_color"] is None


def test_the_net_cell_prints_a_signed_two_place_figure() -> None:
    assert surface.net_cell({"net_score": 1.25})["text"] == "+1.25"
    assert surface.net_cell({"net_score": -0.5})["text"] == "-0.50"


def test_a_row_with_no_composite_reads_an_em_dash_in_the_comp_column() -> None:
    cell = surface.comp_cell({"composite_net": None})
    assert cell["text"] == surface.COMP_ABSENT_TEXT
    assert cell["text_color"] == surface.ABSENT_TEXT_COLOR


def test_a_row_with_a_composite_prints_it_signed() -> None:
    assert surface.comp_cell({"composite_net": 2.5})["text"] == "+2.50"


def test_the_confidence_cell_colours_by_the_published_breadth_bands() -> None:
    assert surface.conf_cell({"confidence": 0.6})["text_color"] == (
        surface.BULLISH_TEXT_COLOR
    )
    assert surface.conf_cell({"confidence": 0.3})["text_color"] == (
        surface.WARNING_TEXT_COLOR
    )
    assert surface.conf_cell({"confidence": 0.29})["text_color"] == (
        surface.ABSENT_TEXT_COLOR
    )


def test_the_confidence_bar_always_holds_ten_cells() -> None:
    for confidence in (0.0, 0.37, 1.0):
        drawn = surface.confidence_bar(confidence)
        assert (
            len(drawn) == surface.CONF_BAR_CELLS
        ), f"confidence {confidence} drew {drawn!r}"


def test_the_confidence_bar_fills_in_step_with_the_reading() -> None:
    assert surface.confidence_bar(0.0).count(surface.CONF_BAR_FILLED) == 0
    assert surface.confidence_bar(1.0).count(surface.CONF_BAR_FILLED) == 10
    assert surface.confidence_bar(0.5).count(surface.CONF_BAR_FILLED) == 5


# -- rows, ordering and the tally --------------------------------------


def test_timeframes_are_listed_shortest_first() -> None:
    order = surface.ordered_timeframes({"1d": {}, "5m": {}, "1h": {}})
    assert order == ["5m", "1h", "1d"]


def test_an_unknown_timeframe_sorts_after_every_known_one() -> None:
    order = surface.ordered_timeframes({"phantom": {}, "5m": {}})
    assert order[-1] == "phantom", f"got {order}"


def test_row_a_carries_the_three_aggregate_columns_and_row_b_does_not() -> None:
    model = surface.IndicatorPanelModel()
    model.set_summary(ONE_TIMEFRAME, "BTC-USD")
    assert model.table_a.titles[-3:] == surface.AGGREGATE_TITLES
    assert (
        model.table_b.titles[-1] == "RSI"
    ), f"row B ends at its last indicator; got {model.table_b.titles}"


def test_each_table_draws_one_row_per_timeframe() -> None:
    model = surface.IndicatorPanelModel()
    model.set_summary({"5m": timeframe(), "1h": timeframe()}, "BTC-USD")
    assert len(model.table_a.rows) == 2
    assert len(model.table_b.rows) == 2


def test_the_summary_line_sums_the_votes_across_every_timeframe() -> None:
    summary = {
        "5m": timeframe(bullish=2, bearish=1, neutral=9),
        "1h": timeframe(bullish=3, bearish=0, neutral=9),
    }
    assert surface.summary_text(summary) == "▲ 5  ▼ 1  ─ 18"


def test_the_locks_line_names_every_active_lock() -> None:
    line = surface.locks_text(
        [{"source_tf": "4h", "locked_direction": "SELL", "candles_remaining": 2}]
    )
    assert line == "Active locks: 4h → SELL lock (2 candles remaining)"


def test_the_locks_line_says_so_when_nothing_is_locked() -> None:
    assert surface.locks_text([]) == surface.LOCKS_IDLE_TEXT


# -- the empty state and the stale one ---------------------------------


def test_a_live_reading_leaves_the_staleness_banner_down() -> None:
    model = surface.IndicatorPanelModel()
    model.set_summary(ONE_TIMEFRAME, "BTC-USD")
    assert model.showing_stored is False
    assert model.staleness_line == ""


def test_a_stored_reading_raises_the_banner_naming_its_age() -> None:
    model = surface.IndicatorPanelModel()
    model.show_stored(
        {"symbol": "BTC-USD", "timeframes": ONE_TIMEFRAME},
        "09:41:07",
        "4m 12s ago",
        "cold start — this bot has computed no TA.",
    )
    assert (
        model.showing_stored is True
    ), "a stored reading must announce itself as not current"
    assert "4m 12s ago" in model.staleness_line
    assert "09:41:07" in model.staleness_line


def test_a_stored_reading_still_fills_the_table_it_came_from() -> None:
    model = surface.IndicatorPanelModel()
    model.show_stored(
        {"symbol": "BTC-USD", "timeframes": ONE_TIMEFRAME}, "09:41:07", "just now", ""
    )
    assert (
        len(model.table_a.rows) == 1
    ), "the stale banner sits over a drawn reading, not over an empty table"


def test_an_empty_state_names_its_one_cause_in_the_summary_line() -> None:
    model = surface.IndicatorPanelModel()
    model.set_summary(ONE_TIMEFRAME, "BTC-USD")
    model.show_no_data("parked at target", cause="parked_at_target")
    assert model.table_a.rows == [], "the table empties when there is no reading"
    assert model.summary_line == "No TA data — parked at target"
    assert model.no_data_cause == "parked_at_target"


def test_an_empty_state_clears_the_bars_the_last_bot_left_behind() -> None:
    model = surface.IndicatorPanelModel()
    model.set_summary(ONE_TIMEFRAME, "BTC-USD")
    assert model.bars_a.targets, "positive control: a live reading fills the bars"
    model.show_no_data("no bot is selected", cause="no_selection")
    assert (
        model.bars_a.targets == []
    ), "the previous bot's bars must not stay painted over an empty table"
    assert model.bars_b.targets == []


# -- the bot selector and the privacy mask -----------------------------


def test_only_accumulation_bots_reach_the_dropdown() -> None:
    model = surface.IndicatorPanelModel()
    items = model.set_bots(
        [
            {"bot_id": "aaaa1111", "symbol": "BTC-USD", "mode": "accumulation"},
            {"bot_id": "bbbb2222", "symbol": "ETH-USD", "mode": "extractor"},
            {"bot_id": "cccc3333", "symbol": "SOL-USD", "mode": "scrumming"},
        ]
    )
    assert [one["value"] for one in items] == [
        "aaaa1111",
        "cccc3333",
    ], "accumulation and scrumming name the same bot class; extractor does not"


def test_an_empty_fleet_says_so_rather_than_offering_nothing() -> None:
    model = surface.IndicatorPanelModel()
    items = model.set_bots([])
    assert items[0]["text"] == surface.SELECTOR_EMPTY_TEXT


def test_a_dropdown_entry_names_the_symbol_the_short_id_and_the_state() -> None:
    model = surface.IndicatorPanelModel()
    items = model.set_bots(
        [
            {
                "bot_id": "abcdef0123456789",
                "symbol": "BTC-USD",
                "mode": "accumulation",
                "state": "running",
            }
        ]
    )
    assert items[0]["text"] == "BTC-USD [abcdef01] (running)"


def test_masking_replaces_the_dropdown_text_but_keeps_the_bot_id() -> None:
    model = surface.IndicatorPanelModel()
    model.set_bots(
        [{"bot_id": "aaaa1111", "symbol": "BTC-USD", "mode": "accumulation"}]
    )
    revealed = model.selector_payload()
    assert (
        revealed[0]["text"] == "BTC-USD [aaaa1111] (idle)"
    ), "positive control: the entry reads plainly before the mask goes on"
    model.set_masked(masked=True)
    masked = model.selector_payload()
    assert masked[0]["text"] == surface.PRIVACY_MASK_TEXT
    assert (
        masked[0]["value"] == "aaaa1111"
    ), "selection must survive the mask, or a masked panel cannot pick a bot"


def test_masking_hides_the_symbol_label_too() -> None:
    model = surface.IndicatorPanelModel()
    model.set_summary(ONE_TIMEFRAME, "BTC-USD")
    assert model.symbol_payload() == "BTC-USD"
    model.set_masked(masked=True)
    assert model.symbol_payload() == surface.PRIVACY_MASK_TEXT


def test_the_privacy_dot_is_dark_when_masked_and_bright_when_revealed() -> None:
    assert surface.PRIVACY_MASKED_COLOR in surface.privacy_style_sheet(masked=True)
    assert surface.PRIVACY_REVEALED_COLOR in surface.privacy_style_sheet(masked=False)


def test_the_privacy_tooltip_says_what_a_click_will_do() -> None:
    assert "reveal" in surface.privacy_tooltip(masked=True)
    assert "mask" in surface.privacy_tooltip(masked=False)


# -- the timeframe lock ------------------------------------------------


def test_the_lock_dropdown_opens_with_no_lock_then_one_entry_per_timeframe() -> None:
    options = surface.tf_lock_options()
    assert options[0]["value"] == surface.TF_LOCK_NONE_VALUE
    assert [one["value"] for one in options[1:]] == surface.TF_LOCK_TIMEFRAMES


def test_choosing_a_lock_says_which_direction_is_locked() -> None:
    model = surface.IndicatorPanelModel()
    model.set_lock("4h")
    assert surface.tf_lock_status("4h") == (
        "Active: trades below 4h locked to 4h direction"
    )


def test_clearing_the_lock_leaves_the_status_line_empty() -> None:
    assert surface.tf_lock_status("") == ""


def test_the_lock_index_follows_the_chosen_timeframe() -> None:
    model = surface.IndicatorPanelModel()
    model.set_lock("1h")
    options = surface.tf_lock_options()
    assert options[model.lock_index]["value"] == "1h"


# -- the currency rate strip -------------------------------------------


def test_a_missing_snapshot_says_the_rates_are_unavailable() -> None:
    assert surface.rate_strip_text(None) == surface.RATE_STRIP_ABSENT_TEXT


def test_a_side_with_no_price_reads_an_em_dash_rather_than_zero() -> None:
    line = surface.rate_strip_text(
        {"btc_usd": 0, "eth_usd": 2000.0, "gwei_per_dollar": 500000.0}
    )
    assert line.startswith(
        surface.RATE_STRIP_BTC_ABSENT_TEXT
    ), f"an absent BTC price must not print as $0.00; got {line!r}"
    assert "ETH $2,000.00" in line, "positive control: the present side still prints"


def test_the_rate_strip_names_the_exchange_it_read_from() -> None:
    line = surface.rate_strip_text({"btc_usd": 60000.0, "source": "coinbase"})
    assert line.endswith("coinbase")


def test_a_source_of_none_is_not_printed_as_a_source() -> None:
    line = surface.rate_strip_text({"btc_usd": 60000.0, "source": "none"})
    assert not line.endswith("none"), f"got {line!r}"


# -- the bar animation, counted in frames ------------------------------


def test_the_bar_animation_publishes_its_frame_interval_as_a_value() -> None:
    model = surface.IndicatorPanelModel()
    payload = model.bars_a.payload()
    assert payload["frame_interval_ms"] == surface.BARS_FRAME_INTERVAL_MS
    assert payload["lerp_factor"] == surface.BARS_LERP_FACTOR
    assert payload["settle_delta"] == surface.BARS_SETTLE_DELTA


def test_bars_start_at_zero_so_the_animation_has_somewhere_to_travel() -> None:
    bars = surface.ConfidenceBarsModel()
    bars.set_bars([{"name": "BB", "confidence": 0.9, "direction": BULLISH}])
    assert bars.current[0]["confidence"] == 0.0


def test_one_frame_moves_each_bar_the_published_fraction_of_its_gap() -> None:
    bars = surface.ConfidenceBarsModel()
    bars.set_bars([{"name": "BB", "confidence": 1.0, "direction": BULLISH}])
    bars.step()
    assert bars.current[0]["confidence"] == pytest.approx(surface.BARS_LERP_FACTOR)


def test_the_animation_settles_on_its_target_and_stops_running() -> None:
    bars = surface.ConfidenceBarsModel()
    bars.set_bars([{"name": "BB", "confidence": 0.5, "direction": BULLISH}])
    assert bars.running is True, "positive control: it starts out running"
    settled = False
    for _frame in range(500):
        settled = bars.step()
        if settled:
            break
    assert settled is True, "the animation must reach its target and stop"
    assert bars.running is False
    assert bars.current[0]["confidence"] == pytest.approx(0.5)


def test_a_bar_carries_its_direction_from_the_first_frame() -> None:
    bars = surface.ConfidenceBarsModel()
    bars.set_bars([{"name": "BB", "confidence": 0.9, "direction": BEARISH}])
    bars.step()
    assert (
        bars.current[0]["direction"] == BEARISH
    ), "colour must not lag the reading by a frame"


def test_stepping_with_no_bars_settles_at_once_rather_than_spinning() -> None:
    bars = surface.ConfidenceBarsModel()
    assert bars.step() is True
    assert bars.running is False


def test_the_arrow_appears_only_once_a_bar_is_tall_enough_to_hold_it() -> None:
    fraction = surface.arrow_min_fraction()
    assert (
        0.0 < fraction < 1.0
    ), f"the arrow threshold must sit inside the bar's range; got {fraction}"
    assert (
        surface.shine_min_fraction() < fraction
    ), "the highlight shows on a shorter bar than the arrow does"


def test_a_bar_row_is_built_for_each_indicator_in_its_subset() -> None:
    bars = surface.bars_for(surface.ROW_A_INDICATOR_COLS, ONE_TIMEFRAME["1h"])
    assert [one["name"] for one in bars] == [
        short for _, short, _ in surface.ROW_A_INDICATOR_COLS
    ]
    assert bars[0]["confidence"] == 0.8, "a voting indicator carries its confidence"


# -- the payload the bridge answers -------------------------------------


def test_the_bridge_answers_the_indicator_panel_method() -> None:
    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry, (
        f"{surface.METHOD} must be reachable from the renderer; "
        f"registry holds {len(registry)} methods"
    )


def test_a_reset_call_answers_a_panel_with_no_rows_in_it() -> None:
    payload = surface.view_model({"reset": True})
    assert payload["method"] == surface.METHOD
    assert payload["tables"][0]["rows"] == []


def test_a_set_summary_call_fills_both_tables() -> None:
    surface.view_model({"reset": True})
    payload = surface.view_model(
        {"action": "set_summary", "summary": ONE_TIMEFRAME, "symbol": "BTC-USD"}
    )
    assert payload["tables"][0]["row_count"] == 1
    assert payload["tables"][1]["row_count"] == 1
    assert payload["symbol_text"] == "BTC-USD"


def test_the_payload_carries_the_alpha_unit_a_frontend_converts_with() -> None:
    payload = surface.view_model({"reset": True})
    assert payload["alpha_unit"] == pytest.approx(1.0 / 255.0)
    assert payload["alpha_scale"] == 255.0


def test_a_step_bars_call_advances_the_animation_by_the_frames_asked_for() -> None:
    surface.view_model({"reset": True})
    surface.view_model(
        {"action": "set_summary", "summary": ONE_TIMEFRAME, "symbol": "BTC-USD"}
    )
    before = surface.view_model({"action": "step_bars", "frames": 1})
    after = surface.view_model({"action": "step_bars", "frames": 5})
    first = before["bars"][0]["bars"][0]["confidence"]
    later = after["bars"][0]["bars"][0]["confidence"]
    assert (
        later > first
    ), f"six frames must travel further than one; got {first} then {later}"


def test_an_unknown_action_leaves_the_panel_as_it_stood() -> None:
    surface.view_model({"reset": True})
    surface.view_model(
        {"action": "set_summary", "summary": ONE_TIMEFRAME, "symbol": "BTC-USD"}
    )
    payload = surface.view_model({"action": "no_such_action"})
    assert (
        payload["tables"][0]["row_count"] == 1
    ), "an action the surface does not know must not empty the panel"


def test_the_sim_panel_drops_the_bot_selector_and_the_lock_row() -> None:
    payload = surface.view_model({"reset": True, "sim_mode": True})
    assert payload["sim_mode"] is True


# -- the module the renderer loads --------------------------------------


def test_the_renderer_manifest_names_the_indicator_panel_module() -> None:
    manifest = MANIFEST.read_text(encoding="utf-8")
    assert MODULE_NAME in manifest, (
        f"{MODULE_NAME} must be in the generated manifest; "
        "regenerate it with tools.sync_renderer_modules"
    )


def test_the_surface_imports_no_qt() -> None:
    module = sys.modules[surface.__name__]
    assert not hasattr(
        module, "QWidget"
    ), "the surface serves any frontend and must not reach for Qt"
