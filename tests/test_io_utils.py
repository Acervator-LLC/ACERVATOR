"""Contract tests for core.io_utils.atomic_write_json.

The helper is the single implementation of the tmp-then-rename atomic
JSON write that every persistence path routes through. These tests pin
its observable contract: the bytes it produces for each formatting mode
the call sites rely on, that a reader never sees a partial file, and that
a failed write leaves the target untouched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.io_utils import atomic_write_json  # noqa: E402


def test_roundtrips_the_payload(tmp_path):
    dest = tmp_path / "state.json"
    payload = {"bots": {"a": 1}, "n": [1, 2, 3]}
    atomic_write_json(dest, payload)
    assert json.loads(dest.read_text(encoding="utf-8")) == payload


def test_returns_the_destination_path(tmp_path):
    dest = tmp_path / "state.json"
    assert atomic_write_json(dest, {"x": 1}) == dest


def test_creates_missing_parent_directories(tmp_path):
    dest = tmp_path / "deep" / "nested" / "state.json"
    atomic_write_json(dest, {"x": 1})
    assert json.loads(dest.read_text(encoding="utf-8")) == {"x": 1}


def test_default_indent_is_two_spaces(tmp_path):
    dest = tmp_path / "state.json"
    atomic_write_json(dest, {"a": 1, "b": 2})
    assert dest.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}'


def test_compact_mode_matches_json_dumps(tmp_path):
    dest = tmp_path / "state.json"
    payload = {"a": 1, "b": [2, 3]}
    atomic_write_json(dest, payload, indent=None, separators=(",", ":"))
    assert dest.read_text(encoding="utf-8") == json.dumps(
        payload, separators=(",", ":")
    )


def test_sort_keys_orders_output(tmp_path):
    dest = tmp_path / "state.json"
    atomic_write_json(dest, {"b": 1, "a": 2}, indent=2, sort_keys=True)
    assert dest.read_text(encoding="utf-8") == '{\n  "a": 2,\n  "b": 1\n}'


def test_default_callable_serializes_otherwise_unencodable_values(tmp_path):
    dest = tmp_path / "state.json"

    class Weird:
        def __str__(self):
            return "weird-value"

    atomic_write_json(dest, {"k": Weird()}, default=str)
    assert json.loads(dest.read_text(encoding="utf-8")) == {"k": "weird-value"}


def test_without_a_default_unencodable_values_raise(tmp_path):
    dest = tmp_path / "state.json"

    class Weird:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(dest, {"k": Weird()}, default=None)


def test_a_failed_write_preserves_the_previous_file(tmp_path):
    dest = tmp_path / "state.json"
    atomic_write_json(dest, {"good": 1})
    before = dest.read_text(encoding="utf-8")

    class Weird:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(dest, {"bad": Weird()}, default=None)

    assert dest.read_text(encoding="utf-8") == before


def test_no_staging_file_remains_after_success(tmp_path):
    dest = tmp_path / "state.json"
    atomic_write_json(dest, {"x": 1})
    assert [p.name for p in tmp_path.iterdir() if p != dest] == []


def test_no_staging_file_remains_after_failure(tmp_path):
    dest = tmp_path / "state.json"

    class Weird:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(dest, {"bad": Weird()}, default=None)

    assert list(tmp_path.iterdir()) == []


def test_each_call_stages_through_a_distinct_temp_file(tmp_path, monkeypatch):
    """Two writers targeting one path must never share a staging file —
    the property that makes the bot_state.json double-writer safe. Spy on
    the temp names the helper requests and assert they differ."""
    import tempfile as _tempfile

    seen = []
    real_mkstemp = _tempfile.mkstemp

    def spy_mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        seen.append(name)
        return fd, name

    monkeypatch.setattr("src.core.io_utils.tempfile.mkstemp", spy_mkstemp)

    dest = tmp_path / "bot_state.json"
    atomic_write_json(dest, {"writer": 1})
    atomic_write_json(dest, {"writer": 2})

    assert len(seen) == 2
    assert seen[0] != seen[1], f"both writes staged through {seen[0]}"
