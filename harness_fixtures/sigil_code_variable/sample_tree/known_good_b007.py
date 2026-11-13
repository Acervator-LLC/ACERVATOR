# B007 unused-loop-control-variable: the lines above the Use instead block python -m ruff rule B007 prints define its free names
foo, bar = [(1, 2)], print
for i, _j in foo:
    bar(i)
