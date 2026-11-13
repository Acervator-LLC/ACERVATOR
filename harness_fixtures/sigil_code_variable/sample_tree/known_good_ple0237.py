# PLE0237 non-slot-assignment: the Use instead block python -m ruff rule PLE0237 prints
class Student:
    __slots__ = ("name", "surname")

    def __init__(self, name, surname):
        self.name = name
        self.surname = surname
        self.setup()

    def setup(self):
        pass
