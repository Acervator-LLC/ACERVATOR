# B039 mutable-contextvar-default: the Use instead block python -m ruff rule B039 prints
from contextvars import ContextVar


cv: ContextVar[list | None] = ContextVar("cv", default=None)

...

if cv.get() is None:
    cv.set([])
