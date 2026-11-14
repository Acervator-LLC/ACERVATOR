# F823 undefined-local: the Use instead block python -m ruff rule F823 prints
x = 1


def foo():
    global x
    x += 1
