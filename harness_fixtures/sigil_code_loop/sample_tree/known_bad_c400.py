# C400 unnecessary-generator-list: the lines above the Example block python -m ruff rule C400 prints define its free names
foo, f = [1, 2], str
list(f(x) for x in foo)
list(x for x in foo)
list((x for x in foo))
