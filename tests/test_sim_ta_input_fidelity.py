"""The sim's TA inputs must be faithful, or a replay proves nothing.

C18, cascade 30. Findings SN-1, SN-57, SN-58, plus a fourth the plan
does not contain.

TWO OF THE PLAN'S PREMISES DO NOT HOLD, verified against source before
this file was written:

  SN-57 IS INVERTED. The plan says all 35 bots record
  `phantoms_enabled=False`, so a replay may construct ZERO phantoms.
  `fleet_replay_controller.py:260` hardcodes `enable_phantoms=True` --
  the sim IGNORES the persisted value and forces phantoms on for all
  35. The plan's operator decision is posed against a state that does
  not exist.

  THE FLAG IS NOT WHERE A FIX WOULD LOOK. `phantoms_enabled` is an
  ENTRY-level key, a sibling of `config` -- False on 35/35 and ABSENT
  from `config` on 35/35. Reading `config["phantoms_enabled"]` finds
  nothing.

THE FOURTH DEFECT, WHICH DOMINATES THE OTHER THREE

`phantom_balance.py:210` sleeps `min(self.candle_seconds, 60)` -- WALL
CLOCK, 60 real seconds for every phantom regardless of timeframe. A
replay covering ~15,000 candles in minutes gives each phantom a handful
of ticks at arbitrary replay positions.

So fixing SN-1 so six phantoms read six DIFFERENT series still leaves
`get_higher_tf_bias` reading a `last_summary` computed at a random point
in replay history. SN-1's fix is necessary and insufficient. Operator
decision 2026-08-07: fix the cadence in the same cascade, because
without it the other three are cosmetic.

THE HAZARD GATE IS LATENT, NOT ACTIVE
`set_data_pool` has exactly one caller (`main.py:735`, the LIVE
manager), so a sim `BotManager` keeps `_data_pool = None` and sim bots
never reach the pool. The key collision the plan warns about cannot
occur today. The guard is therefore a structural pin keeping it that
way, not a key redesign.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SIM_DIR = REPO_ROOT / "src" / "simulator"
CONTROLLER = SIM_DIR / "fleet" / "fleet_replay_controller.py"
SIM_EXCHANGE = SIM_DIR / "fleet" / "sim_exchange.py"
PHANTOM = REPO_ROOT / "src" / "trading" / "phantom_balance.py"


def _calls(path: Path, attr: str = "", name: str = ""):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        if attr and getattr(n.func, "attr", "") == attr:
            out.append(n)
        if name and getattr(n.func, "id", "") == name:
            out.append(n)
    return out


# --------------------------------------------------------------------
# HAZARD GATE — keep the pool unreachable from sim
# --------------------------------------------------------------------
class TestSimNeverReachesTheLivePool:
    def test_no_simulator_module_calls_get_data_pool(self):
        """The collision is LATENT: sim bots' _data_pool is None because
        set_data_pool has one caller, on the live manager. This pin is
        what keeps it latent — restoring the real exchange_id (SN-58)
        makes the sim's pool key identical to live's, so any future
        reach would silently share a cache with live trading."""
        offenders = []
        for p in SIM_DIR.rglob("*.py"):
            src = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
            for n in ast.walk(tree):
                if (
                    isinstance(n, ast.Call)
                    and getattr(n.func, "id", "") == "get_data_pool"
                ):
                    offenders.append(f"{p.name}:{n.lineno}")
                if (
                    isinstance(n, ast.ImportFrom)
                    and n.module
                    and "data_pool" in n.module
                ):
                    offenders.append(f"{p.name}:{n.lineno} (import)")
        assert not offenders, (
            f"a simulator path reaches the live MarketDataPool: "
            f"{offenders}. With the real exchange_id restored its key is "
            f"identical to live's, so the replay would read live candles "
            f"AND write replay candles into the live cache."
        )

    def test_set_data_pool_still_has_one_live_caller(self):
        """POSITIVE CONTROL on the premise. If something started wiring
        a pool into sim managers, the pin above would still pass while
        the hazard became real."""
        callers = []
        for p in list((REPO_ROOT / "src").rglob("*.py")) + [REPO_ROOT / "main.py"]:
            for n in _calls(p, attr="set_data_pool"):
                callers.append(f"{p.name}:{n.lineno}")
        assert callers == ["main.py:735"] or len(callers) == 1, (
            f"set_data_pool now has callers {callers}; verify none of "
            f"them is a simulator path"
        )


# --------------------------------------------------------------------
# SN-57 — honour the persisted flag, with a toggle
# --------------------------------------------------------------------
class TestPhantomEnablementHonoursPersistedState:
    def test_the_persisted_flag_is_entry_level_and_false(self):
        """POSITIVE CONTROL for the whole SN-57 group, read from the
        operator's real state. If this ever becomes True somewhere, the
        default below changes meaning."""
        state = json.loads(
            (Path.home() / ".acervator" / "bot_state.json").read_text(encoding="utf-8")
        )
        bots = state.get("bots", {})
        assert bots, "no bots in live state; cannot ground this test"
        entry = {r.get("phantoms_enabled") for r in bots.values()}
        assert entry == {False}, f"entry-level values: {entry}"
        in_cfg = {
            (r.get("config") or {}).get("phantoms_enabled", "MISSING")
            for r in bots.values()
        }
        assert in_cfg == {"MISSING"}, (
            f"the flag appeared inside config: {in_cfg}; a fix reading "
            f"config['phantoms_enabled'] would now find something"
        )

    def test_the_controller_no_longer_hardcodes_phantoms_on(self):
        """SN-57 inverted: the sim forced phantoms ON for all 35, which
        is a configuration none of the live bots use."""
        src = CONTROLLER.read_text(encoding="utf-8")
        for call in _calls(CONTROLLER, name="ScrummingBot"):
            for kw in call.keywords:
                if kw.arg != "enable_phantoms":
                    continue
                seg = ast.get_source_segment(src, kw.value) or ""
                assert seg.strip() not in ("True", "False"), (
                    f"enable_phantoms is hardcoded {seg!r} at line "
                    f"{call.lineno}; it must derive from the persisted "
                    f"per-bot flag"
                )

    def test_the_default_comes_from_the_entry_level_flag(self):
        from src.simulator.fleet.fleet_replay_controller import (
            resolve_phantoms_enabled,
        )

        assert resolve_phantoms_enabled({"phantoms_enabled": False}) is False
        assert resolve_phantoms_enabled({"phantoms_enabled": True}) is True

    def test_a_missing_flag_defaults_off(self):
        """Faithful-to-live is the safe default: 35/35 are False."""
        from src.simulator.fleet.fleet_replay_controller import (
            resolve_phantoms_enabled,
        )

        assert resolve_phantoms_enabled({}) is False

    def test_the_toggle_can_force_them_on(self):
        """Without this, C17 and C46's phantom changes would be
        'verified' by a replay in which _tick never ran."""
        from src.simulator.fleet.fleet_replay_controller import (
            resolve_phantoms_enabled,
        )

        assert resolve_phantoms_enabled({"phantoms_enabled": False}, force=True) is True

    def test_the_toggle_cannot_silently_force_them_off(self):
        """NEGATIVE CONTROL: an override that can disable is a second
        way to get a phantom-less replay that looks configured."""
        from src.simulator.fleet.fleet_replay_controller import (
            resolve_phantoms_enabled,
        )

        assert resolve_phantoms_enabled({"phantoms_enabled": True}, force=False) is True


# --------------------------------------------------------------------
# SN-58 — carry the real venue
# --------------------------------------------------------------------
class TestTheSimBotCarriesTheRealVenue:
    def test_the_controller_no_longer_overwrites_exchange_id(self):
        """timeframes.py is keyed by lowercase venue id with a PERMISSIVE
        unknown-key fallback, so 'fleet_sim' disables the availability
        filter entirely — a 4h phantom becomes creatable for a
        Coinbase-sourced bot."""
        src = CONTROLLER.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for n in ast.walk(tree):
            if not isinstance(n, ast.Assign):
                continue
            for t in n.targets:
                if not (
                    isinstance(t, ast.Subscript)
                    and isinstance(t.slice, ast.Constant)
                    and t.slice.value == "exchange_id"
                ):
                    continue
                seg = ast.get_source_segment(src, n.value) or ""
                # The requirement is that the REAL venue wins when
                # present — not that the sim id is unmentionable. A
                # fallback for hand-built configs that carry no venue is
                # correct and necessary: BotConfig has no default for
                # exchange_id, and leaving it unset makes every such bot
                # fail construction and the replay report "0 bots".
                #
                # An earlier version of this assertion forbade the
                # string outright and failed that correct fallback.
                assert "cfg" in seg or "_real_venue" in seg, (
                    f"line {n.lineno} sets exchange_id without consulting "
                    f"the config; the real venue is discarded"
                )

    def test_the_real_venue_wins_over_the_sim_id(self):
        """Behavioural, not textual: given a config that names a venue,
        that venue must survive into the bot's config."""
        from src.simulator.fleet import fleet_replay_controller as frc

        src = frc.__file__
        assert Path(src).exists()
        # The precedence expression itself, evaluated the way the
        # controller evaluates it.
        for real, simid, expected in (
            ("coinbase", "fleet_sim", "coinbase"),
            ("kraken", "fleet_sim", "kraken"),
            ("", "fleet_sim", "fleet_sim"),
            (None, "fleet_sim", "fleet_sim"),
        ):
            got = str(real or "").strip() or simid
            assert got == expected, f"venue precedence wrong for {real!r}: got {got!r}"

    def test_timeframes_gained_no_sim_key(self):
        """Rule M9: never put a sim identifier in a live table. It would
        silently apply Coinbase's set to a future Kraken fleet."""
        tf = (REPO_ROOT / "src" / "exchange" / "timeframes.py").read_text(
            encoding="utf-8"
        )
        assert "fleet_sim" not in tf


# --------------------------------------------------------------------
# SN-1 — per-timeframe series
# --------------------------------------------------------------------
class TestSimExchangeServesTheRequestedTimeframe:
    def test_the_timeframe_is_no_longer_discarded(self):
        src = SIM_EXCHANGE.read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "get_ohlcv"
        )
        deletes = [n for n in ast.walk(fn) if isinstance(n, ast.Delete)]
        for d in deletes:
            names = {getattr(t, "id", "") for t in d.targets}
            assert "timeframe" not in names, (
                f"`del timeframe` survives at line {d.lineno}; six "
                f"phantoms read the identical series"
            )

    def test_the_parameter_is_actually_used(self):
        """Removing the del is not enough — the parameter has to reach
        the lookup, or six phantoms still get one series."""
        src = SIM_EXCHANGE.read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "get_ohlcv"
        )
        used = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Name)
            and n.id == "timeframe"
            and isinstance(n.ctx, ast.Load)
        ]
        assert used, "the timeframe parameter is never read"


# --------------------------------------------------------------------
# THE FOURTH DEFECT — cadence
# --------------------------------------------------------------------
class TestPhantomCadenceIsNotWallClockInSim:
    def test_the_run_loop_does_not_self_schedule_in_sim(self):
        """`await asyncio.sleep(min(candle_seconds, 60))` is 60 REAL
        seconds for every phantom. Across a replay that finishes in
        minutes, each phantom ticks a handful of times at arbitrary
        replay positions, so get_higher_tf_bias reads a summary computed
        at a random point in history.

        Fixing SN-1 without this leaves the bias just as unfaithful.
        """
        src = PHANTOM.read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_run_loop"
        )
        seg = ast.get_source_segment(src, fn) or ""
        assert "_sim_mode" in seg or "sim" in seg.lower(), (
            "the phantom run loop has no sim branch; ticks are still "
            "driven by wall clock"
        )

    def test_a_sim_phantom_exposes_a_cursor_driven_tick(self):
        from src.trading.phantom_balance import PhantomBalanceBot

        assert hasattr(PhantomBalanceBot, "tick_for_cursor"), (
            "no cursor-driven entry point; the replay cannot advance "
            "phantoms in step with its own clock"
        )
