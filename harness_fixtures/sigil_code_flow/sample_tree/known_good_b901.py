# B901 return-in-generator: the Use instead block python -m ruff rule B901 prints
from collections.abc import Iterable
from pathlib import Path


def get_file_paths(file_types: Iterable[str] | None = None) -> Iterable[Path]:
    dir_path = Path(".")
    if file_types is None:
        yield from dir_path.glob("*")
    else:
        for file_type in file_types:
            yield from dir_path.glob(f"*.{file_type}")
