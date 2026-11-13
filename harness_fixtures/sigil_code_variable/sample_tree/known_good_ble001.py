# BLE001 blind-except: the lines above the Use instead block python -m ruff rule BLE001 prints define its free names
import logging
foo = print
try:
    foo()
except FileNotFoundError:
    ...
try:
    foo()
except BaseException:
    raise
try:
    foo()
except BaseException:
    logging.exception("Something went wrong")
