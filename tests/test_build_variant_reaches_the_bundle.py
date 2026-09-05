"""One variant name travels from a build entry point to the bundle that reports it.

``ENV_VAR`` is the single environment variable ``requested_variant`` and
``resolve_variant`` both read, ``run_build`` puts the chosen names on the
``build_windows.ps1`` argv, and the spec bakes the answer into the bundle.
``BUILD.py`` chooses through ``parse_variants``; ``React_BUILD.py`` and
``Qt_BUILD.py`` pin ``VARIANT`` and read no argv at all.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import _variant
from src._variant import (
    BAKED_FILENAME as VARIANT_BAKED_FILENAME,
)
from src._variant import (
    DEFAULT_VARIANT,
    ENV_VAR,
    QT,
    REACT,
    VARIANTS,
    resolve_variant,
)
from tests.fixtures.spec_runner import run_spec
from tools import build_launcher
from tools.build_variants import (
    APP_NAME,
    requested_variant,
    selected_variants,
    windows_version_fields,
)

REPO = Path(__file__).resolve().parents[1]
WIN_SPEC = REPO / "Acervator_win.spec"
MAC_SPEC = REPO / "Acervator_mac.spec"
SPECS = ["Acervator_win.spec", "Acervator_mac.spec"]

# The entry points that take no argument, and the surface each one pins.
PINNED_ENTRY_POINTS = [
    pytest.param("React_BUILD.py", REACT, id="react"),
    pytest.param("Qt_BUILD.py", QT, id="qt"),
]

RETIRED_ENV_VAR = "ACERVATOR_BUILD_VARIANT"
CLI = [sys.executable, "-m", "tools.build_variants"]
CLI_TIMEOUT = 120
UNKNOWN_VARIANT = "electron"
BAD_ARGUMENT_EXIT = 2


def names_a_spec_imports(spec: Path) -> set[str]:
    """Return the names ``spec`` asks ``tools.build_variants`` for, read by AST."""
    tree = ast.parse(spec.read_text(encoding="utf-8"))
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "tools.build_variants"
        for alias in node.names
    }


def other_variant(name: str) -> str:
    """Return the ``VARIANTS`` entry that is not ``name``."""
    return QT if name == REACT else REACT


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run ``python -m tools.build_variants`` with ``args`` from the repo root."""
    return subprocess.run(  # noqa: S603
        [*CLI, *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=CLI_TIMEOUT,
        check=False,
    )


def load_entry_point(path: Path, name: str):
    """Import a root build entry point under ``name``, restoring the directory.

    ``launch`` changes directory when it runs, which no other test may inherit.
    """
    original = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.chdir(original)
    return module


def variant_token_for(variants: tuple[str, ...]) -> str:
    """Return the ``-Variant`` token ``run_build`` puts on the builder's argv."""
    calls = []

    def record(argv, **_keyword):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(build_launcher, "powershell_exe", lambda: "powershell.exe")
        patched.setattr(subprocess, "run", record)
        build_launcher.run_build(variants)
    argv = calls[0]
    assert "-Variant" in argv, f"no variant reached build_windows.ps1: {argv}"
    return argv[argv.index("-Variant") + 1]


@pytest.fixture(scope="module")
def launcher():
    """Import ``BUILD.py`` under a private name."""
    return load_entry_point(REPO / "BUILD.py", "acervator_build_entry")


# One environment variable, read by the build and by the application


@pytest.mark.parametrize("variant", VARIANTS)
def test_one_variable_answers_both_the_build_and_the_application(
    variant, tmp_path, monkeypatch
):
    """The builder and the running application read the same name."""
    monkeypatch.setattr(_variant, "is_frozen", lambda: False)
    monkeypatch.setenv(ENV_VAR, variant)
    assert requested_variant() == variant, "the build side missed the variable"
    assert resolve_variant(tmp_path) == variant, "the application side missed it"


def test_the_retired_build_variable_selects_nothing(tmp_path, monkeypatch):
    """Two names let one half of the build be set while the other stayed unset."""
    monkeypatch.setattr(_variant, "is_frozen", lambda: False)
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setenv(RETIRED_ENV_VAR, QT)
    assert requested_variant() == DEFAULT_VARIANT, (
        f"{RETIRED_ENV_VAR} still steers the build; it is a second name for "
        f"{ENV_VAR} and the two drift apart"
    )
    assert resolve_variant(tmp_path) == DEFAULT_VARIANT


# Choosing the variants to build


def test_no_name_chooses_every_variant():
    assert selected_variants([]) == tuple(VARIANTS)


def test_one_name_chooses_that_variant_alone():
    assert selected_variants([QT]) == (QT,)


def test_a_comma_separated_name_chooses_several():
    assert selected_variants([f"{QT},{REACT}"]) == tuple(VARIANTS)


def test_a_repeated_flag_chooses_several():
    assert selected_variants([QT, REACT]) == tuple(VARIANTS)


def test_a_name_given_twice_is_chosen_once():
    assert selected_variants([QT, QT]) == (QT,)


def test_an_unknown_name_is_refused_rather_than_built_as_the_default():
    with pytest.raises(ValueError, match=UNKNOWN_VARIANT):
        selected_variants([UNKNOWN_VARIANT])


# The command line the shell builders read


def test_the_cli_prints_the_environment_variable_the_spec_reads():
    result = run_cli("env-var")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ENV_VAR


def test_the_cli_prints_the_chosen_variants_one_per_line():
    result = run_cli("select", "--variant", f"{QT},{REACT}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == list(VARIANTS)


def test_the_cli_refuses_an_unknown_variant():
    result = run_cli("select", "--variant", UNKNOWN_VARIANT)
    assert result.returncode == BAD_ARGUMENT_EXIT, (
        f"the CLI answered {result.returncode} for {UNKNOWN_VARIANT!r}; a "
        f"shell builder would have built the default and named it wrongly"
    )
    assert UNKNOWN_VARIANT in result.stderr


@pytest.mark.parametrize("spec", SPECS)
def test_every_name_a_spec_asks_the_variant_module_for_is_defined(spec):
    """A missing name stops PyInstaller on the operator's machine, not here."""
    import tools.build_variants as module

    wanted = names_a_spec_imports(REPO / spec)
    assert wanted, f"{spec} imports nothing from tools.build_variants"
    missing = sorted(name for name in wanted if not hasattr(module, name))
    assert not missing, f"{spec} imports {missing}, which the module does not define"


def test_the_import_reader_reports_a_name_the_module_does_not_define(tmp_path):
    """Control: the reader above answers nothing on a spec that asks for nothing."""
    planted = tmp_path / "planted.spec"
    planted.write_text(
        "from tools.build_variants import no_such_name\n", encoding="utf-8"
    )
    assert names_a_spec_imports(planted) == {"no_such_name"}
    bare = tmp_path / "bare.spec"
    bare.write_text("a = 1\n", encoding="utf-8")
    assert names_a_spec_imports(bare) == set()


# BUILD.py, and the argv it hands the Windows builder


def test_the_launcher_builds_every_variant_when_none_is_named(launcher):
    assert launcher.parse_variants([]) == tuple(VARIANTS)


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_launcher_builds_only_the_variant_named(launcher, variant):
    assert launcher.parse_variants(["--variant", variant]) == (variant,)


def test_the_launcher_refuses_an_unknown_variant(launcher):
    with pytest.raises(ValueError, match=UNKNOWN_VARIANT):
        launcher.parse_variants(["--variant", UNKNOWN_VARIANT])


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_launcher_hands_the_variant_to_the_windows_builder(variant, monkeypatch):
    """``BUILD.py`` named no variant at all before ``parse_variants``."""
    calls = []

    def record(argv, **_keyword):
        assert argv[0] == "powershell.exe", f"the launcher spawned {argv[0]!r}"
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(build_launcher, "powershell_exe", lambda: "powershell.exe")
    monkeypatch.setattr(subprocess, "run", record)

    assert build_launcher.run_build((variant,)) is True, "the launcher reported failure"
    argv = calls[0]
    assert "-Variant" in argv, f"no variant reached build_windows.ps1: {argv}"
    assert argv[argv.index("-Variant") + 1] == variant


def test_the_launcher_joins_several_variants_into_one_argument():
    """PowerShell binds one argv token to -Variant, so the names travel joined."""
    assert variant_token_for(tuple(VARIANTS)) == ",".join(VARIANTS)


# React_BUILD.py and Qt_BUILD.py, which take no argument


@pytest.mark.parametrize(("filename", "variant"), PINNED_ENTRY_POINTS)
def test_a_pinned_entry_point_names_its_own_surface(filename, variant):
    module = load_entry_point(REPO / filename, f"acervator_entry_{variant}")
    assert module.VARIANT == variant, (
        f"{filename} pins {module.VARIANT!r}; the operator double-clicks it "
        f"expecting the {variant} surface"
    )


@pytest.mark.parametrize(("filename", "variant"), PINNED_ENTRY_POINTS)
def test_an_argument_cannot_make_a_pinned_entry_point_build_the_other_surface(
    filename, variant, monkeypatch
):
    """The argument that steers ``BUILD.py`` must reach nothing here."""
    module = load_entry_point(REPO / filename, f"acervator_entry_argv_{variant}")
    asked = []
    monkeypatch.setattr(module, "launch", asked.append)
    monkeypatch.setattr("builtins.input", lambda *_prompt: "")
    monkeypatch.setattr(sys, "argv", [filename, "--variant", other_variant(variant)])

    module.main()

    assert asked == [(variant,)], (
        f"{filename} asked to build {asked}; `--variant "
        f"{other_variant(variant)}` on its command line must select nothing"
    )


def test_the_pin_check_reports_an_entry_point_that_names_the_other_surface(
    tmp_path, monkeypatch
):
    """Control: the check above, driven at a file whose ``VARIANT`` is flipped."""
    planted = tmp_path / "Flipped_BUILD.py"
    planted.write_text(
        "from src._variant import QT\n"
        "from tools.build_launcher import launch\n"
        "VARIANT = QT\n"
        "def main():\n"
        "    launch((VARIANT,))\n",
        encoding="utf-8",
    )
    module = load_entry_point(planted, "acervator_entry_flipped")
    asked = []
    monkeypatch.setattr(module, "launch", asked.append)

    module.main()

    assert module.VARIANT != REACT, "the control does not differ from React_BUILD.py"
    assert asked != [(REACT,)], "the check cannot tell the two surfaces apart"
    assert asked == [(QT,)]


@pytest.mark.parametrize(("filename", "variant"), PINNED_ENTRY_POINTS)
def test_a_pinned_entry_points_surface_reaches_the_bundle(
    filename, variant, tmp_path, monkeypatch
):
    """The whole path: the pin, the builder argv, the CLI, the spec, the bundle."""
    module = load_entry_point(REPO / filename, f"acervator_entry_reach_{variant}")

    token = variant_token_for((module.VARIANT,))
    assert token == variant, f"{filename} put {token!r} on the builder argv"

    chosen = run_cli("select", "--variant", token)
    assert chosen.returncode == 0, chosen.stderr
    assert chosen.stdout.split() == [variant], (
        f"build_windows.ps1 asks the CLI for {token!r} and it answered "
        f"{chosen.stdout.split()}"
    )

    built = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=chosen.stdout.split()[0])
    bundle = bundle_from(built["Analysis"], tmp_path)
    monkeypatch.setattr(_variant, "is_frozen", lambda: True)
    monkeypatch.setenv(ENV_VAR, other_variant(variant))
    reported = resolve_variant(bundle)
    assert reported == variant, (
        f"{filename} built the {variant} surface and the bundle reports "
        f"{reported!r}"
    )


@pytest.mark.parametrize(("filename", "variant"), PINNED_ENTRY_POINTS)
def test_two_runs_of_one_entry_point_leave_two_runnable_builds(
    filename, variant, tmp_path, monkeypatch
):
    """The troubleshooting case: run the build before this one against this one."""
    module = load_entry_point(REPO / filename, f"acervator_entry_dist_{variant}")
    dist = tmp_path / "dist"
    dist.mkdir()

    first = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=module.VARIANT)
    first_name = first["COLLECT"]["name"]
    first_exe = materialise(dist, first_name, b"first")

    second = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=module.VARIANT)
    second_name = second["COLLECT"]["name"]
    second_exe = materialise(dist, second_name, b"second")

    assert variant in first_name and variant in second_name
    assert second_name != first_name, (
        f"the second run of {filename} claimed {first_name!r}, the folder the "
        f"first build holds"
    )
    assert first_exe.read_bytes() == b"first", "the rebuild overwrote the first build"
    assert second_exe.read_bytes() == b"second"


def test_only_the_folders_a_run_added_are_reported(tmp_path, monkeypatch):
    """A rebuild reports what it produced, never the builds already in dist."""
    dist = tmp_path / "dist"
    dist.mkdir()
    for stale in ("Acervator-1.0.0-react", "Acervator-1.0.0-qt"):
        materialise(dist, stale, b"old")
    monkeypatch.setattr(build_launcher, "PROJECT_ROOT", str(tmp_path))

    before = build_launcher.build_folder_names()
    fresh = materialise(dist, "Acervator-2.0.0-react", b"new")

    assert build_launcher.build_outputs(skip=frozenset(before)) == [str(fresh)]
    assert len(build_launcher.build_outputs()) == 3, (
        "the unfiltered read is the control; it must see all three builds or "
        "the filtered read above proves nothing"
    )


# The spec bakes the variant, and a bundle reports it


def bundle_from(analysis: dict, root: Path) -> Path:
    """Lay the variant pair the spec shipped out the way PyInstaller unpacks it."""
    shipped = {Path(source).name: (source, dest) for source, dest in analysis["datas"]}
    source, dest = shipped[VARIANT_BAKED_FILENAME]
    bundle = root / "bundle"
    (bundle / dest).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, bundle / dest / VARIANT_BAKED_FILENAME)
    return bundle


@pytest.mark.parametrize("spec", SPECS)
@pytest.mark.parametrize("variant", VARIANTS)
def test_a_bundle_reports_the_variant_it_was_built_as(
    spec, variant, tmp_path, monkeypatch
):
    """The environment holds the other variant, so only the bake can answer."""
    built = run_spec(REPO / spec, tmp_path, monkeypatch, variant=variant)
    bundle = bundle_from(built["Analysis"], tmp_path)

    monkeypatch.setattr(_variant, "is_frozen", lambda: True)
    monkeypatch.setenv(ENV_VAR, other_variant(variant))
    reported = resolve_variant(bundle)
    assert reported == variant, (
        f"{spec} built the {variant} variant and the bundle reports "
        f"{reported!r}; the two executables would be indistinguishable"
    )


@pytest.mark.parametrize("spec", SPECS)
def test_two_bundles_of_one_spec_report_different_variants(spec, tmp_path, monkeypatch):
    """Positive control: ``resolve_variant`` tracks the bake, not one fixed answer."""
    first = run_spec(REPO / spec, tmp_path, monkeypatch, variant=REACT)
    react_bundle = bundle_from(first["Analysis"], tmp_path / "a")
    second = run_spec(REPO / spec, tmp_path, monkeypatch, variant=QT)
    qt_bundle = bundle_from(second["Analysis"], tmp_path / "b")

    monkeypatch.setattr(_variant, "is_frozen", lambda: True)
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert resolve_variant(react_bundle) == REACT
    assert resolve_variant(qt_bundle) == QT


def test_the_mac_bundle_name_carries_the_variant(tmp_path, monkeypatch):
    """``build_mac.sh`` names each DMG after the bundle the run produced."""
    react = run_spec(MAC_SPEC, tmp_path, monkeypatch, variant=REACT)["BUNDLE"]["name"]
    qt = run_spec(MAC_SPEC, tmp_path, monkeypatch, variant=QT)["BUNDLE"]["name"]
    assert react.endswith(".app") and qt.endswith(".app")
    assert react != qt, f"both variants claimed the bundle {react!r}"


def test_the_windows_resource_names_the_variant_it_was_built_as(tmp_path, monkeypatch):
    """Explorer's Properties pane is where the operator tells two builds apart."""
    built = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=QT)
    description = windows_version_fields(
        built["version"], built["variant"], built["EXE"]["name"]
    )["FileDescription"]
    assert QT in description, f"FileDescription {description!r} omits the variant"
    assert REACT not in description
    assert description in str(built["EXE"]["version"]), (
        f"the spec did not hand EXE the description {description!r}; "
        f"it handed {built['EXE']['version']}"
    )


def test_the_windows_resource_reaches_the_keyword_pyinstaller_reads(
    tmp_path, monkeypatch
):
    """``version_info`` was dropped without a warning and shipped a blank pane."""
    built = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=QT)
    resource = built["EXE"].get("version")
    assert type(resource).__name__ == "VSVersionInfo", (
        f"EXE was handed {type(resource)!r} as version; only a "
        f"VSVersionInfo reaches the executable"
    )
    assert "version_info" not in built["EXE"], "the ignored keyword is back"


# Builds accumulate in dist


def materialise(dist: Path, name: str, body: bytes) -> Path:
    """Write ``dist/name/name.exe`` holding ``body`` and return that path."""
    folder = dist / name
    folder.mkdir(parents=True)
    executable = folder / f"{name}.exe"
    executable.write_bytes(body)
    return executable


def test_both_variants_of_one_version_stand_in_dist_together(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    produced = {}
    for variant in VARIANTS:
        built = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=variant)
        name = built["COLLECT"]["name"]
        produced[variant] = materialise(dist, name, variant.encode())

    assert len(set(produced.values())) == len(VARIANTS), f"{produced} collided"
    for variant, executable in produced.items():
        assert (
            executable.read_bytes() == variant.encode()
        ), f"the {variant} build was overwritten by the other variant: {executable}"


def test_the_name_the_old_build_claimed_would_have_collided(tmp_path, monkeypatch):
    """Control for the test above: the fixed name really is one name."""
    produced = [
        run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=v)["COLLECT"]["name"]
        for v in VARIANTS
    ]
    fixed = [APP_NAME for _ in VARIANTS]
    assert len(set(fixed)) == 1, "the control is not a collision"
    assert len(set(produced)) == len(VARIANTS), f"the new naming collided: {produced}"


def test_a_newer_version_of_one_variant_leaves_the_older_build_runnable(
    tmp_path, monkeypatch
):
    dist = tmp_path / "dist"
    dist.mkdir()
    monkeypatch.setattr(
        "tools.spec_common.read_acervator_version", lambda _root: "1.0.0"
    )
    older = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=QT)["COLLECT"]["name"]
    older_exe = materialise(dist, older, b"older")

    monkeypatch.setattr(
        "tools.spec_common.read_acervator_version", lambda _root: "2.0.0"
    )
    newer = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=QT)["COLLECT"]["name"]
    newer_exe = materialise(dist, newer, b"newer")

    assert older != newer, f"both versions claimed {older!r}"
    assert older_exe.read_bytes() == b"older", "the newer build overwrote the older one"
    assert newer_exe.read_bytes() == b"newer"


def test_a_rebuild_of_one_version_steps_past_the_build_already_there(
    tmp_path, monkeypatch
):
    """The troubleshooting case: rebuild without losing what is running."""
    dist = tmp_path / "dist"
    dist.mkdir()
    first = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=REACT)["COLLECT"]["name"]
    first_exe = materialise(dist, first, b"first")

    second = run_spec(WIN_SPEC, tmp_path, monkeypatch, variant=REACT)["COLLECT"]["name"]
    second_exe = materialise(dist, second, b"second")

    assert second != first, f"the rebuild claimed {first!r}, the folder in use"
    assert first_exe.read_bytes() == b"first"
    assert second_exe.read_bytes() == b"second"
