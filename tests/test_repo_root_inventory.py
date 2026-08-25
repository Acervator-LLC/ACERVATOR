"""Every file at the repository root is declared, and says why it is there.

WHAT THIS GUARDS
================
Issue #85 called the root "loose scripts flattened at repo root" and
proposed six moves and one deletion. Six of the seven were REFUSED, and
each refusal rests on a mechanism that this file now pins. A guard that
only counted files would let the same proposal back in next month with
the same reasoning and the same result.

The root is not a folder like any other. Three mechanisms give it
meaning, and all three are read from the tree below rather than
restated here:

1. ``tests/conftest.py`` puts the repository root on ``sys.path``. Every
   ``.py`` file at the root is therefore an importable TOP-LEVEL module
   for the whole test session. ``tests/test_screen_rng_and_signatures``
   uses that: it says ``import splash_screen`` and ``import
   investor_screen``. Move either file and those imports raise.

2. ``tools/spec_common.datas_candidates`` ships the WHOLE ``src`` and
   ``resources`` directories into the frozen application. Issue #85
   proposed moving three dormant marketing screens into one or the
   other. Both destinations would put 79 KB of animation code that
   nothing imports into every build. At the root they ship in no build,
   because PyInstaller starts from ``main.py`` and no import reaches
   them.

3. ``tests/test_one_dependency_source.PRODUCT_ROOTS`` is
   ``("src", "tools", "os", "contracts")`` and the walk beside it adds
   ``REPO_ROOT.glob("*.py")``. A root ``.py`` is inside the import
   contract. Move one to a directory outside that tuple and it leaves
   the contract with NO message: its third-party imports stop being
   read, and an undeclared dependency stops being reported.

WHY AN EXPLICIT LIST AND NOT A GLOB
===================================
Issue #83 measured the failure mode: a list discovered by glob still
passes when a file VANISHES, because the glob and the assertion move
together. INVENTORY below is written out by hand. It is compared with
``git ls-files`` in both directions, so an added file and a deleted file
each fail, and each names itself.

TWO-SIDED
=========
``TestTheRulesFire`` drives every rule with a synthetic listing and a
synthetic inventory. Each rule is shown reporting the case it exists
for. No rule in this file is asserted only in the passing direction.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# The inventory
# ---------------------------------------------------------------------------
#
# Every TRACKED file at the repository root, with the reason it is at the
# root and not in a directory. Untracked files are not subjects: the root
# also carries gitignored scratch output (``gate_*.log``, ``pytest_out
# .txt``), and a guard that failed on those would fail on a normal
# working tree.
#
# A new entry needs a reason that names a MECHANISM. "tidier here" is not
# one. Three of the entries below say plainly that nothing requires the
# location; they are at the root because moving them costs more than it
# buys, and the entry says so rather than inventing a requirement.

INVENTORY: dict[str, str] = {
    # -- repository and tool configuration ------------------------------
    ".gitattributes": "git reads it at the root only",
    ".flake8": "flake8 does not read pyproject.toml; it reads this, at the root only",
    ".python-version": "the ONE interpreter pin. actions/setup-python reads it through python-version-file, and pyproject.toml requires-python must agree",
    ".git-blame-ignore-revs": "git blame --ignore-revs-file reads it at the root; it holds the whole-tree reformat commit so blame skips over it",
    "CLAUDE.md": "repository guidance an agent reads on entry; tooling looks for it at the root and nowhere else",
    ".gitignore": "git reads it at the root only",
    ".vale.ini": "vale reads it from the directory it runs in",
    "pyproject.toml": "the one source for dependencies, pytest config, coverage and "
    "the package version. Build back ends read it at the root",
    # -- entry points a HUMAN is meant to find ---------------------------
    "main.py": "the application entry point. pyproject.toml [project.scripts] "
    'says `acervator = "main:main"`, and both spec files pass '
    "`main.py` to PyInstaller Analysis. Moving it breaks the "
    "console script AND both builds",
    "run_acervator.bat": "operator launch wrapper for Windows. It runs `python main.py` "
    "from the directory it sits in",
    "run_acervator.sh": "operator launch wrapper for macOS and Linux. It runs "
    "`python3 main.py` from the directory it sits in",
    "BUILD.py": "the build driver. It resolves build_windows.ps1 beside itself "
    "with os.path.dirname(__file__), so the two must stay together",
    "build_windows.ps1": "the Windows build script BUILD.py calls by name",
    "build_mac.sh": "the macOS build script, run as ./build_mac.sh",
    "Acervator_win.spec": "PyInstaller spec. It sets PROJECT_ROOT from the SPEC variable, "
    "so the directory it sits in IS the project root for the build",
    "Acervator_mac.spec": "PyInstaller spec, same reason as the Windows one",
    "acervator_watchdog.py": "out-of-process crash watchdog. tools/spec_common.py names "
    "`acervator_watchdog` as a hidden import, which is a TOP-LEVEL "
    "module name; pyproject.toml [tool.coverage.run] names it at "
    "the root as well",
    # -- licence and product documents -----------------------------------
    "LICENSE": "licence, read at the root by convention and by GitHub",
    "NOTICE": "attribution notice, read at the root by convention",
    "README.md": "front page, read at the root by GitHub",
    "CONTRIBUTING.md": "read at the root by GitHub",
    "DISCLAIMER.md": "product disclaimer, shipped beside the licence",
    "CHANGELOG.md": "historical record. src/core/version_sweep.py reads it at "
    '`self.root / "CHANGELOG.md"`',
    "ACERVATOR_HOP7.md": "the live orientation document. It is meant to be the first "
    "thing found at the root",
    "ACERVATOR_HOP2.md": "April archive. src/core/version_sweep.py reads it at "
    '`self.root / "ACERVATOR_HOP2.md"` for stale version strings',
    "ACERVATOR_HOP3.md": "April archive, kept beside HOP2 and HOP4",
    "ACERVATOR_HOP4.md": "April archive, kept beside HOP2 and HOP3",
    "ACERVATOR_DEPT_LEAD_REVIEW_v3_12_0.md": "April review record, kept beside the HOP archives",
    "TESTNET_POA_VERIFY_REPORT.md": "April verification record, kept beside the HOP archives",
    # -- the animation core the three screens share ----------------------
    "screen_fx.py": "issue #74. splash_screen.py, cartoon_screen.py and "
    "investor_screen.py all say `import screen_fx`, a top-level "
    "import that resolves only because conftest puts the root on "
    "sys.path. It may not move to src/ or resources/ for the same "
    "reason they may not: `tools/spec_common.datas_candidates` "
    "copies both directories wholesale, so there it would ship in "
    "EVERY build, and at the root it ships in none. "
    "tests/test_screens_share_one_animation_core.py pins that",
    # -- version-carrying scripts pinned to the root by live tests -------
    "splash_screen.py": "tests/test_screen_rng_and_signatures.py says `import "
    "splash_screen`, a top-level import that resolves only because "
    "conftest puts the root on sys.path. src/core/version_sweep.py "
    'reads it at `self.root / "splash_screen.py"`. Moving it '
    "under src/ or resources/ would also ship it in every build",
    "investor_screen.py": "tests/test_screen_rng_and_signatures.py says `import "
    "investor_screen` and reads its `_cached_prices` signature. "
    "src/core/version_sweep.py reads it at "
    '`self.root / "investor_screen.py"`',
    "generate_essay_ja.py": "tests/test_check_release_readiness.py reads it at "
    '`REPO_ROOT / "generate_essay_ja.py"` in three tests, one of '
    "them the positive control for the `*_FROZEN_AT` exemption. "
    "src/core/version_sweep.py reads it at the root as well",
    # -- scripts nothing requires at the root ----------------------------
    #
    # Each of these three could move. Issue #85 measured what the move
    # would buy and left them where they are. The entry records the
    # measurement, so the next reader does not repeat it.
    "cartoon_screen.py": "a 60-second marketing animation. Nothing imports it and no "
    "test reads it; its stated renderer, render.py, is not in the "
    "tree. It is the one root file with no consumer of any kind. "
    "Deleting an operator marketing asset is the operator's call, "
    "and both destinations issue #85 proposed (src/ or resources/) "
    "would put it INTO every build",
    "download_archive.py": "operator data-ops CLI. Its own docstring documents six "
    "commands as `python download_archive.py ...`. Nothing requires "
    "the location; moving it to tools/ renames six documented "
    "commands and buys tidiness only",
    "generate_essay_localized.py": "five-language essay generator. Nothing requires the location, "
    "but generate_essay_ja.py is pinned to the root by three tests, "
    "and splitting the two essay generators across two directories "
    "reads worse than leaving both here",
}

# Root files that pytest's discovery patterns must NOT match. Issue #85
# emptied this set by renaming `test_scrumming_v3.py` to
# `tools/scrumming_v3_sim.py`. It stays as a named rule rather than an
# implicit one, because the rule is what matters, not the count.
PYTEST_DISCOVERY_PREFIXES = ("test_",)
PYTEST_DISCOVERY_SUFFIXES = ("_test.py",)


# ---------------------------------------------------------------------------
# Reading the tree
# ---------------------------------------------------------------------------


def tracked_root_files() -> set[str]:
    """Every tracked file at the top level of the repository.

    Read from the git index, not from ``iterdir``. The working tree also
    holds gitignored scratch output at the root -- ``gate_*.log``,
    ``pytest_out.txt`` -- and a guard that read the directory would fail
    on a normal working tree.

    The index is read by ``tests/test_one_dependency_source.tracked_
    files``, which already resolves an absolute git path and already
    fails rather than skips when git is missing. Calling it is a reuse,
    not a copy: a second subprocess call here would be a second thing to
    keep right.
    """
    from tests.test_one_dependency_source import tracked_files

    names = {path for path in tracked_files() if "/" not in path}
    if not names:
        pytest.fail(
            "the git index reports no top-level file; the "
            "instrument read nothing and can report nothing"
        )
    return names


def _wears_a_discovery_name(name: str) -> bool:
    """True if pytest's default python_files patterns match ``name``."""
    if not name.endswith(".py"):
        return False
    return name.startswith(PYTEST_DISCOVERY_PREFIXES) or name.endswith(
        PYTEST_DISCOVERY_SUFFIXES
    )


def _module_source(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def test_the_inventory_names_every_tracked_root_file() -> None:
    """A new file at the root must declare itself."""
    undeclared = sorted(tracked_root_files() - set(INVENTORY))
    assert undeclared == [], (
        f"these files are at the repository root and INVENTORY in "
        f"{Path(__file__).name} does not name them: {undeclared}. Add an "
        f"entry that says which mechanism requires the location, or put "
        f"the file in a directory"
    )


def test_the_inventory_names_no_file_that_has_left() -> None:
    """A declaration for a file that has gone is dead cover.

    This is the half a glob cannot do. Issue #83 measured that a
    glob-discovered list still passes when its subject vanishes, because
    the discovery and the assertion move together.
    """
    gone = sorted(set(INVENTORY) - tracked_root_files())
    assert gone == [], (
        f"INVENTORY names files that are no longer tracked at the root: "
        f"{gone}. Delete the entry, or restore the file"
    )


def test_every_inventory_entry_carries_a_reason() -> None:
    """An entry with no reason is a suppression wearing a list."""
    blank = sorted(name for name, why in INVENTORY.items() if not why.strip())
    assert blank == [], f"INVENTORY entries with no reason: {blank}"


def test_no_root_file_wears_pytests_discovery_name() -> None:
    """The defect issue #85 removed, stated as a rule.

    A root ``.py`` named ``test_*.py`` sits outside ``testpaths``, so
    pytest never collects it, and it reads as coverage that is not there.
    ``test_scrumming_v3.py`` sat here in exactly that state from
    2026-04-23 until issue #85 renamed it.
    """
    offenders = sorted(n for n in tracked_root_files() if _wears_a_discovery_name(n))
    assert offenders == [], (
        f"these root files match pytest's discovery patterns but sit "
        f"outside testpaths, so nothing collects them: {offenders}. "
        f"Rename the file, or move it under tests/ AND give it a test "
        f"function"
    )


def test_main_py_is_still_the_declared_entry_point() -> None:
    """The reason main.py may not move, read from the tree."""
    import tomllib

    data = tomllib.loads(_module_source("pyproject.toml"))
    target = data["project"]["scripts"]["acervator"]
    assert target.split(":")[0] == "main", (
        f"pyproject.toml [project.scripts] points at {target!r}. The "
        f"INVENTORY entry for main.py claims it points at `main:`"
    )


@pytest.mark.parametrize("spec", ["Acervator_win.spec", "Acervator_mac.spec"])
def test_each_spec_builds_from_main_py_at_the_root(spec: str) -> None:
    """Both builds start at ``main.py`` in the spec's own directory."""
    source = _module_source(spec)
    assert (
        "PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))" in source
    ), f"{spec} no longer derives PROJECT_ROOT from its own location"
    assert (
        "'main.py'" in source or '"main.py"' in source
    ), f"{spec} no longer names main.py"


def test_the_watchdog_is_still_a_top_level_hidden_import() -> None:
    """The reason acervator_watchdog.py may not move."""
    from tools.spec_common import COMMON_HIDDENIMPORTS

    assert "acervator_watchdog" in COMMON_HIDDENIMPORTS, (
        "tools/spec_common.py no longer names acervator_watchdog as a "
        "hidden import. That name is a TOP-LEVEL module name and it "
        "resolves only while the file is at the repository root"
    )


def test_no_marketing_screen_sits_in_a_directory_the_build_ships() -> None:
    """Issue #85's proposed destinations would ship dormant code.

    ``tools/spec_common.datas_candidates`` copies the whole ``src`` and
    ``resources`` directories into the frozen application. The three
    presentation screens are reached by no import from ``main.py``, so
    at the root they ship in NO build. Under either proposed destination
    they would ship in EVERY build.
    """
    from tools.spec_common import datas_candidates

    shipped_dirs = {
        Path(source).name for source, _dest in datas_candidates(str(REPO_ROOT))
    }
    assert {"src", "resources"} <= shipped_dirs, (
        f"the spec no longer ships src and resources wholesale "
        f"({sorted(shipped_dirs)}); this rule's premise has changed and "
        f"the rule needs rewriting, not deleting"
    )

    screens = ("cartoon_screen.py", "investor_screen.py", "splash_screen.py")
    stowaways = [
        f"{directory}/**/{screen}"
        for directory in ("src", "resources")
        for screen in screens
        if any((REPO_ROOT / directory).rglob(screen))
    ]
    assert stowaways == [], (
        f"a marketing screen is under a directory the build ships "
        f"wholesale: {stowaways}. Nothing imports these files, so at the "
        f"root they cost the build nothing; there they are dead weight "
        f"in every release"
    )


def test_the_root_is_inside_the_dependency_import_contract() -> None:
    """The reason a root ``.py`` may not move to an arbitrary directory.

    ``tests/test_one_dependency_source.py`` walks ``REPO_ROOT.glob
    ("*.py")`` plus ``PRODUCT_ROOTS``. A file moved OUT of the root and
    into a directory that tuple does not name leaves the contract in
    silence.
    """
    from tests.test_one_dependency_source import PRODUCT_ROOTS, product_python_files

    assert "tools" in PRODUCT_ROOTS, (
        "PRODUCT_ROOTS no longer names tools/. Issue #85 moved "
        "scrumming_v3_sim.py there BECAUSE the tuple named it"
    )

    walked = {p.relative_to(REPO_ROOT).as_posix() for p in product_python_files()}
    for name in sorted(n for n in INVENTORY if n.endswith(".py")):
        assert name in walked, (
            f"{name} is at the root and the dependency walk does not " f"reach it"
        )
    assert (
        "tools/scrumming_v3_sim.py" in walked
    ), "the file issue #85 moved has left the dependency walk"


# ---------------------------------------------------------------------------
# Two-sided: each rule, driven with the case it exists for
# ---------------------------------------------------------------------------


class TestTheRulesFire:
    """A rule that is never shown failing is a rule nobody has tested."""

    def test_an_undeclared_file_is_reported(self) -> None:
        listing = set(INVENTORY) | {"scratch_helper.py"}
        assert sorted(listing - set(INVENTORY)) == ["scratch_helper.py"]

    def test_a_vanished_file_is_reported(self) -> None:
        listing = set(INVENTORY) - {"main.py"}
        assert sorted(set(INVENTORY) - listing) == ["main.py"]

    def test_a_blank_reason_is_reported(self) -> None:
        pretend = {"main.py": "", "README.md": "front page"}
        assert sorted(n for n, w in pretend.items() if not w.strip()) == ["main.py"]

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("test_scrumming_v3.py", True),
            ("test_anything.py", True),
            ("anything_test.py", True),
            ("scrumming_v3_sim.py", False),
            ("main.py", False),
            ("test_notes.md", False),
            ("latest_test.txt", False),
        ],
    )
    def test_the_discovery_name_rule_reads_the_name(
        self, name: str, expected: bool
    ) -> None:
        """The rule that emptied the root must answer both ways.

        ``test_scrumming_v3.py`` is the real historical subject and it
        must still be recognised, so the rule cannot rot into one that
        matches nothing.
        """
        assert _wears_a_discovery_name(name) is expected

    def test_the_stowaway_search_finds_a_real_file(self) -> None:
        """Positive control for the marketing-screen rule.

        The search reports an empty list. An empty list is a claim about
        the instrument until the instrument is shown finding something,
        so it is pointed at a file that IS under src/.
        """
        hits = list((REPO_ROOT / "src").rglob("__init__.py"))
        assert hits, (
            "rglob found nothing under src/; the stowaway "
            "search cannot report anything either"
        )

    def test_the_dependency_walk_reads_more_than_nothing(self) -> None:
        """Positive control for the import-contract rule."""
        from tests.test_one_dependency_source import product_python_files

        assert len(product_python_files()) > 100


def test_the_moved_simulator_still_defines_its_public_surface() -> None:
    """The file issue #85 moved must still be the file it was.

    Parsed, not imported: importing it costs a numpy import and a
    ta_engine import for a question the parse tree answers.
    """
    tree = ast.parse(_module_source("tools/scrumming_v3_sim.py"))
    names = {
        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.ClassDef)
    }
    for expected in (
        "ScrumSim",
        "run_scenario",
        "gen_range_bound",
        "gen_bull_run",
        "gen_bear_drop",
        "gen_volatile_chop",
    ):
        assert expected in names, f"{expected} left the simulator"
    assert not any(n.startswith("test") for n in names), (
        "the simulator has grown a test-prefixed name; it is a script "
        "and pytest does not collect it"
    )
