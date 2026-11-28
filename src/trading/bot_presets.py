"""``Preset`` is a named set of every bot setting the fleet menu does not set.

``SETTING_RULES`` holds the rule each ``PRESET_FIELDS`` value passes, read from
``CONTROL_SPECS`` where that table names a span or a list. ``PresetStore``
saves and reads a ``Preset`` by name in the file ``resolve_preset_path`` names.
``PresetStore.read`` answers ``BASELINE_NAME`` with ``baseline_preset`` over the
records of the fleet the program has loaded.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import MISSING, dataclass, fields
from enum import Enum
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Optional

from ..core.io_utils import atomic_write_json
from ..core.log_paths import resolve_preset_path
from ..core.settings import DEFAULT_ENABLE_PHANTOMS, DEFAULT_LOCK_CANDLE_COUNT
from ..exchange.timeframes import ALL_TIMEFRAMES
from ..gui.main_tabs.bot_wizard_surface import NUMBER_FIELDS
from ..gui.main_tabs.live_settings_tab_surface import (
    CHECK,
    COMBO_DATA,
    COMBO_TEXT,
    CONTROL_SPECS,
    DOUBLE_SPIN,
    SPIN,
)
from .container.config import (
    ASSET_CLASS_DEFAULT,
    PHANTOM_ARGUMENTS,
    BotConfig,
    BotMode,
    as_box_figure,
    as_finite_float,
    as_whole_count,
    phantom_restore_kwargs,
)
from .container.restore import restored_config, restored_mode
from .ta_engine import DEFAULT_WEIGHTS

logger = logging.getLogger("acervator.bot")

#: The Preset ``PresetStore.read`` builds from the loaded fleet and never saves.
BASELINE_NAME = "Ekthelius's Prototyping Baseline"

#: ``BotConfig`` fields the fleet menu sets on each bot: market and Target Balance.
MENU_FIELDS = frozenset(
    {"exchange_id", "base_currency", "target_asset", "symbol", "target_balance"}
)

#: ``BotConfig`` fields naming one market: unserved timeframes and entry prices.
ONE_BOT_FIELDS = frozenset(
    {
        "ta_timeframe_unserved",
        "scrum_read_timeframe_unserved",
        "max_entry_price",
        "min_entry_price",
    }
)

#: The ``BotConfig`` field a ``Preset`` holds as its ``sector``.
SECTOR_FIELD = "asset_class"

#: The ``BotConfig`` fields a ``Preset`` holds, in declaration order.
CONFIG_FIELDS: tuple[str, ...] = tuple(
    one.name
    for one in fields(BotConfig)
    if one.name not in MENU_FIELDS | ONE_BOT_FIELDS | {SECTOR_FIELD}
)

#: The phantom settings a ``Preset`` holds, named as ``PHANTOM_ARGUMENTS`` names them.
PHANTOM_FIELDS: tuple[str, ...] = tuple(one.keyword for one in PHANTOM_ARGUMENTS)

#: Every setting a ``Preset`` holds one value for.
PRESET_FIELDS: tuple[str, ...] = CONFIG_FIELDS + PHANTOM_FIELDS

#: The store file's top-level key, and the two keys of each entry under it.
PRESETS_KEY = "presets"
SECTOR_KEY = "sector"
SETTINGS_KEY = "settings"

#: What a ``SETTING_RULES`` rule answers for a value it refuses.
REFUSED = object()

Rule = Callable[[Any], Any]


class PresetRefused(ValueError):
    """Raised for a ``Preset`` name, sector, value or save the store refuses."""


def _flag(value: Any) -> Any:
    """``value`` when its exact type is bool, else ``REFUSED``."""
    return value if type(value) is bool else REFUSED


def _whole_rule(low: int, high: int) -> Rule:
    """A rule admitting an ``as_whole_count`` count from ``low`` to ``high``."""

    def admit(value: Any) -> Any:
        count = as_whole_count(value)
        return count if count is not None and low <= count <= high else REFUSED

    return admit


def _figure_rule(low: float, high: float) -> Rule:
    """A rule admitting an ``as_box_figure`` figure from ``low`` to ``high``."""

    def admit(value: Any) -> Any:
        figure = as_box_figure(value, low, high)
        return REFUSED if figure is None else figure

    return admit


def _floor_rule(low: float) -> Rule:
    """A rule admitting an ``as_finite_float`` figure at or above ``low``."""

    def admit(value: Any) -> Any:
        figure = as_finite_float(value)
        return figure if figure is not None and figure >= low else REFUSED

    return admit


def _choice_rule(options: tuple) -> Rule:
    """A rule admitting a str ``value`` that ``options`` holds."""

    def admit(value: Any) -> Any:
        return value if type(value) is str and value in options else REFUSED

    return admit


def _weights(value: Any) -> Any:
    """``value`` as a read-only map when each name is a ``DEFAULT_WEIGHTS`` name
    and each weight an ``as_finite_float`` figure at or above zero."""
    if not isinstance(value, Mapping):
        return REFUSED
    held = {}
    for name, figure in value.items():
        weight = as_finite_float(figure)
        if name not in DEFAULT_WEIGHTS or weight is None or weight < 0.0:
            return REFUSED
        held[name] = weight
    return MappingProxyType(held)


def _timeframes(value: Any) -> Any:
    """``value`` as a tuple in ``ALL_TIMEFRAMES`` order when it lists distinct
    ``ALL_TIMEFRAMES`` names."""
    if not isinstance(value, (list, tuple)):
        return REFUSED
    if any(type(one) is not str or one not in ALL_TIMEFRAMES for one in value):
        return REFUSED
    if len(set(value)) != len(value):
        return REFUSED
    return tuple(sorted(value, key=ALL_TIMEFRAMES.index))


def _box_span(box: str) -> tuple:
    """The ``NUMBER_FIELDS`` minimum and maximum of the New Bot wizard's ``box``."""
    return NUMBER_FIELDS[box]["minimum"], NUMBER_FIELDS[box]["maximum"]


#: Rules for the ``PRESET_FIELDS`` names ``CONTROL_SPECS`` gives no span or list for.
_NAMED_RULES: dict[str, Rule] = {
    "mode": _choice_rule(tuple(one.value for one in BotMode)),
    "ta_timeframe": _choice_rule(ALL_TIMEFRAMES),
    "scrum_read_timeframe": _choice_rule(("", *ALL_TIMEFRAMES)),
    "own_ta_weights": _weights,
    "hunger_skew_max": _floor_rule(0.0),
    "whole_unit_opening_units": _whole_rule(*_box_span("whole_unit_open_units")),
    "enable_phantoms": _flag,
    "phantom_timeframes": _timeframes,
    "lock_candle_count": _whole_rule(*_box_span("lock_candles")),
}

#: The app's own phantom defaults: on, no chosen length, the coordinator's count.
_PHANTOM_DEFAULTS: dict[str, Any] = {
    "enable_phantoms": DEFAULT_ENABLE_PHANTOMS,
    "phantom_timeframes": (),
    "lock_candle_count": DEFAULT_LOCK_CANDLE_COUNT,
}


def _spec_rule(spec: Mapping) -> Optional[Rule]:
    """The rule a ``CONTROL_SPECS`` entry's kind and span or item list give, or None."""
    kind = spec.get("kind")
    span = spec.get("range")
    items = spec.get("items")
    if kind == CHECK:
        return _flag
    if kind == SPIN and span:
        return _whole_rule(*span)
    if kind == DOUBLE_SPIN and span:
        return _figure_rule(*span)
    if kind in (COMBO_DATA, COMBO_TEXT) and items:
        return _choice_rule(
            tuple(one[1] if isinstance(one, tuple) else one for one in items)
        )
    return None


def _setting_rules() -> dict[str, Rule]:
    """One rule per ``PRESET_FIELDS`` name, from ``_NAMED_RULES`` else its one
    ``CONTROL_SPECS`` entry; raises ``LookupError`` for a name neither gives."""
    specs: dict[Any, list] = {}
    for spec in CONTROL_SPECS:
        specs.setdefault(spec.get("field"), []).append(spec)
    rules: dict[str, Rule] = {}
    for name in PRESET_FIELDS:
        found = specs.get(name, [])
        rule = _NAMED_RULES.get(name)
        if rule is None and len(found) == 1:
            rule = _spec_rule(found[0])
        if rule is None:
            raise LookupError(f"no rule admits the Preset setting {name}")
        rules[name] = rule
    return rules


#: The rule each ``PRESET_FIELDS`` value passes.
SETTING_RULES: Mapping[str, Rule] = MappingProxyType(_setting_rules())


def admitted(name: str, value: Any) -> Any:
    """``value`` as ``SETTING_RULES[name]`` admits it; raises ``PresetRefused``
    naming ``name`` for a value that rule refuses."""
    held = SETTING_RULES[name](value)
    if held is REFUSED:
        raise PresetRefused(f"{name} cannot hold {value!r}")
    return held


def _field_default(name: str) -> Any:
    """``BotConfig``'s own default for the field ``name``, an enum read as its value."""
    one = next(found for found in fields(BotConfig) if found.name == name)
    if one.default_factory is not MISSING:
        default = one.default_factory()
    else:
        default = one.default
    return default.value if isinstance(default, Enum) else default


#: The app's own default for each ``PRESET_FIELDS`` name, admitted by its rule.
SETTING_DEFAULTS: Mapping[str, Any] = MappingProxyType(
    {
        name: admitted(
            name,
            _PHANTOM_DEFAULTS[name] if name in PHANTOM_FIELDS else _field_default(name),
        )
        for name in PRESET_FIELDS
    }
)


@cache
def market_sectors() -> tuple[str, ...]:
    """``ata_spm.ASSET_CLASSES``, the sectors a ``Preset`` may name, read once."""
    from .ata_spm import ASSET_CLASSES

    return tuple(ASSET_CLASSES)


@dataclass(frozen=True)
class Preset:
    """A ``name``, the ``sector`` its bots trade in, and ``settings`` holding
    one admitted value per ``PRESET_FIELDS`` name."""

    name: str
    sector: str
    settings: Mapping[str, Any]

    def __post_init__(self) -> None:
        """Raises ``PresetRefused`` for a blank ``name``, a ``sector`` outside
        ``market_sectors``, or ``settings`` not holding exactly ``PRESET_FIELDS``."""
        if type(self.name) is not str or not self.name.strip():
            raise PresetRefused(f"a Preset name is text, not {self.name!r}")
        if type(self.sector) is not str or self.sector not in market_sectors():
            raise PresetRefused(f"{self.sector!r} is not a market sector")
        if not isinstance(self.settings, Mapping):
            raise PresetRefused("a Preset's settings are a mapping")
        missing = [name for name in PRESET_FIELDS if name not in self.settings]
        unknown = sorted(str(one) for one in self.settings if one not in SETTING_RULES)
        if missing or unknown:
            raise PresetRefused(f"settings lack {missing} and hold unknown {unknown}")
        held = {name: admitted(name, self.settings[name]) for name in PRESET_FIELDS}
        object.__setattr__(self, "settings", MappingProxyType(held))


def plain(value: Any) -> Any:
    """``value`` with each mapping a dict and each tuple a list, for ``json.dumps``."""
    if isinstance(value, Mapping):
        return {key: plain(one) for key, one in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(one) for one in value]
    return value


def preset_entry(preset: Preset) -> dict:
    """The store file entry for ``preset``, its sector and ``plain`` settings."""
    return {SECTOR_KEY: preset.sector, SETTINGS_KEY: plain(preset.settings)}


def preset_from_entry(name: str, entry: Any) -> Preset:
    """The ``Preset`` a store file ``entry`` holds under ``name``; raises
    ``PresetRefused`` for an entry a ``Preset`` cannot hold."""
    if not isinstance(entry, Mapping):
        raise PresetRefused(f"the entry under {name!r} is not a mapping")
    sector = entry.get(SECTOR_KEY)
    settings = entry.get(SETTINGS_KEY)
    if not isinstance(sector, str) or not isinstance(settings, Mapping):
        raise PresetRefused(f"the entry under {name!r} lacks a sector or settings")
    return Preset(name, sector, settings)


def _vote_key(value: Any) -> str:
    """``value`` made ``plain`` as key-sorted JSON, one key per distinct value."""
    return json.dumps(plain(value), sort_keys=True)


def majority_value(values: Iterable[Any], default: Any) -> Any:
    """The value most of ``values`` hold, else ``default`` for no values or a tie
    holding ``default``; another tie answers its value seen first."""
    counts: dict[str, int] = {}
    first: dict[str, Any] = {}
    for value in values:
        key = _vote_key(value)
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, value)
    if not counts:
        return default
    top = max(counts.values())
    tied = [key for key, count in counts.items() if count == top]
    if len(tied) > 1 and _vote_key(default) in tied:
        return default
    return first[tied[0]]


def held_settings(record: Any) -> Optional[dict[str, Any]]:
    """The ``PRESET_FIELDS`` values and ``SECTOR_FIELD`` a saved-shape ``record``'s
    bot holds once ``restored_config`` loads it, phantom values for a Scrumming
    bot alone; None for a record the restore skips."""
    config_record = record.get("config") if isinstance(record, Mapping) else None
    if not isinstance(config_record, dict):
        return None
    mode = restored_mode(config_record)
    if mode is None:
        return None
    try:
        config = restored_config(mode, config_record)
    except (ValueError, TypeError):
        return None
    held: dict[str, Any] = {name: getattr(config, name) for name in CONFIG_FIELDS}
    held["mode"] = config.mode.value
    held[SECTOR_FIELD] = config.asset_class
    if mode is BotMode.SCRUMMING:
        phantom = phantom_restore_kwargs(dict(record))
        held.update(phantom)
        held["phantom_timeframes"] = phantom["phantom_timeframes"] or ()
        if phantom["lock_candle_count"] is None:
            held["lock_candle_count"] = DEFAULT_LOCK_CANDLE_COUNT
    return held


def _admitted_values(name: str, bots: list[dict[str, Any]]) -> Iterator[Any]:
    """Each ``bots`` value for ``name`` that ``SETTING_RULES[name]`` admits."""
    rule = SETTING_RULES[name]
    for bot in bots:
        if name in bot:
            value = rule(bot[name])
            if value is not REFUSED:
                yield value


def baseline_preset(records: Iterable[Any]) -> Preset:
    """``BASELINE_NAME`` holding each ``PRESET_FIELDS`` value, and its sector, at
    the ``majority_value`` the bots of the loaded ``records`` hold."""
    bots = [held for held in map(held_settings, records) if held is not None]
    settings = {
        name: majority_value(_admitted_values(name, bots), SETTING_DEFAULTS[name])
        for name in PRESET_FIELDS
    }
    sectors = [
        one[SECTOR_FIELD] for one in bots if one[SECTOR_FIELD] in market_sectors()
    ]
    return Preset(BASELINE_NAME, majority_value(sectors, ASSET_CLASS_DEFAULT), settings)


class PresetStore:
    """Saves each ``Preset`` under its name in the file at ``path`` and reads it
    back; ``BASELINE_NAME`` reads ``baseline_preset`` over ``fleet()``."""

    def __init__(
        self, fleet: Callable[[], Iterable[Any]], path: Optional[Path] = None
    ) -> None:
        self.fleet = fleet
        self.path = Path(path) if path is not None else resolve_preset_path()

    def _entries(self) -> Optional[dict]:
        """The raw entries ``PRESETS_KEY`` holds in the file, empty for a missing
        or empty file; None for a file that is not a Preset file."""
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {}
        if not raw.strip():
            return {}
        try:
            loaded = json.loads(raw)
        except ValueError as unreadable:
            logger.warning("Preset file %s is not JSON: %s", self.path, unreadable)
            return None
        entries = loaded.get(PRESETS_KEY, {}) if isinstance(loaded, dict) else None
        if not isinstance(entries, dict):
            logger.warning("Preset file %s holds no %s map", self.path, PRESETS_KEY)
            return None
        return dict(entries)

    def _readable(self, name: str, entry: Any) -> Optional[Preset]:
        """The ``Preset`` ``entry`` holds under ``name``, else None and a warning."""
        try:
            return preset_from_entry(name, entry)
        except PresetRefused as refusal:
            logger.warning("Preset %r in %s is not read: %s", name, self.path, refusal)
            return None

    def names(self) -> list[str]:
        """``BASELINE_NAME``, then each name holding a readable ``Preset``, sorted."""
        entries = self._entries() or {}
        saved = sorted(
            name
            for name, entry in entries.items()
            if name != BASELINE_NAME and self._readable(name, entry) is not None
        )
        return [BASELINE_NAME, *saved]

    def read(self, name: str) -> Optional[Preset]:
        """The ``Preset`` saved as ``name``, ``baseline_preset`` for ``BASELINE_NAME``,
        or None for a name the file holds no readable ``Preset`` under."""
        if name == BASELINE_NAME:
            return baseline_preset(self.fleet())
        entries = self._entries() or {}
        if name not in entries:
            return None
        return self._readable(name, entries[name])

    def save(self, preset: Preset) -> None:
        """Writes ``preset`` under its name, replacing a ``Preset`` saved as that name.

        Raises ``PresetRefused`` for ``BASELINE_NAME`` or a file ``_entries`` refuses.
        """
        if type(preset) is not Preset:
            raise PresetRefused(f"{type(preset).__name__} is not a Preset")
        if preset.name == BASELINE_NAME:
            raise PresetRefused(f"{BASELINE_NAME} is read from the fleet, never saved")
        entries = self._entries()
        if entries is None:
            raise PresetRefused(
                f"{self.path} is not a Preset file; it is left as it is"
            )
        entries[preset.name] = preset_entry(preset)
        atomic_write_json(self.path, {PRESETS_KEY: entries}, sort_keys=True)
