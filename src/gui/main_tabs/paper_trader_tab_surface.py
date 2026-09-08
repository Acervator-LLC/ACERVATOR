"""paper_trader_tab_surface.py -- the Paper tab as data, read from the live feed.

``build_view_model`` reads one live window through ``LiveFeedSource`` and answers
the Trading-tab clone: the Privacy Mode row, the bot list under
``bot_status_table_surface.COLUMN_LABELS``, the panel ``indicator_panel_surface``
describes, the fake balance and the paper run. ``reserved_rows`` names what the
crypto news ticker and data-pool rows carry, and ``start_run``, ``advance_run``
and ``stop_run`` fill the run pane. ``src.core.desktop_bridge`` registers
``view_model`` under ``METHOD``, and nothing here imports Qt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from ...paper import fake_balance, paper_run
from ...paper.fleet_source import PaperFleetSource, paper_fleet
from ...paper.live_feed_source import (
    READ_NAMES,
    WINDOW_CANDLES,
    LiveFeedSource,
    bar_seconds,
    granularity_for,
    product_id_for,
)
from .. import design_system as ds
from . import indicator_panel_surface as ivp
from .bot_status_table_surface import COLUMN_LABELS, FIXED_WIDTHS

logger = logging.getLogger("acervator.gui")

METHOD = "paper_trader_tab.state"

HEADING = "Paper"
ISSUE = 19
BUILT = True

#: Below this the voting engine has too few candles for its own formulae.
MIN_CANDLES = paper_run.MIN_CANDLES

IDLE = paper_run.IDLE
STARTED = paper_run.STARTED
STOPPED = paper_run.STOPPED

PRIVACY_ON_TEXT = "Privacy Mode: ON"
PRIVACY_OFF_TEXT = "Privacy Mode: OFF"

IMPORT_LIVE_FLEET_ACTION = "import_live_fleet"
START_RUN_ACTION = "start_paper_run"
STOP_RUN_ACTION = "stop_paper_run"
CHOOSE_SYMBOL_ACTION = "choose_symbol"
TOGGLE_PRIVACY_ACTION = "toggle_privacy"

IMPORT_LIVE_FLEET_TEXT = "Import Live Fleet"
START_RUN_TEXT = "Start Paper Run"
STOP_RUN_TEXT = "Stop Paper Run"

NEWS_TICKER_ROW = "news_ticker_row"
DATA_POOL_ROW = "data_pool_row"


def button_name(action: str) -> str:
    """The accessible name both hosts give the button that sends ``action``."""
    return "paper-" + str(action).replace("_", "-")


#: The rows the two strips held on the Trading tab, now the two run buttons.
def reserved_rows(state: str) -> tuple[dict[str, Any], ...]:
    """The two button rows, the second reading Start or Stop for ``state``."""
    running = state == paper_run.STARTED
    return (
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
            "action": STOP_RUN_ACTION if running else START_RUN_ACTION,
            "text": STOP_RUN_TEXT if running else START_RUN_TEXT,
            "button_name": button_name(
                STOP_RUN_ACTION if running else START_RUN_ACTION
            ),
        },
    )


FLEET_LABEL_TEXT = "Paper Bots"
FLEET_EMPTY_TEXT = "No paper fleet. Import Live Fleet builds one."
SYMBOL_LABEL_TEXT = "Market:"
NO_FLEET_TEXT = "No paper fleet yet. Press Import Live Fleet."
NO_SYMBOL_TEXT = "No market chosen."

FEED_TITLE = "Live Feed"
FEED_IDLE_TEXT = "The live feed has not been asked yet."
FEED_REFUSES_FORMAT = (
    "Downstream only. The feed answers {names} and refuses every other name."
)

BALANCE_TITLE = "Fake Balance"
BALANCE_EMPTY_TEXT = "No fake balance is open. Press Start Paper Run."
BALANCE_COLUMNS = (
    "Bot ID",
    "Symbol",
    "Budget",
    "Units",
    "Position",
    "Cash",
    "Tranches",
    "Total",
)

RUN_TITLE = "Paper Run"
RUN_IDLE_TEXT = "No paper run yet. Import Live Fleet, then Start Paper Run."
RUN_COLUMNS = (
    "At",
    "Bot ID",
    "Symbol",
    "Side",
    "Price",
    "Units",
    "USD",
    "Fee",
)

RUN_STATE_TEXT = {
    paper_run.IDLE: "Idle",
    paper_run.STARTED: "Running against the live feed",
    paper_run.STOPPED: "Stopped",
}

#: How many trades the run table lists.
TRADE_ROW_LIMIT = 200

#: The shortest gap between two feed asks, whatever the fleet size.
MIN_TICK_INTERVAL_MS = 2000

#: The Trading tab's own pane geometry, cloned. ``trading_tab.py`` sets these.
MARGINS_PX = [2, 2, 2, 2]
SPACING_PX = 2
HANDLE_WIDTH_PX = 5
TOP_SPLITTER_SIZES = [600, 500]
MAIN_SPLITTER_SIZES = [500, 350]

SKIN = {
    "--paper-ground": ds.SURFACE_0,
    "--paper-heading-colour": ds.PRIMARY,
    "--paper-body-colour": ds.TEXT_MED,
    "--paper-empty-colour": ds.TEXT_EMPTY_STATE,
    "--paper-outline": ds.OUTLINE,
    "--paper-value-colour": ds.TEXT_HIGH,
    "--paper-scrum-colour": ds.SUCCESS,
    "--paper-fold-colour": ds.ACCENT_GOLD,
    "--paper-refused-colour": ds.ERROR,
    "--paper-body-size": f"{ds.TYPE_BODY}px",
    "--paper-caption-size": f"{ds.TYPE_CAPTION}px",
}

DECLARED_FIELDS = (
    "accessible_name",
    "balance",
    "built",
    "feed",
    "fleet",
    "heading",
    "indicators",
    "issue",
    "method",
    "panes",
    "privacy_button",
    "reserved_rows",
    "run",
    "skin",
    "symbol",
    "symbols",
)


def iso_stamp(ts_ms: Any) -> str:
    """``ts_ms`` as a UTC ``YYYY-MM-DDTHH:MM:SSZ`` stamp, empty at or below zero."""
    try:
        stamp = int(ts_ms)
    except (TypeError, ValueError):
        return ""
    if stamp <= 0:
        return ""
    moment = datetime.fromtimestamp(stamp / 1000.0, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def usd_text(amount: Optional[float]) -> str:
    """``amount`` as ``$0.00``, empty when it is None."""
    return "" if amount is None else f"${float(amount):,.2f}"


def units_text(units: Optional[float]) -> str:
    """``units`` to eight places, empty when it is None."""
    return "" if units is None else f"{float(units):.8f}"


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


def fleet_row(bot, balance, trades: int, price: float) -> dict:
    """One paper bot as the bot list draws it, under ``COLUMN_LABELS``."""
    held = None if balance is None else balance.value_usd(price)
    return {
        "bot_id": bot.bot_id,
        "symbol": bot.symbol,
        "origin": bot.origin,
        "cells": [
            bot.bot_id,
            bot.symbol,
            usd_text(held),
            str(trades),
            usd_text(bot.target_usd),
            "",
            "",
            "",
            "",
            "",
        ],
    }


def fleet_model(
    bots: Sequence[Any] = (),
    balances: Optional[dict] = None,
    trades_by_bot: Optional[dict] = None,
    prices: Optional[dict] = None,
) -> dict:
    """The bot list: the Trading tab's columns over ``bots``."""
    open_balances = balances or {}
    counted = trades_by_bot or {}
    seen = prices or {}
    rows = [
        fleet_row(
            one,
            open_balances.get(one.bot_id),
            int(counted.get(one.bot_id, 0)),
            float(seen.get(one.bot_id, 0.0)),
        )
        for one in bots
    ]
    return {
        "label": FLEET_LABEL_TEXT,
        "columns": list(COLUMN_LABELS),
        "column_count": len(COLUMN_LABELS),
        "fixed_widths": {str(key): int(value) for key, value in FIXED_WIDTHS.items()},
        "rows": rows,
        "row_count": len(rows),
        "empty_text": FLEET_EMPTY_TEXT,
    }


def symbol_rows(bots: Sequence[Any]) -> list[dict]:
    """One selector row per distinct market the fleet trades."""
    out: list[dict] = []
    for bot in bots:
        if any(row["symbol"] == bot.symbol for row in out):
            continue
        out.append(
            {
                "symbol": bot.symbol,
                "timeframe": bot.ta_timeframe,
                "exchange_id": bot.exchange_id,
                "product_id": product_id_for(bot.symbol),
            }
        )
    return sorted(out, key=lambda row: row["symbol"])


def chosen_bot(bots: Sequence[Any], symbol: str):
    """The first bot trading ``symbol``, or the first bot of ``bots``."""
    for bot in bots:
        if bot.symbol == symbol:
            return bot
    return bots[0] if bots else None


def multi_tf_summary(candles: Sequence[Any], timeframe: str, symbol: str) -> dict:
    """The voting engine's reading of ``candles``, keyed by ``timeframe``.

    An empty dict comes back when ``compute_all`` raises.
    """
    try:
        from ...trading.ta_engine import VotingEngine

        summary = VotingEngine().compute_all(list(candles), timeframe, symbol=symbol)
    except Exception as exc:  # noqa: BLE001 - a bad window draws the empty state
        logger.warning("Paper: the voting engine refused the window: %s", exc)
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
    candles: Sequence[Any], timeframe: str, symbol: str, refusal: str
) -> dict:
    """The Indicator Voting Panel drawn from ``candles``, or the empty state.

    A non-empty ``refusal`` reaches ``show_no_data`` and no reading is computed.
    """
    model = ivp.IndicatorPanelModel()
    if refusal:
        model.show_no_data(refusal)
        return ivp.build_payload(model)
    summary = multi_tf_summary(candles, timeframe, symbol)
    if not summary:
        model.show_no_data(NO_SYMBOL_TEXT)
        return ivp.build_payload(model)
    model.set_summary(summary, symbol)
    return ivp.build_payload(model)


def feed_payload(feed: Any, bot, candles: Sequence[Any], refusal: str) -> dict:
    """What the Live Feed pane says about the window the panel was drawn from."""
    timeframe = bot.ta_timeframe if bot is not None else ""
    lines = [FEED_REFUSES_FORMAT.format(names=", ".join(READ_NAMES))]
    if bot is None:
        lines.insert(0, NO_FLEET_TEXT)
    elif refusal:
        lines.insert(0, refusal)
    else:
        lines.insert(
            0,
            f"{product_id_for(bot.symbol)} {timeframe} — {len(candles)} candles, "
            f"newest close {usd_text(float(candles[-1].close))}",
        )
    return {
        "title": FEED_TITLE,
        "venue": feed.venue(),
        "symbol": bot.symbol if bot is not None else "",
        "product_id": product_id_for(bot.symbol) if bot is not None else "",
        "timeframe": timeframe,
        "granularity": granularity_for(timeframe) if bot is not None else "",
        "window_candles": WINDOW_CANDLES,
        "candle_count": len(candles),
        "last_price": float(candles[-1].close) if candles else None,
        "last_price_text": usd_text(float(candles[-1].close)) if candles else "",
        "asked_at": iso_stamp(feed.asked_at()),
        "read_names": list(READ_NAMES),
        "refusal": refusal,
        "lines": lines,
        "idle_text": FEED_IDLE_TEXT,
    }


def balance_row(bot, balance, price: float) -> dict:
    """One open ``FakeBalance`` as the Fake Balance table lists it."""
    return {
        "bot_id": bot.bot_id,
        "symbol": bot.symbol,
        "budget_usd": balance.budget_usd,
        "units": balance.units,
        "position_usd": balance.value_usd(price),
        "cash_usd": balance.cash_usd,
        "tranches": balance.tranches,
        "total_usd": balance.total_usd(price),
        "cells": [
            bot.bot_id,
            bot.symbol,
            usd_text(balance.budget_usd),
            units_text(balance.units),
            usd_text(balance.value_usd(price)),
            usd_text(balance.cash_usd),
            str(balance.tranches),
            usd_text(balance.total_usd(price)),
        ],
    }


def balance_payload(run, prices: dict) -> dict:
    """The Fake Balance pane: one row per bot holding a paper balance."""
    rows = []
    if run is not None:
        for bot in run.bots:
            held = run.balances.get(bot.bot_id)
            if held is not None:
                rows.append(balance_row(bot, held, float(prices.get(bot.bot_id, 0.0))))
    return {
        "title": BALANCE_TITLE,
        "columns": list(BALANCE_COLUMNS),
        "currency": fake_balance.CURRENCY,
        "budget_multiple": fake_balance.BUDGET_MULTIPLE,
        "budget_usd": sum(row["budget_usd"] for row in rows),
        "budget_text": usd_text(sum(row["budget_usd"] for row in rows)),
        "rows": rows,
        "row_count": len(rows),
        "empty_text": BALANCE_EMPTY_TEXT,
    }


def trade_row(trade) -> dict:
    """One paper trade as the Paper Run table lists it."""
    return {
        "bot_id": trade.bot_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "at": iso_stamp(trade.wall_ms),
        "candle_at": iso_stamp(trade.candle_ts_ms),
        "price": trade.price,
        "units": trade.units,
        "usd": trade.usd,
        "fee_usd": trade.fee_usd,
        "cells": [
            iso_stamp(trade.wall_ms),
            trade.bot_id,
            trade.symbol,
            trade.side,
            usd_text(trade.price),
            units_text(trade.units),
            usd_text(trade.usd),
            usd_text(trade.fee_usd),
        ],
    }


def run_lines(run) -> list[str]:
    """The fleet, the wall clock and what latched, in the pane's own order."""
    if run is None:
        return [RUN_IDLE_TEXT]
    read = run.summary
    out = [
        f"{read['bots_open']} of {read['bots']} bots opened a fake balance, "
        f"{usd_text(read['budget_usd'])} of paper budget.",
        f"started {iso_stamp(run.started_at_ms)}, "
        f"{read['ticks']} gate-chain evaluations on the wall clock.",
        f"{read['scrum_armed']} scrum latches and {read['fold_armed']} fold latches.",
        f"{read['scrum_trades']} scrum sells and {read['fold_trades']} fold buys "
        f"filled, {usd_text(read['fees_usd'])} in fees.",
    ]
    out.extend(sorted(run.refusals.values()))
    return out


def run_payload(run) -> dict:
    """The Paper Run pane: its state, its counts and the trades it produced."""
    state = run.state if run is not None else paper_run.IDLE
    trades = list(run.trades) if run is not None else []
    return {
        "title": RUN_TITLE,
        "columns": list(RUN_COLUMNS),
        "state": state,
        "state_text": RUN_STATE_TEXT.get(state, RUN_STATE_TEXT[paper_run.IDLE]),
        "running": state == paper_run.STARTED,
        "started_at": iso_stamp(run.started_at_ms) if run is not None else "",
        "summary": run.summary if run is not None else {},
        "lines": run_lines(run),
        "rows": [trade_row(one) for one in trades[-TRADE_ROW_LIMIT:]],
        "row_count": len(trades),
        "buttons": [dict(one) for one in reserved_rows(state)],
    }


def live_fleet(exchange_id: str = "") -> list:
    """The paper fleet read from ``bot_state.json``, narrowed to ``exchange_id``."""
    return paper_fleet(PaperFleetSource(), exchange_id)


def start_run(bots: Sequence[Any]):
    """Mark a run started over ``bots``, asking the feed for nothing yet."""
    return paper_run.start(bots)


def advance_run(run, feed: Any, bot_id: str = "") -> list:
    """Ask the feed for each open bot's newest window and tick it once.

    A ``bot_id`` narrows the pass to that one bot, which is one feed ask.
    """
    return paper_run.advance(run, feed, bot_id)


def tick_interval_ms(run, symbol: str = "") -> int:
    """Milliseconds between two ticks, one bar shared across the open bots.

    A bar is asked for one bot at a time, so no single tick blocks on the whole
    fleet.
    """
    bots = list(run.bots) if run is not None else []
    bot = chosen_bot(bots, str(symbol or ""))
    bar_ms = bar_seconds(bot.ta_timeframe if bot is not None else "") * 1000
    return max(MIN_TICK_INTERVAL_MS, bar_ms // max(1, len(bots)))


def stop_run(run):
    """Mark ``run`` stopped; its balances and trades stay readable."""
    return paper_run.stop(run)


def last_prices(run) -> dict:
    """The newest price each bot ticked at, by ``bot_id``."""
    out: dict[str, float] = {}
    if run is None:
        return out
    for seen in run.ticks:
        if seen.price > 0.0:
            out[seen.bot_id] = seen.price
    return out


def trades_by_bot(run) -> dict:
    """How many paper trades each bot has filled, by ``bot_id``."""
    out: dict[str, int] = {}
    if run is None:
        return out
    for trade in run.trades:
        out[trade.bot_id] = out.get(trade.bot_id, 0) + 1
    return out


def build_view_model(
    feed: Any, bots: Sequence[Any] = (), run=None, symbol: str = ""
) -> dict:
    """The whole Paper tab as one dict, read from ``feed``, ``bots`` and ``run``.

    ``run`` carries the fake balances and the trades, and its own fleet replaces
    ``bots`` once Start Paper Run has opened one.
    """
    fleet = list(run.bots) if run is not None else list(bots)
    bot = chosen_bot(fleet, str(symbol or ""))
    candles = paper_run.candles_for(feed, bot) if bot is not None else []
    refusal = paper_run.refusal_for(bot, candles) if bot is not None else NO_FLEET_TEXT
    prices = last_prices(run)
    if bot is not None and candles:
        prices.setdefault(bot.bot_id, float(candles[-1].close))
    drawable = [] if refusal else candles
    return {
        "accessible_name": HEADING,
        "balance": balance_payload(run, prices),
        "built": BUILT,
        "feed": feed_payload(feed, bot, candles, "" if bot is None else refusal),
        "fleet": fleet_model(
            fleet, getattr(run, "balances", None), trades_by_bot(run), prices
        ),
        "heading": HEADING,
        "indicators": indicator_payload(
            drawable,
            bot.ta_timeframe if bot is not None else "",
            bot.symbol if bot is not None else "",
            refusal,
        ),
        "issue": ISSUE,
        "method": METHOD,
        "panes": {
            "margins_px": list(MARGINS_PX),
            "spacing_px": SPACING_PX,
            "handle_width_px": HANDLE_WIDTH_PX,
            "top_splitter_sizes": list(TOP_SPLITTER_SIZES),
            "main_splitter_sizes": list(MAIN_SPLITTER_SIZES),
            "symbol_label_text": SYMBOL_LABEL_TEXT,
        },
        "privacy_button": privacy_button(privacy_masked()),
        "reserved_rows": [
            dict(row)
            for row in reserved_rows(run.state if run is not None else paper_run.IDLE)
        ],
        "run": run_payload(run),
        "skin": dict(SKIN),
        "symbol": bot.symbol if bot is not None else "",
        "symbols": symbol_rows(fleet),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``paper_trader_tab.state``.

    Reads ``symbol`` and the live fleet; one bridge call holds no run, so the
    Fake Balance and Paper Run panes answer their empty state.
    """
    asked = params if isinstance(params, dict) else {}
    return build_view_model(
        LiveFeedSource(), live_fleet(), None, str(asked.get("symbol") or "")
    )
