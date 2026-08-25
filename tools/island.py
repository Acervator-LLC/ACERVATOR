"""Island manifests, staleness detection, and gated promotion to live.

An *island* is an isolated hard copy of the repo where work happens, so
the live tree is never edited directly. Promotion used to be a plain file
copy: last writer wins, silently. On 2026-08-10 two islands each held a
modified copy of `src/trading/bot_container.py`. One forked early and
carried a new method but lacked 22 later defect fixes; the other carried
the fixes but lacked the method. Two of those fixes were live-money
defects. The early island looked promotable. Promoting it would have
reverted both fixes and printed nothing.

That is a merge conflict. Git refuses these; copying files over the top
does not. This module restores the refusal.

The one rule that matters: a file is STALE when live changed after the
island forked. Promoting a stale file reverts whatever landed in the
meantime. `promote` refuses on any stale file, and it is ALL OR NOTHING —
it will not promote the clean files and leave the stale ones behind. A
half-applied change is worse than none.

Subcommands
-----------
new <name> --purpose TEXT --touches PATH [PATH ...]
    Hard-copy live to a new island and record base hashes for every `.py`
    file in live at fork time. Refuses if the island already exists.
status <name>
    What the island changed, what it added, and which of those live has
    moved under since the fork.
promote <name> [--dry-run]
    Refuse on any stale in-scope file, naming it and what diverged.
    Otherwise copy to live preserving each destination's line endings and
    append a ledger line.
list
    Every island under the islands root, with purpose, age, changed-file
    count and staleness.

Hashing normalises CRLF to LF before SHA-256, so a line-ending
difference alone is never seen as a change. Without that, every
promotion would look stale on Windows.

Every subcommand that takes a name validates it first. A name is a
simple directory name that lands DIRECTLY under the islands root and
nothing else. Windows path joining discards the left operand when the
right side is absolute, and walks upward on a dot-dot segment, so an
unchecked name addresses any directory on the machine — including the
live tree. The check runs before any copy, so a refused name creates
nothing at all.

Scope: only files under `src/` and `tests/` are ever written to live.
`tools/harness/`, `.claude/`, config files and the version banner are
protected — an island that changed one is refused outright rather than
silently skipped, because silent dropping is the failure mode this tool
exists to stop.

Known boundary: change detection covers `.py` files only, matching the
manifest. A non-Python file added under `src/` is not tracked and will
not be promoted. This is reported by `status` only insofar as it is
absent; it is a real limit, not an oversight.

Falsification — this module is wrong if a stale promotion reaches live
while it reports success; if it refuses a promotion where live did not
change since the fork; if a CRLF-versus-LF difference alone reads as a
change; if the ledger cannot reconstruct which island a live file came
from; or if any name that does not land directly under the islands root
creates, reads or writes a single byte.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = ".island.json"
LEDGER_RELPATH = "tools/.island_ledger.jsonl"


def _islands_root() -> Path:
    """Where islands are forked. DERIVED, never hardcoded.

    This was an absolute path to one machine's session scratchpad until
    2026-08-16. On the move to the GitHub repo it still pointed at the old
    tree, so every fork would have landed beside a repository that is no
    longer the one being worked on — silently, because a fork succeeds either
    way.

    Three properties matter and each is why this is not simply `Path.cwd()`:
      - OUTSIDE the repository, so an island is never committed by accident;
      - STABLE across runs, so `status` and `promote` find the same fork;
      - PER-REPOSITORY, so two checkouts do not share an island namespace.

    `ACERVATOR_ISLANDS_ROOT` overrides it for anyone who wants islands on a
    different disk.
    """
    override = os.environ.get("ACERVATOR_ISLANDS_ROOT")
    if override:
        return Path(override)
    repo_name = Path(__file__).resolve().parent.parent.name
    return Path(tempfile.gettempdir()) / "acervator_islands" / repo_name


ISLANDS_ROOT = _islands_root()

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "node_modules",
    }
)

PROMOTABLE_ROOTS = ("src/", "tests/")

PROTECTED_PREFIXES = ("tools/harness/", ".claude/")
PROTECTED_EXACT = frozenset(
    {
        "src/__init__.py",
        "main.py",
        "conftest.py",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
    }
)
PROTECTED_SUFFIXES = (
    ".toml",
    ".cfg",
    ".ini",
    ".yaml",
    ".yml",
    ".json",
)

# Verdict kinds.
CURRENT = "current"
CHANGED = "changed"
ADDED = "added"
LIVE_MOVED = "live-moved"

# Scope kinds.
PROMOTABLE = "promotable"
PROTECTED = "protected"
OUT_OF_SCOPE = "out-of-scope"

NAME_RULE = (
    "An island name must be a simple directory name that lands directly "
    "under the islands root. It may not be empty, be a single dot or a "
    "double dot, be made only of dots, contain a slash or a backslash or "
    "a colon, end in a dot or a space, or be an absolute path."
)


class IslandNameError(ValueError):
    """A name that does not designate a directory inside the root.

    Distinct from FileExistsError so a caller can tell "that name is not
    allowed" apart from "that island is already there".
    """


def _say(line: str = "") -> None:
    """Write one line to stdout."""
    sys.stdout.write(line + "\n")


def normalise(data: bytes) -> bytes:
    """Return `data` with CRLF collapsed to LF.

    Line endings are a transport detail. Two files that differ only in
    their endings are the same file, and must never read as a change.
    """
    return data.replace(b"\r\n", b"\n")


def hash_bytes(data: bytes) -> str:
    """Return the SHA-256 of `data` after line-ending normalisation."""
    return hashlib.sha256(normalise(data)).hexdigest()


def hash_file(path: Path) -> str | None:
    """Return the normalised hash of `path`, or None if unreadable.

    None means "no such file". A caller that treats None as "unchanged"
    would silently drop a file, so every caller compares None
    explicitly.
    """
    try:
        return hash_bytes(path.read_bytes())
    except OSError:
        return None


def _short(digest: str | None) -> str:
    """Return a 12-character prefix of a digest, or a dash for None."""
    return digest[:12] if digest else "-"


def iter_py_files(root: Path) -> Iterator[Path]:
    """Yield every `.py` file under `root`, skipping caches and islands.

    A nested directory carrying an island manifest is skipped, so an
    island that happens to live inside the tree never contributes its
    copy of a file to that tree's hashes.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIR_NAMES:
                    continue
                if (entry / MANIFEST_NAME).is_file():
                    continue
                stack.append(entry)
            elif entry.suffix == ".py":
                yield entry


def build_base_hashes(live_root: Path) -> dict[str, str]:
    """Return {relative posix path: normalised hash} for live's `.py`."""
    hashes: dict[str, str] = {}
    for path in iter_py_files(live_root):
        digest = hash_file(path)
        if digest is None:
            continue
        rel = path.relative_to(live_root).as_posix()
        hashes[rel] = digest
    return hashes


def scope_of(rel: str) -> str:
    """Classify `rel` as promotable, protected, or out of scope."""
    if rel in PROTECTED_EXACT:
        return PROTECTED
    if rel.startswith(PROTECTED_PREFIXES):
        return PROTECTED
    if rel.endswith(PROTECTED_SUFFIXES):
        return PROTECTED
    if rel.startswith(PROMOTABLE_ROOTS):
        return PROMOTABLE
    return OUT_OF_SCOPE


@dataclass
class Verdict:
    """One island file weighed against its fork base and current live."""

    rel: str
    kind: str
    stale: bool
    scope: str
    base_hash: str | None
    live_hash: str | None
    island_hash: str
    note: str = ""

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serialisable view of this verdict."""
        return {
            "path": self.rel,
            "kind": self.kind,
            "stale": self.stale,
            "scope": self.scope,
            "base_hash": self.base_hash,
            "live_hash": self.live_hash,
            "island_hash": self.island_hash,
        }


def _classify_one(
    rel: str,
    island_hash: str,
    base_hash: str | None,
    live_hash: str | None,
) -> Verdict:
    """Decide one file's kind and staleness from three hashes.

    The whole truth table lives here so it can be read at a glance:

    * island matches live now      -> already current, nothing to do
    * absent at fork, absent now   -> a clean addition
    * absent at fork, present now  -> live grew its own file: STALE
    * island untouched, live moved -> live is ahead; not ours to promote
    * island changed, live at base -> a clean change
    * island changed, live moved   -> the near-miss: STALE
    """
    scope = scope_of(rel)

    def make(kind: str, stale: bool, note: str) -> Verdict:
        """Build a verdict carrying the three hashes already in hand."""
        return Verdict(
            rel=rel,
            kind=kind,
            stale=stale,
            scope=scope,
            base_hash=base_hash,
            live_hash=live_hash,
            island_hash=island_hash,
            note=note,
        )

    if island_hash == live_hash:
        return make(CURRENT, False, "identical to live already")
    if base_hash is None:
        if live_hash is None:
            return make(ADDED, False, "new file, absent from live")
        return make(
            ADDED,
            True,
            "island adds this path but live has since created it",
        )
    if island_hash == base_hash:
        return make(
            LIVE_MOVED,
            False,
            "island did not touch it; live moved ahead",
        )
    if live_hash == base_hash:
        return make(CHANGED, False, "live still at fork base")
    return make(
        CHANGED,
        True,
        "live changed after this island forked",
    )


def classify(island_dir: Path, manifest: dict) -> list[Verdict]:
    """Weigh every `.py` file on the island against base and live."""
    live_root = Path(str(manifest["live_root"]))
    base: dict[str, str] = dict(manifest.get("base_hashes", {}))
    verdicts: list[Verdict] = []
    for path in iter_py_files(island_dir):
        rel = path.relative_to(island_dir).as_posix()
        island_hash = hash_file(path)
        if island_hash is None:
            continue
        verdicts.append(
            _classify_one(
                rel,
                island_hash,
                base.get(rel),
                hash_file(live_root / rel),
            )
        )
    verdicts.sort(key=lambda v: v.rel)
    return verdicts


def candidates(verdicts: list[Verdict]) -> list[Verdict]:
    """Return the verdicts that represent island work to promote."""
    return [v for v in verdicts if v.kind in (CHANGED, ADDED)]


def load_manifest(island_dir: Path) -> dict | None:
    """Return the island manifest, or None when there is not one.

    None means UNMANAGED. There is no recorded base, and a guessed base
    is exactly the near-miss this tool exists to prevent, so an
    unmanaged island is never promotable.
    """
    path = island_dir / MANIFEST_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    """Return the entries of `directory` that must not be copied."""
    base = Path(directory)
    skip = {name for name in names if name in SKIP_DIR_NAMES or name.endswith(".pyc")}
    for name in names:
        if (base / name / MANIFEST_NAME).is_file():
            skip.add(name)
    return skip


def _same_path(left: Path, right: Path) -> bool:
    """Return True when two paths name the same location.

    Windows compares paths without regard to case; POSIX compares with
    it. `os.path.normcase` is the one call that is correct on both.
    """
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _syntax_refusal(name: str) -> str | None:
    """Return why `name` is not a simple directory name, or None.

    These are the forms that the placement check below cannot catch on
    its own. A trailing separator, a trailing dot and a trailing space
    all resolve to a legitimate-looking child, because Windows drops
    them, so the name would then designate a directory it does not name.
    """
    checks = (
        (not name.strip(), "island name is empty"),
        ("/" in name or "\\" in name, "island name contains a path separator"),
        (":" in name, "island name contains a drive or stream marker"),
        (set(name) == {"."}, "island name is made only of dots"),
        (name.endswith((".", " ")), "island name ends in a dot or a space"),
    )
    for failed, reason in checks:
        if failed:
            return reason
    return None


def _placement_refusal(islands_root: Path, name: str) -> str | None:
    """Return why `name` lands outside the root, or None.

    This is the load-bearing check: whatever the name looks like, the
    directory it finally resolves to must be a DIRECT child of the
    islands root.
    """
    try:
        target = (islands_root / name).resolve()
        root = islands_root.resolve()
    except (OSError, ValueError):
        return "island name is not a usable path"
    if _same_path(target, root):
        return "island name resolves to the islands root itself"
    if _same_path(target.parent, root):
        return None
    return "island name does not land directly under the islands root"


def island_dir_for(islands_root: Path, name: str) -> Path:
    """Return the directory for island `name`, or refuse the name.

    Raises IslandNameError for any name that does not land directly
    under `islands_root`. Every entry point that accepts a name calls
    this BEFORE it reads, copies or writes anything, so a refused name
    leaves no partial tree behind.
    """
    reason = _syntax_refusal(name) or _placement_refusal(islands_root, name)
    if reason is not None:
        message = f"{reason}: {name!r}. {NAME_RULE}"
        raise IslandNameError(message)
    return islands_root / name


def create_island(
    live_root: Path,
    islands_root: Path,
    name: str,
    purpose: str,
    touches: list[str],
) -> Path:
    """Fork `live_root` into a new island and write its manifest.

    Raises IslandNameError if the name does not land directly under
    `islands_root`, before anything is read or copied. Raises
    FileExistsError if the island already exists. Overwriting one would
    destroy uncommitted work with no record.
    """
    island_dir = island_dir_for(islands_root, name)
    if island_dir.exists():
        raise FileExistsError(f"island already exists: {island_dir}")

    base_hashes = build_base_hashes(live_root)
    islands_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(live_root, island_dir, ignore=_copy_ignore, symlinks=True)

    manifest = {
        "name": name,
        "purpose": purpose,
        "created": datetime.now(timezone.utc).isoformat(),
        "live_root": str(live_root),
        "declared_files": [Path(t).as_posix() for t in touches],
        "base_hashes": base_hashes,
    }
    (island_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return island_dir


def dominant_eol(data: bytes) -> bytes:
    """Return the line ending that `data` mostly uses."""
    crlf = data.count(b"\r\n")
    lone_lf = data.count(b"\n") - crlf
    return b"\r\n" if crlf > lone_lf else b"\n"


def apply_eol(data: bytes, eol: bytes) -> bytes:
    """Return `data` rewritten to use `eol` throughout."""
    flat = normalise(data)
    if eol == b"\r\n":
        return flat.replace(b"\n", b"\r\n")
    return flat


def write_preserving_eol(source: Path, dest: Path) -> None:
    """Copy `source` to `dest`, keeping the destination's line endings.

    A promotion must not rewrite every line of a file just because the
    island was edited on a different platform. When `dest` does not yet
    exist there is nothing to preserve, so the source bytes stand.
    """
    payload = source.read_bytes()
    if dest.exists():
        payload = apply_eol(payload, dominant_eol(dest.read_bytes()))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)


def divergence(island_file: Path, live_file: Path) -> str:
    """Summarise how the island copy differs from live's current copy."""
    if not live_file.exists():
        return "absent from live"
    try:
        left = normalise(live_file.read_bytes()).decode("utf-8", "replace")
        right = normalise(island_file.read_bytes()).decode("utf-8", "replace")
    except OSError:
        return "unreadable"
    added = 0
    removed = 0
    for line in difflib.unified_diff(
        left.splitlines(),
        right.splitlines(),
        n=0,
        lineterm="",
    ):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return f"island differs from live by +{added}/-{removed} lines"


def append_ledger(live_root: Path, manifest: dict, promoted: list[Verdict]) -> Path:
    """Append one JSONL record of this promotion and return its path."""
    ledger = live_root / LEDGER_RELPATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "island": manifest.get("name"),
        "purpose": manifest.get("purpose"),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "forked_at": manifest.get("created"),
        "live_root": str(live_root),
        "files": [
            {"path": v.rel, "hash": v.island_hash, "kind": v.kind} for v in promoted
        ],
    }
    with ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return ledger


def _age(created: str) -> str:
    """Return a rough human age for an ISO timestamp."""
    try:
        then = datetime.fromisoformat(created)
    except (TypeError, ValueError):
        return "unknown"
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    seconds = int((datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 3600:
        return f"{max(seconds, 0) // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _describe(verdict: Verdict, island_dir: Path, live_root: Path) -> list[str]:
    """Return the report lines for one verdict."""
    lines = [f"  {verdict.rel}", f"      {verdict.note}"]
    lines.append(
        f"      base {_short(verdict.base_hash)}"
        f"  live {_short(verdict.live_hash)}"
        f"  island {_short(verdict.island_hash)}"
    )
    lines.append(
        "      " + divergence(island_dir / verdict.rel, live_root / verdict.rel)
    )
    return lines


def render_status(island_dir: Path) -> int:
    """Print what the island changed and added, and what went stale."""
    manifest = load_manifest(island_dir)
    if manifest is None:
        _say(f"{island_dir.name}: UNMANAGED — no {MANIFEST_NAME}.")
        _say("  No recorded fork base. Not promotable, and no base is guessed.")
        return 2
    live_root = Path(str(manifest["live_root"]))
    _say(f"island   {manifest.get('name')}")
    _say(f"purpose  {manifest.get('purpose')}")
    _say(
        f"forked   {manifest.get('created')}  ({_age(str(manifest.get('created')))} ago)"
    )
    _say(f"live     {live_root}")
    if not live_root.is_dir():
        _say("WARNING: live root no longer exists; staleness cannot be judged.")
        return 2

    verdicts = classify(island_dir, manifest)
    cands = candidates(verdicts)
    if not cands:
        _say("")
        _say("No island-side changes. Every file matches live: SUPERSEDED.")
        return 0

    for label, kind in (("CHANGED", CHANGED), ("ADDED", ADDED)):
        rows = [v for v in cands if v.kind == kind]
        if not rows:
            continue
        _say("")
        _say(f"{label} ({len(rows)}):")
        for verdict in rows:
            mark = "STALE  " if verdict.stale else "ok     "
            _say(f"  [{mark}] {verdict.scope:<12} {verdict.rel}")
            if verdict.stale:
                for line in _describe(verdict, island_dir, live_root)[1:]:
                    _say("  " + line)

    stale = [v for v in cands if v.stale and v.scope == PROMOTABLE]
    _say("")
    _say(
        f"{len(stale)} in-scope file(s) STALE. "
        f"{'Promotion will refuse.' if stale else 'Promotion may proceed.'}"
    )
    return 0


def _refuse_protected(protected: list[Verdict]) -> int:
    """Print the protected-path refusal and return its exit code."""
    _say(f"REFUSED: the island changed {len(protected)} protected file(s).")
    _say("")
    for verdict in protected:
        _say(f"  {verdict.rel}")
    _say("")
    _say("This tool promotes only src/ and tests/. It never writes")
    _say("tools/harness/, .claude/, a config file, or a version banner.")
    _say("Nothing was promoted. Move that work out of the island, or land")
    _say("it deliberately by hand with the operator watching.")
    return 1


def _refuse_stale(
    stale: list[Verdict],
    island_dir: Path,
    live_root: Path,
) -> int:
    """Print the staleness refusal and return its exit code."""
    _say(f"REFUSED: {len(stale)} file(s) went STALE — live changed after")
    _say("this island forked. Promoting them would revert whatever landed")
    _say("in the meantime.")
    _say("")
    for verdict in stale:
        for line in _describe(verdict, island_dir, live_root):
            _say(line)
        _say("")
    _say("Nothing was promoted. This is ALL OR NOTHING: a half-applied")
    _say("change is worse than none, so the clean files stayed behind too.")
    _say("")
    _say("REBASE this island onto current live: fork a fresh island from")
    _say("live now, re-apply this work onto it, and promote that. Do not")
    _say("hand-copy around this tool, and do not edit the tool.")
    return 1


def promote_island(island_dir: Path, dry_run: bool = False) -> int:
    """Promote an island to live, or refuse. Returns an exit code.

    Refuses on any protected path and on any stale in-scope file, and
    promotes nothing at all when it refuses.
    """
    manifest = load_manifest(island_dir)
    if manifest is None:
        _say(f"REFUSED: {island_dir.name} is UNMANAGED — no {MANIFEST_NAME}.")
        _say("There is no recorded fork base, so staleness cannot be judged,")
        _say("and a guessed base is exactly the defect this tool prevents.")
        _say("Nothing was promoted.")
        return 2
    live_root = Path(str(manifest["live_root"]))
    if not live_root.is_dir():
        _say(f"REFUSED: live root missing: {live_root}")
        return 2

    cands = candidates(classify(island_dir, manifest))
    protected = [v for v in cands if v.scope == PROTECTED]
    in_scope = [v for v in cands if v.scope == PROMOTABLE]
    skipped = [v for v in cands if v.scope == OUT_OF_SCOPE]
    stale = [v for v in in_scope if v.stale]

    if protected:
        return _refuse_protected(protected)
    if stale:
        return _refuse_stale(stale, island_dir, live_root)

    if skipped:
        _say(f"NOT PROMOTED — outside src/ and tests/ ({len(skipped)}):")
        for verdict in skipped:
            _say(f"  {verdict.rel}")
        _say("")

    if not in_scope:
        _say("Nothing to promote: no in-scope changes on this island.")
        return 0

    declared = set(manifest.get("declared_files") or [])
    undeclared = [v.rel for v in in_scope if v.rel not in declared]

    _say(
        f"{'WOULD PROMOTE' if dry_run else 'PROMOTING'} "
        f"{len(in_scope)} file(s) to {live_root}:"
    )
    for verdict in in_scope:
        _say(f"  {verdict.kind:<8} {verdict.rel}")
    if undeclared:
        _say("")
        _say(f"NOTE: {len(undeclared)} file(s) were not declared at fork time:")
        for rel in undeclared:
            _say(f"  {rel}")

    if dry_run:
        _say("")
        _say("Dry run: live was not touched.")
        return 0

    for verdict in in_scope:
        write_preserving_eol(island_dir / verdict.rel, live_root / verdict.rel)
    ledger = append_ledger(live_root, manifest, in_scope)
    _say("")
    _say(f"Promoted {len(in_scope)} file(s). Ledger: {ledger}")
    return 0


def list_islands(islands_root: Path) -> int:
    """Print every island under `islands_root` with its state."""
    if not islands_root.is_dir():
        _say(f"No islands root at {islands_root}")
        return 2
    entries = sorted(p for p in islands_root.iterdir() if p.is_dir())
    if not entries:
        _say("No islands.")
        return 0

    managed = 0
    for island_dir in entries:
        manifest = load_manifest(island_dir)
        if manifest is None:
            _say(f"  UNMANAGED   {island_dir.name}")
            _say("              no manifest; not promotable, base not guessed")
            continue
        managed += 1
        _summarise_managed(island_dir, manifest)

    _say("")
    _say(
        f"{len(entries)} island(s): {managed} managed, "
        f"{len(entries) - managed} unmanaged."
    )
    return 0


def _summarise_managed(island_dir: Path, manifest: dict) -> None:
    """Print the one-island summary for a managed island."""
    live_root = Path(str(manifest["live_root"]))
    purpose = str(manifest.get("purpose") or "")
    age = _age(str(manifest.get("created")))
    if not live_root.is_dir():
        _say(f"  NO-LIVE     {island_dir.name}  ({age} old)")
        _say(f"              live root missing: {live_root}")
        return
    cands = candidates(classify(island_dir, manifest))
    stale = [v for v in cands if v.stale and v.scope == PROMOTABLE]
    if not cands:
        state = "SUPERSEDED"
    elif stale:
        state = "STALE"
    else:
        state = "READY"
    _say(
        f"  {state:<11} {island_dir.name}  ({age} old, "
        f"{len(cands)} changed, {len(stale)} stale)"
    )
    if purpose:
        _say(f"              {purpose}")


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the four subcommands."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.island",
        description="Fork, inspect and promote development islands.",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    new = subs.add_parser("new", help="fork live into a new island")
    new.add_argument("name")
    new.add_argument("--purpose", required=True)
    new.add_argument("--touches", nargs="+", default=[])

    status = subs.add_parser("status", help="show island changes and staleness")
    status.add_argument("name")

    promote = subs.add_parser("promote", help="promote an island to live")
    promote.add_argument("name")
    promote.add_argument("--dry-run", action="store_true")

    subs.add_parser("list", help="list every island")
    return parser


def _refuse_name(exc: IslandNameError, islands_root: Path) -> int:
    """Print the rejected-name refusal and return its exit code."""
    _say(f"REFUSED: {exc}")
    _say(f"Islands root: {islands_root}")
    _say("Nothing was created, inspected or promoted.")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return an exit code."""
    args = build_parser().parse_args(argv)
    live_root = Path(__file__).resolve().parents[1]

    if args.command == "list":
        return list_islands(ISLANDS_ROOT)

    try:
        island_dir = island_dir_for(ISLANDS_ROOT, args.name)
    except IslandNameError as exc:
        return _refuse_name(exc, ISLANDS_ROOT)

    if args.command == "new":
        try:
            island = create_island(
                live_root,
                ISLANDS_ROOT,
                args.name,
                args.purpose,
                args.touches,
            )
        except FileExistsError as exc:
            _say(f"REFUSED: {exc}")
            _say("Pick another name. An existing island is never overwritten.")
            return 1
        _say(f"Forked {live_root}")
        _say(f"    -> {island}")
        _say(f"Purpose: {args.purpose}")
        return 0
    if args.command == "status":
        return render_status(island_dir)
    return promote_island(island_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
