"""``VersionSweep`` must read and write text as UTF-8, not as the locale codec.

WHAT A FAILURE MEANS
====================
``test_get_version_reads_a_utf8_init_under_a_cp1252_locale`` red: an
unencoded text read is back on the version path. On a cp1252 default the
box-drawing characters in ``src/__init__.py`` raise ``UnicodeDecodeError``,
the sweep loses its canonical version, and ``check_version_consistency``
returns at its ``canonical == "unknown"`` guard without running one check
-- reporting nothing in language identical to a clean run. The version
itself now comes from ``src/_version.py``, so the fixture tree carries the
build-time stamp a bundle carries as well as the non-ASCII package file.

``test_check_version_consistency_still_checks_under_a_cp1252_locale``
red: the consistency check is dead. It found no mismatch in a tree built
to contain one.

``test_no_unencoded_text_io_in_version_sweep`` red: some text read or
write in the module dropped its ``encoding=`` argument. That call decodes
with whatever codec the machine's locale supplies.

``test_json_report_does_not_write_into_the_repo`` red: the sweep report
is landing in the source tree again.

``test_force_utf8_stdio_retags_a_cp1252_stream`` red: the CLI prints
U+2713 and box-drawing characters to a locale-encoded console, and the
sweep aborts on UnicodeEncodeError before writing any report.

TWO-SIDED
=========
Drop ``encoding="utf-8"`` from ``read_baked_version`` and the first two
tests fail. Point ``get_reports_dir`` back into the repo tree and the
destination test fails.
"""

from __future__ import annotations

import ast
import io
import json
import locale
import sys
from pathlib import Path

import pytest

from src._version import baked_path
from src.core import log_paths
from src.core.version_sweep import (
    ROOT,
    SweepResult,
    VersionSweep,
    _force_utf8_stdio,
)

MODULE = Path(__file__).resolve().parents[1] / "src" / "core" / "version_sweep.py"

TEXT_IO_CALLS = frozenset({"read_text", "write_text"})


@pytest.fixture
def cp1252_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the interpreter's default text encoding to cp1252.

    ``TextIOWrapper`` resolves ``encoding=None`` through
    ``locale.getencoding()``, so this reproduces a Windows default on any
    host, including a UTF-8 CI runner.
    """
    monkeypatch.setattr(locale, "getencoding", lambda: "cp1252")


@pytest.fixture
def utf8_tree(tmp_path: Path) -> Path:
    """A miniature bundle whose ``src/__init__.py`` holds non-ASCII text.

    The version comes from the build-time stamp, as it does in a real
    bundle. ``main.py`` restates 4.4.4 against a canonical 9.9.9, so a live
    consistency check must produce exactly one HIGH finding.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text(
        '"""┌─ box drawing ─┐"""\nfrom ._version import resolve_version\n',
        encoding="utf-8",
    )
    baked_path(tmp_path).write_text("9.9.9\n", encoding="utf-8")
    (tmp_path / "main.py").write_text('current_version = "4.4.4"\n', encoding="utf-8")
    return tmp_path


@pytest.mark.usefixtures("cp1252_locale")
def test_get_version_reads_a_utf8_init_under_a_cp1252_locale(utf8_tree: Path) -> None:
    """A tree holding non-ASCII text must still yield its version."""
    sweep = VersionSweep(root=utf8_tree)
    assert sweep.result.version == "9.9.9"


@pytest.mark.usefixtures("cp1252_locale")
def test_check_version_consistency_still_checks_under_a_cp1252_locale(
    utf8_tree: Path,
) -> None:
    """The check must see the 4.4.4 mismatch it was pointed at."""
    sweep = VersionSweep(root=utf8_tree)
    sweep.check_version_consistency()

    mismatches = [f for f in sweep.result.findings if "4.4.4" in f.description]
    assert len(mismatches) == 1, sweep.result.findings
    assert mismatches[0].severity == "HIGH"


def test_no_unencoded_text_io_in_version_sweep() -> None:
    """Every ``read_text``/``write_text`` in the module names its codec."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    offenders = [
        f"{MODULE.name}:{node.lineno} {node.func.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in TEXT_IO_CALLS
        and not any(kw.arg == "encoding" for kw in node.keywords)
    ]
    assert offenders == []


def test_json_report_default_destination_is_outside_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default report directory must not sit under the source tree.

    ``_LOG_ROOT`` is redirected so the assertion creates nothing under
    the operator's real ``~/.acervator_logs``.
    """
    monkeypatch.setattr(log_paths, "_LOG_ROOT", tmp_path)

    reports = log_paths.get_reports_dir()
    assert reports == tmp_path / "reports"
    assert ROOT not in reports.parents
    assert log_paths.layout_map()["reports"] == reports


def test_json_report_does_not_write_into_the_repo(tmp_path: Path) -> None:
    """An explicit destination must be honoured and no ``sadp/`` created."""
    sweep = VersionSweep(root=tmp_path)
    out = sweep.save_json_report(
        SweepResult(version="9.9.9", timestamp="2026-01-01 00:00:00"),
        reports_dir=tmp_path / "reports",
    )

    assert out.parent == tmp_path / "reports"
    assert json.loads(out.read_text(encoding="utf-8"))["version"] == "9.9.9"
    assert not (ROOT / "sadp").exists()


def test_force_utf8_stdio_retags_a_cp1252_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cp1252 stdout must be UTF-8 after the call, and U+2713 printable."""
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", buf)

    _force_utf8_stdio()

    assert buf.encoding == "utf-8"
    buf.write("✓")


def test_force_utf8_stdio_tolerates_a_stream_without_reconfigure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A capture object with no ``reconfigure`` must not raise."""
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())

    _force_utf8_stdio()
