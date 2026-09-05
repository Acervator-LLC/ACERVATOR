"""A package name lives in `pyproject.toml` and nowhere else.

`TestNoFileHoldsAList` reads every tracked text file and fails a line that names
two or more of `install_words()`. `TestEveryConsumerNamesARealExtra` requires
every extra `tools/deps.py` maps to be declared. `TestEveryImportIsDeclared`
walks `PRODUCT_ROOTS` and requires each import outside the standard library and
FIRST_PARTY to be declared. `TestTheInstrumentCanFail` drives the rule to a
report and to silence.
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

# Session records and lock files, which list resolved packages by design.
EXCLUDED_PREFIXES: tuple[str, ...] = (
    "docs-archive/llm-session-history/",
    "docs/audits/",
    "requirements/",
)
# This file only: the controls below hold the pre-fix lines as string literals
# and trip the rule on their own evidence.
EXCLUDED_FILES: tuple[str, ...] = ("tests/test_one_dependency_source.py",)

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

# `install_words()` adds these to the names read from pyproject.toml. The rule
# fires on a line naming two or more; one name is a sentence, two are a list.
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

# A line that installs. The class before the command carries a quote, so a pip
# argv built inside a string literal still matches.
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
        # A root .py, so a top-level import name rather than a package root.
        "screen_fx",
    }
)

# Import name -> distribution name, for the cases where they differ. No rule
# derives one from the other.
IMPORT_TO_DISTRIBUTION: dict[str, str] = {
    "PIL": "pillow",
    "cv2": "opencv-python",
    "luma": "luma.oled",
    "ST7789": "st7789",
    "tomli": "tomli",
    "eth_account": "eth-account",
    "solcx": "py-solc-x",
}

# Contract 3 skips these: tomli sits in an unreachable `ImportError` arm below
# `import tomllib`, ST7789 inside a `TftColorAdapter.connect` try returning False.
UNDECLARED_ON_PURPOSE: frozenset[str] = frozenset({"tomli", "ST7789"})

# Every FIRST_PARTY root that is a shipped directory. `tests` and
# `dev_harness` ship with nothing; the root `*.py` glob covers the rest.
PRODUCT_ROOTS: tuple[str, ...] = ("src", "tools", "deploy", "contracts")


# Reading the one source


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


# The list rule


def hand_copied_list(line: str, words: set[str]) -> tuple[str, ...]:
    """Return the package names a line installs by hand, or an empty tuple.

    A line qualifies when `_PIP_INSTALL` matches, `_DERIVED` does not, and the
    text up to `_COMMAND_END` names two or more distinct entries of `words`
    after `normalise`. `_DERIVED` is measured on the whole line.
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


# The import inventory


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


def _git_exe() -> str:
    """Return an absolute git path, or fail. A skip is not evidence."""
    import shutil

    git = shutil.which("git")
    if git is None:
        pytest.fail("git not found; tracked files cannot be enumerated")
    return git


# Contract 1


class TestNoFileHoldsAList:
    """No tracked file holds a hand-copied dependency list."""

    def test_no_tracked_file_holds_a_dependency_list(self) -> None:
        hits = scan_for_lists(tracked_files(), install_words())
        assert not hits, (
            "hand-copied dependency list(s) found:\n  "
            + "\n  ".join(hits)
            + "\n\npyproject.toml is the one source. Call "
            "`python -m tools.deps requirements <consumer>` and install "
            "what it prints."
        )

    def test_the_repaired_shell_installers_still_call_the_tool(self) -> None:
        """The repair holds. Deleting the call would pass contract 1."""
        expected = {
            "build_mac.sh": "tools.deps",
            "build_windows.ps1": "tools.deps",
            "deploy/kiosk/install.sh": "tools/deps.py",
            "deploy/kiosk/update.sh": "tools/deps.py",
        }
        missing = []
        for path, needle in expected.items():
            text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
            if needle not in text:
                missing.append(f"{path} no longer names {needle}")
        assert not missing, "; ".join(missing)

    def test_the_python_installer_installs_what_the_one_source_answers(
        self, monkeypatch
    ) -> None:
        """The path behind every root build entry point, driven, not read."""
        import tools.deps as deps
        from tools import build_launcher

        answered = ["only-this-package==1.2.3"]
        installed: list[str] = []

        def record_install(requirement: str) -> bool:
            installed.append(requirement)
            return True

        monkeypatch.setattr(deps, "requirements_for", lambda _extras: answered)
        monkeypatch.setattr(deps, "installed_version", lambda _req: None)
        monkeypatch.setattr(build_launcher, "install_package", record_install)

        assert build_launcher.check_and_install_deps() is True
        assert installed == answered, (
            f"the build path installed {installed}; the one source answered "
            f"{answered}. A hand-copied list would have installed something else"
        )

    def test_the_python_installer_refuses_when_the_one_source_answers_nothing(
        self, monkeypatch
    ) -> None:
        """Control. A file holding its own list would install it regardless."""
        import tools.deps as deps
        from tools import build_launcher

        def no_source(_extras):
            raise deps.DependencySourceError("pyproject.toml is not readable")

        monkeypatch.setattr(deps, "requirements_for", no_source)
        monkeypatch.setattr(
            build_launcher,
            "install_package",
            lambda req: pytest.fail(f"installed {req!r} with no dependency source"),
        )

        assert build_launcher.check_and_install_deps() is False


class TestTheInterpreterFloorIsReadNotHeld:
    """`requires-python` is read from the one source, never copied into a build."""

    def test_the_floor_follows_the_source(self, monkeypatch) -> None:
        """A planted bound moves the floor; a held constant would not."""
        import tools.deps as deps
        from tools import build_launcher

        monkeypatch.setattr(
            deps, "load_project", lambda *_a, **_k: {"requires-python": ">=9.9"}
        )
        assert build_launcher.required_python() == (9, 9)

    def test_the_running_interpreter_meets_the_declared_floor(self) -> None:
        from tools import build_launcher

        assert build_launcher.check_python() is True

    def test_an_interpreter_below_the_declared_floor_is_refused(
        self, monkeypatch
    ) -> None:
        """Control for the check above, which would else pass on any floor."""
        from tools import build_launcher

        monkeypatch.setattr(build_launcher, "required_python", lambda: (99, 0))
        assert build_launcher.check_python() is False

    def test_a_source_stating_no_lower_bound_stops_the_build(self, monkeypatch) -> None:
        import tools.deps as deps
        from tools import build_launcher

        monkeypatch.setattr(
            deps, "load_project", lambda *_a, **_k: {"requires-python": ""}
        )
        with pytest.raises(deps.DependencySourceError):
            build_launcher.required_python()
        assert build_launcher.check_python() is False


# Contract 2


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


# Contract 3


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


# Two-sided control


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


# Two-sided control for the import walk


class TestTheWalkReachesTheContractsTree:
    """Drive `third_party_imports` with `BROKEN_ROOTS` and with `PRODUCT_ROOTS`.

    A failure names the file and the modules in `CHAIN_MODULES`, not a count.
    """

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
