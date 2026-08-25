"""Sim and Live must fill the same fields of the same dataclasses.

Operator directive 2026-08-09: the Simulator must handle its different
data source "in an identical, verifiable manner so that we have a valid
test environment on which to build."

`FleetSimExchange` subclasses `ExchangeInterface`, so Python's ABC
machinery already guarantees every method EXISTS. It guarantees nothing
about what those methods put inside the objects they return. Both sides
construct the real `Ticker` / `Balance` / `Order` / `Trade` /
`OrderBook` dataclasses from `src/exchange/base.py` -- which is good,
they are not lookalikes -- but a field left at its default on one side
and populated on the other is invisible to the type system and to the
ABC.

That is the same shape as the defect found on the OHLCV seam: the sim
satisfied the declared interface while behaving differently from live
in a way nothing checked.

HOW THIS CHECKS. Parses both modules and collects, per dataclass, the
fields each side populates -- constructor keywords AND post-construction
attribute assignment. The second half matters: `sim_exchange.py:580`
sets `order.average` after the constructor, so a constructor-only diff
reports a mismatch that is not real. This test was written after making
exactly that error.

MEASURED at the time of writing: Ticker, Balance, Trade and OrderBook
have identical populated field sets. `Order` differs on three fields.
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from src.exchange import base as B  # noqa: E402

LIVE = REPO_ROOT / "src/exchange/ccxt_connector.py"
SIM = REPO_ROOT / "src/gui/simulator_tab/fleet/sim_exchange.py"
CONSUMER_DIRS = ("src/trading", "src/gui")

DATACLASSES = ("Ticker", "Balance", "Order", "Trade", "OrderBook")

# Fields live populates and the Simulator does not.
#
# EMPTY, AND IT STAYS EMPTY. Operator directive 2026-08-09: "If the code
# is not bit identical to live and only varies by calling the Stone
# Tablets and YTD as its source of data, you have failed."
#
# An earlier version of this file exempted Order.fee / fee_currency /
# raw on the grounds that nothing read them. That is not a standard —
# it dates the guarantee to the last time someone grepped. The sim
# already computed the fee and stamped it on the Trade; it now stamps
# the Order too.
KNOWN_UNPOPULATED: dict = {}


def _populated(path: Path) -> tuple[dict, set]:
    """(fields set via constructor kwargs, fields set via attribute)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    ctor: dict = defaultdict(set)
    attrs: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", "")
            if name in DATACLASSES:
                for kw in node.keywords:
                    if kw.arg:
                        ctor[name].add(kw.arg)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Attribute):
                    attrs.add(tgt.attr)
    return ctor, attrs


def _fields_set(path: Path, cls: str) -> set:
    ctor, attrs = _populated(path)
    declared = {f.name for f in dataclasses.fields(getattr(B, cls))}
    return ctor.get(cls, set()) | (attrs & declared)


@pytest.mark.parametrize("cls", DATACLASSES)
def test_sim_populates_every_field_live_does(cls):
    live = _fields_set(LIVE, cls)
    sim = _fields_set(SIM, cls)
    if not live:
        pytest.skip(f"live does not construct {cls} directly")
    missing = live - sim - KNOWN_UNPOPULATED.get(cls, set())
    assert not missing, (
        f"{cls}: live fills {sorted(missing)} and the Simulator does not. "
        f"A bot reading those gets real values live and defaults in sim, "
        f"so a replay cannot reproduce the live decision. Either populate "
        f"them in FleetSimExchange or add them to KNOWN_UNPOPULATED with "
        f"a reason and no consumer."
    )


def test_the_exempt_fields_are_still_unread():
    """THE CONDITION ON THE EXEMPTION.

    Those fields are only safe to leave empty while nothing reads them.
    This is what stops "accepted difference" from decaying into "silent
    divergence" the first time someone writes `order.fee`.
    """
    offenders = []
    for cls, fields in KNOWN_UNPOPULATED.items():
        for field in fields:
            for d in CONSUMER_DIRS:
                for py in (REPO_ROOT / d).rglob("*.py"):
                    if py.resolve() in (LIVE.resolve(), SIM.resolve()):
                        continue
                    try:
                        tree = ast.parse(py.read_text(encoding="utf-8"))
                    except (SyntaxError, OSError):
                        continue
                    for node in ast.walk(tree):
                        # An attribute READ, not a write and not a string.
                        if (
                            isinstance(node, ast.Attribute)
                            and node.attr == field
                            and isinstance(node.ctx, ast.Load)
                        ):
                            src = ast.unparse(node)
                            if src.startswith(("self.", "cls.")):
                                continue
                            offenders.append(
                                f"{py.relative_to(REPO_ROOT).as_posix()}:"
                                f"{node.lineno} reads {src} ({cls}.{field})"
                            )
    assert not offenders, (
        "a field exempted as unread is now being read; the Simulator "
        "must populate it or the exemption must be re-justified:\n  "
        + "\n  ".join(sorted(set(offenders))[:10])
    )


def test_both_sides_use_the_same_dataclasses():
    """Not lookalikes. If the sim ever defines its own Ticker/Order,
    every field comparison above becomes meaningless."""
    src = SIM.read_text(encoding="utf-8")
    assert "from ....exchange.base import (" in src
    for cls in DATACLASSES:
        assert f"class {cls}" not in src, (
            f"the Simulator defines its own {cls}; it must use the one " f"live returns"
        )


def test_the_parser_sees_attribute_assignment():
    """NEGATIVE CONTROL for this file's own method. `order.average` is
    set post-constructor in the sim; a constructor-only diff reports it
    as missing. If this stops holding, the parser has regressed and the
    tests above would pass vacuously."""
    ctor, attrs = _populated(SIM)
    assert "average" in attrs
    assert "average" not in ctor.get("Order", set())
    assert "average" in _fields_set(SIM, "Order")
