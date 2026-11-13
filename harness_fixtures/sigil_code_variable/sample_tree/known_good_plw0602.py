# PLW0602 global-variable-not-assigned: the Use instead block python -m ruff rule PLW0602 prints
DEBUG = True


def foo():
    if DEBUG:
        print("foo() called")
    ...
