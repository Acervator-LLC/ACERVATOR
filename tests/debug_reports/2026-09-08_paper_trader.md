# Paper Trader: the initial build-out, driven against the live feed

The tab is built and reached by the running program. Every reading below came
from running the program, not from a test.

`~/.acervator/settings.json` hashed the same before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## The tab is reached, in both variants

`MainWindow._setup_ui` was run under the offscreen platform, once per variant,
and the tab bar read back off the real `QTabWidget`.

```
ACERVATOR_VARIANT unset
bar: ['Sim', 'Paper', 'Live', 'Charts', 'Inspector', 'Swarm',
      'Accumulation', 'History', 'Status', 'Console']
paper widget: PaperTraderTabReact
index of Paper: 1

ACERVATOR_VARIANT=qt
bar: ['Sim', 'Paper', 'Live', 'Charts', 'Inspector', 'Swarm',
      'Accumulation', 'History', 'Status', 'Console']
paper widget: PaperTraderTabQt
constructed_tabs: ['Live', 'Sim', 'Paper', 'Charts', 'Swarm', 'Inspector',
                   'History', 'Console', 'Status', 'Accumulation']
```

## A fleet is present and the live feed arrives

`PaperTraderTabQt` was built, Import Live Fleet pressed, then Start Paper Run.

```
accessible Paper fleet rows 0
import -> 38 rows now 38
symbol ADA/USDC indicator summary ▲ 3  ▼ 5  ─ 4
feed pane: ADA-USDC 5m — 100 candles, newest close $0.22
start -> started state started
balance rows 1 run lines 1 of 38 bots opened a fake balance, $50.00 of paper budget.
tick again -> 1 balances 2
stop -> stopped button now Start Paper Run
```

38 bots came from `bot_state.json`. 100 candles came from the venue's public
market endpoint. The Indicator Voting Panel reports twelve voters over that
window.

## The React page draws the same values

The page was loaded, the same two presses run, and the document read back.

```
page_ready True
import -> 38
start -> started state started
DOM: {"symbol":"ADA/USDC","built":"true","fleetRows":"38","balanceRows":"1",
      "runState":"started","indicators":"▲ 1  ▼ 5  ─ 6","markets":38,
      "stopButton":"Stop Paper Run",
      "feed":"ADA-USDC 5m — 100 candles, newest close $0.22"}
```

The two runs are minutes apart, so the vote counts differ; the market moved
between them. Every other value matches the Qt reading.

## The feed refuses a send

Two-sided. A read name answers; seven send names raise.

```
READ_NAMES ('venue', 'product_id', 'granularity', 'candles', 'ticker', 'asked_at')
venue -> coinbase
create_order  -> refused
cancel_order  -> refused
place_order   -> refused
edit_order    -> refused
post          -> refused
withdraw      -> refused
set_leverage  -> refused
```

## The starting balance, and where the rule comes from

`docs/manual/08-tabs.md` states it, and `docs/manual/08-tabs/paper-trader.md`
repeats it: the paper budget is twice the dollar target. The measured opening
for a bot whose stored `target_balance` is 25.00:

```
balances {'ff6a37a3': (114.74205985, 25.0, 50.0)}
          units          cash_usd  budget_usd
```

Budget 50.00, position worth 25.00, cash 25.00. No number invented.

## Where the gate chain comes from

`src/paper/paper_run.py` imports `tape_context` and `latch` and defines no gate.
`latch` runs `build_scrumming_scrum_chain` and `build_scrumming_fold_chain` from
`src.trading.gate_chain`, unchanged.

```python
context = tape_context(bot, balance, window, reading, summary)
armed = latch(context)
```

The candles-to-`GateContext` translation lives in `src/simulator/back_test.py`.
Paper imports it rather than writing a second copy. Its natural home is beside
`src.trading.gate_chain`; moving it would change a live trading file and belongs
to a unit of its own.

## What the manual still says that is now stale

Two sentences and one code block in `docs/manual/08-tabs.md` describe the Paper
tab as a skeleton, and `docs/manual/08-tabs/paper-trader.md` says Paper sits
behind two gates. No sentence was reworded; the current state was added below
them.

`src/gui/stock_main_window.py` imports `PaperTraderTab` from
`src.gui.paper_trader_tab`. The module now exists and that name does not, so the
shelved stock window still logs its warning and adds no tab.
