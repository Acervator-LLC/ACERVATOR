"""The Scrum/Fold cycle's sizing arithmetic, one definition of each figure.

``ScrummingBot.tick``, ``TickPhaseMixin``, ``ExecutionEngineMixin`` and
``FoldTrancheAccountingMixin`` call these at the sites that computed each figure
inline, and ``back_test.walk`` calls the same functions over a ``SimPosition``.
``priced_usd`` through ``cartridge_threshold_usd`` each answer the expression
their Live site held, in that site's operand order, holding no state.
``unit_rule`` answers the rule ``CITED_UNIT_RULES`` cites for an asset class on
a venue, ``scrum_units`` and ``fold_units`` size under that rule through
``sized_units``, and ``trim_fold_plan`` keeps what a whole-unit fold could not
spend in its tranches. ``plan_source_price`` reads the scrum price a fold plan
re-enters against, and ``opposing_trade_distances`` reads the distance between
each fold and that scrum over a run's pairs. ``tradeable_answer`` is the one
place that says whether the built variant can trade one market, measuring
``smallest_order_usd`` against ``REFERENCE_SCRUM_EXCESS_USD``; the Market
Inspector's ticker rows read it.

OVERTAKEN: "``unit_rule`` answers the rule ``CITED_UNIT_RULES`` cites for an
asset class on a venue, ``scrum_units`` and ``fold_units`` size under that rule
through ``sized_units``".
``sized_order`` is the one place an order's amount is sized: a market's own
recorded ``MarketRules`` floor it through ``amount_on_increment`` and refuse it
through ``steps_below_minimum``, and ``CITED_UNIT_RULES`` answers through
``sized_units`` only where no record was recorded. Every ``SizedOrder`` carries
the ``RULE_SOURCE`` that sized it and the refusal reason behind zero units.

OVERTAKEN: "``CITED_UNIT_RULES`` answers through ``sized_units`` only where no
record was recorded."
``market_unit_rule`` is the one place that says which rule governs one market:
``recorded_unit_rule`` reads the venue's own step and ``unit_rule`` answers the
sector where the venue published none, with ``WHOLE_UNITS`` winning wherever
either reads it. ``variant_holds_market`` holds ``VARIANT_WHOLE_UNIT`` for such
a market and ``position_minimum_refusal`` refuses its opening order under
``opening_position_minimum``, which reads the bot's own
``whole_unit_opening_units`` and floors it at ``WHOLE_UNIT_POSITION_MINIMUM``.

OVERTAKEN: "``recorded_unit_rule`` reads the venue's own step and ``unit_rule``
answers the sector where the venue published none".
``permitted_order_shape`` answers before all of them for a market whose own
record publishes a permission set, naming the one member of ``SIZE_SHAPES`` that
set and ``session_size_shapes`` leave, and ``size_shape_refusal`` names the
permission where they leave none; ``venue_variant`` answers
``VARIANT_PERMITTED_SHAPE`` for such a market. ``session_unit_rule`` answers
next, reading ``WHOLE_UNITS`` while the market's own session takes a whole unit
alone at the moment the order is sized, and ``session_for`` names that session
off the market's own record with ``CITED_VENUE_SESSIONS`` answering where the
record carries none.

OVERTAKEN: "``venue_variant`` answers ``VARIANT_PERMITTED_SHAPE`` for such a
market."
``sector_variant`` is the one place that names the variant one market trades
under: ``SECTOR_VARIANTS`` names it off the sector, and ``VARIANT_WHOLE_UNIT``
answers ahead of the sector while the venue's smallest order costs more than the
excess. ``venue_variant`` answers the venue's order-formatting mechanic beside
it, one ``MECHANIC_MARKETS`` name per market, which ``market_permits_close`` and
``market_replaces_market_order`` read on the order path.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any, Optional, Sequence

from ...exchange.base import SETTLEMENT_DAY_SECONDS
from ...stocks.market_hours import MarketSession, accepts_order, session_at

#: The ``state`` an ``ExtractorBot`` writes on a position below its entry value.
DRAWDOWN_STATE = "drawdown"

#: The two unit rules a venue's published documentation states for an asset
#: class: an order may name a fraction of a unit, or only whole units.
FRACTIONAL_UNITS = "fractional"
WHOLE_UNITS = "whole"
UNIT_RULES = (FRACTIONAL_UNITS, WHOLE_UNITS)

#: A unit count within this of a whole number reads as that whole number: the
#: ninth decimal, the most an Alpaca ``qty`` carries.
WHOLE_UNIT_GRAIN = 1e-9

#: The two asset classes the determination table cites, spelled as
#: ``ata_spm.ASSET_CLASSES`` spells them.
CLASS_CRYPTO = "crypto"
CLASS_STOCKS = "stocks"

# OVERTAKEN, the comment above reading "The two asset classes the determination
# table cites": all six of ``ata_spm.ASSET_CLASSES`` are spelled here, and
# ``ata_spm`` imports this module so the spellings cannot be imported from it.
CLASS_COMMODITIES = "commodities"
CLASS_FOREX = "forex"
CLASS_INDICES = "indices"
CLASS_FUTURES_PERPS = "futures_perps"

#: The unit rule each ``(asset class, venue)`` trades under, one row per rule
#: the manual's determination table cites from the venue's published page. A
#: pair absent here has no cited rule and is not simulated.
# OVERTAKEN, the comment above reading "A pair absent here has no cited rule and
# is not simulated": every one of ``ata_spm.ASSET_CLASSES`` has a Coinbase row,
# so no sector the venue serves falls to ``NO_SIZE_RULE``.
CITED_UNIT_RULES: dict[tuple[str, str], str] = {
    (CLASS_CRYPTO, "coinbase"): FRACTIONAL_UNITS,
    # Robinhood publishes asset_increment to 18 decimal places.
    (CLASS_CRYPTO, "robinhood"): FRACTIONAL_UNITS,
    (CLASS_STOCKS, "alpaca"): FRACTIONAL_UNITS,
    (CLASS_FOREX, "coinbase"): FRACTIONAL_UNITS,
    (CLASS_STOCKS, "coinbase"): WHOLE_UNITS,
    (CLASS_COMMODITIES, "coinbase"): WHOLE_UNITS,
    (CLASS_INDICES, "coinbase"): WHOLE_UNITS,
    (CLASS_FUTURES_PERPS, "coinbase"): WHOLE_UNITS,
}

#: ``position_ceiling`` clamps ``position_ceiling_multiple`` to this range.
CEILING_MULTIPLE_MIN = 1.0
CEILING_MULTIPLE_MAX = 10.0

#: ``fold_rate_taper`` reads full size under this ratio and nothing at 1.0.
TAPER_START_RATIO = 0.5

#: How much of the size ``fold_rate_taper`` takes off between the start ratio
#: and 1.0, so the taper lands at a tenth of the size there.
TAPER_DROP = 0.9

#: The Bollinger positions ``growth_cycle_side`` reads as the two extremes: the
#: cycle's consumed cap resets when ``bb_pos`` reaches the extreme opposite the
#: side the last growth fired on.
GROWTH_CYCLE_UPPER_BB = 0.75
GROWTH_CYCLE_LOWER_BB = 0.25

#: The side a fold's target growth is booked on, and the side a scrum-side
#: growth would be booked on.
GROWTH_SIDE_LOWER = "lower"
GROWTH_SIDE_UPPER = "upper"


def priced_usd(units: float, price: float, quote_to_usd: float = 1.0) -> float:
    """``units`` at ``price`` in USD: the position value ``ScrummingBot.tick``
    reads and the notional ``_tick_execute_scrum`` sizes."""
    return units * price * quote_to_usd


def target_delta_usd(position_usd: float, target_balance: float) -> float:
    """The Target Delta: ``position_usd`` less ``target_balance``, positive above
    target."""
    return position_usd - target_balance


def target_delta_pct(delta_usd: float, target_balance: float) -> float:
    """``delta_usd`` as a percentage of ``target_balance``, the ``delta_pct``
    the tick logs."""
    return abs(delta_usd) / (target_balance + 1e-9) * 100


def scrumming_interval_usd(
    target_balance: float, scrumming_interval_pct: float
) -> float:
    """The scrumming interval in USD: ``scrumming_interval_pct`` of
    ``target_balance``."""
    return target_balance * scrumming_interval_pct / 100.0


def delta_below_interval(delta_usd: float, interval_usd: float) -> bool:
    """True when ``delta_usd`` sits inside ``interval_usd``, so the tick holds."""
    return abs(delta_usd) < interval_usd


def unit_rule(asset_class: str, venue: str) -> Optional[str]:
    """The unit rule ``CITED_UNIT_RULES`` cites for ``asset_class`` on
    ``venue``, or None when the table cites none for the pair."""
    return CITED_UNIT_RULES.get((str(asset_class), str(venue)))


def recorded_unit_rule(recorded: Any) -> Optional[str]:
    """The unit rule one market's own recorded ``amount_increment`` states.

    ``WHOLE_UNITS`` where the step is a whole unit or larger,
    ``FRACTIONAL_UNITS`` where it is smaller, and None where the venue
    published no step or the record was never read.
    """
    if recorded is None or not getattr(recorded, "read", False):
        return None
    step = getattr(recorded, "amount_increment", None)
    if not rule_published(step):
        return None
    held = float(step or 0.0)
    if held <= 0.0:
        return None
    return WHOLE_UNITS if held >= 1.0 else FRACTIONAL_UNITS


# ``CLASS_COMMODITIES`` holds a tokenised metal and a dated contract, which
# size differently, so ``recorded_unit_rule`` answers before the sector row.
# OVERTAKEN, the docstring below reading "A recorded step is never raised to
# ``WHOLE_UNITS`` by the sector row": ``session_unit_rule`` raises it, because
# the market's own session takes a whole unit alone outside its normal hours.
# A caller naming no ``moment_s`` reads no session, and one naming no ``side``
# reads no permission set; neither raises a recorded step.
def market_unit_rule(
    recorded: Any,
    asset_class: str = "",
    venue: str = "",
    moment_s: Any = None,
    side: Any = "",
) -> Optional[str]:
    """The unit rule governing one market: ``permitted_order_shape`` for a
    market publishing a permission set, then ``session_unit_rule`` at
    ``moment_s``, then ``recorded_unit_rule``, else the ``CITED_UNIT_RULES`` row.

    A recorded step is never raised to ``WHOLE_UNITS`` by the sector row, so
    this answers the rule ``sized_order`` sizes the same amount under.
    """
    if str(side) in ORDER_SIDES and permits_size_shapes(recorded):
        return shape_unit_rule(permitted_order_shape(recorded, side, moment_s))
    demanded = session_unit_rule(getattr(recorded, "session", None), moment_s)
    if demanded is not None:
        return demanded
    declared = recorded_unit_rule(recorded)
    if declared is not None:
        return declared
    return unit_rule(asset_class, venue)


#: The two sessions a venue publishes: one that takes an order at any hour, and
#: the NYSE and NASDAQ session ``market_hours`` declares.
SESSION_CONTINUOUS = "continuous"
SESSION_US_EQUITY = "us_equity"

#: The two names above, closed. A session outside this pair is no session, so a
#: corrupt recorded value reads as a venue that published nothing.
SESSIONS_DECLARED = (SESSION_CONTINUOUS, SESSION_US_EQUITY)

#: The session each ``(asset class, venue)`` publishes, keyed as
#: ``CITED_UNIT_RULES`` is keyed. A pair absent here publishes no session.
CITED_VENUE_SESSIONS: dict[tuple[str, str], str] = {
    (CLASS_CRYPTO, "coinbase"): SESSION_CONTINUOUS,
    (CLASS_STOCKS, "alpaca"): SESSION_US_EQUITY,
}

#: The reason a held order carries, never one of ``sized_order``'s refusals.
HELD_OUTSIDE_SESSION = "outside the venue's session"

#: The two order-type declarations a venue publishes: one taking a market order
#: beside a limit order, and one taking a limit order alone.
ORDER_TYPES_WITH_MARKET = "market and limit"
ORDER_TYPES_LIMIT_ONLY = "limit only"

#: The two names above, closed. A declaration outside this pair is no
#: declaration, so a corrupt recorded value reads as a venue that said nothing.
ORDER_TYPES_DECLARED = (ORDER_TYPES_WITH_MARKET, ORDER_TYPES_LIMIT_ONLY)

#: The order types each ``(asset class, venue)`` declares, keyed as
#: ``CITED_UNIT_RULES`` is keyed. A pair absent here declares nothing, which
#: ``venue_variant`` never reads as declining a type.
CITED_VENUE_ORDER_TYPES: dict[tuple[str, str], str] = {
    (CLASS_CRYPTO, "coinbase"): ORDER_TYPES_WITH_MARKET,
    (CLASS_CRYPTO, "gemini"): ORDER_TYPES_LIMIT_ONLY,
    # Robinhood publishes market, limit, stop_loss and stop_limit.
    (CLASS_CRYPTO, "robinhood"): ORDER_TYPES_WITH_MARKET,
}


def venue_order_types(asset_class: str, venue: str) -> Optional[str]:
    """The order types ``CITED_VENUE_ORDER_TYPES`` cites for ``asset_class`` on
    ``venue``, or None when the table cites none for the pair."""
    return CITED_VENUE_ORDER_TYPES.get((str(asset_class), str(venue)))


#: The separator a unified symbol puts before its settle currency. A symbol
#: carrying it names a contract, whose market buy names a unit count.
SETTLE_LEG = ":"

#: The venues whose own order path turns a spot market buy into a cash amount,
#: read from each one's order builder. ``coinbase`` sends ``quote_size`` and
#: ``binance`` sends ``quoteOrderQty`` for a spot buy, and both send a unit
#: count on every other order.
# ``gateio`` is a third: its ``POST /spot/orders`` reads ``amount`` as the quote
# currency on a market buy and as the base currency on a market sell.
CITED_CASH_MARKET_BUY: frozenset[str] = frozenset({"binance", "coinbase", "gateio"})

#: Why a ``WHOLE_UNITS`` market buy names a limit order.
MARKET_BUY_NAMES_CASH = "a market buy names a cash amount, not a unit count"


def market_buy_names_cash(symbol: Any, venue: Any) -> bool:
    """True while a market buy into ``symbol`` reaches ``venue`` as a cash
    amount.

    False for a ``venue`` outside ``CITED_CASH_MARKET_BUY`` and for a
    ``symbol`` carrying ``SETTLE_LEG``.
    """
    if str(venue) not in CITED_CASH_MARKET_BUY:
        return False
    if type(symbol) is not str or not symbol:
        return False
    return SETTLE_LEG not in symbol


def whole_unit_buy_needs_limit(symbol: Any, venue: Any, rule: Any) -> bool:
    """True while ``rule`` reads ``WHOLE_UNITS`` and ``market_buy_names_cash``
    reads True for ``symbol`` on ``venue``.

    False for every other ``rule``, so a market held in fractions keeps the
    market order it came in as.
    """
    if str(rule) != WHOLE_UNITS:
        return False
    return market_buy_names_cash(symbol, venue)


# OVERTAKEN, the CITED_VENUE_ORDER_TYPES comment above reading "The order types
# each ``(asset class, venue)`` declares": the venue's own record declares them
# through ``declared_order_types``, and the table answers where it declared none.
def order_types_for(recorded: Any, asset_class: str, venue: str) -> Optional[str]:
    """The order types governing one market: ``recorded.order_types`` where the
    venue declared one ``ORDER_TYPES_DECLARED`` holds, else the
    ``CITED_VENUE_ORDER_TYPES`` row for the pair.

    ``ORDER_TYPES_LIMIT_ONLY`` wins wherever either reads it, so neither source
    can widen what the other refuses.
    """
    declared = getattr(recorded, "order_types", None)
    if type(declared) is not str or declared not in ORDER_TYPES_DECLARED:
        declared = None
    cited = venue_order_types(asset_class, venue)
    if declared == ORDER_TYPES_LIMIT_ONLY or cited == ORDER_TYPES_LIMIT_ONLY:
        return ORDER_TYPES_LIMIT_ONLY
    return declared or cited


def venue_session(asset_class: str, venue: str) -> Optional[str]:
    """The session ``CITED_VENUE_SESSIONS`` cites for ``asset_class`` on
    ``venue``, or None when the table cites none for the pair."""
    return CITED_VENUE_SESSIONS.get((str(asset_class), str(venue)))


# OVERTAKEN, the CITED_VENUE_SESSIONS comment above reading "The session each
# ``(asset class, venue)`` publishes": the venue's own product record publishes
# it through ``market_session``, and the table answers where it published none.
def session_for(recorded: Any, asset_class: str, venue: str) -> Optional[str]:
    """The session governing one market: ``recorded.session`` where the venue
    published one ``SESSIONS_DECLARED`` holds, else the ``CITED_VENUE_SESSIONS``
    row for the pair.

    ``SESSION_US_EQUITY`` wins wherever either source reads it, so neither
    source can widen the hours the other restricts.
    """
    declared = getattr(recorded, "session", None)
    if type(declared) is not str or declared not in SESSIONS_DECLARED:
        declared = None
    cited = venue_session(asset_class, venue)
    if declared == SESSION_US_EQUITY or cited == SESSION_US_EQUITY:
        return SESSION_US_EQUITY
    return declared or cited


#: The settlement delay each ``(asset class, venue)`` publishes, in days, keyed
#: as ``CITED_UNIT_RULES`` is keyed. A pair absent here publishes none, and a
#: cited zero is a venue returning the cash of a sale at once.
CITED_VENUE_SETTLEMENT: dict[tuple[str, str], float] = {
    (CLASS_CRYPTO, "coinbase"): 0.0,
}

#: What a fold carries when ``unsettled_usd`` leaves it nothing to spend.
HELD_UNSETTLED_CASH = "the venue has not settled the sale"


def venue_settlement_days(asset_class: str, venue: str) -> Optional[float]:
    """The settlement delay ``CITED_VENUE_SETTLEMENT`` cites for ``asset_class``
    on ``venue`` in days, or None when the table cites none for the pair."""
    return CITED_VENUE_SETTLEMENT.get((str(asset_class), str(venue)))


def unsettled_usd(tranches: Any, moment_s: Any, settlement_days: Any) -> float:
    """The dollars in ``tranches`` the venue has not settled at ``moment_s``: the
    ``usd`` of each whose ``created_ts`` falls inside ``settlement_days``.

    Zero where the venue published no delay, where ``settlement_days`` is no
    positive finite figure, and where ``moment_s`` is not a finite number.
    """
    if not rule_published(settlement_days):
        return 0.0
    days = float(settlement_days)
    if days <= 0.0:
        return 0.0
    if type(moment_s) not in (int, float) or not math.isfinite(float(moment_s)):
        return 0.0
    cutoff = float(moment_s) - days * SETTLEMENT_DAY_SECONDS
    held = 0.0
    for one in tranches or ():
        if not isinstance(one, dict):
            continue
        created = one.get("created_ts")
        if type(created) not in (int, float) or not math.isfinite(float(created)):
            continue
        if float(created) <= cutoff:
            continue
        usd = one.get("usd")
        if type(usd) not in (int, float) or not math.isfinite(float(usd)):
            continue
        if float(usd) <= 0.0:
            continue
        held += float(usd)
    return held


def spend_less_unsettled_usd(spend: float, cash_usd: Any, held_usd: Any) -> float:
    """``spend`` held to ``cash_usd`` less ``held_usd``, never below zero.

    ``spend`` is answered unchanged while ``held_usd`` is no positive finite
    amount, so a venue publishing no settlement delay caps nothing.
    """
    if type(held_usd) not in (int, float) or not math.isfinite(float(held_usd)):
        return spend
    if float(held_usd) <= 0.0:
        return spend
    if type(cash_usd) not in (int, float) or not math.isfinite(float(cash_usd)):
        return spend
    return min(spend, max(0.0, float(cash_usd) - float(held_usd)))


def outside_session(session: Optional[str], moment_s: Any) -> bool:
    """True only where ``session`` names a session taking no order at
    ``moment_s``, epoch seconds; an unpublished session holds nothing."""
    if session != SESSION_US_EQUITY:
        return False
    if type(moment_s) not in (int, float) or not math.isfinite(float(moment_s)):
        return False
    try:
        return not accepts_order(float(moment_s))
    except (OSError, OverflowError, ValueError):
        return False


# ``MarketSession`` decides this and not ``outside_session``: a venue takes a
# whole-unit order in windows where ``accepts_order`` refuses an order.
def session_unit_rule(session: Optional[str], moment_s: Any) -> Optional[str]:
    """``WHOLE_UNITS`` while ``session`` takes a whole unit alone at
    ``moment_s``, epoch seconds, and None at every other moment.

    ``SESSION_US_EQUITY`` takes a fraction inside ``MarketSession.REGULAR`` and
    a whole unit in every window outside it.
    """
    if session != SESSION_US_EQUITY:
        return None
    if type(moment_s) not in (int, float) or not math.isfinite(float(moment_s)):
        return None
    try:
        regular = session_at(float(moment_s)) == MarketSession.REGULAR
    except (OSError, OverflowError, ValueError):
        return None
    return None if regular else WHOLE_UNITS


#: The three shapes a venue's size field takes: a count of whole units, a count
#: carrying a fraction, and a cash amount in the quote currency.
SHAPE_WHOLE_UNITS = "whole units"
SHAPE_FRACTIONAL_UNITS = "fractional units"
SHAPE_CASH_AMOUNT = "cash amount"

#: The three names above, closed. A name outside this set is no shape, so a
#: corrupt recorded value names nothing rather than widening what is permitted.
SIZE_SHAPES = (SHAPE_WHOLE_UNITS, SHAPE_FRACTIONAL_UNITS, SHAPE_CASH_AMOUNT)

#: The order the shapes are read in: the finest count first, so a market
#: permitting a fraction names the step the venue published for it.
SHAPE_PREFERENCE = (SHAPE_FRACTIONAL_UNITS, SHAPE_WHOLE_UNITS, SHAPE_CASH_AMOUNT)

#: The two sides a venue's permission set names a shape on separately.
SIDE_BUY = "buy"
SIDE_SELL = "sell"
ORDER_SIDES = (SIDE_BUY, SIDE_SELL)


def shapes_named(shapes: Any) -> str:
    """``shapes`` as one phrase in ``SHAPE_PREFERENCE`` order, empty for a set
    naming no member of it."""
    held = shapes or frozenset()
    return ", ".join(one for one in SHAPE_PREFERENCE if one in held)


def permits_size_shapes(recorded: Any) -> bool:
    """True while ``recorded`` publishes a permission set on either side,
    telling an absent set from one naming no shape."""
    for name in ("buy_size_shapes", "sell_size_shapes"):
        if isinstance(getattr(recorded, name, None), (frozenset, set)):
            return True
    return False


def permitted_size_shapes(recorded: Any, side: Any) -> Optional[frozenset]:
    """The shapes ``recorded`` permits on ``side``, off ``buy_size_shapes`` or
    ``sell_size_shapes``.

    None where the venue published no set, an empty frozenset where it published
    one naming no shape, and ``ValueError`` for a side outside ``ORDER_SIDES``.
    """
    held = str(side)
    if held == SIDE_BUY:
        published = getattr(recorded, "buy_size_shapes", None)
    elif held == SIDE_SELL:
        published = getattr(recorded, "sell_size_shapes", None)
    else:
        raise ValueError(f"order side {side!r} is not one of {ORDER_SIDES}")
    if not isinstance(published, (frozenset, set)):
        return None
    return frozenset(str(one) for one in published if str(one) in SIZE_SHAPES)


def session_size_shapes(session: Any, moment_s: Any) -> Optional[frozenset]:
    """The shapes ``session`` leaves at ``moment_s``, epoch seconds.

    ``SHAPE_WHOLE_UNITS`` alone where ``session_unit_rule`` reads
    ``WHOLE_UNITS``, and None at every other moment.
    """
    if session_unit_rule(session, moment_s) != WHOLE_UNITS:
        return None
    return frozenset({SHAPE_WHOLE_UNITS})


def permitted_order_shape(
    recorded: Any, side: Any, moment_s: Any = None
) -> Optional[str]:
    """The shape an order of ``side`` into ``recorded`` names at ``moment_s``,
    the first of ``SHAPE_PREFERENCE`` both its permission set and
    ``session_size_shapes`` leave.

    None where the record publishes no permission set and None where the set and
    the session leave no shape, which ``permits_size_shapes`` tells apart.
    """
    allowed = permitted_size_shapes(recorded, side)
    if allowed is None:
        return None
    narrowed = session_size_shapes(getattr(recorded, "session", None), moment_s)
    if narrowed is not None:
        allowed = allowed & narrowed
    for shape in SHAPE_PREFERENCE:
        if shape in allowed:
            return shape
    return None


def shape_unit_rule(shape: Any) -> Optional[str]:
    """The ``UNIT_RULES`` member ``shape`` sizes a unit count under.

    ``FRACTIONAL_UNITS`` for ``SHAPE_FRACTIONAL_UNITS``, ``WHOLE_UNITS`` for
    ``SHAPE_WHOLE_UNITS``, and None for ``SHAPE_CASH_AMOUNT``, which names no
    unit count.
    """
    held = str(shape)
    if held == SHAPE_FRACTIONAL_UNITS:
        return FRACTIONAL_UNITS
    if held == SHAPE_WHOLE_UNITS:
        return WHOLE_UNITS
    return None


#: The three answers a market gives about the built variant, the bot that names
#: a unit count. ``TRADEABLE_UNKNOWN`` is never read as either other.
TRADEABLE_YES = "can size a scrum"
TRADEABLE_NO = "cannot size a scrum"
TRADEABLE_UNKNOWN = "size rules not read"

#: The highest Target Balance in the saved fleet and the interval every one of
#: its bots carries, read from ``bot_state.json`` on 2026-09-24.
LARGEST_FLEET_TARGET_USD = 350.0
FLEET_SCRUMMING_INTERVAL_PCT = 5.0

#: The largest excess any bot in the saved fleet submits. ``tradeable_answer``
#: measures a market's smallest order against it, so ``TRADEABLE_NO`` means no
#: bot at any target this fleet carries could size a scrum there.
REFERENCE_SCRUM_EXCESS_USD = scrumming_interval_usd(
    LARGEST_FLEET_TARGET_USD, FLEET_SCRUMMING_INTERVAL_PCT
)


def smallest_order_usd(rules: Any, price: Optional[float]) -> Optional[float]:
    """The smallest order ``rules`` accepts, in quote currency, at ``price``.

    ``MarketRules.smallest_amount`` at ``price`` and the venue's own minimum
    order cost, whichever is larger; None when a published size rule needs a
    price and none is known.

    OVERTAKEN: "None when a published size rule needs a price and none is
    known."
    None when a published size rule needs a price and none is known, and also
    when the venue published no size rule and no ``min_cost``, because the floor
    is then unknown rather than zero. A ``min_cost`` the venue published AS zero
    is a known floor of zero and stays one.
    """
    cost = getattr(rules, "min_cost", None)
    cost_published = cost is not None and math.isfinite(cost)
    floor_usd = float(cost) if cost_published else 0.0
    amount = getattr(rules, "smallest_amount", None)
    if amount is None:
        return floor_usd if cost_published else None
    if price is None or not math.isfinite(price) or price <= 0.0:
        return None
    return max(floor_usd, float(amount) * float(price))


def tradeable_answer(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> str:
    """Whether the built variant can trade the market ``rules`` describes.

    ``TRADEABLE_YES`` while the smallest order the venue accepts costs no more
    than ``excess_usd``, ``TRADEABLE_NO`` while it costs more, and
    ``TRADEABLE_UNKNOWN`` while no record was read or no price is known.

    OVERTAKEN: "``TRADEABLE_UNKNOWN`` while no record was read or no price is
    known."
    ``TRADEABLE_UNKNOWN`` while no record was read, no price is known, or
    ``smallest_order_usd`` answers None because the venue published no size rule
    and no minimum cost.
    """
    if rules is None or not getattr(rules, "read", False):
        return TRADEABLE_UNKNOWN
    if not math.isfinite(excess_usd) or excess_usd <= 0.0:
        return TRADEABLE_UNKNOWN
    floor_usd = smallest_order_usd(rules, price)
    if floor_usd is None:
        return TRADEABLE_UNKNOWN
    return TRADEABLE_YES if floor_usd <= excess_usd else TRADEABLE_NO


# OVERTAKEN in this module's docstring: "``tradeable_answer`` is the one place
# that says whether the built variant can trade one market, measuring
# ``smallest_order_usd`` against ``REFERENCE_SCRUM_EXCESS_USD``; the Market
# Inspector's ticker rows read it."
# ``variant_trades_market`` is the one place that says whether a built variant
# trades one market; ``tradeable_answer`` answers the size question it reads.

#: The bot as written, and the three variants the venue comparison names. Each
#: variant is named by the venue shape it absorbs.
# OVERTAKEN, the comment above reading "Each variant is named by the venue shape
# it absorbs": a variant is named by the SECTOR it serves, and the venue shape it
# absorbs is a mechanic the variant reads. ``SECTOR_VARIANTS`` names the first
# axis and ``MECHANIC_MARKETS`` the second.
# OVERTAKEN, the four names below reading ``VARIANT_NONE``,
# ``VARIANT_LIMIT_ONLY``, ``VARIANT_CASH_AMOUNT`` and
# ``VARIANT_ROLLING_POSITION``: each named a venue order-formatting mechanic
# rather than a sector, so each is a ``MECHANIC_`` name below and none is a
# variant. ``VARIANT_CASH_AMOUNT`` is gone; ``size_shape_refusal`` names the
# shape ``permitted_order_shape`` left instead.

#: The variant each sector names, the first axis: a variant exists because a
#: sector needs one. Every key is spelled as ``ata_spm.ASSET_CLASSES`` spells it.
SECTOR_VARIANTS: dict[str, str] = {
    CLASS_CRYPTO: "Crypto Scrumming",
    CLASS_STOCKS: "Stock Scrumming",
    CLASS_COMMODITIES: "Commodity Scrumming",
    CLASS_FOREX: "Forex Scrumming",
    CLASS_INDICES: "Index Scrumming",
    CLASS_FUTURES_PERPS: "Futures Scrumming",
}

#: The variant a market whose smallest order costs more than the excess trades
#: under, whatever its sector. The one variant name the operator approved.
VARIANT_WHOLE_UNIT = "Whole Unit Scrumming"

#: The variant a market read with no sector named trades under, which the Market
#: Inspector's ticker rows and ``variant_trades_market`` ask for.
VARIANT_SECTOR_UNNAMED = "Scrumming"

#: What a market naming a sector no ``SECTOR_VARIANTS`` row holds carries, so a
#: sector with no variant is refused rather than traded under another's.
SECTOR_VARIANT_UNBUILT_FORMAT = "{sector} Scrumming"

#: The second axis: the one order-formatting difference one venue's own protocol
#: puts on a market. A mechanic is a property a sector variant reads while
#: sizing, never a variant of its own.
MECHANIC_NONE = "no order-formatting difference"
MECHANIC_LIMIT_ONLY = "the venue declares no market order"
MECHANIC_EXPIRY = "the venue expires this market on a date"
MECHANIC_SMALLEST_ORDER_OVER_EXCESS = (
    "the venue's smallest order costs more than the excess"
)

#: A market whose own permission set names which of ``SIZE_SHAPES`` each side
#: may take, so one market names three sizes at three hours of one day.
MECHANIC_PERMITTED_SHAPE = "the venue publishes the size shapes each side may take"

#: The market shape each mechanic absorbs, one row per mechanic.
MECHANIC_MARKETS: dict[str, str] = {
    MECHANIC_NONE: "a market naming a unit count on a venue taking a market order",
    MECHANIC_LIMIT_ONLY: "a market on a venue declaring no market order",
    MECHANIC_SMALLEST_ORDER_OVER_EXCESS: (
        "a market whose smallest order costs more than the excess"
    ),
    MECHANIC_EXPIRY: "a market the venue expires on a date",
    MECHANIC_PERMITTED_SHAPE: (
        "a market whose own permission set names the size shapes each side may "
        "take, narrowed by its session"
    ),
}

#: The variants the running program holds: one per sector, the operator's
#: approved whole-unit variant, and the one a market read with no sector asked
#: trades under. A sector outside ``SECTOR_VARIANTS`` is absent here, so
#: ``variant_holds_market`` refuses it.
VARIANTS_BUILT = frozenset(SECTOR_VARIANTS.values()) | {
    VARIANT_WHOLE_UNIT,
    VARIANT_SECTOR_UNNAMED,
}

#: What a market no built variant trades carries, naming the variant it needs
#: and the shape that variant absorbs.
UNTRADEABLE_REASON_FORMAT = "{variant} is not built: {market}"

#: The market shape a sector variant absorbs, read into
#: ``UNTRADEABLE_REASON_FORMAT`` where ``VARIANTS_BUILT`` holds no variant for
#: the sector the market names.
SECTOR_MARKET_FORMAT = "a market the venue serves in its {sector} sector"

#: Why a market ``VARIANT_WHOLE_UNIT`` selects is still not traded: the variant
#: sizes whole units and this market's own step is a fraction.
WHOLE_UNIT_STEP_IS_A_FRACTION = (
    "the whole-unit position variant sizes whole units and this market steps in "
    "fractions, so no built variant sizes an order costing this much"
)


# OVERTAKEN in venue_variant's docstring below: "``VARIANT_WHOLE_UNIT`` while
# ``tradeable_answer`` reads ``TRADEABLE_NO``, ``VARIANT_LIMIT_ONLY`` while the
# record declares ``ORDER_TYPES_LIMIT_ONLY``, and ``VARIANT_NONE`` for every
# other record, an unread one included."
# ``VARIANT_ROLLING_POSITION`` is answered first, while ``MarketRules.expires``
# is True; the three answers above follow it unchanged and read no expiry.
# ``VARIANT_PERMITTED_SHAPE`` follows the expiry, while ``permits_size_shapes``
# reads a published permission set; a market carrying none reads no further.
# OVERTAKEN, every sentence above: ``venue_variant`` answers a ``MECHANIC_``
# name and not a variant, under the same five tests in the same order, so no
# market's answer moves. ``sector_variant`` answers the variant.
# ``MECHANIC_EXPIRY`` is answered first, then ``MECHANIC_PERMITTED_SHAPE``, then
# ``MECHANIC_SMALLEST_ORDER_OVER_EXCESS``, then ``MECHANIC_LIMIT_ONLY``, and
# ``MECHANIC_NONE`` answers every other record, an unread one included.
def venue_variant(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> str:
    """The order-formatting mechanic one market's own rules carry, the second
    axis a ``SECTOR_VARIANTS`` variant reads while sizing.

    One ``MECHANIC_MARKETS`` name per market, the first of the five tests that
    answers.
    """
    if rules is None or not getattr(rules, "read", False):
        return MECHANIC_NONE
    if getattr(rules, "expires", False):
        return MECHANIC_EXPIRY
    if permits_size_shapes(rules):
        return MECHANIC_PERMITTED_SHAPE
    if tradeable_answer(rules, price, excess_usd) == TRADEABLE_NO:
        return MECHANIC_SMALLEST_ORDER_OVER_EXCESS
    if getattr(rules, "order_types", None) == ORDER_TYPES_LIMIT_ONLY:
        return MECHANIC_LIMIT_ONLY
    return MECHANIC_NONE


def sector_variant(
    asset_class: str = "",
    rules: Any = None,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> str:
    """The variant one market trades under: ``SECTOR_VARIANTS`` names it, and
    ``VARIANT_WHOLE_UNIT`` answers ahead of the sector while ``venue_variant``
    reads ``MECHANIC_SMALLEST_ORDER_OVER_EXCESS``.

    ``VARIANT_SECTOR_UNNAMED`` where no sector is asked, and
    ``SECTOR_VARIANT_UNBUILT_FORMAT`` for a sector ``SECTOR_VARIANTS`` has no
    row for, which ``VARIANTS_BUILT`` lacks.
    """
    if venue_variant(rules, price, excess_usd) == MECHANIC_SMALLEST_ORDER_OVER_EXCESS:
        return VARIANT_WHOLE_UNIT
    named = str(asset_class or "")
    if not named:
        return VARIANT_SECTOR_UNNAMED
    held = SECTOR_VARIANTS.get(named)
    if held is not None:
        return held
    return SECTOR_VARIANT_UNBUILT_FORMAT.format(sector=named)


def market_permits_close(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> bool:
    """True only while ``venue_variant`` reads ``MECHANIC_EXPIRY`` for one
    market, whose sell carries the expiry notice
    ``BotContainer.guarded_place_order`` emits."""
    return venue_variant(rules, price, excess_usd) == MECHANIC_EXPIRY


def variant_built(variant: Any) -> bool:
    """True while ``VARIANTS_BUILT`` holds ``variant``."""
    return str(variant) in VARIANTS_BUILT


def mechanic_market(mechanic: Any) -> str:
    """The market shape ``MECHANIC_MARKETS`` names for ``mechanic``, empty for a
    name no row holds."""
    return MECHANIC_MARKETS.get(str(mechanic), "")


def market_replaces_market_order(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> bool:
    """True only while ``venue_variant`` reads ``MECHANIC_LIMIT_ONLY`` for one
    market, which names a limit order where the bot names a market order."""
    return venue_variant(rules, price, excess_usd) == MECHANIC_LIMIT_ONLY


def variant_trades_market(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> bool:
    """True while the program holds the variant one market selects, with no
    class and no venue asked, so ``market_unit_rule`` reads the recorded step."""
    return variant_holds_market(rules, "", "", price, excess_usd)


def variant_holds_market(
    rules: Any,
    asset_class: str = "",
    venue: str = "",
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> bool:
    """True while the program holds the variant ``venue_variant`` selects for
    one market, reading the pair as well as the variant name.

    ``VARIANTS_BUILT`` answers every name, and ``VARIANT_WHOLE_UNIT`` needs
    ``market_unit_rule`` to read ``WHOLE_UNITS`` as well, so a market held in
    fractions is refused although the variant is built.
    """
    variant = sector_variant(asset_class, rules, price, excess_usd)
    if not variant_built(variant):
        return False
    if variant != VARIANT_WHOLE_UNIT:
        return True
    return market_unit_rule(rules, asset_class, venue) == WHOLE_UNITS


def variant_refuses_sale(
    rules: Any,
    asset_class: str = "",
    venue: str = "",
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> bool:
    """True while a sale out of one market refuses as a buy into it refuses:
    ``variant_holds_market`` denies the market and ``market_permits_close``
    denies the mechanic, the pair ``BotContainer.guarded_place_order`` reads for
    a sell.
    """
    held = variant_holds_market(rules, asset_class, venue, price, excess_usd)
    return not held and not market_permits_close(rules, price, excess_usd)


def untradeable_reason(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
    asset_class: str = "",
    venue: str = "",
) -> str:
    """Why one market is read and not traded, empty while
    ``variant_holds_market`` holds it.

    ``UNTRADEABLE_REASON_FORMAT`` names a variant ``VARIANTS_BUILT`` lacks, and
    ``WHOLE_UNIT_STEP_IS_A_FRACTION`` names a built ``VARIANT_WHOLE_UNIT`` whose
    market steps in fractions.
    """
    variant = sector_variant(asset_class, rules, price, excess_usd)
    if variant_holds_market(rules, asset_class, venue, price, excess_usd):
        return ""
    if variant_built(variant):
        return WHOLE_UNIT_STEP_IS_A_FRACTION
    return UNTRADEABLE_REASON_FORMAT.format(
        variant=variant,
        market=SECTOR_MARKET_FORMAT.format(sector=str(asset_class or "")),
    )


#: Why a product's own permission set refuses an order: it names no shape at all
#: for that side, so no count and no cash amount may be sent.
NO_PERMITTED_SHAPE_FORMAT = (
    "the venue's own permission set for this product names no {side} size "
    "shape, so no whole unit, no fraction and no cash amount may be named"
)

#: Why a product's session refuses every shape its permission set permits.
SESSION_REFUSES_SHAPES_FORMAT = (
    "the venue permits {allowed} on a {side} of this product, and its "
    "{session} session takes a whole unit alone at this hour, so no shape is "
    "left to name"
)

#: Why a product permitting a cash amount alone is not sized: the bot names a
#: unit count and ``VARIANT_CASH_AMOUNT`` has no caller.
# OVERTAKEN, the comment above: ``VARIANT_CASH_AMOUNT`` is gone, because a cash
# amount is a venue order-formatting difference and not a sector, so no variant
# is named here and every ``VARIANTS_BUILT`` name sizes a unit count.
CASH_SHAPE_ONLY_FORMAT = (
    "the venue permits a {shape} alone on a {side} of this product, and every "
    "built variant sizes a unit count rather than a cash amount in the quote "
    "currency"
)


def size_shape_refusal(recorded: Any, side: Any, moment_s: Any = None) -> str:
    """Why ``recorded`` refuses an order of ``side`` at ``moment_s`` on its own
    permitted shape, through one of three formats naming the permission set.

    Empty where the record publishes no set and empty where the shape
    ``permitted_order_shape`` leaves names a unit count.
    """
    if not permits_size_shapes(recorded):
        return ""
    allowed = permitted_size_shapes(recorded, side) or frozenset()
    shape = permitted_order_shape(recorded, side, moment_s)
    if shape is None:
        if not allowed:
            return NO_PERMITTED_SHAPE_FORMAT.format(side=side)
        return SESSION_REFUSES_SHAPES_FORMAT.format(
            allowed=shapes_named(allowed),
            side=side,
            session=getattr(recorded, "session", None),
        )
    if shape_unit_rule(shape) is not None:
        return ""
    return CASH_SHAPE_ONLY_FORMAT.format(shape=shape, side=side)


def sized_units(units: float, rule: str) -> float:
    """``units`` under ``rule``: unchanged when fractional, floored to a whole
    number when whole, with a count within ``WHOLE_UNIT_GRAIN`` of a whole
    number read as that number."""
    if rule == FRACTIONAL_UNITS:
        return units
    if rule == WHOLE_UNITS:
        return float(math.floor(units + WHOLE_UNIT_GRAIN))
    raise ValueError(f"unit rule {rule!r} is not one of {UNIT_RULES}")


def scrum_units(delta_usd: float, price: float, rule: str) -> float:
    """The units a scrum sells: ``delta_usd`` at ``price``, sized under
    ``rule``."""
    return sized_units(abs(delta_usd) / price, rule)


#: Which rule sized an order's amount: the market's own recorded rules, the
#: ``CITED_UNIT_RULES`` row for its class and venue, or neither.
RULE_SOURCE_RECORDED = "recorded venue rules"
RULE_SOURCE_CITED = "cited unit rule"
RULE_SOURCE_NONE = "no rule"

#: Why a sized order fills nothing: its dollars buy under one whole unit, the
#: amount steps under the venue's published minimum, or no rule sized it.
BELOW_ONE_UNIT = "below one unit"
BELOW_MINIMUM_AMOUNT = "below the venue's minimum size"
NO_SIZE_RULE = "no size rule for the pair"


@dataclass(frozen=True)
class SizedOrder:
    """The amount an order may name, the ``RULE_SOURCE`` that sized it, and the
    refusal reason while ``units`` is zero."""

    units: float
    source: str
    refusal: str = ""


def rule_published(value: Any) -> bool:
    """True while ``value`` is a finite number the venue published, False for
    the None an unpublished rule carries."""
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def amount_on_increment(units: float, increment: Optional[float]) -> float:
    """``units`` floored onto ``increment`` in exact decimal steps.

    ``units`` is answered unchanged where ``increment`` is no positive finite
    step, and zero where ``units`` is not a positive finite amount.
    """
    if not math.isfinite(units) or units <= 0.0:
        return 0.0
    if not rule_published(increment) or float(increment or 0.0) <= 0.0:
        return units
    try:
        step = Decimal(repr(float(increment or 0.0)))
        steps = (Decimal(repr(units)) / step).to_integral_value(rounding=ROUND_FLOOR)
        return float(steps * step)
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return units


def grained_units(units: float, increment: Optional[float]) -> float:
    """``units`` with ``WHOLE_UNIT_GRAIN`` added where ``increment`` steps in
    whole units, and unchanged on every smaller or unpublished step.

    ``sized_units`` reads a count within ``WHOLE_UNIT_GRAIN`` of a whole number
    as that number, and this answers ``amount_on_increment`` the same count.
    """
    if type(units) not in (int, float):
        return units
    if not math.isfinite(float(units)):
        return units
    if not rule_published(increment) or float(increment or 0.0) < 1.0:
        return units
    return float(units) + WHOLE_UNIT_GRAIN


def whole_unit_over_fractional_step(rule: Any, increment: Optional[float]) -> bool:
    """True while ``rule`` reads ``WHOLE_UNITS`` and ``increment`` is a
    published step below one unit.

    The step a market publishes is the step its fractional order carries, so
    ``WHOLE_UNITS`` overrides it rather than flooring onto it.
    """
    if str(rule) != WHOLE_UNITS:
        return False
    if not rule_published(increment):
        return False
    return float(increment or 0.0) > 0.0 and float(increment or 0.0) < 1.0


def recorded_size_rules(rules: Any) -> bool:
    """True while ``rules`` was read and published a size step or a minimum
    amount, the two figures ``sized_order`` sizes and refuses by."""
    if rules is None or not getattr(rules, "read", False):
        return False
    if rule_published(getattr(rules, "amount_increment", None)):
        return True
    return rule_published(getattr(rules, "min_amount", None))


#: Why an order's amount is a contract count, naming the units one contract
#: stands for beside the two counts.
CONTRACT_COUNT_FORMAT = (
    "One contract stands for {size} units, so {units:.10f} units name "
    "{contracts:.10f} contracts."
)


def contract_size_divides(contract_size: Any) -> bool:
    """True while ``contract_size`` is a published positive finite count of base
    units.

    False for the None an unpublished contract size carries and for a published
    zero, which ``contracts_for_units`` cannot divide by.
    """
    if not rule_published(contract_size):
        return False
    return float(contract_size or 0.0) > 0.0


def contracts_for_units(units: float, contract_size: Optional[float]) -> float:
    """``units`` as the contract count the venue's size field carries.

    A contract standing for ``contract_size`` base units takes ``units`` divided
    by it, and ``units`` is answered unchanged where ``contract_size_divides``
    reads False or one contract stands for one unit.
    """
    if type(units) not in (int, float):
        return units
    try:
        held = float(units)
    except (OverflowError, TypeError, ValueError):
        return units
    if not math.isfinite(held) or not contract_size_divides(contract_size):
        return units
    size = float(contract_size or 0.0)
    if size == 1.0:
        return units
    try:
        return float(Decimal(repr(held)) / Decimal(repr(size)))
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return units


def units_for_contracts(contracts: float, contract_size: Optional[float]) -> float:
    """``contracts`` as the base units they stand for, the inverse of
    ``contracts_for_units``.

    ``contracts`` is answered unchanged where ``contract_size_divides`` reads
    False or one contract stands for one unit.
    """
    if type(contracts) not in (int, float):
        return contracts
    try:
        held = float(contracts)
    except (OverflowError, TypeError, ValueError):
        return contracts
    if not math.isfinite(held) or not contract_size_divides(contract_size):
        return contracts
    size = float(contract_size or 0.0)
    if size == 1.0:
        return contracts
    try:
        return float(Decimal(repr(held)) * Decimal(repr(size)))
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return contracts


def contract_count_note(units: float, contract_size: Optional[float]) -> str:
    """Why an order's amount is a contract count, through
    ``CONTRACT_COUNT_FORMAT``.

    Empty where ``contracts_for_units`` answers ``units`` unchanged.
    """
    counted = contracts_for_units(units, contract_size)
    if counted == units:
        return ""
    return CONTRACT_COUNT_FORMAT.format(
        size=contract_size, units=float(units), contracts=float(counted)
    )


# OVERTAKEN in sized_order's docstring below: "A market the venue published a
# ``min_amount`` for and no step is sized by ``rule`` instead."
# ``whole_unit_over_fractional_step`` sizes a ``WHOLE_UNITS`` market by ``rule``
# as well, over a published step below one unit, and measures the whole count
# against ``min_amount`` again.
def sized_order(units: float, rule: Optional[str], rules: Any = None) -> SizedOrder:
    """``units`` sized to the market's own recorded rules where it has them, and
    to ``rule`` from ``CITED_UNIT_RULES`` where it has none.

    A recorded ``amount_increment`` floors the amount through
    ``amount_increment`` and a recorded ``min_amount`` refuses it through
    ``MarketRules.steps_below_minimum``; a pair with neither a recorded rule nor
    a cited one answers ``NO_SIZE_RULE`` and zero units.

    OVERTAKEN: "A recorded ``amount_increment`` floors the amount through
    ``amount_increment``."
    A market the venue published a ``min_amount`` for and no step is sized by
    ``rule`` instead, so a ``WHOLE_UNITS`` sector still reaches a whole amount.

    OVERTAKEN: "a recorded ``min_amount`` refuses it through
    ``MarketRules.steps_below_minimum``."
    ``grained_units`` answers the count both ``MarketRules.steps_below_minimum``
    and ``amount_on_increment`` read, and a step ``sized_units`` floored is
    measured against ``min_amount`` again.
    """
    if recorded_size_rules(rules):
        held = grained_units(units, getattr(rules, "amount_increment", None))
        if rules.steps_below_minimum(held):
            return SizedOrder(0.0, RULE_SOURCE_RECORDED, BELOW_MINIMUM_AMOUNT)
        if whole_unit_over_fractional_step(rule, rules.amount_increment):
            whole = sized_units(held, WHOLE_UNITS)
            if whole <= 0.0:
                return SizedOrder(0.0, RULE_SOURCE_RECORDED, BELOW_ONE_UNIT)
            if rules.steps_below_minimum(whole):
                return SizedOrder(0.0, RULE_SOURCE_RECORDED, BELOW_MINIMUM_AMOUNT)
            return SizedOrder(whole, RULE_SOURCE_RECORDED)
        stepped = amount_on_increment(held, rules.amount_increment)
        if not rule_published(getattr(rules, "amount_increment", None)):
            if rule in UNIT_RULES:
                stepped = sized_units(stepped, str(rule))
                if rules.steps_below_minimum(stepped):
                    return SizedOrder(0.0, RULE_SOURCE_RECORDED, BELOW_MINIMUM_AMOUNT)
        if stepped <= 0.0:
            return SizedOrder(0.0, RULE_SOURCE_RECORDED, BELOW_ONE_UNIT)
        return SizedOrder(stepped, RULE_SOURCE_RECORDED)
    if rule in UNIT_RULES:
        cited = sized_units(units, str(rule))
        if cited <= 0.0:
            return SizedOrder(0.0, RULE_SOURCE_CITED, BELOW_ONE_UNIT)
        return SizedOrder(cited, RULE_SOURCE_CITED)
    return SizedOrder(0.0, RULE_SOURCE_NONE, NO_SIZE_RULE)


#: The whole units a position opens at under ``WHOLE_UNITS``. One unit cannot
#: scrum: giving it back closes the position instead of rebalancing it.
WHOLE_UNIT_POSITION_MINIMUM = 2

#: Why a ``WHOLE_UNITS`` market refuses an order that would open a position,
#: naming the units ``opening_position_minimum`` requires.
BELOW_POSITION_MINIMUM_FORMAT = "a whole-unit position opens at {minimum} units"

#: ``BELOW_POSITION_MINIMUM_FORMAT`` at ``WHOLE_UNIT_POSITION_MINIMUM``, the
#: refusal reason a caller naming no configured minimum carries.
BELOW_POSITION_MINIMUM = BELOW_POSITION_MINIMUM_FORMAT.format(
    minimum=WHOLE_UNIT_POSITION_MINIMUM
)

#: What ``position_minimum_refusal`` names: the market, the units the order
#: carries, one unit's price, and what the minimum costs.
POSITION_MINIMUM_FORMAT = (
    "{symbol}: {reason} and this order carries {units:g}. One unit prices at "
    "${price:,.8f}, so {minimum} units cost ${needed:,.4f}."
)


def opening_position_minimum(configured: Any = None) -> int:
    """The whole units an opening order carries on a ``WHOLE_UNITS`` market:
    ``configured`` where it raises ``WHOLE_UNIT_POSITION_MINIMUM``, and that
    constant otherwise.

    ``WHOLE_UNIT_POSITION_MINIMUM`` is a floor ``configured`` cannot lower.
    """
    if type(configured) not in (int, float):
        return WHOLE_UNIT_POSITION_MINIMUM
    try:
        held = float(configured)
    except (OverflowError, TypeError, ValueError):
        return WHOLE_UNIT_POSITION_MINIMUM
    if not math.isfinite(held):
        return WHOLE_UNIT_POSITION_MINIMUM
    return max(WHOLE_UNIT_POSITION_MINIMUM, int(held))


def position_minimum_reason(configured: Any = None) -> str:
    """Why a ``WHOLE_UNITS`` market refuses an opening order, through
    ``BELOW_POSITION_MINIMUM_FORMAT`` at ``opening_position_minimum``."""
    return BELOW_POSITION_MINIMUM_FORMAT.format(
        minimum=opening_position_minimum(configured)
    )


def whole_unit_position_usd(price: Any, configured: Any = None) -> Optional[float]:
    """What opening a position costs under ``WHOLE_UNITS``:
    ``opening_position_minimum`` units at ``price``.

    None where ``price`` is not a positive finite number, the same unknown
    ``smallest_order_usd`` answers for an unknown price.
    """
    if type(price) not in (int, float):
        return None
    held = float(price)
    if not math.isfinite(held) or held <= 0.0:
        return None
    return float(opening_position_minimum(configured)) * held


def opens_below_position_minimum(
    units: Any, rule: Any, position_usd: Any, configured: Any = None
) -> bool:
    """True while an order of ``units`` under ``rule`` opens a position holding
    fewer than ``opening_position_minimum`` units.

    False for every rule but ``WHOLE_UNITS``, and false while ``position_usd``
    reads a position already open.
    """
    if str(rule) != WHOLE_UNITS:
        return False
    if type(position_usd) in (int, float):
        held = float(position_usd)
        if math.isfinite(held) and held > 0.0:
            return False
    if type(units) not in (int, float):
        return True
    try:
        carried = float(units)
    except (OverflowError, TypeError, ValueError):
        return True
    if not math.isfinite(carried):
        return True
    return carried + WHOLE_UNIT_GRAIN < float(opening_position_minimum(configured))


def position_minimum_refusal(
    symbol: Any,
    units: Any,
    price: Any,
    rule: Any,
    position_usd: Any,
    configured: Any = None,
) -> str:
    """Why a ``WHOLE_UNITS`` market refuses an opening order, through
    ``POSITION_MINIMUM_FORMAT`` and naming ``symbol`` and ``price``.

    Empty while ``opens_below_position_minimum`` reads False.
    """
    if not opens_below_position_minimum(units, rule, position_usd, configured):
        return ""
    needed = whole_unit_position_usd(price, configured)
    shown_price = float(price) if needed is not None else 0.0
    try:
        shown_units = float(units) if type(units) in (int, float) else 0.0
    except (OverflowError, TypeError, ValueError):
        shown_units = 0.0
    return POSITION_MINIMUM_FORMAT.format(
        symbol=symbol,
        units=shown_units,
        reason=position_minimum_reason(configured),
        price=shown_price,
        minimum=opening_position_minimum(configured),
        needed=needed if needed is not None else 0.0,
    )


def sale_proceeds_usd(gross_usd: float, fee_usd: float) -> float:
    """``gross_usd`` less ``fee_usd``, what a settled sell leaves the bot."""
    return gross_usd - fee_usd


def estimated_fee_usd(notional_usd: float, fee_pct: float) -> float:
    """``fee_pct`` of ``notional_usd``, the fee a run with no venue books; Live
    reads the venue's reported fee and never calls this."""
    return abs(notional_usd) * fee_pct / 100.0


def eligible_fold_tranches(
    tranches: list, ticker_last: float, otd_factor: float
) -> list:
    """The tranches in ``tranches`` whose ``ref`` times ``otd_factor`` is at or
    above ``ticker_last``."""
    return [t for t in tranches if ticker_last <= float(t.get("ref", 0)) * otd_factor]


def cycle_growth_cap_usd(
    target_balance: float, consumed_usd: float, growth_pct: float
) -> float:
    """The per-cycle growth cap: ``growth_pct`` of ``target_balance`` less
    ``consumed_usd``, never below zero."""
    base = max(0.0, target_balance - consumed_usd)
    return base * (growth_pct / 100.0)


def fold_cap_remaining_usd(cycle_cap_usd: float, consumed_usd: float) -> float:
    """What is left of ``cycle_cap_usd`` after ``consumed_usd``, never below
    zero: the room ``plan_fold_consumption`` plans under."""
    return max(0.0, cycle_cap_usd - consumed_usd)


def plan_fold_consumption(
    eligible: list, cap_remaining: float
) -> tuple[list, list, int]:
    """What one fold takes from each tranche in ``eligible`` under
    ``cap_remaining``: the ``(source, usd, units)`` plan, the slices taken, and
    how many tranches were part-consumed."""
    plan: list[tuple[dict, float, float]] = []
    slices: list[dict] = []
    running_usd = 0.0
    partial_count = 0
    for _t in eligible:
        room = cap_remaining - running_usd
        if room <= 1e-12:
            break
        tranche_usd = float(_t.get("usd", 0) or 0)
        tranche_units = float(_t.get("units", 0) or 0)
        if tranche_usd <= 0.0 or tranche_units <= 0.0:
            continue
        if tranche_usd <= room + 1e-9:
            take_usd = tranche_usd
            take_units = tranche_units
        else:
            take_usd = room
            take_units = tranche_units * (take_usd / tranche_usd)
            partial_count += 1
        slices.append(
            {
                "usd": take_usd,
                "units": take_units,
                "ref": float(_t.get("ref", 0) or 0),
                "initial_buy_price": _t["initial_buy_price"],
                "created_ts": _t.get("created_ts", 0.0),
            }
        )
        plan.append((_t, take_usd, take_units))
        running_usd += take_usd
    return plan, slices, partial_count


def settle_fold_plan(tranches: list, plan: list) -> tuple[list, int, int]:
    """Take from each source tranche in ``plan`` what it says, and answer the
    tranches left, how many records left ``tranches``, and how many were
    drained to nothing."""
    pre_remove = len(tranches)
    spent: set[int] = set()
    for src, took_usd, took_units in plan:
        src["usd"] = max(0.0, float(src.get("usd", 0) or 0) - took_usd)
        src["units"] = max(0.0, float(src.get("units", 0) or 0) - took_units)
        if src["usd"] <= 1e-9 or src["units"] <= 1e-12:
            spent.add(id(src))
        else:
            src["fold_partial_spent"] = True
    kept = [t for t in tranches if id(t) not in spent]
    return kept, pre_remove - len(kept), len(spent)


def plan_source_price(plan: list) -> float:
    """The scrum price a fold under ``plan`` re-enters against: each source
    tranche's ``ref`` weighted by the USD the plan takes from it; zero for an
    empty ``plan`` or one taking no USD."""
    taken_usd = sum(float(take_usd) for _src, take_usd, _units in plan)
    if taken_usd <= 0.0:
        return 0.0
    weighted = sum(
        float(src.get("ref", 0) or 0) * float(take_usd)
        for src, take_usd, _units in plan
    )
    return weighted / taken_usd


def opposing_trade_distance_pct(scrum_price: float, fold_price: float) -> float:
    """``scrum_price`` less ``fold_price`` as a percentage of ``scrum_price``,
    positive for a fold that re-entered below its scrum."""
    return 100.0 * (float(scrum_price) - float(fold_price)) / float(scrum_price)


def opposing_trade_distances(pairs: Sequence[Sequence[float]]) -> dict:
    """``opposing_trade_distance_pct`` over each ``(scrum_price, fold_price)``
    in ``pairs`` whose scrum price is above zero: the ``count``, the
    ``mean_pct``, the ``median_pct`` and the ``distances_pct``, the two figures
    None when ``count`` is zero."""
    distances = [
        opposing_trade_distance_pct(scrum, fold)
        for scrum, fold in pairs
        if float(scrum) > 0.0
    ]
    return {
        "count": len(distances),
        "mean_pct": statistics.mean(distances) if distances else None,
        "median_pct": statistics.median(distances) if distances else None,
        "distances_pct": distances,
    }


def fold_spend_usd(eligible_usd: float, taper: float) -> float:
    """The USD a fold buys with: ``eligible_usd`` times ``taper``."""
    return eligible_usd * taper


def fold_surplus_usd(units_bought: float, slices: list, fill_price: float) -> float:
    """The surplus one fold realised, as ``_tick_execute_fold`` books it:
    the units bought less the units the consumed ``slices`` sold at their
    ``ref``, priced at ``fill_price``; never below zero."""
    asset_at_scrum = sum(
        float(one.get("usd", 0) or 0) / float(one.get("ref", 0) or 0)
        for one in slices
        if float(one.get("ref", 0) or 0) > 0
    )
    return max(0.0, priced_usd(float(units_bought) - asset_at_scrum, float(fill_price)))


def target_growth_applied(
    surplus_usd: float, standing_usd: float, cap_remaining_usd: float
) -> tuple[float, float]:
    """What ``_apply_fold_target_growth`` adds to the target and what it parks:
    ``(applied, standing_after)`` where the applied growth is the surplus plus
    the standing pool held to ``cap_remaining_usd``, and the rest stays
    standing; nothing is applied when the cap is consumed."""
    if cap_remaining_usd <= 1e-9:
        return 0.0, max(0.0, float(standing_usd) + max(0.0, float(surplus_usd)))
    available = max(0.0, float(surplus_usd)) + max(0.0, float(standing_usd))
    applied = min(available, float(cap_remaining_usd))
    return applied, max(0.0, available - applied)


def growth_cycle_side(
    last_side: Optional[str], bb_pos: float
) -> tuple[Optional[str], bool]:
    """The tick's growth-cycle reading over ``bb_pos``: ``(side_after,
    reset)``. A ``last_side`` of ``GROWTH_SIDE_LOWER`` resets at or above
    ``GROWTH_CYCLE_UPPER_BB``, ``GROWTH_SIDE_UPPER`` at or below
    ``GROWTH_CYCLE_LOWER_BB``, and no side takes the extreme it sits at."""
    at = max(0.0, min(1.0, float(bb_pos)))
    at_upper = at >= GROWTH_CYCLE_UPPER_BB
    at_lower = at <= GROWTH_CYCLE_LOWER_BB
    if last_side == GROWTH_SIDE_LOWER and at_upper:
        return None, True
    if last_side == GROWTH_SIDE_UPPER and at_lower:
        return None, True
    if last_side is None and (at_upper or at_lower):
        return (GROWTH_SIDE_LOWER if at_lower else GROWTH_SIDE_UPPER), False
    return last_side, False


def wallet_capped_spend_usd(spend_usd: float, available_usd: float) -> float:
    """``spend_usd`` held to ``available_usd``, the cap Manual Fire applies."""
    return min(spend_usd, available_usd)


def fold_units(spend_usd: float, price: float, rule: str) -> float:
    """The units a buy of ``spend_usd`` at ``price`` books, sized under
    ``rule``."""
    return sized_units(spend_usd / price, rule)


def trim_fold_plan(plan: list, unspent_usd: float) -> list:
    """``plan`` with ``unspent_usd`` taken back off its last entries, dollars
    and units alike, so ``settle_fold_plan`` leaves in the tranches what a
    whole-unit fold could not spend."""
    left = float(unspent_usd)
    trimmed: list = []
    for source, take_usd, take_units in reversed(plan):
        if left <= 1e-12:
            trimmed.append((source, take_usd, take_units))
            continue
        given_back = min(left, take_usd)
        keep_usd = take_usd - given_back
        keep_units = take_units * (keep_usd / take_usd) if take_usd > 0.0 else 0.0
        left -= given_back
        if keep_usd > 1e-12:
            trimmed.append((source, keep_usd, keep_units))
    trimmed.reverse()
    return trimmed


def position_ceiling(anchor_target_balance: float, multiple: float) -> float:
    """``anchor_target_balance`` times ``multiple`` clamped to
    ``CEILING_MULTIPLE_MIN`` and ``CEILING_MULTIPLE_MAX``."""
    mult = max(CEILING_MULTIPLE_MIN, min(CEILING_MULTIPLE_MAX, multiple))
    return anchor_target_balance * mult


def ratio_to_ceiling(position_usd: float, ceiling_usd: float) -> float:
    """How much of ``ceiling_usd`` the position at ``position_usd`` fills."""
    return position_usd / ceiling_usd


def fold_rate_taper(ratio: float) -> float:
    """The multiplier on a fold's USD size for ``ratio``: full under
    ``TAPER_START_RATIO``, then linear by ``TAPER_DROP`` to 1.0, and nothing
    from 1.0 up."""
    if ratio >= 1.0:
        return 0.0
    if ratio < TAPER_START_RATIO:
        return 1.0
    return 1.0 - (ratio - TAPER_START_RATIO) / TAPER_START_RATIO * TAPER_DROP


def cartridge_threshold_usd(target_balance: float, cartridge_pct: float) -> float:
    """The Target Delta at which the cartridge fires: ``cartridge_pct`` of
    ``target_balance``."""
    return target_balance * cartridge_pct / 100.0


__all__ = [
    "BELOW_POSITION_MINIMUM",
    "BELOW_POSITION_MINIMUM_FORMAT",
    "CASH_SHAPE_ONLY_FORMAT",
    "CEILING_MULTIPLE_MAX",
    "CEILING_MULTIPLE_MIN",
    "CITED_CASH_MARKET_BUY",
    "CITED_UNIT_RULES",
    "CITED_VENUE_ORDER_TYPES",
    "CITED_VENUE_SESSIONS",
    "CITED_VENUE_SETTLEMENT",
    "CLASS_COMMODITIES",
    "CLASS_CRYPTO",
    "CLASS_FOREX",
    "CLASS_FUTURES_PERPS",
    "CLASS_INDICES",
    "CLASS_STOCKS",
    "CONTRACT_COUNT_FORMAT",
    "DRAWDOWN_STATE",
    "FLEET_SCRUMMING_INTERVAL_PCT",
    "FRACTIONAL_UNITS",
    "GROWTH_CYCLE_LOWER_BB",
    "GROWTH_CYCLE_UPPER_BB",
    "GROWTH_SIDE_LOWER",
    "GROWTH_SIDE_UPPER",
    "HELD_OUTSIDE_SESSION",
    "HELD_UNSETTLED_CASH",
    "LARGEST_FLEET_TARGET_USD",
    "MARKET_BUY_NAMES_CASH",
    "NO_PERMITTED_SHAPE_FORMAT",
    "ORDER_SIDES",
    "ORDER_TYPES_DECLARED",
    "ORDER_TYPES_LIMIT_ONLY",
    "ORDER_TYPES_WITH_MARKET",
    "POSITION_MINIMUM_FORMAT",
    "REFERENCE_SCRUM_EXCESS_USD",
    "SESSIONS_DECLARED",
    "SESSION_CONTINUOUS",
    "SESSION_REFUSES_SHAPES_FORMAT",
    "SESSION_US_EQUITY",
    "SETTLEMENT_DAY_SECONDS",
    "SETTLE_LEG",
    "SHAPE_CASH_AMOUNT",
    "SHAPE_FRACTIONAL_UNITS",
    "SHAPE_PREFERENCE",
    "SHAPE_WHOLE_UNITS",
    "SIDE_BUY",
    "SIDE_SELL",
    "SIZE_SHAPES",
    "TAPER_DROP",
    "TAPER_START_RATIO",
    "TRADEABLE_NO",
    "TRADEABLE_UNKNOWN",
    "TRADEABLE_YES",
    "UNIT_RULES",
    "UNTRADEABLE_REASON_FORMAT",
    "MECHANIC_EXPIRY",
    "MECHANIC_LIMIT_ONLY",
    "MECHANIC_MARKETS",
    "MECHANIC_NONE",
    "MECHANIC_PERMITTED_SHAPE",
    "MECHANIC_SMALLEST_ORDER_OVER_EXCESS",
    "SECTOR_MARKET_FORMAT",
    "SECTOR_VARIANTS",
    "SECTOR_VARIANT_UNBUILT_FORMAT",
    "VARIANTS_BUILT",
    "VARIANT_SECTOR_UNNAMED",
    "VARIANT_WHOLE_UNIT",
    "WHOLE_UNITS",
    "WHOLE_UNIT_GRAIN",
    "WHOLE_UNIT_POSITION_MINIMUM",
    "WHOLE_UNIT_STEP_IS_A_FRACTION",
    "cartridge_threshold_usd",
    "contract_count_note",
    "contract_size_divides",
    "contracts_for_units",
    "cycle_growth_cap_usd",
    "delta_below_interval",
    "eligible_fold_tranches",
    "estimated_fee_usd",
    "fold_cap_remaining_usd",
    "fold_rate_taper",
    "fold_spend_usd",
    "fold_surplus_usd",
    "fold_units",
    "grained_units",
    "growth_cycle_side",
    "market_buy_names_cash",
    "market_permits_close",
    "market_replaces_market_order",
    "market_unit_rule",
    "mechanic_market",
    "opening_position_minimum",
    "opens_below_position_minimum",
    "opposing_trade_distance_pct",
    "opposing_trade_distances",
    "order_types_for",
    "outside_session",
    "permits_size_shapes",
    "permitted_order_shape",
    "permitted_size_shapes",
    "plan_fold_consumption",
    "plan_source_price",
    "position_ceiling",
    "position_minimum_reason",
    "position_minimum_refusal",
    "priced_usd",
    "ratio_to_ceiling",
    "recorded_unit_rule",
    "sale_proceeds_usd",
    "scrum_units",
    "sector_variant",
    "scrumming_interval_usd",
    "session_for",
    "session_size_shapes",
    "session_unit_rule",
    "settle_fold_plan",
    "shape_unit_rule",
    "shapes_named",
    "size_shape_refusal",
    "sized_units",
    "smallest_order_usd",
    "spend_less_unsettled_usd",
    "target_delta_pct",
    "target_delta_usd",
    "target_growth_applied",
    "tradeable_answer",
    "trim_fold_plan",
    "unit_rule",
    "units_for_contracts",
    "unsettled_usd",
    "untradeable_reason",
    "variant_built",
    "variant_holds_market",
    "variant_refuses_sale",
    "variant_trades_market",
    "venue_order_types",
    "venue_session",
    "venue_settlement_days",
    "venue_variant",
    "wallet_capped_spend_usd",
    "whole_unit_buy_needs_limit",
    "whole_unit_over_fractional_step",
    "whole_unit_position_usd",
]
