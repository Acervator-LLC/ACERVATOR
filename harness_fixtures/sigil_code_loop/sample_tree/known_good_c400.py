# C400 unnecessary-generator-list: the lines above the Use instead block python -m ruff rule C400 prints define its free names
foo, f = [1, 2], str
[f(x) for x in foo]
list(foo)
list(foo)
