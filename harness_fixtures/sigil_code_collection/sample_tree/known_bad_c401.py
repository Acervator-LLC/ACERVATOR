# C401 unnecessary-generator-set: the lines above the Example block python -m ruff rule C401 prints define its free names
f, foo = str, [1]
set(f(x) for x in foo)
set(x for x in foo)
set((x for x in foo))
