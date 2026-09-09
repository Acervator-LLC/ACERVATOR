# The live gate chain verdict decides the chart and the bucket

## The error

`ata_spm.pull` built the post image for every call the TA vote produced, and the
gate chain verdict it carried decided nothing.

`src/trading/ata_spm.py`, before the change:

```python
        gates=ata_gate_scan.scan_gates(
            vote.symbol, vote.timeframe, candles, vote.summary, proximity, rows,
            settings,
        ),
        panel=dict(rows or {}),
        image=render_pull_image(vote, candles, max_supporting_indicators, messages),
```

Both sit in one constructor call, so the render ran whatever the chains said.
`ata_spm_push.format_run` keys its posts off `AtaSpmRun.pulls`, so every call
reached the Ready to Send bucket as well.

## Reproduction

Two drivers run the real `ata_spm.run` over real venue candles. The asset source
is `ata_asset_maps.listings_for` and the candle source is
`ata_asset_maps.venue_candles`, which reads the Yahoo chart endpoint. The first
driver scans forex `major`, forex `minor` and metals `spot` — 32 listed assets,
four timeframes each, 128 votes. The second scans the two forex sectors and then
hands the run to `market_inspector_surface.sector_entry`, so the lines the zone
draws are read back from the same run.

```
PYTHONIOENCODING=utf-8 PYTHONWARNINGS=error \
python -X dev -X faulthandler run_bucket_gate.py
python -X dev -X faulthandler run_read_path.py
```

`ACERVATOR_ATA_POST_ROOT` points the image store at an empty temporary
directory, so the file count before and after is attributable to the run alone.

## The cause

Two faults in `src/trading/ata_spm.py`.

**The verdict was never read.** `ata_gate_scan.GateScan` published `latched`,
`blocked`, `not_run` and `ran`, and no single field said whether the chains
would fire. The raw `ChainResult.should_fire` cannot serve: a scan holds no
position, so `delta_positive`, `interval` and `hysteresis_scrum` always block
the scrum chain and `tranches_queued` and `hysteresis_fold` always block the
fold chain. Read straight off the chain, `should_fire` is False on every market
ever scanned.

**The judgement was the reversal vote.** `identify` kept only
`AssetVote.is_reversal` rows, and those were the only markets `pull` ever saw.
Measured on the 128 real votes: 14 reversal calls, 4 markets the chains would
fire, and **no market in both sets**. Gating the reversal calls on the chain
verdict would have posted nothing at all.

## The correction

**One verdict, read off the states the chains already answered.**
`src/trading/ata_gate_scan.py` gains `GateScan.side_fires`, `firing_side` and
`would_fire`. A chain fires when it ran at least one gate and every gate that
ran latched. The states come from `ChainResult.passed` and
`ChainResult.blocked`; no gate condition is copied and no gate is re-tested.
The confidence term is the chain's own, through `confidence_floor`, and the
scan adds no floor of its own.

```python
    def side_fires(self, side: Any) -> bool:
        decided = [one for one in self.side_readings(side) if one.ran]
        return bool(decided) and all(one.state == STATE_LATCHED for one in decided)
```

**The scan runs before the image.** `pull` now computes `gates` into a local and
renders only on `would_fire`.

```python
    image = (
        render_pull_image(vote, candles, max_supporting_indicators, messages)
        if gates.would_fire
        else ChartImage()
    )
```

**The verdict is the only judgement.** `identify` ranks every vote the run cast
instead of filtering on the reversal reading, and `run` partitions on the
verdict. A refused market keeps its scan in `AtaSpmRun.refused`, so a reader
sees it was judged and on which gates it failed. `SectorScan.calls` still holds
the reversal votes for the sector readback, which is where that reading belongs.

```python
        if held.gates.would_fire:
            found.calls.append(vote)
            found.pulls.append(held)
        else:
            found.refused.append(held.gates)
```

**The charts reach the screen.** `market_inspector_surface.sector_entry` picked
the pulls whose symbol matched a reversal call, so the two markets the chains
fired on would have drawn no chart row and no voting panel while the zone line
said two charts. It now picks the pulls of the sector's own assets.

```python
    assets = set(scan.assets)
    held = [one for one in pulls if one.symbol in assets]
```

## The rerun

Exit code 0 on both drivers, no traceback, no warning raised as an error.

```
PNG count before: 0
phase line: Phase 3 Pull: 2 sector(s), 2 call(s), 2 chart(s), 110 refused by the gates
```

### The markets the chains fired

One on each chain.

```
CHARTED NZD/JPY 1h BEARISH firing_side='fold'
  scrum: fires=False | ta_bullish=blocked, trend_hold=latched,
    midline_scrum=blocked, target_fires=latched, bb_proximity_scrum=blocked,
    circuit_breaker_scrum=latched, htf_defer_scrum=latched,
    adx_trend_suppression=blocked, efficiency_ratio_regime=latched,
    zscore_extremity=latched
  fold: fires=True | ta_bearish=latched, midline_fold=latched,
    bb_proximity_fold=latched, circuit_breaker_fold=latched,
    htf_defer_fold=latched, zscore_extremity=latched
  image='C:\...\Temp\ata_read_path_run\NZD-JPY_1h_1788937200000.png'

CHARTED EUR/NZD 1d BULLISH firing_side='scrum'
  scrum: fires=True | ta_bullish=latched, trend_hold=latched,
    midline_scrum=latched, target_fires=latched, bb_proximity_scrum=latched,
    circuit_breaker_scrum=latched, htf_defer_scrum=latched,
    adx_trend_suppression=latched, efficiency_ratio_regime=latched,
    zscore_extremity=latched
  fold: fires=False | ta_bearish=blocked, midline_fold=blocked,
    bb_proximity_fold=blocked, circuit_breaker_fold=latched,
    htf_defer_fold=latched, zscore_extremity=latched
  image='C:\...\Temp\ata_read_path_run\EUR-NZD_1d_1788912000000.png'
```

Six fold gates ran on the first and all six latched. Ten scrum gates ran on the
second and all ten latched.

### A market the chains refused

```
REFUSED AUD/USD 1w
  scrum: fires=False | ta_bullish=latched, trend_hold=blocked,
    midline_scrum=latched, target_fires=blocked, bb_proximity_scrum=blocked,
    circuit_breaker_scrum=latched, htf_defer_scrum=latched,
    adx_trend_suppression=latched, efficiency_ratio_regime=blocked,
    zscore_extremity=latched
    blocked -> trend_hold: trend_hold(70%)
    blocked -> target_fires: target_fires=False(detect/fire)
    blocked -> bb_proximity_scrum: BB-below-upper-detect(bb_pos=0.84<0.88)
    blocked -> efficiency_ratio_regime: efficiency_ratio_regime(ER=0.964>=0.70;
      strong-trend MR suppression)
  fold: fires=False | ta_bearish=blocked, midline_fold=blocked,
    bb_proximity_fold=blocked, circuit_breaker_fold=latched,
    htf_defer_fold=latched, zscore_extremity=latched
    blocked -> ta_bearish: TA-not-bearish(dir=BULLISH)
    blocked -> midline_fold: fold_ok_midline=False(bb_pos=0.84)
    blocked -> bb_proximity_fold: BB-above-lower-detect(bb_pos=0.84>0.12)
```

110 markets were refused in that run. One is quoted in full above.

### The post root, before and after

```
PNG count before: 0
PNG count after:  2
new PNGs: ['EUR-NZD_1d_1788912000000.png', 'NZD-JPY_1h_1788937200000.png']
```

Two charts for the two firing markets. 110 refusals wrote nothing.

### The lines the zone draws

```
=== zone entry for minor ===
headline: minor (forex)
meta: 21 asset(s) · 84 vote(s) · 11 reversal call(s)
panels drawn: 2
  Phase 3 Pull NZD/JPY 1hr: 286 candles, last close 89.816
  Phase 3 Pull NZD/JPY bands: lower 89.7037 · middle 90.0281 · upper 90.3525
  Phase 3 Pull EUR/NZD 1d: 244 candles, last close 1.98541
  Phase 3 Pull EUR/NZD bands: lower 1.94832 · middle 1.9659 · upper 1.98349
```

Neither charted market is one of the 11 reversal calls, which is why the
`sector_entry` correction was needed for the charts to appear at all.

### The control on the verdict

A run of the first driver swept all 128 votes through `ata_gate_scan.scan_gates`
on its own, outside `run`, and counted the markets that would fire:

```
votes 128, would_fire 1
WOULD FIRE EUR/NZD 1d BULLISH
  confidence 0.2334 floor 0.1923 band_position 1.0713 reversal=False
```

```
phase line: Phase 3 Pull: 3 sector(s), 1 call(s), 1 chart(s), 127 refused by the gates
PNG count before: 0
PNG count after: 1
new PNGs: ['EUR-NZD_1d_1788912000000.png']
bucket posts: 7 over 7 targets
bucket markets: ['EUR/NZD']
```

The independent sweep and `run` name the same one market, and the bucket holds
that market on all seven push targets and nothing else.

## What else the run measured

`pull` now runs for every vote rather than for the reversal calls alone, so the
candle source is read once more per vote. For crypto that source is the Market
Inspector scan cache and costs nothing; for forex and metals it is a venue
fetch. No indicator arithmetic was touched in this change.
