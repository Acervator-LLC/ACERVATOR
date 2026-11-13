# RUF072 useless-finally: the lines above the Use instead block python -m ruff rule RUF072 prints define its free names
foo, bar = print, print
try:
    foo()
except Exception:
    bar()
