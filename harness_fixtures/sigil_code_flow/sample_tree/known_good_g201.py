# G201 logging-exc-info: the Use instead block python -m ruff rule G201 prints
import logging

try:
    ...
except ValueError:
    logging.exception("Exception occurred")
