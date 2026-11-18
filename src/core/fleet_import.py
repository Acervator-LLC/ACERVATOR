"""Copy one fleet file from any folder into a new instance's expected place.

``import_fleet`` checks the picked file and writes its bytes unchanged to
``resolve_fleet_path`` through ``atomic_write_bytes``, and a sealed fleet also
brings the ``MASTER_KEY_FILE_NAME`` beside it to ``master_key_path``.
``fleet_on_disk`` answers whether the instance is new, and
``src/gui/fleet_import_dialog.py, in ask_for_import`` is the screen that calls both.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from .encryption import MASTER_KEY_FILE_NAME, master_key_path, read_master_key
from .io_utils import atomic_write_bytes
from .log_paths import resolve_fleet_backup_path, resolve_fleet_path
from .state_manager import BOTS_FIELD, SEALED_PAYLOAD_FIELD, fleet_sealed

logger = logging.getLogger("acervator.fleet_import")

FLEET_PRESENT_TEXT = "{folder} already holds a fleet, so no file is imported into it."
EXPECTED_PLACE_TEXT = (
    "{picked} is the file this instance reads its fleet from, so it cannot be "
    "imported into itself."
)
MISSING_TEXT = "No file was found at {picked}."
FOLDER_TEXT = "{picked} is a folder, not a fleet file."
UNREADABLE_TEXT = "{picked} could not be read ({reason})."
NOT_JSON_TEXT = "{picked} is not a fleet file, because it does not hold JSON text."
NOT_OBJECT_TEXT = "{picked} is not a fleet file, because its JSON is not one object."
NO_BOTS_TEXT = "{picked} is not a fleet file, because it holds no map of bots."
NO_PAYLOAD_TEXT = "{picked} is marked sealed, but it carries no sealed fleet."
NO_KEY_TEXT = "{picked} is a sealed fleet, and no {key_name} is beside it in {folder}."
KEY_UNREADABLE_TEXT = (
    "{picked} is a sealed fleet, and the {key_name} beside it could not be read."
)
KEY_DIFFERS_TEXT = (
    "{key_dest} already holds another master key, so this sealed fleet is not "
    "imported over it."
)
WRITE_FAILED_TEXT = "The fleet could not be written to {dest} ({reason})."
IMPORTED_TEXT = "Imported {picked} to {dest}."
IMPORTED_SEALED_TEXT = "Imported {picked} to {dest}, with its master key to {key_dest}."

Picked = Union[str, "os.PathLike[str]"]


@dataclass(frozen=True)
class ImportOutcome:
    """What ``import_fleet`` did with one picked file.

    ``imported`` is True only once the fleet file is written, ``sentence`` is the
    one line the screen shows, and ``written`` names every file the import wrote.
    """

    imported: bool
    sentence: str
    written: tuple[Path, ...] = ()


def _refused(sentence: str) -> ImportOutcome:
    """An ``ImportOutcome`` that wrote nothing, logged at WARNING."""
    logger.warning("fleet import refused: %s", sentence)
    return ImportOutcome(imported=False, sentence=sentence)


def _occupied(path: Path) -> bool:
    """True where ``os.lstat`` finds *path*, or raises anything but FileNotFoundError."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def fleet_on_disk() -> bool:
    """True where ``resolve_fleet_path`` or ``resolve_fleet_backup_path`` is occupied.

    ``main.py, in main`` offers an import only while this answers False, and
    ``import_fleet`` asks it again before and during its write.
    """
    return _occupied(resolve_fleet_path()) or _occupied(resolve_fleet_backup_path())


def _same_file(one: Path, other: Path) -> bool:
    """True where ``Path.resolve`` names one place for *one* and *other*."""
    try:
        return one.resolve() == other.resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def _reason(exc: OSError) -> str:
    """The operating system's own words for *exc*, else its class name."""
    return str(exc.strerror or type(exc).__name__)


def _read_picked(picked: Path) -> tuple[Optional[bytes], str]:
    """The bytes at *picked*, or None and the refusal sentence naming why."""
    try:
        if picked.is_dir():
            return None, FOLDER_TEXT.format(picked=picked)
        return picked.read_bytes(), ""
    except FileNotFoundError:
        return None, MISSING_TEXT.format(picked=picked)
    except IsADirectoryError:
        return None, FOLDER_TEXT.format(picked=picked)
    except OSError as exc:
        return None, UNREADABLE_TEXT.format(picked=picked, reason=_reason(exc))


def _parse_fleet(picked: Path, data: bytes) -> tuple[Optional[dict], str]:
    """*data* read the way ``StateManager.load_state`` reads it, or the refusal."""
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError):
        return None, NOT_JSON_TEXT.format(picked=picked)
    if not isinstance(parsed, dict):
        return None, NOT_OBJECT_TEXT.format(picked=picked)
    return parsed, ""


def _key_beside(picked: Path) -> tuple[Optional[bytes], str]:
    """The ``MASTER_KEY_FILE_NAME`` bytes beside *picked*, or the refusal.

    ``read_master_key`` must answer a ``SealedMasterKey`` for that file, so a key
    the unlock screen could not open is refused here.
    """
    source = picked.parent / MASTER_KEY_FILE_NAME
    if not _occupied(source):
        return None, NO_KEY_TEXT.format(
            picked=picked, key_name=MASTER_KEY_FILE_NAME, folder=picked.parent
        )
    unreadable = KEY_UNREADABLE_TEXT.format(
        picked=picked, key_name=MASTER_KEY_FILE_NAME
    )
    if read_master_key(source) is None:
        return None, unreadable
    try:
        return source.read_bytes(), ""
    except OSError:
        return None, unreadable


def _key_needs_writing(key: bytes, key_dest: Path) -> tuple[bool, str]:
    """Whether *key* must be written to *key_dest*, or the refusal.

    An empty *key_dest* needs the write and the same bytes need none, while any
    other file at *key_dest* is refused and left in place.
    """
    if not _occupied(key_dest):
        return True, ""
    try:
        if key_dest.read_bytes() == key:
            return False, ""
    except OSError as exc:
        logger.warning("fleet import could not read %s: %s", key_dest, exc)
    return False, KEY_DIFFERS_TEXT.format(key_dest=key_dest)


def _refuse_if(occupied: Callable[[], bool], where: Path) -> Callable[[], None]:
    """A ``before_replace`` hook raising FileExistsError while *occupied* answers True."""

    def _check() -> None:
        if occupied():
            raise FileExistsError(f"{where} appeared during the import")

    return _check


def _write_fleet(
    data: bytes, dest: Path, key: Optional[bytes], key_dest: Path
) -> tuple[tuple[Path, ...], str]:
    """Write *key* to *key_dest* when given, then *data* to *dest*, or the refusal.

    Each ``atomic_write_bytes`` call refuses to replace a file, and a failed fleet
    write unlinks the *key_dest* this call wrote.
    """
    written: list[Path] = []
    try:
        if key is not None:
            atomic_write_bytes(
                key_dest,
                key,
                before_replace=_refuse_if(lambda: _occupied(key_dest), key_dest),
            )
            written.append(key_dest)
        atomic_write_bytes(dest, data, before_replace=_refuse_if(fleet_on_disk, dest))
        written.append(dest)
    except OSError as exc:
        for one in written:
            try:
                one.unlink()
            except OSError as undo_exc:
                logger.error("fleet import could not remove %s: %s", one, undo_exc)
        return (), WRITE_FAILED_TEXT.format(dest=dest, reason=_reason(exc))
    return tuple(written), ""


def import_fleet(picked: Picked) -> ImportOutcome:
    """Write *picked* to ``resolve_fleet_path``, or refuse with one sentence while
    ``fleet_on_disk`` answers True or the file fails a check.

    A plain fleet needs a ``BOTS_FIELD`` map, and a ``fleet_sealed`` one needs its
    ``SEALED_PAYLOAD_FIELD`` and a readable ``MASTER_KEY_FILE_NAME`` beside it.
    """
    dest = resolve_fleet_path()
    if fleet_on_disk():
        return _refused(FLEET_PRESENT_TEXT.format(folder=dest.parent))
    source = Path(picked).expanduser()
    if _same_file(source, dest):
        return _refused(EXPECTED_PLACE_TEXT.format(picked=source))
    data, refusal = _read_picked(source)
    if data is None:
        return _refused(refusal)
    parsed, refusal = _parse_fleet(source, data)
    if parsed is None:
        return _refused(refusal)

    sealed = fleet_sealed(parsed)
    key: Optional[bytes] = None
    key_dest = master_key_path()
    if sealed:
        token = parsed.get(SEALED_PAYLOAD_FIELD)
        if not isinstance(token, str) or not token:
            return _refused(NO_PAYLOAD_TEXT.format(picked=source))
        key, refusal = _key_beside(source)
        if key is None:
            return _refused(refusal)
        needed, refusal = _key_needs_writing(key, key_dest)
        if refusal:
            return _refused(refusal)
        if not needed:
            key = None
    elif not isinstance(parsed.get(BOTS_FIELD), dict):
        return _refused(NO_BOTS_TEXT.format(picked=source))

    written, refusal = _write_fleet(data, dest, key, key_dest)
    if refusal:
        return _refused(refusal)
    if sealed:
        sentence = IMPORTED_SEALED_TEXT.format(
            picked=source, dest=dest, key_dest=key_dest
        )
    else:
        sentence = IMPORTED_TEXT.format(picked=source, dest=dest)
    logger.info("fleet import: %s", sentence)
    return ImportOutcome(imported=True, sentence=sentence, written=written)
