# SIM110 reimplemented-builtin: the lines above the Use instead block python -m ruff rule SIM110 prints define its free names
iterable, predicate = [1, 2], bool
def foo():
    return any(predicate(item) for item in iterable)
