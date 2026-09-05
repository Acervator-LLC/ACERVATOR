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
SIM = REPO_ROOT / "src/simulator/fleet/sim_exchange.py"
CONSUMER_DIRS = ("src/trading", "src/gui")

DATACLASSES = ("Ticker", "Balance", "Order", "Trade", "OrderBook")

# Fields live populates and the Simulator does not. Empty, and it stays
# empty: the sim is bit identical to live but for its data source.
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


def _reads_of(field: str, paths) -> list[str]:
    """Every ``obj.field`` read in ``paths``, skipping ``self`` and ``cls``."""
    found: list[str] = []
    for py in paths:
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == field
                and isinstance(node.ctx, ast.Load)
            ):
                text = ast.unparse(node)
                if text.startswith(("self.", "cls.")):
                    continue
                found.append(f"{py.name}:{node.lineno} reads {text}")
    return found


def _consumer_files():
    """Every file under ``CONSUMER_DIRS`` other than ``LIVE`` and ``SIM``."""
    skip = {LIVE.resolve(), SIM.resolve()}
    for d in CONSUMER_DIRS:
        for py in (REPO_ROOT / d).rglob("*.py"):
            if py.resolve() not in skip:
                yield py


def test_the_reader_scan_sees_a_read_and_ignores_a_write(tmp_path):
    """POSITIVE CONTROL for ``_reads_of``. ``KNOWN_UNPOPULATED`` is empty, so the
    test below scans nothing and its green says only that the dict is empty."""
    module = tmp_path / "consumer.py"
    module.write_text(
        "def go(order):\n"
        "    order.fee = 1.0\n"
        "    self.fee = 2.0\n"
        "    return order.fee\n",
        encoding="utf-8",
    )
    hits = _reads_of("fee", [module])
    assert hits == ["consumer.py:4 reads order.fee"], hits
    assert _reads_of("average", [module]) == []


def test_the_exempt_fields_are_still_unread():
    """THE CONDITION ON THE EXEMPTION.

    Those fields are only safe to leave empty while nothing reads them.
    This is what stops "accepted difference" from decaying into "silent
    divergence" the first time someone writes `order.fee`.
    """
    consumers = list(_consumer_files())
    assert consumers, "the consumer scan found no file to read"
    offenders = []
    for cls, fields in KNOWN_UNPOPULATED.items():
        for field in fields:
            offenders += [
                f"{hit} ({cls}.{field})" for hit in _reads_of(field, consumers)
            ]
    assert not offenders, (
        "a field exempted as unread is now being read; the Simulator "
        "must populate it or the exemption must be re-justified:\n  "
        + "\n  ".join(sorted(set(offenders))[:10])
    )


def test_the_simulator_binds_the_live_dataclasses():
    """Not lookalikes: every name in ``DATACLASSES`` that ``sim_exchange`` binds is
    the object ``src.exchange.base`` declares."""
    from src.simulator.fleet import sim_exchange

    bound = {cls: getattr(sim_exchange, cls, None) for cls in DATACLASSES}
    assert None not in bound.values(), bound
    for cls, obj in bound.items():
        assert obj is getattr(B, cls), (
            f"sim_exchange.{cls} is {obj!r}, not the {cls} live returns; every "
            f"field comparison above compares two different classes"
        )


def test_the_simulator_subclasses_the_live_interface():
    """``FleetSimExchange`` is a real ``ExchangeInterface``, so ABC machinery still
    covers the method set the field comparison assumes."""
    from src.simulator.fleet.sim_exchange import FleetSimExchange

    assert issubclass(FleetSimExchange, B.ExchangeInterface)


def test_the_connector_binds_the_live_dataclasses():
    """Whatever ``ccxt_connector`` binds at module level is the live object; the
    names it imports inside a method are absent here and skipped."""
    from src.exchange import ccxt_connector

    checked = [
        cls for cls in DATACLASSES if getattr(ccxt_connector, cls, None) is not None
    ]
    assert len(checked) >= 4, checked
    for cls in checked:
        assert getattr(ccxt_connector, cls) is getattr(B, cls), cls


def test_the_parser_sees_attribute_assignment():
    """NEGATIVE CONTROL for this file's own method. `order.average` is
    set post-constructor in the sim; a constructor-only diff reports it
    as missing. If this stops holding, the parser has regressed and the
    tests above would pass vacuously."""
    ctor, attrs = _populated(SIM)
    assert "average" in attrs
    assert "average" not in ctor.get("Order", set())
    assert "average" in _fields_set(SIM, "Order")
