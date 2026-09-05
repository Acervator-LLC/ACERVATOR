"""Every exception `smart_wire.py` catches leaves a log line, a count, or a raise.

`export_ledgers` and `import_ledgers` name the bot id they drop and reconcile
the offered count. `distribute_fold_profit` warns when the money has moved,
counts the in-loop notices, and keeps the route-error copy at DEBUG.
`TestTheNarrowedCatchAtSite5` holds both halves of the one narrowed catch.
"""

from __future__ import annotations

import logging

import pytest

from src.trading.smart_wire import BotLedger, SmartWireManager

LOGGER_NAME = "acervator.smart_wire"


class RecordingBus:
    """Records every emit in `messages`.

    `emit` raises `exc` when the message holds the `fail_on` substring.
    """

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
        self._result = (
            result
            if result is not None
            else {"applied": True, "placement": "tranche", "tranche_index": 2}
        )

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
    return [r.getMessage() for r in records if r.levelno >= logging.WARNING]


def _debugs(records):
    return [r.getMessage() for r in records if r.levelno == logging.DEBUG]


class TestSuccessPathIsUntouched:
    def test_export_returns_every_field_unchanged(self, capture_log):
        m = _mgr()
        m._ledgers["a"] = _ledger(
            "a",
            total_profit=10.5,
            available_profit=4.25,
            wired_in=132.86,
            wired_out=9.81,
            provenance={"SEED": 200.0, "b": 12.5},
            starting_balance=200.0,
            mature_profit_allocated=7.35,
        )
        m._ledgers["b"] = _ledger("b", asset="ETH/USD", wired_out=50.0)
        with capture_log(LOGGER_NAME) as rec:
            rows = m.export_ledgers()
        assert rows == [
            {
                "bot_id": "a",
                "asset": "BTC/USD",
                "total_profit": 10.5,
                "available_profit": 4.25,
                "wired_in": 132.86,
                "wired_out": 9.81,
                "provenance": {"SEED": 200.0, "b": 12.5},
                "starting_balance": 200.0,
                "mature_profit_allocated": 7.35,
            },
            {
                "bot_id": "b",
                "asset": "ETH/USD",
                "total_profit": 0.0,
                "available_profit": 0.0,
                "wired_in": 0.0,
                "wired_out": 50.0,
                "provenance": {},
                "starting_balance": 0.0,
                "mature_profit_allocated": 0.0,
            },
        ]
        assert _warnings(rec) == [], (
            "a clean export must stay silent; a warning here means the "
            "new reporting fires on the success path"
        )

    def test_import_restores_every_field_and_returns_the_count(self, capture_log):
        src = _mgr()
        src._ledgers["a"] = _ledger(
            "a",
            total_profit=10.5,
            available_profit=4.25,
            wired_in=132.86,
            wired_out=9.81,
            provenance={"SEED": 200.0},
            starting_balance=200.0,
            mature_profit_allocated=7.35,
        )
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
        """Total wired_out equals total wired_in across a ledger round trip."""
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

    def test_a_routed_wire_books_and_reports_exactly_as_before(self, capture_log):
        """A clean `distribute_fold_profit` books the transfer and emits WIRE FLOW.

        The result dict, the `_transactions` row and the bus message are all
        pinned.
        """
        bus = RecordingBus()
        m = _mgr(bus)
        tgt = AcceptingTarget()
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = tgt
        m._wires["srcbot"] = {"tgtbot": 25.0}

        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0, ref="r1")

        assert results == [
            {
                "target_id": "tgtbot",
                "pct": 25.0,
                "share": 25.0,
                "applied": True,
                "result": {"applied": True, "placement": "tranche", "tranche_index": 2},
            }
        ]
        assert tgt.calls == [(25.0, "srcbot", "r1")]
        assert len(m._transactions) == 1
        tx = m._transactions[0]
        assert tx.source_bot == "srcbot"
        assert tx.target_bot == "tgtbot"
        assert tx.amount == 25.0
        assert tx.wire_type == "WIRE_BACK"
        assert tx.reason == "fold_profit pct=25.0% ref=r1"
        expected = (
            "WIRE FLOW: $25.00 from srcbot → tgtbot "
            "(25.0% of fold profit, ref=r1) → tranche #2"
        )
        assert bus.messages == [expected, expected]
        assert bus.topics == ["bot.log", "bot.log"]
        assert _warnings(rec) == []

    def test_placement_without_a_tranche_index_is_unchanged(self):
        bus = RecordingBus()
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget({"applied": True, "placement": "cash"})
        m._wires["srcbot"] = {"tgtbot": 10.0}
        m.distribute_fold_profit("srcbot", 100.0)
        assert bus.messages[0] == (
            "WIRE FLOW: $10.00 from srcbot → tgtbot " "(10.0% of fold profit) → cash"
        )


class TestEveryCaughtExceptionLeavesEvidence:
    def test_site1_export_names_the_dropped_bot_and_counts_it(self, capture_log):
        """`export_ledgers` names the dropped bot and reconciles the exported count."""
        m = _mgr()
        m._ledgers["good1"] = _ledger("good1", wired_out=5.0)
        m._ledgers["bad"] = _ledger("bad", total_profit="not-a-number")
        m._ledgers["good2"] = _ledger("good2", wired_in=5.0)
        with capture_log(LOGGER_NAME) as rec:
            rows = m.export_ledgers()
        assert [r["bot_id"] for r in rows] == ["good1", "good2"]
        warns = _warnings(rec)
        assert any("export DROPPED ledger row for bad" in w for w in warns), warns
        assert any("ValueError" in w for w in warns), warns
        assert any(
            "exported 2 of 3 ledger row(s); 1 dropped" in w for w in warns
        ), warns

    def test_site2_import_names_the_dropped_bot_and_the_offered_count(
        self, capture_log
    ):
        """`import_ledgers` names the dropped bot, the offered count and the cause."""
        m = _mgr()
        rows = [
            {"bot_id": "ok", "wired_in": 10.0},
            {"bot_id": "bad", "wired_in": "not-a-number"},
        ]
        with capture_log(LOGGER_NAME) as rec:
            n = m.import_ledgers(rows)
        assert n == 1
        warns = _warnings(rec)
        assert any("import DROPPED ledger row for bad" in w for w in warns), warns
        assert any("PARTIALLY applied" in w for w in warns), warns
        assert any(
            "accepted 1 of 2 ledger row(s) offered" in w
            and "1 lost" in w
            and "1 raised" in w
            for w in warns
        ), warns

    def test_site3_dust_skip_notice_failure_is_counted_and_reported(self, capture_log):
        """A failed dust-skip notice is logged at DEBUG and counted in a WARNING."""
        bus = RecordingBus(fail_on="dust skip", exc=AttributeError("no emit"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget()
        m._wires["srcbot"] = {"tgtbot": 0.001}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"] == "below min_wire_amount"
        assert any(
            "dust-skip notice for srcbot -> tgtbot" in d for d in _debugs(rec)
        ), _debugs(rec)
        assert any(
            "1 wire-notice emit(s) failed" in w and "dust-skip" in w
            for w in _warnings(rec)
        ), _warnings(rec)

    def test_site4_orphan_notice_failure_is_counted_and_reported(self, capture_log):
        """A failed orphan-wire notice is logged at DEBUG and counted in a WARNING."""
        bus = RecordingBus(fail_on="target unreachable", exc=AttributeError("no emit"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._wires["srcbot"] = {"ghostbot": 10.0}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"] == "target bot not attached"
        assert any(
            "orphan-wire notice for srcbot -> ghostbot" in d for d in _debugs(rec)
        ), _debugs(rec)
        assert any(
            "1 wire-notice emit(s) failed" in w and "target-unreachable" in w
            for w in _warnings(rec)
        ), _warnings(rec)

    def test_site5_refused_notice_failure_warns(self, capture_log):
        """A failed target-refused notice warns, naming both ids and the amount."""
        bus = RecordingBus(fail_on="target refused", exc=TypeError("bad signature"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = RefusingTarget()
        m._wires["srcbot"] = {"tgtbot": 10.0}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["applied"] is False
        assert results[0]["reason"] == "no room in the fold queue"
        assert any(
            "target-refused notice for srcbot -> tgtbot " "($10.0000)" in w
            for w in _warnings(rec)
        ), _warnings(rec)

    def test_site6_placement_failure_warns_and_keeps_the_transfer(self, capture_log):
        """A placement str() failure warns, and the transfer stays applied."""
        bus = RecordingBus()
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget(
            {"applied": True, "placement": "tranche", "tranche_index": RaisingStr()}
        )
        m._wires["srcbot"] = {"tgtbot": 10.0}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert (
            results[0]["applied"] is True
        ), "a cosmetic rendering fault must never unbook a transfer"
        assert len(m._transactions) == 1
        assert any(
            "could not render placement" in w for w in _warnings(rec)
        ), _warnings(rec)
        assert bus.messages[0] == (
            "WIRE FLOW: $10.00 from srcbot → tgtbot " "(10.0% of fold profit)"
        ), "the suffix must be dropped whole, not half-built"

    def test_site7_completed_transfer_notice_failure_names_the_amount(
        self, capture_log
    ):
        """A failed completed-transfer notice warns, naming both ids and the amount."""
        bus = RecordingBus(fail_on="WIRE FLOW: $", exc=RuntimeError("bus closed"))
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
        self, capture_log
    ):
        """A failed route-error notice is DEBUG, and raises no second WARNING."""
        bus = RecordingBus(fail_on="WIRE FLOW (error)", exc=AttributeError("no emit"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = RaisingTarget()
        m._wires["srcbot"] = {"tgtbot": 10.0}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"].startswith("exception:")
        assert any(
            "route-error notice for srcbot -> tgtbot" in d for d in _debugs(rec)
        ), _debugs(rec)
        warns = _warnings(rec)
        assert [w for w in warns if "route srcbot->tgtbot raised" in w]
        assert not [w for w in warns if "route-error notice" in w], (
            "the missing console copy must not raise a second WARNING "
            "for an event already warned about"
        )

    def test_site9_no_flow_summary_failure_is_debug(self, capture_log):
        """A failed no-flow summary is DEBUG, and `distribute_fold_profit` returns."""
        bus = RecordingBus(fail_on="no routed shares", exc=RuntimeError("bus closed"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget()
        m._wires["srcbot"] = {"tgtbot": 0.001}
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["applied"] is False
        assert any(
            "no-flow summary for srcbot did not reach the bus" in d
            for d in _debugs(rec)
        ), _debugs(rec)


class TestTheNarrowedCatchAtSite5:
    def _setup(self, exc):
        bus = RecordingBus(fail_on="target refused", exc=exc)
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["refuser"] = RefusingTarget()
        m._bot_refs["taker"] = AcceptingTarget()
        m._wires["srcbot"] = {"refuser": 10.0, "taker": 10.0}
        return m

    @pytest.mark.parametrize(
        "exc",
        [
            AttributeError("no emit"),
            TypeError("bad signature"),
            RuntimeError("bus closed"),
            ValueError("bad format"),
        ],
    )
    def test_it_still_catches_every_intended_type(self, exc, capture_log):
        m = self._setup(exc)
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"] == "no room in the fold queue", (
            "the intended type escaped; the refusal reason was "
            "replaced by a generic exception string"
        )
        assert any("target-refused notice" in w for w in _warnings(rec))

    def test_an_unintended_type_escapes_instead_of_being_eaten(self, capture_log):
        """KeyError is outside the narrowed set. It must NOT vanish."""
        m = self._setup(KeyError("surprise"))
        with capture_log(LOGGER_NAME) as rec:
            results = m.distribute_fold_profit("srcbot", 100.0)
        assert results[0]["reason"].startswith("exception:"), (
            "an unintended type was silently eaten by the narrowed "
            "catch - the narrowing is not doing anything"
        )
        assert any(
            "route srcbot->refuser raised" in w for w in _warnings(rec)
        ), _warnings(rec)

    def test_the_escape_still_reaches_every_remaining_wire(self):
        """A KeyError escaping the narrowed catch stays in its own iteration."""
        m = self._setup(KeyError("surprise"))
        results = m.distribute_fold_profit("srcbot", 100.0)
        assert len(results) == 2
        assert results[1]["target_id"] == "taker"
        assert results[1]["applied"] is True
        assert len(m._transactions) == 1


class TestNoNewEscapePaths:
    @pytest.mark.parametrize(
        "fail_on",
        [
            "dust skip",
            "target unreachable",
            "WIRE FLOW: $",
            "WIRE FLOW (error)",
            "no routed shares",
        ],
    )
    def test_a_hostile_bus_never_makes_the_method_raise(self, fail_on):
        """A KeyError at any `fail_on` site leaves the method returning."""
        bus = RecordingBus(fail_on=fail_on, exc=KeyError("surprise"))
        m = _mgr(bus)
        m._bot_refs["srcbot"] = object()
        m._bot_refs["tgtbot"] = AcceptingTarget()
        m._bot_refs["ghostbot"] = None
        m._wires["srcbot"] = {"tgtbot": 25.0, "dustbot": 0.001, "ghostbot": 10.0}
        results = m.distribute_fold_profit("srcbot", 100.0)
        assert isinstance(results, list)
        assert (
            len(results) == 3
        ), "a wire was abandoned mid-fold; an escape skipped a route"
        assert results[0]["applied"] is True

    def test_a_totally_broken_export_still_returns_the_good_rows(self):
        m = _mgr()
        m._ledgers["bad"] = _ledger("bad", wired_in=RaisingStr())
        m._ledgers["good"] = _ledger("good", wired_in=1.0)
        rows = m.export_ledgers()
        assert [r["bot_id"] for r in rows] == ["good"]

    def test_a_bad_row_does_not_stop_the_rows_after_it(self):
        m = _mgr()
        n = m.import_ledgers(
            [
                {"bot_id": "bad", "wired_in": "x"},
                {"bot_id": "after", "wired_in": 7.0},
            ]
        )
        assert n == 1
        assert "after" in m._ledgers
        assert m._ledgers["after"].wired_in == 7.0
