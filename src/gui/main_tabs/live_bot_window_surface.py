"""live_bot_window_surface.py -- the one-window live bot runner and all of it.

Describes the window the operator opens to run one ScrummingBot on its
own. It holds a "Bot Configuration" group with an exchange picker, a
base picker, a target-asset picker, a target-dollar box and two masked
credential fields, a START and a STOP button with a status line, and
three read-only panes below: Console, API and Trading Activity.

The three panes are described as far as this window reads them: what
each pane holds, how many blocks it keeps, and which lines reach which
pane. ``PaneModel`` drops the oldest block exactly where the shipped
pane drops it, so a window driven with the same lines holds the same
text on both sides.

``controls_reach_the_window`` is False. The shipped window builds the
configuration grid inside a group box it then drops, so the pickers,
the target-dollar box and the two credential fields never reach the
screen and every value they carry is recorded here instead.

Every step is appended to ``calls`` rather than sent, so nothing here
writes to a log file or to a disk.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``live_bot_window.state`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger("acervator.gui.live_bot")

METHOD = "live_bot_window.state"

LOGGER_NAME = "acervator.gui.live_bot"

ACCESSIBLE_NAME = "Lite Live Bot Window"
WINDOW_TITLE = "Acervator — Lite Live Bot"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 700

CONFIG_GROUP_TITLE = "Bot Configuration"
CONFIG_GROUPS_BUILT = 2
DROPPED_GROUP_INDEX = 0

EXCHANGE_LABEL = "Exchange:"
BASE_LABEL = "Base (quote):"
TARGET_LABEL = "Target asset:"
TARGET_DOLLARS_LABEL = "Target $:"

# The two masked fields are placed and read as one pair, in this order.
CREDENTIAL_LABELS = ("API key:", "Secret:")
CREDENTIAL_FIELDS = ("api_key", "api_signature")

NOT_WIRED_FORMAT = "no {name} is wired to this window"

DEFAULT_EXCHANGE_ID = "coinbase"

DEFAULT_PAIRS = {
    "USD": ("BTC", "ETH", "SOL", "ADA", "AVAX", "DOT", "BONK", "PEPE", "WIF"),
    "USDT": ("BTC", "ETH", "SOL", "ADA", "AVAX", "DOT", "MATIC", "LINK"),
    "USDC": ("BTC", "ETH", "SOL"),
    "EUR": ("BTC", "ETH"),
}
DEFAULT_BASE = "USD"
NO_TARGET_ASSET = ""

TARGET_MIN = 1.0
TARGET_MAX = 1_000_000.0
TARGET_DECIMALS = 2
TARGET_DEFAULT = 200.00
TARGET_STEP = 10.0

ECHO_MODE = "Password"
NO_CREDENTIAL = ""

GRID_CELLS = (
    ("exchange_label", 0, 0, 1, 1),
    ("exchange_picker", 0, 1, 1, 1),
    ("base_label", 0, 2, 1, 1),
    ("base_picker", 0, 3, 1, 1),
    ("target_label", 0, 4, 1, 1),
    ("target_picker", 0, 5, 1, 1),
    ("target_dollars_label", 0, 6, 1, 1),
    ("target_dollars_box", 0, 7, 1, 1),
    ("api_key_label", 1, 0, 1, 1),
    ("api_key_field", 1, 1, 1, 3),
    ("secret_label", 1, 4, 1, 1),
    ("secret_field", 1, 5, 1, 3),
)

START_LABEL = "START"
STOP_LABEL = "STOP"
START_ENABLED_AT_REST = True
STOP_ENABLED_AT_REST = False

STATUS_IDLE = "Status: idle"
STATUS_RUNNING_FORMAT = "Status: running {symbol}"

CONSOLE_TITLE = "Console"
API_TITLE = "API"
ACTIVITY_TITLE = "Trading Activity"
PANE_TITLES = (CONSOLE_TITLE, API_TITLE, ACTIVITY_TITLE)
PANE_STRETCHES = (2, 2, 1)
PANES_ROOT_STRETCH = 1
PANE_READ_ONLY = True
PANE_WRAP_MODE = "NoWrap"
PANE_MAX_BLOCKS = 5000
PANE_STYLE = (
    "QPlainTextEdit { font-family: 'Menlo','Consolas',monospace; "
    "font-size: 11pt; background: #0e1420; color: #c8d4e3; }"
)
NO_TEXT = ""
ONE_BLOCK = 1
BLOCK_SEPARATOR = "\n"

BUS_TOPICS = (
    "bot.log",
    "trade.filled",
    "exchange.request",
    "exchange.response",
)
LOG_TOPIC = "bot.log"
FILL_TOPIC = "trade.filled"
REQUEST_TOPIC = "exchange.request"
RESPONSE_TOPIC = "exchange.response"

MESSAGE_KEY = "message"
NO_MESSAGE = ""
ACTIVITY_KEYWORDS = (
    "buy ",
    "sell ",
    "fold ",
    "scrum ",
    "initial entry",
    "fire-window",
    "fold rebuy",
    "executed",
)

SIDE_KEY = "side"
SYMBOL_KEY = "symbol"
AMOUNT_KEY = "amount"
PRICE_KEY = "price"
UNKNOWN_FIELD = "?"
NO_AMOUNT = 0.0
NO_PRICE = 0.0

ALREADY_RUNNING_TEXT = "Bot already running — STOP first"
SELECT_PAIR_TITLE = "Select pair"
SELECT_PAIR_TEXT = "Pick a target asset before starting."
CREDENTIALS_TITLE = "API credentials required"
CREDENTIALS_TEXT = "Both API key and secret are required for live trading."

STARTING_FORMAT = "Starting: {exchange_id} {symbol} target=${target_dollars:.2f}"
CONNECTED_FORMAT = "Connected to {exchange_id}"
CONNECT_FAILED_FORMAT = "CONNECT FAILED: {error}"
BOT_CRASHED_FORMAT = "BOT CRASHED: {error}"
DISCONNECT_FAILED_LOG = "Lite Live Bot status refresh failed: %s"
STOPPING_TEXT = "Stopping bot (graceful shutdown)..."
STOP_ERROR_FORMAT = "STOP ERROR: {error}"
STOPPED_TEXT = "Stopped."

THREAD_NAME = "live-bot-window"
THREAD_DAEMON = True
STOP_TIMEOUT_S = 10
POLL_INTERVAL_S = 1.0
BOT_MODE_NAME = "SCRUMMING"

SYMBOL_FORMAT = "{target_asset}/{base}"

SKIN: dict = {}
STYLE_SHEET = ""
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()

SIGNAL_NAMES = ("console", "api", "activity")

ACTIONS = {
    "base_changed": "on_base_changed",
    "start_clicked": "on_start",
    "stop_clicked": "on_stop",
    "console_line": "append_console",
    "api_line": "append_api",
    "activity_line": "append_activity",
}

LIVE_ITEM_NAMES = (
    "start_button",
    "stop_button",
    "status_label",
    "console_pane",
    "api_pane",
    "activity_pane",
)
DROPPED_ITEM_NAMES = (
    "exchange_label",
    "exchange_picker",
    "base_label",
    "base_picker",
    "target_label",
    "target_picker",
    "target_dollars_label",
    "target_dollars_box",
    "api_key_label",
    "api_key_field",
    "secret_label",
    "secret_field",
)
CONTROLS_REACH_THE_WINDOW = False

WINDOW_BUILT = "window.built"
PANES_BUILT = "panes.built"
SIGNALS_WIRED = "signals.wired"
BASE_CHANGED = "base.changed"
LOG_SEEN = "log.seen"
ACTIVITY_SEEN = "activity.seen"
FILL_SEEN = "fill.seen"
API_SEEN = "api.seen"
START_REFUSED = "start.refused"
START_WARNED = "start.warned"
SUBSCRIBED = "bus.subscribed"
THREAD_STARTED = "thread.started"
EXCHANGE_BUILT = "exchange.built"
CONNECT_FAILED = "connect.failed"
CONNECTED = "exchange.connected"
CONFIG_BUILT = "config.built"
BOT_BUILT = "bot.built"
BOT_CRASHED = "bot.crashed"
DISCONNECTED = "exchange.disconnected"
DISCONNECT_FAILED = "disconnect.failed"
STOP_ASKED = "stop.asked"
STOP_FAILED = "stop.failed"
UNSUBSCRIBED = "bus.unsubscribed"
UNSUBSCRIBE_FAILED = "unsubscribe.failed"
STOPPED = "window.stopped"
CLOSED = "window.closed"
LAUNCHED = "app.launched"
EXCHANGE_PICKED = "exchange.picked"
BASE_PICKED = "base.picked"
TARGET_PICKED = "target.picked"
PICK_IGNORED = "pick.ignored"
PRESS_IGNORED = "press.ignored"


def wired(found: Optional[Callable], name: str) -> Callable:
    """The collaborator wired under `name`, or a refusal naming what is absent."""
    if found is None:
        raise TypeError(NOT_WIRED_FORMAT.format(name=name))
    return found


def no_unsubscribe() -> None:
    """The way back off a topic when no bus was wired to this window."""


def target_assets(base: str) -> list:
    """The target assets one base currency offers, in the order shown."""
    return list(DEFAULT_PAIRS.get(base, ()))


def symbol_for(target_asset: str, base: str) -> str:
    """The pair the window trades, written the way the venue writes it."""
    return SYMBOL_FORMAT.format(target_asset=target_asset, base=base)


def is_activity_line(message: str) -> bool:
    """Whether one log line also belongs in the Trading Activity pane."""
    lower = message.lower()
    return any(keyword in lower for keyword in ACTIVITY_KEYWORDS)


def fill_line(data: dict) -> str:
    """The Trading Activity line one filled order writes."""
    side = data.get(SIDE_KEY, UNKNOWN_FIELD)
    symbol = data.get(SYMBOL_KEY, UNKNOWN_FIELD)
    amount = data.get(AMOUNT_KEY, NO_AMOUNT)
    price = data.get(PRICE_KEY, NO_PRICE)
    return f"FILL: {side.upper()} {amount:.6f} {symbol} @ ${price:.8f}"


def api_line(topic: str, data: object) -> str:
    """The API pane line one exchange request or response writes."""
    return f"[{topic}] {data}"


def appended(text: str, line: str) -> str:
    """`text` with `line` added as the shipped pane adds it.

    The shipped pane holds one empty block before anything is written,
    so the first line replaces it rather than following a blank one. A
    carriage return is dropped, as the pane drops it.
    """
    written = line.replace("\r\n", BLOCK_SEPARATOR).replace("\r", BLOCK_SEPARATOR)
    if text == NO_TEXT:
        return written
    return text + BLOCK_SEPARATOR + written


def capped(text: str, max_blocks: int) -> str:
    """`text` with its oldest blocks dropped until `max_blocks` remain."""
    if max_blocks <= 0:
        return text
    blocks = text.split(BLOCK_SEPARATOR)
    if len(blocks) <= max_blocks:
        return text
    return BLOCK_SEPARATOR.join(blocks[len(blocks) - max_blocks :])


class PaneModel:
    """One read-only pane: its heading, its look and the text it holds.

    ``append`` adds one block the way the shipped pane adds it and drops
    the oldest blocks past ``max_blocks``. A line that is not text
    reaches the shipped pane as nothing, because the signal carrying it
    accepts text only, so it is added here as nothing too.
    """

    def __init__(self, title: str, max_blocks: int = PANE_MAX_BLOCKS) -> None:
        self.title = title
        self.max_blocks = max_blocks
        self.read_only = PANE_READ_ONLY
        self.wrap_mode = PANE_WRAP_MODE
        self.style_sheet = PANE_STYLE
        self.text = NO_TEXT
        self.appends = 0

    def append(self, line: object) -> None:
        """Add one block, then drop the oldest blocks past the cap."""
        written = line if isinstance(line, str) else NO_TEXT
        self.text = capped(appended(self.text, written), self.max_blocks)
        self.appends += 1

    def block_count(self) -> int:
        """How many blocks the pane holds, blank ones counted."""
        if self.text == NO_TEXT:
            return ONE_BLOCK
        return self.text.count(BLOCK_SEPARATOR) + ONE_BLOCK


def offered_exchange_ids() -> tuple:
    """``SUPPORTED_EXCHANGES`` in id order, what ``exchange_ids`` is filled from.

    ``SUPPORTED_EXCHANGES`` is imported when first asked, so importing this
    file loads no exchange library.
    """
    from ...exchange.ccxt_connector import SUPPORTED_EXCHANGES

    return tuple(sorted(SUPPORTED_EXCHANGES.keys()))


class LiveBotWindowModel:
    """The one-window live bot runner: its controls, its buttons, its panes.

    ``on_start`` reads the pickers and the credential fields, subscribes
    to the four bus topics and hands one worker the pair to trade.
    ``run_bot`` is that worker. ``on_stop`` asks the bot to stop, drops
    the four subscriptions and puts the buttons back. Every step is
    appended to ``calls``.
    """

    def __init__(
        self,
        event_bus: object = None,
        exchange_factory: Optional[Callable] = None,
        config_factory: Optional[Callable] = None,
        bot_factory: Optional[Callable] = None,
        thread_factory: Optional[Callable] = None,
        warn: Optional[Callable] = None,
        stop_caller: Optional[Callable] = None,
    ) -> None:
        self.event_bus = event_bus
        self.exchange_factory = exchange_factory
        self.config_factory = config_factory
        self.bot_factory = bot_factory
        self.thread_factory = thread_factory
        self.warn = warn
        self.stop_caller = stop_caller
        self.accessible_name = ACCESSIBLE_NAME
        self.window_title = WINDOW_TITLE
        self.window_width = WINDOW_WIDTH
        self.window_height = WINDOW_HEIGHT
        self.bot = None
        self.exchange = None
        self.bot_thread = None
        self.loop = None
        self.unsubs: list = []
        self.calls: list = []
        self.warnings: list = []
        self.threads: list = []
        self.subscribed: list = []
        self.configs: list = []
        self.exchange_ids = list(offered_exchange_ids())
        self.exchange_id = DEFAULT_EXCHANGE_ID
        self.bases = list(DEFAULT_PAIRS)
        self.base = DEFAULT_BASE
        self.target_assets: list = []
        self.target_asset = NO_TARGET_ASSET
        self.target_dollars = TARGET_DEFAULT
        self.api_key = NO_CREDENTIAL
        self.api_secret = NO_CREDENTIAL
        self.start_enabled = START_ENABLED_AT_REST
        self.stop_enabled = STOP_ENABLED_AT_REST
        self.status_text = STATUS_IDLE
        self.console = PaneModel(CONSOLE_TITLE)
        self.api = PaneModel(API_TITLE)
        self.activity = PaneModel(ACTIVITY_TITLE)
        self.controls_reach_the_window = CONTROLS_REACH_THE_WINDOW
        self.build_ui()
        self.wire_signals()

    # ----- building the window -----

    def build_ui(self) -> None:
        """Put the configuration group above the three panes."""
        self.build_controls()
        self.build_panes()
        self.calls.append([WINDOW_BUILT, self.window_title])

    def build_controls(self) -> None:
        """Fill the configuration group and set the buttons at rest."""
        self.on_base_changed(self.base)

    def build_panes(self) -> None:
        """Give the three panes their headings and their look."""
        self.calls.append([PANES_BUILT, list(PANE_TITLES)])

    def wire_signals(self) -> None:
        """Point the three line carriers at the three panes."""
        self.calls.append([SIGNALS_WIRED, list(SIGNAL_NAMES)])

    def on_base_changed(self, base: str) -> None:
        """Rewrite the target-asset picker for one base currency.

        The base picker itself is not moved. The shipped slot empties
        the target picker and refills it, and an empty picker holds
        nothing, so a base offering no asset leaves the picker blank.
        """
        self.target_assets = target_assets(base)
        first = self.target_assets[0] if self.target_assets else NO_TARGET_ASSET
        self.target_asset = first
        self.calls.append([BASE_CHANGED, base, list(self.target_assets)])

    def choose_exchange(self, exchange_id: str) -> None:
        """Move the exchange picker, which ignores an id it does not offer."""
        if exchange_id not in self.exchange_ids:
            self.calls.append([PICK_IGNORED, exchange_id])
            return
        self.exchange_id = exchange_id
        self.calls.append([EXCHANGE_PICKED, exchange_id])

    def choose_base(self, base: str) -> None:
        """Move the base picker, which ignores a base it does not offer."""
        if base not in self.bases:
            self.calls.append([PICK_IGNORED, base])
            return
        self.base = base
        self.calls.append([BASE_PICKED, base])
        self.on_base_changed(base)

    def choose_target_asset(self, target_asset: str) -> None:
        """Move the target picker, which ignores an asset it does not offer."""
        if target_asset not in self.target_assets:
            self.calls.append([PICK_IGNORED, target_asset])
            return
        self.target_asset = target_asset
        self.calls.append([TARGET_PICKED, target_asset])

    # ----- the three panes -----

    def append_console(self, line: object) -> None:
        """Add one line to the Console pane."""
        self.console.append(line)

    def append_api(self, line: object) -> None:
        """Add one line to the API pane."""
        self.api.append(line)

    def append_activity(self, line: object) -> None:
        """Add one line to the Trading Activity pane."""
        self.activity.append(line)

    # ----- what the bus sends the window -----

    def on_bot_log(self, event: "BusEvent") -> None:
        """One bot log line: to the Console, and to Activity when it trades."""
        message = event.data.get(MESSAGE_KEY, NO_MESSAGE)
        self.append_console(message)
        self.calls.append([LOG_SEEN])
        if is_activity_line(message):
            self.append_activity(message)
            self.calls.append([ACTIVITY_SEEN])

    def on_trade_filled(self, event: "BusEvent") -> None:
        """One filled order, written into the Trading Activity pane."""
        line = fill_line(event.data)
        self.append_activity(line)
        self.calls.append([FILL_SEEN, line])

    def on_api_event(self, event: "BusEvent") -> None:
        """One exchange request or response, written into the API pane."""
        line = api_line(event.topic, event.data)
        self.append_api(line)
        self.calls.append([API_SEEN, event.topic])

    # ----- START -----

    def press_start(self) -> None:
        """A press on START, which a disabled button ignores."""
        if not self.start_enabled:
            self.calls.append([PRESS_IGNORED, START_LABEL])
            return
        self.on_start()

    def press_stop(self) -> None:
        """A press on STOP, which a disabled button ignores."""
        if not self.stop_enabled:
            self.calls.append([PRESS_IGNORED, STOP_LABEL])
            return
        self.on_stop()

    def on_start(self) -> None:
        """Read the controls, take the four topics and hand off one worker."""
        if self.bot is not None:
            self.append_console(ALREADY_RUNNING_TEXT)
            self.calls.append([START_REFUSED, ALREADY_RUNNING_TEXT])
            return
        exchange_id = self.exchange_id
        base = self.base
        target_asset = self.target_asset
        if not target_asset:
            self.raise_warning(SELECT_PAIR_TITLE, SELECT_PAIR_TEXT)
            return
        symbol = symbol_for(target_asset, base)
        target_dollars = float(self.target_dollars)
        api_key = self.api_key.strip()
        api_secret = self.api_secret.strip()
        if not api_key or not api_secret:
            self.raise_warning(CREDENTIALS_TITLE, CREDENTIALS_TEXT)
            return
        self.unsubs = [
            self.subscribe(LOG_TOPIC, self.on_bot_log),
            self.subscribe(FILL_TOPIC, self.on_trade_filled),
            self.subscribe(REQUEST_TOPIC, self.on_api_event),
            self.subscribe(RESPONSE_TOPIC, self.on_api_event),
        ]
        self.append_console(
            STARTING_FORMAT.format(
                exchange_id=exchange_id, symbol=symbol, target_dollars=target_dollars
            )
        )
        args = (
            exchange_id,
            base,
            target_asset,
            symbol,
            target_dollars,
            api_key,
            api_secret,
        )
        self.bot_thread = self.start_thread(args)
        self.start_enabled = False
        self.stop_enabled = True
        self.status_text = STATUS_RUNNING_FORMAT.format(symbol=symbol)

    def raise_warning(self, title: str, text: str) -> None:
        """Put one warning box in front of the operator."""
        self.warnings.append([title, text])
        self.calls.append([START_WARNED, title])
        if self.warn:
            self.warn(title, text)

    def subscribe(self, topic: str, handler: Callable) -> Callable:
        """Take one bus topic and keep the way back off it."""
        self.subscribed.append(topic)
        self.calls.append([SUBSCRIBED, topic])
        if self.event_bus is None:
            return no_unsubscribe
        return self.event_bus.subscribe(topic, handler)

    def start_thread(self, args: tuple) -> object:
        """Hand the worker its pair on a thread of its own."""
        self.threads.append(
            {"args": list(args), "name": THREAD_NAME, "daemon": THREAD_DAEMON}
        )
        self.calls.append([THREAD_STARTED, THREAD_NAME])
        if self.thread_factory is None:
            return None
        thread = self.thread_factory(self.run_bot, args, THREAD_NAME, THREAD_DAEMON)
        thread.start()
        return thread

    # ----- the worker -----

    def run_bot(
        self,
        exchange_id: str,
        base: str,
        target_asset: str,
        symbol: str,
        target_dollars: float,
        api_key: str,
        api_secret: str,
    ) -> None:
        """Connect, build the bot, run it, and disconnect when it ends.

        A venue that refuses the connection ends the worker there and
        leaves the connection object in place. A config or a bot the
        worker cannot build ends the worker as well, and the connection
        it already opened is not closed.
        """
        self.exchange = wired(self.exchange_factory, "exchange_factory")(exchange_id)
        self.calls.append([EXCHANGE_BUILT, exchange_id])
        try:
            self.exchange.connect(api_key, api_secret)
        except Exception as exc:
            self.append_console(CONNECT_FAILED_FORMAT.format(error=exc))
            self.calls.append([CONNECT_FAILED, type(exc).__name__])
            return
        self.append_console(CONNECTED_FORMAT.format(exchange_id=exchange_id))
        self.calls.append([CONNECTED, exchange_id])
        config = wired(self.config_factory, "config_factory")(
            BOT_MODE_NAME,
            exchange_id=exchange_id,
            base_currency=base,
            target_asset=target_asset,
            symbol=symbol,
            target_balance=target_dollars,
        )
        self.configs.append(config)
        self.calls.append([CONFIG_BUILT, symbol])
        self.bot = wired(self.bot_factory, "bot_factory")(config, self.exchange)
        self.calls.append([BOT_BUILT, symbol])
        try:
            self.bot.start()
        except Exception as exc:
            self.append_console(BOT_CRASHED_FORMAT.format(error=exc))
            self.calls.append([BOT_CRASHED, type(exc).__name__])
        finally:
            if self.exchange:
                try:
                    self.exchange.disconnect()
                    self.calls.append([DISCONNECTED])
                except Exception as exc:
                    logger.warning(DISCONNECT_FAILED_LOG, exc)
                    self.calls.append([DISCONNECT_FAILED, type(exc).__name__])

    # ----- STOP -----

    def on_stop(self) -> None:
        """Ask the bot to stop, drop the four topics and reset the buttons."""
        if self.bot is None:
            return
        self.append_console(STOPPING_TEXT)
        if self.loop is not None and self.loop.is_running():
            self.calls.append([STOP_ASKED, STOP_TIMEOUT_S])
            try:
                wired(self.stop_caller, "stop_caller")(self.bot, STOP_TIMEOUT_S)
            except Exception as exc:
                self.append_console(STOP_ERROR_FORMAT.format(error=exc))
                self.calls.append([STOP_FAILED, type(exc).__name__])
        for unsub in self.unsubs:
            try:
                unsub()
                self.calls.append([UNSUBSCRIBED])
            except Exception as exc:
                self.calls.append([UNSUBSCRIBE_FAILED, type(exc).__name__])
        self.unsubs = []
        self.bot = None
        self.exchange = None
        self.start_enabled = True
        self.stop_enabled = False
        self.status_text = STATUS_IDLE
        self.append_console(STOPPED_TEXT)
        self.calls.append([STOPPED])

    def close_event(self) -> None:
        """Stop the bot before the window closes."""
        if self.bot is not None:
            self.on_stop()
        self.calls.append([CLOSED])


def launch(app_factory: Callable, show: Optional[Callable] = None) -> int:
    """Open the window on its own and return the code the app ends with."""
    app = app_factory()
    model = build_model()
    model.calls.append([LAUNCHED, model.window_title])
    if show is not None:
        show(model)
    return app.exec()


PANE_MODEL: Optional[LiveBotWindowModel] = None


def pane_model() -> LiveBotWindowModel:
    """The one window the bridge keeps between calls.

    Built on the first request, never at import: building one reads the
    pickers, and a window built while this module is being imported
    would settle before a caller can point it anywhere.
    """
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = LiveBotWindowModel()
    return PANE_MODEL


def build_model(**wiring: object) -> LiveBotWindowModel:
    """One window, wired to whatever the caller hands it."""
    return LiveBotWindowModel(**wiring)


def pane_view(pane: PaneModel) -> dict:
    """One pane as the window reads it."""
    return {
        "title": pane.title,
        "read_only": pane.read_only,
        "wrap_mode": pane.wrap_mode,
        "style_sheet": pane.style_sheet,
        "max_blocks": pane.max_blocks,
        "text": pane.text,
        "block_count": pane.block_count(),
        "appends": pane.appends,
    }


def build_view_model(model: LiveBotWindowModel) -> dict:
    """Return the whole surface state as one serialisable dict."""
    return {
        "method": METHOD,
        "accessible_name": model.accessible_name,
        "window_title": model.window_title,
        "window_width": model.window_width,
        "window_height": model.window_height,
        "config_group_title": CONFIG_GROUP_TITLE,
        "config_groups_built": CONFIG_GROUPS_BUILT,
        "dropped_group_index": DROPPED_GROUP_INDEX,
        "controls_reach_the_window": model.controls_reach_the_window,
        "live_item_names": list(LIVE_ITEM_NAMES),
        "dropped_item_names": list(DROPPED_ITEM_NAMES),
        "grid_cells": [list(cell) for cell in GRID_CELLS],
        "exchange_label": EXCHANGE_LABEL,
        "base_label": BASE_LABEL,
        "target_label": TARGET_LABEL,
        "target_dollars_label": TARGET_DOLLARS_LABEL,
        "credential_labels": list(CREDENTIAL_LABELS),
        "credential_fields": list(CREDENTIAL_FIELDS),
        "not_wired_format": NOT_WIRED_FORMAT,
        "exchange_ids": list(model.exchange_ids),
        "exchange_id": model.exchange_id,
        "default_exchange_id": DEFAULT_EXCHANGE_ID,
        "bases": list(model.bases),
        "base": model.base,
        "default_base": DEFAULT_BASE,
        "default_pairs": {key: list(value) for key, value in DEFAULT_PAIRS.items()},
        "target_assets": list(model.target_assets),
        "target_asset": model.target_asset,
        "no_target_asset": NO_TARGET_ASSET,
        "target_dollars": model.target_dollars,
        "target_min": TARGET_MIN,
        "target_max": TARGET_MAX,
        "target_decimals": TARGET_DECIMALS,
        "target_default": TARGET_DEFAULT,
        "target_step": TARGET_STEP,
        "echo_mode": ECHO_MODE,
        "api_key": model.api_key,
        "api_secret": model.api_secret,
        "no_credential": NO_CREDENTIAL,
        "start_label": START_LABEL,
        "stop_label": STOP_LABEL,
        "start_enabled": model.start_enabled,
        "stop_enabled": model.stop_enabled,
        "start_enabled_at_rest": START_ENABLED_AT_REST,
        "stop_enabled_at_rest": STOP_ENABLED_AT_REST,
        "status_text": model.status_text,
        "status_idle": STATUS_IDLE,
        "status_running_format": STATUS_RUNNING_FORMAT,
        "pane_titles": list(PANE_TITLES),
        "pane_stretches": list(PANE_STRETCHES),
        "panes_root_stretch": PANES_ROOT_STRETCH,
        "pane_read_only": PANE_READ_ONLY,
        "pane_wrap_mode": PANE_WRAP_MODE,
        "pane_max_blocks": PANE_MAX_BLOCKS,
        "pane_style": PANE_STYLE,
        "no_text": NO_TEXT,
        "one_block": ONE_BLOCK,
        "block_separator": BLOCK_SEPARATOR,
        "console": pane_view(model.console),
        "api": pane_view(model.api),
        "activity": pane_view(model.activity),
        "console_title": CONSOLE_TITLE,
        "api_title": API_TITLE,
        "activity_title": ACTIVITY_TITLE,
        "bus_topics": list(BUS_TOPICS),
        "log_topic": LOG_TOPIC,
        "fill_topic": FILL_TOPIC,
        "request_topic": REQUEST_TOPIC,
        "response_topic": RESPONSE_TOPIC,
        "subscribed": list(model.subscribed),
        "message_key": MESSAGE_KEY,
        "no_message": NO_MESSAGE,
        "activity_keywords": list(ACTIVITY_KEYWORDS),
        "side_key": SIDE_KEY,
        "symbol_key": SYMBOL_KEY,
        "amount_key": AMOUNT_KEY,
        "price_key": PRICE_KEY,
        "unknown_field": UNKNOWN_FIELD,
        "no_amount": NO_AMOUNT,
        "no_price": NO_PRICE,
        "already_running_text": ALREADY_RUNNING_TEXT,
        "select_pair_title": SELECT_PAIR_TITLE,
        "select_pair_text": SELECT_PAIR_TEXT,
        "credentials_title": CREDENTIALS_TITLE,
        "credentials_text": CREDENTIALS_TEXT,
        "warnings": [list(warning) for warning in model.warnings],
        "starting_format": STARTING_FORMAT,
        "connected_format": CONNECTED_FORMAT,
        "connect_failed_format": CONNECT_FAILED_FORMAT,
        "bot_crashed_format": BOT_CRASHED_FORMAT,
        "disconnect_failed_log": DISCONNECT_FAILED_LOG,
        "stopping_text": STOPPING_TEXT,
        "stop_error_format": STOP_ERROR_FORMAT,
        "stopped_text": STOPPED_TEXT,
        "thread_name": THREAD_NAME,
        "thread_daemon": THREAD_DAEMON,
        "bot_thread_held": model.bot_thread is not None,
        "threads": [dict(thread) for thread in model.threads],
        "stop_timeout_s": STOP_TIMEOUT_S,
        "poll_interval_s": POLL_INTERVAL_S,
        "bot_mode_name": BOT_MODE_NAME,
        "symbol_format": SYMBOL_FORMAT,
        "bot_built": model.bot is not None,
        "exchange_built": model.exchange is not None,
        "subscriptions_held": len(model.unsubs),
        "skin": dict(SKIN),
        "style_sheet": STYLE_SHEET,
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "signal_names": list(SIGNAL_NAMES),
        "actions": dict(ACTIONS),
        "logger_name": LOGGER_NAME,
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``live_bot_window.state``.

    Reads ``reset``, ``base``, ``exchange_id``, ``target_asset``,
    ``target_dollars``, ``api_key``, ``api_secret``, ``log``, ``fill``,
    ``api_event``, ``start``, ``stop`` and ``close`` from the request
    parameters. The window keeps its text and its buttons between calls
    because the shipped window does; ``reset`` is what a fresh paint
    sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = LiveBotWindowModel()
    model = pane_model()
    if params.get("exchange_id") is not None:
        model.choose_exchange(params["exchange_id"])
    if params.get("base") is not None:
        model.choose_base(params["base"])
    if params.get("target_asset") is not None:
        model.choose_target_asset(params["target_asset"])
    if params.get("target_dollars") is not None:
        model.target_dollars = params["target_dollars"]
    if params.get("api_key") is not None:
        model.api_key = params["api_key"]
    if params.get("api_secret") is not None:
        model.api_secret = params["api_secret"]
    if params.get("log") is not None:
        model.on_bot_log(BusEvent(LOG_TOPIC, params["log"]))
    if params.get("fill") is not None:
        model.on_trade_filled(BusEvent(FILL_TOPIC, params["fill"]))
    if params.get("api_event") is not None:
        model.on_api_event(BusEvent(REQUEST_TOPIC, params["api_event"]))
    if params.get("start", False):
        model.press_start()
    if params.get("stop", False):
        model.press_stop()
    if params.get("close", False):
        model.close_event()
    return build_view_model(model)


class BusEvent:
    """One bus message, as the window reads it."""

    def __init__(self, topic: str, data: object) -> None:
        self.topic = topic
        self.data = data
