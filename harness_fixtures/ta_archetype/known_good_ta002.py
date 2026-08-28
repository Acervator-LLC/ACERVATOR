"""The TA002 body, corrected: both ends of the clamp are set."""


def squeeze_confidence(raw):
    """Return the squeeze confidence for `raw`."""
    squeeze_conf = max(0.0, min(1.0, raw))
    return squeeze_conf
