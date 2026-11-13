# SIM114 if-with-same-arms: the lines above the Example block python -m ruff rule SIM114 prints define its free names
x = 1
if x == 1:
    print("Hello")
elif x == 2:
    print("Hello")
