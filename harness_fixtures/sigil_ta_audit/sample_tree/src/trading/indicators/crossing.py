"""`CrossingIndicator` and `detect_crossing` hold the names the sample lines cite."""

# comment_only_name appears in this comment alone.
LOOKBACK = 3
LABEL = "string_only_name"


class CrossingIndicator:
    """`compute` returns `name`; docstring_only_name appears in this docstring alone."""

    def __init__(self, name: str) -> None:
        """Store `name`."""
        self.name = name

    def compute(self) -> str:
        """Return `name`."""
        return self.name


def detect_crossing() -> int:
    """Return `LOOKBACK`."""
    return LOOKBACK
