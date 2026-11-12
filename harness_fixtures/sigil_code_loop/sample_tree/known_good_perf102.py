# PERF102 incorrect-dict-iterator: the Use instead block python -m ruff rule PERF102 prints
obj = {"a": 1, "b": 2}
for value in obj.values():
    print(value)
