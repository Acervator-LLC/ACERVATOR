# C411 unnecessary-list-call: the lines above the Example block python -m ruff rule C411 prints define its free names
f, foo = str, [1]
list([f(x) for x in foo])
