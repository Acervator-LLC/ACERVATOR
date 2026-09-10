# 2026-09-09 — Proof of Accumulation: the Quintessence wallet

Issue #147, unit 15. Files changed:
`src/gui/main_tabs/proof_of_accumulation_tab_surface.py`,
`src/gui/web/proof_of_accumulation_tab.js`,
`src/gui/web/proof_of_accumulation_tab.css` and
[docs/manual/08-tabs/proof-of-accumulation.md](../../docs/manual/08-tabs/proof-of-accumulation.md).
No test file was written.

Unit 4 built the panel. This unit fills it from the ledgers the running program
holds. The wallet reads and never writes: no spend, no transfer, no movement of
any balance.

Two runs drove the change. The Electron shell ran from `desktop/main.js` under
the installed Electron binary with a throwaway home and profile, and its page
was read over the Chrome DevTools Protocol through playwright. The tab was also
built the way the main window builds it, through
`ProofOfAccumulationReactPanel`, under `python -X dev -X faulthandler` with
`PYTHONWARNINGS=error`, and read through the page's own `runJavaScript`.
`main.py` was never launched: it takes an instance lock in the operator's live
tree while he is trading.

Every value below was read off the rendered page, never off the payload. The
throwaway home was seeded through the package's own write methods before any
run: `BotIdentity.generate`, two calls to `QuintessenceLedger.distil` on the
live chain, one on the demo chain, and two calls to `TokenLedger.award`.

---

## 1 — The trophy row cut the competition name in half

### 1.1 the error

No traceback. The trophy row read `Season 4 - comp-autumn-` where the award
record holds `comp-autumn-0002`.

### 1.2 reproduction

The shell drew the tab, the wallet was opened, and the row values were read back
with the page's own `textContent`.

### 1.3 the cause

The surface sliced the competition id to twelve characters, copying a habit that
suits the sixty-four character bot ids in the leaderboard. A competition id is
short and human-readable, so twelve characters land inside a word.

### 1.4 the correction

The row carries the field as the record holds it, and the style sheet breaks a
long value rather than the surface truncating one.

```python
        row(
            f"{award.tier_emoji} {award.tier_name}",
            f"Season {award.season} - {award.competition_id}",
        )
```

### 1.5 the rerun

```
🐻 Bear Slayer   Season 4 - comp-autumn-0002
🪙 Gold Fold     Season 3 - comp-autumn-0001
```

---

## 2 — The panel printed a count with the wrong plural

### 2.1 the error

The demo chain's Quintessence note read `quintessence_ledger_testnet.json, 1
movements`.

### 2.2 reproduction

The wallet was reloaded against the TestNet chain, whose ledger holds one
movement, and the note was read back.

### 2.3 the cause

The note pasted a count into a sentence with a fixed plural. Any ledger holding
exactly one movement printed it wrongly.

### 2.4 the correction

The count is a row like every other figure, and the note is the file name.

```python
        row(MOVEMENTS_ROW, str(summary["movement_count"])),
    ]
    note = path.name if path.exists() else NO_LEDGER_NOTE.format(name=path.name)
```

### 2.5 the rerun

```
live      Movements 2   quintessence_ledger.json
testnet   Movements 1   quintessence_ledger_testnet.json
```

---

## 3 — The demo chain's trophy note named the live file

### 3.1 the error

On the TestNet chain the trophy section read
`acrv_ledger.json records no trophy for this participant.` The file it had
actually looked in was `acrv_ledger_testnet.json`.

### 3.2 reproduction

The wallet was reloaded against the TestNet chain and the note was read back.

### 3.3 the cause

The sentence was built once at import from the live file name, so it could not
follow the chain the section had read.

### 3.4 the correction

The sentence is a template and takes the name of the file the section opened.

```python
NO_TROPHY_NOTE = "{name} records no trophy for this participant."
```

### 3.5 the rerun

```
testnet   acrv_ledger_testnet.json records no trophy for this participant.
```

---

## 4 — A refused ledger printed the whole home path on screen

### 4.1 the error

With the ledger file corrupted, the Quintessence note read

```
<the whole home directory>\.acervator\quintessence_ledger.json could not be
replayed: Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)
```

### 4.2 reproduction

The Quintessence ledger file was overwritten with text that is not JSON, and the
wallet was opened.

### 4.3 the cause

The section printed the ledger's refusal unchanged, and that message carries the
full path of the file it failed on.

### 4.4 the correction

The refusal keeps its reason and loses the directory.

```python
def fault_note(path: Path, exc: Exception) -> str:
    """The text of ``exc``, with ``path`` cut back to the file name it ends in."""
    return str(exc).replace(str(path), path.name)
```

### 4.5 the rerun

```
quintessence_ledger.json could not be replayed: Expecting property name
enclosed in double quotes: line 1 column 3 (char 2)
```

---

## 5 — The loot holding fell below the panel

### 5.1 the error

No traceback. The picture showed Quintessence and part of the trophies, with the
loot section off the bottom edge behind a scrollbar.

### 5.2 reproduction

The shell drew the tab at 1440 by 900 and the wallet was opened.

### 5.3 the cause

The three holdings were stacked down a panel whose height is half the tab, so
the third one had nowhere to go.

### 5.4 the correction

The three share the band across, and each one scrolls inside itself.

```css
.acervator-poa-tab [data-part="wallet-sections"] {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: calc(var(--SPACE_S) * 1px);
  flex: 1 1 auto;
  min-height: 0;
}
```

### 5.5 the rerun

All three holdings draw side by side over the party window, and the loot
sentence is on screen without scrolling.

---

## 6 — The Electron binary was in the cache and not on disk

### 6.1 the error

```
ls: node_modules/electron/dist/electron.exe: No such file or directory
```

after `npm install` reported success.

### 6.2 reproduction

```
npm install --no-save --prefer-offline electron@44.2.0
```

### 6.3 the cause

The install script that unpacks the binary is held behind this npm's
allow-scripts gate, so the package landed without its `dist` directory.

### 6.4 the correction

The unpack step was run directly. Nothing in the repository was changed for it.

```
node node_modules/electron/install.js
```

### 6.5 the rerun

The binary is 246 MB on disk and the shell starts.

---

## What the runs report

Three shell runs, each with every stale renderer killed before and after. All
three read the same seeded home, so the difference between the columns is the
change and not the data.

| reading | removed, at origin/current | on the branch, live | on the branch, testnet |
| --- | --- | --- | --- |
| header balance, wallet closed | -- | 17.25 | 50.00 |
| wallet panels, open | 1 | 1 | 1 |
| wallet sections, open | 3 | 3 | 3 |
| wallet rows, open | 0 | 7 | 5 |
| Balance | none drawn | 17.25 | 50.00 |
| Distilled, all time | none drawn | 17.25 | 50.00 |
| Still mintable | none drawn | 32999982.75 | 32999950.00 |
| Supply cap | none drawn | 33000000 | 33000000 |
| Movements | none drawn | 2 | 1 |
| Participant | none drawn | a9c147423045 | a9c147423045 |
| trophy rows | 0 | 2 | 0 |
| whole page, same counter | 523 | 556 | 550 |
| absent selector, same counter | 0 | 0 | 0 |
| panel host faults | none | none | none |

The whole-page count sits beside every other count and is never nought, so a
nought under a row count is a fact about that row and not about the counter. The
absent selector answers nought through that same counter in every run.

The tab was also built the way the main window builds it, and its page agrees.

```
load_finished      True
page_ready         True
wallet closed      0 panels, 0 rows, header balance 17.25, page 80 elements
wallet open        1 panel, 3 sections, 7 rows, page 120 elements
row values         a9c147423045, live, 17.25, 17.25, 32999982.75, 33000000, 2,
                   Season 4 - comp-autumn-0002, Season 3 - comp-autumn-0001
```

### Breaking each source empties its own holding

Two controls, each read at the rendered page.

```
ledger corrupted   Quintessence 0 rows, its refusal printed, header balance --,
                   trophies still 2 rows, page 104 elements
identity removed   Participant none, Balance --, trophies 0 rows with a reason,
                   Quintessence still 5 rows, page 110 elements
```

### The demo chain

The chain rides in the request to the one bridge method, so the TestNet run uses
the same module, the same page and no second surface. It reads a differently
named ledger file and draws a different balance.

```
live      Balance 17.25   quintessence_ledger.json
testnet   Balance 50.00   quintessence_ledger_testnet.json
```

### Loot

Loot has no contract and no store, so it draws no row and prints one sentence.
Nothing about a loot item is invented anywhere on the page.

```
No loot contract and no loot store is built. Nothing is read.
```

### The pictures

```
U147U15_final_closed.png    the persistent balance in the party header
U147U15_final_open.png      the wallet open over the party window
U147U15_final_testnet.png   the same page on the demo chain
U147U15_removed_open.png    the same panel with this change removed
```

They are under the session scratchpad.

## The archetypes

Read from the `passed` field of each run's JSON, with `tool_availability`
checked. Every tool in every run reported ok, and every `errors` list was empty.

| file | archetype | passed |
| --- | --- | --- |
| `src/gui/main_tabs/proof_of_accumulation_tab_surface.py` | coding, ta, gui | true |
| `src/gui/web/proof_of_accumulation_tab.js` | coding, gui | true |
| `src/gui/web/proof_of_accumulation_tab.css` | gui | true |
| `docs/manual/08-tabs/proof-of-accumulation.md` | docs | true |
| `tests/debug_reports/2026-09-09_poa_quintessence_wallet.md` | docs | true |

The coding archetype does not own a style sheet: the GUI archetype reads that
one through stylelint. The instrument was proved on the fixtures before any of
the above.

```
known_good.py   exit 0
known_bad.py    exit 1
```

## What is not built

The wallet displays. A spend path belongs to unit 13, a transfer path to the
skill in unit 21, and the loot store to unit 19. None of the three is in this
change, and the panel carries no control that could move a balance.
