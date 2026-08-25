"""Promotion must refuse a stale island, and must not refuse a clean one.

These tests reconstruct the 2026-08-10 near-miss in miniature: an island
forks, live moves on underneath it, and the island's copy still looks
promotable. Promoting it would revert whatever landed in the meantime.

Every refusal test is paired with a control in which live did NOT move.
Without that pair, a tool that refused everything would pass the suite
while protecting nothing — and a tool that refuses everything gets
bypassed, which is worse than no tool.

No test touches the real live tree or the real scratchpad. Every tree is
built under `tmp_path`, and promotion targets whatever `live_root` the
manifest records, which is always inside `tmp_path` here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import island

RATE_BEFORE = "def usd_per_base(sym):\n    return None\n"
RATE_FIXED = "def usd_per_base(sym):\n    return lookup(sym)\n"
RATE_FABRICATED = "def usd_per_base(sym):\n    return 1.0\n"

SIBLING_BEFORE = "def sum_claims(bots):\n    return 0.0\n"
SIBLING_FIXED = "def sum_claims(bots):\n    raise LookupError(bots)\n"


def write(path: Path, text: str, eol: str = "\n") -> None:
    """Write `text` to `path` using `eol`, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.replace("\r\n", "\n").replace("\n", eol)
    path.write_bytes(payload.encode("utf-8"))


@pytest.fixture
def live(tmp_path: Path) -> Path:
    """Build a miniature live tree under tmp_path."""
    root = tmp_path / "live"
    write(root / "src" / "trading" / "bot_container.py", RATE_BEFORE)
    write(root / "src" / "trading" / "claims.py", SIBLING_BEFORE)
    write(root / "tests" / "test_claims.py", "def test_x():\n    assert True\n")
    write(root / "src" / "__init__.py", '__version__ = "3.15.27"\n')
    write(root / "tools" / "harness" / "coding_archetype.py", "PASS = True\n")
    return root


@pytest.fixture
def islands(tmp_path: Path) -> Path:
    """Return an islands root under tmp_path, never the real scratchpad."""
    root = tmp_path / "islands"
    root.mkdir()
    return root


def fork(live_root: Path, islands_root: Path, name: str = "ISL") -> Path:
    """Fork `live_root` into `islands_root` and return the island path."""
    return island.create_island(
        live_root,
        islands_root,
        name,
        "unit test island",
        ["src/trading/bot_container.py"],
    )


def snapshot(root: Path) -> dict[str, bytes]:
    """Return every file under `root` as raw bytes, keyed by relpath."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def dirs(root: Path) -> set[str]:
    """Return every directory under `root`, keyed by relpath."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir()}


# --------------------------------------------------------------------
# A clean island promotes, and the ledger records it.
# --------------------------------------------------------------------


def test_clean_island_promotes_and_writes_a_ledger_line(
    live: Path,
    islands: Path,
) -> None:
    """Live did not move, so the promotion lands and is recorded."""
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "bot_container.py", RATE_FIXED)

    assert island.promote_island(isl) == 0
    assert (live / "src" / "trading" / "bot_container.py").read_text() == RATE_FIXED

    ledger = live / island.LEDGER_RELPATH
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["island"] == "ISL"
    assert record["purpose"] == "unit test island"
    assert record["promoted_at"]
    promoted = {f["path"]: f["hash"] for f in record["files"]}
    assert "src/trading/bot_container.py" in promoted
    assert promoted["src/trading/bot_container.py"] == island.hash_bytes(
        RATE_FIXED.encode("utf-8"),
    )


def test_ledger_reconstructs_which_island_a_live_file_came_from(
    live: Path,
    islands: Path,
) -> None:
    """Two islands promote in turn; the ledger keeps both attributions."""
    first = fork(live, islands, "ISL_A")
    write(first / "src" / "trading" / "bot_container.py", RATE_FIXED)
    assert island.promote_island(first) == 0

    second = island.create_island(
        live,
        islands,
        "ISL_B",
        "second island",
        ["src/trading/claims.py"],
    )
    write(second / "src" / "trading" / "claims.py", SIBLING_FIXED)
    assert island.promote_island(second) == 0

    lines = (
        (live / island.LEDGER_RELPATH).read_text(encoding="utf-8").strip().splitlines()
    )
    owners = {
        f["path"]: json.loads(line)["island"]
        for line in lines
        for f in json.loads(line)["files"]
    }
    assert owners["src/trading/bot_container.py"] == "ISL_A"
    assert owners["src/trading/claims.py"] == "ISL_B"


# --------------------------------------------------------------------
# The near-miss itself: live moved, so the island is refused.
# --------------------------------------------------------------------


def test_stale_island_is_refused_and_live_is_byte_identical(
    live: Path,
    islands: Path,
) -> None:
    """The ISLAND_P2 case: live gained a fix after the island forked."""
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "bot_container.py", RATE_FABRICATED)

    # Live gains the real fix after the fork. The island never saw it.
    write(live / "src" / "trading" / "bot_container.py", RATE_FIXED)
    before = snapshot(live)

    assert island.promote_island(isl) != 0
    assert snapshot(live) == before
    assert (live / "src" / "trading" / "bot_container.py").read_text() == RATE_FIXED
    assert not (live / island.LEDGER_RELPATH).exists()


def test_refusal_names_the_stale_file_and_says_to_rebase(
    live: Path,
    islands: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A refusal that does not say what to do next gets worked around."""
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "bot_container.py", RATE_FABRICATED)
    write(live / "src" / "trading" / "bot_container.py", RATE_FIXED)

    assert island.promote_island(isl) != 0
    out = capsys.readouterr().out
    assert "src/trading/bot_container.py" in out
    assert "REFUSED" in out
    assert "REBASE" in out.upper()
    assert "Nothing was promoted" in out


def test_clean_island_is_not_refused_control_for_staleness(
    live: Path,
    islands: Path,
) -> None:
    """Control: the same shape with live unmoved must PASS.

    This is the pair for the staleness tests. A tool that refused every
    promotion would satisfy them alone, and would then be bypassed.
    """
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "bot_container.py", RATE_FABRICATED)

    assert island.promote_island(isl) == 0


# --------------------------------------------------------------------
# All or nothing.
# --------------------------------------------------------------------


def test_one_stale_file_blocks_the_clean_file_too(
    live: Path,
    islands: Path,
) -> None:
    """A half-applied change is worse than none, so neither lands."""
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "bot_container.py", RATE_FABRICATED)
    write(isl / "src" / "trading" / "claims.py", SIBLING_FIXED)

    # Only ONE of the two moved in live.
    write(live / "src" / "trading" / "bot_container.py", RATE_FIXED)
    before = snapshot(live)

    assert island.promote_island(isl) != 0
    assert snapshot(live) == before
    # The clean file specifically did NOT sneak through.
    assert (live / "src" / "trading" / "claims.py").read_text() == SIBLING_BEFORE


def test_both_files_land_when_neither_is_stale_control(
    live: Path,
    islands: Path,
) -> None:
    """Control for all-or-nothing: two clean files both promote."""
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "bot_container.py", RATE_FIXED)
    write(isl / "src" / "trading" / "claims.py", SIBLING_FIXED)

    assert island.promote_island(isl) == 0
    assert (live / "src" / "trading" / "claims.py").read_text() == SIBLING_FIXED
    assert (live / "src" / "trading" / "bot_container.py").read_text() == RATE_FIXED


# --------------------------------------------------------------------
# Unmanaged islands.
# --------------------------------------------------------------------


def test_unmanaged_island_is_refused(
    live: Path,
    islands: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No manifest means no recorded base, so no promotion."""
    hand_rolled = islands / "ISLAND_P2"
    write(hand_rolled / "src" / "trading" / "bot_container.py", RATE_FABRICATED)
    before = snapshot(live)

    assert island.promote_island(hand_rolled) != 0
    assert snapshot(live) == before
    out = capsys.readouterr().out
    assert "UNMANAGED" in out
    assert "Nothing was promoted" in out


def test_list_reports_unmanaged_islands_without_crashing(
    live: Path,
    islands: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Forty hand-rolled islands must not crash the tool."""
    for index in range(5):
        write(islands / f"ISLAND{index}" / "src" / "a.py", "x = 1\n")
    managed = fork(live, islands, "ISL_MANAGED")
    write(managed / "src" / "trading" / "claims.py", SIBLING_FIXED)

    assert island.list_islands(islands) == 0
    out = capsys.readouterr().out
    assert out.count("UNMANAGED") >= 5
    assert "ISL_MANAGED" in out


def test_island_with_no_changes_is_superseded(
    live: Path,
    islands: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An island whose files all match live is litter, and says so."""
    fork(live, islands, "ISL_DONE")
    assert island.list_islands(islands) == 0
    assert "SUPERSEDED" in capsys.readouterr().out


# --------------------------------------------------------------------
# Line endings.
# --------------------------------------------------------------------


def test_promotion_preserves_crlf_destination_line_endings(
    live: Path,
    islands: Path,
) -> None:
    """A CRLF file in live stays CRLF after an LF island promotes onto it."""
    write(live / "src" / "trading" / "claims.py", SIBLING_BEFORE, eol="\r\n")
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "claims.py", SIBLING_FIXED, eol="\n")

    assert island.promote_island(isl) == 0
    landed = (live / "src" / "trading" / "claims.py").read_bytes()
    assert b"\r\n" in landed
    assert landed.replace(b"\r\n", b"\n").decode() == SIBLING_FIXED


def test_promotion_preserves_lf_destination_line_endings(
    live: Path,
    islands: Path,
) -> None:
    """Control: an LF destination is not converted to CRLF."""
    write(live / "src" / "trading" / "claims.py", SIBLING_BEFORE, eol="\n")
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "claims.py", SIBLING_FIXED, eol="\r\n")

    assert island.promote_island(isl) == 0
    landed = (live / "src" / "trading" / "claims.py").read_bytes()
    assert b"\r\n" not in landed
    assert landed.decode() == SIBLING_FIXED


def test_line_ending_difference_alone_is_not_a_change(
    live: Path,
    islands: Path,
) -> None:
    """Otherwise every promotion would look stale on Windows."""
    isl = fork(live, islands)
    # Same text, different endings only.
    write(isl / "src" / "trading" / "claims.py", SIBLING_BEFORE, eol="\r\n")

    manifest = island.load_manifest(isl)
    assert manifest is not None
    changed = island.candidates(island.classify(isl, manifest))
    assert [v.rel for v in changed] == []


def test_real_content_change_is_still_detected_control(
    live: Path,
    islands: Path,
) -> None:
    """Control: normalisation must not blind the tool to a real edit."""
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "claims.py", SIBLING_FIXED, eol="\r\n")

    manifest = island.load_manifest(isl)
    assert manifest is not None
    changed = island.candidates(island.classify(isl, manifest))
    assert [v.rel for v in changed] == ["src/trading/claims.py"]


# --------------------------------------------------------------------
# Scope, additions, and dry run.
# --------------------------------------------------------------------


def test_protected_paths_are_refused_not_silently_skipped(
    live: Path,
    islands: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Silent dropping is the failure mode this tool exists to stop."""
    isl = fork(live, islands)
    write(isl / "tools" / "harness" / "coding_archetype.py", "PASS = False\n")
    write(isl / "src" / "__init__.py", '__version__ = "9.9.9"\n')
    before = snapshot(live)

    assert island.promote_island(isl) != 0
    assert snapshot(live) == before
    out = capsys.readouterr().out
    assert "protected" in out.lower()


def test_added_file_absent_from_live_promotes(
    live: Path,
    islands: Path,
) -> None:
    """A genuinely new file is not stale and may land."""
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "reservation.py", "RESERVED = 1\n")

    assert island.promote_island(isl) == 0
    assert (live / "src" / "trading" / "reservation.py").read_text() == "RESERVED = 1\n"


def test_added_file_that_since_appeared_in_live_is_stale(
    live: Path,
    islands: Path,
) -> None:
    """Two authors created the same path. That is a conflict, not a copy."""
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "reservation.py", "RESERVED = 1\n")
    write(live / "src" / "trading" / "reservation.py", "RESERVED = 2\n")
    before = snapshot(live)

    assert island.promote_island(isl) != 0
    assert snapshot(live) == before


def test_dry_run_never_writes_to_live(live: Path, islands: Path) -> None:
    """A dry run reports the same set it would write, and writes nothing."""
    isl = fork(live, islands)
    write(isl / "src" / "trading" / "claims.py", SIBLING_FIXED)
    before = snapshot(live)

    assert island.promote_island(isl, dry_run=True) == 0
    assert snapshot(live) == before
    assert not (live / island.LEDGER_RELPATH).exists()


def test_live_moving_alone_does_not_make_the_island_promotable(
    live: Path,
    islands: Path,
) -> None:
    """The island never touched the file, so it must not push its old copy."""
    isl = fork(live, islands)
    write(live / "src" / "trading" / "bot_container.py", RATE_FIXED)

    assert island.promote_island(isl) == 0
    # Live keeps its newer content; the island's stale copy did not win.
    assert (live / "src" / "trading" / "bot_container.py").read_text() == RATE_FIXED


def test_new_refuses_an_existing_island_name(live: Path, islands: Path) -> None:
    """Overwriting an island would destroy work with no record."""
    fork(live, islands, "ISL_ONE")
    with pytest.raises(FileExistsError):
        fork(live, islands, "ISL_ONE")


def test_manifest_records_base_hashes_and_declared_files(
    live: Path,
    islands: Path,
) -> None:
    """Without a recorded base there is nothing to judge staleness against."""
    isl = fork(live, islands)
    manifest = island.load_manifest(isl)
    assert manifest is not None
    assert manifest["live_root"] == str(live)
    assert manifest["declared_files"] == ["src/trading/bot_container.py"]
    base = manifest["base_hashes"]
    assert base["src/trading/bot_container.py"] == island.hash_bytes(
        RATE_BEFORE.encode("utf-8"),
    )


# --------------------------------------------------------------------
# An island name may not escape the islands root.
#
# Windows drops the left operand of a path join when the right side is
# absolute, and walks upward on a dot-dot segment. An unchecked name
# therefore addresses any directory on the machine, including the live
# tree this tool exists to protect. Every name below must be refused by
# NAME VALIDATION, before one byte is written.
#
# Every escape target in these tests stays inside tmp_path, so that a
# run with the validation removed — the mutation control — damages
# nothing outside the temporary tree.
# --------------------------------------------------------------------

# Names checked through pure functions and read-only subcommands only.
ESCAPING_NAMES = [
    "..",
    "../ESCAPED",
    "..\\ESCAPED",
    "../../ESCAPED",
    "sub/ISL",
    "sub\\ISL",
    "/ABS_ESCAPE",
    "\\ABS_ESCAPE",
    "C:/tmp/isl_break/ABS_ESCAPE",
    "C:\\tmp\\isl_break\\ABS_ESCAPE",
    "C:",
    "",
    "   ",
    ".",
    "...",
    "ISL/",
    "ISL\\",
    "ISL.",
    "ISL ",
]

# The subset whose escape target stays inside tmp_path even unguarded,
# so it is safe to attempt a real fork with it.
CONTAINED_ESCAPING_NAMES = [
    "..",
    "../ESCAPED",
    "..\\ESCAPED",
    "sub/ISL",
    "sub\\ISL",
    "",
    ".",
    "...",
    "ISL/",
    "ISL\\",
    "ISL.",
    "ISL ",
]


@pytest.mark.parametrize("name", ESCAPING_NAMES)
def test_island_dir_for_refuses_a_name_that_is_not_a_direct_child(
    islands: Path,
    name: str,
) -> None:
    """The resolved directory must be a DIRECT child of the root."""
    with pytest.raises(island.IslandNameError) as caught:
        island.island_dir_for(islands, name)
    message = str(caught.value)
    assert repr(name) in message
    assert "simple directory name" in message
    assert "directly under the islands root" in message


@pytest.mark.parametrize("name", ["ISL", "ISL_OK", "isl.2", "a-b_c", "ISL2"])
def test_island_dir_for_accepts_a_simple_name_control(
    islands: Path,
    name: str,
) -> None:
    """Control: a validator that refused everything would be bypassed."""
    assert island.island_dir_for(islands, name) == islands / name


@pytest.mark.parametrize("name", CONTAINED_ESCAPING_NAMES)
def test_create_island_refuses_a_traversal_name(
    live: Path,
    islands: Path,
    name: str,
) -> None:
    """The fork itself must refuse, not only the CLI wrapper."""
    with pytest.raises(island.IslandNameError):
        island.create_island(live, islands, name, "traversal probe", [])


def test_refused_new_creates_nothing_on_disk(
    live: Path,
    islands: Path,
    tmp_path: Path,
) -> None:
    """A refused name must not leave one byte or one directory behind.

    This is the requirement the 2026-08-11 defect broke: the unchecked
    name reached copytree, wrote a partial tree outside the root, and
    left it there when it died.
    """
    before_files = snapshot(tmp_path)
    before_dirs = dirs(tmp_path)

    for name in CONTAINED_ESCAPING_NAMES:
        with pytest.raises(island.IslandNameError):
            island.create_island(live, islands, name, "traversal probe", [])

    assert snapshot(tmp_path) == before_files
    assert dirs(tmp_path) == before_dirs
    assert not (tmp_path / "ESCAPED").exists()
    assert not (islands / "sub").exists()


def test_a_simple_name_still_forks_control(
    live: Path,
    islands: Path,
    tmp_path: Path,
) -> None:
    """Control for the test above: a good name DOES create a tree."""
    before_dirs = dirs(tmp_path)
    island.create_island(live, islands, "ISL_OK", "control", [])
    assert dirs(tmp_path) != before_dirs
    assert (islands / "ISL_OK" / island.MANIFEST_NAME).is_file()


@pytest.mark.parametrize("name", ESCAPING_NAMES)
def test_status_refuses_a_traversal_name(
    islands: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every subcommand that takes a name refuses it identically."""
    monkeypatch.setattr(island, "ISLANDS_ROOT", islands)
    assert island.main(["status", name]) == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "simple directory name" in out


@pytest.mark.parametrize("name", ESCAPING_NAMES)
def test_promote_refuses_a_traversal_name(
    islands: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Promotion is the path that writes to live, so it refuses too."""
    monkeypatch.setattr(island, "ISLANDS_ROOT", islands)
    assert island.main(["promote", name]) == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "simple directory name" in out


@pytest.mark.parametrize("name", ["..", ".", ""])
def test_new_refuses_a_traversal_name_by_name_validation(
    islands: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`new` must refuse by NAME, not by tripping over an existing dir.

    Each name here already points at a directory that exists, so an
    unchecked `new` would refuse it as "island already exists". The
    message is what tells the two refusals apart.
    """
    monkeypatch.setattr(island, "ISLANDS_ROOT", islands)
    assert island.main(["new", name, "--purpose", "traversal probe"]) == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "simple directory name" in out
    assert "already exists" not in out


def test_promote_refuses_a_traversal_name_even_when_it_would_have_worked(
    live: Path,
    islands: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The refusal comes from the name, not from a missing manifest.

    Before this fix, `promote ../X` was refused only INCIDENTALLY,
    because nothing at X carried a manifest. Here X does carry one and
    is otherwise promotable — the dry run proves it — so only name
    validation can refuse it.
    """
    escaped = island.create_island(
        live,
        islands.parent,
        "ESCAPED",
        "outside the islands root",
        [],
    )
    write(escaped / "src" / "trading" / "claims.py", SIBLING_FIXED)
    assert island.promote_island(escaped, dry_run=True) == 0
    capsys.readouterr()

    monkeypatch.setattr(island, "ISLANDS_ROOT", islands)
    before = snapshot(live)
    assert island.main(["promote", "../ESCAPED"]) == 1

    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "'../ESCAPED'" in out
    assert "simple directory name" in out
    assert "UNMANAGED" not in out
    assert snapshot(live) == before
    assert not (live / island.LEDGER_RELPATH).exists()


def test_a_simple_name_still_reaches_status_and_promote_control(
    live: Path,
    islands: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control: validation must not refuse the names the tool needs."""
    isl = fork(live, islands, "ISL_OK")
    write(isl / "src" / "trading" / "claims.py", SIBLING_FIXED)
    monkeypatch.setattr(island, "ISLANDS_ROOT", islands)

    assert island.main(["status", "ISL_OK"]) == 0
    assert island.main(["promote", "ISL_OK", "--dry-run"]) == 0
    assert island.main(["list"]) == 0
