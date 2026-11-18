# PERF101 unnecessary-list-cast: the Example block python -m ruff rule PERF101 prints
items = (1, 2, 3)
for i in list(items):
    print(i)
