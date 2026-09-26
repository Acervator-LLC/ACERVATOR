"""A group called segmented whose segments are separated cards.

GUI007 refuses this file three times: ``segment_box`` suppresses no shared
edge, it rounds two corners in one branch, and ``GROUP_SPACING_PX`` is six.
"""

OUTLINE = "#7a7a9c"

#: The gap between two neighbouring cards, which a segmented group may not have.
GROUP_SPACING_PX = 6

#: The radius each card's own corners carry.
OUTER_RADIUS_PX = 3


def segment_box(position: str) -> str:
    """The border and radius declarations one segment carries at ``position``."""
    corner = f"{OUTER_RADIUS_PX}px"
    said = [f"border: 1px solid {OUTLINE}"]
    said.append("border-radius: 0px")
    if position == "first":
        said.append(f"border-top-left-radius: {corner}")
        said.append(f"border-bottom-left-radius: {corner}")
    if position == "last":
        said.append(f"border-top-right-radius: {corner}")
        said.append(f"border-bottom-right-radius: {corner}")
    return "; ".join(said) + "; "
