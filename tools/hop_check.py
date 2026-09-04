"""Reports whether the HOP handoff has drifted from the repository.

Drift is the commits landed since the HOP file was last written past
`STALE_AFTER`, plus every `TRACKED` path it cites that is gone and every commit
it names that no longer resolves. A path listed under `ABSENT_HEADING` is
excluded. Exit 1 means drift.
"""

# ruff: noqa: S603
# `git` resolves through `shutil.which`, and every argv here carries a variable.

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STALE_AFTER = 15
ABSENT_HEADING = "## CITED AS ABSENT"
TRACKED = r"`((?:src|tests|tools|docs|desktop|dev_harness|harness_fixtures|\.github)/[\w./-]+)`"


def git(*args: str) -> str:
    """Runs a git command in the repository and returns its stdout, stripped.

    Resolves git to a full path first, mirroring tools/migration_verifier.py.
    """
    exe = shutil.which("git")
    if exe is None:
        return ""
    done = subprocess.run(
        [exe, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done.stdout.strip()


def newest_hop() -> pathlib.Path | None:
    """Returns the highest-numbered ACERVATOR_HOP*.md at the repository root."""
    found = sorted(ROOT.glob("ACERVATOR_HOP*.md"), key=lambda p: p.stem)
    return found[-1] if found else None


def declared_absent(text: str) -> set[str]:
    """Returns the paths the handoff declares it names only to say they are gone."""
    head = text.find(ABSENT_HEADING)
    if head < 0:
        return set()
    rest = text[head + len(ABSENT_HEADING) :]
    stop = rest.find("\n## ")
    return set(re.findall(TRACKED, rest if stop < 0 else rest[:stop]))


def main() -> int:
    """Prints the drift report and returns 1 if the handoff needs rewriting."""
    hop = newest_hop()
    if hop is None:
        print("NO HOP FILE at the repository root. A fresh clone gets no orientation.")
        return 1

    print("handoff: " + hop.name)
    last_touch = git("log", "-1", "--format=%H", "--", hop.name)
    if not last_touch:
        print("  it is untracked, so no clone gets it")
        return 1

    behind = git("rev-list", "--count", last_touch + "..HEAD")
    count = int(behind) if behind.isdigit() else 0
    print("  commits since it was last written   : " + str(count))

    text = hop.read_text(encoding="utf-8", errors="replace")
    excused = declared_absent(text)
    missing = sorted(
        cited
        for cited in set(re.findall(TRACKED, text))
        if cited not in excused and not (ROOT / cited).exists()
    )
    unresolved = sorted(
        sha
        for sha in set(re.findall(r"`([0-9a-f]{7,40})`", text))
        if not git("cat-file", "-t", sha)
    )

    print("  declared absent on purpose          : " + str(len(excused)))
    print("  cited paths that are gone anyway    : " + str(len(missing)))
    for gone in missing:
        print("      " + gone)
    print("  cited commits that do not resolve   : " + str(len(unresolved)))
    for sha in unresolved:
        print("      " + sha)

    stale = count >= STALE_AFTER
    if stale:
        print()
        print("DRIFTED. " + str(count) + " commits since " + hop.name + " was written,")
        print(
            "at or past the threshold of "
            + str(STALE_AFTER)
            + ". Rewrite what moved; never append."
        )
    if missing or unresolved:
        print()
        print(
            "It cites things that are gone. Every claim must be checkable in one command."
        )

    return 1 if (stale or missing or unresolved) else 0


if __name__ == "__main__":
    sys.exit(main())
