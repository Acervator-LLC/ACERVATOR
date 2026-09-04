"""Regression pin — 2026-07-25 operator-reported bug:

    Bot creation REJECTED — mode-shape violation:
    BotConfig.__init__() got an unexpected keyword argument 'position_count'

Root cause: bot_wizard.TradingParamsPage had an orphaned grid branch in
get_config() that produced `position_count` and `position_distance_pct`
fields. BotMode.GRID was excised in v3.20.4; BotConfig no longer has
those fields; the wizard's dead branch still emitted them, and
BotConfig(**kwargs) raised TypeError.

Fix landed v3.23.21:
  - src/gui/bot_wizard.py:521 → self._is_grid = False (was True)
  - src/gui/bot_wizard.py:1632-1641 → grid branch deleted; only
    Scrumming block remains after the Extractor early-return

These pins catch any reintroduction of grid-shape fields into the
wizard config or the BotConfig dataclass.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WIZARD = REPO / "src" / "gui" / "bot_wizard.py"


# BotConfig dataclass surface pin


class TestBotConfigSurface:
    def test_bot_config_has_no_position_count(self):
        """BotConfig must NOT accept position_count as a kwarg.
        If some future refactor adds it back, either fix downstream
        consumers or update this pin."""
        from src.trading.bot_container import BotConfig
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(BotConfig)}
        assert "position_count" not in field_names, (
            "BotConfig has re-acquired position_count field; either "
            "wizard needs to re-emit it or this pin needs updating"
        )
        assert "position_distance_pct" not in field_names

    def test_bot_config_construct_with_position_count_raises(self):
        """Direct sanity check: passing position_count still raises
        TypeError, matching the operator's original error message."""
        from src.trading.bot_container import BotConfig

        with pytest.raises(TypeError, match="position_count"):
            BotConfig(
                exchange_id="coinbase",
                base_currency="USDC",
                target_asset="BTC",
                position_count=10,  # the offending kwarg
            )

    def test_make_bot_config_silently_drops_position_count(self):
        """v3.23.25 update: make_bot_config now sanitizes deprecated
        kwargs (including position_count) via _sanitize_deprecated_kwargs
        so older bot_state.json files load cleanly. The factory no
        longer raises on position_count; the underlying BotConfig still
        doesn't have the field.

        Historical behavior (pre-v3.23.25): make_bot_config raised
        TypeError because position_count reached BotConfig.__init__.
        This test was rewritten to lock the new behavior in place."""
        from src.trading.bot_container import make_bot_config, BotMode

        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="coinbase",
            base_currency="USDC",
            target_asset="BTC",
            position_count=10,  # deprecated — should be silently dropped
        )
        # Sanitize dropped it; construction succeeded.
        assert cfg.mode == BotMode.SCRUMMING
        # Field must NOT re-appear on the resulting BotConfig.
        assert not hasattr(cfg, "position_count")


# Bot wizard source pin — the fix must stay in place


class TestBotWizardSourcePins:
    @pytest.fixture(scope="class")
    def wizard_source(self) -> str:
        return WIZARD.read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def wizard_tree(self, wizard_source) -> ast.Module:
        return ast.parse(wizard_source)

    def test_wizard_parses(self, wizard_tree):
        """Bot wizard must be syntactically valid — the fix landed
        via mixed Edit + inline Python rewrite, so this catches any
        indentation drift or leftover brace."""
        assert wizard_tree is not None

    def test_no_position_count_kwarg_in_cfg_update(self, wizard_source):
        """The wizard must NEVER emit position_count as a config key.
        Match the specific pattern from the deleted grid branch."""
        # We tolerate: comments mentioning position_count, and
        # `defaults.get("default_position_count", ...)` (a defaults
        # dict key, not a BotConfig kwarg).
        # We reject: `"position_count": self._positions.value()` shape
        assert (
            '"position_count":' not in wizard_source
            or '"default_position_count"' in wizard_source
        ), (
            'wizard emits raw "position_count" key — grid branch may '
            "have been reintroduced. Grep bot_wizard.py for the "
            "exact pattern."
        )

    def test_no_position_distance_pct_kwarg(self, wizard_source):
        """Same rule for position_distance_pct."""
        assert '"position_distance_pct":' not in wizard_source

    def test_is_grid_default_is_false(self, wizard_source):
        """TradingParamsPage.__init__ must not default self._is_grid=True.
        This was the belt-and-brace fix that prevents the grid branch
        from being reached even if some future codepath forgot to call
        set_mode()."""
        # Look inside the TradingParamsPage class for the init default
        assert "self._is_grid = True" not in wizard_source, (
            "self._is_grid defaults to True somewhere — the belt-and-"
            "brace v3.23.21 fix has been reverted"
        )

    def test_no_orphan_if_self_is_grid_config_branch(self, wizard_source):
        """The dead grid branch in get_config() must stay deleted."""
        # If someone re-adds `if self._is_grid:` immediately followed
        # by `cfg.update({` — that's the exact pattern we removed.
        import re

        m = re.search(
            r"if\s+self\._is_grid\s*:\s*\n\s*cfg\.update\(",
            wizard_source,
        )
        assert m is None, (
            "the grid cfg.update branch in TradingParamsPage.get_config "
            "has returned — that branch is the source of the "
            "position_count TypeError"
        )


class TestMainWindowScrummingKwargsPin:
    """v3.23.21 → 3.23.22 second-source pin. main_window.py's SCRUMMING
    branch of _mode_kwargs also emitted position_count / position_distance_pct
    at the direct BotConfig factory call. That path was the actual runtime
    trigger for the 17:45:21 error notification. Both must stay excised."""

    @pytest.fixture(scope="class")
    def main_window_source(self) -> str:
        return (REPO / "src" / "gui" / "main_window.py").read_text(
            encoding="utf-8",
            errors="replace",
        )

    def test_scrumming_mode_kwargs_no_position_count(self, main_window_source):
        """The SCRUMMING _mode_kwargs block must not include position_count."""
        import re

        # Isolate the SCRUMMING branch
        block = re.search(
            r"if _mode == BotMode\.SCRUMMING:\s*\n\s*_mode_kwargs = \{(.*?)\}\s*\n\s*else",
            main_window_source,
            re.DOTALL,
        )
        assert block, "SCRUMMING _mode_kwargs block not found in main_window.py"
        body = block.group(1)
        assert '"position_count"' not in body, (
            'main_window.py SCRUMMING _mode_kwargs re-emits "position_count" '
            "— the v3.23.22 fix has been reverted. This is the branch that "
            "reaches make_bot_config() directly and fires the "
            "BotConfig.__init__() got an unexpected keyword argument "
            '"position_count" runtime error.'
        )

    def test_scrumming_mode_kwargs_no_position_distance_pct(self, main_window_source):
        import re

        block = re.search(
            r"if _mode == BotMode\.SCRUMMING:\s*\n\s*_mode_kwargs = \{(.*?)\}\s*\n\s*else",
            main_window_source,
            re.DOTALL,
        )
        assert block
        assert '"position_distance_pct"' not in block.group(1)
