"""The Simulator tab's page view model, forked from ``trading_tab_surface``.

``build_view_model`` is Live's ``trading_tab_surface.build_view_model`` under
``METHOD``, with each layer's corner holding nothing in place of the add button
and a way-in row above the exchange tab bar holding ``way_in_buttons`` while
records are held, ``clear_fleet_button`` then the two ways in the active run
mode offers from ``sim.reserved_rows`` then ``start_run_button``, the Get
Started card carrying the mode's two
buttons in its button position under ``placeholder_title_text`` and
``placeholder_hint_text`` with Clear Fleet above them while ``held`` records
are held, the watchdog and the API-log listener not carried,
and ``replay_layer``, ``flip_button``, ``layer_splitter`` and ``replay_header``
added. ``SimTradingTabState`` owns the run mode, the ``ApiPauseBuffer`` and
``ApiLogPane`` one host reads and the venues it has seated; ``way_in_refused_line``
is the Activity Log line both hosts write for a way-in whose run has not
landed, ``imported_line`` and ``no_stored_bot_line`` the lines Import Live
Fleet writes, ``generated_line``, ``no_target_line``, ``ytd_root_line``,
``ytd_no_pair_line`` and ``ytd_file_missing_line`` the lines Generate From YTD
writes, and ``exchange_choice_options`` and ``exchange_prompt_text``
what ``SimExchangeChoiceDialog`` lists. ``ivp_feed`` and ``rate_snapshot`` are the
voting panel's feed, read by both hosts; ``watchdog_lines`` is the Activity-Log
watchdog's tick over the sim bots, run by both hosts every
``WATCHDOG_INTERVAL_MS``. ``api_block`` and ``api_event_off_thread`` are the
two halves of Live's ``_on_api_event`` both hosts run over their own
``SimApiLog``: the block one entry draws on the API Interaction Log,
and the refusal of an entry recorded off the GUI thread. ``retrieval_api_entry``
and ``ytd_api_entry`` are the two entries that log accepts, one per venue
call of a Stone Tablet retrieval and one per Generate From YTD read.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional, cast

from ...core.fmt import fmt_price_coerced
from ...core.log_paths import get_log_root
from ...exchange.ytd_trade_store import MANIFEST_NAME
from ...simulator import portfolio_battery
from ...simulator.fleet_source import BATTERY_ORIGIN, BOT_STATE_NAME
from ...simulator.read_only_connector import EXCHANGE_ID
from ...simulator.sim_api_log import TABLET_ACTION, YTD_ACTION
from ...simulator.sim_bus import fill_line
from ...simulator.validation import iso_stamp
from ...simulator.ytd_trade_source import ROOT_EMPTY, ROOT_MISSING, ROOT_NO_MANIFEST
from ...trading.container.config import BotState
from ..main_tabs import indicator_panel_surface as panel
from ..main_tabs import simulator_tab_surface as sim
from ..main_tabs import trading_tab_surface as live
from ..main_tabs.main_window_surface import MAIN_THREAD_NAME, api_event_block
from .sim_bot_status_table_surface import base_of, usd_rates

logger = logging.getLogger("acervator.gui")

METHOD = "sim_trading.tab"

TAB_TITLE = sim.HEADING

#: Live's corner button is 24 px tall; the way-in buttons carry no glyph
#: that would set it, so the Qt fork names the height and the page reads it.
WAY_IN_BUTTON_HEIGHT_PX = 24

#: The text each way-in action draws, over every mode's two rows.
WAY_IN_TEXT = {
    row["action"]: row["text"] for rows in sim.ROWS_FOR_MODE.values() for row in rows
}

#: The Activity Log line for a way-in whose run has not landed.
WAY_IN_REFUSED_FORMAT = "{text} refused: {error}"

#: The way-in row above the exchange tab bar, at the corner's own margins and
#: spacing; the tab bar's corner holds nothing.
WAY_IN_ROW_LAYOUT = {"margins_px": [0, 0, 0, 0], "spacing_px": 2}

#: The Get Started card's children, with the run mode's two way-ins where
#: Live's card holds its add button.
PLACEHOLDER_ORDER = ["title", "way_in_buttons", "hint"]

FLIP_BUTTON_NAME = "sim-flip-button"

#: The replay layer's header row, at the panel header's own margins and the
#: panel column's spacing, read from ``indicator_panel_surface`` so the flip
#: button lands at one corner under both layers.
REPLAY_HEADER_LAYOUT = {
    "margins_px": list(cast(list, panel.HEADER["margins_px"])),
    "spacing_px": int(cast(int, panel.CONTAINER["spacing_px"])),
}

#: The ask param carrying the pressed flip button's rect, in the layer stack's
#: coordinates, from either page module to the host.
FLIP_RECT_PARAM = "flip_rect"
FLIP_RECT_KEYS = ("x", "y", "width", "height")

LAYER_SPLITTER = {
    "orientation": "vertical",
    "handle_width_px": sim.HANDLE_WIDTH_PX,
    "children_collapsible": False,
    "children": ["vwap_view", "playback_view"],
    "sizes_px": list(sim.LAYER_SPLITTER_SIZES),
}

WAY_IN_PARAM = "way_in"
REPLAY_LAYER_PARAM = "replay_layer"

#: The Pause Console press on the page makes two asks: ``paused`` on the log
#: method through ``setPaused``, and ``activity_paused`` on this method.
LOG_PAUSED_PARAM = "paused"
ACTIVITY_PAUSED_PARAM = "activity_paused"

#: The Pause API Log press on the page asks ``api_paused`` on this method;
#: each block the API log writer pushes arrives as one of ``api_lines``.
API_PAUSED_PARAM = "api_paused"
API_LINES_PARAM = "api_lines"

#: The file under the runtime log directory an off-thread API entry is written
#: to instead of the pane, one file per day, as Live's writer names it.
THREAD_VIOLATION_FILE_FORMAT = "thread_violation_{day}.log"
THREAD_VIOLATION_LINE_FORMAT = (
    "[{now}] {handler} called on thread={current} (origin={origin}) "
    "— REFUSED to avoid Qt qFatal. Entry action={action}.\n"
)

ACTIONS = {
    "layer.way_in_button.clicked": "way_in",
    "activity_pause_button.toggled": "toggle_activity_pause",
    "api_pause_button.toggled": "toggle_api_pause",
    "flip_button.clicked": "flip_layer",
    "tablet_chooser.changed": "choose_tablet",
    "retrieve_button.clicked": "retrieve_tablet",
}

#: The replay layer's chooser change asks ``tablet`` with the chosen key; its
#: retrieval press asks ``retrieve_tablet``; the host pushes the layer's
#: state as ``replay``.
TABLET_PARAM = "tablet"
RETRIEVE_PARAM = "retrieve_tablet"
REPLAY_PARAM = "replay"

TABLET_LABEL_NAME = "sim-tablet-label"
TABLET_CHOOSER_NAME = "sim-tablet-chooser"
RETRIEVE_BUTTON_NAME = "sim-retrieve-button"

#: The chooser's one width in both builds: the widest file key and the
#: no-tablet item fit, and the layer's header keeps room for the flip under a
#: monospace theme at the window's floor.
TABLET_CHOOSER_WIDTH_PX = 240

#: The Activity Log lines a tablet retrieval writes on both hosts.
RETRIEVAL_STARTED_FORMAT = (
    "Stone Tablet {key}: {verb} {asset}/{quote} {timeframe} candles on "
    "{exchange_id} from {since} to {until}."
)
RETRIEVAL_PROGRESS_FORMAT = (
    "Stone Tablet {key}: {rows} candles received, {first} to {last} ({ms:.0f} ms)."
)
RETRIEVAL_FINISHED_FORMAT = (
    "Stone Tablet {key}: {appended} candles appended over {chunks} chunk(s); "
    "{file} under {root}."
)
RETRIEVAL_REFUSED_FORMAT = (
    "Stone Tablet {key}: {exchange_id} refused after {chunks} chunk(s): {error}; "
    "{appended} candles appended, nothing more written."
)
RETRIEVAL_CURRENT_FORMAT = (
    "Stone Tablet {key} is current to {until}; nothing to retrieve."
)
RETRIEVAL_RUNNING_TEXT = "A Stone Tablet retrieval is in progress; wait for its line."
RETRIEVAL_NO_CHOICE_TEXT = "Choose a Stone Tablet on the replay layer first."
RETRIEVAL_VERB = {True: "Update", False: "Retrieve"}
RETRIEVAL_QUOTE = "USD"

#: The API Interaction Log entry one venue call records, in Live's fields.
RETRIEVAL_ACTION_FORMAT = TABLET_ACTION + " {key}"
RETRIEVAL_REASON_FORMAT = (
    "Get {limit} candles ({timeframe}) for {symbol} since {since} - "
    "Stone Tablet {verb}"
)
RETRIEVAL_RESULT_FORMAT = "{rows} candles received, latest close={close}"
RETRIEVAL_NO_DATA_TEXT = "No data"
RETRIEVAL_ERROR_RESULT_FORMAT = "refused: {error}"
RETRIEVAL_DATA_USAGE_FORMAT = (
    "Appended to Stone Tablet {file} under {root}; the VWAP and Stone Tablet "
    "Playback windows redraw from it"
)
RETRIEVAL_ERROR_USAGE_TEXT = "Nothing written"

#: The API Interaction Log entry one Generate From YTD read records, in
#: Live's fields; ``YTD_ACTION`` is the whole action.
YTD_REASON_FORMAT = "Read the YTD trade files for {exchange} - Generate From YTD"
YTD_RESULT_FORMAT = "{fills} fills read from {files} file(s): {names}"
YTD_DATA_USAGE_FORMAT = "Generated {bots} bot(s) on the Scrumming Bots table"
YTD_NOTHING_GENERATED_TEXT = "Nothing generated"
YTD_MISSING_USAGE_FORMAT = "; {missing} manifest row(s) skipped, file missing"


def clear_fleet_button() -> dict:
    """The way-in row's Clear Fleet button, at the way-in buttons' size."""
    return {
        "action": sim.CLEAR_FLEET_ACTION,
        "text": sim.CLEAR_FLEET_TEXT,
        "accessible_name": sim.button_name(sim.CLEAR_FLEET_ACTION),
        "minimum_width_px": live.ADD_BUTTON_MIN_WIDTH_PX,
        "minimum_height_px": WAY_IN_BUTTON_HEIGHT_PX,
    }


def start_run_button() -> dict:
    """The way-in row's Start Run button, at the way-in buttons' size."""
    return {
        "action": sim.START_RUN_ACTION,
        "text": sim.START_RUN_TEXT,
        "accessible_name": sim.button_name(sim.START_RUN_ACTION),
        "minimum_width_px": live.ADD_BUTTON_MIN_WIDTH_PX,
        "minimum_height_px": WAY_IN_BUTTON_HEIGHT_PX,
    }


def way_in_buttons(mode: str = sim.MODES[0], held: int = 0) -> list:
    """The way-in row's buttons as the page draws them, while ``held``
    records are held: ``clear_fleet_button`` first, then the two ways in
    ``mode`` offers from ``sim.reserved_rows``, then ``start_run_button``;
    an empty list with nothing held, so the row is absent and the card shows."""
    if int(held or 0) <= 0:
        return []
    return (
        [clear_fleet_button()]
        + [
            {
                "action": row["action"],
                "text": row["text"],
                "accessible_name": row["button_name"],
                "minimum_width_px": live.ADD_BUTTON_MIN_WIDTH_PX,
                "minimum_height_px": WAY_IN_BUTTON_HEIGHT_PX,
            }
            for row in sim.reserved_rows(mode)
        ]
        + [start_run_button()]
    )


def way_in_refused_line(action: str, error: Any) -> str:
    """The Activity Log line for ``action`` refused with ``error``: the button's
    text over the ``SendRefused`` ``FleetSource`` raised."""
    return WAY_IN_REFUSED_FORMAT.format(
        text=WAY_IN_TEXT.get(action, action), error=error
    )


#: The Activity Log lines Import Live Fleet writes on both hosts.
IMPORTED_FORMAT = "Imported {count} bot(s) from {file} on {exchange}."
NO_STORED_BOT_FORMAT = "{file} holds no bot to import."
IMPORT_CANCELLED_TEXT = "Import Live Fleet cancelled."

#: The exchange chooser: Live's one-question dialog holding the bot wizard's
#: ``Exchange:`` row, at the dialog width Live gives Configure Profit Wire.
EXCHANGE_CHOICE_TITLE = sim.IMPORT_LIVE_FLEET_TEXT
EXCHANGE_CHOICE_ROW_LABEL = "Exchange:"
EXCHANGE_CHOICE_MIN_WIDTH_PX = 350


def exchange_choice_options(exchanges: Any) -> list:
    """One ``{exchange_id, display_name}`` entry per id in ``exchanges``, the
    shape the bot wizard's ``Exchange:`` combo lists, captioned as the venue
    sub-tab is through ``exchange_display_name``."""
    return [
        {
            "exchange_id": str(eid),
            "display_name": live.exchange_display_name({"exchange_id": str(eid)}),
        }
        for eid in exchanges
        if eid
    ]


def exchange_prompt_text(options: Any) -> str:
    """The chooser's line, ``sim.EXCHANGE_PROMPT_FORMAT`` over the ids in
    ``options``."""
    return sim.EXCHANGE_PROMPT_FORMAT.format(
        options=", ".join(str(one) for one in options)
    )


def imported_line(count: int, exchange_id: Any) -> str:
    """The Activity Log line for ``count`` records copied from
    ``BOT_STATE_NAME`` on ``exchange_id``."""
    return IMPORTED_FORMAT.format(
        count=int(count), file=BOT_STATE_NAME, exchange=exchange_id
    )


def no_stored_bot_line() -> str:
    """The Activity Log line for a ``BOT_STATE_NAME`` naming no bot."""
    return NO_STORED_BOT_FORMAT.format(file=BOT_STATE_NAME)


#: The Activity Log lines Generate From YTD writes on both hosts.
GENERATED_FORMAT = (
    "Generated {count} bot(s) from {files} YTD trade file(s) on {exchange}."
)
NO_TARGET_FORMAT = (
    "{count} of them hold no Target Balance: the fills sold more than they bought."
)
GENERATE_CANCELLED_TEXT = "Generate From YTD cancelled."
YTD_ROOT_MISSING_FORMAT = "No YTD trade directory at {path}."
YTD_ROOT_EMPTY_FORMAT = "{path} holds no YTD trade file."
YTD_ROOT_NO_MANIFEST_FORMAT = "{path} holds no {manifest}."
YTD_NO_PAIR_FORMAT = "{manifest} under {path} names no traded pair."
YTD_FILE_MISSING_FORMAT = (
    "{file} named by {manifest} is missing; {symbol} on {exchange} not generated."
)

#: ``YtdTradeSource.root_state`` answers keyed to the line each one writes.
YTD_ROOT_LINE_FORMATS = {
    ROOT_MISSING: YTD_ROOT_MISSING_FORMAT,
    ROOT_EMPTY: YTD_ROOT_EMPTY_FORMAT,
    ROOT_NO_MANIFEST: YTD_ROOT_NO_MANIFEST_FORMAT,
}


def ytd_root_line(state: str, path: Any) -> str:
    """The Activity Log line for a ``root_state`` that is not ``ROOT_READY``,
    naming ``path``; empty for ``ROOT_READY``."""
    line_format = YTD_ROOT_LINE_FORMATS.get(str(state))
    if line_format is None:
        return ""
    return line_format.format(path=path, manifest=MANIFEST_NAME)


def ytd_no_pair_line(path: Any) -> str:
    """The Activity Log line for a ``MANIFEST_NAME`` under ``path`` naming no
    traded pair."""
    return YTD_NO_PAIR_FORMAT.format(manifest=MANIFEST_NAME, path=path)


def ytd_file_missing_line(entry: Any) -> str:
    """The Activity Log line for a manifest row ``entry`` whose file is absent."""
    return YTD_FILE_MISSING_FORMAT.format(
        file=entry.file,
        manifest=MANIFEST_NAME,
        symbol=entry.symbol,
        exchange=entry.exchange_id,
    )


def generated_line(count: int, files: int, exchange_id: Any) -> str:
    """The Activity Log line for ``count`` records held from ``files`` YTD trade
    files on ``exchange_id``."""
    return GENERATED_FORMAT.format(
        count=int(count), files=int(files), exchange=exchange_id
    )


def no_target_line(count: int) -> str:
    """The Activity Log line for ``count`` generated records holding no Target
    Balance."""
    return NO_TARGET_FORMAT.format(count=int(count))


#: The portfolio chooser: the same one-question dialog with a ``Portfolio:``
#: row over ``PORTFOLIOS`` and a ``Span:`` row over ``BATTERY_SPANS``.
PORTFOLIO_CHOICE_TITLE = sim.RUN_PORTFOLIO_TEXT
EVERY_PORTFOLIO_CHOICE_TITLE = sim.RUN_EVERY_PORTFOLIO_TEXT
PORTFOLIO_CHOICE_ROW_LABEL = sim.PORTFOLIO_LABEL_TEXT
SPAN_CHOICE_ROW_LABEL = sim.SPAN_LABEL_TEXT
PORTFOLIO_PROMPT_TEXT = "Choose the historical portfolio and the span to run."
EVERY_PORTFOLIO_PROMPT_TEXT = "Choose the span every historical portfolio runs over."
PORTFOLIO_OPTION_FORMAT = "{name} — {count} symbols: {description}"

#: The Activity Log lines the Portfolio Battery writes on both hosts.
BATTERY_STARTED_FORMAT = (
    "Portfolio Battery: {subject} over {span}; {bots} bot(s) {origins}; "
    "budget ${budget:,.2f}, the sum of their Target Balances."
)
#: How a plan's per-portfolio origin, ``BATTERY_ORIGIN`` or ``HELD_FLEET``,
#: is spelled on the started line.
BATTERY_ORIGIN_TEXT = {
    BATTERY_ORIGIN: "generated at ${default:,.2f} times each portfolio's mix share",
    portfolio_battery.HELD_FLEET: (
        "loaded from the held fleet at their own Target Balances"
    ),
}
BATTERY_CANCELLED_TEXT = "Portfolio Battery cancelled."
BATTERY_RUNNING_TEXT = "A Portfolio Battery run is in progress; wait for its report."
BATTERY_FAILED_FORMAT = "Portfolio Battery failed: {error}"
EVERY_PORTFOLIO_SUBJECT = "every portfolio"


def portfolio_choice_options(portfolios: Any) -> list:
    """One ``{name, display_name}`` entry per name in ``portfolios``, captioned
    with its symbol count and description through ``PORTFOLIO_OPTION_FORMAT``."""
    return [
        {
            "name": str(name),
            "display_name": PORTFOLIO_OPTION_FORMAT.format(
                name=name,
                count=len(portfolios[name].symbols),
                description=portfolios[name].description or "no description",
            ),
        }
        for name in sorted(portfolios)
    ]


def span_choice_options(spans: Any) -> list:
    """One ``{span, display_name}`` entry per label in ``spans``, in order."""
    return [{"span": str(one), "display_name": str(one)} for one in spans]


def battery_started_line(
    subject: str, span: str, bots: int, origins: Any, budget_usd: float
) -> str:
    """The Activity Log line for a Battery press: ``subject`` over ``span``,
    ``bots`` counted, each origin word in ``origins`` spelled through
    ``BATTERY_ORIGIN_TEXT`` and ``budget_usd``."""
    spelled = " and ".join(
        BATTERY_ORIGIN_TEXT.get(str(one), str(one)).format(
            default=portfolio_battery.DEFAULT_TARGET_USD
        )
        for one in origins
    )
    return BATTERY_STARTED_FORMAT.format(
        subject=subject,
        span=span,
        bots=int(bots),
        origins=spelled or "none",
        budget=float(budget_usd),
    )


def battery_failed_line(error: Any) -> str:
    """The Activity Log line for a Battery run that raised ``error``."""
    return BATTERY_FAILED_FORMAT.format(error=error)


#: The lines the command bar's Start and Stop write in Validation and Back
#: Test modes, when the run they start covers the venue page's scrumming bots.
RUN_MODES = (sim.MODE_VALIDATION, sim.MODE_BACK_TEST)
RUN_STARTED_FORMAT = "{mode} started on {exchange} over {bots} bot(s); {funding}."
RUN_FUNDING_TEXT = {
    sim.MODE_VALIDATION: (
        "budget ${budget:,.2f}, the sum of the held Target Balances; no rerun "
        "fill is refused for cash"
    ),
    sim.MODE_BACK_TEST: "each fold spends its own scrum proceeds",
}
RUN_NO_BOT_FORMAT = "{mode}: no scrumming bot is held on {exchange}; nothing started."
RUN_IN_FLIGHT_FORMAT = (
    "A {mode} run is in flight over {bots} bot(s); Stop on one of its rows ends "
    "it, and {command} waits for it."
)
RUN_STOPPING_FORMAT = (
    "{mode} run stopping at Stop on bot {bot_id}; the partial report follows."
)
RUN_FAILED_FORMAT = "{mode} failed: {error}"
RUN_THREAD_NAME = "sim-mode-run"

#: The signal a Start Run press emits through ``signal_contract``: the press,
#: whose count of the venue's scrumming rows reading ``running`` after must
#: equal the run's bot count on ``START_OUTCOME_STARTED`` under Validation or
#: Back Test and the count before otherwise.
START_PRESSED_SIGNAL = "sim.run.start_pressed"
START_OUTCOME_STARTED = "started"
START_OUTCOME_IN_FLIGHT = "refused_in_flight"
START_OUTCOME_NO_BOT = "no_bot"
START_OUTCOME_CANCELLED = "cancelled"


def rows_running(bots: Any) -> int:
    """How many of ``bots`` carry ``BotState.RUNNING`` as their ``state``."""
    return sum(1 for one in bots if one.state == BotState.RUNNING.value)


def run_started_line(mode: str, exchange_id: Any, bots: int, budget_usd: float) -> str:
    """The Activity Log line for a Start in ``mode``: the exchange, the bot
    count and the mode's funding through ``RUN_FUNDING_TEXT``, the Validation
    text carrying ``budget_usd``."""
    return RUN_STARTED_FORMAT.format(
        mode=sim.MODE_TEXT.get(mode, mode),
        exchange=exchange_id,
        bots=int(bots),
        funding=RUN_FUNDING_TEXT.get(mode, "").format(budget=float(budget_usd)),
    )


def run_no_bot_line(mode: str, exchange_id: Any) -> str:
    """The Activity Log line for a Start in ``mode`` on a page holding no
    scrumming bot."""
    return RUN_NO_BOT_FORMAT.format(
        mode=sim.MODE_TEXT.get(mode, mode), exchange=exchange_id
    )


def run_in_flight_line(mode: str, bots: int, command: str) -> str:
    """The Activity Log line for a bar press other than Stop on a run row
    while a run in ``mode`` is in flight."""
    return RUN_IN_FLIGHT_FORMAT.format(
        mode=sim.MODE_TEXT.get(mode, mode), bots=int(bots), command=str(command)
    )


def run_stopping_line(mode: str, bot_id: Any) -> str:
    """The Activity Log line written when Stop on ``bot_id`` asks a run in
    ``mode`` to end."""
    return RUN_STOPPING_FORMAT.format(mode=sim.MODE_TEXT.get(mode, mode), bot_id=bot_id)


def run_failed_line(mode: str, error: Any) -> str:
    """The Activity Log line for a run in ``mode`` that raised ``error``."""
    return RUN_FAILED_FORMAT.format(mode=sim.MODE_TEXT.get(mode, mode), error=error)


#: Clear Fleet's box, in Live's ``Delete Bot`` shape, and its Activity Log
#: lines on both hosts.
CLEAR_FLEET_BOX_TITLE = sim.CLEAR_FLEET_TEXT
CLEAR_FLEET_QUESTION_FORMAT = (
    "Clear the Simulator fleet of {count} bot(s) on {venues}? This cannot be undone."
)
CLEARED_FORMAT = "Cleared {count} bot(s) on {venues}; the Simulator fleet is empty."
CLEAR_CANCELLED_TEXT = "Clear Fleet cancelled."
NOTHING_HELD_TEXT = "No fleet is held; nothing to clear."
FLEET_CLEARED_NOTICE = "Fleet cleared"

#: The two signals a Clear Fleet press emits through ``signal_contract``: the
#: press, whose held count after must move only on ``CLEAR_OUTCOME_CLEARED``,
#: and the clear, after which nothing is held and no venue is seated.
CLEAR_PRESSED_SIGNAL = "sim.fleet.clear_pressed"
CLEARED_SIGNAL = "sim.fleet.cleared"
CLEAR_OUTCOME_CLEARED = "cleared"
CLEAR_OUTCOME_CANCELLED = "cancelled"
CLEAR_OUTCOME_NOTHING_HELD = "nothing_held"
CLEAR_OUTCOME_IN_FLIGHT = "refused_in_flight"

#: The signal a flip press emits through ``signal_contract``: the pressed
#: button's rect against the previous press's rect, so the way back reads at
#: the way in's position.
LAYER_FLIPPED_SIGNAL = "sim.layer.flipped"


def flip_rect(value: Any) -> Optional[dict]:
    """``value`` as the four integer ``FLIP_RECT_KEYS``, or None when it does
    not carry all four as numbers."""
    if not isinstance(value, dict):
        return None
    try:
        return {key: int(round(float(value[key]))) for key in FLIP_RECT_KEYS}
    except (KeyError, TypeError, ValueError):
        return None


def flipped_pin(leaving: str, shown: str, pressed: Any, previous: Any) -> dict:
    """The ``LAYER_FLIPPED_SIGNAL`` row for one press: ``actual`` the pressed
    rect, ``expected`` the previous press's rect, ``ok`` their equality or
    None on the first press, ``context`` the layer left and the layer shown."""
    return {
        "actual": pressed,
        "expected": previous,
        "ok": None if previous is None or pressed is None else pressed == previous,
        "context": {"from": leaving, "to": shown},
    }


def venues_text(venues: Any) -> str:
    """The venue ids in ``venues`` joined for a line, ``no venue`` for none."""
    joined = ", ".join(str(one) for one in venues if one)
    return joined or "no venue"


def clear_fleet_question(count: int, venues: Any) -> str:
    """The box's question for ``count`` held records on ``venues``."""
    return CLEAR_FLEET_QUESTION_FORMAT.format(
        count=int(count), venues=venues_text(venues)
    )


def cleared_line(count: int, venues: Any) -> str:
    """The Activity Log line for ``count`` records removed from ``venues``."""
    return CLEARED_FORMAT.format(count=int(count), venues=venues_text(venues))


#: The trade line one ``SimTrade`` writes on both hosts: Live's ``SELL FILLED``
#: and ``BUY FILLED`` bot line under the ``[asset/id tail]`` prefix
#: ``MainWindow._on_bot_log`` gives every bot line, at the level it writes at.
TRADE_LINE_LEVEL = "info"
BOT_PREFIX_FORMAT = "[{asset}/{tail}] "
BOT_ID_TAIL_CHARS = 4
TRADE_LINE_FORMAT = "{prefix}{line}"


def bot_prefix(asset: str, bot_id: str) -> str:
    """``[{asset}/{tail}] `` over the last ``BOT_ID_TAIL_CHARS`` of ``bot_id``, as
    ``MainWindow._on_bot_log`` prefixes a bot's line."""
    tail = bot_id[-BOT_ID_TAIL_CHARS:] if len(bot_id) >= BOT_ID_TAIL_CHARS else bot_id
    return BOT_PREFIX_FORMAT.format(asset=asset, tail=tail)


def trade_stamp(trade: Any) -> str:
    """The stamp a trade line carries: ``iso_stamp`` of the trade's ``ts_ms``,
    the candle's time rather than the clock."""
    return iso_stamp(trade.ts_ms)


def trade_line(trade: Any) -> str:
    """``TRADE_LINE_FORMAT`` over one ``SimTrade``: ``bot_prefix`` before
    ``fill_line``, the message the same trade's ``bot.log`` row carries."""
    asset = str(trade.symbol).split("/")[0]
    return TRADE_LINE_FORMAT.format(
        prefix=bot_prefix(asset, str(trade.bot_id)), line=fill_line(trade)
    )


def flip_button(layer: Any) -> dict:
    """The flip button as it reads on ``layer``, with ``other_text`` the word
    it reads on the other layer, so the page reserves one width for both."""
    shown = layer if layer in sim.LAYERS else sim.LAYER_INDICATORS
    other = next(one for one in sim.LAYERS if one != shown)
    return {
        "text": sim.FLIP_BUTTON_TEXT[shown],
        "other_text": sim.FLIP_BUTTON_TEXT[other],
        "name": FLIP_BUTTON_NAME,
    }


def replay_model(feed: Any, choices: Any = (), running: bool = False) -> dict:
    """The replay layer as the page draws it: the ``Tablet:`` label, the
    chooser over ``choices`` with ``feed["key"]`` chosen, the retrieval button
    reading ``feed["button_text"]`` and disabled while ``running``, and the
    two windows' payloads and colours out of ``feed``."""
    held = dict(feed or {})
    return {
        "tablet_label": {"text": sim.TABLET_LABEL_TEXT, "name": TABLET_LABEL_NAME},
        "chooser": {
            "name": TABLET_CHOOSER_NAME,
            "width_px": TABLET_CHOOSER_WIDTH_PX,
            "options": [
                {"key": str(one["key"]), "text": str(one["text"])} for one in choices
            ],
            "chosen": str(held.get("key") or ""),
        },
        "retrieve_button": {
            "text": str(held.get("button_text") or sim.RETRIEVE_TABLET_TEXT),
            "name": RETRIEVE_BUTTON_NAME,
            "enabled": not bool(running),
        },
        "refusal": str(held.get("refusal") or ""),
        "vwap": dict(held.get("vwap") or sim.vwap_payload([])),
        "playback": dict(held.get("playback") or sim.playback_payload([])),
        "colours": dict(held.get("colours") or sim.replay_colours()),
    }


def retrieval_started_line(
    key: str, asset: str, exchange_id: str, on_disk: bool, since_ms: int, until_ms: int
) -> str:
    """The Activity Log line for one retrieval press."""
    return RETRIEVAL_STARTED_FORMAT.format(
        key=key,
        verb=RETRIEVAL_VERB[bool(on_disk)],
        asset=str(asset).upper(),
        quote=RETRIEVAL_QUOTE,
        timeframe=sim.NATIVE_TIMEFRAME,
        exchange_id=exchange_id,
        since=iso_stamp(since_ms),
        until=iso_stamp(until_ms),
    )


def retrieval_current_line(key: str, until_ms: int) -> str:
    """The Activity Log line for a press on a tablet that already holds the
    newest closed candle."""
    return RETRIEVAL_CURRENT_FORMAT.format(key=key, until=iso_stamp(until_ms))


def retrieval_progress_line(key: str, call: Any) -> str:
    """The Activity Log line for one venue call that answered rows."""
    rows = list(getattr(call, "rows", None) or [])
    first = iso_stamp(rows[0][0]) if rows else ""
    last = iso_stamp(rows[-1][0]) if rows else ""
    return RETRIEVAL_PROGRESS_FORMAT.format(
        key=key, rows=len(rows), first=first, last=last, ms=float(call.elapsed_ms)
    )


def retrieval_finished_line(key: str, outcome: Any, file: str, root: Any) -> str:
    """The Activity Log line for a walk that ended, refused or whole."""
    if outcome.refused:
        return RETRIEVAL_REFUSED_FORMAT.format(
            key=key,
            exchange_id=outcome.exchange_id,
            chunks=int(outcome.chunks),
            error=outcome.error,
            appended=int(outcome.candles_appended),
        )
    return RETRIEVAL_FINISHED_FORMAT.format(
        key=key,
        appended=int(outcome.candles_appended),
        chunks=int(outcome.chunks),
        file=file,
        root=root,
    )


def retrieval_api_entry(
    call: Any, key: str, file: str, root: Any, on_disk: bool
) -> dict:
    """One ``APIInteractionLog.record`` call's fields for the venue call
    ``call`` made for the tablet ``key``, in Live's ``get_ohlcv`` phrasing."""
    rows = list(getattr(call, "rows", None) or [])
    error = str(getattr(call, "error", "") or "")
    if error:
        result = RETRIEVAL_ERROR_RESULT_FORMAT.format(error=error)
    elif rows:
        result = RETRIEVAL_RESULT_FORMAT.format(
            rows=len(rows), close=fmt_price_coerced(rows[-1][4])
        )
    else:
        result = RETRIEVAL_NO_DATA_TEXT
    return {
        "exchange": EXCHANGE_ID,
        "action": RETRIEVAL_ACTION_FORMAT.format(key=key),
        "reason": RETRIEVAL_REASON_FORMAT.format(
            limit=int(call.limit),
            timeframe=call.timeframe,
            symbol=call.symbol,
            since=iso_stamp(call.since_ms),
            verb=RETRIEVAL_VERB[bool(on_disk)].lower(),
        ),
        "endpoint": str(call.endpoint),
        "params": {
            "symbol": call.symbol,
            "timeframe": call.timeframe,
            "limit": int(call.limit),
            "since": int(call.since_ms),
        },
        "result": result,
        "elapsed_ms": float(call.elapsed_ms),
        "level": "error" if error else "success",
        "data_usage": (
            RETRIEVAL_ERROR_USAGE_TEXT
            if error
            else RETRIEVAL_DATA_USAGE_FORMAT.format(file=file, root=root)
        ),
    }


def ytd_api_entry(made: Any, exchange_id: Any, root: Any, elapsed_ms: float) -> dict:
    """One ``APIInteractionLog.record`` call's fields for the Generate From YTD
    read ``made``, a ``YtdGeneration``, on ``exchange_id`` under ``root``."""
    names = [str(name) for name in (getattr(made, "files", None) or ())]
    fills = int(getattr(made, "trades_read", 0) or 0)
    bots = len(getattr(made, "bots", None) or ())
    missing = len(getattr(made, "missing", None) or ())
    if names:
        result = YTD_RESULT_FORMAT.format(
            fills=fills, files=len(names), names=", ".join(names)
        )
    else:
        result = RETRIEVAL_NO_DATA_TEXT
    usage = (
        YTD_DATA_USAGE_FORMAT.format(bots=bots) if bots else YTD_NOTHING_GENERATED_TEXT
    )
    if missing:
        usage += YTD_MISSING_USAGE_FORMAT.format(missing=missing)
    return {
        "exchange": str(exchange_id),
        "action": YTD_ACTION,
        "reason": YTD_REASON_FORMAT.format(exchange=exchange_id),
        "endpoint": str(root),
        "params": {"exchange": str(exchange_id), "files": names},
        "result": result,
        "elapsed_ms": float(elapsed_ms),
        "level": "success" if names else "warning",
        "data_usage": usage,
    }


def placeholder_title_text(label: Any) -> str:
    """The Get Started card's heading for one layer: the first step is a fleet."""
    return f"No {label} Fleet Loaded"


def placeholder_hint_text(label: Any) -> str:
    """The line under the Get Started card's buttons for one layer."""
    return f"Load a {label} fleet to begin a run"


#: The prefix ``_NotifyStub.notify`` puts on the line it writes.
NOTIFICATION_PREFIX = "[notification] "


def notification_line(*parts: Any) -> str:
    """The Activity Log line ``_NotifyStub.notify`` writes for a window
    notification, ``NOTIFICATION_PREFIX`` over ``parts`` joined by ``" | "``;
    both Sim hosts hand it to their log's ``notice``."""
    return NOTIFICATION_PREFIX + " | ".join(
        str(one) for one in parts if one is not None
    )


def watchdog_lines(
    state: live.WatchdogState, stats: Any, bots: Any, now: float
) -> list:
    """Live's ``watchdog_tick`` over the sim bots ``bots``: the ``(text, level)``
    lines one tick force-logs, the silence lines needing a running sim bot."""
    running = live.running_bots(bot.state for bot in bots)
    return live.watchdog_tick(state, stats, now, running, running > 0)


def api_block(entry: dict) -> str:
    """Live's ``api_event_block`` over ``entry``, stamped ``hh:mm:ss`` from
    ``entry["timestamp"]`` in local time."""
    stamp = time.strftime("%H:%M:%S", time.localtime(entry["timestamp"]))
    return api_event_block(entry, stamp)


def api_event_off_thread(entry: dict, handler: str, current: str) -> bool:
    """Whether ``current`` is not ``MAIN_THREAD_NAME``; when it is not, one
    ``THREAD_VIOLATION_LINE_FORMAT`` line naming ``handler`` is appended to
    the day's ``THREAD_VIOLATION_FILE_FORMAT`` file under the runtime log
    directory, or logged when that write fails."""
    if current == MAIN_THREAD_NAME:
        return False
    origin = entry.get("_thread_name", "unknown")
    now = datetime.now()
    line = THREAD_VIOLATION_LINE_FORMAT.format(
        now=now.isoformat(),
        handler=handler,
        current=current,
        origin=origin,
        action=entry.get("action"),
    )
    try:
        log_path = get_log_root() / THREAD_VIOLATION_FILE_FORMAT.format(
            day=now.strftime("%Y%m%d")
        )
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        logger.exception(
            "%s called on thread=%s (origin=%s) - REFUSED to avoid Qt qFatal; "
            "the thread_violation log file could not be written",
            handler,
            current,
            origin,
        )
    return True


def card_button_name(action: str) -> str:
    """The accessible name of the Get Started card's button that sends ``action``."""
    return sim.button_name(action) + "-card"


def placeholder_way_in_buttons(
    accent: Any, mode: str = sim.MODES[0], held: int = 0
) -> list:
    """The card's buttons at Live's card-button size and sheet: Clear Fleet
    first while ``held`` records are held, then the two ways in ``mode`` offers."""
    rows = list(sim.reserved_rows(mode))
    if int(held or 0) > 0:
        rows.insert(0, {"action": sim.CLEAR_FLEET_ACTION, "text": sim.CLEAR_FLEET_TEXT})
    return [
        {
            "action": row["action"],
            "text": row["text"],
            "accessible_name": card_button_name(row["action"]),
            "minimum_size_px": list(live.PLACEHOLDER_ADD_MIN_SIZE_PX),
            "style_sheet": live.placeholder_add_style(accent),
            "align": "center",
        }
        for row in rows
    ]


def layer_card(
    key: Any,
    exchanges: Any = None,
    current: Any = None,
    mode: str = sim.MODES[0],
    held: int = 0,
) -> dict:
    """Live's ``layer_card`` with ``way_in_buttons`` and ``way_in_row_layout``
    added, and the Get Started card asking for a fleet.

    The card's ``placeholder`` keeps Live's frame and geometry; its title, its
    hint and its button position carry the Simulator's contents, the button
    position Clear Fleet while ``held`` records are held and the two ways in
    ``mode`` offers. The way-in row's list holds Clear Fleet, the two ways in
    and Start Run while ``held`` records are held, and nothing otherwise.
    """
    card = live.layer_card(key, exchanges, current)
    card["way_in_buttons"] = way_in_buttons(mode, held)
    card["way_in_row_layout"] = dict(WAY_IN_ROW_LAYOUT)
    placeholder = card["placeholder"]
    placeholder["order"] = list(PLACEHOLDER_ORDER)
    placeholder["title"]["text"] = placeholder_title_text(card["label"])
    placeholder["hint"]["text"] = placeholder_hint_text(card["label"])
    placeholder["way_in_buttons"] = placeholder_way_in_buttons(
        card["accent"], mode, held
    )
    del placeholder["add_button"]
    return card


def build_view_model(
    layer: Any = "crypto",
    activity_paused: bool = False,
    api_buffer: Optional[live.ApiPauseBuffer] = None,
    api_pane: Optional[live.ApiLogPane] = None,
    exchanges: Any = None,
    current_exchange: Any = None,
    replay_layer: Any = sim.LAYER_INDICATORS,
    mode: str = sim.MODES[0],
    replay: Optional[dict] = None,
    held: int = 0,
) -> dict:
    """Return the whole Simulator tab state as one serialisable dict.

    ``layer`` names the stack page on show, ``exchanges`` the venues seated,
    ``replay_layer`` which of the panel and the replay layer shows, ``mode``
    the run mode whose two ways in the corner and the card draw, ``replay``
    the layer's chooser, button and two windows as ``replay_model`` builds
    them, and ``held`` how many records the fleet holds, which puts Clear
    Fleet on the card.
    """
    key = "stock" if str(layer) == "stock" else "crypto"
    buffer = live.ApiPauseBuffer() if api_buffer is None else api_buffer
    pane = live.ApiLogPane() if api_pane is None else api_pane
    routed = live.layer_exchanges(exchanges)
    shown = replay_layer if replay_layer in sim.LAYERS else sim.LAYER_INDICATORS
    active = mode if mode in sim.MODES else sim.MODES[0]
    return {
        "tab_title": TAB_TITLE,
        "container": dict(live.CONTAINER),
        "main_splitter": dict(live.MAIN_SPLITTER),
        "top_splitter": dict(live.TOP_SPLITTER),
        "bottom_splitter": dict(live.BOTTOM_SPLITTER),
        "log_splitter": dict(live.LOG_SPLITTER),
        "layer_splitter": dict(LAYER_SPLITTER),
        "equity_exchange_ids": list(live.EQUITY_EXCHANGE_IDS),
        "trading_stack": {
            "pages": list(live.LAYER_ORDER),
            "current_index": live.LAYER_ORDER.index(key),
        },
        "mode": active,
        "held": int(held or 0),
        "layers": [
            layer_card(name, routed[name], current_exchange, active, held)
            for name in live.LAYER_ORDER
        ],
        "alias_layer": live.ALIAS_LAYER,
        "chart_present": live.CHART_PRESENT,
        "replay_layer": shown,
        "replay_header": dict(REPLAY_HEADER_LAYOUT),
        "flip_button": flip_button(shown),
        "replay": dict(replay) if replay else replay_model(None),
        "activity_pane": {
            "layout": dict(live.ACTIVITY_PANE_LAYOUT),
            "header_row": dict(live.HEADER_ROW_LAYOUT),
            "header_row_order": list(live.HEADER_ROW_ORDER),
            "label": {
                "text": live.ACTIVITY_LABEL_TEXT,
                "style_sheet": live.PANE_LABEL_STYLE,
            },
            "pause_button": live.activity_pause_button(activity_paused),
            "status_log": dict(live.STATUS_LOG),
        },
        "api_pane": {
            "layout": dict(live.API_PANE_LAYOUT),
            "header_row": dict(live.HEADER_ROW_LAYOUT),
            "header_row_order": list(live.HEADER_ROW_ORDER),
            "label": {
                "text": live.API_LABEL_TEXT,
                "style_sheet": live.PANE_LABEL_STYLE,
            },
            "pause_button": live.api_pause_button(buffer.paused),
            "pause_buffer": buffer.as_dict(),
            "log_view": {**live.API_LOG_VIEW, **pane.as_dict()},
        },
        "actions": dict(ACTIONS),
    }


class SimTradingTabState:
    """The page state one Simulator tab host owns between asks.

    ``api_buffer`` and ``api_pane`` persist across ``view_model`` calls, which
    reads ``replay_layer`` beside the fields Live's handler reads. ``mode`` is
    the run mode, the first of ``sim.MODES`` at open, the one place the React
    host holds it; ``set_mode`` moves it and answers what it became. ``replay``
    is the replay layer's last ``replay_model``, replaced when a request
    carries ``REPLAY_PARAM``. ``held`` is how many records the fleet holds,
    written by the host before each ``view_model``.
    """

    def __init__(self) -> None:
        self.api_buffer = live.ApiPauseBuffer()
        self.api_pane = live.ApiLogPane()
        self.layer = "crypto"
        self.activity_paused = False
        self.replay_layer = sim.LAYER_INDICATORS
        self.replay: dict = replay_model(None)
        self.exchanges: list = []
        self.current_exchange = ""
        self.mode = sim.MODES[0]
        self.held = 0

    def set_mode(self, mode: Any) -> str:
        """Make ``mode`` the run mode when it is one of ``sim.MODES``; answer
        the run mode in force afterwards."""
        if mode in sim.MODES:
            self.mode = str(mode)
        return self.mode

    def seat(self, exchange_id: str, display_name: str) -> None:
        """Record one venue for the layer stack to draw."""
        for entry in self.exchanges:
            if entry.get("exchange_id") == exchange_id:
                return
        self.exchanges.append(
            {"exchange_id": exchange_id, "display_name": display_name}
        )

    def unseat(self, exchange_id: str) -> None:
        """Forget one venue so the layer stack stops drawing it."""
        self.exchanges = [
            entry for entry in self.exchanges if entry.get("exchange_id") != exchange_id
        ]
        if self.current_exchange == exchange_id:
            self.current_exchange = ""

    def view_model(self, params: Optional[dict] = None) -> dict:
        """Apply one request and return the tab payload."""
        asked = dict(params or {})
        for line in asked.get(API_LINES_PARAM) or []:
            if self.api_buffer.paused:
                self.api_buffer.hold(line)
            else:
                self.api_pane.append(line)
        requested = asked.get(API_PAUSED_PARAM)
        if requested is not None:
            self.api_buffer.toggle(bool(requested), self.api_pane)
        if asked.get("activity_paused") is not None:
            self.activity_paused = bool(asked.get("activity_paused"))
        if asked.get("layer") is not None:
            self.layer = str(asked.get("layer"))
        if asked.get(REPLAY_LAYER_PARAM) in sim.LAYERS:
            self.replay_layer = str(asked.get(REPLAY_LAYER_PARAM))
        if isinstance(asked.get(REPLAY_PARAM), dict):
            self.replay = dict(asked[REPLAY_PARAM])
        if asked.get(live.EXCHANGE_PARAM) is not None:
            self.current_exchange = str(asked.get(live.EXCHANGE_PARAM))
        return build_view_model(
            layer=self.layer,
            activity_paused=self.activity_paused,
            api_buffer=self.api_buffer,
            api_pane=self.api_pane,
            exchanges=self.exchanges,
            current_exchange=self.current_exchange,
            replay_layer=self.replay_layer,
            mode=self.mode,
            replay=self.replay,
            held=self.held,
        )


# -- the voting panel's feed, one definition for both hosts ------------------

#: The page's ask when the bot selector changes, the mirror of ``flip_layer``.
SELECT_BOT_ACTION = "select_bot"
BOT_ID_PARAM = "bot_id"

#: The states the window's ``_ivp_empty_state_cause`` names ``not_running``.
NOT_RUNNING_STATES = (BotState.IDLE.value, BotState.STOPPED.value)
ERROR_STATE = BotState.ERROR.value

#: ``when`` on the staleness banner, as ``_render_stored_reading`` prints it.
STALENESS_WHEN_FORMAT = "%H:%M:%S"

#: The logger line for a phantom timeframe the tablet root does not hold.
PHANTOM_SKIPPED_FORMAT = (
    "Simulator: no Stone Tablet for %s %s on %s; phantom timeframe skipped"
)


def rate_snapshot(statuses: list) -> Any:
    """A ``CurrencyRates`` over ``usd_rates`` of the fleet's own BTC and ETH
    rows, derived by a private ``CurrencyRateMonitor``; ``source`` is the
    exchange of the row that priced BTC, else ETH."""
    from ...exchange.currency_rate_monitor import CurrencyRateMonitor, CurrencyRates

    rates = usd_rates(list(statuses))
    btc = float(rates.get("BTC", 0.0) or 0.0)
    eth = float(rates.get("ETH", 0.0) or 0.0)
    if btc <= 0 and eth <= 0:
        return CurrencyRates()
    source = ""
    for quote in ("BTC", "ETH"):
        for status in statuses:
            if base_of(status.get("symbol", "")) == quote and rates.get(quote):
                source = str(status.get("exchange", "") or "")
                break
        if source:
            break
    return CurrencyRateMonitor().update_from_prices(btc, eth, source=source)


def _tablet_reading(source: Any, entry: Any, timeframe: str) -> tuple:
    """``multi_tf_summary`` over ``window_of`` the tablet, and the window rows."""
    rows = sim.window_of(source.candles(entry))
    return sim.multi_tf_summary(rows, timeframe), rows


def _empty_feed(bot: Any, cause: str, detail: dict, reason: str = "") -> dict:
    """The empty-state answer of ``ivp_feed``: ``cause`` with ``detail``, or ``reason``."""
    return {
        "bot_id": "" if bot is None else bot.bot_id,
        "symbol": "" if bot is None else str(bot.symbol or ""),
        "cause": cause,
        "detail": detail,
        "reason": reason,
    }


def ivp_feed(source: Any, bot: Any, now: Optional[float] = None) -> dict:
    """The voting panel's reading for ``bot`` over the tablet ``tablet_for``
    finds, with each phantom timeframe merged and ``composite_net`` over the
    phantom rows, or the one empty-state cause; a reading carries ``summary``,
    ``stored``, ``when``, ``age`` and ``message`` for ``show_stored``."""
    import time

    from ...trading.ata_gate_scan import composite_net
    from ...trading.phantom_balance import default_phantom_timeframes, tf_rank
    from ..indicator_panel import age_phrase

    if bot is None:
        return _empty_feed(bot, "bot_missing", {})
    detail = {"bot_id": str(bot.bot_id)}
    state = str(bot.state or "").lower()
    if state in NOT_RUNNING_STATES:
        detail["state"] = state
        return _empty_feed(bot, "not_running", detail)
    if state == ERROR_STATE:
        detail["error"] = str(bot.last_error or "")
        return _empty_feed(bot, "bot_error", detail)
    timeframe = str(bot.ta_timeframe or "")
    entry = sim.tablet_for(source, bot.exchange_id, bot.asset, timeframe)
    if entry is None:
        return _empty_feed(bot, "", detail, sim.NO_TABLET_TEXT)
    summary, rows = _tablet_reading(source, entry, timeframe)
    if len(rows) < sim.MIN_CANDLES:
        reason = sim.SHORT_TABLET_FORMAT.format(
            asset=entry.asset, year=entry.year, count=len(rows), need=sim.MIN_CANDLES
        )
        return _empty_feed(bot, "", detail, reason)
    if not summary:
        return _empty_feed(bot, "", detail, sim.NO_TABLET_TEXT)
    parent = summary[timeframe]
    merged: dict = {timeframe: parent}
    phantom_rows: dict = {}
    skipped: list = []
    if bot.phantoms_enabled:
        phantom_tfs = list(bot.phantom_timeframes) or default_phantom_timeframes(
            timeframe
        )
        for phantom_tf in phantom_tfs:
            if phantom_tf == timeframe:
                continue
            phantom_entry = sim.tablet_for(
                source, bot.exchange_id, bot.asset, phantom_tf
            )
            if phantom_entry is None:
                logger.info(
                    PHANTOM_SKIPPED_FORMAT, bot.asset, phantom_tf, bot.exchange_id
                )
                continue
            phantom_summary, _rows = _tablet_reading(source, phantom_entry, phantom_tf)
            if not phantom_summary:
                continue
            merged[phantom_tf] = phantom_summary[phantom_tf]
            if tf_rank(phantom_tf) <= tf_rank(timeframe):
                skipped.append(phantom_tf)
            else:
                phantom_rows[phantom_tf] = phantom_summary[phantom_tf]
    parent["composite_net"] = composite_net(
        phantom_rows, timeframe, parent["net_score"]
    )
    parent["composite_skipped"] = skipped
    taken_at = float(rows[-1][0]) / 1000.0
    moment = time.time() if now is None else float(now)
    symbol = str(bot.symbol or "")
    return {
        "bot_id": bot.bot_id,
        "symbol": symbol,
        "summary": merged,
        "stored": {
            "bot_id": bot.bot_id,
            "symbol": symbol,
            "timeframes": merged,
            "taken_at": taken_at,
        },
        "when": time.strftime(STALENESS_WHEN_FORMAT, time.localtime(taken_at)),
        "age": age_phrase(max(0.0, moment - taken_at)),
        "message": sim.TABLET_ENDS_FORMAT.format(day=sim.iso_day(rows[-1][0])),
        "tablet": entry.file,
        "skipped_phantoms": skipped,
    }
