"""settings_dialog_surface.py -- the Settings dialog, without Qt.

Describes the window the operator opens from the Settings menu. Nine
tabs -- User, Exchanges, Trading, TA Indicators, Phantom
Bots, Theme, Sound, SMS and AI Monitor -- above one Cancel and
one Save button.

``SettingsDialogModel`` holds the dialog's state. ``build`` lays out
every tab and then seeds every control from the settings store, which is
the order the shipped dialog does it in. ``save`` runs the Save button
and reports which groups persisted and which were discarded.
``test_api_connection``, ``add_exchange`` and ``remove_exchange`` run the
three Exchanges buttons. ``sfx_volume_changed``, ``test_sound`` and
``test_ai_handshake`` run the rest.

``SettingsSource``, ``StatusLogSink``, ``ValidatorSource``,
``ValidationResult`` and ``SoundEngineSink`` are plain stand-ins for the
settings store, the status line, the credential checker and the sound
engine, so the dialog can be driven over the bridge from values alone.
Nothing here reaches the operator's settings file: a ``SettingsSource``
holds its values in memory and records every write.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``settings_dialog.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.settings_dialog``, and nothing compares the two copies. Three
values are not written out and so cannot drift: the twelve indicator weights
read ``ta_engine.DEFAULT_WEIGHTS``, and ``crypto_exchange_items`` and
``passphrase_exchange_ids`` read the connector registry.
Nothing here imports Qt, and nothing runs at import time that
reads a clock, opens a file or reaches a network.
"""

from __future__ import annotations

import math
from functools import partial
from typing import Any, Optional

from ...core.encryption import looks_like_pem, unescape_pem_newlines, vault_phrase
from ...exchange.timeframes import ALL_TIMEFRAMES
from ...core.settings import CREDENTIAL_FIELDS, AppSettings
from ...core.sms_engine import (
    CARRIER_GATEWAYS,
    EMAIL_GATEWAY,
    FIELD_BOUNDS,
    SETTINGS_GROUP,
    TWILIO,
    SMSConfig,
    gateway_address,
)
from ...trading.ta_engine import DEFAULT_WEIGHTS
from ..color_alpha import ALPHA_HIGHEST, rgba

METHOD = "settings_dialog.state"

ACCESSIBLE_NAME = ""

WINDOW_TITLE_FORMAT = "Settings — {wing} Wing"
PLAIN_WINDOW_TITLE = "Settings"
MINIMUM_SIZE = (700, 600)

CRYPTO_WING = "crypto"
STOCK_WING = "stock"
KNOWN_WINGS = (CRYPTO_WING, STOCK_WING)
DEFAULT_WING = CRYPTO_WING

#: The wing each asset class name reaches. `asset_class_surface.normalise`
#: answers `stocks`, where this module's own wing word is `stock`.
CLASS_WINGS = {"crypto": CRYPTO_WING, "stocks": STOCK_WING}

USER_TAB = "User"
EXCHANGE_TAB = "Exchanges"
TRADING_TAB = "Trading"
TA_TAB = "TA Indicators"
PHANTOM_TAB = "Phantom Bots"
THEME_TAB = "Theme"
SOUND_TAB = "Sound"
SMS_TAB = "SMS"
AI_TAB = "AI Monitor"

TAB_TITLES = (
    USER_TAB,
    EXCHANGE_TAB,
    TRADING_TAB,
    TA_TAB,
    PHANTOM_TAB,
    THEME_TAB,
    SOUND_TAB,
    SMS_TAB,
    AI_TAB,
)

SCROLLING_TABS = (SMS_TAB, AI_TAB)

CANCEL_BUTTON_TEXT = "Cancel"
SAVE_BUTTON_TEXT = "Save"
SAVE_BUTTON_STYLE = "font-weight: bold; padding: 6px 24px;"
ACCENT_PROPERTY = "accent"
DANGER_PROPERTY = "danger"

from .. import design_system as ds  # noqa: E402
from . import asset_class_surface as acs  # noqa: E402
from .asset_class_surface import EQUITY_VENUES as EQUITY_EXCHANGE_IDS  # noqa: E402

EQUITY_ITEM_FORMAT = "{name} (planned, not yet live)"

STRONG_OPEN = "<b>"
STRONG_CLOSE = "</b>"
STRONG_WEIGHT = "bold"

STOCK_BANNER_LEAD = "Stock Wing:"
STOCK_BANNER_TAIL = (
    " equity-broker integration is "
    "queued — no live brokers are wired up yet. The "
    "list below shows the planned brokers; Add / Test "
    "are disabled until the broker connectors ship. "
    "Use the Crypto Wing for active trading today."
)
STOCK_BANNER_PIECES = (STOCK_BANNER_LEAD, STOCK_BANNER_TAIL)
STOCK_BANNER_TEXT = STRONG_OPEN + STOCK_BANNER_LEAD + STRONG_CLOSE + STOCK_BANNER_TAIL
STOCK_BANNER_WORD_WRAP = True

ALPHA_SCALE = ALPHA_HIGHEST
ALPHA_RECIPROCAL = 1.0 / ALPHA_SCALE
COLOUR_OPEN = "rgba("
COLOUR_JOIN = ","
COLOUR_CLOSE = ")"

BANNER_TINT = "#6699ff"
BANNER_TINT_RGB = (102, 153, 255)
BANNER_FILL_ALPHA = 30
BANNER_EDGE_ALPHA = 85
BANNER_BORDER_WIDTH_PX = 1
BANNER_BORDER_KIND = "solid"
BANNER_PADDING_PX = 8
BANNER_RADIUS_PX = 4


def banner_colour(alpha: Any) -> str:
    """The banner tint at `alpha`, built by `src.gui.color_alpha.rgba`.

    `COLOUR_OPEN` / `COLOUR_JOIN` / `COLOUR_CLOSE` publish the same
    format to the React side.
    """
    return rgba(BANNER_TINT, alpha)


STOCK_BANNER_STYLE_FORMAT = (
    "background: {fill}; "
    "color: {tint}; border: {width}px {kind} {edge}; "
    "padding: {padding}px; border-radius: {radius}px;"
)
STOCK_BANNER_STYLE = STOCK_BANNER_STYLE_FORMAT.format(
    fill=banner_colour(BANNER_FILL_ALPHA),
    tint=BANNER_TINT,
    width=BANNER_BORDER_WIDTH_PX,
    kind=BANNER_BORDER_KIND,
    edge=banner_colour(BANNER_EDGE_ALPHA),
    padding=BANNER_PADDING_PX,
    radius=BANNER_RADIUS_PX,
)
STOCK_DISABLED_TIP = (
    "Stock broker connector integration is queued; "
    "no live brokers ship yet. Use the Crypto Wing "
    "for active trading."
)
STOCK_DISABLED_CONTROLS = (
    "test_btn",
    "add_btn",
    "new_api_key",
    "new_api_secret",
    "new_passphrase",
    "pp_check",
)

CRYPTO_LIST_LABEL = "Configured Crypto Exchanges:"
STOCK_LIST_LABEL = "Configured Stock Brokers:"
CRYPTO_ADD_GROUP = "Add Crypto Exchange"
ADD_GROUP_FORMAT = "Add {name} {noun}"
REMOVE_BUTTON_TEXT = "Remove Selected"

EXCHANGE_STATUS_LABEL = "Exchange Status"

VENUE_STATE_VALIDATED = "validated"
VENUE_STATE_LOST = "lost"
VENUE_STATE_UNSET = "unset"

#: The ``design_system`` token each venue state paints with.
VENUE_STATE_TOKENS = {
    VENUE_STATE_VALIDATED: "SUCCESS",
    VENUE_STATE_LOST: "ERROR",
    VENUE_STATE_UNSET: "STATUS_NEUTRAL",
}
VENUE_STATE_COLOURS = {
    VENUE_STATE_VALIDATED: ds.SUCCESS,
    VENUE_STATE_LOST: ds.ERROR,
    VENUE_STATE_UNSET: ds.STATUS_NEUTRAL,
}
VENUE_STATE_WORDS = {
    VENUE_STATE_VALIDATED: "credentials validated",
    VENUE_STATE_LOST: "API connection lost",
    VENUE_STATE_UNSET: "no valid credentials",
}
VENUE_ROW_FORMAT = "{name} ({venue})"
VENUE_ROW_STYLE = (
    "color: {colour}; border: none; border-left: 3px solid {colour}; "
    "background: " + ds.SURFACE_CONTROL + "; padding: 4px 8px; text-align: left;"
)
VENUE_ROW_TOOLTIP = "{name} — {words}. Press to enter credentials."
VENUE_FORM_BOUND = "Enter credentials for {name}."
VENUE_HAS_NO_FORM = "{name} has no credential form on this tab."

#: The venues one page of the Exchange Status array holds. Past this a pages
#: button draws and the array still never scrolls.
VENUE_PAGE_HOLDS = 16

#: The columns one page divides into, so a further venue adds a row and never
#: a column. Four, because ``VENUE_PAGE_HOLDS`` then fills four rows of four
#: exactly, and the widest venue label measures 152px with its padding against
#: the 164px each of four columns holds in a dialog at its 700px floor.
VENUE_GRID_COLUMNS = 4

#: The lines one venue button is tall enough for, so a label too wide for one
#: line breaks on its space instead of being clipped.
VENUE_BUTTON_LINES = 2

VENUE_PAGES_FORMAT = "Page {page} of {pages} ▸"
VENUE_PAGES_TOOLTIP = "Press for page {next} of {pages}."

LOCK_GROUP_TITLE = "Higher-TF Lock Settings"
SMS_PROVIDER_GROUP_TITLE = "SMS Provider"
SMS_EVENTS_GROUP_TITLE = "Notification Events"
SMS_RATE_GROUP_TITLE = "Rate Limiting"
AI_API_GROUP_TITLE = "Claude API Connection"
AI_HANDSHAKE_GROUP_TITLE = "Handshake Authentication"
AI_BEHAVIOUR_GROUP_TITLE = "Monitor Behavior"
AI_STATUS_GROUP_TITLE = "Connection Status"

TA_HEADING = "Adjust indicator weights in the voting engine."
PHANTOM_HEADING = "Default Phantom Timeframes:"
THEME_HEADING = "Visual Theme:"
ACCENT_HEADING = "Accent Color:"
SOUND_EVENTS_HEADING = "Sound Events:"
VOLUME_HEADING = "SFX Volume:"
SMS_GATEWAY_HEADING = "Email Gateway Settings"
SMS_GATEWAY_HEADING_STYLE = "color: #00cccc; font-weight: bold; margin-top: 6px;"

AI_INFO_TEXT = (
    "The connect phrase is embedded in the system prompt sent to Claude.\n"
    "The confirm phrase is what Claude must respond with to prove identity.\n"
    "Change both phrases together. Keep them secret."
)
AI_INFO_STYLE = "color: #888; font-size: 10px;"
AI_INFO_WORD_WRAP = True

#: Read off DEFAULT_WEIGHTS so the page cannot hold a second set of figures.
TA_INDICATOR_WEIGHTS = tuple(DEFAULT_WEIGHTS.items())
TA_LABEL_FORMAT = "{name}:"
TA_VALUE_FORMAT = "{weight:.2f}"
TA_SLIDER_RANGE = (0, 200)
TA_SLIDER_SCALE = 100
TA_LABEL_MIN_WIDTH = 140
TA_VALUE_MIN_WIDTH = 40
TA_SLIDER_NAME_FORMAT = "ta_weight_{name}"


def ta_label(name: str) -> str:
    """The printed name of one indicator weight row."""
    return TA_LABEL_FORMAT.format(name=name.replace("_", " ").title())


def ta_slider_name(name: str) -> str:
    """The control name the indicator ``name`` weight slider answers to."""
    return TA_SLIDER_NAME_FORMAT.format(name=name)


def ta_slider_value(weight: float) -> int:
    """One indicator weight as its slider position."""
    return int(round(weight * TA_SLIDER_SCALE))


def ta_value_text(weight: float) -> str:
    """One indicator weight as the figure printed beside its slider."""
    return TA_VALUE_FORMAT.format(weight=weight)


PHANTOM_TIMEFRAMES = ALL_TIMEFRAMES
PHANTOM_TIMEFRAME_ITEMS = tuple((one, one) for one in PHANTOM_TIMEFRAMES)
#: The store declares the opening choice, so the page and the schema agree.
PHANTOM_TIMEFRAME_DEFAULT = AppSettings().default_phantom_timeframe

#: The lock spin box's opening figure and its fallback, declared once.
LOCK_CANDLE_DEFAULT = AppSettings().default_lock_candle_count

THEME_ITEMS = (
    ("Cyberpunk Dark", "cyberpunk_dark"),
    ("Neon Light", "neon_light"),
    ("Classic Terminal", "classic_terminal"),
    ("Minimal Modern", "minimal_modern"),
    ("Glass & Metal", "glass_metal"),
)

#: Read off CARRIER_GATEWAYS so the picker cannot offer a name the engine has
#: no gateway template for.
CARRIER_NAMES = tuple(CARRIER_GATEWAYS)

#: The engine's own opening figures, so the page declares no second set.
SMS_BUILT = SMSConfig()

#: The printed label beside the value the send path tests, so the picker stores
#: a provider the engine routes on.
SMS_PROVIDERS = (
    ("Email-to-SMS Gateway", EMAIL_GATEWAY),
    ("Twilio API", TWILIO),
)
SMS_FORM_SPACING_PX = 6
SMS_FORM_MARGINS = (8, 16, 8, 8)
SMS_CONTENT_SPACING_PX = 8
AI_CONTENT_SPACING_PX = 12
SMS_CONTROL_MIN_HEIGHT = 28
AI_TEST_BUTTON_MIN_HEIGHT = 32

AI_STATUS_LABEL = "Not connected"
AI_STATUS_STYLE = "color: #888; font-weight: bold;"
AI_HASH_LABEL = "—"
AI_HASH_STYLE = "color: #666; font-family: Consolas;"
AI_CHECKS_LABEL = "0"
AI_TEST_BUTTON_TEXT = "Test Handshake"
AI_TEST_BUTTON_STYLE = (
    "background: #1a3a4a; color: #00ddff; border: 1px solid #00aacc; "
    "border-radius: 4px; font-weight: bold;"
)
AI_MISSING_CREDENTIAL_TEXT = "No API key entered"
AI_MISSING_PHRASE_TEXT = "Phrases required"
AI_SAVED_TEXT = "Settings saved — handshake runs on next bot cycle"
AI_ERROR_STYLE = "color: #ff3366; font-weight: bold;"
AI_OK_STYLE = "color: #00ddff; font-weight: bold;"

FEEDBACK_COLORS = {
    "info": "#00aaff",
    "success": "#00ff88",
    "warning": "#ffaa00",
    "error": "#ff3366",
}
FEEDBACK_FALLBACK_COLOR = "#e0e0f0"
FEEDBACK_STYLE_FORMAT = "color: {color};"
INFO_LEVEL = "info"
SUCCESS_LEVEL = "success"
WARNING_LEVEL = "warning"
ERROR_LEVEL = "error"

MISSING_CREDENTIALS_FEEDBACK = "Enter API key and secret first."
TESTING_FEEDBACK_FORMAT = "Testing connection to {name}..."
BALANCES_FEEDBACK_FORMAT = "\nBalances: {details}"
BALANCES_LOG_FORMAT = "Balances: {details}"
DETAILS_FEEDBACK_FORMAT = "\n{details}"
API_FAILED_LOG_FORMAT = "API failed ({eid}): {message}"
TEST_FAILED_FEEDBACK_FORMAT = "Test failed: {error}"

ADDED_WITH_CREDENTIALS = "with stored credentials"
ADDED_WITHOUT_CREDENTIALS = "without credentials"
ADDED_FEEDBACK_FORMAT = "{name} added {how}."
ADDED_LOG_FORMAT = "Exchange added: {name} ({how})"
ADDED_BOX_TITLE = "Exchange Added"
ADDED_BOX_FORMAT = (
    "{name} has been added {how}.\n" "The exchange tab will appear in the main window."
)
EXCHANGE_ITEM_FORMAT = "{name} ({eid})"
CONFIGURED_ITEM_FORMAT = "{name} ({eid})"
KEY_FIELD = "api_key_enc"
SIGNING_FIELD = "api_secret_enc"
PHRASE_FIELD = "passphrase_enc"
EXCHANGE_CONFIG_FIELDS = (
    "exchange_id",
    "display_name",
    KEY_FIELD,
    SIGNING_FIELD,
    PHRASE_FIELD,
    "enabled",
    "hardware_mode",
    "hw_volume_serial",
)
TYPED_CREDENTIAL_CONTROLS = ("new_api_key", "new_api_secret", "new_passphrase")
EMPTY_TEXT = ""
EXCHANGE_CONFIG_DEFAULTS = (
    EMPTY_TEXT,
    EMPTY_TEXT,
    EMPTY_TEXT,
    EMPTY_TEXT,
    EMPTY_TEXT,
    True,
    False,
    EMPTY_TEXT,
)

NO_SELECTION_FEEDBACK = "Select an exchange to remove."
REMOVED_FEEDBACK_FORMAT = "{name} removed."
REMOVED_LOG_FORMAT = "Exchange removed: {eid}"

PROCESS_EVENTS_REASON = "legacy processEvents site"

VOLUME_LABEL_FORMAT = "{value}%"
VOLUME_SCALE = 100.0
VOLUME_RANGE = (0, 100)
SOUND_NAMES = ("buy", "sell", "fire", "track", "profit", "drip")
SOUND_TEST_BUTTONS = (
    ("Test Buy", "buy", None),
    ("Test Sell", "sell", None),
    ("Test Fire", "fire", "Play the sniper rifle SFX."),
    ("Test Track", "track", "Play one tracking beep."),
    ("Test Profit", "profit", "Play the coins-in-bucket SFX."),
    ("Test Drip", "drip", "Play the water-drip SFX."),
)
SOUND_CONFIG_FIELDS = (
    ("enabled", "sound_enabled"),
    ("buy_sound", "sound_buy"),
    ("sell_sound", "sound_sell"),
    ("error_sound", "sound_error"),
    ("bot_state_sound", "sound_state"),
    ("fire_sound", "sound_fire"),
    ("track_sound", "sound_track"),
    ("profit_sound", "sound_profit"),
    ("drip_sound", "sound_drip"),
)
SOUND_GROUP_KEY = "sound"
VOLUME_FIELD = "volume"
VOLUME_NAME = "sound_volume"

#: One entry per SMSConfig field the SMS page sets: the field, and the control
#: carrying it. The save and the load both walk this list.
SMS_CONFIG_FIELDS = (
    ("enabled", "sms_enabled"),
    ("provider", "sms_provider"),
    ("phone_number", "sms_phone"),
    ("twilio_sid", "sms_twilio_sid"),
    ("twilio_auth_token", "sms_twilio_token"),
    ("twilio_from_number", "sms_twilio_from"),
    ("carrier", "sms_carrier"),
    ("gateway_email", "sms_gateway"),
    ("smtp_server", "sms_smtp_server"),
    ("smtp_port", "sms_smtp_port"),
    ("smtp_username", "sms_smtp_user"),
    ("smtp_password", "sms_smtp_pass"),
    ("notify_buy_fills", "sms_buy"),
    ("notify_sell_fills", "sms_sell"),
    ("notify_bot_state_changes", "sms_state"),
    ("notify_errors", "sms_errors"),
    ("notify_pl_threshold", "sms_pl"),
    ("pl_threshold_amount", "sms_pl_amount"),
    ("notify_balance_warning", "sms_balance"),
    ("notify_connection_status", "sms_connection"),
    ("max_messages_per_hour", "sms_max_hour"),
    ("cooldown_seconds", "sms_cooldown"),
)
#: The store key both builds persist the SMS page into, read off the engine so
#: the page cannot name a group the engine does not read.
MESSAGE_CHANNELS_GROUP_KEY = SETTINGS_GROUP

TA_WEIGHT_GROUP_KEY = "ta_indicator_weights"

SAVE_CALLED_PRINT = "[SETTINGS] _save called"
NO_MANAGER_PRINT = "[SETTINGS] No settings manager, closing"
SAVE_ERROR_PRINT_FORMAT = "[SETTINGS ERROR] {key}: {error}"
SAVE_DONE_PRINT_FORMAT = "[SETTINGS] Saved {saved} groups, closing dialog"
FAILED_ENTRY_FORMAT = "{key} ({error})"
PARTIAL_LOG_FORMAT = "Settings PARTIALLY saved: {saved} ok, {count} FAILED — {names}"
FAILED_JOIN = "; "
CLEAN_LOG_FORMAT = "Settings saved ({saved} groups)."
PARTIAL_BOX_TITLE = "Settings partially saved"
PARTIAL_BOX_FORMAT = (
    "{saved} setting group(s) saved, but "
    "{count} FAILED and were discarded:\n\n{names}"
    "\n\nThese values are NOT persisted and will "
    "revert when the dialog is reopened."
)
PARTIAL_BOX_ENTRY_FORMAT = "  • {entry}"
PARTIAL_BOX_JOIN = "\n"
WARNING_ICON = "warning"
INFORMATION_ICON = "information"

AI_LOAD_KEYS = (
    ("api_key", "", "ai_api_key"),
    ("interval_hours", 4.0, "ai_interval"),
    ("connect_phrase", "", "ai_connect_phrase"),
    ("confirm_phrase", "", "ai_confirm_phrase"),
    ("enabled", False, "ai_enabled"),
    ("auto_handshake", True, "ai_auto_handshake"),
    ("log_feedback", True, "ai_log_feedback"),
)
AI_GROUP_KEY = "ai_monitor"
THEME_KEY = "theme"
THEME_DEFAULT = "cyberpunk_dark"
#: Empty leaves the theme's own accent painting, so the box opens on its
#: placeholder.
ACCENT_DEFAULT = ""
EXCHANGE_ID_KEY = "exchange_id"
DISPLAY_NAME_KEY = "display_name"
NO_MATCH_INDEX = -1
FIRST_INDEX = 0


#: One entry per setting the store holds at its top level: the store key, the
#: control carrying it, and what stands in for a store without the key. ``save``
#: and ``_load_current`` read this one list, so no setting can be written
#: without also being loaded.
PERSISTED_ROWS = (
    ("username", "username", EMPTY_TEXT),
    ("default_target_balance", "default_balance", 200.0),
    ("bot_visibility", "visibility", "orderbook"),
    ("aggressive_trading", "aggressive", False),
    ("default_enable_phantoms", "phantoms_enabled", True),
    ("default_phantom_timeframe", "phantom_timeframe", PHANTOM_TIMEFRAME_DEFAULT),
    ("default_lock_candle_count", "lock_candles", LOCK_CANDLE_DEFAULT),
    (THEME_KEY, "theme_combo", THEME_DEFAULT),
    ("accent_color", "accent_color", ACCENT_DEFAULT),
)
SAVE_PAIRS = tuple((key, name) for key, name, _fallback in PERSISTED_ROWS)
SETTING_LOAD_KEYS = tuple(
    (key, fallback, name) for key, name, fallback in PERSISTED_ROWS
)

LINE = "line"
TEXT_AREA = "text_area"
COMBO_TEXT = "combo_text"
COMBO_DATA = "combo_data"
CHECK = "check"
SPIN = "spin"
DOUBLE_SPIN = "double_spin"
SLIDER = "slider"
LIST = "list"

SIGNAL_FOR_KIND = {
    LINE: "textChanged",
    COMBO_TEXT: "currentIndexChanged",
    COMBO_DATA: "currentIndexChanged",
    CHECK: "toggled",
    SPIN: "valueChanged",
    DOUBLE_SPIN: "valueChanged",
    SLIDER: "valueChanged",
}

BUS_SUBSCRIBES: tuple = ()
BUS_EMITS: tuple = ()
QT_SIGNALS = ("settings_changed",)
TIMERS_BUILT: tuple = ()
TIMERS_STARTED: tuple = ()
THREADS_BUILT: tuple = ()
THREADS_STARTED: tuple = ()

CONTROL_SPECS: tuple[dict, ...] = (
    {
        "tab": USER_TAB,
        "group": None,
        "label": "Username:",
        "name": "username",
        "kind": LINE,
    },
    {
        "tab": EXCHANGE_TAB,
        "group": None,
        "label": None,
        "name": "exchange_list",
        "kind": LIST,
    },
    {
        "tab": EXCHANGE_TAB,
        "group": CRYPTO_ADD_GROUP,
        "label": "Exchange:",
        "name": "new_exchange",
        "kind": COMBO_DATA,
    },
    {
        "tab": EXCHANGE_TAB,
        "group": CRYPTO_ADD_GROUP,
        "label": "API Key:",
        "name": "new_api_key",
        "kind": LINE,
        "echo": "password",
        "placeholder": "API Key or organizations/.../.../apiKeys/...",
        "tooltip": (
            "For Coinbase CDP keys, paste the full "
            "organizations/.../apiKeys/... string"
        ),
    },
    {
        "tab": EXCHANGE_TAB,
        "group": CRYPTO_ADD_GROUP,
        "label": "API Secret:",
        "name": "new_api_secret",
        "kind": TEXT_AREA,
        "echo": "password",
        "max_height": 60,
        "placeholder": "API Secret or EC Private Key (PEM format with \\n is OK)",
        "tooltip": (
            "For Coinbase CDP keys, paste the full PEM key including\n"
            "-----BEGIN EC PRIVATE KEY----- and -----END EC PRIVATE KEY-----\n"
            "Literal \\n characters will be auto-converted to newlines."
        ),
    },
    {
        "tab": EXCHANGE_TAB,
        "group": CRYPTO_ADD_GROUP,
        "label": None,
        "name": "pp_check",
        "kind": CHECK,
        "text": "This exchange uses an API passphrase",
        "checked": False,
    },
    {
        "tab": EXCHANGE_TAB,
        "group": CRYPTO_ADD_GROUP,
        "label": "",
        "name": "new_passphrase",
        "kind": LINE,
        "echo": "password",
        "visible": False,
        "placeholder": "Passphrase set when creating API key",
    },
    {
        "tab": TRADING_TAB,
        "group": None,
        "label": "Default Target Balance:",
        "name": "default_balance",
        "kind": DOUBLE_SPIN,
        "range": (1.0, 1000000.0),
        "prefix": "$",
        "decimals": 2,
    },
    {
        "tab": TRADING_TAB,
        "group": None,
        "label": "Bot Visibility:",
        "name": "visibility",
        "kind": COMBO_TEXT,
        "items": ("orderbook", "internal"),
    },
    {
        "tab": TRADING_TAB,
        "group": None,
        "label": None,
        "name": "aggressive",
        "kind": CHECK,
        "text": "Enable aggressive trading mode",
        "checked": False,
    },
    {
        "tab": PHANTOM_TAB,
        "group": None,
        "label": None,
        "name": "phantoms_enabled",
        "kind": CHECK,
        "text": "Enable Phantom Bots for Scrumming",
        "checked": True,
    },
    {
        "tab": PHANTOM_TAB,
        "group": None,
        "label": None,
        "name": "phantom_timeframe",
        "kind": COMBO_DATA,
        "items": PHANTOM_TIMEFRAME_ITEMS,
        "current_data": PHANTOM_TIMEFRAME_DEFAULT,
        "tooltip": "The one phantom timeframe a new bot starts with",
    },
    {
        "tab": PHANTOM_TAB,
        "group": LOCK_GROUP_TITLE,
        "label": "Lock duration (candles):",
        "name": "lock_candles",
        "kind": SPIN,
        "range": (1, 10),
        "value": LOCK_CANDLE_DEFAULT,
    },
    {
        "tab": THEME_TAB,
        "group": None,
        "label": None,
        "name": "theme_combo",
        "kind": COMBO_DATA,
        "items": THEME_ITEMS,
    },
    {
        "tab": THEME_TAB,
        "group": None,
        "label": None,
        "name": "accent_color",
        "kind": LINE,
        "placeholder": "#00ffcc",
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_enabled",
        "kind": CHECK,
        "text": "Enable sound notifications",
        "checked": True,
        "tooltip": "Master switch for all audio notifications",
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_buy",
        "kind": CHECK,
        "text": "Buy order fills (blurb + squirt tone)",
        "checked": True,
        "tooltip": "Plays a low bubbly rising tone when a buy order is filled",
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_sell",
        "kind": CHECK,
        "text": "Sell order fills (bell + jingle tone)",
        "checked": True,
        "tooltip": "Plays a high bright bell tone when a sell order is filled",
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_error",
        "kind": CHECK,
        "text": "Errors (alert tone)",
        "checked": True,
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_state",
        "kind": CHECK,
        "text": "Bot state changes (subtle click)",
        "checked": True,
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_fire",
        "kind": CHECK,
        "text": "Scrum/Fold Fire (sniper rifle shot)",
        "checked": True,
        "tooltip": (
            "Synthesized rifle shot plays when a scrum or fold\n"
            "actually executes. Also plays on Manual Fire."
        ),
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_track",
        "kind": CHECK,
        "text": "Tracking beeps (speeds up as bot closes on fire)",
        "checked": True,
        "tooltip": (
            "Short beep paced by scrum phase:\n"
            "  SEARCH = silent\n"
            "  TRACK  = slow beep (800ms)\n"
            "  FIRE   = fast beep (200ms)"
        ),
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_profit",
        "kind": CHECK,
        "text": "P/L increase (coins dropping into bucket)",
        "checked": True,
        "tooltip": (
            "Synthesized 3-coin bucket drop plays on any trade\n"
            "event with realized profit > 0. Fires on grid and\n"
            "scrumming bots alike."
        ),
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_drip",
        "kind": CHECK,
        "text": "Accumulation (water drip)",
        "checked": True,
        "tooltip": (
            "Water drip plays on FOLD events — the canonical\n"
            "Acervator accumulation moment (buying back more asset\n"
            "than was sold). Does not fire on SCRUM or DIST."
        ),
    },
    {
        "tab": SOUND_TAB,
        "group": None,
        "label": None,
        "name": "sound_volume",
        "kind": SLIDER,
        "range": VOLUME_RANGE,
        "value": 70,
    },
    {
        "tab": SMS_TAB,
        "group": None,
        "label": None,
        "name": "sms_enabled",
        "kind": CHECK,
        "text": "Enable SMS notifications",
        "checked": SMS_BUILT.enabled,
        "tooltip": "Send text messages to your phone for trading events",
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "Provider:",
        "name": "sms_provider",
        "kind": COMBO_DATA,
        "items": SMS_PROVIDERS,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "Phone Number:",
        "name": "sms_phone",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "placeholder": "+15551234567",
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "Twilio Account SID:",
        "name": "sms_twilio_sid",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "placeholder": "AC...",
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "Twilio Auth Token:",
        "name": "sms_twilio_token",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "echo": "password",
        "placeholder": "Auth token from the Twilio console",
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "Twilio From Number:",
        "name": "sms_twilio_from",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "placeholder": "+15559876543",
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "Carrier:",
        "name": "sms_carrier",
        "kind": COMBO_TEXT,
        "items": CARRIER_NAMES,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "Gateway Email:",
        "name": "sms_gateway",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "placeholder": "5551234567@vtext.com",
        "tooltip": "Full email address for carrier SMS gateway",
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "SMTP Username:",
        "name": "sms_smtp_user",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "placeholder": "your.email@gmail.com",
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "SMTP Password:",
        "name": "sms_smtp_pass",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "echo": "password",
        "placeholder": "App password (not regular password)",
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "Mail Server:",
        "name": "sms_smtp_server",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "placeholder": SMS_BUILT.smtp_server,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_PROVIDER_GROUP_TITLE,
        "label": "Mail Port:",
        "name": "sms_smtp_port",
        "kind": SPIN,
        "range": FIELD_BOUNDS["smtp_port"],
        "value": SMS_BUILT.smtp_port,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_EVENTS_GROUP_TITLE,
        "label": None,
        "name": "sms_buy",
        "kind": CHECK,
        "text": "Buy fills",
        "checked": SMS_BUILT.notify_buy_fills,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_EVENTS_GROUP_TITLE,
        "label": None,
        "name": "sms_sell",
        "kind": CHECK,
        "text": "Sell fills",
        "checked": SMS_BUILT.notify_sell_fills,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_EVENTS_GROUP_TITLE,
        "label": None,
        "name": "sms_state",
        "kind": CHECK,
        "text": "Bot state changes (start/stop/error)",
        "checked": SMS_BUILT.notify_bot_state_changes,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_EVENTS_GROUP_TITLE,
        "label": None,
        "name": "sms_errors",
        "kind": CHECK,
        "text": "API errors and failures",
        "checked": SMS_BUILT.notify_errors,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_EVENTS_GROUP_TITLE,
        "label": None,
        "name": "sms_pl",
        "kind": CHECK,
        "text": "P/L threshold alerts",
        "checked": SMS_BUILT.notify_pl_threshold,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_EVENTS_GROUP_TITLE,
        "label": "P/L threshold:",
        "name": "sms_pl_amount",
        "kind": DOUBLE_SPIN,
        "range": FIELD_BOUNDS["pl_threshold_amount"],
        "value": SMS_BUILT.pl_threshold_amount,
        "prefix": "$",
        "min_height": SMS_CONTROL_MIN_HEIGHT,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_EVENTS_GROUP_TITLE,
        "label": None,
        "name": "sms_balance",
        "kind": CHECK,
        "text": "Low balance warnings",
        "checked": SMS_BUILT.notify_balance_warning,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_EVENTS_GROUP_TITLE,
        "label": None,
        "name": "sms_connection",
        "kind": CHECK,
        "text": "Exchange connection status",
        "checked": SMS_BUILT.notify_connection_status,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_RATE_GROUP_TITLE,
        "label": "Max messages per hour:",
        "name": "sms_max_hour",
        "kind": SPIN,
        "range": FIELD_BOUNDS["max_messages_per_hour"],
        "value": SMS_BUILT.max_messages_per_hour,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
    },
    {
        "tab": SMS_TAB,
        "group": SMS_RATE_GROUP_TITLE,
        "label": "Min time between messages:",
        "name": "sms_cooldown",
        "kind": SPIN,
        "range": FIELD_BOUNDS["cooldown_seconds"],
        "value": SMS_BUILT.cooldown_seconds,
        "suffix": " sec",
        "min_height": SMS_CONTROL_MIN_HEIGHT,
    },
    {
        "tab": AI_TAB,
        "group": AI_API_GROUP_TITLE,
        "label": "Anthropic API Key:",
        "name": "ai_api_key",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "echo": "password",
        "placeholder": "sk-ant-api03-...",
    },
    {
        "tab": AI_TAB,
        "group": AI_API_GROUP_TITLE,
        "label": "Check interval:",
        "name": "ai_interval",
        "kind": DOUBLE_SPIN,
        "range": (0.5, 24.0),
        "value": 4.0,
        "suffix": " hours",
        "decimals": 1,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
    },
    {
        "tab": AI_TAB,
        "group": AI_HANDSHAKE_GROUP_TITLE,
        "label": "Connect phrase:",
        "name": "ai_connect_phrase",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "placeholder": "acervator-heapbuilder-live",
    },
    {
        "tab": AI_TAB,
        "group": AI_HANDSHAKE_GROUP_TITLE,
        "label": "Confirm phrase:",
        "name": "ai_confirm_phrase",
        "kind": LINE,
        "min_height": SMS_CONTROL_MIN_HEIGHT,
        "placeholder": "the-heap-grows-by-accumulation",
    },
    {
        "tab": AI_TAB,
        "group": AI_BEHAVIOUR_GROUP_TITLE,
        "label": None,
        "name": "ai_enabled",
        "kind": CHECK,
        "text": "Enable AI Monitor feedback loop",
        "checked": False,
    },
    {
        "tab": AI_TAB,
        "group": AI_BEHAVIOUR_GROUP_TITLE,
        "label": None,
        "name": "ai_auto_handshake",
        "kind": CHECK,
        "text": "Auto-handshake on first analysis",
        "checked": True,
    },
    {
        "tab": AI_TAB,
        "group": AI_BEHAVIOUR_GROUP_TITLE,
        "label": None,
        "name": "ai_log_feedback",
        "kind": CHECK,
        "text": "Log AI feedback to trade journal",
        "checked": True,
    },
    # One per indicator weight. label None keeps them out of `rows`; the TA_ROWS
    # layout item draws them.
    *(
        {
            "tab": TA_TAB,
            "group": None,
            "label": None,
            "name": ta_slider_name(name),
            "kind": SLIDER,
            "range": TA_SLIDER_RANGE,
            "value": ta_slider_value(weight),
        }
        for name, weight in TA_INDICATOR_WEIGHTS
    ),
)

GROUPS = (
    (EXCHANGE_TAB, CRYPTO_ADD_GROUP),
    (PHANTOM_TAB, LOCK_GROUP_TITLE),
    (SMS_TAB, SMS_PROVIDER_GROUP_TITLE),
    (SMS_TAB, SMS_EVENTS_GROUP_TITLE),
    (SMS_TAB, SMS_RATE_GROUP_TITLE),
    (AI_TAB, AI_API_GROUP_TITLE),
    (AI_TAB, AI_HANDSHAKE_GROUP_TITLE),
    (AI_TAB, AI_BEHAVIOUR_GROUP_TITLE),
    (AI_TAB, AI_STATUS_GROUP_TITLE),
)

NO_STYLE = ""

TEXT_ROWS = (
    (
        AI_TAB,
        AI_STATUS_GROUP_TITLE,
        "Status:",
        "ai_status",
        AI_STATUS_LABEL,
        AI_STATUS_STYLE,
    ),
    (
        AI_TAB,
        AI_STATUS_GROUP_TITLE,
        "Journal hash:",
        "ai_hash",
        AI_HASH_LABEL,
        AI_HASH_STYLE,
    ),
    (
        AI_TAB,
        AI_STATUS_GROUP_TITLE,
        "Checks completed:",
        "ai_checks",
        AI_CHECKS_LABEL,
        NO_STYLE,
    ),
)

STATUS_ROWS = tuple(
    (label, name, text, style)
    for tab, _group, label, name, text, style in TEXT_ROWS
    if tab == AI_TAB
)

EXCHANGE_CONNECTIONS = (
    ("new_exchange.currentIndexChanged", "on_exchange_changed"),
    ("pp_check.toggled", "show_passphrase"),
    ("test_btn.clicked", "test_api_connection"),
    ("add_btn.clicked", "add_exchange"),
    ("remove_btn.clicked", "remove_exchange"),
)
SOUND_BOX_HANDLER = "push_sound_config"
SOUND_BOX_SIGNAL_FORMAT = "{name}.toggled"
SOUND_CONNECTIONS = (
    ("sound_volume.valueChanged", "update_volume_label"),
    ("sound_volume.valueChanged.2", "sfx_volume_changed"),
) + tuple(
    (SOUND_BOX_SIGNAL_FORMAT.format(name=name), SOUND_BOX_HANDLER)
    for _field, name in SOUND_CONFIG_FIELDS
)
SMS_CARRIER_CONNECTIONS = (("sms_carrier.currentIndexChanged", "fill_gateway_email"),)
AI_CONNECTIONS = (("ai_test_btn.clicked", "test_ai_handshake"),)
FOOTER_CONNECTIONS = (
    ("cancel_btn.clicked", "reject"),
    ("save_btn.clicked", "save"),
)
TA_SLIDER_HANDLER = "update_weight_label"
SOUND_BUTTON_HANDLER = "test_sound"
TA_SLIDER_SIGNAL_FORMAT = "{name}.valueChanged"
SOUND_BUTTON_SIGNAL_FORMAT = "sound_test[{name}].clicked"


def connect_order() -> tuple:
    """Every signal connected, with its handler, in the order wired."""
    found = list(EXCHANGE_CONNECTIONS)
    for name, _weight in TA_INDICATOR_WEIGHTS:
        found.append(
            (
                TA_SLIDER_SIGNAL_FORMAT.format(name=ta_slider_name(name)),
                TA_SLIDER_HANDLER,
            )
        )
    found.extend(SOUND_CONNECTIONS)
    for _text, name, _tip in SOUND_TEST_BUTTONS:
        found.append(
            (SOUND_BUTTON_SIGNAL_FORMAT.format(name=name), SOUND_BUTTON_HANDLER)
        )
    found.extend(SMS_CARRIER_CONNECTIONS)
    found.extend(AI_CONNECTIONS)
    found.extend(FOOTER_CONNECTIONS)
    return tuple(found)


ACTION_HANDLERS = dict(
    EXCHANGE_CONNECTIONS
    + SOUND_CONNECTIONS
    + SMS_CARRIER_CONNECTIONS
    + AI_CONNECTIONS
    + FOOTER_CONNECTIONS
)


HORIZONTAL_BAR_OFF_TABS = (SMS_TAB,)
CONTENT_SPACING = {
    SMS_TAB: SMS_CONTENT_SPACING_PX,
    AI_TAB: AI_CONTENT_SPACING_PX,
}
AI_STATUS_FORM_SPACING_PX = 4
GROUP_FORM_SPACING = {
    SMS_PROVIDER_GROUP_TITLE: SMS_FORM_SPACING_PX,
    SMS_EVENTS_GROUP_TITLE: SMS_FORM_SPACING_PX,
    SMS_RATE_GROUP_TITLE: SMS_FORM_SPACING_PX,
    AI_API_GROUP_TITLE: SMS_FORM_SPACING_PX,
    AI_HANDSHAKE_GROUP_TITLE: SMS_FORM_SPACING_PX,
    AI_BEHAVIOUR_GROUP_TITLE: SMS_FORM_SPACING_PX,
    AI_STATUS_GROUP_TITLE: AI_STATUS_FORM_SPACING_PX,
}
GROUP_FORM_MARGINS = {title: SMS_FORM_MARGINS for title in GROUP_FORM_SPACING}

COLUMN = "column"
FORM = "form"
ROW = "row"
SCROLL = "scroll"
GROUP = "group"

CONTROL = "control"
LABEL = "label"
TEXT = "text"
BUTTON = "button"
STRETCH = "stretch"
BANNER = "banner"
TA_ROWS = "ta_rows"
SOUND_ROW = "sound_row"
ADD_GROUP_BY_WING = "add_group"

TEST_BUTTON_TEXT = "Test Connection"
ADD_BUTTON_TEXT = "Test and Add Exchange"

BUTTON_NAMES_BY_TEXT = {
    TEST_BUTTON_TEXT: "test_btn",
    ADD_BUTTON_TEXT: "add_btn",
    REMOVE_BUTTON_TEXT: "remove_btn",
    AI_TEST_BUTTON_TEXT: "ai_test_btn",
    CANCEL_BUTTON_TEXT: "cancel_btn",
    SAVE_BUTTON_TEXT: "save_btn",
}

LAYOUT = {
    USER_TAB: (FORM, ((CONTROL, "username"),)),
    EXCHANGE_TAB: (
        COLUMN,
        (
            (BANNER,),
            (TEXT, "list_label"),
            (CONTROL, "exchange_list"),
            (
                GROUP,
                ADD_GROUP_BY_WING,
                (
                    FORM,
                    (
                        (CONTROL, "new_exchange"),
                        (CONTROL, "new_api_key"),
                        (CONTROL, "new_api_secret"),
                        (CONTROL, "pp_check"),
                        (CONTROL, "new_passphrase"),
                        (
                            ROW,
                            (
                                (BUTTON, TEST_BUTTON_TEXT),
                                (BUTTON, ADD_BUTTON_TEXT),
                            ),
                        ),
                        (TEXT, "api_feedback"),
                    ),
                ),
            ),
            (BUTTON, REMOVE_BUTTON_TEXT),
        ),
    ),
    TRADING_TAB: (
        FORM,
        (
            (CONTROL, "default_balance"),
            (CONTROL, "visibility"),
            (CONTROL, "aggressive"),
        ),
    ),
    TA_TAB: (COLUMN, ((LABEL, TA_HEADING), (TA_ROWS,), (STRETCH,))),
    PHANTOM_TAB: (
        COLUMN,
        (
            (CONTROL, "phantoms_enabled"),
            (LABEL, PHANTOM_HEADING),
            (CONTROL, "phantom_timeframe"),
            (GROUP, LOCK_GROUP_TITLE, (FORM, ((CONTROL, "lock_candles"),))),
            (STRETCH,),
        ),
    ),
    THEME_TAB: (
        COLUMN,
        (
            (LABEL, THEME_HEADING),
            (CONTROL, "theme_combo"),
            (LABEL, ACCENT_HEADING),
            (CONTROL, "accent_color"),
            (STRETCH,),
        ),
    ),
    SOUND_TAB: (
        COLUMN,
        (
            (CONTROL, "sound_enabled"),
            (LABEL, SOUND_EVENTS_HEADING),
            (CONTROL, "sound_buy"),
            (CONTROL, "sound_sell"),
            (CONTROL, "sound_error"),
            (CONTROL, "sound_state"),
            (CONTROL, "sound_fire"),
            (CONTROL, "sound_track"),
            (CONTROL, "sound_profit"),
            (CONTROL, "sound_drip"),
            (
                ROW,
                (
                    (LABEL, VOLUME_HEADING),
                    (CONTROL, "sound_volume"),
                    (TEXT, "vol_label"),
                ),
            ),
            (SOUND_ROW,),
            (STRETCH,),
        ),
    ),
    SMS_TAB: (
        SCROLL,
        (
            COLUMN,
            (
                (CONTROL, "sms_enabled"),
                (
                    GROUP,
                    SMS_PROVIDER_GROUP_TITLE,
                    (
                        FORM,
                        (
                            (CONTROL, "sms_provider"),
                            (CONTROL, "sms_phone"),
                            (CONTROL, "sms_twilio_sid"),
                            (CONTROL, "sms_twilio_token"),
                            (CONTROL, "sms_twilio_from"),
                            (LABEL, SMS_GATEWAY_HEADING),
                            (CONTROL, "sms_carrier"),
                            (CONTROL, "sms_gateway"),
                            (CONTROL, "sms_smtp_user"),
                            (CONTROL, "sms_smtp_pass"),
                            (CONTROL, "sms_smtp_server"),
                            (CONTROL, "sms_smtp_port"),
                        ),
                    ),
                ),
                (
                    GROUP,
                    SMS_EVENTS_GROUP_TITLE,
                    (
                        FORM,
                        (
                            (CONTROL, "sms_buy"),
                            (CONTROL, "sms_sell"),
                            (CONTROL, "sms_state"),
                            (CONTROL, "sms_errors"),
                            (CONTROL, "sms_pl"),
                            (CONTROL, "sms_pl_amount"),
                            (CONTROL, "sms_balance"),
                            (CONTROL, "sms_connection"),
                        ),
                    ),
                ),
                (
                    GROUP,
                    SMS_RATE_GROUP_TITLE,
                    (FORM, ((CONTROL, "sms_max_hour"), (CONTROL, "sms_cooldown"))),
                ),
                (STRETCH,),
            ),
        ),
    ),
    AI_TAB: (
        SCROLL,
        (
            COLUMN,
            (
                (
                    GROUP,
                    AI_API_GROUP_TITLE,
                    (FORM, ((CONTROL, "ai_api_key"), (CONTROL, "ai_interval"))),
                ),
                (
                    GROUP,
                    AI_HANDSHAKE_GROUP_TITLE,
                    (
                        FORM,
                        (
                            (LABEL, AI_INFO_TEXT),
                            (CONTROL, "ai_connect_phrase"),
                            (CONTROL, "ai_confirm_phrase"),
                        ),
                    ),
                ),
                (
                    GROUP,
                    AI_BEHAVIOUR_GROUP_TITLE,
                    (
                        FORM,
                        (
                            (CONTROL, "ai_enabled"),
                            (CONTROL, "ai_auto_handshake"),
                            (CONTROL, "ai_log_feedback"),
                        ),
                    ),
                ),
                (
                    GROUP,
                    AI_STATUS_GROUP_TITLE,
                    (
                        FORM,
                        (
                            (TEXT, "ai_status"),
                            (TEXT, "ai_hash"),
                            (TEXT, "ai_checks"),
                            (BUTTON, AI_TEST_BUTTON_TEXT),
                        ),
                    ),
                ),
                (STRETCH,),
            ),
        ),
    ),
}

PAINTED_KIND = {
    LINE: "line",
    TEXT_AREA: "text_area",
    COMBO_TEXT: "combo",
    COMBO_DATA: "combo",
    CHECK: "check",
    SPIN: "spin",
    DOUBLE_SPIN: "double_spin",
    SLIDER: "slider",
    LIST: "list",
}
SILENT_KINDS = ("spin", "double_spin", "slider", "list")

TEXT_ROW_LABELS = {
    name: label for _tab, _group, label, name, _text, _style in TEXT_ROWS
}


def title_for(wing: Any) -> str:
    """The window title for one wing, plain where the wing is unknown."""
    if wing in KNOWN_WINGS:
        return WINDOW_TITLE_FORMAT.format(wing=wing.capitalize())
    return PLAIN_WINDOW_TITLE


# OVERTAKEN, quoted whole:
#   "`wing` when the dialog knows it, the crypto wing otherwise."
# True today: `wing` when the dialog knows it, the wing `CLASS_WINGS` names for
# an asset class, and the crypto wing otherwise.
def wing_or_default(wing: Any) -> str:
    """`wing` when the dialog knows it, the crypto wing otherwise."""
    if wing in KNOWN_WINGS:
        return str(wing)
    return CLASS_WINGS.get(str(wing or "").strip().lower(), DEFAULT_WING)


def crypto_exchange_items() -> tuple:
    """Every ``SUPPORTED_EXCHANGES`` id with its ``exchange_label``, in id order.

    ``SUPPORTED_EXCHANGES`` is imported when first asked, so importing this
    file loads no exchange library and reads no settings.
    """
    from ...exchange.ccxt_connector import SUPPORTED_EXCHANGES, exchange_label

    return tuple(
        (exchange_label(eid), eid) for eid in sorted(SUPPORTED_EXCHANGES.keys())
    )


def passphrase_exchange_ids() -> frozenset:
    """``PASSPHRASE_EXCHANGES``, the set ``on_exchange_changed`` ticks the box on.

    ``PASSPHRASE_EXCHANGES`` is imported when first asked, so importing this
    file loads no exchange library and reads no settings.
    """
    from ...exchange.ccxt_connector import PASSPHRASE_EXCHANGES

    return frozenset(PASSPHRASE_EXCHANGES)


def exchange_items(wing: str) -> tuple:
    """The Add-exchange dropdown items for one wing, as (text, id) pairs."""
    if wing == STOCK_WING:
        return tuple(
            (EQUITY_ITEM_FORMAT.format(name=eid.capitalize()), eid)
            for eid in sorted(EQUITY_EXCHANGE_IDS)
        )
    return crypto_exchange_items()


def list_label_for(wing: str) -> str:
    """The heading above the Configured-exchanges list."""
    return STOCK_LIST_LABEL if wing == STOCK_WING else CRYPTO_LIST_LABEL


def add_group_title(sector: Any) -> str:
    """The title of the box holding the Add-exchange form, naming one sector.

    ``acs.display_name`` and ``acs.venue_noun`` fill ``ADD_GROUP_FORMAT``, and
    both builds read this one answer.
    """
    return ADD_GROUP_FORMAT.format(
        name=acs.display_name(sector), noun=acs.venue_noun(sector)
    )


def exchange_status_label() -> str:
    """The heading above the Exchange Status panel, the same in both builds."""
    return EXCHANGE_STATUS_LABEL


def venue_state(venue_id: Any, states: Any = None) -> str:
    """One venue's recorded state, ``VENUE_STATE_UNSET`` while nothing recorded one."""
    held = states if isinstance(states, dict) else {}
    found = str(held.get(str(venue_id or "").strip().lower()) or "")
    return found if found in VENUE_STATE_TOKENS else VENUE_STATE_UNSET


def venue_state_token(state: Any) -> str:
    """The ``design_system`` token name one venue state resolves."""
    return VENUE_STATE_TOKENS.get(str(state), VENUE_STATE_TOKENS[VENUE_STATE_UNSET])


def venue_state_colour(state: Any) -> str:
    """The colour one venue state draws."""
    return VENUE_STATE_COLOURS.get(str(state), VENUE_STATE_COLOURS[VENUE_STATE_UNSET])


def venue_row_style(state: Any) -> str:
    """The declarations one Exchange Status row paints its state with."""
    return VENUE_ROW_STYLE.format(colour=venue_state_colour(state))


def exchange_status_rows(wing: Any, states: Any = None) -> tuple:
    """Every venue ``venues_for_class`` answers for one sector, as drawn rows.

    A row is ``(text, venue_id, state, colour, style, tooltip)``, and a sector
    with no venue draws ``class_state``'s note under an empty venue id.
    """
    held = states if isinstance(states, dict) else {}
    found = []
    for venue in sorted(acs.venues_for_class(wing)):
        state = venue_state(venue, held)
        name = venue.capitalize()
        found.append(
            (
                VENUE_ROW_FORMAT.format(name=name, venue=venue),
                venue,
                state,
                venue_state_colour(state),
                venue_row_style(state),
                VENUE_ROW_TOOLTIP.format(name=name, words=VENUE_STATE_WORDS[state]),
            )
        )
    if not found:
        note = acs.class_state(wing)["note"]
        state = VENUE_STATE_UNSET
        found.append(
            (note, "", state, venue_state_colour(state), venue_row_style(state), note)
        )
    return tuple(found)


def exchange_status_lines(wing: Any, states: Any = None) -> tuple:
    """The text of every Exchange Status row, in drawn order."""
    return tuple(row[0] for row in exchange_status_rows(wing, states))


def row_venue_id(wing: Any, at: Any, states: Any = None) -> str:
    """The venue the row at ``at`` names, empty where that row names none."""
    rows = exchange_status_rows(wing, states)
    try:
        found = int(at)
    except (TypeError, ValueError):
        return ""
    if not 0 <= found < len(rows):
        return ""
    return str(rows[found][1])


def venue_grid_shape(count: Any = None) -> tuple:
    """The rows and columns ``count`` venue buttons divide one page into.

    ``VENUE_GRID_COLUMNS`` fixes the width, so both builds read one shape and
    a further venue lengthens the array rather than narrowing a button.
    """
    held = max(int(count or 0), 0)
    if held <= 0:
        return (0, 0)
    columns = min(VENUE_GRID_COLUMNS, held)
    rows = math.ceil(held / columns)
    return (rows, columns)


def venue_row_holds(count: Any = None) -> list:
    """How many venue buttons each row of one page holds, the top row first.

    Every row but the last holds a full ``columns`` and the last holds what is
    left, so no row is empty and the last row's buttons widen to fill it.
    """
    held = max(int(count or 0), 0)
    rows, columns = venue_grid_shape(held)
    if rows <= 0:
        return []
    counts = [columns] * (rows - 1)
    counts.append(held - columns * (rows - 1))
    return counts


def venue_cell(at: Any, count: Any = None) -> dict:
    """Where venue button ``at`` of ``count`` sits on its page, and what it spans.

    Carries the fields ``asset_class_surface.segment_cell`` answers, so
    ``segment_box`` paints the array's shared borders and rounds only the four
    outer corners, exactly as it does for the Sector buttons.
    """
    held = max(int(count or 0), 0)
    rows, columns = venue_grid_shape(held)
    counts = venue_row_holds(held)
    index = min(max(int(at), 0), max(held - 1, 0))
    row = 0
    before = 0
    for holds in counts:
        if index < before + holds:
            break
        before += holds
        row += 1
    if row >= len(counts):
        row = max(len(counts) - 1, 0)
        before = sum(counts[:row])
    holds = counts[row] if counts else 0
    column = index - before
    spans = acs.column_spans(columns, holds)
    return {
        "row": row,
        "column": column,
        "rows": rows,
        "columns": columns,
        "row_holds": holds,
        "grid_column": sum(spans[:column]) if spans else 0,
        "column_span": spans[column] if spans and column < len(spans) else 1,
    }


def venue_page_count(wing: Any, states: Any = None) -> int:
    """How many pages the sector's venues fill, one page at the fewest.

    Exactly ``VENUE_PAGE_HOLDS`` venues fill one page, so a sector at the
    limit draws no pages button.
    """
    held = len(exchange_status_rows(wing, states))
    return max(math.ceil(held / VENUE_PAGE_HOLDS), 1)


def venue_page_at(page: Any, pages: Any) -> int:
    """``page`` brought inside ``pages``, wrapping the last back to the first."""
    many = max(int(pages or 0), 1)
    try:
        found = int(page)
    except (TypeError, ValueError):
        return 0
    return found % many


def venue_next_page(page: Any, pages: Any) -> int:
    """The page the pages button moves to, the first again after the last."""
    return venue_page_at(venue_page_at(page, pages) + 1, pages)


def venue_page_offset(page: Any, pages: Any) -> int:
    """The ``exchange_status_rows`` index the first button of ``page`` names."""
    return venue_page_at(page, pages) * VENUE_PAGE_HOLDS


def venue_button_style(state: Any, cell: Any = None) -> str:
    """The Sector button skin one venue draws, accented by its API state.

    The form is ``asset_class_surface.button_style`` unchanged -- transparent
    ground, bold segment font, shared borders, hover, checked and disabled --
    and the accent is the colour ``venue_state_colour`` gives that state.
    """
    return acs.button_style(venue_state_colour(state), cell)


def exchange_status_page(wing: Any, page: Any = 0, states: Any = None) -> tuple:
    """The venue buttons one page of the Exchange Status array draws.

    Each button carries its row's own text, venue id, state, colour, row style
    and tooltip unchanged, plus the ``venue_cell`` it sits at and the Sector
    button skin its state accents. ``at`` stays the index into
    ``exchange_status_rows``, so a press reports the same row in either build.
    """
    rows = exchange_status_rows(wing, states)
    pages = max(math.ceil(len(rows) / VENUE_PAGE_HOLDS), 1)
    first = venue_page_offset(page, pages)
    held = rows[first : first + VENUE_PAGE_HOLDS]
    found = []
    for at, row in enumerate(held):
        cell = venue_cell(at, len(held))
        one = {
            "at": first + at,
            "text": row[0],
            "venue": row[1],
            "state": row[2],
            "colour": row[3],
            "style": row[4],
            "tooltip": row[5],
            "style_sheet": venue_button_style(row[2], cell),
        }
        one.update(cell)
        found.append(one)
    return tuple(found)


def venue_pages_button(wing: Any, page: Any = 0, states: Any = None) -> dict:
    """The pages control under the venue array, drawn only past one page.

    ``shown`` is False at ``VENUE_PAGE_HOLDS`` venues or fewer, so a sector
    that fits one page carries neither a pages button nor a scroll bar. The
    button takes the sector's own accent in the Sector button skin.
    """
    pages = venue_page_count(wing, states)
    here = venue_page_at(page, pages)
    onward = venue_next_page(here, pages)
    return {
        "shown": pages > 1,
        "page": here,
        "pages": pages,
        "next": onward,
        "text": VENUE_PAGES_FORMAT.format(page=here + 1, pages=pages),
        "tooltip": VENUE_PAGES_TOOLTIP.format(next=onward + 1, pages=pages),
        "style_sheet": acs.button_style(acs.accent(wing), venue_cell(0, 1)),
    }


def listed_exchange_position(listed: Any, exchange_id: Any) -> int:
    """Where ``exchange_id`` already sits in ``listed``, or ``NO_MATCH_INDEX``.

    Both builds call this before adding a line, so one venue cannot be drawn
    twice while ``add_exchange`` holds one entry for it.
    """
    tail = "(" + str(exchange_id) + ")"
    for at, line in enumerate(listed or []):
        if str(line).endswith(tail):
            return at
    return NO_MATCH_INDEX


def stored_credential_phrase(entry: Any) -> str:
    """The phrase an add reports, read off ``entry`` and not off the typed rows.

    ``test_api_connection`` is the only step that reaches a venue, and it
    reports that venue's own answer, so no phrase here claims one.
    """
    holder = entry if isinstance(entry, dict) else {}
    if any(holder.get(name) for name in CREDENTIAL_FIELDS):
        return ADDED_WITH_CREDENTIALS
    return ADDED_WITHOUT_CREDENTIALS


def banner_of(wing: str) -> dict:
    """The stock-wing banner, its words, its pieces and its colours."""
    return {
        "shown": wing == STOCK_WING,
        "text": STOCK_BANNER_TEXT,
        "lead": STOCK_BANNER_LEAD,
        "tail": STOCK_BANNER_TAIL,
        "pieces": list(STOCK_BANNER_PIECES),
        "word_wrap": STOCK_BANNER_WORD_WRAP,
        "style_sheet": STOCK_BANNER_STYLE,
        "marks": {
            "strong_open": STRONG_OPEN,
            "strong_close": STRONG_CLOSE,
            "strong_weight": STRONG_WEIGHT,
        },
        "tint": BANNER_TINT,
        "rgb": list(BANNER_TINT_RGB),
        "alpha": {
            "scale": ALPHA_SCALE,
            "reciprocal": ALPHA_RECIPROCAL,
            "fill": BANNER_FILL_ALPHA,
            "edge": BANNER_EDGE_ALPHA,
        },
        "colour_marks": {
            "open": COLOUR_OPEN,
            "join": COLOUR_JOIN,
            "close": COLOUR_CLOSE,
        },
        "border_width_px": BANNER_BORDER_WIDTH_PX,
        "border_kind": BANNER_BORDER_KIND,
        "padding_px": BANNER_PADDING_PX,
        "radius_px": BANNER_RADIUS_PX,
    }


def feedback_style(level: Any) -> str:
    """The one colour rule the feedback line carries for `level`."""
    return FEEDBACK_STYLE_FORMAT.format(
        color=FEEDBACK_COLORS.get(level, FEEDBACK_FALLBACK_COLOR)
    )


#: Every control name the TA Indicators page holds a weight slider under.
TA_SLIDER_NAMES = frozenset(
    ta_slider_name(name) for name, _weight in TA_INDICATOR_WEIGHTS
)


def ta_rows(values: Optional[dict] = None) -> tuple:
    """Every indicator weight row: label, position, figure and control name.

    ``values`` is a control-name-to-value mapping; a row whose slider it
    carries draws at that position, and every other row at its default.
    """
    rows = []
    for name, weight in TA_INDICATOR_WEIGHTS:
        held = (values or {}).get(ta_slider_name(name))
        position = ta_slider_value(weight) if held is None else int(held)
        rows.append(
            (
                ta_label(name),
                position,
                slider_label_text(position),
                ta_slider_name(name),
            )
        )
    return tuple(rows)


def slider_label_text(position: Any) -> str:
    """The figure printed beside a slider at `position`."""
    return TA_VALUE_FORMAT.format(weight=position / TA_SLIDER_SCALE)


def volume_label_text(position: Any) -> str:
    """The figure printed beside the volume slider."""
    return VOLUME_LABEL_FORMAT.format(value=position)


def index_of_data(items: Any, wanted: Any) -> int:
    """Where `wanted` sits among the items' data values, -1 when absent."""
    for at, pair in enumerate(items):
        if pair[1] == wanted:
            return at
    return NO_MATCH_INDEX


def index_of_text(texts: Any, wanted: Any) -> int:
    """Where `wanted` sits among the items' printed texts, -1 when absent."""
    for at, text in enumerate(texts):
        if text == wanted:
            return at
    return NO_MATCH_INDEX


INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
FLOAT_LIMIT = 2**1024
DEFAULT_DECIMALS = 2

REFUSED_TYPE = "this control takes a number, not {found}"
REFUSED_SIZE = "{found} is outside the range this control can hold"
REFUSED_TEXT = "this control takes text, not {found}"
REFUSED_FLAG = "this control takes a true or false value, not {found}"


def _named(value: Any) -> str:
    return type(value).__name__


def seed_whole(raw: Any, low: int, high: int) -> int:
    """The figure a whole-number control shows once it is given `raw`.

    Reproduces what the shipped control does, refusal for refusal. Text
    is refused. A value that is not a whole number is cut towards zero.
    A figure outside the platform's whole-number range is refused rather
    than wrapped. Anything left is held to the control's own range.
    """
    if type(raw) is bool:
        number = int(raw)
    elif type(raw) is float:
        if not math.isfinite(raw):
            raise OverflowError(REFUSED_SIZE.format(found=raw))
        number = int(raw)
    elif type(raw) is int:
        number = raw
    else:
        raise TypeError(REFUSED_TYPE.format(found=_named(raw)))
    if not INT32_MIN <= number <= INT32_MAX:
        raise OverflowError(REFUSED_SIZE.format(found=number))
    return min(high, max(low, number))


def seed_decimal(raw: Any, low: float, high: float, decimals: int) -> float:
    """The figure a decimal control shows once it is given `raw`.

    Text is refused, and a whole number too large to become a decimal is
    refused. Not-a-number and plus-infinity both print the top of the
    range; minus-infinity prints the bottom. What is left is held to the
    range and then cut to the control's decimal places.
    """
    if type(raw) is bool:
        number = float(raw)
    elif type(raw) is int:
        if not -FLOAT_LIMIT < raw < FLOAT_LIMIT:
            raise OverflowError(REFUSED_SIZE.format(found=_named(raw)))
        number = float(raw)
    elif type(raw) is float:
        number = raw
    else:
        raise TypeError(REFUSED_TYPE.format(found=_named(raw)))
    if math.isnan(number):
        return float(high)
    return float(round(min(high, max(low, number)), decimals))


def seed_flag(raw: Any) -> bool:
    """Whether a tick box is ticked once it is given `raw`."""
    if type(raw) is bool:
        return raw
    if type(raw) is int:
        if not INT32_MIN <= raw <= INT32_MAX:
            raise OverflowError(REFUSED_SIZE.format(found=_named(raw)))
        return bool(raw)
    raise TypeError(REFUSED_FLAG.format(found=_named(raw)))


def seed_text(raw: Any) -> str:
    """The text a text field shows once it is given `raw`."""
    if raw is None:
        return EMPTY_TEXT
    if type(raw) is str:
        return raw
    raise TypeError(REFUSED_TEXT.format(found=_named(raw)))


def seed_index(raw: Any, count: int) -> int:
    """Which item a list control shows once it is given `raw`.

    Text is refused. A figure outside the platform's whole-number range
    is refused. A figure outside the list shows no item at all.
    """
    if type(raw) is bool:
        at = int(raw)
    elif type(raw) is float:
        if not math.isfinite(raw):
            raise OverflowError(REFUSED_SIZE.format(found=raw))
        at = int(raw)
    elif type(raw) is int:
        at = raw
    else:
        raise TypeError(REFUSED_TYPE.format(found=_named(raw)))
    if not INT32_MIN <= at <= INT32_MAX:
        raise OverflowError(REFUSED_SIZE.format(found=at))
    return at if FIRST_INDEX <= at < count else NO_MATCH_INDEX


def data_index(items: Any, wanted: Any) -> int:
    """Where `wanted` sits among the items' data values, as the list finds it.

    A whole number too large for the platform's data slot is refused
    rather than reported absent.
    """
    if type(wanted) is int and not INT64_MIN <= wanted <= INT64_MAX:
        raise OverflowError(REFUSED_SIZE.format(found=_named(wanted)))
    return index_of_data(items, wanted)


def text_index(texts: Any, wanted: Any) -> int:
    """Where `wanted` sits among the items' printed texts, as the list finds it."""
    if wanted is None:
        return NO_MATCH_INDEX
    if type(wanted) is not str:
        raise TypeError(REFUSED_TEXT.format(found=_named(wanted)))
    return index_of_text(texts, wanted)


def signal_for(spec: dict) -> Optional[str]:
    """The signal one control emits when the operator moves it."""
    if "signal" in spec:
        return spec["signal"]
    return SIGNAL_FOR_KIND.get(spec["kind"])


def spec_for(name: str) -> dict:
    """The one control spec carrying `name`."""
    for spec in CONTROL_SPECS:
        if spec["name"] == name:
            return spec
    raise KeyError(name)


def specs_on(tab: str) -> tuple:
    """Every control spec belonging to one tab, in painted order."""
    return tuple(spec for spec in CONTROL_SPECS if spec["tab"] == tab)


def group_titles(tab: str, sector: Any) -> tuple:
    """Every boxed group title on one tab, in painted order."""
    found = []
    for owner, title in GROUPS:
        if owner != tab:
            continue
        if owner == EXCHANGE_TAB and title == CRYPTO_ADD_GROUP:
            found.append(add_group_title(sector))
        else:
            found.append(title)
    return tuple(found)


def actions() -> dict:
    """Every signal the dialog connects, and what each one runs.

    One entry is one connection a built dialog holds. The volume slider
    carries two, and each indicator weight carries its own. Built from
    ``connect_order`` so the bag cannot name a signal the list omits.
    """
    return dict(connect_order())


def connection_counts() -> dict:
    """How many connections a built dialog holds."""
    return {"run_time": len(actions())}


def read_mapping(value: Any, key: str, default: Any) -> Any:
    """One value out of a stored group, refusing as the dialog refuses.

    The shipped dialog calls ``.get`` on whatever the store returned for
    the group, so a group stored as anything but a mapping raises
    ``AttributeError`` there and here alike.
    """
    return value.get(key, default)


class SettingsSource:
    """The settings store the dialog reads and writes, from a mapping.

    Holds its values in memory. ``set`` records every write and raises
    ``KeyError`` for a name in ``refuses``, which is what the shipped
    store does for a setting it does not carry.
    """

    def __init__(
        self,
        values: Optional[dict] = None,
        exchanges: Any = None,
        refuses: Any = (),
    ) -> None:
        self.values = dict(values or {})
        self.exchanges = list(exchanges) if exchanges is not None else []
        self.refuses = tuple(refuses)
        self.written: list = []
        self.removed: list = []

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key in self.refuses:
            raise KeyError(f"Unknown setting: {key}")
        self.values[key] = value
        self.written.append([key, value])

    def list_exchanges(self) -> list:
        return list(self.exchanges)

    def get_exchange(self, exchange_id: Any) -> Optional[dict]:
        for one in self.exchanges:
            if isinstance(one, dict) and one.get(EXCHANGE_ID_KEY) == exchange_id:
                return dict(one)
        return None

    def add_exchange(self, config: Any) -> None:
        """Store ``config`` under its id, keeping a token it leaves empty.

        ``SettingsManager.add_exchange`` merges the same way, so a blank
        re-add cannot read differently here.
        """
        entry = dict(config)
        for at, one in enumerate(self.exchanges):
            if not isinstance(one, dict):
                continue
            if one.get(EXCHANGE_ID_KEY) != entry.get(EXCHANGE_ID_KEY):
                continue
            for name in CREDENTIAL_FIELDS:
                if not entry.get(name):
                    entry[name] = one.get(name, "")
            self.exchanges[at] = entry
            return
        self.exchanges.append(entry)

    def remove_exchange(self, exchange_id: Any) -> None:
        self.removed.append(exchange_id)
        self.exchanges = [
            one
            for one in self.exchanges
            if not isinstance(one, dict) or one.get(EXCHANGE_ID_KEY) != exchange_id
        ]


class StatusLogSink:
    """The status line, keeping every message it was handed."""

    def __init__(self) -> None:
        self.lines: list = []

    def log(self, message: Any, level: Any = INFO_LEVEL) -> None:
        self.lines.append([message, level])


class ValidationResult:
    """One answer from the credential checker."""

    def __init__(self, success: Any, message: Any, details: Any = None) -> None:
        self.success = success
        self.message = message
        self.details = details


class ValidatorSource:
    """The credential checker, answering from a value or an exception."""

    def __init__(
        self, result: Any = None, raises: Optional[BaseException] = None
    ) -> None:
        self.result = result
        self.raises = raises
        self.asked: list = []

    def validate(self, exchange_id: Any, key: Any, secret: Any, phrase: Any) -> Any:
        self.asked.append([exchange_id, key, secret, phrase])
        if self.raises is not None:
            raise self.raises
        return self.result


class SoundEngineSink:
    """The sound engine, keeping the configs it was given and what it played."""

    def __init__(self, raises: Optional[BaseException] = None) -> None:
        self.raises = raises
        self.configs: list = []
        self.played: list = []
        self._available = True
        self._cache: dict = {"stale": 1}

    def update_config(self, config: Any) -> None:
        if self.raises is not None:
            raise self.raises
        self.configs.append(config)

    def play(self, name: Any) -> None:
        self.played.append(name)


class SettingsDialogModel:
    """The Settings dialog's state, filled by ``build``.

    ``values`` carries one entry per named control. ``rows`` carries the
    painted order of every labelled row. ``calls`` records every step the
    dialog ran, in order, so a run that refused part way still reports
    what it reached.
    """

    def __init__(
        self,
        settings: Any = None,
        status_log: Any = None,
        wing: Any = DEFAULT_WING,
        validator: Any = None,
        sound: Any = None,
        encryptor: Any = None,
    ) -> None:
        self.settings = settings
        self.status_log = status_log
        self.wing = wing_or_default(wing)
        #: The sector the dialog was opened from, before `wing_or_default`
        #: collapses it onto one of two wings. Only the Exchange Status
        #: panel reads it.
        self.asset_class = acs.normalise(wing)
        self.venue_states: dict = {}
        self.validator = validator
        self.sound = sound
        self.encryptor = encryptor
        self.window_title = title_for(self.wing)
        self.minimum_size = MINIMUM_SIZE
        self.last_validation: Any = None
        self.values: dict = {}
        self.texts: dict = {}
        self.styles: dict = {}
        self.enabled: dict = {}
        self.visible: dict = {}
        self.tooltips: dict = {}
        self.rows: list = []
        self.listed_exchanges: list = []
        self.calls: list = []
        self.processed_events: list = []
        self.accepted = False
        self.rejected = False
        self.emitted: list = []
        self.prints: list = []
        self.message_boxes: list = []

    def _record(self, name: str, *carried: Any) -> None:
        self.calls.append([name, *carried])

    def build(self) -> None:
        """Lay out every tab, then seed every control from the store."""
        self._record("build", self.wing)
        self._setup()
        self._load_current()

    def _setup(self) -> None:
        for spec in CONTROL_SPECS:
            name = spec["name"]
            self.enabled[name] = True
            self.visible[name] = spec.get("visible", True)
            if "tooltip" in spec:
                self.tooltips[name] = spec["tooltip"]
            self.values[name] = self._seed(spec)
            if spec["label"]:
                self.rows.append([spec["tab"], spec["group"], spec["label"], name])
        for button in BUTTON_NAMES_BY_TEXT.values():
            self.enabled[button] = True
        self.values["new_exchange_items"] = [
            list(one) for one in exchange_items(self.wing)
        ]
        self.values[TA_ROWS] = [list(one) for one in ta_rows(self.values)]
        self.texts["vol_label"] = volume_label_text(spec_for("sound_volume")["value"])
        self.texts["api_feedback"] = ""
        self.styles["api_feedback"] = ""
        for tab, group, label, name, text, style in TEXT_ROWS:
            self.texts[name] = text
            self.styles[name] = style
            self.rows.append([tab, group, label, name])
        self.texts["list_label"] = exchange_status_label()
        self.values["exchange_list"] = list(
            exchange_status_lines(self.asset_class, self.venue_states)
        )
        self.texts["add_group"] = add_group_title(self.asset_class)
        self.texts["banner"] = STOCK_BANNER_TEXT if self.wing == STOCK_WING else ""
        self.styles["banner"] = STOCK_BANNER_STYLE if self.wing == STOCK_WING else ""
        if self.wing == STOCK_WING:
            for name in STOCK_DISABLED_CONTROLS:
                self.enabled[name] = False
                self.tooltips[name] = STOCK_DISABLED_TIP
        self.on_exchange_changed()

    def _seed(self, spec: dict) -> Any:
        kind = spec["kind"]
        if kind == CHECK:
            return spec["checked"]
        if kind in (SPIN, SLIDER):
            return seed_whole(spec.get("value", spec["range"][0]), *spec["range"])
        if kind == DOUBLE_SPIN:
            return self._decimal(spec, spec.get("value", spec["range"][0]))
        if kind == COMBO_DATA:
            if "current_data" in spec:
                return index_of_data(spec["items"], spec["current_data"])
            return FIRST_INDEX
        if kind == COMBO_TEXT:
            if "current_text" in spec:
                return index_of_text(spec["items"], spec["current_text"])
            return FIRST_INDEX
        if kind == LIST:
            return []
        return EMPTY_TEXT

    def _decimal(self, spec: dict, raw: Any) -> float:
        low, high = spec["range"]
        return seed_decimal(raw, low, high, spec.get("decimals", DEFAULT_DECIMALS))

    def _seed_control(self, name: str, raw: Any) -> Any:
        """One stored value put into one control, refusing as it refuses."""
        spec = spec_for(name)
        kind = spec["kind"]
        if kind in (LINE, TEXT_AREA):
            return seed_text(raw)
        if kind == CHECK:
            return seed_flag(raw)
        if kind in (SPIN, SLIDER):
            return seed_whole(raw, *spec["range"])
        if kind == DOUBLE_SPIN:
            return self._decimal(spec, raw)
        if kind in (COMBO_TEXT, COMBO_DATA):
            return seed_index(raw, len(self._items_for(spec)))
        raise KeyError(name)

    def _items_for(self, spec: dict) -> Any:
        if spec["name"] == "new_exchange":
            return self.values["new_exchange_items"]
        return spec["items"]

    def _show_stored(self, name: str, raw: Any) -> None:
        """One stored value put into one control, as that control admits it.

        A drop-down holds a row number, so a value its list does not offer
        leaves the row the build chose.
        """
        spec = spec_for(name)
        kind = spec["kind"]
        if kind == COMBO_TEXT:
            found = text_index(self._items_for(spec), raw)
        elif kind == COMBO_DATA:
            found = data_index(self._items_for(spec), raw)
        else:
            self.values[name] = self._seed_control(name, raw)
            return
        if found >= FIRST_INDEX:
            self.values[name] = found

    def _load_stored(self, key: str, show: Any, raw: Any) -> None:
        """Puts one stored value into its control, recording a value it refuses."""
        try:
            show(raw)
        except Exception as exc:  # noqa: BLE001
            self._record("load_refused", key, str(exc))

    def _ai_rows(self) -> tuple:
        """Every ``ai_monitor`` key, from the one list naming its controls."""
        return tuple(
            (
                key,
                partial(self._pair_value, name),
                partial(self._show_stored, name),
                fallback,
            )
            for key, fallback, name in AI_LOAD_KEYS
        )

    def _ta_weight_read(self, name: str) -> float:
        """The weight the slider named ``name`` is showing."""
        return self.values[name] / TA_SLIDER_SCALE

    def _ta_weight_show(self, name: str, value: Any) -> None:
        """Put the stored weight ``value`` on the slider named ``name``."""
        self.admit(name, int(round(float(value) * TA_SLIDER_SCALE)))

    def _ta_weight_rows(self) -> tuple:
        """Every ``ta_indicator_weights`` key, one per indicator weight slider."""
        return tuple(
            (
                name,
                partial(self._ta_weight_read, ta_slider_name(name)),
                partial(self._ta_weight_show, ta_slider_name(name)),
                weight,
            )
            for name, weight in TA_INDICATOR_WEIGHTS
        )

    def _volume_read(self) -> float:
        """The fraction the engine holds for the percent the slider is showing."""
        return self.values[VOLUME_NAME] / VOLUME_SCALE

    def _volume_show(self, value: Any) -> None:
        """Put the stored fraction on the slider as whole percent."""
        self.admit(VOLUME_NAME, int(round(float(value) * VOLUME_SCALE)))

    def _sound_rows(self) -> tuple:
        """Every ``sound`` key, from the one list naming its controls.

        The slider shows whole percent and ``SoundConfig.volume`` holds a
        fraction, so the volume row divides out and multiplies back.
        """
        switches = tuple(
            (
                key,
                partial(self._pair_value, name),
                partial(self._show_stored, name),
                spec_for(name)["checked"],
            )
            for key, name in SOUND_CONFIG_FIELDS
        )
        return switches + (
            (
                VOLUME_FIELD,
                self._volume_read,
                self._volume_show,
                spec_for(VOLUME_NAME)["value"] / VOLUME_SCALE,
            ),
        )

    def _sms_rows(self) -> tuple:
        """Every ``message_channels`` key, from the one list naming its controls."""
        return tuple(
            (
                key,
                partial(self._pair_value, name),
                partial(self._show_stored, name),
                getattr(SMS_BUILT, key),
            )
            for key, name in SMS_CONFIG_FIELDS
        )

    def _stored_groups(self) -> tuple:
        """Every group the dialog persists as one key, with the rows inside it."""
        return (
            (AI_GROUP_KEY, self._ai_rows()),
            (TA_WEIGHT_GROUP_KEY, self._ta_weight_rows()),
            (SOUND_GROUP_KEY, self._sound_rows()),
            (MESSAGE_CHANNELS_GROUP_KEY, self._sms_rows()),
        )

    def _load_current(self) -> None:
        if not self.settings:
            self._record("load_skipped")
            return
        self._record("load_current")
        for key, fallback, name in SETTING_LOAD_KEYS:
            self._load_stored(
                key,
                partial(self._show_stored, name),
                self.settings.get(key, fallback),
            )

        for group, rows in self._stored_groups():
            stored = self.settings.get(group, {})
            for key, _read, show, fallback in rows:
                self._load_stored(
                    group + "." + key, show, read_mapping(stored, key, fallback)
                )

        for entry in self.settings.list_exchanges():
            eid = (entry.get(EXCHANGE_ID_KEY, "") or "").lower()
            is_equity = eid in EQUITY_EXCHANGE_IDS
            if self.wing == STOCK_WING and not is_equity:
                continue
            if self.wing == CRYPTO_WING and is_equity:
                continue
            self.listed_exchanges.append(
                CONFIGURED_ITEM_FORMAT.format(
                    name=entry.get(DISPLAY_NAME_KEY, ""),
                    eid=entry.get(EXCHANGE_ID_KEY, ""),
                )
            )
        self.values["exchange_list"] = list(self.listed_exchanges)
        if self.sound:
            self.push_sound_config()

    def current_exchange_id(self) -> Any:
        """The id of the exchange the dropdown is showing."""
        items = self.values["new_exchange_items"]
        at = self.values["new_exchange"]
        if not items or at < FIRST_INDEX or at >= len(items):
            return None
        return items[at][1]

    def on_exchange_changed(self) -> None:
        """Tick the passphrase box for an exchange that needs one.

        ``show_passphrase`` then draws ``new_passphrase`` for that venue alone.
        """
        eid = self.current_exchange_id()
        self.values["pp_check"] = eid in passphrase_exchange_ids()
        self.texts["api_feedback"] = ""
        self._record("on_exchange_changed", eid)
        self.show_passphrase(self.values["pp_check"])

    def show_passphrase(self, on: Any) -> None:
        """Show or hide the passphrase field."""
        self.visible["new_passphrase"] = on
        self._record("show_passphrase", on)

    def set_feedback(self, message: Any, level: Any = INFO_LEVEL) -> None:
        """Print one line under the Add-exchange form, coloured by level."""
        self.texts["api_feedback"] = message
        self.styles["api_feedback"] = feedback_style(level)
        self._record("set_feedback", level)

    def _typed_credentials(self) -> tuple:
        key = self.values["new_api_key"].strip()
        secret = self.values["new_api_secret"].strip()
        if looks_like_pem(secret):
            secret = unescape_pem_newlines(secret)
        phrase = (
            self.values["new_passphrase"].strip() if self.values["pp_check"] else ""
        )
        return key, secret, phrase

    def _process_events(self) -> None:
        self.processed_events.append(PROCESS_EVENTS_REASON)

    def test_api_connection(self) -> Any:
        """Check the typed credentials and report on the feedback line."""
        self._record("test_api_connection")
        eid = self.current_exchange_id()
        key, secret, phrase = self._typed_credentials()

        if not key or not secret:
            self.set_feedback(MISSING_CREDENTIALS_FEEDBACK, ERROR_LEVEL)
            return None

        self.set_feedback(
            TESTING_FEEDBACK_FORMAT.format(name=eid.capitalize()), INFO_LEVEL
        )
        self.enabled["test_btn"] = False
        self.enabled["add_btn"] = False
        self._process_events()

        try:
            result = self.validator.validate(eid, key, secret, phrase)
            if result.success:
                message = result.message
                if result.details:
                    message += BALANCES_FEEDBACK_FORMAT.format(details=result.details)
                self.set_feedback(message, SUCCESS_LEVEL)
                if self.status_log:
                    self.status_log.log(result.message, SUCCESS_LEVEL)
                    if result.details:
                        self.status_log.log(
                            BALANCES_LOG_FORMAT.format(details=result.details),
                            INFO_LEVEL,
                        )
                self.last_validation = result
                return result
            message = result.message
            if result.details:
                message += DETAILS_FEEDBACK_FORMAT.format(details=result.details)
            self.set_feedback(message, ERROR_LEVEL)
            if self.status_log:
                self.status_log.log(
                    API_FAILED_LOG_FORMAT.format(eid=eid, message=result.message),
                    ERROR_LEVEL,
                )
            self.last_validation = None
            return None
        except Exception as exc:
            self.set_feedback(
                TEST_FAILED_FEEDBACK_FORMAT.format(error=exc), ERROR_LEVEL
            )
            self.last_validation = None
            return None
        finally:
            self.enabled["test_btn"] = True
            self.enabled["add_btn"] = True

    def _master_phrase(self) -> str:
        return vault_phrase(self.settings.get("username", ""))

    def add_exchange(self) -> None:
        """Check the credentials, store the exchange and close the dialog."""
        self._record("add_exchange")
        self.enabled["add_btn"] = False
        self.enabled["test_btn"] = False
        self._process_events()

        try:
            eid = self.current_exchange_id()
            key, secret, phrase = self._typed_credentials()

            if key and secret:
                result = self.test_api_connection()
                if result is None or not result.success:
                    return

            config = dict(zip(EXCHANGE_CONFIG_FIELDS, EXCHANGE_CONFIG_DEFAULTS))
            config[EXCHANGE_ID_KEY] = eid
            config[DISPLAY_NAME_KEY] = eid.capitalize()

            if key and secret:
                master = self._master_phrase()
                config[KEY_FIELD] = self.encryptor(key, master)
                config[SIGNING_FIELD] = self.encryptor(secret, master)
                if phrase:
                    config[PHRASE_FIELD] = self.encryptor(phrase, master)

            self.settings.add_exchange(config)
            if listed_exchange_position(self.listed_exchanges, eid) == NO_MATCH_INDEX:
                self.listed_exchanges.append(
                    EXCHANGE_ITEM_FORMAT.format(name=eid.capitalize(), eid=eid)
                )
            self.values["exchange_list"] = list(self.listed_exchanges)
            for name in TYPED_CREDENTIAL_CONTROLS:
                self.values[name] = EMPTY_TEXT

            how = stored_credential_phrase(self.settings.get_exchange(eid))
            self.set_feedback(
                ADDED_FEEDBACK_FORMAT.format(name=eid.capitalize(), how=how),
                SUCCESS_LEVEL,
            )
            if self.status_log:
                self.status_log.log(
                    ADDED_LOG_FORMAT.format(name=eid.capitalize(), how=how),
                    SUCCESS_LEVEL,
                )
            self.message_boxes.append(
                [
                    INFORMATION_ICON,
                    ADDED_BOX_TITLE,
                    ADDED_BOX_FORMAT.format(name=eid.capitalize(), how=how),
                ]
            )
            self.accepted = True
        finally:
            self.enabled["add_btn"] = True
            self.enabled["test_btn"] = True

    def remove_exchange(self, selected: Any = None) -> None:
        """Drop the selected exchange from the store and the list."""
        self._record("remove_exchange", selected)
        if selected is None:
            self.set_feedback(NO_SELECTION_FEEDBACK, WARNING_LEVEL)
            return
        eid = selected.split("(")[-1].rstrip(")")
        self.settings.remove_exchange(eid)
        if selected in self.listed_exchanges:
            self.listed_exchanges.remove(selected)
        self.values["exchange_list"] = list(self.listed_exchanges)
        self.set_feedback(
            REMOVED_FEEDBACK_FORMAT.format(name=eid.capitalize()), INFO_LEVEL
        )
        if self.status_log:
            self.status_log.log(REMOVED_LOG_FORMAT.format(eid=eid), WARNING_LEVEL)

    def update_volume_label(self, position: Any) -> None:
        """Print the volume figure beside the slider."""
        self.texts["vol_label"] = volume_label_text(position)
        self._record("update_volume_label", position)

    def update_weight_label(self) -> None:
        """Redraw the twelve weight rows so each prints its slider's figure."""
        self.values[TA_ROWS] = [list(one) for one in ta_rows(self.values)]
        self._record("update_weight_label")

    def sfx_volume_changed(self, position: Any) -> None:
        """Hand the sound engine a fresh config and clear its cache.

        Volume is baked into each sample when it is made, so the cache
        must be dropped for the new volume to be heard.
        """
        self._record("sfx_volume_changed", position)
        try:
            config = {field: self.values[name] for field, name in SOUND_CONFIG_FIELDS}
            config["volume"] = position / VOLUME_SCALE
            self.sound.update_config(config)
            self.sound._available = False
            self.sound._cache = {}
        except Exception as exc:
            self._record("sfx_volume_failed", type(exc).__name__)

    def push_sound_config(self) -> None:
        """Hand the engine every switch at the volume the slider is showing.

        Wired to each sound box, so one box ticked on its own reaches the
        engine without the slider moving.
        """
        self._record("push_sound_config")
        self.sfx_volume_changed(self.values[VOLUME_NAME])

    def fill_gateway_email(self) -> None:
        """Build the Gateway Email row from the carrier and the typed number.

        A number the carrier's gateway cannot address, and the manual choice,
        both leave the row as the operator left it.
        """
        self._record("fill_gateway_email")
        carrier = CARRIER_NAMES[self.values["sms_carrier"]]
        built = gateway_address(carrier, self.values["sms_phone"])
        if built:
            self.admit("sms_gateway", built)

    def test_sound(self, name: Any) -> None:
        """Apply the current volume, then play one sound."""
        self._record("test_sound", name)
        self.sfx_volume_changed(self.values[VOLUME_NAME])
        self.sound.play(name)

    def test_ai_handshake(self) -> None:
        """Report whether the AI Monitor has what it needs to connect."""
        self._record("test_ai_handshake")
        key = self.values["ai_api_key"].strip()
        connect = self.values["ai_connect_phrase"].strip()
        confirm = self.values["ai_confirm_phrase"].strip()
        if not key:
            self.texts["ai_status"] = AI_MISSING_CREDENTIAL_TEXT
            self.styles["ai_status"] = AI_ERROR_STYLE
            return
        if not connect or not confirm:
            self.texts["ai_status"] = AI_MISSING_PHRASE_TEXT
            self.styles["ai_status"] = AI_ERROR_STYLE
            return
        self.texts["ai_status"] = AI_SAVED_TEXT
        self.styles["ai_status"] = AI_OK_STYLE

    def _pair_value(self, name: str) -> Any:
        spec = spec_for(name)
        value = self.values[name]
        if spec["kind"] == COMBO_TEXT:
            return spec["items"][value]
        if spec["kind"] == COMBO_DATA:
            return spec["items"][value][1]
        if spec["kind"] == LINE:
            return value.strip()
        return value

    def save(self) -> dict:
        """Write every setting, report what failed, and close the dialog.

        The dialog always closes. A group the store refused is named on
        the status line and in a warning box, and is not persisted.
        """
        self._record("save")
        self.prints.append(SAVE_CALLED_PRINT)
        if not self.settings:
            self.prints.append(NO_MANAGER_PRINT)
            self.accepted = True
            return {"saved": 0, "failed": [], "closed": True}

        saved = 0
        failed: list = []
        for key, name in SAVE_PAIRS:
            try:
                self.settings.set(key, self._pair_value(name))
                saved += 1
            except Exception as exc:
                failed.append(FAILED_ENTRY_FORMAT.format(key=key, error=exc))
                self.prints.append(SAVE_ERROR_PRINT_FORMAT.format(key=key, error=exc))

        for key, rows in self._stored_groups():
            try:
                self.settings.set(
                    key, {name: read() for name, read, _show, _fallback in rows}
                )
                saved += 1
            except Exception as exc:
                failed.append(FAILED_ENTRY_FORMAT.format(key=key, error=exc))
                self.prints.append(SAVE_ERROR_PRINT_FORMAT.format(key=key, error=exc))

        self.emitted.append(QT_SIGNALS[0])

        if self.status_log:
            if failed:
                self.status_log.log(
                    PARTIAL_LOG_FORMAT.format(
                        saved=saved,
                        count=len(failed),
                        names=FAILED_JOIN.join(failed),
                    ),
                    ERROR_LEVEL,
                )
            else:
                self.status_log.log(CLEAN_LOG_FORMAT.format(saved=saved), SUCCESS_LEVEL)

        self.prints.append(SAVE_DONE_PRINT_FORMAT.format(saved=saved))

        if failed:
            self.message_boxes.append(
                [
                    WARNING_ICON,
                    PARTIAL_BOX_TITLE,
                    PARTIAL_BOX_FORMAT.format(
                        saved=saved,
                        count=len(failed),
                        names=PARTIAL_BOX_JOIN.join(
                            PARTIAL_BOX_ENTRY_FORMAT.format(entry=one) for one in failed
                        ),
                    ),
                ]
            )

        self.accepted = True
        return {"saved": saved, "failed": list(failed), "closed": True}

    def cancel(self) -> None:
        """Close the dialog, writing nothing."""
        self._record("cancel")
        self.rejected = True

    def admit(self, name: str, value: Any) -> Any:
        """Store ``value`` under ``name`` as that control admits it.

        A ``list`` control keeps the lines it is given; every other kind
        goes through ``_seed_control``.
        """
        if spec_for(name)["kind"] == LIST:
            self.values[name] = list(value or [])
        else:
            self.values[name] = self._seed_control(name, value)
        if name in TA_SLIDER_NAMES:
            self.values[TA_ROWS] = [list(one) for one in ta_rows(self.values)]
        return self.values[name]

    def edit(self, name: str, value: Any) -> None:
        """One operator edit, admitted as the control admits it.

        The control takes the value the same way it takes a stored one,
        and every action wired to that control then runs.
        """
        spec = spec_for(name)
        self.admit(name, value)
        self._record("edit", name)
        signal = signal_for(spec)
        if signal is None:
            return
        for wired, handler in connect_order():
            head = wired.split(".")
            if head[0] != name or head[1] != signal:
                continue
            getattr(self, handler)(*self._handler_arguments(handler, name))

    def _handler_arguments(self, handler: str, name: str) -> tuple:
        if handler in ("update_volume_label", "sfx_volume_changed"):
            return (self.values[name],)
        if handler == "show_passphrase":
            return (self.values[name],)
        return ()

    def painted(self) -> dict:
        """Every widget each tab paints, in painted order, as kind and text."""
        found = {}
        for tab in TAB_TITLES:
            walker = _Walker(self)
            walker.block(LAYOUT[tab])
            found[tab] = [list(one) for one in walker.found]
        return found


def painted_kind(spec: dict) -> str:
    """The painted kind one control spec is drawn as."""
    return PAINTED_KIND[spec["kind"]]


def _combo_text(spec: dict, at: Any) -> str:
    items = spec["items"] if "items" in spec else ()
    if not items or not isinstance(at, int) or at < FIRST_INDEX or at >= len(items):
        return EMPTY_TEXT
    one = items[at]
    return one[0] if isinstance(one, tuple) else one


def control_painted_text(spec: dict, values: dict) -> str:
    """The text one control prints once it has been seeded."""
    kind = painted_kind(spec)
    if kind in SILENT_KINDS:
        return EMPTY_TEXT
    if kind == "check":
        return spec["text"]
    if kind == "combo":
        if spec["kind"] == COMBO_DATA:
            at = values[spec["name"]]
            items = spec["items"] if "items" in spec else values["new_exchange_items"]
            if not isinstance(at, int) or at < FIRST_INDEX or at >= len(items):
                return EMPTY_TEXT
            return items[at][0]
        return _combo_text(spec, values[spec["name"]])
    return values[spec["name"]]


class _Walker:
    """Turns one tab's layout tree into the widgets it paints, in order."""

    def __init__(self, model: "SettingsDialogModel") -> None:
        self.model = model
        self.found: list = []

    def emit(self, kind: str, printed: Any) -> None:
        self.found.append([kind, printed])

    def block(self, node: Any) -> None:
        role = node[0]
        if role == SCROLL:
            self.block(node[1])
            return
        for item in node[1]:
            self.item(item)

    def item(self, item: Any) -> None:
        role = item[0]
        if role == STRETCH:
            return
        if role == BANNER:
            if self.model.wing == STOCK_WING:
                self.emit(LABEL, STOCK_BANNER_TEXT)
            return
        if role == LABEL:
            self.emit(LABEL, item[1])
            return
        if role == BUTTON:
            self.emit(BUTTON, item[1])
            return
        if role == TEXT:
            named = item[1]
            if named in TEXT_ROW_LABELS:
                self.emit(LABEL, TEXT_ROW_LABELS[named])
            self.emit(LABEL, self.model.texts[named])
            return
        if role == ROW:
            for inner in item[1]:
                self.item(inner)
            return
        if role == GROUP:
            title = item[1]
            if title == ADD_GROUP_BY_WING:
                title = add_group_title(self.model.asset_class)
            self.emit(GROUP, title)
            self.block(item[2])
            return
        if role == TA_ROWS:
            for label, _position, printed, _name in ta_rows(self.model.values):
                self.emit(LABEL, label)
                self.emit("slider", EMPTY_TEXT)
                self.emit(LABEL, printed)
            return
        if role == SOUND_ROW:
            for printed, _name, _tip in SOUND_TEST_BUTTONS:
                self.emit(BUTTON, printed)
            return
        spec = spec_for(item[1])
        if spec["label"]:
            self.emit(LABEL, spec["label"])
        self.emit(painted_kind(spec), control_painted_text(spec, self.model.values))


def _plain(node: Any) -> Any:
    """`node` as nested lists and bags, so the payload carries no tuples."""
    if isinstance(node, tuple):
        return [_plain(one) for one in node]
    if isinstance(node, dict):
        return {key: _plain(value) for key, value in node.items()}
    return node


def build_view_model(model: SettingsDialogModel) -> dict:
    """Everything the frontend needs to paint the dialog, as plain values."""
    return {
        "window_title": model.window_title,
        "minimum_size": list(model.minimum_size),
        "wing": model.wing,
        "tabs": list(TAB_TITLES),
        "scrolling_tabs": list(SCROLLING_TABS),
        "groups": {
            tab: list(group_titles(tab, model.asset_class)) for tab in TAB_TITLES
        },
        "painted": model.painted(),
        "layout": {tab: _plain(LAYOUT[tab]) for tab in TAB_TITLES},
        "rows": [list(one) for one in model.rows],
        "values": dict(model.values),
        "texts": dict(model.texts),
        "styles": dict(model.styles),
        "enabled": dict(model.enabled),
        "visible": dict(model.visible),
        "tooltips": dict(model.tooltips),
        "control_specs": [_plain(dict(one)) for one in CONTROL_SPECS],
        "exchange_items": [list(one) for one in exchange_items(model.wing)],
        "exchange_status": {
            "label": exchange_status_label(),
            "asset_class": model.asset_class,
            "rows": [
                list(one)
                for one in exchange_status_rows(model.asset_class, model.venue_states)
            ],
            "page": [
                dict(one)
                for one in exchange_status_page(
                    model.asset_class, 0, model.venue_states
                )
            ],
            "pages": venue_pages_button(model.asset_class, 0, model.venue_states),
            "page_holds": VENUE_PAGE_HOLDS,
            "grid_columns": VENUE_GRID_COLUMNS,
        },
        TA_ROWS: [list(one) for one in ta_rows(model.values)],
        "sound_test_buttons": [list(one) for one in SOUND_TEST_BUTTONS],
        "spacing": {
            "content": dict(CONTENT_SPACING),
            "group_form": dict(GROUP_FORM_SPACING),
            "group_margins": {
                title: list(margins) for title, margins in GROUP_FORM_MARGINS.items()
            },
            "no_horizontal_bar": list(HORIZONTAL_BAR_OFF_TABS),
        },
        "buttons": {
            "cancel": CANCEL_BUTTON_TEXT,
            "save": SAVE_BUTTON_TEXT,
            "save_style": SAVE_BUTTON_STYLE,
            "remove": REMOVE_BUTTON_TEXT,
            "test": TEST_BUTTON_TEXT,
            "add": ADD_BUTTON_TEXT,
            "ai_test": AI_TEST_BUTTON_TEXT,
            "ai_test_style": AI_TEST_BUTTON_STYLE,
        },
        "headings": {
            "ta": TA_HEADING,
            "phantom": PHANTOM_HEADING,
            "theme": THEME_HEADING,
            "accent": ACCENT_HEADING,
            "sound_events": SOUND_EVENTS_HEADING,
            "volume": VOLUME_HEADING,
            "sms_gateway": SMS_GATEWAY_HEADING,
            "sms_gateway_style": SMS_GATEWAY_HEADING_STYLE,
            "ai_info": AI_INFO_TEXT,
            "ai_info_style": AI_INFO_STYLE,
        },
        "banner": banner_of(model.wing),
        "button_names": [[words, name] for words, name in BUTTON_NAMES_BY_TEXT.items()],
        "text_rows": [list(one) for one in TEXT_ROWS],
        "connect_order": [list(one) for one in connect_order()],
        "listed_exchanges": list(model.listed_exchanges),
        "calls": [list(one) for one in model.calls],
        "call_names": sorted(
            {
                "build",
                "load_current",
                "load_skipped",
                "on_exchange_changed",
                "show_passphrase",
                "set_feedback",
                "test_api_connection",
                "add_exchange",
                "remove_exchange",
                "update_volume_label",
                "sfx_volume_changed",
                "sfx_volume_failed",
                "push_sound_config",
                "test_sound",
                "test_ai_handshake",
                "save",
                "cancel",
            }
        ),
        "actions": actions(),
        "connections": connection_counts(),
        "message_boxes": [list(one) for one in model.message_boxes],
        "prints": list(model.prints),
        "emitted": list(model.emitted),
        "processed_events": list(model.processed_events),
        "accepted": model.accepted,
        "rejected": model.rejected,
        "bus": {"subscribes": list(BUS_SUBSCRIBES), "emits": list(BUS_EMITS)},
        "timers": {"built": list(TIMERS_BUILT), "started": list(TIMERS_STARTED)},
        "threads": {"built": list(THREADS_BUILT), "started": list(THREADS_STARTED)},
    }


def view_model(params: dict) -> dict:
    """Build the dialog from `params` and return what it paints.

    ``params`` may carry ``wing``, ``settings`` (a mapping of stored
    values) and ``exchanges`` (a list of stored exchange entries).
    """
    params = params or {}
    model = SettingsDialogModel(
        settings=SettingsSource(
            params.get("settings") or {}, params.get("exchanges") or []
        ),
        status_log=StatusLogSink(),
        wing=params.get("wing", DEFAULT_WING),
    )
    model.build()
    return build_view_model(model)
