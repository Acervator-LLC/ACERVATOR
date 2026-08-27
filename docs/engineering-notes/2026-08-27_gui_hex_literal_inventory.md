# GUI hex-literal inventory and the token migration order

Issue #79 [DUP-09], unit 3a. Measured 2026-08-27 at commit `751a325`.

`src/gui/design_system.py` is the GUI token source of truth. This note
records every `#RRGGBB` and `#RGB` literal in `src/gui/*.py`, what token
already covered it, the tokens this unit added, and the order the
remaining files should be migrated in.

## Method

Literals are located with the Python tokenizer, not a line regex. A match
inside a STRING token is a rendered colour; a match inside a COMMENT or a
docstring is prose. `#RGB` is expanded to `#RRGGBB` and case-folded before
grouping.

The distinction is load-bearing. `#133`, `#128`, `#106`, `#105` and `#103`
are GitHub issue references written in comments; a line regex counts them
as three-digit colours. They are 34 of the 1,195 raw matches.

| set | count |
|---|---|
| raw `#` matches in `src/gui/*.py` | 1,195 |
| in a COMMENT token | 60 |
| in a docstring | 14 |
| rendered (STRING token) | 1,121 |
| rendered, excluding `design_system.py` and `theme_engine.py` | 967 |
| distinct rendered colours in widget code | 190 |

## Distribution

| uses | distinct colours | share of the 190 |
|---|---|---|
| 1 | 106 | 56% |
| 2 | 18 | 9% |
| 3 | 16 | 8% |
| 4 to 9 | 32 | 17% |
| 10 to 30 | 13 | 7% |
| 41 to 100 | 5 | 3% |

Six colours cover 378 of the 967 literals, 39%. The 106 single-use
colours cover 106, 11%. The head is a token set; the tail is where a
colour used once may simply be a mistake.

## The headline finding: two tokens were WCAG-corrected and no widget followed

`design_system.py` and `theme_engine.py` both record a value that was
changed to clear WCAG AA. Neither change reached a widget.

| token | value | comment in source | value the widgets render | rendered count |
|---|---|---|---|---|
| `DANGER` | `#ff5577` | "adjusted from `#ff3366` to clear WCAG AA" | `#ff3366` | 97 vs 1 |
| `INFO` | `#4fc3ff` | "adjusted from `#00aaff` to clear WCAG AA" | `#00aaff` | 25 vs 0 |

`#ff3366` is the most-used colour in the GUI. `#4fc3ff` is rendered
nowhere. The accessibility fix was made in the token module and the read
path was never migrated, so the screen never changed. This unit does NOT
repaint them: it adds `ERROR = "#ff3366"` and `STATUS_INFO = "#00aaff"`
for what the widgets actually draw, and leaves `DANGER` and `INFO` at
their corrected values. Deciding whether the GUI adopts the corrected
reds and blues is a product call.

## `theme_engine.py` versus `design_system.py`

`theme_engine.py:20-27` names `design_system.py` as canonical. Comparing
`CYBERPUNK_DARK` defaults against the design-system role of the same
name, 14 of 22 roles agree and 8 disagree.

| theme_engine | value | design_system | value | delta |
|---|---|---|---|---|
| `text_secondary` | `#8888aa` | `TEXT_MED` | `#a8a8c5` | 52.7 |
| `border_secondary` | `#5e5e80` | `OUTLINE_STRONG` | `#a0a0c0` | 113.2 |
| `bg_card` | `#16162a` | `SURFACE_1` | `#141420` | 10.4 |
| `bg_input` | `#0e0e1a` | `SURFACE_1` | `#141420` | 10.4 |
| `bg_hover` | `#1e1e35` | `SURFACE_3` | `#22223a` | 7.5 |
| `bg_selected` | `#252545` | `SURFACE_4` | `#2a2a44` | 7.1 |
| `bg_secondary` | `#12121a` | `SURFACE_1` | `#141420` | 6.6 |
| `scrollbar_bg` | `#0a0a14` | `SURFACE_0` | `#0a0a0f` | 5.0 |

`border_secondary` is the widest: the two modules disagree by 113 units
on the same role. `theme_engine.border_accent` (`#00ffcc44`) has no
design-system counterpart.

None of these are changed here. `theme_engine.py` is a token module, not
widget code; its literals ARE definitions.

## Near-miss token pairs -- reported, not collapsed

After this unit's additions the token set holds 84 pairs within an RGB
distance of 12, and 26 pairs within 6. A migration is a rename, so every
one of these is left exactly as it is. Collapsing two colours three units
apart changes what the operator sees and is his decision, not a
refactor's.

The pairs within 6. Use counts are the tree as it stands after this
unit, so `analytics_tab.py` is already migrated:

| delta (r,g,b) | token A | uses | token B | uses |
|---|---|---|---|---|
| 4.4 (-3, -3, 1) | `VIZ_SWARM_SURFACE` `#070710` | 6 in bot_visualizer.py, screen_recorder.py | `SURFACE_0` `BG` `#0a0a0f` | 1 in tradingview_chart.py |
| 4.7 (-3, -3, -2) | `VIZ_SWARM_SURFACE` `#070710` | 6 in bot_visualizer.py, screen_recorder.py | `SURFACE_CHART` `#0a0a12` | 19 in alerts_tab.py, bot_live_settings.py, journal_tab.py +5 |
| 5.8 (-3, -3, -4) | `VIZ_SWARM_SURFACE` `#070710` | 6 in bot_visualizer.py, screen_recorder.py | `SURFACE_CONSOLE_HEADER` `#0a0a14` | 3 in launcher.py, main_window.py, usb_auth_widget.py |
| 4.9 (-2, 2, 4) | `CARD_STOCK_LOG_SURFACE` `#080c18` | 3 in stock_main_window.py | `SURFACE_CONSOLE_HEADER` `#0a0a14` | 3 in launcher.py, main_window.py, usb_auth_widget.py |
| 2.8 (-2, 2, 0) | `CARD_STOCK_LOG_SURFACE` `#080c18` | 3 in stock_main_window.py | `VIZ_LIST_SURFACE` `#0a0a18` | 3 in bot_visualizer.py, competition_tab.py |
| 4.5 (-4, 0, -2) | `CARD_STOCK_LOG_SURFACE` `#080c18` | 3 in stock_main_window.py | `VIZ_PANEL_SURFACE` `#0c0c1a` | 12 in bot_visualizer.py |
| 3.0 (0, 0, -3) | `SURFACE_0` `BG` `#0a0a0f` | 1 in tradingview_chart.py | `SURFACE_CHART` `#0a0a12` | 19 in alerts_tab.py, bot_live_settings.py, journal_tab.py +5 |
| 5.0 (0, 0, -5) | `SURFACE_0` `BG` `#0a0a0f` | 1 in tradingview_chart.py | `SURFACE_CONSOLE_HEADER` `#0a0a14` | 3 in launcher.py, main_window.py, usb_auth_widget.py |
| 2.0 (0, 0, -2) | `SURFACE_CHART` `#0a0a12` | 19 in alerts_tab.py, bot_live_settings.py, journal_tab.py +5 | `SURFACE_CONSOLE_HEADER` `#0a0a14` | 3 in launcher.py, main_window.py, usb_auth_widget.py |
| 6.0 (0, 0, -6) | `SURFACE_CHART` `#0a0a12` | 19 in alerts_tab.py, bot_live_settings.py, journal_tab.py +5 | `VIZ_LIST_SURFACE` `#0a0a18` | 3 in bot_visualizer.py, competition_tab.py |
| 4.0 (0, 0, -4) | `SURFACE_CONSOLE_HEADER` `#0a0a14` | 3 in launcher.py, main_window.py, usb_auth_widget.py | `VIZ_LIST_SURFACE` `#0a0a18` | 3 in bot_visualizer.py, competition_tab.py |
| 3.5 (-2, -2, -2) | `VIZ_LIST_SURFACE` `#0a0a18` | 3 in bot_visualizer.py, competition_tab.py | `VIZ_PANEL_SURFACE` `#0c0c1a` | 12 in bot_visualizer.py |
| 6.0 (0, -6, 0) | `VIZ_TAB_SELECTED` `#0a0a20` | 6 in bot_visualizer.py, testnet_tab.py | `CARD_STOCK_PANEL` `#0a1020` | 7 in stock_main_window.py |
| 3.0 (-2, -2, 1) | `CARD_METRIC_SURFACE` `#12121f` | never rendered | `MAIN_TOOLBAR_SURFACE` `#14141e` | 2 in main_window.py, start_all_progress_dialog.py |
| 3.0 (-2, -2, -1) | `CARD_METRIC_SURFACE` `#12121f` | never rendered | `SURFACE_1` `CARD` `#141420` | never rendered |
| 2.0 (0, 0, -2) | `MAIN_TOOLBAR_SURFACE` `#14141e` | 2 in main_window.py, start_all_progress_dialog.py | `SURFACE_1` `CARD` `#141420` | never rendered |
| 2.0 (0, 0, -2) | `MAIN_BUTTON_SURFACE` `#1a1a26` | 3 in main_window.py, start_all_progress_dialog.py | `SURFACE_2` `#1a1a28` | 1 in tradingview_chart.py |
| 6.0 (0, 0, -6) | `SURFACE_2` `#1a1a28` | 1 in tradingview_chart.py | `SURFACE_CONTROL` `#1a1a2e` | 6 in bot_live_settings.py, main_window.py, risk_tab.py +1 |
| 1.0 (0, 0, -1) | `SURFACE_CONTROL` `#1a1a2e` | 6 in bot_live_settings.py, main_window.py, risk_tab.py +1 | `MENU_SURFACE` `#1a1a2f` | 4 in bot_visualizer.py, launcher.py |
| 5.0 (0, 0, -5) | `MAIN_TOGGLE_SURFACE` `#1a1a3a` | 2 in main_window.py | `VIZ_PANEL_BORDER` `#1a1a3f` | 14 in alerts_tab.py, bot_visualizer.py, journal_tab.py +2 |
| 5.0 (0, 0, -5) | `VIZ_LIST_BORDER` `#1a2a4a` | 3 in bot_visualizer.py, indicator_panel.py | `CARD_STOCK_BORDER` `#1a2a4f` | 7 in stock_main_window.py |
| 5.0 (0, 0, -5) | `MAIN_SEPARATOR` `#2a2a3a` | 4 in main_window.py, start_all_progress_dialog.py | `CARD_METRIC_BORDER` `#2a2a3f` | 17 in alerts_tab.py, bot_live_settings.py, bot_visualizer.py +2 |
| 5.0 (0, 0, -5) | `CARD_METRIC_BORDER` `#2a2a3f` | 17 in alerts_tab.py, bot_live_settings.py, bot_visualizer.py +2 | `SURFACE_4` `#2a2a44` | 2 in main_window.py, tradingview_chart.py |
| 4.2 (0, -3, 3) | `OUTLINE` `#7a7a9c` | never rendered | `MAIN_CAPTION` `#7a7d99` | 1 in main_window.py |
| 5.0 (0, 0, -5) | `TEXT_EMPTY_STATE` `#8a8aab` | 2 in bot_live_settings.py | `TEXT_LOW` `HINT` `#8a8ab0` | never rendered |
| 6.0 (0, -6, 0) | `WARNING` `#ffaa00` | 50 in alerts_tab.py, bot_live_settings.py, bot_swarm_list.py +9 | `MAIN_HIGHLIGHT_AMBER_TEXT` `#ffb000` | 1 in main_window.py |

`SURFACE_CONTROL` and `MENU_SURFACE` differ by one hex digit in one
channel and are both rendered. That pair is the most likely typo in the
set.

## Tokens added by this unit

106 tokens, all additive. No existing token value changed and no existing
name left `__all__`; `tests/test_design_system_token_values.py` pins each
new value to the literal it replaced.

The set was chosen to cover every untokened colour in the five files
issue #79 names, so the later units migrate one file each and none of
them needs to reopen `design_system.py`. Coverage turned out wider than
that: after the additions, 864 of the 945 remaining widget literals have
an exact token.

| section | tokens |
|---|---|
| Semantic roles the widgets actually render | 9 |
| Text roles beyond `TEXT_HIGH` / `MED` / `LOW` | 10 |
| Surfaces beyond `SURFACE_0..4` | 5 |
| Context menu | 3 |
| Control states | 7 |
| Tranche row skins, `bot_live_settings` | 6 |
| Settings dialog controls, `bot_live_settings` | 10 |
| Bot visualizer | 24 |
| Main window chrome | 20 |
| Stock window | 12 |

Six tokens take their name from a module-level constant that already
carried the role in widget code: `FOLD_RATIO_AMBER`, `FOLD_SOURCE_MANUAL`,
`FOLD_TRANCHE_SURFACE`, `FOLD_TRANCHE_BORDER`,
`EXTRACTOR_TRANCHE_SURFACE`, `EXTRACTOR_TRANCHE_BORDER`. Those constants
in `bot_live_settings.py` are the migration target for their file.

## Migration order for the remaining units

`analytics_tab.py` is migrated in this unit: 22 literals to 0.

Counts are rendered literals; "untokened" is what still has no exact
token after this unit.


### Phase 1 -- every literal already has a token

| file | literals | untokened |
|---|---|---|
| `main_window.py` | 183 | 0 |
| `bot_visualizer.py` | 159 | 0 |
| `bot_live_settings.py` | 156 | 0 |
| `stock_main_window.py` | 67 | 0 |
| `risk_tab.py` | 45 | 0 |
| `alerts_tab.py` | 37 | 0 |
| `start_all_progress_dialog.py` | 13 | 0 |
| `bot_swarm_list.py` | 6 | 0 |
| `init_wizard.py` | 6 | 0 |
| `audio_suite.py` | 4 | 0 |
| `bot_wizard.py` | 2 | 0 |
| `history_tab.py` | 1 | 0 |

Take them largest first. Each is a pure rename against the token set that
exists now. `main_window.py` and `bot_live_settings.py` are the two
largest files in the GUI and should each be a unit on their own.

### Phase 2 -- two to four new tokens each

| file | literals | untokened |
|---|---|---|
| `journal_tab.py` | 53 | 2 |
| `screen_recorder.py` | 29 | 3 |
| `settings_dialog.py` | 21 | 3 |
| `indicator_panel.py` | 20 | 3 |
| `launcher.py` | 14 | 4 |
| `market_inspector_topologies.py` | 11 | 2 |
| `market_inspector.py` | 10 | 4 |
| `buy_confirmation_dialog.py` | 3 | 2 |
| `live_bot_window.py` | 2 | 2 |
| `crypto_news_ticker.py` | 1 | 1 |

These need a small token addition each, so they cannot run in parallel
with each other against one `design_system.py`. Batch the 26 additions
into one shared-infrastructure step first, exactly as this unit did, then
migrate the files in parallel.

### Phase 3 -- do NOT migrate these as GUI chrome

| file | literals | distinct | untokened |
|---|---|---|---|
| `tradingview_chart.py` | 44 | 35 | 26 |
| `native_chart.py` | 11 | 11 | 8 |
| `usb_auth_widget.py` | 13 | 13 | 8 |
| `competition_tab.py` | 17 | 11 | 7 |
| `testnet_tab.py` | 17 | 11 | 6 |

`tradingview_chart.py` and `native_chart.py` have one use per distinct
colour: 35 colours for 44 literals, and 11 for 11. That is a chart series
palette, not GUI chrome, and tokenising it would add 34 names that are
each referenced once. `src/design_system.py` -- the light-theme sibling --
is where chart palettes live. Recommend a separate decision on a
dark-theme chart palette rather than folding these into the GUI token
set.

`usb_auth_widget.py` has the same 1:1 shape at smaller scale.
`competition_tab.py` and `testnet_tab.py` are migratable but need 13 new
tokens between them for colours used once or twice; they are the lowest
value in the issue.

`theme_engine.py` (119 literals) is NOT widget code and must not be
migrated. Its literals are theme definitions. Pointing them at
`design_system` would make one token module import the other and would
force the six role disagreements above to resolve, which is a product
decision.

## Colours that still have no token

72 distinct values, 81 literals, measured after this unit. All of them
sit inside the Phase 2 and Phase 3 files.

| value | uses | files |
|---|---|---|
| `#8899bb` | 4 | competition_tab.py, testnet_tab.py |
| `#ff3355` | 3 | competition_tab.py, testnet_tab.py |
| `#2a2a5f` | 2 | journal_tab.py |
| `#ffcc00` | 2 | market_inspector.py, native_chart.py |
| `#667799` | 2 | screen_recorder.py, usb_auth_widget.py |
| `#00ff00` | 2 | tradingview_chart.py |
| `#225522` | 1 | buy_confirmation_dialog.py |
| `#552222` | 1 | buy_confirmation_dialog.py |
| `#0a0a1c` | 1 | competition_tab.py |
| `#d8e8ff` | 1 | competition_tab.py |
| `#334455` | 1 | competition_tab.py |
| `#cfe6ff` | 1 | crypto_news_ticker.py |
| `#3344ff` | 1 | indicator_panel.py |
| `#00ffaa` | 1 | indicator_panel.py |
| `#ffb020` | 1 | indicator_panel.py |
| `#0e0e1a` | 1 | launcher.py |
| `#08080f` | 1 | launcher.py |
| `#08081a` | 1 | launcher.py |
| `#060612` | 1 | launcher.py |
| `#0e1420` | 1 | live_bot_window.py |
| `#c8d4e3` | 1 | live_bot_window.py |
| `#66cc99` | 1 | market_inspector.py |
| `#ff9966` | 1 | market_inspector.py |
| `#ffcc66` | 1 | market_inspector.py |
| `#ffb84d` | 1 | market_inspector_topologies.py |
| `#bb6666` | 1 | market_inspector_topologies.py |
| `#50a0f0` | 1 | native_chart.py |
| `#ff9060` | 1 | native_chart.py |
| `#c080ff` | 1 | native_chart.py |
| `#80ffcc` | 1 | native_chart.py |
| `#ff4488` | 1 | native_chart.py |
| `#ffa000` | 1 | native_chart.py |
| `#00b4ff` | 1 | native_chart.py |
| `#2a0008` | 1 | screen_recorder.py |
| `#1a0008` | 1 | screen_recorder.py |
| `#6699ff55` | 1 | settings_dialog.py |
| `#1a3a4a` | 1 | settings_dialog.py |
| `#00aacc` | 1 | settings_dialog.py |
| `#080818` | 1 | testnet_tab.py |
| `#c0d0e8` | 1 | testnet_tab.py |
| `#050510` | 1 | testnet_tab.py |
| `#26a69a` | 1 | tradingview_chart.py |
| `#12121a` | 1 | tradingview_chart.py |
| `#1e1e35` | 1 | tradingview_chart.py |
| `#f5f5fa` | 1 | tradingview_chart.py |
| `#e5e5f0` | 1 | tradingview_chart.py |
| `#ccccdd` | 1 | tradingview_chart.py |
| `#6600cc` | 1 | tradingview_chart.py |
| `#eeeef5` | 1 | tradingview_chart.py |
| `#0a0a0a` | 1 | tradingview_chart.py |
| `#181818` | 1 | tradingview_chart.py |
| `#003300` | 1 | tradingview_chart.py |
| `#111111` | 1 | tradingview_chart.py |
| `#fafafa` | 1 | tradingview_chart.py |
| `#e8e8e8` | 1 | tradingview_chart.py |
| `#e0e0e0` | 1 | tradingview_chart.py |
| `#2563eb` | 1 | tradingview_chart.py |
| `#f0f0f0` | 1 | tradingview_chart.py |
| `#eeeeee` | 1 | tradingview_chart.py |
| `#1c1c24` | 1 | tradingview_chart.py |
| `#d0d0e0` | 1 | tradingview_chart.py |
| `#2c2c3a` | 1 | tradingview_chart.py |
| `#3a3a50` | 1 | tradingview_chart.py |
| `#242430` | 1 | tradingview_chart.py |
| `#30303f` | 1 | tradingview_chart.py |
| `#0d0d20` | 1 | usb_auth_widget.py |
| `#4488ff` | 1 | usb_auth_widget.py |
| `#ffb800` | 1 | usb_auth_widget.py |
| `#ff4444` | 1 | usb_auth_widget.py |
| `#ff6666` | 1 | usb_auth_widget.py |
| `#333355` | 1 | usb_auth_widget.py |
| `#222244` | 1 | usb_auth_widget.py |

## What this unit did not do

- `analytics_tab.py:96-101` builds the equity-curve gradient from
  `QColor(0, 255, 136, 40)` and `QColor(255, 51, 102, 40)`. Those are
  `SUCCESS` and `ERROR` written as RGB tuples, not hex literals, so the
  migration left them. They will drift from the tokens beside them.
- `bot_live_settings.py:1604` writes `f"background: {...}22;"`, appending
  an alpha pair to a colour chosen at runtime. A token migration of that
  file has to keep the concatenation, not just the value.
- Qt reads an 8-digit stylesheet colour as `#AARRGGBB`.
  `design_system.GLOW_PRIMARY` is documented as "PRIMARY with 20% alpha",
  which reads the digits the other way round. `GLOW_PRIMARY_EDGE` and
  `GLOW_PRIMARY_FAINT` are added with their exact shipped strings and no
  claim about which end the alpha is on.

## Full colour table

Measured at `751a325`, before this unit migrated `analytics_tab.py`.
The token column is the set as it stands AFTER this unit.

| value | uses | token | files |
|---|---|---|---|
| `#ff3366` | 100 | `ERROR` | bot_live_settings.py x23, main_window.py x21, bot_visualizer.py x13, screen_recorder.py x11, +10 more |
| `#00ff88` | 92 | `SUCCESS` | bot_live_settings.py x22, bot_visualizer.py x21, main_window.py x14, screen_recorder.py x6, +14 more |
| `#888888` | 66 | `CARD_METRIC_LABEL` | journal_tab.py x18, main_window.py x15, bot_live_settings.py x11, stock_main_window.py x5, +11 more |
| `#ffaa00` | 51 | `WARNING` | main_window.py x19, screen_recorder.py x6, alerts_tab.py x5, risk_tab.py x5, +9 more |
| `#00ffcc` | 41 | `PRIMARY` | main_window.py x10, journal_tab.py x7, alerts_tab.py x6, risk_tab.py x6, +5 more |
| `#aaaaaa` | 28 | `TEXT_INACTIVE` | bot_live_settings.py x12, journal_tab.py x4, bot_visualizer.py x2, main_window.py x2, +5 more |
| `#00aaff` | 25 | `STATUS_INFO` | stock_main_window.py x9, risk_tab.py x4, alerts_tab.py x3, journal_tab.py x3, +5 more |
| `#e0e0f0` | 25 | `TEXT_HIGH`, `FG` | stock_main_window.py x6, main_window.py x5, risk_tab.py x5, bot_visualizer.py x2, +6 more |
| `#0a0a12` | 24 | `SURFACE_CHART` | alerts_tab.py x5, analytics_tab.py x5, journal_tab.py x4, risk_tab.py x4, +5 more |
| `#ff9900` | 21 | `FOLD_RATIO_AMBER` | bot_live_settings.py x20, main_window.py x1 |
| `#2a2a3f` | 20 | `CARD_METRIC_BORDER` | risk_tab.py x6, alerts_tab.py x4, analytics_tab.py x3, bot_live_settings.py x3, +2 more |
| `#00ffee` | 19 | `PRIMARY_BRIGHT` | bot_visualizer.py x13, competition_tab.py x2, bot_swarm_list.py x1, main_window.py x1, +2 more |
| `#666666` | 18 | `TEXT_MUTED` | bot_live_settings.py x7, main_window.py x4, indicator_panel.py x2, analytics_tab.py x1, +4 more |
| `#555555` | 17 | `TEXT_PLACEHOLDER` | main_window.py x8, bot_live_settings.py x3, alerts_tab.py x1, analytics_tab.py x1, +4 more |
| `#445566` | 15 | `VIZ_CAPTION` | bot_visualizer.py x13, competition_tab.py x1, testnet_tab.py x1 |
| `#1a1a3f` | 14 | `VIZ_PANEL_BORDER` | bot_visualizer.py x8, alerts_tab.py x2, journal_tab.py x2, screen_recorder.py x1, +1 more |
| `#0c0c1a` | 12 | `VIZ_PANEL_SURFACE` | bot_visualizer.py x12 |
| `#00ccff` | 11 | `FOLD_SOURCE_MANUAL` | bot_live_settings.py x6, audio_suite.py x2, bot_wizard.py x2, market_inspector.py x1 |
| `#a8a8c5` | 9 | `TEXT_MED`, `DIM` | main_window.py x6, bot_live_settings.py x3 |
| `#ffd700` | 9 | `ACCENT_GOLD` | bot_visualizer.py x9 |
| `#c0c0c0` | 8 | `TEXT_CONSOLE` | start_all_progress_dialog.py x4, main_window.py x3, journal_tab.py x1 |
| `#cccccc` | 8 | `TEXT_NEUTRAL` | main_window.py x4, bot_live_settings.py x3, market_inspector_topologies.py x1 |
| `#0a1020` | 7 | `CARD_STOCK_PANEL` | stock_main_window.py x7 |
| `#1a1a2e` | 7 | `SURFACE_CONTROL` | risk_tab.py x3, analytics_tab.py x1, bot_live_settings.py x1, main_window.py x1, +1 more |
| `#1a2a4f` | 7 | `CARD_STOCK_BORDER` | stock_main_window.py x7 |
| `#ffffff` | 7 | `TEXT_MAX` | main_window.py x4, bot_live_settings.py x2, indicator_panel.py x1 |
| `#001a0a` | 6 | `VIZ_GO_HOVER` | bot_visualizer.py x6 |
| `#00cc66` | 6 | `STOCK_POSITIVE` | stock_main_window.py x6 |
| `#070710` | 6 | `VIZ_SWARM_SURFACE` | bot_visualizer.py x5, screen_recorder.py x1 |
| `#0a0a20` | 6 | `VIZ_TAB_SELECTED` | testnet_tab.py x5, bot_visualizer.py x1 |
| `#1a0011` | 6 | `VIZ_STOP_HOVER` | bot_visualizer.py x6 |
| `#00ccaa` | 5 | `LAYER_CRYPTO` | main_window.py x4, usb_auth_widget.py x1 |
| `#00ddff` | 5 | `STATUS_AUTHENTICATED` | main_window.py x3, settings_dialog.py x2 |
| `#333333` | 5 | `SETTINGS_DISABLED_DEEP` | settings_dialog.py x2, audio_suite.py x1, bot_live_settings.py x1, market_inspector_topologies.py x1 |
| `#3a2020` | 5 | `SETTINGS_DANGER_SURFACE` | bot_live_settings.py x5 |
| `#3a3a5f` | 5 | `MENU_BORDER` | bot_visualizer.py x3, bot_live_settings.py x2 |
| `#3ed080` | 5 | `STATE_ARMED` | main_window.py x5 |
| `#444444` | 5 | `BORDER_DISABLED` | bot_live_settings.py x5 |
| `#6699ff` | 5 | `LAYER_STOCK` | main_window.py x4, settings_dialog.py x1 |
| `#8899aa` | 5 | `STATUS_NEUTRAL` | stock_main_window.py x4, main_window.py x1 |
| `#ff4466` | 5 | `STOCK_NEGATIVE` | stock_main_window.py x5 |
| `#00290f` | 4 | `VIZ_GO_HOVER_DEEP` | bot_visualizer.py x4 |
| `#1a1a2f` | 4 | `MENU_SURFACE` | bot_visualizer.py x3, launcher.py x1 |
| `#2a0018` | 4 | `VIZ_STOP_HOVER_DEEP` | bot_visualizer.py x4 |
| `#2a2a3a` | 4 | `MAIN_SEPARATOR` | main_window.py x2, start_all_progress_dialog.py x2 |
| `#8899bb` | 4 | **none** | competition_tab.py x2, testnet_tab.py x2 |
| `#aabbcc` | 4 | `CARD_STOCK_BODY` | stock_main_window.py x4 |
| `#cc0000` | 4 | `VIZ_NUCLEAR_BORDER` | bot_visualizer.py x4 |
| `#ff0000` | 4 | `VIZ_NUCLEAR_SURFACE` | bot_visualizer.py x4 |
| `#ff00aa` | 4 | `SECONDARY` | competition_tab.py x2, native_chart.py x1, testnet_tab.py x1 |
| `#00cccc` | 3 | `MAIN_TOOLTIP_BORDER` | main_window.py x1, market_inspector_topologies.py x1, settings_dialog.py x1 |
| `#080c18` | 3 | `CARD_STOCK_LOG_SURFACE` | stock_main_window.py x3 |
| `#0a0a14` | 3 | `SURFACE_CONSOLE_HEADER` | launcher.py x1, main_window.py x1, usb_auth_widget.py x1 |
| `#0a0a18` | 3 | `VIZ_LIST_SURFACE` | bot_visualizer.py x2, competition_tab.py x1 |
| `#1a1a1a` | 3 | `SETTINGS_DISABLED_SURFACE` | tradingview_chart.py x2, bot_live_settings.py x1 |
| `#1a1a26` | 3 | `MAIN_BUTTON_SURFACE` | main_window.py x2, start_all_progress_dialog.py x1 |
| `#1a2a4a` | 3 | `VIZ_LIST_BORDER` | bot_visualizer.py x2, indicator_panel.py x1 |
| `#22222e` | 3 | `MAIN_BUTTON_HOVER` | main_window.py x2, start_all_progress_dialog.py x1 |
| `#3a3a4a` | 3 | `MAIN_BUTTON_BORDER` | main_window.py x2, start_all_progress_dialog.py x1 |
| `#66ccff` | 3 | `TEXT_INFO_SOFT` | bot_live_settings.py x1, indicator_panel.py x1, main_window.py x1 |
| `#aaccff` | 3 | `VIZ_LIST_TEXT` | bot_visualizer.py x3 |
| `#c8d8f0` | 3 | `VIZ_HEADING` | bot_visualizer.py x2, usb_auth_widget.py x1 |
| `#ddaa00` | 3 | `STOCK_WARNING` | stock_main_window.py x3 |
| `#ff3355` | 3 | **none** | competition_tab.py x2, testnet_tab.py x1 |
| `#ff6600` | 3 | `WARNING_STRONG` | main_window.py x2, bot_live_settings.py x1 |
| `#ffcc44` | 3 | `STATE_PENDING` | main_window.py x3 |
| `#00ddaa` | 2 | `SETTINGS_PRIMARY_HOVER` | alerts_tab.py x1, bot_live_settings.py x1 |
| `#00e6ff` | 2 | `STATE_STARTING` | main_window.py x2 |
| `#00ff00` | 2 | **none** | tradingview_chart.py x2 |
| `#091a0e` | 2 | `VIZ_LANE_LIVE` | bot_visualizer.py x2 |
| `#14141e` | 2 | `MAIN_TOOLBAR_SURFACE` | main_window.py x1, start_all_progress_dialog.py x1 |
| `#142244` | 2 | `VIZ_INPUT_SURFACE` | bot_visualizer.py x2 |
| `#1a1a3a` | 2 | `MAIN_TOGGLE_SURFACE` | main_window.py x2 |
| `#222250` | 2 | `MAIN_TOGGLE_HOVER` | main_window.py x2 |
| `#2a2a44` | 2 | `SURFACE_4` | main_window.py x1, tradingview_chart.py x1 |
| `#2a2a4f` | 2 | `MENU_ITEM_SELECTED` | bot_visualizer.py x2 |
| `#2a2a5f` | 2 | **none** | journal_tab.py x2 |
| `#2d9d5f` | 2 | `STATE_ENGAGED` | main_window.py x2 |
| `#556677` | 2 | `VIZ_CAPTION_DIM` | bot_visualizer.py x2 |
| `#667799` | 2 | **none** | screen_recorder.py x1, usb_auth_widget.py x1 |
| `#88ccff` | 2 | `STATE_MARKET` | main_window.py x1, tradingview_chart.py x1 |
| `#8a8aab` | 2 | `TEXT_EMPTY_STATE` | bot_live_settings.py x2 |
| `#c0ffe0` | 2 | `TEXT_LOG_MINT` | main_window.py x2 |
| `#ffcc00` | 2 | **none** | market_inspector.py x1, native_chart.py x1 |
| `#000000` | 1 | `TEXT_ON_LIGHT` | main_window.py x1 |
| `#001122` | 1 | `SETTINGS_ON_INFO` | bot_live_settings.py x1 |
| `#001a18` | 1 | `VIZ_SIM_HOVER` | bot_visualizer.py x1 |
| `#003300` | 1 | **none** | tradingview_chart.py x1 |
| `#003822` | 1 | `VIZ_CONFIRM_SURFACE` | bot_visualizer.py x1 |
| `#0088dd` | 1 | `STOCK_BUTTON_HOVER` | stock_main_window.py x1 |
| `#00aacc` | 1 | **none** | settings_dialog.py x1 |
| `#00b4ff` | 1 | **none** | native_chart.py x1 |
| `#00ffaa` | 1 | **none** | indicator_panel.py x1 |
| `#00ffcc22` | 1 | `GLOW_PRIMARY_FAINT` | bot_live_settings.py x1 |
| `#00ffcc55` | 1 | `GLOW_PRIMARY_EDGE` | bot_live_settings.py x1 |
| `#05050a` | 1 | `SURFACE_CONSOLE` | main_window.py x1 |
| `#050510` | 1 | **none** | testnet_tab.py x1 |
| `#060612` | 1 | **none** | launcher.py x1 |
| `#08080f` | 1 | **none** | launcher.py x1 |
| `#080818` | 1 | **none** | testnet_tab.py x1 |
| `#08081a` | 1 | **none** | launcher.py x1 |
| `#0a0a0a` | 1 | **none** | tradingview_chart.py x1 |
| `#0a0a0f` | 1 | `SURFACE_0`, `BG` | tradingview_chart.py x1 |
| `#0a0a1c` | 1 | **none** | competition_tab.py x1 |
| `#0d0d20` | 1 | **none** | usb_auth_widget.py x1 |
| `#0e0e09` | 1 | `VIZ_LANE_PAPER` | bot_visualizer.py x1 |
| `#0e0e1a` | 1 | **none** | launcher.py x1 |
| `#0e1420` | 1 | **none** | live_bot_window.py x1 |
| `#111111` | 1 | **none** | tradingview_chart.py x1 |
| `#12121a` | 1 | **none** | tradingview_chart.py x1 |
| `#123a63` | 1 | `FOLD_TRANCHE_SURFACE` | bot_live_settings.py x1 |
| `#181818` | 1 | **none** | tradingview_chart.py x1 |
| `#1a0008` | 1 | **none** | screen_recorder.py x1 |
| `#1a1400` | 1 | `VIZ_GOLD_HOVER` | bot_visualizer.py x1 |
| `#1a1a28` | 1 | `SURFACE_2` | tradingview_chart.py x1 |
| `#1a3a4a` | 1 | **none** | settings_dialog.py x1 |
| `#1c1c24` | 1 | **none** | tradingview_chart.py x1 |
| `#1e1e35` | 1 | **none** | tradingview_chart.py x1 |
| `#222244` | 1 | **none** | usb_auth_widget.py x1 |
| `#2244aa` | 1 | `VIZ_INPUT_BORDER` | bot_visualizer.py x1 |
| `#225522` | 1 | **none** | buy_confirmation_dialog.py x1 |
| `#242430` | 1 | **none** | tradingview_chart.py x1 |
| `#2563eb` | 1 | **none** | tradingview_chart.py x1 |
| `#26a69a` | 1 | **none** | tradingview_chart.py x1 |
| `#2a0008` | 1 | **none** | screen_recorder.py x1 |
| `#2a3a5f` | 1 | `CARD_STOCK_BUTTON_BORDER` | stock_main_window.py x1 |
| `#2a3a6f` | 1 | `CARD_STOCK_BUTTON_HOVER` | stock_main_window.py x1 |
| `#2c2c3a` | 1 | **none** | tradingview_chart.py x1 |
| `#2d5f48` | 1 | `STATE_ENGAGED_DIM` | main_window.py x1 |
| `#30303f` | 1 | **none** | tradingview_chart.py x1 |
| `#33220a` | 1 | `MAIN_HIGHLIGHT_AMBER` | main_window.py x1 |
| `#333355` | 1 | **none** | usb_auth_widget.py x1 |
| `#334455` | 1 | **none** | competition_tab.py x1 |
| `#3344ff` | 1 | **none** | indicator_panel.py x1 |
| `#3a1a1a` | 1 | `MAIN_TOGGLE_CHECKED` | main_window.py x1 |
| `#3a3a50` | 1 | **none** | tradingview_chart.py x1 |
| `#440011` | 1 | `SETTINGS_DESTRUCTIVE_SURFACE` | bot_live_settings.py x1 |
| `#444455` | 1 | `STOCK_LOG_DEBUG` | stock_main_window.py x1 |
| `#4488ff` | 1 | **none** | usb_auth_widget.py x1 |
| `#50a0f0` | 1 | **none** | native_chart.py x1 |
| `#552222` | 1 | **none** | buy_confirmation_dialog.py x1 |
| `#555566` | 1 | `STOCK_LOG_TIMESTAMP` | stock_main_window.py x1 |
| `#557766` | 1 | `STATE_ENGAGED_GLOW` | main_window.py x1 |
| `#660022` | 1 | `SETTINGS_DESTRUCTIVE_HOVER` | bot_live_settings.py x1 |
| `#6600cc` | 1 | **none** | tradingview_chart.py x1 |
| `#663300` | 1 | `MAIN_TOGGLE_CHECKED_AMBER` | main_window.py x1 |
| `#666677` | 1 | `VIZ_TAB_TEXT` | bot_visualizer.py x1 |
| `#667788` | 1 | `MAIN_LOG_SITE` | main_window.py x1 |
| `#6699ff55` | 1 | **none** | settings_dialog.py x1 |
| `#66cc99` | 1 | **none** | market_inspector.py x1 |
| `#6ea6e6` | 1 | `FOLD_TRANCHE_BORDER` | bot_live_settings.py x1 |
| `#7a7d99` | 1 | `MAIN_CAPTION` | main_window.py x1 |
| `#7fb3ff` | 1 | `MAIN_BADGE_TEXT` | main_window.py x1 |
| `#80ffcc` | 1 | **none** | native_chart.py x1 |
| `#88c0ff` | 1 | `MAIN_LOG_NAME` | main_window.py x1 |
| `#b3261e` | 1 | `EXTRACTOR_TRANCHE_SURFACE` | bot_live_settings.py x1 |
| `#bb6666` | 1 | **none** | market_inspector_topologies.py x1 |
| `#c080ff` | 1 | **none** | native_chart.py x1 |
| `#c0c4d8` | 1 | `MAIN_TABLE_HEADER` | main_window.py x1 |
| `#c0d0e8` | 1 | **none** | testnet_tab.py x1 |
| `#c8d4e3` | 1 | **none** | live_bot_window.py x1 |
| `#ccccdd` | 1 | **none** | tradingview_chart.py x1 |
| `#cfe6ff` | 1 | **none** | crypto_news_ticker.py x1 |
| `#d0d0e0` | 1 | **none** | tradingview_chart.py x1 |
| `#d61a3d` | 1 | `MAIN_ALERT_SURFACE` | main_window.py x1 |
| `#d8e8ff` | 1 | **none** | competition_tab.py x1 |
| `#e0e0e0` | 1 | **none** | tradingview_chart.py x1 |
| `#e5e5f0` | 1 | **none** | tradingview_chart.py x1 |
| `#e8e8e8` | 1 | **none** | tradingview_chart.py x1 |
| `#eeeeee` | 1 | **none** | tradingview_chart.py x1 |
| `#eeeef5` | 1 | **none** | tradingview_chart.py x1 |
| `#f0f0f0` | 1 | **none** | tradingview_chart.py x1 |
| `#f5f5fa` | 1 | **none** | tradingview_chart.py x1 |
| `#fafafa` | 1 | **none** | tradingview_chart.py x1 |
| `#ff0033` | 1 | `STOCK_LOG_CRITICAL` | stock_main_window.py x1 |
| `#ff0044` | 1 | `MAIN_LOG_CRITICAL` | main_window.py x1 |
| `#ff4444` | 1 | **none** | usb_auth_widget.py x1 |
| `#ff4488` | 1 | **none** | native_chart.py x1 |
| `#ff6666` | 1 | **none** | usb_auth_widget.py x1 |
| `#ff66dd` | 1 | `MAIN_BADGE_MAGENTA` | main_window.py x1 |
| `#ff8833` | 1 | `SETTINGS_WARNING_HOVER` | bot_live_settings.py x1 |
| `#ff9060` | 1 | **none** | native_chart.py x1 |
| `#ff9966` | 1 | **none** | market_inspector.py x1 |
| `#ffa000` | 1 | **none** | native_chart.py x1 |
| `#ffb000` | 1 | `MAIN_HIGHLIGHT_AMBER_TEXT` | main_window.py x1 |
| `#ffb020` | 1 | **none** | indicator_panel.py x1 |
| `#ffb0a6` | 1 | `EXTRACTOR_TRANCHE_BORDER` | bot_live_settings.py x1 |
| `#ffb800` | 1 | **none** | usb_auth_widget.py x1 |
| `#ffb84d` | 1 | **none** | market_inspector_topologies.py x1 |
| `#ffcc66` | 1 | **none** | market_inspector.py x1 |
