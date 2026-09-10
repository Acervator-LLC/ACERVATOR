# 2026-09-10 - Proof of Accumulation: a reset control, two meters, a fourth wallet holding

Issue #147, unit 41. Branch `unit/147-u41-reset-meters-vessels`, cut from `5e49c87c`.
Files changed: `src/gui/shared_testnet.py`,
`src/gui/main_tabs/proof_of_accumulation_tab_surface.py`,
`src/gui/web/proof_of_accumulation_tab.js`,
`src/gui/web/proof_of_accumulation_tab.css` and
[docs/manual/08-tabs/proof-of-accumulation.md](../../docs/manual/08-tabs/proof-of-accumulation.md).
No test file was written.

`main.py` was never launched. Every figure below was read off a rendered page: once
under `ACERVATOR_VARIANT=qt` with `QT_QPA_PLATFORM=offscreen`, and once in the real
Electron shell started as `electron desktop/` with
`ACERVATOR_BRIDGE_ARGV="-X dev -X faulthandler -m src.core.desktop_bridge"`, so every
click crossed the real preload, the real IPC channel and the real Python bridge.

Every run redirected `HOME` and `USERPROFILE` to a scratch home before the surface was
imported, and each run printed `Path.home()` and the surface's own `LEDGER_DIR`.

| scratch path | what ran there |
|---|---|
| `%TEMP%/claude/.../scratchpad/wt-u41` | the git worktree |
| `%TEMP%/claude/.../scratchpad/U41_home` | `Path.home()` for every run |
| `%TEMP%/claude/.../scratchpad/U41_home/.acervator` | the surface's `LEDGER_DIR` |
| `%TEMP%/claude/.../scratchpad/U41_electron` | the shell's own user data directory |

Nothing under the real `~/.acervator` was written. One file was read out of it and
copied into the scratch home: `bot_state.json`, so the party window came off the
operator's own fleet.

The operator's chain file was hashed before the work and after it.

```
before   4059629 bytes   f84458bc69c8e894794836b8658be7518cb6e108e78861cd9769f12fe25988be
after    4059629 bytes   f84458bc69c8e894794836b8658be7518cb6e108e78861cd9769f12fe25988be
```

`SCHEMA_VERSION` is 1 before and after.

---

## 1 - The Vessels section could never have drawn a Vessel

### 1.1 the error

No traceback. The section printed its no-Vessel sentence on every input, including a
request that named a class for this node.

```
vessels with a pick []  poa_record_store.json keeps no Vessel for this participant.
```

### 1.2 reproduction

```
PYTHONIOENCODING=utf-8 PYTHONWARNINGS=error python -X dev -X faulthandler U41_surface_run.py
```

The run asks `view_model` for the demo chain with `participant` and `class_name` set.

### 1.3 the cause

The first version matched the wallet's address against the party rows. Those are two
different identities: the wallet's Reincarnate is `BotIdentity.bot_id` from
`bot_identity.json`, and a party row's `participant` is the first eight characters of
a fleet bot id from `bot_state.json`. No party row can ever carry the node's own
address, so the filter selected nothing whatever the request named.

### 1.4 the correction

`vessels_section` takes the `ClassPick` that `view_model` already builds and compares
its participant with the wallet address, which is one identity rather than two.

```python
def vessels_section(address: str | None, pick: ClassPick | None) -> dict:
    if address is None:
        return section(VESSELS_SECTION, [], NO_IDENTITY_NOTE)
    if pick is None or pick.participant != address:
        return section(VESSELS_SECTION, [], NO_VESSEL_NOTE.format(name=STORE_NAME))
```

### 1.5 the rerun

Same command, and the section now answers differently for the two inputs.

```
pick names this node        [{'label': 'Iron Edge', 'value': 'level 1 - Impetus 4'},
                             {'label': 'Summed requirement', 'value': '--'}]
pick names somebody else    []  poa_record_store.json keeps no Vessel for this participant.
```

Read off the rendered Qt page rather than off the model:

```
sections  ['Quintessence', 'Trophies', 'Loot', 'Vessels']
rows      Iron Edge  level 1 - Impetus 4
          Summed requirement  --
note      No field holds the Quintessence a Vessel's level requires, so no
          requirement sums against the balance above.
```

---

## 2 - stylelint refused a deprecated keyword

### 2.1 the error

```
exit 2
871:15  declaration-property-value-keyword-no-deprecated
        Deprecated keyword "break-word" for property "word-break"
```

### 2.2 reproduction

```
node node_modules/stylelint/bin/stylelint.mjs --formatter json src/gui/web/proof_of_accumulation_tab.css
```

The report is written to stderr, and the exit code is 2 rather than 1.

### 2.3 the cause

The reset panel's value column asked for `word-break: break-word` so a file name
could wrap. That keyword is deprecated; the sheet's own wallet value column already
used `break-all` for the same job.

### 2.4 the correction

`word-break: break-all`, which is what the neighbouring rule uses.

### 2.5 the rerun

```
exit 0   errored false   warnings []
```

The red came from the ordinary development cycle. Nothing was planted.

---

## 3 - The shell driver read the standing answer back for the second refusal

### 3.1 the error

```
playwright._impl._errors.TimeoutError: Page.wait_for_function: Timeout 30000ms exceeded.
```

### 3.2 reproduction

```
python U41_shell_drive.py
```

Press Ask on the live chain, then press Confirm on the live chain.

### 3.3 the cause

The wait watched for a verdict sentence different from the one standing. Both reset
buttons refuse on the live chain with one sentence, so the sentence never changed and
the wait ran to its timeout. This is the same shape unit 36 recorded for a repeated
control.

### 3.4 the correction

A second wait watches the verdict's `data-action`, which moves even when the sentence
does not.

### 3.5 the rerun

```
-- reset on the live chain            acted false  action reset
-- reset confirmed on the live chain  acted false  action reset_confirm
```

---

## 4 - The chain-growing run refused its own competition ids

### 4.1 the error

```
ValueError: Need >= 2 participants
```

then, on a second run,

```
ValueError: competition u41-demo-0 already exists
```

### 4.2 reproduction

```
python U41_grow_chain.py 3
```

### 4.3 the cause

The first fault was mine: `activate` needs two registered wallets and the run
registered one. The second was a fixed id: a second run of the same script opened
`u41-demo-0` again on a chain that already held it.

### 4.4 the correction

Two wallets are registered, and each id counts from the competitions the chain
already reports holding.

```python
opened = net.get_competition_stats()["total_competitions"]
comp = f"u41-demo-{opened + at}"
```

### 4.5 the rerun

```
before 0 0
after 12 14371
file testnet_chain_testnet.log 14371
```

---

## 5 - The Qt picture of this tab is flat white

### 5.1 the error

No traceback. `QWidget.grab()` on the panel saved a 7,105-byte all-white PNG while
the page underneath reported two meters, eleven control buttons and no faults.

### 5.2 reproduction

```
ACERVATOR_VARIANT=qt QT_QPA_PLATFORM=offscreen PYTHONWARNINGS=error \
python -X dev -X faulthandler U41_qt_render.py testnet
```

### 5.3 the cause

The panel draws through `QWebEngineView`, whose content the widget grab does not
capture. This is the shape already catalogued as OCIR C37.

### 5.4 the correction

Nothing in the product. The picture of this screen is taken in the Electron shell,
where the same renderer module draws with real fonts, and the Qt side is compared by
the values its page reports rather than by a picture.

### 5.5 the rerun

The shell's own screenshots carry the layout, and the Qt page's values are read with
the same script the shell uses.

---

## 6 - The player window clipped what it held

### 6.1 the error

No traceback. In the shell screenshot the meter pair was cut off at the zone's lower
edge, and neither the map button nor the eight mode rows appeared at all.

### 6.2 reproduction

```
python U41_shell_drive.py
```

Read `U41_react_closed.png`.

### 6.3 the cause

The zone carries `overflow: hidden` and its content is taller than the row the tab's
grid gives it. The two meters made an existing overflow visible.

### 6.4 the correction

The player window scrolls inside itself, which is the treatment the conservation and
season panels already use.

```css
.acervator-poa-tab [data-part="player-window"] {
  display: flex;
  flex-direction: column;
  gap: calc(var(--SPACE_XS) * 1px);
  overflow-y: auto;
}
```

### 6.5 the rerun

The zone draws its own scrollbar and nothing it holds is unreachable.

---

## 7 - The wallet's four holdings had no height, and the reset panel drew a sliver

### 7.1 the error

No traceback. The wallet panel captured 180 pixels tall with four section headings
cut through the middle, and the reset panel captured as a 10-pixel bar.

### 7.2 reproduction

```
python U41_shell_drive.py
```

Read `U41_react_wallet.png` and `U41_react_reset.png`.

### 7.3 the cause

The wallet stacked four chrome rows above its holdings: the title, the Close button
alone on a line, the participant and the chain. The reset panel sat in the party
window beside four other panels, each capped at 30% of a zone that was already short.

### 7.4 the correction

The wallet lays its chrome on two rows, the title beside Close and the participant
beside the chain, so the four holdings take every line left. The reset panel moved
under the two buttons it reports on, where it pairs its five readings across the
width.

### 7.5 the rerun

```
wallet   Quintessence  Trophies  Loot  Vessels, four equal cards, each with its rows
reset    Checkpoint | Log        A deliberate reset reads | A schema wipe reads
                                 Bytes both files hold
```

---

## 8 - What the page drew, and what each control did

Read off the rendered document in the Electron shell, with a part name that does not
exist as the control.

| part | count | control `no-such-part-zz` |
|---|---|---|
| `meter` | 2 | 0 |
| `meter-pair` | 1 | 0 |
| `reset-panel` | 1 | 0 |
| `wallet-section` | 4 | 0 |
| `control-button` | 11 | 0 |

### 8.1 both meters, quoted at two moments

Between the two readings the chain was given more records through its own save path.

```
moment one   BLOCK FILL 2.7%   28230 of 1048576 bytes
             TURN COMPLETION 98.7%   296s of 300s elapsed
moment two   BLOCK FILL 3.7%   38778 of 1048576 bytes
             TURN COMPLETION 99.0%   297s of 300s elapsed
after reset  BLOCK FILL 0.0%   0 of 1048576 bytes
```

### 8.2 the reset, on the demo chain

```
ask       refused   testnet_chain_testnet.json and testnet_chain_testnet.log hold
                    38778 bytes at block height 32. Confirm the reset deletes both;
                    this control deletes nothing.
                    Block height 32 | Chain events 24 | Bytes 38778
page      unchanged BLOCK FILL 3.7%, 38778 bytes, block height still 32
confirm   acted     testnet_chain_testnet.json and testnet_chain_testnet.log are
                    deleted and the Demo TestNet chain stands at block height 0 for
                    the reason the Accumulation tab's reset control.
                    Block height 0 | Chain events 0 | Bytes 0
```

On the live chain both buttons refuse.

```
Reset clears the Demo TestNet chain. The Live chain is the one a running window
holds in memory, which would write it back, so this refuses there.
```

### 8.3 the two reasons, on screen together

```
A deliberate reset reads   the Accumulation tab's reset control
A schema wipe reads        schema version upgrade (another schema → 1)
```

---

## 9 - Both variants, compared field by field

The same reading script ran against the Qt page and against the Electron page, two
seconds apart, with the demo chain untouched between them.

```
fields compared   20
identical         16
differing          4   eventTurn, meterPercents, meterValues, meterFillWidths
```

Every difference is the live candle clock.

```
qt      Turn 5963585 - one 5m candle - 59s left   80.3%   241s of 300s elapsed
react   Turn 5963585 - one 5m candle - 57s left   81.0%   243s of 300s elapsed
```

Block fill is identical on both sides, `2.7%` and `28226 of 1048576 bytes`, as are
the four wallet section names, the five reset rows and the eleven control actions.

---

## 10 - The instruments

Proved once, each read out of the JSON rather than off an exit code.

| instrument | known good | known bad |
|---|---|---|
| `coding_archetype` python | exit 0, `passed=true` | exit 1, `passed=false` |
| `coding_archetype` js | exit 0, `passed=true` | exit 1, `passed=false` |
| `docs_archetype` | exit 0, `passed=true` | exit 1, `passed=false` |
| `gui_archetype` widget | exit 0, `passed=true` | exit 1, `passed=false` |
| `gui_archetype` screen | exit 0, `passed=true` | exit 1, `passed=false` |
| `gui_archetype` style | exit 0, `passed=true` | exit 1, `passed=false` |
| `ta_archetype` | exit 0, `passed=true` | exit 1, `passed=false` |
| `stylelint` | exit 0, `errored=false` | exit 2, one error, on this file |
| `eslint` | exit 0, 0 errors | exit 1, 1 error, on this file |

`stylelint`'s red is the one recorded in section 2 and came from the work.
`eslint` reported nothing on this file, so it was shown able to report: an unused
part name was added, `eslint` answered `exit 1, no-unused-vars`, the line was removed
and the file compared byte-identical afterwards.

```
before the plant   2325acf17a5e218c152a0d227c9732d42e6c9b9c2985d439809469725d00a098
after the restore  2325acf17a5e218c152a0d227c9732d42e6c9b9c2985d439809469725d00a098
```

A further control: the reading script counts a part name that exists in no page,
`no-such-part-zz`, and answers 0 beside every non-zero count above.

---

## 11 - The verdicts

Every file through the archetype that owns it. `passed` and `tool_availability` read
out of the JSON on stdout.

| file | archetype | passed | tools |
|---|---|---|---|
| `shared_testnet.py` | coding | True | all ok |
| `shared_testnet.py` | ta | True | all ok |
| `shared_testnet.py` | gui | True | all ok |
| `proof_of_accumulation_tab_surface.py` | coding | True | all ok |
| `proof_of_accumulation_tab_surface.py` | ta | True | all ok |
| `proof_of_accumulation_tab_surface.py` | gui | True | all ok |
| `proof_of_accumulation_tab.js` | coding | True | all ok |
| `proof_of_accumulation_tab.js` | gui | True | all ok |
| `proof_of_accumulation_tab.css` | gui | True | all ok |
| `proof-of-accumulation.md` | docs | True | all ok |

The lanes, both with `--all`.

```
black    PASSED - 1 lane(s) ran, 0 failed
flake8   PASSED - 1 lane(s) ran, 0 failed
```

`black` refused `shared_testnet.py` once, on a signature it wanted on one line, and
was applied.

The manual diff removes two lines, one sentence, and each is paired with what
replaced it.

| removed line | replacement |
|---|---|
| `while the wallet is closed. Opening the wallet lays three holdings side by side` | `while the wallet is closed. Opening the wallet lays four holdings side by side` |
| `across the party window: Quintessence, trophies, loot.` | `across the party window: Quintessence, trophies, loot, Vessels.` |

---

## 12 - What this does not reach

No control on the page picks a class, so the Vessels section reads a Vessel only when
a request carries one. That reading was taken on the Qt page, which is built from a
model the caller supplies; the Electron page has no control that sends a class name.

No field anywhere holds what a Vessel's level requires, so the summed requirement row
draws two dashes. The row and its sentence are the seam.

Nothing records the bytes one world turn wrote. The fill meter reads every byte the
chain holds since its last reset, and says so on the page.

The reset refuses on the live chain. A running window holds that chain in memory and
would write it back, so deleting its files would not clear it.

The tab's three equal rows leave the player window about a hundred pixels at a
thousand-pixel window height, so the meter pair is reached by scrolling that zone.
Re-proportioning those rows would change the whole screen and belongs to no feature
in this unit.
