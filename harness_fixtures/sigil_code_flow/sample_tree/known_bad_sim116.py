# SIM116 if-else-block-instead-of-dict-lookup: the Example block python -m ruff rule SIM116 prints
def find_phrase(x):
    if x == 1:
        return "Hello"
    elif x == 2:
        return "Goodbye"
    elif x == 3:
        return "Good morning"
    else:
        return "Goodnight"
