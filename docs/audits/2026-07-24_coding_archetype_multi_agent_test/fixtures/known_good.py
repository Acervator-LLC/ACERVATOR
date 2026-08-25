"""A file with zero known code-quality defects.

Ground truth: CodingArchetype.review() should produce ZERO
critical/high findings on this file. Any high finding here is a
false positive that must be investigated.
"""

from __future__ import annotations


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


def multiply(a: int, b: int) -> int:
    """Return the product of two integers."""
    return a * b


def apply_op(op: str, a: int, b: int) -> int:
    """Dispatch to add or multiply based on op name."""
    if op == "add":
        return add(a, b)
    if op == "multiply":
        return multiply(a, b)
    raise ValueError(f"unknown op: {op}")


def main() -> None:
    print(apply_op("add", 2, 3))
    print(apply_op("multiply", 4, 5))


if __name__ == "__main__":
    main()
