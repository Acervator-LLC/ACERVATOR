"""signal_contract.py — emitters that carry their own expectation.

Operator directive 2026-08-08:

    "All emitters going forward must be able to generate a standardized
    output format that you can read i.e. name, location, expected
    result, actual result, etc."
    "Emitter data is not allowed to be mutated after retrieval."
    "I do not want to over do it."

WHY THIS EXISTS
===============
The static gates (ruff/mypy/vulture/bandit + the archetype linters) read
SOURCE. They cannot catch a false claim about RUNTIME. "Per-candle TA
ran", "the tablets were processed", "the swarm was driven" were all
asserted and all wrong, and no gate could have known.

Measured example of the gap: Nuclear Mode computes TA on ~2-5% of ticks
(read-rate throttle at scrumming_bot.py:5046), and NOTHING in the run
artifacts recorded that. `bots_ticked` counts tick ENTRIES, so the ~91%
that return early are indistinguishable from the ~5% that compute. The
run could not falsify the claim.

EMIT ON THE SUCCESS PATH. THIS IS THE WHOLE POINT.
==================================================
Research (2026-08-08) surveyed Design by Contract, the Linux kernel
Runtime Verification subsystem, JavaMOP and icontract. Every one is
FAILURE-TRIGGERED: it emits nothing when the expectation holds. That is
fatal here, because silence is then indistinguishable from
never-executed — which is exactly the class of false claim this module
exists to make impossible. So a satisfied expectation is recorded too.

The record shape is not invented. Great Expectations'
`ExpectationValidationResult` binds declared-expectation + verdict +
observation in one persisted JSON record. This is that triple, with one
deliberate departure: GX lets the observed half be suppressed by a
result-format tier. Here `actual` is MANDATORY. A record that can drop
its observation degrades to a pass/fail bit, and a pass/fail bit is what
we already had.

DESIGN CONSTRAINTS, taken from THIS codebase (not from a paper)
===============================================================
1. NO I/O ON THE EMIT PATH. `EventBus.emit` calls subscribers
   "synchronously on the caller's thread", and the sim tick loop runs on
   the asyncio loop `main.py` pumps from the Qt GUI thread. A
   disk-touching emitter would block the GUI on every signal. So `emit`
   appends to an in-memory buffer and returns; disk cost is amortised
   over `flush_every`, mirroring `SimRunLog`.
2. NOT ROUTED THROUGH `EventBus`. Two reasons. `Event.data` is a dict
   handed by reference to every subscriber, so any subscriber can mutate
   it — which violates the no-mutation rule outright. And a bus hop adds
   a synchronous callback chain to a hot path that runs per tick.
3. IMMUTABLE BY CONSTRUCTION. `Signal` is a frozen dataclass. Retrieval
   returns a tuple of frozen records, so a consumer cannot alter what was
   captured. Append-only JSONL on disk; no record is ever rewritten.
4. TIME IS MEASURED HERE, NOT AT THE CALL SITE. Queue item 10.3. Two
   different durations exist and only one of them is the sink's to know.
   How long an OBSERVED OPERATION took is knowable only by the caller
   that wrapped it, and would need all 40 call sites changed. The
   INTERVAL BETWEEN EMISSIONS of one pin, and how long since a pin was
   last seen, are computable by the sink alone from what already passes
   through it. This module implements the second and does not pretend to
   the first: a pin that still fires on cadence while each individual
   operation inside it takes twice as long is INVISIBLE here.

WHAT THIS IS NOT
================
Not a test framework and not an assertion: a failed expectation NEVER
raises. This instruments a live trading platform, where an exception
thrown to report a schema nit would be a worse defect than the nit. It
records; something else decides.
"""
from __future__ import annotations

import json
import math
import sys
import threading
import time
from collections import deque
from types import MappingProxyType
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_FLUSH_EVERY = 200
"""Rows buffered before a disk write. Matches SimRunLog's default so the
two sinks have the same amortisation behaviour under the same load."""

RETAIN_ROWS = 350_000
"""Records kept IN MEMORY. Replaces the old ``MAX_ROWS`` row cap.

WHAT ``MAX_ROWS`` WAS AND WHY IT IS GONE
----------------------------------------
``MAX_ROWS = 2_000_000`` was a hard stop in ``emit``: at the two
millionth record the sink set ``_capped``, counted a drop, and returned
None for the rest of the process. Its stated reason was "so a runaway
soak cannot fill the disk".

That reason is spent. ``MAX_FILE_BYTES`` and ``FILE_BACKUP_COUNT``
below bound the disk directly, at 6 x 50 MB, and they do it without
switching the instrument off. What was left of the row cap was
silence — in the network the operator is scaling to "a thousand eyes",
which is the worst place on the platform for it.

MEASURED 2026-08-13 on the operator's own ``session.jsonl``: of four
process runs in the file, TWO ended at exactly 2,000,000 rows — run 0
after 13.10 hours, run 2 after 12.99 hours. The cap was not a
theoretical ceiling. It was reached on ordinary sessions, and the
emitter network then ran blind for however many hours were left.

THE SECOND, UNSTATED REASON — WHICH IS REAL, SO THE BOUND STAYS
---------------------------------------------------------------
The cap was also the ONLY bound on ``_all``, the in-memory record list.
Removing it outright would have traded a blind instrument for an
unbounded one, inside the process that owns the Qt GUI thread.

MEASURED on 20,000 real records read from the operator's file, deep
retained size with each object counted once:

    per record, distinct labels   818.1 bytes   (conservative)
    per record, labels shared     733.0 bytes   (the live shape)
    control: half the records ->  0.497 of the memory

Projected at the measured rate of 4,942,000 records in 32.16 active
hours = 153,669 records/hour:

     1 h ->    153,669 records ->     119.9 MB
    13 h ->  1,997,699 records ->   1,558.6 MB   <- where the cap bit
    24 h ->  3,688,060 records ->   2,877.4 MB
    48 h ->  7,376,119 records ->   5,754.8 MB

So the row cap was quietly a 1,560 MB memory ceiling, and lifting it
without replacement would have put 2.9 GB of Signal objects in the GUI
process after a day.

The bound therefore stays — but as a RETENTION window on the buffer,
never as a stop on the emitter. Emission is unbounded; memory is not.

WHY 350,000
-----------
Anchored to the bound this module already has rather than invented:
the file ladder occupies 6 x 50 MB = 300 MB on disk, so the sink is
not allowed to cost more in RAM than it already costs on disk.
350,000 x 818.1 bytes = 273.1 MB, which stays under it with headroom
at the CONSERVATIVE per-record figure.

That is 2.28 hours of live history in memory against the ladder's
~4.1 hours on disk. The asymmetry is real and is not a defect: a
record costs 818 bytes resident and about 495 bytes on disk
(2,445,435,093 / 4,942,000, measured), so equal bytes buy fewer rows
in RAM. The FILE is the complete record; memory is a window onto it.

It is a constructor argument for the same reason ``max_bytes`` and
``backup_count`` are: a caller that needs a longer window can ask.
"""

MAX_FILE_BYTES = 50 * 1024 * 1024
"""Rotation threshold for the sink's file.

The same 50 MB ``NDJSONWriter`` has used for trade.log, gate.log,
diagnostics.log and voting.log since v3.23.5, measured holding on the
operator's disk at 52,428,9xx bytes per backup.
"""

FILE_BACKUP_COUNT = 5
"""Backups kept beside the sink's file.

Five, matching ``NDJSONWriter``, so the footprint is bounded at
6 x 50 MB = 300 MB.

MEASURED on the operator's ``signals/session.jsonl`` 2026-08-13:
2,445,435,093 bytes, 4,942,000 records, 26 distinct signal names over
32.2 hours of active process time — 72.5 MB/h. So 300 MB holds roughly
4.1 hours of live history at today's emitter count, and the file stops
being 2.4 GB and climbing. Raise ``backup_count`` if a longer window is
wanted; the number is a constructor argument for exactly that reason.
"""


FRESH_WITHIN = 0.5
"""Age below which a pin reads as JUST FIRED, in seconds.

Queue item 10.3. Anchored to the reader rather than invented: the
Console drains this sink on a 500 ms timer -- `main_window.py:5205`,
`self._signal_timer.setInterval(500)`. A record younger than one drain
interval arrived since the operator last saw the pane, which is what
"just fired" means to the only human reading it.
"""

STALE_AFTER = 660.0
"""Age above which a pin reads as STALE, in seconds.

MEASURED read-only 2026-08-15 on the operator's own history: 598,500
records across six generations of `signals/session.jsonl`, one process
run, 17 distinct `(name, site)` identities. Gap between consecutive
emissions of the SAME identity, in seconds:

    identity                            n       p50       p99       max
    bot.capital_reservation        75,001     0.051     1.965     2.824
    ta.raw.* (13 names, ONE site)  34,459     0.091     2.814     4.715
    tick.throttled                 38,026     0.146     2.303     3.359
    tick.worked                    36,974     0.096     2.709     4.736
    tick.exit_dust_band               510     5.346   309.655   605.696

The widest gap a HEALTHY pin produced was 605.696 s. 660.0 is the next
whole minute above it, so nothing the operator's machine has ever
emitted would be called stale by this default.

THIS DEFAULT IS A PLACEHOLDER, AND THE TABLE ABOVE IS WHY. The p99
spread runs 1.965 s to 309.655 s, a factor of 158. One global threshold
loose enough not to slander the slowest pin cannot notice the fastest
pin going quiet for five minutes. An "on time" verdict needs a per-pin
expected cadence. This module does NOT supply one. It supplies the
measurement a cadence check will read, and it takes the threshold as an
argument so a caller that knows better can say so.
"""

MAX_IDENTITIES = 10_000
"""Distinct `(name, site)` pairs the last-seen map will track.

The map grows per IDENTITY, never per record. That is not the same as
bounded, and an unbounded dict inside the process that owns the Qt GUI
thread is the exact failure `RETAIN_ROWS` exists to close.

MEASURED TWICE 2026-08-15, deep retained size with each object counted
once. The second measurement is the one the ceiling is derived from,
and the gap between them is why the first alone was not enough.

MODELLED, a 53-character name (the widest in
`docs/EMITTER_IDENTIFICATION.md`), a `file.py:NNNN` site and one
ISO-8601 timestamp:

        40 identities ->        13,945 bytes   (0.013 MB)
     1,000 identities ->       354,049 bytes   (0.338 MB)
    10,000 identities ->     3,466,089 bytes   (3.306 MB)
    50,000 identities ->    18,512,625 bytes   (17.655 MB)
    control: half the identities -> 0.500 of the memory
    -> 348.6 bytes per identity

LIVE, a real `SignalSink` after 100,000 emits over 5 identities:

     2,294 bytes for 5 entries -> 458.8 bytes per identity

The model was 32% light, because it shared ONE timestamp string across
every entry and a real sink gives each entry its own. The live figure
is the one that counts:

        40 identities ->        18,352 bytes   (0.017 MB)
     1,000 identities ->       458,800 bytes   (0.438 MB)
    10,000 identities ->     4,588,000 bytes   (4.375 MB)

40 is today's network. 1,000 is the operator's stated target. 10,000 is
this ceiling: ten times that target, costing 4.38 MB, which is 1.5% of
the 300 MB the file ladder already occupies -- the same budget
`RETAIN_ROWS` is anchored to.

Reaching the ceiling does NOT stop the emitter and does not stop timing
the identities already known. It stops ADDING new ones, and counts
every refusal in `health()['identity_overflow']`, because a bound that
goes quiet is the silence this module exists to remove.
"""

PIN_NEVER = "never"
"""No record with this identity has ever entered this sink.

DISTINCT FROM STALE, and keeping them apart is the point. A pin that
never fired and a pin that fired and stopped have different causes and
different fixes, and a reader shown one message for both cannot tell
which it is looking at. That disjunction -- one message covering two
causes -- is the defect class this project keeps paying for.
"""

PIN_FRESH = "fresh"
"""This identity emitted within `fresh_within` seconds. Just fired."""

PIN_CURRENT = "current"
"""This identity emitted between `fresh_within` and `stale_after` ago.

Firing, and not recently enough to be called "just now". The ordinary
state of a healthy pin between two Console drains.
"""

PIN_STALE = "stale"
"""This identity last emitted more than `stale_after` seconds ago.

A HANG HAS NO RECORD. This is the state that exists so the ABSENCE of a
record is readable, and it is reachable only through `pin_state` or
`timing`, never by waiting for a record that is not coming.
"""

PIN_STATES = (PIN_NEVER, PIN_FRESH, PIN_CURRENT, PIN_STALE)
"""The four states, in increasing order of having-recently-happened.

Four, not three. `PIN_NEVER` is not a degree of staleness; it is the
absence of any measurement at all, and it carries `age=None` and `n=0`
where the other three always carry a float and a positive integer.
"""


def _utc_iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(
        ts if ts is not None else time.time(), tz=timezone.utc).isoformat()


def _json_default(o: Any) -> Any:
    """Frozen containers are not JSON types; unwrap them for the file."""
    if isinstance(o, MappingProxyType):
        return dict(o)
    if isinstance(o, (frozenset, set)):
        return sorted(o, key=repr)
    return repr(o)


def freeze(value: Any) -> Any:
    """Return an immutable snapshot of `value`.

    v3.24.81 — CLOSES A HOLE IN THIS MODULE'S OWN CONTRACT.

    `context` was copied on the way in but `actual` was stored BY
    REFERENCE, so a caller that mutated the object after emitting
    rewrote the record retroactively. Demonstrated:

        d = {"BTC/USD": 10}
        sink.emit("x", actual=d)
        d["BTC/USD"] = 999
        sink.records("x")[0].actual  ->  {"BTC/USD": 999}

    That is precisely what "emitter data is not allowed to be mutated
    after retrieval" forbids, and the module claiming to enforce it was
    the thing violating it.

    dict -> read-only view over a copy (subscripting still works, and it
    compares equal to a plain dict). list/set -> tuple/frozenset.
    Recursive, so nesting is covered too. Scalars pass through
    untouched, which is the overwhelmingly common case and costs
    nothing.
    """
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(freeze(v) for v in value)
    return value


def render(value: Any) -> str:
    """Human-readable form of a frozen payload.

    v3.24.81 — `freeze()` turns dicts into `mappingproxy` and lists into
    tuples, and `repr()` of those leaks the implementation into the
    operator's view: `mappingproxy({'BTC/USD': 10})`. Display code uses
    this instead so the reader sees the data, not the mechanism.
    """
    if isinstance(value, MappingProxyType):
        inner = ", ".join(f"{k!r}: {render(v)}" for k, v in value.items())
        return "{" + inner + "}"
    if isinstance(value, tuple):
        return "[" + ", ".join(render(v) for v in value) + "]"
    if isinstance(value, frozenset):
        return "{" + ", ".join(render(v) for v in sorted(value, key=repr)) + "}"
    return repr(value)


def _caller_site(depth: int = 2) -> str:
    """`file:line` of the emitting code.

    Operator asked for "location". Captured automatically rather than
    passed by hand: a hand-written location is one more thing that can
    be wrong, and it silently rots when code moves.
    """
    try:
        f = sys._getframe(depth)
        return f"{Path(f.f_code.co_filename).name}:{f.f_lineno}"
    except Exception:  # noqa: BLE001 - location is best-effort
        return "?"


def _caller_module(depth: int = 2) -> str:
    """Module name of the emitting code.

    v3.24.90. Operator, 2026-08-08: "module not being a field is
    something we can fix and should in order to establish the emitter
    message standard."

    `site` carries `file:line`, so the module was implied but not
    QUERYABLE -- grouping by module meant string-parsing a field whose
    line number changes on every edit. It is a first-class field now.

    Captured from the frame, like `site`, for the same reason: a
    hand-passed module is one more thing that can be wrong.
    """
    try:
        f = sys._getframe(depth)
        mod = f.f_globals.get("__name__")
        if mod:
            return str(mod)
        return Path(f.f_code.co_filename).stem
    except Exception:  # noqa: BLE001 - best-effort
        return "?"


NAME_COLUMN = 53
"""Width of the name column in `Signal.message`.

Queue item 10.2. It was 28, chosen when the longest name in the tree
ran to 32 characters, so the column already overflowed and every
following field on a long line sat one step right of the field above
it. The naming convention makes the names longer still: the longest
name in `docs/EMITTER_IDENTIFICATION.md` is
`fleet.03.007.postcondition.positions_seeded_from_lots`, 53 characters.

53 is the widest name the register holds, not a ceiling the convention
imposes — the slug is free text. So the field is padded and NEVER
truncated: a name longer than this pushes the rest of its own line
right, exactly as before, while an ID stays readable. Truncating would
cut the slug off the end and leave two different emitters printing the
same line.
"""


@dataclass(frozen=True)
class Signal:
    """One observation, with the expectation it was judged against.

    FROZEN. The operator's rule is that emitter data may not be mutated
    after retrieval, and the cheapest way to guarantee that is to make
    mutation raise.

    Every field earns its place:
      name      — what was observed. The join key for analysis.
      site      — file:line. Answers "which emitter", auto-captured.
      expected  — the DECLARED expectation, in the emitter's own terms.
                  None means "recording an observation, asserting
                  nothing" — legitimate and distinct from a passing
                  check.
      actual    — the observation. MANDATORY, and the departure from
                  Great Expectations, which allows suppressing it.
      ok        — the verdict. None when `expected` is None; there is
                  nothing to judge.
      seq       — monotonic per run. Gives total order independent of
                  clock resolution, so two records in the same
                  millisecond are still ordered.
      ts        — wall clock, for correlating with the trade/gate logs.
      context   — the dimensions needed to slice: bot_id, symbol, candle
                  index. Kept as a plain dict and frozen on the way in.
      dt        — seconds since the previous emission of the SAME
                  (name, site). None when no interval was measured.
      nth       — which emission of that identity this is, 1-based.
                  0 means the field was never measured.
    """
    name: str
    site: str
    actual: Any
    expected: Any = None
    ok: Optional[bool] = None
    seq: int = 0
    ts: str = ""
    context: Optional[dict] = None
    # v3.24.90 — module, so records can be GROUPED without parsing
    # `site`. Auto-captured.
    module: str = ""
    # v3.24.90 — CHECK or SAMPLE, declared rather than inferred.
    #
    # Operator, 2026-08-08: "expected=none is functionally useless as
    # designed." It was: `expected=None` meant BOTH "this is a raw
    # observation with nothing to assert" and "somebody forgot to
    # declare an expectation", and no reader could tell which. 92.8% of
    # records carried it, so most of the network could not fail and
    # nobody could tell whether that was by design.
    #
    # A SAMPLE is now a deliberate declaration. A CHECK without an
    # expectation is a defect the contract can point at.
    kind: str = "check"
    # v3.24.90 — how many identical observations this record stands for
    # when the synchroniser has folded a loop's worth into one line.
    count: int = 1
    # 10.3 — seconds since the previous emission of the SAME
    # (name, site) identity, taken from `time.monotonic()`.
    #
    # THE IDENTITY IS THE PAIR, NOT THE NAME. `_throttle_admit` already
    # keys its rate limit on (name, site) and states the reason: the
    # same signal emitted from two places is two different things to a
    # reader. `stats()` keys on the name alone, so it merges them. This
    # does not.
    #
    # None means NO INTERVAL WAS MEASURED, and `nth` says which of the
    # two reasons applies. Zero is never used for that: zero reads as
    # "instantaneous", which is a measurement, and there was none.
    #
    # ON A RATE-LIMITED PIN (`emit(..., every=N)`) THIS IS THE INTERVAL
    # BETWEEN ADMITTED RECORDS, NOT BETWEEN OBSERVATIONS. `count` says
    # how many observations the record stands for. Dividing one by the
    # other assumes the fold was uniform, and nothing guarantees that.
    dt: Optional[float] = None
    # 10.3 — 1-based ordinal of this record within its (name, site)
    # identity, for this sink.
    #
    #    0  never measured. Every one of the 598,500 records on the
    #       operator's disk reads back this way: they were written
    #       before this field existed. It is also what an identity gets
    #       once `MAX_IDENTITIES` is reached.
    #    1  the FIRST emission of this identity. `dt` is None because
    #       there is genuinely no previous one, not because nobody
    #       looked.
    #   >1  `dt` is a real measured interval.
    nth: int = 0
    # 10.3 phase 2 — HOW LONG THE OBSERVED OPERATION TOOK, in seconds,
    # from `time.monotonic()`. Supplied BY THE CALL SITE, because only
    # the call site knows when the operation began; the sink sees the
    # emit moment and nothing before it.
    #
    # THIS IS NOT `dt`, AND THE DIFFERENCE IS THE WHOLE POINT.
    #   dt        the gap BETWEEN successive emissions — cadence.
    #             Answers item 17's "on time" and "hangs".
    #   duration  how long the work being observed took — latency.
    #             Answers item 17's "slow downs".
    # A record can honestly carry one, both, or neither.
    #
    # None means NO DURATION WAS MEASURED, and it is never 0.0. Zero
    # reads as "instantaneous", which is a measurement; there was none.
    # Measured 2026-08-19: 23 of the 40 emitters are instantaneous
    # observations where a duration would be FABRICATED, and a
    # fabricated duration is worse than a missing one because item 17
    # computes health from it. For those, None is the correct answer
    # and no call site should pass anything. See
    # docs/audits/2026-08-19_emitter_duration_classification.md.
    duration: Optional[float] = None

    def to_json(self) -> str:
        return json.dumps({
            "ts": self.ts,
            "seq": self.seq,
            "module": self.module,
            "name": self.name,
            "kind": self.kind,
            "ok": self.ok,
            "expected": self.expected,
            "actual": self.actual,
            "count": self.count,
            "dt": self.dt,
            "nth": self.nth,
            "duration": self.duration,
            "site": self.site,
            "context": self.context or {},
        }, default=_json_default, separators=(",", ":"))

    def message(self) -> str:
        """The operator-facing line. THE emitter message standard.

        v3.24.90. Operator, 2026-08-08: "render() issue will require
        translation to the standard emitter message format. we only need
        to know or retrieve or present data that can help troubleshoot
        issues... after release, more traditional coders are going to
        need these."

        `render()` was a debug repr -- it dumped the whole dataclass,
        `mappingproxy` and all, which is unreadable in a console and
        useless pasted into a bug report.

        Fixed column order so a wall of these scans vertically:

            HH:MM:SS  module            name  VERDICT  detail

        The name column is `NAME_COLUMN` wide and is never truncated.

        VERDICT is PASS / FAIL / ---- (a sample asserts nothing). FAIL
        lines carry expected and actual; PASS lines do not, because a
        passing check's numbers are noise when you are hunting a
        failure. Context always trails, because that is what says WHICH
        bot and WHICH candle.
        """
        t = (self.ts or "")[11:19] or "--:--:--"
        mod = (self.module or "?").rsplit(".", 1)[-1][:18]
        verdict = "----" if self.ok is None else ("PASS" if self.ok else "FAIL")
        parts = [f"{t}  {mod:<18} {self.name:<{NAME_COLUMN}} {verdict}"]
        if self.ok is False:
            parts.append(f" expected={render(self.expected)}"
                         f" actual={render(self.actual)}")
        elif self.kind == "sample":
            parts.append(f" {render(self.actual)}")
        if self.count > 1:
            parts.append(f" x{self.count}")
        if self.context:
            inner = " ".join(
                f"{k}={render(v)}" for k, v in self.context.items())
            parts.append(f"  [{inner}]")
        return "".join(parts)


def _as_float(value: Any) -> Optional[float]:
    """Return `value` as a float, or None when it is not one.

    10.3. A line read back off disk is untrusted input. `read_records`
    already skips a line it cannot decode, so a FIELD it cannot coerce
    has to be survivable too -- otherwise one malformed number aborts
    the read of a 50 MB file and the caller gets an empty tuple with no
    error. Measured: the operator's live history is 598,500 records in
    six files, and losing a whole generation to one bad float is not a
    trade this module gets to make.

    EXACT TYPES, NOT `isinstance`. `bool` is a subclass of `int` and
    `float(True)` is 1.0, so an isinstance guard turns a boolean into a
    one-second interval -- the class of coercion defect this repo has
    already paid for once. `coding_archetype`'s numeric_guard NG001
    refuses the isinstance form for that reason and refused this
    function's first draft, which rejected `bool` by name and still
    left a bare `float(value)` fallback behind it.

    There is no fallback now. The only input that reaches here is a
    JSON value read off disk, where exact `int` and `float` cover every
    legitimate case; a string, a list or a bool is not a mis-typed
    interval, it is no interval, and None says so.

    IT NEVER RAISES FOR ANY INPUT, AND HERE THAT MATTERS MORE THAN IT
    DOES AT THE INGRESS. `emit` wraps its guard in a blanket handler,
    so a raise there cost ONE record. `read_records` has no blanket
    handler: its inner `except json.JSONDecodeError` sits around
    `json.loads` ALONE, and its outer handler catches `OSError` ONLY.
    This function runs after the decode, inside the `Signal(...)`
    construction, where neither one reaches it. An OverflowError raised
    here therefore left `read_records` entirely, so one bad line cost
    the WHOLE FILE and took the caller down with it -- measured on this
    branch over a three-line file, where zero of the three came back.

    THE INT BRANCH IS BOUNDED FOR THAT REASON. `float(10 ** 400)`
    raises OverflowError, which no type check can see, because the type
    is a perfectly ordinary `int`. The bound is an int compared against
    a float, which CPython evaluates EXACTLY, without converting either
    side, so the test cannot itself raise; anything inside the bound is
    representable, so neither can the conversion under it.

    IT IS ONLY THE TOTALITY THAT IS SHARED WITH THE INGRESS GUARD, NOT
    THE RULES. `_as_measured_duration` refuses a negative, a NaN and an
    infinity, and rounds what it keeps, because it judges a number
    arriving from a CALL SITE where those shapes mean a defect. This
    function reads a number back off DISK, and a value a previous
    generation really did write must read back as the value that is
    there, or the reader is editing history. A wide int is refused
    because no float can HOLD it, which is a different statement.
    """
    if type(value) is float:
        return value
    if type(value) is int:
        if not -sys.float_info.max <= value <= sys.float_info.max:
            return None
        return float(value)
    return None


def _as_ordinal(value: Any) -> int:
    """Return `value` as a positive int, or 0 when it is not one.

    10.3. Exact-typed for the same reason as `_as_float`: `True` would
    otherwise read back as ordinal 1, which is this module's spelling
    of "the first emission of this identity". 0 is "never measured", so
    anything uncoercible degrades to unknown rather than to a
    fabricated position in the sequence.
    """
    if type(value) is int and value > 0:
        return value
    return 0


def _as_measured_duration(value: Any) -> Optional[float]:
    """Return `value` as a REAL measured duration, or None when it is not.

    10.3 phase 2 -- THE INGRESS GUARD, and the counterpart to
    `_as_float` above. That one refuses a bad number arriving from
    DISK. Nothing refused a bad number arriving from a CALL SITE, and
    `emit` wrote `float(duration)` verbatim, which had four holes with
    one consequence.

      `float(True)` is 1.0. A caller that passes a FLAG by mistake --
      `duration=is_slow` -- wrote a one-second latency that is
      indistinguishable on disk from a measured one. This is the exact
      coercion `_as_float` names as "the class of coercion defect this
      repo has already paid for once"; the way in from a call site had
      no such refusal.

      A NEGATIVE duration says time ran backwards. `time.monotonic()`
      cannot produce one, so it can only come from a reversed
      subtraction or a wall-clock difference taken across an NTP step.
      It was stored verbatim.

      Anything `float()` REFUSES -- a string, an object, None-like
      sentinels -- raised TypeError inside `emit`, where the blanket
      handler swallowed it and returned None. The bad argument did not
      just lose its duration, it destroyed THE WHOLE RECORD, silently.

      AN INT TOO WIDE FOR A FLOAT does the same thing by another
      route. `float(10**400)` raises OverflowError, not TypeError, so
      a guard that only judged the TYPE and then converted still fed
      the blanket handler and still lost the record. No measurement
      off `time.monotonic()` is 1e308 seconds, so a value that large
      is not a slow operation, it is not a duration at all.

    Every one of those writes a number item 17 reads as LATENCY. The
    module's position is already stated on the field itself: A
    FABRICATED DURATION IS WORSE THAN A MISSING ONE. So a value that
    fails any check here degrades to None -- "no duration was
    measured", which is the truth -- the record survives intact, and
    the sink counts the refusal in `health()['duration_rejected']` so a
    developer sees it without a debugger.

    IT NEVER RAISES FOR ANY INPUT, AND THAT IS THE POINT. Not "for
    every shape seen so far" -- TOTAL: every branch that could throw
    is guarded before it is taken, which is why the int bound is
    checked instead of the conversion being tried. `emit` runs on the
    live trading and GUI paths. The module docstring already forbids an
    exception thrown to report a schema nit, and a rejected argument is
    a schema nit.

    EXACT TYPES, NOT `isinstance`, for the reason `_as_float` gives:
    `bool` is a subclass of `int`, so an isinstance guard is precisely
    what lets `True` through as 1.0. `type(True) is int` is False, so a
    bool needs no branch of its own -- it falls to the refusal below.

    ZERO IS ACCEPTED AND IS NOT THE SAME AS None, exactly as for `dt`:
    an operation faster than the clock can resolve is a real
    measurement that rounds to 0.0, and None is reserved for the 23
    emitters that measured nothing at all.

    ROUNDED TO THE CLOCK'S OWN RESOLUTION, 1e-07, the same treatment
    `dt` gets in `emit` for the same reason. Both fields come off the
    same `time.monotonic()`, whose resolution on the operator's machine
    is 1e-07, so the eighth decimal onward is float representation
    noise -- written to disk on every record that carries a duration.
    """
    if value is None:
        return None
    if type(value) is int:
        # AN INT TOO WIDE FOR A FLOAT IS NOT A MEASUREMENT, AND THE
        # CONVERSION MUST NOT BE ATTEMPTED. `float(10**400)` raises
        # OverflowError, which left this guard, reached `emit`, and was
        # swallowed by the same blanket handler that swallowed
        # `float(object())` -- destroying THE WHOLE RECORD by the
        # fourth route rather than the third.
        #
        # The bound is an int compared against a float, which CPython
        # evaluates EXACTLY, without converting either side, so the
        # test cannot itself raise. Anything inside the bound is
        # representable, so neither can the conversion under it. That
        # is what makes this function total.
        if not -sys.float_info.max <= value <= sys.float_info.max:
            return None
        value = float(value)
    if type(value) is not float:
        return None
    if not math.isfinite(value):
        return None
    if value < 0.0:
        return None
    return round(value, 7)


def _classify(name: str, site: str, now: float,
              snapshot: Optional[tuple],
              fresh_within: float, stale_after: float) -> dict:
    """Return one identity's timing view. FOUR STATES, NEVER THREE.

    `snapshot` is None when the identity has never been seen, and that
    case returns `PIN_NEVER` with `age=None` and `n=0`. It is the only
    state that can do so: the other three always carry a float age and
    a positive ordinal, so no reader can confuse "nothing ever
    happened" with "it happened and stopped".

    The remaining three partition the age axis at two thresholds and
    are therefore disjoint by construction:

        age <= fresh_within                    PIN_FRESH
        fresh_within < age <= stale_after      PIN_CURRENT
        age > stale_after                      PIN_STALE

    `stale_after` is raised to `fresh_within` if a caller passes them
    inverted, because an inverted pair makes PIN_FRESH unreachable and
    silently reclassifies every fresh pin as stale. Passing them EQUAL
    is legal and makes PIN_CURRENT empty; that is a caller's choice of
    thresholds, not a defect in the partition.

    THE AGE COMES FROM THE MONOTONIC CLOCK. `last_ts` is the wall clock
    of the same emission, carried alongside so a human can correlate it
    with trade.log and gate.log, and it is never differenced.
    """
    if snapshot is None:
        return {"name": name, "site": site, "state": PIN_NEVER,
                "age": None, "n": 0, "last_ts": None, "last_dt": None}
    last_mono, count, last_ts, last_dt = snapshot
    age = now - last_mono
    limit = max(float(stale_after), float(fresh_within))
    if age <= float(fresh_within):
        state = PIN_FRESH
    elif age <= limit:
        state = PIN_CURRENT
    else:
        state = PIN_STALE
    return {"name": name, "site": site, "state": state, "age": age,
            "n": count, "last_ts": last_ts, "last_dt": last_dt}


class SignalSink:
    """Buffered, append-only sink for `Signal` records.

    Thread-safe because the sim ticks on the asyncio loop pumped from the
    Qt GUI thread while other producers may be elsewhere; the lock is
    held only for a list append, never across I/O.

    v3.24.9x — TWO locks, and the split is the point. `_lock` still
    guards nothing but the buffer, so `emit` is never delayed by a
    disk write. `_io_lock` guards the file: rotation plus the append
    that follows it are one critical section, because `flush` is
    reachable from every producer thread and a rename racing an append
    is how a rotation loses records. `_lock` is never taken while
    `_io_lock` is held, so the two cannot deadlock.

    v3.24.9x — THE EMITTER NEVER STOPS; THE MEMORY IS BOUNDED INSTEAD.
    Both collections are `deque`s with a `maxlen`, so a session of any
    length costs a fixed amount of RAM. See `RETAIN_ROWS` for the
    measurement the window is sized from, and for why the row cap that
    used to switch `emit` off is gone.

    10.3 — IT ALSO KEEPS A LAST-SEEN MAP, AND THAT MAP IS THE ONLY WAY
    A HANG IS READABLE. Every other retrieval on this class answers a
    question about records that ARRIVED. A pin that stopped emits
    nothing, so no record-shaped query can ever mention it. `_seen`
    holds one small entry per `(name, site)` identity -- never per
    record -- and `pin_state` reads it without waiting for anything.
    """

    def __init__(self, path: Optional[Path] = None,
                 flush_every: int = DEFAULT_FLUSH_EVERY,
                 enabled: bool = True,
                 max_bytes: int = MAX_FILE_BYTES,
                 backup_count: int = FILE_BACKUP_COUNT,
                 retain_rows: int = RETAIN_ROWS,
                 max_identities: int = MAX_IDENTITIES) -> None:
        self.path = path
        self.flush_every = max(1, int(flush_every))
        self.enabled = enabled
        # max_bytes <= 0 disables rotation. backup_count is clamped to at
        # least one, because a "rotation" with nowhere to rotate to would
        # be a delete, and this sink does not delete evidence.
        self._max_bytes = max(0, int(max_bytes))
        self._backup_count = max(1, int(backup_count))
        # retain_rows is clamped to at least one for the same reason
        # backup_count is: a window of zero would be a sink that keeps
        # nothing, which is the silence this module exists to remove.
        self._retain = max(1, int(retain_rows))
        # BOTH are bounded, and both bounds are load-bearing.
        #
        # `_all` is the obvious one. `_buf` is not, and it was the trap:
        # `flush` deliberately does NOT drain the buffer while `path` is
        # None (v3.24.83 — draining with nowhere to write destroyed 200
        # records every flush). A sink installed before its run
        # directory exists therefore accumulates in `_buf` with nothing
        # to stop it. The old row cap stopped it by accident, because
        # `emit` returned before appending anywhere. Removing that cap
        # without bounding `_buf` would have re-opened an unbounded
        # growth path AND pinned every record `_all` had already
        # evicted, since the two hold the same objects.
        self._buf: deque = deque(maxlen=self._retain)
        self._all: deque = deque(maxlen=self._retain)
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        # 10.3 — LAST SEEN, PER IDENTITY, NOT PER RECORD.
        #
        #     {(name, site): [last_monotonic, emissions, last_ts,
        #                     last_dt]}
        #
        # A plain list rather than a tuple or a dataclass because it is
        # written in place on every single emit: rebuilding a tuple
        # there would allocate once per record, on the Qt GUI thread,
        # which is the one place this module is not allowed to be
        # careless. Guarded by `_lock`, the same lock the buffer uses,
        # so no second lock and no new deadlock ordering.
        self._seen: dict = {}
        self._max_identities = max(1, int(max_identities))
        self._identity_overflow = 0
        self._seq = 0
        self._dropped = 0
        self._evicted = 0
        self._rotate_failures = 0
        # 10.3 phase 2 -- how many call sites handed `emit` a
        # duration it refused; see `_as_measured_duration`. A
        # non-zero value means a caller is passing something that
        # is not a measurement, and the records it produced carry
        # None rather than a fabricated latency. Counted rather
        # than logged because nothing on this path is allowed to
        # touch I/O.
        self._duration_rejected = 0

    def emit(self, name: str, actual: Any, expected: Any = None,
             ok: Optional[bool] = None,
             context: Optional[dict] = None,
             site: Optional[str] = None,
             module: Optional[str] = None,
             count: int = 1,
             duration: Optional[float] = None) -> Optional[Signal]:
        """Record one observation. NEVER raises, NEVER blocks on I/O.

        Fires on BOTH the satisfied and violated paths — see the module
        docstring. `ok` is derived by equality when an expectation is
        given and no verdict is supplied, which keeps the common call
        site to two arguments.

        v3.24.9x — NEVER REFUSES. This method used to compare `_seq`
        against a 2,000,000-row cap and return None for the rest of the
        process once it was reached, which measurably happened after
        about 13 hours on the operator's machine. There is no row at
        which the instrument switches itself off any more. What is
        bounded is how much is kept resident; see `RETAIN_ROWS`.
        """
        if not self.enabled:
            return None
        try:
            if ok is None and expected is not None:
                ok = bool(actual == expected)
            # 10.3 — the frame walk moved OUT of the lock. `site` and
            # `module` are pure functions of this thread's own call
            # stack, which cannot change while this frame runs, so
            # holding the buffer lock across two `sys._getframe` walks
            # bought nothing. The depth is unchanged: frame 2 is still
            # the caller of `emit`, wherever inside `emit` it is read.
            # The identity has to exist before the record does, because
            # the record carries an interval that is keyed on it.
            _name = str(name)
            _site = site or _caller_site(2)
            _mod = module or _caller_module(2)
            # 10.3 phase 2 -- THE DURATION IS JUDGED BEFORE THE
            # LOCK. `_as_measured_duration` is a pure function of
            # its argument, so holding the buffer lock across it
            # would buy nothing, for the same reason the frame
            # walk above sits outside. The REFUSAL is counted
            # inside, with every other counter.
            _dur = _as_measured_duration(duration)
            _dur_refused = duration is not None and _dur is None
            with self._lock:
                self._seq += 1
                if _dur_refused:
                    self._duration_rejected += 1
                # 10.3 — BOTH CLOCKS, READ ADJACENT, INSIDE THE LOCK.
                #
                # `_now` is MONOTONIC and is the only thing ever
                # subtracted. `_ts` is the wall clock and is the only
                # thing ever shown to a human. The operator's machine
                # sleeps and its clock is stepped by NTP; a wall-clock
                # difference across either is wrong, and can be
                # NEGATIVE, which would read as a pin that fired before
                # it fired. Reading them one line apart under the lock
                # keeps the pair describing the same instant, and keeps
                # `ts` ordered with `seq` the way it already was.
                _now = time.monotonic()
                _ts = _utc_iso()
                _prev = self._seen.get((_name, _site))
                if _prev is None:
                    # FIRST EMISSION. `dt` stays None -- there is no
                    # previous, and saying 0.0 would claim a
                    # measurement nobody took.
                    _dt = None
                    _nth = 1
                    if len(self._seen) < self._max_identities:
                        self._seen[(_name, _site)] = [_now, 1, _ts, None]
                    else:
                        # The ceiling. Recording continues; only the
                        # TIMING of this new identity is refused, and
                        # `nth=0` says so rather than claiming a first
                        # emission that will never get a second.
                        _nth = 0
                        self._identity_overflow += 1
                else:
                    # ROUNDED TO THE CLOCK'S OWN RESOLUTION, 1e-07.
                    #
                    # Not a tolerance and not a tidy-up: nothing is
                    # discarded that was ever measured.
                    # `time.get_clock_info("monotonic")` on the
                    # operator's machine reports
                    # `QueryPerformanceCounter()` with resolution
                    # 1e-07, so the eighth decimal onward is float
                    # representation noise the clock did not produce.
                    #
                    # It is worth doing because those digits are
                    # written to disk on EVERY record. Measured: an
                    # unrounded interval serialised as
                    # `3.199998172931373e-05`, 21 characters, against
                    # `3.2e-05` at 7. Over the operator's real
                    # 495-byte average record that is the difference
                    # between costing his 300 MB ladder 7.9% of its
                    # retained history and costing it 5.9%.
                    #
                    # A sub-microsecond gap rounds to 0.0, and 0.0 is
                    # honest there: it is a real interval too short for
                    # the clock to resolve. It is still not confusable
                    # with "no previous", because that case carries
                    # `dt=None` and `nth=1`.
                    _dt = round(_now - _prev[0], 7)
                    _nth = _prev[1] + 1
                    _prev[0] = _now
                    _prev[1] = _nth
                    _prev[2] = _ts
                    _prev[3] = _dt
                sig = Signal(
                    name=_name,
                    site=_site,
                    module=_mod,
                    actual=freeze(actual),
                    expected=freeze(expected),
                    ok=ok,
                    kind=("sample" if expected is None and ok is None
                          else "check"),
                    count=int(count) if count else 1,
                    seq=self._seq,
                    ts=_ts,
                    dt=_dt,
                    nth=_nth,
                    duration=_dur,
                    context=freeze(context) if context else None,
                )
                # EVICTION IS COUNTED, AND THE TWO EVICTIONS MEAN
                # DIFFERENT THINGS.
                #
                # Falling out of `_all` is not a loss: the record was
                # written to the file and the file is what the record
                # set IS. It only means `records()` is a window, which
                # `health()['evicted']` says out loud so no reader can
                # mistake the window for the whole run.
                #
                # Falling out of `_buf` IS a loss, because that record
                # never reached disk. It can only happen when there is
                # nowhere to write yet, and it is counted in `_dropped`
                # beside every other real loss.
                if len(self._all) == self._retain:
                    self._evicted += 1
                if len(self._buf) == self._retain:
                    self._dropped += 1
                self._buf.append(sig)
                self._all.append(sig)
                due = len(self._buf) >= self.flush_every
            if due:
                self.flush()
            return sig
        except Exception:  # noqa: BLE001 - instrumentation must never break the app
            return None

    def _rotate_if_needed(self) -> None:
        """Roll the file to ``<name>.1`` once it reaches `max_bytes`.

        v3.24.9x — THE FILE HAD NO BOUND AT ALL. `flush` appended and
        nothing ever checked the size, and because `install_process_sink`
        stamps a CONSTANT name, every process appended to the same file
        for ever. Measured on the operator's disk 2026-08-13:
        ``~/.acervator_logs/signals/session.jsonl`` at 2,445,435,093
        bytes, 4,942,000 records, still growing at 72.5 MB per active
        hour. Its neighbours in ``trade/`` were all capped at 50 MB x 5
        by ``NDJSONWriter``; this one writer was not.

        Deliberately the SAME shape as
        ``NDJSONWriter._rotate_if_needed``, down to the primitive.
        ``Path.replace`` rather than ``Path.rename`` because rename
        raises WinError 183 on Windows when the destination exists, and
        this repo has already paid for that once: 350,470
        'gate.log.4 -> gate.log.5' warnings and a writer stalled for
        three days. One module, one rotation idiom.

        Called with `_io_lock` held, so a rename can never interleave
        with another thread's append.
        """
        if self.path is None or self._max_bytes <= 0:
            return
        if not self.path.is_file():
            return
        if self.path.stat().st_size < self._max_bytes:
            return
        for i in range(self._backup_count - 1, 0, -1):
            src = self.path.parent / f"{self.path.name}.{i}"
            dst = self.path.parent / f"{self.path.name}.{i + 1}"
            if src.exists():
                src.replace(dst)
        self.path.replace(self.path.parent / f"{self.path.name}.1")

    def flush(self) -> None:
        """Append the buffer to disk. Append-only: never rewrites.

        v3.24.83 — DOES NOT DRAIN THE BUFFER WHEN THERE IS NOWHERE TO
        WRITE. The previous version popped `_buf` and THEN returned if
        `path` was None, so every flush silently destroyed 200 records.
        Measured: a run emitted 2,240 signals and wrote a file with
        none of them, reporting `buffered: 0, dropped: 0` — the sink
        built to stop data vanishing was vanishing data, and its own
        health said everything was fine.

        A sink with no path yet is the NORMAL state early in a run: it
        is installed before `_build_sim` so the fleet emitters are
        captured, and the run directory does not exist until SimRunLog
        opens it. Those records must survive until the path arrives.

        v3.24.9x — rotation happens HERE, before the append and inside
        the same `_io_lock`, so the rows that trigger a rollover land in
        the NEW file rather than in a handle that has just been renamed
        out from under them. A rotation that fails is counted and the
        rows are still written: missing the bound for one cycle is a
        recoverable cost, losing the records is not.

        v3.24.9x — the replacement buffer is a bounded `deque`, not a
        plain list. Swapping in a list here would silently undo the
        bound `__init__` set: the sink would run bounded until its
        first flush and unbounded for ever after, which is the worst of
        both because it would test clean.
        """
        if self.path is None:
            return
        with self._lock:
            rows, self._buf = self._buf, deque(maxlen=self._retain)
        if not rows:
            return
        with self._io_lock:
            try:
                self._rotate_if_needed()
            except OSError:
                # Surfaced through `health()`. A cap that silently stops
                # being enforced is the same failure as a sink that
                # silently stops recording.
                self._rotate_failures += 1
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open(
                        "a", encoding="utf-8", errors="replace") as fh:
                    for r in rows:
                        fh.write(r.to_json() + "\n")
            except OSError:
                # Losing instrumentation must not take the run down. The
                # loss is counted so a reader can see the record set is
                # partial.
                self._dropped += len(rows)

    # ── retrieval ────────────────────────────────────────────────────
    #
    # Returns TUPLES of FROZEN records. A caller cannot append to, remove
    # from, or edit what was captured. "Emitter data is not allowed to be
    # mutated after retrieval."

    def records(self, name: Optional[str] = None) -> tuple:
        """Every record STILL RETAINED, newest last.

        This is a window, not the run. Records older than `RETAIN_ROWS`
        have been evicted from memory; they are still on disk, and
        `health()['evicted']` says how many, so a caller counting from
        here can tell an empty result from a trimmed one.
        """
        with self._lock:
            rows = tuple(self._all)
        if name is None:
            return rows
        return tuple(r for r in rows if r.name == name)

    def since(self, seq: int) -> tuple:
        """Records with `seq` greater than the given watermark.

        v3.24.81 — for incremental consumers. The Console polls this on a
        timer rather than being pushed to, for two reasons: `emit` must
        stay free of I/O and of callbacks (it runs on the tick path), and
        a push would arrive on whatever thread emitted — which for a Qt
        widget is a cross-thread touch. Polling sidesteps both and
        batches naturally.

        v3.24.9x — WALKS BACK FROM THE NEWEST AND STOPS. The previous
        body was ``tuple(r for r in self._all if r.seq > seq)``, a scan
        of every retained record on every call. Its own docstring said
        "the cost is proportional to what arrived, not to the run",
        and that was not true of the code underneath it.

        It matters because of WHO calls it: `MainWindow._drain_signals`,
        on a 500 ms QTimer, on the Qt GUI thread — the thread that must
        not run unbounded loops. At the old 2,000,000-row cap that was
        up to two million comparisons twice a second, on the thread
        that also paints 37 bots.

        `_all` is append-only under `_lock` and `seq` is assigned under
        the same lock, so it is strictly increasing left to right. The
        first record at or below the watermark therefore means every
        record before it is too, and the walk can stop there. That makes
        the cost what the docstring always claimed: proportional to what
        arrived since the last poll.
        """
        with self._lock:
            newest_first = []
            for record in reversed(self._all):
                if record.seq <= seq:
                    break
                newest_first.append(record)
        newest_first.reverse()
        return tuple(newest_first)

    def count(self, name: Optional[str] = None) -> int:
        return len(self.records(name))

    def violations(self) -> tuple:
        return tuple(r for r in self.records() if r.ok is False)

    def names(self) -> tuple:
        return tuple(sorted({r.name for r in self.records()}))

    def by_subsystem(self, subsystem: Optional[str] = None) -> dict:
        """What has been recorded, grouped by subsystem.

        v3.24.91. Operator's model, 2026-08-10: the test pins are "all
        wired out to the same message handler that parses the messages
        by application subsystem". This is that parse. The sink already
        held every record; nothing could ask it for one subsystem's
        worth without walking the whole set by hand.

        The subsystem is the part of the name before the first dot:
        `sim.06.004.counter.trades_fired` belongs to `sim`. A name
        with no dot is its
        own subsystem, so no record can fall out of the grouping.

        Returns {subsystem: tuple of records}. Records stay in the order
        they were emitted. Pass `subsystem` to get just that one bucket,
        so a reader can take one subsystem at a time.
        """
        buckets: dict = {}
        for r in self.records():
            sub = r.name.split(".", 1)[0]
            if subsystem is not None and sub != subsystem:
                continue
            buckets.setdefault(sub, []).append(r)
        return {k: tuple(v) for k, v in buckets.items()}

    def stats(self) -> dict:
        """Per-signal totals. The shape an operator or an audit reads."""
        out: dict = {}
        for r in self.records():
            s = out.setdefault(r.name, {"n": 0, "ok": 0, "bad": 0,
                                        "unjudged": 0, "site": r.site})
            s["n"] += 1
            if r.ok is True:
                s["ok"] += 1
            elif r.ok is False:
                s["bad"] += 1
            else:
                s["unjudged"] += 1
        return out

    # ── timing ───────────────────────────────────────────────────────
    #
    # 10.3. Everything above answers a question about records that
    # ARRIVED. A HANG HAS NO RECORD, so none of it can mention a pin
    # that stopped. These three read the last-seen map instead, and
    # need nothing to arrive.

    def identities(self) -> tuple:
        """Every `(name, site)` pair this sink has recorded, sorted.

        THE IDENTITY IS THE PAIR. `_throttle_admit` keys its rate limit
        on it and says why: the same signal from two places is two
        different things to a reader. `stats()` keys on the name alone
        and therefore merges them into one row; this does not, and
        neither does `timing()`.
        """
        with self._lock:
            return tuple(sorted(self._seen))

    def pin_state(self, name: str, site: str,
                  fresh_within: float = FRESH_WITHIN,
                  stale_after: float = STALE_AFTER) -> dict:
        """How one identity is doing RIGHT NOW, with nothing arriving.

        THIS IS THE HANG QUERY. Ask it about a pin at any moment and it
        answers from what it already holds; it never waits for a
        record, because the record is exactly what a hung pin is not
        going to send.

        An identity this sink has never seen returns `PIN_NEVER` --
        not an empty dict, not None, and not a raised KeyError. A pin
        that never fired is a real, reportable state, and returning
        nothing for it would make it indistinguishable from a caller
        that forgot to ask.

        Returns `{name, site, state, age, n, last_ts, last_dt}`:

            state    one of `PIN_STATES`
            age      seconds since the last emission, monotonic.
                     None only for `PIN_NEVER`
            n        emissions of this identity in this sink.
                     0 only for `PIN_NEVER`
            last_ts  wall clock of the last emission, for a human
            last_dt  the interval the last record carried. None when
                     that record was the first
        """
        # THE CLOCK IS READ INSIDE THE LOCK, AND THAT ORDER IS THE
        # WHOLE POINT.
        #
        # Sampling `now` first and then blocking on a contended lock
        # compares an OLD clock reading against a last-seen stamp that
        # `emit` wrote WHILE this call was waiting. `age` then comes out
        # NEGATIVE -- a pin that fired in the future -- and because a
        # negative age is below every threshold it classifies as
        # PIN_FRESH, so the wrong number arrives wearing the healthiest
        # label it has.
        #
        # MEASURED on this class before the order was fixed: 20,000
        # queries against 4 concurrent emitters produced 6 negative
        # ages, worst -0.0314865 s; `timing()` produced 9 in 5,000
        # surveys. Rare is not never, and this is the query the health
        # panel will poll for the life of the process.
        #
        # Taking both readings under one lock makes the comparison
        # ordered by construction: nothing can move `_seen` between the
        # snapshot and the clock, so `age` cannot be negative. The cost
        # is one `time.monotonic()` inside the lock -- measured 0.0175
        # us -- on a query, not on `emit`.
        with self._lock:
            prev = self._seen.get((name, site))
            snapshot = None if prev is None else tuple(prev)
            now = time.monotonic()
        return _classify(name, site, now, snapshot,
                         fresh_within, stale_after)

    def timing(self, name: Optional[str] = None,
               fresh_within: float = FRESH_WITHIN,
               stale_after: float = STALE_AFTER) -> dict:
        """`{(name, site): pin_state}` for every identity SEEN so far.

        Pass `name` to take one name's identities, which is how the two
        sites of a shared name are read apart.

        THIS CANNOT REPORT `PIN_NEVER`, and the reason is structural
        rather than an omission: an identity that never emitted is not
        in the map, so nothing here knows it should exist. A roster of
        expected pins lives in `docs/EMITTER_IDENTIFICATION.md`, not in
        the sink. To ask about a specific pin that may never have
        fired, name it to `pin_state`.
        """
        # ONE CLOCK READING, INSIDE THE LOCK, FOR THE WHOLE SURVEY.
        #
        # Inside for the reason `pin_state` gives at length: a reading
        # taken before a contended lock goes stale against stamps
        # `emit` writes while this call waits, and every age computed
        # from it can be negative.
        #
        # ONE reading rather than one per identity, because a survey
        # whose rows are aged against different instants cannot be
        # compared row to row -- which is the only thing a survey is
        # for. `_classify` then runs OUTSIDE the lock, so the work that
        # scales with the identity count is not work `emit` waits on.
        with self._lock:
            snap = {key: tuple(value)
                    for key, value in self._seen.items()
                    if name is None or key[0] == name}
            now = time.monotonic()
        return {key: _classify(key[0], key[1], now, value,
                               fresh_within, stale_after)
                for key, value in snap.items()}

    def health(self) -> dict:
        """Sink integrity — reported so a partial record set announces
        itself instead of reading as a complete one.

        v3.24.9x — ``capped`` IS GONE, and was not replaced by a
        permanently-False field. It meant "the emitter has stopped
        recording", and there is no longer any row at which that
        happens, so keeping the key would have been a promise the sink
        could never make good on and a reader could never falsify.

        In its place, the two facts that ARE now true and were not
        reported before:

          retained — how many records are still in memory. `records()`
                     returns this many, so a caller can tell a window
                     from a whole run without guessing.
          evicted  — how many aged out of that window. NOT a loss: they
                     are on disk. A non-zero value says "count from the
                     file, not from me".

        `dropped` keeps its meaning exactly — records that never
        reached disk — and now also carries buffer evictions, which are
        the one eviction that IS a loss.
        """
        return {
            "emitted": self._seq,
            "buffered": len(self._buf),
            "retained": len(self._all),
            "evicted": self._evicted,
            "dropped": self._dropped,
            # v3.24.9x — a rotation that could not run. Nothing was lost
            # when this is non-zero, but the file is over its cap and
            # somebody should know that without reading the disk.
            "rotate_failures": self._rotate_failures,
            # 10.3 phase 2 -- a duration `emit` refused. Nothing
            # was lost when this is non-zero: the record was kept
            # and only its duration reads as "not measured". It is
            # here because a caller passing a flag or a negative
            # interval is a defect at the CALL SITE, and this is
            # the only place the sink can say so.
            "duration_rejected": self._duration_rejected,
            # 10.3 — the last-seen map's size, so its growth is visible
            # without a debugger, and its ceiling announces itself
            # rather than quietly stopping.
            "identities": len(self._seen),
            "identity_overflow": self._identity_overflow,
            "path": str(self.path) if self.path else None,
        }


_ACTIVE: Optional[SignalSink] = None
_ACTIVE_LOCK = threading.Lock()


_THROTTLE_LOCK = threading.Lock()
_THROTTLE: dict = {}


def _throttle_admit(name: str, site: str, every: float):
    """Admit this observation, or fold it into the next one.

    Returns the number of observations the admitted record stands for
    (>= 1), or None when this one is suppressed.

    Keyed by (name, site) rather than name alone: the same signal
    emitted from two places is two different things to a reader, and
    collapsing them would hide which one is firing.
    """
    now = time.monotonic()
    with _THROTTLE_LOCK:
        key = (name, site)
        last, pending = _THROTTLE.get(key, (None, 0))
        if last is not None and (now - last) < every:
            _THROTTLE[key] = (last, pending + 1)
            return None
        _THROTTLE[key] = (now, 0)
        return pending + 1


def reset_throttle() -> None:
    """Forget every rate-limit window. For tests and run boundaries."""
    with _THROTTLE_LOCK:
        _THROTTLE.clear()


def set_sink(sink: Optional[SignalSink]) -> None:
    """Install the process sink. A run owns its sink and clears it after."""
    global _ACTIVE
    with _ACTIVE_LOCK:
        _ACTIVE = sink


def get_sink() -> Optional[SignalSink]:
    with _ACTIVE_LOCK:
        return _ACTIVE


def emit(name: str, actual: Any, expected: Any = None,
         ok: Optional[bool] = None,
         context: Optional[dict] = None,
         every: float = 0.0,
         module: Optional[str] = None,
         duration: Optional[float] = None) -> Optional[Signal]:
    """Module-level emit — the universal connection point.

    Deliberately a plain function, not a bus subscription: a call site
    should not need a reference to anything. With no sink installed this
    is a dict lookup and a return, so instrumentation can live on a hot
    path and cost nothing when nobody is collecting.
    """
    sink = get_sink()
    if sink is None:
        return None
    _site = _caller_site(2)
    _mod = module or _caller_module(2)
    if every and every > 0:
        # v3.24.90 — SYNCHRONISER. Operator, 2026-08-08: "I am
        # concerned that because programs are constantly looping that
        # some emitters (maybe most) will be spamming I/O messages."
        #
        # Correct concern: a per-candle emitter on a 35-bot fleet fires
        # tens of thousands of times a run, and at that rate the file
        # is a cost rather than evidence. `every=N` admits one record
        # per N seconds per (name, site) and folds the suppressed ones
        # into the next record's `count`, so nothing is silently
        # dropped -- the line says how many it stands for.
        #
        # A FAILING check is NEVER suppressed. Rate-limiting the thing
        # you built the network to catch is how a spam control becomes
        # a blindfold.
        _judged = ok if ok is not None else (
            bool(actual == expected) if expected is not None else None)
        if _judged is not False:
            _n = _throttle_admit(name, _site, float(every))
            if _n is None:
                return None
            return sink.emit(name, actual, expected=expected, ok=ok,
                             context=context, site=_site, module=_mod,
                             count=_n, duration=duration)
    return sink.emit(name, actual, expected=expected, ok=ok,
                     context=context, site=_site, module=_mod,
                     duration=duration)


def install_process_sink(
    log_dir: Optional[Path] = None,
    flush_every: int = 500,
) -> Optional["SignalSink"]:
    """Install the sink the whole process emits into.

    v3.24.88. Operator, 2026-08-08: "Emitters don't work unless program
    is running or a debug is performed."

    That was accurate. `set_sink` had exactly one caller -- the Fleet
    Replay controller, at the start of a replay -- so during ordinary
    live operation nothing was collecting and every `emit()` in the
    platform returned immediately. An instrument that only records
    while someone is watching it cannot report the thing nobody was
    watching for, which is the only kind of failure worth instrumenting.

    Called once from `main()`. A replay still installs its own sink for
    the duration of the run so its records land in that run's
    directory; it now RESTORES this one afterwards instead of clearing
    to None, so live collection resumes when the replay ends.

    THIS is the sink the row cap used to switch off. It runs for the
    life of the process, so it was the one that reached 2,000,000 rows
    after about 13 hours and then recorded nothing more. It no longer
    stops. Its file is bounded by rotation and its memory by
    `RETAIN_ROWS`; neither bound touches whether `emit` records.

    Buffered -- `flush_every` is higher than a replay's because this
    runs for the life of the process and the write should be rarer.

    Returns the sink, or None if the log directory cannot be opened;
    collection is never allowed to prevent startup.
    """
    try:
        base = Path(log_dir) if log_dir else (
            Path.home() / ".acervator_logs" / "signals")
        base.mkdir(parents=True, exist_ok=True)
        # ONE FILE, SHARED BY EVERY PROCESS AND EVERY LAUNCH.
        #
        # v3.24.9x — the previous comment here said "one file per
        # process", and that was wrong in effect. The name is a
        # CONSTANT, so process 2 opens the same file process 1 wrote
        # and appends to it, for ever. Measured 2026-08-13: four
        # separate runs, distinguishable only by `seq` restarting,
        # sharing one 2,445,435,093-byte file.
        #
        # The name STAYS constant. Stamping a pid or a clock into it
        # would trade one unbounded thing for another — an unbounded
        # COUNT of files, which is the failure
        # `acervator_watchdog.prune_postmortem_bundles` already exists
        # to clean up after. The file is bounded by rotation instead:
        # 50 MB x 5 backups, the same as every writer in
        # `logging_engine`, so a reader always knows the one path to
        # look at and the disk footprint has a ceiling.
        sink = SignalSink(flush_every=flush_every)
        sink.path = base / "session.jsonl"
        set_sink(sink)
        return sink
    except OSError:
        return None


def read_records(path: Path) -> tuple:
    """Read a captured JSONL back as frozen records.

    v3.24.91 — READS BACK EVERY FIELD IT WROTE.

    10.3 — AND STILL READS EVERY FIELD IT NEVER WROTE. The two timing
    keys are absent from all 598,500 records in the operator's live
    history, measured read-only 2026-08-15 with zero decode failures
    across six generations. Their absence restores as "not measured",
    which is what it is.

    `to_json` writes `module`, `kind` and `count`; this reader dropped
    all three, so the record that came off disk was not the record that
    went on. A `sample` read back as a `check`, which flipped the
    verdict column in `message()` from "----" to a judgement. `module`
    read back as the empty string and displayed as "?". A folded record
    that stood for 300 observations read back as 1, so a reader counting
    from the file undercounted.

    Payloads are re-frozen on the way in for the same reason: `emit`
    stores a list as a tuple, and a plain list read back would not
    compare equal to the record that was written.

    The operator's standing rule is that emitter data may not change
    after it is read back. The reader was the thing changing it.

    A FIELD IT CANNOT USE COSTS THE FIELD, NEVER THE FILE. Two things
    are skipped here and they are not the same thing. A line that will
    not DECODE is not a record at all, and `continue` drops it. A line
    that decodes cleanly and carries one unusable number IS a record:
    its name, site, verdict and sequence are all readable, and the
    coercion helpers return None for the number so the rest survives.
    Dropping the whole record would delete a real emission from the
    census to punish a field no consumer has to read, and an emission
    missing from the census is the exact silent absence a monitor
    exists to notice.
    """
    out: list[Signal] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ctx = d.get("context")
                out.append(Signal(
                    name=d.get("name", ""), site=d.get("site", ""),
                    actual=freeze(d.get("actual")),
                    expected=freeze(d.get("expected")),
                    ok=d.get("ok"), seq=int(d.get("seq", 0) or 0),
                    ts=d.get("ts", ""),
                    context=freeze(ctx) if ctx else None,
                    module=d.get("module") or "",
                    kind=d.get("kind") or "check",
                    count=int(d.get("count") or 1),
                    # 10.3 — ABSENT IS NOT ZERO. Every one of the
                    # 598,500 records already on the operator's disk
                    # was written before these two keys existed, and
                    # each one must still read back as a valid record.
                    # A missing `dt` restores as None ("no interval was
                    # measured"), never as 0.0, and a missing `nth`
                    # restores as 0 ("never measured"), never as 1 --
                    # which would claim every legacy record was the
                    # first emission of its identity.
                    dt=_as_float(d.get("dt")),
                    nth=_as_ordinal(d.get("nth")),
                    # 10.3 phase 2 — ABSENT IS NOT ZERO, for the same
                    # reason as `dt` above. Every record written before
                    # this key existed restores with duration None, "no
                    # duration was measured", never 0.0, which would
                    # claim every legacy operation was instantaneous.
                    duration=_as_float(d.get("duration"))))
    except OSError:
        return ()
    return tuple(out)
