# G101 logging-extra-attr-clash: the Example block python -m ruff rule G101 prints
import logging

logging.basicConfig(format="%(name) - %(message)s", level=logging.INFO)

username = "Maria"

logging.info("Something happened", extra=dict(name=username))
