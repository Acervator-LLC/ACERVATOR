# PERF102 incorrect-dict-iterator: the Example block python -m ruff rule PERF102 prints
obj = {"a": 1, "b": 2}
for key, value in obj.items():
    print(value)
