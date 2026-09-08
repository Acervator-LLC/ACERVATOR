"""simulator_tab_surface.py -- the Sim tab as data, read from RA-StoneTablets.

``build_view_model`` reads one tablet through ``TabletSource`` and answers the
Trading-tab clone: the Privacy Mode row, the bot list under
``bot_status_table_surface.COLUMN_LABELS``, the panel
``indicator_panel_surface`` describes, and the second layer holding the VWAP
window over the tablet playback window. ``RESERVED_ROWS`` names the two rows
the crypto news ticker and the data-pool line held, which stay empty.
``src.core.desktop_bridge`` registers ``view_model`` under ``METHOD``, and
nothing here imports Qt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from ...simulator.tablet_source import TabletSource, tablet_key
from .. import design_system as ds
from . import indicator_panel_surface as ivp
from .bot_status_table_surface import COLUMN_LABELS, FIXED_WIDTHS

logger = logging.getLogger("acervator.gui")

METHOD = "simulator_tab.state"

HEADING = "Sim"
ISSUE = 117
BUILT = True

#: The candle window live reads. ``ScrummingBot`` asks ``get_ohlcv`` for 100,
#: and the Simulator reads the same count off the tablet.
WINDOW_CANDLES = 100

#: Below this the voting engine has too few candles for its own formulae.
MIN_CANDLES = 30

PRIVACY_ON_TEXT = "Privacy Mode: ON"
PRIVACY_OFF_TEXT = "Privacy Mode: OFF"
PRIVACY_BUTTON_TEXT = PRIVACY_OFF_TEXT

#: The rows the two strips held on the Trading tab, and the height each keeps.
RESERVED_ROWS: tuple[dict[str, Any], ...] = (
    {"name": "news_ticker_row", "height_px": 24},
    {"name": "data_pool_row", "height_px": 18},
)

FLEET_LABEL_TEXT = "Scrumming Bots"
FLEET_EMPTY_TEXT = "No simulated fleet. Import Live Fleet builds one."
TABLET_LABEL_TEXT = "Tablet:"
NO_TABLET_TEXT = "No Stone Tablet on disk."
SHORT_TABLET_FORMAT = "{asset} {year} holds {count} candles; {need} are needed."

LAYER_INDICATORS = "indicators"
LAYER_PLAYBACK = "playback"
LAYERS = (LAYER_INDICATORS, LAYER_PLAYBACK)

FLIP_BUTTON_TEXT = {
    LAYER_INDICATORS: "Show Playback",
    LAYER_PLAYBACK: "Show Indicators",
}

VWAP_TITLE = "VWAP"
PLAYBACK_TITLE = "Stone Tablet Playback"
REPLAY_LOG_TITLE = "Replay Log"

#: The Trading tab's own pane geometry, cloned. ``trading_tab.py`` sets these.
MARGINS_PX = [2, 2, 2, 2]
SPACING_PX = 2
HANDLE_WIDTH_PX = 5
TOP_SPLITTER_SIZES = [600, 500]
MAIN_SPLITTER_SIZES = [500, 350]
LAYER_SPLITTER_SIZES = [500, 500]

SKIN = {
    "--sim-ground": ds.SURFACE_0,
    "--sim-chart-ground": ds.SURFACE_CHART,
    "--sim-heading-colour": ds.PRIMARY,
    "--sim-body-colour": ds.TEXT_MED,
    "--sim-empty-colour": ds.TEXT_EMPTY_STATE,
    "--sim-outline": ds.OUTLINE,
    "--sim-close-line": ds.TEXT_HIGH,
    "--sim-vwap-line": ds.ACCENT_GOLD,
    "--sim-candle-up": ds.SUCCESS,
    "--sim-candle-down": ds.ERROR,
    "--sim-body-size": f"{ds.TYPE_BODY}px",
    "--sim-caption-size": f"{ds.TYPE_CAPTION}px",
}

DECLARED_FIELDS = (
    "accessible_name",
    "built",
    "fleet",
    "heading",
    "indicators",
    "issue",
    "layer",
    "layers",
    "method",
    "panes",
    "playback",
    "privacy_button",
    "replay_log",
    "reserved_rows",
    "skin",
    "tablet",
    "tablets",
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
    any_revealed = any(
        not state.get(one, False) for one in registry.known_field_ids()
    )
    registry.set_all(any_revealed)
    return any_revealed


def privacy_button(masked: bool) -> dict:
    """The Privacy Mode button's words and the state they report."""
    return {
        "text": PRIVACY_ON_TEXT if masked else PRIVACY_OFF_TEXT,
        "masked": bool(masked),
    }


def fleet_model() -> dict:
    """The bot list: the Trading tab's columns, and no imported fleet."""
    return {
        "label": FLEET_LABEL_TEXT,
        "columns": list(COLUMN_LABELS),
        "column_count": len(COLUMN_LABELS),
        "fixed_widths": {str(key): int(value) for key, value in FIXED_WIDTHS.items()},
        "rows": [],
        "row_count": 0,
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


def multi_tf_summary(candles: Sequence[Sequence[float]], timeframe: str) -> dict:
    """The voting engine's reading of ``candles``, keyed by ``timeframe``.

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
                    "details": {},
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


def playback_payload(candles: Sequence[Sequence[float]]) -> dict:
    """The playback window: one shape per candle, and the price bounds."""
    span = bounds(
        [float(row[2]) for row in candles] + [float(row[3]) for row in candles]
    )
    return {
        "title": PLAYBACK_TITLE,
        "low": span["low"],
        "high": span["high"],
        "candle_count": len(candles),
        "candles": candle_shapes(candles, span["low"], span["high"]),
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


def chosen_entry(source: TabletSource, key: str):
    """The entry ``key`` names, or ``source.newest`` when it names none."""
    if key:
        found = source.entry_for(key)
        if found is not None:
            return found
    return source.newest()


def build_view_model(
    source: TabletSource, key: str = "", layer: str = LAYER_INDICATORS
) -> dict:
    """The whole Sim tab as one dict, read from ``source``."""
    chosen_layer = layer if layer in LAYERS else LAYER_INDICATORS
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
        "built": BUILT,
        "fleet": fleet_model(),
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
        "panes": {
            "margins_px": list(MARGINS_PX),
            "spacing_px": SPACING_PX,
            "handle_width_px": HANDLE_WIDTH_PX,
            "top_splitter_sizes": list(TOP_SPLITTER_SIZES),
            "main_splitter_sizes": list(MAIN_SPLITTER_SIZES),
            "layer_splitter_sizes": list(LAYER_SPLITTER_SIZES),
            "flip_button_text": FLIP_BUTTON_TEXT[chosen_layer],
            "tablet_label_text": TABLET_LABEL_TEXT,
        },
        "playback": playback_payload(drawable),
        "privacy_button": privacy_button(privacy_masked()),
        "replay_log": {
            "title": REPLAY_LOG_TITLE,
            "lines": replay_lines(entry, candles, refusal),
        },
        "reserved_rows": [dict(row) for row in RESERVED_ROWS],
        "skin": dict(SKIN),
        "tablet": None if entry is None else tablet_row(entry),
        "tablets": [tablet_row(one) for one in entries],
        "vwap": vwap_payload(drawable),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``simulator_tab.state``.

    Reads ``tablet`` and ``layer``; an unknown tablet falls back to the newest.
    """
    asked = params if isinstance(params, dict) else {}
    return build_view_model(
        TabletSource(),
        str(asked.get("tablet") or ""),
        str(asked.get("layer") or LAYER_INDICATORS),
    )
