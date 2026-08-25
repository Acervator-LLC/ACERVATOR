"""v3.24.8 — pin tests for FeatureTelemetry.

Operator directive 2026-08-02: runtime feedback loops so a feature
that runs and does nothing is distinguishable from one that works.

The single most important test here is T1: the module MUST detect
the two components confirmed dead by manual audit on 2026-08-02
(``SimStatStrip.set`` and ``parity_harness.compare_trades``). A
telemetry layer that reports optimistically is worse than none,
because it manufactures confidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core.feature_telemetry import (  # noqa: E402
    FeatureCounter,
    FeatureTelemetry,
    get_telemetry,
)


@pytest.fixture
def tel(tmp_path):
    return FeatureTelemetry(path=tmp_path / "tel.json", autoload=False)


# ── T1: the reason this module exists ────────────────────────────


def test_detects_declared_but_never_called(tel):
    """THE test. Mirrors the 2026-08-02 audit exactly."""
    tel.declare("sim.stat_strip.feed", "sim.price_chart.append")
    tel.record_call("sim.price_chart.append", count=4182)
    dead = tel.dead_features(scope="sim.")
    assert dead == ["sim.stat_strip.feed"]


def test_no_false_positive_on_active_feature(tel):
    tel.declare("a.thing")
    tel.record_call("a.thing")
    assert tel.dead_features() == []


def test_undeclared_feature_is_not_reported_dead(tel):
    """Only DECLARED features can be dead — an undeclared name that
    never fires is simply unknown, not a defect."""
    tel.record_call("known.thing")
    assert tel.dead_features() == []


# ── counters ─────────────────────────────────────────────────────


def test_record_call_accumulates(tel):
    tel.record_call("f", count=3)
    tel.record_call("f")
    c = tel.get("f")
    assert c.calls == 4
    assert c.session_calls == 4


def test_zero_or_negative_count_is_noop(tel):
    tel.record_call("f", count=0)
    tel.record_call("f", count=-5)
    assert tel.get("f") is None


def test_skips_track_reasons(tel):
    tel.record_skip("f", reason="no data")
    tel.record_skip("f", reason="no data")
    tel.record_skip("f", reason="stale")
    c = tel.get("f")
    assert c.skips == {"no data": 2, "stale": 1}
    assert c.total_skips == 3


def test_exceptions_track_type_names(tel):
    tel.record_exception("f", RecursionError("x"))
    tel.record_exception("f", RecursionError("y"))
    tel.record_exception("f", ValueError("z"))
    c = tel.get("f")
    assert c.exceptions == {"RecursionError": 2, "ValueError": 1}
    assert c.total_exceptions == 3


def test_exception_accepts_plain_string(tel):
    tel.record_exception("f", "CustomFailure")
    assert tel.get("f").exceptions == {"CustomFailure": 1}


def test_timestamps_set_on_first_and_last(tel):
    tel.record_call("f")
    c = tel.get("f")
    assert c.first_ts > 0
    first = c.first_ts
    tel.record_call("f")
    assert tel.get("f").first_ts == first  # unchanged
    assert tel.get("f").last_ts >= first  # advanced


# ── context manager ──────────────────────────────────────────────


def test_track_records_call_on_success(tel):
    with tel.track("f"):
        pass
    assert tel.get("f").calls == 1


def test_track_records_exception_and_reraises(tel):
    with pytest.raises(ValueError), tel.track("f"):
        raise ValueError("boom")
    c = tel.get("f")
    assert c.calls == 0
    assert c.exceptions == {"ValueError": 1}


# ── reporting ────────────────────────────────────────────────────


def test_report_flags_dead_first(tel):
    tel.declare("z.dead", "a.alive")
    tel.record_call("a.alive")
    lines = tel.report_lines()
    joined = "\n".join(lines)
    assert "DEAD" in joined
    assert "z.dead" in joined
    dead_i = next(i for i, ln in enumerate(lines) if "DEAD" in ln)
    active_i = next(i for i, ln in enumerate(lines) if "ACTIVE" in ln)
    assert dead_i < active_i, "dead must be reported before active"


def test_report_flags_broken_wired_but_failing(tel):
    """Exceptions with zero successful calls = wired but broken."""
    tel.declare("f.broken")
    tel.record_exception("f.broken", RuntimeError("x"))
    joined = "\n".join(tel.report_lines())
    assert "BROKEN" in joined


def test_report_handles_empty_registry(tel):
    joined = "\n".join(tel.report_lines())
    assert "no features recorded" in joined


def test_scope_filters_report(tel):
    tel.record_call("sim.a")
    tel.record_call("gui.b")
    joined = "\n".join(tel.report_lines(scope="sim."))
    assert "sim.a" in joined
    assert "gui.b" not in joined


# ── persistence ──────────────────────────────────────────────────


def test_save_load_roundtrip_keeps_lifetime(tmp_path):
    p = tmp_path / "tel.json"
    t1 = FeatureTelemetry(path=p, autoload=False)
    t1.declare("f")
    t1.record_call("f", count=100)
    assert t1.save() is True

    t2 = FeatureTelemetry(path=p, autoload=True)
    c = t2.get("f")
    assert c.calls == 100
    assert c.session_calls == 0, "session count must NOT persist"


def test_stalled_detection_after_reload(tmp_path):
    """A feature with lifetime history but no calls this session is
    STALLED — the gate.log-stall failure shape."""
    p = tmp_path / "tel.json"
    t1 = FeatureTelemetry(path=p, autoload=False)
    t1.declare("f")
    t1.record_call("f", count=10)
    t1.save()

    t2 = FeatureTelemetry(path=p, autoload=True)
    assert t2.dead_features(session_only=True) == ["f"]
    assert t2.dead_features() == [], "has lifetime calls, not dead"


def test_load_missing_file_is_clean(tmp_path):
    t = FeatureTelemetry(path=tmp_path / "nope.json", autoload=False)
    assert t.load() is False


def test_load_corrupt_file_does_not_raise(tmp_path):
    p = tmp_path / "tel.json"
    p.write_text("{ not valid json", encoding="utf-8")
    t = FeatureTelemetry(path=p, autoload=False)
    assert t.load() is False
    assert t.snapshot() == []


def test_declared_survives_reload(tmp_path):
    p = tmp_path / "tel.json"
    t1 = FeatureTelemetry(path=p, autoload=False)
    t1.declare("never.fires")
    t1.save()
    t2 = FeatureTelemetry(path=p, autoload=True)
    assert "never.fires" in t2.dead_features()


# ── bounds + hygiene ─────────────────────────────────────────────


def test_reason_keys_are_bounded(tel):
    for i in range(100):
        tel.record_skip("f", reason=f"reason-{i}")
    c = tel.get("f")
    assert len(c.skips) <= 26, "must cap distinct reason keys"
    assert "_other" in c.skips


def test_reset_clears_counts_but_keeps_declarations(tel):
    tel.declare("f")
    tel.record_call("f", count=5)
    tel.reset()
    assert tel.get("f").calls == 0
    assert "f" in tel.dead_features(), "declaration must survive reset"


def test_singleton_is_stable():
    assert get_telemetry() is get_telemetry()


# ── markdown report (v3.24.8) ────────────────────────────────────


def test_markdown_report_written(tmp_path, tel):
    tel.declare("sim.a")
    tel.record_call("sim.a")
    out = tel.write_markdown_report(path=tmp_path / "r.md", scope="sim.")
    assert out is not None
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith(
        "# Feature Validation & Error Report"
    )


def test_markdown_separates_python_and_app_errors(tmp_path, tel):
    """Python errors (exceptions) and application errors (skips
    with reasons) must be distinct sections — they need different
    fixes."""
    tel.declare("sim.f")
    tel.record_call("sim.f")
    tel.record_exception("sim.f", RecursionError("x"))
    tel.record_skip("sim.f", reason="no candle at cursor")
    body = tel.write_markdown_report(path=tmp_path / "r.md", scope="sim.").read_text(
        encoding="utf-8"
    )
    assert "## Python errors" in body
    assert "RecursionError" in body
    assert "## Application errors" in body
    assert "no candle at cursor" in body


def test_markdown_verdict_clean_when_all_fired(tmp_path, tel):
    tel.declare("sim.a")
    tel.record_call("sim.a")
    body = tel.write_markdown_report(path=tmp_path / "r.md", scope="sim.").read_text(
        encoding="utf-8"
    )
    assert "all declared features fired" in body


def test_markdown_verdict_flags_dead(tmp_path, tel):
    tel.declare("sim.dead", "sim.alive")
    tel.record_call("sim.alive")
    body = tel.write_markdown_report(path=tmp_path / "r.md", scope="sim.").read_text(
        encoding="utf-8"
    )
    assert "need attention" in body
    assert "`sim.dead`" in body


def test_markdown_includes_run_context(tmp_path, tel):
    tel.declare("sim.a")
    tel.record_call("sim.a")
    body = tel.write_markdown_report(
        path=tmp_path / "r.md",
        scope="sim.",
        run_context={"Candles played": "4,182 / 35,449"},
    ).read_text(encoding="utf-8")
    assert "Candles played: 4,182 / 35,449" in body


def test_markdown_handles_empty_registry(tmp_path, tel):
    body = tel.write_markdown_report(path=tmp_path / "r.md").read_text(encoding="utf-8")
    assert "no features recorded" in body


def test_counter_from_dict_roundtrip():
    c = FeatureCounter(
        name="x",
        calls=7,
        skips={"a": 1},
        exceptions={"E": 2},
        first_ts=1.0,
        last_ts=2.0,
    )
    c2 = FeatureCounter.from_dict(c.to_dict())
    assert c2.calls == 7
    assert c2.skips == {"a": 1}
    assert c2.exceptions == {"E": 2}
    assert c2.session_calls == 0
