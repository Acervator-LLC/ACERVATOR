# The tab bar: ten single-word tabs, in the operator's order, each on its own ground

The main window's tab bar carried ten tabs in a different order, under longer
names, all painted the same colour. It now carries the same ten tabs in the
operator's order, each under one word, each on one of three grounds. No tab
holds a colour: a ground names two theme tokens and every theme fills them.

Every run used the repository worktree only. `~/.acervator/settings.json` hashed
the same before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

No authenticated call, no credential, no order placed, and the running
Acervator process was never started, attached to or queried.

## Reproduce

Three readings, all against `origin/current` plus this branch:

```
the seam        src.gui.main_tabs.main_window_surface.view_model({})
the Qt bar      MainTabBookQt with the ten tabs, one theme's QSS applied, grab()
the React bar   MainTabBookReact with the ten tabs, page loaded, grab()
```

The React grab needs software rendering. Under the default offscreen platform
the GPU context is lost and `grab()` returns 1400x44 of flat white, one distinct
colour, 61,600 pixels. With `QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu
--disable-gpu-compositing"` the same grab returns 138 distinct colours. Every
React colour below is read off that second image.

## The bar the running program reports

`view_model` answers the labels, the bridge method behind each, and the two
colours each tab paints with.

```
labels: ["Sim","Paper","Live","Charts","Inspector","Swarm","Accumulation","History","Status","Console"]
current: Sim
theme:   cyberpunk_dark

Sim            black  #0a0a0f #ff5577  -> simulator_tab.state
Paper          white  #f5f5fa #0a0a0f  -> paper_trader_tab.state
Live           gold   #fcee0a #8c0018  -> trading.tab
Charts         gold   #fcee0a #8c0018  -> trade_charts_tab.state
Inspector      gold   #fcee0a #8c0018  -> market_inspector.state
Swarm          gold   #fcee0a #8c0018  -> bot_visualizer.state
Accumulation   gold   #fcee0a #8c0018  -> proof_of_accumulation_tab.state
History        gold   #fcee0a #8c0018  -> history_tab.chrome
Status         gold   #fcee0a #8c0018  -> system_status_tab.state
Console        gold   #fcee0a #8c0018  -> console.tab
```

The ten bridge methods are the ten the bar carried before the rename, so every
renamed tab still opens the panel it opened before.

## The builders still run in their own order

`BUILT_TAB_ORDER` and `CANONICAL_TAB_ORDER` are two sequences on purpose. The
builders were not reordered to produce the bar; the reorder pass does that.

```
builders leave  Live, Sim, Charts, Swarm, Inspector, History, Console, Paper, Status, Accumulation
bar ends        Sim, Paper, Live, Charts, Inspector, Swarm, Accumulation, History, Status, Console
```

The shipped `_reorder_main_tabs` and the surface's `reordered_tabs` were driven
on the same eight label sets — the builder order, the construction order, an
already-canonical list, a reversed list, an empty list, one tab, a tab the order
does not name, and a list naming one tab twice. Both sides agreed on all eight.

## Each tab's colour, read off a rendered image

Read from `grab().toImage()`, never from a declared value. The ground is the
pixel two across from the tab's left edge; the text colour is the pixel farthest
from that ground inside the tab.

### Qt, cyberpunk_dark

```
 1 Sim            ground=#0a0a0f text=#ff5577
 2 Paper          ground=#f5f5fa text=#0a0a0f
 3 Live           ground=#fcee0a text=#8c0018
 4 Charts         ground=#fcee0a text=#8c0018
 5 Inspector      ground=#fcee0a text=#8c0018
 6 Swarm          ground=#fcee0a text=#8c0018
 7 Accumulation   ground=#fcee0a text=#8c0018
 8 History        ground=#fcee0a text=#8c0018
 9 Status         ground=#fcee0a text=#8c0018
10 Console        ground=#fcee0a text=#8c0018
```

### Every theme the engine ships

Five themes, ten tabs each. Ground and text were read off the image for all
fifty, on both sides. All fifty matched what the theme declares, on both sides.

```
theme             gold ground  gold text  black ground  black text  white ground  white text
cyberpunk_dark    #fcee0a      #8c0018    #0a0a0f       #ff5577     #f5f5fa       #0a0a0f
neon_light        #f0cf1f      #99001f    #1a1a2e       #ff6b8a     #ffffff       #1a1a2e
classic_terminal  #ffff00      #990000    #0a0a0a       #ff3333     #e8e8e8       #0a0a0a
minimal_modern    #eab308      #7f1d1d    #1a1a1a       #ff6b6b     #ffffff       #1a1a1a
glass_metal       #e8b34a      #6b1020    #1c1c24       #ff6688     #e8e8f0       #1c1c24
```

Contrast, measured with `src.design_system.contrast_ratio`, fifteen pairs:

```
cyberpunk_dark    gold 8.16  black 6.41  white 18.17
neon_light        gold 5.75  black 6.27  white 17.06
classic_terminal  gold 8.31  black 5.44  white 16.16
minimal_modern    gold 5.22  black 6.27  white 17.40
glass_metal       gold 6.38  black 6.05  white 13.89
```

Every one clears WCAG 2.2 AA at 4.5 to 1. The lowest is 5.22.

## The pixel reader has a control

A colour read off an image is worthless if the reader cannot tell a glyph from
the ground. Two readings prove it can.

The count of non-ground pixels inside each Qt tab tracks the label length
exactly, and the whole tab holds two colours and no third:

```
Sim            non-ground-pixels= 96  distinct=2
Paper          non-ground-pixels=160  distinct=2
Live           non-ground-pixels=128  distinct=2
Inspector      non-ground-pixels=288  distinct=2
Accumulation   non-ground-pixels=384  distinct=2
```

Blinding the bar — emptying `TAB_GROUNDS` so no tab resolves a ground — changes
every reading. The grounds fall back to the plain style and the tabs carry
nineteen to twenty-three colours instead of two:

```
Sim            ground=#1e1e35 non-ground-pixels=570 distinct=23
Paper          ground=#1a1a28 non-ground-pixels=391 distinct=20
Accumulation   ground=#1a1a28 non-ground-pixels=706 distinct=20
```

`TAB_GROUNDS` was restored to its ten entries afterwards.

The reader was wrong once and was corrected. On the React side it first reported
near-black text on the gold tabs. The buttons have a four-pixel corner radius,
so the scan was reading the page's own ground through the rounded corners, not
the text. Inset past the border and the corners, every gold tab reads its
declared red, and the count of pixels at exactly that red is sixteen to
fifty-seven per tab.

## The Qt window and the React page, value by value

Both bars were built with the same ten tabs and read under all five themes.

```
compared per theme   tab count 1, selected tab 1, and per tab: position, text,
                     ground colour, text colour, width  = 52
compared in total    52 x 5 themes = 260
matched              260
```

| reading | Qt | React |
| --- | --- | --- |
| tab count | 10 | 10 |
| order | Sim … Console | Sim … Console |
| each tab's text | the ten words | the ten words |
| ground colour, 50 readings | as declared | as declared |
| text colour, 50 readings | as declared | as declared |
| selected at startup | index 0, Sim | Sim |

Tab widths, cyberpunk_dark, with a real font loaded into both sides:

```
        Sim Paper Live Charts Inspector Swarm Accumulation History Status Console
Qt       53    66   54     69        86    71          109      74     67      79
React    52    64   53     68        83    70          108      70     66      77
```

The largest gap is four pixels, on History. That gap is the font: Qt draws in
the theme's own stack and the browser draws in its own. It is the difference the
operator's bar allows.

Two readings here are facts about this machine, not about the product, and both
are recorded rather than reported as product values. The offscreen platform
reports zero font families, so an unsmoothed run draws one box per character at
32 pixels each; that run gives the cleanest colour reading, fifty of fifty
exact. Loading a real font gives antialiased glyphs, and the extreme pixel then
lands on the declared colour on forty of fifty and within a few units on the
other ten, all of them the shortest labels.

## Two things measured and left alone

The React bar is 44 pixels tall and the Qt bar is 32 to 36, because the web view
is fixed at `BAR_HEIGHT_PX`. That difference predates this change. The issue
names order, tab text and each tab's ground and text colour as what must measure
identically, and height is not among them, so it stands.

The conversion table in `docs/manual/08-tabs.md` carries a row per Qt file, not
per tab. Every cell in it — the React module, the bridge, the manifest, whether
it renders, its scope — is unchanged by a rename, so no row moved.

## Before and after

| reading | before | after |
| --- | --- | --- |
| tab 1 | `Trading` | `Sim` |
| tab 2 | `Market Inspector` | `Paper` |
| tab 3 | `Bot Swarm` | `Live` |
| tab 4 | `Asset Charts` | `Charts` |
| tab 5 | `History` | `Inspector` |
| tab 6 | `Simulator` | `Swarm` |
| tab 7 | `Console` | `Accumulation` |
| tab 8 | `Paper Trader` | `History` |
| tab 9 | `System Status` | `Status` |
| tab 10 | `Proof of Accumulation` | `Console` |
| selected at startup | Trading | Sim |
| grounds on the bar | one, from `QTabBar::tab` | three, per tab |
| tab colours in the theme | none | six per theme, 30 in all |
| theme fields | 34 | 40 |
| style sheet, cyberpunk_dark | 7,376 characters | 7,670 characters |
| Qt tab book class | `QTabWidget` | `MainTabBookQt` |
| labels written in the builders | 7 literals | 0, all from the seam |
| Simulator insert index | literal `1` | `SIMULATOR_BUILD_INDEX` |

The builder order, the ten bridge methods, and every panel behind the ten tabs
are unchanged.
