"""Pure text-and-colour formatters for the bot-table Current Position Value,
Ammo and Target-denom cells.

No Qt: the caller applies the returned hex with ``QColor``. Module scope
so the bot tables and their pin tests read one definition.
"""

from __future__ import annotations

import logging
import time

from . import design_system as ds

# One definition of the texts the Electron table also draws.
from .main_tabs.table_cells_surface import (
    AGED_PRICE_TIP_FORMAT,
    MANUAL_FIRE_NOOP_OLD_PRICE_SUFFIX,
    MANUAL_FIRE_NOOP_TIP_FORMAT,
    STALE_TIP_FORMAT,
    units_text,
)

# The Ammo cell reads the engine's thresholds rather than restating them.
from ..trading.target_bands import (
    MANUAL_FIRE_PCT,
    manual_fire_dust_band,
    manual_fire_will_noop,
    target_territory,
)

logger = logging.getLogger("acervator.gui")

# Appended to any dashboard figure that could not be recomputed this tick.
_STALE_MARKER = "(stale)"

_AMMO_SCRUM = ds.SUCCESS
_AMMO_FOLD = ds.ERROR
_AMMO_NEUTRAL = ds.TEXT_MED

# The age past which a displayed price is called old; the refresher rewarms every 5s.
_PRICE_STALE_AFTER_S = 20.0

# Manual Fire's no-op band is ten times the dashboard's actionable band.
_MANUAL_FIRE_DUST_PCT = MANUAL_FIRE_PCT


def _ammo_price_pool():
    """The shared MarketDataPool, or None if it is not available.

    Import is deferred and failure is swallowed so the dashboard still
    renders in harnesses and paper mode where the pool never gets wired.
    Returning None simply falls the caller back to the stats field.
    """
    try:
        from ..exchange.data_pool import get_data_pool

        return get_data_pool()
    except Exception:
        logger.debug("Ammo: data pool unavailable", exc_info=True)
        return None


def _fresh_display_price(pool, exchange_id: str, symbol: str, fallback_price: float):
    """Best available price for DISPLAY, plus its age in seconds.

    Prefers the ``pool`` entry over ``fallback_price``: a bot writes
    ``stats.current_price`` FROM a pool fetch, so the pool entry is never the
    older of the two. Returns ``(price, age_seconds_or_None)``, falling back
    to ``fallback_price`` when the pool is unavailable or holds no entry.
    """
    try:
        entry = pool.get_ticker(exchange_id, symbol) if pool else None
        if entry is not None:
            last = float(getattr(entry, "last", 0) or 0)
            fetched = float(getattr(entry, "fetch_time", 0) or 0)
            if last > 0 and fetched > 0:
                return last, max(0.0, time.time() - fetched)
    except Exception:
        logger.debug(
            "Ammo: pool price lookup failed for %s/%s",
            exchange_id,
            symbol,
            exc_info=True,
        )
    return fallback_price, None


def _priced_position(holdings: float, price: float, quote_rate: float) -> float:
    """The position value at one price: ``holdings`` times ``price`` times
    ``quote_rate``."""
    return holdings * price * quote_rate


def _compose_position_value_cell(
    holdings: float,
    cur_price: float,
    qrate: float,
    price_age_s: float | None = None,
) -> dict:
    """Compute the Current Position Value cell from an exchange price only.

    ``price_age_s`` is None whenever ``_fresh_display_price`` fell back to
    the bot's own reading, and every path but ``priced`` returns an empty
    text with the reason in ``tip``. Qt-free: returns
    ``{text, color, tip, position_val, priced, path}``.
    """
    if holdings <= 0:
        return {
            "text": "",
            "color": "",
            "tip": (
                "No position. This bot holds nothing, so the exchange "
                "prices nothing for it."
            ),
            "position_val": None,
            "priced": False,
            "path": "holdings_absent",
        }
    if cur_price <= 0:
        return {
            "text": "",
            "color": "",
            "tip": (
                "No exchange price for this pair yet. The cell stays blank "
                "until one arrives."
            ),
            "position_val": None,
            "priced": False,
            "path": "price_absent",
        }
    if price_age_s is None:
        return {
            "text": "",
            "color": "",
            "tip": (
                "No exchange price this tick. Blank rather than the bot's "
                "own last reading, which is not a current value."
            ),
            "position_val": None,
            "priced": False,
            "path": "off_exchange",
        }
    if price_age_s > _PRICE_STALE_AFTER_S:
        return {
            "text": "",
            "color": "",
            "tip": (
                f"Exchange price is {price_age_s:,.0f}s old, past the "
                f"{_PRICE_STALE_AFTER_S:,.0f}s limit. Blank rather than a "
                f"figure priced off it."
            ),
            "position_val": None,
            "priced": False,
            "path": "aged",
        }
    position_val = _priced_position(holdings, cur_price, qrate)
    return {
        "text": f"${abs(position_val):,.4f}",
        "color": "",
        "tip": (
            f"Current position value from the exchange: {holdings:.6f} units "
            f"at ${cur_price:,.4f}, priced {price_age_s:,.0f}s ago."
        ),
        "position_val": position_val,
        "priced": True,
        "path": "priced",
    }


def _compose_ammo_cell(
    stats_pv: float,
    holdings: float,
    cur_price: float,
    qrate: float,
    target_val: float,
    price_age_s: float | None = None,
) -> dict:
    """Compute the Ammo cell: distance from target, and its signal.

    Recomputes ``position_val`` from ``holdings * cur_price * qrate`` whenever
    both are present and falls back to ``stats_pv`` marked stale otherwise.
    Qt-free: returns ``{text, color, tip, delta, stale, position_val}`` with a
    colour name the caller turns into a QColor.
    """

    def _mag(v: float) -> str:
        return f"${abs(v):,.4f}"

    fresh_ok = holdings > 0 and cur_price > 0
    fresh_pv = _priced_position(holdings, cur_price, qrate) if fresh_ok else 0.0
    # Freshness-SELECTED, not max(): recompute whenever the inputs are
    # present, else fall back to the last known value and mark it.
    if fresh_ok:
        position_val, stale = fresh_pv, False
    else:
        position_val, stale = stats_pv, stats_pv > 0

    if position_val <= 0 and holdings <= 0:
        # An empty position reads as a full-target Fold, never as $0.
        delta = 0.0 - target_val
        return {
            "text": _mag(delta) if target_val > 0 else "---",
            "color": _AMMO_FOLD,
            "delta": delta,
            "stale": False,
            "position_val": position_val,
            "tip": (
                "No position — initial entry pending. "
                "Ammo = full target (bot must buy in)."
            ),
        }

    if position_val <= 0 and holdings > 0:
        # Holdings exist, no price and no cached value. Honest pending
        # marker — do NOT render $0.
        return {
            "text": "pending…",
            "color": _AMMO_NEUTRAL,
            "delta": 0.0,
            "stale": False,
            "position_val": position_val,
            "tip": (
                f"Holdings present ({holdings:.6f}) but price not "
                f"yet fetched. Ammo will update on first tick."
            ),
        }

    delta = position_val - target_val
    territory = target_territory(position_val, target_val)
    if territory == "scrum":
        color = _AMMO_SCRUM
        tip = "Scrum territory — sell surplus on bullish"
    elif territory == "fold":
        color = _AMMO_FOLD
        tip = "Fold territory — buy deficit on bearish"
    else:
        color = _AMMO_NEUTRAL
        tip = "Within dust band — no action pending"

    mf_dust = manual_fire_dust_band(target_val)
    # 0 < abs(delta) is a display test, not the engine's rule.
    manual_fire_noop = 0 < abs(delta) and manual_fire_will_noop(
        position_val, target_val
    )
    text = _mag(delta) if target_val > 0 else "---"
    old_price = False
    if stale:
        # The cached stats field was used; it never wears a signal colour.
        color = _AMMO_NEUTRAL
        text = f"{text} {_STALE_MARKER}"
        tip = STALE_TIP_FORMAT.format(stats_pv=stats_pv)
        old_price = True
    elif price_age_s is not None and price_age_s > _PRICE_STALE_AFTER_S:
        # The arithmetic ran; the input price is what aged.
        color = _AMMO_NEUTRAL
        text = f"{text} {_STALE_MARKER}"
        tip = AGED_PRICE_TIP_FORMAT.format(price_age_s=price_age_s)
        old_price = True
    # Appended after all three tip writers, so no branch can drop it.
    if manual_fire_noop:
        tip = MANUAL_FIRE_NOOP_TIP_FORMAT.format(
            tip=tip, magnitude=abs(delta), dust_band=mf_dust
        )
        if old_price:
            tip = f"{tip}{MANUAL_FIRE_NOOP_OLD_PRICE_SUFFIX}"
    return {
        "text": text,
        "color": color,
        "tip": tip,
        "delta": delta,
        "stale": stale,
        "position_val": position_val,
        "manual_fire_noop": manual_fire_noop,
        "price_age_s": price_age_s,
    }


def _compose_table_target_denom_cell(
    quote_currency: str,
    base_asset: str,
    exchange_id: str,
    target_usd: float,
) -> tuple[str, str]:
    """`(cell_text, color_hex)` for a Target-BTC or Target-ETH cell.

    Returns an empty `cell_text` when `base_asset` equals `quote_currency`,
    when `target_usd` is not positive, or when the pair is unlisted on
    `exchange_id`.
    """
    _quote = (quote_currency or "").upper()
    _base = (base_asset or "").upper()
    _neutral = ds.TEXT_MED
    if not _quote or not _base:
        return ("", _neutral)
    if _base == _quote:
        # Self-reference row hidden (e.g. BTC bot's Target BTC cell).
        return ("", _neutral)
    if target_usd <= 0:
        return ("", _neutral)
    try:
        from src.exchange.currency_rate_monitor import get_currency_monitor
        from src.exchange.market_pairs_scout import get_scout

        _rates = get_currency_monitor().snapshot()
        _scout = get_scout()
        if _quote == "BTC":
            _quote_usd = float(_rates.btc_usd or 0)
        elif _quote == "ETH":
            _quote_usd = float(_rates.eth_usd or 0)
        else:
            _quote_usd = 0.0
        if _quote_usd <= 0:
            return ("pending", _neutral)
        _pair = _scout.get_pair(_base, _quote, exchange_id=(exchange_id or None))
        if _pair is None:
            return ("—", _neutral)
        _usd_pair = _scout.get_pair(_base, "USD", exchange_id=(exchange_id or None))
        if _usd_pair is None:
            _usd_pair = _scout.get_pair(
                _base, "USDC", exchange_id=(exchange_id or None)
            )
        _usd_pct = float(_usd_pair.pct_24h) if _usd_pair else 0.0
        _units = target_usd / _quote_usd
        _delta = float(_pair.pct_24h) - _usd_pct
        if abs(_delta) < 0.1:
            _color = _neutral
            _sign = ""
        elif _delta > 0:
            _color = ds.SUCCESS
            _sign = "+"
        else:
            _color = ds.ERROR
            _sign = ""
        return (f"{units_text(_units)} ({_sign}{_delta:.1f}%)", _color)
    except Exception:  # noqa: BLE001 - table paint best-effort
        return ("", _neutral)
