"""A row that parks all its spare width on the ``amount`` slot alone.

GUI008 refuses this file: exactly one ``ROW_STRETCH`` share is above zero, so
``count`` and ``button`` fall to their ``ROW_FLOORS`` entry.
"""

#: The slots the row draws, in the order it draws them.
ROW_ORDER = ["amount", "count", "spacer", "button"]

#: The share of spare width each ``ROW_ORDER`` slot takes.
ROW_STRETCH = [1, 0, 0, 0]

#: The narrowest each drawn slot falls to, keyed by slot.
ROW_FLOORS = {"amount": 100, "count": 66, "button": 68}


def slot_stretch(slot: str) -> int:
    """The share of spare width one ``ROW_ORDER`` slot takes."""
    if slot not in ROW_ORDER:
        return 0
    return int(ROW_STRETCH[ROW_ORDER.index(slot)])


def row_min_w(gap: int) -> int:
    """The narrowest the row draws at, holding every ``ROW_FLOORS`` slot."""
    return sum(ROW_FLOORS.values()) + len(ROW_ORDER) * int(gap)
