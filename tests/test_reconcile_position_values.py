"""Pins for the position-value reconciliation harness.

The harness answers the operator's item 3: "Target Delta (Ammo) needs to
be compared against API inputs to ensure a miscalculation is not
happening."

WHAT IT IS AND IS NOT
It is an INTERNAL consistency check. Both sides come from the platform's
own persisted record:

    cached     = stats.position_value
    recomputed = sum(main_lots[].units) x current_price x quote_to_usd

It cannot detect an error that corrupts units and position_value
identically, and it is not an exchange reconciliation. It detects
STALENESS -- the two fields are written at different moments, and when
they drift the cached one is wrong.

WHY IT IS WORTH HAVING ANYWAY
Measured against live state 2026-08-06: 11 of 35 bots diverged by more
than 1%, worst ORCA/USD at 11.53%. The per-bot Ammo is unaffected (C10
made it recompute) and so is the manual-fire engine
(scrumming_bot.py:9246), but bot_container.py:3382 sums the CACHED field
into the fleet total, understating it by $35.45 against $3,311.82.

THE INSTRUMENT HAS A POSITIVE CONTROL, and that is the point
An earlier hand-run of this same comparison read `current_holdings` --
which is not persisted at all -- got 0.000000 for every bot, and printed
"0 bots diverge". A clean bill of health produced by measuring nothing.
The harness now fails loudly when every recomputed value is zero, and
these tests pin that behaviour.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.harness.reconcile_position_values import main, reconcile  # noqa: E402


def _bot(symbol, units, price, cached, qrate=1.0, lots=None):
    return {
        "config": {"symbol": symbol},
        "stats": {"current_price": price, "position_value": cached},
        "scrumming_state": {
            "quote_to_usd": qrate,
            "main_lots": lots if lots is not None
            else [{"units": units, "initial_buy_price": price}],
        },
    }


class TestTheArithmetic:
    def test_an_agreeing_bot_reads_zero(self):
        rows = reconcile({"bots": {"a": _bot("BTC/USD", 2.0, 50.0, 100.0)}})
        assert rows[0]["divergence_usd"] == pytest.approx(0.0)
        assert rows[0]["divergence_pct"] == pytest.approx(0.0)

    def test_a_stale_bot_is_measured(self):
        """ORCA-shaped: cached is below the recomputed value."""
        rows = reconcile({"bots": {"a": _bot("ORCA/USD", 2.0, 50.0, 90.0)}})
        assert rows[0]["recomputed_position_value"] == pytest.approx(100.0)
        assert rows[0]["divergence_usd"] == pytest.approx(-10.0)
        assert rows[0]["divergence_pct"] == pytest.approx(11.11, abs=0.01)

    def test_the_quote_rate_is_applied(self):
        """Crypto-quoted pairs evaluate in USD (v3.15.55)."""
        rows = reconcile({"bots": {"a": _bot("X/BTC", 2.0, 50.0, 300.0,
                                             qrate=3.0)}})
        assert rows[0]["recomputed_position_value"] == pytest.approx(300.0)

    def test_units_sum_across_all_lots(self):
        rows = reconcile({"bots": {"a": _bot(
            "CHIP/USD", 0, 2.0, 20.0,
            lots=[{"units": 4.0}, {"units": 6.0}])}})
        assert rows[0]["units"] == pytest.approx(10.0)
        assert rows[0]["recomputed_position_value"] == pytest.approx(20.0)

    def test_junk_lot_entries_are_skipped_not_crashed_on(self):
        rows = reconcile({"bots": {"a": _bot(
            "X/USD", 0, 2.0, 8.0,
            lots=[{"units": 4.0}, "not-a-dict", None])}})
        assert rows[0]["recomputed_position_value"] == pytest.approx(8.0)

    def test_a_zero_cached_value_does_not_divide_by_zero(self):
        rows = reconcile({"bots": {"a": _bot("X/USD", 1.0, 1.0, 0.0)}})
        assert rows[0]["divergence_pct"] == 0.0


class TestTheInstrumentFailsLoudly:
    def test_all_zero_recompute_is_reported_as_failure(self, capsys, tmp_path):
        """THE control. An earlier hand-run of this comparison read a
        field that is not persisted, got zero everywhere, and printed a
        clean bill of health. Measuring nothing must not look like a
        pass."""
        import json

        p = tmp_path / "state.json"
        p.write_text(json.dumps({"bots": {
            "a": _bot("X/USD", 0.0, 0.0, 100.0, lots=[]),
            "b": _bot("Y/USD", 0.0, 0.0, 50.0, lots=[]),
        }}), encoding="utf-8")
        rc = main(["--state", str(p)])
        assert rc == 3, "an all-zero recompute must not exit 0 or 1"
        assert "INSTRUMENT FAILURE" in capsys.readouterr().err

    def test_a_working_run_reports_the_control(self, capsys, tmp_path):
        """NEGATIVE CONTROL: the failure path must not fire on good
        data, or the tool is useless."""
        import json

        p = tmp_path / "state.json"
        p.write_text(json.dumps({"bots": {
            "a": _bot("BTC/USD", 2.0, 50.0, 100.0)}}), encoding="utf-8")
        rc = main(["--state", str(p)])
        assert rc == 0
        assert "positive control: 1/1" in capsys.readouterr().out

    def test_a_missing_state_file_is_not_a_pass(self, tmp_path):
        assert main(["--state", str(tmp_path / "nope.json")]) == 2

    def test_divergence_sets_a_nonzero_exit(self, tmp_path):
        """So it can gate in CI without anyone reading the output."""
        import json

        p = tmp_path / "state.json"
        p.write_text(json.dumps({"bots": {
            "a": _bot("ORCA/USD", 2.0, 50.0, 90.0)}}), encoding="utf-8")
        assert main(["--state", str(p), "--threshold", "1.0"]) == 1


class TestItNeverWrites:
    def test_the_harness_has_no_write_calls(self):
        """It reads the operator's live runtime tree. It must not be one
        edit away from writing to it."""
        import ast

        import tools.harness.reconcile_position_values as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        banned = {"write_text", "write_bytes", "mkdir", "unlink", "rename",
                  "replace", "rmtree", "remove"}
        called = {getattr(c.func, "attr", "") for c in ast.walk(ast.parse(src))
                  if isinstance(c, ast.Call)}
        assert not (called & banned), f"harness can write: {called & banned}"

    def test_it_constructs_no_project_classes(self):
        """Project defaults resolve into ~/.acervator."""
        import tools.harness.reconcile_position_values as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        assert "from src." not in src
        assert "import src" not in src
