# 2026-09-09 — Proof of Accumulation: the tab shell and its three zones

Issue #147, unit 4. Files changed:
`src/gui/main_tabs/proof_of_accumulation_tab_surface.py`,
`src/gui/main_tabs/proof_of_accumulation_tab.py`,
`src/gui/react_proof_of_accumulation_tab.py`,
`src/gui/web/proof_of_accumulation_tab.js`,
`src/gui/web/proof_of_accumulation_tab.css`,
`src/gui/main_tabs/empty_tabs.py`, `src/gui/main_window.py`,
`desktop/renderer/index.html`, `tools/conversion_table.py`,
`docs/manual/08-tabs.md` and
[docs/manual/08-tabs/proof-of-accumulation.md](../../docs/manual/08-tabs/proof-of-accumulation.md).
No test file was written.

The Electron shell ran from `desktop/main.js` under the installed Electron
binary with a throwaway home and profile, and the renderer was read over the
Chrome DevTools Protocol through playwright. The tab was also built the way the
main window builds it, under `python -X dev -X faulthandler` with
`PYTHONWARNINGS=error`, and its page read through the page's own
`runJavaScript`.

This screen has no Qt original. `variant_surface.py` registers sixteen
screens and none of them draws a proof-of-accumulation, competition or testnet
surface, so no Qt picture was taken and no side-by-side comparison applies. The
two Qt classes that could have been one are shelved by the operator's directive
of 21 April 2026, and neither was restored or built on.

---

## 1 — The shell would not start: the harness environment runs Electron as node

### 1.1 the error

```
Error: Cannot find module 'electron'
    at Object.<anonymous> (<worktree>/desktop/main.js:13:41)
```

and, once the module resolved,

```
TypeError: Cannot read properties of undefined (reading 'whenReady')
    at Object.<anonymous> (<worktree>/desktop/main.js:182:5)
```

### 1.2 reproduction

```
electron.exe <worktree>/desktop --remote-debugging-port=9358
```

### 1.3 the cause

`ELECTRON_RUN_AS_NODE=1` is set in this session's environment. Electron then
runs the entry file as a plain node script, so `require("electron")` answers the
launcher shim rather than the application module and `app` is undefined.

### 1.4 the correction

The run removes that name from the child's environment before launching. Nothing
in the repository was changed for it.

### 1.5 the rerun

```
GET http://127.0.0.1:9357/json/version   answers
renderer page                            desktop/renderer/index.html
```

---

## 2 — The party window was not the lower half

### 2.1 the error

No traceback. The picture showed the upper band taking 474 pixels of height and
the party window 245, against the operator's own layout, which puts the party
window across the lower half.

### 2.2 reproduction

The shell drew the tab and the picture was saved.

### 2.3 the cause

`src/gui/web/proof_of_accumulation_tab.css` laid the tab out as a flex column
and asked for a half share on each band. The square enemy screen sets its own
height from its width, so the upper band grew past its share and the party
window took what was left.

### 2.4 the correction

Two rows of equal height, below the heading and the state line.

```css
.acervator-poa-tab {
  display: grid;
  grid-template-rows: auto auto 1fr 1fr;
  height: 100%;
}
```

### 2.5 the rerun

The upper band and the party window each take half the space under the heading,
and the wallet panel covers the party window exactly.

---

## 3 — The balance label drew a word the payload does not carry

### 3.1 the error

The party header read `QUINT` where the payload carries `Quint`.

### 3.2 reproduction

The shell drew the tab and the header text was read back with the page's own
`textContent`.

### 3.3 the cause

The style sheet carried `text-transform: uppercase` on the balance label, so the
screen showed a word the surface never served. Every other word on this screen
comes from the payload unchanged.

### 3.4 the correction

The rule was removed. The label draws the string the surface serves.

### 3.5 the rerun

```
[data-part="quint-label"]     Quint
[data-part="quint-balance"]   --
```

---

## 4 — The Scope writer wrote a totals block into a quoted table excerpt

### 4.1 the error

Running the canon Scope writer over the tab page replaced six lines inside a
fenced python block, six hundred lines above the conversion table, with a totals
block.

```
374,379c374,382
< def live_view_model(params: dict, live: Any) -> dict:
---
> React module             2
> Uses React               2
```

### 4.2 reproduction

```
python -m tools.conversion_scope docs/manual/08-tabs.md
```

### 4.3 the cause

`tools/conversion_table.table_span` returned the first line starting with the
table head. The page carries that head three times: two earlier entries quote it
above a two-row excerpt, and the conversion table itself is the third. The
writer rewrote the first excerpt and counted its two rows.

### 4.4 the correction

The span is the widest table under that head, so a page quoting the head above a
short excerpt no longer misdirects the writer.

```python
    spans = []
    for start, line in enumerate(lines):
        if line.startswith(TABLE_HEAD):
            end = start + 2
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            spans.append((start, end - 1))
    if not spans:
        raise LookupError("no line starts with " + TABLE_HEAD)
    return max(spans, key=lambda span: span[1] - span[0])
```

### 4.5 the rerun

The writer now reaches the conversion table and leaves the fenced block alone.
It also disagrees with the committed Scope column on twenty rows and moves five
totals, which is a second finding and not this unit's to settle: the column was
not rewritten, and the three cells this unit touches were set by the rule the
column states.

```
in scope     the running window builds this screen
React side   the file exists because of this conversion
shelved      nothing the window builds reaches it
```

---

## 5 — The Qt-side picture is white, and the page is the instrument

### 5.1 the error

`QTabWidget.grab()` over the built tab saved an all-white picture with the tab
label drawn and nothing else.

### 5.2 reproduction

The tab was built the way the main window builds it and the widget was grabbed
after its page reported loaded.

### 5.3 the cause

The panel draws into a `QWebEngineView`, whose surface is composited outside the
widget's own paint path. A widget grab cannot see it.

### 5.4 the correction

None to the product. The reading comes from the page's own document instead of
from a picture of the widget, and the picture in the report is the shell's.

### 5.5 the rerun

```
page_ready         True
load_finished      True
tab_root           1
zones              player window 2, enemy screen 2, party window 56
party window       8 groups, 40 slots
whole page         66 elements, absent selector 0
```

---

## What the runs report

Three runs, each with every stale renderer killed before and after.

| reading | before, at origin/current | after, on the branch | control, registration removed |
| --- | --- | --- | --- |
| panel names registered | 19, including this one | 19, including this one | 18, this one absent |
| reason the panel gives | none | none | registered no panel to draw |
| tabs on the bar | 10, Accumulation seventh | 10, Accumulation seventh | 9, Accumulation gone |
| host element | 1 | 1 | 0 |
| shell root drawn | 0 | 1 | 0 |
| empty-state root drawn | 1 | 0 | 0 |
| player window elements | 0 | 2 | 0 |
| enemy screen elements | 0 | 2 | 0 |
| party window elements | 0 | 56 | 0 |
| party groups, slots | 0, 0 | 8, 40 | 0, 0 |
| whole page, same counter | 122 | 185 | 154 |
| absent selector, same counter | 0 | 0 | 0 |
| payload fields | 7 | 11 | none served |

The whole-page count is the control beside each zone count. It is never nought
in any of the three runs, so a nought under a zone is a fact about that zone and
not about the counter. The absent selector answers nought in every run through
the same counter.

Opening the wallet is the second control on the same page.

```
closed   0 wallet panels, 0 sections, party window 56, page 185
open     1 wallet panel, 3 sections, party window 63, page 192
```

The pictures are under the session scratchpad.

```
U147U4_final_closed.png   the three zones, wallet closed
U147U4_final_wallet.png   the wallet open over the party window
```

## The archetypes

Read from the `passed` field of each run's JSON, with `tool_availability`
checked.

| file | archetype | passed |
| --- | --- | --- |
| `src/gui/main_tabs/proof_of_accumulation_tab_surface.py` | coding, ta, gui | true |
| `src/gui/main_tabs/proof_of_accumulation_tab.py` | coding, gui | true |
| `src/gui/react_proof_of_accumulation_tab.py` | coding, gui | true |
| `src/gui/main_tabs/empty_tabs.py` | coding, gui | true |
| `src/gui/main_window.py` | coding, ta, gui | true |
| `src/gui/web/proof_of_accumulation_tab.js` | coding, gui | true |
| `src/gui/web/proof_of_accumulation_tab.css` | gui | true |
| `tools/conversion_table.py` | coding, ta | true |
| `docs/manual/08-tabs.md` | docs | true |
| `docs/manual/08-tabs/proof-of-accumulation.md` | docs | true |
| `tests/debug_reports/2026-09-09_poa_tab_shell.md` | docs | true |
| `desktop/renderer/index.html` | gui | true |

The gui archetype owns html and read this file with `html-validate`, reporting
`scanned` true and no findings. The coding archetype is not its owner: pointed
at html it answers `passed` false with no analyzer run, which records an
unexamined file type and is not a finding about the file.

The instrument was proved on the fixtures before any of the above.

```
known_good.py   exit 0
known_bad.py    exit 1
```
