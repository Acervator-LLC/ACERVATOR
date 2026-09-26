"""A segmented group whose segments share their edges and round one corner each.

GUI007 passes this file: ``segment_box`` suppresses a shared edge, every
rounded corner sits in its own branch, and ``GROUP_SPACING_PX`` is zero.
"""

OUTLINE = "#7a7a9c"

#: The gap between two neighbouring segments. Zero, so one line draws.
GROUP_SPACING_PX = 0

#: The radius the square's four outer corners carry.
OUTER_RADIUS_PX = 3


def segment_box(row: int, column: int, rows: int, holds: int) -> str:
    """The border and radius declarations one segment carries in the square."""
    corner = f"{OUTER_RADIUS_PX}px"
    said = [f"border: 1px solid {OUTLINE}"]
    if column > 0:
        said.append("border-left: none")
    if row > 0:
        said.append("border-top: none")
    said.append("border-radius: 0px")
    if row == 0 and column == 0:
        said.append(f"border-top-left-radius: {corner}")
    if row == 0 and column == holds - 1:
        said.append(f"border-top-right-radius: {corner}")
    if row == rows - 1 and column == 0:
        said.append(f"border-bottom-left-radius: {corner}")
    if row == rows - 1 and column == holds - 1:
        said.append(f"border-bottom-right-radius: {corner}")
    return "; ".join(said) + "; "
