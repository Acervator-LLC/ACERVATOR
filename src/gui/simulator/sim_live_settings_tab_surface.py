"""The Simulator's Settings tab model, forked from ``live_settings_tab_surface``.

``SimLiveSettingsTabModel`` is Live's model with ``refresh_denom_rows`` reading
``denom_rates``, the fleet's own BTC and ETH rows, through
``sim_target_denom_cell``, and ``build`` writing ``BUDGET_UNREADABLE_TEXT``
into ``budget_row`` while ``cycle_growth_cap_usd`` is None.
``build_view_model`` is Live's builder under ``METHOD``.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import live_settings_tab_surface as live
from .sim_bot_status_table_surface import sim_target_denom_cell

METHOD = "sim_live_settings_tab.state"

BUDGET_UNREADABLE_TEXT = "— (unreadable)"
BUDGET_TEXT_FORMAT = "{budget} — consumed ${consumed:,.4f}"


class SimLiveSettingsTabModel(live.LiveSettingsTabModel):
    """Live's Settings tab model over ``denom_rates``."""

    def __init__(
        self,
        bot: Any = None,
        rates: Any = None,
        timeframes: Any = None,
    ) -> None:
        super().__init__(bot, timeframes=timeframes)
        self.denom_rates = dict(rates or {})

    def build(self) -> None:
        """Live's build, then ``budget_row`` without a cap figure."""
        super().build()
        if getattr(self.bot, live.BUDGET_ATTRIBUTE, None) is None:
            consumed = float(getattr(self.bot, live.CONSUMED_ATTRIBUTE, 0.0) or 0.0)
            self.budget_row = [
                BUDGET_TEXT_FORMAT.format(
                    budget=BUDGET_UNREADABLE_TEXT, consumed=consumed
                )
            ]

    def refresh_denom_rows(self) -> None:
        """The two cross-pair rows from ``denom_rates``; never raises."""
        self.calls.append([live.DENOM_START])
        try:
            if not self.denom_rows:
                self.calls.append([live.DENOM_NO_LABELS])
                return
            if self.bot is None:
                self.calls.append([live.DENOM_NO_BOT])
                return
            config = self._config()
            if config is None:
                self.calls.append([live.DENOM_NO_CONFIG])
                return
            asset = str(getattr(config, live.TARGET_ASSET_FIELD, "") or "").upper()
            target_usd = float(getattr(config, live.TARGET_BALANCE_FIELD, 0.0) or 0.0)
            for quote in (live.DENOM_BTC, live.DENOM_ETH):
                if asset == quote:
                    self.denom_visible[quote] = False
                    self.calls.append([live.DENOM_HIDDEN, quote])
                    continue
                self.denom_visible[quote] = True
                text, color = sim_target_denom_cell(
                    quote, asset, target_usd, self.denom_rates
                )
                self.denom_rows[quote] = [text, color]
                self.calls.append([live.DENOM_ROW_CALL, quote, text])
        except Exception as exc:  # noqa: BLE001 - refresh best-effort
            self.calls.append([live.DENOM_FAILED, type(exc).__name__])


def build_view_model(model: live.LiveSettingsTabModel, build_now: bool = False) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model, build_now=build_now))
    payload["method"] = METHOD
    return payload
