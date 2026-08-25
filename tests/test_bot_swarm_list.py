"""v3.23.61 — pin tests for bot_swarm_list.

Two surfaces:
  (a) BotSwarmLaneAllocator — pure algorithm, no Qt required
  (b) BotListView + LaneWireCanvas — headless-Qt render smoke
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gui.bot_swarm_list import (  # noqa: E402
    LANE_COUNT,
    COLUMN_HEADERS,
    TOTAL_COLS,
    COL_TICKER,
    COL_INFLOW,
    COL_OUTFLOW,
    COL_OUTFLOW_PCT,
    COL_LANE_0,
    BotSwarmLaneAllocator,
)

# C09 — the canvas only paints on a real paintEvent. repaint() does NOT
# fire one offscreen; render(QPixmap) does. The skip-counter pins below
# depend on the paint actually running.
from PySide6.QtGui import QPixmap  # noqa: E402

# -----------------------------------------------------------------
# BotSwarmLaneAllocator — pure algorithm
# -----------------------------------------------------------------


class TestLaneAllocator:
    def test_single_wire_gets_lane_zero(self):
        a = BotSwarmLaneAllocator()
        got = a.assign([("w1", 0, 3)])
        assert got == {"w1": 0}

    def test_non_overlapping_wires_share_lane(self):
        """Wires with non-overlapping row spans fit on the same lane."""
        a = BotSwarmLaneAllocator()
        got = a.assign(
            [
                ("w1", 0, 2),  # rows 0..2
                ("w2", 3, 5),  # rows 3..5 — no overlap with w1
            ]
        )
        assert got["w1"] == 0
        assert got["w2"] == 0, "Non-overlapping wires must share lane 0."

    def test_overlapping_wires_get_separate_lanes(self):
        a = BotSwarmLaneAllocator()
        got = a.assign(
            [
                ("w1", 0, 5),
                ("w2", 2, 7),  # overlaps w1 at rows 2..5
            ]
        )
        assert got["w1"] == 0
        assert got["w2"] == 1

    def test_deterministic_first_free_lane(self):
        """When multiple lanes are free, always pick the lowest index."""
        a = BotSwarmLaneAllocator()
        # Fill lanes 0..2 with an overlapping trio, then a 4th
        # overlapping wire — should land on lane 3.
        got = a.assign(
            [
                ("w1", 0, 10),
                ("w2", 0, 10),
                ("w3", 0, 10),
                ("w4", 0, 10),
            ]
        )
        assert got == {"w1": 0, "w2": 1, "w3": 2, "w4": 3}

    def test_returns_none_when_all_lanes_full(self):
        a = BotSwarmLaneAllocator(lane_count=3)
        got = a.assign(
            [
                ("w1", 0, 5),
                ("w2", 0, 5),
                ("w3", 0, 5),
                ("w4", 0, 5),  # can't fit
            ]
        )
        assert got["w4"] is None

    def test_reverse_direction_treated_same(self):
        """(src_row=5, dst_row=2) same span as (2, 5)."""
        a = BotSwarmLaneAllocator()
        got = a.assign(
            [
                ("w1", 2, 5),
                ("w2", 5, 2),  # same span, reversed
            ]
        )
        assert got["w1"] == 0
        assert got["w2"] == 1

    def test_adjacent_spans_share_lane(self):
        """Adjacent (touching) spans do NOT overlap by inclusive
        boundary; they should share a lane. w1 ends at row 3,
        w2 starts at row 4."""
        a = BotSwarmLaneAllocator()
        got = a.assign(
            [
                ("w1", 0, 3),
                ("w2", 4, 6),
            ]
        )
        assert got["w1"] == 0
        assert got["w2"] == 0

    def test_endpoints_shared_do_overlap(self):
        """When two wires share an endpoint row (e.g. both touch
        row 3), they overlap — must separate lanes."""
        a = BotSwarmLaneAllocator()
        got = a.assign(
            [
                ("w1", 0, 3),
                ("w2", 3, 6),  # shares row 3 with w1
            ]
        )
        assert got["w1"] == 0
        assert got["w2"] == 1


# -----------------------------------------------------------------
# Column schema
# -----------------------------------------------------------------


class TestSchema:
    def test_12_columns_total(self):
        """v3.23.62 — %Out column added → 12 cols total."""
        assert TOTAL_COLS == 12
        assert len(COLUMN_HEADERS) == 12

    def test_column_layout(self):
        assert COLUMN_HEADERS[COL_TICKER] == "Ticker"
        assert COLUMN_HEADERS[COL_INFLOW] == "Inflow"
        assert COLUMN_HEADERS[COL_OUTFLOW] == "Outflow"
        assert COLUMN_HEADERS[COL_OUTFLOW_PCT] == "% Out"
        for i in range(LANE_COUNT):
            assert COLUMN_HEADERS[COL_LANE_0 + i] == f"L{i + 1}"

    def test_lane_count_is_8(self):
        assert LANE_COUNT == 8


# -----------------------------------------------------------------
# Headless-Qt render smoke — BotListView populates + LaneWireCanvas
#                            assigns lanes correctly
# -----------------------------------------------------------------


class TestHeadlessRender:
    def _new_app(self):
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_list_populates_rows_and_bot_ids(self):
        self._new_app()
        from src.gui.bot_swarm_list import BotListView

        lst = BotListView()
        lst.set_bots(
            [
                {
                    "bot_id": "aaa",
                    "symbol": "CHIP/USD",
                    "inflow_usd": 100.5,
                    "outflow_usd": 40.0,
                    "outflow_pct": 25.0,
                },
                {
                    "bot_id": "bbb",
                    "symbol": "SPK/USD",
                    "inflow_usd": 20.0,
                    "outflow_usd": 0.0,
                    "outflow_pct": 0.0,
                },
            ]
        )
        assert lst.rowCount() == 2
        assert lst.bot_ids() == ["aaa", "bbb"]
        assert lst.row_of_bot("aaa") == 0
        assert lst.row_of_bot("ccc") == -1
        # Formatted cell content
        assert lst.item(0, COL_TICKER).text() == "CHIP/USD"
        assert lst.item(0, COL_INFLOW).text() == "$100.50"
        assert lst.item(1, COL_OUTFLOW).text() == "$0.00"
        assert lst.item(0, COL_OUTFLOW_PCT).text() == "25%"
        assert lst.item(1, COL_OUTFLOW_PCT).text() == "0%"

    def test_outflow_pct_color_ramp(self):
        """v3.23.62 — colour thresholds:
        0 → grey  |  1-80 → cyan  |  81-99 → amber  |  100+ → red"""
        self._new_app()
        from src.gui.bot_swarm_list import BotListView

        lst = BotListView()
        lst.set_bots(
            [
                {"bot_id": "a", "symbol": "A/USD", "outflow_pct": 0},
                {"bot_id": "b", "symbol": "B/USD", "outflow_pct": 25},
                {"bot_id": "c", "symbol": "C/USD", "outflow_pct": 90},
                {"bot_id": "d", "symbol": "D/USD", "outflow_pct": 120},
            ]
        )

        def _col(row):
            return lst.item(row, COL_OUTFLOW_PCT).foreground().color().name()

        assert _col(0) == "#666666"  # grey
        assert _col(1) == "#00ffee"  # cyan
        assert _col(2) == "#ffaa00"  # amber
        assert _col(3) == "#ff3366"  # red

    def test_wire_paint_uses_wire_phase_for_animation(self):
        """v3.23.62 — wire animation migrated to list view. The paint
        loop must consume `wire['phase']` (set by BotVisualizationTab
        ._animate at ~2.5/sec) so pulses travel source→target."""
        self._new_app()
        from src.gui.bot_swarm_list import BotListView, LaneWireCanvas

        lst = BotListView()
        lst.set_bots(
            [{"bot_id": "a", "symbol": "A/USD"}, {"bot_id": "b", "symbol": "B/USD"}]
        )
        canvas = LaneWireCanvas(lst)
        canvas.set_wires(
            [{"id": "w", "source_id": "a", "target_id": "b", "phase": 0.42}]
        )
        # Direct source-inspection: assert the paint path actually
        # reads .get('phase', ...) so a fixed sink never happens.
        src = Path(canvas.__class__.__module__.replace(".", "/"))
        src_path = REPO / (str(src) + ".py")
        text = src_path.read_text(encoding="utf-8")
        assert 'w.get("phase"' in text, (
            "LaneWireCanvas.paintEvent must consume wire['phase'] "
            "so pulses animate — v3.23.62 discipline."
        )

    def test_lane_col_x_within_bounds(self):
        self._new_app()
        from src.gui.bot_swarm_list import BotListView

        lst = BotListView()
        lst.resize(900, 400)
        lst.set_bots([{"bot_id": "a", "symbol": "X/USD"}])
        # Each lane column x should be strictly increasing.
        prev = -1
        for i in range(LANE_COUNT):
            x = lst.lane_col_x(i)
            assert x > prev, f"Lane {i} x={x} not > previous {prev}"
            prev = x

    def test_wire_canvas_assigns_lanes(self):
        self._new_app()
        from src.gui.bot_swarm_list import BotListView, LaneWireCanvas

        lst = BotListView()
        lst.set_bots(
            [
                {"bot_id": "a", "symbol": "A/USD"},
                {"bot_id": "b", "symbol": "B/USD"},
                {"bot_id": "c", "symbol": "C/USD"},
                {"bot_id": "d", "symbol": "D/USD"},
            ]
        )
        canvas = LaneWireCanvas(lst)
        # Two overlapping wires — different lanes.
        canvas.set_wires(
            [
                {"id": "w1", "source_id": "a", "target_id": "c"},
                {"id": "w2", "source_id": "b", "target_id": "d"},
            ]
        )
        assert canvas._lane_assignments["w1"] == 0
        assert canvas._lane_assignments["w2"] == 1

    def test_wire_canvas_reports_unknown_bot(self):
        """REPLACES test_wire_canvas_ignores_unknown_bot (C09, v3.24.52).

        The old pin was named "ignores", commented "wire silently
        skipped", and asserted that the silent drop was correct. That is
        finding SWARM-A3 written down as a requirement: it stayed green
        through the defect and would only have gone red if someone fixed
        it.

        Replacement, not relaxation, per M7 with operator acknowledgement
        recorded 2026-08-07 (see
        docs/audits/2026-08-07_C09_pin_replacement_record.md). This
        asserts STRICTLY MORE than the old pin: the original invariant
        survives verbatim as the first assertion, and the silence is
        withdrawn.
        """
        self._new_app()
        from src.gui.bot_swarm_list import BotListView, LaneWireCanvas

        lst = BotListView()
        lst.set_bots([{"bot_id": "a", "symbol": "A/USD"}])
        canvas = LaneWireCanvas(lst)
        canvas.set_wires([{"id": "w1", "source_id": "a", "target_id": "z"}])

        # 1. The original invariant, unchanged: an undrawable wire is
        #    still not assigned a lane.
        assert (
            "w1" not in canvas._lane_assignments
            or canvas._lane_assignments.get("w1") is None
        )

        # 2. ...but the drop is now REPORTED rather than silent.
        canvas.render(QPixmap(canvas.size()))
        assert canvas.undrawable_wire_count() == 1, (
            "a wire that cannot be drawn must be counted, not dropped " "in silence"
        )

        # 3. Exactly one -- a fix that reports every wire as skipped
        #    must not pass either.
        lst.set_bots(
            [{"bot_id": "a", "symbol": "A/USD"}, {"bot_id": "b", "symbol": "B/USD"}]
        )
        canvas.set_wires(
            [
                {"id": "ok", "source_id": "a", "target_id": "b"},
                {"id": "bad", "source_id": "a", "target_id": "z"},
            ]
        )
        canvas.render(QPixmap(canvas.size()))
        assert (
            canvas.undrawable_wire_count() == 1
        ), "only the undrawable wire counts; the drawable one must not"

    def test_undrawable_wires_are_logged_once_not_every_frame(self, caplog):
        """C09 says "increment a visible skipped counter AND surface
        it". A counter nobody reads is not surfaced -- but this canvas
        repaints at ~2.5/sec, so a per-frame line would bury the log
        while saying nothing new. Report on CHANGE."""
        import logging

        self._new_app()
        from src.gui.bot_swarm_list import BotListView, LaneWireCanvas

        lst = BotListView()
        lst.set_bots([{"bot_id": "a", "symbol": "A/USD"}])
        canvas = LaneWireCanvas(lst)
        canvas.set_wires([{"id": "w1", "source_id": "a", "target_id": "z"}])

        with caplog.at_level(logging.WARNING, logger="acervator.gui.bot_swarm_list"):
            for _ in range(4):
                canvas.render(QPixmap(canvas.size()))

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert (
            len(warnings) == 1
        ), f"expected one report across four paints, got {len(warnings)}"
        assert "not drawn" in warnings[0].getMessage()
        # The reason must be named -- "a wire vanished" is not actionable.
        assert "unlisted-bot" in warnings[0].getMessage()

    def test_the_reason_distinguishes_capacity_from_staleness(self):
        """`no-lane` (allocator exhausted) and `unlisted-bot` (endpoint
        not in the row set) are different problems with different fixes,
        so the reported reason must name the real one.

        This caught a defect in the first C09 implementation: `set_wires`
        filters unlisted endpoints BEFORE lane assignment, so at paint
        time they are indistinguishable from exhaustion and were all
        reported as `no-lane` -- pointing the operator at lane capacity
        when the row set was what had gone stale.
        """
        self._new_app()
        from src.gui.bot_swarm_list import BotListView, LaneWireCanvas

        lst = BotListView()
        lst.set_bots([{"bot_id": "a", "symbol": "A/USD"}])
        canvas = LaneWireCanvas(lst)
        canvas.set_wires([{"id": "w1", "source_id": "a", "target_id": "z"}])
        canvas.render(QPixmap(canvas.size()))
        assert canvas.undrawable_wires() == [("w1", "unlisted-bot")], (
            f"an unlisted endpoint must be reported as such, got "
            f"{canvas.undrawable_wires()}"
        )

    def test_endpoint_lookup_is_not_a_linear_scan(self):
        """C09 second half: `row_of_bot` was `self._bot_ids.index(...)`,
        called twice per wire on every paint -- O(bots x wires) per
        repaint. The paint must resolve endpoints from a mapping built
        once, not by scanning rows per wire."""
        self._new_app()
        from src.gui.bot_swarm_list import BotListView, LaneWireCanvas

        lst = BotListView()
        lst.set_bots([{"bot_id": f"b{i}", "symbol": f"S{i}/USD"} for i in range(30)])
        canvas = LaneWireCanvas(lst)
        canvas.set_wires(
            [
                {"id": f"w{i}", "source_id": f"b{i}", "target_id": f"b{i + 1}"}
                for i in range(0, 8)
            ]
        )

        calls = {"n": 0}
        original = lst.row_of_bot

        def _counting(bot_id):
            calls["n"] += 1
            return original(bot_id)

        lst.row_of_bot = _counting
        canvas.render(QPixmap(canvas.size()))
        assert calls["n"] == 0, (
            f"paint called row_of_bot {calls['n']} times; endpoints must "
            f"come from a mapping built once per paint"
        )
