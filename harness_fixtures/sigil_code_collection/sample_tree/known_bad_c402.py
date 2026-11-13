# C402 unnecessary-generator-dict: the lines above the Example block python -m ruff rule C402 prints define its free names
f, foo = str, [1]
dict((x, f(x)) for x in foo)
