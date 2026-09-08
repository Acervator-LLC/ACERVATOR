# Back Test Mode — what was run, and what it drew

Issue #117, step 4 of five. Recorded from runs on 8 September 2026 against the
operator's own Stone Tablets, read in place and read-only.

## The gate chain is the shipped one

`back_test` imports `latch` from `validation`, and that function builds the two
chains `ScrummingBot.tick` builds.

```
back_test latch is validation latch: True
chains: src.trading.gate_chain src.trading.gate_chain
```

No live stateful class is imported. `back_test` reads `GateContext` from
`src/trading/gate_chain.py`, `SimBot` from `src/simulator/fleet_source.py`, and
the voting engine and candle types at call time.

## The imported fleet, over real tablet candles

`SimulatorTabQt` built offscreen on its own default source, switched to Back
Test, and pressed Import Live Fleet.

```
TABLET_ROOT: C:\Users\<name>\.acervator\stone_tablets
38 of 38 bots ran over 1610472 tablet candles.
2026-01-01T00:00:00Z to 2026-08-01T18:35:00Z, 5272 gate-chain evaluations.
58 scrum latches and 55 fold latches.
58 scrum sells and 55 fold buys filled, $38.02 in fees.
qt table rows after import: 38
qt fleet rows after import: 38
bots that filled a trade: 26
```

## The new bot the selector defines

Create New Bots on the tablet the selector was showing.

```
qt row 0: ZRX/USD@coinbase | ZRX/USD | ZRX_5m_2026_coinbase | 19677 | 201 |
2 / 2 | 2 / 2 | -70.31757498 | $11.10
```

## Both hosts draw the same result

`SimulatorTabReact` loaded its page, took the mode press and the fleet press,
and the document was read back through the page.

```
page ready: True
mode now: back_test
buttons: sim-import-live-fleet=Import Live Fleet | sim-create-new-bots=Create New Bots
table rows drawn: 38
table columns drawn: 9
row 0 cells: ff6a37a3 | ADA/USDC | ADA_5m_2026_coinbase | 61181 | 200 | 1 / 1 |
1 / 1 | +0.75090062 | $0.00
header cells: Bot ID | Symbol | Tablet | Candles | Ticks |
Scrum / Fold latched | Scrum / Fold filled | Units gained | Cash held
validation pane hidden: true / false
faults: []
```

The Qt window and the React page report the same four lines, the same 38 rows
and the same first row. Both name the buttons `sim-import-live-fleet` and
`sim-create-new-bots`, built from one `button_name` in the surface.

## The download path, against a throwaway root

`download_missing` was driven with a recorded connector into a
`StoneTabletsRegistry` on a temporary directory.

```
connector calls: 3
report: ZZZTEST coinbase chunks_ok 3 errors 0 candles 701
throwaway root files: MANIFEST.json, ZZZTEST_5m_2026_coinbase.json, _scratch
entry: ZZZTEST coinbase 5m 701 candles read back: 701
live root unchanged: True 407
no connector answers empty: []
```

## The live tree

`settings.json` hashed before and after the Qt run, inside one process.

```
before f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
state changed: {}
```

Four log files grew during the run. A control sampled the same four twice, 20
seconds apart, with no Simulator work between.

```
signals/session.jsonl        40287464 -> 40855782 grew
signals/session.digest.jsonl 14556371 -> 14581731 grew
trade/diagnostics.log        49274025 -> 49355150 grew
console/system.log           12668255 -> 12701485 grew
```

They grow on their own, so the running application wrote them.

## Two errors the runs threw, and what they were

**A segmentation fault at exit, code 139.** The React run ended with a Windows
access violation on the browser thread after every value had printed. The page
was deleted with no event loop left to process the deletion. Closing the page
and draining the loop first ends the same run at code 0. Nothing in the tab
changed.

**A run that read no tablet and no fleet.** The first probe replaced HOME with a
sandbox before importing, so `STONE_TABLETS_DIR` and the bot_state path both
resolved into an empty directory and every bot reported `no_tablet`. The probe
was rewritten to keep the real HOME and to prove the tree unchanged by hashing
it instead.

## One defect this unit found and fixed

The tab's own default source was the RA tablet root while a run read the live
one, so the selector listed one set of tablets and the run walked another. The
issue's own table gives the live root to Validation and Back Test and the RA
root to Portfolio Battery. `TABLET_ROOT` in the surface now names it once, and
both hosts and both runs read it.

## One seam finding, reported not repaired

`back_test.bb_detect_thresholds` is a second spelling of
`CircuitBreakerMixin._bb_detect_thresholds`. That method reads only
`self.config` and is pure, but it is a method on a live bot mixin, so calling it
needs a live bot. Extracting it would change a live trading file to serve the
Simulator.
