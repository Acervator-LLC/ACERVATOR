# TRY401 verbose-log-message: the lines above the Example block python -m ruff rule TRY401 prints define its free names
import logging
logger = logging.getLogger(__name__)
try:
    ...
except ValueError as e:
    logger.exception(f"Found an error: {e}")
