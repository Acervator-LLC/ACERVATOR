r"""
instance_guard.py - one Acervator starts a fleet; a second one must ask
=======================================================================

Issue #96. Every bot reconciles its holdings against the exchange
balance. Two copies of Acervator on one Coinbase account read the same
wallet, act on it, and each reads the other copy's fills as unexplained
drift. That is the Target Delta condition of issue #65, made continuous.

Before this module the tree held no guard at all: no lock file, no PID
claim, no `QSharedMemory`, no `QLocalServer`, no mutex and no socket
bind. `bot_state.json` and `reservation_state.json` carry no owner, no
host and no lease, so the last writer wins. The application also starts
every idle bot about 9.25 seconds after launch (`main.py:970`, `:1005`,
`:1437-1457`), which turns the hazard into a ten-second one.

WHAT THIS MODULE DOES, AND WHAT IT DELIBERATELY DOES NOT
--------------------------------------------------------
It answers ONE question at launch: **may this process start the saved
fleet without asking the operator?** It answers with a verdict and a
sentence the operator can read. It never starts a bot, never stops one,
and never touches `bot_state.json`.

THE DISTINCTION IT IS BUILT TO DRAW
-----------------------------------
The same machine resuming its own fleet after a crash or a reboot is a
FEATURE. `StateRestoreMixin.restore_bots_from_state` in
`src/trading/container/restore.py` records `_was_running` for exactly
that reason. A repair that makes the operator hand-start 37 bots after every
crash is a worse product than the defect.

A DIFFERENT machine adopting that fleet is the hazard. So the guard has
to tell those two apart, and the whole design turns on one property:

**THE MACHINE IDENTITY IS NEVER READ OUT OF THE STATE DIRECTORY.**

A machine id written into `~/.acervator/` travels with a copy of
`~/.acervator/`, so it identifies nothing - a copy would present the
original's id and pass. This module derives the identity from a fact
that lives OUTSIDE that directory and cannot be copied with it:

    Windows   HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid
    Linux     /etc/machine-id, then /var/lib/dbus/machine-id
    macOS     IOPlatformUUID from /usr/sbin/ioreg

The claim file inside `~/.acervator/` holds only the PREVIOUS owner's
derived value. Copying the directory copies that value, and the copy
then computes its OWN value from its own host and finds they disagree.
The copy is what makes the mismatch visible, which is why the copy case
is caught rather than missed.

`uuid.getnode()` is NOT used. Measured on the operator's own machine
2026-08-23: it returns `0xe93f41f2586c` with the locally-administered
bit set, which is a virtual adapter, and virtual adapters appear and
vanish when Hyper-V, WSL or a VPN is installed. An identity that changes
when a VPN is installed would refuse the operator's own fleet.

THE DEFAULT WHEN IT CANNOT TELL IS TO REFUSE
---------------------------------------------
A guard that assumes safety when it is uncertain is not a guard. Every
path that cannot PROVE this machine is the owner returns a verdict
outside `AUTO_START_PERMITTED`. That includes a platform id that cannot
be read, a claim file that will not parse, and a lock that cannot be
taken.

WHY THE CONSTRUCTOR TAKES A REQUIRED `config_dir`
--------------------------------------------------
The operator's Acervator is running and trading real money while this
code is written and tested. A default of `~/.acervator` would let one
forgotten argument in one test write a lock into the live directory. The
parameter therefore has NO default: a caller must name the directory it
means, and every test names a temporary one.
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
"""The owner claim. Written only when ownership is granted or taken."""

LOCK_FILENAME = "instance.lock"
"""The exclusive OS handle. Held open for the life of the process."""

CLAIM_VERSION = 1

# --------------------------------------------------------------------- #
# Verdicts                                                              #
# --------------------------------------------------------------------- #

VERDICT_FIRST_RUN = "first_run"
"""No claim and no saved fleet. Nothing exists to start, so nothing can
collide. The claim is written and the launch owns the directory."""

VERDICT_SAME_MACHINE = "same_machine"
"""The claim names THIS machine and no other process holds the lock.
This is the crash-recovery and reboot path, and it must stay silent."""

VERDICT_LIVE_INSTANCE = "live_instance"
"""Another process holds the lock right now. One machine, two copies."""

VERDICT_FOREIGN_MACHINE = "foreign_machine"
"""The claim names a different machine. This is the copied-directory
case: the claim travelled with the files, the machine identity did not."""

VERDICT_UNCLAIMED_FLEET = "unclaimed_fleet"
"""A saved fleet exists with no claim beside it. Two causes produce this
and no evidence separates them: the first launch of a build that carries
this guard, and a directory copied from a build that did not. The guard
refuses and asks, because guessing here is guessing about real money."""

VERDICT_UNCERTAIN = "uncertain"
"""The guard could not establish ownership. A platform id that would not
read, a claim that would not parse, a lock that could not be taken, or a
partial match. Fail closed."""

AUTO_START_PERMITTED = frozenset({VERDICT_FIRST_RUN, VERDICT_SAME_MACHINE})
"""The only two verdicts that allow a silent fleet start."""

STRENGTH_STRONG = "strong"
"""The platform's own machine id was read. It lives outside the state
directory, so a copy of that directory cannot carry it."""

STRENGTH_WEAK = "weak"
"""No platform machine id. Host name and OS user are all that is left,
and both are trivially equal across two cloud machines built from one
image, so a weak identity never proves ownership."""

LOCK_ACQUIRED = "acquired"
LOCK_HELD_BY_OTHER = "held_by_other"
LOCK_UNAVAILABLE = "unavailable"

_FINGERPRINT_SALT = "acervator-instance-guard-v1"
"""Domain separation. The digest of a machine id is not the machine id,
so the claim file never carries the raw platform identifier."""


# --------------------------------------------------------------------- #
# Machine identity                                                      #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class MachineIdentity:
    """What this process can establish about the machine it runs on."""

    fingerprint: str
    host: str
    os_user: str
    platform: str
    strength: str
    source: str

    @property
    def label(self) -> str:
        """The short name the operator recognises on sight."""
        return f"{self.host} ({self.os_user})"

    @property
    def short_fingerprint(self) -> str:
        """Twelve hex characters. Enough for a human to compare two."""
        return self.fingerprint[:12]


def _machine_id_windows() -> Optional[str]:
    """Read `MachineGuid` from the registry.

    Windows writes this value at install time. It survives every reboot,
    it is not in any user directory, and a copy of `~/.acervator/` cannot
    carry it. It changes when Windows is reinstalled, which is honestly a
    different machine as far as this guard is concerned.
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
    """Read `/etc/machine-id`, then the D-Bus copy.

    systemd generates this at first boot and documents it as stable for
    the life of the installation. Both paths are outside any home
    directory.

    KNOWN LIMIT, STATED RATHER THAN HIDDEN. A machine cloned from a full
    DISK IMAGE carries the image's `/etc/machine-id` until something
    regenerates it. Cloud images normally do regenerate it on first boot,
    but this module cannot verify that from here. The host-name check in
    `compare` is the second gate for exactly that case: two cloud
    machines from one image are given different host names.
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
    """Read `IOPlatformUUID` from the I/O registry.

    macOS holds no stable machine id in a readable file, so the only
    route is the `ioreg` tool. It is called by ABSOLUTE PATH with a fixed
    argument list and no shell, so nothing on `PATH` and nothing in the
    environment can change which program runs.
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
    """Return the platform's own machine id and the source that gave it."""
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
    """Derive this machine's identity from facts outside the state dir.

    The digest covers the platform machine id and nothing else when that
    id is available. Host name and OS user are recorded ALONGSIDE it and
    compared separately, so renaming the machine produces a partial match
    the operator is asked about, rather than a silent refusal he cannot
    explain.
    """
    host = _safe_host()
    user = _safe_user()
    machine_id, source = _platform_machine_id()
    if machine_id:
        material = f"{_FINGERPRINT_SALT}|{sys.platform}|{machine_id}"
        strength = STRENGTH_STRONG
    else:
        # No platform id. Host and user are all that is left, and two
        # cloud machines from one image share both, so this identity is
        # marked weak and can never on its own permit a silent start.
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


# --------------------------------------------------------------------- #
# The claim on disk                                                     #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class InstanceClaim:
    """The previous owner's recorded identity, read back from disk."""

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
    """Return the claim on disk, or None when there is not a usable one.

    None means one of two different things and the CALLER must not merge
    them: the file is absent, or the file is present and unreadable. The
    second is reported as a warning here and lands the caller on
    `VERDICT_UNCERTAIN` through `read_claim_state`, never on the
    permissive `no claim` path.
    """
    state, claim = read_claim_state(config_dir)
    return claim if state == "present" else None


def read_claim_state(config_dir: Path) -> tuple[str, Optional[InstanceClaim]]:
    """Return ("present"|"absent"|"unreadable", claim or None)."""
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
    """Write the claim atomically. Returns the path written.

    Atomic because a claim half-written by a power cut would read as
    `unreadable`, and `unreadable` refuses the operator's own fleet on
    the next launch. The temporary file sits in the same directory so the
    replace is a rename inside one filesystem.
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


# --------------------------------------------------------------------- #
# The exclusive handle                                                  #
# --------------------------------------------------------------------- #


class InstanceLock:
    """An exclusive OS handle on one file, held for the process's life.

    This is the SAME-MACHINE half of the guard, and it is the half the
    machine fingerprint cannot do: two copies on one computer present the
    identical fingerprint, so only the operating system can say which of
    them is running now.

    A crash releases it. The operating system drops every handle a dead
    process held, so the fleet that comes back after a crash finds the
    lock free and resumes without a prompt. That is the behaviour issue
    #96 must not break.
    """

    def __init__(self, config_dir: Path) -> None:
        self._path = Path(config_dir) / LOCK_FILENAME
        self._fd: Optional[int] = None
        self.state: str = LOCK_UNAVAILABLE

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> str:
        """Try to take the handle. Returns one of the three LOCK_ values."""
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
        taken = self._try_lock(fd)
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
            # The handle is what matters. The text is a courtesy for a
            # human reading the directory, so a failed write is not a
            # failed lock and must not be reported as one.
            logger.debug("instance lock note not written")
        return self.state

    @staticmethod
    def _try_lock(fd: int) -> Optional[bool]:
        """True locked, False another process holds it, None no facility."""
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

    def release(self) -> None:
        """Drop the handle. The file itself stays, and that is deliberate:
        deleting it would race a second process that has already opened
        it and would leave two processes locking two different inodes."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
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
        try:
            os.close(fd)
        except OSError:
            pass
        self.state = LOCK_UNAVAILABLE


# --------------------------------------------------------------------- #
# The decision                                                          #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class GuardDecision:
    """One verdict, and every fact the operator needs to judge it."""

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
        """Which machine last wrote the state, and when."""
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
        """Whether consent can be offered at all for this verdict.

        It cannot when another process holds the exclusive handle. That
        copy is not inferred from a file, it is proved by the operating
        system, and no answer the operator gives makes two copies on one
        account safe. The surface therefore states the fact and offers
        no way past it, rather than collecting a consent it must ignore.

        It also cannot when the handle could not be taken at all, because
        this process cannot then promise it is the only one.
        """
        return self.lock_state == LOCK_ACQUIRED

    @property
    def consequence_line(self) -> str:
        """What happens if the operator continues. Say the money part."""
        return (
            f"If you continue, this machine takes ownership and starts "
            f"{self.fleet_bot_count} bot(s) against the live exchange "
            f"account. If the other copy is still running, both copies "
            f"will trade the same wallet and each will read the other's "
            f"fills as unexplained drift."
        )


def _age_phrase(seconds: float) -> str:
    """A duration a person reads at a glance, not a float."""
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
    """Return the headline and the reason for one verdict."""
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

    `config_dir` HAS NO DEFAULT ON PURPOSE. See the module docstring: the
    operator's Acervator is live while this code runs, and a default
    would let one forgotten argument write a lock into the directory his
    running application reads.
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
        """Read the evidence and return the verdict. Writes no claim.

        The claim is written only by `take_ownership`, so a refusal
        leaves the previous owner's record untouched and a second look
        reaches the same verdict.
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
        """Record this machine as the owner. Returns True when written.

        Called on the permitted path to refresh the record, and on the
        refused path ONLY after the operator has consented in the dialog.
        It refuses to write while another process holds the lock: taking
        the record from a copy that is demonstrably alive would tell the
        next launch a lie.
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
        """Drop the exclusive handle at shutdown."""
        self._lock.release()


def _decide(
    identity: MachineIdentity,
    claim_state: str,
    claim: Optional[InstanceClaim],
    lock_state: str,
    fleet_bot_count: int,
) -> str:
    """The whole decision, as one readable ladder.

    Order matters and each rung earns its place.

    1. A live copy dominates everything. It is the only condition proved
       by the operating system rather than inferred from a file.
    2. A lock that could not be taken at all proves nothing, so it is
       uncertain rather than safe.
    3. An unreadable claim is uncertain. It is NOT the same as no claim,
       and merging the two would let a corrupt file open the silent path.
    4. No claim with no fleet is a genuine first run. No claim WITH a
       fleet is the upgrade-or-copy pair, which nothing on disk splits.
    5. A weak identity on either side never proves ownership.
    6. A different fingerprint is a different machine.
    7. A matching fingerprint with a different host or user is a partial
       match: a renamed machine, or two machines cloned from one disk
       image. Both are asked about rather than assumed.
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
    """Pin 17-001. The operator has to be able to see this decision.

    The check is not a restatement of the verdict. `actual` is the flag
    the caller will ACT on, and `expected` is rebuilt from the evidence
    fields on the record - the lock state and the claim comparison -
    without consulting the verdict at all. The two disagree only if the
    ladder and the evidence have come apart, which is the failure a
    reader of this record needs to catch.
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


# --------------------------------------------------------------------- #
# The seam main.py calls                                                #
# --------------------------------------------------------------------- #

AUTHORISED_ALREADY_OWNER = "already_owner"
AUTHORISED_BY_OPERATOR = "operator_consent"
WITHHELD_BY_OPERATOR = "operator_refused"
WITHHELD_NO_EXCLUSIVE_HANDLE = "no_exclusive_handle"


def authorise_auto_start(
    guard: "InstanceGuard",
    decision: GuardDecision,
    ask_consent: Callable[[GuardDecision], bool],
) -> tuple[bool, str]:
    """Return (may the fleet start, the reason in one word).

    THIS FUNCTION EXISTS SO THE SEQUENCE CAN BE TESTED. Written inline in
    `main()` it would sit inside an 841-line function that no test can
    call, and the order of its three steps is the whole point:

      1. An owner never sees a dialog. That is the crash-recovery path
         and it must stay silent.
      2. A refusal from the operator ends it. Nothing else is tried.
      3. Consent is not enough on its own. `take_ownership` still has to
         succeed, and it refuses without the exclusive handle - which
         means another copy is provably alive, and no answer the
         operator gives makes two copies on one account safe.

    `ask_consent` takes the decision and returns a bool. It is passed in
    rather than imported so this module needs no Qt, and so a test can
    supply an operator who says yes and an operator who says no.
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
