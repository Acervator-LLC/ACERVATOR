"""Pin tests for TradeJournal.verify() in src/trading/live_monitor.py.

verify() must recompute the hash chain from GENESIS and confirm it against
each entry's stored chain_hash, not merely count lines.
"""

from __future__ import annotations

import json

from src.trading.live_monitor import TradeJournal, TradeRecord


def _make_record(i: int) -> TradeRecord:
    return TradeRecord(
        timestamp=f"2026-01-0{i}T00:00:00Z",
        unix_ts=1700000000.0 + i,
        bot_id="BOT1",
        asset="BTC",
        action="HARVEST",
        side="sell",
        price=50000.0 + i,
        quantity=0.01,
        usd_value=500.0,
        target_balance=1000.0,
        portfolio_value=10000.0 + i * 10,
        delta_pct=1.0,
        confidence=0.9,
    )


def test_empty_journal_verifies_true_with_zero_count(tmp_path):
    journal = TradeJournal(path=str(tmp_path / "journal.jsonl"))

    ok, count = journal.verify()

    assert (ok, count) == (True, 0)


def test_a_clean_multi_record_journal_verifies_true_with_matching_count(tmp_path):
    journal = TradeJournal(path=str(tmp_path / "journal.jsonl"))
    for i in range(1, 4):
        journal.record(_make_record(i))

    ok, count = journal.verify()

    assert (ok, count) == (True, 3)


def test_a_tampered_chain_hash_is_caught_by_verify(tmp_path):
    """Positive control: without recomputation, verify() returned True on
    every input. Tampering one stored chain_hash must flip the result."""
    path = tmp_path / "journal.jsonl"
    journal = TradeJournal(path=str(path))
    for i in range(1, 4):
        journal.record(_make_record(i))

    lines = path.read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines]
    real_hash = entries[1]["chain_hash"]
    entries[1]["chain_hash"] = "0" * len(real_hash)
    path.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
    )

    tampered_journal = TradeJournal(path=str(path))
    ok, count = tampered_journal.verify()

    assert ok is False
    assert count == 1, "verify() must stop at the first bad entry, index 1"


def test_verify_uses_the_same_hash_as_record(tmp_path):
    """record()'s returned chain hash must equal what verify() recomputes
    for that same entry, proving there is no second, drifting formula."""
    path = tmp_path / "journal.jsonl"
    journal = TradeJournal(path=str(path))
    trade = _make_record(1)

    returned_hash = journal.record(trade)

    expected = TradeJournal._chain_link("GENESIS", trade.record_hash)
    assert returned_hash == expected

    ok, count = journal.verify()
    assert (ok, count) == (True, 1)
