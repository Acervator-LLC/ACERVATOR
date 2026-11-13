# FURB189 subclass-builtin: the Use instead block python -m ruff rule FURB189 prints
from collections import UserDict


class UppercaseDict(UserDict):
    def __setitem__(self, key, value):
        super().__setitem__(key.upper(), value)


d = UppercaseDict({"a": 1, "b": 2})  # Uses __setitem__
print(d)  # {'A': 1, 'B': 2}
