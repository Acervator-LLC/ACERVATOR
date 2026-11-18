# S110 try-except-pass: the Use instead block python -m ruff rule S110 prints
import logging

try:
    ...
except Exception as exc:
    logging.exception("Exception occurred")
