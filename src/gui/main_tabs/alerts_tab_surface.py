"""alerts_tab_surface.py -- the Notifications and Alerts tab, without Qt.

Describes the tab the operator uses to wire Telegram and SMS alerts, to
see how each event is routed, and to read the notification history. The
tab holds 23 nodes in two panes: the left pane carries the two channel
forms and the Save button, the right pane carries the routing table and
the history table with its Acknowledge All button.

``AlertsTabModel`` holds the tab's state. ``setup_ui`` returns the widget
tree in build order. ``test_telegram`` sends one test message and reports
which of its four paths it took. ``save_config`` writes the two channel
settings back. ``acknowledge_all`` clears the unread count and repaints.
``refresh`` reads the manager and rebuilds both tables, the status line
and the unread line.

``ManagerSnapshot``, ``NotificationRecord`` and ``Priority`` are plain
stand-ins for the notification manager and its records, so the tab can be
driven over the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``alerts_tab.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.alerts_tab``, so a value changed on one side alone is reported.
Nothing here imports Qt.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .. import design_system as ds

METHOD = "alerts_tab.state"

ACCESSIBLE_NAME = "Notifications and Alerts tab"

CONTENT_MARGINS = (8, 8, 8, 8)
CONTENT_SPACING = 8
PANE_MARGINS = (0, 0, 0, 0)

SPLITTER_ORIENTATION = "Horizontal"
SPLITTER_ORIENTATION_VALUE = 1
SPLITTER_HANDLE_WIDTH = 5
SPLITTER_CHILDREN_COLLAPSIBLE = False
SPLITTER_SIZES = (350, 550)

TELEGRAM_GROUP_TITLE = "Telegram Bot"
SMS_GROUP_TITLE = "SMS Alerts"
RULES_GROUP_TITLE = "Event Routing"
HISTORY_GROUP_TITLE = "Notification History"

TELEGRAM_BOT_LABEL = "Bot Token:"
CHAT_LABEL = "Chat ID:"
PHONE_LABEL = "Phone:"
SPANNING_LABEL = ""

TELEGRAM_BOT_PLACEHOLDER = "Bot token from @BotFather"
CHAT_PLACEHOLDER = "Chat ID (use @userinfobot)"
PHONE_PLACEHOLDER = "+1234567890"

ECHO_NORMAL = "Normal"
ECHO_HIDDEN = "Password"
ECHO_VALUES = {ECHO_NORMAL: 0, ECHO_HIDDEN: 2}

TEST_BUTTON_TEXT = "Test Telegram"
SAVE_BUTTON_TEXT = "Save Configuration"
ACK_BUTTON_TEXT = "Acknowledge All"

STATUS_TEXT = "Notifications: Active"
STATUS_SEPARATOR = " | "
TELEGRAM_CONNECTED_TEXT = "TG: Connected"
SMS_CONNECTED_TEXT = "SMS: Connected"
SAVED_TEXT = "Configuration saved!"

UNREAD_FORMAT = "Unread: {unread}"
UNREAD_START_TEXT = "Unread: 0"

SMS_STATUS_TEXT = "Not configured"
TELEGRAM_STATUS_TEXT = ""
EMPTY_STYLE = ""

STATUS_STYLE = f"color: {ds.PRIMARY}; font-size: 14px; font-weight: bold;"
UNREAD_WARNING_STYLE = f"color: {ds.WARNING}; font-size: 12px;"
UNREAD_QUIET_STYLE = f"color: {ds.CARD_METRIC_LABEL}; font-size: 12px;"
SMS_STATUS_STYLE = f"color: {ds.CARD_METRIC_LABEL};"
TELEGRAM_ERROR_STYLE = f"color: {ds.ERROR};"
TELEGRAM_SUCCESS_STYLE = f"color: {ds.SUCCESS};"

GROUP_BOX_STYLE = (
    f"QGroupBox {{ background: {ds.SURFACE_CHART}; "
    f"border: 1px solid {ds.CARD_METRIC_BORDER}; "
    f"border-radius: 6px; color: {ds.PRIMARY}; }}"
)

TEST_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.VIZ_PANEL_BORDER}; "
    f"color: {ds.STATUS_INFO}; "
    f"border: 1px solid {ds.STATUS_INFO}; "
    f"border-radius: 4px; padding: 6px; }}"
)

SAVE_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.PRIMARY}; "
    f"color: {ds.SURFACE_CHART}; "
    "border: none; border-radius: 4px; padding: 8px; "
    "font-weight: bold; }"
    f"QPushButton:hover {{ background: {ds.SETTINGS_PRIMARY_HOVER}; }}"
)

ACK_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.VIZ_PANEL_BORDER}; "
    f"color: {ds.WARNING}; "
    f"border: 1px solid {ds.WARNING}; "
    f"border-radius: 4px; padding: 4px 10px; }}"
)

RULES_COLUMNS = ("Event", "Priority", "In-App", "Telegram", "Sound")
HISTORY_COLUMNS = ("Time", "Priority", "Title", "Message", "Channels")
RULES_COLUMN_COUNT = 5
HISTORY_COLUMN_COUNT = 5

HEADER_RESIZE_MODE = "Stretch"
HEADER_RESIZE_VALUE = 1
ALTERNATING_ROW_COLORS = True
VERTICAL_HEADER_VISIBLE = False

EDIT_TRIGGERS_DEFAULT = ("DoubleClicked", "EditKeyPressed", "AnyKeyPressed")
EDIT_TRIGGERS_DEFAULT_VALUE = 26
EDIT_TRIGGERS_NONE: tuple[str, ...] = ()
EDIT_TRIGGERS_NONE_VALUE = 0

ALIGNMENT = "AlignCenter"
ALIGNMENT_VALUE = 132

NO_COLOR = ""
NO_ALIGNMENT = ""
YES_TEXT = "Yes"
NO_TEXT = "No"
CELL_YES_COLOR = ds.SUCCESS
CELL_NO_COLOR = ds.TEXT_PLACEHOLDER
UNACKNOWLEDGED_COLOR = ds.TEXT_HIGH

CHANNEL_IN_APP = "IN_APP"
CHANNEL_TELEGRAM = "TELEGRAM"
CHANNEL_SOUND = "SOUND"
ROUTED_CHANNELS = (CHANNEL_IN_APP, CHANNEL_TELEGRAM, CHANNEL_SOUND)

PRIORITY_LOW = "low"
PRIORITY_MEDIUM = "medium"
PRIORITY_HIGH = "high"
PRIORITY_CRITICAL = "critical"
DEFAULT_PRIORITY = PRIORITY_MEDIUM
PRIORITY_COLORS = {
    PRIORITY_LOW: ds.CARD_METRIC_LABEL,
    PRIORITY_MEDIUM: ds.STATUS_INFO,
    PRIORITY_HIGH: ds.WARNING,
    PRIORITY_CRITICAL: ds.ERROR,
}
PRIORITY_FALLBACK_COLOR = ds.CARD_METRIC_LABEL

EVENT_UNDERSCORE = "_"
EVENT_SPACE = " "
TIME_FORMAT = "%H:%M:%S"
MESSAGE_MAX_CHARS = 60
HISTORY_LIMIT = 100
CHANNEL_JOIN = ", "

PRIORITY_COLUMN = 1
COLORED_FROM_COLUMN = 2

CONFIG_TELEGRAM_KEY = "telegram_configured"
CONFIG_SMS_KEY = "sms_configured"
CONFIG_RULES_KEY = "rules"
RULE_CHANNELS_KEY = "channels"
RULE_PRIORITY_KEY = "priority"

TELEGRAM_TEST_TITLE = "Acervator"
TELEGRAM_TEST_MESSAGE = "Test notification — Telegram is configured correctly!"
TELEGRAM_TEST_PRIORITY = None
TELEGRAM_MISSING_TEXT = "Enter bot token and chat ID first"
TELEGRAM_SENT_TEXT = "Test sent successfully!"
TELEGRAM_FAILED_FORMAT = "Failed: {error}"

TEST_PATH_NO_MANAGER = "no_manager"
TEST_PATH_MISSING = "missing_credentials"
TEST_PATH_SENT = "sent"
TEST_PATH_FAILED = "failed"
TEST_PATHS = (
    TEST_PATH_NO_MANAGER,
    TEST_PATH_MISSING,
    TEST_PATH_SENT,
    TEST_PATH_FAILED,
)

SAVE_PATH_NO_MANAGER = "no_manager"
SAVE_PATH_SAVED = "saved"
SAVE_PATHS = (SAVE_PATH_NO_MANAGER, SAVE_PATH_SAVED)

ACK_PATH_NO_MANAGER = "no_manager"
ACK_PATH_ACKNOWLEDGED = "acknowledged"
ACK_PATHS = (ACK_PATH_NO_MANAGER, ACK_PATH_ACKNOWLEDGED)

REFRESH_PATH_NO_MANAGER = "no_manager"
REFRESH_PATH_PAINTED = "painted"
REFRESH_PATHS = (REFRESH_PATH_NO_MANAGER, REFRESH_PATH_PAINTED)

NO_PATH = ""

SETUP_START = "setup.start"
SETUP_RETURN = "setup.return"
TEST_START = "test.start"
TEST_CONFIGURED = "test.configured"
TEST_SENT = "test.sent"
TEST_FAILED = "test.failed"
TEST_RETURN = "test.return"
SAVE_START = "save.start"
SAVE_TELEGRAM = "save.telegram"
SAVE_SMS = "save.sms"
SAVE_RETURN = "save.return"
ACK_START = "ack.start"
ACK_CALLED = "ack.called"
ACK_RETURN = "ack.return"
REFRESH_START = "refresh.start"
REFRESH_CONFIG = "refresh.config"
REFRESH_UNREAD = "refresh.unread"
REFRESH_STATUS = "refresh.status"
REFRESH_RULES = "refresh.rules"
REFRESH_HISTORY = "refresh.history"
REFRESH_RETURN = "refresh.return"

ACTIONS = {
    "test_button.clicked": "test_telegram",
    "save_button.clicked": "save_config",
    "ack_button.clicked": "acknowledge_all",
}

TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()
SKIN: dict[str, str] = {}
TAB_STYLE_SHEET = ""


def widget(name: str, kind: str, parent: str, **values: Any) -> dict:
    """One node of the tab's widget tree, with its parent and its values."""
    return {"name": name, "kind": kind, "parent": parent, **values}


WIDGETS = (
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
    widget(
        "main_split",
        "QSplitter",
        "tab",
        orientation=SPLITTER_ORIENTATION,
        handle_width=SPLITTER_HANDLE_WIDTH,
        children_collapsible=SPLITTER_CHILDREN_COLLAPSIBLE,
        sizes=SPLITTER_SIZES,
    ),
    widget(
        "left",
        "QWidget",
        "main_split",
        layout="QVBoxLayout",
        margins=PANE_MARGINS,
    ),
    widget(
        "status_label",
        "QLabel",
        "left",
        text=STATUS_TEXT,
        style_sheet=STATUS_STYLE,
    ),
    widget(
        "unread_label",
        "QLabel",
        "left",
        text=UNREAD_START_TEXT,
        style_sheet=UNREAD_WARNING_STYLE,
    ),
    widget(
        "telegram_group",
        "QGroupBox",
        "left",
        title=TELEGRAM_GROUP_TITLE,
        style_sheet=GROUP_BOX_STYLE,
        layout="QFormLayout",
    ),
    widget(
        "token_input",
        "QLineEdit",
        "telegram_group",
        row_label=TELEGRAM_BOT_LABEL,
        placeholder=TELEGRAM_BOT_PLACEHOLDER,
        echo_mode=ECHO_HIDDEN,
    ),
    widget(
        "chat_input",
        "QLineEdit",
        "telegram_group",
        row_label=CHAT_LABEL,
        placeholder=CHAT_PLACEHOLDER,
        echo_mode=ECHO_NORMAL,
    ),
    widget(
        "test_button",
        "QPushButton",
        "telegram_group",
        row_label=SPANNING_LABEL,
        text=TEST_BUTTON_TEXT,
        style_sheet=TEST_BUTTON_STYLE,
        enabled=True,
        action="test_telegram",
    ),
    widget(
        "telegram_status",
        "QLabel",
        "telegram_group",
        row_label=SPANNING_LABEL,
        text=TELEGRAM_STATUS_TEXT,
        style_sheet=EMPTY_STYLE,
    ),
    widget(
        "sms_group",
        "QGroupBox",
        "left",
        title=SMS_GROUP_TITLE,
        style_sheet=GROUP_BOX_STYLE,
        layout="QFormLayout",
    ),
    widget(
        "phone_input",
        "QLineEdit",
        "sms_group",
        row_label=PHONE_LABEL,
        placeholder=PHONE_PLACEHOLDER,
        echo_mode=ECHO_NORMAL,
    ),
    widget(
        "sms_status",
        "QLabel",
        "sms_group",
        row_label=SPANNING_LABEL,
        text=SMS_STATUS_TEXT,
        style_sheet=SMS_STATUS_STYLE,
    ),
    widget(
        "save_button",
        "QPushButton",
        "left",
        text=SAVE_BUTTON_TEXT,
        style_sheet=SAVE_BUTTON_STYLE,
        enabled=True,
        action="save_config",
    ),
    widget("left_stretch", "stretch", "left"),
    widget(
        "right",
        "QWidget",
        "main_split",
        layout="QVBoxLayout",
        margins=PANE_MARGINS,
    ),
    widget(
        "rules_group",
        "QGroupBox",
        "right",
        title=RULES_GROUP_TITLE,
        style_sheet=GROUP_BOX_STYLE,
        layout="QVBoxLayout",
        stretch=1,
    ),
    widget(
        "rules_table",
        "QTableWidget",
        "rules_group",
        columns=RULES_COLUMNS,
        column_count=RULES_COLUMN_COUNT,
        resize_mode=HEADER_RESIZE_MODE,
        alternating_row_colors=ALTERNATING_ROW_COLORS,
        vertical_header_visible=VERTICAL_HEADER_VISIBLE,
        edit_triggers=EDIT_TRIGGERS_DEFAULT,
    ),
    widget(
        "history_group",
        "QGroupBox",
        "right",
        title=HISTORY_GROUP_TITLE,
        style_sheet=GROUP_BOX_STYLE,
        layout="QVBoxLayout",
        stretch=1,
    ),
    widget("ack_row", "QHBoxLayout", "history_group"),
    widget("ack_stretch", "stretch", "ack_row"),
    widget(
        "ack_button",
        "QPushButton",
        "ack_row",
        text=ACK_BUTTON_TEXT,
        style_sheet=ACK_BUTTON_STYLE,
        enabled=True,
        action="acknowledge_all",
    ),
    widget(
        "history_table",
        "QTableWidget",
        "history_group",
        columns=HISTORY_COLUMNS,
        column_count=HISTORY_COLUMN_COUNT,
        resize_mode=HEADER_RESIZE_MODE,
        alternating_row_colors=ALTERNATING_ROW_COLORS,
        vertical_header_visible=VERTICAL_HEADER_VISIBLE,
        edit_triggers=EDIT_TRIGGERS_NONE,
    ),
)

WIDGET_NAMES = tuple(node["name"] for node in WIDGETS)
WIDGET_KINDS = {node["name"]: node["kind"] for node in WIDGETS}
WIDGET_PARENTS = {node["name"]: node["parent"] for node in WIDGETS}
WIDGET_CHILDREN = {
    parent: tuple(node["name"] for node in WIDGETS if node["parent"] == parent)
    for parent in dict.fromkeys(node["parent"] for node in WIDGETS)
}
WIDGET_INDEX = {
    node["name"]: WIDGET_CHILDREN[node["parent"]].index(node["name"])
    for node in WIDGETS
}
BUTTON_NAMES = tuple(node["name"] for node in WIDGETS if node["kind"] == "QPushButton")
BUTTONS_ENABLED = {name: True for name in BUTTON_NAMES}


class Priority:
    """One notification priority, carrying the word the cell prints."""

    def __init__(self, value: Any) -> None:
        self.value = value


class NotificationRecord:
    """One history row: when it fired, what it said, and who saw it."""

    def __init__(
        self,
        timestamp: Any = 0.0,
        priority: Any = PRIORITY_MEDIUM,
        title: Any = "",
        message: Any = "",
        channels_sent: Any = (),
        acknowledged: bool = False,
    ) -> None:
        self.timestamp = timestamp
        self.priority = priority if hasattr(priority, "value") else Priority(priority)
        self.title = title
        self.message = message
        self.channels_sent = list(channels_sent)
        self.acknowledged = acknowledged


class ManagerSnapshot:
    """A notification manager built from plain values.

    Carries the three reads the tab makes -- the config, the unread count
    and the history -- and records the four writes, so a caller over the
    bridge can drive the tab with no manager wired.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        history: Any = (),
        unread: Any = 0,
    ) -> None:
        self._config = {} if config is None else config
        self._history = list(history)
        self._unread = unread
        self.telegram_calls: list = []
        self.sms_calls: list = []
        self.sent: list = []
        self.acknowledge_count = 0

    def get_config(self) -> dict:
        return self._config

    @property
    def unacknowledged_count(self) -> Any:
        return self._unread

    @property
    def history(self) -> list:
        return list(self._history)

    def configure_telegram(self, bot_token: Any, chat_id: Any) -> None:
        self.telegram_calls.append([bot_token, chat_id])

    def configure_sms(self, phone: Any) -> None:
        self.sms_calls.append([phone])

    def acknowledge_all(self) -> None:
        self.acknowledge_count += 1
        for record in self._history:
            record.acknowledged = True
        self._unread = 0

    def send_telegram(self, title: Any, message: Any, priority: Any) -> None:
        self.sent.append([title, message, priority])

    _send_telegram = send_telegram


def event_title(event: Any) -> str:
    """One routing event's name as the first column prints it."""
    return event.replace(EVENT_UNDERSCORE, EVENT_SPACE).title()


def routed_text(channels: Any, channel: str) -> str:
    """Whether one channel carries an event, as the cell prints it."""
    return YES_TEXT if channel in channels else NO_TEXT


def routed_color(text: Any) -> str:
    """The colour a routing answer is drawn in."""
    return CELL_YES_COLOR if text == YES_TEXT else CELL_NO_COLOR


def priority_color(priority: Any) -> str:
    """The colour one priority word is drawn in, or the low-priority grey."""
    return PRIORITY_COLORS.get(priority, PRIORITY_FALLBACK_COLOR)


def clock_text(timestamp: Any) -> str:
    """One notification's local time of day, as the first column prints it."""
    return time.strftime(TIME_FORMAT, time.localtime(timestamp))


def cell(text: Any, color: str) -> dict:
    """One table cell: its text, its colour and its alignment."""
    return {"text": text, "color": color, "alignment": ALIGNMENT}


def blank_row(width: int) -> list:
    """One row that exists with no cell written into it yet.

    The table is given its row count before any cell is built, so a row
    that is never reached stays empty rather than absent.
    """
    return [
        {"text": None, "color": NO_COLOR, "alignment": NO_ALIGNMENT}
        for _ in range(width)
    ]


class AlertsTabModel:
    """The Notifications and Alerts tab: its widgets, its state, its paths.

    ``setup_ui`` returns the widget tree in build order. ``test_telegram``,
    ``save_config``, ``acknowledge_all`` and ``refresh`` are the four
    actions the tab performs, and each records the path it took. Every
    step is appended to ``calls`` in the order the shipped tab makes it.
    """

    def __init__(self, notification_manager: Any = None) -> None:
        self.manager = notification_manager
        self.accessible_name = ACCESSIBLE_NAME
        self.status_text: Any = STATUS_TEXT
        self.status_style = STATUS_STYLE
        self.unread_text: Any = UNREAD_START_TEXT
        self.unread_style = UNREAD_WARNING_STYLE
        self.telegram_status_text: Any = TELEGRAM_STATUS_TEXT
        self.telegram_status_style = EMPTY_STYLE
        self.sms_status_text: Any = SMS_STATUS_TEXT
        self.sms_status_style = SMS_STATUS_STYLE
        self.token: Any = ""
        self.chat_id: Any = ""
        self.phone: Any = ""
        self.rules_rows: list = []
        self.history_rows: list = []
        self.test_path = NO_PATH
        self.save_path = NO_PATH
        self.ack_path = NO_PATH
        self.refresh_path = NO_PATH
        self.calls: list = []

    def setup_ui(self) -> list:
        """The tab's widget tree, in the order the tab builds it."""
        self.calls.append([SETUP_START])
        built = [dict(node) for node in WIDGETS]
        self.calls.append([SETUP_RETURN, len(built)])
        return built

    def test_telegram(self) -> dict:
        """Send one test message to Telegram and report what came back."""
        self.calls.append([TEST_START, self.manager is not None])
        if not self.manager:
            return self._test_finish(TEST_PATH_NO_MANAGER)
        token = self.token.strip()
        chat_id = self.chat_id.strip()
        if not token or not chat_id:
            self.telegram_status_text = TELEGRAM_MISSING_TEXT
            self.telegram_status_style = TELEGRAM_ERROR_STYLE
            return self._test_finish(TEST_PATH_MISSING)
        self.manager.configure_telegram(token, chat_id)
        self.calls.append([TEST_CONFIGURED, token, chat_id])
        try:
            self.manager._send_telegram(
                TELEGRAM_TEST_TITLE,
                TELEGRAM_TEST_MESSAGE,
                TELEGRAM_TEST_PRIORITY,
            )
            self.telegram_status_text = TELEGRAM_SENT_TEXT
            self.telegram_status_style = TELEGRAM_SUCCESS_STYLE
            self.calls.append([TEST_SENT])
            return self._test_finish(TEST_PATH_SENT)
        except Exception as exc:
            self.telegram_status_text = TELEGRAM_FAILED_FORMAT.format(error=exc)
            self.telegram_status_style = TELEGRAM_ERROR_STYLE
            self.calls.append([TEST_FAILED, type(exc).__name__])
            return self._test_finish(TEST_PATH_FAILED)

    def _test_finish(self, path: str) -> dict:
        """Keep the Telegram test's path and report the line it wrote."""
        self.test_path = path
        answer = {
            "path": path,
            "text": self.telegram_status_text,
            "color": self.telegram_status_style,
        }
        self.calls.append([TEST_RETURN, path, self.telegram_status_text])
        return answer

    def save_config(self) -> dict:
        """Write the two channel settings back to the manager."""
        self.calls.append([SAVE_START, self.manager is not None])
        if not self.manager:
            return self._save_finish(SAVE_PATH_NO_MANAGER)
        token = self.token.strip()
        chat_id = self.chat_id.strip()
        if token and chat_id:
            self.manager.configure_telegram(token, chat_id)
            self.calls.append([SAVE_TELEGRAM, token, chat_id])
        phone = self.phone.strip()
        if phone:
            self.manager.configure_sms(phone)
            self.calls.append([SAVE_SMS, phone])
        self.status_text = SAVED_TEXT
        return self._save_finish(SAVE_PATH_SAVED)

    def _save_finish(self, path: str) -> dict:
        """Keep the Save path and report the status line it left."""
        self.save_path = path
        answer = {"path": path, "status_text": self.status_text}
        self.calls.append([SAVE_RETURN, path, self.status_text])
        return answer

    def acknowledge_all(self) -> dict:
        """Mark every notification read, then repaint the tab."""
        self.calls.append([ACK_START, self.manager is not None])
        if self.manager:
            self.manager.acknowledge_all()
            self.calls.append([ACK_CALLED])
            self.refresh()
            return self._ack_finish(ACK_PATH_ACKNOWLEDGED)
        return self._ack_finish(ACK_PATH_NO_MANAGER)

    def _ack_finish(self, path: str) -> dict:
        """Keep the Acknowledge path and report the unread line it left."""
        self.ack_path = path
        answer = {"path": path, "unread_text": self.unread_text}
        self.calls.append([ACK_RETURN, path, self.unread_text])
        return answer

    def refresh(self, notification_manager: Any = None) -> dict:
        """Read the manager and rebuild both tables and both header lines."""
        manager = notification_manager or self.manager
        self.calls.append([REFRESH_START, manager is not None])
        if not manager:
            return self._refresh_finish(REFRESH_PATH_NO_MANAGER)
        config = manager.get_config()
        self.calls.append([REFRESH_CONFIG, len(config)])
        unread = manager.unacknowledged_count
        self.unread_text = UNREAD_FORMAT.format(unread=unread)
        if unread > 0:
            self.unread_style = UNREAD_WARNING_STYLE
        else:
            self.unread_style = UNREAD_QUIET_STYLE
        self.calls.append([REFRESH_UNREAD, self.unread_text])
        parts = [STATUS_TEXT]
        if config.get(CONFIG_TELEGRAM_KEY, False):
            parts.append(TELEGRAM_CONNECTED_TEXT)
        if config.get(CONFIG_SMS_KEY, False):
            parts.append(SMS_CONNECTED_TEXT)
        self.status_text = STATUS_SEPARATOR.join(parts)
        self.calls.append([REFRESH_STATUS, self.status_text])
        rules = config.get(CONFIG_RULES_KEY, {})
        self.rules_rows = [blank_row(RULES_COLUMN_COUNT) for _ in rules]
        for index, (event, rule) in enumerate(rules.items()):
            self.rules_rows[index] = self._rule_row(event, rule)
        self.calls.append([REFRESH_RULES, len(self.rules_rows)])
        recent = manager.history[-HISTORY_LIMIT:]
        self.history_rows = [blank_row(HISTORY_COLUMN_COUNT) for _ in recent]
        for index, record in enumerate(reversed(recent)):
            self.history_rows[index] = self._history_row(record)
        self.calls.append([REFRESH_HISTORY, len(self.history_rows)])
        return self._refresh_finish(REFRESH_PATH_PAINTED)

    def _rule_row(self, event: Any, rule: Any) -> list:
        """One Event Routing row: its five cells and their colours."""
        channels = rule.get(RULE_CHANNELS_KEY, [])
        texts = [
            event_title(event),
            rule.get(RULE_PRIORITY_KEY, DEFAULT_PRIORITY),
        ] + [routed_text(channels, channel) for channel in ROUTED_CHANNELS]
        row = []
        for column, text in enumerate(texts):
            color = NO_COLOR
            if column >= COLORED_FROM_COLUMN:
                color = routed_color(text)
            row.append(cell(text, color))
        return row

    def _history_row(self, record: Any) -> list:
        """One Notification History row: its five cells and their colours."""
        texts = [
            clock_text(record.timestamp),
            record.priority.value,
            record.title,
            record.message[:MESSAGE_MAX_CHARS],
            CHANNEL_JOIN.join(record.channels_sent),
        ]
        row = []
        for column, text in enumerate(texts):
            color = NO_COLOR
            if column == PRIORITY_COLUMN:
                color = priority_color(text)
            if not record.acknowledged:
                color = UNACKNOWLEDGED_COLOR
            row.append(cell(text, color))
        return row

    def _refresh_finish(self, path: str) -> dict:
        """Keep the refresh path and report the two lines and two tables."""
        self.refresh_path = path
        answer = {
            "path": path,
            "status_text": self.status_text,
            "unread_text": self.unread_text,
            "rules_rows": [list(row) for row in self.rules_rows],
            "history_rows": [list(row) for row in self.history_rows],
        }
        self.calls.append(
            [REFRESH_RETURN, path, len(self.rules_rows), len(self.history_rows)]
        )
        return answer


TAB_MODEL = AlertsTabModel()


def build_manager(spec: Optional[dict]) -> Optional[ManagerSnapshot]:
    """One manager built from a request's plain values, or None."""
    if spec is None:
        return None
    return ManagerSnapshot(
        config=spec.get("config"),
        history=[
            NotificationRecord(
                timestamp=record.get("timestamp", 0.0),
                priority=record.get("priority", PRIORITY_MEDIUM),
                title=record.get("title", ""),
                message=record.get("message", ""),
                channels_sent=record.get("channels_sent", ()),
                acknowledged=record.get("acknowledged", False),
            )
            for record in spec.get("history", ())
        ],
        unread=spec.get("unread", 0),
    )


def build_view_model(
    model: AlertsTabModel,
    fields: Optional[dict] = None,
    action: str = "",
) -> dict:
    """Return the whole tab state as one serialisable dict."""
    if fields is not None:
        model.token = fields.get("token", model.token)
        model.chat_id = fields.get("chat_id", model.chat_id)
        model.phone = fields.get("phone", model.phone)
    if action == "test_telegram":
        model.test_telegram()
    elif action == "save_config":
        model.save_config()
    elif action == "acknowledge_all":
        model.acknowledge_all()
    elif action == "refresh":
        model.refresh()
    return {
        "method": METHOD,
        "accessible_name": model.accessible_name,
        "widgets": [dict(node) for node in WIDGETS],
        "widget_names": list(WIDGET_NAMES),
        "widget_kinds": dict(WIDGET_KINDS),
        "widget_parents": dict(WIDGET_PARENTS),
        "widget_children": {
            parent: list(names) for parent, names in WIDGET_CHILDREN.items()
        },
        "widget_index": dict(WIDGET_INDEX),
        "button_names": list(BUTTON_NAMES),
        "buttons_enabled": dict(BUTTONS_ENABLED),
        "content_margins": list(CONTENT_MARGINS),
        "content_spacing": CONTENT_SPACING,
        "pane_margins": list(PANE_MARGINS),
        "splitter_orientation": SPLITTER_ORIENTATION,
        "splitter_orientation_value": SPLITTER_ORIENTATION_VALUE,
        "splitter_handle_width": SPLITTER_HANDLE_WIDTH,
        "splitter_children_collapsible": SPLITTER_CHILDREN_COLLAPSIBLE,
        "splitter_sizes": list(SPLITTER_SIZES),
        "group_titles": [
            TELEGRAM_GROUP_TITLE,
            SMS_GROUP_TITLE,
            RULES_GROUP_TITLE,
            HISTORY_GROUP_TITLE,
        ],
        "row_labels": [TELEGRAM_BOT_LABEL, CHAT_LABEL, PHONE_LABEL, SPANNING_LABEL],
        "placeholders": [TELEGRAM_BOT_PLACEHOLDER, CHAT_PLACEHOLDER, PHONE_PLACEHOLDER],
        "echo_modes": [ECHO_NORMAL, ECHO_HIDDEN],
        "echo_values": dict(ECHO_VALUES),
        "button_texts": [TEST_BUTTON_TEXT, SAVE_BUTTON_TEXT, ACK_BUTTON_TEXT],
        "rules_columns": list(RULES_COLUMNS),
        "history_columns": list(HISTORY_COLUMNS),
        "rules_column_count": RULES_COLUMN_COUNT,
        "history_column_count": HISTORY_COLUMN_COUNT,
        "header_resize_mode": HEADER_RESIZE_MODE,
        "header_resize_value": HEADER_RESIZE_VALUE,
        "alternating_row_colors": ALTERNATING_ROW_COLORS,
        "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
        "edit_triggers_default": list(EDIT_TRIGGERS_DEFAULT),
        "edit_triggers_default_value": EDIT_TRIGGERS_DEFAULT_VALUE,
        "edit_triggers_none": list(EDIT_TRIGGERS_NONE),
        "edit_triggers_none_value": EDIT_TRIGGERS_NONE_VALUE,
        "alignment": ALIGNMENT,
        "alignment_value": ALIGNMENT_VALUE,
        "styles": {
            "status": STATUS_STYLE,
            "unread_warning": UNREAD_WARNING_STYLE,
            "unread_quiet": UNREAD_QUIET_STYLE,
            "sms_status": SMS_STATUS_STYLE,
            "telegram_error": TELEGRAM_ERROR_STYLE,
            "telegram_success": TELEGRAM_SUCCESS_STYLE,
            "group_box": GROUP_BOX_STYLE,
            "test_button": TEST_BUTTON_STYLE,
            "save_button": SAVE_BUTTON_STYLE,
            "ack_button": ACK_BUTTON_STYLE,
            "empty": EMPTY_STYLE,
        },
        "texts": {
            "status": STATUS_TEXT,
            "status_separator": STATUS_SEPARATOR,
            "telegram_connected": TELEGRAM_CONNECTED_TEXT,
            "sms_connected": SMS_CONNECTED_TEXT,
            "saved": SAVED_TEXT,
            "unread_format": UNREAD_FORMAT,
            "unread_start": UNREAD_START_TEXT,
            "sms_status": SMS_STATUS_TEXT,
            "telegram_status": TELEGRAM_STATUS_TEXT,
            "telegram_missing": TELEGRAM_MISSING_TEXT,
            "telegram_sent": TELEGRAM_SENT_TEXT,
            "telegram_failed_format": TELEGRAM_FAILED_FORMAT,
            "telegram_test_title": TELEGRAM_TEST_TITLE,
            "telegram_test_message": TELEGRAM_TEST_MESSAGE,
            "yes": YES_TEXT,
            "no": NO_TEXT,
            "time_format": TIME_FORMAT,
            "channel_join": CHANNEL_JOIN,
            "event_underscore": EVENT_UNDERSCORE,
            "event_space": EVENT_SPACE,
        },
        "telegram_test_priority": TELEGRAM_TEST_PRIORITY,
        "cell_colors": {
            "yes": CELL_YES_COLOR,
            "no": CELL_NO_COLOR,
            "unacknowledged": UNACKNOWLEDGED_COLOR,
            "none": NO_COLOR,
        },
        "priority_colors": dict(PRIORITY_COLORS),
        "priority_fallback_color": PRIORITY_FALLBACK_COLOR,
        "priorities": [
            PRIORITY_LOW,
            PRIORITY_MEDIUM,
            PRIORITY_HIGH,
            PRIORITY_CRITICAL,
        ],
        "default_priority": DEFAULT_PRIORITY,
        "routed_channels": list(ROUTED_CHANNELS),
        "channels": [CHANNEL_IN_APP, CHANNEL_TELEGRAM, CHANNEL_SOUND],
        "config_keys": [CONFIG_TELEGRAM_KEY, CONFIG_SMS_KEY, CONFIG_RULES_KEY],
        "rule_keys": [RULE_CHANNELS_KEY, RULE_PRIORITY_KEY],
        "message_max_chars": MESSAGE_MAX_CHARS,
        "history_limit": HISTORY_LIMIT,
        "priority_column": PRIORITY_COLUMN,
        "colored_from_column": COLORED_FROM_COLUMN,
        "test_paths": list(TEST_PATHS),
        "save_paths": list(SAVE_PATHS),
        "ack_paths": list(ACK_PATHS),
        "refresh_paths": list(REFRESH_PATHS),
        "no_path": NO_PATH,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "skin": dict(SKIN),
        "tab_style_sheet": TAB_STYLE_SHEET,
        "status_text": model.status_text,
        "status_style": model.status_style,
        "unread_text": model.unread_text,
        "unread_style": model.unread_style,
        "telegram_status_text": model.telegram_status_text,
        "telegram_status_style": model.telegram_status_style,
        "sms_status_text": model.sms_status_text,
        "sms_status_style": model.sms_status_style,
        "token": model.token,
        "chat_id": model.chat_id,
        "phone": model.phone,
        "rules_rows": [list(row) for row in model.rules_rows],
        "history_rows": [list(row) for row in model.history_rows],
        "test_path": model.test_path,
        "save_path": model.save_path,
        "ack_path": model.ack_path,
        "refresh_path": model.refresh_path,
        "has_manager": model.manager is not None,
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``alerts_tab.state``.

    Reads ``reset``, ``manager``, ``fields`` and ``action`` from the
    request parameters. The tab keeps what the operator typed between
    calls, so the model persists; ``reset`` is what a fresh open sends.
    """
    global TAB_MODEL
    if params.get("reset", False):
        TAB_MODEL = AlertsTabModel(build_manager(params.get("manager")))
    elif "manager" in params:
        TAB_MODEL.manager = build_manager(params.get("manager"))
    return build_view_model(
        TAB_MODEL,
        params.get("fields"),
        params.get("action", ""),
    )
