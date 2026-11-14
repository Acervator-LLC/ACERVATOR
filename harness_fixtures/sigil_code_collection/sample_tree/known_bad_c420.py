# C420 unnecessary-dict-comprehension-for-iterable: the lines above the Example block python -m ruff rule C420 prints define its free names
iterable = ["a", "b"]
{a: None for a in iterable}
{a: 1 for a in iterable}
