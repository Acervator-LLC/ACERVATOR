# Portfolio Battery reaches both hosts and draws a real result

The Sim tab carries a third mode. It walks a portfolio's symbols over the
RA-StoneTablets through the Back Test walker, which builds the shipped scrum and
fold chains, and sets each result against buy and hold read off the same walk.
Both builds were driven and read off the drawn table and the drawn page.

`~/.acervator/settings.json` hashed the same before and after every run.

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

`~/.acervator_ra_tablets` still holds 411 manifest entries and its index file
still carries its original timestamp. No authenticated call, no credential, no
order, and the running Acervator process was never started, attached to or
queried.

## Reproduce

Both hosts were built offscreen, put into the new mode, given a portfolio and a
span, and pressed. The Qt cells were read off `QTableWidget`; the React cells
were read out of the loaded page's own DOM.

```
QT_QPA_PLATFORM=offscreen
SimulatorTabQt(TabletSource(TABLET_ROOT))
  choose_mode("portfolio_battery") -> "portfolio_battery"
  choose_portfolio("SPAC_BUST"), choose_span("Apr24-Apr25")
  run_portfolio()
SimulatorTabReact(TabletSource(TABLET_ROOT))
  build_panel(), loadFinished -> page_ready True
  same three calls, then runJavaScript over the page
```

## The mode is reachable

The mode selector lists three names and the result stack shows the third pane.
The two rows the removed strips left carry the new presses, and the portfolio
and span selectors are hidden in the other two modes.

```
modes                 ['validation', 'back_test', 'portfolio_battery']
result pane index     2
buttons               ['Run Portfolio', 'Run Every Portfolio']
battery row hidden    False in portfolio_battery, True in validation
portfolio selector    35 options, data-chosen SPAC_BUST
span selector         data-chosen Apr24-Apr25
```

## The run executes over real tablet candles

SPAC_BUST holds five symbols and three of them have a tablet. The walk read 756
daily bars and spent 669 gate-chain evaluations at the daily timeframe.

```
1 portfolio(s) over Apr24-Apr25, 2024-04-01T00:00:00Z to 2025-04-02T00:00:00Z.
15 symbol runs at 1d, 1w, 1M.
1 of 1 portfolio(s) beat their own buy-and-hold at one timeframe or more.
2 symbol(s) hold no tablet: CCIV, IPOF
7 recorded gap(s) fall inside the span.
```

## Both hosts draw the same row

Eleven columns and three rows on each side. The first row is character for
character the same.

```
Qt     ['SPAC_BUST','1d','2024-05-10T00:00:00Z to 2025-04-01T00:00:00Z',
        '3 of 5','756','669','35','$390.75','$415.60','+24.85 (+6.36%)','40.0%']
React  ["SPAC_BUST","1d","2024-05-10T00:00:00Z to 2025-04-01T00:00:00Z",
        "3 of 5","756","669","35","$390.75","$415.60","+24.85 (+6.36%)","40.0%"]

React  columns 11  rows 3  data-ran true  data-verdict better
```

The monthly row reports no run rather than a result: twelve monthly bars sit
under the thirty the Bollinger window and the voting engine need, so its missing
weight reads 100%.

## The whole battery

Every portfolio over the whole tape, driven through `run_battery`.

```
35 portfolio(s) over All, 2020-01-01T00:00:00Z to 2026-09-08T00:00:00Z.
189 symbol runs at 1d, 1w, 1M.
12 of 35 portfolio(s) beat their own buy-and-hold at one timeframe or more.
3 symbol(s) hold no tablet: CCIV, EXPR, IPOF
524 recorded gap(s) fall inside the span.
26.16 seconds
```

## What the archetypes reported

Each fixture control ran first. `known_good` exits 0 and `known_bad` exits 1 for
all four.

```
coding   portfolio_battery.py  simulator_tab_surface.py  simulator_tab.py
         react_simulator_tab.py                                passed=True
gui      the four above, and simulator_tab.js                  passed=True
ta       the four above, and simulator_tab.js                  passed=True
docs     docs/manual/08-tabs/simulator.md                      passed=True

errors [] on every one; every tool in tool_availability reads ok
```

## One reading the shell gave wrong

`python -m ... > /dev/null; echo "name $(basename $f) exit $?"` reported exit 0
for `known_bad_widget.py`. The command substitution inside the same `echo` runs
before `$?` is expanded and resets it. Captured on its own line the same run
reports exit 1, which is the archetype's real answer.

```
wrong   gui known_bad_widget.py exit 0
right   out=$(cmd); code=$?   ->  exit 1
```
