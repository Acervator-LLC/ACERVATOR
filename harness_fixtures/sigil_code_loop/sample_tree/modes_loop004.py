# LOOP004 open-method-readlines-in-for: each faulty_ input iterates readlines() on a file an open method
# returned, its corrected_ twin iterates the file object, its kept_, hint_ and other_ twins keep the list,
# pass a size hint, or read an object no open method returned, and each furb129_ twin is a form FURB129 reads
import io
import pathlib
from collections.abc import Callable
from pathlib import Path
from typing import TextIO


def faulty_with_loop(path: Path) -> int:
    total = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle.readlines():
            if line.strip():
                total += 1
    return total


def corrected_with_loop(path: Path) -> int:
    total = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                total += 1
    return total


def kept_with_loop(path: Path, wanted: list[int]) -> int:
    with path.open(encoding="utf-8") as handle:
        lines = handle.readlines()
    total = 0
    for index in wanted:
        if index < len(lines) and lines[index].strip():
            total += 1
    return total


def hint_with_loop(path: Path) -> int:
    total = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle.readlines(4096):
            if line.strip():
                total += 1
    return total


def other_with_loop(text: str) -> int:
    total = 0
    with io.StringIO(text) as handle:
        for line in handle.readlines():
            if line.strip():
                total += 1
    return total


def faulty_direct_loop(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.open(encoding="utf-8").readlines():
        name = line.strip()
        if name:
            names.append(name.upper())
    return names


def corrected_direct_loop(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.open(encoding="utf-8"):
        name = line.strip()
        if name:
            names.append(name.upper())
    return names


def kept_direct_loop(path: Path, wanted: list[int]) -> list[str]:
    lines = path.open(encoding="utf-8").readlines()
    names: list[str] = []
    for index in wanted:
        name = lines[index].strip() if index < len(lines) else ""
        if name:
            names.append(name.upper())
    return names


def hint_direct_loop(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.open(encoding="utf-8").readlines(4096):
        name = line.strip()
        if name:
            names.append(name.upper())
    return names


def other_direct_loop(text: str) -> list[str]:
    names: list[str] = []
    for line in io.StringIO(text).readlines():
        name = line.strip()
        if name:
            names.append(name.upper())
    return names


def faulty_comprehension(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        return [line.strip() for line in handle.readlines()]


def corrected_comprehension(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        return [line.strip() for line in handle]


def kept_comprehension(path: Path, wanted: list[int]) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        lines = handle.readlines()
    return [lines[index].strip() for index in wanted if index < len(lines)]


def hint_comprehension(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        return [line.strip() for line in handle.readlines(4096)]


def other_comprehension(text: str) -> list[str]:
    with io.StringIO(text) as handle:
        return [line.strip() for line in handle.readlines()]


def faulty_task_count_errors(path: Path, level_of: Callable[[str], str | None]) -> int:
    count = 0
    with path.open(encoding="utf-8") as fp:
        for line in fp.readlines():
            if level_of(line) == "ERROR":
                count += 1
    return count


def corrected_task_count_errors(
    path: Path, level_of: Callable[[str], str | None]
) -> int:
    count = 0
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            if level_of(line) == "ERROR":
                count += 1
    return count


def kept_task_count_errors(
    path: Path, level_of: Callable[[str], str | None], wanted: list[int]
) -> int:
    with path.open(encoding="utf-8") as fp:
        lines = fp.readlines()
    count = 0
    for index in wanted:
        if index < len(lines) and level_of(lines[index]) == "ERROR":
            count += 1
    return count


def hint_task_count_errors(path: Path, level_of: Callable[[str], str | None]) -> int:
    count = 0
    with path.open(encoding="utf-8") as fp:
        for line in fp.readlines(4096):
            if level_of(line) == "ERROR":
                count += 1
    return count


def other_task_count_errors(text: str, level_of: Callable[[str], str | None]) -> int:
    count = 0
    with io.StringIO(text) as fp:
        for line in fp.readlines():
            if level_of(line) == "ERROR":
                count += 1
    return count


class FaultyAttributeLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def errors(self) -> int:
        count = 0
        with self.path.open(encoding="utf-8") as handle:
            for line in handle.readlines():
                if "error" in line:
                    count += 1
        return count


class CorrectedAttributeLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def errors(self) -> int:
        count = 0
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if "error" in line:
                    count += 1
        return count


class KeptAttributeLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def errors(self, wanted: list[int]) -> int:
        with self.path.open(encoding="utf-8") as handle:
            lines = handle.readlines()
        count = 0
        for index in wanted:
            if index < len(lines) and "error" in lines[index]:
                count += 1
        return count


class HintAttributeLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def errors(self) -> int:
        count = 0
        with self.path.open(encoding="utf-8") as handle:
            for line in handle.readlines(4096):
                if "error" in line:
                    count += 1
        return count


class OtherAttributeLog:
    def __init__(self, stream: TextIO) -> None:
        self.stream = stream

    def errors(self) -> int:
        count = 0
        for line in self.stream.readlines():
            if "error" in line:
                count += 1
        return count


def faulty_call_result(path: Path) -> int:
    total = 0
    for line in path.with_suffix(".log").open(encoding="utf-8").readlines():
        if "error" in line:
            total += 1
    return total


def corrected_call_result(path: Path) -> int:
    total = 0
    for line in path.with_suffix(".log").open(encoding="utf-8"):
        if "error" in line:
            total += 1
    return total


def kept_call_result(path: Path, wanted: list[int]) -> int:
    lines = path.with_suffix(".log").open(encoding="utf-8").readlines()
    total = 0
    for index in wanted:
        if index < len(lines) and "error" in lines[index]:
            total += 1
    return total


def hint_call_result(path: Path) -> int:
    total = 0
    for line in path.with_suffix(".log").open(encoding="utf-8").readlines(4096):
        if "error" in line:
            total += 1
    return total


def other_call_result(path: Path) -> int:
    total = 0
    for line in io.StringIO(path.with_suffix(".log").read_text()).readlines():
        if "error" in line:
            total += 1
    return total


def kept_site_usb_mounts(mounts_path: Path) -> list[str]:
    with mounts_path.open() as f:
        mounts = f.readlines()
    media: list[str] = []
    for line in mounts:
        parts = line.split()
        if len(parts) < 2:
            continue
        mount = parts[1]
        if not mount.startswith("/media"):
            continue
        media.append(mount)
    return media


def furb129_builtin_with_loop(name: str) -> int:
    total = 0
    with open(name, encoding="utf-8") as handle:
        for line in handle.readlines():
            if line.strip():
                total += 1
    return total


def furb129_builtin_generator(name: str) -> int:
    with open(name, encoding="utf-8") as handle:
        return sum(1 for line in handle.readlines() if line.strip())


def furb129_builtin_direct_loop(name: str) -> int:
    total = 0
    for line in open(name, encoding="utf-8").readlines():
        if line.strip():
            total += 1
    return total


def furb129_io_open(name: str) -> int:
    total = 0
    with io.open(name, encoding="utf-8") as handle:
        for line in handle.readlines():
            if line.strip():
                total += 1
    return total


def furb129_path_call(name: str) -> int:
    total = 0
    with Path(name).open(encoding="utf-8") as handle:
        for line in handle.readlines():
            if line.strip():
                total += 1
    return total


def furb129_pathlib_path_call(name: str) -> int:
    total = 0
    with pathlib.Path(name).open(encoding="utf-8") as handle:
        for line in handle.readlines():
            if line.strip():
                total += 1
    return total
