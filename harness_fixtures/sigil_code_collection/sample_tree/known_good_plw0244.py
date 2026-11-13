# PLW0244 redefined-slots-in-subclass: the Use instead block python -m ruff rule PLW0244 prints
class Base:
    __slots__ = ("a", "b")


class Subclass(Base):
    __slots__ = "d"
