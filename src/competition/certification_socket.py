"""Certify one fill against the PoA chain and distil Quintessence from its fee.

``CertificationSocket.certify`` signs a fill with ``BotIdentity``, appends it to
that bot's ``MerkleTradeLog``, posts the commitment through ``LocalChain``, and
calls ``QuintessenceLedger.distil`` with the fee the venue reported.
``lifetime_certified_fee_usd`` is the socket's own total and only ever rises.
``may_participate`` answers False for a bot that has certified nothing, and
``SharedTestnetBridge.install_on`` builds one socket per process. A fill carrying
an ``exchange_id`` and a ``season`` names an ``Activation``, and ``certify`` then
puts it through ``CaptureBounds.award`` before ``distil`` mints anything.
``award_wallet_for`` answers which wallet that award credits: a bot feeding a
``ParticipantRegistry`` node credits that node's wallet, so every bot on one node
shares one wallet, one market share ceiling and one cooldown.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from ..core.event_bus import Event, EventBus
from ..core.io_utils import atomic_write_json
from .bot_identity import BotIdentity, TradeRecord
from .capture_bounds import (
    AWARDED,
    NO_ACTIVATION_NAMED,
    AwardRequest,
    CaptureAward,
    CaptureBounds,
    CaptureRefusedError,
    activation_key,
    pool_key,
)
from .local_testnet import LocalTestnet
from .merkle_log import MerkleTradeLog
from .participant_node import ParticipantRegistry
from .quintessence_ledger import QuintessenceLedger

logger = logging.getLogger("acervator.certification_socket")

DEFAULT_SOCKET_PATH = Path.home() / ".acervator" / "certification_socket.json"
SOCKET_FILE_VERSION = 1

CERTIFICATION_CONTRACT = "CertifiedTransactionSocket"
CERTIFY_FUNCTION = "certifyTrade"
CERTIFIED_EVENT = "TradeCertified"

#: The competition a fill outside any event certifies against.
STANDING_COMPETITION_ID = "POA-STANDING"

_NUMBER_TYPES = (int, float, Decimal)


def _no_identity(bot_id: str) -> BotIdentity | None:
    """Return None for every ``bot_id``, until ``attach_to_bus`` takes a resolver."""
    return None


class CertificationRefusedError(RuntimeError):
    """Raised when a fill may not be certified, or a bot may not participate."""


def _as_fee_usd(value: object) -> Decimal:
    """Return ``value`` as a non-negative finite Decimal fee; bool and str raise."""
    if type(value) is bool or type(value) not in _NUMBER_TYPES:
        raise TypeError(
            f"fee_usd must be int, float or Decimal, not {type(value).__name__}"
        )
    fee = value if isinstance(value, Decimal) else Decimal(str(value))
    if not fee.is_finite():
        raise ValueError(f"fee_usd must be finite, got {value!r}")
    if fee < 0:
        raise ValueError(f"fee_usd must not be negative, got {value!r}")
    return fee


def _as_trade_grade(value: object) -> Decimal:
    """Return ``value`` as a Decimal trade_grade of zero to one; outside that raises."""
    if type(value) is bool or type(value) not in _NUMBER_TYPES:
        raise TypeError(
            f"trade_grade must be int, float or Decimal, not {type(value).__name__}"
        )
    grade = value if isinstance(value, Decimal) else Decimal(str(value))
    if not grade.is_finite():
        raise ValueError(f"trade_grade must be finite, got {value!r}")
    if grade < 0 or grade > 1:
        raise ValueError(f"trade_grade must be 0 to 1, got {value!r}")
    return grade


@dataclass(frozen=True)
class CertifiedFill:
    """One fill offered for certification, and the activation it earns against.

    ``fee_usd`` is the fee the venue reported, ``exchange_id`` and ``season`` name
    the ``Activation`` whose pool pays, and ``scored_axes``, ``execution_bps`` and
    ``ta_timeframe`` are what ``CaptureBounds`` reads.
    """

    fill_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    fee_usd: float
    role: str = "UNKNOWN"
    timestamp: float | None = None
    trade_grade: float = 1.0
    exchange_id: str = ""
    season: int | None = None
    scored_axes: int = 0
    ta_timeframe: str = ""
    execution_bps: float | None = None

    @property
    def names_activation(self) -> bool:
        """Answer whether this fill carries both an ``exchange_id`` and a ``season``."""
        return bool(str(self.exchange_id or "").strip()) and self.season is not None

    @property
    def activation(self) -> str:
        """The ``activation_key`` this fill names, or "" while it names none."""
        if not self.names_activation:
            return ""
        return activation_key(self.exchange_id, int(self.season or 0))

    @property
    def pool(self) -> str:
        """The ``pool_key`` of the market pool this fill's award comes out of."""
        if not self.names_activation or not str(self.symbol or "").strip():
            return ""
        return pool_key(self.exchange_id, int(self.season or 0), self.symbol)


@dataclass(frozen=True)
class CertificationReceipt:
    """What one certification produced, and which bound decided its award.

    ``distilled`` is the Quintessence minted, ``activation`` the period the fill
    named, and ``award_reason`` either ``AWARDED`` or the ``CaptureBounds`` reason
    that paid nothing.
    """

    bot_id: str
    fill_id: str
    trade_seq: int
    leaf_hash: str
    merkle_root: str
    tx_hash: str
    fee_usd: Decimal
    distilled: Decimal
    lifetime_fee_usd: Decimal
    certified_fill_count: int
    conservation: Any
    activation: str = ""
    pool: str = ""
    award_reason: str = AWARDED
    award: CaptureAward | None = None

    def to_dict(self) -> dict:
        """Return this receipt as a JSON-safe dict with every Decimal as a string."""
        return {
            "bot_id": self.bot_id,
            "fill_id": self.fill_id,
            "trade_seq": self.trade_seq,
            "leaf_hash": self.leaf_hash,
            "merkle_root": self.merkle_root,
            "tx_hash": self.tx_hash,
            "fee_usd": str(self.fee_usd),
            "distilled": str(self.distilled),
            "lifetime_fee_usd": str(self.lifetime_fee_usd),
            "certified_fill_count": self.certified_fill_count,
            "conservation": self.conservation.to_dict(),
            "activation": self.activation,
            "pool": self.pool,
            "award_reason": self.award_reason,
            "award": None if self.award is None else self.award.to_dict(),
        }


class CertificationSocket:
    """Certify fills against one chain and distil from one Quintessence ledger.

    The chain, the ledger and the ``CaptureBounds`` arrive by construction, so a
    TestNet demo run is one socket over a different ``LocalTestnet`` and a
    ``CaptureBounds`` over that same chain, running the one ``certify`` path.
    """

    def __init__(
        self,
        testnet: LocalTestnet,
        quint_ledger: QuintessenceLedger,
        competition_id: str = STANDING_COMPETITION_ID,
        socket_path: str | Path | None = None,
        mutation_lock: AbstractContextManager[bool] | None = None,
        capture_bounds: CaptureBounds | None = None,
        participants: ParticipantRegistry | None = None,
    ) -> None:
        """Hold the chain, the ledger, the bounds, the register and the per-bot totals."""
        self._testnet = testnet
        self._ledger = quint_ledger
        self._bounds = capture_bounds
        self._participants = participants
        self._competition_id = competition_id
        self._path: Path = Path(socket_path) if socket_path else DEFAULT_SOCKET_PATH
        self._chain_lock: AbstractContextManager[bool] = (
            mutation_lock if mutation_lock is not None else threading.RLock()
        )
        self._state_lock = threading.RLock()
        self._logs: dict[str, MerkleTradeLog] = {}
        self._lifetime_fee_usd: dict[str, Decimal] = {}
        self._certified_fill_ids: dict[str, set[str]] = {}
        self._identity_resolver: Callable[[str], BotIdentity | None] = _no_identity
        self._bus_unsubscribe: Callable[[], None] | None = None

    # -- Certification -------------------------------------------------------

    def certify(
        self, identity: BotIdentity, fill: CertifiedFill
    ) -> CertificationReceipt:
        """Sign, log, post and distil one fill, and return its receipt.

        Raises ``CertificationRefusedError`` for an empty ``fill_id``, a fill already
        certified, a participant wallet the ledger cannot answer for, or an award
        past the ledger's ``remaining_ever``; a fill a ``CaptureBounds`` refuses is
        still logged and distils nothing.
        """
        bot_id = identity.bot_id
        fill_id = str(fill.fill_id or "").strip()
        if not fill_id:
            raise CertificationRefusedError(
                "a fill with no fill_id cannot be certified"
            )
        fee = _as_fee_usd(fill.fee_usd)
        grade = _as_trade_grade(fill.trade_grade)
        award = fee * grade
        # Resolved before any mutation, so a refused wallet logs no trade.
        participant = self.award_wallet_for(bot_id)

        with self._state_lock:
            if fill_id in self._certified_fill_ids.get(bot_id, ()):
                raise CertificationRefusedError(
                    f"fill {fill_id} is already certified for bot {bot_id[:12]}"
                )
            remaining = self._ledger.remaining_ever()
            if award > remaining:
                raise CertificationRefusedError(
                    f"the supply cap leaves {remaining} Quintessence, short of "
                    f"the {award} this fill would distil"
                )
            award_reason, capture = self._award_for(participant, fill, fee, grade)
            log = self._log_for(bot_id)
            record = identity.sign_trade(
                TradeRecord(
                    bot_pubkey=bot_id,
                    competition=self._competition_id,
                    symbol=fill.symbol,
                    side=fill.side,
                    quantity=float(fill.quantity),
                    price=float(fill.price),
                    timestamp=(
                        time.time() if fill.timestamp is None else float(fill.timestamp)
                    ),
                    trade_seq=log.size,
                    role=fill.role,
                )
            )
            leaf = log.append(record)
            distilled = (
                self._ledger.distil(participant, fee, grade)
                if award_reason == AWARDED
                else Decimal(0)
            )
            self._certified_fill_ids.setdefault(bot_id, set()).add(fill_id)
            self._lifetime_fee_usd[bot_id] = (
                self._lifetime_fee_usd.get(bot_id, Decimal(0)) + fee
            )
            root = log.root
            count = len(self._certified_fill_ids[bot_id])
            total = self._lifetime_fee_usd[bot_id]
            self.save()

        tx_hash = self._post_commitment(bot_id, record, leaf, root, fee, distilled)
        receipt = CertificationReceipt(
            bot_id=bot_id,
            fill_id=fill_id,
            trade_seq=record.trade_seq,
            leaf_hash=leaf,
            merkle_root=root,
            tx_hash=tx_hash,
            fee_usd=fee,
            distilled=distilled,
            lifetime_fee_usd=total,
            certified_fill_count=count,
            conservation=self._ledger.conservation(),
            activation=fill.activation,
            pool=fill.pool,
            award_reason=award_reason,
            award=capture,
        )
        logger.info(
            "certified fill %s for bot %s: fee $%s distilled %s Quintessence into "
            "%s, lifetime fee $%s over %d fills, activation %r pool %r award %s",
            fill_id,
            bot_id[:12],
            fee,
            distilled,
            participant,
            total,
            count,
            fill.activation,
            fill.pool,
            award_reason,
        )
        return receipt

    def _award_for(
        self,
        participant: str,
        fill: CertifiedFill,
        fee: Decimal,
        grade: Decimal,
    ) -> tuple[str, CaptureAward | None]:
        """Bound ``fill`` against ``participant``, and return its reason and award.

        ``participant`` is the wallet ``award_wallet_for`` resolved, so the share
        ceiling and the cooldown count against that one address. Answers
        ``AWARDED`` with no award while no bounds were constructed, and
        ``NO_ACTIVATION_NAMED`` for a fill carrying no ``exchange_id`` and season.
        """
        if self._bounds is None:
            return (AWARDED, None)
        if not fill.names_activation:
            logger.info(
                "fill %s on %s names no activation, so no market pool pays it",
                fill.fill_id,
                fill.symbol,
            )
            return (NO_ACTIVATION_NAMED, None)
        request = AwardRequest(
            exchange_id=str(fill.exchange_id),
            season=int(fill.season or 0),
            symbol=str(fill.symbol),
            participant=participant,
            fee_usd=float(fee),
            grade_numeric=float(grade),
            scored_axes=int(fill.scored_axes),
            ta_timeframe=str(fill.ta_timeframe),
            execution_bps=fill.execution_bps,
            at_epoch=fill.timestamp,
        )
        try:
            with self._chain_lock:
                award = self._bounds.award(request)
        except CaptureRefusedError as refused:
            logger.info(
                "capture bounds refused fill %s in %s as %s: %s",
                fill.fill_id,
                fill.activation,
                refused.reason,
                refused,
            )
            return (refused.reason, None)
        return (AWARDED, award)

    def _post_commitment(
        self,
        bot_id: str,
        record: TradeRecord,
        leaf: str,
        root: str,
        fee: Decimal,
        distilled: Decimal,
    ) -> str:
        """Send the commitment to the chain and emit ``CERTIFIED_EVENT``."""
        args = {
            "bot": bot_id[:16],
            "competition": self._competition_id,
            "merkleRoot": root[:16],
            "leafHash": leaf[:16],
            "tradeSeq": record.trade_seq,
            "feeUsd": str(fee),
            "distilled": str(distilled),
        }
        with self._chain_lock:
            chain = self._testnet.chain
            tx = chain.send_tx(
                self._wallet_for(bot_id),
                CERTIFICATION_CONTRACT,
                CERTIFY_FUNCTION,
                args,
            )
            chain.emit(tx.tx_hash, CERTIFICATION_CONTRACT, CERTIFIED_EVENT, args)
        return str(tx.tx_hash)

    # -- Participation -------------------------------------------------------

    def may_participate(self, bot_id: str) -> bool:
        """Answer whether ``bot_id`` has certified at least one fill."""
        with self._state_lock:
            return bool(self._certified_fill_ids.get(bot_id))

    def require_participation(self, bot_id: str) -> None:
        """Raise ``CertificationRefusedError`` while ``bot_id`` has certified nothing."""
        if not self.may_participate(bot_id):
            raise CertificationRefusedError(
                f"bot {bot_id[:12]} has certified no trades and cannot enter a "
                f"PoA event"
            )

    # -- Queries -------------------------------------------------------------

    @property
    def participants(self) -> ParticipantRegistry | None:
        """The ``ParticipantRegistry`` an award credits through, or None for none."""
        return self._participants

    def award_wallet_for(self, bot_id: str) -> str:
        """The wallet a certified fill for ``bot_id`` credits and the bounds count.

        A bot feeding a registered participant node credits that node's wallet, so
        every bot on one node shares one wallet, one market share ceiling and one
        cooldown. A bot feeding no node, and every bot while no
        ``ParticipantRegistry`` was constructed, keeps the ``_wallet_for`` address:
        ``ParticipantRegistry.register_node`` refuses a wallet no movement has put
        in the ledger's book, and this ``distil`` is the movement that puts one
        there, so refusing such a fill would leave no node able to register.
        Raises ``CertificationRefusedError`` for a node wallet this socket's ledger
        holds no record of, because no award credits an address the ledger cannot
        answer for.
        """
        if self._participants is None:
            return self._wallet_for(bot_id)
        node_id = self._participants.node_of_bot(bot_id)
        if node_id is None:
            return self._wallet_for(bot_id)
        wallet = self._participants.wallet_of(node_id)
        if wallet is None or not self._ledger.holds_wallet(wallet):
            raise CertificationRefusedError(
                f"bot {bot_id[:12]} feeds node {node_id}, whose wallet "
                f"{wallet!r} this socket's Quintessence ledger holds no record "
                f"of; an award credits a wallet the ledger can answer for"
            )
        return wallet

    def lifetime_certified_fee_usd(self, bot_id: str) -> Decimal:
        """Return the certified exchange fee ``bot_id`` has ever paid."""
        with self._state_lock:
            return self._lifetime_fee_usd.get(bot_id, Decimal(0))

    def certified_fill_count(self, bot_id: str) -> int:
        """Return how many distinct fills ``bot_id`` has certified."""
        with self._state_lock:
            return len(self._certified_fill_ids.get(bot_id, ()))

    def merkle_root(self, bot_id: str) -> str:
        """Return the commitment over every fill ``bot_id`` has certified."""
        with self._state_lock:
            return self._log_for(bot_id).root

    def submission_summary(self, bot_id: str) -> dict:
        """Return ``MerkleTradeLog.submission_summary`` for ``bot_id``."""
        with self._state_lock:
            return self._log_for(bot_id).submission_summary()

    def proof_for(self, bot_id: str, trade_seq: int) -> dict:
        """Return ``MerkleTradeLog.proof_for`` for one of ``bot_id``'s fills."""
        with self._state_lock:
            return self._log_for(bot_id).proof_for(trade_seq)

    def ratchet_certified_fee_usd(
        self, bot_id: str, observed_fee_usd: object
    ) -> Decimal:
        """Raise ``bot_id``'s total to ``observed_fee_usd`` when that is higher.

        ``BotStats.fees_paid_exchange`` is re-derived from a bounded trade window
        and falls, so this takes the max and never the observation alone.
        """
        observed = _as_fee_usd(observed_fee_usd)
        with self._state_lock:
            held = self._lifetime_fee_usd.get(bot_id, Decimal(0))
            if observed > held:
                self._lifetime_fee_usd[bot_id] = observed
                self.save()
                return observed
            return held

    def socket_summary(self) -> dict:
        """Return the per-bot fee totals, fill counts and the ledger's supply.

        ``awards_bounded`` is False while no ``CaptureBounds`` was constructed, and
        ``awards_to_participants`` is False while no ``ParticipantRegistry`` was, so
        every award then credits a ``_wallet_for`` address.
        """
        with self._state_lock:
            return {
                "competition_id": self._competition_id,
                "awards_bounded": self._bounds is not None,
                "awards_to_participants": self._participants is not None,
                "bots": {
                    bot_id: {
                        "lifetime_fee_usd": str(total),
                        "certified_fill_count": len(
                            self._certified_fill_ids.get(bot_id, ())
                        ),
                        "merkle_root": self._log_for(bot_id).root,
                    }
                    for bot_id, total in sorted(self._lifetime_fee_usd.items())
                },
                "quintessence": self._ledger.supply_summary(),
            }

    # -- Bus ------------------------------------------------------------------

    def attach_to_bus(
        self,
        bus: EventBus,
        identity_for: Callable[[str], BotIdentity | None],
    ) -> None:
        """Subscribe ``trade.filled`` so every fill reaches ``certify``.

        ``identity_for`` takes a bot id and returns that bot's ``BotIdentity``,
        or None for a bot whose fill is then not certified.
        """
        self._identity_resolver = identity_for
        self._bus_unsubscribe = bus.subscribe("trade.filled", self._on_trade_filled)
        logger.info("CertificationSocket subscribed to trade.filled")

    def detach_from_bus(self) -> None:
        """Remove the ``trade.filled`` subscription."""
        if self._bus_unsubscribe is not None:
            self._bus_unsubscribe()
            self._bus_unsubscribe = None

    def _on_trade_filled(self, event: Event) -> None:
        """Certify the fill one ``trade.filled`` event describes.

        The payload carries ``fee_usd`` when the venue reported a fee, and
        ``exchange_id`` and ``season`` are absent from every current emit site,
        so such a fill names no activation and distils nothing.
        """
        try:
            payload = getattr(event, "data", None)
            if not isinstance(payload, dict):
                return
            merged = dict(payload)
            inner = payload.get("data")
            if isinstance(inner, dict):
                merged.update(inner)
            bot_id = str(merged.get("bot_id", "") or "")
            if not bot_id:
                return
            identity = self._identity_resolver(bot_id)
            if identity is None:
                logger.debug("bot %s has no identity; fill not certified", bot_id)
                return
            if "fee_usd" not in merged and merged.get("fee_refusal"):
                logger.info(
                    "fill on %s carries no venue fee and distils nothing: %s",
                    merged.get("symbol", "") or bot_id,
                    merged["fee_refusal"],
                )
            fill = CertifiedFill(
                fill_id=str(
                    merged.get("fill_id")
                    or merged.get("order_id")
                    or f"{bot_id}:{getattr(event, 'timestamp', 0)}"
                ),
                symbol=str(merged.get("symbol", "") or ""),
                side=str(merged.get("side", "") or "").lower(),
                quantity=float(merged.get("amount", 0) or 0),
                price=float(merged.get("price", 0) or 0),
                fee_usd=float(merged.get("fee_usd", 0) or 0),
                role=str(merged.get("type", "") or merged.get("role", "") or "UNKNOWN"),
                timestamp=getattr(event, "timestamp", None),
                exchange_id=str(merged.get("exchange_id", "") or ""),
                season=self._season_in(merged),
                scored_axes=int(merged.get("scored_axes", 0) or 0),
                ta_timeframe=str(merged.get("ta_timeframe", "") or ""),
                execution_bps=self._execution_bps_in(merged),
            )
            self.certify(identity, fill)
        except Exception:
            logger.exception("trade.filled certification failed")

    # -- Persistence ---------------------------------------------------------

    def save(self) -> Path:
        """Write the per-bot fee totals and certified fill ids to the socket path."""
        return atomic_write_json(
            self._path,
            {
                "version": SOCKET_FILE_VERSION,
                "competition_id": self._competition_id,
                "bots": {
                    bot_id: {
                        "lifetime_fee_usd": str(total),
                        "certified_fill_ids": sorted(
                            self._certified_fill_ids.get(bot_id, ())
                        ),
                    }
                    for bot_id, total in sorted(self._lifetime_fee_usd.items())
                },
            },
        )

    def load(self) -> CertificationSocket:
        """Replay the socket file, taking the max of the held and stored totals.

        A missing, unreadable or foreign-version file leaves every total as held,
        so no read can lower one.
        """
        if not self._path.exists():
            return self
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("%s could not be read; totals stay as held", self._path)
            return self
        if data.get("version") != SOCKET_FILE_VERSION:
            logger.warning(
                "%s is version %r, this build reads version %d; totals stay as held",
                self._path,
                data.get("version"),
                SOCKET_FILE_VERSION,
            )
            return self
        with self._state_lock:
            for bot_id, row in (data.get("bots") or {}).items():
                stored = Decimal(str(row.get("lifetime_fee_usd", "0")))
                held = self._lifetime_fee_usd.get(bot_id, Decimal(0))
                self._lifetime_fee_usd[bot_id] = max(held, stored)
                self._certified_fill_ids.setdefault(bot_id, set()).update(
                    str(i) for i in row.get("certified_fill_ids", ())
                )
        return self

    # -- Internals -----------------------------------------------------------

    @staticmethod
    def _season_in(merged: dict) -> int | None:
        """Return the payload's ``season`` as an int, or None when it carries none."""
        season = merged.get("season")
        if season is None or isinstance(season, bool):
            return None
        try:
            return int(season)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _execution_bps_in(merged: dict) -> float | None:
        """Return the payload's ``execution_bps`` as a float, or None for none."""
        bps = merged.get("execution_bps")
        if bps is None or isinstance(bps, bool):
            return None
        try:
            return float(bps)
        except (TypeError, ValueError):
            return None

    def _log_for(self, bot_id: str) -> MerkleTradeLog:
        """Return ``bot_id``'s MerkleTradeLog, building it on first use."""
        log = self._logs.get(bot_id)
        if log is None:
            log = MerkleTradeLog(self._competition_id, bot_id)
            self._logs[bot_id] = log
        return log

    @staticmethod
    def _wallet_for(bot_id: str) -> str:
        """Return the address synthesised from ``bot_id``.

        ``_post_commitment`` sends every trade commitment from this address,
        because a trade is the bot's own, and ``award_wallet_for`` returns it as the
        credited wallet for a bot feeding no participant node.
        """
        return f"0x{bot_id[:40]}"
