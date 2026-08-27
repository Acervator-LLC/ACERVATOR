"""``VersionSweep.save_pdf_report`` must build a real PDF.

WHY THIS TEST EXISTS
====================
``src/core/version_sweep.py`` has no caller anywhere in the tree, so
nothing else runs its code. That makes it easy to break in silence.

The Coding Archetype reported four ``list-item`` errors in
``save_pdf_report``. mypy read the element type of two lists from their
first item:

* ``story`` began with two ``Paragraph`` objects, so mypy called it
  ``list[Paragraph]``, and the later ``story.append(table)`` and the
  final ``SimpleDocTemplate.build(story)`` both became type errors.
* ``rows`` began with a header row of plain strings, so mypy called it
  ``list[list[str]]``, and every data row of ``Paragraph`` objects
  became a type error.

The repair states the real element types with two annotations, and it
imports ``Flowable`` from ``reportlab.platypus`` to name the first one.
That import is INSIDE the function's ``try``/``except ImportError``
block, so a missing or renamed ``Flowable`` would not raise. It would
make ``save_pdf_report`` return ``None``, and the method would stop
producing reports with no message at all. This test is what stands
between that outcome and silence.

TWO-SIDED
=========
Remove ``Flowable`` from the ``reportlab.platypus`` import line and
``test_save_pdf_report_writes_a_readable_pdf`` fails on the ``None``
return.
"""

from __future__ import annotations

import time

import pytest

from src.core.version_sweep import Finding, Severity, SweepResult, VersionSweep


def _result() -> SweepResult:
    """One SweepResult that holds a finding of every severity."""
    return SweepResult(
        version="9.9.9",
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        findings=[
            Finding(
                Severity.CRITICAL,
                "SECURITY",
                "a/very/long/path/that/" "runs/past/forty/characters/mod.py",
                11,
                "critical row",
            ),
            Finding(Severity.HIGH, "QUALITY", "b.py", 22, "high row"),
            Finding(Severity.MEDIUM, "CONSISTENCY", "c.py", 0, "medium row"),
            Finding(Severity.LOW, "HYGIENE", "d.py", 44, "low row"),
            Finding(Severity.INFO, "DEPENDENCY", "e.py", 55, "info row"),
        ],
        files_scanned=3,
        lines_scanned=4567,
        elapsed_sec=1.25,
    )


def test_save_pdf_report_writes_a_readable_pdf(tmp_path):
    """The method returns a path, and that path holds a real PDF."""
    reportlab = pytest.importorskip("reportlab")
    assert reportlab is not None

    out = VersionSweep().save_pdf_report(_result(), reports_dir=tmp_path / "reports")

    assert out is not None, (
        "save_pdf_report returned None. Its reportlab import block failed, "
        "so no report was written and nothing said so."
    )
    assert out.exists()
    data = out.read_bytes()
    assert data.startswith(b"%PDF-"), data[:16]
    assert data.rstrip().endswith(b"%%EOF")
    assert len(data) > 1500, len(data)
    assert out.parent == tmp_path / "reports"


def test_save_pdf_report_covers_every_severity_section(tmp_path):
    """A severity with no finding draws no section; one finding draws one.

    This walks the ``sev_order`` loop that builds ``rows``, which is the
    list the archetype reported on.
    """
    pytest.importorskip("reportlab")

    full = VersionSweep().save_pdf_report(_result(), reports_dir=tmp_path / "reports")
    assert full is not None
    big = full.stat().st_size

    empty_result = SweepResult(version="9.9.8", timestamp="t", findings=[])
    empty = VersionSweep().save_pdf_report(
        empty_result, reports_dir=tmp_path / "reports"
    )
    assert empty is not None
    small = empty.stat().st_size

    assert small < big, (
        f"a report with no findings ({small} bytes) must be smaller than a "
        f"report with five ({big} bytes); the findings loop drew nothing"
    )


def test_unused_stdlib_imports_stay_out(tmp_path):
    """``hashlib`` and ``importlib`` were imported and never called.

    They are named in this module only inside the SECRET/QUALITY regex
    string literals. Deleting the imports cleared two vulture rows. This
    test fails if either import comes back without a use.
    """
    del tmp_path
    import src.core.version_sweep as vs

    for name in ("hashlib", "importlib"):
        assert not hasattr(vs, name), (
            f"src/core/version_sweep.py imports {name} again. Either call "
            f"it or drop the import; an unused import is a vulture finding."
        )
