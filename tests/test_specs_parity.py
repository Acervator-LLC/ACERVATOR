r"""Structural pin — Acervator_win.spec, Acervator_mac.spec, tools/spec_common.py.

WHY THIS FILE EXISTS
====================
On 2026-06-18 the mac spec had rotted for about two months. It called
``_build_graceful_datas()`` and ``ACERVATOR_VERSION`` without defining
either, so PyInstaller aborted with ``NameError`` before producing
anything. The Windows spec had both. The two files had drifted silently
because nothing compared them.

WHAT CHANGED — ISSUE #87
========================
The first version of this file compared the two specs as TEXT, with
regular expressions. That had two defects, both measured.

1. **It could only report drift after it happened**, and only in the
   shapes somebody had written a pin for.

2. **It cost 214 seconds.** Measured 2026-08-23 with
   ``pytest --durations``: 22 assertions, of which
   ``test_hiddenimports_match_ignoring_platform`` alone took 214.40 s.
   The cause was catastrophic backtracking in one pattern,
   ``hiddenimports=\(\s*(?:# .*\n\s*)*collect_submodules...``, compiled
   with ``re.DOTALL``. Under DOTALL the ``.`` inside ``# .*\n`` matches
   newlines, so the repeated group could span the whole file and the
   engine explored that space exponentially. Measured in isolation:
   3.2 s against the 7,444-byte win spec, 180.0 s against the
   8,665-byte mac spec. Every line added to either spec made it worse.

Both defects had one root: two copies kept in step by a text
comparison. Issue #87 removed the copies. The shared content lives once
in ``tools/spec_common.py``, and this file pins that it STAYS shared.
The pins below import that module instead of parsing spec text, so the
file runs in milliseconds.

The spec files are still read as text, but only to answer questions
about the spec files themselves: do they import the shared module, and
have they re-grown a private copy of something now shared. Those reads
use substring tests, not regular expressions.
"""

from __future__ import annotations

import ast
import re
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from src._version import BAKED_FILENAME, baked_path
from tools.build_variants import sanitise, windows_file_version
from tools.spec_common import (
    COMMON_HIDDENIMPORTS,
    EXCLUDES,
    FALLBACK_VERSION,
    KEYRING_BACKENDS,
    bake_version_datas,
    build_graceful_datas,
    datas_candidates,
    hiddenimports_for,
    read_acervator_version,
)

REPO = Path(__file__).resolve().parent.parent
WIN_SPEC = REPO / "Acervator_win.spec"
MAC_SPEC = REPO / "Acervator_mac.spec"
SHARED_MODULE = REPO / "tools" / "spec_common.py"
SPEC_DIR = REPO

VARIANT_BAKED_FILENAME = "_baked_variant.txt"


def run_spec(
    spec_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str = "react",
) -> dict:
    """Run a spec file against ``project_root`` and report what it built.

    The spec is copied so ``PROJECT_ROOT``, which it derives from its own
    location, becomes the caller's temporary directory. Nothing is written
    into the repository and no build runs: PyInstaller's builder callables
    are replaced with recorders, so the answer holds the arguments the spec
    actually passed rather than a bundle.

    ``collect_submodules`` is stubbed because walking the real ``src``
    package costs seconds and answers nothing this asks about.
    """
    copied = project_root / spec_path.name
    copied.write_bytes(spec_path.read_bytes())

    recorded: dict = {}

    def recorder(name):
        def record(*_positional, **kwargs):
            recorded[name] = kwargs
            # The spec reads attributes off what Analysis returns and
            # passes them on, so the stand-in has to carry them.
            return SimpleNamespace(
                pure=f"<{name}.pure>",
                zipped_data=f"<{name}.zipped_data>",
                scripts=f"<{name}.scripts>",
                binaries=f"<{name}.binaries>",
                zipfiles=f"<{name}.zipfiles>",
                datas=f"<{name}.datas>",
            )

        return record

    def one_stub_module(*_positional, **_keyword):
        return ["src.stub"]

    monkeypatch.setattr("PyInstaller.utils.hooks.collect_submodules", one_stub_module)
    monkeypatch.setenv("ACERVATOR_BUILD_VARIANT", variant)

    namespace = runpy.run_path(
        str(copied),
        init_globals={
            "SPEC": str(copied),
            "DISTPATH": str(project_root / "dist"),
            "Analysis": recorder("Analysis"),
            "PYZ": recorder("PYZ"),
            "EXE": recorder("EXE"),
            "COLLECT": recorder("COLLECT"),
            "BUNDLE": recorder("BUNDLE"),
        },
    )
    recorded["version"] = namespace["ACERVATOR_VERSION"]
    recorded["variant"] = namespace["ACERVATOR_VARIANT"]
    return recorded


# The names both specs must take from the shared module. Losing any one of
# them means that spec has grown a private copy again.
SHARED_NAMES = (
    "EXCLUDES",
    "bake_version_datas",
    "build_graceful_datas",
    "hiddenimports_for",
    "read_acervator_version",
)

# Text that must NOT reappear in a spec file. Each entry is something
# issue #87 moved out. Its return is the drift this file guards against.
PRIVATE_COPY_MARKERS = (
    "def _read_acervator_version",
    "def _build_graceful_datas",
    "ccxt.async_support.kraken",
    "keyring.backends",
    "'tkinter'",
)


@pytest.fixture(scope="module")
def win_src() -> str:
    return WIN_SPEC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def mac_src() -> str:
    return MAC_SPEC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The rules, as functions, so the controls at the bottom can drive them
# ---------------------------------------------------------------------------


def shared_names_imported(src: str) -> set[str]:
    """Return the shared names a spec file imports, by reading its text.

    Substring tests, not a regular expression. The pattern this file
    replaced was the 214-second test; the repair is wasted if the
    replacement reaches for the same tool.
    """
    marker = "from tools.spec_common import"
    if marker not in src:
        return set()
    start = src.index(marker)
    end = src.index(")", start)
    block = src[start:end]
    return {name for name in SHARED_NAMES if name in block}


def private_copies(src: str) -> tuple[str, ...]:
    """Return the shared-content markers that have reappeared in ``src``."""
    return tuple(marker for marker in PRIVATE_COPY_MARKERS if marker in src)


def top_level_imports(path: Path) -> set[str]:
    """Return every top-level package name a module imports, via AST.

    Reading the source for the word 'PyInstaller' would hit the prose in
    the docstring, so this walks the import statements instead.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


# ---------------------------------------------------------------------------
# The files exist
# ---------------------------------------------------------------------------


class TestSpecsExist:
    def test_win_spec_present(self):
        assert WIN_SPEC.is_file(), f"missing {WIN_SPEC}"

    def test_mac_spec_present(self):
        assert MAC_SPEC.is_file(), f"missing {MAC_SPEC}"

    def test_shared_module_present(self):
        assert SHARED_MODULE.is_file(), (
            "tools/spec_common.py missing — both specs import it and "
            "neither can build without it."
        )

    def test_build_mac_script_present(self):
        assert (REPO / "build_mac.sh").is_file(), "build_mac.sh missing"

    def test_build_windows_script_present(self):
        assert (
            REPO / "build_windows.ps1"
        ).is_file(), "build_windows.ps1 missing — BUILD.py runs it."


# ---------------------------------------------------------------------------
# Both specs take the shared content from the shared module
# ---------------------------------------------------------------------------


class TestSpecsUseTheSharedModule:
    def test_win_imports_every_shared_name(self, win_src):
        assert shared_names_imported(win_src) == set(SHARED_NAMES)

    def test_mac_imports_every_shared_name(self, mac_src):
        assert shared_names_imported(mac_src) == set(SHARED_NAMES)

    def test_win_holds_no_private_copy(self, win_src):
        assert private_copies(win_src) == (), (
            "Acervator_win.spec has re-grown shared content. It belongs "
            "in tools/spec_common.py so both platforms follow one change."
        )

    def test_mac_holds_no_private_copy(self, mac_src):
        assert private_copies(mac_src) == (), (
            "Acervator_mac.spec has re-grown shared content. It belongs "
            "in tools/spec_common.py so both platforms follow one change."
        )

    def test_win_asks_for_the_windows_platform(self, win_src):
        assert "hiddenimports_for('windows')" in win_src

    def test_mac_asks_for_the_macos_platform(self, mac_src):
        assert "hiddenimports_for('macos')" in mac_src

    def test_both_keep_collect_submodules_in_the_spec(self, win_src, mac_src):
        """``collect_submodules`` needs PyInstaller, so it stays in the
        spec and the shared module stays importable anywhere."""
        for label, src in (("win", win_src), ("mac", mac_src)):
            assert (
                "collect_submodules('src')" in src
            ), f"{label} spec must still call collect_submodules('src')"

    def test_the_shared_module_does_not_import_pyinstaller(self):
        """If it grows a PyInstaller import, this test file stops running
        on a machine that has no PyInstaller, and the cheap pin is gone.
        `src` is allowed: `src._version` owns the version and imports
        stdlib only."""
        imported = top_level_imports(SHARED_MODULE)
        assert "PyInstaller" not in imported
        assert imported == {"__future__", "os", "src"}


# ---------------------------------------------------------------------------
# The shared hidden imports
# ---------------------------------------------------------------------------


class TestHiddenImports:
    def test_the_only_difference_is_the_keyring_backend(self):
        win = set(hiddenimports_for("windows"))
        mac = set(hiddenimports_for("macos"))
        assert win - mac == {"keyring.backends.Windows"}
        assert mac - win == {"keyring.backends.macOS"}

    def test_the_common_list_holds_no_keyring_backend(self):
        """The backend comes from the platform argument. If it were in the
        common list, both backends would ship on both platforms."""
        for backend in KEYRING_BACKENDS.values():
            assert backend not in COMMON_HIDDENIMPORTS

    def test_watchdog_present(self):
        """MEM-219 — the self-supervising watchdog must ship on both."""
        assert "acervator_watchdog" in COMMON_HIDDENIMPORTS

    def test_no_duplicate_names(self):
        assert len(set(COMMON_HIDDENIMPORTS)) == len(COMMON_HIDDENIMPORTS)

    def test_an_unknown_platform_raises(self):
        """It must not answer the common list with no backend. A build
        with no keyring backend cannot reach the operator's credentials."""
        with pytest.raises(ValueError, match="unknown spec platform"):
            hiddenimports_for("linux")

    def test_the_set_did_not_shrink(self):
        """A dropped hidden import does not fail the build. It fails the
        frozen application at run time, on the operator's machine. The
        count is pinned so a deletion has to be deliberate."""
        assert len(COMMON_HIDDENIMPORTS) == 37, (
            f"COMMON_HIDDENIMPORTS holds {len(COMMON_HIDDENIMPORTS)} "
            f"names, not 37. If the change is intended, update this pin "
            f"and say in the commit which name moved and why."
        )


# ---------------------------------------------------------------------------
# The shared excludes
# ---------------------------------------------------------------------------


class TestExcludes:
    def test_matplotlib_is_excluded(self):
        """pyproject.toml's `charts` extra rests on both specs excluding
        matplotlib; src/design_system.py imports it with no guard."""
        assert "matplotlib" in EXCLUDES

    def test_excludes_hold_no_duplicates(self):
        assert len(set(EXCLUDES)) == len(EXCLUDES)


# ---------------------------------------------------------------------------
# The shared version reader
# ---------------------------------------------------------------------------


class TestVersionHelper:
    def test_it_reads_the_repo_version(self):
        import src

        assert read_acervator_version(str(REPO)) == src.__version__

    def test_it_falls_back_when_nothing_resolves(self, tmp_path):
        """No repository and no baked file means no version to report."""
        assert read_acervator_version(str(tmp_path)) == FALLBACK_VERSION

    def test_it_reads_a_baked_version(self, tmp_path):
        """A tree carrying a build-time stamp reports that stamp."""
        baked_path(tmp_path).parent.mkdir()
        baked_path(tmp_path).write_text("9.9.9\n", encoding="utf-8")
        assert read_acervator_version(str(tmp_path)) == "9.9.9"

    def test_a_version_literal_is_no_longer_read(self, tmp_path):
        """A planted literal must not resurrect the retired reader."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text(
            '__version__ = "9.9.9"\n', encoding="utf-8"
        )
        assert read_acervator_version(str(tmp_path)) == FALLBACK_VERSION

    def test_mac_bundle_version_comes_from_the_reader(self, mac_src):
        """BUNDLE(version=...) and both plist keys must be
        ACERVATOR_VERSION, never a literal."""
        assert re.search(r"version\s*=\s*ACERVATOR_VERSION", mac_src)
        assert re.search(r"CFBundleVersion['\"]\s*:\s*ACERVATOR_VERSION", mac_src)
        assert re.search(
            r"CFBundleShortVersionString['\"]\s*:\s*ACERVATOR_VERSION", mac_src
        )

    def test_win_file_description_carries_the_resolved_version(
        self, tmp_path, monkeypatch
    ):
        """Run the spec and read the resource block it actually built.

        The icon has to exist: the spec writes ``version_info`` only when
        it does, so without one there is no resource block to read.
        """
        icon = tmp_path / "resources" / "icon.ico"
        icon.parent.mkdir(parents=True, exist_ok=True)
        icon.write_bytes(b"\x00")
        built = run_spec(SPEC_DIR / "Acervator_win.spec", tmp_path, monkeypatch)
        resource = built["EXE"]["version_info"]
        assert built["version"] in resource["FileDescription"], (
            f"FileDescription {resource['FileDescription']!r} does not carry "
            f"the resolved version {built['version']!r}"
        )

    def test_win_numeric_resource_fields_are_not_a_literal(self, tmp_path, monkeypatch):
        """FileVersion and ProductVersion read a hardcoded 1.1.0 until this seam."""
        icon = tmp_path / "resources" / "icon.ico"
        icon.parent.mkdir(parents=True, exist_ok=True)
        icon.write_bytes(b"\x00")
        built = run_spec(SPEC_DIR / "Acervator_win.spec", tmp_path, monkeypatch)
        resource = built["EXE"]["version_info"]
        expected = windows_file_version(built["version"])
        for field in ("FileVersion", "ProductVersion"):
            assert resource[field] == expected, (
                f"{field} reads {resource[field]!r}, not the resolved " f"{expected!r}"
            )


# ---------------------------------------------------------------------------
# The shared datas builder
# ---------------------------------------------------------------------------


class TestGracefulDatas:
    def test_src_ships_first(self):
        assert datas_candidates("/root")[0][1] == "src"

    def test_every_candidate_is_a_directory_this_repository_can_hold(self):
        dests = [Path(dest).as_posix() for _, dest in datas_candidates("/root")]
        assert dests == ["src", "resources", "data/historical"], (
            f"datas_candidates offers {dests}; every entry must name a "
            f"directory a build of this repository can actually produce"
        )

    def test_absent_paths_are_skipped(self, tmp_path):
        assert build_graceful_datas(str(tmp_path)) == []

    def test_a_present_path_is_kept(self, tmp_path):
        (tmp_path / "src").mkdir()
        kept = build_graceful_datas(str(tmp_path))
        assert [dest for _, dest in kept] == ["src"]

    def test_the_baked_version_is_a_separate_pair(self, tmp_path):
        """The bake must not ride inside build_graceful_datas: that builder
        answers [] for an empty tree, and a version file hidden in it would
        make the empty answer non-empty."""
        assert build_graceful_datas(str(tmp_path)) == []
        pairs = bake_version_datas(str(tmp_path))
        assert [dest for _, dest in pairs] == ["src"]
        assert Path(pairs[0][0]).name == BAKED_FILENAME

    @pytest.mark.parametrize("spec", ["Acervator_win.spec", "Acervator_mac.spec"])
    def test_both_specs_ship_the_baked_version(self, spec, tmp_path, monkeypatch):
        """A spec that dropped the pair would build a bundle with no version."""
        built = run_spec(SPEC_DIR / spec, tmp_path, monkeypatch)
        shipped = dict(
            (Path(source).name, dest) for source, dest in built["Analysis"]["datas"]
        )
        assert shipped.get(BAKED_FILENAME) == "src", (
            f"{spec} does not ship {BAKED_FILENAME} to src; "
            f"it ships {sorted(shipped)}"
        )
        baked = tmp_path / "build" / "version" / BAKED_FILENAME
        assert (
            baked.read_text(encoding="utf-8").strip() == built["version"]
        ), f"{spec} baked a version that is not the one it resolved"

    @pytest.mark.parametrize("spec", ["Acervator_win.spec", "Acervator_mac.spec"])
    def test_both_specs_ship_the_baked_variant(self, spec, tmp_path, monkeypatch):
        """The variant travels into the bundle the same way the version does."""
        built = run_spec(SPEC_DIR / spec, tmp_path, monkeypatch, variant="qt")
        shipped = dict(
            (Path(source).name, dest) for source, dest in built["Analysis"]["datas"]
        )
        assert shipped.get(VARIANT_BAKED_FILENAME) == "src", (
            f"{spec} does not ship {VARIANT_BAKED_FILENAME} to src; "
            f"it ships {sorted(shipped)}"
        )
        baked = tmp_path / "build" / "version" / VARIANT_BAKED_FILENAME
        assert baked.read_text(encoding="utf-8").strip() == "qt"

    @pytest.mark.parametrize("spec", ["Acervator_win.spec", "Acervator_mac.spec"])
    def test_the_output_name_carries_the_version_and_the_variant(
        self, spec, tmp_path, monkeypatch
    ):
        """Two variants of one version must not claim the same folder."""
        react = run_spec(SPEC_DIR / spec, tmp_path, monkeypatch, variant="react")
        qt = run_spec(SPEC_DIR / spec, tmp_path, monkeypatch, variant="qt")
        for built, variant in ((react, "react"), (qt, "qt")):
            # COLLECT names the dist folder and EXE names the executable
            # inside it. BUILD.py looks for dist/<name>/<name>.exe, so both
            # have to carry the version and the variant or it finds nothing.
            for stage in ("COLLECT", "EXE"):
                name = built[stage]["name"]
                assert (
                    sanitise(built["version"]) in name
                ), f"{stage} name {name!r} omits the version"
                assert variant in name, f"{stage} name {name!r} omits the variant"
            assert built["COLLECT"]["name"] == built["EXE"]["name"], (
                f"folder {built['COLLECT']['name']!r} and executable "
                f"{built['EXE']['name']!r} disagree; BUILD.py would find neither"
            )
        assert (
            react["COLLECT"]["name"] != qt["COLLECT"]["name"]
        ), "both variants claimed the same output folder"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


class TestEntryPoint:
    def test_both_use_main_py(self, win_src, mac_src):
        for label, src in (("win", win_src), ("mac", mac_src)):
            assert (
                "'main.py'" in src or '"main.py"' in src
            ), f"{label} spec must build from main.py"


# ---------------------------------------------------------------------------
# Two-sided control — every rule above must be able to report
# ---------------------------------------------------------------------------


class TestTheInstrumentCanFail:
    """Point each rule at drifted input and require it to fire.

    Without this, a rule that silently matches nothing reads exactly like
    a rule that found nothing wrong.
    """

    def test_the_import_rule_reports_a_missing_import(self):
        assert shared_names_imported("a = Analysis([])\n") == set()

    def test_the_import_rule_reports_a_partial_import(self):
        drifted = (
            "from tools.spec_common import (\n"
            "    EXCLUDES,\n"
            "    read_acervator_version,\n"
            ")\n"
        )
        found = shared_names_imported(drifted)
        assert found == {"EXCLUDES", "read_acervator_version"}
        assert found != set(SHARED_NAMES)

    def test_the_import_rule_accepts_a_complete_import(self):
        complete = (
            "from tools.spec_common import (\n"
            + "".join(f"    {name},\n" for name in SHARED_NAMES)
            + ")\n"
        )
        assert shared_names_imported(complete) == set(SHARED_NAMES)

    @pytest.mark.parametrize("marker", PRIVATE_COPY_MARKERS)
    def test_the_private_copy_rule_reports_each_marker(self, marker):
        """Drive the rule with the pre-issue-87 shape, one marker at a
        time. A rule that fires on only one of the five would still show
        green against the other four."""
        planted = f"# a spec that forked again\n{marker}\n"
        assert private_copies(planted) == (marker,)

    def test_the_private_copy_rule_stays_quiet_on_clean_text(self):
        assert private_copies("a = Analysis([])\n") == ()

    def test_the_import_rule_reports_the_pre_issue_87_spec(self):
        """The strongest control: the win spec as it stood before this
        issue imported nothing shared and held every marker."""
        old_shape = (
            "import os\n"
            "def _read_acervator_version(project_root):\n"
            "    pass\n"
            "def _build_graceful_datas(project_root):\n"
            "    pass\n"
            "hiddenimports = ['ccxt.async_support.kraken',\n"
            "                 'keyring.backends.Windows']\n"
            "excludes = ['tkinter']\n"
        )
        assert shared_names_imported(old_shape) == set()
        assert set(private_copies(old_shape)) == set(PRIVATE_COPY_MARKERS)

    def test_the_stdlib_rule_reports_a_pyinstaller_import(self, tmp_path):
        planted = tmp_path / "planted.py"
        planted.write_text(
            "from PyInstaller.utils.hooks import collect_submodules\n", encoding="utf-8"
        )
        assert "PyInstaller" in top_level_imports(planted)

    def test_the_datas_rule_reports_a_directory_that_exists(self, tmp_path):
        """`test_absent_paths_are_skipped` expects [], which is also what
        a broken builder returns. This is its positive control."""
        (tmp_path / "resources").mkdir()
        assert build_graceful_datas(str(tmp_path)) != []
