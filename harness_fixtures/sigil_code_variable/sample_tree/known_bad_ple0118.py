# PLE0118 load-before-global-declaration: the Example block python -m ruff rule PLE0118 prints
counter = 1


def increment():
    print(f"Adding 1 to {counter}")
    global counter
    counter += 1
