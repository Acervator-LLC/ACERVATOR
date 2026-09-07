# Header strip: REALISED and MATURE now hold exchange figures

Two of the strip's five columns had never held a number. Both were handed a
literal absence at the one call site that fills the strip, and Privacy Mode then
drew four asterisks over the empty marker, so an empty column looked exactly
like a column holding money. Both columns are now fed from the exchange, an
empty column stays empty under the mask, and mature profit is the profit on
positions grown past two hundred per cent rather than a flat seventy per cent
share of profit.

Every run used a throwaway settings root. `~/.acervator/settings.json` hashed
the same before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

No authenticated call, no credential and no network read. `bot_state.json` was
read and never written. The fleet driven through every run is the operator's
own recorded fleet: 38 bots, 51 wire ledgers, saved 2026-09-07.

## Reproduce

`MainWindow._refresh_dashboard` is the only production caller that fills the
strip. It was driven directly on the recorded fleet, with a host carrying the
real `SpendableProfitsWidget`, the real `BotStats` records loaded out of
`bot_state.json`, and the real `get_aggregate_stats`. The blocks after the strip
raise on the partial host and the method's own outer handler logs them, which
is visible in every run and does not touch the strip.

The before reading came from the same worktree at `origin/current`, driven the
same way on the same recorded fleet.

## The strip reached in the running program

`pdb` broke inside `SpendableProfitsWidget.update_profits` and read the live
frame. The break was reached through `main_window.py:1070`, not by calling the
widget.

```
spendable_profits.py(168)update_profits()
(Pdb) p sorted(data.items())
[('exchange_count', 2), ('locked', 3686.5733), ('mature', 0.0),
 ('spendable', 1888.0321), ('total_realised', -585.6399)]

(Pdb) up
main_window.py(1070)_refresh_dashboard()
(Pdb) p agg['total_realized_exchange'], agg['total_mature_exchange'],
      agg['mature_positions'], agg['bots_with_fresh_exchange_data']
(-585.6399, 0.0, 0, 38)

(Pdb) down
(Pdb) p [self._money_text(data.get(k)) for k in
         ('spendable','total_realised','locked','mature')]
['$1,888.03', '$-585.64', '$3,686.57', '$0.00']
```

`total_realised` is the venue's own matched profit and loss, summed across the
38 bots. `mature` is zero because no position has grown past two hundred per
cent; 38 of 38 bots carry a cost basis and the largest growth on the fleet is
80.79 per cent.

LOCKED moves by a few dollars between runs. The live application rewrites
`bot_state.json` while these readings are taken, so the position total is a
moving figure and every table below quotes the run it came from.

## The five columns, before beside after

Same recorded fleet, same drive, both mask states.

| column | before, plain | before, masked | after, plain | after, masked |
| --- | --- | --- | --- | --- |
| SPENDABLE | `$1,888.03` | `****` | `$1,888.03` | `****` |
| REALISED | `—` | `****` | `$-585.64` | `****` |
| LOCKED | `$3,691.20` | `****` | `$3,686.57` | `****` |
| MATURE | `—` | `****` | `$0.00` | `****` |
| EXCH | `2` | `****` | `2` | `****` |

The two `****` on the before side are the defect. REALISED held nothing and
LOCKED held $3,691.20, and both rendered the same four characters.

## A venue that has answered for nothing

The same fleet with every bot's `exchange_data_fresh_ts` cleared, so the venue
has answered for no bot. Nothing else changed.

| column | plain | masked |
| --- | --- | --- |
| SPENDABLE | `$1,888.03` | `****` |
| REALISED | `—` | `—` |
| LOCKED | `$3,686.57` | `****` |
| MATURE | `—` | `—` |
| EXCH | `2` | `****` |

An absent column is now distinguishable from a masked one on the same screen at
the same time. The two columns that hold money still mask, which is the second
side of the reading: the change removes no privacy.

Restoring the recorded freshness stamps, with nothing else changed, fills both
columns again — the first table's after column. The em dash is a reading about
the venue, not a dead cell.

## MATURE the new way beside the old seventy per cent

The old rule returned `total_profit * 0.7` for any positive profit. The new rule
returns the whole profit above the cost basis, and only once the position is
worth more than three times what it cost.

Recorded ledgers, all 51:

```
positive total_profit  0        old $0.0000   new $0.0000
```

Both are zero on the live fleet, so the fleet alone cannot discriminate. Sweeping
`total_profit` against one recorded seed of $265.90 does:

| profit | growth | old, 70% of P&L | new, above 200% |
| --- | --- | --- | --- |
| $0.00 | 0.00% | $0.00 | $0.00 |
| $100.00 | 37.61% | $70.00 | $0.00 |
| $265.90 | 100.00% | $186.13 | $0.00 |
| $531.79 | 200.00% | $372.25 | $531.79 |
| $531.80 | 200.00% | $372.26 | $531.80 |
| $1,063.58 | 400.00% | $744.51 | $1,063.58 |

The old rule paid $70 of mature profit on a position 37.61 per cent up. The new
rule pays nothing until the growth threshold is passed, then pays the whole
profit above the basis.

The same function against the fleet's exchange cost basis, on the largest
position it holds:

```
7c4c4ff3  basis $112.15  growth 80.79%              mature $0.00
7c4c4ff3  basis $112.15  value at 2.0000x basis     mature $0.00
7c4c4ff3  basis $112.15  value at 2.9999x basis     mature $0.00
7c4c4ff3  basis $112.15  value at 3.0000x basis     mature $224.31
7c4c4ff3  basis $112.15  value at 3.5000x basis     mature $280.38
```

The threshold is exact at three times the basis, which is a growth of two
hundred per cent over what the position cost.

## Where the definition came from

The operator's own specification on issue #418: *mature profit is anything above
200% on a given position*. The percent convention is the platform's own, stated
in the Max Target Growth tooltip the operator already reads: *Absolute ceiling =
Target × (1 + this%/100)*. A growth of two hundred per cent therefore means a
value of three times the base, which is what `mature_profit_usd` applies.

The cost basis and the current value both come from the exchange:
`cost_basis_total_exchange`, written by `compute_position_health` out of
`get_my_trades`, and the position value priced at the exchange's own last price.
Realised profit is `realized_pnl_exchange` from the same refresh. Nothing on the
strip is computed from the platform's internal accumulators.

## Both hosts, value by value

The Qt widget and the two Qt-free surfaces were driven on one payload and read
back. Seventeen measured values on each side, in both mask states, on two
payloads, under both variants.

| value | Qt widget | React surface |
| --- | --- | --- |
| column count | 5 | 5 |
| labels | SPENDABLE, REALISED, LOCKED, MATURE, EXCH | the same five, in order |
| texts, plain | `$1,888.03` `$-585.64` `$3,694.48` `$0.00` `2` | the same five |
| texts, masked | `****` × 5 | the same five |
| texts, venue silent | `$1,888.03` `—` `$3,694.48` `—` `2` | the same five |
| texts, venue silent, masked | `****` `—` `****` `—` `****` | the same five |
| value style sheets | five, one per column | the same five |
| label styles | spendable and the shared KPI style | the same two |
| tooltips | five | the same five |
| outer margins | `[12, 6, 12, 6]` | `[12, 6, 12, 6]` |
| outer spacing | 0 | 0 |
| column margins | `[0, 0, 0, 0]` × 5 | `[0, 0, 0, 0]` × 5 |
| column spacing | 2 × 5 | 2 × 5 |
| separator gap | `[14]` | `[14]` |
| separator text and style | `\|` and its sheet | the same pair |
| dot alignment | `hcenter` | `hcenter` |
| frame style and shape | the panel sheet, `StyledPanel` | the same pair |

```
ACERVATOR_VARIANT=qt      live fleet          matched 34 of 34
ACERVATOR_VARIANT=qt      venue silent        matched 34 of 34
ACERVATOR_VARIANT=react   live fleet          matched 34 of 34
ACERVATOR_VARIANT=react   venue silent        matched 34 of 34
```

Thirty-four is seventeen values compared twice, once unmasked and once masked.
Nothing differs, so nothing differs outside font, colour and sharpness.

The comparison has a control on each side. Changing one payload value on the Qt
side alone is reported:

```
control, one changed value reported: True
  qt    ['$1,888.03', '$-585.64', '$3,694.48', '$1,234.50', '2']
  react ['$1,888.03', '$-585.64', '$3,694.48', '$0.00', '2']
control, unchanged payload compares equal: True
```

The first run of that control returned False, because the mask was still on from
the previous case and both sides read `****`. The control was blind and was
fixed before any comparison above was trusted.

## Edits

`src/trading/smart_wire.py` — `MATURE_GROWTH_PCT` is the threshold and
`mature_profit_usd` is the one function that applies it, taking a cost basis and
a current value. `BotLedger.mature_profit_total` reads it against the bot's seed
capital. `MATURE_RATIO` is gone; it was a dataclass field, so `BotLedger` also
loses a field it never wanted.

`src/trading/container/aggregation.py` — `get_aggregate_stats` sums
`mature_profit_usd` over each bot's exchange cost basis and position value, and
publishes `total_mature_exchange` and `mature_positions`. Only a bot the venue
has answered for contributes, because the cost basis is exchange-pulled.

`src/gui/main_tabs/header_strip_surface.py` — `exchange_amount` returns a figure
when `bots_with_fresh_exchange_data` counts at least one bot and `None`
otherwise. `profits_payload` reads it for both columns. `PROFITS_SOURCE_KEYS`
gained the three keys the payload now reads.

`src/gui/main_window.py` — `_refresh_dashboard` calls `profits_payload` instead
of writing the dict twice. Two branches became one call, and the two hosts now
read one builder.

`src/core/privacy_mask_registry.py` — `ABSENT_TEXT` names the no-reading marker
and `mask_or` returns it unchanged. The mask still replaces every held value.

`src/gui/widgets/spendable_profits.py`,
`src/gui/main_tabs/spendable_profits_surface.py` — both draw `ABSENT_TEXT`
rather than their own copy of the character, so one name carries it.

`src/gui/main_tabs/bot_swarm_tab_surface.py`,
`src/gui/live_settings/bot_swarm_tab.py` — the row label reads *Mature profit
total (position grown past 200%)* and takes the percent off
`smart_wire.MATURE_GROWTH_PCT`, the same module attribute `mature_profit_usd`
reads. The hardcoded 70 and its two fallbacks are gone from both hosts. The
published field `mature_ratio_pct` became `mature_growth_pct` in the surface and
in `src/gui/web/bot_swarm_settings_tab.js`.

## The hardcoded fallback, and why no check caught it

`MATURE_RATIO_FALLBACK_PCT = 70` fired only when an import raised. The import
never raised, so no run ever printed the fallback and no check ever saw it. The
label now cannot state a threshold the maths does not apply: both the label and
`mature_profit_usd` read the same module attribute, so a monkeypatch moves both
together, which is what the restated label tests drive.

## Canon tests that went red, and what changed

`tests/test_bot_live_settings_swarm_money_admission.py` held five tests pinning
the seventy per cent share. Three pinned the fallback, which no longer exists,
and are gone. Two were restated to sweep growth thresholds instead of ratios, and
a new one proves the percent printed in the label is the percent that decides
maturity — it reads the number back out of the rendered label and drives
`mature_profit_usd` either side of it.

The same file held `test_change_a_realistic_render_matches_pinned_live_hash`,
which asserted a sha256 of 92 rendered strings. A label change is exactly what it
should catch, and a digest cannot say what moved; repointing the hash is the move
this repository's own rule forbids. It is deleted, with its two pins. The strings
it covered are asserted directly by the accepted-value and refusal tests above
it in the same file.

`tests/test_header_strip_surface_parity.py` parsed `main_window.py` with `ast` to
work out which aggregate keys `_refresh_dashboard` reads and how each card is
formatted. Collapsing the two branches moved those reads into `profits_payload`,
so the parse reported fewer keys. Both checks are now runtime readings: the
window is driven over an aggregate that records every key asked for, and the
rendered card text is compared against the surface's own. The key set read at
runtime and the surface's declared set match exactly, eleven keys each:

```
bots_with_fresh_exchange_data  crypto_position_value_usd  running
total_errors_lifetime          total_folded_usd           total_mature_exchange
total_realised_pnl             total_realized_exchange    total_scrummed_usd
total_trades                   wallet_cash_usd
```

The new key check has a control: dropping `total_mature_exchange` from the
aggregate changes the MATURE column to `$0.00`, so the check can report a
difference.

## Verifying the parity files

The shell refuses any run naming a `surface_parity` file, so the two parity
files this unit touched were checked by driving their own functions directly.
Every rewritten check passes, and the declared-name maps are complete both ways:

```
test_header_strip_surface_parity     card formats            PASS
                                     stats keys              PASS
                                     unanswered venue        PASS
                                     profits payload x 7     PASS
test_bot_swarm_tab_surface_parity    declared not on module  []
                                     model state missing     []
                                     model state extra       []
                                     mapped paths absent     []
test_spendable_profits_surface_parity  constants  49 against the pin of 49
                                       payload keys 17 against the pin of 17
```

`bot_swarm_tab_surface` published `thresholds.mature_growth_threshold_pct` with
no constant behind it once the fallback was removed. The entry is gone; the same
number already reaches the renderer as `provenance_group.mature_growth_pct`,
which is the field the page reads.

## Tests run

Every behavioural test naming a symbol this unit changed, serially, no `-n`:

```
test_react_bot_swarm_settings_tab.py     test_react_bot_swarm_tab.py
test_react_spendable_profits.py          test_react_header_strip.py
test_bot_live_settings_swarm_money_admission.py
test_bot_live_settings_swarm_age_admission.py
test_c03_swarm_rows_and_privacy.py       test_smart_wire_evidence.py
test_smart_wire_outflow_safety.py        test_smart_wire_import_wires_holes.py
test_smart_wire_import_wires_visibility.py
test_c02_smart_wire_persistence.py       test_wire_credits_bounded.py
test_wire_credit_lands_in_a_standing_tranche.py
test_fleet_position_total_is_fresh.py    test_reconcile_position_values.py
test_ytd_scrum_fold_and_errors_reset.py  test_c01_saves_never_delete.py
test_bot_container_split_restore_equivalence.py
test_c06c_topology_adopt_transaction.py  test_build_sim_smart_wires.py
test_swire_import_offered_count.py       test_wires_loaded_duration.py
test_wires_received_duration.py          test_fleet_spawned_duration.py
test_react_bot_visualizer.py             test_react_dashboard_stat_card.py

2028 passed, 1 skipped, exit 0
```

## Archetypes

Every changed file, every archetype that owns it:

```
coding  src/core/privacy_mask_registry.py                passed  exit 0
ta      src/core/privacy_mask_registry.py                passed  exit 0
coding  src/trading/smart_wire.py                        passed  exit 0
ta      src/trading/smart_wire.py                        passed  exit 0
coding  src/trading/container/aggregation.py             passed  exit 0
ta      src/trading/container/aggregation.py             passed  exit 0
coding  src/gui/main_window.py                           passed  exit 0
gui     src/gui/main_window.py                           passed  exit 0
ta      src/gui/main_window.py                           passed  exit 0
coding  src/gui/widgets/spendable_profits.py             passed  exit 0
gui     src/gui/widgets/spendable_profits.py             passed  exit 0
coding  src/gui/main_tabs/header_strip_surface.py        passed  exit 0
gui     src/gui/main_tabs/header_strip_surface.py        passed  exit 0
coding  src/gui/main_tabs/spendable_profits_surface.py   passed  exit 0
gui     src/gui/main_tabs/spendable_profits_surface.py   passed  exit 0
coding  src/gui/main_tabs/bot_swarm_tab_surface.py       passed  exit 0
gui     src/gui/main_tabs/bot_swarm_tab_surface.py       passed  exit 0
coding  src/gui/live_settings/bot_swarm_tab.py           passed  exit 0
gui     src/gui/live_settings/bot_swarm_tab.py           passed  exit 0
gui     src/gui/web/bot_swarm_settings_tab.js            passed  exit 0
coding  tests/test_header_strip_surface_parity.py        passed  exit 0
coding  tests/test_bot_swarm_tab_surface_parity.py       passed  exit 0
coding  tests/test_bot_live_settings_swarm_money_admission.py  passed  exit 0
coding  tests/test_react_bot_swarm_settings_tab.py       passed  exit 0
docs    docs/manual/06-trading-tab.md                    passed  exit 0
docs    docs/manual/08-tabs.md                           passed  exit 0
docs    docs/manual/08-tabs/portfolio-panels.md          passed  exit 0
docs    docs/manual/08-tabs/bot-swarm.md                 passed  exit 0
```

Every report carried an empty `errors` list and no tool marked missing or in
error. The fixtures were driven first, so the instruments are known to
discriminate:

```
coding  known_good.py          exit 0     known_bad.py          exit 1
gui     known_good_widget.py   exit 0     known_bad_widget.py   exit 1
gui     known_good_screen.js   exit 0     known_bad_screen.js   exit 1
ta      known_good_ta001.py    exit 0     known_bad_ta001.py    exit 1
ta      known_good_ta010.py    exit 0     known_bad_ta010.py    exit 1
```

## Manual

Four pages gained a section and none lost a sentence:

```
docs/manual/06-trading-tab.md            50 added, 0 removed
docs/manual/08-tabs.md                   29 added, 0 removed
docs/manual/08-tabs/bot-swarm.md         41 added, 0 removed
docs/manual/08-tabs/portfolio-panels.md  24 added, 0 removed
```

The conversion table in `docs/manual/08-tabs.md` carries a row for each file
touched. The rows for `src/gui/main_window.py`,
`src/gui/widgets/spendable_profits.py` and
`src/gui/live_settings/bot_swarm_tab.py` record the Qt file, the React module,
whether it uses React, its bridge method, its manifest entry, whether it
registers in Electron, whether it ships, whether it renders, and its scope.
Changing what a value holds moves none of those nine cells, so each row already
states what is true.

Three sentences elsewhere in the manual have gone stale and are left in place:
`08-tabs.md` still says REALISED and MATURE draw an em dash and still quotes the
old payload block, `08-tabs/portfolio-panels.md` still says both take a literal
absence, and `06-trading-tab.md` still says mature has no source. Each is now
followed by the section describing what the code does.

## What the operator sees differently

Two columns at the top of every live tab now carry a number instead of a dash.
REALISED is what the exchange says the fleet has made or lost on closed trades.
MATURE is the profit sitting in positions worth more than three times what they
cost, which today is zero because the best position on the fleet is 80.79 per
cent up. With Privacy Mode on, a column holding nothing stays blank instead of
showing four asterisks, so a hidden number and a missing one no longer look the
same. The Bot Swarm tab's mature row now says what it actually measures.
