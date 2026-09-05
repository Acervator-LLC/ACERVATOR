"""U1 -- the settled-fill fallback line must name the caller that hit it.

THE DEFECT
``ScrummingBot._settled_fill`` hardcoded ``"MANUAL FIRE:"`` into the
message it emits when the exchange never reports a settled fill. That
string was accurate only because the manual rebalance was its one
caller. The operator reads that prefix in bot.log to tell WHICH path
degraded to an estimate, so it becomes a lie about the path the moment
a second caller exists. Labelled before that caller is written, not
after.

WHERE THE VERDICT IS READ
Every assertion below reads the string that reached the EVENT BUS --
the surface the operator actually sees -- and never an intermediate
variable. The fallback is forced two ways in every case, because those
are the two ways the live path degrades: a re-read that keeps answering
with nothing numeric, and a re-read that raises.

ZERO BEHAVIOUR CHANGE
With the argument ABSENT the message is byte-identical to what the
module emitted before U1. ``LIVE_FALLBACK_MESSAGE`` below is that
message, captured by driving the pre-U1 module.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest

from src.trading.scrumming_bot import ScrummingBot

# Distinguishes "no label argument" from "label=None": two call shapes,
# one default.
_ABSENT = object()

# Captured with requested=2.5 and quoted=0.00004321; every byte is a
# string the operator reads in bot.log.
LIVE_FALLBACK_MESSAGE = (
    "MANUAL FIRE: exchange reported no settled fill for order oid-1; "
    "booking the ESTIMATE (2.500000 @ $0.00004321) instead of a "
    "confirmed fill. Position accounting may drift from the exchange "
    "until the next reconcile."
)

_REQUESTED = 2.5
_QUOTED = 0.00004321


class _Order:
    """The real Coinbase create-order shape: no numeric fields at all."""

    def __init__(self, oid: str = "oid-1") -> None:
        self.id = oid


class _SilentExchange:
    """Answers the re-read with nothing numeric, so the polls exhaust."""

    def __init__(self) -> None:
        self.calls = 0

    async def get_order(self, *_args: Any) -> _Order:
        self.calls += 1
        return _Order()


class _RaisingExchange:
    """Raises on the re-read, so the poll loop breaks out early."""

    def __init__(self) -> None:
        self.calls = 0

    async def get_order(self, *_args: Any) -> _Order:
        self.calls += 1
        message = "exchange unreachable"
        raise RuntimeError(message)


class _RecordingBus:
    """Stands in for the event bus and keeps every message emitted."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, *_args: Any, **kwargs: Any) -> None:
        self.messages.append(str(kwargs.get("message", "")))


EXCHANGES = (_SilentExchange, _RaisingExchange)


def _bot(exchange: Any) -> Any:
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "BTC-USD-1"
    bot.exchange = exchange
    bot._bus = _RecordingBus()
    return bot


async def _fallback_message(exchange: Any, label: Any = _ABSENT) -> str:
    """Force the fallback and return the ONE message the bus received.

    Fails loudly if the fallback did not fire or if the count of emitted
    messages is not one: a helper that quietly returns the empty string
    would make every assertion below pass without measuring anything.
    """
    bot = _bot(exchange)
    args = (_Order(), "BTC/USD", _REQUESTED, _QUOTED)
    if label is _ABSENT:
        _, _, is_real = await bot._settled_fill(*args)
    else:
        _, _, is_real = await bot._settled_fill(*args, label=label)
    assert is_real is False, "the fallback never fired; nothing was measured"
    assert (
        len(bot._bus.messages) == 1
    ), f"expected exactly one emit, got {len(bot._bus.messages)}"
    return bot._bus.messages[0]


# ── the closed table, read off the emitted string ───────────────────

ACCEPTED = (
    (_ABSENT, "MANUAL FIRE"),
    ("MANUAL FIRE", "MANUAL FIRE"),
    ("SCRUM", "SCRUM"),
    ("DIST", "DIST"),
    ("STACK", "STACK"),
    ("", "MANUAL FIRE"),
    (None, "MANUAL FIRE"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("exchange_cls", EXCHANGES)
async def test_the_absent_label_is_byte_identical_to_the_pre_u1_message(
    exchange_cls: Any,
) -> None:
    """The zero-behaviour-change claim, stated in bytes."""
    message = await _fallback_message(exchange_cls())
    assert message.encode("utf-8") == LIVE_FALLBACK_MESSAGE.encode("utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("exchange_cls", EXCHANGES)
@pytest.mark.parametrize(("label", "prefix"), ACCEPTED)
async def test_an_accepted_label_names_its_path_and_changes_nothing_else(
    label: Any, prefix: str, exchange_cls: Any
) -> None:
    message = await _fallback_message(exchange_cls(), label)
    assert message.startswith(prefix + ": ")
    # Only the prefix may differ from the message live has always sent.
    assert message == LIVE_FALLBACK_MESSAGE.replace("MANUAL FIRE", prefix, 1)


# ── the set is CLOSED ───────────────────────────────────────────────

REJECTED: tuple[Any, ...] = (
    "BANANA",
    "scrum",  # wrong case
    " SCRUM ",  # padded
    "MANUAL  FIRE",  # doubled space
    "SCRUM: forged",  # tries to carry its own colon into the line
    0,
    True,
    1.5,
    [],
    ("SCRUM",),
    object(),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("label", REJECTED)
async def test_a_token_outside_the_set_never_reaches_the_operator(label: Any) -> None:
    """An unrecognised token would only be a new way to mislabel the
    same line, so it degrades to the manual default instead."""
    message = await _fallback_message(_SilentExchange(), label)
    assert message == LIVE_FALLBACK_MESSAGE


@pytest.mark.asyncio
async def test_a_bad_label_never_raises_after_the_order_is_placed() -> None:
    """This runs after the exchange already executed the order. Raising
    here would abandon the accounting for a trade that really
    happened, which is strictly worse than logging the default."""
    message = await _fallback_message(_RaisingExchange(), object())
    assert message == LIVE_FALLBACK_MESSAGE


def test_the_set_holds_exactly_these_four_labels() -> None:
    """Widening the set silently would put a new token in bot.log."""
    assert ScrummingBot._SETTLED_FILL_LABELS == frozenset(
        {"MANUAL FIRE", "SCRUM", "DIST", "STACK"}
    )
    assert ScrummingBot._SETTLED_FILL_DEFAULT_LABEL == "MANUAL FIRE"


@pytest.mark.asyncio
async def test_POSITIVE_CONTROL_the_prefix_check_can_go_red() -> None:
    """A check that cannot fail is not evidence.

    The same helper, the same forcing mechanism, one different label:
    the assertions the tests above rely on must reject it.
    """
    message = await _fallback_message(_SilentExchange(), "SCRUM")
    assert not message.startswith("MANUAL FIRE: ")
    assert message != LIVE_FALLBACK_MESSAGE
    assert message.startswith("SCRUM: ")


# ── the manual call sites still pass nothing ────────────────────────


def _manual_rebalance_settled_fill_calls() -> list[ast.Call]:
    """Every ``self._settled_fill(...)`` call inside the manual
    rebalance, counted over the AST rather than over substrings: an
    earlier test in this codebase counted substrings and read 3 for 2
    real calls, because the third was the word inside a comment."""
    source = Path(
        inspect.getsourcefile(ScrummingBot._execute_manual_rebalance)
    ).read_text(encoding="utf-8")
    method: Any = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_execute_manual_rebalance"
    )
    return [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", "") == "_settled_fill"
    ]


def test_POSITIVE_CONTROL_the_call_site_scanner_finds_the_calls() -> None:
    """A scanner that finds nothing would pass the next test vacuously."""
    assert len(_manual_rebalance_settled_fill_calls()) == 2


def test_the_manual_path_passes_no_label() -> None:
    """This is what makes U1 a zero-behaviour-change unit: the two
    existing call sites are untouched, so the operator reads exactly the
    string they have always produced.

    If a later unit decides to label the manual rebalance, that IS a
    behaviour change. Restate this pin with the reason; do not delete
    it.
    """
    for call in _manual_rebalance_settled_fill_calls():
        assert not any(kw.arg == "label" for kw in call.keywords)
        assert len(call.args) == 4


def test_settled_fill_takes_label_as_an_optional_keyword() -> None:
    """The parameter has to survive, and its default has to be the one
    that keeps every existing caller byte-identical."""
    params = inspect.signature(ScrummingBot._settled_fill).parameters
    assert "label" in params
    assert params["label"].default is None
