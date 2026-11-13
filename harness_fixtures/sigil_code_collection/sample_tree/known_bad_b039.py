# B039 mutable-contextvar-default: the Example block python -m ruff rule B039 prints
from contextvars import ContextVar


cv: ContextVar[list] = ContextVar("cv", default=[])
