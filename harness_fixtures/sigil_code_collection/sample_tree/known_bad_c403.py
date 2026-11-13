# C403 unnecessary-list-comprehension-set: the lines above the Example block python -m ruff rule C403 prints define its free names
f, foo = str, [1]
set([f(x) for x in foo])
