"""The shipped USB hardware key panel and the Qt-free surface, side by side.

A failure means the view model carries a different label, a different
style, a different drive line, a different message box, a different
exchange row, a different recorded thread, a different timer request or
a different refusal than ``USBAuthWidget``.

No test here reads or writes a real drive, a real credential or anything
under the operator's runtime tree. Every drive, serial, mount point,
exchange and credential store below is invented, and the two functions
that would reach a device are swapped for stand-ins that record instead.
The clock is handed in: a frozen reader replaces every wall-clock
function for the length of a drive.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core import usb_auth as core
from src.gui import usb_auth_widget as shipped
from src.gui.main_tabs import usb_auth_widget_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

WIDGET_PATH = REPO_ROOT / "src/gui/usb_auth_widget.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/usb_auth_widget_surface.py"


PIXEL_SIZE = (760, 460)

#: Counted off the parsed shipped file by the counters below, each of
#: which is pointed at a neighbour that really carries one.
WIDGET_CONNECT_SITES = 8
WIDGET_TIMER_SITES = 1
WIDGET_SIGNAL_BUILDS = 5
WIDGET_THREAD_BUILDS = 2
WIDGET_METHODS = 25
WIDGET_MODULE_FUNCTIONS = 0


#: The frozen reading every wall-clock function returns for a drive.
FROZEN_SECONDS = 1_787_500_000.0

#: Invented. No serial, mount point, exchange or drive name is real.
PLAIN_ID = "chipex"
PLAIN_NAME = "Chip Exchange"
SECOND_ID = "boltex"
PLAIN_SERIAL = "SER-0001-AAAA"
SECOND_SERIAL = "SER-0002-BBBB"
SHORT_SERIAL = "AB"
UNICODE_TEXT = "Δ⚡"
MARKUP_TEXT = "<b>drive</b>"
APOSTROPHE_TEXT = "Ekthelius" + chr(39) + "s"
NEWLINE_TEXT = "two\nlines-one-drive"
LONG_TEXT = "x" * 200
LOWER_CASE_ID = "CHIPex"
PLAIN_MOUNT = PurePosixPath("/invented/chip")
SECOND_MOUNT = PurePosixPath("/invented/bolt")
VAULT = "an invented credential store"
EXPORT_MESSAGE = "wrote 2 exchanges"

WIDGETS_HELD: list = []


# The application object, and the widgets a render must outlive


def app():
    """The one application object every widget below is built under."""
    from PySide6.QtWidgets import QApplication

    load_run_fonts()
    return QApplication.instance() or QApplication([])


def hold(widget):
    """Keep `widget` alive for the whole run and return it."""
    WIDGETS_HELD.append(widget)
    return widget


# One starting state, handed to both sides


class Drive:
    """One invented removable drive. Nothing here touches a device.

    A drive that has stopped answering refuses every read of its
    size, which is what the next read of a removed drive does.
    """

    def __init__(self, label, serial, size_gb, mount_point, auth_file, vanishing):
        self.label = label
        self.serial = serial
        self._size_gb = size_gb
        self.vanishing = vanishing
        self.reads = 0
        self.mount_point = mount_point
        self.auth_file = auth_file
        self.has_auth_file = auth_file is not None

    @property
    def size_gb(self):
        """The drive size, refusing every read once the drive is gone."""
        self.reads += 1
        if self.vanishing:
            raise OSError("the drive was removed while it was being read")
        return self._size_gb


def drive(spec):
    """One drive built from one invented description."""
    return Drive(
        spec["label"],
        spec["serial"],
        spec["size_gb"],
        spec["mount_point"],
        spec["auth_file"],
        spec["vanishing"],
    )


def drive_spec(**over):
    """One drive's whole description, as plain values."""
    found = {
        "label": "CHIPKEY",
        "serial": PLAIN_SERIAL,
        "size_gb": 15.5,
        "mount_point": PLAIN_MOUNT,
        "auth_file": None,
        "vanishing": False,
    }
    found.update(over)
    return found


KEYED_DRIVE = drive_spec(
    label="BOLT",
    serial=SECOND_SERIAL,
    size_gb=3.25,
    mount_point=SECOND_MOUNT,
    auth_file=SECOND_MOUNT / surface.AUTH_FILENAME,
)


def exchange(**over):
    """One exchange row's stored values, as plain values."""
    found = {
        "exchange_id": PLAIN_ID,
        "display_name": PLAIN_NAME,
        "hardware_mode": False,
        "hw_volume_serial": "",
    }
    found.update(over)
    return found


def spec(**over):
    """One panel's whole input, as plain values.

    One spec builds two independent worlds, one per side. Nothing is
    shared between the sides, because the shipped panel edits the
    exchange rows it is given in place.
    """
    found = {
        "exchanges": (exchange(),),
        "drives": (drive_spec(),),
        "vault": VAULT,
        "answers": (),
        "verify_answer": True,
        "export_answer": (True, EXPORT_MESSAGE),
        "list_answer": None,
        "save_raises": None,
    }
    found.update(over)
    return found


CASES = {
    "happy": spec(),
    "empty": spec(
        exchanges=(exchange(exchange_id="", display_name=""),),
        drives=(drive_spec(label="", serial=""),),
    ),
    "zero": spec(drives=(drive_spec(size_gb=0.0, serial="0"),)),
    "negative": spec(drives=(drive_spec(size_gb=-250.75),)),
    "thousand_million": spec(drives=(drive_spec(size_gb=1_000_000_000.0),)),
    "one_billionth": spec(drives=(drive_spec(size_gb=0.000_000_001),)),
    "unicode": spec(
        exchanges=(exchange(display_name=UNICODE_TEXT),),
        drives=(drive_spec(label=UNICODE_TEXT, serial=UNICODE_TEXT),),
    ),
    "long_two_hundred": spec(
        exchanges=(exchange(display_name=LONG_TEXT, hw_volume_serial=LONG_TEXT),),
        drives=(drive_spec(label=LONG_TEXT, serial=LONG_TEXT),),
    ),
    "markup": spec(
        exchanges=(exchange(display_name=MARKUP_TEXT),),
        drives=(drive_spec(label=MARKUP_TEXT),),
    ),
    "apostrophe": spec(
        exchanges=(exchange(display_name=APOSTROPHE_TEXT),),
        drives=(drive_spec(label=APOSTROPHE_TEXT, serial=APOSTROPHE_TEXT),),
    ),
    "wrong_capitals": spec(
        exchanges=(exchange(exchange_id=LOWER_CASE_ID, display_name=""),),
    ),
    "newline": spec(
        exchanges=(exchange(display_name=NEWLINE_TEXT),),
        drives=(drive_spec(label=NEWLINE_TEXT),),
    ),
    "number_where_a_drive_name_belongs": spec(drives=(drive_spec(label=12),)),
    "infinity": spec(drives=(drive_spec(size_gb=float("inf")),)),
    "minus_infinity": spec(drives=(drive_spec(size_gb=float("-inf")),)),
    "not_a_number": spec(drives=(drive_spec(size_gb=float("nan")),)),
    "no_device": spec(drives=()),
    "no_exchanges": spec(exchanges=()),
    "no_vault": spec(vault=None),
    "key_present": spec(drives=(KEYED_DRIVE,)),
    "hardware_on_with_key": spec(
        exchanges=(exchange(hardware_mode=True, hw_volume_serial=PLAIN_SERIAL),),
    ),
    "hardware_on_no_key": spec(exchanges=(exchange(hardware_mode=True),)),
    "short_serial": spec(exchanges=(exchange(hw_volume_serial=SHORT_SERIAL),)),
    "two_exchanges": spec(
        exchanges=(
            exchange(),
            exchange(
                exchange_id=SECOND_ID,
                display_name="",
                hardware_mode=True,
                hw_volume_serial=SECOND_SERIAL,
            ),
        ),
    ),
    "two_drives": spec(drives=(drive_spec(), KEYED_DRIVE)),
    "two_of_each": spec(
        exchanges=(
            exchange(hw_volume_serial=PLAIN_SERIAL),
            exchange(
                exchange_id=SECOND_ID,
                display_name="",
                hardware_mode=True,
                hw_volume_serial=SECOND_SERIAL,
            ),
        ),
        drives=(drive_spec(), KEYED_DRIVE),
    ),
    "credential_wrong_shape": spec(export_answer=(False, "the vault held no keys")),
    "device_refuses": spec(export_answer=OSError("the drive refused the write")),
    "verify_fails": spec(drives=(KEYED_DRIVE,), verify_answer=False),
    "save_refuses": spec(save_raises=OSError("the settings file is read only")),
}

CASE_NAMES = tuple(sorted(CASES))

#: Specs whose drive stops answering part way through a read. These
#: refuse on both sides and are compared by the type of the refusal.
REFUSING_CASES = {
    "text_where_number": spec(drives=(drive_spec(size_gb="fifteen"),)),
    "mount_point_is_text": spec(drives=(drive_spec(mount_point="/invented/chip"),)),
    "device_stops_answering": spec(drives=(drive_spec(vanishing=True),)),
    "serial_is_a_number": spec(exchanges=(exchange(hw_volume_serial=7),)),
    "number_where_an_exchange_name_belongs": spec(
        exchanges=(exchange(display_name=12),),
    ),
    "exchange_id_is_a_number": spec(
        exchanges=(exchange(exchange_id=7, display_name=""),),
    ),
}


# The shared swap helper: neither side reaches a device or a file


class Recorder:
    """Everything one drive of one side reached for."""

    def __init__(self, answers=()):
        self.dialogs: list = []
        self.timers: list = []
        self.threads: list = []
        self.emitted: list = []
        self.verify_calls: list = []
        self.saves: list = []
        self.save_refusals: list = []
        self.answers = list(answers)
        self.clock_readers: list = []
        self.verify_answer = True
        self.export_answer: object = (True, EXPORT_MESSAGE)
        self.list_answer: object = None

    def next_answer(self):
        """The next scripted reply to a confirmation, or no."""
        return self.answers.pop(0) if self.answers else surface.NO


class Inner:
    """The inner settings object the shipped panel reaches through."""

    def __init__(self, exchanges):
        self.exchanges = exchanges


class Settings:
    """One side's own settings.

    Carries the exchange list under both the name the shipped panel
    reads and the name the surface reads, so one object serves both and
    neither side can see the other's edits.
    """

    def __init__(self, exchanges, record, save_raises=None):
        self.exchanges = [dict(one) for one in exchanges]
        self._settings = Inner(self.exchanges)
        self.record = record
        self.save_raises = save_raises

    def save(self):
        """Write the exchange list back, or raise what the spec scripted."""
        if self.save_raises is not None:
            self.record.save_refusals.append(type(self.save_raises).__name__)
            raise self.save_raises
        self.record.saves.append(True)


class ThreadStandIn:
    """A worker thread that records what was asked for and starts nothing."""

    def __init__(self, target=None, args=(), name=None, daemon=None):
        self.record = ThreadStandIn.record
        self.asked = [
            name,
            daemon,
            getattr(target, "__name__", "").lstrip("_"),
            len(args),
        ]

    def start(self):
        """Record the request. No thread is ever started."""
        self.record.threads.append(list(self.asked))


class ThreadModule:
    """The threading module the shipped panel reaches, with no real thread."""

    Thread = ThreadStandIn


class World:
    """The swapped message boxes, threads, timer and device functions.

    ``fresh`` hands out a NEW recorder rather than clearing the old one,
    so a field no reset knows about cannot carry into the next drive.
    """

    def __init__(self):
        self.current = Recorder()

    def fresh(self, one=None):
        """Point every swapped function at a new recorder for one spec."""
        found = Recorder((one or {}).get("answers", ()))
        if one is not None:
            found.verify_answer = one["verify_answer"]
            found.export_answer = one["export_answer"]
            found.list_answer = one["list_answer"]
        self.current = found
        ThreadStandIn.record = found
        return found


WORLD = World()


def clock_caller():
    """The file that asked for the time, one frame above the stand-in."""
    import traceback

    stack = traceback.extract_stack()
    return Path(stack[-3].filename).name


def frozen_clock(*_args, **_kwargs):
    """Return one fixed reading and record who asked for it."""
    WORLD.current.clock_readers.append(clock_caller())
    return FROZEN_SECONDS


def message_box(kind):
    """A message box that records its title and body instead of showing it."""

    def shown(_parent, title, body, *_rest, **_kwargs):
        WORLD.current.dialogs.append([kind, title, body])

    return shown


def question_box(_parent, title, body, *_rest, **_kwargs):
    """A confirmation that records itself and answers from the spec."""
    from PySide6.QtWidgets import QMessageBox

    WORLD.current.dialogs.append([surface.QUESTION, title, body])
    if WORLD.current.next_answer() == surface.YES:
        return QMessageBox.StandardButton.Yes
    return QMessageBox.StandardButton.No


def single_shot(delay_ms, target):
    """A timer request that is recorded and never runs."""
    WORLD.current.timers.append([delay_ms, getattr(target, "__name__", "")])


def listed_drives():
    """The drives the spec says are attached. No device is read."""
    answer = WORLD.current.list_answer
    if isinstance(answer, BaseException):
        raise answer
    return [] if answer is None else answer


def exported_credentials(_volume, _vault, _passphrase):
    """The export answer the spec scripted. Nothing is written."""
    answer = WORLD.current.export_answer
    if isinstance(answer, BaseException):
        raise answer
    return answer


def verified_auth_file(auth_file, serial):
    """The verify answer the spec scripted. No file is read."""
    WORLD.current.verify_calls.append([str(auth_file), serial])
    return WORLD.current.verify_answer


@pytest.fixture(autouse=True)
def swapped_world(monkeypatch):
    """Give this test its own message boxes, threads, timer and device.

    Every process-wide name the shipped panel reaches is swapped here and
    restored afterwards, whether the test passes, fails or refuses.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox

    for owner, name in (
        (shipped, "threading"),
        (core, "list_usb_volumes"),
        (core, "export_credentials_to_usb"),
        (core, "verify_auth_file"),
        (QTimer, "singleShot"),
    ):
        assert hasattr(owner, name), f"{owner!r} carries no {name}; this resets nothing"

    monkeypatch.setattr(shipped, "threading", ThreadModule)
    monkeypatch.setattr(core, "list_usb_volumes", listed_drives)
    monkeypatch.setattr(core, "export_credentials_to_usb", exported_credentials)
    monkeypatch.setattr(core, "verify_auth_file", verified_auth_file)
    monkeypatch.setattr(QTimer, "singleShot", staticmethod(single_shot))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(message_box("warning")))
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(message_box(surface.INFORMATION)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(message_box(surface.CRITICAL)),
    )
    monkeypatch.setattr(QMessageBox, "question", staticmethod(question_box))
    WORLD.fresh()
    yield WORLD
    surface.PANEL_MODEL = None


# Building each side from one spec


def old_panel(one):
    """The shipped panel, opened for one spec, with its own settings."""
    app()
    record = WORLD.fresh(one)
    settings = Settings(one["exchanges"], record, one["save_raises"])
    panel = hold(shipped.USBAuthWidget(settings, one["vault"], None))
    panel.hardware_mode_changed.connect(
        lambda *args: record.emitted.append(
            [surface.SIGNAL_HARDWARE_MODE_CHANGED, list(args)],
        ),
    )
    return panel, record, settings


def new_panel(one):
    """The surface's panel, built for one spec, with its own settings."""
    record = Recorder(one["answers"])
    record.verify_answer = one["verify_answer"]
    record.export_answer = one["export_answer"]
    record.list_answer = one["list_answer"]
    settings = Settings(one["exchanges"], record, one["save_raises"])
    model = surface.build_model(
        settings=settings,
        vault=one["vault"],
        list_volumes=lambda: scripted_list(record),
        export_credentials=lambda *args: scripted_export(record, *args),
        verify_auth_file=lambda path, serial: scripted_verify(record, path, serial),
        answers=list(one["answers"]),
        build_now=True,
    )
    return model, record, settings


def scripted_list(record):
    """The drives one spec says are attached, for the surface's worker."""
    answer = record.list_answer
    if isinstance(answer, BaseException):
        raise answer
    return [] if answer is None else answer


def scripted_export(record, _volume, _vault, _passphrase):
    """The export answer one spec scripted, for the surface's worker."""
    answer = record.export_answer
    if isinstance(answer, BaseException):
        raise answer
    return answer


def scripted_verify(record, path, serial):
    """The verify answer one spec scripted, for the surface's panel."""
    record.verify_calls.append([str(path), serial])
    return record.verify_answer


# Driving one step sequence through either side


def drives_for(one):
    """The drive objects one spec describes, built fresh."""
    return [drive(each) for each in one["drives"]]


def step_old(panel, one, step):
    """Take one step on the shipped panel."""
    name = step[0]
    if name == "refresh":
        panel._on_refresh()
    elif name == "scan_complete":
        panel._on_scan_complete(drives_for(one))
    elif name == "select":
        panel._drive_combo.setCurrentIndex(step[1])
    elif name == "export":
        panel._on_export()
    elif name == "export_complete":
        panel._on_export_complete(step[1], step[2])
    elif name == "verify":
        panel._on_verify()
    elif name == "toggle":
        row_toggle_old(panel, step[1])
    elif name == "set_vault":
        panel.set_vault(step[1])
    elif name == "refresh_exchanges":
        panel.refresh_exchanges()
    else:
        raise AssertionError(f"no step named {name}")


def step_new(model, one, step):
    """Take one step on the surface's panel."""
    name = step[0]
    if name == "refresh":
        model.on_refresh()
    elif name == "scan_complete":
        model.on_scan_complete(drives_for(one))
    elif name == "select":
        model.select(step[1])
    elif name == "export":
        model.on_export()
    elif name == "export_complete":
        model.on_export_complete(step[1], step[2])
    elif name == "verify":
        model.on_verify()
    elif name == "toggle":
        model.toggle_row(step[1], not model.rows[step[1]].toggle_checked)
    elif name == "set_vault":
        model.set_vault(step[1])
    elif name == "refresh_exchanges":
        model.refresh_exchanges()
    else:
        raise AssertionError(f"no step named {name}")


def row_toggle_old(panel, index):
    """Click one row's switch on the shipped panel.

    A click is what a press is. Emitting the signal by hand is
    refused by Qt and would drive a path no press takes.
    """
    old_rows(panel)[index].layout().itemAt(4).widget().click()


def run_old(one, steps):
    """Drive the shipped panel through `steps` and say where it stopped.

    Building the panel is the first thing that can refuse, so a
    refusal there is reported as step -1 rather than escaping.
    """
    try:
        panel, record, settings = old_panel(one)
    except Exception as refused:
        return None, WORLD.current, None, [*BUILD_REFUSED, type(refused).__name__]
    stop = walk(lambda step: step_old(panel, one, step), steps)
    return panel, record, settings, stop


def run_new(one, steps):
    """Drive the surface's panel through `steps` and say where it stopped."""
    try:
        model, record, settings = new_panel(one)
    except Exception as refused:
        return None, Recorder(), None, [*BUILD_REFUSED, type(refused).__name__]
    stop = walk(lambda step: step_new(model, one, step), steps)
    return model, record, settings, stop


def walk(take, steps):
    """Take each step until one refuses, and report where it stopped."""
    for index, step in enumerate(steps):
        try:
            take(step)
        except Exception as refused:
            return [index, step[0], type(refused).__name__]
    return [len(steps), "", ""]


BUILD_REFUSED = [-1, "build"]

SCAN = ("scan_complete",)
REFRESH = ("refresh",)
EXPORT = ("export",)
VERIFY = ("verify",)
DONE_OK = ("export_complete", True, EXPORT_MESSAGE)
DONE_BAD = ("export_complete", False, "the drive refused the write")

SEQUENCES = {
    "just_built": (),
    "one_scan": (SCAN,),
    "refresh_then_scan": (REFRESH, SCAN),
    "scan_then_export": (SCAN, EXPORT),
    "scan_export_done": (SCAN, EXPORT, DONE_OK),
    "scan_export_failed": (SCAN, EXPORT, DONE_BAD),
    "export_with_no_scan": (EXPORT,),
    "verify_with_no_scan": (VERIFY,),
    "scan_then_verify": (SCAN, VERIFY),
    "scan_select_second": (SCAN, ("select", 1)),
    "toggle_once": (("toggle", 0),),
    "toggle_twice": (("toggle", 0), ("toggle", 0)),
    "toggle_after_export": (SCAN, EXPORT, DONE_OK, ("toggle", 0)),
    "vault_arrives_late": (("set_vault", VAULT), SCAN, EXPORT),
    "rebuild_rows": (SCAN, ("refresh_exchanges",)),
    "two_scans": (SCAN, SCAN),
    "done_without_export": (SCAN, DONE_OK),
}

SEQUENCE_NAMES = tuple(sorted(SEQUENCES))


# Reading each side into one comparable shape


def old_parts(panel):
    """Every screen element of the shipped panel, found by layout order."""
    root = panel.layout()
    export_layout = root.itemAt(2).widget().layout()
    select_row = export_layout.itemAt(0).layout()
    button_row = export_layout.itemAt(2).layout()
    mode_layout = root.itemAt(3).widget().layout()
    return {
        "root": root,
        "header": root.itemAt(0).widget(),
        "description": root.itemAt(1).widget(),
        "export_group": root.itemAt(2).widget(),
        "mode_group": root.itemAt(3).widget(),
        "drive_label": select_row.itemAt(0).widget(),
        "combo": select_row.itemAt(1).widget(),
        "refresh": select_row.itemAt(2).widget(),
        "drive_info": export_layout.itemAt(1).widget(),
        "export": button_row.itemAt(0).widget(),
        "verify": button_row.itemAt(1).widget(),
        "progress": export_layout.itemAt(3).widget(),
        "status": export_layout.itemAt(4).widget(),
        "mode_description": mode_layout.itemAt(0).widget(),
        "scroll": mode_layout.itemAt(1).widget(),
    }


def old_rows(panel):
    """The exchange rows the shipped panel built, in order.

    A QLabel is itself a QFrame, so the note shown when there are no
    exchanges is excluded by its own class rather than by its base.
    """
    from PySide6.QtWidgets import QFrame, QLabel

    layout = old_parts(panel)["scroll"].widget().layout()
    found = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, QFrame) and not isinstance(widget, QLabel):
            found.append(widget)
    return found


def old_empty_label(panel):
    """The note the shipped panel shows when there are no exchanges."""
    from PySide6.QtWidgets import QLabel

    layout = old_parts(panel)["scroll"].widget().layout()
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, QLabel):
            return widget
    return None


def rows_layout_of(panel):
    """The layout the shipped panel puts its exchange rows in."""
    return old_parts(panel)["scroll"].widget().layout()


def rows_margins(panel):
    """The margins around the shipped panel's exchange rows."""
    found = rows_layout_of(panel).contentsMargins()
    return [found.left(), found.top(), found.right(), found.bottom()]


def read_old_row(row):
    """Every value one shipped exchange row shows."""
    layout = row.layout()
    name = layout.itemAt(0).widget()
    serial = layout.itemAt(1).widget()
    lamp = layout.itemAt(3).widget()
    toggle = layout.itemAt(4).widget()
    margins = layout.contentsMargins()
    return {
        "exchange_id": row.exchange_id,
        "accessible_name": row.accessibleName(),
        "style": row.styleSheet(),
        "margins_px": [
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        ],
        "name_text": name.text(),
        "name_style": name.styleSheet(),
        "serial_text": serial.text(),
        "serial_style": serial.styleSheet(),
        "lamp_tooltip": lamp.toolTip(),
        "lamp_size_px": [lamp.width(), lamp.height()],
        "toggle_text": toggle.text(),
        "toggle_checked": toggle.isChecked(),
        "toggle_checkable": toggle.isCheckable(),
        "toggle_width_px": toggle.width(),
        "toggle_style": toggle.styleSheet(),
    }


def read_new_row(row):
    """Every value one surface exchange row shows."""
    return {
        "exchange_id": row["exchange_id"],
        "accessible_name": row["accessible_name"],
        "style": row["style"],
        "margins_px": row["margins_px"],
        "name_text": row["name_text"],
        "name_style": row["name_style"],
        "serial_text": row["serial_text"],
        "serial_style": row["serial_style"],
        "lamp_tooltip": row["lamp"]["tooltip"],
        "lamp_size_px": row["lamp"]["size_px"],
        "toggle_text": row["toggle_text"],
        "toggle_checked": row["toggle_checked"],
        "toggle_checkable": row["toggle_checkable"],
        "toggle_width_px": row["toggle_width_px"],
        "toggle_style": row["toggle_style"],
    }


def only_panel_signal(emitted):
    """The panel's own emissions, in order.

    A row's own signal is emitted before the slot that answers it, and a
    recorder connected after the panel's own slot would see the two the
    other way about. The row signal is compared on a standalone row
    instead, by ``test_a_row_emits_the_same_signal_on_both_sides``.
    """
    return [one for one in emitted if one[0] == surface.SIGNAL_HARDWARE_MODE_CHANGED]


def read_old(panel, record, settings):
    """Every value the shipped panel shows, read off the built panel."""
    parts = old_parts(panel)
    combo = parts["combo"]
    margins = parts["root"].contentsMargins()
    empty = old_empty_label(panel)
    return {
        "accessible_name": panel.accessibleName(),
        "root_margins_px": [
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        ],
        "root_spacing_px": parts["root"].spacing(),
        "header_text": parts["header"].text(),
        "header_style": parts["header"].styleSheet(),
        "description_text": parts["description"].text(),
        "description_style": parts["description"].styleSheet(),
        "description_word_wrap": parts["description"].wordWrap(),
        "export_group_title": parts["export_group"].title(),
        "group_style": parts["export_group"].styleSheet(),
        "mode_group_style": parts["mode_group"].styleSheet(),
        "drive_label_text": parts["drive_label"].text(),
        "combo_items": [combo.itemText(one) for one in range(combo.count())],
        "combo_index": combo.currentIndex(),
        "combo_min_width_px": combo.minimumWidth(),
        "combo_style": combo.styleSheet(),
        "refresh_text": parts["refresh"].text(),
        "refresh_width_px": parts["refresh"].width(),
        "refresh_style": parts["refresh"].styleSheet(),
        "refresh_enabled": parts["refresh"].isEnabled(),
        "drive_info_text": parts["drive_info"].text(),
        "drive_info_style": parts["drive_info"].styleSheet(),
        "export_text": parts["export"].text(),
        "export_style": parts["export"].styleSheet(),
        "export_enabled": parts["export"].isEnabled(),
        "verify_text": parts["verify"].text(),
        "verify_width_px": parts["verify"].width(),
        "verify_style": parts["verify"].styleSheet(),
        "progress_visible": parts["progress"].isVisibleTo(panel),
        "progress_height_px": parts["progress"].height(),
        "progress_range": [parts["progress"].minimum(), parts["progress"].maximum()],
        "progress_text_visible": parts["progress"].isTextVisible(),
        "progress_style": parts["progress"].styleSheet(),
        "export_status_text": parts["status"].text(),
        "export_status_style": parts["status"].styleSheet(),
        "export_status_word_wrap": parts["status"].wordWrap(),
        "mode_group_title": parts["mode_group"].title(),
        "mode_description_text": parts["mode_description"].text(),
        "mode_description_style": parts["mode_description"].styleSheet(),
        "scroll_resizable": parts["scroll"].widgetResizable(),
        "scroll_max_height_px": parts["scroll"].maximumHeight(),
        "scroll_style": parts["scroll"].styleSheet(),
        "rows_margins_px": rows_margins(panel),
        "rows_spacing_px": rows_layout_of(panel).spacing(),
        "rows": [read_old_row(one) for one in old_rows(panel)],
        "empty_text": empty.text() if empty else "",
        "empty_style": empty.styleSheet() if empty else "",
        "exchanges": [dict(one) for one in settings.exchanges],
        "dialogs": [list(one) for one in record.dialogs],
        "emitted": only_panel_signal(record.emitted),
        "threads": [list(one) for one in record.threads],
        "timers": [list(one) for one in record.timers],
        "saves": len(record.saves),
        "save_refusals": list(record.save_refusals),
        "verify_calls": [list(one) for one in record.verify_calls],
    }


def read_new(model, record, settings):
    """Every value the surface's panel shows, read off its payload."""
    payload = surface.build_view_model(model)
    return {
        "accessible_name": payload["accessible_name"],
        "root_margins_px": payload["root_margins_px"],
        "root_spacing_px": payload["root_spacing_px"],
        "header_text": payload["header_text"],
        "header_style": payload["header_style"],
        "description_text": payload["description_text"],
        "description_style": payload["description_style"],
        "description_word_wrap": True,
        "export_group_title": payload["export_group_title"],
        "group_style": payload["group_style"],
        "mode_group_style": payload["group_style"],
        "drive_label_text": payload["drive_label_text"],
        "combo_items": payload["combo_items"],
        "combo_index": payload["combo_index"],
        "combo_min_width_px": payload["combo_min_width_px"],
        "combo_style": payload["combo_style"],
        "refresh_text": payload["refresh_text"],
        "refresh_width_px": payload["refresh_width_px"],
        "refresh_style": payload["refresh_style"],
        "refresh_enabled": payload["refresh_enabled"],
        "drive_info_text": payload["drive_info_text"],
        "drive_info_style": payload["drive_info_style"],
        "export_text": payload["export_text"],
        "export_style": payload["export_style"],
        "export_enabled": payload["export_enabled"],
        "verify_text": payload["verify_text"],
        "verify_width_px": payload["verify_width_px"],
        "verify_style": payload["verify_style"],
        "progress_visible": payload["progress_visible"],
        "progress_height_px": payload["progress_height_px"],
        "progress_range": payload["progress_range"],
        "progress_text_visible": payload["progress_text_visible"],
        "progress_style": payload["progress_style"],
        "export_status_text": payload["export_status_text"],
        "export_status_style": payload["export_status_style"],
        "export_status_word_wrap": True,
        "mode_group_title": payload["mode_group_title"],
        "mode_description_text": payload["mode_description_text"],
        "mode_description_style": payload["mode_description_style"],
        "scroll_resizable": payload["scroll_resizable"],
        "scroll_max_height_px": payload["scroll_max_height_px"],
        "scroll_style": payload["scroll_style"],
        "rows_margins_px": payload["rows_margins_px"],
        "rows_spacing_px": payload["rows_spacing_px"],
        "rows": [read_new_row(one) for one in payload["rows"]],
        "empty_text": payload["empty_text"],
        "empty_style": payload["empty_style"],
        "exchanges": payload["exchanges"],
        "dialogs": payload["dialogs"],
        "emitted": only_panel_signal(payload["emitted"]),
        "threads": payload["threads"],
        "timers": payload["timers"],
        "saves": payload["saves"],
        "save_refusals": payload["save_refusals"],
        "verify_calls": payload["verify_calls"],
    }


def numbered(value):
    """One number as its own text, so a whole number and a decimal differ.

    ``12`` and ``12.0`` compare equal and hash apart, and a not-a-number
    is never equal to itself, so both are read as text before any
    comparison.
    """
    if isinstance(value, bool):
        return f"bool:{value}"
    if isinstance(value, float):
        if math.isnan(value):
            return "float:nan"
        return "float:%r" % value
    if isinstance(value, int):
        return f"int:{value:d}"
    return value


def readable(value):
    """One value as nested text, ordered so a swap changes it."""
    if isinstance(value, dict):
        return [
            [readable(key), readable(item)]
            for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))
        ]
    if isinstance(value, (list, tuple)):
        return [readable(item) for item in value]
    return repr(numbered(value))


def digest(reading):
    """SHA-256 over every value one side reported, at every depth."""
    return hashlib.sha256(
        json.dumps(
            {key: readable(value) for key, value in sorted(reading.items())},
        ).encode("utf-8"),
    ).hexdigest()


def both_sides_agree(name, steps=(), note=""):
    """Fail unless the two sides report one value, one hash and one stop."""
    one = CASES[name]
    panel, old_record, old_settings, old_stop = run_old(one, steps)
    model, new_record, new_settings, new_stop = run_new(one, steps)
    old_side = read_old(panel, old_record, old_settings)
    new_side = read_new(model, new_record, new_settings)
    assert set(old_side) == set(new_side), sorted(set(old_side) ^ set(new_side))
    assert old_stop == new_stop, f"{name}: old stopped {old_stop}, new {new_stop}"
    differences = [
        key
        for key in sorted(old_side)
        if readable(old_side[key]) != readable(new_side[key])
    ]
    assert differences == [], "%s%s: old %r new %r" % (
        name,
        " " + note if note else "",
        {key: old_side[key] for key in differences},
        {key: new_side[key] for key in differences},
    )
    assert digest(old_side) == digest(new_side), name
    return old_side, new_side


# Both sides, value for value and by hash


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_panel_is_the_shipped_panel(name):
    """The surface reports a different panel than the shipped one."""
    both_sides_agree(name)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_a_full_export_run_reaches_the_same_place_on_both_sides(name):
    """A scan, an export and its answer went differently on the two sides."""
    both_sides_agree(name, (SCAN, EXPORT, DONE_OK), "scan, export, done")


@pytest.mark.parametrize("name", SEQUENCE_NAMES)
def test_one_step_sequence_leaves_both_sides_in_one_state(name):
    """A step sequence left the two sides holding different values."""
    both_sides_agree("two_of_each", SEQUENCES[name], name)


def test_every_case_in_the_table_is_driven():
    """A case sits in the table and no test ever drives it."""
    assert undriven(CASES, CASE_NAMES) == []
    assert undriven(SEQUENCES, SEQUENCE_NAMES) == []
    for name in REFUSING_CASES:
        assert name not in CASES, name


def undriven(table, driven):
    """Every name in one table that no run drives."""
    return sorted(set(table) - set(driven))


def test_the_coverage_check_reports_a_case_no_run_drives():
    """The coverage check passes whatever a table grows."""
    assert undriven(CASES, CASE_NAMES) == []
    assert undriven(dict(CASES, a_case_no_run_drives=None), CASE_NAMES) == [
        "a_case_no_run_drives",
    ]
    assert undriven(SEQUENCES, ()) == sorted(SEQUENCES)


def test_the_sample_hashes_are_reported():
    """The hash reader answers nothing, so a hash comparison means nothing."""
    samples = {}
    for name in CASE_NAMES:
        model, record, settings = new_panel(CASES[name])
        samples[name] = digest(read_new(model, record, settings))
    assert all(len(one) == 64 for one in samples.values()), samples
    assert len(set(samples.values())) > 1, samples
    reported = {name: samples[name][:12] for name in sorted(samples)}
    assert len(reported) == len(CASES), reported


def test_two_genuinely_different_real_inputs_hash_apart():
    """The hash gives one answer whatever it is given."""
    old_happy = digest(read_old(*drive_old_side("happy")))
    new_keyed = digest(read_new(*drive_new_side("key_present")))
    assert old_happy != new_keyed
    new_happy = digest(read_new(*drive_new_side("happy")))
    old_keyed = digest(read_old(*drive_old_side("key_present")))
    assert new_happy != old_keyed
    assert old_happy == new_happy
    assert old_keyed == new_keyed


def drive_old_side(name, steps=(SCAN,)):
    """The shipped panel driven through `steps`, ready to read."""
    panel, record, settings, _stop = run_old(CASES[name], steps)
    return panel, record, settings


def drive_new_side(name, steps=(SCAN,)):
    """The surface's panel driven through `steps`, ready to read."""
    model, record, settings, _stop = run_new(CASES[name], steps)
    return model, record, settings


def test_the_same_input_hashes_the_same_twice():
    """The hash moves between two readings of one input."""
    assert digest(read_new(*drive_new_side("happy"))) == digest(
        read_new(*drive_new_side("happy")),
    )
    assert digest(read_old(*drive_old_side("happy"))) == digest(
        read_old(*drive_old_side("happy")),
    )


def test_a_whole_number_and_a_decimal_are_told_apart():
    """A whole number and a decimal compare equal, so a change is invisible."""
    assert 12 == 12.0
    assert readable(12) != readable(12.0)
    assert readable(True) != readable(1)


def test_a_not_a_number_is_read_as_its_own_text():
    """A not-a-number never equals itself, so it reads as a difference."""
    assert float("nan") != float("nan")
    assert readable(float("nan")) == readable(float("nan"))
    assert readable(float("inf")) != readable(float("-inf"))


def test_a_swap_of_two_values_changes_the_reading():
    """The reader keeps no order, so a swapped pair reads as unchanged."""
    first = {"a": [1, 2]}
    second = {"a": [2, 1]}
    assert readable(first) != readable(second)
    assert digest(first) != digest(second)


# Every failure path, compared by the type of the refusal


@pytest.mark.parametrize("name", tuple(sorted(REFUSING_CASES)))
def test_a_refusing_drive_stops_both_sides_at_the_same_step(name):
    """One side carried on where the other refused."""
    one = REFUSING_CASES[name]
    _panel, _old_record, _old_settings, old_stop = run_old(one, (SCAN, EXPORT))
    _model, _new_record, _new_settings, new_stop = run_new(one, (SCAN, EXPORT))
    assert old_stop == new_stop, f"{name}: old {old_stop}, new {new_stop}"
    assert old_stop[2] != "", f"{name} refused nowhere: {old_stop}"


def test_every_refusing_case_in_the_table_is_driven():
    """A refusing case sits in the table and no test drives it."""
    assert undriven(REFUSING_CASES, tuple(sorted(REFUSING_CASES))) == []


def test_the_stop_check_reports_two_different_stops():
    """The stop comparison passes whatever the two sides did."""
    _panel, _r, _s, refusing = run_old(REFUSING_CASES["text_where_number"], (SCAN,))
    _model, _r2, _s2, clean = run_new(CASES["happy"], (SCAN,))
    assert refusing != clean, (refusing, clean)
    assert refusing[2] == "ValueError", refusing
    assert clean == [1, "", ""], clean


def test_a_refusal_is_compared_by_type_and_not_by_wording():
    """The refusal wording is pinned, which moves between Python versions."""
    reading = walk(_raising_step, (("one",), ("two",)))
    assert reading[2] == "ValueError"
    assert "fifteen" not in json.dumps(reading)


def _raising_step(_step):
    """A step that always refuses, for the stop reader's own control."""
    raise ValueError("this wording is never compared")


def test_the_shipped_panel_and_the_surface_refuse_a_drive_that_stops():
    """A drive that stops answering left one side holding a half-drawn list."""
    one = REFUSING_CASES["device_stops_answering"]
    _panel, _r, _s, old_stop = run_old(one, (SCAN,))
    _model, _r2, _s2, new_stop = run_new(one, (SCAN,))
    assert old_stop[2] == "OSError", old_stop
    assert old_stop == new_stop


# The worker, the row and the lamp, each on its own


def old_worker():
    """One shipped worker with recorders on its two live signals."""
    app()
    worker = shipped._USBWorker()
    record = WORLD.current
    worker.scan_complete.connect(
        lambda found: record.emitted.append(
            [surface.SIGNAL_SCAN_COMPLETE, list(found)],
        ),
    )
    worker.export_complete.connect(
        lambda done, message: record.emitted.append(
            [surface.SIGNAL_EXPORT_COMPLETE, [done, message]],
        ),
    )
    return worker, record


def new_worker(record):
    """One surface worker reading the same scripted answers."""
    return surface.UsbWorkerModel(
        list_volumes=lambda: scripted_list(record),
        export_credentials=lambda *args: scripted_export(record, *args),
    )


WORKER_RUNS = {
    "scan_finds_none": ("scan", None),
    "scan_finds_one": ("scan", "one drive"),
    "scan_refuses": ("scan", OSError("no drive bus")),
    "export_succeeds": ("export", (True, EXPORT_MESSAGE)),
    "export_fails": ("export", (False, "the vault held no keys")),
    "export_refuses": ("export", OSError("the drive refused the write")),
}

WORKER_RUN_NAMES = tuple(sorted(WORKER_RUNS))


@pytest.mark.parametrize("name", WORKER_RUN_NAMES)
def test_the_worker_reports_the_same_answer_on_both_sides(name):
    """The worker turned one answer into two different signals."""
    kind, answer = WORKER_RUNS[name]
    old_record = WORLD.fresh(CASES["happy"])
    prepare(old_record, kind, answer)
    worker, _record = old_worker()
    if kind == "scan":
        worker._do_scan()
    else:
        worker._do_export(drive(drive_spec()), VAULT, "")
    new_record = Recorder()
    prepare(new_record, kind, answer)
    model = new_worker(new_record)
    if kind == "scan":
        model.do_scan()
    else:
        model.do_export(drive(drive_spec()), VAULT, "")
    assert readable(shaped(old_record.emitted)) == readable(
        shaped(model.emitted),
    ), (old_record.emitted, model.emitted)


def prepare(record, kind, answer):
    """Point one recorder at the scripted answer for one worker run."""
    if kind == "scan":
        record.list_answer = answer if answer != "one drive" else [drive(drive_spec())]
    else:
        record.export_answer = answer


def shaped(emitted):
    """One emission list with each drive reduced to its serial."""
    found = []
    for name, payload in emitted:
        if name == surface.SIGNAL_SCAN_COMPLETE:
            found.append([name, [one.serial for one in payload]])
        else:
            found.append([name, list(payload)])
    return found


def test_every_worker_run_in_the_table_is_driven():
    """A worker run sits in the table and no test drives it."""
    assert undriven(WORKER_RUNS, WORKER_RUN_NAMES) == []


def test_the_worker_check_reports_two_different_answers():
    """The worker comparison passes whatever the two sides emitted."""
    first = Recorder()
    prepare(first, "export", (True, EXPORT_MESSAGE))
    second = Recorder()
    prepare(second, "export", (False, "no"))
    one = new_worker(first)
    other = new_worker(second)
    one.do_export(drive(drive_spec()), VAULT, "")
    other.do_export(drive(drive_spec()), VAULT, "")
    assert readable(shaped(one.emitted)) != readable(shaped(other.emitted))


def test_the_shipped_panel_reads_each_drive_more_often_than_the_surface():
    """One scan reads each drive a different number of times.

    The shipped panel redraws the line under the picker twice: once
    from the picker's own change signal while the list is being
    filled, and once when the fill is done. The surface redraws it
    once. A drive that refuses part way therefore refuses inside a
    signal on the shipped side, where Qt catches it and the panel
    carries on with a half-drawn line.
    """
    old_drive = drive(drive_spec())
    panel, _record, _settings = old_panel(CASES["happy"])
    panel._on_scan_complete([old_drive])
    new_drive = drive(drive_spec())
    model, _record2, _settings2 = new_panel(CASES["happy"])
    model.on_scan_complete([new_drive])
    assert old_drive.reads == 3, old_drive.reads
    assert new_drive.reads == 2, new_drive.reads


def test_the_picker_clears_its_choice_for_an_index_it_does_not_hold():
    """An index the picker does not hold leaves the old choice standing."""
    for ask in (-5, -1, 1, 99):
        panel, _record, _settings, _stop = run_old(CASES["happy"], (SCAN,))
        model, _r, _s, _stop2 = run_new(CASES["happy"], (SCAN,))
        old_parts(panel)["combo"].setCurrentIndex(ask)
        model.select(ask)
        assert old_parts(panel)["combo"].currentIndex() == -1, ask
        assert model.combo_index == -1, ask
        assert model.selected_volume() is None, ask


def test_the_worker_asks_for_the_same_thread_on_both_sides():
    """The two sides asked the operating system for different work."""
    record = WORLD.fresh(CASES["happy"])
    worker, _record = old_worker()
    worker.scan()
    worker.export(drive(drive_spec()), VAULT, surface.EMPTY_PHRASE)
    model = new_worker(Recorder())
    model.scan()
    model.export(drive(drive_spec()), VAULT, surface.EMPTY_PHRASE)
    assert record.threads == model.threads, (record.threads, model.threads)
    assert record.threads == [
        [surface.SCAN_THREAD_NAME, True, "do_scan", 0],
        [surface.EXPORT_THREAD_NAME, True, "do_export", 3],
    ], record.threads


def test_no_worker_thread_outlives_this_test():
    """A real worker thread ran, and it can reach a device.

    The thread stand-in records the request and starts nothing, so the
    count of live threads cannot move.
    """
    import threading

    before = threading.active_count()
    record = WORLD.fresh(CASES["happy"])
    worker, _record = old_worker()
    worker.scan()
    worker.export(drive(drive_spec()), VAULT, surface.EMPTY_PHRASE)
    assert threading.active_count() == before
    assert len(record.threads) == 2
    assert shipped.threading is ThreadModule


#: One click, and the state it reaches. Each run starts at the
#: opposite state, so one click is what takes it there.
ROW_RUNS = {
    "on_with_key": (True, PLAIN_SERIAL),
    "on_with_no_key": (True, ""),
    "off_with_key": (False, PLAIN_SERIAL),
    "off_with_no_key": (False, ""),
}

ROW_RUN_NAMES = tuple(sorted(ROW_RUNS))


@pytest.mark.parametrize("name", ROW_RUN_NAMES)
def test_a_row_emits_the_same_signal_on_both_sides(name):
    """A row's own switch reached the panel differently on the two sides."""
    checked, serial = ROW_RUNS[name]
    hardware_mode = not checked
    app()
    record = WORLD.fresh(CASES["happy"])
    row = hold(
        shipped._ExchangeHWRow(PLAIN_ID, PLAIN_NAME, hardware_mode, serial, None),
    )
    row.mode_changed.connect(
        lambda one, flag: record.emitted.append(
            [surface.SIGNAL_MODE_CHANGED, [one, flag]],
        ),
    )
    row.layout().itemAt(4).widget().click()
    model = surface.ExchangeHwRowModel(
        exchange_id=PLAIN_ID,
        display_name=PLAIN_NAME,
        hardware_mode=hardware_mode,
        volume_serial=serial,
    )
    model.toggle(checked)
    assert record.emitted == model.emitted, (record.emitted, model.emitted)
    assert record.dialogs == model.dialogs, (record.dialogs, model.dialogs)
    assert readable(read_old_row(row)) == readable(
        read_new_row(model.build_view_model()),
    )


def test_every_row_run_in_the_table_is_driven():
    """A row run sits in the table and no test drives it."""
    assert undriven(ROW_RUNS, ROW_RUN_NAMES) == []


def test_the_row_check_reports_two_different_presses():
    """The row comparison passes whatever the switch did."""
    first = surface.ExchangeHwRowModel(volume_serial=PLAIN_SERIAL)
    second = surface.ExchangeHwRowModel(volume_serial=PLAIN_SERIAL)
    first.toggle(True)
    second.toggle(False)
    assert readable(first.build_view_model()) != readable(second.build_view_model())


def test_a_row_told_a_new_serial_shows_it():
    """The row keeps the old key line after a new key is assigned."""
    app()
    row = hold(shipped._ExchangeHWRow(PLAIN_ID, PLAIN_NAME, False, "", None))
    model = surface.ExchangeHwRowModel(exchange_id=PLAIN_ID, display_name=PLAIN_NAME)
    for serial in ("", SHORT_SERIAL, PLAIN_SERIAL, LONG_TEXT):
        row.update_serial(serial)
        model.update_serial(serial)
        assert row.layout().itemAt(1).widget().text() == model.serial_text, serial


LAMP_RUNS = ("inactive", "present", "missing", "melting", "")


@pytest.mark.parametrize("state", LAMP_RUNS)
def test_the_lamp_shows_the_same_hover_text_on_both_sides(state):
    """The lamp's hover text moved on one side only."""
    app()
    lamp = hold(shipped.USBStatusIndicator())
    model = surface.UsbStatusIndicatorModel()
    for label in ("", PLAIN_ID, UNICODE_TEXT):
        lamp.set_state(state, label)
        model.set_state(state, label)
        assert lamp.toolTip() == model.tooltip, (state, label)


def test_the_lamp_starts_the_same_on_both_sides():
    """The lamp opens showing a different state than the shipped one."""
    app()
    lamp = hold(shipped.USBStatusIndicator())
    model = surface.UsbStatusIndicatorModel()
    assert lamp.toolTip() == model.tooltip == surface.LAMP_START_TOOLTIP
    assert [lamp.width(), lamp.height()] == list(model.size_px)


def test_the_lamp_counts_every_state_it_was_given():
    """The lamp's repaint count does not move when its state moves."""
    model = surface.UsbStatusIndicatorModel()
    assert model.updates == 0
    model.set_state(surface.STATE_PRESENT)
    model.set_state(surface.STATE_PRESENT)
    assert model.updates == 2


def test_the_lamp_paint_carries_the_darkening_as_the_request():
    """The lamp asks for a darkened pen, so the renderer cannot apply it."""
    model = surface.UsbStatusIndicatorModel()
    model.set_state(surface.STATE_PRESENT)
    steps = model.paint()
    assert steps[0] == ["antialiasing", True]
    assert steps[1] == [
        surface.UNLOCKED,
        surface.LAMP_PEN_DARKER_PCT,
        surface.LAMP_PEN_WIDTH_PX,
    ][:0] + ["pen", surface.UNLOCKED, surface.LAMP_PEN_DARKER_PCT, 1]
    assert steps[2] == ["brush", surface.UNLOCKED]
    assert steps[3] == ["ellipse", [3, 3, 16, 16]]


# Counting what the shipped file wires, waits on and builds


def declared_classes(module):
    """Every class one imported module declares."""
    import inspect

    return {
        name
        for name, value in vars(module).items()
        if inspect.isclass(value) and value.__module__ == module.__name__
    }


def _is_method(value):
    """True for a plain, static or class method as vars reports it."""
    import inspect

    unwrapped = getattr(value, "__func__", value)
    return inspect.isfunction(unwrapped)


def declared_methods(module):
    """Every method the classes of one module declare, as class dot name."""
    return {
        f"{owner}.{name}"
        for owner in declared_classes(module)
        for name, value in vars(getattr(module, owner)).items()
        if _is_method(value)
    }


def declared_functions(module):
    """Every function one imported module declares."""
    import inspect

    return {
        name
        for name, value in vars(module).items()
        if inspect.isfunction(value) and value.__module__ == module.__name__
    }


#: One action name to the widget that carries it and the signal it wires,
#: written out so the count below is a shape this file chose to pin.
WIRED_SIGNALS = {
    "row_toggle": ("row._toggle_btn", "clicked"),
    "worker_scan_complete": ("panel._worker", "scan_complete"),
    "worker_export_complete": ("panel._worker", "export_complete"),
    "refresh_button": ("panel._refresh_btn", "clicked"),
    "drive_combo_changed": ("panel._drive_combo", "currentIndexChanged"),
    "export_button": ("panel._export_btn", "clicked"),
    "verify_button": ("panel._verify_btn", "clicked"),
    "row_mode_changed": ("row", "mode_changed"),
}


def _signal_signature(owner, name):
    """The SIGNAL() string for one named signal on one live object."""
    meta = owner.metaObject()
    for index in range(meta.methodCount()):
        signature = bytes(meta.method(index).methodSignature()).decode("utf-8")
        if signature.split("(")[0] == name:
            return "2" + signature
    raise AssertionError(f"{type(owner).__name__} declares no signal {name!r}")


def _wired_owner(panel, name):
    """The object one WIRED_SIGNALS entry names, off a built panel."""
    rows = old_rows(panel)
    assert rows, "the panel built no exchange row"
    row = rows[0]
    parts = name.split(".")
    found = {"panel": panel, "row": row}[parts[0]]
    for part in parts[1:]:
        found = getattr(found, part)
    return found


def test_the_panel_wires_eight_actions_and_the_surface_names_eight():
    """Every action the surface names is one live receiver on the panel."""
    panel, _record, _settings = drive_old_side("happy")
    assert set(WIRED_SIGNALS) == set(surface.ACTIONS)
    live = {}
    for action, (owner_name, signal) in WIRED_SIGNALS.items():
        owner = _wired_owner(panel, owner_name)
        live[action] = owner.receivers(_signal_signature(owner, signal))
    assert live == dict.fromkeys(WIRED_SIGNALS, 1), live
    assert sum(live.values()) == WIDGET_CONNECT_SITES == 8
    for name in surface.ACTIONS.values():
        assert callable(getattr(surface.UsbAuthWidgetModel, name)), name


def test_an_unwired_button_carries_no_receiver():
    """POSITIVE CONTROL for the count above: a bare button reports zero
    on the same reader."""
    from PySide6.QtWidgets import QPushButton

    app()
    assert QPushButton("bare").receivers("2clicked()") == 0


def _waits_during_a_build():
    """Every wait the shipped panel asks for while it opens."""
    from PySide6.QtCore import QTimer

    app()
    asked: list = []
    original_single_shot = QTimer.singleShot
    original_start = QTimer.start

    def watch_single_shot(delay_ms, *args, **kwargs):
        asked.append(("singleShot", delay_ms))
        del args, kwargs

    def watch_start(self, *args, **kwargs):
        asked.append(("start", args))
        return original_start(self, *args, **kwargs)

    QTimer.singleShot = watch_single_shot
    QTimer.start = watch_start
    try:
        old_panel(CASES["happy"])
        observed = list(asked)
        asked.clear()
        QTimer.singleShot(400, lambda: None)
    finally:
        QTimer.singleShot = original_single_shot
        QTimer.start = original_start
    return observed, asked


def test_the_panel_asks_for_one_wait_while_it_opens():
    """The panel schedules its auto-scan and starts no repeating timer."""
    observed, control = _waits_during_a_build()
    assert control == [("singleShot", 400)], "the wait watcher is blind"
    assert observed == [("singleShot", surface.SCAN_DELAY_MS)], observed
    assert len(surface.TIMERS) == len(observed) == WIDGET_TIMER_SITES == 1
    assert surface.TIMER_DELAYS_MS == (surface.SCAN_DELAY_MS,)


def test_the_panel_declares_five_signals_and_the_surface_names_five():
    """A signal declaration appeared on one side and not the other."""
    from PySide6.QtCore import Signal

    app()
    owners = (shipped._USBWorker, shipped._ExchangeHWRow, shipped.USBAuthWidget)
    declared = {
        name
        for owner in owners
        for name, value in vars(owner).items()
        if isinstance(value, Signal)
    }
    assert declared == {
        "scan_complete",
        "export_complete",
        "verify_complete",
        "mode_changed",
        "hardware_mode_changed",
    }, sorted(declared)
    assert len(surface.SIGNALS) == len(declared) == WIDGET_SIGNAL_BUILDS == 5
    for name in declared:
        assert name in surface.SIGNALS, name


def test_the_signal_reader_names_nothing_on_a_class_with_no_signal():
    """POSITIVE CONTROL: the same reader is empty for a plain class."""
    from PySide6.QtCore import Signal

    class _Plain:
        pass

    assert [
        name for name, value in vars(_Plain).items() if isinstance(value, Signal)
    ] == []


class _RecordingBus:
    """A bus that records every topic subscribed and emitted on it."""

    def __init__(self):
        self.subscribed: list[str] = []
        self.emitted: list[str] = []

    def subscribe(self, topic, handler):
        self.subscribed.append(topic)
        del handler
        return lambda: None

    def emit(self, topic, **kwargs):
        self.emitted.append(topic)
        del kwargs


def test_the_panel_subscribes_to_no_bus_topic(monkeypatch):
    """Opening the panel takes no topic on the process-wide bus."""
    from src.core import event_bus

    bus = _RecordingBus()
    monkeypatch.setattr(event_bus, "get_event_bus", lambda: bus)
    drive_old_side("happy")
    assert bus.subscribed == []
    assert bus.emitted == []
    assert surface.BUS_TOPICS == ()


def test_the_bus_recorder_sees_a_subscription():
    """POSITIVE CONTROL: the same recorder reports a topic when one is
    taken, so the empty list above is a fact about the panel."""
    bus = _RecordingBus()
    bus.subscribe("wire.created", lambda _event: None)
    assert bus.subscribed == ["wire.created"]


def test_the_panel_starts_two_threads_and_the_surface_names_two():
    """The scan and the export each run on their own named worker.

    Opening the panel asks for none, so the two names below come from the
    two calls and not from the build.
    """
    panel, record, _settings = drive_old_side("happy")
    assert record.threads == [], record.threads
    panel._worker.scan()
    panel._worker.export(None, None, None)
    started = [asked[0] for asked in record.threads]
    assert started == [surface.SCAN_THREAD_NAME, surface.EXPORT_THREAD_NAME], started
    assert len(started) == len(surface.THREADS) == WIDGET_THREAD_BUILDS == 2
    assert set(surface.THREADS) == set(started)
    assert all(asked[1] is True for asked in record.threads), record.threads


def test_the_panel_builds_the_screen_elements_it_shows():
    """The opened panel carries its own row, buttons and combo."""
    from PySide6.QtWidgets import QComboBox, QPushButton, QWidget

    panel, _record, _settings = drive_old_side("happy")
    assert isinstance(panel, QWidget)
    assert panel.findChild(shipped._ExchangeHWRow) is not None
    assert panel.findChild(shipped.USBStatusIndicator) is not None
    assert len(panel.findChildren(QPushButton)) >= 3
    assert len(panel.findChildren(QComboBox)) >= 1
    bare = QWidget()
    assert bare.findChildren(QPushButton) == [], "the child reader is blind"


def test_the_shipped_file_declares_twenty_five_methods_and_no_function():
    """A method appeared on one side and not the other."""
    assert len(declared_methods(shipped)) == WIDGET_METHODS == 25
    assert len(declared_functions(shipped)) == WIDGET_MODULE_FUNCTIONS == 0
    assert declared_methods(surface), "the method reader reports nothing at all"


# Every class and every method has a counterpart


def members(owner):
    """Every method, factory and read-only value a class declares, by name.

    A signal is callable and is not a method, so it is excluded by name.
    A read-only value is not callable at all, so asking ``callable``
    alone misses it.
    """
    import inspect

    from PySide6.QtCore import Signal

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if isinstance(value, Signal):
            continue
        if inspect.isfunction(value) or isinstance(
            value,
            (property, classmethod, staticmethod),
        ):
            found.add(name)
    return found


def test_the_member_counter_excludes_a_signal_and_finds_both_quiet_shapes():
    """The counter counts a signal, or misses a factory or a read-only value."""
    from PySide6.QtCore import Signal

    from src.gui import indicator_panel, launcher

    app()
    panel = indicator_panel.IndicatorVotingPanel
    assert callable(Signal())
    assert isinstance(vars(launcher.ModeCard)["clicked"], Signal)
    assert "clicked" not in members(launcher.ModeCard)
    assert "__init__" in members(launcher.ModeCard)
    assert isinstance(vars(panel)["_reading_fingerprint"], staticmethod)
    assert "_reading_fingerprint" in members(panel)
    assert isinstance(vars(panel)["lock_timeframe"], property)
    assert not callable(vars(panel)["lock_timeframe"])
    assert "lock_timeframe" in members(panel)
    assert isinstance(vars(panel)["selected_bot_id"], property)
    assert "selected_bot_id" in members(panel)
    assert isinstance(vars(shipped.USBAuthWidget)["_btn_style"], staticmethod)
    assert "_btn_style" in members(shipped.USBAuthWidget)
    for name in surface.SIGNALS:
        for owner in (
            shipped.USBAuthWidget,
            shipped._ExchangeHWRow,
            shipped._USBWorker,
        ):
            assert name not in members(owner), name


CLASS_MAP = {
    "USBAuthWidget": "UsbAuthWidgetModel",
    "USBStatusIndicator": "UsbStatusIndicatorModel",
    "_ExchangeHWRow": "ExchangeHwRowModel",
    "_USBWorker": "UsbWorkerModel",
}

METHOD_MAP = {
    "USBAuthWidget.__init__": "UsbAuthWidgetModel.__init__",
    "USBAuthWidget._build_ui": "UsbAuthWidgetModel.build",
    "USBAuthWidget._rebuild_exchange_rows": (
        "UsbAuthWidgetModel.rebuild_exchange_rows"
    ),
    "USBAuthWidget._on_mode_changed": "UsbAuthWidgetModel.on_mode_changed",
    "USBAuthWidget._on_refresh": "UsbAuthWidgetModel.on_refresh",
    "USBAuthWidget._on_scan_complete": "UsbAuthWidgetModel.on_scan_complete",
    "USBAuthWidget._update_drive_info": "UsbAuthWidgetModel.update_drive_info",
    "USBAuthWidget._selected_volume": "UsbAuthWidgetModel.selected_volume",
    "USBAuthWidget._on_export": "UsbAuthWidgetModel.on_export",
    "USBAuthWidget._on_export_complete": "UsbAuthWidgetModel.on_export_complete",
    "USBAuthWidget._on_verify": "UsbAuthWidgetModel.on_verify",
    "USBAuthWidget._btn_style": "button_style",
    "USBAuthWidget.set_vault": "UsbAuthWidgetModel.set_vault",
    "USBAuthWidget.refresh_exchanges": "UsbAuthWidgetModel.refresh_exchanges",
    "USBStatusIndicator.__init__": "UsbStatusIndicatorModel.__init__",
    "USBStatusIndicator.set_state": "UsbStatusIndicatorModel.set_state",
    "USBStatusIndicator.paintEvent": "UsbStatusIndicatorModel.paint",
    "_ExchangeHWRow.__init__": "ExchangeHwRowModel.__init__",
    "_ExchangeHWRow._apply_toggle_style": "ExchangeHwRowModel.apply_toggle_style",
    "_ExchangeHWRow._on_toggle": "ExchangeHwRowModel.toggle",
    "_ExchangeHWRow.update_serial": "ExchangeHwRowModel.update_serial",
    "_USBWorker.scan": "UsbWorkerModel.scan",
    "_USBWorker.export": "UsbWorkerModel.export",
    "_USBWorker._do_scan": "UsbWorkerModel.do_scan",
    "_USBWorker._do_export": "UsbWorkerModel.do_export",
}

#: Members the surface adds. Each names what it is for.
HELPER_MAP = {
    "UsbAuthWidgetModel.exchange_rows": "the exchange list, or none",
    "UsbAuthWidgetModel.save_settings": "one write-back and its refusal",
    "UsbAuthWidgetModel.toggle_row": "one row press and where it is routed",
    "UsbAuthWidgetModel.select": "the drive picker moving to one row",
    "UsbAuthWidgetModel.next_answer": "the next scripted confirmation answer",
    "UsbAuthWidgetModel.build_view_model": "the whole panel as one dict",
    "UsbStatusIndicatorModel.build_view_model": "the lamp as one dict",
    "ExchangeHwRowModel.build_view_model": "one row as one dict",
    "UsbWorkerModel.__init__": "the drive listing and the export",
    "SettingsSource.save": "the settings write-back",
    "VolumeSource.__init__": "one drive described by plain values",
    "SettingsSource.__init__": "the exchange list and its write-back",
    "small_text_style": "the ten-pixel note style",
    "no_volume_listing": "no drives, for a caller that supplied none",
    "no_export": "a refusal, for a caller that supplied no export",
    "no_verify": "a refusal, for a caller that supplied no verifier",
    "lamp_tooltip": "one lamp state's hover text",
    "lamp_colour": "one lamp state's colour",
    "lamp_state": "the lamp state for one exchange row",
    "serial_text": "the key line one row shows",
    "toggle_text": "the switch caption",
    "toggle_style": "the switch look",
    "row_name_text": "the exchange name one row shows",
    "drive_item_label": "one line in the drive picker",
    "drive_info_text": "the line under the drive picker",
    "auth_path": "where the key file would be written",
    "export_question_body": "the confirmation before a write",
    "no_auth_body": "the refusal when a drive carries no key file",
    "verify_passed_body": "the message when a key file decrypts",
    "verify_failed_body": "the message when a key file does not",
    "export_done_body": "the message after a key file is written",
    "status_style": "the status line colour",
    "build_model": "one panel built from plain values",
    "panel_model": "the one panel the bridge keeps",
    "build_view_model": "the whole panel as one dict",
    "view_model": "the bridge handler",
    "volume_from": "one drive built from a bridge request",
}


def resolve(dotted):
    """The member a dotted name in a map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def test_every_shipped_class_has_a_counterpart():
    """A class was lost or renamed with nothing standing in its place."""
    assert set(CLASS_MAP) == declared_classes(shipped)
    for shipped_name, surface_name in CLASS_MAP.items():
        assert hasattr(shipped, shipped_name), shipped_name
        assert isinstance(resolve(surface_name), type), surface_name


def test_every_shipped_method_has_a_counterpart():
    """A method was lost with nothing standing in its place."""
    assert set(METHOD_MAP) == declared_methods(shipped)
    for shipped_name, surface_name in METHOD_MAP.items():
        assert callable(resolve(surface_name)), surface_name


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passes whatever either side declares."""
    assert set(METHOD_MAP) - declared_methods(shipped) == set()
    grown = dict(METHOD_MAP, **{"USBAuthWidget.invented": "UsbAuthWidgetModel.build"})
    assert set(grown) - declared_methods(shipped) == {"USBAuthWidget.invented"}
    with pytest.raises(AttributeError):
        resolve("UsbAuthWidgetModel.a_method_that_does_not_exist")


def test_every_surface_member_is_a_counterpart_or_a_named_helper():
    """A member grew on the surface that nothing accounts for."""
    surface_side = set(METHOD_MAP.values()) | set(HELPER_MAP)
    declared = set(declared_functions(surface))
    for owner in CLASS_MAP.values():
        declared |= {f"{owner}.{one}" for one in members(getattr(surface, owner))}
    for owner in ("VolumeSource", "SettingsSource"):
        declared |= {f"{owner}.{one}" for one in members(getattr(surface, owner))}
    assert declared - surface_side == set(), sorted(declared - surface_side)


def test_the_signatures_match_the_shipped_methods():
    """A method takes a different number of values than the one it replaces."""
    import inspect

    pairs = {
        "USBStatusIndicator.set_state": "UsbStatusIndicatorModel.set_state",
        "_ExchangeHWRow.update_serial": "ExchangeHwRowModel.update_serial",
        "USBAuthWidget.set_vault": "UsbAuthWidgetModel.set_vault",
        "_USBWorker.export": "UsbWorkerModel.export",
    }
    for shipped_name, surface_name in pairs.items():
        owner, method = shipped_name.split(".")
        old_side = inspect.signature(getattr(getattr(shipped, owner), method))
        new_side = inspect.signature(resolve(surface_name))
        assert list(old_side.parameters) == list(new_side.parameters), shipped_name


# The surface writes its own values


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file():
    """The surface reads the shipped file, so a change moves both sides.

    ``_C_BLUE`` reaches exactly one place, the verify button. Changing it
    at run time must move the shipped side alone, and the comparison must
    name that one key.
    """
    first = surface.VERIFY_STYLE
    original = shipped._C_BLUE
    try:
        shipped._C_BLUE = "#123456"
        panel, record, settings = drive_old_side("happy")
        old_side = read_old(panel, record, settings)
        new_side = read_new(*drive_new_side("happy"))
        moved = [
            key
            for key in sorted(old_side)
            if readable(old_side[key]) != readable(new_side[key])
        ]
    finally:
        shipped._C_BLUE = original
    assert moved == ["verify_style"], moved
    assert "#123456" in old_side["verify_style"]
    assert "#123456" not in new_side["verify_style"]
    assert surface.VERIFY_STYLE == first
    both_sides_agree("happy")


def test_neither_side_reads_the_wall_clock_during_a_drive():
    """A drive read the clock, so its answer is not the same twice.

    Every wall-clock function is swapped for one fixed reading and the
    file that asked is recorded, so a read from either file is named.
    """
    record = WORLD.fresh(CASES["happy"])
    swapped = [
        (time, "time"),
        (time, "monotonic"),
        (time, "perf_counter"),
    ]
    originals = [(owner, name, getattr(owner, name)) for owner, name in swapped]
    try:
        for owner, name in swapped:
            setattr(owner, name, frozen_clock)
        run_old(CASES["happy"], (SCAN, EXPORT, DONE_OK))
        run_new(CASES["happy"], (SCAN, EXPORT, DONE_OK))
        read = list(record.clock_readers)
    finally:
        for owner, name, first in originals:
            setattr(owner, name, first)
    assert WIDGET_PATH.name not in read, read
    assert SURFACE_PATH.name not in read, read
    assert frozen_clock() == FROZEN_SECONDS


def test_the_clock_guard_names_a_file_that_does_read_the_clock():
    """The clock guard reports nothing whatever a file does."""
    WORLD.fresh(CASES["happy"])
    frozen_clock()
    assert WORLD.current.clock_readers == [Path(__file__).name]


# A complete comparison

#: Payload keys no side-by-side reading compares, each with the test
#: that does cover it.
NOT_COMPARED = {
    "method": "test_the_bridge_registers_the_panel_method",
    "constants": "test_every_value_the_surface_exports_reaches_the_snapshot",
    "answers_left": "test_a_confirmation_answered_no_writes_nothing",
}

#: Row keys no side-by-side reading compares, each with its test.
ROW_NOT_COMPARED = {
    "lamp": "test_the_lamp_shows_the_same_hover_text_on_both_sides",
    "hardware_mode": "test_a_row_emits_the_same_signal_on_both_sides",
    "serial": "test_a_row_told_a_new_serial_shows_it",
}

LAMP_NOT_COMPARED = {
    "state": "test_the_two_sides_render_the_same_pixels",
    "colour": "test_the_lamp_colours_are_compared_as_exact_text",
    "paint": "test_the_lamp_paint_carries_the_darkening_as_the_request",
    "updates": "test_the_lamp_counts_every_state_it_was_given",
    "exchange_label": "test_the_lamp_shows_the_same_hover_text_on_both_sides",
}


def whole_payload():
    """One payload holding a row, so every key is present."""
    model, record, settings = drive_new_side("two_exchanges", (SCAN,))
    assert record is not None and settings is not None
    return surface.build_view_model(model)


def test_every_payload_key_is_compared_or_named_with_its_test():
    """A key reaches no comparison and no test, so nothing reads it."""
    payload = whole_payload()
    compared = set(read_new(*drive_new_side("two_exchanges", (SCAN,))))
    accounted = compared | set(NOT_COMPARED)
    assert set(payload) - accounted == set(), sorted(set(payload) - accounted)
    row = payload["rows"][0]
    row_accounted = set(read_new_row(row)) | set(ROW_NOT_COMPARED)
    row_accounted |= {"lamp_tooltip", "lamp_size_px"}
    assert set(row) - row_accounted == set(), sorted(set(row) - row_accounted)
    lamp_accounted = set(LAMP_NOT_COMPARED) | {"tooltip", "size_px"}
    assert set(row["lamp"]) - lamp_accounted == set(), sorted(row["lamp"])


def test_the_key_coverage_check_reports_a_key_nothing_reads():
    """The coverage check passes whatever the payload grows."""
    payload = dict(whole_payload(), a_key_nothing_reads=1)
    compared = set(read_new(*drive_new_side("two_exchanges", (SCAN,))))
    accounted = compared | set(NOT_COMPARED)
    assert set(payload) - accounted == {"a_key_nothing_reads"}


def module_constants():
    """Every upper-case value the surface declares, as a name to value table.

    ``CONSTANTS`` is the snapshot itself and ``PANEL_MODEL`` is the
    shared panel, which is state and not a value, so neither is one.
    """
    return {
        name: value
        for name, value in vars(surface).items()
        if name.isupper() and name not in ("CONSTANTS", "PANEL_MODEL")
    }


def comparable(value):
    """One value as the snapshot carries it: a tuple becomes a list."""
    if isinstance(value, tuple):
        return [comparable(one) for one in value]
    if isinstance(value, dict):
        return {key: comparable(one) for key, one in value.items()}
    return value


def missing_from_snapshot(constants, snapshot):
    """Every constant the snapshot does not carry with its own value."""
    return sorted(
        name
        for name, value in constants.items()
        if name not in snapshot
        or readable(comparable(value)) != readable(snapshot[name])
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships reaches no comparison, so nothing reads it."""
    snapshot = whole_payload()["constants"]
    assert missing_from_snapshot(module_constants(), snapshot) == []
    assert len(module_constants()) >= 100, len(module_constants())


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    snapshot = whole_payload()["constants"]
    grown = dict(module_constants(), A_VALUE_NO_SNAPSHOT_HOLDS="x")
    assert missing_from_snapshot(grown, snapshot) == ["A_VALUE_NO_SNAPSHOT_HOLDS"]
    moved = dict(module_constants(), CYAN="#000000")
    assert missing_from_snapshot(moved, snapshot) == ["CYAN"]


def unbacked(snapshot):
    """Every snapshot key no module value stands behind."""
    constants = module_constants()
    return sorted(
        name
        for name, value in snapshot.items()
        if name not in constants
        or readable(comparable(constants[name])) != readable(value)
    )


def test_no_snapshot_key_exists_that_no_value_backs():
    """A snapshot key carries a value the surface does not hold."""
    assert unbacked(whole_payload()["constants"]) == []


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a snapshot carries."""
    snapshot = dict(whole_payload()["constants"])
    snapshot["A_KEY_NO_VALUE_BACKS"] = 1
    snapshot["CYAN"] = "#000000"
    assert unbacked(snapshot) == ["A_KEY_NO_VALUE_BACKS", "CYAN"]


def test_both_completeness_checks_can_report():
    """One of the two checks is blind, so a value can slip past it."""
    snapshot = whole_payload()["constants"]
    assert missing_from_snapshot(module_constants(), snapshot) == []
    assert unbacked(snapshot) == []
    assert missing_from_snapshot({"A_MISSING_NAME": 1}, snapshot) == ["A_MISSING_NAME"]
    assert unbacked({"A_SPARE_KEY": 1}) == ["A_SPARE_KEY"]


# The values a picture cannot see

#: Colours with two equal channels: a swap paints the same picture, so
#: each is compared as exact text.
EQUAL_CHANNEL_COLOURS = (
    "#0A0A14",
    "#0D0D20",
    "#1a1a3f",
    "#FF4444",
    "#FF6666",
    "#333355",
    "#222244",
)


def channels(colour):
    """The three channel pairs of one six-digit colour, lowercased."""
    digits = colour.lstrip("#").lower()
    return (digits[0:2], digits[2:4], digits[4:6])


def test_a_colour_with_two_equal_channels_is_compared_as_exact_text():
    """A channel swap paints the same picture, so a picture cannot see it."""
    for colour in EQUAL_CHANNEL_COLOURS:
        parts = channels(colour)
        assert len(set(parts)) < 3, colour
    named = {
        surface.BG,
        surface.PANEL,
        surface.BORDER,
        surface.RED,
        surface.LOCKED,
        surface.DISABLED_TEXT,
        surface.DISABLED_BORDER,
    }
    assert named == set(EQUAL_CHANNEL_COLOURS), sorted(named)
    for colour in EQUAL_CHANNEL_COLOURS:
        assert colour in json.dumps(whole_payload()["constants"]), colour


def test_the_lamp_colours_are_compared_as_exact_text():
    """A lamp colour moved and the comparison read it as a match."""
    assert surface.LAMP_COLOURS == {
        surface.STATE_INACTIVE: surface.GREY,
        surface.STATE_PRESENT: surface.UNLOCKED,
        surface.STATE_MISSING: surface.LOCKED,
    }
    assert surface.lamp_colour("melting") == surface.GREY
    assert len({surface.GREY, surface.UNLOCKED, surface.LOCKED}) == 3


def test_the_disabled_button_colours_are_compared_as_text():
    """A colour on a disabled rule reaches no pixel an offscreen render draws."""
    style = surface.button_style(surface.CYAN)
    assert surface.DISABLED_TEXT in style
    assert surface.DISABLED_BORDER in style
    assert ":disabled" in style
    assert ":hover" in style


def _painted_colours(name):
    """Every colour one rendered panel puts on screen, as ``#rrggbb``."""
    image = render_offscreen(old_panel_for_picture(name), PIXEL_SIZE)
    found = set()
    for row in range(image.height()):
        for column in range(image.width()):
            found.add(image.pixelColor(column, row).name())
    return found


def test_the_unused_colour_is_named_on_both_sides():
    """A colour the panel declares and paints nowhere is dropped quietly."""
    painted = set()
    for name in ("happy", "hardware_on_with_key", "no_device"):
        painted |= _painted_colours(name)
    assert surface.CYAN.lower() in painted, (
        f"the panel painted no CYAN pixel, so the absence below is a fact "
        f"about the reader; it painted {len(painted)} colours"
    )
    assert surface.GOLD.lower() not in painted
    assert surface.UNUSED_COLOUR_NAMES == ("GOLD",)
    assert surface.GOLD == shipped._C_GOLD


FULL_SCRIPT = (SCAN, ("select", 0), EXPORT, DONE_OK, ("toggle", 0), VERIFY)


def _record_signals(owner, fired):
    """Record every signal named in ``surface.SIGNALS`` that ``owner`` has."""
    for name in surface.SIGNALS:
        found = getattr(owner, name, None)
        if found is None or not hasattr(found, "connect"):
            continue
        found.connect(lambda *args, seen=name: fired.append(seen))


def _signals_fired_by_a_full_drive():
    """Every declared signal that fires while the panel runs FULL_SCRIPT.

    ``_rebuild_exchange_rows`` replaces the row, so ``_record_signals``
    is pointed at the row standing when the toggle step arrives.
    """
    fired: list[str] = []
    panel, _record, _settings = drive_old_side("happy")
    _record_signals(panel, fired)
    _record_signals(panel._worker, fired)
    for step in FULL_SCRIPT:
        if step[0] == "toggle":
            _record_signals(old_rows(panel)[0], fired)
        step_old(panel, CASES["happy"], step)
    panel._worker.scan_complete.emit([])
    panel._worker.export_complete.emit(True, "done")
    return set(fired)


def test_the_unemitted_signal_is_named_on_both_sides():
    """A signal the panel declares and never fires is dropped quietly."""
    fired = _signals_fired_by_a_full_drive()
    assert fired, "the drive fired no signal, so the set below means nothing"
    assert set(surface.SIGNALS) - fired == set(surface.UNEMITTED_SIGNALS)
    assert surface.UNEMITTED_SIGNALS == ("verify_complete",)


def test_the_logger_name_is_the_one_the_panel_writes_under():
    """The surface names a different log than the panel writes to."""
    assert shipped.logger.name == surface.LOGGER_NAME
    assert surface.SAVE_FAILED_MESSAGE.count("%s") == 1


def test_the_key_file_name_is_the_one_the_panel_shows():
    """The surface names a different key file than the panel writes."""
    assert surface.AUTH_FILENAME == core.AUTH_FILENAME
    assert surface.AUTH_FILENAME in surface.no_auth_body(drive(KEYED_DRIVE))
    assert str(surface.auth_path(drive(drive_spec()))).endswith(
        surface.AUTH_FILENAME,
    )


def test_a_confirmation_answered_no_writes_nothing():
    """A refused confirmation still asked for the write."""
    one = spec(answers=("no",))
    panel, old_record, old_settings, _stop = run_old(one, (SCAN, EXPORT))
    model, new_record, new_settings, _stop2 = run_new(one, (SCAN, EXPORT))
    assert old_record.threads == [], old_record.threads
    assert model.threads == [], model.threads
    assert len(old_record.dialogs) == 1
    assert old_record.dialogs[0][0] == surface.QUESTION
    assert readable(read_old(panel, old_record, old_settings)) == readable(
        read_new(model, new_record, new_settings),
    )
    assert model.answers == []


def test_a_confirmation_answered_yes_asks_for_the_write():
    """A confirmed export never reached the worker."""
    one = spec(answers=("yes",))
    _panel, old_record, _s, _stop = run_old(one, (SCAN, EXPORT))
    model, _new_record, _s2, _stop2 = run_new(one, (SCAN, EXPORT))
    assert old_record.threads == [
        [surface.EXPORT_THREAD_NAME, True, "do_export", 3],
    ], old_record.threads
    assert model.threads == old_record.threads


# The two sides paint the same pixels

PICTURE_CASES = (
    "happy",
    "no_device",
    "no_exchanges",
    "two_exchanges",
    "hardware_on_with_key",
    "hardware_on_no_key",
    "key_present",
    "unicode",
    "markup",
    "apostrophe",
    "long_two_hundred",
)


def render_offscreen(widget, size):
    """One render of `widget` at `size`, taken offscreen."""
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def old_panel_for_picture(name):
    """The shipped panel driven through one scan, ready to render."""
    panel, _record, _settings, _stop = run_old(CASES[name], (SCAN,))
    return panel


def model_payload(name):
    """The surface's whole payload for one case, stamped as it comes off."""
    model, _record, _settings, _stop = run_new(CASES[name], (SCAN,))
    return sealed(surface.build_view_model(model))


def lamp_painted_by_the_model(steps):
    """One lamp widget that paints only what the surface asked for."""
    from PySide6.QtGui import QBrush, QColor, QPainter, QPen
    from PySide6.QtWidgets import QWidget

    class PaintedLamp(QWidget):
        """A lamp that runs the surface's drawing steps and nothing else."""

        def __init__(self, drawing):
            super().__init__()
            self.setAccessibleName("U S B Key Lamp")
            self._drawing = drawing

        def paintEvent(self, event):
            """Run each drawing step the surface asked for, in order."""
            assert event is not None
            painter = QPainter(self)
            for step in self._drawing:
                if step[0] == "antialiasing":
                    painter.setRenderHint(
                        QPainter.RenderHint.Antialiasing,
                        step[1],
                    )
                elif step[0] == "pen":
                    painter.setPen(
                        QPen(QColor(step[1]).darker(step[2]), step[3]),
                    )
                elif step[0] == "brush":
                    painter.setBrush(QBrush(QColor(step[1])))
                elif step[0] == "ellipse":
                    painter.drawEllipse(*step[1])

    lamp = PaintedLamp(steps)
    lamp.setFixedSize(*surface.LAMP_SIZE_PX)
    return lamp


def panel_painted_by_the_model(payload):
    """One panel built only from the surface's view model."""
    from PySide6.QtWidgets import (
        QComboBox,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    payload = unaltered(payload)
    app()
    panel = hold(QWidget())
    panel.setAccessibleName(payload["accessible_name"])
    root = QVBoxLayout(panel)
    root.setContentsMargins(*payload["root_margins_px"])
    root.setSpacing(payload["root_spacing_px"])
    header = QLabel(payload["header_text"])
    header.setStyleSheet(payload["header_style"])
    root.addWidget(header)
    description = QLabel(payload["description_text"])
    description.setWordWrap(True)
    description.setStyleSheet(payload["description_style"])
    root.addWidget(description)

    export_group = QGroupBox(payload["export_group_title"])
    export_group.setStyleSheet(payload["group_style"])
    export_layout = QVBoxLayout(export_group)
    select_row = QHBoxLayout()
    select_row.addWidget(QLabel(payload["drive_label_text"]))
    combo = QComboBox()
    combo.setMinimumWidth(payload["combo_min_width_px"])
    combo.setStyleSheet(payload["combo_style"])
    for label in payload["combo_items"]:
        combo.addItem(label)
    combo.setCurrentIndex(payload["combo_index"])
    select_row.addWidget(combo)
    refresh = QPushButton(payload["refresh_text"])
    refresh.setFixedWidth(payload["refresh_width_px"])
    refresh.setStyleSheet(payload["refresh_style"])
    refresh.setEnabled(payload["refresh_enabled"])
    select_row.addWidget(refresh)
    select_row.addStretch()
    export_layout.addLayout(select_row)
    drive_info = QLabel(payload["drive_info_text"])
    drive_info.setStyleSheet(payload["drive_info_style"])
    export_layout.addWidget(drive_info)
    button_row = QHBoxLayout()
    export_button = QPushButton(payload["export_text"])
    export_button.setStyleSheet(payload["export_style"])
    export_button.setEnabled(payload["export_enabled"])
    button_row.addWidget(export_button)
    verify = QPushButton(payload["verify_text"])
    verify.setFixedWidth(payload["verify_width_px"])
    verify.setStyleSheet(payload["verify_style"])
    button_row.addWidget(verify)
    export_layout.addLayout(button_row)
    progress = QProgressBar()
    progress.setTextVisible(payload["progress_text_visible"])
    progress.setFixedHeight(payload["progress_height_px"])
    progress.setRange(*payload["progress_range"])
    progress.setVisible(payload["progress_visible"])
    progress.setStyleSheet(payload["progress_style"])
    export_layout.addWidget(progress)
    status = QLabel(payload["export_status_text"])
    status.setWordWrap(True)
    status.setStyleSheet(payload["export_status_style"])
    export_layout.addWidget(status)
    root.addWidget(export_group)

    mode_group = QGroupBox(payload["mode_group_title"])
    mode_group.setStyleSheet(payload["group_style"])
    mode_layout = QVBoxLayout(mode_group)
    mode_description = QLabel(payload["mode_description_text"])
    mode_description.setWordWrap(True)
    mode_description.setStyleSheet(payload["mode_description_style"])
    mode_layout.addWidget(mode_description)
    scroll = QScrollArea()
    scroll.setWidgetResizable(payload["scroll_resizable"])
    scroll.setMaximumHeight(payload["scroll_max_height_px"])
    scroll.setStyleSheet(payload["scroll_style"])
    container = QWidget()
    rows_layout = QVBoxLayout(container)
    rows_layout.setContentsMargins(*payload["rows_margins_px"])
    rows_layout.setSpacing(payload["rows_spacing_px"])
    if not payload["rows"]:
        empty = QLabel(payload["empty_text"])
        empty.setStyleSheet(payload["empty_style"])
        rows_layout.addWidget(empty)
    for one in payload["rows"]:
        row = QFrame()
        row.setAccessibleName(one["accessible_name"])
        row.setStyleSheet(one["style"])
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(*one["margins_px"])
        name = QLabel(one["name_text"])
        name.setStyleSheet(one["name_style"])
        row_layout.addWidget(name)
        serial = QLabel(one["serial_text"])
        serial.setStyleSheet(one["serial_style"])
        row_layout.addWidget(serial)
        row_layout.addStretch()
        lamp = lamp_painted_by_the_model(one["lamp"]["paint"])
        lamp.setToolTip(one["lamp"]["tooltip"])
        row_layout.addWidget(lamp)
        toggle = QPushButton(one["toggle_text"])
        toggle.setCheckable(one["toggle_checkable"])
        toggle.setChecked(one["toggle_checked"])
        toggle.setFixedWidth(one["toggle_width_px"])
        toggle.setStyleSheet(one["toggle_style"])
        row_layout.addWidget(toggle)
        rows_layout.addWidget(row)
    if payload["rows"]:
        rows_layout.addStretch()
    scroll.setWidget(container)
    mode_layout.addWidget(scroll)
    root.addWidget(mode_group)
    root.addStretch()
    return panel


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a panel the shipped panel does not."""
    app()
    old_side = render_offscreen(old_panel_for_picture(name), PIXEL_SIZE)
    new_side = render_offscreen(
        panel_painted_by_the_model(model_payload(name)),
        PIXEL_SIZE,
    )
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_panel_paints_more_than_one_colour():
    """A panel painting one colour cannot fail a picture check."""
    app()
    painted = colour_count(render_offscreen(old_panel_for_picture("happy"), PIXEL_SIZE))
    assert painted > 2, painted


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the surface paints."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(old_panel_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            panel_painted_by_the_model(model_payload("no_device")),
            PIXEL_SIZE,
        ),
        note="a drive attached against none",
    )
    assert_pictures_differ(
        old_side=render_offscreen(old_panel_for_picture("no_exchanges"), PIXEL_SIZE),
        new_side=render_offscreen(
            panel_painted_by_the_model(model_payload("two_exchanges")),
            PIXEL_SIZE,
        ),
        note="no exchanges against two",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_panel_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            panel_painted_by_the_model(model_payload("happy")),
            PIXEL_SIZE,
        ),
        note="one case, both sides",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """A render of a changed payload would measure the machine, not the product."""
    payload = model_payload("happy")
    payload["header_text"] = "moved"
    with pytest.raises(AssertionError):
        panel_painted_by_the_model(payload)
    with pytest.raises(AssertionError):
        panel_painted_by_the_model({"header_text": ""})
    assert panel_painted_by_the_model(model_payload("happy")) is not None


def test_the_panel_declares_no_skin_of_its_own():
    """A colour the surface ships is one the panel never paints.

    The rule the control applies is one neither side sets, so the
    difference it makes is the rule and not a value already there.
    """
    app()
    assert surface.SKIN == {}
    assert "QWidget" not in surface.GROUP_STYLE
    assert "QWidget" not in surface.ROW_STYLE
    assert "QWidget" not in surface.button_style(surface.CYAN)
    skinned = panel_painted_by_the_model(model_payload("happy"))
    skinned.setStyleSheet("QWidget { background-color: #3a1414; }")
    assert_pictures_differ(
        old_side=render_offscreen(old_panel_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(skinned, PIXEL_SIZE),
        note="a rule the panel does not set",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_panel_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            panel_painted_by_the_model(model_payload("happy")),
            PIXEL_SIZE,
        ),
        note="neither side carries a skin of its own",
    )


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves nothing."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert wide > narrow
    else:
        assert wide == narrow


@skip_unless_no_fonts
def test_with_no_font_database_every_letter_advances_alike():
    """Two strings of equal length measured apart with no font database."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_with_a_font_database_the_letters_advance_apart():
    """A run holding fonts measured every glyph the same width."""
    app()
    assert app_font_advance_px(WIDE_LABEL) > app_font_advance_px(NARROW_LABEL)


# Order independence and shared state


def test_the_shipped_module_changes_no_value_the_next_panel_reads():
    """The shipped panel writes a module value the next panel would read."""
    before = {
        name: value
        for name, value in vars(shipped).items()
        if name.isupper() or name.startswith("_C_")
    }
    run_old(CASES["two_exchanges"], (SCAN, EXPORT, DONE_OK, ("toggle", 0)))
    after = {
        name: value
        for name, value in vars(shipped).items()
        if name.isupper() or name.startswith("_C_")
    }
    assert before == after, sorted(set(before) ^ set(after))


def test_the_surface_keeps_no_value_between_two_panels():
    """The surface carries one panel's values into the next."""
    first, _r, _s, _stop = run_new(CASES["two_exchanges"], (SCAN, EXPORT))
    second, _r2, _s2, _stop2 = run_new(CASES["two_exchanges"], ())
    assert first.dialogs != []
    assert second.dialogs == []
    assert second.threads == []
    assert second.combo_items == []


def test_each_test_is_given_its_own_swapped_world(swapped_world):
    """One test's recorder decides what the next test reads."""
    from PySide6.QtWidgets import QMessageBox

    assert swapped_world.current.dialogs == []
    QMessageBox.warning(None, "a title", "a body")
    assert swapped_world.current.dialogs == [["warning", "a title", "a body"]]


def test_each_test_is_given_its_own_swapped_world_again(swapped_world):
    """The recorder from the test above carried into this one."""
    assert swapped_world.current.dialogs == []


def test_the_swap_is_in_place_during_a_drive_and_gone_after():
    """The swap never fired, so the drive reached the real device."""
    first = core.list_usb_volumes
    assert first is listed_drives
    assert shipped.threading is ThreadModule
    run_old(CASES["happy"], (SCAN,))
    assert core.list_usb_volumes is listed_drives
    assert core.verify_auth_file is verified_auth_file
    assert core.export_credentials_to_usb is exported_credentials


def test_the_swap_survives_a_drive_that_refuses_part_way():
    """A refusal left a swapped function pointing at the real device."""
    _panel, _r, _s, stop = run_old(REFUSING_CASES["text_where_number"], (SCAN,))
    assert stop[2] == "ValueError", stop
    assert core.list_usb_volumes is listed_drives
    assert shipped.threading is ThreadModule


def test_the_shipped_panel_edits_the_exchange_list_it_is_given():
    """The panel leaves the exchange list alone, so nothing is stored."""
    one = CASES["short_serial"]
    panel, record, settings, _stop = run_old(one, (("toggle", 0),))
    assert panel is not None and record is not None
    assert settings.exchanges[0]["hardware_mode"] is True
    assert one["exchanges"][0]["hardware_mode"] is False
    assert record.dialogs == [], record.dialogs


def test_no_test_here_reaches_a_real_device_or_a_real_venue():
    """A test opened a real socket, listed a real drive or read a credential."""
    import socket

    real_socket = socket.create_connection
    real_lookup = socket.getaddrinfo
    reached: list = []

    def refuse(*args, **_kwargs):
        reached.append(args)
        raise AssertionError("this run tried to reach the network")

    socket.create_connection = refuse
    socket.getaddrinfo = refuse
    try:
        both_sides_agree("happy", (SCAN, EXPORT, DONE_OK))
        both_sides_agree("key_present", (SCAN, VERIFY))
    finally:
        socket.create_connection = real_socket
        socket.getaddrinfo = real_lookup
    assert reached == [], reached
    with pytest.raises(AssertionError):
        refuse("a seeded call")


# Over the bridge


def test_view_model_is_json_serialisable():
    """A value in the payload cannot cross the bridge."""
    payload = surface.view_model({"reset": True, "exchanges": [exchange()]})
    text = json.dumps(payload)
    assert json.loads(text)["method"] == surface.METHOD
    surface.view_model({"reset": True})


def test_the_bridge_registers_the_panel_method():
    """The renderer cannot reach the USB key panel over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "usb_auth_widget.state"
    assert registered[surface.METHOD] is surface.view_model


def test_the_bridge_keeps_the_panel_until_a_reset():
    """The panel forgets the operator's steps between two requests."""
    surface.view_model({"reset": True, "exchanges": [exchange()]})
    first = surface.view_model({})
    assert first["rows"][0]["exchange_id"] == PLAIN_ID
    second = surface.view_model({"toggle": [0, True]})
    assert second["rows"][0]["toggle_checked"] is False
    third = surface.view_model({"reset": True})
    assert third["rows"] == []
    surface.view_model({"reset": True})


def test_the_bridge_drives_every_step_the_panel_takes():
    """A step the panel takes cannot be reached over the bridge."""
    answered = surface.view_model(
        {
            "reset": True,
            "exchanges": [exchange(hw_volume_serial=PLAIN_SERIAL)],
            "vault": VAULT,
            "answers": ["yes"],
            "refresh": True,
            "scan_complete": [
                {
                    "label": "CHIPKEY",
                    "serial": PLAIN_SERIAL,
                    "size_gb": 15.5,
                    "mount_point": "/invented/chip",
                    "auth_file": None,
                },
            ],
            "select": 0,
            "export": True,
            "export_complete": [True, EXPORT_MESSAGE],
            "verify": True,
            "toggle": [0, True],
            "refresh_exchanges": True,
        },
    )
    assert answered["combo_items"] == ["CHIPKEY (15.5 GB) — " + PLAIN_SERIAL]
    assert surface.AUTH_FILENAME in answered["dialogs"][0][2]
    assert answered["export_status_text"] == EXPORT_MESSAGE
    assert answered["threads"] == [
        [surface.SCAN_THREAD_NAME, True, "do_scan", 0],
        [surface.EXPORT_THREAD_NAME, True, "do_export", 3],
    ]
    assert answered["timers"] == [[surface.SCAN_DELAY_MS, "scan"]]
    assert [one[0] for one in answered["dialogs"]] == [
        surface.QUESTION,
        surface.INFORMATION,
        surface.WARNING,
    ]
    assert answered["rows"][0]["toggle_checked"] is True
    assert set(surface.STEP_NAMES) == {
        "set_vault",
        "refresh",
        "scan_complete",
        "select",
        "export",
        "export_complete",
        "verify",
        "toggle",
        "refresh_exchanges",
    }
    surface.view_model({"reset": True})


def test_the_bridge_reports_a_panel_it_cannot_read():
    """The bridge swallowed a refusal and answered as if it had a panel."""
    from src.core import desktop_bridge

    frame = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 1,
                "method": surface.METHOD,
                "params": {"reset": True, "scan_complete": [{"size_gb": "fifteen"}]},
            },
        ),
        desktop_bridge.build_registry(),
    )
    assert frame["ok"] is False
    assert frame["error"]["type"] == "ValueError"
    surface.view_model({"reset": True})


# Without Qt at all, in a fresh process

BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

COUNT_NETWORK = (
    "import socket, webbrowser\n"
    "_reached = []\n"
    "_browsed = []\n"
    "def _refuse(*args, **kwargs):\n"
    "    _reached.append(args)\n"
    "    raise AssertionError('this run tried to reach the network')\n"
    "def _refuse_browser(*args, **kwargs):\n"
    "    _browsed.append(args)\n"
    "    raise AssertionError('this run tried to open a browser')\n"
    "socket.create_connection = _refuse\n"
    "socket.getaddrinfo = _refuse\n"
    "socket.socket.connect = _refuse\n"
    "webbrowser.open = _refuse_browser\n"
    "webbrowser.open_new = _refuse_browser\n"
    "webbrowser.open_new_tab = _refuse_browser\n"
)

BRIDGE_PROBE = (
    "import json, sys\n"
    "from src.core import desktop_bridge\n"
    "frame = desktop_bridge.handle_line(\n"
    "    json.dumps({'id': 1, 'method': 'usb_auth_widget.state',\n"
    "                'params': {'reset': True}}),\n"
    "    desktop_bridge.build_registry())\n"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules,\n"
    "                  'reached': len(_reached),\n"
    "                  'browsed': len(_browsed)}))\n"
)

HEADLESS_PROBE = (
    "import json, sys\n"
    "from src.gui.main_tabs import usb_auth_widget_surface as s\n"
    "settings = s.SettingsSource([\n"
    "    {'exchange_id': 'chipex', 'display_name': 'Chip Exchange',\n"
    "     'hardware_mode': False, 'hw_volume_serial': ''}])\n"
    "model = s.build_model(settings=settings, vault='a store',\n"
    "                      answers=['yes'], build_now=True)\n"
    "model.on_scan_complete([s.volume_from({'label': 'CHIPKEY',\n"
    "                                       'serial': 'SER-0001-AAAA',\n"
    "                                       'size_gb': 15.5,\n"
    "                                       'mount_point': '/invented/chip',\n"
    "                                       'auth_file': None})])\n"
    "model.on_export()\n"
    "model.on_export_complete(True, 'wrote 2 exchanges')\n"
    "model.toggle_row(0, True)\n"
    "payload = s.build_view_model(model)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "                  'header': payload['header_text'],\n"
    "                  'items': payload['combo_items'],\n"
    "                  'threads': payload['threads'],\n"
    "                  'timers': payload['timers'],\n"
    "                  'dialogs': [one[0] for one in payload['dialogs']],\n"
    "                  'rows': len(payload['rows']),\n"
    "                  'checked': payload['rows'][0]['toggle_checked'],\n"
    "                  'saves': payload['saves'],\n"
    "                  'reached': len(_reached),\n"
    "                  'browsed': len(_browsed)}))\n"
)

IMPORT_PROBE = (
    "import json, os, shutil, sys, tempfile\n"
    "from pathlib import Path\n"
    "root = Path(tempfile.mkdtemp(prefix='acervator-usb-probe-'))\n"
    "at_import = root / 'at-import'\n"
    "on_request = root / 'on-request'\n"
    "at_import.mkdir()\n"
    "on_request.mkdir()\n"
    "os.environ['ACERVATOR_TEST_HOME'] = str(at_import)\n"
    "os.environ['HOME'] = str(at_import)\n"
    "os.environ['USERPROFILE'] = str(at_import)\n"
    "from src.gui.main_tabs import usb_auth_widget_surface as s\n"
    "built_at_import = s.PANEL_MODEL is not None\n"
    "files_at_import = sorted(one.name for one in at_import.iterdir())\n"
    "os.environ['ACERVATOR_TEST_HOME'] = str(on_request)\n"
    "os.environ['HOME'] = str(on_request)\n"
    "os.environ['USERPROFILE'] = str(on_request)\n"
    "panel = s.panel_model()\n"
    "s.build_view_model(panel)\n"
    "answer = {'built_at_import': built_at_import,\n"
    "          'built_on_request': panel is s.PANEL_MODEL,\n"
    "          'files_at_import': files_at_import,\n"
    "          'files_on_request': sorted(one.name for one in on_request.iterdir()),\n"
    "          'qt': 'PySide6' in sys.modules,\n"
    "          'reached': len(_reached),\n"
    "          'browsed': len(_browsed)}\n"
    "shutil.rmtree(root, ignore_errors=True)\n"
    "print(json.dumps(answer))\n"
)

THROWAWAY_HOME_PROBE = (
    "import json, os, shutil, sys, tempfile\n"
    "from pathlib import Path\n"
    "root = Path(tempfile.mkdtemp(prefix='acervator-usb-home-'))\n"
    "os.environ['ACERVATOR_TEST_HOME'] = str(root)\n"
    "os.environ['HOME'] = str(root)\n"
    "os.environ['USERPROFILE'] = str(root)\n"
    "before = sorted(str(one) for one in root.rglob('*'))\n"
    "from src.gui.main_tabs import usb_auth_widget_surface as s\n"
    "for step in range(3):\n"
    "    s.view_model({'reset': True,\n"
    "                  'exchanges': [{'exchange_id': 'chipex'}],\n"
    "                  'vault': 'a store', 'answers': ['yes'],\n"
    "                  'scan_complete': [{'label': 'K', 'serial': 'S',\n"
    "                                     'size_gb': 1.0,\n"
    "                                     'mount_point': '/invented/k'}],\n"
    "                  'export': True, 'verify': True,\n"
    "                  'export_complete': [True, 'done'],\n"
    "                  'toggle': [0, True]})\n"
    "after = sorted(str(one) for one in root.rglob('*'))\n"
    "if os.environ.get('ACERVATOR_PROBE_CONTROL') == '1':\n"
    "    (root / 'a-file-the-probe-wrote').write_text('x', encoding='utf-8')\n"
    "    after = sorted(str(one) for one in root.rglob('*'))\n"
    "answer = {'before': len(before), 'after': len(after),\n"
    "          'created': [Path(one).name for one in after if one not in before],\n"
    "          'home': str(Path.home()) == str(root),\n"
    "          'reached': len(_reached),\n"
    "          'browsed': len(_browsed)}\n"
    "shutil.rmtree(root, ignore_errors=True)\n"
    "print(json.dumps(answer))\n"
)


def run_script(source, extra_env=None):
    """Run one probe in a fresh process and return what it printed."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("ACERVATOR_PROBE_CONTROL", None)
    if extra_env:
        env.update(extra_env)
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
        env=env,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the USB key panel pulled Qt into the backend."""
    answered = run_script(COUNT_NETWORK + BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["reached"] == 0
    assert answered["browsed"] == 0
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == surface.METHOD
    assert result["header_text"] == surface.HEADER_TEXT
    assert result["rows"] == []


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore\n" + COUNT_NETWORK + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_the_panel_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(BLOCK_QT + COUNT_NETWORK + HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["reached"] == 0
    assert answered["browsed"] == 0
    assert answered["header"] == surface.HEADER_TEXT
    assert answered["items"] == ["CHIPKEY (15.5 GB) — SER-0001-AAAA"]
    assert answered["threads"] == [
        [surface.EXPORT_THREAD_NAME, True, "do_export", 3],
    ], answered["threads"]
    assert answered["timers"] == [[surface.SCAN_DELAY_MS, "scan"]]
    assert answered["dialogs"] == [surface.QUESTION, surface.INFORMATION]
    assert answered["rows"] == 1
    assert answered["checked"] is True
    assert answered["saves"] >= 1


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_network_counter_reaches_a_child_process():
    """The network counter reports zero whatever a child process reaches."""
    probe = COUNT_NETWORK + (
        "import json, socket\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', 9))\n"
        "except AssertionError:\n"
        "    pass\n"
        "print(json.dumps({'reached': len(_reached)}))\n"
    )
    assert run_script(probe)["reached"] == 1


def test_the_browser_counter_reaches_a_child_process():
    """POSITIVE CONTROL: the browser tripwire reports an open() that the
    probes above must never see."""
    probe = COUNT_NETWORK + (
        "import json, webbrowser\n"
        "try:\n"
        "    webbrowser.open('https://example.invalid')\n"
        "except AssertionError:\n"
        "    pass\n"
        "print(json.dumps({'browsed': len(_browsed)}))\n"
    )
    assert run_script(probe)["browsed"] == 1


def test_importing_the_surface_reads_nothing(tmp_path):
    """Loading the surface built a panel, which reads the operator's own tree.

    The home directory is aimed at one folder while the surface is
    imported and at a second before the first request. Nothing is built
    until the request, so neither folder is written to.
    """
    assert tmp_path.is_dir()
    answered = run_script(COUNT_NETWORK + IMPORT_PROBE)
    assert answered["built_at_import"] is False, answered
    assert answered["built_on_request"] is True, answered
    assert answered["files_at_import"] == [], answered
    assert answered["files_on_request"] == [], answered
    assert answered["qt"] is False, answered
    assert answered["reached"] == 0, answered
    assert answered["browsed"] == 0, answered


def test_a_run_against_a_throwaway_home_creates_no_file():
    """The panel wrote into the home directory it was pointed at."""
    answered = run_script(COUNT_NETWORK + THROWAWAY_HOME_PROBE)
    assert answered["home"] is True, answered
    assert answered["created"] == [], answered
    assert answered["before"] == answered["after"] == 0, answered
    assert answered["reached"] == 0, answered
    assert answered["browsed"] == 0, answered


def test_the_throwaway_home_check_sees_a_file_that_is_written():
    """The file check reports nothing whatever the run writes."""
    answered = run_script(
        COUNT_NETWORK + THROWAWAY_HOME_PROBE,
        {"ACERVATOR_PROBE_CONTROL": "1"},
    )
    assert answered["created"] == ["a-file-the-probe-wrote"], answered
    assert answered["after"] == 1, answered
