# TRY004 type-check-without-type-error: the Use instead block python -m ruff rule TRY004 prints
def foo(n: int):
    if isinstance(n, int):
        pass
    else:
        raise TypeError("n must be an integer")
