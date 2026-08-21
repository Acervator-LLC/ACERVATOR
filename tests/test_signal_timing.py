"""Queue item 10.3 -- TIME. When a record happened, and what stopped.

WHAT THIS UNIT ADDS
===================
Before it, ZERO of the 40 pins carried a duration. One pin held a
timestamp pair and it measured the length of the market tape replayed,
not the cost of replaying it. Five pins were NAMED for timing and
reported counts and booleans. The network could answer "did it run, was
the value right" and could not answer "how long did it take".

Two different durations exist and they need different work:

  (a) HOW LONG THE OBSERVED OPERATION TOOK. Only the caller knows. It
      needs all 40 call sites. NOT THIS UNIT, and nothing here should be
      read as supplying it.
  (b) THE INTERVAL BETWEEN EMISSIONS of one pin, and how long since a
      pin was last seen. The sink computes both alone. THIS UNIT.

(b) answers "on time" and "hangs". It cannot answer "slow down" in the
one shape that matters most: a pin that keeps firing on cadence while
each individual operation inside it takes twice as long looks perfect
from here. That is (a).

THE IDENTITY IS `(name, site)`, NOT `name`
==========================================
`signal_contract._throttle_admit` already keys its rate limit on the
pair -- and, since issue #57, on the `instance` a call site may declare
beside it -- and states why: the same signal emitted from two places is
two different things to a reader. `SignalSink.stats` keys on the name
alone. The timing surface follows the pair, and
`TestIdentityIsTheNameAndTheSite` shows the two side by side so the
difference is visible rather than asserted.

A HANG HAS NO RECORD
====================
Every other retrieval on the sink answers a question about records that
ARRIVED. A pin that stopped sends nothing, so no record-shaped query
can name it. `pin_state` reads the last-seen map instead and needs
nothing to arrive; `TestAHangIsReadableWithNoNewRecord` proves the
staleness rises while the record count does not move.

FOUR STATES, NOT THREE
======================
A pin that NEVER fired is not a pin that fired and stopped, and neither
is a pin that just fired. Collapsing them is the disjunction defect
this project keeps paying for -- the indicator panel's two-causes
message cost the operator real time.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import pytest

from src.core.signal_contract import (
    FRESH_WITHIN,
    MAX_IDENTITIES,
    PIN_CURRENT,
    PIN_FRESH,
    PIN_NEVER,
    PIN_STALE,
    PIN_STATES,
    STALE_AFTER,
    Signal,
    SignalSink,
    _classify,
    emit,
    get_sink,
    read_records,
    set_sink,
)

# Set before anything imports Qt, matching
# `tests/test_main_window_suppression_repairs.py`. `tests/conftest.py`
# has already put the repository root on `sys.path`, which is why every
# import above sits at the top of the file and this module carries no
# import-order pragma -- and no suppression directive of any spelling.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parent.parent
REPLAY = REPO_ROOT / "src/gui/simulator_tab/fleet/fleet_replay_controller.py"
MAIN_WINDOW = REPO_ROOT / "src/gui/main_window.py"

# --------------------------------------------------------------------
# REAL LINES FROM THE OPERATOR'S LIVE HISTORY
# --------------------------------------------------------------------
# Copied read-only 2026-08-15 from `~/.acervator_logs/signals/`, one
# verbatim line per distinct name found in a sample of six generations
# totalling 587,000 records. Every one predates this unit, so none of
# them carries `dt` or `nth`, which is exactly the property under test.
#
# They are chunked into adjacent RAW literals only so that no source
# line runs long. `test_the_fixture_is_verbatim` compares the
# reconstruction against a SHA-256 taken at capture time, because a
# "real" line somebody tidied is a synthetic line with a good story.
REAL_LINES = (
    # bot.capital_reservation -- 489 bytes, verbatim
    r'{"ts":"2026-08-15T06:26:53.934678+00:00","seq":2620953,"modu'
    r'le":"src.trading.scrumming_bot","name":"bot.capital_reservat'
    r'ion","kind":"check","ok":false,"expected":114.51,"actual":0.'
    r'0,"count":1,"site":"scrumming_bot.py:1340","context":{"bot_i'
    r'd":"04e1cafc","asset":"RE","holdings":114.51,"error":"ValueE'
    r'rror: reserve: over-commit on RE \u2014 existing reservation'
    r's 242.0509708 + requested 114.51 > total holdings 114.51. Re'
    r'lease stale reservations or reduce request.","released_stale'
    r'":false}}',
    # ta.computed -- 239 bytes, verbatim
    r'{"ts":"2026-08-15T06:27:49.735484+00:00","seq":2623884,"modu'
    r'le":"src.trading.ta_engine","name":"ta.computed","kind":"che'
    r'ck","ok":true,"expected":12,"actual":12,"count":1,"site":"ta'
    r'_engine.py:2601","context":{"timeframe":"5m","window":100}}',
    # ta.raw.adx -- 595 bytes, verbatim
    r'{"ts":"2026-08-15T06:29:58.941653+00:00","seq":2630723,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.adx","kind":"chec'
    r'k","ok":true,"expected":"6 invariants","actual":{"adx":23.24'
    r',"di_plus":29.76,"di_minus":24.16,"ranging":false,"developin'
    r'g":true,"strong_trend":false,"parabolic":false,"adx_rising":'
    r'false,"bull_dominant":true,"bear_dominant":false,"di_bull_cr'
    r'oss":true,"di_bear_cross":false,"new_trend":false},"count":1'
    r',"site":"ta_engine.py:2656","context":{"timeframe":"5m","win'
    r'dow":100,"symbol":"LSETH/USDC","candle_ts":1786596000000,"di'
    r'rection":"BULLISH","confidence":0.331961,"weight":1.0}}',
    # ta.raw.bollinger_bands -- 469 bytes, verbatim
    r'{"ts":"2026-08-15T06:27:10.596378+00:00","seq":2621930,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.bollinger_bands",'
    r'"kind":"check","ok":true,"expected":"2 invariants","actual":'
    r'{"upper":0.008605,"middle":0.0084,"lower":0.008196,"bb_posit'
    r'ion":0.3524,"band_width":0.048803,"squeeze":false},"count":1'
    r',"site":"ta_engine.py:2656","context":{"timeframe":"5m","win'
    r'dow":100,"symbol":"GROVE/USD","candle_ts":1786750500000,"dir'
    r'ection":"NEUTRAL","confidence":0.0,"weight":1.0}}',
    # ta.raw.ichimoku -- 931 bytes, verbatim
    r'{"ts":"2026-08-15T06:33:26.033619+00:00","seq":2641470,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.ichimoku","kind":'
    r'"check","ok":true,"expected":"8 invariants","actual":{"price'
    r'_vs_cloud":"above","cloud_top":0.6797,"cloud_bottom":0.6789,'
    r'"cloud_thick_pct":0.12,"tenkan":0.6834,"kijun":0.6834,"fut_c'
    r'loud_bull":true,"twist_to_bull":false,"twist_to_bear":false,'
    r'"chikou_bull":true,"chikou_bear":false,"chikou_above_cloud":'
    r'true,"tk_bull_cross":false,"tk_bear_cross":false,"tk_above_c'
    r'loud":true,"tk_inside_cloud":false,"tk_below_cloud":false,"b'
    r'reakout_up":false,"breakout_down":false,"kijun_bounce_bull":'
    r'true,"kijun_bounce_bear":false,"kijun_rising":true,"kijun_fl'
    r'at":false,"spb_flat":false,"san_ko_shu_bull":true,"san_ko_sh'
    r'u_bear":false,"score":0.8117},"count":1,"site":"ta_engine.py'
    r':2656","context":{"timeframe":"5m","window":100,"symbol":"SU'
    r'I/USD","candle_ts":1786760100000,"direction":"BULLISH","conf'
    r'idence":0.811684,"weight":1.1}}',
    # ta.raw.kaufman_er -- 540 bytes, verbatim
    r'{"ts":"2026-08-15T06:29:39.634107+00:00","seq":2629746,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.kaufman_er","kind'
    r'":"check","ok":true,"expected":"1 invariants","actual":{"er"'
    r':0.1481,"er_prev":0.0333,"er_rising":true,"er_falling":false'
    r',"ideal_ranging":true,"moderate":false,"trending":false,"hig'
    r'hly_efficient":false,"er_peak_falling":false,"price_up":fals'
    r'e},"count":1,"site":"ta_engine.py:2656","context":{"timefram'
    r'e":"5m","window":100,"symbol":"AGLD/USD","candle_ts":1786635'
    r'000000,"direction":"NEUTRAL","confidence":0.0,"weight":1.0}}',
    # ta.raw.macd -- 443 bytes, verbatim
    r'{"ts":"2026-08-15T06:29:03.280125+00:00","seq":2627792,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.macd","kind":"che'
    r'ck","ok":true,"expected":"1 invariants","actual":{"macd_line'
    r'":8.7e-05,"signal_line":7.9e-05,"histogram":8e-06,"crossover'
    r'":false,"divergence":""},"count":1,"site":"ta_engine.py:2656'
    r'","context":{"timeframe":"5m","window":100,"symbol":"BILL/US'
    r'D","candle_ts":1786755000000,"direction":"BULLISH","confiden'
    r'ce":0.15,"weight":1.2}}',
    # ta.raw.rsi -- 431 bytes, verbatim
    r'{"ts":"2026-08-15T06:27:29.685891+00:00","seq":2622907,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.rsi","kind":"chec'
    r'k","ok":true,"expected":"1 invariants","actual":{"rsi":89.28'
    r',"overbought":true,"oversold":false,"bull_div":false,"bear_d'
    r'iv":false},"count":1,"site":"ta_engine.py:2656","context":{"'
    r'timeframe":"5m","window":100,"symbol":"LINK/USD","candle_ts"'
    r':1786759800000,"direction":"BEARISH","confidence":0.7856,"we'
    r'ight":0.8}}',
    # ta.raw.slingshot -- 599 bytes, verbatim
    r'{"ts":"2026-08-15T06:33:44.329962+00:00","seq":2642447,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.slingshot","kind"'
    r':"check","ok":true,"expected":"5 invariants","actual":{"slin'
    r'gshot_type":"","squeeze_active":false,"squeeze_bull":false,"'
    r'squeeze_bear":false,"squeeze_depth":0.344,"squeeze_conf":1.0'
    r',"expansion_rate":-0.109,"was_squeezed":false,"snapback_type'
    r'":"","snapback_conf":0.0,"curr_bw":0.013665,"avg_bw":0.02083'
    r'},"count":1,"site":"ta_engine.py:2656","context":{"timeframe'
    r'":"5m","window":100,"symbol":"AGLD/USD","candle_ts":17866350'
    r'00000,"direction":"NEUTRAL","confidence":0.0,"weight":1.0}}',
    # ta.raw.stochastic_rsi -- 393 bytes, verbatim
    r'{"ts":"2026-08-15T06:28:44.635103+00:00","seq":2626815,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.stochastic_rsi","'
    r'kind":"check","ok":true,"expected":"2 invariants","actual":{'
    r'"k":78.14,"d":78.76,"crossover":""},"count":1,"site":"ta_eng'
    r'ine.py:2656","context":{"timeframe":"5m","window":100,"symbo'
    r'l":"BONK/USD","candle_ts":1786751100000,"direction":"BEARISH'
    r'","confidence":0.2,"weight":1.0}}',
    # ta.raw.supertrend -- 479 bytes, verbatim
    r'{"ts":"2026-08-15T06:38:24.227785+00:00","seq":2657102,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.supertrend","kind'
    r'":"check","ok":true,"expected":"3 invariants","actual":{"bul'
    r'lish":true,"flip_bull":true,"flip_bear":false,"st_line":0.39'
    r'9815,"dist_pct":0.432,"near_line":true,"curr_atr":0.000472},'
    r'"count":1,"site":"ta_engine.py:2656","context":{"timeframe":'
    r'"5m","window":100,"symbol":"AERO/USDC","candle_ts":178675920'
    r'0000,"direction":"BULLISH","confidence":0.85,"weight":1.0}}',
    # ta.raw.volume -- 745 bytes, verbatim
    r'{"ts":"2026-08-15T06:29:20.234426+00:00","seq":2628769,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.volume","kind":"c'
    r'heck","ok":true,"expected":"4 invariants","actual":{"obv_ris'
    r'ing":true,"obv_divergence":"none","mfi":49.7,"mfi_overbought'
    r'":false,"mfi_oversold":false,"mfi_divergence":"none","cmf":0'
    r'.3059,"cmf_bull":true,"cmf_bear":false,"ad_rising":true,"ad_'
    r'price_div_bull":true,"ad_price_div_bear":false,"vol_ratio":0'
    r'.3,"vol_spike":false,"vol_high":false,"vol_low":true,"capitu'
    r'lation":false,"weak_rally":false,"vol_confirms_bull":false,"'
    r'vol_confirms_bear":false},"count":1,"site":"ta_engine.py:265'
    r'6","context":{"timeframe":"5m","window":100,"symbol":"PENGU/'
    r'USD","candle_ts":1786758600000,"direction":"BULLISH","confid'
    r'ence":0.45,"weight":0.8}}',
    # ta.raw.vortex -- 596 bytes, verbatim
    r'{"ts":"2026-08-15T06:32:50.030147+00:00","seq":2639516,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.vortex","kind":"c'
    r'heck","ok":true,"expected":"2 invariants","actual":{"vi_plus'
    r'":1.288,"vi_minus":0.5795,"separation":0.7085,"sep_accelerat'
    r'ion":0.2085,"crossover":false,"bull_accel":true,"bear_accel"'
    r':false,"vip_at_ceiling":false,"vim_at_ceiling":false,"vip_at'
    r'_floor":false,"vim_at_floor":true,"both_converging":false},"'
    r'count":1,"site":"ta_engine.py:2656","context":{"timeframe":"'
    r'5m","window":100,"symbol":"XLM/USDC","candle_ts":17867601000'
    r'00,"direction":"BULLISH","confidence":1.0,"weight":0.9}}',
    # ta.raw.zscore -- 539 bytes, verbatim
    r'{"ts":"2026-08-15T06:28:24.714843+00:00","seq":2625838,"modu'
    r'le":"src.trading.ta_engine","name":"ta.raw.zscore","kind":"c'
    r'heck","ok":true,"expected":"1 invariants","actual":{"z":1.12'
    r'9,"z_prev":0.706,"sma":0.680312,"std":0.002559,"extreme_high'
    r'":false,"strong_high":false,"mild_high":false,"extreme_low":'
    r'false,"strong_low":false,"mild_low":false,"z_reverting":fals'
    r'e},"count":1,"site":"ta_engine.py:2656","context":{"timefram'
    r'e":"5m","window":100,"symbol":"SUI/USD","candle_ts":17867598'
    r'00000,"direction":"NEUTRAL","confidence":0.0,"weight":0.9}}',
    # tick.throttled -- 285 bytes, verbatim
    r'{"ts":"2026-08-15T06:26:33.411697+00:00","seq":2619976,"modu'
    r'le":"src.trading.scrumming_bot","name":"tick.throttled","kin'
    r'd":"sample","ok":null,"expected":null,"actual":true,"count":'
    r'1,"site":"scrumming_bot.py:6084","context":{"bot_id":"04e1ca'
    r'fc","counter":4,"skip":12,"read_rate_min":1}}',
    # tick.worked -- 251 bytes, verbatim
    r'{"ts":"2026-08-15T06:31:15.583425+00:00","seq":2634631,"modu'
    r'le":"src.trading.scrumming_bot","name":"tick.worked","kind":'
    r'"sample","ok":null,"expected":null,"actual":true,"count":1,"'
    r'site":"scrumming_bot.py:6101","context":{"bot_id":"803eb6a8"'
    r',"skip":1}}',
)

REAL_LINES_SHA256 = "d29c99cb365dd2464f5b806a195d4b94119b2d3b7a444abcff5a9d46c0037020"
REAL_LINE_COUNT = 16


@pytest.fixture
def sink(tmp_path):
    """A real sink, installed as the process sink and put back after.

    `set_sink` is process-global and `ta_engine` decides whether to run
    its instrumentation on `get_sink() is None`, so a sink leaked out of
    this module would change the path later tests take.
    """
    previous = get_sink()
    s = SignalSink(path=tmp_path / "signals.jsonl", flush_every=10_000)
    set_sink(s)
    yield s
    set_sink(previous)


def _emit_from_site_one(name, value):
    """One call site. Its line number is half of an identity."""
    return emit(name, actual=value)


def _emit_from_site_two(name, value):
    """A DIFFERENT call site, deliberately emitting the same name."""
    return emit(name, actual=value)


def _attrs_read_off(path: Path, variable: str, function: str) -> set:
    """Every attribute `function` in `path` reads off `variable`.

    Reads the CONSUMER, not a description of it. If a reader starts
    using a field, or a field it uses disappears, this notices without
    anybody remembering to update a list.

    SCOPED TO ONE FUNCTION DELIBERATELY. A whole-module walk of
    `main_window.py` collects every `r.<attr>` across 8,243 lines --
    `r.bot_id` among them -- and would demand fields of a signal record
    that no consumer of one ever asked for.

    Both an unfound function and an empty attribute set are refused. A
    scope that matched nothing makes every assertion built on it
    vacuously true, which is a verification that graded nothing
    reporting success.
    """
    tree = ast.parse(path.read_bytes().decode("utf-8"))
    scope = None
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == function):
            scope = node
            break
    assert scope is not None, f"{path.name} defines no {function}"
    found = set()
    for node in ast.walk(scope):
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == variable):
            found.add(node.attr)
    assert found, f"{function} reads nothing off `{variable}`"
    return found


# ------------------------------------------------------- CONTROL a --

class TestIdentityIsTheNameAndTheSite:
    """Two pins sharing a name, emitted from two places, are two pins.

    FAILURE MEANING: if these fail, the interval is keyed on the name
    alone, and every shared name reports the cadence of whichever site
    happened to fire last. `bot.capital_reservation` was emitted from
    two sites until 10.2 renamed them apart; the rename fixed ONE
    collision, it did not change the identity rule.
    """

    def test_two_sites_sharing_one_name_keep_separate_intervals(self, sink):
        """Site one waits, site two does not. Under name-only keying
        BOTH of these assertions are impossible: site two's first record
        would inherit site one's 60 ms gap instead of carrying None, and
        site one's second record would measure from site two's emission
        a moment earlier instead of from its own.
        """
        first_one = _emit_from_site_one("pin.shared", 1)
        time.sleep(0.06)
        first_two = _emit_from_site_two("pin.shared", 1)
        second_two = _emit_from_site_two("pin.shared", 2)
        second_one = _emit_from_site_one("pin.shared", 2)

        assert first_one.site != first_two.site
        assert first_one.dt is None and first_one.nth == 1
        assert first_two.dt is None and first_two.nth == 1
        assert second_two.dt < 0.02
        assert second_one.dt >= 0.05
        assert second_one.nth == 2 and second_two.nth == 2

    def test_the_timing_surface_holds_two_rows_where_stats_holds_one(
            self, sink):
        """The contrast, shown rather than described.

        `stats()` groups by name and reports ONE site for both, which is
        the behaviour `docs/EMITTER_IDENTIFICATION.md` records. `timing()`
        and `identities()` follow the throttle's identity instead.
        """
        _emit_from_site_one("pin.shared", 1)
        _emit_from_site_two("pin.shared", 1)
        _emit_from_site_two("pin.shared", 2)

        assert len(sink.stats()) == 1
        assert sink.stats()["pin.shared"]["n"] == 3

        assert len(sink.identities()) == 2
        rows = sink.timing("pin.shared")
        assert len(rows) == 2
        assert sorted(row["n"] for row in rows.values()) == [1, 2]

    def test_the_same_name_on_two_lines_is_two_identities(self, sink):
        """`site` is `file:line`, so the same name written on two lines
        is two emitters -- and a loop, which emits from ONE line, is one.

        This is not a new rule. `_throttle_admit` already rate-limits on
        `(name, site)` -- and on any `instance` the call site declares
        with it -- so those two lines have had separate rate windows all
        along. Stating it here because it surprises people and because a
        test that emits twice on adjacent lines and expects `nth == 2`
        is testing its own misunderstanding.
        """
        sink.emit("pin.lines", actual=1)
        sink.emit("pin.lines", actual=2)
        assert len(sink.timing("pin.lines")) == 2
        assert all(row["n"] == 1 for row in sink.timing("pin.lines").values())

        for value in (3, 4):
            sink.emit("pin.loop", actual=value)
        looped = sink.timing("pin.loop")
        assert len(looped) == 1
        assert next(iter(looped.values()))["n"] == 2


# ------------------------------------------------------- CONTROL b --

class TestTheFirstEmissionIsHonest:
    """No previous emission is not an interval of zero.

    FAILURE MEANING: a first emission reported as 0.0 reads as
    "instantaneous", which is a measurement. Nobody took one.
    """

    def test_a_first_emission_carries_no_interval(self, sink):
        first = sink.emit("pin.first", actual=1)
        assert first.dt is None
        assert first.dt != 0.0
        assert first.nth == 1

    def test_a_reader_can_tell_a_first_emission_from_a_real_interval(
            self, sink):
        # ONE source line, so ONE site, so ONE identity. Two `emit`
        # calls written on two lines would be two emitters -- see
        # `test_the_same_name_on_two_lines_is_two_identities`.
        pair = []
        for value in (1, 2):
            pair.append(sink.emit("pin.first", actual=value))
        first, second = pair
        assert first.dt is None
        assert isinstance(second.dt, float)
        assert second.dt >= 0.0
        assert (first.dt is None) is not (second.dt is None)

    def test_a_never_measured_record_is_not_a_first_emission(self, sink):
        """The disjunction guard. `nth` separates them.

        A record written before this unit existed also has no interval,
        and there are 587,000 of those on the operator's disk. Without
        `nth` a reader loading that history would conclude every
        identity in it had just started.
        """
        first = sink.emit("pin.first", actual=1)
        legacy = Signal(name="pin.first", site="old.py:1", actual=1)
        assert first.dt is legacy.dt is None
        assert first.nth == 1
        assert legacy.nth == 0
        assert first.nth != legacy.nth


# ------------------------------------------------------- CONTROL c --

class TestAHangIsReadableWithNoNewRecord:
    """The absence IS the signal.

    FAILURE MEANING: if staleness can only be read off a record, a hung
    pin is unreportable by construction, because the record is the thing
    it is not sending.
    """

    def test_staleness_rises_while_the_record_count_does_not(self, sink):
        sink.emit("pin.hangs", actual=1)
        site = sink.records("pin.hangs")[0].site
        emitted = sink.health()["emitted"]

        first = sink.pin_state("pin.hangs", site)
        time.sleep(0.15)
        later = sink.pin_state("pin.hangs", site)

        assert later["age"] > first["age"]
        assert later["age"] >= 0.15
        assert sink.count("pin.hangs") == 1
        assert sink.health()["emitted"] == emitted

    def test_a_hang_reaches_the_stale_state_with_nothing_arriving(
            self, sink):
        sink.emit("pin.hangs", actual=1)
        site = sink.records("pin.hangs")[0].site
        assert sink.pin_state("pin.hangs", site,
                              stale_after=10.0)["state"] != PIN_STALE
        time.sleep(0.15)
        hung = sink.pin_state("pin.hangs", site,
                              fresh_within=0.01, stale_after=0.10)
        assert hung["state"] == PIN_STALE
        assert sink.count("pin.hangs") == 1


# ------------------------------------------------------ CONTROL c2 --

class TestAnAgeIsNeverNegative:
    """A pin cannot have fired in the future.

    FAILURE MEANING: `pin_state` and `timing` used to sample the clock
    BEFORE taking `_lock`. A reader that then blocked on the lock
    compared its old clock reading against a last-seen stamp `emit`
    wrote while it waited, and `age = now - last` came out NEGATIVE.

    That is the same defect class the whole unit is built to avoid --
    the module chose the monotonic clock precisely because a stepped
    wall clock "can be NEGATIVE, which would read as a pin that fired
    before it fired" -- reintroduced one layer up, in the query rather
    than in the record. It also hides: a negative age is below every
    threshold, so it classifies as PIN_FRESH and arrives wearing the
    healthiest label the module has.

    MEASURED on the unfixed code: 20,000 queries against 4 concurrent
    emitters produced 6 negative ages, worst -0.0314865 s; `timing()`
    produced 9 in 5,000 surveys.

    THE CONTROL BELOW IS DETERMINISTIC, NOT A RACE. A race that fires
    once in 3,000 queries is not a test; it is a test that passes on
    broken code 2,999 times out of 3,000. Instead the exact interleaving
    is CONSTRUCTED: the reader is parked on the lock, and while it waits
    the last-seen stamp is advanced under that same lock -- which is
    precisely what `emit` does, one field at a time, in the same order.
    """

    @staticmethod
    def _park_a_reader_then_advance_the_stamp(call):
        """Return what `call()` saw after being parked on `_lock`.

        The reader thread is started, given time to block on the lock,
        and only then is the stamp moved forward. A reader that sampled
        its clock BEFORE the lock is now holding a reading older than
        the stamp it is about to subtract from.
        """
        sink = SignalSink()
        sink.emit("pin.parked", actual=1, site="parked.py:1")
        seen = []

        def reader():
            seen.append(call(sink))

        lock = getattr(sink, "_lock")
        seen_map = getattr(sink, "_seen")
        with lock:
            worker = threading.Thread(target=reader, daemon=True)
            worker.start()
            # The reader is now blocked. Advance the stamp exactly as
            # `emit` does: the monotonic slot of the live entry, under
            # the lock this thread already holds.
            time.sleep(0.05)
            sink._seen[("pin.parked", "parked.py:1")][0] = time.monotonic()
        worker.join(timeout=5.0)
        assert seen, "the parked reader never returned"
        return seen[0]

    def test_pin_state_age_is_not_negative_when_parked_on_the_lock(self):
        state = self._park_a_reader_then_advance_the_stamp(
            lambda s: s.pin_state("pin.parked", "parked.py:1"))
        assert state["age"] is not None
        # THE ASSERTION THAT FAILS ON THE OLD ORDER. A clock sampled
        # before the lock yields about -0.05 here.
        assert state["age"] >= 0.0, (
            f"pin_state reported a pin that fired in the future: "
            f"age={state['age']}")

    def test_timing_age_is_not_negative_when_parked_on_the_lock(self):
        rows = self._park_a_reader_then_advance_the_stamp(
            lambda s: s.timing())
        assert rows, "timing() lost the identity"
        for key, row in rows.items():
            assert row["age"] >= 0.0, (
                f"timing() reported {key} firing in the future: "
                f"age={row['age']}")

    def test_a_negative_age_would_have_been_reported_as_the_best_state(
            self):
        """Why the number mattered: the wrong value hid as PIN_FRESH.

        This is the ONE assertion here that does not need the race. It
        reads `_classify` directly with an age that is negative by
        construction, and shows the classifier calls it FRESH -- so a
        reader could never have noticed the defect by watching states.
        """
        future = (time.monotonic() + 5.0, 3, "2026-08-15T00:00:00+00:00",
                  0.1)
        verdict = _classify("pin.future", "f.py:1", time.monotonic(),
                            future, FRESH_WITHIN, STALE_AFTER)
        assert verdict["age"] < 0.0
        assert verdict["state"] == PIN_FRESH, (
            "a negative age no longer classifies as fresh -- if this "
            "changed, the hiding mechanism described above changed too")

    def test_the_parking_harness_can_actually_park_a_reader(self):
        """TWO-SIDED CONTROL for the harness, not for the code.

        If the reader were never actually blocked, the two tests above
        would pass on ANY implementation and prove nothing. This one
        makes the harness report how long the parked call took: it must
        exceed the 50 ms the lock was held, or the parking never
        happened.
        """
        started = time.perf_counter()
        self._park_a_reader_then_advance_the_stamp(
            lambda s: s.pin_state("pin.parked", "parked.py:1"))
        elapsed = time.perf_counter() - started
        assert elapsed >= 0.05, (
            f"the reader was never parked on the lock ({elapsed:.4f}s) "
            f"-- the controls above are vacuous")


# ------------------------------------------------------- CONTROL d --

class TestTheFourStatesAreDistinct:
    """never-fired, fired-and-stale, fired-and-current, just-fired.

    FAILURE MEANING: any two of these collapsing is the two-causes
    message again. A pin that never fired needs a wiring fix; a pin that
    fired and stopped needs a hang investigation. One label for both
    sends the operator to the wrong place.
    """

    def _four(self, sink):
        stale = sink.emit("pin.stale", actual=1)
        time.sleep(0.60)
        current = sink.emit("pin.current", actual=1)
        time.sleep(0.20)
        fresh = sink.emit("pin.fresh", actual=1)
        ask = {"fresh_within": 0.10, "stale_after": 0.50}
        return {
            PIN_NEVER: sink.pin_state("pin.never", "nowhere.py:1", **ask),
            PIN_STALE: sink.pin_state("pin.stale", stale.site, **ask),
            PIN_CURRENT: sink.pin_state("pin.current", current.site, **ask),
            PIN_FRESH: sink.pin_state("pin.fresh", fresh.site, **ask),
        }

    def test_all_four_occur_at_once_and_none_is_confusable(self, sink):
        got = self._four(sink)
        for expected, row in got.items():
            assert row["state"] == expected
        assert len({row["state"] for row in got.values()}) == 4
        assert set(got) == set(PIN_STATES)

    def test_never_is_the_only_state_with_no_measurement(self, sink):
        got = self._four(sink)
        never = got[PIN_NEVER]
        assert never["age"] is None and never["n"] == 0
        for state in (PIN_STALE, PIN_CURRENT, PIN_FRESH):
            assert isinstance(got[state]["age"], float)
            assert got[state]["n"] >= 1

    def test_never_fired_is_not_reported_as_stale(self, sink):
        """The exact confusion. A pin that never fired has no recent
        record either, so a classifier keyed on "nothing lately" calls
        it stale and sends the reader hunting a hang that never was.
        """
        never = sink.pin_state("pin.never", "nowhere.py:1",
                               fresh_within=0.01, stale_after=0.01)
        assert never["state"] == PIN_NEVER
        assert never["state"] != PIN_STALE

    def test_asking_about_a_pin_that_never_fired_returns_a_state(
            self, sink):
        """Not None, not an empty dict, not a KeyError. A caller that
        gets nothing back cannot tell the pin apart from its own bug.
        """
        row = sink.pin_state("pin.never", "nowhere.py:1")
        assert row["name"] == "pin.never"
        assert row["site"] == "nowhere.py:1"
        assert row["state"] == PIN_NEVER
        assert row["last_ts"] is None and row["last_dt"] is None


# ------------------------------------------------------- CONTROL e --

class TestTheOperatorsOwnRecordsStillParse:
    """HARD BLOCK. 587,000 records on his disk predate these fields.

    FAILURE MEANING: any failure here means the new record shape has
    made his live history unreadable. Rotation and the row cap were both
    built this week to KEEP that history.
    """

    def _write(self, tmp_path, lines):
        path = tmp_path / "old_session.jsonl"
        path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        return path

    def test_the_fixture_is_verbatim(self):
        """The control on the fixture itself. If the chunking altered a
        byte, everything below is testing a line the operator's disk
        does not contain.
        """
        joined = ("\n".join(REAL_LINES) + "\n").encode("utf-8")
        assert hashlib.sha256(joined).hexdigest() == REAL_LINES_SHA256
        assert len(REAL_LINES) == REAL_LINE_COUNT

    def test_every_real_line_reads_back_with_zero_decode_failures(
            self, tmp_path):
        """DECODE FAILURES ARE COUNTED DIRECTLY.

        `read_records` swallows a bad line with `continue`, so the
        number of records it returns is not evidence that every line
        parsed. The count is taken here, independently, by decoding each
        line and catching the error.
        """
        path = self._write(tmp_path, REAL_LINES)
        failures = 0
        for line in REAL_LINES:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                failures += 1
        assert failures == 0
        back = read_records(path)
        assert len(back) == REAL_LINE_COUNT
        assert len(back) == len(REAL_LINES) - failures

    def test_a_parse_count_alone_is_not_a_validity_proof(self, tmp_path):
        """THE TWO-SIDED CONTROL for the test above.

        One deliberately corrupt line is added. The direct count sees
        it; `read_records` returns a tuple one short and says nothing.
        If the direct count could not see a line the reader dropped, the
        assertion above would be measuring the reader's opinion of
        itself.
        """
        damaged = [*REAL_LINES, '{"ts":"nope", BROKEN']
        path = self._write(tmp_path, damaged)
        failures = 0
        for line in damaged:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                failures += 1
        assert failures == 1
        back = read_records(path)
        assert len(back) == REAL_LINE_COUNT
        assert len(back) == len(damaged) - failures

    def test_absent_is_not_zero_and_not_a_first_emission(self, tmp_path):
        """A missing `dt` must not restore as 0.0, and a missing `nth`
        must not restore as 1. Either would put a fabricated measurement
        on 587,000 records that never carried one.
        """
        path = self._write(tmp_path, REAL_LINES)
        back = read_records(path)
        assert back
        for record in back:
            assert record.dt is None
            assert record.nth == 0
        assert not any(record.nth == 1 for record in back)

    def test_the_old_fields_survive_the_new_ones(self, tmp_path):
        """Every field the old format carried still reads back."""
        path = self._write(tmp_path, REAL_LINES)
        back = read_records(path)
        originals = [json.loads(line) for line in REAL_LINES]
        for record, original in zip(back, originals, strict=True):
            assert record.name == original["name"]
            assert record.site == original["site"]
            assert record.seq == original["seq"]
            assert record.ts == original["ts"]
            assert record.kind == original["kind"]
            assert record.ok == original["ok"]
            assert record.count == original["count"]
            assert record.module == original["module"]

    def test_a_new_record_round_trips_with_its_timing(self, tmp_path):
        """The other direction: what is written must come back whole."""
        path = tmp_path / "new.jsonl"
        s = SignalSink(path=path, flush_every=1)
        for value in (1, 2):
            s.emit("pin.round.trip", actual=value)
        written = s.records()
        back = read_records(path)
        assert list(back) == list(written)
        assert back[0].dt is None and back[0].nth == 1
        assert isinstance(back[1].dt, float) and back[1].nth == 2


# ------------------------------------------------------- CONTROL f --

class TestTheExistingReadersStillWork:
    """Adding a field must break none of them.

    FAILURE MEANING: the Console is the operator's live view of the
    network and the replay rollup is the only thing that turns ~1200
    per-indicator records into one actionable row. Either one breaking
    is worse than having no timing at all.
    """

    def test_the_console_drain_renders_records_carrying_the_new_fields(
            self, sink):
        """Drives the REAL `MainWindow._drain_signals`, off the real
        class, against a real widget. The method swallows every
        exception into `logger.debug`, so the assertions read the
        SURFACE -- the text in the pane and the advanced watermark --
        rather than trusting that no exception was raised.
        """
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication, QPlainTextEdit
        QApplication.instance() or QApplication([])
        from src.gui import main_window

        for value in ({"a": 1}, {"a": 2}):
            sink.emit("console.drive", actual=value, expected={"a": 1})
        assert sink.records()[-1].nth == 2
        assert isinstance(sink.records()[-1].dt, float)

        stub = type("Driven", (), {
            "_drain_signals": main_window.MainWindow._drain_signals})()
        stub._signal_view = QPlainTextEdit()
        stub._signal_seq = 0
        stub._console_paused = False
        stub._drain_signals()

        text = stub._signal_view.toPlainText()
        assert "console.drive" in text
        assert text.count("console.drive") == 2
        assert stub._signal_seq == 2

    def test_the_console_control_shows_the_assertions_can_fail(self, sink):
        """The other side. With no view the drain returns early, the
        watermark never moves and no text appears -- so the assertions
        above are load-bearing rather than vacuous.
        """
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.gui import main_window

        sink.emit("console.drive", actual=1)
        stub = type("Driven", (), {
            "_drain_signals": main_window.MainWindow._drain_signals})()
        stub._signal_view = None
        stub._signal_seq = 0
        stub._console_paused = False
        stub._drain_signals()
        assert stub._signal_seq == 0

    def test_the_console_reads_no_field_a_record_stopped_carrying(self):
        """Reads the consumer's source and checks the coupling.

        The drain loops `for r in new`, so every `r.<attr>` in
        `main_window.py` is a field it depends on. Each one must exist
        on a record produced AFTER this change.
        """
        record = SignalSink().emit("pin.coupling", actual=1)
        reads = _attrs_read_off(MAIN_WINDOW, "r", "_drain_signals")
        # The sentinel: if the scoping ever silently matches the wrong
        # function, this set stops being a subset and the test fails
        # instead of passing over nothing.
        #
        # `seq` is deliberately absent. The drain reads it off
        # `new[-1].seq`, a subscript rather than the loop variable, so
        # no `r.<attr>` walk can see it. The live Qt drive above covers
        # that line by asserting the watermark advanced to 2.
        assert {"ok", "name", "site", "actual", "expected"} <= reads
        for attr in reads:
            assert hasattr(record, attr), (
                f"the Console reads r.{attr} and a record no longer has it")

    def test_the_replay_rollup_walks_records_unchanged(self, sink):
        """The end-of-run walk in `fleet_replay_controller`: filter
        `sink.records()` by the raw-indicator prefix, split checked from
        violated, and keep the address of the first breach. Run here
        over records that DO carry the new fields.
        """
        from src.trading.ta_engine import TA_RAW_PREFIX

        sink.emit(TA_RAW_PREFIX + "rsi", actual=50.0, expected="0..100",
                  ok=True, context={"symbol": "BTC/USD", "candle_ts": 1})
        sink.emit(TA_RAW_PREFIX + "rsi", actual=140.0, expected="0..100",
                  ok=False, context={"symbol": "BTC/USD", "candle_ts": 2})
        sink.emit(TA_RAW_PREFIX + "macd", actual=1.0)
        sink.emit("sim.06.004.counter.trades_fired", actual=3)

        per, firsts = {}, {}
        for _r in sink.records():
            if not _r.name.startswith(TA_RAW_PREFIX):
                continue
            _ind = _r.name[len(TA_RAW_PREFIX):]
            _slot = per.setdefault(
                _ind, {"checked": 0, "violated": 0, "unchecked": 0})
            if _r.ok is None:
                _slot["unchecked"] += 1
            elif _r.ok:
                _slot["checked"] += 1
            else:
                _slot["checked"] += 1
                _slot["violated"] += 1
                if _ind not in firsts:
                    _c = _r.context or {}
                    firsts[_ind] = {"rule": _r.expected,
                                    "symbol": _c.get("symbol"),
                                    "candle_ts": _c.get("candle_ts")}

        assert sorted(per) == ["macd", "rsi"]
        assert per["rsi"] == {"checked": 2, "violated": 1, "unchecked": 0}
        assert per["macd"] == {"checked": 0, "violated": 0, "unchecked": 1}
        assert firsts["rsi"]["candle_ts"] == 2
        assert sum(v["violated"] for v in per.values()) == 1
        assert all(r.nth >= 1 for r in sink.records())

    def test_the_replay_reads_no_field_a_record_stopped_carrying(self):
        """Same coupling check against the replay controller's `_r`,
        scoped to `_run`, the coroutine the end-of-run walk lives in."""
        record = SignalSink().emit("pin.coupling", actual=1)
        reads = _attrs_read_off(REPLAY, "_r", "_run")
        assert {"name", "ok", "expected", "context"} <= reads
        for attr in reads:
            assert hasattr(record, attr), (
                f"the replay walk reads _r.{attr} and a record lost it")

    def test_every_other_retrieval_still_answers(self, sink):
        """`records`, `since`, `count`, `violations`, `names`,
        `by_subsystem`, `stats`, `health` -- none of them may change
        shape because two fields were added to the record."""
        sink.emit("sim.06.004.counter.trades_fired", actual=3)
        sink.emit("ta.07.003.postcondition.computed", actual=1, expected=2)
        assert len(sink.records()) == 2
        assert len(sink.since(0)) == 2
        assert len(sink.since(1)) == 1
        assert sink.count() == 2
        assert len(sink.violations()) == 1
        assert len(sink.names()) == 2
        assert sorted(sink.by_subsystem()) == ["sim", "ta"]
        assert len(sink.stats()) == 2
        assert sink.health()["emitted"] == 2


# ------------------------------------------------------- CONTROL g --

class TestTheCostIsBoundedInMicroseconds:
    """THIS RUNS ON THE Qt GUI THREAD.

    FAILURE MEANING: that thread is the pump's only driver and one
    blocking call freezes the window; the operator reported 3-4 second
    button delays. Anything added to `emit` is paid 153,669 times an
    hour at his measured rate.

    The work added is one monotonic clock read, one dict lookup and
    either a dict insert or four in-place list stores. This measures
    exactly that, in isolation, over 10,000 repetitions. The before/
    after comparison against the unmodified tree is a measurement
    script, not a test: a test cannot hold both versions of the module.
    """

    REPS = 10_000

    def _per_call_us(self, work):
        start = time.perf_counter()
        for _ in range(self.REPS):
            work()
        return (time.perf_counter() - start) / self.REPS * 1e6

    def test_the_timer_can_see_something_slow(self):
        """POSITIVE CONTROL FOR THE INSTRUMENT. A zero is a claim about
        the clock, not about the code. One millisecond of sleep must
        read as at least 500 microseconds or the harness below is
        measuring nothing.
        """
        start = time.perf_counter()
        time.sleep(0.001)
        assert (time.perf_counter() - start) * 1e6 >= 500

    def test_the_added_work_costs_microseconds(self):
        seen = {("pin.cost", "file.py:1"): [time.monotonic(), 1, "", None]}
        key = ("pin.cost", "file.py:1")

        def added():
            now = time.monotonic()
            prev = seen.get(key)
            prev[3] = now - prev[0]
            prev[0] = now
            prev[1] += 1
            prev[2] = ""

        per_call = self._per_call_us(added)
        assert per_call < 5.0, (
            f"the added work costs {per_call:.3f} us per emit on the Qt "
            "GUI thread, which is not a memory read and arithmetic")

    def test_a_whole_emit_still_costs_what_an_emit_costs(self):
        """The added work must stay a small share of `emit`, which
        already builds an ISO timestamp and walks two stack frames."""
        s = SignalSink(flush_every=self.REPS * 10)
        per_call = self._per_call_us(lambda: s.emit("pin.cost", actual=1))
        assert s.health()["emitted"] == self.REPS
        assert per_call < 200.0, (
            f"emit costs {per_call:.3f} us, far above the measured band")


# ------------------------------------------------------- CONTROL h --

class TestMemoryGrowsPerIdentityNotPerRecord:
    """The last-seen map is keyed by identity.

    FAILURE MEANING: a structure that grew per RECORD would be a second,
    unbounded copy of the record window inside the GUI process -- the
    exact failure `RETAIN_ROWS` was written to close.
    """

    def test_one_hundred_thousand_records_over_five_identities(self):
        s = SignalSink(flush_every=1_000_000, retain_rows=1000)
        for i in range(100_000):
            s.emit("pin.mem.%d" % (i % 5), actual=i)
        health = s.health()
        assert health["emitted"] == 100_000
        assert health["identities"] == 5
        assert len(s.identities()) == 5
        assert health["retained"] == 1000
        assert health["identity_overflow"] == 0

    def test_the_map_is_the_same_size_at_ten_times_the_records(self):
        """The control. If the size tracked records rather than
        identities, these two would differ by a factor of ten."""
        sizes = []
        for total in (10_000, 100_000):
            s = SignalSink(flush_every=total * 10, retain_rows=100)
            for i in range(total):
                s.emit("pin.mem.%d" % (i % 5), actual=i)
            sizes.append(s.health()["identities"])
        assert sizes == [5, 5]

    def test_the_ceiling_refuses_new_identities_and_counts_it(self):
        """The bound exists, it does not switch the emitter off, and it
        announces itself. A bound that goes quiet is the silence this
        module exists to remove.
        """
        s = SignalSink(flush_every=1_000_000, max_identities=3)
        records = [s.emit("pin.ceiling.%d" % i, actual=i) for i in range(5)]
        health = s.health()
        assert health["emitted"] == 5
        assert health["identities"] == 3
        assert health["identity_overflow"] == 2
        assert all(r is not None for r in records)
        assert [r.nth for r in records] == [1, 1, 1, 0, 0]
        assert all(r.dt is None for r in records)

    def test_the_default_ceiling_is_far_above_the_stated_target(self):
        """1,000 identities is the operator's stated target. Measured at
        350 bytes each, the default ceiling costs 3.31 MB -- 1.1% of the
        300 MB the file ladder already occupies."""
        assert MAX_IDENTITIES >= 10_000
