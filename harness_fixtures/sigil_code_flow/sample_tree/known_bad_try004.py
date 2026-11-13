# TRY004 type-check-without-type-error: the Example block python -m ruff rule TRY004 prints
def foo(n: int):
    if isinstance(n, int):
        pass
    else:
        raise ValueError("n must be an integer")
