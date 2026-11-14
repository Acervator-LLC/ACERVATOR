# RUF008 mutable-dataclass-default: the first Use instead block python -m ruff rule RUF008 prints
from dataclasses import dataclass, field


@dataclass
class A:
    mutable_default: list[int] = field(default_factory=list)
