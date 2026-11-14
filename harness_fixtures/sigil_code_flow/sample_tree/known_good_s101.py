# S101 assert: the line above the Use instead block python -m ruff rule S101 prints defines its free name
x = 1
if not x > 0:
    raise ValueError("Expected positive value.")
# or even better:
if x <= 0:
    raise ValueError("Expected positive value.")
