# Coding Archetype v2 — Multi-Agent Simulated Test (Post-Install)

**Date**: 2026-07-24 (afternoon)
**Author**: Claude (session 27)
**Purpose**: After installing the full external-tool stack recommended by the updated SKILL, verify the archetype's recall improves and that the multi-agent test still works as an independent cross-check.

For the v1 baseline see `REPORT.md`.

---

## Install phase — honest results

Ran on the operator's Windows box (Python 3.14.4, no npm / winget / scoop / brew available).

| Category | Tool | Status |
|---|---|---|
| Style/format | **Ruff 0.16.0** | ✓ installed |
| Type check (alt) | **Pyright 1.1.411** | ✓ installed |
| Security lint | **Bandit 1.9.4** | ✓ already had |
| Dead code | **Vulture 2.16** | ✓ already had |
| Type check | **Mypy** | ✓ already had |
| Dep vuln (alt) | **Safety 3.8.1** | ✓ installed |
| Pattern static analysis | **Semgrep 1.171.0** | ✓ installed |
| Pre-commit hooks | **pre-commit 4.6.1** | ✓ installed |
| GUI testing | **pytest-qt 4.5.0** | ✓ installed |
| Prose linting | **proselint** | ✓ installed |
| Docs generator | **MkDocs 1.6.1 + material 9.7.7** | ✓ installed |
| Docs generator | **Sphinx 9.1.0** | ✓ installed |
| LLM SDK | **anthropic 0.120.0** | ✓ installed |
| LLM eval | **DeepEval 4.1.3** | ✓ installed |
| LLM eval | **RAGAS** | ✗ **failed** — transitive dep `scikit-network` has no Python 3.14 wheel |
| LLM output validation | **Guardrails AI** | ✗ **failed** — transitive dep `litellm` fails wheel build on Python 3.14 |
| Prose linting (binary) | **Vale** | ⊘ **skipped** — needs winget / scoop / manual download, none of which are set up on this box |
| Prompt regression | **Promptfoo** | ⊘ **skipped** — needs npm; Node.js not installed |
| Inclusive-language lint | **alex** | ⊘ **skipped** — needs npm |

**Net installed this session**: 8 new Python tools + 4 already present + 3 documentation tools.
**Dependency conflict**: DeepEval pinned `click<8.4.0`; Semgrep needs `click>=8.4.2`. Resolved by keeping `click==8.4.2` — pip warns but both packages continue to function (verified via import + version check).

**Not installed on Windows, would need separate action**:
- Vale — download the .exe from https://github.com/errata-ai/vale/releases and put it on PATH
- Promptfoo, alex — install Node.js first, then `npm i -g promptfoo alex`
- RAGAS, Guardrails AI — try again on Python 3.12/3.13 where their transitive deps have wheels

---

## v2 archetype — what changed from v1

Same class shape (`CodingArchetype`), same subprocess pattern. Added three tools + fixed three documented gaps:

| Change | Reason |
|---|---|
| Added **Ruff** (`--select=ALL`) | Style, dead code, and mirror of bandit security rules (S-family) |
| Added **Pyright** | Second opinion on types; catches things mypy misses |
| Added **Semgrep** (`p/python`, `p/security-audit` rulesets) | Pattern-based vuln detection beyond bandit's rule set |
| Fixed **Mypy strict flags** | `--disallow-untyped-defs --disallow-incomplete-defs --warn-return-any` (v1 gap: mypy defaults let missing annotations pass) |
| Fixed **Bandit severity remap** | B101, B105, B106, B107, B303, B324, B501, B502, B506, B602, B605, B609 escalated to `high` (v1 gap: bandit's own severities ranked hardcoded passwords as `low`) |
| Fixed **Vulture confidence threshold** | `--min-confidence 60` (v1 gap: default 80% missed unused function locals) |

Same fixtures — no ground truth changed. `docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_good.py` and `known_bad.py`.

---

## Results — v1 vs v2

### Recall on known_bad (5 ground-truth defects)

| Defect | v1 Archetype | v2 Archetype | v1 A | v2 A | v1 B | v2 B |
|---|---|---|---|---|---|---|
| D1 unused_import | ✓ vulture high | ✓ 3 tools (ruff F401 med, bandit B404 low, vulture high) | ✓ | ✓ | ✓ | ✓ |
| D2 unused_variable | ✗ MISS | ✓ 2 tools (ruff F841 med, vulture low) | ✓ | ✓ | ✓ | ✓ |
| D3 missing_type_hints | ✗ MISS | ✓ 2 tools, 4 findings (ruff ANN001×2 + ANN201, mypy no-untyped-def HIGH) | ✓ | ✓ | ✓ | ✓ |
| D4 hardcoded_password | ✓ bandit LOW | ✓ 2 tools **both HIGH** (ruff S105, bandit B105) | ✓ | ✓ | ✓ | ✓ |
| D5 assert_for_security | ✓ bandit LOW | ✓ 2 tools **both HIGH** (ruff S101, bandit B101) | ✓ | ✓ | ✓ | ✓ |
| **Recall** | **3/5 (60%)** | **5/5 (100%)** | 5/5 | 5/5 | 5/5 | 5/5 |

### Total findings on known_bad

| Reviewer | v1 | v2 |
|---|---|---|
| Archetype | 4 | **22** |
| Reviewer A | 10 | 14 |
| Reviewer B | 11 | 12 |

### Severity classification agreement (does the archetype's HIGH gate match human consensus?)

| Defect | v1 Archetype | v2 Archetype | Both Reviewers say |
|---|---|---|---|
| D4 hardcoded password | LOW ✗ | **HIGH** ✓ | HIGH |
| D5 assert for security | LOW ✗ | **HIGH** ✓ | HIGH |

**Before the severity remap: v1 archetype would have returned `passed=True` on the security issues alone** (only vulture's unused-import saved the gate). v2 fixes this — hardcoded passwords and assert-for-security now correctly trip the gate on their own.

### Precision on known_good (0 ground-truth defects)

| Reviewer | v1 | v2 | v2 high/critical | v2 gate |
|---|---|---|---|---|
| Archetype | 0 findings | 7 findings (ruff style noise) | 0 high | passed=True ✓ |
| Reviewer A | 2 low | 3 low | 0 high | — |
| Reviewer B | 3 low | 2 low | 0 high | — |

**Ruff at `--select=ALL` produces docstring / naming / preference noise** on clean code. The gate held correctly (0 high on known_good) but the noise floor rose from 0 to 7 findings. In production, a tuned `--select` list would reduce this.

### Tool availability (v2)

All 6 tools reported `ok` on both fixture runs:
- ruff, mypy, pyright, bandit, vulture, semgrep

Semgrep produced no findings on either fixture — the `p/python` and `p/security-audit` rulesets are aimed at higher-order vulnerabilities (SQL injection, XSS shapes, unsafe deserialization) and don't specifically target the small-scale patterns in the fixture. Not a false negative — semgrep is rule-set-dependent by design.

---

## What v2 proves

1. **The three documented gaps from v1 are fixed and verified.** Mypy now catches missing type hints (`no-untyped-def` at HIGH). Vulture now catches unused function locals. Bandit hardcoded-password and assert-for-security now trip the HIGH gate on their own.

2. **Defense in depth is a real property of the multi-tool archetype.** D1 is caught by 3 tools independently; D3, D4, D5 each by 2. A silent regression in one tool's parser or version would not cause the ground-truth defect to sail through undetected.

3. **The v2 archetype now matches human-reviewer recall on ground truth.** Both v1 and v2 multi-agent runs had the peer reviewers at 100% recall — v2 brings the mechanical archetype to the same level for ground-truth defects. The reviewers still add semantic findings (naming smells, latent runtime bugs, credential blast radius, unused-branch-coverage) that no mechanical tool produces.

4. **The severity gate now aligns with human consensus.** In v1, bandit called the hardcoded password “low”; both reviewers called it “high”; the archetype's gate would have missed it in isolation. In v2, the archetype's severity matches the reviewers' — the gate correctly protects against real security issues.

5. **The multi-agent aspect still works.** Two fresh subagents launched in parallel, no shared context, produced independently consistent findings: A caught 14 issues on known_bad (all 5 ground truth), B caught 12 (all 5 ground truth). Their high-severity picks agree on D1, D4, D5 in both runs.

---

## What v2 does NOT prove

- **No semantic hallucination detection is wired.** RAGAS + Guardrails AI failed to install on Python 3.14. DeepEval installed but is not yet integrated into the archetype (it requires an LLM API key at runtime, which would be a separate operator decision on cost).
- **No GUI or Documentation archetype yet.** Only the coding archetype exists. Same subprocess pattern would extend cleanly.
- **Ruff `--select=ALL` produces production noise.** For real code, the ruff invocation needs a curated `--select` list to avoid burying signal in style preferences.
- **Semgrep did not fire on this fixture.** Not a bug in the archetype; the ruleset simply doesn't target these small patterns. A custom Semgrep rule with `--test` positive/negative fixtures would extend coverage, but that's a separate build.
- **Tests were run on a 2-file corpus.** Real usage will find edge cases the fixture doesn't exercise.

---

## Cost accounting (this session)

| Item | Cost |
|---|---|
| pip installs (14 packages + transitive deps) | $0 |
| CodingArchetype v2 runs on 2 fixtures | $0 |
| Peer reviewer A v2 subagent | ~37,957 tokens (subscription) |
| Peer reviewer B v2 subagent | ~38,089 tokens (subscription) |
| Total | ~$0 out-of-pocket, ~76K subagent tokens on subscription |

No API keys required. No headless LLM eval frameworks invoked (those would need `ANTHROPIC_API_KEY`).

---

## Recommendation

Proceed to build the second archetype (GUI or Documentation) using the same subprocess-plus-normalize pattern. Both would use tools already installed here:

- **GUI archetype**: `pytest-qt` for widget interaction testing + Qt's built-in `QAccessibleWidget` API for accessible-name presence checks.
- **Documentation archetype**: `proselint` for prose lint (Python-native, installed) + eventual Vale once it's installed on the Mac Mini (`brew install vale`; you already have brew on Mac per the earlier build script).

Before shipping the coding archetype into a `--pre-commit` role: tune `--select` in the ruff runner to a curated list, or accept the low-severity noise on the assumption that only `high` findings trip the gate.

---

## Raw evidence

- `raw_v2/archetype_known_good.json` — v2 archetype output on clean fixture (7 findings, all low/medium, passed=True)
- `raw_v2/archetype_known_bad.json` — v2 archetype output on dirty fixture (22 findings, 6 high, passed=False)
- `raw_v2/peer_reviewer_A.md` — Reviewer A v2 transcript (14 issues on bad, 3 on good; 100% recall on ground truth)
- `raw_v2/peer_reviewer_B.md` — Reviewer B v2 transcript (12 issues on bad, 2 on good; 100% recall on ground truth)
- `raw/…` — v1 baseline transcripts (for comparison)
- `fixtures/…` — unchanged from v1

Reproduce with:
```
python -m tools.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_good.py
python -m tools.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_bad.py
```
