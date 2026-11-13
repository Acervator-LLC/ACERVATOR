# G101 logging-extra-attr-clash: the Use instead block python -m ruff rule G101 prints
import logging

logging.basicConfig(format="%(user_id)s - %(message)s", level=logging.INFO)

username = "Maria"

logging.info("Something happened", extra=dict(user_id=username))
