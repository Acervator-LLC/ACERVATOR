# Scrumming Bots table: Mode out, Current Position Value in

Column 2 of the Scrumming Bots table was `Mode`. The table skips any bot whose
mode is not `scrumming`, so every row it could draw read the same word. Column 2
is now Current Position Value, priced from the exchange. The state colour and
the mode-and-state tooltip moved to the Bot ID cell.

Every run used a throwaway home. `~/.acervator/settings.json` hashed the same
before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

No authenticated call, no credential and no network read. The shared price pool
was a real `MarketDataPool` holding recorded `TickerEntry` records.

## Reproduce

`surface.view_model` is the bridge handler the renderer calls. It was driven
with four recorded bot statuses, three scrumming and one extractor, against a
pool holding a two-second BTC/USD price, a forty-five-second SOL/USD price and
no ETH/USD entry at all.

```
BTC/USD   last 64,215.37   fetched 2s ago
SOL/USD   last 141.22      fetched 45s ago
ETH/USD   absent from the pool
```

The before reading came from a second worktree at `origin/current`, driven the
same way against the same recorded data.

## The cell reached in the running program

`pdb` broke inside `TableCellsModel.position_value_cell` and read the live
frame's arguments. The break fired three times in one paint, once per drawn row,
reached through `view_model` -> `update_bots` -> `_write_row`, not by calling
the helper.

```
table_cells_surface.py(429)position_value_cell()
-> self.calls.append([POSITION_START, holdings, cur_price, qrate, price_age_s])
('frame', 0.0182, 64215.37, 1.0, 2.004847288131714)
('frame', 0.41, 2450.0, 1.0, None)
('frame', 6.5, 141.22, 1.0, 45.0058958530426)
```

The second frame is the ETH bot. Its price is `2450.0`, the bot's own
`stats.current_price`, and its age is `None` because the pool held no entry. A
`None` age is what marks a price as not coming from the exchange.

## One bot's figure, and the Ammo cell on the same row

`bot-btc-usd-01`, BTC/USD, holdings `0.0182`, exchange price `64,215.37`, quote
rate `1.0`, price age `2.0s`.

```
position_value_cell text        $1,168.7197
position_value_cell value       1168.719734
ammo_cell position_val          1168.719734
equal                           True
ammo_cell text                  $31.2803          (1168.719734 - 1200.0)
stats.position_value on disk    1166.0            not shown, not used
```

Both cells read one function, `priced_position`, so the row cannot carry two
figures. The bot's own ledger value of `1166.0` reached neither cell.

## Before and after, same run, same data

| reading | before | after |
| --- | --- | --- |
| column 2 label | `Mode` | `Current Position Value` |
| column 2, `bot-btc-usd-01` | `scrumming` | `$1,168.7197` |
| column 2, `bot-eth-usd-02` | `scrumming` | blank |
| column 2, `bot-sol-usd-03` | `scrumming` | blank |
| column 0 colour, running | none set | `#00ff88` |
| column 0 colour, paused | none set | `#ffaa00` |
| column 0 tooltip | none | `Mode: scrumming` / `State: RUNNING` |
| Ammo, the three rows | `$31.2803`, `$4.5000`, `$17.9300 (stale)` | unchanged |
| row count | 4 | 4 |
| bot ids | the four, in order | the four, in order |
| skipped rows | `[3]` | `[3]` |
| privacy field, column 2 | `bot_table.mode` | `bot_table.ammo` |

The row set is the second line of proof for the skip. Row 3 is the extractor
bot; it was skipped before the change and after it, and the warning line naming
it appeared in both runs.

## A blank cell, and the same cell filled

`bot-eth-usd-02` holds `0.41` units and the pool held no ETH/USD entry, so the
cell was blank:

```
text     ""
tooltip  No exchange price this tick. Blank rather than the bot's own last
         reading, which is not a current value.
```

Adding one recorded ETH/USD entry to the pool and repainting, with nothing else
changed:

```
text     $1,009.0428
tooltip  Current position value from the exchange: 0.410000 units at
         $2,461.0800, priced 3s ago.
```

The blank is a reading about the price, not a dead cell.

`bot-sol-usd-03` is the other blank. The pool held a price forty-five seconds
old, past the twenty-second limit the surface already uses, so the cell stayed
blank and said so:

```
tooltip  Exchange price is 45s old, past the 20s limit. Blank rather than a
         figure priced off it.
```

## Both hosts

The Qt table and the React module were each driven on the same payload and read
back.

| value | Qt widget | React module |
| --- | --- | --- |
| column 2 label | `Current Position Value` | `Current Position Value` |
| column 2 text, row 0 | `$1,168.7197` | `$1,168.7197` |
| column 2 text, rows 1 and 2 | blank | blank |
| column 2 tooltip, row 0 | the priced tooltip | the same string |
| column 0 colour, rows 0-2 | `#00ff88`, `#ffaa00`, `#00ff88` | the same three |
| alignment value | 132 | 132 |
| fixed width, Fire | 70 | 70 |
| fixed width, Detail | 60 | 60 |
| icon size | 18 | 18 |
| button height | 22 | 22 |
| glow blur radius | 18 | 18 |
| row count | 4 | 4 |
| skipped rows | `[3]` | `[3]` |

Column 2 stretches; only columns 8 and 9 carry a declared width, and both are
unchanged. Labels, tooltips, privacy fields, fixed widths and state colours
compared equal between the Qt spec and the surface constants, before the change
and after it.

The React module reported no faults on the payload, holding 119 of 119 declared
fields. Cutting `bot_id_column` and `position_value_column` out of the payload
made it report both as missing and hold 117 of 119, so its silence on the real
payload is a reading and not an absence.

## Edits

`src/gui/main_tabs/table_cells_surface.py` — `priced_position` is the one
multiplication both priced cells read. `position_value_cell` composes the new
cell on five paths: `priced`, and four that return an empty text with the
reason in the tooltip — `holdings_absent`, `price_absent`, `off_exchange` and
`aged`. `ammo_cell` now reads `priced_position` for its own fresh value.

`src/gui/main_tabs/bot_status_table_surface.py` — `COLUMN_LABELS[2]` is
`Current Position Value` and `COLUMN_TOOLTIPS[2]` names what the number is,
that it comes from the exchange and what a blank cell means.
`COLUMN_TOOLTIPS[0]` gained the six state colours. `MODE_COLUMN` became
`POSITION_VALUE_COLUMN` and `BOT_ID_COLUMN` was added. `_price_reading` reads
the pool once per row and hands one price to both cells, so `_ammo_cell` no
longer fetches its own. `PRIVACY_FIELD_BY_COL[2]` is `bot_table.ammo`, the same
mask the Ammo cell carries, because both cells draw the same quantity.

`src/gui/widgets/bot_status_table.py` — the same label, the same two tooltips,
the same privacy field. `_compose_position_value_cell` fills column 2 and the
state colour and mode tooltip moved from column 2 to column 0.

`src/gui/table_cells.py` — `_priced_position` and
`_compose_position_value_cell`, the Qt-side pair, and `_compose_ammo_cell` reads
`_priced_position`.

`src/gui/web/bot_status_table.js` — the `mode_column` field became
`position_value_column`, `bot_id_column` was added, and the state-colour type
check moved from column 2 to column 0. `position_blank_text` and
`position_paths` were added to the declared fields.

## Not changed, and why

The `mode != "scrumming"` skip is untouched in both hosts. It is what chooses
the rows, and the row set proved identical either side of the change.

The conversion table row for `src/gui/widgets/bot_status_table.py` in
`docs/manual/08-tabs.md` records the Qt file, the React module, and whether it
uses React, has a bridge method, has a manifest entry, registers in Electron,
ships and renders. A column rename changes none of those nine cells, so the row
already states what is true.

`docs/manual/06-trading-tab.md` still carries the sentence describing Mode as
the coloured cell, and both manual pages still quote a `SCRUMMING_COLUMNS` block
containing `"Mode"`. Both are stale. No manual sentence was deleted or reworded:
`git diff --numstat` reports 37 added and 0 removed on `06-trading-tab.md`, and
4 added and 0 removed on `08-tabs.md`.

`"bot_table.mode"` in `src/core/privacy_mask_registry.py` is now read by
nothing. Column 2 masks under `"bot_table.ammo"`, the same mask the Ammo cell
carries, because both cells draw one quantity and masking one and not the other
would defeat the mask. The registry entry stays: `ALL_FIELD_IDS` holds 19 ids
and `docs/manual/06-trading-tab.md` says Privacy Mode toggles eighteen masks, so
removing one would land on the operator's number by accident. The mismatch is
older than this change, which added no id.

`table_cells.state` publishes nothing about the new cell, and the `CELLS`
registry that drives `table_cells.js` is untouched. Both name what that module
draws itself, which is the Ammo cell and the two Target-denom cells. Column 2 is
drawn by `bot_status_table.js` like every other plain cell in the table, and the
column's own payload carries `position_value_column`, `bot_id_column`,
`position_blank_text` and `position_paths`.

Publishing the cell on `table_cells.state` was tried first and reverted.
`tests/test_react_table_cells.py` reported four failures, because
`table_cells.js` must name every field that surface publishes and it named none
of the six. The module is not one of this table's two hosts, so the fields came
out rather than the module gaining them.

## The canon tests that ran red, and the defect they found

`tests/test_react_bot_status_table.py` failed collection on
`bsts.MODE_COLUMN`, which no longer exists. It pins that the module rejects a
numeric colour on the cell type-checked against `default_state_color`. That
cell is now column 0, so the case reads `bsts.BOT_ID_COLUMN` and is named for
the Bot ID cell. Same invariant, on the cell that now carries it.

The same file then reported a real defect in the first naming:

```
bot_status_table.js spells out table values: ['no_holdings', 'no_price']
```

`POSITION_PATHS` had named two paths `no_holdings` and `no_price`, and those
two strings are already payload field names the module spells for `NO_HOLDINGS`
and `NO_PRICE`. One string would have meant two different things. The paths are
now `holdings_absent` and `price_absent`, in both hosts. The test was right and
the code changed.

`tests/test_columnar_table_contract.py` pins the Qt table's header labels and
widths against a literal, structurally and as a rendered picture.
`SCRUMMING_HEADERS[2]` now reads `● Current Position Value` and the column 0
tooltip expectation now carries the six state colours. `SCRUMMING_FIXED` is
unchanged at `((8, 70), (9, 60))`.

`tests/test_bot_status_table_surface_parity.py` names the published fields
exhaustively. `mode_column` came out and `bot_id_column`,
`position_value_column`, `position_blank_text` and `position_paths` went in.
Three cell-press cases named `surface.MODE_COLUMN`; they press column 2 to prove
a non-Symbol column opens no chart, and they now name
`surface.POSITION_VALUE_COLUMN`. Same column index, same invariant.

That file cannot be run here — the shell refuses a run naming a parity file, so
its edit was checked by reading the running surface instead. The declared key
set and the published key set were compared directly and match both ways, and
the four names the map now resolves all exist:

```
payload keys not in the map   []
map keys not in the payload   []
BOT_ID_COLUMN = 0             POSITION_VALUE_COLUMN = 2
POSITION_BLANK_TEXT = ""      POSITION_PATHS = ('priced', 'holdings_absent',
                                                'price_absent',
                                                'off_exchange', 'aged')
MODE_COLUMN no longer exists on the surface
```

## Tests run

Every consumer of the four changed modules, run serially, no `-n`:

```
test_react_bot_status_table.py     test_react_table_cells.py
test_columnar_table_contract.py    test_c10_dashboard_ammo_truth.py
test_ammo_display_freshness.py     test_target_delta_display.py
test_ammo_matches_manual_fire_target.py
test_react_shared_widgets.py       test_react_exchange_tab.py
test_exchange_tab_emitters.py      test_bridge_pushes_unprompted.py
test_target_bands_have_one_spelling.py

1019 passed, exit 0
```

## Archetypes

```
coding_archetype  table_cells_surface.py        passed  exit 0
coding_archetype  bot_status_table_surface.py   passed  exit 0
coding_archetype  widgets/bot_status_table.py   passed  exit 0
coding_archetype  table_cells.py                passed  exit 0
gui_archetype     table_cells_surface.py        passed  exit 0
gui_archetype     bot_status_table_surface.py   passed  exit 0
gui_archetype     widgets/bot_status_table.py   passed  exit 0
gui_archetype     table_cells.py                passed  exit 0
gui_archetype     web/bot_status_table.js       passed  exit 0
docs_archetype    06-trading-tab.md             passed
docs_archetype    08-tabs.md                    passed
```

`coding_archetype` on `src/gui/web/bot_status_table.js` reports
`passed=false, scanned=false, unhandled=true` and states in its own output that
no analyzer ran, so that is not a verdict about the file. `gui_archetype`
carries the JavaScript analyzer and scanned it.

Both archetypes were run on their own known-good and known-bad fixtures first:

```
coding_archetype  known_good.py          exit 0
coding_archetype  known_bad.py           exit 1
gui_archetype     known_good_widget.py   exit 0
gui_archetype     known_bad_widget.py    exit 1
gui_archetype     known_good_screen.js   exit 0
gui_archetype     known_bad_screen.js    exit 1
```

## What the operator sees differently

The Scrumming Bots table drops a column that read `scrumming` on every row and
gains one that says what each bot's holdings are worth right now, at the
exchange's own price. Where the price is not fresh the cell is empty and says
why, so no figure on that column is ever older than twenty seconds. The state
colour he reads at a glance is still there, on the Bot ID cell.
