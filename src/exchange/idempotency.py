"""One client order id per order, held for a resend while the venue has not answered.

``IdempotencyLayer.derive_coid`` issues a ``coid`` and holds it, and a resend of the
same ``TradeIntent`` sends the held ``coid``, which a venue will not open twice.
``decision_purpose`` names a decision, whose resend keeps the ``coid`` at any size or
price, and ``IdempotencyLayer.end_retry`` drops it once an order comes back for that
intent. ``BotContainer.guarded_place_order`` calls both, and ``end_flight`` once a send
is over. A send under a ``coid`` still ``in_flight`` is refused, and a ``coid`` the venue
refused as used stays held with ``id_refused`` set, so later tries read and send nothing.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

#: Hex characters in a hash, and ``acrv-`` beside them fits a 36-character id field.
HASH_CHARS = 16

#: ``TradeIntent.purpose`` of a send that names no decision.
NO_DECISION_PURPOSE = "trade"

#: Opens a ``TradeIntent.purpose`` that names a decision.
DECISION_PREFIX = "decision:"

#: The ccxt error class a venue's refusal of a used client order id raises.
USED_ID_ERROR = "DuplicateOrderId"

#: The ccxt base class of every error a venue answered with.
VENUE_ANSWER_ERROR = "ExchangeError"

#: A used-id refusal under another ccxt class: OKX 51016, Bybit 170141, 110072 and 12141,
#: Binance -4116, KuCoin 126044 and Poloniex 21312, 25004 and 25006, or the venue's words,
#: which Binance -2010 needs because that code also carries other refusals.
USED_ID_TEXT = re.compile(
    r"(?<![\w-])(?:51016|170141|110072|12141|-4116|126044|21312|25004|25006)(?!\w)"
    r"|duplicat|already exists|repeated_creation",
    re.IGNORECASE,
)


def _short_hash(text: str) -> str:
    """The first ``HASH_CHARS`` hex characters of the SHA-256 of ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:HASH_CHARS]


def refuses_used_id(error: BaseException) -> bool:
    """True where ``error`` is a ``USED_ID_ERROR``, or a ``VENUE_ANSWER_ERROR`` whose
    text ``USED_ID_TEXT`` matches: that ``coid`` names an order the venue already took."""
    kinds = {kind.__name__ for kind in type(error).__mro__}
    return USED_ID_ERROR in kinds or (
        VENUE_ANSWER_ERROR in kinds and USED_ID_TEXT.search(str(error)) is not None
    )


def decision_purpose(decision: str) -> str:
    """The ``TradeIntent.purpose`` that carries ``decision``, ``NO_DECISION_PURPOSE``
    for an empty name."""
    return f"{DECISION_PREFIX}{decision}" if decision else NO_DECISION_PURPOSE


@dataclass
class TradeIntent:
    """The exact trade the bot wants to submit, and identical intents share one
    ``fingerprint``, which ``derive_coid`` reads to find a resend."""

    symbol: str
    side: str  # "buy" / "sell"
    amount: float  # in base asset units
    price: Optional[float]  # None for market orders
    bot_id: str
    purpose: str = ""  # NO_DECISION_PURPOSE, or decision_purpose of a named decision

    @property
    def decision(self) -> str:
        """The decision ``purpose`` names, empty where it names none."""
        if self.purpose.startswith(DECISION_PREFIX):
            return self.purpose[len(DECISION_PREFIX) :]
        return ""

    def fingerprint(self, session_nonce: str) -> str:
        """Deterministic hash. Same intent + same session = same value, and a named
        ``decision`` leaves ``amount`` and ``price`` out of it."""
        if self.decision:
            return _short_hash(
                f"{self.bot_id}|{self.symbol}|{self.side}|{self.purpose}|"
                f"{session_nonce}"
            )
        # Round price to 8 decimals to absorb harmless float-jitter while
        # still distinguishing genuinely different price points.
        price_str = "M" if self.price is None else f"{self.price:.8f}"
        amount_str = f"{self.amount:.10f}"
        return _short_hash(
            f"{self.bot_id}|{self.symbol}|{self.side}|{amount_str}|"
            f"{price_str}|{self.purpose}|{session_nonce}"
        )


@dataclass
class UnansweredSend:
    """A ``coid`` the venue has not answered: ``intent`` as last sent, ``issued_at`` its
    first send, ``sizes`` each ``(amount, price read)`` it went out at, ``in_flight`` from
    ``derive_coid`` to ``end_flight``, and ``id_refused`` once ``note_id_refused`` ran."""

    coid: str
    issued_at: float
    intent: TradeIntent
    sizes: list[tuple[float, float]]
    in_flight: bool = True
    id_refused: bool = False


class IdempotencyLayer:
    """Per-process record of each ``coid`` the venue has not answered."""

    def __init__(self, max_entries: int = 5000) -> None:
        self.max_entries = max_entries
        # Not persisted, so a restart gives new coids for the same intent.
        self.session_nonce = uuid.uuid4().hex[:8]
        self._unanswered: dict[str, UnansweredSend] = {}
        self._issued = 0
        self._lock = threading.RLock()

    def derive_coid(
        self,
        intent: TradeIntent,
        price_read: float = 0.0,
        units: Optional[float] = None,
    ) -> str:
        """The ``coid`` held for ``intent``, or a new one no earlier order carried, set
        ``in_flight``, with ``units``, else ``intent.amount``, and ``price_read`` added to
        ``UnansweredSend.sizes`` unless ``id_refused`` says no send follows."""
        size = (intent.amount if units is None else float(units), price_read)
        with self._lock:
            fp = intent.fingerprint(self.session_nonce)
            held = self._unanswered.get(fp)
            if held is not None:
                held.in_flight = True
                if not held.id_refused:
                    held.sizes.append(size)
                    held.intent = intent
                logger.info(
                    "Idempotency: reusing coid=%s for retry of "
                    "%s %s %.8f@%s (issued %.1fs ago)",
                    held.coid,
                    intent.side,
                    intent.symbol,
                    intent.amount,
                    "MKT" if intent.price is None else f"{intent.price:.8f}",
                    time.time() - held.issued_at,
                )
                return held.coid
            self._issued += 1
            coid = f"acrv-{_short_hash(f'{fp}|{self._issued}')}"
            self._unanswered[fp] = UnansweredSend(
                coid=coid,
                issued_at=time.time(),
                intent=intent,
                sizes=[size],
            )
            self._enforce_size_limit()
            return coid

    def holds(self, intent: TradeIntent) -> bool:
        """True where ``derive_coid`` answers a held ``coid`` for ``intent``."""
        with self._lock:
            return intent.fingerprint(self.session_nonce) in self._unanswered

    def in_flight(self, intent: TradeIntent) -> bool:
        """True while a send under the ``coid`` held for ``intent`` waits on the venue."""
        with self._lock:
            held = self._unanswered.get(intent.fingerprint(self.session_nonce))
            return held is not None and held.in_flight

    def end_flight(self, intent: TradeIntent) -> None:
        """Clear ``in_flight`` on the ``coid`` held for ``intent``."""
        with self._lock:
            held = self._unanswered.get(intent.fingerprint(self.session_nonce))
            if held is not None:
                held.in_flight = False

    def sending(self, bot_id: str, symbol: str) -> bool:
        """True while any send of ``bot_id`` on ``symbol`` is ``in_flight``."""
        with self._lock:
            return any(
                held.in_flight
                and held.intent.bot_id == bot_id
                and held.intent.symbol == symbol
                for held in self._unanswered.values()
            )

    def id_refused(self, intent: TradeIntent) -> bool:
        """True where the venue refused the ``coid`` held for ``intent`` as used."""
        with self._lock:
            held = self._unanswered.get(intent.fingerprint(self.session_nonce))
            return held is not None and held.id_refused

    def note_id_refused(self, intent: TradeIntent) -> None:
        """Set ``id_refused`` on the ``coid`` held for ``intent``."""
        with self._lock:
            held = self._unanswered.get(intent.fingerprint(self.session_nonce))
            if held is not None:
                held.id_refused = True

    def end_retry(self, intent: TradeIntent) -> None:
        """Drop the ``coid`` held for ``intent``, leaving ``derive_coid`` to issue a new
        one for the next order."""
        with self._lock:
            self._unanswered.pop(intent.fingerprint(self.session_nonce), None)

    def unanswered_sends(
        self, bot_id: str, symbol: str, side: str
    ) -> list[UnansweredSend]:
        """The sends naming a decision that hold a ``coid`` for ``bot_id`` on ``symbol``
        and ``side``, oldest first."""
        with self._lock:
            return [
                held
                for held in self._unanswered.values()
                if held.intent.decision
                and held.intent.bot_id == bot_id
                and held.intent.symbol == symbol
                and held.intent.side == side
            ]

    def unanswered_decisions(self, bot_id: str, symbol: str, side: str) -> list[str]:
        """The decisions of ``unanswered_sends``."""
        return [
            held.intent.decision for held in self.unanswered_sends(bot_id, symbol, side)
        ]

    def unanswered_buy_units(self, bot_id: str, symbol: str) -> float:
        """The units the ``unanswered_sends`` buys of ``bot_id`` on ``symbol`` may have
        put at the venue, the largest of ``UnansweredSend.sizes`` per ``coid``."""
        return sum(
            max((size for size, _price in held.sizes), default=0.0)
            for held in self.unanswered_sends(bot_id, symbol, "buy")
        )

    def _enforce_size_limit(self) -> None:
        if len(self._unanswered) <= self.max_entries:
            return
        # Drop the oldest entries
        by_age = sorted(self._unanswered.items(), key=lambda kv: kv[1].issued_at)
        for k, _ in by_age[: len(self._unanswered) - self.max_entries]:
            del self._unanswered[k]


# Process-singleton
_layer: Optional[IdempotencyLayer] = None
_singleton_lock = threading.Lock()


def get_idempotency_layer() -> IdempotencyLayer:
    """Return the process-wide IdempotencyLayer (lazy-init)."""
    global _layer
    if _layer is None:
        with _singleton_lock:
            if _layer is None:
                _layer = IdempotencyLayer()
    return _layer


def reset_for_test() -> None:
    """Reset the singleton — tests only."""
    global _layer
    with _singleton_lock:
        _layer = None
