# RET507 superfluous-else-continue: the Example block python -m ruff rule RET507 prints
def foo(bar, baz):
    for i in bar:
        if i < baz:
            continue
        else:
            x = 0
