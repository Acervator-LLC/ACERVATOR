"""table_cells_surface.py -- the bot-table priced, Ammo and Target-denom cells.

Describes the three cells the dashboard paints for every bot row. The
Current Position Value cell says what the holdings are worth at the
exchange's own price. The Ammo cell says how far that position sits
from its target and which way the engine will move it. The
Target-denom cell restates the same target in BTC and in ETH and says
how far that pair has drifted from the same asset priced in dollars.

Six things leave this surface. ``price_pool`` finds the shared price
cache. ``fresh_price`` picks the price the cells are drawn from and
says how old it is. ``priced_position`` is the one multiplication both
priced cells read. ``position_value_cell`` composes the Current
Position Value cell on each of its five paths, four of which are
blank. ``ammo_cell`` composes the Ammo cell on each of its three
paths. ``target_denom_cell`` composes one Target-denom cell on each of
its seven paths. Every path returns a text and a colour, and the Ammo
and Position Value paths return a tooltip as well.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``table_cells.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Optional

from .. import design_system as ds
from ...trading.target_bands import (
    MANUAL_FIRE_PCT,
    TERRITORY_AT_TARGET,
    TERRITORY_FOLD,
    TERRITORY_SCRUM,
    manual_fire_dust_band,
    manual_fire_will_noop,
    target_delta,
    target_territory,
)

logger = logging.getLogger("acervator.gui")

METHOD = "table_cells.state"

LOGGER_NAME = "acervator.gui"

STALE_MARKER = "(stale)"

AMMO_SCRUM_COLOR = ds.SUCCESS
AMMO_FOLD_COLOR = ds.ERROR
AMMO_NEUTRAL_COLOR = ds.TEXT_MED

PRICE_STALE_AFTER_S = 20.0
MANUAL_FIRE_DUST_PCT = MANUAL_FIRE_PCT

MAGNITUDE_FORMAT = "${magnitude:,.4f}"
NO_TARGET_TEXT = "---"
PENDING_PRICE_TEXT = "pending…"
STALE_TEXT_FORMAT = "{text} {marker}"

TERRITORIES = (TERRITORY_SCRUM, TERRITORY_FOLD, TERRITORY_AT_TARGET)

SCRUM_TIP = "Scrum territory — sell surplus on bullish"
FOLD_TIP = "Fold territory — buy deficit on bearish"
AT_TARGET_TIP = "Within dust band — no action pending"

TERRITORY_COLORS = {
    TERRITORY_SCRUM: AMMO_SCRUM_COLOR,
    TERRITORY_FOLD: AMMO_FOLD_COLOR,
    TERRITORY_AT_TARGET: AMMO_NEUTRAL_COLOR,
}
TERRITORY_TIPS = {
    TERRITORY_SCRUM: SCRUM_TIP,
    TERRITORY_FOLD: FOLD_TIP,
    TERRITORY_AT_TARGET: AT_TARGET_TIP,
}

EMPTY_POSITION_TIP = (
    "No position — initial entry pending. " "Ammo = full target (bot must buy in)."
)
PENDING_PRICE_TIP_FORMAT = (
    "Holdings present ({holdings:.6f}) but price not "
    "yet fetched. Ammo will update on first tick."
)
MANUAL_FIRE_NOOP_TIP_FORMAT = (
    "{tip}\n\nMANUAL FIRE WILL NOT ACT: |delta| "
    "${magnitude:,.4f} is inside Manual Fire's own dust "
    "band of ${dust_band:,.2f} (1% of target). The autonomous "
    "engine still works this range; the button will no-op."
)
MANUAL_FIRE_NOOP_OLD_PRICE_SUFFIX = (
    " The delta above rests on the old price named here, so the no-op is "
    "likely rather than certain."
)
STALE_TIP_FORMAT = (
    "STALE — price unavailable this tick, so this is the last "
    "known position value (${stats_pv:,.4f}), not a current "
    "one. Do not fire on it."
)
AGED_PRICE_TIP_FORMAT = (
    "PRICE {price_age_s:,.0f}s OLD — this figure is computed "
    "from a price that has not refreshed recently, so the "
    "true delta may differ. Manual Fire will act on the "
    "CURRENT price, not this one."
)

AMMO_FIELDS = (
    "text",
    "color",
    "tip",
    "delta",
    "stale",
    "position_val",
    "manual_fire_noop",
    "price_age_s",
)
AMMO_EARLY_FIELDS = ("text", "color", "delta", "stale", "position_val", "tip")

AMMO_PATH_EMPTY = "empty"
AMMO_PATH_PENDING = "pending"
AMMO_PATH_SIGNAL = "signal"
AMMO_PATHS = (AMMO_PATH_EMPTY, AMMO_PATH_PENDING, AMMO_PATH_SIGNAL)

POSITION_BLANK_TEXT = ""
NO_CELL_COLOR = ""
NO_POSITION_VALUE: Optional[float] = None

NO_HOLDINGS_POSITION_TIP = (
    "No position. This bot holds nothing, so the exchange prices nothing for it."
)
NO_PRICE_POSITION_TIP = (
    "No exchange price for this pair yet. The cell stays blank until one arrives."
)
OFF_EXCHANGE_POSITION_TIP = (
    "No exchange price this tick. Blank rather than the bot's own last "
    "reading, which is not a current value."
)
AGED_POSITION_TIP_FORMAT = (
    "Exchange price is {price_age_s:,.0f}s old, past the {stale_after_s:,.0f}s "
    "limit. Blank rather than a figure priced off it."
)
PRICED_POSITION_TIP_FORMAT = (
    "Current position value from the exchange: {holdings:.6f} units at "
    "${price:,.4f}, priced {price_age_s:,.0f}s ago."
)

POSITION_PATH_PRICED = "priced"
POSITION_PATH_NO_HOLDINGS = "holdings_absent"
POSITION_PATH_NO_PRICE = "price_absent"
POSITION_PATH_OFF_EXCHANGE = "off_exchange"
POSITION_PATH_AGED = "aged"
POSITION_PATHS = (
    POSITION_PATH_PRICED,
    POSITION_PATH_NO_HOLDINGS,
    POSITION_PATH_NO_PRICE,
    POSITION_PATH_OFF_EXCHANGE,
    POSITION_PATH_AGED,
)

POSITION_BLANK_TIPS = {
    POSITION_PATH_NO_HOLDINGS: NO_HOLDINGS_POSITION_TIP,
    POSITION_PATH_NO_PRICE: NO_PRICE_POSITION_TIP,
    POSITION_PATH_OFF_EXCHANGE: OFF_EXCHANGE_POSITION_TIP,
}

AMMO_PATH_FIELDS = {
    AMMO_PATH_EMPTY: AMMO_EARLY_FIELDS,
    AMMO_PATH_PENDING: AMMO_EARLY_FIELDS,
    AMMO_PATH_SIGNAL: AMMO_FIELDS,
}

DENOM_NEUTRAL_COLOR = ds.TEXT_MED
DENOM_UP_COLOR = ds.SUCCESS
DENOM_DOWN_COLOR = ds.ERROR

QUOTE_BTC = "BTC"
QUOTE_ETH = "ETH"
QUOTE_USD = "USD"
QUOTE_USDC = "USDC"
DENOM_QUOTES = (QUOTE_BTC, QUOTE_ETH)

BLANK_CELL_TEXT = ""
PENDING_RATE_TEXT = "pending"
UNLISTED_TEXT = "—"

MISSING_QUOTE_USD = 0.0
MISSING_USD_PCT = 0.0
DIVERGENCE_DUST_PCT = 0.1
UNITS_SIG_FIGURES = 5
UNITS_MIN_DECIMALS = 4
UNITS_MAX_DECIMALS = 12

UNITS_FORMAT = "{units:.{decimals}f}"
UNITS_UNDERFLOW_FORMAT = "<{floor:.{decimals}f}"
DENOM_TEXT_FORMAT = "{units_text} ({sign}{delta:.1f}%)"

SIGN_UP = "+"
SIGN_FLAT = ""
SIGN_DOWN = ""

DENOM_PATH_NO_NAMES = "no_names"
DENOM_PATH_SELF = "self_reference"
DENOM_PATH_NO_TARGET = "no_target"
DENOM_PATH_NO_RATE = "no_rate"
DENOM_PATH_UNLISTED = "unlisted"
DENOM_PATH_PRICED = "priced"
DENOM_PATH_ERRORED = "errored"
DENOM_PATHS = (
    DENOM_PATH_NO_NAMES,
    DENOM_PATH_SELF,
    DENOM_PATH_NO_TARGET,
    DENOM_PATH_NO_RATE,
    DENOM_PATH_UNLISTED,
    DENOM_PATH_PRICED,
    DENOM_PATH_ERRORED,
)

DENOM_PATH_TEXTS = {
    DENOM_PATH_NO_NAMES: BLANK_CELL_TEXT,
    DENOM_PATH_SELF: BLANK_CELL_TEXT,
    DENOM_PATH_NO_TARGET: BLANK_CELL_TEXT,
    DENOM_PATH_NO_RATE: PENDING_RATE_TEXT,
    DENOM_PATH_UNLISTED: UNLISTED_TEXT,
    DENOM_PATH_ERRORED: BLANK_CELL_TEXT,
}

POOL_UNAVAILABLE_LOG = "Ammo: data pool unavailable"
POOL_LOOKUP_FAILED_LOG = "Ammo: pool price lookup failed for %s/%s"

MISSING_PRICE_AGE_S: Optional[float] = None
MISSING_LAST = 0
MISSING_FETCH_TIME = 0
YOUNGEST_AGE_S = 0.0

AMMO_CELL = "ammo"
TARGET_BTC_CELL = "target_btc"
TARGET_ETH_CELL = "target_eth"
CELLS = (TARGET_BTC_CELL, TARGET_ETH_CELL, AMMO_CELL)

CELL_COLUMNS = {TARGET_BTC_CELL: 5, TARGET_ETH_CELL: 6, AMMO_CELL: 7}
CELL_QUOTES = {TARGET_BTC_CELL: QUOTE_BTC, TARGET_ETH_CELL: QUOTE_ETH}
CELL_MASK_KEYS = {
    TARGET_BTC_CELL: "bot_table.target",
    TARGET_ETH_CELL: "bot_table.target",
    AMMO_CELL: "bot_table.ammo",
}
CELL_TOOLTIPS = {TARGET_BTC_CELL: False, TARGET_ETH_CELL: False, AMMO_CELL: True}
CELL_ICONS = {TARGET_BTC_CELL: False, TARGET_ETH_CELL: False, AMMO_CELL: False}

ALIGNMENT = "AlignCenter"
ALIGNMENT_VALUE = 132
COLUMN_COUNT = 10
SORTING_ENABLED = False
SORT_KEYS: dict[str, str] = {}

ACTIONS: dict[str, str] = {}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
SKIN: dict[str, str] = {}
STYLE_SHEET = ""

POOL_IMPORT = "pool.import"
POOL_MISSING = "pool.missing"
POOL_RETURN = "pool.return"
PRICE_LOOKUP = "price.lookup"
PRICE_HIT = "price.hit"
PRICE_MISS = "price.miss"
PRICE_FAILED = "price.failed"
PRICE_RETURN = "price.return"
POSITION_START = "position.start"
POSITION_BLANK = "position.blank"
POSITION_PRICED = "position.priced"
POSITION_RETURN = "position.return"
AMMO_START = "ammo.start"
AMMO_FRESH = "ammo.fresh"
AMMO_CACHED = "ammo.cached"
AMMO_EMPTY = "ammo.empty"
AMMO_PENDING = "ammo.pending"
AMMO_TERRITORY = "ammo.territory"
AMMO_NOOP = "ammo.noop"
AMMO_AGED = "ammo.aged"
AMMO_RETURN = "ammo.return"
DENOM_START = "denom.start"
DENOM_BLANK = "denom.blank"
DENOM_SELF = "denom.self"
DENOM_NO_TARGET = "denom.no_target"
DENOM_RATES = "denom.rates"
DENOM_PENDING = "denom.pending"
DENOM_PAIR = "denom.pair"
DENOM_UNLISTED = "denom.unlisted"
DENOM_USD_PAIR = "denom.usd_pair"
DENOM_DELTA = "denom.delta"
DENOM_ERROR = "denom.error"
DENOM_RETURN = "denom.return"

ModelCall = list[object]


def magnitude(value: float) -> str:
    """One dollar figure without its sign, as both cells write it."""
    return MAGNITUDE_FORMAT.format(magnitude=abs(value))


def priced_position(holdings: float, price: float, quote_rate: float) -> float:
    """The position value at one price: ``holdings`` times ``price`` times
    ``quote_rate``."""
    return holdings * price * quote_rate


def ammo_text(delta: float, target_val: float) -> str:
    """The Ammo figure, or the no-target dashes when there is no target."""
    return magnitude(delta) if target_val > 0 else NO_TARGET_TEXT


def units_text(units: float) -> str:
    """The target restated in the quote asset, at ``UNITS_SIG_FIGURES``.

    A ``units`` above zero never reads as zeros: under ``UNITS_MAX_DECIMALS``
    the cell draws ``UNITS_UNDERFLOW_FORMAT`` instead.
    """
    if units <= 0:
        return UNITS_FORMAT.format(units=units, decimals=UNITS_MIN_DECIMALS)
    decimals = UNITS_SIG_FIGURES - 1 - math.floor(math.log10(units))
    decimals = min(max(decimals, UNITS_MIN_DECIMALS), UNITS_MAX_DECIMALS)
    text = UNITS_FORMAT.format(units=units, decimals=decimals)
    if float(text) > 0:
        return text
    return UNITS_UNDERFLOW_FORMAT.format(
        floor=10.0**-UNITS_MAX_DECIMALS, decimals=UNITS_MAX_DECIMALS
    )


def divergence_colour(delta: float) -> tuple[str, str]:
    """The colour and the sign one 24-hour divergence is drawn with."""
    if abs(delta) < DIVERGENCE_DUST_PCT:
        return DENOM_NEUTRAL_COLOR, SIGN_FLAT
    if delta > 0:
        return DENOM_UP_COLOR, SIGN_UP
    return DENOM_DOWN_COLOR, SIGN_DOWN


class TableCellsModel:
    """The Ammo cell, the Target-denom cell, and the price they read.

    ``price_pool`` finds the shared price cache. ``fresh_price`` picks
    the price the Ammo cell is drawn from. ``ammo_cell`` and
    ``target_denom_cell`` compose one cell each. Every step is appended
    to ``calls`` in the order the shipped code makes it, so a caller can
    replay the same sequence on a table it owns.
    """

    def __init__(self) -> None:
        self.ammo: dict = {}
        self.ammo_path = ""
        self.denom: dict = {}
        self.denom_path = ""
        self.price: Any = MISSING_LAST
        self.price_age_s: Optional[float] = MISSING_PRICE_AGE_S
        self.pool_found = False
        self.calls: list[ModelCall] = []

    def price_pool(self) -> Any:
        """The shared price cache, or None when it is not wired.

        The dashboard must paint in a harness and in paper mode, where
        the cache is never built, so a failed import is swallowed.
        """
        try:
            from ...exchange.data_pool import get_data_pool

            found = get_data_pool()
            self.pool_found = found is not None
            self.calls.append([POOL_IMPORT, self.pool_found])
            self.calls.append([POOL_RETURN, self.pool_found])
            return found
        except Exception:
            logger.debug(POOL_UNAVAILABLE_LOG, exc_info=True)
            self.pool_found = False
            self.calls.append([POOL_MISSING])
            self.calls.append([POOL_RETURN, False])
            return None

    def fresh_price(
        self,
        pool: Any,
        exchange_id: str,
        symbol: str,
        fallback_price: float,
    ) -> tuple:
        """The price the cell is drawn from, and its age in seconds.

        Prefers the shared cache, which is never older than the bot's
        own reading. Falls back to the passed price with no age when the
        cache is absent, unwired or empty.
        """
        self.calls.append([PRICE_LOOKUP, exchange_id, symbol])
        try:
            entry = pool.get_ticker(exchange_id, symbol) if pool else None
            if entry is not None:
                last = float(getattr(entry, "last", MISSING_LAST) or MISSING_LAST)
                fetched = float(
                    getattr(entry, "fetch_time", MISSING_FETCH_TIME)
                    or MISSING_FETCH_TIME
                )
                if last > 0 and fetched > 0:
                    age = max(YOUNGEST_AGE_S, time.time() - fetched)
                    self.calls.append([PRICE_HIT, last])
                    return self._priced(last, age)
            self.calls.append([PRICE_MISS])
        except Exception:
            logger.debug(
                POOL_LOOKUP_FAILED_LOG,
                exchange_id,
                symbol,
                exc_info=True,
            )
            self.calls.append([PRICE_FAILED])
        return self._priced(fallback_price, MISSING_PRICE_AGE_S)

    def _priced(self, price: Any, age: Optional[float]) -> tuple:
        """Keep one price reading and record what it returned."""
        self.price = price
        self.price_age_s = age
        self.calls.append([PRICE_RETURN, price, age is not None])
        return price, age

    def position_value_cell(
        self,
        holdings: float,
        cur_price: float,
        qrate: float,
        price_age_s: Optional[float] = MISSING_PRICE_AGE_S,
    ) -> dict:
        """The Current Position Value cell, filled only from a fresh exchange price.

        ``price_age_s`` is None whenever ``fresh_price`` fell back to the
        bot's own reading, and every path but ``POSITION_PATH_PRICED``
        returns ``POSITION_BLANK_TEXT`` with the reason in its tooltip.
        """
        self.calls.append([POSITION_START, holdings, cur_price, qrate, price_age_s])
        if holdings <= 0:
            return self._blank_position(POSITION_PATH_NO_HOLDINGS)
        if cur_price <= 0:
            return self._blank_position(POSITION_PATH_NO_PRICE)
        if price_age_s is None:
            return self._blank_position(POSITION_PATH_OFF_EXCHANGE)
        if price_age_s > PRICE_STALE_AFTER_S:
            return self._finish_position(
                POSITION_PATH_AGED,
                {
                    "text": POSITION_BLANK_TEXT,
                    "color": NO_CELL_COLOR,
                    "tip": AGED_POSITION_TIP_FORMAT.format(
                        price_age_s=price_age_s, stale_after_s=PRICE_STALE_AFTER_S
                    ),
                    "position_val": NO_POSITION_VALUE,
                    "priced": False,
                },
            )
        position_val = priced_position(holdings, cur_price, qrate)
        self.calls.append([POSITION_PRICED, position_val, price_age_s])
        return self._finish_position(
            POSITION_PATH_PRICED,
            {
                "text": magnitude(position_val),
                "color": NO_CELL_COLOR,
                "tip": PRICED_POSITION_TIP_FORMAT.format(
                    holdings=holdings, price=cur_price, price_age_s=price_age_s
                ),
                "position_val": position_val,
                "priced": True,
            },
        )

    def _blank_position(self, path: str) -> dict:
        """One unpriced Position Value cell, its tooltip naming what is absent."""
        self.calls.append([POSITION_BLANK, path])
        return self._finish_position(
            path,
            {
                "text": POSITION_BLANK_TEXT,
                "color": NO_CELL_COLOR,
                "tip": POSITION_BLANK_TIPS[path],
                "position_val": NO_POSITION_VALUE,
                "priced": False,
            },
        )

    def _finish_position(self, path: str, cell: dict) -> dict:
        """Stamp ``path`` onto one Position Value cell and record it."""
        cell["path"] = path
        self.calls.append([POSITION_RETURN, path, cell["text"], cell["priced"]])
        return cell

    def ammo_cell(
        self,
        stats_pv: float,
        holdings: float,
        cur_price: float,
        qrate: float,
        target_val: float,
        price_age_s: Optional[float] = MISSING_PRICE_AGE_S,
    ) -> dict:
        """The Ammo cell: distance from target, and the signal it carries.

        Recomputes the position from holdings and price whenever both
        are present. Falls back to the last known value and marks it
        stale when they are not.
        """
        self.calls.append([AMMO_START, stats_pv, holdings, cur_price, qrate])
        fresh_ok = holdings > 0 and cur_price > 0
        fresh_pv = priced_position(holdings, cur_price, qrate) if fresh_ok else 0.0
        if fresh_ok:
            position_val, stale = fresh_pv, False
            self.calls.append([AMMO_FRESH, position_val])
        else:
            position_val, stale = stats_pv, stats_pv > 0
            self.calls.append([AMMO_CACHED, position_val, stale])
        if position_val <= 0 and holdings <= 0:
            return self._empty_cell(position_val, target_val)
        if position_val <= 0 and holdings > 0:
            return self._pending_cell(position_val, holdings)
        return self._signal_cell(stats_pv, position_val, target_val, stale, price_age_s)

    def _empty_cell(self, position_val: float, target_val: float) -> dict:
        """Never held and never traded. Ammo is the whole target, to buy."""
        delta = target_delta(0.0, target_val)
        self.calls.append([AMMO_EMPTY, delta])
        return self._finish(
            AMMO_PATH_EMPTY,
            {
                "text": ammo_text(delta, target_val),
                "color": AMMO_FOLD_COLOR,
                "delta": delta,
                "stale": False,
                "position_val": position_val,
                "tip": EMPTY_POSITION_TIP,
            },
        )

    def _pending_cell(self, position_val: float, holdings: float) -> dict:
        """Holdings exist and no price has arrived. Say so, never zero."""
        self.calls.append([AMMO_PENDING, holdings])
        return self._finish(
            AMMO_PATH_PENDING,
            {
                "text": PENDING_PRICE_TEXT,
                "color": AMMO_NEUTRAL_COLOR,
                "delta": 0.0,
                "stale": False,
                "position_val": position_val,
                "tip": PENDING_PRICE_TIP_FORMAT.format(holdings=holdings),
            },
        )

    def _signal_cell(
        self,
        stats_pv: float,
        position_val: float,
        target_val: float,
        stale: bool,
        price_age_s: Optional[float],
    ) -> dict:
        """A live position: its distance from target and the engine's band."""
        delta = target_delta(position_val, target_val)
        territory = target_territory(position_val, target_val)
        color = TERRITORY_COLORS[territory]
        tip = TERRITORY_TIPS[territory]
        self.calls.append([AMMO_TERRITORY, territory, delta])
        dust_band = manual_fire_dust_band(target_val)
        manual_fire_noop = 0 < abs(delta) and manual_fire_will_noop(
            position_val, target_val
        )
        text = ammo_text(delta, target_val)
        old_price = False
        if stale:
            color = AMMO_NEUTRAL_COLOR
            text = STALE_TEXT_FORMAT.format(text=text, marker=STALE_MARKER)
            tip = STALE_TIP_FORMAT.format(stats_pv=stats_pv)
            old_price = True
        elif price_age_s is not None and price_age_s > PRICE_STALE_AFTER_S:
            color = AMMO_NEUTRAL_COLOR
            text = STALE_TEXT_FORMAT.format(text=text, marker=STALE_MARKER)
            tip = AGED_PRICE_TIP_FORMAT.format(price_age_s=price_age_s)
            old_price = True
            self.calls.append([AMMO_AGED, price_age_s])
        if manual_fire_noop:
            tip = MANUAL_FIRE_NOOP_TIP_FORMAT.format(
                tip=tip, magnitude=abs(delta), dust_band=dust_band
            )
            if old_price:
                tip = f"{tip}{MANUAL_FIRE_NOOP_OLD_PRICE_SUFFIX}"
            self.calls.append([AMMO_NOOP, dust_band])
        return self._finish(
            AMMO_PATH_SIGNAL,
            {
                "text": text,
                "color": color,
                "tip": tip,
                "delta": delta,
                "stale": stale,
                "position_val": position_val,
                "manual_fire_noop": manual_fire_noop,
                "price_age_s": price_age_s,
            },
        )

    def _finish(self, path: str, cell: dict) -> dict:
        """Keep one finished Ammo cell and record what it returned."""
        self.ammo = cell
        self.ammo_path = path
        self.calls.append([AMMO_RETURN, path, cell["text"], cell["color"]])
        return cell

    def target_denom_cell(
        self,
        quote_currency: str,
        base_asset: str,
        exchange_id: str,
        target_usd: float,
    ) -> tuple:
        """One Target-denom cell: the target in BTC or ETH, and its drift.

        Blank when either name is missing, when the target asset is the
        quote itself, when there is no target, and on any failure. The
        cell is best effort, so a broken lookup paints nothing rather
        than raising into the table paint.
        """
        quote = (quote_currency or "").upper()
        base = (base_asset or "").upper()
        self.calls.append([DENOM_START, quote, base, exchange_id])
        if not quote or not base:
            self.calls.append([DENOM_BLANK])
            return self._denom_finish(DENOM_PATH_NO_NAMES, DENOM_NEUTRAL_COLOR)
        if base == quote:
            self.calls.append([DENOM_SELF, base])
            return self._denom_finish(DENOM_PATH_SELF, DENOM_NEUTRAL_COLOR)
        if target_usd <= 0:
            self.calls.append([DENOM_NO_TARGET, target_usd])
            return self._denom_finish(DENOM_PATH_NO_TARGET, DENOM_NEUTRAL_COLOR)
        try:
            return self._priced_denom(quote, base, exchange_id, target_usd)
        except Exception as exc:
            self.calls.append([DENOM_ERROR, type(exc).__name__])
            return self._denom_finish(DENOM_PATH_ERRORED, DENOM_NEUTRAL_COLOR)

    def _priced_denom(
        self, quote: str, base: str, exchange_id: str, target_usd: float
    ) -> tuple:
        """The three paths that need the rate monitor and the pair scout."""
        from src.exchange.currency_rate_monitor import get_currency_monitor
        from src.exchange.market_pairs_scout import get_scout

        rates = get_currency_monitor().snapshot()
        scout = get_scout()
        if quote == QUOTE_BTC:
            quote_usd = float(rates.btc_usd or MISSING_QUOTE_USD)
        elif quote == QUOTE_ETH:
            quote_usd = float(rates.eth_usd or MISSING_QUOTE_USD)
        else:
            quote_usd = MISSING_QUOTE_USD
        self.calls.append([DENOM_RATES, quote, quote_usd])
        if quote_usd <= 0:
            self.calls.append([DENOM_PENDING, quote])
            return self._denom_finish(DENOM_PATH_NO_RATE, DENOM_NEUTRAL_COLOR)
        venue = exchange_id or None
        pair = scout.get_pair(base, quote, exchange_id=venue)
        self.calls.append([DENOM_PAIR, base, quote, pair is not None])
        if pair is None:
            self.calls.append([DENOM_UNLISTED, base, quote])
            return self._denom_finish(DENOM_PATH_UNLISTED, DENOM_NEUTRAL_COLOR)
        usd_pair = scout.get_pair(base, QUOTE_USD, exchange_id=venue)
        if usd_pair is None:
            usd_pair = scout.get_pair(base, QUOTE_USDC, exchange_id=venue)
        usd_pct = float(usd_pair.pct_24h) if usd_pair else MISSING_USD_PCT
        self.calls.append([DENOM_USD_PAIR, usd_pair is not None, usd_pct])
        units = target_usd / quote_usd
        delta = float(pair.pct_24h) - usd_pct
        color, sign = divergence_colour(delta)
        self.calls.append([DENOM_DELTA, delta, sign])
        return self._denom_finish(
            DENOM_PATH_PRICED,
            color,
            DENOM_TEXT_FORMAT.format(
                units_text=units_text(units), sign=sign, delta=delta
            ),
            units,
            delta,
        )

    def _denom_finish(
        self,
        path: str,
        color: str,
        text: Optional[str] = None,
        units: float = 0.0,
        delta: float = 0.0,
    ) -> tuple:
        """Keep one finished Target-denom cell and record its two values."""
        found = DENOM_PATH_TEXTS[path] if text is None else text
        self.denom = {
            "text": found,
            "color": color,
            "units": units,
            "delta": delta,
        }
        self.denom_path = path
        self.calls.append([DENOM_RETURN, path, found, color])
        return found, color


PANE_MODEL = TableCellsModel()


def build_view_model(
    model: TableCellsModel,
    ammo: Optional[dict] = None,
    denom: Optional[dict] = None,
    price: Optional[dict] = None,
) -> dict:
    """Return the whole surface state as one serialisable dict."""
    if price is not None:
        model.fresh_price(
            model.price_pool(),
            str(price.get("exchange_id", "")),
            str(price.get("symbol", "")),
            price.get("fallback_price", MISSING_LAST),
        )
    if ammo is not None:
        model.ammo_cell(
            ammo.get("stats_pv", 0.0),
            ammo.get("holdings", 0.0),
            ammo.get("cur_price", 0.0),
            ammo.get("qrate", 1.0),
            ammo.get("target_val", 0.0),
            ammo.get("price_age_s", MISSING_PRICE_AGE_S),
        )
    if denom is not None:
        model.target_denom_cell(
            denom.get("quote_currency", ""),
            denom.get("base_asset", ""),
            denom.get("exchange_id", ""),
            denom.get("target_usd", 0.0),
        )
    return {
        "cells": list(CELLS),
        "cell_columns": dict(CELL_COLUMNS),
        "cell_quotes": dict(CELL_QUOTES),
        "cell_mask_keys": dict(CELL_MASK_KEYS),
        "cell_tooltips": dict(CELL_TOOLTIPS),
        "cell_icons": dict(CELL_ICONS),
        "alignment": ALIGNMENT,
        "alignment_value": ALIGNMENT_VALUE,
        "column_count": COLUMN_COUNT,
        "sorting_enabled": SORTING_ENABLED,
        "sort_keys": dict(SORT_KEYS),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "skin": dict(SKIN),
        "style_sheet": STYLE_SHEET,
        "ammo": dict(model.ammo),
        "ammo_path": model.ammo_path,
        "ammo_paths": list(AMMO_PATHS),
        "ammo_fields": list(AMMO_FIELDS),
        "ammo_early_fields": list(AMMO_EARLY_FIELDS),
        "denom": dict(model.denom),
        "denom_path": model.denom_path,
        "denom_paths": list(DENOM_PATHS),
        "denom_path_texts": dict(DENOM_PATH_TEXTS),
        "territories": list(TERRITORIES),
        "territory_colors": dict(TERRITORY_COLORS),
        "territory_tips": dict(TERRITORY_TIPS),
        "price": model.price,
        "price_age_s": model.price_age_s,
        "price_stale_after_s": PRICE_STALE_AFTER_S,
        "manual_fire_dust_pct": MANUAL_FIRE_DUST_PCT,
        "stale_marker": STALE_MARKER,
        "pool_found": model.pool_found,
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``table_cells.state``.

    Reads ``reset``, and the ``price``, ``ammo`` and ``denom`` argument
    sets from the request parameters. The last composed cell persists
    between calls because the table's own row does; ``reset`` is what a
    fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = TableCellsModel()
    return build_view_model(
        PANE_MODEL,
        params.get("ammo"),
        params.get("denom"),
        params.get("price"),
    )
