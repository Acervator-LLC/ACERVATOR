"""``calculation_steps`` reads one History row's ``trade.log`` lines, runs ``pair_fill`` and each engine function, and answers a ``Calculation``."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Generator, Optional

from src.core.emit_contracts import TARGET_GROWTH_FIELDS, TargetGrowth
from src.exchange.history_helpers import (
    JOIN_TOLERANCE_SECONDS,
    resolve_bot_id_for_row,
)
from src.trading import order_pairing as op
from src.trading.container.config import as_finite_float
from src.trading.otd_math import (
    DistanceSettings,
    DistanceSettingUnreadable,
    fold_rebuy_price,
)
from src.trading.scrumming.execution import SettledFillFee, venue_fee_pct
from src.trading.scrumming.sizing import (
    fold_cap_remaining_usd,
    fold_gain_usd,
    growth_surplus_usd,
    priced_usd,
    restore_cost_usd,
    restored_sale_surplus_usd,
    routed_share_pct,
    sale_proceeds_usd,
    target_growth_applied,
)

if TYPE_CHECKING:
    from pathlib import Path

WINDOW_TITLE = "Trade Calculator"
ACCESSIBLE_NAME = "Trade Calculator"
TITLE_NAME = "Trade Calculator fill"
TABLE_NAME = "Trade Calculator steps"
READING_TEXT = "Reading the trade record..."
COLUMN_HEADERS = ("Step", "Engine function", "Inputs", "Computed", "Recorded", "Check")
INPUTS_COLUMN = COLUMN_HEADERS.index("Inputs")
WINDOW_WIDTH_PX = 1180
WINDOW_HEIGHT_PX = 720
SECTION_COLOR = "#00ffcc"

EQUAL = "equal"
DIFFERS = "differs"
CHECK_COLORS = {EQUAL: "#00ff88", DIFFERS: "#ff5566"}

TRADE_LOG_NAME = "trade.log"
READ_CHUNK_BYTES = 1 << 20
CHAIN_FOLD_SOURCE = "auto"
"""The ``TargetGrowth.source`` a chain fold records, whose gain ``fold_gain_usd`` gives from the line alone."""

SECTION_FILL = "The fill"
SECTION_RECORD = "The platform's record"
SECTION_PAIR = "The pair"
SECTION_LINE = "The arithmetic, line {number}: {action} at {stamp}"

FOUND_BY_ORDER = "by the venue order id the line names"
FOUND_BY_FIGURES = "by side, units, price and a time inside 60 s, because the fill or the line names no order"
NO_ORDER_ON_ROW = "the venue's fill names no order"
NO_LINE = "no line of the trade record names order {order}"
NO_LINE_BY_FIGURES = (
    "and no line without an order id matches its side, units, price and time"
)
NO_BOT = "no running bot trades this market, so no distance is read"
MOTD_OF_BOT = "the bot's own distance today"
MOTD_DEFAULT = "the 5% default, because no running bot trades this market"
OTHER_SOURCE_GAIN = "a {source} gain sums each spent tranche's own dollars, which the line does not hold"
OTHER_OPENERS = "a sale here opened tranches other buys spent as well"
OTHER_SPENDERS = "a buy here spent tranches other sales opened as well"


def usd_text(value: Optional[float]) -> str:
    """``value`` as dollars to four places, or empty for None."""
    return "" if value is None else f"${value:,.4f}"


def units_text(value: Optional[float]) -> str:
    """``value`` as units to eight places, or empty for None."""
    return "" if value is None else f"{value:,.8f}"


def price_text(value: Optional[float]) -> str:
    """``value`` as a price to eight places, or empty for None."""
    return "" if value is None else f"${value:,.8f}"


def pct_text(value: Optional[float]) -> str:
    """``value`` as a percent to four places, or empty for None."""
    return "" if value is None else f"{value:.4f}%"


FORMATS: dict[str, Callable[[Optional[float]], str]] = {
    "usd": usd_text,
    "units": units_text,
    "price": price_text,
    "pct": pct_text,
}


@dataclass(frozen=True)
class Step:
    """One arithmetic step: the engine ``function``, its ``inputs``, the ``computed`` and the ``recorded`` figure."""

    name: str
    function: str
    inputs: str
    kind: str
    computed: Optional[float] = None
    recorded: Optional[float] = None

    @property
    def check(self) -> str:
        """``EQUAL`` or ``DIFFERS`` where both figures are held, else empty."""
        if self.computed is None or self.recorded is None:
            return ""
        if math.isclose(self.computed, self.recorded, rel_tol=1e-9, abs_tol=1e-9):
            return EQUAL
        return DIFFERS


@dataclass(frozen=True)
class Row:
    """One drawn row of the window: its ``section`` and the six cells ``COLUMN_HEADERS`` names."""

    section: str
    label: str
    function: str = ""
    inputs: str = ""
    computed: str = ""
    recorded: str = ""
    check: str = ""


def step_row(section: str, step: Step) -> Row:
    """``step`` as one ``Row`` of ``section``, each figure in its ``FORMATS`` kind."""
    shown = FORMATS[step.kind]
    return Row(
        section,
        step.name,
        step.function,
        step.inputs,
        shown(step.computed),
        shown(step.recorded),
        step.check,
    )


@dataclass(frozen=True)
class Calculation:
    """What the window draws for one fill: the ``title``, the ``rows`` and the pairing ``method``."""

    title: str
    rows: tuple[Row, ...]
    method: str

    @property
    def differences(self) -> int:
        """How many ``rows`` read ``DIFFERS``."""
        return sum(1 for row in self.rows if row.check == DIFFERS)


@dataclass(frozen=True)
class VenueFill:
    """One History row's venue figures, as ``normalize_trade`` wrote them."""

    exchange: str
    symbol: str
    side: str
    amount: float
    price: float
    cost: float
    fee: float
    fee_currency: str
    trade_id: str
    order_id: str
    timestamp: float

    @property
    def base(self) -> str:
        """The market's base currency, ahead of the slash."""
        return self.symbol.split("/")[0]

    @property
    def quote(self) -> str:
        """The market's quote currency, after the slash."""
        return self.symbol.split("/")[1] if "/" in self.symbol else ""

    def quote_fee(self) -> float:
        """``fee`` in the quote currency, and 0.0 for a fee in another currency."""
        if self.fee_currency == self.quote:
            return self.fee
        if self.fee_currency == self.base:
            return priced_usd(self.fee, self.price)
        return 0.0


def venue_fill(row: dict) -> VenueFill:
    """The ``VenueFill`` one History row holds."""
    return VenueFill(
        exchange=str(row.get("exchange", "") or ""),
        symbol=str(row.get("symbol", "") or ""),
        side=str(row.get("side", "") or ""),
        amount=as_finite_float(row.get("amount")) or 0.0,
        price=as_finite_float(row.get("price")) or 0.0,
        cost=as_finite_float(row.get("cost")) or 0.0,
        fee=as_finite_float(row.get("fee")) or 0.0,
        fee_currency=str(row.get("fee_currency", "") or ""),
        trade_id=str(row.get("id", "") or ""),
        order_id=str(row.get("order_id", "") or ""),
        timestamp=as_finite_float(row.get("timestamp")) or 0.0,
    )


@dataclass(frozen=True)
class TradeLine:
    """One ``trade.log`` line as the window reads it."""

    stamp: str
    epoch: float
    exchange: str
    bot_id: str
    action: str
    side: str
    symbol: str
    amount: float
    price: float
    usd: Optional[float]
    fee_usd: Optional[float]
    fee_refusal: str
    order_id: str
    ids: op.EventIds
    growth: Optional[TargetGrowth]

    def leg(self) -> op.Leg:
        """This line as one ``op.Leg`` of a pair."""
        return op.Leg(self.amount, self.price, self.fee_usd or 0.0)


def epoch_of(stamp: Any) -> Optional[float]:
    """The unix seconds of an ISO-8601 ``stamp``, or None when unreadable."""
    if not isinstance(stamp, str) or not stamp:
        return None
    text = stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def growth_of(held: Any) -> Optional[TargetGrowth]:
    """The ``TargetGrowth`` a line's ``target_growth`` holds, or None where a field is absent or not a number."""
    if not isinstance(held, dict) or set(held) != set(TARGET_GROWTH_FIELDS):
        return None
    if not isinstance(held["source"], str):
        return None
    if held["fee_pct"] is not None and as_finite_float(held["fee_pct"]) is None:
        return None
    others = [
        name for name in TARGET_GROWTH_FIELDS if name not in ("source", "fee_pct")
    ]
    if any(as_finite_float(held[name]) is None for name in others):
        return None
    return TargetGrowth(**held)


def text_ids(value: Any) -> tuple[str, ...]:
    """The text items of a list, or none for anything else."""
    if not isinstance(value, list):
        return ()
    return tuple(one for one in value if isinstance(one, str) and one)


def trade_line(entry: Any) -> Optional[TradeLine]:
    """The ``TradeLine`` one parsed ``trade.log`` entry holds, or None without a stamp, units or price."""
    if not isinstance(entry, dict) or not isinstance(entry.get("data"), dict):
        return None
    data = entry["data"]
    amount = as_finite_float(data.get("amount"))
    price = as_finite_float(data.get("price"))
    epoch = epoch_of(entry.get("timestamp"))
    if amount is None or price is None or epoch is None:
        return None
    return TradeLine(
        stamp=str(entry["timestamp"]),
        epoch=epoch,
        exchange=str(entry.get("exchange", "") or ""),
        bot_id=str(entry.get("bot_id", "") or ""),
        action=str(data.get("action", "") or ""),
        side=str(data.get("side", "") or ""),
        symbol=str(data.get("symbol", "") or ""),
        amount=amount,
        price=price,
        usd=as_finite_float(data.get("usd")),
        fee_usd=as_finite_float(data.get("fee_usd")),
        fee_refusal=str(data.get("fee_refusal", "") or ""),
        order_id=str(data.get("venue_order_id", "") or ""),
        ids=op.EventIds(
            text_ids(data.get("spent_event_ids")),
            text_ids(data.get("opened_event_ids")),
        ),
        growth=growth_of(data.get("target_growth")),
    )


def trade_log_files(trade_dir: Path) -> list[Path]:
    """``TRADE_LOG_NAME`` under ``trade_dir`` and its numbered copies, the active file first."""
    active = trade_dir / TRADE_LOG_NAME
    copies = [
        one
        for one in trade_dir.glob(f"{TRADE_LOG_NAME}.*")
        if one.suffix.lstrip(".").isdigit()
    ]
    copies.sort(key=lambda one: int(one.suffix.lstrip(".")))
    return ([active] if active.is_file() else []) + copies


def read_chunk(path: Path, offset: int) -> bytes:
    """``READ_CHUNK_BYTES`` of ``path`` from ``offset``, the file closed again before this returns."""
    try:
        with open(path, "rb") as handle:
            handle.seek(offset)
            return handle.read(READ_CHUNK_BYTES)
    except OSError:
        return b""


def take_line(raw: bytes, wanted: Callable[[str], bool], found: list) -> None:
    """Append the ``trade_line`` of ``raw`` to ``found`` where ``wanted`` accepts its text."""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text or not wanted(text):
        return
    try:
        entry = json.loads(text)
    except ValueError:
        return
    line = trade_line(entry)
    if line is not None:
        found.append(line)


def scan_steps(
    paths: list[Path], wanted: Callable[[str], bool], step_s: float
) -> Generator[None, None, list[TradeLine]]:
    """Each ``trade_line`` in ``paths`` whose text ``wanted`` accepts, yielding once ``step_s`` passes."""
    found: list[TradeLine] = []
    began = time.monotonic()
    for path in paths:
        offset = 0
        tail = b""
        while True:
            chunk = read_chunk(path, offset)
            if not chunk:
                break
            offset += len(chunk)
            pieces = (tail + chunk).split(b"\n")
            tail = pieces.pop()
            for raw in pieces:
                take_line(raw, wanted, found)
            if time.monotonic() - began >= step_s:
                yield
                began = time.monotonic()
        take_line(tail, wanted, found)
    return found


def matches_figures(line: TradeLine, fill: VenueFill) -> bool:
    """True where ``line`` or ``fill`` names no order and ``line`` holds ``fill``'s market, side, units and price within 60 s."""
    return (
        not (line.order_id and fill.order_id)
        and line.exchange in ("", fill.exchange)
        and line.symbol == fill.symbol
        and line.side == fill.side
        and math.isclose(line.amount, fill.amount, rel_tol=1e-9)
        and math.isclose(line.price, fill.price, rel_tol=1e-9)
        and abs(line.epoch - fill.timestamp) <= JOIN_TOLERANCE_SECONDS
    )


def own_line_steps(
    fill: VenueFill, paths: list[Path], step_s: float
) -> Generator[None, None, tuple[list[TradeLine], str]]:
    """The lines naming ``fill.order_id``, else the ``matches_figures`` lines, and the way they were found."""
    if fill.order_id:
        needle = '"venue_order_id":' + json.dumps(fill.order_id)
        found = yield from scan_steps(paths, lambda text: needle in text, step_s)
        named = [
            one
            for one in found
            if one.order_id == fill.order_id and one.exchange == fill.exchange
        ]
        if named:
            return named, FOUND_BY_ORDER
    needle = '"symbol":' + json.dumps(fill.symbol)
    found = yield from scan_steps(paths, lambda text: needle in text, step_s)
    matched = [one for one in found if matches_figures(one, fill)]
    return matched, (FOUND_BY_FIGURES if matched else "")


def partner_steps(
    own: list[TradeLine], ids: op.EventIds, paths: list[Path], step_s: float
) -> Generator[None, None, list[TradeLine]]:
    """The lines other than ``own`` holding any of ``ids``."""
    needles = tuple(json.dumps(one) for one in (*ids.spent, *ids.opened))
    if not needles:
        return []
    found = yield from scan_steps(
        paths, lambda text: any(needle in text for needle in needles), step_s
    )
    return [one for one in found if one not in own]


def bot_for(bot_manager: Any, own: list[TradeLine], row: dict) -> Any:
    """The running bot that wrote ``own``, else the one ``resolve_bot_id_for_row`` names, else None."""
    bots = getattr(bot_manager, "_bots", None)
    if not isinstance(bots, dict):
        return None
    for line in own:
        if line.bot_id in bots:
            return bots[line.bot_id]
    return bots.get(resolve_bot_id_for_row(bot_manager, row))


def distance_of(bot: Any) -> Optional[DistanceSettings]:
    """``bot.opposing_distance_settings``, or None for a bot without one or a setting that reads no number."""
    read = getattr(bot, "opposing_distance_settings", None)
    if not callable(read):
        return None
    try:
        held = read()
    except DistanceSettingUnreadable:
        return None
    return held if isinstance(held, DistanceSettings) else None


def second_of(timestamp: float) -> datetime:
    """``timestamp`` as a UTC moment cut to its second, the stamp ``op.venue_orders`` merges on."""
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)


def market_orders(history_rows: list, fill: VenueFill) -> list[op.Order]:
    """``op.venue_orders`` of every History row on ``fill``'s exchange and market."""
    fills = []
    for row in history_rows or []:
        if not isinstance(row, dict):
            continue
        other = venue_fill(row)
        if other.timestamp <= 0.0 or other.amount <= 0.0:
            continue
        if other.exchange != fill.exchange or other.symbol != fill.symbol:
            continue
        fills.append(
            op.Fill(
                asset=other.base,
                when=second_of(other.timestamp),
                side=other.side.lower(),
                price=other.price,
                qty=other.amount,
                fee=other.quote_fee(),
            )
        )
    return op.venue_orders(fills)


def fill_order(fill: VenueFill, orders: list[op.Order]) -> op.Order:
    """The order of ``orders`` ``fill`` belongs to, or the fill alone as one order."""
    when = second_of(fill.timestamp)
    for order in orders:
        if order.when == when and order.side == fill.side.lower():
            return order
    return op.Order(
        fill.base, when, fill.side.lower(), fill.price, fill.amount, fill.quote_fee()
    )


def fill_rows(fill: VenueFill) -> list[Row]:
    """The venue's own figures for ``fill``."""
    charged = venue_fee_pct(
        SettledFillFee(fill.amount, fill.price, fill.quote_fee(), fill.quote, True),
        fill.price,
        fill.quote,
    )
    cost = Step(
        "Cost",
        "priced_usd",
        f"{units_text(fill.amount)} at {price_text(fill.price)}",
        "usd",
        priced_usd(fill.amount, fill.price),
        fill.cost,
    )
    fee = Step(
        "Fee the venue charged",
        "venue_fee_pct",
        f"{fill.fee:,.8f} {fill.fee_currency} on {units_text(fill.amount)}",
        "pct",
        charged,
    )
    return [
        Row(
            SECTION_FILL, "Exchange and market", inputs=f"{fill.exchange} {fill.symbol}"
        ),
        Row(SECTION_FILL, "Side", inputs=fill.side),
        Row(SECTION_FILL, "Units", inputs=units_text(fill.amount)),
        Row(SECTION_FILL, "Price", inputs=price_text(fill.price)),
        step_row(SECTION_FILL, cost),
        step_row(SECTION_FILL, fee),
        Row(SECTION_FILL, "Trade id", inputs=fill.trade_id),
        Row(SECTION_FILL, "Venue order id", inputs=fill.order_id or NO_ORDER_ON_ROW),
    ]


def line_text(line: TradeLine) -> str:
    """One line's figures as the record section names them."""
    fee = usd_text(line.fee_usd) if line.fee_usd is not None else line.fee_refusal
    return (
        f"{line.stamp}, {line.action} {line.side} {units_text(line.amount)} at "
        f"{price_text(line.price)}, dollars {usd_text(line.usd)}, fee {fee}, "
        f"order {line.order_id or 'none named'}, bot {line.bot_id}"
    )


def ids_text(ids: tuple[str, ...]) -> str:
    """``ids`` joined, or "none"."""
    return ", ".join(ids) if ids else "none"


def record_rows(own: list[TradeLine], how: str, fill: VenueFill) -> list[Row]:
    """How the platform's lines for ``fill`` were found, and each one's figures."""
    if not own:
        missing = NO_LINE.format(order=fill.order_id or "(none named)")
        return [
            Row(
                SECTION_RECORD, "Lines found", inputs=f"{missing}, {NO_LINE_BY_FIGURES}"
            )
        ]
    rows = [Row(SECTION_RECORD, "Lines found", inputs=f"{len(own)}, {how}")]
    for place, line in enumerate(own, start=1):
        rows.append(Row(SECTION_RECORD, f"Line {place}", inputs=line_text(line)))
        rows.append(
            Row(SECTION_RECORD, "Tranches spent", inputs=ids_text(line.ids.spent))
        )
        rows.append(
            Row(SECTION_RECORD, "Tranches opened", inputs=ids_text(line.ids.opened))
        )
    return rows


def fold_steps(growth: TargetGrowth) -> list[Step]:
    """Each growth step of one fold line, through the functions ``_apply_fold_target_growth`` calls."""
    bought = (
        f"units bought {units_text(growth.units_bought)}, units at scrum "
        f"{units_text(growth.units_at_scrum)}, fill {price_text(growth.fill_price)}, "
        f"fee {pct_text(growth.fee_pct)}"
    )
    gain = None
    if growth.source == CHAIN_FOLD_SOURCE:
        gain = fold_gain_usd(
            priced_usd(growth.units_bought, growth.fill_price),
            growth.units_at_scrum,
            growth.fill_price,
            growth.fee_pct,
        )
    else:
        bought = OTHER_SOURCE_GAIN.format(source=growth.source)
    applied, after = target_growth_applied(
        growth.surplus_usd, growth.standing_usd, growth.cap_room_usd
    )
    held = (
        f"surplus {usd_text(growth.surplus_usd)}, pool {usd_text(growth.standing_usd)}, "
        f"cap room {usd_text(growth.cap_room_usd)}"
    )
    return [
        Step(
            "Units bought", "", "the growth record", "units", None, growth.units_bought
        ),
        Step(
            "Units at scrum",
            "",
            "the growth record",
            "units",
            None,
            growth.units_at_scrum,
        ),
        Step(
            "Fee the growth step priced",
            "",
            "the growth record",
            "pct",
            None,
            growth.fee_pct,
        ),
        Step("Gain", "fold_gain_usd", bought, "usd", gain, growth.gain),
        Step(
            "Surplus",
            "growth_surplus_usd",
            f"gain {usd_text(growth.gain)} at quote rate {growth.quote_to_usd:g}",
            "usd",
            growth_surplus_usd(growth.gain, growth.quote_to_usd),
            growth.surplus_usd,
        ),
        Step(
            "Cap room",
            "fold_cap_remaining_usd",
            f"cycle cap {usd_text(growth.cycle_cap_usd)}, used {usd_text(growth.consumed_usd)}",
            "usd",
            fold_cap_remaining_usd(growth.cycle_cap_usd, growth.consumed_usd),
            growth.cap_room_usd,
        ),
        Step(
            "Growth applied",
            "target_growth_applied",
            held,
            "usd",
            applied,
            growth.applied_usd,
        ),
        Step(
            "Pool after",
            "target_growth_applied",
            held,
            "usd",
            after,
            growth.standing_after_usd,
        ),
        Step(
            "New target",
            "",
            "the target before the growth is not in the record",
            "usd",
            None,
            growth.target_usd,
        ),
    ]


def scrum_steps(line: TradeLine, distance: Optional[DistanceSettings]) -> list[Step]:
    """Each step of one Scrum line, through the functions ``_book_scrum_fill`` and ``_sale_surplus_usd`` call."""
    gross = priced_usd(line.amount, line.price)
    fee = line.fee_usd or 0.0
    proceeds = sale_proceeds_usd(gross, fee)
    steps = [
        Step(
            "Proceeds after the fee",
            "sale_proceeds_usd",
            f"gross {usd_text(gross)} less fee {usd_text(fee)}",
            "usd",
            proceeds,
        )
    ]
    if line.usd is not None:
        routed = proceeds - line.usd
        steps.append(
            Step(
                "Wire share",
                "routed_share_pct",
                f"proceeds {usd_text(proceeds)}, routed {usd_text(routed)}: the proceeds less the line's dollars",
                "pct",
                routed_share_pct(proceeds, routed),
            )
        )
        steps.append(
            Step("Queued for the fold", "", "the line's dollars", "usd", None, line.usd)
        )
    if distance is None:
        steps.append(Step("Surplus", "restored_sale_surplus_usd", NO_BOT, "usd"))
        return steps
    motd = distance.distance_at_band(None)
    rezero = fold_rebuy_price(line.price, motd)
    steps.extend(
        [
            Step(
                "Price that re-zeroes its units",
                "fold_rebuy_price",
                f"sale {price_text(line.price)} less MOTD {pct_text(motd)}, {MOTD_OF_BOT}",
                "price",
                rezero,
            ),
            Step(
                "Dollars that re-zero its units",
                "restore_cost_usd",
                f"{units_text(line.amount)} at {price_text(rezero)} with fee {pct_text(distance.fee_pct)}",
                "usd",
                restore_cost_usd(line.amount, rezero, distance.fee_pct),
            ),
            Step(
                "Surplus",
                "restored_sale_surplus_usd",
                f"proceeds {usd_text(proceeds)} past the dollars that re-zero its units",
                "usd",
                restored_sale_surplus_usd(proceeds, line.amount, line.price, distance),
            ),
        ]
    )
    return steps


def line_steps(
    line: TradeLine, quote: str, distance: Optional[DistanceSettings]
) -> list[Step]:
    """The steps every line takes, then the fold or the Scrum steps its record holds."""
    charged = None
    if line.fee_usd is not None:
        charged = venue_fee_pct(
            SettledFillFee(line.amount, line.price, line.fee_usd, quote, True),
            line.price,
            quote,
        )
    fee_inputs = (
        f"fee {usd_text(line.fee_usd)} on {units_text(line.amount)}"
        if line.fee_usd is not None
        else line.fee_refusal
    )
    steps = [
        Step(
            "Units at the price",
            "priced_usd",
            f"{units_text(line.amount)} at {price_text(line.price)}",
            "usd",
            priced_usd(line.amount, line.price),
        ),
        Step("Fee the venue charged", "venue_fee_pct", fee_inputs, "pct", charged),
    ]
    if line.growth is not None:
        return steps + fold_steps(line.growth)
    if line.action == "SCRUM":
        return steps + scrum_steps(line, distance)
    return steps


def arithmetic_rows(
    own: list[TradeLine], quote: str, distance: Optional[DistanceSettings]
) -> list[Row]:
    """Every ``line_steps`` of ``own``, one section per line."""
    rows: list[Row] = []
    for place, line in enumerate(own, start=1):
        section = SECTION_LINE.format(
            number=place, action=line.action, stamp=line.stamp
        )
        rows.extend(
            step_row(section, step) for step in line_steps(line, quote, distance)
        )
    return rows


def order_text(order: op.Order) -> str:
    """One venue order as the pair section names it."""
    return (
        f"{order.side} {units_text(order.qty)} at {price_text(order.price)}, "
        f"{order.when.isoformat()}"
    )


def figure_rows(figures: op.PairFigures) -> list[Row]:
    """The pair's units, accumulation and profit, through ``op.pair_figures``."""
    profit = Step(
        "Profit",
        "sale_surplus_usd",
        f"proceeds {usd_text(figures.proceeds_usd)} past {units_text(figures.units_sold)} "
        f"bought back at {price_text(figures.buy_price)} with fee {pct_text(figures.buy_fee_pct)}",
        "usd",
        figures.profit_usd,
    )
    return [
        Row(SECTION_PAIR, "Units sold", inputs=units_text(figures.units_sold)),
        Row(SECTION_PAIR, "Units bought", inputs=units_text(figures.units_bought)),
        Row(
            SECTION_PAIR,
            "Accumulation in tokens",
            inputs=f"{units_text(figures.accumulated_units)}: units bought less units sold",
        ),
        Row(
            SECTION_PAIR,
            "Sale proceeds",
            "sale_proceeds_usd",
            usd_text(figures.proceeds_usd),
        ),
        step_row(SECTION_PAIR, profit),
    ]


def event_pair_rows(
    own: list[TradeLine], partners: tuple, ids: op.EventIds, quote: str
) -> list[Row]:
    """The opposing lines the event ids found, and the pair's figures over them and ``own``."""
    rows = [
        Row(SECTION_PAIR, "Opposing line", inputs=line_text(line)) for line in partners
    ]
    lines = [*own, *partners]
    sells = [line.leg() for line in lines if line.side == "SELL"]
    buys = [line.leg() for line in lines if line.side == "BUY"]
    own_opened = set(ids.opened)
    own_spent = set(ids.spent)
    if any(set(line.ids.spent) - own_opened for line in partners if own_opened):
        rows.append(Row(SECTION_PAIR, "Note", inputs=OTHER_OPENERS))
    if any(set(line.ids.opened) - own_spent for line in partners if own_spent):
        rows.append(Row(SECTION_PAIR, "Note", inputs=OTHER_SPENDERS))
    return rows + figure_rows(op.pair_figures(sells, buys, quote))


def time_pair_rows(
    pair: op.CyclePair, motd: float, source: str, quote: str
) -> list[Row]:
    """The order-time pair's two orders, its level, and its figures."""
    sells = [op.Leg(pair.scrum.qty, pair.scrum.price, pair.scrum.fee)]
    buys = [op.Leg(pair.fold.qty, pair.fold.price, pair.fold.fee)]
    return [
        Row(SECTION_PAIR, "MOTD", inputs=f"{pct_text(motd)}, {source}"),
        Row(SECTION_PAIR, "Direction", inputs=pair.direction),
        Row(SECTION_PAIR, "Scrum order", inputs=order_text(pair.scrum)),
        Row(SECTION_PAIR, "Fold order", inputs=order_text(pair.fold)),
        Row(SECTION_PAIR, "Level", "motd_level", price_text(pair.level)),
        *figure_rows(op.pair_figures(sells, buys, quote)),
    ]


def pair_rows(
    pairing: op.FillPairing,
    own: list[TradeLine],
    ids: op.EventIds,
    motd: tuple[float, str],
    quote: str,
) -> list[Row]:
    """The pair section: the method ``op.pair_fill`` names, then what it found."""
    rows = [Row(SECTION_PAIR, "Paired by", inputs=pairing.method)]
    if pairing.method == op.PAIRED_BY_EVENT_IDS:
        return rows + event_pair_rows(own, pairing.partners, ids, quote)
    if pairing.pair is not None:
        return rows + time_pair_rows(pairing.pair, motd[0], motd[1], quote)
    opens, closes = pairing.causes
    return rows + [
        Row(SECTION_PAIR, "MOTD", inputs=f"{pct_text(motd[0])}, {motd[1]}"),
        Row(SECTION_PAIR, "As the earlier order", inputs=opens),
        Row(SECTION_PAIR, "As the later order", inputs=closes),
    ]


def title_of(fill: VenueFill) -> str:
    """The window's first line for ``fill``."""
    when = datetime.fromtimestamp(fill.timestamp, tz=timezone.utc).isoformat()
    return (
        f"{fill.side} {units_text(fill.amount)} {fill.symbol} at "
        f"{price_text(fill.price)} on {fill.exchange}, {when}"
    )


def calculation_steps(
    row: dict,
    history_rows: list,
    bot_manager: Any,
    trade_dir: Path,
    step_s: float,
) -> Generator[None, None, Calculation]:
    """The ``Calculation`` of one History ``row``, reading ``trade_dir`` and yielding once ``step_s`` passes."""
    fill = venue_fill(row)
    paths = trade_log_files(trade_dir)
    own, how = yield from own_line_steps(fill, paths, step_s)
    ids = op.EventIds(
        tuple(dict.fromkeys(one for line in own for one in line.ids.spent)),
        tuple(dict.fromkeys(one for line in own for one in line.ids.opened)),
    )
    partners = yield from partner_steps(own, ids, paths, step_s)
    bot = bot_for(bot_manager, own, row)
    distance = distance_of(bot)
    motd = (
        (distance.distance_at_band(None), MOTD_OF_BOT)
        if distance is not None
        else (op.DEFAULT_MOTD_PCT, MOTD_DEFAULT)
    )
    orders = market_orders(history_rows, fill)
    pairing = op.pair_fill(
        ids,
        [(line, line.ids) for line in partners],
        fill_order(fill, orders),
        orders,
        motd[0],
    )
    rows = [
        *fill_rows(fill),
        *record_rows(own, how, fill),
        *arithmetic_rows(own, fill.quote, distance),
        *pair_rows(pairing, own, ids, motd, fill.quote),
    ]
    return Calculation(title_of(fill), tuple(rows), pairing.method)
