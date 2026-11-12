# B035 static-key-dict-comprehension: the Example block python -m ruff rule B035 prints
data = ["some", "Data"]
{"key": value.upper() for value in data}
