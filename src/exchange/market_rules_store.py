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
RULE_FIELDS = ("min_amount", "min_cost", "amount_increment", "price_increment")


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


def rules_row(rules: Any) -> dict[str, Optional[float]]:
    """``rules``'s ``RULE_FIELDS`` as one row, an unpublished rule None."""
    return {name: rule_value(getattr(rules, name, None)) for name in RULE_FIELDS}


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
    venue: str, markets: Iterable[Any], path: Optional[Path] = None
) -> int:
    """Write every market of ``markets`` under ``venue``, keeping the other
    venues' rows, and answer how many markets were written.

    ``markets`` are ``AssetInfo`` records, each read for its ``symbol`` and its
    ``rules``; a market naming no symbol is skipped.
    """
    name = str(venue or "")
    if not name:
        return 0
    target = path or store_path()
    rows: dict[str, dict] = {}
    for market in markets:
        symbol = str(getattr(market, "symbol", "") or "")
        if not symbol:
            continue
        rows[symbol] = rules_row(getattr(market, "rules", None))
    document = load_document(target)
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
    """
    row = (load_document(path).get(str(venue or "")) or {}).get(str(symbol or ""))
    if not isinstance(row, dict):
        return MarketRules(read=False)
    return MarketRules(
        min_amount=rule_value(row.get("min_amount")),
        min_cost=rule_value(row.get("min_cost")),
        amount_increment=rule_value(row.get("amount_increment")),
        price_increment=rule_value(row.get("price_increment")),
        read=True,
    )


__all__ = [
    "RULE_FIELDS",
    "STORE_NAME",
    "load_document",
    "record_venue",
    "recorded_rules",
    "rule_value",
    "rules_row",
    "store_path",
]
