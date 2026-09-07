# ATA-SPM phases seven and eight

Phase seven says what happened to a call: confirmed, failed, or still open.
Phase eight scans an asset on several timeframes, gives each one its own vote,
and says whether they agree. Both are readable back on the ATA-SPM zone, and a
settled call writes its own post into Ready to Send naming the original.

Renders:

```
docs/audits/2026-09-07_units/ata_phase7_8_qt.png
docs/audits/2026-09-07_units/ata_phase7_8_react.png
docs/audits/2026-09-07_units/ata_phase7_8_electron.png
docs/audits/2026-09-07_units/ata_phase7_followup_react.png
```

**Nothing was sent to a real platform.** No network call was made, no credential
was stored, no exchange order was placed and no test was run. The running
platform was never started, stopped or queried. Every run set `HOME` and
`USERPROFILE` to a throwaway directory. `~/.acervator/settings.json` before and
after:

```
sha256_before f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
sha256_after  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## Edits

`src/trading/ata_spm.py` — `READINGS` now names a tuple of `Signal.details`
keys per voter rather than one, and `reading_values` reads them; `READING_WORDS`
prints a boolean reading as one of two words. That is what repairs the ADX and
Kaufman messages below. Phase eight is here: `SHORTEST_TIMEFRAME_SECONDS`,
`scan_budget_s` and `timeframes_supported` answer how many timeframes one asset
is scanned on from a measured round; `RoundCost` is the measurement, taken in
`_scan_timeframe` around every asset read; `evaluate` stops a sector at the
count the measurement supports and records the rest on `SectorScan.deferred`.
`TimeframeAgreement` and `agreement_for` are the votes across the timeframes and
their verdict, and `ChartPull` carries one. `midline_after` answers the Bollinger
middle band at every candle after a call, computed by `BollingerBands` on its own
window. `_candles_for` is now `candles_for`, because phase seven reads through
it.

`src/trading/ata_spm_push.py` — phase seven. `expected_move`,
`confirmation_target`, `target_reached` and `continues_against` are the four
quantities the outcome turns on. `CONTINUATION_CANDLE_FLOOR` is the two-candle
definition of a failure. `FollowUpCall` is one watched call and `FollowUpOutcome`
what happened to it, with `follow_up_detail` writing the evidence for the state
it reached. `follow_up_outcome` walks the candles that closed after the call.
`FollowUpWatch` holds the watched calls, `check` answers what happened to each,
and `settled` stops a call being watched or posted twice. `format_follow_up`
writes the follow-up post, which carries `follows` naming the original.
`ReadyToSend.load_follow_ups` puts one in the bucket per settled outcome per
target. `AtaSpmSettings` gains `confirmation_share_pct`. `PushBoard.after_scan`
is phase seven around one scan. `_call_lines` writes the phase eight line into
every post.

`src/gui/main_tabs/market_inspector_surface.py` — `phase_seven_rows` and
`phase_eight_rows` write the two readbacks, and `sector_entry` takes the
outcomes. `bucket_method_text` names the original when a post carries `follows`.
`SETTING_ROWS` and `COUNT_SETTINGS` gain the confirmation share.
`MarketInspectorScreenModel.scan_now` calls `after_scan`, and `ata_entries`
hands the outcomes to each entry. `bucket_skin` publishes the outcome lines.

`src/gui/market_inspector.py` — `_on_scan_now` calls `after_scan` and
`_zone_entries` hands the outcomes to the ATA-SPM entries, so the Qt tab and the
screen model run the same phase seven.

`docs/manual/08-tabs.md` — the Market Inspector page gains phase seven, its two
triggers, the confirmation share, the follow-up post, phase eight's per
timeframe vote and the measured timeframe count. No sentence was deleted or
reworded.

The React tab and the page needed no change. `ZoneStepper` draws whatever detail
lines the view carries and `SettingsPage` draws whatever setting rows the model
publishes, so two new phase readbacks and one new setting reached the page with
no edit to `src/gui/web/market_inspector.js`.

## Errors detected

### 1 The ADX message named a reading that cannot carry a direction

A phase three render showed this line, and it is wrong:

```
ADX: ADX 93.54. Votes bullish at 100% confidence.
```

ADX measures how committed a move is and says nothing about which way it points.
`docs/manual/07-indicators.md`, under **ADX and DMI**, carries the published
formula, and the absolute value in it is why:

```
DX     = 100 * |+DI - -DI| / (+DI + -DI)
ADX    = Wilder(DX, 14)
```

The same page states it in words: *"The reading tells you how committed a move
is, and says nothing about which way it points."* and *"The vote itself is
decided by which directional line is on top."* Read off the running voter, the
direction comes from `di_plus` against `di_minus` and the ADX number sets only
the confidence. The message published the confidence input as though it were the
direction input.

Corrected by publishing the readings the direction is actually decided by,
beside the strength. The same run afterwards:

```
ADX: +DI 50.11 against -DI 19.20, trend strength ADX 96.04. Votes bullish at 100% confidence.
```

`+DI` above `-DI` is what makes it bullish, and the ADX figure is named as
strength. No formula, threshold or coefficient was changed; the vote, the
direction and the confidence are the same numbers the voter always produced.
The defect was in the sentence, which is the one a public post carries.

### 2 The Kaufman Efficiency Ratio message had the same defect

Reading the other eleven voters for the same shape found one more. The
Efficiency Ratio is a magnitude between zero and one, and the direction comes
from a separate quantity the same indicator computes:

```
er = |net change| / total travel
price_up = closes[-1] > closes[0]
```

The message published `er` alone:

```
Kaufman Efficiency Ratio: efficiency ratio 0.8200. Votes bullish at 57% confidence.
```

Corrected the same way. The same run afterwards, read off the real voter:

```
Kaufman Efficiency Ratio: efficiency ratio 0.2857, close above the window open. Votes neutral at 0% confidence.
```

The other ten voters publish a reading that does carry the direction: the band
position, the vortex separation, the MACD histogram, the Stochastic %K, the
Ichimoku word, the Money Flow Index, the Slingshot momentum, the Supertrend
distance, the Z-Score and RSI. Two of twelve were wrong and both are corrected.

### 3 A settled call could be watched and posted a second time

Driving two scans over the same run, the failure arm posted, and the next scan
re-detected the same call at the same bar and watched it again:

```
after the failure, watching 8 settled 0
the same run again -> outcomes 8 watching 8 follow-up posts 24
```

`FollowUpWatch.check` took a settled call off the watch list, and `watch_run`
then put it straight back, because nothing recorded that it had already been
answered. Corrected by keeping the settled keys and refusing them in
`watch_run`. The same two scans afterwards:

```
after the failure, watching 0 settled 8
the same run again -> outcomes 0 watching 0 follow-up posts 0
```

### 4 The TA archetype refused two quantities sharing one name

```
python -m dev_harness.harness.ta_archetype src/trading/ata_spm_push.py
ta-quant TA004 line 447 high
units mismatch: 'share' (dimensionless) compared against 'NO_SHARE_SET' (absolute).
```

The finding is real. `confirmation_target` held a ratio in a local called
`share`, and `follow_up_outcome` held a whole percent under the same name. Two
different quantities, one name. Corrected by naming the ratio `share_ratio`.
The archetype passes.

### 5 The page answered nothing on every read

Every read of the React page came back as None, including `1 + 1`:

```
page_ready False
loadFinished ok=True
  probe '1 + 1' -> None
  probe 'JSON.stringify({a: 1})' -> None
```

The driver waited by calling `processEvents` in a loop. That call returns at
once when the queue is empty, so a loop of it does not wait at all and the
page's answer had not arrived. Corrected in the driver by running a real event
loop with a timer. The same reads afterwards:

```
page_ready True
  probe '1 + 1' -> 2.0
  probe 'JSON.stringify({a: 1})' -> '{"a":1}'
  probe 'typeof window.acervatorMarketInspector' -> 'object'
  probe 'document.querySelectorAll(...zone-stepper...).length' -> 6.0
```

### 6 A tape that carried no reversal at all

The first engine drive returned eight votes and no call:

```
=== phases 1 to 3 and 8 ===
  sector l1 assets 2 votes 8 calls 0
```

The refusal is correct. A reversal needs the band voter and the panel to name
one direction, and the tape drove a small dip on a shallow trend, which the
other eleven voters read as a continuation. Sweeping the tape shape against the
real `VotingEngine` found the one that is a reversal, and it is a bearish one:

```
drift 2.0 dip 12.0 wick 0.002 -> bearish net -0.2919 conf 0.0273 band 0.6756 last 586
reversal tapes 1
```

That is the harder direction to drive, and it exercises the bearish branch of
both `target_reached` and `continues_against`.

### 7 The two builds disagreed on the round they measured

The last text comparison read one line apart:

```
qt    'Phase 8 Timeframes payments: 4 of 4 timeframe(s) at 0.0016s per round'
react 'Phase 8 Timeframes payments: 4 of 4 timeframe(s) at 0.0017s per round'
```

Nothing is wrong. The round cost is a measurement of the host, and two runs
cannot produce the same microsecond. Asserting it is equal would be asserting a
property of this machine. Corrected in the comparison, which now compares the
timeframe count both sides scanned and reports the two measured costs beside it.

### The debugger, and what it printed

The engine runs clean under the strictest interpreter mode and under the
debugger, and both builds run clean under the strictest mode:

```
PYTHONWARNINGS=error python -X dev -X faulthandler ata78_engine_drive.py
EXIT=0

PYTHONWARNINGS=error python -m pdb -c continue ata78_engine_drive.py
EXIT=0
The program exited via sys.exit(). Exit status: 0

PYTHONWARNINGS=error python -X dev -X faulthandler   ACERVATOR_VARIANT=qt
EXITCODE=0

PYTHONWARNINGS=error python -X dev -X faulthandler   ACERVATOR_VARIANT=react
EXITCODE=0
```

The Electron shell was started from its own executable with the backend
redirected to the bridge, its own user-data directory and the debugging port
open. `ELECTRON_RUN_AS_NODE` was removed from the child's environment and the
throwaway home was set for the bridge process. Its own log holds nothing but the
debugging address:

```
targets ['page']
DevTools listening on ws://127.0.0.1:9337/devtools/browser/...
```

## Resolution

### Phase seven, driven through both outcomes

The confirmation share was set to 60 per cent. The call is bearish, so the run
to the midline goes down and the target sits below the call's close:

```
=== phase 7: confirmed ===
  BCH 5m · bear · confirmed · close 578 reached 581.98, 60% of the run to midline 579.3, after 1 candle(s)
    candles 1 close 578 target 581.98 midline 579.3 against_run 0
```

The arithmetic, checked against the published middle band. The call closed at
586. The midline on the next candle is 579.3, so the expected move is -6.7.
Sixty per cent of that is -4.02, which puts the target at 581.98. The close of
578 is past it, so the call is confirmed.

The failure arm, on a tape whose trend carried on instead of turning:

```
=== phase 7: failed, two candles against ===
  BCH 5m · bear · failed · the trend held for 2 candles in a row, last close 598, after 2 candle(s)
    against_run 2 candles 2
```

The two-candle floor, driven one candle at a time. One is not a continuation,
two is, and a candle that goes the called way in between resets the run:

```
  1 candle(s) against -> open · 1 candle(s) since the call, last close 592, target 582.4 not reached
  2 candle(s) against -> failed · the trend held for 2 candles in a row, last close 598, after 2 candle(s)
  3 candle(s) against -> failed · the trend held for 2 candles in a row, last close 598, after 2 candle(s)
  against, with, against  -> open · 3 candle(s) since the call, last close 597, target 584.26 not reached
```

A call that is neither says so, and says why:

```
=== phase 7: still open, share unset ===
  open · 2 candle(s) since the call, last close 586. Confirmation share is unset, so nothing confirms
=== phase 7: still open, share set, target not reached ===
  open · 2 candle(s) since the call, last close 586, target 582.91 not reached
=== phase 7: no candle has closed since the call ===
  open · no candle has closed since the call · settled=False
```

An unset share confirms nothing, and a failure is still reported, because the
two-candle floor is the definition and not a setting.

### The follow-up post, and the original it names

Every settled outcome writes one post per push target, and every one opens with
the fixed header:

```
-- X follows 'BCH 5m · bear'
   This is not investment advice. It is a demonstration of Ekthelius's
   proprietary TA engine housed in the Acervator governance execution platform.
   Follow-up on BCH 5m · bear: confirmed.
   BCH on 5m: the bearish reversal confirmed.
   Evidence: close 578 reached 581.98, 60% of the run to midline 579.3, after 1 candle(s).

-- Instagram follows 'BCH 5m · bear'
   the header, the same three lines, then
   Bands: lower 556.763 · middle 578.4 · upper 600.037

-- LinkedIn follows 'BCH 5m · bear'
   the header, the same three lines, then
   Chart: 204 candles, last close 578
```

It waits in Ready to Send with Approve and Decline under it, like every other
post. The bucket after the confirming scan held 48: 24 call posts and 24
follow-ups.

### Phase eight, each timeframe and whether they agree

Every ticked timeframe casts its own vote, read off the real objects:

```
  BCH 5m bearish band 0.6756 reversal=True
  BCH 1hr bearish band 0.6756 reversal=True
  BCH 1d bearish band 0.6756 reversal=True
  BCH 1wk bearish band 0.6756 reversal=True
```

The line every post carries, when they agree and when one does not:

```
Timeframes: 5m bearish · 1hr bearish · 1d bearish · 1wk bearish. Every timeframe agrees.
Timeframes: 5m bearish · 1hr bullish · 1d bearish · 1wk bearish. Contradicted on 1hr.
```

The second was driven by giving one timeframe a different tape. A neutral vote
contradicts nothing; only a vote naming the opposite direction does.

### The measured round, and the count it supports

One full round is one asset on one timeframe: read the chart, run the twelve
voters, cast the vote. Timed on the shipped crypto sector map:

```
=== phase 8: one full round timed on this machine ===
  the shipped sector map answers 18 asset(s) for l1
  18 assets x 4 timeframes = 72 rounds
  scan, TA and vote     0.001451s per round
  the whole run, with the charts  0.001486s per round
  the whole run          0.107s for 72 chart(s)
  budget 300s -> supports 4 timeframe(s) per asset
```

**The measured round is 0.0015 seconds, and it supports four timeframes per
asset.** The budget is 300 seconds for crypto and 3600 for every other class,
which is the shortest candle each class is scanned on: an asset's rounds have to
finish before that candle closes, or the chart already moved. Four is the count
the class lists, so four is the ceiling here with a wide margin.

The count is computed, never fixed. Driven across a range of round costs:

```
  round   0.000s -> crypto 4 stocks 4
  round   0.050s -> crypto 4 stocks 4
  round  40.000s -> crypto 4 stocks 4
  round 120.000s -> crypto 2 stocks 4
  round 400.000s -> crypto 1 stocks 4
  budget crypto 300s stocks 3600s
```

A slow machine scans fewer and says which it deferred, driven with a clock that
reports 200 seconds a round:

```
  scanned ['5m'] deferred ['1h', '1d', '1w'] at 200.0s per round
```

**The measurement does not cover fetching the candles from a venue.** It covers
what Scan Now does: read the candles the Market Inspector's own Refresh already
holds, run the indicators, vote, and build the chart.

### The controls

Nothing is reported when there is nothing, and each control is read beside the
count it guards:

```
=== control: the same drive with no candle source ===
  scans 1 calls 0
  watching 0 outcomes 0 bucket 0
=== control: a flat tape publishes no midline ===
  midlines [0.0, 0.0, 0.0]
```

A flat window makes the Bollinger voter abstain, so no midline is published and
no target can be computed on that candle. The candle still counts toward the
continuation run, because the two-candle floor needs no band.

### The three hosts

Read off the real Qt widgets and off the page's own elements, both sized 1400 by
860 with the theme applied to each. A row matches when every number in it is
within 1.5 px.

```
MATCH   tab                    qt=[0, 0, 1400, 860]      react=[0, 0, 1400, 860]
MATCH   sector-field           qt=[16, 56, 72, 37]       react=[15.8, 55.8, 72, 37]
MATCH   class-box              qt=[94, 56, 92, 37]       react=[93.8, 55.8, 92, 37]
MATCH   timeframe box 0        qt=[192, 63, 64, 22]      react=[191.8, 63.3, 64, 22]
MATCH   timeframe box 1        qt=[262, 63, 64, 22]      react=[261.8, 63.3, 64, 22]
MATCH   timeframe box 2        qt=[332, 63, 64, 22]      react=[331.8, 63.3, 64, 22]
MATCH   timeframe box 3        qt=[402, 63, 64, 22]      react=[401.8, 63.3, 64, 22]
MATCH   scan-now               qt=[472, 56, 108, 36]     react=[471.8, 56.3, 108, 36]
MATCH   settings-button        qt=[585, 56, 96, 36]      react=[585.8, 56.3, 96, 36]
MATCH   post-selected          qt=[720, 56, 128, 36]     react=[719.3, 55.8, 128, 36]
MATCH   post-all               qt=[854, 56, 92, 36]      react=[853.3, 55.8, 92, 36]
MATCH   full-auto              qt=[1200, 56, 184, 36]    react=[1200.2, 55.8, 184, 36]
MATCH   stepper ata_spm        qt=[16, 99, 665, 175]     react=[15.8, 98.8, 664.9, 176.1]
MATCH   stepper ready_to_send  qt=[720, 98, 664, 176]    react=[719.3, 97.8, 664.9, 177.1]
MATCH   back ata_spm           qt=[16, 99, 26, 24]       react=[15.8, 98.8, 26, 24]
MATCH   back ready_to_send     qt=[720, 98, 26, 24]      react=[719.3, 97.8, 26, 24]
MATCH   post-thumbnail         qt=[733, 137, 120, 36]    react=[732.1, 136.6, 120, 36]
MATCH   entry-headline         qt=[857, 137, 96, 36]     react=[856.1, 136.6, 96, 36]
MATCH   post-vote              qt=[957, 137, 28, 36]     react=[956.1, 136.6, 27.3, 36]
MATCH   post-preview           qt=[733, 215, 320, 160]   react=[732.1, 215.4, 320, 160]
MATCH   thumbnail first mark   qt=[2, 33, 3, 1]          react=[3, 34, 3, 1]
MATCH   thumbnail last mark    qt=[114, 2, 4, 4]         react=[115, 3, 4, 4]
MATCH   chart mark counts      qt=[44, 84]               react=[44, 84]
MATCH   action 0               qt=[733, 398, 100, 36]    react=[732.1, 398.8, 100, 36]
MATCH   action 1               qt=[837, 398, 92, 36]     react=[836.1, 398.8, 92, 36]
MATCH   save-credentials       qt=[16, 228, 655, 36]     react=[15.8, 227.8, 655.3, 36]
MATCH   first credential key   qt=[172, 99, 96, 37]      react=[171.8, 98.8, 96, 37]
MATCH   setting field 0        qt=[172, 270, 180, 37]    react=[171.8, 269.8, 180, 37]
MATCH   setting field 1        qt=[172, 313, 180, 37]    react=[171.8, 312.8, 180, 37]
MATCH   setting field 2        qt=[172, 356, 180, 37]    react=[171.8, 355.8, 180, 37]
MATCH   setting field 3        qt=[172, 399, 180, 37]    react=[171.8, 398.8, 180, 37]

rows 31 rows matched 31
numbers 122 numbers matched 122
```

Text, read off both hosts:

```
MATCH  ata_spm position        MATCH  ata_spm headline
MATCH  ata_spm meta            MATCH  ata_spm method
MATCH  ata_spm vote            MATCH  ata_spm detail lines
MATCH  ata_spm actions         MATCH  ready_to_send position
MATCH  ready_to_send headline  MATCH  ready_to_send meta
MATCH  ready_to_send method    MATCH  ready_to_send vote
MATCH  ready_to_send detail    MATCH  ready_to_send actions
MATCH  second_scan_outcomes    MATCH  follow_up_posts
MATCH  bucket_total            MATCH  first_scan_watching
MATCH  first_scan_bucket       MATCH  targets
MATCH  share_pct               MATCH  follow_up_at
MATCH  assets                  MATCH  settings page values

text rows 24 matched 24
round cost, a fact about this host: qt 0.0016s per round react 0.0017s per round
```

**Thirty-one rows and one hundred and twenty-two numbers, all matched.** The
bucket thumbnail unit measured twenty-six rows and one hundred numbers, all
matched, and every one of those rows is in this set. Five rows are new surface:
the two zone steppers, their two back arrows, and the fourth setting field the
confirmation share adds.

The Electron shell, with the backend redirected to the bridge:

```
selected   market_inspector
faults     []
zones      ["ata_spm","opposing_trades","arbitrage","ready_to_send",
            "topologies","phantom_htf"]
sector     payments
headline   payments (crypto)
meta       2 asset(s) · 0 vote(s) · 0 reversal call(s)
detail     Phase 1 Evaluate 5m: 0 vote(s), 2 without candles
           Phase 1 Evaluate 1hr: 0 vote(s), 2 without candles
           Phase 1 Evaluate 1d: 0 vote(s), 2 without candles
           Phase 1 Evaluate 1wk: 0 vote(s), 2 without candles
           Phase 2 Identify: No chart carried a reversal vote.
           Phase 7 Follow-Up: No call is being followed up yet.
           Phase 8 Timeframes payments: 4 of 4 timeframe(s) at 0.0000s per round
settings   confirmation_share_pct is drawn on the settings page
```

**What the shell can and cannot show, and why.** Phase eight runs there for
real: all four timeframes are scanned against the real sector map, and the count
line is written from the round the shell measured. Phase seven has nothing to
follow up, because the bridge process holds no candles, so no chart carries a
reversal and no call is ever made. The round cost reads zero for the same
reason: a round that reads no candle costs nothing. The zone says exactly that
on every line rather than drawing nothing. No market data call was made.

### The gate

Fixture controls first, each exit code read on the same line as the tool and
never through a pipe:

```
coding_archetype known_good.py           exit=0    known_bad.py           exit=1
gui_archetype    known_good_widget.py    exit=0    known_bad_widget.py    exit=1
gui_archetype    known_good_screen.js    exit=0    known_bad_screen.js    exit=1
docs_archetype   known_good.md           exit=0    known_bad.md           exit=1
ta_archetype     known_good_ta001.py     exit=0    known_bad_ta001.py     exit=1
ta_archetype     known_good_ta003.py     exit=0    known_bad_ta004.py     exit=1
control failures 0
```

Every tool reported `ok` on every control. Every file this unit touched:

```
coding_archetype  src/trading/ata_spm.py                        exit=0 passed=True
ta_archetype      src/trading/ata_spm.py                        exit=0 passed=True
coding_archetype  src/trading/ata_spm_push.py                   exit=0 passed=True
ta_archetype      src/trading/ata_spm_push.py                   exit=0 passed=True
coding_archetype  src/gui/main_tabs/market_inspector_surface.py exit=0 passed=True
ta_archetype      src/gui/main_tabs/market_inspector_surface.py exit=0 passed=True
gui_archetype     src/gui/main_tabs/market_inspector_surface.py exit=0 passed=True
coding_archetype  src/gui/market_inspector.py                   exit=0 passed=True
ta_archetype      src/gui/market_inspector.py                   exit=0 passed=True
gui_archetype     src/gui/market_inspector.py                   exit=0 passed=True
docs_archetype    docs/manual/08-tabs.md                        exit=0 passed=True
subjects not passing 0
```

Every tool reported `ok`. `black --check` and `flake8` both exit 0 on the four
Python files.

### The manual

The Market Inspector page gains phase seven, its two triggers, the confirmation
share, the follow-up post, phase eight's per timeframe vote and the measured
timeframe count. The six-zone layout is not written there. Nothing was removed:

```
git diff purge-non-canon-tests -- docs/ | grep "^-" | grep -v "^---" | grep -v "^-|"
REMOVED-LINE-COUNT=0
```

### Dependencies

Nothing was installed. Electron 44.2.0, playwright, debugpy and PySide6 were
already present.

### Size against time

```
source lines produced   817
wall clock              4720 s
seconds per source line 5.8
```

Phases one to three measured 2.51 and phases four to six 2.9, both counting test
lines in the denominator; the bucket thumbnail unit measured 8.0 on source only,
which is what this figure counts.

### What the operator sees differently

He sets a confirmation share on the ATA-SPM settings page. After a scan makes a
reversal call, the next Scan Now says what happened to it: confirmed if the
market moved his way by that share of the run to the Bollinger midline, failed
if the trend carried on for two candles, and open with the reason if it is
neither. A confirmed or failed call writes its own post naming the original, and
that post waits in Ready to Send for Approve or Decline like any other. Every
post now also says whether the timeframes agreed on the call or one of them
contradicted it, and the zone says how many timeframes the machine can scan per
asset and how long a round cost it.
