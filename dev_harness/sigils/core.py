"""`judge` runs a `Sigil` through three tiers, and `main` prints one row per input."""

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Literal, NamedTuple


class Flag(Enum):
    """`FLAGS` holds the side, when and follow-on rule of each `Flag` name."""

    BLOCK = auto()
    HOLD = auto()
    FIX = auto()
    OPTIMIZE = auto()
    PASS = auto()


FLAGS: dict[Flag, dict[str, str]] = {
    Flag.BLOCK: {
        "side": "input",
        "when": "a tier 1 or tier 2 refusal",
        "follows": "the work does not start",
    },
    Flag.HOLD: {
        "side": "output",
        "when": "a fault in application source code",
        "follows": "the merge waits until it is fixed",
    },
    Flag.FIX: {
        "side": "output",
        "when": "a fault anywhere else, such as a document",
        "follows": "the merge proceeds, and the fault is fixed at once",
    },
    Flag.OPTIMIZE: {
        "side": "output",
        "when": "a named optimization rule fires",
        "follows": "the merge proceeds",
    },
    Flag.PASS: {
        "side": "output",
        "when": "the output is valid",
        "follows": "nothing further",
    },
}

GATED = frozenset({Flag.BLOCK, Flag.HOLD})

APPLICATION_SOURCE = ("src", "desktop", "main.py")

DATA_TYPE = "tier 1 data type"
CONTENT = "tier 2 content compatibility"
FUNCTIONS = "tier 3 required processing functions"
TIER_NAMES = (DATA_TYPE, CONTENT, FUNCTIONS)


class Reading(NamedTuple):
    """Tier 3 `output` and `reason`; `holds` False keeps `Flag.HOLD` off this fault."""

    output: str
    reason: str
    holds: bool


OutputFlag = Literal[Flag.PASS, Flag.FIX, Flag.OPTIMIZE, Flag.BLOCK]
DataType = Callable[[str], str | None]
Content = Callable[[str, Path], str | None]
Functions = Callable[[str, Path], tuple[str, str] | Reading]
FaultFile = Callable[[str, Path], Path | None]
TierCard = Mapping[str, object]


@dataclass(frozen=True)
class FlagRow:
    """Output `flag`; `holds_in_source` makes it `Flag.HOLD` in application source."""

    flag: OutputFlag
    holds_in_source: bool = False


@dataclass(frozen=True)
class Sigil:
    """A card as data, with tiers 1, 2 and 3 as `data_type`, `content`, `functions`."""

    name: str
    edition: int
    owner: str
    input_form: str
    settings: Mapping[str, str]
    tiers: tuple[TierCard, TierCard, TierCard]
    outputs: Mapping[str, FlagRow]
    refusal: str
    follows: Mapping[Flag, str]
    readers: Mapping[str, Callable[..., object]]
    data_type: DataType
    content: Content
    functions: Functions
    fault_file: FaultFile | None = None


@dataclass(frozen=True)
class Verdict:
    """One input's `output`, `reason` naming its tier, `tier` number and `flag`."""

    output: str
    reason: str
    tier: int
    flag: Flag


def flag_of(sigil: Sigil, output: str, *, in_source: bool) -> Flag:
    """Return the flag of `output`; `Flag.HOLD` when `in_source` and its row holds."""
    row = sigil.outputs[output]
    return Flag.HOLD if in_source and row.holds_in_source else row.flag


def judge(sigil: Sigil, text: str, root: Path, *, in_source: bool) -> Verdict:
    """Run `text` through tiers 1, 2 and 3 of `sigil`, stopping at the first refusal."""
    fault = sigil.data_type(text)
    if fault:
        return Verdict(sigil.refusal, f"{DATA_TYPE}: {fault}", 1, Flag.BLOCK)
    fault = sigil.content(text, root)
    if fault:
        return Verdict(sigil.refusal, f"{CONTENT}: {fault}", 2, Flag.BLOCK)
    reading = sigil.functions(text, root)
    holds = not isinstance(reading, Reading) or reading.holds
    output, reason = reading[0], reading[1]
    flag = flag_of(sigil, output, in_source=in_source and holds)
    return Verdict(output, f"{FUNCTIONS}: {reason}", 3, flag)


def render_card(sigil: Sigil) -> dict[str, object]:
    """Return `sigil` as JSON data, with both flags of each output."""
    outputs = {
        output: {
            "elsewhere": flag_of(sigil, output, in_source=False),
            "application source": flag_of(sigil, output, in_source=True),
        }
        for output in sigil.outputs
    }
    given = {Flag.BLOCK} | {flag for row in outputs.values() for flag in row.values()}
    flags = {
        flag.name: {
            **FLAGS[flag],
            "follows": sigil.follows.get(flag, FLAGS[flag]["follows"]),
        }
        for flag in Flag
        if flag in given
    }
    return {
        "sigil": sigil.name,
        "edition": sigil.edition,
        "owner": sigil.owner,
        "input": sigil.input_form,
        "settings": {**sigil.settings, "application_source": list(APPLICATION_SOURCE)},
        "tiers": [
            {"name": name, **tier}
            for name, tier in zip(TIER_NAMES, sigil.tiers, strict=True)
        ],
        "outputs": {
            output: {place: flag.name for place, flag in row.items()}
            for output, row in outputs.items()
        },
        "refusal": {"verdict": sigil.refusal, "flag": Flag.BLOCK.name},
        "flags": flags,
        "readers": {
            kind: reader.__name__ for kind, reader in sorted(sigil.readers.items())
        },
    }


def in_application_source(path: Path, root: Path, source: Sequence[str]) -> bool:
    """Report whether `path` sits inside `root`, at or under one `source` entry."""
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return False
    prefixes = (tuple(entry.split("/")) for entry in source)
    return any(parts[: len(prefix)] == prefix for prefix in prefixes)


def named_file(
    text: str, root: Path, data_type: DataType, separator: str
) -> Path | None:
    """Return the file `text` names under `root`, or None if `data_type` refuses it."""
    if data_type(text):
        return None
    path = text.partition(separator)[0]
    return root.joinpath(*path.split("/"))


def tool_text(output: str | bytes) -> str:
    """Return a tool's `output` as text: decoded as UTF-8 when bytes, and stripped."""
    if isinstance(output, bytes):
        output = output.decode("utf-8", "replace")
    return output.strip()


def fault_place(sigil: Sigil, text: str, root: Path, listed: Path) -> Path:
    """Return the file `sigil.fault_file` names for `text`, else `listed`."""
    named = sigil.fault_file(text, root) if sigil.fault_file else None
    return listed if named is None else named


def repository_root(start: Path) -> Path | None:
    """Return the nearest folder at or above `start` that holds `.git`, or None."""
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None


def main(sigil: Sigil, argv: list[str] | None = None) -> int:
    """Print `render_card`, or one `judge` row per input; `GATED` decides --gate."""
    parser = argparse.ArgumentParser(
        description=f"Read one {sigil.name}@{sigil.edition} input per line.",
    )
    parser.add_argument("file", type=Path, nargs="?", help="one input per line")
    parser.add_argument(
        "--root",
        type=Path,
        help="the tree the inputs name; "
        "default: the repository holding the working folder",
    )
    parser.add_argument("--card", action="store_true", help="print the card as JSON")
    parser.add_argument(
        "--gate",
        action="store_true",
        help="exit 1 only when an input reads "
        + " or ".join(sorted(flag.name for flag in GATED)),
    )
    parser.add_argument(
        "--source",
        action="append",
        help="a folder or file under --root that holds application source; "
        "repeat for more; default: " + ", ".join(APPLICATION_SOURCE),
    )
    args = parser.parse_args(argv)
    if args.card:
        print(json.dumps(render_card(sigil), indent=2))
        return 0
    if args.file is None:
        parser.error("an input file is required unless --card is given")
    root = args.root if args.root is not None else repository_root(Path.cwd())
    if root is None:
        print(
            "no folder holding .git at or above the working folder; pass --root",
            file=sys.stderr,
        )
        return 1
    if not root.is_dir():
        print(f"--root is not a folder: {root}", file=sys.stderr)
        return 1
    try:
        lines = args.file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"cannot read {args.file}: {exc}", file=sys.stderr)
        return 1
    source = tuple(args.source) if args.source else APPLICATION_SOURCE
    flags = []
    for number, raw in enumerate(lines, start=1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        place = fault_place(sigil, text, root, args.file)
        in_source = in_application_source(place, root, source)
        verdict = judge(sigil, text, root, in_source=in_source)
        flags.append(verdict.flag)
        row = {
            "line": number,
            "input": text,
            "verdict": verdict.output,
            "reason": verdict.reason,
            "tier": verdict.tier,
            "flag": verdict.flag.name,
        }
        print(json.dumps(row))
    if not flags:
        print(f"no input in {args.file}", file=sys.stderr)
        return 1
    if args.gate:
        return 1 if GATED.intersection(flags) else 0
    return 0 if all(flag is Flag.PASS for flag in flags) else 1
