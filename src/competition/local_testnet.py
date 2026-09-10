"""
local_testnet.py — In-Platform Testnet
=======================================
Full in-memory simulation of the Base blockchain environment.
No wallet, no ETH, no network required.

Simulates:
  • Block production (auto-mines every N calls or on demand)
  • ACRV ERC-20 token state (balances, supply, mint history)
  • CompetitionRegistry state (competitions, submissions, adjudications)
  • Chainlink oracle (configurable mock price)
  • Transaction receipts whose tx_hash is the sha256 of the transaction
  • Event emission and log

The LocalTestnet implements the exact same interface as BaseConnector
so the competition engine never needs to know which chain it's on.

Usage:
    from src.competition.local_testnet import LocalTestnet
    testnet = LocalTestnet()

    # Run a full competition lifecycle
    testnet.open_competition_onchain("COMP-001", "BTC/USDT", season=1)
    testnet.register_bot_onchain("COMP-001", "0xBot1", {}, 400.0)
    testnet.submit_result_onchain("COMP-001", merkle_root, 400.0, 529.0, 9)
    testnet.adjudicate_onchain(result, "0xBot1")
    print(testnet.get_balance("0xBot1"))   # → 10.0 ACRV
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from .competition_engine import CompetitionResult
from .season_schedule import TOTAL_SUPPLY_CAP

logger = logging.getLogger("acervator.local_testnet")

# ── Chain primitives ──────────────────────────────────────────────────────────

TOKEN_DECIMALS = 18
MAX_SUPPLY_WEI = TOTAL_SUPPLY_CAP * (10**TOKEN_DECIMALS)

#: The TxRecord.status of a transaction that was not reverted.
TX_SUCCESS = 1

#: Genesis holds no parent and no transaction, so its id is this constant.
GENESIS_BLOCK_ID = "0x" + "0" * 64

#: Decimal places a stored timestamp keeps, so an id covers the value on disk.
TIMESTAMP_DIGITS = 3

#: How many altered records verify_integrity names in one log line.
ALTERED_LOG_LIMIT = 5

#: Seed for the synthetic price walk run_demo_competition trades against.
DEMO_PRICE_SEED = 42


def canonical_json(payload: dict | list) -> str:
    """Return ``payload`` as the JSON text every node produces byte for byte."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_id(payload: dict) -> str:
    """Return the 0x-prefixed sha256 of ``payload``'s ``canonical_json``."""
    return "0x" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _tx_payload(
    from_addr: str,
    to_addr: str,
    function_name: str,
    args: dict,
    gas_used: int,
    timestamp: float,
    status: int,
) -> dict:
    """Return the fields both ``placement_id`` and ``transaction_id`` hash."""
    return {
        "from_addr": from_addr,
        "to_addr": to_addr,
        "function_name": function_name,
        "args": args,
        "gas_used": gas_used,
        "timestamp": timestamp,
        "status": status,
    }


def placement_id(
    from_addr: str,
    to_addr: str,
    function_name: str,
    args: dict,
    gas_used: int,
    timestamp: float,
    status: int = TX_SUCCESS,
) -> str:
    """Return the id of one placed action, equal on every node holding it.

    ``timestamp`` is the placing node's declared time and excludes
    ``block_position``, which ``LocalChain.mine`` assigns at the close.
    """
    return content_id(
        _tx_payload(
            from_addr, to_addr, function_name, args, gas_used, timestamp, status
        )
    )


def transaction_id(
    from_addr: str,
    to_addr: str,
    function_name: str,
    args: dict,
    gas_used: int,
    timestamp: float,
    block_position: int,
    status: int = TX_SUCCESS,
) -> str:
    """Return the stored id of one transaction at its ``block_position``.

    ``LocalChain.mine`` assigns ``block_position`` at the close, so two nodes
    closing the same actions name each of them by the same id.
    """
    payload = _tx_payload(
        from_addr, to_addr, function_name, args, gas_used, timestamp, status
    )
    payload["block_position"] = block_position
    return content_id(payload)


def block_id(
    number: int,
    parent_hash: str,
    timestamp: float,
    transactions: List[str],
) -> str:
    """Return the id of one block's contents, the parent's id among them."""
    return content_id(
        {
            "number": number,
            "parent_hash": parent_hash,
            "timestamp": timestamp,
            "transactions": list(transactions),
        }
    )


def _fake_addr(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return "0x" + h[:40]


@dataclass
class TxRecord:
    tx_hash: str
    block_number: int
    from_addr: str
    to_addr: str
    function_name: str
    args: dict
    status: int = TX_SUCCESS
    gas_used: int = 21_000
    timestamp: float = field(
        default_factory=lambda: round(time.time(), TIMESTAMP_DIGITS)
    )
    block_position: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def placement_id(self) -> str:
        """Return the ``placement_id`` of this record's action, position aside."""
        return placement_id(
            self.from_addr,
            self.to_addr,
            self.function_name,
            self.args,
            self.gas_used,
            self.timestamp,
            self.status,
        )

    def content_id(self) -> str:
        """Return the ``transaction_id`` this record's own fields produce."""
        return transaction_id(
            self.from_addr,
            self.to_addr,
            self.function_name,
            self.args,
            self.gas_used,
            self.timestamp,
            self.block_position,
            self.status,
        )


def block_order(txs: List[TxRecord]) -> List[TxRecord]:
    """Return ``txs`` in the order a closing block runs them.

    Sorts on ``timestamp`` then ``placement_id``, so arrival order decides
    nothing and two nodes holding the same actions order them alike.
    """
    return sorted(txs, key=lambda tx: (tx.timestamp, tx.placement_id()))


@dataclass
class Block:
    number: int
    hash: str
    parent_hash: str
    timestamp: float
    transactions: List[str] = field(default_factory=list)  # tx hashes

    def to_dict(self) -> dict:
        return asdict(self)

    def content_id(self) -> str:
        """Return the ``block_id`` this block's own fields produce."""
        return block_id(
            self.number,
            self.parent_hash,
            self.timestamp,
            self.transactions,
        )


@dataclass
class ChainEvent:
    block_number: int
    tx_hash: str
    contract: str
    event_name: str
    args: dict
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


# ── In-memory chain state ─────────────────────────────────────────────────────


class LocalChain:
    """Minimal in-memory EVM chain. Produces a new block per transaction group."""

    CHAIN_ID = 84532  # Matches Base Sepolia — useful for tooling
    CHAIN_NAME = "Acervator Local Testnet"

    def __init__(self):
        self._blocks: List[Block] = []
        self._txs: Dict[str, TxRecord] = {}
        self._placements: set[str] = set()
        self._events: List[ChainEvent] = []
        self._block_number: int = 0
        self._content_id_from_block: int = 0
        self._genesis()

    def _genesis(self):
        genesis = Block(
            number=0,
            hash=GENESIS_BLOCK_ID,
            parent_hash=GENESIS_BLOCK_ID,
            timestamp=round(time.time(), TIMESTAMP_DIGITS),
        )
        self._blocks.append(genesis)

    def mine(self, txs: Optional[List[TxRecord]] = None) -> Block:
        """Close a block over ``txs`` in ``block_order``, each at its own position.

        Every transaction takes its ``block_position`` and the ``transaction_id``
        of its contents there, and the block ``hash`` is its own ``block_id``.
        """
        self._block_number += 1
        parent = self._blocks[-1]
        tx_hashes = []
        for position, tx in enumerate(block_order(list(txs or []))):
            tx.block_number = self._block_number
            tx.block_position = position
            tx.tx_hash = tx.content_id()
            self._txs[tx.tx_hash] = tx
            self._placements.add(tx.placement_id())
            tx_hashes.append(tx.tx_hash)
        timestamp = round(time.time(), TIMESTAMP_DIGITS)
        block = Block(
            number=self._block_number,
            hash=block_id(self._block_number, parent.hash, timestamp, tx_hashes),
            parent_hash=parent.hash,
            timestamp=timestamp,
            transactions=tx_hashes,
        )
        self._blocks.append(block)
        logger.debug(
            "mined block %d %s over parent %s holding %d transactions",
            block.number,
            block.hash,
            block.parent_hash,
            len(tx_hashes),
        )
        return block

    def emit(self, tx_hash: str, contract: str, event_name: str, args: dict):
        self._events.append(
            ChainEvent(
                block_number=self._block_number,
                tx_hash=tx_hash,
                contract=contract,
                event_name=event_name,
                args=args,
            )
        )

    def send_tx(
        self,
        from_addr: str,
        to_addr: str,
        fn_name: str,
        args: dict,
        gas_used: int = 50_000,
    ) -> TxRecord:
        """Place one transaction and close a block over it through ``mine``.

        Raises ``ValueError`` when the chain already holds that ``placement_id``.
        """
        tx = TxRecord(
            tx_hash="",
            block_number=self._block_number + 1,
            from_addr=from_addr,
            to_addr=to_addr,
            function_name=fn_name,
            args=args,
            gas_used=gas_used,
        )
        placement = tx.placement_id()
        if placement in self._placements:
            already_held = (
                f"action {placement} calling {fn_name} is already on this chain"
            )
            raise ValueError(already_held)
        logger.debug("placing transaction %s calling %s", placement, fn_name)
        self.mine([tx])
        return tx

    def holds_placement(self, placement: str) -> bool:
        """Answer whether some transaction on this chain carries ``placement``."""
        return placement in self._placements

    def reindex_placements(self) -> None:
        """Rebuild ``_placements`` from the transactions ``_txs`` now holds."""
        self._placements = {tx.placement_id() for tx in self._txs.values()}

    def set_content_id_from_block(self, number: int) -> None:
        """Record the first block number whose stored ids derive from contents."""
        self._content_id_from_block = int(number)

    @property
    def content_id_from_block(self) -> int:
        """Read the first block number ``verify_integrity`` holds to its content id."""
        return self._content_id_from_block

    def verify_integrity(self) -> dict:
        """Report every block and transaction whose stored id is not its content id.

        A record below ``content_id_from_block`` is legacy rather than altered, and
        block 0 is read against ``GENESIS_BLOCK_ID``.
        """
        legacy_blocks = []
        altered_blocks = []
        for b in self._blocks:
            expected = GENESIS_BLOCK_ID if b.number == 0 else b.content_id()
            if b.hash == expected:
                continue
            if b.number < self._content_id_from_block:
                legacy_blocks.append(b.number)
            else:
                altered_blocks.append(b.number)
        broken_parents = [
            child.number
            for parent, child in zip(self._blocks, self._blocks[1:], strict=False)
            if child.parent_hash != parent.hash
        ]
        legacy_txs = []
        altered_txs = []
        for stored_id, tx in self._txs.items():
            if stored_id == tx.content_id():
                continue
            if tx.block_number < self._content_id_from_block:
                legacy_txs.append(stored_id)
            else:
                altered_txs.append(stored_id)
        report = {
            "blocks": len(self._blocks),
            "blocks_altered": altered_blocks,
            "blocks_legacy": len(legacy_blocks),
            "broken_parents": broken_parents,
            "transactions": len(self._txs),
            "transactions_altered": altered_txs,
            "transactions_legacy": len(legacy_txs),
            "content_ids_from_block": self._content_id_from_block,
            "is_verified": not (altered_blocks or broken_parents or altered_txs),
        }
        if legacy_blocks or legacy_txs:
            logger.info(
                "chain holds %d legacy blocks and %d legacy transactions: written "
                "before block %d, when ids began to derive from contents, so the "
                "chain keeps them and does not vouch for them",
                len(legacy_blocks),
                len(legacy_txs),
                self._content_id_from_block,
            )
        if report["is_verified"]:
            logger.info(
                "chain verified: %d blocks and %d transactions carry the id of "
                "their own contents",
                report["blocks"] - len(legacy_blocks),
                report["transactions"] - len(legacy_txs),
            )
        else:
            logger.warning(
                "chain NOT verified: %d of %d blocks altered %s, %d parent links "
                "broken %s, %d of %d transactions altered %s",
                len(altered_blocks),
                report["blocks"],
                altered_blocks[:ALTERED_LOG_LIMIT],
                len(broken_parents),
                broken_parents[:ALTERED_LOG_LIMIT],
                len(altered_txs),
                report["transactions"],
                [i[:18] for i in altered_txs[:ALTERED_LOG_LIMIT]],
            )
        return report

    @property
    def block_number(self) -> int:
        return self._block_number

    @property
    def latest_blocks(self) -> List[Block]:
        return list(reversed(self._blocks[-20:]))

    @property
    def latest_events(self) -> List[ChainEvent]:
        return list(reversed(self._events[-50:]))

    def get_tx(self, tx_hash: str) -> Optional[TxRecord]:
        return self._txs.get(tx_hash)


# ── ACRV token simulation ─────────────────────────────────────────────────────


class LocalACRV:
    """In-memory ACRV ERC-20 token."""

    ADDRESS = _fake_addr("ACRV_contract")

    def __init__(self, chain: LocalChain, registry_addr: str):
        self._chain = chain
        self._registry = registry_addr
        self._balances: Dict[str, int] = {}  # address → wei
        self._allowances: Dict[str, Dict[str, int]] = {}
        self._total_supply: int = 0
        self._mint_log: List[dict] = []
        # Every read and write of _balances and _total_supply holds this.
        self._supply_lock = threading.RLock()

    def mint(
        self,
        recipient: str,
        amount_wei: int,
        competition_id: str,
        tier_name: str,
        caller: str = "",
    ) -> TxRecord:
        """Mint tokens. Only registry can call."""
        if caller and caller != self._registry and caller != "owner":
            raise PermissionError("ACRV: caller is not the registry")
        if amount_wei <= 0:
            raise ValueError("ACRV: amount must be > 0")

        with self._supply_lock:
            if self._total_supply + amount_wei > MAX_SUPPLY_WEI:
                raise OverflowError("ACRV: mint would exceed MAX_SUPPLY")
            self._balances[recipient] = self._balances.get(recipient, 0) + amount_wei
            self._total_supply += amount_wei
            self._mint_log.append(
                {
                    "recipient": recipient,
                    "amount_tokens": amount_wei / 10**TOKEN_DECIMALS,
                    "competition": competition_id,
                    "tier": tier_name,
                    "block": self._chain.block_number,
                    "timestamp": time.time(),
                }
            )
            total_supply_after_tokens = self._total_supply / 10**TOKEN_DECIMALS

        tx = self._chain.send_tx(
            self._registry,
            self.ADDRESS,
            "mint",
            {
                "recipient": recipient,
                "amount": amount_wei,
                "competitionId": competition_id,
                "tierName": tier_name,
            },
            gas_used=65_000,
        )

        self._chain.emit(
            tx.tx_hash,
            self.ADDRESS,
            "TokensMinted",
            {
                "recipient": recipient,
                "amount": amount_wei / 10**TOKEN_DECIMALS,
                "competitionId": competition_id,
                "tierName": tier_name,
                "totalSupplyAfter": total_supply_after_tokens,
            },
        )
        return tx

    def balance_of(self, address: str) -> float:
        with self._supply_lock:
            return self._balances.get(address, 0) / 10**TOKEN_DECIMALS

    def total_supply(self) -> float:
        with self._supply_lock:
            return self._total_supply / 10**TOKEN_DECIMALS

    def remaining_supply(self) -> float:
        with self._supply_lock:
            return (MAX_SUPPLY_WEI - self._total_supply) / 10**TOKEN_DECIMALS

    def cap_reached(self) -> bool:
        with self._supply_lock:
            return self._total_supply >= MAX_SUPPLY_WEI

    def supply_summary(self) -> dict:
        with self._supply_lock:
            holders = {
                a: v / 10**TOKEN_DECIMALS for a, v in self._balances.items() if v > 0
            }
            tier_counts: Dict[str, int] = {}
            for m in self._mint_log:
                tier_counts[m["tier"]] = tier_counts.get(m["tier"], 0) + 1
            return {
                "total_cap": TOTAL_SUPPLY_CAP,
                "total_minted": self.total_supply(),
                "remaining": self.remaining_supply(),
                "pct_minted": self.total_supply() / TOTAL_SUPPLY_CAP * 100,
                "total_holders": len(holders),
                "tier_counts": tier_counts,
                "mint_history": self._mint_log[-20:],
            }


# ── CompetitionRegistry simulation ───────────────────────────────────────────


class LocalRegistry:
    """In-memory CompetitionRegistry contract simulation."""

    ADDRESS = _fake_addr("Registry_contract")

    def __init__(self, chain: LocalChain, acrv: LocalACRV):
        self._chain = chain
        self._acrv = acrv
        self._comps: Dict[str, dict] = {}
        self._entries: Dict[str, Dict[str, dict]] = {}
        self._subs: Dict[str, Dict[str, dict]] = {}
        self._prices: Dict[str, float] = {
            "BTC/USDT": 62_000.0,
            "ETH/USDT": 3_200.0,
        }
        self._ekthelius_minted = 0
        self._grand_acc_minted = 0
        self._current_season = 1
        self._winners: Dict[str, str] = {}
        self._tiers: Dict[str, str] = {}

    def set_mock_price(self, symbol: str, price: float):
        self._prices[symbol] = price

    def get_latest_price(self, symbol: str) -> tuple[float, float]:
        p = self._prices.get(symbol)
        if p is None:
            raise ValueError(f"No mock price for {symbol}")
        return p, time.time()

    def open_competition(
        self, comp_id: str, symbol: str, season: int, owner: str
    ) -> TxRecord:
        if comp_id in self._comps:
            raise ValueError(f"Competition {comp_id} already exists")
        self._comps[comp_id] = {
            "id": comp_id,
            "symbol": symbol,
            "season": season,
            "status": "REGISTRATION",
            "opened_at": time.time(),
            "participants": [],
            "market_regime": "ANY",
        }
        self._entries[comp_id] = {}
        self._subs[comp_id] = {}
        tx = self._chain.send_tx(
            owner,
            self.ADDRESS,
            "openCompetition",
            {"id": comp_id, "symbol": symbol, "season": season},
        )
        self._chain.emit(
            tx.tx_hash,
            self.ADDRESS,
            "CompetitionOpened",
            {"id": comp_id, "symbol": symbol, "season": season},
        )
        return tx

    def register_bot(
        self, comp_id: str, wallet: str, config_hash: bytes, capital_cents: int
    ) -> TxRecord:
        c = self._require_comp(comp_id, "REGISTRATION")
        if wallet in self._entries[comp_id]:
            raise ValueError("Already registered")
        self._entries[comp_id][wallet] = {
            "wallet": wallet,
            "config_hash": config_hash.hex(),
            "capital": capital_cents / 100,
            "registered": True,
        }
        c["participants"].append(wallet)
        tx = self._chain.send_tx(
            wallet,
            self.ADDRESS,
            "registerBot",
            {"compId": comp_id, "wallet": wallet[:10]},
        )
        self._chain.emit(
            tx.tx_hash,
            self.ADDRESS,
            "BotRegistered",
            {"compId": comp_id, "wallet": wallet},
        )
        return tx

    def activate(self, comp_id: str, owner: str) -> TxRecord:
        c = self._require_comp(comp_id, "REGISTRATION")
        if len(c["participants"]) < 2:
            raise ValueError("Need ≥ 2 participants")
        c["status"] = "ACTIVE"
        return self._chain.send_tx(
            owner, self.ADDRESS, "activateCompetition", {"compId": comp_id}
        )

    def close_for_submission(self, comp_id: str, regime: str, owner: str) -> TxRecord:
        c = self._require_comp(comp_id, "ACTIVE")
        c["status"] = "SUBMISSION"
        c["market_regime"] = regime
        c["closed_at"] = time.time()
        return self._chain.send_tx(
            owner,
            self.ADDRESS,
            "closeForSubmission",
            {"compId": comp_id, "regime": regime},
        )

    def submit_result(
        self,
        comp_id: str,
        wallet: str,
        merkle_root: bytes,
        start_cents: int,
        final_cents: int,
        trade_count: int,
    ) -> TxRecord:
        # sadp: R28 R29 R33  # R29 idempotent: _subs[comp_id] guards duplicate submissions
        self._require_comp(comp_id, "SUBMISSION")
        if wallet not in self._entries[comp_id]:
            raise ValueError(f"Bot {wallet[:10]} not registered")
        if wallet in self._subs[comp_id]:
            raise ValueError("Already submitted")
        if trade_count <= 0:
            raise ValueError("No trades recorded")
        adv_cents = final_cents - start_cents
        adv_bps = int(adv_cents * 10000 / max(start_cents, 1))
        self._subs[comp_id][wallet] = {
            "merkle_root": merkle_root.hex(),
            "start": start_cents / 100,
            "final": final_cents / 100,
            "advantage": adv_cents / 100,
            "adv_bps": adv_bps,
            "trades": trade_count,
            "submitted": True,
            "at": time.time(),
        }
        tx = self._chain.send_tx(
            wallet,
            self.ADDRESS,
            "submitResult",
            {
                "compId": comp_id,
                "merkleRoot": merkle_root.hex()[:16],
                "advantageBps": adv_bps,
                "trades": trade_count,
            },
        )
        self._chain.emit(
            tx.tx_hash,
            self.ADDRESS,
            "ResultSubmitted",
            {"compId": comp_id, "wallet": wallet, "advantageBps": adv_bps},
        )
        return tx

    def adjudicate(
        self,
        comp_id: str,
        winner: str,
        tier_name: str,
        token_amount_wei: int,
        owner: str,
    ) -> TxRecord:
        c = self._require_comp(comp_id, "SUBMISSION")
        # Tier supply caps
        if tier_name == "Ekthelius":
            if self._ekthelius_minted >= 21:
                raise OverflowError("Ekthelius supply of 21 exhausted")
            self._ekthelius_minted += 1
        elif tier_name == "Grand Accumulator":
            if self._grand_acc_minted >= 1000:
                raise OverflowError("Grand Accumulator supply of 1,000 exhausted")
            self._grand_acc_minted += 1
        # Mint
        if token_amount_wei > 0:
            self._acrv.mint(
                winner, token_amount_wei, comp_id, tier_name, caller="owner"
            )
        c["status"] = "ADJUDICATED"
        c["adjudicated_at"] = time.time()
        self._winners[comp_id] = winner
        self._tiers[comp_id] = tier_name
        tx = self._chain.send_tx(
            owner,
            self.ADDRESS,
            "adjudicate",
            {
                "compId": comp_id,
                "winner": winner[:10],
                "tier": tier_name,
                "tokens": token_amount_wei / 10**TOKEN_DECIMALS,
            },
        )
        self._chain.emit(
            tx.tx_hash,
            self.ADDRESS,
            "Adjudicated",
            {
                "compId": comp_id,
                "winner": winner,
                "tier": tier_name,
                "tokensAwarded": token_amount_wei / 10**TOKEN_DECIMALS,
                "season": c["season"],
            },
        )
        return tx

    def total_competitions(self) -> int:
        return len(self._comps)

    def _require_comp(self, comp_id: str, status: str) -> dict:
        c = self._comps.get(comp_id)
        if not c:
            raise ValueError(f"Competition {comp_id!r} not found")
        if c["status"] != status:
            raise ValueError(
                f"Competition {comp_id} is {c['status']}, expected {status}"
            )
        return c


# ── Testnet facade (matches BaseConnector interface) ─────────────────────────


class LocalTestnet:
    """
    Drop-in replacement for BaseConnector.
    All BaseConnector methods are implemented here with full state tracking.
    No network. No private key. No ETH.
    """

    OWNER = "0xAcervatorOwner"

    def __init__(self, persist_path: Optional[str] = None):
        self._chain = LocalChain()
        self._acrv = LocalACRV(self._chain, LocalRegistry.ADDRESS)
        self._registry = LocalRegistry(self._chain, self._acrv)
        self._path = Path(persist_path) if persist_path else None
        self._connected = True

    @property
    def is_connected(self) -> bool:
        return True

    def explorer_url(self) -> str:
        return "local://testnet"

    # ── Competition lifecycle (mirrors BaseConnector) ─────────────────────────

    def open_competition_onchain(self, comp_id: str, symbol: str, season: int) -> str:
        tx = self._registry.open_competition(comp_id, symbol, season, self.OWNER)
        return tx.tx_hash

    def register_bot_onchain(
        self, comp_id: str, wallet: str, config: dict, capital_usd: float
    ) -> str:
        config_hash = bytes.fromhex(
            hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        )
        tx = self._registry.register_bot(
            comp_id, wallet, config_hash, int(capital_usd * 100)
        )
        return tx.tx_hash

    def activate_competition_onchain(self, comp_id: str) -> str:
        tx = self._registry.activate(comp_id, self.OWNER)
        return tx.tx_hash

    def close_for_submission_onchain(self, comp_id: str, regime: str = "ANY") -> str:
        tx = self._registry.close_for_submission(comp_id, regime, self.OWNER)
        return tx.tx_hash

    def submit_result_onchain(
        self,
        comp_id: str,
        merkle_root: str,
        start_value_usd: float,
        final_value_usd: float,
        trade_count: int,
        wallet: Optional[str] = None,
    ) -> str:
        # sadp: R28 R29  # fail-loudly(R28) idempotent-via-already-submitted-check(R29)
        # R29 idempotent: LocalRegistry.submit_result raises ValueError if already submitted (_seen via _subs dict)
        w = wallet or _fake_addr(comp_id + "bot")
        root = bytes.fromhex(merkle_root.lstrip("0x").ljust(64, "0"))
        tx = self._registry.submit_result(
            comp_id,
            w,
            root,
            int(start_value_usd * 100),
            int(final_value_usd * 100),
            trade_count,
        )
        return tx.tx_hash

    def adjudicate_onchain(self, result: CompetitionResult, winner_wallet: str) -> str:
        amount_wei = int(result.winner_token_award * (10**TOKEN_DECIMALS))
        # Close submission phase first if still open
        comp = self._registry._comps.get(result.competition_id, {})
        if comp.get("status") == "ACTIVE":
            self._registry.close_for_submission(
                result.competition_id, result.market_regime, self.OWNER
            )
        tx = self._registry.adjudicate(
            result.competition_id,
            winner_wallet,
            result.winner_tier,
            amount_wei,
            self.OWNER,
        )
        return tx.tx_hash

    # ── Token queries ─────────────────────────────────────────────────────────

    def get_balance(self, wallet: str) -> float:
        return self._acrv.balance_of(wallet)

    def get_total_supply(self) -> float:
        return self._acrv.total_supply()

    def get_remaining_supply(self) -> float:
        return self._acrv.remaining_supply()

    def get_latest_price(self, symbol: str) -> Optional[float]:
        try:
            price, _ = self._registry.get_latest_price(symbol)
            return price
        except Exception:
            return None

    def set_mock_price(self, symbol: str, price: float):
        """Set the Chainlink oracle mock price for testing."""
        self._registry.set_mock_price(symbol, price)

    def get_competition_stats(self) -> dict:
        s = self._acrv.supply_summary()
        return {
            "network": f"{LocalChain.CHAIN_NAME}",
            "chain_id": LocalChain.CHAIN_ID,
            "block_number": self._chain.block_number,
            "total_transactions": len(self._chain._txs),
            "total_events": len(self._chain._events),
            "total_competitions": self._registry.total_competitions(),
            "current_season": self._registry._current_season,
            "remaining_ekthelius": 21 - self._registry._ekthelius_minted,
            "remaining_grand_acc": 1000 - self._registry._grand_acc_minted,
            "acrv_total_supply": s["total_minted"],
            "acrv_remaining": s["remaining"],
            "acrv_pct_minted": s["pct_minted"],
            "total_holders": s["total_holders"],
            "tier_counts": s["tier_counts"],
        }

    def tx_url(self, tx_hash: str) -> str:
        return f"local://tx/{tx_hash}"

    def verify_integrity(self) -> dict:
        """Return ``LocalChain.verify_integrity`` for the chain this testnet holds."""
        return self._chain.verify_integrity()

    # ── Chain data for block explorer UI ─────────────────────────────────────

    @property
    def chain(self) -> LocalChain:
        return self._chain

    @property
    def acrv(self) -> LocalACRV:
        return self._acrv

    @property
    def registry(self) -> LocalRegistry:
        return self._registry

    # ── Run a complete competition in one call ────────────────────────────────

    def run_demo_competition(
        self, n_bots: int = 3, season: int = 1, symbol: str = "BTC/USDT"
    ) -> dict:
        """
        Run a complete competition end-to-end on the local testnet.
        Returns a summary dict with tx hashes, winner, and token award.
        """
        from numpy.random import default_rng
        from .competition_engine import CompetitionEngine
        from .bot_identity import BotIdentity
        from .token_ledger import TokenLedger
        import tempfile, os

        # Create temp identities
        tmpdir = tempfile.mkdtemp()
        bots = [
            BotIdentity(os.path.join(tmpdir, f"bot{i}.json")).generate()
            for i in range(n_bots)
        ]
        wallets = [_fake_addr(b.bot_id) for b in bots]

        # Local ledger for off-chain accounting
        ledger = TokenLedger(os.path.join(tmpdir, "ledger.json"))
        engine = CompetitionEngine(season=season, symbol=symbol, ledger=ledger)
        comp_id = engine.competition_id

        # On-chain: open competition
        self.open_competition_onchain(comp_id, symbol, season)

        # Register + on-chain register
        for bot, wallet in zip(bots, wallets):
            engine.register_bot(bot, capital_usd=400.0)
            self.register_bot_onchain(comp_id, wallet, {}, 400.0)

        # Activate
        self.activate_competition_onchain(comp_id)
        engine.open()

        # Simulate trades on shared price feed
        rng = default_rng(DEMO_PRICE_SEED)
        prices = [62000.0]
        for _ in range(119):
            step = float(rng.normal(0, 0.022))
            prices.append(max(1.0, prices[-1] * (1 + step + 0.0008)))

        intervals = [0.02 + i * 0.01 for i in range(n_bots)]
        finals = []

        for bot, interval in zip(bots, intervals):
            h = 400.0 / prices[0]
            u = 0.0
            t = 400.0
            fq = 0.0
            fr = 0.0
            for price in prices:
                v = h * price
                d = v - t
                if d > t * interval and fq < 0.01:
                    sq = d * 0.9 / price
                    net = sq * price * 0.999
                    h -= sq
                    u += net
                    fq = net
                    fr = price
                    engine.record_trade(
                        bot, "sell", sq, price, role="SCRUM", skip_sig=True
                    )
                elif fq > 0.01 and price < fr * 0.995 and u >= fq:
                    qty = fq * 0.999 / price
                    h += qty
                    u -= fq
                    fq = 0.0
                    engine.record_trade(
                        bot, "buy", qty, price, role="FOLD", skip_sig=True
                    )
            finals.append(h * prices[-1] + u + fq)

        # Close and submit
        engine.close()
        self.close_for_submission_onchain(comp_id)

        sub_txs = []
        for bot, wallet, final in zip(bots, wallets, finals):
            engine.submit(bot.bot_id, 400.0, final)
            tx = self.submit_result_onchain(
                comp_id,
                engine._logs[bot.bot_id].root,
                400.0,
                final,
                engine._logs[bot.bot_id].size,
                wallet=wallet,
            )
            sub_txs.append(tx)

        # Adjudicate
        result = engine.adjudicate()
        win_idx = [b.bot_id for b in bots].index(result.winner_bot_id)
        win_addr = wallets[win_idx]
        adj_tx = self.adjudicate_onchain(result, win_addr)

        return {
            "competition_id": comp_id,
            "winner_wallet": win_addr,
            "winner_tier": result.winner_tier,
            "tokens_awarded": result.winner_token_award,
            "winner_balance": self.get_balance(win_addr),
            "adj_tx_hash": adj_tx,
            "sub_tx_hashes": sub_txs,
            "block_number": self._chain.block_number,
            "results_table": engine.results_table(),
        }
