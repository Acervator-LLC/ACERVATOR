# TRY300 try-consider-else: the Example block python -m ruff rule TRY300 prints
import logging


def reciprocal(n):
    try:
        rec = 1 / n
        print(f"reciprocal of {n} is {rec}")
        return rec
    except ZeroDivisionError:
        logging.exception("Exception occurred")
        raise
