"""usb_auth_widget_surface.py -- the USB hardware key panel.

Describes the panel that turns a removable drive into a hardware key for
exchange credentials. It holds a header, a drive picker with a refresh
button, an export button, a verify button, a progress strip, a status
line, and one row per exchange carrying a status lamp and a hardware
mode switch.

``UsbAuthWidgetModel`` is the panel. ``UsbStatusIndicatorModel`` is the
lamp, ``ExchangeHwRowModel`` one exchange row and ``UsbWorkerModel`` the
scan and export the panel runs away from the screen.
``build_view_model`` returns every value the panel holds as one dict.

Nothing here reads a drive, a credential or a file. The drive list, the
credential store, the export answer and the verify answer are all handed
in by the caller, and every reach outward is recorded rather than made:
``threads`` holds the work the panel asked for, ``timers`` the waits,
``dialogs`` the messages and ``emitted`` the signals. A drive is
described by ``VolumeSource``, whose ``mount_point`` is whatever object
the caller gives; ``auth_path`` joins ``AUTH_FILENAME`` onto it and
never opens the result.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``usb_auth_widget.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.usb_auth_widget``, so a value changed on one side alone is
reported. Nothing here imports Qt.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePath
from typing import Any

METHOD = "usb_auth_widget.state"

LOGGER_NAME = "acervator.gui.usb_auth"

AUTH_FILENAME = ".acervator_auth"

BG = "#0A0A14"
PANEL = "#0D0D20"
BORDER = "#1a1a3f"
CYAN = "#00CCAA"
BLUE = "#4488FF"
GOLD = "#FFB800"
RED = "#FF4444"
GREY = "#667799"
TEXT = "#C8D8F0"
LOCKED = "#FF6666"
UNLOCKED = "#00FF88"

DISABLED_TEXT = "#333355"
DISABLED_BORDER = "#222244"

STATE_INACTIVE = "inactive"
STATE_PRESENT = "present"
STATE_MISSING = "missing"

LAMP_STATES = (STATE_INACTIVE, STATE_PRESENT, STATE_MISSING)

LAMP_SIZE_PX = (22, 22)
LAMP_ELLIPSE_PX = (3, 3, 16, 16)
LAMP_PEN_WIDTH_PX = 1
LAMP_PEN_DARKER_PCT = 150

LAMP_START_TOOLTIP = "USB Hardware Key: inactive"
LAMP_FALLBACK_TOOLTIP = "USB Hardware Key"

LAMP_COLOURS = {
    STATE_INACTIVE: GREY,
    STATE_PRESENT: UNLOCKED,
    STATE_MISSING: LOCKED,
}

LAMP_TOOLTIPS = {
    STATE_INACTIVE: "USB Hardware Key: software credentials",
    STATE_PRESENT: "USB Hardware Key: authenticated (%s)",
    STATE_MISSING: "USB Hardware Key: REQUIRED but not found (%s)",
}

WIDGET_ACCESSIBLE_NAME = "U S B Auth Widget"
ROW_ACCESSIBLE_NAME = "Exchange H W Row"

HEADER_TEXT = "\U0001f510  USB Hardware Authentication Keys"
DESCRIPTION_TEXT = (
    "Convert a USB drive into a hardware authentication key. "
    "API credentials are encrypted with a key unique to your Acervator "
    "installation + the USB drive's serial number. "
    "Once exported, you can enable Hardware Mode per exchange — the app "
    "will then require the USB to be present to access those credentials."
)

EXPORT_GROUP_TITLE = "Export Credentials to USB Key"
MODE_GROUP_TITLE = "Exchange Hardware Mode"
MODE_DESCRIPTION_TEXT = (
    "After exporting and verifying your USB key, enable Hardware Mode "
    "per exchange. The app will then refuse to use software credentials "
    "for that exchange — the USB drive must be present."
)

DRIVE_LABEL_TEXT = "USB Drive:"
REFRESH_TEXT = "\U0001f504 Refresh"
EXPORT_TEXT = "\U0001f511  Export API Keys to USB Key"
VERIFY_TEXT = "✓ Verify"

DRIVE_INFO_START_TEXT = "Select a drive and click Export."
DRIVE_INFO_NONE_TEXT = "No drive selected."
DRIVE_INFO_JOIN = "  |  "
AUTH_PRESENT_PREFIX = "Auth file: present — "
AUTH_ABSENT_TEXT = "Auth file: not present"

SCANNING_TEXT = "Scanning..."
NO_DRIVES_TEXT = "No USB drives detected"
KEY_PRESENT_SUFFIX = " ✓ Key present"
EXPORTING_TEXT = "Exporting and encrypting credentials..."
EMPTY_STATUS_TEXT = ""

NO_EXCHANGES_TEXT = "No exchanges configured. Add exchanges in the API Keys settings."

NO_KEY_TEXT = "No key assigned"
KEY_PREFIX = "Key: "
KEY_SUFFIX = "..."
SERIAL_PREFIX_LEN = 8

TOGGLE_ON_TEXT = "Hardware Mode: ON"
TOGGLE_OFF_TEXT = "Hardware Mode: OFF"

WARNING = "warning"
QUESTION = "question"
INFORMATION = "information"
CRITICAL = "critical"

DIALOG_KINDS = (WARNING, QUESTION, INFORMATION, CRITICAL)

NO_KEY_TITLE = "No Key Assigned"
NO_KEY_BODY = (
    "Export credentials to a USB drive first to assign a hardware key.\n\n"
    "Use the 'Export to USB Key' section above."
)

NO_DRIVE_TITLE = "No Drive"
NO_DRIVE_BODY = "Select a USB drive first."

NO_VAULT_TITLE = "No Vault"
NO_VAULT_BODY = (
    "Credential vault not available. Please add exchange API keys in Settings first."
)

EXPORT_QUESTION_TITLE = "Export API Keys"
EXPORT_DONE_TITLE = "Export Successful"
EXPORT_DONE_SUFFIX = "\n\nYou can now enable Hardware Mode for each exchange below."

NO_AUTH_TITLE = "No Auth File"
VERIFY_PASSED_TITLE = "Verification Passed"
VERIFY_FAILED_TITLE = "Verification Failed"

YES = "yes"
NO = "no"

ANSWERS = (YES, NO)

COMBO_MIN_WIDTH_PX = 240
REFRESH_WIDTH_PX = 90
VERIFY_WIDTH_PX = 90
TOGGLE_WIDTH_PX = 160
PROGRESS_HEIGHT_PX = 4
PROGRESS_RANGE = (0, 0)
PROGRESS_TEXT_VISIBLE = False
SCROLL_MAX_HEIGHT_PX = 200
SCROLL_RESIZABLE = True
ROOT_MARGINS_PX = (0, 0, 0, 0)
ROOT_SPACING_PX = 12
ROW_MARGINS_PX = (10, 6, 10, 6)
ROWS_MARGINS_PX = (0, 0, 0, 0)
ROWS_SPACING_PX = 4

SCAN_DELAY_MS = 300
SCAN_THREAD_NAME = "usb-auth-scan"
EXPORT_THREAD_NAME = "usb-auth-export"
THREAD_IS_DAEMON = True
EMPTY_PHRASE = ""

NO_LISTING_MESSAGE = "no drive listing was supplied"
NO_EXPORTER_MESSAGE = "no credential export was supplied"

SIGNAL_SCAN_COMPLETE = "scan_complete"
SIGNAL_EXPORT_COMPLETE = "export_complete"
SIGNAL_VERIFY_COMPLETE = "verify_complete"
SIGNAL_MODE_CHANGED = "mode_changed"
SIGNAL_HARDWARE_MODE_CHANGED = "hardware_mode_changed"

SIGNALS = (
    SIGNAL_SCAN_COMPLETE,
    SIGNAL_EXPORT_COMPLETE,
    SIGNAL_VERIFY_COMPLETE,
    SIGNAL_MODE_CHANGED,
    SIGNAL_HARDWARE_MODE_CHANGED,
)

UNEMITTED_SIGNALS = (SIGNAL_VERIFY_COMPLETE,)

UNUSED_COLOUR_NAMES = ("GOLD",)

SAVE_FAILED_MESSAGE = "USB auth widget refresh failed: %s"

ACTIONS = {
    "row_toggle": "toggle_row",
    "worker_scan_complete": "on_scan_complete",
    "worker_export_complete": "on_export_complete",
    "refresh_button": "on_refresh",
    "drive_combo_changed": "update_drive_info",
    "export_button": "on_export",
    "verify_button": "on_verify",
    "row_mode_changed": "on_mode_changed",
}

TIMERS = {"auto_scan": SCAN_DELAY_MS}

TIMER_DELAYS_MS = (SCAN_DELAY_MS,)

THREADS = {SCAN_THREAD_NAME: "do_scan", EXPORT_THREAD_NAME: "do_export"}

BUS_TOPICS: tuple[str, ...] = ()

SKIN: dict[str, str] = {}

EXCHANGE_ID_FIELD = "exchange_id"
DISPLAY_NAME_FIELD = "display_name"
HARDWARE_MODE_FIELD = "hardware_mode"
SERIAL_FIELD = "hw_volume_serial"

EXCHANGE_FIELDS = (
    EXCHANGE_ID_FIELD,
    DISPLAY_NAME_FIELD,
    HARDWARE_MODE_FIELD,
    SERIAL_FIELD,
)

STEP_NAMES = (
    "set_vault",
    "refresh",
    "scan_complete",
    "select",
    "export",
    "export_complete",
    "verify",
    "toggle",
    "refresh_exchanges",
)


def small_text_style(colour: str) -> str:
    """Return the ten-pixel note style the panel gives its quiet labels."""
    return f"color: {colour}; font-size: 10px;"


def button_style(colour: str) -> str:
    """Return the see-through look the panel gives its three buttons."""
    off = f"color: {DISABLED_TEXT}; border-color: {DISABLED_BORDER};"
    return f"""
            QPushButton {{
                background: rgba(0,0,0,0);
                color: {colour};
                border: 1px solid {colour};
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,8); }}
            QPushButton:disabled {{ {off} }}
        """


HEADER_STYLE = f"color: {CYAN}; font-size: 14px; font-weight: bold;"

DESCRIPTION_STYLE = small_text_style(GREY)

NAME_STYLE = f"color: {TEXT}; font-weight: bold; font-size: 12px;"

SERIAL_STYLE = small_text_style(GREY)

GROUP_STYLE = f"""
            QGroupBox {{
                color: {TEXT}; font-weight: bold; font-size: 11px;
                border: 1px solid {BORDER}; border-radius: 6px;
                margin-top: 8px; padding-top: 8px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}
        """

COMBO_STYLE = f"""
            QComboBox {{
                background: {BG}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 4px;
                padding: 4px 8px;
            }}
        """

PROGRESS_STYLE = f"""
            QProgressBar {{ background: {BG}; border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {CYAN}; }}
        """

SCROLL_STYLE = "QScrollArea { border: none; background: transparent; }"

ROW_STYLE = f"""
            QFrame {{
                background: {PANEL};
                border: 1px solid {BORDER};
                border-radius: 4px;
            }}
        """

TOGGLE_ON_STYLE = f"""
                QPushButton {{
                    background: rgba(0, 204, 170, 40);
                    color: {CYAN}; border: 1px solid {CYAN};
                    border-radius: 4px; font-weight: bold; font-size: 10px;
                }}
            """

TOGGLE_OFF_STYLE = f"""
                QPushButton {{
                    background: rgba(102, 119, 153, 20);
                    color: {GREY}; border: 1px solid {BORDER};
                    border-radius: 4px; font-size: 10px;
                }}
            """

REFRESH_STYLE = button_style(GREY)
EXPORT_STYLE = button_style(CYAN)
VERIFY_STYLE = button_style(BLUE)


class VolumeSource:
    """One removable drive, described by plain values.

    ``mount_point`` is whatever the caller supplies. ``auth_path`` joins
    the key file name onto it and nothing here opens the result.
    """

    def __init__(
        self,
        label: str = "",
        serial: str = "",
        size_gb: float = 0.0,
        mount_point: Any = "",
        auth_file: Any = None,
        *,
        has_auth_file: bool | None = None,
    ) -> None:
        """Hold one drive's shown values and where its key file would sit."""
        self.label = label
        self.serial = serial
        self.size_gb = size_gb
        self.mount_point = mount_point
        self.auth_file = auth_file
        self.has_auth_file = (
            auth_file is not None if has_auth_file is None else has_auth_file
        )


class SettingsSource:
    """The settings the panel reads its exchange list from and writes back.

    ``exchanges`` is the live list; the panel edits its rows in place, as
    the shipped panel does. ``save_raises`` makes the save refuse.
    """

    def __init__(
        self,
        exchanges: list | None = None,
        save_raises: BaseException | None = None,
    ) -> None:
        """Hold the exchange list and what a write-back does."""
        self.exchanges = [] if exchanges is None else exchanges
        self.save_raises = save_raises
        self.saves = 0

    def save(self) -> None:
        """Write the exchange list back, or raise what the caller scripted."""
        if self.save_raises is not None:
            raise self.save_raises
        self.saves += 1


def no_volume_listing() -> list:
    """Return no drives, for a panel the caller gave no drive listing."""
    return []


def no_export(_volume: Any, _vault: Any, _passphrase: str) -> tuple[bool, str]:
    """Return a refusal, for a panel the caller gave no export."""
    return (False, NO_EXPORTER_MESSAGE)


def no_verify(_auth_file: Any, _serial: str) -> bool:
    """Return a refusal, for a panel the caller gave no verifier."""
    return False


def lamp_tooltip(state: str, label: str = "") -> str:
    """Return the hover text one lamp state shows, with `label` filled in.

    A state the table does not hold shows the bare name of the key.
    """
    if state == STATE_INACTIVE:
        return LAMP_TOOLTIPS[STATE_INACTIVE]
    if state in (STATE_PRESENT, STATE_MISSING):
        return LAMP_TOOLTIPS[state] % label
    return LAMP_FALLBACK_TOOLTIP


def lamp_colour(state: str) -> str:
    """Return the lamp colour for one state, grey for a state the table lacks."""
    return LAMP_COLOURS.get(state, GREY)


def lamp_state(hardware_mode: object, volume_serial: object) -> str:
    """Return the lamp state for one exchange row.

    Present when hardware mode is on and a key is assigned, missing when
    it is on with no key, inactive when it is off.
    """
    if hardware_mode and volume_serial:
        return STATE_PRESENT
    if hardware_mode:
        return STATE_MISSING
    return STATE_INACTIVE


def serial_text(serial: str) -> str:
    """Return the key line one exchange row shows for its assigned serial."""
    if not serial:
        return NO_KEY_TEXT
    return KEY_PREFIX + serial[:SERIAL_PREFIX_LEN] + KEY_SUFFIX


def toggle_text(on: object) -> str:
    """Return the switch caption for hardware mode on or off."""
    return TOGGLE_ON_TEXT if on else TOGGLE_OFF_TEXT


def toggle_style(on: object) -> str:
    """Return the switch look for hardware mode on or off."""
    return TOGGLE_ON_STYLE if on else TOGGLE_OFF_STYLE


def row_name_text(exchange_id: str, display_name: str) -> str:
    """Return the exchange name one row shows.

    The shown name wins; with none the exchange id is capitalised.
    A name that is not text is refused, as the label that shows it
    refuses one.
    """
    found = display_name or exchange_id.title()
    if not isinstance(found, str):
        raise TypeError(
            f"an exchange name must be text, not {type(found).__name__}",
        )
    return found


def drive_item_label(volume: VolumeSource) -> str:
    """Return the one line the drive picker shows for one drive."""
    label = f"{volume.label} ({volume.size_gb:.1f} GB) — {volume.serial}"
    if volume.has_auth_file:
        label += KEY_PRESENT_SUFFIX
    return label


def drive_info_text(volume: VolumeSource) -> str:
    """Return the four-part line under the drive picker for one drive."""
    parts = [
        f"Mount: {volume.mount_point}",
        f"Serial: {volume.serial}",
        f"Size: {volume.size_gb:.1f} GB",
    ]
    if volume.has_auth_file:
        parts.append(AUTH_PRESENT_PREFIX + str(volume.auth_file))
    else:
        parts.append(AUTH_ABSENT_TEXT)
    return DRIVE_INFO_JOIN.join(parts)


def auth_path(volume: VolumeSource) -> object:
    """Return where the panel says the key file would be written.

    The mount point is joined with the key file name using whatever
    object the caller supplied. Nothing opens the result.
    """
    return volume.mount_point / AUTH_FILENAME


def export_question_body(volume: VolumeSource) -> str:
    """Return the confirmation shown before the panel writes a key file."""
    return (
        f"This will encrypt ALL exchange API keys to:\n\n"
        f"  {auth_path(volume)}\n\n"
        f"Drive:  {volume.label}\n"
        f"Serial: {volume.serial}\n\n"
        f"The encrypted file can only be read by this Acervator installation.\n"
        f"After export, enable Hardware Mode per exchange below.\n\n"
        f"Continue?"
    )


def no_auth_body(volume: VolumeSource) -> str:
    """Return the refusal shown when a drive carries no key file."""
    return (
        f"No {AUTH_FILENAME} file found on {volume.label}.\n"
        "Export credentials first."
    )


def verify_passed_body(volume: VolumeSource) -> str:
    """Return the message shown when a key file decrypts."""
    return (
        f"✓ Auth file on {volume.label} decrypts successfully.\n"
        f"Serial: {volume.serial}\n"
        "This USB is a valid Acervator hardware key."
    )


def verify_failed_body(volume: VolumeSource) -> str:
    """Return the message shown when a key file does not decrypt."""
    return (
        f"✗ Auth file on {volume.label} could not be verified.\n"
        "It may be corrupted or from a different installation.\n"
        "Try re-exporting."
    )


def export_done_body(message: str) -> str:
    """Return the message shown after a key file is written."""
    return f"{message}{EXPORT_DONE_SUFFIX}"


def status_style(success: object) -> str:
    """Return the status line colour for a finished export."""
    return small_text_style(UNLOCKED if success else RED)


class UsbStatusIndicatorModel:
    """The lamp that shows whether a hardware key is present.

    Green means the key is there, red means hardware mode wants one and
    it is not, grey means the panel is using stored credentials.
    """

    def __init__(self) -> None:
        """Start the lamp grey, with hardware mode not in use."""
        self.state = STATE_INACTIVE
        self.exchange_label = ""
        self.size_px = LAMP_SIZE_PX
        self.tooltip = LAMP_START_TOOLTIP
        self.updates = 0

    def set_state(self, state: str, label: str = "") -> None:
        """Move the lamp to `state` and repaint it."""
        self.state = state
        self.exchange_label = label
        self.tooltip = lamp_tooltip(state, label)
        self.updates += 1

    def paint(self) -> list:
        """Return the drawing steps the lamp asks for, in order.

        The pen carries the fill colour and the darkening percentage --
        the request, not the result -- so the renderer darkens it.
        """
        colour = lamp_colour(self.state)
        return [
            ["antialiasing", True],
            ["pen", colour, LAMP_PEN_DARKER_PCT, LAMP_PEN_WIDTH_PX],
            ["brush", colour],
            ["ellipse", list(LAMP_ELLIPSE_PX)],
        ]

    def build_view_model(self) -> dict:
        """Return every value the lamp holds."""
        return {
            "state": self.state,
            "exchange_label": self.exchange_label,
            "tooltip": self.tooltip,
            "size_px": list(self.size_px),
            "colour": lamp_colour(self.state),
            "paint": self.paint(),
            "updates": self.updates,
        }


class ExchangeHwRowModel:
    """One exchange row: its name, its key, its lamp and its switch."""

    def __init__(
        self,
        exchange_id: str = "",
        display_name: str = "",
        *,
        hardware_mode: Any = False,
        volume_serial: str = "",
        dialogs: list | None = None,
        emitted: list | None = None,
    ) -> None:
        """Build one exchange row from the values that exchange holds."""
        self.exchange_id = exchange_id
        self.hw_mode = hardware_mode
        self.serial = volume_serial
        self.accessible_name = ROW_ACCESSIBLE_NAME
        self.style = ROW_STYLE
        self.margins_px = ROW_MARGINS_PX
        self.name_text = row_name_text(exchange_id, display_name)
        self.name_style = NAME_STYLE
        self.serial_text = serial_text(volume_serial)
        self.serial_style = SERIAL_STYLE
        self.lamp = UsbStatusIndicatorModel()
        self.lamp.set_state(lamp_state(hardware_mode, volume_serial))
        self.toggle_text = toggle_text(hardware_mode)
        self.toggle_checked = bool(hardware_mode)
        self.toggle_checkable = True
        self.toggle_width_px = TOGGLE_WIDTH_PX
        self.toggle_style = toggle_style(hardware_mode)
        self.dialogs = [] if dialogs is None else dialogs
        self.emitted = [] if emitted is None else emitted

    def apply_toggle_style(self, on: object) -> None:
        """Give the switch the look for hardware mode on or off."""
        self.toggle_style = toggle_style(on)

    def toggle(self, checked: object) -> None:
        """Take a press of the hardware mode switch.

        A press that turns hardware mode on with no key assigned refuses,
        shows a message and puts the switch back.
        """
        if checked and not self.serial:
            self.dialogs.append([WARNING, NO_KEY_TITLE, NO_KEY_BODY])
            self.toggle_checked = False
            return
        self.hw_mode = checked
        self.toggle_checked = bool(checked)
        self.toggle_text = toggle_text(checked)
        self.apply_toggle_style(checked)
        self.lamp.set_state(lamp_state(checked, self.serial))
        self.emitted.append([SIGNAL_MODE_CHANGED, [self.exchange_id, checked]])

    def update_serial(self, serial: str) -> None:
        """Assign `serial` as this exchange's key and redraw its key line."""
        self.serial = serial
        self.serial_text = serial_text(serial)

    def build_view_model(self) -> dict:
        """Return every value one exchange row holds."""
        return {
            "exchange_id": self.exchange_id,
            "accessible_name": self.accessible_name,
            "style": self.style,
            "margins_px": list(self.margins_px),
            "name_text": self.name_text,
            "name_style": self.name_style,
            "serial_text": self.serial_text,
            "serial_style": self.serial_style,
            "lamp": self.lamp.build_view_model(),
            "toggle_text": self.toggle_text,
            "toggle_checked": self.toggle_checked,
            "toggle_checkable": self.toggle_checkable,
            "toggle_width_px": self.toggle_width_px,
            "toggle_style": self.toggle_style,
            "hardware_mode": bool(self.hw_mode),
            "serial": self.serial,
        }


class UsbWorkerModel:
    """The scan and the export the panel runs away from the screen.

    ``scan`` and ``export`` record the work the panel asked for and start
    nothing. ``do_scan`` and ``do_export`` are that work, and each reads
    a callable the caller supplied rather than a drive.
    """

    def __init__(
        self,
        list_volumes: Callable[[], list] = no_volume_listing,
        export_credentials: Callable[..., tuple] = no_export,
        threads: list | None = None,
        emitted: list | None = None,
    ) -> None:
        """Hold the drive listing and the export the caller supplied."""
        self.list_volumes = list_volumes
        self.export_credentials = export_credentials
        self.threads = [] if threads is None else threads
        self.emitted = [] if emitted is None else emitted

    def scan(self) -> None:
        """Ask for a drive scan off the screen thread."""
        self.threads.append([SCAN_THREAD_NAME, THREAD_IS_DAEMON, "do_scan", 0])

    def export(self, volume: Any, vault: Any, passphrase: str) -> None:
        """Ask for a credential export off the screen thread."""
        carried = len((volume, vault, passphrase))
        self.threads.append(
            [EXPORT_THREAD_NAME, THREAD_IS_DAEMON, "do_export", carried],
        )

    def do_scan(self) -> list:
        """List the drives, reporting none when the listing refuses."""
        try:
            volumes = self.list_volumes()
        except Exception:
            volumes = []
        self.emitted.append([SIGNAL_SCAN_COMPLETE, volumes])
        return volumes

    def do_export(self, volume: Any, vault: Any, passphrase: str) -> list:
        """Write the credentials, reporting the refusal text on a failure."""
        try:
            done, message = self.export_credentials(volume, vault, passphrase)
            answer = [done, message]
        except Exception as refused:
            answer = [False, str(refused)]
        self.emitted.append([SIGNAL_EXPORT_COMPLETE, answer])
        return answer


class UsbAuthWidgetModel:
    """The whole USB hardware key panel.

    Built from a settings source, an optional credential store and an
    optional verifier. ``build`` lays the panel out and asks for the
    first drive scan; every later step is one of the methods `ACTIONS`
    names.
    """

    def __init__(
        self,
        settings: Any = None,
        vault: Any = None,
        list_volumes: Callable[[], list] = no_volume_listing,
        export_credentials: Callable[..., tuple] = no_export,
        verify_auth_file: Callable[..., bool] = no_verify,
        answers: list | None = None,
    ) -> None:
        """Hold the settings, the credential store and the verifier."""
        self.settings = settings
        self.vault = vault
        self.verify_auth_file = verify_auth_file
        self.answers = list(answers or ())
        self.usb_vols: list = []
        self.dialogs: list = []
        self.emitted: list = []
        self.threads: list = []
        self.timers: list = []
        self.saves: list = []
        self.save_refusals: list = []
        self.verify_calls: list = []
        self.worker = UsbWorkerModel(
            list_volumes=list_volumes,
            export_credentials=export_credentials,
            threads=self.threads,
            emitted=self.emitted,
        )
        self.accessible_name = WIDGET_ACCESSIBLE_NAME
        self.root_margins_px = ROOT_MARGINS_PX
        self.root_spacing_px = ROOT_SPACING_PX
        self.header_text = HEADER_TEXT
        self.header_style = HEADER_STYLE
        self.description_text = DESCRIPTION_TEXT
        self.description_style = DESCRIPTION_STYLE
        self.export_group_title = EXPORT_GROUP_TITLE
        self.group_style = GROUP_STYLE
        self.drive_label_text = DRIVE_LABEL_TEXT
        self.combo_items: list[str] = []
        self.combo_data: list[VolumeSource | None] = []
        self.combo_index = -1
        self.combo_min_width_px = COMBO_MIN_WIDTH_PX
        self.combo_style = COMBO_STYLE
        self.refresh_text = REFRESH_TEXT
        self.refresh_width_px = REFRESH_WIDTH_PX
        self.refresh_style = REFRESH_STYLE
        self.refresh_enabled = True
        self.drive_info_text = DRIVE_INFO_START_TEXT
        self.drive_info_style = small_text_style(GREY)
        self.export_text = EXPORT_TEXT
        self.export_style = EXPORT_STYLE
        self.export_enabled = True
        self.verify_text = VERIFY_TEXT
        self.verify_width_px = VERIFY_WIDTH_PX
        self.verify_style = VERIFY_STYLE
        self.progress_visible = False
        self.progress_height_px = PROGRESS_HEIGHT_PX
        self.progress_range = PROGRESS_RANGE
        self.progress_text_visible = PROGRESS_TEXT_VISIBLE
        self.progress_style = PROGRESS_STYLE
        self.export_status_text = EMPTY_STATUS_TEXT
        self.export_status_style = small_text_style(GREY)
        self.mode_group_title = MODE_GROUP_TITLE
        self.mode_description_text = MODE_DESCRIPTION_TEXT
        self.mode_description_style = small_text_style(GREY)
        self.scroll_resizable = SCROLL_RESIZABLE
        self.scroll_max_height_px = SCROLL_MAX_HEIGHT_PX
        self.scroll_style = SCROLL_STYLE
        self.rows_margins_px = ROWS_MARGINS_PX
        self.rows_spacing_px = ROWS_SPACING_PX
        self.rows: list = []
        self.empty_text = ""
        self.empty_style = ""

    def build(self) -> UsbAuthWidgetModel:
        """Lay the panel out and ask for the first drive scan."""
        self.rebuild_exchange_rows()
        self.timers.append([SCAN_DELAY_MS, "scan"])
        return self

    def exchange_rows(self) -> list:
        """Return the exchange list the settings hold, empty when there are none."""
        return self.settings.exchanges if self.settings else []

    def rebuild_exchange_rows(self) -> None:
        """Rebuild one row per exchange, or the note that there are none."""
        self.rows = []
        exchanges = self.exchange_rows()
        if not exchanges:
            self.empty_text = NO_EXCHANGES_TEXT
            self.empty_style = small_text_style(GREY)
            return
        self.empty_text = ""
        self.empty_style = ""
        for one in exchanges:
            self.rows.append(
                ExchangeHwRowModel(
                    exchange_id=one.get(EXCHANGE_ID_FIELD, ""),
                    display_name=one.get(DISPLAY_NAME_FIELD, ""),
                    hardware_mode=one.get(HARDWARE_MODE_FIELD, False),
                    volume_serial=one.get(SERIAL_FIELD, ""),
                    dialogs=self.dialogs,
                    emitted=self.emitted,
                ),
            )

    def save_settings(self) -> None:
        """Write the settings back, recording a refusal instead of raising."""
        try:
            self.settings.save()
            self.saves.append(True)
        except Exception as refused:
            self.save_refusals.append(type(refused).__name__)

    def on_mode_changed(self, exchange_id: str, hw_mode: object) -> None:
        """Store one row's hardware mode and tell the panel's host."""
        for one in self.exchange_rows():
            if one.get(EXCHANGE_ID_FIELD) == exchange_id:
                one[HARDWARE_MODE_FIELD] = hw_mode
                serial = one.get(SERIAL_FIELD, "")
                self.emitted.append(
                    [
                        SIGNAL_HARDWARE_MODE_CHANGED,
                        [exchange_id, hw_mode, serial],
                    ],
                )
                break
        self.save_settings()

    def toggle_row(self, index: int, checked: object) -> None:
        """Press one row's hardware mode switch and route what it emits."""
        row = self.rows[index]
        before = len(self.emitted)
        row.toggle(checked)
        for one in self.emitted[before:]:
            if one[0] == SIGNAL_MODE_CHANGED:
                self.on_mode_changed(one[1][0], one[1][1])

    def on_refresh(self) -> None:
        """Clear the drive picker and ask for another scan."""
        self.combo_items = [SCANNING_TEXT]
        self.combo_data = [None]
        self.combo_index = 0
        self.refresh_enabled = False
        self.worker.scan()

    def on_scan_complete(self, volumes: list) -> None:
        """Fill the drive picker from a finished scan."""
        self.usb_vols = list(volumes)
        self.combo_items = []
        self.combo_data = []
        self.combo_index = -1
        self.refresh_enabled = True
        if not self.usb_vols:
            self.combo_items = [NO_DRIVES_TEXT]
            self.combo_data = [None]
            self.combo_index = 0
            self.export_enabled = False
        else:
            for volume in self.usb_vols:
                self.combo_items.append(drive_item_label(volume))
                self.combo_data.append(volume)
            self.combo_index = 0
            self.export_enabled = True
        self.update_drive_info()

    def selected_volume(self) -> VolumeSource | None:
        """Return the drive the picker is on, or nothing."""
        if self.combo_index < 0 or not self.usb_vols:
            return None
        return self.combo_data[self.combo_index]

    def select(self, index: int) -> None:
        """Move the drive picker to `index` and redraw the line under it.

        An index the picker does not hold clears the selection.
        Measured on the picker itself: -5, -1, 1 and 99 all land on
        -1 on a picker holding one row.
        """
        holds = 0 <= index < len(self.combo_items)
        self.combo_index = index if holds else -1
        self.update_drive_info()

    def update_drive_info(self) -> None:
        """Redraw the four-part line under the drive picker."""
        volume = self.selected_volume()
        if volume is None:
            self.drive_info_text = DRIVE_INFO_NONE_TEXT
            return
        self.drive_info_text = drive_info_text(volume)

    def next_answer(self) -> str:
        """Return the next scripted answer to a confirmation, or no."""
        return self.answers.pop(0) if self.answers else NO

    def on_export(self) -> None:
        """Confirm, then ask for the credentials to be written to the drive."""
        volume = self.selected_volume()
        if volume is None:
            self.dialogs.append([WARNING, NO_DRIVE_TITLE, NO_DRIVE_BODY])
            return
        if self.vault is None:
            self.dialogs.append([WARNING, NO_VAULT_TITLE, NO_VAULT_BODY])
            return
        self.dialogs.append(
            [QUESTION, EXPORT_QUESTION_TITLE, export_question_body(volume)],
        )
        if self.next_answer() != YES:
            return
        self.export_enabled = False
        self.progress_visible = True
        self.export_status_text = EXPORTING_TEXT
        self.export_status_style = small_text_style(GREY)
        self.worker.export(volume, self.vault, EMPTY_PHRASE)

    def on_export_complete(self, success: object, message: str) -> None:
        """Show the export answer and assign the key to unassigned exchanges."""
        self.progress_visible = False
        self.export_enabled = True
        self.export_status_text = message
        self.export_status_style = status_style(success)
        if not success:
            return
        volume = self.selected_volume()
        if volume:
            for one in self.exchange_rows():
                if not one.get(SERIAL_FIELD):
                    one[SERIAL_FIELD] = volume.serial
            self.save_settings()
            self.rebuild_exchange_rows()
        self.dialogs.append(
            [INFORMATION, EXPORT_DONE_TITLE, export_done_body(message)],
        )

    def on_verify(self) -> None:
        """Read the key file on the selected drive and report what it says."""
        volume = self.selected_volume()
        if volume is None:
            self.dialogs.append([WARNING, NO_DRIVE_TITLE, NO_DRIVE_BODY])
            return
        if not volume.has_auth_file:
            self.dialogs.append([WARNING, NO_AUTH_TITLE, no_auth_body(volume)])
            return
        self.verify_calls.append([str(volume.auth_file), volume.serial])
        if self.verify_auth_file(volume.auth_file, volume.serial):
            self.dialogs.append(
                [INFORMATION, VERIFY_PASSED_TITLE, verify_passed_body(volume)],
            )
        else:
            self.dialogs.append(
                [CRITICAL, VERIFY_FAILED_TITLE, verify_failed_body(volume)],
            )

    def set_vault(self, vault: Any) -> None:
        """Hand the panel its credential store after it is built."""
        self.vault = vault

    def refresh_exchanges(self) -> None:
        """Rebuild the exchange rows after the exchange list changed."""
        self.rebuild_exchange_rows()


def build_model(
    settings: Any = None,
    vault: Any = None,
    list_volumes: Callable[[], list] = no_volume_listing,
    export_credentials: Callable[..., tuple] = no_export,
    verify_auth_file: Callable[..., bool] = no_verify,
    answers: list | None = None,
    *,
    build_now: bool = False,
) -> UsbAuthWidgetModel:
    """Return one panel, built from plain values, laid out when `build_now`."""
    model = UsbAuthWidgetModel(
        settings=settings,
        vault=vault,
        list_volumes=list_volumes,
        export_credentials=export_credentials,
        verify_auth_file=verify_auth_file,
        answers=answers,
    )
    if build_now:
        model.build()
    return model


PANEL_MODEL: UsbAuthWidgetModel | None = None


def panel_model() -> UsbAuthWidgetModel:
    """Return the one panel the bridge keeps, built on the first request."""
    global PANEL_MODEL
    if PANEL_MODEL is None:
        PANEL_MODEL = build_model(settings=SettingsSource(), build_now=True)
    return PANEL_MODEL


CONSTANTS = {
    "METHOD": METHOD,
    "LOGGER_NAME": LOGGER_NAME,
    "AUTH_FILENAME": AUTH_FILENAME,
    "BG": BG,
    "PANEL": PANEL,
    "BORDER": BORDER,
    "CYAN": CYAN,
    "BLUE": BLUE,
    "GOLD": GOLD,
    "RED": RED,
    "GREY": GREY,
    "TEXT": TEXT,
    "LOCKED": LOCKED,
    "UNLOCKED": UNLOCKED,
    "DISABLED_TEXT": DISABLED_TEXT,
    "DISABLED_BORDER": DISABLED_BORDER,
    "STATE_INACTIVE": STATE_INACTIVE,
    "STATE_PRESENT": STATE_PRESENT,
    "STATE_MISSING": STATE_MISSING,
    "LAMP_STATES": list(LAMP_STATES),
    "LAMP_SIZE_PX": list(LAMP_SIZE_PX),
    "LAMP_ELLIPSE_PX": list(LAMP_ELLIPSE_PX),
    "LAMP_PEN_WIDTH_PX": LAMP_PEN_WIDTH_PX,
    "LAMP_PEN_DARKER_PCT": LAMP_PEN_DARKER_PCT,
    "LAMP_START_TOOLTIP": LAMP_START_TOOLTIP,
    "LAMP_FALLBACK_TOOLTIP": LAMP_FALLBACK_TOOLTIP,
    "LAMP_COLOURS": dict(LAMP_COLOURS),
    "LAMP_TOOLTIPS": dict(LAMP_TOOLTIPS),
    "WIDGET_ACCESSIBLE_NAME": WIDGET_ACCESSIBLE_NAME,
    "ROW_ACCESSIBLE_NAME": ROW_ACCESSIBLE_NAME,
    "HEADER_TEXT": HEADER_TEXT,
    "DESCRIPTION_TEXT": DESCRIPTION_TEXT,
    "EXPORT_GROUP_TITLE": EXPORT_GROUP_TITLE,
    "MODE_GROUP_TITLE": MODE_GROUP_TITLE,
    "MODE_DESCRIPTION_TEXT": MODE_DESCRIPTION_TEXT,
    "DRIVE_LABEL_TEXT": DRIVE_LABEL_TEXT,
    "REFRESH_TEXT": REFRESH_TEXT,
    "EXPORT_TEXT": EXPORT_TEXT,
    "VERIFY_TEXT": VERIFY_TEXT,
    "DRIVE_INFO_START_TEXT": DRIVE_INFO_START_TEXT,
    "DRIVE_INFO_NONE_TEXT": DRIVE_INFO_NONE_TEXT,
    "DRIVE_INFO_JOIN": DRIVE_INFO_JOIN,
    "AUTH_PRESENT_PREFIX": AUTH_PRESENT_PREFIX,
    "AUTH_ABSENT_TEXT": AUTH_ABSENT_TEXT,
    "SCANNING_TEXT": SCANNING_TEXT,
    "NO_DRIVES_TEXT": NO_DRIVES_TEXT,
    "KEY_PRESENT_SUFFIX": KEY_PRESENT_SUFFIX,
    "EXPORTING_TEXT": EXPORTING_TEXT,
    "EMPTY_STATUS_TEXT": EMPTY_STATUS_TEXT,
    "NO_EXCHANGES_TEXT": NO_EXCHANGES_TEXT,
    "NO_KEY_TEXT": NO_KEY_TEXT,
    "KEY_PREFIX": KEY_PREFIX,
    "KEY_SUFFIX": KEY_SUFFIX,
    "SERIAL_PREFIX_LEN": SERIAL_PREFIX_LEN,
    "TOGGLE_ON_TEXT": TOGGLE_ON_TEXT,
    "TOGGLE_OFF_TEXT": TOGGLE_OFF_TEXT,
    "WARNING": WARNING,
    "QUESTION": QUESTION,
    "INFORMATION": INFORMATION,
    "CRITICAL": CRITICAL,
    "DIALOG_KINDS": list(DIALOG_KINDS),
    "NO_KEY_TITLE": NO_KEY_TITLE,
    "NO_KEY_BODY": NO_KEY_BODY,
    "NO_DRIVE_TITLE": NO_DRIVE_TITLE,
    "NO_DRIVE_BODY": NO_DRIVE_BODY,
    "NO_VAULT_TITLE": NO_VAULT_TITLE,
    "NO_VAULT_BODY": NO_VAULT_BODY,
    "EXPORT_QUESTION_TITLE": EXPORT_QUESTION_TITLE,
    "EXPORT_DONE_TITLE": EXPORT_DONE_TITLE,
    "EXPORT_DONE_SUFFIX": EXPORT_DONE_SUFFIX,
    "NO_AUTH_TITLE": NO_AUTH_TITLE,
    "VERIFY_PASSED_TITLE": VERIFY_PASSED_TITLE,
    "VERIFY_FAILED_TITLE": VERIFY_FAILED_TITLE,
    "YES": YES,
    "NO": NO,
    "ANSWERS": list(ANSWERS),
    "COMBO_MIN_WIDTH_PX": COMBO_MIN_WIDTH_PX,
    "REFRESH_WIDTH_PX": REFRESH_WIDTH_PX,
    "VERIFY_WIDTH_PX": VERIFY_WIDTH_PX,
    "TOGGLE_WIDTH_PX": TOGGLE_WIDTH_PX,
    "PROGRESS_HEIGHT_PX": PROGRESS_HEIGHT_PX,
    "PROGRESS_RANGE": list(PROGRESS_RANGE),
    "PROGRESS_TEXT_VISIBLE": PROGRESS_TEXT_VISIBLE,
    "SCROLL_MAX_HEIGHT_PX": SCROLL_MAX_HEIGHT_PX,
    "SCROLL_RESIZABLE": SCROLL_RESIZABLE,
    "ROOT_MARGINS_PX": list(ROOT_MARGINS_PX),
    "ROOT_SPACING_PX": ROOT_SPACING_PX,
    "ROW_MARGINS_PX": list(ROW_MARGINS_PX),
    "ROWS_MARGINS_PX": list(ROWS_MARGINS_PX),
    "ROWS_SPACING_PX": ROWS_SPACING_PX,
    "SCAN_DELAY_MS": SCAN_DELAY_MS,
    "SCAN_THREAD_NAME": SCAN_THREAD_NAME,
    "EXPORT_THREAD_NAME": EXPORT_THREAD_NAME,
    "THREAD_IS_DAEMON": THREAD_IS_DAEMON,
    "EMPTY_PHRASE": EMPTY_PHRASE,
    "NO_LISTING_MESSAGE": NO_LISTING_MESSAGE,
    "NO_EXPORTER_MESSAGE": NO_EXPORTER_MESSAGE,
    "SIGNAL_SCAN_COMPLETE": SIGNAL_SCAN_COMPLETE,
    "SIGNAL_EXPORT_COMPLETE": SIGNAL_EXPORT_COMPLETE,
    "SIGNAL_VERIFY_COMPLETE": SIGNAL_VERIFY_COMPLETE,
    "SIGNAL_MODE_CHANGED": SIGNAL_MODE_CHANGED,
    "SIGNAL_HARDWARE_MODE_CHANGED": SIGNAL_HARDWARE_MODE_CHANGED,
    "SIGNALS": list(SIGNALS),
    "UNEMITTED_SIGNALS": list(UNEMITTED_SIGNALS),
    "UNUSED_COLOUR_NAMES": list(UNUSED_COLOUR_NAMES),
    "SAVE_FAILED_MESSAGE": SAVE_FAILED_MESSAGE,
    "ACTIONS": dict(ACTIONS),
    "TIMERS": dict(TIMERS),
    "TIMER_DELAYS_MS": list(TIMER_DELAYS_MS),
    "THREADS": dict(THREADS),
    "BUS_TOPICS": list(BUS_TOPICS),
    "SKIN": dict(SKIN),
    "EXCHANGE_ID_FIELD": EXCHANGE_ID_FIELD,
    "DISPLAY_NAME_FIELD": DISPLAY_NAME_FIELD,
    "HARDWARE_MODE_FIELD": HARDWARE_MODE_FIELD,
    "SERIAL_FIELD": SERIAL_FIELD,
    "EXCHANGE_FIELDS": list(EXCHANGE_FIELDS),
    "STEP_NAMES": list(STEP_NAMES),
    "HEADER_STYLE": HEADER_STYLE,
    "DESCRIPTION_STYLE": DESCRIPTION_STYLE,
    "NAME_STYLE": NAME_STYLE,
    "SERIAL_STYLE": SERIAL_STYLE,
    "GROUP_STYLE": GROUP_STYLE,
    "COMBO_STYLE": COMBO_STYLE,
    "PROGRESS_STYLE": PROGRESS_STYLE,
    "SCROLL_STYLE": SCROLL_STYLE,
    "ROW_STYLE": ROW_STYLE,
    "TOGGLE_ON_STYLE": TOGGLE_ON_STYLE,
    "TOGGLE_OFF_STYLE": TOGGLE_OFF_STYLE,
    "REFRESH_STYLE": REFRESH_STYLE,
    "EXPORT_STYLE": EXPORT_STYLE,
    "VERIFY_STYLE": VERIFY_STYLE,
}


def build_view_model(model: UsbAuthWidgetModel | None = None) -> dict:
    """Return every value the panel holds as one dict.

    With no model the shared panel is used, which is built on the first
    request rather than while this module loads.
    """
    panel = panel_model() if model is None else model
    return {
        "method": METHOD,
        "accessible_name": panel.accessible_name,
        "root_margins_px": list(panel.root_margins_px),
        "root_spacing_px": panel.root_spacing_px,
        "header_text": panel.header_text,
        "header_style": panel.header_style,
        "description_text": panel.description_text,
        "description_style": panel.description_style,
        "export_group_title": panel.export_group_title,
        "group_style": panel.group_style,
        "drive_label_text": panel.drive_label_text,
        "combo_items": list(panel.combo_items),
        "combo_index": panel.combo_index,
        "combo_min_width_px": panel.combo_min_width_px,
        "combo_style": panel.combo_style,
        "refresh_text": panel.refresh_text,
        "refresh_width_px": panel.refresh_width_px,
        "refresh_style": panel.refresh_style,
        "refresh_enabled": panel.refresh_enabled,
        "drive_info_text": panel.drive_info_text,
        "drive_info_style": panel.drive_info_style,
        "export_text": panel.export_text,
        "export_style": panel.export_style,
        "export_enabled": panel.export_enabled,
        "verify_text": panel.verify_text,
        "verify_width_px": panel.verify_width_px,
        "verify_style": panel.verify_style,
        "progress_visible": panel.progress_visible,
        "progress_height_px": panel.progress_height_px,
        "progress_range": list(panel.progress_range),
        "progress_text_visible": panel.progress_text_visible,
        "progress_style": panel.progress_style,
        "export_status_text": panel.export_status_text,
        "export_status_style": panel.export_status_style,
        "mode_group_title": panel.mode_group_title,
        "mode_description_text": panel.mode_description_text,
        "mode_description_style": panel.mode_description_style,
        "scroll_resizable": panel.scroll_resizable,
        "scroll_max_height_px": panel.scroll_max_height_px,
        "scroll_style": panel.scroll_style,
        "rows_margins_px": list(panel.rows_margins_px),
        "rows_spacing_px": panel.rows_spacing_px,
        "rows": [one.build_view_model() for one in panel.rows],
        "empty_text": panel.empty_text,
        "empty_style": panel.empty_style,
        "exchanges": [dict(one) for one in panel.exchange_rows()],
        "dialogs": [list(one) for one in panel.dialogs],
        "emitted": [[one[0], one[1]] for one in panel.emitted],
        "threads": [list(one) for one in panel.threads],
        "timers": [list(one) for one in panel.timers],
        "saves": len(panel.saves),
        "save_refusals": list(panel.save_refusals),
        "verify_calls": [list(one) for one in panel.verify_calls],
        "answers_left": list(panel.answers),
        "constants": dict(CONSTANTS),
    }


def volume_from(one: dict) -> VolumeSource:
    """Return one drive built from the plain values a request carries.

    A mount point and a key file cross the bridge as text. Both are
    turned back into a path, which joins but never opens.
    """
    found = dict(one)
    for name in ("mount_point", "auth_file"):
        if isinstance(found.get(name), str):
            found[name] = PurePath(found[name])
    return VolumeSource(**found)


def view_model(params: dict) -> dict:
    """Bridge handler for ``usb_auth_widget.state``.

    ``reset`` throws the shared panel away and builds a new one from the
    ``exchanges``, ``vault`` and ``answers`` in the same request. Every
    other key named in ``STEP_NAMES`` drives one step, in that order.
    """
    global PANEL_MODEL
    if params.get("reset"):
        PANEL_MODEL = build_model(
            settings=SettingsSource(list(params.get("exchanges") or ())),
            vault=params.get("vault"),
            answers=params.get("answers"),
            build_now=True,
        )
    panel = panel_model()
    if "set_vault" in params:
        panel.set_vault(params["set_vault"])
    if params.get("refresh"):
        panel.on_refresh()
    if "scan_complete" in params:
        panel.on_scan_complete(
            [volume_from(one) for one in params["scan_complete"]],
        )
    if "select" in params:
        panel.select(params["select"])
    if params.get("export"):
        panel.on_export()
    if "export_complete" in params:
        done, message = params["export_complete"]
        panel.on_export_complete(done, message)
    if params.get("verify"):
        panel.on_verify()
    if "toggle" in params:
        index, checked = params["toggle"]
        panel.toggle_row(index, checked)
    if params.get("refresh_exchanges"):
        panel.refresh_exchanges()
    return build_view_model(panel)
