# ATA-SPM phases four to six

Phase four writes one post per push target from the evidence phase three
produced. Phase five sends a post and records what happened to it. Phase six is
the Ready to Send bucket the operator approves from, with a thumbnail per post,
Approve and Decline under the larger chart view, Post Selected, Post All and
Send Bucket Full Auto. The ATA-SPM settings page carries a credential per push
target, the ceiling on posts per hour, the wording each indicator message uses,
and how many indicators a post draws.

**Nothing was sent to a real platform.** Phase five sent to
`ata_spm_push.RecordedDestination`, which keeps every artefact in memory and
answers the name `recorded-destination`. No network call was made, no real
credential exists in the tree, and the only credentials stored were the strings
`key-<target>` and `signature-<target>` typed into a `CredentialVault` built
inside the run. That vault holds them in memory and was never written to disk.

Renders:

```
docs/audits/2026-09-06_units/ata_bucket_qt.png
docs/audits/2026-09-06_units/ata_bucket_react.png
docs/audits/2026-09-06_units/ata_bucket_electron.png
docs/audits/2026-09-06_units/ata_bucket_preview_react.png
```

The runtime tree was not touched. `~/.acervator/settings.json` before and after:

```
sha256_before f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
sha256_after  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## Edits

`src/trading/ata_spm_push.py` — new, and the whole push half. `FIXED_HEADER`
carries the operator's disclaimer. `PushTarget` is one target and the evidence
sections its body carries in order, and `PUSH_TARGETS` holds the four:
TradingView takes the call, the chart, the bands and the indicator messages; X
takes the call and the messages; Instagram takes the call, the bands and the
messages; LinkedIn takes the call, the chart and the messages. Adding a fifth
target is adding a row there, and `format_post`, `distribute` and `ReadyToSend`
read the row rather than the name. `FormattedPost` holds one call written for
one target; its `body`, `caption` and `thread_root` are properties that each
compose `FIXED_HEADER` with the lines, so no caller can build an artefact
without it. `format_run` runs phase four over one `ata_spm.AtaSpmRun`.
`DeliveryRecord` is what phase five did with one post, and `line` is the one
sentence the zone reads back. `SendRate` counts the posts sent inside the last
hour against the ceiling. `deliver_one` refuses in four ways and records each:
no credential held, no sender wired, the ceiling reached, and a sender that
raised. `distribute` is phase five over a list. `BucketPost` is one post and its
approval state; `ReadyToSend` is the bucket, with `approve`, `decline`,
`post_selected`, `post_all`, `release` and `toggle_full_auto`. `AtaSpmSettings`
carries only what a phase reads, and `credential_rows` publishes a held flag and
a word, never a token. `PushBoard` holds the bucket, the settings and which page
the zone shows, so all three hosts share one object. `RecordedDestination` is a
sender that keeps every artefact and reaches no platform.

`src/trading/ata_spm.py` — `indicator_message`, `pull`, `run` and
`SectorBoard.scan_now` take the `message_format` the settings page sets, and
`MESSAGE_FORMAT` is what an unset page leaves. `AtaSpmRun.report` no longer
publishes a Ready to Send count of its own; the host holding a bucket writes the
real count in beside `phase`.

`src/gui/main_tabs/market_inspector_surface.py` — `strip_marker_pct` clamps the
`bb_position` the Bollinger voter published to the strip, `strip_left_px` puts
the marker inside it, and `post_strip` answers the whole strip at its thumbnail
or its preview size. `vote_color` and `vote_fill_color` read the existing signal
palette. `bucket_entry`, `bucket_entries`, `bucket_detail_rows` and
`bucket_method_text` turn one waiting post into the entry the zone steps
through, and `bucket_zone_text` gives the zone its line. `zone_entry` and
`zone_view` gained `thumbnail`, `preview` and `actions`, which the other five
zones leave empty. `bucket_skin` and `settings_page` publish every value the
four buttons and the settings page are drawn from. `MarketInspectorScreenModel`
gained `push`, `bucket_at`, `push_action`, `set_credential_text`,
`save_credentials` and `set_setting`, and its bridge handler reads
`push_action`, `credential_text`, `save_credentials` and `set_setting`.

`src/gui/market_inspector.py` — `_BandStrip` draws one strip from a lead and a
marker in a row layout. `row_height` and `layout_height` answer the height a
zone entry needs at its width, which is what `_ZoneEntry.hold_height` sets as
its minimum. `ProposalStepper` gained the thumbnail, the preview, the strip text
and the action row, and `actionPressed` carries the part name.
`_build_bucket_row` builds Post Selected, Post All and Send Bucket Full Auto;
`_build_settings_page` builds the credential rows, Save credentials and the
three settings. `_on_push_action`, `_on_settings_pressed`,
`_on_save_credentials` and `_on_setting_changed` drive the board. `_ata_report`
writes the bucket count into the run report. The file's own copies of
`ATA_SPM_UNWIRED_TEXT`, `ATA_SPM_NO_RUN_TEXT`, `ATA_SPM_PHASE_KEY` and
`ATA_SPM_READY_KEY` are gone; it imports the surface's instead.

`src/gui/react_market_inspector_tab.py` — the page's presses reach the model:
every part in `surface.PUSH_PARTS`, the two credential fields, Save credentials
and one setting field. The tab's push board and the screen model's push board
are one object.

`src/gui/web/market_inspector.js` — `BandStrip` is the React half of the same
strip, `EntryAction` is Approve or Decline, `PushButton` is one of the phase
five and six buttons, `BucketRow` is the control row, and `CredentialRow`,
`SettingRow`, `SaveCredentialsButton` and `SettingsPage` are the settings page.
`ZoneStepper` draws the thumbnail, the preview and the actions when the view
carries them. `acervatorMarketInspectorAction` sends the new presses to the
bridge as `push_action`, `credential_text`, `save_credentials` and
`set_setting`.

`src/gui/web/market_inspector.css` — the new buttons and the two field kinds
take the colour rules the existing controls take, and the strip takes a corner.

`docs/manual/08-tabs.md` — the Market Inspector page gains phases four, five and
six, the four push targets, the header on every artefact, the delivery record,
the bucket and its four buttons, and the settings page. No sentence was deleted
or reworded.

## Errors detected

### 1 The delivery record could not be printed

The first run of phase five under the strictest interpreter mode died writing
its own record:

```
PYTHONWARNINGS=error python -X dev -X faulthandler
=== phase 5 Distribute: post_all, 1 approved, no credential ===
   Traceback (most recent call last):
  File "encodings\cp1252.py", line 19, in encode
    return codecs.charmap_encode(input,self.errors,encoding_table)[0]
UnicodeEncodeError: 'charmap' codec can't encode character '→' in position 21
```

`DELIVERY_SENT_FORMAT` and `DELIVERY_FAILED_FORMAT` used a right arrow, which
the Windows console encoding has no character for. The rest of the file uses the
middle dot the console does carry. Corrected by writing both records with that
dot and the words `sent to`. The same run afterwards:

```
=== phase 5 Distribute: post_all, ceiling 2 ===
   TradingView · ETH 1d · sent to recorded-destination
```

### 2 The expanded post ran two lines into one

Read off the running Qt widgets, the first expanded line carried the whole image
caption, header and headline together, in a single label:

```
detail  This is not investment advice. It is a demonstration of Ekthelius's
        proprietary TA engine housed in the Acervator governance execution
        platform.
        ETH 1d · bull
```

`bucket_detail_rows` put `FormattedPost.caption`, which is two lines, into one
row. Corrected by writing one row per line of the post body, which starts with
the header. The same entry afterwards:

```
detail  This is not investment advice. It is a demonstration of Ekthelius's ...
detail  ETH on 1d: bullish reversal called.
detail  Bollinger Bands: band position -0.0699. Votes bullish at 100% confidence.
```

### 3 The entry drew its lines on top of each other

Read off the real Qt widgets, the entry was less than half the height its
content needed, and the preview, the buttons and the lines overlapped:

```
entry_box          [720, 93, 651, 257]
entry_min_height   257
entry_hint_height  514
preview_box        [733, 138, 320, 96]
preview_label_box  [733, 188, 625, 15]
action_boxes       [[733, 207, 81, 26], [818, 207, 81, 26]]
detail_boxes       [[733, 275, 625, 3], [733, 282, 625, 2]]
```

`ProposalStepper.show_view` set the entry's minimum height from
`sizeHint().height()`. A wrapping label's own hint follows the height it was
already given, so a squeezed label reported a squeezed hint and the entry stayed
squeezed. Corrected by summing what each row needs at the entry's width, asking
a wrapping label through `heightForWidth`, and recursing into the nested row and
column layouts. The same entry afterwards:

```
entry_box          [720, 93, 651, 366]
preview_box        [733, 176, 320, 48]
preview_label_box  [733, 228, 625, 15]
action_boxes       [[733, 247, 81, 26], [818, 247, 81, 26]]
detail_boxes       [[733, 277, 625, 30], [733, 311, 625, 15]]
```

### 4 Approve and Decline stretched across the zone

The two buttons filled the whole entry width, because their row ended with no
stretch. Corrected by ending the row with one and inserting each button before
it. Measured afterwards: `[733, 280, 95, 36]` and `[832, 280, 88, 36]`.

### 5 The zone entry spread its lines down the whole zone

An entry shorter than its zone had its lines spaced evenly down it, because the
column layout gave the slack to the labels. Corrected by ending the entry body
with a stretch. This is the entry every zone draws, so the ATA-SPM and Opposing
Trades zones read the same way now.

### 6 The control rows were squeezed to their smallest height

With the entry asking for a tall minimum, the row above it lost height: every
control in both panes measured 26 px tall instead of 36, and the zone content
started 23 px higher than it does. Corrected by giving the entry's scroll area
an ignored vertical policy, so the height the entry asks for stays inside the
scroll area. The settings page took the same treatment, and its own rows had
been squeezed to 17 px.

### 7 Pressing Approve in the page also closed the entry

Read off the page after pressing Approve and then Decline:

```
after_approve  {"state": "approved", "page": "X · approved"}
after_decline  {"state": "approved", "page": "X · approved"}
```

Decline did nothing. The entry toggles on its own click and the two buttons sit
inside it, so in the page the press reached both and the second press closed the
expansion. The Qt buttons consume the press, so the Qt host never showed it.
Corrected by stopping the press at the button. The same two presses afterwards:

```
after_approve  {"state": "approved", "page": "X · approved"}
after_decline  {"state": "declined", "page": "X · declined"}
```

### 8 The credential row named its target twice

The settings row carries the target's name as its label and then read:

```
TradingView: held
```

`credential_rows` wrapped the state in a format that repeated the name.
Corrected by publishing the state word alone. The row afterwards reads
`TradingView` on the left and `held` on the right.

### 9 The credential field answered no press

The GUI archetype refused the page:

```
python -m dev_harness.harness.gui_archetype src/gui/web/market_inspector.js
passed False {'gui-js': 1} {'high': 1}
gui-js line 1946 <input> carries none of ['disabled', 'onChange', 'onClick',
'onInput', 'onKeyDown', 'readOnly']; the control draws and answers no
interaction, so it is inert.
```

The field was uncontrolled so the token would stay out of the payload, which
left it with no handler. Corrected by having the field report what is typed to
`AtaSpmSettings.set_credential_text`, which holds it and publishes none of it.
Save credentials then reads what the model holds. Both hosts now do the same
thing, and the archetype passes.

### 10 A local name changed a verdict in another function

The TA archetype refused the surface after a new helper was added:

```
python -m dev_harness.harness.ta_archetype src/gui/main_tabs/market_inspector_surface.py
ta-quant TA004 line 1766 high
units mismatch: 'self.board.sector_at(at)' (dimensionless) compared against
'None' (absolute).
```

The line named is `toggle_timeframe`, which this unit did not change. The new
`strip_left_px` had a local called `at` holding a pixel offset, and the file's
other `at` is a zone index. Corrected by naming the pixel offset `left`.

### 11 The Qt geometry was read without the theme

The first comparison read 24 of 58 numbers matched, and the Qt controls measured
26 px tall against the 37 px the report for phases one to three recorded. The
application style sheet had not been applied before the tab was built, so every
Qt padding was missing. The number was a fact about how the tab was built, not
about the screen. Corrected by applying
`ThemeManager().get_qss("cyberpunk_dark")` first, which restores the sector
field to `[16, 56, 130, 37]`, the figure phases one to three recorded.

### 12 The page answered an empty string for every read

Every read of the React page came back as the empty string:

```
after_scan {"raw": ""}
```

Two causes, both in how the page was asked. `window.acervatorMarketInspector`
exports `faults`, not `report`. And a plain object handed back from
`runJavaScript` converts to an empty string on this build, while text does not.
Corrected by calling `faults()` and reading the page back as JSON text.

### The debugger, and what it printed

All three phases run clean under the strictest interpreter mode. Every run set
`HOME` and `USERPROFILE` to a throwaway directory:

```
PYTHONWARNINGS=error python -X dev -X faulthandler   engine, phases 4 to 6
EXIT=0

PYTHONWARNINGS=error python -X dev -X faulthandler   ACERVATOR_VARIANT=qt
EXIT=0

PYTHONWARNINGS=error python -X dev -X faulthandler   ACERVATOR_VARIANT=react
EXIT=0
```

The Electron shell was started from its own executable with the backend
redirected to the bridge, its own user-data directory, and the debugging port
open. `ELECTRON_RUN_AS_NODE` was removed from the child's environment. The shell
refused once first, and reported it itself:

```
shell_exit 3221225477
```

That is an access violation. Electron crashed with `USERPROFILE` pointed at the
throwaway directory. Corrected by leaving the shell's own profile alone and
setting the throwaway home inside the bridge process, which is what writes. The
shell then started:

```
DevTools listening on ws://127.0.0.1:9334/devtools/browser/...
```

## Resolution

### Phase four, driven and read back

Two reversal calls and four targets produced eight posts. Each target's body
carries its own sections, and every one opens with the fixed header:

```
-- TradingView ETH 1d bull
   This is not investment advice. It is a demonstration of Ekthelius's
   proprietary TA engine housed in the Acervator governance execution platform.
   ETH on 1d: bullish reversal called.
   Chart: 200 candles, last close 219.825
   Bands: lower 219.982 · middle 221.107 · upper 222.232
   Bollinger Bands: band position -0.0699. Votes bullish at 100% confidence.
   Stochastic RSI: %K at 0.00. Votes bullish at 50% confidence.
   Ichimoku Cloud: price above the cloud. Votes bullish at 12% confidence.
   ADX: ADX 85.16. Votes bullish at 100% confidence.
   Supertrend: +2.973% from the Supertrend line. Votes bullish at 35% confidence.
   RSI: RSI 27.04. Votes bullish at 46% confidence.

-- X ETH 1d bull
   This is not investment advice. It is a demonstration of Ekthelius's
   proprietary TA engine housed in the Acervator governance execution platform.
   ETH on 1d: bullish reversal called.
   Bollinger Bands: band position -0.0699. Votes bullish at 100% confidence.
   Stochastic RSI: %K at 0.00. Votes bullish at 50% confidence.
   Ichimoku Cloud: price above the cloud. Votes bullish at 12% confidence.
   ADX: ADX 85.16. Votes bullish at 100% confidence.
   Supertrend: +2.973% from the Supertrend line. Votes bullish at 35% confidence.
   RSI: RSI 27.04. Votes bullish at 46% confidence.

-- Instagram ETH 1d bull
   the call, the bands, then the same six messages

-- LinkedIn ETH 1d bull
   the call, the chart, then the same six messages
```

Every artefact of every post was read for the header:

```
every artefact carries the header: True
```

The indicator cap is a setting phase four reads. The same run at two settings:

```
capped body lines   5   (max supporting indicators 2)
uncapped body lines 9   (max supporting indicators 0)
```

### Phase five, and exactly what it sent and where

Every send in this unit went to `RecordedDestination("recorded-destination")`,
an in-memory object. No platform was reached. The refusals came first, each with
its own record:

```
=== post_all, 1 approved, no credential ===
   TradingView · ETH 1d · not sent · No credential held for TradingView.
=== post_all, credentials held, no sender ===
   TradingView · ETH 1d · not sent · No sender wired for TradingView.
=== post_all, sender wired, ceiling unset ===
   TradingView · ETH 1d · not sent · Max posts per hour is unset. Nothing leaves.
=== post_all, ceiling 2 ===
   TradingView · ETH 1d · sent to recorded-destination
```

What the destination holds after that send, which is everything that left:

```
artefacts recorded 1
 sent TradingView ETH keys ['body', 'caption', 'thread_root']
```

The ceiling refuses the post past it, and the hour rolls:

```
=== 4 approved, ceiling 1 ===
   TradingView · ETH 1d · sent to recorded-destination
   X · ETH 1d · not sent · 1 post(s) sent this hour, ceiling 1.
   Instagram · ETH 1d · not sent · 1 post(s) sent this hour, ceiling 1.
   LinkedIn · ETH 1d · not sent · 1 post(s) sent this hour, ceiling 1.
=== the same board one hour later ===
   TradingView · ETH 1d · sent to recorded-destination
   X · ETH 1d · not sent · 1 post(s) sent this hour, ceiling 1.
```

A declined post is never sent:

```
state at 1 declined
   X · ETH 1d · not sent · Declined. Not sent.
```

The same run with no candle source answers no vote, so the bucket holds nothing
and the count of zero is a fact about the market:

```
scans 1 calls 0 bucket 0
summary No post formatted. Scan a sector first.
```

### Phase six, driven in all three hosts

Qt, read off the real widgets after pressing Scan Now, the next arrow and the
entry:

```
bucket summary  8 post(s) · 0 approved · 0 declined · 8 waiting
position        2 of 8
headline        ETH 1d · bull
meta            X · waiting
method          Phase 6 Ready to Send · X · 200 candles, last close 219.825 · band position -0.0699
strip text      lower 219.982 · middle 221.107 · upper 222.232 · last close 219.825 · band position -0.0699
actions         ['Approve', 'Decline']
detail          8 lines, the first the fixed header
after Approve   state approved · meta 'X · approved'
Post Selected   X · ETH 1d · not sent · No credential held for X.
after Decline   state declined · meta 'X · declined'
Post Selected   X · ETH 1d · not sent · Declined. Not sent.
credentials     {'TradingView': 'held', 'X': 'held', 'Instagram': 'held', 'LinkedIn': 'held'}
fields cleared  ['', '', '', '', '', '', '', '']
settings        max_posts_per_hour 3 · max_supporting_indicators 2
Post All        Instagram · ETH 1d · sent to recorded-destination
                LinkedIn · ETH 1d · sent to recorded-destination
Full Auto on    Instagram · ETH 1d · sent to recorded-destination
                LinkedIn · ETH 1d · not sent · 3 post(s) sent this hour, ceiling 3.
                TradingView · BTC 1wk · not sent · 3 post(s) sent this hour, ceiling 3.
Full Auto off   no record
```

React, read off the page's own elements, the same eight posts and the same
answers:

```
bucket summary  8 post(s) · 0 approved · 0 declined · 8 waiting
position        2 of 8
headline        ETH 1d · bull
meta            X · waiting
method          Phase 6 Ready to Send · X · 200 candles, last close 219.825 · band position -0.0699
strip text      lower 219.982 · middle 221.107 · upper 222.232 · last close 219.825 · band position -0.0699
actions         ['Approve', 'Decline']
detail          8 lines
after Approve   state approved · page 'X · approved'
Post Selected   X · ETH 1d · not sent · No credential held for X.
after Decline   state declined · page 'X · declined'
Post Selected   X · ETH 1d · not sent · Declined. Not sent.
credentials     ['TradingView: held', 'X: held', 'Instagram: held', 'LinkedIn: held']
settings        max_posts_per_hour 3 · max_supporting_indicators 2
Post All        Instagram · ETH 1d · sent to recorded-destination
                LinkedIn · ETH 1d · sent to recorded-destination
Full Auto on    Instagram · ETH 1d · sent to recorded-destination
                LinkedIn · ETH 1d · not sent · 3 post(s) sent this hour, ceiling 3.
                TradingView · BTC 1wk · not sent · 3 post(s) sent this hour, ceiling 3.
Full Auto off   no record
page faults     []
```

The Electron shell, with the backend redirected to the bridge and the tapes on
the analyzer the bridge screen reads:

```
tabs            ["trading_tab","market_inspector","bot_visualizer","trade_charts_tab",
                 "history_tab","simulator_tab","console_tab","paper_trader_tab",
                 "system_status_tab","proof_of_accumulation_tab"]
selected        market_inspector
zones           ["ata_spm","opposing_trades","arbitrage","ready_to_send",
                 "topologies","phantom_htf"]
position        2 of 8
headline        ETH 1d · bull
meta            X · waiting
method          Phase 6 Ready to Send · X · 200 candles, last close 219.825 · band position -0.0699
strip text      lower 219.982 · middle 221.107 · upper 222.232 · last close 219.825 · band position -0.0699
actions         ["Approve", "Decline"]
detail          8 lines
after Approve   X · approved
after Decline   X · declined
settings page   drawn
credentials     ["TradingView: Credential vault not wired.", "X: ...",
                 "Instagram: ...", "LinkedIn: ..."]
settings        [["max_posts_per_hour","0"],["max_supporting_indicators","0"],
                 ["message_format","{label}: {reading}. Votes {direction} at {confidence}% confidence."]]
page faults     []
```

**What the shell can and cannot show, and why.** Phases four and six run there
in full: the eight posts, the stepper, the thumbnail, the preview, Approve,
Decline and the settings page all work against the real bridge screen. No
credential can be stored there, because the bridge process has no vault wired,
so every target reports `Credential vault not wired.` and phase five refuses
each post by name. That is the honest state of the shell, and it is readable
back rather than silent.

### The push targets, and what each one takes

Each row is one target and the sections its body carries, in its own order. A
fifth target is a fifth row; `format_post`, `distribute` and `ReadyToSend` read
the row, not the name.

```
TradingView   call · chart · bands · indicators
X             call · indicators
Instagram     call · bands · indicators
LinkedIn      call · chart · indicators
```

The content under all four is the same evidence phase three produced, and every
indicator sentence is the one `ata_spm.indicator_message` wrote. No indicator
maths is computed in this unit, and no value produced by one indicator is read
by another. The strip's marker sits at the `bb_position` the Bollinger Bands
voter published, clamped to the strip.

### Dimensions

Read off the Qt widgets and off the page's own elements, both sized 1400 by 860,
with the theme applied to each. A row matches when every number in it is within
1.5 px.

```
MATCH   tab                  qt=[1400, 860]        react=[1400, 860]
DIFFER  Post Selected        qt=[720, 56, 124, 36] react=[719.3, 55.8, 116.6, 34.4]
DIFFER  Post All             qt=[850, 56, 89, 36]  react=[841.9, 55.8, 84.5, 34.4]
DIFFER  Send Bucket Full Auto qt=[1207, 56, 177, 36] react=[1218.4, 55.8, 165.8, 34.4]
DIFFER  stepper              qt=[720, 98, 664, 176] react=[719.3, 96.2, 664.9, 178.7]
DIFFER  back button          qt=[720, 98, 26, 24]  react=[719.3, 96.2, 26, 24]
DIFFER  thumbnail            qt=[733, 137, 120, 30] react=[732.1, 135, 120, 30]
DIFFER  thumbnail marker     qt=[734, 138, 5, 28]  react=[732.9, 135.8, 5, 28.4]
MATCH   preview              qt=[733, 209, 320, 48] react=[732.1, 207.8, 320, 48]
DIFFER  Approve              qt=[733, 280, 95, 36] react=[732.1, 279.2, 89.9, 34.4]
DIFFER  Decline              qt=[832, 280, 88, 36] react=[826, 279.2, 83.3, 34.4]
DIFFER  Settings             qt=[589, 57, 92, 36]  react=[593.2, 56.2, 87.5, 34.4]
DIFFER  Save credentials     qt=[16, 272, 655, 36] react=[15.8, 258.6, 649.7, 34.4]
DIFFER  credential field     qt=[172, 100, 96, 37] react=[171.8, 97, 96, 34.4]
DIFFER  setting field        qt=[172, 314, 180, 37] react=[171.8, 299, 180, 34.4]

rows 15 rows matched 2
numbers 58 numbers matched 30
```

**Where the remaining difference comes from, measured rather than asserted.**
Both hosts draw a button from the same padding: 8 px above and below, 20 px each
side, over a 1 px border. Qt's button is 36 px tall, which is 8 + 8 + 2 and a
text box of 18. The page's is 34.4, which is 8 + 8 + 2 and a text box of 16.4,
the line box a 12 px font at 1.4 gives. Every other number on the list follows
from that 1.6 px: the buttons are a few pixels wider or narrower for the same
words, the rows below them start 1.6 to 2 px higher in the page, and the
settings rows drift further down the more rows sit above them. Nothing on the
list is a layout value one host reads and the other does not.

Text, read off all three hosts:

```
MATCH   bucket summary        MATCH   position
MATCH   bucket total          MATCH   headline
MATCH   meta                  MATCH   method
MATCH   strip text            MATCH   actions
MATCH   detail lines          MATCH   approve state
MATCH   approve meta          MATCH   decline state
MATCH   declined record       MATCH   post selected
MATCH   post all              MATCH   full auto text
MATCH   full auto records     MATCH   full auto off
MATCH   credential state      MATCH   settings read back

text rows 20 matched 20
```

### The settings page, and which phase reads each setting

```
credentials                per push target, held in the vault, never published
max posts per hour         the ceiling SendRate obeys, unset until the operator sets it
standardised message text  the wording ata_spm.indicator_message writes
max supporting indicators  the cap format_post draws messages under
```

An unset ceiling releases nothing, so nothing can leave the machine until the
operator sets a number and a credential is held. No other setting was added.

### Two lines for the operator

The manual still carries the sentence `Phases four to eight are not built.` from
the unit before this one. It cannot be reworded here, so the passage added under
it says what is true now and names phases seven and eight as the two still not
built.

The Bot Swarm Topologies button still reads `Refresh proposals` where the item
says it reads `Refresh`. It belongs to the topologies zone, not this one.

### Size against time

```
lines produced              2213
wall clock                  6413 s
seconds per source line     2.9
```

Phases one to three measured 2.51 seconds per source line.
