# RET501 unnecessary-return-none: the Example block python -m ruff rule RET501 prints
def foo(bar):
    if not bar:
        return
    return None
