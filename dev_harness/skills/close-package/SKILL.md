---
name: close-package
description: Build the session close zip pair. Use when the operator asks for a zip, a close package, or a new drop. Reads the convention off the previous package instead of recalling it.
---

# Close Package

## The package is TWO zips, never one

```
acervator_session<N>_CLOSE_hop5_v<X_Y_Z>.zip
acervator_session<N>_CLOSE_hop5_v<X_Y_Z>_additional_items.zip
```

Both land in `ACERTAVOR PRODUCT DOCUMENTATION/`, beside the working
directory, never inside it.

`<N>` is the SESSION number. It has drifted ahead of the folder name — the
directory reads `session25` while the packages read `session27`. **Take the
number from the newest existing zip, not from the folder.** `<X_Y_Z>` is
`__version__` from `src/__init__.py` with dots as underscores.

Each archive holds ONE top-level folder named exactly like the zip.

## READ THE LAST PACKAGE FIRST. Do not recall this.

The convention is discoverable. Open the newest pair and measure it before
building anything:

```python
import zipfile, os
from collections import defaultdict
z = zipfile.ZipFile(prev)
d = defaultdict(int); c = defaultdict(int)
for i in z.infolist():
    rest = i.filename.split('/', 1)[1] if '/' in i.filename else ''
    top = rest.split('/')[0] if '/' in rest else '(root)'
    d[top] += i.file_size; c[top] += 1
```

That prints size and file count per top-level folder. Match it. Both times
this was got wrong, the answer was sitting in the previous zip.

## The split

| content | primary | additional_items |
|---|---|---|
| `src`, `tests`, `docs`, `tools`, `.vale`, `os`, `contracts` | yes | no |
| `_archive`, `.session26_backups`, `.sadp` | no | yes |
| root-level files | yes | yes — in BOTH |

`.sadp` is session backstop diffs — 845 `.diff` files, no harness files, no
source. It belongs in additional_items.

## EXCLUDE FROM BOTH — this is where the size goes wrong

- `.git`, `.claude`
- `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`,
  `.hypothesis`, `.deepeval`, `.venv`, `node_modules`, `*.pyc`
- **`build/`** — 70.9 MB in 12 files. The repo's own `.gitignore` calls it
  "Build + distribution artefacts (71 MB, fully regenerable)".
- **`dist/`** — 2.2 MB, same reason.
- **`ACERVATOR_DEV_1_BACKUP_2026-05-20.jsonl`** — 62.89 MB of the 63.87 MB
  of root files. A May transcript backup. Because root files go in BOTH
  archives, including it costs ~126 MB across the pair.
- any clone or `git worktree` under the scratchpad. Islands are retired
  (issue #67), so an island directory is no longer one of the shapes; a
  unit's branch checkout is

**A root-level file over ~5 MB is almost certainly a mistake.** Check the
root file list by size before building; the legitimate ones are all under
250 KB.

## Reference sizes

| | entries | on disk | note |
|---|---|---|---|
| v3.25.4 primary | 1160 | 14.1 MB | held `.sadp` (59 MB) — superseded |
| v3.25.4 additional | 1015 | 25.8 MB | |
| **v3.25.5 primary** | **617** | **4.6 MB** | `.sadp` moved out |
| **v3.25.5 additional** | **1889** | **36.7 MB** | `.sadp` 69 MB + `_archive` 43 MB |

**v3.25.5 IS THE CURRENT SHAPE.** The primary got smaller on purpose.
Operator, 2026-08-12: `.sadp` holds no harness files, so "move it to the
additional items zip and leave it there".

**A primary over ~10 MB means something regenerable got in.** The 97 MB
failure was `build/` at 70.9 MB, plus a 62.89 MB transcript backup at root,
plus `.sadp`. Find it before shipping rather than after.

## ONE MORE TRAP, hit twice on 2026-08-12

Inspecting the previous package means `cd`-ing to the PARENT directory,
because that is where the zips live. The session working directory
PERSISTS, and the repo's PreToolUse hook is registered with a REPO-RELATIVE
path. Leave the cwd in the parent and every Write and Edit fails with
"can't open file ... .claude/hooks/archetype_gate.py", including in
subagents, which inherit it.

**`cd` back to the repo root immediately after reading the zips.**

## THE SESSION NUMBER COMES FROM THE HIGHEST VERSION, NOT THE HIGHEST NUMBER

Measured 2026-08-16, after getting it wrong and shipping two zips named
`session79`. Session numbers do NOT rise with version on this disk:

    acervator_session79_CLOSE_hop5_v3_23_20.zip     <- session 79, OLD version
    acervator_session27_CLOSE_hop5_v3_25_7.zip      <- session 27, CURRENT

`max(session)` picks a stale package from a different era and names the new drop
after it. Parse `v(\d+)_(\d+)_(\d+)` from every filename, take the package with
the **highest version tuple**, and read its session number. Print which package
you read it off, so the number is auditable rather than asserted.

## VERIFICATION.md IS READ FROM THE LOGS. NEVER TYPED.

Shipped once with the gate banner, the test count and the tree hash hard-coded.
The bundle then went out labelled `v3.25.8` carrying `v3.25.6` evidence and a
402-file hash against a 404-file tree. **Correct-looking citations attached to
the wrong tree** — the exact failure the bundle exists to prevent, inside the
bundle.

**The builder must REFUSE to write the harness zip when any evidence log is
missing or empty.** A typed VERIFICATION.md is worse than none, because it looks
like proof. Prove the refusal fires before trusting an acceptance: run the build
with no evidence and with one key missing, and check it names what is absent.

Six blocks, six logs: the gate banner, the tree hash before and after, the claim
ledger, the launch smoke, and the archetype positive control.

**The gate banner will read the PREVIOUS version**, because the gate runs before
the bump — that is the required order, not an error. Say so in the file.

**Prove the tree did not move DURING the gate** by listing hashed files whose
mtime is later than the gate log, not by diffing against HEAD. HEAD is a whole
session behind and will name files nobody touched tonight.

## NEVER `cd` TO THE PARENT. USE ABSOLUTE PATHS.

The trap below has now been hit FOUR times: twice on 2026-08-12 and twice more
on 2026-08-16, in the same session, after reading the warning. A reminder is not
working, so here is the mechanical rule:

**Do not `cd` out of the repo root at all.** Read the previous packages with
absolute paths from Python, never by changing directory. The session cwd
persists, the PreToolUse hook is registered with a repo-relative path, and every
Write and Edit fails with "can't open file ... .claude/hooks/archetype_gate.py"
until you return — including inside subagents, which inherit it.

## Verify before reporting done

- `testzip()` returns None on both
- no path containing `credential`
- no `.git/` entries
- per-folder sizes match the previous package's shape
- the primary is in the expected size range

## What went wrong the two times this was done by memory

1. **One zip instead of two.** `_archive` was folded into the primary. The
   operator had both filenames on screen in my own output and I still
   shipped half a package.
2. **Regenerable content included.** `build/` at 70.9 MB and a 62.89 MB
   transcript backup took the primary from 14 MB to 97 MB. Both were
   excluded by the previous package and both are named in `.gitignore`.

Both were discoverable by opening the last pair. That is why step one is
read, not recall.

## FALSIFICATION

This skill is wrong if:

- the previous package's shape is NOT a reliable guide, because the
  convention changed for a reason not recorded here
- a primary in the 14-20 MB range still omits something the operator wanted
- the exclusion list grows every session, which would mean the rule should
  be "include an allow-list" rather than "exclude a deny-list"
- the session number is ever taken from the folder name and is right

Related: `harness-law`.
