# FURB188 slice-to-remove-prefix-or-suffix: the Example block python -m ruff rule FURB188 prints
def example(filename: str, text: str):
    filename = filename[:-4] if filename.endswith(".txt") else filename
    if text.startswith("pre"):
        text = text[3:]
