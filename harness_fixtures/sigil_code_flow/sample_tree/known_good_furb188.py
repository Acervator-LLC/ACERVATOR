# FURB188 slice-to-remove-prefix-or-suffix: the Use instead block python -m ruff rule FURB188 prints
def example(filename: str, text: str):
    filename = filename.removesuffix(".txt")
    text = text.removeprefix("pre")
