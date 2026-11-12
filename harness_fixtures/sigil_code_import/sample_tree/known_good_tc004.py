# TC004 runtime-import-in-type-checking-block: the Use instead block python -m ruff rule TC004 prints
import foo


def bar() -> None:
    foo.bar()
