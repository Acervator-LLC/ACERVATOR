"""Phase 1 Step 5 — a failed restore must not destroy the saved record.

THE DEFECT
`restore_bots_from_state` caught an `import_scrumming_state` exception,
set `_state_import_failed`, called `_ledger_skip`, logged an ERROR whose
own text read:

    "so the next save would overwrite its persisted lots and tranches.
     Do not let that record be replaced."

...and then fell straight through to `register(bot)` with DEFAULT state.
Nothing acted on the warning it had just printed. Sixty seconds later the
save timer wrote 0 lots and 0 tranches over the good record. On the
largest queue in the fleet that is roughly 200 tranches plus every lot's
cost basis, destroyed by one malformed field.

THE FIX, AND WHY IT IS THE SMALL ONE
Skipping registration is what protects the record. A bot absent from
`self._bots` is absent from the dict `save_state` rebuilds, and
`state_manager`'s carry-forward keys on exactly that absence
(`carried = [bid for bid in on_disk if bid not in state["bots"]]`), so
the on-disk record is copied forward untouched. No new persistence path
was added; an existing one is allowed to do its job.

WHAT IS BEING PROTECTED
`import_scrumming_state` is NOT transactional -- it applies fields
sequentially -- so the in-memory object after a failure is PARTIALLY
applied, not cleanly zeroed. That is precisely why it must not be saved
from.

THE VISIBLE BEHAVIOUR CHANGE
A bot that fails import no longer appears in the fleet. That must never
read as a silent deletion, so it ships with an operator-facing banner
naming the bot, the exception, and the fact that the saved state is
intact.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.trading.bot_container as bc  # noqa: E402
import src.core.state_manager as sm  # noqa: E402

BC_SRC = Path(bc.__file__).read_text(encoding="utf-8")
SM_SRC = Path(sm.__file__).read_text(encoding="utf-8")


def _restore_fn() -> ast.AST:
    for n in ast.walk(ast.parse(BC_SRC)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.name == "restore_bots_from_state":
            return n
    raise AssertionError("restore_bots_from_state not found")


def _handler() -> ast.ExceptHandler:
    """The except block wrapping import_scrumming_state."""
    for node in ast.walk(_restore_fn()):
        if not isinstance(node, ast.Try):
            continue
        body = ast.unparse(node)
        if "import_scrumming_state" in body and node.handlers:
            return node.handlers[0]
    raise AssertionError("no try/except around import_scrumming_state")


class TestTheExtractorWorks:
    def test_it_finds_the_handler(self):
        """POSITIVE CONTROL: if the handler could not be located every
        assertion below would pass vacuously."""
        assert isinstance(_handler(), ast.ExceptHandler)

    def test_the_handler_still_records_the_failure(self):
        """NEGATIVE CONTROL: the fix must not have removed the existing
        bookkeeping while adding the skip."""
        body = ast.unparse(_handler())
        assert "_state_import_failed" in body
        assert "_ledger_skip" in body


class TestTheBotIsNotRegistered:
    def test_the_handler_skips_registration(self):
        """THE fix. Without this the bot reaches register() with
        partially-applied state and the next save overwrites disk."""
        assert any(isinstance(n, ast.Continue)
                   for n in ast.walk(_handler())), (
            "the failure handler falls through to register(); the next "
            "save will overwrite the good record with defaults")

    def test_registration_still_happens_on_the_success_path(self):
        """NEGATIVE CONTROL: skipping on failure must not skip always."""
        seg = ast.unparse(_restore_fn())
        assert "self.register(bot)" in seg


class TestTheCarryForwardIsTheProtection:
    def test_state_manager_carries_absent_records(self):
        """The whole fix rests on this mechanism existing. If it is ever
        removed, skipping registration would DELETE the bot instead of
        protecting it -- so this pin fails loudly rather than letting
        that happen silently."""
        assert 'carried = [bid for bid in on_disk if bid not in state["bots"]]' \
            in SM_SRC, "the absence-keyed carry-forward is gone"

    def test_it_copies_the_on_disk_record_back(self):
        assert 'state["bots"][bid] = on_disk[bid]' in SM_SRC


class TestTheOperatorIsTold:
    def test_a_banner_is_emitted(self):
        """A bot vanishing from the fleet must not read as a deletion."""
        body = ast.unparse(_handler())
        assert "bot.restore_failed" in body

    def test_the_banner_names_the_bot_and_the_error(self):
        body = ast.unparse(_handler())
        assert "bot_id" in body
        assert "symbol" in body
        assert "error" in body

    def test_it_says_the_saved_state_is_intact(self):
        """Otherwise the operator's reasonable response to a missing bot
        is to recreate it, which is the one action that would destroy
        the record this change exists to protect."""
        body = ast.unparse(_handler())
        assert "INTACT" in body or "intact" in body

    def test_a_failed_banner_is_itself_logged(self):
        """If the notice cannot be shown, a bot is missing with no
        operator-facing trace -- that must not pass silently."""
        body = ast.unparse(_handler())
        assert body.count("logger.error") >= 2
