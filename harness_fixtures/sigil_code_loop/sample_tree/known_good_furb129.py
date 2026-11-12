# FURB129 readlines-in-for: the Use instead block python -m ruff rule FURB129 prints
with open("file.txt") as fp:
    for line in fp:
        ...
