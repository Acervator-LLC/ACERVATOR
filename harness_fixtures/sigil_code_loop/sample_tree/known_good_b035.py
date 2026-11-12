# B035 static-key-dict-comprehension: the Use instead block python -m ruff rule B035 prints
data = ["some", "Data"]
{value: value.upper() for value in data}
