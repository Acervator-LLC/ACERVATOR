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
``WHOLE_UNIT_POSITION_MINIMUM``.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any, Optional, Sequence

from ...exchange.base import SETTLEMENT_DAY_SECONDS
from ...stocks.market_hours import accepts_order

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
def market_unit_rule(
    recorded: Any, asset_class: str = "", venue: str = ""
) -> Optional[str]:
    """The unit rule governing one market: ``recorded_unit_rule`` where the
    venue published a step, else the ``CITED_UNIT_RULES`` row for the pair.

    A recorded step is never raised to ``WHOLE_UNITS`` by the sector row, so
    this answers the rule ``sized_order`` sizes the same amount under.
    """
    declared = recorded_unit_rule(recorded)
    if declared is not None:
        return declared
    return unit_rule(asset_class, venue)


#: The two sessions a venue publishes: one that takes an order at any hour, and
#: the NYSE and NASDAQ session ``market_hours`` declares.
SESSION_CONTINUOUS = "continuous"
SESSION_US_EQUITY = "us_equity"

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
}


def venue_order_types(asset_class: str, venue: str) -> Optional[str]:
    """The order types ``CITED_VENUE_ORDER_TYPES`` cites for ``asset_class`` on
    ``venue``, or None when the table cites none for the pair."""
    return CITED_VENUE_ORDER_TYPES.get((str(asset_class), str(venue)))


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
VARIANT_NONE = "none"
VARIANT_LIMIT_ONLY = "limit-only order"
VARIANT_CASH_AMOUNT = "cash-amount order"
VARIANT_WHOLE_UNIT = "whole-unit position"

# OVERTAKEN, the comment above reading "the three variants the venue comparison
# names": ``VARIANT_ROLLING_POSITION`` is a fourth, named the same way.
VARIANT_ROLLING_POSITION = "rolling position"

#: The market shape each variant absorbs, one row per variant.
VARIANT_MARKETS: dict[str, str] = {
    VARIANT_NONE: "a market naming a unit count on a venue taking a market order",
    VARIANT_LIMIT_ONLY: "a market on a venue declaring no market order",
    VARIANT_CASH_AMOUNT: "a market whose size is a whole share",
    VARIANT_WHOLE_UNIT: "a market whose smallest order costs more than the excess",
    VARIANT_ROLLING_POSITION: "a market the venue expires on a date",
}

#: The variants the running program holds. ``VARIANT_CASH_AMOUNT`` has no caller
#: to reach it and ``VARIANT_WHOLE_UNIT`` waits on the scrum trigger's ruling.
VARIANTS_BUILT = frozenset({VARIANT_NONE, VARIANT_LIMIT_ONLY})

# OVERTAKEN, the comment above reading "``VARIANT_CASH_AMOUNT`` has no caller to
# reach it and ``VARIANT_WHOLE_UNIT`` waits on the scrum trigger's ruling":
# ``VARIANT_ROLLING_POSITION`` is also absent, and it waits on the rule naming
# which contract a position rolls into.
# OVERTAKEN, the sentence above reading "``VARIANT_WHOLE_UNIT`` waits on the
# scrum trigger's ruling": ``variant_holds_market`` holds that variant for a
# market ``market_unit_rule`` reads as ``WHOLE_UNITS``, and
# ``position_minimum_refusal`` refuses its opening order under
# ``WHOLE_UNIT_POSITION_MINIMUM``. ``VARIANTS_BUILT`` itself is unchanged, so
# every caller of ``variant_built`` and ``variant_trades_market`` reads what it
# read before.
# OVERTAKEN, the sentence above reading "every caller of ``variant_built`` and
# ``variant_trades_market`` reads what it read before": ``variant_refuses_sale``
# reads ``variant_holds_market``, so a sale out of a ``WHOLE_UNITS`` market
# fills where a buy into it fills. ``variant_trades_market`` has no caller.

#: What a market no built variant trades carries, naming the variant it needs
#: and the shape that variant absorbs.
UNTRADEABLE_REASON_FORMAT = "{variant} is not built: {market}"


# OVERTAKEN in venue_variant's docstring below: "``VARIANT_WHOLE_UNIT`` while
# ``tradeable_answer`` reads ``TRADEABLE_NO``, ``VARIANT_LIMIT_ONLY`` while the
# record declares ``ORDER_TYPES_LIMIT_ONLY``, and ``VARIANT_NONE`` for every
# other record, an unread one included."
# ``VARIANT_ROLLING_POSITION`` is answered first, while ``MarketRules.expires``
# is True; the three answers above follow it unchanged and read no expiry.
def venue_variant(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> str:
    """The variant one market's own rules select.

    ``VARIANT_WHOLE_UNIT`` while ``tradeable_answer`` reads ``TRADEABLE_NO``,
    ``VARIANT_LIMIT_ONLY`` while the record declares ``ORDER_TYPES_LIMIT_ONLY``,
    and ``VARIANT_NONE`` for every other record, an unread one included.
    """
    if rules is None or not getattr(rules, "read", False):
        return VARIANT_NONE
    if getattr(rules, "expires", False):
        return VARIANT_ROLLING_POSITION
    if tradeable_answer(rules, price, excess_usd) == TRADEABLE_NO:
        return VARIANT_WHOLE_UNIT
    if getattr(rules, "order_types", None) == ORDER_TYPES_LIMIT_ONLY:
        return VARIANT_LIMIT_ONLY
    return VARIANT_NONE


def variant_permits_close(variant: Any) -> bool:
    """True only for ``VARIANT_ROLLING_POSITION``, out of whose market a bot may
    still sell although ``VARIANTS_BUILT`` does not hold the variant."""
    return str(variant) == VARIANT_ROLLING_POSITION


def variant_built(variant: Any) -> bool:
    """True while ``VARIANTS_BUILT`` holds ``variant``."""
    return str(variant) in VARIANTS_BUILT


def variant_market(variant: Any) -> str:
    """The market shape ``VARIANT_MARKETS`` names for ``variant``, empty for a
    name no row holds."""
    return VARIANT_MARKETS.get(str(variant), "")


def variant_replaces_market_order(variant: Any) -> bool:
    """True only for ``VARIANT_LIMIT_ONLY``, which names a limit order where the
    bot names a market order."""
    return str(variant) == VARIANT_LIMIT_ONLY


def variant_trades_market(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> bool:
    """True while the variant ``venue_variant`` selects for one market is one
    ``VARIANTS_BUILT`` holds."""
    return variant_built(venue_variant(rules, price, excess_usd))


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
    fractions keeps the refusal ``variant_trades_market`` gives it.
    """
    variant = venue_variant(rules, price, excess_usd)
    if variant_built(variant):
        return True
    if variant != VARIANT_WHOLE_UNIT:
        return False
    return market_unit_rule(rules, asset_class, venue) == WHOLE_UNITS


def variant_refuses_sale(
    rules: Any,
    asset_class: str = "",
    venue: str = "",
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> bool:
    """True while a sale out of one market refuses as a buy into it refuses:
    ``variant_holds_market`` denies the market and ``variant_permits_close``
    denies the variant, the pair ``BotContainer.guarded_place_order`` reads for
    a sell.
    """
    variant = venue_variant(rules, price, excess_usd)
    held = variant_holds_market(rules, asset_class, venue, price, excess_usd)
    return not held and not variant_permits_close(variant)


def untradeable_reason(
    rules: Any,
    price: Optional[float] = None,
    excess_usd: float = REFERENCE_SCRUM_EXCESS_USD,
) -> str:
    """Why one market is read and not traded, through
    ``UNTRADEABLE_REASON_FORMAT``, and empty while a built variant trades it."""
    variant = venue_variant(rules, price, excess_usd)
    if variant_built(variant):
        return ""
    return UNTRADEABLE_REASON_FORMAT.format(
        variant=variant, market=variant_market(variant)
    )


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


def recorded_size_rules(rules: Any) -> bool:
    """True while ``rules`` was read and published a size step or a minimum
    amount, the two figures ``sized_order`` sizes and refuses by."""
    if rules is None or not getattr(rules, "read", False):
        return False
    if rule_published(getattr(rules, "amount_increment", None)):
        return True
    return rule_published(getattr(rules, "min_amount", None))


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

#: Why a ``WHOLE_UNITS`` market refuses an order that would open a position.
BELOW_POSITION_MINIMUM = (
    f"a whole-unit position opens at {WHOLE_UNIT_POSITION_MINIMUM} units"
)

#: What ``position_minimum_refusal`` names: the market, the units the order
#: carries, one unit's price, and what the minimum costs.
POSITION_MINIMUM_FORMAT = (
    "{symbol}: {reason} and this order carries {units:g}. One unit prices at "
    "${price:,.8f}, so {minimum} units cost ${needed:,.4f}."
)


def whole_unit_position_usd(price: Any) -> Optional[float]:
    """What opening a position costs under ``WHOLE_UNITS``:
    ``WHOLE_UNIT_POSITION_MINIMUM`` units at ``price``.

    None where ``price`` is not a positive finite number, the same unknown
    ``smallest_order_usd`` answers for an unknown price.
    """
    if type(price) not in (int, float):
        return None
    held = float(price)
    if not math.isfinite(held) or held <= 0.0:
        return None
    return float(WHOLE_UNIT_POSITION_MINIMUM) * held


def opens_below_position_minimum(units: Any, rule: Any, position_usd: Any) -> bool:
    """True while an order of ``units`` under ``rule`` opens a position holding
    fewer than ``WHOLE_UNIT_POSITION_MINIMUM`` units.

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
    return carried + WHOLE_UNIT_GRAIN < float(WHOLE_UNIT_POSITION_MINIMUM)


def position_minimum_refusal(
    symbol: Any, units: Any, price: Any, rule: Any, position_usd: Any
) -> str:
    """Why a ``WHOLE_UNITS`` market refuses an opening order, through
    ``POSITION_MINIMUM_FORMAT`` and naming ``symbol`` and ``price``.

    Empty while ``opens_below_position_minimum`` reads False.
    """
    if not opens_below_position_minimum(units, rule, position_usd):
        return ""
    needed = whole_unit_position_usd(price)
    shown_price = float(price) if needed is not None else 0.0
    try:
        shown_units = float(units) if type(units) in (int, float) else 0.0
    except (OverflowError, TypeError, ValueError):
        shown_units = 0.0
    return POSITION_MINIMUM_FORMAT.format(
        symbol=symbol,
        units=shown_units,
        reason=BELOW_POSITION_MINIMUM,
        price=shown_price,
        minimum=WHOLE_UNIT_POSITION_MINIMUM,
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
    "CEILING_MULTIPLE_MAX",
    "CEILING_MULTIPLE_MIN",
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
    "ORDER_TYPES_DECLARED",
    "ORDER_TYPES_LIMIT_ONLY",
    "ORDER_TYPES_WITH_MARKET",
    "POSITION_MINIMUM_FORMAT",
    "REFERENCE_SCRUM_EXCESS_USD",
    "SESSION_CONTINUOUS",
    "SESSION_US_EQUITY",
    "SETTLEMENT_DAY_SECONDS",
    "TAPER_DROP",
    "TAPER_START_RATIO",
    "TRADEABLE_NO",
    "TRADEABLE_UNKNOWN",
    "TRADEABLE_YES",
    "UNIT_RULES",
    "UNTRADEABLE_REASON_FORMAT",
    "VARIANTS_BUILT",
    "VARIANT_CASH_AMOUNT",
    "VARIANT_LIMIT_ONLY",
    "VARIANT_MARKETS",
    "VARIANT_NONE",
    "VARIANT_ROLLING_POSITION",
    "VARIANT_WHOLE_UNIT",
    "WHOLE_UNITS",
    "WHOLE_UNIT_GRAIN",
    "WHOLE_UNIT_POSITION_MINIMUM",
    "cartridge_threshold_usd",
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
    "market_unit_rule",
    "opens_below_position_minimum",
    "opposing_trade_distance_pct",
    "opposing_trade_distances",
    "order_types_for",
    "outside_session",
    "plan_fold_consumption",
    "plan_source_price",
    "position_ceiling",
    "position_minimum_refusal",
    "priced_usd",
    "ratio_to_ceiling",
    "recorded_unit_rule",
    "sale_proceeds_usd",
    "scrum_units",
    "scrumming_interval_usd",
    "settle_fold_plan",
    "sized_units",
    "smallest_order_usd",
    "spend_less_unsettled_usd",
    "target_delta_pct",
    "target_delta_usd",
    "target_growth_applied",
    "tradeable_answer",
    "trim_fold_plan",
    "unit_rule",
    "unsettled_usd",
    "untradeable_reason",
    "variant_built",
    "variant_holds_market",
    "variant_market",
    "variant_permits_close",
    "variant_refuses_sale",
    "variant_replaces_market_order",
    "variant_trades_market",
    "venue_order_types",
    "venue_session",
    "venue_settlement_days",
    "venue_variant",
    "wallet_capped_spend_usd",
    "whole_unit_position_usd",
]
