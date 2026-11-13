# RUF047 needless-else: the lines above the Use instead block python -m ruff rule RUF047 prints define its free names
foo, bar = True, print
if foo:
    bar()
