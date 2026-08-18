"""A caught exception on the wire path must leave evidence.

THE DEFECT
`smart_wire.py` held nine `try/except/pass` and `try/except/continue`
blocks (ruff S110 x7, S112 x2). This file moves money between bots. A
swallowed exception there meant a wire credit, a ledger write or a
transfer could fail and leave NO trace anywhere: no log line, no
counter, no raised error. The operator would find out when a number was
wrong later, with nothing to read.

Measured on the live save file 2026-08-14: 50 ledger rows, 33 carrying
non-zero wire totals, $1,063.89 wired_out exactly balancing $1,063.89
wired_in. `export_ledgers` and `import_ledgers` had ZERO test coverage.

THE RULE THIS PINS
Every caught exception must be logged, counted, or re-raised. Which of
the three depends on the site, and the nine sites do NOT get one
blanket treatment:

  - export/import ledger rows  -> WARNING naming the bot id, plus a
    dropped-row count, because money and provenance cross the block.
  - the completed-transfer notice -> WARNING naming both ids AND the
    amount, because the money has already moved at that point.
  - the target-refused notice -> WARNING, and the only NARROWED catch.
  - the two in-loop notices -> counted, reported once per fold.
  - the error-path notice -> DEBUG only, because the route failure is
    already logged at WARNING one step up and a second WARNING would
    double-count one event.

WHY `capture_log` AND NOT `caplog`
`logging_engine` sets `logging.getLogger("acervator").propagate = False`,
so records never reach the root handler pytest installs and `caplog`
sees nothing once any earlier test has constructed the engine. Measured
here 2026-08-14: the first draft of this file used `caplog`, passed 28/28
alone, and failed 14 of 28 in the full 5385-test run. A log assertion
that depends on collection order is an oracle false negative, so these
tests use the project's `capture_log` fixture, which attaches its own
sink to the named logger and bypasses propagation entirely.

WHY MOST OF THE CATCHES STAY BROAD
Escape analysis, not laziness. Everywhere except the refusal notice, an
exception that escaped would either abandon the remaining wires in the
fold (skipping transfers that would otherwise happen) or reach the
per-route handler and report a COMPLETED, BOOKED transfer as a failure.
Narrowing there would buy a lint rule and sell a money defect.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.smart_wire import (  # noqa: E402
    BotLedger,
    SmartWireManager,
)

LOGGER_NAME = "acervator.smart_wire"


# ──────────────────────────────────────────────────────────────────
# Doubles
# ──────────────────────────────────────────────────────────────────
class RecordingBus:
    """Captures every emit. `fail_on` makes emit raise `exc` when the
    message contains that substring, so one bus can fail at exactly one
    of the nine sites and succeed everywhere else."""

    def __init__(self, fail_on=None, exc=None):
        self.messages: list[str] = []
        self.topics: list[str] = []
        self._fail_on = fail_on
        self._exc = exc or RuntimeError("bus down")

    def emit(self, topic, **kwargs):
        msg = str(kwargs.get("message", ""))
        if self._fail_on is not None and self._fail_on in msg:
            raise self._exc
        self.topics.append(str(topic))
        self.messages.append(msg)
        return None


class AcceptingTarget:
    """A bot that accepts wire income, like a live ScrummingBot."""

    def __init__(self, result=None):
        self.calls: list[tuple] = []
        self._result = result if result is not None else {
            "applied": True, "placement": "tranche", "tranche_index": 2}

    def apply_wire_income(self, usd, source=None, ref=None):
        self.calls.append((usd, source, ref))
        return self._result


class RefusingTarget:
    def __init__(self, reason="no room in the fold queue"):
        self._reason = reason

    def apply_wire_income(self, usd, source=None, ref=None):
        return {"applied": False, "reason": self._reason}


class RaisingTarget:
    def apply_wire_income(self, usd, source=None, ref=None):
        raise RuntimeError("target blew up")


class RaisingStr:
    """A value whose str() raises - what a buggy target can return."""

    def __str__(self):
        raise ValueError("hostile __str__")

    __repr__ = __str__


def _mgr(bus=None):
    m = SmartWireManager(bus=bus)
    m._enabled = True
    m._min_wire = 0.01
    return m


def _ledger(bot_id, **kw):
    lg = BotLedger(bot_id=bot_id, asset=kw.pop("asset", "BTC/USD"))
    for k, v in kw.items():
        setattr(lg, k, v)
    return lg


def _warnings(records):
    return [r.getMessage() for r in records
            if r.levelno >= logging.WARNING]


def _debugs(records):
    return [r.getMessage() for r in records
            if r.levelno == logging.DEBUG]


# ══════════════════════════════════════════════════════════════════
# CONTROL (a) - THE SUCCESS PATH IS UNTOUCHED.
# If any of these fail, the fix changed what happens when nothing goes
# wrong, which is the one thing it was forbidden to do.
# ══════════════════════════════════════════════════════════════════
class TestSuccessPathIsUntouched:
    def test_export_returns_every_field_unchanged(self, capture_log):
        m = _mgr()
        m._ledgers["a"] = _ledger(
            "a", total_profit=10.5, available_profit=4.25,
            wired_in=132.86, wired_out=9.81,
            provenance={"SEED": 200.0, "b": 12.5},
            starting_balance=200.0, mature_profit_allocated=7.35)
        m._ledgers["b"] = _ledger("b", asset="ETH/USD", wired_out=50.0)
        with capture_log(LOGGER_NAME) as rec:
            rows = m.export_ledgers()
        assert rows == [
            {"bot_id": "a", "asset": "BTC/USD", "total_profit": 10.5,
             "available_profit": 4.25, "wired_in": 132.86,
             "wired_out": 9.81,
             "provenance": {"SEED": 200.0, "b": 12.5},
             "starting_balance": 200.0,
             "mature_profit_allocated": 7.35},
            {"bot_id": "b", "asset": "ETH/USD", "total_profit": 0.0,
             "available_profit": 0.0, "wired_in": 0.0,
             "wired_out": 50.0, "provenance": {},
             "starting_balance": 0.0,
             "mature_profit_allocated": 0.0},
        ]
        assert _warnings(rec) == [], (
            "a clean export must stay silent; a warning here means the "
            "new reporting fires on the success path")

    def test_import_restores_every_field_and_returns_the_count(
            self, capture_log):
        src = _mgr()
        src._ledgers["a"] = _ledger(
            "a", total_profit=10.5, available_profit=4.25,
            wired_in=132.86, wired_out=9.81,
            provenance={"SEED": 200.0}, starting_balance=200.0,
            mature_profit_allocated=7.35)
        rows = src.export_ledgers()

        dst = _mgr()
        with capture_log(LOGGER_NAME) as rec:
            n = dst.import_ledgers(rows)
        assert n == 1
        lg = dst._ledgers["a"]
        assert lg.total_profit == 10.5
        assert lg.available_profit == 4.25
        assert lg.wired_in == 132.86
        assert lg.wired_out == 9.81
        assert lg.provenance == {"SEED": 200.0}
        assert lg.starting_balance == 200.0
        assert lg.mature_profit_allocated == 7.35
        assert _warnings(rec) == []

    def test_the_wire_totals_balance_survives_a_round_trip(self):
        """The invariant a silently dropped row would break, and which
        nothing else in the codebase checks."""
        src = _mgr()
        src._ledgers["a"] = _ledger("a", wired_out=1063.89)
        src._ledgers["b"] = _ledger("b", wired_in=1000.00)
        src._ledgers["c"] = _ledger("c", wired_in=63.89)
        dst = _mgr()
        assert dst.import_ledgers(src.export_ledgers()) == 3
        out = sum(x.wired_out for x in dst._ledgers.values())
        into = sum(x.wired_in for x in dst._ledgers.values())
        assert out == pytest.approx(1063.89)
        assert into == pytest.approx(1063.89)

    def test_a_routed_wire_books_and_reports_exactly_as_before(
            self, capture_log):
        """Drives the whole distribute path with nothing failing. Pins
        the transfer, the audit row, the result dict AND the exact
        operator message - the message text is what proves the rewritten
        placement expression produces the same string as the nested-quote
        f-string it replaced."""
        bus = RecordingBus()
        m = _mgr(bus)
        tgt = AcceptingTarget()
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = tgt
        m._wires["srcbot"] = {"tgtbot": 25.0}

        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit(
                "srcbot", 100.0, ref="r1")

        assert results == [{
            "target_id": "tgtbot", "pct": 25.0, "share": 25.0,
            "applied": True,
            "result": {"applied": True, "placement": "tranche",
                       "tranche_index": 2}}]
        assert tgt.calls == [(25.0, "srcbot", "r1")]
        assert len(m._transactions) == 1
        tx = m._transactions[0]
        assert tx.source_bot == "srcbot"
        assert tx.target_bot == "tgtbot"
        assert tx.amount == 25.0
        assert tx.wire_type == "WIRE_BACK"
        assert tx.reason == "fold_profit pct=25.0% ref=r1"
        expected = ("WIRE FLOW: $25.00 from srcbot → tgtbot "
                    "(25.0% of fold profit, ref=r1) → tranche #2")
        assert bus.messages == [expected, expected]
        assert bus.topics == ["bot.log", "bot.log"]
        assert _warnings(rec) == []

    def test_placement_without_a_tranche_index_is_unchanged(self):
        bus = RecordingBus()
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget(
            {"applied": True, "placement": "cash"})
        m._wires["srcbot"] = {"tgtbot": 10.0}
        m.distribute_fold_profit("srcbot", 100.0)
        assert bus.messages[0] == (
            "WIRE FLOW: $10.00 from srcbot → tgtbot "
            "(10.0% of fold profit) → cash")


# ══════════════════════════════════════════════════════════════════
# CONTROL (b) - EACH CAUGHT EXCEPTION NOW LEAVES EVIDENCE.
# One test per site. Each forces the REAL exception the code can raise,
# not a synthetic one, and reads the evidence at the surface a consumer
# reads: the logger, or the returned result.
# ══════════════════════════════════════════════════════════════════
class TestEveryCaughtExceptionLeavesEvidence:
    def test_site1_export_names_the_dropped_bot_and_counts_it(
            self, capture_log):
        """@407 S112. float('not-a-number') raises ValueError."""
        m = _mgr()
        m._ledgers["good1"] = _ledger("good1", wired_out=5.0)
        m._ledgers["bad"] = _ledger("bad", total_profit="not-a-number")
        m._ledgers["good2"] = _ledger("good2", wired_in=5.0)
        with capture_log(LOGGER_NAME) as rec:
            rows = m.export_ledgers()
        assert [r["bot_id"] for r in rows] == ["good1", "good2"]
        warns = _warnings(rec)
        assert any("export DROPPED ledger row for bad" in w
                   for w in warns), warns
        assert any("ValueError" in w for w in warns), warns
        assert any("exported 2 of 3 ledger row(s); 1 dropped" in w
                   for w in warns), warns

    def test_site2_import_names_the_dropped_bot_and_the_offered_count(
            self, capture_log):
        """@459 S112. The caller logs only the ACCEPTED count, so
        'imported 47' is indistinguishable from a 47-bot fleet. The
        offered-vs-accepted line is what makes a drop detectable.

        2026-08-14 - RESTATED, NOT WEAKENED. The trailing clause of the
        summary changed from "; 1 dropped" to "; 1 lost (1 raised, ...)"
        when `offered` was fixed to count the rows the loop's two guard
        clauses drop, which it never used to see. The invariant is the
        same and is still asserted verbatim - "accepted 1 of 2 ledger
        row(s) offered" - and this now also pins the reconciliation
        (1 lost) and the CAUSE (1 raised), neither of which the old
        wording could express. Both rows here are well-formed dicts
        carrying a bot_id, so the offered count is 2 under the old code
        and the new."""
        m = _mgr()
        rows = [
            {"bot_id": "ok", "wired_in": 10.0},
            {"bot_id": "bad", "wired_in": "not-a-number"},
        ]
        with capture_log(LOGGER_NAME) as rec:
            n = m.import_ledgers(rows)
        assert n == 1
        warns = _warnings(rec)
        assert any("import DROPPED ledger row for bad" in w
                   for w in warns), warns
        assert any("PARTIALLY applied" in w for w in warns), warns
        assert any("accepted 1 of 2 ledger row(s) offered" in w
                   and "1 lost" in w and "1 raised" in w
                   for w in warns), warns

    def test_site3_dust_skip_notice_failure_is_counted_and_reported(
            self, capture_log):
        """@601 S110. A broken bus object raises AttributeError."""
        bus = RecordingBus(fail_on="dust skip",
                           exc=AttributeError("no emit"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget()
        m._wires["srcbot"] = {"tgtbot": 0.001}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"] == "below min_wire_amount"
        assert any("dust-skip notice for srcbot -> tgtbot" in d
                   for d in _debugs(rec)), _debugs(rec)
        assert any("1 wire-notice emit(s) failed" in w
                   and "dust-skip" in w
                   for w in _warnings(rec)), _warnings(rec)

    def test_site4_orphan_notice_failure_is_counted_and_reported(
            self, capture_log):
        """@620 S110. The wire points at a bot that is not attached -
        the shape 13 of 48 live ledger rows are already in."""
        bus = RecordingBus(fail_on="target unreachable",
                           exc=AttributeError("no emit"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._wires["srcbot"] = {"ghostbot": 10.0}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"] == "target bot not attached"
        assert any("orphan-wire notice for srcbot -> ghostbot" in d
                   for d in _debugs(rec)), _debugs(rec)
        assert any("1 wire-notice emit(s) failed" in w
                   and "target-unreachable" in w
                   for w in _warnings(rec)), _warnings(rec)

    def test_site5_refused_notice_failure_warns(self, capture_log):
        """@681 S110. This log IS the deliverable of the v3.15.90 F1
        fix: without it the operator sees a green WIRE FLOW while the
        target's fold queue never changed."""
        bus = RecordingBus(fail_on="target refused",
                           exc=TypeError("bad signature"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = RefusingTarget()
        m._wires["srcbot"] = {"tgtbot": 10.0}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["applied"] is False
        assert results[0]["reason"] == "no room in the fold queue"
        assert any("target-refused notice for srcbot -> tgtbot "
                   "($10.0000)" in w
                   for w in _warnings(rec)), _warnings(rec)

    def test_site6_placement_failure_warns_and_keeps_the_transfer(
            self, capture_log):
        """@711 S110. The old comment claimed 'bus emit best-effort' on
        a block with no bus emit in it. What it really guards is str()
        over a value the TARGET returned."""
        bus = RecordingBus()
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget(
            {"applied": True, "placement": "tranche",
             "tranche_index": RaisingStr()})
        m._wires["srcbot"] = {"tgtbot": 10.0}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["applied"] is True, (
            "a cosmetic rendering fault must never unbook a transfer")
        assert len(m._transactions) == 1
        assert any("could not render placement" in w
                   for w in _warnings(rec)), _warnings(rec)
        assert bus.messages[0] == (
            "WIRE FLOW: $10.00 from srcbot → tgtbot "
            "(10.0% of fold profit)"), (
            "the suffix must be dropped whole, not half-built")

    def test_site7_completed_transfer_notice_failure_names_the_amount(
            self, capture_log):
        """@725 S110. THE MONEY HAS ALREADY MOVED here. This is the one
        site where a swallow means a real transfer happened and nothing
        anywhere said so."""
        bus = RecordingBus(fail_on="WIRE FLOW: $",
                           exc=RuntimeError("bus closed"))
        m = _mgr(bus)
        tgt = AcceptingTarget()
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = tgt
        m._wires["srcbot"] = {"tgtbot": 25.0}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["applied"] is True
        assert tgt.calls == [(25.0, "srcbot", "")]
        assert len(m._transactions) == 1
        warns = _warnings(rec)
        hit = [w for w in warns if "COMPLETED" in w]
        assert hit, warns
        assert "$25.0000" in hit[0]
        assert "srcbot" in hit[0] and "tgtbot" in hit[0]

    def test_site8_error_notice_failure_is_debug_and_does_not_double_warn(
            self, capture_log):
        """@747 S110. The route failure is already at WARNING one step
        up. A second WARNING here would double-count one event, so the
        console copy going missing is DEBUG."""
        bus = RecordingBus(fail_on="WIRE FLOW (error)",
                           exc=AttributeError("no emit"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = RaisingTarget()
        m._wires["srcbot"] = {"tgtbot": 10.0}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"].startswith("exception:")
        assert any("route-error notice for srcbot -> tgtbot" in d
                   for d in _debugs(rec)), _debugs(rec)
        warns = _warnings(rec)
        assert [w for w in warns if "route srcbot->tgtbot raised" in w]
        assert not [w for w in warns if "route-error notice" in w], (
            "the missing console copy must not raise a second WARNING "
            "for an event already warned about")

    def test_site9_no_flow_summary_failure_is_debug(self, capture_log):
        """@772 S110. Post-loop, no money crosses it, results already
        complete - so DEBUG, and the method still returns normally."""
        bus = RecordingBus(fail_on="no routed shares",
                           exc=RuntimeError("bus closed"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget()
        m._wires["srcbot"] = {"tgtbot": 0.001}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["applied"] is False
        assert any("no-flow summary for srcbot did not reach the bus"
                   in d for d in _debugs(rec)), _debugs(rec)


# ══════════════════════════════════════════════════════════════════
# CONTROL (c) - THE NARROWED CATCH STILL CATCHES, AND THE UNINTENDED
# ONE NOW ESCAPES. Both halves, or the narrowing is unverified.
# Only site 5 (@681) was narrowed.
# ══════════════════════════════════════════════════════════════════
class TestTheNarrowedCatchAtSite5:
    def _setup(self, exc):
        bus = RecordingBus(fail_on="target refused", exc=exc)
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["refuser"] = RefusingTarget()
        m._bot_refs["taker"] = AcceptingTarget()
        m._wires["srcbot"] = {"refuser": 10.0, "taker": 10.0}
        return m

    @pytest.mark.parametrize("exc", [
        AttributeError("no emit"), TypeError("bad signature"),
        RuntimeError("bus closed"), ValueError("bad format"),
    ])
    def test_it_still_catches_every_intended_type(self, exc, capture_log):
        m = self._setup(exc)
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"] == "no room in the fold queue", (
            "the intended type escaped; the refusal reason was "
            "replaced by a generic exception string")
        assert any("target-refused notice" in w
                   for w in _warnings(rec))

    def test_an_unintended_type_escapes_instead_of_being_eaten(
            self, capture_log):
        """KeyError is outside the narrowed set. It must NOT vanish."""
        m = self._setup(KeyError("surprise"))
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"].startswith("exception:"), (
            "an unintended type was silently eaten by the narrowed "
            "catch - the narrowing is not doing anything")
        assert any("route srcbot->refuser raised" in w
                   for w in _warnings(rec)), _warnings(rec)

    def test_the_escape_still_reaches_every_remaining_wire(self):
        """The escape must be CONTAINED in its own loop iteration. If it
        left the loop, a later transfer would silently not happen - the
        exact class of defect this unit exists to remove."""
        m = self._setup(KeyError("surprise"))
        results = m.distribute_fold_profit("srcbot", 100.0)
        assert len(results) == 2
        assert results[1]["target_id"] == "taker"
        assert results[1]["applied"] is True
        assert len(m._transactions) == 1


# ══════════════════════════════════════════════════════════════════
# CONTROL (d) - NO BEHAVIOUR CHANGE THE OPERATOR DID NOT ASK FOR.
# The eight un-narrowed catches must still contain everything, so no
# escape can skip a transfer or unbook one that happened.
# ══════════════════════════════════════════════════════════════════
class TestNoNewEscapePaths:
    @pytest.mark.parametrize("fail_on", [
        "dust skip", "target unreachable", "WIRE FLOW: $",
        "WIRE FLOW (error)", "no routed shares",
    ])
    def test_a_hostile_bus_never_makes_the_method_raise(self, fail_on):
        """distribute_fold_profit documents that failures 'do NOT raise
        - the fold path continues'. KeyError is outside every narrowed
        set, so this proves the remaining catches are still broad."""
        bus = RecordingBus(fail_on=fail_on, exc=KeyError("surprise"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget()
        m._bot_refs["ghostbot"] = None
        m._wires["srcbot"] = {"tgtbot": 25.0, "dustbot": 0.001,
                              "ghostbot": 10.0}
        results = m.distribute_fold_profit("srcbot", 100.0)
        assert isinstance(results, list)
        assert len(results) == 3, (
            "a wire was abandoned mid-fold; an escape skipped a route")
        assert results[0]["applied"] is True

    def test_a_totally_broken_export_still_returns_the_good_rows(self):
        m = _mgr()
        m._ledgers["bad"] = _ledger("bad", wired_in=RaisingStr())
        m._ledgers["good"] = _ledger("good", wired_in=1.0)
        rows = m.export_ledgers()
        assert [r["bot_id"] for r in rows] == ["good"]

    def test_a_bad_row_does_not_stop_the_rows_after_it(self):
        m = _mgr()
        n = m.import_ledgers([
            {"bot_id": "bad", "wired_in": "x"},
            {"bot_id": "after", "wired_in": 7.0},
        ])
        assert n == 1
        assert "after" in m._ledgers
        assert m._ledgers["after"].wired_in == 7.0


# ══════════════════════════════════════════════════════════════════
# The nine were closed by CHANGING THE CODE. Not one was cleared with a
# suppression - a `# nosec B310` once glossed a real file:// hole for
# the life of a file, and this module moves money.
# ══════════════════════════════════════════════════════════════════
class TestNoSuppressionWasAdded:
    def test_the_directive_count_did_not_rise(self):
        import src.trading.smart_wire as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        assert src.count("noqa") <= 3, (
            "a noqa was added; the nine must be closed by changing the "
            "code, not by silencing the rule")
        for banned in ("nosec", "type: ignore", "pyright: ignore"):
            assert banned not in src, f"{banned} added to a money path"
