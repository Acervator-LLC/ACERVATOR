"""The Paper Trader's Scrumming-bot table model, forked from
``bot_status_table_surface``.

``PaperBotStatusTableModel`` is Live's ``BotStatusTableModel`` under ``METHOD``
with the row's own feeds: a row is priced from its own ``stats.current_price``
at ``PAPER_PRICE_AGE_S``, and the Target BTC and Target ETH cells denominate
through ``usd_rates``, the BTC and ETH rows of the same list. Neither reads
the live data pool, the currency rate monitor or the market pairs scout.
``paper_target_denom_cell`` is the one definition of those two cells, read by
this model and by the Qt fork.
"""

from __future__ import annotations

from typing import Any, Optional

from ..main_tabs import bot_status_table_surface as live
from ..main_tabs import table_cells_surface as cells

METHOD = "paper_bot_status_table.state"

#: The Paper Trader's price is its own reading for this tick; it is never older
#: than the tick, so the Position Value cell and the Ammo cell both price
#: from it as the manual requires.
PAPER_PRICE_AGE_S = 0.0

#: The quote assets whose rows give the fleet its rates.
RATE_QUOTES = cells.DENOM_QUOTES


def base_of(symbol: Any) -> str:
    """The base asset of ``symbol``, upper-cased; empty without a slash."""
    text = str(symbol or "")
    return text.split("/")[0].upper() if "/" in text else ""


def usd_rates(statuses: list) -> dict:
    """The USD price of each ``RATE_QUOTES`` asset ``statuses`` holds a row for:
    ``stats.current_price`` times ``quote_to_usd`` for that base."""
    found: dict = {}
    for status in statuses:
        base = base_of(status.get("symbol", live.EMPTY_TEXT))
        if base not in RATE_QUOTES:
            continue
        stats = status.get("stats", {}) or {}
        price = float(
            stats.get("current_price", cells.MISSING_LAST) or cells.MISSING_LAST
        )
        quote_rate = float(
            status.get("quote_to_usd", live.DEFAULT_QUOTE_TO_USD)
            or live.DEFAULT_QUOTE_TO_USD
        )
        if price > 0:
            found[base] = cells.priced_position(1.0, price, quote_rate)
    return found


def paper_target_denom_cell(
    quote_currency: str, base_asset: str, target_usd: float, rates: dict
) -> tuple:
    """``(text, colour)`` for a Target-BTC or Target-ETH cell: ``target_usd``
    in ``quote_currency`` at ``rates``, with ``DENOM_PATH_TEXTS`` for a missing
    name, a self-reference, no target or no rate. No drift suffix, ``DENOM_NEUTRAL_COLOR``.
    """
    quote = (quote_currency or "").upper()
    base = (base_asset or "").upper()
    if not quote or not base:
        return (
            cells.DENOM_PATH_TEXTS[cells.DENOM_PATH_NO_NAMES],
            cells.DENOM_NEUTRAL_COLOR,
        )
    if base == quote:
        return cells.DENOM_PATH_TEXTS[cells.DENOM_PATH_SELF], cells.DENOM_NEUTRAL_COLOR
    if target_usd <= 0:
        return (
            cells.DENOM_PATH_TEXTS[cells.DENOM_PATH_NO_TARGET],
            cells.DENOM_NEUTRAL_COLOR,
        )
    rate = float(rates.get(quote, cells.MISSING_QUOTE_USD) or cells.MISSING_QUOTE_USD)
    if rate <= 0:
        return (
            cells.DENOM_PATH_TEXTS[cells.DENOM_PATH_NO_RATE],
            cells.DENOM_NEUTRAL_COLOR,
        )
    return cells.units_text(target_usd / rate), cells.DENOM_NEUTRAL_COLOR


class PaperTableCellsModel(cells.TableCellsModel):
    """Live's cell model with the Target-denom cell read from ``rates``."""

    def __init__(self) -> None:
        super().__init__()
        self.rates: dict = {}

    def target_denom_cell(
        self,
        quote_currency: str,
        base_asset: str,
        exchange_id: str,
        target_usd: float,
    ) -> tuple:
        """One Target-denom cell from ``rates`` through ``paper_target_denom_cell``."""
        del exchange_id
        text, color = paper_target_denom_cell(
            quote_currency, base_asset, target_usd, self.rates
        )
        self.denom = {"text": text, "color": color, "units": 0.0, "delta": 0.0}
        return text, color


class PaperBotStatusTableModel(live.BotStatusTableModel):
    """Live's table model over the row's own price and the fleet's own rates."""

    def __init__(self, on_bot_clicked=None, on_fire_clicked=None) -> None:
        super().__init__(on_bot_clicked=on_bot_clicked, on_fire_clicked=on_fire_clicked)
        self.cells = PaperTableCellsModel()

    def update_bots(self, bot_statuses: list) -> None:
        """Rewrite every row, ``usd_rates`` read off ``bot_statuses`` first."""
        self.cells.rates = usd_rates(list(bot_statuses))
        super().update_bots(bot_statuses)

    def _price_reading(self, status, stats) -> tuple:
        """The row's own ``current_price`` at ``PAPER_PRICE_AGE_S``, and its ``quote_to_usd``."""
        price = float(stats.get("current_price", live.NO_PRICE))
        quote_rate = float(
            status.get("quote_to_usd", live.DEFAULT_QUOTE_TO_USD)
            or live.DEFAULT_QUOTE_TO_USD
        )
        return price, PAPER_PRICE_AGE_S, quote_rate


def build_view_model(model: live.BotStatusTableModel) -> dict:
    """Live's ``build_view_model`` under ``METHOD``."""
    payload = dict(live.build_view_model(model))
    payload["method"] = METHOD
    return payload


def drive(model: live.BotStatusTableModel, params: dict) -> dict:
    """Apply one request to ``model``, reading each ``*_PARAM`` field Live
    reads, and answer ``build_view_model``."""
    statuses = params.get(live.STATUSES_PARAM)
    if statuses is not None:
        model.update_bots(statuses)
    if params.get(live.HEADER_CLICK_PARAM) is not None:
        model.on_header_clicked(params[live.HEADER_CLICK_PARAM])
    if params.get(live.CELL_CLICK_PARAM) is not None:
        row, column = params[live.CELL_CLICK_PARAM]
        model.on_cell_clicked(row, column)
    if params.get(live.FIRE_PARAM) is not None:
        model.on_fire(params[live.FIRE_PARAM])
    if params.get(live.DETAIL_PARAM) is not None:
        model.on_detail(params[live.DETAIL_PARAM])
    return build_view_model(model)


def venue_of(params: Optional[dict]) -> str:
    """The exchange ``params`` names under ``EXCHANGE_ID_PARAM``, or empty."""
    if not isinstance(params, dict):
        return live.EMPTY_TEXT
    return str(params.get(live.EXCHANGE_ID_PARAM, live.EMPTY_TEXT) or live.EMPTY_TEXT)
