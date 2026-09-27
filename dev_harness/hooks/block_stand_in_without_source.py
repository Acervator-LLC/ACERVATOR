"""Refuses a brief whose stand-in for an outside source names nothing the source serves.

`STAND_IN` matches a brief that replaces a venue, exchange, feed or endpoint with a
loopback stand-in, and `SOURCE_NAMED` matches the clauses that shape it from the real
source. `EMPTY_AS_PASS` matches a proof that ends at an empty state. `deny` exits 2.
"""

import json
import re
import sys

BRIEFS = {"Agent", "SendMessage"}

STAND_IN = re.compile(
    r"\b(?:stand-in|stood in|stands in|loopback (?:stand|candle|venue|source|endpoint))\b",
    re.IGNORECASE,
)

SOURCE_NAMED = re.compile(
    r"### Real conditions\n(?:(?!\n### )[\s\S]){0,3000}?\b\d", re.IGNORECASE
)

EMPTY_AS_PASS = re.compile(
    r"(?:no candle[^.\n]{0,80}(?:read as|counts as|is) (?:the )?(?:pass|green|reading)"
    r"|empty state[^.\n]{0,60}(?:is|counts as) (?:the )?(?:pass|green))",
    re.IGNORECASE,
)


def text_of(payload):
    """Returns the text a tool call carries, across the tool shapes."""
    data = payload.get("tool_input") or {}
    parts = [data.get(key) or "" for key in ("prompt", "message")]
    return "\n".join(part for part in parts if isinstance(part, str))


def deny(reason: str, fix: str) -> None:
    """Prints the refusal to stderr and exits 2 to block the call."""
    sys.stderr.write("Dispatch refused: %s\n%s\n" % (reason, fix))
    sys.exit(2)


def main() -> int:
    """Reads the hook payload and checks a brief's stand-in against its source."""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if payload.get("tool_name") not in BRIEFS:
        return 0
    text = text_of(payload)
    if not text:
        return 0
    if STAND_IN.search(text) and not SOURCE_NAMED.search(text):
        deny(
            "the brief stands in for an outside source without naming what that"
            " source serves",
            "Add a `### Real conditions` section: the source's documented response"
            " shape and limits (granularities, list endpoints, rate limits), and"
            " the operator's own recorded responses where his logs hold them."
            " Measured 2026-09-19: four units read Scan Now green against a"
            " stand-in that served weekly candles Coinbase never serves; his press"
            " read 120 markets, 0 hits, and no stocks list.",
        )
    if EMPTY_AS_PASS.search(text):
        deny(
            "the brief reads an empty end state as a pass",
            "A bundle that ends at 'no candle' or 'no post' did not exercise the"
            " feature. Name it a non-reading, and require the end state the"
            " operator will see: hits, or a refusal with its cause named.",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
