# F822 undefined-export: the Example block python -m ruff rule F822 prints
from foo import bar


__all__ = ["bar", "baz"]  # undefined name `baz` in `__all__`
