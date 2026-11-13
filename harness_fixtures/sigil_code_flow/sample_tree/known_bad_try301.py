# TRY301 raise-within-try: the Example block python -m ruff rule TRY301 prints
def bar():
    pass


def foo():
    try:
        a = bar()
        if not a:
            raise ValueError
    except ValueError:
        raise
