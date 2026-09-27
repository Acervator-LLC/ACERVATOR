"""Ownership of one Acervator state directory.

``InstanceGuard.evaluate`` returns a ``GuardDecision`` whose verdict falls in
``AUTO_START_PERMITTED`` only when this launch may start the saved fleet with
no prompt. ``read_machine_identity`` builds ``MachineIdentity`` from the
platform machine id, never from a file under ``config_dir``. ``InstanceLock``
holds an exclusive OS handle on ``LOCK_FILENAME``, and ``take_ownership``
writes ``CLAIM_FILENAME``.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from src.core.io_utils import atomic_write_json

logger = logging.getLogger("acervator.instance")

CLAIM_FILENAME = "instance_claim.json"
"""Name of the file ``write_claim`` writes under ``config_dir``."""

LOCK_FILENAME = "instance.lock"
"""Name of the file ``InstanceLock`` opens and holds for the process's life."""

CLAIM_VERSION = 1

VERDICT_FIRST_RUN = "first_run"
"""No ``InstanceClaim`` and no saved fleet; ``_decide`` permits a silent start."""

VERDICT_SAME_MACHINE = "same_machine"
"""The ``InstanceClaim`` names this machine and ``InstanceLock`` was acquired."""

VERDICT_LIVE_INSTANCE = "live_instance"
"""``InstanceLock.acquire`` returned ``LOCK_HELD_BY_OTHER``."""

VERDICT_FOREIGN_MACHINE = "foreign_machine"
"""The stored ``InstanceClaim.fingerprint`` differs from this machine's."""

VERDICT_UNCLAIMED_FLEET = "unclaimed_fleet"
"""A saved fleet with no ``InstanceClaim`` beside it; ``_decide`` refuses."""

VERDICT_UNCERTAIN = "uncertain"
"""``_decide`` could not establish ownership and refuses."""

AUTO_START_PERMITTED = frozenset({VERDICT_FIRST_RUN, VERDICT_SAME_MACHINE})
"""The verdicts ``GuardDecision.permits_auto_start`` reports as True."""

STRENGTH_STRONG = "strong"
"""``read_machine_identity`` read the platform machine id."""

STRENGTH_WEAK = "weak"
"""``read_machine_identity`` hashed ``host`` and ``os_user`` alone."""

LOCK_ACQUIRED = "acquired"
LOCK_HELD_BY_OTHER = "held_by_other"
LOCK_UNAVAILABLE = "unavailable"

_FINGERPRINT_SALT = "acervator-instance-guard-v1"
"""Prefix ``read_machine_identity`` hashes with the platform machine id."""


def _try_lock(fd: int) -> Optional[bool]:
    """Return True when ``fd`` was locked, False when another process holds it.

    None means neither ``msvcrt`` nor ``fcntl`` could be imported.
    """
    if os.name == "nt":
        try:
            import msvcrt
        except ImportError:
            return None
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    try:
        import fcntl
    except ImportError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _try_unlock(fd: int) -> None:
    """Unlock ``fd``, which ``_try_lock`` locked; a failure leaves it to the close."""
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except (OSError, ImportError):
        logger.debug("instance lock release fell through to close")


@dataclass(frozen=True)
class MachineIdentity:
    """What this process establishes about the machine it runs on."""

    fingerprint: str
    host: str
    os_user: str
    platform: str
    strength: str
    source: str

    @property
    def label(self) -> str:
        """``host`` and ``os_user`` in one string."""
        return f"{self.host} ({self.os_user})"

    @property
    def short_fingerprint(self) -> str:
        """The first twelve characters of ``fingerprint``."""
        return self.fingerprint[:12]


def _machine_id_windows() -> Optional[str]:
    """Return ``MachineGuid`` from the Windows registry, or None.

    ``winreg`` reads it under ``HKEY_LOCAL_MACHINE``, outside any ``config_dir``
    a copy could carry.
    """
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
    except OSError as exc:
        logger.debug("MachineGuid could not be read: %s", exc)
        return None
    text = str(value).strip()
    return text or None


def _machine_id_linux() -> Optional[str]:
    """Return ``/etc/machine-id`` or the D-Bus copy, or None.

    A disk-image clone carries the same value; ``_decide`` also compares
    ``InstanceClaim.host`` against ``MachineIdentity.host``.
    """
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return None


def _machine_id_darwin() -> Optional[str]:
    """Return ``IOPlatformUUID`` from ``/usr/sbin/ioreg``, or None.

    ``subprocess.run`` names the absolute path with a fixed argument list and
    ``shell=False``.
    """
    try:
        completed = subprocess.run(
            ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("ioreg could not be run: %s", exc)
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        if "IOPlatformUUID" not in line:
            continue
        _, _, tail = line.partition("=")
        return tail.strip().strip('"') or None
    return None


def _platform_machine_id() -> tuple[Optional[str], str]:
    """Return the machine id for ``sys.platform`` and the source that gave it."""
    if sys.platform.startswith("win"):
        return _machine_id_windows(), "windows:MachineGuid"
    if sys.platform.startswith("linux"):
        return _machine_id_linux(), "linux:/etc/machine-id"
    if sys.platform == "darwin":
        return _machine_id_darwin(), "darwin:IOPlatformUUID"
    return None, f"unsupported:{sys.platform}"


def _safe_host() -> str:
    try:
        return socket.gethostname() or "unknown-host"
    except OSError:
        return "unknown-host"


def _safe_user() -> str:
    try:
        return getpass.getuser() or "unknown-user"
    except (OSError, KeyError):
        return "unknown-user"


def read_machine_identity() -> MachineIdentity:
    """Return a ``MachineIdentity`` derived from outside ``config_dir``.

    ``fingerprint`` covers the platform machine id alone when one is available;
    ``host`` and ``os_user`` sit beside it and ``_decide`` compares them apart.
    """
    host = _safe_host()
    user = _safe_user()
    machine_id, source = _platform_machine_id()
    if machine_id:
        material = f"{_FINGERPRINT_SALT}|{sys.platform}|{machine_id}"
        strength = STRENGTH_STRONG
    else:
        # Two machines built from one image share host and os_user.
        material = f"{_FINGERPRINT_SALT}|weak|{sys.platform}|{host}|{user}"
        strength = STRENGTH_WEAK
        source = f"{source}:absent"
    return MachineIdentity(
        fingerprint=hashlib.sha256(material.encode("utf-8")).hexdigest(),
        host=host,
        os_user=user,
        platform=sys.platform,
        strength=strength,
        source=source,
    )


@dataclass(frozen=True)
class InstanceClaim:
    """One ``CLAIM_FILENAME`` payload, as ``read_claim_state`` returns it."""

    fingerprint: str
    host: str
    os_user: str
    platform: str
    strength: str
    pid: int
    claimed_at: float
    claimed_at_human: str
    app_version: str

    @property
    def label(self) -> str:
        return f"{self.host} ({self.os_user})"

    @property
    def short_fingerprint(self) -> str:
        return self.fingerprint[:12]

    def age_seconds(self, now: Optional[float] = None) -> float:
        return max(0.0, (now if now is not None else time.time()) - self.claimed_at)


def _claim_path(config_dir: Path) -> Path:
    return Path(config_dir) / CLAIM_FILENAME


def read_claim(config_dir: Path) -> Optional[InstanceClaim]:
    """Return the ``InstanceClaim`` under ``config_dir``, or None.

    None covers both the absent and the unreadable state; ``read_claim_state``
    tells them apart and ``_decide`` reads that state.
    """
    state, claim = read_claim_state(config_dir)
    return claim if state == "present" else None


def read_claim_state(config_dir: Path) -> tuple[str, Optional[InstanceClaim]]:
    """Return "present", "absent" or "unreadable" with the ``InstanceClaim``."""
    path = _claim_path(config_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ("absent", None)
    except OSError as exc:
        logger.warning("instance claim could not be read (%s): %s", path, exc)
        return ("unreadable", None)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("instance claim will not parse (%s): %s", path, exc)
        return ("unreadable", None)
    if not isinstance(data, dict):
        logger.warning("instance claim is not an object (%s)", path)
        return ("unreadable", None)
    fingerprint = str(data.get("fingerprint", "")).strip()
    if not fingerprint:
        logger.warning("instance claim carries no fingerprint (%s)", path)
        return ("unreadable", None)
    try:
        claimed_at = float(data.get("claimed_at", 0.0))
    except (TypeError, ValueError):
        claimed_at = 0.0
    try:
        pid = int(data.get("pid", 0))
    except (TypeError, ValueError):
        pid = 0
    return (
        "present",
        InstanceClaim(
            fingerprint=fingerprint,
            host=str(data.get("host", "unknown-host")),
            os_user=str(data.get("os_user", "unknown-user")),
            platform=str(data.get("platform", "unknown")),
            strength=str(data.get("strength", STRENGTH_WEAK)),
            pid=pid,
            claimed_at=claimed_at,
            claimed_at_human=str(data.get("claimed_at_human", "")),
            app_version=str(data.get("app_version", "")),
        ),
    )


def write_claim(
    config_dir: Path, identity: MachineIdentity, app_version: str = ""
) -> Path:
    """Write ``CLAIM_FILENAME`` under ``config_dir`` via ``atomic_write_json``.

    The payload carries every ``MachineIdentity`` field, the current pid and
    ``app_version``, and the path written is returned.
    """
    directory = Path(config_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CLAIM_FILENAME
    payload = {
        "claim_version": CLAIM_VERSION,
        "fingerprint": identity.fingerprint,
        "host": identity.host,
        "os_user": identity.os_user,
        "platform": identity.platform,
        "strength": identity.strength,
        "source": identity.source,
        "pid": os.getpid(),
        "claimed_at": time.time(),
        "claimed_at_human": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "app_version": app_version,
    }
    atomic_write_json(path, payload, indent=2)
    return path


class InstanceLock:
    """An exclusive OS handle on ``LOCK_FILENAME``, held for the process's life.

    Two copies on one machine share a ``MachineIdentity.fingerprint``, and only
    ``acquire`` separates them; a dead process leaves the handle free.
    """

    def __init__(self, config_dir: Path) -> None:
        self._path = Path(config_dir) / LOCK_FILENAME
        self._fd: Optional[int] = None
        self.state: str = LOCK_UNAVAILABLE

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> str:
        """Return ``LOCK_ACQUIRED``, ``LOCK_HELD_BY_OTHER`` or ``LOCK_UNAVAILABLE``."""
        if self._fd is not None:
            return self.state
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self._path), os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            logger.warning(
                "instance lock file could not be opened (%s): %s", self._path, exc
            )
            self.state = LOCK_UNAVAILABLE
            return self.state
        taken = _try_lock(fd)
        if taken is None:
            os.close(fd)
            self.state = LOCK_UNAVAILABLE
            return self.state
        if not taken:
            os.close(fd)
            self.state = LOCK_HELD_BY_OTHER
            return self.state
        self._fd = fd
        self.state = LOCK_ACQUIRED
        try:
            os.write(fd, f"pid={os.getpid()}\n".encode("utf-8"))
        except OSError:
            # The pid text is a note; the fd is what LOCK_ACQUIRED reports.
            logger.debug("instance lock note not written")
        return self.state

    def release(self) -> None:
        """Unlock and close the handle; ``LOCK_FILENAME`` is left on disk.

        ``state`` returns to ``LOCK_UNAVAILABLE`` and ``acquire`` can take the
        handle again.
        """
        fd, self._fd = self._fd, None
        if fd is None:
            return
        _try_unlock(fd)
        try:
            os.close(fd)
        except OSError:
            pass
        self.state = LOCK_UNAVAILABLE


def lock_is_held(config_dir: Path) -> bool:
    """True while another process holds ``LOCK_FILENAME`` under ``config_dir``.

    Nothing is written and no ``InstanceClaim`` is made, so a step outside the
    application can ask whether the fleet is running without taking ownership.
    An absent lock file answers False; a file that cannot be opened answers True,
    because a held handle is the reason a reader is refused.
    """
    path = Path(config_dir) / LOCK_FILENAME
    if not path.is_file():
        return False
    try:
        fd = os.open(str(path), os.O_RDWR)
    except OSError as exc:
        logger.debug("instance lock could not be opened (%s): %s", path, exc)
        return True
    try:
        taken = _try_lock(fd)
        if taken:
            _try_unlock(fd)
        return taken is False
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


@dataclass(frozen=True)
class GuardDecision:
    """One ``verdict`` with the ``MachineIdentity`` and ``InstanceClaim`` behind it."""

    verdict: str
    permits_auto_start: bool
    headline: str
    detail: str
    identity: MachineIdentity
    claim: Optional[InstanceClaim]
    claim_state: str
    lock_state: str
    fleet_bot_count: int

    @property
    def owner_line(self) -> str:
        """The ``claim`` label, its short fingerprint and its age, in one line."""
        if self.claim is None:
            return "This fleet carries no record of the machine that last used it."
        age = self.claim.age_seconds()
        return (
            f"Last used by {self.claim.label} "
            f"[{self.claim.short_fingerprint}] "
            f"on {self.claim.claimed_at_human or 'an unrecorded date'} "
            f"({_age_phrase(age)} ago)."
        )

    @property
    def this_machine_line(self) -> str:
        return (
            f"This machine is {self.identity.label} "
            f"[{self.identity.short_fingerprint}], "
            f"identity {self.identity.strength}."
        )

    @property
    def consent_is_possible(self) -> bool:
        """True when ``lock_state`` is ``LOCK_ACQUIRED``.

        On any other ``lock_state`` ``InstanceGuard.take_ownership`` refuses the
        write, and no consent is collected.
        """
        return self.lock_state == LOCK_ACQUIRED

    @property
    def consequence_line(self) -> str:
        """The sentence naming ``fleet_bot_count`` and the shared exchange account."""
        return (
            f"If you continue, this machine takes ownership and starts "
            f"{self.fleet_bot_count} bot(s) against the live exchange "
            f"account. If the other copy is still running, both copies "
            f"will trade the same wallet and each will read the other's "
            f"fills as unexplained drift."
        )


def _age_phrase(seconds: float) -> str:
    """Return ``seconds`` as a phrase in seconds, minutes, hours or days."""
    if seconds < 90.0:
        return f"{int(seconds)} seconds"
    if seconds < 5400.0:
        return f"{int(seconds / 60.0)} minutes"
    if seconds < 172800.0:
        return f"{int(seconds / 3600.0)} hours"
    return f"{int(seconds / 86400.0)} days"


def _describe(
    verdict: str, claim: Optional[InstanceClaim], identity: MachineIdentity
) -> tuple[str, str]:
    """Return the headline and detail text for one ``verdict``."""
    if verdict == VERDICT_FIRST_RUN:
        return (
            "This machine now owns this Acervator directory.",
            "No saved fleet and no previous owner were found, so "
            "nothing can collide.",
        )
    if verdict == VERDICT_SAME_MACHINE:
        return (
            "This machine owns this fleet.",
            "The recorded owner is this machine and no other copy "
            "is running, so the fleet resumes as it always has.",
        )
    if verdict == VERDICT_LIVE_INSTANCE:
        return (
            "Another Acervator is running on this machine.",
            "A second copy already holds the exclusive handle on "
            f"{LOCK_FILENAME}. Two copies on one account fight each "
            "other. Close the other copy, then launch again.",
        )
    if verdict == VERDICT_FOREIGN_MACHINE:
        owner = claim.label if claim else "another machine"
        return (
            "This fleet belongs to a different machine.",
            f"The saved fleet records {owner} as its owner, and this "
            f"machine is {identity.label}. This is what a copied "
            "Acervator directory looks like. If the other machine is "
            "still trading this account, DO NOT start the bots here.",
        )
    if verdict == VERDICT_UNCLAIMED_FLEET:
        return (
            "This fleet has no recorded owner.",
            "A saved fleet is present with no owner beside it. That "
            "happens on the first launch after this guard was added, "
            "and it also happens when the directory was copied from a "
            "build that had no guard. Nothing on disk separates the "
            "two, so you are being asked once.",
        )
    return (
        "Ownership of this fleet could not be established.",
        "The guard could not prove this machine is the owner. It "
        "refuses rather than guess, because the cost of guessing "
        "wrong is two copies trading one account.",
    )


class InstanceGuard:
    """Decides whether this launch may start the saved fleet silently.

    ``config_dir`` has no default; every caller names the directory it means.
    """

    def __init__(self, config_dir: Path, app_version: str = "") -> None:
        self._dir = Path(config_dir)
        self._app_version = app_version
        self._lock = InstanceLock(self._dir)
        self._identity: Optional[MachineIdentity] = None
        self._decision: Optional[GuardDecision] = None

    @property
    def config_dir(self) -> Path:
        return self._dir

    @property
    def lock(self) -> InstanceLock:
        return self._lock

    @property
    def decision(self) -> Optional[GuardDecision]:
        return self._decision

    def evaluate(self, fleet_bot_count: int) -> GuardDecision:
        """Return a ``GuardDecision`` for ``fleet_bot_count``, writing no claim.

        Only ``take_ownership`` writes ``CLAIM_FILENAME``; a refusal leaves the
        previous ``InstanceClaim`` in place.
        """
        started = time.monotonic()
        identity = read_machine_identity()
        self._identity = identity
        claim_state, claim = read_claim_state(self._dir)
        lock_state = self._lock.acquire()
        verdict = _decide(identity, claim_state, claim, lock_state, fleet_bot_count)
        headline, detail = _describe(verdict, claim, identity)
        decision = GuardDecision(
            verdict=verdict,
            permits_auto_start=verdict in AUTO_START_PERMITTED,
            headline=headline,
            detail=detail,
            identity=identity,
            claim=claim,
            claim_state=claim_state,
            lock_state=lock_state,
            fleet_bot_count=fleet_bot_count,
        )
        self._decision = decision
        _emit_decision(decision, time.monotonic() - started)
        if decision.permits_auto_start:
            logger.info("instance guard: %s - %s", verdict, decision.headline)
        else:
            logger.warning(
                "instance guard REFUSED a silent fleet start " "(%s): %s",
                verdict,
                decision.detail,
            )
        return decision

    def take_ownership(self) -> bool:
        """Write this machine's ``InstanceClaim`` and return True on success.

        It returns False when ``InstanceLock.state`` is not ``LOCK_ACQUIRED``.
        """
        if self._lock.state != LOCK_ACQUIRED:
            logger.warning(
                "instance guard will not write a claim without "
                "the exclusive handle (lock state %s)",
                self._lock.state,
            )
            return False
        identity = self._identity or read_machine_identity()
        try:
            write_claim(self._dir, identity, self._app_version)
        except OSError as exc:
            logger.error("instance claim could not be written (%s): %s", self._dir, exc)
            return False
        logger.info("instance guard: %s now owns %s", identity.label, self._dir)
        return True

    def release(self) -> None:
        """Release the ``InstanceLock`` handle."""
        self._lock.release()


def _decide(
    identity: MachineIdentity,
    claim_state: str,
    claim: Optional[InstanceClaim],
    lock_state: str,
    fleet_bot_count: int,
) -> str:
    """Return the verdict for one ``identity``, ``claim_state``, claim and lock.

    ``LOCK_HELD_BY_OTHER`` outranks every other input, and any state that does
    not prove ownership ends at ``VERDICT_UNCERTAIN``.
    """
    if lock_state == LOCK_HELD_BY_OTHER:
        return VERDICT_LIVE_INSTANCE
    if lock_state != LOCK_ACQUIRED:
        return VERDICT_UNCERTAIN
    if claim_state == "unreadable":
        return VERDICT_UNCERTAIN
    if claim is None:
        return VERDICT_FIRST_RUN if fleet_bot_count <= 0 else VERDICT_UNCLAIMED_FLEET
    if identity.strength != STRENGTH_STRONG or claim.strength != STRENGTH_STRONG:
        return VERDICT_UNCERTAIN
    if claim.fingerprint != identity.fingerprint:
        return VERDICT_FOREIGN_MACHINE
    if claim.host != identity.host or claim.os_user != identity.os_user:
        return VERDICT_UNCERTAIN
    return VERDICT_SAME_MACHINE


def _emit_decision(decision: GuardDecision, elapsed: float) -> None:
    """Emit the auto-start postcondition for one ``decision``.

    ``expected`` is rebuilt from ``lock_state``, ``claim_state`` and the
    ``MachineIdentity`` comparison, never from ``decision.verdict``.
    """
    try:
        from src.core.signal_contract import emit as _guard_emit

        claim = decision.claim
        identity = decision.identity
        evidence_permits = bool(
            decision.lock_state == LOCK_ACQUIRED
            and decision.claim_state != "unreadable"
            and (
                (claim is None and decision.fleet_bot_count <= 0)
                or (
                    claim is not None
                    and claim.strength == STRENGTH_STRONG
                    and identity.strength == STRENGTH_STRONG
                    and claim.fingerprint == identity.fingerprint
                    and claim.host == identity.host
                    and claim.os_user == identity.os_user
                )
            )
        )
        _guard_emit(
            "instance.17.001.postcondition.auto_start_permitted",
            decision.permits_auto_start,
            expected=evidence_permits,
            context={
                "verdict": decision.verdict,
                "lock": decision.lock_state,
                "claim": decision.claim_state,
                "this_machine": identity.label,
                "this_fingerprint": identity.short_fingerprint,
                "identity_strength": identity.strength,
                "owner_machine": claim.label if claim else None,
                "owner_fingerprint": claim.short_fingerprint if claim else None,
                "owner_age_seconds": round(claim.age_seconds(), 1) if claim else None,
                "fleet_bots": decision.fleet_bot_count,
            },
            duration=elapsed,
        )
    except Exception as exc:  # noqa: BLE001 - a pin never breaks the guard
        logger.debug("instance guard pin suppressed: %s", exc)


AUTHORISED_ALREADY_OWNER = "already_owner"
AUTHORISED_BY_OPERATOR = "operator_consent"
WITHHELD_BY_OPERATOR = "operator_refused"
WITHHELD_NO_EXCLUSIVE_HANDLE = "no_exclusive_handle"


def authorise_auto_start(
    guard: "InstanceGuard",
    decision: GuardDecision,
    ask_consent: Callable[[GuardDecision], bool],
) -> tuple[bool, str]:
    """Return whether the fleet may start, with one of the four reason constants.

    ``ask_consent`` runs only when ``decision.permits_auto_start`` is False, and
    a granted consent still needs ``guard.take_ownership`` to return True.
    """
    if decision.permits_auto_start:
        return (True, AUTHORISED_ALREADY_OWNER)
    try:
        granted = bool(ask_consent(decision))
    except Exception as exc:  # noqa: BLE001 - no surface means no consent
        logger.error(
            "instance consent could not be collected (%s). "
            "Treating it as a refusal.",
            exc,
        )
        return (False, WITHHELD_BY_OPERATOR)
    if not granted:
        logger.warning(
            "instance guard: the operator withheld consent; " "the fleet stays idle."
        )
        return (False, WITHHELD_BY_OPERATOR)
    if not guard.take_ownership():
        logger.error(
            "instance guard: consent was given but this process "
            "does not hold the exclusive handle, so another "
            "Acervator is running. The fleet stays idle."
        )
        return (False, WITHHELD_NO_EXCLUSIVE_HANDLE)
    return (True, AUTHORISED_BY_OPERATOR)
