"""Quintessence movements over four buckets: wallets, held, pleroma and embedded."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..core.io_utils import atomic_write_json

QUINTESSENCE_SUPPLY_CAP = Decimal(33_000_000)
QUINTESSENCE_PER_FEE_USD = Decimal(1)
BLEED_FRACTION_AT_LEVEL_1 = Decimal("0.08")
BLEED_FRACTION_AT_LEVEL_10 = Decimal("0.04")
MIN_TRANSFER_SKILL_LEVEL = 1
MAX_TRANSFER_SKILL_LEVEL = 10

DEFAULT_LEDGER_PATH = Path.home() / ".acervator" / "quintessence_ledger.json"
LEDGER_FILE_VERSION = 1

DISTIL = "distil"
SPEND = "spend"
TRANSFER = "transfer"
BLEED = "bleed"
RESPAWN = "respawn"
PAYOUT = "payout"
EMBED_FROM_PLEROMA = "embed_from_pleroma"
EMBED_FROM_WALLET = "embed_from_wallet"
RELEASE_TO_WALLET = "release_to_wallet"
RELEASE_TO_PLEROMA = "release_to_pleroma"

MOVEMENT_KINDS = (
    DISTIL,
    SPEND,
    TRANSFER,
    BLEED,
    RESPAWN,
    PAYOUT,
    EMBED_FROM_PLEROMA,
    EMBED_FROM_WALLET,
    RELEASE_TO_WALLET,
    RELEASE_TO_PLEROMA,
)

_AMOUNT_TYPES = (int, float, Decimal)


class QuintessenceLedgerError(RuntimeError):
    """Raised when a ledger file cannot be replayed or a conservation law breaks."""


def _as_amount(value: object, name: str) -> Decimal:
    """Return ``value`` as a non-negative finite Decimal; bool, str and NaN raise."""
    if type(value) is bool or type(value) not in _AMOUNT_TYPES:
        raise TypeError(
            f"{name} must be int, float or Decimal, not {type(value).__name__}"
        )
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if not amount.is_finite():
        raise ValueError(f"{name} must be finite, got {value!r}")
    if amount < 0:
        raise ValueError(f"{name} must not be negative, got {value!r}")
    return amount


def amount_text(amount: Decimal) -> str:
    """Return ``amount`` in plain notation, with no exponent and no trailing zeros."""
    return format(amount.normalize(), "f")


def _as_address(value: object, name: str) -> str:
    """Return ``value`` as a non-empty address string; every other value raises."""
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty address string, got {value!r}")
    return value


def _as_skill_level(value: object) -> int:
    """Return ``value`` as an int skill_level between the two transfer level bounds."""
    if type(value) is not int:
        raise TypeError(f"skill_level must be int, not {type(value).__name__}")
    if not MIN_TRANSFER_SKILL_LEVEL <= value <= MAX_TRANSFER_SKILL_LEVEL:
        raise ValueError(
            f"skill_level must be {MIN_TRANSFER_SKILL_LEVEL} to "
            f"{MAX_TRANSFER_SKILL_LEVEL}, got {value!r}"
        )
    return value


def bleed_fraction(skill_level: int) -> Decimal:
    """Return the bleed fraction, falling linearly from level one to level ten."""
    level = _as_skill_level(skill_level)
    span = MAX_TRANSFER_SKILL_LEVEL - MIN_TRANSFER_SKILL_LEVEL
    drop = BLEED_FRACTION_AT_LEVEL_1 - BLEED_FRACTION_AT_LEVEL_10
    return BLEED_FRACTION_AT_LEVEL_1 - drop * (level - MIN_TRANSFER_SKILL_LEVEL) / span


@dataclass(frozen=True)
class QuintessenceMovement:
    """One movement: its kind, amount, and the source and target it moves between."""

    kind: str
    amount: Decimal
    source: str | None
    target: str | None
    timestamp: float

    def to_dict(self) -> dict:
        """Return this movement as a JSON-safe dict with amount as a string."""
        return {
            "kind": self.kind,
            "amount": amount_text(self.amount),
            "source": self.source,
            "target": self.target,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> QuintessenceMovement:
        """Return a QuintessenceMovement built from a dict written by to_dict."""
        return cls(
            kind=str(d["kind"]),
            amount=Decimal(str(d["amount"])),
            source=d.get("source"),
            target=d.get("target"),
            timestamp=float(d["timestamp"]),
        )


@dataclass(frozen=True)
class QuintessenceConservation:
    """The four bucket totals, total_ever_minted, supply_cap, and is_balanced."""

    wallets_total: Decimal
    held_total: Decimal
    pleroma_total: Decimal
    embedded_total: Decimal
    total_ever_minted: Decimal
    supply_cap: Decimal
    delta: Decimal
    is_balanced: bool
    is_within_cap: bool
    negative_buckets: int

    def to_dict(self) -> dict:
        """Return this report as a JSON-safe dict with every Decimal as a string."""
        return {
            "wallets_total": amount_text(self.wallets_total),
            "held_total": amount_text(self.held_total),
            "pleroma_total": amount_text(self.pleroma_total),
            "embedded_total": amount_text(self.embedded_total),
            "total_ever_minted": amount_text(self.total_ever_minted),
            "supply_cap": amount_text(self.supply_cap),
            "delta": amount_text(self.delta),
            "is_balanced": self.is_balanced,
            "is_within_cap": self.is_within_cap,
            "negative_buckets": self.negative_buckets,
        }


@dataclass(frozen=True)
class QuintessenceTransfer:
    """What one transfer moved: the amount sent, received, and bled."""

    sent: Decimal
    received: Decimal
    bled: Decimal


@dataclass(frozen=True)
class QuintessenceEmbed:
    """What one embed took from a wallet: the amount spent, embedded, and bled."""

    spent: Decimal
    embedded: Decimal
    bled: Decimal


@dataclass(frozen=True)
class QuintessenceRelease:
    """What one release took out of embedded: the amount released, recovered, returned."""

    released: Decimal
    recovered: Decimal
    returned: Decimal


class QuintessenceLedger:
    """Quintessence accounting where the four buckets equal total_ever_minted."""

    def __init__(self, ledger_path: str | Path | None = None) -> None:
        """Point the ledger at ledger_path or DEFAULT_LEDGER_PATH; no file is read."""
        self._path: Path = Path(ledger_path) if ledger_path else DEFAULT_LEDGER_PATH
        self._movements: list[QuintessenceMovement] = []
        self._wallets: dict[str, Decimal] = {}
        self._held: dict[str, Decimal] = {}
        self._pleroma: Decimal = Decimal(0)
        self._embedded: Decimal = Decimal(0)
        self._total_ever_minted: Decimal = Decimal(0)
        self._load_failed: bool = False

    # -- Write path ----------------------------------------------------------

    def distil(self, address: str, fee_usd: object, trade_grade: object) -> Decimal:
        """Mint at QUINTESSENCE_PER_FEE_USD times trade_grade, under the supply cap."""
        wallet = _as_address(address, "address")
        fee = _as_amount(fee_usd, "fee_usd")
        grade = _as_amount(trade_grade, "trade_grade")
        if grade > 1:
            raise ValueError(f"trade_grade must be 0 to 1, got {trade_grade!r}")
        amount = fee * QUINTESSENCE_PER_FEE_USD * grade
        if amount == 0:
            return Decimal(0)
        if self._total_ever_minted + amount > QUINTESSENCE_SUPPLY_CAP:
            raise OverflowError(
                f"Supply cap {QUINTESSENCE_SUPPLY_CAP:,} Quintessence would be "
                f"exceeded. Only {self.remaining_ever()} remain mintable."
            )
        self._commit([self._movement(DISTIL, amount, None, wallet)])
        return amount

    def spend(self, address: str, amount: object, held_address: str) -> Decimal:
        """Move ``amount`` from address's wallet to held_address, where it rests."""
        wallet = _as_address(address, "address")
        held = _as_address(held_address, "held_address")
        spent = _as_amount(amount, "amount")
        if spent == 0:
            return Decimal(0)
        self._require_balance(wallet, spent)
        self._commit([self._movement(SPEND, spent, wallet, held)])
        return spent

    def transfer(
        self,
        sender: str,
        recipient: str,
        amount: object,
        skill_level: int,
    ) -> QuintessenceTransfer:
        """Move ``amount`` from sender to recipient, less the bleed to the pleroma."""
        from_wallet = _as_address(sender, "sender")
        to_wallet = _as_address(recipient, "recipient")
        if from_wallet == to_wallet:
            raise ValueError("sender and recipient must differ")
        sent = _as_amount(amount, "amount")
        fraction = bleed_fraction(skill_level)
        if sent == 0:
            return QuintessenceTransfer(Decimal(0), Decimal(0), Decimal(0))
        self._require_balance(from_wallet, sent)
        bled = sent * fraction
        received = sent - bled
        moves = [self._movement(TRANSFER, received, from_wallet, to_wallet)]
        if bled > 0:
            moves.append(self._movement(BLEED, bled, from_wallet, None))
        self._commit(moves)
        return QuintessenceTransfer(sent=sent, received=received, bled=bled)

    def payout(self, held_address: str, credits: dict) -> Decimal:
        """Move each amount in ``credits`` from held_address into that wallet.

        Every credit commits together, so a refused one pays nobody, and what stays
        at held_address after the call is the reserve.
        """
        held = _as_address(held_address, "held_address")
        if not isinstance(credits, dict):
            raise TypeError(
                f"credits must be a dict of address to amount, "
                f"not {type(credits).__name__}"
            )
        moves: list[QuintessenceMovement] = []
        total = Decimal(0)
        for address, amount in credits.items():
            wallet = _as_address(address, "address")
            paid = _as_amount(amount, "amount")
            if paid == 0:
                continue
            moves.append(self._movement(PAYOUT, paid, held, wallet))
            total += paid
        if not moves:
            return Decimal(0)
        self._require_held(held, total)
        self._commit(moves)
        return total

    def respawn(self, address: str, amount: object) -> Decimal:
        """Move ``amount`` from the pleroma into address's wallet."""
        wallet = _as_address(address, "address")
        respawned = _as_amount(amount, "amount")
        if respawned == 0:
            return Decimal(0)
        if respawned > self._pleroma:
            raise ValueError(
                f"the pleroma holds {self._pleroma}, cannot respawn {respawned}"
            )
        self._commit([self._movement(RESPAWN, respawned, None, wallet)])
        return respawned

    def embed_from_pleroma(self, amount: object) -> Decimal:
        """Move ``amount`` out of the pleroma into the embedded bucket."""
        embedded = _as_amount(amount, "amount")
        if embedded == 0:
            return Decimal(0)
        if embedded > self._pleroma:
            raise ValueError(
                f"the pleroma holds {self._pleroma}, cannot embed {embedded}"
            )
        self._commit([self._movement(EMBED_FROM_PLEROMA, embedded, None, None)])
        return embedded

    def embed_from_wallet(
        self,
        address: str,
        amount: object,
        embedded_amount: object,
    ) -> QuintessenceEmbed:
        """Move ``amount`` out of address's wallet, ``embedded_amount`` of it into
        the embedded bucket and the remainder into the pleroma.
        """
        wallet = _as_address(address, "address")
        spent = _as_amount(amount, "amount")
        embedded = _as_amount(embedded_amount, "embedded_amount")
        if embedded > spent:
            raise ValueError(
                f"embedded_amount {embedded} is above the amount {spent} spent"
            )
        if spent == 0:
            return QuintessenceEmbed(Decimal(0), Decimal(0), Decimal(0))
        self._require_balance(wallet, spent)
        bled = spent - embedded
        moves = []
        if embedded > 0:
            moves.append(self._movement(EMBED_FROM_WALLET, embedded, wallet, None))
        if bled > 0:
            moves.append(self._movement(BLEED, bled, wallet, None))
        self._commit(moves)
        return QuintessenceEmbed(spent=spent, embedded=embedded, bled=bled)

    def release_from_embedded(
        self,
        address: str,
        amount: object,
        recovered_amount: object,
    ) -> QuintessenceRelease:
        """Move ``amount`` out of the embedded bucket, ``recovered_amount`` of it
        into address's wallet and the remainder into the pleroma.
        """
        wallet = _as_address(address, "address")
        released = _as_amount(amount, "amount")
        recovered = _as_amount(recovered_amount, "recovered_amount")
        if recovered > released:
            raise ValueError(
                f"recovered_amount {recovered} is above the amount {released} released"
            )
        if released == 0:
            return QuintessenceRelease(Decimal(0), Decimal(0), Decimal(0))
        self._require_embedded(released)
        returned = released - recovered
        moves = []
        if recovered > 0:
            moves.append(self._movement(RELEASE_TO_WALLET, recovered, None, wallet))
        if returned > 0:
            moves.append(self._movement(RELEASE_TO_PLEROMA, returned, None, None))
        self._commit(moves)
        return QuintessenceRelease(
            released=released, recovered=recovered, returned=returned
        )

    def release_all_to_pleroma(self, amount: object) -> Decimal:
        """Move all of ``amount`` out of the embedded bucket into the pleroma."""
        released = _as_amount(amount, "amount")
        if released == 0:
            return Decimal(0)
        self._require_embedded(released)
        self._commit([self._movement(RELEASE_TO_PLEROMA, released, None, None)])
        return released

    # -- Queries -------------------------------------------------------------

    def balance(self, address: str) -> Decimal:
        """Return the Quintessence in address's wallet."""
        return self._wallets.get(address, Decimal(0))

    def held_balance(self, held_address: str) -> Decimal:
        """Return the Quintessence resting at held_address."""
        return self._held.get(held_address, Decimal(0))

    def pleroma_balance(self) -> Decimal:
        """Return the Quintessence resting in the pleroma."""
        return self._pleroma

    def embedded_balance(self) -> Decimal:
        """Return the Quintessence in the embedded bucket, which no wallet can spend."""
        return self._embedded

    def total_ever_minted(self) -> Decimal:
        """Return the Quintessence distilled since genesis."""
        return self._total_ever_minted

    def remaining_ever(self) -> Decimal:
        """Return the Quintessence still mintable under the supply cap."""
        return QUINTESSENCE_SUPPLY_CAP - self._total_ever_minted

    def movements(self, address: str | None = None) -> list[QuintessenceMovement]:
        """Return movements touching ``address``, or every movement when None."""
        if address is None:
            return list(self._movements)
        return [m for m in self._movements if address in (m.source, m.target)]

    def conservation(self) -> QuintessenceConservation:
        """Return the four bucket totals and whether their sum balances."""
        wallets_total = sum(self._wallets.values(), Decimal(0))
        held_total = sum(self._held.values(), Decimal(0))
        buckets = wallets_total + held_total + self._pleroma + self._embedded
        negatives = [
            v
            for v in (
                *self._wallets.values(),
                *self._held.values(),
                self._pleroma,
                self._embedded,
            )
            if v < 0
        ]
        delta = buckets - self._total_ever_minted
        return QuintessenceConservation(
            wallets_total=wallets_total,
            held_total=held_total,
            pleroma_total=self._pleroma,
            embedded_total=self._embedded,
            total_ever_minted=self._total_ever_minted,
            supply_cap=QUINTESSENCE_SUPPLY_CAP,
            delta=delta,
            is_balanced=delta == 0 and not negatives,
            is_within_cap=self._total_ever_minted <= QUINTESSENCE_SUPPLY_CAP,
            negative_buckets=len(negatives),
        )

    def supply_summary(self) -> dict:
        """Return the cap, total_ever_minted, remaining_ever and bucket totals."""
        summary = self.conservation().to_dict()
        summary["remaining_ever"] = amount_text(self.remaining_ever())
        summary["wallet_count"] = len(self._wallets)
        summary["held_count"] = len(self._held)
        summary["movement_count"] = len(self._movements)
        return summary

    # -- Persistence ---------------------------------------------------------

    def save(self) -> Path:
        """Write the movement log to the ledger path through atomic_write_json."""
        self._require_usable()
        return atomic_write_json(
            self._path,
            {
                "version": LEDGER_FILE_VERSION,
                "supply_cap": str(QUINTESSENCE_SUPPLY_CAP),
                "total_ever_minted": str(self._total_ever_minted),
                "movements": [m.to_dict() for m in self._movements],
            },
        )

    def load(self) -> QuintessenceLedger:
        """Replay the ledger file; an unreadable or unbalanced file raises."""
        if self._movements:
            raise QuintessenceLedgerError(
                f"{self._path} is already loaded; a second replay would double it"
            )
        if not self._path.exists():
            return self
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            version = data.get("version")
            if version != LEDGER_FILE_VERSION:
                raise QuintessenceLedgerError(
                    f"{self._path} is version {version!r}, "
                    f"this build reads version {LEDGER_FILE_VERSION}"
                )
            movements = [
                QuintessenceMovement.from_dict(d) for d in data.get("movements", [])
            ]
            for movement in movements:
                self._apply(movement)
                self._movements.append(movement)
            recorded = Decimal(str(data["total_ever_minted"]))
        except QuintessenceLedgerError:
            self._load_failed = True
            raise
        except Exception as exc:
            self._load_failed = True
            raise QuintessenceLedgerError(
                f"{self._path} could not be replayed: {exc}"
            ) from exc
        if recorded != self._total_ever_minted:
            self._load_failed = True
            raise QuintessenceLedgerError(
                f"{self._path} records {recorded} ever minted, "
                f"its movements replay to {self._total_ever_minted}"
            )
        self._require_conservation()
        return self

    # -- Internals -----------------------------------------------------------

    @staticmethod
    def _movement(
        kind: str,
        amount: Decimal,
        source: str | None,
        target: str | None,
    ) -> QuintessenceMovement:
        """Return a QuintessenceMovement stamped with the current time."""
        return QuintessenceMovement(
            kind=kind,
            amount=amount,
            source=source,
            target=target,
            timestamp=time.time(),
        )

    def _require_usable(self) -> None:
        """Raise QuintessenceLedgerError while _load_failed is set."""
        if self._load_failed:
            raise QuintessenceLedgerError(
                f"{self._path} failed to load; refusing to write over it"
            )

    def _require_balance(self, wallet: str, amount: Decimal) -> None:
        """Raise ValueError when wallet holds less Quintessence than ``amount``."""
        held = self.balance(wallet)
        if amount > held:
            raise ValueError(f"{wallet} holds {held}, cannot move {amount}")

    def _require_held(self, held: str, amount: Decimal) -> None:
        """Raise ValueError when held_address rests less Quintessence than ``amount``."""
        resting = self.held_balance(held)
        if amount > resting:
            raise ValueError(f"{held} rests {resting}, cannot pay out {amount}")

    def _require_embedded(self, amount: Decimal) -> None:
        """Raise ValueError when the embedded bucket holds less than ``amount``."""
        if amount > self._embedded:
            raise ValueError(
                f"the embedded bucket holds {self._embedded}, cannot release {amount}"
            )

    def _commit(self, movements: list[QuintessenceMovement]) -> None:
        """Apply movements, append them to the log, check conservation and save."""
        self._require_usable()
        wallets = dict(self._wallets)
        held = dict(self._held)
        pleroma = self._pleroma
        embedded = self._embedded
        minted = self._total_ever_minted
        count = len(self._movements)
        try:
            for movement in movements:
                self._apply(movement)
                self._movements.append(movement)
            self._require_conservation()
            self.save()
        except Exception:
            self._wallets = wallets
            self._held = held
            self._pleroma = pleroma
            self._embedded = embedded
            self._total_ever_minted = minted
            del self._movements[count:]
            raise

    def _apply(self, movement: QuintessenceMovement) -> None:
        """Debit and credit the buckets named by ``movement``."""
        amount = movement.amount
        if movement.kind == DISTIL:
            self._total_ever_minted += amount
            self._credit_wallet(movement.target, amount)
        elif movement.kind == SPEND:
            self._debit_wallet(movement.source, amount)
            self._credit_held(movement.target, amount)
        elif movement.kind == TRANSFER:
            self._debit_wallet(movement.source, amount)
            self._credit_wallet(movement.target, amount)
        elif movement.kind == BLEED:
            self._debit_wallet(movement.source, amount)
            self._pleroma += amount
        elif movement.kind == PAYOUT:
            self._debit_held(movement.source, amount)
            self._credit_wallet(movement.target, amount)
        elif movement.kind == RESPAWN:
            self._pleroma -= amount
            self._credit_wallet(movement.target, amount)
        elif movement.kind == EMBED_FROM_PLEROMA:
            self._pleroma -= amount
            self._embedded += amount
        elif movement.kind == EMBED_FROM_WALLET:
            self._debit_wallet(movement.source, amount)
            self._embedded += amount
        elif movement.kind == RELEASE_TO_WALLET:
            self._embedded -= amount
            self._credit_wallet(movement.target, amount)
        elif movement.kind == RELEASE_TO_PLEROMA:
            self._embedded -= amount
            self._pleroma += amount
        else:
            raise QuintessenceLedgerError(
                f"unknown movement kind {movement.kind!r}; "
                f"known kinds are {MOVEMENT_KINDS}"
            )

    def _credit_wallet(self, address: str | None, amount: Decimal) -> None:
        """Add ``amount`` to the wallet named by address."""
        wallet = _as_address(address, "target")
        self._wallets[wallet] = self._wallets.get(wallet, Decimal(0)) + amount

    def _debit_wallet(self, address: str | None, amount: Decimal) -> None:
        """Take ``amount`` from the wallet named by address."""
        wallet = _as_address(address, "source")
        self._wallets[wallet] = self._wallets.get(wallet, Decimal(0)) - amount

    def _credit_held(self, address: str | None, amount: Decimal) -> None:
        """Add ``amount`` to the held address named by address."""
        held = _as_address(address, "target")
        self._held[held] = self._held.get(held, Decimal(0)) + amount

    def _debit_held(self, address: str | None, amount: Decimal) -> None:
        """Take ``amount`` from the held address named by address."""
        held = _as_address(address, "source")
        self._held[held] = self._held.get(held, Decimal(0)) - amount

    def _require_conservation(self) -> None:
        """Raise QuintessenceLedgerError when buckets and total_ever_minted differ."""
        report = self.conservation()
        if not report.is_balanced or not report.is_within_cap:
            raise QuintessenceLedgerError(
                f"conservation broken: wallets {report.wallets_total} + held "
                f"{report.held_total} + pleroma {report.pleroma_total} + embedded "
                f"{report.embedded_total} against "
                f"{report.total_ever_minted} ever minted, delta {report.delta}, "
                f"{report.negative_buckets} negative bucket(s)"
            )
