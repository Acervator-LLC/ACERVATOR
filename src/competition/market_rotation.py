"""The rotating reward set, and which markets it lets reward Quintessence.

``MarketRotation.eligible_pool`` ranks one exchange's USD markets by
``quote_volume_24h``, keeps the top ``TOP_N_BY_VOLUME``, and asks
``ProjectAgeLookup`` for the six-month rule. ``open_window`` draws
``draw_size`` of that pool and posts only a salted ``merkle_root`` to the
``LocalTestnet`` it was built over, so the chain names no market until
``close_window`` publishes the set and its salt. ``reward_reason`` answers
``IN_ROTATION`` for a drawn market and names the refusal for every other.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Callable, Optional

from ..core.io_utils import atomic_write_json
from ..exchange.market_inspector_fetcher import STABLECOIN_DENYLIST
from ..exchange.market_pairs_scout import MarketPairsScout, PairSnapshot, get_scout
from .merkle_log import merkle_proof, merkle_root, verify_proof
from .project_age import ProjectAgeLookup

logger = logging.getLogger("acervator.market_rotation")

#: Markets at the top of an exchange's volume table that may reward at all.
TOP_N_BY_VOLUME = 20

#: Below this many eligible markets an exchange draws nothing that window.
MIN_ELIGIBLE_POOL = 12

#: The draw is one quarter of the eligible pool.
DRAW_DENOMINATOR = 4

#: The most of one market's pool a single participant may take.
MAX_PARTICIPANT_SHARE_PCT = Decimal("5")

USD_QUOTES = ("USD", "USDC", "USDT")

#: Seconds between two coin detail calls; CoinGecko refused 34 of 40 at 2.0.
AGE_LOOKUP_INTERVAL_S = 13.0

ROTATION_CONTRACT = "MarketRotation"
COMMIT_FUNCTION = "commitRotation"
REVEAL_FUNCTION = "revealRotation"
COMMITTED_EVENT = "RotationCommitted"
REVEALED_EVENT = "RotationRevealed"
ROTATION_SALT_BYTES = 16

DEFAULT_ROTATION_PATH = Path.home() / ".acervator" / "market_rotation.json"
ROTATION_FILE_VERSION = 1

ELIGIBLE = "eligible"
IN_ROTATION = "in_rotation"
OUTSIDE_TOP_VOLUME = "outside_top_volume"
EXCLUDED_BY_EXCHANGE = "excluded_by_exchange"
POOL_BELOW_FLOOR = "pool_below_floor"
NOT_DRAWN = "not_drawn"
NO_OPEN_WINDOW = "no_open_window"


class RotationRefusedError(RuntimeError):
    """Raised when no window may open, and when a concealed set may not be read."""


def quarter_rounded_up(pool_size: int) -> int:
    """Markets a quarter of ``pool_size`` draws, rounded up, never fewer than one."""
    if pool_size <= 0:
        return 0
    return max(1, -(-pool_size // DRAW_DENOMINATOR))


def draw_size(pool_size: int) -> int:
    """``quarter_rounded_up`` of ``pool_size``, and 0 below ``MIN_ELIGIBLE_POOL``."""
    if pool_size < MIN_ELIGIBLE_POOL:
        return 0
    return quarter_rounded_up(pool_size)


def max_participant_share(market_pool: Decimal) -> Decimal:
    """The most one participant takes of ``market_pool`` at the share ceiling."""
    return Decimal(market_pool) * MAX_PARTICIPANT_SHARE_PCT / Decimal(100)


def earners_to_exhaust() -> int:
    """Distinct participants a market pool needs before the share ceiling empties it."""
    whole = Decimal(100) / MAX_PARTICIPANT_SHARE_PCT
    return int(whole.to_integral_value(rounding=ROUND_CEILING))


def rotation_leaf(salt: str, symbol: str) -> str:
    """The Merkle leaf ``symbol`` takes under ``salt``, which the root does not name."""
    return hashlib.sha256(f"{salt}|{symbol}".encode()).hexdigest()


@dataclass(frozen=True)
class MarketEligibility:
    """One market's answer to the three eligibility conditions, and the ``reason``.

    ``volume_rank`` is 1 for the exchange's largest USD book and 0 for a market
    ``ranked_usd_markets`` does not hold.
    """

    exchange_id: str
    symbol: str
    base: str
    quote_volume_24h: float
    volume_rank: int
    in_top_volume: bool
    meets_age_rule: bool
    age_reason: str
    is_excluded: bool
    is_eligible: bool
    reason: str

    def to_dict(self) -> dict:
        """Return this row as a JSON-safe dict."""
        return {
            "exchange_id": self.exchange_id,
            "symbol": self.symbol,
            "base": self.base,
            "quote_volume_24h": self.quote_volume_24h,
            "volume_rank": self.volume_rank,
            "in_top_volume": self.in_top_volume,
            "meets_age_rule": self.meets_age_rule,
            "age_reason": self.age_reason,
            "is_excluded": self.is_excluded,
            "is_eligible": self.is_eligible,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EligiblePool:
    """The pool one exchange offers in one season, and what a window may draw.

    ``draw_size`` is 0 while ``pool_size`` sits below ``MIN_ELIGIBLE_POOL``.
    """

    exchange_id: str
    season: int
    markets: tuple[MarketEligibility, ...]
    eligible: tuple[str, ...]
    draw_size: int
    refusal_counts: dict
    age_calls: int

    @property
    def pool_size(self) -> int:
        """How many of ``markets`` passed all three conditions."""
        return len(self.eligible)

    def to_dict(self) -> dict:
        """Return this pool as a JSON-safe dict."""
        return {
            "exchange_id": self.exchange_id,
            "season": self.season,
            "markets": [m.to_dict() for m in self.markets],
            "eligible": list(self.eligible),
            "pool_size": self.pool_size,
            "draw_size": self.draw_size,
            "refusal_counts": dict(self.refusal_counts),
            "age_calls": self.age_calls,
        }


@dataclass(frozen=True)
class RotationWindow:
    """What the chain carries while a window is open: a commitment and two counts.

    ``commitment`` is the salted ``merkle_root`` of the drawn set, and no field
    here names a drawn market.
    """

    exchange_id: str
    season: int
    commitment: str
    market_count: int
    pool_size: int
    share_ceiling_pct: str
    min_earners_per_market: int
    commit_tx: str

    def to_dict(self) -> dict:
        """Return this window as a JSON-safe dict."""
        return {
            "exchange_id": self.exchange_id,
            "season": self.season,
            "commitment": self.commitment,
            "market_count": self.market_count,
            "pool_size": self.pool_size,
            "share_ceiling_pct": self.share_ceiling_pct,
            "min_earners_per_market": self.min_earners_per_market,
            "commit_tx": self.commit_tx,
        }


@dataclass(frozen=True)
class RotationReveal:
    """What ``close_window`` publishes: the drawn markets and the salt that hid them."""

    exchange_id: str
    season: int
    commitment: str
    salt: str
    markets: tuple[str, ...]
    reveal_tx: str

    def to_dict(self) -> dict:
        """Return this reveal as a JSON-safe dict."""
        return {
            "exchange_id": self.exchange_id,
            "season": self.season,
            "commitment": self.commitment,
            "salt": self.salt,
            "markets": list(self.markets),
            "reveal_tx": self.reveal_tx,
        }


class MarketRotation:
    """Draws the rewarding markets for one chain and conceals them until the close.

    The ``LocalTestnet`` and ``rotation_path`` arrive by construction, so a
    TestNet demo run is one rotation over a different chain running the same
    ``open_window`` path.
    """

    def __init__(
        self,
        testnet,
        age_lookup: Optional[ProjectAgeLookup] = None,
        rotation_path: str | Path | None = None,
        age_lookup_interval_s: float = AGE_LOOKUP_INTERVAL_S,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Hold the chain, the age lookup, the pacing and the record path."""
        self._testnet = testnet
        self._age_lookup = age_lookup if age_lookup is not None else ProjectAgeLookup()
        self._path: Path = (
            Path(rotation_path) if rotation_path else DEFAULT_ROTATION_PATH
        )
        self._age_lookup_interval_s = float(age_lookup_interval_s)
        self._sleep = sleep
        self._random = secrets.SystemRandom()
        self._windows: dict[str, RotationWindow] = {}
        self._drawn: dict[str, tuple[str, ...]] = {}
        self._salts: dict[str, str] = {}
        self._reveals: dict[str, RotationReveal] = {}
        self._exclusions: dict[str, dict[str, int]] = {}

    @property
    def rotation_path(self) -> Path:
        """The file ``save`` writes and ``load`` reads."""
        return self._path

    @property
    def age_lookup(self) -> ProjectAgeLookup:
        """The lookup ``eligible_pool`` asks the six-month rule of."""
        return self._age_lookup

    # -- The volume ranking --------------------------------------------------

    def ranked_usd_markets(
        self,
        exchange_id: str,
        scout: Optional[MarketPairsScout] = None,
    ) -> tuple[PairSnapshot, ...]:
        """``exchange_id``'s USD books, one a base, largest ``quote_volume_24h`` first.

        A base quoted against USD and USDC keeps its larger book only, and a pair
        whose ``quote_volume_24h`` is zero is dropped.
        """
        book = scout if scout is not None else get_scout()
        if book is None:
            return ()
        largest: dict[str, PairSnapshot] = {}
        for pair in book.pairs_on(exchange_id):
            if pair.quote not in USD_QUOTES or pair.base in STABLECOIN_DENYLIST:
                continue
            if pair.quote_volume_24h <= 0:
                continue
            held = largest.get(pair.base)
            if held is None or pair.quote_volume_24h > held.quote_volume_24h:
                largest[pair.base] = pair
        pairs = sorted(
            largest.values(), key=lambda pair: (-pair.quote_volume_24h, pair.symbol)
        )
        return tuple(pairs)

    # -- Exchange exclusion --------------------------------------------------

    def file_exclusion(
        self, exchange_id: str, symbol: str, filed_in_season: int
    ) -> int:
        """Record an exclusion of ``symbol`` and return the season it first binds.

        An exclusion filed inside a season binds at the next season boundary.
        """
        effective_from = int(filed_in_season) + 1
        filed = self._exclusions.setdefault(exchange_id, {})
        filed[symbol] = min(filed.get(symbol, effective_from), effective_from)
        logger.info(
            "%s excluded %s from season %d (filed in %d)",
            exchange_id,
            symbol,
            filed[symbol],
            filed_in_season,
        )
        return filed[symbol]

    def exclusions_in_effect(self, exchange_id: str, season: int) -> tuple[str, ...]:
        """The markets ``exchange_id`` excluded whose season boundary has passed."""
        filed = self._exclusions.get(exchange_id, {})
        return tuple(
            sorted(sym for sym, start in filed.items() if int(season) >= start)
        )

    # -- Eligibility ---------------------------------------------------------

    def eligible_pool(
        self,
        exchange_id: str,
        season: int,
        scout: Optional[MarketPairsScout] = None,
    ) -> EligiblePool:
        """Rank, keep the top ``TOP_N_BY_VOLUME``, and apply all three conditions.

        A market that cleared the rank and the exclusions is asked the age rule,
        and a detail call waits ``AGE_LOOKUP_INTERVAL_S`` behind the one before.
        """
        ranked = self.ranked_usd_markets(exchange_id, scout)
        excluded = set(self.exclusions_in_effect(exchange_id, season))
        rows: list[MarketEligibility] = []
        refusals: dict[str, int] = {}
        age_calls = 0
        for rank, pair in enumerate(ranked[:TOP_N_BY_VOLUME], start=1):
            if pair.symbol in excluded:
                rows.append(
                    self._refused_row(
                        exchange_id, pair, rank, EXCLUDED_BY_EXCHANGE, is_excluded=True
                    )
                )
                refusals[EXCLUDED_BY_EXCHANGE] = (
                    refusals.get(EXCLUDED_BY_EXCHANGE, 0) + 1
                )
                continue
            if not self._age_lookup.has_cached_answer(pair.symbol):
                if age_calls:
                    self._sleep(self._age_lookup_interval_s)
                age_calls += 1
            verdict = self._age_lookup.verdict_for(pair.symbol)
            reason = ELIGIBLE if verdict.meets_age_rule else verdict.reason
            if not verdict.meets_age_rule:
                refusals[verdict.reason] = refusals.get(verdict.reason, 0) + 1
            rows.append(
                MarketEligibility(
                    exchange_id=exchange_id,
                    symbol=pair.symbol,
                    base=pair.base,
                    quote_volume_24h=pair.quote_volume_24h,
                    volume_rank=rank,
                    in_top_volume=True,
                    meets_age_rule=verdict.meets_age_rule,
                    age_reason=verdict.reason,
                    is_excluded=False,
                    is_eligible=verdict.meets_age_rule,
                    reason=reason,
                )
            )
        eligible = tuple(row.symbol for row in rows if row.is_eligible)
        pool = EligiblePool(
            exchange_id=exchange_id,
            season=season,
            markets=tuple(rows),
            eligible=eligible,
            draw_size=draw_size(len(eligible)),
            refusal_counts=refusals,
            age_calls=age_calls,
        )
        logger.info(
            "%s season %d: %d ranked, %d eligible, draw %d, refusals %s",
            exchange_id,
            season,
            len(ranked),
            pool.pool_size,
            pool.draw_size,
            refusals,
        )
        return pool

    def _refused_row(
        self,
        exchange_id: str,
        pair: PairSnapshot,
        rank: int,
        reason: str,
        is_excluded: bool = False,
    ) -> MarketEligibility:
        """One row refused before the age rule was asked, carrying ``reason``."""
        return MarketEligibility(
            exchange_id=exchange_id,
            symbol=pair.symbol,
            base=pair.base,
            quote_volume_24h=pair.quote_volume_24h,
            volume_rank=rank,
            in_top_volume=rank <= TOP_N_BY_VOLUME,
            meets_age_rule=False,
            age_reason="",
            is_excluded=is_excluded,
            is_eligible=False,
            reason=reason,
        )

    def eligibility_of(
        self,
        exchange_id: str,
        symbol: str,
        season: int,
        scout: Optional[MarketPairsScout] = None,
    ) -> MarketEligibility:
        """One named market's eligibility, including a rank outside the top twenty."""
        ranked = self.ranked_usd_markets(exchange_id, scout)
        for rank, pair in enumerate(ranked, start=1):
            if pair.symbol != symbol:
                continue
            if rank > TOP_N_BY_VOLUME:
                return self._refused_row(exchange_id, pair, rank, OUTSIDE_TOP_VOLUME)
            if symbol in self.exclusions_in_effect(exchange_id, season):
                return self._refused_row(
                    exchange_id, pair, rank, EXCLUDED_BY_EXCHANGE, is_excluded=True
                )
            verdict = self._age_lookup.verdict_for(symbol)
            return MarketEligibility(
                exchange_id=exchange_id,
                symbol=symbol,
                base=pair.base,
                quote_volume_24h=pair.quote_volume_24h,
                volume_rank=rank,
                in_top_volume=True,
                meets_age_rule=verdict.meets_age_rule,
                age_reason=verdict.reason,
                is_excluded=False,
                is_eligible=verdict.meets_age_rule,
                reason=ELIGIBLE if verdict.meets_age_rule else verdict.reason,
            )
        return MarketEligibility(
            exchange_id=exchange_id,
            symbol=symbol,
            base=symbol.split("/")[0].upper(),
            quote_volume_24h=0.0,
            volume_rank=0,
            in_top_volume=False,
            meets_age_rule=False,
            age_reason="",
            is_excluded=False,
            is_eligible=False,
            reason=OUTSIDE_TOP_VOLUME,
        )

    # -- The window ----------------------------------------------------------

    def open_window(self, pool: EligiblePool) -> RotationWindow:
        """Draw ``pool.draw_size`` markets and post their salted root to the chain.

        Raises ``RotationRefusedError`` when the pool draws nothing, and while a
        window for that exchange is already open.
        """
        exchange_id = pool.exchange_id
        if exchange_id in self._windows:
            raise RotationRefusedError(
                f"a rotation window is already open on {exchange_id}"
            )
        if pool.draw_size <= 0:
            raise RotationRefusedError(
                f"{POOL_BELOW_FLOOR}: {exchange_id} holds {pool.pool_size} eligible "
                f"markets, under the floor of {MIN_ELIGIBLE_POOL}, so it draws nothing"
            )
        drawn = tuple(sorted(self._random.sample(list(pool.eligible), pool.draw_size)))
        salt = secrets.token_hex(ROTATION_SALT_BYTES)
        commitment = merkle_root([rotation_leaf(salt, sym) for sym in drawn])
        tx_hash = self._post_commitment(
            exchange_id, pool.season, commitment, len(drawn)
        )
        window = RotationWindow(
            exchange_id=exchange_id,
            season=pool.season,
            commitment=commitment,
            market_count=len(drawn),
            pool_size=pool.pool_size,
            share_ceiling_pct=str(MAX_PARTICIPANT_SHARE_PCT),
            min_earners_per_market=earners_to_exhaust(),
            commit_tx=tx_hash,
        )
        self._windows[exchange_id] = window
        self._drawn[exchange_id] = drawn
        self._salts[exchange_id] = salt
        self.save()
        logger.info(
            "%s season %d: committed %d of %d markets as %s",
            exchange_id,
            pool.season,
            len(drawn),
            pool.pool_size,
            commitment[:16],
        )
        return window

    def _post_commitment(
        self, exchange_id: str, season: int, commitment: str, market_count: int
    ) -> str:
        """Send the commitment to the chain and emit ``COMMITTED_EVENT``."""
        args = {
            "exchange": exchange_id,
            "season": int(season),
            "commitment": commitment,
            "marketCount": market_count,
        }
        chain = self._testnet.chain
        tx = chain.send_tx(exchange_id, ROTATION_CONTRACT, COMMIT_FUNCTION, args)
        chain.emit(tx.tx_hash, ROTATION_CONTRACT, COMMITTED_EVENT, args)
        return tx.tx_hash

    def close_window(self, exchange_id: str) -> RotationReveal:
        """Publish the drawn markets and the salt, and emit ``REVEALED_EVENT``.

        Raises ``RotationRefusedError`` when no window is open on ``exchange_id``.
        """
        window = self._windows.get(exchange_id)
        if window is None:
            raise RotationRefusedError(f"{NO_OPEN_WINDOW} on {exchange_id}")
        drawn = self._drawn[exchange_id]
        salt = self._salts[exchange_id]
        args = {
            "exchange": exchange_id,
            "season": window.season,
            "commitment": window.commitment,
            "salt": salt,
            "markets": list(drawn),
        }
        chain = self._testnet.chain
        tx = chain.send_tx(exchange_id, ROTATION_CONTRACT, REVEAL_FUNCTION, args)
        chain.emit(tx.tx_hash, ROTATION_CONTRACT, REVEALED_EVENT, args)
        reveal = RotationReveal(
            exchange_id=exchange_id,
            season=window.season,
            commitment=window.commitment,
            salt=salt,
            markets=drawn,
            reveal_tx=tx.tx_hash,
        )
        self._reveals[exchange_id] = reveal
        del self._windows[exchange_id]
        del self._drawn[exchange_id]
        del self._salts[exchange_id]
        self.save()
        logger.info(
            "%s season %d: revealed %s under %s",
            exchange_id,
            window.season,
            ", ".join(drawn),
            window.commitment[:16],
        )
        return reveal

    def open_window_for(self, exchange_id: str) -> Optional[RotationWindow]:
        """The window open on ``exchange_id``, or None while none is."""
        return self._windows.get(exchange_id)

    def reward_reason(self, exchange_id: str, symbol: str) -> str:
        """``IN_ROTATION`` while the open window drew ``symbol``, else the refusal.

        Reads the drawn set this process holds, which the chain does not carry
        until ``close_window`` runs.
        """
        if exchange_id not in self._windows:
            return NO_OPEN_WINDOW
        if symbol in self._drawn.get(exchange_id, ()):
            return IN_ROTATION
        return NOT_DRAWN

    def membership_proof(self, exchange_id: str, symbol: str) -> dict:
        """The leaf, proof and root showing ``symbol`` was drawn, after the close.

        Raises ``RotationRefusedError`` while the window is open, when a proof
        would name one of the markets the commitment conceals.
        """
        if exchange_id in self._windows:
            raise RotationRefusedError(
                f"{exchange_id} has an open window; a membership proof would "
                f"reveal the set it conceals"
            )
        reveal = self._reveals.get(exchange_id)
        if reveal is None or symbol not in reveal.markets:
            raise RotationRefusedError(
                f"no revealed rotation on {exchange_id} carries {symbol}"
            )
        leaves = [rotation_leaf(reveal.salt, sym) for sym in reveal.markets]
        index = reveal.markets.index(symbol)
        proof = merkle_proof(leaves, index)
        return {
            "symbol": symbol,
            "leaf_hash": leaves[index],
            "proof": proof,
            "root": reveal.commitment,
            "verified": verify_proof(leaves[index], proof, reveal.commitment),
        }

    # -- Persistence ---------------------------------------------------------

    def save(self) -> None:
        """Write the windows, the drawn sets, the salts and the exclusions to disk."""
        payload = {
            "version": ROTATION_FILE_VERSION,
            "windows": {k: v.to_dict() for k, v in self._windows.items()},
            "drawn": {k: list(v) for k, v in self._drawn.items()},
            "salts": dict(self._salts),
            "reveals": {k: v.to_dict() for k, v in self._reveals.items()},
            "exclusions": {k: dict(v) for k, v in self._exclusions.items()},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._path, payload, sort_keys=True)

    def load(self) -> "MarketRotation":
        """Fill the windows, drawn sets, salts and exclusions from ``rotation_path``."""
        try:
            with open(self._path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return self
        except (OSError, ValueError) as exc:
            logger.warning("rotation record %s unreadable: %s", self._path, exc)
            return self
        self._windows = {
            k: RotationWindow(**v) for k, v in payload.get("windows", {}).items()
        }
        self._drawn = {
            k: tuple(v)
            for k, v in payload.get("drawn", {}).items()
            if isinstance(v, list)
        }
        self._salts = dict(payload.get("salts", {}))
        self._reveals = {
            k: RotationReveal(
                exchange_id=v["exchange_id"],
                season=v["season"],
                commitment=v["commitment"],
                salt=v["salt"],
                markets=tuple(v.get("markets", [])),
                reveal_tx=v["reveal_tx"],
            )
            for k, v in payload.get("reveals", {}).items()
        }
        self._exclusions = {
            k: {sym: int(start) for sym, start in v.items()}
            for k, v in payload.get("exclusions", {}).items()
        }
        return self

    def rotation_summary(self) -> dict:
        """The open windows, the revealed sets and the filed exclusions, as a dict."""
        return {
            "rotation_path": str(self._path),
            "top_n_by_volume": TOP_N_BY_VOLUME,
            "min_eligible_pool": MIN_ELIGIBLE_POOL,
            "draw_denominator": DRAW_DENOMINATOR,
            "share_ceiling_pct": str(MAX_PARTICIPANT_SHARE_PCT),
            "min_earners_per_market": earners_to_exhaust(),
            "open_windows": {k: v.to_dict() for k, v in self._windows.items()},
            "revealed": {k: v.to_dict() for k, v in self._reveals.items()},
            "exclusions": {k: dict(v) for k, v in self._exclusions.items()},
        }
