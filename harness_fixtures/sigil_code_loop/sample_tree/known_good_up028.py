# UP028 yield-in-for-loop: the lines above the Use instead block python -m ruff rule UP028 prints define its free names
foo = [1]
def bar():
    yield from foo

    for _element in foo:
        y = _element
        yield y
