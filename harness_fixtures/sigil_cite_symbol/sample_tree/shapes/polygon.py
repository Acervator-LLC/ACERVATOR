"""`Polygon`, `describe` and `load_name` hold the names that `sample_good.txt` cites."""

DEFAULT_NAME = "triangle"
first_label, second_label = "a", "b"
STYLE: str = "solid"


class Polygon:
    """`Polygon` holds a `name` and a class-level `sides` label."""

    sides = "three"

    def __init__(self, name: str) -> None:
        self.name = name

    def label(self) -> str:
        """Return `name`."""
        return self.name

    class Corner:
        """`Corner.kind` names the corner type."""

        def kind(self) -> str:
            """Return the corner type of `Corner`."""
            return "interior"


def describe(polygon: Polygon) -> str:
    """Return `Polygon.label` of `polygon`."""
    return polygon.label()


async def load_name() -> str:
    """Return `DEFAULT_NAME`."""
    return DEFAULT_NAME
