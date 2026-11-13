# G201 logging-exc-info: the Example block python -m ruff rule G201 prints
import logging

try:
    ...
except ValueError:
    logging.error("Exception occurred", exc_info=True)
