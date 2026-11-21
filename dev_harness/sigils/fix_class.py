"""`FOLLOW_ON` names each fix class's follow-on rule; `follow_on` applies ruff's safe fixes and runs `judge` again."""

import argparse
import difflib
import importlib
import json
import re
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType

from .coding_input import SEPARATOR, locate
from .core import (
    APPLICATION_SOURCE,
    FLAGS,
    Flag,
    Verdict,
    in_application_source,
    judge,
    repository_root,
    tool_text,
)
from .ruff_rules import ToolFault, _ruff, rule_page

FOLLOW_ON = {
    "always": "apply ruff's fix where ruff marks it safe, and read the file again",
    "sometimes": "the same, where ruff offers a safe fix for that line",
    "none": "a unit of work, with the rule's published corrected form",
}
BY_FIX_CLASS = "; by fix class: " + "; ".join(
    f"{fix} -> {rule}" for fix, rule in FOLLOW_ON.items()
)

RUFF_SIGILS = {
    "CODE.LOOP": "code_loop",
    "CODE.IMPORT": "code_import",
    "CODE.FLOW": "code_flow",
    "CODE.VARIABLE": "code_variable",
    "CODE.COLLECTION": "code_collection",
    "CODE.OPTIMIZE": "code_optimize",
}
OWN_ATTRIBUTE = "OWN_RULES"
ROUND_LIMIT = 2
COPY_PREFIX = "follow_on_"
FORCED_SAFE = "linter.safety_table.forced_safe = ["
PASSED = "the reading passes"
REFUSED = "the sigil refuses the input"
UNCHANGED = "a round changes no byte"
OUTSIDE = "ruff's fix changes a line outside the symbol"
LIMIT = "the round limit is reached"
ENDS = frozenset({Flag.PASS, Flag.BLOCK})
STATED = {Flag.OPTIMIZE: FLAGS[Flag.OPTIMIZE]["follows"]}
CARD: dict[str, object] = {
    "house": "coding",
    "edition": 1,
    "owner": "coding",
    "sigils": sorted(RUFF_SIGILS),
    "follow_on": FOLLOW_ON,
    "round_limit": ROUND_LIMIT,
    "stops": [PASSED, REFUSED, UNCHANGED, OUTSIDE, LIMIT],
    "own_rules": f"each rule a sigil module's {OWN_ATTRIBUTE} holds: no round passes "
    "it to ruff, and its corrected form comes from that module",
    "command": "python -m dev_harness.sigils.fix_class <sigil> <input>",
}

_FINDING_RE = re.compile(
    r"\b([A-Z]+[0-9]+) [a-z0-9-]+ line [0-9]+ fix (?:always|sometimes|none)\b"
)
_CODE_RE = re.compile(r"\(([A-Z]+[0-9]+)\)")


@dataclass(frozen=True)
class FollowOn:
    """One `follow_on` run: codes fixed per round, `stop`, last `verdict`, `corrected` forms, `forced` codes, `change`, `written`, `stated` text."""

    rounds: tuple[tuple[str, ...], ...]
    stop: str
    verdict: Verdict
    corrected: dict[str, str]
    forced: tuple[str, ...]
    change: str
    written: bool
    stated: str = ""


def reading_codes(verdict: Verdict) -> tuple[str, ...]:
    """Return each rule code the first line of `verdict.reason` names, or raise `ToolFault` when none."""
    first = verdict.reason.partition("\n")[0]
    codes = tuple(dict.fromkeys(_FINDING_RE.findall(first)))
    if not codes:
        message = f"the {verdict.output} reading names no ruff rule"
        raise ToolFault(message)
    return codes


def _preview(module: ModuleType, code: str) -> bool:
    """Return the preview flag `module` gives `code`: outside `STABLE` when it has one, else any `PREVIEW`."""
    stable = getattr(module, "STABLE", None)
    return code not in stable if stable is not None else bool(module.PREVIEW)


def _fixed(
    source: bytes, folder: Path, codes: Sequence[str], module: ModuleType
) -> bytes:
    """Return `source` after ruff's safe fixes of `codes`, run from `folder`, one call per preview flag."""
    for preview in (False, True):
        group = [code for code in codes if _preview(module, code) is preview]
        if not group:
            continue
        source = _ruff(
            "ruff check --fix-only",
            [
                "check",
                "--no-cache",
                "--fix-only",
                "--no-unsafe-fixes",
                *(["--preview"] if preview else []),
                "--select",
                ",".join(group),
                "-",
            ],
            source=source,
            folder=folder,
        )
    return source


def _forced_safe(file: Path) -> frozenset[str]:
    """Return each rule code ruff's settings for `file` force safe, or raise `ToolFault` without `FORCED_SAFE`."""
    printed = tool_text(
        _ruff(
            "ruff check --show-settings",
            ["check", "--show-settings", file.name],
            folder=file.parent,
        )
    )
    if FORCED_SAFE not in printed:
        message = f"ruff check --show-settings printed no {FORCED_SAFE}"
        raise ToolFault(message)
    return frozenset(
        _CODE_RE.findall(printed.partition(FORCED_SAFE)[2].partition("]")[0])
    )


def _outside(before: bytes, after: bytes, span: tuple[int, int]) -> bool:
    """Report whether `after` changes a line of `before` outside the one-based `span`."""
    first, last = span
    matcher = difflib.SequenceMatcher(
        None, before.splitlines(), after.splitlines(), autojunk=False
    )
    for tag, start, end, _new_start, _new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        low, high = (start, start + 1) if tag == "insert" else (start + 1, end)
        if low < first or high > last:
            return True
    return False


def _corrected(code: str, module: ModuleType) -> str:
    """Return rule `code`'s corrected form from `module`'s `OWN_ATTRIBUTE` rules or `rule_page`, or the `ToolFault`."""
    own = getattr(module, OWN_ATTRIBUTE, {})
    if code in own:
        return str(own[code].page.corrected)
    try:
        return rule_page(code).corrected
    except ToolFault as exc:
        return str(exc)


def _rounds(
    module: ModuleType,
    copied: str,
    root: Path,
    first: Verdict,
    *,
    in_source: bool,
    forced: frozenset[str],
    limit: int,
) -> tuple[list[tuple[str, ...]], str, Verdict]:
    """Return the codes fixed per round, the stop and the last `judge` verdict of the copy `copied` names."""
    verdict = first
    rounds: list[tuple[str, ...]] = []
    narrowed = bool(copied.partition(SEPARATOR)[1])
    own = getattr(module, OWN_ATTRIBUTE, {})
    while len(rounds) < limit:
        located = locate(copied, root)
        if isinstance(located, str):
            message = f"{copied}: {located}, after a round"
            raise ToolFault(message)
        file, before, span = located
        codes = tuple(
            code
            for code in reading_codes(verdict)
            if code not in forced and code not in own
        )
        rounds.append(codes)
        after = _fixed(before, file.parent, codes, module) if codes else before
        if after == before:
            return rounds, UNCHANGED, verdict
        if narrowed and _outside(before, after, span):
            return rounds, OUTSIDE, verdict
        file.write_bytes(after)
        verdict = judge(module.SIGIL, copied, root, in_source=in_source)
        if verdict.flag in ENDS:
            return rounds, PASSED if verdict.flag is Flag.PASS else REFUSED, verdict
    return rounds, LIMIT, verdict


def follow_on(
    name: str,
    text: str,
    root: Path,
    *,
    write: bool = False,
    limit: int = ROUND_LIMIT,
    source: Sequence[str] = APPLICATION_SOURCE,
) -> FollowOn:
    """Judge `text` with sigil `name`, fix a copy beside its file until a stop, and write only when `write`."""
    module = importlib.import_module(f".{RUFF_SIGILS[name]}", __package__)
    sigil = module.SIGIL
    named = sigil.fault_file(text, root) if sigil.fault_file else None
    in_source = named is not None and in_application_source(named, root, source)
    verdict = judge(sigil, text, root, in_source=in_source)
    if verdict.flag in ENDS:
        stop = PASSED if verdict.flag is Flag.PASS else REFUSED
        return FollowOn((), stop, verdict, {}, (), "", written=False)
    stated = STATED.get(verdict.flag, "")
    located = locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, original, _span = located
    path, separator, symbol = text.partition(SEPARATOR)
    with tempfile.TemporaryDirectory(prefix=COPY_PREFIX, dir=file.parent) as folder:
        copy = Path(folder) / file.name
        copy.write_bytes(original)
        copied = (PurePosixPath(path).parent / copy.parent.name / file.name).as_posix()
        forced = _forced_safe(copy)
        rounds, stop, verdict = _rounds(
            module,
            copied + separator + symbol,
            root,
            verdict,
            in_source=in_source,
            forced=forced,
            limit=limit,
        )
        final = copy.read_bytes()
    corrected = (
        {}
        if verdict.flag in ENDS
        else {code: _corrected(code, module) for code in reading_codes(verdict)}
    )
    change = "".join(
        difflib.unified_diff(
            original.decode("utf-8", "replace").splitlines(keepends=True),
            final.decode("utf-8", "replace").splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )
    written = write and final != original
    if written:
        file.write_bytes(final)
    return FollowOn(
        tuple(rounds),
        stop,
        verdict,
        corrected,
        tuple(sorted(forced)),
        change,
        written,
        stated,
    )


def main(argv: list[str] | None = None) -> int:
    """Print `CARD` with --card, else one `follow_on` run as JSON; exit 0 only on `Flag.PASS`."""
    parser = argparse.ArgumentParser(
        description="Apply ruff's safe fixes to one input of a ruff sigil until a stop.",
    )
    parser.add_argument(
        "sigil", nargs="?", choices=sorted(RUFF_SIGILS), help="the sigil to judge with"
    )
    parser.add_argument(
        "input", nargs="?", help="one input line: <path>, or <path>, in <symbol>"
    )
    parser.add_argument("--card", action="store_true", help="print the card as JSON")
    parser.add_argument(
        "--root",
        type=Path,
        help="the tree the input names; default: the repository holding the working folder",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the fixed file over the named file; without it, only a copy changes",
    )
    parser.add_argument(
        "--source",
        action="append",
        help="a folder or file under --root that holds application source; "
        "repeat for more; default: " + ", ".join(APPLICATION_SOURCE),
    )
    args = parser.parse_args(argv)
    if args.card:
        print(json.dumps(CARD, indent=2))
        return 0
    if args.sigil is None or args.input is None:
        parser.error("a sigil and an input are required unless --card is given")
    root = args.root if args.root is not None else repository_root(Path.cwd())
    if root is None or not root.is_dir():
        print(
            "no --root folder, and no folder holding .git above this one",
            file=sys.stderr,
        )
        return 1
    source = tuple(args.source) if args.source else APPLICATION_SOURCE
    try:
        result = follow_on(
            args.sigil, args.input, root, write=args.write, source=source
        )
    except ToolFault as exc:
        print(f"ruff did not run: {exc}", file=sys.stderr)
        return 1
    row = {
        "sigil": args.sigil,
        "input": args.input,
        "rounds": [list(codes) for codes in result.rounds],
        "stop": result.stop,
        "verdict": result.verdict.output,
        "flag": result.verdict.flag.name,
        "reason": result.verdict.reason,
        "corrected": result.corrected,
        "stated": result.stated,
        "forced_safe": list(result.forced),
        "change": result.change,
        "written": result.written,
    }
    print(json.dumps(row, indent=2))
    return 0 if result.verdict.flag is Flag.PASS else 1


if __name__ == "__main__":
    sys.exit(main())
