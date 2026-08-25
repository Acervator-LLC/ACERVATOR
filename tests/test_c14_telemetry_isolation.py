"""C14: sim telemetry must not write the operator's live tree.

THE SHAPE OF THIS DEFECT IS THE POINT.

`ACERVATOR_TELEMETRY_ROOT` existed. `_telemetry_root()` honoured it. The
override was correct — and unreachable, because `TELEMETRY_PATH` bound
its result at IMPORT time and the tracker's constructor used that
constant. By the time a sim replay sets the override, the module has
long since been imported transitively, so the value was already fixed at
`~/.acervator/feature_telemetry.json`.

A previous attempt at this fix added the env var and stopped there. It
looked complete and changed nothing, which is why the breach recurred.
The defect was never the lookup; it was the BINDING MOMENT. A setter
would have been the wrong repair too — it would have added a second way
to be wrong while leaving the first in place.

These pins therefore test WHEN resolution happens, not merely that an
override exists. tmp_path only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core import feature_telemetry as ft  # noqa: E402


class TestResolutionHappensAtCallTime:
    def test_override_set_AFTER_import_is_honoured(self, tmp_path, monkeypatch):
        """The whole defect in one assertion.

        The module is already imported at this point — exactly the sim
        replay's situation — so this fails against any import-time
        binding.
        """
        monkeypatch.setenv(ft.TELEMETRY_ROOT_ENV, str(tmp_path))
        assert ft.telemetry_path().parent == tmp_path

    def test_a_tracker_built_after_the_override_writes_there(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(ft.TELEMETRY_ROOT_ENV, str(tmp_path))
        tracker = ft.FeatureTelemetry(autoload=False)
        assert tracker._path.parent == tmp_path

    def test_two_trackers_can_target_different_roots(self, tmp_path, monkeypatch):
        """Import-time binding made every tracker share one path. Sim and
        live coexist in one process, so they must be able to differ."""
        a_dir, b_dir = tmp_path / "a", tmp_path / "b"
        monkeypatch.setenv(ft.TELEMETRY_ROOT_ENV, str(a_dir))
        a = ft.FeatureTelemetry(autoload=False)
        monkeypatch.setenv(ft.TELEMETRY_ROOT_ENV, str(b_dir))
        b = ft.FeatureTelemetry(autoload=False)
        assert a._path.parent == a_dir
        assert b._path.parent == b_dir
        assert a._path != b._path


class TestDefaultIsUnchanged:
    def test_without_an_override_it_is_the_live_tree(self, monkeypatch):
        """Negative control. 'Never write the live tree' must not become
        'never write anywhere' — the LIVE app legitimately writes here,
        and a fix that broke that would be a worse regression."""
        monkeypatch.delenv(ft.TELEMETRY_ROOT_ENV, raising=False)
        assert ft.telemetry_path() == (
            Path.home() / ".acervator" / "feature_telemetry.json"
        )

    def test_an_explicit_path_still_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv(ft.TELEMETRY_ROOT_ENV, str(tmp_path / "env"))
        explicit = tmp_path / "explicit.json"
        tracker = ft.FeatureTelemetry(path=explicit, autoload=False)
        assert tracker._path == explicit


class TestItActuallyWritesWhereItSays:
    def test_a_flush_lands_in_the_override_root(self, tmp_path, monkeypatch):
        """Path resolution is necessary but not sufficient — prove the
        bytes land there. The conftest live-tree guard would fail this
        run if they went to ~/.acervator instead."""
        monkeypatch.setenv(ft.TELEMETRY_ROOT_ENV, str(tmp_path))
        tracker = ft.FeatureTelemetry(autoload=False)
        tracker.declare("c14_probe")
        tracker.record_call("c14_probe")
        assert tracker.save() is True
        written = list(tmp_path.glob("*.json"))
        assert written, f"nothing written under {tmp_path}"
        assert written[0].name == "feature_telemetry.json"
