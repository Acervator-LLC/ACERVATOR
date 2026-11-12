# C416 unnecessary-comprehension: the lines above the Example block python -m ruff rule C416 prints define its free names
iterable = [("a", 1)]
{a: b for a, b in iterable}
[x for x in iterable]
{x for x in iterable}
