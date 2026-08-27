"""Behaviour pins for the ten sites now served by src/core/io_utils.py.

Each site used to carry its own temp-file-then-rename idiom. This module
pins what each one writes, and what the shared helper guarantees.

What each group would mean if it went red
-----------------------------------------
equivalence   A migrated site's bytes moved away from what its own old
              idiom produced. The only differences this suite accepts are
              the two declared here: text-mode CRLF translation is gone,
              and capital_reservation now names its encoding.
kwargs        A site stopped passing its own json.dumps arguments, so its
              file changed shape (indent, sort_keys, separators, default).
atomicity     A failure part-way through reached the destination. The
              destination is bot_state.json on the live path.
fsync         The staged file is renamed before its contents are on the
              platter. A power loss then promotes an empty or truncated
              file.
collision     Two writers of one destination share a staging path again.
              StateManager and bot_visualizer both staged bot_state.json
              through bot_state.tmp before this change.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core import feature_telemetry as FT
from src.core import instance_guard as IG
from src.core import io_utils as IO
from src.core import privacy_mask_registry as PMR
from src.core import state_manager as SM
from src.gui import indicator_panel as IP
from src.simulator.fleet import simulator_bot_state as SBS
from src.trading import capital_reservation as CR
from src.trading.stone_tablets import storage as ST

# ------------------------------------------------------------------ #
# The old idioms, reproduced verbatim. Each writes and returns bytes. #
# ------------------------------------------------------------------ #


def _old_open_w_utf8(tmp: Path, payload, **dump_kwargs) -> bytes:
    """state_manager.py: open(tmp, "w", encoding="utf-8") + json.dump."""
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, **dump_kwargs)
    return tmp.read_bytes()


def _old_write_text_utf8(tmp: Path, payload, **dump_kwargs) -> bytes:
    """privacy_mask_registry, feature_telemetry, instance_guard,
    simulator_bot_state, bot_visualizer, shared_testnet."""
    tmp.write_text(json.dumps(payload, **dump_kwargs), encoding="utf-8")
    return tmp.read_bytes()


def _old_write_text_no_encoding(tmp: Path, payload, **dump_kwargs) -> bytes:
    """capital_reservation.py: no encoding= at all, so the locale's."""
    tmp.write_text(json.dumps(payload, **dump_kwargs))
    return tmp.read_bytes()


def _old_open_w_newline_lf(tmp: Path, payload, **dump_kwargs) -> bytes:
    """indicator_panel.py: text mode, utf-8, newline pinned to LF."""
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, **dump_kwargs)
    return tmp.read_bytes()


def _old_fdopen_w_utf8(tmp_dir: Path, text: str) -> bytes:
    """stone_tablets/storage.py: mkstemp + os.fdopen(fd, "w", utf-8)."""
    import tempfile

    fd, name = tempfile.mkstemp(dir=str(tmp_dir), prefix=".tmp_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return Path(name).read_bytes()


def _crlf_to_lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


# ------------------------------------------------------------------ #
# Recorder: wraps a module's helper name, delegates, keeps the call.  #
# ------------------------------------------------------------------ #


class _Recorder:
    """Captures every (path, payload, kwargs) a site hands the helper."""

    def __init__(self, real):
        self._real = real
        self.calls: list[tuple[Path, object, dict]] = []

    def __call__(self, path, payload, **kwargs):
        self.calls.append((Path(path), payload, dict(kwargs)))
        return self._real(path, payload, **kwargs)

    @property
    def only(self) -> tuple[Path, object, dict]:
        assert len(self.calls) == 1, f"expected 1 helper call, got {len(self.calls)}"
        return self.calls[0]


def _install(monkeypatch, module, name: str) -> _Recorder:
    rec = _Recorder(getattr(module, name))
    monkeypatch.setattr(module, name, rec)
    return rec


def _dump_kwargs(kwargs: dict) -> dict:
    """The subset of a helper call that reaches json.dumps."""
    return {
        k: v
        for k, v in kwargs.items()
        if k in {"indent", "sort_keys", "default", "separators", "ensure_ascii"}
    }


# ------------------------------------------------------------------ #
# Realistic payloads                                                  #
# ------------------------------------------------------------------ #


def _bot_record(bot_id: str) -> dict:
    return {
        "bot_id": bot_id,
        "config": {"symbol": "BTC/USD", "dollar_target": 250.0, "exchange": "coinbase"},
        "state": "running",
        "stats": {"cycles": 41, "accumulated": 0.03274119},
        "scrumming_state": {
            "main_lots": [
                {"qty": 0.001, "price": 61234.5, "at": 1756000000.0 + i}
                for i in range(8)
            ],
            "fold_tranches": [{"qty": 0.0004, "trigger": 63000.0}],
        },
    }


# ================================================================== #
# equivalence + kwargs, one test per site                            #
# ================================================================== #


def test_state_manager_save_state_bytes(tmp_path, monkeypatch):
    """Red: bot_state.json's bytes moved off the old save_state idiom."""
    rec = _install(monkeypatch, SM, "atomic_write_json")
    mgr = SM.StateManager(config_dir=tmp_path)
    mgr.save_state([_bot_record("bot-a"), _bot_record("bot-b")])

    path, payload, kwargs = rec.only
    assert _dump_kwargs(kwargs) == {"indent": 2, "default": str}
    old = _old_open_w_utf8(tmp_path / "old.bytes", payload, indent=2, default=str)
    new = path.read_bytes()
    assert _crlf_to_lf(old) == new
    assert json.loads(old) == json.loads(new)


def test_state_manager_delete_bot_bytes(tmp_path, monkeypatch):
    """Red: delete_bot's rewrite of bot_state.json changed shape."""
    mgr = SM.StateManager(config_dir=tmp_path)
    mgr.save_state([_bot_record("bot-a"), _bot_record("bot-b")])

    rec = _install(monkeypatch, SM, "atomic_write_json")
    assert mgr.delete_bot("bot-a") is True

    path, payload, kwargs = rec.only
    assert _dump_kwargs(kwargs) == {"indent": 2, "default": str}
    old = _old_open_w_utf8(tmp_path / "old.bytes", payload, indent=2, default=str)
    assert _crlf_to_lf(old) == path.read_bytes()


def test_privacy_mask_registry_bytes(tmp_path, monkeypatch):
    """Red: settings.json's privacy_mask namespace changed shape."""
    rec = _install(monkeypatch, PMR, "atomic_write_json")
    reg = PMR.PrivacyMaskRegistry(
        settings_path=tmp_path / "settings.json", autosave=False
    )
    reg.set_masked(sorted(PMR.ALL_FIELD_IDS)[0], True)
    reg._persist_unlocked()

    path, payload, kwargs = rec.only
    assert _dump_kwargs(kwargs) == {"indent": 2, "sort_keys": True}
    old = _old_write_text_utf8(
        tmp_path / "old.bytes", payload, indent=2, sort_keys=True
    )
    assert _crlf_to_lf(old) == path.read_bytes()


def test_feature_telemetry_bytes(tmp_path, monkeypatch):
    """Red: the telemetry file stopped being compact JSON."""
    rec = _install(monkeypatch, FT, "atomic_write_json")
    tel = FT.FeatureTelemetry(path=tmp_path / "feature_telemetry.json", autoload=False)
    tel.declare("gui.fold_panel")
    assert tel.save() is True

    path, payload, kwargs = rec.only
    assert _dump_kwargs(kwargs) == {"separators": (",", ":")}
    old = _old_write_text_utf8(tmp_path / "old.bytes", payload, separators=(",", ":"))
    assert old == path.read_bytes()
    assert b"\r" not in old


def test_instance_guard_claim_bytes(tmp_path, monkeypatch):
    """Red: the instance claim changed shape; an unreadable claim
    refuses the operator's own fleet on the next launch."""
    rec = _install(monkeypatch, IG, "atomic_write_json")
    identity = IG.MachineIdentity(
        fingerprint="f" * 16,
        host="kiosk",
        os_user="operator",
        platform="Windows-11",
        strength="strong",
        source="uuid",
    )
    written = IG.write_claim(tmp_path, identity, app_version="3.25.8")

    path, payload, kwargs = rec.only
    assert path == written == tmp_path / IG.CLAIM_FILENAME
    assert _dump_kwargs(kwargs) == {"indent": 2}
    old = _old_write_text_utf8(tmp_path / "old.bytes", payload, indent=2)
    assert _crlf_to_lf(old) == path.read_bytes()


def test_simulator_bot_state_bytes(tmp_path, monkeypatch):
    """Red: simulator_bot_state.json changed shape. default=repr, not
    str: a sim state carrying a non-serialisable value must render the
    same way it did."""
    rec = _install(monkeypatch, SBS, "atomic_write_json")
    state = {"bot_count": 2, "bots": {"sim-a": _bot_record("sim-a")}, "obj": object()}
    SBS.save_sim_state(state, tmp_path / "simulator_bot_state.json")

    path, payload, kwargs = rec.only
    assert _dump_kwargs(kwargs) == {"indent": 2, "default": repr}
    old = _old_write_text_utf8(tmp_path / "old.bytes", payload, indent=2, default=repr)
    assert _crlf_to_lf(old) == path.read_bytes()


def test_capital_reservation_bytes(tmp_path, monkeypatch):
    """Red: reservation_state.json changed shape, or its serialised text
    stopped being ASCII — at which point the old locale write and the new
    utf-8 write would no longer agree."""
    rec = _install(monkeypatch, CR, "atomic_write_json")
    reg = CR.CapitalReservationRegistry(state_path=tmp_path / "reservation.json")
    reg._save()

    path, payload, kwargs = rec.only
    assert _dump_kwargs(kwargs) == {"indent": 2}
    old = _old_write_text_no_encoding(tmp_path / "old.bytes", payload, indent=2)
    assert _crlf_to_lf(old) == path.read_bytes()

    text = json.dumps(payload, indent=2)
    assert text.isascii()
    assert text.encode("cp1252") == text.encode("utf-8")


def test_indicator_panel_snapshot_bytes(tmp_path, monkeypatch):
    """Red: a TA snapshot changed shape and the panel reads a different
    document after a restart."""
    rec = _install(monkeypatch, IP, "atomic_write_json")
    dest = IP.save_ta_snapshot(
        "bot-a",
        "BTC/USD",
        {"5m": {"rsi": 61.2, "direction": "up"}},
        state_dir=tmp_path,
        taken_at=1756000000.0,
    )
    assert dest is not None

    path, payload, kwargs = rec.only
    assert _dump_kwargs(kwargs) == {}
    old = _old_open_w_newline_lf(tmp_path / "old.bytes", payload)
    assert old == path.read_bytes()
    assert b"\r" not in old


def test_stone_tablet_and_manifest_bytes(tmp_path):
    """Red: a tablet or MANIFEST.json changed shape. A tablet carries a
    sha256 over its candles, so a shape change is visible to readers."""
    tab = ST.Tablet(
        asset="BTC",
        exchange_id="coinbase",
        timeframe="5m",
        year=2026,
        source="ccxt",
        fetched_at="2026-08-27T00:00:00+00:00",
        candles=[[1756000000000, 61000.0, 61500.0, 60900.0, 61200.0, 12.5]],
    )
    written = ST.write_tablet(tab, root=tmp_path)
    expected = _old_fdopen_w_utf8(
        tmp_path, json.dumps(tab.to_dict(), separators=(",", ":"))
    )
    assert written.read_bytes() == expected
    assert b"\r" not in expected

    entry = ST.entry_from_tablet(tab)
    manifest = ST.write_manifest([entry], root=tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    expected_manifest = _old_fdopen_w_utf8(tmp_path, json.dumps(payload, indent=2))
    assert _crlf_to_lf(expected_manifest) == manifest.read_bytes()


def test_shared_testnet_bytes(tmp_path, monkeypatch):
    """Red: the persisted testnet chain changed shape."""
    from src.gui import shared_testnet as STN

    rec = _install(monkeypatch, STN, "atomic_write_json")
    payload = {"block_number": 7, "transactions": [{"hash": "0xab", "value": 1}]}
    dest = tmp_path / "testnet_chain.json"
    fake = SimpleNamespace(_persist_path=dest, _serialize_state=lambda: payload)
    STN.SharedTestnetBridge._save_now(fake)

    path, recorded, kwargs = rec.only
    assert path == dest and recorded == payload
    assert _dump_kwargs(kwargs) == {"indent": 2}
    old = _old_write_text_utf8(tmp_path / "old.bytes", payload, indent=2)
    assert _crlf_to_lf(old) == dest.read_bytes()


# ------------------------------------------------------------------ #
# bot_visualizer is not driven: its destination is hardcoded to        #
# ~/.acervator/bot_state.json, the operator's live position file.      #
# Its call is pinned in the source, and the bytes those arguments      #
# produce are pinned beside it.                                        #
# ------------------------------------------------------------------ #

_BV_PATH = Path(__file__).resolve().parents[1] / "src" / "gui" / "bot_visualizer.py"


def _bot_visualizer_saver() -> ast.FunctionDef:
    tree = ast.parse(_BV_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_save_bot_state_dict":
            return node
    raise AssertionError("_save_bot_state_dict not found in bot_visualizer.py")


def test_bot_visualizer_calls_the_shared_helper():
    """Red: the GUI's second writer of bot_state.json went back to its
    own staging name, which is how it collided with StateManager."""
    fn = _bot_visualizer_saver()
    source = ast.unparse(fn)
    assert "atomic_write_json(p, state, indent=2, default=str)" in source
    assert ".tmp" not in source
    assert "write_text" not in source


def test_bot_visualizer_arguments_reproduce_the_old_bytes(tmp_path):
    """Red: the arguments the GUI writer passes no longer reproduce what
    its own old idiom wrote."""
    state = {"bots": {"bot-a": _bot_record("bot-a")}, "obj": object()}
    dest = tmp_path / "bot_state.json"
    IO.atomic_write_json(dest, state, indent=2, default=str)
    old = _old_write_text_utf8(tmp_path / "old.bytes", state, indent=2, default=str)
    assert _crlf_to_lf(old) == dest.read_bytes()


# ================================================================== #
# The helper's own guarantees                                        #
# ================================================================== #


def _code_without_comments_or_strings(path: Path) -> str:
    """Source with every comment and string literal removed, so a marker
    named in a docstring is not read as a call."""
    import tokenize

    kept = []
    with path.open("rb") as handle:
        for tok in tokenize.tokenize(handle.readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            kept.append(tok.string)
    return " ".join(kept)


def test_no_migrated_site_stages_its_own_temp_file():
    """Red: a site went back to naming its own staging path, which is how
    StateManager and bot_visualizer came to share bot_state.tmp."""
    root = Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for rel in [
        "core/state_manager.py",
        "core/privacy_mask_registry.py",
        "core/feature_telemetry.py",
        "core/instance_guard.py",
        "gui/indicator_panel.py",
        "gui/bot_visualizer.py",
        "gui/shared_testnet.py",
        "simulator/fleet/simulator_bot_state.py",
        "trading/capital_reservation.py",
        "trading/stone_tablets/storage.py",
    ]:
        code = _code_without_comments_or_strings(root / rel)
        for marker in ("mkstemp", "NamedTemporaryFile"):
            if marker in code:
                offenders.append(f"{rel}:{marker}")
    assert offenders == []


def test_helper_writes_lf_on_every_platform(tmp_path):
    """Red: the helper translates newlines, so the same source produces
    different bytes on Windows and Linux."""
    dest = tmp_path / "out.json"
    IO.atomic_write_json(dest, {"a": 1, "b": [1, 2]}, indent=2)
    raw = dest.read_bytes()
    assert raw.count(b"\r") == 0
    assert raw.count(b"\n") == 6


def test_helper_writes_utf8_regardless_of_locale(tmp_path):
    """Red: a non-ASCII payload no longer lands as utf-8."""
    dest = tmp_path / "out.json"
    IO.atomic_write_json(dest, {"note": "café — ¥"}, ensure_ascii=False)
    assert dest.read_bytes() == '{"note": "café — ¥"}'.encode("utf-8")


# --------------------------- atomicity ---------------------------- #


def test_failure_before_the_rename_leaves_the_destination_intact(tmp_path):
    """Red: a failure between the staged write and the rename reached
    bot_state.json."""
    dest = tmp_path / "bot_state.json"
    IO.atomic_write_json(dest, {"bots": {"bot-a": 1}}, indent=2)
    before = dest.read_bytes()

    def _boom() -> None:
        raise RuntimeError("backup refresh failed")

    with pytest.raises(RuntimeError, match="backup refresh failed"):
        IO.atomic_write_json(dest, {"bots": {}}, indent=2, before_replace=_boom)

    assert dest.read_bytes() == before
    assert list(tmp_path.iterdir()) == [dest]


def test_failure_after_a_partial_write_leaves_the_destination_intact(
    tmp_path, monkeypatch
):
    """Red: a write that died half way promoted a truncated file over the
    destination."""
    dest = tmp_path / "bot_state.json"
    IO.atomic_write_json(dest, {"bots": {"bot-a": 1}}, indent=2)
    before = dest.read_bytes()

    real_fdopen = os.fdopen

    class _HalfWriter:
        def __init__(self, handle):
            self._handle = handle

        def write(self, data):
            self._handle.write(data[: len(data) // 2])
            raise OSError(28, "No space left on device")

        def __getattr__(self, name):
            return getattr(self._handle, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return self._handle.__exit__(*exc)

    monkeypatch.setattr(
        IO.os, "fdopen", lambda fd, mode: _HalfWriter(real_fdopen(fd, mode))
    )

    with pytest.raises(OSError):
        IO.atomic_write_json(dest, {"bots": {"bot-b": 2}}, indent=2)

    assert dest.read_bytes() == before
    assert list(tmp_path.iterdir()) == [dest]


def test_an_unserialisable_payload_creates_no_temp_file(tmp_path):
    """Red: a payload json.dumps rejects left a staging file behind."""
    dest = tmp_path / "out.json"
    with pytest.raises(TypeError):
        IO.atomic_write_json(dest, {"obj": object()})
    assert list(tmp_path.iterdir()) == []


# ----------------------------- fsync ------------------------------ #


def _fsync_order(tmp_path, monkeypatch) -> tuple[list[str], list[int], list[int]]:
    """Drive one write, returning the call order, fsynced fds, and the
    fds the staged file was written through."""
    order: list[str] = []
    fsynced: list[int] = []
    staged_fds: list[int] = []

    real_fsync = os.fsync
    real_replace = os.replace
    real_fdopen = os.fdopen

    def spy_fdopen(fd, mode):
        staged_fds.append(fd)
        return real_fdopen(fd, mode)

    def spy_fsync(fd):
        order.append("fsync")
        fsynced.append(fd)
        return real_fsync(fd)

    def spy_replace(src, dst):
        order.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(IO.os, "fdopen", spy_fdopen)
    monkeypatch.setattr(IO.os, "fsync", spy_fsync)
    monkeypatch.setattr(IO.os, "replace", spy_replace)

    IO.atomic_write_json(tmp_path / "out.json", {"a": 1}, indent=2)
    return order, fsynced, staged_fds


def test_the_staged_file_is_fsynced_before_the_rename(tmp_path, monkeypatch):
    """Red: the rename runs before the staged contents are on the platter,
    so a power loss can promote an empty bot_state.json."""
    order, fsynced, staged_fds = _fsync_order(tmp_path, monkeypatch)
    assert "fsync" in order, "the staged file was never fsynced"
    assert order.index("fsync") < order.index("replace")
    assert staged_fds, "no staged file descriptor was opened"
    assert staged_fds[0] in fsynced


def test_the_directory_entry_is_fsynced_where_the_platform_allows(
    tmp_path, monkeypatch
):
    """Red: on POSIX the rename itself is not flushed. Windows refuses
    os.open on a directory, so there the attempt is expected to be
    suppressed and no directory fsync appears."""
    order, _fsynced, _staged = _fsync_order(tmp_path, monkeypatch)
    dir_fsyncs = len(order) - 1 - order.index("replace")
    if os.name == "nt":
        assert dir_fsyncs == 0
    else:
        assert dir_fsyncs == 1


# --------------------------- collision ---------------------------- #


def test_two_writers_of_one_destination_cannot_share_a_staging_path(tmp_path):
    """Red: the staging name became a convention again. StateManager and
    bot_visualizer both staged bot_state.json through bot_state.tmp, so
    either could rename the other's partial write over the live file."""
    dest = tmp_path / "bot_state.json"
    IO.atomic_write_json(dest, {"writer": "seed"}, indent=2)
    staged: list[str] = []
    real_replace = os.replace

    inner_staging: list[Path] = []

    def _second_writer() -> None:
        before = set(tmp_path.iterdir())
        IO.atomic_write_json(dest, {"writer": "gui"}, indent=2)
        inner_staging.extend(sorted(set(tmp_path.iterdir()) - before))

    def spy_replace(src, dst):
        staged.append(str(src))
        return real_replace(src, dst)

    original = IO.os.replace
    IO.os.replace = spy_replace
    try:
        IO.atomic_write_json(
            dest, {"writer": "state_manager"}, indent=2, before_replace=_second_writer
        )
    finally:
        IO.os.replace = original

    assert len(staged) == 2
    assert staged[0] != staged[1]
    assert str(dest.with_suffix(".tmp")) not in staged
    assert json.loads(dest.read_text(encoding="utf-8")) == {"writer": "state_manager"}
    assert inner_staging == []


def test_staging_names_are_unique_across_many_writes(tmp_path):
    """Red: the staging name stopped being unique per write."""
    dest = tmp_path / "state.json"
    seen: set[str] = set()
    real_replace = os.replace

    def spy_replace(src, dst):
        seen.add(str(src))
        return real_replace(src, dst)

    original = IO.os.replace
    IO.os.replace = spy_replace
    try:
        for i in range(25):
            IO.atomic_write_json(dest, {"i": i})
    finally:
        IO.os.replace = original

    assert len(seen) == 25


def test_staging_file_is_a_sibling_of_the_destination(tmp_path):
    """Red: the staging file left the destination's directory, so the
    rename is no longer a same-filesystem move and stops being atomic."""
    dest = tmp_path / "nested" / "state.json"
    dest.parent.mkdir()
    captured: list[Path] = []
    real_replace = os.replace

    def spy_replace(src, dst):
        captured.append(Path(src))
        return real_replace(src, dst)

    original = IO.os.replace
    IO.os.replace = spy_replace
    try:
        IO.atomic_write_json(dest, {"a": 1})
    finally:
        IO.os.replace = original

    assert captured[0].parent == dest.parent
