"""Issue #133 unit 8 — Stack Tranches are ON by default.

Three populations, three different answers, and the middle one is the
control that matters:

  a NEW bot                     -> ON (nothing stored, default applies)
  a bot with a stored value     -> that value, ON or OFF, untouched
  a bot saved BEFORE the field  -> ON (nothing stored, default applies)

The second row is what separates a DEFAULT from an OVERRIDE. All 38
bots in the operator's ``bot_state.json`` store ``stack_mode: False``.
A change that reads True for them overrode 38 live settings, and it
would still pass every new-bot test in this file.

WHAT A FAILURE MEANS, per class, stated before the run:

  TestANewBotComesUpOn — a new bot is built with the Stack side
      dormant, so the directive never reached the construction path.

  TestAStoredValueSurvives — the default is acting as an override: the
      value the operator set on a live bot was replaced at restore
      time. Blast radius: 38 bots start splitting every SCRUM into a
      stack ladder without being asked.

  TestPreFieldStateGetsTheDefault — a state file written before the
      field existed either crashes the restore, or resolves through the
      retired ``bulk_trading`` key to a stale False, so the bot comes
      up on the old default.

  TestOneDeclarationSite — a literal was re-hardcoded at a fallback, so
      the declared default and the value a bot gets have drifted.

The restore fixtures are built from the operator's real
``bot_state.json`` (read-only, 72 config keys per bot), not from a
hand-written dict shaped to suit the assertion.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.bot_container import (  # noqa: E402
    STACK_MODE_DEFAULT,
    BotConfig,
    BotManager,
    BotMode,
    make_bot_config,
)

_REQ = {
    "exchange_id": "coinbase",
    "base_currency": "USD",
    "target_asset": "BTC",
    "target_balance": 200.0,
}

_LIVE_STATE = Path(os.path.expanduser("~/.acervator/bot_state.json"))


def _live_configs() -> list[tuple[str, dict]]:
    """Every scrumming config in the operator's state file. READ ONLY."""
    if not _LIVE_STATE.is_file():
        return []
    try:
        data = json.loads(_LIVE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: list[tuple[str, dict]] = []
    for bid, entry in (data.get("bots") or {}).items():
        cfg = entry.get("config") if isinstance(entry, dict) else None
        if isinstance(cfg, dict) and (cfg.get("mode") or "").lower() == "scrumming":
            out.append((str(bid), dict(cfg)))
    return out


def _restore_one(bot_id: str, cfg: dict) -> BotConfig:
    """Drive the REAL restore path and hand back the built BotConfig."""
    mgr = BotManager()
    mgr.restore_bots_from_state({"bots": {bot_id: {"bot_id": bot_id, "config": cfg}}})
    assert bot_id in mgr._bots, f"restore refused {bot_id}: {dict(mgr._restore_ledger)}"
    return mgr._bots[bot_id].config


# ---------------------------------------------------------------------------
# A new bot comes up ON
# ---------------------------------------------------------------------------


class TestANewBotComesUpOn:
    def test_the_declared_default_is_on(self):
        assert STACK_MODE_DEFAULT is True

    def test_the_dataclass_field_carries_it(self):
        f = {x.name: x for x in dataclasses.fields(BotConfig)}["stack_mode"]
        assert f.default is STACK_MODE_DEFAULT
        assert f.default is True

    def test_a_new_scrumming_bot_is_on(self):
        cfg = make_bot_config(BotMode.SCRUMMING, **_REQ)
        assert cfg.stack_mode is True

    def test_a_new_extractor_bot_is_on(self):
        """``stack_mode`` is a SHARED field, so the factory accepts it
        on both modes. No Extractor path reads it; this pins that the
        two modes do not disagree about the default."""
        cfg = make_bot_config(
            BotMode.EXTRACTOR,
            exchange_id="coinbase",
            base_currency="USD",
            target_asset="*",
            target_balance=200.0,
        )
        assert cfg.stack_mode is True

    def test_the_wizard_checkbox_starts_checked(self):
        """The operator's own new-bot surface, DRIVEN. A dataclass
        default the wizard then overwrites with an unchecked box is not
        a default, and a text scan cannot tell a laid-out box from an
        orphan. Read off the real widget and off the payload the
        wizard hands `_create_bot`, which is what a bot is built from.
        """
        pytest.importorskip("PySide6.QtWidgets")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.bot_wizard import BotCreationWizard

        wizard = BotCreationWizard([], {}, None)
        try:
            pages = [wizard.page(i) for i in wizard.pageIds()]
            boxes = [p for p in pages if getattr(p, "_stack_mode", None)]
            assert len(boxes) == 1, f"{len(boxes)} pages carry a Stack Mode box"
            page = boxes[0]
            assert (
                page._stack_mode.parentWidget() is not None
            ), "the Stack Mode box was constructed but never laid out"
            assert page._stack_mode.isChecked() is True
            assert page.get_config()["stack_mode"] is True
        finally:
            wizard.deleteLater()

    def test_the_new_value_round_trips_through_the_save_shape(self):
        """``get_full_state`` persists ``asdict(self.config)``. A
        default that is not written out is a default that reverts."""
        cfg = make_bot_config(BotMode.SCRUMMING, **_REQ)
        saved = dataclasses.asdict(cfg)
        assert saved["stack_mode"] is True
        again = _restore_one("fresh", {**saved, "mode": "scrumming"})
        assert again.stack_mode is True


# ---------------------------------------------------------------------------
# THE CONTROL — a stored value is never overridden
# ---------------------------------------------------------------------------


class TestAStoredValueSurvives:
    def test_an_explicit_false_kwarg_survives_construction(self):
        cfg = make_bot_config(BotMode.SCRUMMING, **_REQ, stack_mode=False)
        assert cfg.stack_mode is False

    def test_a_stored_false_survives_the_real_restore_path(self):
        cfg = _restore_one(
            "stored-off",
            {
                "exchange_id": "coinbase",
                "symbol": "BTC/USD",
                "mode": "scrumming",
                "stack_mode": False,
            },
        )
        assert cfg.stack_mode is False

    def test_a_stored_true_survives_the_real_restore_path(self):
        cfg = _restore_one(
            "stored-on",
            {
                "exchange_id": "coinbase",
                "symbol": "BTC/USD",
                "mode": "scrumming",
                "stack_mode": True,
            },
        )
        assert cfg.stack_mode is True

    def test_every_live_bot_reads_back_what_the_file_stores(self):
        """SECOND WITNESS on a different code path: the JSON value on
        disk and the attribute on the constructed bot must agree, bot
        by bot. This is the assertion that fails if the change turned
        the default into an override."""
        live = _live_configs()
        if not live:
            pytest.skip("no ~/.acervator/bot_state.json on this machine")
        stored_off = [b for b in live if b[1].get("stack_mode") is False]
        assert stored_off, (
            "the fleet no longer stores an explicit False anywhere, so "
            "this control can no longer discriminate"
        )
        for bot_id, cfg in live:
            want = cfg.get("stack_mode")
            got = _restore_one(bot_id, cfg).stack_mode
            assert got is want, (
                f"bot {bot_id}: file says {want!r}, restored bot says "
                f"{got!r} — the default overrode a stored setting"
            )


# ---------------------------------------------------------------------------
# A state file older than the field
# ---------------------------------------------------------------------------


class TestPreFieldStateGetsTheDefault:
    def test_the_deprecated_kwarg_does_not_raise(self):
        """``bulk_trading`` reaches ``make_bot_config`` from any state
        file written before the rename."""
        cfg = make_bot_config(
            BotMode.SCRUMMING,
            **_REQ,
            bulk_trading=False,
            bulk_partial_on_return=True,
        )
        assert cfg.stack_mode is True

    def test_a_pre_field_config_restores_to_the_new_default(self):
        """Built from a REAL live config with the field removed and the
        retired key put back — the shape a pre-rename save left on
        disk."""
        live = _live_configs()
        if not live:
            pytest.skip("no ~/.acervator/bot_state.json on this machine")
        bot_id, cfg = live[0]
        pre = {k: v for k, v in cfg.items() if k != "stack_mode"}
        pre["bulk_trading"] = False
        assert "stack_mode" not in pre
        got = _restore_one(bot_id, pre).stack_mode
        assert got is True, (
            f"a pre-field state file resolved to {got!r} — the retired "
            "`bulk_trading` key is still read as the Stack Mode "
            "setting, so the bot came up on the old default"
        )

    def test_a_bare_pre_field_config_restores_to_the_new_default(self):
        """The same file without even the retired key."""
        cfg = _restore_one(
            "bare",
            {"exchange_id": "coinbase", "symbol": "BTC/USD", "mode": "scrumming"},
        )
        assert cfg.stack_mode is True


# ---------------------------------------------------------------------------
# One declaration, no re-hardcoded literals
# ---------------------------------------------------------------------------


class TestOneDeclarationSite:
    def test_the_restore_path_reads_the_declaration(self):
        src = (REPO / "src" / "trading" / "container" / "restore.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert '"stack_mode": cfg.get("stack_mode", STACK_MODE_DEFAULT)' in src, (
            "the SCRUMMING restore path no longer resolves an absent "
            "`stack_mode` through STACK_MODE_DEFAULT"
        )

    def test_the_restore_path_no_longer_consults_the_retired_key(self):
        src = (REPO / "src" / "trading" / "container" / "restore.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert 'cfg.get("bulk_trading"' not in src, (
            "`bulk_trading` was always False, so reading it as the "
            "Stack Mode fallback resolves a pre-field state file to a "
            "stale False instead of the current default"
        )
