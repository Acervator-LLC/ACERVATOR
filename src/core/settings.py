"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
settings.py — Application settings with TOML persistence
=========================================================
Central configuration store for the Acervator.  Every setting
from the spec is represented here with sensible defaults.  Settings are
persisted to ``~/.acervator/settings.toml`` (or an explicit path)
and reloaded on startup.

Thread safety: Settings uses a ``threading.RLock`` so any thread can
read/write safely.  GUI and bot threads share the same instance.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# We try tomllib (Python 3.11+) for reading and tomli_w for writing.
# If unavailable we fall back to JSON persistence.
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


# ---------------------------------------------------------------------------
# Enums for constrained choices
# ---------------------------------------------------------------------------
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
    ORDERBOOK = "orderbook"  # Standard order-book listing
    INTERNAL = "internal"  # Tracked internally per container


class LogPeriodicity(str, Enum):
    DAILY = "24h"
    WEEKLY = "1_week"
    MONTHLY = "1_month"
    YEARLY = "1_year"


# ---------------------------------------------------------------------------
# Visual theme descriptors
# ---------------------------------------------------------------------------
class VisualTheme(str, Enum):
    CYBERPUNK_DARK = "cyberpunk_dark"
    NEON_LIGHT = "neon_light"
    CLASSIC_TERMINAL = "classic_terminal"
    MINIMAL_MODERN = "minimal_modern"
    GLASS_METAL = "glass_metal"


# ---------------------------------------------------------------------------
# Dataclasses for nested setting groups
# ---------------------------------------------------------------------------
@dataclass
class ProfitFoldingSettings:
    """Configuration for the Profit Folding / Upward Distribution engine."""

    active: bool = True
    mode: FoldDistributeMode = FoldDistributeMode.EQUAL
    fold_target: FoldTarget = FoldTarget.ALL_BUY
    fold_target_count: int = 5  # Used when fold_target == X_BUY
    distribute_target: DistributeTarget = DistributeTarget.ALL_SELL
    distribute_target_count: int = 5  # Used when distribute_target == X_SELL


@dataclass
class DataLoggingSettings:
    """Configuration for data and trade logging."""

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
    """Configuration for the AI feedback monitor.

    v3.24.36 (C12). The Settings dialog has written an ``ai_monitor``
    dict since the AI Monitor tab shipped, but ``AppSettings`` had no
    such field — so ``SettingsManager.set()`` raised
    ``KeyError: Unknown setting: ai_monitor`` on every save, the dialog
    swallowed it, and the operator's AI Monitor configuration was
    discarded every time. Defaults mirror the dialog's own widget
    defaults so an unsaved install and a saved one agree.
    """

    api_key: str = ""
    interval_hours: float = 4.0
    connect_phrase: str = ""
    confirm_phrase: str = ""
    enabled: bool = False
    auto_handshake: bool = True
    log_feedback: bool = True


@dataclass
class ExchangeConfig:
    """Per-exchange configuration (API key stored as encrypted token)."""

    exchange_id: str = ""
    display_name: str = ""
    api_key_enc: str = ""  # Encrypted
    api_secret_enc: str = ""  # Encrypted
    passphrase_enc: str = ""  # Encrypted (only for Coinbase, KuCoin, OKX, Bitget)
    enabled: bool = True
    # Hardware USB key authentication (R25: added via usb_auth.py)
    hardware_mode: bool = False  # True = credentials only accessible via USB key
    hw_volume_serial: str = ""  # USB volume serial that holds the auth file


# ---------------------------------------------------------------------------
# Main settings object
# ---------------------------------------------------------------------------
@dataclass
class AppSettings:
    """
    Root settings container.  Every field maps to a UI control in the
    Settings menu and is persisted to disk.
    """

    # -- Schema versioning (v3.15.97) -----------------------------------
    # Bump SETTINGS_SCHEMA_VERSION when adding/removing/renaming fields with
    # SEMANTIC changes. Adding a new field with a safe default does NOT
    # require a bump (forward-compatible via _apply_dict). RENAMING or
    # SEMANTIC change DOES require a bump + migration step in
    # SettingsManager._migrate.
    schema_version: int = 1

    # -- User -----------------------------------------------------------
    username: str = ""
    app_version: str = ""  # Tracks which build created these settings

    # -- Exchanges (list of ExchangeConfig dicts) -----------------------
    exchanges: list[dict] = field(default_factory=list)

    # -- Trading defaults -----------------------------------------------
    default_position_count: int = 10
    default_target_balance: float = 200.0
    position_distance_pct: float = 2.0  # Percentage between grid levels
    increment_style: str = IncrementStyle.LINEAR.value

    # -- Profit folding / upward distribution ---------------------------
    profit_folding: dict = field(
        default_factory=lambda: asdict(ProfitFoldingSettings())
    )

    # -- Bot visibility -------------------------------------------------
    bot_visibility: str = BotVisibility.ORDERBOOK.value
    aggressive_trading: bool = False

    # -- Visual ---------------------------------------------------------
    theme: str = VisualTheme.CYBERPUNK_DARK.value
    accent_color: str = "#00ffcc"  # Neon teal default

    # -- Typography (v3.24.36, C12) -------------------------------------
    # The Settings dialog has had these four controls since the Fonts
    # section shipped, and wrote them on every Save. AppSettings had no
    # matching fields, so `SettingsManager.set()` raised
    # `KeyError: Unknown setting: font_size` (etc.), `_save()` caught it,
    # printed to stderr and closed the dialog reporting success. Four
    # font choices were discarded on every save with no visible failure.
    #
    # Defaults mirror the dialog's own widget defaults (settings_dialog
    # :520, :526, :533, :539) so an unsaved install and a saved one agree
    # rather than jumping the first time the operator presses Save.
    font_family: str = "Segoe UI"
    font_size: int = 11
    heading_font_size: int = 14
    log_font_size: int = 10

    # -- AI Monitor (v3.24.36, C12) -------------------------------------
    ai_monitor: dict = field(default_factory=lambda: asdict(AIMonitorSettings()))

    # -- Logging --------------------------------------------------------
    data_logging: dict = field(default_factory=lambda: asdict(DataLoggingSettings()))


# ---------------------------------------------------------------------------
# Settings manager — singleton pattern with file persistence
# ---------------------------------------------------------------------------
_DEFAULT_DIR = Path.home() / ".acervator"


class SettingsManager:
    """
    Thread-safe, singleton-friendly settings store.

    Usage::

        sm = SettingsManager()          # Loads from default path
        sm.get("username")              # → "satoshi"
        sm.set("username", "hal")       # Updates + auto-saves
        sm.get_nested("profit_folding", "active")  # → True
    """

    _lock = threading.RLock()

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self._dir = config_dir or _DEFAULT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path_toml = self._dir / "settings.toml"
        self._path_json = self._dir / "settings.json"  # fallback
        self._settings = AppSettings()
        self._load()

    # -- Public API -----------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a top-level setting by attribute name."""
        with self._lock:
            return getattr(self._settings, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a top-level setting and persist to disk."""
        with self._lock:
            if not hasattr(self._settings, key):
                raise KeyError(f"Unknown setting: {key}")
            setattr(self._settings, key, value)
            self._save()

    def get_nested(self, group: str, key: str, default: Any = None) -> Any:
        """Retrieve a value from a nested dict setting (e.g. profit_folding)."""
        with self._lock:
            group_dict = getattr(self._settings, group, {})
            if isinstance(group_dict, dict):
                return group_dict.get(key, default)
            return default

    def set_nested(self, group: str, key: str, value: Any) -> None:
        """Set a value inside a nested dict setting."""
        with self._lock:
            group_dict = getattr(self._settings, group, None)
            if not isinstance(group_dict, dict):
                raise KeyError(f"Setting '{group}' is not a dict")
            group_dict[key] = value
            self._save()

    def get_all(self) -> dict:
        """Return a deep copy of all settings as a plain dict."""
        with self._lock:
            return asdict(self._settings)

    def reset_defaults(self) -> None:
        """Restore factory defaults."""
        with self._lock:
            self._settings = AppSettings()
            self._save()

    # -- Exchange helpers ------------------------------------------------
    def add_exchange(self, config: ExchangeConfig) -> None:
        """Add or update an exchange configuration."""
        with self._lock:
            exchanges = self._settings.exchanges
            # Replace if exchange_id already exists
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

    # -- Persistence ----------------------------------------------------
    def _save(self) -> None:
        """Write settings to TOML (preferred) or JSON (fallback)."""
        data = asdict(self._settings)
        if _CAN_WRITE_TOML:
            with open(self._path_toml, "wb") as f:
                tomli_w.dump(data, f)
        else:
            with open(self._path_json, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Load settings from disk, falling back to defaults.

        v3.15.97: schema-version-aware. If the loaded config has a
        schema_version older than the current AppSettings.schema_version,
        run the migration chain BEFORE applying. If the loaded config has
        a NEWER schema_version, refuse to load it silently — that path
        means a downgrade and a downgrade should be explicit.
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
                # Newer schema on disk than the running build. Refuse
                # silent load — write a sidecar warning so operator sees it.
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
        """Run the migration chain from `from_v` to `to_v`.

        Each migration step is a function that takes a dict and returns
        a dict. They are chained in order. Add a new entry to MIGRATIONS
        below for each schema bump.
        """
        for step_from, step_to, fn in self.MIGRATIONS:
            if from_v <= step_from < to_v:
                data = fn(data)
                data["schema_version"] = step_to
        return data

    # Migration chain. Ordered list of (from_version, to_version, callable).
    # When you bump AppSettings.schema_version from N to N+1, append:
    #   (N, N+1, _migrate_N_to_N_plus_1)
    # Each callable accepts the prior-version dict and returns the new dict.
    MIGRATIONS: list[tuple[int, int, Any]] = []

    def _apply_dict(self, data: dict) -> None:
        """Merge loaded dict into the settings dataclass, preserving
        any new default fields not present in older config files."""
        defaults = asdict(AppSettings())
        for key, default_val in defaults.items():
            if key in data:
                setattr(self._settings, key, data[key])
            # else: keep the default — forward-compatible
