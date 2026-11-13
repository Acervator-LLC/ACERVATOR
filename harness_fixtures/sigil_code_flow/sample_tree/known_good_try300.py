# TRY300 try-consider-else: the Use instead block python -m ruff rule TRY300 prints
import logging


def reciprocal(n):
    try:
        rec = 1 / n
    except ZeroDivisionError:
        logging.exception("Exception occurred")
        raise
    else:
        print(f"reciprocal of {n} is {rec}")
        return rec
