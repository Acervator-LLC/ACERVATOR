"""An autonomous fold must not rebuy above the price it sold at.

THE DEFECT
==========
``_execute_manual_rebalance`` is reached by three callers and two of
them fire with no operator present -- Wire Stack and Max Cartridge, via
``caller_intent="wire_stack"`` and ``"max_cartridge"``. On that path
every MEM-171 gate is bypassed by design. Nothing compared the rebuy
price against the price the tranche was SOLD at.

The discharge loop sorts the ladder by ``ref`` descending and consumes
whatever the fill reaches. It books profit only where
``_t_ref > fill_price``. A tranche re-bought ABOVE its own ref was
therefore consumed for zero booked profit, its queued ``usd`` left the
ladder for good, and the closing emit still read
``Discharged N tranche(s)``. The module's own header states the
invariant that was being broken: "CRITICAL: fold ONLY executes when
price < fold_ref ... DO NOT change this condition."

THE RULE IS NOT NEW
===================
The autonomous tick fold-back already owns it, as a per-tranche filter
whose arithmetic lives in ``src/trading/otd_math.py``::

    eligible  <=>  ticker.last <= ref * fold_rebuy_factor(interval, fee)

This change asks that module the same question at the second site. It
does not restate the arithmetic; four copies of one rule is why
``otd_math`` exists.

WHAT THE CHANGE DOES, AND THE ONE THING IT DOES NOT
===================================================
The verb is REFUSE. The order is placed BEFORE the discharge loop runs,
so a filter inside that loop would not stop a trade -- it would only
move where the bought units land. The gate withholds the WHOLE fire when
not one queued tranche is eligible.

When SOME tranches are eligible the fire proceeds unchanged and the loop
still walks into ineligible ones. That residue is real, it is measured
in the unit's report, and it is NOT closed here -- it is a different
verb and a different change. ``test_a_partly_eligible_ladder_still_fires``
pins the half this change is responsible for; nothing in this file
asserts the residue exists, because a test that did would have to go red
when the residue is finally fixed.

THREE THINGS STAY EXACTLY AS THEY WERE
======================================
* the operator's own button, ``manual_button``, which
  ``manual_fire_tranche`` records as an operator ruling: "OTD
  per-tranche price gate (operator chose this tranche explicitly)";
* the SCRUM side of the same method, which sells;
* a fold on a bot with an empty ladder, where no ``ref`` exists for a
  distance to be measured against.

EVERY CHECK IS RUN TWICE, AGAINST A PROVABLY PRE-CHANGE TWIN
============================================================
``_pregate()`` loads a second copy of the shipping module with the gate
block textually removed. ``test_the_twin_is_the_pre_change_file`` hashes
that stripped text and requires it to equal the sha256 of the file as it
stood before this change. So the twin is not "roughly the old code": it
is the old code, byte for byte, or the whole file errors out.

Every refusal is then asserted twice -- refused here, PLACED on the twin.
A gate that silently stopped reaching the code would turn both sides
green; requiring the twin to trade is what makes a green run mean
something.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import math
import re
import sys
import tempfile
from pathlib import Path

import pytest

from src.trading.otd_math import fold_rebuy_factor
from src.trading.scrumming_bot import ScrummingBot

REPO = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO / "src" / "trading" / "scrumming_bot.py"


class StalePlant(RuntimeError):
    """The twin no longer matches the shipping text.

    DELIBERATELY NOT an ``AssertionError``. The controls below are
    written as "the twin must trade"; if a stale strip raised an
    assertion it could be mistaken for an ordinary failure, and if it
    raised nothing the twin would silently BE the gated code and every
    control would pass without testing anything.

    A source file this module cannot read is refused the same way. A
    reader that cannot find its anchors must say so out loud rather
    than report zero hits.
    """


def _normalise(text: str) -> str:
    """LF, whatever the checkout wrote. THE ONE PLACE THAT DECIDES.

    Every anchor in this module is the text of a LINE. Matching a line
    must not depend on which bytes end it, so the form is decided once,
    here, and nothing below splits or joins on CRLF again.

    WHY THIS FUNCTION EXISTS
    ========================
    It used to be the other way round: this module read the file as
    bytes, split on CRLF, and pinned a sha256 of the exact CRLF bytes.
    ``.gitattributes`` then had to pin ONE source file in the whole
    repository to CRLF to keep this suite green. Git converts at
    CHECKOUT, so that pin made the suite depend on a byte layout no
    fresh clone reproduced by itself: without it, 80 of this file's
    122 tests failed with ``StalePlant`` on a clean clone.

    A carriage return that is NOT part of a CRLF pair is REFUSED rather
    than translated. Translating one would silently rewrite the content
    of a string literal in the source under test; refusing says the
    file is not the file this module knows how to read.
    """
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        raise StalePlant(
            "the source carries a carriage return outside a CRLF pair, so "
            "its lines cannot be recovered without changing its content"
        )
    return text


# Read as BYTES, then normalise EXPLICITLY. ``read_text`` would hand
# back LF too, but it would translate a lone CR as well and leave
# nowhere to refuse one. Reading the bytes keeps that decision visible
# and keeps all of it inside ``_normalise``.
SOURCE = _normalise(SOURCE_PATH.read_bytes().decode("utf-8"))

# sha256 of src/trading/scrumming_bot.py as it stood at git 5405996436d1
# -- the commit this change was written against, BEFORE the gate block
# was inserted -- with its line endings normalised to LF.
#
# NORMALISED RATHER THAN RAW, AND THAT IS THE WHOLE POINT. The constant
# this replaces was a digest of that file's CRLF bytes. A digest of raw
# bytes pins the line-ending form exactly as hard as it pins the
# content, so it went red on a fresh clone for a reason that had
# nothing to do with the code. This one is a digest of the CONTENT:
# the same pre-change source, in the form the git blob stores and a
# checkout now writes.
#
# IT IS DERIVED FROM THE CONSTANT IT REPLACES, not measured afresh:
# the reversal below reproduced 306b2d13..f33d6 exactly under CRLF, and
# this digest is that identical text with every CRLF folded to LF.
#
# WHAT IT STILL CATCHES, WHICH IS WHY IT IS HERE AT ALL: every real
# change to ``scrumming_bot.py`` outside the reversed spans reaches
# this digest through ``_pre_change_source`` and turns this test red.
# The line-ending form stopped mattering. The content did not.
# RE-BASED 2026-08-22, and this is the tripwire doing its job rather
# than a failure being papered over. Two reviewed repairs landed in
# ``scrumming_bot.py`` after the digest above was taken, and both are
# outside every span this file reverses, so both reached the digest:
#
#   1. `repair/target-topup-preserves-growth` -- `set_target_balance_live`
#      compares the operator's input against the ANCHOR, not the grown
#      target. A top-up smaller than accrued growth used to collapse the
#      anchor and destroy the growth.
#   2. `repair/holdings-follow-the-exchange` -- `_reconcile_holdings`
#      adopts the exchange balance on upward drift instead of refusing
#      every correction, so the Target Delta's first operand comes from
#      the venue. This one ADDS a `self._main_lots.append({`, which is
#      why the citation anchors moved and why the re-anchor had to skip
#      that occurrence when counting ordinals.
#
# The reversal itself still reproduces cleanly: `_pre_change_source`
# returns zero orphans, so every `:NNNN` in the file still names a line
# that exists on both sides. What changed is the CONTENT this digest
# describes -- "the shipping file with the U3 gate block and the site-B
# spans removed" -- not the method that derives it.
#
# RE-BASED AGAIN 2026-08-22, same tripwire, same reason. One further
# repair landed in ``scrumming_bot.py`` outside every reversed span:
#
#   3. the three paths the drift-UP adopt left open --
#      ``bootstrap_exchange_state`` still clamped holdings to the book
#      on every launch; the top-up was measured from
#      ``max(scalar, book)`` so a scalar leading the book left
#      ``sum(_main_lots) != _current_holdings``; and the reconciliation
#      lot took ``stats.current_price`` untested, booking a basis of
#      0.0 on a bot that had not completed a priced tick.
#
# This one ADDS a second `self._main_lots.append({`, in the shared
# writer ``_book_reconciliation_lot``, and REMOVES the one that was
# inline in the drift-UP branch. It also holds
# `_adopt = min(exchange_units, _claimable)` twice, once in the new
# bootstrap adopter ABOVE the reconcile. The monotonic guard refused
# that citation rather than re-pointing it into the wrong method, and
# it was re-pointed by hand at the branch the prose means.
#
# `_pre_change_source` still returns zero orphans.
#
# RE-BASED A THIRD TIME 2026-08-22, issue #69, same tripwire, same
# reason. One line changed in the MODULE DOCSTRING of
# ``scrumming_bot.py``. That line read "See ARCHITECTURE.md for full
# invariants list."; no such document is in the tree, so the header
# stated something false. The replacement line says so.
#
# WHAT THIS RE-BASE IS NOT. No executable line moved. The file held
# 15595 lines before the edit and 15595 after, so every ``:NNNN``
# citation still names the line it named. ``CITATION_ANCHORS`` in
# ``tests/test_extractor_tranche_containment.py`` needed no ordinal
# shift, and that file's 122 tests pass unchanged on both sides. The
# edit adds no occurrence of any anchor string. It is outside the gate
# block and outside every span in ``SITE_B_SPANS``, which is why it
# reaches this digest at all.
#
# ``_pre_change_source`` returns zero orphans, and the CRLF rendering
# reconstructs the identical text.
#
# RE-BASED A FOURTH TIME 2026-08-24, issue #102, same tripwire, same
# reason. One repair landed in ``scrumming_bot.py`` outside every span
# this file reverses, so it reaches the digest:
#
#   4. the BB-priority arm could not refuse. ``tick()`` added +0.30 to
#      ``eff_confidence`` and then compared the sum against the 0.25
#      ``_TA_CONFIDENCE_FLOOR``. On a quantity bounded [0, 1] that is
#      ``conf >= -0.05``: no reading fails it, including exactly 0.0,
#      so the confidence conjunct was the hard override the operator
#      refused by name on 2026-04-26. The addition also travelled --
#      nine sites in ``tick()`` printed the inflated number rather than
#      the measured one. The repair leaves ``eff_confidence`` alone and
#      relaxes the THRESHOLD on that arm instead, proportionally, to
#      ``_BB_PRIORITY_CONFIDENCE_FLOOR`` = 0.25 / 1.30.
#
# WHAT THIS RE-BASE IS. Two module-scope constants beside
# ``_TA_CONFIDENCE_FLOOR``, and the gate block in ``tick()`` rewritten
# in place. +86 lines, in two bands: +68 from :574 through :7662 and
# +86 from :9316 down. The unit adds no method and no
# ``self._main_lots.append({``, so no anchor is new and no ordinal
# count moved. ``CITATION_ANCHORS`` in
# ``tests/test_extractor_tranche_containment.py`` was re-anchored in
# the SAME change -- 42 anchors, all moved, all read back out of the
# post-change file -- and that file's 121 tests pass.
#
# The 74 self-citation tokens inside ``scrumming_bot.py`` moved by the
# same two bands. ``:488-494`` did not: pre-change 488-494 is the
# phantom-timeframe filter, so that token names a spec document rather
# than this file, and a cross-document reference is not shifted.
#
# ``_pre_change_source`` returns zero orphans.
#
# The prior digests, kept so the chain is auditable:
#
# RE-BASED A FIFTH TIME 2026-08-24, issue #104, same tripwire, same
# reason. One repair landed in ``scrumming_bot.py`` outside every span
# this file reverses, so it reaches the digest:
#
#   5. the two remaining confidence favours could not refuse either.
#      ``tick()`` added ``position_boost`` and ``bb_confidence_boost``
#      to ``eff_confidence`` and compared the sum against the floor.
#      ``position_boost`` reaches +0.40 by enumeration of its own terms
#      and was OBSERVED at +0.4000 over 406 stone tablets;
#      ``bb_confidence_boost`` reaches +0.60 by derivation from its two
#      component bounds. Either exceeds the 0.25 floor alone, and on 73
#      of 2,436 readings the favour by itself cleared the floor that
#      judged it -- so on those the comparison had no false case
#      whatever the indicators measured. The repair leaves
#      ``eff_confidence`` alone, and it is now exactly
#      ``summary.consensus_confidence``. All THREE favours, the #102 arm
#      included, are summed and divide the floor through the new
#      module-scope ``_skewed_confidence_floor``.
#
# WHAT THIS RE-BASE IS. One module-scope function beside
# ``_TA_CONFIDENCE_FLOOR``, the two ``+=`` lines in ``tick()`` replaced
# by the prose that says why each favour is a favour, the floor
# computation rewritten in place, and five log lines repaired. +141
# lines, in two bands: +52 from :694 through :7782 and +141 from :9543
# down. The unit adds no method and no ``self._main_lots.append({``, so
# no anchor is new and no ordinal count moved. ``CITATION_ANCHORS`` in
# ``tests/test_extractor_tranche_containment.py`` was re-anchored in the
# SAME change -- 42 anchors, all moved, all read back out of the
# post-change file -- and that file's 121 tests pass.
#
# The 74 self-citation tokens inside ``scrumming_bot.py`` moved by the
# same two bands. ``:488-494`` did not, for the reason #102 recorded:
# it names a spec document rather than this file. Nineteen further
# tokens carry another module's filename, and one more -- ``[:180]`` at
# the credential-refusal emit -- is a SLICE that the regex above matches
# and that was never a citation. Those 21 were left alone, and the count
# is written down so the gap does not read as an omission.
#
# ``_pre_change_source`` returns zero orphans.
#
# RE-BASED A SIXTH TIME 2026-08-24, issue #106, same tripwire, same
# reason. One repair landed in ``scrumming_bot.py`` outside every span
# this file reverses, so it reaches the digest:
#
#   6. the per-Fold growth cap never compounded. Four sites spelled it
#      out as ``self._anchor_target_balance * (max_target_growth_pct /
#      100)``, and ``_anchor_target_balance`` is the operator's input
#      value that no Fold ever moves. The cap therefore held ONE dollar
#      value for the life of the bot and the curve was
#      ``anchor x (1 + 0.01N)`` rather than ``anchor x 1.01^N``.
#      Measured on the live fleet the same day: 35 of 38 bots carried
#      accrued growth, IMU had grown 27.1% and still capped each Fold at
#      $0.50, and $13.37 sat parked in ``standing_surplus_usd`` behind
#      the frozen number. The repair adds ONE property,
#      ``cycle_growth_cap_usd``, whose base is the target as it stood
#      when the cycle opened, and the four sites read it.
#
# WHAT THIS RE-BASE IS. One property beside ``_apply_fold_target_growth``
# and four call sites rewritten in place, plus the prose that stated the
# old base. +131 lines, in SEVEN bands: +0 at and below :694, +82 from
# :1784, +94 from :2534, +101 from :3609, +114 from :10291, +122 from
# :10800 and +131 from :13258 down. The unit adds no
# ``self._main_lots.append({``, so no ordinal count moved.
# ``CITATION_ANCHORS`` in ``tests/test_extractor_tranche_containment.py``
# was re-anchored in the SAME change -- 40 anchors moved, 1 did not, ONE
# is new (:1785, the property) and ONE WAS RETIRED (:1858, whose line
# this change deletes) -- and that file's 121 tests pass.
#
# TWO CROSS-FILE TOKENS WERE WRITTEN OUT IN FULL, and this is the part
# a later reader needs. ``# Ported from RAIntSimBat.py:2144-2159``
# appears twice. Those digits name lines in ANOTHER module, but
# ``_CITATION_RE`` cannot tell a cross-file citation from a self one, so
# ``_one`` looked 2144 and 2159 up in ``back`` like any other. Before
# this change both resolved by luck. This change moved ``SITE_B_SPANS``
# span 2 down onto shipping lines 2062-2188, which SWALLOWED both
# numbers -- a reversed span contributes no entry to ``back`` -- and
# ``_pre_change_source`` returned four orphans.
#
# THE GUARD WAS NOT EDITED TO CLEAR THIS. The 2026-08-13 note in
# ``CITATION_ANCHORS`` records the established repair for exactly this
# shape: a ``:NNNN`` in ``scrumming_bot.py`` that means another file is
# "written out in full". Both now read ``RAIntSimBat.py lines
# 2144-2159``, on the same lines, so no line count moved and no anchor
# shifted a second time. The remaining 17 cross-file tokens still
# resolve by luck and are NOT repaired here; they are named in the
# unit's report as a latent hazard of the same shape.
#
# ``_pre_change_source`` returns zero orphans.
#
# RE-BASED A SEVENTH TIME 2026-08-24, issue #98 defect 4, same
# tripwire, same reason. One repair landed in ``scrumming_bot.py``
# outside every span this file reverses, so it reaches the digest:
#
#   7. the fold-tranche counters did not reconcile with the standing
#      list. The stated identity is
#      ``created - closed - discarded == len(_fold_tranches)``, and it
#      failed on 13 of the operator's 38 bots, in BOTH directions.
#      Negative drift is exactly "a record left the queue and no term
#      of the identity moved". Two of the eleven removal sites in this
#      file did that: the TD-017 fold guard, which bumped
#      ``_tranches_malformed_dropped`` -- not a term -- and the restore
#      filter in ``import_scrumming_state``, which bumped nothing. Both
#      now bump ``_tranches_discarded_lifetime``, and the malformed
#      counter became a SUB-COUNT of it rather than a fourth term.
#
# WHAT THIS RE-BASE IS. The counter-declaration prose in ``__init__``
# rewritten in place; two inserts in ``import_scrumming_state``; the
# guard block in ``tick()`` replaced by a call, which makes it ELEVEN
# LINES SHORTER; one new method, ``_drop_malformed_fold_tranches``,
# above ``_settle_fold_plan``; and the ladder comment in
# ``_execute_manual_rebalance`` restated. +125 lines, 8 hunks, NINE
# cumulative bands, and one STEP DOWN -- +51 above the tick guard, +40
# below it. See the 2026-08-24 note in ``CITATION_ANCHORS`` for the
# per-band table. The unit adds no ``self._main_lots.append({``, so no
# ordinal count moved, and no anchor is new or retired.
# ``CITATION_ANCHORS`` in ``tests/test_extractor_tranche_containment.py``
# was re-anchored in the SAME change -- 42 anchors, 42 resolved, cross
# checked against the git hunk map with 0 disagreements -- and that
# file's 121 tests pass.
#
# The self-citation tokens inside ``scrumming_bot.py`` moved by the
# same bands and were verified BY READ-BACK against a full pre-to-post
# line map: 77 tokens, 0 mismatches, 0 naming a line this change
# created. ``:488-494``, the 19 cross-file tokens and the ``[:180]``
# slice were left alone for the reasons #104 and #106 wrote down. ONE
# citation was RETIRED rather than shifted: the ladder comment cited
# the tick guard by line, and that guard now has a name, so the prose
# names it.
#
# ``_pre_change_source`` returns zero orphans, and the CRLF rendering
# reconstructs the identical text.
#
# The prior digests, kept so the chain is auditable:
#   986d79ed7785015d12a57bfc877ba1b078027d93b2f7655ec2fbc78a90ef2082
#   29276909ff46dce02bc650de45802c779539adb7093b010cd875ef376201e9a0
#   4b5c51bde7c54836dcd935c85c76ee06757e1fe8b79edd2ce1febb0831ad3c75
#   ffe8cebd69cbc2eac674d0a8696efdca3542112fe1606bc0dcd3546297c1288f
#   d4edd46f7ce7d04ef716255fc36976056f75a4d938351b3c0ff9388932cd5aef
#   03d05460421d2c601a37dadc5cd97b6a77805a974ac29f6f3f2b5e75cf7f40f5
#   ac3459c2b80406bf7c4e9698c186cb29c77fe32c17ef6d3a8a1f5cb56f3076aa
# Re-derived 2026-08-25. FOUR things moved under this digest and the
# re-derivation enumerated every one: black's layout pass, the 42 re-anchored
# citation numbers, the F541 f-prefix fix, and an autoflake pass that dropped
# unused local bindings. The first three were cancelled symmetrically on both
# reconstructions; the fourth was checked line by line and is assignment
# removals only. FLAGGED, not absorbed: one of them, `_intended_buy_asset =
# buy_cost / ticker.last`, was an UNGUARDED division, so a zero last price
# used to raise here and now does not.
PRE_CHANGE_SHA256 = "b8b79a6a88c2f7bc2e6f34104712d9faa4ee67c86e53e7655429a6b632b6f5c2"

_GATE_FIRST_LINE = (
    "            # v3.25.x (U3) -- THE AUTONOMOUS FOLD IS GATED ON PRICE."
)
_RESUMES_AT = "            # v3.24.xx (operator directive 2026-08-07)"

# The SAME token shape `test_extractor_tranche_containment.py` reads
# with. Two definitions of "a citation" would let a token be re-anchored
# by one file and checked by the other.
_CITATION_RE = re.compile(r":(\d{3,5})(?:-(\d{3,5}))?")

# ── SITE B, AND WHY IT LIVES IN THIS FILE ────────────────────────────
#
# The gate above is not the whole change any more. On 2026-08-15 the
# SAME finiteness rule landed at the second site on the fold money path
# -- `_preview_fold_growth`, which SIZES the order rather than gating it
# -- because promoting the gate alone would have widened that one. The
# gate makes MORE folds fire; every extra fire is then sized by a sort
# whose key could receive `nan`.
#
# `_stripped_source` cuts the gate block only, so its output is the
# pre-gate file WITH site B still applied. That is the right twin for
# every behavioural control below: it differs from the shipping code in
# the gate and in nothing else. The hash constant, though, names the
# file before EITHER change, so reproducing it means undoing BOTH.
#
# Each span is (first line, last line, what the pre-change file held
# instead). The span is inclusive, and its first line must occur EXACTLY
# ONCE -- an anchor that has drifted is caught as a stale plant rather
# than quietly selecting the wrong region.
SITE_B_SPANS = (
    (
        "        # How many ladder rows the LAST growth preview could not order.",
        "        # v3.16.58 — Below-min-cost throttle state. Operator-discovered",
        ("        # v3.16.58 — Below-min-cost throttle state. Operator-discovered",),
    ),
    (
        '        """What ``_apply_fold_target_growth`` WOULD add. Moves no money.',
        "        WHY THIS EXISTS (operator directive 2026-08-07)",
        (
            '        """What ``_apply_fold_target_growth`` WOULD add. Mutates nothing.',
            "",
            "        WHY THIS EXISTS (operator directive 2026-08-07)",
        ),
    ),
    (
        "        # Same highest-price-first discharge order as the real loop, on",
        "            _remaining -= take",
        (
            "        # Same highest-price-first discharge order as the real loop, on",
            "        # a COPY -- previewing must not reorder the live queue.",
            "        _tranches = sorted(",
            "            [t for t in (self._fold_tranches or []) if isinstance(t, dict)],",
            '            key=lambda t: float(t.get("ref", 0.0) or 0.0), reverse=True)',
            "        _remaining = float(units)",
            "        _accum = 0.0",
            "        for t in _tranches:",
            "            if _remaining <= 1e-12:",
            "                break",
            '            take = min(float(t.get("units", 0.0) or 0.0), _remaining)',
            "            if take <= 1e-12:",
            "                continue",
            '            _ref = float(t.get("ref", 0.0) or 0.0)',
            "            if _ref > price:",
            "                _accum += take * (_ref - price)",
            "            _remaining -= take",
        ),
    ),
    (
        "            # RESET BEFORE THE LOOP, NOT INSIDE IT. `_denom_pre <= 0`",
        "            self._fold_preview_unreadable_refs = 0",
        (),
    ),
    (
        "            # SIZING ON A PARTLY READABLE LADDER MUST NOT BE SILENT.",
        "            # THE TWIN NOTICE, ONE FIELD OVER. A row whose `ref` is",
        ("            # THE TWIN NOTICE, ONE FIELD OVER. A row whose `ref` is",),
    ),
    # THE THIRD SITE'S ADDITIONS, REVERSED TOO.
    #
    # The `units` finiteness guard landed in the SAME method after this
    # reversal was written. Its guard block sits inside the span above
    # that rewrites the whole discharge loop, so it is already undone --
    # but the counter it writes sits AFTER `_remaining -= take`, which is
    # that span's end anchor, so the assignment survived into a twin
    # where `_unreadable_units` is never defined. The twin then raised
    # `NameError` on every in-spec row and 27 money controls went red on
    # a fault in the RECONSTRUCTION, not in the shipping code.
    #
    # Reversing the third site here is not a courtesy to it. It makes
    # this control cover BOTH changes: the twin is now the file before
    # either guard, so "the amount is bit-identical" is asserted across
    # the pair rather than across one of them.
    (
        "        # Read by the one caller to say out loud that the sizing answer",
        "        self._fold_preview_unreadable_units = _unreadable_units",
        (),
    ),
    (
        "            self._fold_preview_unreadable_units = 0",
        "            self._fold_preview_unreadable_units = 0",
        (),
    ),
    (
        "            # THE TWIN NOTICE, ONE FIELD OVER. A row whose `ref` is",
        "            buy_usd_target = -delta_usd + _growth_preview",
        ("            buy_usd_target = -delta_usd + _growth_preview",),
    ),
    # 2026-08-20, ISSUE #21 -- THE GRANT-PATH POSTCONDITION IS A NEW PART.
    #
    # `_ensure_capital_reservation` emitted `actual` and `expected` as
    # the SAME expression, so its verdict derived True on every tick of
    # every bot and a green record from it meant nothing. The repair
    # reads the HELD reservation against the NEEDED quantity and judges
    # the pair against the 1 % band the update path above it already
    # keeps the reservation inside. +47 lines, every one of them inside
    # that one `else:` branch.
    #
    # It is enumerated here because the digest below is over the WHOLE
    # file. A part that is not named reaches `_pre_change_source`
    # unreversed, the digest moves, and every "the twin still trades"
    # control in this file is then comparing against something that is
    # not the code that shipped.
    (
        "            # v3.24.93 - the success path reports too, so a green run is",
        "                    every=60.0,",
        (
            "            # v3.24.93 - the success path reports too, so a green run is",
            "            # evidence rather than silence. Throttled: this runs on",
            "            # every tick of every bot.",
            "            try:",
            "                from src.core.signal_contract import emit as _cr_ok",
            "                _cr_ok(",
            '                    "bot.01.002.postcondition.capital_reservation",',
            "                    actual=round(float(_qty), 10),",
            "                    expected=round(float(_qty), 10),",
            "                    every=60.0,",
        ),
    ),
)

# THE RE-ANCHOR IS DERIVED, NOT TRANSCRIBED, AND THAT IS A CORRECTION.
#
# This used to be a hand table of six `(old, new, text)` rows, on the
# model "one insertion, one uniform shift". That model was true while
# the only insertion sat at :12029, below almost every citation in the
# file. Site B inserts near the TOP -- at :891, :1723 and :1746 -- so it
# pushes nearly everything down: SIXTY-THREE citations moved, in four
# bands (0, +6, +75, +107), not six in one.
#
# A table naming six of sixty-three is a SAMPLE of the re-anchor, not a
# record of it, and the fifty-seven it leaves out are precisely the ones
# no reader would notice going wrong. So the map is now derived: each
# surviving line carries its shipping line number through the reversal,
# where it lands IS its pre-change number, and every `:NNNN` token is
# rewritten through that map. Nothing is transcribed, so nothing can be
# transcribed wrongly, and the coverage is every citation in the file.


def _reverse_to_pre_change(lines: list[str]) -> tuple[list[str], dict[int, int]]:
    """The pre-change lines, and shipping line number -> pre-change number."""
    tagged: list[tuple[int | None, str]] = list(enumerate(lines, 1))

    starts = [i for i, (_, ln) in enumerate(tagged) if ln == _GATE_FIRST_LINE]
    resumes = [i for i, (_, ln) in enumerate(tagged) if ln.startswith(_RESUMES_AT)]
    if len(starts) != 1 or len(resumes) != 1:
        raise StalePlant(
            f"expected one gate block and one resume anchor, found "
            f"{len(starts)} and {len(resumes)}"
        )
    tagged = tagged[: starts[0] - 1] + tagged[resumes[0] - 1 :]

    for first, last, replacement in SITE_B_SPANS:
        hits = [i for i, (_, ln) in enumerate(tagged) if ln == first]
        if len(hits) != 1:
            raise StalePlant(
                f"site-B anchor occurs {len(hits)} times, expected once: "
                f"{first!r}. Fix the anchor; do not delete the reversal."
            )
        s = hits[0]
        ends = [i for i, (_, ln) in enumerate(tagged) if ln == last and i >= s]
        if not ends:
            raise StalePlant(f"site-B end anchor never follows its start: {last!r}")
        tagged = tagged[:s] + [(None, ln) for ln in replacement] + tagged[ends[0] + 1 :]

    back = {ship: i + 1 for i, (ship, _) in enumerate(tagged) if ship}
    return [ln for _, ln in tagged], back


def _pre_change_source(source: str | None = None) -> tuple[str, list[int]]:
    """The whole change undone, plus any citation with no pre-change line.

    ``source`` defaults to the shipping file. It is a parameter so the
    control below can hand the SAME file back in the other line-ending
    form and require the same answer out.
    """
    text = SOURCE if source is None else _normalise(source)
    pre_lines, back = _reverse_to_pre_change(text.split("\n"))
    orphans: list[int] = []

    def _one(group):
        if group is None:
            return None
        number = int(group)
        if number in back:
            return str(back[number])
        orphans.append(number)
        return group

    def _sub(match):
        head, tail = _one(match.group(1)), _one(match.group(2))
        return f":{head}" if tail is None else f":{head}-{tail}"

    return _CITATION_RE.sub(_sub, "\n".join(pre_lines)), orphans


AUTONOMOUS = ("wire_stack", "max_cartridge")
EVERY_INTENT = ("manual_button", "wire_stack", "max_cartridge")

# Money is compared to the bit. A tolerance would hide exactly the
# drift these comparisons exist to catch.
EXACT = 0.0


# ── the provably pre-change twin ─────────────────────────────────────


def _stripped_source(source: str | None = None) -> str:
    """The shipping source with the gate block cut back out.

    Line endings are the normalised LF, in and out.
    """
    lines = (SOURCE if source is None else _normalise(source)).split("\n")
    starts = [i for i, ln in enumerate(lines) if ln == _GATE_FIRST_LINE]
    resumes = [i for i, ln in enumerate(lines) if ln.startswith(_RESUMES_AT)]
    if len(starts) != 1 or len(resumes) != 1:
        raise StalePlant(
            f"expected one gate block and one resume anchor, found "
            f"{len(starts)} and {len(resumes)}. Fix the anchors; do not "
            f"delete the twin."
        )
    # One line above the block start is the blank line the insertion
    # added; one line above the resume anchor is the lone '#' that
    # opens the comment block the gate was inserted in front of.
    cut_from, cut_to = starts[0] - 1, resumes[0] - 1
    if not lines[cut_from] == "" or not lines[cut_to].strip() == "#":
        raise StalePlant(
            f"the block boundaries moved: line {cut_from + 1} is "
            f"{lines[cut_from]!r} and line {cut_to + 1} is "
            f"{lines[cut_to]!r}"
        )
    return "\n".join(lines[:cut_from] + lines[cut_to:])


def _load_twin():
    """Import the stripped source as a second, separate module."""
    text = _stripped_source()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "_pregate_scrumming_bot.py"
        path.write_bytes(text.encode("utf-8"))
        name = "src.trading._pregate_scrumming_bot"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise StalePlant("the stripped source would not load")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


_TWIN = None
_PRE_CHANGE = None


def _pregate():
    """The pre-gate ``ScrummingBot``: site B applied, the gate removed."""
    global _TWIN
    if _TWIN is None:
        _TWIN = _load_twin()
    return _TWIN.ScrummingBot


def _load_module(text: str, name: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.py"
        path.write_bytes(text.encode("utf-8"))
        full = f"src.trading.{name}"
        spec = importlib.util.spec_from_file_location(full, path)
        if spec is None or spec.loader is None:
            raise StalePlant(f"{name} would not load")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        spec.loader.exec_module(module)
    return module


def _pre_change():
    """The bot from BEFORE EITHER change, byte-proved by the sha test.

    `_pregate` keeps site B, because the gate controls want a twin that
    differs from shipping in the gate ALONE. This one has neither, and
    it is what the money comparison needs: the amount an in-spec fold
    placed before this unit touched anything.
    """
    global _PRE_CHANGE
    if _PRE_CHANGE is None:
        text, orphans = _pre_change_source()
        if orphans:
            raise StalePlant(f"citations with no pre-change line: {orphans}")
        _PRE_CHANGE = _load_module(text, "_prechange_scrumming_bot")
    return _PRE_CHANGE.ScrummingBot


# ── the least bot that can run the real method ───────────────────────


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.events: list[tuple] = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")
        if "data" in payload:
            self.events.append((topic, payload["data"]))


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_folded_usd = 0.0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0


class _Config:
    def __init__(self, *, symbol="CHIP/USD", interval=1.0, fee=0.6):
        self.symbol = symbol
        self.target_asset = symbol.split("/")[0]
        self.exchange_id = "coinbase"
        self.scrumming_interval_pct = interval
        self.trading_fee_pct = fee
        self.max_target_growth_pct = 1.0
        self.profit_folding_active = True
        self.scrum_fold_pct = 100


class _Order:
    id = "order-u3"
    filled = 0.0
    average = 0.0


class _Ticker:
    def __init__(self, last):
        self.last = last


def _bot(
    cls,
    *,
    tranches,
    holdings,
    target,
    price,
    symbol="CHIP/USD",
    interval=1.0,
    fee=0.6,
    quote_free=1_000_000.0,
    qrate=1.0,
    fill_price=None,
):
    """A bot of ``cls`` that runs the real ``_execute_manual_rebalance``.

    Only the outward edges are stubbed: the exchange, the emitters, the
    settled-fill read. ``_preview_fold_growth``,
    ``_apply_fold_target_growth``, ``reset_swos_cycle`` and the whole
    discharge loop are the shipping code.

    ``cls`` is either the shipping ``ScrummingBot`` or the pre-change
    twin's, so one scenario can be run on both and compared.
    """
    bot = object.__new__(cls)
    bot.bot_id = "u3-bot"
    bot.seen = {"placed": None, "settled": None, "balances": []}
    bot._bus = _Bus()
    bot.config = _Config(symbol=symbol, interval=interval, fee=fee)
    bot.stats = _Stats()
    bot._fold_tranches = [dict(t) for t in tranches]
    bot._main_lots = [{"units": holdings, "initial_buy_price": price}]
    bot._current_holdings = holdings
    bot._target_balance = target
    bot._anchor_target_balance = target
    bot._quote_to_usd = qrate
    bot._manual_fire_pending = True
    bot._fold_queue_usd = sum(float(t.get("usd", 0.0)) for t in tranches)
    bot._fold_cycle_cap_consumed = 0.0
    bot._standing_surplus_usd = 0.0
    bot._retained_this_cycle_usd = 0.0
    bot._fold_accumulator = 0.0
    bot._target_grow_last_side = None
    bot._tranches_closed_lifetime = 0
    bot._tranches_created_lifetime = 0
    bot._pending_wire_credits = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = None

    settled_price = price if fill_price is None else fill_price

    async def _refresh():
        return qrate

    async def _place(**kwargs):
        bot.seen["placed"] = dict(kwargs)
        return _Order()

    async def _settled(order, symbol_, requested, tick_price):
        bot.seen["settled"] = (order.id, symbol_, requested, tick_price)
        return requested, settled_price, True

    async def _balance(currency):
        bot.seen["balances"].append(currency)
        if currency == bot.config.target_asset:
            free = holdings
        else:
            free = quote_free
        return type("B", (), {"total": free, "free": free, "absent": False})()

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._emit_voting_panel_snapshot_at_fire = lambda **kw: bot.seen.setdefault(
        "snapshots", []
    ).append(kw)
    bot._emit_gate_decision_at_fire = lambda **kw: bot.seen.setdefault(
        "gates", []
    ).append(kw)
    bot._reset_opposing_hysteresis_after_fill = lambda: bot.seen.setdefault(
        "disarms", []
    ).append(True)
    bot._route_scrum_proceeds_via_wires = lambda scrum_usd, sell_fill, label: (
        bot.seen.setdefault("routed", []).append((scrum_usd, sell_fill, label)) or 0.0
    )
    bot.note_scrum_retention_usd = lambda retained_usd: bot.seen.setdefault(
        "retained", []
    ).append(retained_usd)
    return bot


def _fire(bot, price, intent):
    asyncio.run(bot._execute_manual_rebalance(_Ticker(price), intent))
    return bot


def _observable(bot):
    """Everything a caller of this method can see it having done.

    Not just the order call: the ladder it left, the lots it opened, the
    target it grew and the words it said. A gate that placed the same
    order but ate a tranche differently would pass an order-only
    comparison.
    """
    return {
        "placed": bot.seen["placed"],
        "settled": bot.seen["settled"],
        "balances": bot.seen["balances"],
        "tranches": [
            (t.get("usd"), t.get("units"), t.get("ref")) for t in bot._fold_tranches
        ],
        "lots": [
            (
                lot.get("units"),
                lot.get("initial_buy_price"),
                lot.get("operator_initiated"),
            )
            for lot in bot._main_lots
        ],
        "holdings": bot._current_holdings,
        "target": bot._target_balance,
        "queue_usd": bot._fold_queue_usd,
        "closed_lifetime": bot._tranches_closed_lifetime,
        "trades": bot.stats.total_trades,
        "folded_usd": bot.stats.total_folded_usd,
        "last_side": bot._last_trade_side,
        "last_price": bot._last_trade_price,
        "messages": bot._bus.messages,
        "events": bot._bus.events,
    }


def _refusal(bot):
    """The refusal lines this change emits, and only those."""
    return [
        m
        for m in bot._bus.messages
        if "AUTONOMOUS FIRE REFUSED (opposing distance" in m
    ]


# ── scenario vocabulary ──────────────────────────────────────────────
#
# A ladder is built from the refs alone; ``usd`` and ``units`` follow
# from them so the numbers are self-consistent rather than decorative.


def _ladder(*refs, units=100.0):
    return [
        {"usd": ref * units, "units": units, "ref": ref, "initial_buy_price": ref * 0.8}
        for ref in refs
    ]


def _tick_factor(interval=1.0, fee=0.6):
    """The factor the AUTONOMOUS TICK path computes for this config.

    Reproduces its coercion exactly, ``or``-fallbacks included::

        minimum_opposing_trade_distance_pct(
            getattr(config, 'scrumming_interval_pct', 0) or 0,
            getattr(config, 'trading_fee_pct', 0.6) or 0.6)

    A CONFIGURED FEE OF 0.0 IS FALSY AND BECOMES 0.6. That is a real
    quirk of the shipping tick path, not of this change, and this file
    reproduces it on purpose: the gate's job is to ask the SAME question
    the tick path asks, and a gate that quietly disagreed with it about
    a zero fee would be a fourth copy of the rule wearing a shared
    import. ``test_a_zero_fee_is_treated_as_the_tick_path_treats_it``
    pins the agreement, and the quirk itself is recorded as a defect
    this unit found and deliberately did not fix.
    """
    return fold_rebuy_factor(interval or 0, fee or 0.6)


def _threshold(ref, interval=1.0, fee=0.6):
    """The highest price at which ``ref`` alone is still eligible."""
    return ref * _tick_factor(interval, fee)


def _admits(ladder, interval=1.0, fee=0.6):
    """The highest price at which ANY tranche in ``ladder`` is eligible.

    The DEAREST ref sets it. A cheap tranche is the strictest, not the
    most permissive -- a reading the first draft of this file got
    backwards, which turned a refusal scenario into a firing one.
    """
    return max(
        _threshold(float(t.get("ref", 0.0) or 0.0), interval, fee) for t in ladder
    )


def _one_float_above(ladder, interval=1.0, fee=0.6):
    """The cheapest price at which the whole ladder is refused."""
    return math.nextafter(_admits(ladder, interval, fee), math.inf)


def _ladder_units(bot):
    return sum(float(t.get("units", 0.0) or 0.0) for t in bot._fold_tranches)


# ── the twin is real ─────────────────────────────────────────────────


def test_the_twin_is_the_pre_change_file():
    """CONTROL OF CONTROLS. The whole change must be reversible, exactly.

    THIS CHANGE HAS THREE PARTS AND THE TEST UNDOES ALL THREE.

    1. The gate block, cut back out by ``_stripped_source``.
    2. Five spans at site B -- ``_preview_fold_growth``'s finiteness
       filter, the counter it writes, the caller's notice, and the
       docstring heading that stopped being true when the counter was
       added. ``SITE_B_SPANS`` holds what the pre-change file had in
       each one's place.
    3. The citation re-anchor, undone through the map derived in
       ``_reverse_to_pre_change`` rather than a hand-written table.

    Undo all three and the sha256 must be the pre-change file's. Nothing
    else changed, and this is what says so.

    IF THIS FAILS: the change is wider than the three parts named above,
    and every "the twin still trades" control is then comparing against
    something that is not the code that shipped.
    """
    text, orphans = _pre_change_source()
    assert orphans == [], (
        f"citations {orphans} name lines that only exist after the change, "
        f"so they have no pre-change line to point at"
    )
    restored = text.encode("utf-8")
    assert hashlib.sha256(restored).hexdigest() == PRE_CHANGE_SHA256, (
        "undoing the gate block, the site-B spans and the citation shift "
        "does not reproduce the pre-change file byte for byte, so the "
        "change is not the three parts this unit claims it is"
    )
    assert b"\r" not in restored, (
        "the twin carries a carriage return, so the digest just checked is "
        "a digest of a byte layout and not of the file's content"
    )

    # AND THE SAME ANSWER COMES BACK FROM THE OTHER LINE-ENDING FORM.
    #
    # This module used to require the file on disk to be CRLF, and
    # ``.gitattributes`` pinned it so that stayed true -- which made the
    # suite green only in a tree carrying one particular byte layout.
    # Reversing the CRLF rendering of the very same source is what says
    # the pin is unnecessary rather than merely gone. If any reader
    # starts splitting on a byte layout again, this assertion goes red,
    # and it goes red whichever form the checkout wrote.
    again, crlf_orphans = _pre_change_source(SOURCE.replace("\n", "\r\n"))
    assert crlf_orphans == [] and again == text, (
        "the same file in CRLF form reconstructs a DIFFERENT pre-change "
        "text, so this module is reading a byte layout and not lines"
    )


def test_every_re_anchored_citation_still_names_its_own_line():
    """THE RE-ANCHOR, over EVERY citation rather than a chosen six.

    For each ``:NNNN`` in the shipping file, the derived map says which
    pre-change line it used to name. This reads BOTH files at those two
    numbers and requires the same text. That is the whole property a
    re-anchor has to have, checked at full coverage.

    IT REPLACED A SAMPLE. The previous form asserted a uniform ``+204``
    over six hand-listed pairs. Site B moved SIXTY-THREE citations in
    four bands, so "uniform" was no longer true and six of sixty-three
    was no longer a record. A test that still passed under those
    conditions would have been measuring its own table, not the file.

    IF THIS FAILS: a citation points at the wrong line -- the exact rot
    the anchor table exists to prevent, reintroduced by the change that
    was supposed to repair it.
    """
    ship = SOURCE.split("\n")
    pre_text, orphans = _pre_change_source()
    pre = pre_text.split("\n")
    _, back = _reverse_to_pre_change(ship)
    assert orphans == [], f"citations with no pre-change line: {orphans}"

    cited = set()
    for match in _CITATION_RE.finditer(SOURCE):
        for group in match.groups():
            if group:
                cited.add(int(group))
    assert cited, "no citations found at all; the token regex is wrong"

    checked = 0
    for number in sorted(cited):
        if number > len(ship) or number not in back:
            continue
        was = back[number]
        assert ship[number - 1] == pre[was - 1], (
            f"citation :{number} reads {ship[number - 1].strip()!r} but the "
            f"line it named before the change reads {pre[was - 1].strip()!r}"
        )
        checked += 1
    assert (
        checked >= 60
    ), f"only {checked} citations were checked; the map lost coverage"


def test_the_gate_block_is_present_in_the_shipping_source():
    """IF THIS FAILS: the change is not in the file under test."""
    assert SOURCE.count(_GATE_FIRST_LINE) == 1
    assert SOURCE.count("AUTONOMOUS FIRE REFUSED (opposing distance)") == 1


def test_site_b_is_present_in_the_shipping_source():
    """IF THIS FAILS: the sizing fix is not in the file under test, and
    every site-B control below is measuring the old code while claiming
    the new one."""
    assert SOURCE.count("_readable.sort(key=lambda pair: pair[0]") == 1
    assert SOURCE.count("FOLD SIZING REF UNREADABLE") == 1
    assert 'key=lambda t: float(t.get("ref", 0.0) or 0.0)' not in SOURCE, (
        "the `float(x) or 0.0` sort key is still in the file; `nan` is "
        "truthy so the `or` never fires and the key still receives it"
    )


# ── b. THE ORDER AMOUNT IS UNCHANGED ON A WELL-FORMED LADDER ─────────

# Each row is (label, tranches, holdings, target, price). The last two
# rows are the ones that matter: a ladder whose units EXCEED the buy, so
# `_remaining` truncates the discharge and the ORDER of the rows decides
# how much surplus is booked. A ladder that fits inside the buy is
# order-independent whatever the sort does, and a suite built only from
# those would pass against the defect.
IN_SPEC_MONEY = [
    (
        "one row",
        [{"usd": 10.0, "units": 100.0, "ref": 1.0, "initial_buy_price": 0.8}],
        50.0,
        175.0,
        0.5,
    ),
    (
        "descending refs",
        [
            {"usd": 10.0, "units": 100.0, "ref": r, "initial_buy_price": 0.8}
            for r in (1.0, 0.9, 0.8)
        ],
        50.0,
        175.0,
        0.5,
    ),
    (
        "ascending refs",
        [
            {"usd": 10.0, "units": 100.0, "ref": r, "initial_buy_price": 0.8}
            for r in (0.8, 0.9, 1.0)
        ],
        50.0,
        175.0,
        0.5,
    ),
    (
        "a zero and a negative beside a good one",
        [
            {"usd": 10.0, "units": 100.0, "ref": r, "initial_buy_price": 0.8}
            for r in (0.0, -1.0, 1.0)
        ],
        50.0,
        175.0,
        0.5,
    ),
    ("empty ladder", [], 50.0, 175.0, 0.5),
    (
        "TRUNCATING: ladder units exceed the buy",
        [
            {"usd": 10.0, "units": 10.0, "ref": r, "initial_buy_price": 0.4}
            for r in (0.6, 0.0, 0.6, 0.0)
        ],
        334.0,
        175.0,
        0.5,
    ),
    (
        "TRUNCATING, reversed",
        [
            {"usd": 10.0, "units": 10.0, "ref": r, "initial_buy_price": 0.4}
            for r in (0.0, 0.6, 0.0, 0.6)
        ],
        334.0,
        175.0,
        0.5,
    ),
    (
        "operator ref magnitudes, 150 rows",
        [
            {
                "usd": 0.44,
                "units": 16.05,
                "ref": 0.02307 + (i % 7) * 0.00004,
                "initial_buy_price": 0.06338,
                "operator_initiated": False,
                "created_ts": 1786682827.88,
                "wire_credits": [],
            }
            for i in range(150)
        ],
        5000.0,
        445.0,
        0.021,
    ),
]


@pytest.mark.parametrize("intent", EVERY_INTENT)
@pytest.mark.parametrize(
    "label, tranches, holdings, target, price",
    IN_SPEC_MONEY,
    ids=[r[0] for r in IN_SPEC_MONEY],
)
def test_a_well_formed_ladder_places_the_same_amount_as_before_the_change(
    label, tranches, holdings, target, price, intent
):
    """THE CONTROL THAT GUARDS THE OPERATOR'S MONEY TODAY.

    Site B decides the AMOUNT sent to the exchange. Every ladder whose
    refs are all finite must place a BIT-IDENTICAL order against the
    byte-provable pre-change twin -- same side, same type, same symbol,
    same amount to the last bit of the float.

    THE TWIN HAS NO GATE, so on the two AUTONOMOUS intents it can place
    where the shipping bot refuses. That difference is the U3 gate doing
    its job and is pinned by the controls above; asserting placement
    parity there would be asserting the gate does nothing. So placement
    parity is required on ``manual_button`` -- which skips the gate in
    the shipping bot and never had one in the twin, leaving site B as
    the only difference between them -- and the AMOUNT is compared
    wherever both did place, on every intent.

    IF THIS FAILS: a fold that fires correctly on the operator's live
    bots today would send a different quantity to Coinbase. That is the
    one outcome this unit is not allowed to have.
    """
    kw = dict(
        tranches=tranches,
        holdings=holdings,
        target=target,
        price=price,
        interval=5.0,
        fee=1.6,
    )
    new = _bot(ScrummingBot, **kw)
    old = _bot(_pre_change(), **kw)
    _fire(new, price, intent)
    _fire(old, price, intent)

    if intent == "manual_button":
        assert (new.seen["placed"] is None) == (old.seen["placed"] is None), (
            f"{label}: one of the two placed an order and the other did "
            f"not, on the intent that skips the gate — so site B changed a "
            f"DECISION. new={new.seen['placed']} old={old.seen['placed']}"
        )
    if new.seen["placed"] is None or old.seen["placed"] is None:
        return
    for field in ("symbol", "side", "order_type", "price"):
        assert (
            new.seen["placed"][field] == old.seen["placed"][field]
        ), f"{label}/{intent}: {field} changed"
    new_amount = float(new.seen["placed"]["amount"])
    old_amount = float(old.seen["placed"]["amount"])
    assert new_amount.hex() == old_amount.hex(), (
        f"{label}/{intent}: the order amount moved from {old_amount!r} to "
        f"{new_amount!r} (delta {new_amount - old_amount!r}) on a ladder "
        f"whose refs are ALL FINITE, so the filter removed nothing and "
        f"the amount had no reason to change"
    )


def test_the_money_comparison_can_see_a_difference():
    """POSITIVE CONTROL for the comparison above.

    The rows above assert two amounts are equal. If the twin were the
    SAME code as the shipping bot, they would be equal for a reason that
    has nothing to do with correctness, and the whole section would be
    an expensive tautology. This drives a ladder holding a ``nan`` --
    the one input the two are supposed to disagree about -- and requires
    them to disagree.

    IF THIS FAILS: the twin is not pre-change code, and every equality
    above proves nothing.
    """
    ladder = [
        {"usd": 10.0, "units": 10.0, "ref": r, "initial_buy_price": 0.4}
        for r in (float("nan"), 0.6, 0.0, 0.6)
    ]
    kw = dict(
        tranches=ladder, holdings=334.0, target=175.0, price=0.5, interval=5.0, fee=1.6
    )
    new = _bot(ScrummingBot, **kw)
    old = _bot(_pre_change(), **kw)
    _fire(new, 0.5, "manual_button")
    _fire(old, 0.5, "manual_button")
    assert new.seen["placed"] is not None and old.seen["placed"] is not None
    assert float(new.seen["placed"]["amount"]) != float(old.seen["placed"]["amount"]), (
        "the shipping bot and the pre-change twin sized the SAME nan "
        "ladder identically; the twin is not the pre-change code"
    )


# ── a. the refused set ───────────────────────────────────────────────


@pytest.mark.parametrize("intent", AUTONOMOUS)
def test_an_autonomous_fold_is_refused_when_no_tranche_is_eligible(intent):
    """THE GATE BITES.

    IF THIS FAILS: the gate is not reached on the autonomous path. The
    defect survives untouched, money still moves, and this unit has
    done nothing.
    """
    ladder = _ladder(1.00, 0.99, 0.98)
    price = _one_float_above(ladder)
    bot = _fire(
        _bot(ScrummingBot, tranches=ladder, holdings=50.0, target=100.0, price=price),
        price,
        intent,
    )

    assert bot.seen["placed"] is None, (
        f"an order was placed at ${price:.8f} although the most "
        f"permissive tranche only allows ${_admits(ladder):.8f}"
    )
    assert len(_refusal(bot)) == 1, bot._bus.messages
    assert bot._fold_tranches == [
        dict(t) for t in ladder
    ], "the ladder was disturbed by a fire that never happened"
    assert bot._current_holdings == 50.0
    assert bot.stats.total_trades == 0


@pytest.mark.parametrize("intent", AUTONOMOUS)
def test_control_the_same_fold_is_placed_without_the_gate(intent):
    """CONTROL for the test above, on the provably pre-change twin.

    IF THIS FAILS: the scenario does not reach the buy even on the old
    code -- something else refuses it -- so the refusal above is not
    evidence that the gate did anything.
    """
    ladder = _ladder(1.00, 0.99, 0.98)
    price = _one_float_above(ladder)
    bot = _fire(
        _bot(_pregate(), tranches=ladder, holdings=50.0, target=100.0, price=price),
        price,
        intent,
    )

    assert bot.seen["placed"] is not None, (
        "the pre-change code did not buy either, so this scenario "
        "cannot show what the gate changed"
    )
    assert bot.seen["placed"]["side"].value == "buy"
    assert _refusal(bot) == []
    assert _ladder_units(bot) < 300.0, (
        "the pre-change code placed the order but consumed no tranche "
        "units, so this scenario does not show the ladder being spent"
    )


def test_the_defect_itself_reproduces_on_the_pre_change_twin():
    """THE DEFECT, shown rather than described.

    Price ABOVE every ref, so no rebuy can be a profit. The pre-change
    code buys anyway, consumes the ladder, books nothing -- because the
    per-slice surplus is only accumulated where ``_t_ref > fill_price``
    -- and reports "Discharged N tranche(s)". Money leaves the ladder
    and no target growth appears against it.

    IF THIS FAILS: the mechanism recorded for this unit is not what the
    old code does, and the whole finding needs re-deriving before the
    gate is justified.
    """
    ladder = _ladder(1.00, 0.99)
    price = 1.20
    old = _fire(
        _bot(_pregate(), tranches=ladder, holdings=50.0, target=100.0, price=price),
        price,
        "max_cartridge",
    )
    assert old.seen["placed"] is not None
    assert _ladder_units(old) < 200.0, "no tranche was consumed"
    assert old._target_balance == 100.0, (
        "the pre-change fold booked growth, so this is not the "
        "zero-profit discharge the finding describes"
    )
    assert any(
        "Discharged" in m for m in old._bus.messages
    ), "the pre-change code did not report the discharge as a success"

    live = _fire(
        _bot(ScrummingBot, tranches=ladder, holdings=50.0, target=100.0, price=price),
        price,
        "max_cartridge",
    )
    assert live.seen["placed"] is None
    assert _ladder_units(live) == 200.0, "the ladder was spent anyway"


def test_the_refusal_names_the_price_the_ladder_and_the_money():
    """The operator must be able to check a refusal against his ladder.

    IF THIS FAILS: a fold stops firing and the log does not say why, at
    which point the gate is indistinguishable from a bug.
    """
    ladder = _ladder(2.00, 1.50)
    price = _admits(ladder) * 1.05
    bot = _fire(
        _bot(ScrummingBot, tranches=ladder, holdings=10.0, target=100.0, price=price),
        price,
        "max_cartridge",
    )
    line = _refusal(bot)[0]
    for fragment in (
        f"${price:.8f}",
        "2 queued tranche(s)",
        f"${_admits(ladder):.8f}",
        "withheld",
    ):
        assert fragment in line, f"{fragment!r} missing from {line!r}"


# ── b. the unchanged set: every fold that should fire, still fires ───
#
# Each row is a fold that is IN SPEC. The claim is not merely that it
# trades -- it is that every argument handed to the order call, and
# every mark left on the bot afterwards, is what the pre-change code
# produced for the same input.

IN_SPEC = [
    (
        "a deep drop, whole ladder eligible",
        dict(
            tranches=_ladder(1.00, 0.99, 0.98), holdings=50.0, target=100.0, price=0.50
        ),
    ),
    (
        "exactly on the threshold of the cheapest ref",
        dict(
            tranches=_ladder(1.00, 0.99, 0.98),
            holdings=50.0,
            target=100.0,
            price=_threshold(0.98),
        ),
    ),
    (
        "exactly on the threshold of the dearest ref",
        dict(
            tranches=_ladder(2.00, 0.10),
            holdings=10.0,
            target=100.0,
            price=_threshold(2.00),
        ),
    ),
    (
        "fifty tranches, the dearest eligible and the cheapest not",
        dict(
            tranches=_ladder(*([1.00] * 49 + [0.20])),
            holdings=50.0,
            target=100.0,
            price=_threshold(1.00),
        ),
    ),
    (
        "a wide interval, so the distance demanded is larger",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.80,
            interval=15.0,
        ),
    ),
    (
        "a zero fee, which the tick path's own idiom turns into 0.6",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=_threshold(1.00, interval=2.0, fee=0.0),
            interval=2.0,
            fee=0.0,
        ),
    ),
    (
        "a crypto-quoted pair, where delta routes via the quote rate",
        dict(
            tranches=_ladder(0.002),
            holdings=1000.0,
            target=100.0,
            price=0.001,
            qrate=50.0,
            symbol="IMU/BTC",
        ),
    ),
    (
        "an empty ladder, which has no ref to measure against",
        dict(tranches=[], holdings=50.0, target=100.0, price=0.50),
    ),
    # A tranche with NO "ref" key is deliberately absent from this row.
    # The discharge loop sorts on `t["ref"]` and raises KeyError on one,
    # before this change and after it. That is a pre-existing defect of
    # the discharge, it is recorded in the unit's report, and it is not
    # this change's to fix -- but a row that crashed both sides would
    # prove nothing about the gate.
    (
        "a zero ref and a negative ref sit beside a good one",
        dict(
            tranches=(
                _ladder(1.00)
                + [
                    {"usd": 0.0, "units": 5.0, "ref": 0.0},
                    {"usd": 0.0, "units": 5.0, "ref": -1.0},
                ]
            ),
            holdings=50.0,
            target=100.0,
            price=0.50,
        ),
    ),
    (
        "the buy is clipped by a thin wallet",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            quote_free=3.0,
        ),
    ),
    (
        "the fill lands below the tick price",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            fill_price=0.45,
        ),
    ),
]


@pytest.mark.parametrize("intent", EVERY_INTENT)
@pytest.mark.parametrize("label, scenario", IN_SPEC, ids=[row[0] for row in IN_SPEC])
def test_an_in_spec_fold_is_unchanged_in_every_observable(intent, label, scenario):
    """THE CONTROL THAT PROTECTS THE OPERATOR.

    IF THIS FAILS: a fold that should have fired did not, or fired
    differently. Too strict is the more dangerous direction -- the
    position never returns to centre, the deficit never shrinks, the
    cartridge re-arms and refuses on every tick, and the ladder is
    stranded with money queued and no path to spend it.
    """
    live = _observable(_fire(_bot(ScrummingBot, **scenario), scenario["price"], intent))
    old = _observable(_fire(_bot(_pregate(), **scenario), scenario["price"], intent))

    assert old["placed"] is not None, (
        f"{label}: the pre-change code did not trade this scenario, so "
        f"it is not evidence about an in-spec fold"
    )
    assert live["placed"] == old["placed"], (
        f"{label} / {intent}: the order call changed\n"
        f"  now: {live['placed']}\n  was: {old['placed']}"
    )
    for key, value in old.items():
        assert live[key] == value, (
            f"{label} / {intent}: {key} changed\n" f"  now: {live[key]}\n  was: {value}"
        )


def test_a_partly_eligible_ladder_still_fires():
    """SCOPE. Some eligible means the fire proceeds, unchanged.

    IF THIS FAILS: the gate has been widened from "refuse when NONE is
    eligible" to something stricter, and folds that the operator's own
    tick path would run are being withheld.

    This is deliberately silent about what the discharge loop then does
    with the ineligible tranches. It still consumes them. That residue
    has a different verb, is measured in the unit's report, and is not
    this change's to close -- and a test that pinned it would have to go
    red the day it is fixed.
    """
    ladder = _ladder(5.00, 0.10)
    price = _threshold(5.00)
    assert price > _threshold(0.10), "this row is not partly eligible"
    bot = _fire(
        _bot(ScrummingBot, tranches=ladder, holdings=10.0, target=100.0, price=price),
        price,
        "max_cartridge",
    )
    assert bot.seen["placed"] is not None
    assert _refusal(bot) == []


# ── c. the operator's own button is untouched ────────────────────────


REFUSED_IF_AUTONOMOUS = [
    (
        "no tranche is eligible",
        dict(tranches=_ladder(1.00), holdings=50.0, target=100.0, price=0.999),
    ),
    (
        "the interval cannot be read",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            interval="abc",
        ),
    ),
    (
        "the fee cannot be read",
        dict(
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            fee=object(),
        ),
    ),
]


@pytest.mark.parametrize(
    "label, scenario",
    REFUSED_IF_AUTONOMOUS,
    ids=[row[0] for row in REFUSED_IF_AUTONOMOUS],
)
def test_the_operator_button_is_never_refused(label, scenario):
    """OPERATOR SOVEREIGNTY, and byte-for-byte at that.

    Every scenario here is refused for an autonomous caller. Pressed by
    the operator each one must still trade, and must leave the bot in
    exactly the state the pre-change code left it in.

    IF THIS FAILS: the gate captured the operator's override. That
    breaks the Session 26 invariant this method's own comments record --
    "Manual Fire is the operator-authorized override. It MUST bypass
    every gate" -- and the ruling in ``manual_fire_tranche`` that names
    this very gate as one the operator has chosen to skip.
    """
    live = _observable(
        _fire(_bot(ScrummingBot, **scenario), scenario["price"], "manual_button")
    )
    old = _observable(
        _fire(_bot(_pregate(), **scenario), scenario["price"], "manual_button")
    )
    assert old["placed"] is not None, f"{label}: nothing to compare"
    assert _refusal_free(live)
    for key, value in old.items():
        assert live[key] == value, (
            f"{label}: manual fire changed in {key}\n"
            f"  now: {live[key]}\n  was: {value}"
        )


def _refusal_free(observable):
    return not [
        m
        for m in observable["messages"]
        if "AUTONOMOUS FIRE REFUSED (opposing distance" in m
    ]


@pytest.mark.parametrize(
    "label, scenario",
    REFUSED_IF_AUTONOMOUS,
    ids=[row[0] for row in REFUSED_IF_AUTONOMOUS],
)
@pytest.mark.parametrize("intent", AUTONOMOUS)
def test_control_the_same_scenario_is_refused_for_an_autonomous_caller(
    label, scenario, intent
):
    """CONTROL for the sovereignty test.

    IF THIS FAILS: the scenarios above are ones nothing refuses, so the
    manual path passing them says nothing about an exemption.
    """
    bot = _fire(_bot(ScrummingBot, **scenario), scenario["price"], intent)
    assert bot.seen["placed"] is None, f"{label}: {intent} was not refused"
    assert len(_refusal(bot)) == 1


def _method_text(source: str, name: str) -> bytes:
    """One method's text, from ``def`` to the next method at its level."""
    lines = _normalise(source).split("\n")
    starts = [
        i
        for i, ln in enumerate(lines)
        if ln.startswith(f"    def {name}(") or ln.startswith(f"    async def {name}(")
    ]
    if len(starts) != 1:
        raise StalePlant(f"expected one definition of {name}, found {len(starts)}")
    body = [lines[starts[0]]]
    for line in lines[starts[0] + 1 :]:
        if line.startswith("    def ") or line.startswith("    async def "):
            break
        body.append(line)
    return "\n".join(body).encode("utf-8")


def test_the_operator_tranche_button_is_textually_unchanged():
    """``manual_fire_tranche`` is the THIRD fold executor.

    It is operator-only -- its single caller in the tree is the GUI
    button -- and its header renounces THIS gate by name: "OTD
    per-tranche price gate (operator chose this tranche explicitly)".

    The claim is checked by hashing its text in the shipping source
    against its text in the provably pre-change twin, so there is no
    magic constant to go stale.

    IF THIS FAILS: a third executor moved in a change whose blast radius
    was measured on the assumption that it did not.
    """
    now = _method_text(SOURCE, "manual_fire_tranche")
    was = _method_text(_stripped_source(), "manual_fire_tranche")
    assert hashlib.sha256(now).hexdigest() == hashlib.sha256(was).hexdigest()
    # The ruling itself sits in the bypass list immediately ABOVE the
    # def, not inside the method, so it is looked for in the file. The
    # gate block quotes it too, which is why the line is matched whole
    # rather than by the phrase.
    ruling = "    #   - OTD per-tranche price gate (operator chose this"
    assert SOURCE.count(ruling) == 1 and (_stripped_source().count(ruling) == 1), (
        "the operator's recorded ruling has gone from the file, and this "
        "change relies on that path being deliberately exempt"
    )


def test_the_shared_executor_changed_and_nothing_else_did():
    """Exactly one method's text moved, and the gate is inside it.

    The byte-hash test above already proves the whole file is unchanged
    outside the block. This says WHERE the block is: inside the shared
    executor's FOLD branch and in no neighbouring method.

    IF THIS FAILS: the change is wider than the unit claims, and the
    blast radius was measured for a smaller change than shipped.
    """
    old = _stripped_source()
    moved = [
        name
        for name in (
            "_execute_manual_rebalance",
            "manual_fire_tranche",
            "tick",
            "_apply_fold_target_growth",
            "_preview_fold_growth",
            "_settled_fill",
            "_execute_buy",
            "_execute_sell",
            "reset_swos_cycle",
        )
        if _method_text(SOURCE, name) != _method_text(old, name)
    ]
    assert moved == ["_execute_manual_rebalance"], moved
    executor = _method_text(SOURCE, "_execute_manual_rebalance")
    assert _GATE_FIRST_LINE.encode("utf-8") in executor


# ── the SCRUM side of the same method sells, and still does ──────────


@pytest.mark.parametrize("intent", EVERY_INTENT)
def test_the_scrum_side_is_untouched(intent):
    """THE GATE MUST NOT REACH THE SELL SIDE.

    IF THIS FAILS: the refusal leaked out of the FOLD branch and is now
    gating live scrums -- the opposite of the intent, on real money, in
    the direction that stops the bot taking profit.
    """
    scenario = dict(
        tranches=_ladder(1.00, 0.99), holdings=1000.0, target=100.0, price=1.0
    )
    live = _observable(_fire(_bot(ScrummingBot, **scenario), 1.0, intent))
    old = _observable(_fire(_bot(_pregate(), **scenario), 1.0, intent))
    assert old["placed"] is not None and (
        old["placed"]["side"].value == "sell"
    ), "this row is not a scrum"
    for key, value in old.items():
        assert live[key] == value, f"{intent}: {key} changed on the sell side"


# ── the value domain, because floats are in the accepted set ─────────


@pytest.mark.parametrize("intent", AUTONOMOUS)
def test_a_nan_price_refuses(intent):
    """FAIL CLOSED ON NaN.

    ``if not price or price <= 0`` admits it -- ``not nan`` is False and
    ``nan <= 0`` is False -- so a NaN price reaches the fold branch:
    ``abs(nan) < dust`` is False and ``nan > 0`` is False, which is the
    else. Under the gate every comparison against it is False, the
    eligible set is empty and the fire is refused.

    IF THIS FAILS: a NaN price reaches a market order on a path where
    every other gate is already bypassed.
    """
    bot = _fire(
        _bot(
            ScrummingBot, tranches=_ladder(1.00), holdings=50.0, target=100.0, price=1.0
        ),
        float("nan"),
        intent,
    )
    assert bot.seen["placed"] is None
    assert len(_refusal(bot)) == 1


@pytest.mark.parametrize("intent", AUTONOMOUS)
def test_control_a_nan_price_bought_before_this_change(intent):
    """CONTROL. The old code placed an order on a NaN price.

    IF THIS FAILS: something already stopped NaN and the refusal above
    is not this change's doing.
    """
    bot = _fire(
        _bot(
            _pregate(), tranches=_ladder(1.00), holdings=50.0, target=100.0, price=1.0
        ),
        float("nan"),
        intent,
    )
    assert bot.seen["placed"] is not None, "the pre-change code refused a NaN price too"


@pytest.mark.parametrize("intent", EVERY_INTENT)
def test_an_infinite_price_goes_to_the_sell_side_exactly_as_before(intent):
    """ATTRIBUTION, and a defect this unit found and did NOT fix.

    ``+inf`` also passes the validity check, but it does not reach the
    fold: ``holdings * inf`` is ``inf``, so ``delta_usd`` is ``inf``,
    ``delta_usd > 0`` is True and the method takes the SCRUM branch. It
    then sells ``inf / inf`` = NaN units, and ``nan <= 0`` is False so
    nothing stops it.

    That is a real hole on the live money path. It is on the SELL side,
    it belongs to the validity check rather than to the fold distance,
    and fixing it here would be a second change riding along. It is
    named in the unit's report instead.

    IF THIS FAILS: the routing of an infinite price changed under this
    unit, which measured its blast radius assuming it did not.
    """
    scenario = dict(tranches=_ladder(1.00), holdings=50.0, target=100.0, price=1.0)
    live = _observable(_fire(_bot(ScrummingBot, **scenario), float("inf"), intent))
    old = _observable(_fire(_bot(_pregate(), **scenario), float("inf"), intent))
    assert old["placed"] is not None
    assert old["placed"]["side"].value == "sell", (
        "an infinite price no longer reaches the sell side, so the "
        "defect recorded here has changed shape"
    )
    assert math.isnan(old["placed"]["amount"])
    for key, value in old.items():
        assert repr(live[key]) == repr(value), f"{intent}: {key} changed"


@pytest.mark.parametrize("intent", AUTONOMOUS)
@pytest.mark.parametrize("price", [float("-inf"), 0.0, -0.0, -1.0])
def test_a_price_the_older_check_already_rejects_is_still_rejected(intent, price):
    """ATTRIBUTION, not a new claim.

    These four never reach the gate: the validity check at the top of
    the method returns first. Pinned so a later reader does not credit
    the refusal to this change and then remove the older check.

    IF THIS FAILS: the older validity check has gone, and the gate is
    now the only thing standing between a nonsense price and an order.
    """
    bot = _fire(
        _bot(
            ScrummingBot, tranches=_ladder(1.00), holdings=50.0, target=100.0, price=1.0
        ),
        price,
        intent,
    )
    assert bot.seen["placed"] is None
    assert _refusal(bot) == [], (
        "this price reached the new gate; it used to be rejected before "
        "the method got that far"
    )
    assert any("no valid price" in m for m in bot._bus.messages)


BAD_CONFIG = [
    ("a non-numeric interval", dict(interval="abc")),
    ("a non-numeric fee", dict(fee="wide")),
    ("an interval that is not a number at all", dict(interval=object())),
    ("a list where a fee should be", dict(fee=[1, 2])),
]


@pytest.mark.parametrize("intent", AUTONOMOUS)
@pytest.mark.parametrize(
    "label, override", BAD_CONFIG, ids=[row[0] for row in BAD_CONFIG]
)
def test_an_unreadable_distance_refuses(intent, label, override):
    """FAIL CLOSED ON A BAD CONFIG -- a deliberate difference from tick.

    The tick path swallows this and falls back to an OTD of 0.0, which
    is a factor of 1.0 and no distance gate at all. ``otd_math``'s own
    docstring names that fallback as a hazard. Inheriting it here would
    mean the bots most likely to be misconfigured are the ones that
    silently keep the defect.

    IF THIS FAILS: an unparseable config restores the defect on exactly
    the path where every other gate is already off.
    """
    bot = _fire(
        _bot(
            ScrummingBot,
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            **override,
        ),
        0.50,
        intent,
    )
    assert bot.seen["placed"] is None, f"{label} traded"
    assert any(
        "opposing distance unreadable" in m for m in bot._bus.messages
    ), bot._bus.messages


@pytest.mark.parametrize(
    "label, override", BAD_CONFIG, ids=[row[0] for row in BAD_CONFIG]
)
def test_control_a_bad_config_traded_before_this_change(label, override):
    """CONTROL. The old code bought straight through a broken config.

    IF THIS FAILS: something else already refused these, and the
    fail-closed claim above is not this change's doing.
    """
    bot = _fire(
        _bot(
            _pregate(),
            tranches=_ladder(1.00),
            holdings=50.0,
            target=100.0,
            price=0.50,
            **override,
        ),
        0.50,
        "wire_stack",
    )
    assert (
        bot.seen["placed"] is not None
    ), f"{label}: the pre-change code refused this too"


REF_EDGE = [
    ("ref of zero", 0.0),
    ("ref missing entirely", None),
    ("a negative ref", -1.0),
]


@pytest.mark.parametrize("intent", AUTONOMOUS)
@pytest.mark.parametrize("label, ref", REF_EDGE, ids=[row[0] for row in REF_EDGE])
def test_a_ladder_of_only_malformed_refs_refuses(intent, label, ref):
    """A ref that cannot be traded against is not a licence to trade.

    IF THIS FAILS: a malformed ladder is treated as an eligible one, and
    the bot buys with nothing to measure the price against.
    """
    tranche = {"usd": 1.0, "units": 5.0}
    if ref is not None:
        tranche["ref"] = ref
    bot = _fire(
        _bot(ScrummingBot, tranches=[tranche], holdings=50.0, target=100.0, price=0.50),
        0.50,
        intent,
    )
    assert bot.seen["placed"] is None, f"{label} traded"
    assert len(_refusal(bot)) == 1


def test_the_threshold_is_the_module_and_not_a_local_copy():
    """The boundary is exactly ``otd_math``'s, on both sides of it.

    IF THIS FAILS: this site has grown its own arithmetic, which is the
    drift ``otd_math`` was extracted to end.
    """
    ref, interval, fee = 1.0, 1.0, 0.6
    edge = ref * fold_rebuy_factor(interval, fee)
    assert not math.isnan(edge)

    at = _fire(
        _bot(
            ScrummingBot, tranches=_ladder(ref), holdings=50.0, target=100.0, price=edge
        ),
        edge,
        "wire_stack",
    )
    assert (
        at.seen["placed"] is not None
    ), "a price exactly ON the threshold was refused; the rule is <="

    above = math.nextafter(edge, math.inf)
    over = _fire(
        _bot(
            ScrummingBot,
            tranches=_ladder(ref),
            holdings=50.0,
            target=100.0,
            price=above,
        ),
        above,
        "wire_stack",
    )
    assert (
        over.seen["placed"] is None
    ), "one float above the threshold was still admitted"


@pytest.mark.parametrize(
    "interval, fee",
    [
        (1.0, 0.6),
        (2.0, 0.0),
        (0.0, 0.6),
        (15.0, 0.6),
        (60.0, 0.6),
    ],
)
def test_the_gate_agrees_with_the_tick_path_on_every_config(interval, fee):
    """ONE RULE, TWO SITES.

    The boundary this gate enforces must be the boundary the autonomous
    tick fold-back enforces for the same config -- including the awkward
    rows. A configured fee of 0.0 is falsy and both sites replace it
    with 0.6. An interval of 60 is clamped, by ``otd_math``, on the SUM.

    IF THIS FAILS: this site has grown a rule of its own, which is the
    drift ``otd_math`` was extracted to end, and the two fold paths will
    disagree about the same tranche on the same tick.
    """
    ref = 1.0
    edge = ref * _tick_factor(interval, fee)
    at = _fire(
        _bot(
            ScrummingBot,
            tranches=_ladder(ref),
            holdings=1.0,
            target=100.0,
            price=edge,
            interval=interval,
            fee=fee,
        ),
        edge,
        "max_cartridge",
    )
    assert at.seen["placed"] is not None, (
        f"interval={interval} fee={fee}: the tick path's own boundary "
        f"price ${edge:.8f} was refused here"
    )

    above = math.nextafter(edge, math.inf)
    over = _fire(
        _bot(
            ScrummingBot,
            tranches=_ladder(ref),
            holdings=1.0,
            target=100.0,
            price=above,
            interval=interval,
            fee=fee,
        ),
        above,
        "max_cartridge",
    )
    assert over.seen["placed"] is None, (
        f"interval={interval} fee={fee}: one float past the tick path's "
        f"boundary was admitted here"
    )
