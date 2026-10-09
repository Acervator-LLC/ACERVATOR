"""The recorded copy of the order rules a venue publishes for each of its markets.

``record_venue`` writes what ``CCXTConnector.get_markets`` already read, and
``recorded_rules`` answers a ``MarketRules`` from that recording with no venue
call and no connector. The Simulator's back test and the Paper Trader read it
through ``recorded_rules`` to size an order to the venue that would execute it.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Iterable, Optional

from .base import MarketRules

logger = logging.getLogger(__name__)

STORE_NAME = "market_rules.json"

#: The four rules ``MarketRules`` carries, each recorded under its own name.
# OVERTAKEN, the comment above reading "The four rules ``MarketRules`` carries":
# ``expiry_ms`` is a fifth, so the Simulator and the Paper Trader read an expiry
# the venue published. A row recorded before it holds no such key and answers
# None, which changes nothing for a market already recorded.
# OVERTAKEN, the two comments above: ``quote_increment`` and ``contract_size``
# are recorded beside them, the step a cash amount moves by and the base units
# one contract stands for.
RULE_FIELDS = (
    "min_amount",
    "min_cost",
    "amount_increment",
    "price_increment",
    "quote_increment",
    "contract_size",
    "expiry_ms",
)

# OVERTAKEN, the comment above reading "``expiry_ms`` is a fifth": ``RULE_FIELDS``
# holds the five NUMERIC rules, and ``order_types`` is a string.
# OVERTAKEN, the sentence above reading "the five NUMERIC rules": ``RULE_FIELDS``
# holds seven, and ``session`` is a second string.
#: The text rules ``MarketRules`` carries, each recorded under its own name. A row
#: recorded before one holds no such key and answers None.
TEXT_RULE_FIELDS = ("order_types", "session")

#: The asset class a row records beside its rules, so one venue's recording can
#: be read one class at a time. A row recorded before it holds no such key and
#: ``recorded_classes`` answers an empty class for it.
CLASS_FIELD = "asset_class"


def store_path() -> Path:
    """``STORE_NAME`` under the runtime home, resolved on every call and never
    held at import."""
    return Path.home() / ".acervator" / STORE_NAME


def rule_value(value: Any) -> Optional[float]:
    """``value`` as a float when it is a finite int or float, else None."""
    if type(value) not in (int, float):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def rule_text(value: Any) -> Optional[str]:
    """``value`` as a string when it is a non-empty string, else None."""
    if type(value) is not str:
        return None
    return value or None


# OVERTAKEN in rules_row's docstring below: "``rules``'s ``RULE_FIELDS`` as one
# row, an unpublished rule None."
# ``TEXT_RULE_FIELDS`` is written into the same row through ``rule_text``.
def rules_row(rules: Any) -> dict[str, Any]:
    """``rules``'s ``RULE_FIELDS`` as one row, an unpublished rule None."""
    row: dict[str, Any] = {
        name: rule_value(getattr(rules, name, None)) for name in RULE_FIELDS
    }
    for name in TEXT_RULE_FIELDS:
        row[name] = rule_text(getattr(rules, name, None))
    return row


def load_document(path: Optional[Path] = None) -> dict:
    """The whole recording as a mapping of venue to market rows, empty when the
    file is absent or holds no mapping."""
    target = path or store_path()
    try:
        body = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return body if isinstance(body, dict) else {}


def record_venue(
    venue: str,
    markets: Iterable[Any],
    path: Optional[Path] = None,
    classes: Optional[dict] = None,
) -> int:
    """Write every market of ``markets`` under ``venue``, keeping the other
    venues' rows, and answer how many markets were written.

    ``markets`` are ``AssetInfo`` records read for ``symbol`` and ``rules``,
    and ``classes`` maps a symbol to the ``CLASS_FIELD`` it records under. An
    empty ``markets`` writes nothing and answers 0, so ``venue``'s own
    recorded rows stand.
    """
    name = str(venue or "")
    if not name:
        return 0
    target = path or store_path()
    held_classes = dict(classes or {})
    rows: dict[str, dict] = {}
    for market in markets:
        symbol = str(getattr(market, "symbol", "") or "")
        if not symbol:
            continue
        rows[symbol] = rules_row(getattr(market, "rules", None))
        asset_class = str(held_classes.get(symbol, "") or "")
        if asset_class:
            rows[symbol][CLASS_FIELD] = asset_class
    document = load_document(target)
    if not rows:
        standing = document.get(name)
        logger.warning(
            "read no market for %s, so its %d recorded market rule rows stand",
            name,
            len(standing) if isinstance(standing, dict) else 0,
        )
        return 0
    document[name] = rows
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_name(target.name + ".writing")
    with open(scratch, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(scratch, target)
    logger.info("recorded %d market rule rows for %s", len(rows), name)
    return len(rows)


def recorded_rules(venue: str, symbol: str, path: Optional[Path] = None) -> MarketRules:
    """The ``MarketRules`` recorded for ``symbol`` on ``venue``.

    ``read`` is False when the recording holds no row for the pair, the same
    unknown a venue that answered no market record carries.

    Every name of ``RULE_FIELDS`` and ``TEXT_RULE_FIELDS`` is read back here, so
    a rule ``rules_row`` writes never goes unread.
    """
    row = (load_document(path).get(str(venue or "")) or {}).get(str(symbol or ""))
    if not isinstance(row, dict):
        return MarketRules(read=False)
    return MarketRules(
        min_amount=rule_value(row.get("min_amount")),
        min_cost=rule_value(row.get("min_cost")),
        amount_increment=rule_value(row.get("amount_increment")),
        price_increment=rule_value(row.get("price_increment")),
        quote_increment=rule_value(row.get("quote_increment")),
        contract_size=rule_value(row.get("contract_size")),
        expiry_ms=rule_value(row.get("expiry_ms")),
        order_types=rule_text(row.get("order_types")),
        session=rule_text(row.get("session")),
        read=True,
    )


def recorded_classes(venue: str, path: Optional[Path] = None) -> dict[str, str]:
    """Every symbol recorded for ``venue`` mapped to its ``CLASS_FIELD``.

    A row recorded before the field answers an empty class, so a recording
    written by an earlier build reads as one class nobody named.
    """
    rows = load_document(path).get(str(venue or "")) or {}
    if not isinstance(rows, dict):
        return {}
    return {
        str(symbol): str((row or {}).get(CLASS_FIELD, "") or "")
        for symbol, row in rows.items()
        if isinstance(row, dict)
    }


__all__ = [
    "CLASS_FIELD",
    "RULE_FIELDS",
    "STORE_NAME",
    "TEXT_RULE_FIELDS",
    "load_document",
    "record_venue",
    "recorded_classes",
    "recorded_rules",
    "rule_text",
    "rule_value",
    "rules_row",
    "store_path",
]
