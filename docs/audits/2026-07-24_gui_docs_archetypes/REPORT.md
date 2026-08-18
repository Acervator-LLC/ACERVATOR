# GUI + Documentation Archetypes — Multi-Agent Test

**Date**: 2026-07-24
**Purpose**: Prove or falsify that the GUI and Documentation archetypes work as an initial design, using the same test structure as the Coding Archetype (fixture ground truth + parallel Claude peer reviewers).

**FALSIFICATION**: this report is wrong if (a) the archetype JSON on disk doesn't match the numbers below (grep the `archetype_known_bad.json` files to check), (b) the peer-reviewer transcripts contradict the recall summaries (files in `gui_raw/` and `docs_raw/`), or © the ground-truth defect list in each fixture doesn't align with what I claim was caught.

---

## Session-limit incident (transparent)

During the first parallel launch of 4 subagents (2 GUI + 2 Docs), the session hit its 19:30 PST usage limit mid-flight. Docs Reviewer B failed with “session limit” error at 19:09 PST. GUI Reviewer A completed. The other two produced no transcript.

Recovery: after the reset, I re-spawned the 3 missing reviewers in a single batched message. All 3 completed successfully. Transcripts saved as `peer_reviewer_B.md` (GUI) and `peer_reviewer_A.md` + `peer_reviewer_B.md` (Docs). The first Docs Reviewer B failure is noted but its transcript was never produced — the “B retry” transcript stands as the B result.

No results were fabricated to fill the gap.

---

## What was built

- **`tools/harness/gui_archetype.py`** (17 KB) — invokes:
  - `gui-static` (AST-based PySide6 analyzer built in this file): checks `setAccessibleName`/`setAccessibleDescription` on QWidget subclasses, `setGeometry` used without QLayout, child widgets constructed without parent argument, missing class docstrings.
  - `ruff` — subprocess, --select=ALL, JSON output
  - `bandit` — subprocess, JSON output
- **`tools/harness/docs_archetype.py`** (11 KB) — invokes:
  - `proselint` — subprocess, JSON output
  - `structure` (in-file): H1 presence check, Diataxis-mode-signal check in opening 500 chars
  - `vale` — attempted subprocess; gracefully marked `missing` when Vale binary isn't installed (Windows box has no npm/winget/scoop)

Same subprocess-normalize pattern as Coding Archetype. No sadp/sadp2 dependencies.

---

## Fixtures + ground truth

### GUI (`gui_fixtures/`)
- `known_good_widget.py` — proper PySide6 widget with class docstring, accessible names on self + children, QVBoxLayout, parented children. Ground truth = 0 defects.
- `known_bad_widget.py` — 5 labeled defects in the module docstring:
  - **G1** no_accessible_name (line 23)
  - **G2** missing_docstring (line 23)
  - **G3** absolute_positioning (lines 30/32-33)
  - **G4** child_widget_no_parent (lines 26/29)
  - **G5** hardcoded_password (line 20)

### Docs (`docs_fixtures/`)
- `known_good.md` — clean how-to per Google style: H1 title, explicit mode label, Prerequisites/Steps/Verify/Rollback sections. Ground truth = 0 defects.
- `known_bad.md` — deliberately dirty. Not labeled D1-DN in the file, but ground-truth defects for scoring:
  - **D1** no H1 title (structural)
  - **D2** no Diataxis mode signal (structural)
  - **D3** duplicate `## Step One` headings (structural)
  - **D4** cliches, weasel words, corporate speak (prose)
  - **D5** typography — straight vs curly quotes (prose)

---

## GUI archetype results

### Recall on known_bad_widget.py (5 ground-truth defects)

| Defect | GUI Archetype | Reviewer A | Reviewer B |
|---|---|---|---|
| G1 no_accessible_name | ✓ gui-static GUI001 (high) | ✓ (high) | ✓ (high) |
| G2 missing_docstring | ✓ gui-static GUI002 (medium) | ✓ (medium) | ✓ (medium) |
| G3 absolute_positioning | ✓ gui-static GUI003 (high, x2) | ✓ (high) | ✓ (high) |
| G4 child_widget_no_parent | ✓ gui-static GUI004 (medium) | ✓ (medium) | ✓ (medium) |
| G5 hardcoded_password | ✓ bandit B105 (high) + ruff S105 (high) | ✓ (high) | ✓ (high) |
| **Recall** | **5/5 (100%)** | **5/5 (100%)** | **5/5 (100%)** |

### Precision on known_good_widget.py

| Reviewer | Total findings | High/critical | False positives on ground truth |
|---|---|---|---|
| GUI Archetype | 1 (low: ruff D107 missing docstring in __init__) | 0 | 0 |
| Reviewer A | 0 | 0 | 0 |
| Reviewer B | 0 | 0 | 0 |

Pass gate: archetype correctly reported `passed=true` on good, `passed=false` on bad.

### What the archetype caught that reviewers didn't (or ranked differently)

- Archetype flagged G3 twice (once per `setGeometry` call at lines 32 and 33). Reviewers collapsed both into a single finding.
- Archetype gave G5 hardcoded password `high` from both ruff S105 and bandit B105 — two-tool agreement. Reviewers gave it single-source `high`.

### What the reviewers caught that the archetype didn't

- **Button label “Go” is non-descriptive** (both reviewers, low severity). Semantic — archetype has no rule for “check semantic quality of visible button text.”
- **No signal wiring** — the button's `clicked` is never connected, the widget is functionally inert (both reviewers, low/medium). Static AST could detect this in principle; not implemented.
- **No custom signal declared** for parent observers (Reviewer B, low). Semantic.

---

## Docs archetype results

### Recall on known_bad.md (5 ground-truth defects)

| Defect | Docs Archetype | Reviewer A | Reviewer B |
|---|---|---|---|
| D1 no H1 title | ✓ structure DOC001 (medium) | ✓ (high) | ✓ (high) |
| D2 no Diataxis mode signal | ✓ structure DOC003 (low) | ✓ (high) | ✓ (high) |
| D3 duplicate `## Step One` | ✗ **MISS** | ✓ (high) | ✓ (high) |
| D4 cliches / weasel / corporate | ✓ proselint (8 hits) | ✓ (multiple) | ✓ (multiple) |
| D5 curly-quotes typography | ✓ proselint typography.symbols.curly_quotes (high) | ✗ | ✗ |
| **Recall** | **4/5 (80%)** | **4/5 (80%)** | **4/5 (80%)** |

### Precision on known_good.md

| Reviewer | Total findings | High/critical | False positives on ground truth |
|---|---|---|---|
| Docs Archetype | 0 | 0 | 0 |
| Reviewer A | 4 (all low, style preferences) | 0 | 0 |
| Reviewer B | 5 (all low, style preferences) | 0 | 0 |

Pass gate: archetype correctly reported `passed=true` on good, `passed=false` on bad.

### Cross-coverage — different reviewers caught different things

- **Archetype ONLY**: D5 curly quotes (proselint's `typography.symbols.curly_quotes` rule — LLM reviewers didn't notice this).
- **Reviewers ONLY**: D3 duplicate heading (structural check in the archetype only counts H1 presence and mode signal; needs a heading-uniqueness pass).
- **Both**: D1, D2, D4 — all detected by both mechanical and judgment paths.

### Vale not installed — impact

The archetype reports `vale: missing` in `tool_availability`, gracefully continues, and includes the error in the report. Vale would add:
- Google/Microsoft style pack enforcement (currently missing)
- Custom-dictionary + Acervator-specific style rules
- Substantially wider rule set than proselint

To install on Mac Mini: `brew install vale && vale sync` (or per-platform equivalent).

---

## Detailed reasoning — what the three archetypes prove as a group

1. **The subprocess-normalize pattern generalizes across domains.** Coding, GUI, and Documentation all fit the same architecture: static analyzer + subprocess-invoked tools + normalized findings + pass/fail gate. Three archetypes; same skeleton.

2. **Every archetype passed its “existing test structure” — meaning:**
   - Correctly `passed=true` on the known-good fixture
   - Correctly `passed=false` on the known-bad fixture
   - Multi-agent peer reviewers agreed on the direction (bad flagged, good not gate-failed)
   - No archetype produced a high-severity false positive on clean code

3. **Recall varies by archetype and by fixture:**
   - Coding Archetype v2 (post-installs): 5/5 (100%) on ground truth
   - GUI Archetype: 5/5 (100%) on ground truth
   - Docs Archetype: 4/5 (80%) — missed the duplicate-heading structural defect
   
4. **Multi-agent peer review catches things mechanical tools cannot.** Semantic issues — vague button labels, missing signal wiring, condescending prose, non-actionable how-to steps — all appear in reviewer output and not in archetype output. This validates the two-layer design (mechanical + LLM peer) proposed in the coding-archetype report.

5. **Two independent reviewers converge.** For both GUI and Docs, Reviewer A and Reviewer B independently produced similar recall rates and largely overlapping finding sets. Agreement is empirical evidence the peer signal is not agent-luck.

6. **Cross-coverage matters.** In the Docs case, the archetype caught D5 (curly quotes) that the LLMs missed, AND the LLMs caught D3 (duplicate heading) that the archetype missed. The three-way test surfaces both directions of the gap.

---

## Concrete gaps found (would need fixing before production)

### GUI Archetype
- **Semantic label quality**: no rule for “button label is generic (Go, Submit, Click)” — this is a WCAG best practice.
- **Signal wiring detection**: could statically detect `QPushButton` created without any `.clicked.connect(...)` at module scope.
- **Duplicate-line finding**: G3 fires once per `setGeometry` call — arguably should collapse into one class-level finding.

### Docs Archetype
- **Duplicate-heading check**: `structure` tool needs an additional rule DOC004 that parses heading text and flags repeats.
- **Second-person / third-person consistency**: no rule for detecting “the user” vs “you” — Google style violation but not in proselint's default rule set.
- **Prerequisites/Verify/Rollback scaffolding checker**: if a doc's mode is “How-to,” those sections should be required. Not in the current structure check.
- **Vale not installed**: adds Google + Microsoft style packs; would substantially widen recall. Requires operator install on Mac Mini.

### Both
- **Severity normalization**: I chose severity mappings by hand. A future audit could align these to the operator's own severity semantics (e.g., what actually blocks a cascade).

---

## Verdict — did all agents pass the existing test structures?

**Yes.** All three archetypes:
- Correctly gated (passed=true on good, passed=false on bad)
- Achieved ≥80% recall on ground truth (Coding 5/5, GUI 5/5, Docs 4/5)
- Zero high-severity false positives on the clean fixtures
- Multi-agent peer reviewers agreed on the pass/fail direction for every fixture

Per the operator's condition: proceeding to SADP novel-features identification.

---

## Raw evidence

- `gui_raw/archetype_known_good.json` — archetype pass=true, 1 low finding
- `gui_raw/archetype_known_bad.json` — archetype pass=false, 11 findings across 3 tools
- `gui_raw/peer_reviewer_A.md` — 13 findings on known_bad, 0 on known_good
- `gui_raw/peer_reviewer_B.md` — 11 findings on known_bad, 0 on known_good
- `docs_raw/archetype_known_good.json` — archetype pass=true, 0 findings
- `docs_raw/archetype_known_bad.json` — archetype pass=false, 12 findings (10 proselint + 2 structure)
- `docs_raw/peer_reviewer_A.md` — 22 findings on known_bad, 4 on known_good
- `docs_raw/peer_reviewer_B.md` — 20 findings on known_bad, 5 on known_good

To reproduce:
```
python -m tools.harness.gui_archetype docs/audits/2026-07-24_gui_docs_archetypes/gui_fixtures/known_good_widget.py
python -m tools.harness.gui_archetype docs/audits/2026-07-24_gui_docs_archetypes/gui_fixtures/known_bad_widget.py
python -m tools.harness.docs_archetype docs/audits/2026-07-24_gui_docs_archetypes/docs_fixtures/known_good.md
python -m tools.harness.docs_archetype docs/audits/2026-07-24_gui_docs_archetypes/docs_fixtures/known_bad.md
```
