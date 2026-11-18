# SIM110 reimplemented-builtin: the lines above the Example block python -m ruff rule SIM110 prints define its free names
iterable, predicate = [1, 2], bool
def foo():
    for item in iterable:
        if predicate(item):
            return True
    return False
