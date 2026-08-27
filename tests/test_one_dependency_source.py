"""A package name lives in `pyproject.toml` and nowhere else.

WHAT WAS MEASURED
=================
Issue #94, on 2026-08-23, in a clone at commit 4965bab. The pip install
list was hand-copied into eight places. No two of them agreed, and none
of them agreed with `pyproject.toml`.

    build_mac.sh:46          14 names
    build_windows.ps1:28     14 names, the same 14
    Acervator_win.spec:8     14 names, in a docstring
    Acervator_mac.spec:8     14 names, in a docstring
    BUILD.py:79              12 names, as (import name, pip name) pairs
    deploy/kiosk/install.sh:177        11 names, plus 4 more at :192
    deploy/kiosk/update.sh:71          11 names
    README.md:123             6 names
    pyproject.toml           11 names

Two of the disagreements were defects and not merely drift.

    `defusedxml` is imported at src/gui/crypto_news_ticker.py:51 and :52
    at MODULE level, with no try block. Both .spec files name it in
    `hiddenimports` and say, in a comment written against a control
    build, that its absence is "an ImportError at module import". No
    build list installed it. The build worked only because the package
    was already on the machine.

    `requests` was installed by four of the eight lists. No file in the
    repository imports it. Measured with an AST walk over every `*.py`
    at the repo root and under `src/`, `tools/` and `deploy/kiosk/`: 83 top-level
    module names, and `requests` was not among them. It reaches the
    machine anyway, as a dependency of ccxt:
    `requirements/build-win32-py3.14.txt` pins `requests==2.34.2` and
    records `# via ccxt`. That is why installing it by hand never
    appeared to matter.

WHAT THIS FILE ASSERTS
======================
Three contracts, each one able to fail on its own.

    1. NO SHIPPED FILE HOLDS A LIST.
       Every tracked text file is read, and a line that installs two or
       more packages by name fails. The rule catches a NEW list as
       readily as the old eight, which is the point: a guard that named
       the eight would pass the day a ninth appeared.

    2. EVERY CONSUMER NAMES AN EXTRA THAT EXISTS.
       `tools/deps.py` maps a consumer to extras. Each extra must be in
       `[project.optional-dependencies]`. Without this, renaming an
       extra in `pyproject.toml` would leave the build asking for one
       that is gone, and the failure would land on the operator during a
       build rather than here.

    3. EVERY THIRD-PARTY IMPORT IS DECLARED.
       The other direction. An AST walk finds every top-level import in
       the product tree, drops the standard library and the first-party
       packages, and requires the rest to be in `dependencies` or in an
       extra. Contract 1 alone would pass on a tree that declared
       nothing at all.

WHAT THIS FILE DOES NOT ASSERT
==============================
It does not check that a declared package is USED. `pandas` and `ta`
are declared and no file imports either one; both are also named in
`hiddenimports` in both .spec files, so removing them changes what
PyInstaller collects. That is a build change, it was not verified by a
build, and it is not this file's subject. Issue #94 reports it and
leaves it declared.

It does not read a lock file. `requirements/` holds a resolved set for
one platform and one interpreter, and the Raspberry Pi target has
neither. A test that compared the tree to a Windows lock would fail on
the Pi for a correct reason and would teach the reader to ignore it.

TWO-SIDED CONTROL
=================
Driven both ways on 2026-08-23.

    IN THE SUITE  `TestTheInstrumentCanFail` drives the rule over nine
                  shapes and requires a report on four of them: the
                  exact fourteen-name line issue #94 removed, a
                  two-name line, a list of packages `pyproject.toml`
                  does not declare, and a list inside a string literal.
                  It requires silence on five: a one-name line, a
                  markdown table row, and the three derived forms the
                  repaired scripts use. Without the first four, this
                  file would pass because the scan found nothing.

    ON THE REPO   The pre-fix pip line from `build_windows.ps1:28` was
                  written back over the repaired call in the working
                  tree. Two tests failed and fifteen passed.
                  `test_no_tracked_file_holds_a_dependency_list` named
                  `build_windows.ps1:35` and listed all fourteen
                  packages: pyinstaller, PySide6, ccxt, cryptography,
                  keyring, pandas, numpy, ta, tomli_w, aiohttp, certifi,
                  requests, reportlab, pillow.
                  `test_the_five_repaired_files_still_call_the_tool`
                  failed as well, because the planted line had displaced
                  the call to the tool. The file was then restored from
                  a copy and kept its sha256, d39d5e874003ca8e5f55c4e1e
                  5bb160b4453ada3bb7a94e45fe53b59953f437b before the
                  plant and the same after it, and all seventeen
                  tests passed again.

ISSUE #92 - A BLIND SPOT IN CONTRACT 3
======================================
Measured 2026-08-23 in a clone at commit 5613bd1, the commit that
merged issue #94. This file passed, and the suite stood at 7388 tests,
while `contracts/deploy.py` imported three undeclared third-party
packages: web3 at line 82, eth_account at line 83 and solcx at line 54.

The cause was `PRODUCT_ROOTS`, which read ("src", "tools", "os").
`contracts` was already in FIRST_PARTY, so an import OF that package
was correctly skipped, but no walk ever ENTERED the directory, so the
imports it MADE were never read. The tuple named the trees to read,
FIRST_PARTY named the trees that are ours, and the two disagreed.

Contract 1 missed the same file for a second and independent reason.
Its word set is read out of pyproject.toml at run time, so a list of
packages the one source has never heard of scores zero known words and
cannot reach the floor of two. `contracts/deploy.py:8` read
"pip install web3 eth-account py-solc-x" and the rule stayed silent.
That blind spot closed as a CONSEQUENCE of the declaration, and not by
a change to the rule. Measured in order, in the same clone:

    1. `contracts` added to PRODUCT_ROOTS, nothing declared.
       `test_no_third_party_import_is_undeclared` FAILED and named
       eth_account, solcx and web3, each at contracts/deploy.py.
       16 passed.
    2. The file was restored from a copy and kept its sha256,
       5921733f5042278481c2718c00a72211e910683baf18cf81ce564adbe829ec4a
       before the plant and the same after it. 17 passed.
    3. The `contracts` extra declared in pyproject.toml and the repair
       applied. `test_no_third_party_import_is_undeclared` passed, and
       `test_no_tracked_file_holds_a_dependency_list` FAILED with
       "contracts/deploy.py:8 names ['web3', 'eth-account',
       'py-solc-x']" - the SAME line, now visible, because the three
       names had entered `install_words()`. 16 passed.
    4. That docstring line replaced with the derived form, and
       `install_deps()` removed. 17 passed, then 21 with the four
       controls in `TestTheWalkReachesTheContractsTree` below.

`src/competition/` was checked and is NOT part of this. Issue #92 says
it needs web3, eth-account and py-solc-x. An AST walk over all ten of
its modules finds one third-party import, `cryptography` at
src/competition/bot_identity.py:34 and :36, and that has always been a
core dependency. Nothing was declared for it.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

# HISTORICAL RECORDS. These hold what was true when they were written and
# they may not be edited to satisfy a rule. `docs/audits/` and
# `docs/harness_archive/` are the session record; `CHANGELOG.md` is the
# release record. `requirements/` is excluded because a lock file lists
# every resolved package by design; that is what a lock file is.
#
# This file excludes ITSELF, and nothing else. The controls below hold
# the exact pre-fix lines as string literals and must trip the rule, so
# the scan would report this file every run. `tools/deps.py` is NOT
# excluded: it describes the eight removed lists by file and count and
# never writes a `pip install` line, and it was measured at zero hits.
EXCLUDED_PREFIXES: tuple[str, ...] = (
    "docs/audits/",
    "docs/harness_archive/",
    "requirements/",
)
EXCLUDED_FILES: tuple[str, ...] = (
    "CHANGELOG.md",
    "tests/test_one_dependency_source.py",
)

# Extensions worth reading. A dependency list is written in a script, a
# spec, a manifest or a document. A `.png` cannot hold one.
READABLE_SUFFIXES: tuple[str, ...] = (
    ".py",
    ".sh",
    ".ps1",
    ".bat",
    ".spec",
    ".md",
    ".toml",
    ".cfg",
    ".txt",
    ".service",
    ".yml",
    ".yaml",
)

# Distribution names this project can install. The rule fires on a line
# that names TWO OR MORE of them, because one name on a line is a
# sentence about a package and two names in sequence is a list.
#
# The set is READ from pyproject.toml at run time and is not written
# here, so it grows when the one source grows. A fixed set would go
# stale the first time a dependency was added.
EXTRA_INSTALL_WORDS: frozenset[str] = frozenset(
    {
        # Names that were in the removed lists and are not in pyproject.toml.
        # A list that names only these must still fail.
        "requests",
        "pyinstaller",
        "pillow",
        "st7789",
        "waveshare_epd",
    }
)

# A line that installs. Any of pip, pip3, or `python -m pip`.
#
# The character class before the command carries a quote as well as
# whitespace. A first version did not, and it read the planted line in
# `test_the_rule_reports_the_removed_windows_line` below as no match,
# because a double quote sat in front of `pip`. A list inside a string
# literal is still a list, and a script that built its pip argv as a
# string would have slipped through. That is also why `tools/deps.py`
# and this file are in EXCLUDED_FILES: with the quote in the class,
# both of them now trip their own rule on the evidence they quote.
_PIP_INSTALL = re.compile(
    r"""(?:^|[\s;&|("'`])(?:pip3?|python3?\s+-m\s+pip)\s+install\b""", re.IGNORECASE
)

# Where an install command ends. Everything after this is prose, another
# cell of a markdown table, or another command.
_COMMAND_END = re.compile(r"""[`"'|;&#)]""")

# The derived forms. A line that installs is allowed only when it takes
# its names from the one source instead of naming them.
_DERIVED = re.compile(
    r"""tools[./]deps|tools\.deps|\$DEPS|\$\{DEPS|@deps|"\$DISPLAY_DEPS"""
    r"""|\$DISPLAY_DEPS|-e\s+["']?\.""",
    re.IGNORECASE,
)

# First-party package roots. An import of one of these is not a
# dependency, so contract 3 skips it.
FIRST_PARTY: frozenset[str] = frozenset(
    {
        "src",
        "tools",
        "tests",
        "dev_harness",
        "acervator_watchdog",
        "contracts",
        "deploy",
        # Issue #74. The animation core the three presentation screens
        # share. It is a root .py, so it is a TOP-LEVEL import name, and
        # this set is what tells contract 3 that `import screen_fx` is ours
        # and not a package somebody has to install.
        "screen_fx",
    }
)

# Import name -> distribution name, for the cases where they differ.
# Written out because there is no rule that derives one from the other:
# `PIL` comes from `pillow` and `cv2` comes from `opencv-python`, and
# nothing in either name says so.
IMPORT_TO_DISTRIBUTION: dict[str, str] = {
    "PIL": "pillow",
    "cv2": "opencv-python",
    "luma": "luma.oled",
    "ST7789": "st7789",
    "tomli": "tomli",
    # Issue #92. `pip install eth_account` and `pip install solcx` both
    # fail; the distributions are `eth-account` and `py-solc-x`. Without
    # these two rows contract 3 would report a package that is declared.
    "eth_account": "eth-account",
    "solcx": "py-solc-x",
}

# Third-party imports the product tree makes that no consumer installs,
# each with the reason it is not a declared dependency.
#
#   tomli   src/core/settings.py:32 imports it only in the `except
#           ImportError` arm below `import tomllib`. `requires-python`
#           is ">=3.11" and tomllib is stdlib from 3.11, so that arm is
#           unreachable on every interpreter this project supports.
#   ST7789  src/core/mini_display.py:362, inside a try that returns
#           False. deploy/kiosk/install.sh has always said it is hardware-specific
#           and has never installed it.
UNDECLARED_ON_PURPOSE: frozenset[str] = frozenset({"tomli", "ST7789"})

# Every Python file the product ships. The repo root carries ten of them
# beside `main.py`, and two of those, `generate_essay_ja.py` and
# `generate_essay_localized.py`, import reportlab. A walk that read only
# `src/` would call reportlab unimported and would report the wrong set.
# Issue #92 REPAIRED A BLIND SPOT HERE. This tuple read
# ("src", "tools", "os"). `contracts` was in FIRST_PARTY above, so an
# import OF it was skipped, but no walk ever entered it, so the imports
# it MAKES were never read. `contracts/deploy.py` imported web3,
# eth_account and solcx, none of them declared, and contract 3 passed
# on 2026-08-23 at 7388 tests while it did.
#
# Contract 1 missed the same file for a second and independent reason.
# Its word set is READ from pyproject.toml, so a list of packages the
# one source has never heard of names zero known words and cannot reach
# the floor of two. `contracts/deploy.py:8` read
# "pip install web3 eth-account py-solc-x" and scored nothing. That
# blind spot closes as a CONSEQUENCE of declaring the three packages,
# not by a change to the rule: the moment pyproject.toml names them
# they enter `install_words()`. This file does not widen the rule to
# guess at unknown package names, because a guess would report every
# `pip install` in every document.
#
# The rule this tuple now follows: every root named in FIRST_PARTY that
# is a directory in the tree is walked. `tests` and `dev_harness` stay
# out because neither ships, and `acervator_watchdog` is a file at the
# root, already covered by the `*.py` glob below.
PRODUCT_ROOTS: tuple[str, ...] = ("src", "tools", "deploy", "contracts")


# ---------------------------------------------------------------------------
# Reading the one source
# ---------------------------------------------------------------------------


def read_project(pyproject: Path = PYPROJECT) -> dict[str, Any]:
    """Return the `[project]` table. Fails rather than answering empty."""
    if not pyproject.is_file():
        pytest.fail(f"the one dependency source is missing: {pyproject}")
    with pyproject.open("rb") as handle:
        project = tomllib.load(handle).get("project")
    if not isinstance(project, dict):
        pytest.fail(f"{pyproject} has no [project] table")
    return project


def read_extras(pyproject: Path = PYPROJECT) -> dict[str, list[str]]:
    """Return `[project.optional-dependencies]`, narrowed and never None."""
    extras = read_project(pyproject).get("optional-dependencies", {})
    if not isinstance(extras, dict):
        return {}
    return {
        str(name): [str(req) for req in group]
        for name, group in extras.items()
        if isinstance(group, list)
    }


def declared_distributions() -> set[str]:
    """Every distribution name the one source states, normalised."""
    project = read_project()
    names: set[str] = set()
    for requirement in project.get("dependencies", []):
        names.add(normalise(str(requirement)))
    for group in read_extras().values():
        for requirement in group:
            names.add(normalise(str(requirement)))
    return names


def normalise(requirement: str) -> str:
    """Return the PEP 503 normalised name at the front of a requirement."""
    name = requirement.strip()
    for index, char in enumerate(name):
        if not (char.isalnum() or char in "-_."):
            name = name[:index]
            break
    return re.sub(r"[-_.]+", "-", name).lower()


def install_words() -> set[str]:
    """Package words the list rule looks for, in lower case."""
    words = {normalise(name) for name in declared_distributions()}
    words |= {normalise(name) for name in EXTRA_INSTALL_WORDS}
    return words


# ---------------------------------------------------------------------------
# The list rule
# ---------------------------------------------------------------------------


def hand_copied_list(line: str, words: set[str]) -> tuple[str, ...]:
    """Return the package names a line installs by hand, or an empty tuple.

    A line qualifies when it runs pip install, it does NOT take its
    names from the one source, and it names two or more DISTINCT
    packages. Two is the floor because one name is a sentence and two in
    sequence is a list.

    Distinctness is measured on the normalised name, not on the token.
    A first attempt deduplicated tokens and reported four false hits:
    `src/exchange/ccxt_connector.py:930` says "CCXT version mismatch.
    Try: pip install ccxt", and `CCXT` and `ccxt` are two tokens and one
    package. `deploy/kiosk/install.sh:205` and two more files pair `ST7789` with
    `st7789` the same way.

    Only the text INSIDE the install command is counted. A second
    attempt counted the whole line and reported two more false hits, in
    a markdown table where one cell installs a package and the next
    cell talks about another: `.claude/skills/acervator/SKILL.md:161`
    reads "| `pip install pyright` | alternative type checker; often
    finds what mypy misses |". One package is installed there and two
    are named. The slice ends at the first character that closes a
    command: a backtick, a quote, a pipe, a semicolon, an ampersand, a
    comment mark or a closing bracket.

    `_DERIVED` is still measured on the WHOLE line, because
    `pip install -e ".[dev]"` carries its marker inside a quote and the
    slice would cut it off.
    """
    match = _PIP_INSTALL.search(line)
    if match is None:
        return ()
    if _DERIVED.search(line):
        return ()
    arguments = _COMMAND_END.split(line[match.end() :], maxsplit=1)[0]
    ordered: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[^A-Za-z0-9_.\-]+", arguments):
        if not token:
            continue
        name = normalise(token)
        if name in words and name not in seen:
            seen.add(name)
            ordered.append(token)
    return tuple(ordered) if len(ordered) >= 2 else ()


def tracked_files() -> list[str]:
    """Every tracked path, from the git index rather than a directory walk."""
    git = _git_exe()
    result = subprocess.run(  # noqa: S603
        [git, "ls-files"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"git ls-files failed: {result.stderr.strip()}")
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not paths:
        pytest.fail("git ls-files returned nothing; the scan has no input")
    return paths


def in_scope(path: str) -> bool:
    """Report whether a tracked path is read by the list rule."""
    if path in EXCLUDED_FILES:
        return False
    if any(path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    return Path(path).suffix.lower() in READABLE_SUFFIXES


def scan_for_lists(paths: list[str], words: set[str]) -> list[str]:
    """Return one report line per hand-copied list found."""
    hits: list[str] = []
    for path in paths:
        if not in_scope(path):
            continue
        target = REPO_ROOT / path
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            names = hand_copied_list(line, words)
            if names:
                hits.append(f"{path}:{number} names {list(names)}")
    return hits


# ---------------------------------------------------------------------------
# The import inventory
# ---------------------------------------------------------------------------


def product_python_files(roots: tuple[str, ...] = PRODUCT_ROOTS) -> list[Path]:
    """Every Python file in the product tree. Never an empty answer.

    `roots` is a parameter and not a constant read, so that
    `TestTheWalkReachesTheContractsTree` below can drive this walk with
    the pre-issue-92 tuple and measure what that tuple missed. A control
    that cannot run the broken version proves nothing about the repair.
    """
    files = sorted(REPO_ROOT.glob("*.py"))
    for root in roots:
        directory = REPO_ROOT / root
        if directory.is_dir():
            files.extend(sorted(directory.rglob("*.py")))
    if not files:
        pytest.fail("no product Python file found; the inventory has no input")
    return files


def top_level_imports(roots: tuple[str, ...] = PRODUCT_ROOTS) -> dict[str, list[str]]:
    """Map each imported top-level module to the files that import it."""
    found: dict[str, list[str]] = {}
    for path in product_python_files(roots):
        try:
            tree = ast.parse(
                path.read_text(encoding="utf-8", errors="replace"), filename=str(path)
            )
        except SyntaxError:
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
            for name in names:
                found.setdefault(name, [])
                if relative not in found[name]:
                    found[name].append(relative)
    return found


def third_party_imports(roots: tuple[str, ...] = PRODUCT_ROOTS) -> dict[str, list[str]]:
    """The imports that are neither standard library nor first party."""
    standard = set(sys.stdlib_module_names)
    return {
        name: files
        for name, files in top_level_imports(roots).items()
        if name not in standard and name not in FIRST_PARTY and not name.startswith("_")
    }


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------
# S607 IS FIXED BY CONSTRUCTION, NOT SUPPRESSED, following the reasoning at
# the top of dev_harness/harness/coding_archetype.py and the pattern already
# measured clean in tests/test_no_committed_backup_copies.py: the spawn
# resolves git to an absolute path with shutil.which, so a `git.cmd` planted
# earlier on PATH cannot run under the developer token during a test. S603 is
# the residue and is not avoidable, because every argv carrying a variable
# draws it.


def _git_exe() -> str:
    """Return an absolute git path, or fail. A skip is not evidence."""
    import shutil

    git = shutil.which("git")
    if git is None:
        pytest.fail("git not found; tracked files cannot be enumerated")
    return git


# ---------------------------------------------------------------------------
# Contract 1
# ---------------------------------------------------------------------------


class TestNoFileHoldsAList:
    """Issue #94's subject. Eight lists became zero."""

    def test_no_tracked_file_holds_a_dependency_list(self) -> None:
        hits = scan_for_lists(tracked_files(), install_words())
        assert not hits, (
            "hand-copied dependency list(s) found:\n  "
            + "\n  ".join(hits)
            + "\n\npyproject.toml is the one source. Call "
            "`python -m tools.deps requirements <consumer>` and install "
            "what it prints."
        )

    def test_the_five_repaired_files_still_call_the_tool(self) -> None:
        """The repair holds. Deleting the call would pass contract 1."""
        expected = {
            "build_mac.sh": "tools.deps",
            "build_windows.ps1": "tools.deps",
            "BUILD.py": "tools.deps",
            "deploy/kiosk/install.sh": "tools/deps.py",
            "deploy/kiosk/update.sh": "tools/deps.py",
        }
        missing = []
        for path, needle in expected.items():
            text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
            if needle not in text:
                missing.append(f"{path} no longer names {needle}")
        assert not missing, "; ".join(missing)


# ---------------------------------------------------------------------------
# Contract 2
# ---------------------------------------------------------------------------


class TestEveryConsumerNamesARealExtra:

    def test_consumer_extras_exist_in_pyproject(self) -> None:
        from tools.deps import CONSUMER_EXTRAS

        declared = read_extras()
        assert declared, (
            "pyproject.toml declares no [project.optional-dependencies]; "
            "every consumer in tools/deps.py asks for one"
        )
        unknown = sorted(
            {
                extra
                for extras in CONSUMER_EXTRAS.values()
                for extra in extras
                if extra not in declared
            }
        )
        assert not unknown, (
            f"tools/deps.py asks for extras pyproject.toml does not "
            f"declare: {unknown}. Declared: {sorted(declared)}"
        )

    def test_every_declared_extra_reaches_a_consumer(self) -> None:
        """The other direction. An extra nothing asks for is dead."""
        from tools.deps import CONSUMER_EXTRAS

        declared = set(read_extras())
        reached = {extra for extras in CONSUMER_EXTRAS.values() for extra in extras}
        orphaned = sorted(declared - reached)
        assert not orphaned, (
            f"pyproject.toml declares extras no consumer in "
            f"tools/deps.py reaches: {orphaned}"
        )

    def test_the_build_consumer_is_not_the_target_consumer(self) -> None:
        """A build HOST compiles; an AcervatorOS TARGET does not.

        This is the distinction the eight lists lost. `deploy/kiosk/install.sh`
        never installed pyinstaller and must not start.
        """
        from tools.deps import CONSUMER_EXTRAS, requirements_for

        host = {normalise(r) for r in requirements_for(CONSUMER_EXTRAS["build"])}
        target = {normalise(r) for r in requirements_for(CONSUMER_EXTRAS["os"])}
        assert "pyinstaller" in host, "the build host must get pyinstaller"
        assert "pyinstaller" not in target, (
            "the AcervatorOS target runs from source in a venv and must "
            "not install pyinstaller"
        )


# ---------------------------------------------------------------------------
# Contract 3
# ---------------------------------------------------------------------------


class TestEveryImportIsDeclared:

    def test_no_third_party_import_is_undeclared(self) -> None:
        declared = declared_distributions()
        undeclared = []
        for module, files in sorted(third_party_imports().items()):
            if module in UNDECLARED_ON_PURPOSE:
                continue
            distribution = IMPORT_TO_DISTRIBUTION.get(module, module)
            if normalise(distribution) not in declared:
                undeclared.append(
                    f"{module} (distribution {distribution}) imported by "
                    f"{files[0]} and {len(files) - 1} more"
                )
        assert (
            not undeclared
        ), "imported but declared nowhere in pyproject.toml:\n  " + "\n  ".join(
            undeclared
        )

    def test_the_inventory_is_not_empty(self) -> None:
        """A zero is a claim about the instrument, not about the world."""
        modules = third_party_imports()
        assert len(modules) >= 15, (
            f"the import walk found only {len(modules)} third-party "
            "modules; it read nothing"
        )
        assert "PySide6" in modules, "the import walk missed PySide6"


# ---------------------------------------------------------------------------
# Two-sided control
# ---------------------------------------------------------------------------


class TestTheInstrumentCanFail:
    """Point the rule at a planted list and require it to report."""

    def test_the_rule_reports_the_removed_windows_line(self) -> None:
        words = install_words()
        planted = (
            "pip install pyinstaller PySide6 ccxt cryptography "
            "keyring pandas numpy ta tomli_w aiohttp certifi "
            "requests reportlab pillow --quiet --upgrade"
        )
        names = hand_copied_list(planted, words)
        assert len(names) >= 10, (
            f"the rule found only {names} in the exact line issue #94 "
            "removed from build_windows.ps1:28"
        )

    def test_the_rule_reports_a_two_name_line(self) -> None:
        """Two names is the floor. It must fire there, not only at ten."""
        names = hand_copied_list("pip install PySide6 ccxt", install_words())
        assert names == ("PySide6", "ccxt"), names

    def test_the_rule_reports_a_new_list_of_unknown_packages(self) -> None:
        """A NEW list must fail, not only a copy of one of the eight."""
        names = hand_copied_list(
            "pip3 install requests pillow --quiet", install_words()
        )
        assert names == ("requests", "pillow"), names

    def test_the_rule_reports_a_list_inside_a_string_literal(self) -> None:
        """A script that builds its pip argv as a string still holds a list."""
        names = hand_copied_list('cmd = "pip install PySide6 ccxt"', install_words())
        assert names == ("PySide6", "ccxt"), names

    def test_the_rule_stays_quiet_on_a_markdown_table_row(self) -> None:
        """One cell installs one package; the next cell names another.

        `.claude/skills/acervator/SKILL.md:161` is this shape. Counting
        the whole line reported it, and it is not a list.
        """
        row = (
            "| **Pyright** | `pip install pyright` | alternative type "
            "checker; often finds what mypy misses |"
        )
        assert hand_copied_list(row, install_words()) == ()

    def test_the_rule_stays_quiet_on_one_name(self) -> None:
        """One name is a sentence about a package, not a list."""
        assert (
            hand_copied_list(
                "pip install opencv-python      # direct MP4", install_words()
            )
            == ()
        )

    def test_the_rule_stays_quiet_on_every_derived_form(self) -> None:
        words = install_words()
        derived = (
            'pip install -e ".[dev]"',
            "pip install $DEPS --quiet",
            "pip install @deps --quiet --upgrade",
            "python -m pip install $(python -m tools.deps requirements build)",
            '"$PIP" install $DISPLAY_DEPS --quiet',
        )
        fired = [line for line in derived if hand_copied_list(line, words)]
        assert not fired, f"the rule fired on a derived install: {fired}"

    def test_the_scan_reports_a_planted_file(self, tmp_path: Path) -> None:
        """The whole scan, not only the rule, must reach a file."""
        planted = tmp_path / "install_something.sh"
        planted.write_text(
            "#!/bin/bash\npip install PySide6 ccxt numpy\n", encoding="utf-8"
        )
        words = install_words()
        line = planted.read_text(encoding="utf-8").splitlines()[1]
        assert hand_copied_list(line, words) == ("PySide6", "ccxt", "numpy")

    def test_the_declared_set_is_not_empty(self) -> None:
        declared = declared_distributions()
        assert len(declared) >= 20, (
            f"only {len(declared)} distributions read out of "
            "pyproject.toml; the reader read nothing"
        )
        assert "pyside6" in declared

    def test_the_scan_reads_more_than_a_handful_of_files(self) -> None:
        paths = [path for path in tracked_files() if in_scope(path)]
        assert len(paths) >= 100, (
            f"the scan read only {len(paths)} tracked files; a rule that "
            "reads nothing reports nothing"
        )


# ---------------------------------------------------------------------------
# Two-sided control for the issue #92 repair
# ---------------------------------------------------------------------------


class TestTheWalkReachesTheContractsTree:
    """Drive the import walk with the broken tuple and the repaired one.

    Issue #92. `PRODUCT_ROOTS` read ("src", "tools", "os"). The whole
    `contracts/` tree was outside every walk, so contract 3 could not
    see the imports it made. These three tests fail if that tuple ever
    narrows again, and they fail for a reason a reader can act on: they
    name the file and the modules, not a count.
    """

    #: The tuple as it stood before issue #92 repaired it.
    BROKEN_ROOTS: tuple[str, ...] = ("src", "tools", "os")

    #: The modules `contracts/deploy.py` imports.
    CHAIN_MODULES: tuple[str, ...] = ("web3", "eth_account", "solcx")

    def test_the_old_tuple_missed_all_three_chain_modules(self) -> None:
        """The NEGATIVE side. Without the repair the walk sees nothing."""
        seen = third_party_imports(self.BROKEN_ROOTS)
        found = [name for name in self.CHAIN_MODULES if name in seen]
        assert not found, (
            f"the pre-issue-92 roots {self.BROKEN_ROOTS} now reach "
            f"{found}. This control no longer measures the blind spot it "
            "was written for; re-derive it before deleting it."
        )

    def test_the_repaired_tuple_finds_all_three_chain_modules(self) -> None:
        """The POSITIVE side. With the repair the walk reports each one."""
        seen = third_party_imports()
        missing = [name for name in self.CHAIN_MODULES if name not in seen]
        assert not missing, (
            f"the import walk did not reach {missing} in contracts/. "
            f"PRODUCT_ROOTS is {PRODUCT_ROOTS}; `contracts` must stay in "
            "it or contract 3 goes blind to that tree again."
        )
        assert "contracts/deploy.py" in seen["web3"], seen["web3"]

    def test_each_chain_module_maps_to_its_declared_distribution(self) -> None:
        """The import name is not the package name for two of the three.

        `pip install eth_account` and `pip install solcx` both fail. Only
        `eth-account` and `py-solc-x` resolve. Contract 3 compares the
        DISTRIBUTION name, so a missing row in IMPORT_TO_DISTRIBUTION
        would report a package that pyproject.toml declares.
        """
        declared = declared_distributions()
        for module in self.CHAIN_MODULES:
            distribution = IMPORT_TO_DISTRIBUTION.get(module, module)
            assert normalise(distribution) in declared, (
                f"{module} maps to {distribution}, which pyproject.toml "
                f"does not declare. Declared: {sorted(declared)}"
            )

    def test_the_contracts_extra_installs_no_other_package(self) -> None:
        """The extra is opt-in and must stay small.

        A default Acervator install must not pull a chain client. This
        fails if `contracts` ever grows beyond the three packages
        `contracts/deploy.py` imports.
        """
        extras = read_extras()
        assert "contracts" in extras, (
            "pyproject.toml no longer declares the `contracts` extra; "
            "issue #92 added it for contracts/deploy.py"
        )
        names = {normalise(req) for req in extras["contracts"]}
        assert names == {"web3", "eth-account", "py-solc-x"}, names
        core = {normalise(req) for req in read_project()["dependencies"]}
        assert not (names & core), (
            f"a chain package reached the core dependency list: "
            f"{sorted(names & core)}. contracts/deploy.py is imported by "
            "no file and collected by no build; it must stay opt-in."
        )
