# RET502 implicit-return-value: the Use instead block python -m ruff rule RET502 prints
def foo(bar):
    if not bar:
        return None
    return 1
