# PLR0402 manual-from-import: the Example block python -m ruff rule PLR0402 prints, then __all__ naming its imports
import concurrent.futures as futures

__all__ = ["futures"]
