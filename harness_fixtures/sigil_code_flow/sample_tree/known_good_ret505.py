# RET505 superfluous-else-return: the Use instead block python -m ruff rule RET505 prints
def foo(bar, baz):
    if bar:
        return 1
    return baz
