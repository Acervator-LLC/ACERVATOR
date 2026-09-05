# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Application settings with TOML persistence.

``AppSettings`` declares every persisted field and ``SettingsManager`` reads
and writes it under ``_DEFAULT_DIR``. ``_save`` writes ``settings.toml`` when
``_CAN_WRITE_TOML`` and ``settings.json`` otherwise. Every ``get`` and ``set``
holds one ``threading.RLock`` shared by every ``SettingsManager``.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # Python 3.11+

    _CAN_READ_TOML = True
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]

        _CAN_READ_TOML = True
    except ImportError:
        _CAN_READ_TOML = False

try:
    import tomli_w

    _CAN_WRITE_TOML = True
except ImportError:
    _CAN_WRITE_TOML = False


class IncrementStyle(str, Enum):
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"


class FoldDistributeMode(str, Enum):
    EQUAL = "equal"
    LOGARITHMIC = "logarithmic"


class FoldTarget(str, Enum):
    ALL_BUY = "all_buy"
    X_BUY = "x_buy"
    MOST_RECENT_BUY = "most_recent_buy"


class DistributeTarget(str, Enum):
    ALL_SELL = "all_sell"
    X_SELL = "x_sell"
    MOST_RECENT_SELL = "most_recent_sell"


class BotVisibility(str, Enum):
    ORDERBOOK = "orderbook"
    INTERNAL = "internal"


class LogPeriodicity(str, Enum):
    DAILY = "24h"
    WEEKLY = "1_week"
    MONTHLY = "1_month"
    YEARLY = "1_year"


class VisualTheme(str, Enum):
    CYBERPUNK_DARK = "cyberpunk_dark"
    NEON_LIGHT = "neon_light"
    CLASSIC_TERMINAL = "classic_terminal"
    MINIMAL_MODERN = "minimal_modern"
    GLASS_METAL = "glass_metal"


@dataclass
class ProfitFoldingSettings:
    """Field defaults for the ``AppSettings.profit_folding`` group."""

    active: bool = True
    mode: FoldDistributeMode = FoldDistributeMode.EQUAL
    fold_target: FoldTarget = FoldTarget.ALL_BUY
    fold_target_count: int = 5
    distribute_target: DistributeTarget = DistributeTarget.ALL_SELL
    distribute_target_count: int = 5


@dataclass
class DataLoggingSettings:
    """Field defaults for the ``AppSettings.data_logging`` group."""

    ta_signal_logging: bool = True
    highlight_trade_proximity: bool = True
    active_periodicities: list[str] = field(
        default_factory=lambda: [
            LogPeriodicity.DAILY.value,
            LogPeriodicity.WEEKLY.value,
        ]
    )


@dataclass
class AIMonitorSettings:
    """Field defaults for the ``AppSettings.ai_monitor`` group."""

    api_key: str = ""
    interval_hours: float = 4.0
    connect_phrase: str = ""
    confirm_phrase: str = ""
    enabled: bool = False
    auto_handshake: bool = True
    log_feedback: bool = True


@dataclass
class ExchangeConfig:
    """One exchange entry in ``AppSettings.exchanges``.

    ``add_exchange`` stores this as a dict keyed by ``exchange_id``.
    """

    exchange_id: str = ""
    display_name: str = ""
    api_key_enc: str = ""
    api_secret_enc: str = ""
    # Set only for an exchange_id in ccxt_connector.PASSPHRASE_EXCHANGES.
    passphrase_enc: str = ""
    enabled: bool = True
    hardware_mode: bool = False  # True = credentials read from USB, not the vault
    hw_volume_serial: str = ""  # USB volume serial that holds .acervator_auth


@dataclass
class AppSettings:
    """Every field ``SettingsManager`` persists.

    ``_save`` writes this dataclass through ``asdict`` and ``_apply_dict``
    reads it back.
    """

    # schema_version bumps for a renamed or re-meant field, never for a new one.
    schema_version: int = 1

    username: str = ""
    # main.py rewrites this with the running build's version at startup.
    app_version: str = ""

    exchanges: list[dict] = field(default_factory=list)  # asdict(ExchangeConfig)

    default_position_count: int = 10
    default_target_balance: float = 200.0
    position_distance_pct: float = 2.0
    increment_style: str = IncrementStyle.LINEAR.value

    profit_folding: dict = field(
        default_factory=lambda: asdict(ProfitFoldingSettings())
    )

    bot_visibility: str = BotVisibility.ORDERBOOK.value
    aggressive_trading: bool = False

    theme: str = VisualTheme.CYBERPUNK_DARK.value
    accent_color: str = "#00ffcc"

    # These four mirror the font widgets in settings_dialog._create_theme_tab.
    font_family: str = "Segoe UI"
    font_size: int = 11
    heading_font_size: int = 14
    log_font_size: int = 10

    ai_monitor: dict = field(default_factory=lambda: asdict(AIMonitorSettings()))

    data_logging: dict = field(default_factory=lambda: asdict(DataLoggingSettings()))


_DEFAULT_DIR = Path.home() / ".acervator"


class SettingsManager:
    """Thread-safe reader and writer for one ``AppSettings``.

    ``get`` and ``set`` address a top-level field while ``get_nested`` and
    ``set_nested`` address a key inside ``profit_folding``, ``ai_monitor`` or
    ``data_logging``.
    """

    _lock = threading.RLock()

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self._dir = config_dir or _DEFAULT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path_toml = self._dir / "settings.toml"
        self._path_json = self._dir / "settings.json"
        self._settings = AppSettings()
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        """Return the ``AppSettings`` attribute named *key*, or *default*."""
        with self._lock:
            return getattr(self._settings, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set the ``AppSettings`` attribute *key* and call ``_save``.

        A *key* that ``AppSettings`` does not declare raises ``KeyError``.
        """
        with self._lock:
            if not hasattr(self._settings, key):
                raise KeyError(f"Unknown setting: {key}")
            setattr(self._settings, key, value)
            self._save()

    def get_nested(self, group: str, key: str, default: Any = None) -> Any:
        """Return *key* from the ``AppSettings`` dict field *group*, or *default*."""
        with self._lock:
            group_dict = getattr(self._settings, group, {})
            if isinstance(group_dict, dict):
                return group_dict.get(key, default)
            return default

    def set_nested(self, group: str, key: str, value: Any) -> None:
        """Write *value* at *key* inside the ``AppSettings`` dict field *group*.

        A *group* that is not a dict raises ``KeyError``.
        """
        with self._lock:
            group_dict = getattr(self._settings, group, None)
            if not isinstance(group_dict, dict):
                raise KeyError(f"Setting '{group}' is not a dict")
            group_dict[key] = value
            self._save()

    def get_all(self) -> dict:
        """Return ``_settings`` as a dict; ``asdict`` deep-copies every value."""
        with self._lock:
            return asdict(self._settings)

    def reset_defaults(self) -> None:
        """Replace ``_settings`` with a fresh ``AppSettings`` and call ``_save``."""
        with self._lock:
            self._settings = AppSettings()
            self._save()

    def add_exchange(self, config: ExchangeConfig) -> None:
        """Replace any entry sharing ``config.exchange_id``, then append it."""
        with self._lock:
            exchanges = self._settings.exchanges
            exchanges = [
                e for e in exchanges if e.get("exchange_id") != config.exchange_id
            ]
            exchanges.append(asdict(config))
            self._settings.exchanges = exchanges
            self._save()

    def get_exchange(self, exchange_id: str) -> Optional[dict]:
        with self._lock:
            for e in self._settings.exchanges:
                if e.get("exchange_id") == exchange_id:
                    return deepcopy(e)
            return None

    def list_exchanges(self) -> list[dict]:
        with self._lock:
            return deepcopy(self._settings.exchanges)

    def remove_exchange(self, exchange_id: str) -> None:
        with self._lock:
            self._settings.exchanges = [
                e
                for e in self._settings.exchanges
                if e.get("exchange_id") != exchange_id
            ]
            self._save()

    def _save(self) -> None:
        """Write ``asdict(_settings)`` to ``_path_toml`` when ``_CAN_WRITE_TOML``.

        Without ``tomli_w`` the same dict goes to ``_path_json``.
        """
        data = asdict(self._settings)
        if _CAN_WRITE_TOML:
            with open(self._path_toml, "wb") as f:
                tomli_w.dump(data, f)
        else:
            with open(self._path_json, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Read ``_path_toml`` or ``_path_json`` into ``_settings``.

        A file whose ``schema_version`` is below ``AppSettings.schema_version``
        passes through ``_migrate`` first; a higher one is logged and dropped.
        """
        loaded: Optional[dict] = None
        source_path: Optional[Path] = None

        if _CAN_READ_TOML and self._path_toml.exists():
            with open(self._path_toml, "rb") as f:
                loaded = tomllib.load(f)
            source_path = self._path_toml
        elif self._path_json.exists():
            with open(self._path_json, "r") as f:
                loaded = json.load(f)
            source_path = self._path_json

        if loaded:
            current = AppSettings().schema_version
            disk_ver = int(loaded.get("schema_version", 0))
            if disk_ver > current:
                import logging as _logging

                _logging.getLogger(__name__).warning(
                    "Settings on disk have schema_version=%d, current=%d. "
                    "Running with defaults. Disk file preserved at %s.",
                    disk_ver,
                    current,
                    source_path,
                )
                return
            if disk_ver < current:
                loaded = self._migrate(loaded, disk_ver, current)
            self._apply_dict(loaded)

    def _migrate(self, data: dict, from_v: int, to_v: int) -> dict:
        """Apply each ``MIGRATIONS`` entry starting inside ``[from_v, to_v)``.

        Each applied entry stamps *data* with its own ``schema_version``.
        """
        for step_from, step_to, fn in self.MIGRATIONS:
            if from_v <= step_from < to_v:
                data = fn(data)
                data["schema_version"] = step_to
        return data

    # Triples of (from_version, to_version, callable), applied in order.
    MIGRATIONS: list[tuple[int, int, Any]] = []

    def _apply_dict(self, data: dict) -> None:
        """Copy every ``AppSettings`` field that *data* carries onto ``_settings``.

        A field absent from *data* keeps its ``AppSettings`` default.
        """
        defaults = asdict(AppSettings())
        for key, default_val in defaults.items():
            if key in data:
                setattr(self._settings, key, data[key])
