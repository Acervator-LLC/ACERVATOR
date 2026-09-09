# 2026-09-09 - #407 - ATA-SMP repost protection

Two rules now hold a repost back. A ticker reaches one push target once an hour,
whatever composed the post. A follow-up is written only when the price moved the
favourable way to the confirmation target, or the trend carried on for three
candles in a row.

**Nothing was sent to a real platform.** No network call was made, no credential
was read or stored, no exchange call was made and no order was placed. The
running platform was never started, stopped or queried. No test was run. The
sender in every run below is `RecordedDestination`, which keeps the artefacts and
reaches nothing, and the vault stand-in holds no token and carries no field.
`~/.acervator/settings.json` before and after every run:

```
sha256_before 18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8
sha256_after  18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8
```

Every run was driven from a git worktree cut from `origin/current`, never from
the tree the platform launches from. The before-side runs used a second detached
worktree at the same commit, so the pre-change numbers come from the shipped file
rather than from a reversal of the edit.

## Edits

`src/trading/ata_spm_push.py` - `RepostGuard` is the per-ticker hour cap, with
`since`, `allows`, `record` and `held_text`. `ReadyToSend` holds one beside
`SendRate`, so the hour holds across the whole bucket. `distribute` takes it and
`deliver_one` consults it before the sender is called and records it after a send.
`REPOST_HELD_FORMAT` is the refusal a held post carries.
`CONTINUATION_CANDLE_FLOOR` is 3. `FOLLOW_UP_NOT_READY_FORMAT` is what a call
under that floor says.

## The caller, on a pdb stack

The guard is reached from the Ready to Send buttons, not from a helper nobody
calls. Post Selected was pressed twice on one ticker, thirty minutes apart, with
a breakpoint on the refusal line:

```
python -m pdb -c "break .../ata_spm_push.py:1126" -c continue -c where -c continue
```

```
market_inspector_surface.py(2416)push_action()   -> answered = handled()
market_inspector_surface.py(2408)<lambda>()      -> POST_SELECTED_PART: lambda: self.push.post_selected(self.bucket_at())
ata_spm_push.py(1403)post_selected()             -> return self.bucket.post_selected(...)
ata_spm_push.py(1302)post_selected()             -> return self._send([held], sender, settings, clock)
ata_spm_push.py(1344)_send()                     -> records = distribute(
ata_spm_push.py(1157)distribute()                -> deliver_one(one, sender, held, counter, guard, now)
ata_spm_push.py(1126)deliver_one()               -> record.detail = repost.held_text(now, post.symbol, post.target)
```

The button map is the caller. Post All and Send Bucket Full Auto reach the same
three frames from `_send` down.

## 1 A ticker could be posted again inside the hour

### The error - the send path counted posts, never tickers

`SendRate` counts every post sent in the hour against the operator's ceiling. No
part of the path asked which ticker a post was about, so one ticker could reach
one platform any number of times inside an hour while the ceiling still had room.

### The reproduction - Post All, three presses, one clock

One sector of one ticker, scanned on the daily timeframe. The ceiling was set to
50 and the clock was driven rather than waited on. Run against the shipped file:

```
first press:              7 sent, 0 held
second press at +30 min:  7 sent, 0 held
third press at +60 min:   7 sent, 0 held
```

Twenty-one posts about one ticker inside one hour, and nothing refused.

### The cause - no state keyed on the ticker

`deliver_one` read `post.over_limit`, the credential, the sender and the rate.
None of those four is about the asset, and no object on the bucket held when a
symbol was last published.

### The correction - a guard the bucket owns

`RepostGuard` keys the last send by symbol and target. `ReadyToSend` builds one
in its constructor, so it lives as long as the bucket and every send route shares
it. `deliver_one` refuses before the sender is called, and records only after a
send succeeds, so a failed send does not start the hour.

The key is the symbol and the target together. The issue requires phase four to
write one post per push target, so one call reaches every selected platform in
one press. Keying on the symbol alone would refuse six of the seven targets on
every first press and break that requirement. Keyed on both, one ticker appears
at most once an hour in any one feed, and a second call on that ticker is refused
on every target.

### The rerun - the same three presses

```
first press:              7 sent, 0 held
second press at +30 min:  0 sent, 7 held
third press at +60 min:   7 sent, 0 held
```

The reason each held post carries:

```
BCH-USD reached X 30 minute(s) ago; one post per ticker per hour.
```

The cap refuses inside the hour and allows after it, on the same run, so the
guard has been watched doing both.

## 2 The hour cap has to hold across two calls, not one

### The error - a second scan refilled the bucket with the same ticker

A scan replaces the bucket. A second scan on the same ticker writes seven new
posts about a new call, and a per-call check would let all seven out.

### The reproduction - two scans ten minutes apart

Run against the shipped file:

```
call one:               7 sent, 0 held
bucket refilled with 7 post(s)
call two at +10 min:    7 sent, 0 held
```

### The cause - the bucket is rebuilt, so anything held on a post is lost

`ReadyToSend.load_run` replaces `posts` outright. State kept on a post, or on a
call, does not survive the next scan.

### The correction - the guard lives on the bucket, not on a post

`RepostGuard` is a field of `ReadyToSend`, which `load_run` never replaces, so
what was published survives every rescan.

### The rerun - the same two scans

```
call one:               7 sent, 0 held
bucket refilled with 7 post(s)
call two at +10 min:    0 sent, 7 held
```

```
BCH-USD reached X 10 minute(s) ago; one post per ticker per hour.
```

## 3 A reversal failed after two candles, where the directive needs three

### The error - the floor was two

The operator's directive of 9 September 2026 requires three or more candles
continuing the trend before a follow-up calls a reversal failed. The floor in the
file was two, from the phase seven spec of 6 September. The newest word governs.

### The reproduction - one call, one candle at a time

A bullish reversal call on the daily timeframe, driven with one, two, three and
four candles carrying on downward. Run against the shipped file:

```
1 candle(s) against -> open   run 1  settled=False
2 candle(s) against -> failed run 2  settled=True
3 candle(s) against -> failed run 2  settled=True
4 candle(s) against -> failed run 2  settled=True
```

A daily call was failed after two days, and the open case at one candle said only
that the target was not reached.

### The cause - a constant, and a message that omitted the run

`CONTINUATION_CANDLE_FLOOR` was 2, and `follow_up_detail` had no wording for a
call whose trend has run but not far enough. Its open message named the
confirmation target and never the continuation.

### The correction - the floor is three, and a short call says so

The floor is 3. `follow_up_detail` now names the run against the floor when one
is under way, so a call short of three candles reports where it stands instead of
reading like a call with no continuation at all. Nothing counts wall-clock time:
the count walks the candles the call's own timeframe produced, so three candles
on a daily call is three days.

### The rerun - the same four cases

```
1 candle(s) against -> open   run 1  settled=False
    the trend has held for 1 of the 3 candles a failure needs, last close 596.5, target 603.355 not reached
2 candle(s) against -> open   run 2  settled=False
    the trend has held for 2 of the 3 candles a failure needs, last close 590.5, target 603.04 not reached
3 candle(s) against -> failed run 3  settled=True
    the trend held for 3 candles in a row, last close 584.5, after 3 candle(s)
4 candle(s) against -> failed run 3  settled=True
    the trend held for 3 candles in a row, last close 584.5, after 3 candle(s)
```

Only a settled outcome writes a post, so the two-candle case composes nothing.

## The confirmation half, unchanged

The favourable move confirms a call through the confirmation share the settings
page already carries. No second percentage was added and no threshold was written
into the code. The setting is `confirmation_share_pct`, listed on the ATA-SPM
settings page as "Confirmation share %".

The same call, driven with one candle thirty dollars the favourable way, at a
share of 60 per cent:

```
before  confirmed  close 632.5 reached 604.435, 60% of the run to midline 605.725, after 1 candle(s)
after   confirmed  close 632.5 reached 604.435, 60% of the run to midline 605.725, after 1 candle(s)
```

Identical on both sides, which is the correct result: this unit did not touch the
confirmation path.

## The debugger, and what it printed

The whole drive runs clean under the strictest interpreter mode, and under the
debugger:

```
PYTHONWARNINGS=error python -X dev -X faulthandler U407REPOST_drive.py
EXIT=0

PYTHONWARNINGS=error python -X dev -X faulthandler -m pdb ... U407REPOST_stack.py
EXIT=0
```

## The archetypes

```
coding_archetype  src/trading/ata_spm_push.py                passed=True  errors=[]
ta_archetype      src/trading/ata_spm_push.py                passed=True  errors=[]
gui_archetype     src/trading/ata_spm_push.py                passed=True  errors=[]
docs_archetype    docs/manual/08-tabs/market-inspector.md    passed=True  errors=[]
```

The coding archetype was proved before it was trusted: `known_good.py` exits 0
and `known_bad.py` exits 1. Every tool in each report reads `ok`.

## What the operator sees differently

Press Post All twice on the same ticker inside an hour and the second press now
refuses, naming the ticker, the platform and how long ago it went out. Scan again
ten minutes later and the new call on that ticker refuses the same way. A daily
reversal call no longer reports a failure after two days; it takes three, and
until then it says how far the trend has run.
