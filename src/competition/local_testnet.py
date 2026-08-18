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
  • Transaction receipts with realistic-looking hashes
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
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

from .competition_engine import CompetitionResult
from .season_schedule    import TOTAL_SUPPLY_CAP, season_reward

# ── Chain primitives ──────────────────────────────────────────────────────────

TOKEN_DECIMALS = 18
MAX_SUPPLY_WEI = TOTAL_SUPPLY_CAP * (10 ** TOKEN_DECIMALS)


def _fake_hash(seed: str = "") -> str:
    raw = f"{seed}{time.time_ns()}{uuid.uuid4()}"
    return "0x" + hashlib.sha256(raw.encode()).hexdigest()


def _fake_addr(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return "0x" + h[:40]


@dataclass
class TxRecord:
    tx_hash:       str
    block_number:  int
    from_addr:     str
    to_addr:       str
    function_name: str
    args:          dict
    status:        int       = 1    # 1 = success, 0 = reverted
    gas_used:      int       = 21_000
    timestamp:     float     = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Block:
    number:       int
    hash:         str
    parent_hash:  str
    timestamp:    float
    transactions: List[str] = field(default_factory=list)    # tx hashes

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChainEvent:
    block_number:  int
    tx_hash:       str
    contract:      str
    event_name:    str
    args:          dict
    timestamp:     float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


# ── In-memory chain state ─────────────────────────────────────────────────────

class LocalChain:
    """Minimal in-memory EVM chain. Produces a new block per transaction group."""

    CHAIN_ID  = 84532       # Matches Base Sepolia — useful for tooling
    CHAIN_NAME = "Acervator Local Testnet"

    def __init__(self):
        self._blocks:       List[Block]              = []
        self._txs:          Dict[str, TxRecord]      = {}
        self._events:       List[ChainEvent]         = []
        self._block_number: int                      = 0
        self._genesis()

    def _genesis(self):
        genesis = Block(
            number      = 0,
            hash        = "0x" + "0" * 64,
            parent_hash = "0x" + "0" * 64,
            timestamp   = time.time(),
        )
        self._blocks.append(genesis)

    def mine(self, txs: Optional[List[TxRecord]] = None) -> Block:
        """Mine a new block, optionally including transactions."""
        self._block_number += 1
        parent = self._blocks[-1]
        tx_hashes = []
        if txs:
            for tx in txs:
                tx.block_number = self._block_number
                self._txs[tx.tx_hash] = tx
                tx_hashes.append(tx.tx_hash)
        block = Block(
            number       = self._block_number,
            hash         = _fake_hash(f"block{self._block_number}"),
            parent_hash  = parent.hash,
            timestamp    = time.time(),
            transactions = tx_hashes,
        )
        self._blocks.append(block)
        return block

    def emit(self, tx_hash: str, contract: str, event_name: str, args: dict):
        self._events.append(ChainEvent(
            block_number = self._block_number,
            tx_hash      = tx_hash,
            contract     = contract,
            event_name   = event_name,
            args         = args,
        ))

    def send_tx(self, from_addr: str, to_addr: str,
                fn_name: str, args: dict,
                gas_used: int = 50_000) -> TxRecord:
        """Record a transaction and mine it into a block."""
        tx = TxRecord(
            tx_hash      = _fake_hash(fn_name),
            block_number = self._block_number + 1,
            from_addr    = from_addr,
            to_addr      = to_addr,
            function_name = fn_name,
            args          = args,
            gas_used      = gas_used,
        )
        self.mine([tx])
        return tx

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
        self._chain      = chain
        self._registry   = registry_addr
        self._balances:  Dict[str, int]  = {}   # address → wei
        self._allowances: Dict[str, Dict[str, int]] = {}
        self._total_supply: int          = 0
        self._mint_log:  List[dict]      = []

    def mint(self, recipient: str, amount_wei: int,
             competition_id: str, tier_name: str,
             caller: str = "") -> TxRecord:
        """Mint tokens. Only registry can call."""
        if caller and caller != self._registry and caller != "owner":
            raise PermissionError("ACRV: caller is not the registry")
        if self._total_supply + amount_wei > MAX_SUPPLY_WEI:
            raise OverflowError("ACRV: mint would exceed MAX_SUPPLY")
        if amount_wei <= 0:
            raise ValueError("ACRV: amount must be > 0")

        self._balances[recipient] = (
            self._balances.get(recipient, 0) + amount_wei)
        self._total_supply += amount_wei
        self._mint_log.append({
            "recipient":     recipient,
            "amount_tokens": amount_wei / 10**TOKEN_DECIMALS,
            "competition":   competition_id,
            "tier":          tier_name,
            "block":         self._chain.block_number,
            "timestamp":     time.time(),
        })

        tx = self._chain.send_tx(
            self._registry, self.ADDRESS, "mint",
            {"recipient": recipient, "amount": amount_wei,
             "competitionId": competition_id, "tierName": tier_name},
            gas_used=65_000)

        self._chain.emit(tx.tx_hash, self.ADDRESS, "TokensMinted", {
            "recipient":        recipient,
            "amount":           amount_wei / 10**TOKEN_DECIMALS,
            "competitionId":    competition_id,
            "tierName":         tier_name,
            "totalSupplyAfter": self._total_supply / 10**TOKEN_DECIMALS,
        })
        return tx

    def balance_of(self, address: str) -> float:
        return self._balances.get(address, 0) / 10**TOKEN_DECIMALS

    def total_supply(self) -> float:
        return self._total_supply / 10**TOKEN_DECIMALS

    def remaining_supply(self) -> float:
        return (MAX_SUPPLY_WEI - self._total_supply) / 10**TOKEN_DECIMALS

    def cap_reached(self) -> bool:
        return self._total_supply >= MAX_SUPPLY_WEI

    def supply_summary(self) -> dict:
        holders = {a: v/10**TOKEN_DECIMALS
                   for a, v in self._balances.items() if v > 0}
        tier_counts: Dict[str, int] = {}
        for m in self._mint_log:
            tier_counts[m["tier"]] = tier_counts.get(m["tier"], 0) + 1
        return {
            "total_cap":     TOTAL_SUPPLY_CAP,
            "total_minted":  self.total_supply(),
            "remaining":     self.remaining_supply(),
            "pct_minted":    self.total_supply() / TOTAL_SUPPLY_CAP * 100,
            "total_holders": len(holders),
            "tier_counts":   tier_counts,
            "mint_history":  self._mint_log[-20:],
        }


# ── CompetitionRegistry simulation ───────────────────────────────────────────

class LocalRegistry:
    """In-memory CompetitionRegistry contract simulation."""

    ADDRESS = _fake_addr("Registry_contract")

    def __init__(self, chain: LocalChain, acrv: LocalACRV):
        self._chain      = chain
        self._acrv       = acrv
        self._comps:     Dict[str, dict]            = {}
        self._entries:   Dict[str, Dict[str, dict]] = {}
        self._subs:      Dict[str, Dict[str, dict]] = {}
        self._prices:    Dict[str, float]           = {
            "BTC/USDT": 62_000.0,
            "ETH/USDT": 3_200.0,
        }
        self._ekthelius_minted    = 0
        self._grand_acc_minted    = 0
        self._current_season      = 1
        self._winners:   Dict[str, str]  = {}
        self._tiers:     Dict[str, str]  = {}

    def set_mock_price(self, symbol: str, price: float):
        self._prices[symbol] = price

    def get_latest_price(self, symbol: str) -> tuple[float, float]:
        p = self._prices.get(symbol)
        if p is None:
            raise ValueError(f"No mock price for {symbol}")
        return p, time.time()

    def open_competition(self, comp_id: str, symbol: str,
                         season: int, owner: str) -> TxRecord:
        if comp_id in self._comps:
            raise ValueError(f"Competition {comp_id} already exists")
        self._comps[comp_id] = {
            "id": comp_id, "symbol": symbol, "season": season,
            "status": "REGISTRATION", "opened_at": time.time(),
            "participants": [], "market_regime": "ANY",
        }
        self._entries[comp_id] = {}
        self._subs[comp_id]    = {}
        tx = self._chain.send_tx(owner, self.ADDRESS, "openCompetition",
                                 {"id": comp_id, "symbol": symbol,
                                  "season": season})
        self._chain.emit(tx.tx_hash, self.ADDRESS, "CompetitionOpened",
                         {"id": comp_id, "symbol": symbol, "season": season})
        return tx

    def register_bot(self, comp_id: str, wallet: str,
                     config_hash: bytes, capital_cents: int) -> TxRecord:
        c = self._require_comp(comp_id, "REGISTRATION")
        if wallet in self._entries[comp_id]:
            raise ValueError("Already registered")
        self._entries[comp_id][wallet] = {
            "wallet": wallet, "config_hash": config_hash.hex(),
            "capital": capital_cents / 100, "registered": True,
        }
        c["participants"].append(wallet)
        tx = self._chain.send_tx(wallet, self.ADDRESS, "registerBot",
                                 {"compId": comp_id, "wallet": wallet[:10]})
        self._chain.emit(tx.tx_hash, self.ADDRESS, "BotRegistered",
                         {"compId": comp_id, "wallet": wallet})
        return tx

    def activate(self, comp_id: str, owner: str) -> TxRecord:
        c = self._require_comp(comp_id, "REGISTRATION")
        if len(c["participants"]) < 2:
            raise ValueError("Need ≥ 2 participants")
        c["status"] = "ACTIVE"
        return self._chain.send_tx(owner, self.ADDRESS, "activateCompetition",
                                   {"compId": comp_id})

    def close_for_submission(self, comp_id: str, regime: str,
                             owner: str) -> TxRecord:
        c = self._require_comp(comp_id, "ACTIVE")
        c["status"] = "SUBMISSION"
        c["market_regime"] = regime
        c["closed_at"] = time.time()
        return self._chain.send_tx(owner, self.ADDRESS, "closeForSubmission",
                                   {"compId": comp_id, "regime": regime})

    def submit_result(self, comp_id: str, wallet: str,
                      merkle_root: bytes, start_cents: int,
                      final_cents: int, trade_count: int) -> TxRecord:
        # sadp: R28 R29 R33  # R29 idempotent: _subs[comp_id] guards duplicate submissions
        c = self._require_comp(comp_id, "SUBMISSION")
        if wallet not in self._entries[comp_id]:
            raise ValueError(f"Bot {wallet[:10]} not registered")
        if wallet in self._subs[comp_id]:
            raise ValueError("Already submitted")
        if trade_count <= 0:
            raise ValueError("No trades recorded")
        adv_cents = final_cents - start_cents
        adv_bps   = int(adv_cents * 10000 / max(start_cents, 1))
        self._subs[comp_id][wallet] = {
            "merkle_root": merkle_root.hex(),
            "start":       start_cents / 100,
            "final":       final_cents / 100,
            "advantage":   adv_cents / 100,
            "adv_bps":     adv_bps,
            "trades":      trade_count,
            "submitted":   True,
            "at":          time.time(),
        }
        tx = self._chain.send_tx(wallet, self.ADDRESS, "submitResult",
                                 {"compId": comp_id,
                                  "merkleRoot": merkle_root.hex()[:16],
                                  "advantageBps": adv_bps,
                                  "trades": trade_count})
        self._chain.emit(tx.tx_hash, self.ADDRESS, "ResultSubmitted",
                         {"compId": comp_id, "wallet": wallet,
                          "advantageBps": adv_bps})
        return tx

    def adjudicate(self, comp_id: str, winner: str, tier_name: str,
                   token_amount_wei: int, owner: str) -> TxRecord:
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
            self._acrv.mint(winner, token_amount_wei, comp_id,
                            tier_name, caller="owner")
        c["status"] = "ADJUDICATED"
        c["adjudicated_at"] = time.time()
        self._winners[comp_id] = winner
        self._tiers[comp_id]   = tier_name
        tx = self._chain.send_tx(owner, self.ADDRESS, "adjudicate",
                                 {"compId": comp_id, "winner": winner[:10],
                                  "tier": tier_name,
                                  "tokens": token_amount_wei / 10**TOKEN_DECIMALS})
        self._chain.emit(tx.tx_hash, self.ADDRESS, "Adjudicated",
                         {"compId": comp_id, "winner": winner,
                          "tier": tier_name,
                          "tokensAwarded": token_amount_wei / 10**TOKEN_DECIMALS,
                          "season": c["season"]})
        return tx

    def total_competitions(self) -> int:
        return len(self._comps)

    def _require_comp(self, comp_id: str, status: str) -> dict:
        c = self._comps.get(comp_id)
        if not c:
            raise ValueError(f"Competition {comp_id!r} not found")
        if c["status"] != status:
            raise ValueError(
                f"Competition {comp_id} is {c['status']}, expected {status}")
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
        self._chain    = LocalChain()
        self._acrv     = LocalACRV(self._chain, LocalRegistry.ADDRESS)
        self._registry = LocalRegistry(self._chain, self._acrv)
        self._path     = Path(persist_path) if persist_path else None
        self._connected = True

    @property
    def is_connected(self) -> bool:
        return True

    def explorer_url(self) -> str:
        return "local://testnet"

    # ── Competition lifecycle (mirrors BaseConnector) ─────────────────────────

    def open_competition_onchain(self, comp_id: str, symbol: str,
                                 season: int) -> str:
        tx = self._registry.open_competition(comp_id, symbol, season, self.OWNER)
        return tx.tx_hash

    def register_bot_onchain(self, comp_id: str, wallet: str,
                             config: dict, capital_usd: float) -> str:
        import json, hashlib
        config_hash = bytes.fromhex(
            hashlib.sha256(
                json.dumps(config, sort_keys=True).encode()
            ).hexdigest()
        )
        tx = self._registry.register_bot(
            comp_id, wallet, config_hash, int(capital_usd * 100))
        return tx.tx_hash

    def activate_competition_onchain(self, comp_id: str) -> str:
        tx = self._registry.activate(comp_id, self.OWNER)
        return tx.tx_hash

    def close_for_submission_onchain(self, comp_id: str,
                                     regime: str = "ANY") -> str:
        tx = self._registry.close_for_submission(comp_id, regime, self.OWNER)
        return tx.tx_hash

    def submit_result_onchain(self, comp_id: str, merkle_root: str,
                              start_value_usd: float, final_value_usd: float,
                              trade_count: int,
                              wallet: Optional[str] = None) -> str:
        # sadp: R28 R29  # fail-loudly(R28) idempotent-via-already-submitted-check(R29)
        # R29 idempotent: LocalRegistry.submit_result raises ValueError if already submitted (_seen via _subs dict)
        w    = wallet or _fake_addr(comp_id + "bot")
        root = bytes.fromhex(merkle_root.lstrip("0x").ljust(64, "0"))
        tx   = self._registry.submit_result(
            comp_id, w, root,
            int(start_value_usd * 100),
            int(final_value_usd * 100),
            trade_count)
        return tx.tx_hash

    def adjudicate_onchain(self, result: CompetitionResult,
                           winner_wallet: str) -> str:
        amount_wei = int(result.winner_token_award * (10 ** TOKEN_DECIMALS))
        # Close submission phase first if still open
        comp = self._registry._comps.get(result.competition_id, {})
        if comp.get("status") == "ACTIVE":
            self._registry.close_for_submission(
                result.competition_id, result.market_regime, self.OWNER)
        tx = self._registry.adjudicate(
            result.competition_id, winner_wallet,
            result.winner_tier, amount_wei, self.OWNER)
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
            "network":               f"{LocalChain.CHAIN_NAME}",
            "chain_id":              LocalChain.CHAIN_ID,
            "block_number":          self._chain.block_number,
            "total_transactions":    len(self._chain._txs),
            "total_events":          len(self._chain._events),
            "total_competitions":    self._registry.total_competitions(),
            "current_season":        self._registry._current_season,
            "remaining_ekthelius":   21 - self._registry._ekthelius_minted,
            "remaining_grand_acc":   1000 - self._registry._grand_acc_minted,
            "acrv_total_supply":     s["total_minted"],
            "acrv_remaining":        s["remaining"],
            "acrv_pct_minted":       s["pct_minted"],
            "total_holders":         s["total_holders"],
            "tier_counts":           s["tier_counts"],
        }

    def tx_url(self, tx_hash: str) -> str:
        return f"local://tx/{tx_hash}"

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

    def run_demo_competition(self, n_bots: int = 3,
                             season: int = 1,
                             symbol: str = "BTC/USDT") -> dict:
        """
        Run a complete competition end-to-end on the local testnet.
        Returns a summary dict with tx hashes, winner, and token award.
        """
        import random
        from .competition_engine import CompetitionEngine
        from .bot_identity       import BotIdentity
        from .token_ledger       import TokenLedger
        import tempfile, os

        # Create temp identities
        tmpdir = tempfile.mkdtemp()
        bots   = [
            BotIdentity(os.path.join(tmpdir, f"bot{i}.json")).generate()
            for i in range(n_bots)
        ]
        wallets = [_fake_addr(b.bot_id) for b in bots]

        # Local ledger for off-chain accounting
        ledger = TokenLedger(os.path.join(tmpdir, "ledger.json"))
        engine = CompetitionEngine(season=season, symbol=symbol,
                                   ledger=ledger)
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
        rng    = random.Random(42)
        prices = [62000.0]
        for _ in range(119):
            prices.append(max(1, prices[-1] * (1 + rng.gauss(0, 0.022) + 0.0008)))

        intervals = [0.02 + i*0.01 for i in range(n_bots)]
        finals    = []

        for bot, interval in zip(bots, intervals):
            h = 400.0 / prices[0]; u = 0.0; t = 400.0; fq = 0.0; fr = 0.0
            for price in prices:
                v = h * price; d = v - t
                if d > t * interval and fq < 0.01:
                    sq = d*.9/price; net = sq*price*.999
                    h -= sq; u += net; fq = net; fr = price
                    engine.record_trade(bot, "sell", sq, price,
                                        role="SCRUM", skip_sig=True)
                elif fq > 0.01 and price < fr*.995 and u >= fq:
                    qty = fq*.999/price; h += qty; u -= fq; fq = 0.0
                    engine.record_trade(bot, "buy", qty, price,
                                        role="FOLD", skip_sig=True)
            finals.append(h*prices[-1]+u+fq)

        # Close and submit
        engine.close()
        self.close_for_submission_onchain(comp_id)

        sub_txs = []
        for bot, wallet, final in zip(bots, wallets, finals):
            engine.submit(bot.bot_id, 400.0, final)
            tx = self.submit_result_onchain(
                comp_id,
                engine._logs[bot.bot_id].root,
                400.0, final,
                engine._logs[bot.bot_id].size,
                wallet=wallet,
            )
            sub_txs.append(tx)

        # Adjudicate
        result   = engine.adjudicate()
        win_idx  = [b.bot_id for b in bots].index(result.winner_bot_id)
        win_addr = wallets[win_idx]
        adj_tx   = self.adjudicate_onchain(result, win_addr)

        return {
            "competition_id": comp_id,
            "winner_wallet":  win_addr,
            "winner_tier":    result.winner_tier,
            "tokens_awarded": result.winner_token_award,
            "winner_balance": self.get_balance(win_addr),
            "adj_tx_hash":    adj_tx,
            "sub_tx_hashes":  sub_txs,
            "block_number":   self._chain.block_number,
            "results_table":  engine.results_table(),
        }
