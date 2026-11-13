# TRY401 verbose-log-message: the lines above the Use instead block python -m ruff rule TRY401 prints define its free names
import logging
logger = logging.getLogger(__name__)
try:
    ...
except ValueError:
    logger.exception("Found an error")
