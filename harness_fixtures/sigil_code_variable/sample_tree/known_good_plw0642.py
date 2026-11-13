# PLW0642 self-or-cls-assignment: the Use instead block python -m ruff rule PLW0642 prints
class Version:
    def add(self, other):
        new_version = self + other
        return new_version

    @classmethod
    def superclass(cls):
        supercls = cls.__mro__[-1]
        return supercls
