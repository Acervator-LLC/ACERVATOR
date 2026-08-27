"""The Ammo readout and Manual Fire must mean the same target.

OPERATOR REPORT
"Manual fire is not re-zeroing the bot to the Target Balance as expected
and required. I am seeing strange, intermittent and hard to explain
amounts being transacted."

THE MECHANISM
The Ammo cell read `status["target_balance"]`, which `get_status` fills
from `config.target_balance` -- the operator's INPUT, frozen, and never
moved by compounding.

`_execute_manual_rebalance` sizes its trade from
`delta_usd = current_value - self._target_balance`: the LIVE grown value.

So the readout measured distance to one target and the button re-zeroed
to another. The trade differed from the displayed Ammo by exactly the
accrued growth.

WHY IT LOOKED INTERMITTENT
Measured against live state 2026-08-06: 26 of 35 bots carried accrued
growth and were mismatched; 9 carried none and behaved perfectly. So the
same button was correct on some bots and wrong on others with no visible
pattern. Largest gap CAP/USD, $5.41 against a $50 target -- 10.83%.

    SYMBOL      GUI showed   engine used   gap
    CAP/USD         50.00         55.41   +5.41   (10.83%)
    BILL/USD       250.00        253.10   +3.10
    GROVE/USD      100.00        102.61   +2.61
    ...
    RAVE/USD        50.00         50.00   +0.00   (never compounded)

WHICH ONE IS CORRECT
The engine. The operator's stated invariant is that compounding is the
only mechanism besides a user edit permitted to move Target Balance --
so the bot SHOULD trade against the grown value, and the display was the
side that was wrong. This is a display-only change: no order size, no
order timing, and no engine path is touched.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.gui.main_window as mw  # noqa: E402
import src.trading.scrumming_bot as sbm  # noqa: E402


def _owning_source(owner, method_name: str) -> str:
    """Source of the file that really defines ``method_name``."""
    import inspect

    path = inspect.getsourcefile(getattr(owner, method_name))
    assert path is not None, method_name
    return Path(path).read_text(encoding="utf-8")


GUI_SRC = _owning_source(mw.BotStatusTable, "update_bots")
BOT_SRC = Path(sbm.__file__).read_text(encoding="utf-8")


def _target_val_line() -> str:
    """The statement that binds `target_val` in update_bots."""
    tree = ast.parse(GUI_SRC)
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
            getattr(t, "id", "") == "target_val" for t in n.targets
        ):
            return ast.unparse(n.value)
    raise AssertionError("target_val is never assigned")


class TestTheExtractorWorks:
    def test_target_val_is_assigned(self):
        """POSITIVE CONTROL for every assertion below."""
        assert _target_val_line()


class TestTheDisplayUsesTheEngineTarget:
    def test_it_reads_the_live_target(self):
        assert "live_target_balance" in _target_val_line(), (
            "the Ammo is measured against config.target_balance while "
            "Manual Fire re-zeroes to the live grown target"
        )

    def test_it_falls_back_to_the_config_value(self):
        """A bot type that does not export the live key must render as
        before, not as 0.00 -- which would read as 'at target' and is
        the worst possible wrong answer on this cell."""
        assert "target_balance" in _target_val_line()

    def test_the_engine_still_sizes_from_the_live_target(self):
        """The other half of the agreement. If the ENGINE ever moved to
        the config value, this fix would silently invert the mismatch
        instead of removing it."""
        fn = next(
            n
            for n in ast.walk(ast.parse(BOT_SRC))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_execute_manual_rebalance"
        )
        seg = ast.get_source_segment(BOT_SRC, fn) or ""
        assert "current_value - self._target_balance" in seg
        assert "config.target_balance" not in seg


class TestTheArithmeticAgrees:
    """The property that matters: for the same position, the Ammo and
    the manual-rebalance delta must be the same number."""

    @pytest.mark.parametrize(
        "cfg,live,pos",
        [
            (50.00, 55.41, 60.00),  # CAP/USD, the worst live mismatch
            (250.00, 253.10, 240.00),  # BILL/USD, fold side
            (50.00, 50.00, 55.00),  # RAVE/USD, never compounded
            (100.00, 102.61, 102.61),  # exactly at the live target
        ],
    )
    def test_display_delta_equals_engine_delta(self, cfg, live, pos):
        from src.gui.table_cells import _compose_ammo_cell

        # The display, post-fix, resolves target_val to the live value.
        cell = _compose_ammo_cell(
            stats_pv=pos, holdings=1.0, cur_price=pos, qrate=1.0, target_val=live
        )
        engine_delta = pos - live
        assert cell["delta"] == pytest.approx(engine_delta), (
            f"Ammo shows {cell['delta']:+.4f} but Manual Fire would "
            f"transact against {engine_delta:+.4f}"
        )

    def test_the_old_behaviour_disagreed(self):
        """POSITIVE CONTROL on the whole premise: using the config value
        must produce a DIFFERENT delta, or there was never a bug."""
        from src.gui.table_cells import _compose_ammo_cell

        cfg, live, pos = 50.00, 55.41, 60.00
        old = _compose_ammo_cell(pos, 1.0, pos, 1.0, cfg)["delta"]
        new = _compose_ammo_cell(pos, 1.0, pos, 1.0, live)["delta"]
        assert old != pytest.approx(new)
        assert abs(old - new) == pytest.approx(5.41)

    def test_a_bot_at_its_live_target_reads_as_dust(self):
        """The operator's actual requirement: Manual Fire re-zeroes the
        bot, so a re-zeroed bot must then read as at-target."""
        from src.gui.table_cells import _compose_ammo_cell

        cell = _compose_ammo_cell(102.61, 1.0, 102.61, 1.0, 102.61)
        assert abs(cell["delta"]) < 0.01
