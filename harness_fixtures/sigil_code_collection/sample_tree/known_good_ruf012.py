# RUF012 mutable-class-default: the first Use instead block python -m ruff rule RUF012 prints
class A:
    def __init__(self) -> None:
        self.variable_1: list[int] = []
        self.variable_2: set[int] = set()
        self.variable_3: dict[str, int] = {}
