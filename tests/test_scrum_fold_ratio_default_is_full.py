"""Issue #133 unit 9 defect A — the Scrum Fold Ratio default is 100.

Operator ruling, 2026-08-26: *"I should have Scrum Fold ratio at 100%
for all bots. This should be the setting that controls this."*

``scrum_fold_pct`` IS the right control and it is applied where it
belongs. This file pins its DEFAULT and, more importantly, pins that a
default is not an override.

Three populations, three answers, and the middle one is the control:

  a NEW bot                     -> 100 (nothing stored, default applies)
  a bot with a stored value     -> that value, 50 or 100, untouched
  a bot saved BEFORE the field  -> 100 (nothing stored, default applies)

The second row is what separates a DEFAULT from an OVERRIDE. Eight of
the operator's 38 bots store ``scrum_fold_pct: 50``, CHIP/USD among
them. A change that reads 100 for those eight overrode eight live
settings, and it would still pass every new-bot test here.

WHAT A FAILURE MEANS, per class, stated before the run:

  TestANewBotFoldsTheWholeScrum — a new bot is built folding back only
      part of a scrum, so the ruling never reached the construction
      path.

  TestAStoredValueSurvives — the default is acting as an override. The
      ratio the operator set on a live bot was replaced at restore
      time. Blast radius: eight bots start folding the whole scrum
      back without being asked, and their cash buffer stops building.

  TestPreFieldStateGetsTheDefault — a state file written before the
      field existed crashes the restore, or comes up on a stale value.

  TestEveryDeclarationSiteAgrees — the five places that decide this
      value have drifted, so the declared default and the value a bot
      actually gets are no longer the same number.

The restore fixtures are built from the operator's real
``bot_state.json`` (read-only), not from a dict shaped to suit the
assertion.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.bot_container import (  # noqa: E402
    BotConfig,
    BotManager,
    BotMode,
    make_bot_config,
)

#: The operator's ruling. Every site below must resolve to this.
FOLD_PCT_DEFAULT = 100

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


def _src(*parts: str) -> str:
    """Read one repository source file as text."""
    return (REPO.joinpath(*parts)).read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# A new bot folds the whole scrum back
# ---------------------------------------------------------------------------


class TestANewBotFoldsTheWholeScrum:
    def test_the_dataclass_field_carries_the_default(self):
        f = {x.name: x for x in dataclasses.fields(BotConfig)}["scrum_fold_pct"]
        assert f.default == FOLD_PCT_DEFAULT

    def test_a_new_scrumming_bot_reads_the_default(self):
        cfg = make_bot_config(BotMode.SCRUMMING, **_REQ)
        assert cfg.scrum_fold_pct == FOLD_PCT_DEFAULT

    def test_the_default_round_trips_through_the_save_shape(self):
        """``get_full_state`` persists ``asdict(self.config)``. A
        default that is not written out is a default that reverts."""
        cfg = make_bot_config(BotMode.SCRUMMING, **_REQ)
        saved = dataclasses.asdict(cfg)
        assert saved["scrum_fold_pct"] == FOLD_PCT_DEFAULT
        again = _restore_one("fresh", {**saved, "mode": "scrumming"})
        assert again.scrum_fold_pct == FOLD_PCT_DEFAULT

    def test_the_wizard_spinbox_starts_at_the_default(self):
        """The operator's own new-bot surface, DRIVEN. A dataclass
        default the wizard then overwrites with a different spinbox
        value is not a default, and a text scan cannot tell a laid-out
        widget from an orphan. Read the real widget and the payload the
        wizard hands ``_create_bot``, which is what a bot is built
        from."""
        pytest.importorskip("PySide6.QtWidgets")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.bot_wizard import BotCreationWizard

        wizard = BotCreationWizard([], {}, None)
        try:
            pages = [wizard.page(i) for i in wizard.pageIds()]
            boxes = [p for p in pages if getattr(p, "_scrum_fold_pct", None)]
            assert len(boxes) == 1, f"{len(boxes)} pages carry a fold-ratio box"
            page = boxes[0]
            assert (
                page._scrum_fold_pct.parentWidget() is not None
            ), "the fold-ratio spinbox was constructed but never laid out"
            assert page._scrum_fold_pct.value() == FOLD_PCT_DEFAULT
            assert page.get_config()["scrum_fold_pct"] == FOLD_PCT_DEFAULT
        finally:
            wizard.deleteLater()


# ---------------------------------------------------------------------------
# THE CONTROL — a stored value is never overridden
# ---------------------------------------------------------------------------


class TestAStoredValueSurvives:
    def test_an_explicit_kwarg_survives_construction(self):
        cfg = make_bot_config(BotMode.SCRUMMING, **_REQ, scrum_fold_pct=50)
        assert cfg.scrum_fold_pct == 50

    def test_a_stored_fifty_survives_the_real_restore_path(self):
        cfg = _restore_one(
            "stored-half",
            {
                "exchange_id": "coinbase",
                "symbol": "BTC/USD",
                "mode": "scrumming",
                "scrum_fold_pct": 50,
            },
        )
        assert cfg.scrum_fold_pct == 50

    def test_a_stored_hundred_survives_the_real_restore_path(self):
        cfg = _restore_one(
            "stored-full",
            {
                "exchange_id": "coinbase",
                "symbol": "BTC/USD",
                "mode": "scrumming",
                "scrum_fold_pct": 100,
            },
        )
        assert cfg.scrum_fold_pct == 100

    def test_every_live_bot_reads_back_what_the_file_stores(self):
        """SECOND WITNESS on a different code path: the JSON value on
        disk and the attribute on the constructed bot must agree, bot
        by bot. This is the assertion that fails if the default turned
        into an override."""
        live = _live_configs()
        if not live:
            pytest.skip("no ~/.acervator/bot_state.json on this machine")
        stored_part = [b for b in live if b[1].get("scrum_fold_pct") == 50]
        assert stored_part, (
            "the fleet no longer stores a partial ratio anywhere, so "
            "this control can no longer discriminate"
        )
        for bot_id, cfg in live:
            want = cfg.get("scrum_fold_pct")
            got = _restore_one(bot_id, cfg).scrum_fold_pct
            assert got == want, (
                f"bot {bot_id}: file says {want!r}, restored bot says "
                f"{got!r} — the default overrode a stored setting"
            )


# ---------------------------------------------------------------------------
# A state file older than the field
# ---------------------------------------------------------------------------


class TestPreFieldStateGetsTheDefault:
    def test_a_pre_field_config_restores_to_the_default(self):
        """Built from a REAL live config with the field removed — the
        shape a save from before the field left on disk."""
        live = _live_configs()
        if not live:
            pytest.skip("no ~/.acervator/bot_state.json on this machine")
        bot_id, cfg = live[0]
        pre = {k: v for k, v in cfg.items() if k != "scrum_fold_pct"}
        assert "scrum_fold_pct" not in pre
        got = _restore_one(bot_id, pre).scrum_fold_pct
        assert got == FOLD_PCT_DEFAULT, (
            f"a pre-field state file resolved to {got!r}; the bot came "
            "up on something other than the declared default"
        )

    def test_a_bare_pre_field_config_restores_to_the_default(self):
        cfg = _restore_one(
            "bare",
            {"exchange_id": "coinbase", "symbol": "BTC/USD", "mode": "scrumming"},
        )
        assert cfg.scrum_fold_pct == FOLD_PCT_DEFAULT


# ---------------------------------------------------------------------------
# Every site that decides the value agrees on it
# ---------------------------------------------------------------------------


class TestEveryDeclarationSiteAgrees:
    """Five sites carry this number. Four are fallbacks, and a fallback
    is the shape that hides a stale default: the obvious test builds a
    bot with the field present, so the literal is never read."""

    def test_the_restore_fallback_carries_the_default(self):
        src = _src("src", "trading", "bot_container.py")
        needle = f'"scrum_fold_pct": cfg.get("scrum_fold_pct", {FOLD_PCT_DEFAULT})'
        assert (
            needle in src
        ), "the SCRUMMING restore path no longer falls back to the default"

    def test_the_dataclass_declaration_carries_the_default(self):
        src = _src("src", "trading", "bot_container.py")
        assert re.search(
            rf"^\s*scrum_fold_pct: int = {FOLD_PCT_DEFAULT}\b", src, re.MULTILINE
        ), "the BotConfig field declaration no longer reads the default"

    def test_the_live_settings_panel_falls_back_to_the_default(self):
        src = _src("src", "gui", "bot_live_settings.py")
        needle = f'getattr(cfg, "scrum_fold_pct", {FOLD_PCT_DEFAULT})'
        assert needle in src, (
            "the live-settings spinbox shows a different value for a "
            "bot with no stored ratio"
        )

    def test_the_wizard_declares_the_default(self):
        src = _src("src", "gui", "bot_wizard.py")
        assert re.search(
            rf"_scrum_fold_pct\.setValue\({FOLD_PCT_DEFAULT}\)", src
        ), "the wizard spinbox no longer opens on the default"

    def test_the_runtime_read_falls_back_to_the_default(self):
        """``_apply_scrum_fold_pct`` reads the config at fire time. Its
        fallback must not disagree with the construction sites, or a
        config missing the attribute folds a different fraction than
        the same bot rebuilt from disk."""
        src = _src("src", "trading", "scrumming_bot.py")
        needle = f'getattr(self.config, "scrum_fold_pct", {FOLD_PCT_DEFAULT})'
        assert needle in src, "the fire-time read no longer falls back to the default"
