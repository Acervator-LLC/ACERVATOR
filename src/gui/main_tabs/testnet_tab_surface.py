"""testnet_tab_surface.py -- the Local Testnet tab, without Qt.

Describes the in-platform block explorer: the chain status row, the run
controls, the block and transaction tables, the contract event table, the
token holder table and the scrolling log. ``TestnetTabModel`` holds the
tab's state and carries one method for each method the shipped tab
declares -- the four refreshes, the run, the stress run, the reset, the
bridge callback and the log line.

``BlockSnapshot``, ``TxSnapshot``, ``EventSnapshot``, ``ChainSnapshot``,
``AcrvSnapshot``, ``TestnetSnapshot`` and ``BridgeSnapshot`` are plain
stand-ins for the chain, the token and the bridge, so the tab can be
driven over the bridge from values alone. No stand-in opens a file,
reaches a network or makes a key.

``CHAIN_ID`` and ``NET_LABEL_TEXT`` are text this tab prints. Nothing here
dials a node. ``src.core.desktop_bridge`` registers ``view_model`` as the
handler for the ``testnet_tab.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.testnet_tab``, so a value changed on one side alone
is reported. Nothing here imports Qt.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .. import design_system as ds
from ..color_alpha import css_colours

METHOD = "testnet_tab.state"
LOGGER_NAME = "acervator.testnet"

ACCESSIBLE_NAME = "Testnet Tab"

CYAN = "#00FFEE"
GREEN = "#00FF88"
AMBER = "#FFAA00"
RED = "#FF3355"
MAGENTA = "#FF00AA"
MUTED = "#8899BB"
PANEL = "#080818"

TIER_COLORS = {
    "Harvest": "#00FF88",
    "Gold Fold": "#FFAA00",
    "Bear Slayer": "#FF3355",
    "Grand Accumulator": "#00FFEE",
    "Ekthelius": "#FF00AA",
}
TIER_FALLBACK_COLOR = MUTED

SECTION_STYLE = f"""
        QGroupBox {{
            border: 1px solid rgba(0,255,238,0.15); border-radius:6px;
            margin-top:14px; background:{PANEL};
        }}
        QGroupBox::title {{
            subcontrol-origin:margin; left:10px;
            color:{CYAN}; font-family:Orbitron; font-size:9px; letter-spacing:3px;
        }}
    """

TABLE_STYLE = f"""
        QTableWidget {{ background:{PANEL}; color:#C0D0E8;
                        font-family:Consolas; font-size:10px;
                        border:none; gridline-color:rgba(0,255,238,0.07); }}
        QTableWidget::item:selected {{ background:rgba(0,255,238,0.08); }}
        QHeaderView::section {{ background:#0A0A20; color:{MUTED};
                                 font-family:Orbitron; font-size:8px;
                                 letter-spacing:2px; border:none;
                                 border-bottom:1px solid rgba(0,255,238,0.15);
                                 padding:4px; }}
    """

LABEL_STYLE_FORMAT = (
    "color:{color}; font-family:Consolas; font-size:{size}px; font-weight:{weight};"
)
LABEL_WEIGHT_BOLD = "bold"
LABEL_WEIGHT_NORMAL = "normal"
LABEL_DEFAULT_COLOR = MUTED
LABEL_DEFAULT_SIZE = 10
LABEL_DEFAULT_BOLD = False

TITLE_STYLE = f"color:{CYAN}; font-family:Orbitron; font-size:14px; font-weight:900;"
SEPARATOR_STYLE = "color:rgba(0,255,238,0.15);"
SPIN_STYLE = (
    f"background:#0A0A20; color:{CYAN};"
    " border:1px solid rgba(0,255,238,0.2); padding:3px;"
)
COMBO_STYLE = f"background:#0A0A20; color:{CYAN}; border:1px solid rgba(0,255,238,0.2);"
PRICE_STYLE = (
    f"background:#0A0A20; color:{AMBER};"
    " border:1px solid rgba(255,170,0,0.2); padding:3px;"
)
RUN_BUTTON_STYLE = (
    f"background:rgba(0,255,238,0.08); color:{CYAN}; "
    f"border:1px solid {CYAN}; font-family:Orbitron; "
    "font-size:10px; padding:8px 20px; border-radius:4px;"
)
STRESS_BUTTON_STYLE = (
    f"background:rgba(255,170,0,0.08); color:{AMBER}; "
    f"border:1px solid {AMBER}; font-family:Orbitron; "
    "font-size:10px; padding:8px 20px; border-radius:4px;"
)
RESET_BUTTON_STYLE = (
    f"background:rgba(255,60,100,0.08); color:{RED}; "
    f"border:1px solid {RED}; font-family:Orbitron; "
    "font-size:10px; padding:8px 16px; border-radius:4px;"
)
LOG_STYLE = (
    "background:#050510; color:#8899BB; "
    "font-family:Consolas; font-size:10px; border:none;"
)
TAB_STYLE_SHEET = ""
SKIN: dict = {}

TAB_TITLE = "Local Testnet"
CHAIN_ID = 84532
NET_LABEL_TEXT = "● ACERVATOR LOCAL TESTNET  ·  Chain ID 84532"

STATUS_SECTION_TITLE = "Chain Status"
RUN_SECTION_TITLE = "Run Competition"
BLOCKS_SECTION_TITLE = "Block Explorer"
TRANSACTIONS_SECTION_TITLE = "Transaction Log"
EVENTS_SECTION_TITLE = "Contract Events"
HOLDERS_SECTION_TITLE = "Token Holders"
LOG_SECTION_TITLE = "Testnet Log"

SECTION_TITLES = (
    STATUS_SECTION_TITLE,
    RUN_SECTION_TITLE,
    BLOCKS_SECTION_TITLE,
    TRANSACTIONS_SECTION_TITLE,
    EVENTS_SECTION_TITLE,
    HOLDERS_SECTION_TITLE,
    LOG_SECTION_TITLE,
)

STAT_BLOCK = "Block"
STAT_TRANSACTIONS = "Transactions"
STAT_EVENTS = "Events"
STAT_COMPETITIONS = "Competitions"
STAT_MINTED = "ACRV Minted"
STAT_REMAINING = "Remaining"
STAT_KEYS = (
    STAT_BLOCK,
    STAT_TRANSACTIONS,
    STAT_EVENTS,
    STAT_COMPETITIONS,
    STAT_MINTED,
    STAT_REMAINING,
)
STAT_PLACEHOLDER = "—"
STAT_KEY_SIZE = 9
STAT_VALUE_SIZE = 14

STAT_SOURCE_KEYS = {
    STAT_BLOCK: "block_number",
    STAT_TRANSACTIONS: "total_transactions",
    STAT_EVENTS: "total_events",
    STAT_COMPETITIONS: "total_competitions",
    STAT_MINTED: "acrv_total_supply",
    STAT_REMAINING: "acrv_remaining",
}
STAT_COUNT_FORMAT = "{value}"
STAT_SUPPLY_FORMAT = "{value:,.0f}"
STAT_SUPPLY_KEYS = (STAT_MINTED, STAT_REMAINING)

BOTS_LABEL = "Bots:"
SYMBOL_LABEL = "Symbol:"
SEASON_LABEL = "Season:"
ORACLE_LABEL = "Oracle BTC/USD:"

BOTS_MINIMUM = 2
BOTS_MAXIMUM = 8
BOTS_DEFAULT = 3
BOTS_WIDTH_PX = 55

SEASON_MINIMUM = 1
SEASON_MAXIMUM = 20
SEASON_DEFAULT = 1
SEASON_WIDTH_PX = 55

SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
SYMBOL_DEFAULT = "BTC/USDT"
SYMBOL_WIDTH_PX = 100

ORACLE_SYMBOL = "BTC/USDT"
ORACLE_MINIMUM = 1000
ORACLE_MAXIMUM = 200000
ORACLE_DEFAULT = 62000
ORACLE_DECIMALS = 0
ORACLE_WIDTH_PX = 90

# What the spin box holds after it takes the three numbers above. A
# QDoubleSpinBox keeps every one as a decimal.
ORACLE_MINIMUM_VALUE = 1000.0
ORACLE_MAXIMUM_VALUE = 200000.0
ORACLE_DEFAULT_VALUE = 62000.0

RUN_BUTTON_TEXT = "⚔  Run Competition"
STRESS_BUTTON_TEXT = "⚡ Stress Test ×10"
RESET_BUTTON_TEXT = "⟲  Reset Chain"

BLOCK_COLUMNS = ("Block", "Txs", "Hash", "Age")
TX_COLUMNS = ("Tx Hash", "Function", "From", "Gas")
EVENT_COLUMNS = ("Block", "Event", "Details")
HOLDER_COLUMNS = ("Wallet", "Balance (ACRV)", "Tier")

BLOCK_TABLE_MAX_HEIGHT_PX = 160
TX_TABLE_MAX_HEIGHT_PX = 160
EVENT_TABLE_MAX_HEIGHT_PX = 150
HOLDER_TABLE_MAX_HEIGHT_PX = 130
TABLE_DEFAULT_MAX_HEIGHT_PX = 180
LOG_MAX_HEIGHT_PX = 120
LOG_READ_ONLY = True

BLOCK_ROW_LIMIT = 15
TX_ROW_LIMIT = 15
EVENT_ROW_LIMIT = 20
HOLDER_ROW_LIMIT = 15
EVENT_ARG_LIMIT = 3

BLOCK_HASH_CHARS = 18
TX_HASH_CHARS = 14
FROM_ADDR_CHARS = 10
WALLET_CHARS = 14
WINNER_CHARS = 14
ADJ_TX_CHARS = 20
HASH_TAIL = "..."

BLOCK_AGE_FORMAT = "{age}s ago"
GAS_FORMAT = "{gas:,}"
HOLDER_BALANCE_FORMAT = "{tokens:,.1f}"
EVENT_ARG_FORMAT = "{key}={value}"
EVENT_ARG_JOIN = "  "
TOKEN_DECIMALS = 18
NO_TIER_TEXT = "—"

BLOCK_ROW_COLORS = (CYAN, AMBER, MUTED, MUTED)
TX_ROW_COLORS = (CYAN, GREEN, MUTED, MUTED)

EVENT_COLORS = {
    "Adjudicated": "#00FF88",
    "TokensMinted": "#FFAA00",
    "ResultSubmitted": "#00FFEE",
    "CompetitionOpened": "#FF00AA",
    "BotRegistered": "#8899BB",
}
EVENT_FALLBACK_COLOR = MUTED

LOG_TIME_FORMAT = "%H:%M:%S"
LOG_LINE_FORMAT = (
    f'<span style="color:{ds.VIZ_CAPTION}">[{{stamp}}]</span> '
    '<span style="color:{color}">{text}</span>'
)

REFRESH_INTERVAL_MS = 3000
REFRESH_FAIL_LIMIT = 3
REFRESH_FAIL_ATTRIBUTE = "_refresh_{name}_fails"
REFRESH_STDERR_FORMAT = "TestnetTab._refresh_{name}: {kind}: {detail}\n"
REFRESH_LOG_FORMAT = "_refresh_%s failed (%s): %s"
REFRESH_NAMES = ("stats", "blocks", "events", "holders")

RESET_DIALOG_TITLE = "Reset Chain?"
RESET_DIALOG_TEXT = (
    "This will permanently delete all block history, "
    "transactions, token balances, and competition records "
    "on the local testnet.\n\n"
    "The persisted chain file will also be deleted.\n\n"
    "This cannot be undone. Continue?"
)
RESET_BRIDGE_REASON = "user clicked Reset Chain"
RESET_BRIDGE_MESSAGE = "Chain reset via bridge."
RESET_STANDALONE_MESSAGE = "Chain reset (in-memory only)."
CHAIN_RESET_MESSAGE = "⚠ Chain reset: {reason}"
CHAIN_RESET_COLOR = "#ffaa00"

RUN_STARTING_MESSAGE = "Starting competition..."
RUN_COMPLETE_MESSAGE = "Competition {competition_id} complete!"
RUN_WINNER_MESSAGE = "  Winner: {winner}...  Tier: {tier}  Awarded: {tokens:,} ACRV"
RUN_ADJ_MESSAGE = "  Adj tx: {adj}..."
RUN_ERROR_MESSAGE = "Error: {detail}"

BRIDGE_WINNER_MESSAGE = "  Winner: {winner}…  Tier: {tier}  Awarded: {tokens:,} ACRV"
BRIDGE_FAILED_MESSAGE = "Competition failed: {detail}"
BRIDGE_UNKNOWN_COMPETITION = "?"
BRIDGE_UNKNOWN_TIER = "?"
BRIDGE_NO_WINNER = ""
BRIDGE_NO_TOKENS = 0
ERROR_KEY = "error"

STRESS_COUNT = 10
STRESS_BOTS = 3
STRESS_STARTING_MESSAGE = "Running 10 competitions..."
STRESS_DONE_MESSAGE = (
    "10 competitions done. "
    "Total minted: {minted:,.0f} ACRV / {remaining:,.0f} remaining."
)
STRESS_TIER_MESSAGE = "  Tier distribution: {tiers}"
STRESS_TIER_FORMAT = "{key}: {value}"
STRESS_TIER_JOIN = ", "
STRESS_ERROR_MESSAGE = "Stress test error: {detail}"
TIER_COUNTS_KEY = "tier_counts"

RESULT_COMPETITION_KEY = "competition_id"
RESULT_WINNER_KEY = "winner_wallet"
RESULT_TIER_KEY = "winner_tier"
RESULT_TOKENS_KEY = "tokens_awarded"
RESULT_ADJ_KEY = "adj_tx_hash"

REQUEST_FIELDS = ("symbol", "season", "n_bots", "round_id")
REQUEST_NO_ROUND = None

ACTIONS = {
    "refresh_timer.timeout": "refresh_all",
    "bridge.chain_updated": "refresh_all",
    "bridge.chain_reset": "chain_reset_message",
    "run_button.clicked": "run_competition",
    "stress_button.clicked": "stress_test",
    "reset_button.clicked": "reset_chain",
    "oracle_price.valueChanged": "set_mock_price",
    "bridge.competition_completed@run": "on_bridge_competition",
    "bridge.competition_completed@stress": "on_bridge_competition",
}
BRIDGE_SIGNALS = ("chain_updated", "chain_reset", "competition_completed")

TIMERS = {"refresh": REFRESH_INTERVAL_MS}
TIMER_DELAYS_MS = (REFRESH_INTERVAL_MS,)
AUTOSTART_TIMERS = ("refresh",)
BUS_TOPICS: tuple = ()

CONTENT_MARGINS = (10, 8, 10, 8)
CONTENT_SPACING = 6
SPLITTER_HANDLE_WIDTH_PX = 5
SPLITTER_CHILDREN_COLLAPSIBLE = False

ALIGNMENT = "AlignCenter"
ALIGNMENT_VALUE = 132
LABEL_DEFAULT_ALIGNMENT_VALUE = 129
SEPARATOR_FRAME_SHAPE = "HLine"
SEPARATOR_FRAME_SHAPE_VALUE = 4
SPLITTER_ORIENTATION = "Horizontal"
SPLITTER_ORIENTATION_VALUE = 1
HEADER_RESIZE_MODE = "Stretch"
HEADER_RESIZE_VALUE = 1
VERTICAL_HEADER_VISIBLE = False
EDIT_TRIGGERS_NONE = "NoEditTriggers"
EDIT_TRIGGERS_NONE_VALUE = 0
EDIT_TRIGGERS_DEFAULT_VALUE = 26
SELECTION_BEHAVIOR_ROWS = "SelectRows"
SELECTION_BEHAVIOR_ROWS_VALUE = 1
SELECTION_BEHAVIOR_DEFAULT_VALUE = 0

NO_COLOR = ""
NO_PATH = ""

RUN_PATH_BRIDGE = "bridge"
RUN_PATH_INLINE = "inline"
RUN_PATH_REFUSED = "refused"
RUN_PATHS = (RUN_PATH_BRIDGE, RUN_PATH_INLINE, RUN_PATH_REFUSED)

STRESS_PATH_BRIDGE = "stress_bridge"
STRESS_PATH_INLINE = "stress_inline"
STRESS_PATH_REFUSED = "stress_refused"
STRESS_PATHS = (STRESS_PATH_BRIDGE, STRESS_PATH_INLINE, STRESS_PATH_REFUSED)

RESET_PATH_CANCELLED = "cancelled"
RESET_PATH_BRIDGE = "reset_bridge"
RESET_PATH_STANDALONE = "standalone"
RESET_PATHS = (RESET_PATH_CANCELLED, RESET_PATH_BRIDGE, RESET_PATH_STANDALONE)

BRIDGE_PATH_FAILED = "failed"
BRIDGE_PATH_COMPLETE = "complete"
BRIDGE_PATHS = (BRIDGE_PATH_FAILED, BRIDGE_PATH_COMPLETE)

WIRED_PATH_BRIDGE = "wired"
WIRED_PATH_STANDALONE = "unwired"
WIRED_PATHS = (WIRED_PATH_BRIDGE, WIRED_PATH_STANDALONE)

SETUP_START = "setup.start"
SETUP_STATUS = "setup.status"
SETUP_RUN = "setup.run"
SETUP_SPLIT = "setup.split"
SETUP_EVENTS = "setup.events"
SETUP_HOLDERS = "setup.holders"
SETUP_LOG = "setup.log"
SETUP_RETURN = "setup.return"
STATS_START = "stats.start"
STATS_RETURN = "stats.return"
BLOCKS_START = "blocks.start"
BLOCKS_RETURN = "blocks.return"
EVENTS_START = "events.start"
EVENTS_RETURN = "events.return"
HOLDERS_START = "holders.start"
HOLDERS_RETURN = "holders.return"
REFRESH_START = "refresh.start"
REFRESH_FAILED = "refresh.failed"
REFRESH_RETURN = "refresh.return"
RUN_START = "run.start"
RUN_RETURN = "run.return"
STRESS_START = "stress.start"
STRESS_RETURN = "stress.return"
RESET_START = "reset.start"
RESET_RETURN = "reset.return"
BRIDGE_START = "bridge.start"
BRIDGE_RETURN = "bridge.return"
MESSAGE_APPENDED = "log.append"
PRICE_SET = "oracle.set"
WIRE_DONE = "wire.done"

CALL_NAMES = (
    SETUP_START,
    SETUP_STATUS,
    SETUP_RUN,
    SETUP_SPLIT,
    SETUP_EVENTS,
    SETUP_HOLDERS,
    SETUP_LOG,
    SETUP_RETURN,
    STATS_START,
    STATS_RETURN,
    BLOCKS_START,
    BLOCKS_RETURN,
    EVENTS_START,
    EVENTS_RETURN,
    HOLDERS_START,
    HOLDERS_RETURN,
    REFRESH_START,
    REFRESH_FAILED,
    REFRESH_RETURN,
    RUN_START,
    RUN_RETURN,
    STRESS_START,
    STRESS_RETURN,
    RESET_START,
    RESET_RETURN,
    BRIDGE_START,
    BRIDGE_RETURN,
    MESSAGE_APPENDED,
    PRICE_SET,
    WIRE_DONE,
)


def label_style(
    color: Any = LABEL_DEFAULT_COLOR,
    size: Any = LABEL_DEFAULT_SIZE,
    bold: Any = LABEL_DEFAULT_BOLD,
) -> str:
    """The look one text label on this tab carries."""
    weight = LABEL_WEIGHT_BOLD if bold else LABEL_WEIGHT_NORMAL
    return LABEL_STYLE_FORMAT.format(color=color, size=size, weight=weight)


def event_color(event_name: Any) -> str:
    """The colour one contract event name is drawn in, or the fallback grey."""
    return EVENT_COLORS.get(event_name, EVENT_FALLBACK_COLOR)


def tier_color(tier_name: Any) -> str:
    """The colour one holder tier is drawn in, or the fallback grey."""
    return TIER_COLORS.get(tier_name, TIER_FALLBACK_COLOR)


def short_hash(text: Any, chars: Any) -> str:
    """The first `chars` characters of a hash, with a trailing ellipsis."""
    return text[:chars] + HASH_TAIL


def block_age(timestamp: Any, now: Any) -> str:
    """How long ago one block was mined, in whole seconds."""
    return BLOCK_AGE_FORMAT.format(age=int(now - timestamp))


def holder_balance(wei: Any) -> str:
    """One holder's ACRV, converted from the smallest unit."""
    return HOLDER_BALANCE_FORMAT.format(tokens=wei / (10**TOKEN_DECIMALS))


def event_args_text(args: Any) -> str:
    """The first three arguments of one contract event, on one line."""
    return EVENT_ARG_JOIN.join(
        EVENT_ARG_FORMAT.format(key=key, value=value)
        for key, value in list(args.items())[:EVENT_ARG_LIMIT]
    )


def oracle_value(price: Any) -> float:
    """The oracle price the spin box holds after it is asked for `price`."""
    return float(min(max(price, ORACLE_MINIMUM), ORACLE_MAXIMUM))


def log_line(text: Any, color: Any, stamp: Any) -> str:
    """One line of the Testnet Log, stamped with the time it was written."""
    return LOG_LINE_FORMAT.format(stamp=stamp, color=color, text=text)


def stat_text(key: Any, stats: Any) -> str:
    """One Chain Status value, grouped in thousands where it counts tokens."""
    value = stats[STAT_SOURCE_KEYS[key]]
    if key in STAT_SUPPLY_KEYS:
        return STAT_SUPPLY_FORMAT.format(value=value)
    return STAT_COUNT_FORMAT.format(value=value)


def cell(text: Any, color: Any) -> dict:
    """One table cell: its text, its colour and its alignment."""
    return {"text": text, "color": color or NO_COLOR, "alignment": ALIGNMENT}


def row_cells(values: Any, colors: Any) -> list:
    """One table row, each cell coloured by its own column."""
    found = []
    for column, value in enumerate(values):
        color = NO_COLOR
        if colors and column < len(colors) and colors[column]:
            color = colors[column]
        found.append(cell(str(value), color))
    return found


def widget(name: str, kind: str, parent: str, **values: Any) -> dict:
    """One node of the tab's widget tree, with its parent and its values."""
    return {"name": name, "kind": kind, "parent": parent, **values}


def section_node(name: str, title: Any, parent: str) -> dict:
    """One titled panel, carrying the look every panel on this tab shares."""
    return widget(
        name,
        "QGroupBox",
        parent,
        title=title.upper(),
        style_sheet=SECTION_STYLE,
        layout="QVBoxLayout",
    )


def label_node(name: str, parent: str, text: Any, **values: Any) -> dict:
    """One text label built the way this tab builds every label."""
    color = values.pop("color", LABEL_DEFAULT_COLOR)
    size = values.pop("size", LABEL_DEFAULT_SIZE)
    bold = values.pop("bold", LABEL_DEFAULT_BOLD)
    return widget(
        name,
        "QLabel",
        parent,
        text=text,
        style_sheet=label_style(color, size, bold),
        **values,
    )


def table_node(
    name: str,
    parent: str,
    columns: Any,
    max_height: Any = TABLE_DEFAULT_MAX_HEIGHT_PX,
) -> dict:
    """One table built the way this tab builds every table."""
    return widget(
        name,
        "QTableWidget",
        parent,
        columns=list(columns),
        column_count=len(columns),
        header_resize_value=HEADER_RESIZE_VALUE,
        vertical_header_visible=VERTICAL_HEADER_VISIBLE,
        edit_triggers_value=EDIT_TRIGGERS_NONE_VALUE,
        selection_behavior_value=SELECTION_BEHAVIOR_ROWS_VALUE,
        max_height=max_height,
        style_sheet=TABLE_STYLE,
    )


def widget_children(nodes: Any) -> dict:
    """Each parent's own children, in the order they were added."""
    return {
        parent: [node["name"] for node in nodes if node["parent"] == parent]
        for parent in dict.fromkeys(node["parent"] for node in nodes)
    }


def widget_index(nodes: Any) -> dict:
    """Each node's position among the children of its own parent."""
    children = widget_children(nodes)
    return {
        node["name"]: children[node["parent"]].index(node["name"]) for node in nodes
    }


class BlockSnapshot:
    """One mined block: its number, its hash, its parent and its clock stamp."""

    def __init__(
        self,
        number: Any = 0,
        block_hash: Any = "",
        parent_hash: Any = "",
        timestamp: Any = 0.0,
        transactions: Optional[list] = None,
    ) -> None:
        self.number = number
        self.hash = block_hash
        self.parent_hash = parent_hash
        self.timestamp = timestamp
        self.transactions = [] if transactions is None else transactions


class TxSnapshot:
    """One recorded transaction, as the Transaction Log prints it."""

    def __init__(
        self,
        tx_hash: Any = "",
        block_number: Any = 0,
        from_addr: Any = "",
        to_addr: Any = "",
        function_name: Any = "",
        args: Optional[dict] = None,
        status: Any = 1,
        gas_used: Any = 21000,
        timestamp: Any = 0.0,
    ) -> None:
        self.tx_hash = tx_hash
        self.block_number = block_number
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.function_name = function_name
        self.args = {} if args is None else args
        self.status = status
        self.gas_used = gas_used
        self.timestamp = timestamp


class EventSnapshot:
    """One contract event, as the Contract Events table prints it."""

    def __init__(
        self,
        block_number: Any = 0,
        tx_hash: Any = "",
        contract: Any = "",
        event_name: Any = "",
        args: Optional[dict] = None,
        timestamp: Any = 0.0,
    ) -> None:
        self.block_number = block_number
        self.tx_hash = tx_hash
        self.contract = contract
        self.event_name = event_name
        self.args = {} if args is None else args
        self.timestamp = timestamp


class ChainSnapshot:
    """A chain built from plain values, carrying the reads the tab makes."""

    def __init__(
        self,
        blocks: Any = (),
        transactions: Any = (),
        events: Any = (),
        block_number: Any = 0,
    ) -> None:
        self.latest_blocks = list(blocks)
        self._txs = {
            getattr(tx, "tx_hash", index): tx for index, tx in enumerate(transactions)
        }
        self.latest_events = list(events)
        self.block_number = block_number


class AcrvSnapshot:
    """A token contract built from plain values: balances and the mint log."""

    def __init__(
        self, balances: Optional[dict] = None, mint_log: Optional[list] = None
    ) -> None:
        self._balances = {} if balances is None else balances
        self._mint_log = [] if mint_log is None else mint_log


RESET_ATTRIBUTES = ("chain", "acrv", "stats")

EMPTY_CHAIN_STATS = {
    "block_number": 0,
    "total_transactions": 0,
    "total_events": 0,
    "total_competitions": 0,
    "acrv_total_supply": 0,
    "acrv_remaining": 10_000_000,
    "tier_counts": {},
}


class TestnetSnapshot:
    """A local testnet built from plain values.

    Carries the chain, the token contract, the competition summary and the
    two calls the tab makes on it. It opens no file, reaches no network and
    makes no key.
    """

    def __init__(
        self,
        chain: Optional[ChainSnapshot] = None,
        acrv: Optional[AcrvSnapshot] = None,
        stats: Optional[dict] = None,
        result: Any = None,
        error: Optional[BaseException] = None,
    ) -> None:
        self.chain = ChainSnapshot() if chain is None else chain
        self.acrv = AcrvSnapshot() if acrv is None else acrv
        self.stats = dict(EMPTY_CHAIN_STATS) if stats is None else stats
        self.result = result
        self.error = error
        self.prices: dict = {}
        self.runs: list = []

    def get_competition_stats(self) -> dict:
        """The Chain Status summary, or the error this stand-in was given."""
        if isinstance(self.error, BaseException):
            raise self.error
        return dict(self.stats)

    def set_mock_price(self, symbol: Any, price: Any) -> None:
        """Record the oracle price the spin box asked for."""
        self.prices[symbol] = price

    def run_demo_competition(
        self, n_bots: Any = 3, season: Any = 1, symbol: Any = SYMBOL_DEFAULT
    ) -> Any:
        """Answer with the invented result, or raise the error it carries."""
        self.runs.append({"n_bots": n_bots, "season": season, "symbol": symbol})
        if isinstance(self.error, BaseException):
            raise self.error
        return self.result

    def fresh(self) -> "TestnetSnapshot":
        """An empty testnet, the way the standalone reset builds one."""
        return TestnetSnapshot(stats=dict(EMPTY_CHAIN_STATS))

    def reset_in_place(self) -> None:
        """Replace this testnet's chain state with a fresh chain's.

        Only the three fields a fresh local testnet carries are replaced.
        Everything else this stand-in records survives, the way a field the
        replaced object never declared survives.
        """
        fresh = self.fresh()
        self.__dict__.update({name: getattr(fresh, name) for name in RESET_ATTRIBUTES})


class BridgeSnapshot:
    """A shared bridge built from plain values.

    Records every wiring, every queued request and every reset, so the two
    bridge paths can be driven without a signal and without a thread. A
    second wiring of one signal is kept once and answers False, the way a
    unique connection keeps one delivery. A signal this bridge does not
    carry is refused, the way a missing attribute is.
    """

    SIGNALS = BRIDGE_SIGNALS

    def __init__(self, wired: Any = ()) -> None:
        self.wired = list(wired)
        self.requests: list = []
        self.resets: list = []

    def connect(self, signal: Any) -> bool:
        """Record one wiring, keeping a repeated wiring of one signal once."""
        if signal not in self.SIGNALS:
            raise AttributeError(
                "%r object has no attribute %r" % (type(self).__name__, signal)
            )
        if signal in self.wired:
            return False
        self.wired.append(signal)
        return True

    def request_competition(self, request: Any) -> None:
        """Queue one competition request."""
        self.requests.append(request)

    def reset(self, reason: Any = RESET_BRIDGE_REASON) -> None:
        """Record one chain reset and the reason it carries."""
        self.resets.append(reason)


def request_payload(symbol: Any, season: Any, n_bots: Any) -> dict:
    """One competition request, as the bridge queue carries it."""
    return {
        "symbol": symbol,
        "season": season,
        "n_bots": n_bots,
        "round_id": REQUEST_NO_ROUND,
    }


class TestnetTabModel:
    """The Local Testnet tab: its widgets, its tables, its log, its paths.

    One method answers each method the shipped tab declares. ``setup_ui``
    returns the whole tree in build order. The four refreshes fill the stat
    row and the four tables. ``run_competition``, ``stress_test``,
    ``reset_chain`` and ``on_bridge_competition`` carry the button
    behaviour. Every step is appended to ``calls`` in the order the shipped
    tab makes it.
    """

    def __init__(self, testnet: Any = None, bridge: Any = None) -> None:
        self.testnet = TestnetSnapshot() if testnet is None else testnet
        self.bridge = bridge
        self.accessible_name = ACCESSIBLE_NAME
        self.comp_count = 0
        self.stat_values = {key: STAT_PLACEHOLDER for key in STAT_KEYS}
        self.block_rows: list = []
        self.tx_rows: list = []
        self.event_rows: list = []
        self.holder_rows: list = []
        self.log_lines: list = []
        self.run_enabled = True
        self.stress_enabled = True
        self.wired_path = NO_PATH
        self.run_path = NO_PATH
        self.stress_path = NO_PATH
        self.reset_path = NO_PATH
        self.bridge_path = NO_PATH
        self.refresh_failures: list = []
        self.wiring_refusals: list = []
        self.stderr_lines: list = []
        self.log_records: list = []
        self.calls: list = []
        self.wire()

    def wire(self) -> str:
        """Start the refresh timer and wire the bridge when there is one."""
        if self.bridge is None:
            self.wired_path = WIRED_PATH_STANDALONE
        else:
            self._wire_signal("chain_updated")
            self._wire_signal("chain_reset")
            self.wired_path = WIRED_PATH_BRIDGE
        self.calls.append([WIRE_DONE, self.wired_path])
        return self.wired_path

    def _wire_signal(self, signal: Any) -> bool:
        """Wire one bridge signal, naming a wiring the bridge already holds."""
        try:
            self.bridge.connect(signal)
        except Exception as exc:
            self.wiring_refusals.append([signal, type(exc).__name__])
            return False
        return True

    def chain_reset_message(self, reason: Any, stamp: Any = None) -> str:
        """The warning line the bridge's reset signal writes into the log."""
        return self.msg(
            CHAIN_RESET_MESSAGE.format(reason=reason), CHAIN_RESET_COLOR, stamp
        )

    def msg(self, text: Any, color: Any = MUTED, stamp: Any = None) -> str:
        """Append one stamped line to the Testnet Log and return it."""
        found = time.strftime(LOG_TIME_FORMAT) if stamp is None else stamp
        line = log_line(text, color, found)
        self.log_lines.append(line)
        self.calls.append([MESSAGE_APPENDED, len(self.log_lines)])
        return line

    def refresh_stats(self) -> dict:
        """Fill the six Chain Status values from the competition summary."""
        stats = self.testnet.get_competition_stats()
        self.calls.append([STATS_START, len(stats)])
        for key in STAT_KEYS:
            if key in self.stat_values:
                self.stat_values[key] = stat_text(key, stats)
        self.calls.append([STATS_RETURN, len(self.stat_values)])
        return dict(self.stat_values)

    def refresh_blocks(self, now: Any = None) -> dict:
        """Fill the Block Explorer and the Transaction Log."""
        found = time.time() if now is None else now
        self.block_rows = []
        self.tx_rows = []
        self.calls.append([BLOCKS_START, len(self.testnet.chain.latest_blocks)])
        for block in self.testnet.chain.latest_blocks[:BLOCK_ROW_LIMIT]:
            self.block_rows.append(
                row_cells(
                    [
                        str(block.number),
                        str(len(block.transactions)),
                        short_hash(block.hash, BLOCK_HASH_CHARS),
                        block_age(block.timestamp, found),
                    ],
                    BLOCK_ROW_COLORS,
                )
            )
        for tx in list(reversed(list(self.testnet.chain._txs.values())))[:TX_ROW_LIMIT]:
            self.tx_rows.append(
                row_cells(
                    [
                        short_hash(tx.tx_hash, TX_HASH_CHARS),
                        tx.function_name,
                        short_hash(tx.from_addr, FROM_ADDR_CHARS),
                        GAS_FORMAT.format(gas=tx.gas_used),
                    ],
                    TX_ROW_COLORS,
                )
            )
        self.calls.append([BLOCKS_RETURN, len(self.block_rows), len(self.tx_rows)])
        return {"blocks": self.block_rows, "transactions": self.tx_rows}

    def refresh_events(self) -> list:
        """Fill the Contract Events table, each event coloured by its name."""
        self.event_rows = []
        self.calls.append([EVENTS_START, len(self.testnet.chain.latest_events)])
        for event in self.testnet.chain.latest_events[:EVENT_ROW_LIMIT]:
            self.event_rows.append(
                row_cells(
                    [
                        str(event.block_number),
                        event.event_name,
                        event_args_text(event.args),
                    ],
                    (MUTED, event_color(event.event_name), MUTED),
                )
            )
        self.calls.append([EVENTS_RETURN, len(self.event_rows)])
        return self.event_rows

    def refresh_holders(self) -> list:
        """Fill the Token Holders table, largest balance first."""
        self.holder_rows = []
        balances = self.testnet.acrv._balances
        ordered = sorted(balances.items(), key=lambda pair: pair[1], reverse=True)
        self.calls.append([HOLDERS_START, len(ordered)])
        tiers: dict = {}
        for mint in self.testnet.acrv._mint_log:
            tiers[mint["recipient"]] = mint["tier"]
        for address, wei in ordered[:HOLDER_ROW_LIMIT]:
            tier = tiers.get(address, NO_TIER_TEXT)
            self.holder_rows.append(
                row_cells(
                    [
                        short_hash(address, WALLET_CHARS),
                        holder_balance(wei),
                        tier,
                    ],
                    (MUTED, GREEN, tier_color(tier)),
                )
            )
        self.calls.append([HOLDERS_RETURN, len(self.holder_rows)])
        return self.holder_rows

    def refresh_all(self, now: Any = None) -> list:
        """Run every refresh, naming the first three failures of each."""
        self.calls.append([REFRESH_START])
        named = []
        for name in REFRESH_NAMES:
            run = getattr(self, "refresh_" + name)
            try:
                if name == "blocks":
                    run(now)
                else:
                    run()
            except Exception as exc:
                named.append(name)
                self._name_failure(name, exc)
        self.calls.append([REFRESH_RETURN, len(named)])
        return named

    def _name_failure(self, name: Any, exc: BaseException) -> None:
        """Write one refresh failure to the error stream and to the log."""
        key = REFRESH_FAIL_ATTRIBUTE.format(name=name)
        seen = getattr(self, key, 0)
        if seen >= REFRESH_FAIL_LIMIT:
            return
        setattr(self, key, seen + 1)
        self.stderr_lines.append(
            REFRESH_STDERR_FORMAT.format(name=name, kind=type(exc).__name__, detail=exc)
        )
        self.log_records.append(
            [REFRESH_LOG_FORMAT, name, type(exc).__name__, str(exc)]
        )
        self.refresh_failures.append([name, type(exc).__name__])
        self.calls.append([REFRESH_FAILED, name, seen])

    def reset_chain(self, confirmed: Any, now: Any = None) -> str:
        """Wipe the chain, after the confirmation the destructive act needs."""
        self.calls.append([RESET_START, bool(confirmed)])
        if not confirmed:
            self.reset_path = RESET_PATH_CANCELLED
            self.calls.append([RESET_RETURN, self.reset_path])
            return self.reset_path
        if self.bridge is not None:
            self.bridge.reset(reason=RESET_BRIDGE_REASON)
            self.msg(RESET_BRIDGE_MESSAGE, AMBER)
            self.reset_path = RESET_PATH_BRIDGE
        else:
            self.testnet.reset_in_place()
            self.msg(RESET_STANDALONE_MESSAGE, AMBER)
            self.reset_path = RESET_PATH_STANDALONE
        self.refresh_all(now)
        self.calls.append([RESET_RETURN, self.reset_path])
        return self.reset_path

    def run_competition(
        self,
        symbol: Any = SYMBOL_DEFAULT,
        season: Any = SEASON_DEFAULT,
        n_bots: Any = BOTS_DEFAULT,
        now: Any = None,
    ) -> str:
        """Run one competition, through the bridge when there is one."""
        self.run_enabled = False
        self.msg(RUN_STARTING_MESSAGE, CYAN)
        self.calls.append([RUN_START, self.bridge is not None])
        if self.bridge is not None:
            request = request_payload(symbol, season, n_bots)
            self._wire_signal("competition_completed")
            self.bridge.request_competition(request)
            self.run_path = RUN_PATH_BRIDGE
            self.calls.append([RUN_RETURN, self.run_path])
            return self.run_path
        try:
            result = self.testnet.run_demo_competition(
                n_bots=n_bots, season=season, symbol=symbol
            )
            self.comp_count += 1
            self.msg(
                RUN_COMPLETE_MESSAGE.format(
                    competition_id=result[RESULT_COMPETITION_KEY]
                ),
                GREEN,
            )
            self.msg(
                RUN_WINNER_MESSAGE.format(
                    winner=result[RESULT_WINNER_KEY][:WINNER_CHARS],
                    tier=result[RESULT_TIER_KEY],
                    tokens=result[RESULT_TOKENS_KEY],
                ),
                GREEN,
            )
            self.msg(
                RUN_ADJ_MESSAGE.format(adj=result[RESULT_ADJ_KEY][:ADJ_TX_CHARS]),
                MUTED,
            )
            self.refresh_all(now)
            self.run_path = RUN_PATH_INLINE
        except Exception as exc:
            self.msg(RUN_ERROR_MESSAGE.format(detail=exc), RED)
            self.run_path = RUN_PATH_REFUSED
        finally:
            self.run_enabled = True
        self.calls.append([RUN_RETURN, self.run_path])
        return self.run_path

    def on_bridge_competition(self, result: Any, now: Any = None) -> str:
        """Take one finished competition off the bridge and log its outcome."""
        self.run_enabled = True
        self.stress_enabled = True
        self.calls.append([BRIDGE_START, ERROR_KEY in result])
        if ERROR_KEY in result:
            self.msg(BRIDGE_FAILED_MESSAGE.format(detail=result[ERROR_KEY]), RED)
            self.bridge_path = BRIDGE_PATH_FAILED
            self.calls.append([BRIDGE_RETURN, self.bridge_path])
            return self.bridge_path
        self.comp_count += 1
        self.msg(
            RUN_COMPLETE_MESSAGE.format(
                competition_id=result.get(
                    RESULT_COMPETITION_KEY, BRIDGE_UNKNOWN_COMPETITION
                )
            ),
            GREEN,
        )
        self.msg(
            BRIDGE_WINNER_MESSAGE.format(
                winner=str(result.get(RESULT_WINNER_KEY, BRIDGE_NO_WINNER))[
                    :WINNER_CHARS
                ],
                tier=result.get(RESULT_TIER_KEY, BRIDGE_UNKNOWN_TIER),
                tokens=result.get(RESULT_TOKENS_KEY, BRIDGE_NO_TOKENS),
            ),
            GREEN,
        )
        self.refresh_all(now)
        self.bridge_path = BRIDGE_PATH_COMPLETE
        self.calls.append([BRIDGE_RETURN, self.bridge_path])
        return self.bridge_path

    def stress_test(
        self,
        symbol: Any = SYMBOL_DEFAULT,
        season: Any = SEASON_DEFAULT,
        now: Any = None,
    ) -> str:
        """Run ten competitions, through the bridge when there is one."""
        self.stress_enabled = False
        self.msg(STRESS_STARTING_MESSAGE, AMBER)
        self.calls.append([STRESS_START, self.bridge is not None])
        if self.bridge is not None:
            self._wire_signal("competition_completed")
            for _ in range(STRESS_COUNT):
                self.bridge.request_competition(
                    request_payload(symbol, season, STRESS_BOTS)
                )
            self.stress_path = STRESS_PATH_BRIDGE
            self.calls.append([STRESS_RETURN, self.stress_path])
            return self.stress_path
        try:
            for _ in range(STRESS_COUNT):
                self.testnet.run_demo_competition(
                    n_bots=STRESS_BOTS, season=season, symbol=symbol
                )
            stats = self.testnet.get_competition_stats()
            self.msg(
                STRESS_DONE_MESSAGE.format(
                    minted=stats["acrv_total_supply"],
                    remaining=stats["acrv_remaining"],
                ),
                GREEN,
            )
            tiers = stats.get(TIER_COUNTS_KEY, {})
            if tiers:
                self.msg(
                    STRESS_TIER_MESSAGE.format(
                        tiers=STRESS_TIER_JOIN.join(
                            STRESS_TIER_FORMAT.format(key=key, value=value)
                            for key, value in tiers.items()
                        )
                    ),
                    AMBER,
                )
            self.refresh_all(now)
            self.stress_path = STRESS_PATH_INLINE
        except Exception as exc:
            self.msg(STRESS_ERROR_MESSAGE.format(detail=exc), RED)
            self.stress_path = STRESS_PATH_REFUSED
        finally:
            self.stress_enabled = True
        self.calls.append([STRESS_RETURN, self.stress_path])
        return self.stress_path

    def set_mock_price(self, price: Any) -> Any:
        """Hand the oracle spin box's value to the testnet.

        The spin box holds a value inside its own range and holds it as a
        decimal, so the value that leaves the box is the clamped one.
        """
        held = oracle_value(price)
        self.testnet.set_mock_price(ORACLE_SYMBOL, held)
        self.calls.append([PRICE_SET, ORACLE_SYMBOL])
        return held

    def setup_ui(self) -> list:
        """The tab's widget tree, in the order the tab builds it."""
        self.calls.append([SETUP_START])
        nodes = [
            widget(
                "tab",
                "QWidget",
                "",
                accessible_name=ACCESSIBLE_NAME,
                layout="QVBoxLayout",
                margins=CONTENT_MARGINS,
                spacing=CONTENT_SPACING,
                style_sheet=TAB_STYLE_SHEET,
            ),
            widget("header_row", "QHBoxLayout", "tab"),
            widget(
                "title",
                "QLabel",
                "header_row",
                text=TAB_TITLE,
                style_sheet=TITLE_STYLE,
            ),
            widget("header_stretch", "stretch", "header_row"),
            label_node("net_label", "header_row", NET_LABEL_TEXT, color=GREEN, size=10),
            widget(
                "separator",
                "QFrame",
                "tab",
                frame_shape_value=SEPARATOR_FRAME_SHAPE_VALUE,
                style_sheet=SEPARATOR_STYLE,
            ),
        ]
        nodes.extend(self._status_nodes())
        self.calls.append([SETUP_STATUS, len(nodes)])
        nodes.extend(self._run_nodes())
        self.calls.append([SETUP_RUN, len(nodes)])
        nodes.extend(self._split_nodes())
        self.calls.append([SETUP_SPLIT, len(nodes)])
        nodes.extend(
            [
                section_node("events_section", EVENTS_SECTION_TITLE, "tab"),
                table_node(
                    "events_table",
                    "events_section",
                    EVENT_COLUMNS,
                    EVENT_TABLE_MAX_HEIGHT_PX,
                ),
            ]
        )
        self.calls.append([SETUP_EVENTS, len(nodes)])
        nodes.extend(
            [
                section_node("holders_section", HOLDERS_SECTION_TITLE, "tab"),
                table_node(
                    "holders_table",
                    "holders_section",
                    HOLDER_COLUMNS,
                    HOLDER_TABLE_MAX_HEIGHT_PX,
                ),
            ]
        )
        self.calls.append([SETUP_HOLDERS, len(nodes)])
        nodes.extend(
            [
                section_node("log_section", LOG_SECTION_TITLE, "tab"),
                widget(
                    "log_view",
                    "QTextEdit",
                    "log_section",
                    read_only=LOG_READ_ONLY,
                    max_height=LOG_MAX_HEIGHT_PX,
                    style_sheet=LOG_STYLE,
                ),
            ]
        )
        self.calls.append([SETUP_LOG, len(nodes)])
        self.refresh_stats()
        self.calls.append([SETUP_RETURN, len(nodes)])
        return nodes

    def _status_nodes(self) -> list:
        """The Chain Status panel: six stacked label-and-value columns."""
        nodes = [
            section_node("status_section", STATUS_SECTION_TITLE, "tab"),
            widget("status_row", "QHBoxLayout", "status_section"),
        ]
        for index, key in enumerate(STAT_KEYS):
            column = "stat_column_%d" % index
            nodes.append(widget(column, "QVBoxLayout", "status_row"))
            nodes.append(
                label_node(
                    "stat_key_%d" % index,
                    column,
                    key.upper(),
                    color=MUTED,
                    size=STAT_KEY_SIZE,
                    alignment=ALIGNMENT,
                )
            )
            nodes.append(
                label_node(
                    "stat_value_%d" % index,
                    column,
                    self.stat_values[key],
                    color=CYAN,
                    size=STAT_VALUE_SIZE,
                    bold=True,
                    alignment=ALIGNMENT,
                )
            )
        return nodes

    def _run_nodes(self) -> list:
        """The Run Competition panel: the control row and the oracle row."""
        return [
            section_node("run_section", RUN_SECTION_TITLE, "tab"),
            widget("control_row", "QHBoxLayout", "run_section"),
            label_node("bots_label", "control_row", BOTS_LABEL),
            widget(
                "bots_spin",
                "QSpinBox",
                "control_row",
                minimum=BOTS_MINIMUM,
                maximum=BOTS_MAXIMUM,
                value=BOTS_DEFAULT,
                fixed_width=BOTS_WIDTH_PX,
                style_sheet=SPIN_STYLE,
            ),
            label_node("symbol_label", "control_row", SYMBOL_LABEL),
            widget(
                "symbol_combo",
                "QComboBox",
                "control_row",
                items=list(SYMBOLS),
                current_text=SYMBOL_DEFAULT,
                current_index=0,
                fixed_width=SYMBOL_WIDTH_PX,
                style_sheet=COMBO_STYLE,
            ),
            label_node("season_label", "control_row", SEASON_LABEL),
            widget(
                "season_spin",
                "QSpinBox",
                "control_row",
                minimum=SEASON_MINIMUM,
                maximum=SEASON_MAXIMUM,
                value=SEASON_DEFAULT,
                fixed_width=SEASON_WIDTH_PX,
                style_sheet=SPIN_STYLE,
            ),
            widget("control_stretch", "stretch", "control_row"),
            widget(
                "run_button",
                "QPushButton",
                "control_row",
                text=RUN_BUTTON_TEXT,
                style_sheet=RUN_BUTTON_STYLE,
                enabled=self.run_enabled,
            ),
            widget(
                "stress_button",
                "QPushButton",
                "control_row",
                text=STRESS_BUTTON_TEXT,
                style_sheet=STRESS_BUTTON_STYLE,
                enabled=self.stress_enabled,
            ),
            widget(
                "reset_button",
                "QPushButton",
                "control_row",
                text=RESET_BUTTON_TEXT,
                style_sheet=RESET_BUTTON_STYLE,
                enabled=True,
            ),
            widget("oracle_row", "QHBoxLayout", "run_section"),
            label_node("oracle_label", "oracle_row", ORACLE_LABEL),
            widget(
                "oracle_price",
                "QDoubleSpinBox",
                "oracle_row",
                minimum=ORACLE_MINIMUM_VALUE,
                maximum=ORACLE_MAXIMUM_VALUE,
                value=ORACLE_DEFAULT_VALUE,
                decimals=ORACLE_DECIMALS,
                fixed_width=ORACLE_WIDTH_PX,
                style_sheet=PRICE_STYLE,
            ),
            widget("oracle_stretch", "stretch", "oracle_row"),
        ]

    def _split_nodes(self) -> list:
        """The two side-by-side panels: the blocks and the transactions."""
        return [
            widget(
                "splitter",
                "QSplitter",
                "tab",
                orientation_value=SPLITTER_ORIENTATION_VALUE,
                handle_width=SPLITTER_HANDLE_WIDTH_PX,
                children_collapsible=SPLITTER_CHILDREN_COLLAPSIBLE,
            ),
            section_node("blocks_section", BLOCKS_SECTION_TITLE, "splitter"),
            table_node(
                "blocks_table",
                "blocks_section",
                BLOCK_COLUMNS,
                BLOCK_TABLE_MAX_HEIGHT_PX,
            ),
            section_node(
                "transactions_section", TRANSACTIONS_SECTION_TITLE, "splitter"
            ),
            table_node(
                "transactions_table",
                "transactions_section",
                TX_COLUMNS,
                TX_TABLE_MAX_HEIGHT_PX,
            ),
        ]


def build_chain(state: Any) -> ChainSnapshot:
    """One chain stand-in from the plain values a bridge request carries."""
    asked = state or {}
    return ChainSnapshot(
        blocks=[BlockSnapshot(**row) for row in asked.get("blocks") or []],
        transactions=[TxSnapshot(**row) for row in asked.get("transactions") or []],
        events=[EventSnapshot(**row) for row in asked.get("events") or []],
        block_number=asked.get("block_number", 0),
    )


def build_model(state: Any) -> TestnetTabModel:
    """One tab model from the plain values a bridge request carries."""
    asked = state or {}
    testnet = TestnetSnapshot(
        chain=build_chain(asked.get("chain")),
        acrv=AcrvSnapshot(
            balances=asked.get("balances"), mint_log=asked.get("mint_log")
        ),
        stats=asked.get("stats") or dict(EMPTY_CHAIN_STATS),
        result=asked.get("result"),
    )
    bridge = BridgeSnapshot() if asked.get("bridge") else None
    return TestnetTabModel(testnet=testnet, bridge=bridge)


TAB_MODEL: Optional[TestnetTabModel] = None


def constant_view() -> dict:
    """Every value this tab carries that no run of it can change."""
    return {
        "method": METHOD,
        "logger_name": LOGGER_NAME,
        "accessible_name": ACCESSIBLE_NAME,
        "tab_title": TAB_TITLE,
        "net_label_text": NET_LABEL_TEXT,
        "chain_id": CHAIN_ID,
        "section_titles": list(SECTION_TITLES),
        "colors": [CYAN, GREEN, AMBER, RED, MAGENTA, MUTED, PANEL, NO_COLOR],
        "tier_colors": dict(TIER_COLORS),
        "tier_fallback_color": TIER_FALLBACK_COLOR,
        "event_colors": dict(EVENT_COLORS),
        "event_fallback_color": EVENT_FALLBACK_COLOR,
        "styles": {
            "section": SECTION_STYLE,
            "table": TABLE_STYLE,
            "title": TITLE_STYLE,
            "separator": SEPARATOR_STYLE,
            "spin": SPIN_STYLE,
            "combo": COMBO_STYLE,
            "price": PRICE_STYLE,
            "run_button": RUN_BUTTON_STYLE,
            "stress_button": STRESS_BUTTON_STYLE,
            "reset_button": RESET_BUTTON_STYLE,
            "log": LOG_STYLE,
            "label_format": LABEL_STYLE_FORMAT,
        },
        "label_weights": [LABEL_WEIGHT_BOLD, LABEL_WEIGHT_NORMAL],
        "label_defaults": [LABEL_DEFAULT_COLOR, LABEL_DEFAULT_SIZE, LABEL_DEFAULT_BOLD],
        "stat_keys": list(STAT_KEYS),
        "stat_source_keys": dict(STAT_SOURCE_KEYS),
        "stat_supply_keys": list(STAT_SUPPLY_KEYS),
        "stat_placeholder": STAT_PLACEHOLDER,
        "stat_sizes": [STAT_KEY_SIZE, STAT_VALUE_SIZE],
        "stat_formats": [STAT_COUNT_FORMAT, STAT_SUPPLY_FORMAT],
        "control_labels": [BOTS_LABEL, SYMBOL_LABEL, SEASON_LABEL, ORACLE_LABEL],
        "bots": [BOTS_MINIMUM, BOTS_MAXIMUM, BOTS_DEFAULT, BOTS_WIDTH_PX],
        "season": [SEASON_MINIMUM, SEASON_MAXIMUM, SEASON_DEFAULT, SEASON_WIDTH_PX],
        "symbols": list(SYMBOLS),
        "symbol_default": SYMBOL_DEFAULT,
        "symbol_width_px": SYMBOL_WIDTH_PX,
        "oracle": [
            ORACLE_MINIMUM,
            ORACLE_MAXIMUM,
            ORACLE_DEFAULT,
            ORACLE_DECIMALS,
            ORACLE_WIDTH_PX,
        ],
        "oracle_held": [
            ORACLE_MINIMUM_VALUE,
            ORACLE_MAXIMUM_VALUE,
            ORACLE_DEFAULT_VALUE,
        ],
        "request_no_round": REQUEST_NO_ROUND,
        "oracle_symbol": ORACLE_SYMBOL,
        "button_texts": [RUN_BUTTON_TEXT, STRESS_BUTTON_TEXT, RESET_BUTTON_TEXT],
        "columns": {
            "blocks": list(BLOCK_COLUMNS),
            "transactions": list(TX_COLUMNS),
            "events": list(EVENT_COLUMNS),
            "holders": list(HOLDER_COLUMNS),
        },
        "table_max_heights": [
            BLOCK_TABLE_MAX_HEIGHT_PX,
            TX_TABLE_MAX_HEIGHT_PX,
            EVENT_TABLE_MAX_HEIGHT_PX,
            HOLDER_TABLE_MAX_HEIGHT_PX,
            TABLE_DEFAULT_MAX_HEIGHT_PX,
        ],
        "log_max_height_px": LOG_MAX_HEIGHT_PX,
        "log_read_only": LOG_READ_ONLY,
        "row_limits": [
            BLOCK_ROW_LIMIT,
            TX_ROW_LIMIT,
            EVENT_ROW_LIMIT,
            HOLDER_ROW_LIMIT,
            EVENT_ARG_LIMIT,
        ],
        "hash_chars": [
            BLOCK_HASH_CHARS,
            TX_HASH_CHARS,
            FROM_ADDR_CHARS,
            WALLET_CHARS,
            WINNER_CHARS,
            ADJ_TX_CHARS,
        ],
        "hash_tail": HASH_TAIL,
        "row_colors": {
            "blocks": list(BLOCK_ROW_COLORS),
            "transactions": list(TX_ROW_COLORS),
        },
        "formats": {
            "block_age": BLOCK_AGE_FORMAT,
            "gas": GAS_FORMAT,
            "holder_balance": HOLDER_BALANCE_FORMAT,
            "event_arg": EVENT_ARG_FORMAT,
            "event_arg_join": EVENT_ARG_JOIN,
            "log_time": LOG_TIME_FORMAT,
            "log_line": LOG_LINE_FORMAT,
        },
        "token_decimals": TOKEN_DECIMALS,
        "no_tier_text": NO_TIER_TEXT,
        "actions": dict(ACTIONS),
        "bridge_signals": list(BRIDGE_SIGNALS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "autostart_timers": list(AUTOSTART_TIMERS),
        "refresh_interval_ms": REFRESH_INTERVAL_MS,
        "refresh_names": list(REFRESH_NAMES),
        "refresh_fail_limit": REFRESH_FAIL_LIMIT,
        "refresh_fail_attribute": REFRESH_FAIL_ATTRIBUTE,
        "refresh_stderr_format": REFRESH_STDERR_FORMAT,
        "refresh_log_format": REFRESH_LOG_FORMAT,
        "bus_topics": list(BUS_TOPICS),
        "content_margins": list(CONTENT_MARGINS),
        "content_spacing": CONTENT_SPACING,
        "splitter": [
            SPLITTER_HANDLE_WIDTH_PX,
            SPLITTER_CHILDREN_COLLAPSIBLE,
            SPLITTER_ORIENTATION,
            SPLITTER_ORIENTATION_VALUE,
        ],
        "alignment": ALIGNMENT,
        "alignment_value": ALIGNMENT_VALUE,
        "label_default_alignment_value": LABEL_DEFAULT_ALIGNMENT_VALUE,
        "separator_frame_shape": SEPARATOR_FRAME_SHAPE,
        "separator_frame_shape_value": SEPARATOR_FRAME_SHAPE_VALUE,
        "header_resize_mode": HEADER_RESIZE_MODE,
        "header_resize_value": HEADER_RESIZE_VALUE,
        "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
        "edit_triggers_none": EDIT_TRIGGERS_NONE,
        "edit_triggers_none_value": EDIT_TRIGGERS_NONE_VALUE,
        "edit_triggers_default_value": EDIT_TRIGGERS_DEFAULT_VALUE,
        "selection_behavior_rows": SELECTION_BEHAVIOR_ROWS,
        "selection_behavior_rows_value": SELECTION_BEHAVIOR_ROWS_VALUE,
        "selection_behavior_default_value": SELECTION_BEHAVIOR_DEFAULT_VALUE,
        "reset_dialog": [RESET_DIALOG_TITLE, RESET_DIALOG_TEXT],
        "reset_messages": [
            RESET_BRIDGE_REASON,
            RESET_BRIDGE_MESSAGE,
            RESET_STANDALONE_MESSAGE,
        ],
        "chain_reset_message": CHAIN_RESET_MESSAGE,
        "chain_reset_color": CHAIN_RESET_COLOR,
        "run_messages": [
            RUN_STARTING_MESSAGE,
            RUN_COMPLETE_MESSAGE,
            RUN_WINNER_MESSAGE,
            RUN_ADJ_MESSAGE,
            RUN_ERROR_MESSAGE,
        ],
        "bridge_messages": [
            BRIDGE_WINNER_MESSAGE,
            BRIDGE_FAILED_MESSAGE,
            BRIDGE_UNKNOWN_COMPETITION,
            BRIDGE_UNKNOWN_TIER,
            BRIDGE_NO_WINNER,
            BRIDGE_NO_TOKENS,
        ],
        "stress_messages": [
            STRESS_STARTING_MESSAGE,
            STRESS_DONE_MESSAGE,
            STRESS_TIER_MESSAGE,
            STRESS_TIER_FORMAT,
            STRESS_TIER_JOIN,
            STRESS_ERROR_MESSAGE,
        ],
        "stress_counts": [STRESS_COUNT, STRESS_BOTS],
        "result_keys": [
            RESULT_COMPETITION_KEY,
            RESULT_WINNER_KEY,
            RESULT_TIER_KEY,
            RESULT_TOKENS_KEY,
            RESULT_ADJ_KEY,
        ],
        "error_key": ERROR_KEY,
        "tier_counts_key": TIER_COUNTS_KEY,
        "request_fields": list(REQUEST_FIELDS),
        "empty_chain_stats": dict(EMPTY_CHAIN_STATS),
        "reset_attributes": list(RESET_ATTRIBUTES),
        "skin": dict(SKIN),
        "tab_style_sheet": TAB_STYLE_SHEET,
        "no_color": NO_COLOR,
        "no_path": NO_PATH,
        "run_paths": list(RUN_PATHS),
        "stress_paths": list(STRESS_PATHS),
        "reset_paths": list(RESET_PATHS),
        "bridge_paths": list(BRIDGE_PATHS),
        "wired_paths": list(WIRED_PATHS),
        "call_names": list(CALL_NAMES),
    }


def build_view_model(model: Optional[TestnetTabModel] = None) -> dict:
    """Return the whole tab state as one serialisable dict."""
    state = TestnetTabModel() if model is None else model
    nodes = state.setup_ui()
    answer = constant_view()
    answer.update(
        {
            "widgets": nodes,
            "widget_names": [node["name"] for node in nodes],
            "widget_kinds": [node["kind"] for node in nodes],
            "widget_parents": [node["parent"] for node in nodes],
            "widget_children": widget_children(nodes),
            "widget_index": widget_index(nodes),
            "stat_values": dict(state.stat_values),
            "buttons_enabled": {
                "run_button": state.run_enabled,
                "stress_button": state.stress_enabled,
            },
            "rows": {
                "blocks": state.block_rows,
                "transactions": state.tx_rows,
                "events": state.event_rows,
                "holders": state.holder_rows,
            },
            "log_lines": list(state.log_lines),
            "refresh_failures": list(state.refresh_failures),
            "wiring_refusals": [list(item) for item in state.wiring_refusals],
            "stderr_lines": list(state.stderr_lines),
            "log_records": list(state.log_records),
            "wired_path": state.wired_path,
            "run_path": state.run_path,
            "stress_path": state.stress_path,
            "reset_path": state.reset_path,
            "bridge_path": state.bridge_path,
            "comp_count": state.comp_count,
            "has_bridge": state.bridge is not None,
            "calls": [list(call) for call in state.calls],
        }
    )
    return answer


def view_model(params: dict) -> dict:
    """Bridge handler for ``testnet_tab.state``.

    Reads ``reset``, ``state``, ``refresh`` and ``now`` from the request
    parameters. A call with no parameters answers with the tab the last
    call built; ``reset`` is what a fresh open sends. ``refresh`` fills
    the four tables from the chain, which is the poll the shipped tab
    runs on its own timer and the renderer asks for instead.

    The answer leaves under `src.gui.color_alpha.css_colours`, so a Qt
    alpha byte becomes the share a browser reads. `build_view_model`
    keeps the byte, because the shipped tab writes those same sheets
    into `setStyleSheet` and Qt counts alpha in bytes.
    """
    global TAB_MODEL
    if params.get("reset", False) or "state" in params:
        TAB_MODEL = build_model(params.get("state"))
    if params.get("refresh", False) and TAB_MODEL is not None:
        TAB_MODEL.refresh_all(params.get("now"))
    return css_colours(build_view_model(TAB_MODEL))
