# SIM116 if-else-block-instead-of-dict-lookup: the Use instead block python -m ruff rule SIM116 prints
def find_phrase(x):
    phrases = {1: "Hello", 2: "Goodbye", 3: "Good morning"}
    return phrases.get(x, "Goodnight")
