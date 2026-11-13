# PERF403 manual-dict-comprehension: the Use instead block python -m ruff rule PERF403 prints
pairs = (("a", 1), ("b", 2))
result = {x: y for x, y in pairs if y % 2}
pairs = (("a", 1), ("b", 2))
result.update({x: y for x, y in pairs if y % 2})
