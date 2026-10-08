"""
merkle_log.py — Append-Only Merkle Trade Log
=============================================
Every signed trade is appended to a Merkle tree.  The root hash is the
compact cryptographic commitment to all trades — publishable to a smart
contract or P2P challenge arbiter without revealing individual trade details.

Inclusion proofs allow any third party to verify that a specific trade
exists in the log, without receiving the full trade list.

Structure:
  Leaves:  SHA-256(trade.canonical_bytes())  — one per trade
  Nodes:   SHA-256(left_child || right_child)
  Root:    top node hash — the commitment

R28: All append operations validate the incoming record before accepting it.
R33: The log is append-only.  No record may be modified or removed.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import List, Optional

from .bot_identity import BotIdentity, TradeRecord

# ── Merkle helpers ────────────────────────────────────────────────────────────


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _node_hash(left: str, right: str) -> str:
    return _sha256((left + right).encode())


def _build_tree(leaves: List[str]) -> List[List[str]]:
    """
    Build a complete Merkle tree from leaf hashes.
    Returns a list of levels: [leaves, level1, ..., [root]].
    Odd-length levels duplicate the last node (standard padding).
    """
    if not leaves:
        return [[_sha256(b"empty")]]
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        level = levels[-1]
        if len(level) % 2 == 1:
            level = level + [level[-1]]  # duplicate last
        next_level = [
            _node_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)
        ]
        levels.append(next_level)
    return levels


def merkle_root(leaves: List[str]) -> str:
    """Compute Merkle root from a list of leaf hashes."""
    return _build_tree(leaves)[-1][0]


def merkle_proof(leaves: List[str], leaf_index: int) -> List[dict]:
    """
    Generate an inclusion proof for leaf at leaf_index.
    Returns a list of {"hash": hex, "position": "left"|"right"} steps.
    The verifier applies these in order to reconstruct the root.
    """
    if leaf_index >= len(leaves):
        raise IndexError(f"Leaf index {leaf_index} out of range ({len(leaves)} leaves)")
    levels = _build_tree(leaves)
    proof = []
    idx = leaf_index
    for level in levels[:-1]:
        if len(level) % 2 == 1:
            level = level + [level[-1]]
        sibling_idx = idx - 1 if idx % 2 == 1 else idx + 1
        sibling_idx = min(sibling_idx, len(level) - 1)
        position = "left" if idx % 2 == 1 else "right"
        proof.append({"hash": level[sibling_idx], "position": position})
        idx //= 2
    return proof


def verify_proof(leaf_hash: str, proof: List[dict], root: str) -> bool:
    """Verify a Merkle inclusion proof."""
    current = leaf_hash
    for step in proof:
        if step["position"] == "left":
            current = _node_hash(step["hash"], current)
        else:
            current = _node_hash(current, step["hash"])
    return current == root


# ── Merkle log ────────────────────────────────────────────────────────────────


class MerkleTradeLog:
    """
    Append-only log of signed trade records backed by a Merkle tree.

    Every append:
      1. Verifies the incoming record's signature, raising if it is invalid
      2. Appends the leaf hash to the tree
      3. Recomputes the root
      4. Writes the updated log to disk (if persistent)

    The root hash is a compact commitment to all trades.
    Individual proofs allow third-party verification of any single trade.
    """

    def __init__(
        self, competition_id: str, bot_id: str, log_path: Optional[str] = None
    ):
        self.competition_id = competition_id
        self.bot_id = bot_id
        self._records: List[TradeRecord] = []
        self._leaves: List[str] = []
        self._log_path = Path(log_path) if log_path else None
        self._opened_at = time.time()

    # ── Append ────────────────────────────────────────────────────────────────

    def append(self, record: TradeRecord, skip_sig_verify: bool = False) -> str:
        """
        Append a signed trade record.  Returns the leaf hash.

        Raises ValueError if:
          - record belongs to a different competition
          - record belongs to a different bot
          - signature is invalid (unless skip_sig_verify=True for testing)
        Records can never be removed after appending.
        """
        if record.competition != self.competition_id:
            raise ValueError(
                f"Record competition {record.competition!r} != "
                f"log competition {self.competition_id!r}"
            )
        if record.bot_pubkey != self.bot_id:
            raise ValueError(
                f"Record bot_pubkey {record.bot_pubkey[:12]}... "
                f"!= log bot_id {self.bot_id[:12]}..."
            )
        if not skip_sig_verify and not BotIdentity.verify_trade(record):
            raise ValueError(f"Invalid signature on trade seq={record.trade_seq}")

        leaf = record.record_hash()
        self._records.append(record)
        self._leaves.append(leaf)
        return leaf

    # ── Tree state ────────────────────────────────────────────────────────────

    @property
    def root(self) -> str:
        """Current Merkle root. Changes with every append."""
        return merkle_root(self._leaves)

    @property
    def size(self) -> int:
        return len(self._records)

    def proof_for(self, trade_seq: int) -> dict:
        """
        Generate an inclusion proof for the trade with the given sequence number.
        Returns: {"leaf_hash": hex, "proof": [...], "root": hex, "trade_seq": int}
        """
        idx = next(
            (i for i, r in enumerate(self._records) if r.trade_seq == trade_seq), None
        )
        if idx is None:
            raise KeyError(f"No trade with seq={trade_seq} in log")
        leaf = self._leaves[idx]
        proof = merkle_proof(self._leaves, idx)
        return {
            "leaf_hash": leaf,
            "proof": proof,
            "root": self.root,
            "trade_seq": trade_seq,
        }

    def verify_inclusion(self, trade_seq: int) -> bool:
        """Self-check: verify the trade is provably in the current tree."""
        try:
            p = self.proof_for(trade_seq)
            return verify_proof(p["leaf_hash"], p["proof"], p["root"])
        except Exception:
            return False

    # ── Summary for competition submission ────────────────────────────────────

    def submission_summary(self) -> dict:
        """
        The summary a bot submits to a competition arbiter.
        Contains: bot ID, competition ID, root hash, trade count,
        opening/closing timestamps, but NO individual trade details.
        Strategy remains private.
        """
        if not self._records:
            return {"error": "No trades in log"}
        return {
            "bot_id": self.bot_id,
            "competition_id": self.competition_id,
            "merkle_root": self.root,
            "trade_count": self.size,
            "opened_at": self._opened_at,
            "closed_at": time.time(),
            "first_trade_ts": self._records[0].timestamp,
            "last_trade_ts": self._records[-1].timestamp,
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self):
        """Save the full log to disk; it never overwrites, it appends."""
        if not self._log_path:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "competition_id": self.competition_id,
            "bot_id": self.bot_id,
            "opened_at": self._opened_at,
            "merkle_root": self.root,
            "records": [r.to_dict() for r in self._records],
        }
        self._log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self) -> "MerkleTradeLog":
        """Load an existing log from disk."""
        if not self._log_path or not self._log_path.exists():
            return self
        data = json.loads(self._log_path.read_text(encoding="utf-8"))
        self._opened_at = data.get("opened_at", self._opened_at)
        for rd in data.get("records", []):
            record = TradeRecord.from_dict(rd)
            leaf = record.record_hash()
            self._records.append(record)
            self._leaves.append(leaf)
        return self
