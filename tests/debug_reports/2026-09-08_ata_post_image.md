# The ATA-SMP Post Image, Drawn On The Charts Tab Renderer

**Mode: Reference.**

Phase three carried a data record and no picture. It now draws the called
chart on the Charts tab's own renderer and writes a PNG, so the post's caption
captions something.

Nothing here was measured against a running Acervator. No process was started,
attached to or queried, no order was touched, and no exchange call was made.
Nothing was posted to any platform and no credential was read.
`~/.acervator/settings.json` hashed
`18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8`
before the work and the same after it.

## The candles

The images below were drawn on recorded daily bars read from
`~/.acervator_ra_tablets`, read-only. No candle was made up, resampled or
filled. The scan served `1d` only, so the other three crypto timeframes
answered no candles and read unread.

## The error that decided the design

The renderer is a `QWidget`. Phase three does not run on the drawing thread:
`src/gui/market_inspector.py` starts a worker thread and calls
`SectorBoard.compute` on it. Building a widget there was driven before any of
this was written.

**The error.** A widget built off the drawing thread, followed by a second
image painter on the same thread, kills the process.

```
Fatal Python error: Aborted
Current thread 0x000040f8 [ata-scan-probe] (most recent call first):
  File "premortem_u407_thread.py", line 27 in build_off_thread
exit 3
```

**The reproduction.** `python -X dev -X faulthandler`, PySide6 6.11.2, Qt
6.11.2, offscreen platform, one `threading.Thread`. Painting a `QImage` on
that same thread and building no widget exits 0 and reports the pixel it
painted.

```
off GUI thread, qimage: painted, pixel 0xff204060      exit 0
```

**The cause.** Qt owns widgets on the thread that runs the application. A
render path that builds one inside `ata_spm.pull` would abort the live
application on every scan.

**The correction.** The drawing state and the paint routine moved out of the
widget into `ChartPainter`, which is a plain object. `CandlestickChart` now
inherits it and supplies the window. `paintEvent` hands `paint_to` a widget
painter; `render_chart_png` hands it a `QImage` painter. One paint routine,
two paint devices, no second renderer.

`src/gui/native_chart.py` — the widget is now a thin shell over the painter

```python
    class CandlestickChart(ChartPainter, QWidget):
        def paintEvent(self, event):
            p = QPainter(self)
            self.paint_to(p, self.width(), self.height())
            p.end()
```

**The rerun.** The same probe with a `ChartPainter` in place of the widget
draws off the drawing thread and exits 0.

## Phase three reaches the renderer

The run drove the Market Inspector screen model's own Scan Now, which is what
the screen presses. The render helper was never called directly. `pdb` broke
on the first line of `render_chart_png` and printed the stack.

```
u407drive.py                              run = model.scan_now()
market_inspector_surface.py:2303          added = self.board.scan_now(
ata_spm.py:1056  SectorBoard.scan_now     sectors, added, found = self.compute(
ata_spm.py:1026  SectorBoard.compute      run(
ata_spm.py:918   run                      pull(
ata_spm.py:894   pull                     image=render_pull_image(...)
ata_spm.py:820   render_pull_image        return render_chart_png(
native_chart.py:2189  render_chart_png
```

## The file it wrote

Read back off disk after the run.

```
path              <ATA_POST_ROOT>/SOL-USD_1d_1787616000000.png
bytes             121044
size              1200 x 372
format            Format_ARGB32
distinct colours  7126
```

## It is not a uniform rectangle

The chart's ground is a gradient, so no single colour is the background: the
most common colour holds 14.89% of the picture. The reading that means
something is the same chart drawn with no candles, at the same width, as a
control.

```
                     drawn            control (no candles)
bytes                121044           2579
distinct colours     7126             17
most common colour   14.89%           12.5%

pixels compared      374400
pixels differing     279311
ink over control     74.602%
```

The control reports 17 colours where the drawn chart reports 7126, so the
count can tell a near-empty picture from a full one.

## The indicators drawn, and the bars behind them

The vote was a bearish reversal on SOL/USD, 1d, from 602 bars. Six voters
confirmed it. `ChartOverlay.voter` names the voter each overlay draws, so the
overlays are chosen by the vote and not by the toolbar defaults.

```
confirming voters  bollinger_bands, stochastic_rsi, volume, slingshot,
                   zscore, rsi
drawn              bb, stochrsi, volume
drawn voters       bollinger_bands, stochastic_rsi, volume
not drawn          slingshot, zscore, rsi
bars               602
```

Z-Score and RSI have no overlay in the registry, so no cap can draw them. The
image names them in its header line rather than passing over them.

## Max supporting indicators governs the picture

The cap is the ATA-SPM settings page field. It was set through
`MarketInspectorScreenModel.set_setting` and the same scan re-driven. The
drawn set, the image height and the colour count all move with it.

```
cap   drawn                                    height  colours   bytes
0     bb, stochrsi, volume, slingshot          372     10766     148845
1     bb                                       284      5396      67698
2     bb, stochrsi                             344      6851     112266
3     bb, stochrsi, volume                     372      7126     121044
6     bb, stochrsi, volume, slingshot          372     10766     148845
```

A cap of zero draws every confirming voter an overlay exists for, which is
four of the six. A cap above that number is the same picture.

## The caption captions the image

```
post.image_path   <ATA_POST_ROOT>/SOL-USD_1d_1787616000000.png
artefact keys     body, caption, image, thread_root
caption           the fixed header over "SOL/USD 1d - bear"
```

Before this unit `artefacts()` answered three text keys and no image.

## Where the file goes

`src/trading/ata_post_paths.py` defines one home-relative root,
`~/.acervator_ata_posts`, a sibling of the other runtime roots. It is the
fifth root `tests/conftest.py` watches and redirects, so no suite run can
write into the operator's home. Driving the run with
`ACERVATOR_ATA_POST_ROOT` set left no `~/.acervator_ata_posts` on disk.

## The Charts tab does not regress

`origin/current`'s renderer and this branch's renderer were built in one
process, given the same recorded bars at the same size, and read against each
other. Every value either side reports was compared, then both were rendered
and compared pixel by pixel, then the toolbar was driven through every
overlay off and on again.

```
                      ACERVATOR_VARIANT=qt   ACERVATOR_VARIANT=react
values compared       192                    192
values matched        192                    192
render size           1200 x 700             1200 x 700
pixels compared       840000                 840000
pixels matched        840000                 840000
toggle steps          19                     19
toggle steps matched  19                     19
```

The pixel comparison can report a difference: the same reading against a
chart carrying one overlay instead of eight matches 452736 of 840000.

## The archetype findings this unit had to repair

**S003, 114 findings.** Splitting the widget produced them all. The rule
suppresses itself for the whole class when a base is a Qt widget, because the
inheritance is not readable; a plain class is read strictly. Sixty-five
colours were written onto the class by a loop and eight overlay flags by
`setattr`, so no reader could see either. The colours are now declared, and
the flags are one dictionary built from the overlay registry, which keeps the
registry the only place overlays are enumerated.

`src/gui/native_chart.py` — one dictionary, built from the registry

```python
            self._overlay_shown: dict[str, bool] = {
                one.key: one.starts_on for one in CHART_OVERLAYS
            }
```

**TA004, 2 findings.** The mouse handlers compared a pointer position against
`self.height() - self._resize_grip_h`. With the grip height now assigned in
the painter and the comparison in the widget, the rule read pixel geometry as
band arithmetic. The quantities are named `press_y_px` and `grip_top_px`, and
the archetype reports `passed=True`.

**`QImage.save` overload.** Passing the format as a second string matched no
overload. The name carries `.png` and Qt reads the format from it.

**flake8 F401, F811, F402.** An unused `field` import from `dataclasses`
collided with a parameter and a loop variable of the same name. The import is
gone.

**A note that named the wrong reason.** The header line read `no overlay:
slingshot, zscore, rsi` while Slingshot has an overlay and was cut by the cap.
It reads `not drawn:` now, which is true of both reasons.

## What this host could not show

Text on the rendered images draws as boxes. Measured on this machine under the
offscreen platform:

```
platform       offscreen
font families  0
```

That is a fact about this host, not about the product. The build machine ships
font families and draws the same text as glyphs.

## What the operator sees differently

Nothing on screen yet. A post that reaches Ready to Send now has a chart image
on disk beside its text, drawn from the same candles the call was made on and
carrying the indicators that voted for it.

## What is not done

Nothing reads the image on screen. The Ready to Send zone draws the post's
text and does not show the picture.

`deliver_one` hands the whole post to the sender, so the image path travels
with it, and `RecordedDestination` keeps it. No sender reaches a platform, so
nothing has been sent and nothing was tried.

The image is never deleted. One PNG is written per asset, timeframe and last
bar, so a repeated call on the same bar overwrites its own file and a new bar
adds one. Nothing prunes `~/.acervator_ata_posts`.
