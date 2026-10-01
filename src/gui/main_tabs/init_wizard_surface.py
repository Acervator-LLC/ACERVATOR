"""init_wizard_surface.py -- the three setup pages the first run shows.

Describes the wizard the application opens on a first run and on a
version upgrade. Page one asks for a display name and offers a button
that skips the whole setup. Page two lists the fifteen venues the
connector supports and marks the three that need a passphrase. Page
three takes an API key, an API secret and a passphrase, hides them
behind a show-credentials switch, and tests them against the venue.

Eighteen widgets are named in ``WIDGET_NAMES``, and every piece of
wording the wizard paints is held in a table keyed by that name:
``LABEL_TEXTS``, ``PLACEHOLDERS``, ``TOOL_TIPS``, ``CHECK_TEXTS`` and
``BUTTON_TEXTS``.

``InitWizardModel`` holds every field the three pages carry.
``on_skip`` records the refusal the Skip Setup button makes.
``toggle_visibility`` switches the three secret fields between hidden
and shown. ``on_page_changed`` shows or hides the passphrase row for
the selected venue and clears the status line. ``test_api`` runs one
credential test through a validator handed to it and writes the status
line on each of its five paths. ``validate_current_page`` refuses to
leave page one with an empty name. ``get_results`` returns the six
values the caller collects.

The validator is a parameter, so nothing here opens a connection. No
credential is read from disk and none is written; the three secret
fields are held as text for the length of one call.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``init_wizard.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.init_wizard`` or from ``src.gui.design_system``, and nothing
compares the two copies. The venue list and the passphrase set are not
written out and so cannot drift: ``exchange_ids`` and
``passphrase_exchange_ids`` read ``src.exchange.ccxt_connector``. Nothing
here imports Qt.
"""

from __future__ import annotations

import math
from typing import Any, Optional

METHOD = "init_wizard.state"

LOGGER_NAME = "acervator.gui"

WINDOW_TITLE = "Acervator - Setup"
MINIMUM_SIZE_PX = (600, 450)
WIZARD_STYLE = "ModernStyle"
WIZARD_STYLE_VALUE = 1

WELCOME = "welcome"
EXCHANGE = "exchange"
CREDENTIALS = "credentials"
PAGES = (WELCOME, EXCHANGE, CREDENTIALS)
PAGE_IDS = {WELCOME: 0, EXCHANGE: 1, CREDENTIALS: 2}
FINAL_PAGE = CREDENTIALS
NO_PAGE_ID = -1
VALIDATED_PAGE_ID = 0
PASSPHRASE_PAGE_ID = 2

FRESH_TITLE = "Welcome to Acervator"
FRESH_SUBTITLE = "Set up your trading environment. You can skip this entirely."
UPGRADE_TITLE = "Acervator - New Version"
UPGRADE_SUBTITLE = (
    "A new version has been detected. You can reconfigure "
    "your setup or skip to keep existing settings."
)
EXCHANGE_TITLE = "Select Your Exchange"
EXCHANGE_SUBTITLE = "Choose your primary exchange. You can add more later in Settings."
CREDENTIALS_TITLE = "API Credentials"
CREDENTIALS_SUBTITLE = "Enter your API key and secret, or check Skip to add them later."

WIDGET_NAMES = (
    "username_label",
    "username",
    "fresh_start",
    "welcome_spacing",
    "skip_button",
    "exchange_label",
    "exchange_combo",
    "api_key_label",
    "api_key",
    "show_key",
    "api_secret_label",
    "api_secret",
    "passphrase_label",
    "passphrase",
    "passphrase_hint",
    "skip_creds",
    "test_button",
    "feedback",
)
(
    USERNAME_LABEL,
    USERNAME,
    FRESH_START,
    WELCOME_SPACING,
    SKIP_BUTTON,
    EXCHANGE_LABEL,
    EXCHANGE_COMBO,
    API_KEY_LABEL,
    API_KEY,
    SHOW_KEY,
    API_SECRET_LABEL,
    API_SECRET,
    PASSPHRASE_LABEL,
    PASSPHRASE,
    PASSPHRASE_HINT,
    SKIP_CREDS,
    TEST_BUTTON,
    FEEDBACK,
) = WIDGET_NAMES

EMPTY_TEXT = ""

LABEL_TEXTS = {
    USERNAME_LABEL: "Username:",
    EXCHANGE_LABEL: "Exchange:",
    API_KEY_LABEL: "API Key:",
    API_SECRET_LABEL: "API Secret:",
    PASSPHRASE_LABEL: "API Passphrase:",
    PASSPHRASE_HINT: "This exchange requires an API passphrase.",
    FEEDBACK: EMPTY_TEXT,
}
PLACEHOLDERS = {
    USERNAME: "Enter your display name",
    API_KEY: "API key or organizations/.../apiKeys/... (CDP)",
    API_SECRET: "API secret or EC private key (PEM with \\n is OK)",
    PASSPHRASE: "Passphrase you chose when creating the API key",
}
TOOL_TIPS = {
    FRESH_START: (
        "Check this to remove all saved exchanges, credentials, and settings "
        "from the previous version. Useful if you're seeing stale data."
    ),
    SKIP_BUTTON: ("Skip the setup wizard entirely. No exchanges will be configured."),
    API_SECRET: (
        "For Coinbase CDP keys, paste the full PEM key.\n"
        "Literal \\n characters will be auto-converted."
    ),
}
CHECK_TEXTS = {
    FRESH_START: "Start fresh (clear all previous settings and exchanges)",
    SHOW_KEY: "Show credentials",
    SKIP_CREDS: "Skip - add credentials later in Settings",
}
BUTTON_TEXTS = {
    SKIP_BUTTON: "Skip Setup",
    TEST_BUTTON: "Test Connection",
}

USERNAME_DEFAULT = "User"
WELCOME_SPACING_PX = 20
API_SECRET_MAX_HEIGHT_PX = 60

SKIP_BUTTON_COLOR = "#888"
FEEDBACK_ERROR_COLOR = "#ff3366"
FEEDBACK_INFO_COLOR = "#00aaff"
FEEDBACK_SUCCESS_COLOR = "#00ff88"

SKIN = {
    "skip_button": SKIP_BUTTON_COLOR,
    "feedback_error": FEEDBACK_ERROR_COLOR,
    "feedback_info": FEEDBACK_INFO_COLOR,
    "feedback_success": FEEDBACK_SUCCESS_COLOR,
}

SKIP_BUTTON_STYLE_FORMAT = "color: {color}; padding: 8px;"
FEEDBACK_STYLE_FORMAT = "color: {color};"
NO_STYLE = EMPTY_TEXT

STYLES = {
    "skip_button": SKIP_BUTTON_STYLE_FORMAT.format(color=SKIP_BUTTON_COLOR),
    "hidden_field": "color: transparent; background-selection-color: transparent;",
    "shown_field": NO_STYLE,
}
SKIP_BUTTON_STYLE = STYLES["skip_button"]
SECRET_HIDDEN_STYLE = STYLES["hidden_field"]
SECRET_SHOWN_STYLE = STYLES["shown_field"]

ECHO_MODES = ("Normal", "Password")
ECHO_NORMAL, ECHO_PASSWORD = ECHO_MODES
ECHO_VALUES = {ECHO_NORMAL: 0, ECHO_PASSWORD: 2}

PASSPHRASE_HINT_WORD_WRAP = True
FEEDBACK_WORD_WRAP = True
MUTED_PROPERTY = "muted"
MUTED_VALUE = True

EXCHANGE_NOTES = {"suffix": " (requires passphrase)"}
PASSPHRASE_SUFFIX = EXCHANGE_NOTES["suffix"]
DEFAULT_EXCHANGE_INDEX = 0
NO_EXCHANGE_INDEX = -1
NO_EXCHANGE_ID = None
NO_EXCHANGE_LABEL = EMPTY_TEXT

MISSING_CREDENTIALS_TEXT = "Enter API key and secret first."
TESTING_FORMAT = "Testing connection to {exchange}..."
TEST_FAILED_FORMAT = "Test failed: {error}"

USERNAME_REQUIRED_TITLE = "Username Required"
USERNAME_REQUIRED_TEXT = "Please enter a username."
NO_WARNING = None

SAFE_EVENTS_REASON = "legacy processEvents site"

SKIPPED_DEFAULT = False
FRESH_START_ABSENT = None
FRESH_START_DEFAULT = False
SHOW_KEY_DEFAULT = False
SKIP_CREDS_DEFAULT = False
TEST_BUTTON_ENABLED = True
PASSPHRASE_VISIBLE_DEFAULT = True

INT32_MIN = -2147483648
INT32_MAX = 2147483647

WRONG_TEXT_TYPE = "a text field takes text, not {kind}"
WRONG_CHECK_TYPE = "a check box takes a whole number, not {kind}"
WRONG_INDEX_TYPE = "a list position takes a number, not {kind}"
INDEX_OVERFLOW = "a list position must fit a 32-bit whole number"

ACTIONS = {
    "skip_button.clicked": "on_skip",
    "show_key.toggled": "toggle_visibility",
    "test_button.clicked": "test_api",
    "wizard.currentIdChanged": "on_page_changed",
}

TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()

WIZARD_SET_WINDOW_TITLE = "wizard.setWindowTitle"
WIZARD_SET_MINIMUM_SIZE = "wizard.setMinimumSize"
WIZARD_SET_WIZARD_STYLE = "wizard.setWizardStyle"
WIZARD_ADD_PAGE = "wizard.addPage"
WIZARD_REJECT = "wizard.reject"
PAGE_CREATE = "page.create"
PAGE_SET_TITLE = "page.setTitle"
PAGE_SET_SUB_TITLE = "page.setSubTitle"
PAGE_SET_FINAL = "page.setFinalPage"
LAYOUT_CREATE = "layout.create"
LAYOUT_ADD_WIDGET = "layout.addWidget"
LAYOUT_ADD_SPACING = "layout.addSpacing"
LABEL_CREATE = "label.create"
LABEL_SET_WORD_WRAP = "label.setWordWrap"
LABEL_SET_PROPERTY = "label.setProperty"
LABEL_SET_TEXT = "label.setText"
LABEL_SET_STYLE_SHEET = "label.setStyleSheet"
LABEL_SET_VISIBLE = "label.setVisible"
LINE_CREATE = "line.create"
LINE_SET_PLACEHOLDER = "line.setPlaceholderText"
LINE_SET_TEXT = "line.setText"
LINE_SET_ECHO_MODE = "line.setEchoMode"
LINE_SET_VISIBLE = "line.setVisible"
COMBO_CREATE = "combo.create"
COMBO_ADD_ITEM = "combo.addItem"
COMBO_SET_CURRENT_INDEX = "combo.setCurrentIndex"
CHECK_CREATE = "check.create"
CHECK_SET_TOOL_TIP = "check.setToolTip"
CHECK_SET_CHECKED = "check.setChecked"
TEXT_CREATE = "text.create"
TEXT_SET_MAXIMUM_HEIGHT = "text.setMaximumHeight"
TEXT_SET_PLACEHOLDER = "text.setPlaceholderText"
TEXT_SET_TOOL_TIP = "text.setToolTip"
TEXT_SET_PLAIN_TEXT = "text.setPlainText"
TEXT_SET_STYLE_SHEET = "text.setStyleSheet"
BUTTON_CREATE = "button.create"
BUTTON_SET_TOOL_TIP = "button.setToolTip"
BUTTON_SET_STYLE_SHEET = "button.setStyleSheet"
BUTTON_SET_ENABLED = "button.setEnabled"
SAFE_PROCESS_EVENTS = "wizard.safeProcessEvents"
VALIDATE_CALL = "wizard.validateCredentials"
MESSAGE_BOX_WARNING = "messageBox.warning"

LABEL_TAGS = (
    USERNAME_LABEL,
    EXCHANGE_LABEL,
    API_KEY_LABEL,
    API_SECRET_LABEL,
    PASSPHRASE_LABEL,
    PASSPHRASE_HINT,
    FEEDBACK,
)
LINE_TAGS = (USERNAME, API_KEY, PASSPHRASE)
CHECK_TAGS = (SHOW_KEY, SKIP_CREDS)
UPGRADE_CHECK_TAGS = (FRESH_START, SHOW_KEY, SKIP_CREDS)
BUTTON_TAGS = (SKIP_BUTTON, TEST_BUTTON)
TEXT_TAGS = (API_SECRET,)
COMBO_TAGS = (EXCHANGE_COMBO,)

WELCOME_ORDER = (USERNAME_LABEL, USERNAME, WELCOME_SPACING, SKIP_BUTTON)
UPGRADE_WELCOME_ORDER = (
    USERNAME_LABEL,
    USERNAME,
    FRESH_START,
    WELCOME_SPACING,
    SKIP_BUTTON,
)
EXCHANGE_ORDER = (EXCHANGE_LABEL, EXCHANGE_COMBO)
CREDENTIALS_ORDER = (
    API_KEY_LABEL,
    API_KEY,
    SHOW_KEY,
    API_SECRET_LABEL,
    API_SECRET,
    PASSPHRASE_LABEL,
    PASSPHRASE,
    PASSPHRASE_HINT,
    SKIP_CREDS,
    TEST_BUTTON,
    FEEDBACK,
)
PAGE_ORDERS = {
    WELCOME: WELCOME_ORDER,
    EXCHANGE: EXCHANGE_ORDER,
    CREDENTIALS: CREDENTIALS_ORDER,
}
UPGRADE_PAGE_ORDERS = {
    WELCOME: UPGRADE_WELCOME_ORDER,
    EXCHANGE: EXCHANGE_ORDER,
    CREDENTIALS: CREDENTIALS_ORDER,
}

PAGE_TITLES = {
    WELCOME: FRESH_TITLE,
    EXCHANGE: EXCHANGE_TITLE,
    CREDENTIALS: CREDENTIALS_TITLE,
}
UPGRADE_PAGE_TITLES = {
    WELCOME: UPGRADE_TITLE,
    EXCHANGE: EXCHANGE_TITLE,
    CREDENTIALS: CREDENTIALS_TITLE,
}
PAGE_SUBTITLES = {
    WELCOME: FRESH_SUBTITLE,
    EXCHANGE: EXCHANGE_SUBTITLE,
    CREDENTIALS: CREDENTIALS_SUBTITLE,
}
UPGRADE_PAGE_SUBTITLES = {
    WELCOME: UPGRADE_SUBTITLE,
    EXCHANGE: EXCHANGE_SUBTITLE,
    CREDENTIALS: CREDENTIALS_SUBTITLE,
}

STEP_NAMES = (
    "username",
    "api_key",
    "api_secret",
    "passphrase",
    "show_key",
    "skip_creds",
    "fresh_start",
    "exchange_index",
    "page_id",
    "skip",
    "test",
)

RESULT_FIELDS = (
    "username",
    "exchange_id",
    "api_key",
    "api_secret",
    "passphrase",
    "fresh_start",
)

TEST_PATH_MISSING = "missing_credentials"
TEST_PATH_NO_EXCHANGE = "no_exchange"
TEST_PATH_SUCCESS = "success"
TEST_PATH_REFUSED = "refused"
TEST_PATH_RAISED = "raised"
TEST_PATHS = (
    TEST_PATH_MISSING,
    TEST_PATH_NO_EXCHANGE,
    TEST_PATH_SUCCESS,
    TEST_PATH_REFUSED,
    TEST_PATH_RAISED,
)
NO_TEST_PATH = EMPTY_TEXT


def exchange_ids() -> tuple:
    """``SUPPORTED_EXCHANGES`` in id order, the venues page two lists.

    ``SUPPORTED_EXCHANGES`` is imported when first asked, so importing this
    file loads no exchange library and reads no settings.
    """
    from ...exchange.ccxt_connector import SUPPORTED_EXCHANGES

    return tuple(sorted(SUPPORTED_EXCHANGES.keys()))


def passphrase_exchange_ids() -> tuple:
    """``PASSPHRASE_EXCHANGES`` in id order, the venues ``exchange_label`` notes.

    ``PASSPHRASE_EXCHANGES`` is imported when first asked, so importing this
    file loads no exchange library and reads no settings.
    """
    from ...exchange.ccxt_connector import PASSPHRASE_EXCHANGES

    return tuple(sorted(PASSPHRASE_EXCHANGES))


def exchange_label(exchange_id: str) -> str:
    """One venue's list entry, with the passphrase note when it needs one."""
    label = exchange_id.capitalize()
    if exchange_id in passphrase_exchange_ids():
        label += PASSPHRASE_SUFFIX
    return label


def exchange_labels() -> tuple:
    """One ``exchange_label`` for every ``exchange_ids`` entry, in that order."""
    return tuple(exchange_label(found) for found in exchange_ids())


def exchange_items() -> tuple:
    """Every venue's list entry beside its id, the pairs page two draws."""
    return tuple(zip(exchange_labels(), exchange_ids(), strict=True))


def text_value(value: Any) -> str:
    """Give back the text a Qt text field keeps for `value`.

    Nothing becomes the empty string, text is kept as it is, and any
    other type is refused the way the field refuses it.
    """
    if value is None:
        return EMPTY_TEXT
    if isinstance(value, str):
        return value
    raise TypeError(WRONG_TEXT_TYPE.format(kind=type(value).__name__))


def checked_value(value: Any) -> bool:
    """Give back the state a Qt check box keeps for `value`.

    A whole number becomes on or off. Text, nothing and a fraction are
    refused the way the check box refuses them.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    raise TypeError(WRONG_CHECK_TYPE.format(kind=type(value).__name__))


def index_value(value: Any) -> int:
    """Give back the list position a Qt drop-down keeps for `value`.

    A fraction is cut towards zero. Text and nothing are refused, and a
    number outside a 32-bit whole number overflows, both as the drop-down
    does it.
    """
    if isinstance(value, int):
        number = int(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise OverflowError(INDEX_OVERFLOW)
        number = int(value)
    else:
        raise TypeError(WRONG_INDEX_TYPE.format(kind=type(value).__name__))
    if not INT32_MIN <= number <= INT32_MAX:
        raise OverflowError(INDEX_OVERFLOW)
    return number


def list_position(index: int) -> int:
    """The position a Qt drop-down settles on for `index`.

    A position outside the list leaves no entry selected, which the
    drop-down reports as -1 whatever number it was given.
    """
    if 0 <= index < len(exchange_ids()):
        return index
    return NO_EXCHANGE_INDEX


def selected_exchange(index: int) -> tuple:
    """Give back the venue id and list entry at `index`, nothing outside it."""
    offered = exchange_ids()
    if 0 <= index < len(offered):
        return offered[index], exchange_labels()[index]
    return NO_EXCHANGE_ID, NO_EXCHANGE_LABEL


def needs_passphrase(exchange_id: Any) -> bool:
    """Say whether the named venue asks for a passphrase as well as a key."""
    return exchange_id in passphrase_exchange_ids()


def page_titles(is_upgrade: Any) -> dict:
    """Give back the three page titles, in upgrade or first-run wording."""
    return dict(UPGRADE_PAGE_TITLES if is_upgrade else PAGE_TITLES)


def page_subtitles(is_upgrade: Any) -> dict:
    """Give back the three page subtitles, in upgrade or first-run wording."""
    return dict(UPGRADE_PAGE_SUBTITLES if is_upgrade else PAGE_SUBTITLES)


def page_orders(is_upgrade: Any) -> dict:
    """Give back each page's children in the order the layout takes them."""
    source = UPGRADE_PAGE_ORDERS if is_upgrade else PAGE_ORDERS
    return {name: list(order) for name, order in source.items()}


def feedback_style(color: str) -> str:
    """Give back the style the status line carries for one colour."""
    return FEEDBACK_STYLE_FORMAT.format(color=color)


class InitWizardModel:
    """Every field, button and status line the three setup pages carry.

    The build below follows the wizard it replaces call for call, and
    each call is appended to ``calls`` so a caller can replay the same
    sequence on pages it owns. No credential is read from disk and none
    is written; the validator ``test_api`` runs is handed in.
    """

    def __init__(self, is_upgrade: Any = False) -> None:
        """Lay out the three pages, in upgrade or first-run wording."""
        self.calls: list[list] = []
        self.is_upgrade = is_upgrade
        self.skipped = SKIPPED_DEFAULT
        self.current_page_id: Any = NO_PAGE_ID
        self.warning: Optional[list] = NO_WARNING
        self.test_path = NO_TEST_PATH
        self.username_text = USERNAME_DEFAULT
        self.api_key_text = EMPTY_TEXT
        self.api_secret_text = EMPTY_TEXT
        self.passphrase_text = EMPTY_TEXT
        self.api_key_echo = ECHO_PASSWORD
        self.passphrase_echo = ECHO_PASSWORD
        self.api_secret_style = NO_STYLE
        self.show_key_checked = SHOW_KEY_DEFAULT
        self.skip_creds_checked = SKIP_CREDS_DEFAULT
        self.fresh_start_checked: Optional[bool] = FRESH_START_ABSENT
        self.exchange_index = DEFAULT_EXCHANGE_INDEX
        self.exchange_id, self.exchange_label_text = selected_exchange(
            DEFAULT_EXCHANGE_INDEX
        )
        self.passphrase_label_visible = PASSPHRASE_VISIBLE_DEFAULT
        self.passphrase_visible = PASSPHRASE_VISIBLE_DEFAULT
        self.passphrase_hint_visible = PASSPHRASE_VISIBLE_DEFAULT
        self.feedback_text = EMPTY_TEXT
        self.feedback_style = NO_STYLE
        self.test_button_enabled = TEST_BUTTON_ENABLED
        self._build_welcome_page()
        self._build_exchange_page()
        self._build_credentials_page()
        for name in PAGES:
            self.calls.append([WIZARD_ADD_PAGE, name, PAGE_IDS[name]])

    def _build_welcome_page(self) -> None:
        """Record the calls that lay out page one: the name and the skip."""
        self.calls.append([WIZARD_SET_WINDOW_TITLE, WINDOW_TITLE])
        self.calls.append([WIZARD_SET_MINIMUM_SIZE, list(MINIMUM_SIZE_PX)])
        self.calls.append([WIZARD_SET_WIZARD_STYLE, WIZARD_STYLE_VALUE])
        upgrade = bool(self.is_upgrade)
        self.calls.append([PAGE_CREATE, WELCOME])
        self.calls.append(
            [PAGE_SET_TITLE, WELCOME, UPGRADE_TITLE if upgrade else FRESH_TITLE]
        )
        self.calls.append(
            [
                PAGE_SET_SUB_TITLE,
                WELCOME,
                UPGRADE_SUBTITLE if upgrade else FRESH_SUBTITLE,
            ]
        )
        self.calls.append([LAYOUT_CREATE, WELCOME])
        self.calls.append([LABEL_CREATE, USERNAME_LABEL, LABEL_TEXTS[USERNAME_LABEL]])
        self.calls.append([LAYOUT_ADD_WIDGET, WELCOME, USERNAME_LABEL])
        self.calls.append([LINE_CREATE, USERNAME, EMPTY_TEXT])
        self.calls.append([LINE_SET_PLACEHOLDER, USERNAME, PLACEHOLDERS[USERNAME]])
        self.calls.append([LINE_SET_TEXT, USERNAME, USERNAME_DEFAULT])
        self.calls.append([LAYOUT_ADD_WIDGET, WELCOME, USERNAME])
        if upgrade:
            self.fresh_start_checked = FRESH_START_DEFAULT
            self.calls.append([CHECK_CREATE, FRESH_START, CHECK_TEXTS[FRESH_START]])
            self.calls.append([CHECK_SET_TOOL_TIP, FRESH_START, TOOL_TIPS[FRESH_START]])
            self.calls.append([LAYOUT_ADD_WIDGET, WELCOME, FRESH_START])
        self.calls.append([LAYOUT_ADD_SPACING, WELCOME, WELCOME_SPACING_PX])
        self.calls.append([BUTTON_CREATE, SKIP_BUTTON, BUTTON_TEXTS[SKIP_BUTTON]])
        self.calls.append([BUTTON_SET_TOOL_TIP, SKIP_BUTTON, TOOL_TIPS[SKIP_BUTTON]])
        self.calls.append([BUTTON_SET_STYLE_SHEET, SKIP_BUTTON, SKIP_BUTTON_STYLE])
        self.calls.append([LAYOUT_ADD_WIDGET, WELCOME, SKIP_BUTTON])

    def _build_exchange_page(self) -> None:
        """Record the calls that lay out page two: the venue list."""
        self.calls.append([PAGE_CREATE, EXCHANGE])
        self.calls.append([PAGE_SET_TITLE, EXCHANGE, EXCHANGE_TITLE])
        self.calls.append([PAGE_SET_SUB_TITLE, EXCHANGE, EXCHANGE_SUBTITLE])
        self.calls.append([LAYOUT_CREATE, EXCHANGE])
        self.calls.append([LABEL_CREATE, EXCHANGE_LABEL, LABEL_TEXTS[EXCHANGE_LABEL]])
        self.calls.append([LAYOUT_ADD_WIDGET, EXCHANGE, EXCHANGE_LABEL])
        self.calls.append([COMBO_CREATE, EXCHANGE_COMBO])
        for label, found in exchange_items():
            self.calls.append([COMBO_ADD_ITEM, EXCHANGE_COMBO, label, found])
        self.calls.append([LAYOUT_ADD_WIDGET, EXCHANGE, EXCHANGE_COMBO])

    def _build_credentials_page(self) -> None:
        """Record the calls that lay out page three: the key, secret and test."""
        self.calls.append([PAGE_CREATE, CREDENTIALS])
        self.calls.append([PAGE_SET_TITLE, CREDENTIALS, CREDENTIALS_TITLE])
        self.calls.append([PAGE_SET_SUB_TITLE, CREDENTIALS, CREDENTIALS_SUBTITLE])
        self.calls.append([PAGE_SET_FINAL, CREDENTIALS, True])
        self.calls.append([LAYOUT_CREATE, CREDENTIALS])
        self.calls.append([LABEL_CREATE, API_KEY_LABEL, LABEL_TEXTS[API_KEY_LABEL]])
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, API_KEY_LABEL])
        self.calls.append([LINE_CREATE, API_KEY, EMPTY_TEXT])
        self.calls.append([LINE_SET_PLACEHOLDER, API_KEY, PLACEHOLDERS[API_KEY]])
        self.calls.append([LINE_SET_ECHO_MODE, API_KEY, ECHO_VALUES[ECHO_PASSWORD]])
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, API_KEY])
        self.calls.append([CHECK_CREATE, SHOW_KEY, CHECK_TEXTS[SHOW_KEY]])
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, SHOW_KEY])
        self.calls.append(
            [LABEL_CREATE, API_SECRET_LABEL, LABEL_TEXTS[API_SECRET_LABEL]]
        )
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, API_SECRET_LABEL])
        self.calls.append([TEXT_CREATE, API_SECRET, EMPTY_TEXT])
        self.calls.append(
            [TEXT_SET_MAXIMUM_HEIGHT, API_SECRET, API_SECRET_MAX_HEIGHT_PX]
        )
        self.calls.append([TEXT_SET_PLACEHOLDER, API_SECRET, PLACEHOLDERS[API_SECRET]])
        self.calls.append([TEXT_SET_TOOL_TIP, API_SECRET, TOOL_TIPS[API_SECRET]])
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, API_SECRET])
        self.calls.append(
            [LABEL_CREATE, PASSPHRASE_LABEL, LABEL_TEXTS[PASSPHRASE_LABEL]]
        )
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, PASSPHRASE_LABEL])
        self.calls.append([LINE_CREATE, PASSPHRASE, EMPTY_TEXT])
        self.calls.append([LINE_SET_PLACEHOLDER, PASSPHRASE, PLACEHOLDERS[PASSPHRASE]])
        self.calls.append([LINE_SET_ECHO_MODE, PASSPHRASE, ECHO_VALUES[ECHO_PASSWORD]])
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, PASSPHRASE])
        self.calls.append([LABEL_CREATE, PASSPHRASE_HINT, LABEL_TEXTS[PASSPHRASE_HINT]])
        self.calls.append(
            [LABEL_SET_WORD_WRAP, PASSPHRASE_HINT, PASSPHRASE_HINT_WORD_WRAP]
        )
        self.calls.append(
            [LABEL_SET_PROPERTY, PASSPHRASE_HINT, MUTED_PROPERTY, MUTED_VALUE]
        )
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, PASSPHRASE_HINT])
        self.calls.append([CHECK_CREATE, SKIP_CREDS, CHECK_TEXTS[SKIP_CREDS]])
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, SKIP_CREDS])
        self.calls.append([BUTTON_CREATE, TEST_BUTTON, BUTTON_TEXTS[TEST_BUTTON]])
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, TEST_BUTTON])
        self.calls.append([LABEL_CREATE, FEEDBACK, LABEL_TEXTS[FEEDBACK]])
        self.calls.append([LABEL_SET_WORD_WRAP, FEEDBACK, FEEDBACK_WORD_WRAP])
        self.calls.append([LAYOUT_ADD_WIDGET, CREDENTIALS, FEEDBACK])

    def set_username(self, value: Any) -> None:
        """Type a display name into the page-one field."""
        self.username_text = text_value(value)
        self.calls.append([LINE_SET_TEXT, USERNAME, self.username_text])

    def set_api_key(self, value: Any) -> None:
        """Type an API key into the page-three field."""
        self.api_key_text = text_value(value)
        self.calls.append([LINE_SET_TEXT, API_KEY, self.api_key_text])

    def set_api_secret(self, value: Any) -> None:
        """Type an API secret into the page-three box."""
        self.api_secret_text = text_value(value)
        self.calls.append([TEXT_SET_PLAIN_TEXT, API_SECRET, self.api_secret_text])

    def set_passphrase(self, value: Any) -> None:
        """Type an API passphrase into the page-three field."""
        self.passphrase_text = text_value(value)
        self.calls.append([LINE_SET_TEXT, PASSPHRASE, self.passphrase_text])

    def set_show_key(self, value: Any) -> None:
        """Tick or clear the show-credentials switch, and follow it.

        A set to the state the switch already holds changes nothing, as
        the switch it replaces reports only a change.
        """
        wanted = checked_value(value)
        changed = wanted != self.show_key_checked
        self.show_key_checked = wanted
        if changed:
            self.toggle_visibility(wanted)
        self.calls.append([CHECK_SET_CHECKED, SHOW_KEY, wanted])

    def set_skip_creds(self, value: Any) -> None:
        """Tick or clear the add-credentials-later switch."""
        self.skip_creds_checked = checked_value(value)
        self.calls.append([CHECK_SET_CHECKED, SKIP_CREDS, self.skip_creds_checked])

    def set_fresh_start(self, value: Any) -> None:
        """Tick or clear the start-fresh switch; it is absent on a first run."""
        if self.fresh_start_checked is FRESH_START_ABSENT:
            raise AttributeError(FRESH_START)
        self.fresh_start_checked = checked_value(value)
        self.calls.append([CHECK_SET_CHECKED, FRESH_START, self.fresh_start_checked])

    def set_exchange_index(self, value: Any) -> None:
        """Pick one venue by its position in the page-two list."""
        self.exchange_index = list_position(index_value(value))
        self.exchange_id, self.exchange_label_text = selected_exchange(
            self.exchange_index
        )
        self.calls.append(
            [COMBO_SET_CURRENT_INDEX, EXCHANGE_COMBO, self.exchange_index]
        )

    def on_skip(self) -> None:
        """Skip the whole setup: record the refusal and close the wizard."""
        self.skipped = True
        self.calls.append([WIZARD_REJECT])

    def was_skipped(self) -> bool:
        """Say whether the Skip Setup button was pressed."""
        return self.skipped

    def toggle_visibility(self, show: Any) -> None:
        """Show or hide the key, the secret and the passphrase."""
        mode = ECHO_NORMAL if show else ECHO_PASSWORD
        self.api_key_echo = mode
        self.calls.append([LINE_SET_ECHO_MODE, API_KEY, ECHO_VALUES[mode]])
        self.passphrase_echo = mode
        self.calls.append([LINE_SET_ECHO_MODE, PASSPHRASE, ECHO_VALUES[mode]])
        self.api_secret_style = SECRET_SHOWN_STYLE if show else SECRET_HIDDEN_STYLE
        self.calls.append([TEXT_SET_STYLE_SHEET, API_SECRET, self.api_secret_style])

    def on_page_changed(self, page_id: Any) -> None:
        """Enter one page: show the passphrase row it needs, clear the status."""
        self.current_page_id = page_id
        if page_id == PASSPHRASE_PAGE_ID:
            wanted = needs_passphrase(self.exchange_id)
            self.passphrase_label_visible = wanted
            self.calls.append([LABEL_SET_VISIBLE, PASSPHRASE_LABEL, wanted])
            self.passphrase_visible = wanted
            self.calls.append([LINE_SET_VISIBLE, PASSPHRASE, wanted])
            self.passphrase_hint_visible = wanted
            self.calls.append([LABEL_SET_VISIBLE, PASSPHRASE_HINT, wanted])
            self.feedback_text = EMPTY_TEXT
            self.calls.append([LABEL_SET_TEXT, FEEDBACK, EMPTY_TEXT])

    def _write_feedback(self, text: str, color: str) -> None:
        """Put one line of status text on page three, in one colour."""
        self.feedback_text = text
        self.calls.append([LABEL_SET_TEXT, FEEDBACK, text])
        self.feedback_style = feedback_style(color)
        self.calls.append([LABEL_SET_STYLE_SHEET, FEEDBACK, self.feedback_style])

    def _enable_test_button(self, enabled: bool) -> None:
        """Turn the Test Connection button on or off."""
        self.test_button_enabled = enabled
        self.calls.append([BUTTON_SET_ENABLED, TEST_BUTTON, enabled])

    def test_api(self, validate: Any) -> None:
        """Test the typed credentials against the selected venue.

        ``validate`` takes the venue id, key, secret and passphrase and
        gives back an answer carrying ``success`` and ``message``, or
        raises. Nothing here opens a connection of its own.
        """
        exchange_id = self.exchange_id
        key = self.api_key_text.strip()
        secret = self.api_secret_text.strip()
        passphrase = self.passphrase_text.strip()

        if not key or not secret:
            self.test_path = TEST_PATH_MISSING
            self._write_feedback(MISSING_CREDENTIALS_TEXT, FEEDBACK_ERROR_COLOR)
            return

        if exchange_id is NO_EXCHANGE_ID:
            self.test_path = TEST_PATH_NO_EXCHANGE
        named = exchange_id.capitalize()
        self._write_feedback(TESTING_FORMAT.format(exchange=named), FEEDBACK_INFO_COLOR)
        self._enable_test_button(False)
        self.calls.append([SAFE_PROCESS_EVENTS, SAFE_EVENTS_REASON])

        try:
            self.calls.append([VALIDATE_CALL, exchange_id])
            answer = validate(exchange_id, key, secret, passphrase)
            if answer.success:
                self.test_path = TEST_PATH_SUCCESS
                self._write_feedback(answer.message, FEEDBACK_SUCCESS_COLOR)
            else:
                self.test_path = TEST_PATH_REFUSED
                self._write_feedback(answer.message, FEEDBACK_ERROR_COLOR)
        except Exception as exc:
            self.test_path = TEST_PATH_RAISED
            self._write_feedback(
                TEST_FAILED_FORMAT.format(error=exc), FEEDBACK_ERROR_COLOR
            )
        finally:
            self._enable_test_button(True)

    def validate_current_page(self) -> bool:
        """Refuse to leave page one while the display name is empty."""
        if self.current_page_id == VALIDATED_PAGE_ID:
            name = self.username_text.strip()
            if not name:
                self.warning = [USERNAME_REQUIRED_TITLE, USERNAME_REQUIRED_TEXT]
                self.calls.append(
                    [
                        MESSAGE_BOX_WARNING,
                        USERNAME_REQUIRED_TITLE,
                        USERNAME_REQUIRED_TEXT,
                    ]
                )
                return False
        return True

    def get_results(self) -> dict:
        """Give back the six values the caller collects when the wizard ends."""
        skip = self.skip_creds_checked
        return {
            "username": self.username_text.strip() or USERNAME_DEFAULT,
            "exchange_id": self.exchange_id,
            "api_key": EMPTY_TEXT if skip else self.api_key_text.strip(),
            "api_secret": EMPTY_TEXT if skip else self.api_secret_text.strip(),
            "passphrase": EMPTY_TEXT if skip else self.passphrase_text.strip(),
            "fresh_start": (
                self.fresh_start_checked
                if self.fresh_start_checked is not FRESH_START_ABSENT
                else FRESH_START_DEFAULT
            ),
        }


class TestAnswer:
    """One credential-test answer: whether it worked, and the line to show.

    ``test_api`` reads ``success`` and ``message``. The bridge builds one
    of these from the request rather than opening a connection.
    """

    def __init__(self, success: bool, message: str) -> None:
        """Hold one answer's verdict and the line the status shows."""
        self.success = success
        self.message = message


def canned_validator(answer: dict) -> Any:
    """Give back a validator that answers, or raises, from the request.

    An ``error`` entry raises; anything else answers with ``success`` and
    ``message``. Nothing here reaches a venue.
    """
    error = answer.get("error")
    success = bool(answer.get("success", False))
    message = str(answer.get("message", EMPTY_TEXT))

    def validate(
        _exchange_id: Any, _api_key: Any, _api_secret: Any, _passphrase: Any
    ) -> TestAnswer:
        """Answer one credential test from the canned values above."""
        if error:
            raise RuntimeError(error)
        return TestAnswer(success, message)

    return validate


def drive_model(model: InitWizardModel, steps: dict) -> InitWizardModel:
    """Run one set of steps over `model`, in the order a person works.

    The fields, then the switches, then the venue, then the page change,
    then the credential test, then the Skip Setup button. A step whose
    value is ``None`` is not taken.
    """
    if steps.get("username") is not None:
        model.set_username(steps["username"])
    if steps.get("api_key") is not None:
        model.set_api_key(steps["api_key"])
    if steps.get("api_secret") is not None:
        model.set_api_secret(steps["api_secret"])
    if steps.get("passphrase") is not None:
        model.set_passphrase(steps["passphrase"])
    if steps.get("fresh_start") is not None and bool(model.is_upgrade):
        model.set_fresh_start(steps["fresh_start"])
    if steps.get("skip_creds") is not None:
        model.set_skip_creds(steps["skip_creds"])
    if steps.get("show_key") is not None:
        model.set_show_key(steps["show_key"])
    if steps.get("exchange_index") is not None:
        model.set_exchange_index(steps["exchange_index"])
    if steps.get("page_id") is not None:
        model.on_page_changed(steps["page_id"])
    if steps.get("test") is not None:
        model.test_api(canned_validator(steps["test"]))
    if steps.get("skip"):
        model.on_skip()
    return model


def build_view_model(is_upgrade: Any = False, steps: Optional[dict] = None) -> dict:
    """Give back the whole wizard state as one serialisable dict.

    ``steps`` names the fields typed, the switches ticked, the venue
    picked, the page entered, the canned test answer and the skip.
    """
    upgrade = bool(is_upgrade)
    model = drive_model(InitWizardModel(upgrade), dict(steps or {}))
    return {
        "method": METHOD,
        "window_title": WINDOW_TITLE,
        "minimum_size_px": list(MINIMUM_SIZE_PX),
        "wizard_style": WIZARD_STYLE,
        "wizard_style_value": WIZARD_STYLE_VALUE,
        "pages": list(PAGES),
        "page_ids": dict(PAGE_IDS),
        "final_page": FINAL_PAGE,
        "page_titles": page_titles(upgrade),
        "page_subtitles": page_subtitles(upgrade),
        "page_orders": page_orders(upgrade),
        "widget_names": list(WIDGET_NAMES),
        "label_texts": dict(LABEL_TEXTS),
        "placeholders": dict(PLACEHOLDERS),
        "tool_tips": dict(TOOL_TIPS),
        "check_texts": dict(CHECK_TEXTS),
        "button_texts": dict(BUTTON_TEXTS),
        "styles": dict(STYLES),
        "buttons": {
            SKIP_BUTTON: {
                "text": BUTTON_TEXTS[SKIP_BUTTON],
                "tool_tip": TOOL_TIPS[SKIP_BUTTON],
                "style_sheet": SKIP_BUTTON_STYLE,
                "enabled": True,
            },
            TEST_BUTTON: {
                "text": BUTTON_TEXTS[TEST_BUTTON],
                "tool_tip": EMPTY_TEXT,
                "style_sheet": NO_STYLE,
                "enabled": model.test_button_enabled,
            },
        },
        "exchange_ids": list(exchange_ids()),
        "exchange_labels": list(exchange_labels()),
        "exchange_items": [list(item) for item in exchange_items()],
        "exchange_notes": dict(EXCHANGE_NOTES),
        "passphrase_exchange_ids": list(passphrase_exchange_ids()),
        "passphrase_suffix": PASSPHRASE_SUFFIX,
        "default_exchange_index": DEFAULT_EXCHANGE_INDEX,
        "no_exchange_index": NO_EXCHANGE_INDEX,
        "no_exchange_id": NO_EXCHANGE_ID,
        "no_exchange_label": NO_EXCHANGE_LABEL,
        "is_upgrade": upgrade,
        "skipped": model.skipped,
        "skipped_default": SKIPPED_DEFAULT,
        "current_page_id": model.current_page_id,
        "no_page_id": NO_PAGE_ID,
        "validated_page_id": VALIDATED_PAGE_ID,
        "passphrase_page_id": PASSPHRASE_PAGE_ID,
        "username_text": model.username_text,
        "username_default": USERNAME_DEFAULT,
        "api_key_text": model.api_key_text,
        "api_secret_text": model.api_secret_text,
        "passphrase_text": model.passphrase_text,
        "api_key_echo": model.api_key_echo,
        "passphrase_echo": model.passphrase_echo,
        "echo_modes": list(ECHO_MODES),
        "echo_values": dict(ECHO_VALUES),
        "api_secret_style": model.api_secret_style,
        "api_secret_max_height_px": API_SECRET_MAX_HEIGHT_PX,
        "secret_hidden_style": SECRET_HIDDEN_STYLE,
        "secret_shown_style": SECRET_SHOWN_STYLE,
        "no_style": NO_STYLE,
        "show_key_checked": model.show_key_checked,
        "show_key_default": SHOW_KEY_DEFAULT,
        "skip_creds_checked": model.skip_creds_checked,
        "skip_creds_default": SKIP_CREDS_DEFAULT,
        "fresh_start_checked": model.fresh_start_checked,
        "fresh_start_absent": FRESH_START_ABSENT,
        "fresh_start_default": FRESH_START_DEFAULT,
        "exchange_index": model.exchange_index,
        "exchange_id": model.exchange_id,
        "exchange_label_text": model.exchange_label_text,
        "passphrase_label_visible": model.passphrase_label_visible,
        "passphrase_visible": model.passphrase_visible,
        "passphrase_hint_visible": model.passphrase_hint_visible,
        "passphrase_visible_default": PASSPHRASE_VISIBLE_DEFAULT,
        "feedback_text": model.feedback_text,
        "feedback_style": model.feedback_style,
        "feedback_word_wrap": FEEDBACK_WORD_WRAP,
        "passphrase_hint_word_wrap": PASSPHRASE_HINT_WORD_WRAP,
        "muted_property": [MUTED_PROPERTY, MUTED_VALUE],
        "welcome_spacing_px": WELCOME_SPACING_PX,
        "test_button_enabled": model.test_button_enabled,
        "test_button_enabled_default": TEST_BUTTON_ENABLED,
        "test_path": model.test_path,
        "test_paths": list(TEST_PATHS),
        "no_test_path": NO_TEST_PATH,
        "missing_credentials_text": MISSING_CREDENTIALS_TEXT,
        "testing_format": TESTING_FORMAT,
        "test_failed_format": TEST_FAILED_FORMAT,
        "skip_button_style_format": SKIP_BUTTON_STYLE_FORMAT,
        "feedback_style_format": FEEDBACK_STYLE_FORMAT,
        "skip_button_style": SKIP_BUTTON_STYLE,
        "skin": dict(SKIN),
        "skip_button_color": SKIP_BUTTON_COLOR,
        "feedback_error_color": FEEDBACK_ERROR_COLOR,
        "feedback_info_color": FEEDBACK_INFO_COLOR,
        "feedback_success_color": FEEDBACK_SUCCESS_COLOR,
        "warning": model.warning,
        "no_warning": NO_WARNING,
        "username_required": [USERNAME_REQUIRED_TITLE, USERNAME_REQUIRED_TEXT],
        "validated": model.validate_current_page(),
        "results": model.get_results(),
        "result_fields": list(RESULT_FIELDS),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "safe_events_reason": SAFE_EVENTS_REASON,
        "logger_name": LOGGER_NAME,
        "label_tags": list(LABEL_TAGS),
        "line_tags": list(LINE_TAGS),
        "check_tags": list(UPGRADE_CHECK_TAGS if upgrade else CHECK_TAGS),
        "button_tags": list(BUTTON_TAGS),
        "text_tags": list(TEXT_TAGS),
        "combo_tags": list(COMBO_TAGS),
        "int32_min": INT32_MIN,
        "int32_max": INT32_MAX,
        "wrong_text_type": WRONG_TEXT_TYPE,
        "wrong_check_type": WRONG_CHECK_TYPE,
        "wrong_index_type": WRONG_INDEX_TYPE,
        "index_overflow": INDEX_OVERFLOW,
        "empty_text": EMPTY_TEXT,
        "muted_value": MUTED_VALUE,
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Answer the ``init_wizard.state`` request the bridge hands over.

    Reads ``is_upgrade`` and the step values from the request. The wizard
    keeps nothing between calls, so every call lays out fresh pages.
    """
    steps = {name: params.get(name) for name in STEP_NAMES}
    return build_view_model(params.get("is_upgrade", False), steps)
