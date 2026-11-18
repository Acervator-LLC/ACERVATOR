class Pool:
    def __init__(self) -> None:
        self.surplus = 0.0

    def discharge(self) -> None:
        float(getattr(self, "surplus", 0.0) or 0.0)
        self.surplus = 0.0
