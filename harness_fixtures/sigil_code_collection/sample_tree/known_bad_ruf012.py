# RUF012 mutable-class-default: the Example block python -m ruff rule RUF012 prints
class A:
    variable_1: list[int] = []
    variable_2: set[int] = set()
    variable_3: dict[str, int] = {}
