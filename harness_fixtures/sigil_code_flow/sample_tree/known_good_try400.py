# TRY400 error-instead-of-exception: the Use instead block python -m ruff rule TRY400 prints
import logging


def func():
    try:
        raise NotImplementedError
    except NotImplementedError:
        logging.exception("Exception occurred")
