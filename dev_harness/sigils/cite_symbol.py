"""`SIGIL` is CITE.SYMBOL on the `core` card; `resolve_citation` runs one citation."""

import sys
from pathlib import Path

from .citation import (
    DATA_TYPE_REJECTS,
    NOT_GROUNDED,
    READERS,
    REJECTED,
    RESOLVED,
    SEARCH_NOT_GROUNDED,
    SEARCH_RESOLVED,
    SEARCH_RUNS,
    SETTINGS,
    data_type_fault,
    definition_verdict,
    file_type,
)
from .core import Flag, FlagRow, Sigil, Verdict, judge, main

OUTSIDE_ROOT = "path outside the target tree"
NO_READER = f"file type other than {' or '.join(sorted(READERS))}"


def _content_fault(citation: str, root: Path) -> str | None:
    """Return the tier 2 reason the `citation` path fails under `root`, or None."""
    path = citation.split(SETTINGS["separator"], 1)[0]
    target = root.joinpath(*path.split("/")).resolve()
    if not target.is_relative_to(root.resolve()):
        return OUTSIDE_ROOT
    if file_type(path) not in READERS:
        return NO_READER
    return None


SIGIL = Sigil(
    name="CITE.SYMBOL",
    edition=3,
    owner="truth",
    input_form=f"one line: <path>{SETTINGS['separator']}<symbol>",
    settings=SETTINGS,
    tiers=(
        {
            "accepts": "a relative path in forward slashes and name characters, "
            "and a dotted symbol of identifiers",
            "rejects": DATA_TYPE_REJECTS,
        },
        {
            "accepts": "a path inside the target tree, of a file type in readers",
            "rejects": [OUTSIDE_ROOT, NO_READER],
        },
        {
            "runs": SEARCH_RUNS,
            "not_grounded": SEARCH_NOT_GROUNDED,
            "resolved": SEARCH_RESOLVED,
        },
    ),
    outputs={
        RESOLVED: FlagRow(Flag.PASS),
        NOT_GROUNDED: FlagRow(Flag.FIX, holds_in_source=True),
    },
    refusal=REJECTED,
    follows={
        Flag.FIX: "find where the symbol lives now, rewrite the citation, "
        "read it again",
    },
    readers=READERS,
    data_type=data_type_fault,
    content=_content_fault,
    functions=definition_verdict,
)


def resolve_citation(citation: str, root: Path, *, in_source: bool = False) -> Verdict:
    """Return the `judge` verdict of `SIGIL` for `citation` under `root`."""
    return judge(SIGIL, citation, root, in_source=in_source)


if __name__ == "__main__":
    sys.exit(main(SIGIL))
