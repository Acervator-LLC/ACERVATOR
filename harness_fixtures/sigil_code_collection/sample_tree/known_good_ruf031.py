# RUF031 incorrectly-parenthesized-tuple-in-subscript: the Use instead block python -m ruff rule RUF031 prints
directions = {(0, 1): "North", (1, 0): "East", (0, -1): "South", (-1, 0): "West"}
directions[0, 1]
