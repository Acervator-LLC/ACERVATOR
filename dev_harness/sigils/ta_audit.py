"""`SIGIL` is TA.AUDIT on the `core` card, using the `CITE_SYMBOL` citation rules."""

import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .cite_symbol import NOT_GROUNDED, REJECTED, RESOLVED
from .cite_symbol import SIGIL as CITE_SYMBOL
from .core import Flag, FlagRow, Sigil, main

CLEAN = "CLEAN"
DIRECTION = "DIRECTION"
SIGNAL = "SIGNAL"
CONFIDENCE = "CONFIDENCE"
DOCUMENTATION = "DOCUMENTATION"

SETTINGS: dict[str, str] = {
    **CITE_SYMBOL.settings,
    "field_separator": " | ",
    "indicators": "src/trading/indicators/*.py",
}

FIELDS = (f"<path>{SETTINGS['separator']}<symbol>", "<rank>", "<url>")

OUTPUTS: dict[str, FlagRow] = {
    CLEAN: FlagRow(Flag.PASS),
    DIRECTION: FlagRow(Flag.FIX, holds_in_source=True),
    SIGNAL: FlagRow(Flag.FIX, holds_in_source=True),
    CONFIDENCE: FlagRow(Flag.FIX),
    DOCUMENTATION: FlagRow(Flag.FIX),
    NOT_GROUNDED: FlagRow(Flag.BLOCK),
}

NOT_THREE_FIELDS = "not three fields: citation, rank and url"
OUTSIDE_INDICATORS = f"path outside {SETTINGS['indicators']}"
NOT_A_RANK = "rank not in outputs"
NOT_HTTPS = "url is not https"
NO_HOST = "url names no host"


def _cite_card(tier: int, key: str) -> list[str]:
    """Return the list `CITE_SYMBOL.tiers` holds under `key` in tier index `tier`."""
    listed = CITE_SYMBOL.tiers[tier][key]
    if not isinstance(listed, list):
        message = f"CITE.SYMBOL tier index {tier} holds no list under {key}"
        raise TypeError(message)
    return [str(item) for item in listed]


def _fields(line: str) -> list[str]:
    """Return `line` split at the `field_separator` in `SETTINGS`."""
    return line.split(SETTINGS["field_separator"])


def _data_type_fault(line: str) -> str | None:
    """Return the tier 1 reason `line` fails, or None when it fits."""
    fields = _fields(line)
    if len(fields) != len(FIELDS):
        return NOT_THREE_FIELDS
    if any(part.split() != [part] for part in fields[1:]):
        return NOT_THREE_FIELDS
    return CITE_SYMBOL.data_type(fields[0])


def _url_fault(url: str) -> str | None:
    """Return `NOT_HTTPS` or `NO_HOST` for the parts `urlsplit` reads, else None."""
    try:
        address = urlsplit(url)
        host = address.hostname
    except ValueError:
        return NO_HOST
    if address.scheme != "https":
        return NOT_HTTPS
    return None if host else NO_HOST


def _content_fault(line: str, _root: Path) -> str | None:
    """Return the tier 2 reason `line` fails under `SETTINGS`, or None."""
    citation, rank, url = _fields(line)
    path = citation.split(SETTINGS["separator"], 1)[0]
    if not PurePosixPath(path).full_match(SETTINGS["indicators"]):
        return OUTSIDE_INDICATORS
    if rank not in OUTPUTS:
        return NOT_A_RANK
    return _url_fault(url)


def _functions_verdict(line: str, root: Path) -> tuple[str, str]:
    """Return the rank where `CITE_SYMBOL.functions` resolves, else `NOT_GROUNDED`."""
    citation, rank = _fields(line)[:2]
    reading = CITE_SYMBOL.functions(citation, root)
    output, reason = reading[0], reading[1]
    return (rank if output == RESOLVED else NOT_GROUNDED), reason


SIGIL = Sigil(
    name="TA.AUDIT",
    edition=1,
    owner="ta",
    input_form="one line: " + SETTINGS["field_separator"].join(FIELDS),
    settings=SETTINGS,
    tiers=(
        {
            "accepts": "three fields split by the field separator: a citation the "
            "CITE.SYMBOL@3 path and symbol rules accept, then a rank and a url "
            "with no space",
            "rejects": [NOT_THREE_FIELDS, *_cite_card(0, "rejects")],
        },
        {
            "accepts": "a path the indicators setting matches, a rank in outputs, "
            "and an https url that names a host",
            "rejects": [OUTSIDE_INDICATORS, NOT_A_RANK, NOT_HTTPS, NO_HOST],
        },
        {
            "runs": _cite_card(2, "runs"),
            "not_grounded": _cite_card(2, "not_grounded"),
            "chosen_rank": _cite_card(2, "resolved"),
        },
    ),
    outputs=OUTPUTS,
    refusal=REJECTED,
    follows={},
    readers=CITE_SYMBOL.readers,
    data_type=_data_type_fault,
    content=_content_fault,
    functions=_functions_verdict,
)


if __name__ == "__main__":
    sys.exit(main(SIGIL))
