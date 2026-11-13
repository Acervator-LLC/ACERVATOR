# PLE0118 load-before-global-declaration: the Use instead block python -m ruff rule PLE0118 prints
counter = 1


def increment():
    global counter
    print(f"Adding 1 to {counter}")
    counter += 1
