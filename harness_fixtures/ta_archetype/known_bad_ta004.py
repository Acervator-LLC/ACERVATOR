"""TA004 - a dimensionless ratio compared against an absolute.

The real incident: a squeeze flag compared a dimensionless band
width against an absolute price width, so the flag reduced to a
test on the price level. Every symbol at or below $0.42 squeezed
on 0.0% of windows and every symbol at or above $8.28 on 100.0%.
"""


def squeezing(upper, lower, mid, avg_width):
    """Return whether the band is squeezing."""
    band_width = (upper - lower) / mid
    return band_width < avg_width
