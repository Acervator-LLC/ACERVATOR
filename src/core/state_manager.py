"""Bot state persistence.

``StateManager`` reads and writes ``bot_state.json`` under ``_DEFAULT_DIR``
through ``atomic_write_json``. ``save_state`` carries forward every record
already on disk, and ``delete_bot`` is the only path that removes one.
``load_state`` falls back to ``_try_backup`` when the primary will not parse,
and ``_unseal`` opens the payload a ``SEALED_LATCH_FIELD`` file holds.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

from .io_utils import atomic_write_json

logger = logging.getLogger("acervator.state")

_DEFAULT_DIR = Path.home() / ".acervator"

BOTS_FIELD = "bots"

SEALED_LATCH_FIELD = "fleet_sealed"
"""The plain-text field saying a password exists, and nothing else about it."""

SEALED_PAYLOAD_FIELD = "sealed_fleet"
"""The field holding ``SEALED_FIELDS`` as one token ``seal_payload`` produced."""

SEALED_FIELDS = (BOTS_FIELD, "bot_count", "smart_wires", "smart_wire_ledgers")
"""The fields that move inside the sealed payload, and are absent beside it."""

PROBE_NO_FILE = "no_file"
PROBE_SEALED = "sealed"
PROBE_EMPTY = "empty"
PROBE_HAS_BOTS = "has_bots"
PROBE_UNREADABLE = "unreadable"

FLEET_SEALED_NOTE = (
    "The saved fleet is sealed and this session holds no key for it. No bot is "
    "loaded and none starts. This is NOT the same as having no saved bots, and "
    "nothing may overwrite the sealed file."
)
"""What a reader reports for a sealed fleet, so none of them draws an empty one."""

SEALED_NO_KEY_LOG = (
    "%s carries the fleet latch and this session holds no master key, so its "
    "fleet payload stays sealed. No reader is given an empty fleet, and no "
    "write may replace the payload."
)

SEALED_REFUSED_LOG = (
    "%s carries a fleet payload that would NOT open with the master key this "
    "session holds (%s). The fleet stays sealed; do NOT let a save overwrite it."
)

SAVE_REFUSED_SEALED_LOG = (
    "REFUSING to write %s: its fleet payload is sealed and unopened, so this "
    "write would replace a fleet this session cannot read. The file is left as "
    "it is."
)

DELETE_REFUSED_SEALED_LOG = (
    "state: delete_bot(%s) REFUSED — the fleet payload in %s is sealed and "
    "unopened, so no record can be read or removed"
)

WRITE_FAILED_LOG = "Failed to write %s (%s: %s)"

LATCH_READ_FAILED_LOG = "The fleet latch in %s could not be read (%s)"

STATE_FILE_UNREADABLE_LOG = (
    "The state file %s could NOT be read (%s: %s), so the reader asking is "
    "given no fleet. This is NOT the same as having no saved bots."
)

BOT_IDS_UNREADABLE_LOG = (
    "The bot ids in %s could NOT be read (%s: %s), so every detector asking "
    "for them is answered unknown rather than an empty file."
)
"""What ``_read_bot_ids`` logs for a read it swallows, naming the cause."""

DIFF_UNREADABLE_LOG = (
    "C01 primary/backup diff: %s would not read, so this launch cannot tell "
    "whether %s holds bots that %s has lost. Treat neither copy as checked."
)
"""What ``diff_primary_vs_backup`` logs when it answers an empty list unread."""

UNLOCK_NO_KEY_LOG = "Fleet unlock refused: this install holds no sealed master key"

UNLOCK_REFUSED_LOG = "Fleet unlock refused: %s"


class FleetSealed(RuntimeError):
    """The state file holds a fleet payload no key in this session opens.

    ``_read_bot_records`` raises it, and ``save_state`` catches it to refuse a
    write that would replace records it cannot read.
    """


def fleet_sealed(state: object) -> bool:
    """True where *state* carries ``SEALED_LATCH_FIELD`` and no ``BOTS_FIELD``.

    ``load_state`` puts the opened payload's fields back, so this answers False
    once the payload is open and False for the empty dict an absent file gives.
    """
    if not isinstance(state, dict):
        return False
    return bool(state.get(SEALED_LATCH_FIELD)) and BOTS_FIELD not in state


def unseal(state: dict, name: str) -> dict:
    """*state* with its ``SEALED_PAYLOAD_FIELD`` opened, or *state* as it is.

    A *state* carrying no ``SEALED_LATCH_FIELD`` comes back untouched, and one
    whose payload will not open comes back carrying the latch and no
    ``BOTS_FIELD``, which is what ``fleet_sealed`` answers True for.
    """
    if not isinstance(state, dict) or not state.get(SEALED_LATCH_FIELD):
        return state
    from .encryption import held_master_key, open_payload

    key = held_master_key()
    if key is None:
        logger.warning(SEALED_NO_KEY_LOG, name)
        return state
    token = str(state.get(SEALED_PAYLOAD_FIELD) or "")
    try:
        opened = json.loads(open_payload(key, token))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error(SEALED_REFUSED_LOG, name, exc)
        return state
    if not isinstance(opened, dict):
        logger.error(SEALED_REFUSED_LOG, name, "the payload is not an object")
        return state
    out = {one: value for one, value in state.items() if one != SEALED_PAYLOAD_FIELD}
    out.update(opened)
    return out


def load_state_file(path) -> dict:
    """The state dict at *path*, with ``unseal`` run over whatever it holds.

    Every reader that builds its own path to the state file reads it here, so
    one held master key opens the payload for all of them and ``fleet_sealed``
    answers True only while none of them can read the fleet.
    """
    target = Path(path)
    if not target.exists():
        return {}
    try:
        with open(target, "r", encoding="utf-8") as f:
            return unseal(json.load(f), target.name)
    except Exception as exc:  # noqa: BLE001 - a bad file must not stop a launch
        logger.error(STATE_FILE_UNREADABLE_LOG, target, type(exc).__name__, exc)
        return {}


class StateManager:
    """Persists bot state to disk through ``atomic_write_json``.

    ``save_state`` writes ``version``, ``saved_at``, ``saved_at_human``,
    ``bot_count``, ``smart_wires``, ``smart_wire_ledgers`` and a ``bots`` map
    keyed by bot id.
    """

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self._dir = config_dir or _DEFAULT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "bot_state.json"
        self._backup_path = self._dir / "bot_state.backup.json"

    @property
    def config_dir(self) -> Path:
        """The directory this manager reads and writes.

        ``__init__`` sets it from its ``config_dir`` argument or from
        ``_DEFAULT_DIR``.
        """
        return self._dir

    def save_state(
        self,
        bots: list[dict],
        smart_wires: Optional[list[dict]] = None,
        smart_wire_ledgers: Optional[list[dict]] = None,
    ) -> None:
        """Write ``bots`` to disk atomically, merged with the records already there.

        ``smart_wires`` and ``smart_wire_ledgers`` replace the stored topology
        and ledger totals, and None for either writes an empty list.
        """
        from datetime import datetime

        state = {
            "version": "1.9.5",
            "saved_at": time.time(),
            "saved_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bot_count": len(bots),
            "bots": {},
            "smart_wires": list(smart_wires or []),
            "smart_wire_ledgers": list(smart_wire_ledgers or []),
        }

        for bot_data in bots:
            bid = bot_data.get("bot_id", "")
            if bid:
                state["bots"][bid] = bot_data

        # A record leaves this file only through delete_bot.
        try:
            on_disk = self._read_bot_records()
            carried = [bid for bid in on_disk if bid not in state["bots"]]
            for bid in carried:
                state["bots"][bid] = on_disk[bid]
            if carried:
                logger.info(
                    "state: carried forward %d record(s) not present in "
                    "memory (not deleted, merely not loaded): %s",
                    len(carried),
                    ", ".join(carried[:8]),
                )
        except FleetSealed:
            logger.error(SAVE_REFUSED_SEALED_LOG, self._path.name)
            return
        except Exception as exc:  # noqa: BLE001 - never block a save
            logger.error(
                "state: carry-forward failed (%s) — this save reverts to "
                "memory-only contents and MAY DROP records",
                exc,
            )

        state["bot_count"] = len(state["bots"])

        self.detect_prune(set(state["bots"].keys()))

        def _refresh_backup() -> None:
            """Copy the primary over ``_backup_path`` before it is replaced.

            ``_read_bot_ids`` returning None leaves the existing backup
            untouched.
            """
            if not self._path.exists():
                return
            if self._read_bot_ids(self._path) is None:
                logger.error(
                    "REFUSING to refresh %s: the current %s does not parse, "
                    "and copying it would destroy the last good backup. "
                    "The existing backup is being preserved as-is.",
                    self._backup_path.name,
                    self._path.name,
                )
                return
            try:
                self._backup_path.write_bytes(self._path.read_bytes())
            except OSError as _bk_exc:
                logger.warning(
                    "Bot state backup FAILED (%s): %s — proceeding "
                    "with save, but %s will not be recoverable from "
                    "backup if this write corrupts it",
                    type(_bk_exc).__name__,
                    _bk_exc,
                    self._path.name,
                )

        if self.write_state(state, before_replace=_refresh_backup):
            logger.info("Bot state saved: %d bots", len(bots))

    def _sealed_for_disk(self, state: dict) -> Optional[dict]:
        """*state* with ``SEALED_FIELDS`` moved into one ``SEALED_PAYLOAD_FIELD``.

        Answers *state* itself where ``held_master_key`` holds nothing, which is
        every install no password was set on, and None where ``fleet_sealed`` is
        already True for *state*.
        """
        if fleet_sealed(state):
            return None
        from .encryption import held_master_key, seal_payload

        key = held_master_key()
        if key is None:
            return state
        payload = {one: state[one] for one in SEALED_FIELDS if one in state}
        out = {one: value for one, value in state.items() if one not in SEALED_FIELDS}
        out[SEALED_LATCH_FIELD] = True
        out[SEALED_PAYLOAD_FIELD] = seal_payload(key, json.dumps(payload, default=str))
        return out

    def write_state(
        self, state: dict, *, before_replace: Optional[Callable[[], None]] = None
    ) -> bool:
        """Write a whole *state* over ``_path``, sealed where a master key is held.

        ``_sealed_for_disk`` decides what reaches the file, and this answers
        False where ``probe`` reads ``PROBE_SEALED`` off the file on disk, where
        *state* itself is sealed, or where the write raised.
        """
        if self.probe() == PROBE_SEALED:
            logger.error(SAVE_REFUSED_SEALED_LOG, self._path.name)
            return False
        for_disk = self._sealed_for_disk(state)
        if for_disk is None:
            logger.error(SAVE_REFUSED_SEALED_LOG, self._path.name)
            return False
        try:
            atomic_write_json(
                self._path,
                for_disk,
                indent=2,
                default=str,
                before_replace=before_replace,
            )
            return True
        except Exception as exc:  # noqa: BLE001 - never break a save
            logger.error(WRITE_FAILED_LOG, self._path.name, type(exc).__name__, exc)
            return False

    def latch_on(self) -> bool:
        """True where ``_path`` carries ``SEALED_LATCH_FIELD`` set.

        Opens no payload and needs no password, so a launch learns one exists
        before it holds it; an absent or unreadable file answers False.
        """
        try:
            if not self._path.exists():
                return False
            with open(self._path, "r", encoding="utf-8") as f:
                return bool(json.load(f).get(SEALED_LATCH_FIELD))
        except Exception as exc:  # noqa: BLE001 - must never stop a launch
            logger.warning(LATCH_READ_FAILED_LOG, self._path.name, exc)
            return False

    def unlock(self, password: str) -> bool:
        """Hold the master key *password* opens, so ``load_state`` opens the payload.

        ``open_master_key`` refuses a wrong *password* by failing the sealed
        key's own authentication tag, and this then holds nothing, answers False
        and leaves every reader the sealed state it already had.
        """
        from .encryption import hold_master_key, open_master_key, read_master_key

        sealed = read_master_key()
        if sealed is None:
            logger.warning(UNLOCK_NO_KEY_LOG)
            return False
        try:
            opened = open_master_key(sealed, str(password))
        except ValueError as exc:
            logger.warning(UNLOCK_REFUSED_LOG, exc)
            return False
        hold_master_key(opened)
        return True

    def _unseal(self, state: dict, name: str) -> dict:
        """``unseal`` over *state*, named *name* in whatever it logs."""
        return unseal(state, name)

    def delete_bot(self, bot_id: str) -> bool:
        """Remove one ``bot_id`` record from disk, the only removal path.

        Also drops that bot's ``smart_wire_ledgers`` row and every
        ``smart_wires`` entry naming it, and returns True when a record was
        removed.
        """
        try:
            if not self._path.exists():
                return False
            with open(self._path, "r", encoding="utf-8") as f:
                state = self._unseal(json.load(f), self._path.name)
            if fleet_sealed(state):
                logger.error(DELETE_REFUSED_SEALED_LOG, bot_id, self._path.name)
                return False

            bots = state.get(BOTS_FIELD) or {}
            if bot_id not in bots:
                logger.info(
                    "state: delete_bot(%s) — no record on disk, nothing " "to remove",
                    bot_id,
                )
                return False

            removed = bots.pop(bot_id)
            lots = len((removed.get("scrumming_state") or {}).get("main_lots") or [])
            tranches = len(
                (removed.get("scrumming_state") or {}).get("fold_tranches") or []
            )

            state["bots"] = bots
            state["bot_count"] = len(bots)
            state["smart_wire_ledgers"] = [
                r
                for r in (state.get("smart_wire_ledgers") or [])
                if str(r.get("bot_id", "")) != str(bot_id)
            ]
            state["smart_wires"] = [
                w
                for w in (state.get("smart_wires") or [])
                if str(w.get("source_id", "")) != str(bot_id)
                and str(w.get("target_id", "")) != str(bot_id)
            ]

            def _refresh_backup() -> None:
                """Copy the outgoing primary over the backup."""
                if not self._path.exists():
                    return
                try:
                    self._backup_path.write_bytes(self._path.read_bytes())
                except OSError as exc:
                    logger.warning("delete_bot: backup refresh failed: %s", exc)

            if not self.write_state(state, before_replace=_refresh_backup):
                return False

            # ERROR level marks an irreversible removal, not a failure.
            logger.error(
                "state: DELETED bot %s from disk — %d lot(s), %d "
                "tranche(s), and its wire/ledger rows are gone. "
                "%d bot(s) remain.",
                bot_id,
                lots,
                tranches,
                len(bots),
            )
            return True
        except Exception as exc:  # noqa: BLE001 - never break teardown
            logger.error(
                "state: delete_bot(%s) FAILED (%s: %s) — the record is "
                "still on disk and will be carried forward",
                bot_id,
                type(exc).__name__,
                exc,
            )
            return False

    def _read_bot_records(self, path=None) -> dict:
        """The ``BOTS_FIELD`` map from a state file, or {} when the file is absent.

        A decode error propagates to the caller, and ``FleetSealed`` is raised
        where the file's payload is sealed and unopened, so neither case ever
        answers an empty fleet.
        """
        target = self._path if path is None else path
        if not target.exists():
            return {}
        with open(target, "r", encoding="utf-8") as f:
            state = self._unseal(json.load(f), target.name)
        if fleet_sealed(state):
            raise FleetSealed(target.name)
        return dict(state.get(BOTS_FIELD) or {})

    def _read_bot_ids(self, path) -> "Optional[set]":
        """Bot ids in a state file, or None when ``_read_bot_records`` raises.

        ``detect_prune`` and ``diff_primary_vs_backup`` read None as unknown
        and never as an empty file. This is the only place the cause of a
        swallowed read is named, so the failure reaches the log here.
        """
        try:
            return set(self._read_bot_records(path).keys())
        except Exception as exc:  # noqa: BLE001 - a detector must never raise
            logger.error(
                BOT_IDS_UNREADABLE_LOG,
                Path(path).name,
                type(exc).__name__,
                exc,
            )
            return None

    def detect_prune(self, incoming_ids: set) -> list:
        """Return the bot ids on disk that ``incoming_ids`` omits, logged at ERROR.

        ``save_state`` calls this after its carry-forward, where a non-empty
        result means the carry-forward raised; this never raises.
        """
        try:
            on_disk = self._read_bot_ids(self._path)
            if on_disk is None:
                logger.warning(
                    "C01 prune detector: %s unreadable; cannot tell "
                    "whether this save drops anything",
                    self._path.name,
                )
                return []
            dropped = sorted(on_disk - set(incoming_ids or set()))
            if dropped:
                logger.error(
                    "C01 PRUNE RISK: this save omits %d bot(s) present on "
                    "disk and will DELETE their records (per-lot cost "
                    "basis, fold tranches, anchor balance): %s",
                    len(dropped),
                    ", ".join(dropped[:10]),
                )
            return dropped
        except Exception as exc:  # noqa: BLE001 - never break the save
            logger.warning("C01 prune detector failed: %s", exc)
            return []

    def diff_primary_vs_backup(self) -> list:
        """Bot ids present in ``_backup_path`` but missing from ``_path``.

        ``_read_bot_ids`` returning None for either file yields an empty
        list, which is reported as unread rather than as a clean pair; this
        logs at ERROR and never raises.
        """
        try:
            primary = self._read_bot_ids(self._path)
            backup = self._read_bot_ids(self._backup_path)
            if primary is None or backup is None:
                unread = [
                    p.name
                    for p, ids in ((self._path, primary), (self._backup_path, backup))
                    if ids is None
                ]
                logger.warning(
                    DIFF_UNREADABLE_LOG,
                    " and ".join(unread),
                    self._backup_path.name,
                    self._path.name,
                )
                return []
            missing = sorted(backup - primary)
            if missing:
                logger.error(
                    "C01 DAMAGE SUSPECTED: %d bot(s) present in %s but "
                    "absent from %s: %s. The backup copy is one save "
                    "cycle from being overwritten.",
                    len(missing),
                    self._backup_path.name,
                    self._path.name,
                    ", ".join(missing[:10]),
                )
            return missing
        except Exception as exc:  # noqa: BLE001 - never break boot
            logger.warning("C01 primary/backup diff failed: %s", exc)
            return []

    PREFLIGHT_KEEP = 10
    """How many snapshot sets ``preflight_snapshot`` keeps before pruning."""

    def _preflight_stamp(self) -> str:
        """Timestamp for a ``preflight_snapshot`` filename, to 1-second resolution."""
        from datetime import datetime

        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def preflight_snapshot(self) -> list:
        """Copy ``_path`` and ``_backup_path`` into a ``preflight`` subdirectory.

        Writes nothing when the digest of both files matches the newest
        ``.stamp``, prunes sets beyond ``PREFLIGHT_KEEP``, never raises, and
        returns the paths written.
        """
        import hashlib
        import shutil

        written: list = []
        try:
            root = self._path.parent / "preflight"
            root.mkdir(parents=True, exist_ok=True)

            sources = [p for p in (self._path, self._backup_path) if p.exists()]
            if not sources:
                return []

            digest = hashlib.sha256()
            for p in sources:
                digest.update(p.read_bytes())
            stamp_now = digest.hexdigest()[:16]

            existing = sorted(root.glob("*.stamp"))
            if (
                existing
                and existing[-1].read_text(encoding="utf-8").strip() == stamp_now
            ):
                logger.debug(
                    "preflight: state unchanged since last snapshot; " "nothing written"
                )
                return []

            ts = self._preflight_stamp()
            for p in sources:
                dest = root / f"{p.stem}.{ts}{p.suffix}"
                shutil.copy2(p, dest)
                written.append(dest)
            (root / f"{ts}.stamp").write_text(stamp_now, encoding="utf-8")

            stamps = sorted(root.glob("*.stamp"))
            for old in stamps[: -self.PREFLIGHT_KEEP]:
                old_ts = old.stem
                for victim in root.glob(f"*.{old_ts}.json"):
                    victim.unlink(missing_ok=True)
                old.unlink(missing_ok=True)

            logger.info(
                "preflight: snapshotted %d state file(s) to %s (keeping "
                "%d most recent)",
                len(written),
                root,
                self.PREFLIGHT_KEEP,
            )
            return written
        except Exception as exc:  # noqa: BLE001 - must never abort boot
            logger.error(
                "preflight snapshot FAILED (%s: %s) — continuing boot "
                "without a pre-session copy",
                type(exc).__name__,
                exc,
            )
            return written

    def load_state(self) -> dict:
        """Return the whole state dict from ``_path``, or {} when it is absent.

        A ``json.JSONDecodeError`` routes to ``_try_backup``, and a state whose
        payload ``_unseal`` could not open comes back carrying the latch and no
        ``BOTS_FIELD``, which ``fleet_sealed`` answers True for.
        """
        if not self._path.exists():
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                state = self._unseal(json.load(f), self._path.name)
            if fleet_sealed(state):
                return state
            bot_count = len(state.get(BOTS_FIELD, {}))
            saved_at = state.get("saved_at_human", "unknown")
            logger.info("Bot state loaded: %d bots (saved %s)", bot_count, saved_at)
            return state
        except json.JSONDecodeError:
            logger.error("Corrupt state file, trying backup...")
            return self._try_backup()
        except Exception as exc:
            logger.error(
                "Bot state file %s could NOT be read (%s: %s), returning 0 "
                "bots. This is NOT the same as having no saved bots. %s "
                "exists=%s and may hold a good copy — do NOT let a save "
                "overwrite it.",
                self._path,
                type(exc).__name__,
                exc,
                self._backup_path.name,
                self._backup_path.exists(),
            )
            return {}

    def _try_backup(self) -> dict:
        """Load ``_backup_path`` when ``load_state`` cannot parse the primary."""
        if not self._backup_path.exists():
            return {}
        try:
            with open(self._backup_path, "r", encoding="utf-8") as f:
                state = self._unseal(json.load(f), self._backup_path.name)
            if fleet_sealed(state):
                return state
            logger.info("Loaded from backup: %d bots", len(state.get(BOTS_FIELD, {})))
            return state
        except Exception as exc:
            logger.error(
                "Bot state backup %s could NOT be read either (%s: %s), "
                "returning 0 bots. Both saved copies are unread; do NOT let "
                "a save overwrite them.",
                self._backup_path,
                type(exc).__name__,
                exc,
            )
            return {}

    def clear_state(self) -> None:
        """Delete ``_path`` and ``_backup_path``, reporting any unlink that fails."""
        cleared, failed = [], []
        for p in [self._path, self._backup_path]:
            if p.exists():
                try:
                    p.unlink()
                    cleared.append(p.name)
                except OSError as _rm_exc:
                    failed.append(p.name)
                    logger.error(
                        "Failed to clear state file %s (%s): %s — stale "
                        "state remains on disk and WILL be restored on "
                        "next launch",
                        p.name,
                        type(_rm_exc).__name__,
                        _rm_exc,
                    )
        if failed:
            logger.warning(
                "Bot state clear INCOMPLETE: removed %s, failed %s",
                cleared or "nothing",
                failed,
            )
        else:
            logger.info("Bot state cleared")

    def probe(self) -> str:
        """Classify ``_path`` as one of the five ``PROBE_`` answers.

        ``has_saved_state`` is built on it, and neither a sealed payload nor an
        unreadable file ever reports as ``PROBE_EMPTY``.
        """
        try:
            if not self._path.exists():
                return PROBE_NO_FILE
            with open(self._path, "r", encoding="utf-8") as f:
                state = self._unseal(json.load(f), self._path.name)
            if fleet_sealed(state):
                return PROBE_SEALED
            if len(state.get(BOTS_FIELD, {})) > 0:
                return PROBE_HAS_BOTS
            return PROBE_EMPTY
        except Exception as exc:  # noqa: BLE001 - classify, never crash boot
            logger.error(
                "Bot state file %s is UNREADABLE (%s: %s). This is NOT the "
                "same as having no saved bots. %s exists=%s and may hold a "
                "good copy — do NOT let a save overwrite it.",
                self._path.name,
                type(exc).__name__,
                exc,
                self._backup_path.name,
                self._backup_path.exists(),
            )
            return PROBE_UNREADABLE

    def has_saved_state(self) -> bool:
        """Report whether ``probe`` returns ``PROBE_HAS_BOTS``.

        ``PROBE_NO_FILE``, ``PROBE_SEALED``, ``PROBE_EMPTY`` and
        ``PROBE_UNREADABLE`` all return False.
        """
        return self.probe() == PROBE_HAS_BOTS
