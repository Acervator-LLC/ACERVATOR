# C400 unnecessary-generator-list: the lines above the Example block python -m ruff rule C400 prints define its free names
f, foo = str, [1]
list(f(x) for x in foo)
list(x for x in foo)
list((x for x in foo))
