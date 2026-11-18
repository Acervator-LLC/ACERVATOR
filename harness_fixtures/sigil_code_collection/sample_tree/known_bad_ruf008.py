# RUF008 mutable-dataclass-default: the Example block python -m ruff rule RUF008 prints
from dataclasses import dataclass


@dataclass
class A:
    # A list without a `default_factory` or `ClassVar` annotation
    # will raise a `ValueError`.
    mutable_default: list[int] = []
