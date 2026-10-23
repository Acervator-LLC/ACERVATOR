"""A money cell that appends two notes to the figure it draws.

CF001 refuses this file: `marked_cell` and `joined_cell` each compose a drawn
text of 161 px, and the column holds 158. `marked_cell` appends through
`MARKED_FIGURE_FORMAT` and `joined_cell` through an f-string, so one reading
covers both ways a cell is marked.
"""

#: The money figure both cells draw, grouped and to four decimals.
MAGNITUDE_FORMAT = "${magnitude:,.4f}"

#: The drawn text with one note set beside it.
MARKED_FIGURE_FORMAT = "{text} {marker}"

STALE_MARKER = "(stale)"

TWO_READS_MARKER = "(two reads)"


def marked_cell(magnitude: float, stale: bool, two_reads: bool) -> dict:
    """The money cell, each note appended through `MARKED_FIGURE_FORMAT`."""
    text = MAGNITUDE_FORMAT.format(magnitude=magnitude)
    if stale:
        text = MARKED_FIGURE_FORMAT.format(text=text, marker=STALE_MARKER)
    if two_reads:
        text = MARKED_FIGURE_FORMAT.format(text=text, marker=TWO_READS_MARKER)
    return {"text": text, "tip": ""}


def joined_cell(magnitude: float, stale: bool, two_reads: bool) -> dict:
    """The same money cell, each note joined into the drawn text by an f-string."""
    text = f"${abs(magnitude):,.4f}"
    if stale:
        text = f"{text} {STALE_MARKER}"
    if two_reads:
        text = f"{text} {TWO_READS_MARKER}"
    return {"text": text, "tip": ""}
