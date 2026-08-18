"""C12: read back everything you write.

THE DEFECT
`AppSettings` had 14 fields. The Settings dialog wrote 16 keys. Five of
them were not fields at all:

    font_family, font_size, heading_font_size, log_font_size, ai_monitor

`SettingsManager.set()` raises `KeyError: Unknown setting: <key>` for a
key that is not a dataclass field. `_save()` caught it, printed to
stderr — which the operator never sees — and closed the dialog. The
status line then read "Settings saved (N groups)." at SUCCESS level
regardless, so a save that discarded five values looked identical to a
clean one; only the count differed, and nobody knows what the count
should be.

Confirmed empirically before the fix, not inferred from source:

    set('theme')         -> OK
    set('font_size')     -> KeyError: Unknown setting: font_size
    set('ai_monitor')    -> KeyError: Unknown setting: ai_monitor
    set('log_font_size') -> KeyError: Unknown setting: log_font_size

So four font choices and the entire AI Monitor configuration were
discarded on every single save, invisibly, since those tabs shipped.

The class docstring states the invariant this violated: "Every field
maps to a UI control in the Settings menu and is persisted to disk."
It held in one direction only.

NOTHING HERE CONSTRUCTS A SettingsManager. Its default config_dir is
`Path.home() / ".acervator"` — the operator's live tree — and a probe
that constructs one writes there for real. Field inspection and AST are
sufficient, and cannot touch anything.
"""
from __future__ import annotations

import ast
import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.settings import AppSettings  # noqa: E402

DIALOG = REPO_ROOT / "src" / "gui" / "settings_dialog.py"


def _keys_the_dialog_writes() -> set[str]:
    """Every settings key `_save()` attempts to persist.

    TWO sources, and missing the second is a trap worth naming: the
    dialog writes three keys as literals (`self._sm.set("ai_monitor",
    ...)`) but the other thirteen through a loop —

        for key, getter in pairs.items():
            self._sm.set(key, getter())

    — where the argument is a VARIABLE. A walk that only collects
    literal call arguments finds 3 of 16 and the invariant test then
    passes while checking almost nothing. The positive control below
    exists because that is exactly what the first version of this
    extractor did.

    AST, not grep: the receiver and method are both matched, so a
    `.set()` on some other object cannot inflate the set.
    """
    tree = ast.parse(DIALOG.read_text(encoding="utf-8"))
    out: set[str] = set()

    # 1. literal-argument calls: self._sm.set("key", ...)
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "set"):
            continue
        recv = n.func.value
        if not (isinstance(recv, ast.Attribute) and recv.attr == "_sm"):
            continue
        if n.args and isinstance(n.args[0], ast.Constant) \
                and isinstance(n.args[0].value, str):
            out.add(n.args[0].value)

    # 2. the `pairs = {...}` dict driving the loop
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pairs"
                   for t in n.targets):
            continue
        if isinstance(n.value, ast.Dict):
            for k in n.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    out.add(k.value)
    return out


def _fields() -> set[str]:
    return {f.name for f in dataclasses.fields(AppSettings)}


class TestEveryWrittenKeyIsAField:
    def test_the_extractor_finds_the_dialog_keys(self):
        """Positive control. If the AST walk silently matched nothing,
        the invariant test below would pass vacuously and the whole
        file would be decorative."""
        keys = _keys_the_dialog_writes()
        assert len(keys) >= 14, f"extractor found only {len(keys)}: {keys}"
        assert "theme" in keys and "ai_monitor" in keys

    def test_no_key_is_written_that_cannot_be_stored(self):
        """THE invariant. set() raises KeyError for a non-field, so any
        key here that is not an AppSettings field is discarded on every
        save."""
        orphans = sorted(_keys_the_dialog_writes() - _fields())
        assert not orphans, (
            f"the Settings dialog writes {len(orphans)} key(s) that are "
            f"not AppSettings fields: {orphans}. SettingsManager.set() "
            f"raises KeyError for each, so these are silently discarded "
            f"on every save.")

    @pytest.mark.parametrize("key", [
        "font_family", "font_size", "heading_font_size",
        "log_font_size", "ai_monitor",
    ])
    def test_each_previously_discarded_key_now_exists(self, key):
        assert key in _fields()


class TestDefaultsMatchTheDialogWidgets:
    """An unsaved install and a saved one must agree, or the UI jumps
    the first time the operator presses Save."""

    @pytest.mark.parametrize("key,expected", [
        ("font_family", "Segoe UI"),   # settings_dialog :520
        ("font_size", 11),             # :526
        ("heading_font_size", 14),     # :533
        ("log_font_size", 10),         # :539
    ])
    def test_font_default(self, key, expected):
        assert getattr(AppSettings(), key) == expected

    def test_ai_monitor_default_shape(self):
        """The dialog reads seven sub-keys off this dict; a default
        missing one means a fresh install reads None into a widget."""
        ai = AppSettings().ai_monitor
        assert isinstance(ai, dict)
        assert set(ai) == {
            "api_key", "interval_hours", "connect_phrase",
            "confirm_phrase", "enabled", "auto_handshake", "log_feedback"}
        assert ai["interval_hours"] == 4.0
        assert ai["enabled"] is False


class TestPartialSaveIsNotReportedAsSuccess:
    """Adding the fields fixes today's five. The reporting fix is what
    stops the NEXT orphan key from being invisible."""

    def test_save_collects_failures(self):
        src = DIALOG.read_text(encoding="utf-8")
        assert "failed: list[str] = []" in src
        assert src.count("failed.append(") >= 4, (
            "each save site must record its failure, or a partial save "
            "is under-reported")

    def test_success_message_is_conditional(self):
        src = DIALOG.read_text(encoding="utf-8")
        assert "PARTIALLY saved" in src, (
            "a save that dropped keys must not log at success level")

    def test_the_dialog_still_always_closes(self):
        """The 'ALWAYS close' guarantee is load-bearing and predates
        this cascade. A warning box must not be able to strand the
        dialog open."""
        tree = ast.parse(DIALOG.read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_save")
        accepts = [n for n in ast.walk(fn)
                   if isinstance(n, ast.Call)
                   and getattr(n.func, "attr", "") == "accept"]
        assert accepts, "_save no longer calls accept()"
        msgboxes = [n.lineno for n in ast.walk(fn)
                    if isinstance(n, ast.Call)
                    and getattr(n.func, "attr", "") == "warning"
                    and getattr(getattr(n.func, "value", None), "id", "")
                    == "QMessageBox"]
        for mb in msgboxes:
            assert mb < max(a.lineno for a in accepts), (
                "the partial-save warning must precede accept(), and "
                "accept() must remain unconditional")
