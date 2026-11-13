# PLW0642 self-or-cls-assignment: the Example block python -m ruff rule PLW0642 prints
class Version:
    def add(self, other):
        self = self + other
        return self

    @classmethod
    def superclass(cls):
        cls = cls.__mro__[-1]
        return cls
