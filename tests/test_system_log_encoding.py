"""The system log must not drop records containing non-cp1252 glyphs.

HOW THIS WAS FOUND
Not by reading code. While trying to read the operator's system log to
diagnose an unrelated Indicator-Voting-Panel question on 2026-08-07, the
log turned out to contain almost nothing:

    console_20260807_081802.log
      15,616 lines
         825 "--- Logging error ---" blocks
           3 surviving log records

Every block was:

    UnicodeEncodeError: 'charmap' codec can't encode character
    '\\u2192' in position 72

`logging_engine.py:348` built the ONLY logging handler in the codebase
with `logging.FileHandler(path)` and no encoding, so it opened with the
locale codec -- cp1252 on Windows. This codebase logs arrows, em-dashes
and multiplication signs freely (`trade.filled -> trade.log`,
`take x (ref - fill)`), and Python's logging swallows the encode failure
into a traceback and DROPS the record.

The instrument the operator relies on to diagnose the platform had been
reporting almost nothing, and nothing said so.

Same class as the archetype subprocess defect fixed in 3.24.51: that one
decoded tool output with the locale codec, this one encodes log output
with it. Reading and writing ends of one mistake.
"""

from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SRC = REPO_ROOT / "src"

# The exact character from the operator's log, plus the other glyphs
# this codebase emits routinely.
ARROW = "→"  # → , as in "trade.filled → trade.log"
GLYPHS = "→ — × ≥"  # → — × ≥


def _handler_calls(path: Path):
    """Every logging.*Handler(...) construction in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", "") or getattr(node.func, "id", "")
            if name.endswith("FileHandler"):
                out.append(node)
    return out


class TestTheDefectIsReal:
    """POSITIVE CONTROL for the whole file. If a bare FileHandler could
    already write an arrow on this machine, there was nothing to fix and
    every assertion below is theatre."""

    def test_a_bare_file_handler_cannot_write_the_arrow(self, tmp_path):
        target = tmp_path / "bare.log"
        handler = logging.FileHandler(target)
        if (handler.stream.encoding or "").lower().replace("-", "") == "utf8":
            handler.close()
            pytest.skip(
                "locale codec is already utf-8 on this machine; "
                "the defect is Windows/cp1252-specific"
            )
        log = logging.getLogger("acervator.test.bare")
        log.propagate = False
        log.addHandler(handler)
        try:
            log.error("LogManager attached to bus: trade.filled %s trade.log", ARROW)
        finally:
            log.removeHandler(handler)
            handler.close()
        # The record is LOST -- not raised, not written. Silently gone.
        assert ARROW not in target.read_text(encoding="utf-8", errors="replace")

    def test_a_utf8_handler_writes_it(self, tmp_path):
        target = tmp_path / "utf8.log"
        handler = logging.FileHandler(target, encoding="utf-8", errors="replace")
        log = logging.getLogger("acervator.test.utf8")
        log.propagate = False
        log.addHandler(handler)
        try:
            log.error("glyphs %s", GLYPHS)
        finally:
            log.removeHandler(handler)
            handler.close()
        written = target.read_text(encoding="utf-8")
        for ch in GLYPHS.split():
            assert ch in written, f"{ch!r} was dropped from the log"


class TestEveryHandlerInSrcPinsUtf8:
    def test_the_codebase_has_a_handler_to_check(self):
        """POSITIVE CONTROL: if handler construction moved, the sweep
        below would pass by finding nothing."""
        found = [p for p in SRC.rglob("*.py") if _handler_calls(p)]
        assert found, "no FileHandler construction found anywhere in src/"

    def test_no_file_handler_relies_on_the_locale_codec(self):
        offenders = []
        for p in sorted(SRC.rglob("*.py")):
            for call in _handler_calls(p):
                kw = {k.arg for k in call.keywords if k.arg}
                if "encoding" not in kw:
                    offenders.append(f"{p.relative_to(REPO_ROOT)}:{call.lineno}")
        assert not offenders, (
            "FileHandler without encoding= opens with the locale codec; on "
            "Windows that is cp1252 and any arrow/em-dash in a log message "
            f"silently DROPS the record: {offenders}"
        )

    def test_no_file_handler_can_raise_on_a_bad_byte(self):
        """utf-8 alone is not enough -- errors= must degrade rather than
        cost the record."""
        offenders = []
        for p in sorted(SRC.rglob("*.py")):
            for call in _handler_calls(p):
                kw = {k.arg for k in call.keywords if k.arg}
                if "encoding" in kw and "errors" not in kw:
                    offenders.append(f"{p.relative_to(REPO_ROOT)}:{call.lineno}")
        assert (
            not offenders
        ), f"FileHandler without errors= can still lose a record: {offenders}"


class TestTheRealHandler:
    def test_logging_engine_pins_utf8_at_the_construction_site(self):
        """Named explicitly, because this is THE handler -- the only one
        in src/, and the one that produced 825 dropped records."""
        path = SRC / "core" / "logging_engine.py"
        calls = _handler_calls(path)
        assert calls, "logging_engine no longer builds the system handler"
        for call in calls:
            kw = {k.arg: k.value for k in call.keywords if k.arg}
            assert "encoding" in kw, "system.log handler lost its encoding"
            assert ast.literal_eval(kw["encoding"]) == "utf-8"
            assert "errors" in kw, "system.log handler lost its errors="
