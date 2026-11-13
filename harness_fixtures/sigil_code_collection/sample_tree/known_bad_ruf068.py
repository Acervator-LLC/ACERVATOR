# RUF068 duplicate-entry-in-dunder-all: the Example block python -m ruff rule RUF068 prints
__all__ = [
    "DatabaseConnection",
    "Product",
    "User",
    "DatabaseConnection",  # Duplicate
]
