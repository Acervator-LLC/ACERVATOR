# RET506 superfluous-else-raise: the Example block python -m ruff rule RET506 prints
def foo(bar, baz):
    if bar == "Specific Error":
        raise Exception(bar)
    else:
        raise Exception(baz)
