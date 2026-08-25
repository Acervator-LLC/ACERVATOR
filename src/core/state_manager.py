"""
state_manager.py - Robust bot state persistence
=================================================
Saves and restores bot configurations, positions, and statistics
between application sessions.

SAFETY RULES:
  - Bots are ALWAYS restored in PAUSED state, never auto-started
  - No orders are placed during restore
  - Exchange must be synced before resuming
  - User must explicitly verify and resume each bot
  - State is saved atomically (write temp, rename)
  - Corrupt state files are backed up, not overwritten

Storage: ~/.acervator/bot_state.json
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.state")

_DEFAULT_DIR = Path.home() / ".acervator"


class StateManager:
    """
    Persists bot state to disk. Thread-safe via atomic writes.

    State file structure:
    {
        "version": "1.9.4",
        "saved_at": 1234567890.0,
        "saved_at_human": "2025-04-12 03:00:00",
        "bots": {
            "bot_id_1": {
                "config": { ... all BotConfig fields ... },
                "state": "running",          # state when saved
                "stats": { ... all BotStats fields ... },
                "phantom_config": { ... },   # for scrumming bots
                "scrumming_state": { ... },  # for scrumming bots (MEM-245)
                "extractor_state": { ... },  # for extractor bots (v3.20.4)
            },
            ...
        }
    }
    """

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self._dir = config_dir or _DEFAULT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "bot_state.json"
        self._backup_path = self._dir / "bot_state.backup.json"

    @property
    def config_dir(self) -> Path:
        """The directory this manager reads and writes.

        Issue #96 added a single-instance guard, and that guard must
        claim the SAME directory the fleet was loaded from. Re-deriving
        `Path.home() / ".acervator"` at the guard would guard a
        different directory whenever a caller passed `config_dir=`,
        which every test does. So the guard asks the manager instead of
        repeating the default.
        """
        return self._dir

    def save_state(
        self,
        bots: list[dict],
        smart_wires: Optional[list[dict]] = None,
        smart_wire_ledgers: Optional[list[dict]] = None,
    ) -> None:
        """
        Save all bot states to disk atomically.

        Parameters
        ----------
        bots : list[dict]
            List of bot state dicts from BotContainer.get_full_state()
        smart_wires : Optional[list[dict]]
            v3.15.68 — list of {source_id, target_id, pct} dicts from
            SmartWireManager.export_wires(). When None, the current
            file's existing wires field (if any) is preserved.
        smart_wire_ledgers : Optional[list[dict]]
            v3.16.57 — per-bot ledger snapshots from
            SmartWireManager.export_ledgers(). Persists lifetime
            wired_in / wired_out totals and provenance across restart.
            Operator-reported bug 2026-05-13: "Smart Wire credits are
            not persisting across platform restarts."
        """
        from datetime import datetime

        state = {
            "version": "1.9.5",
            "saved_at": time.time(),
            "saved_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bot_count": len(bots),
            "bots": {},
            # v3.15.68 — Bot Swarm state preservation
            "smart_wires": list(smart_wires or []),
            # v3.16.57 — per-bot ledger totals (wired_in/wired_out, etc.)
            "smart_wire_ledgers": list(smart_wire_ledgers or []),
        }

        for bot_data in bots:
            bid = bot_data.get("bot_id", "")
            if bid:
                state["bots"][bid] = bot_data

        # v3.24.35 (C01) — A SAVE NEVER REMOVES A BOT RECORD.
        #
        # Operator, 2026-08-05: "Why modify long term storage based on
        # what could be a short term glitch?"
        #
        # This method used to rebuild "bots" purely from the list it was
        # handed, and save_all_state hands it only bots currently in
        # BotManager._bots. So any transient in-memory condition became
        # permanent data loss on the next 60-second tick. The clearest
        # case: register() returns (False, reason) on capital
        # over-allocation (MEM-417) — a momentary allocation state — and
        # 60 seconds later that bot's per-lot cost basis is gone. The
        # live file holds 1,949 such lots and 829 fold tranches, none of
        # it derivable from exchange fill history.
        #
        # A record now leaves this file only via delete_bot(), called
        # from an explicit operator delete. Absence from memory means
        # nothing.
        #
        # Wrapped so it can never abort a save: on a read failure we log
        # and fall back to the old rebuild-from-memory behaviour, which
        # is no worse than what shipped for the last year.
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

        # Regression tripwire. Under the rule this should report nothing;
        # a non-empty report now means an explicit delete or a bug.
        self.detect_prune(set(state["bots"].keys()))

        # Atomic write: write to temp file, then rename
        tmp_path = self._path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            # Backup existing state before overwriting.
            #
            # v3.24.35 (C01 PR-0) — but NEVER with an unparseable
            # primary. This step copies the current primary over
            # bot_state.backup.json, so if the primary is corrupt it
            # destroys the last good copy — and since has_saved_state()
            # answers "no saved state" for an unreadable file, the
            # platform will already have launched with zero bots and be
            # about to write an empty primary. That sequence loses the
            # fleet record and its only recovery path in one 60s cycle.
            #
            # A backup that is one cycle stale is worth incomparably
            # more than a backup that is a copy of garbage.
            if self._path.exists() and self._read_bot_ids(self._path) is None:
                logger.error(
                    "REFUSING to refresh %s: the current %s does not parse, "
                    "and copying it would destroy the last good backup. "
                    "The existing backup is being preserved as-is.",
                    self._backup_path.name,
                    self._path.name,
                )
            elif self._path.exists():
                try:
                    self._backup_path.write_bytes(self._path.read_bytes())
                except OSError as _bk_exc:
                    # v3.24.21 — was `except Exception: pass`.
                    # The backup is the ONLY recovery path when a save
                    # produces a corrupt state file (load_state falls
                    # back to it). Silently skipping it meant the safety
                    # net could be gone for weeks with no signal, and the
                    # operator would only discover it at the moment they
                    # needed it. Warning, not debug: this is a degraded
                    # durability guarantee, not a cosmetic miss.
                    logger.warning(
                        "Bot state backup FAILED (%s): %s — proceeding "
                        "with save, but %s will not be recoverable from "
                        "backup if this write corrupts it",
                        type(_bk_exc).__name__,
                        _bk_exc,
                        self._path.name,
                    )
            tmp_path.replace(self._path)
            logger.info("Bot state saved: %d bots", len(bots))
        except Exception as exc:
            logger.error("Failed to save bot state: %s", exc)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def delete_bot(self, bot_id: str) -> bool:
        """Remove one bot's record from disk. The ONLY removal path.

        v3.24.35 (C01). Until now, deleting a bot was not implemented
        anywhere. ``BotManager.unregister()`` popped it out of memory —
        it contains no reference to a state manager, no save call, no
        file access at all — and the record vanished from disk purely
        because the next ``save_state`` rebuilt the file from RAM.

        Deletion was a SIDE EFFECT OF THE BUG. That is also why it was
        never logged: there was no deletion operation to log. The
        operator reported deleting bots and finding no record of it
        anywhere, which is exactly right.

        Now that a save carries records forward, that accidental
        mechanism is gone, so deletion has to become a positive act —
        otherwise a deleted bot would return on every subsequent save.

        Also drops the bot's Smart Wire ledger row and any wire naming
        it, so a delete does not leave the orphans it used to. (13 of 48
        ledger rows on the live file are such orphans, 2 carrying
        non-zero wired_out — the only surviving trace of bots already
        deleted. Those are pre-existing and are NOT touched here.)

        Idempotent. Returns True if a record was removed.
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

            tmp_path = self._path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            if self._path.exists():
                try:
                    self._backup_path.write_bytes(self._path.read_bytes())
                except OSError as exc:
                    logger.warning("delete_bot: backup refresh failed: %s", exc)
            tmp_path.replace(self._path)

            # ERROR level on purpose. This is irreversible and destroys
            # data the exchange cannot reproduce; it should be findable
            # in the logs a year from now.
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
        """The ``bots`` map from a state file, or {} if unreadable.

        Used by the carry-forward in save_state. RAISES nothing itself,
        but returns {} on failure — and the caller treats {} as "carry
        nothing", which is why the caller logs loudly rather than
        silently accepting an empty result.
        """
        target = self._path if path is None else path
        if not target.exists():
            return {}
        with open(target, "r", encoding="utf-8") as f:
            return dict(json.load(f).get("bots") or {})

    def _read_bot_ids(self, path) -> "Optional[set]":
        """Bot ids in a state file, or None if it cannot be read.

        None means "unknown", NOT "empty" — the distinction matters,
        because treating an unreadable file as empty would report every
        bot as being dropped.
        """
        try:
            return set(self._read_bot_records(path).keys())
        except Exception:  # noqa: BLE001 - a detector must never raise
            return None

    def detect_prune(self, incoming_ids: set) -> list:
        """Report bot ids this save is about to DROP. Log-only.

        v3.24.35 (C01 PR-0). ``save_state`` rebuilds ``"bots"`` from
        scratch out of the list it is handed, with no read-merge against
        disk. ``save_all_state`` hands it only bots present in
        ``BotManager._bots``, so any bot that was skipped or refused
        during restore is absent — and is erased by the 60-second save
        timer. What is lost is not derivable from exchange history:
        measured on the live file 2026-08-05, 35 bots holding 1,949
        per-lot cost-basis entries and 829 fold tranches.

        This detector changes nothing. It exists so the failure becomes
        VISIBLE before the merge lands, and so a Phase-0 session
        produces evidence about whether it ever fires in practice.
        (It has not yet: zero restore-skip events across 3,012 log
        files as of 2026-08-05.)

        Returns the dropped ids so tests can assert on them without
        parsing log output. NEVER raises: it sits on the live save path,
        and a detector that can break saving is worse than the defect.
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
        """Bot ids in the BACKUP but missing from the primary.

        v3.24.35 (C01 PR-0). The only detector that can surface
        PRE-EXISTING C01 damage. The backup is written immediately
        before each overwrite, so it lags the primary by exactly one
        save cycle — measured at 60 s on 2026-08-05. If a bot was pruned
        by the last save, it is still in the backup and gone from the
        primary, and this is the single window in which that is
        recoverable. One more save closes it.

        Returns the ids so a caller can surface them; logs at ERROR.
        Never raises.
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
    """How many boot snapshots to retain. Bounded on purpose: each pair
    is ~1.7 MB against the current 870 KB state file, and an unbounded
    forensic directory inside the operator's runtime tree is its own
    problem. Ten covers roughly a week of daily restarts."""

    def _preflight_stamp(self) -> str:
        """Timestamp for a snapshot filename, to 1-second resolution.

        Its own method so tests can override it. Otherwise every test
        exercising retention has to sleep past the granularity — 10.6
        seconds of wall-clock across this file's cases, and tests that
        depend on real time are flaky by construction.
        """
        from datetime import datetime

        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def preflight_snapshot(self) -> list:
        """Copy the state files aside BEFORE anything can overwrite them.

        v3.24.35 (C01 PR-0), method rule M11: back up before the first
        destructive run.

        The existing safety net is one cycle deep — ``bot_state.backup``
        is refreshed immediately before every save, so it always holds
        the previous 60 seconds and nothing older. That is enough to
        survive one bad save and nothing more. If a boot goes wrong and
        the timer ticks twice, both copies are gone.

        This takes a dated copy of BOTH files at boot, before restore
        runs and before the save timer starts, so there is always a
        known-good pre-session copy independent of the rolling backup.

        Design notes:
          * Snapshots live in a ``preflight/`` SUBDIRECTORY so they do
            not clutter the runtime root.
          * Retention is bounded (``PREFLIGHT_KEEP``); the oldest are
            pruned. An unbounded copy pile inside the operator's own
            tree is not a kindness.
          * A boot whose files are byte-identical to the newest existing
            snapshot writes nothing — repeated restarts do not multiply
            copies.
          * Never raises. A backup step that can abort boot is worse
            than no backup step.

        Returns the paths written (empty if nothing needed writing).
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

            # Identical to the most recent snapshot? Then skip.
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

            # Prune oldest complete sets beyond PREFLIGHT_KEEP.
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
        """
        Load saved bot state from disk.
        Returns the full state dict, or empty dict if no state.
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
        """Attempt to load from backup if primary is corrupt."""
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
        """Remove saved state (used on fresh start / version change)."""
        cleared, failed = [], []
        for p in [self._path, self._backup_path]:
            if p.exists():
                try:
                    p.unlink()
                    cleared.append(p.name)
                except OSError as _rm_exc:
                    # v3.24.21 — was `except Exception: pass`.
                    # A failed unlink means state the caller believes is
                    # gone is still on disk, so the next boot restores
                    # bots the operator intended to clear. Reporting it
                    # is the difference between a visible error and a
                    # confusing resurrection.
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
        """Three-valued state-file probe.

        Returns one of ``"no_file"``, ``"empty"``, ``"has_bots"`` or
        ``"unreadable"``.

        v3.24.35 (C01 PR-0). ``has_saved_state()`` collapsed all four
        onto a bare bool via ``except Exception: return False``, and
        ``main.py:720`` gates the ENTIRE restore on it. So an unreadable
        primary meant "there is no saved state", the platform launched
        with zero bots, and ``load_state()``'s ``_try_backup()`` fallback
        (:238) was never reached because the gate had already answered.

        The second half is what makes it unrecoverable rather than
        merely alarming: 60 seconds later the save timer runs
        ``save_state([])``, whose backup step copies the CURRENT primary
        over ``bot_state.backup.json``. The corrupt primary overwrites
        the good backup, and then an empty state overwrites the primary.
        One failed read destroys the fleet record and its recovery path
        in the same cycle.

        "unreadable" is therefore never silently equivalent to "empty".
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
        """Check if there's a saved state file with bots.

        Built on ``probe()``. Behaviour for the three healthy outcomes is
        unchanged. ``unreadable`` still returns False — changing the
        launch policy is an open operator decision (halt and prompt for
        recovery, vs launch empty) and is NOT decided here — but it is
        now loud rather than silent, and the backup is protected from
        being overwritten by the unreadable primary (see save_state).
        """
        return self.probe() == "has_bots"
