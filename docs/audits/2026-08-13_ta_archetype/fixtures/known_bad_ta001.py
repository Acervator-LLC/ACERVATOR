"""TA001 - a docstring promising an average over a body that
never divides.

The real incident: `_wilder_smooth` documented "First value =
sum/period" and returned the SUM. ADX then ran at about 14 times
its definitional maximum for four minor versions, and 99.8% of
readings exceeded 100 on an index bounded at 100.
"""


def wilder_smooth(values, period):
    """Return the average of the first `period` values."""
    return sum(values[:period])
