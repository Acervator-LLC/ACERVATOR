"""Pure text-and-colour formatters for the bot-table Ammo and Target-denom
cells.

No Qt: the caller applies the returned hex with ``QColor``. Module scope
so the bot tables and their pin tests read one definition.
"""

from __future__ import annotations

import logging
import time

from . import design_system as ds

# THE ENGINE OWNS THE BANDS. The Ammo cell says what the tick and the
# Fire button are about to do, so it reads their thresholds rather than
# restating them. See ``_compose_ammo_cell``.
from ..trading.target_bands import (
    MANUAL_FIRE_PCT,
    manual_fire_dust_band,
    manual_fire_will_noop,
    target_territory,
)

logger = logging.getLogger("acervator.gui")

# v3.24.38 (C10 / NF-5) — appended to any dashboard figure that could
# not be recomputed this tick. A module constant so pins assert against
# the same string the renderer uses rather than a copy that can drift.
_STALE_MARKER = "(stale)"

_AMMO_SCRUM = ds.SUCCESS
_AMMO_FOLD = ds.ERROR
_AMMO_NEUTRAL = ds.TEXT_MED

# v3.24.xx — the age past which a displayed price is called out as old.
# The bulk refresher (BotManager._ticker_refresh_loop) rewarms the shared
# cache every 5s, so anything materially older than that means the
# refresher is not running and the reading came from the bot's own gated
# fetch instead.
_PRICE_STALE_AFTER_S = 20.0

# Manual Fire's own no-op band, RE-EXPORTED from the engine rather than
# mirrored. The dashboard's actionable band is 0.1% and this one is 1%,
# so there is a 10x window in which the cell renders a confident signal
# colour and Manual Fire silently returns "already within dust band ...
# No-op". Operator 2026-08-06: "strange, intermittent and hard to
# explain amounts". Zero is one of those amounts, and the cell warns.
#
# It used to be a literal copy of ``scrumming_bot.py``'s, kept honest by
# a test that read the engine's SOURCE TEXT for "* 0.01". Issue #128 R2
# made both sides call ``src/trading/target_bands.py``, so there is now
# one number and nothing to keep in step.
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
    except Exception:  # R28-OK: display must render without a pool
        logger.debug("Ammo: data pool unavailable", exc_info=True)
        return None


def _fresh_display_price(pool, exchange_id: str, symbol: str, fallback_price: float):
    """Best available price for DISPLAY, plus its age in seconds.

    WHY THIS EXISTS (corrects a wrong fix shipped 2026-08-06)
    The dashboard reads ``stats.current_price``, whose only recurring
    writer is ``ScrummingBot.tick`` (``src/trading/scrumming_bot.py``)
    -- downstream of the read-rate
    gate. Measured 2026-08-06: that field refreshes no faster than every
    60s on 29 bots and every 300s on 6, while the cell repaints every
    2s. The bulk ticker refresher was shipped believing it fixed this;
    it does not, because it warms the shared cache and never writes
    ``stats.current_price``. This reader is the half that was missing.

    DISPLAY ONLY. The trading path keeps reading ``stats.current_price``
    on its own cadence, so nothing here changes what any bot decides or
    transacts.

    The pool entry is never older than ``stats.current_price``: the bot
    populates that field FROM a pool fetch, so the cache is written at
    or before the same instant. Preferring it is therefore always a
    freshness win, never a regression.

    Returns ``(price, age_seconds_or_None)``. Falls back to the passed
    price when the pool is unavailable, unwired, or has no entry -- the
    dashboard must render in test harnesses and paper mode too.
    """
    try:
        entry = pool.get_ticker(exchange_id, symbol) if pool else None
        if entry is not None:
            last = float(getattr(entry, "last", 0) or 0)
            fetched = float(getattr(entry, "fetch_time", 0) or 0)
            if last > 0 and fetched > 0:
                return last, max(0.0, time.time() - fetched)
    except Exception:  # R28-OK: display path must never raise on a cache read
        logger.debug(
            "Ammo: pool price lookup failed for %s/%s",
            exchange_id,
            symbol,
            exc_info=True,
        )
    return fallback_price, None


def _compose_ammo_cell(
    stats_pv: float,
    holdings: float,
    cur_price: float,
    qrate: float,
    target_val: float,
    price_age_s: float | None = None,
) -> dict:
    """Compute the Ammo cell: distance from target, and its signal.

    v3.24.38 (C10 / NF-5). Extracted from ``update_bots`` so the most
    safety-critical number on the dashboard can be tested without
    booting a window — the same shape as the existing
    ``_compose_table_target_denom_cell`` helper. Deliberately Qt-free:
    it returns a colour NAME and the caller builds the QColor.

    THE DEFECT THIS REPLACES
    ``position_val = max(stats_pv, fresh_pv)``, justified in-line as
    "whichever is non-zero is the real exposure". That holds only when
    one of them IS zero. With both non-zero, max() picks the larger,
    which is the STALE one exactly when the price has fallen:

        target $50, holdings 5, price 20 -> 8
          max()  : pv=100  delta=+50  SCRUM (sell surplus)
          fresh  : pv= 40  delta=-10  FOLD  (buy deficit)

    A full inversion of the signal on the Manual Fire surface, biased in
    one direction only: it is correct while prices rise and wrong while
    they fall. delta also stays pinned at the high-water mark no matter
    how far the price drops, so the worse the fall the more wrong it
    gets. On an ACCUMULATION platform it says sell precisely when it
    should say buy.

    Returns {text, color, tip, delta, stale, position_val}.
    """

    def _mag(v: float) -> str:
        return f"${abs(v):,.4f}"

    fresh_ok = holdings > 0 and cur_price > 0
    fresh_pv = holdings * cur_price * qrate if fresh_ok else 0.0
    # Freshness-SELECTED, not max(): recompute whenever the inputs are
    # present, else fall back to the last known value and mark it.
    if fresh_ok:
        position_val, stale = fresh_pv, False
    else:
        position_val, stale = stats_pv, stats_pv > 0

    if position_val <= 0 and holdings <= 0:
        # Genuinely empty position (never held, never traded). Ammo =
        # full target as a Fold signal; the operator needs initial
        # entry. Not hidden, and not a rogue $0.
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
    # THE ENGINE'S OWN TEST, not a copy of it. ``target_territory``
    # applies the same band ``tick()`` parks inside, so the colour on
    # this cell cannot say SCRUM while the tick sits at target.
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

    # Manual Fire refuses to act inside its OWN band, which is 10x this
    # one (1% of target vs 0.1% here). In that window the cell would
    # otherwise render a confident signal colour for an order that
    # silently never happens. Say so on the cell rather than letting the
    # operator discover it by firing.
    mf_dust = manual_fire_dust_band(target_val)
    # ``0 < abs(delta)`` is the DISPLAY half and is not the engine's
    # rule: a bot sitting exactly on target has nothing to fire, so
    # warning about a refusal there would be noise.
    manual_fire_noop = 0 < abs(delta) and manual_fire_will_noop(
        position_val, target_val
    )
    if manual_fire_noop and not stale:
        tip = (
            f"{tip}\n\nMANUAL FIRE WILL NOT ACT: |delta| "
            f"${abs(delta):,.4f} is inside Manual Fire's own dust "
            f"band of ${mf_dust:,.2f} (1% of target). The autonomous "
            f"engine still works this range; the button will no-op."
        )

    text = _mag(delta) if target_val > 0 else "---"
    if stale:
        # The value came from the cached stats field because holdings x
        # price was not computable this tick. Show it, but never as a
        # confident number, and never wearing a signal colour — an
        # unmarked figure of unknown age is what NF-5 was.
        color = _AMMO_NEUTRAL
        text = f"{text} {_STALE_MARKER}"
        tip = (
            f"STALE — price unavailable this tick, so this is the last "
            f"known position value (${stats_pv:,.4f}), not a current "
            f"one. Do not fire on it."
        )
    elif price_age_s is not None and price_age_s > _PRICE_STALE_AFTER_S:
        # Computable, but from an old price. Distinct from the branch
        # above: the arithmetic ran, the INPUT is what aged. Previously
        # this was rendered as a confident number with nothing to
        # distinguish a 2-second price from a 5-minute one.
        color = _AMMO_NEUTRAL
        text = f"{text} {_STALE_MARKER}"
        tip = (
            f"PRICE {price_age_s:,.0f}s OLD — this figure is computed "
            f"from a price that has not refreshed recently, so the "
            f"true delta may differ. Manual Fire will act on the "
            f"CURRENT price, not this one."
        )
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


# v3.23.49 — pure formatter for the main BotStatusTable Target-BTC /
# Target-ETH cells. Module-level so pin tests import without Qt.
#
# Returns ``(cell_text, color_hex)``. Reads MarketPairsScout +
# CurrencyRateMonitor at call time. Blank ("") + neutral grey when:
#   - target asset is the same as the quote (self-reference), OR
#   - the <base>/<quote> pair isn't listed on the bot's exchange, OR
#   - the currency-rate monitor hasn't populated the USD spot yet.
#
# Cell format: "0.00400 (+1.5%)"  — single line, ~14 chars. The
# color hex is applied by the caller via item.setForeground(QColor(hex)).
def _compose_table_target_denom_cell(
    quote_currency: str,
    base_asset: str,
    exchange_id: str,
    target_usd: float,
) -> tuple[str, str]:
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
        # Compact units — 5 sig figures below 1, 4 decimals above.
        if _units >= 1:
            _units_txt = f"{_units:.4f}"
        elif _units >= 0.01:
            _units_txt = f"{_units:.5f}"
        else:
            _units_txt = f"{_units:.6f}"
        return (f"{_units_txt} ({_sign}{_delta:.1f}%)", _color)
    except Exception:  # noqa: BLE001 - table paint best-effort
        return ("", _neutral)
