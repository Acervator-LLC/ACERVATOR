# 2026-09-09 — Swarm tab: List View removed, the grid rebuilt

Issue #128. Files: `src/gui/bot_visualizer.py`, `src/gui/visualizer/bot_node.py`,
`src/gui/visualizer/wire_canvas.py`, `src/gui/visualizer/growth_stage.py`,
`src/gui/main_tabs/bot_node_surface.py`,
`src/gui/main_tabs/bot_visualizer_surface.py`,
`src/gui/main_tabs/wire_canvas_surface.py`, `src/gui/react_bot_swarm_tab.py`,
`src/gui/theme_engine.py`, `src/gui/main_window.py`,
`src/gui/web/bot_node.js`, `src/gui/web/bot_visualizer.js`,
`src/gui/web/bot_swarm_tab.css`, `src/trading/bot_container.py`,
`tools/conversion_state.py`. Deleted: `src/gui/bot_swarm_list.py`.

Run under `python -X dev -X faulthandler` with `PYTHONWARNINGS=error` and
`QT_QPA_PLATFORM=offscreen`. No test file was written.

---

## 1 — TA004 on the catenary solver

### 1.1 the error

```
[archetype] not green: 1 critical/high finding(s)
TA004 line 341 - units mismatch: 'HALF * mid * math.sinh(span / (HALF ' (dimensionless)
compared against 'wanted' (absolute).
```

### 1.2 reproduction

```
python -m dev_harness.harness.ta_archetype src/gui/main_tabs/wire_canvas_surface.py
exit 1
```

The same command on `origin/current` exits 0, so the finding is in the new code.

### 1.3 the cause

`catenary_parameter` solved `2a sinh(span / 2a) = sqrt(length^2 - drop^2)` for
`a` by halving an interval. The bisection midpoint came from a division, so
`ta_archetype` recorded the left side as dimensionless, and `wanted` came from a
square root, so the right side was absolute. The rule flags a comparison that
crosses that line.

### 1.4 the correction

The solve was restated on the ratio form of the same equation. With `u = span /
2a` the condition is `sinh(u) / u = sqrt(length^2 - drop^2) / span`, and both
sides are ratios. The ceiling is bound to a local name that also comes from a
division.

```python
    wanted_ratio = math.sqrt(length * length - drop * drop) / span
    ceiling_ratio = math.sinh(CATENARY_U_MAX) / CATENARY_U_MAX
    if wanted_ratio >= ceiling_ratio:
        return None
```

### 1.5 the rerun

```
python -m dev_harness.harness.ta_archetype src/gui/main_tabs/wire_canvas_surface.py
exit 0
```

The curve is unchanged by the restatement. Driven on a 200 pixel span the
sampled polyline measures 1.17972 times its chord against the 1.18 asked for,
sags 55.033 pixels, and the flattest sample index equals the minimum-slope
segment index on a sloped span.

---

## 2 — TA004 on the card's path builder, which predates this change

### 2.1 the error

```
[archetype] not green: 4 critical/high finding(s)
TA004 line 718 - units mismatch: 'first[1]' (dimensionless) compared against
'last[1]' (absolute).
```

### 2.2 reproduction

```
python -m dev_harness.harness.ta_archetype src/gui/main_tabs/bot_node_surface.py
exit 1
```

The same command on `origin/current` also exits 1 with the same four findings, so
this one is older than the change.

### 2.3 the cause

`PathBuilder.quad_to` binds `first` and `second` from a division by
`CUBIC_DIVISOR`. `PathBuilder.close` binds `first` and `last` from list indexing.
The analyzer tracks divided names for the whole module, so the name `first` was
marked dimensionless everywhere and the comparison in `close` crossed the rule's
line.

### 2.4 the correction

`close` names its two elements for what they are. No arithmetic changed.

```python
        opening = self.elements[self.start_index]
        ending = self.elements[-1]
```

### 2.5 the rerun

```
python -m dev_harness.harness.ta_archetype src/gui/main_tabs/bot_node_surface.py
exit 0
```

---

## 3 — The grid column count disagreed between the two builds

### 3.1 the error

```
grid_cols              DIFFERS
   qt     8
   react  6
matched 20 of 21 compared
```

### 3.2 reproduction

Both sides were built in one process under `ACERVATOR_VARIANT=qt`: the Qt tab
through `BotVisualizationTab`, the React side through
`bot_visualizer_surface.build_payload`, then every named value compared.

### 3.3 the cause

The Qt tab's `_grid_cols` was widened to 8 for the smaller card.
`bot_visualizer_surface.GRID_COLS` still held 6, and nothing made the two agree.

### 3.4 the correction

```python
# 8 columns fits an 88px locust plus GRID_SPACING in the left pane.
GRID_COLS = 8
```

### 3.5 the rerun

```
matched 22 of 22 compared
exit 0
```

The comparison had reported a real difference before the fix, so its zero is a
result. The count rose to 22 after the bot id colour was added to it.

---

## 4 — The bot id text failed the contrast floor on every canvas ground

### 4.1 the error

```
FAILS  nebula   bot id       #6e6e8c on #080414  4.12:1
FAILS  matrix   bot id       #6e6e8c on #000800  4.13:1
FAILS  quantum  bot id       #6e6e8c on #0a0f19  3.90:1
FAILS  ocean    bot id       #6e6e8c on #050a1e  4.00:1
AA 4.5:1 readings passed 28 of 32
```

### 4.2 reproduction

`src.design_system.validate_contrast` was run over every text colour the card
paints against every canvas background the four palettes carry.

The instrument was controlled in the same run: it returns `(False, 1.07)` for a
near-black trim and `(False, 2.18)` for the hopper body tone on the Quantum
ground, so it reports a failure when one exists.

### 4.3 the cause

`BOT_ID_COLOR = (110, 110, 140, 255)` was a literal in both card painters. Its
luminance clears neither the 4.5 to 1 floor on any of the four grounds.

### 4.4 the correction

A `locust_id_text` token was added to every theme, and both painters read it.

```python
    locust_id_text: str = "#8c8ca8"
```

```python
            p.setPen(QColor(id_text_color(self._app_theme_name)))
```

### 4.5 the rerun

```
AA 4.5:1 text readings passed 160 of 160
bot id         #8c8ca8  5.87:1
```

160 readings is five app themes by four canvas palettes by eight text roles.

---

## 5 — A conversion control pointed at the deleted file

### 5.1 the error

No traceback. `tools/conversion_state.py` prints its controls, and the row for
the deleted name would have read `born React` rather than `paired`.

### 5.2 reproduction

```
python -m tools.conversion_state
CONTROL, a converted name must report 'paired':
  bot_swarm_list    born React
```

### 5.3 the cause

`control_state` returns `BORN_REACT` when no verdict carries the probe's stem. A
probe naming a file that no longer exists therefore reports a state that is not
`paired`, and a reader cannot tell that from a genuine classification.

### 5.4 the correction

```python
CONTROLS = ("bot_visualizer", "theme_engine", "design_tokens")
```

### 5.5 the rerun

```
CONTROL, a converted name must report 'paired':
  bot_visualizer    paired
  theme_engine      born React
  design_tokens     born React
exit 0
```

The control discriminates again: one paired Qt file and two born-React names.

---

## 6 — The React Swarm tab could not be told the app theme

### 6.1 the error

```
variant: react
swarm tab class: BotSwarmReactTab
has set_app_theme: False
```

### 6.2 reproduction

`MainWindow` was constructed offscreen under `ACERVATOR_VARIANT=react` and the
Swarm tab read back off the window.

### 6.3 the cause

`_switch_theme` in the main window forwards the chosen theme to whatever carries
`set_app_theme`. The Qt tab gained that method; the React tab did not, so the
stage colours in the React build would never follow a theme change.

### 6.4 the correction

```python
        def set_app_theme(self, theme_name: str) -> None:
            """Read every locust's growth-stage colours from theme_name."""
            self.take({"action": "set_app_theme", "name": theme_name})
```

### 6.5 the rerun

```
variant: react
has set_app_theme: True
```

---

## 7 — Undefined names while the change was being built

### 7.1 the error

Seven runs raised a name that did not exist yet, each found by the archetype on
the file just edited. The names were `HALF_INDEX`, `CATENARY_U_MAX`,
`SEGMENT_COUNT`, `CROWN_DRAWN`, `hex_color`, `STAGE_LABELS` and
`self._theme_name`.

```
mypy:name-defined line 379 [high]: Name "HALF_INDEX" is not defined
pyright:reportUndefinedVariable line 1083 [high]: "hex_color" is not defined
```

### 7.2 reproduction

Each was reported by `coding_archetype` on the file it was introduced in,
immediately after the edit.

### 7.3 the cause

A constant or helper was used in one edit and defined in the next. `SEGMENT_COUNT`
was the one real case of the opposite kind: it was removed because the tergite
count became per stage, and two readers still named it.

### 7.4 the correction

Each name was defined, or the reader was pointed at its replacement.
`self._theme_name` was a wrong attribute name and became `self._app_theme_name`.

### 7.5 the rerun

Every touched file reports `passed` with an empty `errors` list.

```
passed 38 of 38 archetype runs
exit 0
```

---

## What was opened, and what drew

Both builds were constructed offscreen and every main tab opened.

```
variant: qt
tabs   : ['Live', 'Charts', 'Inspector', 'Console', 'Swarm', 'Accumulation', 'Status', 'History']
has a View picker: False
has a bot list   : False
has a lane canvas: False

variant: react
tabs   : ['Sim', 'Paper', 'Live', 'Charts', 'Inspector', 'Swarm', 'Accumulation', 'History', 'Status', 'Console']
has a View picker: False
```

Both tab lists match the lists the same run produced on `origin/current`, so
nothing was lost with the List View.

A card was driven at each of the four stages, with the figure that placed it.

```
hopper          50.0 %  body #4a4a52 trim #9a9aa6  tergites 2 crown 0 wings 0.35 body 0.82
fledgling      120.0 %  body #c4303f trim #f2f2f7  tergites 3 crown 0 wings 0.80 body 0.91
immature_adult 210.0 %  body #9ea4ad trim #e2e6ec  tergites 4 crown 0 wings 1.00 body 1.00
mature_adult   340.0 %  body #b8912c trim #f0c64a  tergites 4 crown 3 wings 1.00 body 1.00
```

Every figure is a realised profit of 500, 1,200, 2,100 and 3,400 dollars against a
cost basis of 1,000 dollars, read from `realized_pnl_exchange` and
`cost_basis_total_exchange` on the bot status snapshot. A bot whose
`exchange_data_fresh_ts` is zero draws as a Hopper and prints an em dash.

The wire labels were measured on a 38 bot grid carrying 152 wires, with the real
33 pixel width of a printed rate label.

```
overlapping label pairs at the flattest point 114
overlapping label pairs after place_badge     0
```

The repaint rate was measured over 300 frames of the tab's 33 millisecond timer.

```
Qt still card     :  75 of 300 frames = 7.58 Hz
React still card  :  75 of 300 frames = 7.58 Hz
Qt card, one trade:  30 of 30 frames = every frame while the ring lives
38 still cards    : 288 repaints a second, against 1152 at the timer rate
```

## One check that does not exist

`src/gui/web/bot_swarm_tab.css` was edited and no archetype examines a `.css`
file. Every archetype run on it reports `no analyzer for css - this file type was
NOT examined, which is not the same as clean`. The proposed rule is that
`gui_archetype` gains a stylesheet analyzer, so a rule changed in a sheet is
adjudicated rather than unexamined. No such analyzer was written here.
