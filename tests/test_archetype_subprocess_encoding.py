"""Archetype subprocess reads must not depend on the machine's locale.

THE DEFECT (found 2026-08-07)
`docs_archetype._run_proselint` called
``subprocess.run(..., capture_output=True, text=True)``. With `text=True`
and no explicit encoding, Python decodes using the locale codec --
cp1252 on this Windows machine. proselint's curly-quote message is
literally:

    Use curly quotes "", not straight quotes ""

Those curly characters are not decodable as cp1252. The read raised
``UnicodeDecodeError``, `proc.stdout` came back None, and the whole
prose layer silently produced ZERO findings. It had been passing every
document it checked.

The defect message that broke the decoder was the very defect the layer
was supposed to report.

WHY A STRUCTURAL TEST AND NOT JUST THE GROUND-TRUTH ONES
`test_docs_archetype.py`'s D4/D5 recall tests DID catch this -- that is
the positive control working exactly as intended. But they fail for many
possible reasons and would not tell the next reader that the cause was
an encoding default. This pins the actual root cause, across all three
archetypes at once, so the class cannot come back through a tool that
happens to emit a non-cp1252 byte.

`check_release_readiness.py:91` already carried this fix. It was never
propagated to the archetypes, which is precisely how a fixed bug
reappears somewhere else.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HARNESS = REPO_ROOT / "dev_harness" / "harness"
ARCHETYPES = ["coding_archetype.py", "docs_archetype.py", "gui_archetype.py"]


def _subprocess_run_calls(path: Path):
    """Every subprocess.run(...) call node in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "attr", None) or getattr(fn, "id", None)
        if name != "run":
            continue
        # subprocess.run(...) specifically
        owner = getattr(getattr(fn, "value", None), "id", None)
        if owner in ("subprocess", None):
            out.append(node)
    return out


class TestTheInstrumentWorks:
    @pytest.mark.parametrize("mod", ARCHETYPES)
    def test_each_archetype_shells_out_at_all(self, mod):
        """POSITIVE CONTROL. If an archetype stopped invoking anything,
        the assertions below would pass vacuously."""
        calls = _subprocess_run_calls(HARNESS / mod)
        assert calls, f"{mod} makes no subprocess.run calls to check"


class TestNoLocaleDependentDecoding:
    @pytest.mark.parametrize("mod", ARCHETYPES)
    def test_every_text_mode_call_pins_utf8(self, mod):
        """A tool that emits one non-cp1252 byte must not be able to
        blank an entire review layer."""
        path = HARNESS / mod
        offenders = []
        for call in _subprocess_run_calls(path):
            kw = {k.arg: k for k in call.keywords if k.arg}
            text_mode = "text" in kw or "universal_newlines" in kw
            if not text_mode:
                continue  # bytes mode decodes nothing; not vulnerable
            if "encoding" not in kw:
                offenders.append(call.lineno)
        assert not offenders, (
            f"{mod}: subprocess.run at line(s) {offenders} decode with the "
            f"locale codec. On Windows that is cp1252, and any non-cp1252 "
            f"byte in tool output silently blanks that layer."
        )

    @pytest.mark.parametrize("mod", ARCHETYPES)
    def test_decoding_never_raises_on_undecodable_bytes(self, mod):
        """utf-8 alone is not enough: a tool emitting genuinely invalid
        bytes would still raise. errors= must be set."""
        path = HARNESS / mod
        offenders = []
        for call in _subprocess_run_calls(path):
            kw = {k.arg: k for k in call.keywords if k.arg}
            if ("text" in kw or "universal_newlines" in kw) and "errors" not in kw:
                offenders.append(call.lineno)
        assert not offenders, (
            f"{mod}: subprocess.run at line(s) {offenders} would raise "
            f"UnicodeDecodeError on undecodable output instead of "
            f"degrading. stdout then comes back None."
        )


class TestTheRealisticPayloadDecodes:
    def test_the_curly_quote_message_survives_a_utf8_read(self):
        """The exact message that broke it. Decoded as utf-8 this is
        fine; as cp1252 it raises."""
        msg = 'Use curly quotes “”, not straight quotes "".'
        raw = msg.encode("utf-8")
        assert raw.decode("utf-8", errors="replace") == msg
        with pytest.raises(UnicodeDecodeError):
            raw.decode("cp1252")

    def test_the_prose_layer_returns_findings_on_the_bad_fixture(self):
        """End-to-end: the layer that was silently empty now reports.
        This is the assertion that would have caught the original."""
        from dev_harness.harness.docs_archetype import DocsArchetype

        fixture = (
            REPO_ROOT
            / "docs"
            / "audits"
            / "2026-07-24_gui_docs_archetypes"
            / "docs_fixtures"
            / "known_bad.md"
        )
        findings, status = DocsArchetype()._run_proselint([fixture])
        assert status == "ok"
        assert len(findings) >= 5, (
            f"prose layer returned {len(findings)} findings on a fixture "
            f"authored to be full of defects"
        )
