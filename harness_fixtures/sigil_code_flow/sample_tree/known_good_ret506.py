# RET506 superfluous-else-raise: the Use instead block python -m ruff rule RET506 prints
def foo(bar, baz):
    if bar == "Specific Error":
        raise Exception(bar)
    raise Exception(baz)
