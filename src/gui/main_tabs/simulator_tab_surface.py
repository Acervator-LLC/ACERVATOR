"""simulator_tab_surface.py -- the Sim tab as data, read from RA-StoneTablets.

``build_view_model`` reads one tablet through ``TabletSource`` and answers the
Trading-tab clone: the Privacy Mode row, the bot list under
``bot_status_table_surface.COLUMN_LABELS``, the panel
``indicator_panel_surface`` describes, and the second layer holding the VWAP
window over the tablet playback window. ``reserved_rows`` names what the crypto
news ticker and data-pool rows carry in each of ``MODES``, and ``run_validation``,
``run_back_test`` and ``run_battery`` fill the pane each mode draws.
``tablet_choices``, ``default_tablet_key`` and ``replay_feed`` are the forked
tab's replay layer as data: the chooser's items, the item the selected bot
names, and the two windows' payloads over one tablet, the playback carrying
``mark_shapes`` for the ``shown_bot``'s fills and ``replay_figures`` beside it.
``src.core.desktop_bridge`` registers ``view_model`` under ``METHOD``, and
nothing here imports Qt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from ...simulator import back_test, portfolio_battery, validation
from ...simulator.fleet_source import (
    MODE_BACK_TEST,
    MODE_PORTFOLIO_BATTERY,
    MODE_VALIDATION,
    MODES,
    aggregate_stats,
)
from ...simulator.portfolios import PORTFOLIOS
from ...simulator.tablet_source import TabletSource, tablet_key
from ...trading.scrumming.sizing import opposing_trade_distances
from ...trading.stone_tablets.ra_paths import RA_STONE_TABLETS_DIR
from ...trading.stone_tablets.registry import NATIVE_TIMEFRAME
from ...trading.stone_tablets.storage import STONE_TABLETS_DIR
from .. import design_system as ds
from ..theme_engine import NIGREDO_FRACTION, toward_black
from . import indicator_panel_surface as ivp
from .bot_status_table_surface import COLUMN_LABELS, FIXED_WIDTHS
from .native_chart_surface import (
    MARK_GLYPHS,
    MARK_HEIGHT_FRACTION,
    MARK_OUTLINE_PX,
    MARK_WIDTH_RATIO,
)

logger = logging.getLogger("acervator.gui")

METHOD = "simulator_tab.state"

HEADING = "Sim"
ISSUE = 117
BUILT = True

#: The Stone Tablets Validation and Back Test read: the operator's own traded
#: assets.
TABLET_ROOT = STONE_TABLETS_DIR

#: The RA-StoneTablets Portfolio Battery reads: the 35 portfolios' own history.
BATTERY_TABLET_ROOT = RA_STONE_TABLETS_DIR

#: The candle window live reads. ``ScrummingBot`` asks ``get_ohlcv`` for 100,
#: and the Simulator reads the same count off the tablet.
WINDOW_CANDLES = 100

#: Below this the voting engine has too few candles for its own formulae.
MIN_CANDLES = 30

PRIVACY_ON_TEXT = "Privacy Mode: ON"
PRIVACY_OFF_TEXT = "Privacy Mode: OFF"
PRIVACY_BUTTON_TEXT = PRIVACY_OFF_TEXT

IMPORT_LIVE_FLEET_ACTION = "import_live_fleet"
GENERATE_FROM_YTD_ACTION = "generate_from_ytd"
CREATE_NEW_BOTS_ACTION = "create_new_bots"
RUN_PORTFOLIO_ACTION = "run_portfolio"
RUN_EVERY_PORTFOLIO_ACTION = "run_every_portfolio"
IMPORT_LIVE_FLEET_TEXT = "Import Live Fleet"
GENERATE_FROM_YTD_TEXT = "Generate From YTD"
CREATE_NEW_BOTS_TEXT = "Create New Bots"
RUN_PORTFOLIO_TEXT = "Run Portfolio"
RUN_EVERY_PORTFOLIO_TEXT = "Run Every Portfolio"

#: The corner's first button in every mode: it empties the held fleet.
CLEAR_FLEET_ACTION = "clear_fleet"
CLEAR_FLEET_TEXT = "Clear Fleet"

#: The corner's last button while a fleet is held: it starts the run mode's run.
START_RUN_ACTION = "start_run"
START_RUN_TEXT = "Start Run"

CHOOSE_PORTFOLIO_ACTION = "choose_portfolio"
CHOOSE_SPAN_ACTION = "choose_span"

NEWS_TICKER_ROW = "news_ticker_row"
DATA_POOL_ROW = "data_pool_row"

#: The three run modes and their tuple are ``fleet_source``'s, one fleet each.
MODE_LABEL_TEXT = "Mode:"
MODE_TEXT = {
    MODE_VALIDATION: "Validation",
    MODE_BACK_TEST: "Back Test",
    MODE_PORTFOLIO_BATTERY: "Portfolio Battery",
}

#: How each mode's run funds its folds, in ``back_test``'s two fundings.
MODE_FUNDING = {
    MODE_VALIDATION: back_test.FUNDED_BY_TARGETS,
    MODE_BACK_TEST: back_test.FUNDED_BY_PROCEEDS,
    MODE_PORTFOLIO_BATTERY: back_test.FUNDED_BY_TARGETS,
}


def funding_for(mode: Any) -> str:
    """The ``back_test`` funding of ``mode``, Back Test's for a name outside
    ``MODES``."""
    return MODE_FUNDING.get(mode, back_test.FUNDED_BY_PROCEEDS)


def fleet_aggregate(fleet_source: Any, mode: Any) -> dict:
    """The header strip's figures for the Sim tab in ``mode``: ``aggregate_stats``
    over the held bots, with the wallet reading ``run_budget_usd`` while the
    mode's funding is ``FUNDED_BY_TARGETS``."""
    bots = fleet_source.bots()
    budget = None
    if funding_for(mode) == back_test.FUNDED_BY_TARGETS:
        budget = back_test.run_budget_usd(bots)
    return aggregate_stats(bots, budget_usd=budget)


def button_name(action: str) -> str:
    """The accessible name both hosts give the button that sends ``action``."""
    return "sim-" + str(action).replace("_", "-")


#: The rows the two strips held on the Trading tab, now the two fleet buttons.
RESERVED_ROWS: tuple[dict[str, Any], ...] = (
    {
        "name": NEWS_TICKER_ROW,
        "height_px": 24,
        "action": IMPORT_LIVE_FLEET_ACTION,
        "text": IMPORT_LIVE_FLEET_TEXT,
        "button_name": button_name(IMPORT_LIVE_FLEET_ACTION),
    },
    {
        "name": DATA_POOL_ROW,
        "height_px": 18,
        "action": GENERATE_FROM_YTD_ACTION,
        "text": GENERATE_FROM_YTD_TEXT,
        "button_name": button_name(GENERATE_FROM_YTD_ACTION),
    },
)

#: The same two rows in Back Test, where the second way in makes new bots.
BACK_TEST_ROWS: tuple[dict[str, Any], ...] = (
    {
        "name": NEWS_TICKER_ROW,
        "height_px": 24,
        "action": IMPORT_LIVE_FLEET_ACTION,
        "text": IMPORT_LIVE_FLEET_TEXT,
        "button_name": button_name(IMPORT_LIVE_FLEET_ACTION),
    },
    {
        "name": DATA_POOL_ROW,
        "height_px": 18,
        "action": CREATE_NEW_BOTS_ACTION,
        "text": CREATE_NEW_BOTS_TEXT,
        "button_name": button_name(CREATE_NEW_BOTS_ACTION),
    },
)

#: The same two rows in Portfolio Battery, where the ways in are one portfolio
#: and all of them.
BATTERY_ROWS: tuple[dict[str, Any], ...] = (
    {
        "name": NEWS_TICKER_ROW,
        "height_px": 24,
        "action": RUN_PORTFOLIO_ACTION,
        "text": RUN_PORTFOLIO_TEXT,
        "button_name": button_name(RUN_PORTFOLIO_ACTION),
    },
    {
        "name": DATA_POOL_ROW,
        "height_px": 18,
        "action": RUN_EVERY_PORTFOLIO_ACTION,
        "text": RUN_EVERY_PORTFOLIO_TEXT,
        "button_name": button_name(RUN_EVERY_PORTFOLIO_ACTION),
    },
)

ROWS_FOR_MODE = {
    MODE_VALIDATION: RESERVED_ROWS,
    MODE_BACK_TEST: BACK_TEST_ROWS,
    MODE_PORTFOLIO_BATTERY: BATTERY_ROWS,
}


def reserved_rows(mode: str) -> tuple[dict[str, Any], ...]:
    """The two button rows ``mode`` puts where the two strips were."""
    return ROWS_FOR_MODE.get(mode, RESERVED_ROWS)


VALIDATION_TITLE = "Validation"
VALIDATION_IDLE_TEXT = "No validation run yet. Import Live Fleet or Generate From YTD."
EXCHANGE_PROMPT_FORMAT = "More than one exchange is active. Choose one: {options}"

#: How many compared rows the Validation table lists.
VALIDATION_ROW_LIMIT = 200

#: How many trades one press reruns. A whole-fleet pass reads the gate log
#: once.
VALIDATION_RERUN_LIMIT = 400

BACK_TEST_TITLE = "Back Test"
BACK_TEST_IDLE_TEXT = "No back test yet. Import Live Fleet or Create New Bots."

#: The columns both hosts give the Back Test table, read off the model.
BACK_TEST_COLUMNS = (
    "Bot ID",
    "Symbol",
    "Tablet",
    "Candles",
    "Ticks",
    "Scrum / Fold latched",
    "Scrum / Fold filled",
    "Units gained",
    "Cash held",
)

#: How many compared bots the Back Test table lists.
BACK_TEST_ROW_LIMIT = 200

BATTERY_TITLE = "Portfolio Battery"
BATTERY_IDLE_TEXT = "No battery run yet. Run Portfolio or Run Every Portfolio."

#: The columns both hosts give the Portfolio Battery table, one row per
#: portfolio and timeframe.
BATTERY_COLUMNS = (
    "Portfolio",
    "Timeframe",
    "Span",
    "Symbols",
    "Bars",
    "Evaluations",
    "Trades",
    "HODL end",
    "Harvest-Fold end",
    "Difference",
    "Missing weight",
)

#: How many portfolio-and-timeframe rows the Portfolio Battery table lists.
BATTERY_ROW_LIMIT = 200

PORTFOLIO_LABEL_TEXT = "Portfolio:"
SPAN_LABEL_TEXT = "Span:"

#: The spans and timeframes both hosts list, from ``portfolio_battery``.
BATTERY_SPANS = portfolio_battery.SPANS
BATTERY_TIMEFRAMES = portfolio_battery.TIMEFRAMES
DEFAULT_SPAN = portfolio_battery.FULL_SPAN

#: The portfolio a run opens on when the operator has chosen none.
DEFAULT_PORTFOLIO = sorted(PORTFOLIOS)[0]

NO_NEW_BOT_TEXT = "Choose a Stone Tablet, then press Create New Bots."

FLEET_LABEL_TEXT = "Scrumming Bots"
FLEET_EMPTY_TEXT = "No simulated fleet. Import Live Fleet builds one."
TABLET_LABEL_TEXT = "Tablet:"
NO_TABLET_TEXT = "No Stone Tablet on disk."
SHORT_TABLET_FORMAT = "{asset} {year} holds {count} candles; {need} are needed."
#: Under the staleness banner over a tablet reading: the day of the newest
#: candle the reading was computed on.
TABLET_ENDS_FORMAT = "Stone Tablet ends {day}."

LAYER_INDICATORS = "indicators"
LAYER_PLAYBACK = "playback"
LAYERS = (LAYER_INDICATORS, LAYER_PLAYBACK)

#: The flip's text on each layer: the directive's word for the two windows on
#: the panel, where the header row's room under a monospace theme is 90 px,
#: and the panel's own word on the layer.
FLIP_BUTTON_TEXT = {
    LAYER_INDICATORS: "Replay",
    LAYER_PLAYBACK: "Indicators",
}

VWAP_TITLE = "VWAP"
PLAYBACK_TITLE = "Stone Tablet Playback"
REPLAY_LOG_TITLE = "Replay Log"

#: The retrieval button on the replay layer, read off the chosen item: the
#: directive's own two words for a market with no tablet and for one with.
RETRIEVE_TABLET_TEXT = "Retrieve Tablet"
UPDATE_TABLET_TEXT = "Update Tablet"
#: The chooser's item for a held market with no tablet on disk.
NO_TABLET_CHOICE_FORMAT = "{key} — no tablet"

#: The Trading tab's own pane geometry, cloned. ``trading_tab.py`` sets these.
MARGINS_PX = [2, 2, 2, 2]
SPACING_PX = 2
HANDLE_WIDTH_PX = 5
TOP_SPLITTER_SIZES = [600, 500]
MAIN_SPLITTER_SIZES = [500, 350]
LAYER_SPLITTER_SIZES = [500, 500]

#: The two grounds carry the Simulator's tone, ``toward_black`` at
#: ``NIGREDO_FRACTION``; every other entry is Live's own token.
SKIN = {
    "--sim-ground": toward_black(ds.SURFACE_0, NIGREDO_FRACTION),
    "--sim-chart-ground": toward_black(ds.SURFACE_CHART, NIGREDO_FRACTION),
    "--sim-heading-colour": ds.PRIMARY,
    "--sim-body-colour": ds.TEXT_MED,
    "--sim-empty-colour": ds.TEXT_EMPTY_STATE,
    "--sim-outline": ds.OUTLINE,
    "--sim-close-line": ds.TEXT_HIGH,
    "--sim-vwap-line": ds.ACCENT_GOLD,
    "--sim-candle-up": ds.SUCCESS,
    "--sim-candle-down": ds.ERROR,
    "--sim-mark-scrum": ds.ACCENT_GOLD,
    "--sim-mark-fold": ds.INFO,
    "--sim-better-colour": ds.SUCCESS,
    "--sim-agrees-colour": ds.SUCCESS,
    "--sim-disagrees-colour": ds.ERROR,
    "--sim-body-size": f"{ds.TYPE_BODY}px",
    "--sim-caption-size": f"{ds.TYPE_CAPTION}px",
}

#: ``MARK_GLYPHS`` is keyed by ``SCRUM_SIDE`` and ``FOLD_SIDE``, the strings
#: ``back_test.SCRUM`` and ``back_test.FOLD`` carry.
if MARK_GLYPHS.keys() != {back_test.SCRUM, back_test.FOLD}:
    raise ImportError("MARK_GLYPHS keys differ from back_test.SCRUM and FOLD")

#: The replay layer's header figures with no run held.
NO_RUN_TEXT = "no run"
NO_IMPROVEMENT_TEXT = "—"

DECLARED_FIELDS = (
    "accessible_name",
    "back_test",
    "battery",
    "built",
    "fleet",
    "heading",
    "indicators",
    "issue",
    "layer",
    "layers",
    "method",
    "mode",
    "modes",
    "panes",
    "playback",
    "privacy_button",
    "replay_log",
    "reserved_rows",
    "skin",
    "tablet",
    "tablets",
    "validation",
    "vwap",
)


def iso_day(ts_ms: Any) -> str:
    """``YYYY-MM-DD`` in UTC for ``ts_ms``, empty at or below zero."""
    try:
        stamp = int(ts_ms)
    except (TypeError, ValueError):
        return ""
    if stamp <= 0:
        return ""
    return datetime.fromtimestamp(stamp / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def window_of(candles: Sequence[Sequence[float]]) -> list[list[float]]:
    """The last ``WINDOW_CANDLES`` rows of ``candles``, oldest first."""
    rows = [list(row) for row in candles]
    return rows[-WINDOW_CANDLES:]


def typical_price(row: Sequence[float]) -> float:
    """``(high + low + close) / 3`` for one ``[ts, o, h, l, c, v]`` row."""
    return (float(row[2]) + float(row[3]) + float(row[4])) / 3.0


def vwap_series(candles: Sequence[Sequence[float]]) -> list[Optional[float]]:
    """Cumulative ``sum(typical_price * volume) / sum(volume)`` per row.

    A row whose cumulative volume is still zero carries None.
    """
    out: list[Optional[float]] = []
    price_volume = 0.0
    volume = 0.0
    for row in candles:
        price_volume += typical_price(row) * float(row[5])
        volume += float(row[5])
        out.append(price_volume / volume if volume > 0.0 else None)
    return out


def bounds(values: Sequence[Optional[float]]) -> dict:
    """The lowest and the highest number in ``values``, ignoring None."""
    numbers = [float(one) for one in values if one is not None]
    if not numbers:
        return {"low": 0.0, "high": 0.0}
    return {"low": min(numbers), "high": max(numbers)}


def unit_x(index: int, count: int) -> float:
    """``index``'s place across ``count`` columns, 0.0 to 1.0."""
    if count <= 1:
        return 0.5
    return float(index) / float(count - 1)


def unit_y(value: Optional[float], low: float, high: float) -> Optional[float]:
    """``value`` down the pane, 0.0 at ``high`` and 1.0 at ``low``."""
    if value is None:
        return None
    if high <= low:
        return 0.5
    return (high - float(value)) / (high - low)


def line_points(
    values: Sequence[Optional[float]], low: float, high: float
) -> list[Optional[list[float]]]:
    """Each value as an ``[x, y]`` pair in the unit square, None where absent."""
    count = len(values)
    out: list[Optional[list[float]]] = []
    for index, value in enumerate(values):
        y = unit_y(value, low, high)
        out.append(None if y is None else [unit_x(index, count), y])
    return out


def candle_shapes(
    candles: Sequence[Sequence[float]], low: float, high: float
) -> list[dict]:
    """Each candle's body and wick as unit-square edges, with its direction."""
    count = len(candles)
    out: list[dict] = []
    for index, row in enumerate(candles):
        open_px = float(row[1])
        close_px = float(row[4])
        out.append(
            {
                "x": unit_x(index, count),
                "ts_ms": int(row[0]),
                "open": open_px,
                "high": float(row[2]),
                "low": float(row[3]),
                "close": close_px,
                "volume": float(row[5]),
                "body_top": unit_y(max(open_px, close_px), low, high),
                "body_bottom": unit_y(min(open_px, close_px), low, high),
                "wick_top": unit_y(float(row[2]), low, high),
                "wick_bottom": unit_y(float(row[3]), low, high),
                "up": close_px >= open_px,
            }
        )
    return out


def mark_shapes(
    candles: Sequence[Sequence[float]],
    fills: Sequence[Any],
    low: float,
    high: float,
) -> list[dict]:
    """One mark per fill in ``fills`` whose ``ts_ms`` is a candle's stamp in
    ``candles``: the candle's ``index`` and ``x``, the fill's price as ``y``
    over ``low`` and ``high``, its ``side`` and the ``MARK_GLYPHS`` name."""
    count = len(candles)
    index_of = {int(row[0]): index for index, row in enumerate(candles)}
    out: list[dict] = []
    for fill in fills:
        index = index_of.get(int(fill.ts_ms))
        if index is None:
            continue
        glyph = MARK_GLYPHS.get(str(fill.side))
        if glyph is None:
            continue
        out.append(
            {
                "index": index,
                "x": unit_x(index, count),
                "y": unit_y(float(fill.price), low, high),
                "ts_ms": int(fill.ts_ms),
                "price": float(fill.price),
                "side": str(fill.side),
                "scrum_price": float(getattr(fill, "scrum_price", 0.0) or 0.0),
                "glyph": glyph["name"],
            }
        )
    return out


def privacy_masked() -> bool:
    """True when the registry holds fields and every one of them is masked."""
    from ...core.privacy_mask_registry import get_privacy_mask_registry

    registry = get_privacy_mask_registry()
    state = registry.to_dict()
    field_ids = registry.known_field_ids()
    return bool(field_ids) and all(bool(state.get(one, False)) for one in field_ids)


def toggle_privacy() -> bool:
    """Mask every field while any is revealed, reveal all otherwise.

    Returns the state every field now holds.
    """
    from ...core.privacy_mask_registry import get_privacy_mask_registry

    registry = get_privacy_mask_registry()
    state = registry.to_dict()
    any_revealed = any(not state.get(one, False) for one in registry.known_field_ids())
    registry.set_all(any_revealed)
    return any_revealed


def privacy_button(masked: bool) -> dict:
    """The Privacy Mode button's words and the state they report."""
    return {
        "text": PRIVACY_ON_TEXT if masked else PRIVACY_OFF_TEXT,
        "masked": bool(masked),
    }


def usd_text(amount: Optional[float]) -> str:
    """``amount`` as ``$0.00``, empty when no target is known."""
    return "" if amount is None else f"${float(amount):,.2f}"


def fleet_row(bot, counts: dict) -> dict:
    """One simulated bot as the bot list draws it, under ``COLUMN_LABELS``.

    ``counts`` carries ``trades`` and the ``position_usd`` a ``BackTestRun``
    ended holding; the Ammo, Fire and detail cells stay empty.
    """
    return {
        "bot_id": bot.bot_id,
        "symbol": bot.symbol,
        "origin": bot.origin,
        "cells": [
            bot.bot_id,
            bot.symbol,
            usd_text(counts.get("position_usd")),
            str(counts.get("trades", 0)),
            usd_text(bot.target_usd),
            "",
            "",
            "",
            "",
            "",
        ],
    }


def fleet_model(bots: Sequence[Any] = (), by_bot: Optional[dict] = None) -> dict:
    """The bot list: the Trading tab's columns over ``bots``."""
    counted = by_bot or {}
    rows = [fleet_row(one, counted.get(one.bot_id, {})) for one in bots]
    return {
        "label": FLEET_LABEL_TEXT,
        "columns": list(COLUMN_LABELS),
        "column_count": len(COLUMN_LABELS),
        "fixed_widths": {str(key): int(value) for key, value in FIXED_WIDTHS.items()},
        "rows": rows,
        "row_count": len(rows),
        "empty_text": FLEET_EMPTY_TEXT,
    }


def tablet_row(entry) -> dict:
    """One MANIFEST entry as the tablet selector lists it."""
    return {
        "key": tablet_key(entry),
        "asset": entry.asset,
        "year": int(entry.year),
        "timeframe": entry.timeframe,
        "exchange_id": entry.exchange_id,
        "source": entry.source,
        "candle_count": int(entry.candle_count),
        "first_ts_ms": int(entry.first_ts_ms),
        "last_ts_ms": int(entry.last_ts_ms),
        "first_day": iso_day(entry.first_ts_ms),
        "last_day": iso_day(entry.last_ts_ms),
    }


def tablet_for(source: TabletSource, exchange_id: str, asset: str, timeframe: str):
    """The newest MANIFEST entry filed under ``asset`` on ``exchange_id`` at
    ``timeframe``, or None; a tie on ``last_ts_ms`` breaks on the key."""
    wanted = (str(asset).upper(), str(exchange_id), str(timeframe))
    found = [
        entry
        for entry in source.entries()
        if (str(entry.asset).upper(), str(entry.exchange_id), str(entry.timeframe))
        == wanted
    ]
    if not found:
        return None
    return max(found, key=lambda entry: (entry.last_ts_ms, tablet_key(entry)))


def multi_tf_summary(candles: Sequence[Sequence[float]], timeframe: str) -> dict:
    """The voting engine's reading of ``candles``, keyed by ``timeframe``, each
    signal carrying the ``details`` its indicator published.

    An empty dict comes back when ``candles_from_raw`` or ``compute_all`` raises.
    """
    try:
        from ...trading.indicators.types import candles_from_raw
        from ...trading.ta_engine import VotingEngine

        parsed = candles_from_raw([list(row) for row in candles])
        summary = VotingEngine().compute_all(parsed, timeframe)
    except Exception as exc:  # noqa: BLE001 - a bad tablet draws the empty state
        logger.warning("Simulator: the voting engine refused the tablet: %s", exc)
        return {}
    return {
        timeframe: {
            "bullish": summary.bullish_count,
            "bearish": summary.bearish_count,
            "neutral": summary.neutral_count,
            "net_score": summary.net_score,
            "confidence": summary.consensus_confidence,
            "direction": summary.consensus_direction.name,
            "signals": [
                {
                    "indicator": one.indicator,
                    "direction": one.direction.name,
                    "confidence": one.confidence,
                    "details": dict(getattr(one, "details", None) or {}),
                }
                for one in summary.signals
            ],
            "locks": [],
        }
    }


def indicator_payload(
    candles: Sequence[Sequence[float]], timeframe: str, symbol: str, refusal: str
) -> dict:
    """The Indicator Voting Panel drawn from ``candles``, or the empty state.

    A non-empty ``refusal`` reaches ``show_no_data`` and no reading is computed.
    """
    model = ivp.IndicatorPanelModel()
    if refusal:
        model.show_no_data(refusal)
        return ivp.build_payload(model)
    summary = multi_tf_summary(candles, timeframe)
    if not summary:
        model.show_no_data(NO_TABLET_TEXT)
        return ivp.build_payload(model)
    model.set_summary(summary, symbol)
    return ivp.build_payload(model)


def vwap_payload(candles: Sequence[Sequence[float]]) -> dict:
    """The VWAP window: the close line, the VWAP line and their bounds."""
    closes: list[Optional[float]] = [float(row[4]) for row in candles]
    vwaps = vwap_series(candles)
    span = bounds(list(closes) + list(vwaps))
    return {
        "title": VWAP_TITLE,
        "low": span["low"],
        "high": span["high"],
        "point_count": len(candles),
        "close_points": line_points(closes, span["low"], span["high"]),
        "vwap_points": line_points(vwaps, span["low"], span["high"]),
        "close_last": closes[-1] if closes else None,
        "vwap_last": vwaps[-1] if vwaps else None,
    }


def playback_payload(
    candles: Sequence[Sequence[float]], fills: Sequence[Any] = ()
) -> dict:
    """The playback window: one shape per candle, the price bounds, and one
    ``mark_shapes`` mark per fill in ``fills`` on a candle in ``candles``, with
    ``fills`` the count handed and ``mark_count`` the count drawn."""
    span = bounds(
        [float(row[2]) for row in candles] + [float(row[3]) for row in candles]
    )
    marks = mark_shapes(candles, fills, span["low"], span["high"])
    return {
        "title": PLAYBACK_TITLE,
        "low": span["low"],
        "high": span["high"],
        "candle_count": len(candles),
        "candles": candle_shapes(candles, span["low"], span["high"]),
        "marks": marks,
        "mark_count": len(marks),
        "fills": len(fills),
        "glyphs": {side: dict(glyph) for side, glyph in MARK_GLYPHS.items()},
        "mark_width_ratio": MARK_WIDTH_RATIO,
        "mark_height_fraction": MARK_HEIGHT_FRACTION,
        "mark_outline_px": MARK_OUTLINE_PX,
    }


def replay_colours() -> dict:
    """The seven ``SKIN`` colours the two replay windows paint, in both builds."""
    return {
        "ground": SKIN["--sim-chart-ground"],
        "close": SKIN["--sim-close-line"],
        "vwap": SKIN["--sim-vwap-line"],
        "up": SKIN["--sim-candle-up"],
        "down": SKIN["--sim-candle-down"],
        "mark_scrum": SKIN["--sim-mark-scrum"],
        "mark_fold": SKIN["--sim-mark-fold"],
    }


def market_key(asset: str, exchange_id: str) -> str:
    """The chooser's key for a held market with no tablet on disk."""
    return f"{str(asset).upper()}_{NATIVE_TIMEFRAME}_{exchange_id}"


def tablet_choices(source: TabletSource, bots: Sequence[Any] = ()) -> list[dict]:
    """The tablet chooser's items: one per MANIFEST row, keyed by
    ``tablet_key`` and shown as it, then one per held market in ``bots`` with
    no tablet at ``NATIVE_TIMEFRAME``, keyed by ``market_key`` and shown through
    ``NO_TABLET_CHOICE_FORMAT``."""
    entries = source.entries()
    items = [
        {
            "key": tablet_key(entry),
            "text": tablet_key(entry),
            "asset": entry.asset,
            "exchange_id": entry.exchange_id,
            "timeframe": entry.timeframe,
            "on_disk": True,
        }
        for entry in entries
    ]
    held = {(str(e.asset).upper(), str(e.exchange_id)) for e in entries}
    seen: set[tuple[str, str]] = set()
    for bot in bots:
        market = (str(bot.asset).upper(), str(bot.exchange_id))
        if market in held or market in seen:
            continue
        seen.add(market)
        key = market_key(*market)
        items.append(
            {
                "key": key,
                "text": NO_TABLET_CHOICE_FORMAT.format(key=key),
                "asset": market[0],
                "exchange_id": market[1],
                "timeframe": NATIVE_TIMEFRAME,
                "on_disk": False,
            }
        )
    return items


def default_tablet_key(source: TabletSource, bot: Any = None) -> str:
    """The chooser's key for ``bot``: ``tablet_for`` at its timeframe, else the
    newest entry for its market, else ``market_key``; with no bot,
    ``source.newest``, or an empty string when the root holds nothing."""
    if bot is not None:
        entry = tablet_for(source, bot.exchange_id, bot.asset, bot.ta_timeframe)
        if entry is not None:
            return tablet_key(entry)
        wanted = (str(bot.asset).upper(), str(bot.exchange_id))
        held = [
            one
            for one in source.entries()
            if (str(one.asset).upper(), str(one.exchange_id)) == wanted
        ]
        if held:
            return tablet_key(max(held, key=lambda e: (e.last_ts_ms, tablet_key(e))))
        return market_key(*wanted)
    newest = source.newest()
    return tablet_key(newest) if newest is not None else ""


def shown_bot(
    bots: Sequence[Any],
    asset: str,
    exchange_id: str,
    last_bot_id: str = "",
    selected_bot_id: str = "",
) -> Any:
    """The bot whose fills the playback marks for a tablet on ``asset`` and
    ``exchange_id``: of the ``bots`` on that market, the one ``last_bot_id``
    names, else the one ``selected_bot_id`` names, else the lowest ``bot_id``;
    None with no bot on the market."""
    wanted = (str(asset).upper(), str(exchange_id))
    held = sorted(
        (
            bot
            for bot in bots
            if (str(bot.asset).upper(), str(bot.exchange_id)) == wanted
        ),
        key=lambda bot: str(bot.bot_id),
    )
    if not held:
        return None
    for preferred in (last_bot_id, selected_bot_id):
        found = next((bot for bot in held if bot.bot_id == preferred), None)
        if found is not None:
            return found
    return held[0]


def fills_for(fills: Sequence[Any], bot_id: str, timeframe: str) -> list:
    """The fills in ``fills`` of ``bot_id`` whose ``timeframe`` is ``timeframe``
    or empty, in fill order."""
    return [
        fill
        for fill in fills
        if str(fill.bot_id) == str(bot_id)
        and str(getattr(fill, "timeframe", "") or "") in ("", str(timeframe))
    ]


def trade_pairs(fills: Sequence[Any]) -> list[tuple[float, float]]:
    """``(scrum_price, fold price)`` for each ``FOLD`` in ``fills`` whose
    ``scrum_price`` is above zero."""
    return [
        (float(fill.scrum_price), float(fill.price))
        for fill in fills
        if str(fill.side) == back_test.FOLD
        and float(getattr(fill, "scrum_price", 0.0) or 0.0) > 0.0
    ]


def improvement_pct(hodl_usd: float, harvest_fold_usd: float) -> Optional[float]:
    """``harvest_fold_usd`` less ``hodl_usd`` as a percentage of ``hodl_usd``;
    None when ``hodl_usd`` is not above zero."""
    if float(hodl_usd) <= 0.0:
        return None
    return 100.0 * (float(harvest_fold_usd) - float(hodl_usd)) / float(hodl_usd)


def improvement_for(outcome: Any, bot_id: str, timeframe: str) -> Optional[float]:
    """``improvement_pct`` over ``baseline_usd`` and ``accumulation_usd`` of the
    first ``SymbolRun`` in ``outcome`` that ran ``bot_id`` at ``timeframe``;
    None with no such run or no ``outcome``."""
    for portfolio in getattr(outcome, "portfolios", None) or ():
        for frame in getattr(portfolio, "timeframes", None) or ():
            for run in getattr(frame, "runs", None) or ():
                if (
                    str(run.bot_id) == str(bot_id)
                    and str(run.timeframe) == str(timeframe)
                    and run.ran
                ):
                    return improvement_pct(run.baseline_usd, run.accumulation_usd)
    return None


def replay_figures(
    bot: Any, fills: Sequence[Any], improvement: Optional[float]
) -> dict:
    """The header's figures for ``bot`` over its ``fills``:
    ``opposing_trade_distances`` over ``trade_pairs``, the ``improvement``
    percentage, and ``held`` False with no fill."""
    distances = opposing_trade_distances(trade_pairs(fills))
    return {
        "bot_id": str(bot.bot_id) if bot is not None else "",
        "held": bool(fills),
        "fills": len(fills),
        "pairs": int(distances["count"]),
        "mean_pct": distances["mean_pct"],
        "median_pct": distances["median_pct"],
        "improvement_pct": improvement,
    }


def replay_feed(
    source: TabletSource,
    key: str,
    bots: Sequence[Any] = (),
    fills: Sequence[Any] = (),
    outcome: Any = None,
    last_bot_id: str = "",
    selected_bot_id: str = "",
) -> dict:
    """The two windows' payloads for the item ``key`` names: ``vwap_payload``
    and ``playback_payload`` over ``window_of`` the tablet, empty with no
    entry or under ``MIN_CANDLES``, with ``entry`` and ``refusal`` beside them,
    the playback marking ``fills_for`` the ``shown_bot`` at the entry's
    timeframe and ``figures`` reading ``replay_figures`` over the same fills
    with ``improvement_for`` the bot's run in ``outcome``."""
    entry = source.entry_for(key) if key else None
    candles = window_of(source.candles(entry)) if entry is not None else []
    refusal = ""
    if entry is None:
        refusal = NO_TABLET_TEXT
    elif len(candles) < MIN_CANDLES:
        refusal = SHORT_TABLET_FORMAT.format(
            asset=entry.asset, year=entry.year, count=len(candles), need=MIN_CANDLES
        )
    drawable: list[list[float]] = [] if refusal else candles
    bot = (
        shown_bot(bots, entry.asset, entry.exchange_id, last_bot_id, selected_bot_id)
        if entry is not None
        else None
    )
    shown = (
        fills_for(fills, bot.bot_id, entry.timeframe)
        if bot is not None and entry is not None
        else []
    )
    improvement = (
        improvement_for(outcome, bot.bot_id, entry.timeframe)
        if bot is not None and entry is not None
        else None
    )
    return {
        "key": key,
        "entry": entry,
        "on_disk": entry is not None,
        "refusal": refusal,
        "window": len(candles),
        "vwap": vwap_payload(drawable),
        "playback": playback_payload(drawable, shown),
        "figures": replay_figures(bot, shown, improvement),
        "colours": replay_colours(),
        "button_text": (
            UPDATE_TABLET_TEXT if entry is not None else RETRIEVE_TABLET_TEXT
        ),
    }


def replay_lines(entry, candles: Sequence[Sequence[float]], refusal: str) -> list[str]:
    """What the Replay Log says about the tablet the windows were drawn from."""
    if entry is None:
        return [NO_TABLET_TEXT]
    read = [
        f"{tablet_key(entry)} — {entry.candle_count} candles, "
        f"{iso_day(entry.first_ts_ms)} to {iso_day(entry.last_ts_ms)}",
        f"source {entry.source}",
        f"window {len(candles)} of {entry.candle_count} candles",
    ]
    if refusal:
        read.append(refusal)
    return read


def label_row(seen) -> dict:
    """One compared trade as the Validation table lists it."""
    return {
        "bot_id": seen.bot_id,
        "symbol": seen.symbol,
        "trade_at": validation.iso_stamp(seen.trade_ts_ms),
        "candle_at": validation.iso_stamp(seen.candle_ts_ms),
        "gate_at": validation.iso_stamp(seen.gate_ts_ms),
        "agreed": seen.agreed,
        "light_count": len(seen.labels),
        "latches_identically": seen.latches_identically,
        "lights": [
            {
                "bank": one.bank,
                "label": one.label,
                "recorded": one.recorded,
                "rerun": one.rerun,
                "driven_by": one.driven_by,
                "agrees": one.agrees,
            }
            for one in seen.labels
        ],
    }


def empty_validation() -> dict:
    """The Validation pane before any run, naming the two ways in."""
    return {
        "title": VALIDATION_TITLE,
        "ran": False,
        "origin": "",
        "match_key": "",
        "bot_count": 0,
        "exchange": {"options": [], "chosen": "", "prompt": False, "count": 0},
        "prompt_text": "",
        "lines": [VALIDATION_IDLE_TEXT],
        "summary": validation.summarise([]),
        "coverage": {
            "total": 0,
            "snapped": 0,
            "unsnapped": 0,
            "by_reason": {},
            "uncovered_since": "",
            "uncovered_until": "",
            "newest_candle": "",
        },
        "rows": [],
        "row_count": 0,
        "buttons": [dict(one) for one in RESERVED_ROWS],
    }


def validation_payload(outcome, origin: str, choice: dict) -> dict:
    """One ``ValidationRun`` as the Validation pane draws it."""
    cover = outcome.coverage
    listed = list(outcome.comparisons)[:VALIDATION_ROW_LIMIT]
    return {
        "title": VALIDATION_TITLE,
        "ran": True,
        "origin": origin,
        "match_key": outcome.match_key,
        "bot_count": len(outcome.bots),
        "exchange": dict(choice),
        "prompt_text": (
            EXCHANGE_PROMPT_FORMAT.format(options=", ".join(choice["options"]))
            if choice["prompt"]
            else ""
        ),
        "lines": list(outcome.lines),
        "summary": outcome.summary,
        "coverage": {
            "total": cover.total,
            "snapped": cover.snapped,
            "unsnapped": cover.unsnapped,
            "by_reason": dict(cover.by_reason),
            "uncovered_since": validation.iso_stamp(cover.uncovered_since_ms),
            "uncovered_until": validation.iso_stamp(cover.uncovered_until_ms),
            "newest_candle": validation.iso_stamp(cover.tablet_last_ts_ms),
        },
        "rows": [label_row(one) for one in listed],
        "row_count": len(outcome.comparisons),
        "buttons": [dict(one) for one in RESERVED_ROWS],
    }


def back_test_row(result) -> dict:
    """One bot's whole Back Test pass as the table lists it."""
    return {
        "bot_id": result.bot_id,
        "symbol": result.symbol,
        "tablet_key": result.tablet_key,
        "outcome": result.outcome,
        "candles_read": result.candles_read,
        "ticks": result.ticks,
        "scrum_latched": result.scrum_latched,
        "fold_latched": result.fold_latched,
        "scrum_trades": result.scrum_trades,
        "fold_trades": result.fold_trades,
        "start_units": result.start_units,
        "end_units": result.end_units,
        "units_gained": result.units_gained,
        "units_text": f"{result.units_gained:+.8f}",
        "cash_usd": result.cash_usd,
        "cash_text": usd_text(result.cash_usd),
        "fees_usd": result.fees_usd,
        "first_at": validation.iso_stamp(result.first_ts_ms),
        "last_at": validation.iso_stamp(result.last_ts_ms),
    }


def empty_back_test() -> dict:
    """The Back Test pane before any run, naming the two ways in."""
    return {
        "title": BACK_TEST_TITLE,
        "columns": list(BACK_TEST_COLUMNS),
        "ran": False,
        "origin": "",
        "bot_count": 0,
        "exchange": {"options": [], "chosen": "", "prompt": False, "count": 0},
        "prompt_text": "",
        "lines": [BACK_TEST_IDLE_TEXT],
        "summary": {},
        "missing": [],
        "rows": [],
        "row_count": 0,
        "buttons": [dict(one) for one in BACK_TEST_ROWS],
    }


def back_test_payload(outcome, origin: str, choice: dict) -> dict:
    """One ``BackTestRun`` as the Back Test pane draws it."""
    listed = list(outcome.results)[:BACK_TEST_ROW_LIMIT]
    return {
        "title": BACK_TEST_TITLE,
        "columns": list(BACK_TEST_COLUMNS),
        "ran": True,
        "origin": origin,
        "bot_count": len(outcome.bots),
        "exchange": dict(choice),
        "prompt_text": (
            EXCHANGE_PROMPT_FORMAT.format(options=", ".join(choice["options"]))
            if choice["prompt"]
            else ""
        ),
        "lines": list(outcome.lines),
        "summary": outcome.summary,
        "missing": [
            {"asset": asset, "exchange_id": venue} for asset, venue in outcome.missing
        ],
        "rows": [back_test_row(one) for one in listed],
        "row_count": len(outcome.results),
        "buttons": [dict(one) for one in BACK_TEST_ROWS],
    }


def pct_text(share: float) -> str:
    """``share`` of one as ``0.0%``."""
    return f"{float(share) * 100.0:.1f}%"


def battery_row(portfolio: str, read: dict) -> dict:
    """One portfolio at one timeframe as the Portfolio Battery table lists
    it."""
    return {
        "portfolio": portfolio,
        "timeframe": read["timeframe"],
        "first_at": read["first_at"],
        "last_at": read["last_at"],
        "span_text": (
            f"{read['first_at']} to {read['last_at']}" if read["first_at"] else ""
        ),
        "symbols": read["symbols"],
        "symbols_run": read["symbols_run"],
        "symbols_text": f"{read['symbols_run']} of {read['symbols']}",
        "bars": read["bars"],
        "ticks": read["ticks"],
        "evaluations_expected": read["evaluations_expected"],
        "scrum_latched": read["scrum_latched"],
        "fold_latched": read["fold_latched"],
        "trades": read["trades"],
        "partial_exits": read["partial_exits"],
        "re_entries": read["re_entries"],
        "baseline_usd": read["baseline_usd"],
        "baseline_text": usd_text(read["baseline_usd"]),
        "accumulation_usd": read["accumulation_usd"],
        "accumulation_text": usd_text(read["accumulation_usd"]),
        "difference_usd": read["difference_usd"],
        "difference_pct": read["difference_pct"],
        "difference_text": (
            f"{read['difference_usd']:+,.2f} ({read['difference_pct']:+.2f}%)"
        ),
        "comparison": read["comparison"],
        "missing_weight": read["missing_weight"],
        "missing_text": pct_text(read["missing_weight"]),
        "missing_symbols": list(read["missing_symbols"]),
    }


def battery_rows(outcome) -> list[dict]:
    """Every portfolio-and-timeframe row of one ``BatteryRun``."""
    out: list[dict] = []
    for result in outcome.portfolios:
        read = result.summary
        for row in read["timeframes"]:
            out.append(battery_row(read["portfolio"], row))
    return out


def battery_fleet(result) -> dict:
    """The bot list for one ``PortfolioResult``, one bot per symbol it ran."""
    if not result.timeframes:
        return fleet_model()
    first = result.timeframes[0]
    bots = [
        portfolio_battery.battery_bot(
            one.asset, one.exchange_id, one.timeframe, one.capital_usd
        )
        for one in first.runs
    ]
    counts = {
        bot.bot_id: {
            "trades": run.trade_count,
            "position_usd": run.accumulation_usd,
        }
        for bot, run in zip(bots, first.runs, strict=True)
    }
    return fleet_model(bots, counts)


def portfolio_rows() -> list[dict]:
    """Every portfolio the selector lists, by name."""
    return [
        {
            "name": name,
            "symbols": list(PORTFOLIOS[name].symbols),
            "symbol_count": len(PORTFOLIOS[name].symbols),
            "description": PORTFOLIOS[name].description,
        }
        for name in sorted(PORTFOLIOS)
    ]


def empty_battery(portfolio: str = "", span: str = "") -> dict:
    """The Portfolio Battery pane before any run, naming the two ways in."""
    return {
        "title": BATTERY_TITLE,
        "columns": list(BATTERY_COLUMNS),
        "ran": False,
        "origin": "",
        "portfolio": str(portfolio or DEFAULT_PORTFOLIO),
        "portfolios": portfolio_rows(),
        "span": str(span or DEFAULT_SPAN),
        "spans": list(BATTERY_SPANS),
        "timeframes": list(BATTERY_TIMEFRAMES),
        "lines": [BATTERY_IDLE_TEXT],
        "summary": {},
        "gaps": [],
        "missing_assets": [],
        "rows": [],
        "row_count": 0,
        "buttons": [dict(one) for one in BATTERY_ROWS],
    }


def battery_payload(outcome, origin: str, portfolio: str) -> dict:
    """One ``BatteryRun`` as the Portfolio Battery pane draws it."""
    rows = battery_rows(outcome)
    return {
        "title": BATTERY_TITLE,
        "columns": list(BATTERY_COLUMNS),
        "ran": True,
        "origin": origin,
        "portfolio": str(portfolio),
        "portfolios": portfolio_rows(),
        "span": outcome.span,
        "spans": list(BATTERY_SPANS),
        "timeframes": list(outcome.timeframes),
        "lines": list(outcome.lines),
        "summary": outcome.summary,
        "gaps": [dict(one) for one in outcome.gaps],
        "missing_assets": list(outcome.missing_assets),
        "rows": rows[:BATTERY_ROW_LIMIT],
        "row_count": len(rows),
        "buttons": [dict(one) for one in BATTERY_ROWS],
    }


def run_battery(origin: str, portfolio: str = "", span: str = "") -> dict:
    """Walk one portfolio, or every portfolio, over the RA-StoneTablets.

    ``RUN_PORTFOLIO_ACTION`` runs the chosen portfolio and
    ``RUN_EVERY_PORTFOLIO_ACTION`` runs all of them.
    """
    chosen = str(portfolio or DEFAULT_PORTFOLIO)
    window = str(span or DEFAULT_SPAN)
    names = () if origin == RUN_EVERY_PORTFOLIO_ACTION else (chosen,)
    outcome = portfolio_battery.run_battery(
        TabletSource(BATTERY_TABLET_ROOT),
        names=names,
        span=window,
    )
    payload = battery_payload(outcome, origin, chosen)
    for result in outcome.portfolios:
        if result.name == chosen:
            payload["fleet"] = battery_fleet(result)
            break
    return payload


def new_bot_specs(entry) -> list[dict]:
    """One new-bot spec for ``entry``'s asset, on the Bot Wizard's own
    defaults."""
    from .bot_wizard_surface import NUMBER_FIELDS

    if entry is None:
        return []
    return [
        {
            "symbol": f"{entry.asset}/USD",
            "exchange_id": entry.exchange_id,
            "target_usd": float(NUMBER_FIELDS["target_balance"]["value"]),
            "ta_timeframe": entry.timeframe,
            "scrumming_interval_pct": float(
                NUMBER_FIELDS["scrumming_interval"]["value"]
            ),
        }
    ]


def back_test_fleet(origin: str, exchange_id: str, specs: Sequence[dict]) -> tuple:
    """The fleet a Back Test button asks for, and the exchange choice it
    resolved.

    ``IMPORT_LIVE_FLEET_ACTION`` reads ``bot_state.json`` and
    ``CREATE_NEW_BOTS_ACTION`` builds one ``SimBot`` per spec.
    """
    from ...simulator.back_test import new_bots
    from ...simulator.fleet_source import FleetSource, exchange_choice, live_fleet

    if origin == CREATE_NEW_BOTS_ACTION:
        made = new_bots(list(specs))
        choice = exchange_choice(
            sorted({one.exchange_id for one in made if one.exchange_id}), exchange_id
        )
        return made, choice
    fleet = FleetSource()
    choice = exchange_choice(fleet.stored_exchanges(), exchange_id)
    return live_fleet(fleet, choice["chosen"]), choice


def run_back_test(
    origin: str, exchange_id: str = "", specs: Sequence[dict] = ()
) -> dict:
    """Walk ``origin``'s fleet over the live Stone Tablets and draw the result.

    An exchange choice still awaiting the operator returns the prompt and runs
    nothing.
    """
    from ...simulator import back_test

    bots, choice = back_test_fleet(origin, exchange_id, specs)
    if choice["prompt"]:
        idle = empty_back_test()
        idle["origin"] = origin
        idle["exchange"] = dict(choice)
        idle["prompt_text"] = EXCHANGE_PROMPT_FORMAT.format(
            options=", ".join(choice["options"])
        )
        idle["lines"] = [idle["prompt_text"]]
        return idle
    if not bots:
        idle = empty_back_test()
        idle["origin"] = origin
        idle["lines"] = [NO_NEW_BOT_TEXT]
        return idle
    outcome = back_test.run(
        bots,
        TabletSource(TABLET_ROOT),
        exchange_id=choice["chosen"],
    )
    payload = back_test_payload(outcome, origin, choice)
    payload["fleet"] = fleet_model(
        bots,
        {
            one.bot_id: {
                "trades": one.scrum_trades + one.fold_trades,
                "position_usd": one.end_units * one.end_price,
            }
            for one in outcome.results
        },
    )
    return payload


def build_fleet(origin: str, exchange_id: str = "") -> tuple:
    """The fleet one button asks for, and the exchange choice it resolved.

    ``IMPORT_LIVE_FLEET_ACTION`` reads ``bot_state.json`` through
    ``stored_exchanges`` and ``live_fleet``; ``GENERATE_FROM_YTD_ACTION`` reads
    the YTD trade files.
    """
    from ...simulator.fleet_source import (
        FleetSource,
        exchange_choice,
        live_fleet,
        ytd_fleet,
    )
    from ...simulator.ytd_trade_source import YtdTradeSource

    if origin == GENERATE_FROM_YTD_ACTION:
        ytd = YtdTradeSource()
        choice = exchange_choice(
            sorted({one.exchange_id for one in ytd.entries()}), exchange_id
        )
        return ytd_fleet(ytd, choice["chosen"]), choice
    fleet = FleetSource()
    choice = exchange_choice(fleet.stored_exchanges(), exchange_id)
    return live_fleet(fleet, choice["chosen"]), choice


def run_validation(origin: str, exchange_id: str = "") -> dict:
    """Build the fleet ``origin`` names and validate it against the record.

    An exchange choice still awaiting the operator returns the prompt and
    runs nothing.
    """
    from ...simulator.gate_log_source import GateLogSource
    from ...simulator.ytd_trade_source import YtdTradeSource

    bots, choice = build_fleet(origin, exchange_id)
    if choice["prompt"]:
        idle = empty_validation()
        idle["origin"] = origin
        idle["exchange"] = dict(choice)
        idle["prompt_text"] = EXCHANGE_PROMPT_FORMAT.format(
            options=", ".join(choice["options"])
        )
        idle["lines"] = [idle["prompt_text"]]
        return idle
    outcome = validation.run(
        bots,
        TabletSource(TABLET_ROOT),
        YtdTradeSource(),
        GateLogSource(),
        exchange_id=choice["chosen"],
        limit=VALIDATION_RERUN_LIMIT,
    )
    payload = validation_payload(outcome, origin, choice)
    payload["fleet"] = fleet_model(
        bots,
        {
            bot_id: {"trades": counts.get("snapped", 0)}
            for bot_id, counts in outcome.by_bot.items()
        },
    )
    return payload


def chosen_entry(source: TabletSource, key: str):
    """The entry ``key`` names, or ``source.newest`` when it names none."""
    if key:
        found = source.entry_for(key)
        if found is not None:
            return found
    return source.newest()


def build_view_model(
    source: TabletSource,
    key: str = "",
    layer: str = LAYER_INDICATORS,
    validation_payload_held: Optional[dict] = None,
    mode: str = MODE_VALIDATION,
    back_test_payload_held: Optional[dict] = None,
    battery_payload_held: Optional[dict] = None,
    portfolio: str = "",
    span: str = "",
) -> dict:
    """The whole Sim tab as one dict, read from ``source``.

    ``validation_payload_held``, ``back_test_payload_held`` and
    ``battery_payload_held`` carry the last run of each mode, and the matching
    ``empty_`` payload stands in before the first press. ``portfolio`` and
    ``span`` carry the two battery selectors before a battery has run.
    """
    chosen_layer = layer if layer in LAYERS else LAYER_INDICATORS
    chosen_mode = mode if mode in MODES else MODE_VALIDATION
    held = validation_payload_held or empty_validation()
    tested = back_test_payload_held or empty_back_test()
    charged = battery_payload_held or empty_battery(portfolio, span)
    shown = {
        MODE_BACK_TEST: tested,
        MODE_PORTFOLIO_BATTERY: charged,
    }.get(chosen_mode, held)
    entries = source.entries()
    entry = chosen_entry(source, key)
    candles = window_of(source.candles(entry)) if entry is not None else []
    refusal = ""
    if entry is None:
        refusal = NO_TABLET_TEXT
    elif len(candles) < MIN_CANDLES:
        refusal = SHORT_TABLET_FORMAT.format(
            asset=entry.asset, year=entry.year, count=len(candles), need=MIN_CANDLES
        )
    drawable: list[list[float]] = [] if refusal else candles
    return {
        "accessible_name": HEADING,
        "back_test": {name: value for name, value in tested.items() if name != "fleet"},
        "battery": {name: value for name, value in charged.items() if name != "fleet"},
        "built": BUILT,
        "fleet": shown.get("fleet") or fleet_model(),
        "heading": HEADING,
        "indicators": indicator_payload(
            candles,
            entry.timeframe if entry is not None else "",
            entry.asset if entry is not None else "",
            refusal,
        ),
        "issue": ISSUE,
        "layer": chosen_layer,
        "layers": list(LAYERS),
        "method": METHOD,
        "mode": chosen_mode,
        "modes": [
            {"name": name, "text": MODE_TEXT[name], "chosen": name == chosen_mode}
            for name in MODES
        ],
        "panes": {
            "margins_px": list(MARGINS_PX),
            "spacing_px": SPACING_PX,
            "handle_width_px": HANDLE_WIDTH_PX,
            "top_splitter_sizes": list(TOP_SPLITTER_SIZES),
            "main_splitter_sizes": list(MAIN_SPLITTER_SIZES),
            "layer_splitter_sizes": list(LAYER_SPLITTER_SIZES),
            "flip_button_text": FLIP_BUTTON_TEXT[chosen_layer],
            "tablet_label_text": TABLET_LABEL_TEXT,
            "mode_label_text": MODE_LABEL_TEXT,
            "portfolio_label_text": PORTFOLIO_LABEL_TEXT,
            "span_label_text": SPAN_LABEL_TEXT,
            "battery_row_shown": chosen_mode == MODE_PORTFOLIO_BATTERY,
        },
        "playback": playback_payload(drawable),
        "privacy_button": privacy_button(privacy_masked()),
        "replay_log": {
            "title": REPLAY_LOG_TITLE,
            "lines": replay_lines(entry, candles, refusal),
        },
        "reserved_rows": [dict(row) for row in reserved_rows(chosen_mode)],
        "skin": dict(SKIN),
        "tablet": None if entry is None else tablet_row(entry),
        "tablets": [tablet_row(one) for one in entries],
        "validation": {name: value for name, value in held.items() if name != "fleet"},
        "vwap": vwap_payload(drawable),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``simulator_tab.state``.

    Reads ``tablet``, ``layer`` and ``mode``; an unknown tablet falls back to
    the newest.
    """
    asked = params if isinstance(params, dict) else {}
    return build_view_model(
        TabletSource(TABLET_ROOT),
        str(asked.get("tablet") or ""),
        str(asked.get("layer") or LAYER_INDICATORS),
        mode=str(asked.get("mode") or MODE_VALIDATION),
    )
