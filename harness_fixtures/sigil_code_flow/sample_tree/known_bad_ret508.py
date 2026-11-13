# RET508 superfluous-else-break: the Example block python -m ruff rule RET508 prints
def foo(bar, baz):
    for i in bar:
        if i > baz:
            break
        else:
            x = 0
