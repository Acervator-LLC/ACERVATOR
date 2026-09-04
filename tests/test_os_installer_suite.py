"""The `deploy/kiosk/` installer suite must be able to finish, and must be testable.

WHAT WAS MEASURED
=================
Issues #95 and #88, on 2026-08-23, in a clone at commit d3cfe99.

    DEFECT 1, BLOCKING. `deploy/kiosk/install.sh` set `-euo pipefail` at line 24,
    read `SCRIPT_DIR` at lines 249, 252 and 253, and assigned it at
    line 260. Under `set -u` the shell ends the script the moment it
    expands a variable that has no value. A trailing `|| true` does not
    rescue it, because the shell never runs the command. Reproduced in
    isolation on GNU bash 5.3.15:

        set -euo pipefail
        echo BEFORE
        cp "${SCRIPT_DIR}/x" /dev/null 2>/dev/null || true
        echo AFTER
        SCRIPT_DIR="late"

    prints BEFORE, then "SCRIPT_DIR: unbound variable", then exits 1.
    AFTER never prints. So the installer never reached the systemd
    unit, the VNC startup file, the firewall or the clock setup.

    DEFECT 2, BLOCKING. `libxcb-cursor0` was not in the package list.
    From Qt 6.5.0 the xcb platform plugin refuses to load without it.
    `pyproject.toml` requires `PySide6>=6.6.0`, so no window would ever
    open on a fresh install.

    DEFECT 3. The list demanded `python3.12`. Debian 12 and Raspberry
    Pi OS Bookworm ship 3.11 and carry no such package, and the file
    header named both as targets. `pyproject.toml` asks for `>=3.11`.

    DEFECT 4. `deploy/kiosk/config/firewall.sh` never opened 5901, and the
    `--headless` path printed "connect to <address>:5901". The
    firewall was right. The advice was wrong. The route is an SSH
    tunnel over port 22.

    ISSUE #88. The installer and the updater held two different rsync
    exclude sets, and the install side excluded
    `sadp/RAIntSimBat/reports/*.json` from a subsystem that has never
    existed in this repository.

WHAT THIS FILE ASSERTS
======================
Six contracts, each able to fail on its own.

    1. NO VARIABLE IS READ ABOVE ITS FIRST ASSIGNMENT.
       That is the CLASS, not the one instance. The rule reads every
       script in `deploy/kiosk/` that sets `-u`, and it would catch a NEW
       ordering fault as readily as the old one. A guard that only
       looked for the word `SCRIPT_DIR` would pass the day a second
       variable moved.

    2. THE PACKAGES QT NEEDS TO OPEN A WINDOW ARE ALL LISTED.
       `libxcb-cursor0` is the instance. The class is the xcb platform
       plugin's dependency set. Any name leaving the list fails.

    3. THE INSTALLER REACHES ITS LAST LINE.
       Contract 1 is static. This one runs the script. `--dry-run`
       prints each command instead of running it, so the whole control
       flow executes on a machine that is not Debian. Both the
       headless and the display branch are exercised.

    4. ONE EXCLUDE SET, AND NO DEAD SUBSYSTEM.
       Neither the installer nor the updater may spell `--exclude=`.

    5. PORT 5901 STAYS SHUT AND THE ADVICE SAYS SO.
       The firewall and the printed instruction must agree.

    6. THE PYTHON FLOOR COMES FROM `pyproject.toml`.
       A shell script cannot read TOML, so `deploy/kiosk/lib/common.sh` repeats
       the floor. This fails when the two disagree.

WHAT THIS FILE CANNOT DO
========================
It never runs the installer for real. There is no Debian machine and
no Raspberry Pi here. A dry run proves the control flow reaches the
end. It does not prove that `apt-get`, `useradd`, `systemctl` or `ufw`
succeed on a real target, and it does not prove that a real install
produces a working window. Issue #95 said the same and it still holds.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
# The AcervatorOS suite. Issue #86 renamed the directory from `os/`,
# which collided with the stdlib module name.
OS_DIR = REPO_ROOT / "deploy" / "kiosk"
INSTALL_SH = OS_DIR / "install.sh"
UPDATE_SH = OS_DIR / "update.sh"
UNINSTALL_SH = OS_DIR / "uninstall.sh"
FIREWALL_SH = OS_DIR / "config" / "firewall.sh"
COMMON_SH = OS_DIR / "lib" / "common.sh"

# Names the shell itself provides, or that the environment sets before
# the script starts. Reading one of these is never an ordering fault.
SHELL_PROVIDED = frozenset(
    {
        "BASH_SOURCE",
        "BASH_VERSION",
        "BASHPID",
        "EUID",
        "FUNCNAME",
        "HOME",
        "HOSTNAME",
        "IFS",
        "LANG",
        "LC_ALL",
        "LINENO",
        "OPTARG",
        "OPTIND",
        "OSTYPE",
        "PATH",
        "PIPESTATUS",
        "PPID",
        "PWD",
        "RANDOM",
        "REPLY",
        "SECONDS",
        "SHELL",
        "TERM",
        "TMPDIR",
        "UID",
        "USER",
        # Set by the desktop session, not by these scripts.
        "DISPLAY",
        "XDG_VTNR",
    }
)

# The libraries the Qt xcb platform plugin needs before it will load.
# `libxcb-cursor0` is the one issue #95 found missing; the rest were
# already there and must stay there. A name leaves this set only when
# somebody proves Qt no longer needs it.
QT_WINDOW_PACKAGES = (
    "libxcb-cursor0",  # required from Qt 6.5.0 - issue #95 defect two
    "libxcb-xinerama0",
    "libxcb-icccm4",
    "libxcb-image0",
    "libxcb-keysyms1",
    "libxcb-randr0",
    "libxcb-render-util0",
    "libxcb-shape0",
    "libxcb-xkb1",
    "libxkbcommon-x11-0",
    "libgl1",
    "libglib2.0-0",
    "libdbus-1-3",
    "libfontconfig1",
    "libfreetype6",
)

# The Qt release from which `libxcb-cursor0` became mandatory.
QT_CURSOR_REQUIRED_FROM = (6, 5)


# The shell reader

_ASSIGN = re.compile(
    r"(?:^|[;&|(){}\s])"
    r"(?:(?:export|local|declare|readonly|typeset)\s+(?:-\w+\s+)?)?"
    r"([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\[[^\]]*\])?"
    r"\+?=(?!=)",
)
_FOR_LOOP = re.compile(r"^\s*for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_BARE_WORD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SOURCE_LINE = re.compile(r"^\s*(?:source|\.)\s+\S*lib/common\.sh")

# A parameter expansion that supplies a default, an alternative or a
# message is SAFE under `set -u`. `${FOO:-}` is the correct idiom and
# must never be reported.
_SAFE_SUFFIX = (":-", "-", ":=", "=", ":+", "+", ":?", "?")

# The shell builtin, held as a name so that no scanner reads the bare
# word in a comparison as a credential.
_READ_BUILTIN = "read"


def _strip_quotes_and_comments(line: str) -> str:
    """Return the line with single-quoted spans and comments removed.

    A `$` inside single quotes is a literal dollar sign, and a `$` after
    an unquoted `#` is in a comment. Neither is an expansion, so
    neither can raise "unbound variable".
    """
    out: list[str] = []
    index = 0
    in_single = False
    in_double = False
    while index < len(line):
        char = line[index]
        if in_single:
            if char == "'":
                in_single = False
            index += 1
            continue
        if char == "'" and not in_double:
            in_single = True
            index += 1
            continue
        if char == '"':
            in_double = not in_double
            out.append(char)
            index += 1
            continue
        if char == "#" and not in_double and (index == 0 or line[index - 1].isspace()):
            break
        if char == "\\":
            out.append(" ")
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _uses(text: str) -> list[str]:
    """Return the variable names a fragment expands, defaults excluded."""
    found: list[str] = [
        match.group(1)
        for match in re.finditer(r"\$\{([A-Za-z_][A-Za-z0-9_]*)([^}]*)", text)
        if not match.group(2).startswith(_SAFE_SUFFIX)
    ]
    found.extend(
        match.group(1) for match in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*)", text)
    )
    return found


def _assignments(line: str) -> list[str]:
    """Return the variable names a line binds."""
    names = [match.group(1) for match in _ASSIGN.finditer(line)]
    loop = _FOR_LOOP.match(line)
    if loop:
        names.append(loop.group(1))
    if re.search(r"\bread\b", line):
        # `read -rp "prompt" confirm` binds every bare word that follows.
        names.extend(
            word
            for word in line.split()
            if _BARE_WORD.match(word) and word != _READ_BUILTIN
        )
    return names


class ShellReading(NamedTuple):
    """What one shell script says about its own variables.

    `uses` holds (line number, name, inside a function body). A use
    inside a function body is order-free, because the function runs
    when it is called and not where it is written.
    """

    first_assignment: dict[str, int]
    uses: list[tuple[int, str, bool]]
    source_line: int | None


class _Reader:
    """Line-by-line state for one pass over a shell script."""

    def __init__(self) -> None:
        self.first_assignment: dict[str, int] = {}
        self.uses: list[tuple[int, str, bool]] = []
        self.source_line: int | None = None
        self.in_function = False
        self.heredoc_end: str | None = None
        self.heredoc_expands = False

    def in_heredoc(self, number: int, raw: str) -> bool:
        """Consume one here-document line. Report whether it was one."""
        if self.heredoc_end is None:
            return False
        if raw.strip() == self.heredoc_end:
            self.heredoc_end = None
            self.heredoc_expands = False
        elif self.heredoc_expands:
            # An UNQUOTED terminator means the body expands, so a name
            # read there is a real read.
            self.uses.extend((number, name, self.in_function) for name in _uses(raw))
        return True

    def code_line(self, number: int, raw: str) -> None:
        """Read one ordinary line."""
        if self.source_line is None and _SOURCE_LINE.match(raw):
            self.source_line = number

        code = _strip_quotes_and_comments(raw)
        opens = re.match(
            r"^\s*(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{", code
        )
        one_liner = bool(opens) and code.rstrip().endswith("}")
        inside = self.in_function or bool(opens)

        for name in _assignments(code):
            self.first_assignment.setdefault(name, number)
        self.uses.extend((number, name, inside) for name in _uses(code))

        heredoc = _HEREDOC.search(code)
        if heredoc:
            self.heredoc_end = heredoc.group(2)
            self.heredoc_expands = heredoc.group(1) == ""

        if opens and not one_liner:
            self.in_function = True
        elif self.in_function and code.rstrip() == "}":
            self.in_function = False


def read_shell(path: Path) -> ShellReading:
    """Read one shell script, and report what it assigns and expands."""
    reader = _Reader()
    for number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not reader.in_heredoc(number, raw):
            reader.code_line(number, raw)
    return ShellReading(reader.first_assignment, reader.uses, reader.source_line)


def ordering_faults(path: Path, library: dict[str, int] | None = None) -> list[str]:
    """Return one report line per variable read above its assignment."""
    reading = read_shell(path)
    first_assignment = reading.first_assignment
    if library and reading.source_line is not None:
        for name in library:
            first_assignment.setdefault(name, reading.source_line)

    faults: list[str] = []
    reported: set[str] = set()
    for number, name, in_function in reading.uses:
        if name in SHELL_PROVIDED or name in reported:
            continue
        bound = first_assignment.get(name)
        if bound is None:
            faults.append(f"{path.name}:{number} reads ${name}, which nothing assigns")
            reported.add(name)
        elif not in_function and number < bound:
            faults.append(
                f"{path.name}:{number} reads ${name}, first assigned at line {bound}"
            )
            reported.add(name)
    return faults


def scripts_under_set_u() -> list[Path]:
    """Every script in deploy/kiosk/ that turns on `set -u`, sorted."""
    return [
        path
        for path in sorted(OS_DIR.rglob("*.sh"))
        if re.search(
            r"^\s*set\s+-[a-z]*u", path.read_text(encoding="utf-8"), re.MULTILINE
        )
    ]


def base_package_names() -> list[str]:
    """Every apt package name inside the BASE_PKGS array of install.sh."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(r"^BASE_PKGS=\((.*?)^\)", text, re.MULTILINE | re.DOTALL)
    if match is None:
        pytest.fail("install.sh no longer declares a BASE_PKGS array")
    names: list[str] = []
    for line in match.group(1).splitlines():
        names.extend(line.split("#", 1)[0].split())
    return names


def _bash() -> str:
    found = shutil.which("bash")
    if found is None:
        pytest.skip("bash is not on PATH; the dry run cannot be exercised")
    return found


def run_dry(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one script with --dry-run. It must change nothing."""
    return subprocess.run(  # noqa: S603
        [_bash(), script.relative_to(REPO_ROOT).as_posix(), "--dry-run", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


# Contract 0 — the instrument answers on a known fault


class TestTheReaderWorks:
    """A zero from a broken reader looks exactly like a clean tree."""

    def test_it_reports_a_planted_ordering_fault(self, tmp_path: Path) -> None:
        """The reader finds a fault it was given on purpose."""
        planted = tmp_path / "planted.sh"
        planted.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'cp "${SCRIPT_DIR}/x" /dev/null 2>/dev/null || true\n'
            'SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"\n',
            encoding="utf-8",
        )
        faults = ordering_faults(planted)
        assert len(faults) == 1, faults
        assert "SCRIPT_DIR" in faults[0]
        assert "line 4" in faults[0]

    def test_it_stays_silent_on_the_repaired_order(self, tmp_path: Path) -> None:
        """The reader reports nothing when the order is right."""
        clean = tmp_path / "clean.sh"
        clean.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"\n'
            'cp "${SCRIPT_DIR}/x" /dev/null 2>/dev/null || true\n',
            encoding="utf-8",
        )
        assert ordering_faults(clean) == []

    def test_a_default_expansion_is_not_a_fault(self, tmp_path: Path) -> None:
        """`${FOO:-}` is the correct idiom and must never be reported."""
        safe = tmp_path / "safe.sh"
        safe.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if [[ -n "${LOADED:-}" ]]; then exit 0; fi\n'
            "LOADED=1\n",
            encoding="utf-8",
        )
        assert ordering_faults(safe) == []

    def test_the_planted_script_really_does_exit_early(self, tmp_path: Path) -> None:
        """The shell semantics, not the reader. `|| true` does not rescue it."""
        planted = tmp_path / "semantics.sh"
        planted.write_text(
            "set -euo pipefail\n"
            "echo BEFORE\n"
            'cp "${SCRIPT_DIR}/x" /dev/null 2>/dev/null || true\n'
            "echo AFTER\n"
            'SCRIPT_DIR="late"\n',
            encoding="utf-8",
        )
        result = subprocess.run(  # noqa: S603
            [_bash(), str(planted)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        assert result.returncode != 0
        assert "BEFORE" in result.stdout
        assert "AFTER" not in result.stdout
        assert "unbound variable" in result.stderr


# Contract 1 — no variable is read above its first assignment


class TestNoOrderingFault:
    """No variable in the `deploy/kiosk/` suite is read above its assignment."""

    def test_the_suite_has_scripts_to_read(self) -> None:
        """The rule has input. An empty sweep is not a clean one."""
        found = scripts_under_set_u()
        assert len(found) >= 5, [path.name for path in found]
        assert INSTALL_SH in found

    @pytest.mark.parametrize(
        "script", scripts_under_set_u(), ids=lambda path: path.name
    )
    def test_no_variable_is_read_before_it_is_assigned(self, script: Path) -> None:
        """The class, over every script in the suite that sets `-u`."""
        library = read_shell(COMMON_SH).first_assignment
        faults = ordering_faults(script, library=library)
        assert faults == [], "\n".join(faults)

    def test_install_assigns_script_dir_above_every_use(self) -> None:
        """The named instance, pinned as well as the class."""
        reading = read_shell(INSTALL_SH)
        bound = reading.first_assignment.get("SCRIPT_DIR")
        assert bound is not None, "install.sh no longer assigns SCRIPT_DIR"
        reads = [number for number, name, _ in reading.uses if name == "SCRIPT_DIR"]
        assert reads, "install.sh no longer reads SCRIPT_DIR"
        assert min(reads) > bound, (
            f"SCRIPT_DIR is assigned at line {bound} and first read at "
            f"line {min(reads)}"
        )


# Contract 2 — the packages Qt needs to open a window


class TestQtCanOpenAWindow:
    """The installer lists every library Qt needs to open a window."""

    def test_pyside_floor_still_needs_the_cursor_library(self) -> None:
        """State the mechanism, so the rule cannot outlive its reason."""
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        pyside = [
            line
            for line in data["project"]["dependencies"]
            if line.lower().startswith("pyside6")
        ]
        assert pyside, "pyproject.toml no longer requires PySide6"
        floor = re.search(r">=\s*(\d+)\.(\d+)", pyside[0])
        assert floor is not None, pyside[0]
        version = (int(floor.group(1)), int(floor.group(2)))
        assert version >= QT_CURSOR_REQUIRED_FROM, (
            f"PySide6 floor is {version}. Below Qt {QT_CURSOR_REQUIRED_FROM} "
            "libxcb-cursor0 stops being mandatory and this rule needs review"
        )

    @pytest.mark.parametrize("package", QT_WINDOW_PACKAGES)
    def test_the_package_is_in_the_install_list(self, package: str) -> None:
        """One package Qt needs, still named by the installer."""
        names = base_package_names()
        assert package in names, (
            f"deploy/kiosk/install.sh no longer installs {package}. Qt needs it to "
            f"load the xcb platform plugin, so no window would open. "
            f"The list holds: {names}"
        )

    def test_the_headless_path_installs_a_vnc_server(self) -> None:
        """The `--headless` path still installs TigerVNC."""
        text = INSTALL_SH.read_text(encoding="utf-8")
        assert "tigervnc-standalone-server" in text


# Contract 3 — the installer reaches its last line


class TestTheInstallerCompletes:
    """The installer reaches its last line, under `--dry-run`."""

    @pytest.mark.parametrize(
        "flags", [(), ("--headless",)], ids=["display", "headless"]
    )
    def test_the_dry_run_reaches_the_end(self, flags: tuple[str, ...]) -> None:
        """The installer prints its last line, on both branches."""
        result = run_dry(INSTALL_SH, *flags)
        assert "unbound variable" not in result.stderr, result.stderr
        assert result.returncode == 0, (
            f"exit {result.returncode}\nSTDERR:\n{result.stderr}\n"
            f"TAIL:\n{result.stdout[-2000:]}"
        )
        assert "DRY RUN finished" in result.stdout, result.stdout[-2000:]

    def test_the_dry_run_reaches_every_section(self) -> None:
        """Defect one skipped sections 5 to 8. Name each one."""
        result = run_dry(INSTALL_SH, "--headless")
        for section in (
            "1 / 8",
            "2 / 8",
            "3 / 8",
            "4 / 8",
            "5 / 8",
            "6 / 8",
            "7 / 8",
            "8 / 8",
        ):
            assert (
                section in result.stdout
            ), f"section {section} never ran\n{result.stdout[-2000:]}"

    def test_the_dry_run_still_derives_the_dependency_set(self) -> None:
        """Issue #94's wiring must survive this repair."""
        result = run_dry(INSTALL_SH, "--headless")
        assert "PySide6" in result.stdout
        assert "defusedxml" in result.stdout
        assert (
            "pyinstaller" not in result.stdout
        ), "the os consumer must not take the build host's extra"

    @pytest.mark.parametrize(
        "script", [UPDATE_SH, UNINSTALL_SH, FIREWALL_SH], ids=lambda path: path.name
    )
    def test_the_other_scripts_dry_run_clean(self, script: Path) -> None:
        """The updater, the uninstaller and the firewall also complete."""
        result = run_dry(script)
        assert "unbound variable" not in result.stderr, result.stderr
        assert (
            result.returncode == 0
        ), f"exit {result.returncode}\nSTDERR:\n{result.stderr}"

    @pytest.mark.parametrize(
        "script", sorted(OS_DIR.rglob("*.sh")), ids=lambda path: path.name
    )
    def test_every_script_parses(self, script: Path) -> None:
        """Every script in the suite is valid shell."""
        result = subprocess.run(  # noqa: S603
            [_bash(), "-n", str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr


# Contract 4 — one exclude set, and no dead subsystem


class TestOneExcludeSet:
    """One rsync exclude set, in one file, naming no dead subsystem."""

    def test_the_library_holds_the_only_set(self) -> None:
        """The one exclude set lives in the shared library."""
        text = COMMON_SH.read_text(encoding="utf-8")
        assert "ACERVATOR_SYNC_EXCLUDES=(" in text

    @pytest.mark.parametrize(
        "script", [INSTALL_SH, UPDATE_SH], ids=lambda path: path.name
    )
    def test_no_script_spells_its_own_excludes(self, script: Path) -> None:
        """No caller writes an rsync exclude of its own."""
        offending = [
            f"{script.name}:{number}"
            for number, line in enumerate(
                script.read_text(encoding="utf-8").splitlines(), start=1
            )
            if "--exclude=" in line and not line.lstrip().startswith("#")
        ]
        assert offending == [], (
            f"{offending} spells an rsync exclude. The one set lives in "
            "deploy/kiosk/lib/common.sh, which is what issue #88 asked for"
        )

    @pytest.mark.parametrize(
        "script", [INSTALL_SH, UPDATE_SH], ids=lambda path: path.name
    )
    def test_the_script_calls_the_shared_sync(self, script: Path) -> None:
        """Each caller copies the tree through the shared function."""
        assert "acervator_sync_source" in script.read_text(encoding="utf-8")

    def test_the_os_suite_names_no_dead_subsystem(self) -> None:
        """`sadp/RAIntSimBat` has never existed in this repository.

        The rule reads LIVE lines. A comment that records the removal
        is the record this repair wanted to leave, and issue #68 keeps
        the same distinction for README.md.
        """
        hits = []
        for path in sorted(OS_DIR.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {
                ".sh",
                ".py",
                ".json",
                ".service",
                ".md",
            }:
                continue
            commented = path.suffix.lower() in {".sh", ".py", ".service"}
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                if commented and line.lstrip().startswith("#"):
                    continue
                lowered = line.lower()
                if "sadp" in lowered or "raintsimbat" in lowered:
                    hits.append(
                        f"{path.relative_to(REPO_ROOT).as_posix()}:{number}"
                        f" {line.strip()}"
                    )
        assert hits == [], hits


# Contract 5 — port 5901 stays shut, and the advice agrees


class TestTheViewerPortStaysShut:
    """Port 5901 stays shut, and the printed advice agrees with it."""

    def test_the_firewall_never_opens_5901(self) -> None:
        """No firewall rule opens the VNC port."""
        offending = [
            f"firewall.sh:{number}"
            for number, line in enumerate(
                FIREWALL_SH.read_text(encoding="utf-8").splitlines(), start=1
            )
            if "5901" in line and re.search(r"^\s*(acervator_run\s+)?ufw\s", line)
        ]
        assert offending == [], (
            f"{offending} opens the VNC port. A VNC port reachable from the "
            "internet draws continuous scanning. Use an SSH tunnel on port 22"
        )

    def test_the_installer_advises_the_tunnel_and_not_the_open_port(self) -> None:
        """The printed advice names an SSH tunnel, not a public address."""
        text = INSTALL_SH.read_text(encoding="utf-8")
        assert (
            "ssh -L 5901:localhost:5901" in text
        ), "the headless path must tell the reader to build an SSH tunnel"
        assert (
            "-localhost yes" in text
        ), "the VNC server must be told to bind to the loopback interface"
        assert not re.search(
            r"vncviewer\s+\$\(hostname", text
        ), "the installer must not print a public VNC address"

    def test_the_firewall_still_permits_ssh(self) -> None:
        """The tunnel has no route without it."""
        text = FIREWALL_SH.read_text(encoding="utf-8")
        assert re.search(r"ufw allow in 22/tcp", text)

    def test_the_hardware_guide_agrees(self) -> None:
        """The suite's own guide must not send a viewer at the shut port.

        `deploy/kiosk/HARDWARE_GUIDE.md` used to say "Connect to:
        acervator.local:5901". The firewall has never permitted that,
        so the instruction could not work. Two files gave one reader
        two answers, which is what issue #88 is about.
        """
        guide = OS_DIR / "HARDWARE_GUIDE.md"
        assert guide.is_file(), "deploy/kiosk/HARDWARE_GUIDE.md is gone"
        text = guide.read_text(encoding="utf-8")
        assert (
            "ssh -L 5901:localhost:5901" in text
        ), "the headless section must name the tunnel"
        offending = [
            f"HARDWARE_GUIDE.md:{number}"
            for number, line in enumerate(text.splitlines(), start=1)
            if re.search(r"(vncviewer|Connect to:)\s*\S*[^t]:5901", line)
        ]
        assert (
            offending == []
        ), f"{offending} points a viewer at a port the firewall shuts"

    def test_the_cloud_guide_agrees(self) -> None:
        """The live cloud guide says the same as the installer."""
        guide = (
            REPO_ROOT / "docs" / "guides" / "2026-08-23_run_acervator_in_the_cloud.md"
        )
        assert guide.is_file(), "the cloud guide is gone"
        text = guide.read_text(encoding="utf-8")
        assert "ssh -L 5901:localhost:5901" in text or "SSH tunnel" in text


# Contract 6 — the Python floor comes from pyproject.toml


def pyproject_python_floor() -> tuple[int, int]:
    """The `requires-python` lower bound in pyproject.toml, as (major, minor)."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = data["project"]["requires-python"]
    match = re.search(r">=\s*(\d+)\.(\d+)", declared)
    assert match is not None, f"pyproject.toml states no lower bound: {declared}"
    return int(match.group(1)), int(match.group(2))


class TestThePythonFloor:
    """The Python floor comes from `pyproject.toml` and nowhere else."""

    def test_the_library_repeats_the_pyproject_floor(self) -> None:
        """The shell floor and the TOML floor are the same number."""
        expected = pyproject_python_floor()

        text = COMMON_SH.read_text(encoding="utf-8")
        major = re.search(r"^ACERVATOR_PYTHON_MIN_MAJOR=(\d+)", text, re.MULTILINE)
        minor = re.search(r"^ACERVATOR_PYTHON_MIN_MINOR=(\d+)", text, re.MULTILINE)
        assert major is not None, "deploy/kiosk/lib/common.sh states no major floor"
        assert minor is not None, "deploy/kiosk/lib/common.sh states no minor floor"
        found = (int(major.group(1)), int(minor.group(1)))
        assert found == expected, (
            f"pyproject.toml asks for {expected} and deploy/kiosk/lib/common.sh "
            f"asks for {found}"
        )

    def test_the_package_list_names_no_python_release(self) -> None:
        """Debian 12 has no `python3.12` package. Issue #95 defect three.

        A first version of this rule read whole LINES and asked for
        `apt-get install` or `BASE_PKGS` on the same line. The control
        run put `python3.12` back inside the array and the rule stayed
        silent, because the array spreads over many lines and the
        package sits on none of them. It now reads the array itself.
        """
        offending = [
            name for name in base_package_names() if re.match(r"^python3\.\d+", name)
        ]
        assert offending == [], (
            f"deploy/kiosk/install.sh asks apt for {offending}. Debian 12 and "
            "Raspberry Pi OS Bookworm carry no such package. Ask for the "
            "unversioned python3 set and check the floor at run time"
        )

    def test_no_script_runs_one_python_release_by_name(self) -> None:
        """`python3.12 -m venv` fails on a machine that ships 3.11.

        A line may name SEVERAL versioned interpreters, because that is
        a probe list that falls back: `acervator_find_python` tries
        3.14 down to 3.11 and then the unversioned names. Naming ONE is
        a demand, and a demand is what issue #95 defect three is.
        """
        offending = []
        for script in sorted(OS_DIR.rglob("*.sh")):
            for number, line in enumerate(
                script.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if line.lstrip().startswith("#"):
                    continue
                named = re.findall(r"(?<![\w.])python3\.\d+", line)
                if len(set(named)) == 1:
                    offending.append(f"{script.name}:{number} {line.strip()}")
        assert offending == [], offending

    def test_the_installer_checks_the_floor_at_run_time(self) -> None:
        """The installer measures the interpreter it was given."""
        assert "acervator_find_python" in INSTALL_SH.read_text(encoding="utf-8")

    def test_the_finder_accepts_this_interpreter(self) -> None:
        """A positive control: the rule must accept a real, adequate Python."""
        floor = pyproject_python_floor()
        assert sys.version_info[:2] >= floor, (
            f"this interpreter is {sys.version_info[:2]} and pyproject.toml "
            f"asks for {floor} or later"
        )
        probe = subprocess.run(  # noqa: S603
            [
                _bash(),
                "-c",
                f'source "{COMMON_SH.as_posix()}" && acervator_find_python',
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        assert probe.returncode == 0, probe.stderr
        assert probe.stdout.strip(), "acervator_find_python found nothing"
