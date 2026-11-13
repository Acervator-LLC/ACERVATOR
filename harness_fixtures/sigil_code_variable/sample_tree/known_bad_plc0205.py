# PLC0205 single-string-slots: the Example block python -m ruff rule PLC0205 prints
class Person:
    __slots__: str = "name"

    def __init__(self, name: str) -> None:
        self.name = name
