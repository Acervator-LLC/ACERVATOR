"""Pin tests for the ``sim/runs/`` retention policy.

WHY THIS FILE HAS A GROWTH REPRODUCTION IN IT
=============================================
A retention policy that quietly does nothing looks EXACTLY like one
that works, because the directory stays small either way when
nothing is running. Asserting "the tree is under the cap" after a
handful of runs proves nothing at all: it passes with the policy
deleted.

So every bound here is measured against a control that reproduces
the failure first. ``test_growth_is_unbounded_without_a_policy``
drives the same fixture with ``RetentionPolicy(enabled=False)`` and
asserts the tree goes PAST the cap and keeps climbing. Only then
does the bounded case mean anything.

WHAT THE FIXTURE IS
===================
``_make_run`` writes a run directory shaped like the real one --
``meta.json``, ``trades.log``, ``gates.log``, ``signals.jsonl``,
``signals.digest.jsonl`` -- with the measured size RATIO between
them, not the measured sizes. One sampled production run on
2026-08-24 held signals.jsonl at 5.8 MB against a 12.8 KB digest and
a 302 B trades.log. The fixture keeps that 450:1 shape at 1/100th
the scale so the suite stays fast, and every byte assertion is
written against the fixture's own numbers.

Everything lands under ``tmp_path``. Nothing here reads or writes
``~/.acervator_logs`` or ``~/.acervator``.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.sim_run_log import (
    BULK_FILENAMES,
    PROTECTED_TREE_NAME,
    RetentionPolicy,
    SimRunLog,
    _safe_run_dir,
    apply_retention,
    list_runs,
)

# Fixture sizes. The RATIO is the measured one; the scale is not.
_BULK_BYTES = 58_000  # stands for signals.jsonl at 5.8 MB
_DIGEST_BYTES = 128  # stands for signals.digest.jsonl at 12.8 KB
_TRADES_BYTES = 302  # measured exactly
_GATES_BYTES = 4_000

_EPOCH = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
"""Fixture time origin. One run per minute, so any run count renders
a valid, monotonic, correctly shaped run_id."""


# ── fixture ──────────────────────────────────────────────────────


def _make_run(
    root: Path, day: int, *, bulk: int = _BULK_BYTES, digest: bool = True
) -> Path:
    """One run directory shaped like a real one. Newer = higher day.

    The run_id is DERIVED from a real datetime rather than formatted
    out of ``day`` by hand. The hand-rolled version rendered day 99
    as ``202601100T120000_...`` -- nine characters before the ``T``
    -- which is not the ``%Y%m%dT%H%M%S`` shape ``start_run``
    produces, so ``_sort_key`` ordered it by a different key and a
    policy assertion failed for a reason that was entirely the
    fixture's. Measured 2026-08-24. Deriving it removes the class.
    """
    when = _EPOCH + timedelta(minutes=day)
    run_id = when.strftime("%Y%m%dT%H%M%S") + f"_{day:06x}"
    d = root / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "origin": "sim",
                "started_at": when.isoformat(),
                "finished_at": None,
                "config": {"bots": 35},
                "summary": {"trades_logged": 7},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (d / "trades.log").write_text("t" * _TRADES_BYTES, encoding="utf-8")
    (d / "gates.log").write_text("g" * _GATES_BYTES, encoding="utf-8")
    if bulk:
        (d / "signals.jsonl").write_text("s" * bulk, encoding="utf-8")
    if digest:
        (d / "signals.digest.jsonl").write_text("d" * _DIGEST_BYTES, encoding="utf-8")
    return d


def _seed_index(root: Path) -> None:
    """An index describing every run on disk, newest first."""
    runs = sorted((root / "runs").iterdir(), reverse=True)
    (root / "index.json").write_text(
        json.dumps(
            [
                {
                    "run_id": d.name,
                    "started_at": json.loads(
                        (d / "meta.json").read_text(encoding="utf-8")
                    )["started_at"],
                    "finished_at": None,
                    "trades": 7,
                    "gates": 11,
                }
                for d in runs
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


def _tree_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in (root / "runs").rglob("*") if p.is_file())


def _run_names(root: Path) -> set:
    return {p.name for p in (root / "runs").iterdir() if p.is_dir()}


def _make_link(link: Path, target: Path) -> bool:
    """Plant a directory link at ``link`` pointing at ``target``.

    On Windows this is a JUNCTION, not a symlink, and that is the
    point rather than a convenience: ``os.symlink`` raises
    ``WinError 1314`` for this unprivileged account, so a junction is
    the link a hostile or careless input can actually plant here, and
    it is the one ``Path.is_symlink()`` reads as False.

    ``_winapi.CreateJunction`` is the same call ``mklink /J`` makes.
    Using it directly rather than shelling out keeps the test free of
    a subprocess whose argv is built from paths.
    """
    try:
        if sys.platform == "win32":
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)
    except (OSError, AttributeError, ImportError):
        return False
    return link.exists()


# ── A. the growth reproduction, and its controls ─────────────────


def test_growth_is_unbounded_without_a_policy(tmp_path):
    """THE CONTROL. Without a bound the tree climbs without limit.

    This test exists so the bounded tests below mean something. It
    passes today and it would still pass with every line of
    retention deleted -- that is what makes it the control and not
    the pin.
    """
    budget = 20 * _BULK_BYTES
    marks = []
    for i in range(60):
        _make_run(tmp_path, i)
        if (i + 1) % 20 == 0:
            res = apply_retention(tmp_path, policy=RetentionPolicy(enabled=False))
            assert res.refused == "policy disabled"
            assert res.evicted == 0 and res.demoted == 0
            marks.append(_tree_bytes(tmp_path))

    # Unbounded means two things, and both are asserted.
    # 1. It goes past any budget you name.
    assert marks[-1] > budget * 2, marks
    # 2. It keeps climbing at the same rate -- it does not level off.
    assert marks[0] < marks[1] < marks[2], marks
    step_a = marks[1] - marks[0]
    step_b = marks[2] - marks[1]
    assert (
        abs(step_a - step_b) < step_a * 0.05
    ), f"growth should be linear in run count: {marks}"
    assert len(_run_names(tmp_path)) == 60


def test_the_policy_bounds_the_same_fixture(tmp_path):
    """THE PIN. Identical fixture, policy on, tree under budget."""
    budget = 20 * _BULK_BYTES
    pol = RetentionPolicy(keep_verbatim=5, keep_runs=30, max_total_bytes=budget)
    marks = []
    for i in range(60):
        _make_run(tmp_path, i)
        _seed_index(tmp_path)
        apply_retention(tmp_path, policy=pol)
        if (i + 1) % 20 == 0:
            marks.append(_tree_bytes(tmp_path))

    assert max(marks) <= budget, marks
    assert _tree_bytes(tmp_path) <= budget
    assert len(_run_names(tmp_path)) <= 30


def test_the_bound_holds_at_ten_times_the_run_count(tmp_path):
    """The bound is on the tree, not on the number of passes.

    600 runs through a 20-run budget. If the policy were merely
    slowing growth rather than bounding it, this is where it shows.
    """
    budget = 20 * _BULK_BYTES
    pol = RetentionPolicy(keep_verbatim=5, keep_runs=30, max_total_bytes=budget)
    for i in range(600):
        _make_run(tmp_path, i)
        apply_retention(tmp_path, policy=pol)
    assert _tree_bytes(tmp_path) <= budget
    assert len(_run_names(tmp_path)) <= 30


def test_a_single_giant_run_does_not_defeat_the_count_cap(tmp_path):
    """Why the byte cap exists: a count cap alone bounds nothing.

    One run 100x normal size, well inside a generous count cap. A
    count-only policy leaves it; the byte cap takes it.
    """
    budget = 10 * _BULK_BYTES
    for i in range(5):
        _make_run(tmp_path, i)
    _make_run(tmp_path, 0, bulk=_BULK_BYTES * 100)
    _seed_index(tmp_path)
    before = _tree_bytes(tmp_path)
    assert before > budget

    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=10, keep_runs=100, max_total_bytes=budget),
    )
    assert res.evicted + res.demoted > 0
    assert _tree_bytes(tmp_path) <= budget


# ── B. it keeps what it claims to keep ───────────────────────────


def test_demotion_keeps_everything_except_the_bulk_file(tmp_path):
    """A demoted run is thinner, not gone."""
    for i in range(6):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=2, keep_runs=100, max_total_bytes=10**12),
    )

    assert res.demoted == 4, res.summary()
    assert len(_run_names(tmp_path)) == 6
    for name in res.demoted_run_ids:
        d = tmp_path / "runs" / name
        assert (d / "meta.json").exists()
        assert (d / "trades.log").exists()
        assert (d / "gates.log").exists()
        assert (d / "signals.digest.jsonl").exists()
        assert not (d / "signals.jsonl").exists()


def test_the_digest_is_what_survives_demotion(tmp_path):
    """Issue #62's digest retains every emitter identity, and it is
    the reason demotion is an acceptable loss at all. If the digest
    did not survive, this policy would have no argument."""
    for i in range(4):
        _make_run(tmp_path, i)
    apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=100, max_total_bytes=10**12),
    )
    digests = list((tmp_path / "runs").rglob("signals.digest.jsonl"))
    assert len(digests) == 4
    for d in digests:
        assert d.stat().st_size == _DIGEST_BYTES


def test_gates_log_is_never_bulk(tmp_path):
    """Gate-latch parity is the Simulator's validation criterion and
    a run's gates.log is the only record of it. It must not be in
    the demotion list, however tight the budget gets."""
    assert "gates.log" not in BULK_FILENAMES
    for i in range(20):
        _make_run(tmp_path, i)
    apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=3, max_total_bytes=1),
    )
    for d in (tmp_path / "runs").iterdir():
        assert (d / "gates.log").exists(), d.name


def test_the_newest_run_survives_a_budget_it_alone_exceeds(tmp_path):
    """THE RUN THAT MUST SURVIVE. The operator just made it.

    A budget smaller than one run would evict everything if the
    floor were not there. It must keep the newest, and it must SAY
    the budget did not hold rather than pretending it did.
    """
    newest = _make_run(tmp_path, 9, bulk=_BULK_BYTES * 4)
    for i in range(5):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)

    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=1, max_total_bytes=100),
    )

    assert newest.exists(), "the newest run was evicted"
    assert (newest / "meta.json").exists()
    assert _run_names(tmp_path) == {newest.name}
    assert res.floor_held is True
    assert "floor held" in res.summary()


def test_a_protected_run_id_is_never_evicted(tmp_path):
    """A run open in a second SimRunLog -- Nuclear loops them -- is
    the oldest on disk and every bound says evict it."""
    oldest = _make_run(tmp_path, 0)
    for i in range(1, 12):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)

    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=2, max_total_bytes=1),
        protect=frozenset({oldest.name}),
    )

    assert oldest.exists(), "a protected run was evicted"
    assert oldest.name not in res.evicted_run_ids


def test_nothing_is_touched_when_the_tree_is_already_within_bounds(tmp_path):
    """Retention that fires when it should not is as bad as one that
    never fires."""
    for i in range(3):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    before = _tree_bytes(tmp_path)
    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=10, keep_runs=100, max_total_bytes=10**12),
    )
    assert res.demoted == 0 and res.evicted == 0
    assert res.bytes_reclaimed == 0
    assert _tree_bytes(tmp_path) == before


def test_the_verbatim_window_tightens_before_a_run_is_evicted(tmp_path):
    """Cheapest reclaim first: bulk files go before whole runs do."""
    for i in range(10):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    # A budget that the skeletons alone fit inside, but the verbatim
    # window does not.
    skeletons = 10 * (_TRADES_BYTES + _GATES_BYTES + _DIGEST_BYTES + 400)
    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(
            keep_verbatim=8, keep_runs=100, max_total_bytes=skeletons + _BULK_BYTES
        ),
    )

    assert res.evicted == 0, "a run was evicted before demotion ran"
    assert res.verbatim_kept < 8, res.summary()
    assert len(_run_names(tmp_path)) == 10


# ── C. nothing is deleted silently ───────────────────────────────


def test_every_eviction_is_counted_and_named(tmp_path):
    for i in range(10):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    before = _run_names(tmp_path)
    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=4, max_total_bytes=10**12),
    )
    gone = before - _run_names(tmp_path)

    assert res.evicted == len(gone) == 6
    assert set(res.evicted_run_ids) == gone
    assert res.bytes_reclaimed > 0


def test_every_demotion_is_counted_and_named(tmp_path):
    for i in range(6):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=2, keep_runs=100, max_total_bytes=10**12),
    )
    thinned = {
        d.name
        for d in (tmp_path / "runs").iterdir()
        if not (d / "signals.jsonl").exists()
    }
    assert res.demoted == len(thinned) == 4
    assert set(res.demoted_run_ids) == thinned
    assert res.bytes_reclaimed == 4 * _BULK_BYTES


def test_a_demoted_run_is_distinguishable_from_one_that_never_wrote(tmp_path):
    """Two directories with no signals.jsonl. One was demoted, one
    never had one. On disk they would be identical without the
    retention block in meta."""
    _make_run(tmp_path, 5)  # newest, kept whole
    demoted = _make_run(tmp_path, 3)
    never = _make_run(tmp_path, 1, bulk=0)
    _seed_index(tmp_path)

    apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=100, max_total_bytes=10**12),
    )

    assert not (demoted / "signals.jsonl").exists()
    assert not (never / "signals.jsonl").exists()

    d_meta = json.loads((demoted / "meta.json").read_text("utf-8"))
    n_meta = json.loads((never / "meta.json").read_text("utf-8"))
    assert d_meta["retention"]["removed"] == ["signals.jsonl"]
    assert d_meta["retention"]["bytes_removed"] == _BULK_BYTES
    assert d_meta["retention"]["digest_retained"] is True
    assert d_meta["retention"]["demoted_at"]
    assert "retention" not in n_meta


def test_the_result_reaches_the_log(capture_log, tmp_path):
    """One INFO line on the module logger, carrying the counts.

    ``capture_log``, not ``caplog``: ``acervator`` sets
    ``propagate = False`` once the logging engine initialises, so
    caplog sees nothing in a full run and everything in isolation.
    """
    for i in range(8):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    with capture_log("acervator.sim_run_log") as records:
        res = apply_retention(
            tmp_path,
            policy=RetentionPolicy(
                keep_verbatim=1, keep_runs=3, max_total_bytes=10**12
            ),
        )

    lines = [r.getMessage() for r in records]
    assert lines, "retention logged nothing"
    assert any("sim retention:" in ln for ln in lines), lines
    assert any(f"{res.evicted} evicted" in ln for ln in lines), lines
    assert any(f"{res.demoted} demoted" in ln for ln in lines), lines


def test_a_refusal_does_not_read_as_a_quiet_success(tmp_path):
    """`refused` non-empty means nothing was touched. It must not be
    reportable as 'ran, found nothing'."""
    res = apply_retention(tmp_path / "nowhere")
    assert res.refused
    assert res.scanned == 0
    assert "refused" in res.summary()
    assert "0 evicted" not in res.summary()


def test_finish_run_publishes_what_retention_did(tmp_path):
    """The count has to reach the caller that just persisted a run,
    not only the log file."""
    for i in range(6):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    lg = SimRunLog(root=tmp_path)
    lg.start_run(config={})
    lg.record_trade("BTC-USD", "buy", 1.0, 100.0)
    lg.finish_run(summary={})

    assert lg.retention is not None
    assert lg.retention.refused == ""
    assert lg.retention.scanned == 7
    assert lg.run_id not in lg.retention.evicted_run_ids


def test_finish_run_never_evicts_its_own_directory(tmp_path):
    """The bounds all say evict, and it is the run that just closed."""
    for i in range(30):
        _make_run(tmp_path, i)
    lg = SimRunLog(root=tmp_path)
    lg.start_run(config={})
    lg.finish_run(summary={})
    assert lg.directory is not None
    assert lg.directory.exists()
    assert (lg.directory / "meta.json").exists()


def test_index_entries_pushed_off_the_end_are_counted(tmp_path):
    """The index has a length cap, so tombstones can themselves be
    evicted. That eviction is counted too."""
    for i in range(4):
        _make_run(tmp_path, i)
    (tmp_path / "index.json").write_text(
        json.dumps(
            [
                {"run_id": f"old-{n:04d}", "started_at": "2025-01-01T00:00:00"}
                for n in range(40)
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(
            keep_verbatim=10,
            keep_runs=100,
            max_total_bytes=10**12,
            index_max_entries=12,
        ),
    )
    assert res.index_dropped == 32
    assert len(list_runs(tmp_path)) == 12


# ── D. the index stays truthful ──────────────────────────────────


def _readable_entries(root: Path) -> list:
    return [e for e in list_runs(root) if not e.get("pruned")]


def test_no_readable_index_entry_names_a_missing_directory(tmp_path):
    """THE INVARIANT. Whatever the index calls readable is on disk.

    Driven hard: 40 runs through a policy that keeps 3, so most of
    the index is tombstone.
    """
    for i in range(40):
        _make_run(tmp_path, i)
        _seed_index(tmp_path)
        apply_retention(
            tmp_path,
            policy=RetentionPolicy(
                keep_verbatim=1, keep_runs=3, max_total_bytes=10**12
            ),
        )

    entries = list_runs(tmp_path)
    assert entries
    for e in _readable_entries(tmp_path):
        d = tmp_path / "runs" / str(e["run_id"])
        assert d.is_dir(), f"index calls {e['run_id']} readable; it is gone"


def test_an_evicted_run_is_tombstoned_not_erased(tmp_path):
    """A pruned run must stay distinguishable from a run that never
    happened, so its entry survives and keeps describing it."""
    for i in range(6):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=2, max_total_bytes=10**12),
    )
    assert res.evicted == 4

    by_id = {str(e["run_id"]): e for e in list_runs(tmp_path)}
    for run_id in res.evicted_run_ids:
        assert run_id in by_id, "an evicted run vanished from the index"
        e = by_id[run_id]
        assert e["pruned"] is True
        assert e["pruned_reason"] == "retention"
        assert e["pruned_at"]
        # still DESCRIBES the run
        assert e["trades"] == 7
        assert e["started_at"]


def test_a_hand_purged_tree_heals_the_index(tmp_path):
    """Reproduces 2026-08-24: the operator emptied runs/ himself.

    Every index entry then named a directory that is not there. The
    next pass has to mark them, not leave 102 lies in place.
    """
    for i in range(8):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    assert len(_readable_entries(tmp_path)) == 8

    for d in list((tmp_path / "runs").iterdir()):
        for f in d.iterdir():
            f.unlink()
        d.rmdir()

    res = apply_retention(tmp_path)
    assert res.scanned == 0
    entries = list_runs(tmp_path)
    assert len(entries) == 8, "the entries were erased instead of marked"
    assert all(e["pruned"] is True for e in entries)
    assert all(e["pruned_reason"] == "missing" for e in entries)
    assert _readable_entries(tmp_path) == []


def test_a_run_on_disk_missing_from_the_index_is_recovered(tmp_path):
    """Truthfulness runs both ways. An index that omits a run on
    disk hides bytes from the only surface that lists them."""
    for i in range(4):
        _make_run(tmp_path, i)
    (tmp_path / "index.json").write_text("[]", encoding="utf-8")

    apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=10, keep_runs=100, max_total_bytes=10**12),
    )

    listed = {str(e["run_id"]) for e in list_runs(tmp_path)}
    assert listed == _run_names(tmp_path)
    assert all(e.get("recovered") for e in list_runs(tmp_path))


def test_a_demoted_run_is_marked_not_verbatim_in_the_index(tmp_path):
    for i in range(5):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=2, keep_runs=100, max_total_bytes=10**12),
    )

    by_id = {str(e["run_id"]): e for e in list_runs(tmp_path)}
    for run_id in res.demoted_run_ids:
        assert by_id[run_id]["verbatim"] is False
        assert not by_id[run_id].get("pruned")


def test_a_missing_index_still_leaves_the_readers_working(tmp_path):
    """Both readers survived an absent index before retention
    existed. Retention writes one; that must not become a
    requirement for anything."""
    for i in range(3):
        _make_run(tmp_path, i)
    assert not (tmp_path / "index.json").exists()
    res = apply_retention(tmp_path)
    assert res.refused == ""
    (tmp_path / "index.json").unlink()
    assert list_runs(tmp_path) == []


def test_a_corrupt_index_is_rebuilt_not_propagated(tmp_path):
    for i in range(3):
        _make_run(tmp_path, i)
    (tmp_path / "index.json").write_text("{not json", encoding="utf-8")
    apply_retention(tmp_path)
    assert {str(e["run_id"]) for e in list_runs(tmp_path)} == _run_names(tmp_path)


def test_the_index_stays_newest_first_after_retention(tmp_path):
    for i in range(12):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)
    apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=2, keep_runs=6, max_total_bytes=10**12),
    )
    ids = [str(e["run_id"]) for e in list_runs(tmp_path)]
    assert ids == sorted(ids, reverse=True)


# ── E. containment: retention cannot reach outside runs/ ─────────


def test_a_link_out_of_runs_is_refused_and_its_target_survives(tmp_path):
    """THE HOSTILE INPUT. A directory link planted inside runs/,
    pointing at a tree that is none of retention's business.

    On Windows this is a junction, and ``Path.is_symlink()`` reads
    False for it. The refusal here comes from resolving the path and
    comparing its parent, not from the link check.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    precious = outside / "PRECIOUS.txt"
    precious.write_text("do not delete", encoding="utf-8")
    (outside / "nested").mkdir()
    (outside / "nested" / "also.txt").write_text("me either", "utf-8")

    for i in range(6):
        _make_run(tmp_path, i)
    link = tmp_path / "runs" / "00000000T000000_evil00"
    assert _make_link(link, outside), "could not plant the hostile link"

    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=1, max_total_bytes=1),
    )

    assert precious.read_text(encoding="utf-8") == "do not delete"
    assert (outside / "nested" / "also.txt").exists()
    assert link.exists(), "retention removed the link itself"
    assert res.skipped >= 1
    assert any("evil00" in r for r in res.skipped_reasons), res.skipped_reasons
    assert "evil00" not in res.evicted_run_ids


def test_a_link_pointing_back_into_runs_is_refused(tmp_path):
    """The case the containment check alone does NOT catch.

    ``runs/evil -> runs/keepme`` resolves to a path whose parent IS
    runs/, so the resolve-and-compare check passes it. Only the
    reparse check stops it, and without that check deleting the link
    deletes ``keepme``'s contents.
    """
    for i in range(6):
        _make_run(tmp_path, i)
    keep = max(_run_names(tmp_path))
    target = tmp_path / "runs" / keep
    link = tmp_path / "runs" / "00000000T000000_evil00"
    assert _make_link(link, target), "could not plant the hostile link"

    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=1, max_total_bytes=1),
    )

    assert (
        target / "meta.json"
    ).exists(), "the link's target was gutted through the link"
    assert (target / "gates.log").exists()
    assert any("evil00" in r for r in res.skipped_reasons), res.skipped_reasons


@pytest.mark.parametrize(
    "name",
    [
        "..",
        ".",
        "",
        "../..",
        "../../trade",
        "a/b",
        "runs/../../..",
        "C:/Windows",
        "\\\\server\\share",
        "..\\..\\trade",
        "x\x00y",
    ],
)
def test_a_hostile_name_is_never_resolved_to_a_run_directory(tmp_path, name):
    """The candidate guard, driven directly. None of these is a
    plain direct child of runs/, so none may become a delete."""
    (tmp_path / "runs").mkdir(parents=True)
    assert _safe_run_dir(tmp_path / "runs", name) is None


def test_a_crafted_run_id_in_the_index_is_data_not_a_path(tmp_path):
    """An index entry is untrusted text. Retention tombstones it as
    a label and never builds a filesystem path from it."""
    outside = tmp_path / "trade"
    outside.mkdir()
    (outside / "trade.log").write_text("live rows", encoding="utf-8")
    for i in range(3):
        _make_run(tmp_path, i)
    (tmp_path / "index.json").write_text(
        json.dumps(
            [
                {"run_id": "../../trade", "started_at": "2099-01-01T00:00:00"},
                {"run_id": "../trade", "started_at": "2098-01-01T00:00:00"},
                {"run_id": str(outside), "started_at": "2097-01-01T00:00:00"},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=1, max_total_bytes=1),
    )

    assert (outside / "trade.log").read_text(encoding="utf-8") == "live rows"
    crafted = {str(e["run_id"]): e for e in list_runs(tmp_path)}
    assert crafted["../../trade"]["pruned"] is True
    assert crafted["../../trade"]["pruned_reason"] == "missing"


def test_retention_refuses_the_protected_tree_outright(tmp_path, monkeypatch):
    """``~/.acervator`` holds bot_state.json, the exchange
    credentials and the stone tablet archive. No log policy may
    reach it, and the refusal is structural: retention declines the
    whole target rather than skipping items inside it."""
    fake_home = tmp_path / "home"
    protected = fake_home / PROTECTED_TREE_NAME
    tablets = protected / "stone_tablets"
    tablets.mkdir(parents=True)
    (tablets / "tablet_0001.json").write_text("sacred", encoding="utf-8")
    (protected / "bot_state.json").write_text("{}", encoding="utf-8")
    runs = protected / "sim" / "runs"
    runs.mkdir(parents=True)
    (runs / "20260801T120000_aaaaaa").mkdir()

    def _fake_home(cls: type) -> Path:
        del cls
        return fake_home

    monkeypatch.setattr(Path, "home", classmethod(_fake_home))

    res = apply_retention(
        protected / "sim",
        policy=RetentionPolicy(keep_verbatim=0, keep_runs=0, max_total_bytes=0),
    )

    assert res.refused
    assert "protected tree" in res.refused
    assert res.scanned == 0 and res.evicted == 0
    assert (tablets / "tablet_0001.json").exists()
    assert (protected / "bot_state.json").exists()
    assert (runs / "20260801T120000_aaaaaa").exists()


def test_retention_refuses_when_runs_itself_is_a_link(tmp_path):
    """If ``runs`` is a link to somewhere else, retention is not
    looking at the sim tree and must not act."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    root = tmp_path / "sim"
    root.mkdir()
    if not _make_link(root / "runs", outside):
        pytest.fail("could not plant the hostile link")

    res = apply_retention(
        root, policy=RetentionPolicy(keep_verbatim=0, keep_runs=0, max_total_bytes=0)
    )
    assert res.refused
    assert (outside / "keep.txt").exists()


def test_only_direct_children_of_runs_are_candidates(tmp_path):
    """A file beside the run directories, and a directory one level
    deeper, are neither of them runs."""
    for i in range(3):
        _make_run(tmp_path, i)
    stray = tmp_path / "runs" / "NOTES.txt"
    stray.write_text("operator notes", encoding="utf-8")
    deep = tmp_path / "runs" / max(_run_names(tmp_path)) / "sub" / "deeper"
    deep.mkdir(parents=True)
    (deep / "x.txt").write_text("x", encoding="utf-8")

    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=10, keep_runs=100, max_total_bytes=10**12),
    )
    assert stray.exists()
    assert deep.exists()
    assert any("NOTES.txt" in r for r in res.skipped_reasons)


def test_retention_never_removes_runs_root_or_the_log_root(tmp_path):
    """Even with every bound at zero and nothing left to keep."""
    _make_run(tmp_path, 0)
    _seed_index(tmp_path)
    apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=0, keep_runs=0, max_total_bytes=0),
    )
    assert (tmp_path / "runs").is_dir()
    assert tmp_path.is_dir()
    assert (tmp_path / "index.json").exists()


def test_a_sibling_of_the_sim_root_is_never_walked(tmp_path):
    """``sim/`` sits beside ``trade/`` and ``console/`` in the real
    tree. Retention is given the sim root and must not climb out."""
    logs = tmp_path / "logs"
    for bucket in ("trade", "console", "signals"):
        b = logs / bucket
        b.mkdir(parents=True)
        (b / f"{bucket}.log").write_text("rows", encoding="utf-8")
    sim = logs / "sim"
    for i in range(6):
        _make_run(sim, i)
    _seed_index(sim)

    apply_retention(
        sim, policy=RetentionPolicy(keep_verbatim=0, keep_runs=1, max_total_bytes=0)
    )

    for bucket in ("trade", "console", "signals"):
        assert (logs / bucket / f"{bucket}.log").exists()


# ── F. the pass never takes the replay down ──────────────────────


def test_retention_never_raises_on_a_hostile_root(tmp_path):
    for root in (tmp_path / "missing", tmp_path / "index.json", Path("")):
        res = apply_retention(root)
        assert res.refused, root


def test_finish_run_survives_a_retention_pass_that_raises(tmp_path, monkeypatch):
    """Losing a retention pass is recoverable. Taking down the
    replay that just finished is not."""
    import src.trading.sim_run_log as mod

    def _boom(*args: object, **kwargs: object) -> None:
        del args, kwargs
        msg = "scandir exploded"
        raise RuntimeError(msg)

    lg = SimRunLog(root=tmp_path)
    lg.start_run(config={})
    lg.record_trade("BTC-USD", "buy", 1.0, 100.0)
    monkeypatch.setattr(mod, "apply_retention", _boom)
    lg.finish_run(summary={})

    assert lg.is_open is False
    assert lg.retention is not None
    assert "scandir exploded" in lg.retention.refused
    assert (lg.directory / "trades.log").exists()


def test_an_interrupted_pass_never_leaves_a_readable_lie(tmp_path, monkeypatch):
    """THE ORDERING INVARIANT, driven by an interruption.

    Without a crash both orders -- record-then-delete and
    delete-then-record -- end in the same state, so nothing
    distinguishes them and the order looks like taste. It is not.

    Here the pass dies part-way through its evictions. The index was
    written in phase B, so it already calls every doomed run pruned
    and the survivors of the interruption merely still exist: the
    record UNDERSTATES what is gone, which claims nothing false.

    Reverse the order and this test goes red: the runs deleted
    before the interruption would still be listed as readable, and a
    reader following the index would find an empty directory and
    conclude the run had no trades.
    """
    import src.trading.sim_run_log as mod

    for i in range(10):
        _make_run(tmp_path, i)
    _seed_index(tmp_path)

    real = mod._remove_plain_tree
    calls = {"n": 0}

    def _dies_after_two(path: Path) -> int:
        calls["n"] += 1
        if calls["n"] > 2:
            msg = "power cut mid-pass"
            raise KeyboardInterrupt(msg)
        return real(path)

    monkeypatch.setattr(mod, "_remove_plain_tree", _dies_after_two)
    with pytest.raises(KeyboardInterrupt):
        apply_retention(
            tmp_path,
            policy=RetentionPolicy(
                keep_verbatim=1, keep_runs=2, max_total_bytes=10**12
            ),
        )

    on_disk = _run_names(tmp_path)
    assert len(on_disk) < 10, "the interruption removed nothing"
    entries = list_runs(tmp_path)
    assert entries

    for e in entries:
        run_id = str(e["run_id"])
        if not e.get("pruned"):
            assert (
                run_id in on_disk
            ), f"the index calls {run_id} readable and it is gone"
    # And the understatement is real, not vacuous: at least one run
    # is marked pruned while its bytes are still on disk.
    understated = [
        str(e["run_id"])
        for e in entries
        if e.get("pruned") and str(e["run_id"]) in on_disk
    ]
    assert understated, (
        "nothing was left understated, so this run did not exercise "
        "the window the ordering protects"
    )


def test_only_whole_run_eviction_can_meet_a_skeleton_budget(tmp_path):
    """THE BYTE CAP'S OWN CASE, and the tier nothing else covers.

    Found by calibration on 2026-08-24: deleting the byte-cap
    eviction loop left the whole suite green, because every existing
    budget test was satisfied by demotion or by the count cap before
    that loop was reached.

    Here neither can help. Every run is skeleton only -- no bulk
    file, so there is nothing to demote -- and the count cap is far
    above the run count. The budget is met by evicting whole runs or
    it is not met at all.
    """
    for i in range(40):
        _make_run(tmp_path, i, bulk=0)
    _seed_index(tmp_path)
    skeleton = _TRADES_BYTES + _GATES_BYTES + _DIGEST_BYTES
    budget = skeleton * 6
    assert _tree_bytes(tmp_path) > budget

    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(
            keep_verbatim=40, keep_runs=1000, max_total_bytes=budget
        ),
    )

    assert res.demoted == 0, "there was no bulk file to demote"
    assert res.evicted > 0, "only whole-run eviction can meet this"
    assert _tree_bytes(tmp_path) <= budget
    assert len(_run_names(tmp_path)) < 40
    assert res.floor_held is False


def test_containment_holds_when_the_link_check_is_blind(tmp_path, monkeypatch):
    """THE SECOND LAYER, driven by the degradation it exists for.

    Found by calibration on 2026-08-24: deleting the
    resolve-and-compare check left the suite green, because the
    reparse check refuses every hostile input first and nothing ever
    reaches the second layer. A layer no test can reach is a layer
    nobody knows is broken.

    So the reparse check is BLINDED here -- exactly what happens when
    it meets a reparse tag it does not know, or a filesystem that
    reports none -- and the containment check is left to refuse a
    real junction on its own.
    """
    import src.trading.sim_run_log as mod

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "PRECIOUS.txt").write_text("do not delete", "utf-8")
    runs = tmp_path / "runs"
    runs.mkdir()
    link = runs / "00000000T000000_evil00"
    assert _make_link(link, outside), "could not plant the hostile link"

    monkeypatch.setattr(mod, "_is_reparse", lambda path: False)

    assert (
        mod._safe_run_dir(runs, link.name) is None
    ), "with the link check blind, containment let a link through"

    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=0, keep_runs=0, max_total_bytes=0),
    )
    assert (outside / "PRECIOUS.txt").read_text("utf-8") == "do not delete"
    assert any("evil00" in r for r in res.skipped_reasons), res.skipped_reasons


def test_a_link_nested_inside_a_real_run_is_refused(tmp_path):
    """THE DEEPEST CONTAINMENT CASE.

    The run directory itself is a perfectly ordinary one -- correct
    name, correct files, a real direct child of runs/ -- so the
    candidate guard admits it. The link is one level DOWN, where
    only the walk can see it.

    Found by calibration on 2026-08-24: with no test in this shape,
    deleting the reparse check inside ``_measure_plain_tree`` left
    the suite green.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "PRECIOUS.txt").write_text("do not delete", "utf-8")
    (outside / "deep").mkdir()
    (outside / "deep" / "also.txt").write_text("me either", "utf-8")

    for i in range(6):
        _make_run(tmp_path, i)
    victim = tmp_path / "runs" / min(_run_names(tmp_path))
    assert _make_link(victim / "nested", outside), "could not plant the hostile link"
    _seed_index(tmp_path)

    res = apply_retention(
        tmp_path,
        policy=RetentionPolicy(keep_verbatim=1, keep_runs=1, max_total_bytes=1),
    )

    assert (outside / "PRECIOUS.txt").exists(), (
        "retention followed a link nested inside a run directory and "
        "deleted a tree outside runs/"
    )
    assert (outside / "PRECIOUS.txt").read_text("utf-8") == "do not delete"
    assert (outside / "deep" / "also.txt").exists()
    assert victim.exists(), "the run holding the link was removed"
    assert victim.name not in res.evicted_run_ids
    assert any(
        victim.name in r and "reparse" in r for r in res.skipped_reasons
    ), res.skipped_reasons


def test_the_bound_is_the_budget_plus_at_most_one_run(tmp_path):
    """The floor's price, pinned so it cannot surprise anybody.

    The newest run is never demoted and never evicted, so a pass that
    closes a run larger than the remaining headroom leaves the tree
    over budget by up to that run's size. The guarantee is
    ``max_total_bytes + one run``, not ``max_total_bytes``, and this
    test is where that is written down.
    """
    budget = 4 * _BULK_BYTES
    pol = RetentionPolicy(keep_verbatim=3, keep_runs=50, max_total_bytes=budget)
    biggest = 0
    for i in range(20):
        d = _make_run(tmp_path, i)
        pol_bytes = sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
        biggest = max(biggest, pol_bytes)
        apply_retention(tmp_path, policy=pol, protect=frozenset({d.name}))
        assert (
            _tree_bytes(tmp_path) <= budget + biggest
        ), "the tree exceeded the budget by more than one run"

    # And the overshoot is REAL, not a slack assertion that would
    # pass at any bound: the tree does go over the plain budget.
    over = _make_run(tmp_path, 27, bulk=_BULK_BYTES * 8)
    res = apply_retention(tmp_path, policy=pol, protect=frozenset({over.name}))
    assert _tree_bytes(tmp_path) > budget
    assert res.floor_held is True
    assert over.exists()
