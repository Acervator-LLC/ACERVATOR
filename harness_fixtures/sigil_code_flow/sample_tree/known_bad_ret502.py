# RET502 implicit-return-value: the Example block python -m ruff rule RET502 prints
def foo(bar):
    if not bar:
        return
    return 1
