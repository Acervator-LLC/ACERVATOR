# S112 try-except-continue: the line above the Use instead block python -m ruff rule S112 prints defines its free name
predicate = __name__ == "__main__"
import logging

while predicate:
    try:
        ...
    except Exception as exc:
        logging.exception("Error occurred")
