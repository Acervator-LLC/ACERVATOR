# UP028 yield-in-for-loop: the lines above the Example block python -m ruff rule UP028 prints define its free names
foo = [1]
def bar():
    for x in foo:
        yield x

    global y
    for y in foo:
        yield y
