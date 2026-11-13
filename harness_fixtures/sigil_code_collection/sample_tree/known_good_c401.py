# C401 unnecessary-generator-set: the lines above the Use instead block python -m ruff rule C401 prints define its free names
f, foo = str, [1]
{f(x) for x in foo}
set(foo)
set(foo)
