import contextlib


class Pool:
    def __init__(self) -> None:
        self.surplus = 0.0

    def discharge(self) -> float:
        discharged = float(getattr(self, "surplus", 0.0) or 0.0)
        self.surplus = 0.0
        return discharged


def refuses(record: dict[str, str]) -> bool:
    try:
        float(record.get("price", "none"))
    except ValueError:
        return True
    return False


def parses(text: str) -> bool:
    with contextlib.suppress(ValueError):
        int(text)
        return True
    return False
