"""TA002 - a one-sided clamp on a bounded quantity.

The real incident: Slingshot `squeeze_conf` was clamped with a
ceiling and no floor, and reported confidences as low as -0.2722.
"""


def squeeze_confidence(raw):
    """Return the squeeze confidence for `raw`."""
    squeeze_conf = min(1.0, raw)
    return squeeze_conf
