# PLW0602 global-variable-not-assigned: the Example block python -m ruff rule PLW0602 prints
DEBUG = True


def foo():
    global DEBUG
    if DEBUG:
        print("foo() called")
    ...
