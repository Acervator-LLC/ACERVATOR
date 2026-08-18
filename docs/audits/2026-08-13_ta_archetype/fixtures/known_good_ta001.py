"""The TA001 body, corrected: the promise and the maths agree."""


def wilder_smooth(values, period):
    """Return the average of the first `period` values."""
    return sum(values[:period]) / period
