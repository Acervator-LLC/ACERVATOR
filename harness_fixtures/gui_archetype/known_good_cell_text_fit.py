"""A money cell whose two notes still fit the figure's own column.

CF001 passes this file: `marked_cell` and `joined_cell` each compose a drawn
text of 155 px against a column of 158, three short of the edge. Both cells
also append `STALE_TIP` to a tooltip far wider than the column, which CF001
leaves unmeasured.
"""

#: The money figure both cells draw, grouped and to four decimals.
MAGNITUDE_FORMAT = "${magnitude:,.4f}"

#: The drawn text with one note set beside it.
MARKED_FIGURE_FORMAT = "{text} {marker}"

STALE_MARKER = "(stale)"

OLD_PRICE_MARKER = "(old price)"

#: The prose the cell carries where length costs nothing.
STALE_TIP = (
    "STALE — the price did not refresh this tick, so this figure rests on the "
    "last reading held rather than a current one. Do not fire on it."
)


def marked_cell(magnitude: float, stale: bool, old_price: bool) -> dict:
    """The money cell, each note appended through `MARKED_FIGURE_FORMAT`."""
    text = MAGNITUDE_FORMAT.format(magnitude=magnitude)
    tip = ""
    if stale:
        text = MARKED_FIGURE_FORMAT.format(text=text, marker=STALE_MARKER)
        tip = f"{tip}{STALE_TIP}"
    if old_price:
        text = MARKED_FIGURE_FORMAT.format(text=text, marker=OLD_PRICE_MARKER)
    return {"text": text, "tip": tip}


def joined_cell(magnitude: float, stale: bool, old_price: bool) -> dict:
    """The same money cell, each note joined into the drawn text by an f-string."""
    text = f"${abs(magnitude):,.4f}"
    tip = ""
    if stale:
        text = f"{text} {STALE_MARKER}"
        tip = f"{tip}{STALE_TIP}"
    if old_price:
        text = f"{text} {OLD_PRICE_MARKER}"
    return {"text": text, "tip": tip}
