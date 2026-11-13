# BLE001 blind-except: the lines above the Example block python -m ruff rule BLE001 prints define its free names
foo = print
try:
    foo()
except BaseException:
    ...
