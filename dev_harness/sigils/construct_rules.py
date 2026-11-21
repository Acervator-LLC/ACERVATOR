"""`take` gives a construct sigil, and `hold` a tool sigil, the scope rules its disciplines house under its characteristics."""

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from itertools import takewhile
from pathlib import Path
from typing import Any, ClassVar

HOUSE = Path(__file__).resolve().parent.parent / "disciplines"
SCOPE_FILE = Path(__file__).with_name("construct_scope.json")
RULES_FILE = "rules.json"
SKILL_FILE = "SKILL.md"
FRONT_MATTER = "---"
ARCHETYPES_LINE = re.compile(r"archetypes:\s*\[(?P<listed>[^\]]*)\]\s*")
UNPLACED_FILE = "unplaced.json"
TOOL = "ruff"
ERROR_CLASS = "PLE"
UNDEFINED_NAMES = ("F821", "F822", "F823")
# Their import moved under TYPE_CHECKING makes typing.get_type_hints raise NameError.
TYPING_ONLY_IMPORTS = ("TC001", "TC002", "TC003")
NOT_NAMED = "housed by {housing}, which the card does not name"
UNHOUSED = (
    "no discipline houses it and unplaced.json does not list it: the house holds only "
    "the rules the Coding Archetype or a sigil runs, and neither runs it"
)
LEFT_BECAUSE = (
    "each is a scope rule no discipline the card names houses under a characteristic the "
    "card names; its text is the unplaced.json row, the discipline and characteristics "
    "that house it, or why the house holds no row for it"
)

Place = tuple[str, str]


class HouseFault(Exception):
    """A discipline or `SCOPE_FILE` holds nothing `take` or `hold` can read."""


@dataclass(frozen=True)
class Taken:
    """The `rules` one construct takes from its `disciplines` and `characteristics`, and each scope rule `left` out."""

    construct: str
    disciplines: tuple[str, ...]
    characteristics: tuple[str, ...]
    rules: tuple[str, ...]
    preview: tuple[str, ...]
    holding: tuple[str, ...]
    optimizing: tuple[str, ...]
    left: dict[str, str]
    left_because: ClassVar[str] = LEFT_BECAUSE

    def settings(self, function: str) -> dict[str, str]:
        """Return the card settings naming `function`, the disciplines, characteristics, scope and rules taken."""
        return {
            "function": function,
            "disciplines": " ".join(self.disciplines),
            "characteristics": " ".join(self.characteristics),
            "scope": f"each ruff rule {SCOPE_FILE.name} places on the {self.construct} construct",
            "rules": " ".join(self.rules),
            "preview_rules": " ".join(self.preview),
            "holding_rules": " ".join(self.holding),
            "error_class": ERROR_CLASS,
            "undefined_names": " ".join(UNDEFINED_NAMES),
        }


@dataclass(frozen=True)
class Held:
    """The `rules` of one `tool` a tool sigil holds from its `disciplines` and `characteristics`, and each scope rule `left`."""

    tool: str
    disciplines: tuple[str, ...]
    characteristics: tuple[str, ...]
    rules: tuple[str, ...]
    left: dict[str, str]


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
def characteristics_of(name: str) -> tuple[str, ...]:
    """Return each characteristic the `RULES_FILE` of discipline `name` lists."""
    return tuple(_load(HOUSE / name / RULES_FILE)["characteristics"])


@cache
def archetypes(name: str) -> tuple[str, ...]:
    """Return each archetype the `ARCHETYPES_LINE` of discipline `name`'s `SKILL_FILE` front matter lists."""
    path = HOUSE / name / SKILL_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        message = f"cannot read {name}/{SKILL_FILE}: {exc}"
        raise HouseFault(message) from exc
    if not lines or lines[0] != FRONT_MATTER:
        return ()
    for line in takewhile(lambda line: line != FRONT_MATTER, lines[1:]):
        found = ARCHETYPES_LINE.fullmatch(line)
        if found:
            return tuple(
                entry.strip() for entry in found["listed"].split(",") if entry.strip()
            )
    return ()


@cache
def _housed() -> dict[tuple[str, str], tuple[Place, ...]]:
    """Return each (discipline, characteristic) `Place` housing each (tool, rule) pair, read from each `RULES_FILE`."""
    housed: dict[tuple[str, str], list[Place]] = {}
    for name in disciplines():
        for row in _load(HOUSE / name / RULES_FILE)["rules"]:
            places = housed.setdefault((row["tool"], row["rule"]), [])
            places.extend((name, characteristic) for characteristic in row["characteristics"])
    return {pair: tuple(places) for pair, places in housed.items()}


@cache
def _unplaced() -> dict[tuple[str, str], str]:
    """Return the text `UNPLACED_FILE` holds for each (tool, rule) pair it lists."""
    rows = _load(HOUSE / UNPLACED_FILE)["rules"]
    return {(row["tool"], row["rule"]): row["reason"] for row in rows}


def housing(tool: str = TOOL) -> dict[str, tuple[str, ...]]:
    """Return the disciplines housing each `tool` rule."""
    return {
        rule: tuple(dict.fromkeys(name for name, _characteristic in places))
        for (owner, rule), places in _housed().items()
        if owner == tool
    }


def unplaced(tool: str = TOOL) -> dict[str, str]:
    """Return the `UNPLACED_FILE` text for each `tool` rule it lists."""
    return {rule: reason for (owner, rule), reason in _unplaced().items() if owner == tool}


def places(tool: str, rule: str) -> tuple[Place, ...]:
    """Return each (discipline, characteristic) `Place` a `RULES_FILE` gives `tool` rule `rule`."""
    return _housed().get((tool, rule), ())


def house_rules(tool: str) -> tuple[str, ...]:
    """Return each `tool` rule a `RULES_FILE` houses or `UNPLACED_FILE` lists, sorted."""
    return tuple(sorted(set(housing(tool)) | set(unplaced(tool))))


def _housing_text(places: Iterable[Place]) -> str:
    """Return `places` as each discipline, then `under` and the characteristics housing the rule there."""
    grouped: dict[str, list[str]] = {}
    for name, characteristic in places:
        grouped.setdefault(name, []).append(characteristic)
    return "; ".join(f"{name} under {', '.join(found)}" for name, found in grouped.items())


def why_left(
    tool: str, rule: str, named: Sequence[str], characteristics: Sequence[str]
) -> str | None:
    """Return why no `named` discipline houses `tool` rule `rule` under one of `characteristics`, or None when one does."""
    places = _housed().get((tool, rule), ())
    if any(name in named and found in characteristics for name, found in places):
        return None
    if places:
        return NOT_NAMED.format(housing=_housing_text(places))
    return _unplaced().get((tool, rule), UNHOUSED)


def _check_named(named: Sequence[str], characteristics: Sequence[str]) -> None:
    """Raise `HouseFault` unless `named` lists only `disciplines`, and `characteristics` only theirs."""
    unknown = sorted(set(named) - set(disciplines()))
    if unknown or not named:
        message = f"no discipline {unknown or 'named'} in {HOUSE.name}"
        raise HouseFault(message)
    listed = {found for name in named for found in characteristics_of(name)}
    stray = sorted(set(characteristics) - listed)
    if stray or not characteristics:
        message = f"no characteristic {stray or 'named'} in {', '.join(named)}"
        raise HouseFault(message)


@cache
def scope() -> dict[str, dict[str, Any]]:
    """Return each `TOOL` rule's `SCOPE_FILE` row, naming its constructs or none."""
    rules: dict[str, dict[str, Any]] = _load(SCOPE_FILE)["rules"]
    return rules


@cache
def constructs() -> tuple[str, ...]:
    """Return the construct names the `SCOPE_FILE` card measured."""
    return tuple(_load(SCOPE_FILE)["card"]["constructs"])


def take(construct: str, named: Sequence[str], characteristics: Sequence[str]) -> Taken:
    """Return the `Taken` scope rules of `construct` that the `named` disciplines house under `characteristics`."""
    if construct not in constructs():
        message = f"no construct {construct}; {SCOPE_FILE.name} reads {list(constructs())}"
        raise HouseFault(message)
    _check_named(named, characteristics)
    rules: list[str] = []
    preview: list[str] = []
    left: dict[str, str] = {}
    for code, row in scope().items():
        if construct not in row.get("constructs", ()):
            continue
        why = why_left(TOOL, code, named, characteristics)
        if why is None and "no_forms" in row:
            left[code] = row["no_forms"]
        elif why is None:
            rules.append(code)
            if row.get("preview"):
                preview.append(code)
        else:
            left[code] = why
    holding = tuple(
        code
        for code in rules
        if code.startswith(ERROR_CLASS) or code in UNDEFINED_NAMES
    )
    optimizing = tuple(code for code in rules if code in TYPING_ONLY_IMPORTS)
    return Taken(
        construct,
        tuple(named),
        tuple(characteristics),
        tuple(rules),
        tuple(preview),
        holding,
        optimizing,
        left,
    )


def hold(
    tool: str, rules: Iterable[str], named: Sequence[str], characteristics: Sequence[str]
) -> Held:
    """Return the `Held` scope `rules` of `tool` that the `named` disciplines house under `characteristics`."""
    _check_named(named, characteristics)
    held: list[str] = []
    left: dict[str, str] = {}
    for rule in rules:
        why = why_left(tool, rule, named, characteristics)
        if why is None:
            held.append(rule)
        else:
            left[rule] = why
    return Held(tool, tuple(named), tuple(characteristics), tuple(held), left)
