"""Phase 1 Step 3 — the compounding surface must be visible.

WHY THIS IS NOT COSMETIC
`get_status` exported `"target_balance": self.config.target_balance` --
the operator's INPUT value, which compounding does not move -- and never
exported the runtime `_target_balance` the bot actually trades against.
So no GUI could show whether compounding had done anything, which is the
mechanism behind the target-delta drift docket and a large part of why
"compounding has never functioned globally" went unnoticed for the
platform's whole life.

Phase 2 and Phase 3 MOVE the target balance. Without this surface there
is no way to tell whether they worked, and the plan would repeat the
failure mode it exists to fix.

THE LIVE-MONEY TRAP, HONOURED
The Target Balance spinbox must keep showing `cfg.target_balance`. The
change-detector diffs edits against that field, so a spinbox holding the
GROWN value would register as an operator edit on every panel open and
could fire `set_target_balance_live`, which collapses the anchor and
wipes accrued growth. Showing the truth in the input box would destroy
the thing it was showing. The grown value goes in a read-only row, and
the first test below pins that the spinbox was not repointed.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.gui.bot_live_settings as bls  # noqa: E402
import src.trading.bot_container as bc  # noqa: E402

GUI_SRC = Path(bls.__file__).read_text(encoding="utf-8")
BC_SRC = Path(bc.__file__).read_text(encoding="utf-8")

NEW_KEYS = (
    "live_target_balance",
    "standing_surplus_usd",
    "fold_cycle_cap_consumed",
    "cycle_growth_budget_usd",
    "tranches_over_cycle_cap",
    "tranches_over_cycle_cap_usd",
)


def _get_status_src() -> str:
    """Give the source of `BotContainer.get_status`, found by its CLASS.

    THE LOCATOR WAS A LINE WINDOW, `1314 < lineno < 1614`, and issue
    #103 measured what that costs: inserting 189 lines ABOVE the class,
    in a part of the file this test says nothing about, pushed the
    method past 1614 and turned nine assertions into "get_status not
    found" - a locator failure wearing the costume of a missing export.

    The window was disambiguation, and it was never needed. There is
    exactly ONE `get_status` in `bot_container.py` and it is a method
    of `BotContainer`. Walking to the class and then to its own body
    names that method exactly, and no edit anywhere else in the file
    can move it out of range.
    """
    for node in ast.walk(ast.parse(BC_SRC)):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name != "BotContainer":
            continue
        for sub in node.body:
            if isinstance(sub, ast.FunctionDef) and sub.name == "get_status":
                return ast.get_source_segment(BC_SRC, sub) or ""
    raise AssertionError("BotContainer.get_status not found in bot_container.py")


class TestTheSpinboxWasNotRepointed:
    """THE trap. Getting this wrong wipes accrued growth on every open."""

    def test_the_spinbox_still_shows_the_config_value(self):
        i = GUI_SRC.index("self._target_bal.setValue(")
        line = GUI_SRC[i : GUI_SRC.index("\n", i)]
        assert "cfg.target_balance" in line, (
            f"the Target Balance spinbox was repointed ({line.strip()}); "
            f"the change-detector will read every panel open as an edit "
            f"and set_target_balance_live will collapse the anchor"
        )

    def test_it_does_not_show_the_runtime_target(self):
        i = GUI_SRC.index("self._target_bal.setValue(")
        line = GUI_SRC[i : GUI_SRC.index("\n", i)]
        assert "_target_balance" not in line


class TestTheStatusDictCarriesTheSurface:
    @pytest.mark.parametrize("key", NEW_KEYS)
    def test_the_key_is_exported(self, key):
        assert (
            f'"{key}"' in _get_status_src()
        ), f"{key} is not exported; no GUI can show it"

    def test_the_config_value_is_still_exported(self):
        """NEGATIVE CONTROL: the additions must not displace the field
        existing consumers read."""
        assert '"target_balance": self.config.target_balance' in _get_status_src()

    def test_live_and_config_targets_are_different_keys(self):
        """They are different quantities. Collapsing them into one key
        is the defect, not the fix."""
        seg = _get_status_src()
        assert '"live_target_balance"' in seg
        assert '"target_balance"' in seg

    def test_the_over_cap_summary_cannot_raise(self):
        """A status call that raises takes the dashboard down. The
        arithmetic is wrapped."""
        seg = _get_status_src()
        i = seg.index("_over_cap_summary")
        assert "try:" in seg[i : i + 400]
        assert "except" in seg[i : i + 900]


class TestTheGuiRendersThem:
    def test_the_live_target_row_exists(self):
        assert "Live target (traded against):" in GUI_SRC

    def test_it_reads_the_runtime_value(self):
        i = GUI_SRC.index("Live target (traded against):")
        assert "_target_balance" in GUI_SRC[max(0, i - 2200) : i]

    def test_zero_accrual_is_stated_not_left_as_a_bare_zero(self):
        """Zero accrual is the condition the whole repair exists to
        change. A bare 0.0000 reads as normal."""
        assert "never compounded" in GUI_SRC

    def test_the_standing_surplus_row_exists(self):
        assert "Standing surplus:" in GUI_SRC

    def test_the_cycle_budget_row_exists(self):
        assert "Cycle growth budget:" in GUI_SRC

    def test_the_over_cap_row_exists(self):
        assert "Over-cap tranches:" in GUI_SRC


class TestTheStaleClaimWasCorrected:
    def test_the_comment_no_longer_claims_it_is_already_surfaced(self):
        """It said "Surfaced for visibility (Status tab + diagnostics)"
        while a grep of src/gui/ for `standing_surplus` returned zero
        matches."""
        i = BC_SRC.index("standing_surplus_usd: float = 0.0")
        block = BC_SRC[max(0, i - 1400) : i]
        assert "Surfaced for visibility (Status tab + diagnostics)." not in block

    def test_the_comment_no_longer_claims_a_drain_exists(self):
        """It said the growth budget "drains it into target_balance over
        time". `_standing_surplus_usd` has no decrement anywhere in
        src/; that drain is Phase 2 Step 7 and has not landed."""
        i = BC_SRC.index("standing_surplus_usd: float = 0.0")
        block = BC_SRC[max(0, i - 1400) : i]
        assert "one-way sink" in block

    def test_it_is_now_actually_surfaced(self):
        """The sentence is made true by the code, not by the sentence."""
        assert "standing_surplus" in GUI_SRC
