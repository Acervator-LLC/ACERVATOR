"""The TA004 body, corrected: avg_width is divided by avg_mid before the compare."""


def squeezing(upper, lower, mid, avg_width, avg_mid):
    """Return whether the band is squeezing."""
    band_width = (upper - lower) / mid
    avg_band_width = avg_width / avg_mid
    return band_width < avg_band_width
