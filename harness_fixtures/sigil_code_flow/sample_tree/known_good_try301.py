# TRY301 raise-within-try: the Use instead block python -m ruff rule TRY301 prints
def bar():
    raise ValueError


def foo():
    try:
        a = bar()  # refactored `bar` to raise `ValueError`
    except ValueError:
        raise
