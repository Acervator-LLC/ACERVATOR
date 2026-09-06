"""exchange_tab_surface.py -- one per-exchange screen and everything on it.

Describes the screen the operator sees for one exchange. It holds a
Privacy Mode button that hides or shows every masked value at once, a
news strip, a "+ New Bot" button, a data-pool freshness line, two bot
tables with a heading each, and a command bar of five buttons: Start,
Pause, Stop, Restart and Delete.

The two tables are described here only as far as this screen reads them:
which bot went into which table, which row is highlighted, and how many
rows really carry a bot. ``HostedTableModel`` refuses exactly the bot
records the shipped tables refuse, so a screen driven with a bad record
stops in the same place on both sides.

Every check this screen makes on itself is recorded in ``pins`` rather
than sent, so nothing here writes to a log file or to a disk.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``exchange_tab.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ...core.privacy_mask_registry import get_privacy_mask_registry
from .. import design_system as ds
from .bot_status_table_surface import EXCHANGE_ID_PARAM as SCRUM_TABLE_EXCHANGE_PARAM

logger = logging.getLogger("acervator.gui")

METHOD = "exchange_tab.state"

LOGGER_NAME = "acervator.gui"

ACCESSIBLE_NAME = ""

PRIVACY_LABEL_ON = "Privacy Mode: ON"
PRIVACY_LABEL_OFF = "Privacy Mode: OFF"
PRIVACY_TOOLTIP = (
    "Toggle ALL 18 privacy masks at once. When ON, every "
    "registered field (5 KPIs, 5 counters, 7 Bot table "
    "columns, IVP bot selector) renders as **** until the "
    "operator reveals them.\n\n"
    "Per-dot toggles remain available even when this is "
    "OFF — Privacy Mode is a fast 'mask everything' "
    "shortcut for screen-sharing."
)
PRIVACY_STYLE_ON = (
    "QPushButton { "
    f"  background-color: {ds.STATE_ENGAGED}; color: {ds.TEXT_MAX}; "
    "  font-weight: bold; padding: 4px 12px; "
    f"  border: 1px solid {ds.STATE_ARMED}; border-radius: 4px; "
    "}"
)
PRIVACY_STYLE_OFF = (
    "QPushButton { "
    f"  background-color: transparent; color: {ds.TEXT_MED}; "
    "  font-weight: bold; padding: 4px 12px; "
    f"  border: 1px solid {ds.TEXT_PLACEHOLDER}; border-radius: 4px; "
    "}"
)
PRIVACY_FOCUS_POLICY = "NoFocus"
# NoFocus is a word with no meaning outside Qt, so PRIVACY_FOCUSABLE answers it.
PRIVACY_FOCUSABLE = False

NEWS_TICKER_STRETCH = 1
NEWS_TICKER_FAILED_LOG = "news ticker failed to initialise: %s"

ADD_BOT_LABEL = "+ New Bot"
ADD_BOT_ACCENT = True

PULL_RATE_INITIAL_TEXT = "Next data pull: — "
PULL_RATE_STYLE = f"color:{ds.MAIN_BADGE_TEXT}; font-size:11px; padding:2px 6px;"
PULL_RATE_TOOLTIP = (
    "MarketDataPool freshness diagnostic. Slots = number "
    "of distinct (exchange, symbol[, TF]) cache entries. "
    "Freshest = seconds since the most-recently-fetched "
    "slot. Oldest = seconds since the least-recently "
    "fetched slot. Stale = slots past their TTL "
    "(ticker 5s, balance 10s, OHLCV = timeframe). "
    "Cache-hit = coalesced-hits / (hits + fetches). "
    "Coalescing added v3.23.74 (OHLCV) + v3.23.76 (balances) "
    "to fix the CPM saturation the operator flagged 2026-07-31."
)
PULL_RATE_INTERVAL_MS = 1000
PULL_RATE_IDLE_TEXT = "Data pool: idle (no active bots)"
PULL_RATE_AWAITING_FORMAT = (
    "Data pool: {slots} slots · awaiting first " "fetch  ·  cache-hit {hit:.0f}%"
)
PULL_RATE_FULL_FORMAT = (
    "Data pool: {slots} slots "
    "(tick {tick}/ohlcv {ohlcv}/bal {bal})  ·  "
    "freshest {fresh:>4.0f}s  ·  "
    "oldest {old:>4.0f}s  ·  "
    "{stale} stale  ·  cache-hit {hit:.0f}%"
)
PERCENT_SCALE = 100.0
NO_SLOTS = 0
NO_HITS = 0

SCRUM_SECTION_LABEL = "Scrumming Bots"
SCRUM_SECTION_STYLE = (
    f"font-size: 11px; color: {ds.TEXT_MED}; "
    "font-weight: bold; padding: 6px 2px 2px 2px;"
)
EXTRACTOR_SECTION_LABEL = "Extractor Bots"
EXTRACTOR_SECTION_STYLE = (
    f"font-size: 11px; color: {ds.TEXT_MED}; "
    "font-weight: bold; padding: 10px 2px 2px 2px;"
)

COMMAND_BUTTONS = (
    ("Start", "start"),
    ("Pause", "pause"),
    ("Stop", "stop"),
    ("Restart", "restart"),
    ("Delete", "delete"),
)
DANGER_COMMAND_LABEL = "Delete"

DEFAULT_EXCHANGE_ID = "coinbase"
DEFAULT_EXCHANGE_NAME = "Coinbase"

MODE_SCRUMMING = "scrumming"
MODE_EXTRACTOR = "extractor"
NO_MODE = ""

TABLE_SCRUMMING = "scrumming"
TABLE_EXTRACTOR = "extractor"
TABLE_NEITHER = "neither"
DEFAULT_TABLE = TABLE_SCRUMMING

NO_SELECTION_ROW = -1
NO_SELECTION_BOT_ID = ""
NO_BOT_ID = ""

SELECT_FIRST_MESSAGE = "Select a bot first."
SELECT_FIRST_LEVEL = "warning"

PIN_COMMAND_ROUTED = "exchange.15.001.postcondition.command_routed_to_chosen_table"
PIN_EVERY_BOT_DRAWN = "exchange.15.002.invariant.every_bot_reaches_a_table"
PIN_SELECTION_SURVIVES = "exchange.15.003.invariant.selection_survives_refresh"
PIN_PRIVACY_APPLIED = "exchange.15.004.postcondition.privacy_applied_to_every_field"
PIN_PRIVACY_BUTTON = "exchange.15.005.postcondition.privacy_button_matches_registry"
REFRESH_EVERY_S = 30.0
NO_EVERY = 0.0
NO_SELECTION_MOVED = 0

SKIN: dict = {}
STYLE_SHEET = ""
TIMERS = {"pull_rate": PULL_RATE_INTERVAL_MS}
TIMER_DELAYS_MS = (PULL_RATE_INTERVAL_MS,)
BUS_TOPICS: tuple = ()

# One PARAM for each request field ``view_model`` reads off one call.
RESET_PARAM = "reset"
EXCHANGE_ID_PARAM = "exchange_id"
EXCHANGE_NAME_PARAM = "exchange_name"
STATUSES_PARAM = "statuses"
SELECT_SCRUM_PARAM = "select_scrum"
SELECT_EXTRACTOR_PARAM = "select_extractor"
POOL_SUMMARY_PARAM = "pool_summary"
PULL_RATE_PARAM = "pull_rate"
COMMAND_PARAM = "command"
NEW_BOT_PARAM = "new_bot"
PRIVACY_PARAM = "privacy"

ACTIONS = {
    "privacy_clicked": "on_global_privacy_clicked",
    "add_bot_clicked": "on_new_bot_clicked",
    "pull_rate_timeout": "update_pull_rate_label",
    "scrum_selection_changed": "on_scrum_selection_changed",
    "extractor_selection_changed": "on_extractor_selection_changed",
    "command_clicked": "cmd",
}

TAB_BUILT = "tab.built"
NEWS_TICKER_ADDED = "news.added"
NEWS_TICKER_FAILED = "news.failed"
HEADER_STRETCH_ADDED = "news.stretch"
PULL_RATE_UNREADABLE = "pull.unreadable"
PULL_RATE_WRITTEN = "pull.written"
ROUTED = "bots.routed"
SECTIONS_SHOWN = "sections.shown"
COMMAND_REFUSED = "command.refused"
COMMAND_SENT = "command.sent"
BOT_OPENED = "bot.opened"
SIBLING_CLEARED = "sibling.cleared"
NEW_BOT_ASKED = "bot.new"
PRIVACY_FLIPPED = "privacy.flipped"
PRIVACY_UNREADABLE = "privacy.unreadable"
PRIVACY_RESTYLED = "privacy.restyled"
WINDOW_REFRESHED = "window.refreshed"
WINDOW_UNREACHABLE = "window.unreachable"
ROW_REFUSED = "row.refused"
PIN_UNRECORDED = "pin.unrecorded"

TableCall = list

CHECK_STATS = "stats"
CHECK_NUMBERS = "numbers"
CHECK_SYMBOL = "symbol"
CHECK_STATE = "state"

ROW_CHECKS = {
    TABLE_SCRUMMING: (
        (CHECK_STATS, "AttributeError"),
        (CHECK_NUMBERS, "ValueError"),
        (CHECK_SYMBOL, "TypeError"),
        (CHECK_STATE, "AttributeError"),
    ),
    TABLE_EXTRACTOR: (
        (CHECK_STATS, "AttributeError"),
        (CHECK_STATE, "AttributeError"),
    ),
}
REFUSAL_TYPES = {
    "AttributeError": AttributeError,
    "TypeError": TypeError,
    "ValueError": ValueError,
}
CHECKS_BEFORE_FIRST_CELL = (CHECK_STATS, CHECK_NUMBERS, CHECK_SYMBOL)
NUMBER_FIELDS = ("current_holdings", "quote_to_usd", "live_target_balance")
NO_NUMBER = 0.0


def privacy_label(all_masked: bool) -> str:
    """The words on the Privacy Mode button for one register state."""
    return PRIVACY_LABEL_ON if all_masked else PRIVACY_LABEL_OFF


def privacy_style(all_masked: bool) -> str:
    """The colours on the Privacy Mode button for one register state."""
    return PRIVACY_STYLE_ON if all_masked else PRIVACY_STYLE_OFF


def hit_rate_pct(hits: float, fetches: float) -> float:
    """Share of data reads answered from the shared cache, as a percentage."""
    total = hits + fetches
    if total <= 0:
        return 0.0
    return PERCENT_SCALE * hits / total


def pull_rate_text(summary: dict) -> str:
    """The data-pool line under the "+ New Bot" button, for one pool report."""
    tick = summary["ticker_slots"]
    ohlcv = summary["ohlcv_slots"]
    bal = summary.get("balance_slots", NO_SLOTS)
    slots = tick + ohlcv + bal
    if slots <= NO_SLOTS:
        return PULL_RATE_IDLE_TEXT
    fetches = (
        summary["ticker_fetches"]
        + summary["ohlcv_fetches"]
        + summary.get("balance_fetches", NO_HITS)
    )
    hits = (
        summary["ticker_hits"]
        + summary["ohlcv_hits"]
        + summary.get("balance_hits", NO_HITS)
    )
    hit = hit_rate_pct(hits, fetches)
    fresh = summary.get("freshest_age_s")
    old = summary.get("oldest_age_s")
    stale = summary.get("stale_slots", NO_SLOTS)
    if fresh is None:
        return PULL_RATE_AWAITING_FORMAT.format(slots=slots, hit=hit)
    return PULL_RATE_FULL_FORMAT.format(
        slots=slots,
        tick=tick,
        ohlcv=ohlcv,
        bal=bal,
        fresh=fresh,
        old=old,
        stale=stale,
        hit=hit,
    )


def statuses_for(statuses: list, mode: str) -> list:
    """The bot records whose mode names one table, in the order given."""
    return [found for found in statuses if found.get("mode", NO_MODE) == mode]


def check_refuses(status: dict, check: str) -> bool:
    """Whether one named check refuses one bot record."""
    if check == CHECK_STATS:
        return not hasattr(status.get("stats", {}), "get")
    if check == CHECK_NUMBERS:
        for field in NUMBER_FIELDS:
            try:
                float(status.get(field, NO_NUMBER))
            except (TypeError, ValueError):
                return True
        return False
    if check == CHECK_SYMBOL:
        return not isinstance(status.get("symbol", NO_BOT_ID) or NO_BOT_ID, str)
    if check == CHECK_STATE:
        return not isinstance(status.get("state", NO_BOT_ID) or NO_BOT_ID, str)
    return False


def refusing_check(status: dict, kind: str) -> Optional[tuple]:
    """The first check one bot record fails in one table, and its refusal."""
    for check, refusal in ROW_CHECKS[kind]:
        if check_refuses(status, check):
            return (check, refusal)
    return None


class HostedTableModel:
    """One of the two bot tables, as far as this screen reads it.

    ``update_bots`` rewrites every row from one list of bot records and
    puts the highlight back on the bot it was on. A record the table
    cannot draw stops the rewrite where the shipped table stops, leaving
    the rows written so far and the rows the previous list left behind.
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.bot_ids: list = []
        self.drawn: list = []
        self.current_row = NO_SELECTION_ROW
        self.current_column = NO_SELECTION_ROW
        self.has_selection = False
        self.signals_blocked = False
        self.calls: list = []

    def row_count(self) -> int:
        """How many rows the table holds, drawn or blank."""
        return len(self.drawn)

    def set_row_count(self, count: int) -> None:
        """Grow the table with blank rows, or drop the rows past `count`."""
        while len(self.drawn) > count:
            self.drawn.pop()
        while len(self.drawn) < count:
            self.drawn.append(False)

    def drawn_rows(self) -> int:
        """How many rows really carry a bot rather than sitting blank."""
        return sum(1 for found in self.drawn if found)

    def get_selected_bot_id(self) -> str:
        """The bot under the highlight, or nothing when no row is highlighted."""
        if not self.has_selection:
            return NO_SELECTION_BOT_ID
        if not 0 <= self.current_row < len(self.bot_ids):
            return NO_SELECTION_BOT_ID
        return self.bot_ids[self.current_row]

    def selected_items(self) -> bool:
        """Whether any row is highlighted."""
        return self.has_selection

    def select_row(self, row: int) -> None:
        """Put the highlight on one row."""
        self.current_row = row
        self.has_selection = 0 <= row < len(self.drawn) and self.drawn[row]

    def clear_selection(self) -> None:
        """Take the highlight off every row."""
        self.has_selection = False

    def set_current_cell(self, row: int, column: int) -> None:
        """Move the focus the highlight is anchored to."""
        self.current_row = row
        self.current_column = column
        if row == NO_SELECTION_ROW:
            self.has_selection = False

    def block_signals(self, blocked: bool) -> bool:
        """Stop or restart this table telling the screen its highlight moved."""
        was = self.signals_blocked
        self.signals_blocked = blocked
        return was

    def update_bots(self, statuses: list) -> None:
        """Rewrite every row from one list of bot records."""
        selected_before = self.get_selected_bot_id()
        self.set_row_count(len(statuses))
        self.bot_ids = []
        for row, status in enumerate(statuses):
            self.bot_ids.append(status.get("bot_id", NO_BOT_ID))
            found = refusing_check(status, self.kind)
            if found is not None:
                check, refusal = found
                if check not in CHECKS_BEFORE_FIRST_CELL:
                    self.drawn[row] = True
                self.calls.append([ROW_REFUSED, self.kind, refusal])
                raise REFUSAL_TYPES[refusal](refusal)
            self.drawn[row] = True
        self.reanchor(selected_before)

    def reanchor(self, previous_bot_id: str) -> None:
        """Put the highlight back on the bot it was on, not on its row."""
        if not previous_bot_id:
            return
        if self.get_selected_bot_id() == previous_bot_id:
            return
        target = None
        for row, bot_id in enumerate(self.bot_ids):
            if bot_id == previous_bot_id:
                target = row
                break
        if target is not None and not self.drawn[target]:
            target = None
        was = self.block_signals(True)
        try:
            self.clear_selection()
            if target is None:
                self.set_current_cell(NO_SELECTION_ROW, 0)
            else:
                self.set_current_cell(target, 0)
                self.select_row(target)
        finally:
            self.block_signals(was)


class ExchangeTabModel:
    """One exchange screen: its header, its two tables and its command bar.

    ``update_bots`` routes one fleet list to the two tables and shows or
    hides each section. ``cmd`` sends one of the five commands to the bot
    the operator highlighted. ``on_global_privacy_clicked`` flips every
    registered mask at once. Every step is appended to ``calls``, and
    every check the screen makes on itself is appended to ``pins``.
    """

    def __init__(
        self,
        exchange_id: str,
        exchange_name: str,
        on_new_bot=None,
        on_bot_clicked=None,
        on_bot_cmd=None,
        on_bot_fire=None,
        status_log=None,
        news_ticker_factory=None,
        pool_reader=None,
        window_refresh=None,
    ) -> None:
        self.exchange_id = exchange_id
        self.exchange_name = exchange_name
        self.on_new_bot = on_new_bot
        self.on_bot_clicked = on_bot_clicked
        self.on_bot_cmd = on_bot_cmd
        self.on_bot_fire = on_bot_fire
        self.status_log = status_log
        self.news_ticker_factory = news_ticker_factory
        self.pool_reader = pool_reader
        self.window_refresh = window_refresh
        self.calls: list = []
        self.pins: list = []
        self.logged: list = []
        self.new_bot_asks: list = []
        self.bot_opens: list = []
        self.commands_sent: list = []
        self.privacy_label_text = PRIVACY_LABEL_OFF
        self.privacy_style_sheet = PRIVACY_STYLE_OFF
        self.pull_rate_label_text = PULL_RATE_INITIAL_TEXT
        self.news_ticker = None
        self.news_ticker_started = 0
        self.header_stretch = False
        self.scrum_section_visible = False
        self.extractor_section_visible = False
        self.scrum_table = HostedTableModel(TABLE_SCRUMMING)
        self.extractor_table = HostedTableModel(TABLE_EXTRACTOR)
        self.last_clicked_table = DEFAULT_TABLE
        self.build_news_ticker()
        self.refresh_privacy_mode_btn_style()
        self.calls.append([TAB_BUILT, exchange_id])

    # ----- header -----

    def build_news_ticker(self) -> None:
        """Put the news strip between the Privacy button and "+ New Bot".

        A strip that cannot be built leaves plain space in its place, so
        the two buttons keep their positions.
        """
        if self.news_ticker_factory is None:
            self.header_stretch = True
            self.calls.append([HEADER_STRETCH_ADDED])
            return
        try:
            self.news_ticker = self.news_ticker_factory()
            self.news_ticker_started += 1
        except Exception as exc:
            logger.debug(NEWS_TICKER_FAILED_LOG, exc)
            self.news_ticker = None
            self.header_stretch = True
            self.calls.append([NEWS_TICKER_FAILED, type(exc).__name__])
            self.calls.append([HEADER_STRETCH_ADDED])
            return
        self.calls.append([NEWS_TICKER_ADDED, NEWS_TICKER_STRETCH])

    def on_new_bot_clicked(self) -> None:
        """Ask the window for a new bot on this exchange."""
        if not self.on_new_bot:
            return
        self.new_bot_asks.append(self.exchange_id)
        self.calls.append([NEW_BOT_ASKED, self.exchange_id])
        self.on_new_bot(self.exchange_id)

    def update_pull_rate_label(self) -> None:
        """Rewrite the data-pool freshness line under the "+ New Bot" button."""
        try:
            summary = self.pool_reader() if self.pool_reader else None
        except Exception:
            self.calls.append([PULL_RATE_UNREADABLE])
            return
        if summary is None:
            self.calls.append([PULL_RATE_UNREADABLE])
            return
        self.pull_rate_label_text = pull_rate_text(summary)
        self.calls.append([PULL_RATE_WRITTEN, self.pull_rate_label_text])

    # ----- the two tables -----

    def scrum_clicked(self, bot_id: str) -> None:
        """A Detail button on the Scrumming table was pressed."""
        self.last_clicked_table = TABLE_SCRUMMING
        self.bot_opens.append(bot_id)
        self.calls.append([BOT_OPENED, TABLE_SCRUMMING])
        if self.on_bot_clicked:
            self.on_bot_clicked(bot_id)

    def extractor_clicked(self, bot_id: str) -> None:
        """A Detail button on the Extractor table was pressed."""
        self.last_clicked_table = TABLE_EXTRACTOR
        self.bot_opens.append(bot_id)
        self.calls.append([BOT_OPENED, TABLE_EXTRACTOR])
        if self.on_bot_clicked:
            self.on_bot_clicked(bot_id)

    def on_scrum_selection_changed(self) -> None:
        """A Scrumming row was highlighted, so the Extractor one is cleared."""
        if not self.scrum_table.selected_items():
            return
        self.last_clicked_table = TABLE_SCRUMMING
        was = self.extractor_table.block_signals(True)
        self.extractor_table.clear_selection()
        self.extractor_table.set_current_cell(NO_SELECTION_ROW, NO_SELECTION_ROW)
        self.extractor_table.block_signals(was)
        self.calls.append([SIBLING_CLEARED, TABLE_EXTRACTOR])

    def on_extractor_selection_changed(self) -> None:
        """An Extractor row was highlighted, so the Scrumming one is cleared."""
        if not self.extractor_table.selected_items():
            return
        self.last_clicked_table = TABLE_EXTRACTOR
        was = self.scrum_table.block_signals(True)
        self.scrum_table.clear_selection()
        self.scrum_table.set_current_cell(NO_SELECTION_ROW, NO_SELECTION_ROW)
        self.scrum_table.block_signals(was)
        self.calls.append([SIBLING_CLEARED, TABLE_SCRUMMING])

    def select_scrum_row(self, row: int) -> None:
        """Highlight one Scrumming row the way an operator click does."""
        self.scrum_table.select_row(row)
        self.on_scrum_selection_changed()

    def select_extractor_row(self, row: int) -> None:
        """Highlight one Extractor row the way an operator click does."""
        self.extractor_table.select_row(row)
        self.on_extractor_selection_changed()

    def update_bots(self, statuses: list) -> None:
        """Route one fleet list to the two tables and show or hide each section."""
        selected_before = (
            self.scrum_table.get_selected_bot_id(),
            self.extractor_table.get_selected_bot_id(),
        )
        scrum_statuses = statuses_for(statuses, MODE_SCRUMMING)
        extractor_statuses = statuses_for(statuses, MODE_EXTRACTOR)
        self.scrum_table.update_bots(scrum_statuses)
        self.extractor_table.update_bots(extractor_statuses)
        self.scrum_section_visible = bool(scrum_statuses)
        self.extractor_section_visible = bool(extractor_statuses)
        self.calls.append([ROUTED, len(scrum_statuses), len(extractor_statuses)])
        self.calls.append(
            [SECTIONS_SHOWN, self.scrum_section_visible, self.extractor_section_visible]
        )
        scrum_drawn = self.scrum_table.drawn_rows()
        extractor_drawn = self.extractor_table.drawn_rows()
        selected_after = (
            self.scrum_table.get_selected_bot_id(),
            self.extractor_table.get_selected_bot_id(),
        )
        moved = [
            bool(was and now and was != now)
            for was, now in zip(selected_before, selected_after)
        ]
        self.pins.append(
            {
                "name": PIN_EVERY_BOT_DRAWN,
                "actual": scrum_drawn + extractor_drawn,
                "expected": len(statuses),
                "every": REFRESH_EVERY_S,
                "instance": self.exchange_id,
                "context": {
                    "exchange": self.exchange_id,
                    "scrumming_rows": scrum_drawn,
                    "extractor_rows": extractor_drawn,
                    "routed_scrumming": len(scrum_statuses),
                    "routed_extractor": len(extractor_statuses),
                },
            }
        )
        self.pins.append(
            {
                "name": PIN_SELECTION_SURVIVES,
                "actual": sum(moved),
                "expected": NO_SELECTION_MOVED,
                "every": REFRESH_EVERY_S,
                "instance": self.exchange_id,
                "context": {
                    "exchange": self.exchange_id,
                    "scrumming_selection_moved": moved[0],
                    "extractor_selection_moved": moved[1],
                    "selections_before": sum(1 for found in selected_before if found),
                    "selections_after": sum(1 for found in selected_after if found),
                    "preferred_table": self.last_clicked_table,
                    "scrumming_rows": scrum_drawn,
                    "extractor_rows": extractor_drawn,
                },
            }
        )

    # ----- the command bar -----

    def cmd(self, command: str) -> None:
        """Send one command to the bot the operator highlighted."""
        if self.last_clicked_table == TABLE_EXTRACTOR:
            bot_id = self.extractor_table.get_selected_bot_id()
            if not bot_id:
                bot_id = self.scrum_table.get_selected_bot_id()
        else:
            bot_id = self.scrum_table.get_selected_bot_id()
            if not bot_id:
                bot_id = self.extractor_table.get_selected_bot_id()
        if not bot_id:
            if self.status_log:
                self.logged.append([SELECT_FIRST_MESSAGE, SELECT_FIRST_LEVEL])
                self.status_log.log(SELECT_FIRST_MESSAGE, SELECT_FIRST_LEVEL)
            self.calls.append([COMMAND_REFUSED, command])
            return
        chosen = self.last_clicked_table
        scrum_selected = self.scrum_table.get_selected_bot_id()
        extractor_selected = self.extractor_table.get_selected_bot_id()
        if chosen == TABLE_EXTRACTOR:
            came_from = (
                TABLE_EXTRACTOR
                if bot_id == extractor_selected
                else TABLE_SCRUMMING if bot_id == scrum_selected else TABLE_NEITHER
            )
        else:
            came_from = (
                TABLE_SCRUMMING
                if bot_id == scrum_selected
                else TABLE_EXTRACTOR if bot_id == extractor_selected else TABLE_NEITHER
            )
        self.pins.append(
            {
                "name": PIN_COMMAND_ROUTED,
                "actual": came_from,
                "expected": chosen,
                "every": NO_EVERY,
                "instance": None,
                "context": {
                    "exchange": self.exchange_id,
                    "command": command,
                    "scrumming_selected": bool(scrum_selected),
                    "extractor_selected": bool(extractor_selected),
                    "fell_back": came_from != chosen,
                },
            }
        )
        if self.on_bot_cmd:
            self.commands_sent.append([bot_id, command])
            self.calls.append([COMMAND_SENT, command, came_from])
            self.on_bot_cmd(bot_id, command)

    # ----- Privacy Mode -----

    def on_global_privacy_clicked(self) -> None:
        """Flip every registered privacy mask in one shot."""
        try:
            registry = get_privacy_mask_registry()
            snapshot = registry.to_dict()
            any_revealed = any(
                not snapshot.get(field_id, False)
                for field_id in registry.known_field_ids()
            )
            registry.set_all(any_revealed)
        except Exception:
            self.calls.append([PRIVACY_UNREADABLE])
            return
        self.calls.append([PRIVACY_FLIPPED, bool(any_revealed)])
        try:
            registry = get_privacy_mask_registry()
            field_ids = registry.known_field_ids()
            state = registry.to_dict()
            applied = sum(
                1
                for field_id in field_ids
                if bool(state.get(field_id, False)) is bool(any_revealed)
            )
            self.pins.append(
                {
                    "name": PIN_PRIVACY_APPLIED,
                    "actual": applied,
                    "expected": len(field_ids),
                    "every": NO_EVERY,
                    "instance": None,
                    "context": {
                        "exchange": self.exchange_id,
                        "masking": bool(any_revealed),
                        "fields_declared": len(field_ids),
                        "fields_left_behind": len(field_ids) - applied,
                    },
                }
            )
        except Exception:
            self.calls.append([PIN_UNRECORDED, PIN_PRIVACY_APPLIED])
        self.refresh_privacy_mode_btn_style()
        try:
            registry = get_privacy_mask_registry()
            shown_on = PRIVACY_LABEL_ON.endswith("ON") and "ON" in (
                self.privacy_label_text
            )
            field_ids = registry.known_field_ids()
            state = registry.to_dict()
            all_masked = all(bool(state.get(field_id, False)) for field_id in field_ids)
            self.pins.append(
                {
                    "name": PIN_PRIVACY_BUTTON,
                    "actual": shown_on,
                    "expected": all_masked,
                    "every": NO_EVERY,
                    "instance": None,
                    "context": {
                        "exchange": self.exchange_id,
                        "masking": bool(any_revealed),
                        "fields_declared": len(field_ids),
                    },
                }
            )
        except Exception:
            self.calls.append([PIN_UNRECORDED, PIN_PRIVACY_BUTTON])
        try:
            if self.window_refresh is not None:
                self.window_refresh()
                self.calls.append([WINDOW_REFRESHED])
            else:
                self.calls.append([WINDOW_UNREACHABLE])
        except Exception:
            self.calls.append([WINDOW_UNREACHABLE])

    def refresh_privacy_mode_btn_style(self) -> None:
        """Rewrite the Privacy Mode button from the register's own answer."""
        try:
            registry = get_privacy_mask_registry()
            all_masked = all(
                registry.is_masked(field_id) for field_id in registry.known_field_ids()
            )
        except Exception:
            all_masked = False
        self.privacy_label_text = privacy_label(all_masked)
        self.privacy_style_sheet = privacy_style(all_masked)
        self.calls.append([PRIVACY_RESTYLED, all_masked])


PANE_MODEL: Optional[ExchangeTabModel] = None

PANE_MODELS: Dict[str, ExchangeTabModel] = {}


def pane_model() -> ExchangeTabModel:
    """The one screen the bridge keeps between calls.

    Built on the first request, never at import: building one reads the
    privacy register, and the register reads the operator's settings
    file the first time anything asks for it.
    """
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = ExchangeTabModel(DEFAULT_EXCHANGE_ID, DEFAULT_EXCHANGE_NAME)
    return PANE_MODEL


def pane_model_for(exchange_id: str, exchange_name: str) -> ExchangeTabModel:
    """The screen ``PANE_MODELS`` keeps for one exchange.

    One ``ExchangeTabModel`` per exchange id, so two screens on the same
    page do not share a selection, a privacy state or a table.
    """
    held = PANE_MODELS.get(exchange_id)
    if held is None:
        held = ExchangeTabModel(exchange_id, exchange_name)
        PANE_MODELS[exchange_id] = held
    return held


def build_model(
    exchange_id: str = DEFAULT_EXCHANGE_ID,
    exchange_name: str = DEFAULT_EXCHANGE_NAME,
    statuses: Optional[list] = None,
    **wiring,
) -> ExchangeTabModel:
    """One screen driven from one fleet list."""
    model = ExchangeTabModel(exchange_id, exchange_name, **wiring)
    if statuses is not None:
        model.update_bots(statuses)
    return model


def table_view(table: HostedTableModel) -> dict:
    """One hosted table as the screen reads it."""
    return {
        "kind": table.kind,
        "bot_ids": list(table.bot_ids),
        "drawn": list(table.drawn),
        "row_count": table.row_count(),
        "drawn_rows": table.drawn_rows(),
        "current_row": table.current_row,
        "current_column": table.current_column,
        "has_selection": table.has_selection,
        "selected_bot_id": table.get_selected_bot_id(),
        "signals_blocked": table.signals_blocked,
        "calls": [list(call) for call in table.calls],
    }


def build_view_model(model: ExchangeTabModel) -> dict:
    """Return the whole surface state as one serialisable dict."""
    return {
        "method": METHOD,
        "accessible_name": ACCESSIBLE_NAME,
        "exchange_id": model.exchange_id,
        "exchange_name": model.exchange_name,
        "privacy_label": model.privacy_label_text,
        "privacy_label_on": PRIVACY_LABEL_ON,
        "privacy_label_off": PRIVACY_LABEL_OFF,
        "privacy_tooltip": PRIVACY_TOOLTIP,
        "privacy_style": model.privacy_style_sheet,
        "privacy_style_on": PRIVACY_STYLE_ON,
        "privacy_style_off": PRIVACY_STYLE_OFF,
        "privacy_focus_policy": PRIVACY_FOCUS_POLICY,
        "privacy_focusable": PRIVACY_FOCUSABLE,
        "news_ticker_stretch": NEWS_TICKER_STRETCH,
        "news_ticker_failed_log": NEWS_TICKER_FAILED_LOG,
        "news_ticker_built": model.news_ticker is not None,
        "news_ticker_started": model.news_ticker_started,
        "header_stretch": model.header_stretch,
        "add_bot_label": ADD_BOT_LABEL,
        "add_bot_accent": ADD_BOT_ACCENT,
        "new_bot_asks": list(model.new_bot_asks),
        "pull_rate_text": model.pull_rate_label_text,
        "pull_rate_initial_text": PULL_RATE_INITIAL_TEXT,
        "pull_rate_style": PULL_RATE_STYLE,
        "pull_rate_tooltip": PULL_RATE_TOOLTIP,
        "pull_rate_interval_ms": PULL_RATE_INTERVAL_MS,
        "pull_rate_idle_text": PULL_RATE_IDLE_TEXT,
        "pull_rate_awaiting_format": PULL_RATE_AWAITING_FORMAT,
        "pull_rate_full_format": PULL_RATE_FULL_FORMAT,
        "percent_scale": PERCENT_SCALE,
        "no_slots": NO_SLOTS,
        "no_hits": NO_HITS,
        "scrum_section_label": SCRUM_SECTION_LABEL,
        "scrum_section_style": SCRUM_SECTION_STYLE,
        "scrum_section_visible": model.scrum_section_visible,
        "extractor_section_label": EXTRACTOR_SECTION_LABEL,
        "extractor_section_style": EXTRACTOR_SECTION_STYLE,
        "extractor_section_visible": model.extractor_section_visible,
        "command_buttons": [list(pair) for pair in COMMAND_BUTTONS],
        "danger_command_label": DANGER_COMMAND_LABEL,
        "commands_sent": [list(sent) for sent in model.commands_sent],
        "scrum_table": table_view(model.scrum_table),
        "extractor_table": table_view(model.extractor_table),
        "last_clicked_table": model.last_clicked_table,
        "default_table": DEFAULT_TABLE,
        "table_scrumming": TABLE_SCRUMMING,
        "table_extractor": TABLE_EXTRACTOR,
        "table_neither": TABLE_NEITHER,
        "mode_scrumming": MODE_SCRUMMING,
        "mode_extractor": MODE_EXTRACTOR,
        "no_mode": NO_MODE,
        "default_exchange_id": DEFAULT_EXCHANGE_ID,
        "default_exchange_name": DEFAULT_EXCHANGE_NAME,
        "no_selection_row": NO_SELECTION_ROW,
        "no_selection_bot_id": NO_SELECTION_BOT_ID,
        "no_bot_id": NO_BOT_ID,
        "no_number": NO_NUMBER,
        "select_first_message": SELECT_FIRST_MESSAGE,
        "select_first_level": SELECT_FIRST_LEVEL,
        "logged": [list(line) for line in model.logged],
        "bot_opens": list(model.bot_opens),
        "pins": [dict(pin) for pin in model.pins],
        "pin_command_routed": PIN_COMMAND_ROUTED,
        "pin_every_bot_drawn": PIN_EVERY_BOT_DRAWN,
        "pin_selection_survives": PIN_SELECTION_SURVIVES,
        "pin_privacy_applied": PIN_PRIVACY_APPLIED,
        "pin_privacy_button": PIN_PRIVACY_BUTTON,
        "refresh_every_s": REFRESH_EVERY_S,
        "no_every": NO_EVERY,
        "no_selection_moved": NO_SELECTION_MOVED,
        "row_checks": {
            kind: [list(pair) for pair in checks] for kind, checks in ROW_CHECKS.items()
        },
        "checks_before_first_cell": list(CHECKS_BEFORE_FIRST_CELL),
        "number_fields": list(NUMBER_FIELDS),
        "check_stats": CHECK_STATS,
        "check_numbers": CHECK_NUMBERS,
        "check_symbol": CHECK_SYMBOL,
        "check_state": CHECK_STATE,
        "refusal_types": sorted(REFUSAL_TYPES),
        "skin": dict(SKIN),
        "style_sheet": STYLE_SHEET,
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "actions": dict(ACTIONS),
        "reset_param": RESET_PARAM,
        "scrum_table_exchange_param": SCRUM_TABLE_EXCHANGE_PARAM,
        "exchange_id_param": EXCHANGE_ID_PARAM,
        "exchange_name_param": EXCHANGE_NAME_PARAM,
        "statuses_param": STATUSES_PARAM,
        "pool_summary_param": POOL_SUMMARY_PARAM,
        "select_scrum_param": SELECT_SCRUM_PARAM,
        "select_extractor_param": SELECT_EXTRACTOR_PARAM,
        "pull_rate_param": PULL_RATE_PARAM,
        "command_param": COMMAND_PARAM,
        "new_bot_param": NEW_BOT_PARAM,
        "privacy_param": PRIVACY_PARAM,
        "logger_name": LOGGER_NAME,
        "calls": [list(call) for call in model.calls],
    }


def drive(model: ExchangeTabModel, params: dict) -> dict:
    """Apply one request to ``model``, reading each ``*_PARAM`` field.

    ``view_model`` and ``live_view_model`` both run their request here.
    """
    statuses = params.get(STATUSES_PARAM)
    if statuses is not None:
        model.update_bots(statuses)
    if params.get(SELECT_SCRUM_PARAM) is not None:
        model.select_scrum_row(params[SELECT_SCRUM_PARAM])
    if params.get(SELECT_EXTRACTOR_PARAM) is not None:
        model.select_extractor_row(params[SELECT_EXTRACTOR_PARAM])
    if params.get(POOL_SUMMARY_PARAM) is not None:
        summary = params[POOL_SUMMARY_PARAM]
        model.pool_reader = lambda: summary
        model.update_pull_rate_label()
    if params.get(PULL_RATE_PARAM, False):
        model.update_pull_rate_label()
    if params.get(COMMAND_PARAM) is not None:
        model.cmd(params[COMMAND_PARAM])
    if params.get(NEW_BOT_PARAM, False):
        model.on_new_bot_clicked()
    if params.get(PRIVACY_PARAM, False):
        model.on_global_privacy_clicked()
    return build_view_model(model)


def view_model(params: dict) -> dict:
    """Bridge handler reading each request field a ``*_PARAM`` constant names."""
    global PANE_MODEL
    if params.get(RESET_PARAM, False):
        PANE_MODEL = ExchangeTabModel(
            params.get(EXCHANGE_ID_PARAM, DEFAULT_EXCHANGE_ID),
            params.get(EXCHANGE_NAME_PARAM, DEFAULT_EXCHANGE_NAME),
        )
    return drive(pane_model(), params)


def live_view_model(params: dict, live: Any) -> dict:
    """Build the screen ``EXCHANGE_ID_PARAM`` names from the running fleet.

    ``live.bot_manager.list_bots_by_exchange`` names the bots the two
    tables draw; ``view_model`` answers while no manager is bound.
    """
    manager = getattr(live, "bot_manager", None)
    if manager is None or not hasattr(manager, "list_bots_by_exchange"):
        return view_model(params)
    asked = dict(params or {})
    exchange_id = str(asked.get(EXCHANGE_ID_PARAM) or DEFAULT_EXCHANGE_ID)
    exchange_name = str(asked.get(EXCHANGE_NAME_PARAM) or DEFAULT_EXCHANGE_NAME)
    if asked.pop(RESET_PARAM, False):
        PANE_MODELS.pop(exchange_id, None)
    if asked.get(STATUSES_PARAM) is None:
        asked[STATUSES_PARAM] = list(manager.list_bots_by_exchange(exchange_id))
    return drive(pane_model_for(exchange_id, exchange_name), asked)


def bind_live(live: Any) -> Any:
    """Return an ``exchange_tab.state`` handler reading ``live``.

    ``build_registry`` calls this when the running program serves the bridge.
    """

    def handler(params: dict) -> dict:
        return live_view_model(params or {}, live)

    return handler
