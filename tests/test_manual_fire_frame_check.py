"""Pins for the Manual Fire target-frame harness.

Manual Fire re-zeros a bot to "the Target Balance", but two of those are
persisted: the operator's `config.target_balance` and the live
`scrumming_state.target_balance` that compounding writes. Which one the
code resolves to changes the order that gets placed.

WHY THE SYMPTOM READS AS INTERMITTENT
The gap between them IS accumulated compounding growth. It is exactly
$0.00 on a bot that has never compounded and grows on one that has, so
the same command behaves correctly on some bots and wrongly on others
with no code change in between. Measured against live state 2026-08-06:
26 of 35 bots diverged, 9 were clean, and 4 would trade in OPPOSITE
DIRECTIONS depending on the reading -- CAP/USD sells $3.31 under one and
buys $2.11 under the other.

The sign-flip case is the sharpest and gets its own class below: a
wrong-sized order is a rounding complaint, a wrong-DIRECTION order moves
the position the wrong way.

This harness measures the disagreement. It deliberately does not encode
an opinion about which frame is correct -- that is a strategy question.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dev_harness.harness.manual_fire_frame_check import analyse, main  # noqa: E402


def _bot(symbol, units, price, t_cfg, t_live, qrate=1.0):
    return {
        "config": {"symbol": symbol, "target_balance": t_cfg},
        "stats": {"current_price": price},
        "scrumming_state": {
            "target_balance": t_live,
            "quote_to_usd": qrate,
            "main_lots": [{"units": units}],
        },
    }


class TestTheArithmetic:
    def test_an_uncompounded_bot_shows_no_gap(self):
        """NEGATIVE CONTROL: the 9 clean bots must read as clean, or the
        tool cries wolf on the whole fleet."""
        rows = analyse({"bots": {"a": _bot("RAVE/USD", 1.0, 50.0, 50.0, 50.0)}})
        assert rows[0]["unexplained_usd"] == pytest.approx(0.0)
        assert rows[0]["direction_inverts"] is False

    def test_the_gap_equals_the_compounding_growth(self):
        """CAP/USD-shaped: config 50.00, live 55.41."""
        rows = analyse({"bots": {"a": _bot("CAP/USD", 1.0, 53.31, 50.0, 55.41)}})
        assert rows[0]["unexplained_usd"] == pytest.approx(5.41)

    def test_both_deltas_are_reported(self):
        rows = analyse({"bots": {"a": _bot("CAP/USD", 1.0, 53.31, 50.0, 55.41)}})
        assert rows[0]["delta_if_config"] == pytest.approx(3.31)
        assert rows[0]["delta_if_live"] == pytest.approx(-2.10, abs=0.01)

    def test_the_quote_rate_is_applied(self):
        rows = analyse(
            {"bots": {"a": _bot("X/BTC", 2.0, 50.0, 100.0, 100.0, qrate=3.0)}}
        )
        assert rows[0]["position"] == pytest.approx(300.0)

    def test_units_sum_across_lots_and_junk_is_skipped(self):
        rec = _bot("X/USD", 0, 2.0, 10.0, 10.0)
        rec["scrumming_state"]["main_lots"] = [
            {"units": 4.0},
            "junk",
            None,
            {"units": 6.0},
        ]
        rows = analyse({"bots": {"a": rec}})
        assert rows[0]["position"] == pytest.approx(20.0)

    def test_a_zero_config_order_does_not_divide_by_zero(self):
        rows = analyse({"bots": {"a": _bot("X/USD", 1.0, 50.0, 50.0, 51.0)}})
        assert rows[0]["gap_pct_of_order"] == float("inf")


class TestTheSignFlipIsCaught:
    """A wrong-sized order is a rounding complaint. A wrong-DIRECTION
    order moves the position the wrong way."""

    def test_opposite_directions_are_flagged(self):
        rows = analyse({"bots": {"a": _bot("CAP/USD", 1.0, 53.31, 50.0, 55.41)}})
        assert rows[0]["direction_inverts"] is True

    def test_same_direction_is_not_flagged(self):
        """Both readings say sell; only the size differs."""
        rows = analyse({"bots": {"a": _bot("ETH/USD", 1.0, 206.38, 200.0, 200.38)}})
        assert rows[0]["delta_if_config"] > 0 and rows[0]["delta_if_live"] > 0
        assert rows[0]["direction_inverts"] is False

    def test_an_exactly_zero_delta_is_not_an_inversion(self):
        """0 * x is not negative; a bot sitting exactly on target must
        not be reported as flipping."""
        rows = analyse({"bots": {"a": _bot("X/USD", 1.0, 50.0, 50.0, 52.0)}})
        assert rows[0]["delta_if_config"] == pytest.approx(0.0)
        assert rows[0]["direction_inverts"] is False


class TestTheInstrumentFailsLoudly:
    def test_all_zero_positions_is_reported_as_failure(self, capsys, tmp_path):
        """THE control. A prior hand-run of a sibling comparison read a
        field that is not persisted, got zero everywhere, and printed a
        clean bill of health. Measuring nothing must not look like a
        pass."""
        p = tmp_path / "s.json"
        p.write_text(
            json.dumps(
                {
                    "bots": {
                        "a": _bot("X/USD", 0.0, 0.0, 50.0, 55.0),
                        "b": _bot("Y/USD", 0.0, 0.0, 25.0, 25.0),
                    }
                }
            ),
            encoding="utf-8",
        )
        assert main(["--state", str(p)]) == 3
        assert "INSTRUMENT FAILURE" in capsys.readouterr().err

    def test_a_working_run_reports_the_control(self, capsys, tmp_path):
        """NEGATIVE CONTROL: the failure path must not fire on good data."""
        p = tmp_path / "s.json"
        p.write_text(
            json.dumps({"bots": {"a": _bot("BTC/USD", 1.0, 250.0, 250.0, 250.0)}}),
            encoding="utf-8",
        )
        assert main(["--state", str(p)]) == 0
        assert "positive control: 1/1" in capsys.readouterr().out

    def test_divergence_sets_a_nonzero_exit(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(
            json.dumps({"bots": {"a": _bot("CAP/USD", 1.0, 53.31, 50.0, 55.41)}}),
            encoding="utf-8",
        )
        assert main(["--state", str(p)]) == 1

    def test_a_missing_state_file_is_not_a_pass(self, tmp_path):
        assert main(["--state", str(tmp_path / "nope.json")]) == 2


class TestItNeverWrites:
    def test_the_harness_has_no_write_calls(self):
        """It reads the operator's live runtime tree."""
        import ast

        import dev_harness.harness.manual_fire_frame_check as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        banned = {
            "write_text",
            "write_bytes",
            "mkdir",
            "unlink",
            "rename",
            "replace",
            "rmtree",
            "remove",
        }
        called = {
            getattr(c.func, "attr", "")
            for c in ast.walk(ast.parse(src))
            if isinstance(c, ast.Call)
        }
        assert not (called & banned), f"harness can write: {called & banned}"

    def test_it_constructs_no_project_classes(self):
        """Project defaults resolve into ~/.acervator."""
        import dev_harness.harness.manual_fire_frame_check as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        assert "from src." not in src
        assert "import src" not in src
