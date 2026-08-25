"""Sub-phase 2A pins — Stack Mode schema + rename + sanitize.

Locks the v3.23.25 schema changes:
  - `stack_mode` (bool) exists on BotConfig; `bulk_trading` does not.
  - `bulk_partial_on_return` retired from BotConfig.
  - `split_distance`, `stack_tranche_count_target`, `stack_spacing_mode`
    exist with expected types/defaults.
  - `_sanitize_deprecated_kwargs` drops known deprecated keys.
  - `make_bot_config(mode=SCRUMMING, bulk_trading=False, ...)` does
    NOT raise TypeError against the new schema (backwards-compat).
  - Settings widget renames + new widgets present in the tab source.
  - Restore paths in main_window.py + bot_container.py emit stack_mode
    (with bulk_trading fallback) and no longer emit the retired keys.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.bot_container import (  # noqa: E402
    BotConfig,
    BotMode,
    _sanitize_deprecated_kwargs,
    make_bot_config,
)

# ---------------------------------------------------------------------------
# BotConfig schema
# ---------------------------------------------------------------------------


class TestBotConfigSchema:
    def _fields(self):
        return {f.name: f for f in dataclasses.fields(BotConfig)}

    def test_stack_mode_field_present(self):
        f = self._fields().get("stack_mode")
        assert f is not None, "stack_mode field missing"
        assert (
            f.default is False
        ), f"stack_mode default should be False, got {f.default!r}"

    def test_bulk_trading_field_absent(self):
        assert "bulk_trading" not in self._fields(), (
            "bulk_trading field must not exist on BotConfig — it was "
            "renamed to stack_mode in v3.23.25"
        )

    def test_bulk_partial_on_return_field_absent(self):
        assert "bulk_partial_on_return" not in self._fields()

    def test_split_distance_field_present(self):
        f = self._fields().get("split_distance")
        assert f is not None
        assert f.default == 1.0

    def test_stack_tranche_count_target_present(self):
        f = self._fields().get("stack_tranche_count_target")
        assert f is not None
        assert f.default == 3

    def test_stack_spacing_mode_present(self):
        f = self._fields().get("stack_spacing_mode")
        assert f is not None
        assert f.default == "linear"


# ---------------------------------------------------------------------------
# _sanitize_deprecated_kwargs — the position_count-class safety net
# ---------------------------------------------------------------------------


class TestSanitizeDeprecatedKwargs:
    def test_drops_bulk_trading(self):
        out = _sanitize_deprecated_kwargs({"bulk_trading": False, "keep": 1})
        assert "bulk_trading" not in out
        assert out["keep"] == 1

    def test_drops_bulk_partial_on_return(self):
        out = _sanitize_deprecated_kwargs({"bulk_partial_on_return": True})
        assert out == {}

    def test_drops_market_check_interval(self):
        out = _sanitize_deprecated_kwargs({"market_check_interval": 5})
        assert out == {}

    def test_drops_all_grid_legacy_fields(self):
        legacy = {
            "position_count": 10,
            "position_distance_pct": 2.0,
            "fold_mode": "even",
            "fold_target": 100.0,
            "fold_target_count": 5,
            "profit_fold_pct": 100.0,
            "distribute_target": 100.0,
            "distribute_target_count": 5,
        }
        out = _sanitize_deprecated_kwargs(legacy)
        assert out == {}, f"grid-legacy fields not fully dropped: {out}"

    def test_preserves_current_fields(self):
        cur = {
            "target_balance": 200.0,
            "scrumming_interval_pct": 1.0,
            "stack_mode": True,
            "split_distance": 2.0,
        }
        out = _sanitize_deprecated_kwargs(cur)
        assert out == cur


# ---------------------------------------------------------------------------
# make_bot_config with old bot_state.json shape must succeed
# ---------------------------------------------------------------------------


class TestOlderBotStateCompatibility:
    # Required BotConfig kwargs that every construction must include.
    # Not part of the compatibility surface being tested — just the
    # minimum shape.
    _REQ = {
        "exchange_id": "coinbase",
        "base_currency": "USD",
        "target_asset": "BTC",
        "target_balance": 200.0,
    }

    def test_bulk_trading_in_kwargs_no_typeerror(self):
        """A bot_state.json saved before v3.23.25 will pass
        bulk_trading=False to make_bot_config. Must not TypeError."""
        cfg = make_bot_config(
            BotMode.SCRUMMING,
            **self._REQ,
            bulk_trading=False,  # deprecated kwarg
            bulk_partial_on_return=True,  # deprecated kwarg
        )
        assert cfg.mode == BotMode.SCRUMMING
        assert cfg.stack_mode is False  # default kept

    def test_grid_legacy_kwargs_no_typeerror(self):
        cfg = make_bot_config(
            BotMode.SCRUMMING,
            **self._REQ,
            position_count=10,  # v3.23.3-removed
            position_distance_pct=2.0,  # v3.23.3-removed
            fold_mode="even",  # v3.23.3-removed
        )
        assert cfg.mode == BotMode.SCRUMMING


# ---------------------------------------------------------------------------
# Restore paths in bot_container.py + main_window.py
# ---------------------------------------------------------------------------


class TestRestorePaths:
    def test_bot_container_restore_emits_stack_mode(self):
        src = (REPO / "src" / "trading" / "bot_container.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert (
            '"stack_mode": cfg.get(' in src
        ), "bot_container.py SCRUMMING restore path must emit stack_mode kwarg"
        assert '"split_distance": cfg.get(' in src
        assert '"stack_tranche_count_target": cfg.get(' in src
        assert '"stack_spacing_mode": cfg.get(' in src

    def test_bot_container_restore_no_retired_kwargs(self):
        src = (REPO / "src" / "trading" / "bot_container.py").read_text(
            encoding="utf-8", errors="replace"
        )
        # allow the string inside _DEPRECATED_KWARGS set but reject the
        # restore-kwarg form
        assert '"bulk_trading": cfg.get(' not in src
        assert '"bulk_partial_on_return": cfg.get(' not in src

    def test_main_window_restore_emits_stack_mode(self):
        src = (REPO / "src" / "gui" / "main_window.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert '"stack_mode": config.get(' in src
        assert '"split_distance": config.get(' in src

    def test_main_window_restore_no_retired_kwargs(self):
        src = (REPO / "src" / "gui" / "main_window.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert '"bulk_trading": config.get(' not in src
        assert '"bulk_partial_on_return": config.get(' not in src


# ---------------------------------------------------------------------------
# Settings widget renames + new widgets
# ---------------------------------------------------------------------------


class TestSettingsWidgets:
    def _settings_body(self) -> str:
        src = (REPO / "src" / "gui" / "bot_live_settings.py").read_text(
            encoding="utf-8", errors="replace"
        )
        i = src.find("def _create_settings_tab")
        return src[i : i + 60000]

    def test_stack_mode_checkbox_present(self):
        b = self._settings_body()
        assert "self._stack_mode = QCheckBox" in b
        assert '_mark_changed("stack_mode"' in b

    def test_bulk_trading_widget_removed(self):
        b = self._settings_body()
        assert (
            'QCheckBox("Bulk Trading' not in b
        ), "old Bulk Trading widget still exists in Settings tab"
        assert '_mark_changed("bulk_trading"' not in b

    def test_split_distance_widget_present(self):
        b = self._settings_body()
        assert "self._split_distance = QDoubleSpinBox" in b
        assert '_mark_changed("split_distance"' in b

    def test_tranche_count_widget_present(self):
        b = self._settings_body()
        assert "self._stack_count = QSpinBox" in b
        assert '_mark_changed("stack_tranche_count_target"' in b

    def test_spacing_mode_combobox_present(self):
        b = self._settings_body()
        assert "self._stack_spacing = QComboBox" in b
        assert (
            '_mark_changed(\n                    "stack_spacing_mode"' in b
            or '_mark_changed("stack_spacing_mode"' in b
        )

    def test_aggressive_widget_updated_label(self):
        b = self._settings_body()
        assert "IOC-limit takers" in b, (
            "Aggressive Trading widget label must reference IOC-limit "
            "taker semantic per v3.23.25 operator directive"
        )

    def test_spacing_combobox_uses_quadratic_label(self):
        """v3.23.26 rename: middle spacing option is 'Quadratic', not
        'Logarithmic'. Operator directive 2026-07-25: prefer accurate
        math naming."""
        b = self._settings_body()
        assert "Quadratic" in b, "'Quadratic' label missing from spacing combobox"
        assert '"quadratic"' in b, "'quadratic' data value missing"

    def test_spacing_combobox_no_logarithmic_label(self):
        """Reject regression to the earlier 'Logarithmic' label."""
        b = self._settings_body()
        # Reject the label form only — the code comment/docstring may
        # still mention 'logarithmic' as historical context.
        assert 'addItem("Logarithmic' not in b, (
            "'Logarithmic' label re-appeared in the spacing combobox; "
            "must stay 'Quadratic' per v3.23.26 rename"
        )


# ---------------------------------------------------------------------------
# v3.23.26 — Stack Mode ledger on ScrummingBot
# ---------------------------------------------------------------------------


class TestScrummingBotStackLedger:
    """The Stack Mode ledger must be initialized on every ScrummingBot
    instance. Runtime consumer (SCRUM path branching) lands in 2B-2."""

    def test_stack_tranches_ledger_declared(self):
        src = (REPO / "src" / "trading" / "scrumming_bot.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "self._stack_tranches: list[dict] = []" in src, (
            "ScrummingBot must initialize _stack_tranches: list[dict] "
            "= [] in __init__ so 2B-2 execution can populate it"
        )

    def test_stack_created_counter_declared(self):
        src = (REPO / "src" / "trading" / "scrumming_bot.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "self._stack_created: int = 0" in src


# ---------------------------------------------------------------------------
# v3.23.26 — sanitize helper promotes deprecated "logarithmic" → "quadratic"
# ---------------------------------------------------------------------------


class TestSpacingModeMigration:
    def test_logarithmic_promoted_to_quadratic(self):
        from src.trading.bot_container import _sanitize_deprecated_kwargs

        out = _sanitize_deprecated_kwargs(
            {"stack_spacing_mode": "logarithmic", "keep": 1}
        )
        assert out["stack_spacing_mode"] == "quadratic"
        assert out["keep"] == 1

    def test_quadratic_passes_through_unchanged(self):
        from src.trading.bot_container import _sanitize_deprecated_kwargs

        out = _sanitize_deprecated_kwargs({"stack_spacing_mode": "quadratic"})
        assert out["stack_spacing_mode"] == "quadratic"

    def test_linear_and_exponential_unaffected(self):
        from src.trading.bot_container import _sanitize_deprecated_kwargs

        for v in ("linear", "exponential"):
            out = _sanitize_deprecated_kwargs({"stack_spacing_mode": v})
            assert out["stack_spacing_mode"] == v
