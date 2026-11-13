# FURB189 subclass-builtin: the Example block python -m ruff rule FURB189 prints
class UppercaseDict(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key.upper(), value)


d = UppercaseDict({"a": 1, "b": 2})  # Bypasses __setitem__
print(d)  # {'a': 1, 'b': 2}
