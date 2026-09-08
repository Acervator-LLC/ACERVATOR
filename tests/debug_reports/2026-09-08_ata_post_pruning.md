# The ATA-SMP Post Image Store, Bounded

**Mode: Reference.**

ATA-SMP wrote one chart image per call and removed none of them. The store now
holds each market's newest image and removes the older ones on the same press
that writes a new one.

Nothing here was measured against a running Acervator. No process was started,
attached to or queried, no order was touched, and no exchange call was made.
Nothing was posted to any platform and no credential was read. The runtime
roots under the operator's home were read and never written: every writable
root was redirected to a throwaway directory before the application was
imported. `~/.acervator/settings.json` hashed
`18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8`
before the work and the same after it.

## The candles

The scans below ran on recorded daily bars read from `~/.acervator_ra_tablets`,
read-only. No candle was made up, resampled or filled. The scan served `1d`
only, so the other three timeframes the stocks class scans answered no candles
and read unread.

## What the retention had to be derived from

Phase seven watches a reversal call and answers what happened to it. It was read
first, because a bound that removes an image a follow-up post still needs is
worse than no bound.

**Phase seven reads candles, never a file.** `FollowUpWatch.check` asks the
candle source for the chart again and measures closes against the Bollinger
midline. Nothing in that path opens the post store.

`src/trading/ata_spm_push.py` — phase seven asks the candle source, not the disk

```python
    def check(self, candle_source: Any, share_pct: Any) -> list:
        """Read each watched call's chart again and answer what happened to it.

        A settled call stops being watched and an open one stays, so no call
        is posted on twice.
        """
```

**Phase seven's own post carries no image.** `format_follow_up` builds its post
without an image path, and the artefact map omits the image key when that field
is empty. A follow-up post is text: the original headline, the outcome and the
evidence.

`src/trading/ata_spm_push.py` — the image key appears only when a path is set

```python
        if self.image_path:
            written[ARTEFACT_IMAGE] = self.image_path
```

**One post kind names an image, and only the newest run's.** `format_post` takes
the path off the pull it is formatting. Phase four keys those pulls by asset and
timeframe, so one market resolves to one pull, and phase six replaces its whole
list of posts on every scan.

`src/trading/ata_spm_push.py` — one pull per market, the last one winning

```python
    pulls = {(one.symbol, one.timeframe): one for one in getattr(run, "pulls", [])}
```

The whole set of images any post can name is therefore the newest image of each
market. That is the retention rule, and the count is a named constant rather
than a number chosen by taste.

`src/trading/ata_post_paths.py` — the rule and where it comes from

```python
#: ``ata_spm_push.format_run`` keys its pulls by symbol and timeframe, last
#: write winning, so one image per market is every image a post can name.
POST_IMAGES_KEPT_PER_MARKET = 1
```

## The first error: two images written back to back share one time

Ordering a market's images by their modification time was the obvious design.
It was driven before any pruning was written, and it does not work on this
machine.

**The error.** Two files written one statement apart report the same
modification time, so the ordering cannot tell which is newer.

```
first  mtime_ns: 1788903278343250400
second mtime_ns: 1788903278343250400
distinct: False
```

**The reproduction.** `python -X dev -X faulthandler`, one script, two writes
into a temporary directory, then `st_mtime_ns` read off each.

**The cause.** The clock behind the file timestamp does not advance between two
writes in the same tick. Nothing in the file system guarantees it will.

**The correction.** The order comes from the name, not the clock. The stamp in a
post image name is the call's last bar, which rises as bars close, and the name
settles two images carrying one stamp. The caller also hands in the path it has
just written, which is kept whatever its order.

`src/trading/ata_post_paths.py` — the order comes out of the name

```python
def stamp_order(path: object) -> tuple:
    """The sort key putting one market's newest post image first.

    The stamp is the call's last bar, which rises as bars close, and the name
    settles two images carrying one stamp.
    """
```

**The rerun.** The same script proved the name shape the order rests on. Every
field is folded through `name_part`, which turns an underscore into a dash, so a
post image name always splits into exactly three fields and a foreign file never
does.

```
'BTC/USD' '1h' 1725800000  -> BTC-USD_1d_1725800000.png   parts=3
'A_B_C'   '1h' 1725800000  -> A-B-C_1h_1725800000.png     parts=3
'///'     '1h' 1725800000  -> _1h_1725800000.png          parts=3
''        ''   ''          -> __.png                      parts=3
underscores answered by name_part across every case: 0

notes.txt   suffix=.txt  parts=1
README      suffix=      parts=1
a_b.png     suffix=.png  parts=2
a_b_c_d.png suffix=.png  parts=4
```

## The second error: the first scan reached no chart

**The error.** The first driven scan answered `Phase 1 Evaluate: 1 sector(s), 0
call(s), 0 chart(s)`. No image was written and the pruning was never reached, so
the run measured nothing.

**The reproduction.** The Market Inspector screen model pressed Scan Now over
three crypto assets on recorded 2024 to 2026 daily bars.

**The cause.** Phase two keeps only a vote whose band voter and consensus name
one direction. The bars chosen carried no such vote. The zero was a fact about
the bars served, not about the pruning.

**The correction.** The recorded windows were measured for reversal votes before
the scan was driven again. Eleven of the sixty-two recorded assets carry a
reversal on the 2024 to 2025 window and three on the 2024 to 2026 window, so the
scan was pointed at three assets that vote on the first window and one that
votes on both.

```
(2024, 2025, 2026)  reversals: 3   AMZN GME IWM
(2024, 2025)        reversals: 10  AAPL CVNA IWM KOSS PLTR PRNT TRX TSLA ...
(2025, 2026)        reversals: 3   AMZN GME IWM
(2025,)             reversals: 9   AAPL CVNA IWM PLTR PRNT TRX TSLA UWMC ...
(2026,)             reversals: 3   AMZN GME IWM
```

**The rerun.** The same press over those assets reached `Phase 3 Pull: 1
sector(s), 3 call(s), 3 chart(s)`.

## A press of Scan Now reaches the pruning

The run drove the Market Inspector screen model's own Scan Now. The pruning was
never called directly. A `pdb` breakpoint was set on the function and the
debugger printed the stack that arrived at it.

```
market_inspector_surface.py(2303)  scan_now()
ata_spm.py(1059)                   SectorBoard.scan_now()
ata_spm.py(1029)                   SectorBoard.compute()
ata_spm.py(921)                    run()
ata_spm.py(897)                    pull()
ata_spm.py(829)                    render_pull_image()
ata_post_paths.py(132)             prune_post_images()
```

`src/trading/ata_spm.py` — the write and the bound, one after the other

```python
    path = ata_post_paths.post_image_path(vote.symbol, vote.timeframe, stamp)
    image = render_chart_png(
        held,
        vote.symbol,
        timeframe_label(vote.timeframe),
        path,
        voters=[one.indicator for one in confirming_signals(vote)],
        max_overlays=int(max_supporting_indicators or NO_INDICATOR_CAP),
    )
    ata_post_paths.prune_post_images(path)
    return image
```

## The store, before and after

The store was a throwaway directory. It was planted with three older images for
each of the three markets the scan would render, and with three files no post
image name can produce.

```
                                    files      bytes
planted, before scan one               12        174
after scan one                          6     478068
after scan two                          6     441483
after scan three                        6     441483
```

The run says what it removed. Every line below is the pruning's own report,
read off the logger it writes to.

```
scan one    removed 7 image(s), reclaimed 84 byte(s), kept 3, refused 0
            removed 1 image(s), reclaimed 21 byte(s), kept 3, refused 0
            removed 1 image(s), reclaimed 21 byte(s), kept 3, refused 0
scan two    removed 1 image(s), reclaimed 173950 byte(s), kept 3, refused 0
scan three  removed 0 image(s), reclaimed 0 byte(s), kept 3, refused 0
```

Scan one wrote three images and removed all nine planted ones. Each market ends
holding exactly the image that scan wrote.

```
AAPL_1d_1767139200000.png   136868
IWM_1d_1767139200000.png    173950
TSLA_1d_1767139200000.png   167202
```

## The newest images survive and every post finds its picture

Phase four wrote twenty-one posts after scan one, one per call per push target.
Every one names an image, the three distinct paths are the three files above,
and all three are on disk after the pruning ran.

```
posts                     21
posts naming an image     21
distinct images named      3
each of the three         exists=True
```

## Phase seven keeps watching a call whose image is gone

Scan two served one more recorded year. One asset voted a reversal on the later
bars, so a newer image was written for it and its scan-one image was removed —
173950 bytes, the largest single reclaim in the run. Phase seven was still
watching that asset's original call at the time.

```
images the scan-one run wrote that are gone:  IWM_1d_1767139200000.png
calls still watched after scan two:           1, IWM at bar 671
outcomes the last check answered:             3, all failed
follow-up posts in the bucket:                21
follow-up posts naming an image:              0
```

Twenty-one follow-up posts were composed and not one of them named an image.
That is the measurement the retention rests on: phase seven settled three calls,
wrote a post for each against every push target, and asked the store for
nothing.

## It removes nothing when the store is inside its bound

Scan three served the same bars as scan two, so the call resolved to the same
last bar and the same file name. The pruning reported zero and the store did not
move.

```
removed 0 image(s), reclaimed 0 byte(s), kept 3, refused 0
files  6 -> 6
bytes  441483 -> 441483
```

## A file being written is never removed

The refusal is the operating system's, not a check in the code. An image was
held open with an unclosed write handle and Scan Now was pressed, so the pruning
met a file the host still owned.

```
held image still on disk : True
free image still on disk : False
ATA post image IWM_1d_1.png stayed, the host holds it:
  [WinError 32] The process cannot access the file because it is being
  used by another process
ATA post store: removed 1 image(s), reclaimed 8 byte(s), kept 1, refused 0
```

The same file after the handle closed, on the next press:

```
ATA post store: removed 1 image(s), reclaimed 9 byte(s), kept 1, refused 0
held image still on disk : False
```

The same file refuses while it is held and goes when it is free, so the control
reports both ways. No defect was planted to produce it.

## Nothing outside the post store was touched

The pruning reads one directory, the root its own module names, and it never
walks into a subdirectory or another tree. Three files that no post image name
can produce sat in the store throughout and were never parsed as images.

```
operator-notes.txt   exists=True
README               exists=True
two_fields.png       exists=True
```

The operator's runtime roots, before the run and after it:

```
                          before                        after
.acervator                484 files, 527109429 bytes    484 files, 527109429 bytes
.acervator_ra_tablets     413 files,   9829596 bytes    413 files,   9829596 bytes
.acervator_paper          absent                        absent
.acervator_ata_posts      absent                        absent
settings.json sha256      18d380c7...feeac8             18d380c7...feeac8
```

`~/.acervator_logs` held 4062 files before and 4062 after, and its byte total
moved. That movement is not this run's. Measured with no scan running at all,
the same total moved on its own:

```
~/.acervator_logs bytes at rest : 1438944606
20 seconds later, still no scan : 1439638759
grew by                         : 694153
```

The live application writes there continuously, and this run redirected every
writable root away from the operator's home before importing anything. The count
of files is the reading that holds still, and it did.

## What the archetypes report

```
src/trading/ata_post_paths.py   coding passed=True   ta passed=True
src/trading/ata_spm.py          coding passed=True   ta passed=True
```

Both fixture controls were driven first: the known-good file exits 0 and the
known-bad file exits 1, so the instrument can report.

Back to [the debug report index](README.md).
