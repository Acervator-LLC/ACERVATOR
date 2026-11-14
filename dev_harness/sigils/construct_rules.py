"""`take` gives a construct sigil the ruff rules its disciplines house inside its construct's scope."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

HOUSE = Path(__file__).resolve().parent.parent / "disciplines"
SCOPE_FILE = Path(__file__).with_name("construct_scope.json")
RULES_FILE = "rules.json"
UNPLACED_FILE = "unplaced.json"
TOOL = "ruff"
ERROR_CLASS = "PLE"
UNDEFINED_NAMES = ("F821", "F822", "F823")
NOT_NAMED = "housed by {housing}, which the card does not name"


class HouseFault(Exception):
    """A discipline or `SCOPE_FILE` holds nothing `take` can read."""


@dataclass(frozen=True)
class Taken:
    """The `rules` one construct takes from its `disciplines`, and each scope rule `left` out."""

    construct: str
    disciplines: tuple[str, ...]
    rules: tuple[str, ...]
    preview: tuple[str, ...]
    holding: tuple[str, ...]
    left: dict[str, str]

    def settings(self, function: str) -> dict[str, str]:
        """Return the card settings naming `function`, the disciplines, the scope and the rules taken."""
        return {
            "function": function,
            "disciplines": " ".join(self.disciplines),
            "scope": f"each ruff rule {SCOPE_FILE.name} places on the {self.construct} construct",
            "rules": " ".join(self.rules),
            "preview_rules": " ".join(self.preview),
            "holding_rules": " ".join(self.holding),
            "error_class": ERROR_CLASS,
            "undefined_names": " ".join(UNDEFINED_NAMES),
        }


def _load(path: Path) -> dict[str, Any]:
    """Return the JSON object at `path`, or raise `HouseFault`."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        message = f"cannot read {path.name}: {exc}"
        raise HouseFault(message) from exc
    if not isinstance(data, dict):
        message = f"{path.name} holds no JSON object"
        raise HouseFault(message)
    return data


@cache
def disciplines() -> tuple[str, ...]:
    """Return the name of each `HOUSE` folder holding a `RULES_FILE`."""
    return tuple(sorted(path.parent.name for path in HOUSE.glob(f"*/{RULES_FILE}")))


@cache
def housing() -> dict[str, tuple[str, ...]]:
    """Return the disciplines housing each `TOOL` rule, read from each `RULES_FILE`."""
    housed: dict[str, list[str]] = {}
    for name in disciplines():
        for row in _load(HOUSE / name / RULES_FILE)["rules"]:
            if row["tool"] == TOOL:
                housed.setdefault(row["rule"], []).append(name)
    return {rule: tuple(names) for rule, names in housed.items()}


@cache
def unplaced() -> dict[str, str]:
    """Return the text `UNPLACED_FILE` holds for each `TOOL` rule it lists."""
    rows = _load(HOUSE / UNPLACED_FILE)["rules"]
    return {row["rule"]: row["reason"] for row in rows if row["tool"] == TOOL}


@cache
def scope() -> dict[str, dict[str, Any]]:
    """Return each `TOOL` rule's `SCOPE_FILE` row, naming its constructs or none."""
    rules: dict[str, dict[str, Any]] = _load(SCOPE_FILE)["rules"]
    return rules


@cache
def constructs() -> tuple[str, ...]:
    """Return the construct names the `SCOPE_FILE` card measured."""
    return tuple(_load(SCOPE_FILE)["card"]["constructs"])


def take(construct: str, named: Sequence[str]) -> Taken:
    """Return the `Taken` scope rules of `construct` that the `named` disciplines house."""
    if construct not in constructs():
        message = f"no construct {construct}; {SCOPE_FILE.name} reads {list(constructs())}"
        raise HouseFault(message)
    unknown = sorted(set(named) - set(disciplines()))
    if unknown or not named:
        message = f"no discipline {unknown or 'named'} in {HOUSE.name}"
        raise HouseFault(message)
    rules: list[str] = []
    preview: list[str] = []
    left: dict[str, str] = {}
    for code, row in scope().items():
        if construct not in row.get("constructs", ()):
            continue
        housed_by = housing().get(code, ())
        if set(housed_by) & set(named) and "no_forms" in row:
            left[code] = row["no_forms"]
        elif set(housed_by) & set(named):
            rules.append(code)
            if row.get("preview"):
                preview.append(code)
        elif housed_by:
            left[code] = NOT_NAMED.format(housing=", ".join(housed_by))
        elif code in unplaced():
            left[code] = unplaced()[code]
    holding = tuple(
        code for code in rules if code.startswith(ERROR_CLASS) or code in UNDEFINED_NAMES
    )
    return Taken(construct, tuple(named), tuple(rules), tuple(preview), holding, left)
