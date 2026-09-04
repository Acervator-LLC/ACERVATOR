"""``VersionSweep`` must name a version literal wherever one can shadow.

WHAT A FAILURE MEANS
====================
A ``*_is_named`` test red: the sweep has stopped seeing one shape of
restated version. A build, a window title or a boot image can then report
a number the resolved version does not carry, and the sweep still says
clean.

A ``*_is_left_alone`` test red: the sweep has widened onto a number that
is legitimately something else — a state record's schema lineage, a
macOS minimum, a report schema, or the resolver's own fallback. Findings
the operator must ignore are how a gate stops being read.

``test_a_file_no_list_names_is_swept`` red: subject discovery is gone and
a written list is back. That list is what made the sweep report clean by
construction.

TWO-SIDED
=========
Every ``is_named`` test is paired with the same tree carrying no literal,
so a sweep that reported everything would fail the ``is_left_alone`` set,
and a sweep that reported nothing would fail the ``is_named`` set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src._version import baked_path
from src.core.version_sweep import (
    VersionSweep,
    find_python_shadow_literals,
    find_script_shadow_literals,
)

BAKED = "9.9.9"


def slots(source: str) -> dict[str, str]:
    """Map every literal Python source restates to the slot holding it."""
    return {s.value: s.slot for s in find_python_shadow_literals(source)}


def script_slots(source: str) -> dict[str, str]:
    """Map every literal a script restates to the slot holding it."""
    return {s.value: s.slot for s in find_script_shadow_literals(source)}


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A miniature project whose version resolves from a baked stamp."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text(
        "from ._version import resolve_version\n", encoding="utf-8"
    )
    baked_path(tmp_path).write_text(f"{BAKED}\n", encoding="utf-8")
    return tmp_path


def sweep_findings(root: Path) -> list:
    """Run the version check over a tree and return what it scored."""
    sweep = VersionSweep(root=root)
    sweep.check_version_consistency()
    return sweep.result.findings


def plant(root: Path, rel: str, body: str) -> None:
    """Write one file into a tree, creating the directories it needs."""
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


# ── literals that must be named ──────────────────────────────────────────


def test_a_parameter_default_is_named() -> None:
    """A version parameter defaulting to a literal is a shadow."""
    found = slots('def surface(version: str = "0.0.0") -> str:\n    return version\n')
    assert found == {"0.0.0": "parameter default"}, found


def test_a_lookup_default_is_named() -> None:
    """``.get("version", literal)`` answers an absent key with a shadow."""
    found = slots('title = given.get("version", "0.0.0")\n')
    assert found == {"0.0.0": "lookup default"}, found


def test_an_except_import_fallback_is_named() -> None:
    """The literal in the except arm is the one that ships when import fails."""
    found = slots(
        "try:\n"
        "    from src import __version__\n"
        "except ImportError:\n"
        '    __version__ = "7.7.7"\n'
    )
    assert found == {"7.7.7": "except fallback"}, found


def test_an_option_default_is_named() -> None:
    """``add_argument("--version", default=...)`` stamps the literal."""
    found = slots('parser.add_argument("--version", default="3.7.0")\n')
    assert found == {"3.7.0": "option default"}, found


def test_a_windows_version_info_entry_is_named() -> None:
    """``FileVersion``/``ProductVersion`` are what the exe reports."""
    found = slots("info = {'FileVersion': '1.1.0.0', 'ProductVersion': '1.1.0'}\n")
    assert found == {
        "1.1.0.0": "mapping entry",
        "1.1.0": "mapping entry",
    }, found


def test_an_or_fallback_is_named() -> None:
    """A literal on the right of ``or`` ships whenever the left is empty."""
    found = slots('app_version = resolve() or "2.2.2"\n')
    assert found == {"2.2.2": "or fallback"}, found


def test_an_or_fallback_behind_a_version_attribute_is_named() -> None:
    """The version name can sit inside the expression, not on the target."""
    found = slots('title = fmt(cfg.app_version or "2.2.2")\n')
    assert found == {"2.2.2": "or fallback"}, found


def test_a_shell_script_assignment_is_named() -> None:
    """A deploy script writing the version down is a shadow."""
    found = script_slots('#!/bin/sh\nAPP_VERSION="4.4.4"\necho "$APP_VERSION"\n')
    assert found == {"4.4.4": "assignment"}, found


def test_a_powershell_assignment_is_named() -> None:
    """A build script writing the version down is a shadow."""
    found = script_slots('$versionStr = "4.4.4"\n')
    assert found == {"4.4.4": "assignment"}, found


def test_a_literal_survives_the_file_also_importing_the_version() -> None:
    """Importing the version does not clear a literal in the same file.

    The literal is usually the fallback, so an "does this file import the
    version?" check passes while the shadow stands.
    """
    found = slots(
        "from src import __version__\n\n"
        'def surface(version: str = "0.0.0") -> str:\n'
        "    return version or __version__\n"
    )
    assert found == {"0.0.0": "parameter default"}, found


# ── numbers that must be left alone ──────────────────────────────────────


def test_a_bare_version_mapping_key_is_left_alone() -> None:
    """A state record stamps its own schema lineage under ``version``."""
    assert slots('state = {"version": "1.9.5", "bots": {}}\n') == {}


def test_a_foreign_subject_version_key_is_left_alone() -> None:
    """``LSMinimumSystemVersion`` is the macOS a bundle needs."""
    assert slots("plist = {'LSMinimumSystemVersion': '12.0'}\n") == {}


def test_a_schema_constant_is_left_alone() -> None:
    """A name that does not say ``version`` is not a version."""
    assert slots('REPORT_SCHEMA = "1.0.0"\n') == {}


def test_a_frozen_content_marker_is_left_alone() -> None:
    """``*_FROZEN_AT`` records which release content was cut from."""
    assert slots('_CONTENT_VERSION_FROZEN_AT = "3.1.98"\n') == {}


def test_the_version_resolver_module_is_left_alone() -> None:
    """The module defining ``resolve_version`` states the fallback itself."""
    assert (
        slots(
            'UNTAGGED_RELEASE = "0.1.0"\n\n'
            "def resolve_version(root=None):\n"
            "    return UNTAGGED_RELEASE\n"
        )
        == {}
    )


def test_a_docstring_usage_example_is_left_alone() -> None:
    """A ``--version 3.7.0`` in prose stamps nothing at runtime."""
    assert slots('"""Run: generate_splash.py --version 3.7.0"""\n') == {}


def test_a_script_comment_is_left_alone() -> None:
    """A commented-out version in a script stamps nothing."""
    assert script_slots('# APP_VERSION="4.4.4"\nAPP_VERSION="$(resolve)"\n') == {}


# ── discovery, end to end ────────────────────────────────────────────────


def test_a_file_no_list_names_is_swept(tree: Path) -> None:
    """A new file carrying a literal is caught with no edit to the sweep."""
    plant(tree, "tools/freshly_added.py", 'APP_VERSION = "8.8.8"\n')

    findings = sweep_findings(tree)

    assert [(f.severity, Path(f.file).name) for f in findings] == [
        ("HIGH", "freshly_added.py")
    ], findings
    assert "8.8.8" in findings[0].description


def test_the_same_tree_without_the_literal_is_clean(tree: Path) -> None:
    """Positive control: the sweep scores nothing when nothing shadows."""
    plant(tree, "tools/freshly_added.py", "from src import __version__\n")

    assert sweep_findings(tree) == []


def test_a_spec_file_is_swept(tree: Path) -> None:
    """A PyInstaller spec is Python and must be read as Python."""
    plant(tree, "Plant_win.spec", "info = {'ProductVersion': '5.5.5'}\n")

    findings = sweep_findings(tree)

    assert [Path(f.file).name for f in findings] == ["Plant_win.spec"], findings


def test_a_deploy_script_is_swept(tree: Path) -> None:
    """A kiosk deploy script stamps the boot image and must be read."""
    plant(tree, "deploy/kiosk/install.sh", 'APP_VERSION="4.4.4"\n')

    findings = sweep_findings(tree)

    assert [Path(f.file).name for f in findings] == ["install.sh"], findings


def test_a_package_manifest_is_left_alone(tree: Path) -> None:
    """``desktop/package.json`` carries a version nothing reads."""
    plant(tree, "desktop/package.json", '{\n  "version": "0.0.0"\n}\n')

    assert sweep_findings(tree) == []


def test_a_test_tree_literal_is_left_alone(tree: Path) -> None:
    """A fixture's version reaches no surface that reports a version."""
    plant(tree, "tests/test_thing.py", 'EXPECTED_VERSION = "8.8.8"\n')

    assert sweep_findings(tree) == []


def test_an_unparsable_subject_is_recorded_not_scored_clean(tree: Path) -> None:
    """A file the sweep cannot parse is attributable, never silently dropped."""
    plant(tree, "tools/broken.py", 'APP_VERSION = "8.8.8"\ndef (\n')

    sweep = VersionSweep(root=tree)
    sweep.check_version_consistency()

    assert [Path(rel).name for rel, _ in sweep.skipped_files] == ["broken.py"]


def test_an_unresolvable_version_is_scored(tmp_path: Path) -> None:
    """No git tag and no baked stamp must score, not pass in silence."""
    findings = sweep_findings(tmp_path)

    assert [f.severity for f in findings] == ["HIGH"], findings
    assert "unresolvable" in findings[0].description


# ── documents ────────────────────────────────────────────────────────────


def test_a_doc_on_the_current_release_line_is_scored(tree: Path) -> None:
    """A stale reference is found on whatever line the project is on now."""
    plant(tree, "CHANGELOG.md", "Released 9.8.7 last week.\n")

    findings = sweep_findings(tree)

    assert [(f.severity, Path(f.file).name) for f in findings] == [
        ("MEDIUM", "CHANGELOG.md")
    ], findings
    assert "9.8.7" in findings[0].description


def test_a_doc_naming_the_resolved_version_is_left_alone(tree: Path) -> None:
    """The current release is not a stale reference to itself."""
    plant(tree, "CHANGELOG.md", f"Released {BAKED} today.\n")

    assert sweep_findings(tree) == []
