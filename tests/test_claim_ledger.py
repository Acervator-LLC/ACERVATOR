"""Pin tests for dev_harness/harness/claim_ledger.py.

Verify the ledger:
  1. Logs claims in `open` state
  2. Assigns monotonic same-day IDs
  3. Refuses to double-transition (verify/refute an already-resolved claim)
  4. `check` exits 1 while a claim is open, exits 0 after resolution
  5. JSONL round-trips correctly

Uses a temporary ledger path to avoid touching the real
docs/audits/CLAIMS.jsonl during test.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dev_harness.harness import claim_ledger


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    """Redirect the module-level LEDGER_PATH to a per-test tempfile."""
    p = tmp_path / "CLAIMS.jsonl"
    monkeypatch.setattr(claim_ledger, "LEDGER_PATH", p)
    yield p


class TestLogClaim:
    def test_log_creates_open_claim(self):
        c = claim_ledger.log_claim("X works", "grep foo.py")
        assert c.status == "open"
        assert c.claim == "X works"
        assert c.evidence_required == "grep foo.py"
        assert c.id.startswith("CLM-")

    def test_second_claim_gets_next_id(self):
        c1 = claim_ledger.log_claim("A", "e1")
        c2 = claim_ledger.log_claim("B", "e2")
        assert c1.id != c2.id
        # NNN sequence should increment
        assert int(c1.id.split("-")[-1]) + 1 == int(c2.id.split("-")[-1])

    def test_persists_to_disk_jsonl(self, _isolated_ledger):
        claim_ledger.log_claim("A", "e1")
        claim_ledger.log_claim("B", "e2")
        lines = _isolated_ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        for line in lines:
            d = json.loads(line)
            assert d["status"] == "open"


class TestVerify:
    def test_verify_transitions_to_verified(self):
        c = claim_ledger.log_claim("A", "e1")
        v = claim_ledger.verify(c.id, note="checked with grep", files=["foo.py"])
        assert v.status == "verified"
        assert v.evidence == {"note": "checked with grep", "files": ["foo.py"]}
        assert v.resolved is not None

    def test_verify_unknown_id_raises_keyerror(self):
        with pytest.raises(KeyError):
            claim_ledger.verify("CLM-99999999-999", note="x")

    def test_verify_twice_raises_valueerror(self):
        c = claim_ledger.log_claim("A", "e1")
        claim_ledger.verify(c.id, note="first")
        with pytest.raises(ValueError, match="verified"):
            claim_ledger.verify(c.id, note="second")


class TestRefute:
    def test_refute_transitions_to_refuted(self):
        c = claim_ledger.log_claim("A", "e1")
        r = claim_ledger.refute(c.id, note="turned out wrong")
        assert r.status == "refuted"

    def test_cannot_refute_verified(self):
        c = claim_ledger.log_claim("A", "e1")
        claim_ledger.verify(c.id, note="ok")
        with pytest.raises(ValueError, match="verified"):
            claim_ledger.refute(c.id, note="x")


class TestListOpen:
    def test_list_open_returns_only_open(self):
        c1 = claim_ledger.log_claim("A", "e1")
        c2 = claim_ledger.log_claim("B", "e2")
        c3 = claim_ledger.log_claim("C", "e3")
        claim_ledger.verify(c2.id, note="ok")
        open_ids = {c.id for c in claim_ledger.list_open()}
        assert open_ids == {c1.id, c3.id}

    def test_list_open_filters_by_session(self):
        c1 = claim_ledger.log_claim("A", "e1", session="s1")
        c2 = claim_ledger.log_claim("B", "e2", session="s2")
        s1_open = {c.id for c in claim_ledger.list_open("s1")}
        assert s1_open == {c1.id}


class TestCheck:
    def test_check_no_open_exits_zero(self, capsys):
        rc = claim_ledger.check_no_open()
        assert rc == 0

    def test_check_with_open_exits_one(self, capsys):
        claim_ledger.log_claim("A", "e1")
        rc = claim_ledger.check_no_open()
        assert rc == 1
        out = capsys.readouterr().out
        assert "1 open claim" in out

    def test_check_clean_after_resolution(self, capsys):
        c = claim_ledger.log_claim("A", "e1")
        assert claim_ledger.check_no_open() == 1
        claim_ledger.verify(c.id, note="done")
        assert claim_ledger.check_no_open() == 0


class TestCli:
    def test_log_and_check_via_cli(self, capsys):
        assert claim_ledger.main(["log", "the sky is blue", "--evidence", "look up"]) == 0
        assert claim_ledger.main(["check"]) == 1  # open claim exists
        # capture the claim ID from the ledger to verify
        open_claims = claim_ledger.list_open()
        assert len(open_claims) == 1
        assert claim_ledger.main(["verify", open_claims[0].id, "--note", "looked; blue"]) == 0
        assert claim_ledger.main(["check"]) == 0
