# C43 entry gate — classification of every archived-pin failure

**Date** 2026-08-05 · **Baseline** commit `861611a`, v3.24.32, 1105 tests
**Requirement** C43's entry gate: both archived gate tests restored, run,
and every failure classified in writing as **(i) import/path drift** or
**(ii) a genuine gate defect** — so a rewrite does not silently discard a
real red.

---

## 1. `test_check_release_readiness.py` — 13 tests, 0 collected

```
tests/test_check_release_readiness.py:26: in <module>
    from tools.check_release_readiness import (
E   ModuleNotFoundError: No module named 'tools.check_release_readiness'
```

**Classification: (i) path drift — collection-time, whole module.**

The tool moved to `tools/harness/check_release_readiness.py`. The
archived module imports six names:

| Imported name | Exists in current tool? |
|---|---|
| `main` | **yes** |
| `_read_init_version` | no — now `_read_version` (`:53-59`) |
| `_read_main_version` | **no — nothing reads `main.py` at all** |
| `_first_changelog_block` | no |
| `_changelog_block_has_version` | no |
| `_changelog_block_test_count` | no |

A verbatim restore yields the *wrong* red: an ImportError, not a failing
assertion. Nothing here is evidence of a gate defect.

**But the absence is itself the finding.** Five of the six helpers do not
exist because the current gate **does not implement those checks**:

- `_read_main_version` — the current gate never opens `main.py`. The
  archived `test_init_and_main_versions_match` is precisely the pin that
  would have caught NF-133 (three stale literals: boot log `:540` and
  `setApplicationVersion` `:555` both say `"3.1.26"` at build v3.24.32).
- The three `_changelog_*` helpers — the current gate never checks that
  CHANGELOG mentions the banner or that its test count matches.

So the correct reading is **not** "13 obsolete tests". It is "13 tests
encoding four contracts, of which the current gate implements one."

## 2. `test_release_gate_hook.py` — 11 tests, 4 failed / 7 passed

**All 11 are (i) contract drift. And the 7 passes are worthless.**

Drift on three independent axes:

| Axis | Archived pin | Current hook |
|---|---|---|
| Payload key | `{"tool": "Edit"}` | reads `tool_name` (`:99`) |
| Sidecar path | `.sadp/.last_release_check.json` (`:22`) | `.release_ready.json` (`:35`) |
| Deny signal | asserts `rc == 2` | **always exits 0**; decision is JSON on stdout (`:17`, `:118-128`) |
| Timestamp | `int(time.time())` | ISO-8601 string (`fromisoformat`, `:71`) |

### 2.1 The 7 "passes" are vacuous — measured

Because the hook reads `tool_name` and the pin sends `tool`, `main()`
returns 0 at `:100` before reading the sidecar, the target path, or
anything else. Every archived payload is a no-op.

Probe, real sidecar deleted (the exact case the pin exists to catch),
restored in a `finally`:

```
=== sidecar MISSING ===
  archived shape : rc=0  NO OUTPUT = ALLOW
  current shape  : rc=0  decision=deny
```

The hook is correct. **The pin cannot see it.** All 7 green assertions
are `assert rc == 0` against a function that returns 0 unconditionally
for their input. They would stay green if the hook body were deleted.

### 2.2 The 4 failures, individually

| Test | Why it failed | Class |
|---|---|---|
| `..._without_sidecar` | unlinks `.sadp/...`, which nothing reads; asserts `rc==2`, never returned | (i) |
| `..._with_unrelated_sidecar_version` | writes to the ignored path; asserts `rc==2` | (i) |
| `..._denies_stale_sidecar` | writes epoch-int timestamp to the ignored path; asserts `rc==2` | (i) |
| `..._changelog_new_entry_without_sidecar` | `CHANGELOG.md` is **not in `BANNER_PATHS`** (`:38-41`) | (i) drift, **and a real coverage gap** |

**No failure among the four is a genuine gate defect.** The hook behaves
correctly on every case once addressed with the payload it actually
consumes.

## 3. Genuine findings surfaced by the exercise

Not failures of the restored tests — gaps the restored tests were the
only thing that would have named.

- **G1** — The gate never reads `main.py`. NF-133's three stale literals
  are invisible to it. *(C43 step 6.)*
- **G2** — `CHANGELOG.md` is not a `BANNER_PATH`, so a new version
  header can be added with no sidecar at all. The cascade order treats
  the CHANGELOG entry as part of the banner promise; the hook does not.
- **G3** — The gate accepts `--no-pytest --no-archetypes --no-claims`
  and still prints `[OK]` and writes a green sidecar. **Observed in the
  wild this session:** a `"tests": 0` green sidecar sat in the tree for
  46 minutes, left by a skipped run. *(C43 steps 3–4.)*
- **G4** — The hook trusts any sidecar with a fresh ISO timestamp. It
  cannot distinguish a full run from a skipped one, because the sidecar
  does not record which checks ran. *(C43 step 4 — `checks_run`.)*

## 4. Consequence for the rewrite

Per **M7** (never modify a test to make it pass): these pins are not
being *relaxed*, they are being **re-pointed at the contract that
exists**, and the vacuity is being removed. Recorded here in writing
because M7's escape hatch is replacement-with-consent, not relaxation.

Rules for the rewrite:
1. Assert on the **stdout JSON decision**, never on exit code.
2. Send `tool_name`. Add an explicit pin that a payload carrying only
   the legacy `tool` key is *not* silently allowed — the vacuity must
   become impossible to reintroduce.
3. Use `.release_ready.json` and ISO timestamps.
4. Keep `test_init_and_main_versions_match` in spirit, widened to all
   three `main.py` literals (G1).
5. Drop the three `_changelog_*` helper tests only if the CHANGELOG
   contract is not being reinstated; if G2 is fixed, restore them.
