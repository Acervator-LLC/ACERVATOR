# G202 logging-redundant-exc-info: the Example block python -m ruff rule G202 prints
import logging

try:
    ...
except ValueError:
    logging.exception("Exception occurred", exc_info=True)
