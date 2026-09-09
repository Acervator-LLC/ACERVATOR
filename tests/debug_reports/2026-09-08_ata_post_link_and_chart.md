# The Organization Link On Every Post, And The Chart That Says Why

**Mode: Reference.**

Two runs are recorded here. The first put the Acervator-LLC link on every post
and re-measured every push target against its own ceiling. The second drove
phase three on a recorded tape and drew the chart the operator asked to see.

Nothing was posted to any platform and no credential was read. No Acervator
process was started, attached to or queried, no order was touched, and no
exchange call was made. `~/.acervator_ra_tablets` was read and never written.
`~/.acervator/settings.json` hashed
`18d380c7134dadbb2acbf5cbe5527ea177fe8b23cc77eb3fff6334fb03feeac8`
before the work and the same after it. The one directory written is the ATA
post root, which is what holds a post's chart image.

## The candles

Every reading below comes from recorded daily bars in
`~/.acervator_ra_tablets`, read-only, through `candles_from_raw`. No candle was
made up, resampled or filled. The scan served `1d` only, so the crypto class's
other three timeframes answered no candles and read unread.

## Part one, the link

### The error - no artefact carried a link

`compose` wrote the fixed header over the evidence lines and nothing else, so
no artefact of any post carried a link to the organization page.

### The reproduction - seven targets formatted

```
PYTHONWARNINGS=error python -X dev -X faulthandler u407_drive_phase_three.py 2026 AMZN
```

The run builds one `ata_spm.SectorBoard`, presses `scan_now` with a tape-backed
asset source and candle source, and formats the first call for every row of
`ata_spm_push.PUSH_TARGETS`. Before the change it printed seven bodies, none
carrying a web address.

### The cause - compose wrote the header alone

`src/trading/ata_spm_push.py`, `compose`. It joined `FIXED_HEADER` with the
lines it was handed. Every artefact property — `body`, `caption`,
`thread_root` and `title` — calls it, so one omission reached all four.

### The correction - one constant, one line

One constant and one line. `ORGANIZATION_URL` sits beside `FIXED_HEADER`, and
`compose` puts it under the lines.

`src/trading/ata_spm_push.py` — the link, written once

```python
def compose(lines: Any) -> str:
    """``FIXED_HEADER`` over ``lines`` over ``ORGANIZATION_URL``.

    ``fit_to_target`` drops ``lines`` to reach a ceiling and reaches neither
    ``FIXED_HEADER`` nor ``ORGANIZATION_URL``.
    """
    return POST_LINE_SEPARATOR.join(
        (FIXED_HEADER,) + tuple(lines) + (ORGANIZATION_URL,)
    )
```

`fit_to_target` measures `compose(lines)` against the ceiling and drops only
from `lines`. The link is outside that list, so a ceiling takes evidence and
never the link.

### The rerun - every target against its ceiling

The same command, on the same tape and the same call. `measured` is the body in
the unit that target counts in, and `dropped` is how many evidence sentences
`fit_to_target` left out.

| target | ceiling | counted in | before | after | dropped | over |
|---|---|---|---|---|---|---|
| X | 280 | weighted characters | 272 | 246 | 7 | no |
| Instagram | 2200 | characters | 727 | 760 | 0 | no |
| LinkedIn | 3000 | characters | 711 | 744 | 0 | no |
| TikTok | 4000 | UTF-16 runes | 765 | 798 | 0 | no |
| Facebook | none published | characters | 765 | 798 | 0 | no |
| Threads | 500 | UTF-8 emoji units | 470 | 431 | 4 | no |
| Reddit | 40000 | characters | 765 | 798 | 0 | no |

The run also read every artefact of all seven posts back. The link is present
in `body`, `caption`, `thread_root`, and in the `title` Reddit carries.

The X post, in full, is what a 280-character ceiling holds:

```
This is not investment advice. It is a demonstration of Ekthelius's proprietary TA engine housed in the Acervator governance execution platform.
AMZN on 1d: bullish reversal called.
Abbreviated: 7 evidence line(s) omitted.
https://github.com/Acervator-LLC
```

X counts a web address as 23 whatever its real length, so the 32-character
link costs 24 of the 280 with its line break. Threads counts every character,
so the same link costs 33 of its 500 and one more sentence drops.

## Part two, the chart

### The error - the picture stated no direction

The image phase three drew stated no direction and explained no voter. A reader
could see four indicators plotted and could not see which way the call went or
what any of them read.

### The reproduction - the same scan

The same command. It printed the image path and the four overlays drawn, and
the picture carried the ticker, the timeframe and the candle count.

### The cause - the renderer took no call

`src/gui/native_chart.py`, `render_chart_png`. It passed the confirming voters
to `show_only`, which switches the matching overlays on, and passed nothing
else. `ChartPainter` had no field for the call, so `paint_to` had nothing to
draw. `src/trading/ata_spm.py`, `render_pull_image`, held the direction and the
standardised sentences and forwarded neither.

### The correction - set_call and the three marks

`ChartPainter.set_call` takes the direction and one `(voter, sentence)` pair per
confirming voter. `_draw_call` paints three marks, and each one is a value the
run produced.

`src/gui/native_chart.py` — what the picture takes

```python
        def set_call(self, direction: str, readings=()) -> None:
            """Take one reversal direction and one reading line per voter.

            ``readings`` are ``(voter, text)`` pairs and ``_draw_call`` paints
            them under the time axis.
            """
```

`src/gui/native_chart.py` — the three marks

```python
        def _draw_call(self, ctx, h: int) -> None:
            """Draw the reversal badge, the call bar mark and the voter strip.

            The bar marked is the last candle, which is the bar the direction
            ``set_call`` took was voted on.
            """
```

The badge names the direction the vote took. The dashed rule and triangle mark
the last bar, which is the bar `VotingEngine.compute_all` was run to. Each strip
row carries the colour of the overlay drawing that voter, from
`ChartPainter.overlay_colour`, and the sentence `ata_spm.indicator_message`
wrote. A voter no overlay draws takes the dim colour, and the header line
already named those two.

`src/trading/ata_spm.py` — the pull hands its own messages to the renderer

```python
        direction=vote.direction_text,
        readings=[(one.indicator, one.message) for one in messages or ()],
```

### The rerun - the stack, the picture and the control

The stack under `pdb`, broken on the line that writes the file, is the path
phase three reaches the chart writer by. `MarketInspectorSurface.scan_now`
calls the same `SectorBoard.scan_now` this run pressed.

```
src/trading/ata_spm.py(1065)scan_now()   -> sectors, added, found = self.compute(
src/trading/ata_spm.py(1035)compute()    -> run(
src/trading/ata_spm.py(927)run()         -> pull(
src/trading/ata_spm.py(903)pull()        -> image=render_pull_image(...)
src/trading/ata_spm.py(824)render_pull_image() -> image = render_chart_png(
src/gui/native_chart.py(2350)render_chart_png() -> if not image.save(str(target)):
```

At that frame the painter held direction `bullish` and six readings, and the
image measured 1200 by 478.

**The tape.** `AMZN_1d_2026_yahoo.json`, 170 daily bars, source
`yahoo_chart_v8_ONE_DAY_SPLIT_ADJUSTED`. **The call.** Amazon on the daily
chart, a bullish reversal, net score `+2.0288`, consensus confidence `0.1734`,
Bollinger band position `0.3346`. Phase two answered it because the band voter
and the consensus named one direction.

**The indicators drawn, and what each read.**

| voter | what it read | drawn as |
|---|---|---|
| Bollinger Bands | band position 0.3346, votes bullish at 14% | the bands and their cloud |
| Stochastic RSI | %K at 23.96, votes bullish at 80% | the sub-pane oscillator |
| Ichimoku Cloud | price above the cloud, votes bullish at 59% | the kumo and its four lines |
| Volume | Money Flow Index 48.9, votes bullish at 15% | the volume strip |
| ADX | +DI 27.41 against -DI 20.21, ADX 16.53, votes bullish at 24% | no overlay draws it |
| Supertrend | +3.438% from the line, votes bullish at 37% | no overlay draws it |

**The picture.** `~/.acervator_ata_posts/AMZN_1d_1788480000000.png`, 164,402
bytes, 1200 by 478 pixels, 14,062 distinct colours. 90.53% of its 573,600
pixels are not its commonest colour, so it is not a uniform rectangle.

**The two-sided control.** The same tape and the same two voters were drawn
twice, once with a direction and once without.

| render | height | bytes |
|---|---|---|
| no call set | 344 | 94,383 |
| call set | 390 | 99,952 |

The plain render carries no badge, no bar mark and no strip. That is the Charts
tab's own path, which never calls `set_call`, so the live screen draws what it
drew before.

## What is not built

The Stochastic RSI sub-pane plots the raw 0-to-1 ratio, while the voter decides
on `%K`, the three-bar average of that ratio on a 0-to-100 scale. The two are
different series, so the sentence in the strip and the badge on the pane will
not read as the same number. The strip states the number the vote used and the
pane is unchanged by this work.
