# RET507 superfluous-else-continue: the Use instead block python -m ruff rule RET507 prints
def foo(bar, baz):
    for i in bar:
        if i < baz:
            continue
        x = 0
