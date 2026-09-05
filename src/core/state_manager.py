"""Bot state persistence.

``StateManager`` reads and writes ``bot_state.json`` under ``_DEFAULT_DIR``
through ``atomic_write_json``. ``save_state`` carries forward every record
already on disk, and ``delete_bot`` is the only path that removes one.
``load_state`` falls back to ``_try_backup`` when the primary will not parse.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from .io_utils import atomic_write_json

logger = logging.getLogger("acervator.state")

_DEFAULT_DIR = Path.home() / ".acervator"


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

        try:
            atomic_write_json(
                self._path,
                state,
                indent=2,
                default=str,
                before_replace=_refresh_backup,
            )
            logger.info("Bot state saved: %d bots", len(bots))
        except Exception as exc:
            logger.error("Failed to save bot state: %s", exc)

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
                state = json.load(f)

            bots = state.get("bots") or {}
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

            atomic_write_json(
                self._path,
                state,
                indent=2,
                default=str,
                before_replace=_refresh_backup,
            )

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
        """The ``bots`` map from a state file, or {} when the file is absent.

        A decode error propagates to the caller, and ``save_state`` and
        ``_read_bot_ids`` each catch it.
        """
        target = self._path if path is None else path
        if not target.exists():
            return {}
        with open(target, "r", encoding="utf-8") as f:
            return dict(json.load(f).get("bots") or {})

    def _read_bot_ids(self, path) -> "Optional[set]":
        """Bot ids in a state file, or None when ``_read_bot_records`` raises.

        ``detect_prune`` and ``diff_primary_vs_backup`` read None as unknown
        and never as an empty file.
        """
        try:
            return set(self._read_bot_records(path).keys())
        except Exception:  # noqa: BLE001 - a detector must never raise
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
        list; this logs at ERROR and never raises.
        """
        try:
            primary = self._read_bot_ids(self._path)
            backup = self._read_bot_ids(self._backup_path)
            if primary is None or backup is None:
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

        A ``json.JSONDecodeError`` routes to ``_try_backup``.
        """
        if not self._path.exists():
            return {}
        try:
            with open(self._path, "r") as f:
                state = json.load(f)
            bot_count = len(state.get("bots", {}))
            saved_at = state.get("saved_at_human", "unknown")
            logger.info("Bot state loaded: %d bots (saved %s)", bot_count, saved_at)
            return state
        except json.JSONDecodeError:
            logger.error("Corrupt state file, trying backup...")
            return self._try_backup()
        except Exception as exc:
            logger.error("Failed to load bot state: %s", exc)
            return {}

    def _try_backup(self) -> dict:
        """Load ``_backup_path`` when ``load_state`` cannot parse the primary."""
        if not self._backup_path.exists():
            return {}
        try:
            with open(self._backup_path, "r") as f:
                state = json.load(f)
            logger.info("Loaded from backup: %d bots", len(state.get("bots", {})))
            return state
        except Exception:
            logger.error("Backup also corrupt")
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
        """Classify ``_path``: ``no_file``, ``empty``, ``has_bots``, ``unreadable``.

        ``has_saved_state`` is built on it, and an unreadable file logs at
        ERROR and never reports as ``empty``.
        """
        try:
            if not self._path.exists():
                return "no_file"
            with open(self._path, "r", encoding="utf-8") as f:
                state = json.load(f)
            return "has_bots" if len(state.get("bots", {})) > 0 else "empty"
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
            return "unreadable"

    def has_saved_state(self) -> bool:
        """Report whether ``probe`` returns ``has_bots``.

        ``no_file``, ``empty`` and ``unreadable`` all return False.
        """
        return self.probe() == "has_bots"
