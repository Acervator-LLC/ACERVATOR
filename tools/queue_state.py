"""Report each standing-queue item's state FROM THE CODE, never from a table.

Why this exists. On 2026-08-16 the queue table said item 4 was open. The code
said otherwise: the delegate, both paint routines and the listing had all
shipped four days earlier. The table was read, believed and reported, and the
next unit was very nearly dispatched to build what already existed.

A written table is a claim about the tree at the moment somebody typed it. This
runs probes instead, so "what is the state of item N" is a MEASUREMENT.

Each probe reports the evidence it found, not a verdict alone. A probe that
finds nothing prints the pattern it searched for, so a zero can be told apart
from a probe pointed at the wrong place.

No subprocess and no shell: the scan is pure Python over the source tree, and
the remote list is read from .git/config. That keeps the tool usable where grep
is absent and leaves nothing for a shell to interpret.

    python -m tools.queue_state          # every item
    python -m tools.queue_state 19 20    # named items
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
    ".claude",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".venv",
    "node_modules",
    "build",
    "dist",
    "_archive",
}


def source_files(sub: str = "src") -> list[pathlib.Path]:
    """Every .py under sub, skipping generated and vendored trees."""
    base = ROOT / sub
    if not base.is_dir():
        return []
    out = []
    for path in sorted(base.rglob("*.py")):
        if SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        out.append(path)
    return out


def hits(needle: str, sub: str = "src") -> list[str]:
    """Every line containing needle, as 'relpath:line: text'."""
    found = []
    for path in source_files(sub):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle not in text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            if needle in line:
                found.append(f"{rel}:{number}: {line.strip()}")
    return found


def git_remotes() -> list[str]:
    """Remote names from .git/config, read directly rather than shelled out."""
    config = ROOT / ".git" / "config"
    if not config.is_file():
        return []
    names = []
    for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith('[remote "') and stripped.endswith('"]'):
            names.append(stripped[len('[remote "') : -2])
    return names


# Each entry: (number, title, [(label, needle)], how to read the result).
# A probe is a QUESTION, so the label says what a hit would mean.
PROBES: list[tuple[int, str, list[tuple[str, str]], str]] = [
    (
        4,
        "Tranche tracking under the parent + row painting",
        [
            ("extractor paint routine", "_paint_extractor_tranche_rows"),
            ("fold paint routine", "_paint_fold_tranche_row"),
            ("row border delegate", "_TrancheRowBorderDelegate"),
            ("delegate wired", "setItemDelegate"),
            # Named _cells, not _row. The first version of this probe searched
            # for `_compose_extractor_tranche_row` and reported 0 — which is
            # exactly why a probe prints the pattern it searched for. A wrong
            # needle and an absent feature look identical without it.
            ("row composer", "_compose_extractor_tranche_cells"),
        ],
        "all five present means the follow-up spec shipped",
    ),
    (
        6,
        "Distribution across Stack Tranches",
        [
            ("spread across ladder", "distribute_across"),
            ("per-rung allocation", "allocate_across_tranches"),
        ],
        "no hits means open",
    ),
    (
        13,
        "Profiler butterfly view + emitter coverage map",
        [
            ("butterfly", "butterfly"),
            ("call graph", "call_graph"),
            ("callee edges", "callee"),
            ("coverage map", "coverage_map"),
        ],
        "no hits means nothing built",
    ),
    (
        14,
        "Decouple stack SPAWN from stack USE",
        [
            ("stack_mode gate sites", "stack_mode"),
            ("spawn bypass", "bypass_stack"),
        ],
        "read the creation gate by hand; a count alone cannot say WHERE it gates",
    ),
    (
        15,
        "Compounding distribution modes equal/linear/quadratic",
        [
            ("mode enum", "DistributionMode"),
            ("mode field", "distribution_mode"),
        ],
        "the bare word quadratic is the SPACING enum, a different axis; do not count it",
    ),
    (
        17,
        "System Status tab",
        [
            ("tab class", "SystemStatusTab"),
            ("snake case", "system_status"),
        ],
        "System Status as free text also matches exchange API URLs; do not count it",
    ),
    (
        18,
        "History tab Gates column legibility",
        [
            ("item delegate anywhere", "QStyledItemDelegate"),
            ("gates cell render", "gates_cell"),
        ],
        "the queue note says the repo had NO delegate on 2026-08-11; if one exists it arrived since",
    ),
    (
        19,
        "Tranche Merge Secondary Rule (below exchange minimum)",
        [
            ("PRIMARY price merge", "_apply_merge_rule"),
            ("merge threshold", "MERGE_THRESHOLD"),
            ("size merge", "merge_below_minimum"),
            ("exchange minimum reader", "min_order_size"),
        ],
        "the primary is a PRICE merge; the secondary is a SIZE merge and is the open half",
    ),
    (
        20,
        "Wire credits when a tranche despawns on age",
        [
            ("per-bot credit pool", "_pending_wire_credits"),
            ("credit ledger", "pending_wire_ledger"),
            ("absorb into tranche", "_absorb_pending_wire_credits_into"),
            ("despawn setting", "tranche_despawn_days"),
        ],
        "the pool is a per-bot scalar so the pool cannot be orphaned; the open question is ABSORBED value on despawn",
    ),
]

GIT_ITEM = 16


def report(only: set[int]) -> int:
    scanned = len(source_files())
    print(f"queue state, measured from {ROOT.name} over {scanned} source files\n")
    for number, title, probes, how in PROBES:
        if only and number not in only:
            continue
        print(f"ITEM {number}  {title}")
        for label, needle in probes:
            found = hits(needle)
            if found:
                print(f"   {label:26} {len(found):>4} hit(s)   {found[0][:88]}")
            else:
                print(f"   {label:26}    0 hit(s)   (searched: {needle!r})")
        print(f"   READ AS: {how}\n")

    if not only or GIT_ITEM in only:
        remotes = git_remotes()
        print(f"ITEM {GIT_ITEM}  Upload project to GitHub")
        if remotes:
            for name in remotes:
                print(f"   remote configured: {name}")
        else:
            print("   remote     0 configured  (.git/config declares no [remote])")
        print(
            "   READ AS: no remote means not uploaded from this tree. "
            "Operator's call, never push unasked.\n"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "items",
        nargs="*",
        type=int,
        help="queue numbers to probe; default every known item",
    )
    args = parser.parse_args()
    known = {n for n, _, _, _ in PROBES} | {GIT_ITEM}
    unknown = [i for i in args.items if i not in known]
    if unknown:
        print(f"no probe defined for item(s) {unknown}. Known: {sorted(known)}")
        print(
            "A missing probe is not evidence of anything. Add one rather than "
            "reading the queue table."
        )
        return 2
    return report(set(args.items))


if __name__ == "__main__":
    sys.exit(main())
