# 2026-09-10 - Proof of Accumulation: the tab's proportions

Issue #147, unit 47. Branch `unit/147-u47-tab-proportions`, cut from `96eec636`.
Files changed: `src/gui/web/proof_of_accumulation_tab.css` and
[docs/manual/08-tabs/proof-of-accumulation.md](../../docs/manual/08-tabs/proof-of-accumulation.md).
No test file was written. No Python test names any symbol this unit touched; the whole
of `tests/` outside the debug reports is `conftest.py`, six Solidity contract tests and
one data file.

`main.py` was never launched. Every figure below was read off a rendered page: once
under `ACERVATOR_VARIANT=qt` with `QT_QPA_PLATFORM=offscreen`, and once in the real
Electron shell started as `electron desktop/` with
`ACERVATOR_BRIDGE_ARGV="-X dev -X faulthandler -m src.core.desktop_bridge"`, so the page
crossed the real preload, the real IPC channel and the real Python bridge.

Every run redirected `HOME` and `USERPROFILE` to a scratch home before the surface was
imported. Nothing under the real `~/.acervator` was read or written; the fleet file was
absent, so the party slots draw as empty placeholders.

| scratch path | what ran there |
|---|---|
| `%TEMP%/claude/.../scratchpad/wt-u47` | the git worktree |
| `%TEMP%/claude/.../scratchpad/U47_home` | `Path.home()` for every run |
| `%TEMP%/claude/.../scratchpad/U47_electron` | the shell's own user data directory |

---

## 1 - The tab has no Qt original, so both variants draw one page

`src/gui/main_tabs/proof_of_accumulation_tab.py` builds
`ProofOfAccumulationReactPanel` unconditionally and its own docstring says the screen
has no Qt original, so no `variant_surface` entry decides the side.
`ACERVATOR_VARIANT=qt` and the default therefore draw the same renderer module, one in
`QWebEngineView` inside the desktop window and one in the Electron shell.

Both readings below are therefore of the same module in two hosts.

---

## 2 - The desktop window's page had no height to divide

### 2.1 the error

No traceback. Under `ACERVATOR_VARIANT=qt` in a 1386x696 window the page reported a
root 3,506 pixels tall, every zone 1,055 pixels tall, and the player window 260 pixels
wide beside a 1,055-pixel square enemy screen. At a 900-pixel-wide window the player
window measured 18 pixels wide.

```
root 3506   vp {"w": 1386, "h": 696}
heights  subtabPanel 1055  upperBand 1055  playerWindow 1055  partyWindow 1055
widths   playerWindow 260  enemyScreen 1055
```

### 2.2 reproduction

```
python U47_qt_read.py 1386 697 U47_out/qt_before_matched.json
python U47_qt_read.py 900 697 U47_out/qt_before_narrow.json
```

### 2.3 the cause

`react_proof_of_accumulation_tab.panel_html` puts the tab in `div#panel-root`, a plain
block with no height. `.acervator-poa-tab` asks for `height: 100%` of that block, which
resolves to auto, so the grid container's height is indefinite and each `1fr` row takes
its own max-content height instead of a share. The square enemy screen then takes its
width from that row height and leaves the player window whatever is left.

The Electron shell does not have the fault: `desktop/renderer/index.html` gives
`#panels > [data-panel]` a height of 100%.

### 2.4 the correction

The style sheet gives the desktop window's panel host a height, scoped so it cannot
reach the shell's own hosts or the `#panel-root` that `history_panel.js` renders inside
them.

```css
body:has(> #panel-root) {
  margin: 0;
}

body > #panel-root {
  height: 100%;
}
```

### 2.5 the rerun

```
root 696   vp {"w": 1386, "h": 696}
heights  playerWindow 182  enemyScreen 182  partyWindow 182
widths   playerWindow 1164  enemyScreen 182
```

At a 900-pixel-wide window the player window is 677 wide and the enemy screen a
183-pixel square.

---

## 3 - Three equal rows left the player window a hundred pixels

### 3.1 the error

No traceback. In the Electron shell at the window size the shell opens, the tab gave
the subtab panel, the upper band and the party window one third each.

```
rows    30.8px 15.4px 201.2px 21.6px 115.925px 115.938px 115.938px
heights controlBar 201  subtabPanel 116  playerWindow 116  partyWindow 116
```

The control bar took 201 pixels, more than any zone.

### 3.2 reproduction

```
python U47_shell_read.py 0 0 U47_out/react_before_native.json U47_out/react_before_native.png
```

### 3.3 the cause

`grid-template-rows: auto auto auto auto 1fr 1fr 1fr` gave the three trailing rows an
equal share, and the two rows above them were unbounded. His layout in issue #147 gives
the upper band the upper half and the party window the lower half, and puts no chrome
between them.

### 3.4 the correction

The two zone rows take the tab in equal halves. The control bar and the subtab panel
take the height their own content needs up to a share of the tab, and scroll past it.

```css
grid-template-rows: auto auto minmax(0, 15%) auto minmax(0, 13%) 1fr 1fr;
```

The 15% cap lands under the verdict line, so every button and the verdict draw and the
chain reset panel is reached by the control bar's own scrollbar.

### 3.5 the rerun

```
rows    30.8px 15.4px 99.7125px 21.6px 86.4125px 181.438px 181.438px
heights controlBar 100  subtabPanel 86  playerWindow 181  partyWindow 181
```

---

## 4 - Bands inside the two zones were drawing at no height

### 4.1 the error

No traceback. The eight mode rows in the player window and the forty slots of a party
page both measured zero, and the skill ladder, the pot division, the four-bucket report
and the season each measured ten pixels.

```
player  zone-title 21  event-band 28  meter-pair 135  map-control 22  mode-list 0
party   party-header 66  party-pages 0  class-list 42  skill-panel 10  pot-panel 10
        keep-panel 10  season-panel 10
```

### 4.2 reproduction

The same shell run, reading each zone's direct children.

### 4.3 the cause

Both zones are flex columns. Every band was shrinkable, `party-pages` carried
`min-height: 0`, and the four report panels carry `min-height: 0` of their own, so a
zone shorter than its content shrank every band toward zero rather than scrolling.

### 4.4 the correction

Each band keeps the height its content needs, the slot pages take the zone's spare
height and never less than the five rows a group holds, and the party window scrolls the
way the player window already did.

```css
.acervator-poa-tab [data-part="player-window"] > *,
.acervator-poa-tab [data-part="party-window"] > * {
  flex-shrink: 0;
}
```

### 4.5 the rerun

```
player  mode-list 150
party   party-pages 88  skill-panel 66  pot-panel 49  keep-panel 49  season-panel 49
```

---

## 5 - The one control

**What a failure would mean.** If the player window still measured near a hundred
pixels, the tab's height would still be divided into equal shares between the game zones
and the chrome above them, and the zone his layout calls the largest would still be the
same size as a detail panel.

The player window's rendered height at a normal window size, on both variants.

| variant | page box | before | after |
|---|---|---|---|
| Electron shell | 1386x838 window, tab root 697 | **116** | **181** |
| desktop window | 1386x696 page, tab root 696 | **1055** | **182** |

The desktop window's before figure is larger and is the same defect: that page was 3,506
pixels tall inside a 696-pixel window, and the zone was 260 pixels wide.

At a full-screen window the zones grow with the tab.

```
1920x1040   controlBar 130  subtabPanel 113  playerWindow 254  partyWindow 254
```

**The control does not fully pass.** The player window's bands come to 410 pixels, so at
181 the zone still scrolls, and at 254 it still scrolls. The tab body would need about
1,335 pixels for the zone to clear its own content, which is a window about 1,480 pixels
tall.

---

## 6 - Both variants, matched reading by reading

The same script ran against the desktop window's page and the shell's page, at the same
tab root height to within one pixel.

```
readings compared   40
identical           24
differing           16
```

Every difference falls in one of three groups.

| group | readings | why |
|---|---|---|
| the live candle clock | `eventTurn`, `meterValues` | read seconds apart |
| the page box | `viewport`, `rootHeight` | 838-pixel shell window against a 696-pixel harness window; tab root 697 against 696 |
| one pixel a text line | the rest | same declared type, different rounding |

The third group is the one to state carefully. `fontSizes` is identical on both -
`heading` 22px, `state` 11px, `zoneTitle` 15px - and `pixelRatio` is 1.25 on both, so the
two engines resolve the same declaration and round each text line differently.

```
heading      30 against 31
state        14 against 15
mode-list   142 against 150   eight rows, one pixel each
meter-pair  130 against 135   five text lines
```

The zone heights differ by one pixel for the same reason, and the widths follow the
heights because the enemy screen is square.

One reading differs by more. The skill ladder declares `max-height: 40%` on both pages,
and both report that computed value; the desktop window resolves it to 105 pixels and
the shell to 66. Both sit inside a zone that scrolls, so nothing is unreachable on
either. Before this unit the same pair read 319 against 10.

A control for the reading script: it counts a part name that exists on no page,
`no-such-part-zz`, and answers 0 beside `partySlot` 40, `controlButton` 11 and
`modeRow` 8.

---

## 7 - The instruments

| instrument | known good | known bad |
|---|---|---|
| `gui_archetype` style | exit 0, `passed=true` | exit 1, `passed=false` |
| `docs_archetype` | exit 0, `passed=true` | exit 1, `passed=false` |

`stylelint` reported nothing on the changed sheet, so it was shown able to report on
that file: a duplicate `height` declaration was added, `stylelint` answered exit 2 with
`declaration-block-no-duplicate-properties` and `gui_archetype` answered exit 1,
`passed=false`. The line was removed and the file compared byte-identical afterwards.

```
before the plant   b524500c4d46b66591f7bcb5b7b5c4d721890aa4e57a0f59b580cdddeac1b709
after the restore  b524500c4d46b66591f7bcb5b7b5c4d721890aa4e57a0f59b580cdddeac1b709
```

---

## 8 - The verdicts

| file | archetype | passed | tools |
|---|---|---|---|
| `proof_of_accumulation_tab.css` | gui | True | stylelint, scaffolding, hallucination all ok |
| `proof-of-accumulation.md` | docs | True | proselint, vale, structure, story, updates, scaffolding, hallucination all ok |

The manual diff adds and removes nothing.

```
git diff --numstat -- docs/manual/08-tabs/proof-of-accumulation.md
60      0       docs/manual/08-tabs/proof-of-accumulation.md
```

---

## 9 - What this does not reach

The player window scrolls. Its eight mode rows sit below the fold at every window height
this machine can render.

The eight event types are named twice on the screen, once as the event buttons in the
control bar and once as the mode rows in the player window. Dropping either copy changes
what the tab says rather than how it is sized.

The chain reset panel sits below the control bar's cap and is reached by that bar's own
scrollbar.

The party window holds nine bands: its header, the slot pages, the class list, the skill
ladder, the pot division, the four-bucket report, the season, and two notes. Five of them
are below the fold.

No picture of the desktop window's page exists. `QWidget.grab` on the panel saves an
all-white image because the content draws through `QWebEngineView`, which the widget
grab does not capture, so that side is compared by the values its page reports.
